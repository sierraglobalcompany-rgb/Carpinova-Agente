"""F7: consult contextual guidance without inventing mechanical data."""
import unittest
from carpinova_agent.construction_advice import AdviceError, construction_advice


class AdvisoryTests(unittest.TestCase):
    def test_empty_request_questions(self):
        r=construction_advice({})
        self.assertEqual(r["status"],"ADVISORY_ONLY")
        self.assertEqual(len(r["questions"]),3)
        self.assertFalse(r["fabrication_ready"])
        self.assertFalse(r["drilling_ready"])
        self.assertFalse(r["cutting_ready"])
        self.assertFalse(r["purchase_ready"])
        self.assertTrue(r["blockers"])

    def test_shop_edge_detail(self):
        r=construction_advice({"edge_workflow":"cut_shop",
                "edge_variant":"flexible","edge_material":"abs","edge_exposure":"visible"})
        self.assertTrue(any("Taller:" in x for x in r["recommendations"]))
        self.assertTrue(any("ABS" in x or "PVC" in x for x in r["recommendations"]))
        self.assertIsNone(next((x for x in r["questions"] if x["field"]=="edge_adhesive"),None))

    def test_diy_preglued(self):
        r=construction_advice({"edge_workflow":"home",
              "edge_adhesive":"pre_glued","edge_material":"melamine",
              "edge_variant":"flexible","edge_exposure":"visible"})
        self.assertTrue(any("retal" in x for x in r["recommendations"]))
        self.assertFalse(any("temperatura" in x for x in r["recommendations"]))

    def test_diy_eva_requires_machine(self):
        r=construction_advice({"edge_workflow":"home",
             "edge_adhesive":"eva_hot_melt","edge_exposure":"wet_exposed"})
        self.assertTrue(any("equipo" in x for x in r["recommendations"]))
        self.assertIn("edge_rehau",r["evidence_refs"])
        self.assertTrue(r["blockers"])

    def test_diy_without_glue_asks(self):
        r=construction_advice({"edge_workflow":"home"})
        self.assertIn("edge_adhesive",r["all_missing_fields"])

    def test_rigid_diy_needs_sku(self):
        r=construction_advice({"edge_workflow":"home","edge_variant":"rigid"})
        self.assertTrue(any("SKU" in x for x in r["blockers"]))

    def test_water_exposure_not_waterproof_claim(self):
        r=construction_advice({"application":"bathroom","water_exposure":True,
                                "edge_exposure":"wet_exposed"})
        self.assertTrue(any("impermeable" in x for x in r["blockers"]))

    def test_service_full_back_conflict(self):
        r=construction_advice({"back_style":"full","has_services":True})
        self.assertTrue(any("interfiere" in x for x in r["blockers"]))

    def test_partial_back_preserves_access(self):
        r=construction_advice({"back_style":"partial_service","has_services":True})
        self.assertTrue(any("registrable" in x for x in r["recommendations"]))

    def test_no_back_block_rigidity(self):
        r=construction_advice({"back_style":"no_back","has_services":True})
        self.assertTrue(any("rigidez" in x for x in r["recommendations"]))

    def test_floor_legs(self):
        r=construction_advice({"support":"floor_legs"})
        self.assertTrue(any("Patas:" in x for x in r["recommendations"]))

    def test_plinth_banquero_term_uncertainty(self):
        r=construction_advice({"support":"plinth_base"})
        self.assertTrue(any("banquero" in x for x in r["notes"]))
        self.assertTrue(any("zócalo" in x for x in r["recommendations"]))

    def test_french_cleat_asks_wall_type(self):
        r=construction_advice({"support":"wall_french_cleat"})
        self.assertIn("wall_substrate",r["all_missing_fields"])
        self.assertTrue(any("suspendido" in x for x in r["blockers"]))
        self.assertIn("wall_blum",r["evidence_refs"])

    def test_rail_requires_anchoring_proof(self):
        r=construction_advice({"support":"wall_rail","wall_substrate":"drywall"})
        self.assertTrue(any("anclajes" in x for x in r["blockers"]))
        self.assertNotIn("wall_substrate",r["all_missing_fields"])

    def test_angles_not_equal_structure(self):
        r=construction_advice({"joint":"concealed_angles"})
        self.assertTrue(any("estructural" in x for x in r["recommendations"]))

    def test_cam_dowels_need_templates(self):
        r=construction_advice({"joint":"cam_dowels"})
        self.assertTrue(any("plantilla" in x for x in r["recommendations"]))

    def test_screw_pilot_not_guessed(self):
        r=construction_advice({"joint":"visible_screws"})
        self.assertTrue(any("material/tornillo" in x for x in r["recommendations"]))

    def test_invalid_category(self):
        with self.assertRaises(AdviceError):
            construction_advice({"support":"unknown_boat"})

    def test_boolean_not_int(self):
        with self.assertRaises(AdviceError):
            construction_advice({"has_services":1})

    def test_no_unknown_drill_claim(self):
        with self.assertRaises(AdviceError):
            construction_advice({"drill_mm":35})

    def test_question_cap(self):
        r=construction_advice({},max_questions=2)
        self.assertEqual(len(r["questions"]),2)
        self.assertGreater(len(r["all_missing_fields"]),2)

    def test_question_cap_type(self):
        with self.assertRaises(AdviceError):
            construction_advice({},max_questions=True)

    def test_all_holes_always_blocked(self):
        configs=[
            {"application":"kitchen","back_style":"no_back","support":"floor_legs"},
            {"application":"bathroom","back_style":"partial_service","support":"wall_rail"},
            {"joint":"concealed_angles","edge_workflow":"home","edge_adhesive":"pre_glued"},
        ]
        for c in configs:
            with self.subTest(c=c):
                r=construction_advice(c)
                self.assertFalse(r["drilling_ready"])
                self.assertFalse(r["fabrication_ready"])
                self.assertTrue(r["blockers"])


if __name__=="__main__":
    unittest.main()
