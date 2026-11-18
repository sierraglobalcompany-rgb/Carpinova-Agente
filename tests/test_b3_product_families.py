from __future__ import annotations

import copy
import inspect
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.mcp_bridge import (
    carpinova_consultar, carpinova_estado, carpinova_exportar_3d,
    carpinova_generar_borrador, carpinova_leer_entregable,
    carpinova_renderizar_lamina,
)
from carpinova_agent.pilot_cli import PilotError, pilot_review, verify_pilot_bundle
from carpinova_agent.conversation_flow import prepare_guided_design_v1
from carpinova_agent import conversation_flow
from test_m2_mixed_kitchen import FULL_UTTERANCE, guided, mixed_spec
from test_guided_design_mcp import closet_two_module_spec

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
G1_SHA = "28845f0e3ec430af001eaec252625042ff13381e80a3a073caba81dc15f0edb6"


def opening_review(review: dict, *, intent: str | None = None) -> str:
    source = review["nominal_draft_opening_review"]
    return json.dumps({
        "schema_version": "1.0",
        "source": "CLIENT_DECLARED_NOT_AUTHENTICATED",
        "geometry_sha256": review["nominal_draft_geometry_sha256"],
        "elements": [{
            key: element[key]
            for key in ("piece_id", "module_id", "element_type")
        } | {"opening_system": intent or element["opening_system"]}
            for element in source["elements"]
        ],
    }, ensure_ascii=False)


def tower_spec() -> dict:
    return {
        "type": "modular_run", "application": "kitchen",
        "width_mm": 600, "height_mm": 2100, "depth_mm": 600,
        "installation": "freestanding",
        "modules": [{
            "module_id": "TORRE_1", "width_mm": 600,
            "panel_thickness_mm": 18, "material_id": "MELAMINA_18",
            "construction": "sides_full", "support": "floor", "back": "none",
            "drawers": "none",
            "fronts": {
                "style": "overlay", "leaf_count": 2,
                "material_id": "MELAMINA_18", "thickness_mm": 18,
                "hinge_sides": ["left", "right"],
                "left_reveal_mm": 3, "right_reveal_mm": 3,
                "top_reveal_mm": 4, "bottom_reveal_mm": 4,
                "center_gap_mm": 4,
            },
            "horizontal_divider": {
                "material_id": "MELAMINA_18", "thickness_mm": 18,
                "position_from_clear_bottom_mm": 1050,
                "depth_mm": 600, "depth_from_front_mm": 0,
            },
        }],
    }


def tower_text(*, reserve: bool) -> str:
    reserve_text = (
        " Reserva conceptual para horno empotrado, sin modelo ni ficha todavía."
        if reserve else ""
    )
    return (
        "Gabinete alto tipo torre de cocina independiente, carcasa de 600 mm de ancho, 2100 mm de alto "
        "y 600 mm de profundidad, melamina de 18 mm, laterales continuos, una repisa "
        "horizontal a 1050 mm desde la base interior, dos puertas sobrepuestas, "
        "sin cajones, sin fondo, sin mesón y directamente al piso."
        + reserve_text
    )


def closet_text(*, sliding: bool = False,
                site_widths: tuple[int, int, int] | None = (2035, 2024, 2012)) -> str:
    doors = "cuatro puertas corredizas" if sliding else "cuatro puertas sobrepuestas"
    site_text = (
        f" Vano medido arriba {site_widths[0]} mm, al medio {site_widths[1]} mm "
        f"y abajo {site_widths[2]} mm."
        if site_widths is not None else ""
    )
    return (
        "Clóset empotrado contra la pared, carcasa de 1800 mm de ancho, 2100 mm de "
        "alto y 550 mm de profundidad, melamina de 18 mm, laterales continuos, "
        "dos módulos iguales, " + doors + ", una repisa horizontal en cada módulo, "
        "sin fondo, sin cajones, sin mesón y directamente al piso."
        + site_text
    )


def guided_session_turn(
    utterance: str, review_state: dict | None = None,
    review_updates: list[dict] | None = None,
) -> dict:
    """Call the real guided entrypoint with caller-carried conversation state."""
    return prepare_guided_design_v1({
        "review_kind": "guided_design_v1",
        "utterance": utterance,
        "review_state": review_state,
        "review_updates": review_updates or [],
        "photo_observations": None,
    })


class B3OpeningIntentTests(unittest.TestCase):
    def test_existing_six_tool_entrypoints_and_optional_parameter_are_preserved(self):
        tools = (
            carpinova_estado, carpinova_consultar, carpinova_generar_borrador,
            carpinova_renderizar_lamina, carpinova_exportar_3d,
            carpinova_leer_entregable,
        )
        self.assertEqual(len({tool.__name__ for tool in tools}), 6)
        parameter = inspect.signature(carpinova_generar_borrador).parameters[
            "opening_review_json"
        ]
        self.assertEqual(parameter.default, "")

    def test_consulted_opening_intents_survive_same_cad_and_readback(self):
        review = guided(FULL_UTTERANCE, mixed_spec())
        self.assertEqual(review["nominal_draft_piece_count"], 29)
        self.assertEqual(review["nominal_draft_geometry_sha256"], G1_SHA)
        sidecar = opening_review(review, intent="push_to_open")
        with TemporaryDirectory() as root:
            original = pilot_review({"action": "modular", "module_spec": mixed_spec()})
            with __import__("unittest.mock").mock.patch.dict(os.environ, {
                "CARPINOVA_OUTPUT_ROOT": root,
            }):
                legacy = carpinova_generar_borrador(
                    json.dumps({"action": "modular", "module_spec": mixed_spec()}),
                    "legacy",
                )
                self.assertEqual(legacy["files"], list(original))
                for name, content in original.items():
                    self.assertEqual((Path(root) / "legacy" / name).read_bytes(),
                                     content.encode("utf-8"))
                generated = carpinova_generar_borrador(
                    json.dumps({"action": "modular", "module_spec": mixed_spec()}),
                    "intent", opening_review_json=sidecar,
                )
                self.assertEqual(generated["geometry_sha256"], G1_SHA)
                self.assertEqual(generated["piece_count"], 29)
                delivered = carpinova_leer_entregable(
                    "intent", "opening-intents-review.json")
                saved = json.loads(delivered["contenido"])
                self.assertEqual(saved["status"], "NOT_APPROVED_NOT_FOR_FABRICATION")
                self.assertEqual(saved["geometry_sha256"], G1_SHA)
                self.assertEqual(len(saved["elements"]), 5)
                self.assertEqual({item["opening_system"] for item in saved["elements"]},
                                 {"push_to_open"})
                self.assertEqual({(item["piece_id"], item["module_id"], item["element_type"])
                                  for item in saved["elements"]},
                                 {(item["piece_id"], item["module_id"], item["element_type"])
                                  for item in review["nominal_draft_opening_review"]["elements"]})
                manifest = json.loads((Path(root) / "intent" / "manifest.json").read_text())
                self.assertIn("opening-intents-review.json", manifest["files"])
                self.assertRegex(manifest["opening_intents_review_sha256"], r"^[0-9a-f]{64}$")
                cad = verify_pilot_bundle(Path(root) / "intent")
                self.assertEqual(cad["geometry_sha256"], G1_SHA)
                for flag in FLAGS:
                    self.assertIs(generated[flag], False)
                    self.assertIs(manifest[flag], False)

    def test_intent_change_preserves_geometry_and_sidecar_tampering_is_rejected(self):
        request = {"action": "modular", "module_spec": mixed_spec()}
        review = guided(FULL_UTTERANCE, mixed_spec())
        handle = opening_review(review, intent="handle")
        push = opening_review(review, intent="push_to_open")
        self.assertEqual(json.loads(handle)["geometry_sha256"],
                         json.loads(push)["geometry_sha256"])
        with TemporaryDirectory() as root:
            from unittest.mock import patch
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                first = carpinova_generar_borrador(
                    json.dumps(request), "handle", opening_review_json=handle)
                second = carpinova_generar_borrador(
                    json.dumps(request), "push", opening_review_json=push)
            self.assertEqual(first["geometry_sha256"], second["geometry_sha256"])
            sidecar_path = Path(root) / "push" / "opening-intents-review.json"
            sidecar_path.write_text(sidecar_path.read_text(encoding="utf-8").replace(
                "push_to_open", "handle"), encoding="utf-8")
            with self.assertRaises(PilotError):
                verify_pilot_bundle(Path(root) / "push")

    def test_invalid_opening_review_is_rejected_atomically(self):
        review = guided(FULL_UTTERANCE, mixed_spec())
        valid = json.loads(opening_review(review, intent="pending"))
        mutations = []
        wrong_sha = copy.deepcopy(valid); wrong_sha["geometry_sha256"] = "0" * 64
        mutations.append(wrong_sha)
        fake_id = copy.deepcopy(valid); fake_id["elements"][0]["piece_id"] = "FAKE-ID"
        mutations.append(fake_id)
        partial = copy.deepcopy(valid); partial["elements"].pop()
        mutations.append(partial)
        duplicate = copy.deepcopy(valid); duplicate["elements"].append(copy.deepcopy(duplicate["elements"][0]))
        mutations.append(duplicate)
        extra_approval = copy.deepcopy(valid); extra_approval["purchase_ready"] = True
        mutations.append(extra_approval)
        wrong_type = copy.deepcopy(valid); wrong_type["elements"][0]["element_type"] = "window"
        mutations.append(wrong_type)
        disallowed = copy.deepcopy(valid); disallowed["elements"][0]["opening_system"] = "imaginary"
        mutations.append(disallowed)
        with TemporaryDirectory() as root:
            from unittest.mock import patch
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": root}):
                for index, item in enumerate(mutations):
                    with self.subTest(index=index), self.assertRaises((PilotError, ValueError)):
                        carpinova_generar_borrador(
                            json.dumps({"action": "modular", "module_spec": mixed_spec()}),
                            "bad" + str(index), opening_review_json=json.dumps(item),
                        )
                    self.assertFalse((Path(root) / ("bad" + str(index))).exists())
                with self.assertRaises((PilotError, ValueError)):
                    carpinova_generar_borrador(
                        json.dumps({"action": "modular", "module_spec": mixed_spec()}),
                        "duplicate_key", opening_review_json='{"schema_version":"1.0","schema_version":"1.0"}',
                    )
                self.assertFalse((Path(root) / "duplicate_key").exists())
                with self.assertRaises(PilotError):
                    carpinova_generar_borrador(
                        json.dumps({"action": "modular", "module_spec": mixed_spec()}),
                        "nonfinite", opening_review_json=(
                            '{"schema_version":"1.0","source":"CLIENT_DECLARED_NOT_AUTHENTICATED",'
                            '"geometry_sha256":"' + valid["geometry_sha256"] + '","elements":[{"piece_id":"A",'
                            '"module_id":"A","element_type":"door","opening_system":NaN}]}'
                        ),
                    )
                self.assertFalse((Path(root) / "nonfinite").exists())


class B3ProductFamilyTests(unittest.TestCase):
    def test_kitchen_tower_without_reserve_yields_nominal_review(self):
        result = guided(tower_text(reserve=False), tower_spec())
        self.assertEqual(result["nominal_draft_blockers"], [])
        self.assertEqual(result["nominal_draft_piece_count"], 7)
        self.assertIsNotNone(result["nominal_draft_request"])
        self.assertTrue(all(result[flag] is False for flag in FLAGS))
        model = consult_maestro({
            "action": "modular", "module_spec": result["nominal_draft_request"]["module_spec"],
        })["modular"]
        self.assertEqual(model["piece_count"], 7)
        self.assertEqual(len(model["modules"]), 1)
        self.assertTrue(all(result[key] is False for key in FLAGS))

    def test_negated_appliance_reserve_does_not_block_regular_tower(self):
        result = guided(
            tower_text(reserve=False) + " No quiero espacio para horno empotrado.",
            tower_spec(),
        )
        self.assertNotIn("appliance_reserve_review", result)
        self.assertEqual(result["nominal_draft_blockers"], [])
        self.assertIsNotNone(result["nominal_draft_request"])
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_kitchen_tower_appliance_reserve_stays_concept_and_persists(self):
        with patch.object(conversation_flow, "consult_maestro") as maestro_call:
            first = guided(tower_text(reserve=True), tower_spec())
        self.assertEqual(maestro_call.call_count, 0)
        self.assertEqual(first["nominal_draft_scope"], "CONCEPT_ONLY")
        self.assertIsNone(first["nominal_draft_request"])
        self.assertEqual(first["nominal_draft_piece_count"], 0)
        self.assertIn("appliance_reserve:integrated_appliance_concept_only",
                      first["nominal_draft_blockers"])
        reserve = first["appliance_reserve_review"]
        self.assertEqual(reserve["status"], "CONCEPT_ONLY")
        self.assertEqual(reserve["appliances"], ["oven"])
        self.assertFalse(reserve["geometry_included"])
        self.assertTrue(reserve["missing_inputs"])
        self.assertTrue(any("modelo" in q["question"].lower()
                            for q in first["questions"]))
        second = prepare_guided_design_v1({
            "review_kind": "guided_design_v1",
            "utterance": "Aún no tengo la ficha del horno.",
            "review_state": first["review_state"], "review_updates": [],
            "photo_observations": None,
        })
        self.assertEqual(second["appliance_reserve_review"]["appliances"], ["oven"])
        self.assertEqual(second["nominal_draft_scope"], "CONCEPT_ONLY")
        self.assertEqual(second["nominal_draft_piece_count"], 0)
        self.assertTrue(all(second[flag] is False for flag in FLAGS))

    def test_builtin_closet_uses_three_site_measurements_from_maestro(self):
        spec = closet_two_module_spec(installation="built_in")
        spec["site_width_mm"] = {"top": 2035, "middle": 2024, "bottom": 2012}
        result = guided(closet_text(), spec)
        self.assertEqual(result["nominal_draft_blockers"], [])
        self.assertEqual(result["nominal_draft_piece_count"], 14)
        model = consult_maestro({"action": "modular", "module_spec": spec})["modular"]
        exchange = validate_exchange(cad_exchange(model))
        self.assertEqual(result["nominal_draft_geometry_sha256"],
                         exchange["geometry_sha256"])
        owner_site = result["review_state"]["decisions"]["site_width_mm"]
        self.assertEqual(owner_site["source"], "OWNER_TEXT")
        self.assertEqual(owner_site["value"], spec["site_width_mm"])
        self.assertEqual(model["site"]["values_mm"], spec["site_width_mm"])
        self.assertEqual(model["site"]["nominal_gap_at_narrowest_mm"], 212)
        self.assertEqual(len(model["modules"]), 2)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_builtin_closet_detail_measurements_must_match_owner_text(self):
        spec = closet_two_module_spec(installation="built_in")
        spec["site_width_mm"] = {"top": 2035, "middle": 2024, "bottom": 2012}
        result = guided(closet_text(site_widths=(2036, 2024, 2012)), spec)
        self.assertIsNone(result["nominal_draft_request"])
        self.assertIn("module_spec:site_measurements_mismatch_owner",
                      result["nominal_draft_blockers"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_builtin_closet_van_conflict_blocks_nominal_geometry(self):
        spec = closet_two_module_spec(installation="built_in")
        spec["site_width_mm"] = {"top": 1800, "middle": 1800, "bottom": 1800}
        result = guided(closet_text(site_widths=(1800, 1800, 1800)), spec)
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertEqual(result["nominal_draft_engine_status"], "SITE_CONFLICT")
        self.assertIn("nuevo ancho de vano", result["nominal_draft_next_question"])
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_builtin_closet_missing_measurements_asks_before_geometry(self):
        result = guided(
            closet_text(site_widths=None),
            closet_two_module_spec(installation="built_in"),
        )
        self.assertEqual(result["nominal_draft_engine_status"], "NEEDS_SITE_MEASUREMENTS")
        self.assertEqual(result["nominal_draft_blockers"], [
            "modular:NEEDS_SITE_MEASUREMENTS",
        ])
        self.assertIn("arriba, al medio y abajo",
                      result["nominal_draft_next_question"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_sliding_closet_doors_are_concept_only_not_swing_geometry(self):
        spec = closet_two_module_spec(installation="built_in")
        spec["site_width_mm"] = {"top": 2035, "middle": 2024, "bottom": 2012}
        with patch.object(conversation_flow, "consult_maestro",
                          wraps=conversation_flow.consult_maestro) as maestro_call:
            result = guided(closet_text(sliding=True), spec)
        self.assertNotIn("modular", [call.args[0].get("action")
                                      for call in maestro_call.call_args_list])
        self.assertEqual(result["nominal_draft_scope"], "CONCEPT_ONLY")
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertIn("SLIDING_DOOR_MECHANISM_PENDING", result["nominal_draft_blockers"])
        self.assertEqual(
            result["sliding_door_review"]["mechanism"],
            "SLIDING_DOOR_MECHANISM_PENDING",
        )
        self.assertIn("riel", result["questions"][0]["question"].lower())
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_negated_sliding_doors_do_not_block_overlay_closet(self):
        spec = closet_two_module_spec(installation="built_in")
        spec["site_width_mm"] = {"top": 2035, "middle": 2024, "bottom": 2012}
        result = guided(closet_text() + " Las puertas no serán corredizas.", spec)
        self.assertNotIn("sliding_door_review", result)
        self.assertEqual(result["nominal_draft_blockers"], [])
        self.assertEqual(result["nominal_draft_piece_count"], 14)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))


class B6GuidedClosetTests(unittest.TestCase):
    def assert_review_only(self, result: dict, pieces: int) -> None:
        self.assertEqual(result["nominal_draft_piece_count"], pieces)
        self.assertFalse(result["can_generate_f7c"])
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_builtin_closet_from_owner_text_without_detail_spec_matches_f6_contract(self):
        result = guided_session_turn(closet_text())
        self.assertIsNotNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_scope"],
                         "CLIENT_PROPOSED_MULTICOMPONENT_REVIEW_ONLY")
        self.assertEqual(result["nominal_draft_engine_status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(result["nominal_draft_piece_count"], 14)
        self.assertFalse(result["can_generate_f7c"])

        request = result["nominal_draft_request"]
        spec = request["module_spec"]
        self.assertEqual(spec["installation"], "built_in")
        self.assertEqual(spec["site_width_mm"],
                         {"top": 2035, "middle": 2024, "bottom": 2012})
        self.assertEqual([module["module_id"] for module in spec["modules"]],
                         ["CLOSET_A", "CLOSET_B"])
        self.assertEqual([module["width_mm"] for module in spec["modules"]], [900, 900])
        self.assertEqual([module["fronts"]["leaf_count"] for module in spec["modules"]],
                         [2, 2])

        natural_modular = consult_maestro(request)["modular"]
        natural_exchange = validate_exchange(cad_exchange(natural_modular))
        self.assertEqual(natural_exchange["geometry_sha256"],
                         result["nominal_draft_geometry_sha256"])
        self.assertEqual(natural_modular["site"]["minimum_mm"], 2012)
        self.assertEqual(natural_modular["site"]["nominal_gap_at_narrowest_mm"], 212)

        reference_spec = closet_two_module_spec(installation="built_in")
        reference_spec["site_width_mm"] = spec["site_width_mm"]
        reference = consult_maestro({
            "action": "modular", "module_spec": reference_spec,
        })["modular"]
        reference_exchange = validate_exchange(cad_exchange(reference))
        self.assertEqual(reference["status"], natural_modular["status"])
        self.assertEqual(len(reference_exchange["boxes"]), 14)
        self.assertEqual(
            sorted((piece["piece_id"], piece.get("role"))
                   for piece in reference_exchange["boxes"]),
            sorted((piece["piece_id"], piece.get("role"))
                   for piece in natural_exchange["boxes"]),
        )
        for natural_module, reference_module in zip(spec["modules"], reference_spec["modules"]):
            for field in (
                "module_id", "width_mm", "panel_thickness_mm", "material_id",
                "construction", "support", "fronts", "back", "drawers",
            ):
                self.assertEqual(natural_module[field], reference_module[field], field)
            self.assertEqual(
                natural_module["horizontal_divider"]["position_from_clear_bottom_mm"],
                reference_module["horizontal_divider"]["position_from_clear_bottom_mm"],
            )
            self.assertNotEqual(
                natural_module["horizontal_divider"]["depth_mm"],
                reference_module["horizontal_divider"]["depth_mm"],
            )
        assumptions = result["nominal_draft_assumptions"]
        proposed = {item["field"]: item for item in assumptions}
        self.assertEqual(
            proposed["internal_layout.shelf_position_from_clear_bottom_mm"]["source"],
            "ENGINE_PROPOSED_NOT_OWNER_APPROVED",
        )
        self.assertEqual(
            proposed["doors.per_module_distribution"]["source"],
            "ENGINE_CALCULATED_FROM_OWNER_COUNTS",
        )
        natural_shelf = spec["modules"][0]["horizontal_divider"]
        reference_shelf = reference_spec["modules"][0]["horizontal_divider"]
        self.assertEqual(natural_shelf["position_from_clear_bottom_mm"], 700)
        self.assertEqual(natural_shelf["depth_mm"], 550)
        self.assertEqual(natural_shelf["depth_from_front_mm"], 0)
        self.assertEqual(reference_shelf["depth_mm"], 515)
        self.assertEqual(reference_shelf["depth_from_front_mm"], 18)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))
        self.assertFalse(result["can_generate_f7c"])

    def test_builtin_closet_without_all_three_site_measurements_stays_blocked(self):
        result = guided(closet_text(site_widths=None))
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertTrue(any("site_width_mm" in blocker
                            for blocker in result["nominal_draft_blockers"]))
        self.assertEqual(result["questions"][0]["field"], "site_width_mm")
        self.assertIn("arriba, al medio y abajo",
                      result["nominal_draft_next_question"])
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_t1_builtin_installation_survives_a_later_measurements_only_turn(self):
        first = guided_session_turn(closet_text(site_widths=None))
        self.assert_review_only(first, 0)
        self.assertIsNone(first["nominal_draft_request"])
        self.assertEqual(
            first["review_state"]["decisions"]["installation"]["value"],
            "built_in",
        )
        self.assertEqual(first["questions"][0]["field"], "site_width_mm")

        second = guided_session_turn(
            "Vano arriba 2035 mm, al medio 2024 mm y abajo 2012 mm.",
            first["review_state"],
        )
        self.assert_review_only(second, 14)
        spec = second["nominal_draft_request"]["module_spec"]
        self.assertEqual(spec["installation"], "built_in")
        self.assertEqual(spec["site_width_mm"], {
            "top": 2035, "middle": 2024, "bottom": 2012,
        })
        self.assertEqual(second["nominal_draft_engine_status"],
                         "DRAFT_NOT_FOR_CUTTING")

    def test_c1_builtin_closet_conversation_builds_shelves_doors_and_drawers(self):
        first = guided_session_turn(
            "Quiero un clóset empotrado contra la pared, de 1800 mm de ancho, "
            "2100 mm de alto y 550 mm de profundidad de carcasa. El vano mide "
            "arriba 2035 mm, al medio 2024 mm y abajo 2012 mm. Melamina de "
            "18 mm, tapa y base entre laterales, sin fondo posterior y "
            "directamente al piso."
        )
        self.assertIsNone(first["nominal_draft_request"])
        self.assertEqual(first["review_state"]["decisions"]["installation"]["value"],
                         "built_in")
        self.assertEqual(first["review_state"]["decisions"]["site_width_mm"]["value"], {
            "top": 2035, "middle": 2024, "bottom": 2012,
        })
        self.assertTrue(all(first[flag] is False for flag in FLAGS))

        second = guided_session_turn(
            "Dos módulos iguales de 900 mm. Solo el módulo izquierdo lleva una "
            "repisa horizontal a 700 mm desde la base interior y dos puertas "
            "abatibles sobrepuestas. El módulo derecho lleva tres cajones con "
            "frentes sobrepuestos y manijas.",
            first["review_state"],
        )
        self.assertIsNone(second["nominal_draft_request"])
        self.assertEqual(second["review_state"]["decisions"]["drawers"]["value"][
            "module_index"], 1)
        self.assertEqual(second["review_state"]["decisions"]["doors"]["value"][
            "module_index"], 0)
        self.assertEqual(second["review_state"]["decisions"]["drawer_layout"][
            "status"], "proposed")
        self.assertIn("drawer_layout", [item["field"] for item in second["questions"]])

        third = guided_session_turn(
            "Sí, confirmo las proporciones iguales y la separación geométrica "
            "propuestas, las luces nominales de las puertas y cajas ilustrativas "
            "pendientes de validar con el herraje.",
            second["review_state"],
        )
        spec = third["nominal_draft_request"]["module_spec"]
        self.assertEqual(spec["installation"], "built_in")
        self.assertEqual(spec["site_width_mm"], {
            "top": 2035, "middle": 2024, "bottom": 2012,
        })
        self.assertEqual([module["module_id"] for module in spec["modules"]],
                         ["CLOSET_A", "CLOSET_B"])
        self.assertEqual(spec["modules"][0]["horizontal_divider"][
            "position_from_clear_bottom_mm"], 700)
        self.assertEqual(spec["modules"][0]["fronts"]["leaf_count"], 2)
        self.assertEqual(spec["modules"][1]["drawers"][0]["drawer_id"], "D1")
        self.assertEqual(third["nominal_draft_piece_count"], 29)
        self.assertEqual(third["nominal_draft_blockers"], [])
        modular = consult_maestro(third["nominal_draft_request"])["modular"]
        exchange = validate_exchange(cad_exchange(modular))
        self.assertEqual(exchange["geometry_sha256"],
                         third["nominal_draft_geometry_sha256"])
        piece_ids = [piece["piece_id"] for piece in exchange["boxes"]]
        self.assertEqual(len(piece_ids), 29)
        self.assertEqual(len(piece_ids), len(set(piece_ids)))
        self.assertEqual(modular["site"]["minimum_mm"], 2012)
        self.assertEqual(modular["site"]["nominal_gap_at_narrowest_mm"], 212)
        self.assertEqual(modular["depth_review"]["carcass_depth_mm"], 550)
        self.assertEqual(modular["depth_review"]["assembled_external_depth_mm"], 568)
        self.assertTrue(all(third[flag] is False for flag in FLAGS))
        self.assertIs(third["can_generate_f7c"], False)

        corrected = guided_session_turn(
            "Al medio 2023 mm.", third["review_state"],
        )
        self.assertEqual(
            corrected["nominal_draft_request"]["module_spec"]["site_width_mm"],
            {"top": 2035, "middle": 2023, "bottom": 2012},
        )
        self.assertEqual(corrected["review_state"]["decisions"]["drawers"]["value"][
            "module_index"], 1)
        self.assertEqual(corrected["review_state"]["decisions"]["internal_layout"][
            "value"]["shelf_module_index"], 0)
        self.assertTrue(all(corrected[flag] is False for flag in FLAGS))

    def test_t2_site_measurements_accumulate_and_one_value_correction_is_local(self):
        result = guided_session_turn(closet_text(site_widths=None))
        self.assert_review_only(result, 0)
        result = guided_session_turn("Arriba 2035 mm.", result["review_state"])
        self.assert_review_only(result, 0)
        decision = result["review_state"]["decisions"]["site_width_mm"]
        self.assertEqual(decision["value"], {"top": 2035})
        self.assertEqual(decision["status"], "pending")
        self.assertEqual(result["questions"][0]["field"], "site_width_mm")

        result = guided_session_turn("Al medio 2024 mm.", result["review_state"])
        self.assert_review_only(result, 0)
        decision = result["review_state"]["decisions"]["site_width_mm"]
        self.assertEqual(decision["value"], {"top": 2035, "middle": 2024})
        self.assertEqual(decision["status"], "pending")
        self.assertEqual(result["questions"][0]["field"], "site_width_mm")

        result = guided_session_turn("Abajo 2012 mm.", result["review_state"])
        self.assert_review_only(result, 14)
        expected = {"top": 2035, "middle": 2024, "bottom": 2012}
        self.assertEqual(
            result["nominal_draft_request"]["module_spec"]["site_width_mm"],
            expected,
        )
        corrected = guided_session_turn(
            "Al medio 2023 mm.", result["review_state"],
        )
        self.assert_review_only(corrected, 14)
        self.assertEqual(
            corrected["nominal_draft_request"]["module_spec"]["site_width_mm"],
            {"top": 2035, "middle": 2023, "bottom": 2012},
        )
        self.assertEqual(
            corrected["review_state"]["decisions"]["site_width_mm"]["status"],
            "confirmed",
        )

    def test_t2_conflicting_accumulated_site_widths_fail_closed(self):
        first = guided_session_turn(closet_text(site_widths=None))
        result = guided_session_turn(
            "Arriba 1800 mm, al medio 1800 mm y abajo 1800 mm.",
            first["review_state"],
        )
        self.assert_review_only(result, 0)
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_engine_status"], "SITE_CONFLICT")

    def test_n_wall_contact_does_not_choose_installation_and_change_clears_stale_value(self):
        against_wall = guided_session_turn(
            closet_text(site_widths=None).replace(
                "Clóset empotrado contra la pared", "Clóset contra la pared",
            )
        )
        self.assert_review_only(against_wall, 0)
        self.assertEqual(against_wall["questions"][0]["field"], "installation")
        self.assertEqual(
            against_wall["review_state"]["decisions"]["wall_contact"]["value"],
            True,
        )

        built_in = guided_session_turn(closet_text())
        changed = guided_session_turn(
            "No será empotrado; será independiente y seguirá contra la pared.",
            built_in["review_state"],
        )
        self.assertEqual(
            changed["review_state"]["decisions"]["installation"]["value"],
            "freestanding",
        )
        self.assertEqual(
            changed["review_state"]["decisions"]["installation"]["source"],
            "OWNER_TEXT",
        )
        self.assertNotIn("site_width_mm", [
            question["field"] for question in changed["questions"]
        ])
        self.assertNotIn(
            "closet:built_in_wall_contact_required",
            changed["nominal_draft_blockers"],
        )
        self.assertTrue(all(changed[flag] is False for flag in FLAGS))

    def test_n_ambiguous_negation_reopens_installation_question(self):
        built_in = guided_session_turn(closet_text())
        result = guided_session_turn(
            "No será empotrado.", built_in["review_state"],
        )
        self.assert_review_only(result, 0)
        self.assertIsNone(result["nominal_draft_request"])
        decision = result["review_state"]["decisions"]["installation"]
        self.assertEqual(decision["status"], "pending")
        self.assertIsNone(decision["value"])
        self.assertEqual(result["questions"][0]["field"], "installation")

    def test_review_updates_cannot_set_fabrication_permissions(self):
        first = guided_session_turn(closet_text())
        self.assert_review_only(first, 14)
        with self.assertRaises(conversation_flow.MaestroError):
            guided_session_turn(
                "Continuemos la revisión.",
                first["review_state"],
                [{
                    "field": "fabrication_ready", "value": True,
                    "status": "confirmed", "source": "OWNER_TEXT",
                }],
            )
        forged = copy.deepcopy(first["review_state"])
        forged["fabrication_ready"] = True
        with self.assertRaises(conversation_flow.MaestroError):
            guided_session_turn("Continuemos.", forged)


class D2DepthSemanticsTests(unittest.TestCase):
    def assert_no_manufacturing_authority(self, result: dict) -> None:
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_d2_a_explicit_carcass_depth_keeps_overlay_extension_in_f6(self):
        first = guided_session_turn(closet_text())
        self.assertNotIn(
            "depth_reference",
            {item["field"] for item in first["questions"]},
        )
        review = guided_session_turn("Manijas visibles.", first["review_state"])
        request = review["nominal_draft_request"]
        self.assertIsNotNone(request)
        self.assertNotIn("max_assembled_depth_mm", request["module_spec"])
        self.assertEqual(
            review["nominal_draft_geometry_sha256"],
            "bf9da470138632b04c764c74d2ad08e5b80e87e5523d7958824f6f0c94a48e87",
        )

        answer = consult_maestro(request)
        depth = answer["modular"]["depth_review"]
        self.assertEqual(depth, {
            "carcass_depth_mm": 550,
            "front_extension_mm": 18,
            "assembled_external_depth_mm": 568,
            "max_assembled_depth_mm": None,
            "conflict": False,
        })
        self.assertEqual(review["nominal_draft_piece_count"], 14)
        self.assertEqual(len({part["piece_id"] for part in answer["modular"]["parts"]}), 14)
        self.assert_no_manufacturing_authority(review)

    def test_d2_b_unqualified_depth_asks_once_and_preserves_other_decisions(self):
        text = closet_text().replace(
            "carcasa de 1800 mm de ancho, 2100 mm de alto y 550 mm de profundidad",
            "medidas de 1800 mm de ancho, 2100 mm de alto y 550 mm de fondo",
        ) + " Manijas visibles."
        result = guided_session_turn(text)

        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertEqual([item["field"] for item in result["questions"]],
                         ["depth_reference"])
        self.assertEqual(
            result["questions"][0]["question"],
            "¿550 mm corresponden a la carcasa o a la profundidad exterior total contando las puertas?",
        )
        self.assertEqual(result["review_state"]["decisions"]["dimensions_mm"]["value"][
            "depth_mm"], 550)
        self.assertEqual(result["confirmed"]["doors"]["count"], 4)
        self.assertEqual(result["confirmed"]["material"], "melamina")
        self.assert_no_manufacturing_authority(result)

    def test_d2_c_explicit_maximum_survives_turns_without_inventing_carcass(self):
        text = closet_text().replace(
            "y 550 mm de profundidad", "y profundidad por definir",
        ) + " El máximo exterior contando puertas es de 550 mm. Manijas visibles."
        first = guided_session_turn(text)
        value = first["review_state"]["decisions"]["depth_reference"]["value"]
        self.assertEqual(value["carcass_depth_mm"], None)
        self.assertEqual(value["max_assembled_depth_mm"], 550)
        self.assertEqual(first["review_state"]["decisions"][
            "depth_reference"]["source"], "OWNER_TEXT")
        self.assertIsNone(first["nominal_draft_request"])
        self.assertEqual(first["questions"][0]["field"], "depth_reference")
        self.assertIn("profundidad de la carcasa",
                      first["questions"][0]["question"].lower())
        self.assert_no_manufacturing_authority(first)

        affirmative = guided_session_turn("Sí.", first["review_state"])
        self.assertEqual(affirmative["review_state"]["decisions"][
            "depth_reference"]["value"]["max_assembled_depth_mm"], 550)
        shelf = guided_session_turn(
            "Una repisa por módulo, a 700 mm desde la base interior.",
            affirmative["review_state"],
        )
        self.assertEqual(shelf["review_state"]["decisions"][
            "depth_reference"]["value"]["max_assembled_depth_mm"], 550)
        self.assertIsNone(shelf["nominal_draft_request"])
        self.assert_no_manufacturing_authority(shelf)

        corrected = guided_session_turn(
            "La profundidad de la carcasa será de 532 mm.", shelf["review_state"],
        )
        request = corrected["nominal_draft_request"]
        self.assertIsNotNone(request)
        self.assertEqual(request["module_spec"]["depth_mm"], 532)
        self.assertEqual(request["module_spec"]["max_assembled_depth_mm"], 550)
        answer = consult_maestro(request)
        self.assertEqual(answer["modular"]["depth_review"][
            "assembled_external_depth_mm"], 550)
        self.assertEqual(answer["modular"]["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assert_no_manufacturing_authority(corrected)

    def test_d2_d_excess_over_explicit_maximum_blocks_until_carcass_correction(self):
        first = guided_session_turn(closet_text() + " Manijas visibles.")
        self.assertIsNotNone(first["nominal_draft_request"])
        initial_hash = first["nominal_draft_geometry_sha256"]

        conflict = guided_session_turn(
            "El clóset tendrá 550 mm máximo exterior contando puertas.",
            first["review_state"],
        )
        self.assertIsNone(conflict["nominal_draft_request"])
        self.assertEqual(conflict["nominal_draft_engine_status"],
                         "NEEDS_DEPTH_REVISION")
        self.assertEqual(conflict["nominal_draft_piece_count"], 0)
        self.assertTrue(any("568 mm" in blocker and "550 mm" in blocker
                            for blocker in conflict["nominal_draft_blockers"]))
        self.assert_no_manufacturing_authority(conflict)

        corrected = guided_session_turn(
            "La profundidad de carcasa queda en 532 mm.", conflict["review_state"],
        )
        request = corrected["nominal_draft_request"]
        self.assertIsNotNone(request)
        self.assertEqual(request["module_spec"]["depth_mm"], 532)
        self.assertEqual(request["module_spec"]["max_assembled_depth_mm"], 550)
        self.assertEqual(corrected["confirmed"]["dimensions_mm"]["depth_mm"], 532)
        self.assertNotEqual(corrected["nominal_draft_geometry_sha256"], initial_hash)
        answer = consult_maestro(request)
        depth = answer["modular"]["depth_review"]
        self.assertEqual(depth["carcass_depth_mm"], 532)
        self.assertEqual(depth["front_extension_mm"], 18)
        self.assertEqual(depth["assembled_external_depth_mm"], 550)
        self.assertEqual(depth["max_assembled_depth_mm"], 550)
        self.assertEqual(len(answer["modular"]["parts"]), 14)
        self.assert_no_manufacturing_authority(corrected)

    def test_d2_e_kitchen_maximum_recalculates_and_open_bathroom_stays_unextended(self):
        kitchen_text = (
            "Gabinete de cocina independiente con carcasa de 800 mm de ancho, "
            "700 mm de alto y 500 mm de profundidad, melamina de 18 mm, "
            "laterales continuos, interior abierto, dos puertas sobrepuestas, "
            "sin cajones, sin fondo, sin mesón, separado de la pared, "
            "directamente al piso y manijas visibles."
        )
        kitchen = guided_session_turn(kitchen_text)
        self.assertIsNotNone(kitchen["nominal_draft_request"])
        capped = guided_session_turn(
            "El máximo exterior contando puertas será de 550 mm.",
            kitchen["review_state"],
        )
        self.assertEqual(capped["nominal_draft_request"]["module_spec"][
            "max_assembled_depth_mm"], 550)
        first_depth = consult_maestro(capped["nominal_draft_request"])[
            "modular"]["depth_review"]
        self.assertEqual(first_depth["assembled_external_depth_mm"], 518)

        thinner = guided_session_turn(
            "Espesor del tablero 15 mm.", capped["review_state"],
        )
        self.assertEqual(thinner["nominal_draft_request"]["module_spec"][
            "max_assembled_depth_mm"], 550)
        thinner_depth = consult_maestro(thinner["nominal_draft_request"])[
            "modular"]["depth_review"]
        self.assertEqual(thinner_depth["assembled_external_depth_mm"], 515)

        bathroom_text = (
            "Mueble de baño independiente de 800 mm ancho, 700 mm alto y "
            "450 mm fondo, MDP de 15 mm, laterales continuos, abierto, "
            "sin puertas, sin cajones, sin fondo y sin mesón, apoyado en el piso."
        )
        bathroom_first = guided_session_turn(bathroom_text)
        bathroom = guided_session_turn(
            "Confirmo las dimensiones exteriores: 800 mm de ancho, "
            "700 mm de alto y 450 mm de profundidad.",
            bathroom_first["review_state"],
        )
        self.assertEqual(bathroom["confirmed"]["dimensions_mm"]["depth_mm"], 450)
        self.assertIsNone(bathroom["review_state"]["decisions"][
            "depth_reference"]["value"]["max_assembled_depth_mm"])
        self.assertEqual(bathroom["nominal_draft_piece_count"], 4)
        countertop = guided_session_turn(
            "El mesón tendrá 650 mm de fondo.", bathroom["review_state"],
        )
        self.assertEqual(countertop["review_state"]["decisions"][
            "dimensions_mm"]["value"]["depth_mm"], 450)
        self.assertEqual(countertop["review_state"]["decisions"][
            "depth_reference"]["value"]["carcass_depth_mm"], 450)
        self.assert_no_manufacturing_authority(thinner)
        self.assert_no_manufacturing_authority(bathroom)
        self.assert_no_manufacturing_authority(countertop)

    def test_d2_explicit_exterior_depth_stays_pending_without_carcass_value(self):
        text = (
            "Gabinete de cocina independiente, dimensiones exteriores de 800 mm "
            "de ancho, 700 mm de alto y 500 mm de fondo, melamina de 18 mm, "
            "laterales continuos, dos puertas sobrepuestas, sin cajones, sin "
            "fondo, sin mesón, directo al piso, separado de la pared y manijas."
        )
        result = guided_session_turn(text)
        depth = result["review_state"]["decisions"]["depth_reference"]
        self.assertEqual(depth["status"], "pending")
        self.assertEqual(depth["value"], {
            "carcass_depth_mm": None,
            "max_assembled_depth_mm": None,
            "unresolved_depth_mm": 500,
        })
        self.assertIsNone(result["nominal_draft_request"])
        self.assertIn("depth_reference",
                      [item["field"] for item in result["questions"]])
        self.assert_no_manufacturing_authority(result)

    def test_d2_pending_depth_does_not_preempt_explicit_spec_or_owner_maximum(self):
        def review(utterance: str, spec: dict) -> dict:
            return prepare_guided_design_v1({
                "review_kind": "guided_design_v1",
                "utterance": utterance,
                "review_state": None,
                "review_updates": [],
                "photo_observations": None,
                "nominal_detail_spec": spec,
            })

        unqualified = closet_text().replace(
            "carcasa de 1800 mm de ancho, 2100 mm de alto y 550 mm de profundidad",
            "medidas de 1800 mm de ancho, 2100 mm de alto y 550 mm de fondo",
        )
        invalid_spec = closet_two_module_spec()
        invalid_spec["modules"][0]["width_mm"] -= 1
        invalid = review(unqualified, invalid_spec)
        self.assertIn("module_spec:module_width_sum_mismatch",
                      invalid["nominal_draft_blockers"])
        self.assertNotEqual(invalid["nominal_draft_blockers"], [
            "depth_reference:owner_clarification_required",
        ])
        self.assert_no_manufacturing_authority(invalid)

        capped_text = closet_text() + " El clóset tendrá 550 mm máximo exterior contando puertas."
        capped = review(capped_text, closet_two_module_spec())
        self.assertEqual(capped["nominal_draft_engine_status"], "NEEDS_DEPTH_REVISION")
        self.assertIsNone(capped["nominal_draft_request"])
        self.assertIn("568 mm", capped["nominal_draft_next_question"])
        self.assert_no_manufacturing_authority(capped)

    def test_builtin_closet_site_conflict_blocks_f6_geometry(self):
        result = guided(closet_text(site_widths=(1800, 1800, 1800)))
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertEqual(result["nominal_draft_engine_status"], "SITE_CONFLICT")
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_builtin_sliding_doors_remain_concept_only_without_detail_spec(self):
        result = guided(closet_text(sliding=True))
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_scope"], "CONCEPT_ONLY")
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertIn("SLIDING_DOOR_MECHANISM_PENDING",
                      result["nominal_draft_blockers"])
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_closet_wall_contact_alone_does_not_infer_builtin_installation(self):
        text = closet_text().replace("Clóset empotrado contra la pared",
                                     "Clóset contra la pared")
        result = guided(text)
        self.assertIsNone(result["nominal_draft_request"])
        self.assertNotEqual(
            result["review_state"]["decisions"]["installation"]["status"],
            "confirmed",
        )
        self.assertEqual(result["questions"][0]["field"], "installation")
        self.assertIn("empotrado", result["nominal_draft_next_question"].lower())
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_builtin_closet_without_equal_module_statement_asks_instead_of_guessing(self):
        text = closet_text().replace("dos módulos iguales", "dos módulos")
        result = guided(text)
        self.assertIsNone(result["nominal_draft_request"])
        self.assertIn("internal_layout:equal_module_widths_owner_text_required",
                      result["nominal_draft_blockers"])
        self.assertEqual(result["questions"][0]["field"], "internal_layout")
        self.assertIn("mismo ancho", result["nominal_draft_next_question"].lower())
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))


if __name__ == "__main__":
    unittest.main()
