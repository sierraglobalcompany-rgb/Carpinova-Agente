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

from carpinova_agent.mcp_bridge import carpinova_generar_borrador
from carpinova_agent.pilot_cli import PilotError
from test_kitchen_linear import ask, make_l1


FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready",
    "can_generate_f7c",
)
EXPECTED_MEMBERS = {
    "LEER_PRIMERO.txt", "01-visor-3d.html", "02-planta.svg",
    "03-seccion.svg", "04-habitacion.json", "05-solicitud.json",
    "06-paneles-en-escena.csv", "MANIFEST.json",
}
LEGACY_TOOL_FIELDS = {
    "status", "proyecto", "room_package_path", "zip_sha256",
    "layout_sha256", "piece_count", "section_y_mm", "files", "release",
    *FLAGS, "warnings",
}


class KitchenSpatialMcpPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.valid_state = make_l1()["review_state"]

    @staticmethod
    def spatial_request(state: dict | None) -> dict:
        return {
            "review_kind": "kitchen_spatial_v1",
            "review_state": copy.deepcopy(state),
            "service_zones": [],
        }

    @staticmethod
    def call(request: dict, project: str, *, section: int = 350,
             include_plans: bool = False) -> dict:
        return carpinova_generar_borrador(
            solicitud_json=json.dumps(request, ensure_ascii=False),
            proyecto=project,
            incluir_planos=include_plans,
            seccion_y_mm=section,
        )

    def test_public_kitchen_spatial_call_writes_verified_d19_bundle(self) -> None:
        request = self.spatial_request(self.valid_state)
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": directory}
        ):
            result = self.call(request, "H9_COCINA_3GRUPOS")
            path = Path(result["room_package_path"])
            self.assertTrue(path.is_file())
            raw_zip = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw_zip).hexdigest(), result["zip_sha256"])
            self.assertEqual(result["status"], "REVIEW_ONLY")
            self.assertEqual(result["release"], "NO_GO")
            self.assertEqual(result["section_y_mm"], 350)
            self.assertEqual(result["files"], sorted(EXPECTED_MEMBERS - {"MANIFEST.json"}))
            self.assertEqual(result["room_status"], "REVIEW_ONLY")
            for flag in FLAGS:
                self.assertIs(result[flag], False, flag)

            with ZipFile(io.BytesIO(raw_zip)) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), EXPECTED_MEMBERS)
                manifest = json.loads(archive.read("MANIFEST.json"))
                review = json.loads(archive.read("04-habitacion.json"))
                saved_request = json.loads(archive.read("05-solicitud.json"))
                self.assertEqual(saved_request, request)
                self.assertEqual(manifest["schema_version"], "D19_REVIEW_BUNDLE_V1")
                self.assertEqual(manifest["source_review_kind"], "kitchen_spatial_v1")
                self.assertEqual(manifest["room_status"], result["room_status"])
                self.assertEqual(manifest["section_y_mm"], 350)
                self.assertEqual(manifest["layout_sha256"], result["layout_sha256"])
                self.assertEqual(review["review_kind"], "room_layout_v1")
                self.assertEqual(review["source_review_kind"], "kitchen_linear_v1")
                self.assertEqual(review["layout_sha256"], result["layout_sha256"])
                self.assertEqual(result["piece_count"], review["piece_count"])
                self.assertEqual(
                    {group["group_id"] for group in review["groups"]},
                    {"BAJO", "ALTO", "TORRE"},
                )
                for flag in FLAGS:
                    self.assertIs(review[flag], False, flag)
                for name, info in manifest["files"].items():
                    data = archive.read(name)
                    self.assertEqual(len(data), info["bytes"], name)
                    self.assertEqual(hashlib.sha256(data).hexdigest(), info["sha256"], name)

                csv_rows = list(csv.DictReader(io.StringIO(
                    archive.read("06-paneles-en-escena.csv").decode("utf-8")
                )))
                csv_ids = {row["piece_id"] for row in csv_rows}
                review_ids = {box["piece_id"] for box in review["world_boxes"]}
                html = archive.read("01-visor-3d.html").decode("utf-8")
                payload_match = re.search(
                    r'<script id="scene-data" type="application/json">(.*?)</script>',
                    html, re.DOTALL,
                )
                self.assertIsNotNone(payload_match)
                canvas_payload = json.loads(payload_match.group(1))
                self.assertEqual(
                    {group["id"] for group in canvas_payload["groups"]},
                    {"BAJO", "ALTO", "TORRE"},
                )
                html_ids = {box["id"] for box in canvas_payload["boxes"]}
                self.assertTrue(review_ids)
                self.assertEqual(review_ids, csv_ids)
                self.assertEqual(review_ids, html_ids)

            before = path.read_bytes()
            with self.assertRaises(PilotError):
                self.call(request, "H9_COCINA_3GRUPOS")
            self.assertEqual(path.read_bytes(), before)

    def test_unconfirmed_and_untrusted_requests_fail_before_zip_creation(self) -> None:
        pending = ask(
            self.valid_state, "BAJO", "La carcasa ahora tiene 1100 mm de ancho."
        )["review_state"]
        cases = {
            "no-last-valid": self.spatial_request(None),
            "pending-candidate": self.spatial_request(pending),
            "client-boxes": {
                **self.spatial_request(self.valid_state), "world_boxes": []
            },
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": directory}
        ):
            for suffix, request in cases.items():
                with self.subTest(case=suffix), self.assertRaises(ValueError):
                    self.call(request, "H9_NEG_" + suffix.replace("-", "_"))
                self.assertFalse(
                    (Path(directory) / ("H9_NEG_" + suffix.replace("-", "_")
                                        + "-room-review.zip")).exists()
                )

            with self.assertRaises(PilotError):
                self.call(self.spatial_request(self.valid_state), "H9_BOOL_SECTION",
                           section=True)
            self.assertFalse((Path(directory) / "H9_BOOL_SECTION-room-review.zip").exists())

            with self.assertRaises(PilotError):
                self.call(self.spatial_request(self.valid_state), "H9_PLANS",
                           include_plans=True)
            self.assertFalse((Path(directory) / "H9_PLANS-room-review.zip").exists())

            unknown = {"review_kind": "unknown_v1"}
            with self.assertRaisesRegex(PilotError, "room_layout_v1 o kitchen_spatial_v1"):
                self.call(unknown, "H9_UNKNOWN", section=350)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_existing_room_layout_tool_contract_and_d19_manifest_remain_compatible(self) -> None:
        request = json.loads(Path(
            "examples/room-layout-kitchen-storage-review.json"
        ).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": directory}
        ):
            result = self.call(request, "H9_LEGACY_ROOM_LAYOUT")
            self.assertEqual(set(result), LEGACY_TOOL_FIELDS)
            path = Path(result["room_package_path"])
            self.assertTrue(path.is_file())
            with ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), EXPECTED_MEMBERS)
                manifest = json.loads(archive.read("MANIFEST.json"))
                self.assertEqual(manifest["source_review_kind"], "room_layout_v1")
                review = json.loads(archive.read("04-habitacion.json"))
                self.assertEqual(review["review_kind"], "room_layout_v1")
                self.assertEqual(json.loads(archive.read("05-solicitud.json")), request)
            self.assertEqual(result["zip_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
