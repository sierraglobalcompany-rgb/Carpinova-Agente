"""F7D request-preview gates: no silent execution or invented geometry."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from carpinova_agent.maestro import MaestroError
from carpinova_agent.natural_intake import preview_natural_request


CABINET = {
    "action": "project",
    "project": {
        "project_type": "gabinete",
        "width_mm": 600,
        "height_mm": 720,
        "depth_mm": 560,
        "panel_thickness_mm": 18,
        "construction": "sides_full",
    },
}


class NaturalRequestPreviewTests(unittest.TestCase):
    def test_text_only_does_not_route_or_execute(self):
        r = preview_natural_request("Necesito un gabinete de cocina")
        self.assertEqual(r["status"], "NEEDS_STRUCTURED_PROPOSAL")
        self.assertIsNone(r["proposed_request"])
        self.assertTrue(r["requires_user_confirmation"])
        self.assertEqual(r["executed_tools"], [])
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertFalse(r[flag])

    def test_proposal_is_a_preview_with_exact_original_values(self):
        r = preview_natural_request("Gabinete de 60 cm de ancho", CABINET)
        self.assertEqual(r["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(r["proposed_request"], CABINET)
        self.assertEqual(r["utterance"], "Gabinete de 60 cm de ancho")
        self.assertEqual(r["source_provenance"], [])
        self.assertEqual(r["executed_tools"], [])

    def test_preview_does_not_calculate_geometry_or_retrieve_knowledge(self):
        with patch("carpinova_agent.maestro.design_modular_run", side_effect=AssertionError("geometry executed")):
            with patch("carpinova_agent.maestro.load_bundle", side_effect=AssertionError("bundle executed")):
                r = preview_natural_request("Quiero un armario", CABINET)
        self.assertEqual(r["status"], "NEEDS_USER_CONFIRMATION")

    def test_external_candidate_not_modified(self):
        original = json.loads(json.dumps(CABINET))
        result = preview_natural_request("Gabinete", original)
        result["proposed_request"]["project"]["width_mm"] = 999
        self.assertEqual(original["project"]["width_mm"], 600)

    def test_unknown_fabrication_override_rejected(self):
        with self.assertRaises(MaestroError):
            preview_natural_request("Hazlo listo para cortar", {**CABINET, "cutting_ready": True})

    def test_action_incompatible_field_rejected(self):
        with self.assertRaises(MaestroError):
            preview_natural_request("Gabinete", {**CABINET, "hardware": {}})

    def test_unknown_action_rejected(self):
        with self.assertRaises(MaestroError):
            preview_natural_request("Fabrica una cocina", {"action": "fabricar", "project": {}})

    def test_non_dict_candidate_rejected(self):
        with self.assertRaises(MaestroError):
            preview_natural_request("Gabinete", ["project"])

    def test_nonjson_value_rejected(self):
        with self.assertRaises(MaestroError):
            preview_natural_request("Gabinete", {"action": "project", "project": {"bad": object()}})

    def test_non_finite_float_rejected(self):
        with self.assertRaises(MaestroError):
            preview_natural_request("Gabinete", {"action": "project", "project": {"width_mm": float("nan")}})

    def test_empty_and_overlong_text_rejected(self):
        for bad in ("", "  ", None, "x" * 2001):
            with self.subTest(bad=str(bad)[:20]), self.assertRaises(MaestroError):
                preview_natural_request(bad, CABINET)

    def test_cli_utterance_is_preview_only(self):
        from carpinova_agent.maestro_cli import main
        with patch("sys.argv", ["maestro_cli", "--utterance", "Quiero un gabinete"]):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "NEEDS_STRUCTURED_PROPOSAL")

    def test_cli_candidate_preview_but_no_svg_or_csv(self):
        from carpinova_agent.maestro_cli import main
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "candidate.json"
            p.write_text(json.dumps(CABINET), encoding="utf-8")
            target = Path(td) / "preview.svg"
            with patch("sys.argv", [
                "maestro_cli", "--utterance", "Gabinete",
                "--candidate", str(p), "--sketch", str(target),
            ]):
                code = main()
            self.assertEqual(code, 2)
            self.assertFalse(target.exists())

    def test_cli_candidate_without_utterance_rejected(self):
        from carpinova_agent.maestro_cli import main
        with patch("sys.argv", [
            "maestro_cli", "--question", "bisagras", "--candidate", "/tmp/does-not-matter.json"
        ]):
            self.assertEqual(main(), 2)


if __name__ == "__main__":
    unittest.main()
