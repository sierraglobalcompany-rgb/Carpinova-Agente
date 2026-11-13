"""MCP consult-router tests for the guided, review-only conversation."""
from __future__ import annotations

from copy import deepcopy
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

from carpinova_agent.maestro import MaestroError
from carpinova_agent.conversation_flow import preview_natural_request
from carpinova_agent.drawer_modules import propose_drawer_layout
from carpinova_agent.mcp_bridge import (
    carpinova_consultar, carpinova_generar_borrador, carpinova_leer_entregable,
)
from carpinova_agent.pilot_cli import verify_pilot_bundle


FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready",
)


_UNSET = object()


def query(utterance: str, *, review_state=None, review_updates=None,
          photo_observations=None, nominal_detail_spec=_UNSET) -> dict:
    payload = {
        "review_kind": "guided_design_v1",
        "utterance": utterance,
        "review_state": review_state,
        "review_updates": review_updates if review_updates is not None else [],
        "photo_observations": photo_observations,
    }
    if nominal_detail_spec is not _UNSET:
        payload["nominal_detail_spec"] = nominal_detail_spec
    return carpinova_consultar(json.dumps(payload, ensure_ascii=False))


def kitchen_two_door_shelf_spec() -> dict:
    return {
        "type": "modular_run", "application": "kitchen",
        "width_mm": 800, "height_mm": 700, "depth_mm": 400,
        "installation": "freestanding",
        "modules": [{
            "module_id": "COCINA_1", "width_mm": 800,
            "panel_thickness_mm": 15, "material_id": "MELAMINA_15",
            "construction": "sides_full", "support": "floor",
            "back": "none", "drawers": "none",
            "fronts": {
                "style": "overlay", "leaf_count": 2,
                "material_id": "MELAMINA_15", "thickness_mm": 15,
                "hinge_sides": ["left", "right"],
                "left_reveal_mm": 3, "right_reveal_mm": 3,
                "top_reveal_mm": 4, "bottom_reveal_mm": 4,
                "center_gap_mm": 4,
            },
            "horizontal_divider": {
                "material_id": "MELAMINA_15", "thickness_mm": 15,
                "position_from_clear_bottom_mm": 250,
                "depth_mm": 350, "depth_from_front_mm": 25,
            },
        }],
    }


def bathroom_countertop_legs_spec() -> dict:
    return {
        "type": "modular_run", "application": "cabinet_run",
        "width_mm": 800, "height_mm": 700, "depth_mm": 400,
        "installation": "freestanding",
        "modules": [{
            "module_id": "BANO_1", "width_mm": 800,
            "panel_thickness_mm": 15, "material_id": "MELAMINA_15",
            "construction": "sides_full", "support": "floor",
            "fronts": "none", "back": "none", "drawers": "none",
            "support_concept": {
                "style": "legs", "support_height_mm": 100,
                "overall_height_mm": 830,
            },
            "countertop": {
                "material_id": "MESON_30", "thickness_mm": 30,
                "width_mm": 820, "depth_mm": 440,
                "left_overhang_mm": 10, "right_overhang_mm": 10,
                "front_overhang_mm": 20, "rear_overhang_mm": 20,
            },
        }],
    }


def bathroom_25mm_countertop_spec() -> dict:
    return {
        "type": "modular_run", "application": "cabinet_run",
        "width_mm": 800, "height_mm": 700, "depth_mm": 450,
        "installation": "freestanding",
        "modules": [{
            "module_id": "BANO_RH", "width_mm": 800,
            "panel_thickness_mm": 15, "material_id": "MELAMINA_15",
            "construction": "sides_full", "support": "floor",
            "fronts": "none", "back": "none", "drawers": "none",
            "support_concept": {
                "style": "legs", "support_height_mm": 100,
                "overall_height_mm": 825,
            },
            "countertop": {
                "material_id": "MDF_RH_25", "thickness_mm": 25,
                "width_mm": 820, "depth_mm": 470,
                "left_overhang_mm": 10, "right_overhang_mm": 10,
                "front_overhang_mm": 10, "rear_overhang_mm": 10,
            },
        }],
    }


def closet_two_module_spec(*, installation: str = "freestanding") -> dict:
    modules = []
    for module_id in ("CLOSET_A", "CLOSET_B"):
        modules.append({
            "module_id": module_id, "width_mm": 900,
            "panel_thickness_mm": 18, "material_id": "MELAMINA_18",
            "construction": "sides_full", "support": "floor",
            "fronts": {
                "style": "overlay", "leaf_count": 2,
                "material_id": "MELAMINA_18", "thickness_mm": 18,
                "hinge_sides": ["left", "right"],
                "left_reveal_mm": 3, "right_reveal_mm": 3,
                "top_reveal_mm": 4, "bottom_reveal_mm": 4,
                "center_gap_mm": 4,
            },
            "back": "none", "drawers": "none",
            "horizontal_divider": {
                "material_id": "MELAMINA_18", "thickness_mm": 18,
                "position_from_clear_bottom_mm": 700,
                "depth_mm": 515, "depth_from_front_mm": 18,
            },
        })
    return {
        "type": "modular_run", "application": "closet",
        "width_mm": 1800, "height_mm": 2100, "depth_mm": 550,
        "installation": installation, "modules": modules,
    }


def three_drawer_review_spec(utterance: str) -> dict:
    preview = preview_natural_request(utterance, include_concept_sketch=False)
    option = preview.get("illustrative_drawer_layout_option")
    reference = option["proposed_request"]["module_spec"]
    plan = propose_drawer_layout(reference)["opening_plan"]
    example = json.loads((Path(__file__).resolve().parents[1] / "examples" /
                          "four-drawer-500x500x800-OVERLAY-UNCONFIRMED.json")
                         .read_text(encoding="utf-8"))
    drawers = deepcopy(example["module_spec"]["modules"][0]["drawers"][:3])
    for drawer, opening in zip(drawers, plan):
        drawer["opening_bottom_offset_mm"] = opening["opening_bottom_offset_mm"]
        drawer["opening_height_mm"] = opening["opening_height_mm"]
        drawer["box_height_mm"] = min(drawer["box_height_mm"],
                                      opening["opening_height_mm"] - 25)
        drawer["material_id"] = "MELAMINA_18"
        drawer["bottom_material_id"] = "MATERIAL_PENDIENTE"
        drawer["facade"]["material_id"] = "MELAMINA_18"
        drawer["facade"]["opening_system"] = "pending"
    reference = deepcopy(reference)
    return {
        "type": "modular_run", "application": "cabinet_run",
        "width_mm": 500, "height_mm": 800, "depth_mm": 500,
        "installation": "freestanding",
        "modules": [{
            "module_id": "NOCHERO_1", "width_mm": 500,
            "panel_thickness_mm": 18, "material_id": "MELAMINA_18",
            "construction": reference["construction"],
            "fronts": "none", "back": "none", "support": "floor",
            "drawers": drawers, "drawer_layout_reference": reference,
        }],
    }


def record_gn3_tool(case_id: str, tool: str, request: dict, response: dict) -> None:
    root = os.environ.get("CARPINOVA_GN3_EVIDENCE_ROOT")
    if not root:
        return
    path = Path(root) / "real_tool_transcripts.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"calls": []}
    data["calls"].append({
        "case_id": case_id, "tool": tool,
        "execution": "local Python implementation; no mocks; not Codex Desktop MCP",
        "scenario_evidence": "acceptance test fixture; not live owner approval",
        "request": request, "response": response,
        "serialized_request_utf8": json.dumps(request, ensure_ascii=False),
    })
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def record_gn4_flow(case_id: str, turns: list[dict]) -> None:
    root = os.environ.get("CARPINOVA_GN4_EVIDENCE_ROOT")
    if not root:
        return
    path = Path(root) / "flows.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"cases": []}
    data["cases"].append({
        "case_id": case_id,
        "execution": "local Python MCP tool-router implementation; not Codex Desktop MCP",
        "turns": turns,
    })
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def gn3_query(case_id: str, utterance: str, *, review_state=None,
              nominal_detail_spec=_UNSET) -> dict:
    request = {
        "review_kind": "guided_design_v1", "utterance": utterance,
        "review_state": review_state, "review_updates": [],
        "photo_observations": None,
    }
    if nominal_detail_spec is not _UNSET:
        request["nominal_detail_spec"] = nominal_detail_spec
    response = query(
        utterance, review_state=review_state,
        nominal_detail_spec=nominal_detail_spec,
    )
    record_gn3_tool(case_id, "carpinova_consultar", {
        "solicitud_json": json.dumps(request, ensure_ascii=False),
        "decoded_solicitud_json": request,
    }, response)
    return response


class GuidedDesignMcpTests(unittest.TestCase):
    def assert_gn3_bundle(self, case_id: str, review: dict,
                          expected_roles: set[str] | None = None,
                          expected_scope: str =
                          "CLIENT_PROPOSED_MULTICOMPONENT_REVIEW_ONLY") -> dict:
        self.assertEqual(review["nominal_draft_scope"], expected_scope)
        self.assertEqual(review["nominal_draft_blockers"], [])
        self.assertGreater(review["nominal_draft_piece_count"], 0)
        self.assertTrue(all(review[flag] is False for flag in FLAGS))
        self.assertEqual(review["piece_count"], 0)
        self.assertIs(review["can_generate_f7c"], False)
        with tempfile.TemporaryDirectory(prefix=f"carpinova-gn3-{case_id}-") as root:
            output_root = Path(root)
            project = f"GN3_{case_id.upper()}"
            previous = os.environ.get("CARPINOVA_OUTPUT_ROOT")
            os.environ["CARPINOVA_OUTPUT_ROOT"] = str(output_root)
            request = review["nominal_draft_request"]
            try:
                generated = carpinova_generar_borrador(
                    solicitud_json=json.dumps(request, ensure_ascii=False),
                    proyecto=project, incluir_planos=False,
                )
            finally:
                if previous is None:
                    os.environ.pop("CARPINOVA_OUTPUT_ROOT", None)
                else:
                    os.environ["CARPINOVA_OUTPUT_ROOT"] = previous
            record_gn3_tool(case_id, "carpinova_generar_borrador", {
                "solicitud_json": json.dumps(request, ensure_ascii=False),
                "decoded_solicitud_json": request, "proyecto": project,
                "incluir_planos": False,
            }, generated)
            destination = output_root / project
            cad = verify_pilot_bundle(destination)
            expected_names = (
                "maestro-review.json", "front-review.svg", "parts-review.csv",
                "cad-exchange.json", "manifest.json",
            )
            self.assertTrue(all((destination / name).is_file() for name in expected_names))
            answer = json.loads((destination / "maestro-review.json").read_text(
                encoding="utf-8"))
            manifest = json.loads((destination / "manifest.json").read_text(
                encoding="utf-8"))
            saved_cad = json.loads((destination / "cad-exchange.json").read_text(
                encoding="utf-8"))
            rows = list(csv.DictReader((destination / "parts-review.csv").read_text(
                encoding="utf-8").splitlines()))
            ET.fromstring((destination / "front-review.svg").read_text(encoding="utf-8"))
            model = answer["modular"]
            roles = {part["role"] for part in model["parts"]}
            self.assertEqual(len(model["parts"]), review["nominal_draft_piece_count"])
            if expected_roles is not None:
                self.assertEqual(roles, expected_roles)
            geometry_sha = review["nominal_draft_geometry_sha256"]
            self.assertEqual(generated["geometry_sha256"], geometry_sha)
            self.assertTrue(all(generated[flag] is False for flag in FLAGS))
            self.assertEqual(cad["geometry_sha256"], geometry_sha)
            self.assertEqual(saved_cad["geometry_sha256"], geometry_sha)
            self.assertEqual(manifest["geometry_sha256"], geometry_sha)
            self.assertEqual({row["piece_id"] for row in rows},
                             {part["piece_id"] for part in model["parts"]})
            self.assertTrue(all(answer[flag] is False and model[flag] is False
                                and manifest[flag] is False for flag in FLAGS))
            self.assertTrue(all(cad[flag] is False for flag in (
                "fabrication_ready", "cutting_ready", "drilling_ready",
            )))
            evidence_root = os.environ.get("CARPINOVA_GN3_EVIDENCE_ROOT")
            if evidence_root:
                sample = Path(evidence_root) / "ARTIFACTS" / case_id
                sample.mkdir(parents=True, exist_ok=False)
                for name in expected_names:
                    shutil.copyfile(destination / name, sample / name)
        return {"generated": generated, "model": model, "rows": rows, "cad": cad}

    def test_gn3_r3_uses_owner_countertop_material_and_non_30_thickness(self):
        owner_text = (
            "Gabinete de baño: dimensiones exteriores de la carcasa 800 mm de "
            "ancho, 700 mm de alto y 450 mm de profundidad; melamina de 15 mm, "
            "laterales continuos, separado de la pared, interior abierto, sin "
            "cajones, sin puertas, sin fondo y patas de 100 mm de alto. Mesón: "
            "820 mm de ancho por 470 mm de profundidad y 25 mm de espesor, "
            "material MDF RH."
        )
        first = gn3_query("R3", owner_text)
        result = gn3_query(
            "R3",
            "Revisa esta propuesta nominal.", review_state=first["review_state"],
            nominal_detail_spec=bathroom_25mm_countertop_spec(),
        )
        self.assertEqual(result["nominal_draft_scope"],
                         "CLIENT_PROPOSED_MULTICOMPONENT_REVIEW_ONLY")
        self.assertEqual(result["nominal_draft_piece_count"], 4)
        self.assertEqual(result["nominal_draft_geometry_sha256"] is not None, True)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))
        self.assertIs(result["can_generate_f7c"], False)
        self.assertEqual(result["nominal_draft_request"]["module_spec"]["modules"][0]
                         ["countertop"]["thickness_mm"], 25)
        self.assertNotEqual(result["nominal_draft_request"]["module_spec"]["modules"][0]
                            ["countertop"]["material_id"], "MESON_30")
        bundle = self.assert_gn3_bundle("R3", result, {
            "left_side", "right_side", "bottom", "countertop",
        })
        self.assertEqual(bundle["generated"]["piece_count"], 4)
        self.assertEqual(bundle["model"]["assembly_review"]["carcass_dimensions_xyz_mm"],
                         [800, 700, 450])
        self.assertEqual(bundle["model"]["modules"][0]["support_review"]["overall_height_mm"],
                         825)
        self.assertNotIn("top", {part["role"] for part in bundle["model"]["parts"]})

    def test_gn3_r1_two_module_closet_runs_through_maestro_and_cadexchange(self):
        owner_text = (
            "Clóset independiente, dimensiones exteriores de carcasa: ancho "
            "1800 mm, alto 2100 mm y profundidad 550 mm; melamina de 18 mm, "
            "laterales continuos, dos módulos "
            "iguales, cuatro puertas sobrepuestas con manijas, una repisa "
            "horizontal en cada módulo, sin fondo, sin cajones, sin mesón y "
            "directamente al piso."
        )
        first = gn3_query("R1", owner_text)
        self.assertFalse({item["field"] for item in first["questions"]} & {"use"})
        self.assertIn("nominal_detail_spec:explicit_modular_run_required",
                      first["nominal_draft_blockers"])
        self.assertNotIn("project_type:unsupported", first["nominal_draft_blockers"])
        result = gn3_query(
            "R1", "Revisemos esta composición nominal de dos módulos.",
            review_state=first["review_state"],
            nominal_detail_spec=closet_two_module_spec(),
        )
        self.assertEqual(result["confirmed"]["project_type"], "closet")
        self.assertEqual(result["nominal_draft_request"]["module_spec"]["width_mm"], 1800)
        self.assertEqual([module["width_mm"] for module in
                          result["nominal_draft_request"]["module_spec"]["modules"]],
                         [900, 900])
        bundle = self.assert_gn3_bundle("R1", result, {
            "left_side", "right_side", "top", "bottom", "front_left",
            "front_right", "shelf_horizontal",
        })
        self.assertEqual(bundle["generated"]["piece_count"], 14)
        self.assertEqual(len(bundle["model"]["modules"]), 2)

        built_in_text = owner_text.replace("independiente", "contra la pared")
        built_in_first = gn3_query("R1", built_in_text)
        built_in = closet_two_module_spec(installation="built_in")
        blocked = gn3_query(
            "R1", "Revisemos el empotramiento sin medidas de sitio.",
            review_state=built_in_first["review_state"],
            nominal_detail_spec=built_in,
        )
        self.assertEqual(blocked["nominal_draft_scope"],
                         "BLOCKED_UNSUPPORTED_OR_INCOMPLETE")
        self.assertIsNone(blocked["nominal_draft_request"])
        self.assertEqual(blocked["nominal_draft_piece_count"], 0)
        self.assertIn("modular:NEEDS_SITE_MEASUREMENTS",
                      blocked["nominal_draft_blockers"])
        self.assertEqual(blocked["nominal_draft_engine_status"],
                         "NEEDS_SITE_MEASUREMENTS")
        self.assertTrue(all(blocked[flag] is False for flag in FLAGS))

    def test_gn3_r2_three_drawers_replay_a_b_and_opening_without_geometry_drift(self):
        base_intake = "cajonera ancho 500 mm alto 800 mm profundidad 500 mm tres cajones"
        detail_spec = three_drawer_review_spec(base_intake)
        initial = gn3_query("R2", base_intake, nominal_detail_spec=detail_spec)
        self.assertNotIn("nominal_detail_spec",
                         {item["field"] for item in initial["questions"]})
        owner_text = (
            "Es un nochero de dormitorio. Confirmo que las dimensiones exteriores "
            "de la carcasa son 500 mm de ancho, 800 mm de alto y 500 mm de "
            "profundidad; tres cajones, melamina de 18 mm, tapa y base entre "
            "laterales, independiente y separado de la pared, interior abierto, "
            "sin puertas, sin fondo, sin mesón, directamente al piso y con "
            "manijas visibles."
        )
        first = gn3_query("R2", owner_text, review_state=initial["review_state"])
        self.assertEqual(first["confirmed"]["drawers"]["count"], 3)
        self.assertEqual(first["confirmed"]["use"], "bedroom")
        baseline = first
        self.assertEqual(baseline["nominal_draft_scope"],
                         "CLIENT_PROPOSED_MULTICOMPONENT_REVIEW_ONLY")
        self.assertEqual(len(baseline["nominal_draft_opening_review"]["elements"]), 3)
        self.assertTrue(all(item["opening_system"] == "handle" for item in
                            baseline["nominal_draft_opening_review"]["elements"]))
        baseline_ids = {part["drawer_id"] for part in
                        baseline["nominal_draft_request"]["module_spec"]["modules"][0]["drawers"]}
        facade_ids = {item["piece_id"] for item in
                      baseline["nominal_draft_opening_review"]["elements"]}
        baseline_dims = deepcopy(baseline["nominal_draft_request"]["module_spec"])

        def heights_by_public_ref(result):
            by_drawer = {drawer["drawer_id"]: drawer["opening_height_mm"] for drawer in
                         result["nominal_draft_request"]["module_spec"]["modules"][0]["drawers"]}
            return {"A": by_drawer["D3"], "B": by_drawer["D2"], "C": by_drawer["D1"]}

        self.assertEqual(heights_by_public_ref(baseline), {"A": 236, "B": 236, "C": 236})

        after_a = gn3_query("R2", "Haz el cajón A 10 cm más alto",
                            review_state=baseline["review_state"])
        after_b = gn3_query("R2", "Haz el cajón B 5 cm más bajo",
                            review_state=after_a["review_state"])
        for result in (after_a, after_b):
            root = result["nominal_draft_request"]["module_spec"]
            module = root["modules"][0]
            self.assertEqual({drawer["drawer_id"] for drawer in module["drawers"]},
                             baseline_ids)
            self.assertEqual(
                {key: root[key] for key in ("width_mm", "height_mm", "depth_mm")},
                {key: baseline_dims[key] for key in ("width_mm", "height_mm", "depth_mm")},
            )
            self.assertEqual(module["width_mm"], baseline_dims["modules"][0]["width_mm"])
            self.assertEqual({item["piece_id"] for item in
                              result["nominal_draft_opening_review"]["elements"]}, facade_ids)
            self.assertEqual(result["nominal_draft_revision"]["reference_ids_preserved"], True)
            self.assertEqual(result["nominal_draft_revision"]["exterior_dimensions_preserved"], True)
            self.assertEqual(result["nominal_draft_piece_count"],
                             baseline["nominal_draft_piece_count"])
        self.assertEqual(heights_by_public_ref(after_a), {"A": 336, "B": 186, "C": 186})
        self.assertEqual(heights_by_public_ref(after_b), {"A": 336, "B": 136, "C": 236})
        self.assertEqual(after_b["nominal_draft_revision"]["last_revision"]["instruction"],
                         "Haz el cajón B 5 cm más bajo")
        before_opening_change = after_b["nominal_draft_geometry_sha256"]
        pushed = gn3_query(
            "R2", "Cambiemos la apertura de los tres frentes a push-to-open.",
            review_state=after_b["review_state"],
        )
        self.assertEqual(pushed["nominal_draft_geometry_sha256"], before_opening_change)
        opening_elements = pushed["nominal_draft_opening_review"]["elements"]
        self.assertEqual(len(opening_elements), 3)
        self.assertTrue(all(item["opening_system"] == "push_to_open"
                            and item["hardware_selected"] is False
                            for item in opening_elements))
        bundle = self.assert_gn3_bundle("R2", pushed, {
            "left_side", "right_side", "top", "bottom", "drawer_side_left",
            "drawer_side_right", "drawer_front_wall", "drawer_rear_wall",
            "drawer_bottom", "drawer_facade",
        })
        facade_rows = [row for row in bundle["rows"] if row["role"] == "drawer_facade"]
        self.assertEqual(len(facade_rows), 3)
        self.assertTrue(all(row["opening_system_intent"] == "push_to_open"
                            for row in facade_rows))
        self.assertTrue(all(row["drawer_facade_style"] == "overlay"
                            for row in facade_rows))
        self.assertTrue(all(row["material_id"] == "MELAMINA_18"
                            for row in facade_rows))
        drawer_bottoms = [row for row in bundle["rows"] if row["role"] == "drawer_bottom"]
        self.assertEqual(len(drawer_bottoms), 3)
        self.assertTrue(all(row["material_id"] == "MATERIAL_PENDIENTE"
                            for row in drawer_bottoms))

    def test_gn4_t1_invalid_drawer_revision_is_atomic_and_valid_retry_uses_same_state(self):
        utterance = "cajonera ancho 500 mm alto 800 mm profundidad 500 mm tres cajones"
        spec = three_drawer_review_spec(utterance)
        first = query(utterance, nominal_detail_spec=spec)
        owner_text = (
            "Nochero: dimensiones exteriores 500 mm de ancho, 800 mm de alto y "
            "500 mm de profundidad; melamina de 18 mm, tapa y base entre laterales, "
            "separado de la pared, interior abierto, tres cajones, sin puertas, "
            "sin fondo, sin mesón, directamente al piso y manijas visibles."
        )
        confirmed = query(owner_text, review_state=first["review_state"])
        after_a = query("Haz el cajón A 10 cm más alto",
                        review_state=confirmed["review_state"])
        after_b = query("Haz el cajón B 5 cm más bajo",
                        review_state=after_a["review_state"])
        before = deepcopy(after_b["review_state"])
        bad = query("Haz el cajón A 1000 mm más alto",
                    review_state=after_b["review_state"])

        self.assertEqual(bad["review_state"], before)
        saved = before["decisions"]["nominal_detail_spec"]["value"]
        self.assertEqual(saved["source_utterance"], utterance)
        self.assertEqual(saved["corrections"], [
            "Haz el cajón A 10 cm más alto", "Haz el cajón B 5 cm más bajo",
        ])
        self.assertIn("Corrección: entre 1 y 500 mm enteros.",
                      bad["nominal_draft_blockers"])
        self.assertIs(bad["nominal_draft_revision_rejected"], True)
        self.assertEqual(bad["nominal_draft_request"],
                         after_b["nominal_draft_request"])
        self.assertEqual(bad["nominal_draft_geometry_sha256"],
                         after_b["nominal_draft_geometry_sha256"])
        self.assertEqual(bad["nominal_draft_piece_count"],
                         after_b["nominal_draft_piece_count"])
        self.assertEqual(bad["nominal_draft_revision"],
                         after_b["nominal_draft_revision"])
        self.assertTrue(all(bad[flag] is False for flag in FLAGS))

        retry = query("Haz el cajón B 10 mm más bajo",
                      review_state=after_b["review_state"])
        self.assertEqual(retry["review_state"]["decisions"]["nominal_detail_spec"]
                         ["value"]["corrections"], [
                             *saved["corrections"], "Haz el cajón B 10 mm más bajo",
                         ])
        self.assertEqual(retry["nominal_draft_piece_count"],
                         after_b["nominal_draft_piece_count"])
        self.assertEqual(retry["nominal_draft_revision"]["reference_ids_preserved"], True)
        self.assertEqual(retry["nominal_draft_revision"]["exterior_dimensions_preserved"], True)
        self.assertTrue(all(retry[flag] is False for flag in FLAGS))
        record_gn4_flow("T1", [
            {"request": {"utterance": utterance, "review_state": None,
                          "nominal_detail_spec": spec}, "response": first},
            {"request": {"utterance": owner_text,
                          "review_state": first["review_state"]}, "response": confirmed},
            {"request": {"utterance": "Haz el cajón A 10 cm más alto",
                          "review_state": confirmed["review_state"]}, "response": after_a},
            {"request": {"utterance": "Haz el cajón B 5 cm más bajo",
                          "review_state": after_a["review_state"]}, "response": after_b},
            {"request": {"utterance": "Haz el cajón A 1000 mm más alto",
                          "review_state": before}, "response": bad},
            {"request": {"utterance": "Haz el cajón B 10 mm más bajo",
                          "review_state": before}, "response": retry},
        ])

    def test_gn4_t2_generic_confirmation_never_promotes_internal_or_photo_state(self):
        utterance = "cajonera ancho 500 mm alto 800 mm profundidad 500 mm tres cajones"
        spec = three_drawer_review_spec(utterance)
        observation = {
            "visible_features": ["tres frentes"],
            "ambiguous_or_occluded": ["interior no visible"],
            "dimensions_from_user_only": {}, "questions": [],
        }
        first = query(utterance, nominal_detail_spec=spec,
                      photo_observations=observation)
        internal_before = deepcopy(first["review_state"]["decisions"]["nominal_detail_spec"])
        photo_before = deepcopy(first["review_state"]["decisions"]["photo_observations"])
        all_confirm = query("Confirmo todo", review_state=first["review_state"])
        self.assertEqual(all_confirm["review_state"]["decisions"]["nominal_detail_spec"],
                         internal_before)
        self.assertEqual(all_confirm["review_state"]["decisions"]["photo_observations"],
                         photo_before)
        self.assertNotIn("nominal_detail_spec", all_confirm["confirmed"])
        self.assertNotIn("photo_observations", all_confirm["confirmed"])
        self.assertTrue(all(all_confirm[flag] is False for flag in FLAGS))

        ambiguous = query(
            "Gabinete de cocina.",
            review_updates=[
                {"field": "support", "value": {"style": "wall_mounted"},
                 "status": "proposed", "source": "ENGINE_CALCULATED"},
                {"field": "opening_intent", "value": "push_to_open",
                 "status": "proposed", "source": "ENGINE_CALCULATED"},
            ],
        )
        yes = query("Sí", review_state=ambiguous["review_state"])
        for field in ("support", "opening_intent"):
            self.assertEqual(yes["review_state"]["decisions"][field]["status"],
                             "proposed")
            self.assertNotIn(field, yes["confirmed"])
        record_gn4_flow("T2", [
            {"request": {"utterance": utterance,
                          "nominal_detail_spec": spec,
                          "photo_observations": observation}, "response": first},
            {"request": {"utterance": "Confirmo todo",
                          "review_state": first["review_state"]},
             "response": all_confirm},
            {"request": {"utterance": "Gabinete de cocina.",
                          "review_updates": [
                              {"field": "support", "value": {"style": "wall_mounted"},
                               "status": "proposed", "source": "ENGINE_CALCULATED"},
                              {"field": "opening_intent", "value": "push_to_open",
                               "status": "proposed", "source": "ENGINE_CALCULATED"},
                          ]}, "response": ambiguous},
            {"request": {"utterance": "Sí",
                          "review_state": ambiguous["review_state"]}, "response": yes},
        ])

    def test_gn4_t3_natural_two_module_closet_generates_five_review_artifacts(self):
        owner_text = (
            "Clóset independiente, dimensiones exteriores de carcasa: ancho "
            "1800 mm, alto 2100 mm y profundidad 550 mm; melamina de 18 mm, "
            "laterales continuos, dos módulos iguales, dos puertas sobrepuestas "
            "por módulo, una repisa por módulo a 700 mm desde la base interior, "
            "sin fondo trasero ni cajones."
        )
        first = query(owner_text)
        self.assertIn("support", {item["field"] for item in first["questions"]})
        self.assertIsNone(first["nominal_draft_request"])
        answer_text = "Directamente al piso y manijas visibles."
        second = query(answer_text, review_state=first["review_state"])
        self.assertEqual(second["nominal_draft_scope"],
                         "CLIENT_PROPOSED_MULTICOMPONENT_REVIEW_ONLY")
        self.assertEqual(second["nominal_draft_blockers"], [])
        self.assertEqual(second["nominal_draft_piece_count"], 14)
        self.assertEqual(second["piece_count"], 0)
        self.assertIs(second["can_generate_f7c"], False)
        self.assertTrue(all(second[flag] is False for flag in FLAGS))
        modules = second["nominal_draft_request"]["module_spec"]["modules"]
        self.assertEqual([module["width_mm"] for module in modules], [900, 900])
        self.assertEqual([module["module_id"] for module in modules],
                         ["CLOSET_1", "CLOSET_2"])
        self.assertEqual(sum(module["fronts"]["leaf_count"] for module in modules), 4)
        self.assertTrue(all(module["horizontal_divider"][
            "position_from_clear_bottom_mm"] == 700 for module in modules))
        assumptions = second["nominal_draft_assumptions"]
        self.assertTrue(assumptions)
        self.assertTrue(all(item["source"] == "ENGINE_PROPOSED_NOT_OWNER_APPROVED"
                            for item in assumptions))
        self.assertTrue(any(item["field"].endswith("shelf_depth_and_setback")
                            for item in assumptions))

        record_gn4_flow("T3", [
            {"request": {"utterance": owner_text, "review_state": None,
                          "review_updates": [], "photo_observations": None},
             "response": first},
            {"request": {"utterance": answer_text,
                          "review_state": first["review_state"],
                          "review_updates": [], "photo_observations": None},
             "response": second},
        ])
        bundle = self.assert_gn3_bundle("GN4_T3", second, {
            "left_side", "right_side", "top", "bottom", "front_left",
            "front_right", "shelf_horizontal",
        })
        self.assertEqual(len(bundle["model"]["modules"]), 2)
        self.assertEqual(len(bundle["rows"]), 14)
        self.assertEqual(len({row["piece_id"] for row in bundle["rows"]}), 14)
        self.assertEqual(bundle["model"]["depth_review"]["carcass_depth_mm"], 550)
        self.assertEqual(bundle["model"]["depth_review"]["assembled_external_depth_mm"], 568)
        self.assertEqual(bundle["cad"]["bounds_xyz_mm"], [1800, 2100, 568])

    def test_gn4_t4_natural_open_bathroom_without_countertop_generates_four_panels(self):
        owner_text = (
            "Mueble de baño independiente de 800 mm ancho, 700 mm alto y 450 mm "
            "fondo, MDP de 15 mm, laterales continuos, abierto, sin puertas, "
            "sin cajones, sin fondo y sin mesón, apoyado en el piso."
        )
        first = query(owner_text)
        self.assertIn("dimensions_mm", {item["field"] for item in first["questions"]})
        self.assertEqual(first["confirmed"]["countertop"], {"present": False})
        self.assertEqual(first["confirmed"]["drawers"], "none")
        self.assertEqual(first["confirmed"]["doors"], "none")
        answer_text = (
            "Confirmo las dimensiones exteriores: 800 mm de ancho, 700 mm de alto "
            "y 450 mm de profundidad."
        )
        second = query(answer_text, review_state=first["review_state"])
        self.assertEqual(second["nominal_draft_scope"], "OPEN_CABINET_REVIEW_ONLY")
        self.assertEqual(second["nominal_draft_piece_count"], 4)
        self.assertEqual(second["nominal_draft_blockers"], [])
        self.assertTrue(all(second[flag] is False for flag in FLAGS))
        record_gn4_flow("T4", [
            {"request": {"utterance": owner_text, "review_state": None,
                          "review_updates": [], "photo_observations": None},
             "response": first},
            {"request": {"utterance": answer_text,
                          "review_state": first["review_state"],
                          "review_updates": [], "photo_observations": None},
             "response": second},
        ])
        bundle = self.assert_gn3_bundle("GN4_T4", second, {
            "left_side", "right_side", "top", "bottom",
        }, expected_scope="OPEN_CABINET_REVIEW_ONLY")
        self.assertEqual(len(bundle["rows"]), 4)
        self.assertEqual(sum(row["role"] == "top" for row in bundle["rows"]), 1)
        self.assertNotIn("countertop", {row["role"] for row in bundle["rows"]})
        self.assertEqual(bundle["cad"]["bounds_xyz_mm"], [800, 700, 450])
        self.assertEqual(bundle["cad"]["manufacturing_holes"], [])

    def test_gn4_t5_wall_mounted_upper_is_concept_only_without_installation_claims(self):
        owner_text = (
            "Mueble superior para cocina, 1000 mm ancho × 700 mm alto × "
            "350 mm fondo, 2 puertas sobrepuestas, melamina de 15 mm, "
            "sin cajones, fijación a pared por instalador."
        )
        result = query(owner_text)
        self.assertEqual(result["nominal_draft_scope"], "CONCEPT_ONLY")
        self.assertEqual(result["nominal_draft_engine_status"], "CONCEPT_ONLY")
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["nominal_draft_piece_count"], 0)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))
        self.assertIs(result["can_generate_f7c"], False)
        self.assertIn("NOT_CERTIFIED_INSTALLATION",
                      result["nominal_draft_warnings"])
        self.assertIn("instalador", result["nominal_draft_next_question"])
        self.assertEqual(result["confirmed"]["project_type"], "gabinete")
        record_gn4_flow("T5", [{
            "request": {"utterance": owner_text, "review_state": None,
                         "review_updates": [], "photo_observations": None},
            "response": result,
        }])

    def test_gn4_t6_invalid_dimensions_negatives_cut_and_false_source_fail_closed(self):
        impossible_text = (
            "Gabinete de baño: dimensiones exteriores ancho 800 mm, alto 0 mm y "
            "profundidad 450 mm; MDP de 15 mm."
        )
        impossible = query(impossible_text)
        self.assertEqual(impossible["nominal_draft_piece_count"], 0)
        self.assertTrue(all(impossible[flag] is False for flag in FLAGS))

        closet_text = (
            "Clóset independiente, dimensiones exteriores ancho 1800 mm, alto "
            "2100 mm y profundidad 550 mm; melamina 18 mm, laterales continuos, "
            "dos módulos iguales, dos puertas sobrepuestas por módulo, una repisa "
            "por módulo a 700 mm desde la base interior, sin fondo trasero ni cajones."
        )
        first = query(closet_text)
        second = query("Directamente al piso y manijas visibles.",
                       review_state=first["review_state"])
        uneven_text = closet_text.replace("1800 mm", "1801 mm")
        uneven_first = query(uneven_text)
        uneven = query("Directamente al piso y manijas visibles.",
                       review_state=uneven_first["review_state"])
        self.assertIsNone(uneven["nominal_draft_request"])
        self.assertEqual(uneven["nominal_draft_piece_count"], 0)
        self.assertIn("internal_layout:equal_module_width_not_integral",
                      uneven["nominal_draft_blockers"])
        self.assertTrue(all(uneven[flag] is False for flag in FLAGS))
        cut = query("Genera un despiece listo para cortar.",
                    review_state=second["review_state"])
        self.assertIsNone(cut["nominal_draft_request"])
        self.assertEqual(cut["nominal_draft_piece_count"], 0)
        self.assertIn("authorization:fabrication_cutting_or_drilling_not_permitted",
                      cut["nominal_draft_blockers"])
        self.assertTrue(all(cut[flag] is False for flag in FLAGS))

        false_source_request = {
            "review_kind": "guided_design_v1",
            "utterance": "Revisa el apoyo.",
            "review_state": first["review_state"],
            "review_updates": [{
                "field": "support", "value": {"style": "wall_mounted"},
                "status": "confirmed", "source": "ENGINE_CALCULATED",
            }],
            "photo_observations": None,
        }
        with self.assertRaisesRegex(MaestroError,
                                    "Una fuente distinta de texto explícito no confirma"):
            carpinova_consultar(json.dumps(false_source_request, ensure_ascii=False))
        record_gn4_flow("T6", [
            {"request": {"utterance": impossible_text, "review_state": None,
                          "review_updates": [], "photo_observations": None},
             "response": impossible},
            {"request": {"utterance": uneven_text, "review_state": None,
                          "review_updates": [], "photo_observations": None},
             "response": uneven_first},
            {"request": {"utterance": "Directamente al piso y manijas visibles.",
                          "review_state": uneven_first["review_state"],
                          "review_updates": [], "photo_observations": None},
             "response": uneven},
            {"request": {"utterance": "Genera un despiece listo para cortar.",
                          "review_state": second["review_state"],
                          "review_updates": [], "photo_observations": None},
             "response": cut},
            {"request": false_source_request, "response": {
                "error": "Una fuente distinta de texto explícito no confirma decisiones."
            }},
        ])

    def test_gn3_r6_scope_mismatches_missing_owner_data_and_cut_request_block(self):
        complete = gn3_query(
            "R6",
            "Gabinete de cocina: dimensiones exteriores 800 mm de ancho, 700 mm "
            "de alto y 400 mm de profundidad; melamina de 15 mm, laterales "
            "continuos, separado de la pared, dos puertas sobrepuestas y una "
            "división horizontal, sin cajones, sin fondo, sin mesón y directamente "
            "al piso."
        )
        bad_width = kitchen_two_door_shelf_spec()
        bad_width["modules"][0]["width_mm"] = 790
        mismatch = gn3_query(
            "R6", "Revisa, sin corregir automáticamente el ancho.",
            review_state=complete["review_state"], nominal_detail_spec=bad_width,
        )
        self.assertIn("module_spec:module_width_sum_mismatch",
                      mismatch["nominal_draft_blockers"])
        self.assertIsNone(mismatch["nominal_draft_request"])
        self.assertEqual(mismatch["nominal_draft_piece_count"], 0)

        wrong_root = kitchen_two_door_shelf_spec()
        wrong_root["width_mm"] = 799
        dimension_mismatch = gn3_query(
            "R6", "Revisa la discrepancia de ancho sin corregirla.",
            review_state=complete["review_state"], nominal_detail_spec=wrong_root,
        )
        self.assertIn("module_spec:root_dimensions_mismatch_owner",
                      dimension_mismatch["nominal_draft_blockers"])
        self.assertIsNone(dimension_mismatch["nominal_draft_request"])

        closet_owner = gn3_query(
            "R6",
            "Clóset independiente, dimensiones exteriores de carcasa: ancho 1800 mm, "
            "alto 2100 mm y profundidad 550 mm; melamina de 18 mm, laterales "
            "continuos, cuatro puertas sobrepuestas con manijas, una repisa "
            "horizontal en cada módulo, sin fondo, sin cajones, sin mesón y "
            "directamente al piso."
        )
        overlapping_fronts = closet_two_module_spec()
        for module in overlapping_fronts["modules"]:
            module["fronts"].update({
                "left_reveal_mm": 0, "right_reveal_mm": 0, "center_gap_mm": 2,
            })
        overlap = gn3_query(
            "R6", "Revisa las hojas adyacentes, sin rediseñarlas.",
            review_state=closet_owner["review_state"],
            nominal_detail_spec=overlapping_fronts,
        )
        self.assertIsNone(overlap["nominal_draft_request"])
        self.assertEqual(overlap["nominal_draft_piece_count"], 0)
        self.assertTrue(any("solapan o tocan" in item for item in
                            overlap["nominal_draft_blockers"]))

        missing_owner = gn3_query(
            "R6",
            "Gabinete de cocina: dimensiones exteriores 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad; laterales continuos, separado de la pared, "
            "dos puertas sobrepuestas, una división horizontal, sin cajones, "
            "sin fondo, sin mesón y al piso."
        )
        missing_material = gn3_query(
            "R6", "Revisa la composición con material aún faltante.",
            review_state=missing_owner["review_state"],
            nominal_detail_spec=kitchen_two_door_shelf_spec(),
        )
        self.assertIn("material:explicit_confirmation_required",
                      missing_material["nominal_draft_blockers"])
        self.assertIsNone(missing_material["nominal_draft_request"])

        cut_request = gn3_query(
            "R6", "Hazlo cortable.", review_state=complete["review_state"],
            nominal_detail_spec=kitchen_two_door_shelf_spec(),
        )
        self.assertIn("authorization:fabrication_cutting_or_drilling_not_permitted",
                      cut_request["nominal_draft_blockers"])
        self.assertIsNone(cut_request["nominal_draft_request"])
        for result in (mismatch, dimension_mismatch, overlap, missing_material, cut_request):
            self.assertEqual(result["nominal_draft_piece_count"], 0)
            self.assertIs(result["can_generate_f7c"], False)
            self.assertTrue(all(result[flag] is False for flag in FLAGS))

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

    def test_complete_open_carcass_review_exposes_nominal_draft_request(self):
        result = query(
            "Gabinete: dimensiones exteriores 890 mm de ancho, 770 mm de alto y "
            "600 mm de profundidad; melamina de 15 mm, laterales continuos, "
            "separado de la pared, interior abierto, sin cajones, sin puertas, "
            "sin fondo y directamente al piso."
        )
        self.assertIn("nominal_draft_request", result)

    def test_multicomponent_request_a_returns_client_proposed_scope(self):
        first = query(
            "Gabinete de cocina: dimensiones exteriores 800 mm de ancho, 700 mm "
            "de alto y 400 mm de profundidad; melamina de 15 mm, laterales "
            "continuos, separado de la pared, dos puertas sobrepuestas y una "
            "división horizontal, sin cajones, sin fondo, sin mesón y directamente "
            "al piso."
        )
        state_before = deepcopy(first["review_state"])
        try:
            result = query(
                "Continuemos con la propuesta A.",
                review_state=first["review_state"],
                nominal_detail_spec=kitchen_two_door_shelf_spec(),
            )
        except MaestroError as exc:
            self.fail(f"guided router rejected client-proposed details: {exc}")
        self.assertEqual(
            result.get("nominal_draft_scope"),
            "CLIENT_PROPOSED_MULTICOMPONENT_REVIEW_ONLY",
        )
        self.assertEqual(result["nominal_draft_piece_count"], 7)
        self.assertEqual(result["nominal_draft_request"]["module_spec"],
                         kitchen_two_door_shelf_spec())
        self.assertEqual(result["nominal_draft_provenance"],
                         "CLIENT_PROPOSED_NOT_OWNER_APPROVED")
        self.assertEqual(result["nominal_draft_blockers"], [])
        self.assertEqual(first["review_state"], state_before)
        self.assertNotIn("nominal_detail_spec", result["review_state"])
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_bathroom_owner_sentence_keeps_carcass_height_separate_from_leg_height(self):
        result = query(
            "Gabinete de baño: dimensiones exteriores de la carcasa 800 mm de ancho, "
            "700 mm de alto y 400 mm de profundidad; melamina de 15 mm, laterales "
            "continuos, separado de la pared, interior abierto, sin cajones, sin "
            "puertas, sin fondo y patas de 100 mm de alto."
        )
        self.assertEqual(result["confirmed"].get("dimensions_mm"), {
            "width_mm": 800, "height_mm": 700, "depth_mm": 400,
        })
        self.assertEqual(result["confirmed"]["support"], {
            "style": "legs", "height_mm": 100,
        })
        self.assertNotIn("dimensions_mm", result["proposed"])

    def test_multicomponent_request_b_keeps_countertop_and_support_as_review_only(self):
        first = query(
            "Gabinete de baño: dimensiones exteriores de la carcasa 800 mm de ancho, "
            "700 mm de alto y 400 mm de profundidad; melamina de 15 mm, laterales "
            "continuos, separado de la pared, interior abierto, sin cajones, sin "
            "puertas, sin fondo y patas de 100 mm de alto."
        )
        second = query(
            "El mesón tiene 820 mm de ancho y 440 mm de profundidad y 30 mm de espesor.",
            review_state=first["review_state"],
        )
        try:
            result = query(
                "Continuemos con la propuesta nominal.",
                review_state=second["review_state"],
                nominal_detail_spec=bathroom_countertop_legs_spec(),
            )
        except MaestroError as exc:
            self.fail(f"guided router rejected client-proposed details: {exc}")
        self.assertEqual(
            result.get("nominal_draft_scope"),
            "CLIENT_PROPOSED_MULTICOMPONENT_REVIEW_ONLY",
        )
        self.assertEqual(result["nominal_draft_piece_count"], 4)
        self.assertIn("COUNTERTOP_MATERIAL_NOT_OWNER_APPROVED",
                      result["nominal_draft_warnings"])
        self.assertIn("COUNTERTOP_SUPPORT_NOT_STRUCTURALLY_VERIFIED",
                      result["nominal_draft_warnings"])
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_multicomponent_specs_reject_scope_mismatches_without_fallback(self):
        a_first = query(
            "Gabinete de cocina: dimensiones exteriores 800 mm de ancho, 700 mm "
            "de alto y 400 mm de profundidad; melamina de 15 mm, laterales "
            "continuos, separado de la pared, dos puertas sobrepuestas y una "
            "división horizontal, sin cajones, sin fondo, sin mesón y directamente "
            "al piso."
        )
        a_state = a_first["review_state"]
        a_mutations = (
            ("root width", lambda s: s.update(width_mm=790)),
            ("module width", lambda s: s["modules"][0].update(width_mm=790)),
            ("body material", lambda s: s["modules"][0].update(material_id="MDP_15")),
            ("thickness", lambda s: s["modules"][0].update(panel_thickness_mm=14)),
            ("construction", lambda s: s["modules"][0].update(construction="top_bottom_full")),
            ("installation", lambda s: s.update(installation="wall_mounted")),
            ("door count", lambda s: s["modules"][0]["fronts"].update(leaf_count=1)),
            ("front style", lambda s: s["modules"][0]["fronts"].update(style="inset")),
            ("missing divider", lambda s: s["modules"][0].pop("horizontal_divider")),
            ("back", lambda s: s["modules"][0].update(back="inset_full")),
            ("drawers", lambda s: s["modules"][0].update(drawers={"count": 1})),
            ("vertical divider", lambda s: s["modules"][0].update(vertical_divider={})),
            ("fronts omitted", lambda s: s["modules"][0].update(fronts="none")),
            ("second module", lambda s: s["modules"].append(deepcopy(s["modules"][0]))),
            ("unknown module key", lambda s: s["modules"][0].update(extra=True)),
            ("wrong type", lambda s: s.update(type="cabinet")),
        )
        for label, mutate in a_mutations:
            with self.subTest(scenario="A", mismatch=label):
                spec = kitchen_two_door_shelf_spec()
                mutate(spec)
                result = query(
                    "Revisemos la propuesta A.", review_state=a_state,
                    nominal_detail_spec=spec,
                )
                self.assertIsNone(result["nominal_draft_request"])
                self.assertEqual(result["nominal_draft_piece_count"], 0)
                self.assertEqual(result["nominal_draft_scope"],
                                 "BLOCKED_UNSUPPORTED_OR_INCOMPLETE")
                self.assertTrue(all(result[flag] is False for flag in FLAGS))

        b_first = query(
            "Gabinete de baño: dimensiones exteriores de la carcasa 800 mm de ancho, "
            "700 mm de alto y 400 mm de profundidad; melamina de 15 mm, laterales "
            "continuos, separado de la pared, interior abierto, sin cajones, sin "
            "puertas, sin fondo y patas de 100 mm de alto."
        )
        b_second = query(
            "El mesón tiene 820 mm de ancho y 440 mm de profundidad y 30 mm de espesor.",
            review_state=b_first["review_state"],
        )
        b_state = b_second["review_state"]
        b_mutations = (
            ("root width", lambda s: s.update(width_mm=799)),
            ("root height", lambda s: s.update(height_mm=701)),
            ("root depth", lambda s: s.update(depth_mm=401)),
            ("module width", lambda s: s["modules"][0].update(width_mm=790)),
            ("body material", lambda s: s["modules"][0].update(material_id="MDP_15")),
            ("body thickness", lambda s: s["modules"][0].update(panel_thickness_mm=14)),
            ("construction", lambda s: s["modules"][0].update(construction="top_bottom_full")),
            ("installation", lambda s: s.update(installation="wall_mounted")),
            ("application", lambda s: s.update(application="kitchen")),
            ("countertop width", lambda s: s["modules"][0]["countertop"].update(width_mm=821)),
            ("countertop depth", lambda s: s["modules"][0]["countertop"].update(depth_mm=441)),
            ("countertop thickness", lambda s: s["modules"][0]["countertop"].update(thickness_mm=29)),
            ("countertop material", lambda s: s["modules"][0]["countertop"].update(material_id="MDF_RH_30")),
            ("overhang closure", lambda s: s["modules"][0]["countertop"].update(left_overhang_mm=11)),
            ("support height", lambda s: s["modules"][0]["support_concept"].update(support_height_mm=90)),
            ("overall height", lambda s: s["modules"][0]["support_concept"].update(overall_height_mm=829)),
            ("support role", lambda s: s["modules"][0].update(support="wall")),
            ("back", lambda s: s["modules"][0].update(back="inset_full")),
            ("drawers", lambda s: s["modules"][0].update(drawers={"count": 1})),
            ("fronts", lambda s: s["modules"][0].update(fronts={"style": "overlay"})),
            ("vertical divider", lambda s: s["modules"][0].update(vertical_divider={})),
            ("second module", lambda s: s["modules"].append(deepcopy(s["modules"][0]))),
            ("unknown root key", lambda s: s.update(untrusted=True)),
        )
        for label, mutate in b_mutations:
            with self.subTest(scenario="B", mismatch=label):
                spec = bathroom_countertop_legs_spec()
                mutate(spec)
                result = query(
                    "Revisemos la propuesta B.", review_state=b_state,
                    nominal_detail_spec=spec,
                )
                self.assertIsNone(result["nominal_draft_request"])
                self.assertEqual(result["nominal_draft_piece_count"], 0)
                self.assertEqual(result["nominal_draft_scope"],
                                 "BLOCKED_UNSUPPORTED_OR_INCOMPLETE")
                self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_detail_spec_null_preserves_legacy_handoff_and_historical_photo_warning(self):
        owner_text = (
            "Gabinete: dimensiones exteriores 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad; melamina de 15 mm, laterales continuos, "
            "separado de la pared, interior abierto, sin cajones, sin puertas, "
            "sin fondo, sin mesón y directamente al piso."
        )
        observation = {
            "visible_features": ["un estante"], "ambiguous_or_occluded": [],
            "dimensions_from_user_only": {}, "questions": [],
        }
        first = query(owner_text, photo_observations=observation)
        state_before = deepcopy(first["review_state"])
        result = query(
            "Continuemos con la revisión.", review_state=first["review_state"],
            nominal_detail_spec=None,
        )
        self.assertEqual(first["review_state"], state_before)
        self.assertEqual(result["nominal_draft_scope"], "OPEN_CABINET_REVIEW_ONLY")
        self.assertEqual(result["nominal_draft_request"]["module_spec"]["width_mm"], 800)
        self.assertIn("PHOTO_NOT_USED_FOR_GEOMETRY", result["nominal_draft_warnings"])
        self.assertIsNone(result["photo_input"])
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_optional_detail_field_rejects_bad_types(self):
        payload = {
            "review_kind": "guided_design_v1", "utterance": "Gabinete.",
            "review_state": None, "review_updates": [], "photo_observations": None,
            "nominal_detail_spec": "not-an-object",
        }
        with self.assertRaisesRegex(MaestroError, "nominal_detail_spec debe ser objeto"):
            carpinova_consultar(json.dumps(payload))

    def test_multicomponent_drafts_match_all_five_generated_artifacts(self):
        a_first = query(
            "Gabinete de cocina: dimensiones exteriores 800 mm de ancho, 700 mm "
            "de alto y 400 mm de profundidad; melamina de 15 mm, laterales "
            "continuos, separado de la pared, dos puertas sobrepuestas y una "
            "división horizontal, sin cajones, sin fondo, sin mesón y directamente "
            "al piso."
        )
        a_review = query(
            "Continuemos con la propuesta A.", review_state=a_first["review_state"],
            nominal_detail_spec=kitchen_two_door_shelf_spec(),
        )
        b_first = query(
            "Gabinete de baño: dimensiones exteriores de la carcasa 800 mm de ancho, "
            "700 mm de alto y 400 mm de profundidad; melamina de 15 mm, laterales "
            "continuos, separado de la pared, interior abierto, sin cajones, sin "
            "puertas, sin fondo y patas de 100 mm de alto."
        )
        b_second = query(
            "El mesón tiene 820 mm de ancho y 440 mm de profundidad y 30 mm de espesor.",
            review_state=b_first["review_state"],
        )
        b_review = query(
            "Continuemos con la propuesta B.", review_state=b_second["review_state"],
            nominal_detail_spec=bathroom_countertop_legs_spec(),
        )
        cases = (
            ("A", a_review, 7, {"left_side", "right_side", "top", "bottom",
                                 "front_left", "front_right", "shelf_horizontal"},
             [800, 700, 415]),
            ("B", b_review, 4, {"left_side", "right_side", "bottom", "countertop"},
             [820, 830, 440]),
        )
        optional_render = (
            importlib.util.find_spec("resvg_py") is not None
            and importlib.util.find_spec("PIL") is not None
        )
        evidence_root = os.environ.get("CARPINOVA_GN2_EVIDENCE_ROOT")
        response_evidence = None
        if evidence_root:
            response_evidence = Path(evidence_root) / "GN2_STRUCTURED_RESPONSES.json"
            structured_responses = {
                "A": {"owner_turn": a_first, "detail_review": a_review},
                "B": {
                    "owner_turn": b_first, "countertop_turn": b_second,
                    "detail_review": b_review,
                },
            }
            with response_evidence.open("x", encoding="utf-8") as stream:
                json.dump(structured_responses, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
        all_case_evidence = []
        for letter, review, expected_count, expected_roles, expected_bounds in cases:
            with self.subTest(case=letter):
                project_name = f"GN2_MULTICOMPONENT_{letter}"
                self.assertEqual(review["nominal_draft_scope"],
                                 "CLIENT_PROPOSED_MULTICOMPONENT_REVIEW_ONLY")
                self.assertEqual(review["nominal_draft_piece_count"], expected_count)
                self.assertTrue(all(review[flag] is False for flag in FLAGS))
                self.assertEqual(review["piece_count"], 0)
                self.assertIs(review["can_generate_f7c"], False)
                with tempfile.TemporaryDirectory(prefix=f"carpinova-gn2-{letter}-") as root:
                    output_root = Path(root)
                    destination = output_root / project_name
                    previous = os.environ.get("CARPINOVA_OUTPUT_ROOT")
                    os.environ["CARPINOVA_OUTPUT_ROOT"] = str(output_root)
                    try:
                        generated = carpinova_generar_borrador(
                            solicitud_json=json.dumps(review["nominal_draft_request"]),
                            proyecto=project_name, incluir_planos=optional_render,
                        )
                        if response_evidence:
                            structured_responses[letter]["generator_response"] = generated
                            with response_evidence.open("w", encoding="utf-8") as stream:
                                json.dump(structured_responses, stream, indent=2,
                                          ensure_ascii=False)
                                stream.write("\n")
                        self.assertEqual(generated["status"], "DRAFT_NOT_FOR_CUTTING")
                        self.assertEqual(generated["piece_count"], expected_count)
                        self.assertEqual(generated["geometry_sha256"],
                                         review["nominal_draft_geometry_sha256"])
                        self.assertTrue(all(generated[flag] is False for flag in FLAGS))
                        cad = verify_pilot_bundle(destination)
                        names = (
                            "maestro-review.json", "front-review.svg", "parts-review.csv",
                            "cad-exchange.json", "manifest.json",
                        )
                        artifact_hashes = []
                        for name in names:
                            raw = (destination / name).read_bytes()
                            artifact_hashes.append({
                                "path": name, "bytes": len(raw),
                                "sha256": hashlib.sha256(raw).hexdigest(),
                            })
                        answer = json.loads((destination / "maestro-review.json").read_text(
                            encoding="utf-8"))
                        manifest = json.loads((destination / "manifest.json").read_text(
                            encoding="utf-8"))
                        saved_cad = json.loads((destination / "cad-exchange.json").read_text(
                            encoding="utf-8"))
                        rows = list(csv.DictReader((destination / "parts-review.csv").read_text(
                            encoding="utf-8").splitlines()))
                        svg = (destination / "front-review.svg").read_text(encoding="utf-8")
                        ET.fromstring(svg)
                        model = answer["modular"]
                        pieces = model["parts"]
                        ids = {piece["piece_id"] for piece in pieces}
                        self.assertEqual(len(ids), expected_count)
                        self.assertEqual({piece["role"] for piece in pieces}, expected_roles)
                        self.assertEqual({box["piece_id"] for box in cad["boxes"]}, ids)
                        self.assertEqual({box["role"] for box in cad["boxes"]}, expected_roles)
                        self.assertEqual(cad["bounds_xyz_mm"], expected_bounds)
                        self.assertEqual(saved_cad, cad)
                        self.assertEqual(manifest["geometry_sha256"], generated["geometry_sha256"])
                        self.assertEqual(manifest["piece_count"], expected_count)
                        self.assertEqual({row["piece_id"] for row in rows}, ids)
                        self.assertEqual(len(rows), expected_count)
                        self.assertTrue({
                            "maestro-review.json", "front-review.svg", "parts-review.csv",
                            "cad-exchange.json", "manifest.json",
                        }.issubset({path.name for path in destination.iterdir()}))
                        self.assertTrue(all(answer[flag] is False and model[flag] is False
                                            and manifest[flag] is False for flag in FLAGS))
                        self.assertTrue(all(cad[flag] is False for flag in (
                            "fabrication_ready", "cutting_ready", "drilling_ready",
                        )))
                        if letter == "B":
                            self.assertEqual(model["carcass_dimensions_mm"], {
                                "width": 800, "height": 700, "depth": 400,
                            })
                            self.assertNotIn("top", {piece["role"] for piece in pieces})
                            self.assertNotIn("support_leg_concept",
                                             {piece["role"] for piece in pieces})
                            self.assertEqual(model["assembly_review"]["physical_support_parts"],
                                             "NOT_MODELED")
                            self.assertEqual(
                                model["assembly_review"]["carcass_dimensions_xyz_mm"],
                                [800, 700, 400],
                            )
                            self.assertEqual(model["assembly_review"]["support_height_mm"], 100)
                            self.assertEqual(
                                model["modules"][0]["support_review"]["overall_height_mm"],
                                830,
                            )
                        if letter == "A":
                            self.assertEqual(model["dimensions_mm"], {
                                "width": 800, "height": 700, "depth": 400,
                            })
                            self.assertIn("shelf_horizontal", {piece["role"] for piece in pieces})
                            self.assertEqual({piece["role"] for piece in pieces
                                              if piece["role"].startswith("front_")},
                                             {"front_left", "front_right"})
                        if evidence_root:
                            fixture = Path(evidence_root) / f"fixture_{letter}"
                            fixture.mkdir(parents=True, exist_ok=False)
                            for name in names:
                                (fixture / name).write_bytes((destination / name).read_bytes())
                        all_case_evidence.append({
                            "case": letter, "project": project_name,
                            "status": review["status"],
                            "scope": review["nominal_draft_scope"],
                            "piece_count": expected_count, "roles": sorted(expected_roles),
                            "bounds_xyz_mm": cad["bounds_xyz_mm"],
                            "geometry_sha256": generated["geometry_sha256"],
                            "artifacts": artifact_hashes,
                            "verified": True,
                        })
                    finally:
                        if previous is None:
                            os.environ.pop("CARPINOVA_OUTPUT_ROOT", None)
                        else:
                            os.environ["CARPINOVA_OUTPUT_ROOT"] = previous
        if evidence_root:
            summary_path = Path(evidence_root) / "GN2_CASE_ARTIFACTS.json"
            with summary_path.open("x", encoding="utf-8") as stream:
                json.dump(all_case_evidence, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
        print("GN2_CASE_ARTIFACTS=" + json.dumps({
            "cases": all_case_evidence,
            "render_status": "RENDERED" if optional_render else "RENDER_BLOCKED_ENV",
            "native_cad": "NOT_CALLED",
        }, sort_keys=True))

    def test_nominal_open_cabinet_handoff_is_dynamic_and_keeps_wizard_review_only(self):
        cases = (
            (
                "Gabinete: dimensiones exteriores 800 mm de ancho, 700 mm de alto y "
                "400 mm de profundidad; melamina de 15 mm, laterales continuos, "
                "separado de la pared, interior abierto, sin cajones, sin puertas, "
                "sin fondo, sin mesón y directamente al piso.",
                [800, 700, 400], "MELAMINA_15", "sides_full",
            ),
            (
                "Gabinete: dimensiones exteriores 650 mm de ancho, 900 mm de alto y "
                "350 mm de profundidad; MDF RH de 18 mm, tapa y base entre laterales, "
                "separado de la pared, interior abierto, sin cajones, sin puertas, "
                "sin fondo, sin mesón y directamente al piso.",
                [650, 900, 350], "MDF_RH_18", "top_bottom_full",
            ),
        )
        for utterance, dimensions, material_id, construction in cases:
            with self.subTest(dimensions=dimensions):
                result = query(utterance)
                self.assertEqual(result["nominal_draft_scope"], "OPEN_CABINET_REVIEW_ONLY")
                request = result["nominal_draft_request"]
                self.assertEqual(request["action"], "modular")
                spec = request["module_spec"]
                self.assertEqual(
                    [spec["width_mm"], spec["height_mm"], spec["depth_mm"]],
                    dimensions,
                )
                self.assertEqual(spec["installation"], "freestanding")
                module = spec["modules"][0]
                self.assertEqual(module["material_id"], material_id)
                self.assertEqual(module["construction"], construction)
                self.assertEqual(result["nominal_draft_piece_count"], 4)
                self.assertRegex(result["nominal_draft_geometry_sha256"], r"^[0-9a-f]{64}$")
                self.assertEqual(
                    result["nominal_draft_provenance"],
                    "CLIENT_DECLARED_OWNER_TEXT_NOT_AUTHENTICATED",
                )
                self.assertEqual(result["piece_count"], 0)
                self.assertIs(result["can_generate_f7c"], False)
                self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_open_cabinet_handoff_blocks_unmodeled_components_and_unconfirmed_choices(self):
        base = (
            "Gabinete: dimensiones exteriores 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad; melamina de 15 mm, laterales continuos, "
            "separado de la pared, interior abierto, sin cajones, sin puertas, "
            "sin fondo, sin mesón y directamente al piso."
        )
        cases = (
            (base.replace("sin puertas", "dos puertas sobrepuestas"), "doors:"),
            (base.replace("interior abierto", "una división horizontal"), "internal_layout:"),
            (base.replace("sin cajones", "un cajón"), "drawers:"),
            (base.replace("sin fondo", "fondo pendiente"), "back:"),
            (base.replace("sin mesón", "lleva mesón"), "countertop:"),
            (base.replace("directamente al piso", "suspendido"), "support:"),
            (base.replace("separado de la pared, ", ""), "wall_contact:"),
            (base.replace("sin puertas", "sin puertas, con manijas visibles"), "opening_intent:"),
        )
        for utterance, expected_blocker in cases:
            with self.subTest(blocker=expected_blocker):
                result = query(utterance)
                self.assertIsNone(result["nominal_draft_request"])
                self.assertEqual(
                    result["nominal_draft_scope"],
                    "BLOCKED_UNSUPPORTED_OR_INCOMPLETE",
                )
                self.assertEqual(result["nominal_draft_piece_count"], 0)
                self.assertTrue(any(
                    item.startswith(expected_blocker)
                    for item in result["nominal_draft_blockers"]
                ), result["nominal_draft_blockers"])
                self.assertLessEqual(len(result["questions"]), 3)
                self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_photo_never_supplies_geometry_and_owner_text_can_stand_alone(self):
        observation = {
            "visible_features": ["dos puertas", "una repisa"],
            "ambiguous_or_occluded": ["interior no visible"],
            "dimensions_from_user_only": {},
            "questions": [],
        }
        photo_only = query(
            "Quiero revisar un gabinete desde una foto.",
            photo_observations=observation,
        )
        self.assertIsNone(photo_only["nominal_draft_request"])
        self.assertIn("dimensions_mm:explicit_confirmation_required",
                      photo_only["nominal_draft_blockers"])
        self.assertIn("PHOTO_NOT_USED_FOR_GEOMETRY", photo_only["nominal_draft_warnings"])
        self.assertTrue(any("does not reproduce or validate" in item
                            for item in photo_only["nominal_draft_warnings"]))

        owner_text = (
            "Gabinete: dimensiones exteriores 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad; melamina de 15 mm, laterales continuos, "
            "separado de la pared, interior abierto, sin cajones, sin puertas, "
            "sin fondo, sin mesón y directamente al piso."
        )
        independent = query(owner_text, photo_observations=observation)
        self.assertIsNotNone(independent["nominal_draft_request"])
        self.assertIn("PHOTO_NOT_USED_FOR_GEOMETRY", independent["nominal_draft_warnings"])
        self.assertEqual(
            independent["nominal_draft_request"]["module_spec"]["width_mm"], 800,
        )

    def test_engine_proposed_material_cannot_satisfy_owner_confirmation(self):
        result = query(
            "Gabinete: dimensiones exteriores 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad; espesor del tablero 15 mm, laterales continuos, "
            "separado de la pared, interior abierto, sin cajones, sin puertas, "
            "sin fondo, sin mesón y directamente al piso.",
            review_updates=[{
                "field": "material", "value": "mdf", "status": "proposed",
                "source": "ENGINE_CALCULATED",
            }],
        )
        self.assertIsNone(result["nominal_draft_request"])
        self.assertIn("material:OWNER_TEXT_required", result["nominal_draft_blockers"])
        self.assertEqual(result["proposed"].get("material"), "mdf")

    def test_review_state_is_not_mutated_and_finish_is_not_claimed_as_applied(self):
        first = query(
            "Gabinete: dimensiones exteriores 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad; melamina de 15 mm, laterales continuos."
        )
        before = deepcopy(first["review_state"])
        updated = query(
            "Separado de la pared, interior abierto, sin cajones, sin puertas, "
            "sin fondo, sin mesón y directamente al piso.",
            review_state=first["review_state"],
            review_updates=[{
                "field": "finish", "value": "acabado mate", "status": "proposed",
                "source": "OWNER_TEXT",
            }],
        )
        self.assertEqual(first["review_state"], before)
        self.assertIsNotNone(updated["nominal_draft_request"])
        self.assertIn("FINISH_NOT_REPRESENTED_IN_GEOMETRY.",
                      updated["nominal_draft_warnings"])

    def test_nominal_request_generates_one_verified_review_bundle_from_mcp_router(self):
        utterance = (
            "Gabinete: dimensiones exteriores 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad; melamina de 15 mm, laterales continuos, "
            "separado de la pared, interior abierto, sin cajones, sin puertas, "
            "sin fondo, sin mesón y directamente al piso."
        )
        review = query(utterance)
        request = review["nominal_draft_request"]
        self.assertIsNotNone(request)
        project_name = "GN1_OPEN_CABINET_E2E"
        optional_render = (
            importlib.util.find_spec("resvg_py") is not None
            and importlib.util.find_spec("PIL") is not None
        )
        with tempfile.TemporaryDirectory(prefix="carpinova-gn1-") as root:
            output_root = Path(root)
            destination = output_root / project_name
            self.assertTrue(output_root.is_dir())
            self.assertFalse(destination.exists())
            previous = os.environ.get("CARPINOVA_OUTPUT_ROOT")
            os.environ["CARPINOVA_OUTPUT_ROOT"] = str(output_root)
            try:
                generated = carpinova_generar_borrador(
                    solicitud_json=json.dumps(request),
                    proyecto=project_name,
                    incluir_planos=optional_render,
                )
                self.assertEqual(generated["status"], "DRAFT_NOT_FOR_CUTTING")
                self.assertEqual(generated["geometry_sha256"],
                                 review["nominal_draft_geometry_sha256"])
                self.assertEqual(generated["piece_count"], 4)
                self.assertTrue(all(generated[flag] is False for flag in FLAGS))
                cad = verify_pilot_bundle(destination)
                manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
                saved_cad = json.loads((destination / "cad-exchange.json").read_text(encoding="utf-8"))
                rows = list(csv.DictReader(
                    (destination / "parts-review.csv").read_text(encoding="utf-8").splitlines()
                ))
                svg = (destination / "front-review.svg").read_text(encoding="utf-8")
                ET.fromstring(svg)
                self.assertEqual(manifest["geometry_sha256"], saved_cad["geometry_sha256"])
                self.assertEqual(manifest["geometry_sha256"], cad["geometry_sha256"])
                self.assertEqual(manifest["geometry_sha256"], generated["geometry_sha256"])
                self.assertEqual(manifest["piece_count"], 4)
                self.assertEqual(len(rows), 4)
                self.assertEqual(
                    {row["piece_id"] for row in rows},
                    {box["piece_id"] for box in saved_cad["boxes"]},
                )
                self.assertIn("<svg", svg)
                self.assertEqual(manifest["fabrication_ready"], False)
                read_manifest = carpinova_leer_entregable(project_name, "manifest.json")
                self.assertEqual(read_manifest["contenido"],
                                 (destination / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    review["piece_count"], 0,
                    "the conversation wizard itself remains piece-free",
                )
                if optional_render:
                    png = destination / "lamina" / "three-views.png"
                    pdf = destination / "lamina" / "three-views.pdf"
                    self.assertTrue(png.is_file())
                    self.assertTrue(pdf.is_file())
                    self.assertTrue(png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
                    self.assertTrue(pdf.read_bytes().startswith(b"%PDF-"))
                artifact_names = (
                    "manifest.json", "cad-exchange.json", "parts-review.csv",
                    "front-review.svg",
                )
                artifact_evidence = []
                for name in artifact_names:
                    raw = (destination / name).read_bytes()
                    artifact_evidence.append({
                        "path": name, "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    })
                print("GN1_E2E_ARTIFACTS=" + json.dumps({
                    "geometry_sha256": generated["geometry_sha256"],
                    "piece_count": generated["piece_count"],
                    "verified": True,
                    "render_status": "RENDERED" if optional_render else "RENDER_ENV_BLOCKED",
                    "native_cad": "NO_NATIVE_CAD",
                    "files": artifact_evidence,
                }, sort_keys=True))
            finally:
                if previous is None:
                    os.environ.pop("CARPINOVA_OUTPUT_ROOT", None)
                else:
                    os.environ["CARPINOVA_OUTPUT_ROOT"] = previous

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


class GN5NaturalF6AcceptanceTests(unittest.TestCase):
    def ask(self, case_id: str, utterance: str, review_state=None) -> dict:
        payload = {
            "review_kind": "guided_design_v1", "utterance": utterance,
            "review_state": review_state, "review_updates": [],
            "photo_observations": None,
        }
        self.assertNotIn("nominal_detail_spec", payload)
        response = carpinova_consultar(json.dumps(payload, ensure_ascii=False))
        record_gn3_tool(case_id, "carpinova_consultar", {
            "solicitud_json": json.dumps(payload, ensure_ascii=False),
            "decoded_solicitud_json": payload,
        }, response)
        return response

    def assert_bundle(self, case_id: str, review: dict,
                      expected_roles: set[str]) -> dict:
        self.assertIsNotNone(review["nominal_draft_request"])
        self.assertEqual(review["nominal_draft_blockers"], [])
        self.assertGreater(review["nominal_draft_piece_count"], 0)
        self.assertEqual(review["piece_count"], 0)
        self.assertIs(review["can_generate_f7c"], False)
        self.assertTrue(all(review[flag] is False for flag in FLAGS))
        request = review["nominal_draft_request"]
        self.assertEqual(request["action"], "modular")
        self.assertNotIn("nominal_detail_spec", request)

        evidence_root = os.environ.get("CARPINOVA_GN5_ARTIFACT_ROOT")
        transcript_root = os.environ.get("CARPINOVA_GN3_EVIDENCE_ROOT")
        self.assertTrue(evidence_root)
        self.assertTrue(transcript_root)
        with tempfile.TemporaryDirectory(prefix=f"carpinova-gn5-{case_id}-") as root:
            output_root = Path(root)
            previous = os.environ.get("CARPINOVA_OUTPUT_ROOT")
            os.environ["CARPINOVA_OUTPUT_ROOT"] = str(output_root)
            project = f"GN5_{case_id.upper()}"
            try:
                generated = carpinova_generar_borrador(
                    solicitud_json=json.dumps(request, ensure_ascii=False),
                    proyecto=project, incluir_planos=False,
                )
            finally:
                if previous is None:
                    os.environ.pop("CARPINOVA_OUTPUT_ROOT", None)
                else:
                    os.environ["CARPINOVA_OUTPUT_ROOT"] = previous
            record_gn3_tool(case_id, "carpinova_generar_borrador", {
                "solicitud_json": json.dumps(request, ensure_ascii=False),
                "decoded_solicitud_json": request, "proyecto": project,
                "incluir_planos": False,
            }, generated)
            destination = output_root / project
            names = (
                "maestro-review.json", "cad-exchange.json",
                "parts-review.csv", "front-review.svg", "manifest.json",
            )
            self.assertTrue(all((destination / name).is_file() for name in names))
            answer = json.loads((destination / "maestro-review.json").read_text(
                encoding="utf-8"))
            manifest = json.loads((destination / "manifest.json").read_text(
                encoding="utf-8"))
            saved_cad = json.loads((destination / "cad-exchange.json").read_text(
                encoding="utf-8"))
            rows = list(csv.DictReader((destination / "parts-review.csv").read_text(
                encoding="utf-8").splitlines()))
            ET.fromstring((destination / "front-review.svg").read_text(encoding="utf-8"))
            model = answer["modular"]
            parts = model["parts"]
            ids = [part["piece_id"] for part in parts]
            roles = {part["role"] for part in parts}
            boxes = saved_cad["boxes"]
            cad_ids = [box["piece_id"] for box in boxes]
            csv_ids = [row["piece_id"] for row in rows]
            geometry_sha = review["nominal_draft_geometry_sha256"]
            self.assertEqual(roles, expected_roles)
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(set(ids), set(cad_ids))
            self.assertEqual(set(ids), set(csv_ids))
            self.assertEqual(generated["geometry_sha256"], geometry_sha)
            self.assertEqual(saved_cad["geometry_sha256"], geometry_sha)
            self.assertEqual(manifest["geometry_sha256"], geometry_sha)
            self.assertTrue(all(answer[flag] is False and model[flag] is False
                                and manifest[flag] is False for flag in FLAGS))
            self.assertTrue(all(saved_cad[flag] is False for flag in (
                "fabrication_ready", "cutting_ready", "drilling_ready",
            )))
            self.assertEqual(saved_cad["manufacturing_holes"], [])
            self.assertEqual(len(parts), review["nominal_draft_piece_count"])

            destination_evidence = Path(evidence_root) / case_id
            destination_evidence.mkdir(parents=True, exist_ok=False)
            for name in names:
                shutil.copyfile(destination / name, destination_evidence / name)
            return {"model": model, "cad": saved_cad, "manifest": manifest,
                    "rows": rows, "answer": answer, "generated": generated}

    def test_gn5_c1_kitchen_doors_shelf_overlay_and_depth_gate(self):
        utterance = (
            "Quiero un gabinete de cocina independiente. La carcasa mide 800 mm de "
            "ancho, 700 mm de alto y 400 mm de fondo. Melamina de 15 mm, laterales "
            "continuos, dos puertas sobrepuestas con manijas, una repisa horizontal, "
            "sin cajones, sin fondo trasero, sin mesón, directo al piso y separado "
            "de la pared."
        )
        first = self.ask("C1", utterance)
        self.assertEqual(first["confirmed"]["use"], "kitchen")
        self.assertEqual(first["nominal_draft_request"]["module_spec"]["application"], "kitchen")
        self.assertEqual(first["nominal_draft_piece_count"], 7)
        assumptions = first["nominal_draft_assumptions"]
        self.assertTrue(all(item["source"] == "ENGINE_PROPOSED_NOT_OWNER_APPROVED"
                            for item in assumptions))
        bundle = self.assert_bundle("C1", first, {
            "left_side", "right_side", "top", "bottom", "front_left",
            "front_right", "shelf_horizontal",
        })
        self.assertEqual(bundle["model"]["depth_review"]["assembled_external_depth_mm"], 415)

        push = self.ask("C1_PUSH", "Prefiero push en vez de manijas.", first["review_state"])
        self.assertEqual(push["nominal_draft_geometry_sha256"],
                         first["nominal_draft_geometry_sha256"])
        self.assertTrue(all(item["opening_system"] == "push_to_open"
                            for item in push["nominal_draft_opening_review"]["elements"]))
        self.assertFalse(push["nominal_draft_opening_review"]["hardware_selected"])

        max_text = utterance.replace(
            "400 mm de fondo.",
            "400 mm de fondo; la profundidad exterior máxima montada aceptable es 400 mm.",
        )
        max_depth = self.ask("C1_MAX_DEPTH", max_text)
        self.assertEqual(max_depth["nominal_draft_engine_status"], "NEEDS_DEPTH_REVISION")
        self.assertIsNone(max_depth["nominal_draft_request"])
        self.assertEqual(max_depth["nominal_draft_piece_count"], 0)
        self.assertEqual(max_depth["piece_count"], 0)
        self.assertTrue(all(max_depth[flag] is False for flag in FLAGS))
        self.assertIn("415 mm", max_depth["nominal_draft_next_question"])

        cut = self.ask("C1_CUT_ATTEMPT", "Déjalo listo para cortar.", first["review_state"])
        self.assertIsNone(cut["nominal_draft_request"])
        self.assertEqual(cut["piece_count"], 0)
        self.assertEqual(cut["nominal_draft_piece_count"], 0)
        self.assertTrue(all(cut[flag] is False for flag in FLAGS))
        self.assertTrue(any("authorization:" in item
                            for item in cut["nominal_draft_blockers"]))

    def test_gn5_c2_bathroom_keeps_carcass_total_and_countertop_separate(self):
        utterance = (
            "Diseña un gabinete de baño independiente y abierto, sin puertas ni cajones "
            "ni fondo trasero. Carcasa de 800 mm ancho, 700 mm alto y 400 mm de fondo, "
            "cuerpo MDF RH de 15 mm, laterales continuos. Mesón aparte de 820 mm ancho "
            "× 440 mm fondo × 25 mm espesor, que sustituye la tapa superior completa. "
            "Patas de 100 mm. La altura total con patas y mesón es 825 mm. Separado de pared."
        )
        first = self.ask("C2", utterance)
        clarification = (
            "Confirmo las medidas de carcasa: 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad. El mesón mide 820 mm de ancho por 440 mm de "
            "fondo y 25 mm de espesor. La altura total con patas y mesón es 825 mm."
        )
        review = self.ask("C2_CLARIFIED", clarification, first["review_state"])
        self.assertEqual(review["confirmed"]["dimensions_mm"], {
            "width_mm": 800, "height_mm": 700, "depth_mm": 400,
        })
        self.assertEqual(review["confirmed"]["support"], {
            "style": "legs", "height_mm": 100,
        })
        module = review["nominal_draft_request"]["module_spec"]["modules"][0]
        self.assertEqual(review["nominal_draft_request"]["module_spec"]["application"],
                         "cabinet_run")
        self.assertEqual(module["material_id"], "MDF_RH_15")
        self.assertEqual(module["countertop"]["thickness_mm"], 25)
        self.assertEqual(module["support_concept"]["overall_height_mm"], 825)
        self.assertEqual(module["countertop"]["left_overhang_mm"], 10)
        self.assertEqual(module["countertop"]["right_overhang_mm"], 10)
        self.assertEqual(module["countertop"]["front_overhang_mm"], 20)
        self.assertEqual(module["countertop"]["rear_overhang_mm"], 20)
        self.assertEqual(module["countertop"]["material_id"], "MATERIAL_PENDIENTE")
        self.assertTrue(any(item["field"] == "countertop.material_id"
                            and item["source"] == "ENGINE_PROPOSED_NOT_OWNER_APPROVED"
                            for item in review["nominal_draft_assumptions"]))
        bundle = self.assert_bundle("C2", review, {
            "left_side", "right_side", "bottom", "countertop",
        })
        self.assertNotIn("top", {part["role"] for part in bundle["model"]["parts"]})
        assembly = bundle["model"]["assembly_review"]
        self.assertEqual(bundle["model"]["dimensions_mm"]["height"], 825)
        self.assertEqual(assembly["carcass_dimensions_xyz_mm"][1], 700)

        mismatch = self.ask("C2_BAD_TOTAL", utterance.replace("825 mm", "830 mm"))
        self.assertIsNone(mismatch["nominal_draft_request"])
        self.assertEqual(mismatch["piece_count"], 0)
        self.assertTrue(all(mismatch[flag] is False for flag in FLAGS))
        self.assertTrue(any("overall_height_conflicts" in item
                            for item in mismatch["nominal_draft_blockers"]))

    def test_gn5_c3_drawer_revisions_are_f1_cumulative_and_atomic(self):
        utterance = (
            "Quiero un nochero independiente con tres cajones, 500 mm de ancho, "
            "800 mm de alto y 500 mm de fondo de carcasa, melamina de 18 mm, tapa "
            "y base entre laterales, tres frentes sobrepuestos con manijas. Sin "
            "puertas, sin fondo trasero, sin mesón, directo al piso y separado de pared."
        )
        base = self.ask("C3", utterance)
        spec = base["nominal_draft_request"]["module_spec"]
        module = spec["modules"][0]
        base_plan = propose_drawer_layout(module["drawer_layout_reference"])
        base_openings_top_to_bottom = list(reversed(base_plan["opening_plan"]))
        base_public_ids = [item["drawer_id"] for item in base_openings_top_to_bottom]
        self.assertEqual(base["confirmed"]["use"], "bedroom")
        self.assertGreater(base["nominal_draft_piece_count"], 0)
        self.assertTrue(all(item["front_construction"] == "separate"
                            for item in module["drawers"]))
        self.assertTrue(all(item["facade"]["opening_system"] == "handle"
                            for item in module["drawers"]))
        self.assertTrue(any("DRAWER_CLEARANCES_ENGINE_PROPOSED_NOT_USER_SUPPLIED"
                            in warning for warning in base["nominal_draft_warnings"]))

        first = self.ask("C3_A_PLUS_100", "Haz el cajón A 10 cm más alto.",
                         base["review_state"])
        second = self.ask("C3_B_MINUS_50", "Haz el cajón B 5 cm más bajo.",
                          first["review_state"])
        for result in (first, second):
            self.assertEqual(result["nominal_draft_scope"],
                             "CLIENT_PROPOSED_MULTICOMPONENT_REVIEW_ONLY")
            module = result["nominal_draft_request"]["module_spec"]["modules"][0]
            self.assertEqual(module["drawer_layout_reference"]["width_mm"], 500)
            self.assertEqual(module["drawer_layout_reference"]["height_mm"], 800)
        first_changes = {item["ref"]: item["after_mm"] for item in
                         first["nominal_draft_revision"]["last_revision"]["changes"]}
        second_changes = {item["ref"]: item["after_mm"] for item in
                          second["nominal_draft_revision"]["last_revision"]["changes"]}
        self.assertEqual(first_changes["A"], 336)
        self.assertEqual(second_changes["B"], 136)
        self.assertEqual(second_changes["C"], 236)
        self.assertTrue(second["nominal_draft_revision"]["exterior_dimensions_preserved"])
        after_b = deepcopy(second)
        before_ids = [item["drawer_id"] for item in
                      after_b["nominal_draft_request"]["module_spec"]["modules"][0]["drawers"]]
        self.assertEqual(after_b["nominal_draft_request"]["module_spec"]["modules"][0]
                         ["drawer_layout_reference"]["height_mm"], 800)
        self.assertIn("A", [item["ref"] for item in after_b["nominal_draft_revision"]
                             ["history"]])
        self.assertIn("B", [item["ref"] for item in after_b["nominal_draft_revision"]
                             ["history"]])

        invalid = self.ask("C3_A_PLUS_1000", "Haz el cajón A 1000 mm más alto.",
                           after_b["review_state"])
        self.assertIs(invalid["nominal_draft_revision_rejected"], True)
        self.assertEqual(invalid["nominal_draft_request"], after_b["nominal_draft_request"])
        self.assertEqual(invalid["nominal_draft_geometry_sha256"],
                         after_b["nominal_draft_geometry_sha256"])
        self.assertEqual(invalid["nominal_draft_piece_count"],
                         after_b["nominal_draft_piece_count"])
        self.assertEqual(invalid["piece_count"], 0)
        self.assertTrue(all(invalid[flag] is False for flag in FLAGS))

        last = self.ask("C3_C_MINUS_20", "Haz el cajón C 2 cm más bajo.",
                        invalid["review_state"])
        self.assertIs(last["nominal_draft_revision_rejected"], True)
        self.assertEqual(last["nominal_draft_request"], after_b["nominal_draft_request"])
        self.assertEqual(last["nominal_draft_geometry_sha256"],
                         after_b["nominal_draft_geometry_sha256"])
        self.assertEqual(last["piece_count"], 0)
        self.assertTrue(all(last[flag] is False for flag in FLAGS))
        self.assertIn("redistribuir una altura previa",
                      last["nominal_draft_next_question"])
        final_module = after_b["nominal_draft_request"]["module_spec"]["modules"][0]
        final_plan = propose_drawer_layout(final_module["drawer_layout_reference"])
        final_openings_top_to_bottom = list(reversed(final_plan["opening_plan"]))
        final_public_ids = [item["drawer_id"] for item in final_openings_top_to_bottom]
        self.assertEqual(final_public_ids, base_public_ids)
        self.assertEqual([item["drawer_id"] for item in final_module["drawers"]], before_ids)
        actual_by_id = {item["drawer_id"]: item["opening_height_mm"]
                        for item in final_module["drawers"]}
        self.assertEqual([actual_by_id[item["drawer_id"]]
                          for item in final_openings_top_to_bottom], [336, 136, 236])
        bundle = self.assert_bundle("C3", after_b, {
            "left_side", "right_side", "top", "bottom",
            "drawer_side_left", "drawer_side_right", "drawer_front_wall",
            "drawer_rear_wall", "drawer_bottom", "drawer_facade",
        })
        self.assertEqual(bundle["model"]["depth_review"]["assembled_external_depth_mm"], 518)

    def test_gn5_c4_wall_cabinet_requires_back_choice_and_flags_installation(self):
        utterance = (
            "Mueble superior de cocina suspendido, 1000 mm ancho × 700 mm alto × "
            "350 mm fondo de carcasa. Melamina de 15 mm, laterales continuos, dos "
            "puertas sobrepuestas, interior abierto, sin cajones ni mesón, fondo "
            "trasero pendiente. Va fijado al muro, pero la instalación y los chazos "
            "los define un instalador."
        )
        first = self.ask("C4_T1", utterance)
        self.assertEqual(first["nominal_draft_scope"], "CONCEPT_ONLY")
        self.assertIsNone(first["nominal_draft_request"])
        self.assertIn("fondo posterior", first["nominal_draft_next_question"])
        review = self.ask("C4_T2", "Para este boceto, déjalo sin fondo posterior.",
                          first["review_state"])
        self.assertEqual(review["confirmed"]["wall_contact"], True)
        self.assertEqual(review["nominal_draft_request"]["module_spec"]["installation"],
                         "wall_mounted")
        self.assertIn("NOT_CERTIFIED_INSTALLATION", review["nominal_draft_warnings"])
        self.assertIn("NO_ANCHORS_OR_LOAD_CAPACITY_ARE_PROPOSED",
                      review["nominal_draft_warnings"])
        bundle = self.assert_bundle("C4", review, {
            "left_side", "right_side", "top", "bottom", "front_left", "front_right",
        })
        self.assertTrue(any("anclajes" in str(item).casefold()
                            for item in bundle["model"].get("blockers", [])))


class GN6CausalDefectTests(unittest.TestCase):
    def test_d1_engine_proposed_empty_layout_keeps_warning_and_is_review_only(self):
        utterance = (
            "Necesito un mueble de 800 mm de ancho, 700 mm de alto y 400 mm "
            "de profundidad, melamina de 15 mm, laterales continuos, separado "
            "de la pared, directamente al piso, tres cajones, sin puertas y "
            "sin fondo posterior."
        )
        result = query(utterance)
        self.assertIn(
            "NO_ADDITIONAL_DIVIDERS_ENGINE_PROPOSED_NOT_OWNER_APPROVED.",
            result["nominal_draft_warnings"],
        )
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_d2_floor_direct_countertop_uses_zero_support_and_separates_heights(self):
        utterance = (
            "Diseña un mueble de baño de 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad, MDF RH de 15 mm, laterales continuos, "
            "separado de la pared, directamente al piso, interior abierto, "
            "sin cajones, sin puertas, sin fondo posterior. Mesón aparte de "
            "820 mm de ancho por 440 mm de profundidad y 25 mm de espesor."
        )
        first = query(utterance)
        clarification = (
            "Confirmo las medidas exteriores de la carcasa: 800 mm de ancho, "
            "700 mm de alto y 400 mm de profundidad. Confirmo el mesón aparte "
            "de 820 mm de ancho, 440 mm de profundidad y 25 mm de espesor."
        )
        result = query(clarification, review_state=first["review_state"])
        self.assertIsNotNone(result["nominal_draft_request"])
        module = result["nominal_draft_request"]["module_spec"]["modules"][0]
        self.assertEqual(module["support_concept"]["support_height_mm"], 0)
        self.assertEqual(module["support_concept"]["overall_height_mm"], 725)
        vertical = next(
            item["value"] for item in result["nominal_draft_assumptions"]
            if item["field"] == "vertical_dimensions_review"
        )
        self.assertEqual(vertical, {
            "carcass_height_mm": 700,
            "support_height_mm": 0,
            "countertop_thickness_mm": 25,
            "overall_height_mm": 725,
        })
        self.assertEqual(result["piece_count"], 0)
        self.assertIs(result["can_generate_f7c"], False)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_d2_legs_without_height_remain_pending(self):
        utterance = (
            "Diseña un mueble de baño de 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad, MDF RH de 15 mm, laterales continuos, "
            "separado de la pared, con patas, interior abierto, sin cajones, "
            "sin puertas, sin fondo posterior. Mesón aparte de 820 mm de ancho "
            "por 440 mm de profundidad y 25 mm de espesor."
        )
        result = query(utterance)
        self.assertEqual(result["review_state"]["decisions"]["support"]["status"], "proposed")
        self.assertIn("support", result["readiness_blockers"])
        self.assertIsNone(result["nominal_draft_request"])
        self.assertEqual(result["piece_count"], 0)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))

    def test_d2_declared_total_conflict_is_blocked(self):
        utterance = (
            "Diseña un mueble de baño de 800 mm de ancho, 700 mm de alto y "
            "400 mm de profundidad, MDF RH de 15 mm, laterales continuos, "
            "separado de la pared, directamente al piso, interior abierto, "
            "sin cajones, sin puertas, sin fondo posterior. Mesón aparte de "
            "820 mm de ancho por 440 mm de profundidad y 25 mm de espesor."
        )
        first = query(utterance)
        clarification = (
            "Confirmo las medidas exteriores de la carcasa: 800 mm de ancho, "
            "700 mm de alto y 400 mm de profundidad. Confirmo el mesón aparte "
            "de 820 mm de ancho, 440 mm de profundidad y 25 mm de espesor; "
            "la altura total es 730 mm."
        )
        result = query(clarification, review_state=first["review_state"])
        self.assertIsNone(result["nominal_draft_request"])
        self.assertTrue(any(
            "overall_height_conflicts" in item
            for item in result["nominal_draft_blockers"]
        ))
        self.assertEqual(result["piece_count"], 0)
        self.assertTrue(all(result[flag] is False for flag in FLAGS))


if __name__ == "__main__":
    unittest.main()
