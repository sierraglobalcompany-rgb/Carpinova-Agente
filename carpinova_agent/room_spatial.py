"""D5: nominal 3-D room composition reusing existing CADExchange boxes.

This module does NOT design cabinet boards, cutouts, joints or hardware.  Its
input exchanges must be produced and validated by local Maestro/CADExchange;
see review_room_from_specs() for that trust boundary.  All coordinates are mm.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
LIMIT = 20000
MAX_GROUPS = 6
MAX_ZONES = 12
MAX_BACK_REVISIONS = 12
PHYSICAL_FLAGS = {
    "fabrication_ready": False,
    "cutting_ready": False,
    "drilling_ready": False,
    "purchase_ready": False,
    "can_generate_f7c": False,
}
ROTATIONS = (0, 90, 180, 270)
PURPOSES = ("plumbing", "electric", "appliance", "access")


def _error(message: str) -> None:
    raise ValueError(message)


def _vec3(value: Any, path: str, *, positive: bool = False) -> list[int]:
    if (type(value) is not list or len(value) != 3 or any(
        type(x) is not int or (x <= 0 if positive else x < 0) or x > LIMIT
        for x in value
    )):
        _error(f"{path}: requiere tres enteros mm " + ("positivos" if positive else "no negativos"))
    return list(value)


def _id(value: Any, path: str) -> str:
    if type(value) is not str or not ID.fullmatch(value):
        _error(f"{path}: ID inválido")
    return value


def _construction_review(model: dict[str, Any]) -> dict[str, Any]:
    """Summarize declared back/support choices without certifying installation."""
    modules = model.get("modules")
    if type(modules) is not list or not modules:
        _error("Maestro no devolvió módulos para revisar fondo y soporte")

    back_states: list[str] = []
    support_states: list[str] = []
    verified_wall_tie_pair = False
    model_parts = model.get("parts")
    if type(model_parts) is not list:
        _error("Maestro no devolvió piezas F6 para revisar soportes traseros")
    for module in modules:
        if type(module) is not dict:
            _error("Módulo Maestro inválido para revisar construcción")
        back = module.get("back")
        if back == "none":
            back_status = "none"
        elif back == "pending" or back is None:
            back_status = "pending"
        elif type(back) is dict and back.get("style") in {
                "inset_full", "inset_two_strips"}:
            back_status = back["style"]
        else:
            back_status = "unconfirmed"
        back_states.append(back_status)

        support = module.get("support")
        if support == "wall" or model.get("installation") == "wall_mounted":
            support_states.append("REAR_WALL_SUPPORT_PENDING")
        elif support in {"floor", "legs", "plinth"}:
            support_states.append("NOT_APPLICABLE")
        else:
            support_states.append("SUPPORT_PENDING")

        tie_review = module.get("wall_rear_ties_review")
        if tie_review is not None:
            if type(tie_review) is not dict:
                _error("Resumen Maestro de amarres traseros inválido")
            expected = {
                "wall_rear_lower_tie": module.get("module_id", "")
                                     + "-WALL_REAR_LOWER_TIE",
                "wall_rear_upper_tie": module.get("module_id", "")
                                     + "-WALL_REAR_UPPER_TIE",
            }
            module_parts = [part for part in model_parts
                            if type(part) is dict
                            and part.get("module_id") == module.get("module_id")
                            and part.get("role") in expected]
            by_role = {part["role"]: part for part in module_parts}
            thickness = tie_review.get("thickness_mm")
            tie_height = tie_review.get("tie_height_mm")
            material_id = tie_review.get("material_id")
            part_ids = module.get("part_ids")
            if (module.get("back") != "none"
                    or tie_review.get("module_id") != module.get("module_id")
                    or tie_review.get("style") != "direct_pair_review"
                    or tie_review.get("piece_ids") != list(expected.values())
                    or type(thickness) is not int or thickness <= 0
                    or type(tie_height) is not int or tie_height <= 0
                    or type(material_id) is not str or not material_id
                    or type(part_ids) is not list
                    or any(piece_id not in part_ids
                           for piece_id in expected.values())
                    or tie_review.get("structural_engineering") != "UNVERIFIED"
                    or tie_review.get("cabinet_wall_anchoring") != "NOT_DESIGNED"
                    or tie_review.get("install_ready") is not False
                    or set(by_role) != set(expected)
                    or any(by_role[role].get("piece_id") != piece_id
                           or by_role[role].get("material_id") != material_id
                           or by_role[role].get("thickness_mm") != thickness
                           or by_role[role].get("nominal_face_y_mm") != tie_height
                           or by_role[role].get("source_engine")
                              != "F6_WALL_REAR_TIES_CONCEPT_ONLY"
                           for role, piece_id in expected.items())):
                _error("Maestro devolvió un par de amarres incompleto o no verificable")
            verified_wall_tie_pair = True

    unique_back = sorted(set(back_states))
    unique_support = sorted(set(support_states))
    return {
        "back_status": unique_back[0] if len(unique_back) == 1 else "mixed",
        "wall_support_status": (
            unique_support[0] if len(unique_support) == 1 else "mixed"
        ),
        "wall_tie_mode": (
            "DIRECT_PAIR_CONCEPT_ONLY_UNVERIFIED"
            if verified_wall_tie_pair else
            "NOT_IMPLEMENTED"
            if "REAR_WALL_SUPPORT_PENDING" in support_states
            else "NOT_APPLICABLE"
        ),
        "install_ready": False,
        "module_count": len(modules),
    }


def _attach_construction_reviews(
    result: dict[str, Any], models_by_group: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    reviews = {group: _construction_review(model)
               for group, model in models_by_group.items()}
    result["construction_review_by_group"] = reviews
    if any(item["wall_support_status"] in {
            "REAR_WALL_SUPPORT_PENDING", "SUPPORT_PENDING", "mixed"}
            for item in reviews.values()):
        result["warnings"] = list(dict.fromkeys([
            *result["warnings"], "REAR_WALL_SUPPORT_PENDING",
        ]))
    if any(item["wall_tie_mode"] == "DIRECT_PAIR_CONCEPT_ONLY_UNVERIFIED"
           for item in reviews.values()):
        result["warnings"] = list(dict.fromkeys([
            *result["warnings"],
            "DIRECT_PAIR_CONCEPT_ONLY_UNVERIFIED_NO_LOADS_ANCHORS_OR_HOLES",
        ]))
    return result


def _apply_back_revisions(
    reviews: dict[str, dict[str, Any]], revisions: Any,
) -> dict[str, dict[str, Any]]:
    """Rebuild only explicitly revised groups from their private Maestro requests."""
    if type(revisions) is not list or not 1 <= len(revisions) <= MAX_BACK_REVISIONS:
        _error("back_revisions: se requiere una lista de 1 a 12 revisiones explícitas")

    from .maestro import consult_maestro
    from .cad_exchange import cad_exchange, validate_exchange

    by_group: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for revision in revisions:
        revision_fields = {"group_id", "module_id", "back"}
        wall_tie_fields = revision_fields | {"wall_rear_ties"}
        if (type(revision) is not dict
                or set(revision) not in (
                    revision_fields,
                    revision_fields | {"horizontal_divider_depth_mm"},
                    wall_tie_fields,
                )):
            _error(
                "back_revision: use group_id, module_id, back y, opcionalmente, "
                "horizontal_divider_depth_mm o wall_rear_ties"
            )
        group, module_id = revision["group_id"], revision["module_id"]
        if type(group) is not str or group not in ("BAJO", "ALTO", "TORRE"):
            _error("back_revision.group_id debe ser BAJO, ALTO o TORRE")
        if type(module_id) is not str or not module_id:
            _error("back_revision.module_id debe identificar un módulo existente")
        key = (group, module_id)
        if key in seen:
            _error("back_revisions no admite módulo duplicado")
        seen.add(key)

        reviewed = reviews.get(group)
        trusted = (reviewed.get("_trusted_nominal_request")
                   if type(reviewed) is dict else None)
        module_spec = trusted.get("module_spec") if type(trusted) is dict else None
        modules = module_spec.get("modules") if type(module_spec) is dict else None
        matches = ([module for module in modules if type(module) is dict
                    and module.get("module_id") == module_id]
                   if type(modules) is list else [])
        if (type(trusted) is not dict or trusted.get("action") != "modular"
                or len(matches) != 1):
            _error(f"{group}/{module_id}: no existe en la solicitud Maestro revalidada")
        if "wall_rear_ties" in revision:
            ties = revision["wall_rear_ties"]
            tie_fields = {"style", "material_id", "thickness_mm", "tie_height_mm"}
            if (group != "ALTO"
                    or module_spec.get("application") != "kitchen"
                    or set(revision) != wall_tie_fields
                    or revision["back"] != "none"
                    or type(ties) is not dict or set(ties) != tie_fields
                    or ties.get("style") != "direct_pair_review"):
                _error(
                    f"{group}/{module_id}: wall_rear_ties requiere ALTO de cocina, "
                    "back=none y el contrato direct_pair_review exacto"
                )
            target = matches[0]
            thickness = ties["thickness_mm"]
            tie_height = ties["tie_height_mm"]
            module_height = module_spec.get("height_mm")
            panel_thickness = target.get("panel_thickness_mm")
            if (module_spec.get("installation") != "wall_mounted"
                    or target.get("construction") != "sides_full"
                    or target.get("support") != "wall"
                    or target.get("back") != "none"
                    or "wall_rear_ties" in target
                    or target.get("material_id") != ties["material_id"]
                    or type(panel_thickness) is not int
                    or type(thickness) is not int or thickness != panel_thickness
                    or type(module_height) is not int
                    or type(tie_height) is not int or tie_height <= 0
                    or 2 * tie_height > module_height - 2 * panel_thickness
                    or any(target.get(field) is not None for field in (
                        "upper_support", "countertop", "support_concept",
                        "horizontal_divider", "vertical_divider", "corner_blind",
                    ))
                    or target.get("drawers", "none") not in (None, "none")):
                _error(
                    f"{group}/{module_id}: amarres requieren módulo ALTO mural "
                    "sides_full, wall, back=none, material/espesor coincidentes, "
                    "altura entera positiva y sin conceptos incompatibles"
                )
        by_group.setdefault(group, []).append(revision)

    effective = dict(reviews)
    for group, group_revisions in by_group.items():
        trusted = reviews[group]["_trusted_nominal_request"]
        rebuilt_request = copy.deepcopy(trusted)
        modules = rebuilt_request["module_spec"]["modules"]
        target_ids = set()
        for revision in group_revisions:
            module_id = revision["module_id"]
            targets = [module for module in modules
                       if module.get("module_id") == module_id]
            if len(targets) != 1:
                _error(f"{group}/{module_id}: solicitud privada inconsistente")
            target = targets[0]
            if "horizontal_divider_depth_mm" in revision:
                new_depth = revision["horizontal_divider_depth_mm"]
                divider = target.get("horizontal_divider")
                back = revision["back"]
                run_depth = rebuilt_request["module_spec"].get("depth_mm")
                if (type(new_depth) is not int or new_depth <= 0
                        or type(run_depth) is not int or run_depth <= 0
                        or type(divider) is not dict
                        or type(divider.get("depth_mm")) is not int
                        or divider["depth_mm"] <= 0
                        or type(divider.get("depth_from_front_mm")) is not int
                        or divider["depth_from_front_mm"] < 0
                        or type(back) is not dict
                        or back.get("style") != "inset_full"
                        or type(back.get("thickness_mm")) is not int
                        or back["thickness_mm"] <= 0
                        or back.get("services_present") is not False):
                    _error(
                        f"{group}/{module_id}: profundidad de repisa requiere "
                        "datos F6 enteros, fondo completo sin instalaciones y repisa existente"
                    )
                previous_depth = divider["depth_mm"]
                offset = divider["depth_from_front_mm"]
                thickness = back["thickness_mm"]
                if new_depth > previous_depth:
                    _error(
                        f"{group}/{module_id}: horizontal_divider_depth_mm "
                        "no puede ampliar la repisa existente"
                    )
                if offset + new_depth > run_depth - thickness:
                    _error(
                        f"{group}/{module_id}: profundidad de repisa intersecta "
                        "el fondo completo; se requiere una profundidad explícita compatible"
                    )
                divider["depth_mm"] = new_depth
            if "wall_rear_ties" in revision:
                target["back"] = "none"
                target["wall_rear_ties"] = copy.deepcopy(
                    revision["wall_rear_ties"]
                )
            else:
                target["back"] = copy.deepcopy(revision["back"])
            target_ids.add(module_id)

        answer = consult_maestro(rebuilt_request)
        model = answer.get("modular")
        if (answer.get("status") != "DRAFT_NOT_FOR_CUTTING"
                or type(model) is not dict
                or model.get("status") != "DRAFT_NOT_FOR_CUTTING"
                or any(answer.get(flag) is not False or model.get(flag) is not False
                       for flag in ("fabrication_ready", "cutting_ready",
                                    "drilling_ready", "purchase_ready"))
                or ("can_generate_f7c" in model
                    and model["can_generate_f7c"] is not False)):
            _error(f"{group}: Maestro no conservó el borrador nominal bloqueado")
        exchange = validate_exchange(cad_exchange(model))

        for module_id in target_ids:
            module_matches = [module for module in model.get("modules", [])
                              if type(module) is dict
                              and module.get("module_id") == module_id]
            if len(module_matches) != 1:
                _error(f"{group}/{module_id}: módulo ausente en el modelo Maestro")
            revision = next(
                item for item in group_revisions
                if item["module_id"] == module_id
            )
            if "wall_rear_ties" in revision:
                ties = revision["wall_rear_ties"]
                f6_module = module_matches[0]
                expected_ids = [
                    module_id + "-WALL_REAR_LOWER_TIE",
                    module_id + "-WALL_REAR_UPPER_TIE",
                ]
                roles = ("wall_rear_lower_tie", "wall_rear_upper_tie")
                f6_parts = [part for part in model.get("parts", [])
                            if type(part) is dict
                            and part.get("module_id") == module_id
                            and part.get("role") in roles]
                f6_by_role = {part["role"]: part for part in f6_parts}
                f6_review = f6_module.get("wall_rear_ties_review")
                height = f6_module.get("external_height_mm")
                depth = f6_module.get("external_depth_mm")
                clear_width = f6_module.get("clear_width_mm")
                thickness = f6_module.get("panel_thickness_mm")
                start_x = f6_module.get("start_x_mm")
                tie_height = ties["tie_height_mm"]
                front_shift = exchange.get("front_shift_mm", 0)
                if any(type(value) is not int for value in (
                        height, depth, clear_width, thickness, start_x,
                        tie_height, front_shift)) or front_shift < 0:
                    _error(f"{group}/{module_id}: dimensiones F6/CAD de amarres inválidas")
                expected_origins = {
                    roles[0]: [start_x + thickness, thickness, depth - thickness],
                    roles[1]: [start_x + thickness,
                               height - thickness - tie_height,
                               depth - thickness],
                }
                part_ids = f6_module.get("part_ids")
                if (f6_module.get("back") != "none"
                        or type(f6_review) is not dict
                        or f6_review.get("style") != "direct_pair_review"
                        or f6_review.get("piece_ids") != expected_ids
                        or f6_review.get("material_id") != ties["material_id"]
                        or f6_review.get("thickness_mm") != ties["thickness_mm"]
                        or f6_review.get("tie_height_mm") != tie_height
                        or f6_review.get("structural_engineering") != "UNVERIFIED"
                        or f6_review.get("cabinet_wall_anchoring") != "NOT_DESIGNED"
                        or f6_review.get("install_ready") is not False
                        or type(part_ids) is not list
                        or any(piece_id not in part_ids for piece_id in expected_ids)
                        or set(f6_by_role) != set(roles)
                        or len(f6_parts) != 2):
                    _error(f"{group}/{module_id}: Maestro/F6 no devolvió los dos amarres requeridos")
                cad_ties = [box for box in exchange["boxes"]
                            if box["module_id"] == module_id
                            and box["role"] in roles]
                if (len(cad_ties) != 2
                        or any(box["role"].startswith("back_")
                               for box in exchange["boxes"]
                               if box["module_id"] == module_id)):
                    _error(f"{group}/{module_id}: amarres no son un fondo ni coinciden con CAD")
                for role, expected_id in zip(roles, expected_ids):
                    part = f6_by_role[role]
                    origin = expected_origins[role]
                    cad_origin = [origin[0], origin[1], origin[2] + front_shift]
                    cad_matches = [box for box in cad_ties if box["role"] == role]
                    if (part.get("piece_id") != expected_id
                            or part.get("material_id") != ties["material_id"]
                            or part.get("thickness_mm") != ties["thickness_mm"]
                            or part.get("nominal_face_x_mm") != clear_width
                            or part.get("nominal_face_y_mm") != tie_height
                            or part.get("nominal_origin_xyz_mm") != origin
                            or part.get("face_plane") != "XY"
                            or part.get("source_engine")
                               != "F6_WALL_REAR_TIES_CONCEPT_ONLY"
                            or len(cad_matches) != 1
                            or cad_matches[0]["piece_id"] != expected_id
                            or cad_matches[0]["material_id"] != ties["material_id"]
                            or cad_matches[0]["origin_xyz_mm"] != cad_origin
                            or cad_matches[0]["size_xyz_mm"]
                               != [clear_width, tie_height, thickness]):
                        _error(f"{group}/{module_id}: CAD del amarre no coincide con F6")
                continue
            back = module_matches[0].get("back")
            if type(back) is not dict:
                _error(f"{group}/{module_id}: Maestro no devolvió un fondo explícito")
            requested_module = next(
                module for module in modules
                if module.get("module_id") == module_id
            )
            if back != requested_module.get("back"):
                _error(f"{group}/{module_id}: el fondo F6 difiere de la solicitud privada")
            if back.get("style") == "inset_full":
                expected_roles = ["back_full"]
            elif back.get("style") == "inset_two_strips":
                expected_roles = ["back_bottom", "back_top"]
            else:
                expected_roles = []
            actual = [box for box in exchange["boxes"]
                      if box["module_id"] == module_id
                      and box["role"].startswith("back_")]
            if (not expected_roles
                    or sorted(box["role"] for box in actual) != sorted(expected_roles)
                    or any(box["material_id"] != back["material_id"]
                           or box["size_xyz_mm"][2] != back["thickness_mm"]
                           for box in actual)):
                _error(f"{group}/{module_id}: el CADExchange no coincide con el fondo Maestro")

            f6_backs = [part for part in model.get("parts", [])
                        if type(part) is dict
                        and part.get("module_id") == module_id
                        and part.get("role", "").startswith("back_")]
            f6_by_role = {part["role"]: part for part in f6_backs}
            if (set(f6_by_role) != set(expected_roles)
                    or any(part.get("material_id") != back["material_id"]
                           or part.get("thickness_mm") != back["thickness_mm"]
                           for part in f6_backs)):
                _error(f"{group}/{module_id}: piezas F6 del fondo no coinciden con Maestro")
            front_shift = exchange.get("front_shift_mm", 0)
            if type(front_shift) is not int or front_shift < 0:
                _error(f"{group}/{module_id}: desplazamiento frontal CAD inválido")
            for role, part in f6_by_role.items():
                cad_matches = [box for box in actual if box["role"] == role]
                origin = list(part["nominal_origin_xyz_mm"])
                origin[2] += front_shift
                size = [part["nominal_face_x_mm"],
                        part["nominal_face_y_mm"], part["thickness_mm"]]
                if (role not in ("back_full", "back_bottom", "back_top")
                        or len(cad_matches) != 1
                        or cad_matches[0]["piece_id"] != part["piece_id"]
                        or cad_matches[0]["material_id"] != part["material_id"]
                        or cad_matches[0]["origin_xyz_mm"] != origin
                        or cad_matches[0]["size_xyz_mm"] != size):
                    _error(f"{group}/{module_id}: CAD del fondo no coincide con la pieza F6")

            if "horizontal_divider_depth_mm" in revision:
                divider = requested_module.get("horizontal_divider")
                f6_shelves = [part for part in model.get("parts", [])
                              if type(part) is dict
                              and part.get("module_id") == module_id
                              and part.get("role") == "shelf_horizontal"]
                cad_shelves = [box for box in exchange["boxes"]
                               if box["module_id"] == module_id
                               and box["role"] == "shelf_horizontal"]
                if (type(divider) is not dict or len(f6_shelves) != 1
                        or len(cad_shelves) != 1):
                    _error(f"{group}/{module_id}: Maestro debe devolver una repisa F6 única")
                shelf = f6_shelves[0]
                cad_shelf = cad_shelves[0]
                shelf_origin = list(shelf["nominal_origin_xyz_mm"])
                shelf_origin[2] += front_shift
                if (shelf["piece_id"] != module_id + "-SHELF"
                        or shelf.get("material_id") != divider.get("material_id")
                        or shelf.get("thickness_mm") != divider.get("thickness_mm")
                        or shelf.get("nominal_face_y_mm") != divider["depth_mm"]
                        or shelf.get("nominal_origin_xyz_mm", [None, None, None])[2]
                        != divider["depth_from_front_mm"]
                        or cad_shelf["piece_id"] != shelf["piece_id"]
                        or cad_shelf["material_id"] != shelf["material_id"]
                        or cad_shelf["origin_xyz_mm"] != shelf_origin
                        or cad_shelf["size_xyz_mm"] != [
                            shelf["nominal_face_x_mm"], shelf["thickness_mm"],
                            shelf["nominal_face_y_mm"],
                        ]):
                    _error(f"{group}/{module_id}: CAD de repisa no coincide con solicitud F6")

        effective[group] = {
            **reviews[group], "model": model, "exchange": exchange,
            "_trusted_nominal_request": rebuilt_request,
        }
    return effective


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _turn_point(x: int, z: int, width: int, depth: int, degrees: int) -> tuple[int, int]:
    """Top-view clockwise orthogonal rotations, retaining nonnegative XYZ."""
    if degrees == 0:
        return x, z
    if degrees == 90:
        return depth - z, x
    if degrees == 180:
        return width - x, depth - z
    return z, width - x


def _transform_box(box: dict[str, Any], dims: list[int], origin: list[int],
                   degrees: int) -> tuple[list[int], list[int]]:
    x, y, z = _vec3(box.get("origin_xyz_mm"), "box.origin_xyz_mm")
    sx, sy, sz = _vec3(box.get("size_xyz_mm"), "box.size_xyz_mm", positive=True)
    if x + sx > dims[0] or y + sy > dims[1] or z + sz > dims[2]:
        _error("panel CAD fuera de su envolvente local")
    rotated = [_turn_point(a, b, dims[0], dims[2], degrees)
               for a in (x, x + sx) for b in (z, z + sz)]
    xs = [a for a, _ in rotated]
    zs = [b for _, b in rotated]
    world_origin = [origin[0] + min(xs), origin[1] + y, origin[2] + min(zs)]
    world_size = [max(xs) - min(xs), sy, max(zs) - min(zs)]
    if any(o + s > LIMIT for o, s in zip(world_origin, world_size)):
        _error("elemento excede los límites espaciales de revisión")
    return world_origin, world_size


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> list[int] | None:
    lo = [max(a["origin_xyz_mm"][i], b["origin_xyz_mm"][i]) for i in range(3)]
    size_a = a.get("size_xyz_mm", a.get("bounds_xyz_mm"))
    size_b = b.get("size_xyz_mm", b.get("bounds_xyz_mm"))
    hi = [min(a["origin_xyz_mm"][i] + size_a[i],
              b["origin_xyz_mm"][i] + size_b[i]) for i in range(3)]
    if all(hi[i] > lo[i] for i in range(3)):
        return [hi[i] - lo[i] for i in range(3)]
    return None  # touching faces/edges are not penetrations


def compose_verified_exchanges(assemblies: list[dict[str, Any]],
                               service_zones: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Pure spatial review; CAD exchanges are trusted ONLY at its caller boundary.

    Each assembly: group_id, exchange (already validate_exchange-checked),
    origin_xyz_mm, rotation_deg.  It never accepts/executes client Python code.
    """
    if type(assemblies) is not list or not 1 <= len(assemblies) <= MAX_GROUPS:
        _error("assemblies: se admiten entre 1 y 6 muebles")
    if service_zones is None:
        service_zones = []
    if type(service_zones) is not list or len(service_zones) > MAX_ZONES:
        _error("service_zones: máximo 12 reservas")

    groups: list[dict[str, Any]] = []
    world_boxes: list[dict[str, Any]] = []
    seen_groups: set[str] = set()
    seen_pieces: set[str] = set()
    for assembly in assemblies:
        if type(assembly) is not dict or set(assembly) != {
            "group_id", "exchange", "origin_xyz_mm", "rotation_deg"
        }:
            _error("assemblies: esquema de grupo no admitido")
        gid = _id(assembly["group_id"], "group_id")
        if gid in seen_groups:
            _error("group_id duplicado")
        seen_groups.add(gid)
        rotation = assembly["rotation_deg"]
        if type(rotation) is not int or rotation not in ROTATIONS:
            _error(f"{gid}: rotación permitida 0,90,180,270 grados")
        origin = _vec3(assembly["origin_xyz_mm"], f"{gid}.origin_xyz_mm")
        exchange = assembly["exchange"]
        if (type(exchange) is not dict or exchange.get("status") != "DRAFT_NOT_FOR_CUTTING"
                or any(exchange.get(flag) is not False for flag in (
                    "fabrication_ready", "cutting_ready", "drilling_ready"))
                or any(exchange.get(flag) is not False for flag in (
                    "purchase_ready", "can_generate_f7c") if flag in exchange)
                or exchange.get("hardware_included") is not False
                or exchange.get("finished_panel_edges_included") is not False
                or type(exchange.get("geometry_sha256")) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", exchange["geometry_sha256"])):
            _error(f"{gid}: CADExchange sin certificación nominal")
        if _hash({key: value for key, value in exchange.items()
                  if key != "geometry_sha256"}) != exchange["geometry_sha256"]:
            _error(f"{gid}: integridad SHA geométrico incorrecta")
        dims = _vec3(exchange.get("bounds_xyz_mm"), f"{gid}.bounds_xyz_mm", positive=True)
        boxes = exchange.get("boxes")
        if type(boxes) is not list or not 1 <= len(boxes) <= 72:
            _error(f"{gid}: número de paneles fuera de límites")
        rotated_bounds = [dims[2], dims[1], dims[0]] if rotation in (90, 270) else list(dims)
        if any(origin[i] + rotated_bounds[i] > LIMIT for i in range(3)):
            _error(f"{gid}: envolvente fuera de los límites espaciales")
        groups.append({
            "group_id": gid, "geometry_sha256": exchange["geometry_sha256"],
            "origin_xyz_mm": origin, "rotation_deg": rotation,
            "bounds_xyz_mm": rotated_bounds, "piece_count": len(boxes),
        })
        for box in boxes:
            if type(box) is not dict:
                _error(f"{gid}: panel CAD inválido")
            pid = _id(box.get("piece_id"), f"{gid}.piece_id")
            qualified = f"{gid}:{pid}"
            if qualified in seen_pieces:
                _error(f"{gid}: pieza duplicada")
            seen_pieces.add(qualified)
            position, size = _transform_box(box, dims, origin, rotation)
            world_boxes.append({
                "group_id": gid, "piece_id": qualified,
                "role": box.get("role", "unknown"),
                "origin_xyz_mm": position, "size_xyz_mm": size,
            })

    # Broadphase conservative envelope interference, followed by panel-specific
    # evidence. A void inside a cabinet never makes an overlapping envelope safe.
    envelope_collisions: list[dict[str, Any]] = []
    panel_collisions: list[dict[str, Any]] = []
    for i, a in enumerate(groups):
        for b in groups[i + 1:]:
            overlap = _overlap(a, b)
            if overlap is None:
                continue
            envelope_collisions.append({
                "groups": [a["group_id"], b["group_id"]],
                "overlap_xyz_mm": overlap,
            })
            a_boxes = [p for p in world_boxes if p["group_id"] == a["group_id"]]
            b_boxes = [p for p in world_boxes if p["group_id"] == b["group_id"]]
            for left in a_boxes:
                for right in b_boxes:
                    section = _overlap(left, right)
                    if section is not None:
                        panel_collisions.append({
                            "pieces": [left["piece_id"], right["piece_id"]],
                            "overlap_xyz_mm": section,
                        })
                        if len(panel_collisions) >= 64:
                            break
                if len(panel_collisions) >= 64:
                    break

    zone_reviews: list[dict[str, Any]] = []
    seen_zones: set[str] = set()
    for zone in service_zones:
        if type(zone) is not dict or set(zone) != {
            "zone_id", "purpose", "origin_xyz_mm", "size_xyz_mm"
        }:
            _error("service_zone: esquema inválido")
        zid = _id(zone["zone_id"], "zone_id")
        if zid in seen_zones:
            _error("zone_id duplicado")
        seen_zones.add(zid)
        if zone["purpose"] not in PURPOSES:
            _error(f"{zid}: purpose no admitido")
        lo = _vec3(zone["origin_xyz_mm"], f"{zid}.origin_xyz_mm")
        size = _vec3(zone["size_xyz_mm"], f"{zid}.size_xyz_mm", positive=True)
        if any(lo[i] + size[i] > LIMIT for i in range(3)):
            _error(f"{zid}: zona fuera de límites")
        normalized = {"origin_xyz_mm": lo, "size_xyz_mm": size}
        touches = [p["piece_id"] for p in world_boxes if _overlap(normalized, p) is not None]
        inside = [g["group_id"] for g in groups if _overlap(normalized, g) is not None]
        fully_contained = [g["group_id"] for g in groups if all(
            lo[i] >= g["origin_xyz_mm"][i] and
            lo[i] + size[i] <= g["origin_xyz_mm"][i] + g["bounds_xyz_mm"][i]
            for i in range(3))]
        status = ("PANEL_INTERFERENCE" if touches else
                  "OUTSIDE_CABINETS" if not inside else
                  "PARTIAL_ENVELOPE_OVERLAP" if not fully_contained else
                  "CLEAR_NOMINAL_ONLY")
        zone_reviews.append({
            "zone_id": zid, "purpose": zone["purpose"],
            **normalized, "inside_groups": inside,
            "fully_contained_by": fully_contained,
            "intersected_piece_ids": touches,
            "status": status,
        })

    layout_entries = [{
        "group_id": g["group_id"], "geometry_sha256": g["geometry_sha256"],
        "origin_xyz_mm": g["origin_xyz_mm"], "rotation_deg": g["rotation_deg"],
    } for g in groups]
    canonical = {"groups": sorted(layout_entries, key=lambda g: g["group_id"]),
                 "service_zones": sorted(service_zones, key=lambda s: s["zone_id"])}
    status = ("INTERFERENCE_REVIEW_REQUIRED" if envelope_collisions or
              any(z["status"] in {"PANEL_INTERFERENCE", "PARTIAL_ENVELOPE_OVERLAP"}
                  for z in zone_reviews) else
              "REVIEW_ONLY")
    orthogonal = len(set(g["rotation_deg"] % 180 for g in groups)) > 1
    warnings = [
        "ALL_GEOMETRY_NOMINAL_NO_CUT_AUTHORITY",
        "ROOM_LAYOUT_DOES_NOT_VERIFY_WALLS_LOADS_ANCHORS_OR_HARDWARE",
        "SERVICE_RESERVATIONS_ARE_NOT_HOLES_OR_PLUMBING_INSTALLATION",
    ]
    if orthogonal:
        warnings.append("CORNER_JOINT_AND_FILLER_NOT_DESIGNED")
    if envelope_collisions:
        warnings.append("OVERLAPPING_CABINET_ENVELOPES_BLOCK_APPROVAL")
    return {
        "review_kind": "room_layout_v1", "status": status,
        "groups": groups, "world_boxes": world_boxes,
        "piece_count": len(world_boxes),
        "global_piece_ids": [b["piece_id"] for b in world_boxes],
        "envelope_collisions": envelope_collisions,
        "panel_collisions": panel_collisions,
        "service_zones": zone_reviews,
        "layout_sha256": _hash(canonical),
        "warnings": warnings, **PHYSICAL_FLAGS,
    }


def review_room_from_specs(request: dict[str, Any]) -> dict[str, Any]:
    """Only public entry: rebuild CADExchange from F6 specs on the server side.

    Never accept client-supplied boxes, CADExchange or geometry digests. Existing
    F6/commissioning contracts and permissions remain the authority.
    """
    if (type(request) is not dict or set(request) != {
        "review_kind", "assemblies", "service_zones"
    } or request.get("review_kind") != "room_layout_v1"):
        _error("room_layout_v1 requiere review_kind, assemblies, service_zones")
    from .maestro import consult_maestro
    from .cad_exchange import cad_exchange, validate_exchange
    assembly_input = request["assemblies"]
    if type(assembly_input) is not list or not 1 <= len(assembly_input) <= MAX_GROUPS:
        _error("assemblies: entre 1 y 6 grupos")
    prepared = []
    models_by_group: dict[str, dict[str, Any]] = {}
    for raw in assembly_input:
        if type(raw) is not dict or set(raw) != {
            "group_id", "module_spec", "origin_xyz_mm", "rotation_deg"
        } or type(raw.get("module_spec")) is not dict:
            _error("assembly: use group_id, module_spec, origin_xyz_mm, rotation_deg")
        answer = consult_maestro({"action": "modular", "module_spec": raw["module_spec"]})
        model = answer.get("modular")
        if (answer.get("status") != "DRAFT_NOT_FOR_CUTTING" or type(model) is not dict
                or model.get("status") != "DRAFT_NOT_FOR_CUTTING"
                or any(answer.get(f) is not False or model.get(f) is not False
                       for f in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"))
                or ("can_generate_f7c" in model and model["can_generate_f7c"] is not False)):

            _error("El compositor no entregó un modelo nominal seguro")
        exchange = validate_exchange(cad_exchange(model))
        models_by_group[raw["group_id"]] = model
        prepared.append({
            "group_id": raw["group_id"], "exchange": exchange,
            "origin_xyz_mm": raw["origin_xyz_mm"],
            "rotation_deg": raw["rotation_deg"],
        })
    result = compose_verified_exchanges(prepared, request["service_zones"])
    return _attach_construction_reviews(result, models_by_group)


def render_top_view_svg(review: dict[str, Any]) -> str:
    """Review-only top view of cabinet envelopes; never a fabrication drawing."""
    from xml.etree import ElementTree as ET
    if (type(review) is not dict or review.get("review_kind") != "room_layout_v1"
            or any(review.get(key) is not False for key in PHYSICAL_FLAGS)):
        _error("Vista superior: solo se admite un room_layout_v1 nominal bloqueado")
    groups = review.get("groups")
    if type(groups) is not list or not groups:
        _error("Vista superior: sin grupos")
    x_max = max(item["origin_xyz_mm"][0] + item["bounds_xyz_mm"][0]
                for item in groups) + 100
    z_max = max(item["origin_xyz_mm"][2] + item["bounds_xyz_mm"][2]
                for item in groups) + 100
    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg", "width": str(x_max),
        "height": str(z_max), "viewBox": f"0 0 {x_max} {z_max}",
        "role": "img", "aria-label": "Vista superior nominal, no fabricable",
    })
    ET.SubElement(svg, "title").text = "Distribución espacial nominal en mm"
    for group in groups:
        x, _, z = group["origin_xyz_mm"]
        w, _, d = group["bounds_xyz_mm"]
        ET.SubElement(svg, "rect", {
            "x": str(x), "y": str(z), "width": str(w), "height": str(d),
            "fill": "#eceff1", "stroke": "#263238", "stroke-width": "2",
        })
        ET.SubElement(svg, "text", {
            "x": str(x + 5), "y": str(z + min(25, d)),
            "font-family": "sans-serif", "font-size": "18", "fill": "#263238",
        }).text = group["group_id"]
    for zone in review.get("service_zones", []):
        x, _, z = zone["origin_xyz_mm"]
        w, _, d = zone["size_xyz_mm"]
        ET.SubElement(svg, "rect", {
            "x": str(x), "y": str(z), "width": str(w), "height": str(d),
            "fill": "none", "stroke": "#8d6e63", "stroke-width": "2",
            "stroke-dasharray": "8,6",
        })
    return ET.tostring(svg, encoding="unicode", short_empty_elements=True)

def review_room_from_kitchen_state(request: dict[str, Any]) -> dict[str, Any]:
    """D6: place D4's validated conversational kitchen using D5's CAD boxes.

    This does not trust public exchange/boxes/hash fields: the source review
    state holds only natural language and positions, rebuilt by Maestro/F6.
    The output remains an unapproved conceptual room layout.
    """
    from .kitchen_linear import _GROUPS, _build, _validate_state

    allowed = {
        frozenset(("review_kind", "review_state", "service_zones")),
        frozenset(("review_kind", "review_state", "service_zones", "rotations_deg")),
        frozenset(("review_kind", "review_state", "service_zones", "back_revisions")),
        frozenset(("review_kind", "review_state", "service_zones", "rotations_deg",
                   "back_revisions")),
    }
    if (type(request) is not dict or frozenset(request) not in allowed
            or request.get("review_kind") != "kitchen_spatial_v1"):
        _error("kitchen_spatial_v1 exige review_kind, review_state y service_zones")

    state = _validate_state(request["review_state"])
    last = state["last_valid"]
    if last is None or state["pending_candidate"] is not None:
        _error("La cocina debe tener tres grupos confirmados sin revisión pendiente")
    working = state["working"]
    if working["groups"] != last["groups"] or working["positions"] != last["positions"]:
        _error("El estado actual debe coincidir con la última disposición válida")

    rotations = request.get("rotations_deg", {g: 0 for g in _GROUPS})
    if (type(rotations) is not dict or set(rotations) != set(_GROUPS)
            or any(type(v) is not int or v not in ROTATIONS for v in rotations.values())):
        _error("rotations_deg requiere BAJO, ALTO, TORRE con 0/90/180/270")

    rebuilt = _build(working)  # Recomputes every group from text via real Maestro/F6.
    if (rebuilt["assemblage_status"] != "REVIEW_ONLY_VALID"
            or rebuilt["layout_sha256"] != last["layout_sha256"]):
        _error("El historial no valida la instantánea; no se aceptan hashes del cliente")

    reviewed_groups = (
        _apply_back_revisions(rebuilt["_reviews"], request["back_revisions"])
        if "back_revisions" in request else rebuilt["_reviews"]
    )
    assemblies = []
    models_by_group: dict[str, dict[str, Any]] = {}
    for group in _GROUPS:
        reviewed = reviewed_groups[group]
        origin = working["positions"][group]
        if (reviewed["status"] != "REVIEW_ONLY_VALID" or origin is None
                or type(reviewed.get("exchange")) is not dict):
            _error("Falta geometría nominal revalidada para " + group)
        assemblies.append({
            "group_id": group,
            "exchange": reviewed["exchange"],
            "origin_xyz_mm": origin,
            "rotation_deg": rotations[group],
        })
        models_by_group[group] = reviewed["model"]
    output = compose_verified_exchanges(assemblies, request["service_zones"])
    _attach_construction_reviews(output, models_by_group)
    if any(output.get(flag) is not False for flag in PHYSICAL_FLAGS):
        _error("La revisión espacial no puede habilitar fabricación")
    output["top_view_svg"] = render_top_view_svg(output)
    output["source_review_kind"] = "kitchen_linear_v1"
    output["source_layout_sha256"] = rebuilt["layout_sha256"]
    warnings = [*output["warnings"],
                "CONVERSATIONAL_LAYOUT_NOMINAL_ONLY_NO_FABRICATION"]
    if "back_revisions" in request:
        warnings.append("BACK_OPTIONS_UNAPPROVED")
    output["warnings"] = list(dict.fromkeys(warnings))
    return output

def _session_snapshot(assemblies: list[dict[str, Any]],
                      zones: list[dict[str, Any]],
                      digest: str) -> dict[str, Any]:
    """Client-carried *untrusted* inputs, not a privileged approval ticket.

    Layout digest is recomputed from Maestro/F6 on every subsequent turn.
    This checksum is not an authentication signature and never grants cutting.
    """
    from copy import deepcopy
    data = {
        "schema_version": "room_layout_session_v1",
        "assemblies": deepcopy(assemblies), "service_zones": deepcopy(zones),
        "layout_sha256": digest,
    }
    data["snapshot_sha256"] = _hash(data)
    return data


def _session_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Compact revision evidence, not a manufacturing drawing or full CAD."""
    return {
        "status": result["status"], "layout_sha256": result["layout_sha256"],
        "piece_count": result["piece_count"], "groups": result["groups"],
        "envelope_collisions": result["envelope_collisions"],
        "panel_collisions": result["panel_collisions"],
        "service_zones": result["service_zones"],
        "warnings": result["warnings"],
    }


def review_room_session(request: dict[str, Any]) -> dict[str, Any]:
    """D7: one safe, editable multivuelta spatial review over existing F6.

    `start` accepts precisely the same specs as D5 room_layout_v1. Subsequent
    `move`/`rotate`/`upsert_zone`/`remove_zone` always reconstruct Maestro/F6
    and CADExchange; there is no retained authority for client-side CAD boxes.
    Rejected collisions leave the previous verified state unchanged and include
    a visual candidate comparison for the user's next correction.
    """
    from copy import deepcopy

    if (type(request) is not dict or set(request) !=
            {"review_kind", "review_state", "edit"} or
            request.get("review_kind") != "room_layout_session_v1" or
            type(request["edit"]) is not dict):
        _error("room_layout_session_v1 exige review_kind, review_state y edit")
    previous = request["review_state"]
    edit = request["edit"]
    if type(edit.get("op")) is not str:
        _error("edit.op inválido")

    if previous is None:
        if set(edit) != {"op", "assemblies", "service_zones"} or edit["op"] != "start":
            _error("Primera revisión exige start con assemblies y service_zones")
        assemblies = deepcopy(edit["assemblies"])
        zones = deepcopy(edit["service_zones"])
        before = None
    else:
        if (type(previous) is not dict or set(previous) != {
            "schema_version", "assemblies", "service_zones",
            "layout_sha256", "snapshot_sha256",
        } or previous["schema_version"] != "room_layout_session_v1"):
            _error("review_state espacial inválido")
        raw = {key: value for key, value in previous.items() if key != "snapshot_sha256"}
        try:
            digest = _hash(raw)
        except (TypeError, ValueError, OverflowError, RecursionError):
            _error("review_state no es JSON canónico")
        if (type(previous["snapshot_sha256"]) is not str or
                previous["snapshot_sha256"] != digest or
                type(previous["layout_sha256"]) is not str):
            _error("review_state modificado; checksum no coincide")
        if edit["op"] == "start":
            _error("start no puede reemplazar un estado existente")
        assemblies = deepcopy(previous["assemblies"])
        zones = deepcopy(previous["service_zones"])
        # Only the existing public D5 boundary is allowed to issue a review.
        before = review_room_from_specs({
            "review_kind": "room_layout_v1", "assemblies": assemblies,
            "service_zones": zones,
        })
        if (before["status"] != "REVIEW_ONLY" or
                before["layout_sha256"] != previous["layout_sha256"] or
                any(before.get(flag) is not False for flag in PHYSICAL_FLAGS)):
            _error("Estado anterior ya no revalida con Maestro/CAD")
        op = edit["op"]
        if op in {"move", "rotate"}:
            needed = ({"op", "group_id", "origin_xyz_mm"} if op == "move" else
                      {"op", "group_id", "rotation_deg"})
            if set(edit) != needed or type(edit["group_id"]) is not str:
                _error("Edición de módulo contiene campos inválidos")
            matching = [item for item in assemblies if item.get("group_id") == edit["group_id"]]
            if len(matching) != 1:
                _error("No existe el módulo especificado")
            if op == "move":
                matching[0]["origin_xyz_mm"] = _vec3(edit["origin_xyz_mm"], "origin_xyz_mm")
            else:
                if type(edit["rotation_deg"]) is not int or edit["rotation_deg"] not in ROTATIONS:
                    _error("rotation_deg debe ser 0,90,180 o 270")
                matching[0]["rotation_deg"] = edit["rotation_deg"]
        elif op == "upsert_zone":
            if set(edit) != {"op", "zone"} or type(edit["zone"]) is not dict:
                _error("upsert_zone exige una zona")
            zone = deepcopy(edit["zone"])
            if set(zone) != {"zone_id", "purpose", "origin_xyz_mm", "size_xyz_mm"}:
                _error("Zona con campos no permitidos")
            zid = _id(zone["zone_id"], "zone_id")
            if type(zone["purpose"]) is not str or zone["purpose"] not in PURPOSES:
                _error("Propósito de zona desconocido")
            zone["origin_xyz_mm"] = _vec3(zone["origin_xyz_mm"], "zone.origin_xyz_mm")
            zone["size_xyz_mm"] = _vec3(zone["size_xyz_mm"], "zone.size_xyz_mm", positive=True)
            zones = [item for item in zones if item.get("zone_id") != zid]
            zones.append(zone)
        elif op == "remove_zone":
            if set(edit) != {"op", "zone_id"}:
                _error("remove_zone exige zone_id")
            zid = _id(edit["zone_id"], "zone_id")
            if not any(item.get("zone_id") == zid for item in zones):
                _error("La zona a eliminar no existe")
            zones = [item for item in zones if item["zone_id"] != zid]
        else:
            _error("Operación desconocida; usar move, rotate, upsert_zone o remove_zone")

    # All edits, even when blocked, go through real Maestro and CADExchange.
    candidate = review_room_from_specs({
        "review_kind": "room_layout_v1", "assemblies": assemblies,
        "service_zones": zones,
    })
    if any(candidate.get(flag) is not False for flag in PHYSICAL_FLAGS):
        _error("La revisión no puede conceder permisos físicos")
    accepted = candidate["status"] == "REVIEW_ONLY"
    current_state = (_session_snapshot(assemblies, zones, candidate["layout_sha256"])
                     if accepted else deepcopy(previous))
    # In the first turn a rejected candidate deliberately produces no last_valid.
    out = {
        "review_kind": "room_layout_session_v1",
        "status": "REVIEW_ONLY_STATE_UPDATED" if accepted else "NEEDS_CORRECTION",
        "review_state": current_state,
        "before": _session_summary(before) if before is not None else None,
        "candidate": _session_summary(candidate),
        "before_svg": render_top_view_svg(before) if before is not None else None,
        "candidate_svg": render_top_view_svg(candidate),
        "change_applied": accepted,
        "warnings": list(dict.fromkeys([
            *candidate["warnings"],
            "SPATIAL_EDIT_ONLY_NOT_A_FABRICATION_APPROVAL",
        ])),
        **PHYSICAL_FLAGS,
    }
    return out

def review_room_fit(request: dict[str, Any]) -> dict[str, Any]:
    """D8: conservative room/obstacle fit using *only* revalidated D5 CAD.

    It does not infer room measurements, legal clearances, door arcs or cutouts.
    All room and obstacle dimensions must be provided in millimetres by a human.
    The same D5 public boundary reconstructs F6/CADExchange from module_specs.
    """
    from xml.etree import ElementTree as ET

    if (type(request) is not dict or set(request) != {
            'review_kind', 'assemblies', 'service_zones', 'room'
        } or request.get('review_kind') != 'room_fit_v1'):
        _error('room_fit_v1 requiere review_kind, assemblies, service_zones y room')
    room = request['room']
    if type(room) is not dict or set(room) != {'size_xyz_mm', 'obstacles'}:
        _error('room exige size_xyz_mm y obstacles')
    room_size = _vec3(room['size_xyz_mm'], 'room.size_xyz_mm', positive=True)
    raw_obstacles = room['obstacles']
    if type(raw_obstacles) is not list or len(raw_obstacles) > 12:
        _error('room.obstacles: máximo 12 obstáculos')
    kinds = ('column', 'fixed_wall', 'opening_keepout', 'appliance_keepout',
             'access_keepout', 'other')
    obstacles = []
    seen = set()
    for obstacle in raw_obstacles:
        if type(obstacle) is not dict or set(obstacle) != {
            'obstacle_id', 'kind', 'origin_xyz_mm', 'size_xyz_mm'
        }:
            _error('obstacle: esquema estricto requerido')
        oid = _id(obstacle['obstacle_id'], 'obstacle_id')
        if oid in seen:
            _error('obstacle_id duplicado')
        seen.add(oid)
        if type(obstacle['kind']) is not str or obstacle['kind'] not in kinds:
            _error('obstacle.kind no admitido')
        origin = _vec3(obstacle['origin_xyz_mm'], 'obstacle.origin_xyz_mm')
        size = _vec3(obstacle['size_xyz_mm'], 'obstacle.size_xyz_mm', positive=True)
        # An obstacle measured outside the room is a *bad survey*, not a safe fit.
        if any(origin[i] + size[i] > room_size[i] for i in range(3)):
            _error('obstacle fuera del recinto medido')
        obstacles.append({'obstacle_id': oid, 'kind': obstacle['kind'],
                          'origin_xyz_mm': origin, 'size_xyz_mm': size})

    # Do not use client-provided exchange, panel geometry or digest: D5 owns it.
    layout = review_room_from_specs({
        'review_kind': 'room_layout_v1',
        'assemblies': request['assemblies'],
        'service_zones': request['service_zones'],
    })
    if any(layout.get(flag) is not False for flag in PHYSICAL_FLAGS):
        _error('layout intentó habilitar permisos físicos')
    if layout.get('review_kind') != 'room_layout_v1':
        _error('D5 retornó tipo de revisión inesperado')
    groups = layout['groups']
    for g in groups:
        _id(g['group_id'], 'group_id')
    fit = []
    for g in groups:
        inside = all(g['origin_xyz_mm'][i] + g['bounds_xyz_mm'][i] <= room_size[i]
                     for i in range(3))
        fit.append({'group_id': g['group_id'], 'inside_room': inside,
                    'origin_xyz_mm': list(g['origin_xyz_mm']),
                    'bounds_xyz_mm': list(g['bounds_xyz_mm'])})

    envelope_hits = []
    piece_hits = []
    for obstacle in obstacles:
        for g in groups:
            intersection = _overlap(obstacle, g)
            if intersection is not None:
                envelope_hits.append({'obstacle_id': obstacle['obstacle_id'],
                                      'group_id': g['group_id'],
                                      'overlap_xyz_mm': intersection})
        # Evidence only, not an exemption: a column in a cabinet's void is
        # still a potential obstruction unless a real designer approves it.
        for p in layout['world_boxes']:
            intersection = _overlap(obstacle, p)
            if intersection is not None:
                piece_hits.append({'obstacle_id': obstacle['obstacle_id'],
                                   'piece_id': p['piece_id'],
                                   'overlap_xyz_mm': intersection})
    # D10: service reservations are part of the measured room review too.
    # A reservation outside cabinets is not automatically inside the room;
    # and an obstacle crossing a service zone needs human review even when
    # no cabinet panel is intersected. No holes or permits are created.
    zone_fit = []
    zone_obstacle_hits = []
    for zone in layout['service_zones']:
        zone_origin = _vec3(zone['origin_xyz_mm'], 'service_zone.origin_xyz_mm')
        zone_size = _vec3(zone['size_xyz_mm'], 'service_zone.size_xyz_mm', positive=True)
        inside = all(zone_origin[i] + zone_size[i] <= room_size[i]
                     for i in range(3))
        zone_fit.append({'zone_id': zone['zone_id'], 'inside_room': inside,
                         'origin_xyz_mm': zone_origin, 'size_xyz_mm': zone_size})
        volume = {'origin_xyz_mm': zone_origin, 'size_xyz_mm': zone_size}
        for obstacle in obstacles:
            section = _overlap(volume, obstacle)
            if section is not None:
                zone_obstacle_hits.append({
                    'zone_id': zone['zone_id'],
                    'obstacle_id': obstacle['obstacle_id'],
                    'overlap_xyz_mm': section,
                })
    blocked = (layout['status'] != 'REVIEW_ONLY' or
               any(not item['inside_room'] for item in fit) or
               any(not item['inside_room'] for item in zone_fit) or
               bool(envelope_hits) or bool(zone_obstacle_hits))

    # All drawn elements use the same measured coordinates. 2D is only a
    # footprint; Y/height checks are done above but not visible in top view.
    width, _, depth = room_size
    # Keep the viewport manageable on Windows; the viewBox remains in actual mm.
    scale = min(1.0, 1200 / max(width, depth))
    width_px = max(1, round(width * scale))
    height_px = max(1, round(depth * scale))
    root = ET.Element('svg', {
        'xmlns': 'http://www.w3.org/2000/svg',
        'width': str(width_px), 'height': str(height_px),
        'viewBox': f'0 0 {width} {depth}',
        'role': 'img', 'aria-label': 'Revisión nominal de recinto, no fabricable',
    })
    ET.SubElement(root, 'title').text = 'Encaje nominal en recinto, no plano de obra'
    ET.SubElement(root, 'rect', {
        'x': '0', 'y': '0', 'width': str(width), 'height': str(depth),
        'fill': '#fff', 'stroke': '#334155', 'stroke-width': '5',
    })
    for g in groups:
        x, _, z = g['origin_xyz_mm']
        w, _, d = g['bounds_xyz_mm']
        flagged = any(i['group_id'] == g['group_id'] and not i['inside_room'] for i in fit)
        ET.SubElement(root, 'rect', {
            'x': str(x), 'y': str(z), 'width': str(w), 'height': str(d),
            'fill': '#fecaca' if flagged else '#dbeafe',
            'stroke': '#9f1239' if flagged else '#1d4ed8', 'stroke-width': '3',
        })
        ET.SubElement(root, 'text', {
            'x': str(x + 5), 'y': str(z + min(24, d)),
            'font-family': 'sans-serif', 'font-size': '18',
        }).text = g['group_id']
    for obstacle in obstacles:
        x, _, z = obstacle['origin_xyz_mm']
        w, _, d = obstacle['size_xyz_mm']
        ET.SubElement(root, 'rect', {
            'x': str(x), 'y': str(z), 'width': str(w), 'height': str(d),
            'fill': '#fca5a5', 'fill-opacity': '0.5',
            'stroke': '#991b1b', 'stroke-width': '2', 'stroke-dasharray': '6,4',
        })
    # Show reviewed reservation footprints as dashed rectangles; top view
    # does not represent depth/height or validate service routing.
    for zone in zone_fit:
        x, _, z = zone['origin_xyz_mm']
        w, _, d = zone['size_xyz_mm']
        ET.SubElement(root, 'rect', {
            'x': str(x), 'y': str(z), 'width': str(w), 'height': str(d),
            'fill': 'none', 'stroke': '#7c3aed', 'stroke-width': '3',
            'stroke-dasharray': '8,5',
        })
    warnings = list(dict.fromkeys([
        *layout['warnings'],
        'SERVICE_RESERVATIONS_CANNOT_EXTEND_BEYOND_MEASURED_ROOM',
        'SERVICE_ZONES_CROSSING_OBSTACLES_REQUIRE_REVIEW',
        'ROOM_MEASUREMENTS_AND_OBSTACLES_MUST_BE_CONFIRMED_ON_SITE',
        'OPENING_KEEP_OUT_IS_A_RECTANGLE_NOT_A_VERIFIED_DOOR_SWING',
        'ROOM_FIT_IS_NOT_A_STRUCTURAL_OR_ACCESSIBILITY_CERTIFICATE',
    ]))
    return {
        'review_kind': 'room_fit_v1',
        'status': 'ROOM_FIT_REVIEW_REQUIRED' if blocked else 'ROOM_FIT_NOMINAL_ONLY',
        'layout_status': layout['status'],
        'layout_sha256': layout['layout_sha256'],
        'room_fit_sha256': _hash({'layout_sha256': layout['layout_sha256'],
                                 'size_xyz_mm': room_size,
                                 'obstacles': sorted(obstacles, key=lambda o: o['obstacle_id'])}),
        'room_size_xyz_mm': room_size,
        'groups': fit,
        'obstacles': obstacles,
        'obstacle_envelope_interferences': envelope_hits,
        'obstacle_piece_interferences': piece_hits,
        'service_zone_room_fit': zone_fit,
        'service_zone_obstacle_interferences': zone_obstacle_hits,
        'layout_envelope_collisions': layout['envelope_collisions'],
        'layout_service_zones': layout['service_zones'],
        'top_view_svg': ET.tostring(root, encoding='unicode', short_empty_elements=True),
        'warnings': warnings,
        **PHYSICAL_FLAGS,
    }
