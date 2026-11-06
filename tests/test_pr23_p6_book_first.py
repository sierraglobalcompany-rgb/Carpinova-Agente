"""P6 book-first constructive review from the existing CN-BAR-001 CAD."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from carpinova_agent.cad_exchange import cad_exchange
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.pilot_cli import pilot_review
from carpinova_agent.wall_bar_delivery import review_files
from carpinova_agent.wall_bar_sheets import edge_policy_rows


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "wall-bar-900-review-p5.json"
EXPECTED_GEOMETRY_SHA = "5c0b8944ba015ef537688afac3ee58b9dd52011267c28278c9134a473cecf947"
P6_JSON = "CN-BAR-001-P6-revision-constructiva.json"
P6_CRITERIA = "CN-BAR-001-P6-criterios.md"
BLOCKED_FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready",
)


class PR23P6BookFirstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.answer = consult_maestro(cls.request)
        cls.model = cls.answer["modular"]
        cls.cad = cad_exchange(cls.model)
        cls.edge_rows = edge_policy_rows(cls.model)
        cls.files = review_files(cls.model)
        cls.review = json.loads(cls.files[P6_JSON])

    def test_edge_review_observes_96_unique_physical_edges_without_claiming_joints(self):
        self.assertEqual(self.cad["geometry_sha256"], EXPECTED_GEOMETRY_SHA)
        self.assertEqual(len(self.cad["boxes"]), 28)
        self.assertEqual(len(self.edge_rows), 96)
        self.assertEqual(len({(row["piece_id"], row["face_edge"])
                              for row in self.edge_rows}), 96)
        self.assertEqual(len({row["piece_id"] for row in self.edge_rows}), 24)
        self.assertTrue(all(row["evidence_status"] == "CAD_OBSERVED"
                            and row["evidence_basis"] == "ROLE_AND_GEOMETRY"
                            and row["site_context"] == "SITE_UNKNOWN"
                            and row["physical_edge_model"] == "NOT_MODELED"
                            for row in self.edge_rows))
        self.assertFalse(any("SUPPORT-LEG" in row["piece_id"]
                             or any("SUPPORT-LEG" in neighbor
                                    for neighbor in row["neighbor_piece_ids"])
                             for row in self.edge_rows))
        counts = self.review["edge_review"]["edge_policy_counts"]
        self.assertEqual(counts, {
            "REVIEW_REQUIRED": 82,
            "RIGID_PVC_2MM_CANDIDATE": 14,
        })
        left_side = next(row for row in self.edge_rows
                         if row["piece_id"] == "CAJONERA_DERECHA-LEFT_SIDE"
                         and row["face_edge"] == "x_max")
        self.assertEqual(left_side["neighbor_piece_id"], "BAR-COVER-TOP")
        self.assertEqual(left_side["cad_contact"], "CAD_CONTACT_NOMINAL")
        cover_wall_edge = next(row for row in self.edge_rows
                               if row["piece_id"] == "BAR-COVER-TOP"
                               and row["face_edge"] == "x_min")
        self.assertIsNone(cover_wall_edge["neighbor_piece_id"])
        self.assertEqual(cover_wall_edge["cad_contact"],
                         "NO_CAD_CONTACT_NOMINAL")
        self.assertIn("no demuestra unión", self.review["edge_review"]["interpretation"])
        self.assertEqual(self.review["edge_review"]["nominal_contact_edge_count"], 47)
        self.assertTrue(all(row["neighbor_piece_ids"] == sorted(set(row["neighbor_piece_ids"]))
                            and row["neighbor_piece_id"] == (
                                row["neighbor_piece_ids"][0]
                                if len(row["neighbor_piece_ids"]) == 1 else None
                            )
                            for row in self.edge_rows))
        options = {item["policy"]: item for item in
                   self.review["edge_review"]["book_conditional_options"]}
        self.assertIn("bajo contacto", options[
            "FLEXIBLE_PVC_0_45MM_CANDIDATE"]["condition"])
        self.assertIn("completamente oculto", options[
            "NO_DECORATIVE_EDGE_CANDIDATE"]["condition"])

    def test_finished_targets_theoretical_substrates_and_invalid_raw_scenario(self):
        dimensions = self.review["finished_targets_vs_substrate"]
        self.assertEqual([
            (row["facade"], row["finished_outer_target_mm"],
             row["ideal_substrate_dimensions_mm"], row["ideal_substrate_status"])
            for row in dimensions["facades"]
        ], [
            ("A", [292, 178], [288, 174], "NOT_A_CUT_DIMENSION"),
            ("B", [292, 178], [288, 174], "NOT_A_CUT_DIMENSION"),
            ("C", [292, 473], [288, 469], "NOT_A_CUT_DIMENSION"),
        ])
        self.assertFalse(dimensions["finished_panel_edges_included"])
        self.assertEqual(dimensions["cover_E01_substrate"]["status"],
                         "NOT_COMPUTABLE")
        self.assertFalse(dimensions["cover_E01_substrate"][
            "raw_substrate_dimensions_emitted"])
        self.assertEqual(dimensions["cover_E01_substrate"]["dimensions"]["X"]["status"],
                         "NOT_COMPUTABLE")
        self.assertEqual(dimensions["cover_E01_substrate"]["dimensions"]["Z"]["status"],
                         "NOT_COMPUTABLE")
        negative = dimensions["invalid_raw_vs_finished_example"]
        self.assertEqual(negative["status"], "INVALID_RAW_VS_FINISHED")
        self.assertEqual(negative["raw_interpretation_front_sizes_mm"], {
            "D3": [296, 477], "D2": [296, 182], "D1": [296, 182],
        })
        self.assertEqual(negative["theoretical_interfront_gaps_mm"], {
            "D3_D2": 0, "D2_D1": 0,
        })
        self.assertFalse(negative["zero_gap_accepted"])
        self.assertFalse(negative["cut_dimensions_authorized"])

    def test_book_rail_options_are_filtered_by_cad_without_selecting_hardware(self):
        slides = self.review["slide_review"]
        derived = slides["cad_derived_dimensions"]
        self.assertEqual(derived["carcass_inner_opening_width_mm"], 270)
        self.assertEqual(derived["drawer_box_outer_width_mm"], 244)
        self.assertEqual(derived["drawer_left_clearance_mm"], 13)
        self.assertEqual(derived["drawer_right_clearance_mm"], 13)
        self.assertEqual(derived["drawer_box_interior_clear_width_mm"], 214)
        self.assertEqual(slides["book_example_344_interpretation"][
            "current_cad_drawer_box_outer_width_mm"], 244)
        self.assertEqual(slides["book_example_344_interpretation"][
            "current_cad_drawer_interior_clear_width_mm"], 214)
        self.assertIn("outer width", slides["book_example_344_interpretation"][
            "review_interpretation"])
        self.assertEqual(derived["cavity_front_to_back_mm"], 430)
        self.assertEqual(derived["drawer_box_nominal_depth_mm"], 400)
        self.assertEqual(derived["nominal_rear_margin_mm"], 30)
        self.assertEqual(derived["drawer_bottom_piece_id"],
                         "CAJONERA_DERECHA-D1-DRAWER_BOTTOM")
        self.assertEqual(derived["back_piece_id"], "CAJONERA_DERECHA-BACK_FULL")
        self.assertEqual([
            (row["allowance_each_side_mm"], row["total_pair_mm"],
             row["theoretical_box_outer_width_mm"])
            for row in slides["lateral_options_mm_each_side"]
        ], [(13, 26, 244), (14, 28, 242), (15, 30, 240)])
        self.assertEqual(slides["under_mount_option"]["book_deduction_total_per_pair_mm"], 15)
        self.assertFalse(slides["under_mount_option"]["applied_to_current_geometry"])
        length = slides["book_length_heuristic"]
        self.assertEqual(length["nominal_candidate_mm"], 450)
        self.assertEqual(slides["book_exception"],
                         "BOOK_HEURISTIC_REJECTED_BY_CAD_ENVELOPE")
        self.assertEqual(slides["length_nominal_candidate_mm"], 400)
        self.assertFalse(slides["length_fitment_verified"])
        self.assertFalse(slides["installation_verified"])
        self.assertEqual(slides["drilling_coordinates"], [])
        self.assertIn("CONTENT-CPNC-2025-P0114-001", slides["book_source_ids"])
        self.assertEqual(slides["family_status"], "PRELIMINARY_BOOK_BASED_NOT_SELECTED")
        self.assertIsNone(slides["sku_selected"])
        self.assertIsNone(slides["weight_capacity_for_drawer"])
        manufacturer = slides["manufacturer_reference"]
        self.assertEqual(manufacturer["variant"], "DZ3832-0040DO")
        self.assertEqual((manufacturer["slide_length_SL_mm"],
                          manufacturer["extension_travel_TR_mm"]), (400, 406))
        self.assertEqual(manufacturer["derived_slide_thickness_plus_adjustment_mm_each_side"],
                         [12.9, 13.2])
        self.assertFalse(manufacturer["compatibility_verified"])
        self.assertEqual(manufacturer["drilling_coordinates"], [])
        self.assertEqual(slides["source_frame_conflict"]["id"],
                         "SOURCE_FRAME_CONFLICT_37_32")
        self.assertEqual(slides["source_frame_conflict"]["drilling_coordinates"], [])

    def test_source_provenance_outputs_manifest_and_all_manufacturing_flags_stay_blocked(self):
        provenance = self.review["knowledge_provenance"]
        self.assertEqual(provenance["commit"],
                         "d350f3de1104977986f30498d212e018cbac5d29")
        self.assertEqual(provenance["reference_mode"], "REFERENCE_DOCUMENTAL_AUDITADA")
        self.assertFalse(provenance["runtime_query_performed"])
        sources = {item["content_id"]: item
                   for item in provenance["content_references"]}
        for source_id in (
            "CONTENT-CPNC-2025-P0113-003",
            "CONTENT-CPNC-2025-P0114-002",
            "CONTENT-CPNC-2025-P0114-004",
            "CONTENT-CPNC-2025-P0115-002",
            "CONTENT-CPNC-2025-P0116-002",
            "CONTENT-CPNC-2025-P0067-001",
            "CONTENT-CPNC-2025-P0114-005",
            "CONTENT-CPNC-2025-P0116-001",
            "CONTENT-CPNC-2025-P0177-004",
            "CONTENT-CPNC-2025-P0266-001",
            "CONTENT-CPNC-2025-P0267-001",
        ):
            self.assertEqual(sources[source_id]["extraction_status"],
                             "VISUALLY_VERIFIED")
        self.assertNotIn("source_transcription", self.files[P6_JSON])
        bundle = pilot_review(self.request)
        manifest = json.loads(bundle["manifest.json"])
        self.assertIn(P6_JSON, manifest["files"])
        self.assertIn(P6_CRITERIA, manifest["files"])
        self.assertEqual(set(bundle), set(manifest["files"]))
        self.assertEqual(self.review["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertFalse(self.review["hardware_included"])
        self.assertEqual(self.review["manufacturing_flags"],
                         {flag: False for flag in BLOCKED_FLAGS})
        for flag in BLOCKED_FLAGS:
            self.assertIs(self.review[flag], False)
        self.assertIn("Qué recomienda el libro", self.files[P6_CRITERIA])
        self.assertIn("Qué calcula el diseño", self.files[P6_CRITERIA])
        self.assertIn("Qué falta para instalar", self.files[P6_CRITERIA])
        self.assertIn("NOT_A_CUT_DIMENSION", self.files[P6_CRITERIA])
        self.assertIn("no se generan perforaciones", self.files[P6_CRITERIA])
        for source_id in (
            "CONTENT-CPNC-2025-P0113-003", "CONTENT-CPNC-2025-P0114-002",
            "CONTENT-CPNC-2025-P0115-002", "CONTENT-CPNC-2025-P0116-002",
            "CONTENT-CPNC-2025-P0266-001", "CONTENT-CPNC-2025-P0267-001",
        ):
            self.assertIn(source_id, self.files[P6_CRITERIA])


if __name__ == "__main__":
    unittest.main()
