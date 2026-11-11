"""MCP consult-router tests for the guided, review-only conversation."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from carpinova_agent.maestro import MaestroError
from carpinova_agent.mcp_bridge import carpinova_consultar


FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready",
)


def query(utterance: str, *, review_state=None, review_updates=None,
          photo_observations=None) -> dict:
    return carpinova_consultar(json.dumps({
        "review_kind": "guided_design_v1",
        "utterance": utterance,
        "review_state": review_state,
        "review_updates": review_updates if review_updates is not None else [],
        "photo_observations": photo_observations,
    }, ensure_ascii=False))


class GuidedDesignMcpTests(unittest.TestCase):
    def test_three_turn_mcp_consult_retains_choices_and_closes_questions(self):
        first = query(
            "Quiero un gabinete de café de 890 mm de ancho, 770 mm de alto y "
            "600 mm de profundidad. Melamina de 15 mm, laterales continuos y dos puertas."
        )
        self.assertEqual(first["status"], "NEEDS_USER_CONFIRMATION")
        self.assertLessEqual(len(first["questions"]), 3)
        self.assertEqual(first["proposed"]["dimensions_mm"], {
            "width_mm": 890, "height_mm": 770, "depth_mm": 600,
        })
        self.assertEqual(first["confirmed"]["material"], "melamina")
        self.assertEqual(first["confirmed"]["thickness_mm"], 15)
        first_questions = {item["field"] for item in first["questions"]}
        self.assertTrue({"dimensions_mm", "wall_contact", "countertop"}.issubset(first_questions))

        second = query(
            "Las dimensiones exteriores de la carcasa son 890 mm de ancho, 770 mm de alto "
            "y 600 mm de profundidad; va contra la pared. El mesón tiene 940 mm de ancho, "
            "650 mm de profundidad y 30 mm de espesor.",
            review_state=first["review_state"],
        )
        self.assertEqual(second["confirmed"]["dimensions_mm"], {
            "width_mm": 890, "height_mm": 770, "depth_mm": 600,
        })
        self.assertIs(second["confirmed"]["wall_contact"], True)
        self.assertEqual(second["confirmed"]["countertop"]["dimensions_mm"], {
            "width_mm": 940, "depth_mm": 650,
        })
        self.assertEqual(second["confirmed"]["countertop"]["thickness_mm"], 30)
        second_questions = {item["field"] for item in second["questions"]}
        self.assertFalse({"dimensions_mm", "wall_contact", "countertop"} & second_questions)

        third = query(
            "No tendrá cajones; llevará una repisa horizontal a media altura. El fondo queda pendiente.",
            review_state=second["review_state"],
        )
        self.assertEqual(third["confirmed"]["dimensions_mm"], second["confirmed"]["dimensions_mm"])
        self.assertEqual(third["confirmed"]["material"], "melamina")
        self.assertEqual(third["confirmed"]["construction"], "sides_full")
        self.assertIs(third["confirmed"]["wall_contact"], True)
        self.assertEqual(third["confirmed"]["drawers"], "none")
        self.assertEqual(third["confirmed"]["internal_layout"], ["horizontal"])
        self.assertIn("back", third["pending"])
        third_questions = {item["field"] for item in third["questions"]}
        self.assertFalse({"dimensions_mm", "wall_contact", "countertop", "drawers",
                          "internal_layout"} & third_questions)
        self.assertLessEqual(len(third["questions"]), 3)
        self.assertEqual(third["piece_count"], 0)
        self.assertFalse(third["can_generate_f7c"])
        self.assertTrue(all(third[flag] is False for flag in FLAGS))

    def test_client_updates_cannot_forge_authority_or_overwrite_confirmed_text(self):
        first = query(
            "Gabinete de 890 mm de ancho, 770 mm de alto y 600 mm de profundidad, "
            "melamina de 15 mm, laterales continuos.",
        )
        with self.assertRaisesRegex(MaestroError, "fuente distinta de texto explícito"):
            query("Quiero continuar.", review_state=first["review_state"], review_updates=[{
                "field": "material", "value": "mdf", "status": "confirmed",
                "source": "BOOK_GUIDANCE",
            }])

        second = query("Quiero continuar.", review_state=first["review_state"], review_updates=[{
            "field": "material", "value": "mdf", "status": "confirmed",
            "source": "OWNER_TEXT",
        }])
        self.assertEqual(second["confirmed"]["material"], "melamina")
        self.assertNotEqual(second["confirmed"]["material"], "mdf")
        self.assertTrue(all(second[flag] is False for flag in FLAGS))

    def test_complete_carcass_review_reuses_maestro_f1_without_releasing_flags(self):
        result = query(
            "Gabinete: dimensiones exteriores 890 mm de ancho, 770 mm de alto y "
            "600 mm de profundidad; melamina de 15 mm, laterales continuos, "
            "separado de la pared, interior abierto, sin cajones, sin puertas, "
            "sin fondo y directamente al piso."
        )
        self.assertTrue(result["ready_for_nominal_review"])
        self.assertEqual(result["nominal_review"]["action"], "project")
        self.assertEqual(result["nominal_review"]["project"]["phase"], "GEOMETRY_DRAFT")
        self.assertIn("carcasa básica", result["nominal_review_scope"])
        self.assertEqual(result["piece_count"], 0)
        self.assertFalse(result["can_generate_f7c"])
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_natural_confirmation_and_local_support_measure_are_not_lost(self):
        first = query(
            "Gabinete de 890 mm de ancho, 770 mm de alto y 600 mm de profundidad; "
            "melamina de 15 mm, laterales continuos."
        )
        self.assertIn("dimensions_mm", first["proposed"])
        second = query(
            "Sí, confirmo las dimensiones exteriores.",
            review_state=first["review_state"],
        )
        self.assertEqual(second["confirmed"]["dimensions_mm"], {
            "width_mm": 890, "height_mm": 770, "depth_mm": 600,
        })

        supports = query("El gabinete lleva patas de 100 mm de altura y carcasa de 770 mm.")
        self.assertEqual(supports["confirmed"]["support"], {
            "style": "legs", "height_mm": 100,
        })
        drawers = query("Gabinete con dos cajones pequeños y uno grande.")
        self.assertEqual(drawers["confirmed"]["drawers"]["count"], 3)

    def test_countertop_dimensions_in_natural_por_phrase_are_not_reasked(self):
        result = query(
            "Mueble de café; mesón MDF RH de 940 mm por 650 mm, "
            "30 mm de espesor."
        )
        self.assertEqual(result["confirmed"]["countertop"]["dimensions_mm"], {
            "width_mm": 940, "depth_mm": 650,
        })
        self.assertEqual(result["confirmed"]["countertop"]["thickness_mm"], 30)
        self.assertNotIn("countertop", {item["field"] for item in result["questions"]})

    def test_negated_options_are_not_recorded_as_selected(self):
        result = query(
            "Gabinete; no quiero melamina ni manijas, no va contra la pared, "
            "sin repisa horizontal y sin patas."
        )
        self.assertNotIn("material", result["confirmed"])
        self.assertNotIn("opening_intent", result["confirmed"])
        self.assertIs(result["confirmed"]["wall_contact"], False)
        self.assertNotIn("internal_layout", result["confirmed"])
        self.assertEqual(result["proposed"]["support"]["style"],
                         "legs_absent_support_unspecified")

    def test_photo_observation_stays_proposed_and_accepts_no_file_or_pixel_payload(self):
        observation = {
            "visible_features": ["dos puertas"],
            "ambiguous_or_occluded": ["interior no visible"],
            "dimensions_from_user_only": {"width_mm": 900},
            "questions": ["¿Cuál es el ancho confirmado por el usuario?"],
        }
        result = query("Quiero revisar un gabinete desde una foto.",
                       photo_observations=observation)
        self.assertEqual(result["photo_input"], {
            "status": "IMAGE_OBSERVED_UNCONFIRMED", "pixels_received": False,
        })
        decision = result["review_state"]["decisions"]["photo_observations"]
        self.assertEqual(decision["status"], "proposed")
        self.assertEqual(decision["source"], "IMAGE_OBSERVED_UNCONFIRMED")
        self.assertNotIn("dimensions_mm", result["confirmed"])
        with self.assertRaisesRegex(MaestroError, "no admite archivos ni rutas"):
            query("Revisar foto.", photo_observations={
                **observation, "file_path": "C:/private/photo.png",
            })

    def test_tampered_state_and_unknown_request_fields_are_rejected(self):
        result = query("Gabinete de 890 mm de ancho.")
        tampered = deepcopy(result["review_state"])
        tampered["revision"] += 1
        with self.assertRaisesRegex(MaestroError, "secuencia completa"):
            query("Continuar.", review_state=tampered)

        payload = {
            "review_kind": "guided_design_v1", "utterance": "Gabinete.",
            "review_state": None, "review_updates": [], "photo_observations": None,
            "arbitrary": True,
        }
        with self.assertRaisesRegex(MaestroError, "sin campos adicionales"):
            carpinova_consultar(json.dumps(payload))

    def test_bridge_keeps_json_size_and_duplicate_key_guards(self):
        with self.assertRaisesRegex(MaestroError, "JSON válido"):
            carpinova_consultar('{"review_kind":"guided_design_v1",}')
        with self.assertRaisesRegex(MaestroError, "JSON válido"):
            carpinova_consultar(
                '{"review_kind":"guided_design_v1","review_kind":"guided_design_v1"}'
            )
        with self.assertRaisesRegex(MaestroError, "64 KiB"):
            carpinova_consultar("{" + " " * 65536 + "}")

    def _assert_review_only(self, result):
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        for flag in FLAGS:
            self.assertIs(result[flag], False)

    def test_t09_depth_does_not_change_pending_back_across_three_turns(self):
        first = query(
            "Quiero un gabinete de 800 mm de ancho, 700 mm de alto y 400 mm de "
            "profundidad, melamina de 15 mm, laterales continuos, dos puertas "
            "sobrepuestas y una división horizontal. No tendrá cajones."
        )
        self._assert_review_only(first)
        self.assertEqual(first["proposed"]["dimensions_mm"], {
            "width_mm": 800, "height_mm": 700, "depth_mm": 400,
        })
        self.assertEqual(first["confirmed"]["thickness_mm"], 15)
        self.assertEqual(first["confirmed"]["construction"], "sides_full")
        self.assertEqual(first["confirmed"]["doors"]["count"], 2)
        self.assertEqual(first["confirmed"]["front_style"], "overlay")
        self.assertEqual(first["confirmed"]["drawers"], "none")
        self.assertLessEqual(len(first["questions"]), 3)
        back1 = first["review_state"]["decisions"].get("back")
        self.assertIsNotNone(back1, "T1 debe crear back pendiente antes de probar T09")
        self.assertIsNone(back1["value"])
        self.assertEqual(back1["status"], "pending")
        self.assertEqual(back1["source"], "ENGINE_CALCULATED")

        second = query(
            "No va contra la pared; quiero manijas visibles. Conserva el mismo "
            "ancho, alto y fondo; no tendra cajones",
            review_state=first["review_state"],
        )
        self._assert_review_only(second)
        self.assertIs(second["confirmed"]["wall_contact"], False)
        self.assertEqual(second["confirmed"]["opening_intent"], "handle")
        self.assertEqual(second["confirmed"]["drawers"], "none")
        self.assertLessEqual(len(second["questions"]), 3)
        back2 = second["review_state"]["decisions"].get("back")
        self.assertEqual(back2, back1)

        third = query(
            "Agrega tambien una division vertical en el interior, conservando "
            "la division horizontal. No cambies las medidas ni las puertas",
            review_state=second["review_state"],
        )
        self._assert_review_only(third)
        self.assertEqual(third["confirmed"]["internal_layout"], ["horizontal", "vertical"])
        self.assertLessEqual(len(third["questions"]), 3)
        self.assertEqual(third["review_state"]["decisions"].get("back"), back1)

    def test_material_thickness_is_not_attributed_to_back_panel(self):
        for utterance in (
            "Quiero un gabinete de ancho 800 mm, alto 700 mm, fondo 400 mm, "
            "melamina de 15 mm, dos puertas.",
            "Gabinete con fondo 400 mm y melamina de 15 mm.",
        ):
            with self.subTest(utterance=utterance):
                result = query(utterance)
                self._assert_review_only(result)
                decision = result["review_state"]["decisions"].get("back")
                if decision is not None:
                    self.assertIsNone(decision["value"])
                    self.assertEqual(decision["status"], "pending")
                    self.assertEqual(decision["source"], "ENGINE_CALCULATED")

    def test_other_pending_choice_does_not_change_back(self):
        first = query(
            "Gabinete de 800 mm de ancho, 700 mm de alto y 400 mm de "
            "profundidad, melamina de 15 mm."
        )
        back1 = first["review_state"]["decisions"].get("back")
        self.assertIsNotNone(back1)
        second = query(
            "Conserva el mismo fondo y la elección de manijas está pendiente",
            review_state=first["review_state"],
        )
        self.assertEqual(second["review_state"]["decisions"].get("back"), back1)
        self._assert_review_only(second)

    def test_pending_hardware_is_not_attributed_to_back_panel(self):
        result = query("Gabinete con fondo 400 mm, el herraje queda pendiente.")
        self._assert_review_only(result)
        decision = result["review_state"]["decisions"].get("back")
        if decision is not None:
            self.assertIsNone(decision["value"])
            self.assertEqual(decision["status"], "pending")
            self.assertEqual(decision["source"], "ENGINE_CALCULATED")

    def test_negated_back_thickness_is_not_confirmed(self):
        result = query("Gabinete; no quiero fondo de 15 mm.")
        self._assert_review_only(result)
        decision = result["review_state"]["decisions"].get("back")
        if decision is not None:
            self.assertIsNone(decision["value"])
            self.assertEqual(decision["status"], "pending")
            self.assertEqual(decision["source"], "ENGINE_CALCULATED")

    def test_explicit_back_choices_remain_supported(self):
        cases = (
            ("Gabinete; sin fondo.", "none"),
            ("Gabinete; abierto por atrás.", "none"),
            ("Gabinete; fondo pendiente.", "pending"),
            ("Gabinete; el fondo queda pendiente.", "pending"),
            ("Gabinete; fondo de 3 mm.", "thin_3mm"),
            ("Gabinete; fondo posterior de 3 mm.", "thin_3mm"),
            ("Gabinete; fondo de 15 mm.", "same_board_15mm"),
            ("Gabinete; fondo de melamina de 15 mm.", "same_board_15mm"),
        )
        for utterance, expected in cases:
            with self.subTest(utterance=utterance):
                result = query(utterance)
                decision = result["review_state"]["decisions"].get("back")
                self.assertIsNotNone(decision)
                self.assertEqual(decision["value"], expected)


if __name__ == "__main__":
    unittest.main()
