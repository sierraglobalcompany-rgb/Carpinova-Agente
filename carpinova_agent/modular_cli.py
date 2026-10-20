"""Run: python -m carpinova_agent.modular_cli --input examples/modular-closet.json"""
import argparse
import json
from pathlib import Path
import sys

from .core import DesignError
from .modular import design_modular_run


def main() -> int:
    p = argparse.ArgumentParser(description="Muebles modulares abiertos preliminares, NO FABRICAR.")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path)
    options = p.parse_args()
    try:
        data = json.loads(options.input.read_text(encoding="utf-8"))
        result = design_modular_run(data)
        output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if options.output:
            options.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        return 0 if result["status"] == "DRAFT_NOT_FOR_CUTTING" else 3
    except (OSError, UnicodeError, ValueError, DesignError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
