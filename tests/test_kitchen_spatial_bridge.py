"""D6: public end-to-end D4 conversational kitchen -> D5 spatial layout.

Requires both real modules, Maestro/F6 and CADExchange; mocks are forbidden
in this test. The D4 history and its fixture phrases are reused, not recreated.
"""
from __future__ import annotations

import copy
import json
import unittest

from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent.room_spatial import render_top_view_svg
from test_kitchen_linear import ask, make_l1


PHYSICAL_FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready",
    "purchase_ready", "can_generate_f7c",
)


def spatial(state: dict, *, rotations: dict | None = None,
            zones: list | None = None) -> dict:
    payload = {"review_kind": "kitchen_spatial_v1",
               "review_state": copy.deepcopy(state),
               "service_zones": zones if zones is not None else []}
    if rotations is not None:
        payload["rotations_deg"] = rotations
    return carpinova_consultar(json.dumps(payload, ensure_ascii=False))


class KitchenToSpatialRealIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d4_result = make_l1()
        if cls.d4_result["assemblage_status"] != "REVIEW_ONLY_VALID":
            raise AssertionError("D4 base must be fully valid, not a fixture mock")
        cls.state = cls.d4_result["review_state"]

    def assert_review_only(self, result):
        for flag in PHYSICAL_FLAGS:
            self.assertIs(result[flag], False, flag)

    def test_real_42_pieces_sha_and_spatial_svg(self):
        result = spatial(self.state)
        self.assertEqual(result["review_kind"], "room_layout_v1")
        self.assertEqual(result["source_review_kind"], "kitchen_linear_v1")
        self.assertEqual(result["source_layout_sha256"],
                         self.d4_result["layout_sha256"])
        self.assertEqual(result["piece_count"], 42)
        self.assertEqual(len(result["global_piece_ids"]), 42)
        self.assertEqual(len(set(result["global_piece_ids"])), 42)
        self.assertEqual(result["status"], "REVIEW_ONLY")
        self.assertEqual(result["envelope_collisions"], [])
        self.assertEqual(
            {g["group_id"]: g["geometry_sha256"] for g in result["groups"]},
            {g["group_id"]: g["geometry_sha256"] for g in self.d4_result["groups"]},
        )
        self.assertEqual(result["top_view_svg"], render_top_view_svg(result))
        self.assertIn("no fabricable", result["top_view_svg"])
        self.assert_review_only(result)

    def test_rotation_and_services_do_not_create_cutouts(self):
        zones = [{"zone_id":"S1", "purpose":"plumbing",
                  "origin_xyz_mm":[0,0,0], "size_xyz_mm":[30,30,30]}]
        result = spatial(self.state, rotations={"BAJO":0,"ALTO":0,"TORRE":90}, zones=zones)
        self.assertEqual(result["groups"][2]["rotation_deg"],90)
        self.assertNotEqual(result["layout_sha256"],
                            spatial(self.state)["layout_sha256"])
        self.assertEqual(result["source_layout_sha256"], self.d4_result["layout_sha256"])
        self.assertEqual(result["service_zones"][0]["purpose"], "plumbing")
        self.assertIn("SERVICE_RESERVATIONS_ARE_NOT_HOLES_OR_PLUMBING_INSTALLATION",
                      result["warnings"])
        self.assert_review_only(result)

    def test_rejects_colliding_pending_candidate_without_promoting_last_valid(self):
        rejected = ask(self.state, "ALTO", "Mover ALTO: X=0 mm, Y=650 mm, Z=0 mm")
        self.assertEqual(rejected["pending_candidate"]["status"], "PENDING_COLLISION")
        with self.assertRaisesRegex(ValueError, "revisión pendiente"):
            spatial(rejected["review_state"])

    def test_rejects_forged_hash_and_injected_geometry(self):
        bad = copy.deepcopy(self.state)
        bad["last_valid"]["layout_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError,"instantánea"):
            spatial(bad)
        bad = copy.deepcopy(self.state)
        bad["working"]["groups"]["BAJO"]["exchange"] = {"boxes": []}
        with self.assertRaisesRegex(ValueError,"campos no permitidos"):
            spatial(bad)
        payload = {"review_kind":"kitchen_spatial_v1", "review_state":self.state,
                   "service_zones":[], "exchange": {"boxes": []}}
        with self.assertRaisesRegex(ValueError,"kitchen_spatial_v1 exige"):
            carpinova_consultar(json.dumps(payload))

    def test_existing_six_mcp_tool_registrations_preserved(self):
        import ast
        import inspect
        from carpinova_agent.mcp_bridge import create_server
        tree = ast.parse(inspect.getsource(create_server))
        registrations = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Call)
                    and isinstance(node.func.func, ast.Attribute)
                    and node.func.func.attr == "tool"
                    and isinstance(node.func.func.value, ast.Name)
                    and node.func.func.value.id == "server"
                    and len(node.args) == 1 and isinstance(node.args[0], ast.Name)):
                registrations.append(node.args[0].id)
        self.assertEqual(set(registrations), {
            "carpinova_estado", "carpinova_consultar", "carpinova_generar_borrador",
            "carpinova_renderizar_lamina", "carpinova_exportar_3d",
            "carpinova_leer_entregable",
        })
        self.assertEqual(len(registrations), 6)

    def test_rejects_missing_or_invalid_rotations(self):
        for val in (
            {"BAJO": True,"ALTO":0,"TORRE":0},
            {"BAJO":45,"ALTO":0,"TORRE":0},
            {"BAJO":0,"ALTO":0},
        ):
            with self.subTest(rotation=val), self.assertRaisesRegex(ValueError,"rotations_deg"):
                spatial(self.state,rotations=val)
        with self.assertRaisesRegex(ValueError,"La cocina debe tener"):
            spatial({"schema_version":"kitchen_linear_v1", "working": {
                "groups":{g:{"history":[]} for g in ("BAJO","ALTO","TORRE")},
                "positions":{g:None for g in ("BAJO","ALTO","TORRE")}},
                "last_valid":None, "pending_candidate":None})


if __name__ == "__main__":
    unittest.main()
