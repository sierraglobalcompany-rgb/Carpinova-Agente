"""D5: nominal 3-D room composition reusing existing CADExchange boxes.

This module does NOT design cabinet boards, cutouts, joints or hardware.  Its
input exchanges must be produced and validated by local Maestro/CADExchange;
see review_room_from_specs() for that trust boundary.  All coordinates are mm.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
LIMIT = 20000
MAX_GROUPS = 6
MAX_ZONES = 12
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
        prepared.append({
            "group_id": raw["group_id"], "exchange": exchange,
            "origin_xyz_mm": raw["origin_xyz_mm"],
            "rotation_deg": raw["rotation_deg"],
        })
    return compose_verified_exchanges(prepared, request["service_zones"])


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

    assemblies = []
    for group in _GROUPS:
        reviewed = rebuilt["_reviews"][group]
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
    output = compose_verified_exchanges(assemblies, request["service_zones"])
    if any(output.get(flag) is not False for flag in PHYSICAL_FLAGS):
        _error("La revisión espacial no puede habilitar fabricación")
    output["top_view_svg"] = render_top_view_svg(output)
    output["source_review_kind"] = "kitchen_linear_v1"
    output["source_layout_sha256"] = rebuilt["layout_sha256"]
    output["warnings"] = list(dict.fromkeys([
        *output["warnings"],
        "CONVERSATIONAL_LAYOUT_NOMINAL_ONLY_NO_FABRICATION",
    ]))
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
