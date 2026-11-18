from __future__ import annotations

import json
from pathlib import Path
import unittest
from xml.etree import ElementTree

from carpinova_agent.cad_exchange import cad_exchange
from carpinova_agent.drawing_sheet import three_views_svg
from carpinova_agent.wall_bar import design_wall_bar
from carpinova_agent.wall_bar_delivery import review_booklet_svgs
from carpinova_agent.wall_bar_sheets import wall_bar_isometric_svg

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "wall-bar-900-review-p5.json"
HANDLE = "handle-visual-only"
EXPECTED_GEOMETRY = "5c0b8944ba015ef537688afac3ee58b9dd52011267c28278c9134a473cecf947"


def model():
    request = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return design_wall_bar(request["module_spec"])


def handle_symbols(svg: str):
    root = ElementTree.fromstring(svg)
    return [node for node in root.iter()
            if node.get("data-concept") == HANDLE]


class R3IllustrativeHandleTests(unittest.TestCase):
    def test_isometric_draws_three_non_cad_facade_symbols_without_geometry_change(self):
        draft = model()
        cad = cad_exchange(draft)
        symbols = handle_symbols(wall_bar_isometric_svg(draft))
        expected_ids = {part["piece_id"] for part in draft["parts"]
                        if part["role"] == "drawer_facade"}
        self.assertEqual(len(symbols), 3)
        self.assertEqual({node.get("data-source-piece-id") for node in symbols},
                         expected_ids)
        self.assertTrue(all(node.tag.endswith("path") for node in symbols))
        self.assertTrue(all(node.get("data-piece-id") is None for node in symbols))
        self.assertEqual(cad["geometry_sha256"], EXPECTED_GEOMETRY)
        self.assertEqual(len(cad["boxes"]), 28)
        self.assertEqual(draft["status"], "DRAFT_NOT_FOR_CUTTING")
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready",
                     "purchase_ready"):
            self.assertIs(draft[flag], False)

    def test_distribution_sheet_draws_symbols_and_keeps_disclosures(self):
        draft = model()
        pages = review_booklet_svgs(draft)
        self.assertEqual(len(pages), 7)
        page = pages[4]
        symbols = handle_symbols(page)
        self.assertEqual(len(symbols), 3)
        self.assertEqual({node.get("data-source-piece-id") for node in symbols},
                         {part["piece_id"] for part in draft["parts"]
                          if part["role"] == "drawer_facade"})
        for letter in "ABC":
            self.assertIn(f'data-front-letter="{letter}"', page)
        self.assertIn("Tiradores negros ilustrativos; tamaño, posición y fijación NO definidos", page)
        self.assertIn("INVALID_RAW_VS_FINISHED", page)
        self.assertIn("el cero no se acepta como holgura", page)

    def test_symbols_are_omitted_when_handle_intent_is_not_selected(self):
        draft = model()
        for part in draft["parts"]:
            if part["role"] == "drawer_facade":
                part["opening_system"] = "pending"
        self.assertEqual(handle_symbols(wall_bar_isometric_svg(draft)), [])
        self.assertEqual(handle_symbols(review_booklet_svgs(draft)[4]), [])

    def test_cad_pure_three_views_contain_no_presentation_handles(self):
        draft = model()
        cad_svg = three_views_svg(cad_exchange(draft))
        self.assertEqual(handle_symbols(cad_svg), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
