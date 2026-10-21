"""Review-to-CAD integrity: no silent changes to drawer layout in F7C."""
import copy
import json
from pathlib import Path
import unittest

from carpinova_agent.core import DesignError
from carpinova_agent.drawer_modules import propose_drawer_layout
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent.modular import design_modular_run
from carpinova_agent.pilot_cli import PilotError, pilot_review

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def reviewed(style: str = "OVERLAY"):
    request = json.loads((EXAMPLES / (
        f"four-drawer-500x500x800-{style}-UNCONFIRMED.json"
    )).read_text(encoding="utf-8"))
    proposal = {
        "type": "drawer_layout_proposal",
        "width_mm": 500, "height_mm": 800, "depth_mm": 500,
        "panel_thickness_mm": 18, "construction": "sides_full",
        "vertical_gap_mm": 28, "drawer_weights": [1, 1, 1, 2],
    }
    plan = propose_drawer_layout(proposal)["opening_plan"]
    drawers = request["module_spec"]["modules"][0]["drawers"]
    for drawer, opening in zip(drawers, plan):
        drawer["opening_bottom_offset_mm"] = opening["opening_bottom_offset_mm"]
        drawer["opening_height_mm"] = opening["opening_height_mm"]
    request["module_spec"]["modules"][0]["drawer_layout_reference"] = proposal
    return request


class ReviewedOpeningTests(unittest.TestCase):
    def test_both_front_styles_generate_28_pieces_only_when_plan_matches(self):
        for style in ("INSET", "OVERLAY"):
            with self.subTest(style=style):
                request = reviewed(style)
                answer = consult_maestro(request)
                self.assertEqual(answer["status"], "DRAFT_NOT_FOR_CUTTING")
                self.assertEqual(answer["modular"]["piece_count"], 28)
                preview = carpinova_consultar(json.dumps(request))
                self.assertEqual(preview["status"], "DRAFT_NOT_FOR_CUTTING")
                self.assertEqual(preview["modular"]["piece_count"], 28)
                bundle = pilot_review(request)
                self.assertIn("M1-D4-DRAWER_FACADE", bundle["parts-review.csv"])
                for flag in ("fabrication_ready", "cutting_ready",
                             "drilling_ready", "purchase_ready"):
                    self.assertIs(answer[flag], False)

    def test_tampering_with_one_drawer_or_swapping_boxes_blocks_cad(self):
        original = reviewed()
        for field, replacement in (
            ("opening_height_mm", 135),
            ("opening_bottom_offset_mm", 495),
            ("drawer_id", "WRONG"),
        ):
            with self.subTest(field=field):
                req = copy.deepcopy(original)
                req["module_spec"]["modules"][0]["drawers"][3][field] = replacement
                with self.assertRaises(DesignError):
                    design_modular_run(req["module_spec"])
                with self.assertRaises((DesignError, PilotError)):
                    pilot_review(req)
        req = copy.deepcopy(original)
        drawers = req["module_spec"]["modules"][0]["drawers"]
        drawers[0], drawers[1] = drawers[1], drawers[0]
        with self.assertRaises(DesignError):
            design_modular_run(req["module_spec"])

    def test_proposal_geometry_mismatch_blocks_cad(self):
        for field, value in (
            ("width_mm", 501), ("height_mm", 801), ("depth_mm", 482),
            ("panel_thickness_mm", 16), ("construction", "top_bottom_full"),
            ("vertical_gap_mm", 27), ("drawer_weights", [1, 1, 2, 1]),
        ):
            with self.subTest(field=field):
                req = reviewed()
                req["module_spec"]["modules"][0]["drawer_layout_reference"][field] = value
                with self.assertRaises(DesignError):
                    design_modular_run(req["module_spec"])

    def test_nonreviewed_legacy_modules_are_not_modified(self):
        req = reviewed()
        del req["module_spec"]["modules"][0]["drawer_layout_reference"]
        model = design_modular_run(req["module_spec"])
        self.assertEqual(model["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(model["piece_count"], 28)

    def test_invalid_reference_and_quantity_are_not_silently_ignored(self):
        for value in (None, "pending", {}, []):
            with self.subTest(value=value):
                req = reviewed()
                req["module_spec"]["modules"][0]["drawer_layout_reference"] = value
                with self.assertRaises(DesignError):
                    design_modular_run(req["module_spec"])
        req = reviewed()
        del req["module_spec"]["modules"][0]["drawers"][-1]
        with self.assertRaises(DesignError):
            design_modular_run(req["module_spec"])


if __name__ == "__main__":
    unittest.main()
