from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from carpinova_agent.mcp_bridge import carpinova_consultar, carpinova_generar_borrador
from carpinova_agent.room_3d_review import render_room_3d_html
from test_kitchen_linear import make_l1


FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready",
    "can_generate_f7c",
)
H9_LAYOUT_SHA256_M1 = "fe5c492e40cb76a42fa2dba619282c4ee7544dd20b89a67782774de438d18c15"
EXPECTED_DRAWER_ROLES = {
    "drawer_side_left", "drawer_side_right", "drawer_front_wall",
    "drawer_rear_wall", "drawer_bottom", "drawer_facade",
}


def cabinet_spec(module_id: str, back: object) -> dict:
    return {
        "type": "modular_run", "application": "kitchen",
        "width_mm": 600, "height_mm": 700, "depth_mm": 560,
        "installation": "freestanding",
        "modules": [{
            "module_id": module_id, "width_mm": 600,
            "panel_thickness_mm": 18, "material_id": "MELAMINA_18_LAB",
            "construction": "sides_full", "support": "floor",
            "fronts": "none", "drawers": "none", "back": copy.deepcopy(back),
        }],
    }


def room_request(main_back: dict) -> dict:
    return {
        "review_kind": "room_layout_v1",
        "assemblies": [
            {"group_id": "LAB_MAIN", "module_spec": cabinet_spec("LAB_MAIN_CAB", main_back),
             "origin_xyz_mm": [0, 0, 0], "rotation_deg": 0},
            {"group_id": "LAB_PENDING", "module_spec": cabinet_spec("LAB_PENDING_CAB", "pending"),
             "origin_xyz_mm": [700, 0, 0], "rotation_deg": 0},
        ],
        "service_zones": [],
    }


class H9M2DrawerBackFocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state = make_l1()["review_state"]

    @staticmethod
    def generate(request: dict, project: str, output_root: str) -> dict:
        with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": output_root}):
            return carpinova_generar_borrador(
                solicitud_json=json.dumps(request, ensure_ascii=False),
                proyecto=project, incluir_planos=False, seccion_y_mm=350,
            )

    def test_h9_real_d19_has_three_complete_drawers_and_safe_wall_status(self) -> None:
        request = {
            "review_kind": "kitchen_spatial_v1",
            "review_state": copy.deepcopy(self.state), "service_zones": [],
        }
        with tempfile.TemporaryDirectory() as output_root:
            result = self.generate(request, "H9_M2_DRAWERS", output_root)
            path = Path(result["room_package_path"])
            self.assertTrue(path.is_file())
            self.assertEqual(result["status"], "REVIEW_ONLY")
            for flag in FLAGS:
                self.assertIs(result[flag], False, flag)
            with ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                manifest = json.loads(archive.read("MANIFEST.json"))
                review = json.loads(archive.read("04-habitacion.json"))
                html = archive.read("01-visor-3d.html").decode("utf-8")
                csv_rows = list(csv.DictReader(io.StringIO(
                    archive.read("06-paneles-en-escena.csv").decode("utf-8")
                )))
            self.assertEqual(review["piece_count"], 42)
            self.assertEqual(review["layout_sha256"], H9_LAYOUT_SHA256_M1)
            self.assertEqual(manifest["layout_sha256"], H9_LAYOUT_SHA256_M1)
            boxes = review["world_boxes"]
            drawer_ids = sorted({
                match.group(1) for box in boxes
                if (match := re.search(r"(BAJO:[A-Za-z0-9_-]+-D[0-9]+)-DRAWER_", box["piece_id"]))
            })
            self.assertEqual([item.rsplit("-", 1)[-1] for item in drawer_ids], ["D1", "D2", "D3"])
            for drawer_id in drawer_ids:
                pieces = [box for box in boxes if box["piece_id"].startswith(drawer_id + "-DRAWER_")]
                self.assertEqual(len(pieces), 6)
                self.assertEqual({box["role"] for box in pieces}, EXPECTED_DRAWER_ROLES)

            payload_match = re.search(
                r'<script id="scene-data" type="application/json">(.*?)</script>',
                html, re.DOTALL,
            )
            self.assertIsNotNone(payload_match)
            payload = json.loads(payload_match.group(1))
            self.assertEqual(len(payload["drawers"]), 3)
            self.assertEqual({item["id"].rsplit("-", 1)[-1] for item in payload["drawers"]},
                             {"D1", "D2", "D3"})
            self.assertTrue(all(len(item["piece_ids"]) == 6 for item in payload["drawers"]))
            csv_ids = {row["piece_id"] for row in csv_rows}
            self.assertEqual(csv_ids, {box["piece_id"] for box in boxes})
            for name, info in manifest["files"].items():
                data = ZipFile(path).read(name)
                self.assertEqual(len(data), info["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), info["sha256"])

            incomplete = copy.deepcopy(review)
            removed_id = next(box["piece_id"] for box in incomplete["world_boxes"]
                              if "-D2-DRAWER_REAR_WALL" in box["piece_id"])
            incomplete["world_boxes"] = [box for box in incomplete["world_boxes"]
                                          if box["piece_id"] != removed_id]
            incomplete["piece_count"] -= 1
            next(group for group in incomplete["groups"] if group["group_id"] == "BAJO")["piece_count"] -= 1
            incomplete_html = render_room_3d_html(incomplete)
            incomplete_match = re.search(
                r'<script id="scene-data" type="application/json">(.*?)</script>',
                incomplete_html, re.DOTALL,
            )
            incomplete_payload = json.loads(incomplete_match.group(1))
            self.assertEqual(len(incomplete_payload["drawers"]), 2)
            self.assertTrue(any(item["id"].endswith("-D2")
                                for item in incomplete_payload["blocked_drawers"]))

    def test_real_f7c_back_variants_are_distinct_and_match_d19_outputs(self) -> None:
        back3 = {"style": "inset_full", "material_id": "HDF_3_LAB",
                 "thickness_mm": 3, "services_present": False, "grain_axis": "none"}
        carcass = {"style": "inset_full", "material_id": "MELAMINA_18_LAB",
                   "thickness_mm": 18, "services_present": False, "grain_axis": "none"}
        with tempfile.TemporaryDirectory() as output_root:
            results = [
                self.generate(room_request(back), project, output_root)
                for back, project in ((back3, "H9_M2_BACK3"),
                                      (carcass, "H9_M2_BACKCARCASS"))
            ]
            digests = []
            for result, expected_thickness in zip(results, (3, 18)):
                with ZipFile(result["room_package_path"]) as archive:
                    self.assertIsNone(archive.testzip())
                    review = json.loads(archive.read("04-habitacion.json"))
                    manifest = json.loads(archive.read("MANIFEST.json"))
                    html = archive.read("01-visor-3d.html").decode("utf-8")
                    rows = list(csv.DictReader(io.StringIO(
                        archive.read("06-paneles-en-escena.csv").decode("utf-8")
                    )))
                self.assertEqual(review["layout_sha256"], result["layout_sha256"])
                self.assertEqual(manifest["layout_sha256"], result["layout_sha256"])
                back_boxes = [box for box in review["world_boxes"]
                              if box["group_id"] == "LAB_MAIN" and box["role"] == "back_full"]
                self.assertEqual(len(back_boxes), 1)
                self.assertEqual(back_boxes[0]["size_xyz_mm"][2], expected_thickness)
                box_ids = {box["piece_id"] for box in review["world_boxes"]}
                self.assertIn(back_boxes[0]["piece_id"], {row["piece_id"] for row in rows})
                self.assertEqual(box_ids, {row["piece_id"] for row in rows})
                payload_match = re.search(
                    r'<script id="scene-data" type="application/json">(.*?)</script>',
                    html, re.DOTALL,
                )
                payload = json.loads(payload_match.group(1))
                self.assertEqual(box_ids, {box["id"] for box in payload["boxes"]})
                self.assertEqual(payload["groups"][0]["construction"]["back_status"],
                                 "inset_full")
                pending_group = next(group for group in payload["groups"]
                                     if group["id"] == "LAB_PENDING")
                self.assertEqual(pending_group["construction"]["back_status"], "pending")
                digests.append(review["layout_sha256"])
                for name, info in manifest["files"].items():
                    with ZipFile(result["room_package_path"]) as archive:
                        data = archive.read(name)
                    self.assertEqual(len(data), info["bytes"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), info["sha256"])
                for flag in FLAGS:
                    self.assertIs(result[flag], False, flag)
            self.assertNotEqual(digests[0], digests[1])

            invalid = copy.deepcopy(back3)
            invalid["services_present"] = True
            invalid_request = room_request(invalid)
            invalid_path = Path(output_root) / "H9_M2_INVALID_SERVICES-room-review.zip"
            with self.assertRaises(ValueError):
                self.generate(invalid_request, "H9_M2_INVALID_SERVICES", output_root)
            self.assertFalse(invalid_path.exists())

    def test_wall_support_stays_pending_and_never_changes_h9_geometry(self) -> None:
        request = {
            "review_kind": "kitchen_spatial_v1",
            "review_state": copy.deepcopy(self.state), "service_zones": [],
        }
        review = carpinova_consultar(json.dumps(request, ensure_ascii=False))
        self.assertEqual(review["piece_count"], 42)
        self.assertEqual(review["layout_sha256"], H9_LAYOUT_SHA256_M1)
        alto = review["construction_review_by_group"]["ALTO"]
        self.assertEqual(alto["back_status"], "none")
        self.assertEqual(alto["wall_support_status"], "REAR_WALL_SUPPORT_PENDING")
        self.assertEqual(alto["wall_tie_mode"], "NOT_IMPLEMENTED")
        self.assertIs(alto["install_ready"], False)
        self.assertTrue(any("REAR_WALL_SUPPORT_PENDING" in warning
                            for warning in review["warnings"]))
        self.assertFalse(any(box["role"].startswith("back_") or "TIE" in box["piece_id"]
                             for box in review["world_boxes"]))
        for flag in FLAGS:
            self.assertIs(review[flag], False, flag)

        # The safe layout summary explicitly distinguishes a chosen absence from a pending choice.
        state_review = carpinova_consultar(json.dumps(room_request("none"), ensure_ascii=False))
        statuses = state_review["construction_review_by_group"]
        self.assertEqual(statuses["LAB_MAIN"]["back_status"], "none")
        self.assertEqual(statuses["LAB_PENDING"]["back_status"], "pending")
        html = render_room_3d_html(state_review)
        payload_match = re.search(
            r'<script id="scene-data" type="application/json">(.*?)</script>',
            html, re.DOTALL,
        )
        payload = json.loads(payload_match.group(1))
        group_statuses = {group["id"]: group["construction"]["back_status"]
                          for group in payload["groups"]}
        self.assertEqual(group_statuses, {"LAB_MAIN": "none", "LAB_PENDING": "pending"})


if __name__ == "__main__":
    unittest.main()
