"""Nominal orthographic 3-view rendering; one verified CADExchange only."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from carpinova_agent.cad_exchange import cad_exchange
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.drawing_sheet import create_render_bundle, three_views_svg
from carpinova_agent.pilot_cli import write_pilot_bundle
from carpinova_agent.core import DesignError


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "pilot-open-kitchen-800.json"
REQUEST = json.loads(FIXTURE.read_text(encoding="utf-8"))


class SheetTests(unittest.TestCase):
    def test_exact_same_geometry_sha_and_external_dimensions(self):
        model = consult_maestro(REQUEST)["modular"]
        cad = cad_exchange(model)
        sheet = three_views_svg(cad)
        ElementTree.fromstring(sheet)
        self.assertIn(cad["geometry_sha256"], sheet)
        for text in ("800 mm", "720 mm", "550 mm", "4 piezas", "BORRADOR"):
            self.assertIn(text, sheet)
        self.assertEqual(sheet.count('class="part"'), 12)  # 4 original boxes x 3 views

    def test_three_views_are_not_fabrication_authority(self):
        cad = cad_exchange(consult_maestro(REQUEST)["modular"])
        sheet = three_views_svg(cad)
        self.assertIn("NO CORTAR, PERFORAR NI FABRICAR", sheet)
        self.assertIn("no resuelve líneas ocultas", sheet)
        self.assertNotIn("finished_cut_dimensions", sheet)

    def test_tampered_sha_or_geometry_fails_closed(self):
        cad = cad_exchange(consult_maestro(REQUEST)["modular"])
        cad["bounds_xyz_mm"][0] += 1
        with self.assertRaises(DesignError):
            three_views_svg(cad)

    def test_create_png_and_pdf_after_existing_pilot(self):
        try:
            import cairosvg
        except ImportError:
            self.skipTest("CairoSVG optional extra not installed here")
        with TemporaryDirectory() as td:
            destination = Path(td) / "cabinet"
            original = write_pilot_bundle(REQUEST, destination)
            sheet = create_render_bundle(destination)
            self.assertEqual(sheet["geometry_sha256"], original["geometry_sha256"])
            self.assertEqual(len(sheet["files"]), 4)
            for key in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
                self.assertFalse(sheet[key])
            self.assertTrue((destination / "lamina" / "three-views.png").read_bytes().startswith(
                b"\x89PNG\r\n\x1a\n"))
            self.assertTrue((destination / "lamina" / "three-views.pdf").read_bytes().startswith(
                b"%PDF-"))
            with self.assertRaisesRegex(DesignError, "existente"):
                create_render_bundle(destination)

    def test_mismatched_manifest_refuses_render(self):
        with TemporaryDirectory() as td:
            destination = Path(td) / "cabinet"
            write_pilot_bundle(REQUEST, destination)
            manifest = destination / "manifest.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["geometry_sha256"] = "0" * 64
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(DesignError, "inconsistente"):
                create_render_bundle(destination)
            self.assertFalse((destination / "lamina").exists())

    def test_missing_cairosvg_never_publishes_partial_render(self):
        with TemporaryDirectory() as td:
            destination = Path(td) / "cabinet"
            write_pilot_bundle(REQUEST, destination)
            with patch.dict("sys.modules", {"cairosvg": None}):
                with self.assertRaisesRegex(DesignError, "CairoSVG"):
                    create_render_bundle(destination)
            self.assertFalse((destination / "lamina").exists())


if __name__ == "__main__":
    unittest.main()
