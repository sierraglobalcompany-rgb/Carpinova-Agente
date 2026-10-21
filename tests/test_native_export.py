"""Controlled native export: denied by default, no arbitrary executable or overwrite."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from zipfile import ZipFile

from carpinova_agent.native_export import (
    NativeExportError, REVIEW_CONFIRMATION, export_native_project,
)
from carpinova_agent.pilot_cli import write_pilot_bundle


ROOT = Path(__file__).resolve().parents[1]
REQUEST = json.loads(
    (ROOT / "examples" / "pilot-open-kitchen-800.json").read_text(encoding="utf-8")
)


class NativeExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "test"
        write_pilot_bundle(REQUEST, self.project)
        self.fc = self.root / "FreeCADCmd.exe"
        self.bl = self.root / "blender.exe"
        self.fc.write_bytes(b"fake runner fixture")
        self.bl.write_bytes(b"fake runner fixture")
        self.cad = json.loads((self.project / "cad-exchange.json").read_text(encoding="utf-8"))
        self.calls: list[list[str]] = []

    def call(self, **kw):
        return export_native_project(
            self.project, confirmation=REVIEW_CONFIRMATION, enabled=True,
            freecad_executable=str(self.fc), blender_executable=str(self.bl),
            runner=self.fake_runner, **kw,
        )

    def _proof(self):
        return {
            "status": "NATIVE_GEOMETRY_MATCH",
            "geometry_sha256": self.cad["geometry_sha256"],
            "verified_piece_count": len(self.cad["boxes"]),
            "max_abs_error_mm": 0.0,
            "tolerance_mm": 0.05,
            "fabrication_ready": False, "drilling_ready": False, "cutting_ready": False,
        }

    def fake_runner(self, command, **kwargs):
        self.calls.append(command)
        self.assertIsInstance(command, list)
        self.assertNotIn("shell", kwargs)
        self.assertTrue(kwargs["timeout"] <= 240)
        self.assertEqual(kwargs["env"]["PYTHONPATH"], str(ROOT))
        report = {
            "geometry_sha256": self.cad["geometry_sha256"],
            "native_measurements": self._proof(),
        }
        if "FreeCADCmd.exe" in command[0]:
            target = Path(kwargs["env"]["CARPINOVA_FCSTD_OUTPUT"])
            with ZipFile(target, "w") as file:
                file.writestr("Document.xml", "<Document/>")
            text = "FREECAD_NATIVE_RESULT=" + json.dumps(report)
        elif "blender_presentation.py" in " ".join(command):
            for key in ("--output-blend", "--output-png"):
                target = Path(command[command.index(key) + 1])
                target.write_bytes(b"BLENDERv01" if key.endswith("blend")
                                   else b"\x89PNG\r\n\x1a\nfixture")
            text = "BLENDER_PRESENTATION_RESULT=" + json.dumps(report)
        else:
            Path(command[command.index("--output") + 1]).write_bytes(b"BLENDERv01")
            text = json.dumps(report)
        return SimpleNamespace(returncode=0, stdout=text, stderr="")

    def test_full_native_export_preserves_contract_and_four_blocks(self):
        result = self.call()
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(result["piece_count"], 4)
        self.assertEqual(result["geometry_sha256"], self.cad["geometry_sha256"])
        self.assertEqual(set(result["reports"]), {"FreeCAD", "Blender", "BlenderPresentation"})
        for k in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertFalse(result[k])
        self.assertEqual((self.project / "native/native.blend").read_bytes()[:7], b"BLENDER")
        self.assertTrue((self.project / "native/presentation.png").is_file())
        with self.assertRaisesRegex(NativeExportError, "sobrescribir"):
            self.call()

    def test_missing_host_enable_refuses_without_running(self):
        with self.assertRaisesRegex(NativeExportError, "habilitación"):
            export_native_project(self.project, confirmation=REVIEW_CONFIRMATION,
                                  enabled=False, freecad_executable=str(self.fc),
                                  blender_executable=str(self.bl),
                                  runner=self.fake_runner)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.project / "native").exists())

    def test_missing_confirmation_refuses_without_running(self):
        with self.assertRaises(NativeExportError):
            export_native_project(self.project, confirmation="yes",
                                  enabled=True, freecad_executable=str(self.fc),
                                  blender_executable=str(self.bl),
                                  runner=self.fake_runner)
        self.assertFalse((self.project / "native").exists())

    def test_rejects_arbitrary_or_nonabsolute_binaries(self):
        evil = self.root / "cmd.exe"
        evil.write_bytes(b"x")
        for exe in (str(evil), "blender.exe", "", None):
            with self.subTest(executable=exe), self.assertRaises(NativeExportError):
                export_native_project(self.project,
                                      confirmation=REVIEW_CONFIRMATION,
                                      enabled=True,
                                      freecad_executable=str(self.fc),
                                      blender_executable=exe,
                                      runner=self.fake_runner)
        self.assertFalse((self.project / "native").exists())

    def test_trusted_binary_symlink_allowed_but_arbitrary_target_rejected(self):
        correct = self.root / "bin"
        correct.mkdir()
        freecad_link = correct / "freecadcmd"
        blender_link = correct / "blender"
        try:
            freecad_link.symlink_to(self.fc)
            blender_link.symlink_to(self.bl)
        except (OSError, NotImplementedError):
            self.skipTest("No symlink privilege on this runner")
        # Both target names are allowed by contract (case-insensitive).
        result = export_native_project(
            self.project, confirmation=REVIEW_CONFIRMATION, enabled=True,
            freecad_executable=str(freecad_link),
            blender_executable=str(blender_link),
            runner=self.fake_runner,
        )
        self.assertEqual(result["piece_count"], 4)

    def test_bad_binary_symlink_target_fails_closed(self):
        evil = self.root / "cmd.exe"
        evil.write_bytes(b"fake")
        link = self.root / "blender"
        try:
            link.symlink_to(evil)
        except (OSError, NotImplementedError):
            self.skipTest("No symlink privilege on this runner")
        with self.assertRaisesRegex(NativeExportError, "no autorizado"):
            export_native_project(
                self.project, confirmation=REVIEW_CONFIRMATION, enabled=True,
                freecad_executable=str(self.fc), blender_executable=str(link),
                runner=self.fake_runner,
            )
        self.assertEqual(self.calls, [])

    def test_changed_source_manifest_blocks_execution(self):
        p = self.project / "manifest.json"
        obj = json.loads(p.read_text(encoding="utf-8"))
        obj["geometry_sha256"] = "0" * 64
        p.write_text(json.dumps(obj), encoding="utf-8")
        with self.assertRaisesRegex(NativeExportError, "no coinciden"):
            self.call()
        self.assertEqual(self.calls, [])

    def test_native_failure_never_publishes_partial_outputs(self):
        def failure(command, **kwargs):
            return SimpleNamespace(returncode=12, stdout="no", stderr="err")
        with self.assertRaisesRegex(NativeExportError, "falló"):
            export_native_project(self.project, confirmation=REVIEW_CONFIRMATION,
                                  enabled=True, freecad_executable=str(self.fc),
                                  blender_executable=str(self.bl), runner=failure)
        self.assertFalse((self.project / "native").exists())

    def test_timeout_never_publishes_partial_outputs(self):
        def timeout(command, **kwargs):
            raise subprocess.TimeoutExpired(cmd=command, timeout=10)
        with self.assertRaisesRegex(NativeExportError, "terminar"):
            export_native_project(self.project, confirmation=REVIEW_CONFIRMATION,
                                  enabled=True, freecad_executable=str(self.fc),
                                  blender_executable=str(self.bl), runner=timeout)
        self.assertFalse((self.project / "native").exists())

    def test_mismatch_native_geometry_rejected_without_files(self):
        def tampered(command, **kwargs):
            x = self.fake_runner(command, **kwargs)
            if "FreeCADCmd.exe" in command[0]:
                item = json.loads(x.stdout.split("=", 1)[1])
                item["native_measurements"]["verified_piece_count"] = 3
                x.stdout = "FREECAD_NATIVE_RESULT=" + json.dumps(item)
            return x
        with self.assertRaisesRegex(NativeExportError, "no coincide"):
            export_native_project(self.project, confirmation=REVIEW_CONFIRMATION,
                                  enabled=True, freecad_executable=str(self.fc),
                                  blender_executable=str(self.bl), runner=tampered)
        self.assertFalse((self.project / "native").exists())


if __name__ == "__main__":
    unittest.main()
