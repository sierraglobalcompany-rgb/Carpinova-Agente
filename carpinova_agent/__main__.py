"""Usage: python -m carpinova_agent --input examples/cabinet.json."""
import argparse
import json
import sys
from pathlib import Path

from .core import DesignError, design


def main() -> int:
    parser = argparse.ArgumentParser(description="Despiece geométrico PRELIMINAR (NO FABRICAR).")
    parser.add_argument("--input", type=Path, help="JSON de entrada; por defecto stdin")
    parser.add_argument("--output", type=Path, help="Archivo JSON de salida; por defecto stdout")
    args = parser.parse_args()
    try:
        source = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
        result = design(json.loads(source))
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    except (OSError, ValueError, DesignError) as error:
        sys.stderr.write(f"ERROR: {error}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
