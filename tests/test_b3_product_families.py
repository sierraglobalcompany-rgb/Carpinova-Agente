from __future__ import annotations

import copy
import inspect
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from carpinova_agent.cad_exchange import validate_exchange
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


if __name__ == "__main__":
    unittest.main()
