"""Per-part traceable review sheet derived from canonical CADExchange boxes.

Never re-solves furniture dimensions. No manufacturing cut instructions.
"""
from __future__ import annotations

import csv
from html import escape
from io import StringIO
from typing import Any
from xml.etree import ElementTree

from .cad_exchange import cad_exchange, validate_exchange
from .core import DesignError
from .wall_bar import AESTHETIC_PRESENTATION_CHOICES


def wall_bar_review_dimensions(model: dict[str, Any]) -> dict[str, Any]:
    """Describe human-review dimensions from the one canonical CADExchange."""
    review = model.get("wall_bar_review")
    if not isinstance(review, dict):
        raise DesignError("Resumen de cotas requiere una barra canónica.")
    cad = validate_exchange(cad_exchange(model))
    boxes = cad["boxes"]
    dimensions = cad["bounds_xyz_mm"]
    fronts = [box for box in boxes if box["role"] == "drawer_facade"]
    supports = [box for box in boxes if box["role"] == "support_leg_concept"]
    if len(fronts) != 3 or len(supports) != 4:
        raise DesignError("Cotas humanas requieren tres frentes y cuatro apoyos conceptuales.")
    front_by_drawer = {
        did: next((box for box in fronts if f"-{did}-" in box["piece_id"]), None)
        for did in ("D1", "D2", "D3")
    }
    if any(box is None for box in front_by_drawer.values()):
        raise DesignError("Fachadas CAD sin identidad D1/D2/D3.")

    drawer_boxes = {}
    for did in ("D1", "D2", "D3"):
        members = [box for box in boxes
                   if box["role"].startswith("drawer_")
                   and box["role"] != "drawer_facade"
                   and f"-{did}-" in box["piece_id"]]
        if len(members) != 5:
            raise DesignError("Caja completa CAD incompleta: " + did)
        low = [min(box["origin_xyz_mm"][axis] for box in members)
               for axis in range(3)]
        high = [max(box["origin_xyz_mm"][axis] + box["size_xyz_mm"][axis]
                    for box in members) for axis in range(3)]
        by_role = {box["role"]: box for box in members}
        required = {"drawer_side_left", "drawer_side_right", "drawer_front_wall",
                    "drawer_rear_wall", "drawer_bottom"}
        if set(by_role) != required:
            raise DesignError("Caja completa CAD con roles inesperados: " + did)
        left_side = by_role["drawer_side_left"]
        right_side = by_role["drawer_side_right"]
        front_wall = by_role["drawer_front_wall"]
        rear_wall = by_role["drawer_rear_wall"]
        bottom = by_role["drawer_bottom"]
        inside = (
            right_side["origin_xyz_mm"][0] -
            (left_side["origin_xyz_mm"][0] + left_side["size_xyz_mm"][0]),
            left_side["origin_xyz_mm"][1] + left_side["size_xyz_mm"][1] -
            (bottom["origin_xyz_mm"][1] + bottom["size_xyz_mm"][1]),
            rear_wall["origin_xyz_mm"][2] -
            (front_wall["origin_xyz_mm"][2] + front_wall["size_xyz_mm"][2]),
        )
        if min(inside) <= 0:
            raise DesignError("Luz interior CAD no positiva: " + did)
        drawer_boxes[did] = {
            "width_mm": high[0] - low[0],
            "height_mm": high[1] - low[1],
            "depth_mm": high[2] - low[2],
            "internal_clear_dimensions_mm": list(inside),
            "piece_ids": [box["piece_id"] for box in members],
        }
    face_summary = {}
    for letter, did in (("A", "D1"), ("B", "D2"), ("C", "D3")):
        box = front_by_drawer[did]
        face_summary[letter] = {
            "drawer_id": did, "piece_id": box["piece_id"],
            "width_mm": box["size_xyz_mm"][0],
            "height_mm": box["size_xyz_mm"][1],
            "thickness_mm": box["size_xyz_mm"][2],
            "origin_y_mm": box["origin_xyz_mm"][1],
        }
    ordered = sorted(face_summary.items(), key=lambda item: item[1]["origin_y_mm"])
    gaps = {}
    for (lower_letter, lower), (upper_letter, upper) in zip(ordered, ordered[1:]):
        gaps[f"{upper_letter}_{lower_letter}"] = (
            upper["origin_y_mm"] - (lower["origin_y_mm"] + lower["height_mm"]))
    cabinet_x0, cabinet_x1 = review["cabinet_x_range_mm"]
    face_x0 = min(box["origin_xyz_mm"][0] for box in fronts)
    face_x1 = max(box["origin_xyz_mm"][0] + box["size_xyz_mm"][0]
                  for box in fronts)
    sides = [box for box in boxes if box["role"] in ("left_side", "right_side")]
    if len(sides) != 2:
        raise DesignError("Laterales de carcasa LI/LD no coinciden con el CAD.")
    support_size = supports[0]["size_xyz_mm"]
    if any(box["size_xyz_mm"] != support_size or box["origin_xyz_mm"][1] != 0
           for box in supports):
        raise DesignError("Bloques de apoyo CAD no comparten altura/huella nominal.")
    return {
        "width_mm": dimensions[0], "height_mm": dimensions[1],
        "depth_mm": dimensions[2],
        "free_span_mm": review["free_span_mm"],
        "cabinet_width_mm": cabinet_x1 - cabinet_x0,
        "support_count": len(supports),
        "support_height_mm": support_size[1],
        "support_footprint_width_mm": support_size[0],
        "support_footprint_depth_mm": support_size[2],
        "support_piece_ids": [box["piece_id"] for box in supports],
        "facades": face_summary,
        "drawer_boxes": drawer_boxes,
        "front_gaps_mm": gaps,
        "left_front_reveal_mm": face_x0 - cabinet_x0,
        "right_front_reveal_mm": cabinet_x1 - face_x1,
        "carcass_side_size_xyz_mm": sides[0]["size_xyz_mm"],
    }


def part_schedule(model: dict[str, Any]) -> list[dict[str, Any]]:
    cad = validate_exchange(cad_exchange(model))
    parts = model["parts"]
    source = {p["piece_id"]: p for p in parts}
    if len(source) != len(parts):
        raise DesignError("Piezas fuente con ID repetido.")
    if set(source) != {b["piece_id"] for b in cad["boxes"]}:
        raise DesignError("Inventario y CAD difieren.")
    rows = []
    for item in cad["boxes"]:
        part = source[item["piece_id"]]
        front = item["role"] == "drawer_facade"
        support_concept = item["role"] == "support_leg_concept"
        role = item["role"]
        drawer_id = part.get("drawer_id", "")
        rows.append({
            "piece_id": item["piece_id"],
            "drawer_id": drawer_id,
            "role": role,
            "material_id": item["material_id"],
            "face_x_mm": part["nominal_face_x_mm"],
            "face_y_mm": part["nominal_face_y_mm"],
            "thickness_mm": part["thickness_mm"],
            "origin_xyz_mm": ",".join(map(str, item["origin_xyz_mm"])),
            "size_xyz_mm": ",".join(map(str, item["size_xyz_mm"])),
            "edge_policy": ("CONCEPTO_SIN_CANTO_APROBADO" if support_concept
                            else "RIGIDO_FRENTES_2MM_CANDIDATO" if front
                            else "FLEXIBLE_RESTANTES_0_45MM_CANDIDATO"),
            "edge_positions": ("NO_APLICA_CONCEPTO" if support_concept
                               else "CUATRO_BORDES_NOMINALES" if front
                               else "PENDIENTE_POR_PIEZA"),
            "finished_cut_dimensions_mm": "NOT_VERIFIED",
            "cad_geometry_sha256": cad["geometry_sha256"],
        })
    return rows


def part_schedule_csv(model: dict[str, Any]) -> str:
    rows = part_schedule(model)
    dest = StringIO()
    writer = csv.DictWriter(dest, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return dest.getvalue()


def part_schedule_svg(model: dict[str, Any]) -> str:
    """One panel per row with code and dimensions, without invented geometry."""
    rows = part_schedule(model)
    height = 130 + 105 * len(rows)
    fragments = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1150" height="{height}" '
        f'viewBox="0 0 1150 {height}" role="img" '
        f'aria-label="Despiece nominal CarpiNova con referencias">',
        '<style>text{font-family:Arial,sans-serif;fill:#192436}'
        '.panel{fill:#fbfaf7;stroke:#cbd5e1}'
        '.wood{fill:#ded0b8;stroke:#405269}'
        '.front{fill:#c5e1e5;stroke:#235268}'
        '.support{fill:#a89a88;stroke:#544637}'
        '.name{font-size:17px;font-weight:bold}'
        '.info{font-size:14px}'
        '.warning{font-size:17px;fill:#a62525;font-weight:bold}</style>',
        '<text x="30" y="42" font-size="25" font-weight="bold">'
        'CARPINOVA · Fichas por pieza verificable</text>',
        '<text x="30" y="72" class="warning">'
        'BORRADOR · NO CORTAR · NO PERFORAR · NO FABRICAR</text>',
    ]
    for i, row in enumerate(rows):
        y = 95 + i * 105
        w, h = row["face_x_mm"], row["face_y_mm"]
        scale = min(0.16, 295/max(w, 1), 65/max(h, 1))
        wd, ht = w*scale, h*scale
        front = row["role"] == "drawer_facade"
        support_concept = row["role"] == "support_leg_concept"
        fragments.extend([
            f'<rect x="20" y="{y}" width="1100" height="94" rx="8" class="panel"/>',
            f'<rect x="45" y="{y+12}" width="{wd:.2f}" height="{ht:.2f}" '
            f'class="{"front" if front else "support" if support_concept else "wood"}"/>',
            f'<text x="390" y="{y+27}" class="name">{escape(row["piece_id"])}</text>',
            f'<text x="390" y="{y+51}" class="info">'
            f'{w} × {h} × {row["thickness_mm"]} mm · {escape(row["role"])}</text>',
            f'<text x="390" y="{y+76}" class="info">'
            f'{"Apoyo conceptual, no SKU" if support_concept else "Canto: " + escape(row["edge_policy"])} · corte final NO VALIDADO</text>',
        ])
    fragments.append("</svg>")
    return "\n".join(fragments) + "\n"


def format_mm_as_cm(value_mm: int) -> str:
    """Format one CAD millimeter value as readable Spanish centimeters."""
    if type(value_mm) is not int:
        raise DesignError("La conversión visible mm→cm requiere milímetros enteros.")
    sign = "-" if value_mm < 0 else ""
    whole, tenth = divmod(abs(value_mm), 10)
    value = str(whole) if tenth == 0 else f"{whole},{tenth}"
    return sign + value


def wall_bar_orientation_svg(model: dict[str, Any]) -> str:
    """Human main sheet: plan/elevation and dimensions projected from CAD."""
    rv = model.get("wall_bar_review")
    if (not isinstance(rv, dict) or rv.get("drawer_opening_face") != "long_side_front"
            or rv.get("drawer_open_direction") != "negative_Z"
            or rv.get("wall_side") != "left"):
        raise DesignError("Lámina humana requiere orientación A confirmada.")
    cad = validate_exchange(cad_exchange(model))
    w, h, d = cad["bounds_xyz_mm"]
    fronts = [box for box in cad["boxes"] if box["role"] == "drawer_facade"]
    covers = [box for box in cad["boxes"] if box["piece_id"] == "BAR-COVER-TOP"]
    supports = [box for box in cad["boxes"]
                if box["role"] == "support_leg_concept"]
    human = wall_bar_review_dimensions(model)
    if (len(cad["boxes"]) != 28 or len(fronts) != 3 or len(covers) != 1
            or len(supports) != 4 or (w, h, d) != (900, 900, 460)):
        raise DesignError("La lámina humana requiere el CAD CN-BAR-001 conocido.")
    choices = rv.get("design_choices", {})
    aesthetic = choices.get("aesthetic_presentation", "undecided")
    if (type(aesthetic) is not str
            or aesthetic not in AESTHETIC_PRESENTATION_CHOICES):
        raise DesignError("Opción estética no soportada por la lámina humana.")

    def h_dimension(name: str, x1: float, x2: float, y: float,
                    source_y1: float, source_y2: float,
                    label: str) -> str:
        tx = (x1 + x2) / 2
        return (
            f'<line x1="{x1:.2f}" y1="{source_y1:.2f}" x2="{x1:.2f}" '
            f'y2="{y:.2f}" stroke="#668094" stroke-width="1.5"/>'
            f'<line x1="{x2:.2f}" y1="{source_y2:.2f}" x2="{x2:.2f}" '
            f'y2="{y:.2f}" stroke="#668094" stroke-width="1.5"/>'
            f'<g data-dimension-id="{name}"><line x1="{x1:.2f}" y1="{y:.2f}" '
            f'x2="{x2:.2f}" y2="{y:.2f}" stroke="#244b63" stroke-width="2" '
            'marker-start="url(#dim-arrow)" marker-end="url(#dim-arrow)"/>'
            f'<text x="{tx:.2f}" y="{y-10:.2f}" text-anchor="middle" '
            f'font-size="20" font-weight="bold" fill="#244b63">{escape(label)}</text>'
            '</g>'
        )

    def v_dimension(name: str, x: float, y1: float, y2: float,
                    source_x1: float, source_x2: float,
                    label: str) -> str:
        mid = (y1 + y2) / 2
        return (
            f'<line x1="{source_x1:.2f}" y1="{y1:.2f}" x2="{x:.2f}" '
            f'y2="{y1:.2f}" stroke="#668094" stroke-width="1.5"/>'
            f'<line x1="{source_x2:.2f}" y1="{y2:.2f}" x2="{x:.2f}" '
            f'y2="{y2:.2f}" stroke="#668094" stroke-width="1.5"/>'
            f'<g data-dimension-id="{name}"><line x1="{x:.2f}" y1="{y1:.2f}" '
            f'x2="{x:.2f}" y2="{y2:.2f}" stroke="#244b63" stroke-width="2" '
            'marker-start="url(#dim-arrow)" marker-end="url(#dim-arrow)"/>'
            f'<text x="{x-13:.2f}" y="{mid:.2f}" text-anchor="middle" '
            f'transform="rotate(-90 {x-13:.2f} {mid:.2f})" font-size="20" '
            f'font-weight="bold" fill="#244b63">{escape(label)}</text></g>'
        )

    plan_x, plan_y = 170.0, 360.0
    plan_scale = min(0.58, 540 / w, 350 / d)
    plan_w, plan_d = w * plan_scale, d * plan_scale
    plan_x1, plan_y1 = plan_x + plan_w, plan_y + plan_d
    cabinet_x0 = plan_x + human["free_span_mm"] * plan_scale
    cabinet_x1 = plan_x1
    grain_paths = []
    if aesthetic == "bicolor_modern_preliminary":
        for ratio in (0.2, 0.4, 0.6, 0.8):
            y = plan_y + plan_d * ratio
            grain_paths.append(
                f'<path data-concept="decorative-grain" data-axis="X" '
                f'd="M{plan_x+18:.2f} {y:.2f}H{cabinet_x0-18:.2f}" '
                'fill="none" stroke="#9a7448" stroke-width="1.4" opacity=".48"/>'
            )

    elev_x, elev_y = 1000.0, 315.0
    elev_scale = min(0.45, 520 / w, 430 / h)
    elev_y1 = elev_y + h * elev_scale
    elev_x1 = elev_x + w * elev_scale
    cab0, cab1 = rv["cabinet_x_range_mm"]
    cy0, cy1 = rv["cabinet_y_range_mm"]
    cab_px0, cab_px1 = elev_x + cab0 * elev_scale, elev_x + cab1 * elev_scale
    cab_py0 = elev_y + (h - cy1) * elev_scale
    cab_py1 = elev_y + (h - cy0) * elev_scale

    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1130" '
        'viewBox="0 0 1600 1130" role="img" '
        'aria-label="Barra de cocina: vista superior y elevación con cotas humanas">',
        '<defs><marker id="dim-arrow" markerWidth="8" markerHeight="8" '
        'refX="4" refY="4" orient="auto-start-reverse">'
        '<path d="M0,0 L8,4 L0,8 z" fill="#244b63"/></marker></defs>',
        '<rect width="1600" height="1130" fill="#ffffff"/>',
        '<g font-family="Arial,sans-serif" fill="#20394b">',
        '<text x="48" y="58" font-size="38" font-weight="bold">Tu barra de cocina</text>',
        '<text x="50" y="96" font-size="21" fill="#587083">'
        'Propuesta visual para revisar · orientación A · medidas en centímetros</text>',
        '<text x="50" y="127" font-size="17" fill="#a12e35" font-weight="bold">'
        'BORRADOR · NO CORTAR, PERFORAR NI FABRICAR</text>',
        '<rect x="35" y="145" width="730" height="790" rx="18" '
        'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
        '<text x="62" y="190" font-size="25" font-weight="bold">'
        'Desde arriba · dónde queda cada extremo</text>',
        '<rect x="785" y="145" width="780" height="790" rx="18" '
        'fill="#f8fafb" stroke="#d1dce4" stroke-width="2"/>',
        '<text x="815" y="190" font-size="25" font-weight="bold">'
        'De frente · cómo se reparte el largo</text>',
        '<text x="65" y="222" font-size="17" fill="#536b7e">'
        'Muro en el extremo corto; cajones abren por el costado largo.</text>',
        '<text x="817" y="222" font-size="17" fill="#536b7e">'
        'Las patas dibujadas son conceptuales y aparecen solo bajo la cajonera.</text>',
    ]

    length_label = f'{format_mm_as_cm(w)} cm de largo'
    depth_label = f'{format_mm_as_cm(d)} cm de fondo'
    free_label = f'{format_mm_as_cm(human["free_span_mm"])} cm libres'
    cabinet_label = f'{format_mm_as_cm(human["cabinet_width_mm"])} cm cajonera'
    lines.extend((
        f'<path d="M{plan_x-12:.2f} 350 V638" stroke="#475d6b" stroke-width="9"/>',
        '<text x="50" y="493" font-size="18" font-weight="bold">MURO</text>',
        '<text x="50" y="519" font-size="15">extremo corto</text>',
        f'<rect x="{plan_x:.2f}" y="{plan_y:.2f}" width="{plan_w:.2f}" '
        f'height="{plan_d:.2f}" fill="#efe4d2" stroke="#334b5c" stroke-width="3"/>',
        *grain_paths,
        f'<rect x="{cabinet_x0:.2f}" y="{plan_y:.2f}" '
        f'width="{cabinet_x1-cabinet_x0:.2f}" height="{plan_d:.2f}" '
        'fill="#bcd6df" fill-opacity=".78" stroke="#546e7b" stroke-dasharray="7 4"/>',
        f'<text x="{(plan_x+cabinet_x0)/2:.2f}" y="{plan_y+plan_d/2-3:.2f}" '
        'text-anchor="middle" font-size="23" font-weight="bold">60 cm libres</text>',
        f'<text x="{(cabinet_x0+cabinet_x1)/2:.2f}" y="{plan_y+plan_d/2-3:.2f}" '
        'text-anchor="middle" font-size="19" font-weight="bold">30 cm</text>',
        f'<text x="{(cabinet_x0+cabinet_x1)/2:.2f}" y="{plan_y+plan_d/2+25:.2f}" '
        'text-anchor="middle" font-size="16">cajonera</text>',
        h_dimension("plan-length", plan_x, plan_x1, plan_y-62,
                    plan_y, plan_y, length_label),
        v_dimension("plan-depth", plan_x1+35, plan_y, plan_y1,
                    plan_x1, plan_x1, depth_label),
        h_dimension("plan-free-span", plan_x, cabinet_x0, plan_y1+52,
                    plan_y1, plan_y1, free_label),
        h_dimension("plan-cabinet-width", cabinet_x0, cabinet_x1, plan_y1+100,
                    plan_y1, plan_y1, cabinet_label),
        f'<path d="M{(cabinet_x0+cabinet_x1)/2:.2f} {plan_y1:.2f} '
        f'v32" stroke="#315d73" stroke-width="3" marker-end="url(#dim-arrow)"/>',
        f'<text x="{(cabinet_x0+cabinet_x1)/2:.2f}" y="{plan_y1+165:.2f}" '
        'text-anchor="middle" font-size="16" font-weight="bold">'
        'Los cajones abren por el costado largo</text>',
    ))

    if aesthetic == "bicolor_modern_preliminary":
        presentation_lines = (
            "Bicolor preliminar · no acabado aprobado",
            "Cubierta roble claro · lateral/frentes blanco mate",
            "Veta X decorativa; veta productiva sin confirmar",
            "Tirador recto negro · concepto",
            "Sin herraje, SKU, cantidad, posición ni taladros",
        )
    else:
        presentation_lines = (
            "Apariencia por definir · colores no seleccionados",
            "Veta productiva sin confirmar",
            "Apertura sin herraje verificado; SKU y taladros pendientes",
        )
    lines.append(
        '<g data-concept="visual-finish-and-opening-not-production">'
        '<text x="60" y="824" font-size="14" font-weight="bold" '
        'fill="#315d73">Notas visuales; no definen materiales ni herrajes de compra</text>'
    )
    for index, label in enumerate(presentation_lines):
        lines.append(
            f'<text x="60" y="{845 + 18*index}" font-size="13" '
            f'fill="#536b7e">{escape(label)}</text>'
        )
    lines.append('</g>')

    cover = covers[0]
    cx, cy, cz = cover["origin_xyz_mm"]
    cw, ch, cd = cover["size_xyz_mm"]
    lines.append(
        f'<rect data-piece-id="{escape(covers[0]["piece_id"], quote=True)}" '
        f'x="{elev_x+cx*elev_scale:.2f}" '
        f'y="{elev_y+(h-cy-ch)*elev_scale:.2f}" '
        f'width="{cw*elev_scale:.2f}" height="{ch*elev_scale:.2f}" '
        'fill="#dfc99f" stroke="#334b5c" stroke-width="2"/>'
    )
    lines.append(
        f'<rect x="{cab_px0:.2f}" y="{cab_py0:.2f}" '
        f'width="{cab_px1-cab_px0:.2f}" height="{cab_py1-cab_py0:.2f}" '
        'fill="none" stroke="#657b89" stroke-width="2" stroke-dasharray="7 5"/>'
    )
    front_support_z = min(box["origin_xyz_mm"][2] for box in supports)
    for box in supports:
        px, py, pz = box["origin_xyz_mm"]
        pw, ph, _ = box["size_xyz_mm"]
        if pz == front_support_z:
            lines.append(
                f'<rect x="{elev_x+px*elev_scale:.2f}" '
                f'y="{elev_y+(h-py-ph)*elev_scale:.2f}" '
                f'width="{pw*elev_scale:.2f}" height="{ph*elev_scale:.2f}" '
                'fill="#8c7864" stroke="#4f4032" stroke-width="1.5"/>'
            )
    lines.append(
        f'<path d="M{elev_x-18:.2f} {elev_y-3:.2f} V{elev_y1+5:.2f}" '
        'stroke="#475d6b" stroke-width="8"/>'
    )
    for letter, did in (("A", "D1"), ("B", "D2"), ("C", "D3")):
        face = next(box for box in fronts if f"-{did}-" in box["piece_id"])
        px, py, _ = face["origin_xyz_mm"]
        fw, fh, _ = face["size_xyz_mm"]
        front_fill = "#f2f3f0" if aesthetic == "bicolor_modern_preliminary" else "#d8e8ed"
        top = elev_y + (h-py-fh)*elev_scale
        lines.extend((
            f'<rect data-piece-id="{escape(face["piece_id"], quote=True)}" '
            f'x="{elev_x+px*elev_scale:.2f}" y="{top:.2f}" '
            f'width="{fw*elev_scale:.2f}" height="{fh*elev_scale:.2f}" '
            f'fill="{front_fill}" stroke="#52798a" stroke-width="2"/>',
            f'<text x="{elev_x+(px+fw/2)*elev_scale:.2f}" '
            f'y="{top+fh*elev_scale/2+7:.2f}" text-anchor="middle" '
            'font-size="19" font-weight="bold">'
            f'{letter} · {"arriba" if letter == "A" else "en medio" if letter == "B" else "abajo"}'
            '</text>',
        ))
    length_y = elev_y1 + 80
    lines.extend((
        h_dimension("elevation-length", elev_x, elev_x1, length_y,
                    elev_y1, elev_y1, length_label),
        v_dimension("elevation-height", elev_x-65, elev_y, elev_y1,
                    elev_x, elev_x, f'{format_mm_as_cm(h)} cm de alto'),
        f'<text x="{elev_x+human["free_span_mm"]*elev_scale/2:.2f}" '
        f'y="{elev_y+260:.2f}" text-anchor="middle" font-size="20" '
        'font-weight="bold">60 cm libres</text>',
        f'<text x="{cab_px0+12:.2f}" y="{cab_py0-15:.2f}" '
        'font-size="16" font-weight="bold">30 cm cajonera</text>',
        f'<path d="M{cab_px1-10:.2f} {elev_y1-14:.2f} '
        f'L{cab_px1+28:.2f} {elev_y1-34:.2f}" stroke="#705a46" '
        'stroke-width="1.7"/>',
        f'<text x="{cab_px1+32:.2f}" y="{elev_y1-38:.2f}" '
        'font-size="18" font-weight="bold" fill="#614b37">4 cm</text>',
        f'<text x="{cab_px1+32:.2f}" y="{elev_y1-16:.2f}" '
        'font-size="14" fill="#614b37">apoyo conceptual</text>',
        '<text x="816" y="872" font-size="16" fill="#536b7e">'
        'Los 4 cm están debajo del módulo; no se eligió una pata física.</text>',
        '<text x="48" y="1000" font-size="18" font-weight="bold" '
        'fill="#a12e35">La orientación y las cotas son nominales; no describen un montaje validado.</text>',
        f'<text x="48" y="1030" font-size="13" fill="#617688">'
        f'CAD de origen · {len(cad["boxes"])} elementos · SHA-256: '
        f'{escape(cad["geometry_sha256"])}</text>',
        '</g></svg>',
    ))
    svg = "\n".join(lines) + "\n"
    ElementTree.fromstring(svg)
    return svg

def wall_bar_front_contacts_svg(model: dict[str, Any]) -> str:
    """Visualize exact facade-to-box contact patches, never guessed fasteners.

    One panel for each drawer. The display projects the separate decorative
    facade and the box front-wall/side/bottom end faces from canonical CADExchange.
    No holes, screws, supports or physical joinery are implied.
    """
    review = model.get("wall_bar_review", {})
    joints = review.get("front_joint_interfaces")
    if (not isinstance(joints, dict) or set(joints) != {"D1", "D2", "D3"}
            or review.get("drawer_opening_face") != "long_side_front"):
        raise DesignError("No hay evidencia canónica de tres contactos frontales A.")
    cad = validate_exchange(cad_exchange(model))
    pieces = {p["piece_id"]: p for p in cad["boxes"]}
    if len(pieces) != len(cad["boxes"]):
        raise DesignError("IDs repetidos en plano de contactos.")
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1210" height="750" '
        'viewBox="0 0 1210 750" role="img" '
        'aria-label="CarpiNova: contactos geométricos de fachadas separadas D1 D2 D3">',
        '<rect width="1210" height="750" fill="white"/>',
        '<g font-family="Arial,sans-serif" fill="#26354a">',
        '<text x="30" y="44" font-size="26" font-weight="bold">'
        'CARPINOVA · FACHADA SEPARADA Y CAJA · ORIENTACIÓN A</text>',
        '<text x="30" y="79" font-size="17">'
        'Vista posterior de cada fachada. Colores = contactos nominales de piezas CAD reales.</text>',
        '<text x="30" y="108" font-size="16" fill="#a11c32" font-weight="bold">'
        'SIN TORNILLOS / SIN PERFORACIONES / NO ES INSTRUCCIÓN DE ENSAMBLE</text>',
    ]
    palette = {"front_wall": "#9fc9df", "left_side": "#e6a34f",
               "right_side": "#e6a34f", "bottom": "#60a5fa"}
    for i, did in enumerate(("D1", "D2", "D3")):
        x0 = 30 + 390 * i
        panel = joints[did]
        facade = pieces[panel["front_piece_id"]]
        wall_id = panel.get("box_front_wall_piece_id")
        front_wall = pieces.get(wall_id)
        bx, by, bz = facade["origin_xyz_mm"]
        fw, fh, ft = facade["size_xyz_mm"]
        if (facade["role"] != "drawer_facade" or ft != 15
                or front_wall is None or front_wall["role"] != "drawer_front_wall"
                or panel.get("front_construction") != "separate"
                or panel.get("front_style") != "overlay"
                or panel.get("decorative_front_is_structural") is not False
                or panel.get("contact_is_not_a_mechanical_joint") is not True
                or panel.get("fixing_holes_specified") is not False
                or set(panel.get("surfaces", {})) != {
                    "front_wall", "left_side", "right_side", "bottom"
                }):
            raise DesignError("La fachada separada o su contacto no coincide con el CAD.")
        sx = 0.77
        sy = min(0.73, 260.0 / fh)
        left = x0 + (368.0 - fw*sx)/2
        top = 178.0 + (266.0 - fh*sy)/2
        out += [
            f'<rect x="{x0}" y="138" width="370" height="568" rx="10" '
            'fill="#fbfaf7" stroke="#cbd5e1"/>',
            f'<text x="{x0+15}" y="164" font-size="22" font-weight="bold">{did}</text>',
            f'<rect x="{left:.2f}" y="{top:.2f}" width="{fw*sx:.2f}" '
            f'height="{fh*sy:.2f}" fill="#e6d5b5" stroke="#5c4536" stroke-width="2"/>',
        ]
        for role in ("front_wall", "left_side", "right_side", "bottom"):
            surface = panel["surfaces"].get(role)
            if not isinstance(surface, dict):
                raise DesignError("Superficie de contacto no identificada.")
            part = pieces[surface["piece_id"]]
            px, py, pz = part["origin_xyz_mm"]
            dx, dy, dz = part["size_xyz_mm"]
            wx, wy = surface["nominal_contact_patch_xy_mm"]
            if pz != bz + ft:
                raise DesignError("Cara de contacto fuera del plano frontal CAD.")
            expected = (dx, dy)
            if tuple(expected) != (wx, wy):
                raise DesignError("Contacto no coincide con dimensiones CAD.")
            rx = left + (px-bx)*sx
            ry = top + (fh-(py-by)-wy)*sy
            out.append(
                f'<rect x="{rx:.2f}" y="{ry:.2f}" '
                f'width="{wx*sx:.2f}" height="{wy*sy:.2f}" '
                f'fill="{palette[role]}" fill-opacity=".82" '
                'stroke="#37556f" stroke-width="1.4"/>'
            )
        wall_w, wall_h = panel["surfaces"]["front_wall"][
            "nominal_contact_patch_xy_mm"]
        side_h = panel["surfaces"]["left_side"]["nominal_contact_patch_xy_mm"][1]
        bottom_w, bottom_h = panel["surfaces"]["bottom"][
            "nominal_contact_patch_xy_mm"]
        out += [
            f'<text x="{x0+16}" y="481" font-size="16" font-weight="bold">'
            f'Frente: {fw} × {fh} × {ft} mm</text>',
            f'<text x="{x0+16}" y="512" font-size="14">'
            f'Frontal interior: {wall_w} × {wall_h} mm, contacto nominal</text>',
            f'<text x="{x0+16}" y="538" font-size="14">'
            f'LI/LD: 15 × {side_h} mm · base {bottom_w} × {bottom_h} mm</text>',
            f'<text x="{x0+16}" y="576" font-size="12" fill="#9a1e39">'
            'Contacto geométrico, no unión · montaje sin definir</text>',
            f'<text x="{x0+16}" y="610" font-size="12">'
            f'{escape(panel["front_piece_id"])}</text>',
        ]
    out += [
        '<text x="30" y="731" font-size="12">'
        f'Fuente CAD · {escape(cad["geometry_sha256"])} · {len(cad["boxes"])} elementos nominales; no fabricar.</text>',
        '</g></svg>',
    ]
    return "\n".join(out)+"\n"


def wall_bar_isometric_svg(model: dict[str, Any]) -> str:
    """CAD-backed kitchen peninsula preview with explicitly conceptual feet.

    This is a presentation projection of the EXISTING sealed CADExchange
    boxes, not a geometry engine or a manufacturing drawing. The wall and
    mounting choices are explanatory notes; leg blocks are marked concepts.
    """
    rv = model.get("wall_bar_review", {})
    if (rv.get("wall_side") != "left"
            or rv.get("drawer_opening_face") != "long_side_front"
            or rv.get("drawer_open_direction") != "negative_Z"):
        raise DesignError("Vista de barra: orientación A obligatoria.")
    cad = validate_exchange(cad_exchange(model))
    w, height, depth = cad["bounds_xyz_mm"]
    boxes = cad["boxes"]
    human = wall_bar_review_dimensions(model)
    support_boxes = [b for b in boxes if b["role"] == "support_leg_concept"]
    if (len(boxes) != 28 or len({b["piece_id"] for b in boxes}) != 28
            or len(support_boxes) != 4
            or (w, height, depth) != (900, 900, 460)
            or len([b for b in boxes if b["piece_id"] == "BAR-COVER-TOP"]) != 1
            or len([b for b in boxes if b["role"] == "drawer_facade"]) != 3):
        raise DesignError("Vista vinculada solo a la barra aplicada con cuatro apoyos conceptuales.")

    x0, y0 = 110, 765
    def project(x: float, y: float, z: float) -> tuple[float, float]:
        return (x0 + x*.76 + z*.47, y0 + x*.12 - y*.58 - z*.29)

    def points(corners: list[tuple[float, float, float]]) -> str:
        return " ".join(f"{project(*p)[0]:.2f},{project(*p)[1]:.2f}" for p in corners)

    names = {"installer_defined": "A definir por instalador",
             "wood_cleat": "Listón bajo cubierta (no modelado)",
             "metal_l_brackets": "Escuadras L (no modeladas)",
             "metal_support": "Soporte metálico (no modelado)",
             "other_pending": "Otro soporte: pendiente"}
    edges = {"actual_15mm": "Canto real de 15 mm",
             "false_thickness_pending": "Falso espesor: pendiente de medidas",
             "undecided": "Aspecto de canto: por definir"}
    choices = rv.get("design_choices", {})
    aesthetic = choices.get("aesthetic_presentation", "undecided")
    if (type(aesthetic) is not str
            or aesthetic not in AESTHETIC_PRESENTATION_CHOICES):
        raise DesignError("Opción estética no soportada por la vista.")
    # Review only the CAD-backed exterior IDs. This includes the right side,
    # which was previously omitted from the visible-surface summary.
    source_parts = {p["piece_id"]: p for p in model["parts"]}
    if set(source_parts) != {b["piece_id"] for b in boxes}:
        raise DesignError("Piezas del modelo y CAD no concuerdan.")
    visible_source = [p for p in model["parts"] if
                      p["piece_id"] == "BAR-COVER-TOP"
                      or p["role"] in ("right_side", "drawer_facade")]
    visible_ids = {p["piece_id"] for p in visible_source}
    cad_visible_ids = {b["piece_id"] for b in boxes if
                       b["piece_id"] == "BAR-COVER-TOP"
                       or b["role"] in ("right_side", "drawer_facade")}
    if len(visible_source) != 5 or visible_ids != cad_visible_ids:
        raise DesignError("Superficies visibles no corresponden a 5 IDs CAD.")
    drawers = [p for p in visible_source if p["role"] == "drawer_facade"]
    opening_intents = {p.get("opening_system", "pending") for p in drawers}
    opening_label = ("Tirador indicado; SKU pendiente"
                     if opening_intents == {"handle"}
                     else "Apertura sin herraje verificado")
    if aesthetic == "bicolor_modern_preliminary":
        finish_label = "Bicolor preliminar · no acabado aprobado"
        color_label = "Cubierta roble claro · lateral/frentes blanco mate"
        grain_label = "Veta X decorativa; veta productiva sin confirmar"
    else:
        finish_label = "Apariencia por definir · colores no seleccionados"
        grain_label = "Veta productiva sin confirmar"
    surface_label = "5 superficies · 7 caras + 4 apoyos CAD"
    support = choices.get("wall_support_presentation", "installer_defined")
    edge = choices.get("top_edge_presentation", "actual_15mm")
    if support not in names or edge not in edges:
        raise DesignError("Opciones de diseño no soportadas por la vista.")
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1460" height="960" '
        'viewBox="0 0 1460 960" role="img" '
        'aria-label="Barra cocina CarpiNova: isométrica del CAD validado">',
        '<rect width="1460" height="960" fill="#fafbfc"/>',
        '<defs><clipPath id="scene-clip"><rect x="0" y="113" '
        'width="1038" height="740"/></clipPath></defs>',
        '<rect width="1460" height="113" fill="#172b40"/>',
        '<g font-family="Arial,sans-serif">',
        '<text x="55" y="44" fill="white" font-size="28" font-weight="bold">'
        'CARPINOVA · BARRA AUXILIAR DE COCINA</text>',
        '<text x="55" y="78" fill="#cddee9" font-size="16">'
        'VISTA ISOMÉTRICA CAD · ORIENTACIÓN A · SOLO REVISIÓN</text>',
        '<rect x="1038" y="140" width="381" height="700" rx="18" '
        'fill="white" stroke="#e1e8f0"/>',
        '<text x="1070" y="182" font-size="23" font-weight="bold" '
        'fill="#273e56">Geometría de revisión</text>',
        '<text x="1070" y="215" font-size="17" fill="#53697e">'
        f'{w} × {depth} × {height} mm</text>',
        '<text x="1070" y="239" font-size="13" fill="#53697e">'
        f'Largo X: {w} mm · Fondo Z: {depth} mm</text>',
        '<text x="1070" y="258" font-size="13" fill="#53697e">'
        f'Altura total Y: {height} mm</text>',
        '<text x="1070" y="282" font-size="16" font-weight="bold" '
        'fill="#1a6479">El extremo CORTO va al muro</text>',
        '<text x="1070" y="310" font-size="14" fill="#53697e">'
        'Largo total medido desde el muro</text>',
        '<text x="1070" y="340" font-size="18" font-weight="bold" '
        'fill="#243c53">Cajones en el costado largo</text>',
    ]
    for i, label in enumerate(("D1 · pequeño superior",
                               "D2 · pequeño intermedio",
                               "D3 · grande inferior")):
        y = 369 + i*37
        lines.extend([
            f'<rect x="1070" y="{y-11}" width="14" height="14" '
            'fill="#bcdce8" stroke="#4d7990"/>',
            f'<text x="1092" y="{y}" font-size="16" fill="#53697e">'
            f'{escape(label)}</text>',
        ])
    free = human["free_span_mm"]
    lines += [
        '<path d="M1070 480H1384M1070 625H1384" '
        'stroke="#d5dee8" stroke-width="1.5"/>',
        '<text x="1070" y="514" font-size="18" font-weight="bold" '
        f'fill="#243c53">{free} mm libres bajo cubierta</text>',
        '<text x="1070" y="545" font-size="15" fill="#53697e">'
        f'Cajonera: {human["cabinet_width_mm"]} mm</text>',
        '<text x="1070" y="576" font-size="15" fill="#53697e">'
        f'Patas conceptuales: {human["support_height_mm"]} mm, solo cajonera</text>',
        '<text x="1070" y="599" font-size="12" fill="#53697e">'
        f'{human["support_count"]} bloques CAD {human["support_footprint_width_mm"]} × '
        f'{human["support_height_mm"]} × {human["support_footprint_depth_mm"]} mm; huella ilustrativa</text>',
        '<text x="1070" y="618" font-size="12" fill="#53697e">'
        'Material, SKU y fijación pendientes · sin selección física</text>',
        '<text x="1070" y="650" font-size="17" font-weight="bold" '
        'fill="#243c53">Presentación y acabados</text>',
        '<text x="1070" y="671" font-size="13" fill="#53697e">'
        f'{escape(names[support])}</text>',
        '<text x="1070" y="691" font-size="13" fill="#53697e">'
        f'{escape(edges[edge])}</text>',
        '<text x="1070" y="711" font-size="13" fill="#53697e">'
        f'{escape(finish_label)}</text>',
    ]
    if aesthetic == "bicolor_modern_preliminary":
        lines.extend([
            '<text x="1070" y="729" font-size="12" fill="#53697e">'
            f'{escape(color_label)}</text>',
            '<text x="1070" y="748" font-size="12" fill="#53697e">'
            f'{escape(grain_label)}</text>',
            '<text x="1070" y="767" font-size="12" fill="#53697e">'
            f'{escape(surface_label)}</text>',
            '<g data-concept="handle-legend">',
            '<path d="M1072 783H1108" stroke="#161616" stroke-width="4" '
            'stroke-linecap="round"/>',
            '<text x="1118" y="788" font-size="13" fill="#273e56">'
            'Tirador recto negro · concepto</text>',
            '<text x="1070" y="806" font-size="11" fill="#53697e">'
            'Sin herraje, SKU, cantidad, posición ni taladros</text>',
            '</g>',
        ])
        foot_y, anchor_y = 819, 837
    else:
        lines.extend([
            '<text x="1070" y="729" font-size="13" fill="#53697e">'
            f'{escape(grain_label)}</text>',
            '<text x="1070" y="750" font-size="13" fill="#53697e">'
            f'{escape(surface_label)}</text>',
        ])
        lines.append(
            '<text x="1070" y="771" font-size="13" fill="#53697e">'
            f'{escape(opening_label)}</text>')
        foot_y, anchor_y = 808, 830
    lines += [
        f'<text x="1070" y="{anchor_y}" font-size="13" font-weight="bold" '
        'fill="#9a3d32">Anclajes: responsabilidad instalador</text>',
    ]
    # A dashed existing-wall REFERENCE, not a left-hand wooden panel.
    wall = [(0,0,0),(0,945,0),(0,945,460),(0,0,460)]
    lines.append(f'<polygon points="{points(wall)}" fill="none" '
                 'stroke="#9fb2c3" stroke-width="3" stroke-dasharray="8 7" '
                 'clip-path="url(#scene-clip)"/>')


    # Exterior visibility, not a depth-sort of every internal box.
    # Drawing all box faces exposes interior drawer parts THROUGH carcass.
    # External faces come from CADExchange boxes; no geometry is invented.
    external_faces = []
    oak_top, oak_front, oak_side = "#e8d2a8", "#d8bd8e", "#c5a472"
    white_matte = "#f2f3f0"
    for b in boxes:
        x,y,z = b["origin_xyz_mm"]
        dx,dy,dz = b["size_xyz_mm"]
        xx,yy,zz = x+dx,y+dy,z+dz
        is_cover = b["piece_id"] == "BAR-COVER-TOP"
        is_front = b["role"] == "drawer_facade"
        is_right = b["role"] == "right_side"
        if is_cover:
            if aesthetic == "bicolor_modern_preliminary":
                cover_top, cover_front, cover_side = oak_top, oak_front, oak_side
            else:
                cover_top, cover_front, cover_side = "#f7ecd8", "#d8c3a5", "#b49e80"
            surfaces = (
                ("top", [(x,yy,z),(xx,yy,z),(xx,yy,zz),(x,yy,zz)], cover_top),
                ("front", [(x,y,z),(xx,y,z),(xx,yy,z),(x,yy,z)], cover_front),
                ("right", [(xx,y,z),(xx,yy,z),(xx,yy,zz),(xx,y,zz)], cover_side),
            )
            layer = 2
        elif is_front:
            fill = white_matte if aesthetic == "bicolor_modern_preliminary" else "#bcdce8"
            surfaces = (("front", [(x,y,z),(xx,y,z),(xx,yy,z),(x,yy,z)], fill),)
            layer = 1
        elif is_right:
            fill = white_matte if aesthetic == "bicolor_modern_preliminary" else "#d8c3a5"
            surfaces = (("right", [(xx,y,z),(xx,yy,z),(xx,yy,zz),(xx,y,zz)], fill),)
            layer = 0
        elif b["role"] == "support_leg_concept":
            surfaces = (
                ("top", [(x,yy,z),(xx,yy,z),(xx,yy,zz),(x,yy,zz)], "#a89a88"),
                ("front", [(x,y,z),(xx,y,z),(xx,yy,z),(x,yy,z)], "#8c7864"),
                ("right", [(xx,y,z),(xx,yy,z),(xx,yy,zz),(xx,y,zz)], "#725f4e"),
            )
            layer = -1
        else:
            continue  # Internal panels remain in CAD, not the exterior view.
        for face_name, face_poly, color in surfaces:
            external_faces.append(
                (layer, b["piece_id"], face_name, points(face_poly), color,
                 b["role"] == "support_leg_concept"))
    expected_external_ids = visible_ids | {b["piece_id"] for b in support_boxes}
    if (len(external_faces) != 19
            or {face[1] for face in external_faces} != expected_external_ids):
        raise DesignError("Exterior no corresponde a cubierta, lateral, frentes y apoyos CAD.")
    for _,pid,name,poly,color,is_concept in sorted(external_faces):
        concept_attr = 'data-concept="support" ' if is_concept else ""
        lines.append(
            f'<polygon data-piece-id="{escape(pid)}" data-face="{name}" '
            f'{concept_attr}'
            f'points="{poly}" fill="{color}" stroke="#4f6576" '
            'stroke-width="1.05" stroke-linejoin="round"/>')
    if aesthetic == "bicolor_modern_preliminary":
        cover = next(b for b in boxes if b["piece_id"] == "BAR-COVER-TOP")
        x, y, z = cover["origin_xyz_mm"]
        dx, dy, dz = cover["size_xyz_mm"]
        for ratio in (0.14, 0.32, 0.50, 0.68, 0.86):
            start = project(x + dx * 0.035, y + dy, z + dz * ratio)
            end = project(x + dx * 0.965, y + dy, z + dz * ratio)
            lines.append(
                f'<path data-concept="decorative-grain" data-axis="X" '
                f'd="M{start[0]:.2f} {start[1]:.2f} '
                f'L{end[0]:.2f} {end[1]:.2f}" fill="none" '
                'stroke="#9a7448" stroke-width="1.8" opacity="0.62"/>')
    for did in ("D1","D2","D3"):
        front=next(b for b in boxes if b["piece_id"].endswith(f"{did}-DRAWER_FACADE"))
        x,y,z=front["origin_xyz_mm"]
        dx,dy,dz=front["size_xyz_mm"]
        px,py=project(x+dx/2,y+dy/2,0)
        lines.append(f'<text x="{px:.2f}" y="{py+5:.2f}" '
                     'text-anchor="middle" font-size="20" font-weight="bold" '
                     f'fill="#245877">{did}</text>')
    label_x,label_y=project(0,680,150)
    lines += [
        f'<path d="M{label_x:.2f} {label_y:.2f}L98 330" '
        'stroke="#58738a" stroke-width="2" fill="none"/>',
        '<text x="52" y="314" fill="#36556f" font-size="18" '
        'font-weight="bold">MURO</text>',
        '<text x="52" y="340" fill="#53697e" font-size="13">'
        'Solo contexto, NO tablero</text>',
        f'<text x="{project(315,430,80)[0]:.2f}" '
        f'y="{project(315,430,80)[1]:.2f}" font-size="20" '
        'font-weight="bold" fill="#36556f">'
        f'{free} mm libres</text>',
        '<rect x="40" y="855" width="1380" height="74" rx="8" '
        'fill="#fff6e8" stroke="#e8d2a9"/>',
        f'<text x="62" y="882" fill="#9c4b21" font-size="16" '
        f'font-weight="bold">BORRADOR · {len(boxes)} ELEMENTOS CAD · NO CORTAR NI FABRICAR</text>',
        '<text x="62" y="907" fill="#6e655d" font-size="13">'
        + (('Bicolor preliminar elegido; SKU y veta productiva pendientes. '
          if aesthetic == "bicolor_modern_preliminary"
          else 'Colores/veta ilustrativos; aún sin selección estética. ')
         + 'Sin herrajes, anclajes ni perforaciones físicas.</text>'),
        f'<text x="48" y="947" fill="#758494" font-size="11">'
        f'CAD SHA-256: {escape(cad["geometry_sha256"])}</text>',
        '</g></svg>',
    ]
    return "\n".join(lines) + "\n"
