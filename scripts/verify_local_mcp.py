"""Cross-platform REAL MCP local test: one engine, two sample furniture projects.

Run after installing direct dependencies. No local CAD application or network.
This script is the SINGLE authoritative MCP protocol test for Linux CI,
Windows CI and a newly configured owner's PC. It never clears output folders.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from pathlib import Path
import sys
from xml.etree import ElementTree

from carpinova_agent.cad_exchange import validate_exchange

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES = (
    ("primer_mueble", "pilot-open-kitchen-800.json", 4),
    ("cocina_dos_modulos", "modular-kitchen-door-fronts.json", 13),
)
TOOLS = {
    "carpinova_estado",
    "carpinova_consultar",
    "carpinova_generar_borrador",
    "carpinova_renderizar_lamina",
    "carpinova_leer_entregable",
}
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")


def verified_requests() -> list[tuple[str, str, int]]:
    results = []
    for name, filename, count in CASES:
        obj = json.loads((PROJECT_ROOT / "examples" / filename).read_text(encoding="utf-8"))
        if filename == "pilot-open-kitchen-800.json":
            assert obj["action"] == "modular"
        else:
            obj = {"action": "modular", "module_spec": obj}
        results.append((name, json.dumps(obj, ensure_ascii=False), count))
    return results


async def execute(output_root: Path) -> None:
    # Official SDK, imported only after a deliberate explicit invocation.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    requests = verified_requests()
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "carpinova_agent.mcp_bridge"],
        env={**os.environ, "CARPINOVA_OUTPUT_ROOT": str(output_root),
             "PYTHONPATH": str(PROJECT_ROOT)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            available = await session.list_tools()
            names = {tool.name for tool in available.tools}
            assert names == TOOLS, f"MCP tools mismatch: {names}"
            state = await session.call_tool("carpinova_estado", {})
            assert not state.isError, "State tool failed"
            for project, request, _ in requests:
                for tool, args in (
                    ("carpinova_consultar", {"solicitud_json": request}),
                    ("carpinova_generar_borrador", {
                        "solicitud_json": request, "proyecto": project,
                    }),
                    ("carpinova_renderizar_lamina", {"proyecto": project}),
                    ("carpinova_leer_entregable", {
                        "proyecto": project, "archivo": "lamina/three-views.svg",
                    }),
                ):
                    response = await session.call_tool(tool, args)
                    assert not response.isError, f"{project}: {tool}: {response}"


def validate_artifacts(root: Path) -> list[dict]:
    results = []
    for project, _, count in verified_requests():
        folder = root / project
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        maestro = json.loads((folder / "maestro-review.json").read_text(encoding="utf-8"))
        cad = validate_exchange(json.loads(
            (folder / "cad-exchange.json").read_text(encoding="utf-8")
        ))
        sheet = json.loads((folder / "lamina" / "render-manifest.json").read_text(
            encoding="utf-8"
        ))
        assert manifest["piece_count"] == maestro["modular"]["piece_count"] == count
        assert sheet["piece_count"] == len(cad["boxes"]) == count
        assert manifest["geometry_sha256"] == cad["geometry_sha256"] == sheet["geometry_sha256"]
        assert maestro["status"] == manifest["status"] == "DRAFT_NOT_FOR_CUTTING"
        assert all(manifest[k] is False and maestro[k] is False and sheet[k] is False
                   for k in FLAGS)
        assert all(cad[k] is False
                   for k in ("fabrication_ready", "cutting_ready", "drilling_ready"))
        with (folder / "parts-review.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == count
        assert all(r["production_status"] == "BORRADOR_NO_CORTAR" for r in rows)
        ElementTree.parse(folder / "front-review.svg")
        ElementTree.parse(folder / "lamina" / "three-views.svg")
        assert (folder / "lamina" / "three-views.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert (folder / "lamina" / "three-views.pdf").read_bytes()[:5] == b"%PDF-"
        if project == "cocina_dos_modulos":
            assert sum(b["role"].startswith("front_") for b in cad["boxes"]) == 3
            assert sum(b["role"].startswith("back_") for b in cad["boxes"]) == 2
            assert len(maestro["modular"]["modules"]) == 2
        results.append({
            "project": project, "pieces": count,
            "geometry_sha256": cad["geometry_sha256"],
            "fabrication_ready": False, "cutting_ready": False,
            "drilling_ready": False, "purchase_ready": False,
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="CarpiNova MCP local preflight, no fabrication.")
    parser.add_argument("--output-root", type=Path, required=True)
    options = parser.parse_args()
    root = options.output_root.expanduser().resolve()
    if not root.is_absolute():
        raise ValueError("Output folder must be absolute.")
    if root.exists():
        if not root.is_dir() or any(root.iterdir()):
            raise ValueError("Use a new, empty output folder; do not overwrite reviews.")
    else:
        root.mkdir(parents=True)
    asyncio.run(execute(root))
    results = validate_artifacts(root)
    report = {
        "status": "MCP_LOCAL_PROTOCOL_PASS",
        "runtime_platform": sys.platform,
        "python": sys.version.split()[0],
        "tools": sorted(TOOLS),
        "projects": results,
        "fabrication_authority": False,
        "pc_owner_session_certified": False,
        "freecad_blender_executed_by_this_script": False,
    }
    (root / "mcp-preflight-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for item in results:
        print("MCP_FURNITURE_PASS=" + item["project"] +
              "; PIECES=" + str(item["pieces"]) +
              "; GEOMETRY_SHA256=" + item["geometry_sha256"])
    print("REAL_MCP_STDIO=PASS; FIVE_TOOLS=PASS")
    print("THREE_VIEWS_SVG_PNG_PDF=PASS")
    print("FABRICATION_AUTHORITY=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
