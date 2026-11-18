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
