"""Strict one-time resolution of the documented F4/F5 README merge conflict.

This helper is used ONLY by an isolated no-push merge rehearsal. It cannot
merge branches, change GitHub refs or reconcile any other file/conflict.
"""
from __future__ import annotations
import argparse
from pathlib import Path


def reconcile(f4: str, f5: str, f7: str) -> str:
    hardware = "## Catálogo de herrajes (desarrollo F4)"
    maestro = "## CarpiNova Maestro — interfaz unificada (F5)"
    if hardware not in f4 or hardware in f5 or maestro not in f5:
        raise ValueError("Unexpected source README; abort documented reconciliation.")
    section = f4[f4.index(hardware):].rstrip() + "\n\n"
    resolved = f5.replace(maestro, section + maestro, 1)
    if not f7.startswith(resolved):
        raise ValueError("Final F7 README does not preserve BOTH source documents.")
    return resolved


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--f4", type=Path, required=True)
    p.add_argument("--f5", type=Path, required=True)
    p.add_argument("--f7", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    output = reconcile(
        args.f4.read_text(encoding="utf-8"),
        args.f5.read_text(encoding="utf-8"),
        args.f7.read_text(encoding="utf-8"),
    )
    args.output.write_text(output, encoding="utf-8")
    print("KNOWN_F5_README_CONFLICT=RESOLVED_IN_REHEARSAL_ONLY")
    print("OWNER_REVIEW_REQUIRED=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
