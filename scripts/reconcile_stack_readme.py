"""Fail-closed F4/F5 README reconciliation for an isolated no-push stack rehearsal.

An edited README introduction is permitted, but BOTH upstream F4/F5 sections
must survive byte-for-byte as logical Markdown sections in the final F7C README.
The final F7C README is audited, but only the historical F4+F5 content is
written at the F5 stage. Later PRs must introduce their own README changes.
No other conflicting path, branch ref, or protected branch is modified.
"""
from __future__ import annotations

import argparse
from pathlib import Path


HARDWARE_HEADING = "## Catálogo de herrajes (desarrollo F4)"
MAESTRO_HEADING = "## CarpiNova Maestro — interfaz unificada (F5)"


def _section(source: str, heading: str) -> str:
    lines = source.splitlines(keepends=True)
    positions = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == heading]
    if len(positions) != 1:
        raise ValueError(f"Expected exactly one section {heading!r}; got {len(positions)}.")
    start = positions[0]
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "".join(lines[start:end]).rstrip()


def reconcile(f4: str, f5: str, f7: str) -> str:
    if (
        HARDWARE_HEADING not in f4
        or HARDWARE_HEADING in f5
        or MAESTRO_HEADING not in f5
        or MAESTRO_HEADING in f4
    ):
        raise ValueError("Unexpected source READMEs; abort documented reconciliation.")
    if not f7.startswith("# CarpiNova Agente\n"):
        raise ValueError("Unexpected final F7C README identity.")
    if any(marker in f7 for marker in ("<<<<<<<", "=======", ">>>>>>>")):
        raise ValueError("Unresolved conflict markers in final F7C README.")
    for label, source, heading in (
        ("F4", f4, HARDWARE_HEADING),
        ("F5", f5, MAESTRO_HEADING),
    ):
        if _section(source, heading) != _section(f7, heading):
            raise ValueError(f"Final F7C README does not preserve the exact {label} section.")
    if f7.index(HARDWARE_HEADING) > f7.index(MAESTRO_HEADING):
        raise ValueError("Final F7C README has reversed source section order.")
    # At this point the rehearsal has merged only F1/F3/F2/F4 and is handling
    # F5. Writing the FINAL F7C README here would prematurely introduce F6/F7C
    # edits and cause a false README conflict at F6. Preserve the genuine F5
    # ancestry here; later PR merges apply the feature README on their turn.
    f4_section = _section(f4, HARDWARE_HEADING)
    return f5.replace(MAESTRO_HEADING, f4_section + "\n\n" + MAESTRO_HEADING, 1)


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
    print("F4_F5_SOURCE_SECTIONS_EXACT=YES")
    print("OWNER_REVIEW_REQUIRED=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
