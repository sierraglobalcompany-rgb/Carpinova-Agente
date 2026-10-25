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
