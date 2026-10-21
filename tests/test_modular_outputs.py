"""F6 SVG and CSV must be faithful to the same draft data, never cut-ready."""
import csv
from io import StringIO
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from carpinova_agent.core import DesignError
from carpinova_agent.modular import design_modular_run
from carpinova_agent.modular_outputs import modular_front_svg, modular_bom_csv

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def fixture():
    return json.loads((EXAMPLES / "modular-closet.json").read_text(encoding="utf-8"))


class ModularOutputTests(unittest.TestCase):
    def test_svg_parseable_and_dimensioned(self):
        model = design_modular_run(fixture())
        drawing = modular_front_svg(model)
        root = ET.fromstring(drawing)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertIn("2000 mm", drawing)
        self.assertIn("2400 mm", drawing)
        self.assertIn("NO CORTAR", drawing)
        self.assertIn("LEFT", drawing)
        self.assertIn("RIGHT", drawing)
        self.assertEqual(len(root.findall("{http://www.w3.org/2000/svg}rect")), 8)

    def test_panels_use_exact_model_coordinates(self):
        model = design_modular_run(fixture())
        drawing = modular_front_svg(model)
        for p in model["parts"]:
            self.assertIn(p["piece_id"], drawing)

    def test_csv_has_exactly_one_row_per_piece(self):
        model = design_modular_run(fixture())
        rows = list(csv.DictReader(StringIO(modular_bom_csv(model))))
        self.assertEqual(len(rows), model["piece_count"])
        self.assertEqual({r["piece_id"] for r in rows},
                         {p["piece_id"] for p in model["parts"]})
        self.assertTrue(all(r["production_status"] == "BORRADOR_NO_CORTAR" for r in rows))

    def test_csv_provenance_and_grain(self):
        model = design_modular_run(fixture())
        rows = {row["piece_id"]: row for row in
                csv.DictReader(StringIO(modular_bom_csv(model)))}
        self.assertEqual(rows["LEFT-TOP"]["nominal_face_x_mm"], "914")
        self.assertEqual(rows["LEFT-TOP"]["grain_axis"], "face_x")
        self.assertEqual(rows["LEFT-LEFT_SIDE"]["edgebanding_nominal_total_mm"], "2400")
        self.assertEqual(rows["RIGHT-RIGHT_SIDE"]["origin_x_mm"], "1982")

    def test_csv_unconfirmed_is_never_zero(self):
        data = json.loads((EXAMPLES / "modular-kitchen.json").read_text())
        out = design_modular_run(data)
        first = next(csv.DictReader(StringIO(modular_bom_csv(out))))
        self.assertEqual(first["grain_axis"], "UNCONFIRMED")
        self.assertEqual(first["edgebanding_thickness_mm"], "UNCONFIRMED")
        self.assertEqual(first["edgebanding_nominal_total_mm"], "UNCONFIRMED")

    def test_blocked_site_no_exports(self):
        spec = fixture()
        spec["site_width_mm"]["bottom"] = 1990
        model = design_modular_run(spec)
        with self.assertRaises(DesignError):
            modular_bom_csv(model)
        with self.assertRaises(DesignError):
            modular_front_svg(model)

    def test_unclosed_layout_no_exports(self):
        spec = fixture()
        spec["modules"][1]["width_mm"] = 1000
        model = design_modular_run(spec)
        with self.assertRaises(DesignError):
            modular_bom_csv(model)
        with self.assertRaises(DesignError):
            modular_front_svg(model)

    def test_non_draft_cannot_trick_exporter(self):
        model = design_modular_run(fixture())
        model["status"] = "RELEASED"
        with self.assertRaises(DesignError):
            modular_front_svg(model)

    def test_impossible_panel_coordinates_block_drawing(self):
        model = design_modular_run(fixture())
        model["parts"][0]["nominal_origin_xyz_mm"] = [-1, 0, 0]
        with self.assertRaises(DesignError):
            modular_front_svg(model)

    def test_csv_does_not_contain_finished_cut_sizes(self):
        result = modular_bom_csv(design_modular_run(fixture()))
        self.assertNotIn("finished_cut_dimensions", result)
        self.assertNotIn("READY_TO_CUT", result)


if __name__ == "__main__":
    unittest.main()
