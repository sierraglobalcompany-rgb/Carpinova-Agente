"""Annotated orthographic cabinet/drawer geometry SVG — conceptual, NOT cut plans.

Uses the same calculated output from F1; no numerical assumptions or
manufacturer-specific drilling is embedded in the visual.
"""
from __future__ import annotations

from html import escape
from typing import Any

from .core import DesignError

SVG_W = 900
SVG_H = 660
AREA_WIDTH = 650
AREA_HEIGHT = 410


def render_svg(result: dict[str, Any]) -> str:
    if not isinstance(result, dict) or result.get("status") != "DRAFT_NOT_FOR_CUTTING":
        raise DesignError("Se requiere diseño preliminar de F1 válido.")
    kind = result.get("design_type")
    dims = result.get("dimensions", {})
    if kind == "open_cabinet":
        width = dims.get("external_width_mm")
        height = dims.get("external_height_mm")
        parts = result.get("parts", [])
        if len(parts) != 2:
            raise DesignError("Piezas de gabinete insuficientes.")
        side = parts[0]
        cap = parts[1]
        t = side["thickness_mm"]
        if side["face_y_mm"] == height and cap["face_x_mm"] == width - 2*t:
            structure = "sides_full"
        elif cap["face_x_mm"] == width and side["face_y_mm"] == height - 2*t:
            structure = "top_bottom_full"
        else:
            raise DesignError("Partes no corresponden a una estructura admitida.")
        label = ("Gabinete abierto: costados completos" if structure == "sides_full"
                 else "Gabinete abierto: tapa/base completas")
    elif kind == "drawer_box_surface_bottom":
        width = dims.get("box_external_width_mm")
        height = dims.get("box_external_height_mm")
        t = result["parts"][0]["thickness_mm"]
        bottom_t = result["parts"][2]["thickness_mm"]
        label = "Cajón: caja con fondo inferior aplicado"
    else:
        raise DesignError("Solo se dibuja gabinete abierto o caja de cajón.")
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise DesignError("Dimensiones no positivas.")
    if type(t) is not int or t <= 0 or width <= 2*t or height <= 2*t:
        raise DesignError("Espesores/dimensiones incompatibles con el croquis.")
    if kind == "drawer_box_surface_bottom" and (type(bottom_t) is not int or
                                                   bottom_t <= 0 or height <= bottom_t):
        raise DesignError("Fondo incompatible con altura de caja.")
    scale = min(AREA_WIDTH / width, AREA_HEIGHT / height)
    sw, sh = width*scale, height*scale
    x0, y0 = (SVG_W - sw)/2, 120 + (AREA_HEIGHT-sh)/2
    sx, sy = t*scale, t*scale
    # True scaled proportions; no minimum stroke widths are imposed on panels.
    pieces: list[tuple[float, float, float, float, str]] = []
    if kind == "open_cabinet":
        if structure == "sides_full":
            pieces = [(0, 0, sx, sh, "L"), (sw-sx, 0, sx, sh, "R"),
                      (sx, 0, sw-2*sx, sy, "T"), (sx, sh-sy, sw-2*sx, sy, "B")]
        else:
            pieces = [(0, 0, sw, sy, "T"), (0, sh-sy, sw, sy, "B"),
                      (0, sy, sx, sh-2*sy, "L"),
                      (sw-sx, sy, sx, sh-2*sy, "R")]
    else:
        # Front view: front wall between two sides and applied bottom.
        base = bottom_t * scale
        pieces = [(0, 0, sx, sh-base, "L"),
                  (sw-sx, 0, sx, sh-base, "R"),
                  (sx, 0, sw-2*sx, sh-base, "F"),
                  (0, sh-base, sw, base, "B")]
    rects = [
        f'<rect x="{x0+px:.3f}" y="{y0+py:.3f}" width="{pw:.3f}" '
        f'height="{ph:.3f}" class="piece"/>' for px,py,pw,ph,_ in pieces
        if pw > 0 and ph > 0
    ]
    left = x0 - 38
    top = y0 - 27
    # All positions are proportional to the supplied dimensions; labels show exact mm.
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" '
        f'height="{SVG_H}" viewBox="0 0 {SVG_W} {SVG_H}" '
        'role="img" aria-label="Croquis frontal preliminar con cotas en milímetros">'
        '<style>'
        'text{font-family:Arial,sans-serif;fill:#1e293b;font-size:17px}'
        '.piece{fill:#e2e8f0;stroke:#334155;stroke-width:1.2}'
        '.dimension{stroke:#0f766e;stroke-width:1.1;fill:none}'
        '.warn{fill:#b91c1c;font-weight:bold;font-size:23px}'
        '.secondary{fill:#475569;font-size:14px}'
        '</style>'
        f'<text x="40" y="39" font-weight="bold" font-size="23">{escape(label)}</text>'
        '<text x="40" y="72" class="warn">BORRADOR — NO FABRICAR / NO PERFORAR</text>'
        '<text x="40" y="93" class="secondary">Vista frontal ortográfica, cotas nominales en mm. Sin herrajes ni cantos.</text>'
        + "".join(rects) +
        f'<path class="dimension" d="M {x0:.3f} {top-9:.3f} v 19 '
        f'M {x0+sw:.3f} {top-9:.3f} v 19 '
        f'M {x0:.3f} {top:.3f} H {x0+sw:.3f}"/>'
        f'<text x="{x0+sw/2:.3f}" y="{top-5:.3f}" text-anchor="middle">{width} mm</text>'
        f'<path class="dimension" d="M {left-9:.3f} {y0:.3f} h 19 '
        f'M {left-9:.3f} {y0+sh:.3f} h 19 '
        f'M {left:.3f} {y0:.3f} V {y0+sh:.3f}"/>'
        f'<text x="{left-12:.3f}" y="{y0+sh/2:.3f}" text-anchor="middle" '
        f'transform="rotate(-90 {left-12:.3f} {y0+sh/2:.3f})">{height} mm</text>'
        '<text x="40" y="592" class="secondary">Frente esquemático: no representa uniones, fondo oculto, tornillos ni taladros.</text>'
        '<text x="40" y="616" class="secondary">No compensa tolerancias del sitio, ranuras, tapacantos ni deformaciones.</text>'
        '</svg>\n'
    )
