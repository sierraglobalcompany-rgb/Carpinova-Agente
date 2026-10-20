"""F7B -- compare native scene observations against one CADExchange.

These tests use observed-box fixtures; they DO NOT claim FreeCAD or Blender
executables have run. A real app must supply observations from its objects.
"""
import copy
import json
from pathlib import Path
import unittest

from carpinova_agent.core import DesignError
from carpinova_agent.cad_exchange import cad_exchange
from carpinova_agent.modular import design_modular_run
from integrations.cad_native import native_boxes
from integrations.geometry_audit import verify_native_boxes

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "modular-closet.json"


def prepared():
    spec = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    source = cad_exchange(design_modular_run(spec))
    observations = [
        {
            "piece_id": p["piece_id"],
            "native_origin_xyz_mm": list(p["native_origin_xyz_mm"]),
            "native_size_xyz_mm": list(p["native_size_xyz_mm"]),
        }
        for p in native_boxes(source)
    ]
    return source, observations


class SceneVerificationTests(unittest.TestCase):
    def test_identical_native_bboxes_accepted(self):
        source, observed = prepared()
        report = verify_native_boxes(source, observed)
        self.assertEqual(report["status"], "NATIVE_GEOMETRY_MATCH")
        self.assertEqual(report["verified_piece_count"], 8)
        self.assertEqual(report["max_abs_error_mm"], 0)
        self.assertEqual(report["geometry_sha256"], source["geometry_sha256"])
        self.assertFalse(report["fabrication_ready"])
        self.assertFalse(report["cutting_ready"])

    def test_order_does_not_matter(self):
        source, observed = prepared()
        report = verify_native_boxes(source, list(reversed(observed)))
        self.assertEqual(report["verified_piece_count"], 8)

    def test_floating_point_noise_accepted_under_explicit_tolerance(self):
        source, observed = prepared()
        observed[0]["native_origin_xyz_mm"][0] += 0.001
        report = verify_native_boxes(source, observed)
        self.assertAlmostEqual(report["max_abs_error_mm"], 0.001)

    def test_shifted_panel_fails(self):
        source, observed = prepared()
        observed[1]["native_origin_xyz_mm"][2] += 1
        with self.assertRaisesRegex(DesignError, "Divergencia CAD"):
            verify_native_boxes(source, observed)

    def test_resized_panel_fails(self):
        source, observed = prepared()
        observed[3]["native_size_xyz_mm"][1] -= 2
        with self.assertRaisesRegex(DesignError, "Divergencia CAD"):
            verify_native_boxes(source, observed)

    def test_wrong_axis_swap_fails(self):
        source, observed = prepared()
        observed[1]["native_size_xyz_mm"].reverse()
        with self.assertRaises(DesignError):
            verify_native_boxes(source, observed)

    def test_one_missing_panel_fails(self):
        source, observed = prepared()
        with self.assertRaises(DesignError):
            verify_native_boxes(source, observed[:-1])

    def test_duplicate_panel_fails(self):
        source, observed = prepared()
        observed[1]["piece_id"] = observed[0]["piece_id"]
        with self.assertRaises(DesignError):
            verify_native_boxes(source, observed)

    def test_unknown_panel_name_fails(self):
        source, observed = prepared()
        observed[2]["piece_id"] = "EXTRA_HOLE"
        with self.assertRaises(DesignError):
            verify_native_boxes(source, observed)

    def test_bad_number_fails(self):
        source, observed = prepared()
        for num in (float("inf"), float("nan"), True, "42"):
            with self.subTest(num=str(num)):
                obs = copy.deepcopy(observed)
                obs[0]["native_size_xyz_mm"][0] = num
                with self.assertRaises(DesignError):
                    verify_native_boxes(source, obs)

    def test_zero_size_fails(self):
        source, observed = prepared()
        observed[0]["native_size_xyz_mm"][0] = 0
        with self.assertRaises(DesignError):
            verify_native_boxes(source, observed)

    def test_invalid_tolerance_fails(self):
        source, observed = prepared()
        for number in (-1, True, 1, float("nan"), "0.02"):
            with self.subTest(tolerance=number):
                with self.assertRaises(DesignError):
                    verify_native_boxes(source, observed, tolerance_mm=number)

    def test_bad_observation_schema_fails(self):
        source, observed = prepared()
        observed[0]["execute_code"] = "no"
        with self.assertRaises(DesignError):
            verify_native_boxes(source, observed)

    def test_tampered_exchange_fails_before_comparison(self):
        source, observed = prepared()
        source["boxes"][0]["size_xyz_mm"][0] = 99
        with self.assertRaises(DesignError):
            verify_native_boxes(source, observed)

    def test_fractional_native_coords_prohibited_if_not_near_source(self):
        source, observed = prepared()
        observed[0]["native_origin_xyz_mm"][0] = 0.5
        with self.assertRaises(DesignError):
            verify_native_boxes(source, observed)

    def test_exact_zero_tolerance(self):
        source, observed = prepared()
        self.assertEqual(verify_native_boxes(
            source, observed, tolerance_mm=0)["max_abs_error_mm"], 0)


if __name__ == "__main__":
    unittest.main()
