"""F7C Task 3 — modular drawer instances, sourced only from F1 design_drawer.

Inset decorative drawer faces are optional explicit parts. No slide SKU,
runners, drilled holes, fastening or fabrication release.
"""
from __future__ import annotations
import re
from typing import Any

from .core import DesignError, design

IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
GRAINS = {"face_x", "face_y", "none"}
EDGES = {"x_min", "x_max", "y_min", "y_max"}
DRAWER_FIELDS = frozenset({
    "drawer_id", "opening_bottom_offset_mm", "opening_height_mm",
    "opening_depth_mm", "box_height_mm", "panel_thickness_mm",
    "bottom_thickness_mm", "slide_clearance_left_mm",
    "slide_clearance_right_mm", "front_setback_mm", "rear_setback_mm",
    "material_id", "bottom_material_id", "facade"
})
FACADE_REQUIRED = frozenset({
    "style", "material_id", "thickness_mm", "left_clearance_mm",
    "right_clearance_mm", "top_clearance_mm", "bottom_clearance_mm"
})
FACADE_OPTIONAL = frozenset({
    "grain_axis", "edgebanding_edges", "edgeband_thickness_mm"
})


def _mm(value: Any, label: str, *, allow_zero: bool = False) -> int:
    if type(value) is not int or value < 0 or (not allow_zero and value == 0):
        raise DesignError(f"{label}: milímetros enteros {'no negativos' if allow_zero else 'positivos'} requeridos.")
    return value


def _id(value: Any, label: str) -> str:
    if type(value) is not str or not IDENT.fullmatch(value):
        raise DesignError(f"{label}: identificador no válido.")
    return value


def _finish(facade: dict[str, Any], drawer_id: str) -> tuple[str, str | list[str], int | None, int | None]:
    grain = facade.get("grain_axis", "UNCONFIRMED")
    if type(grain) is not str or grain not in GRAINS | {"UNCONFIRMED"}:
        raise DesignError(f"{drawer_id}: veta de frente inválida.")
    edges = facade.get("edgebanding_edges", "UNCONFIRMED")
    thickness = facade.get("edgeband_thickness_mm")
    if edges == "UNCONFIRMED":
        if thickness is not None:
            raise DesignError(f"{drawer_id}: espesor de canto sin bordes.")
        return grain, "UNCONFIRMED", None, None
    if (type(edges) is not list or any(type(e) is not str or e not in EDGES for e in edges)
            or len(edges) != len(set(edges))):
        raise DesignError(f"{drawer_id}: bordes del frente inválidos.")
    if edges:
        _mm(thickness, "edgeband_thickness_mm")
    elif thickness is not None:
        raise DesignError(f"{drawer_id}: espesor de canto sin bordes.")
    return grain, sorted(edges), thickness, 0


def _part(module_id: str, drawer_id: str, role: str, material: str,
          fx: int, fy: int, thickness: int, plane: str, origin: list[int],
          formula: str, *, grain: str = "UNCONFIRMED",
          edges: str | list[str] = "UNCONFIRMED",
          edge_thickness: int | None = None) -> dict[str, Any]:
    band = None if edges == "UNCONFIRMED" else sum(
        fy if e.startswith("x_") else fx for e in edges
    )
    return {
        "piece_id": f"{module_id}-{drawer_id}-{role.upper()}",
        "module_id": module_id, "drawer_id": drawer_id, "role": role,
        "material_id": material, "nominal_face_x_mm": fx,
        "nominal_face_y_mm": fy, "thickness_mm": thickness,
        "face_plane": plane, "nominal_origin_xyz_mm": origin,
        "grain_axis": grain, "edgebanding_edges": edges,
        "edgebanding_thickness_mm": edge_thickness,
        "edgebanding_nominal_total_mm": band,
        "finished_cut_dimensions_mm": None,
        "source_engine": "F1_CORE_DRAWER" if role != "drawer_facade" else "F7C_EXPLICIT_INSET_FACADE",
        "source_formula": formula,
    }


def _facade(data: Any, *, module_id: str, drawer_id: str,
            aperture_width: int, aperture_height: int,
            opening_y: int, opening_x: int,
            front_setback: int) -> tuple[list[dict[str, Any]], list[str]]:
    if data == "pending":
        return [], [f"{module_id}/{drawer_id}: falta frente decorativo de cajón."]
    if type(data) is not dict:
        raise DesignError(f"{drawer_id}.facade: usar pending o un objeto.")
    if set(data) - (FACADE_REQUIRED | FACADE_OPTIONAL) or FACADE_REQUIRED - set(data):
        raise DesignError(f"{drawer_id}.facade: campos ausentes o desconocidos.")
    if data["style"] != "inset":
        raise DesignError(f"{drawer_id}: solo frente embutido inset en este incremento.")
    material = _id(data["material_id"], "facade.material_id")
    thick = _mm(data["thickness_mm"], "facade.thickness_mm")
    gaps = {key: _mm(data[key], "facade."+key) for key in
            ("left_clearance_mm", "right_clearance_mm",
             "top_clearance_mm", "bottom_clearance_mm")}
    fx = aperture_width - gaps["left_clearance_mm"] - gaps["right_clearance_mm"]
    fy = aperture_height - gaps["top_clearance_mm"] - gaps["bottom_clearance_mm"]
    if min(fx, fy) <= 0:
        raise DesignError(f"{drawer_id}: frente embutido no cabe en la abertura.")
    if front_setback <= thick:
        raise DesignError(
            f"{drawer_id}: retranqueo de caja debe superar espesor del frente "
            "para que no ocupen el mismo volumen."
        )
    grain, edges, band_t, _ = _finish(data, drawer_id)
    face = _part(
        module_id, drawer_id, "drawer_facade", material, fx, fy, thick,
        "XY", [opening_x+gaps["left_clearance_mm"],
               opening_y+gaps["bottom_clearance_mm"], 0],
        "F1.clear_width_mm - two explicit horizontal clearances; "
        "drawer.opening_height_mm - two explicit vertical clearances",
        grain=grain, edges=edges, edge_thickness=band_t,
    )
    blockers = [
        f"{module_id}/{drawer_id}: frente decorativo sin uniones, tiradores, "
        "cantos finales ni validación de montaje."
    ]
    if grain == "UNCONFIRMED":
        blockers.append(f"{module_id}/{drawer_id}: falta orientación de veta decorativa.")
    if edges == "UNCONFIRMED":
        blockers.append(f"{module_id}/{drawer_id}: falta decisión de cantos decorativos.")
    return [face], blockers


def module_drawers(drawers: Any, *, module_id: str,
                   start_x_mm: int, carcase_thickness_mm: int,
                   clear_width_mm: int, clear_height_mm: int,
                   module_depth_mm: int, back_parts: list[dict[str, Any]],
                   has_doors: bool) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Append only physical panels calculated by F1, in declared clear apertures."""
    if drawers is None or drawers == "none":
        return [], [], []
    if drawers == "pending":
        return [], [f"{module_id}: elegir cantidad, aperturas y correderas de cajones."], []
    if type(drawers) is not list or not 1 <= len(drawers) <= 4:
        raise DesignError(f"{module_id}.drawers: usar none, pending o lista de 1 a 4.")
    if has_doors:
        raise DesignError(f"{module_id}: cajones con puertas configuradas requieren "
                          "validación de giro/colisión; usar otro módulo.")
    all_parts: list[dict[str, Any]] = []
    blockers: list[str] = []
    ids: list[str] = []
    openings: list[tuple[int, int]] = []
    for index, request in enumerate(drawers):
        if type(request) is not dict or set(request) != DRAWER_FIELDS:
            raise DesignError(f"{module_id}.drawers[{index}]: campos faltantes o desconocidos.")
        drawer_id = _id(request["drawer_id"], "drawer_id")
        if drawer_id in ids:
            raise DesignError(f"{module_id}: drawer_id repetido.")
        ids.append(drawer_id)
        material = _id(request["material_id"], "drawer.material_id")
        bottom_material = _id(request["bottom_material_id"], "drawer.bottom_material_id")
        offset = _mm(request["opening_bottom_offset_mm"], "opening_bottom_offset_mm", allow_zero=True)
        aperture_h = _mm(request["opening_height_mm"], "opening_height_mm")
        aperture_d = _mm(request["opening_depth_mm"], "opening_depth_mm")
        if offset + aperture_h > clear_height_mm or aperture_d > module_depth_mm:
            raise DesignError(f"{module_id}/{drawer_id}: abertura excede el cuerpo.")
        openings.append((offset, offset+aperture_h))
        spec = {
            "type": "drawer",
            "opening_width_mm": clear_width_mm,
            "opening_height_mm": aperture_h,
            "opening_depth_mm": aperture_d,
            **{k: request[k] for k in (
                "box_height_mm", "panel_thickness_mm", "bottom_thickness_mm",
                "slide_clearance_left_mm", "slide_clearance_right_mm",
                "front_setback_mm", "rear_setback_mm")},
        }
        result = design(spec)  # one authoritative F1 calculation
        dimensions = result["dimensions"]
        x = start_x_mm + carcase_thickness_mm + request["slide_clearance_left_mm"]
        y = carcase_thickness_mm + offset
        z = request["front_setback_mm"]
        box_w = dimensions["box_external_width_mm"]
        box_d = dimensions["box_external_depth_mm"]
        wall_h = dimensions["wall_height_mm"]
        t = request["panel_thickness_mm"]
        bt = request["bottom_thickness_mm"]
        if box_d <= t:
            raise DesignError(f"{module_id}/{drawer_id}: profundidad incompatible con paredes.")
        # Strictly guard interior volumes against a real back board if one exists.
        rear_z = min((p["nominal_origin_xyz_mm"][2] for p in back_parts), default=module_depth_mm)
        if z + box_d > rear_z:
            raise DesignError(
                f"{module_id}/{drawer_id}: la caja invade fondo posterior."
            )
        # Side walls are YZ; front and back walls XY; under-bottom XZ.
        specs = (
            ("drawer_side_left", material, box_d, wall_h, t,
             "YZ", [x, y+bt, z], result["parts"][0]["calculation"]),
            ("drawer_side_right", material, box_d, wall_h, t,
             "YZ", [x+box_w-t, y+bt, z], result["parts"][0]["calculation"]),
            ("drawer_front_wall", material, dimensions["box_inner_width_mm"], wall_h, t,
             "XY", [x+t, y+bt, z], result["parts"][1]["calculation"]),
            ("drawer_rear_wall", material, dimensions["box_inner_width_mm"], wall_h, t,
             "XY", [x+t, y+bt, z+box_d-t], result["parts"][1]["calculation"]),
            ("drawer_bottom", bottom_material, box_w, box_d, bt,
             "XZ", [x, y, z], result["parts"][2]["calculation"]),
        )
        for role, mat, fx, fy, thick, plane, origin, formula in specs:
            all_parts.append(_part(module_id, drawer_id, role, mat,
                                   fx, fy, thick, plane, origin, formula))
        fronts, front_blockers = _facade(
            request["facade"], module_id=module_id, drawer_id=drawer_id,
            aperture_width=clear_width_mm, aperture_height=aperture_h,
            opening_y=y, opening_x=start_x_mm + carcase_thickness_mm,
            front_setback=z,
        )
        all_parts.extend(fronts)
        blockers.extend(front_blockers)
        blockers.append(
            f"{module_id}/{drawer_id}: luces de corredera declaradas por usuario, "
            "SIN validar SKU, longitud, capacidad, fijación, cotas de taladros "
            "ni resistencia del fondo aplicado."
        )
        if front_setback := request["front_setback_mm"]:
            pass  # no implicit slide specification from this dimension
    sorted_openings = sorted(openings)
    if any(a[1] >= b[0] for a, b in zip(sorted_openings, sorted_openings[1:])):
        raise DesignError(f"{module_id}: aperturas verticales se solapan o tocan.")
    return all_parts, blockers, ids
