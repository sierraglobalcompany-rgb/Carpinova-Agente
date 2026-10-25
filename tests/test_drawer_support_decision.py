"""Support decisions must not be silently confirmed by an initial drawer sketch."""
import unittest
from carpinova_agent.drawer_modules import guide_drawer_layout
from carpinova_agent.maestro import consult_maestro


class DrawerSupportDecisionTests(unittest.TestCase):
    def request(self, **changes):
        spec = {"type": "drawer_layout_guide", "width_mm": 500,
                "height_mm": 800, "depth_mm": 500, "small_drawers": 3}
        spec.update(changes)
        return spec

    def test_omitted_support_requires_explicit_choice_before_approval(self):
        reply = consult_maestro({"action": "modular",
                                 "module_spec": self.request()})
        plan = reply["modular"]
        self.assertEqual(len(reply["questions"]), 1)
        self.assertEqual(reply["questions"][0]["field"],
                         "module_spec.proposed_layout_spec")
        self.assertIn("¿irá al piso", reply["questions"][0]["question"])
        self.assertTrue(plan["support_style_is_suggestion"])
        self.assertEqual(plan["support_style"], "floor_direct")
        self.assertIn("AP · sin patas (al piso)", plan["sketch_svg"])
        self.assertIn("APOYO SIN CONFIRMAR", plan["sketch_text"])
        self.assertEqual(plan["piece_count"], 0)
        self.assertFalse(plan["can_generate_f7c"])

    def test_leg_height_recalculates_every_drawer_keeping_total(self):
        floor = guide_drawer_layout(self.request(support_style="floor_direct"))
        legs = guide_drawer_layout(self.request(
            support_style="legs", support_height_mm=100))
        self.assertEqual(floor["carcass_height_mm"], 800)
        self.assertEqual(legs["carcass_height_mm"], 700)
        self.assertEqual(legs["overall_height_mm"], 800)
        self.assertEqual(legs["support_height_mm"], 100)
        self.assertEqual(legs["external_dimensions_mm"]["height"], 700)
        self.assertNotEqual(
            [x["opening_height_mm"] for x in floor["opening_plan"]],
            [x["opening_height_mm"] for x in legs["opening_plan"]])
        self.assertEqual(
            sum(x["opening_height_mm"] for x in legs["opening_plan"])
            + 3 * legs["vertical_gap_mm"], legs["clear_height_mm"])
        self.assertTrue(legs["unvalidated_support"])
        self.assertEqual(legs["piece_count"], 0)

    def test_legs_without_height_need_confirmation(self):
        reply = consult_maestro({"action": "modular",
                                 "module_spec": self.request(support_style="legs")})
        self.assertEqual(reply["questions"][0]["field"],
                         "module_spec.proposed_layout_spec")
        self.assertIn("altura real", reply["questions"][0]["question"])
        self.assertEqual(reply["modular"]["support_height_mm"], 100)
        self.assertTrue(reply["modular"]["support_height_is_suggestion"])
        self.assertIn("sugeridos", reply["modular"]["sketch_svg"])

    def test_explicit_support_is_not_a_silent_suggestion(self):
        for opts in ({"support_style": "floor_direct"},
                     {"support_style": "legs", "support_height_mm": 150}):
            with self.subTest(opts=opts):
                reply = consult_maestro({
                    "action": "modular", "module_spec": self.request(**opts)})
                plan = reply["modular"]
                self.assertFalse(plan["support_style_is_suggestion"])
                self.assertFalse(plan["support_height_is_suggestion"])
                self.assertEqual(reply["questions"][0]["field"],
                                 "module_spec.proposed_layout_spec")
                for flag in ("fabrication_ready", "cutting_ready",
                             "drilling_ready", "purchase_ready"):
                    self.assertFalse(plan[flag])
                self.assertFalse(plan["can_generate_f7c"])

    def test_rejects_leg_height_that_leaves_no_carcass(self):
        with self.assertRaisesRegex(ValueError, "altura suficiente"):
            guide_drawer_layout(self.request(
                support_style="legs", support_height_mm=790))


if __name__ == "__main__":
    unittest.main()
