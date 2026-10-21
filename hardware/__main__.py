"""Run: python -m hardware --input examples/hinge-overlay.json"""
import argparse
import json
from pathlib import Path
import sys

from .catalog import HardwareError, suggest_hinge


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Asistente de herrajes Blum, referencias preliminares, NO PERFORAR."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        request = json.loads(args.input.read_text(encoding="utf-8"))
        result = json.dumps(suggest_hinge(request), ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(result, encoding="utf-8")
        else:
            sys.stdout.write(result)
        return 0
    except (OSError, UnicodeError, ValueError, HardwareError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
