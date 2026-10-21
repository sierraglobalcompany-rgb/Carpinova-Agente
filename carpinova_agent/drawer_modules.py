"""F7C Task 3 — modular drawer instances, sourced only from F1 design_drawer.

Inset decorative drawer faces are optional explicit parts. No slide SKU,
runners, drilled holes, fastening or fabrication release.
"""
from __future__ import annotations
import re
from typing import Any

from .core import DesignError, design

IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
GRAINS = {"face_x", "face_y", "none"}
EDGES = {"x_min", "x_max", "y_min", "y_max"}
DRAWER_FIELDS = frozenset({
    "drawer_id", "opening_bottom_offset_mm", "opening_height_mm",
    "opening_depth_mm", "box_height_mm", "panel_thickness_mm",
    "bottom_thickness_mm", "slide_clearance_left_mm",
    "slide_clearance_right_mm", "front_setback_mm", "rear_setback_mm",
    "material_id", "bottom_material_id", "facade"
})
FACADE_REQUIRED = frozenset({
    "style", "material_id", "thickness_mm", "left_clearance_mm",
    "right_clearance_mm", "top_clearance_mm", "bottom_clearance_mm"
})
FACADE_OPTIONAL = frozenset({
    "grain_axis", "edgebanding_edges", "edgeband_thickness_mm",
    "opening_system",
})
# F7C_DRAWR_OVERLAY_INTEGRATED_20261021
# Do not alter the original inset contract; overlay requires explicit overlaps.
OVERLAY_REQUIRED = frozenset({
    "style", "material_id", "thickness_mm", "left_overlap_mm",
    "right_overlap_mm", "top_overlap_mm", "bottom_overlap_mm",
})
OPENING_SYSTEMS = frozenset({
    "pending", "handle", "push_to_open", "finger_pull", "profile",
})


def _mm(value: Any, label: str, *, allow_zero: bool = False) -> int:
    if type(value) is not int or value < 0 or (not allow_zero and value == 0):
        raise DesignError(f"{label}: milímetros enteros {'no negativos' if allow_zero else 'positivos'} requeridos.")
    return value


def _id(value: Any, label: str) -> str:
    if type(value) is not str or not IDENT.fullmatch(value):
        raise DesignError(f"{label}: identificador no válido.")
    return value


def _finish(facade: dict[str, Any], drawer_id: str) -> tuple[str, str | list[str], int | None]:
    grain = facade.get("grain_axis", "UNCONFIRMED")
    if type(grain) is not str or grain not in GRAINS | {"UNCONFIRMED"}:
        raise DesignError(f"{drawer_id}: veta de frente inválida.")
    edges = facade.get("edgebanding_edges", "UNCONFIRMED")
    thickness = facade.get("edgeband_thickness_mm")
    if edges == "UNCONFIRMED":
        if thickness is not None:
            raise DesignError(f"{drawer_id}: espesor de canto sin bordes.")
        return grain, "UNCONFIRMED", None
    if (type(edges) is not list or any(type(e) is not str or e not in EDGES for e in edges)
            or len(edges) != len(set(edges))):
        raise DesignError(f"{drawer_id}: bordes del frente inválidos.")
    if edges:
        _mm(thickness, "edgeband_thickness_mm")
    elif thickness is not None:
        raise DesignError(f"{drawer_id}: espesor de canto sin bordes.")
    return grain, sorted(edges), thickness


def _part(module_id: str, drawer_id: str, role: str, material: str,
          fx: int, fy: int, thickness: int, plane: str, origin: list[int],
          formula: str, *, grain: str = "UNCONFIRMED",
          edges: str | list[str] = "UNCONFIRMED",
          edge_thickness: int | None = None,
          facade_style: str = "inset") -> dict[str, Any]:
    band = None if edges == "UNCONFIRMED" else sum(
        fy if e.startswith("x_") else fx for e in edges
    )
    return {
        "piece_id": f"{module_id}-{drawer_id}-{role.upper()}",
        "module_id": module_id, "drawer_id": drawer_id, "role": role,
        "material_id": material, "nominal_face_x_mm": fx,
        "nominal_face_y_mm": fy, "thickness_mm": thickness,
        "face_plane": plane, "nominal_origin_xyz_mm": origin,
        "grain_axis": grain, "edgebanding_edges": edges,
        "edgebanding_thickness_mm": edge_thickness,
        "edgebanding_nominal_total_mm": band,
        "finished_cut_dimensions_mm": None,
        "source_engine": ("F1_CORE_DRAWER" if role != "drawer_facade"
                          else "F7C_EXPLICIT_" + facade_style.upper() + "_FACADE"),
        "source_formula": formula,
    }


def _facade(data: Any, *, module_id: str, drawer_id: str,
            aperture_width: int, aperture_height: int,
            opening_y: int, opening_x: int,
            front_setback: int, carcase_thickness: int,
            module_height: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Create a *nominal* inset or overlay decorative drawer face.

    Both styles use the same F1 opening; unlike an inset front, an overlay
    face extends onto the surrounding carcass and sits at negative Z.
    All four overlaps must be given explicitly and cannot exceed the
    local frame thickness. They are NOT assumed hardware defaults.
    """
    if data == "pending":
        return [], [f"{module_id}/{drawer_id}: falta frente decorativo de cajón."]
    if type(data) is not dict:
        raise DesignError(f"{drawer_id}.facade: usar pending o un objeto.")
    style = data.get("style")
    if style not in {"inset", "overlay"}:
        raise DesignError(f"{drawer_id}: facade.style debe ser inset u overlay.")
    required = FACADE_REQUIRED if style == "inset" else OVERLAY_REQUIRED
    if set(data) - (required | FACADE_OPTIONAL) or required - set(data):
        raise DesignError(f"{drawer_id}.facade: campos ausentes o incompatibles con {style}.")
    opening_system = data.get("opening_system", "pending")
    if type(opening_system) is not str or opening_system not in OPENING_SYSTEMS:
        raise DesignError(f"{drawer_id}: opening_system no reconocido; confirmar alternativa.")
    material = _id(data["material_id"], "facade.material_id")
    thick = _mm(data["thickness_mm"], "facade.thickness_mm")
    if style == "inset":
        gaps = {key: _mm(data[key], "facade." + key) for key in (
            "left_clearance_mm", "right_clearance_mm",
            "top_clearance_mm", "bottom_clearance_mm")}
        fx = aperture_width - gaps["left_clearance_mm"] - gaps["right_clearance_mm"]
        fy = aperture_height - gaps["top_clearance_mm"] - gaps["bottom_clearance_mm"]
        x = opening_x + gaps["left_clearance_mm"]
        y = opening_y + gaps["bottom_clearance_mm"]
        z = 0
        formula = "F1.clear_width_mm - two explicit horizontal clearances; drawer.opening_height_mm - two explicit vertical clearances"
    else:
        overlaps = {key: _mm(data[key], "facade." + key, allow_zero=True) for key in (
            "left_overlap_mm", "right_overlap_mm",
            "top_overlap_mm", "bottom_overlap_mm")}
        if not any(overlaps.values()):
            raise DesignError(f"{drawer_id}: frente overlay sin solape real; usar inset o declarar solapes.")
        if any(v > carcase_thickness for v in overlaps.values()):
            raise DesignError(f"{drawer_id}: solape mayor que el marco estructural.")
        fx = aperture_width + overlaps["left_overlap_mm"] + overlaps["right_overlap_mm"]
        fy = aperture_height + overlaps["top_overlap_mm"] + overlaps["bottom_overlap_mm"]
        x = opening_x - overlaps["left_overlap_mm"]
        y = opening_y - overlaps["bottom_overlap_mm"]
        z = -thick
        formula = "F7C.overlay: F1 clear opening plus four explicit bounded frame overlaps"
    if min(fx, fy) <= 0:
        raise DesignError(f"{drawer_id}: frente no cabe en la abertura.")
    # Keep every facade inside the parent module's external front rectangle.
    if (x < opening_x - carcase_thickness
            or x + fx > opening_x + aperture_width + carcase_thickness
            or y < 0 or y + fy > module_height):
        raise DesignError(f"{drawer_id}: frente invade espacio exterior del módulo.")
    if front_setback <= thick:
        raise DesignError(
            f"{drawer_id}: retranqueo de caja debe superar espesor del frente "
            "para que no ocupen el mismo volumen."
        )
    grain, edges, band_t = _finish(data, drawer_id)
    face = _part(
        module_id, drawer_id, "drawer_facade", material, fx, fy, thick,
        "XY", [x, y, z], formula,
        grain=grain, edges=edges, edge_thickness=band_t,
        facade_style=style,
    )
    # Opening mechanism is an *intent*, not a drilled or modeled mechanism.
    face["opening_system"] = opening_system
    blockers = [
        f"{module_id}/{drawer_id}: frente decorativo sin uniones, tiradores, "
        "cantos finales ni validación de montaje."
    ]
    if opening_system == "pending":
        blockers.append(f"{module_id}/{drawer_id}: decidir tirador, push-to-open, uñero o perfil.")
    elif opening_system == "profile":
        blockers.append(f"{module_id}/{drawer_id}: perfil elegido sin sección SKU ni mecanizado validado.")
    elif opening_system in {"handle", "push_to_open", "finger_pull"}:
        blockers.append(f"{module_id}/{drawer_id}: sistema {opening_system} requiere ficha/compatibilidad; no hay taladros ni fresados aprobados.")
    if grain == "UNCONFIRMED":
        blockers.append(f"{module_id}/{drawer_id}: falta orientación de veta decorativa.")
    if edges == "UNCONFIRMED":
        blockers.append(f"{module_id}/{drawer_id}: falta decisión de cantos decorativos.")
    return [face], blockers


def module_drawers(drawers: Any, *, module_id: str,
                   start_x_mm: int, carcase_thickness_mm: int,
                   clear_width_mm: int, clear_height_mm: int,
                   module_depth_mm: int, back_parts: list[dict[str, Any]],
                   has_doors: bool) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Append only physical panels calculated by F1, in declared clear apertures."""
    if drawers is None or drawers == "none":
        return [], [], []
    if drawers == "pending":
        return [], [f"{module_id}: elegir cantidad, aperturas y correderas de cajones."], []
    if type(drawers) is not list or not 1 <= len(drawers) <= 4:
        raise DesignError(f"{module_id}.drawers: usar none, pending o lista de 1 a 4.")
    if has_doors:
        raise DesignError(f"{module_id}: cajones con puertas configuradas requieren "
                          "validación de giro/colisión; usar otro módulo.")
    all_parts: list[dict[str, Any]] = []
    blockers: list[str] = []
    ids: list[str] = []
    openings: list[tuple[int, int]] = []
    for index, request in enumerate(drawers):
        if type(request) is not dict or set(request) != DRAWER_FIELDS:
            raise DesignError(f"{module_id}.drawers[{index}]: campos faltantes o desconocidos.")
        drawer_id = _id(request["drawer_id"], "drawer_id")
        if drawer_id in ids:
            raise DesignError(f"{module_id}: drawer_id repetido.")
        ids.append(drawer_id)
        material = _id(request["material_id"], "drawer.material_id")
        bottom_material = _id(request["bottom_material_id"], "drawer.bottom_material_id")
        offset = _mm(request["opening_bottom_offset_mm"], "opening_bottom_offset_mm", allow_zero=True)
        aperture_h = _mm(request["opening_height_mm"], "opening_height_mm")
        aperture_d = _mm(request["opening_depth_mm"], "opening_depth_mm")
        if offset + aperture_h > clear_height_mm or aperture_d > module_depth_mm:
            raise DesignError(f"{module_id}/{drawer_id}: abertura excede el cuerpo.")
        openings.append((offset, offset+aperture_h))
        spec = {
            "type": "drawer",
            "opening_width_mm": clear_width_mm,
            "opening_height_mm": aperture_h,
            "opening_depth_mm": aperture_d,
            **{k: request[k] for k in (
                "box_height_mm", "panel_thickness_mm", "bottom_thickness_mm",
                "slide_clearance_left_mm", "slide_clearance_right_mm",
                "front_setback_mm", "rear_setback_mm")},
        }
        result = design(spec)  # one authoritative F1 calculation
        dimensions = result["dimensions"]
        x = start_x_mm + carcase_thickness_mm + request["slide_clearance_left_mm"]
        y = carcase_thickness_mm + offset
        z = request["front_setback_mm"]
        box_w = dimensions["box_external_width_mm"]
        box_d = dimensions["box_external_depth_mm"]
        wall_h = dimensions["wall_height_mm"]
        t = request["panel_thickness_mm"]
        bt = request["bottom_thickness_mm"]
        if box_d <= t:
            raise DesignError(f"{module_id}/{drawer_id}: profundidad incompatible con paredes.")
        # Strictly guard interior volumes against a real back board if one exists.
        rear_z = min((p["nominal_origin_xyz_mm"][2] for p in back_parts), default=module_depth_mm)
        if z + box_d > rear_z:
            raise DesignError(
                f"{module_id}/{drawer_id}: la caja invade fondo posterior."
            )
        # Side walls are YZ; front and back walls XY; under-bottom XZ.
        specs = (
            ("drawer_side_left", material, box_d, wall_h, t,
             "YZ", [x, y+bt, z], result["parts"][0]["calculation"]),
            ("drawer_side_right", material, box_d, wall_h, t,
             "YZ", [x+box_w-t, y+bt, z], result["parts"][0]["calculation"]),
            ("drawer_front_wall", material, dimensions["box_inner_width_mm"], wall_h, t,
             "XY", [x+t, y+bt, z], result["parts"][1]["calculation"]),
            ("drawer_rear_wall", material, dimensions["box_inner_width_mm"], wall_h, t,
             "XY", [x+t, y+bt, z+box_d-t], result["parts"][1]["calculation"]),
            ("drawer_bottom", bottom_material, box_w, box_d, bt,
             "XZ", [x, y, z], result["parts"][2]["calculation"]),
        )
        for role, mat, fx, fy, thick, plane, origin, formula in specs:
            all_parts.append(_part(module_id, drawer_id, role, mat,
                                   fx, fy, thick, plane, origin, formula))
        fronts, front_blockers = _facade(
            request["facade"], module_id=module_id, drawer_id=drawer_id,
            aperture_width=clear_width_mm, aperture_height=aperture_h,
            opening_y=y, opening_x=start_x_mm + carcase_thickness_mm,
            front_setback=z,
            carcase_thickness=carcase_thickness_mm,
            module_height=clear_height_mm + 2 * carcase_thickness_mm,
        )
        all_parts.extend(fronts)
        blockers.extend(front_blockers)
        blockers.append(
            f"{module_id}/{drawer_id}: luces de corredera declaradas por usuario, "
            "SIN validar SKU, longitud, capacidad, fijación, cotas de taladros "
            "ni resistencia del fondo aplicado."
        )
    sorted_openings = sorted(openings)
    if any(a[1] >= b[0] for a, b in zip(sorted_openings, sorted_openings[1:])):
        raise DesignError(f"{module_id}: aperturas verticales se solapan o tocan.")
    # Catch adjacent overlay/inset decorative face collisions independently
    # of the drawer opening check. Touching faces are rejected as well.
    facades = [p for p in all_parts if p["role"] == "drawer_facade"]
    for ix, a in enumerate(facades):
        ax, ay, _ = a["nominal_origin_xyz_mm"]
        aw, ah = a["nominal_face_x_mm"], a["nominal_face_y_mm"]
        for b in facades[ix + 1:]:
            bx, by, _ = b["nominal_origin_xyz_mm"]
            bw, bh = b["nominal_face_x_mm"], b["nominal_face_y_mm"]
            if (ax <= bx + bw and bx <= ax + aw
                    and ay <= by + bh and by <= ay + ah):
                raise DesignError(
                    f"{module_id}: fachadas {a['piece_id']} y {b['piece_id']} se tocan o solapan."
                )
    return all_parts, blockers, ids

# A compact, REVIEW-ONLY calculation routed through the existing Maestro.
# It does not produce panels, choose runners or infer manufacturing clearances.
DRAWER_LAYOUT_FIELDS = frozenset({
    "type", "width_mm", "height_mm", "depth_mm",
    "panel_thickness_mm", "construction", "vertical_gap_mm",
    "drawer_weights",
})


def propose_drawer_layout(spec: Any) -> dict[str, Any]:
    """Propose 1–4 nominal openings bottom-to-top via the single F1 cabinet.

    The caller supplies every dimension and relative weight explicitly. A
    chat client can *suggest* [1, 1, 1, 2] for three small/one larger, but
    MUST show/confirm that interpretation before producing geometry.
    """
    if type(spec) is not dict or set(spec) != DRAWER_LAYOUT_FIELDS:
        raise DesignError("drawer_layout_proposal: campos requeridos/desconocidos; "
                          "ancho, alto, fondo, tablero, construcción, separación y pesos.")
    if spec["type"] != "drawer_layout_proposal":
        raise DesignError("type debe ser drawer_layout_proposal.")
    cabinet = design({
        "type": "cabinet",
        **{key: spec[key] for key in (
            "width_mm", "height_mm", "depth_mm",
            "panel_thickness_mm", "construction"
        )},
    })
    weights = spec["drawer_weights"]
    if (type(weights) is not list or not 1 <= len(weights) <= 4
            or any(type(w) is not int or not 1 <= w <= 100 for w in weights)):
        raise DesignError("drawer_weights: lista de 1 a 4 enteros entre 1 y 100.")
    # One drawer has no inter-drawer separator. Multiple openings require
    # a positive separation so F7C will never receive touching apertures.
    gap = _mm(spec["vertical_gap_mm"], "vertical_gap_mm",
              allow_zero=len(weights) == 1)
    clear_height = cabinet["dimensions"]["clear_height_mm"]
    space = clear_height - (len(weights) - 1) * gap
    if space < len(weights):
        raise DesignError("No caben aperturas positivas tras las separaciones indicadas.")
    # Largest remainders apportion indivisible millimetres fairly instead
    # of loading ALL rounding residue into the last (often largest) drawer.
    # Stable index order breaks equal fractional remainders; integer-only.
    total = sum(weights)
    heights = [space * w // total for w in weights]
    extra = space - sum(heights)
    ranked = sorted(range(len(weights)),
                    key=lambda i: (-(space * weights[i] % total), i))
    for index in ranked[:extra]:
        heights[index] += 1
    if min(heights) <= 0:
        raise DesignError("La distribución deja una abertura sin altura positiva.")
    openings: list[dict[str, int | str]] = []
    cursor = 0
    for index, height in enumerate(heights, 1):
        openings.append({
            "drawer_id": f"D{index}",
            "opening_bottom_offset_mm": cursor,
            "opening_height_mm": height,
        })
        cursor += height + (gap if index < len(heights) else 0)
    if cursor != clear_height:
        raise DesignError("Error de integridad: alturas y separaciones no cierran.")
    result = {
        "schema_version": "0.1.0",
        "type": "drawer_layout_proposal",
        "status": "NEEDS_USER_CONFIRMATION",
        "source_engine": "F1_CORE_CABINET",
        "bottom_to_top": True,
        "external_dimensions_mm": {
            "width": spec["width_mm"], "height": spec["height_mm"],
            "depth": spec["depth_mm"],
        },
        "panel_thickness_mm": spec["panel_thickness_mm"],
        "construction": spec["construction"],
        "clear_height_mm": clear_height,
        "vertical_gap_mm": gap,
        "drawer_weights": list(weights),
        "opening_plan": openings,
        "depth_scope": "CARCASS_ONLY_UNTIL_FACADE_SELECTED",
        "assembled_external_depth_mm": None,
        "parts": [],
        "piece_count": 0,
        "fabrication_ready": False, "cutting_ready": False,
        "drilling_ready": False, "purchase_ready": False,
        "blockers": [
            "Propuesta de aperturas nominales: confirmar posición y proporciones "
            "de todos los cajones antes de diseñar.",
            "Separaciones geométricas entre franjas: NO son paneles divisores "
            "ni prueban montaje de correderas o carga.",
            "Faltan cotas de caja, frente, holguras de herrajes, fondo, "
            "materiales y autorización de fabricación.",
            "Confirmar si la profundidad total solicitada incluye el "
            "frente sobrepuesto: el plano propuesto usa profundidad "
            "de carcasa, sin espesor de fachada.",
        ],
    }
    result["sketch_svg"] = drawer_layout_sketch_svg(result)
    result["sketch_text"] = drawer_layout_sketch_text(result)
    return result


def drawer_layout_sketch_text(plan: dict[str, Any]) -> str:
    """Short, human-readable front sketch; no fabricated facades or rails."""
    dims = plan["external_dimensions_mm"]
    rows = [
        "BOCETO FRONTAL · PROPUESTA, NO CORTAR",
        f"Ancho {dims['width']} mm × alto {dims['height']} mm; "
        f"fondo de carcasa {dims['depth']} mm",
        "ARRIBA",
    ]
    openings = plan["opening_plan"]
    for index, item in enumerate(reversed(openings)):
        is_large = item["opening_height_mm"] == max(
            x["opening_height_mm"] for x in openings
        ) and len({x["opening_height_mm"] for x in openings}) > 1
        label = "gaveta grande" if is_large else "cajón"
        rows.append(
            f"[ {item['drawer_id']} · {label} · "
            f"{item['opening_height_mm']} mm de abertura ]"
        )
        if index < len(openings) - 1:
            rows.append(
                f"·· franja de {plan['vertical_gap_mm']} mm "
                "(NO es divisor ni espacio entre frentes) ··"
            )
    rows.extend(["ABAJO", "Sin fachadas/correderas/patas definidas. "
                 "Las medidas son ilustrativas."])
    return "\n".join(rows)


def drawer_layout_sketch_svg(plan: dict[str, Any]) -> str:
    """Annotated SVG using F1 opening_plan, without a second geometry engine."""
    dims = plan["external_dimensions_mm"]
    width, height = dims["width"], dims["height"]
    t = plan["panel_thickness_mm"]
    scale = min(250 / width, 390 / height)
    left, top = 115.0, 90.0
    w, h = width * scale, height * scale
    inner_left, inner_top = left + t * scale, top + t * scale
    inner_w = (width - 2 * t) * scale
    marks: list[str] = []
    for opening in plan["opening_plan"]:
        y = inner_top + (plan["clear_height_mm"]
                         - opening["opening_bottom_offset_mm"]
                         - opening["opening_height_mm"]) * scale
        ph = opening["opening_height_mm"] * scale
        big = (opening["opening_height_mm"] ==
               max(item["opening_height_mm"] for item in plan["opening_plan"])
               and len({item["opening_height_mm"]
                        for item in plan["opening_plan"]}) > 1)
        label = "GAVETA" if big else "CAJÓN"
        marks.append(
            f'<rect x="{inner_left:.2f}" y="{y:.2f}" '
            f'width="{inner_w:.2f}" height="{ph:.2f}" '
            f'fill="{"#d4e7e5" if big else "#e8edf4"}" '
            'stroke="#62768b" stroke-width="1.5"/>'
            f'<line x1="{inner_left+inner_w:.2f}" y1="{y+ph/2:.2f}" '
            f'x2="450" y2="{y+ph/2:.2f}" '
            'stroke="#738496" stroke-dasharray="4 3"/>'
            f'<text x="461" y="{y+ph/2+5:.2f}" class="dimension">'
            f'{opening["drawer_id"]} {label} · {opening["opening_height_mm"]} mm</text>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="800" height="610" viewBox="0 0 800 610" '
        'role="img" aria-label="Boceto frontal de propuesta de cajones, sin herrajes">'
        '<style>'
        'text{font-family:Arial,sans-serif;fill:#253446}'
        '.title{font-size:21px;font-weight:bold}'
        '.dimension{font-size:15px}'
        '.note{font-size:14px;fill:#556577}'
        '</style>'
        '<rect width="800" height="610" rx="14" fill="#fafbfc"/>'
        '<text x="34" y="37" class="title">Así podría quedar tu mueble</text>'
        '<text x="34" y="60" class="note">BOCETO · medidas nominales para conversar</text>'
        f'<rect x="{left:.2f}" y="{top:.2f}" width="{w:.2f}" '
        f'height="{h:.2f}" fill="#f5f7f9" stroke="#354657" stroke-width="3"/>'
        + "".join(marks)
        + f'<text x="{left+w/2:.2f}" y="{top-12:.2f}" '
          f'text-anchor="middle" class="dimension">ANCHO {width} mm</text>'
        + f'<text x="23" y="{top+h/2:.2f}" class="dimension" '
          f'transform="rotate(-90 23 {top+h/2:.2f})" '
          f'text-anchor="middle">ALTO {height} mm</text>'
        + f'<text x="34" y="525" class="note">Fondo de carcasa: {dims["depth"]} mm · '
          f'Tablero ilustrativo: {t} mm</text>'
        + f'<text x="34" y="546" class="note">Bandas entre aberturas: '
          f'{plan["vertical_gap_mm"]} mm (no representan divisores ni fachadas)</text>'
        + '<text x="34" y="577" class="note">NO CORTAR · No se han '
          'seleccionado correderas, frente ni herrajes.</text>'
        + '</svg>'
    )


DRAWER_GUIDE_FIELDS = frozenset({
    "type", "width_mm", "height_mm", "depth_mm", "small_drawers",
    "large_drawer_position",
})


def guide_drawer_layout(spec: Any) -> dict[str, Any]:
    """Friendly, opt-in F1 sketch with disclosed EXAMPLE assumptions only.

    No user is expected to know panel thickness, gaps, ratios or jargon.
    Defaults are proposals, not facts, purchase specs or manufacturing approval.
    """
    if type(spec) is not dict or spec.get("type") != "drawer_layout_guide" or (
        set(spec) - DRAWER_GUIDE_FIELDS
    ) or not {"type", "width_mm", "height_mm", "depth_mm",
              "small_drawers"}.issubset(spec):
        raise DesignError(
            "Para boceto guiado: ancho, alto, fondo y cantidad de cajones pequeños."
        )
    n = spec["small_drawers"]
    if type(n) is not int or not 1 <= n <= 3:
        raise DesignError("small_drawers debe estar entre 1 y 3.")
    position = spec.get("large_drawer_position", "bottom")
    if position not in ("bottom", "top"):
        raise DesignError("La gaveta grande va arriba o abajo.")
    weights = ([2] + [1] * n if position == "bottom"
               else [1] * n + [2])
    illustrative_spec = {
        "type": "drawer_layout_proposal",
        "width_mm": spec["width_mm"],
        "height_mm": spec["height_mm"],
        "depth_mm": spec["depth_mm"],
        "panel_thickness_mm": 18,
        "construction": "sides_full",
        "vertical_gap_mm": 28,
        "drawer_weights": weights,
    }
    result = propose_drawer_layout(illustrative_spec)
    result["type"] = "drawer_layout_guide"
    result["guided"] = True
    result["proposed_layout_spec"] = illustrative_spec
    result["suggestions_not_confirmed"] = {
        "panel_thickness_mm": 18,
        "construction": "sides_full",
        "vertical_gap_mm": 28,
        "drawer_weights": list(weights),
        "large_drawer_position": position,
    }
    result["human_summary"] = (
        "Te propongo una gaveta grande "
        + ("abajo" if position == "bottom" else "arriba")
        + f" y {n} cajones más pequeños. Mira el boceto antes de elegir "
          "medidas y herrajes. Los 18 mm de tablero y 28 mm entre aberturas "
          "son solo supuestos para dibujar; NO son especificaciones."
    )
    result["blockers"].insert(
        0, "Boceto guiado con supuestos no aprobados: primero confirmar "
           "distribución, tablero y geometría antes de cualquier borrador."
    )
    return result
