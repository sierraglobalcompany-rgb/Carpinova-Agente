"""F6: compose OPEN rectangular carcasses with explicit grain and edging.

This is intentionally NOT a full closet/kitchen solver. It reuses F1 design()
for every panel dimension, then gives each physical board an identity,
front-view/space origin and nonproduction finishing metadata.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from .core import DesignError, design
from .back_panels import back_panels

ROLES = ("left_side", "right_side", "top", "bottom")
EDGES = frozenset(("x_min", "x_max", "y_min", "y_max"))
GRAIN_AXES = frozenset(("face_x", "face_y", "none"))
APPLICATIONS = frozenset(("closet", "kitchen", "cabinet_run"))
INSTALLATIONS = frozenset(("built_in", "freestanding", "wall_mounted"))
ROOT_FIELDS = frozenset(("type", "application", "width_mm", "height_mm",
                         "depth_mm", "installation", "site_width_mm", "modules"))
MODULE_FIELDS = frozenset(("module_id", "width_mm", "panel_thickness_mm",
                           "material_id", "construction", "fronts", "back",
                           "support", "finish"))
FINISH_FIELDS = frozenset(("grain", "edgebanding", "edgeband_thickness_mm"))
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DesignError(f"{name} debe ser objeto JSON.")
    return value


def _exact(value: dict[str, Any], permitted: frozenset[str], name: str) -> None:
    extra = value.keys() - permitted
    if extra:
        raise DesignError(f"{name}: campos desconocidos: {', '.join(sorted(extra))}.")


def _positive(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise DesignError(f"{name}: se requiere entero positivo en milímetros.")
    return value


def _choice(value: Any, choices: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise DesignError(f"{name}: elegir uno de {', '.join(sorted(choices))}.")
    return value


def _finish(value: Any, module_id: str) -> dict[str, Any] | None:
    if value is None:
        return None
    finish = _object(value, f"{module_id}.finish")
    _exact(finish, FINISH_FIELDS, f"{module_id}.finish")
    if "grain" not in finish or "edgebanding" not in finish:
        raise DesignError(f"{module_id}: acabado parcial; incluir grain y edgebanding de las cuatro piezas.")
    grain = _object(finish["grain"], "finish.grain")
    band = _object(finish["edgebanding"], "finish.edgebanding")
    if set(grain) != set(ROLES) or set(band) != set(ROLES):
        raise DesignError(f"{module_id}: grain y edgebanding deben indicar exactamente {', '.join(ROLES)}.")
    for role in ROLES:
        _choice(grain[role], GRAIN_AXES, f"{module_id}.grain.{role}")
        edges = band[role]
        if not isinstance(edges, list) or any(
                not isinstance(edge, str) or edge not in EDGES for edge in edges):
            raise DesignError(f"{module_id}.edgebanding.{role}: usar lista de lados conocidos.")
        if len(set(edges)) != len(edges):
            raise DesignError(f"{module_id}.edgebanding.{role}: bordes duplicados.")
    has_edges = any(band[role] for role in ROLES)
    thickness = finish.get("edgeband_thickness_mm")
    if has_edges:
        _positive(thickness, f"{module_id}.edgeband_thickness_mm")
    elif thickness is not None:
        raise DesignError(f"{module_id}: no se indicó ningún borde para el espesor de tapacanto.")
    return finish


def _site_check(spec: dict[str, Any], width: int) -> dict[str, Any]:
    measurement = spec.get("site_width_mm")
    if measurement is None:
        return {
            "complete": False, "values_mm": None, "minimum_mm": None,
            "variation_mm": None, "conflict": False,
        }
    site = _object(measurement, "site_width_mm")
    if set(site) != {"top", "middle", "bottom"}:
        raise DesignError("site_width_mm debe incluir top, middle y bottom.")
    values = {key: _positive(site[key], f"site_width_mm.{key}")
              for key in ("top", "middle", "bottom")}
    shortest = min(values.values())
    return {
        "complete": True, "values_mm": values, "minimum_mm": shortest,
        "variation_mm": max(values.values()) - shortest,
        "nominal_gap_at_narrowest_mm": shortest - width,
        "conflict": width >= shortest,
    }


def design_modular_run(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Return documented nominal carcasses, always blocking cut/installation."""
    d = _object(spec, "proyecto")
    _exact(d, ROOT_FIELDS, "proyecto")
    if d.get("type") != "modular_run":
        raise DesignError("type debe ser modular_run.")
    _choice(d.get("application"), APPLICATIONS, "application")
    installation = _choice(d.get("installation"), INSTALLATIONS, "installation")
    width = _positive(d.get("width_mm"), "width_mm")
    height = _positive(d.get("height_mm"), "height_mm")
    depth = _positive(d.get("depth_mm"), "depth_mm")
    site = _site_check(d, width)
    modules = d.get("modules")
    if not isinstance(modules, list) or not 1 <= len(modules) <= 12:
        raise DesignError("modules: se requieren entre 1 y 12 módulos.")
    widths: list[int] = []
    prepared: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    seen: set[str] = set()
    for i, item in enumerate(modules):
        module = _object(item, f"modules[{i}]")
        _exact(module, MODULE_FIELDS, f"modules[{i}]")
        module_id = module.get("module_id")
        if (not isinstance(module_id, str) or not NAME_RE.fullmatch(module_id)
                or module_id in seen):
            raise DesignError(f"modules[{i}].module_id debe ser identificador único.")
        seen.add(module_id)
        w = _positive(module.get("width_mm"), f"{module_id}.width_mm")
        _positive(module.get("panel_thickness_mm"), f"{module_id}.panel_thickness_mm")
        material = module.get("material_id")
        if not isinstance(material, str) or not NAME_RE.fullmatch(material):
            raise DesignError(f"{module_id}: material_id debe ser identificador seguro y no vacío.")
        if module.get("construction") not in ("sides_full", "top_bottom_full"):
            raise DesignError(f"{module_id}: estructura no admitida.")
        if module.get("fronts") not in ("none", "pending"):
            raise DesignError(f"{module_id}: indicar fronts=none o pending.")
        if module.get("back") not in ("none", "pending") and not isinstance(module.get("back"), dict):
            raise DesignError(f"{module_id}: back requiere none, pending u objeto documentado.")
        if module.get("support") not in ("floor", "wall", "pending"):
            raise DesignError(f"{module_id}: indicar support=floor, wall o pending.")
        prepared.append((module, _finish(module.get("finish"), module_id)))
        widths.append(w)

    total = sum(widths)
    blockers = [
        "Paneles nominales: sin compensación por tapacantos, sierra, cola o mecanizado.",
        "Verificar cara vista, vetas, cantos, uniones, cargas, vuelco y anclajes.",
        "No hay puertas, cajones, patas, zócalo ni taladros de producción modelados; fondos solo por especificación explícita.",
    ]
    if total != width:
        blockers.insert(
            0, f"Los módulos suman {total} mm frente a ancho objetivo {width} mm: "
               "definir anchos o módulos explícitos. No se crea un relleno supuesto."
        )
        return {
            "schema_version": "0.1.0", "type": "modular_run",
            "application": d["application"], "status": "NEEDS_LAYOUT_REVISION",
            "fabrication_ready": False, "cutting_ready": False,
            "drilling_ready": False, "purchase_ready": False,
            "parts": [], "modules": [], "total_module_width_mm": total,
            "run_width_mm": width, "site": site, "blockers": blockers,
        }
    status = "DRAFT_NOT_FOR_CUTTING"
    if site["conflict"] and installation == "built_in":
        status = "SITE_CONFLICT"
        blockers.insert(0, "Ancho igual o mayor que la menor luz del espacio; rediseñar.")
    if installation == "built_in" and not site["complete"]:
        status = "NEEDS_SITE_MEASUREMENTS"
        blockers.insert(0, "Tomar los tres anchos del hueco (arriba, medio, abajo).")

    all_parts: list[dict[str, Any]] = []
    out_modules: list[dict[str, Any]] = []
    x_offset = 0
    for module, finish in prepared:
        w, t = module["width_mm"], module["panel_thickness_mm"]
        geometry = design({
            "type": "cabinet", "width_mm": w,
            "height_mm": height, "depth_mm": depth,
            "panel_thickness_mm": t, "construction": module["construction"],
        })
        sides, caps = geometry["parts"]
        for role in ROLES:
            part = sides if role.endswith("side") else caps
            if module["construction"] == "sides_full":
                y_origin = 0 if role.endswith("side") else (height - t if role == "top" else 0)
            else:
                y_origin = t if role.endswith("side") else (height - t if role == "top" else 0)
            x_origin = x_offset + (w-t if role == "right_side" else 0)
            if role in ("top", "bottom") and module["construction"] == "sides_full":
                x_origin += t
            grain = finish["grain"][role] if finish else "UNCONFIRMED"
            banded = sorted(finish["edgebanding"][role]) if finish else []
            band_length = sum(
                part["face_y_mm"] if edge.startswith("x_") else part["face_x_mm"]
                for edge in banded
            ) if finish else None
            all_parts.append({
                "piece_id": module["module_id"] + "-" + role.upper(),
                "module_id": module["module_id"], "role": role,
                "material_id": module["material_id"], "nominal_face_x_mm": part["face_x_mm"],
                "nominal_face_y_mm": part["face_y_mm"],
                "thickness_mm": t,
                "grain_axis": grain,
                "face_plane": "YZ" if role.endswith("side") else "XZ",
                "nominal_origin_xyz_mm": [x_origin, y_origin, 0],
                "edgebanding_edges": banded if finish else "UNCONFIRMED",
                "edgebanding_thickness_mm":
                    finish.get("edgeband_thickness_mm") if finish else None,
                "edgebanding_nominal_total_mm": band_length,
                "finished_cut_dimensions_mm": None,
                "source_engine": "F1_CORE_CABINET",
                "source_formula": part["calculation"],
            })
        rear_parts, rear_blockers = back_panels(
            module["back"], module_id=module["module_id"],
            module_height_mm=height, module_depth_mm=depth,
            clear_width_mm=geometry["dimensions"]["clear_width_mm"],
            clear_height_mm=geometry["dimensions"]["clear_height_mm"],
            carcase_thickness_mm=t, start_x_mm=x_offset,
        )
        all_parts.extend(rear_parts)
        blockers.extend(rear_blockers)
        if finish is None:
            blockers.append(f"{module['module_id']}: definir veta y cuatro lados de canto por pieza.")
        if module["fronts"] == "pending":
            blockers.append(f"{module['module_id']}: definir puertas/frentes y sus holguras.")
        if module["back"] == "pending":
            blockers.append(f"{module['module_id']}: definir fondo, ranura o panel aplicado.")
        if module["support"] == "pending":
            blockers.append(f"{module['module_id']}: definir fijación/soporte.")
        out_modules.append({
            "module_id": module["module_id"], "start_x_mm": x_offset,
            "external_width_mm": w, "external_height_mm": height,
            "external_depth_mm": depth, "clear_width_mm": geometry["dimensions"]["clear_width_mm"],
            "clear_height_mm": geometry["dimensions"]["clear_height_mm"],
            "construction": module["construction"], "part_ids":
                [module["module_id"] + "-" + role.upper() for role in ROLES] +
                [piece["piece_id"] for piece in rear_parts],
            "panel_thickness_mm": t, "fronts": module["fronts"],
            "back": module["back"], "support": module["support"],
        })
        x_offset += w
    if installation == "wall_mounted":
        blockers.insert(0, "Mueble suspendido: carga, muro y anclajes requieren cálculo competente.")
    blockers.append("La unión entre módulos y los apoyos entre cuerpos aún no están diseñados.")
    return {
        "schema_version": "0.1.0", "type": "modular_run",
        "application": d["application"], "status": status,
        "fabrication_ready": False, "cutting_ready": False, "drilling_ready": False,
        "purchase_ready": False,
        "dimensions_mm": {"width": width, "height": height, "depth": depth},
        "installation": installation, "site": site, "modules": out_modules,
        "parts": all_parts, "piece_count": len(all_parts),
        "total_module_width_mm": x_offset, "blockers": blockers,
        "conventions": {
            "axes": "X derecha (ancho), Y arriba (alto), Z atrás (profundidad)",
            "face_x": "longitud de cara sobre eje físico indicado por face_plane",
            "face_y": "anchura de cara sobre el otro eje físico de face_plane",
            "edgebanding": "longitud nominal, sin margen de merma ni compensación de corte",
            "independent_carcase_sides": True,
        },
    }
