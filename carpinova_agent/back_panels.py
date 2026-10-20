"""F7C: explicitly dimensioned INSET backs and service-access strips.

Back boards are attached to neither a confirmed groove nor a confirmed
fastener system. Geometry is for review only. No holes/pipe penetrations,
overlays, French cleats or structural capacity are inferred.
"""
from __future__ import annotations

import re
from typing import Any

from .core import DesignError

ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
COMMON = frozenset({"style", "material_id", "thickness_mm",
                    "services_present", "grain_axis"})
STRIPS = frozenset({"top_strip_height_mm", "bottom_strip_height_mm"})
STYLES = frozenset({"inset_full", "inset_two_strips"})
GRAINS = frozenset({"face_x", "face_y", "none"})


def _mm(value: Any, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise DesignError(f"{field}: se requiere entero positivo en mm.")
    return value


def _panel(module_id: str, role: str, material: str,
           width: int, height: int, thickness: int,
           origin: list[int], grain: str, formula: str) -> dict[str, Any]:
    return {
        "piece_id": f"{module_id}-{role.upper()}",
        "module_id": module_id, "role": role, "material_id": material,
        "nominal_face_x_mm": width, "nominal_face_y_mm": height,
        "thickness_mm": thickness, "face_plane": "XY",
        "nominal_origin_xyz_mm": origin, "grain_axis": grain,
        "edgebanding_edges": "UNCONFIRMED",
        "edgebanding_thickness_mm": None,
        "edgebanding_nominal_total_mm": None,
        "finished_cut_dimensions_mm": None,
        "source_engine": "F7C_EXPLICIT_INSET_BACK",
        "source_formula": formula,
    }


def back_panels(back: Any, *, module_id: str, module_width_mm: int,
                module_height_mm: int, module_depth_mm: int,
                carcase_thickness_mm: int, start_x_mm: int
                ) -> tuple[list[dict[str, Any]], list[str]]:
    """Geometry of user-selected inset back(s), inside the F1 clear aperture."""
    if back in ("none", "pending"):
        return [], []
    if not isinstance(back, dict):
        raise DesignError(f"{module_id}.back: se espera none, pending u objeto.")
    style = back.get("style")
    if style not in STYLES:
        raise DesignError(f"{module_id}.back.style: usar inset_full o inset_two_strips.")
    expected = COMMON | (STRIPS if style == "inset_two_strips" else frozenset())
    unknown = set(back) - expected
    missing = (COMMON - {"grain_axis"}) - set(back)
    if missing or unknown:
        raise DesignError(
            f"{module_id}.back: faltan {sorted(missing)}, desconocidos {sorted(unknown)}."
        )
    material = back["material_id"]
    if not isinstance(material, str) or not ID.fullmatch(material):
        raise DesignError(f"{module_id}.back.material_id inválido.")
    thickness = _mm(back["thickness_mm"], "back.thickness_mm")
    if thickness >= module_depth_mm:
        raise DesignError(f"{module_id}: fondo demasiado grueso para la profundidad.")
    if type(back["services_present"]) is not bool:
        raise DesignError(f"{module_id}.back.services_present debe ser booleano.")
    services = back["services_present"]
    if style == "inset_full" and services:
        raise DesignError(
            f"{module_id}: fondo completo obstruiría instalaciones declaradas; "
            "elegir fondo parcial o sin fondo."
        )
    grain = back.get("grain_axis", "UNCONFIRMED")
    if grain != "UNCONFIRMED" and grain not in GRAINS:
        raise DesignError(f"{module_id}.back.grain_axis no reconocido.")
    inner_width = module_width_mm - 2 * carcase_thickness_mm
    inner_height = module_height_mm - 2 * carcase_thickness_mm
    if min(inner_width, inner_height) <= 0:
        raise DesignError(f"{module_id}: no hay abertura libre para el fondo.")
    x = start_x_mm + carcase_thickness_mm
    z = module_depth_mm - thickness
    origin_y = carcase_thickness_mm
    blockers = [
        f"{module_id}: montaje de fondo embutido sin ranura, fijaciones, "
        "compensación de holguras ni rigidez ensayadas.",
        f"{module_id}: cantos y acabado del fondo sin confirmar.",
    ]
    if grain == "UNCONFIRMED":
        blockers.append(f"{module_id}: orientar veta del fondo.")
    if style == "inset_full":
        panels = [_panel(
            module_id, "back_full", material, inner_width, inner_height,
            thickness, [x, origin_y, z], grain,
            "module.width_mm - 2*module.panel_thickness_mm; "
            "run.height_mm - 2*module.panel_thickness_mm",
        )]
    else:
        if set(back) - expected or not STRIPS.issubset(back):
            raise DesignError(
                f"{module_id}: especificar alturas superior e inferior del fondo parcial."
            )
        top = _mm(back["top_strip_height_mm"], "back.top_strip_height_mm")
        bottom = _mm(back["bottom_strip_height_mm"], "back.bottom_strip_height_mm")
        if top + bottom >= inner_height:
            raise DesignError(
                f"{module_id}: las dos tiras eliminan el acceso posterior."
            )
        gap = inner_height - top - bottom
        panels = [
            _panel(
                module_id, "back_bottom", material, inner_width, bottom,
                thickness, [x, origin_y, z], grain,
                "back.bottom_strip_height_mm (dato explícito de usuario)"
            ),
            _panel(
                module_id, "back_top", material, inner_width, top,
                thickness, [x, origin_y + bottom + gap, z], grain,
                "back.top_strip_height_mm (dato explícito de usuario)"
            ),
        ]
        blockers.append(
            f"{module_id}: abertura posterior libre de {gap} mm de alto; "
            "cotejar tuberías y acceso reales antes de elegir esta distribución."
        )
        if not services:
            blockers.append(
                f"{module_id}: fondo dividido solicitado sin instalaciones; "
                "confirmar intención del usuario."
            )
    return panels, blockers
