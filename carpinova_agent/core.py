"""Deterministic *preliminary* furniture geometry, not fabrication authority.

All inputs are integer millimeters.  No dimensions come from the book's
normalized diagrams or from an unverified hardware catalogue.
"""
from __future__ import annotations

from typing import Any, Mapping


class DesignError(ValueError):
    """Input is incomplete, unsupported, or geometrically impossible."""


def _shape(data: Any, required: set[str]) -> Mapping[str, Any]:
    if not isinstance(data, dict):
        raise DesignError("La especificación debe ser un objeto JSON.")
    missing = required - data.keys()
    unknown = data.keys() - required
    if missing:
        raise DesignError("Faltan datos: " + ", ".join(sorted(missing)))
    if unknown:
        raise DesignError("Campos desconocidos: " + ", ".join(sorted(unknown)))
    return data


def _mm(data: Mapping[str, Any], key: str, *, allow_zero: bool = False) -> int:
    value = data[key]
    if type(value) is not int or value < 0 or (value == 0 and not allow_zero):
        raise DesignError(f"{key} debe ser un entero en milímetros "
                          + ("no negativo." if allow_zero else "positivo."))
    return value


def _piece(
    code: str,
    label: str,
    qty: int,
    x: int,
    y: int,
    t: int,
    formula: str,
    x_axis: str,
    y_axis: str,
) -> dict[str, Any]:
    if min(x, y, t, qty) <= 0:
        raise DesignError(f"Dimensión imposible en {code}.")
    return {
        "code": code,
        "name": label,
        "quantity": qty,
        "face_x_mm": x,
        "face_y_mm": y,
        "thickness_mm": t,
        "face_x_direction": x_axis,
        "face_y_direction": y_axis,
        "grain": "UNCONFIRMED",
        "edgebanding": "UNCONFIRMED",
        "source_type": "CALCULATED_FROM_USER_DIMENSIONS",
        "calculation": formula,
    }


def _result(
    kind: str,
    dimensions: dict[str, int],
    parts: list[dict[str, Any]],
    checks: list[str],
    blockers: list[str],
    assumptions: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "design_type": kind,
        "units": "mm",
        "status": "DRAFT_NOT_FOR_CUTTING",
        "dimensions": dimensions,
        "parts": parts,
        "checks_passed": checks,
        "release_blockers": blockers,
        "assumptions": assumptions,
        "safety_note": (
            "Despiece geométrico preliminar. No cortar, taladrar ni instalar "
            "sin verificar espesores reales, cantos, herrajes, cargas, "
            "uniones y mediciones en sitio."
        ),
    }


def design_cabinet(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Rectangular open carcass, no doors, back, plinth or hardware."""
    s = _shape(spec, {
        "type", "width_mm", "height_mm", "depth_mm",
        "panel_thickness_mm", "construction",
    })
    if s["type"] != "cabinet":
        raise DesignError("type debe ser cabinet.")
    if s["construction"] not in ("sides_full", "top_bottom_full"):
        raise DesignError("construction: sides_full o top_bottom_full.")
    width = _mm(s, "width_mm")
    height = _mm(s, "height_mm")
    depth = _mm(s, "depth_mm")
    t = _mm(s, "panel_thickness_mm")
    if width <= 2 * t or height <= 2 * t:
        raise DesignError("El ancho y alto deben superar dos espesores de tablero.")
    inner_w, inner_h = width - 2 * t, height - 2 * t
    if s["construction"] == "sides_full":
        side_h, cap_w = height, inner_w
        side_formula = "height_mm"
        cap_formula = "width_mm - 2 * panel_thickness_mm"
    else:
        side_h, cap_w = inner_h, width
        side_formula = "height_mm - 2 * panel_thickness_mm"
        cap_formula = "width_mm"
    parts = [
        _piece("SIDE", "Laterales", 2, depth, side_h, t,
               side_formula, "profundidad", "altura"),
        _piece("TOP_BOTTOM", "Tapa y base", 2, cap_w, depth, t,
               cap_formula, "ancho", "profundidad"),
    ]
    return _result(
        "open_cabinet",
        {"external_width_mm": width, "external_height_mm": height,
         "external_depth_mm": depth, "clear_width_mm": inner_w,
         "clear_height_mm": inner_h},
        parts,
        ["ancho exterior/interior coherentes: ancho_libre = ancho - 2*espesor",
         "alto exterior/interior coherentes: alto_libre = alto - 2*espesor",
         "las cuatro piezas tienen dimensiones positivas"],
        ["Definir vetas y cantos; las medidas aún no compensan adhesivo/canto.",
         "Especificar fondo, puertas/frentes, uniones, tornillos y perforaciones.",
         "Validar estabilidad, cargas, anclajes y medidas reales del lugar."],
        ["Módulo abierto de 4 paneles; sin fondo, patas, zócalo ni puerta.",
         "Las dimensiones son geométricas nominales, sin acabado ni tolerancias.",
         "No se presume que el libro avale las dimensiones calculadas."],
    )


def design_drawer(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Surface-bottom box; front/back BETWEEN sides, no decorative front."""
    s = _shape(spec, {
        "type", "opening_width_mm", "opening_height_mm", "opening_depth_mm",
        "box_height_mm", "panel_thickness_mm", "bottom_thickness_mm",
        "slide_clearance_left_mm", "slide_clearance_right_mm",
        "front_setback_mm", "rear_setback_mm",
    })
    if s["type"] != "drawer":
        raise DesignError("type debe ser drawer.")
    w = _mm(s, "opening_width_mm")
    h = _mm(s, "opening_height_mm")
    d = _mm(s, "opening_depth_mm")
    box_h = _mm(s, "box_height_mm")
    t = _mm(s, "panel_thickness_mm")
    bottom_t = _mm(s, "bottom_thickness_mm")
    left = _mm(s, "slide_clearance_left_mm", allow_zero=True)
    right = _mm(s, "slide_clearance_right_mm", allow_zero=True)
    front = _mm(s, "front_setback_mm", allow_zero=True)
    rear = _mm(s, "rear_setback_mm", allow_zero=True)
    box_w = w - left - right
    box_d = d - front - rear
    wall_h = box_h - bottom_t
    inner_w = box_w - 2 * t
    if min(box_w, box_d, wall_h, inner_w) <= 0 or box_h > h:
        raise DesignError("El cajón no cabe: revisar luces, espesor, altura y profundidad.")
    parts = [
        _piece("DRAWER_SIDE", "Costados", 2, box_d, wall_h, t,
               "opening_depth_mm - front_setback_mm - rear_setback_mm",
               "profundidad", "altura"),
        _piece("DRAWER_FRONT_BACK", "Frente estructural y trasera", 2,
               inner_w, wall_h, t,
               "opening_width_mm - clearances_left_right - 2*panel_thickness_mm",
               "ancho", "altura"),
        _piece("DRAWER_BOTTOM", "Fondo aplicado inferior", 1,
               box_w, box_d, bottom_t,
               "ancho_caja x profundidad_caja", "ancho", "profundidad"),
    ]
    return _result(
        "drawer_box_surface_bottom",
        {"opening_width_mm": w, "opening_height_mm": h,
         "opening_depth_mm": d, "box_external_width_mm": box_w,
         "box_external_height_mm": box_h, "box_external_depth_mm": box_d,
         "box_inner_width_mm": inner_w, "wall_height_mm": wall_h},
        parts,
        ["ancho caja + holguras laterales = luz del hueco",
         "profundidad caja + retranqueos = luz de profundidad",
         "alto pared + espesor fondo = alto exterior de caja",
         "frente/trasera entre laterales cierra ancho exterior"],
        ["Las holguras ingresadas NO están validadas contra una corredera real.",
         "Elegir fabricante, referencia exacta, carga, longitud y ficha de montaje.",
         "Definir frente decorativo (aplicado/embutido), luces y tirador.",
         "Definir uniones, tornillos, taladros, vetas y cantos.",
         "Comprobar resistencia y montaje del fondo aplicado."],
        ["Frente/trasera estructurales entre costados; fondo por debajo de paredes.",
         "No hay ranuras, herrajes, frente decorativo ni tolerancias de mecanizado.",
         "Valores de holgura provienen exclusivamente del usuario, no del fabricante."],
    )


def design(spec: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise DesignError("Entrada JSON debe ser un objeto.")
    if spec.get("type") == "cabinet":
        return design_cabinet(spec)
    if spec.get("type") == "drawer":
        return design_drawer(spec)
    raise DesignError("Tipo no admitido: use cabinet o drawer.")
