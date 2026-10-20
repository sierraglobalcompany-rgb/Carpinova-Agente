"""Tests for source-backed hardware advice and fail-closed drilling."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hardware.catalog import HardwareError, load_hardware_catalog, suggest_hinge


class HardwareCatalogTests(unittest.TestCase):
    def test_catalog_source_family_and_styles(self):
        d = load_hardware_catalog()
        self.assertEqual(d["manufacturer"], "Blum")
        self.assertEqual(len(d["hinges"]), 3)
        self.assertEqual({h["front_style"] for h in d["hinges"]},
                         {"overlay", "dual", "inset"})
        self.assertEqual({h["sku"] for h in d["hinges"]},
                         {"71B3550", "71B3650", "71B3750"})
        self.assertEqual(d["scope"], "REFERENCE_SELECTION_ONLY")

    def test_candidate_overlay(self):
        r = suggest_hinge({"manufacturer": "Blum", "front_style": "overlay"})
        self.assertEqual(r["candidate_hinge_sku"], "71B3550")
        self.assertEqual(r["status"], "BLOCKED_HARDWARE_SPEC")
        self.assertFalse(r["purchase_ready"])
        self.assertFalse(r["drilling_ready"])
        self.assertEqual(r["drilling_coordinates"], [])

    def test_candidate_dual(self):
        r = suggest_hinge({"front_style": "dual"})
        self.assertEqual(r["candidate_hinge_sku"], "71B3650")

    def test_candidate_inset(self):
        r = suggest_hinge({"front_style": "inset"})
        self.assertEqual(r["candidate_hinge_sku"], "71B3750")

    def test_missing_style_asks_instead_of_guessing(self):
        r = suggest_hinge({"door_thickness_mm": 18})
        self.assertIsNone(r["candidate_hinge_sku"])
        self.assertIn("front_style: overlay, dual o inset", r["missing_inputs"])
        self.assertFalse(r["drilling_ready"])

    def test_wrong_hinge_sku_is_not_substituted(self):
        r = suggest_hinge({"front_style": "overlay", "hinge_sku": "71B3750"})
        self.assertEqual(r["status"], "BLOCKED_HARDWARE_SPEC")
        self.assertIsNone(r["candidate_hinge_sku"])
        self.assertFalse(r["drilling_ready"])

    def test_unrecognized_sku_blocks(self):
        r = suggest_hinge({"front_style": "overlay", "hinge_sku": "71B3550_fake"})
        self.assertIsNone(r["candidate_hinge_sku"])
        self.assertTrue(r["blockers"])

    def test_plate_reference_only_no_drill_points(self):
        r = suggest_hinge({"front_style": "inset", "plate_sku": "173H7100",
                           "door_thickness_mm": 18})
        self.assertEqual(r["candidate_plate_sku"], "173H7100")
        self.assertEqual(r["mounting_pattern"]["front_edge_reference_mm"], 37)
        self.assertEqual(r["mounting_pattern"]["hole_pitch_reference_mm"], 32)
        self.assertTrue(r["mounting_pattern"]["not_drilling_coordinates"])
        self.assertEqual(r["drilling_coordinates"], [])
        self.assertFalse(r["purchase_ready"])

    def test_plate_variant_remains_distinct(self):
        a = suggest_hinge({"front_style": "overlay", "plate_sku": "173H7100"})
        b = suggest_hinge({"front_style": "overlay", "plate_sku": "173H7130"})
        self.assertEqual(a["mounting_pattern"]["plate_spacing_mm"], 0)
        self.assertEqual(b["mounting_pattern"]["plate_spacing_mm"], 3)
        self.assertFalse(a["drilling_ready"])
        self.assertFalse(b["drilling_ready"])

    def test_unknown_plate_not_fabricated(self):
        r = suggest_hinge({"front_style": "overlay", "plate_sku": "OTHER"})
        self.assertIsNone(r["candidate_plate_sku"])
        self.assertIsNone(r["mounting_pattern"])
        self.assertEqual(r["drilling_coordinates"], [])

    def test_thin_door_rejected(self):
        for t in (12, 13):
            with self.subTest(t=t):
                r = suggest_hinge({"front_style": "overlay",
                                   "door_thickness_mm": t})
                self.assertTrue(any("no supera" in x for x in r["blockers"]))
                self.assertFalse(r["drilling_ready"])

    def test_thick_door_is_not_auto_approved(self):
        r = suggest_hinge({"front_style": "overlay", "door_thickness_mm": 25})
        self.assertTrue(any("no certifica" in x for x in r["blockers"]))
        self.assertFalse(r["drilling_ready"])

    def test_missing_material_and_weight_not_ignored(self):
        r = suggest_hinge({"front_style": "inset"})
        self.assertIn("door_material", r["missing_inputs"])
        self.assertIn("door_weight_g", r["missing_inputs"])
        self.assertIn("door_height_mm", r["missing_inputs"])

    def test_all_inputs_still_draft(self):
        r = suggest_hinge({
            "front_style": "overlay", "hinge_sku": "71B3550",
            "plate_sku": "173H7100", "door_thickness_mm": 18,
            "door_height_mm": 680, "door_weight_g": 3200,
            "door_material": "MDF", "manufacturer": "Blum"
        })
        self.assertEqual(r["missing_inputs"], [])
        self.assertFalse(r["drilling_ready"])
        self.assertFalse(r["purchase_ready"])
        self.assertGreater(len(r["blockers"]), 3)

    def test_reject_untrusted_manufacturer(self):
        with self.assertRaises(HardwareError):
            suggest_hinge({"manufacturer": "Other", "front_style": "overlay"})

    def test_reject_unstructured_numeric_data(self):
        for value in (True, 18.2, -1, 0, "18"):
            with self.subTest(value=value), self.assertRaises(HardwareError):
                suggest_hinge({"front_style": "overlay", "door_thickness_mm": value})

    def test_reject_unknown_field(self):
        with self.assertRaises(HardwareError):
            suggest_hinge({"front_style": "overlay", "drilling_coordinates": [[1, 2]]})

    def test_reject_non_object(self):
        with self.assertRaises(HardwareError):
            suggest_hinge([])

    def test_reject_changed_manufacturer(self):
        c = load_hardware_catalog()
        c["manufacturer"] = "Other"
        with TemporaryDirectory() as root:
            p = Path(root) / "catalog.json"
            p.write_text(json.dumps(c))
            with self.assertRaises(HardwareError):
                load_hardware_catalog(p)

    def test_reject_duplicate_sku(self):
        c = load_hardware_catalog()
        c["hinges"][1]["sku"] = c["hinges"][0]["sku"]
        with TemporaryDirectory() as root:
            p = Path(root) / "catalog.json"
            p.write_text(json.dumps(c))
            with self.assertRaises(HardwareError):
                load_hardware_catalog(p)

    def test_reject_fabrication_claim_in_catalog(self):
        c = load_hardware_catalog()
        c["not_present"]["hinge_plate_fitment_authorized"] = True
        with TemporaryDirectory() as root:
            p = Path(root) / "catalog.json"
            p.write_text(json.dumps(c))
            with self.assertRaises(HardwareError):
                load_hardware_catalog(p)

    def test_reject_modified_source_url(self):
        c = load_hardware_catalog()
        c["source_references"]["blum_hinges_pdf"]["url"] = (
            "https://not-blum.example/false.pdf"
        )
        with TemporaryDirectory() as root:
            p = Path(root) / "catalog.json"
            p.write_text(json.dumps(c))
            with self.assertRaises(HardwareError):
                load_hardware_catalog(p)

    def test_missing_sku_is_not_buying_advice(self):
        r = suggest_hinge({"front_style": "dual"})
        self.assertFalse(r["purchase_ready"])
        self.assertTrue(any("actual" in x for x in r["blockers"]))


if __name__ == "__main__":
    unittest.main()
