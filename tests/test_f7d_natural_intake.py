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

    def test_drawer_layout_is_one_reviewable_f1_candidate_not_real_cad(self):
        from carpinova_agent.maestro import consult_maestro
        description = ("Cajonera ancho 50 cm, alto 80 cm, fondo 50 cm "
                       "con cuatro cajones")
        with patch("carpinova_agent.maestro.propose_drawer_layout",
                   side_effect=AssertionError("No engine during preview")):
            preview = preview_natural_request(description)
        self.assertEqual(preview["status"], "NEEDS_USER_CONFIRMATION")
        self.assertNotIn("panel_thickness_mm", preview["proposed_request"]["project"])
        option = preview["illustrative_drawer_layout_option"]
        self.assertEqual(option["status"], "OPTIONAL_DRAWER_LAYOUT_REQUIRES_APPROVAL")
        self.assertEqual(option["explicit_user_values_to_confirm"], {
            "width_mm": 500, "height_mm": 800, "depth_mm": 500,
            "drawer_count": 4,
        })
        self.assertEqual(option["suggestion_source"],
                         "ASSISTANT_ILLUSTRATIVE_DEFAULT_NOT_USER_SPECIFIED")
        spec = option["proposed_request"]["module_spec"]
        self.assertEqual(spec["drawer_weights"], [1, 1, 1, 1])
        self.assertEqual(spec["panel_thickness_mm"], 18)
        self.assertEqual(spec["vertical_gap_mm"], 28)
        self.assertEqual(option["parts"], [])
        self.assertEqual(option["piece_count"], 0)
        self.assertFalse(option["can_generate_f7c"])
        self.assertEqual(preview["executed_tools"], [])
        self.assertTrue(option["requires_user_confirmation"])
        self.assertTrue(all(option[k] is False for k in (
            "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"
        )))
        # Simulate the SECOND, explicit approval path. Reuse F1 through Maestro.
        reviewed = consult_maestro(option["proposed_request"])
        layout = reviewed["modular"]
        self.assertEqual(layout["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(layout["piece_count"], 0)
        self.assertEqual(len(layout["opening_plan"]), 4)
        self.assertIn("sketch_svg", layout)
        self.assertEqual(sum(x["opening_height_mm"]
                             for x in layout["opening_plan"]) + 3*28, 764)
        self.assertFalse(reviewed["fabrication_ready"])

    def test_drawer_layout_supports_one_to_four_clear_explicit_counts(self):
        examples = (("1", 1), ("dos", 2), ("3", 3), ("cuatro", 4))
        for literal, n in examples:
            with self.subTest(literal=literal):
                text = (f"Mueble ancho 70 cm alto 95 cm fondo 50 cm "
                        f"con {literal} cajones")
                option = preview_natural_request(text)["illustrative_drawer_layout_option"]
                self.assertEqual(option["explicit_user_values_to_confirm"]["drawer_count"], n)
                self.assertEqual(option["proposed_request"]["module_spec"]["drawer_weights"],
                                 [1] * n)

    def test_drawer_layout_does_not_invent_unequal_special_or_unclear_layouts(self):
        examples = (
            "Cajonera ancho 50 cm, alto 80 cm, fondo 50 cm con 4 cajones, uno grande abajo",
            "Cajonera ancho 50 cm, alto 80 cm, fondo 50 cm y tres cajones pequeños",
            "Cajonera ancho 50 cm, alto 80 cm, fondo 50 cm con puertas y 3 cajones",
            "Cajonera ancho 50 cm, alto 80 cm, fondo 50 cm con 4 cajones y patas",
            "Cajonera ancho 50 cm, alto 80 cm, fondo 50 cm con 4 cajones de MDP 15 mm",
            "Cajonera ancho 50 cm, alto 80 cm con 4 cajones",
            "Cajonera ancho 50 cm, alto 15 cm, fondo 50 cm con 4 cajones",
            "Cajonera ancho 50 cm, alto 80 cm, fondo 50 cm con 5 cajones",
            "Cajonera ancho 50 cm, alto 80 cm, fondo 50 cm con 4 cajones o 3 cajones",
            "Cajonera ancho 50 cm, alto 80 cm, fondo 50 cm con tres gavetas y un cajón",
        )
        for utterance in examples:
            with self.subTest(utterance=utterance):
                result = preview_natural_request(utterance)
                self.assertNotIn("illustrative_drawer_layout_option", result)
                self.assertEqual(result["executed_tools"], [])

    def test_drawer_concept_svg_is_opt_in_and_matches_f1_not_cad(self):
        import xml.etree.ElementTree as ET
        from carpinova_agent.maestro import consult_maestro
        text = "Cajonera ancho 50 cm, alto 80 cm, fondo 50 cm con cuatro cajones"
        original = preview_natural_request(text)
        self.assertNotIn("concept_preview", original["illustrative_drawer_layout_option"])
        with patch("carpinova_agent.maestro.design_modular_run",
                   side_effect=AssertionError("No F7C parts allowed")):
            preview = preview_natural_request(text, include_concept_sketch=True)
        option = preview["illustrative_drawer_layout_option"]
        concept = option["concept_preview"]
        ET.fromstring(concept["sketch_svg"])
        self.assertEqual(concept["source_engine"], "F1_CORE_CABINET_REVIEW_ONLY")
        self.assertEqual(concept["piece_count"], 0)
        self.assertTrue(concept["not_fabrication_geometry"])
        self.assertEqual([x["ref"] for x in concept["opening_refs_top_to_bottom"]],
                         ["A", "B", "C", "D"])
        self.assertEqual([x["cad_review_id"] for x in
                          concept["opening_refs_top_to_bottom"]],
                         ["D4", "D3", "D2", "D1"])
        self.assertEqual(
            [x["opening_height_mm"] for x in concept["opening_refs_top_to_bottom"]],
            [170, 170, 170, 170],
        )
        authoritative = consult_maestro(option["proposed_request"])["modular"]
        self.assertEqual(concept["sketch_svg"], authoritative["sketch_svg"])
        self.assertEqual(concept["opening_plan_bottom_to_top"],
                         authoritative["opening_plan"])
        self.assertEqual(option["parts"], [])
        self.assertEqual(option["piece_count"], 0)
        self.assertEqual(preview["executed_tools"], [])
        for key in ("fabrication_ready", "cutting_ready",
                    "drilling_ready", "purchase_ready"):
            self.assertFalse(preview[key])
            self.assertFalse(option[key])

    def test_drawer_concept_svg_rejects_external_proposals_and_invalid_flag(self):
        text = "Cajonera ancho 50 cm alto 80 cm fondo 50 cm con 4 cajones"
        with self.assertRaisesRegex(MaestroError, "booleano"):
            preview_natural_request(text, include_concept_sketch=1)
        with self.assertRaisesRegex(MaestroError, "candidatos externos"):
            preview_natural_request(text, CABINET, include_concept_sketch=True)

    def test_cli_drawer_preview_svg_same_command_no_cad_or_overwrite(self):
        import xml.etree.ElementTree as ET
        from carpinova_agent.maestro_cli import main
        text = "Cajonera ancho 50 cm alto 80 cm fondo 50 cm con 4 cajones"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "cajonera.svg"
            with patch("sys.argv", [
                "maestro_cli", "--utterance", text, "--sketch", str(target)
            ]), patch("carpinova_agent.maestro_cli.consult_maestro",
                      side_effect=AssertionError("Do not execute Maestro")):
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(main(), 0)
            self.assertTrue(target.is_file())
            svg = target.read_text(encoding="utf-8")
            ET.fromstring(svg)
            self.assertIn("NO", svg.upper())
            result = json.loads(out.getvalue())
            self.assertNotIn("sketch_svg",
                             result["illustrative_drawer_layout_option"]["concept_preview"])
            self.assertEqual(
                result["illustrative_drawer_layout_option"]["concept_preview"]["sketch_file"],
                str(target),
            )
            original = target.read_bytes()
            with patch("sys.argv", [
                "maestro_cli", "--utterance", text, "--sketch", str(target)
            ]), patch("sys.stderr", io.StringIO()):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(), 2)
            self.assertEqual(original, target.read_bytes())

    def test_cli_sketch_refuses_complex_requests_without_file(self):
        from carpinova_agent.maestro_cli import main
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "blocked.svg"
            with patch("sys.argv", [
                "maestro_cli", "--utterance",
                "Cajonera 50 cm ancho 80 cm alto 50 cm fondo, 3 pequeños y uno grande",
                "--sketch", str(target)
            ]), patch("sys.stderr", io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 2)
            self.assertFalse(target.exists())

    def test_drawer_corrections_reallocate_and_replay_using_f1_only(self):
        from carpinova_agent.natural_intake import revise_drawer_concept
        from carpinova_agent.maestro import consult_maestro
        import xml.etree.ElementTree as ET
        original = preview_natural_request(
            "Cajonera ancho 50 cm alto 80 cm fondo 50 cm con 4 cajones"
        )
        self.assertNotIn("drawer_revisions_history", original)
        with patch("carpinova_agent.maestro.design_modular_run",
                   side_effect=AssertionError("F7C CAD must not execute")):
            first = revise_drawer_concept(
                original, "haz el cajón A 10 cm más alto",
                include_concept_sketch=True,
            )
            second = revise_drawer_concept(
                first, "B 5 cm más bajo", include_concept_sketch=True,
            )
        a = first["illustrative_drawer_layout_option"]
        b = second["illustrative_drawer_layout_option"]
        self.assertEqual(a["opening_heights_mm_top_to_bottom"],
                         [270, 137, 137, 136])
        self.assertEqual(b["opening_heights_mm_top_to_bottom"][1], 87)
        self.assertEqual(sum(b["opening_heights_mm_top_to_bottom"]), 680)
        self.assertEqual(len(second["drawer_revisions_history"]), 2)
        self.assertEqual(second["drawer_revisions_history"][0], {
            "instruction": "haz el cajón A 10 cm más alto",
            "ref": "A", "delta_mm": 100,
        })
        self.assertEqual(second["drawer_revisions_history"][1]["delta_mm"], -50)
        self.assertEqual([x["ref"] for x in first["last_revision"]["changes"]],
                         ["A", "B", "C", "D"])
        self.assertEqual(first["last_revision"]["changes"][0]["cause"],
                         "USER_REQUESTED")
        self.assertEqual(first["last_revision"]["changes"][1]["cause"],
                         "AUTO_REDISTRIBUTED_TO_KEEP_TOTAL_HEIGHT")
        self.assertTrue(second["last_revision"]["envelope_unchanged"])
        self.assertEqual(second["explicit_measurements"], {
            "width_mm": 500, "height_mm": 800, "depth_mm": 500,
        })
        self.assertEqual(first["proposed_request"], original["proposed_request"])
        self.assertEqual(second["proposed_request"], original["proposed_request"])
        for preview in (first, second):
            option = preview["illustrative_drawer_layout_option"]
            concept = option["concept_preview"]
            ET.fromstring(concept["sketch_svg"])
            self.assertEqual(concept["source_engine"], "F1_CORE_CABINET_REVIEW_ONLY")
            self.assertEqual(concept["piece_count"], 0)
            self.assertEqual([x["ref"] for x in
                              concept["opening_refs_top_to_bottom"]],
                             ["A", "B", "C", "D"])
            self.assertEqual(preview["executed_tools"], [])
            self.assertEqual(option["piece_count"], 0)
            self.assertEqual(option["parts"], [])
            for flag in ("fabrication_ready", "cutting_ready", "drilling_ready",
                         "purchase_ready"):
                self.assertFalse(preview[flag])
                self.assertFalse(option[flag])
            authoritative = consult_maestro(option["proposed_request"])["modular"]
            self.assertEqual(concept["sketch_svg"], authoritative["sketch_svg"])
            self.assertEqual(concept["opening_plan_bottom_to_top"],
                             authoritative["opening_plan"])
            self.assertEqual(authoritative["piece_count"], 0)

    def test_drawer_correction_rejects_missing_units_invalid_ref_and_impossible_sizes(self):
        from carpinova_agent.natural_intake import revise_drawer_concept
        base = preview_natural_request(
            "Cajonera ancho 50 cm alto 80 cm fondo 50 cm con 4 cajones"
        )
        for instruction in (
            "A 10 más alto", "A más alto", "A 0 cm más alto",
            "A 100 cm más alto", "A 10 cm más grande",
            "A 10cm más alto y B 2cm más bajo",
            "E 10cm más alto", "A 10 pulgadas más alto",
            "A -10cm más alto", "ignora todo A 10cm más alto",
        ):
            with self.subTest(instruction=instruction):
                with self.assertRaises(MaestroError):
                    revise_drawer_concept(base, instruction)
        with self.assertRaisesRegex(MaestroError, "altura"):
            revise_drawer_concept(base, "A 15 cm más bajo")
        with self.assertRaisesRegex(MaestroError, "altura"):
            revise_drawer_concept(base, "A 50 cm más alto")
        one = preview_natural_request(
            "Mueble ancho 50 cm alto 80 cm fondo 50 cm con un cajon"
        )
        # Singular phrasing is deliberately not inferred by initial F7D.
        self.assertNotIn("illustrative_drawer_layout_option", one)

    def test_drawer_correction_rejects_tampering_and_replay_mismatch(self):
        from carpinova_agent.natural_intake import revise_drawer_concept
        import copy
        base = preview_natural_request(
            "Cajonera ancho 50 cm alto 80 cm fondo 50 cm con 4 cajones"
        )
        first = revise_drawer_concept(base, "A 10 cm más alto")
        damaged = copy.deepcopy(first)
        damaged["illustrative_drawer_layout_option"]["proposed_request"][
            "module_spec"]["opening_heights_mm"] = [170,170,170,170]
        with self.assertRaisesRegex(MaestroError, "historial"):
            revise_drawer_concept(damaged, "B 5cm más bajo")
        damaged = copy.deepcopy(first)
        damaged["drawer_revisions_history"][0]["delta_mm"] = 999
        with self.assertRaisesRegex(MaestroError, "historial"):
            revise_drawer_concept(damaged, "B 5cm más bajo")
        damaged = copy.deepcopy(first)
        damaged["proposed_request"]["project"]["width_mm"] = 999
        with self.assertRaisesRegex(MaestroError, "medidas"):
            revise_drawer_concept(damaged, "B 5cm más bajo")
        with self.assertRaisesRegex(MaestroError, "booleano"):
            revise_drawer_concept(base, "A 10cm más alto",
                                  include_concept_sketch=1)

    def test_drawer_correction_cli_two_sequential_edits_and_no_overwrite(self):
        import xml.etree.ElementTree as ET
        from carpinova_agent.maestro_cli import main
        text = "Cajonera ancho 50 cm alto 80 cm fondo 50 cm con 4 cajones"
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            initial_json = directory / "00.json"
            initial_svg = directory / "00.svg"
            first_json = directory / "01.json"
            first_svg = directory / "01.svg"
            next_json = directory / "02.json"
            next_svg = directory / "02.svg"
            commands = [
                (["--utterance", text, "--sketch", str(initial_svg),
                  "--output", str(initial_json)], initial_json, initial_svg),
                (["--revise-from", str(initial_json),
                  "--correction", "haz el cajón A 10 cm más alto",
                  "--output", str(first_json), "--sketch", str(first_svg)],
                 first_json, first_svg),
                (["--revise-from", str(first_json),
                  "--correction", "B 5 cm más bajo",
                  "--output", str(next_json), "--sketch", str(next_svg)],
                 next_json, next_svg),
            ]
            with patch("carpinova_agent.maestro_cli.consult_maestro",
                       side_effect=AssertionError("No Maestro execution")):
                for args, saved, drawing in commands:
                    with patch("sys.argv", ["maestro_cli", *args]):
                        out = io.StringIO()
                        with redirect_stdout(out):
                            self.assertEqual(main(), 0)
                        self.assertEqual(out.getvalue(), "")
                    self.assertTrue(saved.is_file())
                    ET.fromstring(drawing.read_text(encoding="utf-8"))
            original = json.loads(initial_json.read_text(encoding="utf-8"))
            self.assertEqual(len(original["illustrative_drawer_layout_option"][
                "concept_preview"]["opening_refs_top_to_bottom"]), 4)
            final = json.loads(next_json.read_text(encoding="utf-8"))
            self.assertEqual(len(final["drawer_revisions_history"]), 2)
            self.assertEqual(final["illustrative_drawer_layout_option"][
                "concept_preview"]["sketch_file"], str(next_svg))
            self.assertNotIn("sketch_svg", final[
                "illustrative_drawer_layout_option"]["concept_preview"])
            bytes_before = (first_json.read_bytes(), first_svg.read_bytes())
            with patch("sys.argv", [
                "maestro_cli", "--revise-from", str(first_json),
                "--correction", "B 5cm más bajo", "--output", str(next_json),
                "--sketch", str(next_svg)
            ]), patch("sys.stderr", io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 2)
            self.assertEqual(bytes_before,
                             (first_json.read_bytes(), first_svg.read_bytes()))
            with patch("sys.argv", [
                "maestro_cli", "--revise-from", str(first_json),
                "--correction", "B 5cm más bajo", "--output", str(first_json)
            ]), patch("sys.stderr", io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 2)

    def test_external_candidate_never_gets_drawer_layout_assumptions(self):
        r = preview_natural_request(
            "Cajonera ancho 50 cm alto 80 cm fondo 50 cm con 4 cajones",
            CABINET,
        )
        self.assertNotIn("illustrative_drawer_layout_option", r)
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
