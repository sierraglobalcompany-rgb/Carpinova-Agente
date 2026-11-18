from __future__ import annotations

import copy
import json
import unittest

from carpinova_agent.conversation_flow import prepare_guided_design_v1
from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.maestro import consult_maestro

FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
BASE_SPEC_JSON = r'''{"type":"modular_run","application":"kitchen","installation":"freestanding","width_mm":1000,"height_mm":800,"depth_mm":500,"modules":[{"module_id":"KITCHEN_LEFT","width_mm":500,"panel_thickness_mm":18,"material_id":"MELAMINA_18","construction":"top_bottom_full","support":"floor","back":"none","drawers":"none","fronts":{"style":"overlay","leaf_count":2,"material_id":"MELAMINA_18","thickness_mm":18,"hinge_sides":["left","right"],"left_reveal_mm":3,"right_reveal_mm":3,"top_reveal_mm":4,"bottom_reveal_mm":4,"center_gap_mm":4},"horizontal_divider":{"material_id":"MELAMINA_18","thickness_mm":18,"position_from_clear_bottom_mm":335,"depth_mm":500,"depth_from_front_mm":0}},{"module_id":"KITCHEN_RIGHT","width_mm":500,"panel_thickness_mm":18,"material_id":"MELAMINA_18","construction":"top_bottom_full","support":"floor","fronts":"none","back":"none","drawers":[{"drawer_id":"D1","opening_bottom_offset_mm":0,"opening_height_mm":236,"opening_depth_mm":500,"box_height_mm":216,"panel_thickness_mm":18,"bottom_thickness_mm":18,"slide_clearance_left_mm":0,"slide_clearance_right_mm":0,"front_setback_mm":0,"rear_setback_mm":0,"material_id":"MELAMINA_18","bottom_material_id":"MELAMINA_18","facade":{"style":"overlay","material_id":"MELAMINA_18","thickness_mm":18,"left_overlap_mm":1,"right_overlap_mm":1,"top_overlap_mm":1,"bottom_overlap_mm":1,"opening_system":"handle"},"front_construction":"separate"},{"drawer_id":"D2","opening_bottom_offset_mm":264,"opening_height_mm":236,"opening_depth_mm":500,"box_height_mm":216,"panel_thickness_mm":18,"bottom_thickness_mm":18,"slide_clearance_left_mm":0,"slide_clearance_right_mm":0,"front_setback_mm":0,"rear_setback_mm":0,"material_id":"MELAMINA_18","bottom_material_id":"MELAMINA_18","facade":{"style":"overlay","material_id":"MELAMINA_18","thickness_mm":18,"left_overlap_mm":1,"right_overlap_mm":1,"top_overlap_mm":1,"bottom_overlap_mm":1,"opening_system":"handle"},"front_construction":"separate"},{"drawer_id":"D3","opening_bottom_offset_mm":528,"opening_height_mm":236,"opening_depth_mm":500,"box_height_mm":216,"panel_thickness_mm":18,"bottom_thickness_mm":18,"slide_clearance_left_mm":0,"slide_clearance_right_mm":0,"front_setback_mm":0,"rear_setback_mm":0,"material_id":"MELAMINA_18","bottom_material_id":"MELAMINA_18","facade":{"style":"overlay","material_id":"MELAMINA_18","thickness_mm":18,"left_overlap_mm":1,"right_overlap_mm":1,"top_overlap_mm":1,"bottom_overlap_mm":1,"opening_system":"handle"},"front_construction":"separate"}],"drawer_layout_reference":{"type":"drawer_layout_proposal","width_mm":500,"height_mm":800,"depth_mm":500,"panel_thickness_mm":18,"construction":"top_bottom_full","vertical_gap_mm":28,"drawer_weights":[1,1,1]}}]}'''

FULL_UTTERANCE = (
    "Quiero un gabinete de cocina independiente de dos módulos iguales de ancho. "
    "La carcasa completa mide 1000 mm de ancho, 800 mm de alto y 500 mm de profundidad. "
    "Melamina de 18 mm, tapa y base entre laterales. Solo el módulo izquierdo lleva "
    "una repisa horizontal a 335 mm desde la base interior y dos puertas sobrepuestas. "
    "El módulo derecho lleva tres cajones con frentes sobrepuestos y manijas. Sin fondo "
    "trasero, sin mesón, directamente al piso y separado de la pared."
)


def mixed_spec() -> dict:
    return json.loads(BASE_SPEC_JSON)


def right_shelf_spec() -> dict:
    spec = mixed_spec()
    left, right = spec["modules"]
    right["horizontal_divider"] = left.pop("horizontal_divider")
    right["drawers"] = "none"
    right.pop("drawer_layout_reference", None)
    return spec


def right_shelf_utterance() -> str:
    return FULL_UTTERANCE.replace(
        "Solo el módulo izquierdo lleva una repisa horizontal a 335 mm desde la base interior y dos puertas sobrepuestas.",
        "Solo el módulo derecho lleva una repisa horizontal a 335 mm desde la base interior. El módulo izquierdo lleva dos puertas sobrepuestas.",
    ).replace(
        "El módulo derecho lleva tres cajones con frentes sobrepuestos y manijas.",
        "El módulo derecho no lleva cajones.",
    )


def right_shelf_with_drawers_utterance() -> str:
    old = (
        "Solo el módulo izquierdo lleva una repisa horizontal a 335 mm desde la base interior "
        "y dos puertas sobrepuestas."
    )
    new = (
        "Solo el módulo derecho lleva una repisa horizontal a 335 mm desde la base interior. "
        "El módulo izquierdo lleva dos puertas sobrepuestas."
    )
    assert FULL_UTTERANCE.count(old) == 1
    return FULL_UTTERANCE.replace(old, new)


def guided(utterance: str, spec: dict | None = None) -> dict:
    request = {
        "review_kind": "guided_design_v1",
        "utterance": utterance,
        "review_state": None,
        "review_updates": [],
        "photo_observations": None,
    }
    if spec is not None:
        request["nominal_detail_spec"] = copy.deepcopy(spec)
    return prepare_guided_design_v1(request)


def guided_turn(utterance: str, review_state: dict | None = None) -> dict:
    return prepare_guided_design_v1({
        "review_kind": "guided_design_v1",
        "utterance": utterance,
        "review_state": copy.deepcopy(review_state),
        "review_updates": [],
        "photo_observations": None,
    })


class MixedKitchenShelfScopeTests(unittest.TestCase):
    def assert_blocked(self, result: dict, expected_blocker: str) -> None:
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertIn(expected_blocker, result["nominal_draft_blockers"])
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_mixed_kitchen_captures_left_only_shelf_scope(self) -> None:
        spec = mixed_spec()
        result = guided(FULL_UTTERANCE, spec)
        decision = result["review_state"]["decisions"]["internal_layout"]
        self.assertEqual(decision["value"], {
            "elements": ["horizontal"],
            "module_count": 2,
            "modules_equal_width": True,
            "shelf_module_index": 0,
            "shelf_position_from_clear_bottom_mm": 335,
        })
        self.assertEqual(decision["status"], "confirmed")
        self.assertEqual(decision["source"], "OWNER_TEXT")
        self.assertEqual(result["nominal_draft_blockers"], [])
        self.assertEqual(result["nominal_draft_piece_count"], 29)
        self.assertEqual(result["nominal_draft_request"]["module_spec"], spec)
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_right_shelf_with_drawers_is_blocked(self) -> None:
        spec = mixed_spec()
        left, right = spec["modules"]
        right["horizontal_divider"] = copy.deepcopy(left.pop("horizontal_divider"))
        self.assert_blocked(
            guided(right_shelf_with_drawers_utterance(), spec),
            "internal_layout:divider_drawer_collision_unverified",
        )

    def test_right_shelf_without_drawers_is_accepted_by_module_position(self) -> None:
        result = guided(right_shelf_utterance(), right_shelf_spec())
        layout = result["review_state"]["decisions"]["internal_layout"]
        self.assertEqual(layout["value"]["shelf_module_index"], 1)
        self.assertEqual(layout["value"]["shelf_position_from_clear_bottom_mm"], 335)
        self.assertEqual(result["nominal_draft_blockers"], [])
        self.assertEqual(result["nominal_draft_piece_count"], 11)
        self.assertIsNotNone(result["nominal_draft_request"])
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_missing_left_shelf_in_structured_module_is_rejected(self) -> None:
        spec = mixed_spec()
        spec["modules"][0].pop("horizontal_divider")
        self.assert_blocked(
            guided(FULL_UTTERANCE, spec), "module_spec:scoped_horizontal_divider_missing"
        )

    def test_shelf_position_must_match_confirmed_text(self) -> None:
        spec = mixed_spec()
        utterance = FULL_UTTERANCE.replace("335 mm", "340 mm")
        self.assert_blocked(
            guided(utterance, spec), "module_spec:shelf_position_mismatch_owner"
        )

    def test_one_shelf_per_module_keeps_historical_all_modules_rule(self) -> None:
        utterance = FULL_UTTERANCE.replace(
            "Solo el módulo izquierdo lleva una repisa horizontal a 335 mm desde la base interior",
            "Una repisa por cada módulo a 335 mm desde la base interior",
        )
        result = guided(utterance, mixed_spec())
        layout = result["review_state"]["decisions"]["internal_layout"]["value"]
        self.assertEqual(layout["shelves_per_module"], 1)
        self.assertIn("module_spec:horizontal_divider_missing", result["nominal_draft_blockers"])
        self.assert_blocked(result, "module_spec:horizontal_divider_missing")

    def test_incomplete_mixed_kitchen_asks_before_nominal_request(self) -> None:
        result = guided(
            "Quiero una cocina de dos módulos, el izquierdo con puertas y repisa "
            "y el derecho con tres cajones."
        )
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(result["questions"])
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_k1_conversation_builds_mixed_modules_without_prebuilt_spec(self) -> None:
        first = guided_turn(FULL_UTTERANCE)
        self.assertIsNone(first["nominal_draft_request"])
        self.assertEqual(first["nominal_draft_piece_count"], 0)
        self.assertIs(first["can_generate_f7c"], False)
        self.assertTrue(all(first[flag] is False for flag in FLAGS))
        layout = first["review_state"]["decisions"].get("drawer_layout")
        self.assertIsNotNone(layout)
        self.assertEqual(layout["status"], "proposed")
        self.assertEqual(layout["source"], "ENGINE_CALCULATED")
        self.assertEqual(layout["value"]["drawer_module_index"], 1)
        self.assertEqual(layout["value"]["reference"]["drawer_weights"], [1, 1, 1])
        self.assertEqual(layout["value"]["reference"]["vertical_gap_mm"], 28)
        self.assertIn("drawer_layout", [item["field"] for item in first["questions"]])
        self.assertIn("3/3/4/4 mm", first["questions"][0]["question"])

        second = guided_turn(
            "Sí, confirmo las proporciones iguales, la franja geométrica de 28 mm "
            "y la caja ilustrativa pendiente de revisar con la corredera exacta. "
            "También confirmo las luces nominales de puertas propuestas.",
            first["review_state"],
        )
        spec = second["nominal_draft_request"]["module_spec"]
        self.assertEqual(spec, mixed_spec())
        self.assertNotIn("nominal_detail_spec", second["nominal_draft_request"])
        self.assertEqual([module["width_mm"] for module in spec["modules"]], [500, 500])
        self.assertEqual(spec["modules"][0]["fronts"]["leaf_count"], 2)
        self.assertEqual(spec["modules"][0]["horizontal_divider"][
            "position_from_clear_bottom_mm"], 335)
        self.assertEqual(len(spec["modules"][1]["drawers"]), 3)
        self.assertEqual(second["nominal_draft_piece_count"], 29)
        self.assertEqual(second["nominal_draft_blockers"], [])
        modular = consult_maestro(second["nominal_draft_request"])["modular"]
        exchange = validate_exchange(cad_exchange(modular))
        self.assertEqual(second["nominal_draft_geometry_sha256"],
                         "28845f0e3ec430af001eaec252625042ff13381e80a3a073caba81dc15f0edb6")
        self.assertEqual(exchange["geometry_sha256"],
                         second["nominal_draft_geometry_sha256"])
        piece_ids = [piece["piece_id"] for piece in exchange["boxes"]]
        self.assertEqual(len(piece_ids), 29)
        self.assertEqual(len(piece_ids), len(set(piece_ids)))
        self.assertTrue(all(second[flag] is False for flag in FLAGS))
        self.assertIs(second["can_generate_f7c"], False)

        changed_width = guided_turn(
            "La carcasa ahora tiene 1100 mm de ancho.", second["review_state"],
        )
        self.assertIsNone(changed_width["nominal_draft_request"])
        changed_layout = changed_width["review_state"]["decisions"]["drawer_layout"]
        self.assertEqual(changed_layout["status"], "proposed")
        self.assertEqual(changed_layout["value"]["reference"]["width_mm"], 550)
        self.assertIn("drawer_layout", [item["field"]
                                        for item in changed_width["questions"]])
        self.assertEqual(changed_width["nominal_draft_piece_count"], 0)
        self.assertTrue(all(changed_width[flag] is False for flag in FLAGS))

        changed_review = guided_turn(
            "Sí, confirmo las nuevas proporciones y la separación geométrica "
            "propuestas, luces de puertas y placeholders de caja solo ilustrativos.",
            changed_width["review_state"],
        )
        changed_spec = changed_review["nominal_draft_request"]["module_spec"]
        self.assertEqual(changed_spec["width_mm"], 1100)
        self.assertEqual([module["width_mm"] for module in changed_spec["modules"]],
                         [550, 550])
        self.assertNotEqual(changed_review["nominal_draft_geometry_sha256"],
                            second["nominal_draft_geometry_sha256"])
        self.assertTrue(all(changed_review[flag] is False for flag in FLAGS))

    def test_k1_blocks_unassigned_drawer_module_and_shelf_drawer_collision(self) -> None:
        unassigned = FULL_UTTERANCE.replace(
            "El módulo derecho lleva tres cajones",
            "También lleva tres cajones",
        )
        result = guided_turn(unassigned)
        self.assertIsNone(result["nominal_draft_request"])
        self.assertIn("drawers:explicit_module_assignment_required",
                      result["nominal_draft_blockers"])
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

        collision = FULL_UTTERANCE.replace(
            "Solo el módulo izquierdo lleva", "Solo el módulo derecho lleva",
        )
        result = guided_turn(collision)
        self.assertIsNone(result["nominal_draft_request"])
        self.assertIn("internal_layout:divider_drawer_collision_unverified",
                      result["nominal_draft_blockers"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

        cutting = guided_turn(FULL_UTTERANCE + " Déjalo listo para cortar.")
        self.assertIsNone(cutting["nominal_draft_request"])
        self.assertIn("authorization:fabrication_cutting_or_drilling_not_permitted",
                      cutting["nominal_draft_blockers"])
        self.assertEqual(cutting["nominal_draft_piece_count"], 0)
        self.assertTrue(all(cutting[flag] is False for flag in FLAGS))

        unequal_modules = FULL_UTTERANCE.replace(
            "dos módulos iguales de ancho", "dos módulos de ancho diferente",
        )
        result = guided_turn(unequal_modules)
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

if __name__ == "__main__":
    unittest.main()
