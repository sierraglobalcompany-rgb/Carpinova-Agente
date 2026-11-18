"""Focal acceptance tests for nominal board-plan review only."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from carpinova_agent import mcp_bridge
from carpinova_agent.maestro import MaestroError, consult_maestro


ROOT = Path(__file__).resolve().parents[1]
P5_REQUEST = json.loads(
    (ROOT / "examples" / "wall-bar-900-review-p5.json").read_text(
        encoding="utf-8"
    )
)
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
EXPECTED_GEOMETRY_SHA = "5c0b8944ba015ef537688afac3ee58b9dd52011267c28278c9134a473cecf947"


def physical_ids(request: dict | None = None) -> list[str]:
    source = P5_REQUEST if request is None else request
    model = consult_maestro(source)["modular"]
    return [p["piece_id"] for p in model["parts"]
            if p["role"] != "support_leg_concept"]


def catalog(board_id: str = "MDP15-A-QA", *, length: int = 2440,
            width: int = 2150, substrate: str = "MDP", thickness: int = 15,
            grain: str = "none", decoration: str = "Decor A · QA") -> dict:
    return {
        "board_id": board_id, "supplier": "Proveedor sintético QA",
        "reference": f"REF-{board_id}", "decoration": decoration,
        "substrate": substrate, "thickness_mm": thickness,
        "length_mm": length, "width_mm": width,
        "grain_direction": grain,
    }


def envelope(*, boards: list[dict] | None = None,
              assignments: list[dict] | None = None,
              source: dict | None = None,
              allowances: dict | None = None) -> dict:
    source_request = copy.deepcopy(P5_REQUEST if source is None else source)
    all_ids = physical_ids(source_request)
    selected_boards = [catalog()] if boards is None else copy.deepcopy(boards)
    default_board_id = selected_boards[0]["board_id"] if selected_boards else "MDP15-A-QA"
    return {
        "review_kind": "board_plan_nominal",
        "source_request": source_request,
        "board_catalog": selected_boards,
        "piece_assignments": (
            [{"piece_id": pid, "board_id": default_board_id, "grain_axis": "none"}
             for pid in all_ids]
            if assignments is None else copy.deepcopy(assignments)
        ),
        "machine_allowances": ({
            "kerf_mm": 4, "trim_left_mm": 10, "trim_right_mm": 10,
            "trim_top_mm": 10, "trim_bottom_mm": 10,
        } if allowances is None else copy.deepcopy(allowances)),
    }


def review(value: dict) -> dict:
    return mcp_bridge.carpinova_consultar(json.dumps(value, ensure_ascii=False))


def assert_all_flags_false(test: unittest.TestCase, value: dict) -> None:
    for flag in FLAGS:
        test.assertIs(value[flag], False, flag)


class BoardPlanDispatchTests(unittest.TestCase):
    def test_existing_consultar_dispatches_board_plan_read_only(self):
        value = envelope()
        expected = {"status": "BOARD_PLAN_REVIEW_ONLY"}
        with patch.object(mcp_bridge, "build_board_plan_review", create=True,
                          return_value=expected) as planner:
            try:
                result = mcp_bridge.carpinova_consultar(
                    json.dumps(value, ensure_ascii=False)
                )
            except MaestroError as exc:
                self.fail(f"board_plan_nominal no se enruta: {exc}")
        self.assertEqual(result, expected)
        planner.assert_called_once()


class BoardPlanReviewTests(unittest.TestCase):
    def test_monochrome_preserves_maestro_ids_geometry_and_concept_markers(self):
        request = envelope()
        result = review(request)
        self.assertEqual(result["status"], "BOARD_PLAN_REVIEW_ONLY")
        self.assertEqual(result["output_kind"], "NOMINAL_SHEET_SIMULATION")
        self.assertEqual(result["geometry_sha256"], EXPECTED_GEOMETRY_SHA)
        self.assertEqual(result["piece_ids"], physical_ids())
        self.assertEqual(len(result["piece_ids"]), 24)
        self.assertEqual(len(result["excluded_concept_piece_ids"]), 4)
        self.assertEqual(result["estimated_nominal_sheet_count"],
                         sum(len(sheet["placements"]) >= 0
                             for sheet in result["sheets"]))
        self.assertTrue(result["sheets"])
        self.assertEqual(result["unplaced"], [])
        self.assertEqual(result["cut_sequence_status"], "CUT_SEQUENCE_NOT_VERIFIED")
        self.assertIs(result["can_generate_f7c"], False)
        assert_all_flags_false(self, result)

    def test_placements_respect_four_trims_kerf_and_svg_is_valid(self):
        request = envelope(allowances={
            "kerf_mm": 3, "trim_left_mm": 11, "trim_right_mm": 12,
            "trim_top_mm": 13, "trim_bottom_mm": 14,
        })
        result = review(request)
        ET.fromstring(result["sketch_svg"])
        board = request["board_catalog"][0]
        placements = [p for sheet in result["sheets"] for p in sheet["placements"]]
        self.assertEqual({p["piece_id"] for p in placements}, set(physical_ids()))
        for sheet in result["sheets"]:
            placements_in_sheet = sheet["placements"]
            for p in placements_in_sheet:
                x, y = p["board_origin_xy_mm"]
                w, h = p["size_on_sheet_mm"]
                self.assertGreaterEqual(x, 11)
                self.assertGreaterEqual(y, 14)
                self.assertLessEqual(x + w, board["width_mm"] - 12)
                self.assertLessEqual(y + h, board["length_mm"] - 13)
                self.assertEqual(p["board_id"], sheet["board_id"])
            for i, a in enumerate(placements_in_sheet):
                ax, ay = a["board_origin_xy_mm"]
                aw, ah = a["size_on_sheet_mm"]
                for b in placements_in_sheet[i + 1:]:
                    bx, by = b["board_origin_xy_mm"]
                    bw, bh = b["size_on_sheet_mm"]
                    self.assertFalse(ax < bx + bw and bx < ax + aw
                                     and ay < by + bh and by < ay + ah)
                    if ay < by + bh and by < ay + ah:
                        self.assertGreaterEqual(max(bx - (ax + aw), ax - (bx + bw)), 3)
                    if ax < bx + bw and bx < ax + aw:
                        self.assertGreaterEqual(max(by - (ay + ah), ay - (by + bh)), 3)
        sheet = result["sheets"][0]
        self.assertEqual(sheet["physical_origin_transform_mm"], [11, 14])
        self.assertGreaterEqual(sheet["geometric_remnant_area_mm2"], 0)
        self.assertEqual(sheet["nominal_piece_area_mm2"] +
                         sheet["kerf_separation_area_estimate_mm2"] +
                         sheet["geometric_remnant_area_mm2"],
                         sheet["usable_area_mm2"])

    def test_two_and_three_decorations_are_separate_sku_groups(self):
        ids = physical_ids()
        two = envelope(boards=[catalog("A"), catalog("B", decoration="Decor B · QA")])
        two["piece_assignments"] = [
            {"piece_id": pid, "board_id": "A" if pid == "BAR-COVER-TOP" else "B",
             "grain_axis": "none"} for pid in ids
        ]
        result2 = review(two)
        self.assertEqual(result2["status"], "BOARD_PLAN_REVIEW_ONLY")
        self.assertEqual({s["board_id"] for s in result2["sheets"]}, {"A", "B"})
        root2 = ET.fromstring(result2["sketch_svg"])
        fills2 = {
            node.attrib["data-board-id"]: node.attrib["fill"]
            for node in root2.iter()
            if node.tag.endswith("rect") and "data-board-id" in node.attrib
        }
        self.assertEqual(set(fills2), {"A", "B"})
        self.assertEqual(len(set(fills2.values())), 2)
        self.assertIn("TONOS SOLO ILUSTRATIVOS", result2["sketch_svg"])
        for sheet in result2["sheets"]:
            self.assertTrue(all(p["board_id"] == sheet["board_id"]
                                for p in sheet["placements"]))
        self.assertEqual(result2["customer_finish_confirmation"], "PENDING")

        three = envelope(boards=[catalog("A"),
                                 catalog("B", decoration="Decor B · QA",
                                         length=1830, width=2440),
                                 catalog("C", decoration="Decor C · QA",
                                         length=1200, width=600)])
        thirds = {"BAR-COVER-TOP": "A"}
        facades = [pid for pid in ids if pid.endswith("DRAWER_FACADE")]
        thirds.update({pid: "B" for pid in facades})
        thirds.update({pid: "C" for pid in ids if pid not in thirds})
        three["piece_assignments"] = [
            {"piece_id": pid, "board_id": thirds[pid], "grain_axis": "none"}
            for pid in ids
        ]
        result3 = review(three)
        self.assertEqual(result3["status"], "BOARD_PLAN_REVIEW_ONLY")
        self.assertEqual({s["board_id"] for s in result3["sheets"]}, {"A", "B", "C"})
        root3 = ET.fromstring(result3["sketch_svg"])
        fills3 = {
            node.attrib["data-board-id"]: node.attrib["fill"]
            for node in root3.iter()
            if node.tag.endswith("rect") and "data-board-id" in node.attrib
        }
        self.assertEqual(set(fills3), {"A", "B", "C"})
        self.assertEqual(len(set(fills3.values())), 3)
        placed = [p["piece_id"] for s in result3["sheets"] for p in s["placements"]]
        self.assertCountEqual(placed, ids)
        self.assertEqual(sum(v["estimated_nominal_sheet_count"]
                             for v in result3["by_board"]),
                         result3["estimated_nominal_sheet_count"])

    def test_oracle_two_50_by_100_rectangles_depends_on_kerf(self):
        from carpinova_agent.board_plan_review import _pack_rectangles
        pieces = [
            {"piece_id": "A", "width_mm": 50, "height_mm": 100,
             "allowed_rotations": [0]},
            {"piece_id": "B", "width_mm": 50, "height_mm": 100,
             "allowed_rotations": [0]},
        ]
        board = {"board_id": "ORACLE", "width_mm": 100, "length_mm": 100}
        trims = {"trim_left_mm": 0, "trim_right_mm": 0,
                 "trim_top_mm": 0, "trim_bottom_mm": 0}
        zero = _pack_rectangles(pieces, board, {**trims, "kerf_mm": 0})
        one = _pack_rectangles(pieces, board, {**trims, "kerf_mm": 1})
        self.assertEqual(len(zero["sheets"]), 1)
        self.assertEqual(zero["unplaced"], [])
        self.assertEqual(len(one["sheets"]), 2)
        self.assertEqual(one["unplaced"], [])

    def test_grain_veto_selects_only_compatible_zero_or_ninety_rotation(self):
        ids = physical_ids()
        request = envelope(boards=[catalog("GRAIN", grain="along_length")])
        chosen = {pid: "none" for pid in ids}
        chosen["CAJONERA_DERECHA-BACK_FULL"] = "face_y"  # XY: face_y -> Y
        chosen["CAJONERA_DERECHA-TOP"] = "face_x"         # XZ: face_x -> X
        chosen["CAJONERA_DERECHA-LEFT_SIDE"] = "face_x"  # YZ: face_x -> Z
        request["piece_assignments"] = [
            {"piece_id": pid, "board_id": "GRAIN", "grain_axis": chosen[pid]}
            for pid in ids
        ]
        result = review(request)
        placements = {p["piece_id"]: p for s in result["sheets"]
                      for p in s["placements"]}
        self.assertEqual(placements["CAJONERA_DERECHA-BACK_FULL"]["rotation_degrees"], 0)
        self.assertEqual(placements["CAJONERA_DERECHA-TOP"]["rotation_degrees"], 90)
        self.assertEqual(placements["CAJONERA_DERECHA-LEFT_SIDE"]["rotation_degrees"], 90)
        self.assertEqual(result["grain_assignment_provenance"],
                         "DECLARED_INPUT_NOT_AUTHENTICATED")
        from carpinova_agent.board_plan_review import _face_axis_to_world
        self.assertEqual(_face_axis_to_world("XY", "face_x"), "X")
        self.assertEqual(_face_axis_to_world("XY", "face_y"), "Y")
        self.assertEqual(_face_axis_to_world("XZ", "face_x"), "X")
        self.assertEqual(_face_axis_to_world("XZ", "face_y"), "Z")
        self.assertEqual(_face_axis_to_world("YZ", "face_x"), "Z")
        self.assertEqual(_face_axis_to_world("YZ", "face_y"), "Y")

    def test_grain_veto_blocks_panel_that_only_fits_after_forbidden_rotation(self):
        ids = physical_ids()
        request = envelope(
            boards=[catalog("NARROW", length=1000, width=500,
                            grain="along_width")],
            allowances={"kerf_mm": 0, "trim_left_mm": 0, "trim_right_mm": 0,
                        "trim_top_mm": 0, "trim_bottom_mm": 0},
        )
        for assignment in request["piece_assignments"]:
            if assignment["piece_id"] == "BAR-COVER-TOP":
                assignment["grain_axis"] = "face_x"
        result = review(request)
        self.assertEqual(result["status"], "BLOCKED_UNPLACED")
        blocked = next(row for row in result["unplaced"]
                       if row["piece_id"] == "BAR-COVER-TOP")
        self.assertEqual(blocked["reason"], "NO_LEGAL_ORIENTATION_FITS_USEFUL_ZONE")
        self.assertIsNone(result["estimated_nominal_sheet_count"])
        self.assertIsNone(result["estimated_total_sheet_count"])
        self.assertEqual(result["grain_assignment_provenance"],
                         "DECLARED_INPUT_NOT_AUTHENTICATED")

    def test_adulterated_cad_box_is_rejected_before_any_placement(self):
        from carpinova_agent.cad_exchange import cad_exchange
        request = envelope()
        model = consult_maestro(request["source_request"])["modular"]
        altered = cad_exchange(model)
        altered["boxes"][0]["size_xyz_mm"][0] += 1
        with patch("carpinova_agent.board_plan_review.cad_exchange",
                   return_value=altered):
            result = review(request)
        self.assertEqual(result["status"], "CONCEPT_ONLY")
        self.assertIsNone(result["estimated_nominal_sheet_count"])
        self.assertEqual(result["sheets"], [])
        self.assertTrue(any("UNSUPPORTED_SOURCE" in reason
                            for reason in result["review_blockers"]))

    def test_confirmed_maestro_grain_cannot_be_overridden_by_assignment(self):
        from carpinova_agent.board_plan_review import _assignments
        with self.assertRaisesRegex(MaestroError, "GRAIN_OVERRIDE_REJECTED"):
            _assignments(
                [{"piece_id": "PANEL-1", "board_id": "STOCK-A", "grain_axis": "face_y"}],
                [{"piece_id": "PANEL-1", "grain_axis": "face_x"}],
                [{"board_id": "STOCK-A"}],
            )

    def test_unplaced_or_incomplete_assignments_never_report_sheet_count(self):
        request = envelope(boards=[catalog("SMALL", length=500, width=600)])
        result = review(request)
        self.assertEqual(result["status"], "BLOCKED_UNPLACED")
        self.assertTrue(result["unplaced"])
        self.assertIsNone(result["estimated_nominal_sheet_count"])
        self.assertTrue(all(v["estimated_nominal_sheet_count"] is None
                            for v in result["by_board"]))

        incomplete = envelope()
        incomplete["piece_assignments"].pop()
        blocked = review(incomplete)
        self.assertEqual(blocked["status"], "NEEDS_MATERIAL_CONFIRMATION")
        self.assertIsNone(blocked["estimated_nominal_sheet_count"])
        self.assertEqual(blocked["sheets"], [])

    def test_incompatible_material_or_thickness_blocks_counts(self):
        request = envelope(boards=[catalog("WRONG-THICKNESS", thickness=18)])
        result = review(request)
        self.assertEqual(result["status"], "BLOCKED_INCOMPATIBLE_STOCK")
        self.assertIsNone(result["estimated_nominal_sheet_count"])
        self.assertEqual(result["sheets"], [])
        wrong_substrate = envelope(boards=[catalog("WRONG-SUBSTRATE", substrate="MDF")])
        blocked = review(wrong_substrate)
        self.assertEqual(blocked["status"], "BLOCKED_INCOMPATIBLE_STOCK")
        self.assertIsNone(blocked["estimated_nominal_sheet_count"])

    def test_continuity_is_never_verified_and_edge_finish_conflict_stays_blocked(self):
        request = envelope()
        for assignment in request["piece_assignments"]:
            if assignment["piece_id"].endswith("DRAWER_FACADE"):
                assignment["continuity_group"] = "facades"
        result = review(request)
        self.assertEqual(result["continuity_status"], "CONTINUITY_NOT_VERIFIED")
        self.assertIn("RAW_VS_FINISHED_UNRESOLVED", result["review_blockers"])
        self.assertEqual(result["finished_cut_dimensions_status"], "NOT_VERIFIED")
        self.assertIsNone(result["saw_dimensions_mm"])
        explicit_edges = [item for item in result["edgebanding_review"]
                          if item["edges"] != "UNCONFIRMED"]
        self.assertTrue(explicit_edges)
        self.assertTrue(all(set(item["edges"]) ==
                            {"x_min", "x_max", "y_min", "y_max"}
                            for item in explicit_edges))
        self.assertTrue(all(item["thickness_mm"] == 2
                            for item in explicit_edges))
        self.assertTrue(all("candidate" in item["classification"].lower()
                            for item in explicit_edges))
        self.assertTrue(all(item["approval"] == "NOT_APPROVED"
                            for item in explicit_edges))
        self.assertEqual(result["edgebanding_nominal_length_mm"], 3410)
        self.assertIs(result["cutting_dimensions_authorized"], False)
        assert_all_flags_false(self, result)

    def test_missing_machine_inputs_and_invalid_allowances_fail_closed(self):
        missing = envelope()
        missing.pop("machine_allowances")
        need = review(missing)
        self.assertEqual(need["status"], "NEEDS_MACHINE_INPUT")
        self.assertIsNone(need["estimated_nominal_sheet_count"])
        for bad in (
            {"kerf_mm": True, "trim_left_mm": 0, "trim_right_mm": 0,
             "trim_top_mm": 0, "trim_bottom_mm": 0},
            {"kerf_mm": 0.5, "trim_left_mm": 0, "trim_right_mm": 0,
             "trim_top_mm": 0, "trim_bottom_mm": 0},
            {"kerf_mm": -1, "trim_left_mm": 0, "trim_right_mm": 0,
             "trim_top_mm": 0, "trim_bottom_mm": 0},
            {"kerf_mm": 0, "trim_left_mm": 2150, "trim_right_mm": 0,
             "trim_top_mm": 0, "trim_bottom_mm": 0},
        ):
            with self.subTest(bad=bad), self.assertRaises(MaestroError):
                review(envelope(allowances=bad))

    def test_exact_envelope_rejects_cad_query_injection_duplicate_ids_and_dual_face(self):
        extra = envelope()
        extra["cad_exchange"] = {"geometry_sha256": "0" * 64}
        with self.assertRaises(MaestroError):
            review(extra)
        for forbidden in ("query", "evidence_topic"):
            bad = envelope()
            bad["source_request"][forbidden] = "no consultar libro"
            with self.assertRaises(MaestroError):
                review(bad)
        duplicate = envelope()
        duplicate["piece_assignments"].append(copy.deepcopy(
            duplicate["piece_assignments"][0]))
        with self.assertRaises(MaestroError):
            review(duplicate)
        dual = envelope()
        dual["piece_assignments"][0]["front_decoration"] = "X"
        dual["piece_assignments"][0]["back_decoration"] = "Y"
        with self.assertRaisesRegex(MaestroError, "UNSUPPORTED_DUAL_DECOR_FACE"):
            review(dual)
        with patch("carpinova_agent.board_plan_review.consult_maestro") as maestro:
            query = envelope()
            query["source_request"]["query"] = "consulta del libro"
            with self.assertRaises(MaestroError):
                review(query)
        maestro.assert_not_called()

    def test_unknown_board_reference_needs_material_confirmation_without_count(self):
        request = envelope()
        request["piece_assignments"][0]["board_id"] = "MISSING-SKU"
        result = review(request)
        self.assertEqual(result["status"], "NEEDS_MATERIAL_CONFIRMATION")
        self.assertIsNone(result["estimated_nominal_sheet_count"])
        self.assertEqual(result["sheets"], [])

    def test_json_duplicate_keys_oversize_and_hostile_catalog_are_rejected(self):
        duplicate = (
            '{"review_kind":"board_plan_nominal",'
            '"review_kind":"board_plan_nominal"}'
        )
        with self.assertRaises(MaestroError):
            mcp_bridge.carpinova_consultar(duplicate)
        with self.assertRaises(MaestroError):
            mcp_bridge.carpinova_consultar("{" + " " * 65540 + "}")
        bad = envelope()
        bad["board_catalog"][0]["reference"] = "https://invalid.example/sku"
        with self.assertRaises(MaestroError):
            review(bad)
        bad = envelope()
        bad["board_catalog"][0]["length_mm"] = 10_001
        with self.assertRaises(MaestroError):
            review(bad)

    def test_continuity_does_not_change_geometric_sha_or_source_request(self):
        request = envelope()
        before = copy.deepcopy(request["source_request"])
        plain = review(request)
        for assignment in request["piece_assignments"]:
            assignment["continuity_group"] = "run-1"
        grouped = review(request)
        self.assertEqual(plain["geometry_sha256"], grouped["geometry_sha256"])
        self.assertEqual(request["source_request"], before)
        self.assertEqual(grouped["continuity_status"], "CONTINUITY_NOT_VERIFIED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
