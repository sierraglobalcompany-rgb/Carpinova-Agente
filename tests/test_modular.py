"""F6: dimensional closure and finish annotations of open modular carcasses."""
import copy
import json
from pathlib import Path
import unittest

from carpinova_agent.core import DesignError, design
from carpinova_agent.modular import design_modular_run

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def fixture(name="modular-closet.json"):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class ModularTests(unittest.TestCase):
    def test_two_modules_four_physical_parts_each(self):
        out = design_modular_run(fixture())
        self.assertEqual(out["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(out["piece_count"], 8)
        self.assertEqual(len({x["piece_id"] for x in out["parts"]}), 8)
        self.assertEqual([x["start_x_mm"] for x in out["modules"]], [0, 950])
        self.assertEqual(out["total_module_width_mm"], 2000)
        self.assertFalse(out["fabrication_ready"])
        self.assertFalse(out["cutting_ready"])
        self.assertFalse(out["drilling_ready"])
        self.assertFalse(out["purchase_ready"])

    def test_f1_only_source_for_dimensions(self):
        data = fixture()
        out = design_modular_run(data)
        for i, module in enumerate(data["modules"]):
            one = design({
                "type": "cabinet", "width_mm": module["width_mm"],
                "height_mm": data["height_mm"], "depth_mm": data["depth_mm"],
                "panel_thickness_mm": module["panel_thickness_mm"],
                "construction": module["construction"],
            })
            actual = out["parts"][4*i:4*i+4]
            for p in actual:
                source = one["parts"][0 if p["role"].endswith("side") else 1]
                self.assertEqual(p["nominal_face_x_mm"], source["face_x_mm"])
                self.assertEqual(p["nominal_face_y_mm"], source["face_y_mm"])
                self.assertEqual(p["source_formula"], source["calculation"])
                self.assertEqual(p["source_engine"], "F1_CORE_CABINET")

    def test_distinct_construction_geometry(self):
        out = design_modular_run(fixture())
        side_l = next(p for p in out["parts"] if p["piece_id"] == "LEFT-LEFT_SIDE")
        side_r = next(p for p in out["parts"] if p["piece_id"] == "RIGHT-LEFT_SIDE")
        top_l = next(p for p in out["parts"] if p["piece_id"] == "LEFT-TOP")
        top_r = next(p for p in out["parts"] if p["piece_id"] == "RIGHT-TOP")
        self.assertEqual(side_l["nominal_face_y_mm"], 2400)
        self.assertEqual(side_r["nominal_face_y_mm"], 2364)
        self.assertEqual(top_l["nominal_face_x_mm"], 914)
        self.assertEqual(top_r["nominal_face_x_mm"], 1050)

    def test_end_of_left_second_module(self):
        result = design_modular_run(fixture())
        self.assertEqual(result["modules"][1]["start_x_mm"], 950)
        right = next(p for p in result["parts"] if p["piece_id"] == "RIGHT-RIGHT_SIDE")
        self.assertEqual(right["nominal_origin_xyz_mm"][0], 2000-18)

    def test_grain_preserved_per_piece(self):
        out = design_modular_run(fixture())
        values = {(p["module_id"], p["role"]): p["grain_axis"] for p in out["parts"]}
        self.assertEqual(values[("LEFT", "left_side")], "face_y")
        self.assertEqual(values[("RIGHT", "bottom")], "face_x")
        self.assertTrue(all(p["finished_cut_dimensions_mm"] is None
                            for p in out["parts"]))

    def test_edgeband_lengths_x_and_y(self):
        out = design_modular_run(fixture())
        left_side = next(p for p in out["parts"] if p["piece_id"] == "LEFT-LEFT_SIDE")
        left_top = next(p for p in out["parts"] if p["piece_id"] == "LEFT-TOP")
        self.assertEqual(left_side["edgebanding_nominal_total_mm"], 2400)
        self.assertEqual(left_top["edgebanding_nominal_total_mm"], 914)
        self.assertEqual(left_side["edgebanding_thickness_mm"], 1)

    def test_no_finish_is_not_guessed(self):
        out = design_modular_run(fixture("modular-kitchen.json"))
        self.assertEqual(out["piece_count"], 8)
        self.assertEqual(out["parts"][0]["grain_axis"], "UNCONFIRMED")
        self.assertEqual(out["parts"][0]["edgebanding_edges"], "UNCONFIRMED")
        self.assertIsNone(out["parts"][0]["edgebanding_nominal_total_mm"])
        self.assertTrue(any("veta" in item for item in out["blockers"]))

    def test_no_silent_filler_when_short(self):
        spec = fixture()
        spec["modules"][1]["width_mm"] = 1000
        out = design_modular_run(spec)
        self.assertEqual(out["status"], "NEEDS_LAYOUT_REVISION")
        self.assertEqual(out["parts"], [])
        self.assertEqual(out["total_module_width_mm"], 1950)

    def test_no_silent_overlap_when_wide(self):
        spec = fixture()
        spec["modules"][1]["width_mm"] = 1200
        out = design_modular_run(spec)
        self.assertEqual(out["status"], "NEEDS_LAYOUT_REVISION")
        self.assertEqual(out["parts"], [])

    def test_conflict_with_narrowest_opening(self):
        spec = fixture()
        spec["site_width_mm"]["bottom"] = 1999
        out = design_modular_run(spec)
        self.assertEqual(out["status"], "SITE_CONFLICT")
        self.assertTrue(any("menor luz" in item for item in out["blockers"]))
        self.assertFalse(out["fabrication_ready"])

    def test_equal_opening_is_conflict(self):
        spec = fixture()
        spec["site_width_mm"]["middle"] = 2000
        out = design_modular_run(spec)
        self.assertEqual(out["status"], "SITE_CONFLICT")

    def test_built_in_without_site_measurements(self):
        spec = fixture()
        del spec["site_width_mm"]
        out = design_modular_run(spec)
        self.assertEqual(out["status"], "NEEDS_SITE_MEASUREMENTS")
        self.assertFalse(out["site"]["complete"])

    def test_complete_site_distances_without_hidden_tolerance(self):
        out = design_modular_run(fixture())
        self.assertEqual(out["site"]["minimum_mm"], 2012)
        self.assertEqual(out["site"]["variation_mm"], 23)
        self.assertEqual(out["site"]["nominal_gap_at_narrowest_mm"], 12)
        self.assertTrue(out["blockers"])
        self.assertFalse(out["cutting_ready"])

    def test_freestanding_kitchen_is_conceptual(self):
        out = design_modular_run(fixture("modular-kitchen.json"))
        self.assertEqual(out["application"], "kitchen")
        self.assertEqual(out["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(out["modules"][0]["start_x_mm"], 0)
        self.assertEqual(out["modules"][1]["start_x_mm"], 600)
        self.assertTrue(any("zócalo" in x for x in out["blockers"]))

    def test_wall_mounted_requires_verification(self):
        spec = fixture("modular-kitchen.json")
        spec["installation"] = "wall_mounted"
        out = design_modular_run(spec)
        self.assertIn("suspendido", out["blockers"][0].lower())

    def test_reject_non_object(self):
        with self.assertRaises(DesignError):
            design_modular_run([])

    def test_reject_missing_root_field(self):
        spec = fixture()
        del spec["application"]
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_reject_unknown_root_field(self):
        spec = fixture()
        spec["door_drilling_mm"] = 35
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_reject_duplicate_ids(self):
        spec = fixture()
        spec["modules"][1]["module_id"] = "LEFT"
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_reject_boolean_or_float_measurement(self):
        for value in (True, 2000.0, -20, 0):
            spec = fixture()
            spec["width_mm"] = value
            with self.subTest(value=value), self.assertRaises(DesignError):
                design_modular_run(spec)

    def test_reject_dimension_smaller_than_two_thicknesses(self):
        spec = fixture()
        spec["modules"][0]["width_mm"] = 36
        spec["modules"][1]["width_mm"] = 1964
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_reject_third_party_dimension_unknown(self):
        spec = fixture()
        spec["modules"][0]["cut_width_mm"] = 912
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_reject_partial_finish(self):
        spec = fixture()
        del spec["modules"][0]["finish"]["grain"]["bottom"]
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_reject_invalid_grain(self):
        spec = fixture()
        spec["modules"][0]["finish"]["grain"]["left_side"] = "north"
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_reject_repeated_edge(self):
        spec = fixture()
        spec["modules"][0]["finish"]["edgebanding"]["left_side"] = ["x_min", "x_min"]
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_reject_nonexistent_edge(self):
        spec = fixture()
        spec["modules"][0]["finish"]["edgebanding"]["left_side"] = ["north"]
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_reject_band_without_thickness(self):
        spec = fixture()
        del spec["modules"][0]["finish"]["edgeband_thickness_mm"]
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_reject_nonstandard_fronts(self):
        spec = fixture()
        spec["modules"][0]["fronts"] = "overlay"
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_does_not_mutate_input(self):
        spec = fixture()
        before = copy.deepcopy(spec)
        design_modular_run(spec)
        self.assertEqual(before, spec)

    def test_plain_open_carcase_has_four_parts_per_module(self):
        spec = fixture("modular-kitchen.json")
        spec["modules"] = spec["modules"][:1]
        spec["width_mm"] = 600
        out = design_modular_run(spec)
        self.assertEqual(out["piece_count"], 4)


if __name__ == "__main__":
    unittest.main()
