"""First furniture pilot: one Maestro request -> audited draft review bundle.

This is an offline local developer bridge, NOT an MCP tool or a fabrication
service. No LLM, CAD application, network or third-party executable is run.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from typing import Any

from .cad_exchange import cad_exchange, validate_exchange
from .conversation_flow import _guided_hardware_review, validate_flow_review
from .core import DesignError
from .wall_bar_delivery import review_files
from .maestro import MaestroError, consult_maestro
from .modular_outputs import modular_bom_csv, modular_front_svg
from .drawer_modules import OPENING_SYSTEMS
from knowledge_client.reader import BundleError, load_bundle

_BLOCKED_FLAGS = ("fabrication_ready", "cutting_ready",
                  "drilling_ready", "purchase_ready")
_FILES = ("maestro-review.json", "front-review.svg",
          "parts-review.csv", "cad-exchange.json", "manifest.json")
_MAX_MANIFEST_BYTES = 65536
_MAX_BOOK_REQUEST_BYTES = 32768
_OPENING_REVIEW_FILE = "opening-intents-review.json"
_MAX_OPENING_REVIEW_BYTES = 16384
_HARDWARE_REFERENCE_FILE = "hardware-reference-review.json"
_MAX_HARDWARE_REFERENCE_BYTES = 262144
_HARDWARE_REFERENCE_CONTRACT = "B4_DECLARED_SOURCE_V1"
_HARDWARE_SOURCE_REQUEST_FIELD = "hardware_reference_source_request"
_OPENING_FIELDS = frozenset((
    "piece_id", "module_id", "element_type", "opening_system",
))
_FRONT_ROLES = frozenset(("front_left", "front_right", "front_single"))


class PilotError(ValueError):
    """An unapproved or inconsistent proposal cannot yield a pilot bundle."""


class BookEvidenceError(PilotError):
    """A book-backed proposal cannot be generated or verified safely."""


def _opening_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PilotError("opening_review_json contiene una clave duplicada.")
        result[key] = value
    return result


def _opening_constant(value: str) -> None:
    raise PilotError("opening_review_json no admite cifras no finitas.")


def _opening_review_payload(raw: str) -> dict[str, Any]:
    if type(raw) is not str or not raw.strip():
        raise PilotError("opening_review_json debe ser texto JSON no vacío.")
    try:
        encoded = raw.encode("utf-8")
    except UnicodeError as exc:
        raise PilotError("opening_review_json no es UTF-8 válido.") from exc
    if len(encoded) > _MAX_OPENING_REVIEW_BYTES:
        raise PilotError("opening_review_json supera 16 KiB.")
    try:
        value = json.loads(
            raw, object_pairs_hook=_opening_pairs, parse_constant=_opening_constant,
        )
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise PilotError("opening_review_json no contiene JSON válido.") from exc
    if type(value) is not dict or set(value) != {
        "schema_version", "source", "geometry_sha256", "elements",
    }:
        raise PilotError("opening_review_json no cumple el esquema estricto 1.0.")
    if (value["schema_version"] != "1.0"
            or value["source"] != "CLIENT_DECLARED_NOT_AUTHENTICATED"
            or type(value["geometry_sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", value["geometry_sha256"])):
        raise PilotError("opening_review_json tiene versión, fuente o SHA inválido.")
    elements = value["elements"]
    if type(elements) is not list or not 1 <= len(elements) <= 128:
        raise PilotError("opening_review_json requiere de 1 a 128 elementos.")
    seen: set[str] = set()
    for element in elements:
        if type(element) is not dict or set(element) != _OPENING_FIELDS:
            raise PilotError("Cada apertura requiere exactamente cuatro campos.")
        if any(type(element[key]) is not str or not element[key].strip()
               or len(element[key]) > 160 for key in _OPENING_FIELDS):
            raise PilotError("IDs e intenciones de apertura deben ser texto acotado.")
        if element["piece_id"] in seen:
            raise PilotError("opening_review_json contiene IDs de pieza duplicados.")
        seen.add(element["piece_id"])
        if (element["element_type"] not in ("door", "drawer")
                or element["opening_system"] not in OPENING_SYSTEMS):
            raise PilotError("Tipo o intención de apertura no admitidos.")
    return value


def _opening_review_for_cad(
    payload: dict[str, Any], exchange: dict[str, Any],
) -> dict[str, Any]:
    if payload["geometry_sha256"] != exchange["geometry_sha256"]:
        raise PilotError("opening_review_json pertenece a otro geometry_sha256.")
    actual: dict[str, tuple[str, str]] = {}
    for box in exchange["boxes"]:
        role = box.get("role")
        if role in _FRONT_ROLES or role == "drawer_facade":
            piece_id, module_id = box.get("piece_id"), box.get("module_id")
            element_type = "drawer" if role == "drawer_facade" else "door"
            if type(piece_id) is not str or type(module_id) is not str:
                raise PilotError("CADExchange tiene una fachada sin IDs válidos.")
            if piece_id in actual:
                raise PilotError("CADExchange contiene IDs de fachada duplicados.")
            actual[piece_id] = (module_id, element_type)
    declared = {
        item["piece_id"]: (item["module_id"], item["element_type"])
        for item in payload["elements"]
    }
    if declared != actual:
        raise PilotError(
            "opening_review_json no coincide exactamente con las fachadas de CADExchange."
        )
    return {
        "schema_version": "1.0",
        "source": "CLIENT_DECLARED_NOT_AUTHENTICATED",
        "geometry_sha256": exchange["geometry_sha256"],
        "elements": sorted(payload["elements"], key=lambda item: item["piece_id"]),
        "status": "NOT_APPROVED_NOT_FOR_FABRICATION",
        "hardware_selected": False,
        "drilling_ready": False,
        "purchase_ready": False,
        "authentication": "NOT_AUTHENTICATED",
    }


def _validate_hardware_source_request(
    request: dict[str, Any], *, with_book_query: bool,
) -> dict[str, Any]:
    """Keep the persisted replay source small, structured and free of paths or grants."""
    try:
        raw = json.dumps(
            request, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        )
        normalized = json.loads(
            raw, object_pairs_hook=_opening_pairs, parse_constant=_opening_constant,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise PilotError("HARDWARE_SOURCE_REQUEST_INVALID: JSON no reproducible.") from exc
    if type(normalized) is not dict or normalized != request:
        raise PilotError("HARDWARE_SOURCE_REQUEST_INVALID: la solicitud no se normaliza.")
    if len(raw.encode("utf-8")) > _MAX_BOOK_REQUEST_BYTES:
        raise PilotError("HARDWARE_SOURCE_REQUEST_TOO_LARGE: máximo 32 KiB.")
    allowed = ({"action", "module_spec", "query", "evidence_topic"}
               if with_book_query else {"action", "module_spec"})
    required = {"action", "module_spec", "query"} if with_book_query else {
        "action", "module_spec",
    }
    if (set(normalized) - allowed or required - set(normalized)
            or normalized.get("action") != "modular"
            or type(normalized.get("module_spec")) is not dict
            or (("query" in normalized) != with_book_query)):
        raise PilotError(
            "HARDWARE_SOURCE_REQUEST_INVALID: se requiere action=modular/module_spec "
            "y, solo en el contrato Knowledge, query."
        )

    forbidden_key_parts = (
        "path", "url", "uri", "approval", "approved", "authorization",
        "authorized", "ticket", "token", "credential",
    )
    blocked_grant_values = set(_BLOCKED_FLAGS) | {
        "approved", "authorized", "owner_approved", "authorization_granted",
    }

    def inspect(value: Any) -> None:
        if type(value) is dict:
            for key, child in value.items():
                if type(key) is not str:
                    raise PilotError("HARDWARE_SOURCE_REQUEST_INVALID: clave no textual.")
                folded = key.casefold()
                key_parts = set(re.split(r"[^a-z0-9]+", folded))
                if (key_parts.intersection(forbidden_key_parts)
                        or folded in _BLOCKED_FLAGS):
                    raise PilotError(
                        "HARDWARE_SOURCE_REQUEST_INVALID: ruta, URL o marcador de "
                        "autorización no admitido."
                    )
                inspect(child)
        elif type(value) is list:
            for child in value:
                inspect(child)
        elif type(value) is str:
            if (re.search(r"(?i)(?:https?|ftp|file)://", value)
                    or re.match(r"^(?:[A-Za-z]:[\\/]|\\\\|/|\.\.?[\\/])", value)
                    or re.search(r"(?:^|[\\/])\.\.(?:[\\/]|$)", value)):
                raise PilotError(
                    "HARDWARE_SOURCE_REQUEST_INVALID: la fuente no puede contener rutas o URL."
                )
            normalized_value = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
            if normalized_value in blocked_grant_values:
                raise PilotError(
                    "HARDWARE_SOURCE_REQUEST_INVALID: marcador de autorización no admitido."
                )
        elif value is not None and type(value) not in (bool, int, float):
            raise PilotError("HARDWARE_SOURCE_REQUEST_INVALID: valor no JSON.")

    inspect(normalized)
    return normalized


def _hardware_context_modules(
    source_request: dict[str, Any], model: dict[str, Any],
    exchange: dict[str, Any], opening_review: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Match declared drawer records to Maestro and CAD before temporary enrichment."""
    spec = source_request["module_spec"]
    if spec.get("type") == "wall_bar":
        source_modules = [spec.get("cabinet_module")]
    else:
        source_modules = spec.get("modules")
    model_modules = model.get("modules")
    if (type(source_modules) is not list or not source_modules
            or any(type(item) is not dict for item in source_modules)
            or type(model_modules) is not list):
        raise PilotError("HARDWARE_SOURCE_MODULES_MISMATCH: módulos ausentes o inválidos.")

    source_by_id: dict[str, dict[str, Any]] = {}
    for source in source_modules:
        module_id = source.get("module_id")
        if type(module_id) is not str or not module_id or module_id in source_by_id:
            raise PilotError("HARDWARE_SOURCE_MODULES_MISMATCH: module_id duplicado o inválido.")
        source_by_id[module_id] = source
    model_by_id: dict[str, dict[str, Any]] = {}
    for module in model_modules:
        if type(module) is not dict:
            raise PilotError("HARDWARE_MAESTRO_MODULES_MISMATCH.")
        module_id = module.get("module_id")
        if type(module_id) is not str or not module_id or module_id in model_by_id:
            raise PilotError("HARDWARE_MAESTRO_MODULES_MISMATCH: module_id duplicado.")
        model_by_id[module_id] = module
    if set(source_by_id) != set(model_by_id):
        raise PilotError("HARDWARE_SOURCE_MODULES_MISMATCH: IDs difieren de Maestro.")

    part_by_id: dict[str, dict[str, Any]] = {}
    for part in model.get("parts", []):
        if type(part) is not dict or type(part.get("piece_id")) is not str:
            raise PilotError("HARDWARE_MAESTRO_PARTS_INVALID.")
        if part["piece_id"] in part_by_id:
            raise PilotError("HARDWARE_MAESTRO_PARTS_INVALID: piece_id duplicado.")
        part_by_id[part["piece_id"]] = part
    cad_by_id: dict[str, dict[str, Any]] = {}
    for box in exchange.get("boxes", []):
        if type(box) is not dict or type(box.get("piece_id")) is not str:
            raise PilotError("HARDWARE_CAD_PARTS_INVALID.")
        if box["piece_id"] in cad_by_id:
            raise PilotError("HARDWARE_CAD_PARTS_INVALID: piece_id duplicado.")
        cad_by_id[box["piece_id"]] = box

    for element in opening_review.get("elements", []):
        piece_id = element.get("piece_id")
        module_id = element.get("module_id")
        element_type = element.get("element_type")
        part = part_by_id.get(piece_id)
        box = cad_by_id.get(piece_id)
        expected_roles = (
            {"drawer_facade"} if element_type == "drawer" else _FRONT_ROLES
        )
        if (module_id not in source_by_id
                or part is None or part.get("module_id") != module_id
                or part.get("role") not in expected_roles
                or box is None or box.get("module_id") != module_id
                or box.get("role") != part.get("role")):
            raise PilotError(
                "HARDWARE_SOURCE_FACADE_MISMATCH: module_id/piece_id/tipo "
                "no coincide con la solicitud, Maestro y CAD."
            )

    drawer_by_piece: dict[str, dict[str, Any]] = {}
    drawer_module_by_piece: dict[str, str] = {}
    drawer_ids_by_module: dict[str, list[str]] = {}
    for module_id, source in source_by_id.items():
        raw_drawers = source.get("drawers", "none")
        if type(raw_drawers) is list:
            drawer_ids: list[str] = []
            for drawer in raw_drawers:
                if type(drawer) is not dict:
                    raise PilotError("HARDWARE_SOURCE_DRAWERS_INVALID.")
                drawer_id = drawer.get("drawer_id")
                if (type(drawer_id) is not str or not drawer_id
                        or drawer_id in drawer_ids):
                    raise PilotError(
                        "HARDWARE_SOURCE_DRAWERS_INVALID: drawer_id duplicado o inválido."
                    )
                drawer_ids.append(drawer_id)
                piece_id = f"{module_id}-{drawer_id}-DRAWER_FACADE"
                if piece_id in drawer_by_piece:
                    raise PilotError("HARDWARE_SOURCE_DRAWERS_INVALID: fachada duplicada.")
                drawer_by_piece[piece_id] = drawer
                drawer_module_by_piece[piece_id] = module_id
            drawer_ids_by_module[module_id] = drawer_ids
        elif raw_drawers in ("none", "pending", None):
            drawer_ids_by_module[module_id] = []
        else:
            raise PilotError("HARDWARE_SOURCE_DRAWERS_INVALID.")

        observed_ids = model_by_id[module_id].get("drawer_ids")
        if (type(observed_ids) is not list
                or any(type(item) is not str for item in observed_ids)
                or len(observed_ids) != len(set(observed_ids))
                or set(observed_ids) != set(drawer_ids_by_module[module_id])):
            raise PilotError(
                "HARDWARE_SOURCE_DRAWERS_MISMATCH: drawer_id difiere de Maestro."
            )

    opening_drawers = {
        item["piece_id"]: item
        for item in opening_review.get("elements", [])
        if item.get("element_type") == "drawer"
    }
    if set(opening_drawers) != set(drawer_by_piece):
        raise PilotError(
            "HARDWARE_SOURCE_DRAWERS_MISMATCH: fachadas no coinciden con el sidecar."
        )
    for piece_id, drawer in drawer_by_piece.items():
        module_id = drawer_module_by_piece[piece_id]
        source_element = opening_drawers[piece_id]
        part = part_by_id.get(piece_id)
        box = cad_by_id.get(piece_id)
        if (source_element.get("module_id") != module_id
                or part is None or part.get("module_id") != module_id
                or part.get("role") != "drawer_facade"
                or box is None or box.get("module_id") != module_id
                or box.get("role") != "drawer_facade"):
            raise PilotError(
                "HARDWARE_SOURCE_DRAWERS_MISMATCH: identidad no coincide con Maestro/CAD."
            )

    enriched = deepcopy(model_modules)
    for module in enriched:
        source = source_by_id[module["module_id"]]
        raw_drawers = source.get("drawers", "none")
        if type(raw_drawers) is list:
            module["drawers"] = deepcopy(raw_drawers)
        else:
            module.pop("drawers", None)
    return enriched, drawer_by_piece


def _hardware_reference_review(
    opening_review: dict[str, Any], model: dict[str, Any],
    exchange: dict[str, Any], source_request: dict[str, Any],
) -> dict[str, Any]:
    """Reuse the conversation flow's F4 references for validated CAD facades."""
    if opening_review.get("geometry_sha256") != exchange.get("geometry_sha256"):
        raise PilotError("La revisión de herrajes pertenece a otra geometría.")
    source_elements = opening_review.get("elements")
    if type(source_elements) is not list:
        raise PilotError("El sidecar validado no contiene elementos de apertura.")
    source_by_id = {item["piece_id"]: item for item in source_elements}
    if len(source_by_id) != len(source_elements):
        raise PilotError("El sidecar validado contiene IDs de fachada duplicados.")

    enriched_modules, drawer_sources = _hardware_context_modules(
        source_request, model, exchange, opening_review,
    )
    review = _guided_hardware_review(
        source_elements, model["parts"], enriched_modules,
    )
    if (type(review) is not dict
            or review.get("status") != "REFERENCE_ONLY_NOT_SELECTED"
            or review.get("hardware_selected") is not False
            or review.get("drilling_ready") is not False
            or review.get("purchase_ready") is not False
            or review.get("drilling_coordinates") != []):
        raise PilotError("El helper F4 no conservó el estado consultivo requerido.")
    entries = review.get("elements")
    if type(entries) is not list or len(entries) != len(source_elements):
        raise PilotError("La revisión F4 no devolvió una fila por fachada.")
    rows_by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if type(entry) is not dict:
            raise PilotError("El helper F4 devolvió una fila inválida.")
        piece_id = entry.get("piece_id")
        source = source_by_id.get(piece_id)
        if (type(piece_id) is not str or source is None or piece_id in rows_by_id
                or any(entry.get(key) != source.get(key) for key in (
                    "piece_id", "module_id", "element_type", "opening_system",
                ))
                or entry.get("hardware_selected") is not False):
            raise PilotError("La revisión F4 no coincide exactamente con el sidecar.")
        normalized_entry = {
            **entry,
            "status": "REFERENCE_ONLY_NOT_SELECTED",
            "approval_status": "NOT_APPROVED_NOT_FOR_FABRICATION",
            "fabrication_ready": False,
            "cutting_ready": False,
            "drilling_ready": False,
            "purchase_ready": False,
        }
        if source.get("element_type") == "drawer":
            drawer = drawer_sources[piece_id]
            left = drawer.get("slide_clearance_left_mm")
            right = drawer.get("slide_clearance_right_mm")
            normalized_entry["drawer_id"] = drawer["drawer_id"]
            if (type(left) is int and left >= 0
                    and type(right) is int and right >= 0):
                normalized_entry["slide_clearance_reading"] = {
                    "status": "DECLARED_REVIEW_ONLY",
                    "left_mm": left,
                    "right_mm": right,
                    "installation_status":
                        "PENDING_EXACT_SKU_DATASHEET_AND_MOUNTING",
                }
                if left == 0 or right == 0:
                    normalized_entry["blockers"] = list(dict.fromkeys(
                        normalized_entry["blockers"] + [
                            "ZERO_MM_CLEARANCES_ARE_PLACEHOLDERS_NOT_INSTALLABLE",
                        ]
                    ))
            else:
                normalized_entry["slide_clearance_reading"] = {
                    "status": "UNKNOWN",
                    "left_mm": "UNKNOWN",
                    "right_mm": "UNKNOWN",
                    "installation_status":
                        "PENDING_EXACT_SKU_DATASHEET_AND_MOUNTING",
                }
                normalized_entry["blockers"] = list(dict.fromkeys(
                    normalized_entry["blockers"] + [
                        "SLIDE_CLEARANCES_NOT_VERIFIED",
                    ]
                ))
        rows_by_id[piece_id] = normalized_entry
    if set(rows_by_id) != set(source_by_id):
        raise PilotError("La revisión F4 omitió o agregó fachadas.")
    return {
        "schema_version": "1.0",
        "source": "MAESTRO_GUIDED_HARDWARE_REFERENCE",
        "geometry_sha256": exchange["geometry_sha256"],
        "status": "REFERENCE_ONLY_NOT_SELECTED",
        "approval_status": "NOT_APPROVED_NOT_FOR_FABRICATION",
        "hardware_selected": False,
        "fabrication_ready": False,
        "cutting_ready": False,
        "drilling_ready": False,
        "purchase_ready": False,
        "elements": [rows_by_id[piece_id] for piece_id in sorted(rows_by_id)],
    }


def _book_bundle(bundle_dir: Path | str | None) -> dict[str, Any]:
    if bundle_dir is None:
        raise BookEvidenceError(
            "BLOCKED_BOOK_BUNDLE: configurar el bundle Knowledge para esta consulta."
        )
    try:
        bundle = load_bundle(bundle_dir)
    except (BundleError, OSError, TypeError, ValueError) as exc:
        raise BookEvidenceError(
            "BLOCKED_BOOK_BUNDLE: el bundle Knowledge falta o no es válido."
        ) from exc
    manifest = bundle["manifest"]
    if (bundle.get("coverage") != "FULL_BOOK"
            or manifest.get("scope") != "BOOK"
            or manifest.get("knowledge_version") != "1.2.0"
            or manifest.get("schema_version") != "0.1.0"
            or manifest.get("counts", {}).get("pages") != 252
            or manifest.get("source_page_count") != 295
            or manifest.get("excluded_page_count") != 43):
        raise BookEvidenceError(
            "BOOK_SCOPE_NOT_FULL: se requiere Knowledge BOOK 1.2.0 completo."
        )
    return bundle


def _book_source_request(request: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = json.dumps(request, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":"))
        round_trip = json.loads(raw)
    except (TypeError, ValueError, RecursionError) as exc:
        raise BookEvidenceError(
            "BOOK_SOURCE_REQUEST_INVALID: la solicitud no es JSON reproducible."
        ) from exc
    if round_trip != request:
        raise BookEvidenceError(
            "BOOK_SOURCE_REQUEST_INVALID: la solicitud cambia al serializarla."
        )
    if len(raw.encode("utf-8")) > _MAX_BOOK_REQUEST_BYTES:
        raise BookEvidenceError(
            "BOOK_SOURCE_REQUEST_TOO_LARGE: solicitud bibliográfica mayor de 32 KiB."
        )
    return round_trip


def _book_source_metadata(bundle: dict[str, Any]) -> dict[str, Any]:
    manifest = bundle["manifest"]
    return {
        "book_id": manifest["book_id"],
        "scope": manifest["scope"],
        "knowledge_version": manifest["knowledge_version"],
        "schema_version": manifest["schema_version"],
        "source_manifest_sha256": manifest["source_manifest_sha256"],
        "counts": manifest["counts"],
        "source_page_count": manifest["source_page_count"],
        "excluded_page_count": manifest["excluded_page_count"],
        "files": manifest["files"],
        "source_pdf_bytes_verified": bundle["source_pdf_bytes_verified"],
        "provenance_note": bundle["provenance_note"],
    }


def _book_source_status(answer: dict[str, Any]) -> str:
    knowledge = answer.get("knowledge")
    provenance = answer.get("source_provenance")
    if (not isinstance(knowledge, dict)
            or knowledge.get("coverage") != "FULL_BOOK"
            or knowledge.get("knowledge_version") != "1.2.0"
            or not isinstance(knowledge.get("results"), list)
            or not isinstance(provenance, list)):
        raise BookEvidenceError(
            "BLOCKED_BOOK_BUNDLE: Maestro no devolvió evidencia FULL_BOOK coherente."
        )
    if knowledge.get("total_matches") == 0:
        if knowledge["results"] or provenance:
            raise BookEvidenceError("NO_BOOK_MATCH inconsistente con las referencias.")
        return "NO_BOOK_MATCH"
    if not knowledge["results"] or len(provenance) != len(knowledge["results"]):
        raise BookEvidenceError("La procedencia del libro no coincide con resultados.")
    return "BOOK_EVIDENCE_PASS"


def pilot_review(
    request: dict[str, Any], flow_review: dict[str, Any] | None = None,
    *, bundle_dir: Path | str | None = None, opening_review_json: str = "",
) -> dict[str, str]:
    """Calculate every deliverable from one already-structured Maestro request.

    A text-only proposal or an LLM classification is NOT sufficient input.
    All downstream derivations share Maestro's one modular geometry object.
    """
    if type(request) is not dict or request.get("action") != "modular":
        raise PilotError("Piloto: se requiere action=modular con module_spec explícito.")
    has_query = "query" in request
    if has_query and flow_review is not None:
        raise BookEvidenceError(
            "BOOK_FLOW_COMBINATION_UNSUPPORTED: separar consulta del libro y flow-review."
        )
    source_request = _book_source_request(request) if has_query else None
    hardware_source_request = None
    if opening_review_json != "":
        hardware_source_request = _validate_hardware_source_request(
            source_request if has_query else request,
            with_book_query=has_query,
        )
    book = _book_bundle(bundle_dir) if has_query else None
    answer = consult_maestro(request, bundle_dir=bundle_dir)
    book_status = _book_source_status(answer) if has_query else None
    model = answer.get("modular")
    if not isinstance(model, dict) or answer["status"] != "DRAFT_NOT_FOR_CUTTING":
        raise PilotError(
            "Proyecto bloqueado: corregir medidas/distribución antes de generar el paquete."
        )
    if any(answer.get(key) is not False or model.get(key) is not False
           for key in _BLOCKED_FLAGS):
        raise PilotError("Respuesta inconsistente: bloqueos de fabricación no preservados.")
    svg = modular_front_svg(model)
    csv_text = modular_bom_csv(model)
    exchange = validate_exchange(cad_exchange(model))
    # CADExchange's strict schema deliberately exposes three release flags.
    # purchase_ready belongs to Maestro and is checked above; do not add a
    # fictitious field to the canonical geometry exchange contract.
    if any(exchange.get(key) is not False for key in (
        "fabrication_ready", "cutting_ready", "drilling_ready"
    )):
        raise PilotError("Contrato CAD inconsistente: autoridad de fabricación alterada.")
    expected = {part["piece_id"] for part in model["parts"]}
    observed = {box["piece_id"] for box in exchange["boxes"]}
    if expected != observed or len(expected) != len(model["parts"]):
        raise PilotError("CAD/BOM no coincide con piezas de geometría Maestro.")
    opening_review = None
    hardware_review = None
    if opening_review_json != "":
        opening_review = _opening_review_for_cad(
            _opening_review_payload(opening_review_json), exchange,
        )
        hardware_review = _hardware_reference_review(
            opening_review, model, exchange, hardware_source_request,
        )
    if flow_review is not None:
        if type(flow_review) is not dict:
            raise PilotError("flow-review debe ser un objeto de revisión válido.")
        try:
            validate_flow_review(flow_review, request)
        except (MaestroError, DesignError, ValueError) as exc:
            raise PilotError("Traza conversacional inválida o distinta de Maestro.") from exc
        if (flow_review.get("geometry_sha256") != exchange["geometry_sha256"]
                or flow_review.get("piece_count") != len(exchange["boxes"])):
            raise PilotError("Traza conversacional no corresponde al CAD del borrador.")
    extras = review_files(model) if model.get("wall_bar_review") else {}
    trace_files = ["flow-review.json"] if flow_review is not None else []
    opening_files = [_OPENING_REVIEW_FILE] if opening_review is not None else []
    hardware_files = [_HARDWARE_REFERENCE_FILE] if hardware_review is not None else []
    manifest = {
        "schema_version": "1.0",
        "status": "DRAFT_NOT_FOR_CUTTING",
        "source": "MAESTRO_MODULAR_F1_F7C",
        "piece_count": len(model["parts"]),
        "geometry_sha256": exchange["geometry_sha256"],
        "files": (list(_FILES) + trace_files + list(extras)
                  + opening_files + hardware_files),
        "fabrication_ready": False,
        "cutting_ready": False,
        "drilling_ready": False,
        "purchase_ready": False,
        "limitations": [
            "Medidas nominales, no dimensiones finales de corte.",
            "Cantos, herrajes, ensambles, cargas, instalaciones y tolerancias requieren revisión.",
            "FreeCAD y Blender deben ejecutar por separado el CADExchange con adaptadores auditados.",
        ],
    }
    if model.get("upper_support_review") is not None:
        manifest["upper_support_review"] = model["upper_support_review"]
        manifest["assembly_review"] = model["assembly_review"]
        manifest["piece_ids"] = [piece["piece_id"] for piece in model["parts"]]
        manifest["review_hypotheses"] = {
            module["module_id"]: module["review_hypotheses"]
            for module in model["modules"]
            if "review_hypotheses" in module
        }
    if has_query:
        manifest.update({
            "book_source_request": source_request,
            "book_source_metadata": _book_source_metadata(book),
            "book_source_status": book_status,
        })
    opening_text = None
    if opening_review is not None:
        opening_text = json.dumps(opening_review, indent=2, ensure_ascii=False) + "\n"
        manifest["opening_intents_review_sha256"] = hashlib.sha256(
            opening_text.encode("utf-8")
        ).hexdigest()
    hardware_text = None
    if hardware_review is not None:
        hardware_text = json.dumps(hardware_review, indent=2, ensure_ascii=False) + "\n"
        if len(hardware_text.encode("utf-8")) > _MAX_HARDWARE_REFERENCE_BYTES:
            raise PilotError("La revisión de referencias de herrajes excede 256 KiB.")
        manifest["hardware_reference_review_sha256"] = hashlib.sha256(
            hardware_text.encode("utf-8")
        ).hexdigest()
        manifest["hardware_reference_contract"] = _HARDWARE_REFERENCE_CONTRACT
        if not has_query:
            manifest[_HARDWARE_SOURCE_REQUEST_FIELD] = hardware_source_request
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    if ((has_query or hardware_review is not None)
            and len(manifest_text.encode("utf-8")) > _MAX_MANIFEST_BYTES):
        if has_query:
            raise BookEvidenceError(
                "BOOK_SOURCE_REQUEST_TOO_LARGE: vínculo excede el límite de 65.536 bytes."
            )
        raise PilotError(
            "HARDWARE_SOURCE_MANIFEST_TOO_LARGE: vínculo excede 65.536 bytes."
        )
    flow_text = (json.dumps(flow_review, indent=2, ensure_ascii=False) + "\n"
                 if flow_review is not None else None)
    if flow_text is not None and len(flow_text.encode("utf-8")) > 262144:
        raise PilotError("La traza conversacional excede 256 KiB.")
    return {
        "maestro-review.json": json.dumps(answer, indent=2, ensure_ascii=False) + "\n",
        "front-review.svg": svg,
        "parts-review.csv": csv_text,
        "cad-exchange.json": json.dumps(exchange, indent=2, ensure_ascii=False) + "\n",
        "manifest.json": manifest_text,
        **extras,
        **({"flow-review.json": flow_text} if flow_text is not None else {}),
        **({_OPENING_REVIEW_FILE: opening_text} if opening_text is not None else {}),
        **({_HARDWARE_REFERENCE_FILE: hardware_text}
           if hardware_text is not None else {}),
    }


def write_pilot_bundle(
    request: dict[str, Any], output_dir: Path,
    flow_review: dict[str, Any] | None = None,
    *, bundle_dir: Path | str | None = None, opening_review_json: str = "",
) -> dict[str, Any]:
    """Fail closed: stage complete files on the same filesystem before rename.

    Requires a new directory. Never overwrite prior review or source files.
    """
    if output_dir.exists() or output_dir.is_symlink():
        raise PilotError("Salida existente: elija un directorio nuevo sin sobrescribir.")
    parent = output_dir.parent
    if not parent.is_dir():
        raise PilotError("El directorio padre de salida debe existir.")
    bundle = pilot_review(
        request, flow_review=flow_review, bundle_dir=bundle_dir,
        opening_review_json=opening_review_json,
    )
    with TemporaryDirectory(prefix=".carpinova-pilot-", dir=parent) as temp:
        staging = Path(temp) / "review"
        staging.mkdir()
        for name, content in bundle.items():
            (staging / name).write_bytes(content.encode("utf-8"))
        if output_dir.exists() or output_dir.is_symlink():
            raise PilotError("Otra ejecución creó la salida; no se sobrescribe.")
        # Rename a complete directory within the same filesystem.
        os.rename(staging, output_dir)
    return json.loads(bundle["manifest.json"])



def verify_pilot_bundle(
    project_folder: Path, *, bundle_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Verify the base bundle and declared optional reviews against ONE Maestro model.

    The CAD digest alone is NOT provenance: it is an unkeyed checksum that
    could be recomputed after editing a box. Re-derive the original CAD, CSV
    and SVG from the recorded Maestro model and reject partial changes.
    Always return the original, strictly validated CADExchange.
    """
    folder = Path(project_folder)
    limits = {
        "maestro-review.json": 1048576,
        "front-review.svg": 1048576,
        "parts-review.csv": 1048576,
        "cad-exchange.json": 262144,
        "manifest.json": _MAX_MANIFEST_BYTES,
        "flow-review.json": 262144,
        _OPENING_REVIEW_FILE: _MAX_OPENING_REVIEW_BYTES,
        _HARDWARE_REFERENCE_FILE: _MAX_HARDWARE_REFERENCE_BYTES,
    }
    if not folder.is_dir() or folder.is_symlink():
        raise PilotError("El directorio del proyecto original no es confiable.")
    contents: dict[str, str] = {}
    for filename in _FILES:
        max_bytes = limits[filename]
        file = folder / filename
        if not file.is_file() or file.is_symlink() or file.stat().st_size > max_bytes:
            raise PilotError("Archivo original faltante, enlazado o excesivo: " + filename)
        try:
            contents[filename] = file.read_bytes().decode("utf-8")
        except UnicodeError as exc:
            raise PilotError("Archivo de revisión no es UTF-8 válido: " + filename) from exc
    try:
        answer = json.loads(
            contents["maestro-review.json"], object_pairs_hook=_opening_pairs,
            parse_constant=_opening_constant,
        )
        manifest = json.loads(
            contents["manifest.json"], object_pairs_hook=_opening_pairs,
            parse_constant=_opening_constant,
        )
        saved_cad = json.loads(
            contents["cad-exchange.json"], object_pairs_hook=_opening_pairs,
            parse_constant=_opening_constant,
        )
    except (ValueError, TypeError) as exc:
        raise PilotError("Archivos JSON de revisión inválidos.") from exc
    if not isinstance(answer, dict) or not isinstance(manifest, dict):
        raise PilotError("No existe respuesta de Maestro o manifiesto de revisión válido.")
    has_answer_book_data = (
        answer.get("knowledge") is not None
        or bool(answer.get("source_provenance"))
    )
    book_markers = {
        "book_source_request", "book_source_metadata", "book_source_status",
    }
    has_manifest_book_data = any(key in manifest for key in book_markers)
    book_source_request_for_hardware = None
    if has_answer_book_data or has_manifest_book_data:
        if not all(key in manifest for key in book_markers) or not has_answer_book_data:
            raise BookEvidenceError(
                "BOOK_EVIDENCE_BINDING_INCOMPLETE: falta vínculo bidireccional."
            )
        source_request = manifest.get("book_source_request")
        if type(source_request) is not dict or "query" not in source_request:
            raise BookEvidenceError(
                "BOOK_EVIDENCE_BINDING_INCOMPLETE: falta solicitud original."
            )
        if "flow-review.json" in manifest.get("files", []):
            raise BookEvidenceError(
                "BOOK_FLOW_COMBINATION_UNSUPPORTED: paquete con libro y flow-review."
            )
        source_request = _book_source_request(source_request)
        book_source_request_for_hardware = source_request
        bundle = _book_bundle(bundle_dir)
        expected_metadata = _book_source_metadata(bundle)
        if manifest.get("book_source_metadata") != expected_metadata:
            raise BookEvidenceError(
                "BOOK_BUNDLE_METADATA_MISMATCH: cambió el alcance o la procedencia declarada."
            )
        expected_status = _book_source_status(answer)
        if manifest.get("book_source_status") != expected_status:
            raise BookEvidenceError("BOOK_SOURCE_STATUS_MISMATCH.")
        try:
            replayed_answer = consult_maestro(source_request, bundle_dir=bundle_dir)
        except (
            MaestroError, BundleError, OSError, ValueError, TypeError,
            KeyError, RecursionError,
        ) as exc:
            raise BookEvidenceError(
                "BOOK_REPLAY_FAILED: no se pudo recalcular Maestro con el bundle."
            ) from exc
        if replayed_answer != answer:
            raise BookEvidenceError(
                "BOOK_REPLAY_MISMATCH: Maestro no reproduce íntegramente la respuesta guardada."
            )
    model = answer.get("modular")
    if (not isinstance(model, dict)
            or answer.get("status") != "DRAFT_NOT_FOR_CUTTING"
            or any(answer.get(flag) is not False or model.get(flag) is not False
                   for flag in _BLOCKED_FLAGS)):
        raise PilotError("Fuente Maestro no aprobada como borrador.")
    expected_extras = review_files(model) if model.get("wall_bar_review") else {}
    manifest_files = manifest.get("files")
    if type(manifest_files) is not list:
        raise PilotError("Manifiesto sin lista segura de archivos.")
    has_flow_review = "flow-review.json" in manifest_files
    has_opening_review = _OPENING_REVIEW_FILE in manifest_files
    has_hardware_reference = _HARDWARE_REFERENCE_FILE in manifest_files
    has_hardware_contract = "hardware_reference_contract" in manifest
    has_hardware_hash = "hardware_reference_review_sha256" in manifest
    has_hardware_source = _HARDWARE_SOURCE_REQUEST_FIELD in manifest
    if has_hardware_reference:
        if (not has_opening_review
                or manifest.get("hardware_reference_contract")
                != _HARDWARE_REFERENCE_CONTRACT
                or not has_hardware_hash):
            raise PilotError(
                "B4_HARDWARE_CONTRACT_INVALID: faltan sidecar, contrato o hash."
            )
        if has_hardware_source:
            if has_answer_book_data or has_manifest_book_data:
                raise PilotError(
                    "B4_HARDWARE_SOURCE_AMBIGUOUS: no duplicar fuente Knowledge."
                )
            hardware_source_request = _validate_hardware_source_request(
                manifest[_HARDWARE_SOURCE_REQUEST_FIELD], with_book_query=False,
            )
        else:
            if not (has_answer_book_data and has_manifest_book_data
                    and book_source_request_for_hardware is not None):
                raise PilotError(
                    "B4_HARDWARE_SOURCE_MISSING: falta solicitud modular reproducible."
                )
            hardware_source_request = _validate_hardware_source_request(
                book_source_request_for_hardware, with_book_query=True,
            )
    elif has_hardware_contract or has_hardware_hash or has_hardware_source:
        raise PilotError(
            "B4_HARDWARE_DECLARATION_WITHOUT_ARTIFACT: contrato o fuente huérfanos."
        )
    expected_files = (
        list(_FILES)
        + (["flow-review.json"] if has_flow_review else [])
        + list(expected_extras)
        + ([_OPENING_REVIEW_FILE] if has_opening_review else [])
        + ([_HARDWARE_REFERENCE_FILE] if has_hardware_reference else [])
    )
    physical_files = []
    for entry in folder.iterdir():
        if entry.is_file():
            if entry.is_symlink():
                raise PilotError("Archivo físico enlazado no permitido en el paquete.")
            physical_files.append(entry.name)
    if (len(physical_files) != len(set(physical_files))
            or set(physical_files) != set(expected_files)):
        raise PilotError("Archivos físicos no coinciden exactamente con el manifiesto.")
    if (manifest.get("schema_version") != "1.0"
            or manifest.get("source") != "MAESTRO_MODULAR_F1_F7C"
            or manifest.get("status") != "DRAFT_NOT_FOR_CUTTING"
            or manifest.get("files") != expected_files
            or manifest.get("piece_count") != len(model.get("parts", []))
            or manifest.get("upper_support_review") !=
                model.get("upper_support_review")
            or (model.get("upper_support_review") is not None
                and (manifest.get("assembly_review") != model.get("assembly_review")
                     or manifest.get("piece_ids") != [
                         piece["piece_id"] for piece in model["parts"]
                     ]
                     or manifest.get("review_hypotheses") != {
                         module["module_id"]: module["review_hypotheses"]
                         for module in model["modules"]
                         if "review_hypotheses" in module
                     }))
            or any(manifest.get(flag) is not False for flag in _BLOCKED_FLAGS)):
        raise PilotError("Manifiesto no corresponde a la fuente Maestro.")
    expected_cad = cad_exchange(model)
    actual_cad = validate_exchange(saved_cad)
    if (expected_cad != actual_cad
            or manifest.get("geometry_sha256") != expected_cad["geometry_sha256"]
            or len(actual_cad["boxes"]) != len(model["parts"])):
        raise PilotError("CAD, piezas o geometría diferentes del Maestro original.")

    opening_path = folder / _OPENING_REVIEW_FILE
    opening_hash = manifest.get("opening_intents_review_sha256")
    if has_opening_review:
        if (opening_path.is_symlink() or not opening_path.is_file()
                or opening_path.stat().st_size > limits[_OPENING_REVIEW_FILE]):
            raise PilotError("Sidecar de intenciones ausente, enlazado o excesivo.")
        opening_bytes = opening_path.read_bytes()
        actual_opening_hash = hashlib.sha256(opening_bytes).hexdigest()
        if opening_hash != actual_opening_hash:
            raise PilotError("Hash del sidecar de intenciones no coincide con el manifiesto.")
        try:
            opening_text = opening_bytes.decode("utf-8")
            saved_opening = json.loads(
                opening_text, object_pairs_hook=_opening_pairs,
                parse_constant=_opening_constant,
            )
            if type(saved_opening) is not dict:
                raise PilotError("Sidecar de intenciones debe ser un objeto JSON.")
            payload = {key: saved_opening[key] for key in (
                "schema_version", "source", "geometry_sha256", "elements",
            )}
            if set(saved_opening) != {
                "schema_version", "source", "geometry_sha256", "elements",
                "status", "hardware_selected", "drilling_ready", "purchase_ready",
                "authentication",
            }:
                raise PilotError("Sidecar de intenciones tiene campos inesperados.")
            expected_opening = _opening_review_for_cad(
                _opening_review_payload(json.dumps(payload, ensure_ascii=False)),
                actual_cad,
            )
        except (UnicodeError, ValueError, TypeError, KeyError, RecursionError) as exc:
            raise PilotError("Sidecar de intenciones JSON inválido.") from exc
        if saved_opening != expected_opening:
            raise PilotError("Sidecar de intenciones no coincide con el CAD revisado.")
    elif opening_path.exists() or opening_path.is_symlink() or opening_hash is not None:
        raise PilotError("Sidecar de intenciones no declarado en el manifiesto.")

    hardware_path = folder / _HARDWARE_REFERENCE_FILE
    hardware_hash = manifest.get("hardware_reference_review_sha256")
    if has_hardware_reference:
        if (hardware_path.is_symlink() or not hardware_path.is_file()
                or hardware_path.stat().st_size > limits[_HARDWARE_REFERENCE_FILE]):
            raise PilotError("Revisión de herrajes ausente, enlazada o excesiva.")
        hardware_bytes = hardware_path.read_bytes()
        if (type(hardware_hash) is not str
                or hashlib.sha256(hardware_bytes).hexdigest() != hardware_hash):
            raise PilotError("Hash de revisión de herrajes no coincide con el manifiesto.")
        try:
            if not has_answer_book_data:
                try:
                    replayed_answer = consult_maestro(hardware_source_request)
                except (
                    MaestroError, DesignError, ValueError, TypeError, KeyError,
                    RecursionError,
                ) as exc:
                    raise PilotError(
                        "HARDWARE_SOURCE_REPLAY_FAILED: solicitud modular inválida."
                    ) from exc
                if replayed_answer != answer:
                    raise PilotError(
                        "HARDWARE_SOURCE_REPLAY_MISMATCH: Maestro no reproduce "
                        "íntegramente la respuesta guardada."
                    )
            saved_hardware = json.loads(
                hardware_bytes.decode("utf-8"), object_pairs_hook=_opening_pairs,
                parse_constant=_opening_constant,
            )
            expected_hardware = _hardware_reference_review(
                expected_opening, model, actual_cad, hardware_source_request,
            )
            expected_hardware_bytes = (
                json.dumps(expected_hardware, indent=2, ensure_ascii=False) + "\n"
            ).encode("utf-8")
        except PilotError:
            raise
        except (UnicodeError, ValueError, TypeError, KeyError, RecursionError) as exc:
            raise PilotError("Revisión de herrajes JSON inválida.") from exc
        if type(saved_hardware) is not dict or hardware_bytes != expected_hardware_bytes:
            raise PilotError("Revisión de herrajes no reproduce íntegramente Maestro/F4.")
    elif (hardware_path.exists() or hardware_path.is_symlink()
          or "hardware_reference_review_sha256" in manifest):
        raise PilotError("Revisión de herrajes no declarada en el manifiesto.")

    flow_path = folder / "flow-review.json"
    if has_flow_review:
        if (not flow_path.is_file() or flow_path.is_symlink()
                or flow_path.stat().st_size > limits["flow-review.json"]):
            raise PilotError("Traza conversacional ausente, enlazada o excesiva.")
        try:
            flow_record = json.loads(flow_path.read_text(encoding="utf-8"))
            flow_request = flow_record.get("source_request")
            if (type(flow_request) is not dict or "query" in flow_request
                    or consult_maestro(flow_request) != answer):
                raise PilotError("Traza conversacional no reproduce el Maestro original.")
            validate_flow_review(flow_record, flow_request)
        except (OSError, UnicodeError, ValueError, TypeError, MaestroError, DesignError) as exc:
            raise PilotError("Traza conversacional alterada o inválida.") from exc
        if (flow_record.get("geometry_sha256") != expected_cad["geometry_sha256"]
                or flow_record.get("piece_count") != len(actual_cad["boxes"])):
            raise PilotError("Traza conversacional corresponde a otro proyecto CAD.")
    elif flow_path.exists() or flow_path.is_symlink():
        raise PilotError("Traza conversacional no declarada en el manifiesto.")

    for filename, expected in (
        ("front-review.svg", modular_front_svg(model)),
        ("parts-review.csv", modular_bom_csv(model)),
    ):
        if contents[filename] != expected:
            raise PilotError("Entregable no coincide con Maestro: " + filename)
    for filename, expected in expected_extras.items():
        path = folder / filename
        if (not path.is_file() or path.is_symlink()
                or path.stat().st_size > 1048576):
            raise PilotError("Entregable de barra ausente o alterado: " + filename)
        try:
            # Preserve CRLF in CSV: pathlib.read_text() normalizes newlines.
            observed = path.read_bytes().decode("utf-8")
        except UnicodeError as exc:
            raise PilotError("Entregable de barra no es UTF-8: " + filename) from exc
        if observed != expected:
            raise PilotError("Entregable de barra distinto del CAD: " + filename)
    return actual_cad

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CarpiNova: primer paquete geométrico de REVISIÓN, NO para cortar."
    )
    parser.add_argument("--input", required=True, type=Path,
                        help="JSON Maestro action=modular ya revisado")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Carpeta NUEVA para cinco archivos de revisión")
    parser.add_argument("--bundle-dir", type=Path,
                        help="Bundle Knowledge requerido para solicitudes con query")
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.input.read_text(encoding="utf-8"))
        result = write_pilot_bundle(request, args.output_dir,
                                    bundle_dir=args.bundle_dir)
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    except (OSError, ValueError, DesignError, MaestroError, PilotError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
