"""Focused contract tests for the read-only P5 review envelope."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from carpinova_agent import mcp_bridge
from carpinova_agent.conversation_flow import (
    prepare_wall_bar_p5_nominal_review,
    validate_wall_bar_p5_nominal_review,
)
from carpinova_agent.maestro import MaestroError
from tests.test_r4_wall_bar_conversation import OWNER_TEXT

FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
P5 = Path(__file__).resolve().parents[1] / "examples" / "wall-bar-900-review-p5.json"
BASE_SHA = "5c0b8944ba015ef537688afac3ee58b9dd52011267c28278c9134a473cecf947"
A_SHA = "59e082db9296a3fa0ddeb35aee415c29cd8e8bafbf88475c579068ebc4a38e23"
AB_SHA = "5a4c478bdafa5efa866f642bb80505722ccbee85a12dd55ae66452eb7be80f00"
A = "A 100 mm mas alto"
B = "B 50 mm mas bajo"


def envelope(corrections: list[str] | None = None) -> dict[str, object]:
    return {
        "review_kind": "wall_bar_p5_nominal",
        "utterance": OWNER_TEXT,
        "corrections": [] if corrections is None else corrections,
    }


def consult(value: dict[str, object]) -> dict[str, object]:
    return mcp_bridge.carpinova_consultar(
        json.dumps(value, ensure_ascii=False),
    )


class R5McpConversationalReviewTests(unittest.TestCase):
    def test_read_only_envelope_replays_base_and_cumulative_synthetic_cases(self):
        with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": ""}, clear=False):
            with patch.object(mcp_bridge, "write_pilot_bundle",
                              side_effect=AssertionError("consult must not write")) as writer:
                base = consult(envelope())
                after_a = consult(envelope([A]))
                after_ab = consult(envelope([A, B]))
            writer.assert_not_called()

        self.assertEqual(base["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(base["geometry_sha256"], BASE_SHA)
        self.assertEqual(base["piece_count"], 0)
        self.assertIs(base["can_generate_f7c"], False)
        self.assertEqual(base["owner_visual_acceptance"], "PENDING")
        self.assertEqual(base["authorization"], "NOT_FABRICATION_APPROVAL")
        self.assertEqual(base["source_provenance"]["corrections"],
                         "DECLARED_TEXT_REPLAY_NOT_AUTHENTICATED")
        self.assertEqual(base["source_provenance"]["owner_measurements"],
                         "INPUT_TEXT_NOT_AUTHENTICATED")
        self.assertEqual([r["opening_height_mm"] for r in base["openings_top_to_bottom"]],
                         [150, 150, 447])
        self.assertEqual([r["opening_height_mm"] for r in after_a["openings_top_to_bottom"]],
                         [250, 125, 372])
        self.assertEqual(after_a["geometry_sha256"], A_SHA)
        self.assertEqual([r["opening_height_mm"] for r in after_ab["openings_top_to_bottom"]],
                         [250, 75, 422])
        self.assertEqual(after_ab["geometry_sha256"], AB_SHA)
        for result in (base, after_a, after_ab):
            self.assertTrue(all(result[field] is False for field in FLAGS))
            self.assertTrue(all(gap == 4
                                for gap in result["front_gaps_nominal_mm"].values()))

    def test_normal_maestro_action_keeps_existing_consultar_route(self):
        request = json.loads(P5.read_text(encoding="utf-8"))
        result = consult(request)
        self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(result["modular"]["dimensions_mm"],
                         {"width": 900, "height": 900, "depth": 460})
        self.assertTrue(all(result[field] is False for field in FLAGS))

    def test_invalid_discriminator_shapes_and_duplicate_keys_fail_before_engines(self):
        valid = envelope()
        invalid = []
        for key, value in (
            ("action", "modular"), ("query", "libro"),
            ("flow_review_json", "{}"), ("project", {}),
            ("approval", True), ("cutting_ready", True),
        ):
            extra = copy.deepcopy(valid)
            extra[key] = value
            invalid.append(extra)
        for changed in (
            {"review_kind": "unknown", "utterance": OWNER_TEXT, "corrections": []},
            {"review_kind": "wall_bar_p5_nominal", "utterance": OWNER_TEXT},
            {**valid, "corrections": "A 100 mm mas alto"},
            {**valid, "corrections": [True]},
            {**valid, "corrections": ["A 1 mm mas alto"] * 13},
            {**valid, "utterance": 900},
        ):
            invalid.append(changed)
        duplicate = (
            '{"review_kind":"wall_bar_p5_nominal",'
            '"review_kind":"wall_bar_p5_nominal",'
            '"utterance":"texto","corrections":[]}'
        )
        with patch.object(mcp_bridge, "prepare_wall_bar_p5_nominal_review") as preview, \
                patch.object(mcp_bridge, "consult_maestro") as maestro:
            for raw in invalid:
                with self.subTest(request=raw), self.assertRaises(MaestroError):
                    mcp_bridge.carpinova_consultar(json.dumps(raw, ensure_ascii=False))
            with self.assertRaises(MaestroError):
                mcp_bridge.carpinova_consultar(duplicate)
        preview.assert_not_called()
        maestro.assert_not_called()

    def test_invalid_corrections_and_tampered_preview_fail_closed(self):
        for correction in ("A mas alto", "D 10 mm mas alto", "A 500 mm mas alto"):
            with self.subTest(correction=correction), self.assertRaises(MaestroError):
                consult(envelope([correction]))
        with self.assertRaises(MaestroError):
            consult(envelope([A, B, "C 10 mm mas alto"]))
        preview = prepare_wall_bar_p5_nominal_review(OWNER_TEXT, [A])
        changed = copy.deepcopy(preview)
        changed["request"]["module_spec"]["overall_width_mm"] = 901
        with self.assertRaisesRegex(MaestroError, "editado"):
            validate_wall_bar_p5_nominal_review(changed)

    def test_preview_remains_read_only_without_output_root(self):
        with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": ""}, clear=False):
            state = mcp_bridge.carpinova_estado()
            with patch.object(mcp_bridge, "write_pilot_bundle",
                              side_effect=AssertionError("consult must not write")) as writer:
                preview = consult(envelope())
            writer.assert_not_called()
        self.assertIs(state["output_root_configured"], False)
        self.assertEqual(preview["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(preview["piece_count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
