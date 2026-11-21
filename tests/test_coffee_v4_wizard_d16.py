"""D16: synthetic coffee wizard acceptance through the real query entrypoint."""
from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.mcp_bridge import carpinova_consultar


FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
BASE = (
    "Gabinete de café con carcasa exterior 890 mm de ancho, 770 mm de alto y "
    "600 mm de profundidad, melamina de 15 mm, "
    "laterales continuos, patas de {leg_mm} mm solo para este ensayo nominal, "
    "contra la pared. Mesón MDF RH de 940 x 650 mm, 30 mm de espesor; "
    "vuelo frontal 50 mm y vuelo posterior {rear_mm} mm. {doors} "
    "{drawer_text}; {shelf_text}; {back_text}. {support_text} "
    "{tie_text} {total_text}"
)
HAPPY = BASE.format(
    leg_mm=100,
    rear_mm=0,
    doors="Dos puertas sobrepuestas lado a lado con manijas visibles;",
    drawer_text="sin cajones",
    shelf_text="una repisa horizontal a 370 mm desde la base interior",
    back_text="sin fondo para este ensayo",
    support_text=(
        "El mesón descansa sobre la carcasa y las patas; la pared no soporta carga "
        "vertical del mesón y solo sirve para estabilidad anti-vuelco; el instalador "
        "revisará el anclaje anti-vuelco."
    ),
    tie_text=(
        "Tres correas verticales de canto: frontal superior, posterior superior y "
        "posterior inferior, altura 80 mm solo para ensayo nominal."
    ),
    total_text="",
)
TIES_NO_HEIGHT = (
    "Tres correas verticales de canto: frontal superior, posterior superior "
    "y posterior inferior."
)


class CoffeeV4WizardD16(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[dict] = []

    def ask(self, utterance: str, state: dict | None = None,
            photo: dict | None = None) -> dict:
        payload = {
            "review_kind": "guided_design_v1",
            "utterance": utterance,
            "review_state": state,
            "review_updates": [],
            "photo_observations": photo,
        }
        encoded = json.dumps(payload, ensure_ascii=False)
        response = carpinova_consultar(encoded)
        self.calls.append({"solicitud_json": payload, "response": response})
        self.assert_safe(response)
        self.assertLessEqual(len(response.get("questions", [])), 3)
        return response

    def assert_safe(self, response: dict) -> None:
        self.assertEqual(response.get("piece_count"), 0)
        self.assertIs(response.get("can_generate_f7c"), False)
        for flag in FLAGS:
            self.assertIs(response.get(flag), False, flag)

    def assert_no_nominal_geometry(self, response: dict) -> None:
        self.assertIsNone(response.get("nominal_draft_request"))
        self.assertEqual(response.get("nominal_draft_piece_count"), 0)
        self.assertEqual(response.get("piece_count"), 0)
        self.assertIs(response.get("can_generate_f7c"), False)

    def test_multiturn_entrypoint_reaches_maestro_f6_and_cad(self) -> None:
        first = self.ask(
            "Gabinete de café con carcasa exterior 890 mm de ancho, "
            "770 mm de alto y 600 mm de profundidad, "
            "melamina de 15 mm, laterales continuos, patas de 100 mm solo para "
            "este ensayo nominal, contra la pared."
        )
        second = self.ask(
            "Mesón MDF RH de 940 x 650 mm, 30 mm de espesor; vuelo frontal 50 mm.",
            first["review_state"],
        )
        partial_flight = second["review_state"]["decisions"]["countertop_overhang"]
        self.assertEqual(partial_flight["value"],
                         {"front_mm": 50, "rear_mm": None})
        self.assertEqual(partial_flight["status"], "pending")
        self.assert_no_nominal_geometry(second)
        third = self.ask(
            "Posterior 0 mm. Dos puertas sobrepuestas lado a lado con manijas "
            "visibles; sin cajones; una repisa horizontal a 370 mm desde la base "
            "interior; sin fondo para este ensayo. El mesón descansa sobre la "
            "carcasa y las patas; la pared no soporta carga vertical del mesón y "
            "solo sirve para estabilidad anti-vuelco; el instalador revisará el "
            "anclaje anti-vuelco.",
            second["review_state"],
        )
        fourth = self.ask(
            "Tres correas verticales de canto: frontal superior, posterior "
            "superior y posterior inferior, altura 80 mm solo para ensayo "
            "nominal. La pared no soporta carga vertical del mesón.",
            third["review_state"],
        )

        self.assertEqual(len(self.calls), 4)
        for previous, following in zip(self.calls, self.calls[1:]):
            self.assertEqual(following["solicitud_json"]["review_state"],
                             previous["response"]["review_state"])
        self.assertEqual(fourth["confirmed"]["countertop_overhang"],
                         {"front_mm": 50, "rear_mm": 0})
        final_question_fields = {item["field"] for item in fourth["questions"]}
        self.assertFalse({
            "dimensions_mm", "countertop", "countertop_overhang", "support",
            "countertop_support", "cabinet_bracing", "anti_tip_anchor", "back",
            "internal_layout", "drawers", "doors", "front_style", "opening_intent",
        } & final_question_fields)
        self.assertEqual(fourth["confirmed"]["cabinet_bracing"]["tie_height_mm"], 80)
        self.assertEqual(
            fourth["nominal_draft_blockers"], [],
            json.dumps(fourth["review_state"]["decisions"], ensure_ascii=False),
        )
        request = fourth["nominal_draft_request"]
        self.assertIsInstance(request, dict)
        self.assertEqual(request["action"], "modular")
        module_spec = request["module_spec"]
        module = module_spec["modules"][0]
        self.assertEqual(
            (module_spec["width_mm"], module_spec["height_mm"], module_spec["depth_mm"]),
            (890, 770, 600),
        )
        self.assertEqual(module["support_concept"]["support_height_mm"], 100)
        self.assertEqual(module["support_concept"]["overall_height_mm"], 900)
        self.assertEqual(module["countertop"]["front_overhang_mm"], 50)
        self.assertEqual(module["countertop"]["rear_overhang_mm"], 0)
        self.assertEqual(module["upper_support"], {
            "style": "coffee_three_upright_ties",
            "tie_height_mm": 80,
            "tie_height_status": "REVIEW_HEIGHT_HYPOTHESIS_ONLY",
        })
        self.assertEqual(module["back"], "none")
        self.assertEqual(module["drawers"], "none")
        warnings = fourth["nominal_draft_warnings"]
        self.assertNotIn("COUNTERTOP_OVERHANG_SPLIT_IS_PROPOSED_NOT_OWNER_APPROVED", warnings)
        self.assertIn("COUNTERTOP_SUPPORT_NOT_STRUCTURALLY_VERIFIED", warnings)
        self.assertIn("STRUCTURAL_ENGINEERING_UNVERIFIED", warnings)
        self.assertIn(
            "SUPPORT_CONCEPT_100MM_DOES_NOT_RESOLVE_HISTORICAL_40MM_LEG_REFERENCE",
            warnings,
        )
        self.assertTrue(all(fourth[flag] is False for flag in FLAGS))
        self.assertIs(fourth["can_generate_f7c"], False)
        self.assertEqual(fourth["piece_count"], 0)
        self.assertEqual(fourth["nominal_draft_piece_count"], 10)

        maestro = consult_maestro(request)
        f6 = maestro["modular"]
        cad = validate_exchange(cad_exchange(f6))
        roles = {part["role"] for part in f6["parts"]}
        expected_roles = {
            "left_side", "right_side", "bottom", "upper_front_tie",
            "upper_rear_tie", "lower_rear_tie", "countertop",
            "shelf_horizontal", "front_left", "front_right",
        }
        self.assertEqual(roles, expected_roles)
        self.assertEqual(f6["piece_count"], 10)
        self.assertEqual(len(cad["boxes"]), 10)
        self.assertEqual({box["role"] for box in cad["boxes"]}, expected_roles)
        self.assertNotIn("support_leg_concept", roles)
        self.assertEqual(f6["upper_support_review"]["structural_engineering"], "UNVERIFIED")
        self.assertEqual(f6["upper_support_review"]["countertop_wall_vertical_support"],
                         "EXCLUDED_BY_OWNER")
        self.assertEqual(f6["assembly_review"]["support_height_mm"], 100)
        self.assertEqual(f6["assembly_review"]["physical_support_parts"], "NOT_MODELED")
        self.assertEqual(f6["assembly_review"]["vertical_load_path"],
                         "CARCASS_TO_LEGS_TO_FLOOR_CONCEPT_ONLY")
        self.assertEqual(module["countertop"]["material_id"], "MDF_RH_30")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", cad["geometry_sha256"]))
        for flag in FLAGS:
            self.assertIs(maestro[flag], False)
            self.assertIs(f6[flag], False)
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready"):
            self.assertIs(cad[flag], False)
        self.assertIs(cad["hardware_included"], False)
        self.assertEqual(cad["manufacturing_holes"], [])

        part_by_role = {part["role"]: part for part in f6["parts"]}
        expected_origins = {
            "upper_front_tie": [40, 790, 50],
            "upper_rear_tie": [40, 790, 635],
            "lower_rear_tie": [40, 115, 635],
        }
        for role, origin in expected_origins.items():
            part = part_by_role[role]
            self.assertEqual(part["nominal_origin_xyz_mm"], origin)
            self.assertEqual(part["face_plane"], "XY")
            self.assertEqual(part["nominal_face_y_mm"], 80)
            self.assertEqual(part["thickness_mm"], 15)
        self.assertEqual(f6["modules"][0]["countertop_review"]["overhangs_mm"]["front"], 50)
        self.assertEqual(f6["modules"][0]["countertop_review"]["overhangs_mm"]["rear"], 0)

        evidence_dir = os.environ.get("CARPINOVA_D16_EVIDENCE_DIR")
        self.assertTrue(evidence_dir, "CARPINOVA_D16_EVIDENCE_DIR no está configurado")
        evidence_path = Path(evidence_dir) / "CAFE_V4_MCP_F6_CAD_E2E.json"
        evidence_path.write_text(json.dumps({
            "provenance": "SIMULATED_OWNER_TEST_INPUT",
            "mcp_entrypoint": "carpinova_agent.mcp_bridge.carpinova_consultar",
            "calls": self.calls,
            "nominal_draft_request": request,
            "maestro_response": maestro,
            "f6_modular": f6,
            "cad_exchange": cad,
            "geometry_sha256": {
                "guided": fourth["nominal_draft_geometry_sha256"],
                "cad": cad["geometry_sha256"],
            },
            "physical_flags": {flag: False for flag in FLAGS},
            "pending_owner_decisions": [
                "modelo y altura física de patas históricas de 40 mm",
                "verificación estructural de correas, uniones y soporte del mesón",
                "estabilidad y anclaje por instalador",
                "visual UAT del propietario",
            ],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_tie_height_can_be_supplied_in_a_later_turn(self) -> None:
        pending = self.ask(BASE.format(
            leg_mm=100, rear_mm=0,
            doors="Dos puertas sobrepuestas lado a lado con manijas visibles;",
            drawer_text="sin cajones",
            shelf_text="una repisa horizontal a 370 mm desde la base interior",
            back_text="sin fondo para este ensayo",
            support_text=(
                "El mesón descansa sobre la carcasa y las patas; la pared no soporta "
                "carga vertical del mesón y solo sirve para estabilidad anti-vuelco; "
                "el instalador revisará el anclaje anti-vuelco."
            ),
            tie_text=TIES_NO_HEIGHT,
            total_text="",
        ))
        self.assertEqual(pending["review_state"]["decisions"]["cabinet_bracing"]["status"],
                         "pending")
        self.assert_no_nominal_geometry(pending)
        completed = self.ask("La altura de las correas es 80 mm, solo para ensayo.",
                             pending["review_state"])
        self.assertEqual(completed["confirmed"]["cabinet_bracing"]["tie_height_mm"], 80)
        self.assertIsNotNone(completed["nominal_draft_request"])

    def test_overhang_merges_across_turns_and_rejects_mismatch(self) -> None:
        first = self.ask(HAPPY)
        self.assertEqual(first["confirmed"]["countertop_overhang"],
                         {"front_mm": 50, "rear_mm": 0})
        corrected = self.ask("Corrijo: vuelo posterior 5 mm.", first["review_state"])
        self.assert_no_nominal_geometry(corrected)
        self.assertTrue(any("countertop_overhang:front_rear_do_not_match_depth" in item
                            for item in corrected["nominal_draft_blockers"]))

    def test_three_mm_back_with_rear_ties_is_concept_only(self) -> None:
        text = HAPPY.replace("sin fondo para este ensayo", "fondo posterior de 3 mm")
        result = self.ask(text)
        self.assert_no_nominal_geometry(result)
        self.assertEqual(result["nominal_draft_scope"], "CONCEPT_ONLY")
        self.assertIn("BLOCKED_UNSUPPORTED_BACK_GEOMETRY",
                      result["nominal_draft_blockers"])
        self.assertIn("interferiría con las correas traseras",
                      result["nominal_draft_next_question"])

    def test_historical_40_mm_legs_do_not_satisfy_900_mm_total(self) -> None:
        text = BASE.format(
            leg_mm=40, rear_mm=0,
            doors="Dos puertas sobrepuestas lado a lado con manijas visibles;",
            drawer_text="sin cajones",
            shelf_text="una repisa horizontal a 370 mm desde la base interior",
            back_text="sin fondo para este ensayo",
            support_text=(
                "El mesón descansa sobre la carcasa y las patas; la pared no soporta "
                "carga vertical del mesón y solo sirve para estabilidad anti-vuelco; "
                "el instalador revisará el anclaje anti-vuelco."
            ),
            tie_text="Tres correas verticales frontal superior, posterior superior "
                     "y posterior inferior, altura 80 mm.",
            total_text="altura total 900 mm",
        )
        result = self.ask(text)
        self.assert_no_nominal_geometry(result)
        self.assertIn("countertop:declared_overall_height_conflicts_with_components",
                      result["nominal_draft_blockers"])

    def test_unconfirmed_photo_does_not_supply_dimensions(self) -> None:
        photo = {
            "visible_features": ["posibles puertas"],
            "ambiguous_or_occluded": [],
            "dimensions_from_user_only": {},
            "questions": [],
        }
        first = self.ask("Gabinete de café contra la pared.")
        self.assertIn("foto de referencia", first["next_step"])
        result = self.ask("Sigo con el mismo gabinete.", first["review_state"], photo)
        self.assert_no_nominal_geometry(result)
        observation = result["review_state"]["decisions"]["photo_observations"]
        self.assertEqual(observation["source"], "IMAGE_OBSERVED_UNCONFIRMED")
        self.assertEqual(observation["status"], "proposed")
        self.assertEqual(result["photo_input"]["status"], "IMAGE_OBSERVED_UNCONFIRMED")
        self.assertNotIn("dimensions_mm", result["confirmed"])

    def test_wall_vertical_load_is_rejected(self) -> None:
        text = HAPPY.replace(
            "la pared no soporta carga vertical del mesón y solo sirve para estabilidad anti-vuelco",
            "la pared soporta carga vertical del mesón",
        )
        result = self.ask(text)
        self.assert_no_nominal_geometry(result)
        support = result["review_state"]["decisions"]["countertop_support"]["value"]
        self.assertEqual(support["support_source"], "wall")
        self.assertIs(support["wall_vertical_support"], True)
        self.assertEqual(result["review_state"]["decisions"]["anti_tip_anchor"]["status"],
                         "pending")

    def test_ties_require_two_overlay_doors(self) -> None:
        text = HAPPY.replace(
            "Dos puertas sobrepuestas lado a lado con manijas visibles;",
            "Una puerta sobrepuesta con manija visible;",
        )
        result = self.ask(text)
        self.assert_no_nominal_geometry(result)
        self.assertIn("cabinet_bracing:requires_two_overlay_doors",
                      result["nominal_draft_blockers"])

    def test_missing_shelf_location_stays_pending_and_asks(self) -> None:
        result = self.ask(HAPPY.replace(
            "una repisa horizontal a 370 mm desde la base interior",
            "una repisa horizontal",
        ))
        self.assert_no_nominal_geometry(result)
        layout = result["review_state"]["decisions"]["internal_layout"]
        self.assertEqual(layout["status"], "pending")
        question = next(item for item in result["questions"]
                        if item["field"] == "internal_layout")
        self.assertIn("la posición central no se dará por aprobada", question["question"])

    def test_back_without_owner_decision_remains_pending(self) -> None:
        result = self.ask(HAPPY.replace("sin fondo para este ensayo", "fondo sin decidir"))
        self.assert_no_nominal_geometry(result)
        back = result["review_state"]["decisions"]["back"]
        self.assertEqual(back["value"], "pending")
        self.assertEqual(back["status"], "pending")

    def test_confirmed_layout_change_to_unpositioned_vertical_blocks_geometry(self) -> None:
        first = self.ask(HAPPY)
        self.assertIsNotNone(first["nominal_draft_request"])
        changed = self.ask(
            "Corrijo: ahora una división vertical sin posición indicada.",
            first["review_state"],
        )
        self.assert_no_nominal_geometry(changed)
        self.assertTrue(any("internal_layout:vertical_divider_position_required" in item
                            for item in changed["nominal_draft_blockers"]))
        self.assertEqual(changed["review_state"]["decisions"]["internal_layout"]["value"],
                         ["vertical"])


if __name__ == "__main__":
    unittest.main()
