"""First furniture pilot: one Maestro request -> audited draft review bundle.

This is an offline local developer bridge, NOT an MCP tool or a fabrication
service. No LLM, CAD application, network or third-party executable is run.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

from .cad_exchange import cad_exchange, validate_exchange
from .core import DesignError
from .maestro import MaestroError, consult_maestro
from .modular_outputs import modular_bom_csv, modular_front_svg

_BLOCKED_FLAGS = ("fabrication_ready", "cutting_ready",
                  "drilling_ready", "purchase_ready")
_FILES = ("maestro-review.json", "front-review.svg",
          "parts-review.csv", "cad-exchange.json", "manifest.json")


class PilotError(ValueError):
    """An unapproved or inconsistent proposal cannot yield a pilot bundle."""


def pilot_review(request: dict[str, Any]) -> dict[str, str]:
    """Calculate every deliverable from one already-structured Maestro request.

    A text-only proposal or an LLM classification is NOT sufficient input.
    All downstream derivations share Maestro's one modular geometry object.
    """
    if type(request) is not dict or request.get("action") != "modular":
        raise PilotError("Piloto: se requiere action=modular con module_spec explícito.")
    answer = consult_maestro(request)
    model = answer.get("modular")
    if not isinstance(model, dict) or answer["status"] != "DRAFT_NOT_FOR_CUTTING":
        raise PilotError(
            "Proyecto bloqueado: corregir medidas/distribución antes de generar el paquete."
        )
    if any(answer.get(key) is not False or model.get(key) is not False
           for key in _BLOCKED_FLAGS):
        raise PilotError("Respuesta inconsistente: bloqueos de fabricación no preservados.")
    svg = modular_front_svg(model)
    csv_text = modular_bom_csv(model)
    exchange = validate_exchange(cad_exchange(model))
    # CADExchange's strict schema deliberately exposes three release flags.
    # purchase_ready belongs to Maestro and is checked above; do not add a
    # fictitious field to the canonical geometry exchange contract.
    if any(exchange.get(key) is not False for key in (
        "fabrication_ready", "cutting_ready", "drilling_ready"
    )):
        raise PilotError("Contrato CAD inconsistente: autoridad de fabricación alterada.")
    expected = {part["piece_id"] for part in model["parts"]}
    observed = {box["piece_id"] for box in exchange["boxes"]}
    if expected != observed or len(expected) != len(model["parts"]):
        raise PilotError("CAD/BOM no coincide con piezas de geometría Maestro.")
    manifest = {
        "schema_version": "1.0",
        "status": "DRAFT_NOT_FOR_CUTTING",
        "source": "MAESTRO_MODULAR_F1_F7C",
        "piece_count": len(model["parts"]),
        "geometry_sha256": exchange["geometry_sha256"],
        "files": list(_FILES),
        "fabrication_ready": False,
        "cutting_ready": False,
        "drilling_ready": False,
        "purchase_ready": False,
        "limitations": [
            "Medidas nominales, no dimensiones finales de corte.",
            "Cantos, herrajes, ensambles, cargas, instalaciones y tolerancias requieren revisión.",
            "FreeCAD y Blender deben ejecutar por separado el CADExchange con adaptadores auditados.",
        ],
    }
    return {
        "maestro-review.json": json.dumps(answer, indent=2, ensure_ascii=False) + "\n",
        "front-review.svg": svg,
        "parts-review.csv": csv_text,
        "cad-exchange.json": json.dumps(exchange, indent=2, ensure_ascii=False) + "\n",
        "manifest.json": json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    }


def write_pilot_bundle(request: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Fail closed: stage complete files on the same filesystem before rename.

    Requires a new directory. Never overwrite prior review or source files.
    """
    if output_dir.exists() or output_dir.is_symlink():
        raise PilotError("Salida existente: elija un directorio nuevo sin sobrescribir.")
    parent = output_dir.parent
    if not parent.is_dir():
        raise PilotError("El directorio padre de salida debe existir.")
    bundle = pilot_review(request)
    with TemporaryDirectory(prefix=".carpinova-pilot-", dir=parent) as temp:
        staging = Path(temp) / "review"
        staging.mkdir()
        for name in _FILES:
            (staging / name).write_text(bundle[name], encoding="utf-8")
        if output_dir.exists() or output_dir.is_symlink():
            raise PilotError("Otra ejecución creó la salida; no se sobrescribe.")
        # Rename a complete directory within the same filesystem.
        os.rename(staging, output_dir)
    return json.loads(bundle["manifest.json"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CarpiNova: primer paquete geométrico de REVISIÓN, NO para cortar."
    )
    parser.add_argument("--input", required=True, type=Path,
                        help="JSON Maestro action=modular ya revisado")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Carpeta NUEVA para cinco archivos de revisión")
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.input.read_text(encoding="utf-8"))
        result = write_pilot_bundle(request, args.output_dir)
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    except (OSError, ValueError, DesignError, MaestroError, PilotError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
