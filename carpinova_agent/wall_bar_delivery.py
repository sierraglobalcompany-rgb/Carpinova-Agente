"""Review-only delivery sheets for the existing wall-bar CAD; never a cut plan.

Pure presentation layer: every reference and rectangle comes from the
canonical CADExchange boxes. No new geometry, joints, hardware or approvals.
"""
from __future__ import annotations

import csv
from html import escape
from io import StringIO
import json
from textwrap import wrap
from typing import Any
from xml.etree import ElementTree

from .cad_exchange import cad_exchange, validate_exchange
from .core import DesignError
from .wall_bar_sheets import edge_policy_rows

STRUCTURE = (
    ("E01", "Cubierta", "BAR-COVER-TOP"),
    ("E02", "Lateral izquierdo", "CAJONERA_DERECHA-LEFT_SIDE"),
    ("E03", "Lateral derecho", "CAJONERA_DERECHA-RIGHT_SIDE"),
    ("E04", "Tapa de cajonera", "CAJONERA_DERECHA-TOP"),
    ("E05", "Base de cajonera", "CAJONERA_DERECHA-BOTTOM"),
    ("E06", "Respaldo", "CAJONERA_DERECHA-BACK_FULL"),
)
DRAWER_ROLES = (
    ("01", "Fachada decorativa aplicada", "DRAWER_FACADE"),
    ("02", "Pared frontal interior", "DRAWER_FRONT_WALL"),
    ("03", "Lateral izquierdo", "DRAWER_SIDE_LEFT"),
    ("04", "Lateral derecho", "DRAWER_SIDE_RIGHT"),
    ("05", "Trasera", "DRAWER_REAR_WALL"),
    ("06", "Fondo", "DRAWER_BOTTOM"),
)

_P6_BOOK_SOURCES = (
    ("CONTENT-CPNC-2025-P0067-001", 67, 45),
    ("CONTENT-CPNC-2025-P0068-001", 68, 46),
    ("CONTENT-CPNC-2025-P0073-001", 73, 51),
    ("CONTENT-CPNC-2025-P0113-002", 113, 91),
    ("CONTENT-CPNC-2025-P0113-003", 113, 91),
    ("CONTENT-CPNC-2025-P0114-001", 114, 92),
    ("CONTENT-CPNC-2025-P0114-002", 114, 92),
    ("CONTENT-CPNC-2025-P0114-003", 114, 92),
    ("CONTENT-CPNC-2025-P0114-004", 114, 92),
    ("CONTENT-CPNC-2025-P0114-005", 114, 92),
    ("CONTENT-CPNC-2025-P0115-001", 115, 93),
    ("CONTENT-CPNC-2025-P0115-002", 115, 93),
    ("CONTENT-CPNC-2025-P0115-003", 115, 93),
    ("CONTENT-CPNC-2025-P0115-004", 115, 93),
    ("CONTENT-CPNC-2025-P0116-001", 116, 94),
    ("CONTENT-CPNC-2025-P0116-002", 116, 94),
    ("CONTENT-CPNC-2025-P0118-001", 118, 96),
    ("CONTENT-CPNC-2025-P0118-002", 118, 96),
    ("CONTENT-CPNC-2025-P0118-003", 118, 96),
    ("CONTENT-CPNC-2025-P0177-001", 177, 155),
    ("CONTENT-CPNC-2025-P0177-002", 177, 155),
    ("CONTENT-CPNC-2025-P0177-003", 177, 155),
    ("CONTENT-CPNC-2025-P0177-004", 177, 155),
    ("CONTENT-CPNC-2025-P0266-001", 266, 244),
    ("CONTENT-CPNC-2025-P0267-001", 267, 245),
)


def _wall_bar_p6_review(
    model: dict[str, Any], edge_rows: list[dict[str, Any]],
    cad: dict[str, Any], human: dict[str, Any],
) -> dict[str, Any]:
    """Build book-first review metadata from existing CAD and edge policy."""
    review = model.get("wall_bar_review")
    if not isinstance(review, dict):
        raise DesignError("P6 requiere el proyecto CN-BAR-001 de revisión.")
    front_review = review.get("front_edgebanding_review")
    if not isinstance(front_review, dict):
        raise DesignError("P6 requiere la revisión vigente de frentes aplicados.")
    boxes = {box["piece_id"]: box for box in cad["boxes"]}
    if len(boxes) != 28 or len(edge_rows) != 96:
        raise DesignError("P6 requiere los 28 elementos CAD y la matriz de 96 bordes.")

    policy_counts: dict[str, int] = {}
    for row in edge_rows:
        policy = row["edge_policy"]
        policy_counts[policy] = policy_counts.get(policy, 0) + 1
    contact_edges = sum(row["cad_contact"] == "CAD_CONTACT_NOMINAL"
                        for row in edge_rows)
    physical_panels = {row["piece_id"] for row in edge_rows}

    facade_summary = []
    for letter, drawer_id in (("A", "D1"), ("B", "D2"), ("C", "D3")):
        source = front_review.get("fronts", {}).get(drawer_id)
        facade = human.get("facades", {}).get(letter)
        if not isinstance(source, dict) or not isinstance(facade, dict):
            raise DesignError("Falta el objetivo exterior de fachada " + letter + ".")
        target = source.get("proposed_finished_outer_target_size_mm")
        nominal = [facade.get("width_mm"), facade.get("height_mm")]
        if (type(target) is not list or len(target) != 2
                or any(type(value) is not int or value <= 0 for value in target)
                or target != nominal):
            raise DesignError("El objetivo de fachada no coincide con CAD: " + letter)
        candidate_edges = [row for row in edge_rows
                           if row["piece_id"] == facade["piece_id"]]
        edge_band = source.get("rigid_edge_mm_each_side")
        all_four_candidates = (
            len(candidate_edges) == 4 and edge_band == 2
            and all(row["edge_policy"] == "RIGID_PVC_2MM_CANDIDATE"
                    and row["candidate_thickness_mm"] == 2
                    for row in candidate_edges)
        )
        substrate = ([target[0] - 2 * edge_band, target[1] - 2 * edge_band]
                     if all_four_candidates else None)
        facade_summary.append({
            "facade": letter,
            "drawer_id": drawer_id,
            "piece_id": facade["piece_id"],
            "cad_nominal_dimensions_mm": nominal,
            "finished_outer_target_mm": target,
            "finished_outer_target_status": "OWNER_DESIGN_TARGET_PROPOSED",
            "edge_candidate": "RIGID_PVC_2MM_CANDIDATE" if all_four_candidates
            else "NOT_CONFIRMED",
            "ideal_substrate_dimensions_mm": substrate,
            "ideal_substrate_status": ("NOT_A_CUT_DIMENSION" if substrate
                                       else "NOT_COMPUTABLE"),
            "unverified_processes": [
                "adhesive_or_application_allowance", "machine_tolerance",
                "squareness", "physical_edge_measurement",
            ],
        })

    cover_id = "BAR-COVER-TOP"
    cover_edges = {row["face_edge"]: row for row in edge_rows
                   if row["piece_id"] == cover_id}
    if set(cover_edges) != {"x_min", "x_max", "y_min", "y_max"}:
        raise DesignError("P6 necesita las cuatro aristas de la cubierta E01.")

    left = boxes["CAJONERA_DERECHA-LEFT_SIDE"]
    right = boxes["CAJONERA_DERECHA-RIGHT_SIDE"]
    side_thickness = left["size_xyz_mm"][0]
    inside_left = left["origin_xyz_mm"][0] + side_thickness
    inside_right = right["origin_xyz_mm"][0]
    opening_width = inside_right - inside_left
    drawer_boxes = [boxes[f"CAJONERA_DERECHA-{drawer}-DRAWER_BOTTOM"]
                    for drawer in ("D1", "D2", "D3")]
    drawer_widths = {box["size_xyz_mm"][0] for box in drawer_boxes}
    if len(drawer_widths) != 1:
        raise DesignError("Las tres cajas no comparten el ancho CAD esperado.")
    box_width = drawer_widths.pop()
    drawer_left = drawer_boxes[0]["origin_xyz_mm"][0]
    drawer_right = drawer_left + box_width
    clearance_left = drawer_left - inside_left
    clearance_right = inside_right - drawer_right
    if min(opening_width, box_width, clearance_left, clearance_right) <= 0:
        raise DesignError("La comparación nominal caja/carcasa no es positiva.")

    drawer_bottom_id = "CAJONERA_DERECHA-D1-DRAWER_BOTTOM"
    back_id = "CAJONERA_DERECHA-BACK_FULL"
    bottom = boxes[drawer_bottom_id]
    back = boxes[back_id]
    drawer_front_z = bottom["origin_xyz_mm"][2]
    drawer_back_z = drawer_front_z + bottom["size_xyz_mm"][2]
    back_start_z = back["origin_xyz_mm"][2]
    cavity_depth = back_start_z - drawer_front_z
    rear_margin = back_start_z - drawer_back_z
    if min(cavity_depth, rear_margin) <= 0:
        raise DesignError("La caja nominal invade o excede la envolvente CAD posterior.")
    external_depth = human["depth_mm"]
    standard_lengths = tuple(range(200, 651, 50))
    book_length_candidate = max(
        (length for length in standard_lengths if length < external_depth),
        default=None,
    )
    envelope_length_candidate = max(
        (length for length in standard_lengths if length < cavity_depth),
        default=None,
    )
    book_exception = (
        "BOOK_HEURISTIC_REJECTED_BY_CAD_ENVELOPE"
        if book_length_candidate is not None and book_length_candidate > cavity_depth
        else "BOOK_HEURISTIC_NOT_REJECTED_BUT_FITMENT_UNVERIFIED"
    )

    raw_scenario = front_review.get("raw_interpretation_scenario", {})
    if raw_scenario.get("status") != "INVALID_RAW_VS_FINISHED":
        raise DesignError("P6 requiere conservar el rechazo de doble compensación.")
    raw_sizes = raw_scenario.get("resulting_front_sizes_mm", {})
    raw_gaps = raw_scenario.get("theoretical_interfront_gaps_mm", {})

    return {
        "schema_version": "1.0",
        "project_id": "CN-BAR-001",
        "status": "DRAFT_NOT_FOR_CUTTING",
        "review_scope": "BOOK_FIRST_CONSTRUCTIVE_REVIEW",
        "geometry_sha256": cad["geometry_sha256"],
        "cad_element_count": len(boxes),
        "physical_panel_count": len(physical_panels),
        "conceptual_support_count_excluded_from_edgebanding": 4,
        "edge_review": {
            "source": "CADExchange",
            "evidence_status": "CAD_OBSERVED",
            "evidence_basis": "ROLE_AND_GEOMETRY",
            "site_context": "SITE_UNKNOWN",
            "edge_count": len(edge_rows),
            "unique_piece_edge_count": len({
                (row["piece_id"], row["face_edge"]) for row in edge_rows
            }),
            "nominal_contact_edge_count": contact_edges,
            "edge_policy_counts": policy_counts,
            "conditional_candidates_are_not_assignments": True,
            "book_conditional_options": [
                {"policy": "RIGID_PVC_2MM_CANDIDATE",
                 "condition": "Borde de fachada realmente visible; humedad y proceso aún por verificar."},
                {"policy": "FLEXIBLE_PVC_0_45MM_CANDIDATE",
                 "condition": "Borde estructural/interior que sea realmente visible y reciba bajo contacto; no asignado sin contexto."},
                {"policy": "SEMIRIGID_PVC_1_OR_1_5MM_BOOK_OPTION_ONLY",
                 "condition": "Alternativa citada por el libro; ningún borde de este proyecto la tiene seleccionada."},
                {"policy": "NO_DECORATIVE_EDGE_CANDIDATE",
                 "condition": "Solo si el borde está completamente oculto, seco y protegido; condición del sitio no verificada."},
            ],
            "rows_file": "CN-BAR-001-cantos-por-borde-REVISION.json",
            "csv_file": "CN-BAR-001-cantos-por-borde-REVISION.csv",
            "interpretation": (
                "CAD_CONTACT_NOMINAL solo informa contacto entre cajas geométricas; "
                "no demuestra unión, fijación, canto físico, ocultamiento ni sequedad."
            ),
        },
        "finished_targets_vs_substrate": {
            "finished_panel_edges_included": False,
            "facades": facade_summary,
            "cover_E01_substrate": {
                "status": "NOT_COMPUTABLE",
                "dimensions": {
                    "X": {"status": "NOT_COMPUTABLE",
                          "edges": ["x_min", "x_max"],
                          "reason": "x_min no confirma ocultamiento/sequedad y x_max es candidato sin validar."},
                    "Z": {"status": "NOT_COMPUTABLE",
                          "edges": ["y_min", "y_max"],
                          "reason": "y_min es candidato sin validar y y_max permanece en revisión."},
                },
                "raw_substrate_dimensions_emitted": False,
            },
            "invalid_raw_vs_finished_example": {
                "status": "INVALID_RAW_VS_FINISHED",
                "raw_interpretation_front_sizes_mm": raw_sizes,
                "theoretical_interfront_gaps_mm": raw_gaps,
                "zero_gap_accepted": False,
                "cut_dimensions_authorized": False,
            },
        },
        "slide_review": {
            "family_candidate": "TELESCOPIC_SIDE_MOUNT_BALL_BEARING_TRADITIONAL_CLOSE",
            "family_status": "PRELIMINARY_BOOK_BASED_NOT_SELECTED",
            "book_rule": {
                "lateral_clearances_mm_each_side": {
                    "light_duty": 13,
                    "medium_or_heavy": 14,
                    "soft_close_or_push_open": 15,
                },
                "under_mount_deduction_total_per_pair_mm": 15,
                "standard_length_selection": "Immediately shorter standard length than external depth; compare with CAD cavity before review recommendation.",
                "x_and_2x": "Educational vertical distribution; not the 4 mm facade gaps and not a drilling pattern.",
            },
            "book_source_ids": [
                "CONTENT-CPNC-2025-P0113-002",
                "CONTENT-CPNC-2025-P0113-003",
                "CONTENT-CPNC-2025-P0114-001",
                "CONTENT-CPNC-2025-P0114-002",
                "CONTENT-CPNC-2025-P0114-003",
                "CONTENT-CPNC-2025-P0114-004",
                "CONTENT-CPNC-2025-P0115-002",
                "CONTENT-CPNC-2025-P0115-004",
                "CONTENT-CPNC-2025-P0116-002",
            ],
            "book_exception": book_exception,
            "length_nominal_candidate_mm": envelope_length_candidate,
            "length_fitment_verified": False,
            "installation_verified": False,
            "drilling_coordinates": [],
            "sku_selected": None,
            "weight_capacity_for_drawer": None,
            "cad_derived_dimensions": {
                "carcass_inner_opening_width_mm": opening_width,
                "drawer_box_outer_width_mm": box_width,
                "drawer_left_clearance_mm": clearance_left,
                "drawer_right_clearance_mm": clearance_right,
                "drawer_box_interior_clear_width_mm": human["drawer_boxes"]["D1"]["internal_clear_dimensions_mm"][0],
                "external_depth_mm": external_depth,
                "cavity_front_z_mm": drawer_front_z,
                "cavity_rear_z_mm": back_start_z,
                "cavity_front_to_back_mm": cavity_depth,
                "drawer_box_front_z_mm": drawer_front_z,
                "drawer_box_rear_z_mm": drawer_back_z,
                "drawer_box_nominal_depth_mm": drawer_back_z - drawer_front_z,
                "nominal_rear_margin_mm": rear_margin,
                "drawer_bottom_piece_id": drawer_bottom_id,
                "back_piece_id": back_id,
            },
            "lateral_options_mm_each_side": [
                {"book_class": "LIGHT_DUTY", "allowance_each_side_mm": 13,
                 "total_pair_mm": 26, "theoretical_box_outer_width_mm": opening_width - 26,
                 "status": "REVIEW_ONLY_NOT_SELECTED"},
                {"book_class": "MEDIUM_OR_HEAVY", "allowance_each_side_mm": 14,
                 "total_pair_mm": 28, "theoretical_box_outer_width_mm": opening_width - 28,
                 "status": "REVIEW_ONLY_NOT_SELECTED"},
                {"book_class": "SOFT_CLOSE_OR_PUSH_OPEN", "allowance_each_side_mm": 15,
                 "total_pair_mm": 30, "theoretical_box_outer_width_mm": opening_width - 30,
                 "status": "REVIEW_ONLY_NOT_SELECTED"},
            ],
            "under_mount_option": {
                "book_deduction_total_per_pair_mm": 15,
                "family": "UNDER_MOUNT_SEPARATE_FROM_LATERAL",
                "applied_to_current_geometry": False,
            },
            "book_example_344_interpretation": {
                "source_id": "CONTENT-CPNC-2025-P0114-003",
                "source_labels_344_mm_as": "internal_drawer_width",
                "review_interpretation": "244/344 arithmetic is drawer-box outer width between side slides, not useful interior clear width.",
                "current_cad_drawer_box_outer_width_mm": box_width,
                "current_cad_drawer_interior_clear_width_mm": human["drawer_boxes"]["D1"]["internal_clear_dimensions_mm"][0],
            },
            "book_length_heuristic": {
                "basis": "Immediately shorter standard length than external depth, per book.",
                "external_depth_mm": external_depth,
                "nominal_candidate_mm": book_length_candidate,
                "cad_cavity_front_to_back_mm": cavity_depth,
                "alternative_350_mm": "BOOK_EXAMPLE_ONLY_NOT_SELECTED",
            },
            "manufacturer_reference": {
                "status": "VERIFIED_OFFICIAL_REFERENCE_ILLUSTRATIVE_ONLY",
                "manufacturer": "Accuride",
                "family": "DZ3832DO",
                "variant": "DZ3832-0040DO",
                "slide_length_SL_mm": 400,
                "extension_travel_TR_mm": 406,
                "slide_thickness_mm": 12.7,
                "required_side_space_adjustment_mm": [0.2, 0.5],
                "derived_slide_thickness_plus_adjustment_mm_each_side": [12.9, 13.2],
                "hold_out_present": True,
                "sku_selected": None,
                "compatibility_verified": False,
                "drilling_coordinates": [],
                "datasheet_url": "https://hs-europe.accuride.com/hubfs/Datasheets/3832DO_en.pdf",
            },
            "source_frame_conflict": {
                "id": "SOURCE_FRAME_CONFLICT_37_32",
                "status": "UNRESOLVED",
                "source_ids": ["CONTENT-CPNC-2025-P0067-001",
                               "CONTENT-CPNC-2025-P0114-005",
                               "CONTENT-CPNC-2025-P0116-001"],
                "drilling_coordinates": [],
            },
        },
        "knowledge_provenance": {
            "book_id": "cpnc-2025",
            "book_title": "Carpintería para no Carpinter@s",
            "edition_year": 2025,
            "repository": "sierraglobalcompany-rgb/CarpiNova-Knowledge",
            "commit": "d350f3de1104977986f30498d212e018cbac5d29",
            "reference_mode": "REFERENCE_DOCUMENTAL_AUDITADA",
            "runtime_query_performed": False,
            "content_references": [
                {"content_id": content_id, "pdf_page": pdf_page,
                 "printed_page": printed_page,
                 "extraction_status": "VISUALLY_VERIFIED"}
                for content_id, pdf_page, printed_page in _P6_BOOK_SOURCES
            ],
        },
        "hardware_included": False,
        "manufacturing_flags": {
            "fabrication_ready": False,
            "cutting_ready": False,
            "drilling_ready": False,
            "purchase_ready": False,
        },
        "fabrication_ready": False,
        "cutting_ready": False,
        "drilling_ready": False,
        "purchase_ready": False,
    }


def _wall_bar_p6_criteria(review: dict[str, Any]) -> str:
    """Explain book, CAD calculations and unresolved decisions plainly."""
    edge = review["edge_review"]
    dimensions = review["finished_targets_vs_substrate"]
    rails = review["slide_review"]
    lines = [
        "# CN-BAR-001 · Revisión constructiva P6 (BORRADOR · NO FABRICAR)",
        "",
        "Este documento explica una revisión nominal del CAD existente. No es un despiece de corte, patrón de perforación ni selección aprobada de herrajes.",
        "",
        "## Qué recomienda el libro",
        "",
        "- Para frentes visibles, el libro presenta canto rígido de 2 mm; para piezas estructurales/interiores menciona canto flexible de 0,45 mm y semirrígido de 1 o 1,5 mm. La geometría no demuestra exposición, humedad ni protección, así que estas son referencias condicionadas, no órdenes de canto.",
        "  Referencias: `CONTENT-CPNC-2025-P0177-001`, `CONTENT-CPNC-2025-P0177-002`, `CONTENT-CPNC-2025-P0177-003` y `CONTENT-CPNC-2025-P0177-004` (PDF p177, impresa p155). El flexible de 0,45 mm solo es opción para un borde interior realmente visible y de bajo contacto; el sitio sigue sin verificar.",
        "- En correderas laterales, las referencias pedagógicas son 13 mm por lado para livianas, 14 mm por lado para medianas/pesadas y 15 mm por lado para cierre suave o push-open. Las correderas de montaje inferior son otra familia: el libro menciona 15 mm total por par; no se combina con los descuentos laterales. `CONTENT-CPNC-2025-P0113-002`, `CONTENT-CPNC-2025-P0113-003`, `CONTENT-CPNC-2025-P0114-002` y `CONTENT-CPNC-2025-P0114-004` (PDF p113–114, impresa p91–92).",
        "- En el ejemplo del libro, 344 mm queda denominado “ancho interno”; al restar rieles laterales, ese resultado corresponde al ancho exterior de la caja, no a su espacio útil interior. Aquí el CAD da 244 mm exterior y 214 mm interior. `CONTENT-CPNC-2025-P0114-003` (PDF p114, impresa p92).",
        "- El libro sugiere una longitud comercial inmediatamente menor que la profundidad exterior; el propio ejemplo 400→350 mm es una heurística, no una regla que confirme el espacio real de instalación. `CONTENT-CPNC-2025-P0114-001`.",
        "- X y 2X ayudan a explicar la distribución de correderas. No son las luces de 4 mm entre frentes de esta barra ni un patrón de taladros aprobado. `CONTENT-CPNC-2025-P0115-002`, `CONTENT-CPNC-2025-P0115-004` y `CONTENT-CPNC-2025-P0116-002`.",
        "- El texto 37/32 difiere en su referencia de borde entre `CONTENT-CPNC-2025-P0067-001`, `CONTENT-CPNC-2025-P0114-005` y `CONTENT-CPNC-2025-P0116-001`; se conserva como conflicto, sin coordenadas de perforación.",
        "- Las páginas de revisión de entrega p266–267 piden separaciones parejas; no fijan 4 mm como medida universal. `CONTENT-CPNC-2025-P0266-001` y `CONTENT-CPNC-2025-P0267-001`.",
        "- La fuente impresa de 45 kg/18 pulgadas y 30.000 ciclos de p118 pertenece al ejemplo reproducido allí; no se extrapola a otra referencia. `CONTENT-CPNC-2025-P0118-001`, `CONTENT-CPNC-2025-P0118-002` y `CONTENT-CPNC-2025-P0118-003`.",
        "",
        "## Qué calcula el diseño",
        "",
        f"- CADExchange: SHA `{review['geometry_sha256']}`, {review['physical_panel_count']} paneles nominales y 4 apoyos conceptuales excluidos de la matriz de cantos.",
        f"- La única matriz contiene {edge['edge_count']} bordes únicos: {edge['edge_policy_counts'].get('RIGID_PVC_2MM_CANDIDATE', 0)} candidatos rígidos de 2 mm y {edge['edge_policy_counts'].get('REVIEW_REQUIRED', 0)} bordes en revisión. Contactos CAD registrados: {edge['nominal_contact_edge_count']}; `CAD_CONTACT_NOMINAL` no acredita una unión física.",
        f"- El detalle completo está en `{edge['rows_file']}` y `{edge['csv_file']}`; este resumen no duplica sus 96 filas.",
        "",
        "| Frente | Objetivo exterior terminado propuesto (mm) | Sustrato ideal teórico (mm) | Estado |",
        "|---|---:|---:|---|",
    ]
    for facade in dimensions["facades"]:
        target = " × ".join(map(str, facade["finished_outer_target_mm"]))
        substrate = (" × ".join(map(str, facade["ideal_substrate_dimensions_mm"]))
                     if facade["ideal_substrate_dimensions_mm"] else "NOT_COMPUTABLE")
        lines.append(
            f"| {facade['facade']} | {target} | {substrate} | {facade['ideal_substrate_status']} |"
        )
    lines.extend([
        "",
        "Los sustratos son una resta ideal de 2 mm por cada borde de fachada, solo para mostrar la relación entre objetivo terminado y tablero. No incluyen adhesivo, tolerancias, proceso ni escuadría; no son medidas de corte. Para E01 no se publica un tamaño de sustrato: ambos ejes quedan `NOT_COMPUTABLE` porque faltan decisiones verificadas de canto/ocultamiento.",
        "",
        "**Control negativo:** interpretar A/B como tablero bruto y sumar 2 mm en cada borde daría 296 × 182 mm; para C daría 296 × 477 mm. El escenario registrado reduce las luces teóricas entre frentes a 0 mm y se rechaza como `INVALID_RAW_VS_FINISHED`; no se acepta ni autoriza corte.",
        "",
        "### Correderas: comparación educativa",
        "",
        "| Alternativa lateral del libro | Descuento por lado | Descuento del par | Caja exterior teórica desde abertura CAD 270 mm | Aplicada |",
        "|---|---:|---:|---:|---|",
    ])
    for option in rails["lateral_options_mm_each_side"]:
        lines.append(
            f"| {option['book_class']} | {option['allowance_each_side_mm']} mm | "
            f"{option['total_pair_mm']} mm | {option['theoretical_box_outer_width_mm']} mm | No |"
        )
    lines.extend([
        "",
        f"La caja CAD mide {rails['cad_derived_dimensions']['drawer_box_outer_width_mm']} mm por fuera y sus holguras laterales nominales son {rails['cad_derived_dimensions']['drawer_left_clearance_mm']} + {rails['cad_derived_dimensions']['drawer_right_clearance_mm']} mm. La coincidencia numérica con 13 mm por lado no selecciona una corredera ni valida montaje.",
        "",
        f"El criterio del libro produciría {rails['book_length_heuristic']['nominal_candidate_mm']} mm para {rails['book_length_heuristic']['external_depth_mm']} mm de profundidad exterior. La cavidad nominal frontal→respaldo, calculada entre `{rails['cad_derived_dimensions']['drawer_bottom_piece_id']}` y `{rails['cad_derived_dimensions']['back_piece_id']}`, es {rails['cad_derived_dimensions']['cavity_front_to_back_mm']} mm. La excepción queda `{rails['book_exception']}`. Se deja {rails['length_nominal_candidate_mm']} mm como candidato de revisión sin compatibilidad ni instalación verificadas; 350 mm solo aparece como ejemplo del libro y no se elige automáticamente.",
        "",
        "La ficha oficial Accuride DZ3832DO se conserva como referencia ilustrativa: la variante DZ3832-0040DO indica SL 400 mm y TR 406 mm. Espesor, margen lateral y función hold-out de esa ficha no prueban compatibilidad con esta caja. `sku_selected=null`; no hay capacidad de carga aprobada ni coordenadas de taladros.",
        "",
        "## Qué falta para instalar",
        "",
        "- Confirmar ambiente, humedad, exposición real, caras visibles, ocultamiento, protección y acabado de cada borde.",
        "- Confirmar si los objetivos propuestos de fachada y los 4 mm siguen vigentes después de revisar el montaje real. Las páginas 266–267 solo piden uniformidad; no establecen ese valor.",
        "- Elegir una familia y referencia de corredera con ficha exacta y verificar carga, recorrido, longitud retraída, ancho de instalación y espacio posterior.",
        "- El texto 37/32 tiene referencias de borde diferentes en `SOURCE_FRAME_CONFLICT_37_32`; no se generan perforaciones.",
        "- Revisar fijaciones, uniones, estabilidad, nivelación y condiciones del sitio por separado.",
        "",
        f"Estado: `{review['status']}`. Hardware incluido: `{str(review['hardware_included']).lower()}`. Permisos: fabrication/cutting/drilling/purchase = `false`. Fuente bibliográfica documental fijada en `{review['knowledge_provenance']['commit']}`; no se afirma consulta del bundle runtime.",
        "",
    ])
    return "\n".join(lines)
DRAWERS = (("A", "D1"), ("B", "D2"), ("C", "D3"))


def reference_rows(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Stable E01-E06/A01-C05 codes, each mapped to exactly one CAD piece."""
    rv = model.get("wall_bar_review")
    if not isinstance(rv, dict) or rv.get("drawer_opening_face") != "long_side_front":
        raise DesignError("Entregable solo para la barra aprobada en orientación A.")
    cad = validate_exchange(cad_exchange(model))
    pieces = {p["piece_id"]: p for p in cad["boxes"]}
    if len(pieces) != 28 or len(cad["boxes"]) != 28:
        raise DesignError("El despiece aplicado exige 28 piezas CAD únicas.")
    expected = list(STRUCTURE)
    for letter, did in DRAWERS:
        expected.extend((letter + n, "Cajón " + letter + ": " + label,
                         "CAJONERA_DERECHA-" + did + "-" + suffix)
                        for n, label, suffix in DRAWER_ROLES)
    support_ids = rv.get("conceptual_support_piece_ids", [])
    if len(support_ids) != 4:
        raise DesignError("Se requieren cuatro apoyos CAD conceptuales.")
    expected.extend((f"P{index:02d}", "Marcador CAD de apoyo (no pieza seleccionada)", pid)
                    for index, pid in enumerate(support_ids, start=1))
    if set(pieces) != {pid for _, _, pid in expected}:
        raise DesignError("Los códigos y el CAD no contienen las mismas 28 piezas.")
    rows = []
    for code, label, pid in expected:
        part = pieces[pid]
        x, y, z = part["size_xyz_mm"]
        role = part["role"]
        if min(x, y, z) != 15:
            raise DesignError("Espesor nominal no reconocido: " + pid)
        face = ((x, y) if role == "support_leg_concept"
                else (z, y) if role in ("left_side", "right_side", "drawer_side_left",
                                       "drawer_side_right")
                else (x, z) if role in ("top", "bottom", "drawer_bottom")
                else (x, y))
        rows.append({"referencia": code, "descripcion": label, "id_cad": pid,
                     "cara_a_mm": face[0], "cara_b_mm": face[1],
                     "espesor_mm": 15, "corte_terminado": "NO_VERIFICADO"})
    return rows


def review_files(model: dict[str, Any]) -> dict[str, str]:
    """Plain-language drawer cards, CSV references and review-only notes."""
    from .wall_bar_sheets import format_mm_as_cm, wall_bar_review_dimensions

    rows = reference_rows(model)
    edge_rows = edge_policy_rows(model)
    cad = validate_exchange(cad_exchange(model))
    human = wall_bar_review_dimensions(model)
    pieces = {p["piece_id"]: p for p in cad["boxes"]}
    writer_buffer = StringIO()
    writer = csv.DictWriter(writer_buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    edge_buffer = StringIO()
    edge_writer = csv.DictWriter(edge_buffer, fieldnames=list(edge_rows[0]))
    edge_writer.writeheader()
    edge_writer.writerows(edge_rows)
    result = {
        "CN-BAR-001-referencias.csv": writer_buffer.getvalue(),
        "CN-BAR-001-cantos-por-borde-REVISION.csv": edge_buffer.getvalue(),
        "CN-BAR-001-cantos-por-borde-REVISION.json": (
            json.dumps(edge_rows, ensure_ascii=False, indent=2) + "\n"
        ),
    }
    p6_review = _wall_bar_p6_review(model, edge_rows, cad, human)
    result["CN-BAR-001-P6-revision-constructiva.json"] = (
        json.dumps(p6_review, ensure_ascii=False, indent=2) + "\n"
    )
    result["CN-BAR-001-P6-criterios.md"] = _wall_bar_p6_criteria(p6_review)

    def h_dimension(name: str, x1: float, x2: float, y: float,
                    source_y: float, label: str) -> str:
        center = (x1 + x2) / 2
        return (
            f'<line x1="{x1:.2f}" y1="{source_y:.2f}" x2="{x1:.2f}" y2="{y:.2f}" '
            'stroke="#6b8291" stroke-width="1.4"/>'
            f'<line x1="{x2:.2f}" y1="{source_y:.2f}" x2="{x2:.2f}" y2="{y:.2f}" '
            'stroke="#6b8291" stroke-width="1.4"/>'
            f'<g data-dimension-id="{name}"><line x1="{x1:.2f}" y1="{y:.2f}" '
            f'x2="{x2:.2f}" y2="{y:.2f}" stroke="#315d73" stroke-width="1.8" '
            'marker-start="url(#dim-arrow)" marker-end="url(#dim-arrow)"/>'
            f'<text x="{center:.2f}" y="{y-8:.2f}" text-anchor="middle" '
            f'font-size="17" font-weight="bold" fill="#315d73">{escape(label)}</text></g>'
        )

    def v_dimension(name: str, x: float, y1: float, y2: float,
                    source_x: float, label: str) -> str:
        center = (y1 + y2) / 2
        tx = x - 9
        return (
            f'<line x1="{source_x:.2f}" y1="{y1:.2f}" x2="{x:.2f}" y2="{y1:.2f}" '
            'stroke="#6b8291" stroke-width="1.4"/>'
            f'<line x1="{source_x:.2f}" y1="{y2:.2f}" x2="{x:.2f}" y2="{y2:.2f}" '
            'stroke="#6b8291" stroke-width="1.4"/>'
            f'<g data-dimension-id="{name}"><line x1="{x:.2f}" y1="{y1:.2f}" '
            f'x2="{x:.2f}" y2="{y2:.2f}" stroke="#315d73" stroke-width="1.8" '
            'marker-start="url(#dim-arrow)" marker-end="url(#dim-arrow)"/>'
            f'<text x="{tx:.2f}" y="{center:.2f}" text-anchor="middle" '
            f'transform="rotate(-90 {tx:.2f} {center:.2f})" font-size="17" '
            f'font-weight="bold" fill="#315d73">{escape(label)}</text></g>'
        )

    positions = {"A": "superior", "B": "intermedio", "C": "inferior"}
    plain_parts = {
        "01": "Frente decorativo EXTERIOR aplicado",
        "02": "Pared frontal INTERIOR; no es otra fachada visible",
        "03": "Costado izquierdo",
        "04": "Costado derecho",
        "05": "Pared trasera",
        "06": "Fondo inferior",
    }
    role_color = {
        "drawer_bottom": "#ddc49b", "drawer_side_left": "#aac7d0",
        "drawer_side_right": "#92b7c1", "drawer_front_wall": "#d6b987",
        "drawer_rear_wall": "#b8cbd2", "drawer_facade": "#ffffff",
    }
    for letter, did in DRAWERS:
        subset = [r for r in rows if r["referencia"].startswith(letter)]
        if len(subset) != 6:
            raise DesignError("Caja y frente requieren seis piezas CAD: " + letter)
        face = human["facades"][letter]
        box = human["drawer_boxes"][did]
        face_part = pieces[face["piece_id"]]
        fw, fh, ft = face_part["size_xyz_mm"]
        face_scale = 0.74
        face_left = 255 - fw * face_scale / 2
        face_top = 420 - fh * face_scale / 2
        face_bottom = face_top + fh * face_scale

        box_parts = [pieces[row["id_cad"]] for row in subset
                     if row["id_cad"] != face["piece_id"]]
        if len(box_parts) != 5:
            raise DesignError("La caja deslizante debe conservar cinco paneles: " + letter)
        side_left = next(p for p in box_parts if p["role"] == "drawer_side_left")
        side_right = next(p for p in box_parts if p["role"] == "drawer_side_right")
        front_wall = next(p for p in box_parts if p["role"] == "drawer_front_wall")
        rear_wall = next(p for p in box_parts if p["role"] == "drawer_rear_wall")
        min_x = min(p["origin_xyz_mm"][0] for p in box_parts)
        max_x = max(p["origin_xyz_mm"][0] + p["size_xyz_mm"][0]
                    for p in box_parts)
        min_z = min(p["origin_xyz_mm"][2] for p in box_parts)
        max_z = max(p["origin_xyz_mm"][2] + p["size_xyz_mm"][2]
                    for p in box_parts)
        plan_scale = min(0.70, 420 / (max_x-min_x), 300 / (max_z-min_z))
        plan_left, plan_top = 745.0 - (max_x-min_x)*plan_scale/2, 270.0
        plan_width, plan_depth = (max_x-min_x)*plan_scale, (max_z-min_z)*plan_scale
        inner_x0 = side_left["origin_xyz_mm"][0] + side_left["size_xyz_mm"][0]
        inner_x1 = side_right["origin_xyz_mm"][0]
        inner_z0 = front_wall["origin_xyz_mm"][2] + front_wall["size_xyz_mm"][2]
        inner_z1 = rear_wall["origin_xyz_mm"][2]
        ix = plan_left + (inner_x0-min_x)*plan_scale
        iz = plan_top + (max_z-inner_z1)*plan_scale
        iw, idepth = (inner_x1-inner_x0)*plan_scale, (inner_z1-inner_z0)*plan_scale
        refs_by_id = {row["id_cad"]: row["referencia"] for row in subset}

        svg = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1130" '
            'viewBox="0 0 1600 1130" role="img" '
            f'aria-label="Cajón {letter}: frente aplicado, caja abierta y perspectiva del conjunto armado">',
            '<defs><marker id="dim-arrow" markerWidth="8" markerHeight="8" '
            'refX="4" refY="4" orient="auto-start-reverse">'
            '<path d="M0,0 L8,4 L0,8 z" fill="#315d73"/></marker></defs>',
            '<rect width="1600" height="1130" fill="#ffffff"/>',
            '<rect width="1600" height="128" fill="#183247"/>',
            f'<text x="55" y="55" fill="white" font-size="34" font-weight="bold">'
            f'Cajón {letter} · {positions[letter]}</text>',
            '<text x="55" y="94" fill="#f3d5aa" font-size="19" font-weight="bold">'
            'REVISIÓN NOMINAL · NO CORTAR NI PERFORAR</text>',
            '<rect x="40" y="150" width="430" height="520" rx="14" '
            'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
            '<text x="60" y="184" font-size="18" font-weight="bold">'
            '(1) Frente blanco visible cuando cierra</text>',
            '<rect data-piece-id="' + escape(face_part["piece_id"], quote=True) + '" '
            f'data-piece-reference="{letter}01" x="{face_left:.2f}" y="{face_top:.2f}" '
            f'width="{fw*face_scale:.2f}" height="{fh*face_scale:.2f}" '
            'fill="#ffffff" stroke="#456678" stroke-width="3"/>',
            f'<text x="{face_left+10:.2f}" y="{face_top+22:.2f}" '
            'font-size="14" font-weight="bold" fill="#315d73">'
            f'{letter}01 · EXTERIOR</text>',
            h_dimension(letter+"-front-width", face_left,
                        face_left+fw*face_scale, face_top-24, face_top,
                        f'{format_mm_as_cm(fw)} cm de ancho'),
            v_dimension(letter+"-front-height", face_left+fw*face_scale+31,
                        face_top, face_bottom, face_left+fw*face_scale,
                        f'{format_mm_as_cm(fh)} cm de alto'),
            f'<text x="60" y="615" font-size="17" font-weight="bold">'
            f'{format_mm_as_cm(fw)} × {format_mm_as_cm(fh)} × '
            f'{format_mm_as_cm(ft)} cm</text>',
            '<text x="60" y="642" font-size="13" fill="#536b7e">'
            f'{fw} × {fh} × {ft} mm · objetivo exterior; el frente aplicado es pieza separada.</text>',
            '<rect x="490" y="150" width="510" height="520" rx="14" '
            'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
            '<text x="510" y="184" font-size="18" font-weight="bold">'
            '(2) Caja de madera que se desliza detrás · vista superior</text>',
            '<text x="510" y="213" font-size="14" fill="#536b7e">'
            'Vista abierta de la caja; el frente 01 no se dibuja aquí para leer su interior.</text>',
            f'<rect x="{plan_left:.2f}" y="{plan_top:.2f}" '
            f'width="{plan_width:.2f}" height="{plan_depth:.2f}" '
            'fill="#e7d2ae" stroke="#435c69" stroke-width="2"/>',
        ]
        # The plan and all component references use the five box parts from CAD.
        draw_order = ("drawer_bottom", "drawer_side_left", "drawer_side_right",
                      "drawer_front_wall", "drawer_rear_wall")
        for role in draw_order:
            part = next(p for p in box_parts if p["role"] == role)
            x, _, z = part["origin_xyz_mm"]
            sx, _, sz = part["size_xyz_mm"]
            px = plan_left + (x-min_x)*plan_scale
            py = plan_top + (max_z-z-sz)*plan_scale
            svg.append(
                f'<rect data-piece-id="{escape(part["piece_id"], quote=True)}" '
                f'data-piece-reference="{refs_by_id[part["piece_id"]]}" '
                f'x="{px:.2f}" y="{py:.2f}" width="{sx*plan_scale:.2f}" '
                f'height="{sz*plan_scale:.2f}" fill="{role_color[role]}" '
                'stroke="#405c6b" stroke-width="2"/>'
            )
        svg.extend((
            f'<rect data-inner-clearance="geometric-only" x="{ix:.2f}" y="{iz:.2f}" '
            f'width="{iw:.2f}" height="{idepth:.2f}" fill="none" '
            'stroke="#187b7b" stroke-width="2" stroke-dasharray="7 5"/>',
            f'<text x="{plan_left+plan_width/2:.2f}" y="{plan_top+plan_depth/2:.2f}" '
            'text-anchor="middle" font-size="16" font-weight="bold" fill="#31515e">'
            f'{letter}06 · fondo</text>',
            f'<text x="{plan_left+plan_width/2:.2f}" y="{plan_top+plan_depth+18:.2f}" '
            'text-anchor="middle" font-size="13" font-weight="bold">'
            f'{letter}02 · pared frontal INTERIOR</text>',
            f'<text x="{plan_left+plan_width/2:.2f}" y="{plan_top-7:.2f}" '
            'text-anchor="middle" font-size="13" font-weight="bold">'
            f'{letter}05 · pared trasera</text>',
            f'<text x="{plan_left-6:.2f}" y="{plan_top+plan_depth/2:.2f}" '
            'text-anchor="end" font-size="13" font-weight="bold">'
            f'{letter}03</text>',
            f'<text x="{plan_left+plan_width+6:.2f}" y="{plan_top+plan_depth/2:.2f}" '
            'font-size="13" font-weight="bold">'
            f'{letter}04</text>',
            h_dimension(letter+"-box-width", plan_left,
                        plan_left+plan_width, plan_top+plan_depth+44,
                        plan_top+plan_depth, f'{format_mm_as_cm(box["width_mm"])} cm'),
            f'<text x="510" y="612" font-size="15" font-weight="bold">'
            f'Medida por fuera de la caja que se desliza: '
            f'{format_mm_as_cm(box["width_mm"])} × '
            f'{format_mm_as_cm(box["height_mm"])} × '
            f'{format_mm_as_cm(box["depth_mm"])} cm</text>',
            '<text x="510" y="638" font-size="14" fill="#536b7e">'
            'Espacio útil final: pendiente de validar; correderas sin seleccionar.</text>',
            '<rect x="1020" y="150" width="540" height="520" rx="14" '
            'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
            '<text x="1040" y="184" font-size="18" font-weight="bold">'
            '(3) Perspectiva · conjunto armado desde CAD</text>',
        ))

        all_drawer_parts = [pieces[row["id_cad"]] for row in subset]
        xyz_bounds = []
        for part in all_drawer_parts:
            ox, oy, oz = part["origin_xyz_mm"]
            sx, sy, sz = part["size_xyz_mm"]
            xyz_bounds.extend((x, y, z)
                              for x in (ox, ox+sx)
                              for y in (oy, oy+sy)
                              for z in (oz, oz+sz))
        min_x = min(point[0] for point in xyz_bounds)
        min_y = min(point[1] for point in xyz_bounds)
        min_z = min(point[2] for point in xyz_bounds)

        def oblique_raw(point: tuple[float, float, float]) -> tuple[float, float]:
            x, y, z = point
            return (x-min_x+0.42*(z-min_z),
                    -(y-min_y)-0.28*(z-min_z))

        raw_points = [oblique_raw(point) for point in xyz_bounds]
        raw_left = min(point[0] for point in raw_points)
        raw_right = max(point[0] for point in raw_points)
        raw_top = min(point[1] for point in raw_points)
        raw_bottom = max(point[1] for point in raw_points)
        iso_scale = 0.72
        iso_center_x, iso_center_y = 1290.0, 410.0
        raw_center_x = (raw_left+raw_right)/2
        raw_center_y = (raw_top+raw_bottom)/2

        def oblique_point(point: tuple[float, float, float]) -> tuple[float, float]:
            u, v = oblique_raw(point)
            return (iso_center_x+(u-raw_center_x)*iso_scale,
                    iso_center_y+(v-raw_center_y)*iso_scale)

        def projection_face(part: dict[str, Any],
                            corners: tuple[tuple[float, float, float], ...],
                            fill: str | None = None) -> str:
            points = " ".join(
                f"{x:.2f},{y:.2f}" for x, y in
                (oblique_point(point) for point in corners)
            )
            pid = part["piece_id"]
            return (
                f'<polygon data-projection-view="assembled" '
                f'data-projection-piece-id="{escape(pid, quote=True)}" '
                f'data-projection-reference="{refs_by_id[pid]}" '
                f'points="{points}" fill="{fill or role_color[part["role"]]}" '
                'stroke="#405c6b" stroke-width="2"/>'
            )

        projected_by_role = {part["role"]: part for part in all_drawer_parts}
        svg.append('<g data-assembly-view="assembled">')
        for role in ("drawer_bottom", "drawer_rear_wall", "drawer_side_left",
                     "drawer_side_right", "drawer_front_wall"):
            part = projected_by_role[role]
            x, y, z = part["origin_xyz_mm"]
            sx, sy, sz = part["size_xyz_mm"]
            if role == "drawer_bottom":
                corners = ((x, y+sy, z), (x+sx, y+sy, z),
                           (x+sx, y+sy, z+sz), (x, y+sy, z+sz))
            elif role in ("drawer_side_left", "drawer_side_right"):
                plane_x = x if role == "drawer_side_left" else x+sx
                corners = ((plane_x, y, z), (plane_x, y+sy, z),
                           (plane_x, y+sy, z+sz), (plane_x, y, z+sz))
            elif role in ("drawer_front_wall", "drawer_facade"):
                corners = ((x, y, z), (x+sx, y, z),
                           (x+sx, y+sy, z), (x, y+sy, z))
            else:
                plane_z = z+sz
                corners = ((x, y, plane_z), (x+sx, y, plane_z),
                           (x+sx, y+sy, plane_z), (x, y+sy, plane_z))
            svg.append(projection_face(part, corners))
        facade_part = projected_by_role["drawer_facade"]
        facade_x, facade_y, facade_z = facade_part["origin_xyz_mm"]
        facade_sx, facade_sy, facade_sz = facade_part["size_xyz_mm"]
        svg.extend((
            projection_face(
                facade_part,
                ((facade_x, facade_y+facade_sy, facade_z),
                 (facade_x+facade_sx, facade_y+facade_sy, facade_z),
                 (facade_x+facade_sx, facade_y+facade_sy, facade_z+facade_sz),
                 (facade_x, facade_y+facade_sy, facade_z+facade_sz)),
                "#eef2f4",
            ),
            projection_face(
                facade_part,
                ((facade_x+facade_sx, facade_y, facade_z),
                 (facade_x+facade_sx, facade_y+facade_sy, facade_z),
                 (facade_x+facade_sx, facade_y+facade_sy, facade_z+facade_sz),
                 (facade_x+facade_sx, facade_y, facade_z+facade_sz)),
                "#dce4e8",
            ),
            projection_face(
                facade_part,
                ((facade_x, facade_y, facade_z),
                 (facade_x+facade_sx, facade_y, facade_z),
                 (facade_x+facade_sx, facade_y+facade_sy, facade_z),
                 (facade_x, facade_y+facade_sy, facade_z)),
            ),
        ))
        facade_corners = (
            (face_part["origin_xyz_mm"][0],
             face_part["origin_xyz_mm"][1],
             face_part["origin_xyz_mm"][2]),
            (face_part["origin_xyz_mm"][0]+fw,
             face_part["origin_xyz_mm"][1]+fh,
             face_part["origin_xyz_mm"][2]),
        )
        fx0, fy0 = oblique_point(facade_corners[0])
        fx1, fy1 = oblique_point(facade_corners[1])
        svg.extend((
            f'<text x="{(fx0+fx1)/2:.2f}" y="{(fy0+fy1)/2:.2f}" '
            'text-anchor="middle" font-size="15" font-weight="bold" '
            'fill="#315d73">'
            f'{letter}01 · EXTERIOR</text>',
            '</g>',
            '<text x="1040" y="626" font-size="14" font-weight="bold" fill="#315d73">'
            f'{letter}02 queda detrás de {letter}01 al cerrar; la vista superior muestra la pared.</text>',
            '<text x="1040" y="650" font-size="13" fill="#536b7e">'
            'Sin rieles, tornillos ni fijación dibujados.</text>',
            '<rect x="40" y="700" width="960" height="320" rx="14" '
            'fill="#ffffff" stroke="#d1dce4" stroke-width="2"/>',
            '<text x="66" y="742" font-size="22" font-weight="bold">'
            'Seis piezas nominales · códigos vinculados al CAD</text>',
            '<rect x="1020" y="700" width="540" height="320" rx="14" '
            'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
            '<text x="1045" y="742" font-size="21" font-weight="bold">'
            'Cómo se lee el conjunto</text>',
        ))
        code_positions = ((68, 795), (68, 850), (68, 905),
                          (520, 795), (520, 850), (520, 905))
        code_order = ("01", "02", "03", "04", "05", "06")
        for code, (x, y) in zip(code_order, code_positions):
            svg.extend((
                f'<text x="{x}" y="{y}" font-size="14" font-weight="bold" '
                f'fill="#315d73">{letter}{code}</text>',
                f'<text x="{x+54}" y="{y}" font-size="13" fill="#20394b">'
                f'{escape(plain_parts[code])}</text>',
            ))
        iw_mm, ih_mm, id_mm = box["internal_clear_dimensions_mm"]
        svg.extend((
            '<text x="1045" y="792" font-size="15" fill="#20394b">'
            '1. Primero se forma la caja con cuatro paredes y el fondo.</text>',
            '<text x="1045" y="830" font-size="15" fill="#20394b">'
            '2. Después se fija el frente decorativo aplicado.</text>',
            '<text x="1045" y="870" font-size="14" fill="#536b7e">'
            'Secuencia conceptual; la unión y su fijación no están definidas.</text>',
            '<text x="1045" y="902" font-size="14" fill="#536b7e">'
            f'{letter}02 queda cubierto por {letter}01 cuando cierra; '
            'no es una segunda fachada exterior.</text>',
            f'<text x="68" y="970" font-size="16" font-weight="bold" '
            f'fill="#187b7b">Luz interior geométrica CAD (ancho × alto × fondo): '
            f'{format_mm_as_cm(iw_mm)} × {format_mm_as_cm(ih_mm)} × '
            f'{format_mm_as_cm(id_mm)} cm; sin correderas.</text>',
            '<text x="1045" y="948" font-size="14" fill="#9e2733" font-weight="bold">'
            'Riel, canto y holguras finales pendientes de validar.</text>',
            '<text x="1045" y="980" font-size="14" fill="#9e2733" font-weight="bold">'
            'REVISIÓN NOMINAL · NO CORTAR NI PERFORAR</text>',
            '<text x="50" y="1055" font-size="16" fill="#9e2733" font-weight="bold">'
            'Las vistas explican las piezas; no representan una unión, herraje ni montaje aprobado.</text>',
            f'<text x="50" y="1087" font-size="12" fill="#617688">'
            f'Fuente CAD · {escape(cad["geometry_sha256"])} · NO FABRICAR</text>',
            '</svg>',
        ))
        drawing = "\n".join(svg) + "\n"
        ElementTree.fromstring(drawing)
        result[f"CN-BAR-001-cajon-{letter}.svg"] = drawing

    result["CN-BAR-001-guia-de-armado-REVISION.md"] = (
        "# CN-BAR-001 · Qué sabemos y qué falta (NO FABRICAR)\n\n"
        "1. La barra mide 90 cm de largo, 46 cm de fondo y 90 cm de alto.\n"
        "2. Hay 60 cm libres bajo cubierta y una cajonera de 30 cm en el extremo.\n"
        "3. A va arriba, B en medio y C abajo; cada caja se desliza detrás de su frente.\n"
        "4. Los apoyos dibujados miden 4 cm y solo aparecen bajo la cajonera; no se eligió una pata física.\n"
        "5. A/B/C muestran 4 mm objetivo entre envolventes exteriores terminadas propuestas; la holgura física no está verificada.\n"
        "6. El instalador define la fijación en obra; la cubierta tiene una revisión por borde en el CSV/JSON. Rieles, adhesivo y tolerancias siguen pendientes.\n\n"
        f"Fuente: CAD nominal de {len(cad['boxes'])} elementos; SHA {cad['geometry_sha256']}. "
        "Nada de este borrador autoriza corte, perforación, compra o fabricación.\n"
    )
    return result


def wall_bar_review_cover_svg(model: dict[str, Any]) -> str:
    """Human cover: reuse the actual CAD isometric and the canonical E01 rows."""
    from .wall_bar_sheets import wall_bar_isometric_svg, wall_bar_review_dimensions

    cad = validate_exchange(cad_exchange(model))
    human = wall_bar_review_dimensions(model)
    source = ElementTree.fromstring(wall_bar_isometric_svg(model))
    edge_rows = {row["face_edge"]: row for row in edge_policy_rows(model)
                 if row["piece_id"] == "BAR-COVER-TOP"}
    if set(edge_rows) != {"x_min", "x_max", "y_min", "y_max"}:
        raise DesignError("La cubierta E01 requiere sus cuatro bordes identificados.")
    if cad["bounds_xyz_mm"] != [900, 900, 460]:
        raise DesignError("Portada requiere la barra CN-BAR-001 de 900×460×900 mm.")

    edge_labels = {
        "x_min": "x_min muro",
        "x_max": "x_max libre",
        "y_min": "y_min frente usuario",
        "y_max": "y_max posterior",
    }

    def policy_text(edge: str) -> str:
        row = edge_rows[edge]
        label = edge_labels[edge]
        if row.get("conditional_candidate_policy") == "NO_DECORATIVE_EDGE_CANDIDATE":
            return (f"{label}: sin cinta decorativa solo si queda oculto y seco; "
                    "evaluar sellado.")
        if row.get("conditional_candidate_policy") == "RIGID_PVC_2MM_CANDIDATE_MOISTURE_UNVERIFIED":
            return (f"{label}: PVC rígido 2 mm candidato; "
                    "humedad por verificar, no aprobado.")
        if row["edge_policy"] == "RIGID_PVC_2MM_CANDIDATE":
            return f"{label}: PVC rígido 2 mm candidato, no aprobado."
        return f"{label}: revisar; visibilidad/agua no confirmadas."

    def policy_block(edge: str, y: int) -> str:
        lines = wrap(policy_text(edge), width=54, break_long_words=False,
                     break_on_hyphens=False) or [policy_text(edge)]
        color = ("#315d73" if edge_rows[edge]["edge_policy"]
                 == "RIGID_PVC_2MM_CANDIDATE" else "#536b7e")
        spans = "".join(
            f'<tspan x="1090" dy="{0 if index == 0 else 17}">'
            f'{escape(line)}</tspan>'
            for index, line in enumerate(lines)
        )
        return (f'<text x="1090" y="{y}" font-size="14" font-weight="bold" '
                f'fill="{color}">{spans}</text>')

    source_children = "".join(
        ElementTree.tostring(child, encoding="unicode") for child in list(source)
    )
    edge_colors = {
        edge: ("#b37724" if edge_rows[edge]["certainty"] == "REVIEW_REQUIRED"
               or edge_rows[edge]["certainty"] == "CONDITIONAL_NOT_VERIFIED"
               else "#287b68")
        for edge in edge_rows
    }
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1130"
 viewBox="0 0 1600 1130" role="img" aria-label="Portada isométrica y revisión por borde de la cubierta">
<rect width="1600" height="1130" fill="#ffffff"/>
<g font-family="Arial,sans-serif" fill="#20394b">
<text x="52" y="56" font-size="34" font-weight="bold">Tu barra de cocina · propuesta para revisar</text>
<text x="55" y="91" font-size="18" fill="#9e2733" font-weight="bold">BORRADOR · orientación A · 900 × 460 × 900 mm · NO FABRICAR, CORTAR NI PERFORAR</text>
</g>
<svg x="30" y="108" width="1010" height="720" viewBox="0 113 1038 740" preserveAspectRatio="xMidYMid meet">
{source_children}
</svg>
<rect x="1060" y="112" width="500" height="760" rx="15" fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>
<g font-family="Arial,sans-serif" fill="#20394b">
<text x="1090" y="153" font-size="24" font-weight="bold">Lectura rápida</text>
<text x="1090" y="190" font-size="18">90 cm largo × 46 cm fondo × 90 cm alto</text>
<text x="1090" y="222" font-size="16">60 cm libres + 30 cm cajonera</text>
<text x="1090" y="251" font-size="15">Apoyos conceptuales de 4 cm; no son patas elegidas.</text>
<text x="1090" y="269" font-size="14">Cajones abren por el costado largo.</text>
<line x1="1090" y1="286" x2="1530" y2="286" stroke="#d1dce4"/>
<text x="1090" y="322" font-size="21" font-weight="bold">E01 · cubierta · vista superior</text>
<text x="1090" y="349" font-size="14" fill="#536b7e">Eje X: largo · eje Z: fondo</text>
<rect x="1197" y="395" width="250" height="133" fill="#ead7b4" stroke="#526879" stroke-width="2"/>
<line data-edge="x_min" x1="1197" y1="395" x2="1197" y2="528" stroke="{edge_colors['x_min']}" stroke-width="7"/>
<line data-edge="x_max" x1="1447" y1="395" x2="1447" y2="528" stroke="{edge_colors['x_max']}" stroke-width="7"/>
<line data-edge="y_max" x1="1197" y1="395" x2="1447" y2="395" stroke="{edge_colors['y_max']}" stroke-width="7"/>
<line data-edge="y_min" x1="1197" y1="528" x2="1447" y2="528" stroke="{edge_colors['y_min']}" stroke-width="7"/>
<text x="1322" y="466" text-anchor="middle" font-size="16" font-weight="bold">E01 · 900 × 460 mm</text>
<text x="1186" y="462" text-anchor="end" font-size="13" font-weight="bold">x_min · muro</text>
<text x="1458" y="462" font-size="13" font-weight="bold">x_max · libre</text>
<text x="1322" y="382" text-anchor="middle" font-size="13" font-weight="bold">y_max · posterior</text>
<text x="1322" y="552" text-anchor="middle" font-size="13" font-weight="bold">y_min · frente usuario</text>
{policy_block('x_max', 598)}
{policy_block('y_min', 644)}
{policy_block('x_min', 690)}
{policy_block('y_max', 744)}
<text x="1090" y="831" font-size="13" fill="#9e2733" font-weight="bold">Candidatos no aprobados · dimensión acabada y sellado sin validar.</text>
</g>
<text x="52" y="1078" font-family="Arial,sans-serif" font-size="15" fill="#617688">Isométrica tomada de CADExchange existente · geometría nominal · no representa herrajes, anclajes ni proceso de canto.</text>
<text x="52" y="1104" font-family="Arial,sans-serif" font-size="12" fill="#617688">CAD SHA-256: {escape(cad['geometry_sha256'])}</text>
</svg>'''
    ElementTree.fromstring(svg)
    return svg + "\n"


def review_booklet_svgs(model: dict[str, Any]) -> list[str]:
    """Seven human-first sheets followed by review notes and a technical annex."""
    from .wall_bar_sheets import (format_mm_as_cm,
                                  wall_bar_review_dimensions)

    files = review_files(model)
    rows = reference_rows(model)
    cad = validate_exchange(cad_exchange(model))
    pieces = {piece["piece_id"]: piece for piece in cad["boxes"]}
    human = wall_bar_review_dimensions(model)
    if cad["bounds_xyz_mm"] != [900, 900, 460] or len(cad["boxes"]) != 28:
        raise DesignError("Cuadernillo CN-BAR-001 no coincide con CAD.")

    def title_svg(label: str, body: list[str]) -> str:
        out = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1600" '
            'height="1130" viewBox="0 0 1600 1130">',
            '<rect width="1600" height="1130" fill="#ffffff"/>',
            '<rect width="1600" height="130" fill="#183247"/>',
            '<g font-family="Arial,sans-serif">',
            f'<text x="55" y="60" fill="white" font-size="34" '
            f'font-weight="bold">{escape(label)}</text>',
            '<text x="55" y="99" fill="#f3d5aa" font-size="19" '
            'font-weight="bold">CN-BAR-001 · REVISIÓN NOMINAL · NO FABRICAR</text>',
            *body,
            f'<text x="55" y="1092" font-size="13" fill="#617688">'
            f'Fuente CAD · {len(cad["boxes"])} elementos · SHA-256: '
            f'{escape(cad["geometry_sha256"])} · NO FABRICAR</text>',
            '</g></svg>',
        ]
        svg = "\n".join(out) + "\n"
        ElementTree.fromstring(svg)
        return svg

    edge = model["wall_bar_review"]["front_edgebanding_review"]
    if (edge.get("status") != "FINISHED_TARGET_PROPOSED_CLEARANCE_UNVERIFIED"
            or edge.get("cutting_dimensions_authorized") is not False):
        raise DesignError("El análisis requiere objetivo terminado propuesto y corte bloqueado.")
    gap_ab = human["front_gaps_mm"]["A_B"]
    gap_bc = human["front_gaps_mm"]["B_C"]
    faces = edge["fronts"]
    target_a_w, target_a_h = faces["D1"]["proposed_finished_outer_target_size_mm"]
    target_c_w, target_c_h = faces["D3"]["proposed_finished_outer_target_size_mm"]
    substrate_a_w = faces["D1"]["if_nominal_is_finished_theoretical_raw_width_mm"]
    substrate_a_h = faces["D1"]["if_nominal_is_finished_theoretical_raw_height_mm"]
    substrate_c_w = faces["D3"]["if_nominal_is_finished_theoretical_raw_width_mm"]
    substrate_c_h = faces["D3"]["if_nominal_is_finished_theoretical_raw_height_mm"]
    band = faces["D1"]["rigid_edge_mm_each_side"]
    invalid_raw = edge["raw_interpretation_scenario"]
    if invalid_raw.get("status") != "INVALID_RAW_VS_FINISHED":
        raise DesignError("La interpretación bruta que deja luz cero debe rechazarse.")

    cabinet_left_part = pieces["CAJONERA_DERECHA-LEFT_SIDE"]
    cabinet_right_part = pieces["CAJONERA_DERECHA-RIGHT_SIDE"]
    cabinet_top_part = pieces["CAJONERA_DERECHA-TOP"]
    cabinet_base_part = pieces["CAJONERA_DERECHA-BOTTOM"]
    cabinet_x0 = cabinet_left_part["origin_xyz_mm"][0]
    cabinet_x1 = (cabinet_right_part["origin_xyz_mm"][0]
                  + cabinet_right_part["size_xyz_mm"][0])
    cabinet_y0 = cabinet_base_part["origin_xyz_mm"][1]
    cabinet_y1 = (cabinet_top_part["origin_xyz_mm"][1]
                  + cabinet_top_part["size_xyz_mm"][1])
    cabinet_width, cabinet_height = cabinet_x1-cabinet_x0, cabinet_y1-cabinet_y0
    front_intervals = {}
    for letter, did in DRAWERS:
        facade_id = human["facades"][letter]["piece_id"]
        part = pieces[facade_id]
        x, y, z = part["origin_xyz_mm"]
        width, height, depth = part["size_xyz_mm"]
        front_intervals[letter] = {
            "piece_id": facade_id, "x0": x, "x1": x+width,
            "y0": y, "y1": y+height, "z0": z, "depth": depth,
            "width": width, "height": height,
        }
    front_a, front_b, front_c = (front_intervals[key] for key in "ABC")
    gap_values = {
        "PERIMETER-LEFT": front_a["x0"]-cabinet_x0,
        "PERIMETER-RIGHT": cabinet_x1-front_a["x1"],
        "PERIMETER-TOP": cabinet_y1-front_a["y1"],
        "PERIMETER-BOTTOM": front_c["y0"]-cabinet_y0,
        "A-B": front_a["y0"]-front_b["y1"],
        "B-C": front_b["y0"]-front_c["y1"],
    }
    if (gap_values["A-B"] != gap_ab or gap_values["B-C"] != gap_bc
            or len(set(gap_values.values())) != 1
            or min(gap_values.values()) < 0):
        raise DesignError("Las seis separaciones no coinciden con el CAD y Maestro.")

    drawing_scale = min(0.72, 610/cabinet_height, 350/cabinet_width)
    cabinet_draw_left = 330.0
    cabinet_draw_top = 270.0
    cabinet_draw_right = cabinet_draw_left + cabinet_width*drawing_scale
    cabinet_draw_bottom = cabinet_draw_top + cabinet_height*drawing_scale

    def front_point(x: float, y: float) -> tuple[float, float]:
        return (cabinet_draw_left+(x-cabinet_x0)*drawing_scale,
                cabinet_draw_top+(cabinet_y1-y)*drawing_scale)

    gap_svg_body: list[str] = [
        '<text x="58" y="174" font-size="22" font-weight="bold" '
        'fill="#20394b">Separación objetivo: 4 mm entre envolventes exteriores terminadas propuestas; seis posiciones.</text>',
        '<rect x="55" y="195" width="660" height="700" rx="12" '
        'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
        '<text x="78" y="226" font-size="19" font-weight="bold" fill="#20394b">'
        'Cajonera completa · elevación frontal proporcional al CAD</text>',
        f'<g data-cabinet-outline="drawer-module" '
        f'data-source-width-mm="{cabinet_width}" '
        f'data-source-height-mm="{cabinet_height}">',
        f'<rect x="{cabinet_draw_left:.2f}" y="{cabinet_draw_top:.2f}" '
        f'width="{cabinet_width*drawing_scale:.2f}" '
        f'height="{cabinet_height*drawing_scale:.2f}" '
        'fill="#e6edf0" stroke="#405c6b" stroke-width="3"/>',
    ]
    width_y = cabinet_draw_top-9
    gap_svg_body.extend((
        f'<line x1="{cabinet_draw_left:.2f}" y1="{width_y:.2f}" '
        f'x2="{cabinet_draw_right:.2f}" y2="{width_y:.2f}" '
        'stroke="#315d73" stroke-width="1.8" marker-start="url(#dim-arrow)" '
        'marker-end="url(#dim-arrow)"/>',
        f'<text x="{(cabinet_draw_left+cabinet_draw_right)/2:.2f}" '
        f'y="{width_y-8:.2f}" text-anchor="middle" font-size="16" '
        'font-weight="bold" fill="#315d73">'
        f'{cabinet_width} mm de ancho</text>',
    ))
    for letter in "ABC":
        front = front_intervals[letter]
        fx0, fy0 = front_point(front["x0"], front["y1"])
        fx1, fy1 = front_point(front["x1"], front["y0"])
        gap_svg_body.extend((
            f'<rect data-front-letter="{letter}" '
            f'data-cad-piece-id="{escape(front["piece_id"], quote=True)}" '
            f'data-origin-x-mm="{front["x0"]}" data-origin-y-mm="{front["y0"]}" '
            f'data-width-mm="{front["width"]}" data-height-mm="{front["height"]}" '
            f'x="{fx0:.2f}" y="{fy0:.2f}" width="{fx1-fx0:.2f}" '
            f'height="{fy1-fy0:.2f}" fill="#ffffff" stroke="#52798a" '
            'stroke-width="2"/>',
            f'<text x="{(fx0+fx1)/2:.2f}" y="{(fy0+fy1)/2+6:.2f}" '
            'text-anchor="middle" font-size="20" font-weight="bold" '
            'fill="#315d73">'
            f'{letter}</text>',
        ))
    gap_svg_body.append('</g>')

    perimeter_callouts = (
        ("PERIMETER-LEFT", "Lateral izquierdo",
         (cabinet_x0+front_a["x0"])/2,
         (front_a["y0"]+front_a["y1"])/2, "left"),
        ("PERIMETER-RIGHT", "Lateral derecho",
         (front_a["x1"]+cabinet_x1)/2,
         (front_a["y0"]+front_a["y1"])/2, "right"),
        ("PERIMETER-TOP", "Arriba", (front_a["x0"]+front_a["x1"])/2,
         (front_a["y1"]+cabinet_y1)/2, "top"),
        ("PERIMETER-BOTTOM", "Abajo", (front_c["x0"]+front_c["x1"])/2,
         (cabinet_y0+front_c["y0"])/2, "bottom"),
    )
    for gap_id, label, source_x, source_y, side in perimeter_callouts:
        px, py = front_point(source_x, source_y)
        gap_value = gap_values[gap_id]
        gap_svg_body.append(
            f'<g data-gap-id="{gap_id}" data-gap-kind="perimeter" '
            f'data-nominal-gap-mm="{gap_value}">'
            f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4.5" fill="#d27b27"/>'
            '</g>'
        )
        if side == "left":
            label_x, label_y = cabinet_draw_left-72, py+6
            gap_svg_body.extend((
                f'<path d="M{label_x+8:.2f},{label_y-5:.2f} '
                f'H{px:.2f}" fill="none" stroke="#d27b27" stroke-width="1.5"/>',
                f'<text x="{label_x:.2f}" y="{label_y:.2f}" text-anchor="end" '
                'font-size="14" font-weight="bold" fill="#8c571d">'
                f'{gap_value} mm · {label}</text>',
            ))
        elif side == "right":
            label_x, label_y = cabinet_draw_right+18, py+6
            gap_svg_body.extend((
                f'<path d="M{px:.2f},{py:.2f} H{label_x-4:.2f}" '
                'fill="none" stroke="#d27b27" stroke-width="1.5"/>',
                f'<text x="{label_x:.2f}" y="{label_y:.2f}" '
                'font-size="14" font-weight="bold" fill="#8c571d">'
                f'{gap_value} mm · {label}</text>',
            ))
        else:
            label_x = cabinet_draw_right+18
            label_y = py + (14 if side == "top" else -5)
            gap_svg_body.extend((
                f'<path d="M{px:.2f},{py:.2f} L{label_x-5:.2f},{label_y-5:.2f}" '
                'fill="none" stroke="#d27b27" stroke-width="1.5"/>',
                f'<text x="{label_x:.2f}" y="{label_y:.2f}" '
                'font-size="14" font-weight="bold" fill="#8c571d">'
                f'{gap_value} mm · {label}</text>',
            ))

    detail_cards = (
        ("A-B", "Borde inferior A", "Borde superior B", front_a, front_b, 205),
        ("B-C", "Borde inferior B", "Borde superior C", front_b, front_c, 520),
    )
    for gap_id, upper_label, lower_label, upper, lower, top in detail_cards:
        anchor_y = (upper["y0"]+lower["y1"])/2
        anchor_x = upper["x1"]
        px, py = front_point(anchor_x, anchor_y)
        value = gap_values[gap_id]
        gap_svg_body.append(
            f'<g data-gap-id="{gap_id}" data-gap-kind="interfront" '
            f'data-nominal-gap-mm="{value}">'
            f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4.5" fill="#315d73"/>'
            '</g>'
        )
        card_x, card_width, card_height = 760, 785, 295
        gap_svg_body.extend((
            f'<rect x="{card_x}" y="{top}" width="{card_width}" '
            f'height="{card_height}" rx="12" '
            'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
            f'<text x="{card_x+24}" y="{top+37}" font-size="20" font-weight="bold" '
            f'fill="#20394b">Detalle ampliado {gap_id}</text>',
            f'<text x="{card_x+28}" y="{top+70}" font-size="14" fill="#536b7e">'
            f'{upper_label}</text>',
            f'<rect x="{card_x+28}" y="{top+82}" width="400" height="50" '
            'fill="#d8e8ed" stroke="#52798a" stroke-width="2"/>',
            f'<line x1="{card_x+28}" y1="{top+132}" '
            f'x2="{card_x+428}" y2="{top+132}" '
            'stroke="#d27b27" stroke-width="6"/>',
            f'<text x="{card_x+28}" y="{top+159}" font-size="14" fill="#536b7e">'
            f'{lower_label}</text>',
            f'<rect x="{card_x+28}" y="{top+171}" width="400" height="50" '
            'fill="#e6d2b2" stroke="#52798a" stroke-width="2"/>',
            f'<line x1="{card_x+28}" y1="{top+171}" '
            f'x2="{card_x+428}" y2="{top+171}" '
            'stroke="#d27b27" stroke-width="6"/>',
            f'<g data-gap-detail-for="{gap_id}" '
            f'data-nominal-gap-mm="{value}">',
            f'<line x1="{card_x+500}" y1="{top+132}" '
            f'x2="{card_x+500}" y2="{top+171}" '
            'stroke="#315d73" stroke-width="2.4" marker-start="url(#dim-arrow)" '
            'marker-end="url(#dim-arrow)"/>',
            f'<text x="{card_x+520}" y="{top+150}" font-size="17" '
            'font-weight="bold" fill="#315d73">'
            f'{value} mm libres</text>',
            f'<text x="{card_x+520}" y="{top+174}" font-size="15" '
            'font-weight="bold" fill="#315d73">OBJETIVO</text>',
            '</g>',
            f'<text x="{card_x+520}" y="{top+204}" font-size="14" fill="#536b7e">'
            'entre bordes terminados</text>',
            f'<text x="{card_x+28}" y="{top+257}" font-size="14" '
            'font-weight="bold" fill="#8c571d">'
            'Naranja: PVC rígido 2 mm candidato; el canto físico no está modelado.</text>',
            f'<text x="{card_x+28}" y="{top+279}" font-size="13" fill="#536b7e">'
            'Ampliación esquemática · NO A ESCALA</text>',
        ))
        line_y = py
        leader_y = top+36
        gap_svg_body.append(
            f'<path d="M{px:.2f},{line_y:.2f} L728,{line_y:.2f} '
            f'L748,{leader_y:.2f} H760" fill="none" stroke="#315d73" '
            'stroke-width="1.8"/>'
        )
    gap_svg_body.extend((
        '<rect x="55" y="915" width="1490" height="130" rx="12" '
        'fill="#fff3cf" stroke="#e1b844" stroke-width="2"/>',
        '<text x="78" y="940" font-size="14" fill="#775b11">'
        f'A/B {target_a_w} × {target_a_h} mm y C {target_c_w} × {target_c_h} mm: '
        f'objetivos exteriores terminados; PVC rígido {band} mm por borde candidato.</text>',
        '<text x="78" y="963" font-size="14" fill="#775b11">'
        f'Sustrato teórico ilustrativo (no para sierra): A/B {substrate_a_w} × '
        f'{substrate_a_h} mm; C {substrate_c_w} × {substrate_c_h} mm.</text>',
        '<text x="78" y="985" font-size="14" fill="#775b11">'
        f'Si se toma el objetivo terminado como sustrato bruto y se suma el canto: '
        f'{gap_values["A-B"]} → '
        f'{invalid_raw["theoretical_interfront_gaps_mm"]["D2_D1"]} mm teóricos · '
        'INVALID_RAW_VS_FINISHED; el cero no se acepta como holgura.</text>',
        '<text x="78" y="1008" font-size="15" font-weight="bold" fill="#a12e35">'
        'SIN HOLGURA FÍSICA CERTIFICADA · PROPUESTA NO APROBADA · NO CORTAR</text>',
        '<text x="78" y="1031" font-size="13" fill="#775b11">'
        'La holgura física sigue sin verificar; no es la luz en profundidad para push-to-open ni una holgura de corredera.</text>',
    ))
    gap_svg = title_svg("Separación objetivo y revisión de cantos", gap_svg_body)

    guidance = files["CN-BAR-001-guia-de-armado-REVISION.md"]
    steps = [line.split(". ", 1)[1] for line in guidance.splitlines()
             if len(line) > 3 and line[0] in "123456" and line[1:3] == ". "]
    if len(steps) != 6:
        raise DesignError("La hoja de revisión debe conservar seis ideas breves.")
    guide: list[str] = []
    y = 190
    for index, step in enumerate(steps):
        lines = wrap(step, width=90, break_long_words=False,
                     break_on_hyphens=False) or [""]
        card_height = max(94, 54 + 27 * len(lines))
        card_top = y - 26
        if card_top + card_height > 940:
            raise DesignError("La hoja de pendientes excede su espacio legible.")
        guide.extend((
            f'<rect data-guide-step="{index+1:02d}" x="58" y="{card_top}" '
            f'width="1480" height="{card_height}" rx="9" fill="#f4f8fa" '
            'stroke="#d1dfe6"/>',
            f'<text x="83" y="{y+9}" font-size="27" font-weight="bold" '
            f'fill="#0c5777">{index+1:02d}</text>',
            f'<text data-guide-step="{index+1:02d}" x="155" y="{y+9}" '
            'font-size="20" fill="#20394b">'
            + "".join(
                f'<tspan x="155" dy="{0 if line_index == 0 else 27}">'
                f'{escape(line)}</tspan>'
                for line_index, line in enumerate(lines)
            )
            + "</text>",
        ))
        y = card_top + card_height + 25
    guide.extend((
        '<text x="62" y="990" font-size="19" font-weight="bold" '
        'fill="#a12e35">Los cuatro permisos siguen desactivados: no fabricar, cortar, perforar ni comprar.</text>',
        '<text x="62" y="1024" font-size="17" fill="#536b7e">'
        'El propietario todavía no ha aprobado visualmente el diseño.</text>',
    ))
    guide_svg = title_svg("Lo que sabemos y lo que falta confirmar", guide)

    wood_count = sum(1 for row in rows
                     if pieces[row["id_cad"]]["role"] != "support_leg_concept")
    support_count = len(rows) - wood_count
    if (len(rows) != 28 or wood_count != 24 or support_count != 4):
        raise DesignError("El anexo requiere 24 paneles y 4 marcadores conceptuales.")
    bom = [
        f'<text x="57" y="171" font-size="21" font-weight="bold" '
        f'fill="#183247">{wood_count} paneles nominales de madera + '
        f'{support_count} marcadores conceptuales de apoyo</text>',
        '<text x="57" y="204" font-size="17" fill="#9e2733" font-weight="bold">'
        '28 referencias CAD; no son 28 piezas de madera para cortar. '
        'Medidas en mm · nominales · NO autoriza corte; cantos sin compensación aprobada.</text>',
    ]
    for index, row in enumerate(rows):
        col = index // 14
        line = index % 14
        x = 55 + col * 770
        y = 250 + 58 * line
        size = (f'{row["cara_a_mm"]} × {row["cara_b_mm"]} '
                f'× {row["espesor_mm"]} mm')
        is_support = pieces[row["id_cad"]]["role"] == "support_leg_concept"
        category = "support-concept" if is_support else "wood-panel"
        label = (f'{row["referencia"]} · Marcador conceptual de apoyo '
                 '(no pieza seleccionada)' if is_support else
                 f'{row["referencia"]} · {row["descripcion"]}')
        fill = "#fff3cf" if is_support else "#f4f8fa"
        bom.extend((
            f'<rect data-reference="{escape(row["referencia"], quote=True)}" '
            f'data-category="{category}" '
            f'data-cad-id="{escape(row["id_cad"], quote=True)}" '
            f'data-nominal-size="{escape(size, quote=True)}" '
            f'x="{x}" y="{y-24}" width="720" height="56" rx="6" '
            f'fill="{fill}" stroke="#d1dfe6"/>',
            f'<text data-reference="{escape(row["referencia"], quote=True)}" '
            f'data-bom-field="label" x="{x+12}" y="{y}" font-size="15" '
            f'font-weight="bold" fill="#183247">{escape(label)}</text>',
            f'<text data-reference="{escape(row["referencia"], quote=True)}" '
            f'data-bom-field="size" x="{x+706}" y="{y}" font-size="15" '
            'text-anchor="end" fill="#0c5777">'
            f'{escape(size)}</text>',
            f'<text data-reference="{escape(row["referencia"], quote=True)}" '
            f'data-bom-field="cad-id" x="{x+12}" y="{y+22}" font-size="11" '
            f'fill="#617688">{escape(row["id_cad"])}</text>',
        ))
    bom_svg = title_svg("ANEXO TÉCNICO · códigos de referencia y medidas", bom)

    pages = [
        wall_bar_review_cover_svg(model),
        *(files[f"CN-BAR-001-cajon-{letter}.svg"] for letter in "ABC"),
        gap_svg,
        guide_svg,
        bom_svg,
    ]
    if len(pages) != 7:
        raise DesignError("El cuadernillo humano debe conservar siete hojas.")
    for svg in pages:
        ElementTree.fromstring(svg)
        if cad["geometry_sha256"] not in svg:
            raise DesignError("Hoja sin referencia al CAD canónico.")
    return pages
