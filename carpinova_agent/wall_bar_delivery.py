"""Review-only delivery sheets for the existing wall-bar CAD; never a cut plan.

Pure presentation layer: every reference and rectangle comes from the
canonical CADExchange boxes. No new geometry, joints, hardware or approvals.
"""
from __future__ import annotations

import csv
from html import escape
from io import StringIO
from textwrap import wrap
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
    ("01", "Fachada decorativa aplicada", "DRAWER_FACADE"),
    ("02", "Pared frontal interior", "DRAWER_FRONT_WALL"),
    ("03", "Lateral izquierdo", "DRAWER_SIDE_LEFT"),
    ("04", "Lateral derecho", "DRAWER_SIDE_RIGHT"),
    ("05", "Trasera", "DRAWER_REAR_WALL"),
    ("06", "Fondo", "DRAWER_BOTTOM"),
)
DRAWERS = (("A", "D1"), ("B", "D2"), ("C", "D3"))


def reference_rows(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Stable E01-E06/A01-C05 codes, each mapped to exactly one CAD piece."""
    rv = model.get("wall_bar_review")
    if not isinstance(rv, dict) or rv.get("drawer_opening_face") != "long_side_front":
        raise DesignError("Entregable solo para la barra aprobada en orientación A.")
    cad = validate_exchange(cad_exchange(model))
    pieces = {p["piece_id"]: p for p in cad["boxes"]}
    if len(pieces) != 24 or len(cad["boxes"]) != 24:
        raise DesignError("El despiece aplicado exige 24 piezas CAD únicas.")
    expected = list(STRUCTURE)
    for letter, did in DRAWERS:
        expected.extend((letter + n, "Cajón " + letter + ": " + label,
                         "CAJONERA_DERECHA-" + did + "-" + suffix)
                        for n, label, suffix in DRAWER_ROLES)
    if set(pieces) != {pid for _, _, pid in expected}:
        raise DesignError("Los códigos y el CAD no contienen las mismas 24 piezas.")
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
        if len(subset) != 6:
            raise DesignError("Caja y fachada requieren seis piezas CAD: " + letter)
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
            'PLANTA NOMINAL · caja completa + fachada separada</text>',
            '<rect x="610" y="125" width="523" height="460" rx="10" '
            'fill="#f7fafb" stroke="#bacbd6"/>',
            '<text x="630" y="160" font-size="20" font-weight="bold">'
            'DESPIECE DEL CAJÓN</text>',
        ]
        # Render the canonical six CAD boxes from the rear of the plan to the
        # applied facade; the front wall stays visible as its own rectangle.
        roles = ("DRAWER_BOTTOM", "DRAWER_SIDE_LEFT", "DRAWER_SIDE_RIGHT",
                 "DRAWER_REAR_WALL", "DRAWER_FRONT_WALL", "DRAWER_FACADE")
        for suffix in roles:
            row = next(r for r in subset if r["id_cad"].endswith("-" + suffix))
            part = pieces[row["id_cad"]]
            x, _, z = part["origin_xyz_mm"]
            w, _, depth = part["size_xyz_mm"]
            left, top, width, height = (105 + (x-600)*.92, 150 + z*.92,
                                         w*.92, depth*.92)
            fill = ("#e7d2a8" if suffix == "DRAWER_BOTTOM" else
                    "#f4d7a0" if suffix == "DRAWER_FRONT_WALL" else
                    "#cde4e8" if suffix == "DRAWER_FACADE" else "#edf2f5")
            svg.append(
                f'<rect data-piece-id="{escape(row["id_cad"], quote=True)}" '
                f'x="{left:.2f}" y="{top:.2f}" width="{width:.2f}" '
                f'height="{height:.2f}" fill="{fill}" '
                'stroke="#36536a" stroke-width="1.5"/>'
            )
            if suffix == "DRAWER_BOTTOM":
                svg.append(f'<text x="{left+width/2:.2f}" '
                           f'y="{top+height/2:.2f}" text-anchor="middle" '
                           f'font-size="18" font-weight="bold">{letter}06</text>')
        # Visual cross-references for all six real panels, not only the floor.
        # Leaders and labels are annotations; they never change CAD geometry.
        callouts = (
            (letter + "01", 195, 145, 235, 150),
            (letter + "02", 275, 190, 355, 174),
            (letter + "03", 42, 347, 128, 347),
            (letter + "04", 400, 347, 355, 347),
            (letter + "05", 224, 557, 235, 530),
        )
        for ref, tx, ty, px, py in callouts:
            svg.extend((
                # Start the leader clear of the three-character reference;
                # otherwise the line runs through labels such as A02/A06.
                f'<path d="M{tx+44},{ty+4} L{px},{py}" fill="none" '
                'stroke="#5c7690" stroke-width="1.3"/>',
                f'<text x="{tx}" y="{ty}" font-size="17" '
                f'font-weight="bold" fill="#183247">{ref}</text>',
            ))
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
        f"CAD: `{cad['geometry_sha256']}`; 24 piezas nominales: seis de carcasa "
        "y seis por cajón (cuatro paredes, fondo y fachada decorativa separada); "
        "mueble 900 × 460 × 900 mm.\n\n"
        "1. Identificar E01–E06 con la tabla de referencias.\n"
        "2. Presentar E02/E03 (laterales), E04/E05 (tapa/base) y E06 "
        "(respaldo); uniones pendientes.\n"
        "3. Secuencia conceptual: caja cerrada de cuatro paredes y fondo; "
        "validar la corredera exacta y presentarla nivelada; solo después "
        "montar y ajustar la fachada decorativa separada. La fijación aún "
        "no está especificada.\n"
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


def review_booklet_svgs(model: dict[str, Any]) -> list[str]:
    """Exactly seven review pages: CAD views, A/B/C, BOM and assembly notes.

    Reuses the existing SVG projections and five archived review artifacts.
    Never adds physical panels or selects hardware.
    """
    from .wall_bar_sheets import wall_bar_isometric_svg, wall_bar_orientation_svg

    files = review_files(model)
    rows = reference_rows(model)
    cad = validate_exchange(cad_exchange(model))
    if cad["bounds_xyz_mm"] != [900, 900, 460]:
        raise DesignError("Paquete CN-BAR-001 no coincide con dimensiones CAD.")

    def title_svg(label: str, body: list[str]) -> str:
        out = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1600" '
            'height="1130" viewBox="0 0 1600 1130">',
            '<rect width="1600" height="1130" fill="#ffffff"/>',
            '<rect width="1600" height="130" fill="#183247"/>',
            '<g font-family="Arial,sans-serif">',
            f'<text x="55" y="60" fill="white" font-size="37" '
            f'font-weight="bold">{escape(label)}</text>',
            '<text x="55" y="99" fill="#e5ecf0" font-size="20">'
            'CN-BAR-001 · REVISION NOMINAL · NO FABRICAR</text>',
            *body,
            f'<text x="55" y="1092" font-size="15" fill="#617688">'
            f'24 IDs CAD · SHA-256: {escape(cad["geometry_sha256"])} · NO FABRICAR</text>',
            '</g></svg>',
        ]
        svg = "\n".join(out) + "\n"
        ElementTree.fromstring(svg)
        return svg

    bom = [
        '<text x="57" y="173" font-size="23" font-weight="bold" '
        'fill="#183247">REFERENCIA / PIEZA / MEDIDA NOMINAL</text>',
        '<text x="57" y="207" font-size="18" fill="#9e2733">'
        'Los tamaños indicados NO incorporan descuentos verificados de cantos.</text>',
    ]
    for index, row in enumerate(rows):
        col = index // 12
        line = index % 12
        x = 55 + col * 770
        y = 250 + 66 * line
        size = (f'{row["cara_a_mm"]} × {row["cara_b_mm"]} '
                f'× {row["espesor_mm"]} mm')
        bom.extend((
            f'<rect data-reference="{escape(row["referencia"], quote=True)}" '
            f'data-cad-id="{escape(row["id_cad"], quote=True)}" '
            f'data-nominal-size="{escape(size, quote=True)}" '
            f'x="{x}" y="{y-24}" width="720" height="56" rx="6" '
            'fill="#f4f8fa" stroke="#d1dfe6"/>',
            f'<text data-reference="{escape(row["referencia"], quote=True)}" '
            f'data-bom-field="label" x="{x+12}" y="{y}" font-size="16" font-weight="bold" '
            f'fill="#183247">{escape(row["referencia"])} · '
            f'{escape(row["descripcion"])}</text>',
            f'<text data-reference="{escape(row["referencia"], quote=True)}" '
            f'data-bom-field="size" x="{x+706}" y="{y}" font-size="15" text-anchor="end" '
            f'fill="#0c5777">{escape(size)}</text>',
            f'<text data-reference="{escape(row["referencia"], quote=True)}" '
            f'data-bom-field="cad-id" x="{x+12}" y="{y+22}" font-size="12" '
            f'fill="#617688">{escape(row["id_cad"])}</text>',
        ))
    bom_svg = title_svg("DESPIECE NOMINAL · 24 PIEZAS", bom)
    guidance = files["CN-BAR-001-guia-de-armado-REVISION.md"]
    steps = [line.split(". ", 1)[1] for line in guidance.splitlines()
             if len(line) > 3 and line[0] in "123456" and line[1:3] == ". "]
    if len(steps) != 6:
        raise DesignError("La guía de armado no conserva sus seis pasos.")
    manual = [
        '<text x="58" y="186" font-size="24" fill="#183247" '
        'font-weight="bold">ORDEN DE PRESENTACION Y REVISION</text>',
    ]
    y = 230
    for index, step in enumerate(steps):
        lines = wrap(step, width=100, break_long_words=False,
                     break_on_hyphens=False) or [""]
        card_height = max(87, 54 + 26 * len(lines))
        card_top = y - 26
        card_bottom = card_top + card_height
        if card_bottom > 950:
            raise DesignError("La guía de armado excede el espacio de revisión.")
        manual.extend((
            f'<rect data-guide-step="{index+1:02d}" x="58" '
            f'y="{card_top}" width="1480" height="{card_height}" rx="9" '
            'fill="#f4f8fa" stroke="#d1dfe6"/>',
            f'<text x="83" y="{y+10}" font-size="28" font-weight="bold" '
            f'fill="#0c5777">{index+1:02d}</text>',
        ))
        manual.append(
            f'<text data-guide-step="{index+1:02d}" x="159" y="{y+10}" '
            'font-size="20" fill="#183247">'
            + "".join(
                f'<tspan x="159" dy="{0 if line_index == 0 else 26}">'
                f'{escape(line)}</tspan>'
                for line_index, line in enumerate(lines)
            )
            + "</text>"
        )
        y = card_bottom + 16 + 26
    manual.extend((
        '<text x="62" y="985" font-size="20" font-weight="bold" '
        'fill="#9e2733">PENDIENTE: fijaciones, apoyo, cargas, cantos '
        'terminados y patrón de perforación.</text>',
        '<text x="62" y="1022" font-size="18" fill="#617688">'
        'El apoyo mural y su seguridad los verifica el instalador en obra.</text>',
    ))
    guide_svg = title_svg("GUIA PRELIMINAR · SIN MECANIZADOS", manual)
    def labeled_overview(svg: str, *, elevation: bool) -> str:
        # D1-D3 stay canonical CAD IDs. A/B/C are stable CLIENT references,
        # not replacements for geometry or data-model IDs.
        for letter, did in DRAWERS:
            old = f'>{did}</text>'
            if svg.count(old) != 1:
                raise DesignError("Vista general sin cajón identificable: " + did)
            svg = svg.replace(old, f'>{letter}</text>', 1)
        if not svg.endswith("</g></svg>\n"):
            raise DesignError("Cierre inesperado de vista general.")
        if elevation:
            note = (
                '<text x="752" y="934" font-size="19" font-weight="bold" '
                'fill="#183247">HOJAS DEL MANUAL</text>'
                '<text x="752" y="970" font-size="16" fill="#183247">'
                'A = superior (CAD D1)</text>'
                '<text x="752" y="1002" font-size="16" fill="#183247">'
                'B = intermedio (CAD D2)</text>'
                '<text x="752" y="1034" font-size="16" fill="#183247">'
                'C = inferior (CAD D3)</text>'
                '<text x="752" y="1074" font-size="15" fill="#183247">'
                'E01 cubierta; E02-E06 carcasa</text>'
            )
        else:
            note = (
                '<text x="55" y="104" font-size="15" fill="white">'
                'HOJAS A/B/C = superior/intermedio/inferior · E01 cubierta</text>'
            )
        return svg.replace("</g></svg>\n", note + "</g></svg>\n", 1)

    pages = [
        labeled_overview(wall_bar_isometric_svg(model), elevation=False),
        labeled_overview(wall_bar_orientation_svg(model), elevation=True),
        *(files[f"CN-BAR-001-cajon-{letter}.svg"] for letter in "ABC"),
        bom_svg,
        guide_svg,
    ]
    if len(pages) != 7:
        raise DesignError("Paquete incompleto: se requieren siete hojas.")
    for svg in pages:
        ElementTree.fromstring(svg)
        if cad["geometry_sha256"] not in svg:
            raise DesignError("Hoja sin referencia geométrica CAD.")
    return pages
