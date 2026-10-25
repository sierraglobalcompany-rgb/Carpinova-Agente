"""A confirmed leg/plinth concept survives the F1-to-F7C handoff safely."""
import copy
import json
from pathlib import Path
import unittest

from carpinova_agent.core import DesignError
from carpinova_agent.drawer_modules import guide_drawer_layout
from carpinova_agent.modular import design_modular_run

ROOT = Path(__file__).resolve().parents[1]


def prepared_with_legs(height=100):
    request = json.loads((ROOT / "examples" /
        "four-drawer-500x500x800-OVERLAY-UNCONFIRMED.json").read_text(encoding="utf-8"))
    guide = guide_drawer_layout({
        "type": "drawer_layout_guide", "width_mm": 500,
        "height_mm": 800, "depth_mm": 500, "small_drawers": 3,
        "construction": "sides_full", "support_style": "legs",
        "support_height_mm": height,
    })
    spec = request["module_spec"]
    spec["height_mm"] = guide["carcass_height_mm"]
    module = spec["modules"][0]
    module["drawer_layout_reference"] = guide["proposed_layout_spec"]
    module["support_concept"] = {
        "style": "legs", "support_height_mm": height,
        "overall_height_mm": guide["overall_height_mm"],
    }
    for drawer, opening in zip(module["drawers"], guide["opening_plan"]):
        drawer["opening_bottom_offset_mm"] = opening["opening_bottom_offset_mm"]
        drawer["opening_height_mm"] = opening["opening_height_mm"]
        # Example box heights are illustrative; keep each box inside the new
        # opening rather than carrying prototype dimensions into new carcass.
        drawer["box_height_mm"] = min(drawer["box_height_mm"],
                                       opening["opening_height_mm"] - 25)
    return request


class SupportTransferTests(unittest.TestCase):
    def test_legs_preserve_total_height_and_drawer_layout_without_fake_parts(self):
        req = prepared_with_legs()
        model = design_modular_run(req["module_spec"])
        support = model["modules"][0]["support_review"]
        self.assertEqual(model["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(model["dimensions_mm"]["height"], 700)
        self.assertEqual(support["carcass_height_mm"], 700)
        self.assertEqual(support["support_height_mm"], 100)
        self.assertEqual(support["overall_height_mm"], 800)
        self.assertEqual(support["style"], "legs")
        self.assertIsNone(support["physical_support_parts"])
        self.assertEqual(support["physical_support_specification"], "NOT_VERIFIED")
        self.assertTrue(any("NO añadir patas" in b for b in model["blockers"]))
        self.assertFalse(any("LEG" in p["piece_id"] for p in model["parts"]))
        for key in ("fabrication_ready", "cutting_ready",
                    "drilling_ready", "purchase_ready"):
            self.assertIs(model[key], False)

    def test_inconsistent_carcass_support_heights_are_rejected(self):
        for field, value in (("overall_height_mm", 900),
                             ("support_height_mm", 150),
                             ("style", "floor_direct")):
            with self.subTest(field=field):
                req = prepared_with_legs()
                req["module_spec"]["modules"][0]["support_concept"][field] = value
                with self.assertRaises(DesignError):
                    design_modular_run(req["module_spec"])

    def test_missing_or_unsafe_support_details_are_rejected(self):
        for support in (
            None, {}, {"style": "legs", "support_height_mm": 0,
                       "overall_height_mm": 700},
            {"style": "legs", "support_height_mm": True,
             "overall_height_mm": 800},
            {"style": "legs", "support_height_mm": 100,
             "overall_height_mm": 800, "pieces": 4},
        ):
            with self.subTest(support=support):
                req = prepared_with_legs()
                req["module_spec"]["modules"][0]["support_concept"] = support
                with self.assertRaises(DesignError):
                    design_modular_run(req["module_spec"])

    def test_legacy_floor_without_support_concept_stays_unchanged(self):
        req = prepared_with_legs()
        del req["module_spec"]["modules"][0]["support_concept"]
        model = design_modular_run(req["module_spec"])
        self.assertNotIn("support_review", model["modules"][0])
        self.assertEqual(model["status"], "DRAFT_NOT_FOR_CUTTING")

    def test_explicit_leg_detail_requires_floor_compatible_support(self):
        req = prepared_with_legs()
        req["module_spec"]["modules"][0]["support"] = "wall"
        with self.assertRaises(DesignError):
            design_modular_run(req["module_spec"])


if __name__ == "__main__":
    unittest.main()
