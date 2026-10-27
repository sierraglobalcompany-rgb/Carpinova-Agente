"""Review-only delivery sheets for the existing wall-bar CAD; never a cut plan.

Pure presentation layer: every reference and rectangle comes from the
canonical CADExchange boxes. No new geometry, joints, hardware or approvals.
"""
from __future__ import annotations

import csv
from html import escape
from io import StringIO
from typing import Any
from xml.etree import ElementTree

from .cad_exchange import cad_exchange, validate_exchange
from .core import DesignError

STRUCTURE = (
    ("E01", "Cubierta", "BAR-COVER-TOP"),
    ("E02", "Lateral izquierdo", "CAJONERA_DERECHA-LEFT_SIDE"),
    ("E03", "Lateral derecho", "CAJONERA_DERECHA-RIGHT_SIDE"),
    ("E04", "Tapa de cajonera", "CAJONERA_DERECHA-TOP"),
    ("E05", "Base de cajonera", "CAJONERA_DERECHA-BOTTOM"),
    ("E06", "Respaldo", "CAJONERA_DERECHA-BACK_FULL"),
)
DRAWER_ROLES = (
    ("01", "Frente", "DRAWER_FACADE"),
    ("02", "Lateral izquierdo", "DRAWER_SIDE_LEFT"),
    ("03", "Lateral derecho", "DRAWER_SIDE_RIGHT"),
    ("04", "Trasera", "DRAWER_REAR_WALL"),
    ("05", "Fondo", "DRAWER_BOTTOM"),
)
DRAWERS = (("A", "D1"), ("B", "D2"), ("C", "D3"))


def reference_rows(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Stable E01-E06/A01-C05 codes, each mapped to exactly one CAD piece."""
    rv = model.get("wall_bar_review")
    if not isinstance(rv, dict) or rv.get("drawer_opening_face") != "long_side_front":
        raise DesignError("Entregable solo para la barra aprobada en orientación A.")
    cad = validate_exchange(cad_exchange(model))
    pieces = {p["piece_id"]: p for p in cad["boxes"]}
    if len(pieces) != 21 or len(cad["boxes"]) != 21:
        raise DesignError("El despiece exige 21 piezas CAD únicas.")
    expected = list(STRUCTURE)
    for letter, did in DRAWERS:
        expected.extend((letter + n, "Cajón " + letter + ": " + label,
                         "CAJONERA_DERECHA-" + did + "-" + suffix)
                        for n, label, suffix in DRAWER_ROLES)
    if set(pieces) != {pid for _, _, pid in expected}:
        raise DesignError("Los códigos y el CAD no contienen las mismas 21 piezas.")
    rows = []
    for code, label, pid in expected:
        part = pieces[pid]
        x, y, z = part["size_xyz_mm"]
        role = part["role"]
        if min(x, y, z) != 15:
            raise DesignError("Espesor nominal no reconocido: " + pid)
        face = ((z, y) if role in ("left_side", "right_side", "drawer_side_left",
                                  "drawer_side_right")
                else (x, z) if role in ("top", "bottom", "drawer_bottom")
                else (x, y))
        rows.append({"referencia": code, "descripcion": label, "id_cad": pid,
                     "cara_a_mm": face[0], "cara_b_mm": face[1],
                     "espesor_mm": 15, "corte_terminado": "NO_VERIFICADO"})
    return rows


def review_files(model: dict[str, Any]) -> dict[str, str]:
    """Five text outputs: CSV, three separate drawer SVGs, assembly review."""
    rows = reference_rows(model)
    cad = validate_exchange(cad_exchange(model))
    pieces = {p["piece_id"]: p for p in cad["boxes"]}
    writer_buffer = StringIO()
    writer = csv.DictWriter(writer_buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    result = {"CN-BAR-001-referencias.csv": writer_buffer.getvalue()}
    for letter, did in DRAWERS:
        subset = [r for r in rows if r["referencia"].startswith(letter)]
        if len(subset) != 5:
            raise DesignError("Cajón con despiece incompleto: " + letter)
        svg = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1160" height="760" '
            'viewBox="0 0 1160 760" role="img">',
            '<rect width="1160" height="760" fill="white"/>',
            '<g font-family="Arial,sans-serif" fill="#183247">',
            f'<text x="32" y="48" font-size="27" font-weight="bold">'
            f'CN-BAR-001 · HOJA {letter} · CAJÓN {letter}</text>',
            '<text x="32" y="83" font-size="18" fill="#9e2733">'
            'BORRADOR · NO CORTAR · NO PERFORAR · NO FABRICAR</text>',
            '<text x="32" y="119" font-size="15">'
            'PLANTA NOMINAL · cinco piezas CAD · frente hacia abajo</text>',
            '<rect x="610" y="125" width="523" height="460" rx="10" '
            'fill="#f7fafb" stroke="#bacbd6"/>',
            '<text x="630" y="160" font-size="20" font-weight="bold">'
            'DESPIECE DEL CAJÓN</text>',
        ]
        # Back-to-front render order avoids drawing an invented interior part.
        roles = ("DRAWER_BOTTOM", "DRAWER_SIDE_LEFT", "DRAWER_SIDE_RIGHT",
                 "DRAWER_REAR_WALL", "DRAWER_FACADE")
        for suffix in roles:
            row = next(r for r in subset if r["id_cad"].endswith("-" + suffix))
            part = pieces[row["id_cad"]]
            x, _, z = part["origin_xyz_mm"]
            w, _, depth = part["size_xyz_mm"]
            left, top, width, height = (105 + (x-600)*.92, 150 + z*.92,
                                         w*.92, depth*.92)
            fill = "#e7d2a8" if suffix == "DRAWER_BOTTOM" else "#edf2f5"
            svg.append(
                f'<rect data-piece-id="{escape(row["id_cad"], quote=True)}" '
                f'x="{left:.2f}" y="{top:.2f}" width="{width:.2f}" '
                f'height="{height:.2f}" fill="{fill}" '
                'stroke="#36536a" stroke-width="1.5"/>'
            )
            if suffix == "DRAWER_BOTTOM":
                svg.append(f'<text x="{left+width/2:.2f}" '
                           f'y="{top+height/2:.2f}" text-anchor="middle" '
                           f'font-size="18" font-weight="bold">{letter}05</text>')
        for index, row in enumerate(subset):
            y = 212 + 67*index
            svg.extend((
                f'<text x="635" y="{y}" font-size="17" font-weight="bold">'
                f'{row["referencia"]}</text>',
                f'<text x="702" y="{y}" font-size="16">'
                f'{escape(row["descripcion"].split(": ", 1)[-1])}</text>',
                f'<text x="702" y="{y+23}" font-size="13" fill="#506474">'
                f'{row["cara_a_mm"]} × {row["cara_b_mm"]} × '
                f'{row["espesor_mm"]} mm</text>',
            ))
        front = pieces[next(r["id_cad"] for r in subset
                            if r["referencia"] == letter + "01")]
        fw, fh, _ = front["size_xyz_mm"]
        svg.extend((
            f'<rect x="740" y="610" width="{fw*.75:.2f}" '
            f'height="{fh*.22:.2f}" fill="#f0f3f3" stroke="#36536a"/>',
            f'<text x="630" y="635" font-size="14">Frente {letter}01</text>',
            f'<text x="740" y="{650+fh*.22:.2f}" font-size="13">'
            f'{fw} × {fh} × 15 mm</text>',
            f'<text x="32" y="676" font-size="12">'
            f'CAD SHA-256: {escape(cad["geometry_sha256"])}</text>',
            '<text x="32" y="703" font-size="15" fill="#9e2733">'
            'Sin fijaciones, cantos terminados, cargas ni rieles aprobados.</text>',
            '</g></svg>',
        ))
        drawing = "\n".join(svg) + "\n"
        ElementTree.fromstring(drawing)
        result[f"CN-BAR-001-cajon-{letter}.svg"] = drawing
    result["CN-BAR-001-guia-de-armado-REVISION.md"] = (
        "# CN-BAR-001 · Guía preliminar (NO FABRICAR)\n\n"
        f"CAD: `{cad['geometry_sha256']}`; 21 piezas; "
        "mueble 900 × 460 × 900 mm.\n\n"
        "1. Identificar E01–E06 con la tabla de referencias.\n"
        "2. Presentar E02/E03 (laterales), E04/E05 (tapa/base) y E06 "
        "(respaldo); uniones pendientes.\n"
        "3. Preparar A, B y C por separado, cada uno con cinco piezas "
        "numeradas en su hoja; sin perforar hasta validar uniones.\n"
        "4. Elegir rieles comerciales según longitud, holguras y categoría "
        "de carga documentada; no seleccionar marca automáticamente.\n"
        "5. Comprobar frentes, cantos terminados, apertura y roce.\n"
        "6. Presentar cubierta E01; el instalador define en obra "
        "anclaje mural, estabilidad y apoyos.\n\n"
        "**PENDIENTE:** mecanizados, dimensiones terminadas, patas físicas, "
        "uniones resistentes, carga admisible y accesorios. No es un manual "
        "de taller liberado.\n"
    )
    return result
