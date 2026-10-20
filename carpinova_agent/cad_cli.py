"""python -m carpinova_agent.cad_cli --input examples/modular-closet.json --output /tmp/cad.json"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from .core import DesignError
from .modular import design_modular_run
from .cad_exchange import cad_exchange


def main()->int:
    parser=argparse.ArgumentParser(description="Contrato geométrico F6 para CAD, NO FABRICAR.")
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        spec=json.loads(args.input.read_text(encoding="utf-8"))
        cad=cad_exchange(design_modular_run(spec))
        args.output.write_text(json.dumps(cad,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(f"CAD_PREVIEW_ONLY geometry_sha256={cad['geometry_sha256']}")
        return 0
    except (OSError,ValueError,DesignError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
