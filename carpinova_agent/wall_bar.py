"""Wall-to-cabinet auxiliary bar: place validated F1/F7C parts only.

The left wall is NOT a wooden panel. Feet and anchors are concepts, not CAD parts.
All output is nominal review geometry, never a cut/drill/fabrication release.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .core import DesignError
from .modular import design_modular_run


def _positive(spec: Mapping[str, Any], name: str) -> int:
    n = spec.get(name)
    if type(n) is not int or n <= 0:
        raise DesignError(f"wall_bar.{name}: positivo entero en mm requerido.")
    return n


def design_wall_bar(spec: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"type", "overall_width_mm", "overall_height_mm",
              "overall_depth_mm", "free_span_mm", "feet_height_mm",
              "top_thickness_mm", "wall_side", "drawer_opening_face",
              "cabinet_module"}
    if type(spec) is not dict or set(spec) != fields or spec["type"] != "wall_bar":
        raise DesignError("wall_bar: contrato exacto requerido.")
    w = _positive(spec, "overall_width_mm")
    h = _positive(spec, "overall_height_mm")
    d = _positive(spec, "overall_depth_mm")
    free = _positive(spec, "free_span_mm")
    feet = _positive(spec, "feet_height_mm")
    top = _positive(spec, "top_thickness_mm")
    if spec["wall_side"] != "left":
        raise DesignError("Solo se modela la variante aprobada: muro a la izquierda.")
    if spec["drawer_opening_face"] != "long_side_front":
        raise DesignError("Orientación A confirmada: cajones al costado largo; no hacia la punta.")
    if w <= free or h <= feet + top or d <= top:
        raise DesignError("Dimensiones del conjunto incompatibles.")
    cabinet_w, cabinet_h, cabinet_d = w - free, h - feet - top, d - top
    module = spec["cabinet_module"]
    if type(module) is not dict or module.get("width_mm") != cabinet_w:
        raise DesignError("La cajonera debe ocupar exclusivamente el extremo derecho.")
    if module.get("panel_thickness_mm") != top:
        raise DesignError("Espesor cuerpo/cubierta debe ser el mismo y explícito.")
    if module.get("fronts") != "none" or module.get("support") != "floor":
        raise DesignError("No agregar puerta independiente ni apoyo mural a cajonera.")
    if module.get("support_concept") != {
        "style": "legs", "support_height_mm": feet,
        "overall_height_mm": feet + cabinet_h
    }:
        raise DesignError("Altura de soporte incompatible.")
    drawers = module.get("drawers")
    if type(drawers) is not list or len(drawers) != 3:
        raise DesignError("Se requieren tres cajones.")
    for drawer in drawers:
        if (type(drawer) is not dict
                or drawer.get("front_construction") != "integrated_overlay"
                or not isinstance(drawer.get("facade"), dict)
                or drawer["facade"].get("style") != "overlay"
                or drawer.get("front_setback_mm") != 0):
            raise DesignError("Frente exterior único requerido para cada cajón.")
    inner = {
        "type": "modular_run", "application": "kitchen",
        "width_mm": cabinet_w, "height_mm": cabinet_h,
        "depth_mm": cabinet_d, "max_assembled_depth_mm": d,
        "installation": "freestanding", "modules": [deepcopy(module)]
    }
    source = design_modular_run(inner)
    if source["status"] != "DRAFT_NOT_FOR_CUTTING":
        raise DesignError("F1/F7C no aprobó geometría nominal del módulo.")
    if source["depth_review"]["assembled_external_depth_mm"] != d:
        raise DesignError("Profundidad terminada exterior no coincide.")
    source_ids = [p["piece_id"] for p in source["parts"]]
    if len(source_ids) != len(set(source_ids)):
        raise DesignError("IDs duplicados.")
    if (sum(p["role"] == "drawer_facade" for p in source["parts"]) != 3
            or any(p["role"] == "drawer_front_wall" for p in source["parts"])):
        raise DesignError("Cajones no representan el frente externo único.")
    result = deepcopy(source)
    # Translate F1/F7C panels into one common coordinate system, no redraw.
    # Original overlay z=-top; after shifting it occupies z=0..top.
    for part in result["parts"]:
        x, y, z = part["nominal_origin_xyz_mm"]
        part["nominal_origin_xyz_mm"] = [x + free, y + feet, z + top]
    # A: facades lie along the 900 mm long edge (XY plane at Z=0),
    # and drawers open outwards towards negative Z, never from the short tip.
    faces = [p for p in result["parts"] if p["role"] == "drawer_facade"]
    if (len(faces) != 3 or any(p["face_plane"] != "XY"
            or p["nominal_origin_xyz_mm"][2] != 0
            or p["nominal_origin_xyz_mm"][0] < free
            or p["nominal_origin_xyz_mm"][0] + p["nominal_face_x_mm"] > w
            for p in faces)):
        raise DesignError("Frentes de cajón no coinciden con apertura A sobre el costado largo.")
    if any(p["piece_id"] == "BAR-COVER-TOP" for p in result["parts"]):
        raise DesignError("Cubierta duplicada.")
    result["parts"].append({
        "piece_id": "BAR-COVER-TOP", "module_id": "BAR", "role": "top",
        "material_id": module["material_id"], "nominal_face_x_mm": w,
        "nominal_face_y_mm": d, "thickness_mm": top,
        "grain_axis": "UNCONFIRMED", "face_plane": "XZ",
        "nominal_origin_xyz_mm": [0, h-top, 0],
        "edgebanding_edges": "UNCONFIRMED",
        "edgebanding_thickness_mm": None,
        "edgebanding_nominal_total_mm": None,
        "finished_cut_dimensions_mm": None,
        "source_engine": "WALL_BAR_PLACEMENT_F1_F7C",
        "source_formula": "cover=(overall_width, overall_depth); y=height-top"
    })
    result["dimensions_mm"] = {"width": w, "height": h, "depth": d}
    result["modules"][0]["start_x_mm"] = free
    result["modules"][0]["start_y_mm"] = feet
    result["piece_count"] = len(result["parts"])
    # Existing CAD and BOM consumers accept the same modular_run model.
    result["type"] = "modular_run"
    result["wall_bar_review"] = {
        "wall_side": "left", "wall_attachment": "NOT_VERIFIED",
        "drawer_opening_face": "long_side_front",
        "drawer_open_direction": "negative_Z",
        "drawer_front_plane": "XY",
        "left_vertical_wood_panels": 0, "free_span_mm": free,
        "cabinet_x_range_mm": [free, w],
        "cabinet_y_range_mm": [feet, h-top],
        "feet_height_mm": feet, "physical_feet_parts": None,
        "top_y_range_mm": [h-top, h]
    }
    result["blockers"].extend([
        "Tipo de muro, unión al muro, cargas y flecha de cubierta NO VERIFICADOS.",
        "Patas: SKU, cantidad, capacidad, distribución y fijaciones SIN VALIDAR.",
        "Frente exterior único: fijación estructural a costados/base SIN VALIDAR.",
        "Tapacanto rígido en frentes y flexible en restantes: dimensiones de corte pendientes.",
        "Prohibido inventar lateral izquierdo, faldón, escuadra o soporte físico.",
        "A confirmada: tres cajones abren hacia costado largo (Z negativo)."
    ])
    for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
        result[flag] = False
    return result
