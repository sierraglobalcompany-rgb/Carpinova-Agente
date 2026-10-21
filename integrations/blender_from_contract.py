"""Blender preview generated exclusively from checked F6 CAD exchange.

Run only inside Blender Python (bpy installed). Do not use to calculate
geometry, drill points, fastener positions, or machine-cut pieces.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from carpinova_agent.cad_exchange import validate_exchange
from integrations.cad_native import native_boxes
from integrations.geometry_audit import verify_native_boxes


def build_blender(input_path: Path, output_path: Path)->dict:
    import bpy
    from mathutils import Vector
    if not output_path.is_absolute() or output_path.suffix.lower()!=".blend":
        raise ValueError("Choose an absolute .blend output path.")
    data=validate_exchange(json.loads(input_path.read_text(encoding="utf-8")))
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    built = []
    for item in native_boxes(data):
        x,y,z=item["native_origin_xyz_mm"]
        dx,dy,dz=item["native_size_xyz_mm"]
        bpy.ops.mesh.primitive_cube_add(size=1, location=(
            (x+dx/2)/1000.0, (y+dy/2)/1000.0, (z+dz/2)/1000.0
        ))
        obj=bpy.context.object
        obj.name=item["piece_id"]
        obj.dimensions=(dx/1000.0,dy/1000.0,dz/1000.0)
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        built.append((item["piece_id"], obj))
    # Read the CREATED meshes, not the expected dimensions, before saving.
    bpy.context.view_layer.update()
    observed = []
    for piece_id, obj in built:
        if obj.name != piece_id:
            raise ValueError("Blender object ID mismatch: " + piece_id)
        world_vertices = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        low = [min(point[axis] for point in world_vertices) * 1000.0
               for axis in range(3)]
        high = [max(point[axis] for point in world_vertices) * 1000.0
                for axis in range(3)]
        observed.append({
            "piece_id": piece_id,
            "native_origin_xyz_mm": low,
            "native_size_xyz_mm": [high[i] - low[i] for i in range(3)],
        })
    verification = verify_native_boxes(data, observed)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    return {
        "geometry_sha256": data["geometry_sha256"],
        "parts": len(observed),
        "status": "VISUAL_PREVIEW_NOT_FOR_FABRICATION",
        "native_measurements": verification,
    }


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    import sys
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    options=parser.parse_args(argv)
    print(json.dumps(build_blender(options.input,options.output)))


if __name__=="__main__":
    main()
