"""F9B × D18 × D19 NEW combined public acceptance; not a historical replay.

Requires real Maestro/F6/CADExchange through room_layout_v1 and the D19 writer.
Not a Codex Desktop MCP transport test, fabrication approval, or a render mock.
"""
from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent.room_review_package import write_room_review_package


def _spec(module_id: str, width: int, *, corner: bool) -> dict:
    module = {
        "module_id": module_id,
        "width_mm": width,
        "panel_thickness_mm": 18,
        "material_id": "MELAMINA_18",
        "construction": "sides_full",
        "support": "floor",
        "fronts": "none",
        "back": "none",
        "drawers": "none",
    }
    if corner:
        module["corner_blind"] = {
            "side": "right",
            "blind_width_mm": 420,
            "access_door": {
                "material_id": "MELAMINA_18",
                "thickness_mm": 18,
                "gap_left_mm": 3, "gap_right_mm": 3,
                "gap_top_mm": 3, "gap_bottom_mm": 3,
                "hinge_side": "left",
            },
        }
    return {
        "type": "modular_run", "application": "kitchen",
        "width_mm": width, "height_mm": 720, "depth_mm": 560,
        "installation": "freestanding", "modules": [module],
    }


def _request() -> dict:
    return {
        "review_kind": "room_layout_v1",
        "assemblies": [
            {"group_id": "CIEGO", "module_spec": _spec("CIEGO", 900, corner=True),
             "origin_xyz_mm": [0, 0, 0], "rotation_deg": 0},
            {"group_id": "RECTO", "module_spec": _spec("RECTO", 600, corner=False),
             "origin_xyz_mm": [900, 0, 0], "rotation_deg": 90},
        ],
        "service_zones": [],
    }


class F9BD18D19PublicAcceptance(unittest.TestCase):
    def test_one_real_public_room_to_portable_zip(self):
        request = _request()
        room = carpinova_consultar(json.dumps(request, ensure_ascii=False))
        self.assertEqual(room["status"], "REVIEW_ONLY")
        self.assertEqual(room["piece_count"], 10)
        self.assertEqual([g["piece_count"] for g in room["groups"]], [6, 4])
        self.assertEqual(room["envelope_collisions"], [])
        self.assertEqual(room["panel_collisions"], [])
        fronts = {p["role"]: p for p in room["world_boxes"]
                  if p["role"] in {"front_corner_blind", "front_corner_access"}}
        self.assertEqual(fronts["front_corner_blind"]["size_xyz_mm"], [420, 720, 18])
        self.assertEqual(fronts["front_corner_access"]["origin_xyz_mm"], [21, 21, 0])
        self.assertEqual(fronts["front_corner_access"]["size_xyz_mm"], [456, 678, 18])
        self.assertIn("CORNER_JOINT_AND_FILLER_NOT_DESIGNED", room["warnings"])
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready",
                     "purchase_ready", "can_generate_f7c"):
            self.assertIs(room[flag], False)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "review.zip"
            result = write_room_review_package(request, output, y_mm=350)
            self.assertEqual(result["piece_count"], 10)
            self.assertEqual(result["release"], "NO_GO")
            with ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                html = archive.read("01-visor-3d.html").decode("utf-8")
                section = archive.read("03-seccion.svg").decode("utf-8")
                self.assertIn("front_corner_access", html)
                self.assertIn("front_corner_blind", html)
                self.assertIn("front_corner_access", section)
                self.assertIn("front_corner_blind", section)
                self.assertEqual(json.loads(archive.read("04-habitacion.json"))
                                 ["layout_sha256"], room["layout_sha256"])
                rows = list(csv.DictReader(io.StringIO(
                    archive.read("06-paneles-en-escena.csv").decode("utf-8"))))
                self.assertEqual(len(rows), 10)
                self.assertTrue(all(row["NOT_FOR_CUTTING"] == "TRUE"
                                    for row in rows))
                self.assertEqual(json.loads(archive.read("MANIFEST.json"))
                                 ["release"], "NO_GO")


if __name__ == "__main__":
    unittest.main()
