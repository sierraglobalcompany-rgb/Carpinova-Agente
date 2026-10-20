"""CarpiNova Maestro F5: fail-closed orchestration for existing expert tools.

The future language model may explain returned evidence, but cannot turn
preliminary geometry, book excerpts or hardware candidates into approved
manufacturing instructions. Inputs are explicitly structured JSON.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from hardware import suggest_hinge
from knowledge_client import load_bundle, search_content

from .intake import guide_project


ACTIONS = frozenset({"project", "knowledge", "hardware", "combined"})
FIELDS = frozenset({"action", "project", "query", "hardware"})
REQUIRED = {
    "project": frozenset({"project"}),
    "knowledge": frozenset({"query"}),
    "hardware": frozenset({"hardware"}),
    "combined": frozenset({"project"}),
}
ALLOWED = {
    "project": frozenset({"project"}),
    "knowledge": frozenset({"query"}),
    "hardware": frozenset({"hardware"}),
    "combined": frozenset({"project", "query", "hardware"}),
}


class MaestroError(ValueError):
    """Invalid routing or unavailable trusted evidence."""


def _normalize_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise MaestroError("La solicitud Maestro debe ser un objeto JSON.")
    action = request.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        raise MaestroError("action debe ser project, knowledge, hardware o combined.")
    provided = set(request) - {"action"}
    unknown = provided - FIELDS
    if unknown:
        raise MaestroError("Campos de Maestro desconocidos: " + ", ".join(sorted(unknown)))
    forbidden = provided - ALLOWED[action]
    if forbidden:
        raise MaestroError("Campos incompatibles con action: " + ", ".join(sorted(forbidden)))
    missing = REQUIRED[action] - provided
    if missing:
        raise MaestroError("Faltan campos: " + ", ".join(sorted(missing)))
    if "project" in provided and not isinstance(request["project"], dict):
        raise MaestroError("project debe ser un objeto JSON.")
    if "hardware" in provided and not isinstance(request["hardware"], dict):
        raise MaestroError("hardware debe ser un objeto JSON.")
    if "query" in provided and (
            not isinstance(request["query"], str) or not request["query"].strip()):
        raise MaestroError("query debe ser una consulta de texto no vacía.")
    return request


def consult_maestro(
    request: Mapping[str, Any],
    *,
    bundle_dir: Path | str | None = None,
    max_questions: int = 3,
) -> dict[str, Any]:
    """Compose source-backed tools; never invent drill patterns or dimensions.

    bundle_dir points to prebuilt, verified Knowledge consumer bundles.
    The tool does not silently search the network or ignore book questions.
    """
    inp = _normalize_request(request)
    action = inp["action"]
    result: dict[str, Any] = {
        "assistant": "CarpiNova Maestro",
        "integration_schema_version": "0.1.0",
        "action": action,
        "status": "NOT_READY_FOR_FABRICATION",
        "fabrication_ready": False,
        "cutting_ready": False,
        "drilling_ready": False,
        "purchase_ready": False,
        "project": None,
        "knowledge": None,
        "hardware": None,
        "questions": [],
        "blockers": [],
        "source_provenance": [],
    }
    if action == "combined" and "hardware" in inp:
        front = inp["project"].get("front_style")
        hw_front = inp["hardware"].get("front_style")
        if front == "none":
            raise MaestroError(
                "El proyecto declara frente ninguno, pero solicita bisagra."
            )
        if front in {"overlay", "inset"} and hw_front != front:
            raise MaestroError(
                "Conflicto de tipo de frente entre proyecto y herraje: "
                "no seleccionar bisagra hasta aclarar."
            )
    if action in ("project", "combined"):
        project = guide_project(inp["project"], max_questions=max_questions)
        result["project"] = project
        result["questions"].extend(project["questions"])
        result["blockers"].extend(project["release_blockers"])
    if action in ("knowledge", "combined") and "query" in inp:
        if bundle_dir is None:
            raise MaestroError(
                "Se requiere un bundle Knowledge validado para responder "
                "sobre el libro; no se inventan fuentes."
            )
        bundle = load_bundle(bundle_dir)
        found = search_content(bundle, inp["query"])
        result["knowledge"] = found
        result["source_provenance"] = [
            {
                "book": item["source_book"],
                "content_id": item["content_id"],
                "pdf_page": item["pdf_page"],
                "printed_page": item["printed_page"],
                "review_status": item["review_status"],
                "fabrication_authority": False,
            }
            for item in found["results"]
        ]
        if not found["results"]:
            result["blockers"].append(
                "No se encontró evidencia textual para esa consulta "
                "en el alcance del bundle disponible."
            )
        if found["coverage"] != "FULL_BOOK":
            result["blockers"].append(
                "Consulta sobre un paquete parcial; puede omitir "
                "partes del libro."
            )
        result["blockers"].append(
            "El contenido del libro es referencia educativa, "
            "no autoridad directa de fabricación."
        )
    if action in ("hardware", "combined") and "hardware" in inp:
        selected = suggest_hinge(inp["hardware"])
        result["hardware"] = selected
        result["blockers"].extend(selected["blockers"])
        for missing in selected["missing_inputs"]:
            result["questions"].append({
                "field": f"hardware.{missing}",
                "question": f"Falta verificar herraje: {missing}",
                "unit": "as_specified",
            })

    if result["project"] is not None:
        phase = result["project"]["phase"]
        if phase in {"NEEDS_INPUT", "INVALID_GEOMETRY", "SITE_CONFLICT"}:
            result["status"] = phase
        elif phase == "CONCEPT_ONLY":
            result["status"] = "CONCEPT_ONLY"
        else:
            result["status"] = "DRAFT_NOT_FOR_CUTTING"
    elif result["hardware"] is not None:
        result["status"] = "BLOCKED_HARDWARE_SPEC"
    else:
        result["status"] = "REFERENCE_ONLY"

    if not result["blockers"]:
        result["blockers"].append(
            "No existe proceso de certificación de fabricación en este MVP."
        )
    return result
