"""Conservative manufacturer-reference selection; deliberately no drill plan.

A catalog row explains a potential hinge; it does not establish a compatible
hinge+plate+door assembly or release dimensions for cutting, boring or purchase.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "blum-clip-top-110-reference.json"
_ALLOWED_INPUTS = frozenset({
    "manufacturer", "front_style", "door_thickness_mm", "door_height_mm",
    "door_weight_g", "door_material", "hinge_sku", "plate_sku",
})
_STYLES = frozenset({"overlay", "dual", "inset"})
_ISSUE = "BLOCKED_HARDWARE_SPEC"
_SOURCE_KEYS = frozenset({"blum_hinges_pdf", "blum_current_assembly"})


class HardwareError(ValueError):
    """Invalid or untrusted specification."""


def load_hardware_catalog(path: Path | str = CATALOG) -> dict[str, Any]:
    """Read the reviewable exact-SKU catalog, reject malformed evidence."""
    try:
        catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise HardwareError("El catálogo no se puede leer o no es JSON válido.") from exc
    if not isinstance(catalog, dict):
        raise HardwareError("El catálogo debe ser un objeto JSON.")
    if (catalog.get("manufacturer") != "Blum"
            or catalog.get("scope") != "REFERENCE_SELECTION_ONLY"
            or catalog.get("catalog_version") != "0.1.0"):
        raise HardwareError("Versión, alcance o fabricante de catálogo no reconocidos.")
    refs = catalog.get("source_references")
    if not isinstance(refs, dict) or set(refs) != _SOURCE_KEYS:
        raise HardwareError("Fuentes oficiales del catálogo ausentes o inesperadas.")
    for ref in refs.values():
        if (not isinstance(ref, dict)
                or not isinstance(ref.get("url"), str)
                or not (ref["url"].startswith("https://www.blum.com/")
                        or ref["url"].startswith("https://d2.blum.com/"))):
            raise HardwareError("URL de la fuente no pertenece al fabricante.")
    hinges = catalog.get("hinges")
    plates = catalog.get("mounting_plates")
    if (not isinstance(hinges, list) or not isinstance(plates, list)
            or not hinges or not plates):
        raise HardwareError("Referencias de bisagras/placas incompletas.")
    all_skus: set[str] = set()
    styles: set[str] = set()
    for hinge in hinges:
        if not isinstance(hinge, dict):
            raise HardwareError("Fila inválida del catálogo.")
        sku, style, ref = (hinge.get("sku"), hinge.get("front_style"),
                           hinge.get("reference_id"))
        if (not isinstance(sku, str) or not sku
                or style not in _STYLES or style in styles or sku in all_skus
                or ref not in refs or hinge.get("opening_angle_deg") != 110):
            raise HardwareError("Bisagra duplicada/inconsistente o fuente ausente.")
        all_skus.add(sku)
        styles.add(style)
    if styles != _STYLES:
        raise HardwareError("Faltan variantes sobrepuesta, dual o embutida.")
    for plate in plates:
        if not isinstance(plate, dict):
            raise HardwareError("Fila de placa inválida.")
        sku = plate.get("sku")
        if (not isinstance(sku, str) or not sku or sku in all_skus
                or plate.get("reference_id") not in refs
                or plate.get("drawing_coordinate_frame")
                    != "ILLUSTRATION_ONLY_UNVERIFIED_IN_INSTALLATION"):
            raise HardwareError("Placa no reconocida o intentó autorizar perforaciones.")
        all_skus.add(sku)
    missing = catalog.get("not_present")
    if (not isinstance(missing, dict)
            or missing.get("hinge_plate_fitment_authorized") is not False
            or any(v is not None for k, v in missing.items()
                   if k != "hinge_plate_fitment_authorized")):
        raise HardwareError("El catálogo afirma parámetros de mecanizado no auditados.")
    return catalog


def _positive_mm(values: dict[str, Any], key: str) -> int | None:
    if key not in values:
        return None
    value = values[key]
    if type(value) is not int or value <= 0:
        raise HardwareError(f"{key} debe ser entero positivo.")
    return value


def suggest_hinge(request: dict[str, Any]) -> dict[str, Any]:
    """Choose only a reference by style; always refuse a production drill plan."""
    if not isinstance(request, dict):
        raise HardwareError("La solicitud debe ser un objeto JSON.")
    extra = set(request) - _ALLOWED_INPUTS
    if extra:
        raise HardwareError("Campos no admitidos: " + ", ".join(sorted(extra)))
    for key in ("manufacturer", "front_style", "hinge_sku", "plate_sku",
                "door_material"):
        if key in request and (not isinstance(request[key], str)
                               or not request[key].strip()):
            raise HardwareError(f"{key} debe ser texto no vacío.")
    for key in ("door_thickness_mm", "door_height_mm", "door_weight_g"):
        _positive_mm(request, key)
    manufacturer = request.get("manufacturer", "Blum")
    if manufacturer != "Blum":
        raise HardwareError("Este catálogo inicial solo admite Blum; no equivalencias.")
    # The on-disk reviewed catalog is the ONLY source; reject injected datasets.
    catalog = load_hardware_catalog()
    # A reviewer must still verify hardware sources; never output drilling geometry.
    results: dict[str, Any] = {
        "status": _ISSUE,
        "manufacturer": "Blum",
        "candidate_hinge_sku": None,
        "candidate_plate_sku": None,
        "application": request.get("front_style"),
        "purchase_ready": False,
        "drilling_ready": False,
        "drilling_coordinates": [],
        "mounting_pattern": None,
        "missing_inputs": [],
        "blockers": [],
        "sources": [],
    }
    style = request.get("front_style")
    if style not in _STYLES:
        results["missing_inputs"].append("front_style: overlay, dual o inset")
        results["blockers"].append("Debe definirse cómo la puerta cubre el costado.")
        return results

    hinges = catalog.get("hinges")
    plates = catalog.get("mounting_plates")
    refs = catalog.get("source_references", {})
    if not isinstance(hinges, list) or not isinstance(plates, list) or not isinstance(refs, dict):
        raise HardwareError("Catálogo incompleto.")
    candidates = [h for h in hinges if h.get("front_style") == style]
    if len(candidates) != 1:
        raise HardwareError("No hay correspondencia única con el frente.")
    hinge = candidates[0]
    if request.get("hinge_sku") is not None and request["hinge_sku"] != hinge["sku"]:
        results["blockers"].append(
            "La bisagra solicitada no corresponde a la aplicación según documento Blum."
        )
        return results

    results["candidate_hinge_sku"] = hinge["sku"]
    results["series"] = hinge["series"]
    results["sources"].append({
        "sku": hinge["sku"], "page": hinge["pdf_page"],
        "url": refs[hinge["reference_id"]]["url"],
        "evidence": "CORRESPONDENCIA_DE_APLICACION_FUENTE_FABRICANTE",
    })

    plate_sku = request.get("plate_sku")
    if plate_sku:
        match = [plate for plate in plates if plate.get("sku") == plate_sku]
        if len(match) != 1:
            results["blockers"].append("Base/placa desconocida; no inferir equivalencia.")
            return results
        plate = match[0]
        results["candidate_plate_sku"] = plate_sku
        results["mounting_pattern"] = {
            "status": "DOCUMENT_DIAGRAM_REFERENCE_ONLY",
            "front_edge_reference_mm": plate["hole_line_reference_from_front_mm"],
            "hole_pitch_reference_mm": plate["mounting_screw_hole_pitch_mm"],
            "plate_spacing_mm": plate["spacing_mm"],
            "not_drilling_coordinates": True,
            "explanation": (
                "Cotas mostradas por el fabricante en un croquis de placa; "
                "no se estableció origen, cara, taladro piloto ni "
                "compatibilidad completa con puerta y bisagra."
            ),
        }
        results["sources"].append({
            "sku": plate_sku, "page": plate["pdf_page"],
            "url": refs[plate["reference_id"]]["url"],
            "evidence": "CROQUIS_REFERENCIAL_FABRICANTE_NO_PERFORAR",
        })
    else:
        results["missing_inputs"].append("plate_sku: base exacta verificada")

    thickness = request.get("door_thickness_mm")
    if thickness is None:
        results["missing_inputs"].append("door_thickness_mm")
    else:
        nominal_depth = catalog["generic_assembly_reference"]["hinge_cup_boring_depth_mm"]
        if thickness <= nominal_depth:
            results["blockers"].append(
                "Espesor de puerta no supera la profundidad nominal de taladrado "
                "de la familia: incompatibilidad geométrica aparente; NO taladrar."
            )
        else:
            results["blockers"].append(
                "Espesor superior a profundidad nominal no certifica "
                "taladrado seguro ni profundidad adecuada a este SKU."
            )
    for key in ("door_height_mm", "door_weight_g", "door_material"):
        if key not in request:
            results["missing_inputs"].append(key)
    results["blockers"].extend([
        "Verificar la combinación exacta bisagra/base y la superposición del frente.",
        "Falta esquema de cazoleta con diámetro, distancia al borde, coordenadas y profundidades SKU-específicas.",
        "Faltan número de bisagras, carga admisible, separación vertical y tolerancias según fabricante.",
        "Falta validación de tornillos, material, agujeros piloto y anclajes.",
        "Cotas del folleto histórico: comprobar ficha actual del SKU antes de comprar o fabricar.",
    ])
    return results
