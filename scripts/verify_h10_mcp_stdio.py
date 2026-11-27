"""One-shot H10-M4 stdio integration check; never retries a dispatched call."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from datetime import timedelta
from typing import Any
from zipfile import ZipFile

from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "H10_M4_MCP_FRANCES"
SOURCE_SIZE = 4593
SOURCE_SHA256 = "f875b5f78ef47f1176d188b1dd0c6fa8c345a8da9bdd49d2abd88a33f516db4c"
LAYOUT_SHA256 = "757c8665b48ec374b0163f6bb2e1906e93f98f544982bd01dedc09846979ea44"
FIXATION_SHA256 = "f2e521a9950971f238263d892e1c84be34a9bf113b1266e3711e426c435ece49"
TOOLS = {
    "carpinova_estado", "carpinova_consultar", "carpinova_generar_borrador",
    "carpinova_renderizar_lamina", "carpinova_exportar_3d", "carpinova_leer_entregable",
}
FILES = {
    "LEER_PRIMERO.txt", "01-visor-3d.html", "02-planta.svg", "03-seccion.svg",
    "04-habitacion.json", "05-solicitud.json", "06-paneles-en-escena.csv",
}
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready", "can_generate_f7c")
WINDOWS_ENV = ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP")


class T1Failure(RuntimeError):
    pass


def _json_object(text: str) -> dict[str, Any]:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    def no_constant(value):
        raise ValueError(f"non-finite JSON value: {value}")

    result = json.loads(text, object_pairs_hook=unique, parse_constant=no_constant)
    if type(result) is not dict:
        raise ValueError("se esperaba un objeto JSON")
    return result


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    temporary.replace(path)


def _linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _real_directory(path: Path, name: str, *, empty: bool) -> Path:
    if not path.is_absolute() or _linked(path) or not path.is_dir():
        raise T1Failure(f"{name} debe ser un directorio absoluto, real y existente")
    resolved = path.resolve(strict=True)
    if os.path.normcase(str(resolved)) != os.path.normcase(str(path)):
        raise T1Failure(f"{name} resuelve fuera de su ruta declarada")
    if empty and any(path.iterdir()):
        raise T1Failure(f"{name} debe estar vacío; se conserva el contenido existente")
    return resolved


def _under(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(parent.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _load_helpers():
    helper = ROOT / "scripts" / "verify_f11_stdio_f10.py"
    spec = importlib.util.spec_from_file_location("carpinova_verify_f11_stdio_helpers", helper)
    if spec is None or spec.loader is None:
        raise T1Failure("No se pudo importar el helper histórico _schema/_decode.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._schema, module._decode


def _record(path: Path, state: dict[str, Any], phase: str, status: str, **fields: Any) -> None:
    state["phase"] = phase
    state["phase_status"] = status
    state.setdefault("history", []).append({"phase": phase, "status": status, **fields})
    _write_json(path, state)


def _plain_response(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(by_alias=True, mode="json")
    content = []
    for block in getattr(response, "content", []) or []:
        if hasattr(block, "model_dump"):
            content.append(block.model_dump(by_alias=True, mode="json"))
        else:
            content.append({"type": getattr(block, "type", None),
                            "text": getattr(block, "text", None)})
    return {
        "isError": getattr(response, "isError", getattr(response, "is_error", False)),
        "structuredContent": getattr(response, "structuredContent",
                                      getattr(response, "structured_content", None)),
        "content": content,
    }


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise T1Failure(message)


def _false_flags(value: dict[str, Any], owner: str) -> None:
    for key in FLAGS:
        _need(type(value.get(key)) is bool and value[key] is False,
              f"{owner}.{key} no es boolean false")


def _validate_product(result: dict[str, Any], source_request: dict[str, Any],
                      output: Path) -> dict[str, Any]:
    _need(result.get("status") == "REVIEW_ONLY", "respuesta status no es REVIEW_ONLY")
    _need(result.get("release") == "NO_GO", "respuesta release no es NO_GO")
    _need(result.get("room_status") == "REVIEW_ONLY", "room_status no es REVIEW_ONLY")
    _need(result.get("proyecto") == PROJECT, "proyecto MCP no coincide")
    _need(type(result.get("piece_count")) is int and result["piece_count"] == 45,
          "respuesta piece_count no es 45")
    _need(type(result.get("section_y_mm")) is int and result["section_y_mm"] == 350,
          "respuesta section_y_mm no es 350")
    _false_flags(result, "respuesta")
    _need(result.get("layout_sha256") == LAYOUT_SHA256, "layout SHA de respuesta distinto")
    _need(result.get("wall_fixation_sha256") == FIXATION_SHA256,
          "wall_fixation SHA de respuesta distinto")
    _need(re.fullmatch(r"[0-9a-f]{64}", result.get("zip_sha256", "")) is not None,
          "respuesta zip_sha256 inválido")
    files = result.get("files")
    _need(type(files) is list and all(type(name) is str for name in files)
          and len(files) == 7 and len(set(files)) == 7 and set(files) == FILES,
          "respuesta files no contiene exactamente los siete miembros declarados")
    warnings = result.get("warnings")
    _need(type(warnings) is list and all(type(w) is str for w in warnings),
          "warnings no es lista de texto")
    _need(any(w.startswith("LOCAL_PATH_NOT_BINARY_MCP") for w in warnings),
          "falta advertencia LOCAL_PATH_NOT_BINARY_MCP")
    _need(any(w.startswith("EDITOR_LOCAL") for w in warnings), "falta instrucción EDITOR_LOCAL")

    expected = output / f"{PROJECT}-room-review.zip"
    supplied = result.get("room_package_path")
    _need(type(supplied) is str, "room_package_path no es texto")
    product = Path(supplied)
    _need(not _linked(product) and product.is_file(), "ZIP de producto falta o es enlace")
    actual_path = product.resolve(strict=True)
    _need(os.path.normcase(str(actual_path)) == os.path.normcase(str(expected.resolve(strict=True))),
          "room_package_path no coincide con la salida T1 esperada")
    _need(not _linked(output) and actual_path.parent == output.resolve(strict=True),
          "ZIP no es hijo directo real de output-root")
    _need(sorted(p.name for p in output.iterdir()) == [expected.name],
          "output-root debe contener solo el ZIP producto")
    zip_bytes = product.read_bytes()
    zip_sha = hashlib.sha256(zip_bytes).hexdigest()
    _need(zip_sha == result["zip_sha256"], "SHA de bytes ZIP no coincide con respuesta")

    with ZipFile(product) as archive:
        _need(archive.testzip() is None, "CRC del D19 no pasa")
        names = archive.namelist()
        _need(len(names) == 8 and len(set(names)) == 8,
              "D19 no tiene exactamente ocho nombres únicos")
        _need(set(names) == FILES | {"MANIFEST.json"}, "miembros D19 inesperados")
        for name in names:
            path = PurePosixPath(name)
            _need(not path.is_absolute() and ".." not in path.parts and "\\" not in name,
                  f"ruta inválida en ZIP: {name}")
        members = {name: archive.read(name) for name in names}
    manifest = _json_object(members["MANIFEST.json"].decode("utf-8", errors="strict"))
    _need(manifest.get("release") == "NO_GO", "manifest release no es NO_GO")
    _need(manifest.get("room_status") == "REVIEW_ONLY", "manifest room_status distinto")
    _need(type(manifest.get("section_y_mm")) is int and manifest["section_y_mm"] == 350,
          "manifest section_y_mm distinto")
    _need(type(manifest.get("piece_count")) is int and manifest["piece_count"] == 45,
          "manifest piece_count distinto")
    for key, expected_hash in (("layout_sha256", LAYOUT_SHA256),
                               ("wall_fixation_sha256", FIXATION_SHA256)):
        _need(manifest.get(key) == expected_hash and result.get(key) == expected_hash,
              f"{key} no coincide con el SHA esperado")
    listed = manifest.get("files")
    _need(type(listed) is dict and set(listed) == FILES,
          "MANIFEST.files no contiene los siete miembros esperados")
    for name, data in members.items():
        if name == "MANIFEST.json":
            continue
        record = listed[name]
        _need(type(record) is dict and type(record.get("bytes")) is int
              and record.get("bytes") == len(data)
              and record.get("sha256") == hashlib.sha256(data).hexdigest(),
              f"MANIFEST hash/tamaño no coincide: {name}")

    review = _json_object(members["04-habitacion.json"].decode("utf-8", errors="strict"))
    _need(review.get("status") == "REVIEW_ONLY" and review.get("release") == "NO_GO",
          "04-habitacion status/release no son de revisión")
    _false_flags(review, "04-habitacion")
    _need(review.get("piece_count") == 45 and review.get("layout_sha256") == LAYOUT_SHA256,
          "04-habitacion piece_count/layout SHA distinto")
    _need(review.get("wall_fixation_sha256") == FIXATION_SHA256,
          "04-habitacion wall_fixation SHA distinto")
    boxes = review.get("world_boxes")
    ids = review.get("global_piece_ids")
    _need(type(boxes) is list and len(boxes) == 45, "world_boxes no contiene 45 piezas")
    _need(type(ids) is list and all(type(piece_id) is str for piece_id in ids)
          and len(ids) == 45 and len(set(ids)) == 45,
          "global_piece_ids no son 45 IDs únicos")
    _need(all(type(box) is dict and type(box.get("piece_id")) is str for box in boxes),
          "world_boxes contiene piezas con esquema inválido")
    box_ids = [box.get("piece_id") for box in boxes]
    _need(len(set(box_ids)) == 45 and set(box_ids) == set(ids),
          "world_boxes y global_piece_ids no coinciden")
    for key in ("envelope_collisions", "panel_collisions", "support_collisions", "manufacturing_holes"):
        _need(review.get(key) == [], f"{key} no está vacío")
    fixation = review.get("wall_fixation_geometry")
    _need(type(fixation) is list and len(fixation) == 1,
          "wall_fixation_geometry debe contener una entrada")
    item = fixation[0]
    _need((item.get("group_id"), item.get("module_id"), item.get("system"))
          == ("ALTO", "KITCHEN_1", "french_cleat_45"),
          "la fijación francesa no corresponde a ALTO/KITCHEN_1")
    _need(type(item.get("install_ready")) is bool and item["install_ready"] is False,
          "install_ready de fijación no es boolean false")
    profiles = item.get("profiles")
    _need(type(profiles) is list and all(type(profile) is dict for profile in profiles)
          and len(profiles) == 2
          and {p.get("role") for p in profiles}
          == {"french_cleat_cabinet", "french_cleat_wall"},
          "perfiles franceses no contienen exactamente sus dos roles")

    csv_rows = list(csv.DictReader(members["06-paneles-en-escena.csv"].decode("utf-8").splitlines()))
    csv_ids = [row.get("piece_id") for row in csv_rows]
    _need(len(csv_rows) == 45 and len(set(csv_ids)) == 45 and set(csv_ids) == set(ids),
          "CSV no coincide con los 45 IDs únicos del review")
    _need(all(row.get("NOT_FOR_CUTTING") == "TRUE" for row in csv_rows),
          "CSV tiene una fila sin NOT_FOR_CUTTING=TRUE")
    returned_request = _json_object(members["05-solicitud.json"].decode("utf-8", errors="strict"))
    _need(returned_request == source_request, "05-solicitud no coincide con el JSON de entrada")
    html = members["01-visor-3d.html"]
    _need(b"window.CARPNOVA_EDITOR_SESSION={" not in html,
          "el HTML offline contiene una inyección de sesión")

    return {
        "project": PROJECT,
        "status": result["status"],
        "release": result["release"],
        "room_status": result["room_status"],
        "piece_count": result["piece_count"],
        "section_y_mm": result["section_y_mm"],
        "zip_sha256": zip_sha,
        "layout_sha256": LAYOUT_SHA256,
        "wall_fixation_sha256": FIXATION_SHA256,
        "members": 8,
        "manifest_files": 7,
        "profile_roles": sorted(p["role"] for p in profiles),
        "fabrication_flags_false": list(FLAGS),
        "install_ready": False,
    }


async def _run_t1(args: argparse.Namespace, source_text: str, source_request: dict[str, Any],
                  state: dict[str, Any], phase_file: Path) -> dict[str, Any]:
    runtime = _json_object((ROOT / "work" / "mcp-runtime" / "runtime.json").read_text(encoding="utf-8"))
    _need(runtime.get("status") == "READY", "runtime.json no está READY")
    expected_python = Path(runtime["python_exe"]).resolve(strict=True)
    _need(Path(sys.executable).resolve(strict=True) == expected_python,
          "el verificador no corre con el Python del TOML/runtime.json")
    _need(Path(sys.prefix).resolve(strict=True) == Path(runtime["venv"]).resolve(strict=True),
          "sys.prefix no corresponde al venv validado")
    _need(Path(runtime["repo"]).resolve(strict=True) == ROOT,
          "runtime.json apunta a otro checkout")
    import mcp
    _need(Path(mcp.__file__).resolve(strict=True).is_relative_to(Path(sys.prefix).resolve(strict=True)),
          "el SDK MCP no proviene del venv local")
    source_bytes = source_text.encode("utf-8")
    _need(len(source_bytes) == SOURCE_SIZE and hashlib.sha256(source_bytes).hexdigest() == SOURCE_SHA256,
          "source JSON cambió después del preflight")

    child_env = {}
    for key in WINDOWS_ENV:
        value = os.environ.get(key)
        _need(bool(value), f"falta variable Windows requerida {key}")
        child_env[key] = value
    child_env.update({
        "PYTHONPATH": str(ROOT),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CARPINOVA_OUTPUT_ROOT": str(Path(args.output_root).resolve(strict=True)),
        "CARPINOVA_NATIVE_EXECUTION_ENABLED": "0",
    })
    _need("CARPINOVA_NATIVE_APPROVAL_DIR" not in child_env,
          "el hijo no debe recibir directorio de aprobaciones")
    state["runtime"] = {
        "python_exe": str(expected_python),
        "python_version": runtime["python_version"],
        "versions": runtime["versions"],
        "requirements_sha256": runtime["requirements_sha256"],
        "method": runtime["method"],
        "mcp_module_path": str(Path(mcp.__file__).resolve(strict=True)),
        "cwd": str(ROOT),
        "child_env_keys": sorted(child_env),
        "native_execution_enabled": "0",
        "approval_dir_in_child": False,
    }
    _record(phase_file, state, "PREFLIGHT_READY", "PASS")

    helper_schema, helper_decode = _load_helpers()
    parameters = StdioServerParameters(
        command=str(expected_python),
        args=["-m", "carpinova_agent.mcp_bridge"],
        env=child_env,
        cwd=str(ROOT),
        encoding="utf-8",
        encoding_error_handler="strict",
    )
    tools_path = args.evidence_dir / "T1_TOOLS_AND_SCHEMAS.json"
    response_raw_path = args.evidence_dir / "T1_RESPONSE_RAW.json"
    response_decoded_path = args.evidence_dir / "T1_RESPONSE_DECODED.json"
    stderr_path = args.evidence_dir / "T1_MCP_SERVER.stderr.log"
    args_hash = hashlib.sha256(json.dumps({
        "solicitud_json": source_text,
        "proyecto": PROJECT,
        "incluir_planos": False,
        "seccion_y_mm": 350,
    }, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    call_args = {
        "solicitud_json": source_text,
        "proyecto": PROJECT,
        "incluir_planos": False,
        "seccion_y_mm": 350,
    }

    async with asyncio.timeout(180):
        with stderr_path.open("w", encoding="utf-8", newline="\n") as server_log:
            async with AsyncExitStack() as stack:
                _record(phase_file, state, "STDIO_START", "IN_PROGRESS")
                async with asyncio.timeout(30):
                    read_stream, write_stream = await stack.enter_async_context(
                        stdio_client(parameters, errlog=server_log))
                _record(phase_file, state, "STDIO_STARTED", "PASS")
                async with ClientSession(read_stream, write_stream) as session:
                    _record(phase_file, state, "INITIALIZE", "IN_PROGRESS")
                    async with asyncio.timeout(30):
                        await session.initialize()
                    _record(phase_file, state, "INITIALIZE", "PASS")

                    listed = []
                    seen_cursors = set()
                    cursor = None
                    while True:
                        _record(phase_file, state, "LIST_TOOLS", "IN_PROGRESS",
                                page=len(listed) // 6 + 1)
                        async with asyncio.timeout(30):
                            page = await session.list_tools(cursor=cursor)
                        listed.extend(list(getattr(page, "tools", []) or []))
                        cursor = getattr(page, "nextCursor", None) or getattr(page, "next_cursor", None)
                        if not cursor:
                            break
                        _need(cursor not in seen_cursors, "cursor repetido en tools/list")
                        seen_cursors.add(cursor)
                    names = [getattr(item, "name", None) for item in listed]
                    _need(len(names) == 6 and len(set(names)) == 6 and set(names) == TOOLS,
                          f"lista MCP no es exactamente las seis tools requeridas: {names}")
                    schemas = {}
                    for item in listed:
                        name, schema = helper_schema(item)
                        Draft202012Validator.check_schema(schema)
                        schemas[name] = schema
                    generate_schema = schemas["carpinova_generar_borrador"]
                    validate_args = {
                        "solicitud_json": source_text,
                        "proyecto": PROJECT,
                        "incluir_planos": False,
                        "seccion_y_mm": 350,
                    }
                    Draft202012Validator(generate_schema).validate(validate_args)
                    _need(type(validate_args["incluir_planos"]) is bool
                          and validate_args["incluir_planos"] is False,
                          "incluir_planos debe ser boolean false")
                    _need(type(validate_args["seccion_y_mm"]) is int
                          and validate_args["seccion_y_mm"] == 350,
                          "seccion_y_mm debe ser integer 350")
                    _write_json(tools_path, {
                        "count": len(names), "tools": sorted(names),
                        "schemas": schemas,
                    })
                    state["tools_discovered"] = sorted(names)
                    _record(phase_file, state, "LIST_TOOLS", "PASS", count=6)

                    state["call"] = {
                        "tool": "carpinova_generar_borrador",
                        "project": PROJECT,
                        "incluir_planos": False,
                        "section_y_mm": 350,
                        "source_json_bytes": SOURCE_SIZE,
                        "arguments_sha256": args_hash,
                    }
                    _record(phase_file, state, "CALL_DISPATCHED", "IN_PROGRESS")
                    response = await session.call_tool(
                        "carpinova_generar_borrador", call_args,
                        read_timeout_seconds=timedelta(seconds=90),
                    )
                    state["productive_tool_calls"] = 1
                    _write_json(response_raw_path, _plain_response(response))
                    _record(phase_file, state, "RESPONSE_CAPTURED", "PASS")
                    result, result_source = helper_decode(response)
                    _write_json(response_decoded_path, {
                        "result_source": result_source,
                        "result": result,
                    })
                    _record(phase_file, state, "RESPONSE_DECODED", "PASS",
                            result_source=result_source)
                    product_summary = _validate_product(result, source_request,
                                                        Path(args.output_root).resolve(strict=True))
                    extracted = args.evidence_dir / "D19_MCP"
                    extracted.mkdir(exist_ok=False)
                    with ZipFile(Path(result["room_package_path"])) as archive:
                        for name in archive.namelist():
                            (extracted / name).write_bytes(archive.read(name))
                    _need(len(list(extracted.iterdir())) == 8,
                          "la evidencia D19_MCP no contiene ocho miembros extraídos")
                    product_summary["extracted_members"] = 8
                    record_summary = dict(product_summary)
                    record_summary["product_status"] = record_summary.pop("status")
                    _record(phase_file, state, "PRODUCT_VALIDATION", "PASS", **record_summary)
                    state["status"] = "PASS_SCOPED"
                    state["productive_tool_calls"] = 1
                    _record(phase_file, state, "T1_TERMINAL", "PASS_SCOPED")
                    return {"status": "PASS_SCOPED", **product_summary,
                            "result_source": result_source,
                            "tools": sorted(names), "arguments_sha256": args_hash}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run exactly one H10-M4 CarpiNova stdio product call")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    phase_file = None
    state: dict[str, Any] = {"task": "CARPN_H10_M4_V2", "status": "PREFLIGHT"}
    dispatched = False
    try:
        input_path = args.input
        _need(input_path.is_absolute() and not _linked(input_path) and input_path.is_file(),
              "--input debe ser un archivo JSON absoluto, real y existente")
        input_path = input_path.resolve(strict=True)
        output = _real_directory(args.output_root, "output-root", empty=True)
        evidence = _real_directory(args.evidence_dir, "evidence-dir", empty=True)
        _need(output != evidence, "output-root y evidence-dir deben ser distintos")
        _need(not _under(output, evidence) and not _under(evidence, output),
              "output-root y evidence-dir no pueden solaparse")
        _need(not _under(output, ROOT) and not _under(evidence, ROOT),
              "output-root y evidence-dir deben permanecer fuera del repositorio")
        _need(not _under(input_path, output) and not _under(input_path, evidence),
              "input no puede estar dentro de output-root/evidence-dir")
        raw = input_path.read_bytes()
        _need(len(raw) == SOURCE_SIZE and hashlib.sha256(raw).hexdigest() == SOURCE_SHA256,
              "input no coincide con el D19 M3 validado")
        source_text = raw.decode("utf-8", errors="strict")
        source_request = _json_object(source_text)
        phase_file = evidence / "T1_PHASES.json"
        state.update({
            "status": "PREFLIGHT_PASS",
            "base_actual": "c205e194bc9bcae899f2cbc916f3057e7ea82707",
            "input_sha256": SOURCE_SHA256,
            "input_bytes": SOURCE_SIZE,
            "output_root": str(output),
            "evidence_dir": str(evidence),
            "native_execution_enabled": "0",
            "authorization_directory_configured": False,
            "productive_tool_calls": 0,
            "history": [{"phase": "PREFLIGHT", "status": "PASS"}],
        })
        _write_json(phase_file, state)
        summary = asyncio.run(_run_t1(args, source_text, source_request, state, phase_file))
        _write_json(evidence / "T1_RESULT.json", summary)
        print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
        return 0
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            reason = "interrumpido por el operador"
        elif isinstance(exc, asyncio.TimeoutError):
            reason = "timeout MCP"
        else:
            reason = f"{type(exc).__name__}: {str(exc)[:1200]}"
        if phase_file is not None:
            current = state.get("phase")
            was_dispatched = current == "CALL_DISPATCHED" or any(
                row.get("phase") == "CALL_DISPATCHED" for row in state.get("history", []))
            response_captured = any(
                row.get("phase") == "RESPONSE_CAPTURED" and row.get("status") == "PASS"
                for row in state.get("history", []))
            state["status"] = (
                "FAIL_PRODUCT" if response_captured and isinstance(exc, (T1Failure, AssertionError))
                else "PARTIAL_RESPONSE_CAPTURE" if was_dispatched
                else "FAIL_PRODUCT" if isinstance(exc, (T1Failure, AssertionError))
                else "BLOCKED_ENV"
            )
            state["error"] = reason
            if was_dispatched:
                expected = Path(args.output_root) / f"{PROJECT}-room-review.zip"
                state["expected_product_exists_after_dispatch"] = expected.is_file()
                state["retry_permitted"] = False
            _record(phase_file, state, "T1_TERMINAL", state["status"])
            _write_json(args.evidence_dir / "T1_RESULT.json", {
                "status": state["status"], "error": reason,
                "productive_tool_calls": state.get("productive_tool_calls", 0),
                "retry_permitted": False if was_dispatched else None,
            })
        print(f"T1={state.get('status', 'BLOCKED_ENV')} · {reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
