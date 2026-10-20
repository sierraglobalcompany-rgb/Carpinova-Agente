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
from carpinova_agent.maestro_cli import _confirmation_display


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



class _FakeTty(io.StringIO):
    def isatty(self) -> bool:
        return True


class HumanConfirmationCliTests(unittest.TestCase):
    def _candidate(self, folder: str, content: str | None = None) -> Path:
        path = Path(folder) / "candidate.json"
        path.write_text(content if content is not None else json.dumps(CABINET), encoding="utf-8")
        return path

    def _invoke(self, args: list[str], stdin: io.StringIO | None = None,
                stderr: io.StringIO | None = None) -> tuple[int, str, str]:
        from carpinova_agent.maestro_cli import main
        err = stderr if stderr is not None else io.StringIO()
        inp = stdin if stdin is not None else io.StringIO()
        out = io.StringIO()
        with patch("sys.argv", ["maestro_cli", *args]):
            with patch("sys.stdin", inp), patch("sys.stderr", err), redirect_stdout(out):
                code = main()
        return code, out.getvalue(), err.getvalue()

    def test_explicit_flag_requires_candidate(self):
        with patch("carpinova_agent.maestro_cli.consult_maestro") as engine:
            status, out, error = self._invoke(["--utterance", "Gabinete", "--confirm-execute"])
        self.assertEqual(status, 2)
        self.assertEqual(out, "")
        self.assertIn("requiere --candidate", error)
        engine.assert_not_called()

    def test_execution_without_tty_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._candidate(td)
            with patch("carpinova_agent.maestro_cli.consult_maestro") as engine:
                code, out, error = self._invoke([
                    "--utterance", "Gabinete", "--candidate", str(path), "--confirm-execute",
                ])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("TTY", error)
            engine.assert_not_called()

    def test_wrong_confirmation_fails_without_file_or_calls(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._candidate(td)
            outfile = Path(td) / "output.json"
            with patch("carpinova_agent.maestro_cli.consult_maestro") as engine:
                code, out, err = self._invoke([
                    "--utterance", "Gabinete", "--candidate", str(path),
                    "--confirm-execute", "--output", str(outfile),
                ], stdin=_FakeTty("si\n"), stderr=_FakeTty())
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("cancelado", err)
            self.assertFalse(outfile.exists())
            engine.assert_not_called()

    def test_approved_tty_runs_exact_candidate_once_and_stays_nonfabricable(self):
        with tempfile.TemporaryDirectory() as td:
            candidate = self._candidate(td)
            preview = preview_natural_request("Gabinete", CABINET)
            visible, phrase = _confirmation_display(preview)
            result = {
                "status": "DRAFT_NOT_FOR_CUTTING",
                "fabrication_ready": False, "cutting_ready": False,
                "drilling_ready": False, "purchase_ready": False,
            }
            with patch("carpinova_agent.maestro_cli.consult_maestro", return_value=result) as engine:
                code, out, err = self._invoke([
                    "--utterance", "Gabinete", "--candidate", str(candidate),
                    "--confirm-execute",
                ], stdin=_FakeTty(phrase + "\n"), stderr=_FakeTty())
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), result)
            self.assertIn(visible, err)
            self.assertIn("NO está verificada", err)
            engine.assert_called_once_with(CABINET, bundle_dir=None, max_questions=3)

    def test_approved_tty_executes_real_maestro_only_as_draft(self):
        # No mocked engine: verify the second action actually re-enters F1/F3
        # deterministically and retains all four release blocks.
        with tempfile.TemporaryDirectory() as td:
            candidate = self._candidate(td)
            preview = preview_natural_request("Gabinete", CABINET)
            _, phrase = _confirmation_display(preview)
            code, out, err = self._invoke([
                "--utterance", "Gabinete", "--candidate", str(candidate),
                "--confirm-execute",
            ], stdin=_FakeTty(phrase + "\n"), stderr=_FakeTty())
        self.assertEqual(code, 0)
        response = json.loads(out)
        self.assertEqual(response["action"], "project")
        self.assertEqual(response["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(response["project"]["phase"], "GEOMETRY_DRAFT")
        self.assertEqual(
            response["project"]["design"]["dimensions"]["external_width_mm"], 600
        )
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertFalse(response[flag])
        self.assertIn("NO está verificada técnicamente", err)

    def test_confirmation_code_changes_with_exact_proposal(self):
        original = preview_natural_request("Gabinete", CABINET)
        changed = json.loads(json.dumps(CABINET))
        changed["project"]["width_mm"] = 601
        alternative = preview_natural_request("Gabinete", changed)
        shown1, phrase1 = _confirmation_display(original)
        shown2, phrase2 = _confirmation_display(alternative)
        self.assertNotEqual(shown1, shown2)
        self.assertNotEqual(phrase1, phrase2)

    def test_input_candidate_is_snapshot_even_if_file_changes_during_approval(self):
        with tempfile.TemporaryDirectory() as td:
            candidate = self._candidate(td)
            preview = preview_natural_request("Gabinete", CABINET)
            _, phrase = _confirmation_display(preview)

            class MutatingTty(_FakeTty):
                def readline(self):
                    candidate.write_text(json.dumps({"action": "fabricar"}), encoding="utf-8")
                    return super().readline()

            with patch("carpinova_agent.maestro_cli.consult_maestro", return_value={"status": "REFERENCE_ONLY"}) as engine:
                code, _, _ = self._invoke([
                    "--utterance", "Gabinete", "--candidate", str(candidate),
                    "--confirm-execute",
                ], stdin=MutatingTty(phrase + "\n"), stderr=_FakeTty())
            self.assertEqual(code, 0)
            engine.assert_called_once_with(CABINET, bundle_dir=None, max_questions=3)

    def test_preview_candidate_never_executes_even_on_tty(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._candidate(td)
            with patch("carpinova_agent.maestro_cli.consult_maestro") as engine:
                code, out, _ = self._invoke([
                    "--utterance", "Gabinete", "--candidate", str(p)
                ], stdin=_FakeTty("CONFIRMAR evil\n"), stderr=_FakeTty())
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["status"], "NEEDS_USER_CONFIRMATION")
            engine.assert_not_called()

    def test_duplicate_keys_rejected_even_nested(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._candidate(td, '{"action":"project","project":{"width_mm":600,"width_mm":800}}')
            with patch("carpinova_agent.maestro_cli.consult_maestro") as engine:
                code, _, error = self._invoke([
                    "--utterance", "Gabinete", "--candidate", str(path),
                ])
            self.assertEqual(code, 2)
            self.assertIn("clave duplicada", error)
            engine.assert_not_called()

    def test_oversized_candidate_blocked_before_json_parsing(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._candidate(td, " " * 65537)
            code, out, error = self._invoke([
                "--utterance", "Gabinete", "--candidate", str(path),
            ])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("demasiado grande", error)

    def test_nonfinite_constant_rejected_before_preview(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._candidate(td, '{"action":"project","project":{"width_mm":NaN}}')
            code, _, error = self._invoke([
                "--utterance", "Gabinete", "--candidate", str(path),
            ])
            self.assertEqual(code, 2)
            self.assertIn("no admite valores no finitos", error)

    def test_execution_flag_rejected_for_nonutterance_modes(self):
        with patch("carpinova_agent.maestro_cli.consult_maestro") as engine:
            code, _, error = self._invoke(["--question", "bisagras", "--confirm-execute"])
        self.assertEqual(code, 2)
        self.assertIn("requieren --utterance", error)
        engine.assert_not_called()

    def test_noninteractive_preview_cannot_accept_bundle(self):
        code, _, err = self._invoke([
            "--utterance", "Bisagras", "--bundle-dir", "/tmp/know",
        ])
        self.assertEqual(code, 2)
        self.assertIn("previsualización no admite bundle", err)

    def test_confirm_execute_never_overwrites_candidate_input(self):
        with tempfile.TemporaryDirectory() as td:
            candidate = self._candidate(td)
            with patch("carpinova_agent.maestro_cli.consult_maestro") as engine:
                code, _, err = self._invoke([
                    "--utterance", "Gabinete", "--candidate", str(candidate),
                    "--confirm-execute", "--output", str(candidate)
                ], stdin=_FakeTty(), stderr=_FakeTty())
            self.assertEqual(code, 2)
            self.assertIn("no puede sobrescribir", err)
            self.assertEqual(json.loads(candidate.read_text(encoding="utf-8")), CABINET)
            engine.assert_not_called()

    def test_confirm_execute_allows_knowledge_bundle_only_after_tty_approval(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._candidate(td, json.dumps({"action": "knowledge", "query": "bisagras"}))
            preview = preview_natural_request("Buscar bisagras", {"action": "knowledge", "query": "bisagras"})
            _, phrase = _confirmation_display(preview)
            with patch("carpinova_agent.maestro_cli.consult_maestro", return_value={"status": "REFERENCE_ONLY"}) as engine:
                code, out, _ = self._invoke([
                    "--utterance", "Buscar bisagras", "--candidate", str(path),
                    "--bundle-dir", td, "--confirm-execute",
                ], stdin=_FakeTty(phrase + "\n"), stderr=_FakeTty())
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["status"], "REFERENCE_ONLY")
            engine.assert_called_once_with(
                {"action": "knowledge", "query": "bisagras"},
                bundle_dir=Path(td), max_questions=3,
            )

if __name__ == "__main__":
    unittest.main()
