"""Conservative topic screening of canonical Knowledge search results.

This is NOT semantic validation. It only checks normalized whole-word
signals within source text and editorial tags, then fails closed if the
requested topic lacks its required context. No rules, dimensions or source
pages are generated here.
"""
from __future__ import annotations

import re
from typing import Any

from .reader import BundleError, _normalize

# Each inner tuple is an obligatory lexical concept family. All families
# must be represented in one source record (text or tags). These are
# search hints, not a claim that a specific woodworking practice is safe.
TOPIC_TERMS: dict[str, tuple[frozenset[str], ...]] = {
    "edge_banding": (
        frozenset({"canto", "cantos", "tapacanto", "tapacantos",
                   "enchapado", "enchapados", "reborde", "bordes"}),
    ),
    "backs_and_services": (
        frozenset({"fondo", "fondos", "trasera", "traseras", "posterior",
                   "posteriores", "respaldo", "respaldos"}),
        frozenset({"tuberia", "tuberias", "desague", "desagues",
                   "sifon", "sifones", "valvula", "valvulas",
                   "instalacion", "instalaciones", "plomeria",
                   "registro", "registros"}),
    ),
    "screws_and_connectors": (
        frozenset({"tornillo", "tornillos", "escuadra", "escuadras",
                   "esquinero", "esquineros", "tarugo", "tarugos",
                   "conector", "conectores", "ensamble", "ensambles"}),
    ),
    "wall_support": (
        frozenset({"pared", "paredes", "muro", "muros", "wall"}),
        frozenset({"anclaje", "anclajes", "riel", "rieles", "liston",
                   "listones", "frances", "francesa", "suspension",
                   "soporte", "soportes", "colgado", "colgar"}),
    ),
    "floor_support": (
        frozenset({"pata", "patas", "banquero", "zocalo", "zocalos",
                   "pedestal", "pedestales", "base", "bases"}),
    ),
    # This category documents SITE SURVEY context, not a construction
    # method for backs, cutouts or plumbing connections.
    "site_survey": (
        frozenset({"levantamiento", "medidas", "medicion", "obra",
                   "croquis", "esquema", "replanteo"}),
        frozenset({"instalaciones", "hidrosanitarios", "hidrosanitarias",
                   "electricos", "electricas", "tuberias", "tuberia",
                   "desague", "desagues", "puntos"}),
    ),
}


def _words(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _normalize(value)))


def screen_topic_results(search_result: dict[str, Any],
                         topic: str) -> dict[str, Any]:
    """Return a filtered shallow copy; NEVER promote a lexical hit to a rule.

    total_matches retains the reader's raw lexical count. Relevance
    metrics are scoped to this sampled search window, not the full book.
    """
    if type(topic) is not str or topic not in TOPIC_TERMS:
        raise BundleError("Tema de pertinencia no reconocido.")
    if not isinstance(search_result, dict) or not isinstance(
            search_result.get("results"), list):
        raise BundleError("Se necesitan resultados del lector Knowledge.")
    groups = TOPIC_TERMS[topic]
    selected: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for item in search_result["results"]:
        if not isinstance(item, dict) or type(item.get("content_id")) is not str:
            raise BundleError("Registro de contenido inválido para auditoría.")
        raw_tags = item.get("tags", [])
        if not isinstance(raw_tags, list):
            raw_tags = []
        text_words = _words(str(item.get("text", "")))
        tag_words = _words(" ".join(x for x in raw_tags if type(x) is str))
        text_signals = [sorted(text_words & family) for family in groups]
        all_signals = [sorted((text_words | tag_words) & family)
                       for family in groups]
        direct = all(bool(hits) for hits in text_signals)
        candidate = all(bool(hits) for hits in all_signals)
        status = ("TEXT_CONTEXT_CANDIDATE" if direct else
                  "TEXT_AND_TAG_CANDIDATE" if candidate else
                  "NO_TOPIC_CONTEXT_IN_SAMPLE")
        reports.append({
            "content_id": item["content_id"],
            "pdf_page": item.get("pdf_page"),
            "relation_status": status,
            "matched_terms": all_signals,
            "technical_rule_verified": False,
            "source_pdf_page_visually_checked_here": False,
        })
        if candidate:
            # All original text and page refs are retained unchanged.
            selected.append(item)
    # A direct text hit is stronger lexical evidence than tags alone, but
    # BOTH are still only candidates, never verified construction guidance.
    relation = {entry["content_id"]: entry["relation_status"] for entry in reports}
    selected.sort(key=lambda item: (
        0 if relation[item["content_id"]] == "TEXT_CONTEXT_CANDIDATE" else 1,
        item["pdf_page"], item["content_id"],
    ))
    audit = {
        "topic": topic,
        "status": ("LEXICAL_CANDIDATES_REQUIRE_HUMAN_REVIEW" if selected
                   else "NO_CONTEXT_CANDIDATES_IN_SEARCH_SAMPLE"),
        "sampled_result_count": len(search_result["results"]),
        "candidate_count_in_sample": len(selected),
        "returned_candidate_count": min(len(selected), 5),
        "original_lexical_total_matches": search_result["total_matches"],
        "reviewed_against_original_pdf": False,
        "technical_suitability_verified": False,
        "manufacturer_spec_verified": False,
        "records": reports,
        "limitation": (
            "Coincidencia de términos completos y etiquetas en una muestra "
            "de resultados. No equivale a pertinencia semántica, revisión "
            "humana de la página original ni regla para fabricar."
        ),
    }
    # Keep the chat/CLI brief: at most five cited records, while retaining
    # the screening counts for the wider 20-record diagnostic window.
    return {**search_result, "results": selected[:5], "relevance_review": audit}
