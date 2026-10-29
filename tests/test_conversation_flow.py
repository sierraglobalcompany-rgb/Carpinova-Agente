"""Focal acceptance tests for the A+B conversational adapter and trace."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from carpinova_agent.conversation_flow import (
    bind_reviewed_layout, build_flow_review, preview_conversation, validate_flow_review,
)
from carpinova_agent.drawer_modules import guide_drawer_layout
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.mcp_bridge import carpinova_generar_borrador, carpinova_leer_entregable, create_server
from carpinova_agent.pilot_cli import PilotError, verify_pilot_bundle

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def four_drawer_fixture(style="INSET"):
    request = json.loads((EXAMPLES / f"four-drawer-500x500x800-{style}-UNCONFIRMED.json").read_text(encoding="utf-8"))
    proposal = {
        "type": "drawer_layout_proposal", "width_mm": 500, "height_mm": 800,
        "depth_mm": 500, "panel_thickness_mm": 18, "construction": "sides_full",
        "vertical_gap_mm": 28, "drawer_weights": [1, 1, 1, 1],
        "opening_heights_mm": [161, 162, 87, 270],
    }
    # The S1 acceptance example overrides only opening heights through F1.
    from carpinova_agent.drawer_modules import propose_drawer_layout
    proposal_result = propose_drawer_layout(proposal)["opening_plan"]
    module = request["module_spec"]["modules"][0]
    for drawer, opening in zip(module["drawers"], proposal_result):
        drawer["opening_bottom_offset_mm"] = opening["opening_bottom_offset_mm"]
        drawer["opening_height_mm"] = opening["opening_height_mm"]
        drawer["box_height_mm"] = min(drawer["box_height_mm"], opening["opening_height_mm"] - 25)
    module["drawer_layout_reference"] = proposal
    return request


def confirmed_trace(request, *, utterance="mueble con cuatro cajones", fixture="TEST_FIXTURE_NOT_USER_CHOICE"):
    return build_flow_review(
        utterance=utterance,
        history=[{"role": "user", "content": utterance},
                 {"role": "assistant", "content": "Resumen nominal presentado."},
                 {"role": "user", "content": "Confirmo distribución y construcción para revisión."}],
        decisions=[{"topic": "distribución", "value": "A-D revisada", "source": "TEST_FIXTURE_NOT_USER_CHOICE"}],
        request=request, summary_shown=True, layout_approved=True,
        construction_approved=True, source_fixture=fixture,
    )


class ConversationFlowTests(unittest.TestCase):
    def test_preview_and_correction_replay_f1_with_stable_public_refs(self):
        utterance = "cajonera ancho 500 mm alto 800 mm profundidad 500 mm cuatro cajones"
        base = preview_conversation(utterance)
        after_a = preview_conversation(utterance, ["A 100 mm mas alto"])
        preview = preview_conversation(utterance, ["A 100 mm mas alto", "B 50 mm mas bajo"])
        front_rule = base["current_owner_directives"]["drawer_front_construction"]
        self.assertEqual(front_rule["front_construction"], "separate")
        self.assertEqual(front_rule["front_style"], "overlay")
        self.assertEqual(front_rule["source"], "OWNER_DIRECTIVE_CURRENT_PROMPT")
        self.assertTrue(front_rule["not_manufacturing_approval"])
        self.assertIn("solapes", " ".join(base["illustrative_drawer_layout_option"]["assumptions"]))
        proposal_module = base["illustrative_drawer_layout_option"][
            "proposed_request"]["module_spec"]
        self.assertNotIn("front_construction", proposal_module)
        self.assertNotIn("facade", proposal_module)
        self.assertIs(base["illustrative_drawer_layout_option"]["can_generate_f7c"], False)
        self.assertEqual(base["illustrative_drawer_layout_option"]["piece_count"], 0)
        self.assertTrue(all(base[flag] is False for flag in (
            "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")))
        complex_drawers = preview_conversation(
            "cajonera ancho 300 mm alto 900 mm fondo 400 mm "
            "con tres cajones pequeños y una gaveta grande abajo"
        )
        self.assertIsNone(complex_drawers.get("illustrative_drawer_layout_option"))
        self.assertEqual(
            complex_drawers["current_owner_directives"]["drawer_front_construction"]["front_style"],
            "overlay",
        )
        self.assertTrue(all(complex_drawers[flag] is False for flag in (
            "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")))
        self.assertEqual([r["opening_height_mm"] for r in base["illustrative_drawer_layout_option"]["concept_preview"]["opening_refs_top_to_bottom"]], [170]*4)
        self.assertEqual([r["opening_height_mm"] for r in after_a["illustrative_drawer_layout_option"]["concept_preview"]["opening_refs_top_to_bottom"]], [270, 137, 137, 136])
        option = preview["illustrative_drawer_layout_option"]
        refs = option["concept_preview"]["opening_refs_top_to_bottom"]
        self.assertEqual([row["ref"] for row in refs], ["A", "B", "C", "D"])
        self.assertEqual([row["cad_review_id"] for row in refs], ["D4", "D3", "D2", "D1"])
        self.assertEqual([row["opening_height_mm"] for row in refs], [270, 87, 162, 161])
        self.assertEqual(preview["can_generate_f7c"], False)
        self.assertEqual(preview["piece_count"], 0)
        request = four_drawer_fixture()
        proposal = preview["illustrative_drawer_layout_option"]["proposed_request"]["module_spec"]
        proposal["construction"] = "sides_full"  # explicit fixture selection
        del request["module_spec"]["modules"][0]["drawer_layout_reference"]
        bound = bind_reviewed_layout(
            request, proposal, summary_shown=True, layout_approved=True,
        )
        module = bound["module_spec"]["modules"][0]
        self.assertEqual(module["drawer_layout_reference"], proposal)
        self.assertEqual([d["opening_height_mm"] for d in module["drawers"]], [161, 162, 87, 270])

    def test_unconfirmed_or_unsupported_language_never_yields_geometry(self):
        preview = preview_conversation("mueble ancho 50 profundidad 50 alto 80")
        self.assertIsNone(preview.get("illustrative_drawer_layout_option"))
        self.assertEqual(preview["status"], "NEEDS_STRUCTURED_PROPOSAL")
        with self.assertRaises(ValueError):
            confirmed_trace(four_drawer_fixture(), utterance="")

    def test_trace_maps_public_D_to_internal_D1_and_is_bound_to_f1(self):
        request = four_drawer_fixture()
        trace = confirmed_trace(request)
        self.assertEqual(trace["openings_top_to_bottom"][0]["public_ref"], "A")
        self.assertEqual(trace["openings_top_to_bottom"][-1]["public_ref"], "D")
        self.assertEqual(trace["openings_top_to_bottom"][-1]["drawer_id"], "D1")
        self.assertEqual(trace["confirmation"]["basis"], "CLIENT_DECLARED_NOT_AUTHENTICATED")
        self.assertEqual(trace["authorization"], "NOT_FABRICATION_APPROVAL")
        self.assertIs(validate_flow_review(trace, request), True)
        changed = copy.deepcopy(trace)
        changed["openings_top_to_bottom"][0]["opening_height_mm"] += 1
        with self.assertRaises(ValueError):
            validate_flow_review(changed, request)

    def test_compact_summary_uses_correct_module_and_drawer_references(self):
        request = four_drawer_fixture()
        trace = confirmed_trace(request)
        summary = trace["confirmation_summary"]
        self.assertLessEqual(len(summary.splitlines()), 25)
        self.assertIn("Módulo 1 (M1)", summary)
        self.assertNotIn("Módulo 2", summary)
        self.assertIn("A ↔ D4", summary)
        self.assertIn("D ↔ D1", summary)
        self.assertNotIn("Cajón 2", summary)
        self.assertNotIn("Cajón 3", summary)

    def test_pilot_bundle_persists_trace_and_verifier_detects_tampering(self):
        request = four_drawer_fixture()
        envelope = {
            "utterance": "mueble con cuatro cajones",
            "history": [
                {"role": "user", "content": "mueble con cuatro cajones"},
                {"role": "assistant", "content": "Resumen nominal presentado."},
                {"role": "user", "content": "Confirmo distribución y construcción para revisión."},
            ],
            "decisions": [{"topic": "distribución", "value": "A-D revisada", "source": "TEST_FIXTURE_NOT_USER_CHOICE"}],
            "confirmation": {"summary_shown": True, "layout_approved": True, "construction_approved": True},
            "source_fixture": "TEST_FIXTURE_NOT_USER_CHOICE",
        }
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": td}):
            result = carpinova_generar_borrador(
                json.dumps(request), "flow_review_test", flow_review_json=json.dumps(envelope),
            )
            project = Path(result["review_directory"])
            self.assertIn("flow-review.json", result["files"])
            self.assertEqual(verify_pilot_bundle(project)["geometry_sha256"], result["geometry_sha256"])
            self.assertIn("CARPINOVA_CONVERSATION_FLOW_V1", carpinova_leer_entregable("flow_review_test", "flow-review.json")["contenido"])
            stored = project / "flow-review.json"
            data = json.loads(stored.read_text(encoding="utf-8"))
            data["utterance"] = "altered"
            stored.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(PilotError):
                verify_pilot_bundle(project)
            with self.assertRaises(PilotError):
                carpinova_leer_entregable("flow_review_test", "flow-review.json")

    def test_s2_three_small_and_bottom_gaveta_keep_D_to_D1_without_support_parts(self):
        guide = guide_drawer_layout({
            "type": "drawer_layout_guide", "width_mm": 500, "height_mm": 800,
            "depth_mm": 500, "small_drawers": 3, "construction": "sides_full",
            "support_style": "legs", "support_height_mm": 100,
        })
        request = four_drawer_fixture("OVERLAY")
        request["module_spec"]["height_mm"] = guide["carcass_height_mm"]
        module = request["module_spec"]["modules"][0]
        module["support_concept"] = {
            "style": "legs", "support_height_mm": 100, "overall_height_mm": 800,
        }
        for drawer, opening in zip(module["drawers"], guide["opening_plan"]):
            drawer["box_height_mm"] = min(drawer["box_height_mm"], opening["opening_height_mm"] - 25)
        request["module_spec"]["modules"][0]["drawer_layout_reference"] = guide["proposed_layout_spec"]
        # F1 reference and F6 drawer coordinates come from the same guide result.
        for drawer, opening in zip(module["drawers"], guide["opening_plan"]):
            drawer["opening_bottom_offset_mm"] = opening["opening_bottom_offset_mm"]
            drawer["opening_height_mm"] = opening["opening_height_mm"]
        trace = confirmed_trace(request)
        self.assertEqual(trace["openings_top_to_bottom"][-1]["public_ref"], "D")
        self.assertEqual(trace["openings_top_to_bottom"][-1]["drawer_id"], "D1")
        self.assertEqual(trace["openings_top_to_bottom"][-1]["opening_height_mm"], 232)
        self.assertEqual(trace["piece_count"], 28)
        answer = consult_maestro(request)
        self.assertFalse(any("LEG" in p["piece_id"] for p in answer["modular"]["parts"]))

    def test_mcp_still_registers_exactly_six_tools_and_flow_is_optional_argument(self):
        server = create_server()
        expected = {
            "carpinova_estado", "carpinova_consultar", "carpinova_generar_borrador",
            "carpinova_renderizar_lamina", "carpinova_exportar_3d", "carpinova_leer_entregable",
        }
        self.assertEqual(set(server._tool_manager._tools), expected)
        params = server._tool_manager._tools["carpinova_generar_borrador"].parameters
        self.assertIn("flow_review_json", params["properties"])
        self.assertNotIn("flow_review_json", params["required"])

    def test_confirmation_flags_and_exact_request_binding_are_fail_closed(self):
        request = four_drawer_fixture()
        with self.assertRaises(ValueError):
            build_flow_review(
                utterance="mueble", history=[], decisions=[], request=request,
                summary_shown=False, layout_approved=True, construction_approved=True,
            )
        altered = copy.deepcopy(request)
        altered["module_spec"]["modules"][0]["drawer_layout_reference"]["depth_mm"] = 482
        with self.assertRaises(Exception):
            confirmed_trace(altered)


if __name__ == "__main__":
    unittest.main()
