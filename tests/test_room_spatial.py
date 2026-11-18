"""D5 focal QA against real prevalidated D4 CADExchange bundle bytes."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "carpinova_agent" / "room_spatial.py"
spec = importlib.util.spec_from_file_location("carpinova_agent.room_spatial", MODULE_PATH)
spatial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spatial)


def load(group: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / "room_spatial" / f"{group}_cad-exchange.json").read_text())


def group(name: str, origin=None, rotation=0) -> dict:
    return {"group_id": name, "exchange": load(name),
            "origin_xyz_mm": origin if origin is not None else [0, 0, 0],
            "rotation_deg": rotation}


def kitchen() -> list[dict]:
    return [group("BAJO"), group("ALTO", [0, 1420, 0]),
            group("TORRE", [1100, 0, 0], 90)]


def zone(lo, size=(25, 25, 25), purpose="plumbing", name="S1"):
    return {"zone_id": name, "purpose": purpose,
            "origin_xyz_mm": list(lo), "size_xyz_mm": list(size)}


class SpatialRoomD5Tests(unittest.TestCase):
    def test_real_d4_bundles_compose_42_globally_unique_pieces(self):
        result = spatial.compose_verified_exchanges(kitchen())
        self.assertEqual(result["status"], "REVIEW_ONLY")
        self.assertEqual(result["piece_count"], 42)
        self.assertEqual(len(set(result["global_piece_ids"])), 42)
        self.assertEqual([g["piece_count"] for g in result["groups"]], [29, 6, 7])
        self.assertEqual(result["groups"][2]["bounds_xyz_mm"], [618, 2100, 600])
        self.assertFalse(result["envelope_collisions"])
        self.assertIn("CORNER_JOINT_AND_FILLER_NOT_DESIGNED", result["warnings"])
        for flag in spatial.PHYSICAL_FLAGS:
            self.assertIs(result[flag], False)

    def test_rotation_four_quadrants_preserves_panel_dimensions_and_integrity(self):
        cad = load("TORRE")
        source = cad["boxes"][0]
        boxes = []
        for degrees, bounds in [(0, [600, 2100, 618]), (90, [618, 2100, 600]),
                                (180, [600, 2100, 618]), (270, [618, 2100, 600])]:
            res = spatial.compose_verified_exchanges([group("TORRE", [300, 0, 100], degrees)])
            self.assertEqual(res["groups"][0]["bounds_xyz_mm"], bounds)
            boxes.append(res["world_boxes"][0])
            self.assertEqual(res["groups"][0]["geometry_sha256"], cad["geometry_sha256"])
            self.assertEqual(res["piece_count"], len(cad["boxes"]))
        self.assertEqual(boxes[0]["size_xyz_mm"], source["size_xyz_mm"])
        self.assertEqual(boxes[1]["size_xyz_mm"], [source["size_xyz_mm"][2],
                                                      source["size_xyz_mm"][1],
                                                      source["size_xyz_mm"][0]])
        self.assertEqual(len(set(tuple(b["origin_xyz_mm"]) for b in boxes)), 4)

    def test_moving_a_group_only_changes_layout_sha_not_f6_geometry_sha(self):
        first = spatial.compose_verified_exchanges(kitchen())
        moved = kitchen();moved[2]["origin_xyz_mm"] = [1200, 0, 0]
        second = spatial.compose_verified_exchanges(moved)
        self.assertNotEqual(first["layout_sha256"], second["layout_sha256"])
        self.assertEqual([g["geometry_sha256"] for g in first["groups"]],
                         [g["geometry_sha256"] for g in second["groups"]])

    def test_layout_sha_is_independent_of_assembly_and_zone_input_order(self):
        a = kitchen()
        z = [zone([100, 100, 100], name="A"),zone([130, 100, 100], name="B")]
        first = spatial.compose_verified_exchanges(a,z)
        second = spatial.compose_verified_exchanges(list(reversed(a)),list(reversed(z)))
        self.assertEqual(first["layout_sha256"], second["layout_sha256"])

    def test_overlapping_envelopes_rejected_even_if_no_panel_intersection(self):
        a = [group("BAJO"), group("ALTO", [0, 700, 0])]
        result = spatial.compose_verified_exchanges(a)
        self.assertEqual(result["status"], "INTERFERENCE_REVIEW_REQUIRED")
        self.assertEqual(result["envelope_collisions"][0]["groups"], ["BAJO", "ALTO"])
        self.assertEqual(result["envelope_collisions"][0]["overlap_xyz_mm"], [1000, 100, 365])

    def test_touching_faces_not_reported_as_penetration(self):
        a=[group("BAJO"), group("TORRE", [1000, 0, 0])]
        result=spatial.compose_verified_exchanges(a)
        self.assertEqual(result["status"], "REVIEW_ONLY")
        self.assertEqual(result["envelope_collisions"], [])

    def test_reservation_inside_empty_cabinet_is_nominal_not_hole(self):
        result=spatial.compose_verified_exchanges(kitchen(),[zone([100,100,100],(40,40,40))])
        self.assertEqual(result["service_zones"][0]["status"], "CLEAR_NOMINAL_ONLY")
        self.assertIn("BAJO",result["service_zones"][0]["fully_contained_by"])
        self.assertEqual(result["service_zones"][0]["intersected_piece_ids"], [])
        self.assertIn("SERVICE_RESERVATIONS_ARE_NOT_HOLES_OR_PLUMBING_INSTALLATION",result["warnings"])

    def test_reservation_crossing_real_panel_blocks_and_cites_piece(self):
        result=spatial.compose_verified_exchanges(kitchen(),[zone([1,100,30],(30,40,40))])
        self.assertEqual(result["status"], "INTERFERENCE_REVIEW_REQUIRED")
        self.assertEqual(result["service_zones"][0]["status"], "PANEL_INTERFERENCE")
        self.assertIn("BAJO:KITCHEN_LEFT-LEFT_SIDE", result["service_zones"][0]["intersected_piece_ids"])

    def test_reservation_partially_outside_a_group_cannot_claim_clear(self):
        result=spatial.compose_verified_exchanges([group("BAJO")],[zone([100,400,500],(30,30,50))])
        self.assertEqual(result["service_zones"][0]["status"], "PARTIAL_ENVELOPE_OVERLAP")
        self.assertEqual(result["status"], "INTERFERENCE_REVIEW_REQUIRED")

    def test_reservation_completely_outside_declared_group_stays_noncertified(self):
        result=spatial.compose_verified_exchanges([group("BAJO")],[zone([1200,100,100])])
        self.assertEqual(result["service_zones"][0]["status"], "OUTSIDE_CABINETS")

    def test_rejects_corrupted_geometry_hash_and_client_altered_cad(self):
        a = kitchen(); a[0]["exchange"]["boxes"][0]["size_xyz_mm"][1] += 1
        with self.assertRaisesRegex(ValueError,"integridad"):
            spatial.compose_verified_exchanges(a)
        a = kitchen(); a[0]["exchange"]["fabrication_ready"] = True
        with self.assertRaisesRegex(ValueError,"certificación nominal"):
            spatial.compose_verified_exchanges(a)

    def test_rejects_duplicate_group_and_box_identifiers(self):
        with self.assertRaisesRegex(ValueError,"group_id duplicado"):
            spatial.compose_verified_exchanges([group("BAJO"),group("BAJO",[1100,0,0])])
        a=[group("BAJO")]
        a[0]["exchange"]["boxes"][1]["piece_id"]=a[0]["exchange"]["boxes"][0]["piece_id"]
        a[0]["exchange"]["geometry_sha256"]=spatial._hash({k:v for k,v in a[0]["exchange"].items() if k!="geometry_sha256"})
        with self.assertRaisesRegex(ValueError,"pieza duplicada"):
            spatial.compose_verified_exchanges(a)

    def test_invalid_coordinates_and_rotations_fail_closed(self):
        mutations = [
            ("origin_xyz_mm", [True,0,0]),("origin_xyz_mm",[-1,0,0]),
            ("origin_xyz_mm",[0,0]), ("origin_xyz_mm",[19999,0,0]),
            ("rotation_deg", True),("rotation_deg",45),
        ]
        for field,value in mutations:
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                a=[group("BAJO")];a[0][field]=value
                spatial.compose_verified_exchanges(a)

    def test_service_zone_schema_limits_and_nonfinite_rejected(self):
        inputs = [
            [zone([0,0,0],(0,1,1))],
            [zone([0,0,0],(1,1,1),purpose="machining")],
            [zone([0,0,0]), zone([500,0,0])],
            [zone([float('nan'),0,0])],
            [zone([0,0,0],name="bad/../path")],
            [zone([0,0,0]) for _ in range(13)],
        ]
        for z in inputs:
            with self.subTest(z=repr(z)[:40]),self.assertRaises(ValueError):
                spatial.compose_verified_exchanges([group("BAJO")],z)

    def test_unexpected_cad_and_assembly_fields_rejected(self):
        a=[group("BAJO")];a[0]["extra"]="injected"
        with self.assertRaises(ValueError):spatial.compose_verified_exchanges(a)
        a=[group("BAJO")];a[0]["exchange"]["hardware_included"]=True
        a[0]["exchange"]["geometry_sha256"]=spatial._hash({k:v for k,v in a[0]["exchange"].items() if k!="geometry_sha256"})
        with self.assertRaises(ValueError):spatial.compose_verified_exchanges(a)

    def test_revisions_are_deterministic_for_same_input(self):
        first=spatial.compose_verified_exchanges(kitchen(),[zone([100,100,100])])
        second=spatial.compose_verified_exchanges(kitchen(),[zone([100,100,100])])
        self.assertEqual(first,second)


class SpatialPublicTrustBoundaryTests(unittest.TestCase):
    def test_wrapper_generates_internal_f6_cad_and_rejects_client_cad(self):
        import sys
        import types
        from unittest.mock import patch
        pkg=types.ModuleType("carpinova_agent")
        pkg.__path__ = []
        maestro=types.ModuleType("carpinova_agent.maestro")
        cad=types.ModuleType("carpinova_agent.cad_exchange")
        flags={name: False for name in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")}
        calls=[]
        def fake_maestro(req):
            calls.append(req)
            return {"status":"DRAFT_NOT_FOR_CUTTING","modular": {"status":"DRAFT_NOT_FOR_CUTTING", "mock":"BAJO",**flags},**flags}
        maestro.consult_maestro=fake_maestro
        cad.cad_exchange=lambda model: load(model["mock"])
        def verified(exchange):
            self.assertEqual(exchange["geometry_sha256"], spatial._hash({k:v for k,v in exchange.items() if k!="geometry_sha256"}))
            return exchange
        cad.validate_exchange=verified
        args={"review_kind":"room_layout_v1","assemblies":[{
            "group_id":"BAJO","module_spec":{"type":"modular_run", "mock":"placeholder"},
            "origin_xyz_mm":[0,0,0],"rotation_deg":0}], "service_zones":[]}
        with patch.dict(sys.modules,{"carpinova_agent":pkg,"carpinova_agent.maestro":maestro,"carpinova_agent.cad_exchange":cad}):
            old_package=spatial.__package__
            spatial.__package__="carpinova_agent"
            try:
                result=spatial.review_room_from_specs(args)
                self.assertEqual(result["piece_count"],29)
                self.assertEqual(calls[0]["action"],"modular")
                bad=copy.deepcopy(args)
                bad["assemblies"][0]["exchange"]=load("BAJO")
                with self.assertRaisesRegex(ValueError,"assembly: use"):
                    spatial.review_room_from_specs(bad)
            finally:
                spatial.__package__=old_package

    def test_wrapper_rejects_f6_release_flags_without_using_cad(self):
        import sys,types
        from unittest.mock import patch
        pkg=types.ModuleType("carpinova_agent");pkg.__path__=[]
        maestro=types.ModuleType("carpinova_agent.maestro")
        cad=types.ModuleType("carpinova_agent.cad_exchange")
        maestro.consult_maestro=lambda request: {
            "status":"DRAFT_NOT_FOR_CUTTING", "modular": {
                "status":"DRAFT_NOT_FOR_CUTTING", "fabrication_ready":True,
                "cutting_ready":False,"drilling_ready":False,"purchase_ready":False},
            "fabrication_ready":True,"cutting_ready":False,"drilling_ready":False,"purchase_ready":False}
        cad.cad_exchange=lambda model: self.fail("CAD should not be called")
        cad.validate_exchange=lambda data: data
        args={"review_kind":"room_layout_v1","assemblies":[{
            "group_id":"BAJO","module_spec":{},"origin_xyz_mm":[0,0,0],"rotation_deg":0}],"service_zones":[]}
        with patch.dict(sys.modules,{"carpinova_agent":pkg,"carpinova_agent.maestro":maestro,"carpinova_agent.cad_exchange":cad}):
            old=spatial.__package__;spatial.__package__="carpinova_agent"
            try:
                with self.assertRaisesRegex(ValueError,"modelo nominal seguro"):
                    spatial.review_room_from_specs(args)
            finally:spatial.__package__=old


class SpatialTopViewTests(unittest.TestCase):
    def test_svg_top_view_uses_verified_group_envelopes(self):
        from xml.etree import ElementTree as ET
        result = spatial.compose_verified_exchanges(kitchen(), [zone([100, 100, 100])])
        svg = spatial.render_top_view_svg(result)
        root = ET.fromstring(svg)
        rectangles = root.findall('{http://www.w3.org/2000/svg}rect')
        self.assertEqual(len(rectangles), 4)
        labels = root.findall('{http://www.w3.org/2000/svg}text')
        self.assertEqual({label.text for label in labels}, {"BAJO", "ALTO", "TORRE"})
        self.assertIn('no fabricable', svg)

    def test_svg_rejects_unlocked_fabrication_status(self):
        r = spatial.compose_verified_exchanges([group("BAJO")])
        r["fabrication_ready"] = True
        with self.assertRaisesRegex(ValueError, "nominal bloqueado"):
            spatial.render_top_view_svg(r)

    def test_svg_never_injects_markup_from_identifiers(self):
        bad = [group("BAJO")]
        bad[0]["group_id"] = 'bad<svg>'
        with self.assertRaisesRegex(ValueError, "ID inválido"):
            spatial.compose_verified_exchanges(bad)


if __name__ == "__main__":
    unittest.main()
