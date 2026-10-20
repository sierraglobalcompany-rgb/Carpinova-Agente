"""F7C Task 2: explicitly dimensioned door leaves, NOT hinge design.

Overlay fronts sit in front of the carcass at negative Z; inset fronts
occupy the clear aperture starting at Z=0. All clear dimensions originate
from F1/F6. No hinges, bores, swing arcs or structural validity inferred.
"""
from __future__ import annotations

import re
from typing import Any

from .core import DesignError

SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
GRAINS = {"face_x", "face_y", "none"}
EDGES = {"x_min", "x_max", "y_min", "y_max"}
BASE = {"style", "leaf_count", "material_id", "thickness_mm", "hinge_sides"}
OPTIONAL = {"grain_axis", "edgebanding_edges", "edgeband_thickness_mm"}
OVERLAY = {"left_reveal_mm", "right_reveal_mm", "top_reveal_mm", "bottom_reveal_mm"}
INSET = {"left_clearance_mm", "right_clearance_mm",
         "top_clearance_mm", "bottom_clearance_mm"}


def _int(value: Any, field: str, *, zero: bool = False) -> int:
    if type(value) is not int or value < 0 or (value == 0 and not zero):
        raise DesignError(f"{field}: milímetros enteros "
                          + ("no negativos." if zero else "positivos."))
    return value


def front_panels(fronts: Any, *, module_id: str, module_width_mm: int,
                 module_height_mm: int, clear_width_mm: int,
                 clear_height_mm: int, panel_thickness_mm: int,
                 start_x_mm: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Calculate zero, one, or two nominal front panels from user parameters."""
    if fronts in ("none", "pending"):
        return [], []
    if not isinstance(fronts, dict):
        raise DesignError(f"{module_id}.fronts: usar none, pending u objeto explícito.")
    style = fronts.get("style")
    if type(style) is not str or style not in ("overlay", "inset"):
        raise DesignError(f"{module_id}.fronts.style: overlay o inset.")
    required = BASE | (OVERLAY if style == "overlay" else INSET)
    count = _int(fronts.get("leaf_count"), "leaf_count")
    if count not in (1, 2):
        raise DesignError(f"{module_id}: por ahora se admiten 1 o 2 hojas.")
    if count == 2:
        required = required | {"center_gap_mm"}
    allowed = required | OPTIONAL
    if (set(fronts) - allowed) or (required - set(fronts)):
        raise DesignError(f"{module_id}.fronts: campos faltantes o inesperados.")
    material = fronts["material_id"]
    if type(material) is not str or not SAFE_ID.fullmatch(material):
        raise DesignError(f"{module_id}: material de frente inválido.")
    thickness = _int(fronts["thickness_mm"], "thickness_mm")
    hinge_sides = fronts["hinge_sides"]
    expected_hinges = ("left", "right") if count == 2 else None
    if (type(hinge_sides) is not list or len(hinge_sides) != count
            or any(type(h) is not str or h not in ("left", "right")
                   for h in hinge_sides)
            or (count == 2 and tuple(hinge_sides) != expected_hinges)):
        raise DesignError(
            f"{module_id}: declarar sentido de giro: [left] o [right] para "
            "una hoja; [left,right] para dos."
        )
    grain = fronts.get("grain_axis", "UNCONFIRMED")
    if type(grain) is not str or (grain != "UNCONFIRMED" and grain not in GRAINS):
        raise DesignError(f"{module_id}: orientación de veta inválida.")
    edges = fronts.get("edgebanding_edges", "UNCONFIRMED")
    if edges != "UNCONFIRMED":
        if type(edges) is not list or len(edges) != len(set(
                e for e in edges if type(e) is str)) or any(
                type(e) is not str or e not in EDGES for e in edges):
            raise DesignError(f"{module_id}: bordes de canto inválidos.")
    band_thickness = fronts.get("edgeband_thickness_mm")
    if edges == "UNCONFIRMED":
        if band_thickness is not None:
            raise DesignError("No indicar espesor de canto sin bordes confirmados.")
    elif edges:
        _int(band_thickness, "edgeband_thickness_mm")
    elif band_thickness is not None:
        raise DesignError("No indicar espesor de canto sin cantos solicitados.")

    if style == "overlay":
        left = _int(fronts["left_reveal_mm"], "left_reveal_mm", zero=True)
        right = _int(fronts["right_reveal_mm"], "right_reveal_mm", zero=True)
        top = _int(fronts["top_reveal_mm"], "top_reveal_mm", zero=True)
        bottom = _int(fronts["bottom_reveal_mm"], "bottom_reveal_mm", zero=True)
        if any(value >= panel_thickness_mm for value in (left, right, top, bottom)):
            raise DesignError(
                f"{module_id}: overlay exige solape real de los paneles "
                "(reveal_mm menor al espesor estructural)."
            )
        total_width = module_width_mm
        total_height = module_height_mm
        x_start = start_x_mm
        y_start = 0
        z_start = -thickness
        basis = "external_dimensions minus explicit edge reveals"
    else:
        left = _int(fronts["left_clearance_mm"], "left_clearance_mm")
        right = _int(fronts["right_clearance_mm"], "right_clearance_mm")
        top = _int(fronts["top_clearance_mm"], "top_clearance_mm")
        bottom = _int(fronts["bottom_clearance_mm"], "bottom_clearance_mm")
        total_width = clear_width_mm
        total_height = clear_height_mm
        x_start = start_x_mm + panel_thickness_mm
        y_start = panel_thickness_mm
        z_start = 0
        basis = "F1 clear_aperture minus explicit edge clearances"
    panel_width = total_width - left - right
    panel_height = total_height - bottom - top
    gap = _int(fronts["center_gap_mm"], "center_gap_mm") if count == 2 else 0
    available = panel_width - gap
    if panel_height <= 0 or available <= 0:
        raise DesignError(f"{module_id}: no existe espacio útil para las hojas.")
    if count == 2 and available % 2:
        raise DesignError(
            f"{module_id}: dos puertas iguales requieren ancho par después "
            "de descontar la separación central."
        )
    each_width = available // count
    if each_width <= 0:
        raise DesignError(f"{module_id}: ancho de hoja imposible.")
    x_start += left
    y_start += bottom
    # Edges run along their *orthogonal* face dimension.
    band_length = None if edges == "UNCONFIRMED" else sum(
        panel_height if e.startswith("x_") else each_width for e in edges
    )
    panels = []
    for i in range(count):
        role = ("front_single" if count == 1 else
                ("front_left" if i == 0 else "front_right"))
        px = x_start + i * (each_width + gap)
        panels.append({
            "piece_id": f"{module_id}-{role.upper()}",
            "module_id": module_id, "role": role,
            "material_id": material, "nominal_face_x_mm": each_width,
            "nominal_face_y_mm": panel_height, "thickness_mm": thickness,
            "face_plane": "XY", "nominal_origin_xyz_mm": [px, y_start, z_start],
            "grain_axis": grain, "edgebanding_edges": (
                "UNCONFIRMED" if edges == "UNCONFIRMED" else sorted(edges)),
            "edgebanding_thickness_mm": band_thickness,
            "edgebanding_nominal_total_mm": band_length,
            "finished_cut_dimensions_mm": None,
            "source_engine": "F7C_EXPLICIT_FRONT",
            "source_formula": basis + (
                "; width=(available-center_gap_mm)/2" if count == 2 else ""
            ),
            "hinge_side_requested": hinge_sides[i],
        })
    blockers = [
        f"{module_id}: la hoja {style} no tiene bisagra SKU/placa, "
        "cazoleta, holgura dinámica ni patrón de perforaciones verificados.",
        f"{module_id}: giro, tiradores, choque con paredes y módulos "
        "adyacentes sin validar físicamente.",
        f"{module_id}: canto/adhesivo y espesor final de puertas por validar.",
    ]
    if grain == "UNCONFIRMED":
        blockers.append(f"{module_id}: veta de los frentes aún sin definir.")
    if edges == "UNCONFIRMED":
        blockers.append(f"{module_id}: cantos de los frentes aún sin definir.")
    return panels, blockers


def check_adjacent_fronts(modules: list[dict[str, Any]],
                          parts: list[dict[str, Any]]) -> None:
    """Detect overlap or touching of nominal front envelopes across modules."""
    fronts = [p for p in parts if p["role"].startswith("front_")]
    for left, right in zip(modules, modules[1:]):
        group_l = [p for p in fronts if p["module_id"] == left["module_id"]]
        group_r = [p for p in fronts if p["module_id"] == right["module_id"]]
        if not group_l or not group_r:
            continue
        end_left = max(p["nominal_origin_xyz_mm"][0] +
                       p["nominal_face_x_mm"] for p in group_l)
        start_right = min(p["nominal_origin_xyz_mm"][0] for p in group_r)
        if end_left >= start_right:
            raise DesignError(
                f"{left['module_id']}/{right['module_id']}: frentes "
                "adyacentes se solapan o tocan; definir luces laterales."
            )
