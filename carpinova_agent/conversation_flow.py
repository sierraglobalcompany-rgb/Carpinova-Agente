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

from .cad_exchange import cad_exchange
from .drawer_modules import propose_drawer_layout
from .maestro import MaestroError, consult_maestro
from .intake import _fold
from .natural_intake import (
    OWNER_DIRECTIVE_SOURCE, extract_explicit_dimensions,
    is_drawer_correction_instruction, preview_natural_request,
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
_PRIOR_REPORTED = "PRIOR_DESIGN_DECISION_REPORTED"
_OWNER_DIRECTIVE = OWNER_DIRECTIVE_SOURCE
_WALL_BAR_FIXTURE_SHA256 = "966ba2aaf6f104d3483b5d8126e2ec443c12c54893f992be7e106ce9593d956c"
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


def _wall_bar_reference_review(text: str) -> dict[str, Any] | None:
    """Compare literal bar requirements to the protected reference, without CAD."""
    normalized = _fold(text)
    if not (re.search(r"(?<!\w)barra(?:\s+de\s+cocina)?(?!\w)", normalized)
            and re.search(r"(?<!\w)cajonera(?!\w)", normalized)):
        return None

    fixture, fixture_bytes, fixture_sha = _load_wall_bar_fixture()
    fixture_spec = fixture["module_spec"]
    fixture_module = fixture_spec["cabinet_module"]

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
    large_bottom = drawer_count == 3
    feet = next((item["value_mm"] for item in evidence["component_measurements"]
                 if item.get("scope") == "patas" and item.get("field") == "height_mm"),
                None)
    rails_requested = bool(re.search(r"(?<!\w)(?:riel|rieles|corredera)(?!\w)", normalized))

    reference = {
        "overall_width_mm": fixture_spec["overall_width_mm"],
        "overall_depth_mm": fixture_spec["overall_depth_mm"],
        "overall_height_mm": fixture_spec["overall_height_mm"],
        "free_span_horizontal_mm": fixture_spec["free_span_mm"],
        "cabinet_width_mm": fixture_module["width_mm"],
        "feet_height_mm": fixture_spec["feet_height_mm"],
        "drawer_count": len(fixture_module["drawers"]),
    }
    owner_values = {
        "overall_width_mm": dims.get("width_mm"),
        "overall_depth_mm": dims.get("depth_mm"),
        "overall_height_mm": dims.get("height_mm"),
        "free_span_horizontal_mm": free_span,
        "cabinet_width_mm": cabinet_width,
        "feet_height_mm": feet,
        "drawer_count": drawer_count,
        "large_drawer_position": "bottom" if large_bottom else None,
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
    standard_mentioned = bool(re.search(r"(?<!\w)estandar(?!\w)", normalized))
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


def preview_conversation(utterance: str, corrections: list[str] | None = None) -> dict[str, Any]:
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
