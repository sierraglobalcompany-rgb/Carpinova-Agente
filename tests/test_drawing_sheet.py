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
        from carpinova_agent.drawing_sheet import generic_booklet_svgs
        self.assertNotIn("cajón", generic_booklet_svgs(model, cad)[-1].lower())
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
        from hashlib import sha256
        try:
            import resvg_py
            from PIL import Image
        except ImportError:
            self.skipTest("resvg_py/Pillow optional extras not installed here")
        with TemporaryDirectory() as td:
            destination = Path(td) / "cabinet"
            original = write_pilot_bundle(REQUEST, destination)
            sheet = create_render_bundle(destination)
            self.assertEqual(sheet["geometry_sha256"], original["geometry_sha256"])
            svg = (destination / "lamina" / "three-views.svg").read_bytes()
            pdf = (destination / "lamina" / "three-views.pdf").read_bytes()
            self.assertEqual(sha256(svg).hexdigest(), sheet["svg_sha256"])
            self.assertEqual(sha256(pdf).hexdigest(), sheet["pdf_sha256"])
            self.assertNotEqual(sha256(pdf + b"\\n% tamper check").hexdigest(),
                                sheet["pdf_sha256"])
            self.assertEqual(len(sheet["files"]), 5)
            self.assertEqual(sheet["booklet_pages"], 3)
            self.assertTrue((destination / "lamina" /
                             "CARPINOVA-planos-REVISION.pdf").is_file())
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

    def test_missing_resvg_never_publishes_partial_render(self):
        with TemporaryDirectory() as td:
            destination = Path(td) / "cabinet"
            write_pilot_bundle(REQUEST, destination)
            with patch.dict("sys.modules", {"resvg_py": None}):
                with self.assertRaisesRegex(DesignError, "resvg_py"):
                    create_render_bundle(destination)
            self.assertFalse((destination / "lamina").exists())


    def test_wall_bar_booklet_pdf_is_integrity_bound_and_seven_pages(self):
        try:
            import resvg_py
            from PIL import Image
        except ImportError:
            self.skipTest("PDF conversion optional dependencies unavailable")
        from hashlib import sha256
        request = json.loads((ROOT / "examples" /
                              "wall-bar-900-review.json").read_text(encoding="utf-8"))
        with TemporaryDirectory() as td:
            output = Path(td) / "barra"
            source = write_pilot_bundle(request, output)
            manifest = create_render_bundle(output)
            self.assertEqual(manifest["piece_count"], 28)
            self.assertEqual(manifest["geometry_sha256"], source["geometry_sha256"])
            self.assertEqual(manifest["booklet_pages"], 7)
            self.assertEqual(len(manifest["files"]), 5)
            pdf_path = output / "lamina" / "CN-BAR-001-planos-REVISION.pdf"
            pdf = pdf_path.read_bytes()
            self.assertTrue(pdf.startswith(b"%PDF-"))
            self.assertEqual(sha256(pdf).hexdigest(),
                             manifest["booklet_pdf_sha256"])
            for flag in ("fabrication_ready", "cutting_ready",
                         "drilling_ready", "purchase_ready"):
                self.assertFalse(manifest[flag])


    def test_generic_four_drawers_inset_overlay_have_unique_sheets(self):
        try:
            import resvg_py
            from PIL import Image
        except ImportError:
            self.skipTest("PDF converter optional")
        import re
        from carpinova_agent.drawing_sheet import generic_booklet_svgs
        for facade in ("INSET", "OVERLAY"):
            with self.subTest(style=facade), TemporaryDirectory() as td:
                request = json.loads((ROOT / "examples" /
                    f"four-drawer-500x500x800-{facade}-UNCONFIRMED.json"
                ).read_text(encoding="utf-8"))
                output = Path(td) / "furniture"
                source = write_pilot_bundle(request, output)
                model = consult_maestro(request)["modular"]
                cad = cad_exchange(model)
                svgs = generic_booklet_svgs(model, cad)
                self.assertEqual(len(svgs), 8)
                self.assertIn("correderas", svgs[-1])
                for ref in "ABCD":
                    self.assertTrue(any(f"CAJÓN {ref} · 6 PIEZAS" in sheet
                                        for sheet in svgs))
                for letter, drawing in zip("ABCD", svgs[1:5]):
                    root = ElementTree.fromstring(drawing)
                    callouts = [n for n in root.iter()
                                if n.get("data-visible-part-id") is not None]
                    leaders = [n for n in root.iter()
                               if n.get("data-leader-id") is not None]
                    self.assertEqual(len(callouts), 6)
                    self.assertEqual(len(leaders), 6)
                    self.assertEqual({n.get("data-visible-part-id") for n in callouts},
                                     {n.get("data-leader-id") for n in leaders})
                    self.assertEqual({n.text for n in callouts},
                                     {f"{letter}{idx:02d}" for idx in range(1,7)})
                for sheet in svgs:
                    ElementTree.fromstring(sheet)
                    self.assertIn(cad["geometry_sha256"], sheet)
                manifest = create_render_bundle(output)
                self.assertEqual(manifest["booklet_pages"], 8)
                self.assertEqual(manifest["piece_count"], 28)
                self.assertEqual(manifest["geometry_sha256"],
                                 source["geometry_sha256"])
                path = output / "lamina" / "CARPINOVA-planos-REVISION.pdf"
                self.assertEqual(
                    len(re.findall(rb"/Type\s*/Page\b", path.read_bytes())), 8)
                for flag in ("fabrication_ready", "cutting_ready",
                             "drilling_ready", "purchase_ready"):
                    self.assertFalse(manifest[flag])


if __name__ == "__main__":
    unittest.main()
