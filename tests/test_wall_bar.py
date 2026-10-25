"""Focused regression for a wall-mounted-left bar with right-side floor drawer pedestal."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from carpinova_agent.core import DesignError
from carpinova_agent.wall_bar import design_wall_bar
from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.wall_bar_sheets import (part_schedule, part_schedule_csv,
                                              part_schedule_svg, wall_bar_orientation_svg)
from xml.etree import ElementTree
from integrations.cad_native import native_boxes

FILE = Path(__file__).resolve().parents[1] / "examples/wall-bar-900-review.json"


def spec():
    return json.loads(FILE.read_text(encoding="utf-8"))["module_spec"]


class WallBarTests(unittest.TestCase):
    def model(self):
        return design_wall_bar(spec())

    def test_21_real_panels_and_cad_agree(self):
        m = self.model()
        cad = cad_exchange(m)
        self.assertEqual(m["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(cad["bounds_xyz_mm"], [900, 900, 460])
        self.assertEqual(len(m["parts"]), 21)
        self.assertEqual(len(cad["boxes"]), 21)
        self.assertEqual({p["piece_id"] for p in m["parts"]},
                         {p["piece_id"] for p in cad["boxes"]})
        self.assertEqual(len(native_boxes(cad)), 21)
        self.assertEqual(validate_exchange(cad), cad)
        for key in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(m[key], False)
        for key in ("fabrication_ready", "cutting_ready", "drilling_ready"):
            self.assertIs(cad[key], False)

    def test_exactly_one_cover_no_left_panel(self):
        boxes = cad_exchange(self.model())["boxes"]
        cover = [b for b in boxes if b["piece_id"] == "BAR-COVER-TOP"]
        self.assertEqual(len(cover), 1)
        self.assertEqual(cover[0]["origin_xyz_mm"], [0, 885, 0])
        self.assertEqual(cover[0]["size_xyz_mm"], [900, 15, 460])
        self.assertTrue(all(b["origin_xyz_mm"][0] >= 600 or b["origin_xyz_mm"][1] >= 885
                            for b in boxes))
        self.assertEqual(len([b for b in boxes if b["role"] == "back_full"]), 1)

    def test_no_double_front_and_drawer_order(self):
        boxes = cad_exchange(self.model())["boxes"]
        self.assertFalse(any(b["role"] == "drawer_front_wall" for b in boxes))
        faces = {b["piece_id"].split("-")[1]: b for b in boxes
                 if b["role"] == "drawer_facade"}
        self.assertEqual(set(faces), {"D1", "D2", "D3"})
        self.assertEqual([faces[k]["size_xyz_mm"][1] for k in ("D1", "D2", "D3")],
                         [180, 180, 477])
        self.assertGreater(faces["D1"]["origin_xyz_mm"][1],
                           faces["D2"]["origin_xyz_mm"][1])
        self.assertGreater(faces["D2"]["origin_xyz_mm"][1],
                           faces["D3"]["origin_xyz_mm"][1])

    def test_panels_and_sheets_share_ids(self):
        m = self.model()
        ids = {b["piece_id"] for b in cad_exchange(m)["boxes"]}
        schedule = part_schedule(m)
        self.assertEqual(ids, {p["piece_id"] for p in schedule})
        self.assertIn("CAJONERA_DERECHA-D1-DRAWER_FACADE", part_schedule_csv(m))
        self.assertIn("BAR-COVER-TOP", part_schedule_svg(m))
        self.assertEqual(sum(p["edge_policy"].startswith("RIGIDO") for p in schedule), 3)

    def test_orientation_A_is_explicit_and_cad_proven(self):
        model = self.model()
        review = model["wall_bar_review"]
        self.assertEqual(review["drawer_opening_face"], "long_side_front")
        self.assertEqual(review["drawer_open_direction"], "negative_Z")
        cad = validate_exchange(cad_exchange(model))
        fronts = [b for b in cad["boxes"] if b["role"] == "drawer_facade"]
        self.assertEqual(len(fronts), 3)
        self.assertTrue(all(b["origin_xyz_mm"][2] == 0 and
                            b["origin_xyz_mm"][0] >= 600 and
                            b["origin_xyz_mm"][0] + b["size_xyz_mm"][0] <= 900 and
                            b["size_xyz_mm"][0] == 296 for b in fronts))
        sheet = wall_bar_orientation_svg(model)
        ElementTree.fromstring(sheet)
        self.assertIn("ORIENTACION A CONFIRMADA", sheet)
        self.assertIn("BAR-COVER-TOP", sheet)
        self.assertIn("CAJONERA_DERECHA-D1-DRAWER_FACADE", sheet)

    def test_physical_interfaces_are_derived_and_not_approved(self):
        m = self.model()
        review = m["wall_bar_review"]
        self.assertEqual(review["drawer_base_clearance_mm"]["D3"], 2)
        self.assertEqual(review["drawer_rear_clearance_mm"]["D3"], 30)
        self.assertEqual(set(review["drawer_front_side_contact"]), {"D1", "D2", "D3"})
        self.assertTrue(all(v == "GEOMETRIC_PLANE_ONLY_NOT_FASTENED"
                            for v in review["drawer_front_side_contact"].values()))
        self.assertTrue(any("D3: holgura vertical inferior nominal de 2 mm"
                            in blocker for blocker in m["blockers"]))
        self.assertEqual(len(m["parts"]), 21)
        self.assertEqual(cad_exchange(m)["geometry_sha256"],
                         "a689b5742709e83ae691ec5c16ec4d81b82ac19ba021ecc62f3d92211eeba58b")
        self.assertFalse(m["fabrication_ready"])
        self.assertFalse(m["cutting_ready"])
        self.assertFalse(m["drilling_ready"])
        self.assertFalse(m["purchase_ready"])

    def test_no_mutation(self):
        request = spec()
        before = copy.deepcopy(request)
        design_wall_bar(request)
        self.assertEqual(request, before)

    def test_wrong_configuration_fails_closed(self):
        for scenario in ("wall", "orientation_B", "orientation_missing", "feet", "cabinet", "front", "span", "extra"):
            request = spec()
            if scenario == "wall":
                request["wall_side"] = "right"
            elif scenario == "orientation_B":
                request["drawer_opening_face"] = "short_free_end"
            elif scenario == "orientation_missing":
                del request["drawer_opening_face"]
            elif scenario == "feet":
                request["feet_height_mm"] = 80
            elif scenario == "cabinet":
                request["cabinet_module"]["width_mm"] = 900
            elif scenario == "front":
                request["cabinet_module"]["drawers"][0]["front_construction"] = "separate"
            elif scenario == "span":
                request["free_span_mm"] = 900
            else:
                request["extra_phantom_left_panel"] = True
            with self.subTest(scenario=scenario), self.assertRaises(DesignError):
                design_wall_bar(request)


if __name__ == "__main__":
    unittest.main()
