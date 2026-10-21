"""Human-first furniture sketch: a novice can ask for drawers without knowing mm gaps."""
import json
import unittest
import xml.etree.ElementTree as ET

from carpinova_agent.core import DesignError
from carpinova_agent.drawer_modules import (
    guide_drawer_layout, propose_drawer_layout, drawer_layout_sketch_svg,
)
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent.pilot_cli import PilotError, pilot_review
from carpinova_agent.modular import design_modular_run


def novice(position=None):
    spec = {
        "type": "drawer_layout_guide",
        "width_mm": 500, "height_mm": 800, "depth_mm": 500,
        "small_drawers": 3,
    }
    if position is not None:
        spec["large_drawer_position"] = position
    return {"action": "modular", "module_spec": spec}


class NoviceSketchTests(unittest.TestCase):
    def test_simple_request_returns_dimensioned_sketch_and_one_clear_question(self):
        reply = consult_maestro(novice())
        model = reply["modular"]
        self.assertEqual(reply["status"], "NEEDS_USER_CONFIRMATION")
        self.assertTrue(model["guided"])
        self.assertEqual(model["piece_count"], 0)
        self.assertEqual(model["parts"], [])
        self.assertEqual(model["source_engine"], "F1_CORE_CABINET")
        self.assertEqual(model["clear_height_mm"], 764)
        self.assertEqual(
            [(p["drawer_id"], p["opening_bottom_offset_mm"],
              p["opening_height_mm"]) for p in model["opening_plan"]],
            [("D1", 0, 272), ("D2", 300, 136),
             ("D3", 464, 136), ("D4", 628, 136)]
        )
        self.assertEqual(len(reply["questions"]), 1)
        self.assertIn("¿Te gusta este boceto", reply["questions"][0]["question"])
        self.assertNotIn("correderas y sistema", reply["questions"][0]["question"])
        self.assertEqual(model["suggestions_not_confirmed"]["panel_thickness_mm"], 18)
        self.assertEqual(model["suggestions_not_confirmed"]["vertical_gap_mm"], 28)
        self.assertIn("solo supuestos", model["human_summary"])
        self.assertIn("GAVETA", model["sketch_text"])
        self.assertIn("NO es divisor", model["sketch_text"])
        self.assertIn("NO CORTAR", model["sketch_svg"])
        self.assertIn("ANCHO 500 mm", model["sketch_svg"])
        self.assertIn("ALTO 800 mm", model["sketch_svg"])
        self.assertIn("D1 GAVETA · 272 mm", model["sketch_svg"])
        ET.fromstring(model["sketch_svg"])
        for flag in ("fabrication_ready", "cutting_ready",
                     "drilling_ready", "purchase_ready"):
            self.assertIs(reply[flag], False)
            self.assertIs(model[flag], False)

    def test_top_versus_bottom_changes_preview_from_same_F1(self):
        bottom = consult_maestro(novice())["modular"]
        top = consult_maestro(novice("top"))["modular"]
        self.assertEqual(top["drawer_weights"], [1, 1, 1, 2])
        self.assertEqual(
            [x["opening_height_mm"] for x in top["opening_plan"]],
            [136, 136, 136, 272],
        )
        self.assertIn("arriba", top["human_summary"])
        self.assertEqual(bottom["source_engine"], top["source_engine"])
        self.assertEqual(bottom["clear_height_mm"], top["clear_height_mm"])
        self.assertNotEqual(bottom["sketch_svg"], top["sketch_svg"])
        ET.fromstring(top["sketch_svg"])

    def test_existing_detailed_proposal_remains_review_only_with_sketch(self):
        full = guide_drawer_layout(novice()["module_spec"])["proposed_layout_spec"]
        result = propose_drawer_layout(full)
        self.assertEqual(result["type"], "drawer_layout_proposal")
        self.assertIn("D1 GAVETA", result["sketch_svg"])
        self.assertEqual(result["piece_count"], 0)
        self.assertEqual(result["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(drawer_layout_sketch_svg(result), result["sketch_svg"])

    def test_live_existing_mcp_returns_sketch_without_seventh_tool(self):
        reply = carpinova_consultar(json.dumps(novice(), ensure_ascii=False))
        self.assertEqual(reply["status"], "NEEDS_USER_CONFIRMATION")
        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg"',
                      reply["modular"]["sketch_svg"])
        self.assertEqual(len(reply["questions"]), 1)

    def test_unapproved_sketch_never_creates_cad_or_materials(self):
        with self.assertRaises((PilotError, DesignError)):
            pilot_review(novice())
        with self.assertRaises(DesignError):
            design_modular_run(novice()["module_spec"])

    def test_invalid_dimensions_and_uncertain_counts_fail_closed(self):
        changes = [
            {"width_mm": True}, {"height_mm": 20},
            {"depth_mm": 0}, {"small_drawers": 0},
            {"small_drawers": 4}, {"small_drawers": 2.5},
            {"large_drawer_position": "middle"},
            {"max_assembled_depth_mm": 500},
        ]
        for change in changes:
            with self.subTest(change=change):
                request = novice()
                request["module_spec"].update(change)
                with self.assertRaises(DesignError):
                    guide_drawer_layout(request["module_spec"])
        with self.assertRaises(DesignError):
            guide_drawer_layout(None)

    def test_markup_and_values_from_f1_stay_in_sync(self):
        req = novice()
        req["module_spec"]["height_mm"] = 803
        model = guide_drawer_layout(req["module_spec"])
        ET.fromstring(model["sketch_svg"])
        self.assertIn("ALTO 803 mm", model["sketch_svg"])
        for opening in model["opening_plan"]:
            self.assertIn(
                f'{opening["drawer_id"]} ' +
                ("GAVETA" if opening["drawer_id"] == "D1" else "CAJÓN") +
                f' · {opening["opening_height_mm"]} mm', model["sketch_svg"]
            )
        self.assertEqual(
            sum(x["opening_height_mm"] for x in model["opening_plan"]) +
            3 * model["vertical_gap_mm"], model["clear_height_mm"]
        )


if __name__ == "__main__":
    unittest.main()
