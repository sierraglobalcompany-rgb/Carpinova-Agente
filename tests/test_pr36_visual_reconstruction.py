"""Regression against ten surviving PR36 final-UX SVGs (historical CI evidence).

This validates a functional reconstruction, not the identity of the lost PR.
The checks NEVER grant fabrication or generate CAD/pieces.
"""
from __future__ import annotations

import hashlib
import unittest
from xml.etree import ElementTree as ET

from carpinova_agent.drawer_modules import guide_drawer_layout, propose_drawer_layout


BASE = {
    "type": "drawer_layout_guide", "width_mm": 500, "height_mm": 800,
    "depth_mm": 500, "small_drawers": 3,
}
# SHA-256 of SVG evidence in CarpiNova_Agente_PR36_UX_LEYENDAS_CONTEXTUALES_20cacf0.zip
CASES = {
    "C01": ({}, "9e99fbf76a323701ce9165fed7a670f63f12ba7e3e1f4a692c8183840ab6f970"),
    "C02": ({"construction": "sides_full"}, "2f718a7752b573d18d0594a2bd29d30fc7bef5cdffbcf61ee06a4ecfadcc3240"),
    "C03": ({"drawer_adjustments_mm": {"A": 100}}, "c88a5e4714f2a5a7fae994f49cee2811dc596a91d3a24d3b61f671acfe343860"),
    "C03b": ({"construction": "sides_full", "drawer_adjustments_mm": {"A": 100}}, "844074a531220d667a9cb28790f8967cf517925194cd275a41a08886ebd66c61"),
    "C04": ({"top_overhang_front_mm": 50}, "5d5f214c74cd4879ab2f80c42654fd21ec8396a54567bd3ac84c005e5bb4f7bb"),
    "C05": ({"bottom_overhang_front_mm": 100}, "2e40bd87e86d30741330d8db3591b44b18c1d12a26ad5f87108219f81316f45f"),
    "C06": ({"top_overhang_front_mm": 50, "bottom_overhang_front_mm": 100}, "b858afac78d723dd28f79646b8e9da08b8c9bcc759acfaf3c1f3b3d2430eca5f"),
    "C07": ({"top_overhang_front_mm": 50, "drawer_adjustments_mm": {"A": 100}}, "53f89f7efb3f7129acf76baa96235c3c1553ae09fe17b416577c5de5b1cdd275"),
    "N02": ({"small_drawers": 1}, "013226c05f87d6e01abd65e9eac67d4b75f5737abbd7baa6520aeb2dcc118c98"),
    "N03": ({"small_drawers": 2}, "e875ab6bc4e74b3c87e38f4a2b85339c64fe7ab1ccc95c983b2a784182e8e7ac"),
}


class PR36VisualRecovery(unittest.TestCase):
    def test_ten_ux_scenarios_match_original_svgs_and_remain_unapproved(self):
        for case, (options, expected_sha) in CASES.items():
            with self.subTest(case=case):
                spec = {**BASE, **options}
                result = guide_drawer_layout(spec)
                svg = result["sketch_svg"]
                self.assertEqual(hashlib.sha256(svg.encode("utf-8")).hexdigest(), expected_sha)
                root = ET.fromstring(svg)
                self.assertEqual(root.get("viewBox"), "0 0 1160 1325")
                self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}title"))
                self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}desc"))
                gaps = [el for el in root.iter() if el.get("data-concept") == "calculation-only"]
                self.assertEqual(len(gaps), len(result["opening_plan"]) - 1)
                self.assertTrue(all(el.get("class") == "calculation-gap" for el in gaps))
                self.assertEqual(result["status"], "NEEDS_USER_CONFIRMATION")
                self.assertEqual(result["piece_count"], 0)
                self.assertFalse(result["can_generate_f7c"])
                for field in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
                    self.assertIs(result[field], False)

    def test_join_details_follow_existing_f1_construction(self):
        for construction in ("top_bottom_full", "sides_full"):
            with self.subTest(construction=construction):
                result = guide_drawer_layout({**BASE, "construction": construction})
                root = ET.fromstring(result["sketch_svg"])
                details = [e.get("data-detail") for e in root.iter() if e.get("data-detail")]
                self.assertEqual(details.count("joint-side"), 2)
                self.assertEqual(details.count("joint-cover" if construction == "top_bottom_full" else "joint-inset"), 2)
                self.assertFalse(result["construction_review"]["is_user_confirmed"])
                self.assertEqual(result["parts"], [])

    def test_illustrations_for_wall_and_openings_do_not_authorize_manufacture(self):
        spec = {**BASE, "support_style": "wall_mounted", "wall_contact": True,
                "wall_fixing": "french_cleat", "back_style": "thin_sheet",
                "opening_systems": {"A": "handle"}}
        r = guide_drawer_layout(spec)
        self.assertIn("MF: listón francés", r["sketch_svg"])
        self.assertIn("FP · lámina delgada", r["sketch_svg"])
        self.assertIn("apertura: manija", r["sketch_svg"].lower())
        self.assertEqual(r["piece_count"], 0)
        self.assertFalse(r["fabrication_ready"])

    def test_direct_f1_proposal_keeps_its_panels_and_no_fabrication(self):
        r = propose_drawer_layout({
            "type": "drawer_layout_proposal", "width_mm": 500,
            "height_mm": 800, "depth_mm": 500, "panel_thickness_mm": 18,
            "construction": "top_bottom_full", "vertical_gap_mm": 28,
            "drawer_weights": [2, 1, 1, 1],
        })
        self.assertEqual(r["piece_count"], 0)
        self.assertFalse(r["fabrication_ready"])
        self.assertIn("calculation-only", r["sketch_svg"])


if __name__ == "__main__":
    unittest.main()
