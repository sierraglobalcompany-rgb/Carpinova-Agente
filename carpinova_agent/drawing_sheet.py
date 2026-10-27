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
        booklet_name = "CN-BAR-001-planos-REVISION.pdf"
    else:
        booklet_svgs = generic_booklet_svgs(model, cad)
        booklet_name = "CARPINOVA-planos-REVISION.pdf"
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
                              f"CARPINOVA | HOJA {index:02d}/{len(booklet_svgs):02d} | NO FABRICAR",
                              fill="#9e2733")
                    pages.append(page)
            with BytesIO() as stream:
                pages[0].save(stream, format="PDF", resolution=150.0,
                              save_all=True, append_images=pages[1:])
                booklet = stream.getvalue()
            if not booklet.startswith(b"%PDF-"):
                raise DesignError("No se generó la cartilla PDF.")
            (stage / booklet_name).write_bytes(booklet)
        render_manifest = {
            "status": "DRAFT_NOT_FOR_CUTTING",
            "source": "CANONICAL_CAD_EXCHANGE",
            "geometry_sha256": cad["geometry_sha256"],
            "piece_count": len(cad["boxes"]),
            "files": list(_SHEET_FILES) + (
                [booklet_name] if booklet is not None else []),
            "svg_sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
            "png_sha256": hashlib.sha256(png).hexdigest(),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            **({"booklet_pdf_sha256": hashlib.sha256(booklet).hexdigest(),
                "booklet_pages": len(booklet_svgs)} if booklet is not None else {}),
            **{key: False for key in _RELEASE_FLAGS},
        }
        (stage / "render-manifest.json").write_text(
            json.dumps(render_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if destination.exists() or destination.is_symlink():
            raise DesignError("Lámina creada por otra operación; no sobrescribir.")
        os.rename(stage, destination)
    return render_manifest


def generic_booklet_svgs(model: dict[str, Any], cad: dict[str, Any]) -> list[str]:
    """Review sheets for F6/F7C modules using existing canonical part data.

    One general CAD view, a separate sheet for each real drawer, a referenced
    nominal BOM, and a preliminary assembly review. No second geometry engine.
    """
    from xml.etree import ElementTree

    cad = validate_exchange(cad)
    source = {p["piece_id"]: p for p in model["parts"]}
    boxes = {b["piece_id"]: b for b in cad["boxes"]}
    if (len(source) != len(model["parts"]) or len(boxes) != len(cad["boxes"])
            or set(source) != set(boxes)):
        raise DesignError("Referencias del mueble distintas del CAD.")

    def ref_letter(number: int) -> str:
        result = ""
        while number:
            number, index = divmod(number - 1, 26)
            result = chr(65 + index) + result
        return result

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    frame: list[dict[str, Any]] = []
    for part in model["parts"]:
        did = part.get("drawer_id")
        if part["role"].startswith("drawer_"):
            if not isinstance(did, str) or not did:
                raise DesignError("Cajón CAD sin identificador de origen.")
            groups.setdefault((part["module_id"], did), []).append(part)
        else:
            frame.append(part)
    for key, parts in groups.items():
        fronts = [p for p in parts if p["role"] == "drawer_facade"]
        if len(fronts) != 1 or len(parts) not in (5, 6):
            raise DesignError("Cajón incompleto o sin frente: " + str(key))
    ordered_groups = sorted(
        groups,
        key=lambda key: (
            -max(boxes[p["piece_id"]]["origin_xyz_mm"][1] +
                 boxes[p["piece_id"]]["size_xyz_mm"][1]
                 for p in groups[key] if p["role"] == "drawer_facade"),
            key[0], key[1],
        ),
    )
    order = ("drawer_facade", "drawer_front_wall", "drawer_side_left",
             "drawer_side_right", "drawer_rear_wall", "drawer_bottom")
    references: list[tuple[str, dict[str, Any]]] = []
    for number, part in enumerate(sorted(frame, key=lambda p: (
            p["module_id"], p["role"], p["piece_id"])), start=1):
        references.append((f"E{number:02d}", part))
    sheet_groups = []
    for idx, key in enumerate(ordered_groups, start=1):
        letter = ref_letter(idx)
        parts = sorted(groups[key], key=lambda p: (
            order.index(p["role"]), p["piece_id"]))
        entries = [(f"{letter}{j:02d}", p) for j, p in enumerate(parts, 1)]
        references.extend(entries)
        sheet_groups.append((letter, key, entries))
    if len(references) != len(boxes):
        raise DesignError("Despiece de revisión no cubre las piezas CAD.")

    digest = cad["geometry_sha256"]

    def sheet(title: str, body: list[str]) -> str:
        result = "\n".join([
            '<svg xmlns="http://www.w3.org/2000/svg" width="1600" '
            'height="1130" viewBox="0 0 1600 1130">',
            '<rect width="1600" height="1130" fill="#fff"/>',
            '<rect width="1600" height="126" fill="#183247"/>',
            '<g font-family="Arial,sans-serif">',
            f'<text x="50" y="60" fill="white" font-size="34" '
            f'font-weight="bold">{escape(title)}</text>',
            '<text x="50" y="100" fill="#dbe8f0" font-size="18">'
            'CARPINOVA · BORRADOR NOMINAL · NO FABRICAR</text>',
            *body,
            f'<text x="50" y="1095" fill="#52677a" font-size="15">'
            f'Piezas reales {len(boxes)} · CAD SHA-256: {escape(digest)}</text>',
            '</g></svg>',
        ]) + "\n"
        ElementTree.fromstring(result)
        return result

    # Reuse the existing general three-view renderer; overlay only client
    # references for real drawer facades at their CAD-backed XY positions.
    overview = three_views_svg(cad)
    w, h, _ = cad["bounds_xyz_mm"]
    scale = min((536 - 76) / w, (460 - 76 - 30) / h)
    left = 36 + (536 - w * scale) / 2
    top = 128 + 37 + (460 - 76 - 30 - h * scale) / 2
    markers = []
    for letter, key, entries in sheet_groups:
        front = next(p for _, p in entries if p["role"] == "drawer_facade")
        b = boxes[front["piece_id"]]
        x, y, _ = b["origin_xyz_mm"]
        dx, dy, _ = b["size_xyz_mm"]
        xx = left + (x + dx / 2) * scale
        yy = top + (h - y - dy / 2) * scale
        markers.append(
            f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="13" '
            'fill="#fff" stroke="#175579" stroke-width="2"/>'
            f'<text x="{xx:.2f}" y="{yy+5:.2f}" text-anchor="middle" '
            f'font-family="Arial" font-size="16" fill="#175579">'
            f'{escape(letter)}</text>'
        )
    if not overview.endswith("</svg>\n"):
        raise DesignError("Vista general de CAD sin cierre esperado.")
    overview = overview.replace("</svg>\n", "".join(markers) + "</svg>\n")

    pages = [overview]
    for letter, (module_id, drawer_id), entries in sheet_groups:
        body = [
            f'<text x="54" y="178" font-size="24" font-weight="bold" '
            f'fill="#183247">Módulo {escape(module_id)} · ID CAD {escape(drawer_id)}</text>',
            '<text x="54" y="214" font-size="18" fill="#9e2733">'
            'Las uniones, rieles y medidas de corte terminadas NO están aprobadas.</text>',
            '<rect x="50" y="250" width="850" height="680" rx="8" '
            'fill="#f6f9fb" stroke="#cad8e2"/>',
            '<text x="64" y="283" font-size="21" fill="#183247">'
            'PLANTA · piezas reales (X/Z)</text>',
            '<text x="963" y="280" font-size="23" font-weight="bold" '
            'fill="#183247">DESPIECE DEL CAJÓN</text>',
        ]
        coords = [boxes[p["piece_id"]] for _, p in entries]
        xmin = min(b["origin_xyz_mm"][0] for b in coords)
        zmin = min(b["origin_xyz_mm"][2] for b in coords)
        xmax = max(b["origin_xyz_mm"][0] + b["size_xyz_mm"][0] for b in coords)
        zmax = max(b["origin_xyz_mm"][2] + b["size_xyz_mm"][2] for b in coords)
        scale = min(720 / (xmax - xmin), 555 / (zmax - zmin))
        for code, part in sorted(entries, key=lambda pair: (
                pair[1]["role"] == "drawer_facade", pair[0])):
            b = boxes[part["piece_id"]]
            px, _, pz = b["origin_xyz_mm"]
            dx, _, dz = b["size_xyz_mm"]
            xx = 100 + (px - xmin) * scale
            yy = 335 + (pz - zmin) * scale
            body.append(
                f'<rect x="{xx:.2f}" y="{yy:.2f}" '
                f'width="{dx*scale:.2f}" height="{dz*scale:.2f}" '
                'fill="#d8e9f3" fill-opacity=".6" '
                'stroke="#36536a" stroke-width="1.7" '
                f'data-piece-id="{escape(part["piece_id"], quote=True)}">'
                f'<title>{escape(code)}</title></rect>'
            )
        # Visible client references: all CAD pieces, never only SVG <title>.
        # Callouts link each reference to its original X/Z rectangle.
        positions = {
            "drawer_facade": (160, 302),
            "drawer_front_wall": (720, 302),
            "drawer_side_left": (74, 510),
            "drawer_side_right": (818, 510),
            "drawer_rear_wall": (155, 900),
            "drawer_bottom": (500, 695),
        }
        for code, part in entries:
            b = boxes[part["piece_id"]]
            px, _, pz = b["origin_xyz_mm"]
            dx, _, dz = b["size_xyz_mm"]
            tx = 100 + (px + dx / 2 - xmin) * scale
            ty = 335 + (pz + dz / 2 - zmin) * scale
            cx, cy = positions[part["role"]]
            body.extend((
                f'<path data-leader-id="{escape(part["piece_id"], quote=True)}" '
                f'd="M{cx:.2f} {cy:.2f} L{tx:.2f} {ty:.2f}" fill="none" '
                'stroke="#5d7889" stroke-width="1.2" stroke-dasharray="5 4"/>',
                f'<rect x="{cx-23}" y="{cy-15}" width="48" height="28" '
                'rx="6" fill="#fff" stroke="#215370" stroke-width="1.5"/>',
                f'<text data-visible-part-id="{escape(part["piece_id"], quote=True)}" '
                f'x="{cx+1}" y="{cy+5}" text-anchor="middle" '
                f'font-size="18" font-weight="bold" fill="#17435f">{code}</text>',
            ))
        for j, (code, part) in enumerate(entries):
            by = 335 + j * 100
            fx = part["nominal_face_x_mm"]
            fy = part["nominal_face_y_mm"]
            thick = part["thickness_mm"]
            body.extend((
                f'<text x="965" y="{by}" font-size="21" font-weight="bold" '
                f'fill="#17435f">{escape(code)}</text>',
                f'<text x="1040" y="{by}" font-size="18" fill="#183247">'
                f'{escape(part["role"])}</text>',
                f'<text x="1040" y="{by+30}" font-size="17" fill="#53697e">'
                f'{fx} × {fy} × {thick} mm</text>',
                f'<text x="1040" y="{by+53}" font-size="12" fill="#53697e">'
                f'{escape(part["piece_id"])}</text>',
            ))
        pages.append(sheet(f"CAJÓN {letter} · {len(entries)} PIEZAS", body))
    per_page = 18
    for start in range(0, len(references), per_page):
        subset = references[start:start + per_page]
        body = [
            '<text x="50" y="182" font-size="21" fill="#183247">'
            'REF. / ROL / MEDIDA NOMINAL / ID CAD</text>',
            '<text x="50" y="218" font-size="17" fill="#9e2733">'
            'Sin descuentos de canto, mecanizados o patrón de perforaciones.</text>',
        ]
        for i, (code, part) in enumerate(subset):
            col = i // 9
            row = i % 9
            x = 50 + col * 770
            y = 255 + row * 88
            size = (f'{part["nominal_face_x_mm"]} × '
                    f'{part["nominal_face_y_mm"]} × {part["thickness_mm"]} mm')
            body.extend((
                f'<rect x="{x}" y="{y-23}" width="742" height="76" '
                'fill="#f4f8fb" stroke="#cbd8e2"/>',
                f'<text x="{x+12}" y="{y+3}" font-size="18" '
                f'font-weight="bold" fill="#17435f">{escape(code)} · '
                f'{escape(part["role"])}</text>',
                f'<text x="{x+720}" y="{y+3}" font-size="16" '
                f'text-anchor="end" fill="#17435f">{size}</text>',
                f'<text x="{x+12}" y="{y+28}" font-size="14" '
                f'fill="#53697e">{escape(part["piece_id"])}</text>',
            ))
        pages.append(sheet("DESPIECE GENERAL · REFERENCIAS", body))
    steps = [
        "Identificar cada pieza con su código de la tabla y su ID CAD.",
        "Revisar el encaje nominal de la carcasa antes de definir uniones.",
    ]
    if sheet_groups:
        steps.extend([
            "Revisar cada cajón en su hoja individual y sus luces laterales.",
            "Elegir correderas por longitud, holgura y carga documentada.",
        ])
    else:
        steps.extend([
            "Revisar los frentes y puertas únicamente si existen en el CAD.",
            "Definir las uniones según el material y el sistema constructivo.",
        ])
    steps.extend([
        "Validar cantos terminados, fijaciones, cargas y estabilidad.",
        "El instalador verifica apoyos y anclajes cuando correspondan.",
    ])
    manual = [
        '<text x="50" y="187" font-size="23" font-weight="bold" '
        'fill="#183247">SECUENCIA PRELIMINAR DE REVISIÓN</text>',
    ]
    for i, step in enumerate(steps):
        y = 254 + i * 116
        manual.extend((
            f'<rect x="50" y="{y-27}" width="1470" height="85" '
            'rx="8" fill="#f4f8fb" stroke="#cbd8e2"/>',
            f'<text x="70" y="{y+12}" font-size="29" font-weight="bold" '
            f'fill="#17435f">{i+1:02d}</text>',
            f'<text x="155" y="{y+12}" font-size="22" fill="#183247">'
            f'{escape(step)}</text>',
        ))
    manual.append(
        '<text x="52" y="1015" font-size="20" fill="#9e2733">'
        'NO es un manual de taller liberado: faltan ensambles, perforaciones '
        'y resistencia documentada.</text>'
    )
    pages.append(sheet("GUÍA DE ARMADO · SOLO REVISIÓN", manual))
    if len(pages) > 32:
        raise DesignError("Paquete demasiado grande: dividir en módulos.")
    for page in pages:
        ElementTree.fromstring(page)
        if digest not in page:
            raise DesignError("Página sin trazabilidad geométrica.")
    return pages
