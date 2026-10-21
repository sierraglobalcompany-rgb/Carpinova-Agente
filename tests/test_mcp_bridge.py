"""MCP bridge contract QA: offline, no SDK install or external runtime required."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from carpinova_agent.maestro import MaestroError
from carpinova_agent.core import DesignError
from carpinova_agent.mcp_bridge import (
    carpinova_consultar, carpinova_estado, carpinova_generar_borrador,
    carpinova_leer_entregable, carpinova_renderizar_lamina,
    carpinova_exportar_3d,
)
from carpinova_agent.pilot_cli import PilotError


ROOT = Path(__file__).resolve().parents[1]
REQUEST = (ROOT / "examples" / "pilot-open-kitchen-800.json").read_text(encoding="utf-8")


class McpBridgeContractTests(unittest.TestCase):
    def test_status_is_honest_about_cad_fabrication(self):
        status = carpinova_estado()
        self.assertEqual(status["transport"], "stdio")
        self.assertFalse(status["freecad_blender_mcp_connected"])
        self.assertEqual(len(status["skills"]), 4)
        for field in ("fabrication_ready", "cutting_ready",
                      "drilling_ready", "purchase_ready"):
            self.assertFalse(status[field])

    def test_existing_maestro_consultation_is_reused(self):
        result = carpinova_consultar(REQUEST)
        self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(result["modular"]["piece_count"], 4)
        self.assertFalse(result["fabrication_ready"])

    def test_same_mcp_request_yields_five_review_artifacts(self):
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                result = carpinova_generar_borrador(REQUEST, "Mueble_001")
                self.assertEqual(result["piece_count"], 4)
                self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")
                self.assertEqual(len(result["files"]), 5)
                preview = carpinova_leer_entregable("Mueble_001", "front-review.svg")
                self.assertIn("svg", preview["contenido"].lower())
                cad = carpinova_leer_entregable("Mueble_001", "cad-exchange.json")
                self.assertEqual(json.loads(cad["contenido"])["geometry_sha256"],
                                 result["geometry_sha256"])
                self.assertFalse(preview["cutting_ready"])

    def test_missing_output_root_is_fail_closed(self):
        with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": ""}):
            with self.assertRaisesRegex(PilotError, "CARPINOVA_OUTPUT_ROOT"):
                carpinova_generar_borrador(REQUEST, "safe")

    def test_only_allowlisted_names_and_files(self):
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                for name in ("../outside", ".hidden", "/abs", "a/b", "", "x" * 80):
                    with self.subTest(name=name), self.assertRaises(PilotError):
                        carpinova_generar_borrador(REQUEST, name)
                for file in ("../../etc/passwd", "secrets.txt", "a.svg", ""):
                    with self.subTest(file=file), self.assertRaises(PilotError):
                        carpinova_leer_entregable("safe", file)

    def test_duplicate_keys_and_nan_rejected(self):
        for raw in ('{"action":"project","action":"modular"}',
                    '{"action":"project","project":{"x":NaN}}', "[]", ""):
            with self.subTest(raw=raw), self.assertRaises(MaestroError):
                carpinova_consultar(raw)

    def test_draft_never_overwrites_existing_result(self):
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                first = carpinova_generar_borrador(REQUEST, "prototype")
                with self.assertRaisesRegex(PilotError, "existente"):
                    carpinova_generar_borrador(REQUEST, "prototype")
                saved = json.loads(carpinova_leer_entregable(
                    "prototype", "manifest.json")["contenido"])
                self.assertEqual(first["geometry_sha256"], saved["geometry_sha256"])

    def test_layout_conflict_leaves_no_output_directory(self):
        invalid = json.loads(REQUEST)
        invalid["module_spec"]["width_mm"] = 801
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                with self.assertRaises(PilotError):
                    carpinova_generar_borrador(json.dumps(invalid), "blocked")
                self.assertFalse((Path(root) / "blocked").exists())

    def test_stage_does_not_run_native_cad(self):
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                with patch("integrations.freecad_from_contract.build_freecad",
                           side_effect=AssertionError("FreeCAD must not run")):
                    with patch("integrations.blender_from_contract.build_blender",
                               side_effect=AssertionError("Blender must not run")):
                        carpinova_generar_borrador(REQUEST, "no_external_apps")

    def test_outside_symlink_rejected_for_artifact_read(self):
        with TemporaryDirectory() as root, TemporaryDirectory() as outside:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                symlink = Path(root) / "external"
                try:
                    symlink.symlink_to(outside, target_is_directory=True)
                except (NotImplementedError, OSError):
                    self.skipTest("symlink privileges unavailable")
                with self.assertRaises(PilotError):
                    carpinova_leer_entregable("external", "manifest.json")


    def test_mcp_generates_3view_png_pdf_and_returns_paths(self):
        try:
            import resvg_py
            from PIL import Image
        except ImportError:
            self.skipTest("Optional resvg_py/Pillow rendering absent")
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                carpinova_generar_borrador(REQUEST, "lamina_001")
                result = carpinova_renderizar_lamina("lamina_001")
                self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")
                self.assertEqual(result["piece_count"], 4)
                self.assertTrue(Path(result["image_preview_png"]).read_bytes().startswith(
                    b"\x89PNG\r\n\x1a\n"))
                self.assertTrue(Path(result["printable_pdf"]).read_bytes().startswith(b"%PDF-"))
                view = carpinova_leer_entregable("lamina_001", "lamina/three-views.svg")
                self.assertIn(result["geometry_sha256"], view["contenido"])
                with self.assertRaisesRegex(DesignError, "existente"):
                    carpinova_renderizar_lamina("lamina_001")

    def test_mcp_render_rejects_unknown_project(self):
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                with self.assertRaises((FileNotFoundError, DesignError)):
                    carpinova_renderizar_lamina("not_existing")

    def test_mcp_blocks_cross_project_symlink_sheet_read(self):
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                carpinova_generar_borrador(REQUEST, "viewer")
                carpinova_generar_borrador(REQUEST, "foreign")
                path = Path(root) / "viewer" / "lamina"
                try:
                    path.symlink_to(Path(root) / "foreign", target_is_directory=True)
                except (OSError, NotImplementedError):
                    self.skipTest("Symlink unsupported")
                with self.assertRaises(PilotError):
                    carpinova_leer_entregable("viewer", "lamina/render-manifest.json")


    def test_native_execution_requires_explicit_local_enable(self):
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {
                "CARPINOVA_OUTPUT_ROOT": root,
                "CARPINOVA_NATIVE_EXECUTION_ENABLED": "0",
                "CARPINOVA_FREECADCMD": "",
                "CARPINOVA_BLENDER": "",
            }):
                carpinova_generar_borrador(REQUEST, "safe")
                with self.assertRaisesRegex(ValueError, "habilitación"):
                    carpinova_exportar_3d("safe", "AUTORIZO_EXPORTAR_BORRADOR_3D")
                self.assertFalse((Path(root) / "safe" / "native").exists())

if __name__ == "__main__":
    unittest.main()
