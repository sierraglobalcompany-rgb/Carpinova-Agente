"""Front elevation and human-review BOM from F6 geometry, never cutting plans."""
from __future__ import annotations

import csv
from html import escape
from io import StringIO
from typing import Any

from .core import DesignError
from .drawer_modules import OPENING_SYSTEMS


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


def _drawer_review_labels(piece: dict[str, Any]) -> tuple[str, str]:
    """Carry existing decorative choices into review files, not CAD tooling.

    Both values are sourced from F7C. Do not infer hardware specifications,
    drilled-hole coordinates or ready-to-manufacture status.
    """
    if piece["role"] != "drawer_facade":
        return "", ""
    styles = {
        "F7C_EXPLICIT_INSET_FACADE": "inset",
        "F7C_EXPLICIT_OVERLAY_FACADE": "overlay",
    }
    style = styles.get(piece.get("source_engine"))
    intent = piece.get("opening_system")
    if style is None or type(intent) is not str or intent not in OPENING_SYSTEMS:
        raise DesignError("Frente de cajón sin estilo o apertura válida para revisión.")
    return style, intent


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
        "dimension_formula", "production_status", "hinge_side_requested", "drawer_id",
        "drawer_facade_style", "opening_system_intent",
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
            "BORRADOR_NO_CORTAR", piece.get("hinge_side_requested", ""), piece.get("drawer_id",""),
            *_drawer_review_labels(piece),
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
    # Rear panels first, carcass next, doors last. No second geometry engine.
    ordered = sorted(draft["parts"], key=lambda p: (
        0 if p["role"].startswith("back_") else
        2 if p["role"].startswith("front_") or p["role"]=="drawer_facade" else 1
    ))
    for piece in ordered:
        role = piece["role"]
        if role in ("left_side", "right_side", "drawer_side_left", "drawer_side_right"):
            pw, ph = piece["thickness_mm"], piece["nominal_face_y_mm"]
        elif role in ("top", "bottom", "drawer_bottom"):
            pw, ph = piece["nominal_face_x_mm"], piece["thickness_mm"]
        elif role in ("back_full", "back_top", "back_bottom",
                      "front_single", "front_left", "front_right",
                      "drawer_front_wall", "drawer_rear_wall", "drawer_facade"):
            pw, ph = piece["nominal_face_x_mm"], piece["nominal_face_y_mm"]
        elif role == "support_leg_concept":
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
        if role == "drawer_facade":
            style, intent = _drawer_review_labels(piece)
            # Explicit text metadata only; not a depiction of real hardware.
            name += (f" | {escape(style, quote=True)} | "
                     f"{escape(intent, quote=True)} | SIN MECANIZADO")
        panel_class = ("support" if role == "support_leg_concept" else
                       "front" if role.startswith("front_") or role=="drawer_facade" else
                       "panel")
        if role == "support_leg_concept":
            name += " | APOYO CONCEPTUAL | SIN SKU"
        shapes.append(
            f'<rect data-role="{escape(role, quote=True)}" '
            f'x="{sx:.4f}" y="{sy:.4f}" width="{pw*scale:.4f}" '
            f'height="{ph*scale:.4f}" class="{panel_class}"><title>{name}</title></rect>'
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
        '.front{fill:#e8cfad;stroke:#475569;stroke-width:1.4}'
        '.support{fill:#8c7864;stroke:#4f4032;stroke-width:1.2}'
        'text{font-family:Arial,sans-serif;fill:#1e293b;font-size:18px}'
        '.bad{font-size:25px;fill:#b91c1c;font-weight:bold}'
        '.note{font-size:15px;fill:#475569}.module{font-size:14px}'
        '.dim{stroke:#0f766e;stroke-width:1.1;fill:none}'
        '</style>'
        '<path d="M0 0H1000V790H0Z" fill="#ffffff" aria-hidden="true"/>'
        f'<text x="45" y="37" font-size="25" font-weight="bold">CarpiNova — boceto modular · {name}</text>'
        '<text x="45" y="74" class="bad">BORRADOR: NO CORTAR NI FABRICAR</text>'
        '<text x="45" y="99" class="note">Elevación frontal geométrica; '
        'frentes sólo si están especificados; sin bisagras, correderas ni mecanizados.</text>'
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
        + ('<text x="45" y="700" class="note">'
           'Patas: geometría CAD conceptual bajo cajonera; sin material ni SKU.</text>'
           if any(p["role"] == "support_leg_concept" for p in draft["parts"])
           else "")
        + '</svg>\n'
    )
