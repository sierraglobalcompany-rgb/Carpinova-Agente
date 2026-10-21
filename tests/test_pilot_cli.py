"""Contract smoke for the first offline furniture-design pilot."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree

from carpinova_agent.cad_exchange import validate_exchange
from carpinova_agent.pilot_cli import PilotError, main, pilot_review, write_pilot_bundle


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "pilot-open-kitchen-800.json"


class FirstFurniturePilotTests(unittest.TestCase):
    def setUp(self):
        self.project = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_first_mueble_has_four_nominal_panels_same_engine(self):
        bundle = pilot_review(self.project)
        result = json.loads(bundle["maestro-review.json"])
        cad = validate_exchange(json.loads(bundle["cad-exchange.json"]))
        manifest = json.loads(bundle["manifest.json"])
        self.assertEqual(result["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(result["modular"]["piece_count"], 4)
        self.assertEqual(manifest["piece_count"], 4)
        self.assertEqual({box["piece_id"] for box in cad["boxes"]},
                         {p["piece_id"] for p in result["modular"]["parts"]})
        self.assertEqual(cad["geometry_sha256"], manifest["geometry_sha256"])
        self.assertEqual(result["modular"]["modules"][0]["clear_width_mm"], 764)
        self.assertEqual(result["modular"]["dimensions_mm"],
                         {"width": 800, "height": 720, "depth": 550})
        for key in ("fabrication_ready", "cutting_ready",
                    "drilling_ready", "purchase_ready"):
            self.assertFalse(result[key])
            self.assertFalse(cad[key])
            self.assertFalse(manifest[key])

    def test_svg_csv_are_review_outputs_not_cut_instructions(self):
        bundle = pilot_review(self.project)
        ElementTree.fromstring(bundle["front-review.svg"])
        rows = list(csv.DictReader(io.StringIO(bundle["parts-review.csv"])))
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r["production_status"] == "BORRADOR_NO_CORTAR"
                            for r in rows))
        self.assertTrue(all(p["finished_cut_dimensions_mm"] is None
                            for p in json.loads(bundle["maestro-review.json"])["modular"]["parts"]))

    def test_bundle_written_once_with_all_five_files(self):
        with TemporaryDirectory() as td:
            target = Path(td) / "pilot"
            manifest = write_pilot_bundle(self.project, target)
            self.assertEqual({p.name for p in target.iterdir()},
                             set(manifest["files"]))
            self.assertEqual(json.loads((target / "manifest.json").read_text()),
                             manifest)
            with self.assertRaisesRegex(PilotError, "existente"):
                write_pilot_bundle(self.project, target)

    def test_no_files_created_on_missing_layout_dimensions(self):
        invalid = json.loads(json.dumps(self.project))
        invalid["module_spec"]["width_mm"] = 820
        with TemporaryDirectory() as td:
            target = Path(td) / "blocked"
            with self.assertRaisesRegex(PilotError, "bloqueado"):
                write_pilot_bundle(invalid, target)
            self.assertFalse(target.exists())

    def test_cannot_use_unconfirmed_module_spec(self):
        candidate = json.loads(json.dumps(self.project))
        candidate["module_spec"]["installation"] = "built_in"
        with self.assertRaisesRegex(PilotError, "bloqueado"):
            pilot_review(candidate)

    def test_only_explicit_modular_action_accepted(self):
        for invalid in (
            {"action": "project", "project": {}},
            {"action": "knowledge", "query": "cantos"},
            {"action": "fabricar", "module_spec": self.project["module_spec"]},
        ):
            with self.subTest(action=invalid["action"]), self.assertRaises(PilotError):
                pilot_review(invalid)

    def test_bad_geometry_fails_before_outputs(self):
        bad = json.loads(json.dumps(self.project))
        bad["module_spec"]["modules"][0]["panel_thickness_mm"] = 500
        with TemporaryDirectory() as td:
            target = Path(td) / "blocked"
            with self.assertRaises(ValueError):
                write_pilot_bundle(bad, target)
            self.assertFalse(target.exists())

    def test_source_request_is_not_mutated(self):
        initial = json.loads(json.dumps(self.project))
        pilot_review(self.project)
        self.assertEqual(self.project, initial)

    def test_command_line_succeeds_only_with_new_output(self):
        with TemporaryDirectory() as td:
            target = Path(td) / "pilot"
            import contextlib
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["--input", str(FIXTURE), "--output-dir", str(target)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["piece_count"], 4)
            self.assertEqual(main(["--input", str(FIXTURE),
                                   "--output-dir", str(target)]), 2)

    def test_input_not_matching_schema_fails_before_output(self):
        with TemporaryDirectory() as td:
            source = Path(td) / "candidate.json"
            source.write_text('{"action":"modular","module_spec":{}}', encoding="utf-8")
            target = Path(td) / "pilot"
            self.assertEqual(main(["--input", str(source),
                                   "--output-dir", str(target)]), 2)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
