"""D17×F9A: one NEW focal integration test; not a replay of F9A suites.

Uses existing public Maestro/MCP path and verifies that the D17 read-only
section consumes the *real* F9A panel emitted by that path.
"""
from __future__ import annotations

import json
import unittest
import xml.etree.ElementTree as ET

from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent.room_panel_section import render_room_panel_section_svg


def cabinet(name: str, width: int, *, corner: bool) -> dict:
    module = {
        "module_id": name, "width_mm": width,
        "panel_thickness_mm": 18, "material_id": "MELAMINA_18",
        "construction": "sides_full", "support": "floor",
        "fronts": "none", "back": "none", "drawers": "none",
    }
    if corner:
        module["corner_blind"] = {"side": "right", "blind_width_mm": 420}
    return {
        "type": "modular_run", "application": "kitchen",
        "width_mm": width, "height_mm": 720, "depth_mm": 560,
        "installation": "freestanding", "modules": [module],
    }


class F9AD17ActualPublicIntegration(unittest.TestCase):
    def test_public_nominal_cad_panel_visible_in_d17_section(self):
        request = {
            "review_kind": "room_layout_v1",
            "assemblies": [
                {"group_id": "CIEGO", "module_spec": cabinet("CIEGO", 900, corner=True),
                 "origin_xyz_mm": [0, 0, 0], "rotation_deg": 0},
                {"group_id": "RECTO", "module_spec": cabinet("RECTO", 600, corner=False),
                 "origin_xyz_mm": [900, 0, 0], "rotation_deg": 90},
            ],
            "service_zones": [],
        }
        answer = carpinova_consultar(json.dumps(request, ensure_ascii=False))
        self.assertEqual(answer["status"], "REVIEW_ONLY")
        self.assertEqual(answer["piece_count"], 9)
        self.assertEqual(answer["envelope_collisions"], [])
        self.assertIn("CORNER_JOINT_AND_FILLER_NOT_DESIGNED", answer["warnings"])
        pieces = [p for p in answer["world_boxes"]
                  if p["role"] == "front_corner_blind"]
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0]["piece_id"], "CIEGO:CIEGO-FRONT_CORNER_BLIND")
        self.assertEqual(pieces[0]["origin_xyz_mm"], [480, 0, 0])
        self.assertEqual(pieces[0]["size_xyz_mm"], [420, 720, 18])
        for key in ("fabrication_ready", "cutting_ready", "drilling_ready",
                    "purchase_ready", "can_generate_f7c"):
            self.assertIs(answer[key], False, key)
        root = ET.fromstring(render_room_panel_section_svg(answer, y_mm=350))
        visible = [e for e in root.iter() if
                   e.attrib.get("data-role") == "front_corner_blind"]
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].get("data-piece-id"),
                         "CIEGO:CIEGO-FRONT_CORNER_BLIND")
        self.assertEqual(visible[0].get("width"), "420")
        self.assertEqual(visible[0].get("height"), "18")
        self.assertIn("NO CORTAR", "".join(root.itertext()))


if __name__ == "__main__":
    unittest.main()
