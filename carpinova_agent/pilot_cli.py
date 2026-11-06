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
from .conversation_flow import validate_flow_review
from .core import DesignError
from .wall_bar_delivery import review_files
from .maestro import MaestroError, consult_maestro
from .modular_outputs import modular_bom_csv, modular_front_svg
from knowledge_client.reader import BundleError, load_bundle

_BLOCKED_FLAGS = ("fabrication_ready", "cutting_ready",
                  "drilling_ready", "purchase_ready")
_FILES = ("maestro-review.json", "front-review.svg",
          "parts-review.csv", "cad-exchange.json", "manifest.json")
_MAX_MANIFEST_BYTES = 65536
_MAX_BOOK_REQUEST_BYTES = 32768


class PilotError(ValueError):
    """An unapproved or inconsistent proposal cannot yield a pilot bundle."""


class BookEvidenceError(PilotError):
    """A book-backed proposal cannot be generated or verified safely."""


def _book_bundle(bundle_dir: Path | str | None) -> dict[str, Any]:
    if bundle_dir is None:
        raise BookEvidenceError(
            "BLOCKED_BOOK_BUNDLE: configurar el bundle Knowledge para esta consulta."
        )
    try:
        bundle = load_bundle(bundle_dir)
    except (BundleError, OSError, TypeError, ValueError) as exc:
        raise BookEvidenceError(
            "BLOCKED_BOOK_BUNDLE: el bundle Knowledge falta o no es válido."
        ) from exc
    manifest = bundle["manifest"]
    if (bundle.get("coverage") != "FULL_BOOK"
            or manifest.get("scope") != "BOOK"
            or manifest.get("knowledge_version") != "1.2.0"
            or manifest.get("schema_version") != "0.1.0"
            or manifest.get("counts", {}).get("pages") != 252
            or manifest.get("source_page_count") != 295
            or manifest.get("excluded_page_count") != 43):
        raise BookEvidenceError(
            "BOOK_SCOPE_NOT_FULL: se requiere Knowledge BOOK 1.2.0 completo."
        )
    return bundle


def _book_source_request(request: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = json.dumps(request, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":"))
        round_trip = json.loads(raw)
    except (TypeError, ValueError, RecursionError) as exc:
        raise BookEvidenceError(
            "BOOK_SOURCE_REQUEST_INVALID: la solicitud no es JSON reproducible."
        ) from exc
    if round_trip != request:
        raise BookEvidenceError(
            "BOOK_SOURCE_REQUEST_INVALID: la solicitud cambia al serializarla."
        )
    if len(raw.encode("utf-8")) > _MAX_BOOK_REQUEST_BYTES:
        raise BookEvidenceError(
            "BOOK_SOURCE_REQUEST_TOO_LARGE: solicitud bibliográfica mayor de 32 KiB."
        )
    return round_trip


def _book_source_metadata(bundle: dict[str, Any]) -> dict[str, Any]:
    manifest = bundle["manifest"]
    return {
        "book_id": manifest["book_id"],
        "scope": manifest["scope"],
        "knowledge_version": manifest["knowledge_version"],
        "schema_version": manifest["schema_version"],
        "source_manifest_sha256": manifest["source_manifest_sha256"],
        "counts": manifest["counts"],
        "source_page_count": manifest["source_page_count"],
        "excluded_page_count": manifest["excluded_page_count"],
        "files": manifest["files"],
        "source_pdf_bytes_verified": bundle["source_pdf_bytes_verified"],
        "provenance_note": bundle["provenance_note"],
    }


def _book_source_status(answer: dict[str, Any]) -> str:
    knowledge = answer.get("knowledge")
    provenance = answer.get("source_provenance")
    if (not isinstance(knowledge, dict)
            or knowledge.get("coverage") != "FULL_BOOK"
            or knowledge.get("knowledge_version") != "1.2.0"
            or not isinstance(knowledge.get("results"), list)
            or not isinstance(provenance, list)):
        raise BookEvidenceError(
            "BLOCKED_BOOK_BUNDLE: Maestro no devolvió evidencia FULL_BOOK coherente."
        )
    if knowledge.get("total_matches") == 0:
        if knowledge["results"] or provenance:
            raise BookEvidenceError("NO_BOOK_MATCH inconsistente con las referencias.")
        return "NO_BOOK_MATCH"
    if not knowledge["results"] or len(provenance) != len(knowledge["results"]):
        raise BookEvidenceError("La procedencia del libro no coincide con resultados.")
    return "BOOK_EVIDENCE_PASS"


def pilot_review(
    request: dict[str, Any], flow_review: dict[str, Any] | None = None,
    *, bundle_dir: Path | str | None = None,
) -> dict[str, str]:
    """Calculate every deliverable from one already-structured Maestro request.

    A text-only proposal or an LLM classification is NOT sufficient input.
    All downstream derivations share Maestro's one modular geometry object.
    """
    if type(request) is not dict or request.get("action") != "modular":
        raise PilotError("Piloto: se requiere action=modular con module_spec explícito.")
    has_query = "query" in request
    if has_query and flow_review is not None:
        raise BookEvidenceError(
            "BOOK_FLOW_COMBINATION_UNSUPPORTED: separar consulta del libro y flow-review."
        )
    source_request = _book_source_request(request) if has_query else None
    book = _book_bundle(bundle_dir) if has_query else None
    answer = consult_maestro(request, bundle_dir=bundle_dir)
    book_status = _book_source_status(answer) if has_query else None
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
    if flow_review is not None:
        if type(flow_review) is not dict:
            raise PilotError("flow-review debe ser un objeto de revisión válido.")
        try:
            validate_flow_review(flow_review, request)
        except (MaestroError, DesignError, ValueError) as exc:
            raise PilotError("Traza conversacional inválida o distinta de Maestro.") from exc
        if (flow_review.get("geometry_sha256") != exchange["geometry_sha256"]
                or flow_review.get("piece_count") != len(exchange["boxes"])):
            raise PilotError("Traza conversacional no corresponde al CAD del borrador.")
    extras = review_files(model) if model.get("wall_bar_review") else {}
    trace_files = ["flow-review.json"] if flow_review is not None else []
    manifest = {
        "schema_version": "1.0",
        "status": "DRAFT_NOT_FOR_CUTTING",
        "source": "MAESTRO_MODULAR_F1_F7C",
        "piece_count": len(model["parts"]),
        "geometry_sha256": exchange["geometry_sha256"],
        "files": list(_FILES) + trace_files + list(extras),
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
    if has_query:
        manifest.update({
            "book_source_request": source_request,
            "book_source_metadata": _book_source_metadata(book),
            "book_source_status": book_status,
        })
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    if has_query and len(manifest_text.encode("utf-8")) > _MAX_MANIFEST_BYTES:
        raise BookEvidenceError(
            "BOOK_SOURCE_REQUEST_TOO_LARGE: vínculo excede el límite de 65.536 bytes."
        )
    flow_text = (json.dumps(flow_review, indent=2, ensure_ascii=False) + "\n"
                 if flow_review is not None else None)
    if flow_text is not None and len(flow_text.encode("utf-8")) > 262144:
        raise PilotError("La traza conversacional excede 256 KiB.")
    return {
        "maestro-review.json": json.dumps(answer, indent=2, ensure_ascii=False) + "\n",
        "front-review.svg": svg,
        "parts-review.csv": csv_text,
        "cad-exchange.json": json.dumps(exchange, indent=2, ensure_ascii=False) + "\n",
        "manifest.json": manifest_text,
        **extras,
        **({"flow-review.json": flow_text} if flow_text is not None else {}),
    }


def write_pilot_bundle(
    request: dict[str, Any], output_dir: Path,
    flow_review: dict[str, Any] | None = None,
    *, bundle_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Fail closed: stage complete files on the same filesystem before rename.

    Requires a new directory. Never overwrite prior review or source files.
    """
    if output_dir.exists() or output_dir.is_symlink():
        raise PilotError("Salida existente: elija un directorio nuevo sin sobrescribir.")
    parent = output_dir.parent
    if not parent.is_dir():
        raise PilotError("El directorio padre de salida debe existir.")
    bundle = pilot_review(request, flow_review=flow_review, bundle_dir=bundle_dir)
    with TemporaryDirectory(prefix=".carpinova-pilot-", dir=parent) as temp:
        staging = Path(temp) / "review"
        staging.mkdir()
        for name, content in bundle.items():
            (staging / name).write_bytes(content.encode("utf-8"))
        if output_dir.exists() or output_dir.is_symlink():
            raise PilotError("Otra ejecución creó la salida; no se sobrescribe.")
        # Rename a complete directory within the same filesystem.
        os.rename(staging, output_dir)
    return json.loads(bundle["manifest.json"])



def verify_pilot_bundle(
    project_folder: Path, *, bundle_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Verify all five immutable review artifacts against ONE Maestro model.

    The CAD digest alone is NOT provenance: it is an unkeyed checksum that
    could be recomputed after editing a box. Re-derive the original CAD, CSV
    and SVG from the recorded Maestro model and reject partial changes.
    Always return the original, strictly validated CADExchange.
    """
    folder = Path(project_folder)
    limits = {
        "maestro-review.json": 1048576,
        "front-review.svg": 1048576,
        "parts-review.csv": 1048576,
        "cad-exchange.json": 262144,
        "manifest.json": _MAX_MANIFEST_BYTES,
        "flow-review.json": 262144,
    }
    if not folder.is_dir() or folder.is_symlink():
        raise PilotError("El directorio del proyecto original no es confiable.")
    contents: dict[str, str] = {}
    for filename in _FILES:
        max_bytes = limits[filename]
        file = folder / filename
        if not file.is_file() or file.is_symlink() or file.stat().st_size > max_bytes:
            raise PilotError("Archivo original faltante, enlazado o excesivo: " + filename)
        try:
            contents[filename] = file.read_bytes().decode("utf-8")
        except UnicodeError as exc:
            raise PilotError("Archivo de revisión no es UTF-8 válido: " + filename) from exc
    try:
        answer = json.loads(contents["maestro-review.json"])
        manifest = json.loads(contents["manifest.json"])
        saved_cad = json.loads(contents["cad-exchange.json"])
    except (ValueError, TypeError) as exc:
        raise PilotError("Archivos JSON de revisión inválidos.") from exc
    if not isinstance(answer, dict) or not isinstance(manifest, dict):
        raise PilotError("No existe respuesta de Maestro o manifiesto de revisión válido.")
    has_answer_book_data = (
        answer.get("knowledge") is not None
        or bool(answer.get("source_provenance"))
    )
    book_markers = {
        "book_source_request", "book_source_metadata", "book_source_status",
    }
    has_manifest_book_data = any(key in manifest for key in book_markers)
    if has_answer_book_data or has_manifest_book_data:
        if not all(key in manifest for key in book_markers) or not has_answer_book_data:
            raise BookEvidenceError(
                "BOOK_EVIDENCE_BINDING_INCOMPLETE: falta vínculo bidireccional."
            )
        source_request = manifest.get("book_source_request")
        if type(source_request) is not dict or "query" not in source_request:
            raise BookEvidenceError(
                "BOOK_EVIDENCE_BINDING_INCOMPLETE: falta solicitud original."
            )
        if "flow-review.json" in manifest.get("files", []):
            raise BookEvidenceError(
                "BOOK_FLOW_COMBINATION_UNSUPPORTED: paquete con libro y flow-review."
            )
        source_request = _book_source_request(source_request)
        bundle = _book_bundle(bundle_dir)
        expected_metadata = _book_source_metadata(bundle)
        if manifest.get("book_source_metadata") != expected_metadata:
            raise BookEvidenceError(
                "BOOK_BUNDLE_METADATA_MISMATCH: cambió el alcance o la procedencia declarada."
            )
        expected_status = _book_source_status(answer)
        if manifest.get("book_source_status") != expected_status:
            raise BookEvidenceError("BOOK_SOURCE_STATUS_MISMATCH.")
        try:
            replayed_answer = consult_maestro(source_request, bundle_dir=bundle_dir)
        except (MaestroError, BundleError, OSError, ValueError) as exc:
            raise BookEvidenceError(
                "BOOK_REPLAY_FAILED: no se pudo recalcular Maestro con el bundle."
            ) from exc
        if replayed_answer != answer:
            raise BookEvidenceError(
                "BOOK_REPLAY_MISMATCH: Maestro no reproduce íntegramente la respuesta guardada."
            )
    model = answer.get("modular")
    if (not isinstance(model, dict)
            or answer.get("status") != "DRAFT_NOT_FOR_CUTTING"
            or any(answer.get(flag) is not False or model.get(flag) is not False
                   for flag in _BLOCKED_FLAGS)):
        raise PilotError("Fuente Maestro no aprobada como borrador.")
    expected_extras = review_files(model) if model.get("wall_bar_review") else {}
    manifest_files = manifest.get("files")
    if type(manifest_files) is not list:
        raise PilotError("Manifiesto sin lista segura de archivos.")
    has_flow_review = "flow-review.json" in manifest_files
    expected_files = list(_FILES) + (["flow-review.json"] if has_flow_review else []) + list(expected_extras)
    if (manifest.get("schema_version") != "1.0"
            or manifest.get("source") != "MAESTRO_MODULAR_F1_F7C"
            or manifest.get("status") != "DRAFT_NOT_FOR_CUTTING"
            or manifest.get("files") != expected_files
            or manifest.get("piece_count") != len(model.get("parts", []))
            or any(manifest.get(flag) is not False for flag in _BLOCKED_FLAGS)):
        raise PilotError("Manifiesto no corresponde a la fuente Maestro.")
    expected_cad = cad_exchange(model)
    actual_cad = validate_exchange(saved_cad)
    if (expected_cad != actual_cad
            or manifest.get("geometry_sha256") != expected_cad["geometry_sha256"]
            or len(actual_cad["boxes"]) != len(model["parts"])):
        raise PilotError("CAD, piezas o geometría diferentes del Maestro original.")

    flow_path = folder / "flow-review.json"
    if has_flow_review:
        if (not flow_path.is_file() or flow_path.is_symlink()
                or flow_path.stat().st_size > limits["flow-review.json"]):
            raise PilotError("Traza conversacional ausente, enlazada o excesiva.")
        try:
            flow_record = json.loads(flow_path.read_text(encoding="utf-8"))
            flow_request = flow_record.get("source_request")
            if (type(flow_request) is not dict or "query" in flow_request
                    or consult_maestro(flow_request) != answer):
                raise PilotError("Traza conversacional no reproduce el Maestro original.")
            validate_flow_review(flow_record, flow_request)
        except (OSError, UnicodeError, ValueError, TypeError, MaestroError, DesignError) as exc:
            raise PilotError("Traza conversacional alterada o inválida.") from exc
        if (flow_record.get("geometry_sha256") != expected_cad["geometry_sha256"]
                or flow_record.get("piece_count") != len(actual_cad["boxes"])):
            raise PilotError("Traza conversacional corresponde a otro proyecto CAD.")
    elif flow_path.exists() or flow_path.is_symlink():
        raise PilotError("Traza conversacional no declarada en el manifiesto.")

    for filename, expected in (
        ("front-review.svg", modular_front_svg(model)),
        ("parts-review.csv", modular_bom_csv(model)),
    ):
        if contents[filename] != expected:
            raise PilotError("Entregable no coincide con Maestro: " + filename)
    for filename, expected in expected_extras.items():
        path = folder / filename
        if (not path.is_file() or path.is_symlink()
                or path.stat().st_size > 1048576):
            raise PilotError("Entregable de barra ausente o alterado: " + filename)
        try:
            # Preserve CRLF in CSV: pathlib.read_text() normalizes newlines.
            observed = path.read_bytes().decode("utf-8")
        except UnicodeError as exc:
            raise PilotError("Entregable de barra no es UTF-8: " + filename) from exc
        if observed != expected:
            raise PilotError("Entregable de barra distinto del CAD: " + filename)
    return actual_cad

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CarpiNova: primer paquete geométrico de REVISIÓN, NO para cortar."
    )
    parser.add_argument("--input", required=True, type=Path,
                        help="JSON Maestro action=modular ya revisado")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Carpeta NUEVA para cinco archivos de revisión")
    parser.add_argument("--bundle-dir", type=Path,
                        help="Bundle Knowledge requerido para solicitudes con query")
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.input.read_text(encoding="utf-8"))
        result = write_pilot_bundle(request, args.output_dir,
                                    bundle_dir=args.bundle_dir)
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    except (OSError, ValueError, DesignError, MaestroError, PilotError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
