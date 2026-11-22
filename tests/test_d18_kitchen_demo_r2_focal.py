import copy
import json
import re
import unittest
from pathlib import Path

from carpinova_agent.room_3d_review import render_room_3d_html
from carpinova_agent.room_spatial import review_room_from_specs


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "room-layout-kitchen-storage-review.json"
PHYSICAL_FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready",
    "purchase_ready", "can_generate_f7c",
)


class D18KitchenDemoR2FocalTests(unittest.TestCase):
    def test_engine_scene_payload_and_rotated_generic_canary(self):
        request = json.loads(DEMO.read_text(encoding="utf-8"))
        self.assertEqual(set(request), {"review_kind", "assemblies", "service_zones"})
        review = review_room_from_specs(request)
        before = json.dumps(review, sort_keys=True, separators=(",", ":"))

        self.assertEqual(review["status"], "REVIEW_ONLY")
        self.assertEqual(review["piece_count"], 8)
        self.assertEqual(
            {box["role"] for box in review["world_boxes"]},
            {"left_side", "right_side", "top", "bottom", "front_left",
             "front_right", "back_full", "shelf_horizontal"},
        )
        self.assertEqual(review["groups"][0]["bounds_xyz_mm"], [900, 720, 578])
        self.assertEqual(review["groups"][0]["rotation_deg"], 0)
        self.assertEqual(review["envelope_collisions"], [])
        self.assertEqual(review["panel_collisions"], [])
        for flag in PHYSICAL_FLAGS:
            self.assertIs(review[flag], False)

        panels = {box["role"]: box for box in review["world_boxes"]}
        self.assertEqual(panels["front_left"]["size_xyz_mm"], [445, 714, 18])
        self.assertEqual(panels["front_right"]["size_xyz_mm"], [445, 714, 18])
        self.assertEqual(panels["shelf_horizontal"]["size_xyz_mm"], [864, 18, 500])
        self.assertEqual(panels["shelf_horizontal"]["origin_xyz_mm"][1], 338)
        self.assertEqual(panels["back_full"]["size_xyz_mm"][2], 6)

        html = render_room_3d_html(review)
        embedded = re.search(
            r'<script id="scene-data" type="application/json">(.*?)</script>',
            html, re.DOTALL,
        )
        self.assertIsNotNone(embedded)
        payload = json.loads(embedded.group(1))
        self.assertEqual(payload["groups"][0]["rotation"], 0)
        self.assertEqual(len(payload["boxes"]), 8)
        self.assertEqual(before, json.dumps(review, sort_keys=True, separators=(",", ":")))

        for text in (
            "VISOR NOMINAL SIN AUTORIZACIÓN DE FABRICACIÓN", "BAJO_COCINA_2P",
            "Conjunto nominal", "X (horizontal)", "Y (vertical)", "Z (fondo)",
            "Inspeccionar interior", "VISTA INTERIOR", "Restablecer vista completa",
            "CORTE ACTIVADO", "NO FABRICAR", "front_left", "puerta izquierda nominal",
            "front_right", "puerta derecha nominal", "front_corner_blind",
            "panel ciego NO puerta", "front_corner_access",
            "puerta nominal sin bisagra validada", "shelf_horizontal", "repisa",
        ):
            self.assertIn(text, html)
        self.assertIn("startsWith('front_')", html)
        self.assertIn("role==='top'", html)
        self.assertIn("cameraHeading=(heading+180)%360", html)
        self.assertIn("return sum-u-v", html)
        self.assertNotIn("selected?1:0", html)

        # A real F1/F6/CADExchange scene, not fabricated boxes: rotation and a
        # service reservation must remain inspectable without inventing a title.
        canary_request = copy.deepcopy(request)
        canary_request["assemblies"][0]["group_id"] = "MUESTRA_GIRADA"
        canary_request["assemblies"][0]["module_spec"]["modules"][0]["module_id"] = "MUESTRA_GIRADA"
        canary_request["assemblies"][0]["rotation_deg"] = 90
        canary_request["service_zones"] = [{
            "zone_id": "RESERVA_INTERIOR", "purpose": "access",
            "origin_xyz_mm": [100, 100, 200], "size_xyz_mm": [10, 10, 10],
        }]
        canary = review_room_from_specs(canary_request)
        canary_html = render_room_3d_html(canary)
        canary_script = re.search(
            r'<script id="scene-data" type="application/json">(.*?)</script>',
            canary_html, re.DOTALL,
        )
        self.assertIsNotNone(canary_script)
        canary_payload = json.loads(canary_script.group(1))
        self.assertEqual(canary_payload["groups"][0]["id"], "MUESTRA_GIRADA")
        self.assertEqual(canary_payload["groups"][0]["rotation"], 90)
        self.assertEqual(canary_payload["zones"][0]["id"], "RESERVA_INTERIOR")
        self.assertEqual(canary["status"], "REVIEW_ONLY")
        self.assertNotIn("cocina", canary_html.casefold())
        for flag in PHYSICAL_FLAGS:
            self.assertIs(canary[flag], False)


if __name__ == "__main__":
    unittest.main()
