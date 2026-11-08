"""Single CAD exchange contract for FreeCAD and Blender, not an MCP server.

Source of truth is F6 panel geometry; CAD executors/renderers are consumers.
No geometry is reconstructed by prose or a second model implementation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .core import DesignError
from .modular_outputs import _review_draft


def nominal_front_extension_mm(parts: list[dict[str, Any]]) -> int:
    """Forward extension of real overlay faces from the carcass plane.

    Shared by F6 dimensional review and the single CADExchange contract.
    Do not treat material thickness alone as an extra front unless its
    origin lies ahead of the carcass (negative Z).
    """
    return max((p["thickness_mm"] for p in parts
                if (p["role"].startswith("front_")
                    or p["role"] == "drawer_facade")
                and p["nominal_origin_xyz_mm"][2] < 0), default=0)


def cad_exchange(model: dict[str, Any]) -> dict[str, Any]:
    """Stable 3D panel boxes with explicit physical mm coordinates."""
    draft=_review_draft(model)
    boxes=[]
    w,h,d=(draft["dimensions_mm"][k] for k in ("width","height","depth"))
    seen=set()
    has_fronts=any(p["role"].startswith("front_") for p in draft["parts"])
    has_drawers=any(p["role"].startswith("drawer_") for p in draft["parts"])
    # Overlay leaves extend in front of the F6 z=0 carcass plane.
    # Translate ALL pieces by the same amount for nonnegative CAD coordinates.
    # F7C_CAD_OVERLAY_SHIFT_20261021
    # Drawer facades use the SAME geometric origin system as door leaves.
    # Shift every panel uniformly; never allow negative CAD coordinates.
    front_shift=nominal_front_extension_mm(draft["parts"])
    for p in draft["parts"]:
        role=p["role"]
        t=p["thickness_mm"]
        fx,fy=p["nominal_face_x_mm"],p["nominal_face_y_mm"]
        x,y,z=p["nominal_origin_xyz_mm"]
        if type(t) is not int or type(fx) is not int or type(fy) is not int:
            raise DesignError("Paneles sin cotas físicas enteras.")
        if role in ("left_side","right_side"):
            size=[t,fy,fx]  # panel in YZ plane: thickness X; face_x -> depth Z
            grain_world={"face_x":"Z","face_y":"Y","none":"none"}
        elif role in ("top", "bottom", "shelf_horizontal", "countertop"):
            size=[fx,t,fy]  # panel in XZ plane: thickness Y; face_x -> width X
            grain_world={"face_x":"X","face_y":"Z","none":"none"}
        elif role in ("upper_front_tie", "upper_rear_tie", "lower_rear_tie"):
            size=[fx,fy,t]  # upright tie in XY: board thickness is depth Z
            grain_world={"face_x":"X","face_y":"Y","none":"none"}
        elif role in ("back_full", "back_bottom", "back_top",
                      "front_single", "front_left", "front_right",
                      "drawer_front_wall", "drawer_rear_wall", "drawer_facade"):
            size=[fx,fy,t]  # back/door planes XY, thickness Z
            grain_world={"face_x":"X","face_y":"Y","none":"none"}
        elif role in ("drawer_side_left", "drawer_side_right"):
            size=[t,fy,fx]  # XY? no: YZ side box with depth along Z
            grain_world={"face_x":"Z","face_y":"Y","none":"none"}
        elif role == "drawer_bottom":
            size=[fx,t,fy]  # XZ bottom under drawer walls
            grain_world={"face_x":"X","face_y":"Z","none":"none"}
        elif role == "support_leg_concept":
            size=[fx,fy,t]  # conceptual vertical support marker, XY face
            grain_world={"face_x":"X","face_y":"Y","none":"none"}
        else:
            raise DesignError("Rol no soportado en intercambio CAD.")
        z += front_shift
        if any(type(n) is not int for n in (x,y,z)) or min([x,y,z]+size)<0:
            raise DesignError("Panel con origen/medidas no válidos.")
        if min(size)<=0 or x+size[0]>w or y+size[1]>h or z+size[2]>d+front_shift:
            raise DesignError("Panel CAD fuera de dimensiones del mueble.")
        pid=p["piece_id"]
        if not isinstance(pid,str) or not pid or pid in seen:
            raise DesignError("ID de pieza duplicado o inválido.")
        seen.add(pid)
        grain=p["grain_axis"]
        if grain!="UNCONFIRMED" and grain not in grain_world:
            raise DesignError("Veta no reconocida.")
        boxes.append({
            "piece_id":pid,"module_id":p["module_id"],
            "material_id":p["material_id"],"role":role,
            "origin_xyz_mm":[x,y,z],"size_xyz_mm":size,
            "grain_world_axis":(
                "UNCONFIRMED" if grain=="UNCONFIRMED" else grain_world[grain]
            ),
            "construction_geometry":"NOMINAL_PANEL_BOX",
        })
    has_backs=any(b["role"].startswith("back_") for b in boxes)
    payload={
        "schema_version":"0.1.0",
        "source_engine":("F7C_DRAWER_BOXES_FROM_F1" if has_drawers else
                         "F7C_EXPLICIT_FRONTS_FROM_F6" if has_fronts else
                         "F7C_INSET_BACKS_FROM_F6" if has_backs else
                         "F6_OPEN_MODULES_FROM_F1"),
        "unit":"mm",
        "coordinate_system":"right-handed X width/right, Y height/up, Z depth/back",
        "status":"DRAFT_NOT_FOR_CUTTING",
        "fabrication_ready":False,
        "cutting_ready":False,
        "drilling_ready":False,
        "manufacturing_holes":[],
        "bounds_xyz_mm":[w,h,d+front_shift],
        "boxes":boxes,
        "hardware_included":False,
        "finished_panel_edges_included":False,
        "cad_warning":("Nominal drawers from F1 and explicit inset/overlay facades. "
                       "Slides, joins, bores, face mounting and load capacity NOT certified."
                       if has_drawers else
                       "Nominal carcass and front leaf boxes. "
                       "All boxes share an explicit forward-Z CAD shift. "
                       "No hinges, drilling, sweeps, hardware or finished cut authority."
                       if has_fronts else
                       "Nominal carcass and rear inset panel boxes. "
                       "No routed service cutouts, door/drawer details, "
                       "machining or verified anchors."
                       if has_backs else
                       "Only carcass panel boxes. No backs, doors, drawers, machining or anchors."),
    }
    # Existing front-door contract is unchanged. New overlay drawer facades
    # need the same audited offset so they fit nonnegative FreeCAD/Blender XYZ.
    if has_fronts or front_shift > 0:
        payload["front_shift_mm"]=front_shift
    if draft.get("assembly_review") is not None:
        payload["assembly_review"] = draft["assembly_review"]
    if draft.get("upper_support_review") is not None:
        payload["upper_support_review"] = draft["upper_support_review"]
    signature=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":"))
    # One canonical integrity check before FreeCAD, Blender or CSV clients
    # can consume the model, including physical solid intersections.
    return validate_exchange({
        **payload, "geometry_sha256":hashlib.sha256(
            signature.encode("utf-8")).hexdigest(),
    })


def validate_exchange(data: Any) -> dict[str,Any]:
    """Validate an exchange before any external CAD application receives it."""
    if not isinstance(data,dict):
        raise DesignError("CAD exchange debe ser un objeto.")
    if data.get("schema_version")!="0.1.0" or data.get("unit")!="mm":
        raise DesignError("Contrato CAD incompatible.")
    if data.get("source_engine") not in (
            "F6_OPEN_MODULES_FROM_F1", "F7C_INSET_BACKS_FROM_F6",
            "F7C_EXPLICIT_FRONTS_FROM_F6", "F7C_DRAWER_BOXES_FROM_F1"):
        raise DesignError("Fuente de geometría no canónica.")
    if data.get("status")!="DRAFT_NOT_FOR_CUTTING":
        raise DesignError("Solo se admite geometría preliminar.")
    for flag in ("fabrication_ready","cutting_ready","drilling_ready",
                 "hardware_included","finished_panel_edges_included"):
        if data.get(flag) is not False:
            raise DesignError(f"Bandera prohibida: {flag}")
    if data.get("manufacturing_holes") != []:
        raise DesignError("No se admiten patrones de taladro por CAD.")
    expected=set(("schema_version","source_engine","unit","coordinate_system","status",
        "fabrication_ready","cutting_ready","drilling_ready","manufacturing_holes",
        "bounds_xyz_mm","boxes","hardware_included","finished_panel_edges_included",
        "cad_warning","geometry_sha256"))
    # Legacy F7C inset drawers keep the EXACT old schema (without shift).
    # F7C overlay drawers may opt into the front_shift field. The validator
    # still checks the digest, all bounds and every intersecting solid.
    has_front_boxes = any(
        isinstance(p, dict) and p.get("role", "").startswith("front_")
        for p in data.get("boxes", [])
    )
    required_shift = (data["source_engine"]=="F7C_EXPLICIT_FRONTS_FROM_F6" or
                      (data["source_engine"]=="F7C_DRAWER_BOXES_FROM_F1"
                       and has_front_boxes))
    overlay_drawer_shift = (data["source_engine"]=="F7C_DRAWER_BOXES_FROM_F1"
                            and not required_shift
                            and "front_shift_mm" in data
                            and any(isinstance(p,dict) and
                                    p.get("role")=="drawer_facade"
                                    for p in data.get("boxes", [])))
    if required_shift or overlay_drawer_shift:
        expected.add("front_shift_mm")
        shift=data.get("front_shift_mm")
        if type(shift) is not int or shift < (1 if overlay_drawer_shift else 0):
            raise DesignError("Desplazamiento CAD frontal inválido.")
    if "assembly_review" in data:
        expected.add("assembly_review")
    if "upper_support_review" in data:
        expected.add("upper_support_review")
    if set(data)!=expected:
        raise DesignError("Campos CAD faltantes o inesperados.")
    h=data["geometry_sha256"]
    if not isinstance(h,str) or len(h)!=64:
        raise DesignError("Firma de geometría ausente.")
    unsealed={k:v for k,v in data.items() if k!="geometry_sha256"}
    digest=hashlib.sha256(json.dumps(unsealed,sort_keys=True,
        ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest()
    if h!=digest:
        raise DesignError("Contrato CAD modificado después del cálculo F6.")
    limits=data["bounds_xyz_mm"]
    if not isinstance(limits,list) or len(limits)!=3 or any(
        type(n) is not int or n<=0 for n in limits):
        raise DesignError("Medidas CAD generales inválidas.")
    boxes=data["boxes"]
    if not isinstance(boxes,list) or not boxes or len(boxes)>72:
        raise DesignError("Cantidad de piezas inválida.")
    names=set()
    for item in boxes:
        if not isinstance(item,dict) or set(item)!={
                "piece_id","module_id","material_id","role","origin_xyz_mm",
                "size_xyz_mm","grain_world_axis","construction_geometry"}:
            raise DesignError("Panel CAD inválido.")
        name=item["piece_id"]
        if not isinstance(name,str) or not name or name in names:
            raise DesignError("Identificador CAD repetido.")
        names.add(name)
        if item["role"] not in ("left_side","right_side","top","bottom",
                                "back_full","back_bottom","back_top",
                                "front_single","front_left","front_right",
                                "drawer_side_left","drawer_side_right",
                                "drawer_front_wall","drawer_rear_wall",
                                "drawer_bottom","drawer_facade",
                                "support_leg_concept", "shelf_horizontal",
                                "countertop", "upper_front_tie",
                                "upper_rear_tie", "lower_rear_tie"):
            raise DesignError("Rol CAD no soportado.")
        a,b=item["origin_xyz_mm"],item["size_xyz_mm"]
        if (not isinstance(a,list) or not isinstance(b,list)
                or len(a)!=3 or len(b)!=3 or any(
                    type(n) is not int for n in a+b)
                or min(a)<0 or min(b)<=0 or any(
                    a[i]+b[i]>limits[i] for i in range(3))):
            raise DesignError("Caja CAD excede límites físicos.")
    assembly = data.get("assembly_review")
    has_countertop = any(box["role"] == "countertop" for box in boxes)
    if has_countertop != (assembly is not None):
        raise DesignError("Una cubierta requiere metadatos de ensamblaje verificables.")
    if assembly is not None:
        fields = {
            "carcass_origin_xyz_mm", "carcass_dimensions_xyz_mm",
            "support_style", "support_height_mm", "physical_support_parts",
            "countertop_piece_id", "countertop_thickness_mm",
            "countertop_finish_note", "review_status", "vertical_load_path",
            "wall_vertical_load_role", "countertop_wall_vertical_support",
            "front_gaps_status", "shelf_position_status",
        }
        if not isinstance(assembly, dict) or set(assembly) != fields:
            raise DesignError("Revisión de cubierta/apoyo CAD incompleta.")
        origin, carcass = (assembly["carcass_origin_xyz_mm"],
                           assembly["carcass_dimensions_xyz_mm"])
        if (not isinstance(origin, list) or len(origin) != 3
                or not isinstance(carcass, list) or len(carcass) != 3
                or any(type(v) is not int or v < 0 for v in origin)
                or any(type(v) is not int or v <= 0 for v in carcass)
                or any(origin[i] + carcass[i] > limits[i] for i in range(3))):
            raise DesignError("Envolvente de carcasa CAD inválida.")
        if (assembly["support_style"] not in (
                    "floor_direct", "legs", "plinth", "wall_mounted")
                or type(assembly["support_height_mm"]) is not int
                or assembly["support_height_mm"] < 0
                or assembly["physical_support_parts"] != "NOT_MODELED"
                or type(assembly["countertop_thickness_mm"]) is not int
                or assembly["countertop_thickness_mm"] <= 0
                or type(assembly["countertop_finish_note"]) is not str
                or assembly["review_status"] != "HYPOTHESIS_PREVIEW_ONLY"
                or assembly["vertical_load_path"] !=
                    "CARCASS_TO_LEGS_TO_FLOOR_CONCEPT_ONLY"
                or assembly["wall_vertical_load_role"] != "NONE_OWNER_CONFIRMED"
                or assembly["countertop_wall_vertical_support"] != "EXCLUDED_BY_OWNER"
                or assembly["front_gaps_status"] != "HYPOTHESIS_PREVIEW_ONLY"
                or assembly["shelf_position_status"] != "HYPOTHESIS_PREVIEW_ONLY"):
            raise DesignError("Metadatos de apoyo/cubierta CAD inválidos.")
        top = next((box for box in boxes
                    if box["piece_id"] == assembly["countertop_piece_id"]
                    and box["role"] == "countertop"), None)
        if (top is None or top["origin_xyz_mm"] !=
                [0, limits[1] - assembly["countertop_thickness_mm"], 0]
                or top["size_xyz_mm"] != [limits[0],
                                           assembly["countertop_thickness_mm"],
                                           limits[2]]
                or limits[1] != (carcass[1] + assembly["support_height_mm"]
                                 + assembly["countertop_thickness_mm"])):
            raise DesignError("Cubierta CAD no cierra con la carcasa y el alto total.")
        left_side = next((box for box in boxes
                          if box["role"] == "left_side"), None)
        right_side = next((box for box in boxes
                           if box["role"] == "right_side"), None)
        if (left_side is None or right_side is None
                or left_side["origin_xyz_mm"] != origin
                or left_side["size_xyz_mm"] != [left_side["size_xyz_mm"][0],
                                                  carcass[1], carcass[2]]
                or right_side["origin_xyz_mm"] != [
                    origin[0] + carcass[0] - right_side["size_xyz_mm"][0],
                    origin[1], origin[2],
                ]
                or right_side["size_xyz_mm"] != left_side["size_xyz_mm"]):
            raise DesignError("Origen o dimensiones CAD de carcasa no coinciden.")
    upper = data.get("upper_support_review")
    tie_boxes = [box for box in boxes
                 if box["role"] in ("upper_front_tie", "upper_rear_tie",
                                     "lower_rear_tie")]
    if bool(tie_boxes) != (upper is not None):
        raise DesignError("Los travesaños CAD requieren revisión de apoyo superior.")
    if upper is not None:
        fields = {
            "module_id", "style", "construction", "piece_ids", "length_mm",
            "length_basis", "tie_height_mm", "tie_height_status", "material_id",
            "thickness_mm", "source_engine", "structural_engineering",
            "wall_vertical_load_role", "countertop_wall_vertical_support",
            "cabinet_wall_anchoring",
        }
        if not isinstance(upper, dict) or set(upper) != fields:
            raise DesignError("Revisión de travesaños superiores incompleta.")
        if (upper["style"] != "coffee_three_upright_ties"
                or upper["construction"] != "sides_full"
                or upper["source_engine"] != "F6_OPTIONAL_UPPER_SUPPORT"
                or upper["length_basis"] != "F1.clear_width_mm"
                or upper["tie_height_status"] != "REVIEW_HEIGHT_HYPOTHESIS_ONLY"
                or upper["structural_engineering"] != "UNVERIFIED"
                or upper["wall_vertical_load_role"] != "NONE_OWNER_CONFIRMED"
                or upper["countertop_wall_vertical_support"] != "EXCLUDED_BY_OWNER"
                or upper["cabinet_wall_anchoring"] !=
                    "INSTALLER_STABILITY_ONLY_UNVERIFIED"
                or not has_countertop
                or any(box["role"] == "top" for box in boxes)):
            raise DesignError("Las correas de canto contradicen sus bloqueos o geometría.")
        module_id = upper["module_id"]
        tie_height, length, thickness = (upper[key] for key in
                                         ("tie_height_mm", "length_mm", "thickness_mm"))
        if (type(module_id) is not str or type(tie_height) is not int or tie_height <= 0
                or type(length) is not int or length <= 0
                or type(thickness) is not int or thickness <= 0
                or type(upper["material_id"]) is not str
                or 2 * thickness > limits[2]
                or not isinstance(upper["piece_ids"], list)
                or upper["piece_ids"] != [
                    module_id + "-UPPER_FRONT_TIE",
                    module_id + "-UPPER_REAR_TIE",
                    module_id + "-LOWER_REAR_TIE",
                ]):
            raise DesignError("Dimensiones o IDs de correas de canto inválidos.")
        if assembly is None:
            raise DesignError("Travesaños superiores sin mesón ensamblado.")
        carcass_origin = assembly["carcass_origin_xyz_mm"]
        carcass_size = assembly["carcass_dimensions_xyz_mm"]
        left_side = next((box for box in boxes
                          if box["role"] == "left_side"
                          and box["module_id"] == module_id), None)
        if (left_side is None or upper["construction"] != "sides_full"
                or length != carcass_size[0] - 2 * left_side["size_xyz_mm"][0]
                or 2 * tie_height + thickness > carcass_size[1]
                or len(tie_boxes) != 3):
            raise DesignError("Correas no coinciden con el claro interior F1.")
        by_role = {box["role"]: box for box in tie_boxes}
        if set(by_role) != {"upper_front_tie", "upper_rear_tie",
                            "lower_rear_tie"}:
            raise DesignError("Falta una de las tres correas de canto.")
        shift = data.get("front_shift_mm", 0)
        upper_y = carcass_origin[1] + carcass_size[1] - tie_height
        rear_z = carcass_origin[2] + carcass_size[2] - thickness + shift
        expected_origins = {
            "upper_front_tie": [
                carcass_origin[0] + left_side["size_xyz_mm"][0],
                upper_y,
                carcass_origin[2] + shift,
            ],
            "upper_rear_tie": [
                carcass_origin[0] + left_side["size_xyz_mm"][0],
                upper_y,
                rear_z,
            ],
            "lower_rear_tie": [
                carcass_origin[0] + left_side["size_xyz_mm"][0],
                carcass_origin[1] + thickness,
                rear_z,
            ],
        }
        for role, box in by_role.items():
            if (box["module_id"] != module_id
                    or box["piece_id"] != module_id + "-" + role.upper()
                    or box["material_id"] != upper["material_id"]
                    or box["origin_xyz_mm"] != expected_origins[role]
                    or box["size_xyz_mm"] != [length, tie_height, thickness]):
                raise DesignError("Caja de correa de canto CAD no coincide con F1.")
    # A butt joint may share a face (zero overlap), but two physical panels
    # must never have strictly positive intersecting volumes. Reuse the
    # already-standardized CAD boxes instead of a parallel geometry engine.
    for idx, first in enumerate(boxes):
        f0, fs = first["origin_xyz_mm"], first["size_xyz_mm"]
        for second in boxes[idx+1:]:
            s0, ss = second["origin_xyz_mm"], second["size_xyz_mm"]
            if all(max(f0[axis], s0[axis]) <
                   min(f0[axis]+fs[axis], s0[axis]+ss[axis])
                   for axis in range(3)):
                raise DesignError(
                    "Tableros CAD ocupan el mismo volumen: "
                    + first["piece_id"] + " / " + second["piece_id"]
                    + "; corregir la geometría original antes de fabricar."
                )
    return data
