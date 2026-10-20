"""Run CarpiNova Maestro with structured project or plain book query.

Examples:
  python -m carpinova_agent.maestro_cli --input examples/maestro-combined.json --bundle-dir ...
  python -m carpinova_agent.maestro_cli --question "bisagras" --bundle-dir ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from hardware import HardwareError
from knowledge_client import BundleError
from .core import DesignError
from .maestro import MaestroError, consult_maestro
from .natural_intake import MAX_CANDIDATE_UTF8_BYTES, preview_natural_request
from .sketch import render_svg
from .modular_outputs import modular_front_svg, modular_bom_csv


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MaestroError("F7D JSON con clave duplicada: " + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise MaestroError("F7D JSON no admite valores no finitos: " + value)


def _load_untrusted_candidate(path: Path) -> object:
    # Read at most one byte beyond the explicit upper bound, even on file races.
    with path.open("rb") as stream:
        payload = stream.read(MAX_CANDIDATE_UTF8_BYTES + 1)
    if len(payload) > MAX_CANDIDATE_UTF8_BYTES:
        raise MaestroError("Propuesta F7D demasiado grande.")
    return json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_unique_keys,
        parse_constant=_reject_constant,
    )


def _confirmation_display(preview: dict) -> tuple[str, str]:
    payload = json.dumps(
        {"texto_original": preview["utterance"],
         "propuesta_no_verificada": preview["proposed_request"]},
        indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False,
    )
    # This short checksum is ONLY an anti-accidental-approval cue, not
    # authentication, a digital signature or manufacturing authority.
    code = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12].upper()
    return payload, "CONFIRMAR " + code


def _require_human_terminal_confirmation(preview: dict) -> None:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise MaestroError("F7D ejecución bloqueada: requiere terminal humana interactiva (TTY).")
    shown, phrase = _confirmation_display(preview)
    sys.stderr.write(
        "F7D — REVISIÓN HUMANA. Esta propuesta NO está verificada técnicamente.\n"
        "Comprueba TODOS los datos y el texto original antes de ejecutar Maestro:\n"
        + shown + "\n"
        "No autoriza fabricar, cortar, perforar ni comprar.\n"
        "Para ejecutar solamente Maestro, escribe exactamente: " + phrase + "\n"
        "Confirmación: "
    )
    sys.stderr.flush()
    if sys.stdin.readline().rstrip("\r\n") != phrase:
        raise MaestroError("F7D cancelado: no hubo confirmación humana exacta.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CarpiNova Maestro F5: guía, libro y herrajes; NO APTO PARA FABRICACIÓN."
    )
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", type=Path, help="Solicitud estructurada JSON")
    inputs.add_argument("--question", type=str,
                        help="Consulta libre solo para buscar en el libro")
    inputs.add_argument("--utterance", type=str,
                        help="F7D: texto natural, SOLO previsualización sin ejecutar herramientas")
    parser.add_argument("--candidate", type=Path,
                        help="JSON propuesto por intérprete externo; requiere --utterance")
    parser.add_argument("--confirm-execute", action="store_true",
                        help="F7D: tras revisión completa, solicitar confirmación humana TTY para Maestro")
    parser.add_argument("--bundle-dir", type=Path,
                        help="Carpeta de bundle Knowledge completo, ya compilado")
    parser.add_argument("--output", type=Path, help="Salida JSON")
    parser.add_argument("--sketch", type=Path,
                        help="SVG frontal si el proyecto tiene geometría soportada")
    parser.add_argument("--csv", type=Path, help="BOM de revisión si hay módulo F6")
    parser.add_argument("--max-questions", type=int, default=3)
    args = parser.parse_args()
    try:
        if args.utterance is not None:
            if args.sketch is not None or args.csv is not None:
                raise MaestroError(
                    "F7D no emite SVG ni CSV: ejecutar exportaciones en una operación aparte."
                )
            if args.bundle_dir is not None and not args.confirm_execute:
                raise MaestroError(
                    "F7D previsualización no admite bundle: no ejecuta herramientas."
                )
            candidate = (
                _load_untrusted_candidate(args.candidate)
                if args.candidate is not None else None
            )
            preview = preview_natural_request(args.utterance, candidate)
            if args.confirm_execute:
                if preview["status"] != "NEEDS_USER_CONFIRMATION":
                    raise MaestroError(
                        "F7D requiere --candidate y revisión completa para ejecutar Maestro."
                    )
                if (
                    args.output is not None and args.candidate is not None
                    and args.output.resolve() == args.candidate.resolve()
                ):
                    raise MaestroError("La salida no puede sobrescribir la propuesta revisada.")
                _require_human_terminal_confirmation(preview)
                # Second, explicit operation: existing deterministic Maestro
                # revalidates the exact JSON presented to the user.
                response = consult_maestro(
                    preview["proposed_request"],
                    bundle_dir=args.bundle_dir,
                    max_questions=args.max_questions,
                )
                output = json.dumps(response, indent=2, ensure_ascii=False) + "\n"
            else:
                output = json.dumps(preview, indent=2, ensure_ascii=False) + "\n"
            if args.output is not None:
                args.output.write_text(output, encoding="utf-8")
            else:
                sys.stdout.write(output)
            return 0
        if args.candidate is not None or args.confirm_execute:
            raise MaestroError("--candidate y --confirm-execute requieren --utterance.")
        if args.input is not None:
            inp = json.loads(args.input.read_text(encoding="utf-8"))
        else:
            inp = {"action": "knowledge", "query": args.question}
        response = consult_maestro(
            inp, bundle_dir=args.bundle_dir, max_questions=args.max_questions
        )
        if args.sketch:
            if response["modular"] is not None:
                svg = modular_front_svg(response["modular"])
            else:
                part = response["project"]
                if part is None or part["design"] is None or part["phase"] != "GEOMETRY_DRAFT":
                    raise MaestroError(
                        "No es seguro generar un croquis: faltan medidas o hay conflicto."
                    )
                svg = render_svg(part["design"])
        else:
            svg = None
        if args.csv:
            if response["modular"] is None:
                raise MaestroError("CSV de revisión F6 solo disponible en modo modular.")
            csv_data = modular_bom_csv(response["modular"])
        else:
            csv_data = None
        output = json.dumps(response, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        if svg is not None:
            args.sketch.write_text(svg, encoding="utf-8")
        if csv_data is not None:
            args.csv.write_text(csv_data, encoding="utf-8")
        return 0
    except (OSError, UnicodeError, ValueError, DesignError, BundleError,
            HardwareError, MaestroError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
