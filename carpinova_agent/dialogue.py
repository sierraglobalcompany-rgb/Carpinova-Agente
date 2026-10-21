"""Terminal interview for the preliminary structured furniture specification.

No LLM, no recognition of photos, no fixture-based hardware advice.
Never defaults missing dimensions or pretends the answer is production-ready.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from .core import DesignError
from .intake import TYPES, _fold, guide_project


def parse_answer(field: str, value: str) -> Any:
    """Parse a single user response; fail closed on ambiguity."""
    raw = value.strip()
    if not raw:
        raise DesignError("Escribe un valor; no se aplican medidas por defecto.")
    if field.endswith("_mm"):
        match = re.fullmatch(r"([0-9]+)\s*(?:mm)?", raw.casefold())
        if not match:
            raise DesignError("Escribe milímetros enteros, por ejemplo: 600 o 600 mm.")
        return int(match.group(1))
    if field == "project_type":
        if _fold(raw) not in TYPES:
            raise DesignError("Mueble no reconocido. Prueba gabinete, cajón, clóset, cocina o nicho.")
        return raw
    if field == "construction":
        aliases = {
            "costados completos": "sides_full",
            "laterales completos": "sides_full",
            "tapas completas": "top_bottom_full",
            "tapa y base completas": "top_bottom_full",
        }
        canonical = aliases.get(_fold(raw), raw)
        if canonical not in {"sides_full", "top_bottom_full"}:
            raise DesignError(
                "Elige sides_full (costados completos) o "
                "top_bottom_full (tapa y base completas)."
            )
        return canonical
    raise DesignError(f"Pregunta aún no soportada en terminal: {field}.")


def run_interview(
    ask: Callable[[str], str],
    say: Callable[[str], None],
    *,
    max_attempts: int = 40,
) -> tuple[int, dict[str, Any] | None]:
    """Ask for necessary geometry once; return the draft or a safe blocker."""
    values: dict[str, Any] = {}
    say("CarpiNova — diseño preliminar, NO apto para cortar ni perforar.")
    for _ in range(max_attempts):
        try:
            guidance = guide_project(values, max_questions=1)
        except DesignError as exc:
            say(f"Datos inválidos: {exc}. Revisa el proyecto.")
            return 2, None
        phase = guidance["phase"]
        if phase in {"GEOMETRY_DRAFT", "CONCEPT_ONLY"}:
            if phase == "GEOMETRY_DRAFT":
                say("Geometría preliminar calculada; faltan herrajes, vetas, cantos y revisión.")
            else:
                say("Diseño conceptual; dividir en módulos antes de producir un despiece.")
            say(json.dumps(guidance, ensure_ascii=False, indent=2))
            return 0, guidance
        if phase in {"INVALID_GEOMETRY", "SITE_CONFLICT"}:
            say("Bloqueado: " + guidance["release_blockers"][0])
            return 2, guidance
        questions = guidance["questions"]
        if not questions:
            say("No hay pregunta disponible para completar el proyecto.")
            return 2, guidance
        current = questions[0]
        try:
            raw = ask(current["question"] + " (o 'salir'): ")
        except (EOFError, KeyboardInterrupt):
            say("Entrevista cancelada. No se generó un despiece.")
            return 1, None
        if not isinstance(raw, str):
            say("Respuesta inválida: se espera texto.")
            continue
        if _fold(raw) in {"salir", "cancelar"}:
            say("Entrevista cancelada. No se generó un despiece.")
            return 1, None
        try:
            values[current["field"]] = parse_answer(current["field"], raw)
        except DesignError as exc:
            say(str(exc))
    say("Entrevista detenida tras demasiados intentos sin completar datos.")
    return 2, None


def main() -> int:
    code, _ = run_interview(input, print)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
