from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from carpinova_agent import mcp_bridge
from carpinova_agent.room_editor_local import (
    EditorError, EditorSession, _read_d19, _read_input,
    _read_d19_with_manifest, create_server,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "room_review_d19" / "f9a_room_public.json"


def source_request() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["request"]


class H10M3EditorUsableFocalTests(unittest.TestCase):
    def test_saved_zip_download_is_authenticated_bounded_and_version_stable(self):
        request = source_request()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            output.mkdir()
            session = EditorSession(request, output, 350)
            session.initialize()
            self.assertEqual(session.version, 1)
            self.assertEqual(session.last_valid_path, output / "editor-v000001")
            self.assertEqual(session.last_valid_zip_path,
                             output / "editor-v000001-room-review.zip")
            saved = session.last_valid_zip_path.read_bytes()
            self.assertEqual(session.last_valid_zip_sha256,
                             hashlib.sha256(saved).hexdigest())

            server = create_server(session)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(base + "/download", timeout=3)
                self.assertEqual(rejected.exception.code, 403)

                page = urlopen(base + "/", timeout=3).read().decode("utf-8")
                self.assertIn("EDITOR LOCAL · conectado", page)
                self.assertIn('id="downloadSavedProject"', page)
                self.assertIn('id="applyModuleChanges"', page)
                self.assertIn('id="editorModeStatus"', page)

                request = Request(base + "/download", headers={
                    "X-CarpiNova-Session": session.token,
                })
                with urlopen(request, timeout=3) as response:
                    downloaded = response.read()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get_content_type(), "application/zip")
                    self.assertEqual(response.headers["Content-Disposition"],
                                     'attachment; filename="editor-v000001-room-review.zip"')
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(downloaded, saved)
                self.assertEqual(hashlib.sha256(downloaded).hexdigest(),
                                 session.last_valid_zip_sha256)
                self.assertEqual(session.version, 1)

                outside = Path(temporary) / "outside"
                outside.mkdir()
                outside_zip = outside / "editor-v000001-room-review.zip"
                outside_zip.write_bytes(saved)
                valid_path = session.last_valid_zip_path
                session.last_valid_zip_path = outside_zip
                with self.assertRaises(HTTPError) as invalid_path:
                    urlopen(request, timeout=3)
                self.assertEqual(invalid_path.exception.code, 404)
                session.last_valid_zip_path = valid_path

                session.last_valid_zip_sha256 = "0" * 64
                with self.assertRaises(HTTPError) as altered:
                    urlopen(request, timeout=3)
                self.assertEqual(altered.exception.code, 422)
                self.assertEqual(session.version, 1)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)

    def test_reader_hash_transaction_and_mcp_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            output.mkdir()
            session = EditorSession(source_request(), output, 350)
            session.initialize()
            request, manifest = _read_d19_with_manifest(session.last_valid_zip_path)
            self.assertEqual(request, _read_d19(session.last_valid_zip_path))
            self.assertEqual(request, _read_input(session.last_valid_zip_path))
            self.assertEqual(manifest["section_y_mm"], 350)

            invalid = Path(temporary) / "invalid-section.zip"
            with ZipFile(session.last_valid_zip_path) as original:
                members = {name: original.read(name) for name in original.namelist()}
            changed = json.loads(members["MANIFEST.json"])
            changed["section_y_mm"] = True
            members["MANIFEST.json"] = json.dumps(changed).encode("utf-8")
            with ZipFile(invalid, "w", compression=ZIP_DEFLATED) as archive:
                for name, content in members.items():
                    archive.writestr(name, content)
            with self.assertRaises(EditorError):
                _read_d19_with_manifest(invalid)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            output.mkdir()
            session = EditorSession(source_request(), output, 350)
            original = mcp_bridge.carpinova_generar_borrador

            def wrong_hash(**kwargs):
                result = original(**kwargs)
                result["zip_sha256"] = "0" * 64
                return result

            with patch.object(mcp_bridge, "carpinova_generar_borrador", wrong_hash):
                with self.assertRaisesRegex(EditorError, "SHA-256"):
                    session.initialize()
            self.assertEqual(session.version, 0)
            self.assertIsNone(session.last_valid_path)
            self.assertIsNone(session.last_valid_zip_path)
            self.assertEqual(session.last_valid_zip_sha256, "")
            self.assertFalse((output / "editor-v000001-room-review.zip").exists())

        request = source_request()
        digest = "f" * 64
        files = {name: {"bytes": 1, "sha256": "a" * 64} for name in (
            "LEER_PRIMERO.txt", "01-visor-3d.html", "02-planta.svg",
            "03-seccion.svg", "04-habitacion.json", "05-solicitud.json",
            "06-paneles-en-escena.csv",
        )}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(mcp_bridge, "_output_root", return_value=root), \
                    patch("carpinova_agent.room_review_package.write_room_review_package",
                          return_value={
                              "path": str(root / "project-room-review.zip"),
                              "zip_sha256": "b" * 64, "layout_sha256": "c" * 64,
                              "piece_count": 9, "section_y_mm": 350,
                              "release": "NO_GO", "room_status": "REVIEW_ONLY",
                              "files": files, "wall_fixation_sha256": digest,
                          }):
                result = mcp_bridge.carpinova_generar_borrador(
                    json.dumps(request), "H10_M3_TEST_WITH_FIXATION",
                    incluir_planos=False, seccion_y_mm=350,
                )
            self.assertEqual(result["wall_fixation_sha256"], digest)
            self.assertTrue(any("ABRIR_CARPINOVA.cmd" in warning
                                for warning in result["warnings"]))
            without_digest = {key: value for key, value in {
                "path": str(root / "without-digest-room-review.zip"),
                "zip_sha256": "d" * 64, "layout_sha256": "e" * 64,
                "piece_count": 9, "section_y_mm": 350,
                "release": "NO_GO", "room_status": "REVIEW_ONLY",
                "files": files,
            }.items()}
            with patch.object(mcp_bridge, "_output_root", return_value=root), \
                    patch("carpinova_agent.room_review_package.write_room_review_package",
                          return_value=without_digest):
                omitted = mcp_bridge.carpinova_generar_borrador(
                    json.dumps(request), "H10_M3_TEST_WITHOUT_FIXATION",
                    incluir_planos=False, seccion_y_mm=350,
                )
            self.assertNotIn("wall_fixation_sha256", omitted)


if __name__ == "__main__":
    unittest.main()
