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
    "drawer_weights", "opening_heights_mm",
})


def propose_drawer_layout(spec: Any) -> dict[str, Any]:
    """Propose 1–4 nominal openings bottom-to-top via the single F1 cabinet.

    The caller supplies every dimension and relative weight explicitly. A
    chat client can *suggest* [1, 1, 1, 2] for three small/one larger, but
    MUST show/confirm that interpretation before producing geometry.
    """
    required = DRAWER_LAYOUT_FIELDS - {"opening_heights_mm"}
    if (type(spec) is not dict or not required.issubset(spec)
            or set(spec) - DRAWER_LAYOUT_FIELDS):
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
    if "opening_heights_mm" in spec:
        explicit = spec["opening_heights_mm"]
        if (type(explicit) is not list or len(explicit) != len(weights)
                or any(type(v) is not int or v <= 0 for v in explicit)
                or sum(explicit) != space):
            raise DesignError(
                "Alturas ajustadas inválidas: deben ser enteros positivos "
                "y cerrar exactamente el hueco F1 con las franjas."
            )
        heights = list(explicit)
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
        "layout_source": ("EXPLICIT_HEIGHTS" if "opening_heights_mm" in spec
                          else "PROPORTIONAL_WEIGHTS"),
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



# Persistent human labels are top-to-bottom A, B, C, D.
# F1's D1..D4 remain bottom-to-top internal IDs and are never renamed.
OPENING_CHOICES = frozenset({
    "pending", "handle", "push_to_open", "finger_pull", "profile",
})
CHOICE_LABELS = {
    "pending": "por elegir",
    "handle": "manija (indicativa)",
    "push_to_open": "presión (indicativa)",
    "finger_pull": "uñero (indicativo)",
    "profile": "perfil (indicativo)",
}


def _annotated_openings(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(chr(65 + i), item)
            for i, item in enumerate(reversed(plan["opening_plan"]))]


def _guide_ref_map(plan: dict[str, Any]) -> list[dict[str, Any]]:
    styles = plan.get("opening_systems", {})
    return [
        {
            "ref": label,
            "engine_id": opening["drawer_id"],
            "kind": "drawer",
            "nominal_opening_height_mm": opening["opening_height_mm"],
            "opening_bottom_offset_mm": opening["opening_bottom_offset_mm"],
            "opening_system_intent": styles.get(label, "pending"),
        }
        for label, opening in _annotated_openings(plan)
    ] + [
        {"ref": "T", "kind": "top_panel",
         "concept_overhang_left_mm": plan.get("top_overhang_left_mm", 0),
         "concept_overhang_right_mm": plan.get("top_overhang_right_mm", 0)},
        {"ref": "LI", "kind": "left_side"},
        {"ref": "LD", "kind": "right_side"},
    ]


def drawer_layout_sketch_text(plan: dict[str, Any]) -> str:
    dims = plan["external_dimensions_mm"]
    refs = _guide_ref_map(plan)
    rows = [
        "BOCETO IDENTIFICADO · PROPUESTA, NO CORTAR",
        f"Ancho de carcasa {dims['width']} mm × alto {dims['height']} mm; "
        f"fondo de carcasa {dims['depth']} mm",
        "T = tapa superior (solo esquema; LI = lateral izquierdo, LD = derecho)",
        "ARRIBA",
    ]
    for item in refs:
        if item["kind"] == "drawer":
            large = item["nominal_opening_height_mm"] == max(
                opening["opening_height_mm"] for opening in plan["opening_plan"]
            ) and len({opening["opening_height_mm"]
                       for opening in plan["opening_plan"]}) > 1
            rows.append(
                f"[ {item['ref']} = {item['engine_id']} · "
                f"{'gaveta' if large else 'cajón'} · "
                f"{item['nominal_opening_height_mm']} mm · "
                f"{CHOICE_LABELS[item['opening_system_intent']]} ]"
            )
    rows.append("ABAJO")
    rows.append(
        f"T sobresale a izquierda/derecha: "
        f"{plan.get('top_overhang_left_mm', 0)} / "
        f"{plan.get('top_overhang_right_mm', 0)} mm; "
        "no está resuelto en la carcasa F1."
    )
    rows.append(
        f"Franjas internas de {plan['vertical_gap_mm']} mm: "
        "NO son divisores ni holguras visibles."
    )
    rows.append("Sin herrajes ni frentes fabricables. El dibujo es modificable.")
    return "\n".join(rows)


def drawer_layout_sketch_svg(plan: dict[str, Any]) -> str:
    """Annotated review SVG; all opening coordinates originate in F1."""
    dims = plan["external_dimensions_mm"]
    width, height = dims["width"], dims["height"]
    t = plan["panel_thickness_mm"]
    ext_l = plan.get("top_overhang_left_mm", 0)
    ext_r = plan.get("top_overhang_right_mm", 0)
    scale = min(255 / (width + ext_l + ext_r), 380 / height)
    left, top = 128.0 + ext_l * scale, 104.0
    w, h = width * scale, height * scale
    inner_l, inner_t = left + t * scale, top + t * scale
    inner_w = (width - 2 * t) * scale
    marks: list[str] = []
    for label, opening in _annotated_openings(plan):
        y = inner_t + (
            plan["clear_height_mm"]
            - opening["opening_bottom_offset_mm"]
            - opening["opening_height_mm"]
        ) * scale
        ph = opening["opening_height_mm"] * scale
        large = (opening["opening_height_mm"] ==
                 max(item["opening_height_mm"]
                     for item in plan["opening_plan"])
                 and len({item["opening_height_mm"]
                          for item in plan["opening_plan"]}) > 1)
        kind = "GAVETA" if large else "CAJÓN"
        choice = plan.get("opening_systems", {}).get(label, "pending")
        marks.append(
            f'<rect x="{inner_l:.2f}" y="{y:.2f}" '
            f'width="{inner_w:.2f}" height="{ph:.2f}" '
            f'fill="{"#d4e7e5" if large else "#e8edf4"}" '
            'stroke="#62768b" stroke-width="1.5"/>'
            f'<text x="{inner_l+9:.2f}" y="{y+ph/2+5:.2f}" '
            'class="ref">'
            f'{label}</text>'
            f'<path d="M {inner_l+inner_w:.2f} {y+ph/2:.2f} '
            f'L 449 {y+ph/2:.2f}" stroke="#738496" '
            'stroke-dasharray="4 3"/>'
            f'<text x="457" y="{y+ph/2-3:.2f}" class="dimension">'
            f'{label} ({opening["drawer_id"]}) · {kind} '
            f'{opening["opening_height_mm"]} mm</text>'
            f'<text x="457" y="{y+ph/2+17:.2f}" class="small">'
            f'{CHOICE_LABELS[choice]}</text>'
        )
        if choice == "handle":
            # Tiny handle symbol, not a real SKU or drill location.
            mx = inner_l + inner_w / 2
            marks.append(
                f'<path d="M {mx-11:.2f} {y+ph/2+5:.2f} '
                f'L {mx+11:.2f} {y+ph/2+5:.2f}" '
                'stroke="#43556c" stroke-width="3"/>'
            )
        elif choice == "finger_pull":
            marks.append(
                f'<path d="M {inner_l+inner_w/2-9:.2f} {y+4:.2f} '
                f'Q {inner_l+inner_w/2:.2f} {y+15:.2f} '
                f'{inner_l+inner_w/2+9:.2f} {y+4:.2f}" '
                'fill="none" stroke="#43556c" stroke-width="2"/>'
            )
        elif choice == "profile":
            marks.append(
                f'<line x1="{inner_l+2:.2f}" y1="{y+6:.2f}" '
                f'x2="{inner_l+inner_w-2:.2f}" y2="{y+6:.2f}" '
                'stroke="#43556c" stroke-width="3"/>'
            )
        elif choice == "push_to_open":
            marks.append(
                f'<text x="{inner_l+inner_w/2:.2f}" y="{y+ph/2+5:.2f}" '
                'class="small" text-anchor="middle">PUSH</text>'
            )
    top_extension = ""
    if ext_l or ext_r:
        top_extension = (
            f'<rect x="{left-ext_l*scale:.2f}" y="{top:.2f}" '
            f'width="{w+(ext_l+ext_r)*scale:.2f}" height="{t*scale:.2f}" '
            'fill="#fbdfb2" stroke="#9c672c" stroke-width="2" '
            'stroke-dasharray="5 3"/>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="820" height="650" viewBox="0 0 820 650" '
        'role="img" aria-label="Boceto frontal etiquetado de cajones '
        'y componentes, sujeto a revisión">'
        '<style>text{font-family:Arial,sans-serif;fill:#253446}'
        '.title{font-size:20px;font-weight:bold}'
        '.dimension{font-size:15px}.small{font-size:12px}'
        '.ref{font-size:19px;font-weight:bold}'
        '.note{font-size:13px;fill:#556577}</style>'
        '<rect width="820" height="650" rx="12" fill="#fafbfc"/>'
        '<text x="28" y="32" class="title">Tu mueble, por piezas identificadas</text>'
        '<text x="28" y="55" class="note">Di: “sube el cajón A 10 cm” '
        'o “haz que T sobresalga a ambos lados”.</text>'
        f'<rect x="{left:.2f}" y="{top:.2f}" width="{w:.2f}" '
        f'height="{h:.2f}" fill="#f5f7f9" '
        'stroke="#354657" stroke-width="3"/>'
        + top_extension
        + "".join(marks)
        + f'<text x="{left+w/2:.2f}" y="{top-16:.2f}" '
          'class="dimension" text-anchor="middle">'
          f'T · TAPA · {width+ext_l+ext_r} mm</text>'
        + f'<text x="36" y="{top+h/2:.2f}" class="dimension" '
          f'transform="rotate(-90 36 {top+h/2:.2f})" '
          'text-anchor="middle">'
          f'ALTO {height} mm</text>'
        + f'<text x="{left-25:.2f}" y="{top+h/2:.2f}" '
          'class="ref">LI</text>'
        + f'<text x="{left+w+8:.2f}" y="{top+h-14:.2f}" '
          'class="ref">LD</text>'
        + f'<text x="30" y="524" class="note">'
          f'Carcasa: ancho {width}, alto {height}, fondo {dims["depth"]} mm. '
          f'Tablero supuesto: {t} mm.</text>'
        + f'<text x="30" y="547" class="note">'
          f'T: saliente izquierda {ext_l} / derecha {ext_r} mm '
          '(solo idea, NO calculado como panel).</text>'
        + f'<text x="30" y="570" class="note">'
          f'Franjas internas: {plan["vertical_gap_mm"]} mm; '
          'no son espacios entre frentes ni divisores.</text>'
        + '<text x="30" y="596" class="note">'
          'Sistemas: manija, presión, uñero o perfil '
          '(dibujos genéricos; no herrajes verificados).</text>'
        + '<text x="30" y="624" class="note">'
          'BOCETO · NO CORTAR, TALADRAR NI COMPRAR.</text></svg>'
    )


DRAWER_GUIDE_FIELDS = frozenset({
    "type", "width_mm", "height_mm", "depth_mm", "small_drawers",
    "large_drawer_position", "drawer_adjustments_mm",
    "top_overhang_left_mm", "top_overhang_right_mm", "opening_systems",
})


def _apportion_nominal(remaining: int, weights: list[int]) -> list[int]:
    """Exact integer distribution; same largest-remainder rule as F1 plan."""
    if not weights:
        if remaining != 0:
            raise DesignError("Las modificaciones alteran la altura total; falta compensación.")
        return []
    if remaining < len(weights):
        raise DesignError("Las modificaciones dejan algún cajón sin altura suficiente.")
    total = sum(weights)
    result = [remaining * w // total for w in weights]
    residue = remaining - sum(result)
    ranked = sorted(range(len(weights)),
                    key=lambda i: (-(remaining * weights[i] % total), i))
    for i in ranked[:residue]:
        result[i] += 1
    if min(result) <= 0:
        raise DesignError("La nueva proporción deja una abertura sin altura.")
    return result


def guide_drawer_layout(spec: Any) -> dict[str, Any]:
    """Revisable concept only; never silently turn decisions into CAD.

    A-D label openings top-to-bottom, whereas F1 D1-D4 remain bottom-to-top.
    All parameters except dimensions, count and explicitly requested edits are
    EXAMPLE assumptions. Revisions must show affected other drawers.
    """
    if (type(spec) is not dict or spec.get("type") != "drawer_layout_guide"
            or set(spec) - DRAWER_GUIDE_FIELDS
            or not {"type", "width_mm", "height_mm", "depth_mm",
                    "small_drawers"}.issubset(spec)):
        raise DesignError(
            "Boceto guiado: ancho, alto, fondo y cantidad de cajones pequeños."
        )
    n = spec["small_drawers"]
    if type(n) is not int or not 1 <= n <= 3:
        raise DesignError("small_drawers debe ser entero entre 1 y 3.")
    position = spec.get("large_drawer_position", "bottom")
    if position not in ("bottom", "top"):
        raise DesignError("La gaveta grande va arriba o abajo.")
    refs = [chr(65 + i) for i in range(n + 1)]
    adjustments = spec.get("drawer_adjustments_mm", {})
    if (type(adjustments) is not dict
            or any(ref not in refs or type(delta) is not int
                   or not -2000 <= delta <= 2000
                   for ref, delta in adjustments.items())):
        raise DesignError(
            "Modificaciones: usar letras de los cajones y milímetros enteros "
            "con signo. Ejemplo A +100, B -100."
        )
    choices = spec.get("opening_systems", {})
    if (type(choices) is not dict
            or any(ref not in refs or type(option) is not str
                   or option not in OPENING_CHOICES
                   for ref, option in choices.items())):
        raise DesignError(
            "Sistemas de apertura: usar A-D y pending/handle/"
            "push_to_open/finger_pull/profile. Aún no especifican herrajes."
        )
    left = spec.get("top_overhang_left_mm", 0)
    right = spec.get("top_overhang_right_mm", 0)
    if any(type(value) is not int or not 0 <= value <= 200
           for value in (left, right)):
        raise DesignError(
            "Saliente de tapa T: indicar en mm entre 0 y 200 para "
            "izquierda/derecha (solo concepto)."
        )
    weights = ([2] + [1] * n if position == "bottom"
               else [1] * n + [2])
    proposed = {
        "type": "drawer_layout_proposal",
        "width_mm": spec["width_mm"],
        "height_mm": spec["height_mm"],
        "depth_mm": spec["depth_mm"],
        "panel_thickness_mm": 18,
        "construction": "sides_full",
        "vertical_gap_mm": 28,
        "drawer_weights": weights,
    }
    base = propose_drawer_layout(proposed)
    base_top = [x["opening_height_mm"]
                for x in reversed(base["opening_plan"])]
    if adjustments and any(adjustments.values()):
        fixed = {refs.index(ref): base_top[refs.index(ref)] + delta
                 for ref, delta in adjustments.items()
                 if delta != 0}
        if any(height <= 0 for height in fixed.values()):
            raise DesignError("El cambio solicitado deja un cajón sin altura.")
        free = [i for i in range(len(refs)) if i not in fixed]
        remaining = sum(base_top) - sum(fixed.values())
        assigned = _apportion_nominal(remaining, [base_top[i] for i in free])
        heights = [0] * len(refs)
        for i, height in fixed.items():
            heights[i] = height
        for i, height in zip(free, assigned):
            heights[i] = height
        # Pass exact heights back through the existing F1 proposal validation.
        proposed["opening_heights_mm"] = list(reversed(heights))
        result = propose_drawer_layout(proposed)
    else:
        result = base
    new_top = [x["opening_height_mm"]
               for x in reversed(result["opening_plan"])]
    revisions = [
        {
            "ref": ref,
            "before_mm": old, "after_mm": new,
            "delta_mm": new - old,
            "cause": ("USER_REQUESTED" if adjustments.get(ref, 0) != 0
                      else "AUTO_REDISTRIBUTED_TO_KEEP_TOTAL_HEIGHT"),
        }
        for ref, old, new in zip(refs, base_top, new_top) if old != new
    ]
    result.update({
        "type": "drawer_layout_guide",
        "guided": True,
        "opening_systems": dict(choices),
        "top_overhang_left_mm": left,
        "top_overhang_right_mm": right,
        "unvalidated_top_extension": bool(left or right),
        "revisions": revisions,
        "proposed_layout_spec": proposed,
        "review_state": dict(spec),
        "suggestions_not_confirmed": {
            "panel_thickness_mm": 18, "construction": "sides_full",
            "vertical_gap_mm": 28, "drawer_weights": list(weights),
            "large_drawer_position": position,
        },
        "can_generate_f7c": False,
    })
    result["element_refs"] = _guide_ref_map(result)
    result["sketch_text"] = drawer_layout_sketch_text(result)
    result["sketch_svg"] = drawer_layout_sketch_svg(result)
    result["human_summary"] = (
        f"Te propongo {n} cajones pequeños y una gaveta grande "
        + ("abajo" if position == "bottom" else "arriba")
        + ". Identifiqué A-D (arriba hacia abajo), T (tapa), LI/LD "
          "(laterales). Puedes pedirme «A 10 cm más alto» o «T sobresale "
          "5 cm»; te mostraré cómo afecta a las demás piezas. "
          "Los 18 mm de tablero y 28 mm de franjas internas son solo "
          "supuestos para la propuesta, no especificaciones."
    )
    result["blockers"].insert(
        0, "Boceto editable, NO plano de despiece: confirmar cada opción "
           "técnica antes de crear piezas."
    )
    if revisions:
        result["blockers"].insert(
            1, "Las medidas modificadas redistribuyeron la altura de los "
               "cajones no fijados; revisar TODOS los cambios de revisions."
        )
    if left or right:
        result["blockers"].insert(
            1, "Voladizo de T SOLO ilustrado: el motor F1 actual no "
               "modela tapa saliente ni ha validado su soporte/rigidez. "
               "No convertir este boceto directamente en F7C."
        )
    return result
