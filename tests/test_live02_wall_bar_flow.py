"""Focal LIVE02 tests: bind the owner's bar transcript to existing Maestro CAD."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from carpinova_agent.conversation_flow import build_flow_review, validate_flow_review
from carpinova_agent.maestro import MaestroError, consult_maestro
from carpinova_agent.cad_exchange import cad_exchange


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "wall-bar-900-review.json"
FIXTURE_SHA256 = "966ba2aaf6f104d3483b5d8126e2ec443c12c54893f992be7e106ce9593d956c"
GEOMETRY_SHA256 = "1e560b4856e3483ff6772a4da477d967d10aa6070fb2e96242c58f494c003492"
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
ASSISTANT_CLARIFICATION = (
    "La vista previa falló al interpretar tu descripción: tomó las patas de 4 cm como altura total "
    "y no dibujó el modelo."
)


def wall_bar_request() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def decision_trace() -> list[dict]:
    values = [
        ("overall_width_mm", 900, "USER_CONFIRMED"),
        ("overall_depth_mm", 460, "USER_CONFIRMED"),
        ("overall_height_mm", 900, "USER_CONFIRMED"),
        ("free_span_horizontal_mm", 600, "USER_CONFIRMED"),
        ("cabinet_width_mm", 300, "USER_CONFIRMED"),
        ("feet_height_mm", 40, "USER_CONFIRMED"),
        ("drawer_count", 3, "USER_CONFIRMED"),
        ("large_drawer_position", "bottom", "USER_CONFIRMED"),
        ("wall_side", "left", "PRIOR_DESIGN_DECISION_REPORTED"),
        ("drawer_opening_face", "long_side_front", "PRIOR_DESIGN_DECISION_REPORTED"),
        ("drawer_order", "D1=small_top;D2=small_middle;D3=large_bottom", "PRIOR_DESIGN_DECISION_REPORTED"),
        ("left_vertical_wood_panels", 0, "PRIOR_DESIGN_DECISION_REPORTED"),
        ("material_id", "MDP_15", "PRIOR_DESIGN_DECISION_REPORTED"),
        ("panel_thickness_mm", 15, "PRIOR_DESIGN_DECISION_REPORTED"),
        ("construction", "sides_full", "PRIOR_DESIGN_DECISION_REPORTED"),
        ("top_thickness_mm", 15, "PRIOR_DESIGN_DECISION_REPORTED"),
        ("front_construction", "separate", "OWNER_DIRECTIVE_CURRENT_PROMPT"),
        ("front_style", "overlay", "PRIOR_DESIGN_DECISION_REPORTED"),
        ("aesthetic_presentation", "bicolor_modern_preliminary", "PRIOR_DESIGN_DECISION_REPORTED"),
        ("drawer_opening_system", "handle", "PRIOR_DESIGN_DECISION_REPORTED"),
        ("fixture_sha256", FIXTURE_SHA256, "TEST_FIXTURE_NOT_USER_CHOICE"),
        ("slide_clearance_each_side_mm", 13, "TEST_FIXTURE_NOT_USER_CHOICE"),
        ("drawer_rear_setback_mm", 45, "TEST_FIXTURE_NOT_USER_CHOICE"),
        ("drawer_box_heights_mm", "D1=120;D2=120;D3=390", "TEST_FIXTURE_NOT_USER_CHOICE"),
        ("drawer_opening_heights_mm", "D1=150;D2=150;D3=447", "TEST_FIXTURE_NOT_USER_CHOICE"),
        ("facade_edgeband_mm", 2, "TEST_FIXTURE_NOT_USER_CHOICE"),
    ]
    return [{"topic": topic, "value": value, "source": source}
            for topic, value, source in values]


def build_trace(request=None, decisions=None):
    utterance = OWNER_FIRST
    history = [
        {"role": "assistant", "content": ASSISTANT_CLARIFICATION},
        {"role": "user", "content": OWNER_CLARIFICATION},
    ]
    return build_flow_review(
        utterance=utterance, history=history,
        decisions=decision_trace() if decisions is None else decisions,
        request=wall_bar_request() if request is None else request,
        summary_shown=True, layout_approved=True, construction_approved=True,
        source_fixture=f"examples/wall-bar-900-review.json#sha256={FIXTURE_SHA256}",
    )


class Live02WallBarFlowTests(unittest.TestCase):
    def test_owner_transcript_and_current_front_policy_bind_to_28_element_maestro_model(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        canonical = json.dumps(
            fixture, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), FIXTURE_SHA256)
        request = wall_bar_request()
        answer = consult_maestro(request)
        model = answer["modular"]
        exchange = cad_exchange(model)
        trace = build_trace(request)

        self.assertEqual(answer["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(len(model["parts"]), 28)
        self.assertEqual(exchange["geometry_sha256"], GEOMETRY_SHA256)
        self.assertEqual(trace["geometry_sha256"], GEOMETRY_SHA256)
        self.assertEqual(trace["piece_count"], 28)
        self.assertEqual(trace["source_provenance"]["geometry_engine"], "WALL_BAR_F1_F7C")
        self.assertEqual(trace["source_provenance"]["prior_decision_source"],
                         "PRIOR_DESIGN_DECISION_REPORTED")
        self.assertEqual([row["drawer_id"] for row in trace["openings_top_to_bottom"]],
                         ["D1", "D2", "D3"])
        self.assertEqual([row["opening_height_mm"] for row in trace["openings_top_to_bottom"]],
                         [150, 150, 447])
        self.assertEqual(trace["confirmation"]["basis"], "CLIENT_DECLARED_NOT_AUTHENTICATED")
        self.assertIn("provisionales para revisión", trace["confirmation_summary"])
        self.assertIn("no autenticadas como aprobación nueva",
                      trace["confirmation_summary"])
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(answer[flag], False)
            self.assertIs(model[flag], False)
            self.assertIs(trace[flag], False)
        self.assertTrue(validate_flow_review(trace, request))

    def test_wrong_owner_measurement_is_not_bound_to_fixture(self):
        request = wall_bar_request()
        request["module_spec"]["overall_depth_mm"] = 461
        with self.assertRaisesRegex(MaestroError, "Solicitud de barra distinta"):
            build_trace(request)

    def test_prior_decision_source_cannot_be_forged_as_current_user_confirmation(self):
        decisions = decision_trace()
        decisions[8]["source"] = "USER_CONFIRMED"
        with self.assertRaisesRegex(MaestroError, "Procedencia o valor de decisión"):
            build_trace(decisions=decisions)

    def test_visual_choices_are_preserved_as_reported_and_remain_nonmanufacturing(self):
        request = wall_bar_request()
        spec = request["module_spec"]
        self.assertEqual(spec["design_choices"]["aesthetic_presentation"],
                         "bicolor_modern_preliminary")
        self.assertTrue(all(drawer["facade"]["opening_system"] == "handle"
                            for drawer in spec["cabinet_module"]["drawers"]))
        trace = build_trace(request)
        self.assertEqual(trace["source_provenance"]["prior_decision_source"],
                         "PRIOR_DESIGN_DECISION_REPORTED")
        self.assertIn("Elección visual previa reportada", trace["confirmation_summary"])
        self.assertIn("sin acabado comercial", trace["confirmation_summary"])
        self.assertEqual(trace["confirmation"]["basis"],
                         "CLIENT_DECLARED_NOT_AUTHENTICATED")
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(trace[flag], False)

    def test_visual_choice_mutation_is_rejected_by_reference_binding(self):
        request = wall_bar_request()
        request["module_spec"]["design_choices"]["aesthetic_presentation"] = "undecided"
        with self.assertRaisesRegex(MaestroError, "Solicitud de barra distinta"):
            build_trace(request)
        request = wall_bar_request()
        request["module_spec"]["cabinet_module"]["drawers"][1]["facade"]["opening_system"] = "pending"
        with self.assertRaisesRegex(MaestroError, "Solicitud de barra distinta"):
            build_trace(request)

    def test_altered_prior_choice_and_geometry_are_rejected_on_validation(self):
        request = wall_bar_request()
        trace = build_trace(request)
        changed = copy.deepcopy(trace)
        changed["decisions"][8]["value"] = "right"
        with self.assertRaises(MaestroError):
            validate_flow_review(changed, request)


if __name__ == "__main__":
    unittest.main()
