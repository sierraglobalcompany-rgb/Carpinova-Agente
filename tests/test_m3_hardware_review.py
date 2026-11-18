from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from carpinova_agent import conversation_flow
from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.maestro import consult_maestro
from test_m2_mixed_kitchen import (
    FLAGS,
    FULL_UTTERANCE,
    guided,
    mixed_spec,
    right_shelf_spec,
    right_shelf_utterance,
    right_shelf_with_drawers_utterance,
)


class ScopedShelfAndHardwareReviewTests(unittest.TestCase):
    def test_right_shelf_with_drawers_blocks_before_modular_cad(self) -> None:
        spec = mixed_spec()
        left, right = spec["modules"]
        right["horizontal_divider"] = copy.deepcopy(left.pop("horizontal_divider"))
        with patch.object(conversation_flow, "consult_maestro") as maestro_call:
            result = guided(right_shelf_with_drawers_utterance(), spec)
        actions = [call.args[0].get("action") for call in maestro_call.call_args_list]
        self.assertNotIn("modular", actions)
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertEqual(result["piece_count"], 0)
        self.assertIn(
            "internal_layout:divider_drawer_collision_unverified",
            result["nominal_draft_blockers"],
        )
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_invalid_indexes_fail_closed_before_maestro(self) -> None:
        valid = guided(FULL_UTTERANCE, mixed_spec())
        baseline_decisions = valid["review_state"]["decisions"]
        for invalid_index in (True, -1, 2):
            with self.subTest(index=invalid_index):
                decisions = copy.deepcopy(baseline_decisions)
                decisions["internal_layout"]["value"]["shelf_module_index"] = invalid_index
                with patch.object(conversation_flow, "consult_maestro") as maestro_call:
                    result = conversation_flow._guided_multicomponent_handoff(
                        decisions,
                        mixed_spec(),
                        photo_attached=False,
                        utterance=FULL_UTTERANCE,
                    )
                maestro_call.assert_not_called()
                self.assertIn(
                    "internal_layout:scoped_shelf_module_index_invalid",
                    result["nominal_draft_blockers"],
                )
                self.assertIsNone(result["nominal_draft_request"])
                self.assertEqual(result["nominal_draft_piece_count"], 0)
                self.assertIs(result["can_generate_f7c"], False)
                self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_right_shelf_without_drawers_is_nominal_module_one(self) -> None:
        result = guided(right_shelf_utterance(), right_shelf_spec())
        value = result["review_state"]["decisions"]["internal_layout"]["value"]
        self.assertEqual(value["shelf_module_index"], 1)
        self.assertEqual(value["shelf_position_from_clear_bottom_mm"], 335)
        self.assertEqual(result["nominal_draft_blockers"], [])
        self.assertEqual(result["nominal_draft_piece_count"], 11)
        self.assertNotEqual(
            result["nominal_draft_geometry_sha256"],
            "28845f0e3ec430af001eaec252625042ff13381e80a3a073caba81dc15f0edb6",
        )
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))
        modules = result["nominal_draft_request"]["module_spec"]["modules"]
        self.assertEqual(modules[0]["fronts"]["leaf_count"], 2)
        self.assertIsNone(modules[0].get("horizontal_divider"))
        self.assertEqual(modules[1]["drawers"], "none")
        self.assertEqual(modules[1]["horizontal_divider"]["position_from_clear_bottom_mm"], 335)
        modular = consult_maestro({
            "action": "modular", "module_spec": result["nominal_draft_request"]["module_spec"],
        })["modular"]
        self.assertEqual(modular["piece_count"], 11)
        self.assertEqual(len({p["piece_id"] for p in modular["parts"]}), 11)
        left_parts = [p for p in modular["parts"] if p["module_id"] == modules[0]["module_id"]]
        right_parts = [p for p in modular["parts"] if p["module_id"] == modules[1]["module_id"]]
        self.assertEqual(len(left_parts), 6)
        self.assertEqual(len(right_parts), 5)
        self.assertEqual(sum(p["role"].startswith("front_") for p in left_parts), 2)
        self.assertEqual(sum(p["role"] == "shelf_horizontal" for p in right_parts), 1)
        self.assertFalse(any(p["role"].startswith("drawer_") for p in modular["parts"]))

    def test_hardware_review_is_consultative_and_matches_cad_ids(self) -> None:
        result = guided(FULL_UTTERANCE, mixed_spec())
        review = result["hardware_review"]
        self.assertEqual(review["status"], "REFERENCE_ONLY_NOT_SELECTED")
        self.assertIs(review["hardware_selected"], False)
        self.assertIs(review["drilling_ready"], False)
        self.assertIs(review["purchase_ready"], False)
        self.assertEqual(review["drilling_coordinates"], [])
        self.assertEqual(result["nominal_draft_piece_count"], 29)
        self.assertEqual(
            result["nominal_draft_geometry_sha256"],
            "28845f0e3ec430af001eaec252625042ff13381e80a3a073caba81dc15f0edb6",
        )
        self.assertIs(result["nominal_draft_opening_review"]["hardware_selected"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

        modules = result["nominal_draft_request"]["module_spec"]["modules"]
        modular = consult_maestro({
            "action": "modular",
            "module_spec": result["nominal_draft_request"]["module_spec"],
        })["modular"]
        cad = validate_exchange(cad_exchange(modular))
        cad_ids = {box["piece_id"] for box in cad["boxes"]}
        opening_ids = {
            entry["piece_id"] for entry in result["nominal_draft_opening_review"]["elements"]
        }
        hardware_ids = {entry["piece_id"] for entry in review["elements"]}
        self.assertEqual(len(review["elements"]), 5)
        self.assertEqual(hardware_ids, opening_ids)
        self.assertTrue(hardware_ids.issubset(cad_ids))
        self.assertEqual(cad["geometry_sha256"], result["nominal_draft_geometry_sha256"])

        doors = [entry for entry in review["elements"] if entry["element_type"] == "door"]
        drawers = [entry for entry in review["elements"] if entry["element_type"] == "drawer"]
        self.assertEqual(len(doors), 2)
        self.assertEqual(len(drawers), 3)
        for entry in doors:
            self.assertIs(entry["hardware_selected"], False)
            self.assertEqual(entry["f4_status"], "BLOCKED_HARDWARE_SPEC")
            self.assertEqual(entry["candidate_hinge_sku"], "71B3550")
            self.assertIsNone(entry["candidate_plate_sku"])
            self.assertTrue(entry["required_inputs"])
            self.assertTrue(entry["blockers"])
            self.assertTrue(entry["sources"])
            self.assertTrue(all(
                source["evidence"] == "HISTORICAL_MANUFACTURER_REFERENCE_NOT_COMPATIBILITY"
                for source in entry["sources"]
            ))
        for entry in drawers:
            self.assertIs(entry["hardware_selected"], False)
            self.assertIsNone(entry["slide_sku"])
            self.assertEqual(entry["slide_compatibility"], "NOT_VERIFIED")
            self.assertIn(
                "ZERO_MM_CLEARANCES_ARE_PLACEHOLDERS_NOT_INSTALLABLE",
                entry["blockers"],
            )
            self.assertTrue(entry["required_inputs"])
            self.assertEqual(entry["opening_system"], "handle")
        self.assertEqual(len(modules), 2)

    def test_handle_to_push_changes_intent_without_changing_geometry(self) -> None:
        handle = guided(FULL_UTTERANCE, mixed_spec())
        result = conversation_flow.prepare_guided_design_v1({
            "review_kind": "guided_design_v1",
            "utterance": "Prefiero push en vez de las manijas.",
            "review_state": handle["review_state"],
            "review_updates": [],
            "photo_observations": None,
            "nominal_detail_spec": mixed_spec(),
        })
        self.assertEqual(result["nominal_draft_blockers"], [])
        self.assertEqual(result["nominal_draft_piece_count"], 29)
        self.assertEqual(
            result["nominal_draft_geometry_sha256"],
            handle["nominal_draft_geometry_sha256"],
        )
        before = {e["piece_id"] for e in handle["nominal_draft_opening_review"]["elements"]}
        after = {e["piece_id"] for e in result["nominal_draft_opening_review"]["elements"]}
        self.assertEqual(before, after)
        self.assertEqual(
            {e["opening_system"] for e in result["hardware_review"]["elements"]},
            {"push_to_open"},
        )
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_unsupported_front_style_does_not_invent_hinge(self) -> None:
        opening = [{
            "module_id": "MODULE_X",
            "piece_id": "MODULE_X-FRONT_CUSTOM",
            "element_type": "door",
            "opening_system": "pending",
        }]
        parts = [{
            "module_id": "MODULE_X",
            "piece_id": "MODULE_X-FRONT_CUSTOM",
            "role": "front_custom",
            "thickness_mm": 18,
        }]
        modules = [{"module_id": "MODULE_X", "fronts": {"style": "custom"}}]
        with patch.object(conversation_flow, "consult_maestro") as maestro_call:
            review = conversation_flow._guided_hardware_review(opening, parts, modules)
        maestro_call.assert_not_called()
        self.assertEqual(len(review["elements"]), 1)
        entry = review["elements"][0]
        self.assertIsNone(entry["candidate_hinge_sku"])
        self.assertIsNone(entry["candidate_plate_sku"])
        self.assertTrue(entry["blockers"])
        self.assertIs(entry["hardware_selected"], False)

    def test_each_door_uses_its_own_module_front_style(self) -> None:
        opening = [
            {"module_id": "MODULE_OVERLAY", "piece_id": "MODULE_OVERLAY-F1",
             "element_type": "door", "opening_system": "handle"},
            {"module_id": "MODULE_INSET", "piece_id": "MODULE_INSET-F1",
             "element_type": "door", "opening_system": "pending"},
        ]
        parts = [
            {"module_id": "MODULE_OVERLAY", "piece_id": "MODULE_OVERLAY-F1",
             "role": "front_left", "thickness_mm": 18},
            {"module_id": "MODULE_INSET", "piece_id": "MODULE_INSET-F1",
             "role": "front_left", "thickness_mm": 18},
        ]
        modules = [
            {"module_id": "MODULE_OVERLAY", "fronts": {"style": "overlay"}},
            {"module_id": "MODULE_INSET", "fronts": {"style": "inset"}},
        ]
        review = conversation_flow._guided_hardware_review(opening, parts, modules)
        by_id = {entry["piece_id"]: entry for entry in review["elements"]}
        self.assertEqual(by_id["MODULE_OVERLAY-F1"]["candidate_hinge_sku"], "71B3550")
        self.assertEqual(by_id["MODULE_INSET-F1"]["candidate_hinge_sku"], "71B3750")
        for entry in by_id.values():
            self.assertIsNone(entry["candidate_plate_sku"])
            self.assertIs(entry["hardware_selected"], False)
            self.assertTrue(all(
                source["evidence"] == "HISTORICAL_MANUFACTURER_REFERENCE_NOT_COMPATIBILITY"
                for source in entry["sources"]
            ))

    def test_manufacturing_request_stays_blocked_and_has_no_hardware_review(self) -> None:
        result = guided(
            FULL_UTTERANCE + " Déjalo listo para fabricar, cortar, perforar y comprar.",
            mixed_spec(),
        )
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertNotIn("hardware_review", result)
        self.assertIn(
            "authorization:fabrication_cutting_or_drilling_not_permitted",
            result["nominal_draft_blockers"],
        )
        self.assertTrue(all(result[flag] is False for flag in FLAGS))


if __name__ == "__main__":
    unittest.main()
