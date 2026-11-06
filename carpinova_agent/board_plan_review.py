"""Deterministic nominal sheet-placement review; never a saw/CNC plan."""
from __future__ import annotations

import colorsys
from html import escape
import math
import re
from typing import Any

from .cad_exchange import cad_exchange
from .core import DesignError
from .maestro import MaestroError, consult_maestro


_ROOT_KEYS = frozenset((
    "review_kind", "source_request", "board_catalog", "piece_assignments",
    "machine_allowances",
))
_BOARD_KEYS = frozenset((
    "board_id", "supplier", "reference", "decoration", "substrate",
    "thickness_mm", "length_mm", "width_mm", "grain_direction",
))
_ASSIGNMENT_KEYS = frozenset(("piece_id", "board_id", "grain_axis", "continuity_group"))
_ALLOWANCE_KEYS = frozenset((
    "kerf_mm", "trim_left_mm", "trim_right_mm", "trim_top_mm",
    "trim_bottom_mm",
))
_GRAIN_AXES = frozenset(("face_x", "face_y", "none"))
_BOARD_GRAINS = frozenset(("along_length", "along_width", "none"))
_MAX_PARTS = 72
_MAX_BOARDS = 24
_MAX_SHEETS = 72
_MAX_DIMENSION_MM = 10_000
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PHYSICAL_ROLES = frozenset((
    "left_side", "right_side", "top", "bottom", "back_full", "back_bottom",
    "back_top", "front_single", "front_left", "front_right",
    "drawer_side_left", "drawer_side_right", "drawer_front_wall",
    "drawer_rear_wall", "drawer_bottom", "drawer_facade",
))
_CONCEPT_ROLES = frozenset(("support_leg_concept",))
_ROLE_PLANE = {
    "left_side": "YZ", "right_side": "YZ",
    "drawer_side_left": "YZ", "drawer_side_right": "YZ",
    "top": "XZ", "bottom": "XZ", "drawer_bottom": "XZ",
    "back_full": "XY", "back_bottom": "XY", "back_top": "XY",
    "front_single": "XY", "front_left": "XY", "front_right": "XY",
    "drawer_front_wall": "XY", "drawer_rear_wall": "XY",
    "drawer_facade": "XY", "support_leg_concept": "XY",
}
_FLAGS = {
    "fabrication_ready": False, "cutting_ready": False,
    "drilling_ready": False, "purchase_ready": False,
}


def _invalid(message: str) -> MaestroError:
    return MaestroError(message)


def _object(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise _invalid(f"{name} debe ser un objeto JSON.")
    return value


def _extra_keys(value: dict[str, Any], allowed: frozenset[str], name: str) -> None:
    extra = value.keys() - allowed
    if extra:
        if {"front_decoration", "back_decoration"} <= extra:
            front, back = value.get("front_decoration"), value.get("back_decoration")
            if front != back:
                raise _invalid("UNSUPPORTED_DUAL_DECOR_FACE: una cara doble requiere otro modelo explícito.")
        raise _invalid(f"{name}: campos no permitidos: {', '.join(sorted(extra))}.")


def _safe_id(value: Any, name: str) -> str:
    if type(value) is not str or not _SAFE_ID.fullmatch(value):
        raise _invalid(f"{name} debe ser un identificador corto sin rutas ni URL.")
    return value


def _label(value: Any, name: str) -> str:
    if (type(value) is not str or not value.strip() or len(value) > 120
            or any(ord(ch) < 32 for ch in value)
            or re.search(r"(?i)(https?://|file:|[a-z]:[/\\])", value)
            or "/" in value or "\\" in value):
        raise _invalid(f"{name} debe ser una etiqueta breve, sin URL ni ruta.")
    return value.strip()


def _integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _invalid(f"{name} requiere entero entre {minimum} y {maximum} mm.")
    return value


def _face_axis_to_world(face_plane: str, grain_axis: str) -> str:
    mapping = {
        "XY": {"face_x": "X", "face_y": "Y"},
        "XZ": {"face_x": "X", "face_y": "Z"},
        "YZ": {"face_x": "Z", "face_y": "Y"},
    }
    if grain_axis == "none":
        return "none"
    try:
        return mapping[face_plane][grain_axis]
    except KeyError as exc:
        raise _invalid("Plano de cara o eje de veta no soportado.") from exc


def _plane_box_size(part: dict[str, Any]) -> list[int]:
    plane = part.get("face_plane")
    fx, fy, thickness = (part.get(key) for key in (
        "nominal_face_x_mm", "nominal_face_y_mm", "thickness_mm"))
    if (plane not in ("XY", "XZ", "YZ")
            or any(type(v) is not int or v <= 0 for v in (fx, fy, thickness))):
        raise _invalid("UNSUPPORTED_SOURCE: panel sin cara rectangular nominal válida.")
    return {"XY": [fx, fy, thickness],
            "XZ": [fx, thickness, fy],
            "YZ": [thickness, fy, fx]}[plane]


def _validate_maestro_cad(modular: dict[str, Any], cad: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    parts = modular.get("parts")
    boxes = cad.get("boxes")
    if (type(parts) is not list or not parts or len(parts) > _MAX_PARTS
            or type(boxes) is not list or len(boxes) != len(parts)):
        raise _invalid("UNSUPPORTED_SOURCE: Maestro no produjo una lista acotada de paneles físicos.")
    part_by_id: dict[str, dict[str, Any]] = {}
    box_by_id: dict[str, dict[str, Any]] = {}
    for part in parts:
        _object(part, "Maestro part")
        pid = part.get("piece_id")
        if type(pid) is not str or not pid or pid in part_by_id:
            raise _invalid("UNSUPPORTED_SOURCE: IDs de panel ausentes o duplicados.")
        part_by_id[pid] = part
    for box in boxes:
        _object(box, "CAD box")
        pid = box.get("piece_id")
        if type(pid) is not str or not pid or pid in box_by_id:
            raise _invalid("UNSUPPORTED_SOURCE: IDs CAD ausentes o duplicados.")
        box_by_id[pid] = box
    if set(part_by_id) != set(box_by_id):
        raise _invalid("UNSUPPORTED_SOURCE: IDs de Maestro y CAD no coinciden.")

    physical: list[dict[str, Any]] = []
    concepts: list[dict[str, Any]] = []
    for pid, part in part_by_id.items():
        role = part.get("role")
        if type(role) is not str or role not in _PHYSICAL_ROLES | _CONCEPT_ROLES:
            raise _invalid("UNSUPPORTED_SOURCE: rol no rectangular o no admitido.")
        expected_plane = _ROLE_PLANE[role]
        if part.get("face_plane") != expected_plane:
            raise _invalid("UNSUPPORTED_SOURCE: face_plane no corresponde al rol.")
        size = _plane_box_size(part)
        box = box_by_id[pid]
        if (box.get("role") != role or box.get("module_id") != part.get("module_id")
                or box.get("material_id") != part.get("material_id")
                or box.get("size_xyz_mm") != size
                or box.get("construction_geometry") != "NOMINAL_PANEL_BOX"):
            raise _invalid("UNSUPPORTED_SOURCE: CADExchange no coincide con el panel Maestro " + pid + ".")
        source_grain = part.get("grain_axis")
        if type(source_grain) is not str or source_grain not in _GRAIN_AXES | {"UNCONFIRMED"}:
            raise _invalid("UNSUPPORTED_SOURCE: eje de veta de Maestro no reconocido.")
        expected_world = ("UNCONFIRMED" if source_grain == "UNCONFIRMED"
                          else _face_axis_to_world(expected_plane, source_grain))
        if box.get("grain_world_axis") != expected_world:
            raise _invalid("UNSUPPORTED_SOURCE: conversión de veta Maestro/CAD no coincide " + pid + ".")
        if role in _CONCEPT_ROLES:
            concepts.append(part)
            continue
        finished = part.get("finished_cut_dimensions_mm")
        if (finished is not None and finished != "NOT_VERIFIED"
                and (type(finished) not in (list, tuple) or len(finished) != 2
                     or any(type(n) is not int or n <= 0 for n in finished))):
            raise _invalid("UNSUPPORTED_SOURCE: medidas terminadas no verificables.")
        physical.append(part)
    if not physical:
        raise _invalid("UNSUPPORTED_SOURCE: no hay paneles rectangulares físicos.")
    return physical, concepts


def _blocked(status: str, *, geometry_sha: str | None = None,
             piece_ids: list[str] | None = None,
             concept_ids: list[str] | None = None,
             blockers: list[str] | None = None,
             extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "output_kind": ("CONCEPT_ONLY" if status == "CONCEPT_ONLY"
                         else "NOMINAL_SHEET_SIMULATION"),
        "geometry_sha256": geometry_sha,
        "piece_ids": list(piece_ids or []),
        "piece_count": len(piece_ids or []),
        "excluded_concept_piece_ids": list(concept_ids or []),
        "sheets": [], "by_board": [], "unplaced": [],
        "estimated_nominal_sheet_count": None,
        "estimated_total_sheet_count": None,
        "area_lower_bound": [],
        "review_blockers": list(blockers or []),
        "cut_sequence_status": "CUT_SEQUENCE_NOT_VERIFIED",
        "cut_sequence_reason": (
            "La colocación geométrica por estantes no valida una secuencia de corte guillotina ni una máquina."
        ),
        "finished_cut_dimensions_status": "NOT_VERIFIED",
        "continuity_status": "NOT_REQUESTED",
        "grain_assignment_provenance": "DECLARED_INPUT_NOT_AUTHENTICATED",
        "customer_finish_confirmation": "PENDING",
        "edgebanding_review": [],
        "edgebanding_nominal_length_mm": None,
        "can_generate_f7c": False,
        **_FLAGS,
    }
    if extra:
        result.update(extra)
    return result


def _validate_source_request(source: Any) -> dict[str, Any]:
    source = _object(source, "source_request")
    _extra_keys(source, frozenset(("action", "module_spec")), "source_request")
    if "query" in source or "evidence_topic" in source:
        raise _invalid("Las consultas del libro no se admiten en board_plan_nominal.")
    if set(source) != {"action", "module_spec"} or source.get("action") != "modular":
        raise _invalid("source_request requiere action=modular y module_spec explícito.")
    spec = _object(source.get("module_spec"), "source_request.module_spec")
    if type(spec.get("type")) is not str or not spec["type"].strip():
        raise _invalid("source_request.module_spec.type debe ser explícito.")
    # Existing Maestro remains the only geometry authority; unknown families
    # are allowed to reach it and are accepted only if it returns supported panels.
    return source


def _catalog(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if value is None or value == []:
        return [], ["Falta board_catalog con SKU/formato comercial explícito."]
    if type(value) is not list or len(value) > _MAX_BOARDS:
        raise _invalid("board_catalog debe contener como máximo 24 referencias.")
    normalized: list[dict[str, Any]] = []
    missing: list[str] = []
    seen_ids: set[str] = set()
    seen_refs: set[tuple] = set()
    for index, item in enumerate(value):
        item = _object(item, f"board_catalog[{index}]")
        _extra_keys(item, _BOARD_KEYS, f"board_catalog[{index}]")
        if _BOARD_KEYS - item.keys():
            missing.append(f"board_catalog[{index}]: faltan campos {', '.join(sorted(_BOARD_KEYS - item.keys()))}.")
            continue
        board_id = _safe_id(item["board_id"], "board_id")
        if board_id in seen_ids:
            raise _invalid("board_catalog contiene board_id duplicado.")
        seen_ids.add(board_id)
        row = {
            "board_id": board_id,
            "supplier": _label(item["supplier"], "supplier"),
            "reference": _label(item["reference"], "reference"),
            "decoration": _label(item["decoration"], "decoration"),
            "substrate": _label(item["substrate"], "substrate").upper(),
            "thickness_mm": _integer(item["thickness_mm"], "thickness_mm", minimum=1, maximum=100),
            "length_mm": _integer(item["length_mm"], "length_mm", minimum=1, maximum=_MAX_DIMENSION_MM),
            "width_mm": _integer(item["width_mm"], "width_mm", minimum=1, maximum=_MAX_DIMENSION_MM),
            "grain_direction": item["grain_direction"],
        }
        if (type(row["grain_direction"]) is not str
                or row["grain_direction"] not in _BOARD_GRAINS):
            raise _invalid("grain_direction debe ser along_length, along_width o none.")
        identity = tuple(row[key] for key in (
            "supplier", "reference", "decoration", "substrate", "thickness_mm",
            "length_mm", "width_mm", "grain_direction"))
        if identity in seen_refs:
            raise _invalid("board_catalog repite una referencia comercial completa.")
        seen_refs.add(identity)
        normalized.append(row)
    return normalized, missing


def _assignments(value: Any, physical: list[dict[str, Any]], boards: list[dict[str, Any]]) -> tuple[dict[str, dict], list[str]]:
    if value is None or value == []:
        return {}, ["Falta una asignación de acabado/veta para cada panel físico."]
    if type(value) is not list or len(value) > _MAX_PARTS:
        raise _invalid("piece_assignments debe contener como máximo 72 registros.")
    part_by_id = {p["piece_id"]: p for p in physical}
    board_ids = {b["board_id"] for b in boards}
    assigned: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for index, raw in enumerate(value):
        row = _object(raw, f"piece_assignments[{index}]")
        if {"front_decoration", "back_decoration"} <= row.keys():
            if row["front_decoration"] != row["back_decoration"]:
                raise _invalid("UNSUPPORTED_DUAL_DECOR_FACE: una cara doble requiere otro modelo explícito.")
            raise _invalid("Asignar una sola referencia por panel; las decoraciones por cara no están modeladas.")
        _extra_keys(row, _ASSIGNMENT_KEYS, f"piece_assignments[{index}]")
        required = {"piece_id", "board_id", "grain_axis"}
        if required - row.keys():
            missing.append(f"piece_assignments[{index}]: faltan campos {', '.join(sorted(required - row.keys()))}.")
            continue
        pid = row["piece_id"]
        if type(pid) is not str or pid not in part_by_id:
            raise _invalid("Asignación de pieza desconocida o pieza conceptual excluida.")
        if pid in assigned:
            raise _invalid("piece_assignments repite piece_id: " + pid)
        board_id = _safe_id(row["board_id"], "piece_assignments.board_id")
        grain_axis = row["grain_axis"]
        if type(grain_axis) is not str or grain_axis not in _GRAIN_AXES:
            raise _invalid("grain_axis debe ser face_x, face_y o none.")
        front, back = row.get("front_decoration"), row.get("back_decoration")
        if front is not None and back is not None and front != back:
            raise _invalid("UNSUPPORTED_DUAL_DECOR_FACE: una cara doble requiere otro modelo explícito.")
        if board_ids and board_id not in board_ids:
            missing.append(f"{pid}: board_id no existe en board_catalog.")
            continue
        continuity = row.get("continuity_group")
        if continuity is not None:
            continuity = _safe_id(continuity, "continuity_group")
        source_grain = part_by_id[pid]["grain_axis"]
        if source_grain != "UNCONFIRMED" and source_grain != grain_axis:
            raise _invalid("GRAIN_OVERRIDE_REJECTED: assignment contradice veta confirmada por Maestro.")
        assigned[pid] = {
            "piece_id": pid, "board_id": board_id, "grain_axis": grain_axis,
            "continuity_group": continuity,
        }
    absent = sorted(set(part_by_id) - assigned.keys())
    if absent:
        missing.append("Sin asignación para: " + ", ".join(absent) + ".")
    return assigned, missing


def _allowances(value: Any, boards: list[dict[str, Any]]) -> tuple[dict[str, int] | None, list[str]]:
    if value is None:
        return None, ["Falta kerf_mm y los cuatro despuntes perimetrales."]
    row = _object(value, "machine_allowances")
    _extra_keys(row, _ALLOWANCE_KEYS, "machine_allowances")
    if _ALLOWANCE_KEYS - row.keys():
        return None, ["Faltan machine_allowances: " + ", ".join(sorted(_ALLOWANCE_KEYS - row.keys())) + "."]
    normalized = {
        "kerf_mm": _integer(row["kerf_mm"], "kerf_mm", minimum=0, maximum=100),
        "trim_left_mm": _integer(row["trim_left_mm"], "trim_left_mm", minimum=0, maximum=1000),
        "trim_right_mm": _integer(row["trim_right_mm"], "trim_right_mm", minimum=0, maximum=1000),
        "trim_top_mm": _integer(row["trim_top_mm"], "trim_top_mm", minimum=0, maximum=1000),
        "trim_bottom_mm": _integer(row["trim_bottom_mm"], "trim_bottom_mm", minimum=0, maximum=1000),
    }
    for board in boards:
        if (normalized["trim_left_mm"] + normalized["trim_right_mm"] >= board["width_mm"]
                or normalized["trim_top_mm"] + normalized["trim_bottom_mm"] >= board["length_mm"]):
            raise _invalid("Los cuatro despuntes anulan la zona útil de un tablero.")
    return normalized, []


def _material_signature(part: dict[str, Any]) -> tuple[str, int] | None:
    material_id = part.get("material_id")
    thickness = part.get("thickness_mm")
    if type(material_id) is not str or type(thickness) is not int:
        return None
    substrate, separator, raw_thickness = material_id.rpartition("_")
    if (not separator or not substrate or not raw_thickness.isdigit()
            or int(raw_thickness) != thickness):
        return None
    return substrate.upper(), thickness


def _orientation_allowed(axis: str, rotation: int, board_grain: str) -> bool:
    if axis == "none":
        return True
    if board_grain == "none":
        return False
    face_axis_on_sheet = ("x" if axis == "face_x" else "y")
    if rotation == 90:
        face_axis_on_sheet = "y" if face_axis_on_sheet == "x" else "x"
    expected = "y" if board_grain == "along_length" else "x"
    return face_axis_on_sheet == expected


def _pack_rectangles(pieces: list[dict], board: dict,
                     allowances: dict) -> dict[str, list]:
    """Fixed-order first-fit shelves. Coordinates are geometric, not saw steps."""
    useful_w = board["width_mm"] - allowances["trim_left_mm"] - allowances["trim_right_mm"]
    useful_h = board["length_mm"] - allowances["trim_top_mm"] - allowances["trim_bottom_mm"]
    kerf = allowances["kerf_mm"]
    order = sorted(pieces, key=lambda p: (
        -max(p["width_mm"], p["height_mm"]),
        -(p["width_mm"] * p["height_mm"]), p["piece_id"]))
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, str]] = []

    def try_sheet(sheet: dict[str, Any], piece: dict) -> dict[str, Any] | None:
        rotations = [r for r in piece["allowed_rotations"] if r in (0, 90)]
        for rotation in rotations:
            width, height = ((piece["width_mm"], piece["height_mm"])
                             if rotation == 0 else
                             (piece["height_mm"], piece["width_mm"]))
            shelves = sheet["shelves"]
            if shelves:
                shelf = shelves[-1]
                x = shelf["cursor_x"] + (kerf if shelf["placements"] else 0)
                if height <= shelf["height_mm"] and x + width <= useful_w:
                    return {"shelf": shelf, "x": x, "y": shelf["y_mm"],
                            "width": width, "height": height, "rotation": rotation}
            y = 0 if not shelves else shelves[-1]["y_mm"] + shelves[-1]["height_mm"] + kerf
            if width <= useful_w and y + height <= useful_h:
                shelf = {"y_mm": y, "height_mm": height,
                         "cursor_x": 0, "placements": 0}
                return {"new_shelf": shelf, "x": 0, "y": y,
                        "width": width, "height": height, "rotation": rotation}
        return None

    for piece in order:
        if not piece["allowed_rotations"]:
            unplaced.append({"piece_id": piece["piece_id"], "reason": "GRAIN_DIRECTION_CONFLICT"})
            continue
        selected = None
        sheet_index = -1
        for index, sheet in enumerate(sheets):
            selected = try_sheet(sheet, piece)
            if selected is not None:
                sheet_index = index
                break
        if selected is None and len(sheets) < _MAX_SHEETS:
            fresh = {"shelves": [], "placements": []}
            selected = try_sheet(fresh, piece)
            if selected is not None:
                sheets.append(fresh)
                sheet_index = len(sheets) - 1
        if selected is None:
            reason = ("SHEET_BUDGET_EXCEEDED" if len(sheets) >= _MAX_SHEETS
                      else "NO_LEGAL_ORIENTATION_FITS_USEFUL_ZONE")
            unplaced.append({"piece_id": piece["piece_id"], "reason": reason})
            continue
        sheet = sheets[sheet_index]
        if "new_shelf" in selected:
            sheet["shelves"].append(selected["new_shelf"])
            shelf = selected["new_shelf"]
        else:
            shelf = selected["shelf"]
        shelf["cursor_x"] = selected["x"] + selected["width"]
        shelf["placements"] += 1
        sheet["placements"].append({
            "piece_id": piece["piece_id"], "x_mm": selected["x"],
            "y_mm": selected["y"],
            "size_on_sheet_mm": [selected["width"], selected["height"]],
            "rotation_degrees": selected["rotation"],
            "nominal_area_mm2": piece["width_mm"] * piece["height_mm"],
        })
    return {"sheets": sheets, "unplaced": unplaced}


def _edge_review(modular: dict, physical: list[dict]) -> tuple[list[dict], int | None, list[str]]:
    details: list[dict] = []
    total: int | None = 0
    blockers: list[str] = []
    front_review = modular.get("wall_bar_review", {}).get("front_edgebanding_review", {})
    raw_status = front_review.get("raw_interpretation_scenario", {}).get("status")
    if raw_status == "INVALID_RAW_VS_FINISHED":
        blockers.append("RAW_VS_FINISHED_UNRESOLVED")
    existing_rows: dict[tuple[str, str], dict[str, Any]] = {}
    if modular.get("wall_bar_review"):
        try:
            from .wall_bar_sheets import edge_policy_rows
            existing_rows = {
                (row["piece_id"], row["face_edge"]): row
                for row in edge_policy_rows(modular)
            }
        except DesignError:
            existing_rows = {}
    for part in physical:
        edges = part.get("edgebanding_edges", "UNCONFIRMED")
        thickness = part.get("edgebanding_thickness_mm")
        explicit = (type(edges) is list and all(
            edge in {"x_min", "x_max", "y_min", "y_max"} for edge in edges))
        if explicit and type(thickness) is int and thickness > 0:
            nominal = part.get("edgebanding_nominal_total_mm")
            length = nominal if type(nominal) is int and nominal >= 0 else None
            if length is None:
                total = None
            elif total is not None:
                total += length
            rows = [existing_rows[(part["piece_id"], edge)]
                    for edge in edges if (part["piece_id"], edge) in existing_rows]
            labels = [row.get("conditional_candidate_policy") or row.get("edge_policy")
                      for row in rows]
            labels = [label for label in labels if isinstance(label, str)]
            classification = (";".join(sorted(set(labels)))
                              if labels else "DECLARED_SOURCE_NOT_APPROVED")
            edge_details = [{
                "edge": row["face_edge"],
                "classification": row.get("conditional_candidate_policy") or row.get("edge_policy"),
                "certainty": row.get("certainty"),
                "physical_edge_model": row.get("physical_edge_model"),
            } for row in rows]
        else:
            length = None
            classification = "UNCONFIRMED"
            edge_details = []
        if (explicit and edges and thickness == 2
                and part.get("finished_cut_dimensions_mm") is None):
            if "RAW_VS_FINISHED_UNRESOLVED" not in blockers:
                blockers.append("RAW_VS_FINISHED_UNRESOLVED")
        details.append({
            "piece_id": part["piece_id"],
            "edges": list(edges) if explicit else "UNCONFIRMED",
            "thickness_mm": thickness if explicit else None,
            "classification": classification,
            "source_review_status": front_review.get("status", "UNCONFIRMED"),
            "edge_details": edge_details,
            "nominal_length_mm": length,
            "approval": "NOT_APPROVED",
        })
    if not any(row["nominal_length_mm"] is not None for row in details):
        total = None
    return details, total, blockers


def _svg(sheets: list[dict[str, Any]]) -> str:
    if not sheets:
        return ""

    def illustrative_color(index: int) -> str:
        # Stable, separated pastel hues keyed only to catalog order. They are
        # visual labels for this review, never a selected commercial finish.
        hue = (index * 137.50776405) % 360 / 360
        red, green, blue = colorsys.hls_to_rgb(hue, 0.79, 0.58)
        return "#" + "".join(f"{round(channel * 255):02x}" for channel in (red, green, blue))

    scale = 0.30
    margin, label_h, gap, columns = 22, 30, 24, 2
    cell_w = max(s["format_mm"]["width_mm"] for s in sheets) * scale + 24
    legend_rows = max((len(s["placements"]) for s in sheets), default=0)
    legend_h = legend_rows * 11 + 18
    cell_h = (max(s["format_mm"]["length_mm"] for s in sheets) * scale
              + label_h + legend_h + 24)
    rows = math.ceil(len(sheets) / columns)
    width = margin * 2 + columns * cell_w + (columns - 1) * gap
    height = margin * 2 + rows * cell_h + (rows - 1) * gap
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<text x="22" y="19" font-family="sans-serif" font-size="15" font-weight="700">SIMULACIÓN NOMINAL · NO ES PLANO DE SIERRA · TONOS SOLO ILUSTRATIVOS</text>',
    ]
    board_colors: dict[str, str] = {}
    for index, sheet in enumerate(sheets):
        col, row = index % columns, index // columns
        x0 = margin + col * (cell_w + gap)
        y0 = margin + row * (cell_h + gap)
        width_px = sheet["format_mm"]["width_mm"] * scale
        height_px = sheet["format_mm"]["length_mm"] * scale
        board_label = escape(
            f'{sheet["board_id"]} · {sheet["reference"]} · {sheet["decoration"]}',
            quote=True)
        board_id = str(sheet["board_id"])
        if board_id not in board_colors:
            board_colors[board_id] = illustrative_color(len(board_colors))
        chunks.append(
            f'<text x="{x0:.1f}" y="{y0+12:.1f}" font-family="sans-serif" font-size="10">{board_label} · lámina {sheet["sheet_ordinal"]}</text>')
        sx, sy = x0, y0 + label_h
        chunks.append(
            f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{width_px:.1f}" height="{height_px:.1f}" fill="#fafafa" stroke="#111" stroke-width="1.4"/>')
        for piece_index, item in enumerate(sheet["placements"], start=1):
            px = sx + item["board_origin_xy_mm"][0] * scale
            py = sy + (sheet["format_mm"]["length_mm"] - item["board_origin_xy_mm"][1] - item["size_on_sheet_mm"][1]) * scale
            pw, ph = (v * scale for v in item["size_on_sheet_mm"])
            chunks.append(
                f'<rect data-board-id="{escape(board_id, quote=True)}" x="{px:.1f}" y="{py:.1f}" width="{pw:.1f}" height="{ph:.1f}" fill="{board_colors[board_id]}" stroke="#30445a" stroke-width="0.8"/>')
            if pw >= 14 and ph >= 14:
                chunks.append(
                    f'<text x="{px+pw/2:.1f}" y="{py+ph/2+3:.1f}" text-anchor="middle" font-family="sans-serif" font-size="9" font-weight="700">{piece_index}</text>')
            nominal = "×".join(str(n) for n in item["nominal_size_mm"])
            legend_y = sy + height_px + 14 + (piece_index - 1) * 11
            piece_label = escape(item["piece_id"], quote=True)
            chunks.append(
                f'<text x="{x0+2:.1f}" y="{legend_y:.1f}" font-family="sans-serif" font-size="8">{piece_index}. {piece_label} · {nominal} mm · giro {item["rotation_degrees"]}°</text>')
    chunks.append("</svg>")
    return "".join(chunks)


def build_board_plan_review(request: Any) -> dict[str, Any]:
    """Plan nominal rectangles from a fresh Maestro model through existing MCP."""
    request = _object(request, "solicitud_json")
    _extra_keys(request, _ROOT_KEYS, "board_plan_nominal")
    if request.get("review_kind") != "board_plan_nominal":
        raise _invalid("Tipo de revisión nominal desconocido.")
    if "source_request" not in request:
        raise _invalid("source_request es obligatorio; no se acepta CAD/CSV suministrado por el cliente.")
    source_request = _validate_source_request(request["source_request"])
    try:
        maestro = consult_maestro(source_request, bundle_dir=None)
    except MaestroError:
        raise
    modular = maestro.get("modular") if type(maestro) is dict else None
    if (type(modular) is not dict
            or modular.get("status") != "DRAFT_NOT_FOR_CUTTING"):
        return _blocked("CONCEPT_ONLY", blockers=["UNSUPPORTED_SOURCE: Maestro no devolvió un borrador dimensional."])
    try:
        cad = cad_exchange(modular)
        physical, concepts = _validate_maestro_cad(modular, cad)
    except (DesignError, MaestroError) as exc:
        return _blocked("CONCEPT_ONLY", blockers=["UNSUPPORTED_SOURCE: " + str(exc)])

    ids = [part["piece_id"] for part in physical]
    concept_ids = [part["piece_id"] for part in concepts]
    result = _blocked(
        "NEEDS_MATERIAL_CONFIRMATION", geometry_sha=cad["geometry_sha256"],
        piece_ids=ids, concept_ids=concept_ids,
    )
    result["cad_part_source_match"] = True
    result["source_part_count"] = len(modular["parts"])
    result["physical_piece_count"] = len(physical)
    result["source_status"] = modular["status"]

    boards, board_missing = _catalog(request.get("board_catalog"))
    assignments, assignment_missing = _assignments(
        request.get("piece_assignments"), physical, boards)
    allowances, allowance_missing = _allowances(request.get("machine_allowances"), boards)
    if board_missing or assignment_missing:
        result["status"] = "NEEDS_MATERIAL_CONFIRMATION"
        result["review_blockers"] = board_missing + assignment_missing
        result["missing_material_inputs"] = result["review_blockers"]
        return result
    if allowance_missing or allowances is None:
        result["status"] = "NEEDS_MACHINE_INPUT"
        result["review_blockers"] = allowance_missing
        return result

    board_by_id = {board["board_id"]: board for board in boards}
    incompatible: list[dict[str, Any]] = []
    grain_conflicts: list[dict[str, str]] = []
    for part in physical:
        assignment = assignments[part["piece_id"]]
        board = board_by_id[assignment["board_id"]]
        source_material = _material_signature(part)
        if (source_material is None
                or source_material != (board["substrate"], board["thickness_mm"])):
            incompatible.append({
                "piece_id": part["piece_id"], "source_material_id": part.get("material_id"),
                "source_thickness_mm": part.get("thickness_mm"),
                "board_id": board["board_id"], "board_substrate": board["substrate"],
                "board_thickness_mm": board["thickness_mm"],
            })
            continue
        if (assignment["grain_axis"] != "none"
                and board["grain_direction"] == "none"):
            grain_conflicts.append({"piece_id": part["piece_id"],
                                    "reason": "DIRECTIONAL_GRAIN_WITH_UNGRAINED_BOARD"})
    if incompatible:
        result["status"] = "BLOCKED_INCOMPATIBLE_STOCK"
        result["review_blockers"] = ["BLOCKED_INCOMPATIBLE_STOCK"]
        result["incompatible_stock"] = incompatible
        return result
    if grain_conflicts:
        result["status"] = "BLOCKED_INCOMPATIBLE_STOCK"
        result["review_blockers"] = ["GRAIN_DIRECTION_INCOMPATIBLE_WITH_BOARD"]
        result["unplaced"] = grain_conflicts
        return result

    continuity = any(row["continuity_group"] is not None for row in assignments.values())
    result["continuity_status"] = "CONTINUITY_NOT_VERIFIED" if continuity else "NOT_REQUESTED"
    result["customer_finish_confirmation"] = "PENDING"
    result["machine_allowances_mm"] = dict(allowances)
    edge_review, total_edge_length, edge_blockers = _edge_review(modular, physical)
    result["edgebanding_review"] = edge_review
    result["edgebanding_nominal_length_mm"] = total_edge_length
    result["review_blockers"] = edge_blockers

    part_by_id = {part["piece_id"]: part for part in physical}
    cad_by_id = {box["piece_id"]: box for box in cad["boxes"]}
    plan_by_board: list[dict[str, Any]] = []
    all_sheets: list[dict[str, Any]] = []
    all_unplaced: list[dict[str, str]] = []
    for board in boards:
        board_assignments = [assignment for assignment in assignments.values()
                             if assignment["board_id"] == board["board_id"]]
        if not board_assignments:
            continue
        board_pieces: list[dict[str, Any]] = []
        for assignment in board_assignments:
            part = part_by_id[assignment["piece_id"]]
            width = part["nominal_face_x_mm"]
            height = part["nominal_face_y_mm"]
            rotations = [rotation for rotation in (0, 90)
                         if _orientation_allowed(assignment["grain_axis"], rotation,
                                                 board["grain_direction"])]
            board_pieces.append({
                "piece_id": part["piece_id"], "width_mm": width,
                "height_mm": height, "allowed_rotations": rotations,
            })
        packed = _pack_rectangles(board_pieces, board, allowances)
        unplaced_ids = {item["piece_id"] for item in packed["unplaced"]}
        all_unplaced.extend(packed["unplaced"])
        useful_width = board["width_mm"] - allowances["trim_left_mm"] - allowances["trim_right_mm"]
        useful_length = board["length_mm"] - allowances["trim_top_mm"] - allowances["trim_bottom_mm"]
        useful_area = useful_width * useful_length
        assigned_area = sum(p["width_mm"] * p["height_mm"] for p in board_pieces)
        sheets_for_board: list[dict[str, Any]] = []
        for ordinal, raw_sheet in enumerate(packed["sheets"], start=1):
            placements: list[dict[str, Any]] = []
            for item in raw_sheet["placements"]:
                part = part_by_id[item["piece_id"]]
                assignment = assignments[item["piece_id"]]
                plane = part["face_plane"]
                rotation = item["rotation_degrees"]
                grain_axis = assignment["grain_axis"]
                sheet_grain_axis = ("none" if grain_axis == "none" else
                                    ("x" if grain_axis == "face_x" else "y"))
                if rotation == 90 and sheet_grain_axis != "none":
                    sheet_grain_axis = "y" if sheet_grain_axis == "x" else "x"
                box = cad_by_id[item["piece_id"]]
                placements.append({
                    "piece_id": item["piece_id"], "role": part["role"],
                    "board_id": board["board_id"],
                    "material_id": part["material_id"],
                    "nominal_size_mm": [part["nominal_face_x_mm"], part["nominal_face_y_mm"]],
                    "size_on_sheet_mm": item["size_on_sheet_mm"],
                    "rotation_degrees": rotation,
                    "useful_zone_origin_xy_mm": [item["x_mm"], item["y_mm"]],
                    "board_origin_xy_mm": [
                        allowances["trim_left_mm"] + item["x_mm"],
                        allowances["trim_bottom_mm"] + item["y_mm"],
                    ],
                    "grain_axis_input": grain_axis,
                    "grain_axis_world_candidate": _face_axis_to_world(plane, grain_axis),
                    "source_grain_world_axis": box["grain_world_axis"],
                    "grain_axis_on_sheet": sheet_grain_axis,
                    "grain_assignment_status": (
                        "OWNER_INPUT_UNAUTHENTICATED" if part["grain_axis"] == "UNCONFIRMED"
                        else "MATCHES_MAESTRO_CONFIRMED"),
                    "nominal_area_mm2": item["nominal_area_mm2"],
                    "continuity_group": assignment["continuity_group"],
                })
            sheet_area = board["length_mm"] * board["width_mm"]
            nominal_area = sum(p["nominal_area_mm2"] for p in placements)
            kerf_area = sum(
                max(0, shelf["placements"] - 1) * allowances["kerf_mm"] * shelf["height_mm"]
                for shelf in raw_sheet["shelves"]
            ) + max(0, len(raw_sheet["shelves"]) - 1) * allowances["kerf_mm"] * useful_width
            remnant = useful_area - nominal_area - kerf_area
            if remnant < 0:
                raise _invalid("El cálculo de áreas de la simulación nominal es inconsistente.")
            sheet = {
                "board_id": board["board_id"], "supplier": board["supplier"],
                "reference": board["reference"], "decoration": board["decoration"],
                "substrate": board["substrate"], "thickness_mm": board["thickness_mm"],
                "sheet_ordinal": ordinal,
                "format_mm": {"length_mm": board["length_mm"], "width_mm": board["width_mm"]},
                "useful_zone_mm": {
                    "origin": "lower_left_of_usable_zone",
                    "physical_origin_transform_mm": [allowances["trim_left_mm"], allowances["trim_bottom_mm"]],
                    "width_mm": useful_width, "length_mm": useful_length,
                },
                "physical_origin_transform_mm": [allowances["trim_left_mm"], allowances["trim_bottom_mm"]],
                "placements": placements,
                "sheet_area_mm2": sheet_area,
                "usable_area_mm2": useful_area,
                "nominal_piece_area_mm2": nominal_area,
                "kerf_separation_area_estimate_mm2": kerf_area,
                "geometric_remnant_area_mm2": remnant,
                "trim_waste_area_mm2": sheet_area - useful_area,
                "cut_sequence_status": "CUT_SEQUENCE_NOT_VERIFIED",
            }
            sheets_for_board.append(sheet)
            all_sheets.append(sheet)
        board_area = sum(
            part_by_id[item["piece_id"]]["nominal_face_x_mm"] *
            part_by_id[item["piece_id"]]["nominal_face_y_mm"]
            for item in board_assignments)
        lower_bound = {
            "nominal_piece_area_mm2": board_area,
            "usable_area_per_sheet_mm2": useful_area,
            "minimum_sheet_count_area_only": math.ceil(board_area / useful_area),
            "meaning": "Límite inferior por área; no demuestra que las piezas quepan ni que sea óptimo.",
        }
        plan_by_board.append({
            "board_id": board["board_id"], "supplier": board["supplier"],
            "reference": board["reference"], "decoration": board["decoration"],
            "substrate": board["substrate"], "thickness_mm": board["thickness_mm"],
            "piece_ids": [item["piece_id"] for item in board_assignments],
            "nominal_piece_area_mm2": board_area,
            "area_lower_bound": lower_bound,
            "estimated_nominal_sheet_count": None,
        })

    fully_placed = not all_unplaced and sum(
        len(sheet["placements"]) for sheet in all_sheets) == len(physical)
    result["sheets"] = all_sheets
    result["by_board"] = plan_by_board
    result["area_lower_bound"] = [row["area_lower_bound"] for row in plan_by_board]
    result["unplaced"] = all_unplaced
    result["algorithm"] = "FIXED_ORDER_FIRST_FIT_SHELVES"
    result["rotation_policy"] = "0_OR_90_ONLY_IF_ASSIGNED_GRAIN_AXIS_MATCHES_BOARD_DIRECTION"
    result["review_blockers"] = list(dict.fromkeys(result["review_blockers"]))
    if fully_placed:
        count = len(all_sheets)
        result["status"] = "BOARD_PLAN_REVIEW_ONLY"
        result["estimated_nominal_sheet_count"] = count
        result["estimated_total_sheet_count"] = count
        by_board_counts = {
            board["board_id"]: sum(1 for sheet in all_sheets
                                  if sheet["board_id"] == board["board_id"])
            for board in boards
        }
        for row in plan_by_board:
            row["estimated_nominal_sheet_count"] = by_board_counts[row["board_id"]]
        result["review_blockers"].append("CUT_SEQUENCE_NOT_VERIFIED")
        if result["review_blockers"] and "RAW_VS_FINISHED_UNRESOLVED" in result["review_blockers"]:
            result["cutting_dimensions_authorized"] = False
    else:
        result["status"] = "BLOCKED_UNPLACED"
        result["estimated_nominal_sheet_count"] = None
        result["estimated_total_sheet_count"] = None
        for row in plan_by_board:
            row["estimated_nominal_sheet_count"] = None
        result["review_blockers"].append("BLOCKED_UNPLACED")
    result["sketch_svg"] = _svg(all_sheets)
    result["assumptions"] = [
        "Catálogo y veta son entradas declaradas para QA; no validan proveedor, stock ni compra.",
        "Las dimensiones colocadas son caras nominales de Maestro; no son medidas de corte.",
        "La heurística por estantes no garantiza mínimo global ni secuencia guillotina.",
        "Veta y continuidad declaradas no están autenticadas ni verificadas en tablero físico.",
    ]
    result["saw_dimensions_mm"] = None
    return result
