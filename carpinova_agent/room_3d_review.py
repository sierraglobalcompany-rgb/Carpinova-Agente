"""D18: offline 3D nominal viewer of already verified room_layout_v1 CAD boxes.

The CLI accepts only the original module specifications and rebuilds the room
via Maestro/F6/CADExchange. It never accepts untrusted caller-provided boxes,
modifies parts, or grants cutting/fabrication authority.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready",
          "purchase_ready", "can_generate_f7c")
_SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_:.-]{0,100}$")
_MAX_SIZE = 256_000


class RoomViewerError(ValueError):
    """Untrusted or incomplete nominal room cannot be shown as verified."""


def _vec(raw: Any, name: str, *, positive: bool = False) -> list[int]:
    if (type(raw) is not list or len(raw) != 3
            or any(type(v) is not int or v < (1 if positive else 0)
                   or v > 20000 for v in raw)):
        raise RoomViewerError(f"{name}: se necesitan 3 milímetros enteros válidos")
    return raw


def _record_id(value: Any, label: str) -> str:
    if type(value) is not str or not _SAFE_ID.fullmatch(value):
        raise RoomViewerError(f"{label}: identificador inválido")
    return value


def _payload(review: Any) -> dict[str, Any]:
    if (type(review) is not dict or review.get("review_kind") != "room_layout_v1"
            or review.get("status") not in {"REVIEW_ONLY", "INTERFERENCE_REVIEW_REQUIRED"}
            or any(review.get(flag) is not False for flag in _FLAGS)):
        raise RoomViewerError("La escena requiere room_layout_v1 con permisos físicos false")
    groups = review.get("groups")
    boxes = review.get("world_boxes")
    if (type(groups) is not list or not 1 <= len(groups) <= 6
            or type(boxes) is not list or not 1 <= len(boxes) <= 432
            or review.get("piece_count") != len(boxes)):
        raise RoomViewerError("Conjunto CAD incompleto o excedido")
    group_ids: set[str] = set()
    clean_groups = []
    group_bounds = {}
    for item in groups:
        if type(item) is not dict:
            raise RoomViewerError("Grupo inválido")
        gid = _record_id(item.get("group_id"), "group_id")
        if gid in group_ids:
            raise RoomViewerError("Grupos duplicados")
        group_ids.add(gid)
        origin = _vec(item.get("origin_xyz_mm"), "origen de grupo")
        size = _vec(item.get("bounds_xyz_mm"), "volumen de grupo", positive=True)
        if any(origin[i] + size[i] > 20000 for i in range(3)):
            raise RoomViewerError("Grupo fuera de límites")
        group_bounds[gid] = (origin, size)
        clean_group = {"id": gid, "origin": origin, "size": size}
        if "rotation_deg" in item:
            rotation = item["rotation_deg"]
            if type(rotation) is not int or rotation not in {0, 90, 180, 270}:
                raise RoomViewerError("Rotación de grupo inválida")
            clean_group["rotation"] = rotation
        clean_groups.append(clean_group)
    seen: set[str] = set()
    clean_boxes = []
    by_group = {gid: 0 for gid in group_ids}
    for item in boxes:
        if type(item) is not dict:
            raise RoomViewerError("Panel CAD inválido")
        gid = _record_id(item.get("group_id"), "group_id de panel")
        pid = _record_id(item.get("piece_id"), "piece_id")
        role = _record_id(item.get("role"), "rol")
        if gid not in group_ids or pid in seen:
            raise RoomViewerError("Panel sin grupo válido o identificador duplicado")
        seen.add(pid)
        origin = _vec(item.get("origin_xyz_mm"), "origen de panel")
        size = _vec(item.get("size_xyz_mm"), "volumen de panel", positive=True)
        base, bounds = group_bounds[gid]
        if any(origin[i] < base[i] or origin[i] + size[i] > base[i] + bounds[i]
               for i in range(3)):
            raise RoomViewerError("Panel CAD fuera de la envolvente verificada")
        by_group[gid] += 1
        clean_box = {"id": pid, "group": gid, "role": role,
                     "origin": origin, "size": size}
        if "module_id" in item:
            clean_box["module_id"] = _record_id(item["module_id"], "module_id de panel")
        clean_boxes.append(clean_box)
    if any(item.get("piece_count") != by_group[item["group_id"]]
           for item in groups):
        # Existing room_layout_v1 includes group piece counts; refuse discrepancy.
        raise RoomViewerError("El conteo de paneles por grupo no corresponde")
    construction = review.get("construction_review_by_group", {})
    if type(construction) is not dict or set(construction) - group_ids:
        raise RoomViewerError("Resumen de fondo y soporte inválido")
    valid_back = {"none", "pending", "inset_full", "inset_two_strips",
                  "unconfirmed", "mixed"}
    valid_support = {"REAR_WALL_SUPPORT_PENDING", "SUPPORT_PENDING",
                     "NOT_APPLICABLE", "mixed"}
    for group in clean_groups:
        item = construction.get(group["id"])
        if item is None:
            continue
        if (type(item) is not dict
                or set(item) != {"back_status", "wall_support_status",
                                 "wall_tie_mode", "install_ready", "module_count"}
                or type(item.get("back_status")) is not str
                or item.get("back_status") not in valid_back
                or type(item.get("wall_support_status")) is not str
                or item.get("wall_support_status") not in valid_support
                or type(item.get("wall_tie_mode")) is not str
                or item.get("wall_tie_mode") not in {
                    "NOT_IMPLEMENTED", "NOT_APPLICABLE",
                    "DIRECT_PAIR_CONCEPT_ONLY_UNVERIFIED"}
                or item.get("install_ready") is not False
                or type(item.get("module_count")) is not int
                or not 1 <= item["module_count"] <= 6):
            raise RoomViewerError("Resumen de fondo y soporte inseguro")
        group["construction"] = item

    drawer_suffix = {
        "drawer_side_left": "SIDE_LEFT",
        "drawer_side_right": "SIDE_RIGHT",
        "drawer_front_wall": "FRONT_WALL",
        "drawer_rear_wall": "REAR_WALL",
        "drawer_bottom": "BOTTOM",
        "drawer_facade": "FACADE",
    }
    drawer_groups: dict[str, list[dict[str, Any]]] = {}
    blocked_drawers: list[dict[str, str]] = []
    for box in clean_boxes:
        if not box["role"].startswith("drawer_") and "-DRAWER_" not in box["id"]:
            continue
        if "-DRAWER_" not in box["id"]:
            blocked_drawers.append({"id": box["id"], "group": box["group"],
                                    "reason": "ID sin separador -DRAWER_"})
            continue
        prefix, _suffix = box["id"].rsplit("-DRAWER_", 1)
        drawer_groups.setdefault(prefix, []).append(box)
    drawers = []
    expected_roles = set(drawer_suffix)
    for drawer_id, parts in sorted(drawer_groups.items()):
        role_counts = {role: sum(part["role"] == role for part in parts)
                       for role in expected_roles}
        groups_for_drawer = {part["group"] for part in parts}
        valid = (
            len(parts) == 6
            and len(groups_for_drawer) == 1
            and set(part["role"] for part in parts) == expected_roles
            and all(part["id"] == drawer_id + "-DRAWER_" + drawer_suffix[part["role"]]
                    for part in parts)
            and all(count == 1 for count in role_counts.values())
        )
        if not valid:
            blocked_drawers.append({
                "id": drawer_id,
                "group": next(iter(groups_for_drawer)) if len(groups_for_drawer) == 1 else "",
                "reason": "Se requieren seis roles e IDs originales distintos del mismo cajón",
            })
            continue
        min_z = min(part["origin"][2] for part in parts)
        max_z = max(part["origin"][2] + part["size"][2] for part in parts)
        if max_z <= min_z:
            blocked_drawers.append({"id": drawer_id, "group": parts[0]["group"],
                                    "reason": "Profundidad nominal inválida"})
            continue
        match = re.search(r"-(D[0-9]+)$", drawer_id)
        drawers.append({
            "id": drawer_id,
            "label": match.group(1) if match else drawer_id,
            "group": parts[0]["group"],
            "piece_ids": sorted(part["id"] for part in parts),
            "depth_mm": max_z - min_z,
        })
    zones = review.get("service_zones")
    if type(zones) is not list or len(zones) > 12:
        raise RoomViewerError("Reservas de servicio inválidas")
    clean_zones = []
    for item in zones:
        if type(item) is not dict:
            raise RoomViewerError("Zona inválida")
        clean_zones.append({"id": _record_id(item.get("zone_id"), "zona"),
                            "origin": _vec(item.get("origin_xyz_mm"), "origen zona"),
                            "size": _vec(item.get("size_xyz_mm"), "tamaño zona", positive=True)})
    warnings = review.get("warnings")
    if type(warnings) is not list or any(type(w) is not str or len(w) > 180
                                          for w in warnings):
        raise RoomViewerError("Advertencias inválidas")
    if not isinstance(review.get("layout_sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", review["layout_sha256"]):
        raise RoomViewerError("Firma del layout inválida")
    payload = {"groups": clean_groups, "boxes": clean_boxes, "drawers": drawers,
               "blocked_drawers": blocked_drawers, "zones": clean_zones,
               "warnings": warnings, "status": review["status"],
               "digest": review["layout_sha256"]}
    if "module_index" not in review:
        if "wall_review_by_module" in review:
            raise RoomViewerError("Selección de pared sin índice de módulos")
        return payload

    from .room_spatial import (
        _BACK_CHOICES, _BOOK_EVIDENCE, _SUPPORT_CHOICES, _WALL_CANDIDATE_ROLES,
        _WALL_SUBSTRATES, _WALL_SYSTEMS, _WALL_REVISION_FIELDS,
    )
    boxes_by_ref = {(box["group"], box["id"]): box for box in clean_boxes}
    raw_index = review.get("module_index")
    index_fields = {
        "group_id", "module_id", "piece_ids", "candidate_piece_ids", "bounds_origin_xyz_mm",
        "bounds_size_xyz_mm", "installation_mode", "support_status",
        "selection_enabled",
    }
    if type(raw_index) is not list or not 1 <= len(raw_index) <= 72:
        raise RoomViewerError("Índice de módulos inválido")
    modules_by_key, owners, clean_index = {}, {}, []
    for item in raw_index:
        if type(item) is not dict or set(item) != index_fields:
            raise RoomViewerError("Entrada de índice de módulos no admitida")
        gid = _record_id(item.get("group_id"), "module_index.group_id")
        mid = _record_id(item.get("module_id"), "module_index.module_id")
        key = (gid, mid)
        piece_ids = item.get("piece_ids")
        if (gid not in group_ids or key in modules_by_key
                or type(piece_ids) is not list or not piece_ids
                or item.get("selection_enabled") is not True
                or item.get("installation_mode") not in {
                    "wall_mounted", "freestanding", "unknown"}
                or type(item.get("support_status")) is not str):
            raise RoomViewerError("Identidad o selección de módulo inválida")
        origin = _vec(item.get("bounds_origin_xyz_mm"), "module_index.origen")
        size = _vec(item.get("bounds_size_xyz_mm"), "module_index.tamaño", positive=True)
        if any(origin[i] + size[i] > 20000 for i in range(3)):
            raise RoomViewerError("Módulo fuera de límites")
        ids = [_record_id(pid, "module_index.piece_id") for pid in piece_ids]
        if len(ids) != len(set(ids)):
            raise RoomViewerError("Piezas duplicadas en module_index")
        candidates = item.get("candidate_piece_ids")
        if type(candidates) is not list:
            raise RoomViewerError("Candidatos de unión inválidos")
        candidate_ids = [_record_id(pid, "module_index.candidate_piece_id")
                         for pid in candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise RoomViewerError("Candidatos de unión duplicados")
        module_boxes = []
        for pid in ids:
            box = boxes_by_ref.get((gid, pid))
            if box is None or box.get("module_id") != mid or pid in owners:
                raise RoomViewerError("module_index no concilia con piezas reales")
            owners[pid] = key
            module_boxes.append(box)
        expected_candidates = sorted(
            box["id"] for box in module_boxes
            if box["role"] in _WALL_CANDIDATE_ROLES
        )
        if candidate_ids != expected_candidates:
            raise RoomViewerError("Candidatos no concilian con roles reales del módulo")
        lows = [min(box["origin"][axis] for box in module_boxes) for axis in range(3)]
        highs = [max(box["origin"][axis] + box["size"][axis]
                     for box in module_boxes) for axis in range(3)]
        if lows != origin or [highs[i] - lows[i] for i in range(3)] != size:
            raise RoomViewerError("Envolvente del módulo no coincide con world_boxes")
        modules_by_key[key] = ids
        clean_index.append({
            "group_id": gid, "module_id": mid, "piece_ids": ids,
            "candidate_piece_ids": candidate_ids,
            "bounds_origin_xyz_mm": origin, "bounds_size_xyz_mm": size,
            "installation_mode": item["installation_mode"],
            "support_status": item["support_status"], "selection_enabled": True,
        })
    if set(owners) != {pid for _gid, pid in boxes_by_ref}:
        raise RoomViewerError("module_index no cubre todos los paneles exactamente")

    raw_reviews = review.get("wall_review_by_module")
    if type(raw_reviews) is not list:
        raise RoomViewerError("Selección de pared debe ser una lista, incluso vacía")
    review_fields = _WALL_REVISION_FIELDS | {
        "support_function", "selection_status", "status", "constraints",
        "candidate_piece_ids", "book_evidence", "install_ready",
        "manufacturing_holes", "back_geometry_status", "support_actual",
        "support_review_status",
    }
    statuses = {"SELECTABLE_CONCEPT_ONLY", "MODELED_NOMINAL", "NEEDS_BACK_SPEC",
                "INCOMPATIBLE_FOR_SUSPENSION", "NEEDS_DATA"}
    back_statuses = {"MODELED_NOMINAL", "NEEDS_BACK_SPEC",
                     "BACK_GEOMETRY_PENDING", "NEEDS_DATA"}
    clean_reviews, seen_reviews = [], set()
    intent_fields = ("group_id", "module_id", "back_choice", "wall_system",
                     "support_choice", "wall_substrate")
    for item in raw_reviews:
        if type(item) is not dict or set(item) != review_fields:
            raise RoomViewerError("Revisión de pared con esquema inválido")
        gid = _record_id(item.get("group_id"), "wall_review.group_id")
        mid = _record_id(item.get("module_id"), "wall_review.module_id")
        key = (gid, mid)
        if (key not in modules_by_key or key in seen_reviews
                or item.get("back_choice") not in _BACK_CHOICES
                or item.get("wall_system") not in _WALL_SYSTEMS
                or item.get("support_choice") not in _SUPPORT_CHOICES
                or item.get("wall_substrate") not in _WALL_SUBSTRATES
                or item.get("support_function") not in {
                    "wall_suspension", "stability_only", "not_applicable", "pending"}
                or item.get("selection_status") != "SELECTABLE_CONCEPT_ONLY"
                or item.get("status") not in statuses
                or item.get("back_geometry_status") not in back_statuses
                or item.get("support_review_status") not in {
                    "AS_DECLARED", "SUPPORT_CHOICE_PENDING"}
                or type(item.get("support_actual")) is not str
                or not item.get("support_actual")
                or item.get("install_ready") is not False
                or item.get("manufacturing_holes") != []):
            raise RoomViewerError("Elección de pared insegura o duplicada")
        constraints, candidates, evidence = (item.get("constraints"),
                                              item.get("candidate_piece_ids"),
                                              item.get("book_evidence"))
        if (type(constraints) is not list or any(
                type(value) is not str or not re.fullmatch(r"[A-Z0-9_]{1,80}", value)
                for value in constraints)
                or type(candidates) is not list
                or candidates != next(value["candidate_piece_ids"]
                                      for value in clean_index
                                      if (value["group_id"], value["module_id"]) == key)
                or type(evidence) is not list):
            raise RoomViewerError("Evidencia o límites de pared inválidos")
        for source in evidence:
            if (type(source) is not dict or set(source) != {
                    "content_id", "pdf_page", "printed_page", "review_status"}
                    or source.get("review_status") != "VISUALLY_VERIFIED"
                    or type(source.get("pdf_page")) is not int
                    or type(source.get("printed_page")) is not int):
                raise RoomViewerError("Referencia de libro inválida")
        if evidence != _BOOK_EVIDENCE.get(item["wall_system"], []):
            raise RoomViewerError("Referencia de libro no conciliable")
        seen_reviews.add(key)
        clean_reviews.append({name: item[name] for name in intent_fields} | {
            "support_function": item["support_function"],
            "back_geometry_status": item["back_geometry_status"],
            "support_actual": item["support_actual"],
            "support_review_status": item["support_review_status"],
            "selection_status": item["selection_status"], "status": item["status"],
            "constraints": list(constraints), "candidate_piece_ids": list(candidates),
            "book_evidence": evidence, "install_ready": False,
            "manufacturing_holes": [],
        })
    if (review.get("manufacturing_holes") != [] or review.get("release") != "NO_GO"
            or any(review.get(flag) is not False for flag in _FLAGS)):
        raise RoomViewerError("La revisión de pared habilitó una salida física")
    payload["module_index"] = sorted(
        clean_index, key=lambda value: (value["group_id"], value["module_id"])
    )
    payload["wall_reviews"] = sorted(
        clean_reviews, key=lambda value: (value["group_id"], value["module_id"])
    )
    if "support_reservations" in review:
        raw_reservations = review.get("support_reservations")
        raw_collisions = review.get("support_collisions")
        reservation_fields = {"group_id", "module_id", "style", "support_height_mm",
                              "origin_xyz_mm", "size_xyz_mm", "selectable", "status"}
        if type(raw_reservations) is not list or type(raw_collisions) is not list:
            raise RoomViewerError("Reservas conceptuales M6 inválidas")
        clean_reservations = []
        seen_reservations = set()
        for item in raw_reservations:
            if type(item) is not dict or set(item) != reservation_fields:
                raise RoomViewerError("Reserva conceptual con esquema inválido")
            gid = _record_id(item.get("group_id"), "support_reservation.group_id")
            mid = _record_id(item.get("module_id"), "support_reservation.module_id")
            key = (gid, mid)
            if (key not in modules_by_key or key in seen_reservations
                    or item.get("style") not in {"legs", "plinth"}
                    or type(item.get("support_height_mm")) is not int
                    or item["support_height_mm"] <= 0
                    or item.get("selectable") is not False
                    or item.get("status") != "CONCEPTUAL_RESERVATION_NOT_PHYSICAL_PARTS"):
                raise RoomViewerError("Reserva de apoyo contradictoria o seleccionable")
            origin = _vec(item.get("origin_xyz_mm"), "support_reservation.origin")
            size = _vec(item.get("size_xyz_mm"), "support_reservation.size", positive=True)
            if size[1] != item["support_height_mm"] or any(
                    origin[i] + size[i] > 20000 for i in range(3)):
                raise RoomViewerError("Envolvente conceptual fuera de límites")
            seen_reservations.add(key)
            clean_reservations.append({
                **{field: item[field] for field in ("group_id", "module_id", "style",
                    "support_height_mm", "selectable", "status")},
                "origin_xyz_mm": origin, "size_xyz_mm": size,
            })
        if raw_collisions:
            raise RoomViewerError("La reserva conceptual intersecta otra zona; no se puede editar")
        payload["support_reservations"] = sorted(
            clean_reservations, key=lambda item: (item["group_id"], item["module_id"])
        )
    if "module_edit_index" in review:
        raw_edits = review.get("module_edit_index")
        edit_fields = {
            "group_id", "module_id", "width_mm", "overall_height_mm",
            "carcass_height_mm", "carcass_depth_mm",
            "assembled_external_depth_mm", "support_style",
            "support_height_mm", "editable_fields", "edit_block_reason",
        }
        styles = {"floor_direct", "legs", "plinth", "wall_mounted"}
        editable = {"width_mm", "overall_height_mm", "carcass_depth_mm",
                    "support_style", "support_height_mm"}
        if type(raw_edits) is not list or len(raw_edits) != len(clean_index):
            raise RoomViewerError("Índice dimensional M6 incompleto")
        clean_edits, seen_edits = [], set()
        for item in raw_edits:
            if type(item) is not dict or set(item) != edit_fields:
                raise RoomViewerError("Entrada dimensional M6 con esquema inválido")
            gid = _record_id(item.get("group_id"), "module_edit_index.group_id")
            mid = _record_id(item.get("module_id"), "module_edit_index.module_id")
            key = (gid, mid)
            if key not in modules_by_key or key in seen_edits:
                raise RoomViewerError("Identidad dimensional M6 inexistente o duplicada")
            seen_edits.add(key)
            for field in ("width_mm", "overall_height_mm", "carcass_height_mm",
                          "carcass_depth_mm", "assembled_external_depth_mm"):
                if type(item.get(field)) is not int or not 1 <= item[field] <= 20000:
                    raise RoomViewerError(f"{field} dimensional M6 inválido")
            if (item.get("support_style") not in styles
                    or type(item.get("support_height_mm")) is not int
                    or not 0 <= item["support_height_mm"] <= 20000
                    or item["overall_height_mm"] != item["carcass_height_mm"] + item["support_height_mm"]
                    or type(item.get("editable_fields")) is not list
                    or any(type(field) is not str for field in item["editable_fields"])
                    or len(item["editable_fields"]) != len(set(item["editable_fields"]))
                    or not set(item["editable_fields"]) <= editable
                    or type(item.get("edit_block_reason")) is not str):
                raise RoomViewerError("Valores o permisos dimensionales M6 inválidos")
            clean_edits.append({key: item[key] for key in edit_fields})
        if seen_edits != set(modules_by_key):
            raise RoomViewerError("Índice dimensional M6 no cubre los módulos existentes")
        payload["module_edit_index"] = sorted(
            clean_edits, key=lambda item: (item["group_id"], item["module_id"])
        )
    return payload


# Client-side isometric projection uses only verified world_boxes. No CDN,
# external assets, analytics, network calls, scripts or manufacturing endpoints.
_HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CarpiNova · Inspector nominal 3D sin conexión</title>
<style>
:root{font-family:system-ui,"Segoe UI",sans-serif;color:#172b3a;background:#edf2f4;line-height:1.45}
*{box-sizing:border-box}body{margin:0;min-width:0}.top{padding:20px clamp(16px,3vw,36px);background:#163746;color:#f3f7f8;border-bottom:4px solid #d9a441}
h1{font-size:clamp(20px,2.4vw,28px);line-height:1.2;margin:0 0 8px}.sub{font-size:13px;color:#d1e0e4;margin:4px 0}.notice{color:#ffdc91}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:10px;padding:14px clamp(12px,2vw,24px);background:#fff;border-bottom:1px solid #cad5d9}
.summary-card{min-width:0;border-left:3px solid #21758a;padding:7px 10px;background:#f5f8f8;overflow-wrap:anywhere}.summary-card strong{display:block;font-size:12px;color:#375464}.summary-card span{font-size:14px;font-variant-numeric:tabular-nums}
main{display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,360px);min-height:calc(100vh - 180px)}
.stage-wrap{min-width:0;padding:14px}.stage{min-height:500px;background:radial-gradient(circle at 42% 20%,#315469,#102530 82%);border-radius:10px;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}
#scene{display:block;width:100%;height:min(72vh,820px);min-height:460px;touch-action:pan-y;cursor:grab;user-select:none}
.stage.dragging #scene{cursor:grabbing}
.stage-caption{font-size:12px;color:#526774;margin:9px 3px}.sidebar{background:#f6f8f8;border-left:1px solid #cad5d9;padding:14px;display:flex;flex-direction:column;gap:12px;min-width:0}
fieldset{margin:0;min-width:0;border:1px solid #c4d1d5;border-radius:8px;padding:11px;background:#fff}legend{font-weight:700;font-size:14px;padding:0 4px}
button{background:#e6eef0;color:#183745;border:1px solid #91a9b1;border-radius:6px;padding:8px 10px;cursor:pointer;margin:3px 4px 3px 0;font:inherit;font-size:13px}
button[aria-pressed=true]{background:#176b7d;border-color:#176b7d;color:#fff}button:hover{background:#d5e4e7}button[aria-pressed=true]:hover{background:#12596a}
select,input[type=number]{max-width:100%;width:100%;padding:8px;background:#fff;color:#17333f;border:1px solid #829aa2;border-radius:6px;font:inherit}button:focus-visible,input:focus-visible,select:focus-visible,svg polygon:focus-visible{outline:3px solid #c17c00;outline-offset:2px}
label{display:block;font-size:13px;margin:8px 0}.control-line{display:flex;align-items:flex-start;gap:8px}.control-line input{margin-top:4px;flex:0 0 auto}.control-note{display:block;color:#526974;font-size:12px;margin:4px 0}
#details{background:#f1f5f6;border:1px solid #d8e0e2;border-radius:7px;padding:10px;min-height:90px;overflow-wrap:anywhere;font-size:13px;white-space:pre-line}
.tag{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#9ed1dc}svg polygon{cursor:pointer;stroke:#15313c;stroke-width:1.1;vector-effect:non-scaling-stroke}
svg polygon:focus-visible,svg polygon.selected{stroke:#f5bc3d;stroke-width:3;outline:none}
svg text{font-family:system-ui,sans-serif;fill:#eef5f5;font-size:11px;paint-order:stroke;stroke:#102530;stroke-width:3}
.warn{border-left:3px solid #bd7c15;padding:7px 9px;background:#fff7e5;color:#624719;font-size:12px;overflow-wrap:anywhere}
.open-controls{margin:10px 0;background:#f5fafb}.door-control,.drawer-control{margin:8px 0;padding:6px 0;border-bottom:1px solid #d9e4e8}.door-control input[type=range],.drawer-control input[type=range]{width:100%}.door-control output,.drawer-control output{font-variant-numeric:tabular-nums;color:#0e6978;font-weight:700}
.interior-banner{padding:9px;border-radius:6px;background:#fff2cc;color:#624719;font-size:12px;font-weight:700}.empty-note{font-size:12px;color:#526974}
@media(max-width:850px){main{grid-template-columns:minmax(0,1fr)}.sidebar{border-left:0;border-top:1px solid #cad5d9}.stage-wrap{padding:10px}.stage{min-height:390px}#scene{min-height:370px;height:58vh}}
@media(max-width:420px){.summary{grid-template-columns:minmax(0,1fr)}.stage{min-height:340px}#scene{min-height:320px;height:48vh}.sidebar{padding:10px}.views{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}.views button{padding:7px 3px;margin:2px 2px 2px 0}}
</style></head><body>
<header class="top"><h1>CarpiNova · VISOR NOMINAL SIN AUTORIZACIÓN DE FABRICACIÓN</h1>
<p class="sub"><strong class="notice">Ejemplo de revisión, no proyecto para fabricar</strong> · Vista geométrica 2.5D simplificada · 100 % sin conexión</p>
<p class="sub">Estado <span id="status"></span> · SHA de escena <span id="digest" class="tag"></span></p></header>
<section class="summary" aria-label="Resumen dimensional de revisión">
<div class="summary-card"><strong>Conjunto nominal</strong><span id="sceneName"></span></div>
<div class="summary-card"><strong>Envolvente CAD global</strong><span id="globalBounds"></span></div>
<div class="summary-card"><strong>Paneles nominales</strong><span id="sceneCount"></span></div>
<div class="summary-card"><strong>Grupos</strong><span id="groupSummary"></span></div>
</section>
<main><section class="stage-wrap"><div class="stage"><svg id="scene" role="img" aria-label="Vista nominal simplificada 2.5D; no valida ensamble" viewBox="0 0 900 640"></svg></div>
<p class="stage-caption"><strong>Arrastra sobre el mueble para girar · rueda para ampliar.</strong> La proyección puede simplificar oclusiones y uniones. Cambiar la vista solo mueve la cámara; no modifica piezas ni valida el ensamble.</p></section>
<aside class="sidebar"><fieldset><legend>Vista y controles visuales</legend><span class="control-note">Orientación — solo cámara</span><div id="views" class="views"></div>
<span id="cameraReadout" class="control-note" aria-live="polite">Giro 0° · Elevación 35°</span>
<label class="control-line"><input type="checkbox" id="interior"><span>Inspeccionar interior (oculta frentes de puertas; conserva tapas y repisas)</span></label>
<fieldset id="openingGroup" class="open-controls"><legend>Abrir puertas nominales</legend>
<div id="doorSliders"></div><div id="noDoors" class="empty-note" hidden>Esta escena no tiene puertas abatibles con lados identificables.</div>
<div id="drawerSliders"></div><div id="noDrawers" class="empty-note" hidden>Este ejemplo no contiene cajones completos para abrir.</div>
<div id="blockedDrawers" class="empty-note" hidden></div>
<div class="control-note">Movimiento visual ilustrativo (0–90°). Sin bisagras, holguras de giro ni cargas verificadas. No altera las piezas CAD.</div>
<div class="control-note">Apertura de cajón nominal e ilustrativa; no valida riel, cargas, colisiones dinámicas, holguras ni perforaciones.</div>
</fieldset>
<div id="interiorBanner" class="interior-banner" hidden>VISTA INTERIOR: solo se ocultan visualmente los frentes de puertas; tapas, bases, repisas, laterales, fondos y piezas drawer_* permanecen en escena y en los datos.</div>
<div id="noShelf" class="empty-note" hidden>Este modelo no contiene repisa.</div>
<label for="cutEnabled" class="control-line"><input type="checkbox" id="cutEnabled"><span id="cutState">Corte OFF</span></label>
<label for="cutHeight">Altura límite Y (mm)<input type="number" id="cutHeight" step="1" min="0" disabled></label>
<span class="control-note">Corte de visualización simplificada; no altera el modelo.</span>
<label for="zoom">Ampliación <output id="zoomLabel">100 %</output><input type="range" min="60" max="160" step="10" value="100" id="zoom"></label>
<label id="zoneControl" for="zones" hidden><input type="checkbox" checked id="zones"> Mostrar reservas de servicio (no son perforaciones)</label>
<button type="button" id="resetView">Restablecer vista completa</button></fieldset>
<fieldset><legend>Grupos visibles</legend><div id="groups"></div></fieldset>
<fieldset><legend>Panel seleccionado</legend><label for="piecePicker">Elegir tablero (incluye los ocultos)</label><select id="piecePicker"></select><div id="details" aria-live="polite">Selecciona un tablero para ver sus medidas nominales.</div></fieldset>
<div class="warn"><strong>APERTURA VISUAL NOMINAL · NO FABRICAR / NO CORTAR / NO PERFORAR / NO COMPRAR.</strong> La proyección y aperturas son ILUSTRATIVAS, no CAD sólido ni plano de fabricación. No validan bisagras, correderas, cargas, anclajes, holguras dinámicas, instalación ni accesibilidad física. Las reservas no crean agujeros.</div>
<div id="warnings" class="warn"></div></aside></main>
<script id="scene-data" type="application/json">__SCENE_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('scene-data').textContent);
const NS='http://www.w3.org/2000/svg'; const svg=document.getElementById('scene');
const cutEnabled=document.getElementById('cutEnabled'),cutHeight=document.getElementById('cutHeight'),zoom=document.getElementById('zoom');
const INITIAL_ELEVATION=35;
let yaw=0,elevation=INITIAL_ELEVATION,activePreset=0,selected='',shown=new Set(data.groups.map(g=>g.id));
const doorAngles=new Map(),drawerProgress=new Map(),drawerByPiece=new Map();
for(const drawer of data.drawers){for(const id of drawer.piece_ids)drawerByPiece.set(id,drawer)}
const E=(tag,attrs,text)=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs||{}))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n};
const palette=(role)=>role.startsWith('front_')||role==='drawer_facade'?['#b98a50','#d8ad72','#f5d5a0']:role.startsWith('back_')?['#5d8470','#83ac8b','#a9d1ae']:role.includes('tie')?['#607aab','#839fd0','#a9c2e6']:['#467b91','#6ca6bc','#a8d4df'];
const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
const normalizeYaw=value=>((value%360)+360)%360;
const cameraState=()=>{const az=(45-yaw)*Math.PI/180,el=elevation*Math.PI/180,ce=Math.cos(el),se=Math.sin(el);return {position:[Math.sin(az)*ce,se,-Math.cos(az)*ce],right:[Math.cos(az),0,Math.sin(az)],up:[-Math.sin(az)*se,ce,Math.cos(az)*se]}};
const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const P=(x,y,z)=>{const c=cameraState(),d=[x-pivot[0],y-pivot[1],z-pivot[2]];return [dot(c.right,d),-dot(c.up,d)]};
const ROLE_LABEL={front_left:'puerta izquierda nominal',front_right:'puerta derecha nominal',front_corner_blind:'panel ciego NO puerta',front_corner_access:'puerta nominal sin bisagra validada',shelf_horizontal:'repisa',top:'tapa',bottom:'base',left_side:'lateral izquierdo',right_side:'lateral derecho',back_full:'fondo completo'};
const labelRole=role=>ROLE_LABEL[role]||role;
const maxHeight=Math.max(...data.groups.map(g=>g.origin[1]+g.size[1]));
cutHeight.max=String(maxHeight);cutHeight.value=String(maxHeight);
const mins=[0,1,2].map(i=>Math.min(...data.groups.map(g=>g.origin[i])));
const maxs=[0,1,2].map(i=>Math.max(...data.groups.map(g=>g.origin[i]+g.size[i])));
const pivot=mins.map((value,i)=>(value+maxs[i])/2);
// Keep a fixed camera frame that includes door swings and the conservative visual drawer travel.
const frameMin=mins.slice(),frameMax=maxs.slice();
const includeFramePoint=point=>{for(let i=0;i<3;i++){frameMin[i]=Math.min(frameMin[i],point[i]);frameMax[i]=Math.max(frameMax[i],point[i])}};
for(const box of data.boxes.filter(item=>item.role==='front_left'||item.role==='front_right')){
 const [x,y,z]=box.origin,[w,h,d]=box.size,isLeft=box.role==='front_left',hx=isLeft?x:x+w,hz=z+d/2,turn=isLeft?1:-1;
 for(const xx of [x,x+w])for(const yy of [y,y+h])for(const zz of [z,z+d])for(let deg=0;deg<=90;deg++){
  const a=turn*deg*Math.PI/180,c=Math.cos(a),s=Math.sin(a),dx=xx-hx,dz=zz-hz;
  includeFramePoint([hx+dx*c+dz*s,yy,hz-dx*s+dz*c]);
 }
}
for(const drawer of data.drawers){
 const travel=drawer.depth_mm*.2;
 for(const box of data.boxes.filter(item=>drawer.piece_ids.includes(item.id))){
  includeFramePoint([box.origin[0],box.origin[1],box.origin[2]-travel]);
  includeFramePoint([box.origin[0]+box.size[0],box.origin[1]+box.size[1],box.origin[2]+box.size[2]-travel]);
 }
}
const axes=['X (horizontal)','Y (vertical)','Z (fondo)'];
document.getElementById('globalBounds').textContent=axes.map((axis,i)=>`${axis}: ${mins[i]}–${maxs[i]} (${maxs[i]-mins[i]} mm)`).join(' · ');
document.getElementById('sceneName').textContent=data.groups.map(g=>g.id).join(' · ');
document.getElementById('sceneCount').textContent=`${data.boxes.length} paneles · ${data.status}`;
document.getElementById('groupSummary').textContent=data.groups.map(g=>{const c=g.construction;const state=c?`; fondo ${c.back_status}; soporte ${c.wall_support_status}; amarre ${c.wall_tie_mode}; instalación no liberada`:'';return `${g.id}: origen ${g.origin.join(', ')} mm; bounds ${g.size.join(' × ')} mm; ${data.boxes.filter(b=>b.group===g.id).length} piezas${Number.isInteger(g.rotation)?`; rotación ${g.rotation}°`:''}${state}`}).join(' | ');
document.getElementById('digest').textContent=data.digest.slice(0,12);
document.getElementById('status').textContent=data.status;
const updateCut=()=>{cutHeight.disabled=!cutEnabled.checked;document.getElementById('cutState').textContent=cutEnabled.checked?`CORTE ACTIVADO · hasta Y=${cutHeight.value} mm`:'Corte OFF'};
const square=(b,side)=>{const [x,y,z]=b.origin,[w,h,d]=b.size,top=cutEnabled.checked?Math.min(y+h,Number(cutHeight.value)):y+h;if(top<=y)return null;
const faces=[[[x,top,z],[x+w,top,z],[x+w,top,z+d],[x,top,z+d]],
[[x+w,y,z],[x+w,y,z+d],[x+w,top,z+d],[x+w,top,z]],
[[x,y,z+d],[x+w,y,z+d],[x+w,top,z+d],[x,top,z+d]],
[[x,y,z],[x,y,z+d],[x,top,z+d],[x,top,z]],
[[x,y,z],[x+w,y,z],[x+w,top,z],[x,top,z]],
[[x,y,z],[x+w,y,z],[x+w,y,z+d],[x,y,z+d]]];
const normals=[[0,1,0],[1,0,0],[0,0,1],[-1,0,0],[0,0,-1],[0,-1,0]],camera=cameraState();
return faces.flatMap((points,index)=>{if(dot(normals[index],camera.position)<=0.00001)return [];return [{pts:points.map(([xx,yy,zz])=>P(xx,yy,zz)),world:points,faceIndex:index,fill:palette(side)[index===0?2:index===1||index===2?1:0]}]})};
// Orthographic rigid-body display ONLY: no hinge SKU, motion-clearance or load validation.
// A front-left leaf pivots around its left x-edge; a front-right leaf around its right.
const hingeFaces=(box, angleDeg)=>{
 const [x,y,z]=box.origin,[w,h,d]=box.size;
 const isLeft=box.role==='front_left';
 const hingeX=isLeft?x:x+w, hingeZ=z+d/2;
 const theta=(isLeft?1:-1)*angleDeg*Math.PI/180;
 const c=Math.cos(theta),si=Math.sin(theta);
 const R=([xx,yy,zz])=>{const dx=xx-hingeX,dz=zz-hingeZ;
  return [hingeX+dx*c+dz*si,yy,hingeZ-dx*si+dz*c];};
 const original=[
 // top, right, back, left, front, bottom: plane indices stable
 [[x,y+h,z],[x+w,y+h,z],[x+w,y+h,z+d],[x,y+h,z+d]],
 [[x+w,y,z],[x+w,y,z+d],[x+w,y+h,z+d],[x+w,y+h,z]],
 [[x,y,z+d],[x+w,y,z+d],[x+w,y+h,z+d],[x,y+h,z+d]],
 [[x,y,z],[x,y,z+d],[x,y+h,z+d],[x,y+h,z]],
 [[x,y,z],[x+w,y,z],[x+w,y+h,z],[x,y+h,z]],
 [[x,y,z],[x+w,y,z],[x+w,y,z+d],[x,y,z+d]]
 ];
 const normals=[[0,1,0],[1,0,0],[0,0,1],[-1,0,0],[0,0,-1],[0,-1,0]];
  const camera=cameraState(),fills=palette(box.role);
 return original.flatMap((face,index)=>{
  const [nx,ny,nz]=normals[index];
  const rx=nx*c+nz*si,rz=-nx*si+nz*c;
   if(dot([rx,ny,rz],camera.position)<=0.00001)return [];
  const world=face.map(R);
  return [{pts:world.map(([xx,yy,zz])=>P(xx,yy,zz)),world,faceIndex:index,
   fill:index===0?fills[2]:index===4?fills[0]:index===2?fills[1]:fills[1]}];
 });
};
const updateViewBox=()=>{const corners=[];for(const x of [frameMin[0],frameMax[0]])for(const y of [frameMin[1],frameMax[1]])for(const z of [frameMin[2],frameMax[2]])corners.push(P(x,y,z));const halfW=(Math.max(...corners.map(p=>Math.abs(p[0])))+30)*100/Number(zoom.value),halfH=(Math.max(...corners.map(p=>Math.abs(p[1])))+30)*100/Number(zoom.value);svg.setAttribute('viewBox',[-halfW,-halfH,halfW*2,halfH*2].join(' '))};

const MAX_RASTER_PIXELS=1000000;
let pickBuffer=null,baseWarnings=null;
const viewerUnavailable=reason=>{
 pickBuffer=null;
 document.getElementById('status').textContent='VISOR_NO_DISPONIBLE';
 const warnings=document.getElementById('warnings');
 warnings.textContent=[baseWarnings,'VISOR_NO_DISPONIBLE: '+reason].filter(Boolean).join(' · ');
 svg.appendChild(E('text',{x:-120,y:0,'role':'alert'},'VISOR_NO_DISPONIBLE · '+reason));
};
function render(){
 while(svg.firstChild)svg.removeChild(svg.firstChild);
 const warnings=document.getElementById('warnings');
 if(baseWarnings===null)baseWarnings=warnings.textContent;
 warnings.textContent=baseWarnings;
 document.getElementById('status').textContent=data.status;
 const all=[],layer=E('g',{'id':'panels'});svg.appendChild(layer);
 for(let boxIndex=0;boxIndex<data.boxes.length;boxIndex++){
  const original=data.boxes[boxIndex];if(!shown.has(original.group))continue;
  if(document.getElementById('interior').checked&&original.role.startsWith('front_'))continue;
  const drawer=drawerByPiece.get(original.id),progress=drawer?drawerProgress.get(drawer.id)||0:0;
  const box=progress?{...original,origin:[original.origin[0],original.origin[1],original.origin[2]-drawer.depth_mm*.2*progress/100]}:original;
  const angle=doorAngles.get(box.id)||0,parts=angle>0?hingeFaces(box,angle):square(box,box.role);
  if(!parts)continue;
  for(const face of parts)all.push({boxIndex,faceId:boxIndex*6+face.faceIndex,box,face});
 }
 updateViewBox();
 if(!all.length){pickBuffer=null;svg.appendChild(E('text',{x:-120,y:0},'Sin paneles a esta altura o con filtros actuales.'));return;}
 const vb=svg.viewBox.baseVal,width=720;
 if(!Number.isFinite(vb.width)||!Number.isFinite(vb.height)||vb.width<=0||vb.height<=0){viewerUnavailable('encuadre inválido');return;}
 const height=Math.max(100,Math.round(width*vb.height/vb.width)),pixelCount=width*height;
 if(!Number.isSafeInteger(pixelCount)||pixelCount>MAX_RASTER_PIXELS){viewerUnavailable('límite de imagen superado');return;}
 let depth,owners,faceIds,canvas,ctx,imageData;
 try{
  depth=new Float32Array(pixelCount);depth.fill(-Infinity);
  owners=new Int16Array(pixelCount);owners.fill(-1);
  faceIds=new Int16Array(pixelCount);faceIds.fill(-1);
  canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  ctx=canvas.getContext('2d',{alpha:true});
  if(!ctx)throw new Error('Canvas 2D unavailable');
  imageData=ctx.createImageData(width,height);
 }catch(error){viewerUnavailable('memoria o Canvas 2D no disponible');return;}
 const faceColors=[],camera=cameraState();
 for(const entry of all){
  const vertices=entry.face.pts.map(([x,y])=>[(x-vb.x)/vb.width*width,(y-vb.y)/vb.height*height]);
  const distances=entry.face.world.map(point=>dot([point[0]-pivot[0],point[1]-pivot[1],point[2]-pivot[2]],camera.position));
  faceColors[entry.faceId]=paintFaceHex(entry.face.fill);
  for(const triangle of [[0,1,2],[0,2,3]]){
   const [a,b,c]=triangle.map(index=>vertices[index]);
   const [da,db,dc]=triangle.map(index=>distances[index]);
   const area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
   if(Math.abs(area)<1e-8)continue;
   const x0=Math.max(0,Math.floor(Math.min(a[0],b[0],c[0]))),x1=Math.min(width-1,Math.ceil(Math.max(a[0],b[0],c[0])));
   const y0=Math.max(0,Math.floor(Math.min(a[1],b[1],c[1]))),y1=Math.min(height-1,Math.ceil(Math.max(a[1],b[1],c[1])));
   for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){
    const px=x+.5,py=y+.5;
    const wa=((b[0]-px)*(c[1]-py)-(b[1]-py)*(c[0]-px))/area;
    if(wa < -1e-8)continue;
    const wb=((c[0]-px)*(a[1]-py)-(c[1]-py)*(a[0]-px))/area;
    if(wb < -1e-8)continue;
    const wc=1-wa-wb;if(wc < -1e-8)continue;
    const index=y*width+x,value=wa*da+wb*db+wc*dc;
    if(value>depth[index]+1e-5){depth[index]=value;owners[index]=entry.boxIndex;faceIds[index]=entry.faceId;}
   }
  }
 }
 const rgba=imageData.data;
 for(let y=0;y<height;y++)for(let x=0;x<width;x++){
  const index=y*width+x,face=faceIds[index];if(face<0)continue;
  const base=faceColors[face],offset=index*4;
  const edge=(x>0&&faceIds[index-1]!==face)||(x+1<width&&faceIds[index+1]!==face)
   ||(y>0&&faceIds[index-width]!==face)||(y+1<height&&faceIds[index+width]!==face);
  const color=edge?[15,46,60]:base,selectedPiece=data.boxes[owners[index]].id;
  if(selected===selectedPiece&&edge){rgba[offset]=249;rgba[offset+1]=209;rgba[offset+2]=84;}
  else{rgba[offset]=color[0];rgba[offset+1]=color[1];rgba[offset+2]=color[2];}
  rgba[offset+3]=255;
 }
 try{
  ctx.putImageData(imageData,0,0);
  const dataUrl=canvas.toDataURL('image/png');
  if(dataUrl==='data:,')throw new Error('Canvas PNG unavailable');
  const image=E('image',{x:vb.x,y:vb.y,width:vb.width,height:vb.height,
   href:dataUrl,'data-depth-tested':'true','data-piece-count':data.boxes.length});
  layer.appendChild(image);
 }catch(error){viewerUnavailable('falló el dibujo Canvas 2D');return;}
 pickBuffer={width,height,ids:owners,x:vb.x,y:vb.y,w:vb.width,h:vb.height};
 if(data.zones.length&&document.getElementById('zones').checked){
  for(const zone of data.zones){
   if(cutEnabled.checked&&zone.origin[1]>=Number(cutHeight.value))continue;
   const faces=square({origin:zone.origin,size:zone.size},'zone');if(!faces)continue;
   const group=E('g',{'opacity':'.42','data-zone-id':zone.id});
   for(const face of faces)group.appendChild(E('polygon',{'points':face.pts.map(point=>point.join(',')).join(' '),'fill':'#ffbd68','stroke':'#a45f00','stroke-dasharray':'4 3'}));
   layer.appendChild(group);
  }
 }
}
const paintFaceHex=hex=>[parseInt(hex.slice(1,3),16),parseInt(hex.slice(3,5),16),parseInt(hex.slice(5,7),16)];
const panelAt=(x,y)=>{
 if(!pickBuffer)return null;
 const matrix=svg.getScreenCTM();if(!matrix)return null;
 const determinant=matrix.a*matrix.d-matrix.b*matrix.c;
 if(!Number.isFinite(determinant)||Math.abs(determinant)<1e-12)return null;
 try{
  const point=svg.createSVGPoint();point.x=x;point.y=y;
  const hit=point.matrixTransform(matrix.inverse());
  const ix=Math.floor((hit.x-pickBuffer.x)/pickBuffer.w*pickBuffer.width);
  const iy=Math.floor((hit.y-pickBuffer.y)/pickBuffer.h*pickBuffer.height);
  if(ix<0||iy<0||ix>=pickBuffer.width||iy>=pickBuffer.height)return null;
  const owner=pickBuffer.ids[iy*pickBuffer.width+ix];
  return owner>=0&&owner<data.boxes.length?data.boxes[owner].id:null;
 }catch(error){return null;}
};
function pick(box){selected=box.id;document.getElementById('piecePicker').value=box.id;const e=document.getElementById('details');e.textContent=`${box.id}\nGrupo: ${box.group}\nRol: ${labelRole(box.role)} (${box.role})\nOrigen XYZ: ${box.origin.join(', ')} mm\nTamaño XYZ: ${box.size.join(' × ')} mm`;render()}
const updateCameraReadout=()=>{document.getElementById('cameraReadout').textContent=`Giro ${Math.round(yaw)}° · Elevación ${Math.round(elevation)}°`;for(const button of document.querySelectorAll('#views button'))button.setAttribute('aria-pressed',String(activePreset!==null&&Number(button.dataset.yaw)===activePreset&&elevation===INITIAL_ELEVATION))};
for(const angle of [0,90,180,270]){const button=document.createElement('button');button.textContent=angle+'°';button.dataset.yaw=String(angle);button.type='button';button.setAttribute('aria-label',`Solo cámara: orientación ${angle} grados`);button.addEventListener('click',()=>{yaw=angle;elevation=INITIAL_ELEVATION;activePreset=angle;updateCameraReadout();render()});document.getElementById('views').appendChild(button)}updateCameraReadout();
const stage=document.querySelector('.stage');let pointerDrag=null,suppressClickUntil=0;
const finishPointer=(event,allowSelection)=>{if(!pointerDrag||pointerDrag.id!==event.pointerId)return;const drag=pointerDrag;pointerDrag=null;stage.classList.remove('dragging');if(drag.moved){suppressClickUntil=performance.now()+250;setTimeout(()=>{suppressClickUntil=0},0)}else if(allowSelection&&drag.pieceId&&panelAt(event.clientX,event.clientY)===drag.pieceId){const box=data.boxes.find(item=>item.id===drag.pieceId);if(box)pick(box)}};
svg.addEventListener('pointerdown',event=>{if(event.button!==0||!event.isPrimary)return;pointerDrag={id:event.pointerId,x:event.clientX,y:event.clientY,yaw,elevation,pieceId:panelAt(event.clientX,event.clientY),moved:false};svg.setPointerCapture(event.pointerId)});
svg.addEventListener('pointermove',event=>{if(!pointerDrag||pointerDrag.id!==event.pointerId)return;const dx=event.clientX-pointerDrag.x,dy=event.clientY-pointerDrag.y;if(!pointerDrag.moved&&Math.hypot(dx,dy)<5)return;pointerDrag.moved=true;event.preventDefault();yaw=normalizeYaw(pointerDrag.yaw+dx*.5);elevation=clamp(pointerDrag.elevation-dy*.35,15,75);activePreset=null;stage.classList.add('dragging');updateCameraReadout();render()});
svg.addEventListener('pointerup',event=>finishPointer(event,true));svg.addEventListener('pointercancel',event=>finishPointer(event,false));svg.addEventListener('lostpointercapture',event=>finishPointer(event,false));
svg.addEventListener('click',event=>{if(performance.now()<=suppressClickUntil){event.preventDefault();event.stopImmediatePropagation();suppressClickUntil=0}},true);
svg.addEventListener('wheel',event=>{if(event.deltaY===0)return;event.preventDefault();const value=clamp(Number(zoom.value)+(event.deltaY<0?10:-10),60,160);if(value===Number(zoom.value))return;zoom.value=String(value);document.getElementById('zoomLabel').textContent=value+' %';render()},{passive:false});
for(const group of data.groups){const row=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.checked=true;box.addEventListener('change',()=>{box.checked?shown.add(group.id):shown.delete(group.id);render()});row.append(box,document.createTextNode(` ${group.id} (${data.boxes.filter(b=>b.group===group.id).length} paneles)`));document.getElementById('groups').appendChild(row)}
const warningText={'ALL_GEOMETRY_NOMINAL_NO_CUT_AUTHORITY':'Geometría nominal, sin autorización de corte','ROOM_LAYOUT_DOES_NOT_VERIFY_WALLS_LOADS_ANCHORS_OR_HARDWARE':'Muros, cargas, anclajes y herrajes sin verificar','SERVICE_RESERVATIONS_ARE_NOT_HOLES_OR_PLUMBING_INSTALLATION':'Reservas sin perforaciones ni instalación','CORNER_JOINT_AND_FILLER_NOT_DESIGNED':'Uniones y rellenos de esquina sin diseñar','OVERLAPPING_CABINET_ENVELOPES_BLOCK_APPROVAL':'Interferencias entre muebles: aprobación bloqueada'};
document.getElementById('warnings').textContent=data.warnings.map(w=>warningText[w]||w).join(' · ');
const picker=document.getElementById('piecePicker');for(const box of data.boxes){const option=document.createElement('option');option.value=box.id;option.textContent=`${box.id} — ${labelRole(box.role)} (${box.role})`;picker.appendChild(option)}picker.selectedIndex=-1;
picker.addEventListener('change',()=>pick(data.boxes.find(box=>box.id===picker.value)));
// Only actual front-left/right panels get movement controls. Fixed blind panels
// and missing drawers are never invented or animated.
const movable=data.boxes.filter(box=>box.role==='front_left'||box.role==='front_right');
document.getElementById('noDoors').hidden=movable.length>0;
document.getElementById('noDrawers').hidden=data.drawers.length>0;
const blocked=document.getElementById('blockedDrawers');
if(data.blocked_drawers.length){blocked.hidden=false;blocked.textContent='Cajones bloqueados para apertura visual: '+data.blocked_drawers.map(item=>`${item.id}: ${item.reason}`).join(' · ')}
for(const drawer of data.drawers){
 const row=document.createElement('div');row.className='drawer-control';row.dataset.drawerId=drawer.id;
 const label=document.createElement('label');const title=document.createElement('strong');
 title.textContent=`${drawer.label} · ${drawer.group}`;
 const output=document.createElement('output');output.textContent='0 % (cerrado)';
 const slider=document.createElement('input');slider.type='range';slider.min='0';slider.max='100';slider.step='10';slider.value='0';
 slider.dataset.drawerId=drawer.id;
 slider.setAttribute('aria-label',`Apertura visual nominal de ${drawer.label} en ${drawer.group}`);
 slider.addEventListener('input',()=>{const value=Number(slider.value);drawerProgress.set(drawer.id,value);output.textContent=`${value} % ${value===0?'(cerrado)':'(solo ilustración)'}`;render()});
 label.append(title,document.createTextNode(' '),output);row.append(label,slider);document.getElementById('drawerSliders').appendChild(row);
}
for(const box of movable){
 const row=document.createElement('div');row.className='door-control';
 const label=document.createElement('label');
 const title=document.createElement('strong');title.textContent=labelRole(box.role)+' · '+box.group;
 const output=document.createElement('output');output.textContent='0° (cerrada)';
 const slider=document.createElement('input');slider.type='range';slider.min='0';slider.max='90';slider.step='10';slider.value='0';
 slider.setAttribute('aria-label','Apertura visual de '+labelRole(box.role)+' de '+box.group);
 slider.addEventListener('input',()=>{
  const a=Number(slider.value);doorAngles.set(box.id,a);
  output.textContent=a+'° '+(a===0?'(cerrada)':'(solo ilustración)');
  document.getElementById('interior').checked=false;
  document.getElementById('interiorBanner').hidden=true;
  render();
 });
 label.append(title,document.createTextNode(' '),output);row.append(label,slider);
 document.getElementById('doorSliders').appendChild(row);
}

cutEnabled.addEventListener('change',()=>{updateCut();render()});cutHeight.addEventListener('input',()=>{const valid=cutHeight.value!==''&&Number(cutHeight.value)>=0&&Number(cutHeight.value)<=maxHeight;if(valid){updateCut();render()}});
zoom.addEventListener('input',()=>{document.getElementById('zoomLabel').textContent=zoom.value+' %';render()});
document.getElementById('interior').addEventListener('change',event=>{const enabled=event.target.checked;document.getElementById('interiorBanner').hidden=!enabled;document.getElementById('noShelf').hidden=!(enabled&&!data.boxes.some(box=>box.role==='shelf_horizontal'));render()});
if(data.zones.length){document.getElementById('zoneControl').hidden=false;document.getElementById('zones').addEventListener('change',render)}
document.getElementById('resetView').addEventListener('click',()=>{yaw=0;elevation=INITIAL_ELEVATION;activePreset=0;updateCameraReadout();zoom.value='100';cutEnabled.checked=false;cutHeight.value=String(maxHeight);shown=new Set(data.groups.map(group=>group.id));for(const input of document.querySelectorAll('#groups input[type=checkbox]'))input.checked=true;document.getElementById('interior').checked=false;document.getElementById('interiorBanner').hidden=true;document.getElementById('noShelf').hidden=true;if(data.zones.length)document.getElementById('zones').checked=true;selected='';picker.selectedIndex=-1;document.getElementById('details').textContent='Selecciona un tablero para ver sus medidas nominales.';document.getElementById('zoomLabel').textContent='100 %';doorAngles.clear();drawerProgress.clear();for(const input of document.querySelectorAll('#doorSliders input')){input.value='0';input.previousElementSibling?.querySelector('output')?.replaceChildren('0° (cerrada)')}for(const input of document.querySelectorAll('#drawerSliders input')){input.value='0';input.previousElementSibling?.querySelector('output')?.replaceChildren('0 % (cerrado)')}updateCut();render()});
updateCut();render();
</script></body></html>
'''


_MODULE_CSS = r'''
.module-review select{width:100%;margin:4px 0 8px}.module-review button{margin:4px 4px 4px 0}
.module-review output,.module-review pre{display:block;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.45 ui-monospace,Consolas,monospace;color:#304c5a;background:#f4f7f8;border-radius:5px;padding:8px;min-height:32px}
.module-review a{display:inline-block;margin-top:7px;color:#075d78;font-weight:700}
.module-review .candidate-list{display:flex;flex-wrap:wrap;gap:5px}.module-review .candidate-list button{font-size:12px}
.module-stage-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 8px;padding:8px 10px;background:#fff;border:1px solid #c4d1d5;border-radius:8px}.module-stage-bar output{flex:1;min-width:120px;font-weight:650;font-size:13px}.module-stage-bar button{margin:0;background:#176b7d;color:#fff;border-color:#176b7d}.module-stage-bar button:disabled{opacity:.45;cursor:default}
'''

_MODULE_UI = r'''<fieldset id="moduleReview" class="module-review"><legend>Seleccionar y enfocar mueble</legend>
<label for="modulePicker">Muebles del conjunto</label><select id="modulePicker"><option value="">Selecciona un mueble</option></select>
<button type="button" id="focusModule" disabled>Enfocar mueble</button>
<output id="moduleSummary" aria-live="polite">Selecciona un módulo de la lista o una pieza visible.</output>
<fieldset id="candidateField" hidden><legend>Piezas para revisar uniones</legend><div id="candidateButtons" class="candidate-list"></div><output id="candidateStatus" aria-live="polite"></output></fieldset>
<fieldset id="wallEditor" hidden><legend>Propuesta independiente de fondo, pared y apoyo</legend>
<label for="backChoice">A · Fondo posterior</label><select id="backChoice"><option value="">Selecciona fondo</option>
<option value="keep_existing">Conservar el fondo existente</option><option value="none">Sin fondo</option>
<option value="inset_board_3mm_review">Fondo 3 mm · revisar especificación</option><option value="inset_board_15mm_review">Fondo 15 mm · revisar especificación</option><option value="inset_board_18mm_review">Fondo 18 mm · revisar especificación</option>
<option value="inset_carcass_material_review">Material y espesor reales de carcasa</option><option value="inset_two_strips_review">Dos franjas · revisar especificación</option></select>
<label for="wallSystem">B · Sistema de fijación a pared</label><select id="wallSystem"><option value="">Selecciona fijación</option>
<option value="none">Ninguno</option><option value="direct_rear_tie">Amarre trasero directo</option><option value="french_cleat_45">Sistema francés 45°</option><option value="metal_L_bracket">Ángulo metálico en L</option><option value="metal_cabinet_hanger">Colgador metálico</option><option value="metal_cabinet_clip">Grapa metálica para mueble</option><option value="wall_rail">Riel de pared</option><option value="floor_furniture_anti_tip">Antivuelco para mueble apoyado en piso</option></select>
<label for="supportChoice">C · Apoyo propio</label><select id="supportChoice"><option value="">Selecciona apoyo</option>
<option value="keep_existing">Conservar apoyo existente</option><option value="floor_direct">Piso directo</option><option value="legs">Patas</option><option value="plinth">Zócalo</option><option value="wall_mounted">Suspendido al muro</option></select>
<label for="wallSubstrate">Tipo de muro</label><select id="wallSubstrate"><option value="">Selecciona muro</option>
<option value="unknown">Desconocido</option><option value="concrete">Concreto</option><option value="solid_masonry">Mampostería sólida</option><option value="hollow_masonry">Mampostería hueca</option><option value="drywall">Panel de yeso</option><option value="wood_studs">Montantes de madera</option><option value="other">Otro</option></select>
<button type="button" id="prepareWallReview" disabled>Preparar revisión JSON</button>
<output id="backGeometryStatus" aria-live="polite">Geometría del fondo: pendiente de revisión.</output>
<output id="supportReviewStatus" aria-live="polite">Apoyo: pendiente de selección y comparación.</output>
<output id="wallReviewStatus" aria-live="polite">Las opciones no cambian piezas ni autorizan montaje.</output><pre id="wallIntentPreview" hidden></pre><a id="downloadWallIntent" hidden>Descargar intención JSON</a>
<fieldset id="backSpecFields" hidden><legend>Datos explícitos del fondo</legend>
<label for="backMaterial">Material de fondo</label><select id="backMaterial"><option value="">Selecciona material</option><option value="HDF_3_LAB">HDF_3_LAB</option><option value="MELAMINA_15">MELAMINA_15</option><option value="MELAMINA_18">MELAMINA_18</option></select>
<label for="backServices">¿Hay servicios detrás?</label><select id="backServices"><option value="">Confirma servicios</option><option value="false">No</option><option value="true">Sí</option></select>
<label for="backGrain">Veta del fondo</label><select id="backGrain"><option value="">Confirma veta</option><option value="none">Sin veta</option><option value="face_x">Eje X</option><option value="face_y">Eje Y</option></select>
<label for="stripTop">Alto franja superior (solo dos franjas)</label><input id="stripTop" type="number" min="1" max="20000" step="1">
<label for="stripBottom">Alto franja inferior (solo dos franjas)</label><input id="stripBottom" type="number" min="1" max="20000" step="1">
<label for="stripThickness">Espesor de franjas (mm)</label><input id="stripThickness" type="number" min="1" max="20000" step="1">
<label><input id="replaceTies" type="checkbox"> Confirmo sustituir los amarres existentes de este módulo</label></fieldset>
</fieldset>
<fieldset id="moduleDimensions" hidden><legend>Medidas nominales del mueble</legend>
<label for="editWidth">Ancho exterior local (mm)</label><input id="editWidth" type="number" min="1" max="20000" step="1">
<label for="editHeight">Alto exterior total con apoyo (mm)</label><input id="editHeight" type="number" min="1" max="20000" step="1">
<label for="editDepth">Fondo de carcasa (mm)</label><input id="editDepth" type="number" min="1" max="20000" step="1">
<label for="editSupportStyle">Apoyo conceptual</label><select id="editSupportStyle"><option value="floor_direct">Piso directo</option><option value="legs">Patas</option><option value="plinth">Zócalo</option><option value="wall_mounted">Suspendido al muro</option></select>
<label for="editSupportHeight">Reserva de altura del apoyo (mm)</label><input id="editSupportHeight" type="number" min="0" max="20000" step="1">
<output id="editBlockReason" aria-live="polite"></output>
<p id="offlineNotice" hidden>Visor offline: para aplicar y recalcular abre el editor local.</p>
<button type="button" id="applyModuleChanges" hidden>Aplicar cambios y recalcular</button>
<button type="button" id="downloadFullRequest" hidden>Preparar solicitud completa offline</button>
<a id="downloadFullRequestLink" hidden>Descargar solicitud completa</a>
<output id="moduleEditStatus" aria-live="polite">Sin cambios aplicados.</output>
</fieldset></fieldset>'''

_MODULE_SCRIPT = r'''
Object.assign(ROLE_LABEL,{wall_rear_upper_tie:'amarre trasero superior',wall_rear_lower_tie:'amarre trasero inferior',upper_rear_tie:'correa trasera superior',lower_rear_tie:'correa trasera inferior'});
const moduleKey=(groupId,moduleId)=>groupId+'::'+moduleId;
const moduleIndex=data.module_index,wallReviews=data.wall_reviews;
const moduleEditIndex=data.module_edit_index||[],moduleEditRequest=data.module_edit_request||null;
const hostSession=window.CARPNOVA_EDITOR_SESSION||null,pendingModuleEdits=new Map();
const modulePicker=document.getElementById('modulePicker'),moduleSummary=document.getElementById('moduleSummary');
const wallEditor=document.getElementById('wallEditor'),wallSelects=['backChoice','wallSystem','supportChoice','wallSubstrate'].map(id=>document.getElementById(id));
const wallStatus=document.getElementById('wallReviewStatus'),wallPreview=document.getElementById('wallIntentPreview');
const wallDownload=document.getElementById('downloadWallIntent'),prepareWall=document.getElementById('prepareWallReview');
const backGeometryStatus=document.getElementById('backGeometryStatus'),supportReviewStatus=document.getElementById('supportReviewStatus');
const candidateField=document.getElementById('candidateField'),candidateButtons=document.getElementById('candidateButtons'),candidateStatus=document.getElementById('candidateStatus');
const moduleDimensions=document.getElementById('moduleDimensions'),moduleEditStatus=document.getElementById('moduleEditStatus');
const editInputs={width_mm:document.getElementById('editWidth'),overall_height_mm:document.getElementById('editHeight'),carcass_depth_mm:document.getElementById('editDepth'),support_style:document.getElementById('editSupportStyle'),support_height_mm:document.getElementById('editSupportHeight')};
const backSpecFields=document.getElementById('backSpecFields');
const allPieceOptions=[...picker.options].map(option=>({value:option.value,text:option.textContent}));
const findModule=key=>moduleIndex.find(item=>moduleKey(item.group_id,item.module_id)===key);
const savedReview=item=>wallReviews.find(review=>review.group_id===item.group_id&&review.module_id===item.module_id);
function clearPieceSelection(){selected='';picker.selectedIndex=-1;document.getElementById('details').textContent='Selecciona un tablero para ver sus medidas nominales.'}
function setPieceOptions(item=null){picker.replaceChildren();const allowed=item?new Set(item.piece_ids):null;for(const option of allPieceOptions){if(allowed&&!allowed.has(option.value))continue;const node=document.createElement('option');node.value=option.value;node.textContent=option.text;picker.appendChild(node)}picker.selectedIndex=-1}
function clearIntent(){wallPreview.textContent='';wallPreview.hidden=true;wallDownload.hidden=true;wallDownload.removeAttribute('href');wallDownload.removeAttribute('download');prepareWall.disabled=true;if(wallObjectUrl){URL.revokeObjectURL(wallObjectUrl);wallObjectUrl=null}}
function showCandidates(item){candidateButtons.replaceChildren();candidateField.hidden=false;const candidates=item.candidate_piece_ids.map(id=>data.boxes.find(box=>box.id===id)).filter(Boolean);if(!candidates.length){candidateStatus.textContent='Sin piezas candidatas verificadas; revisión de uniones pendiente.';return}candidateStatus.textContent='Candidatos nominales de revisión. No son puntos de perforación ni certifican carga.';for(const box of candidates){const button=document.createElement('button');button.type='button';button.textContent=`${labelRole(box.role)} · ${box.id}`;button.setAttribute('aria-label',`Enfocar ${labelRole(box.role)} ${box.id}`);button.addEventListener('click',()=>focusCandidate(item,box));candidateButtons.appendChild(button)}}
function editItem(item){return moduleEditIndex.find(value=>value.group_id===item.group_id&&value.module_id===item.module_id)}
function populateDimensions(item){const source=editItem(item);moduleDimensions.hidden=!source;if(!source)return;const pending=pendingModuleEdits.get(moduleKey(item.group_id,item.module_id));for(const [field,input] of Object.entries(editInputs)){input.value=String(pending?.[field]??source[field]);input.disabled=!source.editable_fields.includes(field)}document.getElementById('editBlockReason').textContent=source.edit_block_reason||`Carcasa ${source.width_mm} × ${source.carcass_height_mm} × ${source.carcass_depth_mm} mm; exterior ensamblado ${source.assembled_external_depth_mm} mm.`;document.getElementById('offlineNotice').hidden=Boolean(hostSession);document.getElementById('applyModuleChanges').hidden=!hostSession;document.getElementById('downloadFullRequest').hidden=Boolean(hostSession);moduleEditStatus.textContent='Los campos pendientes no cambian la escena hasta aplicar.'}
function showModuleSummary(){const item=findModule(selectedModuleKey);if(!item)return;const reservation=(data.support_reservations||[]).find(value=>value.group_id===item.group_id&&value.module_id===item.module_id);moduleSummary.textContent=`${item.group_id} · ${item.module_id}\nEnvolvente nominal XYZ: origen ${item.bounds_origin_xyz_mm.join(', ')} mm; tamaño ${item.bounds_size_xyz_mm.join(' × ')} mm\nInstalación: ${item.installation_mode}; apoyo real declarado: ${item.support_status}.${reservation?`\nReserva conceptual ${reservation.style}: ${reservation.support_height_mm} mm; contorno discontinuo no seleccionable, no son piezas ni montaje.`:''}\nFoco visual: prioriza este mueble frente a los vecinos atenuados; no representa oclusión física ni medida de corte.`;showCandidates(item);populateDimensions(item)}
function supportPending(item,choice){const actual=item.support_status,aliases={floor_direct:['floor','floor_direct'],legs:['legs'],plinth:['plinth'],wall_mounted:['wall','wall_mounted']};return choice==='keep_existing'?!['floor','legs','plinth','wall'].includes(actual):!(aliases[choice]||[]).includes(actual)}
function updateWallStatus(){const item=findModule(selectedModuleKey),values=wallSelects.map(select=>select.value);clearIntent();prepareWall.disabled=!item||values.some(value=>!value);if(!item){backGeometryStatus.textContent='Geometría del fondo: pendiente de revisión.';supportReviewStatus.textContent='Apoyo: pendiente de selección y comparación.';wallStatus.textContent='Selecciona un módulo. Las opciones no cambian piezas ni autorizan montaje.';return}const saved=savedReview(item),same=saved&&saved.back_choice===values[0]&&saved.wall_system===values[1]&&saved.support_choice===values[2]&&saved.wall_substrate===values[3];backGeometryStatus.textContent=`Geometría del fondo: ${same?saved.back_geometry_status:'sin validar para esta intención'}. No determina fijación.`;supportReviewStatus.textContent=`Apoyo real declarado: ${item.support_status}. ${values[2]?supportPending(item,values[2])?'Apoyo por confirmar; la opción difiere del modelo y no se aplica.':'Opción de apoyo sin cambios aplicados.':'Elige una propuesta para compararla.'}`;wallStatus.textContent=same?`Revisión Maestro: ${saved.status}${saved.constraints.length?` · Pendiente: ${saved.constraints.join(', ')}`:''}${saved.book_evidence.length?` · Fuente: ${saved.book_evidence.map(source=>source.content_id+' p.'+source.pdf_page).join(', ')}`:''}. Instalación no autorizada.`:'PENDING_BACKEND_REVIEW · Esta elección es una intención sin validar; enviar el JSON a Maestro. No se aplicó geometría ni instalación.'}
function leaveFocus(restoreZoom=true){if(!focusedModuleKey)return;focusedModuleKey='';pivot=fullPivot.slice();frameMin=fullFrameMin.slice();frameMax=fullFrameMax.slice();if(restoreZoom&&savedGroupZoom!==null){zoom.value=String(savedGroupZoom);document.getElementById('zoomLabel').textContent=zoom.value+' %'}savedGroupZoom=null;setPieceOptions();clearPieceSelection();document.getElementById('focusModule').hidden=false;document.getElementById('returnToSet').disabled=true}
function returnToSet(){clearModuleSelection()}
function selectModule(item){const key=moduleKey(item.group_id,item.module_id);if(focusedModuleKey&&focusedModuleKey!==key)leaveFocus(true);const groupIndex=data.groups.findIndex(group=>group.id===item.group_id),groupToggle=document.querySelectorAll('#groups input')[groupIndex];if(groupToggle&&!shown.has(item.group_id)){groupToggle.checked=true;shown.add(item.group_id)}selectedModuleKey=key;modulePicker.value=String(moduleIndex.indexOf(item));document.getElementById('focusModule').disabled=false;wallEditor.hidden=false;showModuleSummary();const saved=savedReview(item),values=saved?[saved.back_choice,saved.wall_system,saved.support_choice,saved.wall_substrate]:['','','',''];wallSelects.forEach((select,index)=>{select.value=values[index]});backSpecFields.hidden=!['inset_board_3mm_review','inset_board_15mm_review','inset_board_18mm_review','inset_two_strips_review'].includes(values[0]);document.getElementById('replaceTies').checked=false;clearPieceSelection();document.getElementById('details').textContent='Selecciona el mueble; enfócalo para inspeccionar sus piezas.';updateWallStatus();render()}
function focusSelectedModule(){const item=findModule(selectedModuleKey);if(!item)return;const key=selectedModuleKey;if(!focusedModuleKey)savedGroupZoom=Number(zoom.value);focusedModuleKey=key;const boxes=data.boxes.filter(box=>box.group===item.group_id&&box.module_id===item.module_id),frame=movementFrame(boxes,item.bounds_origin_xyz_mm,item.bounds_origin_xyz_mm.map((value,index)=>value+item.bounds_size_xyz_mm[index]));pivot=frame.min.map((value,index)=>(value+frame.max[index])/2);frameMin=frame.min;frameMax=frame.max;zoom.value='100';document.getElementById('zoomLabel').textContent='100 %';setPieceOptions(item);clearPieceSelection();document.getElementById('focusModule').hidden=true;document.getElementById('returnToSet').disabled=false;showModuleSummary();render()}
function focusCandidate(item,box){if(!shown.has(box.group)){const index=data.groups.findIndex(group=>group.id===box.group),toggle=document.querySelectorAll('#groups input')[index];if(toggle)toggle.checked=true;shown.add(box.group)}if(cutEnabled.checked&&box.origin[1]>=Number(cutHeight.value)){candidateStatus.textContent=`${box.id} queda por encima del corte activo; desactiva el corte para inspeccionarlo.`;return}if(selectedModuleKey!==moduleKey(item.group_id,item.module_id))selectModule(item);if(!focusedModuleKey)focusSelectedModule();pick(box)}
function clearModuleSelection(){leaveFocus(true);selectedModuleKey='';modulePicker.value='';document.getElementById('focusModule').disabled=true;document.getElementById('focusModule').hidden=false;document.getElementById('returnToSet').disabled=true;wallEditor.hidden=true;moduleDimensions.hidden=true;moduleSummary.textContent='Selecciona un módulo de la lista o una pieza visible.';candidateField.hidden=true;candidateButtons.replaceChildren();candidateStatus.textContent='';wallSelects.forEach(select=>select.value='');clearIntent();clearPieceSelection();updateWallStatus();render()}
const originalPick=pick;
pick=function(box){if(!box)return;const key=moduleKey(box.group,box.module_id);if(focusedModuleKey){if(key!==focusedModuleKey)return;originalPick(box);return}if(key!==selectedModuleKey){const item=moduleIndex.find(value=>moduleKey(value.group_id,value.module_id)===key);if(item)selectModule(item);return}showModuleSummary()};
for(const [index,item] of moduleIndex.entries()){const option=document.createElement('option');option.value=String(index);option.textContent=`${item.group_id} · ${item.module_id}`;modulePicker.appendChild(option)}
modulePicker.addEventListener('change',()=>{if(modulePicker.value===''){clearModuleSelection();return}const index=Number(modulePicker.value),item=Number.isInteger(index)?moduleIndex[index]:null;if(item)selectModule(item);else clearModuleSelection()});
document.getElementById('focusModule').addEventListener('click',focusSelectedModule);document.getElementById('returnToSet').addEventListener('click',returnToSet);
svg.addEventListener('dblclick',event=>{const id=panelAt(event.clientX,event.clientY),box=data.boxes.find(item=>item.id===id);if(!box||!box.module_id)return;const item=moduleIndex.find(value=>moduleKey(value.group_id,value.module_id)===moduleKey(box.group,box.module_id));if(item){selectModule(item);focusSelectedModule()}event.preventDefault()});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&(focusedModuleKey||selectedModuleKey))returnToSet()});
document.getElementById('resetView').addEventListener('click',()=>{focusedModuleKey='';savedGroupZoom=null;pivot=fullPivot.slice();frameMin=fullFrameMin.slice();frameMax=fullFrameMax.slice();setPieceOptions();clearPieceSelection();document.getElementById('focusModule').hidden=false;document.getElementById('returnToSet').disabled=true;clearModuleSelection()});
wallSelects.forEach(select=>select.addEventListener('change',updateWallStatus));
for(const [field,input] of Object.entries(editInputs)){input.addEventListener('input',()=>{if(!selectedModuleKey)return;const values={};for(const [name,control] of Object.entries(editInputs))values[name]=control.type==='number'?Number(control.value):control.value;pendingModuleEdits.set(selectedModuleKey,values);moduleEditStatus.textContent='Cambios pendientes en '+selectedModuleKey+'; la geometría aún no cambia.'})}
const backChoice=document.getElementById('backChoice');backChoice.addEventListener('change',()=>{const choice=backChoice.value;backSpecFields.hidden=!['inset_board_3mm_review','inset_board_15mm_review','inset_board_18mm_review','inset_two_strips_review'].includes(choice);document.getElementById('replaceTies').checked=false;updateWallStatus()});
prepareWall.addEventListener('click',()=>{const item=findModule(selectedModuleKey);if(!item||wallSelects.some(select=>!select.value))return;const intent={group_id:item.group_id,module_id:item.module_id,back_choice:wallSelects[0].value,wall_system:wallSelects[1].value,support_choice:wallSelects[2].value,wall_substrate:wallSelects[3].value};const text=JSON.stringify(intent,null,2);wallPreview.textContent=text;wallPreview.hidden=false;wallObjectUrl=URL.createObjectURL(new Blob([text+'\n'],{type:'application/json'}));wallDownload.href=wallObjectUrl;wallDownload.download=`wall-review-${item.group_id}-${item.module_id}.json`;wallDownload.hidden=false;wallDownload.textContent='Descargar intención JSON · seis campos';wallStatus.textContent='Preparada para revisión del Maestro. No se guardó ni aplicó al proyecto y no autoriza instalación.'});
function currentEdit(item){const source=editItem(item);if(!source)return null;const values={};for(const [field,input] of Object.entries(editInputs)){if(source.editable_fields.includes(field)){if(field==='support_style'){if(!['floor_direct','legs','plinth','wall_mounted'].includes(input.value))throw new Error('Selecciona un tipo de apoyo válido.');values[field]=input.value}else{if(input.value===''||!Number.isInteger(Number(input.value)))throw new Error(`Completa ${field} con milímetros enteros.`);values[field]=Number(input.value)}}else values[field]=source[field]}const edit={group_id:item.group_id,module_id:item.module_id,width_mm:values.width_mm,overall_height_mm:values.overall_height_mm,carcass_depth_mm:values.carcass_depth_mm,support_style:values.support_style,support_height_mm:values.support_height_mm};return Object.keys(edit).some(key=>!['group_id','module_id'].includes(key)&&edit[key]!==source[key])?edit:null}
function currentWall(item){const values=wallSelects.map(select=>select.value);if(values.some(value=>!value))return null;const saved=savedReview(item),keys=['back_choice','wall_system','support_choice','wall_substrate'];if(saved&&keys.every((key,index)=>saved[key]===values[index]))return null;return {group_id:item.group_id,module_id:item.module_id,back_choice:values[0],wall_system:values[1],support_choice:values[2],wall_substrate:values[3]}}
function currentBackSpec(){const choice=backChoice.value;if(choice==='keep_existing')return null;if(choice==='none')return 'none';const match=choice.match(/^inset_board_(3|15|18)mm_review$/);if(!match&&choice!=='inset_two_strips_review')return null;const material=document.getElementById('backMaterial').value,services=document.getElementById('backServices').value,grain=document.getElementById('backGrain').value;if(!material||services===''||!grain)throw new Error('Confirma material, servicios y veta del fondo.');const back={style:choice==='inset_two_strips_review'?'inset_two_strips':'inset_full',material_id:material,thickness_mm:match?Number(match[1]):Number(document.getElementById('stripThickness')?.value||0),services_present:services==='true',grain_axis:grain};if(choice==='inset_two_strips_review'){const top=Number(document.getElementById('stripTop').value),bottom=Number(document.getElementById('stripBottom').value);if(!Number.isInteger(top)||top<=0||!Number.isInteger(bottom)||bottom<=0)throw new Error('Indica ambas alturas enteras de las franjas.');back.top_strip_height_mm=top;back.bottom_strip_height_mm=bottom}return back}
function mergedSourceRequest(item){if(!moduleEditRequest)throw new Error('Solicitud fuente offline no incluida.');const request=JSON.parse(JSON.stringify(moduleEditRequest)),edit=currentEdit(item),wall=currentWall(item);if(edit){const edits=request.module_edit_revisions||[];const i=edits.findIndex(value=>value.group_id===edit.group_id&&value.module_id===edit.module_id);if(i<0)edits.push(edit);else edits[i]=edit;request.module_edit_revisions=edits}if(wall){const revisions=request.wall_review_revisions||[];const i=revisions.findIndex(value=>value.group_id===wall.group_id&&value.module_id===wall.module_id);if(i<0)revisions.push(wall);else revisions[i]=wall;request.wall_review_revisions=revisions}const back=currentBackSpec();if(back!==null){if(!wall)throw new Error('El fondo requiere las seis decisiones murales explícitas.');if(request.review_kind==='kitchen_spatial_v1'){const revisions=request.back_revisions||[];const i=revisions.findIndex(value=>value.group_id===item.group_id&&value.module_id===item.module_id);const revision={group_id:item.group_id,module_id:item.module_id,back};if(i<0)revisions.push(revision);else revisions[i]=revision;request.back_revisions=revisions}else{const assembly=request.assemblies.find(value=>value.group_id===item.group_id),module=assembly?.module_spec?.modules?.find(value=>value.module_id===item.module_id);if(!module)throw new Error('No se encontró el módulo en la fuente.');module.back=back}}return request}
function makePayload(item,version){const moduleEdit=currentEdit(item),wall=currentWall(item),backSpec=currentBackSpec();if((backSpec!==null)&&!wall)throw new Error('Un cambio de fondo requiere wall_revision completa.');if(!moduleEdit&&!wall)throw new Error('No hay cambios pendientes.');const hasTies=data.boxes.some(box=>box.group===item.group_id&&box.module_id===item.module_id&&['wall_rear_lower_tie','wall_rear_upper_tie','upper_rear_tie','lower_rear_tie'].includes(box.role));const replace=document.getElementById('replaceTies').checked;if(replace&&!hasTies)throw new Error('No hay amarres existentes que confirmar para sustitución.');return {version,group_id:item.group_id,module_id:item.module_id,wall_revision:wall,back_spec:backSpec,replace_existing_ties:replace,module_edit:moduleEdit}}
document.getElementById('downloadFullRequest').addEventListener('click',()=>{try{const item=findModule(selectedModuleKey),request=mergedSourceRequest(item),text=JSON.stringify(request,null,2);const url=URL.createObjectURL(new Blob([text+'\n'],{type:'application/json'}));const link=document.getElementById('downloadFullRequestLink');link.href=url;link.download='carpinova-solicitud-m6.json';link.hidden=false;link.textContent='Descargar solicitud completa';moduleEditStatus.textContent='Solicitud completa preparada desde la fuente D19; no se aplicó geometría en este visor offline.'}catch(error){moduleEditStatus.textContent=error.message}});
document.getElementById('applyModuleChanges').addEventListener('click',async()=>{const item=findModule(selectedModuleKey);if(!hostSession||!item)return;const button=document.getElementById('applyModuleChanges');try{const payload=makePayload(item,hostSession.version);button.disabled=true;moduleEditStatus.textContent='Recalculando por Maestro/F6…';const response=await fetch('/apply',{method:'POST',headers:{'Content-Type':'application/json','X-CarpiNova-Session':hostSession.token},body:JSON.stringify(payload)});const body=await response.json();if(!response.ok||!body.ok)throw new Error(body.message||`El host rechazó la solicitud (${response.status}).`);sessionStorage.setItem('carpinovaSelection',moduleKey(item.group_id,item.module_id));sessionStorage.setItem('carpinovaAppliedMessage',body.result==='GEOMETRY_UPDATED'?'Cambios geométricos aplicados y D19 guardado.':'Revisión conceptual guardada; geometría sin cambios.');location.reload()}catch(error){moduleEditStatus.textContent=error.message;button.disabled=false}});
if(hostSession){document.getElementById('applyModuleChanges').hidden=false;document.getElementById('downloadFullRequest').hidden=true}else if(moduleEditRequest){document.getElementById('applyModuleChanges').hidden=true;document.getElementById('downloadFullRequest').hidden=false;}
if(hostSession){const restoreKey=sessionStorage.getItem('carpinovaSelection'),appliedMessage=sessionStorage.getItem('carpinovaAppliedMessage');if(restoreKey){const restored=findModule(restoreKey);sessionStorage.removeItem('carpinovaSelection');sessionStorage.removeItem('carpinovaAppliedMessage');if(restored){selectModule(restored);if(appliedMessage)moduleEditStatus.textContent=appliedMessage}}}
'''


def _module_editor_html(html: str) -> str:
    """Add the editor only to explicitly selected D19 reviews.

    The no-selection D19 path intentionally returns the historical template
    bytes unchanged.
    """
    frame_block = """const pivot=mins.map((value,i)=>(value+maxs[i])/2);
// Keep a fixed camera frame that includes door swings and the conservative visual drawer travel.
const frameMin=mins.slice(),frameMax=maxs.slice();
const includeFramePoint=point=>{for(let i=0;i<3;i++){frameMin[i]=Math.min(frameMin[i],point[i]);frameMax[i]=Math.max(frameMax[i],point[i])}};
for(const box of data.boxes.filter(item=>item.role==='front_left'||item.role==='front_right')){
 const [x,y,z]=box.origin,[w,h,d]=box.size,isLeft=box.role==='front_left',hx=isLeft?x:x+w,hz=z+d/2,turn=isLeft?1:-1;
 for(const xx of [x,x+w])for(const yy of [y,y+h])for(const zz of [z,z+d])for(let deg=0;deg<=90;deg++){
  const a=turn*deg*Math.PI/180,c=Math.cos(a),s=Math.sin(a),dx=xx-hx,dz=zz-hz;
  includeFramePoint([hx+dx*c+dz*s,yy,hz-dx*s+dz*c]);
 }
}
for(const drawer of data.drawers){
 const travel=drawer.depth_mm*.2;
 for(const box of data.boxes.filter(item=>drawer.piece_ids.includes(item.id))){
  includeFramePoint([box.origin[0],box.origin[1],box.origin[2]-travel]);
  includeFramePoint([box.origin[0]+box.size[0],box.origin[1]+box.size[1],box.origin[2]+box.size[2]-travel]);
 }
}
const axes=['X (horizontal)','Y (vertical)','Z (fondo)'];"""
    scoped_frame_block = """let pivot=mins.map((value,i)=>(value+maxs[i])/2);
// Shared review-only movement AABB; this never validates hinge or slide hardware.
const movementFrame=(boxes,baseMin=null,baseMax=null)=>{
 const low=baseMin?baseMin.slice():[Infinity,Infinity,Infinity],high=baseMax?baseMax.slice():[-Infinity,-Infinity,-Infinity];
 const include=point=>{for(let i=0;i<3;i++){low[i]=Math.min(low[i],point[i]);high[i]=Math.max(high[i],point[i])}};
 for(const box of boxes){
  const [x,y,z]=box.origin,[w,h,d]=box.size;
  for(const xx of [x,x+w])for(const yy of [y,y+h])for(const zz of [z,z+d])include([xx,yy,zz]);
  if(box.role==='front_left'||box.role==='front_right'){
   const isLeft=box.role==='front_left',hx=isLeft?x:x+w,hz=z+d/2,turn=isLeft?1:-1;
   for(const xx of [x,x+w])for(const yy of [y,y+h])for(const zz of [z,z+d])for(let deg=0;deg<=90;deg++){
    const a=turn*deg*Math.PI/180,c=Math.cos(a),s=Math.sin(a),dx=xx-hx,dz=zz-hz;
    include([hx+dx*c+dz*s,yy,hz-dx*s+dz*c]);
   }
  }
  const drawer=drawerByPiece.get(box.id);
  if(drawer){const travel=drawer.depth_mm*.2;for(const xx of [x,x+w])for(const yy of [y,y+h])for(const zz of [z,z+d])include([xx,yy,zz-travel]);}
 }
 return {min:low,max:high};
};
const fullFrame=movementFrame(data.boxes,mins,maxs);let frameMin=fullFrame.min.slice(),frameMax=fullFrame.max.slice();
const axes=['X (horizontal)','Y (vertical)','Z (fondo)'];"""
    substitutions = (
        ('</style>', _MODULE_CSS + '</style>'),
        ("<section class=\"stage-wrap\"><div class=\"stage\">",
         "<section class=\"stage-wrap\"><div class=\"module-stage-bar\" id=\"moduleStageBar\"><output id=\"selectionStatus\" aria-live=\"polite\">Conjunto completo · clic: seleccionar; doble clic: enfocar</output><button type=\"button\" id=\"returnToSet\" disabled>← Volver al conjunto</button></div><div class=\"stage\">"),
        ('<fieldset><legend>Panel seleccionado</legend>',
         _MODULE_UI + '<fieldset><legend>Panel seleccionado</legend>'),
        ('const data=JSON.parse(document.getElementById(\'scene-data\').textContent);',
         'const data=JSON.parse(document.getElementById(\'scene-data\').textContent);\n'
         'let selectedModuleKey=\'\',focusedModuleKey=\'\',wallObjectUrl=null,savedGroupZoom=null,focusPriorityOverrides=0;'),
        (frame_block, scoped_frame_block),
        ('function render(){', "function render(){focusPriorityOverrides=0;\n const selectionStatus=document.getElementById('selectionStatus'),returnButton=document.getElementById('returnToSet');\n if(selectionStatus&&returnButton){const item=data.module_index.find(value=>value.group_id+'::'+value.module_id===selectedModuleKey);selectionStatus.textContent=item?(focusedModuleKey?'Mueble aislado: ':'Mueble seleccionado: ')+item.group_id+' · '+item.module_id:'Conjunto completo · clic: seleccionar; doble clic: enfocar';returnButton.hidden=false;returnButton.disabled=!selectedModuleKey&&!focusedModuleKey;}"),
        ("if(selected===selectedPiece&&edge){",
         "const moduleSelected=Boolean(!focusedModuleKey&&selectedModuleKey&&ownerBox.module_id&&ownerBox.group+'::'+ownerBox.module_id===selectedModuleKey);\n  if((selected===selectedPiece||moduleSelected)&&edge){"),
        ('let depth,owners,faceIds,canvas,ctx,imageData;',
         'let depth,owners,faceIds,ownerPriority,canvas,ctx,imageData;'),
        ('layer.appendChild(image);',
         '''layer.appendChild(image);
 if(Array.isArray(data.support_reservations))for(const reserve of data.support_reservations){
  const [x,y,z]=reserve.origin_xyz_mm,[w,h,d]=reserve.size_xyz_mm;
  const world=[[x,y,z],[x+w,y,z],[x+w,y,z+d],[x,y,z+d],[x,y+h,z],[x+w,y+h,z],[x+w,y+h,z+d],[x,y+h,z+d]],projected=world.map(point=>P(...point));
  const edges=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]],g=E('g',{'fill':'none','stroke':'#b2691f','stroke-width':'2','stroke-dasharray':'5 4','pointer-events':'none','data-support-reservation':reserve.group_id+'::'+reserve.module_id,'aria-label':'Reserva conceptual no física'});
  for(const [a,b] of edges)g.appendChild(E('line',{x1:projected[a][0],y1:projected[a][1],x2:projected[b][0],y2:projected[b][1]}));
  g.appendChild(E('text',{x:projected[0][0],y:projected[0][1],fill:'#8b4b12','stroke':'none','font-size':'12'},`AP ${reserve.support_height_mm} · reserva conceptual`));layer.appendChild(g);
 }'''),
        ('faceIds=new Int16Array(pixelCount);faceIds.fill(-1);',
         'faceIds=new Int16Array(pixelCount);faceIds.fill(-1);ownerPriority=new Uint8Array(pixelCount);'),
        ('const faceColors=[],camera=cameraState();\n for(const entry of all){',
         'const faceColors=[],camera=cameraState();\n const renderFocusKey=typeof focusedModuleKey===\'string\'?focusedModuleKey:\'\';\n for(const entry of all){\n  const priority=renderFocusKey&&entry.box.module_id&&entry.box.group+\'::\'+entry.box.module_id===renderFocusKey?1:0;'),
        ('if(value>depth[index]+1e-5){depth[index]=value;owners[index]=entry.boxIndex;faceIds[index]=entry.faceId;}',
         'if(priority>ownerPriority[index]||(priority===ownerPriority[index]&&value>depth[index]+1e-5)){if(priority&&owners[index]>=0)focusPriorityOverrides++;depth[index]=value;owners[index]=entry.boxIndex;faceIds[index]=entry.faceId;ownerPriority[index]=priority;}'),
        ('const updateViewBox=()=>{',
         'const fullPivot=pivot.slice(),fullFrameMin=frameMin.slice(),fullFrameMax=frameMax.slice();\nconst updateViewBox=()=>{'),
        ('const color=edge?[15,46,60]:base,selectedPiece=data.boxes[owners[index]].id;',
         'const ownerBox=data.boxes[owners[index]],neighborDimmed=Boolean(focusedModuleKey&&'
         'ownerBox.module_id&&ownerBox.group+\'::\'+ownerBox.module_id!==focusedModuleKey);'
         'let color=edge?[15,46,60]:base;if(neighborDimmed)color=color.map(channel=>Math.round(255-(255-channel)*.2));'
         'const selectedPiece=ownerBox.id;'),
        ('rgba[offset+3]=255;\n }',
         'rgba[offset+3]=255;if(neighborDimmed)owners[index]=-1;\n }'),
        ("href:dataUrl,'data-depth-tested':'true','data-piece-count':data.boxes.length});",
         "href:dataUrl,'data-depth-tested':'true','data-piece-count':data.boxes.length,"
         "'data-selected-module':selectedModuleKey,'data-focused-module':focusedModuleKey,'data-neighbor-opacity':focusedModuleKey?'0.20':'0',"
         "'data-focused-priority-overrides':focusPriorityOverrides});"),
        ("picker.addEventListener('change',()=>pick(data.boxes.find(box=>box.id===picker.value)));",
         "picker.addEventListener('change',()=>{const box=data.boxes.find(item=>item.id===picker.value);if(box)pick(box)});"),
        ('</script></body></html>', _MODULE_SCRIPT + '</script></body></html>'),
    )
    for old, new in substitutions:
        if html.count(old) != 1:
            raise RoomViewerError("Plantilla D19 no coincide con los puntos de extensión aprobados")
        html = html.replace(old, new, 1)
    return html


def render_room_3d_html(
    review: dict[str, Any], *, module_edit_request: dict[str, Any] | None = None,
) -> str:
    """Render a self-contained offline review from a verified room result."""
    data = _payload(review)
    if module_edit_request is not None:
        from .room_review_package import _validate_source_request
        if (type(module_edit_request) is not dict
                or "module_edit_revisions" not in module_edit_request):
            raise RoomViewerError("Solicitud M6 offline ausente o sin contrato de edición")
        try:
            _validate_source_request(module_edit_request)
        except ValueError as exc:
            raise RoomViewerError("Solicitud M6 offline no válida") from exc
        if "module_edit_index" not in data:
            raise RoomViewerError("Índice M6 requerido para guardar solicitud offline")
        data["module_edit_request"] = module_edit_request
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = _HTML.replace("__SCENE_DATA__", payload)
    if "module_index" in data:
        html = _module_editor_html(html)
    return html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visor isométrico nominal autónomo, sin CAD de taller")
    parser.add_argument("--input", type=Path, required=True,
                        help="Solicitud original room_layout_v1 con module_spec (NO CAD provisto)")
    parser.add_argument("--output", type=Path, required=True,
                        help="Ruta nueva para un único HTML offline")
    args = parser.parse_args(argv)
    if not args.input.is_file() or args.input.stat().st_size > _MAX_SIZE:
        parser.error("La solicitud no existe o excede el límite seguro")
    request = json.loads(args.input.read_text(encoding="utf-8"))
    if type(request) is not dict or request.get("review_kind") != "room_layout_v1":
        parser.error("Se requiere solicitud original room_layout_v1")
    # A client-supplied world_boxes/geometry payload is explicitly rejected.
    if set(request) != {"review_kind", "assemblies", "service_zones"}:
        parser.error("Solicitud con campos ajenos a Maestro: NO se acepta CAD del cliente")
    from .room_spatial import review_room_from_specs
    room = review_room_from_specs(request)
    html = render_room_3d_html(room)
    with args.output.open("x", encoding="utf-8") as f:
        f.write(html)
    print(f"D18=REVIEW_ONLY | HTML={args.output} | PIECES={len(room['world_boxes'])} | "
          f"ROOM_STATUS={room['status']} | RELEASE=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
