import unittest
from carpinova_agent.maestro import consult_maestro,MaestroError

CABINET={"project_type":"gabinete","width_mm":600,"height_mm":720,
         "depth_mm":560,"panel_thickness_mm":18,"construction":"sides_full"}
CONSTRUCTION={"application":"bathroom","back_style":"partial_service","has_services":True,
       "support":"wall_french_cleat","wall_substrate":"masonry","edge_workflow":"home"}

class MaestroConstructionTests(unittest.TestCase):
    def test_construction_action(self):
        r=consult_maestro({"action":"construction","construction":CONSTRUCTION})
        self.assertEqual(r["status"],"ADVISORY_ONLY")
        self.assertEqual(r["construction"]["status"],"ADVISORY_ONLY")
        self.assertFalse(r["fabrication_ready"])
        self.assertFalse(r["drilling_ready"])
        self.assertTrue(any("suspendido" in x for x in r["blockers"]))
        self.assertLessEqual(len(r["questions"]),3)

    def test_combined_prioritizes_missing_panel_dimensions(self):
        req={"action":"combined","project":{"project_type":"gabinete"},
             "construction":CONSTRUCTION}
        r=consult_maestro(req)
        self.assertEqual(r["status"],"NEEDS_INPUT")
        self.assertEqual(r["questions"][0]["field"],"width_mm")
        self.assertLessEqual(len(r["questions"]),3)

    def test_complete_project_plus_support_advice(self):
        req={"action":"combined","project":CABINET,"construction":CONSTRUCTION}
        r=consult_maestro(req)
        self.assertEqual(r["status"],"DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(r["project"]["design"]["dimensions"]["clear_width_mm"],564)
        self.assertEqual(r["construction"]["status"],"ADVISORY_ONLY")
        self.assertFalse(r["cutting_ready"])
        self.assertFalse(r["purchase_ready"])

    def test_reject_unstructured(self):
        with self.assertRaises(MaestroError):
            consult_maestro({"action":"construction","construction":"patas"})

    def test_reject_missing(self):
        with self.assertRaises(MaestroError):
            consult_maestro({"action":"construction"})

    def test_cannot_mix_incompatible_fields(self):
        with self.assertRaises(MaestroError):
            consult_maestro({"action":"construction","construction":{},
                "hardware":{"front_style":"overlay"}})

    def test_question_limit(self):
        req={"action":"combined","project":{"project_type":"gabinete"},
             "construction":CONSTRUCTION}
        r=consult_maestro(req,max_questions=2)
        self.assertEqual(len(r["questions"]),2)

if __name__=="__main__":
    unittest.main()
