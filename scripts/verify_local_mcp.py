"""Cross-platform REAL MCP local test: one engine, two sample furniture projects.

Run after installing direct dependencies. No local CAD application or network.
This script is the SINGLE authoritative MCP protocol test for Linux CI,
Windows CI and a newly configured owner's PC. It never clears output folders.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

# When invoked as scripts/verify_local_mcp.py Python places scripts/ first
# on sys.path. Restore the actual repo root BEFORE importing the package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from carpinova_agent.cad_exchange import validate_exchange
CASES = (
    ("primer_mueble", "pilot-open-kitchen-800.json", 4),
    ("cocina_dos_modulos", "modular-kitchen-door-fronts.json", 13),
)
TOOLS = {
    "carpinova_estado",
    "carpinova_consultar",
    "carpinova_generar_borrador",
    "carpinova_renderizar_lamina",
    "carpinova_exportar_3d",
    "carpinova_leer_entregable",
}
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")


def _mcp_structured(response, context: str) -> dict:
    if getattr(response, "isError", getattr(response, "is_error", False)):
        raise AssertionError(f"MCP tool error ({context}): {response}")
    value = getattr(response, "structuredContent", None)
    if value is None:
        value = getattr(response, "structured_content", None)
    assert isinstance(value, dict), f"Missing structured MCP response ({context})"
    return value


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str):
    raise ValueError("non-standard JSON constant")


def _read_json_object(text: str, context: str) -> dict:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError):
        raise AssertionError(f"Invalid JSON text in MCP read ({context})") from None
    if type(value) is not dict:
        raise AssertionError(f"MCP read JSON must be an object ({context})")
    return value


def _reader_protocol_shape(response, context: str) -> AssertionError:
    content = getattr(response, "content", None)
    blocks = content if type(content) is list else []
    block_types = []
    text_length = 0
    for block in blocks:
        block_type = getattr(block, "type", None)
        block_types.append(
            block_type if type(block_type) is str else type(block).__name__
        )
        text = getattr(block, "text", None)
        if type(text) is str:
            text_length += len(text)
    metadata = {
        "type": type(response).__name__,
        "structured_present": any(
            getattr(response, name, None) is not None
            for name in ("structuredContent", "structured_content")
        ),
        "content_count": len(content) if type(content) is list else None,
        "block_types": block_types,
        "text_length": text_length,
    }
    return AssertionError(
        f"BLOCKED_PROTOCOL_SHAPE ({context}): {json.dumps(metadata, sort_keys=True)}"
    )


async def _read_payload_via_mcp(session, project: str, filename: str) -> dict:
    response = await session.call_tool(
        "carpinova_leer_entregable", {"proyecto": project, "archivo": filename},
    )
    context = f"read {project}/{filename}"
    if (getattr(response, "isError", False) is True
            or getattr(response, "is_error", False) is True):
        raise AssertionError(f"MCP tool error ({context})")

    structured = []
    for name in ("structuredContent", "structured_content"):
        value = getattr(response, name, None)
        if value is None:
            continue
        if type(value) is not dict:
            raise _reader_protocol_shape(response, context)
        structured.append((name, value))
    if len(structured) > 1 and any(
        value != structured[0][1] for _, value in structured[1:]
    ):
        raise AssertionError(f"Contradictory structured MCP aliases ({context})")

    if structured:
        payload = structured[0][1]
        content = getattr(response, "content", None)
        if type(content) is list:
            for block in content:
                if getattr(block, "type", None) != "text":
                    continue
                text = getattr(block, "text", None)
                if type(text) is not str:
                    continue
                try:
                    comparable = json.loads(
                        text,
                        object_pairs_hook=_reject_duplicate_json_keys,
                        parse_constant=_reject_json_constant,
                    )
                except json.JSONDecodeError:
                    continue
                except ValueError:
                    raise AssertionError(
                        f"Invalid comparable MCP JSON text ({context})"
                    ) from None
                if type(comparable) is not dict or comparable != payload:
                    raise AssertionError(
                        f"Contradictory structured and text MCP responses ({context})"
                    )
    else:
        content = getattr(response, "content", None)
        if (type(content) is not list or len(content) != 1
                or getattr(content[0], "type", None) != "text"
                or type(getattr(content[0], "text", None)) is not str):
            raise _reader_protocol_shape(response, context)
        payload = _read_json_object(content[0].text, context)

    required = {
        "proyecto", "archivo", "encoding", "status", "contenido", *FLAGS,
    }
    if not required.issubset(payload) or set(payload) - required - {"book_evidence_status"}:
        raise AssertionError(f"Invalid MCP artifact response fields ({context})")
    if (type(payload["proyecto"]) is not str or payload["proyecto"] != project
            or type(payload["archivo"]) is not str or payload["archivo"] != filename):
        raise AssertionError(f"MCP artifact identity mismatch ({context})")
    if (type(payload["encoding"]) is not str or payload["encoding"] != "utf-8"
            or type(payload["status"]) is not str
            or payload["status"] != "DRAFT_NOT_FOR_CUTTING"):
        raise AssertionError(f"MCP artifact state mismatch ({context})")
    if type(payload["contenido"]) is not str:
        raise AssertionError(f"MCP artifact content must be text ({context})")
    if any(type(payload[flag]) is not bool or payload[flag] is not False
           for flag in FLAGS):
        raise AssertionError(f"MCP artifact fabrication flags must be false ({context})")
    if ("book_evidence_status" in payload
            and type(payload["book_evidence_status"]) is not str):
        raise AssertionError(f"Invalid MCP book evidence status ({context})")
    return payload


async def _read_json_via_mcp(session, project: str, filename: str) -> dict:
    payload = await _read_payload_via_mcp(session, project, filename)
    return json.loads(payload["contenido"])


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
            catalog = {tool.name: tool for tool in available.tools}
            for name in ("carpinova_estado", "carpinova_consultar"):
                annotations = catalog[name].annotations
                assert annotations is not None, f"Missing read-only hint: {name}"
                assert annotations.model_dump(by_alias=True).get("readOnlyHint") is True, (
                    f"Tool must advertise readOnlyHint=true: {name}")
            for name in ("carpinova_generar_borrador", "carpinova_renderizar_lamina",
                         "carpinova_exportar_3d"):
                annotations = catalog[name].annotations
                assert annotations is None or annotations.model_dump(
                    by_alias=True).get("readOnlyHint") is not True, (
                        f"Write-capable tool cannot be marked read-only: {name}")
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
                # An image must travel THROUGH MCP, not merely be written to
                # an unreadable local file path on the server computer.
                image = await session.call_tool(
                    "carpinova_leer_entregable",
                    {"proyecto": project, "archivo": "lamina/three-views.png"},
                )
                assert not image.isError, f"PNG preview MCP failed: {project}: {image}"
                assert len(image.content) == 1
                assert image.content[0].type == "image"
                assert image.content[0].mimeType == "image/png"
                assert base64.b64decode(image.content[0].data) == (
                    output_root / project / "lamina/three-views.png"
                ).read_bytes()
                print("MCP_IMAGE_CONTENT_PASS=" + project)

            # Exercise the B3 opening-intent sidecar through this already-open
            # stdio session, using the real geometry generated above.
            project, request, _ = next(item for item in requests
                                       if item[0] == "cocina_dos_modulos")
            base_cad = await _read_json_via_mcp(
                session, project, "cad-exchange.json",
            )
            base_manifest = await _read_json_via_mcp(
                session, project, "manifest.json",
            )
            assert base_manifest["geometry_sha256"] == base_cad["geometry_sha256"]
            sidecar_input = {
                "schema_version": "1.0",
                "source": "CLIENT_DECLARED_NOT_AUTHENTICATED",
                "geometry_sha256": base_cad["geometry_sha256"],
                "elements": sorted(({
                    "piece_id": box["piece_id"],
                    "module_id": box["module_id"],
                    "element_type": "door",
                    "opening_system": "handle",
                } for box in base_cad["boxes"]
                    if box.get("role") in (
                        "front_left", "front_right", "front_single",
                    )), key=lambda item: item["piece_id"]),
            }
            assert len(sidecar_input["elements"]) > 0
            assert set(sidecar_input) == {
                "schema_version", "source", "geometry_sha256", "elements",
            }
            hardware_project = "cocina_dos_modulos_b4"
            generated_response = await session.call_tool(
                "carpinova_generar_borrador", {
                    "solicitud_json": request,
                    "proyecto": hardware_project,
                    "opening_review_json": json.dumps(
                        sidecar_input, ensure_ascii=False,
                    ),
                },
            )
            generated = _mcp_structured(
                generated_response, "generate B3 opening sidecar",
            )
            assert generated.get("status") == "DRAFT_NOT_FOR_CUTTING"
            assert generated.get("geometry_sha256") == base_cad["geometry_sha256"]
            assert generated.get("piece_count") == base_manifest["piece_count"]
            assert all(generated.get(flag) is False for flag in FLAGS)
            assert "opening-intents-review.json" in generated.get("files", [])
            assert "hardware-reference-review.json" in generated.get("files", [])

            opening_payload = await _read_payload_via_mcp(
                session, hardware_project, "opening-intents-review.json",
            )
            saved_opening = json.loads(opening_payload["contenido"])
            hardware_payload = await _read_payload_via_mcp(
                session, hardware_project, "hardware-reference-review.json",
            )
            saved_hardware = json.loads(hardware_payload["contenido"])
            hardware_manifest = await _read_json_via_mcp(
                session, hardware_project, "manifest.json",
            )
            expected_ids = {item["piece_id"] for item in sidecar_input["elements"]}
            assert "opening-intents-review.json" in hardware_manifest["files"]
            assert "hardware-reference-review.json" in hardware_manifest["files"]
            assert saved_opening["schema_version"] == "1.0"
            assert saved_opening["source"] == "CLIENT_DECLARED_NOT_AUTHENTICATED"
            assert saved_opening["authentication"] == "NOT_AUTHENTICATED"
            assert saved_opening["geometry_sha256"] == base_cad["geometry_sha256"]
            assert saved_opening["status"] == "NOT_APPROVED_NOT_FOR_FABRICATION"
            assert saved_opening["hardware_selected"] is False
            assert {
                tuple(item[key] for key in (
                    "piece_id", "module_id", "element_type", "opening_system",
                )) for item in saved_opening["elements"]
            } == {
                tuple(item[key] for key in (
                    "piece_id", "module_id", "element_type", "opening_system",
                )) for item in sidecar_input["elements"]
            }
            assert {item["piece_id"] for item in saved_opening["elements"]} == expected_ids
            assert {item["opening_system"] for item in saved_opening["elements"]} == {"handle"}
            # MCP readback is authoritative here; corroborate its exact bytes
            # against the manifest's digest and deterministic JSON encoding.
            opening_bytes = opening_payload["contenido"].encode("utf-8")
            assert hashlib.sha256(opening_bytes).hexdigest() == (
                hardware_manifest["opening_intents_review_sha256"]
            )
            assert opening_bytes == (
                json.dumps(saved_opening, indent=2, ensure_ascii=False) + "\n"
            ).encode("utf-8")

            assert saved_hardware["geometry_sha256"] == base_cad["geometry_sha256"]
            assert saved_hardware["status"] == "REFERENCE_ONLY_NOT_SELECTED"
            assert saved_hardware["approval_status"] == "NOT_APPROVED_NOT_FOR_FABRICATION"
            assert saved_hardware["hardware_selected"] is False
            assert all(saved_hardware[flag] is False for flag in FLAGS)
            rows = saved_hardware["elements"]
            assert [row["piece_id"] for row in rows] == sorted(expected_ids)
            assert {row["piece_id"] for row in rows} == expected_ids
            assert {
                tuple(row[key] for key in (
                    "piece_id", "module_id", "element_type", "opening_system",
                )) for row in rows
            } == {
                tuple(item[key] for key in (
                    "piece_id", "module_id", "element_type", "opening_system",
                )) for item in sidecar_input["elements"]
            }
            assert all(row["opening_system"] == "handle" for row in rows)
            assert all(row["status"] == "REFERENCE_ONLY_NOT_SELECTED" for row in rows)
            assert all(row["approval_status"] == "NOT_APPROVED_NOT_FOR_FABRICATION"
                       and row["hardware_selected"] is False
                       and all(row[flag] is False for flag in FLAGS) for row in rows)
            assert hashlib.sha256(
                hardware_payload["contenido"].encode("utf-8")
            ).hexdigest() == hardware_manifest["hardware_reference_review_sha256"]
            assert all(hardware_manifest[flag] is False for flag in FLAGS)
            print("MCP_B3_OPENING_AND_HARDWARE_REFERENCE_PASS=" + hardware_project)

            negative_project = "cocina_dos_modulos_b4_bad"
            invalid_input = json.loads(json.dumps(sidecar_input))
            invalid_input["elements"][0]["piece_id"] = "CARPN-B4-FAKE-ID"
            negative_error = None
            try:
                negative_response = await session.call_tool(
                    "carpinova_generar_borrador", {
                        "solicitud_json": request,
                        "proyecto": negative_project,
                        "opening_review_json": json.dumps(
                            invalid_input, ensure_ascii=False,
                        ),
                    },
                )
            except Exception as exc:
                negative_error = f"exception:{type(exc).__name__}"
            else:
                if getattr(negative_response, "isError",
                           getattr(negative_response, "is_error", False)):
                    negative_error = "response:isError"
            assert negative_error is not None, (
                "MCP accepted an altered opening piece ID instead of rejecting it"
            )
            assert not (output_root / negative_project).exists(), (
                "Rejected sidecar created a valid project directory"
            )
            print("MCP_B3_OPENING_NEGATIVE_PASS=" + negative_error)



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



async def execute_native(root: Path) -> None:
    """Verify real FreeCAD/Blender through MCP, with independent host consent."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from carpinova_agent.native_export import REVIEW_CONFIRMATION, issue_native_approval

    for key in (
        "CARPINOVA_NATIVE_EXECUTION_ENABLED", "CARPINOVA_FREECADCMD",
        "CARPINOVA_BLENDER",
    ):
        if not os.environ.get(key):
            raise ValueError("Host opt-in and native executables required: " + key)
    # Only CI/operator code issues approvals, never a language-model MCP tool.
    # Approvals are separate from the output directory, SHA-bound and single-use.
    with TemporaryDirectory(prefix="carpinova-host-approvals-") as approvals:
        for name, _, _ in verified_requests():
            issue_native_approval(root / name, Path(approvals))
        env = {
            **os.environ, "CARPINOVA_OUTPUT_ROOT": str(root),
            "PYTHONPATH": str(PROJECT_ROOT),
            "CARPINOVA_NATIVE_APPROVAL_DIR": approvals,
        }
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "carpinova_agent.mcp_bridge"], env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {item.name for item in (await session.list_tools()).tools}
                assert names == TOOLS, "MCP native tools mismatch"
                for name, _, _ in verified_requests():
                    result = await session.call_tool(
                        "carpinova_exportar_3d",
                        {"proyecto": name, "confirmacion": REVIEW_CONFIRMATION},
                    )
                    assert not result.isError, f"Native CAD export failed: {name}: {result}"
                    preview = await session.call_tool(
                        "carpinova_leer_entregable",
                        {"proyecto": name, "archivo": "native/presentation.png"},
                    )
                    assert not preview.isError, f"Native preview MCP failed: {name}: {preview}"
                    assert len(preview.content) == 1
                    assert preview.content[0].type == "image"
                    assert preview.content[0].mimeType == "image/png"
                    assert base64.b64decode(preview.content[0].data) == (
                        root / name / "native/presentation.png"
                    ).read_bytes()
                    print("MCP_NATIVE_IMAGE_CONTENT_PASS=" + name)



def validate_native(root: Path) -> list[dict]:
    """Proof from native CAD reports, actual files and canonical SHA/part IDs."""
    from zipfile import ZipFile
    results = []
    for name, _, count in verified_requests():
        folder = root / name
        cad = validate_exchange(json.loads(
            (folder / "cad-exchange.json").read_text(encoding="utf-8")
        ))
        manifest = json.loads(
            (folder / "native" / "native-manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["piece_count"] == count == len(cad["boxes"])
        assert manifest["geometry_sha256"] == cad["geometry_sha256"]
        assert manifest["status"] == "NATIVE_PREVIEW_NOT_FOR_CUTTING"
        assert all(manifest[k] is False for k in FLAGS)
        assert set(manifest["reports"]) == {"FreeCAD", "Blender", "BlenderPresentation"}
        for report in manifest["reports"].values():
            assert report["geometry_sha256"] == cad["geometry_sha256"]
            assert report["verified_piece_count"] == count
            assert report["status"] == "NATIVE_GEOMETRY_MATCH"
            assert report["max_abs_error_mm"] <= 0.05
        with ZipFile(folder / "native" / "native.FCStd") as z:
            assert z.testzip() is None and "Document.xml" in z.namelist()
        for suffix in ("native.blend", "presentation.blend"):
            assert (folder / "native" / suffix).read_bytes()[:7] == b"BLENDER"
        assert (folder / "native" / "presentation.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        print("MCP_NATIVE_CAD_PASS=" + name + "; PIECES=" + str(count))
        results.append({
            "project": name, "geometry_sha256": cad["geometry_sha256"],
            "pieces": count, "four_release_flags": False,
        })
    (root / "native-preflight-report.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print("MCP_NATIVE_FREECAD_BLENDER=PASS; FABRICATION_AUTHORITY=NO")
    return results

def main() -> int:
    parser = argparse.ArgumentParser(description="CarpiNova MCP local preflight, no fabrication.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--native-only", action="store_true",
                        help="Only native export of existing projects; opt-in apps required")
    options = parser.parse_args()
    root = options.output_root.expanduser().resolve()
    if not root.is_absolute():
        raise ValueError("Output folder must be absolute.")
    if options.native_only:
        if not root.is_dir():
            raise ValueError("Native export requires an existing review output directory.")
        asyncio.run(execute_native(root))
        validate_native(root)
        return 0
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
    print("REAL_MCP_STDIO=PASS; SIX_TOOLS=PASS")
    print("THREE_VIEWS_SVG_PNG_PDF=PASS")
    print("FABRICATION_AUTHORITY=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
