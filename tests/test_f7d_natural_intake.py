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

    def test_explicit_dimensions_make_partial_preview_without_technical_assumptions(self):
        from carpinova_agent.natural_intake import extract_explicit_dimensions
        text = "Quiero un gabinete, ancho 80 cm, alto 72 cm, fondo 55 cm."
        data = extract_explicit_dimensions(text)
        self.assertEqual(data["dimensions_mm"], {
            "width_mm": 800, "height_mm": 720, "depth_mm": 550,
        })
        self.assertEqual({e["field"] for e in data["source_provenance"]},
                         {"width_mm", "height_mm", "depth_mm"})
        for item in data["source_provenance"]:
            self.assertEqual(text[item["start"]:item["end"]], item["literal"])
            self.assertEqual(item["source"], "user_literal")
        r = preview_natural_request(text)
        self.assertEqual(r["status"], "NEEDS_USER_CONFIRMATION")
        project = r["proposed_request"]["project"]
        self.assertEqual(project["project_type"], "gabinete")
        self.assertEqual(project["width_mm"], 800)
        self.assertEqual(project["height_mm"], 720)
        self.assertEqual(project["depth_mm"], 550)
        self.assertNotIn("panel_thickness_mm", project)
        self.assertNotIn("construction", project)
        self.assertEqual(r["executed_tools"], [])
        self.assertTrue(r["requires_user_confirmation"])
        self.assertFalse(any(r[key] for key in
                         ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")))

    def test_reverse_format_and_comma_are_literally_converted(self):
        r = preview_natural_request(
            "Gabinete de 60,5 cm de ancho, 720 mm de alto y 55 cm de profundidad")
        self.assertEqual(r["proposed_request"]["project"], {
            "project_type": "gabinete",
            "width_mm": 605, "height_mm": 720, "depth_mm": 550,
        })

    def test_ambiguous_dimensions_fail_closed_without_guessing(self):
        from carpinova_agent.natural_intake import extract_explicit_dimensions
        for utterance in (
            "Gabinete 80 x 72 x 55 cm",
            "Gabinete ancho 80 alto 72 fondo 55",
            "Gabinete ancho 30 pulgadas alto 20 pulgadas",
        ):
            with self.subTest(text=utterance):
                result = preview_natural_request(utterance)
                self.assertEqual(result["status"], "NEEDS_STRUCTURED_PROPOSAL")
                self.assertIsNone(result["proposed_request"])
        q = extract_explicit_dimensions("Gabinete ancho 80 cm, ancho 90 cm, alto 70 cm")
        self.assertIn("width_mm", q["ambiguous_fields"])
        self.assertNotIn("width_mm", q["dimensions_mm"])
        self.assertEqual(q["dimensions_mm"], {"height_mm": 700})
        r = preview_natural_request("Gabinete ancho 80 cm o 90 cm")
        self.assertIn("width_mm", r["ambiguous_fields"])
        self.assertIsNone(r["proposed_request"])

    def test_component_vs_whole_type_remains_reviewable_not_geometry(self):
        text = "Un gabinete de 80 cm de ancho con 3 cajones, alto 72 cm"
        result = preview_natural_request(text)
        self.assertEqual(result["proposed_request"]["project"]["project_type"],
                         "gabinete")
        self.assertEqual(result["proposed_request"]["project"]["width_mm"], 800)
        self.assertEqual(result["proposed_request"]["project"]["height_mm"], 720)
        with patch("carpinova_agent.maestro.design_modular_run",
                   side_effect=AssertionError("Geometry cannot execute")):
            self.assertEqual(preview_natural_request(text)["executed_tools"], [])

    def test_drawer_subpart_measure_does_not_become_furniture_depth(self):
        r = preview_natural_request(
            "Gabinete de 80 cm de ancho, con un cajón de 30 cm de fondo")
        self.assertEqual(r["proposed_request"]["project"]["width_mm"], 800)
        self.assertNotIn("depth_mm", r["proposed_request"]["project"])
        self.assertIn("depth_mm", r["ambiguous_fields"])
        other = preview_natural_request(
            "Mueble con 3 cajones, ancho 80 cm, alto 72 cm")
        self.assertNotIn("project_type", other["proposed_request"]["project"])

    def test_clear_cabinet_offers_single_explicitly_illustrative_choice(self):
        text = "Quiero un gabinete ancho 80 cm, alto 72 cm y fondo 55 cm"
        with patch("carpinova_agent.maestro.design_modular_run",
                   side_effect=AssertionError("No geometry before confirmation")):
            r = preview_natural_request(text)
        self.assertEqual(r["status"], "NEEDS_USER_CONFIRMATION")
        self.assertNotIn("panel_thickness_mm", r["proposed_request"]["project"])
        option = r["illustrative_option"]
        self.assertEqual(option["status"], "OPTIONAL_VISUAL_PRESET_REQUIRES_APPROVAL")
        candidate = option["proposed_request"]
        self.assertEqual(candidate["project"], {
            "project_type": "gabinete",
            "width_mm": 800,
            "height_mm": 720,
            "depth_mm": 550,
            "panel_thickness_mm": 15,
            "construction": "sides_full",
        })
        self.assertEqual(option["suggested_fields"]["panel_thickness_mm"]["source"],
                         "ASSISTANT_ILLUSTRATIVE_DEFAULT_NOT_USER_SPECIFIED")
        self.assertEqual(option["suggested_fields"]["construction"]["source"],
                         "ASSISTANT_ILLUSTRATIVE_DEFAULT_NOT_USER_SPECIFIED")
        self.assertEqual(r["executed_tools"], [])
        self.assertTrue(option["requires_user_confirmation"])
        self.assertTrue(all(option[k] is False for k in (
            "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"
        )))

        # A deliberate, separate accepted F3 candidate uses ONLY the existing
        # deterministic engine; it is still explicitly not fabrication-ready.
        from carpinova_agent.maestro import consult_maestro
        actual = consult_maestro(candidate)
        self.assertEqual(actual["project"]["phase"], "GEOMETRY_DRAFT")
        design = actual["project"]["design"]
        self.assertEqual(design["dimensions"]["external_width_mm"], 800)
        self.assertEqual(design["dimensions"]["external_height_mm"], 720)
        self.assertEqual(len(design["parts"]), 2)
        self.assertFalse(actual["fabrication_ready"])
        self.assertFalse(actual["cutting_ready"])

    def test_visual_preset_is_withheld_for_complicated_or_underspecified_cabinets(self):
        for text in (
            "Gabinete ancho 80 cm, alto 72 cm y fondo 55 cm con 3 cajones",
            "Gabinete ancho 80 cm, alto 72 cm y fondo 55 cm con dos puertas",
            "Gabinete ancho 80 cm, alto 72 cm y fondo 55 cm en MDP 18mm",
            "Gabinete ancho 80 cm, alto 72 cm y fondo 55 cm suspendido",
            "Gabinete ancho 80 cm, alto 72 cm",
            "Gabinete ancho 80 cm, alto 72 cm y fondo 55 cm o 60 cm",
            "Gabinete ancho 2 cm, alto 72 cm y fondo 55 cm",
        ):
            with self.subTest(text=text):
                preview = preview_natural_request(text)
                self.assertNotIn("illustrative_option", preview)
                self.assertEqual(preview["executed_tools"], [])

    def test_external_cabinet_candidate_is_not_auto_enriched_with_defaults(self):
        r = preview_natural_request(
            "Gabinete ancho 80 cm, alto 72 cm y fondo 55 cm", CABINET
        )
        self.assertNotIn("illustrative_option", r)
        self.assertEqual(r["proposed_request"], CABINET)

    def test_existing_explicit_candidate_does_not_get_overwritten_by_extractor(self):
        r = preview_natural_request("Gabinete ancho 81 cm", CABINET)
        self.assertEqual(r["proposed_request"], CABINET)
        self.assertEqual(r["status"], "NEEDS_USER_CONFIRMATION")

    def test_cli_plain_utterance_with_dimensions_previews_but_never_executes(self):
        from carpinova_agent.maestro_cli import main
        with patch("sys.argv", [
            "maestro_cli", "--utterance", "Gabinete ancho 80 cm, alto 72 cm, fondo 55 cm"
        ]):
            with patch("carpinova_agent.maestro_cli.consult_maestro") as engine:
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(main(), 0)
                result = json.loads(out.getvalue())
                self.assertEqual(result["status"], "NEEDS_USER_CONFIRMATION")
                self.assertEqual(result["proposed_request"]["project"]["width_mm"], 800)
                engine.assert_not_called()

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
