"""F7D: review untrusted natural-language interpretations before Maestro execution.

No model, NLP parser, CAD executor or MCP session lives here. An external
interpreter may SUGGEST a structured Maestro request; the human must review
it before submitting an independently confirmed JSON to consult_maestro.
"""
from __future__ import annotations

import json
from typing import Any

from .maestro import MaestroError, _normalize_request


MAX_UTTERANCE_CHARS = 2000
MAX_CANDIDATE_UTF8_BYTES = 65536


def preview_natural_request(
    utterance: str,
    proposed_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stage, never execute, an untrusted conversational interpretation.

    Top-level request shape is validated by Maestro's existing single
    validator. Nested dimensions/materials/herrajes are NOT inferred or
    accepted as technical facts until the user confirms and a separate
    Maestro call validates them through its existing deterministic engines.
    """
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
        return result
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
        "Mostrar texto original y TODOS los campos de la propuesta al usuario. "
        "Solo tras confirmación explícita del usuario, enviar exactamente el "
        "JSON aprobado a consult_maestro; repetir validaciones allí. "
        "No ejecutar por la sola presencia de esta previsualización."
    )
    return result
