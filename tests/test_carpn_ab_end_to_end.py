"""End-to-end storyboard fixtures for the local A+B acceptance matrix.

Fixtures are test data, not an actual owner conversation or approval.
"""
import copy
import json
from pathlib import Path
import unittest

from carpinova_agent.cad_exchange import cad_exchange
from carpinova_agent.conversation_flow import bind_reviewed_layout, build_flow_review, preview_conversation
from carpinova_agent.core import DesignError
from carpinova_agent.drawer_modules import guide_drawer_layout
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.pilot_cli import pilot_review

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")


def drawer_f6_base(style="INSET"):
    return json.loads((EXAMPLES / f"four-drawer-500x500x800-{style}-UNCONFIRMED.json").read_text(encoding="utf-8"))


def fixture_history(utterance):
    return [
        {"role": "user", "content": utterance},
        {"role": "assistant", "content": "Resumen completo de revisión presentado."},
        {"role": "user", "content": "Decisión declarada para el escenario de prueba."},
    ]


class CarpinovaABEndToEndTests(unittest.TestCase):
    def test_s1_equal_drawers_then_A_plus_100_B_minus_50_flows_through_F1_F6_F7C(self):
        utterance = "cajonera ancho 500 mm alto 800 mm profundidad 500 mm cuatro cajones"
        preview = preview_conversation(utterance, ["A 100 mm mas alto", "B 50 mm mas bajo"])
        f1 = preview["illustrative_drawer_layout_option"]["proposed_request"]["module_spec"]
        self.assertEqual(f1["opening_heights_mm"], [161, 162, 87, 270])
        self.assertEqual([x["opening_height_mm"] for x in preview["illustrative_drawer_layout_option"]["concept_preview"]["opening_refs_top_to_bottom"]], [270, 87, 162, 161])
        # Construction and inset details are explicit test-fixture decisions.
        f1["construction"] = "sides_full"
        req = drawer_f6_base("INSET")
        module = req["module_spec"]["modules"][0]
        module.pop("drawer_layout_reference", None)
        req = bind_reviewed_layout(req, f1, summary_shown=True, layout_approved=True)
        module = req["module_spec"]["modules"][0]
        plan = f1["opening_heights_mm"]
        for drawer, opening_height in zip(module["drawers"], plan):
            drawer["box_height_mm"] = min(drawer["box_height_mm"], opening_height - 25)
        result = consult_maestro(req)
        self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(result["modular"]["piece_count"], 28)
        self.assertEqual([d["opening_height_mm"] for d in module["drawers"]], [161, 162, 87, 270])
        self.assertEqual([result["fabrication_ready"], result["cutting_ready"], result["drilling_ready"], result["purchase_ready"]], [False]*4)
        package = pilot_review(req)
        self.assertIn("M1-D4-DRAWER_FACADE", package["parts-review.csv"])
        self.assertIn("| inset |", package["front-review.svg"])
        self.assertEqual(len(cad_exchange(result["modular"])["boxes"]), 28)

    def test_s2_bottom_large_drawer_keeps_D_D1_and_100mm_support_concept_only(self):
        guide = guide_drawer_layout({
            "type": "drawer_layout_guide", "width_mm": 500, "height_mm": 800,
            "depth_mm": 482, "small_drawers": 3, "construction": "sides_full",
            "support_style": "legs", "support_height_mm": 100,
        })
        req = drawer_f6_base("OVERLAY")
        req["module_spec"]["height_mm"] = 700
        req["module_spec"]["depth_mm"] = 482
        req["module_spec"]["max_assembled_depth_mm"] = 500
        module = req["module_spec"]["modules"][0]
        module.pop("drawer_layout_reference", None)
        module["support_concept"] = {"style": "legs", "support_height_mm": 100, "overall_height_mm": 800}
        req = bind_reviewed_layout(req, guide["proposed_layout_spec"], summary_shown=True, layout_approved=True)
        module = req["module_spec"]["modules"][0]
        for drawer, opening in zip(module["drawers"], guide["opening_plan"]):
            drawer["box_height_mm"] = min(drawer["box_height_mm"], opening["opening_height_mm"] - 25)
        answer = consult_maestro(req)
        self.assertEqual(answer["modular"]["dimensions_mm"], {"width": 500, "height": 700, "depth": 482})
        self.assertEqual(answer["modular"]["depth_review"]["assembled_external_depth_mm"], 500)
        self.assertFalse(answer["modular"]["depth_review"]["conflict"])
        self.assertEqual(answer["modular"]["modules"][0]["support_review"]["overall_height_mm"], 800)
        self.assertEqual([d["opening_height_mm"] for d in module["drawers"]], [232, 116, 116, 116])
        self.assertFalse(any("LEG" in p["piece_id"] for p in answer["modular"]["parts"]))
        from carpinova_agent.drawing_sheet import generic_booklet_svgs
        overview = generic_booklet_svgs(answer["modular"], cad_exchange(answer["modular"]))[0]
        self.assertIn("CARCASA CAD: 700 mm", overview)
        self.assertIn("PATAS SOLO CONCEPTUALES: 100 mm", overview)
        self.assertIn("ALTO TOTAL PROPUESTO: 800 mm", overview)
        self.assertIn("PATAS NO MODELADAS", overview)
        package = pilot_review(req)
        self.assertEqual(len(json.loads(package["cad-exchange.json"])["boxes"]), 28)
        self.assertTrue(all(answer[flag] is False for flag in FLAGS))

    def test_s3_preview_then_confirmed_open_cabinet_has_four_panels(self):
        preview = preview_conversation("gabinete ancho 800 mm alto 720 mm profundidad 550 mm")
        self.assertIn("illustrative_option", preview)
        self.assertIsNone(preview.get("modular"))
        # Explicit fixture choices after preview; this is not an owner decision.
        req = {"action": "modular", "module_spec": {
            "type": "modular_run", "application": "cabinet_run",
            "width_mm": 800, "height_mm": 720, "depth_mm": 550,
            "installation": "freestanding", "modules": [{
                "module_id": "M1", "width_mm": 800, "panel_thickness_mm": 15,
                "material_id": "MELAMINA_BLANCA_15", "construction": "sides_full",
                "fronts": "none", "back": "none", "support": "floor",
            }],
        }}
        answer = consult_maestro(req)
        self.assertEqual(answer["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(answer["modular"]["piece_count"], 4)
        trace = build_flow_review(
            utterance="gabinete abierto 800 por 720 por 550 mm",
            history=fixture_history("gabinete abierto 800 por 720 por 550 mm"),
            decisions=[{"topic": "carcasa abierta", "value": "sin frente ni fondo", "source": "TEST_FIXTURE_NOT_USER_CHOICE"}],
            request=req, summary_shown=True, layout_approved=True,
            construction_approved=True, source_fixture="TEST_FIXTURE_NOT_USER_CHOICE:S3",
        )
        package = pilot_review(req, trace)
        self.assertIn("flow-review.json", package)
        self.assertEqual(len(json.loads(package["cad-exchange.json"])["boxes"]), 4)
        self.assertTrue(all(answer[flag] is False for flag in FLAGS))

    def test_s4_real_doors_and_back_multi_module_fixture_match_CAD_CSV_SVG(self):
        spec = json.loads((EXAMPLES / "modular-kitchen-door-fronts.json").read_text(encoding="utf-8"))
        req = {"action": "modular", "module_spec": spec}
        answer = consult_maestro(req)
        self.assertEqual(answer["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(answer["modular"]["piece_count"], 13)
        self.assertEqual([m["fronts"]["style"] for m in answer["modular"]["modules"]], ["overlay", "inset"])
        self.assertEqual(answer["modular"]["modules"][0]["back"]["style"], "inset_two_strips")
        self.assertEqual(answer["modular"]["total_module_width_mm"], 1200)
        trace = build_flow_review(
            utterance="cocina modular de dos módulos con frentes y fondo de servicio",
            history=fixture_history("cocina modular de dos módulos con frentes y fondo de servicio"),
            decisions=[{"topic": "composición", "value": "fixture de dos módulos", "source": "TEST_FIXTURE_NOT_USER_CHOICE"}],
            request=req, summary_shown=True, layout_approved=True,
            construction_approved=True, source_fixture="examples/modular-kitchen-door-fronts.json",
        )
        summary = trace["confirmation_summary"]
        self.assertIn("Módulo 1 (SINK)", summary)
        self.assertIn("Módulo 2 (STORAGE)", summary)
        self.assertNotIn("Módulo 3", summary)
        package = pilot_review(req, trace)
        self.assertIn("flow-review.json", package)
        cad = json.loads(package["cad-exchange.json"])
        self.assertEqual(len(cad["boxes"]), 13)
        self.assertIn("SINK", package["parts-review.csv"])
        self.assertIn("STORAGE", package["parts-review.csv"])
        self.assertIn("SINK-FRONT_LEFT", package["front-review.svg"])
        self.assertIn("STORAGE-FRONT_SINGLE", package["front-review.svg"])
        self.assertTrue(all(answer[flag] is False for flag in FLAGS))

    def test_negative_f7c_incomplete_and_module_sum_mismatch_fail_closed(self):
        req = drawer_f6_base()
        req["module_spec"]["modules"][0]["drawers"][0].pop("opening_depth_mm")
        with self.assertRaises((ValueError, DesignError)):
            consult_maestro(req)
        spec = json.loads((EXAMPLES / "modular-kitchen-door-fronts.json").read_text(encoding="utf-8"))
        spec["modules"][1]["width_mm"] = 599
        blocked = consult_maestro({"action": "modular", "module_spec": spec})
        self.assertEqual(blocked["status"], "NEEDS_LAYOUT_REVISION")
        self.assertEqual(blocked["modular"]["parts"], [])


if __name__ == "__main__":
    unittest.main()
