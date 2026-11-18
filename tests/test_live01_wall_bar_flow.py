"""Regression tests grounded in the owner's CARPN-LIVE-01 transcript."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from carpinova_agent.conversation_flow import preview_conversation
from carpinova_agent.maestro import MaestroError
from carpinova_agent.natural_intake import extract_explicit_dimensions


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "wall-bar-900-review.json"
FIXTURE_SHA256 = "966ba2aaf6f104d3483b5d8126e2ec443c12c54893f992be7e106ce9593d956c"


def canonical_fixture_sha256() -> str:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    canonical = json.dumps(
        fixture, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

OWNER_FIRST = (
    "Bueno, me gustaría que volviéramos a hacer la barra, ¿cierto? Tengo una barra de cocina. "
    "Un extremo va pegado a la pared. La barra mide 90 centímetros de largo por 46 de ancho. "
    "Hay que dejar un espacio para que quepa una persona, que creo que el estándar son 60 centímetros. "
    "Entonces 60 centímetros de vacío y al otro extremo, que es el apoyo en el suelo, una cajonera "
    "con dos cajones pequeños y uno grande abajo. Entonces debe medir 30 centímetros esa cajonera. "
    "Quiero la cajonera con rieles. También lleva unas patas de 4 centímetros de alto. Entonces "
    "revisa adecuadamente para generar ese modelo específico que te estoy pidiendo."
)
OWNER_CLARIFICATION = (
    "Bueno, necesito que le pongas también lógica. Si te dije que son 90 centímetros y hay que dejar "
    "60 centímetros de espacio libre para una persona, lo que va contra la pared son unos 46 centímetros. "
    "Entonces, sí te falta lógica. La altura es de 90 centímetros, ¿cierto? del suelo hasta la barra."
)


class Live01WallBarFlowTests(unittest.TestCase):
    def assert_blocked_review(self, result):
        self.assertEqual(result["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(result["mode"], "F7D_WALL_BAR_REFERENCE_REVIEW")
        self.assertIsNone(result["proposed_request"])
        self.assertEqual(result["executed_tools"], [])
        self.assertEqual(result["piece_count"], 0)
        self.assertFalse(result["can_generate_f7c"])
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(result[flag], False)

    def test_first_owner_turn_keeps_unitless_wall_edge_pending_and_shows_reference_route(self):
        result = preview_conversation(OWNER_FIRST)
        self.assert_blocked_review(result)
        review = result["wall_bar_review"]
        self.assertEqual(review["owner_values"], {
            "overall_width_mm": 900,
            "overall_depth_mm": None,
            "overall_height_mm": None,
            "free_span_horizontal_mm": 600,
            "cabinet_width_mm": 300,
            "feet_height_mm": 40,
            "drawer_count": 3,
            "large_drawer_position": "bottom",
        })
        self.assertEqual(review["unit_requires_confirmation"][0]["literal"], "46 de ancho")
        self.assertTrue(review["standard_claim_unverified"])
        self.assertEqual(review["horizontal_allocation"]["equation"], "900 − 600 = 300 mm")
        self.assertTrue(review["horizontal_allocation"]["matches"])
        self.assertEqual(result["conversation_history"], [
            {"role": "user", "content": OWNER_FIRST},
        ])

    def test_owner_clarification_is_cumulative_requirement_not_f1_edit(self):
        with patch("carpinova_agent.conversation_flow.revise_drawer_concept",
                   side_effect=AssertionError("Requirement clarification is not F1")) as revise:
            result = preview_conversation(OWNER_FIRST, [OWNER_CLARIFICATION])
        revise.assert_not_called()
        self.assert_blocked_review(result)
        review = result["wall_bar_review"]
        self.assertEqual(review["owner_values"]["overall_width_mm"], 900)
        self.assertEqual(review["owner_values"]["overall_depth_mm"], 460)
        self.assertEqual(review["owner_values"]["overall_height_mm"], 900)
        self.assertEqual(review["owner_values"]["feet_height_mm"], 40)
        self.assertEqual(review["owner_values"]["free_span_horizontal_mm"], 600)
        self.assertEqual(review["owner_values"]["cabinet_width_mm"], 300)
        self.assertEqual(review["owner_values"]["drawer_count"], 3)
        self.assertEqual(review["owner_values"]["large_drawer_position"], "bottom")
        self.assertEqual(review["unit_requires_confirmation"], [])
        self.assertEqual(review["resolved_unit_confirmations"][0]["resolved_value_mm"], 460)
        self.assertEqual(review["horizontal_allocation"]["equation"], "900 − 600 = 300 mm")
        self.assertTrue(review["rails_requested"])
        self.assertFalse(review["rails_exact_reference_verified"])
        self.assertEqual(result["conversation_original_utterance"], OWNER_FIRST)
        self.assertEqual(result["requirement_clarifications"], [OWNER_CLARIFICATION])
        self.assertEqual(result["conversation_history"][-1]["content"], OWNER_CLARIFICATION)
        self.assertTrue(review["not_currently_confirmed"])
        self.assertEqual(review["reference_label"],
                         "MODELO HISTORICO — DECISIONES PREVIAS REPORTADAS; "
                         "ACEPTACION VISUAL ACTUAL PENDIENTE")
        self.assertEqual(review["reference_fixture_sha256"], FIXTURE_SHA256)
        prior = review["prior_design_choices_for_review"]
        self.assertEqual(prior["source"], "PRIOR_DESIGN_DECISION_REPORTED")
        self.assertTrue(prior["not_authenticated_as_a_new_approval"])
        self.assertEqual(prior["values"]["aesthetic_presentation"],
                         "bicolor_modern_preliminary")
        self.assertEqual(prior["values"]["drawer_opening_system"], "handle")
        self.assertEqual(review["illustrative_fixture_values"]["source"],
                         "TEST_FIXTURE_NOT_USER_CHOICE")
        self.assertNotIn("orientación", " ".join(review["pending_owner_decisions"]))
        self.assertIn("SKU", " ".join(review["pending_workshop"]))
        self.assertNotIn("USER_CONFIRMED", json.dumps(review, ensure_ascii=False))

    def test_same_900_length_and_height_and_feet_component_are_separate(self):
        text = (
            "Barra de cocina de 90 cm de largo, altura total 90 cm, 46 cm de ancho, "
            "60 cm de espacio libre, 30 cm esa cajonera, dos cajones pequeños y uno grande abajo, "
            "patas de 4 cm de alto."
        )
        evidence = extract_explicit_dimensions(text)
        self.assertEqual(evidence["dimensions_mm"], {
            "width_mm": 900, "height_mm": 900, "depth_mm": 460,
        })
        self.assertEqual(evidence["component_measurements"][0]["value_mm"], 40)
        self.assertEqual(evidence["component_measurements"][0]["scope"], "patas")
        self.assertEqual(evidence["ambiguous_fields"], [])

    def test_an_unresolved_46_without_same_value_wall_clarification_stays_unresolved(self):
        text = "Barra de cocina 90 cm de largo por 46 de ancho, altura 90 cm."
        evidence = extract_explicit_dimensions(text)
        self.assertEqual(evidence["dimensions_mm"], {"width_mm": 900, "height_mm": 900})
        self.assertEqual(evidence["unit_requires_confirmation"][0]["field"], "depth_mm")

    def test_true_ad_correction_without_existing_f1_still_fails_closed(self):
        with self.assertRaisesRegex(MaestroError, "No existe una distribución F1 revisable"):
            preview_conversation(OWNER_FIRST, ["A 10 cm mas alto"])
        with self.assertRaisesRegex(MaestroError, "No existe una distribución F1 revisable"):
            preview_conversation(OWNER_FIRST, ["A 10 metros mas alto"])

    def test_reference_fixture_binds_overlay_policy_without_promoting_it_to_owner_choice(self):
        self.assertEqual(canonical_fixture_sha256(), FIXTURE_SHA256)
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["module_spec"]["cabinet_module"]["width_mm"], 300)
        drawers = fixture["module_spec"]["cabinet_module"]["drawers"]
        self.assertTrue(all(drawer["front_construction"] == "separate"
                            and drawer["facade"]["style"] == "overlay"
                            for drawer in drawers))
        result = preview_conversation(OWNER_FIRST, [OWNER_CLARIFICATION])
        review = result["wall_bar_review"]
        self.assertEqual(review["reference_comparison"]["overall_depth_mm"]["matches"], True)
        prior = review["prior_design_choices_for_review"]["values"]
        self.assertEqual(prior["wall_side"], "left")
        self.assertEqual(prior["drawer_opening_face"], "long_side_front")
        self.assertEqual(prior["aesthetic_presentation"], "bicolor_modern_preliminary")
        self.assertTrue(review["not_currently_confirmed"])
        self.assertEqual(review["parts"], [])


if __name__ == "__main__":
    unittest.main()
