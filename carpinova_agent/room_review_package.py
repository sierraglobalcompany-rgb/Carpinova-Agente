"""D19: one portable, review-only ZIP for an entire nominal room layout.

Public entry accepts *specifications*, never CAD boxes/digests from the caller.
Maestro/F6/CADExchange remain the only authority for panel coordinates.
The manifest protects accidental corruption, not cryptographic provenance.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .room_3d_review import render_room_3d_html
from .room_panel_section import render_room_panel_section_svg

_MAX_REQUEST_BYTES = 256_000
_MAX_PACKAGE_BYTES = 4_000_000
_FIELDS = frozenset(("review_kind", "assemblies", "service_zones"))
_KITCHEN_FIELDS = frozenset(("review_kind", "review_state", "service_zones"))
_OPTIONAL_KITCHEN_FIELDS = frozenset((
    "rotations_deg", "back_revisions", "wall_review_revisions",
    "module_edit_revisions",
))
_FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready",
          "purchase_ready", "can_generate_f7c")


class RoomPackageError(ValueError):
    """An unsafe or inconsistent review bundle cannot be issued."""


def _validate_source_request(request: dict[str, Any]) -> str:
    if type(request) is not dict:
        raise RoomPackageError("La solicitud espacial original debe ser un objeto.")
    kind = request.get("review_kind")
    fields = set(request)
    if kind == "room_layout_v1":
        optional = {"wall_review_revisions", "module_edit_revisions"}
        if not _FIELDS <= fields or fields - _FIELDS - optional:
            raise RoomPackageError(
                "Solicitud room_layout_v1 inválida; CAD aportado prohibido y "
                "solo las revisiones permitidas son opcionales"
            )
        if ("wall_review_revisions" in request
                and (type(request["wall_review_revisions"]) is not list
                     or len(request["wall_review_revisions"]) > 12)):
            raise RoomPackageError("wall_review_revisions debe ser una lista de 0 a 12 elementos")
    elif kind == "kitchen_spatial_v1":
        if (not _KITCHEN_FIELDS <= fields
                or fields - _KITCHEN_FIELDS - _OPTIONAL_KITCHEN_FIELDS):
            raise RoomPackageError(
                "kitchen_spatial_v1 solo admite review_kind, review_state, service_zones, "
                "rotations_deg, back_revisions y wall_review_revisions opcionales"
            )
        if ("wall_review_revisions" in request
                and (type(request["wall_review_revisions"]) is not list
                     or len(request["wall_review_revisions"]) > 12)):
            raise RoomPackageError("wall_review_revisions debe ser una lista de 0 a 12 elementos")
    else:
        raise RoomPackageError("Tipo de solicitud espacial no admitido.")
    if "module_edit_revisions" in request:
        from .module_edits import validate_revision_list
        try:
            validate_revision_list(request["module_edit_revisions"])
        except ValueError as exc:
            raise RoomPackageError(str(exc)) from exc
    return kind


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise RoomPackageError(f"Campo JSON duplicado: {key}")
        out[key] = value
    return out


def _no_constant(value: str) -> None:
    raise RoomPackageError(f"Constante JSON no admitida: {value}")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _zip_content(content: dict[str, bytes]) -> bytes:
    memory = io.BytesIO()
    with ZipFile(memory, mode="w", compression=ZIP_DEFLATED, compresslevel=8) as z:
        for name in sorted(content):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            z.writestr(entry, content[name], compress_type=ZIP_DEFLATED, compresslevel=8)
    payload = memory.getvalue()
    if len(payload) > _MAX_PACKAGE_BYTES:
        raise RoomPackageError("ZIP de revisión demasiado grande")
    # A successful write is not yet verification; reread all files and checksums.
    with ZipFile(io.BytesIO(payload)) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(content):
            raise RoomPackageError("Integridad ZIP inválida")
        manifest = json.loads(archive.read("MANIFEST.json"))
        if set(manifest["files"]) != set(content) - {"MANIFEST.json"}:
            raise RoomPackageError("MANIFEST no coincide con los archivos")
        for name, info in manifest["files"].items():
            data = archive.read(name)
            if len(data) != info["bytes"] or _sha(data) != info["sha256"]:
                raise RoomPackageError("Hash o longitud de archivo no coincide")
    return payload


def _render_verified_review(request: dict[str, Any], review: dict[str, Any],
                            *, y_mm: int) -> tuple[bytes, dict[str, Any]]:
    """Private renderer; public writer always regenerates review from request."""
    source_kind = _validate_source_request(request)
    if type(y_mm) is not int or y_mm < 0 or y_mm > 20000:
        raise RoomPackageError("Altura de sección inválida")
    allowed_status = ("REVIEW_ONLY",) if "module_edit_revisions" in request else (
        "REVIEW_ONLY", "INTERFERENCE_REVIEW_REQUIRED")
    if (type(review) is not dict or review.get("review_kind") != "room_layout_v1"
            or review.get("status") not in allowed_status
            or any(review.get(flag) is not False for flag in _FLAGS)):
        raise RoomPackageError("Solo revisión nominal con todas las prohibiciones activas")
    # D18 independently verifies IDs, roles, piece counts, bounds and flags.
    html = render_room_3d_html(
        review,
        module_edit_request=(request if "module_edit_revisions" in request else None),
    )
    from .room_spatial import render_top_view_svg
    top = render_top_view_svg(review)
    section = render_room_panel_section_svg(review, y_mm=y_mm)
    if not isinstance(review.get("layout_sha256"), str) or len(review["layout_sha256"]) != 64:
        raise RoomPackageError("Falta firma nominal de la distribución")
    if not any(b["origin_xyz_mm"][1] <= y_mm < b["origin_xyz_mm"][1] + b["size_xyz_mm"][1]
               for b in review["world_boxes"]):
        raise RoomPackageError("El corte horizontal no atraviesa tableros")
    warning = """CarpiNova · PAQUETE DE REVISIÓN NOMINAL OFFLINE

ABRIR: 01-visor-3d.html (doble clic; sin internet ni aplicaciones CAD).
ALTERNATIVAS: 02-planta.svg y 03-seccion.svg (visores SVG del sistema).
EVIDENCIA: 04-habitacion.json, 05-solicitud.json,
06-paneles-en-escena.csv y MANIFEST.json.

NO FABRICAR · NO CORTAR · NO PERFORAR · NO COMPRAR.
Las medidas XYZ del CSV son envolventes GLOBALES y NO medidas de corte.
Las representaciones son geométricas NOMINALES; no certifican herrajes,
uniones, accesibilidad, cargas ni instalaciones. El ZIP/manifiesto verifica
integridad de bytes, NO autenticidad criptográfica ni autorización del dueño.
Si el estado es INTERFERENCE_REVIEW_REQUIRED, las interferencias siguen
PENDIENTES: este paquete NO las corrige ni aprueba.
"""
    # CSV summarizes world-space boxes; these dimensions are NOT panel cut sizes.
    csv_out = io.StringIO(newline="")
    csv_writer = csv.writer(csv_out)
    csv_writer.writerow(("group_id", "piece_id", "role", "x_world_mm",
                         "y_world_mm", "z_world_mm", "size_x_world_mm",
                         "size_y_world_mm", "size_z_world_mm", "NOT_FOR_CUTTING"))
    for box in review["world_boxes"]:
        csv_writer.writerow((box["group_id"], box["piece_id"], box["role"],
                             *box["origin_xyz_mm"], *box["size_xyz_mm"], "TRUE"))
    files: dict[str, bytes] = {
        "LEER_PRIMERO.txt": warning.encode("utf-8"),
        "01-visor-3d.html": html.encode("utf-8"),
        "02-planta.svg": top.encode("utf-8"),
        "03-seccion.svg": section.encode("utf-8"),
        "04-habitacion.json": _json_bytes(review),
        "05-solicitud.json": _json_bytes(request),
        "06-paneles-en-escena.csv": csv_out.getvalue().encode("utf-8"),
    }
    manifest = {
        "schema_version": "D19_REVIEW_BUNDLE_V1",
        "source_review_kind": source_kind,
        "layout_sha256": review["layout_sha256"],
        "room_status": review["status"],
        "section_y_mm": y_mm,
        "piece_count": review["piece_count"],
        "release": "NO_GO",
        "authenticity": "NOT_ESTABLISHED_BY_UNKEYED_MANIFEST",
        "files": {name: {"bytes": len(value), "sha256": _sha(value)}
                  for name, value in sorted(files.items())},
    }
    files["MANIFEST.json"] = _json_bytes(manifest)
    return _zip_content(files), manifest


def write_room_review_package(request: dict[str, Any], output_path: Path,
                              *, y_mm: int) -> dict[str, Any]:
    """Build a single portable ZIP, never overwriting any existing path."""
    source_kind = _validate_source_request(request)
    raw_request = _json_bytes(request)
    if len(raw_request) > _MAX_REQUEST_BYTES:
        raise RoomPackageError("Solicitud demasiado grande")
    if type(y_mm) is not int or not 0 <= y_mm <= 20000:
        raise RoomPackageError("Altura de sección inválida")
    from .room_spatial import review_room_from_specs, review_room_from_kitchen_state
    if source_kind == "room_layout_v1":
        review = review_room_from_specs(request)
    else:
        review = review_room_from_kitchen_state(request)
    payload, manifest = _render_verified_review(request, review, y_mm=y_mm)
    target = Path(output_path)
    if target.suffix.lower() != ".zip" or not target.parent.is_dir():
        raise RoomPackageError("Destino debe ser ZIP nuevo en una carpeta existente")
    # Render/validate BEFORE opening a destination, so failures never leave it.
    with target.open("xb") as file:
        file.write(payload)
    return {"path": str(target), "zip_sha256": _sha(payload), **manifest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Un ZIP de revisión nominal de habitación (sin fabricación)")
    parser.add_argument("--input", type=Path, required=True,
                        help="Solicitud room_layout_v1 original; no CAD precomputado")
    parser.add_argument("--output", type=Path, required=True,
                        help="Ruta ZIP NUEVA, jamás sobrescrita")
    parser.add_argument("--y-mm", type=int, required=True,
                        help="Cota real de sección horizontal en mm")
    args = parser.parse_args(argv)
    if (not args.input.is_file() or args.input.is_symlink()
            or args.input.stat().st_size > _MAX_REQUEST_BYTES):
        parser.error("Archivo de entrada inexistente, enlace o demasiado grande")
    request = json.loads(args.input.read_text(encoding="utf-8"),
                         object_pairs_hook=_unique_keys,
                         parse_constant=_no_constant)
    summary = write_room_review_package(request, args.output, y_mm=args.y_mm)
    print("D19=REVIEW_ONLY | PIECES=" + str(summary["piece_count"]) +
          " | ROOM_STATUS=" + summary["room_status"] +
          " | ZIP=" + summary["path"] +
          " | ZIP_SHA256=" + summary["zip_sha256"] +
          " | RELEASE=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
