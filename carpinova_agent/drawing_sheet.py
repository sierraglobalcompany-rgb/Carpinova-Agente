"""Nominal 3-view drawing and optional PNG/PDF from a verified CADExchange.

Orthographic silhouettes of the original CAD boxes, never new geometry.
These are translucent SUPERIMPOSED projections, not hidden-line CAD drawings
or manufacturing instructions. PNG uses resvg_py and raster PDF uses Pillow, with no system Cairo dependency.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from html import escape
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .cad_exchange import validate_exchange
from .core import DesignError
from .pilot_cli import PilotError, verify_pilot_bundle


_SHEET_FILES = ("three-views.svg", "three-views.png", "three-views.pdf", "render-manifest.json")
_RELEASE_FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")


def _projection(exchange: dict[str, Any], *,
                axes: tuple[int, int], panel: tuple[int, int, int, int],
                title: str, dimensions: str, invert_v: bool) -> str:
    """Project validated XYZ boxes onto two axes; never alter their dimensions."""
    left, top, width, height = panel
    bound_h, bound_v = (exchange["bounds_xyz_mm"][axis] for axis in axes)
    padding = 38
    usable_w, usable_h = width - 2 * padding, height - 2 * padding - 30
    scale = min(usable_w / bound_h, usable_h / bound_v)
    start_x = left + (width - bound_h * scale) / 2
    start_y = top + 37 + (usable_h - bound_v * scale) / 2
    shapes: list[str] = []
    for box in exchange["boxes"]:
        loc, dim = box["origin_xyz_mm"], box["size_xyz_mm"]
        px = start_x + loc[axes[0]] * scale
        py = start_y + ((bound_v - loc[axes[1]] - dim[axes[1]]) if invert_v
                        else loc[axes[1]]) * scale
        pw, ph = dim[axes[0]] * scale, dim[axes[1]] * scale
        name = escape(str(box["piece_id"]), quote=True)
        shapes.append(
            f'<rect x="{px:.3f}" y="{py:.3f}" width="{pw:.3f}" '
            f'height="{ph:.3f}" class="part"><title>{name}</title></rect>'
        )
    return (
        f'<rect x="{left}" y="{top}" width="{width}" height="{height}" rx="10" class="panel"/>'
        f'<text x="{left + 17}" y="{top + 27}" class="section">{escape(title)}</text>'
        + "".join(shapes) +
        f'<rect x="{start_x:.3f}" y="{start_y:.3f}" '
        f'width="{bound_h * scale:.3f}" height="{bound_v * scale:.3f}" class="bounds"/>'
        f'<text x="{left + width / 2}" y="{top + height - 12}" text-anchor="middle" '
        f'class="dimension">{escape(dimensions)}</text>'
    )


def three_views_svg(data: dict[str, Any]) -> str:
    """A dimensioned three-view visualization from canonical CAD boxes only."""
    cad = validate_exchange(data)
    w, h, d = cad["bounds_xyz_mm"]
    digest = cad["geometry_sha256"]
    parts = len(cad["boxes"])
    drawing = [
        _projection(cad, axes=(0, 1), panel=(36, 128, 536, 460),
                    title="01  FRENTE / X-Y", dimensions=f"Ancho {w} mm · Alto {h} mm",
                    invert_v=True),
        _projection(cad, axes=(2, 1), panel=(588, 128, 536, 460),
                    title="02  LATERAL / Z-Y", dimensions=f"Fondo {d} mm · Alto {h} mm",
                    invert_v=True),
        _projection(cad, axes=(0, 2), panel=(36, 605, 536, 410),
                    title="03  PLANTA / X-Z", dimensions=f"Ancho {w} mm · Fondo {d} mm",
                    invert_v=False),
    ]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1160" height="1040" '
        'viewBox="0 0 1160 1040" role="img" '
        'aria-label="Lámina de tres vistas nominales de un mueble, no fabricable">'
        '<style>'
        'svg{background:#fff}text{font-family:Arial,sans-serif;fill:#152537}'
        '.panel{fill:#f8fafc;stroke:#cbd5e1;stroke-width:1.5}'
        '.part{fill:#b5d5ed;fill-opacity:.30;stroke:#23506f;stroke-width:1}'
        '.bounds{fill:none;stroke:#23465f;stroke-width:1.5;stroke-dasharray:5 3}'
        '.section{font-weight:bold;font-size:18px}.dimension{font-size:17px}'
        '.heading{font-size:26px;font-weight:bold}.warning{font-size:19px;fill:#b91c1c;font-weight:bold}'
        '.note{font-size:16px;fill:#334155}.hash{font-size:13px;fill:#475569}'
        '</style>'
        '<rect x="0" y="0" width="1160" height="1040" fill="#fff"/>'
        '<text x="36" y="42" class="heading">CARPINOVA  ·  Lámina de geometría nominal</text>'
        '<text x="36" y="76" class="warning">BORRADOR — NO CORTAR, PERFORAR NI FABRICAR</text>'
        f'<text x="36" y="104" class="note">{parts} piezas del CADExchange original, unidades mm; vistas superpuestas.</text>'
        + "".join(drawing) +
        '<text x="598" y="660" class="section">LECTURA DE LA LÁMINA</text>'
        '<text x="598" y="700" class="note">Cada rectángulo representa una pieza CAD.</text>'
        '<text x="598" y="730" class="note">El dibujo superpone paneles transparentes:</text>'
        '<text x="598" y="760" class="note">no resuelve líneas ocultas ni ensamblajes.</text>'
        '<text x="598" y="805" class="note">Falta comprobar cantos, veta, uniones,</text>'
        '<text x="598" y="835" class="note">herrajes, apoyo, cargas, tuberías y obra.</text>'
        '<text x="598" y="880" class="note">Las cotas son exteriores nominales;</text>'
        '<text x="598" y="910" class="note">no corresponden a medidas finales de corte.</text>'
        f'<text x="598" y="982" class="hash">CAD SHA-256: {escape(digest)}</text>'
        '</svg>\n'
    )


def create_render_bundle(project_folder: Path) -> dict[str, Any]:
    """Atomically publish SVG/PNG/PDF in a NEW lamina/ directory.

    Reject symlinks and altered CAD before any optional raster conversion.
    Exposes no arbitrary shell commands or extra project geometry.
    """
    folder = Path(project_folder)
    destination = folder / "lamina"
    if destination.exists() or destination.is_symlink():
        raise DesignError("Lámina existente: no sobrescribir.")
    # One provenance gate for 2D AND native CAD. No duplicate geometry tests.
    try:
        cad = verify_pilot_bundle(folder)
    except (PilotError, DesignError) as exc:
        raise DesignError("Paquete de revisión inconsistente con Maestro.") from exc
    svg = three_views_svg(cad)
    # Only the named wall-bar model has the 7-page supplementary booklet.
    # Read the already-verified Maestro snapshot, never recompute geometry.
    answer = json.loads((folder / "maestro-review.json").read_text(encoding="utf-8"))
    model = answer["modular"]
    booklet_svgs = []
    if model.get("wall_bar_review"):
        from .wall_bar_delivery import review_booklet_svgs
        booklet_svgs = review_booklet_svgs(model)
    try:
        import resvg_py
        from PIL import Image
    except ImportError as exc:
        raise DesignError(
            "Para PNG/PDF instalar resvg_py==0.5.0 y Pillow==13.0.0."
        ) from exc
    # All products are staged before a same-filesystem directory rename.
    with TemporaryDirectory(prefix=".carpinova-sheet-", dir=folder) as tmp:
        stage = Path(tmp) / "lamina"
        stage.mkdir()
        (stage / "three-views.svg").write_text(svg, encoding="utf-8")
        try:
            png = resvg_py.svg_to_bytes(svg_string=svg, width=2320)
            with Image.open(BytesIO(png)) as image:
                # PDF de revisión rasterizado a 200 DPI; la fuente vectorial
                # fiel sigue siendo three-views.svg, sin segunda geometría.
                with BytesIO() as stream:
                    image.convert("RGB").save(stream, format="PDF", resolution=200.0)
                    pdf = stream.getvalue()
        except (OSError, ValueError) as exc:
            raise DesignError("No se pudo renderizar la lámina: " + str(exc)) from exc
        if not png.startswith(b"\x89PNG\r\n\x1a\n") or not pdf.startswith(b"%PDF-"):
            raise DesignError("Conversión de imagen inválida.")
        (stage / "three-views.png").write_bytes(png)
        (stage / "three-views.pdf").write_bytes(pdf)
        booklet = None
        if booklet_svgs:
            from PIL import ImageDraw
            # Reuse the SAME optional resvg_py + Pillow stack as three-views.
            # Rasterized A3-landscape review pages; source SVGs are CAD-derived.
            pages = []
            for index, page_svg in enumerate(booklet_svgs, start=1):
                data = resvg_py.svg_to_bytes(svg_string=page_svg, width=2300)
                if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise DesignError("Una página de la cartilla no es PNG.")
                with Image.open(BytesIO(data)) as src:
                    img = src.convert("RGB")
                    img.thumbnail((2350, 1560), Image.Resampling.LANCZOS)
                    page = Image.new("RGB", (2500, 1768), "white")
                    page.paste(img, ((2500 - img.width) // 2, 60 +
                                     (1560 - img.height) // 2))
                    draw = ImageDraw.Draw(page)
                    draw.text((100, 1690),
                              f"CN-BAR-001 | HOJA {index:02d}/07 | NO FABRICAR",
                              fill="#9e2733")
                    pages.append(page)
            with BytesIO() as stream:
                pages[0].save(stream, format="PDF", resolution=150.0,
                              save_all=True, append_images=pages[1:])
                booklet = stream.getvalue()
            if not booklet.startswith(b"%PDF-"):
                raise DesignError("No se generó la cartilla PDF.")
            (stage / "CN-BAR-001-planos-REVISION.pdf").write_bytes(booklet)
        render_manifest = {
            "status": "DRAFT_NOT_FOR_CUTTING",
            "source": "CANONICAL_CAD_EXCHANGE",
            "geometry_sha256": cad["geometry_sha256"],
            "piece_count": len(cad["boxes"]),
            "files": list(_SHEET_FILES) + (
                ["CN-BAR-001-planos-REVISION.pdf"] if booklet is not None else []),
            "svg_sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
            "png_sha256": hashlib.sha256(png).hexdigest(),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            **({"booklet_pdf_sha256": hashlib.sha256(booklet).hexdigest(),
                "booklet_pages": 7} if booklet is not None else {}),
            **{key: False for key in _RELEASE_FLAGS},
        }
        (stage / "render-manifest.json").write_text(
            json.dumps(render_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if destination.exists() or destination.is_symlink():
            raise DesignError("Lámina creada por otra operación; no sobrescribir.")
        os.rename(stage, destination)
    return render_manifest
