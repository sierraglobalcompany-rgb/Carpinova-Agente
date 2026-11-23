"""Conversational, review-only coordination for a linear kitchen.

Each cabinet remains an ordinary guided-design request handled by Maestro/F1/F6.
This module only carries independent group conversations, declared XYZ origins,
CADExchange bounds, and a canonical layout digest. Client state is untrusted.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from .cad_exchange import cad_exchange, validate_exchange
from .conversation_flow import prepare_guided_design_v1
from .maestro import MaestroError, consult_maestro


_GROUPS = ("BAJO", "ALTO", "TORRE")
_FAMILIES = {"BAJO": "BASE_CABINET", "ALTO": "WALL_CABINET",
             "TORRE": "TOWER_CABINET"}
_VERSION = "kitchen_linear_v1"
_MAX_TURNS = 16
_MAX_UTTERANCE = 2000
_MAX_ORIGIN_MM = 10000
_POSITION = re.compile(
    r"^\s*(?:ubicar|mover)\s+(BAJO|ALTO|TORRE)\s*:\s*"
    r"X\s*=\s*(\d+)\s*mm\s*,\s*Y\s*=\s*(\d+)\s*mm\s*,\s*"
    r"Z\s*=\s*(\d+)\s*mm\s*$", re.IGNORECASE,
)
_POSITION_INTENT = re.compile(r"^\s*(?:ubicar|mover)\b", re.IGNORECASE)
_CUT_INTENT = re.compile(r"\blisto\s+para\s+(?:cortar|fabricar)\b", re.IGNORECASE)
_FLAGS = {
    "fabrication_ready": False, "cutting_ready": False,
    "drilling_ready": False, "purchase_ready": False,
    "can_generate_f7c": False,
}


def _canonical_sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _empty_working() -> dict[str, Any]:
    return {
        "groups": {group: {"history": []} for group in _GROUPS},
        "positions": {group: None for group in _GROUPS},
    }


def _validate_working(value: Any, field: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {"groups", "positions"}:
        raise MaestroError(f"{field} debe contener solo groups y positions.")
    groups, positions = value["groups"], value["positions"]
    if type(groups) is not dict or set(groups) != set(_GROUPS):
        raise MaestroError(f"{field}.groups debe declarar BAJO, ALTO y TORRE.")
    total_turns = 0
    clean_groups: dict[str, dict[str, list[str]]] = {}
    for group in _GROUPS:
        entry = groups[group]
        if type(entry) is not dict or set(entry) != {"history"}:
            raise MaestroError(f"{field}.groups.{group} contiene campos no permitidos.")
        history = entry["history"]
        if (type(history) is not list or len(history) > _MAX_TURNS
                or any(type(item) is not str or not item.strip()
                       or len(item) > _MAX_UTTERANCE for item in history)):
            raise MaestroError(f"Historial natural inválido para {group}.")
        total_turns += len(history)
        clean_groups[group] = {"history": list(history)}
    if total_turns > _MAX_TURNS:
        raise MaestroError("El conjunto excede el máximo de 16 turnos naturales.")
    if type(positions) is not dict or set(positions) != set(_GROUPS):
        raise MaestroError(f"{field}.positions debe declarar BAJO, ALTO y TORRE.")
    clean_positions: dict[str, list[int] | None] = {}
    for group, origin in positions.items():
        if origin is None:
            clean_positions[group] = None
        elif (type(origin) is list and len(origin) == 3
              and all(type(n) is int and 0 <= n <= _MAX_ORIGIN_MM for n in origin)):
            clean_positions[group] = list(origin)
        else:
            raise MaestroError(f"Origen XYZ inválido para {group}; use tres enteros mm no negativos.")
    return {"groups": clean_groups, "positions": clean_positions}


def _validate_state(value: Any) -> dict[str, Any]:
    if value is None:
        return {
            "schema_version": _VERSION, "working": _empty_working(),
            "last_valid": None, "pending_candidate": None,
        }
    if type(value) is not dict or set(value) != {
        "schema_version", "working", "last_valid", "pending_candidate",
    } or value.get("schema_version") != _VERSION:
        raise MaestroError("review_state no cumple el esquema kitchen_linear_v1.")
    working = _validate_working(value["working"], "working")
    last = value["last_valid"]
    if last is not None:
        if type(last) is not dict or set(last) != {"groups", "positions", "layout_sha256"}:
            raise MaestroError("last_valid no cumple el esquema de instantánea.")
        last_working = _validate_working(
            {"groups": last["groups"], "positions": last["positions"]}, "last_valid",
        )
        if type(last["layout_sha256"]) is not str or not re.fullmatch(
                r"[0-9a-f]{64}", last["layout_sha256"]):
            raise MaestroError("last_valid.layout_sha256 inválido.")
        last = {**last_working, "layout_sha256": last["layout_sha256"]}
    pending = value["pending_candidate"]
    if pending is not None:
        if type(pending) is not dict or set(pending) != {
            "status", "base_layout_sha256", "candidate_layout_sha256",
        }:
            raise MaestroError("pending_candidate contiene campos no permitidos.")
        if (type(pending["status"]) is not str
                or pending["status"] not in {"PENDING_REVIEW", "PENDING_COLLISION"}):
            raise MaestroError("pending_candidate.status inválido.")
        for key in ("base_layout_sha256", "candidate_layout_sha256"):
            digest = pending[key]
            if digest is not None and (type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                raise MaestroError(f"pending_candidate.{key} inválido.")
        pending = dict(pending)
    return {"schema_version": _VERSION, "working": working,
            "last_valid": last, "pending_candidate": pending}


def _rebuild_group(group: str, history: list[str]) -> dict[str, Any]:
    review: dict[str, Any] | None = None
    review_state: dict[str, Any] | None = None
    for utterance in history:
        review = prepare_guided_design_v1({
            "review_kind": "guided_design_v1", "utterance": utterance,
            "review_state": review_state, "review_updates": [],
            "photo_observations": None,
        })
        review_state = review["review_state"]
    if review is None:
        return {"group_id": group, "status": "NEEDS_USER_CONFIRMATION",
                "questions": ["Describe este grupo con medidas y construcción."]}
    request = review.get("nominal_draft_request")
    if _CUT_INTENT.search(" ".join(history)):
        return {"group_id": group, "status": "CONCEPT_ONLY",
                "questions": ["La solicitud de corte queda bloqueada; mantén esta revisión solo nominal."],
                "warnings": ["PRODUCTION_REQUEST_BLOCKED"]}
    if request is None:
        concept = review.get("nominal_draft_scope") == "CONCEPT_ONLY"
        return {
            "group_id": group,
            "status": "CONCEPT_ONLY" if concept else "NEEDS_USER_CONFIRMATION",
            "questions": ([review.get("nominal_draft_next_question")]
                          if review.get("nominal_draft_next_question") else
                          [item.get("question", "Confirma las decisiones pendientes.")
                           for item in review.get("questions", [])]),
            "warnings": list(review.get("nominal_draft_warnings", [])),
            "nominal_draft_blockers": list(review.get("nominal_draft_blockers", [])),
        }
    try:
        answer = consult_maestro(request)
        model = answer.get("modular")
        if (type(model) is not dict or answer.get("status") != "DRAFT_NOT_FOR_CUTTING"
                or model.get("status") != "DRAFT_NOT_FOR_CUTTING"
                or any(answer.get(flag) is not False for flag in (
                    "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"))
                or any(model.get(flag) is not False for flag in (
                    "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"))
                or ("can_generate_f7c" in model and model["can_generate_f7c"] is not False)):
            raise MaestroError("Maestro no devolvió un modelo modular nominal.")
        exchange = validate_exchange(cad_exchange(model))
    except (MaestroError, ValueError, TypeError) as exc:
        return {"group_id": group, "status": "CONCEPT_ONLY",
                "questions": ["El modelo no superó la validación Maestro/CADExchange."],
                "warnings": [type(exc).__name__ + ": " + str(exc)]}
    return {
        "group_id": group, "family": _FAMILIES[group], "status": "REVIEW_ONLY_VALID",
        "model": model, "exchange": exchange,
        "_trusted_nominal_request": copy.deepcopy(request),
        "warnings": list(dict.fromkeys([
            *review.get("nominal_draft_warnings", []),
            *answer.get("warnings", []),
        ])),
        "questions": [],
    }


def _build(working: dict[str, Any]) -> dict[str, Any]:
    reviews = {group: _rebuild_group(group, working["groups"][group]["history"])
               for group in _GROUPS}
    public_groups: list[dict[str, Any]] = []
    layout_entries: list[dict[str, Any]] = []
    global_ids: list[str] = []
    all_warnings: list[str] = []
    for group in _GROUPS:
        result = reviews[group]
        origin = working["positions"][group]
        all_warnings.extend(result.get("warnings", []))
        if result.get("status") != "REVIEW_ONLY_VALID":
            public_groups.append({
            "group_id": group, "family": _FAMILIES[group], "origin_xyz_mm": origin,
                "bounds_xyz_mm": None, "piece_count": 0,
                "geometry_sha256": None, "status": result["status"],
                "questions": result.get("questions", []),
                "warnings": result.get("warnings", []),
            })
            continue
        exchange = result["exchange"]
        bounds = list(exchange["bounds_xyz_mm"])
        digest = exchange["geometry_sha256"]
        public_groups.append({
            "group_id": group, "family": result["family"],
            "origin_xyz_mm": origin, "bounds_xyz_mm": bounds,
            "piece_count": len(exchange["boxes"]), "geometry_sha256": digest,
            "status": result["status"], "warnings": result["warnings"],
        })
        layout_entries.append({
            "group_id": group, "geometry_sha256": digest,
            "bounds_xyz_mm": bounds, "origin_xyz_mm": origin,
        })
        global_ids.extend(f"{group}:{box['piece_id']}" for box in exchange["boxes"])
    collisions: list[dict[str, Any]] = []
    ready = [item for item in public_groups
             if item["geometry_sha256"] is not None and item["origin_xyz_mm"] is not None]
    for index, left in enumerate(ready):
        for right in ready[index + 1:]:
            axes = []
            for axis, name in enumerate(("X", "Y", "Z")):
                a0 = left["origin_xyz_mm"][axis]
                a1 = a0 + left["bounds_xyz_mm"][axis]
                b0 = right["origin_xyz_mm"][axis]
                b1 = b0 + right["bounds_xyz_mm"][axis]
                if max(a0, b0) < min(a1, b1):
                    axes.append({"axis": name, "left_interval_mm": [a0, a1],
                                 "right_interval_mm": [b0, b1]})
            if len(axes) == 3:
                collisions.append({"groups": [left["group_id"], right["group_id"]],
                                   "overlap_axes": axes})
    digest = (_canonical_sha(sorted(layout_entries, key=lambda item: item["group_id"]))
              if layout_entries else None)
    complete = (len(public_groups) == 3 and all(
        item["status"] == "REVIEW_ONLY_VALID" and item["origin_xyz_mm"] is not None
        for item in public_groups))
    assemblage_status = (
        "REVIEW_ONLY_VALID" if complete and not collisions else
        "CONCEPT_ONLY" if any(item["status"] == "CONCEPT_ONLY" for item in public_groups)
        else "NEEDS_USER_CONFIRMATION"
    )
    if collisions:
        assemblage_status = "NEEDS_USER_CONFIRMATION"
    if len(global_ids) != len(set(global_ids)):
        raise MaestroError("Identificadores de pieza globales duplicados.")
    return {
        "groups": public_groups, "layout_sha256": digest,
        "global_piece_ids": global_ids, "piece_count": len(global_ids),
        "collisions": collisions, "assemblage_status": assemblage_status,
        "warnings": list(dict.fromkeys(all_warnings)),
        "_reviews": reviews,
    }


def _same_working(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left == right


def _snapshot(working: dict[str, Any], built: dict[str, Any]) -> dict[str, Any]:
    return {"groups": copy.deepcopy(working["groups"]),
            "positions": copy.deepcopy(working["positions"]),
            "layout_sha256": built["layout_sha256"]}


def review_linear_kitchen(request: dict[str, Any]) -> dict[str, Any]:
    """Review one kitchen group/position turn through existing deterministic engines."""
    if type(request) is not dict or set(request) != {
        "review_kind", "target_group", "utterance", "review_state",
    } or request.get("review_kind") != _VERSION:
        raise MaestroError("kitchen_linear_v1 exige review_kind, target_group, utterance y review_state.")
    group = request["target_group"]
    utterance = request["utterance"]
    if group not in _GROUPS:
        raise MaestroError("target_group debe ser BAJO, ALTO o TORRE.")
    if type(utterance) is not str or not utterance.strip() or len(utterance) > _MAX_UTTERANCE:
        raise MaestroError("utterance debe tener 1–2000 caracteres.")
    state = _validate_state(request["review_state"])
    if len(json.dumps(state, ensure_ascii=False).encode("utf-8")) > 56000:
        raise MaestroError("review_state se acerca al límite MCP; no se truncó.")

    # Rebuild last_valid from natural histories; supplied hashes/models are never trusted.
    old_last_working = None
    old_last_built = None
    if state["last_valid"] is not None:
        candidate_last = {"groups": state["last_valid"]["groups"],
                          "positions": state["last_valid"]["positions"]}
        old_last_built = _build(candidate_last)
        if (old_last_built["assemblage_status"] != "REVIEW_ONLY_VALID"
                or old_last_built["layout_sha256"] != state["last_valid"]["layout_sha256"]):
            raise MaestroError("last_valid no pudo revalidarse; se rechazó sin usar sus hashes.")
        old_last_working = candidate_last

    working = copy.deepcopy(state["working"])
    match = _POSITION.fullmatch(utterance)
    if match:
        named_group = match.group(1).upper()
        if named_group != group:
            raise MaestroError("La coordenada debe corresponder al target_group seleccionado.")
        if not working["groups"][group]["history"]:
            raise MaestroError("El grupo aún no existe; descríbalo antes de declarar su ubicación.")
        origin = [int(match.group(index)) for index in (2, 3, 4)]
        if any(value > _MAX_ORIGIN_MM for value in origin):
            raise MaestroError("Cada origen XYZ debe ser como máximo 10000 mm.")
        working["positions"][group] = origin
    elif _POSITION_INTENT.match(utterance):
        raise MaestroError("Ubicación ambigua: use Ubicar/Mover GRUPO: X=n mm, Y=n mm, Z=n mm.")
    else:
        total = sum(len(working["groups"][item]["history"]) for item in _GROUPS)
        if total >= _MAX_TURNS:
            raise MaestroError("Se alcanzó el máximo de 16 turnos naturales; no se truncó el historial.")
        working["groups"][group]["history"].append(utterance)

    if len(json.dumps(working, ensure_ascii=False).encode("utf-8")) > 28000:
        raise MaestroError("El historial del conjunto excede su límite seguro; no se truncó.")
    built = _build(working)
    valid = built["assemblage_status"] == "REVIEW_ONLY_VALID"
    last_valid = state["last_valid"]
    pending = None
    last_built_for_summary = old_last_built
    if valid:
        last_valid = _snapshot(working, built)
        last_built_for_summary = built
    elif last_valid is not None and not _same_working(working, old_last_working):
        pending = {
            "status": "PENDING_COLLISION" if built["collisions"] else "PENDING_REVIEW",
            "base_layout_sha256": old_last_built["layout_sha256"],
            "candidate_layout_sha256": built["layout_sha256"],
        }
    new_state = {
        "schema_version": _VERSION, "working": working,
        "last_valid": last_valid, "pending_candidate": pending,
    }
    review_state_public = copy.deepcopy(new_state)
    last_public = None
    if last_valid is not None:
        last_public = {"layout_sha256": last_valid["layout_sha256"],
                       "positions": copy.deepcopy(last_valid["positions"]),
                       "groups": [
                           {"group_id": item["group_id"],
                            "geometry_sha256": item["geometry_sha256"],
                            "bounds_xyz_mm": item["bounds_xyz_mm"]}
                           for item in last_built_for_summary["groups"]
                       ]}
    summary = {key: value for key, value in built.items() if key != "_reviews"}
    questions = [
        {"group_id": item["group_id"], "question": question}
        for item in summary["groups"] for question in item.get("questions", [])
    ]
    return {
        "review_kind": _VERSION, "status": summary["assemblage_status"],
        **summary, "questions": questions, "last_valid_summary": last_public,
        "pending_candidate": copy.deepcopy(pending),
        "review_state": review_state_public,
        "next_step": ("Revisar las preguntas por grupo y declarar cada origen XYZ explícitamente."
                      if not valid else
                      "Revisión nominal conjunta; la instalación y la fabricación siguen fuera de alcance."),
        **_FLAGS,
    }
