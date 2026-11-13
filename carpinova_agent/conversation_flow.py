"""Small adapter from reviewed conversation text to existing F1/F6 flows.

This module stores only a client-declared review trace. It is not an
identity/authentication boundary and never grants fabrication authority.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .cad_exchange import cad_exchange, validate_exchange
from .core import DesignError, design
from .drawer_modules import OPENING_SYSTEMS, _apportion_nominal, propose_drawer_layout
from .maestro import MaestroError, consult_maestro
from .modular import MODULE_FIELDS, ROOT_FIELDS
from .intake import _fold
from .natural_intake import (
    OWNER_DIRECTIVE_SOURCE, extract_explicit_dimensions,
    is_drawer_correction_instruction, preview_natural_request,
    _explicit_project_type,
    _parse_drawer_correction,
    revise_drawer_concept,
)

_SCHEMA = "1.0"
_FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
_RECORD_FIELDS = frozenset({
    "schema_version", "source", "utterance", "history", "decisions",
    "source_fixture", "source_request", "confirmation",
    "confirmation_summary", "openings_top_to_bottom", "geometry_sha256",
    "piece_count", "source_provenance", "authorization", *_FLAGS,
    "record_sha256",
})
_MAX_HISTORY = 100
_MAX_TEXT = 2000
_MAX_DECISIONS = 40
_MAX_REVIEW_FIELDS = 40
_MAX_REVIEW_HISTORY = 100
_PRIOR_REPORTED = "PRIOR_DESIGN_DECISION_REPORTED"
_OWNER_DIRECTIVE = OWNER_DIRECTIVE_SOURCE
_REVIEW_STATUSES = frozenset(("confirmed", "proposed", "pending", "rejected"))
_REVIEW_SOURCES = frozenset((
    "OWNER_TEXT", "OWNER_PHOTO_CONFIRMED", "IMAGE_OBSERVED_UNCONFIRMED",
    "BOOK_GUIDANCE", "ENGINE_CALCULATED",
))
_REVIEW_STATE_FIELDS = frozenset(("schema_version", "revision", "decisions", "history"))
_REVIEW_FIELD_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_REVIEW_QUESTION_ORDER = (
    "project_type", "dimensions_mm", "use", "wall_contact", "countertop",
    "support", "countertop_support", "cabinet_bracing", "anti_tip_anchor",
    "back", "internal_layout", "drawers", "doors", "front_style",
    "opening_intent", "material", "thickness_mm", "construction",
    "finish", "hardware_reference",
)
_REVIEW_QUESTIONS = {
    "project_type": "¿Qué tipo de mueble quieres diseñar y para qué uso?",
    "dimensions_mm": "¿Cuáles son las medidas exteriores confirmadas del mueble?",
    "use": "¿Qué uso tendrá y qué debe guardar o sostener?",
    "wall_contact": "¿El mueble irá contra la pared o separado de ella?",
    "countertop": "¿Lleva mesón o cubierta? Indica sus medidas y espesor si los conoces.",
    "support": "¿Apoyará en el piso, llevará patas o zócalo, o irá suspendido?",
    "countertop_support": "¿Qué apoyará el mesón? Esto es distinto del amarre de la carcasa y del anclaje anti-vuelco.",
    "cabinet_bracing": "¿Cómo se revisará el amarre de la carcasa? La pared no se considera apoyo vertical sin diseño.",
    "anti_tip_anchor": "¿Un instalador revisará el anclaje anti-vuelco según pared y carga?",
    "back": "¿Quieres revisar el fondo posterior, dejarlo abierto o decidirlo después?",
    "internal_layout": "¿Prefieres el interior abierto, con división horizontal, vertical o ambas?",
    "drawers": "¿Lleva cajones o gavetas? Si sí, ¿cuántos y dónde?",
    "doors": "¿Lleva puertas? Si sí, ¿cuántas y cómo se distribuyen?",
    "front_style": "¿Prefieres los frentes sobrepuestos o embutidos?",
    "opening_intent": "¿Prefieres manija, uñero, perfil, apertura por presión o dejarlo pendiente?",
    "material": "¿Qué material quieres usar? Si no lo sabes, puedo mostrar una propuesta sin aprobarla.",
    "thickness_mm": "¿Qué espesor real de tablero usarás?",
    "construction": "¿Prefieres laterales continuos o tapa y base entre los laterales?",
    "finish": "¿Qué acabado o cantos quieres revisar?",
    "hardware_reference": "¿Tienes la referencia exacta del herraje? Sin ella no se validan holguras ni taladros.",
}
_REVIEW_ALLOWED_FIELDS = frozenset((
    *_REVIEW_QUESTION_ORDER, "photo_observations", "nominal_detail_spec",
))
_GUIDED_COUNT_WORDS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
    "diez": 10,
}
_WALL_BAR_FIXTURE_SHA256 = "966ba2aaf6f104d3483b5d8126e2ec443c12c54893f992be7e106ce9593d956c"
_WALL_BAR_P5_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "examples" / "wall-bar-900-review-p5.json"
_WALL_BAR_P5_FIXTURE_SHA256 = "b3beb2e93fe8651ba3a4022d3014aa0c3368fba73a253795639c0f48a4d61983"
_WALL_BAR_P5_GEOMETRY_SHA256 = "5c0b8944ba015ef537688afac3ee58b9dd52011267c28278c9134a473cecf947"
_WALL_BAR_PRIOR_DECISIONS = {
    "wall_side": "left",
    "drawer_opening_face": "long_side_front",
    "drawer_order": "D1=small_top;D2=small_middle;D3=large_bottom",
    "left_vertical_wood_panels": 0,
    "material_id": "MDP_15",
    "panel_thickness_mm": 15,
    "construction": "sides_full",
    "top_thickness_mm": 15,
    "front_construction": "separate",
    "front_style": "overlay",
    "aesthetic_presentation": "bicolor_modern_preliminary",
    "drawer_opening_system": "handle",
}

_FREE_SPAN = re.compile(
    r"(?P<amount>\d{1,5}(?:[.,]\d{1,2})?)\s*"
    r"(?P<unit>mm|mil[ií]metros?|cm|cent[ií]metros?)\s*"
    r"(?:de\s+)?(?:espacio\s+)?(?:vacio|libre)\b", re.IGNORECASE,
)
_DRAWER_UNIT = re.compile(
    r"(?P<amount>\d{1,5}(?:[.,]\d{1,2})?)\s*"
    r"(?P<unit>mm|mil[ií]metros?|cm|cent[ií]metros?)\s+"
    r"(?:esa\s+|la\s+)?cajonera\b", re.IGNORECASE,
)


def _measure_mm(match: re.Match[str]) -> int | None:
    try:
        value = Decimal(match.group("amount").replace(",", "."))
    except InvalidOperation:
        return None
    unit = _fold(match.group("unit"))
    value *= 10 if unit.startswith(("cm", "centimet")) else 1
    if value != value.to_integral_value() or not 1 <= value <= 100000:
        return None
    return int(value)


def _load_wall_bar_fixture() -> tuple[dict[str, Any], bytes, str]:
    fixture_path = Path(__file__).resolve().parents[1] / "examples" / "wall-bar-900-review.json"
    try:
        fixture_bytes = fixture_path.read_bytes()
        fixture = json.loads(fixture_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise MaestroError("Fixture histórico de barra ausente o inválido.") from exc
    # Bind the parsed fixture, not checkout bytes: Git may normalize LF/CRLF
    # differently on Windows and Linux while preserving the same JSON data.
    digest = hashlib.sha256(_canonical(fixture)).hexdigest()
    if (type(fixture) is not dict or fixture.get("action") != "modular"
            or type(fixture.get("module_spec")) is not dict
            or digest != _WALL_BAR_FIXTURE_SHA256):
        raise MaestroError("Fixture histórico de barra distinto del SHA protegido.")
    return fixture, fixture_bytes, digest


def _wall_bar_owner_requirements(text: str) -> dict[str, Any] | None:
    """Parse owner measurements without choosing a geometry fixture."""
    normalized = _fold(text)
    if not (re.search(r"(?<!\w)barra(?:\s+de\s+cocina)?(?!\w)", normalized)
            and re.search(r"(?<!\w)cajonera(?!\w)", normalized)):
        return None
    evidence = extract_explicit_dimensions(text)
    dims = evidence["dimensions_mm"]
    free_matches = [m for m in _FREE_SPAN.finditer(normalized)
                    if _measure_mm(m) is not None]
    cabinet_matches = [m for m in _DRAWER_UNIT.finditer(normalized)
                       if _measure_mm(m) is not None]
    free_values = {_measure_mm(m) for m in free_matches}
    cabinet_values = {_measure_mm(m) for m in cabinet_matches}
    free_span = next(iter(free_values)) if len(free_values) == 1 else None
    cabinet_width = next(iter(cabinet_values)) if len(cabinet_values) == 1 else None
    drawer_count = 3 if re.search(
        r"(?<!\w)dos\s+cajones\s+pequenos\s+y\s+uno\s+grande\s+abajo(?!\w)",
        normalized,
    ) else None
    feet = next((item["value_mm"] for item in evidence["component_measurements"]
                 if item.get("scope") == "patas" and item.get("field") == "height_mm"),
                None)
    return {
        "evidence": evidence,
        "free_matches": free_matches,
        "cabinet_matches": cabinet_matches,
        "rails_requested": bool(re.search(
            r"(?<!\w)(?:riel|rieles|corredera)(?!\w)", normalized,
        )),
        "standard_claim_unverified": bool(
            re.search(r"(?<!\w)estandar(?!\w)", normalized)
        ),
        "owner_values": {
            "overall_width_mm": dims.get("width_mm"),
            "overall_depth_mm": dims.get("depth_mm"),
            "overall_height_mm": dims.get("height_mm"),
            "free_span_horizontal_mm": free_span,
            "cabinet_width_mm": cabinet_width,
            "feet_height_mm": feet,
            "drawer_count": drawer_count,
            "large_drawer_position": "bottom" if drawer_count == 3 else None,
        },
    }


def _wall_bar_reference_review(text: str) -> dict[str, Any] | None:
    """Compare literal bar requirements to the protected reference, without CAD."""
    requirements = _wall_bar_owner_requirements(text)
    if requirements is None:
        return None

    fixture, fixture_bytes, fixture_sha = _load_wall_bar_fixture()
    fixture_spec = fixture["module_spec"]
    fixture_module = fixture_spec["cabinet_module"]
    evidence = requirements["evidence"]
    free_matches = requirements["free_matches"]
    cabinet_matches = requirements["cabinet_matches"]
    owner_values = requirements["owner_values"]
    free_span = owner_values["free_span_horizontal_mm"]
    cabinet_width = owner_values["cabinet_width_mm"]
    drawer_count = owner_values["drawer_count"]
    feet = owner_values["feet_height_mm"]
    rails_requested = requirements["rails_requested"]

    reference = {
        "overall_width_mm": fixture_spec["overall_width_mm"],
        "overall_depth_mm": fixture_spec["overall_depth_mm"],
        "overall_height_mm": fixture_spec["overall_height_mm"],
        "free_span_horizontal_mm": fixture_spec["free_span_mm"],
        "cabinet_width_mm": fixture_module["width_mm"],
        "feet_height_mm": fixture_spec["feet_height_mm"],
        "drawer_count": len(fixture_module["drawers"]),
    }
    comparisons = {
        key: {"owner_value": value, "reference_value": reference[key],
              "matches": value == reference[key]}
        for key, value in owner_values.items()
        if key in reference and value is not None
    }
    width = owner_values["overall_width_mm"]
    arithmetic = None
    if width is not None and free_span is not None and cabinet_width is not None:
        arithmetic = {
            "equation": f"{width} − {free_span} = {width - free_span} mm",
            "declared_cabinet_width_mm": cabinet_width,
            "matches": width - free_span == cabinet_width,
            "horizontal_allocation_only": True,
        }
    standard_mentioned = requirements["standard_claim_unverified"]
    prior_design_choices = {
        "wall_side": fixture_spec["wall_side"],
        "drawer_opening_face": fixture_spec["drawer_opening_face"],
        "top_thickness_mm": fixture_spec["top_thickness_mm"],
        "material_id": fixture_module.get("material_id"),
        "panel_thickness_mm": fixture_module.get("panel_thickness_mm"),
        "construction": fixture_module.get("construction"),
        "front_style": fixture_module["drawers"][0]["facade"].get("style"),
        "drawer_opening_system": fixture_module["drawers"][0]["facade"].get("opening_system"),
        "aesthetic_presentation": fixture_spec.get("design_choices", {}).get(
            "aesthetic_presentation"),
    }
    return {
        "status": "NEEDS_USER_CONFIRMATION",
        "reference_label": (
            "MODELO HISTORICO — DECISIONES PREVIAS REPORTADAS; "
            "ACEPTACION VISUAL ACTUAL PENDIENTE"
        ),
        "reference_fixture": "examples/wall-bar-900-review.json",
        "reference_fixture_sha256": fixture_sha,
        "reference_type": fixture_spec["type"],
        "owner_values": owner_values,
        "owner_measurement_evidence": evidence["source_provenance"],
        "component_measurements": evidence["component_measurements"],
        "unit_requires_confirmation": evidence["unit_requires_confirmation"],
        "resolved_unit_confirmations": evidence["resolved_unit_confirmations"],
        "free_span_evidence": [m.group(0) for m in free_matches],
        "cabinet_width_evidence": [m.group(0) for m in cabinet_matches],
        "standard_claim_unverified": standard_mentioned,
        "rails_requested": rails_requested,
        "rails_exact_reference_verified": False,
        "reference_geometry_mm": reference,
        "reference_comparison": comparisons,
        "horizontal_allocation": arithmetic,
        "prior_design_choices_for_review": {
            "source": _PRIOR_REPORTED,
            "values": prior_design_choices,
            "not_authenticated_as_a_new_approval": True,
        },
        "current_owner_directives": {
            "drawer_front_construction": {
                "value": "separate_overlay",
                "source": _OWNER_DIRECTIVE,
                "meaning": "caja completa; fachada decorativa sobrepuesta separada",
                "not_manufacturing_approval": True,
            },
        },
        "illustrative_fixture_values": {
            "source": "TEST_FIXTURE_NOT_USER_CHOICE",
            "slide_clearance_each_side_mm": fixture_module["drawers"][0].get(
                "slide_clearance_left_mm"),
            "drawer_rear_setback_mm": fixture_module["drawers"][0].get(
                "rear_setback_mm"),
            "drawer_box_heights_mm": [item.get("box_height_mm")
                                      for item in fixture_module["drawers"]],
            "drawer_opening_heights_mm": [item.get("opening_height_mm")
                                          for item in fixture_module["drawers"]],
            "facade_edgeband_mm": fixture_module["drawers"][0]["facade"].get(
                "edgeband_thickness_mm"),
        },
        "pending_owner_decisions": [
            "revisión visual del boceto actual; todavía no hay aceptación del propietario",
        ],
        "pending_workshop": [
            "SKU, capacidad, longitud, montaje y holguras de los rieles",
            "material comercial, ubicación de tiradores y taladros",
            "cantos terminados, uniones, estabilidad, anclaje y tolerancias",
        ],
        "not_currently_confirmed": True,
        "parts": [], "piece_count": 0, "can_generate_f7c": False,
        **{flag: False for flag in _FLAGS},
    }


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise MaestroError("Traza de conversación: contenido JSON inválido.") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def image_input_unavailable() -> dict[str, Any]:
    """Report that this host/MCP contract does not receive image pixels."""
    return {
        "status": "IMAGE_INPUT_NOT_AVAILABLE_IN_HOST",
        "visual_capability_available": False,
        "pixels_received": False,
        "next_step": "Describe lo visible o comparte medidas y partes que no aparecen en la imagen.",
    }


def _photo_observation(value: Any) -> dict[str, Any]:
    fields = {
        "visible_features", "ambiguous_or_occluded",
        "dimensions_from_user_only", "questions",
    }
    if type(value) is not dict or set(value) != fields:
        raise MaestroError(
            "La observación de imagen requiere rasgos visibles, dudas, "
            "medidas dichas por el usuario y preguntas; no admite archivos ni rutas."
        )
    for key in ("visible_features", "ambiguous_or_occluded", "questions"):
        items = value[key]
        if (type(items) is not list or len(items) > 40
                or any(type(item) is not str or not item.strip() or len(item) > 300
                       for item in items)):
            raise MaestroError(f"photo_observations.{key} debe ser una lista breve de textos.")
    dims = value["dimensions_from_user_only"]
    if type(dims) is not dict or len(dims) > 12:
        raise MaestroError("Las medidas de foto solo admiten cotas dichas por el usuario.")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise MaestroError("La observación de imagen debe ser JSON simple.") from exc
    if len(encoded.encode("utf-8")) > 12000:
        raise MaestroError("La observación de imagen excede el límite de revisión.")
    return copy.deepcopy(value)


def update_review_state(
    previous_state: dict[str, Any] | None = None,
    *,
    updates: list[dict[str, Any]] | None = None,
    pending_fields: list[str] | None = None,
    max_questions: int = 3,
) -> dict[str, Any]:
    """Apply explicit conversation decisions to a visible, client-carried trace.

    This is a review record, not authentication or a fabrication permission.
    A later explicit owner decision replaces an earlier value; suggestions and
    observations cannot silently overwrite an owner-confirmed choice.
    """
    if type(max_questions) is not int or not 1 <= max_questions <= 3:
        raise MaestroError("La conversación admite de una a tres preguntas por turno.")
    if previous_state is None:
        state: dict[str, Any] = {
            "schema_version": "1.0", "revision": 0,
            "decisions": {}, "history": [],
        }
    else:
        if (type(previous_state) is not dict
                or set(previous_state) != _REVIEW_STATE_FIELDS
                or previous_state.get("schema_version") != "1.0"
                or type(previous_state.get("revision")) is not int
                or not 0 <= previous_state["revision"] <= _MAX_REVIEW_HISTORY
                or type(previous_state.get("decisions")) is not dict
                or type(previous_state.get("history")) is not list
                or len(previous_state["history"]) > _MAX_REVIEW_HISTORY):
            raise MaestroError("review_state previo inválido o de versión desconocida.")
        state = copy.deepcopy(previous_state)
        try:
            encoded_state = json.dumps(state, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise MaestroError("review_state previo no es JSON finito.") from exc
        if len(encoded_state.encode("utf-8")) > 48000:
            raise MaestroError("review_state previo supera el límite de 48 KB.")
        if len(state["decisions"]) > _MAX_REVIEW_FIELDS or state["revision"] != len(state["history"]):
            raise MaestroError("review_state previo no conserva su secuencia completa de revisiones.")
        history_decisions: dict[str, dict[str, Any]] = {}
        for index, event in enumerate(state["history"], start=1):
            if (type(event) is not dict
                    or set(event) != {"revision", "field", "previous", "current"}
                    or event["revision"] != index
                    or type(event["field"]) is not str
                    or event["field"] not in _REVIEW_ALLOWED_FIELDS
                    or type(event["current"]) is not dict):
                raise MaestroError("Historial de review_state inválido.")
            field = event["field"]
            current = event["current"]
            previous = history_decisions.get(field)
            if (event["previous"] != previous
                    or set(current) != {"value", "status", "source", "revision"}
                    or type(current["status"]) is not str
                    or current["status"] not in _REVIEW_STATUSES
                    or type(current["source"]) is not str
                    or current["source"] not in _REVIEW_SOURCES
                    or type(current["revision"]) is not int
                    or current["revision"] != index):
                raise MaestroError("La secuencia de review_state fue alterada.")
            if (current["source"] in (
                    "IMAGE_OBSERVED_UNCONFIRMED", "BOOK_GUIDANCE", "ENGINE_CALCULATED"
            ) and current["status"] not in ("proposed", "pending")):
                raise MaestroError("Una fuente no humana no puede confirmar una decisión.")
            if (field == "photo_observations"
                    and (current["source"] != "IMAGE_OBSERVED_UNCONFIRMED"
                         or current["status"] not in ("proposed", "pending"))):
                raise MaestroError("Una observación de imagen debe permanecer sin confirmar.")
            if field == "photo_observations":
                _photo_observation(current["value"])
            try:
                encoded_value = json.dumps(
                    current["value"], ensure_ascii=False, allow_nan=False,
                )
            except (TypeError, ValueError, OverflowError, RecursionError) as exc:
                raise MaestroError("Los valores guardados deben ser JSON finito.") from exc
            if len(encoded_value.encode("utf-8")) > 12000:
                raise MaestroError("Un valor guardado excede el límite de 12 KB.")
            history_decisions[field] = copy.deepcopy(current)
        if history_decisions != state["decisions"]:
            raise MaestroError("Las decisiones no coinciden con el historial completo.")

    if updates is None:
        updates = []
    if type(updates) is not list or len(updates) > _MAX_REVIEW_FIELDS:
        raise MaestroError("La revisión admite hasta 40 decisiones explícitas.")
    if pending_fields is None:
        pending_fields = []
    if (type(pending_fields) is not list or len(pending_fields) > _MAX_REVIEW_FIELDS
            or any(type(field) is not str or not _REVIEW_FIELD_RE.fullmatch(field)
                   or field not in _REVIEW_ALLOWED_FIELDS
                   for field in pending_fields)):
        raise MaestroError("pending_fields debe contener campos de revisión válidos.")

    decisions = state["decisions"]
    for field, entry in decisions.items():
        if (type(field) is not str or not _REVIEW_FIELD_RE.fullmatch(field)
                or field not in _REVIEW_ALLOWED_FIELDS or type(entry) is not dict
                or set(entry) != {"value", "status", "source", "revision"}
                or type(entry["status"]) is not str
                or entry["status"] not in _REVIEW_STATUSES
                or type(entry["source"]) is not str
                or entry["source"] not in _REVIEW_SOURCES
                or type(entry["revision"]) is not int
                or not 1 <= entry["revision"] <= state["revision"]):
            raise MaestroError("Una decisión guardada en review_state está dañada.")

    for update in updates:
        if type(update) is not dict or set(update) != {"field", "value", "status", "source"}:
            raise MaestroError("Cada decisión requiere field, value, status y source.")
        field, status, source = update["field"], update["status"], update["source"]
        if (type(field) is not str or not _REVIEW_FIELD_RE.fullmatch(field)
                or field not in _REVIEW_ALLOWED_FIELDS
                or type(status) is not str or type(source) is not str
                or status not in _REVIEW_STATUSES or source not in _REVIEW_SOURCES):
            raise MaestroError("Campo, estado o procedencia de decisión no admitido.")
        if source in ("IMAGE_OBSERVED_UNCONFIRMED", "BOOK_GUIDANCE", "ENGINE_CALCULATED") \
                and status not in ("proposed", "pending"):
            raise MaestroError(f"{source} no puede confirmar ni rechazar una decisión humana.")
        value = (_photo_observation(update["value"])
                 if field == "photo_observations" else copy.deepcopy(update["value"]))
        try:
            encoded_value = json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise MaestroError("Los valores de revisión deben ser JSON finito.") from exc
        if len(encoded_value.encode("utf-8")) > 12000:
            raise MaestroError("Un valor de revisión excede el límite de 12 KB.")
        old = decisions.get(field)
        owner_correction = (
            source in ("OWNER_TEXT", "OWNER_PHOTO_CONFIRMED")
            and status in ("confirmed", "rejected")
        )
        if (old is not None and old["status"] in ("confirmed", "rejected")
                and not owner_correction):
            # Keep a settled owner decision; a suggestion is not a correction.
            continue
        if state["revision"] >= _MAX_REVIEW_HISTORY:
            raise MaestroError("La revisión alcanzó el límite acumulado de cambios.")
        state["revision"] += 1
        decisions[field] = {
            "value": value, "status": status, "source": source,
            "revision": state["revision"],
        }
        state["history"].append({
            "revision": state["revision"], "field": field,
            "previous": copy.deepcopy(old), "current": copy.deepcopy(decisions[field]),
        })

    for field in pending_fields:
        if field not in decisions:
            if state["revision"] >= _MAX_REVIEW_HISTORY:
                raise MaestroError("La revisión alcanzó el límite acumulado de cambios.")
            state["revision"] += 1
            decisions[field] = {
                "value": None, "status": "pending", "source": "ENGINE_CALCULATED",
                "revision": state["revision"],
            }
            state["history"].append({
                "revision": state["revision"], "field": field,
                "previous": None, "current": copy.deepcopy(decisions[field]),
            })
    if len(decisions) > _MAX_REVIEW_FIELDS or len(state["history"]) > _MAX_REVIEW_HISTORY:
        raise MaestroError("review_state excede su límite seguro de tamaño.")

    order = {field: i for i, field in enumerate(_REVIEW_QUESTION_ORDER)}
    candidates = [field for field, entry in decisions.items()
                  if field not in {"photo_observations", "nominal_detail_spec"}
                  and entry["status"] in ("pending", "proposed")]
    candidates = sorted(set(candidates), key=lambda field: (order.get(field, len(order)), field))
    questions = [{
        "field": field,
        "question": _REVIEW_QUESTIONS.get(
            field, f"¿Qué prefieres para {field.replace('_', ' ')}?"
        ),
        "status": decisions[field]["status"],
        "unit": "choice_or_description",
    } for field in candidates[:max_questions]]

    wall = decisions.get("wall_contact")
    back = decisions.get("back")
    structure_options = None
    if wall and wall["status"] in ("confirmed", "proposed"):
        if wall["value"] is True:
            back_value = back["value"] if back and back["status"] == "confirmed" else None
            suggestions = (
                ["rear_ties"] if back_value == "none" else
                ["evaluate_rear_ties_only_after_collision_review"]
                if back_value == "thin_3mm" else
                ["compare_back_and_ties_separately_without_assuming_equivalence"]
                if back_value in ("same_board_15mm", "15mm") else []
            )
            structure_options = {
                "status": "PROPOSAL_ONLY",
                "wall_contact": True,
                "back_choice": back_value if back_value is not None else "PENDING",
                "suggested_options": suggestions,
                "limitations": [
                    "No se decide automáticamente fondo ni correas.",
                    "La unión y resistencia no están comprobadas.",
                    "El anclaje de estabilidad requiere revisión de instalador.",
                ],
                "support_roles": {
                    "countertop_vertical_load": (
                        decisions.get("countertop_support", {}).get("value", "PENDING")
                    ),
                    "carcass_bracing": decisions.get("cabinet_bracing", {}).get(
                        "value", "PENDING"
                    ),
                    "anti_tip_anchor": decisions.get("anti_tip_anchor", {}).get(
                        "value", "PENDING"
                    ),
                    "wall_is_vertical_support": False,
                },
            }
        elif wall["value"] is False:
            structure_options = {
                "status": "PROPOSAL_ONLY", "wall_contact": False,
                "back_choice": (back["value"] if back else "PENDING"),
                "suggested_options": ["visible_rear_finish", "back_panel_to_define"],
                "limitations": ["No se presupone fondo, apoyo ni resistencia estructural."],
            }
    opening = decisions.get("opening_intent")
    opening_guidance = None
    if opening:
        is_wood_t = opening["value"] == "profile_t_wood_inverted"
        opening_guidance = {
            "intent": opening["value"], "status": opening["status"],
            "options": ["handle", "finger_pull", "profile", "push_to_open", "pending"],
            "educational_only": is_wood_t,
            "manufacturing_sku_selected": False,
            "drilling_validated": False,
            "note": ("La T invertida de madera es un concepto educativo; "
                     "no define montaje, herraje ni mecanizado." if is_wood_t else
                     "La intención de apertura no selecciona herraje ni valida perforaciones."),
        }
    return {
        "review_state": state, "questions": questions,
        "structure_options": structure_options,
        "opening_guidance": opening_guidance,
        "status": "NEEDS_USER_CONFIRMATION" if questions else "REVIEW_ONLY",
        "can_generate_f7c": False,
        **{flag: False for flag in _FLAGS},
    }


def preview_conversation(
    utterance: str,
    corrections: list[str] | None = None,
    *,
    review_state: dict[str, Any] | None = None,
    review_updates: list[dict[str, Any]] | None = None,
    pending_fields: list[str] | None = None,
    max_questions: int = 3,
) -> dict[str, Any]:
    """Keep requirement clarifications cumulative; replay only strict F1 edits."""
    if corrections is None:
        corrections = []
    if type(corrections) is not list or len(corrections) > 12:
        raise MaestroError("La revisión admite como máximo 12 correcciones explícitas.")
    if any(type(item) is not str for item in corrections):
        raise MaestroError("Cada corrección debe ser una frase de texto.")
    if (type(utterance) is not str or not utterance.strip()
            or len(utterance) > _MAX_TEXT):
        raise MaestroError("La descripción original debe tener 1–2000 caracteres.")
    clarifications: list[str] = []
    drawer_corrections: list[str] = []
    result = preview_natural_request(utterance, include_concept_sketch=True)
    for correction in corrections:
        if is_drawer_correction_instruction(correction):
            if not isinstance(result.get("illustrative_drawer_layout_option"), dict):
                raise MaestroError("No existe una distribución F1 revisable para corregir.")
            drawer_corrections.append(correction)
        else:
            clarifications.append(correction)
            combined = "\n".join([utterance, *clarifications])
            if len(combined) > _MAX_TEXT:
                raise MaestroError("La conversación excede el límite de 2000 caracteres.")
            result = preview_natural_request(combined, include_concept_sketch=True)
            for instruction in drawer_corrections:
                result = revise_drawer_concept(
                    result, instruction, include_concept_sketch=True,
                )
            continue
        result = revise_drawer_concept(
            result, correction, include_concept_sketch=True,
        )
    combined_text = "\n".join([utterance, *clarifications])
    wall_bar_review = _wall_bar_reference_review(combined_text)
    if wall_bar_review is not None:
        result.update({
            "mode": "F7D_WALL_BAR_REFERENCE_REVIEW",
            "status": "NEEDS_USER_CONFIRMATION",
            "proposed_request": None,
            "illustrative_drawer_layout_option": None,
            "wall_bar_review": wall_bar_review,
            "requires_user_confirmation": True,
            "executed_tools": [],
            "next_step": (
                "Preparar una revisión nominal con las decisiones previas reportadas "
                "y el acabado visual del fixture; después mostrar la imagen y dejar "
                "la aceptación visual del propietario pendiente."
            ),
        })
    state_updates = list(review_updates or [])
    existing_fields = {
        item.get("field") for item in state_updates if type(item) is dict
    }
    if (result.get("explicit_measurements")
            and "dimensions_mm" not in existing_fields
            and not (review_state and "dimensions_mm" in
                     review_state.get("decisions", {}))):
        state_updates.append({
            "field": "dimensions_mm", "value": result["explicit_measurements"],
            "status": "proposed", "source": "OWNER_TEXT",
        })
    guided = update_review_state(
        review_state, updates=state_updates,
        pending_fields=pending_fields, max_questions=max_questions,
    )
    result["review_state"] = guided["review_state"]
    result["guided_questions"] = guided["questions"]
    if guided["structure_options"] is not None:
        result["structure_options"] = guided["structure_options"]
    if guided["opening_guidance"] is not None:
        result["opening_guidance"] = guided["opening_guidance"]
    result["conversation_original_utterance"] = utterance
    result["requirement_clarifications"] = list(clarifications)
    result["drawer_corrections"] = list(drawer_corrections)
    result["conversation_history"] = [
        {"role": "user", "content": utterance},
        *[{"role": "user", "content": item} for item in corrections],
    ]
    result.update({
        "conversation_flow_schema_version": _SCHEMA,
        "public_reference_order": "A-D_TOP_TO_BOTTOM",
        "internal_reference_order": "D1-Dn_BOTTOM_TO_TOP",
        "can_generate_f7c": False,
        "piece_count": 0,
        **{flag: False for flag in _FLAGS},
    })
    return result


def _guided_dimension_value(
    natural_preview: dict[str, Any], utterance: str,
    previous_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    normalized = _fold(utterance)
    component = re.search(r"\b(?:meson|cubierta|encimera|patas?)\b", normalized)
    evidence = extract_explicit_dimensions(utterance[:component.start()]) if component else None
    if component:
        measurements = (evidence.get("dimensions_mm")
                        if evidence is not None else None)
        ambiguous = set(evidence.get("ambiguous_fields", [])) if evidence else set()
    else:
        measurements = natural_preview.get("explicit_measurements")
        ambiguous = set(natural_preview.get("ambiguous_fields", []))
    if component and not measurements:
        # A countertop-only turn must not overwrite carcass dimensions with
        # measurements scoped to that separate component.
        return None
    if type(measurements) is not dict or not measurements:
        return None
    previous = ((previous_state or {}).get("decisions", {}).get("dimensions_mm", {}))
    previous_value = previous.get("value") if type(previous) is dict else None
    previous_complete = (
        type(previous_value) is dict
        and set(previous_value) == {"width_mm", "height_mm", "depth_mm"}
        and all(type(value) is int and value > 0 for value in previous_value.values())
    )
    if set(measurements) != {"width_mm", "height_mm", "depth_mm"} and previous_complete:
        merged = dict(previous_value)
        merged.update(measurements)
        measurements = merged
    complete = set(measurements) == {"width_mm", "height_mm", "depth_mm"}
    unambiguous = not ambiguous.intersection({"width_mm", "height_mm", "depth_mm"})
    exterior = bool(re.search(
        r"\b(?:exterior(?:es)?|externo|externa|carcasa|caja exterior)\b",
        normalized,
    ))
    already_confirmed = (
        type(previous) is dict and previous.get("status") == "confirmed"
    )
    return {
        "value": copy.deepcopy(measurements),
        "status": "confirmed" if complete and unambiguous and (exterior or already_confirmed)
        else "proposed",
    }


def _guided_countertop_value(utterance: str) -> tuple[dict[str, Any], str] | None:
    match = re.search(r"\b(mes[oó]n|cubierta|encimera)\b(.*)", utterance, re.IGNORECASE)
    if not match:
        return None
    segment = re.split(r"[.;\n]", match.group(2), maxsplit=1)[0][:400]
    value: dict[str, Any] = {"present": True}
    explicit = extract_explicit_dimensions(segment)
    dimensions = dict(explicit.get("dimensions_mm", {}))
    if not {"width_mm", "depth_mm"}.issubset(dimensions):
        pair = re.search(
            r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(mm|cm)?\s*(?:por|[x×])\s*"
            r"(\d+(?:[.,]\d+)?)\s*(mm|cm)?\b",
            segment, re.IGNORECASE,
        )
        if pair:
            left_unit = (pair.group(2) or pair.group(4) or "").casefold()
            right_unit = (pair.group(4) or pair.group(2) or "").casefold()
            if left_unit and right_unit:
                left = Decimal(pair.group(1).replace(",", ".")) * (
                    10 if left_unit == "cm" else 1
                )
                right = Decimal(pair.group(3).replace(",", ".")) * (
                    10 if right_unit == "cm" else 1
                )
                if left == left.to_integral_value() and right == right.to_integral_value():
                    dimensions.setdefault("width_mm", int(left))
                    dimensions.setdefault("depth_mm", int(right))
    if dimensions:
        value["dimensions_mm"] = dimensions
    sequence = re.search(
        r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(mm|cm)?\s*[x×]\s*"
        r"(\d+(?:[.,]\d+)?)\s*(mm|cm)?\s*[x×]\s*"
        r"(\d+(?:[.,]\d+)?)\s*(mm|cm)\b",
        segment, re.IGNORECASE,
    )
    if sequence:
        unit = next((item for item in reversed((sequence.group(6), sequence.group(4), sequence.group(2)))
                     if item), "mm").casefold()
        multiplier = 10 if unit == "cm" else 1
        value["dimensions_literal_mm"] = [
            int(Decimal(sequence.group(i).replace(",", ".")) * multiplier)
            for i in (1, 3, 5)
        ]
    thickness_match = re.search(
        r"(?:espesor|grosor)\s*(?:de|del)?\s*(\d+(?:[.,]\d+)?)\s*(mm|cm)\b|"
        r"(\d+(?:[.,]\d+)?)\s*(mm|cm)\s+(?:de\s+)?(?:espesor|grosor)\b",
        segment, re.IGNORECASE,
    )
    if thickness_match:
        amount = thickness_match.group(1) or thickness_match.group(3)
        unit = thickness_match.group(2) or thickness_match.group(4)
        value["thickness_mm"] = int(
            Decimal(amount.replace(",", ".")) * (10 if unit.casefold() == "cm" else 1)
        )
    countertop_material = re.search(
        r"\b(mdf\s+rh|mdf|mdp|melamina)\b(?:\s+(?:de\s+)?"
        r"(?P<material_mm>\d{1,4})\s*mm\b)?",
        segment, re.IGNORECASE,
    )
    if countertop_material:
        material = _fold(countertop_material.group(1)).replace(" ", "_").upper()
        material_mm = countertop_material.group("material_mm")
        if material_mm and "thickness_mm" not in value:
            value["thickness_mm"] = int(material_mm)
        if "thickness_mm" in value:
            value["material_id"] = f"{material}_{value['thickness_mm']}"
    labelled_complete = (
        {"width_mm", "depth_mm"}.issubset(dimensions)
        and "thickness_mm" in value
    )
    return value, "confirmed" if labelled_complete else "proposed"


def _guided_count(token: str) -> int:
    normalized = _fold(token)
    return int(normalized) if normalized.isdigit() else _GUIDED_COUNT_WORDS[normalized]


def _guided_count_items(text: str, nouns: str) -> list[tuple[int, str]]:
    count = r"(?:\d{1,2}|un|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
    return [(_guided_count(match.group("count")), match.group("noun"))
            for match in re.finditer(
                rf"\b(?P<count>{count})\s+(?P<noun>{nouns})\b", text)]


def _guided_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 32):start]
    return bool(re.search(
        r"\b(?:no|sin|ni)\s+(?:(?:quiero|deseo|lleva|llevar|tiene|usar|use|va|ira|queda|esta)\s+)?$",
        prefix,
    ))


def _guided_text_updates(
    utterance: str, natural_preview: dict[str, Any],
    previous_state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Extract only explicit review choices; unparsed detail stays a question."""
    if is_drawer_correction_instruction(utterance):
        return []
    text = _fold(utterance)
    updates: list[dict[str, Any]] = []

    def add(field: str, value: Any, status: str = "confirmed",
            source: str = "OWNER_TEXT") -> None:
        updates.append({
            "field": field, "value": value, "status": status,
            "source": source,
        })

    project = natural_preview.get("proposed_request")
    project_data = project.get("project", {}) if type(project) is dict else {}
    project_type = project_data.get("project_type") or _explicit_project_type(utterance)
    if re.search(r"\b(?:cl[oó]set|closet)\b", text):
        project_type = "closet"
    elif re.search(r"\bmueble\s+(?:de\s+)?(?:ba[nñ]o|superior|flotante)\b", text):
        project_type = "gabinete"
    elif project_type is None and re.search(
        r"\b(?:gabinete|cajonera|nochero|mesa\s+de\s+noche|"
        r"mesita\s+de\s+noche)\b", text,
    ):
        project_type = "gabinete"
    elif project_type is None and re.search(r"\bmueble\b", text) and re.search(
        r"\b(?:cocina|ba[nñ]o|superior|flotante)\b", text,
    ):
        project_type = "gabinete"
    if project_type:
        add("project_type", project_type)
    dimension = _guided_dimension_value(natural_preview, utterance, previous_state)
    if dimension:
        add("dimensions_mm", dimension["value"], dimension["status"])

    if re.search(r"\b(caf[eé]|cafetera|coffee)\b", text):
        add("use", "coffee")
    elif re.search(r"\b(cocina|cocin[aá])\b", text):
        add("use", "kitchen")
    elif re.search(r"\bba[nñ]o\b", text):
        add("use", "bathroom")
    elif re.search(r"\b(?:nochero|mesa\s+de\s+noche|mesita\s+de\s+noche|dormitorio)\b", text):
        add("use", "bedroom")

    material_pattern = re.compile(r"\b(melamina|mdp|mdf(?:\s+rh)?)\b")
    material_matches = list(material_pattern.finditer(text))
    body_materials = []
    for material_match in material_matches:
        if _guided_negated(text, material_match.start()):
            continue
        boundary = max(text.rfind(".", 0, material_match.start()),
                       text.rfind(";", 0, material_match.start()),
                       text.rfind("\n", 0, material_match.start()))
        prefix = text[boundary + 1:material_match.start()]
        if not re.search(r"\b(?:meson|cubierta|encimera)\b", prefix):
            body_materials.append(material_match)
    selected_material = body_materials[-1] if body_materials else None
    if selected_material:
        material_name = _fold(selected_material.group(1)).replace(" ", "_")
        add("material", material_name)
        thickness = re.search(
            r"\b(?:melamina|mdp|mdf(?:\s+rh)?|tablero(?:s)?|carcasa|cuerpo|"
            r"laterales|costados)\s+(?:de\s+)?(\d+(?:[.,]\d+)?)\s*mm\b",
            text[selected_material.start():],
        )
        if thickness:
            amount = Decimal(thickness.group(1).replace(",", "."))
            if amount == amount.to_integral_value():
                add("thickness_mm", int(amount))
    if "thickness_mm" not in {item["field"] for item in updates}:
        thickness = re.search(
            r"\b(?:espesor|grosor)\s*(?:del\s+(?:tablero|cuerpo|mueble))?\s*"
            r"(?:de\s+)?(\d+(?:[.,]\d+)?)\s*mm\b", text,
        )
        if thickness:
            clause_start = max(text.rfind(".", 0, thickness.start()),
                               text.rfind(";", 0, thickness.start()),
                               text.rfind("\n", 0, thickness.start()))
            clause = text[clause_start + 1:thickness.start()]
            if not re.search(r"\b(?:meson|cubierta|encimera)\b", clause):
                amount = Decimal(thickness.group(1).replace(",", "."))
                if amount == amount.to_integral_value():
                    add("thickness_mm", int(amount))

    sides_full = re.search(r"\b(?:laterales|costados)\s+continuos\b|\bsides_full\b", text)
    top_bottom = re.search(
        r"\b(?:tapa\s+y\s+base|tapas\s+y\s+base)\s+entre\s+(?:los\s+)?"
        r"(?:laterales|costados)\b|\btop_bottom_full\b", text,
    )
    if sides_full and not _guided_negated(text, sides_full.start()):
        add("construction", "sides_full")
    elif top_bottom and not _guided_negated(text, top_bottom.start()):
        add("construction", "top_bottom_full")

    wall_positive = re.search(
        r"\b(?:contra|pegad[oa] a|junto a|fijaci[oó]n a|fijar a|montaje a|"
        r"fijad[oa] al|anclad[oa] al)\s+"
        r"(?:(?:la|el)\s+)?(?:pared|muro)\b", text,
    )
    if wall_positive and _guided_negated(text, wall_positive.start()):
        add("wall_contact", False)
    elif wall_positive:
        add("wall_contact", True)
    elif re.search(r"\b(?:separad[oa] de\s+(?:la\s+)?pared|exento|independiente)\b", text):
        add("wall_contact", False)

    countertop_match = re.search(r"\b(mes[oó]n|cubierta|encimera)\b", utterance, re.IGNORECASE)
    if countertop_match and _guided_negated(text, countertop_match.start()):
        add("countertop", {"present": False})
    countertop = _guided_countertop_value(utterance)
    if countertop and not (countertop_match and _guided_negated(text, countertop_match.start())):
        add("countertop", countertop[0], countertop[1])

    floor_support = re.search(
        r"\b(?:direct(?:o|amente)?\s+al\s+piso|apoyad[oa]s?\s+en\s+(?:el\s+)?piso|"
        r"al\s+suelo)\b", text,
    )
    if floor_support and not _guided_negated(text, floor_support.start()):
        add("support", {"style": "floor_direct"})
    elif re.search(r"\bpatas?\b", text):
        legs_match = re.search(r"\bpatas?\b", text)
        legs = re.search(r"\bpatas?\b([^.;\n]{0,100})", text)
        if legs_match and _guided_negated(text, legs_match.start()):
            add("support", {"style": "legs_absent_support_unspecified"}, "proposed")
            legs = None
        height = (re.search(
            r"^\s*(?:de\s+)?(\d+(?:[.,]\d+)?)\s*(mm|cm)"
            r"(?:\s+(?:de\s+)?(?:alto|altura))?\b",
            legs.group(1),
        ) if legs else None)
        support: dict[str, Any] = {"style": "legs"}
        status = "proposed"
        if height and legs is not None:
            amount = Decimal(height.group(1).replace(",", "."))
            mm = amount * (10 if height.group(2) == "cm" else 1)
            if mm == mm.to_integral_value():
                support["height_mm"] = int(mm)
                status = "confirmed"
        if legs is not None:
            previous_support = ((previous_state or {}).get("decisions", {})
                                .get("support", {}))
            keep_confirmed_height = (
                status == "proposed" and type(previous_support) is dict
                and previous_support.get("status") == "confirmed"
                and previous_support.get("source") == "OWNER_TEXT"
                and type(previous_support.get("value")) is dict
                and previous_support["value"].get("style") == "legs"
                and type(previous_support["value"].get("height_mm")) is int
            )
            if not keep_confirmed_height:
                add("support", support, status)
    elif re.search(r"\bz[oó]calo\b", text):
        add("support", {"style": "plinth"}, "proposed")
    elif re.search(r"\b(?:va\s+)?(?:fijad[oa]|anclad[oa]|colgad[oa])\s+"
                   r"(?:al|a\s+la)\s+(?:muro|pared)\b", text):
        add("support", {"style": "wall_mounted"})
    elif re.search(
        r"\b(?:suspendido|colgado|anclado\s+a\s+(?:la\s+)?pared|"
        r"fijaci[oó]n\s+a\s+(?:la\s+)?(?:pared|muro)|fijar\s+a\s+(?:la\s+)?pared)\b",
        text,
    ):
        add("support", {"style": "wall_mounted"}, "proposed")

    layout: list[str] = []
    module_count_match = re.search(
        r"\b(?P<count>\d{1,2}|un|uno|una|dos|tres|cuatro)\s+"
        r"m[oó]dulos?\b", text,
    )
    explicit_module_count = (
        _guided_count(module_count_match.group("count"))
        if module_count_match else None
    )
    shelf_per_module = re.search(
        r"\b(?P<count>\d{1,2}|un|uno|una|dos|tres|cuatro)\s+"
        r"repisas?\s+por\s+(?:cada\s+)?m[oó]dulo\b", text,
    )
    shelf_position = re.search(
        r"\b(?P<mm>\d{1,5})\s*mm\s+desde\s+(?:la\s+)?base\s+interior\b",
        text,
    )
    horizontal = re.search(r"\b(?:repisa|divisi[oó]n|divisor)\s+horizontal\b|"
                           r"\bhorizontal\s+(?:repisa|divisi[oó]n)\b", text)
    vertical = re.search(r"\b(?:divisi[oó]n|divisor)\s+vertical\b|"
                         r"\bvertical\s+(?:divisi[oó]n|divisor)\b", text)
    if shelf_per_module and not _guided_negated(text, shelf_per_module.start()):
        detail: dict[str, Any] = {
            "elements": ["horizontal"],
            "shelves_per_module": _guided_count(shelf_per_module.group("count")),
        }
        if explicit_module_count is not None:
            detail["module_count"] = explicit_module_count
        if shelf_position:
            detail["shelf_position_from_clear_bottom_mm"] = int(shelf_position.group("mm"))
        add("internal_layout", detail)
    elif explicit_module_count is not None and re.search(
        r"\b(?:modulos?\s+iguales|iguales\s+de\s+ancho)\b", text,
    ):
        add("internal_layout", {"elements": [], "module_count": explicit_module_count})
    elif horizontal and not _guided_negated(text, horizontal.start()):
        layout.append("horizontal")
    if vertical and not _guided_negated(text, vertical.start()):
        layout.append("vertical")
    if re.search(r"\binterior\s+(?:abierto|libre)\b|\babierto\b", text):
        layout.append("open")
    if layout and not (shelf_per_module or explicit_module_count is not None
                       and re.search(r"\b(?:modulos?\s+iguales|iguales\s+de\s+ancho)\b", text)):
        add("internal_layout", layout)

    if re.search(r"\b(?:sin\s+(?:ning[uú]n(?:a)?\s+)?(?:caj[oó]n(?:es)?|gaveta(?:s)?)|"
                 r"ni\s+(?:ning[uú]n(?:a)?\s+)?(?:caj[oó]n(?:es)?|gaveta(?:s)?)|"
                 r"no\s+(?:lleva|llevar[aá]|tiene|tendr[aá]|quiero)\s+"
                 r"(?:ning[uú]n(?:a)?\s+)?(?:caj[oó]n(?:es)?|gaveta(?:s)?)|"
                 r"ning[uú]n(?:a)?\s+(?:caj[oó]n(?:es)?|gaveta(?:s)?))\b", text):
        add("drawers", "none")
    else:
        drawer_counts = _guided_count_items(text, r"caj[oó]n(?:es)?|gaveta(?:s)?")
        implicit = re.search(
            r"\b(?:caj[oó]n(?:es)?|gaveta(?:s)?)\b[^.;\n]{0,35}\by\s+"
            r"(?P<count>\d{1,2}|un|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+"
            r"(?:pequenos?|grandes?)\b",
            text,
        )
        if implicit:
            following = text[implicit.end():implicit.end() + 20]
            if not re.match(r"\s+(?:cajones?|gavetas?)\b", following):
                drawer_counts.append((_guided_count(implicit.group("count")), "cajon"))
        if drawer_counts:
            add("drawers", {
                "count": sum(count for count, _ in drawer_counts),
                "items": [{"count": count, "type": noun} for count, noun in drawer_counts],
            })
            if "internal_layout" not in {item["field"] for item in updates}:
                add("internal_layout", [], "proposed", "ENGINE_CALCULATED")
        elif re.search(r"\b(?:caj[oó]n(?:es)?|gaveta(?:s)?)\b", text):
            add("drawers", {"description": utterance.strip()}, "proposed")

    overlay_match = re.search(r"\bsobrepuest[oa]s?\b", text)
    inset_match = re.search(r"\bembutid[oa]s?\b", text)
    front_style = (
        "overlay" if overlay_match and not _guided_negated(text, overlay_match.start()) else
        "inset" if inset_match and not _guided_negated(text, inset_match.start()) else None
    )
    if front_style:
        add("front_style", front_style)
    if re.search(r"\b(?:sin\s+puertas?|no\s+(?:lleva|tiene|quiero)\s+puertas?)\b", text):
        add("doors", "none")
    else:
        door_counts = _guided_count_items(text, r"puertas?")
        doors_per_module_match = re.search(
            r"\b(?P<count>\d{1,2}|un|uno|una|dos|tres|cuatro)\s+"
            r"puertas?\b[^.;\n]{0,40}\bpor\s+(?:cada\s+)?m[oó]dulo\b",
            text,
        )
        if doors_per_module_match and explicit_module_count is not None:
            per_module = _guided_count(doors_per_module_match.group("count"))
            total = per_module * explicit_module_count
            add("doors", {
                "count": total,
                "items": [{"count": total, "type": "puerta"}],
                "arrangement": "side_by_side" if per_module == 2 else None,
                "per_module_count": per_module,
                "module_count": explicit_module_count,
            })
        elif door_counts:
            add("doors", {
                "count": sum(count for count, _ in door_counts),
                "items": [{"count": count, "type": noun} for count, noun in door_counts],
                "arrangement": "side_by_side" if re.search(r"\blado\s+a\s+lado\b", text) else None,
            })
        elif re.search(r"\bpuertas?\b", text):
            add("doors", {
                "count": None,
                "arrangement": "side_by_side" if re.search(r"\blado\s+a\s+lado\b", text) else None,
            }, "proposed")

    opening = None
    handle_match = re.search(r"\b(?:manijas?|tiradores?)\b", text)
    finger_match = re.search(r"\bu[nñ]eros?\b", text)
    profile_match = re.search(r"\bperfil\b", text)
    push_match = re.search(
        r"\b(?:push(?:\s*[- ]?to\s*[- ]?open)?|apertura\s+por\s+presi[oó]n)\b",
        text,
    )
    if push_match and not _guided_negated(text, push_match.start()):
        opening = "push_to_open"
    elif handle_match and not _guided_negated(text, handle_match.start()):
        opening = "handle"
    elif finger_match and not _guided_negated(text, finger_match.start()):
        opening = "finger_pull"
    elif profile_match and not _guided_negated(text, profile_match.start()):
        opening = "profile"
    if opening:
        add("opening_intent", opening)

    if re.search(r"\b(?:sin\s+fondo|ni\s+fondo(?:\s+(?:posterior|trasero))?|"
                 r"abierto\s+por\s+atr[aá]s)\b", text):
        add("back", "none")
    else:
        back_pending = re.search(
            r"\bfondo\b(?:\s+(?:posterior|trasero))?\s+"
            r"(?:(?:queda|est[aá])\s+)?"
            r"(?:pendiente|para\s+despu[eé]s|despu[eé]s|m[aá]s\s+adelante)\b",
            text,
        )
        back_thickness = re.search(
            r"\bfondo\b(?:\s+(?:posterior|trasero))?\s+"
            r"(?:(?:de|en|con|es\s+de|ser[aá]\s+de|queda\s+de)\s+)?"
            r"(?:(?:melamina|mdp|mdf)\s+(?:de\s+)?)?"
            r"(?P<mm>3|15)\s*mm\b",
            text,
        )
        if back_pending and not _guided_negated(text, back_pending.start()):
            add("back", "pending")
        elif (back_thickness
              and not _guided_negated(text, back_thickness.start())):
            thickness_value = (
                "thin_3mm" if back_thickness.group("mm") == "3"
                else "same_board_15mm"
            )
            add("back", thickness_value)

    return updates


def _guided_confirmation_updates(
    utterance: str, previous_state: dict[str, Any] | None,
    already_updated: set[str],
) -> list[dict[str, Any]]:
    if not previous_state:
        return []
    text = _fold(utterance).strip()
    affirmative = (
        bool(re.match(r"^(?:si|ok|vale|de acuerdo|correcto)\b", text))
        or bool(re.search(r"\bconfirmo\b", text))
    )
    if not affirmative or (text.startswith("no ") and "confirmo" not in text):
        return []
    decisions = previous_state.get("decisions", {})
    proposed = {
        field: entry for field, entry in decisions.items()
        if field not in {"photo_observations", "nominal_detail_spec"}
        and entry.get("status") == "proposed"
    }
    aliases = (
        (r"\b(?:medidas?|dimensiones?)\b", "dimensions_mm"),
        (r"\b(?:meson|cubierta|encimera)\b", "countertop"),
        (r"\b(?:pared|muro)\b", "wall_contact"),
        (r"\bmaterial\b", "material"),
        (r"\b(?:espesor|grosor)\b", "thickness_mm"),
        (r"\b(?:construccion|laterales|costados)\b", "construction"),
        (r"\b(?:interior|repisa|division|divisor)\b", "internal_layout"),
        (r"\b(?:cajones?|gavetas?)\b", "drawers"),
        (r"\bpuertas?\b", "doors"),
        (r"\b(?:sobrepuest[oa]s?|embutid[oa]s?|frentes?)\b", "front_style"),
        (r"\b(?:patas?|zocalo|suelo|piso)\b", "support"),
        (r"\bfondo\b", "back"),
        (r"\b(?:cafe|cafetera)\b", "use"),
    )
    targets = {field for pattern, field in aliases if re.search(pattern, text)}
    if not targets and re.search(r"\b(?:todo|todas?|ambas?)\b", text):
        targets = set(proposed)
    elif not targets and len(proposed) == 1:
        targets = set(proposed)
    updates = []
    for field in targets:
        entry = proposed.get(field)
        if entry is None or field in already_updated:
            continue
        if field == "dimensions_mm" and (
            type(entry.get("value")) is not dict
            or set(entry["value"]) != {"width_mm", "height_mm", "depth_mm"}
        ):
            continue
        if field == "countertop" and (
            type(entry.get("value")) is not dict
            or not {"width_mm", "depth_mm"}.issubset(
                entry["value"].get("dimensions_mm", {})
            )
            or "thickness_mm" not in entry["value"]
        ):
            continue
        updates.append({
            "field": field, "value": copy.deepcopy(entry["value"]),
            "status": "confirmed", "source": "OWNER_TEXT",
        })
    return updates


def _guided_question_fields(decisions: dict[str, dict[str, Any]]) -> list[str]:
    project_type = decisions.get("project_type", {}).get("value")
    if not project_type:
        return ["project_type", "dimensions_mm", "use"]
    is_cabinet = _fold(str(project_type)) in {
        "gabinete", "cabinet", "cajonera", "closet", "clóset",
    }
    if not is_cabinet:
        return ["dimensions_mm", "material", "thickness_mm", "construction"]
    coffee = decisions.get("use", {}).get("value") == "coffee"
    fields = ["dimensions_mm", "wall_contact"]
    if _fold(str(project_type)) not in {"closet"}:
        fields.insert(1, "use")
    if coffee:
        fields.extend(("countertop", "support"))
    fields.extend(("internal_layout", "drawers", "doors", "back", "material",
                   "thickness_mm", "construction"))
    if not coffee:
        fields.append("support")
    door_value = decisions.get("doors", {}).get("value")
    drawer_value = decisions.get("drawers", {}).get("value")
    has_doors = (type(door_value) is dict and type(door_value.get("count")) is int
                 and door_value["count"] > 0)
    has_drawers = (type(drawer_value) is dict and type(drawer_value.get("count")) is int
                   and drawer_value["count"] > 0)
    if has_doors and "front_style" not in decisions:
        fields.append("front_style")
    if has_doors or has_drawers:
        fields.append("opening_intent")
    return list(dict.fromkeys(fields))


def _guided_needs_modular_spec(decisions: dict[str, dict[str, Any]]) -> bool:
    project_type = _fold(str(decisions.get("project_type", {}).get("value", "")))
    if project_type == "closet":
        return True
    doors = decisions.get("doors", {}).get("value")
    drawers = decisions.get("drawers", {}).get("value")
    countertop = decisions.get("countertop", {}).get("value")
    layout = decisions.get("internal_layout", {}).get("value")
    support = decisions.get("support", {}).get("value")
    back = decisions.get("back", {}).get("value")
    return bool(
        type(doors) is dict and type(doors.get("count")) is int
        and doors["count"] > 0
        or type(drawers) is dict and type(drawers.get("count")) is int
        and drawers["count"] > 0
        or type(countertop) is dict and countertop.get("present") is True
        or type(layout) is list and any(item in ("horizontal", "vertical") for item in layout)
        or type(support) is dict and support.get("style") in {"legs", "plinth", "wall_mounted"}
        or back not in (None, "none", "pending")
    )


def _guided_compose_closet_spec(
    decisions: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    """Translate the narrow confirmed two-module closet pattern into F6."""
    assumptions: list[dict[str, Any]] = []
    blockers: list[str] = []

    def confirmed(field: str) -> Any:
        entry = decisions.get(field)
        if (type(entry) is not dict or entry.get("status") != "confirmed"
                or entry.get("source") != "OWNER_TEXT"):
            blockers.append(f"{field}:confirmed_owner_text_required")
            return None
        return entry.get("value")

    dimensions = confirmed("dimensions_mm")
    material = confirmed("material")
    thickness = confirmed("thickness_mm")
    construction = confirmed("construction")
    support = confirmed("support")
    wall_contact = confirmed("wall_contact")
    layout = confirmed("internal_layout")
    drawers = confirmed("drawers")
    doors = confirmed("doors")
    front_style = confirmed("front_style")
    back = confirmed("back")
    if blockers:
        return None, assumptions, list(dict.fromkeys(blockers))

    if (type(dimensions) is not dict
            or set(dimensions) != {"width_mm", "height_mm", "depth_mm"}
            or any(type(value) is not int or value <= 0 for value in dimensions.values())):
        blockers.append("dimensions_mm:positive_exterior_integers_required")
    if type(thickness) is not int or thickness <= 0:
        blockers.append("thickness_mm:positive_integer_required")
    if material not in {"melamina", "mdp", "mdf", "mdf_rh"}:
        blockers.append("material:unsupported_catalog_value")
    if construction not in {"sides_full", "top_bottom_full"}:
        blockers.append("construction:unsupported")
    if support != {"style": "floor_direct"} or wall_contact is not False:
        blockers.append("closet:freestanding_floor_support_required")
    if drawers != "none":
        blockers.append("closet:drawer_layout_not_supported_by_this_composer")
    if back != "none":
        blockers.append("closet:explicit_absent_back_required")
    if front_style not in {"overlay", "inset"}:
        blockers.append("front_style:explicit_overlay_or_inset_required")
    if type(layout) is not dict or set(layout) - {
        "elements", "shelves_per_module", "module_count",
        "shelf_position_from_clear_bottom_mm",
    }:
        blockers.append("internal_layout:two_module_shelf_description_required")
    if type(doors) is not dict:
        blockers.append("doors:per_module_count_required")
    if blockers:
        return None, assumptions, list(dict.fromkeys(blockers))

    count = layout.get("module_count")
    shelf_count = layout.get("shelves_per_module")
    position = layout.get("shelf_position_from_clear_bottom_mm")
    if type(count) is not int or not 1 <= count <= 12:
        blockers.append("internal_layout:module_count_1_to_12_required")
    if (type(shelf_count) is not int or shelf_count != 1
            or layout.get("elements") != ["horizontal"]):
        blockers.append("internal_layout:one_horizontal_shelf_per_module_required")
    if type(position) is not int or position < 0:
        blockers.append("internal_layout:explicit_shelf_position_required")
    width = dimensions.get("width_mm") if type(dimensions) is dict else None
    height = dimensions.get("height_mm") if type(dimensions) is dict else None
    depth = dimensions.get("depth_mm") if type(dimensions) is dict else None
    if type(count) is int and type(width) is int and count > 0 and width % count:
        blockers.append("internal_layout:equal_module_width_not_integral")
    per_module_doors = doors.get("per_module_count")
    door_modules = doors.get("module_count")
    if (type(per_module_doors) is not int or per_module_doors not in (1, 2)
            or door_modules != count or doors.get("count") != per_module_doors * count):
        blockers.append("doors:module_distribution_must_be_explicit")
    if (type(height) is int and type(thickness) is int and type(position) is int
            and position > height - 3 * thickness):
        blockers.append("internal_layout:shelf_position_outside_clear_height")
    if blockers:
        return None, assumptions, list(dict.fromkeys(blockers))

    material_names = {
        "melamina": "MELAMINA", "mdp": "MDP", "mdf": "MDF", "mdf_rh": "MDF_RH",
    }
    material_id = f"{material_names[material]}_{thickness}"
    modules = []
    module_width = width // count
    for index in range(count):
        module_id = f"CLOSET_{index + 1}"
        fronts: Any = "none"
        if per_module_doors:
            if front_style == "overlay":
                fronts = {
                    "style": "overlay", "leaf_count": per_module_doors,
                    "material_id": material_id, "thickness_mm": thickness,
                    "hinge_sides": (["left", "right"] if per_module_doors == 2
                                    else ["left"]),
                    "left_reveal_mm": 3, "right_reveal_mm": 3,
                    "top_reveal_mm": 4, "bottom_reveal_mm": 4,
                }
                if per_module_doors == 2:
                    fronts["center_gap_mm"] = 4
            else:
                fronts = {
                    "style": "inset", "leaf_count": per_module_doors,
                    "material_id": material_id, "thickness_mm": thickness,
                    "hinge_sides": (["left", "right"] if per_module_doors == 2
                                    else ["left"]),
                    "left_clearance_mm": 3, "right_clearance_mm": 3,
                    "top_clearance_mm": 4, "bottom_clearance_mm": 4,
                }
                if per_module_doors == 2:
                    fronts["center_gap_mm"] = 4
            assumptions.append({
                "field": f"{module_id}.front_geometry",
                "value": {
                    "style": front_style,
                    "thickness_mm": thickness,
                    "hinge_sides": fronts["hinge_sides"],
                    "perimeter_reveals_or_clearances_mm": [3, 3, 4, 4],
                    "center_gap_mm": 4 if per_module_doors == 2 else None,
                },
                "source": "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
                "reason": "Parámetros ilustrativos requeridos por F6 para geometría nominal; no validan herrajes ni montaje.",
            })
        modules.append({
            "module_id": module_id, "width_mm": module_width,
            "panel_thickness_mm": thickness, "material_id": material_id,
            "construction": construction, "support": "floor",
            "fronts": fronts, "back": "none", "drawers": "none",
            "horizontal_divider": {
                "material_id": material_id, "thickness_mm": thickness,
                "position_from_clear_bottom_mm": position,
                "depth_mm": depth, "depth_from_front_mm": 0,
            },
        })
        assumptions.append({
            "field": f"{module_id}.shelf_depth_and_setback",
            "value": {"depth_mm": depth, "depth_from_front_mm": 0},
            "source": "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
            "reason": "La solicitud da el fondo exterior pero no la profundidad ni el retiro de repisa; se representa de forma reversible a fondo completo y al ras del frente.",
        })

    return {
        "type": "modular_run", "application": "closet",
        "width_mm": width, "height_mm": height, "depth_mm": depth,
        "installation": "freestanding", "modules": modules,
    }, assumptions, []


def _guided_compose_product_spec(
    decisions: dict[str, dict[str, Any]], utterance: str,
    natural_preview: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    """Translate one confirmed natural product into the existing F6 module."""
    assumptions: list[dict[str, Any]] = []
    blockers: list[str] = []
    values: dict[str, Any] = {}
    for field in (
        "project_type", "dimensions_mm", "use", "material", "thickness_mm",
        "construction", "wall_contact", "support", "internal_layout",
        "drawers", "doors", "back", "countertop",
    ):
        entry = decisions.get(field)
        if (field == "internal_layout" and type(entry) is dict
                and entry.get("value") == [] and entry.get("status") == "proposed"
                and entry.get("source") == "ENGINE_CALCULATED"):
            values[field] = []
            assumptions.append({
                "field": "internal_layout", "value": [],
                "source": "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
                "reason": "No se añaden divisores fijos al módulo de cajones.",
            })
            continue
        if (type(entry) is not dict or entry.get("value") in (None, "pending")
                or entry.get("source") != "OWNER_TEXT"
                or entry.get("status") != "confirmed"):
            blockers.append(f"{field}:confirmed_owner_text_required")
            continue
        values[field] = entry["value"]
    if blockers:
        return None, assumptions, blockers

    dimensions = values["dimensions_mm"]
    if (type(dimensions) is not dict
            or set(dimensions) != {"width_mm", "height_mm", "depth_mm"}
            or any(type(v) is not int or v <= 0 for v in dimensions.values())):
        blockers.append("dimensions_mm:positive_carcass_dimensions_required")
    width = dimensions.get("width_mm") if type(dimensions) is dict else None
    height = dimensions.get("height_mm") if type(dimensions) is dict else None
    depth = dimensions.get("depth_mm") if type(dimensions) is dict else None
    thickness = values["thickness_mm"]
    if type(thickness) is not int or thickness <= 0:
        blockers.append("thickness_mm:positive_integer_required")
    material_name = _fold(str(values["material"]))
    material_prefix = {
        "melamina": "MELAMINA", "mdp": "MDP", "mdf": "MDF",
        "mdf_rh": "MDF_RH",
    }.get(material_name)
    if material_prefix is None:
        blockers.append("material:unsupported_catalog_value")
    if values["construction"] not in {"sides_full", "top_bottom_full"}:
        blockers.append("construction:unsupported")
    use = _fold(str(values["use"]))
    application = "kitchen" if use == "kitchen" else "cabinet_run"
    support = values["support"]
    support_style = support.get("style") if type(support) is dict else None
    support_height = support.get("height_mm") if type(support) is dict else None
    if support_style not in {"floor_direct", "legs", "plinth", "wall_mounted"}:
        blockers.append("support:explicit_supported_style_required")
    if support_style in {"floor_direct", "wall_mounted"}:
        support_height = 0
    if support_style in {"legs", "plinth"} and (
            type(support_height) is not int or support_height <= 0):
        blockers.append("support:positive_height_required")
    wall_contact = values["wall_contact"]
    if type(wall_contact) is not bool:
        blockers.append("wall_contact:boolean_required")
    if support_style == "wall_mounted" and wall_contact is not True:
        blockers.append("wall_mounted:owner_wall_contact_required")
    if blockers:
        return None, assumptions, list(dict.fromkeys(blockers))

    body_material_id = f"{material_prefix}_{thickness}"
    doors = values["doors"]
    door_count = doors.get("count") if type(doors) is dict else 0
    if doors != "none" and (type(door_count) is not int or door_count < 1):
        blockers.append("doors:explicit_positive_count_or_none_required")
    front_style = decisions.get("front_style", {}).get("value")
    if type(door_count) is int and door_count > 0 and front_style not in {"overlay", "inset"}:
        blockers.append("front_style:confirmed_overlay_or_inset_required")
    back = values["back"]
    if back != "none":
        blockers.append("back:only_explicit_absence_supported_by_this_review")
    layout = values["internal_layout"]
    layout_elements = layout.get("elements", []) if type(layout) is dict else layout
    if type(layout_elements) is not list:
        blockers.append("internal_layout:list_or_elements_required")
    elif "vertical" in layout_elements:
        blockers.append("internal_layout:vertical_divider_position_required")

    countertop = values["countertop"]
    has_countertop = type(countertop) is dict and countertop.get("present") is True
    countertop_module: dict[str, Any] = {}
    if has_countertop:
        top_dimensions = countertop.get("dimensions_mm")
        if (type(top_dimensions) is not dict
                or type(top_dimensions.get("width_mm")) is not int
                or type(top_dimensions.get("depth_mm")) is not int
                or type(countertop.get("thickness_mm")) is not int):
            blockers.append("countertop:owner_dimensions_and_thickness_required")
        else:
            top_width = top_dimensions["width_mm"]
            top_depth = top_dimensions["depth_mm"]
            left_overhang = (top_width - width) // 2
            right_overhang = top_width - width - left_overhang
            depth_overhang = top_depth - depth
            front_overhang = depth_overhang // 2
            rear_overhang = top_depth - depth - front_overhang
            if min(left_overhang, right_overhang, front_overhang, rear_overhang) < 0:
                blockers.append("countertop:dimensions_smaller_than_carcass")
            total = height + support_height + countertop["thickness_mm"]
            declared_total = re.search(
                r"\baltura\s+total\b[^.;\n]{0,70}?(\d{2,5})\s*mm\b",
                _fold(utterance),
            )
            if declared_total and int(declared_total.group(1)) != total:
                blockers.append("countertop:declared_overall_height_conflicts_with_components")
            material_id = countertop.get("material_id") or "MATERIAL_PENDIENTE"
            assumptions.append({
                "field": "vertical_dimensions_review",
                "value": {
                    "carcass_height_mm": height,
                    "support_height_mm": support_height,
                    "countertop_thickness_mm": countertop["thickness_mm"],
                    "overall_height_mm": total,
                },
                "source": "ENGINE_CALCULATED_FROM_OWNER_DECLARED_DIMENSIONS",
                "reason": "Separa carcasa, apoyo y mesón; no valida la estructura ni autoriza fabricación.",
            })
            countertop_module = {
                "countertop": {
                    "material_id": material_id,
                    "thickness_mm": countertop["thickness_mm"],
                    "width_mm": top_width, "depth_mm": top_depth,
                    "left_overhang_mm": left_overhang,
                    "right_overhang_mm": right_overhang,
                    "front_overhang_mm": front_overhang,
                    "rear_overhang_mm": rear_overhang,
                },
                "support_concept": {
                    "style": support_style,
                    "support_height_mm": support_height,
                    "overall_height_mm": total,
                },
            }
            assumptions.extend((
                {
                    "field": "countertop.material_id", "value": material_id,
                    "source": "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
                    "reason": "No se declaró material comercial para el mesón.",
                },
                {
                    "field": "countertop.overhangs_mm",
                    "value": {"left": left_overhang, "right": right_overhang,
                              "front": front_overhang, "rear": rear_overhang},
                    "source": "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
                    "reason": "Reparto geométrico equilibrado de las diferencias indicadas.",
                },
                {
                    "field": "support_concept",
                    "value": {"style": support_style,
                              "support_height_mm": support_height,
                              "overall_height_mm": total},
                    "source": "OWNER_TEXT_PLUS_ENGINE_CALCULATION",
                    "reason": "Patas conceptuales; no se crean piezas ni se valida carga.",
                },
            ))
    elif type(countertop) is not dict or countertop.get("present") is not False:
        blockers.append("countertop:explicit_presence_or_absence_required")

    module: dict[str, Any] = {
        "module_id": {
            "kitchen": "KITCHEN_1", "bathroom": "BATHROOM_1",
            "bedroom": "BEDROOM_1",
        }.get(use, "CABINET_1"),
        "width_mm": width, "panel_thickness_mm": thickness,
        "material_id": body_material_id,
        "construction": values["construction"],
        "support": "wall" if support_style == "wall_mounted" else "floor",
        "fronts": "none", "back": "none", "drawers": "none",
    }
    if countertop_module:
        module.update(countertop_module)

    if type(door_count) is int and door_count > 0:
        hinges = ["left", "right"] if door_count == 2 else ["left"]
        front: dict[str, Any] = {
            "style": front_style, "leaf_count": door_count,
            "material_id": body_material_id, "thickness_mm": thickness,
            "hinge_sides": hinges,
        }
        if front_style == "overlay":
            front.update({"left_reveal_mm": 3, "right_reveal_mm": 3,
                          "top_reveal_mm": 4, "bottom_reveal_mm": 4})
        else:
            front.update({"left_clearance_mm": 3, "right_clearance_mm": 3,
                          "top_clearance_mm": 4, "bottom_clearance_mm": 4})
        if door_count == 2:
            front["center_gap_mm"] = 4
        module["fronts"] = front
        assumptions.append({
            "field": f"{module['module_id']}.front_geometry",
            "value": {"style": front_style, "thickness_mm": thickness,
                      "hinge_sides": hinges,
                      "perimeter_reveals_or_clearances_mm": [3, 3, 4, 4],
                      "center_gap_mm": 4 if door_count == 2 else None},
            "source": "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
            "reason": "La geometría nominal requiere luces y lados de bisagra; no valida un SKU.",
        })

    if "horizontal" in layout_elements:
        geometry = design({
            "type": "cabinet", "width_mm": width, "height_mm": height,
            "depth_mm": depth, "panel_thickness_mm": thickness,
            "construction": values["construction"],
        })
        clear_height = geometry["dimensions"]["clear_height_mm"]
        position = clear_height // 2
        module["horizontal_divider"] = {
            "material_id": body_material_id, "thickness_mm": thickness,
            "position_from_clear_bottom_mm": position,
            "depth_mm": depth, "depth_from_front_mm": 0,
        }
        assumptions.append({
            "field": f"{module['module_id']}.horizontal_divider",
            "value": {"position_from_clear_bottom_mm": position,
                      "depth_mm": depth, "depth_from_front_mm": 0},
            "source": "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
            "reason": "El texto pide una repisa horizontal, pero no fija altura ni retiro.",
        })
    elif layout_elements not in ([], ["open"]):
        blockers.append("internal_layout:unsupported_for_single_module_composer")

    drawers = values["drawers"]
    if drawers != "none":
        drawer_count = drawers.get("count") if type(drawers) is dict else None
        if type(drawer_count) is not int or not 1 <= drawer_count <= 4:
            blockers.append("drawers:one_to_four_explicit_count_required")
        elif front_style != "overlay":
            blockers.append("drawers:overlay_facades_required_for_this_review")
        else:
            option = natural_preview.get("illustrative_drawer_layout_option")
            reference = (option.get("proposed_request", {}).get("module_spec")
                         if type(option) is dict
                         and type(option.get("proposed_request")) is dict else None)
            if (type(reference) is not dict or reference.get("width_mm") != width
                    or reference.get("height_mm") != height
                    or reference.get("depth_mm") != depth
                    or reference.get("panel_thickness_mm") != thickness
                    or reference.get("construction") != values["construction"]
                    or len(reference.get("drawer_weights", [])) != drawer_count):
                blockers.append("drawers:F1_layout_proposal_missing_or_mismatched")
            else:
                plan = propose_drawer_layout(reference)
                module["drawer_layout_reference"] = copy.deepcopy(reference)
                drawer_parts = []
                for opening in plan["opening_plan"]:
                    opening_height = opening["opening_height_mm"]
                    box_height = max(1, opening_height - 20)
                    drawer_parts.append({
                        "drawer_id": opening["drawer_id"],
                        "opening_bottom_offset_mm": opening["opening_bottom_offset_mm"],
                        "opening_height_mm": opening_height,
                        "opening_depth_mm": depth,
                        "box_height_mm": box_height,
                        "panel_thickness_mm": thickness,
                        "bottom_thickness_mm": thickness,
                        "slide_clearance_left_mm": 0,
                        "slide_clearance_right_mm": 0,
                        "front_setback_mm": 0, "rear_setback_mm": 0,
                        "material_id": body_material_id,
                        "bottom_material_id": body_material_id,
                        "facade": {
                            "style": "overlay", "material_id": body_material_id,
                            "thickness_mm": thickness,
                            "left_overlap_mm": 1, "right_overlap_mm": 1,
                            "top_overlap_mm": 1, "bottom_overlap_mm": 1,
                            "opening_system": decisions.get("opening_intent", {}).get(
                                "value", "pending"),
                        },
                        "front_construction": "separate",
                    })
                module["drawers"] = drawer_parts
                assumptions.append({
                    "field": "drawer_layout_reference",
                    "value": copy.deepcopy(reference),
                    "source": "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
                    "reason": "Propuesta de aperturas F1 desde el texto; pesos y franja vienen de la propuesta ilustrativa existente.",
                })
                assumptions.append({
                    "field": "drawer_box_and_facade_geometry",
                    "value": {
                        "box_height_reduction_mm": 20,
                        "box_depth_mm": depth,
                        "slide_clearance_each_side_mm": 0,
                        "front_and_rear_setback_mm": [0, 0],
                        "bottom_thickness_mm": thickness,
                        "facade_overlap_mm_each_edge": 1,
                        "front_construction": "separate",
                    },
                    "source": "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
                    "reason": "Parámetros solo geométricos; no certifican recorrido, corredera, holgura, uniones ni fabricación.",
                })

    if blockers:
        return None, assumptions, list(dict.fromkeys(blockers))

    max_depth_match = re.search(
        r"\b(?:fondo|profundidad)\s+(?:exterior\s+)?m[aá]xim[oa]\s+"
        r"montad[oa][^.;\n]{0,40}?(\d{2,5})\s*mm\b|"
        r"\b(\d{2,5})\s*mm\s+(?:de\s+)?(?:fondo|profundidad)\s+"
        r"(?:exterior\s+)?m[aá]xim[oa]\s+montad[oa]\b",
        _fold(utterance),
    )
    max_assembled_depth = int(next(
        group for group in max_depth_match.groups() if group
    )) if max_depth_match else None
    spec = {
        "type": "modular_run", "application": application,
        "width_mm": width, "height_mm": height, "depth_mm": depth,
        "installation": "wall_mounted" if support_style == "wall_mounted" else "freestanding",
        "modules": [module],
    }
    if max_assembled_depth is not None:
        spec["max_assembled_depth_mm"] = max_assembled_depth
        assumptions.append({
            "field": "max_assembled_depth_mm", "value": max_assembled_depth,
            "source": "OWNER_TEXT", "reason": "Límite exterior máximo declarado por el usuario.",
        })
    return spec, assumptions, []


def _guided_wall_mounted_concept() -> dict[str, Any]:
    question = (
        "¿Qué construcción, fondo e interior quieres revisar? Un instalador debe "
        "definir y comprobar el amarre y el anclaje según el muro y la carga; "
        "esta vista no certifica el montaje."
    )
    return {
        "nominal_draft_request": None,
        "nominal_draft_scope": "CONCEPT_ONLY",
        "nominal_draft_blockers": [
            "wall_mounted:construction_back_and_internal_layout_unconfirmed",
            "wall_mounted:installer_must_assess_wall_fixing_and_load",
        ],
        "nominal_draft_next_question": question,
        "nominal_draft_engine_status": "CONCEPT_ONLY",
        "nominal_draft_geometry_sha256": None,
        "nominal_draft_piece_count": 0,
        "nominal_draft_provenance": "CLIENT_TEXT_REVIEW_ONLY",
        "nominal_draft_warnings": [
            "NOT_CERTIFIED_INSTALLATION",
            "NO_ANCHORS_OR_LOAD_CAPACITY_ARE_PROPOSED",
            "HARDWARE_NOT_SELECTED_OR_CERTIFIED",
        ],
        "nominal_draft_opening_review": {
            "status": "PENDING", "elements": [], "hardware_selected": False,
        },
        "can_generate_f7c": False,
        **{flag: False for flag in _FLAGS},
    }


def _guided_open_cabinet_handoff(
    decisions: dict[str, dict[str, Any]], *, photo_attached: bool,
) -> dict[str, Any]:
    """Build a review-only request from explicit owner decisions and existing F6."""
    required = (
        "project_type", "dimensions_mm", "material", "thickness_mm",
        "construction", "wall_contact", "support", "internal_layout",
        "drawers", "doors", "back", "countertop",
    )
    blockers: list[str] = []
    warnings = [
        "MATERIAL_ID_IS_GENERIC_NOT_SKU_OR_FINISH.",
        "NOMINAL_PANELS_DO_NOT_INCLUDE_EDGEBAND_OR_CUT_COMPENSATION.",
        "JOINTS_LOAD_STABILITY_AND_ANCHORAGE_REMAIN_UNVERIFIED.",
    ]
    values: dict[str, Any] = {}
    for field in required:
        entry = decisions.get(field)
        if (field == "internal_layout" and type(entry) is dict
                and entry.get("value") == [] and entry.get("status") == "proposed"
                and entry.get("source") == "ENGINE_CALCULATED"):
            values[field] = []
            warnings.append("NO_ADDITIONAL_DIVIDERS_ENGINE_PROPOSED_NOT_OWNER_APPROVED.")
        elif type(entry) is not dict or entry.get("value") in (None, "pending"):
            blockers.append(f"{field}:explicit_confirmation_required")
        elif entry.get("source") != "OWNER_TEXT":
            blockers.append(f"{field}:OWNER_TEXT_required")
        elif entry.get("status") != "confirmed":
            blockers.append(f"{field}:confirmed_value_required")
        else:
            values[field] = entry["value"]

    project_type = _fold(str(values.get("project_type", "")))
    if "project_type" in values and project_type not in {
        "gabinete", "cabinet", "cajonera", "closet",
    }:
        blockers.append("project_type:unsupported")

    dimensions = values.get("dimensions_mm")
    if ("dimensions_mm" in values and (
            type(dimensions) is not dict
            or set(dimensions) != {"width_mm", "height_mm", "depth_mm"}
            or any(type(n) is not int or n <= 0 for n in dimensions.values()))):
        blockers.append("dimensions_mm:positive_exterior_integers_required")

    thickness = values.get("thickness_mm")
    if "thickness_mm" in values and (type(thickness) is not int or thickness <= 0):
        blockers.append("thickness_mm:positive_integer_required")
    materials = {"melamina": "MELAMINA", "mdp": "MDP", "mdf": "MDF", "mdf_rh": "MDF_RH"}
    material = values.get("material")
    if "material" in values and _fold(str(material)) not in materials:
        blockers.append("material:unsupported_catalog_value")
    if "construction" in values and values["construction"] not in {
            "sides_full", "top_bottom_full"}:
        blockers.append("construction:unsupported")

    exact_choices = (
        ("wall_contact", False, "wall_contact:must_be_separate"),
        ("support", {"style": "floor_direct"}, "support:floor_direct_required"),
        ("internal_layout", ["open"], "internal_layout:must_be_open"),
        ("drawers", "none", "drawers:unsupported_for_open_cabinet"),
        ("doors", "none", "doors:unsupported_for_open_cabinet"),
        ("back", "none", "back:must_be_explicitly_absent"),
        ("countertop", {"present": False}, "countertop:must_be_explicitly_absent"),
    )
    for field, expected, reason in exact_choices:
        internal_layout = decisions.get("internal_layout")
        if (field == "internal_layout" and type(internal_layout) is dict
                and internal_layout.get("value") == []
                and internal_layout.get("status") == "proposed"
                and internal_layout.get("source") == "ENGINE_CALCULATED"):
            continue
        if (field in values and (type(values[field]) is not type(expected)
                                 or values[field] != expected)):
            blockers.append(reason)

    for field in ("front_style", "opening_intent"):
        entry = decisions.get(field)
        if (type(entry) is dict and entry.get("value") not in (None, "pending", "none", "")
                and entry.get("status") in ("confirmed", "proposed")):
            blockers.append(f"{field}:requires_explicit_fronts")

    for field in ("countertop_support", "cabinet_bracing", "anti_tip_anchor"):
        entry = decisions.get(field)
        if (type(entry) is dict and entry.get("value") not in (None, "pending", "none", "")
                and entry.get("status") in ("confirmed", "proposed")):
            blockers.append(f"{field}:not_represented_in_open_cabinet_request")

    finish_entry = decisions.get("finish")
    if (type(finish_entry) is dict
            and finish_entry.get("value") not in (None, "pending", "none", "")
            and finish_entry.get("status") in ("confirmed", "proposed")):
        warnings.append("FINISH_NOT_REPRESENTED_IN_GEOMETRY.")
    if photo_attached:
        warnings.extend((
            "PHOTO_NOT_USED_FOR_GEOMETRY",
            "The nominal draft does not reproduce or validate the photo.",
        ))

    result: dict[str, Any] = {
        "nominal_draft_request": None,
        "nominal_draft_scope": "BLOCKED_UNSUPPORTED_OR_INCOMPLETE",
        "nominal_draft_blockers": list(dict.fromkeys(blockers))[:16],
        "nominal_draft_geometry_sha256": None,
        "nominal_draft_piece_count": 0,
        "nominal_draft_provenance": None,
        "nominal_draft_warnings": warnings,
    }
    if blockers:
        return result

    width = dimensions["width_mm"]
    height = dimensions["height_mm"]
    depth = dimensions["depth_mm"]
    material_id = f"{materials[_fold(str(material))]}_{thickness}"
    module_spec = {
        "type": "modular_run",
        "application": "cabinet_run",
        "width_mm": width,
        "height_mm": height,
        "depth_mm": depth,
        "installation": "freestanding",
        "modules": [{
            "module_id": "GABINETE_1",
            "width_mm": width,
            "panel_thickness_mm": thickness,
            "material_id": material_id,
            "construction": values["construction"],
            "fronts": "none",
            "back": "none",
            "support": "floor",
            "drawers": "none",
        }],
    }
    request = {"action": "modular", "module_spec": module_spec}
    try:
        maestro = consult_maestro(request)
        modular = maestro.get("modular")
        if type(modular) is not dict:
            blockers.append("maestro:modular_result_missing")
        else:
            parts = modular.get("parts")
            roles = {part.get("role") for part in parts if type(part) is dict} \
                if type(parts) is list else set()
            piece_ids = [part.get("piece_id") for part in parts if type(part) is dict] \
                if type(parts) is list else []
            if (modular.get("status") != "DRAFT_NOT_FOR_CUTTING"
                    or modular.get("piece_count") != 4 or len(piece_ids) != 4
                    or len(set(piece_ids)) != 4
                    or roles != {"left_side", "right_side", "top", "bottom"}
                    or any(modular.get(flag) is not False for flag in _FLAGS)
                    or any(maestro.get(flag) is not False for flag in _FLAGS)):
                blockers.append("maestro:four_panel_review_contract_mismatch")
            cad = cad_exchange(modular)
            boxes = cad.get("boxes")
            cad_ids = [box.get("piece_id") for box in boxes if type(box) is dict] \
                if type(boxes) is list else []
            cad_roles = {box.get("role") for box in boxes if type(box) is dict} \
                if type(boxes) is list else set()
            if (cad.get("status") != "DRAFT_NOT_FOR_CUTTING"
                    or cad.get("bounds_xyz_mm") != [width, height, depth]
                    or len(cad_ids) != 4 or len(set(cad_ids)) != 4
                    or set(cad_ids) != set(piece_ids)
                    or cad_roles != {"left_side", "right_side", "top", "bottom"}
                    or type(cad.get("geometry_sha256")) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", cad["geometry_sha256"])
                    or any(cad.get(flag) is not False for flag in (
                        "fabrication_ready", "cutting_ready", "drilling_ready",
                    ))):
                blockers.append("cad_exchange:geometry_or_safety_contract_mismatch")
    except MaestroError as exc:
        blockers.append(f"maestro:{exc}")
    except DesignError as exc:
        blockers.append(f"cad_or_geometry:{exc}")

    if blockers:
        result["nominal_draft_blockers"] = list(dict.fromkeys(blockers))[:16]
        return result
    result.update({
        "nominal_draft_request": request,
        "nominal_draft_scope": "OPEN_CABINET_REVIEW_ONLY",
        "nominal_draft_blockers": [],
        "nominal_draft_geometry_sha256": cad["geometry_sha256"],
        "nominal_draft_piece_count": 4,
        "nominal_draft_provenance": "CLIENT_DECLARED_OWNER_TEXT_NOT_AUTHENTICATED",
    })
    return result


def _guided_multicomponent_handoff(
    decisions: dict[str, dict[str, Any]], detail_spec: dict[str, Any] | None, *,
    photo_attached: bool, utterance: str = '', revision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a proposed F6 composition against owner declarations and reuse Maestro."""
    warnings = [
        "CLIENT_PROPOSED_GEOMETRY_NOT_OWNER_APPROVED.",
        "HARDWARE_NOT_SELECTED_OR_CERTIFIED.",
        "FINISH_NOT_REPRESENTED_IN_GEOMETRY.",
        "NOMINAL_PANELS_DO_NOT_INCLUDE_EDGEBAND_OR_CUT_COMPENSATION.",
        "LOADS_JOINTS_STABILITY_AND_ANCHORAGE_REMAIN_UNVERIFIED.",
    ]
    if photo_attached:
        warnings.extend((
            "PHOTO_NOT_USED_FOR_GEOMETRY",
            "The nominal draft does not reproduce or validate the photo.",
        ))
    result: dict[str, Any] = {
        "nominal_draft_request": None,
        "nominal_draft_scope": "BLOCKED_UNSUPPORTED_OR_INCOMPLETE",
        "nominal_draft_blockers": [],
        "nominal_draft_engine_status": None,
        "nominal_draft_geometry_sha256": None,
        "nominal_draft_piece_count": 0,
        "nominal_draft_provenance": None,
        "nominal_draft_warnings": warnings,
        "nominal_draft_opening_review": {
            "status": "PENDING", "elements": [],
            "hardware_selected": False,
        },
        "can_generate_f7c": False,
    }
    blockers: list[str] = []
    required = (
        "project_type", "dimensions_mm", "material", "thickness_mm",
        "construction", "wall_contact", "support", "internal_layout",
        "drawers", "doors", "back",
    )
    declared_project_type = _fold(str(
        decisions.get("project_type", {}).get("value", "")
    ))
    if declared_project_type != "closet":
        required = (*required, "countertop")
    values: dict[str, Any] = {}
    for field in required:
        entry = decisions.get(field)
        if (field == "internal_layout" and type(entry) is dict
                and entry.get("value") == [] and entry.get("status") == "proposed"
                and entry.get("source") == "ENGINE_CALCULATED"):
            values[field] = []
            warnings.append("NO_ADDITIONAL_DIVIDERS_ENGINE_PROPOSED_NOT_OWNER_APPROVED.")
        elif type(entry) is not dict or entry.get("value") in (None, "pending"):
            blockers.append(f"{field}:explicit_confirmation_required")
        elif entry.get("source") != "OWNER_TEXT":
            blockers.append(f"{field}:OWNER_TEXT_required")
        elif entry.get("status") != "confirmed":
            blockers.append(f"{field}:confirmed_value_required")
        else:
            values[field] = entry["value"]

    project_type = _fold(str(values.get("project_type", "")))
    allowed_types = {"gabinete", "cabinet", "cajonera", "closet"}
    if "project_type" in values and project_type not in allowed_types:
        blockers.append("project_type:unsupported")
    dimensions = values.get("dimensions_mm")
    valid_dimensions = (
        type(dimensions) is dict
        and set(dimensions) == {"width_mm", "height_mm", "depth_mm"}
        and all(type(value) is int and value > 0 for value in dimensions.values())
    )
    if "dimensions_mm" in values and not valid_dimensions:
        blockers.append("dimensions_mm:positive_exterior_integers_required")

    material_names = {
        "melamina": "MELAMINA", "mdp": "MDP", "mdf": "MDF",
        "mdf_rh": "MDF_RH",
    }
    material = _fold(str(values.get("material", "")))
    thickness = values.get("thickness_mm")
    if "material" in values and material not in material_names:
        blockers.append("material:unsupported_catalog_value")
    if "thickness_mm" in values and (type(thickness) is not int or thickness <= 0):
        blockers.append("thickness_mm:positive_integer_required")
    body_material_id = (
        f"{material_names[material]}_{thickness}"
        if material in material_names and type(thickness) is int and thickness > 0
        else None
    )
    construction = values.get("construction")
    if "construction" in values and construction not in {"sides_full", "top_bottom_full"}:
        blockers.append("construction:unsupported")
    wall_contact = values.get("wall_contact")
    if "wall_contact" in values and type(wall_contact) is not bool:
        blockers.append("wall_contact:boolean_required")

    support = values.get("support")
    support_style = support.get("style") if type(support) is dict else None
    support_height = support.get("height_mm") if type(support) is dict else None
    if "support" in values and support_style not in {
        "floor_direct", "legs", "plinth", "wall_mounted",
    }:
        blockers.append("support:explicit_supported_style_required")
    if support_style in {"legs", "plinth"} and (
        type(support_height) is not int or support_height <= 0
    ):
        blockers.append("support:positive_height_required")

    if detail_spec is None:
        blockers.append("nominal_detail_spec:explicit_modular_run_required")
        result["nominal_draft_blockers"] = list(dict.fromkeys(blockers))[:32]
        return result
    if type(detail_spec) is not dict:
        blockers.append("nominal_detail_spec:object_required")
        modules: list[dict[str, Any]] = []
    else:
        if set(detail_spec) - ROOT_FIELDS:
            blockers.append("module_spec:unknown_root_fields")
        if detail_spec.get("type") != "modular_run":
            blockers.append("module_spec:type_must_be_modular_run")
        expected_application = (
            "closet" if project_type == "closet" else
            "kitchen" if _fold(str(decisions.get("use", {}).get("value", ""))) == "kitchen"
            else "cabinet_run"
        )
        if detail_spec.get("application") != expected_application:
            blockers.append("module_spec:application_mismatch_owner")
        installation = detail_spec.get("installation")
        if installation not in {"built_in", "freestanding", "wall_mounted"}:
            blockers.append("module_spec:installation_invalid")
        if valid_dimensions and any(
            detail_spec.get(field) != dimensions[owner_field]
            for field, owner_field in (
                ("width_mm", "width_mm"), ("height_mm", "height_mm"),
                ("depth_mm", "depth_mm"),
            )
        ):
            blockers.append("module_spec:root_dimensions_mismatch_owner")
        if installation == "built_in" and wall_contact is False:
            blockers.append("module_spec:built_in_conflicts_with_wall_contact")
        if installation in {"built_in", "wall_mounted"} and wall_contact is False:
            blockers.append("module_spec:installation_conflicts_with_owner_wall_decision")

        raw_modules = detail_spec.get("modules")
        if type(raw_modules) is not list or not 1 <= len(raw_modules) <= 12:
            blockers.append("module_spec:one_to_twelve_modules_required")
            modules = []
        else:
            modules = [item for item in raw_modules if type(item) is dict]
            if len(modules) != len(raw_modules):
                blockers.append("module_spec:module_object_required")
            if any(set(module) - MODULE_FIELDS for module in modules):
                blockers.append("module_spec:unknown_module_fields")
            if all(type(module.get("width_mm")) is int and module["width_mm"] > 0
                   for module in modules):
                total_width = sum(module["width_mm"] for module in modules)
                if detail_spec.get("width_mm") != total_width:
                    blockers.append("module_spec:module_width_sum_mismatch")
            if any(type(module.get("drawers")) is list for module in modules):
                warnings.append(
                    "DRAWER_CLEARANCES_ENGINE_PROPOSED_NOT_USER_SUPPLIED; "
                    "ZERO_PLACEHOLDER_DOES_NOT_DEFINE_A_FUNCTIONAL_SLIDE_FIT."
                )
        expected_support = "wall" if support_style == "wall_mounted" else "floor"
        if support_style == "wall_mounted" and (
            installation != "wall_mounted" or wall_contact is not True
        ):
            blockers.append("module_spec:wall_mounted_requires_wall_installation")
        for module in modules:
            if body_material_id is not None and module.get("material_id") != body_material_id:
                blockers.append(f"module_spec:{module.get('module_id', '?')}:body_material_mismatch_owner")
            if type(thickness) is int and module.get("panel_thickness_mm") != thickness:
                blockers.append(f"module_spec:{module.get('module_id', '?')}:body_thickness_mismatch_owner")
            if construction is not None and module.get("construction") != construction:
                blockers.append(f"module_spec:{module.get('module_id', '?')}:construction_mismatch_owner")
            if module.get("support") != expected_support:
                blockers.append(f"module_spec:{module.get('module_id', '?')}:support_mismatch_owner")

    doors = values.get("doors")
    if doors == "none":
        expected_doors = 0
    elif type(doors) is dict and type(doors.get("count")) is int and doors["count"] > 0:
        expected_doors = doors["count"]
    else:
        expected_doors = None
        if "doors" in values:
            blockers.append("doors:explicit_positive_count_or_none_required")
    actual_doors = 0
    for module in modules:
        fronts = module.get("fronts")
        if type(fronts) is dict and type(fronts.get("leaf_count")) is int:
            actual_doors += fronts["leaf_count"]
        elif fronts not in ("none", "pending"):
            blockers.append(f"module_spec:{module.get('module_id', '?')}:fronts_invalid")
        elif fronts == "pending":
            blockers.append(f"module_spec:{module.get('module_id', '?')}:fronts_pending")
    if expected_doors is not None and actual_doors != expected_doors:
        blockers.append("module_spec:door_count_mismatch_owner")
    front_style = decisions.get("front_style")
    if type(front_style) is dict and front_style.get("status") == "confirmed":
        if any(type(module.get("fronts")) is dict
               and module["fronts"].get("style") != front_style.get("value")
               for module in modules):
            blockers.append("module_spec:front_style_mismatch_owner")

    drawer_entry = values.get("drawers")
    if drawer_entry == "none":
        expected_drawers = 0
    elif type(drawer_entry) is dict and type(drawer_entry.get("count")) is int:
        expected_drawers = drawer_entry["count"]
    else:
        expected_drawers = None
        if "drawers" in values:
            blockers.append("drawers:explicit_count_or_none_required")
    actual_drawers = 0
    for module in modules:
        drawer_spec = module.get("drawers", "none")
        if type(drawer_spec) is list:
            actual_drawers += len(drawer_spec)
        elif drawer_spec == "pending":
            blockers.append(f"module_spec:{module.get('module_id', '?')}:drawers_pending")
    if expected_drawers is not None and actual_drawers != expected_drawers:
        blockers.append("module_spec:drawer_count_mismatch_owner")

    layout = values.get("internal_layout")
    layout_elements = (
        layout.get("elements") if type(layout) is dict else layout
    )
    if type(layout_elements) is list:
        if "horizontal" in layout_elements and not all(
            module.get("horizontal_divider") for module in modules
        ):
            blockers.append("module_spec:horizontal_divider_missing")
        if "vertical" in layout_elements and not all(
            module.get("vertical_divider") for module in modules
        ):
            blockers.append("module_spec:vertical_divider_missing")

    back = values.get("back")
    if back == "none" and any(module.get("back") != "none" for module in modules):
        blockers.append("module_spec:back_mismatch_owner")
    if back != "none" and "back" in values and not any(
        type(module.get("back")) is dict for module in modules
    ):
        blockers.append("module_spec:back_panel_missing")

    countertop = values.get("countertop")
    countertop_modules = [
        module for module in modules if type(module.get("countertop")) is dict
    ]
    if type(countertop) is dict and countertop.get("present") is False:
        if countertop_modules:
            blockers.append("module_spec:unexpected_countertop")
    elif type(countertop) is dict and countertop.get("present") is True:
        owner_dims = countertop.get("dimensions_mm")
        if (type(owner_dims) is not dict
                or not {"width_mm", "depth_mm"}.issubset(owner_dims)
                or type(countertop.get("thickness_mm")) is not int
                or countertop["thickness_mm"] <= 0):
            blockers.append("countertop:owner_dimensions_and_thickness_required")
        if len(countertop_modules) != 1:
            blockers.append("module_spec:one_explicit_countertop_required")
        elif type(owner_dims) is dict:
            proposed = countertop_modules[0]["countertop"]
            if any(proposed.get(field) != owner_dims.get(field) for field in (
                "width_mm", "depth_mm",
            )) or proposed.get("thickness_mm") != countertop.get("thickness_mm"):
                blockers.append("module_spec:countertop_dimensions_or_thickness_mismatch_owner")
            owner_material = countertop.get("material_id")
            if owner_material is not None and proposed.get("material_id") != owner_material:
                blockers.append("module_spec:countertop_material_mismatch_owner")
            if owner_material is None:
                proposed_material = proposed.get("material_id")
                legacy_placeholder = re.fullmatch(
                    r"MESON_(\d+)", proposed_material
                ) if type(proposed_material) is str else None
                if not (
                    proposed_material == "MATERIAL_PENDIENTE"
                    or legacy_placeholder is not None
                    and legacy_placeholder.group(1) == str(countertop.get("thickness_mm"))
                ):
                    blockers.append(
                        "module_spec:countertop_material_specific_unconfirmed"
                    )
                warnings.append("COUNTERTOP_MATERIAL_NOT_OWNER_APPROVED")
            warnings.extend((
                "COUNTERTOP_OVERHANG_SPLIT_IS_PROPOSED_NOT_OWNER_APPROVED",
                "COUNTERTOP_SUPPORT_NOT_STRUCTURALLY_VERIFIED",
            ))
            if support_style in {"legs", "plinth"}:
                support_concept = countertop_modules[0].get("support_concept")
                overall = (dimensions["height_mm"] + support_height
                           + countertop["thickness_mm"]
                           if valid_dimensions and type(support_height) is int else None)
                if (type(support_concept) is not dict
                        or support_concept.get("style") != support_style
                        or support_concept.get("support_height_mm") != support_height
                        or support_concept.get("overall_height_mm") != overall):
                    blockers.append("module_spec:support_or_derived_overall_height_mismatch")
                warnings.extend((
                    "OVERALL_HEIGHT_DERIVED_NOT_OWNER_DECLARED",
                    "LEGS_ARE_CONCEPT_ONLY_NOT_PHYSICAL_PIECES",
                ))

    if re.search(
        r"\b(?:hazlo|dejalo|deja|pon|vuelve|genera|entrega|quiero)\b"
        r"[^.]{0,48}\b(?:cortable|fabricable|listo para cortar|listo para fabricar)\b",
        _fold(utterance),
    ):
        blockers.append("authorization:fabrication_cutting_or_drilling_not_permitted")

    result["nominal_draft_warnings"] = list(dict.fromkeys(warnings))
    if blockers:
        result["nominal_draft_blockers"] = list(dict.fromkeys(blockers))[:32]
        return result

    intent_entry = decisions.get("opening_intent")
    opening_intent = None
    opening_source = "PENDING"
    if type(intent_entry) is dict:
        candidate_intent = intent_entry.get("value")
        if candidate_intent in OPENING_SYSTEMS:
            opening_intent = candidate_intent
            opening_source = (
                "OWNER_TEXT_CONFIRMED" if intent_entry.get("status") == "confirmed"
                and intent_entry.get("source") == "OWNER_TEXT"
                else "CLIENT_PROPOSED_NOT_OWNER_APPROVED"
            )
    if opening_intent:
        for module in modules:
            drawers = module.get("drawers")
            if type(drawers) is list:
                for drawer in drawers:
                    facade = drawer.get("facade") if type(drawer) is dict else None
                    if type(facade) is dict:
                        facade["opening_system"] = opening_intent

    request = {"action": "modular", "module_spec": copy.deepcopy(detail_spec)}
    try:
        maestro = consult_maestro(request)
        modular = maestro.get("modular")
        if type(modular) is not dict:
            blockers.append("maestro:modular_result_missing")
        else:
            if installation == "built_in" and (
                type(modular.get("site")) is not dict
                or modular["site"].get("complete") is not True
            ):
                result["nominal_draft_engine_status"] = modular.get("status")
                result["nominal_draft_blockers"] = ["modular:NEEDS_SITE_MEASUREMENTS"]
                return result
            result["nominal_draft_engine_status"] = modular.get("status")
            if modular.get("status") != "DRAFT_NOT_FOR_CUTTING":
                result["nominal_draft_blockers"] = list(dict.fromkeys(
                    str(item) for item in modular.get("blockers", [])[:16]
                )) or ["maestro:modular_status_" + str(modular.get("status"))]
                questions = maestro.get("questions")
                if type(questions) is list and questions:
                    result["nominal_draft_next_question"] = questions[0].get("question")
                return result
            parts = modular.get("parts")
            parts = parts if type(parts) is list else []
            piece_ids = [part.get("piece_id") for part in parts if type(part) is dict]
            roles = [part.get("role") for part in parts if type(part) is dict]
            if (maestro.get("action") != "modular"
                    or maestro.get("status") != "DRAFT_NOT_FOR_CUTTING"
                    or modular.get("piece_count") != len(parts)
                    or not parts or len(piece_ids) != len(parts)
                    or len(set(piece_ids)) != len(piece_ids)
                    or any(type(role) is not str or not role for role in roles)
                    or any(modular.get(flag) is not False for flag in _FLAGS)
                    or any(maestro.get(flag) is not False for flag in _FLAGS)):
                blockers.append("maestro:modular_review_or_safety_contract_mismatch")
            cad = validate_exchange(cad_exchange(modular))
            cad_boxes = cad.get("boxes")
            cad_boxes = cad_boxes if type(cad_boxes) is list else []
            cad_ids = [box.get("piece_id") for box in cad_boxes if type(box) is dict]
            cad_roles = [box.get("role") for box in cad_boxes if type(box) is dict]
            if (cad.get("status") != "DRAFT_NOT_FOR_CUTTING"
                    or len(cad_ids) != len(parts) or len(set(cad_ids)) != len(cad_ids)
                    or set(cad_ids) != set(piece_ids)
                    or sorted(cad_roles) != sorted(roles)
                    or type(cad.get("geometry_sha256")) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", cad["geometry_sha256"])
                    or cad.get("manufacturing_holes") != []
                    or any(cad.get(flag) is not False for flag in (
                        "fabrication_ready", "cutting_ready", "drilling_ready",
                    ))):
                blockers.append("cad_exchange:geometry_or_safety_contract_mismatch")
            warnings.extend(str(item) for item in modular.get("blockers", []))
    except MaestroError as exc:
        blockers.append(f"maestro:{exc}")
    except DesignError as exc:
        blockers.append(f"cad_or_geometry:{exc}")

    result["nominal_draft_warnings"] = list(dict.fromkeys(warnings))
    if blockers:
        result["nominal_draft_blockers"] = list(dict.fromkeys(blockers))[:32]
        return result

    opening_elements = []
    for part in parts:
        role = part.get("role")
        if not (type(role) is str and (role.startswith("front_") or role == "drawer_facade")):
            continue
        part_intent = opening_intent or part.get("opening_system") or "pending"
        opening_elements.append({
            "module_id": part.get("module_id"),
            "piece_id": part.get("piece_id"),
            "element_type": "drawer" if role == "drawer_facade" else "door",
            "opening_system": part_intent,
            "source_status": opening_source if opening_intent else "CLIENT_PROPOSED_OR_PENDING",
            "hardware_selected": False,
        })
    result.update({
        "nominal_draft_request": request,
        "nominal_draft_scope": "CLIENT_PROPOSED_MULTICOMPONENT_REVIEW_ONLY",
        "nominal_draft_blockers": [],
        "nominal_draft_engine_status": modular["status"],
        "nominal_draft_geometry_sha256": cad["geometry_sha256"],
        "nominal_draft_piece_count": len(parts),
        "nominal_draft_provenance": "CLIENT_PROPOSED_NOT_OWNER_APPROVED",
        "nominal_draft_warnings": list(dict.fromkeys(warnings)),
        "nominal_draft_opening_review": {
            "status": "REVIEW_ONLY" if opening_elements else "NO_OPENING_COMPONENTS",
            "elements": opening_elements,
            "hardware_selected": False,
        },
    })
    if revision is not None:
        result["nominal_draft_revision"] = copy.deepcopy(revision)
    return result


def _apply_modular_drawer_revisions(
    base_spec: dict[str, Any], original_utterance: str,
    corrections: list[str],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Replay the existing F1 correction flow into one explicit F6 drawer module."""
    if not corrections:
        return copy.deepcopy(base_spec), None
    preview = preview_natural_request(original_utterance, include_concept_sketch=False)
    base_option = preview.get("illustrative_drawer_layout_option")
    if type(base_option) is not dict or type(base_option.get("proposed_request")) is not dict:
        raise MaestroError("drawer_revision:original_request_has_no_f1_layout")
    base_reference = base_option["proposed_request"].get("module_spec")
    spec = copy.deepcopy(base_spec)
    modules = spec.get("modules")
    if (type(modules) is not list or len(modules) != 1
            or type(modules[0]) is not dict
            or modules[0].get("drawer_layout_reference") != base_reference):
        raise MaestroError("drawer_revision:one_module_must_match_original_f1_reference")
    revised = preview_conversation(
        original_utterance, corrections=corrections, max_questions=3,
    )
    option = revised.get("illustrative_drawer_layout_option")
    request = option.get("proposed_request") if type(option) is dict else None
    reference = request.get("module_spec") if type(request) is dict else None
    if type(reference) is not dict:
        raise MaestroError("drawer_revision:revised_f1_reference_missing")
    original_plan = propose_drawer_layout(base_reference)
    revised_plan = propose_drawer_layout(reference)
    if (original_plan.get("external_dimensions_mm")
            != revised_plan.get("external_dimensions_mm")
            or original_plan.get("piece_count") != 0
            or revised_plan.get("piece_count") != 0):
        raise MaestroError("drawer_revision:outer_envelope_or_review_only_contract_changed")
    drawers = modules[0].get("drawers")
    plan = revised_plan.get("opening_plan")
    if (type(drawers) is not list or type(plan) is not list
            or len(drawers) != len(plan)):
        raise MaestroError("drawer_revision:drawer_count_changed")
    by_id = {item.get("drawer_id"): item for item in plan if type(item) is dict}
    if len(by_id) != len(plan) or {item.get("drawer_id") for item in drawers
                                  if type(item) is dict} != set(by_id):
        raise MaestroError("drawer_revision:drawer_ids_changed")
    for drawer in drawers:
        opening = by_id[drawer["drawer_id"]]
        drawer["opening_bottom_offset_mm"] = opening["opening_bottom_offset_mm"]
        drawer["opening_height_mm"] = opening["opening_height_mm"]
        proposed_box_height = opening["opening_height_mm"] - 20
        if proposed_box_height <= 0:
            raise MaestroError(
                "drawer_revision:opening_too_short_for_proposed_box_clearance"
            )
        drawer["box_height_mm"] = min(
            drawer["box_height_mm"], proposed_box_height,
        )
    modules[0]["drawer_layout_reference"] = reference
    last_revision = revised.get("last_revision")
    if (type(last_revision) is not dict
            or last_revision.get("envelope_unchanged") is not True):
        raise MaestroError("drawer_revision:correction_not_confirmed_by_existing_f1")
    return spec, {
        "history": copy.deepcopy(revised.get("drawer_revisions_history", [])),
        "last_revision": copy.deepcopy(last_revision),
        "reference_ids_preserved": True,
        "exterior_dimensions_preserved": True,
    }


def prepare_guided_design_v1(request: dict[str, Any]) -> dict[str, Any]:
    """Use one client-carried trace and the existing preview/Maestro engines."""
    required_keys = {
        "review_kind", "utterance", "review_state", "review_updates",
        "photo_observations",
    }
    allowed_keys = required_keys | {"nominal_detail_spec"}
    if (type(request) is not dict or not required_keys.issubset(request)
            or set(request) - allowed_keys):
        raise MaestroError(
            "guided_design_v1 requiere review_kind, utterance, review_state, "
            "review_updates y photo_observations, sin campos adicionales."
        )
    nominal_detail_spec = request.get("nominal_detail_spec")
    if nominal_detail_spec is not None and type(nominal_detail_spec) is not dict:
        raise MaestroError("nominal_detail_spec debe ser objeto JSON o null.")
    if request["review_kind"] != "guided_design_v1":
        raise MaestroError("Tipo de revisión guiada desconocido.")
    utterance = request["utterance"]
    if type(utterance) is not str or not utterance.strip() or len(utterance) > _MAX_TEXT:
        raise MaestroError("utterance debe tener entre 1 y 2000 caracteres.")
    previous_state = request["review_state"]
    if previous_state is not None and type(previous_state) is not dict:
        raise MaestroError("review_state debe ser un objeto JSON o null.")
    if previous_state is not None:
        # Validate the complete client-carried chain before using any decision.
        update_review_state(previous_state, updates=[], pending_fields=[])

    natural_preview = preview_natural_request(utterance, include_concept_sketch=False)
    updates = _guided_text_updates(utterance, natural_preview, previous_state)
    parsed_by_field = {item["field"]: item for item in updates}
    confirmations = _guided_confirmation_updates(
        utterance, previous_state, set(parsed_by_field),
    )
    updates.extend(confirmations)
    parsed_by_field.update({item["field"]: item for item in confirmations})

    raw_updates = request["review_updates"]
    if type(raw_updates) is not list or len(raw_updates) > _MAX_REVIEW_FIELDS:
        raise MaestroError("review_updates debe ser una lista de hasta 40 elementos.")
    seen_fields: set[str] = set()
    for item in raw_updates:
        if type(item) is not dict or set(item) != {"field", "value", "status", "source"}:
            raise MaestroError("Cada review_update requiere field, value, status y source.")
        field, status, source = item["field"], item["status"], item["source"]
        if (type(field) is not str or field not in _REVIEW_ALLOWED_FIELDS
                or field in seen_fields or type(status) is not str
                or status not in _REVIEW_STATUSES or type(source) is not str
                or source not in _REVIEW_SOURCES):
            raise MaestroError("review_update contiene campo, estado o fuente inválidos.")
        if field == "nominal_detail_spec":
            raise MaestroError("nominal_detail_spec es un estado interno de revision, no un review_update.")
        seen_fields.add(field)
        if field == "photo_observations":
            raise MaestroError(
                "photo_observations debe usar su campo separado y quedar sin confirmar."
            )
        if source != "OWNER_TEXT" and status in ("confirmed", "rejected"):
            raise MaestroError("Una fuente distinta de texto explícito no confirma decisiones.")
        if field in parsed_by_field and item["value"] == parsed_by_field[field]["value"]:
            # Natural text is the source of a confirmation; metadata cannot upgrade it.
            continue
        updates.append({
            "field": field, "value": copy.deepcopy(item["value"]),
            "status": "proposed", "source": "ENGINE_CALCULATED",
        })

    photo = request["photo_observations"]
    if photo is not None:
        _photo_observation(photo)
        updates.append({
            "field": "photo_observations", "value": photo,
            "status": "proposed", "source": "IMAGE_OBSERVED_UNCONFIRMED",
        })

    # preview_conversation parses the same utterance and applies its explicit
    # decisions to the one review_state; the state remains in the caller's hands.
    preview = preview_conversation(
        utterance, review_state=previous_state, review_updates=updates,
        pending_fields=[], max_questions=3,
    )
    accumulated = preview["review_state"]
    decisions = accumulated["decisions"]
    missing = [field for field in _guided_question_fields(decisions)
               if field not in decisions]
    guided = update_review_state(
        accumulated, pending_fields=missing, max_questions=3,
    )
    state = guided["review_state"]
    decisions = state["decisions"]

    prior_nominal = (
        previous_state.get("decisions", {}).get("nominal_detail_spec", {}).get("value")
        if type(previous_state) is dict else None
    )
    stored_spec: dict[str, Any] | None = None
    source_utterance = utterance
    correction_history: list[str] = []
    if (type(prior_nominal) is dict
            and set(prior_nominal) == {"base_spec", "source_utterance", "corrections"}
            and type(prior_nominal.get("base_spec")) is dict
            and type(prior_nominal.get("source_utterance")) is str
            and type(prior_nominal.get("corrections")) is list
            and len(prior_nominal["corrections"]) <= 12
            and all(type(item) is str for item in prior_nominal["corrections"])):
        stored_spec = copy.deepcopy(prior_nominal["base_spec"])
        source_utterance = prior_nominal["source_utterance"]
        correction_history = list(prior_nominal["corrections"])

    drawer_correction = is_drawer_correction_instruction(utterance)
    effective_detail_spec: dict[str, Any] | None = nominal_detail_spec
    revision: dict[str, Any] | None = None
    revision_blocker: str | None = None
    candidate_base: dict[str, Any] | None = None
    if drawer_correction:
        if stored_spec is None:
            revision_blocker = "drawer_revision:prior_nominal_design_required"
            effective_detail_spec = {}
        else:
            candidate_base = stored_spec
            candidate_history = [*correction_history, utterance]
            try:
                effective_detail_spec, revision = _apply_modular_drawer_revisions(
                    candidate_base, source_utterance, candidate_history,
                )
                correction_history = candidate_history
            except MaestroError as exc:
                revision_blocker = str(exc)
                # Keep the last valid F1 replay available for review. The
                # rejected instruction is never persisted in correction_history.
                try:
                    effective_detail_spec, revision = _apply_modular_drawer_revisions(
                        candidate_base, source_utterance, correction_history,
                    )
                except MaestroError:
                    effective_detail_spec = copy.deepcopy(stored_spec)
                    revision = None
    elif nominal_detail_spec is not None:
        candidate_base = copy.deepcopy(nominal_detail_spec)
        if stored_spec is not None and nominal_detail_spec == stored_spec:
            candidate_base = stored_spec
            if correction_history:
                try:
                    effective_detail_spec, revision = _apply_modular_drawer_revisions(
                        candidate_base, source_utterance, correction_history,
                    )
                except MaestroError as exc:
                    revision_blocker = str(exc)
                    effective_detail_spec = {}
        else:
            source_utterance = utterance
            correction_history = []
    elif stored_spec is not None:
        candidate_base = stored_spec
        try:
            effective_detail_spec, revision = _apply_modular_drawer_revisions(
                candidate_base, source_utterance, correction_history,
            )
        except MaestroError as exc:
            revision_blocker = str(exc)
            effective_detail_spec = {}

    is_coffee = decisions.get("use", {}).get("value") == "coffee"
    required = ["project_type", "dimensions_mm", "material", "thickness_mm", "construction"]
    if _fold(str(decisions.get("project_type", {}).get("value", ""))) in {
        "gabinete", "cabinet", "cajonera", "closet", "clóset",
    }:
        required.extend(("wall_contact", "internal_layout", "drawers", "doors", "back", "support"))
        if is_coffee:
            required.append("countertop")
    readiness_blockers: list[str] = []
    for field in required:
        entry = decisions.get(field)
        if (entry is None or entry["status"] != "confirmed"
                or entry["value"] is None or entry["value"] == "pending"):
            readiness_blockers.append(field)
    dimensions = decisions.get("dimensions_mm", {}).get("value")
    if (type(dimensions) is not dict
            or set(dimensions) != {"width_mm", "height_mm", "depth_mm"}
            or any(type(value) is not int or value <= 0 for value in dimensions.values())):
        if "dimensions_mm" not in readiness_blockers:
            readiness_blockers.append("dimensions_mm")
    thickness = decisions.get("thickness_mm", {}).get("value")
    if type(thickness) is not int or thickness <= 0:
        if "thickness_mm" not in readiness_blockers:
            readiness_blockers.append("thickness_mm")
    project_type = decisions.get("project_type", {}).get("value")
    project_kind = _fold(str(project_type))
    if project_kind not in {"gabinete", "cabinet", "cajonera", "closet", "clóset"}:
        if "project_type" not in readiness_blockers:
            readiness_blockers.append("project_type")
    ready = not readiness_blockers

    nominal_review = None
    if ready:
        nominal_review = consult_maestro({
            "action": "project",
            "project": {
                "project_type": "gabinete",
                **dimensions,
                "panel_thickness_mm": thickness,
                "construction": decisions["construction"]["value"],
            },
        })

    confirmed = {
        field: copy.deepcopy(entry["value"])
        for field, entry in decisions.items()
        if field != "nominal_detail_spec"
        and entry["status"] == "confirmed" and entry["value"] != "pending"
    }
    proposed = {
        field: copy.deepcopy(entry["value"])
        for field, entry in decisions.items()
        if field != "nominal_detail_spec" and entry["status"] == "proposed"
    }
    pending = [field for field, entry in decisions.items()
               if field != "nominal_detail_spec"
               and (entry["status"] == "pending" or entry["value"] in (None, "pending"))]
    preview_keys = (
        "status", "proposed_request", "explicit_measurements", "ambiguous_fields",
        "unit_requires_confirmation", "resolved_unit_confirmations", "next_step",
    )
    natural_summary = {key: copy.deepcopy(natural_preview[key])
                       for key in preview_keys if key in natural_preview}
    questions = guided["questions"]
    warnings = [
        "review_state es una traza declarada por el cliente; no autentica identidad ni autoriza fabricación.",
        "No se reciben píxeles ni rutas de imagen; cualquier observación se mantiene sin confirmar.",
        "No se selecciona SKU, patrón de perforación, compra ni exportación CAD nativa.",
    ]
    if is_coffee:
        warnings.append(
            "El apoyo vertical del mesón, amarre de carcasa y anclaje anti-vuelco "
            "requieren revisión; la pared no se presume como soporte de carga."
        )
    historical_photo = decisions.get("photo_observations")
    photo_attached = (
        photo is not None or type(historical_photo) is dict
        and historical_photo.get("source") == "IMAGE_OBSERVED_UNCONFIRMED"
    )
    if effective_detail_spec is not None:
        nominal_handoff = _guided_multicomponent_handoff(
            decisions, effective_detail_spec, photo_attached=photo_attached,
            utterance=utterance, revision=revision,
        )
        if revision_blocker:
            nominal_handoff["nominal_draft_blockers"] = list(dict.fromkeys(
                [*nominal_handoff.get("nominal_draft_blockers", []), revision_blocker]
            ))[:32]
            nominal_handoff["nominal_draft_revision_rejected"] = True
            if "No quedan cajones libres" in revision_blocker:
                nominal_handoff["nominal_draft_next_question"] = (
                    "Las alturas de A y B ya usan toda la altura disponible. "
                    "Para bajar C 20 mm habría que redistribuir una altura previa; "
                    "¿prefieres cambiar A o B para liberar ese espacio?"
                )
        if revision is not None and type(effective_detail_spec) is dict:
            drawer_module = effective_detail_spec["modules"][0]
            nominal_handoff["nominal_draft_assumptions"] = [{
                "field": "drawer_box_and_facade_geometry",
                "value": [{
                    "drawer_id": drawer["drawer_id"],
                    "opening_height_mm": drawer["opening_height_mm"],
                    "box_height_mm": drawer["box_height_mm"],
                    "box_clearance_mm": (
                        drawer["opening_height_mm"] - drawer["box_height_mm"]
                    ),
                    "slide_clearance_left_mm": drawer["slide_clearance_left_mm"],
                    "slide_clearance_right_mm": drawer["slide_clearance_right_mm"],
                } for drawer in drawer_module["drawers"]],
                "source": "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
                "reason": "F1 revisa aperturas; la caja sigue siendo geometría nominal sin corredera validada.",
            }]
    elif drawer_correction:
        nominal_handoff = _guided_multicomponent_handoff(
            decisions, {}, photo_attached=photo_attached, utterance=utterance,
        )
        nominal_handoff["nominal_draft_blockers"] = list(dict.fromkeys(
            [*nominal_handoff.get("nominal_draft_blockers", []),
             revision_blocker or "drawer_revision:prior_nominal_design_required"]
        ))[:32]
    else:
        if _guided_needs_modular_spec(decisions):
            current_support = decisions.get("support", {}).get("value")
            current_support_entry = decisions.get("support", {})
            unresolved_wall_structure = any(
                decisions.get(field, {}).get("status") != "confirmed"
                for field in ("construction", "internal_layout", "back")
            )
            wall_back_pending = (
                type(decisions.get("back")) is dict
                and decisions["back"].get("value") == "pending"
            )
            if (nominal_detail_spec is None and stored_spec is None
                    and type(current_support) is dict
                    and current_support.get("style") == "wall_mounted"
                    and current_support_entry.get("source") == "OWNER_TEXT"
                    and (unresolved_wall_structure or wall_back_pending)):
                nominal_handoff = _guided_wall_mounted_concept()
                if wall_back_pending:
                    nominal_handoff["nominal_draft_blockers"] = [
                        "back:owner_decision_pending",
                        "wall_mounted:installer_must_assess_wall_fixing_and_load",
                    ]
                    nominal_handoff["nominal_draft_next_question"] = (
                        "¿Lo dejamos sin fondo posterior para este boceto o quieres especificarlo?"
                    )
            elif _fold(str(decisions.get("project_type", {}).get("value", ""))) == "closet":
                composed_spec, assumptions, compose_blockers = (
                    _guided_compose_closet_spec(decisions)
                )
                if composed_spec is not None:
                    nominal_handoff = _guided_multicomponent_handoff(
                        decisions, composed_spec, photo_attached=photo_attached,
                        utterance=utterance,
                    )
                    nominal_handoff["nominal_draft_assumptions"] = assumptions
                else:
                    nominal_handoff = _guided_multicomponent_handoff(
                        decisions, None, photo_attached=photo_attached,
                        utterance=utterance,
                    )
                    nominal_handoff["nominal_draft_blockers"] = list(dict.fromkeys(
                        [*nominal_handoff.get("nominal_draft_blockers", []),
                         *compose_blockers]
                    ))[:32]
            elif _fold(str(decisions.get("use", {}).get("value", ""))) in {
                "kitchen", "bathroom", "bedroom",
            }:
                composed_spec, assumptions, compose_blockers = (
                    _guided_compose_product_spec(decisions, utterance, natural_preview)
                )
                if composed_spec is not None:
                    nominal_handoff = _guided_multicomponent_handoff(
                        decisions, composed_spec, photo_attached=photo_attached,
                        utterance=utterance,
                    )
                    nominal_handoff["nominal_draft_assumptions"] = assumptions
                    if composed_spec["installation"] == "wall_mounted":
                        nominal_handoff["nominal_draft_warnings"] = list(dict.fromkeys([
                            *nominal_handoff.get("nominal_draft_warnings", []),
                            "NOT_CERTIFIED_INSTALLATION",
                            "NO_ANCHORS_OR_LOAD_CAPACITY_ARE_PROPOSED",
                        ]))
                    module = composed_spec["modules"][0]
                    if type(module.get("drawers")) is list:
                        candidate_base = copy.deepcopy(composed_spec)
                        source_utterance = utterance
                        correction_history = []
                else:
                    nominal_handoff = _guided_multicomponent_handoff(
                        decisions, None, photo_attached=photo_attached,
                        utterance=utterance,
                    )
                    nominal_handoff["nominal_draft_blockers"] = list(dict.fromkeys(
                        [*nominal_handoff.get("nominal_draft_blockers", []),
                         *compose_blockers]
                    ))[:32]
            else:
                nominal_handoff = _guided_open_cabinet_handoff(
                    decisions, photo_attached=photo_attached,
                )
        else:
            nominal_handoff = _guided_open_cabinet_handoff(
                decisions, photo_attached=photo_attached,
            )
    if (candidate_base is not None and revision_blocker is None
            and len(candidate_base.get("modules", [])) == 1
            and type(candidate_base.get("modules", [{}])[0]) is dict
            and "drawer_layout_reference" in candidate_base["modules"][0]
            and type(candidate_base["modules"][0].get("drawers")) is list):
        metadata = {
            "base_spec": candidate_base,
            "source_utterance": source_utterance,
            "corrections": correction_history,
        }
        old_metadata = state["decisions"].get("nominal_detail_spec", {}).get("value")
        if metadata != old_metadata:
            state = update_review_state(
                state, updates=[{
                    "field": "nominal_detail_spec", "value": metadata,
                    "status": "proposed", "source": "ENGINE_CALCULATED",
                }], pending_fields=[],
            )["review_state"]
    result: dict[str, Any] = {
        "review_kind": "guided_design_v1",
        "status": "NEEDS_USER_CONFIRMATION" if questions else "REVIEW_ONLY",
        "review_state": state,
        "confirmed": confirmed,
        "proposed": proposed,
        "pending": pending,
        "questions": questions,
        "next_step": (
            "Responder solo las preguntas abiertas; después se revisará una propuesta nominal."
            if questions else
            "La información disponible es de revisión; no hay autorización de fabricación."
        ),
        "ready_for_nominal_review": ready,
        "readiness_blockers": readiness_blockers,
        "warnings": warnings,
        "nominal_review_scope": (
            "F1 carcasa básica; puertas, cajones, divisiones, fondo, patas y uniones "
            "no quedan representados en esta geometría."
            if nominal_review is not None else None
        ),
        "nominal_review": nominal_review,
        "natural_preview": natural_summary,
        "photo_input": (
            {"status": "IMAGE_OBSERVED_UNCONFIRMED", "pixels_received": False}
            if photo is not None else None
        ),
        "piece_count": 0,
        "can_generate_f7c": False,
        **{flag: False for flag in _FLAGS},
        **nominal_handoff,
    }
    return result


def prepare_wall_bar_nominal_review(
    utterance: str, clarifications: list[str] | None = None,
) -> dict[str, Any]:
    """Prepare the protected wall-bar request for a non-approved visual draft.

    It binds the owner's explicit LIVE01 measurements to the existing fixture,
    but creates neither geometry nor an approval/flow-review record. The caller
    may submit only the returned request to Maestro for a draft pending visual
    owner review; the previous choices remain reported, not authenticated.
    """
    preview = preview_conversation(utterance, clarifications)
    review = preview.get("wall_bar_review")
    expected_owner = {
        "overall_width_mm": 900,
        "overall_depth_mm": 460,
        "overall_height_mm": 900,
        "free_span_horizontal_mm": 600,
        "cabinet_width_mm": 300,
        "feet_height_mm": 40,
        "drawer_count": 3,
        "large_drawer_position": "bottom",
    }
    if (type(review) is not dict or review.get("owner_values") != expected_owner
            or type(review.get("horizontal_allocation")) is not dict
            or review["horizontal_allocation"].get("matches") is not True
            or review.get("unit_requires_confirmation")
            or any(item.get("matches") is not True
                   for item in review.get("reference_comparison", {}).values())):
        raise MaestroError(
            "La solicitud de barra no coincide con las medidas explícitas verificadas; "
            "no se prepara una revisión nominal."
        )

    fixture, _, fixture_sha = _load_wall_bar_fixture()
    spec = fixture["module_spec"]
    cabinet = spec.get("cabinet_module")
    drawers = cabinet.get("drawers") if type(cabinet) is dict else None
    if (spec.get("design_choices", {}).get("aesthetic_presentation")
            != _WALL_BAR_PRIOR_DECISIONS["aesthetic_presentation"]
            or type(drawers) is not list or len(drawers) != 3
            or any(item.get("front_construction") != "separate"
                   or item.get("facade", {}).get("style") != "overlay"
                   for item in drawers)
            or any(item.get("facade", {}).get("opening_system") != "handle"
                   for item in drawers)):
        raise MaestroError(
            "El fixture no conserva las opciones visuales históricas para revisión."
        )

    prior_visual_choices = {
        "aesthetic_presentation": {
            "value": "bicolor_modern_preliminary",
            "source": _PRIOR_REPORTED,
            "meaning": "cubierta roble claro; lateral/frentes blanco mate; veta ilustrativa a lo largo de 900 mm",
        },
        "opening_system": {
            "value": "handle",
            "source": _PRIOR_REPORTED,
            "meaning": "tirador recto negro simbólico; sin modelo, posición ni taladro aprobados",
        },
    }
    return {
        "status": "DRAFT_PENDING_OWNER_VISUAL",
        "request": fixture,
        "request_sha256": _digest(fixture),
        "source_provenance": {
            "owner_measurements": "CARPN_LIVE01_TRANSCRIPT_AND_CLARIFICATION",
            "prior_design_choices": _PRIOR_REPORTED,
            "current_owner_directives": _OWNER_DIRECTIVE,
            "visual_choices": prior_visual_choices,
            "technical_fixture_values": "TEST_FIXTURE_NOT_USER_CHOICE",
            "fixture": (
                "examples/wall-bar-900-review.json#sha256=" + fixture_sha
            ),
            "standard_claim_unverified": review.get("standard_claim_unverified") is True,
        },
        "owner_visual_acceptance": "PENDING",
        "authorization": "NOT_FABRICATION_APPROVAL",
        **{flag: False for flag in _FLAGS},
    }


def _compact_summary(request: dict[str, Any], answer: dict[str, Any],
                     openings: list[dict[str, Any]]) -> str:
    """Summarize decisions and geometry without dumping the full request."""
    spec = request["module_spec"]
    model = answer["modular"]
    dimensions = model.get("dimensions_mm", {})
    lines = [
        "CARPINOVA · RESUMEN COMPLETO DE REVISIÓN NOMINAL",
        "No autoriza fabricación, corte, perforación ni compra.",
        ("Carcasa CAD exterior: ancho {width} mm · alto {height} mm · "
         "profundidad {depth} mm.".format(
             width=dimensions.get("width", "no calculado"),
             height=dimensions.get("height", "no calculado"),
             depth=dimensions.get("depth", "no calculado"))),
    ]
    depth = model.get("depth_review")
    if type(depth) is dict and depth.get("assembled_external_depth_mm") is not None:
        assembled = depth["assembled_external_depth_mm"]
        carcass = depth.get("carcass_depth_mm")
        if assembled != carcass:
            lines.append(
                f"Profundidad exterior ensamblada propuesta: {assembled} mm "
                f"(carcasa {carcass} mm; extensión nominal de frentes incluida)."
            )

    if spec.get("type") == "wall_bar":
        bar = model.get("wall_bar_review", {})
        cabinet_spec = spec["cabinet_module"]
        cabinet = model["modules"][0]
        lines.extend([
            ("Barra: muro a la izquierda y cajonera a la derecha; "
             "sin panel de madera adicional en el extremo del muro."),
            (f"Luz horizontal: {spec['free_span_mm']} mm; cajonera nominal: "
             f"{cabinet_spec['width_mm']} × {cabinet['external_height_mm']} × "
             f"{cabinet['external_depth_mm']} mm."),
            (f"Cajonera: {cabinet_spec['material_id']}, "
             f"{cabinet_spec['panel_thickness_mm']} mm, laterales continuos; "
             "caja completa y tres fachadas sobrepuestas separadas."),
            "Patas conceptuales: 40 mm dentro de la altura total de 900 mm; no son piezas CAD.",
        ])
        entries = " · ".join(
            f"{row['public_ref']}↔{row['drawer_id']} {row['opening_height_mm']} mm"
            for row in openings
        )
        lines.append(f"Aberturas nominales arriba→abajo: {entries}.")
        lines.append(
            "Rieles, holgura lateral de 13 mm, retranqueo de 45 mm, "
            "alturas de caja y cantos provienen del fixture: provisionales para revisión."
        )
        aesthetic = spec.get("design_choices", {}).get("aesthetic_presentation")
        handles = [drawer.get("facade", {}).get("opening_system")
                   for drawer in cabinet_spec.get("drawers", [])]
        if (aesthetic == "bicolor_modern_preliminary"
                and handles and all(item == "handle" for item in handles)):
            lines.append(
                "Elección visual previa reportada: cubierta roble claro, "
                "lateral/frentes blanco mate y tirador recto negro simbólico; "
                "sin acabado comercial, ubicación, modelo ni taladros confirmados."
            )
        else:
            lines.append("Opciones visuales pendientes de representar.")
        lines.append(
            "Decisiones previas de orientación/construcción: reportadas, no autenticadas "
            "como aprobación nueva. Aceptación visual del propietario: pendiente."
        )

    model_modules = {item.get("module_id"): item for item in model.get("modules", [])}
    openings_by_module: dict[str, list[dict[str, Any]]] = {}
    for row in openings:
        openings_by_module.setdefault(row["module_id"], []).append(row)
    for index, module_spec in enumerate(spec.get("modules", []), 1):
        module_id = module_spec.get("module_id", f"M{index}")
        module = model_modules.get(module_id, {})
        dims = (module.get("external_width_mm"), module.get("external_height_mm"),
                module.get("external_depth_mm"))
        size = " × ".join(str(value) if value is not None else "?" for value in dims)
        thickness = module_spec.get("panel_thickness_mm")
        material = module_spec.get("material_id", "pendiente")
        construction = {
            "sides_full": "laterales continuos",
            "top_bottom_full": "tapas continuas",
        }.get(module_spec.get("construction"), module_spec.get("construction", "pendiente"))
        lines.append(
            f"Módulo {index} ({module_id}): {size} mm · {construction} · "
            f"{material}, {thickness if thickness is not None else 'espesor pendiente'} mm."
        )
        clear_width = module.get("clear_width_mm")
        clear_height = module.get("clear_height_mm")
        if clear_width is not None and clear_height is not None:
            lines.append(f"  Interior nominal: {clear_width} × {clear_height} mm (ancho × alto).")

        front = module_spec.get("fronts")
        drawer_specs = module_spec.get("drawers", [])
        facade_styles = sorted({
            drawer.get("facade", {}).get("style")
            for drawer in drawer_specs
            if type(drawer) is dict and type(drawer.get("facade")) is dict
            and drawer["facade"].get("style")
        })
        if facade_styles:
            style = ", ".join({"inset": "embutido", "overlay": "sobrepuesto"}.get(v, v)
                               for v in facade_styles)
            lines.append(f"  Frentes de cajón: {style}.")
        elif type(front) is dict:
            style = {"inset": "embutido", "overlay": "sobrepuesto"}.get(
                front.get("style"), front.get("style", "pendiente"))
            lines.append(f"  Frentes de módulo: {style}.")

        support = module.get("support_review")
        if type(support) is dict:
            support_style = support.get("style", "apoyo")
            noun = "patas" if support_style == "legs" else "apoyo"
            lines.append(
                f"  {noun.capitalize()} solo conceptual: "
                f"{support.get('support_height_mm', 'sin altura')} mm; "
                f"carcasa CAD {support.get('carcass_height_mm', dims[1])} mm; "
                f"alto total propuesto {support.get('overall_height_mm', 'no calculado')} mm; "
                f"{noun} no modeladas."
            )
        module_openings = openings_by_module.get(module_id, [])
        if module_openings:
            entries = " · ".join(
                f"{row['public_ref']} ↔ {row['drawer_id']}: "
                f"{row['opening_height_mm']} mm, base {row['opening_bottom_offset_mm']} mm"
                for row in module_openings
            )
            lines.append(f"  Aberturas nominales A-D (arriba→abajo): {entries}.")

    lines.extend([
        "Origen: solicitud estructurada; declaración del cliente no autenticada.",
        "Pendiente de verificar: herrajes/holguras, cantos/veta, uniones, estabilidad y montaje.",
        "No se calcularon medidas finales de corte ni mecanizados.",
        f"Piezas nominales: {len(model.get('parts', []))}; revisión, no autorización.",
        "fabrication_ready=false; cutting_ready=false; drilling_ready=false; purchase_ready=false.",
    ])
    return "\n".join(lines)


def bind_reviewed_layout(request: dict[str, Any], proposal_spec: dict[str, Any], *,
                         summary_shown: bool, layout_approved: bool) -> dict[str, Any]:
    """Bind an approved F1 opening proposal to one matching F6 drawer module.

    Only opening IDs/heights/offsets and drawer_layout_reference are copied;
    this staging helper executes no F6/F7C geometry. The caller must provide
    every physical drawer, construction, facade and hardware field.
    """
    if (type(summary_shown) is not bool or summary_shown is not True
            or type(layout_approved) is not bool or layout_approved is not True):
        raise MaestroError("Mostrar el resumen F1 y declarar aprobación antes de enlazar F6.")
    if type(request) is not dict or request.get("action") != "modular":
        raise MaestroError("El vínculo F1→F6 requiere una solicitud modular explícita.")
    plan = propose_drawer_layout(proposal_spec)
    root = request.get("module_spec")
    modules = root.get("modules") if type(root) is dict else None
    if type(modules) is not list:
        raise MaestroError("La solicitud F6 no incluye módulos explícitos.")
    dims = plan["external_dimensions_mm"]
    matching = [module for module in modules if type(module) is dict and
                type(module.get("drawers")) is list and
                module.get("width_mm") == dims["width"] and
                root.get("height_mm") == dims["height"] and
                root.get("depth_mm") == dims["depth"] and
                module.get("panel_thickness_mm") == plan["panel_thickness_mm"] and
                module.get("construction") == plan["construction"] and
                len(module["drawers"]) == len(plan["opening_plan"])]
    if len(matching) != 1:
        raise MaestroError("La distribución F1 no identifica un único módulo F6 con la misma carcasa.")
    updated = copy.deepcopy(request)
    target = next(m for m in updated["module_spec"]["modules"]
                  if m.get("module_id") == matching[0].get("module_id"))
    for drawer, opening in zip(target["drawers"], plan["opening_plan"]):
        if type(drawer) is not dict or drawer.get("drawer_id") != opening["drawer_id"]:
            raise MaestroError("Los IDs de cajón F6 contradicen el orden D1-Dn de F1.")
        drawer["opening_bottom_offset_mm"] = opening["opening_bottom_offset_mm"]
        drawer["opening_height_mm"] = opening["opening_height_mm"]
    target["drawer_layout_reference"] = copy.deepcopy(proposal_spec)
    return updated


def _derive(request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    if type(request) is not dict or request.get("action") != "modular":
        raise MaestroError("La traza requiere una solicitud modular explícita de Maestro.")
    answer = consult_maestro(request)
    model = answer.get("modular")
    if (answer.get("status") != "DRAFT_NOT_FOR_CUTTING"
            or type(model) is not dict
            or any(answer.get(flag) is not False or model.get(flag) is not False for flag in _FLAGS)):
        raise MaestroError("Maestro no produjo un borrador modular con los cuatro bloqueos.")
    exchange = cad_exchange(model)
    module_specs = request.get("module_spec", {}).get("modules", [])
    model_modules = {m.get("module_id"): m for m in model.get("modules", [])}
    openings: list[dict[str, Any]] = []
    if request["module_spec"].get("type") == "wall_bar":
        cabinet = request["module_spec"].get("cabinet_module")
        drawers = cabinet.get("drawers") if type(cabinet) is dict else None
        if type(drawers) is not list or len(drawers) != 3:
            raise MaestroError("La traza de barra exige tres cajones nominales explícitos.")
        for index, drawer in enumerate(sorted(
                drawers, key=lambda item: item["opening_bottom_offset_mm"], reverse=True)):
            openings.append({
                "module_id": cabinet["module_id"],
                "public_ref": chr(ord("A") + index),
                "drawer_id": drawer["drawer_id"],
                "opening_height_mm": drawer["opening_height_mm"],
                "opening_bottom_offset_mm": drawer["opening_bottom_offset_mm"],
                "source_engine": "WALL_BAR_F1_F7C_NOMINAL",
            })
    if type(module_specs) is not list:
        raise MaestroError("Faltan módulos explícitos para validar la traza.")
    for module_spec in module_specs:
        if type(module_spec) is not dict or "drawers" not in module_spec:
            continue
        reference = module_spec.get("drawer_layout_reference")
        if type(reference) is not dict:
            raise MaestroError("F7C requiere drawer_layout_reference derivado de F1.")
        proposal = propose_drawer_layout(reference)
        actual_module = model_modules.get(module_spec.get("module_id"))
        if actual_module is None or actual_module.get("drawer_ids") != [
            row["drawer_id"] for row in proposal["opening_plan"]
        ]:
            raise MaestroError("IDs/orden F6 no coinciden con la distribución F1.")
        for index, row in enumerate(reversed(proposal["opening_plan"])):
            openings.append({
                "module_id": module_spec["module_id"],
                "public_ref": chr(ord("A") + index),
                "drawer_id": row["drawer_id"],
                "opening_height_mm": row["opening_height_mm"],
                "opening_bottom_offset_mm": row["opening_bottom_offset_mm"],
                "source_engine": "F1_CORE_CABINET",
            })
    summary = _compact_summary(request, answer, openings)
    if len(summary) > 24000:
        raise MaestroError("El resumen completo excede el límite de revisión.")
    return answer, exchange, openings, summary


def _load_wall_bar_p5_fixture() -> tuple[dict[str, Any], str]:
    try:
        payload = _WALL_BAR_P5_FIXTURE_PATH.read_bytes()
        fixture = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise MaestroError("Fixture P5 de barra ausente o inválido.") from exc
    # Windows Git checkouts may convert the JSON fixture from LF to CRLF.
    # Hash its canonical line endings so the pinned fixture identity survives
    # checkout conversion without accepting other content changes.
    digest = hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()
    if (digest != _WALL_BAR_P5_FIXTURE_SHA256
            or type(fixture) is not dict
            or set(fixture) != {"action", "module_spec"}
            or fixture.get("action") != "modular"
            or type(fixture.get("module_spec")) is not dict
            or fixture["module_spec"].get("type") != "wall_bar"):
        raise MaestroError("Fixture P5 protegido distinto del SHA esperado.")
    return fixture, digest


def _wall_bar_p5_owner_check(
    text: str, fixture: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed = _wall_bar_owner_requirements(text)
    if parsed is None:
        raise MaestroError("Se requiere el texto original explícito de barra y cajonera.")
    evidence = parsed["evidence"]
    spec = fixture["module_spec"]
    cabinet = spec["cabinet_module"]
    drawers = sorted(
        cabinet["drawers"], key=lambda row: row["opening_bottom_offset_mm"],
        reverse=True,
    )
    if [row.get("drawer_id") for row in drawers] != ["D1", "D2", "D3"]:
        raise MaestroError("El orden D1/D2/D3 de P5 no coincide con A/B/C.")
    if (evidence.get("ambiguous_fields")
            or evidence.get("unit_requires_confirmation")):
        raise MaestroError("La descripción contiene medidas ambiguas o unidades pendientes.")
    owner = parsed["owner_values"]
    reference = {
        "overall_width_mm": spec["overall_width_mm"],
        "overall_depth_mm": spec["overall_depth_mm"],
        "overall_height_mm": spec["overall_height_mm"],
        "free_span_horizontal_mm": spec["free_span_mm"],
        "cabinet_width_mm": cabinet["width_mm"],
        "feet_height_mm": spec["feet_height_mm"],
        "drawer_count": len(drawers),
        "large_drawer_position": "bottom" if drawers[-1]["drawer_id"] == "D3" else None,
    }
    comparison = {
        key: {"owner_value": owner.get(key), "p5_value": value,
              "matches": owner.get(key) == value}
        for key, value in reference.items()
    }
    arithmetic_matches = (
        owner.get("overall_width_mm") is not None
        and owner.get("free_span_horizontal_mm") is not None
        and owner.get("cabinet_width_mm") is not None
        and owner["overall_width_mm"] - owner["free_span_horizontal_mm"]
        == owner["cabinet_width_mm"]
    )
    if (not all(row["matches"] for row in comparison.values())
            or not arithmetic_matches
            or drawers[-1]["opening_height_mm"]
            <= max(row["opening_height_mm"] for row in drawers[:-1])):
        raise MaestroError("El texto del propietario no coincide con las medidas P5.")
    return parsed, comparison


def prepare_wall_bar_p5_nominal_review(
    utterance: str, corrections: list[str] | None = None,
) -> dict[str, Any]:
    """Replay non-approved A/B/C revisions from the immutable P5 fixture."""
    if (type(utterance) is not str or not utterance.strip()
            or len(utterance) > _MAX_TEXT):
        raise MaestroError("La descripción original debe tener 1–2000 caracteres.")
    if corrections is None:
        corrections = []
    if (type(corrections) is not list or len(corrections) > 12
            or any(type(item) is not str for item in corrections)):
        raise MaestroError("La revisión admite hasta 12 correcciones de texto explícitas.")

    fixture, fixture_sha = _load_wall_bar_p5_fixture()
    parsed, owner_comparison = _wall_bar_p5_owner_check(utterance, fixture)
    request = copy.deepcopy(fixture)
    source_request = copy.deepcopy(fixture)
    source_spec = source_request["module_spec"]
    spec = request["module_spec"]
    source_drawers = sorted(
        source_spec["cabinet_module"]["drawers"],
        key=lambda row: row["opening_bottom_offset_mm"], reverse=True,
    )
    drawers = sorted(
        spec["cabinet_module"]["drawers"],
        key=lambda row: row["opening_bottom_offset_mm"], reverse=True,
    )
    if len(drawers) != 3 or len({row["drawer_id"] for row in drawers}) != 3:
        raise MaestroError("P5 debe conservar tres IDs de cajón únicos.")

    heights = [row["opening_height_mm"] for row in source_drawers]
    offsets = [row["opening_bottom_offset_mm"] for row in source_drawers]
    cabinet_height = (spec["overall_height_mm"] - spec["feet_height_mm"]
                      - spec["top_thickness_mm"])
    top_margin = cabinet_height - (offsets[0] + heights[0])
    bottom_margin = offsets[-1]
    inter_opening_gaps = [
        offsets[index] - (offsets[index + 1] + heights[index + 1])
        for index in range(2)
    ]
    if (top_margin < 0 or bottom_margin < 0
            or any(gap < 0 for gap in inter_opening_gaps)):
        raise MaestroError("La distribución base P5 no conserva márgenes y separaciones válidos.")

    from .natural_intake import _MIN_ILLUSTRATIVE_OPENING_MM
    fixed: set[int] = set()
    correction_history: list[dict[str, Any]] = []
    for instruction in corrections:
        ref, delta = _parse_drawer_correction(instruction, len(drawers))
        position = ord(ref) - ord("A")
        before = list(heights)
        requested = before[position] + delta
        fixed_others = fixed - {position}
        free = [index for index in range(3)
                if index != position and index not in fixed_others]
        remaining = (sum(before) - requested
                     - sum(before[index] for index in fixed_others))
        if requested < _MIN_ILLUSTRATIVE_OPENING_MM:
            raise MaestroError("La corrección deja el cajón solicitado por debajo de 60 mm.")
        if not free and remaining != 0:
            raise MaestroError("No quedan cajones libres para redistribuir la altura solicitada.")
        if free and remaining < _MIN_ILLUSTRATIVE_OPENING_MM * len(free):
            raise MaestroError("La corrección no deja altura nominal suficiente para cajones libres.")
        from .core import DesignError
        try:
            redistributed = _apportion_nominal(
                remaining, [before[index] for index in free],
            ) if free else []
        except DesignError as exc:
            raise MaestroError("Redistribución F1 inválida: " + str(exc)) from exc
        after = list(before)
        after[position] = requested
        for index, value in zip(free, redistributed):
            after[index] = value
        if min(after) < _MIN_ILLUSTRATIVE_OPENING_MM:
            raise MaestroError("La corrección deja una abertura menor que el mínimo visual F1 de 60 mm.")
        changed = []
        for index, (old, new) in enumerate(zip(before, after)):
            if old == new:
                continue
            changed.append({
                "ref": chr(ord("A") + index),
                "drawer_id": drawers[index]["drawer_id"],
                "before_mm": old,
                "after_mm": new,
                "delta_mm": new - old,
                "cause": ("INPUT_REQUESTED_NOT_APPROVED" if index == position
                          else "AUTO_REDISTRIBUTED_TO_KEEP_TOTAL"),
            })
        correction_history.append({
            "instruction": instruction,
            "ref": ref,
            "delta_mm": delta,
            "source": "INPUT_DECLARED_NOT_AUTHENTICATED",
            "changes": changed,
        })
        heights = after
        fixed.add(position)

    new_offsets = [0, 0, 0]
    cursor = bottom_margin
    for index in range(2, -1, -1):
        new_offsets[index] = cursor
        if index > 0:
            cursor += heights[index] + inter_opening_gaps[index - 1]
    if cabinet_height - (new_offsets[0] + heights[0]) != top_margin:
        raise MaestroError("El replay alteró el margen superior de P5.")

    allowed_drawer_fields = {
        "opening_height_mm", "opening_bottom_offset_mm", "box_height_mm",
    }
    for index, (source_drawer, drawer) in enumerate(zip(source_drawers, drawers)):
        box_clearance = (source_drawer["opening_height_mm"]
                         - source_drawer["box_height_mm"])
        box_height = heights[index] - box_clearance
        if box_height <= 0:
            raise MaestroError("La corrección deja una caja nominal sin altura positiva.")
        drawer["opening_height_mm"] = heights[index]
        drawer["opening_bottom_offset_mm"] = new_offsets[index]
        drawer["box_height_mm"] = box_height
        static_keys_before = source_drawer.keys() - allowed_drawer_fields
        static_keys_after = drawer.keys() - allowed_drawer_fields
        if (static_keys_before != static_keys_after
                or any(source_drawer[key] != drawer[key]
                       for key in static_keys_before)):
            raise MaestroError("La revisión alteró un campo inmutable del cajón P5.")

    source_static = copy.deepcopy(source_spec)
    revised_static = copy.deepcopy(spec)
    source_static["cabinet_module"].pop("drawers")
    revised_static["cabinet_module"].pop("drawers")
    if source_static != revised_static:
        raise MaestroError("La revisión alteró dimensiones, acabados o decisiones de P5.")

    base_answer, base_exchange, _, _ = _derive(source_request)
    answer, exchange, openings, _ = _derive(request)
    if (len(exchange["boxes"]) != 28
            or len({box["piece_id"] for box in exchange["boxes"]}) != 28
            or sorted(box["piece_id"] for box in exchange["boxes"])
            != sorted(box["piece_id"] for box in base_exchange["boxes"])):
        raise MaestroError("Maestro/CAD alteró las 28 identidades de elemento de P5.")
    if (answer["modular"].get("dimensions_mm")
            != base_answer["modular"].get("dimensions_mm")):
        raise MaestroError("La revisión alteró la envolvente exterior de P5.")
    if not corrections and exchange["geometry_sha256"] != _WALL_BAR_P5_GEOMETRY_SHA256:
        raise MaestroError("La geometría base P5 no reproduce su SHA protegido.")

    from .wall_bar_sheets import wall_bar_review_dimensions
    human_dimensions = wall_bar_review_dimensions(answer["modular"])
    front_gaps = {
        **human_dimensions["front_perimeter_reveals_mm"],
        **human_dimensions["front_gaps_mm"],
    }
    if len(front_gaps) != 6 or set(front_gaps.values()) != {4}:
        raise MaestroError("Maestro no conserva las seis luces nominales de fachada de 4 mm.")

    opening_rows = []
    drawer_by_id = {row["drawer_id"]: row for row in drawers}
    for row in openings:
        drawer = drawer_by_id[row["drawer_id"]]
        opening_rows.append({
            **row,
            "box_height_mm": drawer["box_height_mm"],
        })
    replay_sha = _digest({
        "fixture_sha256": fixture_sha,
        "utterance": utterance,
        "corrections": corrections,
    })
    request_sha = _digest(request)
    return {
        "schema_version": _SCHEMA,
        "mode": "F7D_WALL_BAR_P5_NOMINAL_REVIEW",
        "status": "NEEDS_USER_CONFIRMATION",
        "utterance": utterance,
        "corrections": list(corrections),
        "correction_history": correction_history,
        "source_fixture": "examples/wall-bar-900-review-p5.json",
        "source_fixture_sha256": fixture_sha,
        "source_request": source_request,
        "request": request,
        "request_sha256": request_sha,
        "replay_sha256": replay_sha,
        "owner_measurement_comparison": owner_comparison,
        "standard_claim_unverified": parsed["standard_claim_unverified"],
        "rails_requested": parsed["rails_requested"],
        "rails_exact_reference_verified": False,
        "openings_top_to_bottom": opening_rows,
        "envelope_mm": {
            "overall_width_mm": spec["overall_width_mm"],
            "overall_depth_mm": spec["overall_depth_mm"],
            "overall_height_mm": spec["overall_height_mm"],
            "free_span_mm": spec["free_span_mm"],
            "cabinet_width_mm": spec["cabinet_module"]["width_mm"],
            "feet_height_mm": spec["feet_height_mm"],
        },
        "front_gaps_nominal_mm": front_gaps,
        "geometry_sha256": exchange["geometry_sha256"],
        "cad_element_count": len(exchange["boxes"]),
        "cad_piece_ids": sorted(box["piece_id"] for box in exchange["boxes"]),
        "source_provenance": {
            "owner_measurements": "INPUT_TEXT_NOT_AUTHENTICATED",
            "prior_design_choices": _PRIOR_REPORTED,
            "technical_fixture_values": "P5_FIXTURE_NOT_OWNER_CHOICE",
            "corrections": "DECLARED_TEXT_REPLAY_NOT_AUTHENTICATED",
        },
        "owner_visual_acceptance": "PENDING",
        "authorization": "NOT_FABRICATION_APPROVAL",
        "piece_count": 0,
        "can_generate_f7c": False,
        "layout_approved": False,
        "construction_approved": False,
        **{flag: False for flag in _FLAGS},
    }


def validate_wall_bar_p5_nominal_review(review: dict[str, Any]) -> bool:
    """Rebuild a client-held preview from P5 and reject edited derived state."""
    if (type(review) is not dict or type(review.get("utterance")) is not str
            or type(review.get("corrections")) is not list):
        raise MaestroError("Vista previa/historial P5 inválidos.")
    expected = prepare_wall_bar_p5_nominal_review(
        review["utterance"], review["corrections"],
    )
    if _canonical(review) != _canonical(expected):
        raise MaestroError("Vista previa o historial P5 editado; replay rechazado.")
    return True


def revise_wall_bar_p5_nominal_review(
    previous_review: dict[str, Any], correction: str,
) -> dict[str, Any]:
    """Validate, then replay all declarations from the immutable P5 source."""
    validate_wall_bar_p5_nominal_review(previous_review)
    corrections = [*previous_review["corrections"], correction]
    return prepare_wall_bar_p5_nominal_review(
        previous_review["utterance"], corrections,
    )


def _geometry_engine(request: dict[str, Any], openings: list[dict[str, Any]]) -> str:
    if request["module_spec"].get("type") == "wall_bar":
        return "WALL_BAR_F1_F7C"
    return "F1_CORE_F6_F7C" if openings else "F1_CORE_F6"


def _validate_wall_bar_binding(
    *, utterance: str, history: list[dict[str, str]],
    decisions: list[dict[str, Any]], request: dict[str, Any],
    source_fixture: str | None,
) -> dict[str, Any] | None:
    """Bind the real bar conversation and reported prior choices to its CAD request."""
    spec = request.get("module_spec") if type(request) is dict else None
    if type(spec) is not dict or spec.get("type") != "wall_bar":
        if any(item["source"] in {_PRIOR_REPORTED, _OWNER_DIRECTIVE}
               for item in decisions):
            raise MaestroError(
                "Decisiones de barra o directivas específicas no se pueden aplicar a otro mueble."
            )
        return None

    fixture_rel = "examples/wall-bar-900-review.json"
    fixture_path = Path(__file__).resolve().parents[1] / fixture_rel
    try:
        fixture_bytes = fixture_path.read_bytes()
        fixture = json.loads(fixture_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaestroError("Fixture histórico de barra ausente o inválido.") from exc
    fixture_sha = hashlib.sha256(_canonical(fixture)).hexdigest()
    expected_fixture_ref = f"{fixture_rel}#sha256={fixture_sha}"
    if (fixture_sha != _WALL_BAR_FIXTURE_SHA256
            or source_fixture != expected_fixture_ref):
        raise MaestroError("La traza no identifica el fixture de barra protegido por su SHA.")

    # The fixture supplies provisional technical dimensions only. Unselected
    # handle/aesthetic values are cleared before deriving the nominal review.
    expected_request = copy.deepcopy(fixture)
    if request != expected_request:
        raise MaestroError("Solicitud de barra distinta del fixture protegido y las decisiones declaradas.")

    source_text = "\n".join(
        [utterance, *(row["content"] for row in history if row["role"] == "user")]
    )
    review = _wall_bar_reference_review(source_text)
    if review is None:
        raise MaestroError("La frase y aclaraciones no identifican la solicitud real de barra.")
    owner = review["owner_values"]
    cabinet = spec["cabinet_module"]
    expected_owner = {
        "overall_width_mm": spec["overall_width_mm"],
        "overall_depth_mm": spec["overall_depth_mm"],
        "overall_height_mm": spec["overall_height_mm"],
        "free_span_horizontal_mm": spec["free_span_mm"],
        "cabinet_width_mm": cabinet["width_mm"],
        "feet_height_mm": spec["feet_height_mm"],
        "drawer_count": len(cabinet["drawers"]),
        "large_drawer_position": "bottom",
    }
    if owner != expected_owner or review["horizontal_allocation"]["matches"] is not True:
        raise MaestroError("Las medidas del Maestro no cierran con la frase y aclaración del propietario.")

    actual_order = "=".join(
        drawer["drawer_id"] for drawer in sorted(
            cabinet["drawers"], key=lambda item: item["opening_bottom_offset_mm"], reverse=True
        )
    )
    if (actual_order != "D1=D2=D3"
            or cabinet["drawers"][-1]["drawer_id"] != "D3"
            or cabinet["drawers"][-1]["opening_height_mm"] <= max(
                item["opening_height_mm"] for item in cabinet["drawers"][:-1]
            )):
        raise MaestroError("D1-D3 no conservan dos cajones superiores y la gaveta grande inferior.")

    expected_decisions = {
        **{topic: (value, "USER_CONFIRMED") for topic, value in {
            "overall_width_mm": 900, "overall_depth_mm": 460,
            "overall_height_mm": 900, "free_span_horizontal_mm": 600,
            "cabinet_width_mm": 300, "feet_height_mm": 40,
            "drawer_count": 3, "large_drawer_position": "bottom",
        }.items()},
        **{topic: (value, _PRIOR_REPORTED)
           for topic, value in _WALL_BAR_PRIOR_DECISIONS.items()
           if topic != "front_construction"},
        "front_construction": (_WALL_BAR_PRIOR_DECISIONS["front_construction"],
                               _OWNER_DIRECTIVE),
        **{topic: (value, "TEST_FIXTURE_NOT_USER_CHOICE") for topic, value in {
            "fixture_sha256": fixture_sha,
            "slide_clearance_each_side_mm": 13,
            "drawer_rear_setback_mm": 45,
            "drawer_box_heights_mm": "D1=120;D2=120;D3=390",
            "drawer_opening_heights_mm": "D1=150;D2=150;D3=447",
            "facade_edgeband_mm": 2,
        }.items()},
    }
    observed = {item["topic"]: item for item in decisions}
    if len(observed) != len(decisions) or set(observed) != set(expected_decisions):
        raise MaestroError("La traza de barra requiere decisiones explícitas y procedencia completa.")
    for topic, (value, source) in expected_decisions.items():
        if observed[topic] != {"topic": topic, "value": value, "source": source}:
            raise MaestroError(f"Procedencia o valor de decisión no coincide: {topic}.")

    return {
        "fixture_sha256": fixture_sha,
        "owner_measurement_source": "CARPN_LIVE01_TRANSCRIPT_AND_CLARIFICATION",
        "prior_decision_source": _PRIOR_REPORTED,
        "technical_fixture_values_are_provisional": True,
    }


def _validated_history(history: Any) -> list[dict[str, str]]:
    if type(history) is not list or not 2 <= len(history) <= _MAX_HISTORY:
        raise MaestroError("La traza necesita entre 2 y 100 turnos de conversación.")
    result = []
    for item in history:
        if (type(item) is not dict or set(item) != {"role", "content"}
                or item.get("role") not in ("user", "assistant")
                or type(item.get("content")) is not str
                or not item["content"].strip() or len(item["content"]) > _MAX_TEXT):
            raise MaestroError("Turno de conversación inválido o excesivo.")
        result.append({"role": item["role"], "content": item["content"]})
    if result[-1]["role"] != "user" or result[-2]["role"] != "assistant":
        raise MaestroError("La última respuesta debe seguir a un resumen y confirmación declarados.")
    return result


def _validated_decisions(decisions: Any) -> list[dict[str, Any]]:
    if type(decisions) is not list or len(decisions) > _MAX_DECISIONS:
        raise MaestroError("Decisiones de conversación inválidas o excesivas.")
    result = []
    for item in decisions:
        if (type(item) is not dict or set(item) != {"topic", "value", "source"}
                or type(item["topic"]) is not str or not item["topic"].strip()
                or len(item["topic"]) > 100 or type(item["source"]) is not str
                or item["source"] not in (
                    "USER_CONFIRMED", "TEST_FIXTURE_NOT_USER_CHOICE",
                    _PRIOR_REPORTED, _OWNER_DIRECTIVE,
                )
                or isinstance(item["value"], (dict, list))):
            raise MaestroError("Decisión declarada con forma/fuente no permitida.")
        result.append(copy.deepcopy(item))
    return result


def build_flow_review(*, utterance: str, history: list[dict[str, str]],
                      decisions: list[dict[str, Any]], request: dict[str, Any],
                      summary_shown: bool, layout_approved: bool,
                      construction_approved: bool,
                      source_fixture: str | None = None) -> dict[str, Any]:
    """Build a bounded, explicitly unauthenticated, Maestro-bound review trace."""
    if type(utterance) is not str or not utterance.strip() or len(utterance) > _MAX_TEXT:
        raise MaestroError("La descripción original debe tener de 1 a 2000 caracteres.")
    if any(type(value) is not bool or value is not True for value in
           (summary_shown, layout_approved, construction_approved)):
        raise MaestroError("Se requiere resumen mostrado y aprobaciones declarativas para registrar la revisión.")
    if source_fixture is not None and (type(source_fixture) is not str or not source_fixture.strip()
                                       or len(source_fixture) > 120):
        raise MaestroError("La referencia de fixture es inválida.")
    clean_history = _validated_history(history)
    clean_decisions = _validated_decisions(decisions)
    wall_bar_binding = _validate_wall_bar_binding(
        utterance=utterance, history=clean_history, decisions=clean_decisions,
        request=request, source_fixture=source_fixture,
    )
    answer, exchange, openings, summary = _derive(request)
    record: dict[str, Any] = {
        "schema_version": _SCHEMA,
        "source": "CARPINOVA_CONVERSATION_FLOW_V1",
        "utterance": utterance,
        "history": clean_history,
        "decisions": clean_decisions,
        "source_fixture": source_fixture,
        "source_request": copy.deepcopy(request),
        "confirmation": {
            "summary_shown": True,
            "layout_approved": True,
            "construction_approved": True,
            "basis": "CLIENT_DECLARED_NOT_AUTHENTICATED",
        },
        "confirmation_summary": summary,
        "openings_top_to_bottom": openings,
        "geometry_sha256": exchange["geometry_sha256"],
        "piece_count": len(exchange["boxes"]),
        "source_provenance": {
            "maestro_action": answer["action"],
            "geometry_engine": _geometry_engine(request, openings),
            "geometry_sha256": exchange["geometry_sha256"],
            "fixture": source_fixture,
            **(wall_bar_binding or {}),
        },
        "authorization": "NOT_FABRICATION_APPROVAL",
        **{flag: False for flag in _FLAGS},
    }
    record["record_sha256"] = _digest(record)
    validate_flow_review(record, request)
    return record


def build_flow_review_from_envelope(envelope: dict[str, Any],
                                    request: dict[str, Any]) -> dict[str, Any]:
    """Create a persisted trace from MCP-friendly client declarations."""
    fields = {"utterance", "history", "decisions", "confirmation", "source_fixture"}
    if type(envelope) is not dict or set(envelope) != fields:
        raise MaestroError("El sobre de flujo requiere utterance, history, decisions, confirmation y source_fixture.")
    confirmation = envelope["confirmation"]
    if type(confirmation) is not dict or set(confirmation) != {
        "summary_shown", "layout_approved", "construction_approved"
    }:
        raise MaestroError("Declaración de confirmación incompleta.")
    return build_flow_review(
        utterance=envelope["utterance"], history=envelope["history"],
        decisions=envelope["decisions"], request=request,
        summary_shown=confirmation["summary_shown"],
        layout_approved=confirmation["layout_approved"],
        construction_approved=confirmation["construction_approved"],
        source_fixture=envelope["source_fixture"],
    )


def validate_flow_review(record: dict[str, Any], request: dict[str, Any]) -> bool:
    """Re-run Maestro and reject trace/source/geometry inconsistencies."""
    if type(record) is not dict or set(record) != _RECORD_FIELDS:
        raise MaestroError("Registro de flujo con campos faltantes o desconocidos.")
    observed_digest = record.get("record_sha256")
    unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
    if type(observed_digest) is not str or _digest(unsigned) != observed_digest:
        raise MaestroError("Integridad local de flow-review.json no válida.")
    if (record.get("schema_version") != _SCHEMA
            or record.get("source") != "CARPINOVA_CONVERSATION_FLOW_V1"
            or record.get("source_request") != request
            or record.get("authorization") != "NOT_FABRICATION_APPROVAL"
            or any(record.get(flag) is not False for flag in _FLAGS)):
        raise MaestroError("Traza no vinculada a la solicitud o con permisos alterados.")
    confirmation = record.get("confirmation")
    if (type(confirmation) is not dict or confirmation != {
        "summary_shown": True, "layout_approved": True,
        "construction_approved": True,
        "basis": "CLIENT_DECLARED_NOT_AUTHENTICATED",
    }):
        raise MaestroError("La confirmación declarada es incompleta o no autenticada.")
    history = _validated_history(record.get("history"))
    decisions = _validated_decisions(record.get("decisions"))
    if (type(record.get("utterance")) is not str
            or not record["utterance"].strip() or len(record["utterance"]) > _MAX_TEXT):
        raise MaestroError("La frase original de la traza es inválida.")
    wall_bar_binding = _validate_wall_bar_binding(
        utterance=record["utterance"], history=history, decisions=decisions,
        request=request, source_fixture=record.get("source_fixture"),
    )
    answer, exchange, openings, summary = _derive(request)
    expected_provenance = {
        "maestro_action": answer["action"],
        "geometry_engine": _geometry_engine(request, openings),
        "geometry_sha256": exchange["geometry_sha256"],
        "fixture": record.get("source_fixture"),
        **(wall_bar_binding or {}),
    }
    if (record.get("confirmation_summary") != summary
            or record.get("openings_top_to_bottom") != openings
            or record.get("geometry_sha256") != exchange["geometry_sha256"]
            or record.get("piece_count") != len(exchange["boxes"])
            or record.get("source_provenance") != expected_provenance
            or record.get("history") != history or record.get("decisions") != decisions):
        raise MaestroError("Traza distinta de la geometría, resumen o historial esperado.")
    return True
