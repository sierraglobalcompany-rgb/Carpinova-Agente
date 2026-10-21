"""Local CarpiNova MCP adapter: one Maestro engine, one geometry contract.

Only stdio is exposed. No user-account service, remote network listener,
arbitrary Python execution, fabrication authority, or CAD application launch.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from .maestro import MaestroError, consult_maestro
from .drawing_sheet import create_render_bundle
from .pilot_cli import PilotError, write_pilot_bundle


_MAX_REQUEST_BYTES = 65536
_MAX_ARTIFACT_BYTES = 262144
_PROJECT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$")
_ALLOWED_FILES = frozenset((
    "maestro-review.json", "front-review.svg", "parts-review.csv",
    "cad-exchange.json", "manifest.json",
    "lamina/three-views.svg", "lamina/render-manifest.json",
))
_FABRICATION = {
    "fabrication_ready": False, "cutting_ready": False,
    "drilling_ready": False, "purchase_ready": False,
}


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MaestroError("JSON con clave duplicada: " + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise MaestroError("Se rechazó una cifra no finita en JSON.")


def _request(raw: str) -> dict[str, Any]:
    if type(raw) is not str or not raw.strip() or len(raw.encode("utf-8")) > _MAX_REQUEST_BYTES:
        raise MaestroError("Solicitud vacía o mayor de 64 KiB.")
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant,
        )
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise MaestroError("La solicitud no contiene JSON válido.") from exc
    if type(value) is not dict:
        raise MaestroError("La solicitud Maestro debe ser un objeto JSON.")
    return value


def _output_root() -> Path:
    raw = os.environ.get("CARPINOVA_OUTPUT_ROOT")
    if not raw:
        raise PilotError("Configurar CARPINOVA_OUTPUT_ROOT antes de exportar.")
    base = Path(raw).expanduser()
    if not base.is_absolute() or not base.is_dir() or base.is_symlink():
        raise PilotError("CARPINOVA_OUTPUT_ROOT debe ser un directorio absoluto existente y real.")
    return base.resolve(strict=True)


def _project_id(name: str) -> str:
    if type(name) is not str or not _PROJECT_NAME.fullmatch(name):
        raise PilotError("Nombre de proyecto inválido: letras, números, guion o guion bajo.")
    return name


def carpinova_estado() -> dict[str, Any]:
    """List contract availability; not a claim that CAD MCP is installed."""
    return {
        "name": "CarpiNova Maestro",
        "transport": "stdio",
        "status": "DRAFT_DESIGN_ONLY",
        "actions": ["project", "knowledge", "hardware", "combined", "modular", "construction"],
        "skills": ["maestro-carpintero", "diseno-muebles",
                   "seleccion-herrajes", "tecnicas-constructivas"],
        "knowledge_bundle_configured": bool(os.environ.get("CARPINOVA_KNOWLEDGE_BUNDLE_DIR")),
        "output_root_configured": bool(os.environ.get("CARPINOVA_OUTPUT_ROOT")),
        "freecad_blender_mcp_connected": False,
        **_FABRICATION,
    }


def carpinova_consultar(solicitud_json: str) -> dict[str, Any]:
    """Query existing deterministic Maestro. Text is not treated as code."""
    request = _request(solicitud_json)
    bundle = os.environ.get("CARPINOVA_KNOWLEDGE_BUNDLE_DIR")
    bundle_path = Path(bundle).expanduser() if bundle else None
    return consult_maestro(request, bundle_dir=bundle_path)


def carpinova_generar_borrador(solicitud_json: str, proyecto: str) -> dict[str, Any]:
    """Produce a five-file NOMINAL review from explicit modular input only.

    No arbitrary output path from the client is honored. Never overwrite.
    """
    request = _request(solicitud_json)
    name = _project_id(proyecto)
    root = _output_root()
    destination = root / name
    manifest = write_pilot_bundle(request, destination)
    return {
        "status": "DRAFT_NOT_FOR_CUTTING",
        "proyecto": name,
        "review_directory": str(destination),
        "geometry_sha256": manifest["geometry_sha256"],
        "piece_count": manifest["piece_count"],
        "files": manifest["files"],
        **_FABRICATION,
    }


def carpinova_renderizar_lamina(proyecto: str) -> dict[str, Any]:
    """Export 3-view SVG, PNG and PDF from canonical CAD, never cut plans.

    Requires optional CairoSVG locally. Does not invoke native CAD, MCP from
    other apps, shell commands or remote APIs. Repeated calls never overwrite.
    """
    name = _project_id(proyecto)
    root = _output_root()
    folder = root / name
    manifest = create_render_bundle(folder)
    return {
        "proyecto": name, "status": "DRAFT_NOT_FOR_CUTTING",
        "geometry_sha256": manifest["geometry_sha256"],
        "piece_count": manifest["piece_count"],
        "files": [str(folder / "lamina" / item) for item in manifest["files"]],
        "image_preview_svg": str(folder / "lamina" / "three-views.svg"),
        "image_preview_png": str(folder / "lamina" / "three-views.png"),
        "printable_pdf": str(folder / "lamina" / "three-views.pdf"),
        **_FABRICATION,
    }


def carpinova_leer_entregable(proyecto: str, archivo: str) -> dict[str, Any]:
    """Read only the allowlisted artefacts from a previously generated bundle."""
    name = _project_id(proyecto)
    if type(archivo) is not str or archivo not in _ALLOWED_FILES:
        raise PilotError("Solo se pueden leer entregables textuales permitidos del borrador.")
    root = _output_root()
    folder = root / name
    path = folder / archivo
    if (folder.is_symlink() or path.is_symlink()
            or (path.parent != folder and path.parent.is_symlink())
            or not path.resolve().is_relative_to(root) or not path.is_file()):
        raise PilotError("Archivo inexistente o fuera del directorio de revisión.")
    if path.stat().st_size > _MAX_ARTIFACT_BYTES:
        raise PilotError("El entregable excede el límite de lectura del Agente.")
    contents = path.read_text(encoding="utf-8")
    return {
        "proyecto": name, "archivo": archivo, "contenido": contents,
        "encoding": "utf-8", "status": "DRAFT_NOT_FOR_CUTTING",
        **_FABRICATION,
    }


def create_server():
    """Import the optional official MCP SDK only when launching this bridge."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP SDK ausente. Instalar: python -m pip install 'mcp>=1.27,<2'"
        ) from exc
    server = FastMCP("CarpiNova Maestro", instructions=(
        "Diseño y consulta de carpintería: consultar, generar borrador y "
        "leer archivos de revisión. Pedir medidas faltantes antes del diseño. "
        "Todos los resultados son NOMINALES y NO autorizan fabricación, "
        "corte, taladro o compra. No ejecutar otras herramientas por analogía."
    ))

    server.tool()(carpinova_estado)
    server.tool()(carpinova_consultar)
    server.tool()(carpinova_generar_borrador)
    server.tool()(carpinova_renderizar_lamina)
    server.tool()(carpinova_leer_entregable)
    return server


def main() -> None:
    # stdout belongs exclusively to the MCP JSON-RPC stdio protocol.
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
