"""Run CarpiNova Maestro with structured project or plain book query.

Examples:
  python -m carpinova_agent.maestro_cli --input examples/maestro-combined.json --bundle-dir ...
  python -m carpinova_agent.maestro_cli --question "bisagras" --bundle-dir ...
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from hardware import HardwareError
from knowledge_client import BundleError
from .core import DesignError
from .maestro import MaestroError, consult_maestro
from .sketch import render_svg
from .modular_outputs import modular_front_svg, modular_bom_csv


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CarpiNova Maestro F5: guía, libro y herrajes; NO APTO PARA FABRICACIÓN."
    )
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", type=Path, help="Solicitud estructurada JSON")
    inputs.add_argument("--question", type=str,
                        help="Consulta libre solo para buscar en el libro")
    parser.add_argument("--bundle-dir", type=Path,
                        help="Carpeta de bundle Knowledge completo, ya compilado")
    parser.add_argument("--output", type=Path, help="Salida JSON")
    parser.add_argument("--sketch", type=Path,
                        help="SVG frontal si el proyecto tiene geometría soportada")
    parser.add_argument("--csv", type=Path, help="BOM de revisión si hay módulo F6")
    parser.add_argument("--max-questions", type=int, default=3)
    args = parser.parse_args()
    try:
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
