"""Compare actual CAD application boxes with F6's canonical geometry.

This is a *measurement verifier*, not a second dimensioning or modeling
engine. Native application adapters capture world-coordinate bounding boxes,
and this module compares them to the original sealed CADExchange.
"""
from __future__ import annotations

import math
from typing import Any

from carpinova_agent.core import DesignError
from integrations.cad_native import native_boxes


def verify_native_boxes(
    exchange: dict[str, Any],
    observed: list[dict[str, Any]],
    *,
    tolerance_mm: float = 0.05,
) -> dict[str, Any]:
    """Reject missing/extra/shifted/resized parts in FreeCAD or Blender.

    observed is measured FROM THE CREATED SCENE, not echoed from the contract:
      [{piece_id, native_origin_xyz_mm:[x,y,z],
                  native_size_xyz_mm:[dx,dy,dz]}, ...].
    """
    if (isinstance(tolerance_mm, bool)
            or not isinstance(tolerance_mm, (int, float))
            or not math.isfinite(tolerance_mm)
            or tolerance_mm < 0 or tolerance_mm > 0.5):
        raise DesignError("La tolerancia CAD debe estar entre 0 y 0.5 mm.")
    expected = {p["piece_id"]: p for p in native_boxes(exchange)}
    if not isinstance(observed, list) or len(observed) != len(expected):
        raise DesignError("El CAD real tiene una cantidad distinta de paneles.")
    actual = {}
    for p in observed:
        if not isinstance(p, dict) or set(p) != {
            "piece_id", "native_origin_xyz_mm", "native_size_xyz_mm"
        }:
            raise DesignError("Registro de medida CAD con esquema incorrecto.")
        pid = p["piece_id"]
        if not isinstance(pid, str) or pid not in expected or pid in actual:
            raise DesignError("ID CAD desconocido o duplicado.")
        for field in ("native_origin_xyz_mm", "native_size_xyz_mm"):
            coords = p[field]
            if (not isinstance(coords, list) or len(coords) != 3
                    or any(isinstance(v, bool) or
                           not isinstance(v, (int, float)) or
                           not math.isfinite(v) for v in coords)):
                raise DesignError(f"Medición inválida de {pid}.{field}")
            if field == "native_size_xyz_mm" and any(v <= 0 for v in coords):
                raise DesignError(f"Dimensión no positiva en {pid}")
        actual[pid] = p

    greatest_error = 0.0
    for pid, exp in expected.items():
        item = actual[pid]
        for field in ("native_origin_xyz_mm", "native_size_xyz_mm"):
            for axis in range(3):
                delta = abs(float(exp[field][axis]) - float(item[field][axis]))
                greatest_error = max(greatest_error, delta)
                if delta > tolerance_mm:
                    raise DesignError(
                        f"Divergencia CAD {pid}, {field}, eje {axis}: "
                        f"{delta:.6f} mm, tolerancia {tolerance_mm} mm."
                    )
    return {
        "status": "NATIVE_GEOMETRY_MATCH",
        "geometry_sha256": exchange["geometry_sha256"],
        "verified_piece_count": len(expected),
        "max_abs_error_mm": round(greatest_error, 8),
        "tolerance_mm": float(tolerance_mm),
        "fabrication_ready": False,
        "drilling_ready": False,
        "cutting_ready": False,
        "native_application_review": "OBSERVATIONS_MATCH_GEOMETRY_ONLY",
    }
