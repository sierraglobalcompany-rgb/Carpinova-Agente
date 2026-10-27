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


    def test_mcp_read_review_png_returns_real_image_content(self):
        try:
            from mcp.server.fastmcp import Image as MCPImage
            import resvg_py
            from PIL import Image as PILImage
        except ImportError:
            self.skipTest("Optional rendering and official MCP SDK absent")
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                carpinova_generar_borrador(REQUEST, "image_001")
                carpinova_renderizar_lamina("image_001")
                result = carpinova_leer_entregable(
                    "image_001", "lamina/three-views.png")
                self.assertIsInstance(result, MCPImage)
                self.assertEqual(
                    result.data,
                    (Path(root) / "image_001/lamina/three-views.png").read_bytes(),
                )

    def test_png_preview_rejects_bad_manifest_and_external_symlink(self):
        try:
            import resvg_py
            from PIL import Image
        except ImportError:
            self.skipTest("Optional renderer absent")
        with TemporaryDirectory() as root, TemporaryDirectory() as outside:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                carpinova_generar_borrador(REQUEST, "image_guard")
                carpinova_renderizar_lamina("image_guard")
                sheet = Path(root) / "image_guard/lamina"
                manifest = sheet / "render-manifest.json"
                original = manifest.read_text(encoding="utf-8")
                item = json.loads(original)
                item["geometry_sha256"] = "0" * 64
                manifest.write_text(json.dumps(item), encoding="utf-8")
                with self.assertRaisesRegex(PilotError, "no corresponde"):
                    carpinova_leer_entregable(
                        "image_guard", "lamina/three-views.png")
                manifest.write_text(original, encoding="utf-8")
                image = sheet / "three-views.png"
                original_image = image.read_bytes()
                image.write_bytes(original_image + b"AFTER_RENDER_TAMPERING")
                with self.assertRaisesRegex(PilotError, "SHA-256 distinto"):
                    carpinova_leer_entregable(
                        "image_guard", "lamina/three-views.png")
                image.write_bytes(original_image)
                target = Path(outside) / "external.png"
                target.write_bytes(image.read_bytes())
                image.unlink()
                try:
                    image.symlink_to(target)
                except (OSError, NotImplementedError):
                    self.skipTest("Symlink privileges unavailable")
                with self.assertRaises(PilotError):
                    carpinova_leer_entregable(
                        "image_guard", "lamina/three-views.png")

    def test_png_preview_blocks_arbitrary_binaries_and_oversized_files(self):
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                carpinova_generar_borrador(REQUEST, "image_limit")
                for forbidden in (
                    "lamina/three-views.pdf", "native/native.blend",
                    "native/native.FCStd", "../private.png",
                ):
                    with self.subTest(forbidden=forbidden):
                        with self.assertRaises(PilotError):
                            carpinova_leer_entregable("image_limit", forbidden)
                folder = Path(root) / "image_limit/lamina"
                folder.mkdir()
                (folder / "three-views.png").write_bytes(
                    b"\x89PNG\r\n\x1a\n" + b"X" * (4 * 1024 * 1024))
                with self.assertRaisesRegex(PilotError, "límite"):
                    carpinova_leer_entregable(
                        "image_limit", "lamina/three-views.png")

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


    def test_real_mcp_four_drawers_inset_and_overlay_28_pieces(self):
        """Use the existing MCP tool entrypoints, not a mock geometry engine."""
        from carpinova_agent.cad_exchange import validate_exchange
        from carpinova_agent.modular_outputs import modular_bom_csv
        from io import StringIO
        import csv
        for style in ("INSET", "OVERLAY"):
            with self.subTest(style=style), TemporaryDirectory() as root:
                fixture = ROOT / "examples" / (
                    "four-drawer-500x500x800-" + style + "-UNCONFIRMED.json"
                )
                raw = fixture.read_text(encoding="utf-8")
                with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                    consult = carpinova_consultar(raw)
                    self.assertEqual(consult["modular"]["piece_count"], 28)
                    draft = carpinova_generar_borrador(raw, "four_" + style.lower())
                    self.assertEqual(draft["piece_count"], 28)
                    self.assertEqual(len(draft["files"]), 5)
                    for flag in ("fabrication_ready", "cutting_ready",
                                 "drilling_ready", "purchase_ready"):
                        self.assertIs(draft[flag], False)
                    cad = json.loads(carpinova_leer_entregable(
                        "four_" + style.lower(), "cad-exchange.json"
                    )["contenido"])
                    validate_exchange(cad)
                    self.assertEqual(len(cad["boxes"]), 28)
                    self.assertEqual(cad["geometry_sha256"], draft["geometry_sha256"])
                    self.assertEqual(cad["bounds_xyz_mm"],
                                     [500, 800, 518 if style == "OVERLAY" else 500])
                    csv_content = carpinova_leer_entregable(
                        "four_" + style.lower(), "parts-review.csv"
                    )["contenido"]
                    rows = list(csv.DictReader(StringIO(csv_content)))
                    self.assertEqual(len(rows), 28)
                    self.assertEqual(
                        {r["piece_id"] for r in rows},
                        {b["piece_id"] for b in cad["boxes"]}
                    )
                    svg = carpinova_leer_entregable(
                        "four_" + style.lower(), "front-review.svg"
                    )["contenido"]
                    self.assertIn("M1-D4-DRAWER_FACADE", svg)
                    self.assertFalse((Path(root) / ("four_" + style.lower()) /
                                      "native").exists())

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

    def test_wall_bar_review_pack_is_readable_and_tamper_protected(self):
        from carpinova_agent.pilot_cli import verify_pilot_bundle
        from xml.etree import ElementTree
        request = (ROOT / "examples" / "wall-bar-900-review.json").read_text(
            encoding="utf-8")
        with TemporaryDirectory() as root:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                response = carpinova_generar_borrador(request, "barra001")
                self.assertEqual(response["piece_count"], 21)
                self.assertEqual(len(response["files"]), 10)
                for letter in "ABC":
                    filename = f"CN-BAR-001-cajon-{letter}.svg"
                    delivered = carpinova_leer_entregable("barra001", filename)
                    drawing = ElementTree.fromstring(delivered["contenido"])
                    self.assertEqual(len([
                        node for node in drawing.iter()
                        if node.get("data-piece-id") is not None
                    ]), 5)
                schedule = carpinova_leer_entregable(
                    "barra001", "CN-BAR-001-referencias.csv")
                self.assertIn("E01", schedule["contenido"])
                self.assertIn("C05", schedule["contenido"])
                guide = carpinova_leer_entregable(
                    "barra001", "CN-BAR-001-guia-de-armado-REVISION.md")
                self.assertIn("NO FABRICAR", guide["contenido"])
                folder = Path(root) / "barra001"
                original = verify_pilot_bundle(folder)
                path = folder / "CN-BAR-001-cajon-C.svg"
                path.write_text(path.read_text(encoding="utf-8") + "ALTERADO",
                                encoding="utf-8")
                with self.assertRaisesRegex(PilotError, "distinto del CAD"):
                    verify_pilot_bundle(folder)
                self.assertEqual(len(original["boxes"]), 21)
                for flag in ("fabrication_ready", "cutting_ready",
                             "drilling_ready", "purchase_ready"):
                    self.assertFalse(response[flag])


if __name__ == "__main__":
    unittest.main()
