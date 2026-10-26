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
from knowledge_client.topic_screen import TOPIC_TERMS, screen_topic_results

from .intake import guide_project
from .modular import design_modular_run
from .wall_bar import design_wall_bar
from .drawer_modules import propose_drawer_layout, guide_drawer_layout
from .opening_guide import guide_opening_systems
from .construction_advice import construction_advice


ACTIONS = frozenset({"project", "knowledge", "hardware", "combined", "modular", "construction"})
FIELDS = frozenset({"action", "project", "query", "evidence_topic", "hardware", "module_spec", "construction"})
REQUIRED = {
    "project": frozenset({"project"}),
    "knowledge": frozenset({"query"}),
    "hardware": frozenset({"hardware"}),
    "combined": frozenset({"project"}),
    "modular": frozenset({"module_spec"}),
    "construction": frozenset({"construction"}),
}
ALLOWED = {
    "project": frozenset({"project"}),
    "knowledge": frozenset({"query"}),
    "hardware": frozenset({"hardware"}),
    "combined": frozenset({"project", "query", "hardware", "construction"}),
    "modular": frozenset({"module_spec", "query", "evidence_topic"}),
    "construction": frozenset({"construction"}),
}


class MaestroError(ValueError):
    """Invalid routing or unavailable trusted evidence."""


def _normalize_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise MaestroError("La solicitud Maestro debe ser un objeto JSON.")
    action = request.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        raise MaestroError("action debe ser project, knowledge, hardware, combined, modular o construction.")
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
    if "evidence_topic" in provided:
        topic = request["evidence_topic"]
        if "query" not in provided or type(topic) is not str or topic not in TOPIC_TERMS:
            raise MaestroError(
                "evidence_topic exige query y uno de los temas documentados."
            )
    if "construction" in provided and not isinstance(request["construction"], dict):
        raise MaestroError("construction debe ser un objeto JSON.")
    if "module_spec" in provided and not isinstance(request["module_spec"], dict):
        raise MaestroError("module_spec debe ser un objeto JSON.")
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
    if type(max_questions) is not int or not 1 <= max_questions <= 6:
        raise MaestroError("max_questions debe ser entero entre 1 y 6.")
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
        "modular": None,
        "construction": None,
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
    if action == "modular":
        spec = inp["module_spec"]
        modular = (
            guide_opening_systems(spec)
            if spec.get("type") == "opening_system_guide"
            else guide_drawer_layout(spec)
            if spec.get("type") == "drawer_layout_guide"
            else propose_drawer_layout(spec)
            if spec.get("type") == "drawer_layout_proposal"
            else design_wall_bar(spec)
            if spec.get("type") == "wall_bar"
            else design_modular_run(spec)
        )
        result["modular"] = modular
        result["blockers"].extend(modular["blockers"])
        if (modular["status"] == "NEEDS_USER_CONFIRMATION"
                and spec.get("type") == "opening_system_guide"):
            result["questions"].append({
                "field": "module_spec.focus",
                "question": (
                    "¿Cuál apertura quieres conocer o comparar? "
                    "El travesaño tipo T es solo una idea, no fabricación."
                ),
                "unit": "opening_choice_review",
            })
        elif modular["status"] == "NEEDS_USER_CONFIRMATION" and modular.get("guided"):
            # One novice-friendly question: never silently approve a floor-only
            # sketch when legs/plinth would change EVERY F1 drawer opening.
            intro = "¿Te gusta este boceto como primera idea? "
            if modular.get("support_style_is_suggestion"):
                guidance = (
                    "Antes de aprobarlo, ¿irá al piso sin patas, con patas, "
                    "con zócalo o suspendido? Sin patas es solo un ejemplo. "
                    "Al escoger patas/zócalo recalcularé carcasa y cajones. "
                )
            elif modular.get("support_height_is_suggestion"):
                guidance = (
                    "Elegiste patas/zócalo. ¿Qué altura real tendrán? "
                    "Los 100 mm del dibujo son solo una sugerencia: se "
                    "descuentan del alto total y cambian todos los cajones. "
                )
            else:
                guidance = (
                    "Puedes decir 'A más alto', 'pon patas de 10 cm', "
                    "'T más ancha' o 'quiero colgarlo en muro'. "
                )
            result["questions"].append({
                "field": "module_spec.proposed_layout_spec",
                "question": intro + guidance
                + "Después revisamos fondo FP, herrajes y materiales.",
                "unit": "simple_confirmation",
            })
        elif modular["status"] == "NEEDS_USER_CONFIRMATION":
            result["questions"].extend([
                {
                    "field": "module_spec.drawer_weights",
                    "question": (
                        "¿Confirmas el orden de abajo hacia arriba y "
                        "las proporciones de estas aperturas, incluida "
                        "la posición de la gaveta grande?"
                    ),
                    "unit": "ratio_and_order",
                },
                {
                    "field": "module_spec.vertical_gap_mm",
                    "question": (
                        "¿Confirmas la franja nominal entre aberturas "
                        "(no entre frentes ni un divisor) o quieres cambiarla?"
                    ),
                    "unit": "mm",
                },
                {
                    "field": "module_spec.finish_and_hardware",
                    "question": (
                        "¿Frentes embutidos o sobrepuestos? ¿La "
                        "profundidad incluye espesor del frente? "
                        "Confirma materiales, correderas y sistema "
                        "de apertura (tirador, uñero, push-to-open o perfil)."
                    ),
                    "unit": "construction_choice",
                },
            ])
        elif modular["status"] == "NEEDS_SITE_MEASUREMENTS":
            for location in ("top", "middle", "bottom"):
                result["questions"].append({
                    "field": f"module_spec.site_width_mm.{location}",
                    "question": f"Indica ancho del hueco en {location} (mm)",
                    "unit": "mm",
                })
        elif modular["status"] == "NEEDS_LAYOUT_REVISION":
            result["questions"].append({
                "field": "module_spec.modules[*].width_mm",
                "question": "Ajusta anchos de módulos para sumar el ancho total sin inventar rellenos.",
                "unit": "mm",
            })
        elif modular["status"] == "NEEDS_DEPTH_REVISION":
            dimensions = modular["depth_review"]
            result["questions"].append({
                "field": "module_spec.max_assembled_depth_mm",
                "question": (
                    f"La carcasa mide {dimensions['carcass_depth_mm']} mm "
                    f"más {dimensions['front_extension_mm']} mm de frente: "
                    f"{dimensions['assembled_external_depth_mm']} mm exteriores. "
                    f"Supera el máximo de {dimensions['max_assembled_depth_mm']} mm. "
                    "¿Reduces profundidad de carcasa o cambias el límite?"
                ),
                "unit": "mm",
            })
        elif modular["status"] == "SITE_CONFLICT":
            result["questions"].append({
                "field": "module_spec.width_mm",
                "question": "El ancho no cabe en la menor luz medida: ¿qué nueva medida propones?",
                "unit": "mm",
            })
        if modular["status"] == "DRAFT_NOT_FOR_CUTTING":
            modules = (inp["module_spec"]["modules"]
                       if spec.get("type") != "wall_bar"
                       else [spec["cabinet_module"]])
            # Structural decisions come first; cosmetic finishing must not
            # hide an unresolved drawer/door/support when max_questions=3.
            for module in modules:
                module_id = module["module_id"]
                for key in ("fronts", "back", "drawers", "support"):
                    if module.get(key) == "pending":
                        result["questions"].append({
                            "field": f"module_spec.modules.{module_id}.{key}",
                            "question": f"Falta definir {key} del módulo {module_id}.",
                            "unit": "construction_choice",
                        })
                drawers = module.get("drawers")
                if isinstance(drawers, list):
                    for drawer in drawers:
                        if drawer.get("facade") == "pending":
                            result["questions"].append({
                                "field": (
                                    f"module_spec.modules.{module_id}.drawers."
                                    f"{drawer['drawer_id']}.facade"
                                ),
                                "question": (
                                    f"Definir frente decorativo embutido del cajón "
                                    f"{drawer['drawer_id']} en {module_id}: "
                                    "material, espesor y cuatro holguras."
                                ),
                                "unit": "construction_choice",
                            })
            for module in modules:
                if module.get("finish") is None:
                    module_id = module["module_id"]
                    result["questions"].append({
                        "field": f"module_spec.modules.{module_id}.finish",
                        "question": (
                            f"¿Qué veta y cantos lleva cada una de las "
                            f"cuatro piezas de {module_id}?"
                        ),
                        "unit": "per_panel",
                    })
            if spec.get("type") == "wall_bar":
                # Optional presentation only. Never infer a mounting method,
                # add physical panels, or block design for unknown wall type.
                choices = spec.get("design_choices", {})
                if "wall_support_presentation" not in choices:
                    result["questions"].append({
                        "field": "module_spec.design_choices.wall_support_presentation",
                        "question": (
                            "¿Cómo deseas representar el apoyo mural? "
                            "installer_defined (decide el instalador, predeterminado), "
                            "wood_cleat (listón bajo cubierta), "
                            "metal_l_brackets (escuadras L), "
                            "metal_support (soporte metálico), u other_pending. "
                            "No se añaden piezas sin dimensiones y aprobación."
                        ),
                        "unit": "optional_design_choice",
                    })
                if "top_edge_presentation" not in choices:
                    result["questions"].append({
                        "field": "module_spec.design_choices.top_edge_presentation",
                        "question": (
                            "¿Mantener el canto visible real de 15 mm (actual_15mm), "
                            "dar apariencia de mayor espesor con cenefa decorativa "
                            "(false_thickness_pending), o dejar undecided? "
                            "La cenefa no certifica refuerzo estructural."
                        ),
                        "unit": "optional_design_choice",
                    })
        result["questions"] = result["questions"][:max_questions]
    if action in ("project", "combined"):
        project = guide_project(inp["project"], max_questions=max_questions)
        result["project"] = project
        result["questions"].extend(project["questions"])
        result["blockers"].extend(project["release_blockers"])
    if action in ("construction", "combined") and "construction" in inp:
        guidance=construction_advice(inp["construction"],max_questions=max_questions)
        result["construction"]=guidance
        result["questions"].extend(guidance["questions"])
        result["blockers"].extend(guidance["blockers"])
    if action in ("knowledge", "combined", "modular") and "query" in inp:
        if bundle_dir is None:
            raise MaestroError(
                "Se requiere un bundle Knowledge validado para responder "
                "sobre el libro; no se inventan fuentes."
            )
        bundle = load_bundle(bundle_dir)
        if "evidence_topic" in inp:
            # Use ONLY the existing canonical Knowledge search. Screening
            # evaluates a bounded retrieval window; it is not semantic proof.
            found = search_content(bundle, inp["query"], limit=20)
            found = screen_topic_results(found, inp["evidence_topic"])
        else:
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
        if "relevance_review" in found:
            result["blockers"].append(
                "Las referencias del tema solo son candidatas léxicas; "
                "se requiere revisar la página original y su pertinencia "
                "técnica para este mueble."
            )
            if not found["results"]:
                result["blockers"].append(
                    "La muestra de búsqueda no contiene una referencia "
                    "con el contexto completo del tema solicitado."
                )
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

    if result["modular"] is not None:
        result["status"] = result["modular"]["status"]
    elif result["project"] is not None:
        phase = result["project"]["phase"]
        if phase in {"NEEDS_INPUT", "INVALID_GEOMETRY", "SITE_CONFLICT"}:
            result["status"] = phase
        elif phase == "CONCEPT_ONLY":
            result["status"] = "CONCEPT_ONLY"
        else:
            result["status"] = "DRAFT_NOT_FOR_CUTTING"
    elif result["hardware"] is not None:
        result["status"] = "BLOCKED_HARDWARE_SPEC"
    elif result["construction"] is not None:
        result["status"] = "ADVISORY_ONLY"
    else:
        result["status"] = "REFERENCE_ONLY"

    if not result["blockers"]:
        result["blockers"].append(
            "No existe proceso de certificación de fabricación en este MVP."
        )
    # Prioritize geometry blockers over nice-to-have construction questions.
    result["questions"]=result["questions"][:max_questions]
    return result
