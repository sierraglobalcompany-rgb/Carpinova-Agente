"""Per-part traceable review sheet derived from canonical CADExchange boxes.

Never re-solves furniture dimensions. No manufacturing cut instructions.
"""
from __future__ import annotations

import csv
from html import escape
from io import StringIO
from typing import Any

from .cad_exchange import cad_exchange, validate_exchange
from .core import DesignError


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
            "edge_policy": ("RIGIDO_FRENTES_2MM_CANDIDATO" if front
                            else "FLEXIBLE_RESTANTES_0_45MM_CANDIDATO"),
            "edge_positions": ("CUATRO_BORDES_NOMINALES" if front
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
        fragments.extend([
            f'<rect x="20" y="{y}" width="1100" height="94" rx="8" class="panel"/>',
            f'<rect x="45" y="{y+12}" width="{wd:.2f}" height="{ht:.2f}" '
            f'class="{"front" if front else "wood"}"/>',
            f'<text x="390" y="{y+27}" class="name">{escape(row["piece_id"])}</text>',
            f'<text x="390" y="{y+51}" class="info">'
            f'{w} × {h} × {row["thickness_mm"]} mm · {escape(row["role"])}</text>',
            f'<text x="390" y="{y+76}" class="info">'
            f'Canto: {escape(row["edge_policy"])} · corte final NO VALIDADO</text>',
        ])
    fragments.append("</svg>")
    return "\n".join(fragments) + "\n"


def wall_bar_orientation_svg(model: dict[str, Any]) -> str:
    """Orthographic plan/elevation of actual CAD boxes, with wall as context ONLY.

    Opening A: facade at long-side front Z=0; motion toward negative Z.
    The contextual wall, arrows and cabinet outline are NOT wooden boards.
    """
    rv = model.get("wall_bar_review")
    if (not isinstance(rv, dict) or rv.get("drawer_opening_face") != "long_side_front"
            or rv.get("drawer_open_direction") != "negative_Z"
            or rv.get("wall_side") != "left"):
        raise DesignError("Lámina A requiere orientación confirmada.")
    cad = validate_exchange(cad_exchange(model))
    w, h, d = cad["bounds_xyz_mm"]
    fronts = [p for p in cad["boxes"] if p["role"] == "drawer_facade"]
    covers = [p for p in cad["boxes"] if p["piece_id"] == "BAR-COVER-TOP"]
    free = rv["free_span_mm"]
    if (len(fronts) != 3 or len(covers) != 1
            or any(p["origin_xyz_mm"][2] != 0 for p in fronts)):
        raise DesignError("Geometría CAD no corresponde a tres frentes laterales.")
    sx, sy, sp = 170.0, 225.0, min(0.66, 645 / w, 300 / d)
    fx, fy, sf = 170.0, 670.0, min(0.55, 520 / h, 620 / w)
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1150" height="1320" '
        'viewBox="0 0 1150 1320" role="img" '
        'aria-label="CarpiNova planta y frente del modelo CAD con orientación A">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" '
        'refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#b45309"/></marker></defs>',
        '<rect width="1150" height="1320" fill="#ffffff"/>',
        '<g font-family="Arial,sans-serif" fill="#223345">',
        '<text x="35" y="43" font-size="25" font-weight="bold">'
        'CARPINOVA · BARRA AUXILIAR DE COCINA</text>',
        '<text x="35" y="79" font-size="19" font-weight="bold">'
        'ORIENTACION A CONFIRMADA · Tres cajones hacia el COSTADO LARGO</text>',
        '<text x="35" y="109" font-size="15" fill="#ad3434">'
        'SOLO REVISION · NO CORTAR, PERFORAR NI FABRICAR</text>',
        '<text x="35" y="165" font-size="21" font-weight="bold">'
        '1. PLANTA (vista desde arriba) · Muro en el borde CORTO de 460 mm</text>',
        f'<rect x="{sx:.2f}" y="{sy:.2f}" width="{w*sp:.2f}" '
        f'height="{d*sp:.2f}" fill="#ecdcc1" stroke="#334155" stroke-width="2"/>',
        f'<path d="M{sx-10:.2f} {sy-20:.2f}V{sy+d*sp+20:.2f}" '
        'stroke="#475569" stroke-width="9"/>',
        f'<rect x="{sx+free*sp:.2f}" y="{sy:.2f}" '
        f'width="{(w-free)*sp:.2f}" height="{d*sp:.2f}" '
        'fill="#c0d3db" fill-opacity=".52" stroke="#64748b" stroke-dasharray="7 4"/>',
        f'<text x="{sx+85:.2f}" y="{sy+92:.2f}" font-size="18">'
        f'600 mm libres BAJO cubierta</text>',
        f'<text x="{sx+free*sp+8:.2f}" y="{sy+98:.2f}" font-size="17">'
        f'Cajonera 300 mm</text>',
        f'<text x="{sx+80:.2f}" y="{sy+d*sp+33:.2f}" font-size="17">'
        f'900 mm desde el muro · 460 mm de fondo</text>',
        f'<text x="27" y="{sy+60:.2f}" font-size="18" font-weight="bold">MURO</text>',
    ]
    for box in fronts:
        x, y, z = box["origin_xyz_mm"]
        dx, dy, dz = box["size_xyz_mm"]
        lines.append(
            f'<path d="M{sx+x*sp:.2f} {sy:.2f}H{sx+(x+dx)*sp:.2f}" '
            'stroke="#2563eb" stroke-width="7"/>'
        )
    arrow_x = sx+(free+(w-free)/2)*sp
    lines += [
        f'<path d="M{arrow_x:.2f} {sy-4:.2f}V{sy-31:.2f}" '
        'stroke="#b45309" stroke-width="3" marker-end="url(#arrow)"/>',
        f'<text x="{sx+w*sp+25:.2f}" y="{sy+35:.2f}" font-size="16">'
        'ABRE HACIA -Z</text>',
        '<text x="35" y="630" font-size="21" font-weight="bold">'
        '2. ELEVACION del COSTADO LARGO (mirando hacia +Z)</text>',
    ]
    cover=covers[0]
    a,b,c=cover["origin_xyz_mm"]
    dx,dy,dz=cover["size_xyz_mm"]
    lines.append(
        f'<rect x="{fx+a*sf:.2f}" y="{fy+(h-b-dy)*sf:.2f}" '
        f'width="{dx*sf:.2f}" height="{dy*sf:.2f}" '
        'fill="#ecdcc1" stroke="#334155" stroke-width="2"/>'
    )
    lines.append(
        f'<text x="{fx+10:.2f}" y="{fy-20:.2f}" font-size="14">'
        f'BAR-COVER-TOP · {w} x {d} mm</text>'
    )
    cab0, cab1 = rv["cabinet_x_range_mm"]
    cy0, cy1 = rv["cabinet_y_range_mm"]
    lines.append(
        f'<rect x="{fx+cab0*sf:.2f}" y="{fy+(h-cy1)*sf:.2f}" '
        f'width="{(cab1-cab0)*sf:.2f}" height="{(cy1-cy0)*sf:.2f}" '
        'fill="none" stroke="#64748b" stroke-dasharray="6 4" stroke-width="2"/>'
    )
    lines.append(
        f'<path d="M{fx-10:.2f} {fy-14:.2f}V{fy+h*sf+15:.2f}" '
        'stroke="#475569" stroke-width="9"/>'
    )
    for box in fronts:
        x,y,z=box["origin_xyz_mm"]
        dx,dy,dz=box["size_xyz_mm"]
        label=box["piece_id"].split("-")[1]
        ydraw=fy+(h-y-dy)*sf
        lines += [
            f'<rect x="{fx+x*sf:.2f}" y="{ydraw:.2f}" '
            f'width="{dx*sf:.2f}" height="{dy*sf:.2f}" '
            'fill="#bfdbfe" stroke="#2563eb" stroke-width="2"/>',
            f'<text x="{fx+(x+dx/2)*sf:.2f}" y="{ydraw+dy*sf/2:.2f}" '
            f'text-anchor="middle" font-size="19" font-weight="bold">{escape(label)}</text>'
        ]
    lines += [
        f'<text x="{fx+20:.2f}" y="{fy+205:.2f}" font-size="18">'
        'SIN LATERAL</text>',
        f'<text x="{fx+20:.2f}" y="{fy+233:.2f}" font-size="18">'
        'JUNTO AL MURO</text>',
        f'<text x="{fx+20:.2f}" y="{fy+h*sf+42:.2f}" font-size="18">'
        f'Altura {h} mm · patas {rv["feet_height_mm"]} mm NO MODELADAS</text>',
        '<text x="755" y="717" font-size="18" font-weight="bold">'
        'Referencias CAD por cajón:</text>'
    ]
    for i,front in enumerate(sorted(fronts, key=lambda b: -b["origin_xyz_mm"][1])):
        lines.append(
            f'<text x="755" y="{752+i*40}" font-size="13">'
            f'{escape(front["piece_id"])}</text>'
        )
    lines += [
        '<text x="35" y="1247" font-size="16" fill="#aa2222">'
        'Muro y piso: contexto, NO piezas. Apoyo, uniones, cantos, herrajes y cargas PENDIENTES.</text>',
        f'<text x="35" y="1286" font-size="13">CAD SHA-256: '
        f'{escape(cad["geometry_sha256"])}</text>',
        '</g></svg>'
    ]
    return "\n".join(lines)+"\n"


def wall_bar_front_contacts_svg(model: dict[str, Any]) -> str:
    """Visualize EXACT rear-face contact patches, never guessed fasteners.

    One panel for each drawer.  The display is an orthographic projection of
    canonical CADExchange boxes at the inner facade plane (Z=15 nominal).
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
        'aria-label="CarpiNova: cara posterior de frentes únicos D1 D2 D3">',
        '<rect width="1210" height="750" fill="white"/>',
        '<g font-family="Arial,sans-serif" fill="#26354a">',
        '<text x="30" y="44" font-size="26" font-weight="bold">'
        'CARPINOVA · UNIÓN DE FRENTE ÚNICO · ORIENTACIÓN A</text>',
        '<text x="30" y="79" font-size="17">'
        'Vista POSTERIOR de cada frente. Cajas coloradas = contacto de pieza REAL en CAD.</text>',
        '<text x="30" y="108" font-size="16" fill="#a11c32" font-weight="bold">'
        'SIN TORNILLOS / SIN PERFORACIONES / NO ES INSTRUCCIÓN DE ENSAMBLE</text>',
    ]
    palette = {"left_side": "#e6a34f",
               "right_side": "#e6a34f", "bottom": "#60a5fa"}
    for i, did in enumerate(("D1", "D2", "D3")):
        x0 = 30 + 390 * i
        panel = joints[did]
        facade = pieces[panel["front_piece_id"]]
        bx, by, bz = facade["origin_xyz_mm"]
        fw, fh, ft = facade["size_xyz_mm"]
        if (facade["role"] != "drawer_facade" or ft != 15
                or panel.get("contact_is_not_a_mechanical_joint") is not True
                or panel.get("fixing_holes_specified") is not False):
            raise DesignError("El frontal se presenta como unión no validada.")
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
        for role in ("left_side", "right_side", "bottom"):
            surface = panel["surfaces"].get(role)
            if not isinstance(surface, dict):
                raise DesignError("Superficie de contacto no identificada.")
            part = pieces[surface["piece_id"]]
            px, py, pz = part["origin_xyz_mm"]
            dx, dy, dz = part["size_xyz_mm"]
            wx, wy = surface["nominal_contact_patch_xy_mm"]
            if pz != bz + ft:
                raise DesignError("Cara de contacto fuera del plano frontal CAD.")
            if role in ("left_side", "right_side"):
                expected = (dx, dy)
            else:
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
        height = "105" if did in ("D1", "D2") else "375"
        out += [
            f'<text x="{x0+16}" y="481" font-size="16" font-weight="bold">'
            f'Frente: {fw} × {fh} × {ft} mm</text>',
            f'<text x="{x0+16}" y="512" font-size="14">'
            f'LI / LD: 15 × {height} mm, contacto nominal</text>',
            f'<text x="{x0+16}" y="538" font-size="14">'
            'BASE: 244 × 15 mm, contacto nominal</text>',
            f'<text x="{x0+16}" y="576" font-size="12" fill="#9a1e39">'
            'Sujeción sin definir · resistencia no verificada</text>',
            f'<text x="{x0+16}" y="610" font-size="12">'
            f'{escape(panel["front_piece_id"])}</text>',
        ]
    out += [
        '<text x="30" y="731" font-size="12">'
        f'Fuente CAD · {escape(cad["geometry_sha256"])} · 21 paneles nominales; no fabricar.</text>',
        '</g></svg>',
    ]
    return "\n".join(out)+"\n"
