"""F7C external depth is a physical limit, not a synonym for carcass depth.

Both drawer fronts and CADExchange must share one forward-extension formula.
All cases remain nominal and non-fabrication-ready.
"""
import copy
import json
from pathlib import Path
import unittest

from carpinova_agent.core import DesignError
from carpinova_agent.modular import design_modular_run
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.pilot_cli import pilot_review, PilotError

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def request(style="OVERLAY"):
    return json.loads((EXAMPLES /
        f"four-drawer-500x500x800-{style}-UNCONFIRMED.json"
    ).read_text(encoding="utf-8"))


class AssembledDepthReviewTests(unittest.TestCase):
    def test_inset_front_does_not_add_external_depth(self):
        req = request("INSET")
        req["module_spec"]["max_assembled_depth_mm"] = 500
        model = consult_maestro(req)["modular"]
        self.assertEqual(model["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(model["depth_review"], {
            "carcass_depth_mm": 500, "front_extension_mm": 0,
            "assembled_external_depth_mm": 500,
            "max_assembled_depth_mm": 500, "conflict": False,
        })
        self.assertEqual(validate_exchange(cad_exchange(model))["bounds_xyz_mm"],
                         [500, 800, 500])

    def test_overlay_reports_true_518_without_claiming_500_final(self):
        req = request("OVERLAY")
        model = design_modular_run(req["module_spec"])
        self.assertEqual(model["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(model["depth_review"]["assembled_external_depth_mm"], 518)
        self.assertEqual(model["depth_review"]["front_extension_mm"], 18)
        self.assertIsNone(model["depth_review"]["max_assembled_depth_mm"])
        self.assertTrue(any("518 mm exteriores" in b for b in model["blockers"]))
        cad = validate_exchange(cad_exchange(model))
        self.assertEqual(cad["bounds_xyz_mm"][2],
                         model["depth_review"]["assembled_external_depth_mm"])

    def test_overlay_above_explicit_limit_blocks_all_artifacts(self):
        req = request("OVERLAY")
        req["module_spec"]["max_assembled_depth_mm"] = 500
        answer = consult_maestro(req)
        model = answer["modular"]
        self.assertEqual(answer["status"], "NEEDS_DEPTH_REVISION")
        self.assertEqual(model["status"], "NEEDS_DEPTH_REVISION")
        self.assertEqual(model["depth_review"], {
            "carcass_depth_mm": 500, "front_extension_mm": 18,
            "assembled_external_depth_mm": 518,
            "max_assembled_depth_mm": 500, "conflict": True,
        })
        self.assertEqual(answer["questions"][0]["field"],
                         "module_spec.max_assembled_depth_mm")
        self.assertIn("518 mm exteriores", answer["questions"][0]["question"])
        for flag in ("fabrication_ready", "cutting_ready",
                     "drilling_ready", "purchase_ready"):
            self.assertIs(answer[flag], False)
            self.assertIs(model[flag], False)
        with self.assertRaises(PilotError):
            pilot_review(req)
        with self.assertRaises(DesignError):
            cad_exchange(model)

    def test_adjusted_carcass_keeps_overlay_within_500mm(self):
        req = request("OVERLAY")
        req["module_spec"]["depth_mm"] = 482
        req["module_spec"]["max_assembled_depth_mm"] = 500
        answer = consult_maestro(req)
        self.assertEqual(answer["status"], "DRAFT_NOT_FOR_CUTTING")
        model = answer["modular"]
        self.assertEqual(model["piece_count"], 28)
        self.assertEqual(model["depth_review"]["carcass_depth_mm"], 482)
        self.assertEqual(model["depth_review"]["assembled_external_depth_mm"], 500)
        self.assertFalse(model["depth_review"]["conflict"])
        cad = validate_exchange(cad_exchange(model))
        self.assertEqual(cad["bounds_xyz_mm"], [500, 800, 500])
        bundle = pilot_review(req)
        self.assertIn("M1-D4-DRAWER_FACADE", bundle["parts-review.csv"])

    def test_invalid_depth_limit_rejected_before_geometry(self):
        for bad in (0, -1, True, 500.0, "500", None):
            with self.subTest(value=bad):
                req = request()
                req["module_spec"]["max_assembled_depth_mm"] = bad
                with self.assertRaises(DesignError):
                    design_modular_run(req["module_spec"])

    def test_no_unverified_depth_rule_applied_to_legacy_projects(self):
        req = request("INSET")
        untouched = design_modular_run(copy.deepcopy(req["module_spec"]))
        self.assertEqual(untouched["piece_count"], 28)
        self.assertEqual(untouched["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(untouched["depth_review"]["assembled_external_depth_mm"], 500)
        self.assertFalse(untouched["depth_review"]["conflict"])


if __name__ == "__main__":
    unittest.main()
