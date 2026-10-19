"""Geometry checks: examples are fictional inputs, NOT hardware guidance."""
import unittest

from carpinova_agent import DesignError, design


CABINET = {
    "type": "cabinet", "width_mm": 600, "height_mm": 720,
    "depth_mm": 560, "panel_thickness_mm": 18,
    "construction": "sides_full",
}
DRAWER = {
    "type": "drawer", "opening_width_mm": 564, "opening_height_mm": 300,
    "opening_depth_mm": 500, "box_height_mm": 150,
    "panel_thickness_mm": 15, "bottom_thickness_mm": 6,
    "slide_clearance_left_mm": 13, "slide_clearance_right_mm": 13,
    "front_setback_mm": 5, "rear_setback_mm": 5,
}


class CabinetTests(unittest.TestCase):
    def test_sides_full(self):
        result = design(CABINET)
        self.assertEqual(result["dimensions"]["clear_width_mm"], 564)
        self.assertEqual(result["dimensions"]["clear_height_mm"], 684)
        side, cap = result["parts"]
        self.assertEqual((side["face_x_mm"], side["face_y_mm"], side["quantity"]),
                         (560, 720, 2))
        self.assertEqual((cap["face_x_mm"], cap["face_y_mm"]), (564, 560))

    def test_top_bottom_full(self):
        data = dict(CABINET, construction="top_bottom_full")
        side, cap = design(data)["parts"]
        self.assertEqual(side["face_y_mm"], 684)
        self.assertEqual(cap["face_x_mm"], 600)

    def test_not_released(self):
        out = design(CABINET)
        self.assertEqual(out["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertTrue(out["release_blockers"])
        self.assertTrue(all(p["grain"] == "UNCONFIRMED" for p in out["parts"]))

    def test_reject_thin_width(self):
        with self.assertRaises(DesignError):
            design(dict(CABINET, width_mm=36))

    def test_reject_thin_height(self):
        with self.assertRaises(DesignError):
            design(dict(CABINET, height_mm=35))

    def test_reject_fraction(self):
        with self.assertRaises(DesignError):
            design(dict(CABINET, width_mm=600.2))

    def test_reject_boolean(self):
        with self.assertRaises(DesignError):
            design(dict(CABINET, width_mm=True))

    def test_reject_unknown_field(self):
        with self.assertRaises(DesignError):
            design(dict(CABINET, guessed_hardware="hinge"))

    def test_reject_unknown_construction(self):
        with self.assertRaises(DesignError):
            design(dict(CABINET, construction="invented"))


class DrawerTests(unittest.TestCase):
    def test_box_closure(self):
        result = design(DRAWER)
        dims = result["dimensions"]
        self.assertEqual(dims["box_external_width_mm"], 538)
        self.assertEqual(dims["box_external_depth_mm"], 490)
        self.assertEqual(dims["wall_height_mm"], 144)
        self.assertEqual(dims["box_inner_width_mm"], 508)
        self.assertEqual([p["quantity"] for p in result["parts"]], [2, 2, 1])
        self.assertEqual(result["parts"][1]["face_x_mm"], 508)
        self.assertEqual(result["parts"][2]["face_x_mm"], 538)

    def test_clearances_are_inputs_not_verified_spec(self):
        out = design(DRAWER)
        self.assertEqual(out["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertTrue(any("corredera" in x.lower() for x in out["release_blockers"]))

    def test_reject_overheight(self):
        with self.assertRaises(DesignError):
            design(dict(DRAWER, box_height_mm=301))

    def test_reject_too_narrow(self):
        with self.assertRaises(DesignError):
            design(dict(DRAWER, slide_clearance_left_mm=550))

    def test_reject_negative_clearance(self):
        with self.assertRaises(DesignError):
            design(dict(DRAWER, slide_clearance_right_mm=-2))

    def test_reject_zero_wall(self):
        with self.assertRaises(DesignError):
            design(dict(DRAWER, box_height_mm=6))

    def test_accept_zero_clearance_as_math_only(self):
        out = design(dict(DRAWER, slide_clearance_left_mm=0,
                          slide_clearance_right_mm=0))
        self.assertEqual(out["dimensions"]["box_external_width_mm"], 564)
        self.assertEqual(out["status"], "DRAFT_NOT_FOR_CUTTING")

    def test_reject_missing_data(self):
        bad = dict(DRAWER)
        del bad["bottom_thickness_mm"]
        with self.assertRaises(DesignError):
            design(bad)


class GeneralTests(unittest.TestCase):
    def test_unknown_design_type(self):
        with self.assertRaises(DesignError):
            design({"type": "closet"})

    def test_reject_non_object(self):
        with self.assertRaises(DesignError):
            design([])


if __name__ == "__main__":
    unittest.main()
