"""Review-only proportional drawer openings via existing F1, Maestro and MCP."""
import copy
import json
import unittest

from carpinova_agent.core import DesignError
from carpinova_agent.drawer_modules import propose_drawer_layout
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.modular import design_modular_run
from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent.pilot_cli import PilotError, pilot_review
from pathlib import Path
from carpinova_agent.cad_exchange import validate_exchange


def proposal(weights=None, gap=28):
    return {
        "action": "modular",
        "module_spec": {
            "type": "drawer_layout_proposal",
            "width_mm": 500,
            "height_mm": 800,
            "depth_mm": 500,
            "panel_thickness_mm": 18,
            "construction": "sides_full",
            "vertical_gap_mm": gap,
            "drawer_weights": [1, 1, 1, 2] if weights is None else weights,
        },
    }


class DrawerLayoutProposalTests(unittest.TestCase):
    def test_three_small_one_large_exact_f1_and_proposal_only(self):
        answer = consult_maestro(proposal())
        self.assertEqual(answer["status"], "NEEDS_USER_CONFIRMATION")
        model = answer["modular"]
        self.assertEqual(model["source_engine"], "F1_CORE_CABINET")
        self.assertEqual(model["clear_height_mm"], 764)
        self.assertEqual(model["drawer_weights"], [1, 1, 1, 2])
        self.assertEqual(model["opening_plan"], [
            {"drawer_id": "D1", "opening_bottom_offset_mm": 0, "opening_height_mm": 136},
            {"drawer_id": "D2", "opening_bottom_offset_mm": 164, "opening_height_mm": 136},
            {"drawer_id": "D3", "opening_bottom_offset_mm": 328, "opening_height_mm": 136},
            {"drawer_id": "D4", "opening_bottom_offset_mm": 492, "opening_height_mm": 272},
        ])
        self.assertTrue(model["bottom_to_top"])
        self.assertEqual(model["piece_count"], 0)
        self.assertEqual(model["parts"], [])
        self.assertIsNone(model["assembled_external_depth_mm"])
        self.assertEqual(model["depth_scope"], "CARCASS_ONLY_UNTIL_FACADE_SELECTED")
        self.assertTrue(any("profundidad total" in b for b in model["blockers"]))
        self.assertTrue(any("profundidad" in q["question"]
                            for q in answer["questions"]))
        self.assertEqual(len(answer["questions"]), 3)
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(answer[flag], False)
            self.assertIs(model[flag], False)

    def test_confirmed_opening_plan_reaches_legacy_f7c_without_new_geometry(self):
        """Review proposal only becomes CAD after full, separately confirmed drawer inputs."""
        plan = consult_maestro(proposal())["modular"]["opening_plan"]
        examples = Path(__file__).resolve().parents[1] / "examples"
        for style in ("INSET", "OVERLAY"):
            with self.subTest(style=style):
                fixture = examples / (
                    f"four-drawer-500x500x800-{style}-UNCONFIRMED.json"
                )
                request = json.loads(fixture.read_text(encoding="utf-8"))
                drawers = request["module_spec"]["modules"][0]["drawers"]
                for drawer, opening in zip(drawers, plan):
                    self.assertEqual(drawer["drawer_id"], opening["drawer_id"])
                    drawer["opening_bottom_offset_mm"] = opening["opening_bottom_offset_mm"]
                    drawer["opening_height_mm"] = opening["opening_height_mm"]
                # These additional fixture values are illustrative, not
                # certified by the proposal or approved by a real user.
                reviewed = consult_maestro(request)
                self.assertEqual(reviewed["status"], "DRAFT_NOT_FOR_CUTTING")
                self.assertEqual(reviewed["modular"]["piece_count"], 28)
                bundle = pilot_review(request)
                cad = validate_exchange(json.loads(bundle["cad-exchange.json"]))
                self.assertEqual(len(cad["boxes"]), 28)
                self.assertIn("M1-D4-DRAWER_FACADE", bundle["parts-review.csv"])
                for flag in ("fabrication_ready", "cutting_ready",
                             "drilling_ready", "purchase_ready"):
                    self.assertIs(reviewed[flag], False)

    def test_equal_openings_and_full_clear_height(self):
        model = propose_drawer_layout(proposal([1, 1, 1, 1])["module_spec"])
        self.assertEqual([d["opening_height_mm"] for d in model["opening_plan"]],
                         [170, 170, 170, 170])
        self.assertEqual([d["opening_bottom_offset_mm"] for d in model["opening_plan"]],
                         [0, 198, 396, 594])
        self.assertEqual(model["opening_plan"][-1]["opening_bottom_offset_mm"]
                         + model["opening_plan"][-1]["opening_height_mm"], 764)

    def test_uneven_millimetres_are_apportioned_without_last_drawer_bias(self):
        request = proposal()
        # Clear height 767, gaps 3x28, weighted space = 683.
        # Fair largest-remainder distribution [136.6,136.6,136.6,273.2].
        request["module_spec"]["height_mm"] = 803
        model = propose_drawer_layout(request["module_spec"])
        self.assertEqual([x["opening_height_mm"] for x in model["opening_plan"]],
                         [137, 137, 136, 273])
        self.assertEqual([x["opening_bottom_offset_mm"] for x in model["opening_plan"]],
                         [0, 165, 330, 494])
        self.assertEqual(sum(x["opening_height_mm"] for x in model["opening_plan"])
                         + 3 * model["vertical_gap_mm"], model["clear_height_mm"])
        self.assertIsNone(model["assembled_external_depth_mm"])

    def test_single_drawer_has_no_separator(self):
        request = proposal([1], gap=0)
        result = consult_maestro(request)
        self.assertEqual(result["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(result["modular"]["opening_plan"], [
            {"drawer_id": "D1", "opening_bottom_offset_mm": 0,
             "opening_height_mm": 764},
        ])
        self.assertEqual(result["modular"]["piece_count"], 0)

    def test_integer_remainder_invariants(self):
        for height in (95, 131, 803, 1200):
            for weights in ([1, 1, 1, 1], [1, 2, 3], [2, 1, 1, 1]):
                with self.subTest(height=height, weights=weights):
                    request = proposal(weights, gap=1)
                    request["module_spec"]["height_mm"] = height
                    proposed = propose_drawer_layout(request["module_spec"])
                    plan = proposed["opening_plan"]
                    self.assertEqual(len(plan), len(weights))
                    self.assertTrue(all(x["opening_height_mm"] > 0 for x in plan))
                    self.assertEqual(
                        sum(x["opening_height_mm"] for x in plan)
                        + (len(weights) - 1) * proposed["vertical_gap_mm"],
                        proposed["clear_height_mm"]
                    )
                    self.assertEqual(
                        plan[-1]["opening_bottom_offset_mm"]
                        + plan[-1]["opening_height_mm"],
                        proposed["clear_height_mm"]
                    )

    def test_proposal_is_available_through_existing_mcp_not_new_tool(self):
        answer = carpinova_consultar(json.dumps(proposal()))
        self.assertEqual(answer["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(len(answer["modular"]["opening_plan"]), 4)

    def test_proposal_cannot_generate_cad_before_user_confirmation(self):
        with self.assertRaises(PilotError):
            pilot_review(proposal())
        with self.assertRaises(DesignError):
            design_modular_run(proposal()["module_spec"])

    def test_reject_invalid_weights_and_gap_without_inference(self):
        bad_cases = [
            {"drawer_weights": []},
            {"drawer_weights": [1, 1, 1, 2, 1]},
            {"drawer_weights": [1, 0, 1]},
            {"drawer_weights": [1, True]},
            {"drawer_weights": [1, 1.5]},
            {"vertical_gap_mm": 0},
            {"vertical_gap_mm": -1},
            {"vertical_gap_mm": 300},
            {"construction": "unsupported"},
            {"width_mm": 30},
        ]
        for change in bad_cases:
            with self.subTest(change=change):
                sample = proposal()["module_spec"]
                sample.update(change)
                with self.assertRaises(DesignError):
                    propose_drawer_layout(sample)

    def test_unknown_fields_and_wrong_type_fail_closed(self):
        sample = copy.deepcopy(proposal()["module_spec"])
        sample["slide_clearance_left_mm"] = 13
        with self.assertRaises(DesignError):
            propose_drawer_layout(sample)
        with self.assertRaises(DesignError):
            propose_drawer_layout(None)
        with self.assertRaises(DesignError):
            propose_drawer_layout({"type": "drawer_layout_proposal"})

    def test_question_limit_keeps_essential_confirmation_first(self):
        answer = consult_maestro(proposal(), max_questions=1)
        self.assertEqual(len(answer["questions"]), 1)
        self.assertEqual(answer["questions"][0]["field"], "module_spec.drawer_weights")


if __name__ == "__main__":
    unittest.main()
