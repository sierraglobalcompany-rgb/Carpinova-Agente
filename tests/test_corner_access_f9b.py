"""F9B: nominal corner-access leaf through existing F6/CAD/public review paths."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import unittest
import xml.etree.ElementTree as ET

from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.core import DesignError
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent.modular_outputs import modular_bom_csv, modular_front_svg
from carpinova_agent.room_panel_section import render_room_panel_section_svg
from test_corner_blind_f9a import blind_spec, straight_spec


F9A_PUBLIC_RESPONSE_SHA256 = (
    "29ec4595e94dc69e0458df81c5008d1a22ac356d84fb6a0c392c2679382a02bb"
)
F9A_CAD_SHA256 = (
    "ecf24fd539ba508c20b8badbede93cf50794227f4d45df44c45d0121fb2de8b4"
)
DOOR = {
    "material_id": "MELAMINA_18",
    "thickness_mm": 18,
    "gap_left_mm": 3,
    "gap_right_mm": 3,
    "gap_top_mm": 3,
    "gap_bottom_mm": 3,
    "hinge_side": "left",
}


def access_spec(*, side: str = "right", blind_width_mm: int = 420) -> dict:
    spec = blind_spec(side=side, blind_width_mm=blind_width_mm)
    spec["modules"][0]["corner_blind"]["access_door"] = dict(DOOR)
    return spec


def public_modular(spec: dict) -> dict:
    request = {"action": "modular", "module_spec": spec}
    return carpinova_consultar(json.dumps(
        request, ensure_ascii=False, separators=(",", ":")
    ))


def model(spec: dict) -> dict:
    return consult_maestro({"action": "modular", "module_spec": spec})["modular"]


def box_overlaps(first: dict, second: dict) -> bool:
    a, da = first["origin_xyz_mm"], first["size_xyz_mm"]
    b, db = second["origin_xyz_mm"], second["size_xyz_mm"]
    return all(
        max(a[axis], b[axis]) < min(a[axis] + da[axis], b[axis] + db[axis])
        for axis in range(3)
    )


class CornerAccessF9BTests(unittest.TestCase):
    def test_f9a_without_access_door_keeps_sealed_public_response_and_cad_hash(self):
        answer = public_modular(blind_spec())
        canonical = json.dumps(
            answer, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         F9A_PUBLIC_RESPONSE_SHA256)
        self.assertEqual(answer["modular"]["piece_count"], 5)
        self.assertEqual(
            answer["modular"]["modules"][0]["corner_blind_review"]["status"],
            "REVIEW_ONLY_UNDOORED",
        )
        exchange = cad_exchange(answer["modular"])
        self.assertEqual(exchange["geometry_sha256"], F9A_CAD_SHA256)

    def test_maestro_adds_exactly_one_nominal_access_panel_and_review(self):
        answer = public_modular(access_spec())
        self.assertEqual(answer["status"], "DRAFT_NOT_FOR_CUTTING")
        result = answer["modular"]
        self.assertEqual(result["piece_count"], 6)
        module = result["modules"][0]
        self.assertEqual(module["part_ids"][-2:], [
            "CIEGO-FRONT_CORNER_BLIND",
            "CIEGO-FRONT_CORNER_ACCESS",
        ])
        review = module["corner_blind_review"]
        self.assertEqual(review["status"], "DOOR_NOMINAL_ONLY_HARDWARE_PENDING")
        self.assertEqual(review["nominal_opening_x_mm"], [18, 480])
        self.assertEqual(review["nominal_opening_width_mm"], 462)
        self.assertEqual(review["nominal_opening_height_mm"], 684)
        self.assertEqual(review["access_door_review"], {
            "status": "DOOR_NOMINAL_ONLY_HARDWARE_PENDING",
            "nominal_face_x_mm": 456,
            "nominal_face_y_mm": 678,
            "nominal_origin_xyz_mm": [21, 21, -18],
            "thickness_mm": 18,
            "hinge_side_requested": "left",
            "hardware_status": "NOT_VERIFIED",
        })
        door = next(p for p in result["parts"]
                    if p["role"] == "front_corner_access")
        self.assertEqual(door["piece_id"], "CIEGO-FRONT_CORNER_ACCESS")
        self.assertEqual(door["source_engine"],
                         "F9B_EXPLICIT_CORNER_ACCESS_REVIEW")
        self.assertEqual(door["face_plane"], "XY")
        self.assertEqual(door["nominal_origin_xyz_mm"], [21, 21, -18])
        self.assertEqual(
            [door["nominal_face_x_mm"], door["nominal_face_y_mm"],
             door["thickness_mm"], door["material_id"]],
            [456, 678, 18, "MELAMINA_18"],
        )
        self.assertEqual(door["hinge_side_requested"], "left")
        self.assertEqual(door["grain_axis"], "UNCONFIRMED")
        self.assertEqual(door["edgebanding_edges"], "UNCONFIRMED")
        self.assertIsNone(door["finished_cut_dimensions_mm"])
        self.assertIn("gap_left_mm-gap_right_mm=(480-18)-3-3",
                      door["source_formula"])
        self.assertIn("clear_height_mm-gap_top_mm-gap_bottom_mm=684-3-3",
                      door["source_formula"])
        self.assertTrue(any(
            "giro/bisagra/clearance dinámico y uniones no verificados" in b
            for b in result["blockers"]
        ))
        self.assertFalse(any("sin puerta" in b.lower()
                             for b in result["blockers"]))
        for response in (answer, result):
            for flag in ("fabrication_ready", "cutting_ready",
                         "drilling_ready", "purchase_ready"):
                self.assertIs(response[flag], False)
            if "can_generate_f7c" in response:
                self.assertIs(response["can_generate_f7c"], False)

    def test_cad_exchange_keeps_both_fronts_shift_and_blocks_overlap_or_tampering(self):
        result = model(access_spec())
        exchange = cad_exchange(result)
        self.assertEqual(validate_exchange(exchange), exchange)
        self.assertEqual(exchange["front_shift_mm"], 18)
        self.assertEqual(exchange["bounds_xyz_mm"], [900, 720, 578])
        self.assertEqual(len(exchange["boxes"]), 6)
        door = next(b for b in exchange["boxes"]
                    if b["role"] == "front_corner_access")
        blind = next(b for b in exchange["boxes"]
                     if b["role"] == "front_corner_blind")
        self.assertEqual(door["piece_id"], "CIEGO-FRONT_CORNER_ACCESS")
        self.assertEqual(door["origin_xyz_mm"], [21, 21, 0])
        self.assertEqual(door["size_xyz_mm"], [456, 678, 18])
        self.assertEqual(blind["origin_xyz_mm"], [480, 0, 0])
        self.assertEqual(blind["size_xyz_mm"], [420, 720, 18])
        for index, first in enumerate(exchange["boxes"]):
            for second in exchange["boxes"][index + 1:]:
                self.assertFalse(box_overlaps(first, second),
                                 (first["piece_id"], second["piece_id"]))
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready",
                     "hardware_included", "finished_panel_edges_included"):
            self.assertIs(exchange[flag], False)
        self.assertEqual(exchange["manufacturing_holes"], [])
        self.assertEqual(exchange["geometry_sha256"],
                         cad_exchange(result)["geometry_sha256"])

        tampered = copy.deepcopy(exchange)
        next(b for b in tampered["boxes"]
             if b["role"] == "front_corner_access")["size_xyz_mm"][0] += 1
        with self.assertRaisesRegex(DesignError, "modificado"):
            validate_exchange(tampered)

        penetrated = copy.deepcopy(result)
        next(p for p in penetrated["parts"]
             if p["role"] == "front_corner_access")["nominal_origin_xyz_mm"][2] = -17
        with self.assertRaisesRegex(DesignError, "plano frontal F6"):
            cad_exchange(penetrated)

    def test_elevation_and_csv_show_same_panel_without_inventing_svg_id_contract(self):
        result = model(access_spec())
        root = ET.fromstring(modular_front_svg(result))
        ns = {"s": "http://www.w3.org/2000/svg"}
        leaves = root.findall('.//s:rect[@data-role="front_corner_access"]', ns)
        self.assertEqual(len(leaves), 1)
        self.assertGreater(float(leaves[0].get("width")), 0)
        self.assertGreater(float(leaves[0].get("height")), 0)
        self.assertIn("CIEGO-FRONT_CORNER_ACCESS",
                      "".join(leaves[0].itertext()))

        rows = list(csv.DictReader(io.StringIO(modular_bom_csv(result))))
        row = next(r for r in rows if r["role"] == "front_corner_access")
        self.assertEqual(row["piece_id"], "CIEGO-FRONT_CORNER_ACCESS")
        self.assertEqual(row["material_id"], "MELAMINA_18")
        self.assertEqual(
            (row["nominal_face_x_mm"], row["nominal_face_y_mm"],
             row["thickness_mm"], row["origin_x_mm"], row["origin_y_mm"],
             row["origin_z_mm"]),
            ("456", "678", "18", "21", "21", "-18"),
        )
        self.assertEqual(row["hinge_side_requested"], "left")
        self.assertEqual(row["production_status"], "BORRADOR_NO_CORTAR")

    def test_public_room_layout_and_d17_section_show_both_corner_fronts(self):
        request = {
            "review_kind": "room_layout_v1",
            "assemblies": [
                {"group_id": "CIEGO", "module_spec": access_spec(),
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
        self.assertEqual([g["piece_count"] for g in review["groups"]], [6, 4])
        self.assertEqual(review["piece_count"], 10)
        self.assertEqual(review["envelope_collisions"], [])
        self.assertEqual(review["panel_collisions"], [])
        self.assertIn("CORNER_JOINT_AND_FILLER_NOT_DESIGNED",
                      review["warnings"])
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready",
                     "purchase_ready", "can_generate_f7c"):
            self.assertIs(review[flag], False)

        section = ET.fromstring(render_room_panel_section_svg(review, y_mm=350))
        ns = {"s": "http://www.w3.org/2000/svg"}
        access = section.findall(
            './/s:rect[@data-role="front_corner_access"]', ns
        )
        blind = section.findall(
            './/s:rect[@data-role="front_corner_blind"]', ns
        )
        self.assertEqual(len(access), 1)
        self.assertEqual(len(blind), 1)
        self.assertEqual(access[0].get("data-piece-id"),
                         "CIEGO:CIEGO-FRONT_CORNER_ACCESS")
        self.assertEqual((access[0].get("width"), access[0].get("height")),
                         ("456", "18"))
        self.assertIn("NO CORTAR", "".join(section.itertext()))

    def test_mirror_and_blind_width_revision_recalculate_door_from_f1_opening(self):
        left = model(access_spec(side="left"))
        left_review = left["modules"][0]["corner_blind_review"]
        left_door = next(p for p in left["parts"]
                         if p["role"] == "front_corner_access")
        self.assertEqual(left_review["nominal_opening_x_mm"], [420, 882])
        self.assertEqual(left_door["nominal_origin_xyz_mm"], [423, 21, -18])
        self.assertEqual(left_door["nominal_face_x_mm"], 456)
        self.assertEqual(left_door["nominal_face_y_mm"], 678)

        narrower_blind = model(access_spec(blind_width_mm=400))
        review = narrower_blind["modules"][0]["corner_blind_review"]
        door = next(p for p in narrower_blind["parts"]
                    if p["role"] == "front_corner_access")
        self.assertEqual(review["nominal_opening_x_mm"], [18, 500])
        self.assertEqual(review["nominal_opening_width_mm"], 482)
        self.assertEqual(door["nominal_origin_xyz_mm"], [21, 21, -18])
        self.assertEqual(door["nominal_face_x_mm"], 476)
        self.assertEqual(door["nominal_face_y_mm"], 678)
        self.assertNotEqual(cad_exchange(left)["geometry_sha256"],
                            cad_exchange(narrower_blind)["geometry_sha256"])

    def test_strict_door_schema_gaps_clearance_and_equal_thickness(self):
        for field in DOOR:
            spec = access_spec()
            del spec["modules"][0]["corner_blind"]["access_door"][field]
            with self.subTest(missing=field), self.assertRaises(DesignError):
                model(spec)
        spec = access_spec()
        spec["modules"][0]["corner_blind"]["access_door"]["extra"] = True
        with self.assertRaises(DesignError):
            model(spec)
        spec = access_spec()
        spec["modules"][0]["corner_blind"]["access_door"] = None
        with self.assertRaises(DesignError):
            model(spec)

        for value in (True, 3.0, float("nan"), "3", -1):
            spec = access_spec()
            spec["modules"][0]["corner_blind"]["access_door"]["gap_left_mm"] = value
            with self.subTest(gap=value), self.assertRaises(DesignError):
                model(spec)
        for value in (True, 18.0, 16, 20):
            spec = access_spec()
            spec["modules"][0]["corner_blind"]["access_door"]["thickness_mm"] = value
            with self.subTest(thickness=value), self.assertRaises(DesignError):
                model(spec)
        for value in ("CENTER", "", None):
            spec = access_spec()
            spec["modules"][0]["corner_blind"]["access_door"]["hinge_side"] = value
            with self.subTest(hinge_side=value), self.assertRaises(DesignError):
                model(spec)
        for field, value in (("gap_left_mm", 462), ("gap_top_mm", 684)):
            spec = access_spec()
            spec["modules"][0]["corner_blind"]["access_door"][field] = value
            with self.subTest(clearance=field), self.assertRaises(DesignError):
                model(spec)
        spec = access_spec()
        spec["modules"][0]["corner_blind"]["access_door"]["material_id"] = "bad id"
        with self.assertRaises(DesignError):
            model(spec)

    def test_door_is_rejected_outside_f9a_supported_cabinet_context(self):
        changes = [
            ("application", "closet"),
            ("construction", "top_bottom_full"),
            ("installation", "built_in"),
            ("support", "pending"),
            ("fronts", "pending"),
            ("back", "pending"),
            ("drawers", "pending"),
            ("countertop", {}),
            ("upper_support", {}),
            ("vertical_divider", {}),
            ("horizontal_divider", {}),
            ("support_concept", {}),
        ]
        for field, value in changes:
            spec = access_spec()
            target = (spec if field in {"application", "installation"}
                      else spec["modules"][0])
            target[field] = value
            with self.subTest(field=field), self.assertRaises(DesignError):
                model(spec)


if __name__ == "__main__":
    unittest.main()
