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
FRONT_CONSTRUCTIONS = frozenset(("separate", "integrated_overlay"))
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
            module_height: int, structural_front: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
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
    if structural_front:
        if style != "overlay" or front_setback != 0:
            raise DesignError(f"{drawer_id}: frente único exige overlay y retranqueo cero.")
    elif front_setback <= thick:
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
    blockers = ([f"{module_id}/{drawer_id}: frente exterior estructural, "
                 "unión a laterales y base PENDIENTE DE VALIDAR."] if structural_front
                else [
        f"{module_id}/{drawer_id}: frente decorativo sin uniones, tiradores, "
        "cantos finales ni validación de montaje."
    ])
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
        if (type(request) is not dict
                or not DRAWER_FIELDS.issubset(request)
                or set(request) - DRAWER_FIELDS - {"front_construction"}):
            raise DesignError(f"{module_id}.drawers[{index}]: campos faltantes o desconocidos.")
        front_mode = request.get("front_construction", "separate")
        if front_mode not in FRONT_CONSTRUCTIONS:
            raise DesignError(f"{module_id}/{index}: modo de frente inválido.")
        integrated_front = front_mode == "integrated_overlay"
        if integrated_front and (request["front_setback_mm"] != 0
                or request["facade"] == "pending"
                or not isinstance(request["facade"], dict)
                or request["facade"].get("style") != "overlay"):
            raise DesignError(f"{module_id}/{index}: frente único incompatible.")
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
            if integrated_front and role == "drawer_front_wall":
                continue  # Frente exterior único sustituye a la pared frontal interior.
            all_parts.append(_part(module_id, drawer_id, role, mat,
                                   fx, fy, thick, plane, origin, formula))
        fronts, front_blockers = _facade(
            request["facade"], module_id=module_id, drawer_id=drawer_id,
            aperture_width=clear_width_mm, aperture_height=aperture_h,
            opening_y=y, opening_x=start_x_mm + carcase_thickness_mm,
            front_setback=z,
            carcase_thickness=carcase_thickness_mm,
            module_height=clear_height_mm + 2 * carcase_thickness_mm,
            structural_front=integrated_front,
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
    heights = _apportion_nominal(space, weights)
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
SUPPORT_LABELS = {
    "floor_direct": "sin patas (al piso)", "legs": "patas",
    "plinth": "zócalo/banqueo", "wall_mounted": "suspendido",
}
WALL_LABELS = {
    "pending": "fijación por decidir", "none": "sin fijación",
    "french_cleat": "listón francés", "direct_fasteners": "fijación directa",
    "rail_hangers": "riel con colgadores",
}
BACK_LABELS = {
    "pending": "por decidir", "none": "sin fondo",
    "thin_sheet": "lámina delgada", "full_panel": "fondo completo",
    "two_strips": "dos franjas",
}



def _sketch_mm(value: int | None) -> str:
    return "por definir" if value is None else f"{value} mm"


def _annotated_openings(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(chr(65 + i), item)
            for i, item in enumerate(reversed(plan["opening_plan"]))]


def _side_panel_height(plan: dict[str, Any]) -> int:
    outer = plan["external_dimensions_mm"]["height"]
    t = plan["panel_thickness_mm"]
    return outer if plan["construction"] == "sides_full" else outer - 2 * t


def _panel_review_dimensions(plan: dict[str, Any], name: str) -> dict[str, Any]:
    outer = plan["external_dimensions_mm"]
    t = plan["panel_thickness_mm"]
    nominal_w = outer["width"] - 2 * t if plan["construction"] == "sides_full" else outer["width"]
    return {
        "nominal_width_mm": nominal_w,
        "nominal_depth_mm": outer["depth"],
        "nominal_thickness_mm": t,
        "concept_overhang_left_mm": plan.get(f"{name}_overhang_left_mm", 0),
        "concept_overhang_right_mm": plan.get(f"{name}_overhang_right_mm", 0),
        "concept_overhang_front_mm": plan.get(f"{name}_overhang_front_mm", 0),
        "concept_overhang_rear_mm": plan.get(f"{name}_overhang_rear_mm", 0),
        "concept_outer_width_mm": outer["width"] + (
            plan.get(f"{name}_overhang_left_mm", 0) +
            plan.get(f"{name}_overhang_right_mm", 0)
        ),
        "concept_outer_depth_mm": outer["depth"] + (
            plan.get(f"{name}_overhang_front_mm", 0) +
            plan.get(f"{name}_overhang_rear_mm", 0)
        ),
        "extension_not_modeled_in_F1": any(
            plan.get(f"{name}_overhang_{side}_mm", 0) > 0
            for side in ("left", "right", "front", "rear")
        ),
    }


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
         **_panel_review_dimensions(plan, "top")},
        {"ref": "BS", "kind": "bottom_panel",
         **_panel_review_dimensions(plan, "bottom")},
        {"ref": "LI", "kind": "left_side",
         "nominal_height_mm": _side_panel_height(plan),
         "nominal_depth_mm": plan["external_dimensions_mm"]["depth"],
         "nominal_thickness_mm": plan["panel_thickness_mm"]},
        {"ref": "LD", "kind": "right_side",
         "nominal_height_mm": _side_panel_height(plan),
         "nominal_depth_mm": plan["external_dimensions_mm"]["depth"],
         "nominal_thickness_mm": plan["panel_thickness_mm"]},
        {"ref": "AP", "kind": "floor_support",
         "style": plan.get("support_style", "floor_direct"),
         "concept_height_mm": plan.get("support_height_mm", 0)},
        {"ref": "FP", "kind": "rear_back",
         "style": plan.get("back_style", "pending"),
         "concept_thickness_mm": plan.get("back_thickness_mm")},
        {"ref": "MF", "kind": "wall_interface",
         "against_wall": plan.get("wall_contact", False),
         "fixing": plan.get("wall_fixing", "pending")},
    ]


def _large_drawer_label(plan: dict[str, Any]) -> str | None:
    """Drawer identity follows the user's original request, never its new rank."""
    if plan.get("large_drawer_ref"):
        return plan["large_drawer_ref"]
    weights = plan["drawer_weights"]
    if max(weights) == min(weights) or weights.count(max(weights)) != 1:
        return None
    return chr(65 + len(weights) - 1 - weights.index(max(weights)))


def drawer_layout_sketch_text(plan: dict[str, Any]) -> str:
    dims = plan["external_dimensions_mm"]
    elements = _guide_ref_map(plan)
    large = _large_drawer_label(plan)
    rows = [
        "BOCETO FRONTAL Y LATERAL · SOLO PROPUESTA, NO CORTAR",
        f"Carcasa nominal: ancho {dims['width']}, alto {dims['height']}, "
        f"fondo {dims['depth']} mm.",
        "Tablero y separaciones son supuestos provisionales.",
        ("Construcción propuesta SIN aprobar: tapa y base cubren laterales."
         if plan["construction"] == "top_bottom_full"
         else "Construcción propuesta SIN aprobar: tapa y base entre laterales."),
        "La vista de costado representa LD; LI queda al lado opuesto.",
        "Arriba hacia abajo:",
    ]
    for part in elements:
        if part["kind"] == "drawer":
            kind = "gaveta solicitada" if part["ref"] == large else "cajón"
            rows.append(
                f"{part['ref']} ({part['engine_id']}): {kind}, abertura "
                f"{part['nominal_opening_height_mm']} mm, "
                f"{CHOICE_LABELS[part['opening_system_intent']]}."
            )
    for part in elements:
        if part["ref"] in ("T", "BS"):
            name = "tapa superior" if part["ref"] == "T" else "base inferior"
            rows.append(
                f"{part['ref']} = {name}: panel nominal "
                f"{part['nominal_width_mm']} × {part['nominal_depth_mm']} "
                f"× {part['nominal_thickness_mm']} mm (ancho × fondo × espesor); "
                f"concepto exterior {part['concept_outer_width_mm']} × "
                f"{part['concept_outer_depth_mm']} mm; salientes izquierda "
                f"{part['concept_overhang_left_mm']}, derecha "
                f"{part['concept_overhang_right_mm']}, frente "
                f"{part['concept_overhang_front_mm']}, atrás "
                f"{part['concept_overhang_rear_mm']} mm."
            )
        elif part["ref"] in ("LI", "LD"):
            rows.append(
                f"{part['ref']} = lateral "
                f"{'izquierdo' if part['ref'] == 'LI' else 'derecho'}: "
                f"{part['nominal_height_mm']} × {part['nominal_depth_mm']} "
                f"× {part['nominal_thickness_mm']} mm "
                "(alto × fondo × espesor)."
            )
    rows.extend([
        f"AP: {SUPPORT_LABELS[plan.get('support_style', 'floor_direct')]}; "
        f"altura {_sketch_mm(plan.get('support_height_mm', 0))}; "
        f"{'APOYO SIN CONFIRMAR; ' if plan.get('support_style_is_suggestion') else ''}"
        f"alto total {_sketch_mm(plan.get('overall_height_mm', dims['height']))}.",
        f"MF: {WALL_LABELS[plan.get('wall_fixing', 'pending')]}, "
        f"muro {'sí' if plan.get('wall_contact', False) else 'no'}; "
        f"elevación {_sketch_mm(plan.get('wall_bottom_above_floor_mm', 0))}.",
        f"FP: {BACK_LABELS[plan.get('back_style', 'pending')]}; "
        f"espesor {_sketch_mm(plan.get('back_thickness_mm'))}.",
        f"Franjas geométricas internas: {plan['vertical_gap_mm']} mm; "
        "no son divisores ni luces visibles de fachada.",
        "T y BS con salientes: SOLO IDEAS. Los paneles reales F1 siguen "
        "sin esos voladizos; ni materiales ni apoyos certificados.",
        "NO CORTAR, TALADRAR NI COMPRAR.",
    ])
    return "\n".join(rows)


def drawer_layout_sketch_svg(plan: dict[str, Any]) -> str:
    """Front + profile drawing from ONE F1 plan. Review-only, never cutting CAD."""
    dims = plan["external_dimensions_mm"]
    width, height, depth = dims["width"], dims["height"], dims["depth"]
    t = plan["panel_thickness_mm"]
    overall = plan.get("overall_height_mm", height)
    support_h = plan.get("support_height_mm", 0)
    style = plan.get("support_style", "floor_direct")
    top_panel = _panel_review_dimensions(plan, "top")
    bottom_panel = _panel_review_dimensions(plan, "bottom")
    panels = (top_panel, bottom_panel)
    left_ext = max(x["concept_overhang_left_mm"] for x in panels)
    right_ext = max(x["concept_overhang_right_mm"] for x in panels)
    front_ext = max(x["concept_overhang_front_mm"] for x in panels)
    rear_ext = max(x["concept_overhang_rear_mm"] for x in panels)
    fs = min(260 / (width + left_ext + right_ext), 366 / overall)
    ss = min(235 / (depth + front_ext + rear_ext), 366 / overall)
    fx, fy = 175 + left_ext * fs, 151
    fw, fh, ft = width * fs, height * fs, t * fs
    sx, sy = 795 + front_ext * ss, 151
    sw, sh, st = depth * ss, height * ss, t * ss
    int_x, int_y = fx + ft, fy + ft
    int_w = fw - 2 * ft
    large_ref = _large_drawer_label(plan)
    if plan.get("wall_contact"):
        wall_text = (f'MF: {WALL_LABELS[plan.get("wall_fixing", "pending")]}; '
                     f'elevación {_sketch_mm(plan.get("wall_bottom_above_floor_mm"))}; '
                     f'FP · {BACK_LABELS[plan.get("back_style", "pending")]}')
    else:
        wall_text = ('MF: sin muro solicitado; apoyo/instalación por revisar; FP · '
                     f'{BACK_LABELS[plan.get("back_style", "pending")]}')
    shapes: list[str] = []

    # Both joint patterns follow F1. Orange dotted panels are UNVALIDATED ideas.
    if plan["construction"] == "sides_full":
        shapes.extend([
            f'<rect x="{fx:.2f}" y="{fy:.2f}" width="{ft:.2f}" '
            f'height="{fh:.2f}" class="panel-side" '
            'data-view="front" data-ref="LI"/>',
            f'<rect x="{fx+fw-ft:.2f}" y="{fy:.2f}" width="{ft:.2f}" '
            f'height="{fh:.2f}" class="panel-side" '
            'data-view="front" data-ref="LD"/>',
            f'<rect x="{fx+ft:.2f}" y="{fy:.2f}" width="{int_w:.2f}" '
            f'height="{ft:.2f}" class="panel-actual" '
            'data-view="front" data-ref="T"/>',
            f'<rect x="{fx+ft:.2f}" y="{fy+fh-ft:.2f}" '
            f'width="{int_w:.2f}" height="{ft:.2f}" '
            'class="panel-actual" data-view="front" data-ref="BS"/>',
        ])
    else:
        shapes.extend([
            f'<rect x="{fx:.2f}" y="{fy:.2f}" width="{fw:.2f}" '
            f'height="{ft:.2f}" class="panel-actual" '
            'data-view="front" data-ref="T"/>',
            f'<rect x="{fx:.2f}" y="{fy+fh-ft:.2f}" width="{fw:.2f}" '
            f'height="{ft:.2f}" class="panel-actual" '
            'data-view="front" data-ref="BS"/>',
            f'<rect x="{fx:.2f}" y="{fy+ft:.2f}" width="{ft:.2f}" '
            f'height="{fh-2*ft:.2f}" class="panel-side" '
            'data-view="front" data-ref="LI"/>',
            f'<rect x="{fx+fw-ft:.2f}" y="{fy+ft:.2f}" width="{ft:.2f}" '
            f'height="{fh-2*ft:.2f}" class="panel-side" '
            'data-view="front" data-ref="LD"/>',
        ])
    for label, opening in _annotated_openings(plan):
        y = int_y + (plan["clear_height_mm"] -
                     opening["opening_bottom_offset_mm"] -
                     opening["opening_height_mm"]) * fs
        ph = opening["opening_height_mm"] * fs
        is_large = label == large_ref
        kind = "GAVETA" if is_large else "CAJÓN"
        choice = plan.get("opening_systems", {}).get(label, "pending")
        shapes.extend([
            f'<rect x="{int_x:.2f}" y="{y:.2f}" width="{int_w:.2f}" '
            f'height="{ph:.2f}" class="{"drawer-large" if is_large else "drawer"}"/>',
            f'<text x="{int_x+10:.2f}" y="{y+ph/2+6:.2f}" '
            f'class="ref">{label}</text>',
            f'<path d="M {int_x+int_w:.2f} {y+ph/2:.2f} L 486 {y+ph/2:.2f}" '
            'class="leader"/>',
            f'<text x="499" y="{y+ph/2-3:.2f}" class="dimension">'
            f'{label} · {kind} {opening["opening_height_mm"]} mm</text>',
            f'<text x="499" y="{y+ph/2+16:.2f}" class="small">'
            f'Apertura: {CHOICE_LABELS[choice]}</text>',
        ])
        cx = int_x + int_w / 2
        if choice == "handle":
            shapes.append(f'<line x1="{cx-11:.2f}" y1="{y+ph/2+6:.2f}" '
                          f'x2="{cx+11:.2f}" y2="{y+ph/2+6:.2f}" '
                          'stroke="#506379" stroke-width="3"/>')
        elif choice == "finger_pull":
            shapes.append(f'<path d="M {cx-9:.2f} {y+4:.2f} '
                          f'Q {cx:.2f} {y+15:.2f} {cx+9:.2f} {y+4:.2f}" '
                          'fill="none" stroke="#506379" stroke-width="2"/>')
        elif choice == "profile":
            shapes.append(f'<line x1="{int_x+3:.2f}" y1="{y+5:.2f}" '
                          f'x2="{int_x+int_w-3:.2f}" y2="{y+5:.2f}" '
                          'stroke="#506379" stroke-width="3"/>')
        elif choice == "push_to_open":
            shapes.append(f'<text x="{cx:.2f}" y="{y+ph/2+7:.2f}" '
                          'class="small" text-anchor="middle">PUSH</text>')
    # Display the calculation-only spans between nominal F1 openings.
    # These rectangles represent NO boards, facade joints, or cutting data.
    openings_top_down = _annotated_openings(plan)
    for (_, upper), (_, lower) in zip(openings_top_down, openings_top_down[1:]):
        lower_edge = (int_y + (plan["clear_height_mm"] -
                      upper["opening_bottom_offset_mm"]) * fs)
        next_top = (int_y + (plan["clear_height_mm"] -
                    lower["opening_bottom_offset_mm"] -
                    lower["opening_height_mm"]) * fs)
        gap_px = next_top - lower_edge
        if gap_px > 0:
            shapes.append(
                f'<rect x="{int_x:.2f}" y="{lower_edge:.2f}" '
                f'width="{int_w:.2f}" height="{gap_px:.2f}" '
                'class="calculation-gap" data-concept="calculation-only"/>'
            )
    shapes.append(f'<text x="{fx-20:.2f}" y="{fy+35:.2f}" '
                  'class="ref" text-anchor="end">LI</text>')
    shapes.append(f'<text x="{fx+fw+8:.2f}" y="{fy+fh-25:.2f}" '
                  'class="ref">LD</text>')
    shapes.append(f'<text x="{fx+fw/2:.2f}" y="{fy-17:.2f}" '
                  'class="dimension" text-anchor="middle">T · superior</text>')
    shapes.append(f'<text x="{fx+fw/2:.2f}" y="{fy+fh+19:.2f}" '
                  'class="dimension" text-anchor="middle">BS · inferior</text>')
    # The lateral view uses THE SAME F1 joints as the front view.
    # sides_full hides inset T/BS behind full-height side LD; they cannot
    # appear on top/bottom of that side. Dashed hidden lines != overhang.
    if plan["construction"] == "top_bottom_full":
        shapes.extend([
            f'<rect x="{sx:.2f}" y="{sy+st:.2f}" width="{sw:.2f}" '
            f'height="{sh-2*st:.2f}" class="panel-side" '
            'data-view="side" data-ref="LD"/>',
            f'<rect x="{sx:.2f}" y="{sy:.2f}" width="{sw:.2f}" '
            f'height="{st:.2f}" class="panel-actual" '
            'data-view="side" data-ref="T"/>',
            f'<rect x="{sx:.2f}" y="{sy+sh-st:.2f}" width="{sw:.2f}" '
            f'height="{st:.2f}" class="panel-actual" '
            'data-view="side" data-ref="BS"/>',
        ])
    else:
        shapes.extend([
            f'<rect x="{sx:.2f}" y="{sy:.2f}" width="{sw:.2f}" '
            f'height="{sh:.2f}" class="panel-side" '
            'data-view="side" data-ref="LD"/>',
            f'<path d="M {sx:.2f} {sy+st:.2f} H {sx+sw:.2f} '
            f'M {sx:.2f} {sy+sh-st:.2f} H {sx+sw:.2f}" '
            'class="hidden-panel" data-view="side" '
            'data-ref="T-BS-hidden"/>',
        ])
    shapes.extend([
        f'<text x="{sx+sw/2:.2f}" y="{sy-17:.2f}" '
        'class="dimension" text-anchor="middle">'
        'LD · costado derecho (LI opuesto)</text>',
        f'<text x="{sx-12:.2f}" y="{sy+15:.2f}" '
        'class="small" text-anchor="end">T · tapa superior</text>',
        f'<text x="{sx-12:.2f}" y="{sy+sh-7:.2f}" '
        'class="small" text-anchor="end">BS · base inferior</text>',
        f'<text x="{sx+sw/2:.2f}" y="{sy+sh/2:.2f}" '
        'class="small" text-anchor="middle">LD · lateral</text>',
        f'<text x="{sx+sw/2:.2f}" y="{sy+sh+19:.2f}" '
        f'class="small" text-anchor="middle">FRENTE ← {depth} mm → FONDO</text>',
    ])
    for ref, name, panel in (("T", "top", top_panel), ("BS", "bottom", bottom_panel)):
        yy = fy if ref == "T" else fy+fh-ft
        yy2 = sy if ref == "T" else sy+sh-st
        if panel["extension_not_modeled_in_F1"]:
            le, ri = panel["concept_overhang_left_mm"], panel["concept_overhang_right_mm"]
            fr, re = panel["concept_overhang_front_mm"], panel["concept_overhang_rear_mm"]
            shapes.extend([
                f'<rect x="{fx-le*fs:.2f}" y="{yy:.2f}" '
                f'width="{(width+le+ri)*fs:.2f}" height="{ft:.2f}" '
                'class="concept"/>',
                f'<rect x="{sx-fr*ss:.2f}" y="{yy2:.2f}" '
                f'width="{(depth+fr+re)*ss:.2f}" height="{st:.2f}" '
                'class="concept"/>',
            ])
            # Place the label inside the profile, away from nominal joint lines.
            front = panel["concept_overhang_front_mm"]
            rear = panel["concept_overhang_rear_mm"]
            if front or rear:
                placement = "frente" if front else "atrás"
                amount = front or rear
                label_y = sy + (st + 45 if ref == "T" else sh - st - 40)
                shapes.append(
                    f'<text x="{sx+12:.2f}" y="{label_y:.2f}" class="overhang-label">'
                    f'{ref} +{amount} mm {placement} · idea</text>'
                )
    if style in ("legs", "plinth"):
        bottom = fy+fh
        sup = support_h * fs
        if style == "legs":
            for x in (fx+11, fx+fw-25):
                shapes.append(f'<rect x="{x:.2f}" y="{bottom:.2f}" '
                              f'width="14" height="{sup:.2f}" class="support"/>')
        else:
            shapes.append(f'<rect x="{fx+9:.2f}" y="{bottom:.2f}" '
                          f'width="{fw-18:.2f}" height="{sup:.2f}" class="support"/>')
    elif style == "wall_mounted":
        shapes.append(f'<line x1="{sx+sw+8:.2f}" y1="{sy:.2f}" '
                      f'x2="{sx+sw+8:.2f}" y2="{sy+sh:.2f}" '
                      'stroke="#a6755a" stroke-width="3" stroke-dasharray="5 4"/>')
    for x, label, info in (
        (35, "T · TAPA SUPERIOR", top_panel),
        (410, "BS · BASE INFERIOR", bottom_panel),
    ):
        outer_str = f'{info["concept_outer_width_mm"]} × {info["concept_outer_depth_mm"]} mm'
        outer_label = (
            f"Idea exterior: {outer_str}"
            if info["extension_not_modeled_in_F1"]
            else f"Sin salientes: carcasa {width} × {depth} mm"
        )
        shapes.extend([
            f'<rect x="{x}" y="624" width="362" height="103" rx="10" '
            'fill="#f7f9fb" stroke="#cad4df"/>',
            f'<text x="{x+15}" y="649" class="card-title">{label}</text>',
            f'<text x="{x+15}" y="671" class="small">'
            f'Nominal: {info["nominal_width_mm"]} × {depth} × {t} mm</text>',
            f'<text x="{x+15}" y="691" class="small">'
            f'{outer_label}</text>',
            f'<text x="{x+15}" y="711" class="note">'
            f'Izq. {info["concept_overhang_left_mm"]} / '
            f'der. {info["concept_overhang_right_mm"]} · '
            f'frente {info["concept_overhang_front_mm"]} / '
            f'atrás {info["concept_overhang_rear_mm"]} mm</text>',
        ])
    shapes.extend([
        '<rect x="785" y="624" width="350" height="103" rx="10" '
        'fill="#f7f9fb" stroke="#cad4df"/>',
        '<text x="801" y="649" class="card-title">LI / LD · LATERALES</text>',
        f'<text x="801" y="674" class="small">'
        f'{_side_panel_height(plan)} × {depth} × {t} mm c/u</text>',
        '<text x="801" y="698" class="small">'
        'Alto × fondo × espesor (nominal F1)</text>',
        f'<text x="801" y="715" class="note">'
        f'Carcasa: ancho {width}, alto {height}, fondo {depth} mm</text>',
        '<text x="35" y="764" class="card-title">Opciones del mueble</text>',
        f'<text x="35" y="788" class="small">'
        f'AP · {SUPPORT_LABELS[style]} · {support_h} mm '
        f'{"(sugeridos) " if plan.get("support_height_is_suggestion") else ""}'
        f'· ALTO {overall} mm</text>',
        f'<text x="35" y="810" class="small">'
        f'{wall_text}</text>',
        f'<text x="35" y="835" class="small">'
        f'Franjas grises {plan["vertical_gap_mm"]} mm = ESPACIOS DE CÁLCULO; NO son tablones ni juntas de frentes.</text>',
        f'<text x="35" y="865" class="small">'
        f'Envolvente ilustrativa: {plan.get("concept_envelope", {}).get("width_mm", width)} '
        f'× {plan.get("concept_envelope", {}).get("depth_mm", depth)} mm en planta.</text>',
        '<text x="35" y="898" class="card-title">'
        'Opciones de apertura (símbolos ilustrativos)</text>',
        '<g stroke="#8799ac" fill="none" stroke-width="1.5">'
        '<rect x="35" y="914" width="267" height="89" rx="11"/>'
        '<rect x="310" y="914" width="267" height="89" rx="11"/>'
        '<rect x="585" y="914" width="267" height="89" rx="11"/>'
        '<rect x="860" y="914" width="267" height="89" rx="11"/>'
        '<path d="M 123 952 L 211 952" stroke-width="4"/>'
        '<path d="M 401 943 Q 443 972 484 943"/>'
        '<path d="M 675 952 L 764 952 M 752 941 L 764 952 L 752 963"/>'
        '<path d="M 946 940 L 1043 940" stroke-width="5"/>'
        '</g>'
        '<text x="168" y="992" class="small" text-anchor="middle">Manija</text>'
        '<text x="443" y="992" class="small" text-anchor="middle">Uñero</text>'
        '<text x="718" y="992" class="small" text-anchor="middle">Presión</text>'
        '<text x="993" y="992" class="small" text-anchor="middle">Perfil</text>'
        # Footer legend is contextual: absent layers are not advertised.
    ])
    # Enlarge the original F1 join logic for an understandable, non-CAD view.
    cover = plan["construction"] == "top_bottom_full"
    if cover:
        joints = (
            '<rect x="78" y="1182" width="115" height="17" class="panel-actual" data-detail="joint-cover"/>'
            '<rect x="95" y="1199" width="17" height="64" class="panel-side" data-detail="joint-side"/>',
            '<rect x="632" y="1246" width="115" height="17" class="panel-actual" data-detail="joint-cover"/>'
            '<rect x="649" y="1182" width="17" height="64" class="panel-side" data-detail="joint-side"/>',
        )
    else:
        joints = (
            '<rect x="78" y="1182" width="17" height="81" class="panel-side" data-detail="joint-side"/>'
            '<rect x="95" y="1199" width="98" height="17" class="panel-actual" data-detail="joint-inset"/>',
            '<rect x="632" y="1182" width="17" height="81" class="panel-side" data-detail="joint-side"/>'
            '<rect x="649" y="1229" width="98" height="17" class="panel-actual" data-detail="joint-inset"/>',
        )
    top_rear = (plan.get("top_overhang_front_mm", 0) +
                plan.get("top_overhang_rear_mm", 0))
    bottom_rear = (plan.get("bottom_overhang_front_mm", 0) +
                   plan.get("bottom_overhang_rear_mm", 0))
    extensions = top_panel["extension_not_modeled_in_F1"] or bottom_panel["extension_not_modeled_in_F1"]
    if top_rear or bottom_rear:
        detail_note = (
            f'Salientes SOLO ilustrativos: T +{top_rear} mm · BS +{bottom_rear} mm; '
            f'fondo máximo {plan.get("concept_envelope", {}).get("depth_mm", depth)} mm, no suma.'
        )
    elif extensions:
        detail_note = (
            'Salientes laterales SOLO ilustrativos; '
            f'ancho exterior máximo {plan.get("concept_envelope", {}).get("width_mm", width)} mm. '
            'No son piezas aprobadas.'
        )
    else:
        detail_note = (
            f'Tableros de {t} mm y franjas de {plan["vertical_gap_mm"]} mm: SUPUESTOS sin aprobar.'
        )
    n = len(plan["opening_plan"])
    construction_label = ("T y BS cubren los laterales" if cover else "T y BS entre los laterales")
    visual_summary = (f'{construction_label}. Las uniones se muestran ampliadas; '
                      'las franjas grises son espacios de cálculo y no tableros. '
                      + ('Los salientes punteados no son fabricables.' if extensions
                         else 'No se solicitaron salientes.'))
    footer_warning = (
        ('<text x="35" y="1291" class="warning">'
         + ('NARANJA PUNTEADA = SALIENTE SIN VALIDAR.' if cover else
            'NARANJA PUNTEADA = SALIENTE SIN VALIDAR; OCRE PUNTEADO INTERIOR = T/BS OCULTAS.')
         + '</text>') if extensions else
        ('<text x="35" y="1291" class="warning">OCRE PUNTEADO INTERIOR = T/BS OCULTAS.</text>'
         if not cover else '')
    )
    revisions = plan.get("revisions", [])
    revision_items = [
        (f'{r["ref"]}: {r["before_mm"]} → {r["after_mm"]} mm '
         f'({"solicitado" if r["cause"] == "USER_REQUESTED" else "redistribuido"})')
        for r in revisions
    ]
    if revision_items:
        note_line = (
            '<text x="49" y="1082" class="small">CAMBIOS DESDE LA PROPUESTA: '
            + ' · '.join(revision_items[:2]) + '</text>'
            + ('<text x="49" y="1104" class="small">'
               + ' · '.join(revision_items[2:]) + '</text>'
               if len(revision_items) > 2 else '')
        )
    else:
        note_line = (
            '<text x="49" y="1082" class="small">Los detalles muestran la unión superior e inferior '
            'de la MISMA construcción F1; ninguna unión está aprobada.</text>'
        )
    joint_detail = (
        note_line
        + f'<text x="49" y="1125" class="{"overhang-label" if extensions else "note"}">{detail_note}</text>'
        '<text x="78" y="1163" class="card-title">UNIÓN SUPERIOR · T / lateral</text>'
        + joints[0] +
        '<text x="215" y="1206" class="small">'
        + ('T cubre el lateral' if cover else 'El lateral cubre T')
        + f' ({t} mm supuesto)</text>'
        '<text x="215" y="1231" class="note">Detalle ampliado · unión nominal</text>'
        '<text x="632" y="1163" class="card-title">UNIÓN INFERIOR · BS / lateral</text>'
        + joints[1] +
        '<text x="769" y="1206" class="small">'
        + ('BS cubre el lateral' if cover else 'El lateral cubre BS')
        + f' ({t} mm supuesto)</text>'
        '<text x="769" y="1231" class="note">Detalle ampliado · unión nominal</text>'
        + footer_warning +
        '<text x="35" y="1313" class="warning">NO CORTAR, TALADRAR NI COMPRAR.</text>'
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1160" height="1325" '
        'viewBox="0 0 1160 1325" role="img" '
        f'aria-label="Boceto de frente y lateral: aberturas A-{chr(64+n)}, tapa T, base BS, '
        'laterales LI LD y cotas para revisión">'
        f'<title>Gabinete con aberturas A-{chr(64+n)}, frente y costado</title>'
        f'<desc>{visual_summary}</desc>'
        '<style>text{font-family:Arial,sans-serif;fill:#26394d}'
        '.title{font-size:24px;font-weight:700}'
        '.subtitle{font-size:16px;fill:#5a6b7d}'
        '.ref{font-size:20px;font-weight:bold}'
        '.dimension{font-size:15px}.small{font-size:14px}'
        '.note{font-size:12px;fill:#526579}'
        '.card-title{font-size:17px;font-weight:700}'
        '.warning{font-size:14px;font-weight:700;fill:#89542b}'
        '.panel-actual{fill:#f0cc8f;stroke:#926f42;stroke-width:1.5}'
        '.panel-side{fill:#a9bfcd;stroke:#45617a;stroke-width:1.5}'
        '.drawer{fill:#e7edf5;stroke:#69829b;stroke-width:1.25}'
        '.drawer-large{fill:#d4e9e5;stroke:#538c82;stroke-width:1.5}'
        '.support{fill:#dfc2a0;stroke:#927257;stroke-width:1.5}'
        '.calculation-gap{fill:#f4f6f8;stroke:#a8b3bd;stroke-width:.8;stroke-dasharray:3 3}'
        '.overhang-label{font-size:14px;fill:#9a5b14;font-weight:700}'
        '.hidden-panel{fill:none;stroke:#926f42;stroke-width:1.7;'
        'stroke-dasharray:5 3}'
        '.concept{fill:#efc578;fill-opacity:.23;stroke:#c18025;'
        'stroke-width:2.5;stroke-dasharray:6 4}'
        '.leader{stroke:#94a7b7;stroke-width:1.3;stroke-dasharray:4 4}'
        '</style><rect width="1160" height="1325" rx="18" fill="#ffffff"/>'
        '<text x="35" y="43" class="title">Tu mueble, explicado por partes</text>'
        '<text x="35" y="70" class="subtitle">Puedes decir: “A más alto”, '
        '“T sobresale 5 cm” o “BS más ancha”.</text>'
        '<text x="35" y="92" class="note">'
        f'PROPUESTA: {"T y BS cubren los laterales" if plan["construction"] == "top_bottom_full" else "T y BS entre los laterales"}; '
        'espesores y franjas ilustrativos. No aprobado para taller.</text>'
        '<text x="175" y="120" class="card-title">FRENTE · aberturas nominales</text>'
        '<text x="800" y="120" class="card-title">VISTA LATERAL · COSTADO</text>'
        + "".join(shapes) + joint_detail + '</svg>'
    )


DRAWER_GUIDE_FIELDS = frozenset({
    "type", "width_mm", "height_mm", "depth_mm", "small_drawers",
    "construction",
    "large_drawer_position", "drawer_adjustments_mm",
    "top_overhang_left_mm", "top_overhang_right_mm",
    "top_overhang_front_mm", "top_overhang_rear_mm",
    "bottom_overhang_left_mm", "bottom_overhang_right_mm",
    "bottom_overhang_front_mm", "bottom_overhang_rear_mm",
    "opening_systems",
    "support_style", "support_height_mm", "wall_contact", "wall_fixing",
    "wall_bottom_above_floor_mm", "back_style", "back_thickness_mm",
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
    # Suggest T/BS over the sides on the initial drawing; both choices are F1.
    construction = spec.get("construction", "top_bottom_full")
    if type(construction) is not str or construction not in (
        "top_bottom_full", "sides_full"
    ):
        raise DesignError(
            "Construcción: tapa y base cubren laterales (top_bottom_full) "
            "o laterales continuos (sides_full)."
        )
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
    extensions = {
        (panel, side): spec.get(f"{panel}_overhang_{side}_mm", 0)
        for panel in ("top", "bottom")
        for side in ("left", "right", "front", "rear")
    }
    if any(type(value) is not int or not 0 <= value <= 200
           for value in extensions.values()):
        raise DesignError(
            "Saliente T/BS: indicar entre 0 y 200 mm enteros por lado "
            "(izquierda, derecha, frente, fondo); solo concepto."
        )
    left, right = extensions["top", "left"], extensions["top", "right"]
    bottom_left = extensions["bottom", "left"]
    bottom_right = extensions["bottom", "right"]
    outer_width = spec["width_mm"] + max(left, bottom_left) + max(right, bottom_right)
    outer_depth = spec["depth_mm"] + max(
        extensions["top", "front"], extensions["bottom", "front"]
    ) + max(extensions["top", "rear"], extensions["bottom", "rear"])
    # A floor-standing drawing is a provisional visual baseline, not an
    # owner-confirmed decision to omit legs or a plinth.
    support_style_is_suggestion = "support_style" not in spec
    support_style = spec.get("support_style", "floor_direct")
    if support_style not in ("floor_direct", "legs", "plinth", "wall_mounted"):
        raise DesignError(
            "Apoyo: piso, patas, zócalo/banqueo o suspendido contra pared."
        )
    support_height_suggested = (
        "support_height_mm" not in spec
        and support_style in ("legs", "plinth")
    )
    sh = spec.get("support_height_mm", 100 if support_height_suggested else 0)
    if (type(sh) is not int or sh < 0
            or (support_style in ("legs", "plinth") and sh == 0)
            or (support_style in ("floor_direct", "wall_mounted") and sh != 0)):
        raise DesignError("Patas/zócalo: altura positiva; "
                          "sin soporte o suspendido usa 0 mm.")
    overall_h = spec["height_mm"]
    if type(overall_h) is not int or overall_h - sh <= 36:
        raise DesignError("El apoyo deja una carcasa sin altura suficiente.")
    wall_contact = spec.get("wall_contact", support_style == "wall_mounted")
    if type(wall_contact) is not bool or (support_style == "wall_mounted"
                                          and not wall_contact):
        raise DesignError("Un suspendido necesita muro declarado.")
    wall_fixing = spec.get("wall_fixing", "pending")
    if wall_fixing not in ("pending", "french_cleat", "direct_fasteners",
                           "rail_hangers", "none"):
        raise DesignError("Muro: listón francés, fijación directa, "
                          "riel, pendiente o ninguna.")
    if ((not wall_contact and wall_fixing not in ("pending", "none"))
            or (support_style == "wall_mounted" and wall_fixing == "none")):
        raise DesignError("No se especifica fijación sin muro "
                          "ni se deja un suspendido sin fijación.")
    wall_h = spec.get(
        "wall_bottom_above_floor_mm",
        None if support_style == "wall_mounted" else 0
    )
    if ((wall_h is not None and (type(wall_h) is not int or wall_h < 0))
            or (support_style != "wall_mounted" and wall_h != 0)):
        raise DesignError("Altura sobre piso es exclusiva del suspendido.")
    back_style = spec.get("back_style", "pending")
    if back_style not in ("pending", "none", "thin_sheet", "full_panel",
                          "two_strips"):
        raise DesignError("Fondo posterior: pendiente, ninguno, lámina fina, "
                          "panel completo o dos franjas.")
    back_t = spec.get("back_thickness_mm")
    if back_t is not None and (type(back_t) is not int
                              or not 1 <= back_t <= 50):
        raise DesignError("Espesor del fondo posterior inválido.")
    if back_style in ("none", "pending") and back_t is not None:
        raise DesignError("Un fondo inexistente/pendiente no tiene espesor.")
    if back_style == "thin_sheet" and back_t is None:
        back_t = 2  # illustrative only, not a structural assumption.
    weights = ([2] + [1] * n if position == "bottom"
               else [1] * n + [2])
    proposed = {
        "type": "drawer_layout_proposal",
        "width_mm": spec["width_mm"],
        "height_mm": overall_h - sh,
        "depth_mm": spec["depth_mm"],
        "panel_thickness_mm": 18,
        "construction": construction,
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
        "unvalidated_top_extension": any(extensions["top", side] for side in ("left", "right", "front", "rear")),
        "unvalidated_bottom_extension": any(extensions["bottom", side] for side in ("left", "right", "front", "rear")),
        **{f"{panel}_overhang_{side}_mm": extension
           for (panel, side), extension in extensions.items()},
        "concept_envelope": {
            "width_mm": outer_width, "depth_mm": outer_depth,
            "height_mm": overall_h,
            "exceeds_carcass_width_mm": outer_width - spec["width_mm"],
            "exceeds_carcass_depth_mm": outer_depth - spec["depth_mm"],
            "not_validated_for_manufacturing": True,
        },
        "large_drawer_ref": refs[0] if position == "top" else refs[-1],
        "construction_review": {
            "selected": construction,
            "is_user_confirmed": False,
            "alternatives": ["top_bottom_full", "sides_full"],
        },
        "revisions": revisions,
        "proposed_layout_spec": proposed,
        "review_state": dict(spec),
        "suggestions_not_confirmed": {
            "panel_thickness_mm": 18, "construction": construction,
            "vertical_gap_mm": 28, "drawer_weights": list(weights),
            "large_drawer_position": position,
            "support_style": support_style if support_style_is_suggestion else None,
            "support_height_mm": sh if support_height_suggested else None,
            "wall_fixing": wall_fixing if "wall_fixing" not in spec else None,
            "back_thickness_mm": back_t if back_style == "thin_sheet"
                and "back_thickness_mm" not in spec else None,
        },
        "can_generate_f7c": False,
        "overall_height_mm": overall_h,
        "carcass_height_mm": overall_h - sh,
        "support_style": support_style,
        "support_style_is_suggestion": support_style_is_suggestion,
        "support_height_mm": sh,
        "support_height_is_suggestion": support_height_suggested,
        "wall_contact": wall_contact,
        "wall_fixing": wall_fixing,
        "wall_bottom_above_floor_mm": wall_h,
        "back_style": back_style,
        "back_thickness_mm": back_t,
        "unvalidated_support": support_style in ("legs", "plinth", "wall_mounted"),
        "unvalidated_mounting": wall_contact,
        "unvalidated_back_panel": back_style not in ("none", "pending"),
    })
    result["element_refs"] = _guide_ref_map(result)
    result["sketch_text"] = drawer_layout_sketch_text(result)
    result["sketch_svg"] = drawer_layout_sketch_svg(result)
    result["human_summary"] = (
        f"Te propongo {n} cajones pequeños y una gaveta grande "
        + ("abajo" if position == "bottom" else "arriba")
        + ". Identifiqué A-D (arriba hacia abajo), T (tapa), BS (base), LI/LD "
          "(laterales). Puedes pedirme «A 10 cm más alto» o «T sobresale "
          "5 cm»; te mostraré cómo afecta a las demás piezas. "
          "El apoyo debe elegirse: piso sin patas, patas, zócalo o suspendido; "
          "si no se eligió, el piso del dibujo es solo una suposición. "
          "AP/MF/FP son partes identificadas solo para conversar. "
          "Los 18 mm de tablero y 28 mm de franjas internas son "
          "supuestos, no especificaciones."
    )
    result["blockers"].insert(
        0, "Boceto editable, NO plano de despiece: confirmar cada opción "
           "técnica antes de crear piezas, incluidos apoyos/muro/fondos."
    )
    if support_style_is_suggestion:
        result["blockers"].insert(
            1, "APOYO SIN CONFIRMAR: el boceto provisional muestra la carcasa al "
               "piso, pero elegir patas/zócalo cambia el alto de la carcasa y "
               "redistribuye TODOS los cajones. Preguntar antes del despiece."
        )
    if support_height_suggested:
        result["blockers"].insert(
            1, "Altura AP 100 mm es un ejemplo no solicitado; la persona "
               "debe decidir si quiere esa altura."
        )
    if support_style == "wall_mounted" and wall_h is None:
        result["blockers"].insert(
            1, "La altura inferior sobre el suelo NO se ha definido; "
               "no usar cero como altura de instalación."
        )
    if support_style in ("legs", "plinth", "wall_mounted"):
        result["blockers"].insert(
            1, "Apoyo AP solo visual: patas, banqueo y suspensión NO tienen "
               "piezas resistentes ni fijaciones modeladas en F1/F7C."
        )
    if wall_contact:
        result["blockers"].insert(
            1, "MF contra muro: no hay verificación de tipo de pared, cargas, "
               "listón francés, fijación directa ni rieles."
        )
    if back_style not in ("none", "pending"):
        result["blockers"].insert(
            1, "FP fondo posterior solo orientativo: confirmar material, "
               "espesor, acceso a instalaciones y fijación. Una lámina "
               "de 2 mm NO acredita arriostramiento estructural."
        )
    if revisions:
        result["blockers"].insert(
            1, "Las medidas modificadas redistribuyeron la altura de los "
               "cajones no fijados; revisar TODOS los cambios de revisions."
        )
    if result["unvalidated_top_extension"] or result["unvalidated_bottom_extension"]:
        result["blockers"].insert(
            1, "Salientes T/BS SOLO ilustrados: F1/F7C no modelan tapas "
               "ni bases sobresalientes; falta validar apoyos, uniones, "
               "rigidez y medidas exteriores antes de despiece CAD."
        )
        result["blockers"].insert(
            2, "Los salientes cambian la envolvente ilustrativa a "
               f'{outer_width} x {outer_depth} mm en planta; confirmar si '
               "el límite exterior admite el aumento."
        )
    return result
