"""F9A: nominal open blind-corner panel through existing F6/CAD/MCP paths."""
from __future__ import annotations

import copy
import csv
import json
import unittest
import xml.etree.ElementTree as ET
from io import StringIO

from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.core import DesignError
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent.modular_outputs import modular_bom_csv, modular_front_svg


def blind_spec(*, side: str = "right", blind_width_mm: int = 420) -> dict:
    return {
        "type": "modular_run",
        "application": "kitchen",
        "width_mm": 900,
        "height_mm": 720,
        "depth_mm": 560,
        "installation": "freestanding",
        "modules": [{
            "module_id": "CIEGO",
            "width_mm": 900,
            "panel_thickness_mm": 18,
            "material_id": "MELAMINA_18",
            "construction": "sides_full",
            "fronts": "none",
            "back": "none",
            "support": "floor",
            "drawers": "none",
            "corner_blind": {
                "side": side,
                "blind_width_mm": blind_width_mm,
            },
        }],
    }


def straight_spec() -> dict:
    return {
        "type": "modular_run",
        "application": "kitchen",
        "width_mm": 600,
        "height_mm": 720,
        "depth_mm": 560,
        "installation": "freestanding",
        "modules": [{
            "module_id": "RECTO",
            "width_mm": 600,
            "panel_thickness_mm": 18,
            "material_id": "MELAMINA_18",
            "construction": "sides_full",
            "fronts": "none",
            "back": "none",
            "support": "floor",
            "drawers": "none",
        }],
    }


def maestro(spec: dict) -> dict:
    return consult_maestro({"action": "modular", "module_spec": spec})


class CornerBlindF9ATests(unittest.TestCase):
    def test_p1_maestro_emits_real_blind_panel_and_opening(self):
        answer = maestro(blind_spec())
        self.assertEqual(answer["status"], "DRAFT_NOT_FOR_CUTTING")
        model = answer["modular"]
        self.assertEqual(model["piece_count"], 5)
        module = model["modules"][0]
        self.assertEqual(module["part_ids"], [
            "CIEGO-LEFT_SIDE", "CIEGO-RIGHT_SIDE", "CIEGO-TOP",
            "CIEGO-BOTTOM", "CIEGO-FRONT_CORNER_BLIND",
        ])
        review = module["corner_blind_review"]
        self.assertEqual(review, {
            "status": "REVIEW_ONLY_UNDOORED",
            "side": "right",
            "blind_width_mm": 420,
            "nominal_opening_width_mm": 462,
            "nominal_opening_height_mm": 684,
            "nominal_opening_x_mm": [18, 480],
        })
        panel = next(p for p in model["parts"]
                     if p["role"] == "front_corner_blind")
        self.assertEqual(panel["piece_id"], "CIEGO-FRONT_CORNER_BLIND")
        self.assertEqual(
            [panel["nominal_face_x_mm"], panel["nominal_face_y_mm"],
             panel["thickness_mm"]], [420, 720, 18]
        )
        self.assertEqual(panel["nominal_origin_xyz_mm"], [480, 0, -18])
        self.assertEqual(panel["face_plane"], "XY")
        self.assertEqual(panel["grain_axis"], "UNCONFIRMED")
        self.assertEqual(panel["edgebanding_edges"], "UNCONFIRMED")
        self.assertIsNone(panel["finished_cut_dimensions_mm"])
        self.assertEqual(panel["source_engine"], "F6_CORNER_BLIND_REVIEW")
        self.assertIn("W=900", panel["source_formula"])
        self.assertIn("B=420", panel["source_formula"])
        self.assertIn("t=18", panel["source_formula"])
        self.assertIn("side=right", panel["source_formula"])
        self.assertTrue(any("sin puerta" in blocker.lower()
                            for blocker in model["blockers"]))
        for response in (answer, model):
            for flag in ("fabrication_ready", "cutting_ready",
                         "drilling_ready", "purchase_ready"):
                self.assertIs(response[flag], False)
            if "can_generate_f7c" in response:
                self.assertIs(response["can_generate_f7c"], False)

    def test_p2_cad_exchange_keeps_geometry_shift_hash_and_no_intersections(self):
        model = maestro(blind_spec())["modular"]
        exchange = cad_exchange(model)
        self.assertEqual(validate_exchange(exchange), exchange)
        self.assertEqual(exchange["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(exchange["source_engine"], "F7C_EXPLICIT_FRONTS_FROM_F6")
        self.assertEqual(exchange["front_shift_mm"], 18)
        self.assertEqual(exchange["bounds_xyz_mm"], [900, 720, 578])
        self.assertEqual(exchange["geometry_sha256"],
                         cad_exchange(model)["geometry_sha256"])
        panel = next(p for p in exchange["boxes"]
                     if p["role"] == "front_corner_blind")
        self.assertEqual(panel["piece_id"], "CIEGO-FRONT_CORNER_BLIND")
        self.assertEqual(panel["origin_xyz_mm"], [480, 0, 0])
        self.assertEqual(panel["size_xyz_mm"], [420, 720, 18])
        self.assertEqual(len(exchange["boxes"]), 5)
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready",
                     "hardware_included", "finished_panel_edges_included"):
            self.assertIs(exchange[flag], False)
        self.assertEqual(exchange["manufacturing_holes"], [])

        tampered = copy.deepcopy(exchange)
        tampered_panel = next(p for p in tampered["boxes"]
                              if p["role"] == "front_corner_blind")
        tampered_panel["size_xyz_mm"][0] = 421
        with self.assertRaisesRegex(DesignError, "modificado"):
            validate_exchange(tampered)

    def test_p3_front_svg_and_bom_contain_the_same_f6_piece(self):
        model = maestro(blind_spec())["modular"]
        svg = modular_front_svg(model)
        root = ET.fromstring(svg)
        ns = {"s": "http://www.w3.org/2000/svg"}
        panels = root.findall('.//s:rect[@data-role="front_corner_blind"]', ns)
        self.assertEqual(len(panels), 1)
        self.assertEqual(panels[0].get("class"), "front")
        self.assertGreater(float(panels[0].get("width")), 0)
        self.assertGreater(float(panels[0].get("height")), 0)

        rows = list(csv.DictReader(StringIO(modular_bom_csv(model))))
        row = next(r for r in rows if r["role"] == "front_corner_blind")
        self.assertEqual(row["piece_id"], "CIEGO-FRONT_CORNER_BLIND")
        self.assertEqual((row["nominal_face_x_mm"], row["nominal_face_y_mm"],
                          row["thickness_mm"]), ("420", "720", "18"))
        self.assertEqual((row["origin_x_mm"], row["origin_y_mm"],
                          row["origin_z_mm"]), ("480", "0", "-18"))
        self.assertEqual(row["production_status"], "BORRADOR_NO_CORTAR")
        self.assertEqual(row["grain_axis"], "UNCONFIRMED")
        self.assertEqual(row["edgebanding_edges"], "UNCONFIRMED")
        self.assertEqual(row["dimension_formula"], next(
            p["source_formula"] for p in model["parts"]
            if p["role"] == "front_corner_blind"
        ))

    def test_p4_existing_public_room_layout_route_composes_perpendicular_modules(self):
        request = {
            "review_kind": "room_layout_v1",
            "assemblies": [
                {"group_id": "CIEGO", "module_spec": blind_spec(),
                 "origin_xyz_mm": [0, 0, 0], "rotation_deg": 0},
                {"group_id": "RECTO", "module_spec": straight_spec(),
                 "origin_xyz_mm": [900, 0, 0], "rotation_deg": 90},
            ],
            "service_zones": [],
        }
        review = carpinova_consultar(json.dumps(
            request, ensure_ascii=False, separators=(",", ":")
        ))
        self.assertEqual(review["review_kind"], "room_layout_v1")
        self.assertEqual(review["status"], "REVIEW_ONLY")
        self.assertEqual([g["group_id"] for g in review["groups"]],
                         ["CIEGO", "RECTO"])
        self.assertEqual([g["piece_count"] for g in review["groups"]], [5, 4])
        self.assertEqual(review["piece_count"], 9)
        self.assertEqual(review["envelope_collisions"], [])
        self.assertEqual(review["panel_collisions"], [])
        self.assertIn("CORNER_JOINT_AND_FILLER_NOT_DESIGNED", review["warnings"])
        blind_box = next(box for box in review["world_boxes"]
                         if box["role"] == "front_corner_blind")
        self.assertEqual(blind_box["piece_id"],
                         "CIEGO:CIEGO-FRONT_CORNER_BLIND")
        self.assertEqual(blind_box["origin_xyz_mm"], [480, 0, 0])
        self.assertEqual(blind_box["size_xyz_mm"], [420, 720, 18])
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready",
                     "purchase_ready", "can_generate_f7c"):
            self.assertIs(review[flag], False)

        from carpinova_agent.room_spatial import render_top_view_svg
        top = ET.fromstring(render_top_view_svg(review))
        ns = {"s": "http://www.w3.org/2000/svg"}
        self.assertEqual(len(top.findall("s:rect", ns)), 2)
        self.assertFalse(top.findall('.//*[@data-role="front_corner_blind"]', ns))

    def test_p5_mirror_and_width_revision_are_deterministic_and_recalculate(self):
        right_420 = maestro(blind_spec())
        right_420_again = maestro(blind_spec())
        right_400 = maestro(blind_spec(blind_width_mm=400))
        left_420 = maestro(blind_spec(side="left"))
        self.assertEqual(right_420["modular"]["modules"][0]
                         ["corner_blind_review"]["nominal_opening_width_mm"], 462)
        self.assertEqual(right_400["modular"]["modules"][0]
                         ["corner_blind_review"]["nominal_opening_width_mm"], 482)
        self.assertEqual(right_400["modular"]["modules"][0]
                         ["corner_blind_review"]["nominal_opening_x_mm"], [18, 500])
        self.assertEqual(right_420["modular"]["parts"][-1]
                         ["nominal_origin_xyz_mm"], [480, 0, -18])
        self.assertEqual(right_400["modular"]["parts"][-1]
                         ["nominal_origin_xyz_mm"], [500, 0, -18])
        self.assertEqual(left_420["modular"]["parts"][-1]
                         ["nominal_origin_xyz_mm"], [0, 0, -18])
        self.assertEqual(
            cad_exchange(right_420["modular"])["geometry_sha256"],
            cad_exchange(right_420_again["modular"])["geometry_sha256"],
        )
        self.assertNotEqual(
            cad_exchange(right_420["modular"])["geometry_sha256"],
            cad_exchange(right_400["modular"])["geometry_sha256"],
        )
        self.assertNotEqual(
            cad_exchange(right_420["modular"])["geometry_sha256"],
            cad_exchange(left_420["modular"])["geometry_sha256"],
        )
        self.assertEqual(left_420["modular"]["modules"][0]
                         ["corner_blind_review"]["nominal_opening_x_mm"], [420, 882])

    def test_n1_rejects_invalid_width_side_and_unexpected_fields(self):
        for value in (0, -1, 18, 882, True, 420.5, "420"):
            spec = blind_spec()
            spec["modules"][0]["corner_blind"]["blind_width_mm"] = value
            with self.subTest(blind_width_mm=value), self.assertRaises(DesignError):
                maestro(spec)
        for side in ("center", "LEFT", ""):
            with self.subTest(side=side), self.assertRaises(DesignError):
                maestro(blind_spec(side=side))
        spec = blind_spec()
        spec["modules"][0]["corner_blind"]["door_width_mm"] = 400
        with self.assertRaisesRegex(DesignError, "corner_blind.*campos desconocidos"):
            maestro(spec)

    def test_n1_corner_blind_rejects_unsupported_construction_and_elements(self):
        changes = [
            ("application", "closet"),
            ("construction", "top_bottom_full"),
            ("fronts", "pending"),
            ("drawers", "pending"),
            ("back", "pending"),
            ("support", "pending"),
            ("installation", "built_in"),
            ("countertop", {}),
            ("upper_support", {}),
            ("vertical_divider", {}),
            ("horizontal_divider", {}),
            ("support_concept", {}),
        ]
        for field, value in changes:
            spec = blind_spec()
            target = spec if field in {"application", "installation"} else spec["modules"][0]
            target[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                    DesignError, "corner_blind"):
                maestro(spec)

    def test_n1_rejects_overlapping_room_layout_and_f6_volume_penetration(self):
        request = {
            "review_kind": "room_layout_v1",
            "assemblies": [
                {"group_id": "CIEGO", "module_spec": blind_spec(),
                 "origin_xyz_mm": [0, 0, 0], "rotation_deg": 0},
                {"group_id": "RECTO", "module_spec": straight_spec(),
                 "origin_xyz_mm": [899, 0, 0], "rotation_deg": 90},
            ],
            "service_zones": [],
        }
        review = carpinova_consultar(json.dumps(request))
        self.assertEqual(review["status"], "INTERFERENCE_REVIEW_REQUIRED")
        self.assertTrue(review["envelope_collisions"])
        self.assertIn("OVERLAPPING_CABINET_ENVELOPES_BLOCK_APPROVAL",
                      review["warnings"])
        self.assertFalse(review["fabrication_ready"])

        model = maestro(blind_spec())["modular"]
        panel = next(p for p in model["parts"]
                     if p["role"] == "front_corner_blind")
        panel["nominal_origin_xyz_mm"][2] = -17
        with self.assertRaisesRegex(DesignError, "mismo volumen"):
            cad_exchange(model)


if __name__ == "__main__":
    unittest.main()
