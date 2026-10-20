"""Regression tests for one coordinated, explicitly nonmanufacturing agent."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from carpinova_agent.maestro import MaestroError, consult_maestro
from hardware import HardwareError


CABINET = {
    "project_type": "gabinete", "width_mm": 600, "height_mm": 720,
    "depth_mm": 560, "panel_thickness_mm": 18,
    "construction": "sides_full",
}
HARDWARE = {"front_style": "overlay", "hinge_sku": "71B3550",
            "door_thickness_mm": 18}
FOUND = {
    "query": "bisagras",
    "coverage": "FULL_BOOK",
    "knowledge_version": "1.2.0",
    "results": [
        {
            "content_id": "CONTENT-CPNC-2025-P0110-001",
            "source_book": "cpnc-2025",
            "page_id": "PAGE-CPNC-2025-P0110",
            "pdf_page": 110,
            "printed_page": 88,
            "review_status": "VISUALLY_VERIFIED",
            "manufacturing_authority": False,
        }
    ],
    "total_matches": 1,
    "source_pdf_bytes_verified": False,
    "technical_use": "REFERENCE_ONLY_NOT_FABRICATION_AUTHORITY",
}


class MaestroRoutingTests(unittest.TestCase):
    def test_modular_asks_drawers_before_finishes(self):
        example = (Path(__file__).resolve().parent.parent /
                   "examples/modular-two-drawers-inset.json")
        data = json.loads(example.read_text(encoding="utf-8"))
        module = data["modules"][0]
        module["fronts"] = "pending"
        module["back"] = "pending"
        module["drawers"] = "pending"
        module["support"] = "pending"
        r = consult_maestro({"action": "modular", "module_spec": data})
        self.assertEqual(r["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual([q["field"] for q in r["questions"]], [
            "module_spec.modules.BASE.fronts",
            "module_spec.modules.BASE.back",
            "module_spec.modules.BASE.drawers",
        ])
        self.assertFalse(r["cutting_ready"])

    def test_modular_asks_pending_decorative_drawer_facade(self):
        example = (Path(__file__).resolve().parent.parent /
                   "examples/modular-two-drawers-inset.json")
        data = json.loads(example.read_text(encoding="utf-8"))
        data["modules"][0]["drawers"][0]["facade"] = "pending"
        r = consult_maestro({"action": "modular", "module_spec": data},
                            max_questions=2)
        self.assertEqual([q["field"] for q in r["questions"]], [
            "module_spec.modules.BASE.drawers.TOP.facade",
            "module_spec.modules.BASE.finish",
        ])
        self.assertIn("embutido", r["questions"][0]["question"])
        self.assertFalse(r["fabrication_ready"])
        self.assertFalse(r["drilling_ready"])

    def test_modular_real_drawers_not_incorrectly_marked_absent(self):
        example = (Path(__file__).resolve().parent.parent /
                   "examples/modular-two-drawers-inset.json")
        data = json.loads(example.read_text(encoding="utf-8"))
        r = consult_maestro({"action": "modular", "module_spec": data})
        self.assertEqual(r["modular"]["piece_count"], 17)
        self.assertFalse(any("no hay cajones" in b for b in r["blockers"]))

    def test_modular_site_measurements_still_take_priority(self):
        example = (Path(__file__).resolve().parent.parent /
                   "examples/modular-two-drawers-inset.json")
        data = json.loads(example.read_text(encoding="utf-8"))
        data["installation"] = "built_in"
        data["modules"][0]["drawers"] = "pending"
        r = consult_maestro({"action": "modular", "module_spec": data})
        self.assertEqual(r["status"], "NEEDS_SITE_MEASUREMENTS")
        self.assertEqual([q["field"] for q in r["questions"]], [
            "module_spec.site_width_mm.top",
            "module_spec.site_width_mm.middle",
            "module_spec.site_width_mm.bottom",
        ])

    def _modular_knowledge_example(self):
        src = (Path(__file__).resolve().parent.parent /
               "examples/modular-kitchen-door-fronts.json")
        return json.loads(src.read_text(encoding="utf-8"))

    def test_modular_with_explicit_knowledge_query(self):
        request = {
            "action": "modular",
            "module_spec": self._modular_knowledge_example(),
            "query": "bisagras",
        }
        with patch("carpinova_agent.maestro.load_bundle",
                   return_value={"verified": True}) as load:
            with patch("carpinova_agent.maestro.search_content",
                       return_value=FOUND) as search:
                response = consult_maestro(request, bundle_dir="/tmp/verified")
        load.assert_called_once_with("/tmp/verified")
        search.assert_called_once_with({"verified": True}, "bisagras")
        self.assertEqual(response["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(response["modular"]["piece_count"], 13)
        self.assertEqual(response["knowledge"]["coverage"], "FULL_BOOK")
        self.assertEqual(response["source_provenance"][0]["pdf_page"], 110)
        self.assertEqual(response["source_provenance"][0]["printed_page"], 88)
        self.assertFalse(response["source_provenance"][0]["fabrication_authority"])
        for key in ("fabrication_ready", "cutting_ready",
                    "drilling_ready", "purchase_ready"):
            self.assertFalse(response[key], key)
        self.assertTrue(any("referencia educativa" in text
                            for text in response["blockers"]))

    def test_modular_query_requires_verified_bundle(self):
        request = {"action": "modular",
                   "module_spec": self._modular_knowledge_example(),
                   "query": "bisagras"}
        with self.assertRaisesRegex(MaestroError, "bundle Knowledge"):
            consult_maestro(request)

    def test_modular_without_query_does_not_lookup_book(self):
        request = {"action": "modular",
                   "module_spec": self._modular_knowledge_example()}
        with patch("carpinova_agent.maestro.load_bundle") as load:
            response = consult_maestro(request, bundle_dir="/tmp/unused")
        load.assert_not_called()
        self.assertIsNone(response["knowledge"])
        self.assertEqual(response["source_provenance"], [])

    def test_modular_book_no_matches_stays_explicitly_uncertain(self):
        data = {**FOUND, "results": [], "total_matches": 0}
        request = {"action": "modular",
                   "module_spec": self._modular_knowledge_example(),
                   "query": "xxxxx"}
        with patch("carpinova_agent.maestro.load_bundle", return_value={}):
            with patch("carpinova_agent.maestro.search_content", return_value=data):
                response = consult_maestro(request, bundle_dir="/tmp/verified")
        self.assertEqual(response["source_provenance"], [])
        self.assertTrue(any("No se encontró" in x for x in response["blockers"]))
        self.assertFalse(response["cutting_ready"])

    def test_modular_partial_book_never_claims_full_coverage(self):
        request = {"action": "modular",
                   "module_spec": self._modular_knowledge_example(),
                   "query": "bisagras"}
        limited = {**FOUND, "coverage": "PARTIAL_CORPUS"}
        with patch("carpinova_agent.maestro.load_bundle", return_value={}):
            with patch("carpinova_agent.maestro.search_content", return_value=limited):
                response = consult_maestro(request, bundle_dir="/tmp/pilot")
        self.assertEqual(response["knowledge"]["coverage"], "PARTIAL_CORPUS")
        self.assertTrue(any("paquete parcial" in x for x in response["blockers"]))
        self.assertFalse(response["fabrication_ready"])

    def test_modular_topic_evidence_filters_unrelated_lexical_results(self):
        request = {
            "action": "modular",
            "module_spec": self._modular_knowledge_example(),
            "query": "fondo tuberias",
            "evidence_topic": "backs_and_services",
        }
        first = {
            "content_id": "CONTENT-FONDO", "page_id": "PAGE-134",
            "pdf_page": 134, "printed_page": 112,
            "review_status": "REVIEW_PENDING",
            "text": "Fondo posterior para paso de tuberías.",
            "tags": ["cocina"], "source_book": "cpnc-2025",
            "manufacturing_authority": False,
        }
        second = {**first, "content_id": "CONTENT-NOISE",
                  "pdf_page": 155, "printed_page": 133,
                  "text": "Solo habla de tuberías sin un fondo."}
        # The unrelated record deliberately lacks BOTH required topic families.
        second["text"] = "Solo habla del paso de tuberías."
        fetched = {**FOUND, "query": "fondo tuberias",
                   "results": [second, first], "total_matches": 21}
        with patch("carpinova_agent.maestro.load_bundle", return_value={}) as load:
            with patch("carpinova_agent.maestro.search_content",
                       return_value=fetched) as search:
                answer = consult_maestro(request,bundle_dir="/tmp/verified")
        load.assert_called_once()
        search.assert_called_once_with({}, "fondo tuberias", limit=20)
        self.assertEqual([x["content_id"] for x in answer["knowledge"]["results"]],
                         ["CONTENT-FONDO"])
        audit = answer["knowledge"]["relevance_review"]
        self.assertEqual(audit["candidate_count_in_sample"],1)
        self.assertEqual(audit["original_lexical_total_matches"],21)
        self.assertFalse(audit["technical_suitability_verified"])
        self.assertEqual([p["content_id"] for p in answer["source_provenance"]],
                         ["CONTENT-FONDO"])
        self.assertEqual(answer["source_provenance"][0]["pdf_page"],134)
        self.assertTrue(any("candidatas léxicas" in x
                            for x in answer["blockers"]))
        self.assertFalse(answer["cutting_ready"])

    def test_modular_topic_without_query_rejected(self):
        with self.assertRaisesRegex(MaestroError, "evidence_topic"):
            consult_maestro({
                "action":"modular",
                "module_spec":self._modular_knowledge_example(),
                "evidence_topic":"edge_banding",
            })

    def test_modular_topic_unknown_rejected(self):
        with self.assertRaisesRegex(MaestroError, "evidence_topic"):
            consult_maestro({
                "action":"modular",
                "module_spec":self._modular_knowledge_example(),
                "query":"canto", "evidence_topic":"unknown_topic",
            })

    def test_evidence_topic_not_accepted_in_knowledge_only(self):
        with self.assertRaises(MaestroError):
            consult_maestro({
                "action":"knowledge", "query":"canto",
                "evidence_topic":"edge_banding",
            })

    def test_modular_topic_no_context_stays_unverified(self):
        request = {
            "action":"modular",
            "module_spec":self._modular_knowledge_example(),
            "query":"tuberías",
            "evidence_topic":"backs_and_services",
        }
        unrelated = {
            "content_id":"CONTENT-PIPE", "page_id":"PAGE-100",
            "pdf_page":100,"printed_page":78,
            "review_status":"VISUALLY_VERIFIED",
            "text":"Tuberías de agua, sin información de carpintería.",
            "tags":[],"source_book":"cpnc-2025",
            "manufacturing_authority":False,
        }
        fetched={**FOUND, "results":[unrelated],"total_matches":1}
        with patch("carpinova_agent.maestro.load_bundle",return_value={}):
            with patch("carpinova_agent.maestro.search_content",return_value=fetched):
                answer=consult_maestro(request,bundle_dir="/tmp/verified")
        self.assertEqual(answer["knowledge"]["results"],[])
        self.assertEqual(answer["source_provenance"],[])
        self.assertEqual(answer["knowledge"]["relevance_review"]["status"],
                         "NO_CONTEXT_CANDIDATES_IN_SEARCH_SAMPLE")
        self.assertTrue(any("contexto completo" in x for x in answer["blockers"]))
        self.assertFalse(answer["fabrication_ready"])

    def test_project_missing_data(self):
        r = consult_maestro({
            "action": "project",
            "project": {"project_type": "gabinete", "width_mm": 600}
        })
        self.assertEqual(r["status"], "NEEDS_INPUT")
        self.assertIsNone(r["project"]["design"])
        self.assertFalse(r["cutting_ready"])
        self.assertLessEqual(len(r["questions"]), 3)

    def test_project_complete_stays_preliminary(self):
        r = consult_maestro({"action": "project", "project": CABINET})
        self.assertEqual(r["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(r["project"]["design"]["dimensions"]["clear_width_mm"], 564)
        self.assertFalse(r["fabrication_ready"])
        self.assertFalse(r["purchase_ready"])
        self.assertIsNone(r["hardware"])
        self.assertIsNone(r["knowledge"])

    def test_hardware_routes_same_exact_catalog(self):
        r = consult_maestro({"action": "hardware", "hardware": HARDWARE})
        self.assertEqual(r["status"], "BLOCKED_HARDWARE_SPEC")
        self.assertEqual(r["hardware"]["candidate_hinge_sku"], "71B3550")
        self.assertFalse(r["hardware"]["drilling_ready"])
        self.assertEqual(r["hardware"]["drilling_coordinates"], [])

    def test_hardware_unknown_manufacturer_rejected(self):
        with self.assertRaises(HardwareError):
            consult_maestro({"action": "hardware",
                            "hardware": {**HARDWARE, "manufacturer": "Fake"}})

    def test_combined_no_silent_book_lookup(self):
        req = {"action": "combined", "project": CABINET,
               "hardware": HARDWARE}
        r = consult_maestro(req)
        self.assertIsNone(r["knowledge"])
        self.assertEqual(r["hardware"]["candidate_hinge_sku"], "71B3550")
        self.assertEqual(r["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertFalse(r["drilling_ready"])

    def test_conflicting_front_blocked(self):
        with self.assertRaises(MaestroError):
            consult_maestro({
                "action": "combined",
                "project": {**CABINET, "front_style": "inset"},
                "hardware": HARDWARE,
            })

    def test_front_none_with_hinge_rejected(self):
        with self.assertRaises(MaestroError):
            consult_maestro({
                "action": "combined",
                "project": {**CABINET, "front_style": "none"},
                "hardware": HARDWARE,
            })

    def test_consistent_front_remains_draft(self):
        req = {"action": "combined", "project": {**CABINET, "front_style": "overlay"},
               "hardware": HARDWARE}
        r = consult_maestro(req)
        self.assertEqual(r["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertFalse(r["drilling_ready"])

    def test_book_query_requires_bundle(self):
        with self.assertRaises(MaestroError):
            consult_maestro({"action": "knowledge", "query": "bisagras"})

    def test_combined_query_requires_bundle(self):
        with self.assertRaises(MaestroError):
            consult_maestro({"action": "combined", "project": CABINET,
                             "query": "bisagras"})

    def test_knowledge_with_provenance(self):
        with patch("carpinova_agent.maestro.load_bundle", return_value={"x": 1}) as lb:
            with patch("carpinova_agent.maestro.search_content", return_value=FOUND):
                r = consult_maestro(
                    {"action": "knowledge", "query": "bisagras"}, bundle_dir="/tmp/test"
                )
        lb.assert_called_once()
        self.assertEqual(r["status"], "REFERENCE_ONLY")
        self.assertEqual(r["source_provenance"][0]["pdf_page"], 110)
        self.assertFalse(r["source_provenance"][0]["fabrication_authority"])
        self.assertFalse(r["fabrication_ready"])

    def test_partial_book_flagged(self):
        with patch("carpinova_agent.maestro.load_bundle", return_value={"x": 1}):
            with patch("carpinova_agent.maestro.search_content",
                       return_value={**FOUND, "coverage": "PARTIAL_CORPUS"}):
                r = consult_maestro({"action": "knowledge", "query": "bisagras"},
                                    bundle_dir="/tmp/test")
        self.assertTrue(any("parcial" in x.lower() for x in r["blockers"]))

    def test_book_no_matches_explained(self):
        empty = {**FOUND, "results": [], "total_matches": 0}
        with patch("carpinova_agent.maestro.load_bundle", return_value={"x": 1}):
            with patch("carpinova_agent.maestro.search_content", return_value=empty):
                r = consult_maestro({"action": "knowledge", "query": "zzz"},
                                    bundle_dir="/tmp/test")
        self.assertEqual(r["source_provenance"], [])
        self.assertTrue(any("no se encontró" in x.lower() for x in r["blockers"]))

    def test_complete_combo_all_three(self):
        req = {
            "action": "combined", "project": {**CABINET, "front_style": "overlay"},
            "query": "bisagras", "hardware": HARDWARE,
        }
        with patch("carpinova_agent.maestro.load_bundle", return_value={"x": 1}):
            with patch("carpinova_agent.maestro.search_content", return_value=FOUND):
                r = consult_maestro(req, bundle_dir="/tmp/test")
        self.assertEqual(r["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(r["project"]["design"]["dimensions"]["external_width_mm"], 600)
        self.assertEqual(r["hardware"]["candidate_hinge_sku"], "71B3550")
        self.assertEqual(r["source_provenance"][0]["printed_page"], 88)
        self.assertFalse(r["drilling_ready"])

    def test_invalid_action_rejected(self):
        with self.assertRaises(MaestroError):
            consult_maestro({"action": "fabricar", "project": CABINET})

    def test_unknown_top_level_fields_rejected(self):
        with self.assertRaises(MaestroError):
            consult_maestro({"action": "project", "project": CABINET,
                            "authorized_perforations": True})

    def test_incompatible_mode_data_rejected(self):
        with self.assertRaises(MaestroError):
            consult_maestro({"action": "project", "project": CABINET,
                            "hardware": HARDWARE})

    def test_all_actions_reject_non_structured(self):
        for payload in ("texto", [], None):
            with self.subTest(payload=payload), self.assertRaises(MaestroError):
                consult_maestro(payload)

    def test_empty_question_not_processed(self):
        with self.assertRaises(MaestroError):
            consult_maestro({"action": "knowledge", "query": ""})

    def test_non_object_hardware_rejected(self):
        with self.assertRaises(MaestroError):
            consult_maestro({"action": "hardware", "hardware": "Blum"})

    def test_no_source_asserted_for_geometry_only(self):
        r = consult_maestro({"action": "project", "project": CABINET})
        self.assertEqual(r["source_provenance"], [])
        self.assertIsNone(r["knowledge"])

    def test_invalid_geometry_never_released(self):
        r = consult_maestro({
            "action": "project", "project": {**CABINET, "width_mm": 35}
        })
        self.assertEqual(r["status"], "INVALID_GEOMETRY")
        self.assertIsNone(r["project"]["design"])
        self.assertFalse(r["cutting_ready"])


if __name__ == "__main__":
    unittest.main()
