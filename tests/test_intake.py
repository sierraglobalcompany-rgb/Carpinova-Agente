"""F3 guided interview and faithful preliminary 2D geometry tests."""
import unittest
import xml.etree.ElementTree as ET

from carpinova_agent.core import DesignError
from carpinova_agent.intake import guide_project
from carpinova_agent.sketch import render_svg


CABINET = {
    "project_type": "gabinete",
    "width_mm": 600,
    "height_mm": 720,
    "depth_mm": 560,
    "panel_thickness_mm": 18,
    "construction": "sides_full",
}
DRAWER = {
    "project_type": "cajón",
    "opening_width_mm": 564,
    "opening_height_mm": 240,
    "opening_depth_mm": 500,
    "box_height_mm": 150,
    "panel_thickness_mm": 15,
    "bottom_thickness_mm": 6,
    "slide_clearance_left_mm": 13,
    "slide_clearance_right_mm": 13,
    "front_setback_mm": 5,
    "rear_setback_mm": 5,
}


class IntakeTests(unittest.TestCase):
    def test_asks_only_missing_geometry_fields(self):
        partial = {k: CABINET[k] for k in (
            "project_type", "width_mm", "height_mm", "depth_mm"
        )}
        result = guide_project(partial)
        self.assertEqual(result["phase"], "NEEDS_INPUT")
        self.assertEqual(result["missing_required_fields"],
                         ["panel_thickness_mm", "construction"])
        self.assertEqual([q["field"] for q in result["questions"]],
                         ["panel_thickness_mm", "construction"])
        self.assertIsNone(result["design"])

    def test_empty_type_is_question_not_invalid_concept(self):
        result = guide_project({"project_type": "  "})
        self.assertEqual(result["phase"], "NEEDS_INPUT")
        self.assertEqual(result["questions"][0]["field"], "project_type")

    def test_bad_structured_choice_has_clear_error(self):
        with self.assertRaises(DesignError):
            guide_project({**CABINET, "front_style": ["overlay"]})

    def test_drawer_low_wall_height_svg_agrees_with_geometry(self):
        low = {**DRAWER, "box_height_mm": 7}
        result = guide_project(low)
        self.assertEqual(result["phase"], "GEOMETRY_DRAFT")
        sketch = render_svg(result["design"])
        ET.fromstring(sketch)
        self.assertIn("7 mm", sketch)

    def test_dimensions_before_type_are_not_discarded(self):
        initial = {"width_mm": 600, "height_mm": 720, "depth_mm": 560}
        result = guide_project(initial)
        self.assertEqual(result["phase"], "NEEDS_INPUT")
        self.assertEqual(result["questions"][0]["field"], "project_type")
        self.assertEqual(result["submitted_values"]["width_mm"], 600)

    def test_concept_accepts_material_context(self):
        result = guide_project({"project_type": "cocina", "width_mm": 2400,
                                "height_mm": 2400, "depth_mm": 600,
                                "panel_thickness_mm": 18})
        self.assertEqual(result["phase"], "CONCEPT_ONLY")
        self.assertIsNone(result["design"])

    def test_built_in_requests_three_site_measurements(self):
        result = guide_project({**CABINET, "installation": "built_in"})
        self.assertEqual([q["field"] for q in result["questions"]],
                         ["site_width_top_mm", "site_width_middle_mm",
                          "site_width_bottom_mm"])

    def test_built_in_conflict_does_not_disappear(self):
        result = guide_project({**CABINET, "installation": "built_in",
                                "site_width_top_mm": 610,
                                "site_width_middle_mm": 598,
                                "site_width_bottom_mm": 595})
        self.assertEqual(result["phase"], "SITE_CONFLICT")
        self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertIn("menor luz", result["release_blockers"][0])
        self.assertEqual(result["design"]["dimensions"]["external_width_mm"], 600)

    def test_built_in_clearance_is_not_assumed(self):
        result = guide_project({**CABINET, "installation": "built_in",
                                "site_width_top_mm": 620,
                                "site_width_middle_mm": 617,
                                "site_width_bottom_mm": 610})
        self.assertEqual(result["phase"], "GEOMETRY_DRAFT")
        self.assertTrue(result["release_blockers"])

    def test_no_type_asks_type(self):
        result = guide_project({})
        self.assertEqual(result["questions"][0]["field"], "project_type")
        self.assertIsNone(result["design"])

    def test_geometry_without_defaults(self):
        result = guide_project(CABINET)
        self.assertEqual(result["phase"], "GEOMETRY_DRAFT")
        self.assertEqual(result["design"]["dimensions"]["clear_width_mm"], 564)
        self.assertEqual(result["design"]["parts"][1]["face_x_mm"], 564)
        self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(result["design"]["status"], "DRAFT_NOT_FOR_CUTTING")

    def test_construction_top_bottom(self):
        result = guide_project({**CABINET, "construction": "top_bottom_full"})
        self.assertEqual(result["design"]["parts"][0]["face_y_mm"], 684)
        self.assertEqual(result["design"]["parts"][1]["face_x_mm"], 600)

    def test_identifies_site_measurements_without_guessing_furniture_size(self):
        result = guide_project({**CABINET, "site_width_top_mm": 615,
                                "site_width_middle_mm": 609,
                                "site_width_bottom_mm": 602})
        self.assertTrue(result["site_measurements"]["all_three_confirmed"])
        self.assertEqual(result["site_measurements"]["range_mm"], 13)
        self.assertEqual(result["design"]["dimensions"]["external_width_mm"], 600)

    def test_one_site_measure_is_not_verified(self):
        result = guide_project({**CABINET, "site_width_top_mm": 610})
        self.assertFalse(result["site_measurements"]["all_three_confirmed"])
        self.assertIsNone(result["site_measurements"]["range_mm"])

    def test_front_intent_does_not_create_false_door_piece(self):
        result = guide_project({**CABINET, "front_style": "overlay"})
        self.assertEqual(len(result["design"]["parts"]), 2)
        self.assertIn("frente", result["front_choices"])

    def test_wall_mount_cannot_release(self):
        result = guide_project({**CABINET, "installation": "wall_mounted"})
        self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertTrue(any("anclajes" in x.lower()
                            for x in result["release_blockers"]))

    def test_cajon_accent_alias(self):
        result = guide_project(DRAWER)
        self.assertEqual(result["phase"], "GEOMETRY_DRAFT")
        self.assertEqual(result["project_type"], "drawer")
        self.assertEqual(result["design"]["dimensions"]["box_external_width_mm"], 538)

    def test_missing_clearance_never_assumed(self):
        partial = {k: v for k, v in DRAWER.items()
                   if not k.startswith("slide_clearance")}
        result = guide_project(partial)
        self.assertEqual(result["phase"], "NEEDS_INPUT")
        self.assertEqual(result["missing_required_fields"],
                         ["slide_clearance_left_mm", "slide_clearance_right_mm"])
        self.assertIn("ficha", result["next_question_hint"])
        self.assertIsNone(result["design"])

    def test_allowed_zero_clearance_remains_uncertified(self):
        result = guide_project({**DRAWER, "slide_clearance_left_mm": 0})
        self.assertEqual(result["phase"], "GEOMETRY_DRAFT")
        self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")

    def test_impossible_geometry_is_rejected(self):
        result = guide_project({**CABINET, "width_mm": 18})
        self.assertEqual(result["phase"], "INVALID_GEOMETRY")
        self.assertIsNone(result["design"])
        self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")

    def test_closet_is_concept_only(self):
        result = guide_project({"project_type": "clóset",
                                "width_mm": 2000, "height_mm": 2400,
                                "depth_mm": 600})
        self.assertEqual(result["phase"], "CONCEPT_ONLY")
        self.assertIsNone(result["design"])
        self.assertEqual(result["questions"][0]["field"], "module_layout")

    def test_kitchen_asks_space_dimensions(self):
        result = guide_project({"project_type": "cocina"})
        self.assertEqual(result["phase"], "NEEDS_INPUT")
        self.assertEqual(len(result["questions"]), 3)

    def test_niche_only_concept(self):
        result = guide_project({"project_type": "nicho", "width_mm": 500,
                                "height_mm": 400, "depth_mm": 300})
        self.assertEqual(result["phase"], "CONCEPT_ONLY")

    def test_max_questions(self):
        result = guide_project({"project_type": "cajón"}, max_questions=2)
        self.assertEqual(len(result["questions"]), 2)
        self.assertGreater(len(result["missing_required_fields"]), 2)

    def test_boolean_and_float_rejected(self):
        for width in (True, 600.0):
            with self.subTest(width=width), self.assertRaises(DesignError):
                guide_project({**CABINET, "width_mm": width})

    def test_unknown_field_rejected(self):
        with self.assertRaises(DesignError):
            guide_project({**CABINET, "hole_diameter_mm": 35})

    def test_wrong_category_field_rejected(self):
        with self.assertRaises(DesignError):
            guide_project({**CABINET, "opening_width_mm": 200})

    def test_unknown_construction_rejected(self):
        with self.assertRaises(DesignError):
            guide_project({**CABINET, "construction": "guessed"})

    def test_invalid_question_limit_rejected(self):
        for value in (0, 7, True, 2.5):
            with self.subTest(value=value), self.assertRaises(DesignError):
                guide_project(CABINET, max_questions=value)

    def test_invalid_type_rejected(self):
        with self.assertRaises(DesignError):
            guide_project({"project_type": "piscina"})

    def test_does_not_mutate_input(self):
        original = dict(CABINET)
        guide_project(original)
        self.assertEqual(original, CABINET)

    def test_draft_questions_do_not_claim_hardware(self):
        result = guide_project(DRAWER)
        self.assertTrue(any("corredera" in x.lower()
                            for x in result["release_blockers"]))


class SketchTests(unittest.TestCase):
    def test_cabinet_svg_is_parseable_and_warns(self):
        output = render_svg(guide_project(CABINET)["design"])
        root = ET.fromstring(output)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertIn("600 mm", output)
        self.assertIn("720 mm", output)
        self.assertIn("NO FABRICAR", output)

    def test_top_bottom_full_renders(self):
        design = guide_project({**CABINET,
                                "construction": "top_bottom_full"})["design"]
        svg = render_svg(design)
        self.assertIn("tapa/base completas", svg)
        self.assertEqual(len(ET.fromstring(svg).findall(
            "{http://www.w3.org/2000/svg}rect")), 4)

    def test_drawer_svg_contains_dimensions(self):
        svg = render_svg(guide_project(DRAWER)["design"])
        self.assertIn("538 mm", svg)
        self.assertIn("150 mm", svg)
        self.assertIn("fondo inferior aplicado", svg)
        ET.fromstring(svg)

    def test_refuses_unsupported_result(self):
        with self.assertRaises(DesignError):
            render_svg({"status": "RELEASED", "design_type": "open_cabinet"})

    def test_refuses_absent_geometry(self):
        with self.assertRaises(DesignError):
            render_svg({"status": "DRAFT_NOT_FOR_CUTTING",
                        "design_type": "kitchen", "dimensions": {}})


if __name__ == "__main__":
    unittest.main()
