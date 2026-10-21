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
        self.assertIn("son supuestos, no especificaciones", model["human_summary"])
        self.assertIn("D = D1 · gaveta", model["sketch_text"])
        self.assertIn("NO son divisores", model["sketch_text"])
        self.assertIn("NO CORTAR", model["sketch_svg"])
        self.assertIn("T · TAPA · 500 mm", model["sketch_svg"])
        self.assertIn("ALTO 800 mm", model["sketch_svg"])
        self.assertIn("D (D1) · GAVETA 272 mm", model["sketch_svg"])
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
        self.assertIn("D (D1) · GAVETA", result["sketch_svg"])
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

    def test_stable_references_A_D_T_and_sides(self):
        result = consult_maestro(novice())["modular"]
        refs = result["element_refs"]
        self.assertEqual([v["ref"] for v in refs],
                         ["A", "B", "C", "D", "T", "LI", "LD", "AP", "FP", "MF"])
        self.assertEqual([v["engine_id"] for v in refs[:4]],
                         ["D4", "D3", "D2", "D1"])
        self.assertEqual([v["nominal_opening_height_mm"] for v in refs[:4]],
                         [136, 136, 136, 272])
        for ref in ("LI", "LD", "T · TAPA · 500 mm"):
            self.assertIn(ref, result["sketch_svg"])

    def test_A_ten_centimeters_higher_shows_all_affected_parts(self):
        req = novice()
        req["module_spec"]["drawer_adjustments_mm"] = {"A": 100}
        result = consult_maestro(req)["modular"]
        self.assertEqual([v["nominal_opening_height_mm"]
                          for v in result["element_refs"][:4]],
                         [236, 111, 111, 222])
        self.assertEqual([v["engine_id"] for v in result["element_refs"][:4]],
                         ["D4", "D3", "D2", "D1"])
        self.assertEqual([v["ref"] for v in result["revisions"]],
                         ["A", "B", "C", "D"])
        self.assertEqual(result["revisions"][0], {
            "ref": "A", "before_mm": 136, "after_mm": 236,
            "delta_mm": 100, "cause": "USER_REQUESTED",
        })
        self.assertTrue(all(v["cause"] == "AUTO_REDISTRIBUTED_TO_KEEP_TOTAL_HEIGHT"
                            for v in result["revisions"][1:]))
        self.assertEqual(result["layout_source"], "EXPLICIT_HEIGHTS")
        self.assertEqual(sum(v["nominal_opening_height_mm"]
                             for v in result["element_refs"][:4]) +
                         3 * result["vertical_gap_mm"], result["clear_height_mm"])
        self.assertFalse(result["can_generate_f7c"])
        ET.fromstring(result["sketch_svg"])

    def test_explicit_compensation_only_changes_A_and_B(self):
        req = novice()
        req["module_spec"]["drawer_adjustments_mm"] = {"A": 100, "B": -100}
        result = consult_maestro(req)["modular"]
        self.assertEqual([v["nominal_opening_height_mm"]
                          for v in result["element_refs"][:4]],
                         [236, 36, 136, 272])
        self.assertEqual([v["ref"] for v in result["revisions"]], ["A", "B"])

    def test_T_50mm_one_side_100mm_other_is_concept_only(self):
        req = novice()
        req["module_spec"].update({
            "top_overhang_left_mm": 50, "top_overhang_right_mm": 100,
        })
        result = consult_maestro(req)["modular"]
        self.assertEqual(result["element_refs"][4]["ref"], "T")
        self.assertEqual(result["element_refs"][4]["concept_overhang_left_mm"], 50)
        self.assertIn("T · TAPA · 650 mm", result["sketch_svg"])
        self.assertTrue(result["unvalidated_top_extension"])
        self.assertTrue(any("F1" in v for v in result["blockers"]))
        self.assertEqual(result["piece_count"], 0)
        ET.fromstring(result["sketch_svg"])

    def test_all_four_opening_options_are_visual_not_hardware(self):
        req = novice()
        req["module_spec"]["opening_systems"] = {
            "A": "handle", "B": "finger_pull",
            "C": "push_to_open", "D": "profile",
        }
        result = carpinova_consultar(json.dumps(req))["modular"]
        self.assertEqual(
            [v["opening_system_intent"] for v in result["element_refs"][:4]],
            ["handle", "finger_pull", "push_to_open", "profile"],
        )
        for label in ("manija (indicativa)", "uñero (indicativo)",
                      "presión (indicativa)", "perfil (indicativo)"):
            self.assertIn(label, result["sketch_svg"])
        self.assertIn("NO CORTAR, TALADRAR NI COMPRAR", result["sketch_svg"])
        ET.fromstring(result["sketch_svg"])

    def test_adjusted_heights_are_reverified_by_existing_F1(self):
        req = novice()
        req["module_spec"]["drawer_adjustments_mm"] = {"A": 100}
        guide = consult_maestro(req)["modular"]
        proposal = propose_drawer_layout(guide["proposed_layout_spec"])
        self.assertEqual(proposal["opening_plan"], guide["opening_plan"])
        self.assertEqual(proposal["layout_source"], "EXPLICIT_HEIGHTS")
        for invalid in ([1, 2, 3, 4], [1, 2, 0, 3],
                        [1.0, 2, 3, 4], [1]):
            with self.subTest(heights=invalid):
                spec = dict(guide["proposed_layout_spec"])
                spec["opening_heights_mm"] = invalid
                with self.assertRaises(DesignError):
                    propose_drawer_layout(spec)

    def test_invalid_references_or_oversized_edits_fail_closed(self):
        invalid = [
            {"drawer_adjustments_mm": {"A": 900}},
            {"drawer_adjustments_mm": {"Z": 10}},
            {"drawer_adjustments_mm": {"A": True}},
            {"drawer_adjustments_mm": {"A": 1.5}},
            {"drawer_adjustments_mm": ["A", 100]},
            {"opening_systems": {"X": "handle"}},
            {"opening_systems": {"A": "imaginary"}},
            {"top_overhang_left_mm": -1},
            {"top_overhang_right_mm": 999},
            {"top_overhang_right_mm": True},
        ]
        for change in invalid:
            req = novice()
            req["module_spec"].update(change)
            with self.subTest(change=change), self.assertRaises(DesignError):
                guide_drawer_layout(req["module_spec"])
        req = novice()
        req["module_spec"]["drawer_adjustments_mm"] = {"A": 100}
        with self.assertRaises((PilotError, DesignError)):
            pilot_review(req)


    def test_legs_are_included_in_fixed_800mm_overall_height(self):
        req = novice()
        req["module_spec"].update({
            "support_style": "legs", "support_height_mm": 100
        })
        result = consult_maestro(req)["modular"]
        self.assertEqual(result["overall_height_mm"], 800)
        self.assertEqual(result["carcass_height_mm"], 700)
        self.assertEqual(result["external_dimensions_mm"]["height"], 700)
        self.assertEqual(result["clear_height_mm"], 664)
        self.assertEqual([x["nominal_opening_height_mm"]
                          for x in result["element_refs"][:4]],
                         [116, 116, 116, 232])
        self.assertEqual(result["element_refs"][7]["ref"], "AP")
        self.assertEqual(result["element_refs"][7]["concept_height_mm"], 100)
        self.assertIn("AP patas (idea)", result["sketch_svg"])
        self.assertIn("ALTO 800 mm", result["sketch_svg"])
        self.assertFalse(result["can_generate_f7c"])
        self.assertEqual(result["parts"], [])
        ET.fromstring(result["sketch_svg"])

    def test_banqueo_base_changes_body_height_and_is_concept_only(self):
        req = novice()
        req["module_spec"].update({
            "support_style": "plinth", "support_height_mm": 80
        })
        result = carpinova_consultar(json.dumps(req))["modular"]
        self.assertEqual(result["carcass_height_mm"], 720)
        self.assertEqual(result["clear_height_mm"], 684)
        self.assertIn("AP zócalo (idea)", result["sketch_svg"])
        self.assertTrue(result["unvalidated_support"])
        self.assertTrue(any("patas" in x for x in result["blockers"]))
        ET.fromstring(result["sketch_svg"])

    def test_wall_french_cleat_references_and_floor_height_are_illustrative(self):
        req = novice()
        req["module_spec"].update({
            "support_style": "wall_mounted",
            "wall_contact": True,
            "wall_fixing": "french_cleat",
            "wall_bottom_above_floor_mm": 400,
            "back_style": "thin_sheet",
        })
        result = consult_maestro(req)["modular"]
        self.assertEqual(result["overall_height_mm"], 800)
        self.assertEqual(result["carcass_height_mm"], 800)
        self.assertTrue(result["unvalidated_support"])
        self.assertTrue(result["unvalidated_mounting"])
        self.assertTrue(result["unvalidated_back_panel"])
        self.assertEqual(result["element_refs"][8]["ref"], "FP")
        self.assertEqual(result["element_refs"][8]["concept_thickness_mm"], 2)
        self.assertEqual(result["element_refs"][9]["ref"], "MF")
        self.assertEqual(result["element_refs"][9]["fixing"], "french_cleat")
        self.assertIn("400 mm", result["sketch_text"])
        self.assertIn("MF muro (idea)", result["sketch_svg"])
        self.assertTrue(any("NO acredita" in v for v in result["blockers"]))
        ET.fromstring(result["sketch_svg"])

    def test_floor_supported_against_wall_with_direct_fixings(self):
        req = novice()
        req["module_spec"].update({
            "wall_contact": True, "wall_fixing": "direct_fasteners",
            "back_style": "full_panel", "back_thickness_mm": 6,
        })
        result = consult_maestro(req)["modular"]
        self.assertEqual(result["support_style"], "floor_direct")
        self.assertEqual(result["carcass_height_mm"], 800)
        self.assertEqual(result["back_thickness_mm"], 6)
        self.assertTrue(result["unvalidated_mounting"])
        self.assertEqual(result["piece_count"], 0)
        self.assertIn("fijación directa", result["sketch_text"])
        ET.fromstring(result["sketch_svg"])

    def test_unsupported_wall_and_support_combinations_fail_closed(self):
        invalid = [
            {"support_style": "legs", "support_height_mm": 0},
            {"support_style": "plinth", "support_height_mm": 790},
            {"support_style": "floor_direct", "support_height_mm": 50},
            {"support_style": "wall_mounted", "wall_contact": False},
            {"support_style": "wall_mounted", "wall_fixing": "none"},
            {"support_style": "masonry"},
            {"support_height_mm": True},
            {"wall_contact": 1},
            {"wall_fixing": "direct_fasteners", "wall_contact": False},
            {"wall_fixing": "unknown"},
            {"wall_bottom_above_floor_mm": -1},
            {"wall_bottom_above_floor_mm": 400},
            {"back_style": "unknown"},
            {"back_style": "none", "back_thickness_mm": 2},
            {"back_style": "pending", "back_thickness_mm": 2},
            {"back_style": "thin_sheet", "back_thickness_mm": True},
            {"back_style": "full_panel", "back_thickness_mm": 0},
        ]
        for changes in invalid:
            req = novice()
            req["module_spec"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(DesignError):
                guide_drawer_layout(req["module_spec"])

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
        for ref, opening in zip("ABCD", reversed(model["opening_plan"])):
            self.assertIn(
                f'{ref} ({opening["drawer_id"]}) · ' +
                ("GAVETA" if opening["drawer_id"] == "D1" else "CAJÓN") +
                f' {opening["opening_height_mm"]} mm', model["sketch_svg"]
            )
        self.assertEqual(
            sum(x["opening_height_mm"] for x in model["opening_plan"]) +
            3 * model["vertical_gap_mm"], model["clear_height_mm"]
        )


if __name__ == "__main__":
    unittest.main()
