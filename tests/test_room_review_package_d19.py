"""D19 focused tests only. No replay of D12-D18 historical suites."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from carpinova_agent.room_review_package import (
    RoomPackageError, _render_verified_review, main,
    write_room_review_package,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "room_review_d19" / "f9a_room_public.json"


def source():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return raw["request"], raw["public_response"]


def shim(scene, svg=None):
    fallback = "<svg xmlns='http://www.w3.org/2000/svg'><title>F9A layout test-only</title></svg>"
    fake = types.ModuleType("carpinova_agent.room_spatial")
    fake.review_room_from_specs = lambda spec: copy.deepcopy(scene)
    fake.render_top_view_svg = lambda room: svg or fallback
    return fake


class ReviewBundleD19(unittest.TestCase):
    def test_real_f9a_artifact_is_packaged_with_d17_d18_and_hashes(self):
        request, scene = source()
        prior = copy.deepcopy(scene)
        with patch.dict(sys.modules, {"carpinova_agent.room_spatial": shim(scene)}):
            raw, info = _render_verified_review(request, scene, y_mm=350)
        self.assertEqual(scene, prior)
        self.assertEqual(info["piece_count"], 9)
        self.assertEqual(info["release"], "NO_GO")
        with ZipFile(io.BytesIO(raw)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(archive.namelist()), 8)
            self.assertIn("CIEGO-FRONT_CORNER_BLIND", archive.read("01-visor-3d.html").decode())
            self.assertIn("CIEGO:CIEGO-FRONT_CORNER_BLIND", archive.read("03-seccion.svg").decode())
            self.assertEqual(json.loads(archive.read("04-habitacion.json"))["layout_sha256"],
                             scene["layout_sha256"])
            self.assertEqual(json.loads(archive.read("05-solicitud.json")), request)
            self.assertIn("NO FABRICAR", archive.read("LEER_PRIMERO.txt").decode())
            self.assertEqual(archive.read("06-paneles-en-escena.csv").decode().count("\n"),10)
            self.assertIsNotNone(ET.fromstring(archive.read("02-planta.svg")))
            self.assertIsNotNone(ET.fromstring(archive.read("03-seccion.svg")))
            for name, attrs in info["files"].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), attrs["sha256"])
                self.assertEqual(len(archive.read(name)), attrs["bytes"])

    def test_public_writer_uses_one_spec_regeneration_and_refuses_overwrite(self):
        request, scene = source()
        calls = []
        s = shim(scene)
        s.review_room_from_specs = lambda req: (calls.append(req), copy.deepcopy(scene))[1]
        with tempfile.TemporaryDirectory() as d, patch.dict(
            sys.modules, {"carpinova_agent.room_spatial": s}
        ):
            out = Path(d) / "review.zip"
            report = write_room_review_package(request, out, y_mm=350)
            self.assertEqual(len(calls), 1)
            self.assertTrue(out.is_file())
            self.assertEqual(report["zip_sha256"], hashlib.sha256(out.read_bytes()).hexdigest())
            before = out.read_bytes()
            with self.assertRaises(FileExistsError):
                write_room_review_package(request, out, y_mm=350)
            self.assertEqual(out.read_bytes(), before)

    def test_cli_rejects_client_boxes_before_rebuild(self):
        request, scene = source()
        request["world_boxes"] = scene["world_boxes"]
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules, {
            "carpinova_agent.room_spatial": shim(scene)
        }):
            out = Path(d)/"pkg.zip"
            with self.assertRaisesRegex(RoomPackageError, "CAD aportado"):
                write_room_review_package(request,out,y_mm=350)
            self.assertFalse(out.exists())

    def test_no_release_flags_can_be_enabled(self):
        request, scene = source()
        for field, value in (("fabrication_ready", True), ("purchase_ready", None),
                             ("drilling_ready", 1), ("can_generate_f7c", True)):
            other = copy.deepcopy(scene)
            other[field] = value
            with self.subTest(flag=field),patch.dict(sys.modules, {
                "carpinova_agent.room_spatial": shim(other)
            }), self.assertRaises((RoomPackageError, ValueError)):
                _render_verified_review(request, other, y_mm=350)

    def test_invalid_section_is_rejected_before_creating_zip(self):
        request, scene = source()
        for y in (True, -1, 20001, 3.5, 900):
            with self.subTest(y=y), patch.dict(sys.modules, {
                "carpinova_agent.room_spatial": shim(scene)
            }), self.assertRaises((RoomPackageError, ValueError)):
                _render_verified_review(request, scene, y_mm=y)

    def test_request_invalid_or_unrecognized_fields_closed(self):
        request, scene = source()
        for field, value in (("review_kind", "cabinet"), ("exchange", []),
                             ("world_boxes", []), ("fabrication_ready", False)):
            wrong = copy.deepcopy(request)
            wrong[field] = value
            with self.subTest(field=field), self.assertRaises(RoomPackageError):
                _render_verified_review(wrong,scene,y_mm=350)

    def test_interference_warning_and_status_preserved(self):
        request, scene = source()
        scene["status"] = "INTERFERENCE_REVIEW_REQUIRED"
        scene["warnings"].append("OVERLAPPING_CABINET_ENVELOPES_BLOCK_APPROVAL")
        with patch.dict(sys.modules, {"carpinova_agent.room_spatial": shim(scene)}):
            raw, manifest = _render_verified_review(request, scene, y_mm=350)
        self.assertEqual(manifest["room_status"], "INTERFERENCE_REVIEW_REQUIRED")
        with ZipFile(io.BytesIO(raw)) as z:
            self.assertIn("INTERFERENCE_REVIEW_REQUIRED", z.read("01-visor-3d.html").decode())
            self.assertEqual(json.loads(z.read("04-habitacion.json"))["status"],
                             "INTERFERENCE_REVIEW_REQUIRED")

    def test_no_output_when_render_fails(self):
        request, scene = source()
        scene["world_boxes"][0]["origin_xyz_mm"] = [-1,0,0]
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules, {
            "carpinova_agent.room_spatial": shim(scene)
        }):
            target = Path(d)/"unsafe.zip"
            with self.assertRaises(ValueError):
                write_room_review_package(request,target,y_mm=350)
            self.assertFalse(target.exists())

    def test_cli_blocks_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as d:
            req=Path(d)/"request.json"
            req.write_text('{"review_kind":"room_layout_v1","assemblies":[],"assemblies":[],"service_zones":[]}',encoding="utf-8")
            with self.assertRaisesRegex(RoomPackageError,"duplicado"):
                main(["--input",str(req),"--output",str(Path(d)/"package.zip"),"--y-mm","350"])
            self.assertFalse((Path(d)/"package.zip").exists())

    def test_package_bytes_are_reproducible(self):
        request, scene = source()
        with patch.dict(sys.modules,{"carpinova_agent.room_spatial":shim(scene)}):
            a, ma = _render_verified_review(request,scene,y_mm=350)
            b, mb = _render_verified_review(request,scene,y_mm=350)
        self.assertEqual(ma,mb)
        self.assertEqual(a,b)


if __name__ == "__main__":
    unittest.main()
