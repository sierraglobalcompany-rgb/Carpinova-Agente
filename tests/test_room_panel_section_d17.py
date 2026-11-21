"""New D17 tool tests only. No D12–D16 suite replay."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from carpinova_agent.room_panel_section import main, render_room_panel_section_svg


# Synthetic, explicit WORLD boxes (not a client CADExchange); only tests renderer.
def scene() -> dict:
    return {
        "review_kind": "room_layout_v1", "status": "REVIEW_ONLY",
        "fabrication_ready": False, "cutting_ready": False,
        "drilling_ready": False, "purchase_ready": False,
        "can_generate_f7c": False,
        "groups": [{"group_id": "BASE_A", "origin_xyz_mm": [0,0,0],
                    "bounds_xyz_mm": [900,720,560]}],
        "world_boxes": [
            {"group_id":"BASE_A", "piece_id":"BASE_A:LEFT_SIDE",
             "role":"left_side","origin_xyz_mm":[0,0,0],
             "size_xyz_mm":[18,720,560]},
            {"group_id":"BASE_A", "piece_id":"BASE_A:BOTTOM",
             "role":"bottom","origin_xyz_mm":[18,0,0],
             "size_xyz_mm":[864,18,560]},
            {"group_id":"BASE_A", "piece_id":"BASE_A:FRONT_X",
             "role":"front_corner_blind","origin_xyz_mm":[480,0,0],
             "size_xyz_mm":[420,720,18]},
        ],
        "service_zones":[{"zone_id":"PIPE", "origin_xyz_mm":[100,10,100],
                          "size_xyz_mm":[40,150,40], "purpose":"plumbing"}],
        "envelope_collisions": [], "panel_collisions": [],
        "warnings": ["ALL_GEOMETRY_NOMINAL_NO_CUT_AUTHORITY"],
    }


class RoomPanelSectionD17(unittest.TestCase):
    def test_at_y_350_uses_real_world_boxes_not_envelope_as_panel(self):
        source = scene()
        before = copy.deepcopy(source)
        root = ET.fromstring(render_room_panel_section_svg(source, y_mm=350))
        pieces = [e.attrib["data-piece-id"] for e in root.iter()
                  if "data-piece-id" in e.attrib]
        self.assertEqual(pieces, ["BASE_A:LEFT_SIDE", "BASE_A:FRONT_X"])
        self.assertEqual(source, before)
        self.assertIn("NO CORTAR", "".join(root.itertext()))

    def test_y_10_includes_bottom_and_plumbing_zone(self):
        root = ET.fromstring(render_room_panel_section_svg(scene(), y_mm=10))
        self.assertEqual(len([e for e in root.iter() if
                             e.attrib.get("data-piece-id") == "BASE_A:BOTTOM"]), 1)
        self.assertIn("Reserva PIPE", "".join(root.itertext()))

    def test_cad_coords_are_used_as_is_with_z_down(self):
        root = ET.fromstring(render_room_panel_section_svg(scene(), y_mm=350))
        p = next(e for e in root.iter() if e.attrib.get("data-piece-id") == "BASE_A:FRONT_X")
        self.assertEqual([p.attrib[k] for k in ("x","y","width","height")],
                         ["535","125","420","18"])

    def test_escapes_untrusted_labels_without_svg_script(self):
        data = scene()
        data["world_boxes"][0]["piece_id"] = 'BASE_A:<svg onload="bad">'
        data["groups"][0]["group_id"] = 'BASE_A & TEST'
        for p in data["world_boxes"]:
            p["group_id"] = 'BASE_A & TEST'
        svg = render_room_panel_section_svg(data, y_mm=350)
        root = ET.fromstring(svg)
        self.assertNotIn("<svg onload", svg)
        self.assertIn("BASE_A:<svg", "".join(root.itertext()))

    def test_fails_closed_on_permission_or_untrusted_review_kind(self):
        for key, value in [("fabrication_ready",True), ("purchase_ready",None),
                           ("review_kind","fake_room"), ("status","FABRICATE")]:
            data = scene()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                render_room_panel_section_svg(data,y_mm=350)

    def test_malformed_measurements_and_duplicate_pieces_rejected(self):
        for key, value in [("origin_xyz_mm",[-1,0,0]),
                           ("size_xyz_mm",[True,720,560]),
                           ("size_xyz_mm",[18,0,560])]:
            data = scene()
            data["world_boxes"][0][key] = value
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                render_room_panel_section_svg(data,y_mm=350)
        data = scene()
        data["world_boxes"][1]["piece_id"] = data["world_boxes"][0]["piece_id"]
        with self.assertRaises(ValueError):
            render_room_panel_section_svg(data,y_mm=350)

    def test_height_must_be_integer_and_in_range(self):
        for height in (True, -1, 20001, 10.2):
            with self.subTest(height=height), self.assertRaises(ValueError):
                render_room_panel_section_svg(scene(),y_mm=height)

    def test_cli_rebuilds_from_specs_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp, out = root/"room.json", root/"section.svg"
            request = {"review_kind":"room_layout_v1", "assemblies": [], "service_zones":[]}
            inp.write_text(json.dumps(request),encoding="utf-8")
            calls = []
            shim = types.ModuleType("carpinova_agent.room_spatial")
            def verified(value):
                calls.append(value)
                return scene()
            shim.review_room_from_specs = verified
            with patch.dict(sys.modules, {"carpinova_agent.room_spatial": shim}):
                self.assertEqual(main(["--input",str(inp),"--output",str(out),"--y-mm","350"]),0)
                self.assertEqual(calls,[request])
                self.assertIn("BASE_A:FRONT_X",out.read_text(encoding="utf-8"))
                with self.assertRaises(FileExistsError):
                    main(["--input",str(inp),"--output",str(out),"--y-mm","350"])

    def test_interference_warning_remains_visible(self):
        data = scene()
        data["status"] = "INTERFERENCE_REVIEW_REQUIRED"
        root = ET.fromstring(render_room_panel_section_svg(data,y_mm=350))
        self.assertIn("REVISAR INTERFERENCIAS", "".join(root.itertext()))


if __name__=="__main__":
    unittest.main()
