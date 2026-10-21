"""One source-of-truth regression checks for five review artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from carpinova_agent.core import DesignError
from carpinova_agent.drawing_sheet import create_render_bundle
from carpinova_agent.native_export import NativeExportError, REVIEW_CONFIRMATION, export_native_project
from carpinova_agent.pilot_cli import PilotError, verify_pilot_bundle, write_pilot_bundle


ROOT = Path(__file__).resolve().parents[1]
REQUEST = json.loads(
    (ROOT / "examples" / "pilot-open-kitchen-800.json").read_text(encoding="utf-8")
)


class ProjectProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "cabinet"
        self.manifest = write_pilot_bundle(REQUEST, self.project)

    def mutate_text(self, name, text):
        (self.project / name).write_text(text, encoding="utf-8")

    def test_generated_five_files_are_consistent(self):
        cad = verify_pilot_bundle(self.project)
        self.assertEqual(cad["geometry_sha256"], self.manifest["geometry_sha256"])
        self.assertEqual(len(cad["boxes"]), 4)


    def test_csv_raw_utf8_has_no_windows_double_carriage_return(self):
        # csv.writer deliberately emits CRLF. Writing text mode on Windows
        # historically doubled carriage returns and corrupted the BOM.
        from carpinova_agent.modular_outputs import modular_bom_csv
        maestro = json.loads((self.project / "maestro-review.json").read_bytes().decode("utf-8"))
        expected = modular_bom_csv(maestro["modular"]).encode("utf-8")
        actual = (self.project / "parts-review.csv").read_bytes()
        self.assertEqual(actual, expected)
        self.assertNotIn(b"\r\r\n", actual)

    def test_altered_csv_is_rejected_before_generating_cad(self):
        p = self.project / "parts-review.csv"
        self.mutate_text(p.name, p.read_text(encoding="utf-8") + "\nFAKE,part\n")
        with self.assertRaisesRegex(PilotError, "parts-review.csv"):
            verify_pilot_bundle(self.project)
        with self.assertRaisesRegex(DesignError, "inconsistente"):
            create_render_bundle(self.project)
        self.assertFalse((self.project / "lamina").exists())

    def test_altered_svg_is_rejected(self):
        p = self.project / "front-review.svg"
        self.mutate_text(p.name, p.read_text(encoding="utf-8").replace("svg", "SxVxG", 1))
        with self.assertRaisesRegex(PilotError, "front-review.svg"):
            verify_pilot_bundle(self.project)

    def test_altered_maestro_response_is_rejected(self):
        p = self.project / "maestro-review.json"
        original = json.loads(p.read_text(encoding="utf-8"))
        original["modular"]["parts"][0]["material_id"] = "MATERIAL_NO_APROBADO"
        self.mutate_text(p.name, json.dumps(original, ensure_ascii=False))
        with self.assertRaises(PilotError):
            verify_pilot_bundle(self.project)

    def test_rehashed_cad_plus_manifest_cannot_replace_original_design(self):
        p = self.project / "cad-exchange.json"
        cad = json.loads(p.read_text(encoding="utf-8"))
        cad["boxes"][0]["material_id"] = "MATERIAL_REEMPLAZADO"
        data = {k: v for k, v in cad.items() if k != "geometry_sha256"}
        cad["geometry_sha256"] = hashlib.sha256(json.dumps(
            data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        self.mutate_text(p.name, json.dumps(cad, ensure_ascii=False))
        m = self.project / "manifest.json"
        manifest = json.loads(m.read_text(encoding="utf-8"))
        manifest["geometry_sha256"] = cad["geometry_sha256"]
        self.mutate_text(m.name, json.dumps(manifest, ensure_ascii=False))
        with self.assertRaisesRegex(PilotError, "Maestro original"):
            verify_pilot_bundle(self.project)

    def test_external_symlink_is_rejected(self):
        origin = self.project / "maestro-review.json"
        external = Path(self.temp.name) / "external.json"
        external.write_bytes(origin.read_bytes())
        origin.unlink()
        try:
            origin.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaisesRegex(PilotError, "enlazado"):
            verify_pilot_bundle(self.project)

    def test_native_export_refuses_partial_csv_tampering_without_running(self):
        p = self.project / "parts-review.csv"
        self.mutate_text(p.name, p.read_text(encoding="utf-8") + "\nILLEGITIMATE")
        commands = []
        def runner(command, **kwargs):
            commands.append(command)
            raise AssertionError("The native CAD program must not be started")
        fc = Path(self.temp.name) / "FreeCADCmd.exe"
        bl = Path(self.temp.name) / "blender.exe"
        fc.write_bytes(b"fake")
        bl.write_bytes(b"fake")
        with self.assertRaisesRegex(NativeExportError, "no coinciden"):
            export_native_project(
                self.project, confirmation=REVIEW_CONFIRMATION,
                freecad_executable=str(fc), blender_executable=str(bl),
                enabled=True, runner=runner
            )
        self.assertEqual(commands, [])
        self.assertFalse((self.project / "native").exists())


if __name__ == "__main__":
    unittest.main()
