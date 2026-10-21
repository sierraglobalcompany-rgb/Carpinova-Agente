"""Read canonical CarpiNova-Knowledge *consumer bundles*, never fabricate rules.

The files are produced by CarpiNova-Knowledge; this code does not copy or
reinterpret the source of truth. It performs deterministic evidence retrieval.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import Any


BOOK_ID = "cpnc-2025"
SOURCE_SHA256 = "318ceb94569608bfe062e3e50c7032edee79febf06102f7eec760769a6dfd90c"
REQUIRED_FILES = (
    "knowledge.bundle.json", "figures.bundle.json", "lessons.bundle.json"
)


class BundleError(ValueError):
    """Bundle invalid, stale or not a supported source."""


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleError(f"{context}: se esperaba objeto JSON")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), path.name)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"No se puede leer {path.name}: {exc}") from exc


def load_bundle(directory: str | Path) -> dict[str, Any]:
    """Verify each artifact against its manifest hash before using any content."""
    root = Path(directory)
    manifest = _read_json(root / "manifest.json")
    if manifest.get("book_id") != BOOK_ID:
        raise BundleError("book_id distinto de la fuente canónica cpnc-2025")
    if manifest.get("source_manifest_sha256") != SOURCE_SHA256:
        raise BundleError("Declaración SHA-256 de libro distinta de cpnc-2025")
    hashes = _mapping(manifest.get("files"), "manifest.files")
    if set(hashes) != set(REQUIRED_FILES):
        raise BundleError("El manifiesto no contiene los tres bundles canónicos")
    data = {}
    for filename in REQUIRED_FILES:
        expected_hash = hashes[filename]
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise BundleError(f"SHA-256 inválido en manifest.files[{filename}]")
        try:
            raw = (root / filename).read_bytes()
        except OSError as exc:
            raise BundleError(f"No se puede leer {filename}: {exc}") from exc
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise BundleError(f"Integridad SHA-256 FALLÓ: {filename}")
        try:
            data[filename] = _mapping(json.loads(raw), filename)
        except (ValueError, UnicodeError) as exc:
            raise BundleError(f"JSON inválido en {filename}") from exc
        bundle = data[filename]
        for key in ("book_id", "knowledge_version", "schema_version"):
            if bundle.get(key) != manifest.get(key):
                raise BundleError(f"Metadatos inconsistentes ({key}) en {filename}")
    knowledge = data["knowledge.bundle.json"]
    counts = _mapping(manifest.get("counts"), "manifest.counts")
    for key in ("pages", "content", "measurements", "rules"):
        if not isinstance(knowledge.get(key), list):
            raise BundleError(f"knowledge.bundle.json: {key} no es lista")
        if counts.get(key) != len(knowledge[key]):
            raise BundleError(f"Contador incoherente para {key}")
    for filename, field in (("figures.bundle.json", "figures"),
                            ("lessons.bundle.json", "lessons")):
        sequence = data[filename].get(field)
        if not isinstance(sequence, list) or counts.get(field) != len(sequence):
            raise BundleError(f"Contador o lista incoherente para {field}")
    if manifest.get("scope") == "BOOK":
        if (manifest.get("knowledge_version") != "1.2.0"
                or counts["pages"] != 252
                or manifest.get("source_page_count") != 295
                or manifest.get("excluded_page_count") != 43):
            raise BundleError("La distribución BOOK no cumple el contrato v1.2.0")
    seen_pages = set()
    for item in knowledge["pages"]:
        if not isinstance(item, dict) or not isinstance(item.get("page_id"), str):
            raise BundleError("Registro de página sin identificador válido")
        if item["page_id"] in seen_pages:
            raise BundleError("Identificador de página duplicado")
        seen_pages.add(item["page_id"])
    for item in knowledge["content"]:
        if not isinstance(item, dict) or not isinstance(item.get("content_id"), str):
            raise BundleError("Registro de contenido sin ID válido")
        if item.get("page_id") not in seen_pages:
            raise BundleError("Contenido sin página canónica correspondiente")
        source = item.get("source")
        if not isinstance(source, dict) or source.get("book_id") != BOOK_ID:
            raise BundleError("Procedencia incompleta o libro incorrecto")
        if type(source.get("pdf_page")) is not int:
            raise BundleError("Sin número de página PDF verificable")
    return {
        "manifest": manifest,
        "knowledge": knowledge,
        "coverage": "FULL_BOOK" if manifest.get("scope") == "BOOK" else "PARTIAL_CORPUS",
        "source_pdf_bytes_verified": False,
        "provenance_note": (
            "Se verificaron los hashes de los bundles y la declaración de origen "
            "del manifiesto; no se verificaron bytes del PDF ni autoridad de fabricación."
        ),
    }


def _normalize(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(ch))


def search_content(bundle: dict[str, Any], query: str, limit: int = 5) -> dict[str, Any]:
    """Retrieve teaching text with per-record citations; NOT technical validation."""
    if not isinstance(query, str) or not query.strip():
        raise BundleError("Se necesita una consulta de texto.")
    if type(limit) is not int or not (1 <= limit <= 20):
        raise BundleError("limit debe estar entre 1 y 20.")
    tokens = list(dict.fromkeys(re.findall(r"[a-z0-9]+", _normalize(query))))
    if not tokens:
        raise BundleError("La consulta no contiene términos buscables.")
    candidates = []
    for item in bundle["knowledge"]["content"]:
        normalized = str(item.get("normalized_text") or "")
        learning = str(item.get("learning_text") or "")
        tags = " ".join(str(tag) for tag in item.get("tags", []) if isinstance(tag, str))
        corpus = _normalize(" ".join((normalized, learning, tags)))
        hits = sum(1 for token in tokens if token in corpus)
        if not hits:
            continue
        source = item["source"]
        candidates.append((
            hits,
            {
                "content_id": item["content_id"],
                "page_id": item["page_id"],
                "pdf_page": source["pdf_page"],
                "printed_page": source.get("printed_page"),
                "review_status": source.get("extraction", {}).get("review_status", "UNKNOWN"),
                "text": normalized or learning,
                "tags": item.get("tags", []),
                "source_book": BOOK_ID,
                "manufacturing_authority": False,
            },
        ))
    candidates.sort(key=lambda pair: (-pair[0], pair[1]["pdf_page"],
                                       pair[1]["content_id"]))
    return {
        "query": query,
        "coverage": bundle["coverage"],
        "knowledge_version": bundle["manifest"]["knowledge_version"],
        "results": [item for _, item in candidates[:limit]],
        "total_matches": len(candidates),
        "source_pdf_bytes_verified": bundle["source_pdf_bytes_verified"],
        "technical_use": "REFERENCE_ONLY_NOT_FABRICATION_AUTHORITY",
    }
