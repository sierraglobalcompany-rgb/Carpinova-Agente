"""Single-process local D19 editor using the existing nominal draft tool."""
from __future__ import annotations

import argparse
import copy
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlsplit
from zipfile import ZipFile

from .module_edits import validate_revision_list
from .room_review_package import (
    _MAX_PACKAGE_BYTES, _unique_keys, _no_constant,
    _validate_source_request,
)

_MEMBERS = {
    "LEER_PRIMERO.txt", "01-visor-3d.html", "02-planta.svg",
    "03-seccion.svg", "04-habitacion.json", "05-solicitud.json",
    "06-paneles-en-escena.csv", "MANIFEST.json",
}
_WALL_FIELDS = {
    "group_id", "module_id", "back_choice", "wall_system",
    "support_choice", "wall_substrate",
}
_BACK_COMMON = {"style", "material_id", "thickness_mm", "services_present", "grain_axis"}
_BACK_STRIPS = _BACK_COMMON | {"top_strip_height_mm", "bottom_strip_height_mm"}
_SAFE_NAME = re.compile(r"^editor-v[0-9]{6}$")
_LIMIT = 64 * 1024


class EditorError(ValueError):
    """A rejected local editing request with a safe user-facing reason."""


def _strict_json(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(text, object_pairs_hook=_unique_keys,
                          parse_constant=_no_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise EditorError("JSON UTF-8 inválido, duplicado o no finito") from exc


def _read_d19(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_PACKAGE_BYTES:
        raise EditorError("La entrada debe ser un D19 regular, no symlink, menor de 4 MB")
    try:
        with ZipFile(path) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if (set(names) != _MEMBERS or len(names) != len(_MEMBERS)
                    or any("/" in name or "\\" in name for name in names)
                    or sum(item.file_size for item in infos) > _MAX_PACKAGE_BYTES
                    or archive.testzip() is not None):
                raise EditorError("D19 inválido: requiere ocho archivos únicos, CRC y límites válidos")
            files = {name: archive.read(name) for name in names}
    except (OSError, ValueError) as exc:
        if isinstance(exc, EditorError):
            raise
        raise EditorError("No se pudo leer el D19") from exc
    manifest = _strict_json(files["MANIFEST.json"])
    expected = _MEMBERS - {"MANIFEST.json"}
    if (type(manifest) is not dict or set(manifest.get("files", {})) != expected
            or manifest.get("release") != "NO_GO"):
        raise EditorError("MANIFEST D19 no coincide con sus siete archivos")
    import hashlib
    for name in expected:
        record = manifest["files"][name]
        if (type(record) is not dict or set(record) != {"bytes", "sha256"}
                or type(record["bytes"]) is not int
                or record["bytes"] != len(files[name])
                or record["sha256"] != hashlib.sha256(files[name]).hexdigest()):
            raise EditorError("Hash o tamaño interno D19 inválido")
    request = _strict_json(files["05-solicitud.json"])
    if len(files["05-solicitud.json"]) > _LIMIT:
        raise EditorError("La solicitud D19 supera 64 KiB")
    _validate_source_request(request)
    return request


def _read_input(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_PACKAGE_BYTES:
        raise EditorError("Entrada inexistente, symlink o demasiado grande")
    if path.suffix.lower() == ".zip":
        return _read_d19(path)
    raw = path.read_bytes()
    if len(raw) > _LIMIT:
        raise EditorError("La solicitud JSON supera 64 KiB")
    request = _strict_json(raw)
    _validate_source_request(request)
    return request


def _validate_back(back: Any) -> Any:
    if back is None or back == "none":
        return back
    if type(back) is not dict:
        raise EditorError("back_spec debe ser null, none o una especificación F7C")
    style = back.get("style")
    allowed = _BACK_STRIPS if style == "inset_two_strips" else _BACK_COMMON
    if set(back) != allowed:
        raise EditorError("back_spec no cumple el esquema F7C exacto")
    if (style not in {"inset_full", "inset_two_strips"}
            or type(back.get("material_id")) is not str
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", back["material_id"])
            or type(back.get("thickness_mm")) is not int
            or not 1 <= back["thickness_mm"] <= 20000
            or type(back.get("services_present")) is not bool
            or back.get("grain_axis") not in {"face_x", "face_y", "none", "UNCONFIRMED"}):
        raise EditorError("back_spec contiene valores F7C inválidos")
    if style == "inset_two_strips" and any(
            type(back[field]) is not int or not 1 <= back[field] <= 20000
            for field in ("top_strip_height_mm", "bottom_strip_height_mm")):
        raise EditorError("Las dos franjas requieren alturas enteras positivas")
    return dict(back)


def _replace_by_key(rows: list[dict[str, Any]], item: dict[str, Any]) -> list[dict[str, Any]]:
    result = [row for row in rows if (row.get("group_id"), row.get("module_id")) !=
              (item["group_id"], item["module_id"])]
    result.append(item)
    return result


class EditorSession:
    def __init__(self, source_request: dict[str, Any], output_dir: Path, y_mm: int):
        self.request = copy.deepcopy(source_request)
        self.request.setdefault("module_edit_revisions", [])
        self.request.setdefault("wall_review_revisions", [])
        self.output_dir = output_dir
        self.y_mm = y_mm
        self.version = 0
        self.last_valid_path: Path | None = None
        self.last_valid_html = b""
        self.layout_sha256 = ""
        self.current_review: dict[str, Any] = {}
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)

    def _new_output(self, request: dict[str, Any], next_version: int):
        name = f"editor-v{next_version:06d}"
        if not _SAFE_NAME.fullmatch(name):
            raise EditorError("Identificador interno inválido")
        archive = self.output_dir / f"{name}-room-review.zip"
        extraction = self.output_dir / name
        if archive.exists() or archive.is_symlink() or extraction.exists() or extraction.is_symlink():
            raise EditorError("Colisión de salida; no se sobrescribió ningún archivo")
        from .mcp_bridge import carpinova_generar_borrador
        old = os.environ.get("CARPINOVA_OUTPUT_ROOT")
        os.environ["CARPINOVA_OUTPUT_ROOT"] = str(self.output_dir)
        try:
            try:
                result = carpinova_generar_borrador(
                    solicitud_json=json.dumps(request, ensure_ascii=False, allow_nan=False),
                    proyecto=name, incluir_planos=False, seccion_y_mm=self.y_mm,
                )
            except Exception as exc:
                if archive.exists() and archive.parent == self.output_dir:
                    archive.unlink()
                if isinstance(exc, ValueError):
                    raise EditorError(_safe_text(exc)) from exc
                raise
        finally:
            if old is None:
                os.environ.pop("CARPINOVA_OUTPUT_ROOT", None)
            else:
                os.environ["CARPINOVA_OUTPUT_ROOT"] = old
        if (result.get("release") != "NO_GO" or result.get("can_generate_f7c") is not False
                or any(result.get(flag) is not False for flag in (
                    "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"))
                or result.get("room_status", "REVIEW_ONLY") != "REVIEW_ONLY"):
            if archive.exists() and not archive.is_symlink():
                archive.unlink()
            raise EditorError("El borrador no superó los guardrails de revisión")
        reported_path = Path(result.get("room_package_path", ""))
        if reported_path.absolute() != archive.absolute() or archive.is_symlink():
            if archive.exists() and not archive.is_symlink():
                archive.unlink()
            raise EditorError("La herramienta devolvió una ruta de salida inesperada")
        zip_path = archive.resolve(strict=True)
        try:
            files = _read_archive(zip_path)
            review = _strict_json(files["04-habitacion.json"])
            if (review.get("status") != "REVIEW_ONLY"
                    or review.get("layout_sha256") != result.get("layout_sha256")
                    or review.get("piece_count") != result.get("piece_count")):
                raise EditorError("La respuesta pública no coincide con el D19 generado")
            extraction.mkdir(exist_ok=False)
            for member, data in files.items():
                (extraction / member).write_bytes(data)
            html = files["01-visor-3d.html"]
        except Exception as exc:
            if zip_path.parent == self.output_dir and zip_path.name == f"{name}-room-review.zip":
                zip_path.unlink(missing_ok=True)
            if extraction.exists() and extraction.parent == self.output_dir:
                for child in extraction.iterdir():
                    if child.is_file() and not child.is_symlink():
                        child.unlink()
                extraction.rmdir()
            if isinstance(exc, ValueError):
                raise EditorError(_safe_text(exc)) from exc
            raise
        return result, zip_path, extraction, html, review

    def initialize(self) -> None:
        result, zip_path, extraction, html, review = self._new_output(self.request, 1)
        self.version = 1
        self.last_valid_path = extraction
        self.last_valid_html = html
        self.layout_sha256 = result["layout_sha256"]
        self.current_review = review

    def apply(self, payload: Any) -> dict[str, Any]:
        with self.lock:
            if type(payload) is not dict or set(payload) != {
                "version", "group_id", "module_id", "wall_revision", "back_spec",
                "replace_existing_ties", "module_edit",
            }:
                raise EditorError("Solicitud apply con esquema inválido")
            if type(payload["version"]) is not int:
                raise EditorError("version debe ser entero")
            if payload["version"] != self.version:
                raise StaleVersion(self.version)
            group, module = payload["group_id"], payload["module_id"]
            if (type(group) is not str or type(module) is not str
                    or not any(row["group_id"] == group and row["module_id"] == module
                               for row in self.current_review.get("module_edit_index", []))):
                raise EditorError("Módulo inexistente en el D19 vigente")
            wall, back, edit = payload["wall_revision"], _validate_back(payload["back_spec"]), payload["module_edit"]
            replace = payload["replace_existing_ties"]
            if type(replace) is not bool:
                raise EditorError("replace_existing_ties debe ser booleano explícito")
            if wall is not None and (type(wall) is not dict or set(wall) != _WALL_FIELDS
                                     or wall.get("group_id") != group
                                     or wall.get("module_id") != module):
                raise EditorError("wall_revision requiere seis campos e identidad exacta")
            if edit is not None:
                if type(edit) is not dict or edit.get("group_id") != group or edit.get("module_id") != module:
                    raise EditorError("module_edit requiere siete campos e identidad exacta")
                edit = validate_revision_list([edit])[0]
            if wall is None and edit is None:
                raise EditorError("Indica wall_revision o module_edit")
            if back is not None and (wall is None or wall.get("back_choice") == "keep_existing"):
                raise EditorError("back_spec requiere una wall_revision que cambie el fondo")
            choices = {
                "keep_existing": None, "none": "none",
                "inset_board_3mm_review": ("inset_full", 3),
                "inset_board_15mm_review": ("inset_full", 15),
                "inset_board_18mm_review": ("inset_full", 18),
                "inset_two_strips_review": ("inset_two_strips", None),
                "inset_carcass_material_review": ("inset_full", None),
            }
            if wall is not None and wall["back_choice"] not in choices:
                raise EditorError("back_choice no admitido")
            if wall is not None:
                expected = choices[wall["back_choice"]]
                if expected is None and back is not None:
                    raise EditorError("La selección mural no corresponde al back_spec")
                if expected == "none" and back != "none":
                    raise EditorError("back_choice=none requiere back_spec=none")
                if type(expected) is tuple and (type(back) is not dict
                        or back.get("style") != expected[0]
                        or (expected[1] is not None and back.get("thickness_mm") != expected[1])):
                    raise EditorError("El fondo F7C no coincide con back_choice")
            current_ties = any(
                box.get("group_id") == group and box.get("module_id") == module
                and box.get("role") in {"wall_rear_lower_tie", "wall_rear_upper_tie",
                                        "upper_rear_tie", "lower_rear_tie"}
                for box in self.current_review.get("world_boxes", [])
            )
            if replace and (not current_ties or type(back) is not dict):
                raise EditorError("Sustitución marcada sin un par de amarres y fondo nuevo")
            if current_ties and type(back) is dict and not replace:
                raise EditorError("Confirma explícitamente sustituir los amarres existentes")
            candidate = copy.deepcopy(self.request)
            if edit is not None:
                candidate["module_edit_revisions"] = _replace_by_key(
                    candidate.get("module_edit_revisions", []), edit,
                )
                saved_wall = next((row for row in candidate.get("wall_review_revisions", [])
                                   if row.get("group_id") == group
                                   and row.get("module_id") == module), None)
                if (saved_wall is not None and wall is None
                        and saved_wall["support_choice"] not in {
                            "keep_existing", edit["support_style"]}):
                    raise EditorError("Actualiza support_choice a keep_existing o al nuevo apoyo")
            if wall is not None:
                if edit is not None and wall["support_choice"] not in {
                        "keep_existing", edit["support_style"]}:
                    raise EditorError("support_choice contradice el nuevo apoyo dimensional")
                candidate["wall_review_revisions"] = _replace_by_key(
                    candidate.get("wall_review_revisions", []), wall,
                )
            if back is not None:
                if candidate["review_kind"] == "kitchen_spatial_v1":
                    old = next((row for row in candidate.get("back_revisions", [])
                                if row.get("group_id") == group and row.get("module_id") == module), None)
                    revision = {"group_id": group, "module_id": module, "back": back}
                    if old and "horizontal_divider_depth_mm" in old:
                        revision["horizontal_divider_depth_mm"] = old["horizontal_divider_depth_mm"]
                    if old and "wall_rear_ties" in old:
                        if back == "none":
                            revision["wall_rear_ties"] = old["wall_rear_ties"]
                        elif not replace:
                            raise EditorError("Confirma la sustitución de amarres existentes")
                    candidate["back_revisions"] = _replace_by_key(
                        candidate.get("back_revisions", []), revision,
                    )
                else:
                    assembly = next(row for row in candidate["assemblies"]
                                    if row["group_id"] == group)
                    target = next(row for row in assembly["module_spec"]["modules"]
                                  if row["module_id"] == module)
                    if replace:
                        target.pop("wall_rear_ties", None)
                    target["back"] = back
            try:
                _validate_source_request(candidate)
            except ValueError as exc:
                raise EditorError(str(exc)) from exc
            next_version = self.version + 1
            result, zip_path, extraction, html, review = self._new_output(candidate, next_version)
            old_digest = self.layout_sha256
            self.request = candidate
            self.version = next_version
            self.last_valid_path = extraction
            self.last_valid_html = html
            self.layout_sha256 = result["layout_sha256"]
            self.current_review = review
            return {
                "ok": True, "version": self.version,
                "result": "GEOMETRY_UPDATED" if old_digest != self.layout_sha256
                          else "REVIEW_SAVED_NO_GEOMETRY_CHANGE",
                "layout_sha256": self.layout_sha256,
            }


class StaleVersion(EditorError):
    def __init__(self, current: int):
        super().__init__("La revisión está desactualizada; recarga la vista para obtener la última versión")
        self.current = current


def _read_archive(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as archive:
        infos = archive.infolist()
        if (len(infos) != len(_MEMBERS) or set(item.filename for item in infos) != _MEMBERS
                or sum(item.file_size for item in infos) > _MAX_PACKAGE_BYTES
                or archive.testzip() is not None):
            raise EditorError("El borrador generado no cumple D19 de ocho archivos")
        files = {item.filename: archive.read(item.filename) for item in infos}
    manifest = _strict_json(files["MANIFEST.json"])
    if type(manifest) is not dict or set(manifest.get("files", {})) != _MEMBERS - {"MANIFEST.json"}:
        raise EditorError("El manifiesto D19 generado no cubre sus siete archivos")
    import hashlib
    for name, record in manifest["files"].items():
        if (type(record) is not dict or set(record) != {"bytes", "sha256"}
                or record["bytes"] != len(files[name])
                or record["sha256"] != hashlib.sha256(files[name]).hexdigest()):
            raise EditorError("El manifiesto D19 generado no valida bytes y hashes")
    return files


def _safe_text(value: str) -> str:
    return " ".join(str(value).split())[:300]


def create_server(session: EditorSession) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "CarpiNovaLocal/1"
        sys_version = ""

        def log_message(self, _format: str, *args: Any) -> None:
            return

        def _headers(self, status: int, body: bytes = b"", content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _host_ok(self) -> bool:
            values = self.headers.get_all("Host") or []
            return (len(values) == 1
                    and values[0] == f"127.0.0.1:{self.server.server_port}")

        def do_GET(self) -> None:
            raw_names = [name.lower() for name, _value in self.headers.raw_items()]
            if len(raw_names) != len(set(raw_names)):
                self._headers(400, b'{"ok":false,"message":"Duplicate request headers"}')
                return
            parsed = urlsplit(self.path)
            if parsed.path == "/favicon.ico" and not parsed.query:
                self._headers(204, b"", "text/plain")
                return
            if parsed.path != "/" or parsed.query or not self._host_ok():
                self._headers(404, b'{"ok":false,"message":"Ruta no disponible"}')
                return
            config = json.dumps({"token": session.token, "version": session.version},
                                separators=(",", ":"))
            config = config.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            html = session.last_valid_html.replace(
                b"</head>", ("<script>window.CARPNOVA_EDITOR_SESSION=" + config
                             + ";</script></head>").encode("utf-8"), 1,
            )
            self._headers(200, html, "text/html; charset=utf-8")

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/apply" or urlsplit(self.path).query:
                self._headers(404, b'{"ok":false,"message":"Ruta no disponible"}')
                return
            raw_names = [name.lower() for name, _value in self.headers.raw_items()]
            if len(raw_names) != len(set(raw_names)):
                self._headers(400, b'{"ok":false,"message":"Duplicate request headers"}')
                return
            origins = self.headers.get_all("Origin") or []
            if (not self._host_ok() or len(origins) != 1
                    or origins[0] != f"http://127.0.0.1:{self.server.server_port}"):
                self._headers(403, b'{"ok":false,"message":"Origen local no autorizado"}')
                return
            if self.headers.get_all("Transfer-Encoding") or len(self.headers.get_all("Content-Length") or []) != 1:
                self._headers(400, b'{"ok":false,"message":"Invalid HTTP headers"}')
                return
            lengths = self.headers.get_all("Content-Length") or []
            if not lengths[0].isdigit():
                self._headers(400, b'{"ok":false,"message":"Invalid Content-Length"}')
                return
            length = int(lengths[0])
            if length > _LIMIT:
                self._headers(413, b'{"ok":false,"message":"Solicitud mayor de 64 KiB"}')
                return
            media = self.headers.get_all("Content-Type") or []
            if (len(media) != 1 or not re.fullmatch(
                    r"application/json(?:\s*;\s*charset=utf-8)?", media[0], re.I)):
                self._headers(415, b'{"ok":false,"message":"Se requiere application/json UTF-8"}')
                return
            supplied = self.headers.get_all("X-CarpiNova-Session") or []
            if len(supplied) != 1 or not hmac.compare_digest(supplied[0], session.token):
                self._headers(403, b'{"ok":false,"message":"Local session rejected"}')
                return
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise EditorError("Cuerpo HTTP incompleto")
                payload = _strict_json(raw)
            except EditorError:
                self._headers(400, b'{"ok":false,"message":"Malformed JSON body"}')
                return
            try:
                answer = session.apply(payload)
                self._headers(200, json.dumps(answer, separators=(",", ":")).encode())
            except StaleVersion as exc:
                body = {"ok": False, "version": exc.current, "message": str(exc)}
                self._headers(409, json.dumps(body, ensure_ascii=False).encode())
            except EditorError as exc:
                body = {"ok": False, "version": session.version, "message": _safe_text(exc)}
                self._headers(422, json.dumps(body, ensure_ascii=False).encode())
            except Exception:
                body = {"ok": False, "version": session.version,
                        "message": "No se pudo aplicar la revisión; la versión anterior sigue vigente"}
                self._headers(500, json.dumps(body, ensure_ascii=False).encode())

        def do_OPTIONS(self) -> None:
            self._headers(404, b'{"ok":false,"message":"Ruta no disponible"}')

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.session = session  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Editor local D19 nominal de CarpiNova")
    parser.add_argument("--input", type=Path, required=True, help="05-solicitud.json o ZIP D19 validado")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directorio absoluto NUEVO, no se sobrescribe")
    parser.add_argument("--y-mm", type=int, required=True, help="Cota de sección existente en mm")
    args = parser.parse_args(argv)
    try:
        source = _read_input(args.input)
        target = args.output_dir
        if (not target.is_absolute() or target.exists() or target.is_symlink()
                or not target.parent.is_dir()):
            raise EditorError("output-dir debe ser una ruta absoluta nueva con padre existente")
        if type(args.y_mm) is not int or not 0 <= args.y_mm <= 20000:
            raise EditorError("--y-mm debe ser un entero entre 0 y 20000")
        target.mkdir(exist_ok=False)
        if target.is_symlink() or target.resolve(strict=True) != target:
            target.rmdir()
            raise EditorError("output-dir debe ser un directorio real no enlazado")
        session = EditorSession(source, target, args.y_mm)
        session.initialize()
    except Exception as exc:
        parser.error(_safe_text(exc))
    server = create_server(session)
    print(f"Editor local CarpiNova · revisión nominal · NO_GO\nhttp://127.0.0.1:{server.server_port}/\nCtrl+C para cerrar", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEditor local cerrado.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
