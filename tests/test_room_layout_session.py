"""D7 nominal room edit regression using real D5 spatial & original D4 CAD fixtures.

Only the Maestro/F6 producer is replaced by a deterministic fixture builder here;
full unmocked Maestro/CAD E2E remains an explicit separate acceptance gate.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent import room_spatial as spatial

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "room_spatial"
PHYSICAL_FLAGS = tuple(spatial.PHYSICAL_FLAGS)


def assembly(gid, origin, rotation=0):
    return {"group_id": gid, "module_spec": {"type": "modular_run", "fixture": gid},
            "origin_xyz_mm": origin, "rotation_deg": rotation}


def seed():
    return [assembly("BAJO", [0, 0, 0]), assembly("ALTO", [0, 1420, 0]),
            assembly("TORRE", [1100, 0, 0], 90)]


def fixture_f6_stub(request):
    """Only at the F6 boundary; actual geometry/collisions are D5 production."""
    if set(request) != {"review_kind", "assemblies", "service_zones"}:
        raise ValueError("unexpected request")
    prepared = []
    for a in request["assemblies"]:
        if set(a) != {"group_id", "module_spec", "origin_xyz_mm", "rotation_deg"}:
            raise ValueError("untrusted exchange not accepted")
        label = a["module_spec"]["fixture"]
        if a["group_id"] != label:
            raise ValueError("fixture label mismatch")
        cad = json.loads((FIXTURES / (label + "_cad-exchange.json")).read_text())
        prepared.append({"group_id": a["group_id"], "exchange": cad,
                         "origin_xyz_mm": a["origin_xyz_mm"], "rotation_deg": a["rotation_deg"]})
    return spatial.compose_verified_exchanges(prepared, request["service_zones"])


def call(state, edit):
    payload = {"review_kind": "room_layout_session_v1",
               "review_state": state, "edit": edit}
    return carpinova_consultar(json.dumps(payload, ensure_ascii=False))


class RoomSessionD7(unittest.TestCase):
    def setUp(self):
        self.stub = patch.object(spatial, "review_room_from_specs", fixture_f6_stub)
        self.stub.start()
        self.addCleanup(self.stub.stop)
        self.first = call(None, {"op":"start", "assemblies":seed(), "service_zones":[]})
        self.assertEqual(self.first["status"], "REVIEW_ONLY_STATE_UPDATED")
        self.assertEqual(self.first["candidate"]["piece_count"], 42)

    def flags_false(self, result):
        for flag in PHYSICAL_FLAGS:
            self.assertIs(result[flag], False, flag)

    def test_start_42_pieces_and_unique_digest(self):
        self.assertEqual(self.first["candidate"]["status"], "REVIEW_ONLY")
        self.assertIsNone(self.first["before"])
        self.assertEqual(self.first["review_state"]["schema_version"], "room_layout_session_v1")
        self.assertIn("no fabricable", self.first["candidate_svg"])
        self.flags_false(self.first)

    def test_move_accepted_and_before_after_differ(self):
        moved = call(self.first["review_state"], {"op":"move", "group_id":"TORRE",
                                                    "origin_xyz_mm":[1300,0,0]})
        self.assertEqual(moved["status"],"REVIEW_ONLY_STATE_UPDATED")
        self.assertNotEqual(moved["before"]["layout_sha256"], moved["candidate"]["layout_sha256"])
        self.assertEqual(moved["review_state"]["assemblies"][2]["origin_xyz_mm"], [1300,0,0])
        self.assertEqual(moved["candidate"]["piece_count"],42)
        self.flags_false(moved)

    def test_move_causes_collision_and_preserves_old_state(self):
        blocked = call(self.first["review_state"], {"op":"move", "group_id":"TORRE",
                                                       "origin_xyz_mm":[200,0,0]})
        self.assertEqual(blocked["status"], "NEEDS_CORRECTION")
        self.assertFalse(blocked["change_applied"])
        self.assertEqual(blocked["review_state"],self.first["review_state"])
        self.assertTrue(blocked["candidate"]["envelope_collisions"])
        self.assertNotEqual(blocked["before_svg"], blocked["candidate_svg"])
        self.flags_false(blocked)

    def test_rotation_roundtrip_and_hash(self):
        changed=call(self.first["review_state"],{"op":"rotate","group_id":"BAJO", "rotation_deg":180})
        self.assertTrue(changed["change_applied"])
        self.assertEqual(changed["review_state"]["assemblies"][0]["rotation_deg"],180)
        self.assertNotEqual(changed["before"]["layout_sha256"], changed["candidate"]["layout_sha256"])
        reverted=call(changed["review_state"],{"op":"rotate","group_id":"BAJO", "rotation_deg":0})
        self.assertEqual(reverted["candidate"]["layout_sha256"], self.first["candidate"]["layout_sha256"])

    def test_upsert_safe_zone_and_remove(self):
        z={"zone_id":"S1","purpose":"plumbing", "origin_xyz_mm":[100,100,100],
           "size_xyz_mm":[30,30,30]}
        added=call(self.first["review_state"],{"op":"upsert_zone","zone":z})
        self.assertTrue(added["change_applied"])
        self.assertEqual(added["candidate"]["service_zones"][0]["status"], "CLEAR_NOMINAL_ONLY")
        removed=call(added["review_state"],{"op":"remove_zone","zone_id":"S1"})
        self.assertEqual(removed["review_state"],self.first["review_state"])

    def test_upsert_crossing_board_blocked(self):
        z={"zone_id":"S2","purpose":"electric", "origin_xyz_mm":[1,100,30],
           "size_xyz_mm":[30,40,40]}
        res=call(self.first["review_state"],{"op":"upsert_zone","zone":z})
        self.assertEqual(res["status"],"NEEDS_CORRECTION")
        self.assertEqual(res["candidate"]["service_zones"][0]["status"], "PANEL_INTERFERENCE")
        self.assertEqual(res["review_state"],self.first["review_state"])

    def test_initial_collision_does_not_issue_valid_state(self):
        a=seed();a[2]["origin_xyz_mm"]=[200,0,0]
        res=call(None,{"op":"start","assemblies":a,"service_zones":[]})
        self.assertIsNone(res["review_state"])
        self.assertEqual(res["status"],"NEEDS_CORRECTION")
        self.flags_false(res)

    def test_rejects_mutated_checksum_and_geometry(self):
        bad=copy.deepcopy(self.first["review_state"])
        bad["assemblies"][0]["origin_xyz_mm"]=[200,0,0]
        with self.assertRaisesRegex(ValueError,"checksum"):
            call(bad,{"op":"rotate","group_id":"BAJO","rotation_deg":90})
        bad=copy.deepcopy(self.first["review_state"])
        bad["assemblies"][0]["origin_xyz_mm"]=[100,0,0]
        # Even a recomputed *unkeyed* checksum cannot forge the prior F6 layout.
        bad["snapshot_sha256"]=spatial._hash({k:v for k,v in bad.items() if k!="snapshot_sha256"})
        with self.assertRaisesRegex(ValueError, "Estado anterior"):
            call(bad,{"op":"rotate","group_id":"BAJO","rotation_deg":90})

    def test_rejects_unknown_edit_and_client_geometry(self):
        for change in [
            {"op":"rotate","group_id":"BAJO","rotation_deg":45},
            {"op":"rotate","group_id":"BAJO","rotation_deg":True},
            {"op":"move","group_id":"ALTO", "origin_xyz_mm":[True,0,0]},
            {"op":"move","group_id":"ALTO", "origin_xyz_mm":[-1,0,0]},
            {"op":"delete_group", "group_id":"BAJO"},
            {"op":"rotate","group_id":"OTRO","rotation_deg":90},
            {"op":"move","group_id":"BAJO","origin_xyz_mm":[0,0,0],"exchange":{}},
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                call(self.first["review_state"],change)

    def test_client_state_schema_and_start_reentry_blocked(self):
        for wrong in [None,[], {"schema_version":"room_layout_session_v1"}]:
            if wrong is None:continue
            with self.assertRaises(ValueError):
                call(wrong,{"op":"move","group_id":"BAJO","origin_xyz_mm":[0,0,0]})
        with self.assertRaisesRegex(ValueError,"start"):
            call(self.first["review_state"],{"op":"start", "assemblies":seed(),"service_zones":[]})


if __name__ == "__main__":
    unittest.main()
