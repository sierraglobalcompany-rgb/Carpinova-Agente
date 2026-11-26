"""Deterministic nominal geometry for review-only French cleat profiles.

This module does not create F6/CADExchange parts and never authorizes installation.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from xml.etree import ElementTree as ET


_FIELDS = {
    "group_id", "module_id", "system", "length_mm", "section_height_mm",
    "thickness_mm", "base_y_from_carcass_mm", "rear_clearance_mm",
    "confirm_external_clearance",
}
_INT_FIELDS = {
    "length_mm": 1, "section_height_mm": 1, "thickness_mm": 1,
    "base_y_from_carcass_mm": 0, "rear_clearance_mm": 1,
}
_PROFILE_ROLES = ("french_cleat_cabinet", "french_cleat_wall")
_EMPTY_SHA256 = hashlib.sha256(b"[]").hexdigest()


class WallFixationError(ValueError):
    """A French cleat review cannot be reconciled safely with verified F6/CAD."""


def _fail(message: str) -> None:
    raise WallFixationError(message)


def _identity(value: Any, name: str) -> str:
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        _fail(f"wall_fixation_revisions.{name}: identidad inválida")
    return value


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_revisions(
    revisions: Any, contexts: dict[tuple[str, str], dict[str, Any]],
    wall_reviews: Any,
) -> list[dict[str, Any]]:
    if type(revisions) is not list or len(revisions) > 12:
        _fail("wall_fixation_revisions debe ser una lista de 0 a 12 entradas")
    if type(wall_reviews) is not list:
        _fail("wall_review_by_module debe existir para validar el sistema francés")
    effective = {(row.get("group_id"), row.get("module_id")): row
                 for row in wall_reviews if type(row) is dict}
    normalized = []
    seen: set[tuple[str, str]] = set()
    for raw in revisions:
        if type(raw) is not dict or set(raw) != _FIELDS:
            _fail("wall_fixation_revisions requiere el esquema exacto de revisión francesa")
        item = {
            "group_id": _identity(raw["group_id"], "group_id"),
            "module_id": _identity(raw["module_id"], "module_id"),
            "system": raw["system"],
        }
        if item["system"] != "french_cleat_45":
            _fail("wall_fixation_revisions solo admite french_cleat_45")
        key = item["group_id"], item["module_id"]
        if key in seen or key not in contexts:
            _fail("wall_fixation_revisions tiene identidad duplicada o ausente de Maestro/F6")
        wall = effective.get(key)
        if type(wall) is not dict or wall.get("wall_system") != "french_cleat_45":
            _fail("La fijación requiere wall_review_revisions francés efectivo para el mismo módulo")
        for name, minimum in _INT_FIELDS.items():
            value = raw[name]
            if type(value) is not int or not minimum <= value <= 20000:
                _fail(f"wall_fixation_revisions.{name} debe ser entero dentro del límite")
            item[name] = value
        if raw["confirm_external_clearance"] is not True:
            _fail("Confirma explícitamente la reserva externa nominal")
        item["confirm_external_clearance"] = True
        if item["section_height_mm"] < item["thickness_mm"] + 2:
            _fail("section_height_mm debe ser al menos thickness_mm + 2")
        if item["rear_clearance_mm"] < item["thickness_mm"]:
            _fail("La reserva posterior debe ser igual o mayor al espesor del perfil")
        seen.add(key)
        normalized.append(item)
    return sorted(normalized, key=lambda row: (row["group_id"], row["module_id"]))


def _cross(a: list[float], b: list[float]) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(a[i] * b[i] for i in range(3))


def _outward_faces(vertices: list[list[int]]) -> list[list[int]]:
    faces = [[0, 1, 2, 3], [7, 6, 5, 4]]
    faces.extend([[i, (i + 1) % 4, (i + 1) % 4 + 4, i + 4] for i in range(4)])
    center = [sum(point[axis] for point in vertices) / 8 for axis in range(3)]
    for face in faces:
        a, b, c = (vertices[index] for index in face[:3])
        normal = _cross([b[i] - a[i] for i in range(3)],
                        [c[i] - b[i] for i in range(3)])
        face_center = [sum(vertices[index][axis] for index in face) / 4
                       for axis in range(3)]
        if _dot(normal, [face_center[i] - center[i] for i in range(3)]) < 0:
            face.reverse()
    return faces


def _bounds(points: list[list[int]]) -> tuple[list[int], list[int]]:
    low = [min(point[i] for point in points) for i in range(3)]
    high = [max(point[i] for point in points) for i in range(3)]
    return low, [high[i] - low[i] for i in range(3)]


def _overlap(left: dict[str, Any], right: dict[str, Any]) -> list[int] | None:
    lo = [max(left["origin_xyz_mm"][i], right["origin_xyz_mm"][i])
          for i in range(3)]
    ls = left.get("size_xyz_mm", left.get("bounds_xyz_mm"))
    rs = right.get("size_xyz_mm", right.get("bounds_xyz_mm"))
    hi = [min(left["origin_xyz_mm"][i] + ls[i],
              right["origin_xyz_mm"][i] + rs[i]) for i in range(3)]
    return [hi[i] - lo[i] for i in range(3)] if all(hi[i] > lo[i] for i in range(3)) else None


def _pair_geometry(
    revision: dict[str, Any], context: dict[str, Any], review: dict[str, Any],
    existing_reservations: list[dict[str, Any]],
) -> dict[str, Any]:
    from .room_spatial import LIMIT, _turn_point

    group, module_id = revision["group_id"], revision["module_id"]
    module = context.get("module")
    parts = context.get("parts_by_id")
    cad = context.get("cad_by_id")
    if type(module) is not dict or type(parts) is not dict or type(cad) is not dict:
        _fail(f"{group}/{module_id}: falta contexto F6/CAD privado")
    part_ids = module.get("part_ids")
    if type(part_ids) is not list or not part_ids:
        _fail(f"{group}/{module_id}: part_ids F6 vacíos")
    owned = [cad.get(pid) for pid in part_ids]
    if any(type(box) is not dict or box.get("module_id") != module_id for box in owned):
        _fail(f"{group}/{module_id}: cajas CADExchange no concilian propiedad F6")
    sides = {parts[pid].get("role"): cad[pid] for pid in part_ids
             if pid in parts and pid in cad and parts[pid].get("role") in {"left_side", "right_side"}}
    left, right = sides.get("left_side"), sides.get("right_side")
    if type(left) is not dict or type(right) is not dict:
        _fail(f"{group}/{module_id}: se requieren ambos laterales estructurales F6")
    lx, ly, lz = left.get("origin_xyz_mm", []); lw, lh, ld = left.get("size_xyz_mm", [])
    rx, ry, rz = right.get("origin_xyz_mm", []); rw, rh, rd = right.get("size_xyz_mm", [])
    if (ly != ry or lh != rh or lz != rz or ld != rd or lw <= 0 or rw <= 0
            or lx + lw >= rx):
        _fail(f"{group}/{module_id}: laterales F6 no definen un vano interior coherente")
    inner_min, inner_max = lx + lw, rx
    inner_width = inner_max - inner_min
    length, height, thickness = (revision["length_mm"], revision["section_height_mm"],
                                 revision["thickness_mm"])
    if length > inner_width:
        _fail("La longitud del perfil supera el vano libre entre laterales F6")
    x0 = inner_min + (inner_width - length) // 2
    y0_local = ly + revision["base_y_from_carcass_mm"]
    if y0_local < ly or y0_local + height > ly + lh:
        _fail("La altura/base nominal del perfil queda fuera de la carcasa F6")
    z0_local = max(box["origin_xyz_mm"][2] + box["size_xyz_mm"][2]
                   for box in owned)
    dims = context.get("exchange_bounds_xyz_mm")
    origin = context.get("assembly_origin_xyz_mm")
    rotation = context.get("rotation_deg")
    if (type(dims) is not list or len(dims) != 3 or any(type(v) is not int or v <= 0 for v in dims)
            or type(origin) is not list or len(origin) != 3
            or any(type(v) is not int or v < 0 for v in origin)
            or type(rotation) is not int or rotation not in {0, 90, 180, 270}):
        _fail(f"{group}/{module_id}: transformación local F6 no verificable")
    a = (height - thickness) // 2
    sections = {
        "french_cleat_cabinet": [[0, a + thickness], [thickness, a],
                                 [thickness, height], [0, height]],
        "french_cleat_wall": [[0, 0], [thickness, 0],
                              [thickness, a], [0, a + thickness]],
    }

    def transform(point: list[int]) -> list[int]:
        x, y, z = point
        tx, tz = _turn_point(x, z, dims[0], dims[2], rotation)
        out = [origin[0] + tx, origin[1] + y, origin[2] + tz]
        if any(value < 0 or value > LIMIT for value in out):
            _fail("Perfil o reserva francesa excede el dominio espacial tras rotación")
        return out

    profiles = []
    for role in _PROFILE_ROLES:
        section = sections[role]
        local_vertices = [[x, y0_local + rel_y, z0_local + rel_z]
                          for x in (x0, x0 + length)
                          for rel_z, rel_y in section]
        vertices = [transform(point) for point in local_vertices]
        low, size = _bounds(vertices)
        faces = _outward_faces(vertices)
        profiles.append({
            "id": f"WALLFIX:{group}:{module_id}:{role.upper()}",
            "role": role, "vertices_xyz_mm": vertices, "faces": faces,
            "bounds_origin_xyz_mm": low, "bounds_size_xyz_mm": size,
        })
    reserve_corners = [transform([x, y, z])
                       for x in (x0, x0 + length)
                       for y in (y0_local, y0_local + height)
                       for z in (z0_local, z0_local + revision["rear_clearance_mm"])]
    reserve_low, reserve_size = _bounds(reserve_corners)
    reservation = {"group_id": group, "module_id": module_id,
                   "origin_xyz_mm": reserve_low, "size_xyz_mm": reserve_size}

    world_boxes = review.get("world_boxes")
    groups = review.get("groups")
    if type(world_boxes) is not list or type(groups) is not list:
        _fail("La revisión no contiene cajas y envolventes espaciales")
    for box in world_boxes:
        if _overlap(reservation, box) is not None:
            _fail(f"Reserva francesa intersecta tablero nominal {box.get('piece_id')}")
    for other in groups:
        if other.get("group_id") != group and _overlap(reservation, other) is not None:
            _fail(f"Reserva francesa intersecta envolvente del grupo {other.get('group_id')}")
    for zone in review.get("service_zones", []):
        if _overlap(reservation, zone) is not None:
            _fail(f"Reserva francesa intersecta servicio {zone.get('zone_id')}")
    for support in review.get("support_reservations", []):
        if _overlap(reservation, support) is not None:
            _fail(f"Reserva francesa intersecta apoyo {support.get('module_id')}")
    for previous in existing_reservations:
        if _overlap(reservation, previous) is not None:
            _fail("Reservas nominales de perfiles franceses se intersectan")
    known_ids = set(review.get("global_piece_ids", []))
    if any(profile["id"] in known_ids for profile in profiles):
        _fail("Identidad de perfil colisiona con un ID F6/CAD de tablero")
    return {
        "group_id": group, "module_id": module_id, "system": "french_cleat_45",
        "parameters": {key: revision[key] for key in (
            "length_mm", "section_height_mm", "thickness_mm",
            "base_y_from_carcass_mm", "rear_clearance_mm",
            "confirm_external_clearance")},
        "profiles": profiles,
        "section_vertices_yz_mm": sections,
        "clearance_reservation": reservation,
        "status": "MODELED_NOMINAL_FIXATION_ONLY",
        "clearance_status": "DECLARED_NOMINAL_SPACE_ONLY",
        "material_status": "UNSPECIFIED_REVIEW_ONLY",
        "book_evidence": [{
            "content_id": "CONTENT-CPNC-2025-P0141-003", "pdf_page": 141,
            "printed_page": 119, "review_status": "VISUALLY_VERIFIED",
        }],
        "connection_constraints": [
            "CARCASS_CONNECTION_AND_LOAD_PATH_UNVERIFIED",
            "WALL_SUBSTRATE_AND_ANCHOR_UNVERIFIED",
            "INSTALLATION_AND_STRUCTURAL_CAPACITY_UNVERIFIED",
        ],
        "install_ready": False,
    }


def build_geometry(
    revisions: list[dict[str, Any]], contexts: dict[tuple[str, str], dict[str, Any]],
    review: dict[str, Any],
) -> list[dict[str, Any]]:
    result = []
    reservations = []
    for revision in revisions:
        key = revision["group_id"], revision["module_id"]
        pair = _pair_geometry(revision, contexts[key], review, reservations)
        reservations.append(pair["clearance_reservation"])
        result.append(pair)
    return result


def validate_geometry(geometry: Any, digest: Any) -> list[dict[str, Any]]:
    if type(geometry) is not list or len(geometry) > 12:
        _fail("wall_fixation_geometry debe ser una lista de máximo 12 parejas")
    if type(digest) is not str or digest != canonical_sha256(geometry):
        _fail("wall_fixation_sha256 no coincide con la geometría")
    seen = set()
    for pair in geometry:
        if (type(pair) is not dict or pair.get("system") != "french_cleat_45"
                or pair.get("status") != "MODELED_NOMINAL_FIXATION_ONLY"
                or pair.get("clearance_status") != "DECLARED_NOMINAL_SPACE_ONLY"
                or pair.get("material_status") != "UNSPECIFIED_REVIEW_ONLY"
                or pair.get("install_ready") is not False):
            _fail("Geometría de fijación no es nominal y bloqueada")
        try:
            key = (_identity(pair.get("group_id"), "group_id"),
                   _identity(pair.get("module_id"), "module_id"))
        except WallFixationError:
            _fail("Identidad de fijación duplicada o inválida")
        if key in seen:
            _fail("Identidad de fijación duplicada o inválida")
        seen.add(key)
        params = pair.get("parameters")
        if (type(params) is not dict or set(params) != {
                "length_mm", "section_height_mm", "thickness_mm",
                "base_y_from_carcass_mm", "rear_clearance_mm",
                "confirm_external_clearance"}
                or any(type(params.get(field)) is not int or params[field] < minimum
                       or params[field] > 20000
                       for field, minimum in _INT_FIELDS.items())
                or params.get("confirm_external_clearance") is not True
                or params["section_height_mm"] < params["thickness_mm"] + 2
                or params["rear_clearance_mm"] < params["thickness_mm"]):
            _fail("Parámetros de fijación nominal no válidos")
        profiles = pair.get("profiles")
        if type(profiles) is not list or len(profiles) != 2:
            _fail("Cada pareja francesa requiere dos perfiles nominales")
        for profile, expected_role in zip(profiles, _PROFILE_ROLES):
            if type(profile) is not dict:
                _fail("Perfil francés requiere un objeto de geometría")
            vertices, faces = profile.get("vertices_xyz_mm"), profile.get("faces")
            expected_id = f"WALLFIX:{key[0]}:{key[1]}:{expected_role.upper()}"
            if (profile.get("id") != expected_id or profile.get("role") != expected_role
                    or type(vertices) is not list or len(vertices) != 8
                    or type(faces) is not list or len(faces) != 6
                    or any(type(point) is not list or len(point) != 3
                           or any(type(v) is not int or not 0 <= v <= 20000 for v in point)
                           for point in vertices)
                    or any(type(face) is not list or len(face) != 4
                           or any(type(index) is not int or not 0 <= index < 8 for index in face)
                           for face in faces)):
                _fail("Perfil francés requiere 8 vértices XYZ y 6 caras cuadrangulares")
        sections = pair.get("section_vertices_yz_mm")
        if (type(sections) is not dict or set(sections) != set(_PROFILE_ROLES)
                or any(type(sections[role]) is not list or len(sections[role]) != 4
                       or any(type(point) is not list or len(point) != 2
                              or any(type(value) is not int or value < 0 for value in point)
                              for point in sections[role]) for role in _PROFILE_ROLES)):
            _fail("Secciones YZ francesas no válidas")
        reserve = pair.get("clearance_reservation")
        if (type(reserve) is not dict or type(reserve.get("origin_xyz_mm")) is not list
                or type(reserve.get("size_xyz_mm")) is not list
                or len(reserve["origin_xyz_mm"]) != 3 or len(reserve["size_xyz_mm"]) != 3
                or any(type(v) is not int or not 0 <= v <= 20000 for v in reserve["origin_xyz_mm"])
                or any(type(v) is not int or v <= 0 for v in reserve["size_xyz_mm"])):
            _fail("Reserva posterior francesa inválida")
    return geometry


def append_section_detail(svg_text: str, geometry: list[dict[str, Any]]) -> str:
    if not geometry:
        return svg_text
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    root = ET.fromstring(svg_text)
    view = [float(value) for value in root.attrib["viewBox"].split()]
    old_height = view[3]
    scale = 2.0
    row_height = 235
    extra = 70 + row_height * len(geometry)
    view[3] += extra
    root.set("viewBox", " ".join(str(int(v)) for v in view))
    root.set("height", str(int(view[3])))
    ns = "http://www.w3.org/2000/svg"
    group = ET.SubElement(root, f"{{{ns}}}g", {"data-wall-fixation-detail": "nominal"})
    ET.SubElement(group, f"{{{ns}}}text", {"x": "30", "y": str(int(old_height + 32)),
                  "font-family": "Arial,sans-serif", "font-size": "19", "font-weight": "bold",
                  "fill": "#a11c1c"}).text = (
                      "DETALLE VERTICAL YZ · FRANCÉS 45° · ESCALA ESQUEMÁTICA 2 px/mm · NO INSTALABLE")
    colors = {"french_cleat_cabinet": "#247a93", "french_cleat_wall": "#d08b27"}
    for index, pair in enumerate(geometry):
        y_top = old_height + 65 + index * row_height
        title = f"{pair['group_id']} · {pair['module_id']} — contacto nominal; reserva/pared/unión sin verificar"
        ET.SubElement(group, f"{{{ns}}}text", {"x": "40", "y": str(int(y_top + 16)),
                      "font-family": "Arial,sans-serif", "font-size": "15", "fill": "#1e293b"}).text = title
        for profile in pair["profiles"]:
            points = pair["section_vertices_yz_mm"][profile["role"]]
            polygon_points = " ".join(
                f"{40 + z * scale},{int(y_top + 205 - y * scale)}"
                for z, y in points
            )
            ET.SubElement(group, f"{{{ns}}}polygon", {
                "points": polygon_points, "fill": colors[profile["role"]],
                "fill-opacity": "0.72", "stroke": "#17323e", "stroke-width": "2",
                "data-profile-id": profile["id"],
            })
        ET.SubElement(group, f"{{{ns}}}text", {"x": "90", "y": str(int(y_top + 90)),
                      "font-family": "Arial,sans-serif", "font-size": "12", "fill": "#17323e"}).text = "perfil mueble"
        ET.SubElement(group, f"{{{ns}}}text", {"x": "90", "y": str(int(y_top + 180)),
                      "font-family": "Arial,sans-serif", "font-size": "12", "fill": "#17323e"}).text = "perfil muro"
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)
