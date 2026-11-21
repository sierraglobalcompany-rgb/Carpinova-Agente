"""F10: targeted contract for the existing MCP draft tool's room-review branch.

F9A/F9B/D17/D18/D19 historical suites are not re-run by this file.
Codex's larger original five-method test remains archived in the F10 ZIP;
this checked-in contract is an independently composed, smaller focal gate.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from carpinova_agent.mcp_bridge import carpinova_generar_borrador
from carpinova_agent.pilot_cli import PilotError
from carpinova_agent.room_review_package import RoomPackageError


ROOT = Path(__file__).resolve().parents[1]
LEGACY = (ROOT / "examples" / "pilot-open-kitchen-800.json").read_text(encoding="utf-8")


def _module(name: str, width: int, door: bool) -> dict:
    body = {
        "module_id": name, "width_mm": width,
        "panel_thickness_mm": 18, "material_id": "MELAMINA_18",
        "construction": "sides_full", "support": "floor",
        "fronts": "none", "back": "none", "drawers": "none",
    }
    if door:
        body["corner_blind"] = {
            "side": "right", "blind_width_mm": 420,
            "access_door": {
                "material_id": "MELAMINA_18", "thickness_mm": 18,
                "gap_left_mm": 3, "gap_right_mm": 3,
                "gap_top_mm": 3, "gap_bottom_mm": 3, "hinge_side": "left",
            },
        }
    return {
        "type": "modular_run", "application": "kitchen",
        "width_mm": width, "height_mm": 720, "depth_mm": 560,
        "installation": "freestanding", "modules": [body],
    }


def _request() -> dict:
    return {
        "review_kind": "room_layout_v1",
        "assemblies": [
            {"group_id": "CIEGO", "module_spec": _module("CIEGO", 900, True),
             "origin_xyz_mm": [0, 0, 0], "rotation_deg": 0},
            {"group_id": "RECTO", "module_spec": _module("RECTO", 600, False),
             "origin_xyz_mm": [900, 0, 0], "rotation_deg": 90},
        ],
        "service_zones": [],
    }


class MCPRoomReviewF10Contract(unittest.TestCase):
    def test_one_new_room_zip_from_existing_tool(self) -> None:
        with TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": folder}):
                result = carpinova_generar_borrador(
                    json.dumps(_request()), "F10_ROOM", seccion_y_mm=350
                )
            self.assertEqual(result["status"], "REVIEW_ONLY")
            self.assertEqual(result["piece_count"], 10)
            self.assertEqual(result["section_y_mm"], 350)
            self.assertEqual(result["release"], "NO_GO")
            self.assertEqual(len(result["files"]), 7)
            for flag in ("fabrication_ready", "cutting_ready",
                         "drilling_ready", "purchase_ready", "can_generate_f7c"):
                self.assertIs(result[flag], False)
            self.assertIn("LOCAL_PATH_NOT_BINARY_MCP", " ".join(result["warnings"]))
            self.assertNotIn("zip_bytes", result)
            expected = Path(folder) / "F10_ROOM-room-review.zip"
            self.assertEqual(result["room_package_path"], str(expected))
            self.assertEqual(hashlib.sha256(expected.read_bytes()).hexdigest(),
                             result["zip_sha256"])
            with ZipFile(expected) as archive:
                self.assertIsNone(archive.testzip())
                manifest = json.loads(archive.read("MANIFEST.json"))
                self.assertEqual(set(archive.namelist()),
                                 set(result["files"]) | {"MANIFEST.json"})
                self.assertEqual(manifest["piece_count"], 10)
                self.assertEqual(manifest["release"], "NO_GO")
                for name, value in manifest["files"].items():
                    raw = archive.read(name)
                    self.assertEqual(len(raw), value["bytes"])
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), value["sha256"])
                data = json.loads(archive.read("04-habitacion.json"))
                self.assertEqual(data["piece_count"], 10)
                self.assertEqual(
                    {p["role"] for p in data["world_boxes"]
                     if p["role"].startswith("front_corner_")},
                    {"front_corner_blind", "front_corner_access"}
                )
                rows = list(csv.DictReader(io.StringIO(
                    archive.read("06-paneles-en-escena.csv").decode("utf-8"))))
                self.assertEqual(len(rows), 10)
                self.assertTrue(all(r["NOT_FOR_CUTTING"] == "TRUE" for r in rows))

    def test_rejects_invalid_room_options_without_side_effects(self) -> None:
        request = json.dumps(_request())
        for label, options in (
            ("missing", {}), ("boolean", {"seccion_y_mm": True}),
            ("float", {"seccion_y_mm": 350.0}),
            ("negative", {"seccion_y_mm": -1}),
            ("too_high", {"seccion_y_mm": 20001}),
            ("plans", {"seccion_y_mm": 350, "incluir_planos": True}),
            ("flow", {"seccion_y_mm": 350, "flow_review_json": "{}"}),
            ("opening", {"seccion_y_mm": 350, "opening_review_json": "{}"}),
        ):
            with self.subTest(label=label), TemporaryDirectory() as folder:
                with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": folder}):
                    with self.assertRaises((PilotError, RoomPackageError)):
                        carpinova_generar_borrador(request, "F10_BAD", **options)
                self.assertEqual(list(Path(folder).iterdir()), [])
        tampered = _request()
        tampered["world_boxes"] = []
        with TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": folder}):
                with self.assertRaises((PilotError, RoomPackageError)):
                    carpinova_generar_borrador(
                        json.dumps(tampered), "F10_INJECTION", seccion_y_mm=350
                    )
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_no_overwrite_or_cross_collision_with_legacy_pilot(self) -> None:
        source = json.dumps(_request())
        with TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": folder}):
                existing = Path(folder) / "ALREADY-room-review.zip"
                existing.write_bytes(b"owner-data")
                with self.assertRaises(PilotError):
                    carpinova_generar_borrador(source, "ALREADY", seccion_y_mm=350)
                self.assertEqual(existing.read_bytes(), b"owner-data")
                pilot = Path(folder) / "PILOT"
                pilot.mkdir()
                (pilot / "marker").write_text("preserve", encoding="utf-8")
                with self.assertRaises(PilotError):
                    carpinova_generar_borrador(source, "PILOT", seccion_y_mm=350)
                self.assertEqual((pilot / "marker").read_text(), "preserve")
                result = carpinova_generar_borrador(source, "ROOM", seccion_y_mm=350)
                snapshot = Path(result["room_package_path"]).read_bytes()
                with self.assertRaises(PilotError):
                    carpinova_generar_borrador(LEGACY, "ROOM")
                with self.assertRaises(PilotError):
                    carpinova_generar_borrador(source, "ROOM", seccion_y_mm=350)
                self.assertEqual(
                    Path(result["room_package_path"]).read_bytes(), snapshot)

    def test_rejects_symlink_destination_when_supported(self) -> None:
        with TemporaryDirectory() as folder, TemporaryDirectory() as outside:
            target = Path(outside) / "keep.zip"
            target.write_bytes(b"preserve")
            link = Path(folder) / "LINK-room-review.zip"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlink privileges unavailable")
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": folder}):
                with self.assertRaises(PilotError):
                    carpinova_generar_borrador(
                        json.dumps(_request()), "LINK", seccion_y_mm=350)
            self.assertEqual(target.read_bytes(), b"preserve")

    def test_legacy_modular_route_keeps_its_contract(self) -> None:
        with TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": folder}):
                result = carpinova_generar_borrador(LEGACY, "LEGACY")
                self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")
                self.assertEqual(result["piece_count"], 4)
                self.assertEqual(len(result["files"]), 5)
                for flag in ("fabrication_ready", "cutting_ready",
                             "drilling_ready", "purchase_ready"):
                    self.assertIs(result[flag], False)
                with self.assertRaisesRegex(PilotError, "seccion_y_mm"):
                    carpinova_generar_borrador(
                        LEGACY, "WRONG_ROUTE", seccion_y_mm=350)
                self.assertFalse((Path(folder) / "WRONG_ROUTE").exists())


if __name__ == "__main__":
    unittest.main()
