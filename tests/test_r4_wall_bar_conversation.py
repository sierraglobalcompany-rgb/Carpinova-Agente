"""R4 synthetic QA for the P5-bound conversational wall-bar review."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from carpinova_agent.conversation_flow import (
    prepare_wall_bar_p5_nominal_review,
    revise_wall_bar_p5_nominal_review,
    validate_wall_bar_p5_nominal_review,
    preview_conversation,
)
from carpinova_agent.maestro import MaestroError
from carpinova_agent.wall_bar import design_wall_bar
from carpinova_agent.wall_bar_delivery import review_booklet_svgs
from tests.test_live02_wall_bar_flow import OWNER_FIRST, OWNER_CLARIFICATION
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
P5 = ROOT / "examples" / "wall-bar-900-review-p5.json"
OWNER_TEXT = OWNER_FIRST + "\n" + OWNER_CLARIFICATION
SYNTHETIC_A = "haz el cajón A 10 cm más alto"
SYNTHETIC_B = "B 5 cm más bajo"
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")


def prepare():
    return prepare_wall_bar_p5_nominal_review(OWNER_TEXT)


def drawers(review):
    return sorted(
        review["request"]["module_spec"]["cabinet_module"]["drawers"],
        key=lambda row: row["opening_bottom_offset_mm"], reverse=True,
    )


class R4WallBarConversationTests(unittest.TestCase):
    def test_base_binds_owner_measurements_to_p5_and_preserves_p5_geometry(self):
        review = prepare()
        fixture = json.loads(P5.read_text(encoding="utf-8"))
        self.assertEqual(review["request"], fixture)
        self.assertEqual(review["source_fixture"], "examples/wall-bar-900-review-p5.json")
        self.assertEqual(review["source_fixture_sha256"],
                         "b3beb2e93fe8651ba3a4022d3014aa0c3368fba73a253795639c0f48a4d61983")
        self.assertNotIn("query", review["request"])
        self.assertEqual(review["geometry_sha256"],
                         "5c0b8944ba015ef537688afac3ee58b9dd52011267c28278c9134a473cecf947")
        self.assertEqual(review["cad_element_count"], 28)
        self.assertEqual(len(review["cad_piece_ids"]), 28)
        self.assertEqual([row["drawer_id"] for row in review["openings_top_to_bottom"]],
                         ["D1", "D2", "D3"])
        self.assertEqual([row["opening_height_mm"] for row in review["openings_top_to_bottom"]],
                         [150, 150, 447])
        self.assertEqual(set(review["front_gaps_nominal_mm"].values()), {4})
        self.assertEqual(len(review["front_gaps_nominal_mm"]), 6)
        self.assertEqual(review["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(review["owner_visual_acceptance"], "PENDING")
        self.assertEqual(review["piece_count"], 0)
        self.assertIs(review["can_generate_f7c"], False)
        self.assertIs(review["layout_approved"], False)
        self.assertIs(review["construction_approved"], False)
        self.assertTrue(all(review[flag] is False for flag in FLAGS))
        self.assertEqual(review["owner_measurement_comparison"]["overall_height_mm"],
                         {"owner_value": 900, "p5_value": 900, "matches": True})
        self.assertTrue(review["standard_claim_unverified"])

    def test_synthetic_revisions_replay_cumulatively_and_keep_only_allowed_fields(self):
        base = prepare()
        after_a = revise_wall_bar_p5_nominal_review(base, SYNTHETIC_A)
        after_b = revise_wall_bar_p5_nominal_review(after_a, SYNTHETIC_B)
        self.assertEqual([r["opening_height_mm"] for r in after_a["openings_top_to_bottom"]],
                         [250, 125, 372])
        self.assertEqual([r["opening_height_mm"] for r in after_b["openings_top_to_bottom"]],
                         [250, 75, 422])
        self.assertEqual([r["drawer_id"] for r in after_b["openings_top_to_bottom"]],
                         ["D1", "D2", "D3"])
        self.assertEqual([r["opening_bottom_offset_mm"] for r in after_a["openings_top_to_bottom"]],
                         [563, 406, 2])
        self.assertEqual([r["opening_bottom_offset_mm"] for r in after_b["openings_top_to_bottom"]],
                         [563, 456, 2])
        self.assertEqual([d["box_height_mm"] for d in drawers(after_b)], [220, 45, 365])
        self.assertEqual([r["ref"] for r in after_b["correction_history"]], ["A", "B"])
        self.assertEqual([r["source"] for r in after_b["correction_history"]],
                         ["INPUT_DECLARED_NOT_AUTHENTICATED"] * 2)
        self.assertEqual(
            {row["ref"]: row["cause"] for row in after_a["correction_history"][0]["changes"]},
            {"A": "INPUT_REQUESTED_NOT_APPROVED",
             "B": "AUTO_REDISTRIBUTED_TO_KEEP_TOTAL",
             "C": "AUTO_REDISTRIBUTED_TO_KEEP_TOTAL"},
        )
        self.assertEqual(
            {row["ref"]: row["cause"] for row in after_b["correction_history"][1]["changes"]},
            {"B": "INPUT_REQUESTED_NOT_APPROVED",
             "C": "AUTO_REDISTRIBUTED_TO_KEEP_TOTAL"},
        )
        self.assertNotEqual(base["replay_sha256"], after_a["replay_sha256"])
        self.assertNotEqual(after_a["replay_sha256"], after_b["replay_sha256"])
        self.assertEqual(after_b["envelope_mm"], base["envelope_mm"])
        self.assertEqual(after_b["envelope_mm"], {
            "overall_width_mm": 900, "overall_depth_mm": 460,
            "overall_height_mm": 900, "free_span_mm": 600,
            "cabinet_width_mm": 300, "feet_height_mm": 40,
        })
        self.assertNotEqual(after_a["geometry_sha256"], base["geometry_sha256"])
        self.assertNotEqual(after_b["geometry_sha256"], after_a["geometry_sha256"])
        self.assertEqual(after_b["cad_piece_ids"], base["cad_piece_ids"])
        base_static = copy.deepcopy(base["request"]["module_spec"])
        revised_static = copy.deepcopy(after_b["request"]["module_spec"])
        base_drawer_rows = base_static["cabinet_module"].pop("drawers")
        revised_drawer_rows = revised_static["cabinet_module"].pop("drawers")
        self.assertEqual(revised_static, base_static)
        allowed = {"opening_height_mm", "opening_bottom_offset_mm", "box_height_mm"}
        original_by_id = {row["drawer_id"]: row for row in base_drawer_rows}
        for row in revised_drawer_rows:
            original = original_by_id[row["drawer_id"]]
            for key in original.keys() | row.keys():
                if original.get(key) != row.get(key):
                    self.assertIn(key, allowed)
        original_box_clearance = {
            row["drawer_id"]: row["opening_height_mm"] - row["box_height_mm"]
            for row in base_drawer_rows
        }
        self.assertEqual(
            {row["drawer_id"]: row["opening_height_mm"] - row["box_height_mm"]
             for row in revised_drawer_rows},
            original_box_clearance,
        )
        self.assertEqual(after_b["source_request"]["module_spec"]["design_choices"],
                         base["source_request"]["module_spec"]["design_choices"])
        self.assertEqual(after_b["source_provenance"]["owner_measurements"],
                         "INPUT_TEXT_NOT_AUTHENTICATED")
        self.assertEqual(set(after_b["front_gaps_nominal_mm"].values()), {4})
        for review in (after_a, after_b):
            self.assertEqual(review["status"], "NEEDS_USER_CONFIRMATION")
            self.assertEqual(review["owner_visual_acceptance"], "PENDING")
            self.assertEqual(review["piece_count"], 0)
            self.assertIs(review["can_generate_f7c"], False)
            self.assertTrue(all(review[flag] is False for flag in FLAGS))
        replayed = prepare_wall_bar_p5_nominal_review(OWNER_TEXT, [SYNTHETIC_A, SYNTHETIC_B])
        self.assertEqual(after_b, replayed)

    def test_rejects_unknown_ambiguous_infeasible_and_overfixed_corrections(self):
        base = prepare()
        with self.assertRaisesRegex(MaestroError, "referencia no existe"):
            revise_wall_bar_p5_nominal_review(base, "haz el cajón D 10 cm más alto")
        with self.assertRaisesRegex(MaestroError, "Corrección ambigua"):
            revise_wall_bar_p5_nominal_review(base, "A más alto")
        with self.assertRaisesRegex(MaestroError, "altura nominal suficiente"):
            revise_wall_bar_p5_nominal_review(base, "haz el cajón A 500 mm más alto")
        after_b = revise_wall_bar_p5_nominal_review(
            revise_wall_bar_p5_nominal_review(base, SYNTHETIC_A), SYNTHETIC_B,
        )
        with self.assertRaisesRegex(MaestroError, "No quedan cajones libres"):
            revise_wall_bar_p5_nominal_review(after_b, "haz el cajón C 10 mm más alto")

    def test_tampered_preview_history_or_approval_is_rejected_by_replay(self):
        base = prepare()
        after_a = revise_wall_bar_p5_nominal_review(base, SYNTHETIC_A)
        for field, change in (
            ("request", lambda value: value["module_spec"].update(overall_width_mm=901)),
            ("correction_history", lambda value: value[0].update(delta_mm=999)),
        ):
            altered = copy.deepcopy(after_a)
            change(altered[field])
            with self.subTest(field=field), self.assertRaisesRegex(MaestroError, "P5 editado"):
                validate_wall_bar_p5_nominal_review(altered)
        altered = copy.deepcopy(after_a)
        altered["layout_approved"] = True
        with self.assertRaises(MaestroError):
            validate_wall_bar_p5_nominal_review(altered)
        self.assertIs(validate_wall_bar_p5_nominal_review(after_a), True)

    def test_p5_boundary_rejects_historical_fixture_and_incompatible_owner_text(self):
        with patch("carpinova_agent.conversation_flow._WALL_BAR_P5_FIXTURE_PATH",
                   ROOT / "examples" / "wall-bar-900-review.json"):
            with self.assertRaisesRegex(MaestroError, "P5 protegido"):
                prepare()
        with self.assertRaisesRegex(MaestroError, "medidas ambiguas"):
            prepare_wall_bar_p5_nominal_review(
                OWNER_TEXT + "\nLa altura total es de 910 milímetros."
            )

    def test_p5_fixture_hash_survives_windows_crlf_checkout(self):
        payload = P5.read_bytes().replace(b"\r\n", b"\n")
        crlf_fixture = payload.replace(b"\n", b"\r\n")
        with tempfile.TemporaryDirectory(prefix="carpn-r5-p5-crlf-") as temp_dir:
            fixture_path = Path(temp_dir) / P5.name
            fixture_path.write_bytes(crlf_fixture)
            with patch("carpinova_agent.conversation_flow._WALL_BAR_P5_FIXTURE_PATH",
                       fixture_path):
                review = prepare()
        self.assertEqual(review["source_fixture_sha256"],
                         "b3beb2e93fe8651ba3a4022d3014aa0c3368fba73a253795639c0f48a4d61983")
        self.assertEqual(review["geometry_sha256"],
                         "5c0b8944ba015ef537688afac3ee58b9dd52011267c28278c9134a473cecf947")

    def test_existing_simple_drawer_preview_and_build_flow_review_are_not_used(self):
        simple = preview_conversation(
            "cajonera ancho 500 mm alto 800 mm profundidad 500 mm cuatro cajones",
            ["A 100 mm mas alto"],
        )
        self.assertIsInstance(simple.get("illustrative_drawer_layout_option"), dict)
        with patch("carpinova_agent.conversation_flow.build_flow_review",
                   side_effect=AssertionError("build_flow_review must not run")):
            review = prepare()
        self.assertEqual(review["status"], "NEEDS_USER_CONFIRMATION")

    def test_r3_handle_symbols_remain_on_booklet_page_five_for_each_revision(self):
        base = prepare()
        after_a = revise_wall_bar_p5_nominal_review(base, SYNTHETIC_A)
        after_b = revise_wall_bar_p5_nominal_review(after_a, SYNTHETIC_B)
        for review in (base, after_a, after_b):
            with self.subTest(geometry=review["geometry_sha256"]):
                draft = design_wall_bar(review["request"]["module_spec"])
                pages = review_booklet_svgs(draft)
                self.assertEqual(len(pages), 7)
                page_five = ElementTree.fromstring(pages[4])
                symbols = [node for node in page_five.iter()
                           if node.get("data-concept") == "handle-visual-only"]
                facade_ids = {part["piece_id"] for part in draft["parts"]
                              if part["role"] == "drawer_facade"}
                self.assertEqual(len(symbols), 3)
                self.assertEqual({node.get("data-source-piece-id")
                                  for node in symbols}, facade_ids)
                self.assertTrue(all(node.get("data-piece-id") is None
                                    for node in symbols))
                self.assertEqual(draft["status"], "DRAFT_NOT_FOR_CUTTING")
                for flag in FLAGS:
                    self.assertIs(draft[flag], False)


if __name__ == "__main__":
    unittest.main()
