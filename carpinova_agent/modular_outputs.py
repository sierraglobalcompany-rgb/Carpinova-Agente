"""Front elevation and human-review BOM from F6 geometry, never cutting plans."""
from __future__ import annotations

import csv
from html import escape
from io import StringIO
from typing import Any

from .core import DesignError


def _review_draft(model: Any) -> dict[str, Any]:
    if (not isinstance(model, dict) or model.get("type") != "modular_run"
            or model.get("status") != "DRAFT_NOT_FOR_CUTTING"
            or model.get("fabrication_ready") is not False
            or model.get("cutting_ready") is not False):
        raise DesignError("Salida F6 sin aprobar o con geometría faltante.")
    dims = model.get("dimensions_mm")
    pieces = model.get("parts")
    if (not isinstance(dims, dict) or not isinstance(pieces, list)
            or not pieces or not isinstance(model.get("modules"), list)):
        raise DesignError("Borrador modular incompleto.")
    if any(type(dims.get(key)) is not int or dims[key] <= 0
           for key in ("width", "height", "depth")):
        raise DesignError("Medidas nominales inválidas.")
    return model


def modular_bom_csv(model: dict[str, Any]) -> str:
    """CSV of *nominal* geometric faces for review, not machine-cut dimensions."""
    draft = _review_draft(model)
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow([
        "piece_id", "module_id", "role", "material_id",
        "nominal_face_x_mm", "nominal_face_y_mm", "thickness_mm",
        "face_plane", "grain_axis", "edgebanding_edges",
        "edgebanding_thickness_mm", "edgebanding_nominal_total_mm",
        "origin_x_mm", "origin_y_mm", "origin_z_mm",
        "dimension_formula", "production_status",
    ])
    for piece in draft["parts"]:
        writer.writerow([
            piece["piece_id"], piece["module_id"], piece["role"],
            piece["material_id"], piece["nominal_face_x_mm"],
            piece["nominal_face_y_mm"], piece["thickness_mm"],
            piece["face_plane"], piece["grain_axis"],
            ("UNCONFIRMED" if piece["edgebanding_edges"] == "UNCONFIRMED"
             else "|".join(piece["edgebanding_edges"])),
            (piece["edgebanding_thickness_mm"] if
             piece["edgebanding_thickness_mm"] is not None else "UNCONFIRMED"),
            (piece["edgebanding_nominal_total_mm"] if
             piece["edgebanding_nominal_total_mm"] is not None else "UNCONFIRMED"),
            *piece["nominal_origin_xyz_mm"], piece["source_formula"],
            "BORRADOR_NO_CORTAR",
        ])
    return buffer.getvalue()


def modular_front_svg(model: dict[str, Any]) -> str:
    """Scaled elevation. All panel coordinates are from F6, not recalculated."""
    draft = _review_draft(model)
    w, h = draft["dimensions_mm"]["width"], draft["dimensions_mm"]["height"]
    viewport_w, viewport_h = 1000, 790
    max_w, max_h = 850, 475
    scale = min(max_w / w, max_h / h)
    scaled_w, scaled_h = w*scale, h*scale
    x0 = (viewport_w-scaled_w)/2
    y0 = 160+(max_h-scaled_h)/2

    shapes = []
    # Rear panels appear behind front carcass outlines in this elevation.
    ordered = sorted(draft["parts"], key=lambda p: 0 if p["role"].startswith("back_") else 1)
    for piece in ordered:
        role = piece["role"]
        if role in ("left_side", "right_side"):
            pw, ph = piece["thickness_mm"], piece["nominal_face_y_mm"]
        elif role in ("top", "bottom"):
            pw, ph = piece["nominal_face_x_mm"], piece["thickness_mm"]
        elif role in ("back_full", "back_top", "back_bottom"):
            pw, ph = piece["nominal_face_x_mm"], piece["nominal_face_y_mm"]
        else:
            raise DesignError("Rol de panel desconocido.")
        origin = piece["nominal_origin_xyz_mm"]
        px, py = origin[0], origin[1]
        if (type(px) is not int or type(py) is not int or
                px < 0 or py < 0 or pw <= 0 or ph <= 0 or
                px+pw > w or py+ph > h):
            raise DesignError("Proyección del panel excede la estructura nominal.")
        sx = x0+px*scale
        sy = y0+(h-(py+ph))*scale
        name = escape(str(piece["piece_id"]), quote=True)
        shapes.append(
            f'<rect x="{sx:.4f}" y="{sy:.4f}" width="{pw*scale:.4f}" '
            f'height="{ph*scale:.4f}" class="panel"><title>{name}</title></rect>'
        )
    titles = []
    for module in draft["modules"]:
        center = x0+(module["start_x_mm"]+module["external_width_mm"]/2)*scale
        identifier = escape(str(module["module_id"]))
        titles.append(
            f'<text x="{center:.3f}" y="{y0+scaled_h+21:.3f}" class="module" '
            f'text-anchor="middle">{identifier} · {module["external_width_mm"]} mm</text>'
        )
    name = escape(str(draft["application"]))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{viewport_w}" '
        f'height="{viewport_h}" viewBox="0 0 {viewport_w} {viewport_h}" '
        'role="img" aria-label="Elevación frontal preliminar de módulos abiertos">'
        '<style>svg{background-color:#ffffff}'
        '.panel{fill:#e2e8f0;stroke:#334155;stroke-width:1.15}'
        'text{font-family:Arial,sans-serif;fill:#1e293b;font-size:18px}'
        '.bad{font-size:25px;fill:#b91c1c;font-weight:bold}'
        '.note{font-size:15px;fill:#475569}.module{font-size:14px}'
        '.dim{stroke:#0f766e;stroke-width:1.1;fill:none}'
        '</style>'
        f'<text x="45" y="37" font-size="25" font-weight="bold">CarpiNova — boceto modular · {name}</text>'
        '<text x="45" y="74" class="bad">BORRADOR: NO CORTAR NI FABRICAR</text>'
        '<text x="45" y="99" class="note">Elevación frontal geométrica, paneles '
        'independientes; sin puertas, cajones ni herrajes.</text>'
        + "".join(shapes) + "".join(titles) +
        f'<path class="dim" d="M {x0:.3f} {y0-17:.3f} v 14 '
        f'M {x0+scaled_w:.3f} {y0-17:.3f} v 14 '
        f'M {x0:.3f} {y0-10:.3f} H {x0+scaled_w:.3f}"/>'
        f'<text x="{x0+scaled_w/2:.3f}" y="{y0-22:.3f}" '
        f'text-anchor="middle">{w} mm</text>'
        f'<path class="dim" d="M {x0-28:.3f} {y0:.3f} H {x0-16:.3f} '
        f'M {x0-28:.3f} {y0+scaled_h:.3f} H {x0-16:.3f} '
        f'M {x0-23:.3f} {y0:.3f} V {y0+scaled_h:.3f}"/>'
        f'<text x="{x0-34:.3f}" y="{y0+scaled_h/2:.3f}" text-anchor="middle" '
        f'transform="rotate(-90 {x0-34:.3f} {y0+scaled_h/2:.3f})">{h} mm</text>'
        '<text x="45" y="730" class="note">Veta y canto están en el CSV de revisión. '
        'Las dimensiones no compensan espesor de tapacanto.</text>'
        '<text x="45" y="755" class="note">No muestra uniones de fondos, '
        'fijaciones ni verificación estructural. Comprobar en sitio.</text>'
        '</svg>\n'
    )
