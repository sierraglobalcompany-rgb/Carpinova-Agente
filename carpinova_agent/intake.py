"""F3: minimal deterministic interview ahead of preliminary geometry.

This module DOES NOT parse natural language or certify furniture designs.
It groups only the questions blocking next progress, then delegates all
measurements to the single F1 geometry engine.
"""
from __future__ import annotations

from typing import Any, Mapping
import unicodedata

from .core import DesignError, design


def _fold(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value.strip().casefold())
        if not unicodedata.combining(char)
    )


ALIASES = {
    "cabinet": "cabinet", "gabinete": "cabinet", "gabinetes": "cabinet", "alacena": "cabinet",
    "drawer": "drawer", "cajon": "drawer", "cajón": "drawer", "cajones": "drawer",
    "closet": "closet", "closets": "closet", "clóset": "closet", "armario": "closet",
    "wardrobe": "closet", "cocina": "kitchen", "cocinas": "kitchen", "kitchen": "kitchen",
    "nicho": "niche", "nichos": "niche", "niche": "niche", "escritorio": "desk",
    "desk": "desk", "biblioteca": "bookcase", "bookcase": "bookcase",
    "mueble de bano": "bathroom", "mueble de baño": "bathroom",
    "bathroom": "bathroom",
}
TYPES = {_fold(key): val for key, val in ALIASES.items()}

CABINET_FIELDS = ("width_mm", "height_mm", "depth_mm",
                  "panel_thickness_mm", "construction")
DRAWER_FIELDS = (
    "opening_width_mm", "opening_height_mm", "opening_depth_mm",
    "box_height_mm", "panel_thickness_mm", "bottom_thickness_mm",
    "slide_clearance_left_mm", "slide_clearance_right_mm",
    "front_setback_mm", "rear_setback_mm",
)
SPACE_FIELDS = ("width_mm", "height_mm", "depth_mm")
SHARED = ("project_type", "installation", "front_style", "back_style",
          "grain_direction", "site_width_top_mm", "site_width_middle_mm",
          "site_width_bottom_mm")
CATEGORIES = {
    "installation": {"freestanding", "wall_mounted", "built_in"},
    "front_style": {"none", "overlay", "inset"},
    "back_style": {"none", "applied", "grooved"},
    "grain_direction": {"vertical", "horizontal", "to_define"},
}
NUMERIC_FIELDS = set(CABINET_FIELDS + DRAWER_FIELDS + SPACE_FIELDS) - {"construction"}
NUMERIC_FIELDS.update({"site_width_top_mm", "site_width_middle_mm",
                       "site_width_bottom_mm"})
NONNEGATIVE_FIELDS = {
    "slide_clearance_left_mm", "slide_clearance_right_mm",
    "front_setback_mm", "rear_setback_mm",
}
CONSTRUCTIONS = {"sides_full", "top_bottom_full"}

# Questions are authored in user language and explicitly refer to geometry.
QUESTION_TEXT = {
    "project_type": "¿Qué mueble quieres hacer: gabinete, cajón, clóset, cocina, nicho u otro?",
    "width_mm": "¿Cuál es el ancho exterior que debe tener el módulo (mm)?",
    "height_mm": "¿Cuál es el alto exterior que debe tener el módulo (mm)?",
    "depth_mm": "¿Cuál es la profundidad exterior que debe tener el módulo (mm)?",
    "opening_width_mm": "¿Cuánto mide el ancho libre del hueco del cajón (mm)?",
    "opening_height_mm": "¿Cuánto mide el alto libre del hueco del cajón (mm)?",
    "opening_depth_mm": "¿Cuánto mide la profundidad libre del hueco (mm)?",
    "box_height_mm": "¿Qué alto exterior tendrá la caja, incluido el fondo aplicado (mm)?",
    "panel_thickness_mm": "¿Qué espesor REAL tienen los tableros (mm)?",
    "bottom_thickness_mm": "¿Qué espesor REAL tendrá el fondo del cajón (mm)?",
    "construction": (
        "¿Los costados llegan de piso a techo (sides_full) o la tapa y "
        "la base cubren los costados (top_bottom_full)?"
    ),
    "slide_clearance_left_mm": (
        "¿Qué holgura lateral izquierda requiere la corredera seleccionada, "
        "según su ficha técnica (mm)?"
    ),
    "slide_clearance_right_mm": (
        "¿Qué holgura lateral derecha requiere esa corredera, según ficha (mm)?"
    ),
    "front_setback_mm": "¿Qué retiro frontal de la caja estás usando (mm)?",
    "rear_setback_mm": "¿Qué retiro posterior de la caja estás usando (mm)?",
    "installation": "¿Va al piso, fijado a pared o empotrado?",
    "front_style": "¿Llevará frente/puerta exterior superpuesta, embutida o ninguno?",
    "back_style": "¿El fondo va aplicado, ranurado o no lleva fondo?",
    "grain_direction": "¿Cómo quieres orientar las vetas visibles: vertical, horizontal o por definir?",
    "site_width_top_mm": "¿Cuál es la medida del hueco arriba (mm)?",
    "site_width_middle_mm": "¿Cuál es la medida del hueco a media altura (mm)?",
    "site_width_bottom_mm": "¿Cuál es la medida del hueco abajo (mm)?",
}

ADVICE = {
    "construction": (
        "sides_full: laterales a altura completa, tapa/base entre costados. "
        "top_bottom_full: tapa y base de ancho completo, laterales entre ambas. "
        "Ninguna opción determina sola la resistencia final."
    ),
    "front_style": (
        "overlay = frente sobrepuesto; inset = frente embutido dentro del hueco. "
        "Las luces y bisagras dependen de la referencia exacta del herraje."
    ),
    "grain_direction": (
        "La veta no se deduce de un render: asignarla a cada pieza y "
        "verificar el formato real del tablero antes de optimizar."
    ),
    "slides": (
        "No asumir holgura estándar de corredera. Consultar la ficha técnica "
        "del fabricante y modelo exactos: espesor, carga, instalación y dibujo acotado."
    ),
}

DETAILS = (
    "Confirmar cantos por lado y espesor de tapacantos, sin compensación automática.",
    "Definir el tipo de uniones, fondos, puertas, guías, bisagras y tornillería.",
    "Revisar cargas, estabilidad, vuelco y anclajes según ubicación.",
    "Validar que las cotas exteriores, el lugar y el acabado físico coincidan.",
)


def _question(key: str) -> dict[str, str]:
    return {"field": key, "question": QUESTION_TEXT[key], "unit": (
        "mm" if key in NUMERIC_FIELDS else "choice"
    )}


def _require_data(project: Any) -> dict[str, Any]:
    if not isinstance(project, dict):
        raise DesignError("El proyecto debe ser un objeto JSON.")
    unknown = project.keys() - (set(SHARED) | set(CABINET_FIELDS)
                                | set(DRAWER_FIELDS) | set(SPACE_FIELDS))
    if unknown:
        raise DesignError("Campos no admitidos: " + ", ".join(sorted(unknown)))
    if "project_type" in project and not isinstance(project["project_type"], str):
        raise DesignError("project_type debe ser texto.")
    for key, value in project.items():
        if key in NUMERIC_FIELDS and (type(value) is not int
                                      or value < 0
                                      or (value == 0 and key not in NONNEGATIVE_FIELDS)):
            raise DesignError(f"{key} debe ser entero en mm"
                              + (" no negativo." if key in NONNEGATIVE_FIELDS
                                 else " positivo."))
        if key in CATEGORIES and (not isinstance(value, str)
                                  or value not in CATEGORIES[key]):
            raise DesignError(f"{key} debe ser uno de: "
                              + ", ".join(sorted(CATEGORIES[key])))
        if key == "construction" and (not isinstance(value, str)
                                      or value not in CONSTRUCTIONS):
            raise DesignError("construction: sides_full o top_bottom_full.")
    return project


def guide_project(project: Mapping[str, Any], max_questions: int = 3) -> dict[str, Any]:
    """Return an actionable next step, or a strictly unapproved geometry draft."""
    if type(max_questions) is not int or not 1 <= max_questions <= 6:
        raise DesignError("max_questions debe ser entero entre 1 y 6.")
    data = dict(_require_data(project))
    if "project_type" in data and not data["project_type"].strip():
        del data["project_type"]
    raw_type = data.get("project_type")
    kind = TYPES.get(_fold(raw_type), None) if raw_type else None
    if raw_type and kind is None:
        raise DesignError("Tipo desconocido. Prueba: gabinete, cajón, clóset, cocina, nicho.")
    if kind == "cabinet":
        fields = CABINET_FIELDS
    elif kind == "drawer":
        fields = DRAWER_FIELDS
    elif kind:
        fields = SPACE_FIELDS
    else:
        fields = ("project_type",)

    # Reject parameters irrelevant to a model rather than silently disregarding
    # them. Shared installation/design intent is kept as non-fabrication context.
    allowed = set(SHARED) | set(fields)
    if kind is None:
        # A person can give dimensions before naming the furniture type.
        allowed.update(CABINET_FIELDS + DRAWER_FIELDS + SPACE_FIELDS)
    elif kind not in ("cabinet", "drawer"):
        # Material information is useful context for later modular design.
        allowed.add("panel_thickness_mm")
    extra = data.keys() - allowed
    if extra:
        raise DesignError("Campos ajenos a este mueble: " + ", ".join(sorted(extra)))
    missing = [key for key in fields if key not in data]
    if kind == "drawer":
        # Guide the user to verify hardware before declaring slide clearance.
        if any(key.startswith("slide_clearance") for key in missing):
            question_hint = ADVICE["slides"]
        else:
            question_hint = None
    else:
        question_hint = ADVICE["construction"] if "construction" in missing else None

    response: dict[str, Any] = {
        "phase": "NEEDS_INPUT",
        "project_type": kind,
        "submitted_values": dict(data),
        "missing_required_fields": missing,
        "questions": [_question(key) for key in missing[:max_questions]],
        "next_question_hint": question_hint,
        "design": None,
        "status": "DRAFT_NOT_FOR_CUTTING",
        "release_blockers": list(DETAILS),
        "construction_choices": ADVICE["construction"],
        "front_choices": ADVICE["front_style"],
        "grain_guidance": ADVICE["grain_direction"],
    }
    site_keys = ("site_width_top_mm", "site_width_middle_mm", "site_width_bottom_mm")
    have_site = [data[key] for key in site_keys if key in data]
    if have_site:
        response["site_measurements"] = {
            "provided": {key: data[key] for key in site_keys if key in data},
            "all_three_confirmed": len(have_site) == 3,
            "range_mm": max(have_site) - min(have_site) if len(have_site) == 3 else None,
            "warning": ("Estas medidas NO sustituyen una cota exterior de "
                        "mueble ni fijan por sí solas una holgura de instalación."),
        }

    if missing:
        return response

    if kind in ("cabinet", "drawer"):
        geometry_spec = (
            {"type": kind, **{name: data[name] for name in fields}}
        )
        try:
            computed = design(geometry_spec)
        except DesignError as exc:
            response.update(phase="INVALID_GEOMETRY",
                            release_blockers=[str(exc), *DETAILS])
            return response
        response.update(
            phase="GEOMETRY_DRAFT",
            design=computed,
            release_blockers=computed["release_blockers"] + list(DETAILS),
        )
    else:
        response.update(
            phase="CONCEPT_ONLY",
            release_blockers=[
                "Desglosar el proyecto en módulos con medidas y función de cada uno.",
                "Motor de geometría integral para esta categoría aún no implementado.",
                *DETAILS,
            ],
        )

    site_keys = ("site_width_top_mm", "site_width_middle_mm", "site_width_bottom_mm")
    site_missing = ([key for key in site_keys if key not in data]
                    if data.get("installation") == "built_in" else [])
    context_missing = [key for key in ("installation", "front_style", "back_style",
                                       "grain_direction") if key not in data]
    priorities = site_missing + context_missing
    response["questions"] = [_question(key) for key in priorities[:max_questions]]
    if kind not in ("cabinet", "drawer"):
        response["questions"] = (
            [{"field": "module_layout", "unit": "description",
              "question": ("¿Cómo quieres dividir el espacio en módulos, "
                           "puertas, cajones y zonas de uso?")}]
            + [_question(key) for key in priorities[:max_questions-1]]
        )[:max_questions]
    if (data.get("installation") == "built_in"
            and len(have_site) == 3
            and kind != "drawer"
            and "width_mm" in data
            and data["width_mm"] >= min(have_site)):
        response["phase"] = "SITE_CONFLICT"
        response["release_blockers"].insert(
            0, "Ancho exterior del mueble iguala/supera la menor luz del sitio. "
               "Revisar cota y holgura de instalación antes de fabricar."
        )
    return response
