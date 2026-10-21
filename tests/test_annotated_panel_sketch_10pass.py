"""Ten-pass review of identified furniture parts in novice drawings.

The drawing is a conversational concept. None of the visual extensions or
installation suggestions may become a manufacturing-ready panel or fixing.
"""
import copy
import unittest
import xml.etree.ElementTree as ET

from carpinova_agent.core import DesignError
from carpinova_agent.drawer_modules import guide_drawer_layout, propose_drawer_layout
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.mcp_bridge import carpinova_consultar
import json


def sample(**changes):
    spec = {
        "type": "drawer_layout_guide", "width_mm": 500,
        "height_mm": 800, "depth_mm": 500, "small_drawers": 3,
    }
    spec.update(changes)
    return spec


class TenPassPanelSketchAudit(unittest.TestCase):
    def test_01_actual_sides_full_panel_width_differs_from_carcass(self):
        r = guide_drawer_layout(sample())
        data = {part["ref"]: part for part in r["element_refs"]}
        for ref in ("T", "BS"):
            self.assertEqual(
                [data[ref][k] for k in (
                    "nominal_width_mm", "nominal_depth_mm",
                    "nominal_thickness_mm")],
                [464, 500, 18]
            )
        for ref in ("LI", "LD"):
            self.assertEqual(
                [data[ref][k] for k in (
                    "nominal_height_mm", "nominal_depth_mm",
                    "nominal_thickness_mm")],
                [800, 500, 18]
            )
        self.assertIn("Nominal: 464 × 500 × 18 mm", r["sketch_svg"])
        self.assertIn("T · TAPA SUPERIOR", r["sketch_svg"])
        self.assertIn("BS · BASE INFERIOR", r["sketch_svg"])
        self.assertIn("LI / LD · LATERALES", r["sketch_svg"])

    def test_02_alternate_existing_F1_construction_has_different_panels(self):
        base = guide_drawer_layout(sample())["proposed_layout_spec"]
        base["construction"] = "top_bottom_full"
        r = propose_drawer_layout(base)
        data = {part["ref"]: part for part in
                __import__("carpinova_agent.drawer_modules",
                           fromlist=["_guide_ref_map"])._guide_ref_map(r)}
        self.assertEqual(data["T"]["nominal_width_mm"], 500)
        self.assertEqual(data["BS"]["nominal_width_mm"], 500)
        self.assertEqual(data["LI"]["nominal_height_mm"], 764)
        self.assertEqual(data["LD"]["nominal_height_mm"], 764)
        ET.fromstring(r["sketch_svg"])

    def test_03_T_overhang_changes_only_T_while_BS_is_nominal(self):
        r = guide_drawer_layout(sample(top_overhang_left_mm=50,
                                       top_overhang_right_mm=100))
        ref = {part["ref"]: part for part in r["element_refs"]}
        self.assertEqual(ref["T"]["concept_outer_width_mm"], 650)
        self.assertEqual(ref["BS"]["concept_outer_width_mm"], 500)
        self.assertTrue(ref["T"]["extension_not_modeled_in_F1"])
        self.assertFalse(ref["BS"]["extension_not_modeled_in_F1"])
        self.assertTrue(r["unvalidated_top_extension"])
        self.assertFalse(r["unvalidated_bottom_extension"])
        self.assertEqual(r["concept_envelope"]["width_mm"], 650)
        self.assertIn('class="concept"', r["sketch_svg"])
        self.assertIn("T = tapa superior", r["sketch_text"])

    def test_04_BS_can_extend_without_changing_T_or_F1_carcase(self):
        r = guide_drawer_layout(sample(bottom_overhang_left_mm=80,
                                       bottom_overhang_right_mm=40))
        ref = {part["ref"]: part for part in r["element_refs"]}
        self.assertEqual(ref["BS"]["concept_outer_width_mm"], 620)
        self.assertEqual(ref["T"]["nominal_width_mm"], 464)
        self.assertEqual(ref["T"]["concept_outer_width_mm"], 500)
        self.assertEqual(r["external_dimensions_mm"]["width"], 500)
        self.assertEqual(r["clear_height_mm"], 764)
        self.assertTrue(r["unvalidated_bottom_extension"])
        self.assertEqual(r["concept_envelope"]["width_mm"], 620)
        self.assertFalse(r["can_generate_f7c"])
        ET.fromstring(r["sketch_svg"])

    def test_05_front_back_extents_are_visible_in_side_view(self):
        r = guide_drawer_layout(sample(top_overhang_front_mm=50,
                                       bottom_overhang_rear_mm=80))
        self.assertEqual(r["concept_envelope"]["depth_mm"], 630)
        self.assertEqual(r["concept_envelope"]["width_mm"], 500)
        self.assertIn("VISTA LATERAL", r["sketch_svg"])
        self.assertIn("frente 50 / atrás 0 mm", r["sketch_svg"])
        self.assertIn("frente 0 / atrás 80 mm", r["sketch_svg"])
        self.assertEqual(r["assembled_external_depth_mm"], None)
        ET.fromstring(r["sketch_svg"])

    def test_06_mixed_extensions_use_max_envelope_not_invalid_sum(self):
        r = guide_drawer_layout(sample(
            top_overhang_left_mm=30, top_overhang_right_mm=10,
            bottom_overhang_left_mm=70, bottom_overhang_right_mm=50,
            top_overhang_front_mm=25, bottom_overhang_rear_mm=40,
        ))
        self.assertEqual(r["concept_envelope"]["width_mm"], 620)
        self.assertEqual(r["concept_envelope"]["depth_mm"], 565)
        self.assertEqual(r["concept_envelope"]["exceeds_carcass_width_mm"], 120)
        self.assertEqual(r["concept_envelope"]["exceeds_carcass_depth_mm"], 65)
        self.assertTrue(any("límite exterior" in x for x in r["blockers"]))

    def test_07_large_drawer_label_is_stable_after_raising_A(self):
        r = guide_drawer_layout(sample(drawer_adjustments_mm={"A": 100}))
        self.assertEqual([x["nominal_opening_height_mm"]
                          for x in r["element_refs"][:4]],
                         [236, 111, 111, 222])
        self.assertEqual(r["large_drawer_ref"], "D")
        self.assertIn("D · GAVETA 222 mm", r["sketch_svg"])
        self.assertIn("A · CAJÓN 236 mm", r["sketch_svg"])
        self.assertNotIn("A · GAVETA", r["sketch_svg"])
        self.assertIn("D (D1): gaveta solicitada", r["sketch_text"])

    def test_08_support_height_changes_body_and_panel_lengths(self):
        r = guide_drawer_layout(sample(support_style="plinth",
                                       support_height_mm=100))
        ref = {part["ref"]: part for part in r["element_refs"]}
        self.assertEqual(r["overall_height_mm"], 800)
        self.assertEqual(r["carcass_height_mm"], 700)
        self.assertEqual(ref["LI"]["nominal_height_mm"], 700)
        self.assertEqual(ref["LD"]["nominal_height_mm"], 700)
        self.assertEqual(ref["T"]["nominal_width_mm"], 464)
        self.assertIn("AP · zócalo/banqueo · 100 mm", r["sketch_svg"])
        self.assertIn("ALTO 800 mm", r["sketch_svg"])
        self.assertFalse(r["fabrication_ready"])

    def test_09_wall_back_and_mount_are_not_real_fittings(self):
        r = guide_drawer_layout(sample(
            support_style="wall_mounted", wall_contact=True,
            wall_fixing="french_cleat", back_style="thin_sheet",
        ))
        self.assertIsNone(r["wall_bottom_above_floor_mm"])
        self.assertEqual(r["back_thickness_mm"], 2)
        self.assertTrue(r["unvalidated_mounting"])
        self.assertTrue(r["unvalidated_back_panel"])
        self.assertIn("MF · listón francés", r["sketch_svg"])
        self.assertIn("FP · lámina delgada", r["sketch_svg"])
        self.assertEqual(r["parts"], [])
        self.assertEqual(r["piece_count"], 0)

    def test_10_invalid_contour_dimensions_rejected_not_clamped(self):
        for key in (
            "top_overhang_left_mm", "top_overhang_right_mm",
            "top_overhang_front_mm", "top_overhang_rear_mm",
            "bottom_overhang_left_mm", "bottom_overhang_right_mm",
            "bottom_overhang_front_mm", "bottom_overhang_rear_mm",
        ):
            for invalid in (-1, 201, 1.25, True, "50"):
                with self.subTest(key=key, invalid=invalid):
                    with self.assertRaises(DesignError):
                        guide_drawer_layout(sample(**{key: invalid}))

    def test_11_review_is_repeatable_with_full_user_state_and_MCP(self):
        spec = sample(bottom_overhang_left_mm=100, opening_systems={"A": "handle"})
        r1 = guide_drawer_layout(spec)
        r2 = guide_drawer_layout(copy.deepcopy(r1["review_state"]))
        self.assertEqual(r1["sketch_svg"], r2["sketch_svg"])
        self.assertEqual(r1["element_refs"], r2["element_refs"])
        query = {"action": "modular", "module_spec": spec}
        rpc = carpinova_consultar(json.dumps(query, ensure_ascii=False))
        self.assertEqual(rpc["modular"]["element_refs"], r1["element_refs"])
        self.assertEqual(rpc["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(len(rpc["questions"]), 1)

    def test_13_real_png_render_of_front_and_side_views_when_engine_available(self):
        try:
            import resvg_py
            from PIL import Image
        except ImportError:
            self.skipTest("optional PNG renderer unavailable outside MCP preflight")
        from io import BytesIO
        for kwargs in (
            {}, {"top_overhang_left_mm": 50,
                 "bottom_overhang_right_mm": 100},
            {"support_style": "legs", "support_height_mm": 100},
            {"top_overhang_front_mm": 75,
             "bottom_overhang_rear_mm": 50},
        ):
            with self.subTest(kwargs=kwargs):
                svg = guide_drawer_layout(sample(**kwargs))["sketch_svg"]
                png = resvg_py.svg_to_bytes(svg_string=svg, width=1160)
                img = Image.open(BytesIO(png))
                img.verify()
                self.assertEqual(Image.open(BytesIO(png)).size, (1160, 930))
                self.assertGreater(len(png), 10000)

    def test_12_svg_structure_is_parseable_accessible_and_render_review_only(self):
        r = consult_maestro({"action": "modular", "module_spec": sample()})
        s = r["modular"]["sketch_svg"]
        root = ET.fromstring(s)
        self.assertEqual(root.get("role"), "img")
        self.assertEqual(root.get("viewBox"), "0 0 1160 930")
        self.assertIn("tapa T, base BS", root.get("aria-label"))
        self.assertIn("LI / LD · LATERALES", s)
        self.assertIn("NO CORTAR, TALADRAR NI COMPRAR", s)
        for flag in ("fabrication_ready", "cutting_ready",
                     "drilling_ready", "purchase_ready"):
            self.assertFalse(r[flag])
            self.assertFalse(r["modular"][flag])
        self.assertEqual(r["modular"]["piece_count"], 0)


if __name__ == "__main__":
    unittest.main()
