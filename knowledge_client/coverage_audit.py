"""Lexical coverage evidence per woodworking topic, not semantic certification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .reader import load_bundle, search_content

TOPICS={
    "materials":["tablero","melamina","canto","veta"],
    "hardware":["bisagra","corredera","tornillo","escuadra"],
    "tools":["taladro","sierra","fresadora"],
    "cutting":["despiece","optimización","corte"],
    "furniture":["cajón","cocina","clóset","closet","fondo","patas"],
    "installation":["listón francés","riel","banquero","tubería"],
}


def audit_knowledge_lexical(directory: str | Path)->dict:
    bundle=load_bundle(directory)
    groups={}
    for group,terms in TOPICS.items():
        rows=[]
        for term in terms:
            found=search_content(bundle,term,limit=5)
            rows.append({
                "term":term,
                "matched_content_records":found["total_matches"],
                "sample_pages":[{"pdf_page":x["pdf_page"],
                    "content_id":x["content_id"],
                    "review_status":x["review_status"]}
                    for x in found["results"][:3]],
                "status":"LEXICAL_MATCHES_EXIST" if found["total_matches"] else "NEEDS_MANUAL_REVIEW",
            })
        groups[group]=rows
    return {
        "scope":bundle["coverage"],
        "knowledge_version":bundle["manifest"]["knowledge_version"],
        "source_pdf_verified_directly":False,
        "not_semantic_coverage_proof":True,
        "source_count_pages":bundle["manifest"]["counts"]["pages"],
        "query_groups":groups,
        "notes":[
            "Cero coincidencias no demuestra ausencia del concepto (sinónimos/dibujos).",
            "Coincidencia léxica no demuestra que la respuesta o su medida sea correcta.",
            "Cotejar muestras con páginas originales y fichas vigentes antes de automatizar.",
        ],
    }


def main()->None:
    p=argparse.ArgumentParser(description="Auditoría léxica de temas del libro CarpiNova.")
    p.add_argument("--bundle-dir",required=True,type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    a.output.write_text(json.dumps(audit_knowledge_lexical(a.bundle_dir),
        ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
