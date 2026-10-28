"""F7D: review untrusted natural-language interpretations before Maestro execution.

No model, NLP parser, CAD executor or MCP session lives here. An external
interpreter may SUGGEST a structured Maestro request; the human must review
it before submitting an independently confirmed JSON to consult_maestro.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .intake import ALIASES, TYPES, _fold

from .maestro import MaestroError, _normalize_request


MAX_UTTERANCE_CHARS = 2000
MAX_CANDIDATE_UTF8_BYTES = 65536


_DIM_LABEL = r"(?:ancho|anchura|alto|altura|fondo|profundidad)"
_DIM_NUMBER = r"\d{1,5}(?:[.,]\d{1,2})?"
_DIM_UNIT = r"(?:mm|cm|mil[ií]metros?|cent[ií]metros?)"
_DIM_FIRST = re.compile(
    rf"(?<!\w)(?P<label>{_DIM_LABEL})\s*"
    rf"(?:exterior(?:es)?|total(?:es)?)?\s*(?:de|es|mide|:|=)?\s*"
    rf"(?P<amount>{_DIM_NUMBER})\s*(?P<unit>{_DIM_UNIT})(?!\w)",
    re.IGNORECASE,
)
_DIM_REVERSE = re.compile(
    rf"(?<![\w.])(?P<amount>{_DIM_NUMBER})\s*(?P<unit>{_DIM_UNIT})"
    rf"\s*(?:de|del|de la)?\s*(?P<label>{_DIM_LABEL})(?!\w)",
    re.IGNORECASE,
)
_MEASURE_FIELDS = {
    "ancho": "width_mm", "anchura": "width_mm",
    "alto": "height_mm", "altura": "height_mm",
    "fondo": "depth_mm", "profundidad": "depth_mm",
}


def extract_explicit_dimensions(utterance: str) -> dict[str, Any]:
    """Conservative offline text evidence; never a production dimension.

    Only individually labelled measures with explicit mm/cm are accepted.
    The human must verify that each label refers to the *whole* furniture.
    """
    if type(utterance) is not str or not utterance.strip() or len(utterance) > MAX_UTTERANCE_CHARS:
        raise MaestroError("Las medidas requieren texto de 1 a 2000 caracteres.")
    hits: dict[str, list[tuple[int, int, str, int]]] = {}
    # A common phrase "ancho 70 cm alto 95 cm" contains an overlapping
    # reverse span ("70 cm alto"). A single literal cannot be two dimensions.
    forward_spans = [m.span() for m in _DIM_FIRST.finditer(utterance)]
    for regex in (_DIM_FIRST, _DIM_REVERSE):
        for match in regex.finditer(utterance):
            if regex is _DIM_REVERSE and any(
                a < match.end() and match.start() < b
                for a, b in forward_spans
            ):
                continue
            field = _MEASURE_FIELDS[_fold(match.group("label"))]
            try:
                qty = Decimal(match.group("amount").replace(",", "."))
                unit = _fold(match.group("unit"))
                multiplier = 10 if unit.startswith(("cm", "centimet")) else 1
                millimetres = qty * multiplier
            except InvalidOperation:
                continue
            if millimetres != millimetres.to_integral_value() or not 1 <= millimetres <= 100000:
                continue
            hits.setdefault(field, []).append(
                (match.start(), match.end(), match.group(0), int(millimetres))
            )
    # A depth quoted for a door/drawer is not automatically cabinet depth.
    subparts = ("cajón", "cajon", "cajones", "gaveta", "gavetas",
                "puerta", "puertas", "repisa", "repisas",
                "estante", "estantes", "entrepaño", "entrepano")
    part_scoped: set[str] = set()
    for field, candidates in hits.items():
        for start, _, _, _ in candidates:
            prefix = _fold(utterance[max(0, start - 50):start])
            if any(re.search(
                    r"(?<!\w)" + re.escape(_fold(noun))
                    + r"(?:\s+\w+){0,2}\s+(?:de|del)\s*$", prefix
                ) for noun in subparts):
                part_scoped.add(field)
    dimensions: dict[str, int] = {}
    evidence: list[dict[str, Any]] = []
    conflicts: list[str] = []
    for field in ("width_mm", "height_mm", "depth_mm"):
        candidates = hits.get(field, [])
        if not candidates:
            continue
        # Alternative readings like "80 cm de ancho o 90 cm" require review.
        alternatives = any(
            re.match(r"\s*(?:o|u)\s+\d", utterance[end:end+15], re.IGNORECASE)
            for _, end, _, _ in candidates
        )
        vals = {val for _, _, _, val in candidates}
        if len(vals) != 1 or alternatives or field in part_scoped:
            conflicts.append(field)
            continue
        start, end, literal, value = sorted(candidates)[0]
        dimensions[field] = value
        evidence.append({"field": field, "literal": literal, "value_mm": value,
                         "start": start, "end": end, "source": "user_literal"})
    return {"dimensions_mm": dimensions, "source_provenance": evidence,
            "ambiguous_fields": conflicts}


def _explicit_project_type(utterance: str) -> str | None:
    """Only one distinct F3 furniture category, never a guessed cabinet type."""
    normalized = _fold(utterance)
    kinds = {
        canonical for alias, canonical in ALIASES.items()
        if not (canonical == "drawer" and _fold(alias) == "cajones")
        if re.search(r"(?<!\w)" + re.escape(_fold(alias)) + r"(?!\w)", normalized)
        for canonical in [TYPES[_fold(alias)]]
    }
    # A drawer mentioned inside a cabinet is a component, not the furniture
    # type. Otherwise "mueble con un cajón" becomes a single drawer project.
    if "drawer" in kinds and re.search(
        r"(?<!\w)(?:cajonera|mueble|gabinete)(?!\w)", normalized
    ):
        kinds.discard("drawer")
    if len(kinds) != 1:
        return None
    # Preserve the original Spanish term supported by F3; no type invention.
    for alias, canonical in ALIASES.items():
        if canonical in kinds and re.search(
                r"(?<!\w)" + re.escape(_fold(alias)) + r"(?!\w)", normalized):
            return alias
    return None


# Presentation-only suggestion. Never extrapolate its thickness/structure
# into manufacturing data or an approved CADExchange.
_ILLUSTRATIVE_PANEL_MM = 15
_ILLUSTRATIVE_STRUCTURE = "sides_full"
_COMPLEXITY_TERMS = (
    "cajon", "cajones", "gaveta", "gavetas", "puerta", "puertas",
    "estante", "estantes", "repisa", "repisas", "entrepaño",
    "cajonera", "modulo", "modulos", "patas", "zocalo",
    "empotrado", "suspendido", "mural", "bisagra", "riel",
    "corredera", "melamina", "mdp", "mdf", "espesor",
    "tablero", "tableros", "dos gabinetes", "varios gabinetes",
)


def _illustrative_open_cabinet_option(
    utterance: str, request: dict[str, Any], conflicts: list[str],
) -> dict[str, Any] | None:
    """One reversible F3 candidate. No geometry run, no inferred hardware."""
    if conflicts or request.get("action") != "project":
        return None
    project = request.get("project")
    if not isinstance(project, dict) or TYPES.get(_fold(project.get("project_type", ""))) != "cabinet":
        return None
    keys = ("width_mm", "height_mm", "depth_mm")
    if set(project) != {*keys, "project_type"} or any(
        type(project[k]) is not int or project[k] <= 2 * _ILLUSTRATIVE_PANEL_MM
        for k in keys
    ):
        return None
    normalized = _fold(utterance)
    if any(re.search(r"(?<!\w)" + re.escape(_fold(term)) + r"(?!\w)", normalized)
           for term in _COMPLEXITY_TERMS):
        return None
    # Keep all literal exterior dimensions. Offer ONE simple carcass to inspect.
    candidate = {
        "action": "project",
        "project": {
            **project,
            "panel_thickness_mm": _ILLUSTRATIVE_PANEL_MM,
            "construction": _ILLUSTRATIVE_STRUCTURE,
        },
    }
    return {
        "status": "OPTIONAL_VISUAL_PRESET_REQUIRES_APPROVAL",
        "description": "Gabinete abierto de cuatro paneles; solo ejemplo visual.",
        "proposed_request": candidate,
        "suggested_fields": {
            "panel_thickness_mm": {
                "value": _ILLUSTRATIVE_PANEL_MM,
                "source": "ASSISTANT_ILLUSTRATIVE_DEFAULT_NOT_USER_SPECIFIED",
            },
            "construction": {
                "value": _ILLUSTRATIVE_STRUCTURE,
                "source": "ASSISTANT_ILLUSTRATIVE_DEFAULT_NOT_USER_SPECIFIED",
            },
        },
        "excludes": [
            "fondo trasero", "puertas", "cajones", "herrajes",
            "patas", "cantos terminados", "uniones de taller",
        ],
        "requires_user_confirmation": True,
        "fabrication_ready": False,
        "cutting_ready": False,
        "drilling_ready": False,
        "purchase_ready": False,
    }


# F7C review-layout contract. Every internal value below is an explicitly
# unconfirmed visual convention, not a customer dimension or hardware choice.
_DRAWER_COUNT = re.compile(
    r"(?<!\w)(?P<count>[1-4]|un|uno|una|dos|tres|cuatro)\s+"
    r"(?:cajon(?:es)?|gavetas?)(?!\w)", re.IGNORECASE,
)
_DRAWER_NUMBER_WORDS = {
    "un": 1, "uno": 1, "una": 1,
    "dos": 2, "tres": 3, "cuatro": 4,
}
_DRAWER_LAYOUT_EXCLUSIONS = (
    "grande", "grandes", "pequeño", "pequenos", "pequena",
    "pequeñas", "arriba", "abajo", "superior", "inferior",
    "distintos", "diferentes", "desiguales", "alto diferente",
    "puertas", "puerta", "patas", "zocalo", "banqueo",
    "suspendido", "empotrado", "mural", "riel", "rieles",
    "corredera", "bisagra", "tablero", "espesor", "mdf", "mdp",
    "melamina", "entrepaño", "repisa", "estante", "modulos",
    "módulos", "izquierda", "derecha", "dividido", "dividida",
)


def _illustrative_drawer_layout_option(
    utterance: str, request: dict[str, Any], conflicts: list[str],
) -> dict[str, Any] | None:
    """A single F1-compatible *unexecuted* proposal for equal drawer openings.

    No F1/F7C geometry call occurs here. Approval is required before routing
    the exact request through existing Maestro's modular action.
    """
    if conflicts or request.get("action") != "project":
        return None
    project = request.get("project")
    if type(project) is not dict:
        return None
    keys = ("width_mm", "height_mm", "depth_mm")
    if not set(keys).issubset(project):
        return None
    if set(project) - {*keys, "project_type"}:
        return None
    normalized = _fold(utterance)
    if not re.search(r"(?<!\w)(?:cajonera|mueble|gabinete)(?!\w)", normalized):
        return None
    matches = list(_DRAWER_COUNT.finditer(normalized))
    if len(matches) != 1:
        return None
    # "3 gavetas y un cajón" does not mean three total drawers. Accept
    # exactly one explicitly counted group; any second drawer noun declines.
    drawer_nouns = list(re.finditer(
        r"(?<!\w)(?:cajon(?:es)?|gavetas?)(?!\w)", normalized
    ))
    if len(drawer_nouns) != 1:
        return None
    if any(re.search(r"(?<!\w)" + re.escape(_fold(word)) + r"(?!\w)", normalized)
           for word in _DRAWER_LAYOUT_EXCLUSIONS):
        return None
    amount = matches[0].group("count")
    count = int(amount) if amount.isdecimal() else _DRAWER_NUMBER_WORDS[amount]
    if any(type(project[k]) is not int for k in keys):
        return None
    w, h, d = (project[k] for k in keys)
    # Avoid a cosmetic "layout" consisting of unusably tiny nominal openings.
    if min(w, d) <= 36 or h < (36 + (count-1)*28 + count*60):
        return None
    module_spec = {
        "type": "drawer_layout_proposal",
        **{k: project[k] for k in keys},
        "panel_thickness_mm": 18,
        "construction": "top_bottom_full",
        "vertical_gap_mm": 28 if count > 1 else 0,
        "drawer_weights": [1] * count,
    }
    return {
        "status": "OPTIONAL_DRAWER_LAYOUT_REQUIRES_APPROVAL",
        "description": (
            f"Esquema de {count} aberturas iguales, "
            "sin cajas de cajón ni frentes fabricables."
        ),
        "proposed_request": {"action": "modular", "module_spec": module_spec},
        "explicit_user_values_to_confirm": {**{k: project[k] for k in keys},
                                  "drawer_count": count},
        "suggested_fields": {
            "panel_thickness_mm": 18,
            "construction": "top_bottom_full",
            "vertical_gap_mm": module_spec["vertical_gap_mm"],
            "drawer_weights": list(module_spec["drawer_weights"]),
        },
        "suggestion_source": "ASSISTANT_ILLUSTRATIVE_DEFAULT_NOT_USER_SPECIFIED",
        "assumptions": [
            "Alturas iguales, solo para iniciar una conversación visual.",
            "Espesor de 18 mm y franjas de 28 mm ilustrativos, no seleccionados.",
            "La profundidad se interpreta como carcasa; fachada pendiente.",
            "Las franjas entre aberturas NO son tableros ni travesaños.",
            "No se eligen rieles, tiradores, caras, fondos, uniones ni apoyos.",
        ],
        "source_engine_after_confirmation": "F1_CORE_CABINET",
        "can_generate_f7c": False,
        "parts": [],
        "piece_count": 0,
        "requires_user_confirmation": True,
        "fabrication_ready": False, "cutting_ready": False,
        "drilling_ready": False, "purchase_ready": False,
    }


def preview_natural_request(
    utterance: str,
    proposed_request: dict[str, Any] | None = None,
    *,
    include_concept_sketch: bool = False,
) -> dict[str, Any]:
    """Stage, never execute, an untrusted conversational interpretation.

    Top-level request shape is validated by Maestro's existing single
    validator. Nested dimensions/materials/herrajes are NOT inferred or
    accepted as technical facts until the user confirms and a separate
    Maestro call validates them through its existing deterministic engines.
    """
    if type(include_concept_sketch) is not bool:
        raise MaestroError("include_concept_sketch debe ser booleano.")
    if include_concept_sketch and proposed_request is not None:
        raise MaestroError(
            "El croquis de texto directo no acepta candidatos externos; "
            "revisar el JSON mediante Maestro tras confirmación."
        )
    if type(utterance) is not str or not utterance.strip():
        raise MaestroError("F7D requiere texto del usuario no vacío.")
    if len(utterance) > MAX_UTTERANCE_CHARS:
        raise MaestroError("F7D supera el límite de texto (2000 caracteres).")

    result: dict[str, Any] = {
        "assistant": "CarpiNova Maestro",
        "mode": "F7D_NATURAL_REQUEST_REVIEW",
        "status": "NEEDS_STRUCTURED_PROPOSAL",
        "utterance": utterance,
        "proposed_request": None,
        "requires_user_confirmation": True,
        "executed_tools": [],
        "source_provenance": [],
        "fabrication_ready": False,
        "cutting_ready": False,
        "drilling_ready": False,
        "purchase_ready": False,
        "next_step": (
            "Un intérprete externo debe proponer un JSON Maestro explícito; "
            "no se infieren medidas o decisiones de fabricación."
        ),
    }
    if proposed_request is None:
        evidence = extract_explicit_dimensions(utterance)
        result["explicit_measurements"] = evidence["dimensions_mm"]
        result["source_provenance"] = evidence["source_provenance"]
        result["ambiguous_fields"] = evidence["ambiguous_fields"]
        if not evidence["dimensions_mm"]:
            return result
        # User must still confirm which dimension is exterior. No material,
        # joints, slides, or missing dimensions are inferred or fabricated.
        project = dict(evidence["dimensions_mm"])
        kind = _explicit_project_type(utterance)
        if kind is not None:
            project["project_type"] = kind
        proposed_request = {"action": "project", "project": project}
        option = _illustrative_open_cabinet_option(
            utterance, proposed_request, evidence["ambiguous_fields"]
        )
        if option is not None:
            result["illustrative_option"] = option
        drawer_option = _illustrative_drawer_layout_option(
            utterance, proposed_request, evidence["ambiguous_fields"]
        )
        if drawer_option is not None:
            if include_concept_sketch:
                # Explicit viewing request: reuse the SAME deterministic F1
                # opening calculation and F7C review sketch, not F7C parts.
                # This does NOT approve the staged request, execute CAD, or
                # authorize any fabricable output.
                from .drawer_modules import propose_drawer_layout
                from .core import DesignError
                try:
                    plan = propose_drawer_layout(
                        drawer_option["proposed_request"]["module_spec"]
                    )
                except DesignError as exc:
                    raise MaestroError(
                        "No se puede dibujar este boceto nominal: " + str(exc)
                    ) from exc
                if (plan.get("status") != "NEEDS_USER_CONFIRMATION"
                        or plan.get("piece_count") != 0
                        or plan.get("parts") != []
                        or any(plan.get(key) is not False for key in (
                            "fabrication_ready", "cutting_ready",
                            "drilling_ready", "purchase_ready"
                        ))):
                    raise MaestroError("El boceto F1 no mantiene los bloqueos.")
                drawer_option["concept_preview"] = {
                    "source_engine": "F1_CORE_CABINET_REVIEW_ONLY",
                    "sketch_svg": plan["sketch_svg"],
                    "sketch_text": plan["sketch_text"],
                    "opening_plan_bottom_to_top": plan["opening_plan"],
                    "opening_refs_top_to_bottom": [
                        {"ref": chr(65 + i),
                         "cad_review_id": opening["drawer_id"],
                         "opening_height_mm": opening["opening_height_mm"]}
                        for i, opening in enumerate(reversed(plan["opening_plan"]))
                    ],
                    "piece_count": 0,
                    "not_fabrication_geometry": True,
                }
            result["illustrative_drawer_layout_option"] = drawer_option

    if type(proposed_request) is not dict:
        raise MaestroError("La propuesta F7D debe ser un objeto JSON Maestro.")
    # Delegate the routing/allowed fields/required fields to the existing
    # Maestro validator. This does NOT call any geometry or source engine.
    _normalize_request(proposed_request)
    try:
        encoded = json.dumps(
            proposed_request, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
        if len(encoded.encode("utf-8")) > MAX_CANDIDATE_UTF8_BYTES:
            raise MaestroError("Propuesta F7D demasiado grande.")
        restored = json.loads(encoded)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise MaestroError("La propuesta F7D solo puede contener datos JSON válidos.") from exc
    if restored != proposed_request:
        raise MaestroError("La propuesta F7D no debe convertir silenciosamente tipos o claves.")
    result["proposed_request"] = restored
    result["status"] = "NEEDS_USER_CONFIRMATION"
    result["next_step"] = (
        "Mostrar el texto original, cotas reconocidas y propuesta revisable. "
        "Confirmar que cada medida corresponde al mueble completo. "
        "Después, ejecutar Maestro con el mismo JSON y preguntar solo "
        "por datos indispensables; sin autorizar fabricar ni cortar."
    )
    return result


# A correction is applied only to a previously proposed F7D opening sketch.
# It is never an authorization to materialize drawer boxes, hardware, or CAD.
_CORRECTION = re.compile(
    r"^(?:(?:haz|pon|deja|ajusta|cambia)\s+)?"
    r"(?:el\s+)?(?:(?:cajon|gaveta)\s+)?"
    r"(?P<ref>[a-d])\s+"
    r"(?P<amount>\d{1,4}(?:[.,]\d{1,2})?)\s*"
    r"(?P<unit>mm|cm|milimetros?|centimetros?)\s+"
    r"mas\s+(?P<direction>alto|bajo)"
    r"(?:\s+que\s+(?:antes|ahora))?$",
    re.IGNORECASE,
)
_MAX_REVISIONS = 12
_MIN_ILLUSTRATIVE_OPENING_MM = 60


def _parse_drawer_correction(instruction: str, count: int) -> tuple[str, int]:
    if (type(instruction) is not str or not instruction.strip()
            or len(instruction) > 120):
        raise MaestroError("Corrección: texto breve y explícito requerido.")
    match = _CORRECTION.fullmatch(_fold(instruction).strip())
    if not match:
        raise MaestroError(
            "Corrección ambigua: usar «haz el cajón A 10 cm más alto» "
            "o «B 5 cm más bajo», con unidad explícita."
        )
    ref = match.group("ref").upper()
    if not 0 <= ord(ref) - ord("A") < count:
        raise MaestroError("La referencia no existe en este mueble: " + ref)
    quantity = Decimal(match.group("amount").replace(",", "."))
    multiplier = 10 if match.group("unit").startswith(("cm", "centimetro")) else 1
    mm = quantity * multiplier
    if mm != mm.to_integral_value() or not 1 <= mm <= 500:
        raise MaestroError("Corrección: entre 1 y 500 mm enteros.")
    return ref, int(mm) * (1 if match.group("direction") == "alto" else -1)


def revise_drawer_concept(
    previous_preview: dict[str, Any],
    correction: str,
    *,
    include_concept_sketch: bool = False,
) -> dict[str, Any]:
    """Edit a REVIEW opening plan, replaying earlier requests via the same F1.

    The previous JSON is never a geometry authority: rebuild from original
    utterance and replay a capped, exact, auditable list of human corrections.
    """
    from .core import DesignError
    from .drawer_modules import _apportion_nominal, propose_drawer_layout

    if type(include_concept_sketch) is not bool:
        raise MaestroError("include_concept_sketch debe ser booleano.")
    if (type(previous_preview) is not dict
            or previous_preview.get("status") != "NEEDS_USER_CONFIRMATION"
            or previous_preview.get("requires_user_confirmation") is not True
            or previous_preview.get("executed_tools") != []
            or any(previous_preview.get(key) is not False for key in (
                "fabrication_ready", "cutting_ready",
                "drilling_ready", "purchase_ready"
            ))):
        raise MaestroError("Estado anterior no es un boceto revisable.")
    utterance = previous_preview.get("utterance")
    if type(utterance) is not str:
        raise MaestroError("Falta la descripción original del mueble.")
    fresh = preview_natural_request(utterance)
    base = fresh.get("illustrative_drawer_layout_option")
    previous = previous_preview.get("illustrative_drawer_layout_option")
    if not isinstance(base, dict) or not isinstance(previous, dict):
        raise MaestroError("El origen no es una propuesta simple de cajonera.")
    if (previous_preview.get("proposed_request") != fresh["proposed_request"]
            or previous.get("explicit_user_values_to_confirm")
            != base["explicit_user_values_to_confirm"]
            or previous.get("suggestion_source") != base["suggestion_source"]):
        raise MaestroError("Las medidas o el origen del boceto se alteraron.")
    raw_history = previous_preview.get("drawer_revisions_history", [])
    if (type(raw_history) is not list or len(raw_history) >= _MAX_REVISIONS
            or any(type(item) is not dict or set(item) != {
                "instruction", "ref", "delta_mm"
            } for item in raw_history)):
        raise MaestroError("Historial de correcciones inválido o completo.")

    count = base["explicit_user_values_to_confirm"]["drawer_count"]
    spec = dict(base["proposed_request"]["module_spec"])
    replay: list[dict[str, Any]] = []
    last_diff: list[dict[str, Any]] = []
    for item in [*raw_history, {"instruction": correction}]:
        instruction = item["instruction"]
        ref, delta = _parse_drawer_correction(instruction, count)
        if "ref" in item and (item["ref"] != ref or item["delta_mm"] != delta):
            raise MaestroError("El historial no coincide con las frases del usuario.")
        prior_spec = dict(spec)
        try:
            original = propose_drawer_layout(spec)
            # Public references A-D top down; F1 internal D1-D4 bottom up.
            before = [
                row["opening_height_mm"]
                for row in reversed(original["opening_plan"])
            ]
            position = ord(ref) - ord("A")
            if len(before) == 1:
                raise MaestroError(
                    "Un solo cajón no puede cambiar su altura sin modificar el mueble."
                )
            requested = before[position] + delta
            others = [i for i in range(count) if i != position]
            remaining = sum(before) - requested
            if (requested < _MIN_ILLUSTRATIVE_OPENING_MM
                    or remaining < _MIN_ILLUSTRATIVE_OPENING_MM * len(others)):
                raise MaestroError(
                    "La corrección no deja altura nominal suficiente "
                    "para todas las aberturas."
                )
            redistributed = _apportion_nominal(
                remaining, [before[i] for i in others]
            )
            after = list(before)
            after[position] = requested
            for idx, value in zip(others, redistributed):
                after[idx] = value
            if min(after) < _MIN_ILLUSTRATIVE_OPENING_MM:
                raise MaestroError(
                    "Alguna abertura queda por debajo del mínimo visual de 60 mm."
                )
            spec["opening_heights_mm"] = list(reversed(after))
            verified = propose_drawer_layout(spec)
        except DesignError as exc:
            raise MaestroError("Corrección F1 inválida: " + str(exc)) from exc
        if (verified["external_dimensions_mm"]
                != original["external_dimensions_mm"] or verified["piece_count"] != 0):
            raise MaestroError("La corrección alteró la envolvente o fabricó piezas.")
        last_diff = [
            {
                "ref": chr(ord("A") + i),
                "before_mm": old,
                "after_mm": new,
                "delta_mm": new - old,
                "cause": ("USER_REQUESTED" if i == position
                          else "AUTO_REDISTRIBUTED_TO_KEEP_TOTAL_HEIGHT"),
            }
            for i, (old, new) in enumerate(zip(before, after)) if old != new
        ]
        replay.append({"instruction": instruction, "ref": ref, "delta_mm": delta})

    # Reject silently altered opening plans, even if the untrusted JSON
    # still carries a plausible preview or a modified file path.
    if previous.get("proposed_request") != {
        "action": "modular", "module_spec": prior_spec
    }:
        raise MaestroError("El plan anterior no coincide con su historial.")

    fresh_option = fresh["illustrative_drawer_layout_option"]
    fresh_option["proposed_request"] = {"action": "modular", "module_spec": spec}
    fresh_option["revision_geometry_source"] = (
        "F1_DERIVED_FROM_USER_DELTA_AND_EXPLICIT_REDISTRIBUTION"
    )
    fresh_option["opening_heights_mm_top_to_bottom"] = [
        item["opening_height_mm"] for item in reversed(verified["opening_plan"])
    ]
    fresh["drawer_revisions_history"] = replay
    fresh["last_revision"] = {
        "instruction": correction,
        "changes": last_diff,
        "envelope_unchanged": True,
        "requires_user_confirmation": True,
    }
    if include_concept_sketch:
        fresh_option["concept_preview"] = {
            "source_engine": "F1_CORE_CABINET_REVIEW_ONLY",
            "sketch_svg": verified["sketch_svg"],
            "sketch_text": verified["sketch_text"],
            "opening_plan_bottom_to_top": verified["opening_plan"],
            "opening_refs_top_to_bottom": [
                {"ref": chr(ord("A") + i),
                 "cad_review_id": row["drawer_id"],
                 "opening_height_mm": row["opening_height_mm"]}
                for i, row in enumerate(reversed(verified["opening_plan"]))
            ],
            "piece_count": 0,
            "not_fabrication_geometry": True,
        }
    fresh["next_step"] = (
        "Revisar el nuevo croquis y todos los deltas A-D; aceptar o corregir. "
        "No hay autorización para generar piezas, comprar ni fabricar."
    )
    return fresh

