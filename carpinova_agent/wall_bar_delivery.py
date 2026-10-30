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
    cad = validate_exchange(cad_exchange(model))
    human = wall_bar_review_dimensions(model)
    pieces = {p["piece_id"]: p for p in cad["boxes"]}
    writer_buffer = StringIO()
    writer = csv.DictWriter(writer_buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    result = {"CN-BAR-001-referencias.csv": writer_buffer.getvalue()}

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
        "01": "Frente blanco visible cuando cierra",
        "02": "Pared delantera interior de la caja; no es otra tapa visible",
        "03": "Costado izquierdo",
        "04": "Costado derecho",
        "05": "Pared trasera",
        "06": "Base o fondo horizontal de abajo",
    }
    for letter, did in DRAWERS:
        subset = [r for r in rows if r["referencia"].startswith(letter)]
        if len(subset) != 6:
            raise DesignError("Caja y frente requieren seis piezas CAD: " + letter)
        face = human["facades"][letter]
        box = human["drawer_boxes"][did]
        face_part = pieces[face["piece_id"]]
        fx, fy, _ = face_part["origin_xyz_mm"]
        fw, fh, ft = face_part["size_xyz_mm"]
        face_scale = min(0.8, 440 / fw, 300 / fh)
        face_left = 400 - fw * face_scale / 2
        face_top = 435 - fh * face_scale / 2
        face_bottom = face_top + fh * face_scale

        box_parts = [pieces[row["id_cad"]] for row in subset
                     if row["id_cad"] != face["piece_id"]]
        if len(box_parts) != 5:
            raise DesignError("La caja deslizante debe conservar cinco paneles: " + letter)
        min_x = min(p["origin_xyz_mm"][0] for p in box_parts)
        max_x = max(p["origin_xyz_mm"][0] + p["size_xyz_mm"][0]
                    for p in box_parts)
        min_z = min(p["origin_xyz_mm"][2] for p in box_parts)
        max_z = max(p["origin_xyz_mm"][2] + p["size_xyz_mm"][2]
                    for p in box_parts)
        plan_scale = min(0.58, 380 / (max_x-min_x), 300 / (max_z-min_z))
        plan_left, plan_top = 1060.0, 270.0
        plan_width, plan_depth = (max_x-min_x)*plan_scale, (max_z-min_z)*plan_scale
        side_left = next(p for p in box_parts if p["role"] == "drawer_side_left")
        side_right = next(p for p in box_parts if p["role"] == "drawer_side_right")
        front_wall = next(p for p in box_parts if p["role"] == "drawer_front_wall")
        rear_wall = next(p for p in box_parts if p["role"] == "drawer_rear_wall")
        bottom = next(p for p in box_parts if p["role"] == "drawer_bottom")
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
            f'aria-label="Cajón {letter}: frente visible y caja deslizante con dimensiones nominales">',
            '<defs><marker id="dim-arrow" markerWidth="8" markerHeight="8" '
            'refX="4" refY="4" orient="auto-start-reverse">'
            '<path d="M0,0 L8,4 L0,8 z" fill="#315d73"/></marker></defs>',
            '<rect width="1600" height="1130" fill="#ffffff"/>',
            '<rect width="1600" height="128" fill="#183247"/>',
            f'<text x="55" y="55" fill="white" font-size="34" font-weight="bold">'
            f'Cajón {letter} · {positions[letter]}</text>',
            '<text x="55" y="94" fill="#f3d5aa" font-size="19" font-weight="bold">'
            'REVISIÓN NOMINAL · NO CORTAR NI PERFORAR</text>',
            '<rect x="40" y="150" width="720" height="520" rx="14" '
            'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
            '<text x="70" y="196" font-size="23" font-weight="bold">'
            '(1) Frente blanco visible cuando cierra</text>',
            '<rect data-piece-id="' + escape(face_part["piece_id"], quote=True) + '" '
            f'x="{face_left:.2f}" y="{face_top:.2f}" '
            f'width="{fw*face_scale:.2f}" height="{fh*face_scale:.2f}" '
            'fill="#ffffff" stroke="#456678" stroke-width="3"/>',
            f'<text x="{face_left+12:.2f}" y="{face_top+24:.2f}" '
            'font-size="14" font-weight="bold" fill="#587083">'
            f'{letter}01</text>',
            h_dimension(letter+"-front-width", face_left,
                        face_left+fw*face_scale, face_top-32, face_top,
                        f'{format_mm_as_cm(fw)} cm de ancho'),
            v_dimension(letter+"-front-height", face_left+fw*face_scale+33,
                        face_top, face_bottom, face_left+fw*face_scale,
                        f'{format_mm_as_cm(fh)} cm de alto'),
            f'<text x="70" y="622" font-size="18" font-weight="bold">'
            f'{format_mm_as_cm(fw)} × {format_mm_as_cm(fh)} × '
            f'{format_mm_as_cm(ft)} cm</text>',
            '<text x="70" y="649" font-size="15" fill="#536b7e">'
            'Ancho × alto × espesor · el frente es una pieza separada</text>',
            '<rect x="840" y="150" width="720" height="520" rx="14" '
            'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
            '<text x="870" y="196" font-size="23" font-weight="bold">'
            '(2) Caja de madera que se desliza detrás</text>',
            '<text x="870" y="226" font-size="15" fill="#536b7e">'
            'Vista desde arriba; las líneas punteadas muestran de dónde se mide el interior.</text>',
            f'<rect x="{plan_left:.2f}" y="{plan_top:.2f}" '
            f'width="{plan_width:.2f}" height="{plan_depth:.2f}" '
            'fill="#e7d2ae" stroke="#435c69" stroke-width="2"/>',
        ]
        # Paint each panel from its exact CAD rectangle; the floor is first,
        # then the four walls are drawn over its edges in the top view.
        draw_order = ("drawer_bottom", "drawer_side_left", "drawer_side_right",
                      "drawer_front_wall", "drawer_rear_wall")
        role_color = {
            "drawer_bottom": "#ddc49b", "drawer_side_left": "#aac7d0",
            "drawer_side_right": "#aac7d0", "drawer_front_wall": "#d6b987",
            "drawer_rear_wall": "#b8cbd2",
        }
        for role in draw_order:
            part = next(p for p in box_parts if p["role"] == role)
            x, _, z = part["origin_xyz_mm"]
            sx, _, sz = part["size_xyz_mm"]
            px = plan_left + (x-min_x)*plan_scale
            py = plan_top + (max_z-z-sz)*plan_scale
            svg.append(
                f'<rect data-piece-id="{escape(part["piece_id"], quote=True)}" '
                f'x="{px:.2f}" y="{py:.2f}" width="{sx*plan_scale:.2f}" '
                f'height="{sz*plan_scale:.2f}" fill="{role_color[role]}" '
                'stroke="#405c6b" stroke-width="2"/>'
            )
        svg.extend((
            f'<rect data-inner-clearance="geometric-only" x="{ix:.2f}" y="{iz:.2f}" '
            f'width="{iw:.2f}" height="{idepth:.2f}" fill="none" '
            'stroke="#187b7b" stroke-width="2" stroke-dasharray="7 5"/>',
            f'<text x="{plan_left+plan_width/2:.2f}" y="{plan_top+plan_depth/2:.2f}" '
            'text-anchor="middle" font-size="17" font-weight="bold" fill="#31515e">'
            f'{letter}06 · fondo</text>',
            f'<text x="{plan_left+plan_width/2:.2f}" y="{plan_top+plan_depth+18:.2f}" '
            'text-anchor="middle" font-size="14" font-weight="bold">'
            f'{letter}02 · pared delantera</text>',
            f'<text x="{plan_left+plan_width/2:.2f}" y="{plan_top-7:.2f}" '
            'text-anchor="middle" font-size="14" font-weight="bold">'
            f'{letter}05 · pared trasera</text>',
            f'<text x="{plan_left-6:.2f}" y="{plan_top+plan_depth/2:.2f}" '
            'text-anchor="end" font-size="14" font-weight="bold">'
            f'{letter}03</text>',
            f'<text x="{plan_left+plan_width+6:.2f}" y="{plan_top+plan_depth/2:.2f}" '
            'font-size="14" font-weight="bold">'
            f'{letter}04</text>',
            h_dimension(letter+"-box-width", plan_left,
                        plan_left+plan_width, plan_top+plan_depth+72,
                        plan_top+plan_depth, f'{format_mm_as_cm(box["width_mm"])} cm'),
            '<path d="M770 405 H822" stroke="#315d73" stroke-width="3" '
            'marker-end="url(#dim-arrow)"/>',
            '<text x="796" y="390" text-anchor="middle" font-size="14" '
            'font-weight="bold">detrás</text>',
            f'<text x="870" y="604" font-size="17" font-weight="bold">'
            f'Medida por fuera de la caja que se desliza: '
            f'{format_mm_as_cm(box["width_mm"])} × '
            f'{format_mm_as_cm(box["height_mm"])} × '
            f'{format_mm_as_cm(box["depth_mm"])} cm</text>',
            '<text x="870" y="630" font-size="15" fill="#536b7e">'
            'Ancho × alto × fondo · la caja sale hacia el frente al abrir.</text>',
            '<text x="870" y="650" font-size="14" fill="#315d73">'
            'Medidas por fuera; no son espacio útil interior.</text>',
            '<rect x="40" y="700" width="1520" height="320" rx="14" '
            'fill="#ffffff" stroke="#d1dce4" stroke-width="2"/>',
            '<text x="66" y="742" font-size="23" font-weight="bold">'
            'Qué significa cada código</text>',
        ))
        code_positions = ((68, 790), (810, 790), (68, 850), (810, 850),
                          (68, 910), (810, 910))
        code_order = ("01", "02", "03", "04", "05", "06")
        for code, (x, y) in zip(code_order, code_positions):
            svg.extend((
                f'<text x="{x}" y="{y}" font-size="16" font-weight="bold" '
                f'fill="#315d73">{letter}{code}</text>',
                f'<text x="{x+66}" y="{y}" font-size="16" fill="#20394b">'
                f'{escape(plain_parts[code])}</text>',
            ))
        iw_mm, ih_mm, id_mm = box["internal_clear_dimensions_mm"]
        svg.extend((
            '<text x="68" y="970" font-size="17" font-weight="bold" '
            'fill="#187b7b">Luz interior geométrica CAD (ancho × alto × fondo): '
            f'{format_mm_as_cm(iw_mm)} × {format_mm_as_cm(ih_mm)} × '
            f'{format_mm_as_cm(id_mm)} cm</text>',
            '<text x="68" y="995" font-size="15" fill="#536b7e">'
            'Cálculo entre las caras de las paredes y la base; sin rieles. '
            'Espacio útil final: pendiente de validar.</text>',
            '<text x="50" y="1055" font-size="16" fill="#9e2733" font-weight="bold">'
            'Riel, canto y fijación del frente sin especificar. Esta vista no los representa ni los valida.</text>',
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
        "5. El dibujo muestra 2 mm nominales entre frentes; el canto puede consumir ese espacio.\n"
        "6. Rieles, medidas terminadas, fijación en obra por instalador, cargas y estabilidad siguen pendientes.\n\n"
        f"Fuente: CAD nominal de {len(cad['boxes'])} elementos; SHA {cad['geometry_sha256']}. "
        "Nada de este borrador autoriza corte, perforación, compra o fabricación.\n"
    )
    return result


def review_booklet_svgs(model: dict[str, Any]) -> list[str]:
    """Seven human-first sheets followed by review notes and a technical annex."""
    from .wall_bar_sheets import (format_mm_as_cm, wall_bar_orientation_svg,
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
    if (edge.get("status") != "PENDING_FINISHED_VS_RAW_INTERPRETATION"
            or edge.get("cutting_dimensions_authorized") is not False):
        raise DesignError("El análisis de cantos requiere interpretación pendiente y corte bloqueado.")
    gap_ab = human["front_gaps_mm"]["A_B"]
    gap_bc = human["front_gaps_mm"]["B_C"]
    faces = edge["fronts"]
    raw_a = faces["D1"]["if_nominal_is_raw_resulting_width_mm"]
    raw_c = faces["D3"]["if_nominal_is_raw_resulting_width_mm"]
    finish_a_w = faces["D1"]["if_nominal_is_finished_theoretical_raw_width_mm"]
    finish_a_h = faces["D1"]["if_nominal_is_finished_theoretical_raw_height_mm"]
    finish_c_w = faces["D3"]["if_nominal_is_finished_theoretical_raw_width_mm"]
    finish_c_h = faces["D3"]["if_nominal_is_finished_theoretical_raw_height_mm"]
    band = faces["D1"]["rigid_edge_mm_each_side"]
    gap_svg_body: list[str] = [
        '<text x="58" y="174" font-size="22" font-weight="bold" '
        'fill="#20394b">El dibujo deja 2 mm nominales entre frentes; aún no sabemos si quedarán libres.</text>',
    ]
    for gap_id, upper, lower, value, left in (
        ("A-B", "Borde inferior A", "Borde superior B", gap_ab, 55),
        ("B-C", "Borde inferior B", "Borde superior C", gap_bc, 815),
    ):
        gap_svg_body.extend((
            f'<rect x="{left}" y="205" width="730" height="285" rx="12" '
            'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
            f'<text x="{left+24}" y="243" font-size="22" font-weight="bold" '
            f'fill="#20394b">Detalle ampliado {gap_id}</text>',
            f'<text x="{left+28}" y="285" font-size="15" fill="#536b7e">{upper}</text>',
            f'<rect x="{left+28}" y="300" width="420" height="58" '
            'fill="#d8e8ed" stroke="#52798a" stroke-width="2"/>',
            f'<rect x="{left+28}" y="378" width="420" height="58" '
            'fill="#e6d2b2" stroke="#52798a" stroke-width="2"/>',
            f'<text x="{left+28}" y="463" font-size="15" fill="#536b7e">{lower}</text>',
            f'<g data-gap-id="{gap_id}" data-nominal-gap-mm="{value}">',
            f'<line x1="{left+448}" y1="358" x2="{left+448}" y2="378" '
            'stroke="#315d73" stroke-width="2.4" marker-start="url(#dim-arrow)" '
            'marker-end="url(#dim-arrow)"/>',
            f'<text x="{left+475}" y="373" font-size="20" font-weight="bold" '
            f'fill="#315d73">{value} mm nominales</text>',
            '</g>',
            f'<text x="{left+475}" y="410" font-size="14" fill="#536b7e">'
            'Ampliación esquemática, no a escala</text>',
        ))
    gap_svg_body.extend((
        '<rect x="55" y="515" width="1490" height="110" rx="12" '
        'fill="#fff3cf" stroke="#e1b844" stroke-width="2"/>',
        '<text x="80" y="555" font-size="22" font-weight="bold" fill="#775b11">'
        'El dibujo dice 2 mm; todavía no sabemos si después del canto quedará espacio real.</text>',
        '<text x="80" y="592" font-size="19" font-weight="bold" fill="#a12e35">'
        'NO RESUELTO · NO CORTAR</text>',
        '<rect x="55" y="650" width="730" height="220" rx="12" '
        'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
        '<text x="80" y="691" font-size="21" font-weight="bold">'
        'Si la medida es del tablero sin canto</text>',
        '<text x="80" y="730" font-size="18">'
        f'{format_mm_as_cm(296)} cm + {band} mm de canto por borde '
        f'→ {format_mm_as_cm(raw_a)} cm de ancho final teórico.',
        '<tspan x="80" dy="30">En A-B y B-C, la luz pasaría a una interferencia teórica de -2 mm.</tspan>',
        '<tspan x="80" dy="30">No es una predicción validada del taller ni una cota para fabricar.</tspan></text>',
        '<rect x="815" y="650" width="730" height="220" rx="12" '
        'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
        '<text x="840" y="691" font-size="21" font-weight="bold">'
        'Si la medida es el frente terminado deseado</text>',
        '<text x="840" y="730" font-size="18">'
        f'A/B: {finish_a_w} × {finish_a_h} mm ({format_mm_as_cm(finish_a_w)} × '
        f'{format_mm_as_cm(finish_a_h)} cm) de sustrato teórico.',
        f'<tspan x="840" dy="28">C: {finish_c_w} × {finish_c_h} mm '
        f'({format_mm_as_cm(finish_c_w)} × {format_mm_as_cm(finish_c_h)} cm).</tspan>',
        f'<tspan x="840" dy="28">{finish_a_w} mm teóricos, no para sierra.</tspan>',
        '<tspan x="840" dy="28">Faltan proceso, adhesivo y tolerancias; no son medidas aprobadas.</tspan></text>',
        '<text x="58" y="915" font-size="18" font-weight="bold" fill="#315d73">'
        '3 mm finales: alternativa a evaluar, no seleccionada; no es norma ni cambió el CAD.</text>',
        '<text x="58" y="952" font-size="17" fill="#536b7e">'
        'La separación entre frentes se ve de frente; no es la luz en profundidad para push-to-open. Ese sistema y su ficha siguen pendientes.</text>',
    ))
    gap_svg = title_svg("Separaciones y canto: qué significa 2 mm", gap_svg_body)

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
        wall_bar_orientation_svg(model),
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
