"""Blender 3D presentation from verified CAD panels; NEVER fabrication."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from carpinova_agent.cad_exchange import validate_exchange
from integrations.geometry_audit import verify_native_boxes


def assert_visible_preview(pixels):
    """Check saved Blender RGBA PNG data; not a substitute for human review."""
    pixel_count = len(pixels) // 4
    if pixel_count < 4 or len(pixels) % 4:
        raise ValueError("Render PNG sin píxeles RGBA válidos.")
    stride = max(1, pixel_count // 8192)
    samples = [
        max(pixels[4 * i], pixels[4 * i + 1], pixels[4 * i + 2])
        for i in range(0, pixel_count, stride)
    ]
    if max(samples) < 0.12 or max(samples) - min(samples) < 0.08:
        raise ValueError("Render PNG oscuro o sin contraste: escena no visible.")


def render_presentation(input_blend, input_cad, output_blend, output_png):
    import bpy
    from mathutils import Vector

    paths = (input_blend, input_cad, output_blend, output_png)
    if not all(p.is_absolute() for p in paths):
        raise ValueError("Absolute paths required")
    if (input_blend.suffix.lower() != ".blend" or
            output_blend.suffix.lower() != ".blend" or output_png.suffix.lower() != ".png"):
        raise ValueError("Invalid output suffix")
    if any(p.exists() for p in (output_blend, output_png)):
        raise ValueError("Do not overwrite presentation files")
    cad = validate_exchange(json.loads(input_cad.read_text(encoding="utf-8")))
    bpy.ops.wm.open_mainfile(filepath=str(input_blend), load_ui=False)
    meshes = {o.name: o for o in bpy.data.objects if o.type == "MESH"}
    expected = {b["piece_id"]: b for b in cad["boxes"]}
    if set(meshes) != set(expected):
        raise ValueError("Blender panel IDs do not match CAD")
    observed, vertices = [], []
    for name, obj in sorted(meshes.items()):
        points = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        vertices.extend(points)
        low = [min(v[i] for v in points) for i in range(3)]
        high = [max(v[i] for v in points) for i in range(3)]
        observed.append({
            "piece_id": name,
            "native_origin_xyz_mm": [v * 1000 for v in low],
            "native_size_xyz_mm": [(high[i] - low[i]) * 1000 for i in range(3)],
        })
        mat_id = expected[name]["material_id"].upper()
        color = ((0.50, 0.30, 0.16, 1) if ("OAK" in mat_id or "ROBLE" in mat_id)
                 else (0.88, 0.87, 0.82, 1) if ("WHITE" in mat_id or "BLAN" in mat_id)
                 else (0.61, 0.72, 0.80, 1))
        material = bpy.data.materials.new("VIEW_" + name[:48])
        material.use_nodes = True
        material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color
        material.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.65
        obj.data.materials.clear()
        obj.data.materials.append(material)
        obj.color = color  # Workbench uses object colors, not shader nodes.
    proof = verify_native_boxes(cad, observed)
    low = Vector(tuple(min(v[i] for v in vertices) for i in range(3)))
    high = Vector(tuple(max(v[i] for v in vertices) for i in range(3)))
    center, span = (low + high) / 2, max(*(high - low), 0.5)
    camera_data = bpy.data.cameras.new("CarpiNova Camera")
    camera = bpy.data.objects.new("CarpiNova Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = center + Vector((1.6 * span, -2.4 * span, 1.7 * span))
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = span * 2.4
    scene = bpy.context.scene
    scene.camera = camera
    # Prior Cycles CI produced a valid PNG with RGB only 0..1: invisible.
    # Workbench is simpler and deterministic for nominal panel presentation.
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "OBJECT"
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (0.88, 0.91, 0.95)
    scene.display.shading.show_shadows = True
    scene.render.film_transparent = False
    scene.render.resolution_x = 960
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.filepath = str(output_png)
    scene.use_nodes = False  # No stale compositor may hide the scene.
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    bpy.ops.render.render(write_still=True)
    raw = output_png.read_bytes()
    if not raw.startswith(bytes((137, 80, 78, 71, 13, 10, 26, 10))):
        raise ValueError("Invalid Blender PNG")
    saved_image = bpy.data.images.load(str(output_png), check_existing=False)
    try:
        assert_visible_preview(saved_image.pixels)
    finally:
        bpy.data.images.remove(saved_image)
    return {
        "status": "VISUAL_PREVIEW_NOT_FOR_FABRICATION",
        "geometry_sha256": cad["geometry_sha256"],
        "piece_count": proof["verified_piece_count"],
        "native_measurements": proof,
        "png_sha256": hashlib.sha256(output_png.read_bytes()).hexdigest(),
        "fabrication_ready": False, "cutting_ready": False,
        "drilling_ready": False, "purchase_ready": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for key in ("input-blend", "input-cad", "output-blend", "output-png"):
        parser.add_argument("--" + key, required=True, type=Path)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    report = render_presentation(args.input_blend, args.input_cad,
                                 args.output_blend, args.output_png)
    print("BLENDER_PRESENTATION_RESULT=" + json.dumps(report, sort_keys=True), flush=True)
