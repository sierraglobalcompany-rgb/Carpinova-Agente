"""Private, absolute module revisions routed back through Maestro and F6."""
from __future__ import annotations

import copy
import re
from typing import Any

from .drawer_modules import propose_drawer_layout

_FIELDS = frozenset({
    "group_id", "module_id", "width_mm", "overall_height_mm",
    "carcass_depth_mm", "support_style", "support_height_mm",
})
_STYLES = frozenset({"floor_direct", "legs", "plinth", "wall_mounted"})
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
_LIMIT = 20000


def validate_revision_list(value: Any) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) > 12:
        raise ValueError("module_edit_revisions debe ser una lista de 0 a 12 revisiones")
    result = []
    seen = set()
    for item in value:
        if type(item) is not dict or set(item) != _FIELDS:
            raise ValueError("module_edit_revisions requiere exactamente siete campos")
        for key in ("group_id", "module_id"):
            if type(item[key]) is not str or not _ID.fullmatch(item[key]):
                raise ValueError(f"module_edit_revisions.{key} inválido")
        key = (item["group_id"], item["module_id"])
        if key in seen:
            raise ValueError("module_edit_revisions no admite módulos duplicados")
        seen.add(key)
        if item["support_style"] not in _STYLES:
            raise ValueError("support_style no admitido")
        for field in ("width_mm", "overall_height_mm", "carcass_depth_mm"):
            if type(item[field]) is not int or not 1 <= item[field] <= _LIMIT:
                raise ValueError(f"{field} debe ser un entero positivo hasta 20000 mm")
        support_height = item["support_height_mm"]
        if type(support_height) is not int or not 0 <= support_height <= _LIMIT:
            raise ValueError("support_height_mm debe ser un entero entre 0 y 20000 mm")
        if item["overall_height_mm"] <= support_height:
            raise ValueError("overall_height_mm debe superar support_height_mm")
        if item["support_style"] in {"legs", "plinth"}:
            if support_height == 0:
                raise ValueError("Patas y zócalo requieren una reserva positiva")
        elif support_height != 0:
            raise ValueError("Piso directo y suspendido requieren apoyo de 0 mm")
        result.append(dict(item))
    return result


def _drawer_signature(module: dict[str, Any]) -> list[tuple[Any, ...]]:
    drawers = module.get("drawers")
    if type(drawers) is not list:
        return []
    return [(item.get("drawer_id"), item.get("opening_bottom_offset_mm"),
             item.get("opening_height_mm")) for item in drawers
            if type(item) is dict]


def apply_group_revisions(
    source_spec: dict[str, Any], revisions: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Apply absolute user dimensions to a copied modular-run specification.

    F1 remains responsible for panels and drawer geometry. The returned map is
    a support reservation from the source floor origin, not a physical panel.
    """
    spec = copy.deepcopy(source_spec)
    if type(spec) is not dict or spec.get("type") != "modular_run":
        raise ValueError("La edición M6 solo admite especificaciones modular_run verificadas")
    modules = spec.get("modules")
    if type(modules) is not list or not modules:
        raise ValueError("La especificación no contiene módulos F6")
    by_id = {item.get("module_id"): item for item in modules if type(item) is dict}
    if len(by_id) != len(modules):
        raise ValueError("La especificación tiene identidades de módulo duplicadas")
    edits = [item for item in revisions if item["module_id"] in by_id]
    if len(edits) != len(revisions):
        raise ValueError("La revisión no pertenece al grupo o módulo indicado")
    offsets: dict[str, int] = {}
    edited_modules = set()
    for edit in edits:
        module = by_id[edit["module_id"]]
        if module.get("upper_support") is not None or module.get("countertop") is not None \
                or module.get("corner_blind") is not None \
                or module.get("vertical_divider") is not None \
                or module.get("built_in") is not None:
            raise ValueError(f"{edit['module_id']}: soporte/café, esquinero, divisor vertical o empotrado fuera de alcance")
        old_style = (module.get("support_concept") or {}).get(
            "style", "wall_mounted" if module.get("support") == "wall" else "floor_direct")
        old_support_concept = module.get("support_concept")
        new_wall = edit["support_style"] == "wall_mounted"
        old_wall = old_style == "wall_mounted" or module.get("support") == "wall"
        if new_wall != old_wall:
            raise ValueError("Cambio piso↔suspendido fuera de alcance dimensional")
        changed_nonwidth = (
            edit["overall_height_mm"] != spec.get("height_mm")
            or edit["carcass_depth_mm"] != spec.get("depth_mm")
            or edit["support_style"] != old_style
            or edit["support_height_mm"] != (module.get("support_concept") or {}).get(
                "support_height_mm", 0)
        )
        if len(modules) > 1 and changed_nonwidth:
            raise ValueError("Alto, fondo y apoyo individual de una fila compartida requieren independización H10")
        if (changed_nonwidth and type(old_support_concept) is dict
                and old_support_concept.get("support_height_mm", 0) > 0):
            raise ValueError("Origen con apoyo previo ambiguo; no se puede desplazar sin acumular Y")
        if len(modules) > 1 and any(module.get(field) is not None for field in (
                "countertop", "upper_support", "corner_blind", "vertical_divider")):
            raise ValueError("Fila compartida con geometría especial: edición dimensional bloqueada")
        if changed_nonwidth and (spec.get("installation") == "built_in"
                                 or spec.get("application") == "closet"):
            raise ValueError("Módulo empotrado: requiere medidas de sitio y revisión independiente")
        if changed_nonwidth and (module.get("wall_rear_ties") is not None
                                 or module.get("upper_support") is not None):
            raise ValueError("Módulo con amarres/soporte superior: edición dimensional bloqueada")

        old_height = spec.get("height_mm")
        old_depth = spec.get("depth_mm")
        if type(old_height) is not int or type(old_depth) is not int:
            raise ValueError("Dimensiones de origen incompletas")
        carcass_height = edit["overall_height_mm"] - edit["support_height_mm"]
        if carcass_height <= 0:
            raise ValueError("La reserva de apoyo deja altura de carcasa inválida")
        old_drawers = _drawer_signature(module)
        if "drawer_layout_reference" in module:
            reference = module["drawer_layout_reference"]
            if type(reference) is not dict:
                raise ValueError("drawer_layout_reference inválida")
            before = propose_drawer_layout(copy.deepcopy(reference))
            if (before["external_dimensions_mm"] != {
                    "width": module["width_mm"], "height": old_height,
                    "depth": old_depth} or
                    [(row["drawer_id"], row["opening_bottom_offset_mm"],
                      row["opening_height_mm"]) for row in before["opening_plan"]]
                    != old_drawers):
                raise ValueError("La referencia F1 no coincide con los cajones existentes")
            if edit["width_mm"] != module["width_mm"]:
                reference["width_mm"] = edit["width_mm"]
                after = propose_drawer_layout(copy.deepcopy(reference))
                if [(row["drawer_id"], row["opening_bottom_offset_mm"],
                     row["opening_height_mm"]) for row in after["opening_plan"]] != old_drawers:
                    raise ValueError("El cambio de ancho altera identidad o distribución vertical de cajones")
        elif old_drawers and edit["width_mm"] != module.get("width_mm"):
            raise ValueError("Cajones sin referencia F1 compatible; no se redimensionan")

        divider = module.get("horizontal_divider")
        if type(divider) is dict and old_depth != edit["carcass_depth_mm"]:
            back = module.get("back")
            old_useful = old_depth - (back["thickness_mm"] if type(back) is dict
                                      and back.get("style") == "inset_full" else 0)
            new_useful = edit["carcass_depth_mm"] - (back["thickness_mm"] if type(back) is dict
                                                      and back.get("style") == "inset_full" else 0)
            offset, depth = divider.get("depth_from_front_mm"), divider.get("depth_mm")
            if type(offset) is not int or type(depth) is not int:
                raise ValueError("Geometría de repisa incompleta")
            if offset + depth == old_useful:
                divider["depth_mm"] = new_useful - offset
            elif offset + depth > new_useful:
                raise ValueError("El nuevo fondo intersecta la repisa; se requiere una cota explícita")

        module["width_mm"] = edit["width_mm"]
        if len(modules) == 1 or old_support_concept is not None or changed_nonwidth:
            module["support"] = "wall" if new_wall else "floor"
            module["support_concept"] = {
                "style": edit["support_style"],
                "support_height_mm": edit["support_height_mm"],
                "overall_height_mm": edit["overall_height_mm"],
            }
            spec["installation"] = (
                "wall_mounted" if edit["support_style"] == "wall_mounted"
                else "freestanding"
            )
        spec["height_mm"] = carcass_height
        spec["depth_mm"] = edit["carcass_depth_mm"]
        edited_modules.add(edit["module_id"])
        offsets[edit["module_id"]] = (
            edit["support_height_mm"] if changed_nonwidth else 0
        )

    if edited_modules:
        spec["width_mm"] = sum(module["width_mm"] for module in modules)
        if len(modules) == 1 and "site_width_mm" in spec:
            if spec["site_width_mm"] != spec["width_mm"]:
                raise ValueError("Ancho revisado no coincide con el sitio declarado")
    return spec, offsets
