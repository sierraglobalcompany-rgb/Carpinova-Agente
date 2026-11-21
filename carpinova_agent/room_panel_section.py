"""Read-only horizontal panel section from D5's verified room world_boxes.

No furniture geometry, machinery, or native CAD is created here. The input
must be the result of room_spatial.review_room_from_specs(), which regenerates
F6/CADExchange from local specifications instead of trusting client CAD.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


_FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready",
          "purchase_ready", "can_generate_f7c")
_CSS = """.room{fill:none;stroke:#0f172a;stroke-width:2}
.panel{stroke:#334155;stroke-width:1.5;fill:#8bbdd4;fill-opacity:.75}
.front{fill:#dcaa75;fill-opacity:.90}.back{fill:#94b49b}
.other{fill:#ccc0da;fill-opacity:.78}
.service{stroke:#9a5a28;stroke-width:2;stroke-dasharray:8 5;fill:none}
.name{font-family:Arial,sans-serif;font-size:17px;fill:#1e293b}
.meta{font-family:Arial,sans-serif;font-size:14px;fill:#334155}
.alert{font-family:Arial,sans-serif;font-size:19px;font-weight:bold;fill:#a11c1c}"""


def _rect3(value: Any, field: str) -> list[int]:
    if (type(value) is not list or len(value) != 3
            or any(type(n) is not int or n < 0 or n > 20000 for n in value)):
        raise ValueError(f"{field}: tres enteros mm no negativos")
    return value


def _box(obj: Any, field: str) -> tuple[list[int], list[int]]:
    if type(obj) is not dict:
        raise ValueError(f"{field}: caja inválida")
    origin = _rect3(obj.get("origin_xyz_mm"), field + ".origin")
    size = _rect3(obj.get("size_xyz_mm", obj.get("bounds_xyz_mm")), field + ".size")
    if any(n <= 0 for n in size) or any(origin[i] + size[i] > 20000 for i in range(3)):
        raise ValueError(f"{field}: volumen fuera de límites")
    return origin, size


def _sub(parent: ET.Element, tag: str, attrs: dict[str, str], text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, tag, attrs)
    if text is not None:
        element.text = text
    return element


def render_room_panel_section_svg(review: dict[str, Any], *, y_mm: int) -> str:
    """Project *existing* 3D panels intersecting height y_mm onto world X/Z.

    This projection is an aid to visual review, not validation of exchanged
    geometry. Public entry points must first call review_room_from_specs().
    """
    if (type(review) is not dict or review.get("review_kind") != "room_layout_v1"
            or review.get("status") not in ("REVIEW_ONLY", "INTERFERENCE_REVIEW_REQUIRED")
            or any(review.get(flag) is not False for flag in _FLAGS)):
        raise ValueError("Se requiere una revisión espacial nominal bloqueada")
    if type(y_mm) is not int or not 0 <= y_mm <= 20000:
        raise ValueError("La altura de corte exige milímetros enteros válidos")
    groups, panels = review.get("groups"), review.get("world_boxes")
    if (type(groups) is not list or not 1 <= len(groups) <= 6
            or type(panels) is not list or not 1 <= len(panels) <= 432):
        raise ValueError("Revisión espacial sin grupos o cajas de paneles")
    if type(review.get("service_zones")) is not list:
        raise ValueError("Zonas de servicio inválidas")

    valid_groups: set[str] = set()
    envelopes: list[tuple[str, list[int], list[int]]] = []
    for index, item in enumerate(groups):
        origin, size = _box(item, f"groups[{index}]")
        gid = item.get("group_id")
        if type(gid) is not str or not gid or gid in valid_groups:
            raise ValueError("Grupo duplicado o sin identificador")
        valid_groups.add(gid)
        envelopes.append((gid, origin, size))
    measured: list[tuple[dict[str, Any], list[int], list[int]]] = []
    names: set[str] = set()
    for index, item in enumerate(panels):
        origin, size = _box(item, f"world_boxes[{index}]")
        pid, gid, role = (item.get(key) for key in ("piece_id", "group_id", "role"))
        if (type(pid) is not str or not pid or pid in names
                or type(gid) is not str or gid not in valid_groups
                or type(role) is not str or not role):
            raise ValueError("Pieza duplicada o con identificación inválida")
        names.add(pid)
        measured.append((item, origin, size))

    max_x = max(origin[0] + size[0] for _, origin, size in envelopes)
    max_z = max(origin[2] + size[2] for _, origin, size in envelopes)
    pad_x, pad_z = 55, 125
    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg", "role": "img",
        "aria-label": "Sección horizontal nominal de tableros, no fabricable",
        "viewBox": f"0 0 {max(580, max_x + 2*pad_x)} {max(320, max_z + pad_z + 65)}",
        "width": str(max(580, max_x + 2*pad_x)),
        "height": str(max(320, max_z + pad_z + 65)),
    })
    _sub(svg, "title", {}, f"CarpiNova · sección horizontal a Y={y_mm} mm · NO FABRICAR")
    _sub(svg, "style", {}, _CSS)
    _sub(svg, "rect", {"x": "0", "y": "0", "width": "100%",
                       "height": "100%", "fill": "#ffffff"})
    _sub(svg, "text", {"x": "30", "y": "35", "class": "alert"},
         "BORRADOR NOMINAL · NO CORTAR NI FABRICAR")
    _sub(svg, "text", {"x": "30", "y": "62", "class": "meta"},
         f"Sección horizontal Y={y_mm} mm · X derecha, Z hacia abajo · cotas mm")
    _sub(svg, "text", {"x": "30", "y": "83", "class": "meta"},
         "Solo paneles CAD existentes que atraviesan el plano; no representa bisagras, uniones ni cargas")

    # Background outlines are footprints, not a new cabinet construction model.
    for gid, origin, size in envelopes:
        attrs = {"x": str(origin[0]+pad_x), "y": str(origin[2]+pad_z),
                 "width": str(size[0]), "height": str(size[2]),
                 "class": "room", "data-group-id": gid}
        _sub(svg, "rect", attrs)
        _sub(svg, "text", {"x": str(origin[0]+pad_x+4),
                           "y": str(origin[2]+pad_z+20), "class": "name"}, gid)

    visible = 0
    for item, origin, size in measured:
        if not (origin[1] <= y_mm < origin[1]+size[1]):
            continue
        visible += 1
        role = item["role"]
        klass = ("front" if role.startswith("front_") or role == "drawer_facade" else
                 "back" if role.startswith("back_") else
                 "panel" if role in {"left_side","right_side","divider_vertical",
                                     "upper_front_tie","upper_rear_tie","lower_rear_tie"} else "other")
        rect = _sub(svg, "rect", {
            "x": str(origin[0]+pad_x), "y": str(origin[2]+pad_z),
            "width": str(size[0]), "height": str(size[2]),
            "class": f"panel {klass}", "data-piece-id": item["piece_id"],
            "data-role": role, "data-group-id": item["group_id"],
        })
        _sub(rect, "title", {},
             f"{item['piece_id']} · {role} · origen={origin} · tamaño={size} mm")

    for index, item in enumerate(review["service_zones"]):
        origin, size = _box(item, f"service_zones[{index}]")
        if origin[1] <= y_mm < origin[1]+size[1]:
            zone_id = item.get("zone_id", "ZONA")
            if type(zone_id) is not str:
                raise ValueError("ID de reserva inválido")
            rect = _sub(svg, "rect", {"x": str(origin[0]+pad_x),
                 "y": str(origin[2]+pad_z), "width": str(size[0]),
                 "height": str(size[2]), "class": "service"})
            _sub(rect, "title", {}, f"Reserva {zone_id}; NO es una perforación")

    _sub(svg, "text", {"x": "30", "y": str(max_z+pad_z+32),
                       "class": "meta"},
         f"Paneles visibles en sección: {visible} de {len(panels)} · "
         f"Estado: {review['status']} · No certifica fabricación")
    if review["status"] == "INTERFERENCE_REVIEW_REQUIRED":
        _sub(svg, "text", {"x": "30", "y": str(max_z+pad_z+53),
                           "class": "alert"}, "REVISAR INTERFERENCIAS ANTES DE CONTINUAR")
    return ET.tostring(svg, encoding="unicode", short_empty_elements=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vista horizontal nominal a partir de Maestro/F6/CADExchange; NO fabricación")
    parser.add_argument("--input", type=Path, required=True,
                        help="Archivo JSON de solicitud room_layout_v1 (no cajas CAD)")
    parser.add_argument("--output", type=Path, required=True,
                        help="SVG nuevo; nunca sobrescribe archivos existentes")
    parser.add_argument("--y-mm", type=int, required=True,
                        help="Altura de la sección horizontal en milímetros")
    args = parser.parse_args(argv)
    request = json.loads(args.input.read_text(encoding="utf-8"))
    if type(request) is not dict or request.get("review_kind") != "room_layout_v1":
        parser.error("--input debe contener una solicitud room_layout_v1")
    # Canonical trust boundary: rebuild every panel from the original specs.
    from .room_spatial import review_room_from_specs
    result = review_room_from_specs(request)
    svg = render_room_panel_section_svg(result, y_mm=args.y_mm)
    with args.output.open("x", encoding="utf-8") as dest:
        dest.write(svg)
    print(f"SECCION_2D=REVIEW_ONLY | Y_MM={args.y_mm} | SVG={args.output} | "
          f"ROOM_STATUS={result['status']} | FABRICATION=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
