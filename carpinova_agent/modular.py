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
from .front_panels import front_panels, check_adjacent_fronts
from .drawer_modules import module_drawers, propose_drawer_layout
from .cad_exchange import nominal_front_extension_mm

ROLES = ("left_side", "right_side", "top", "bottom")
EDGES = frozenset(("x_min", "x_max", "y_min", "y_max"))
GRAIN_AXES = frozenset(("face_x", "face_y", "none"))
APPLICATIONS = frozenset(("closet", "kitchen", "cabinet_run"))
INSTALLATIONS = frozenset(("built_in", "freestanding", "wall_mounted"))
ROOT_FIELDS = frozenset(("type", "application", "width_mm", "height_mm",
                         "depth_mm", "installation", "site_width_mm", "modules",
                         "max_assembled_depth_mm"))
MODULE_FIELDS = frozenset(("module_id", "width_mm", "panel_thickness_mm",
                           "material_id", "construction", "fronts", "back",
                           "support", "finish", "drawers",
                           "drawer_layout_reference", "support_concept",
                           "horizontal_divider", "countertop",
                           "upper_support", "vertical_divider"))
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


def _check_drawer_layout_reference(
    module: dict[str, Any], *, module_height_mm: int, module_depth_mm: int
) -> None:
    """Compare real drawer coordinates to the exact consulted F1 proposal.

    This is a consistency guard, NOT cryptographic proof of user approval.
    Legacy modules without a reference keep their original behavior.
    """
    if "drawer_layout_reference" not in module:
        return
    proposed = propose_drawer_layout(module["drawer_layout_reference"])
    expected_dims = {"width": module["width_mm"],
                     "height": module_height_mm, "depth": module_depth_mm}
    if (proposed["external_dimensions_mm"] != expected_dims
            or proposed["panel_thickness_mm"] != module["panel_thickness_mm"]
            or proposed["construction"] != module["construction"]):
        raise DesignError(
            f"{module['module_id']}: la distribución consultada corresponde "
            "a otra carcasa; volver a consultar Maestro antes de CAD."
        )
    drawers = module.get("drawers")
    plan = proposed["opening_plan"]
    if type(drawers) is not list or len(drawers) != len(plan):
        raise DesignError(
            f"{module['module_id']}: cantidad de cajones diferente de la "
            "propuesta revisada; volver a confirmar."
        )
    for index, (drawer, opening) in enumerate(zip(drawers, plan)):
        if type(drawer) is not dict or any(
            type(drawer.get(field)) is not (str if field == "drawer_id" else int)
            or drawer[field] != opening[field]
            for field in ("drawer_id", "opening_bottom_offset_mm",
                          "opening_height_mm")
        ):
            raise DesignError(
                f"{module['module_id']}.drawers[{index}]: ID, altura o "
                "posición cambiaron respecto al plan consultado."
            )


SUPPORT_STYLES = frozenset(("floor_direct", "legs", "plinth", "wall_mounted"))
SUPPORT_CONCEPT_FIELDS = frozenset(
    ("style", "support_height_mm", "overall_height_mm"))


def _support_concept(
    value: Any, *, module_id: str, carcass_height_mm: int,
    existing_support: str, installation: str,
    countertop_thickness_mm: int = 0,
) -> dict[str, Any]:
    """Preserve confirmed review geometry; never synthesize support parts."""
    data = _object(value, f"{module_id}.support_concept")
    if set(data) != SUPPORT_CONCEPT_FIELDS:
        raise DesignError(
            f"{module_id}.support_concept: especificar style, "
            "support_height_mm y overall_height_mm; ningún otro campo."
        )
    style = _choice(data["style"], SUPPORT_STYLES, f"{module_id}.support_concept.style")
    height = data["support_height_mm"]
    if type(height) is not int or height < 0:
        raise DesignError(f"{module_id}: altura de patas/zócalo inválida.")
    total = _positive(data["overall_height_mm"], f"{module_id}.overall_height_mm")
    if style in ("legs", "plinth"):
        if height == 0:
            raise DesignError(f"{module_id}: patas/zócalo necesitan altura positiva.")
    elif height != 0:
        raise DesignError(f"{module_id}: sin patas o suspendido exige altura AP cero.")
    if carcass_height_mm + height + countertop_thickness_mm != total:
        raise DesignError(
            f"{module_id}: alto total no coincide con carcasa, apoyo y cubierta; "
            "volver a revisar distribución de cajones."
        )
    expected_support = "wall" if style == "wall_mounted" else "floor"
    if existing_support != expected_support:
        raise DesignError(f"{module_id}: support y support_concept se contradicen.")
    if (installation == "wall_mounted") != (style == "wall_mounted"):
        raise DesignError(
            f"{module_id}: el apoyo declarado contradice installation."
        )
    return {
        "style": style, "support_height_mm": height,
        "carcass_height_mm": carcass_height_mm, "overall_height_mm": total,
        **({"countertop_thickness_mm": countertop_thickness_mm}
           if countertop_thickness_mm else {}),
        "physical_support_parts": None,
        "physical_support_specification": "NOT_VERIFIED",
        "fabrication_ready": False,
    }


def _countertop(value: Any, *, module_id: str, module_width_mm: int,
                module_depth_mm: int) -> dict[str, Any] | None:
    if value is None:
        return None
    data = _object(value, f"{module_id}.countertop")
    required = frozenset(("material_id", "thickness_mm", "width_mm", "depth_mm",
                          "left_overhang_mm", "right_overhang_mm",
                          "front_overhang_mm", "rear_overhang_mm"))
    allowed = required | {"finish_note"}
    _exact(data, allowed, f"{module_id}.countertop")
    if required - data.keys():
        raise DesignError(f"{module_id}.countertop: faltan cotas o material explícitos.")
    material = data["material_id"]
    if not isinstance(material, str) or not NAME_RE.fullmatch(material):
        raise DesignError(f"{module_id}.countertop.material_id inválido.")
    for field in ("thickness_mm", "width_mm", "depth_mm"):
        _positive(data[field], f"{module_id}.countertop.{field}")
    for field in ("left_overhang_mm", "right_overhang_mm",
                  "front_overhang_mm", "rear_overhang_mm"):
        if type(data[field]) is not int or data[field] < 0:
            raise DesignError(f"{module_id}.countertop.{field}: milímetros enteros no negativos.")
    if (data["width_mm"] != module_width_mm + data["left_overhang_mm"]
            + data["right_overhang_mm"]):
        raise DesignError(f"{module_id}.countertop: ancho y vuelos laterales no cierran.")
    if (data["depth_mm"] != module_depth_mm + data["front_overhang_mm"]
            + data["rear_overhang_mm"]):
        raise DesignError(f"{module_id}.countertop: fondo y vuelos frontal/trasero no cierran.")
    finish_note = data.get("finish_note", "")
    if type(finish_note) is not str or len(finish_note) > 240:
        raise DesignError(f"{module_id}.countertop.finish_note inválida.")
    return {**data, "finish_note": finish_note}


def _upper_support(value: Any, *, module_id: str, countertop: Any,
                   construction: str, module_depth_mm: int,
                   module_height_mm: int,
                   panel_thickness_mm: int) -> dict[str, Any] | None:
    """Validate the coffee-only, three-upright-tie review option."""
    if value is None:
        return None
    data = _object(value, f"{module_id}.upper_support")
    fields = frozenset(("style", "tie_height_mm", "tie_height_status"))
    _exact(data, fields, f"{module_id}.upper_support")
    if set(data) != fields:
        raise DesignError(
            f"{module_id}.upper_support: especificar style, tie_height_mm "
            "y tie_height_status; ningún valor se infiere."
        )
    if data["style"] != "coffee_three_upright_ties":
        raise DesignError(f"{module_id}.upper_support.style no admitido.")
    if countertop is None:
        raise DesignError(
            f"{module_id}.upper_support requiere un mesón independiente explícito."
        )
    if construction != "sides_full":
        raise DesignError(
            f"{module_id}.upper_support requiere construction=sides_full; "
            "no combinar juntas F1 distintas."
        )
    tie_height = _positive(data["tie_height_mm"],
                           f"{module_id}.upper_support.tie_height_mm")
    if 2 * panel_thickness_mm > module_depth_mm:
        raise DesignError(
            f"{module_id}.upper_support: los travesaños delantero y trasero "
            "se solaparían en profundidad."
        )
    if 2 * tie_height + panel_thickness_mm > module_height_mm:
        raise DesignError(
            f"{module_id}.upper_support: correas superiores e inferior "
            "se solaparían en altura."
        )
    height_status = _choice(
        data["tie_height_status"],
        frozenset(("REVIEW_HEIGHT_HYPOTHESIS_ONLY",)),
        f"{module_id}.upper_support.tie_height_status",
    )
    return {"style": "coffee_three_upright_ties",
            "tie_height_mm": tie_height,
            "tie_height_status": height_status}


def _horizontal_divider(value: Any, *, module_id: str,
                        module_depth_mm: int) -> dict[str, Any] | None:
    if value is None:
        return None
    data = _object(value, f"{module_id}.horizontal_divider")
    required = frozenset(("material_id", "thickness_mm",
                          "position_from_clear_bottom_mm", "depth_mm",
                          "depth_from_front_mm"))
    _exact(data, required, f"{module_id}.horizontal_divider")
    material = data["material_id"]
    if not isinstance(material, str) or not NAME_RE.fullmatch(material):
        raise DesignError(f"{module_id}.horizontal_divider.material_id inválido.")
    _positive(data["thickness_mm"], f"{module_id}.horizontal_divider.thickness_mm")
    _positive(data["depth_mm"], f"{module_id}.horizontal_divider.depth_mm")
    for field in ("position_from_clear_bottom_mm", "depth_from_front_mm"):
        if type(data[field]) is not int or data[field] < 0:
            raise DesignError(f"{module_id}.horizontal_divider.{field}: milímetros enteros no negativos.")
    if data["depth_from_front_mm"] + data["depth_mm"] > module_depth_mm:
        raise DesignError(f"{module_id}.horizontal_divider: excede el fondo de carcasa.")
    return data


def _vertical_divider(value: Any, *, module_id: str,
                      module_depth_mm: int) -> dict[str, Any] | None:
    if value is None:
        return None
    data = _object(value, f"{module_id}.vertical_divider")
    required = frozenset((
        "material_id", "thickness_mm", "position_from_clear_left_mm",
        "depth_mm", "depth_from_front_mm",
    ))
    _exact(data, required, f"{module_id}.vertical_divider")
    if set(data) != required:
        raise DesignError(
            f"{module_id}.vertical_divider: indicar material, espesor, "
            "posición, profundidad y retiro frontal; no se infieren."
        )
    if (not isinstance(data["material_id"], str)
            or not NAME_RE.fullmatch(data["material_id"])):
        raise DesignError(f"{module_id}.vertical_divider.material_id inválido.")
    _positive(data["thickness_mm"], f"{module_id}.vertical_divider.thickness_mm")
    _positive(data["depth_mm"], f"{module_id}.vertical_divider.depth_mm")
    for field in ("position_from_clear_left_mm", "depth_from_front_mm"):
        if type(data[field]) is not int or data[field] < 0:
            raise DesignError(
                f"{module_id}.vertical_divider.{field}: milímetros enteros no negativos."
            )
    if data["depth_from_front_mm"] + data["depth_mm"] > module_depth_mm:
        raise DesignError(f"{module_id}.vertical_divider: excede el fondo de carcasa.")
    return data


def _concept_only_result(spec: dict[str, Any], site: dict[str, Any],
                         blockers: list[str]) -> dict[str, Any]:
    """Return an explicit non-geometric review when F6 lacks a valid joint."""
    result = {
        "schema_version": "0.1.0", "type": "modular_run",
        "application": spec["application"], "status": "CONCEPT_ONLY",
        "fabrication_ready": False, "cutting_ready": False,
        "drilling_ready": False, "purchase_ready": False,
        "can_generate_f7c": False,
        "dimensions_mm": {
            "width": spec["width_mm"], "height": spec["height_mm"],
            "depth": spec["depth_mm"],
        },
        "site": site, "modules": [], "parts": [], "piece_count": 0,
        "blockers": blockers,
    }
    return result


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
    max_assembled_depth = (
        _positive(d["max_assembled_depth_mm"], "max_assembled_depth_mm")
        if "max_assembled_depth_mm" in d else None
    )
    site = _site_check(d, width)
    modules = d.get("modules")
    if not isinstance(modules, list) or not 1 <= len(modules) <= 12:
        raise DesignError("modules: se requieren entre 1 y 12 módulos.")
    widths: list[int] = []
    prepared: list[tuple[dict[str, Any], dict[str, Any] | None,
                         dict[str, Any] | None, dict[str, Any] | None,
                         dict[str, Any] | None]] = []
    support_concepts: dict[str, dict[str, Any]] = {}
    upper_support_specs: dict[str, dict[str, Any]] = {}
    upper_support_reviews: list[dict[str, Any]] = []
    concept_only_reasons: list[str] = []
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
        if module.get("fronts") not in ("none", "pending") and not isinstance(module.get("fronts"), dict):
            raise DesignError(f"{module_id}: fronts requiere none, pending u objeto explícito.")
        if module.get("back") not in ("none", "pending") and not isinstance(module.get("back"), dict):
            raise DesignError(f"{module_id}: back requiere none, pending u objeto documentado.")
        if module.get("support") not in ("floor", "wall", "pending"):
            raise DesignError(f"{module_id}: indicar support=floor, wall o pending.")
        countertop = _countertop(
            module.get("countertop"), module_id=module_id,
            module_width_mm=w, module_depth_mm=depth,
        )
        upper_support = _upper_support(
            module.get("upper_support"), module_id=module_id,
            countertop=countertop, construction=module["construction"],
            module_depth_mm=depth,
            module_height_mm=height,
            panel_thickness_mm=module["panel_thickness_mm"],
        )
        if upper_support is not None:
            upper_support_specs[module_id] = upper_support
        divider = _horizontal_divider(
            module.get("horizontal_divider"), module_id=module_id,
            module_depth_mm=depth,
        )
        vertical_divider = _vertical_divider(
            module.get("vertical_divider"), module_id=module_id,
            module_depth_mm=depth,
        )
        if divider is not None and vertical_divider is not None:
            concept_only_reasons.append(
                f"{module_id}: división horizontal y vertical se cruzan; "
                "CONCEPT_ONLY / JOINT_PENDING. No se generan piezas sin una unión validada."
            )
        if upper_support is not None:
            fronts = module["fronts"]
            if (not isinstance(fronts, dict) or fronts.get("style") != "overlay"
                    or fronts.get("leaf_count") != 2):
                raise DesignError(
                    f"{module_id}: coffee_three_upright_ties exige dos puertas "
                    "overlay explícitas; la repisa interior es independiente."
                )
        if countertop is not None and "support_concept" not in module:
            raise DesignError(
                f"{module_id}: una cubierta separada requiere support_concept "
                "para cerrar la altura total."
            )
        if "support_concept" in module:
            support_concepts[module_id] = _support_concept(
                module["support_concept"], module_id=module_id,
                carcass_height_mm=height,
                existing_support=module["support"], installation=installation,
                countertop_thickness_mm=(countertop["thickness_mm"]
                                         if countertop else 0),
            )
        prepared.append((module, _finish(module.get("finish"), module_id),
                         divider, countertop, vertical_divider))
        widths.append(w)

    if any(countertop is not None for _, _, _, countertop, _ in prepared):
        if len(modules) != 1:
            raise DesignError(
                "La cubierta exterior P0 solo admite una carcasa; "
                "no inferir una cubierta compartida para una fila modular."
            )

    # One horizontal run has one baseline. Partial or contradictory AP heights
    # cannot be silently merged into the same F1 carcass geometry.
    if support_concepts:
        if len(support_concepts) != len(modules):
            raise DesignError(
                "Todos los módulos de una fila deben declarar soporte cuando "
                "uno incluye support_concept; no mezclar alturas implícitas."
            )
        baselines = {(v["style"], v["support_height_mm"],
                      v["overall_height_mm"]) for v in support_concepts.values()}
        if len(baselines) != 1:
            raise DesignError(
                "Fila modular con apoyos/alturas incompatibles: dividir "
                "o revisar físicamente antes de modelar."
            )
    if concept_only_reasons:
        return _concept_only_result(d, site, concept_only_reasons)
    total = sum(widths)
    blockers = [
        "Paneles nominales: sin compensación por tapacantos, sierra, cola o mecanizado.",
        "Verificar cara vista, vetas, cantos, uniones, cargas, vuelco y anclajes.",
        "Puertas, fondos y cajones solo por especificación explícita; patas, zócalos y taladros de producción no modelados.",
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
    assembly_review: dict[str, Any] | None = None
    for module, finish, divider, countertop, vertical_divider in prepared:
        w, t = module["width_mm"], module["panel_thickness_mm"]
        support = support_concepts.get(module["module_id"])
        upper_support = upper_support_specs.get(module["module_id"])
        origin_x = x_offset + (countertop["left_overhang_mm"] if countertop else 0)
        origin_y = (support["support_height_mm"]
                    if support and countertop else 0)
        origin_z = countertop["front_overhang_mm"] if countertop else 0
        geometry = design({
            "type": "cabinet", "width_mm": w,
            "height_mm": height, "depth_mm": depth,
            "panel_thickness_mm": t, "construction": module["construction"],
        })
        _check_drawer_layout_reference(
            module, module_height_mm=height, module_depth_mm=depth
        )
        if divider and (
            divider["position_from_clear_bottom_mm"] + divider["thickness_mm"]
            > geometry["dimensions"]["clear_height_mm"]
        ):
            raise DesignError(
                f"{module['module_id']}.horizontal_divider: excede la altura libre interior."
            )
        sides, caps = geometry["parts"]
        omit_top_panel = countertop is not None or upper_support is not None
        for role in ROLES:
            if role == "top" and omit_top_panel:
                continue
            part = sides if role.endswith("side") else caps
            if module["construction"] == "sides_full":
                y_origin = 0 if role.endswith("side") else (height - t if role == "top" else 0)
            else:
                y_origin = t if role.endswith("side") else (height - t if role == "top" else 0)
            x_origin = origin_x + (w-t if role == "right_side" else 0)
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
                "nominal_origin_xyz_mm": [x_origin, origin_y+y_origin, origin_z],
                "edgebanding_edges": banded if finish else "UNCONFIRMED",
                "edgebanding_thickness_mm":
                    finish.get("edgeband_thickness_mm") if finish else None,
                "edgebanding_nominal_total_mm": band_length,
                "finished_cut_dimensions_mm": None,
                "source_engine": "F1_CORE_CABINET",
                "source_formula": part["calculation"],
            })
        upper_tie_parts: list[dict[str, Any]] = []
        upper_support_review: dict[str, Any] | None = None
        if upper_support is not None:
            clear_width = geometry["dimensions"]["clear_width_mm"]
            tie_height = upper_support["tie_height_mm"]
            rear_z = origin_z + depth - t
            for role, y, z in (
                ("upper_front_tie", origin_y + height - tie_height, origin_z),
                ("upper_rear_tie", origin_y + height - tie_height, rear_z),
                ("lower_rear_tie", origin_y + t, rear_z),
            ):
                upper_tie_parts.append({
                    "piece_id": module["module_id"] + "-" + role.upper(),
                    "module_id": module["module_id"], "role": role,
                    "material_id": module["material_id"],
                    "nominal_face_x_mm": clear_width,
                    "nominal_face_y_mm": tie_height,
                    "thickness_mm": t,
                    "grain_axis": "UNCONFIRMED", "face_plane": "XY",
                    "nominal_origin_xyz_mm": [origin_x + t, y, z],
                    "edgebanding_edges": "UNCONFIRMED",
                    "edgebanding_thickness_mm": None,
                    "edgebanding_nominal_total_mm": None,
                    "finished_cut_dimensions_mm": None,
                    "source_engine": "F6_OPTIONAL_UPPER_SUPPORT",
                    "source_formula": (
                        "length=F1.clear_width_mm; height=explicit "
                        "upper_support.tie_height_mm along Y; face=XY; "
                        "thickness=F1.panel_thickness_mm along Z; positions="
                        "upper-front/upper-rear/lower-rear; "
                        "structural_capacity=UNVERIFIED; tie_height_status="
                        + upper_support["tie_height_status"]
                    ),
                })
            all_parts.extend(upper_tie_parts)
            tie_ids = [piece["piece_id"] for piece in upper_tie_parts]
            upper_support_review = {
                "module_id": module["module_id"],
                "style": "coffee_three_upright_ties",
                "construction": "sides_full",
                "piece_ids": tie_ids,
                "length_mm": clear_width,
                "length_basis": "F1.clear_width_mm",
                "tie_height_mm": tie_height,
                "tie_height_status": upper_support["tie_height_status"],
                "material_id": module["material_id"],
                "thickness_mm": t,
                "source_engine": "F6_OPTIONAL_UPPER_SUPPORT",
                "structural_engineering": "UNVERIFIED",
                "wall_vertical_load_role": "NONE_OWNER_CONFIRMED",
                "countertop_wall_vertical_support": "EXCLUDED_BY_OWNER",
                "cabinet_wall_anchoring": "INSTALLER_STABILITY_ONLY_UNVERIFIED",
            }
            upper_support_reviews.append(upper_support_review)
            blockers.append(
                f"{module['module_id']}: tres correas de canto; altura "
                f"{tie_height} mm ({upper_support['tie_height_status']}); "
                "uniones y resistencia sin verificar; el muro no recibe carga vertical."
            )
        rear_parts, rear_blockers = back_panels(
            module["back"], module_id=module["module_id"],
            module_height_mm=height, module_depth_mm=depth,
            clear_width_mm=geometry["dimensions"]["clear_width_mm"],
            clear_height_mm=geometry["dimensions"]["clear_height_mm"],
            carcase_thickness_mm=t, start_x_mm=origin_x,
        )
        if upper_support is not None and rear_parts:
            return _concept_only_result(d, site, [
                f"{module['module_id']}: el fondo posterior ocupa el volumen de "
                "las correas traseras y las bloquearía. Elija fondo o correas y "
                "revise la estructura; no se presume equivalencia de fondo de 15 mm. "
                "CONCEPT_ONLY por interferencia geométrica."
            ])
        for piece in rear_parts:
            piece["nominal_origin_xyz_mm"][1] += origin_y
            piece["nominal_origin_xyz_mm"][2] += origin_z
        all_parts.extend(rear_parts)
        blockers.extend(rear_blockers)
        doors, door_blockers = front_panels(
            module["fronts"], module_id=module["module_id"],
            module_width_mm=w, module_height_mm=height,
            clear_width_mm=geometry["dimensions"]["clear_width_mm"],
            clear_height_mm=geometry["dimensions"]["clear_height_mm"],
            panel_thickness_mm=t, start_x_mm=origin_x,
        )
        for piece in doors:
            piece["nominal_origin_xyz_mm"][1] += origin_y
            piece["nominal_origin_xyz_mm"][2] += origin_z
        all_parts.extend(doors)
        blockers.extend(door_blockers)
        drawer_parts, drawer_blockers, drawer_ids = module_drawers(
            module.get("drawers", "none"), module_id=module["module_id"],
            start_x_mm=origin_x, carcase_thickness_mm=t,
            clear_width_mm=geometry["dimensions"]["clear_width_mm"],
            clear_height_mm=geometry["dimensions"]["clear_height_mm"],
            module_depth_mm=depth, back_parts=rear_parts,
            has_doors=bool(doors),
        )
        for piece in drawer_parts:
            piece["nominal_origin_xyz_mm"][1] += origin_y
            piece["nominal_origin_xyz_mm"][2] += origin_z
        all_parts.extend(drawer_parts)
        blockers.extend(drawer_blockers)
        divider_parts: list[dict[str, Any]] = []
        if divider:
            divider_parts.append({
                "piece_id": module["module_id"] + "-SHELF",
                "module_id": module["module_id"],
                "role": "shelf_horizontal",
                "material_id": divider["material_id"],
                "nominal_face_x_mm": geometry["dimensions"]["clear_width_mm"],
                "nominal_face_y_mm": divider["depth_mm"],
                "thickness_mm": divider["thickness_mm"],
                "grain_axis": "UNCONFIRMED", "face_plane": "XZ",
                "nominal_origin_xyz_mm": [
                    origin_x+t,
                    origin_y+t+divider["position_from_clear_bottom_mm"],
                    origin_z+divider["depth_from_front_mm"],
                ],
                "edgebanding_edges": "UNCONFIRMED",
                "edgebanding_thickness_mm": None,
                "edgebanding_nominal_total_mm": None,
                "finished_cut_dimensions_mm": None,
                "source_engine": "F6_HORIZONTAL_DIVIDER",
                "source_formula": (
                    "width=F1.clear_width_mm; y=carcass_origin_y + "
                    "panel_thickness_mm + position_from_clear_bottom_mm; "
                    "depth=explicit depth_mm; z=carcass_origin_z + "
                    "depth_from_front_mm"
                ),
            })
            all_parts.extend(divider_parts)
            blockers.append(
                f"{module['module_id']}: repisa horizontal nominal; veta, cantos, "
                "uniones y profundidad de uso requieren revisión."
            )
        vertical_divider_parts: list[dict[str, Any]] = []
        if vertical_divider:
            clear_width = geometry["dimensions"]["clear_width_mm"]
            clear_height = geometry["dimensions"]["clear_height_mm"]
            offset = vertical_divider["position_from_clear_left_mm"]
            thickness = vertical_divider["thickness_mm"]
            if offset <= 0 or offset + thickness >= clear_width:
                raise DesignError(
                    f"{module['module_id']}.vertical_divider: la posición debe "
                    "quedar dentro del claro F1 y sin invadir los laterales."
                )
            vertical_divider_parts.append({
                "piece_id": module["module_id"] + "-DIVIDER-VERTICAL",
                "module_id": module["module_id"], "role": "divider_vertical",
                "material_id": vertical_divider["material_id"],
                "nominal_face_x_mm": vertical_divider["depth_mm"],
                "nominal_face_y_mm": clear_height,
                "thickness_mm": thickness,
                "grain_axis": "UNCONFIRMED", "face_plane": "YZ",
                "nominal_origin_xyz_mm": [
                    origin_x + t + offset, origin_y + t,
                    origin_z + vertical_divider["depth_from_front_mm"],
                ],
                "edgebanding_edges": "UNCONFIRMED",
                "edgebanding_thickness_mm": None,
                "edgebanding_nominal_total_mm": None,
                "finished_cut_dimensions_mm": None,
                "source_engine": "F6_VERTICAL_DIVIDER_FROM_F1",
                "source_formula": (
                    "height=F1.clear_height_mm; x=carcass_origin_x + "
                    "panel_thickness_mm + explicit position_from_clear_left_mm; "
                    "depth and depth_from_front_mm are explicit review inputs"
                ),
            })
            all_parts.extend(vertical_divider_parts)
            blockers.append(
                f"{module['module_id']}: división vertical nominal; contacto, "
                "uniones, holguras y compatibilidad con puertas/cajones pendientes."
            )
        countertop_parts: list[dict[str, Any]] = []
        if countertop:
            countertop_piece_id = module["module_id"] + "-COUNTERTOP"
            countertop_parts.append({
                "piece_id": countertop_piece_id,
                "module_id": module["module_id"], "role": "countertop",
                "material_id": countertop["material_id"],
                "nominal_face_x_mm": countertop["width_mm"],
                "nominal_face_y_mm": countertop["depth_mm"],
                "thickness_mm": countertop["thickness_mm"],
                "grain_axis": "UNCONFIRMED", "face_plane": "XZ",
                "nominal_origin_xyz_mm": [
                    x_offset,
                    origin_y+height,
                    0,
                ],
                "edgebanding_edges": "UNCONFIRMED",
                "edgebanding_thickness_mm": None,
                "edgebanding_nominal_total_mm": None,
                "finished_cut_dimensions_mm": None,
                "finish_note": countertop["finish_note"],
                "source_engine": "F6_EXPLICIT_COUNTERTOP",
                "source_formula": (
                    "width=explicit countertop.width_mm; depth=explicit "
                    "countertop.depth_mm; origin=assembly front/left; "
                    "height=carcass_origin_y + F1.height_mm"
                ),
            })
            all_parts.extend(countertop_parts)
            blockers.append(
                f"{module['module_id']}: cubierta y acabado son datos nominales; "
                "sellado, soporte, cantos y resistencia al agua no verificados."
            )
            if upper_support is None:
                blockers.append(
                    f"{module['module_id']}: se omite la tapa completa bajo el mesón; "
                    "el sistema de apoyo superior sigue pendiente y no está verificado."
                )
            assembly_review = {
                "carcass_origin_xyz_mm": [origin_x, origin_y, origin_z],
                "carcass_dimensions_xyz_mm": [w, height, depth],
                "support_style": support["style"],
                "support_height_mm": support["support_height_mm"],
                "physical_support_parts": "NOT_MODELED",
                "countertop_support_status": (
                    "CONCEPT_ONLY_NOT_STRUCTURALLY_VERIFIED"
                    if upper_support is not None else
                    "PENDING_NO_UPPER_SUPPORT_SELECTED"
                ),
                "countertop_piece_id": countertop_piece_id,
                "countertop_thickness_mm": countertop["thickness_mm"],
                "countertop_finish_note": countertop["finish_note"],
                "review_status": "HYPOTHESIS_PREVIEW_ONLY",
                "vertical_load_path": "CARCASS_TO_LEGS_TO_FLOOR_CONCEPT_ONLY",
                "wall_vertical_load_role": "NONE_OWNER_CONFIRMED",
                "countertop_wall_vertical_support": "EXCLUDED_BY_OWNER",
                "front_gaps_status": "HYPOTHESIS_PREVIEW_ONLY",
                "shelf_position_status": "HYPOTHESIS_PREVIEW_ONLY",
            }
        if finish is None:
            blockers.append(f"{module['module_id']}: definir veta y cuatro lados de canto por pieza.")
        if module["fronts"] == "pending":
            blockers.append(f"{module['module_id']}: definir puertas/frentes y sus holguras.")
        if module["back"] == "pending":
            blockers.append(f"{module['module_id']}: definir fondo, ranura o panel aplicado.")
        if module["support"] == "pending":
            blockers.append(f"{module['module_id']}: definir fijación/soporte.")
        concept = support
        if concept and concept["style"] in ("legs", "plinth"):
            blockers.append(
                f"{module['module_id']}: {concept['style']} de "
                f"{concept['support_height_mm']} mm solo en geometría de "
                "revisión: falta modelo, cantidad, ubicación, resistencia, "
                "fijaciones y compatibilidad con la carga; NO añadir patas "
                "al CSV de paneles ni autorizar fabricación."
            )
        out_modules.append({
            "module_id": module["module_id"], "start_x_mm": origin_x,
            "external_width_mm": w, "external_height_mm": height,
            "external_depth_mm": depth, "clear_width_mm": geometry["dimensions"]["clear_width_mm"],
            "clear_height_mm": geometry["dimensions"]["clear_height_mm"],
            **({"origin_xyz_mm": [origin_x, origin_y, origin_z]}
               if countertop else {}),
            "construction": module["construction"], "part_ids":
                [module["module_id"] + "-" + role.upper() for role in ROLES
                 if not (role == "top" and omit_top_panel)] +
                [piece["piece_id"] for piece in upper_tie_parts] +
                [piece["piece_id"] for piece in rear_parts] +
                [piece["piece_id"] for piece in doors] +
                [piece["piece_id"] for piece in drawer_parts] +
                [piece["piece_id"] for piece in divider_parts] +
                [piece["piece_id"] for piece in vertical_divider_parts] +
                [piece["piece_id"] for piece in countertop_parts],
            "panel_thickness_mm": t, "fronts": module["fronts"],
            "back": module["back"], "support": module["support"],
            **({"support_review": concept} if concept is not None else {}),
            **({"upper_support_review": upper_support_review}
               if upper_support_review is not None else {}),
            **({"countertop_review": {
                "piece_id": countertop_parts[0]["piece_id"],
                "overhangs_mm": {
                    "left": countertop["left_overhang_mm"],
                    "right": countertop["right_overhang_mm"],
                    "front": countertop["front_overhang_mm"],
                    "rear": countertop["rear_overhang_mm"],
                },
                "finish_note": countertop["finish_note"],
            }} if countertop else {}),
            **({"review_hypotheses": {
                "status": "HYPOTHESIS_PREVIEW_ONLY",
                "front_style": module["fronts"]["style"],
                "front_leaf_count": module["fronts"]["leaf_count"],
                "front_reveals_mm": {
                    key: module["fronts"][key] for key in (
                        "left_reveal_mm", "right_reveal_mm",
                        "top_reveal_mm", "bottom_reveal_mm",
                    )
                },
                "front_center_gap_mm": module["fronts"]["center_gap_mm"],
                "shelf_position_from_clear_bottom_mm": (
                    divider["position_from_clear_bottom_mm"]
                ),
                "shelf_depth_mm": divider["depth_mm"],
                "shelf_depth_from_front_mm": divider["depth_from_front_mm"],
            }} if upper_support is not None and divider is not None else {}),
            "drawer_ids": drawer_ids,
            **({"vertical_divider_review": {
                "piece_id": vertical_divider_parts[0]["piece_id"],
                "position_from_clear_left_mm": vertical_divider["position_from_clear_left_mm"],
                "depth_mm": vertical_divider["depth_mm"],
                "depth_from_front_mm": vertical_divider["depth_from_front_mm"],
                "status": "NOMINAL_REVIEW_ONLY",
            }} if vertical_divider else {}),
        })
        x_offset += w
    if len(all_parts) > 72:
        raise DesignError("Se excedió el límite seguro de 72 piezas CAD; dividir el proyecto.")
    check_adjacent_fronts(out_modules, all_parts)
    # Derived from the SAME front-offset formula used by CADExchange; no
    # second 3D model and no presumption that 500 mm carcass means 500 mm
    # assembled depth when an overlay decorative face extends forward.
    front_extension = nominal_front_extension_mm(all_parts)
    countertop_part = next(
        (piece for piece in all_parts if piece["role"] == "countertop"), None
    )
    if countertop_part:
        dimensions = {
            "width": countertop_part["nominal_face_x_mm"],
            "height": assembly_review["carcass_dimensions_xyz_mm"][1]
                     + assembly_review["support_height_mm"]
                     + countertop_part["thickness_mm"],
            "depth": countertop_part["nominal_face_y_mm"],
        }
    else:
        dimensions = {"width": width, "height": height, "depth": depth}
    assembled_depth = (dimensions["depth"] if countertop_part
                       else depth + front_extension)
    depth_conflict = (max_assembled_depth is not None
                      and assembled_depth > max_assembled_depth)
    depth_review = {
        "carcass_depth_mm": depth,
        "front_extension_mm": front_extension,
        "assembled_external_depth_mm": assembled_depth,
        "max_assembled_depth_mm": max_assembled_depth,
        "conflict": depth_conflict,
    }
    if depth_conflict:
        blockers.insert(
            0, f"Profundidad exterior montada {assembled_depth} mm supera "
               f"límite explícito de {max_assembled_depth} mm: cambiar "
               "profundidad de carcasa o revisar el límite antes de CAD."
        )
        if status == "DRAFT_NOT_FOR_CUTTING":
            status = "NEEDS_DEPTH_REVISION"
    elif front_extension and max_assembled_depth is None:
        blockers.append(
            f"Carcasa {depth} mm más frente sobrepuesto {front_extension} mm "
            f"= {assembled_depth} mm exteriores; confirmar si cabe "
            "en la profundidad solicitada."
        )
    if installation == "wall_mounted":
        blockers.insert(0, "Mueble suspendido: carga, muro y anclajes requieren cálculo competente.")
    blockers.append("La unión entre módulos y los apoyos entre cuerpos aún no están diseñados.")
    result = {
        "schema_version": "0.1.0", "type": "modular_run",
        "application": d["application"], "status": status,
        "fabrication_ready": False, "cutting_ready": False, "drilling_ready": False,
        "purchase_ready": False,
        "dimensions_mm": dimensions,
        **({"carcass_dimensions_mm": {
            "width": width, "height": height, "depth": depth,
        }} if countertop_part else {}),
        **({"assembly_review": assembly_review}
           if assembly_review is not None else {}),
        **({"upper_support_review": upper_support_reviews[0]}
           if upper_support_reviews else {}),
        "depth_review": depth_review,
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
    if (status == "DRAFT_NOT_FOR_CUTTING"
            and any(vertical is not None for _, _, _, _, vertical in prepared)):
        try:
            from .cad_exchange import cad_exchange
            cad_exchange(result)
        except DesignError as exc:
            return _concept_only_result(d, site, [
                "División vertical incompatible con sólidos F6 existentes: "
                f"{exc}. Ajustar posición/profundidad o revisar la junta; "
                "CONCEPT_ONLY y cero piezas de producción."
            ])
    return result
