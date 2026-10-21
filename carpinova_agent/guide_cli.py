"""CLI for a minimal question-first CarpiNova furniture guide."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .core import DesignError
from .intake import guide_project
from .sketch import render_svg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Entrevista y boceto de mueble (BORRADOR, NO FABRICAR)."
    )
    parser.add_argument("--input", type=Path, required=True,
                        help="Proyecto parcial o completo en JSON")
    parser.add_argument("--output", type=Path, help="Guardar respuesta JSON")
    parser.add_argument("--sketch", type=Path,
                        help="SVG ortográfico solo si geometría soportada")
    parser.add_argument("--max-questions", type=int, default=3)
    options = parser.parse_args()
    try:
        project = json.loads(options.input.read_text(encoding="utf-8"))
        answer = guide_project(project, options.max_questions)
        if options.sketch:
            if answer["design"] is None:
                raise DesignError(
                    "Aún no hay geometría para SVG. Completar preguntas obligatorias."
                )
            svg = render_svg(answer["design"])
        else:
            svg = None
        message = json.dumps(answer, ensure_ascii=False, indent=2) + "\n"
        if options.output:
            options.output.write_text(message, encoding="utf-8")
        else:
            sys.stdout.write(message)
        if options.sketch is not None and svg is not None:
            options.sketch.write_text(svg, encoding="utf-8")
        return 0
    except (OSError, UnicodeError, ValueError, DesignError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
