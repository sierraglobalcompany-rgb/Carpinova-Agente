"""Wall-to-cabinet auxiliary bar: place validated F1/F7C parts only.

The left wall is NOT a wooden panel. Feet and anchors are concepts, not CAD parts.
All output is nominal review geometry, never a cut/drill/fabrication release.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .core import DesignError
from .modular import design_modular_run


def _positive(spec: Mapping[str, Any], name: str) -> int:
    n = spec.get(name)
    if type(n) is not int or n <= 0:
        raise DesignError(f"wall_bar.{name}: positivo entero en mm requerido.")
    return n


WALL_SUPPORT_CHOICES = frozenset(("installer_defined", "wood_cleat",
                                   "metal_l_brackets", "metal_support", "other_pending"))
TOP_EDGE_CHOICES = frozenset(("actual_15mm", "false_thickness_pending", "undecided"))
AESTHETIC_PRESENTATION_CHOICES = frozenset(("undecided", "bicolor_modern_preliminary"))


def design_wall_bar(spec: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"type", "overall_width_mm", "overall_height_mm",
              "overall_depth_mm", "free_span_mm", "feet_height_mm",
              "top_thickness_mm", "wall_side", "drawer_opening_face",
              "cabinet_module"}
    if (type(spec) is not dict or not fields.issubset(spec)
            or set(spec) - fields - {"design_choices"}
            or spec["type"] != "wall_bar"):
        raise DesignError("wall_bar: contrato exacto requerido.")
    choices = spec.get("design_choices", {})
    if (type(choices) is not dict
            or set(choices) - {"wall_support_presentation", "top_edge_presentation",
                               "aesthetic_presentation"}):
        raise DesignError("wall_bar.design_choices: opciones desconocidas.")
    wall_presentation = choices.get("wall_support_presentation", "installer_defined")
    edge_presentation = choices.get("top_edge_presentation", "actual_15mm")
    aesthetic_presentation = choices.get("aesthetic_presentation", "undecided")
    if (type(wall_presentation) is not str
            or wall_presentation not in WALL_SUPPORT_CHOICES
            or type(edge_presentation) is not str
            or edge_presentation not in TOP_EDGE_CHOICES
            or type(aesthetic_presentation) is not str
            or aesthetic_presentation not in AESTHETIC_PRESENTATION_CHOICES):
        raise DesignError("Opciones de presentación no reconocidas.")
    w = _positive(spec, "overall_width_mm")
    h = _positive(spec, "overall_height_mm")
    d = _positive(spec, "overall_depth_mm")
    free = _positive(spec, "free_span_mm")
    feet = _positive(spec, "feet_height_mm")
    top = _positive(spec, "top_thickness_mm")
    if spec["wall_side"] != "left":
        raise DesignError("Solo se modela la variante aprobada: muro a la izquierda.")
    if spec["drawer_opening_face"] != "long_side_front":
        raise DesignError("Orientación A confirmada: cajones al costado largo; no hacia la punta.")
    if w <= free or h <= feet + top or d <= top:
        raise DesignError("Dimensiones del conjunto incompatibles.")
    cabinet_w, cabinet_h, cabinet_d = w - free, h - feet - top, d - top
    module = spec["cabinet_module"]
    if type(module) is not dict or module.get("width_mm") != cabinet_w:
        raise DesignError("La cajonera debe ocupar exclusivamente el extremo derecho.")
    if module.get("panel_thickness_mm") != top:
        raise DesignError("Espesor cuerpo/cubierta debe ser el mismo y explícito.")
    if module.get("fronts") != "none" or module.get("support") != "floor":
        raise DesignError("No agregar puerta independiente ni apoyo mural a cajonera.")
    if module.get("support_concept") != {
        "style": "legs", "support_height_mm": feet,
        "overall_height_mm": feet + cabinet_h
    }:
        raise DesignError("Altura de soporte incompatible.")
    drawers = module.get("drawers")
    if type(drawers) is not list or len(drawers) != 3:
        raise DesignError("Se requieren tres cajones.")
    for drawer in drawers:
        if (type(drawer) is not dict
                or drawer.get("front_construction") != "separate"
                or not isinstance(drawer.get("facade"), dict)
                or drawer["facade"].get("style") != "overlay"
                or drawer.get("front_setback_mm") != 0):
            raise DesignError(
                "Cada cajón requiere caja completa y fachada overlay separada, "
                "con retranqueo nominal cero."
            )
        facade = drawer["facade"]
        if (facade.get("edgeband_thickness_mm") != 2
                or set(facade.get("edgebanding_edges", []))
                != {"x_min", "x_max", "y_min", "y_max"}):
            raise DesignError(
                "Los tres frentes requieren PVC rígido de 2 mm en los cuatro bordes."
            )
        # Keep the remaining structural checks below.
    inner = {
        "type": "modular_run", "application": "kitchen",
        "width_mm": cabinet_w, "height_mm": cabinet_h,
        "depth_mm": cabinet_d, "max_assembled_depth_mm": d,
        "installation": "freestanding", "modules": [deepcopy(module)]
    }
    source = design_modular_run(inner)
    if source["status"] != "DRAFT_NOT_FOR_CUTTING":
        raise DesignError("F1/F7C no aprobó geometría nominal del módulo.")
    if source["depth_review"]["assembled_external_depth_mm"] != d:
        raise DesignError("Profundidad terminada exterior no coincide.")
    source_ids = [p["piece_id"] for p in source["parts"]]
    if len(source_ids) != len(set(source_ids)):
        raise DesignError("IDs duplicados.")
    expected_drawer_roles = {
        "drawer_side_left", "drawer_side_right", "drawer_front_wall",
        "drawer_rear_wall", "drawer_bottom", "drawer_facade",
    }
    by_drawer: dict[str, set[str]] = {"D1": set(), "D2": set(), "D3": set()}
    for part in source["parts"]:
        if part["role"].startswith("drawer_"):
            did = part.get("drawer_id")
            if did not in by_drawer:
                raise DesignError("Pieza de cajón sin identidad D1/D2/D3.")
            by_drawer[did].add(part["role"])
    if (source["piece_count"] != 23
            or any(roles != expected_drawer_roles for roles in by_drawer.values())):
        raise DesignError("Se requieren seis piezas nominales por cada caja y fachada.")
    result = deepcopy(source)
    # Translate F1/F7C panels into one common coordinate system, no redraw.
    # Original overlay z=-top; after shifting it occupies z=0..top.
    for part in result["parts"]:
        x, y, z = part["nominal_origin_xyz_mm"]
        part["nominal_origin_xyz_mm"] = [x + free, y + feet, z + top]
    # A: facades lie along the 900 mm long edge (XY plane at Z=0),
    # and drawers open outwards towards negative Z, never from the short tip.
    faces = [p for p in result["parts"] if p["role"] == "drawer_facade"]
    if (len(faces) != 3 or any(p["face_plane"] != "XY"
            or p["nominal_origin_xyz_mm"][2] != 0
            or p["nominal_origin_xyz_mm"][0] < free
            or p["nominal_origin_xyz_mm"][0] + p["nominal_face_x_mm"] > w
            for p in faces)):
        raise DesignError("Frentes de cajón no coinciden con apertura A sobre el costado largo.")
    if any(p["piece_id"] == "BAR-COVER-TOP" for p in result["parts"]):
        raise DesignError("Cubierta duplicada.")
    result["parts"].append({
        "piece_id": "BAR-COVER-TOP", "module_id": "BAR", "role": "top",
        "material_id": module["material_id"], "nominal_face_x_mm": w,
        "nominal_face_y_mm": d, "thickness_mm": top,
        "grain_axis": "UNCONFIRMED", "face_plane": "XZ",
        "nominal_origin_xyz_mm": [0, h-top, 0],
        "edgebanding_edges": "UNCONFIRMED",
        "edgebanding_thickness_mm": None,
        "edgebanding_nominal_total_mm": None,
        "finished_cut_dimensions_mm": None,
        "source_engine": "WALL_BAR_PLACEMENT_F1_F7C",
        "source_formula": "cover=(overall_width, overall_depth); y=height-top"
    })
    result["dimensions_mm"] = {"width": w, "height": h, "depth": d}
    result["modules"][0]["start_x_mm"] = free
    result["modules"][0]["start_y_mm"] = feet
    result["piece_count"] = len(result["parts"])
    # Existing CAD and BOM consumers accept the same modular_run model.
    result["type"] = "modular_run"
    result["wall_bar_review"] = {
        "wall_side": "left", "wall_attachment": "NOT_VERIFIED",
        "drawer_opening_face": "long_side_front",
        "drawer_open_direction": "negative_Z",
        "drawer_front_plane": "XY",
        "left_vertical_wood_panels": 0, "free_span_mm": free,
        "cabinet_x_range_mm": [free, w],
        "cabinet_y_range_mm": [feet, h-top],
        "feet_height_mm": feet, "physical_feet_parts": None,
        "top_y_range_mm": [h-top, h],
        "design_choices": {
            "wall_support_presentation": wall_presentation,
            "top_edge_presentation": edge_presentation,
            "aesthetic_presentation": aesthetic_presentation,
            "aesthetic_is_illustrative_only": True,
            "wall_attachment_by_installer": True,
            "site_wall_material_required_for_design": False,
            "support_parts_modeled": False,
            "false_thickness_parts_modeled": False,
            "selected_elements_require_dimensions_and_owner_approval": (
                wall_presentation != "installer_defined"
                or edge_presentation == "false_thickness_pending"
            ),
            "options_are_design_notes_only": True,
        },
    }
    # Physical interfaces read from F1/F7C part coordinates; NO new geometry.
    # Record gaps and planar contacts, never infer a working mechanical joint.
    p_by_id = {p["piece_id"]: p for p in result["parts"]}
    cid = module["module_id"]
    bottom = p_by_id[f"{cid}-BOTTOM"]
    back = p_by_id[f"{cid}-BACK_FULL"]
    bottom_top_y = bottom["nominal_origin_xyz_mm"][1] + bottom["thickness_mm"]
    rear_front_z = back["nominal_origin_xyz_mm"][2]
    gaps = {}
    rear_gaps = {}
    planar_front_contacts = {}
    front_joint_interfaces = {}
    for did in ("D1", "D2", "D3"):
        base = p_by_id[f"{cid}-{did}-DRAWER_BOTTOM"]
        facade = p_by_id[f"{cid}-{did}-DRAWER_FACADE"]
        front_wall = p_by_id[f"{cid}-{did}-DRAWER_FRONT_WALL"]
        left = p_by_id[f"{cid}-{did}-DRAWER_SIDE_LEFT"]
        right = p_by_id[f"{cid}-{did}-DRAWER_SIDE_RIGHT"]
        gap = base["nominal_origin_xyz_mm"][1] - bottom_top_y
        rear_gap = rear_front_z - (
            base["nominal_origin_xyz_mm"][2] + base["nominal_face_y_mm"]
        )
        if gap < 0 or rear_gap < 0:
            raise DesignError(f"{did}: solape con base de carcasa o respaldo.")
        fx, fy, fz = facade["nominal_origin_xyz_mm"]
        contact_z = fz + facade["thickness_mm"]
        if front_wall["nominal_origin_xyz_mm"][2] != contact_z:
            raise DesignError(f"{did}: la fachada separada no toca la pared frontal interior.")
        surfaces = {}
        for label, part in (("front_wall", front_wall), ("left_side", left),
                            ("right_side", right), ("bottom", base)):
            px, py, pz = part["nominal_origin_xyz_mm"]
            if pz != contact_z:
                raise DesignError(f"{did}: {label} no toca plano posterior del frente.")
            # Physical XY rectangle at the open FRONT end of the panel.
            pw = (part["thickness_mm"] if part["face_plane"] == "YZ"
                  else part["nominal_face_x_mm"])
            ph = (part["thickness_mm"] if part["face_plane"] == "XZ"
                  else part["nominal_face_y_mm"])
            shared_width = min(fx + facade["nominal_face_x_mm"], px + pw) - max(fx, px)
            shared_height = min(fy + facade["nominal_face_y_mm"], py + ph) - max(fy, py)
            if shared_width != pw or shared_height != ph:
                raise DesignError(
                    f"{did}: {label} sin contacto frontal completo en ambos ejes."
                )
            surfaces[label] = {
                "piece_id": part["piece_id"],
                "nominal_contact_patch_xy_mm": [shared_width, shared_height],
                "front_contact_plane_z_mm": contact_z,
                "attachment_method": "NOT_SPECIFIED",
                "load_capacity_verified": False,
            }
        planar_front_contacts[did] = True
        front_joint_interfaces[did] = {
            "front_piece_id": facade["piece_id"],
            "box_front_wall_piece_id": front_wall["piece_id"],
            "front_construction": "separate",
            "front_style": "overlay",
            "decorative_front_is_structural": False,
            "contact_is_not_a_mechanical_joint": True,
            "surfaces": surfaces,
            "fixing_holes_specified": False,
            "fabrication_ready": False,
        }
        gaps[did] = gap
        rear_gaps[did] = rear_gap
    result["wall_bar_review"]["drawer_base_clearance_mm"] = gaps
    result["wall_bar_review"]["drawer_rear_clearance_mm"] = rear_gaps
    result["wall_bar_review"]["drawer_front_contact"] = {
        k: "GEOMETRIC_PLANES_ONLY_NOT_FASTENED" for k in planar_front_contacts
    }
    result["wall_bar_review"]["front_joint_interfaces"] = front_joint_interfaces
    # The CAD has NOMINAL external faces only. Panel-cut sizing must not
    # silently treat those nominal sizes as raw substrate plus added PVC.
    # 2 mm banding on four edges can change each face dimension by 4 mm.
    front_edge = 2
    edge_review = {}
    finished_fronts = sorted(
        (p for p in result["parts"] if p["role"] == "drawer_facade"),
        key=lambda p: p["nominal_origin_xyz_mm"][1]
    )
    for front_part in finished_fronts:
        did = front_part["drawer_id"]
        fw = front_part["nominal_face_x_mm"]
        fh = front_part["nominal_face_y_mm"]
        edge_review[did] = {
            "nominal_face_width_mm": fw,
            "nominal_face_height_mm": fh,
            "rigid_edge_mm_each_side": front_edge,
            "if_nominal_is_finished_theoretical_raw_width_mm": fw - 2 * front_edge,
            "if_nominal_is_finished_theoretical_raw_height_mm": fh - 2 * front_edge,
            "if_nominal_is_raw_resulting_width_mm": fw + 2 * front_edge,
            "if_nominal_is_raw_resulting_height_mm": fh + 2 * front_edge,
            "theoretical_only_not_cut_dimensions": True,
        }
    nominal_reveals = {}
    uncompensated_reveals = {}
    for prev, nxt in zip(finished_fronts, finished_fronts[1:]):
        lower_id, upper_id = prev["drawer_id"], nxt["drawer_id"]
        prev_y = prev["nominal_origin_xyz_mm"][1]
        next_y = nxt["nominal_origin_xyz_mm"][1]
        nominal_gap = next_y - (prev_y + prev["nominal_face_y_mm"])
        compensated = nominal_gap - 2 * front_edge
        nominal_reveals[f"{lower_id}_{upper_id}"] = nominal_gap
        uncompensated_reveals[f"{lower_id}_{upper_id}"] = compensated
    cabinet_front_reveal = (cabinet_w - finished_fronts[0]["nominal_face_x_mm"]) / 2
    result["wall_bar_review"]["front_edgebanding_review"] = {
        "status": "PENDING_FINISHED_VS_RAW_INTERPRETATION",
        "nominal_panel_dimensions_are_not_cut_dimensions": True,
        "fronts": edge_review,
        "nominal_gaps_between_fronts_mm": nominal_reveals,
        "gaps_if_nominal_panels_are_cut_raw_then_banded_mm": uncompensated_reveals,
        "nominal_cabinet_side_reveal_each_mm": cabinet_front_reveal,
        "side_reveal_if_nominal_is_raw_and_2mm_band_each_side_mm":
            cabinet_front_reveal - front_edge,
        "cutting_dimensions_authorized": False,
    }
    result["blockers"].append(
        "CANTO FRONTAL: hay holguras nominales de 2 mm entre frentes; "
        "si se cortan a la medida nominal y se agrega PVC 2 mm por borde, "
        "cada frente crece 4 mm por eje y las separaciones pasan a -2 mm. "
        "Definir dimensiones terminadas, sustrato, merma y procesos antes de corte."
    )
    result["blockers"].extend([
        f"D3: holgura vertical inferior nominal de {gaps['D3']} mm sin "
        "validación de correderas, tolerancias, carga ni flexión.",
        "D1/D2/D3: el frente solo contacta geométricamente los laterales; "
        "faltan conectores dimensionados y verificados.",
    ])
    result["blockers"].extend([
        "El instalador verifica en obra los anclajes y la seguridad del apoyo mural; "
        "NO es requisito para continuar el diseño de la barra.",
        "Resistencia de la cubierta bajo uso real NO verificada: "
        "nota técnica, sin impedir la revisión del CAD.",
        "Patas: SKU, cantidad, capacidad, distribución y fijaciones SIN VALIDAR.",
        "Fachadas decorativas separadas: unión a pared frontal interior y ajuste SIN VALIDAR.",
        "Los solapes overlay proceden del fixture de revisión; no son dimensiones aprobadas.",
        "Tapacanto rígido en frentes y flexible en restantes: dimensiones de corte pendientes.",
        "Prohibido inventar lateral izquierdo, faldón, escuadra o soporte físico.",
        "A confirmada: tres cajones abren hacia costado largo (Z negativo)."
    ])
    for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
        result[flag] = False
    return result
