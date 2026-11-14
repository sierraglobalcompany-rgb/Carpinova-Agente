"""Focused review-only contracts for the guided modular conversation."""
from __future__ import annotations

from copy import deepcopy
import unittest
import xml.etree.ElementTree as ET

from carpinova_agent.cad_exchange import cad_exchange
from carpinova_agent.conversation_flow import (
    image_input_unavailable,
    preview_conversation,
    update_review_state,
)
from carpinova_agent.drawing_sheet import three_views_svg
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.modular import design_modular_run

from test_coffee_assembly_p0 import coffee_spec


def _crossover_spec() -> dict:
    spec = coffee_spec()
    module = spec["modules"][0]
    module.pop("upper_support")
    module["horizontal_divider"] = {
        "material_id": "MELAMINE_15", "thickness_mm": 15,
        "position_from_clear_bottom_mm": 370,
        "depth_mm": 570, "depth_from_front_mm": 15,
    }
    module["vertical_divider"] = {
        "material_id": "MELAMINE_15", "thickness_mm": 15,
        "position_from_clear_left_mm": 220,
        "depth_mm": 570, "depth_from_front_mm": 15,
    }
    return spec


class GuidedDesignFlowTests(unittest.TestCase):
    def test_q01_complete_review_has_no_redundant_questions(self):
        response = update_review_state(updates=[
            {"field": "project_type", "value": "coffee_cabinet",
             "status": "confirmed", "source": "OWNER_TEXT"},
            {"field": "dimensions_mm", "value": [890, 770, 600],
             "status": "confirmed", "source": "OWNER_TEXT"},
            {"field": "drawers", "value": "none",
             "status": "confirmed", "source": "OWNER_TEXT"},
        ], pending_fields=[])
        self.assertEqual(response["questions"], [])
        self.assertEqual(response["review_state"]["decisions"]["drawers"]["value"], "none")

    def test_q02_unspecified_drawers_are_asked_not_assumed_absent(self):
        response = update_review_state(pending_fields=["drawers"])
        self.assertEqual([q["field"] for q in response["questions"]], ["drawers"])
        self.assertEqual(response["review_state"]["decisions"]["drawers"]["status"], "pending")

    def test_q03_explicit_no_drawers_resolves_the_question(self):
        response = update_review_state(updates=[
            {"field": "drawers", "value": "none", "status": "confirmed",
             "source": "OWNER_TEXT"},
        ], pending_fields=["drawers"])
        self.assertEqual(response["questions"], [])

    def test_q04_confirmed_visible_drawers_keep_the_maestro_piece_ids(self):
        from pathlib import Path
        import json
        example = Path(__file__).resolve().parents[1] / "examples" / "modular-two-drawers-inset.json"
        spec = json.loads(example.read_text(encoding="utf-8"))
        result = consult_maestro({"action": "modular", "module_spec": spec})
        self.assertEqual(result["modular"]["modules"][0]["drawer_ids"], ["TOP", "LOW"])
        self.assertFalse(result["fabrication_ready"])
        self.assertFalse(result["cutting_ready"])

    def test_q05_photo_drawer_observation_stays_unconfirmed(self):
        response = update_review_state(updates=[
            {"field": "photo_observations", "value": {
                "visible_features": ["dos puertas"],
                "ambiguous_or_occluded": ["posible cajón tras las puertas"],
                "dimensions_from_user_only": {}, "questions": ["¿Hay cajones ocultos?"],
            }, "status": "proposed", "source": "IMAGE_OBSERVED_UNCONFIRMED"},
        ], pending_fields=["drawers"])
        decisions = response["review_state"]["decisions"]
        self.assertEqual(decisions["photo_observations"]["source"], "IMAGE_OBSERVED_UNCONFIRMED")
        self.assertEqual(decisions["drawers"]["status"], "pending")
        self.assertEqual(response["questions"][0]["field"], "drawers")

    def test_q06_horizontal_divider_is_interior_not_a_second_top(self):
        spec = coffee_spec()
        response = consult_maestro({"action": "modular", "module_spec": spec})
        model = response["modular"]
        self.assertEqual(sum(p["role"] == "shelf_horizontal" for p in model["parts"]), 1)
        self.assertEqual(sum(p["role"] == "top" for p in model["parts"]), 0)

    def test_q07_vertical_divider_uses_f1_clear_dimensions(self):
        spec = coffee_spec()
        module = spec["modules"][0]
        module.pop("upper_support")
        module.pop("horizontal_divider")
        module["vertical_divider"] = {
            "material_id": "MELAMINE_15", "thickness_mm": 15,
            "position_from_clear_left_mm": 220,
            "depth_mm": 600, "depth_from_front_mm": 0,
        }
        model = consult_maestro({
            "action": "modular", "module_spec": spec,
        })["modular"]
        divider = next(p for p in model["parts"] if p["role"] == "divider_vertical")
        self.assertEqual(divider["nominal_face_x_mm"], 600)
        self.assertEqual(divider["nominal_face_y_mm"], 740)
        self.assertEqual(divider["nominal_origin_xyz_mm"], [260, 115, 50])
        self.assertIn("F1", divider["source_formula"])
        exchange = cad_exchange(model)
        self.assertTrue(any(b["role"] == "divider_vertical" for b in exchange["boxes"]))

    def test_q08_crossing_dividers_are_concept_only_with_zero_pieces(self):
        result = consult_maestro({
            "action": "modular", "module_spec": _crossover_spec(),
        })["modular"]
        self.assertEqual(result["status"], "CONCEPT_ONLY")
        self.assertEqual(result["piece_count"], 0)
        self.assertEqual(result["parts"], [])
        self.assertIn("JOINT_PENDING", " ".join(result["blockers"]))
        self.assertFalse(result["can_generate_f7c"])

    def test_q09_coffee_ties_work_without_an_interior_shelf(self):
        spec = coffee_spec()
        spec["modules"][0].pop("horizontal_divider")
        model = design_modular_run(spec)
        self.assertEqual(sum(p["role"].endswith("_tie") for p in model["parts"]), 3)
        self.assertFalse(any(p["role"] == "top" for p in model["parts"]))
        self.assertFalse(any(p["role"] == "shelf_horizontal" for p in model["parts"]))
        self.assertFalse(model["fabrication_ready"])

    def test_q10_coffee_ties_and_shelf_remain_independent(self):
        model = design_modular_run(coffee_spec())
        self.assertEqual(sum(p["role"].endswith("_tie") for p in model["parts"]), 3)
        self.assertEqual(sum(p["role"] == "shelf_horizontal" for p in model["parts"]), 1)

    def test_q11_wall_contact_without_back_only_proposes_options(self):
        response = update_review_state(updates=[
            {"field": "wall_contact", "value": True, "status": "confirmed",
             "source": "OWNER_TEXT"},
            {"field": "back", "value": "none", "status": "confirmed",
             "source": "OWNER_TEXT"},
        ])
        options = response["structure_options"]
        self.assertEqual(options["status"], "PROPOSAL_ONLY")
        self.assertIn("rear_ties", options["suggested_options"])
        self.assertIn("instalador", " ".join(options["limitations"]).casefold())

    def test_q12_thin_back_and_ties_return_concept_only_on_interference(self):
        spec = coffee_spec()
        spec["modules"][0]["back"] = {
            "style": "inset_full", "material_id": "BACK_3", "thickness_mm": 3,
            "services_present": False,
        }
        result = design_modular_run(spec)
        self.assertEqual(result["status"], "CONCEPT_ONLY")
        self.assertEqual(result["parts"], [])
        self.assertIn("interferencia", " ".join(result["blockers"]).casefold())

    def test_q13_fifteen_millimeter_back_is_not_assumed_equivalent_to_ties(self):
        spec = coffee_spec()
        spec["modules"][0]["back"] = {
            "style": "inset_full", "material_id": "BACK_15", "thickness_mm": 15,
            "services_present": False,
        }
        result = design_modular_run(spec)
        self.assertEqual(result["status"], "CONCEPT_ONLY")
        self.assertEqual(result["piece_count"], 0)
        self.assertIn("equivalencia", " ".join(result["blockers"]).casefold())

    def test_q14_freestanding_cabinet_does_not_get_automatic_back_or_ties(self):
        spec = coffee_spec()
        module = spec["modules"][0]
        module.pop("upper_support")
        module.pop("countertop")
        module.pop("support_concept")
        module["back"] = "pending"
        model = design_modular_run(spec)
        self.assertFalse(any(p["role"].endswith("_tie") for p in model["parts"]))
        self.assertFalse(any(p["role"].startswith("back_") for p in model["parts"]))

    def test_q15_countertop_does_not_add_a_full_top_under_it(self):
        for include_upper_support in (True, False):
            spec = coffee_spec()
            if not include_upper_support:
                spec["modules"][0].pop("upper_support")
            model = consult_maestro({
                "action": "modular", "module_spec": spec,
            })["modular"]
            self.assertEqual(
                sum(p["role"] == "countertop" for p in model["parts"]), 1
            )
            self.assertEqual(sum(p["role"] == "top" for p in model["parts"]), 0)
            if not include_upper_support:
                self.assertEqual(
                    model["assembly_review"]["countertop_support_status"],
                    "PENDING_NO_UPPER_SUPPORT_SELECTED",
                )
                exchange = cad_exchange(model)
                svg = three_views_svg(exchange, review_model=model)
                self.assertIn("Apoyo superior del mesón pendiente", svg)
                root = ET.fromstring(svg)
                footer_y = [int(node.get("y")) for node in root.iter()
                            if node.get("class") == "support-note"]
                hash_y = next(int(node.get("y")) for node in root.iter()
                              if node.get("class") == "hash")
                self.assertLess(max(footer_y), hash_y - 15)

    def test_q16_opening_intent_is_traceable_and_t_profile_is_educational(self):
        response = update_review_state(updates=[
            {"field": "opening_intent", "value": "profile_t_wood_inverted",
             "status": "proposed", "source": "BOOK_GUIDANCE"},
        ], pending_fields=["opening_intent"])
        entry = response["review_state"]["decisions"]["opening_intent"]
        self.assertEqual(entry["status"], "proposed")
        self.assertEqual(entry["source"], "BOOK_GUIDANCE")
        self.assertTrue(response["opening_guidance"]["educational_only"])
        self.assertFalse(response["opening_guidance"]["manufacturing_sku_selected"])

    def test_q17_photo_observation_questions_for_user_measures_and_hidden_parts(self):
        preview = preview_conversation(
            "Quiero revisar un gabinete a partir de una foto",
            review_updates=[{
                "field": "photo_observations", "value": {
                    "visible_features": ["dos puertas"],
                    "ambiguous_or_occluded": ["interior no visible"],
                    "dimensions_from_user_only": {},
                    "questions": ["¿Cuánto mide?", "¿Hay divisiones?"],
                }, "status": "proposed", "source": "IMAGE_OBSERVED_UNCONFIRMED",
            }],
            pending_fields=["dimensions_mm", "internal_layout"],
        )
        self.assertEqual(len(preview["guided_questions"]), 2)
        self.assertNotIn("cut", " ".join(preview["guided_questions"][0].values()).casefold())
        self.assertFalse(preview["fabrication_ready"])

    def test_q18_host_without_vision_reports_image_input_unavailable(self):
        result = image_input_unavailable()
        self.assertEqual(result["status"], "IMAGE_INPUT_NOT_AVAILABLE_IN_HOST")
        self.assertFalse(result["visual_capability_available"])
        self.assertEqual(result["pixels_received"], False)

    def test_q19_later_back_correction_preserves_other_confirmed_choices(self):
        first = update_review_state(updates=[
            {"field": "dimensions_mm", "value": [890, 770, 600],
             "status": "confirmed", "source": "OWNER_TEXT"},
            {"field": "opening_intent", "value": "handle",
             "status": "confirmed", "source": "OWNER_TEXT"},
            {"field": "material", "value": "melamine_15",
             "status": "confirmed", "source": "OWNER_TEXT"},
        ])
        second = update_review_state(first["review_state"], updates=[
            {"field": "back", "value": "thin_3mm", "status": "confirmed",
             "source": "OWNER_TEXT"},
        ])
        decisions = second["review_state"]["decisions"]
        self.assertEqual(decisions["opening_intent"]["value"], "handle")
        self.assertEqual(decisions["dimensions_mm"]["value"], [890, 770, 600])
        self.assertEqual(decisions["material"]["value"], "melamine_15")
        self.assertEqual(len(second["review_state"]["history"]), 4)

    def test_q20_legacy_coffee_drawing_remains_valid_with_safe_views(self):
        model = design_modular_run(coffee_spec())
        exchange = cad_exchange(model)
        svg = three_views_svg(exchange, review_model=model)
        root = ET.fromstring(svg)
        self.assertEqual(root.tag.rsplit("}", 1)[-1], "svg")
        self.assertIn("BORRADOR", " ".join(root.itertext()))
        self.assertFalse(exchange["fabrication_ready"])

    def test_generic_review_sheet_separates_closed_and_interior_roles(self):
        spec = coffee_spec()
        module = spec["modules"][0]
        module.pop("upper_support")
        module["back"] = "none"
        model = design_modular_run(spec)
        exchange = cad_exchange(model)
        svg = three_views_svg(exchange, review_model=model)
        root = ET.fromstring(svg)
        views = {}
        for element in root.iter():
            view = element.get("data-view")
            role = element.get("data-role")
            if view and role:
                views.setdefault(view, set()).add(role)
        exterior = next(k for k in views if k.startswith("01  FRENTE EXTERIOR"))
        interior = next(k for k in views if k.startswith("02  FRENTE INTERIOR"))
        rear = next(k for k in views if k.startswith("03  POSTERIOR"))
        self.assertNotIn("shelf_horizontal", views[exterior])
        self.assertIn("front_left", views[exterior])
        self.assertNotIn("front_left", views[interior])
        self.assertIn("shelf_horizontal", views[interior])
        self.assertNotIn("back_full", views[rear])
        self.assertIn("Trasera abierta", " ".join(root.itertext()))


if __name__ == "__main__":
    unittest.main()
