"""Review files retain user opening decisions; no fictional hardware geometry."""
import copy
import csv
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from carpinova_agent.core import DesignError
from carpinova_agent.modular import design_modular_run
from carpinova_agent.modular_outputs import modular_bom_csv, modular_front_svg
from carpinova_agent.pilot_cli import pilot_review
from carpinova_agent.mcp_bridge import carpinova_generar_borrador, carpinova_leer_entregable


ROOT = Path(__file__).resolve().parents[1]
INTENTS = ("handle", "push_to_open", "finger_pull", "profile")


def fixture(style: str):
    req = json.loads((ROOT / "examples" /
        f"four-drawer-500x500x800-{style}-UNCONFIRMED.json"
    ).read_text(encoding="utf-8"))
    for drawer, intent in zip(req["module_spec"]["modules"][0]["drawers"], INTENTS):
        drawer["facade"]["opening_system"] = intent
    return req


class ReviewChoicesTests(unittest.TestCase):
    def test_all_four_choices_survive_csv_svg_and_pilot(self):
        for style in ("INSET", "OVERLAY"):
            with self.subTest(style=style):
                req = fixture(style)
                model = design_modular_run(req["module_spec"])
                self.assertEqual(model["piece_count"], 28)
                rows = list(csv.DictReader(StringIO(modular_bom_csv(model))))
                fronts = [r for r in rows if r["role"] == "drawer_facade"]
                self.assertEqual([r["opening_system_intent"] for r in fronts],
                                 list(INTENTS))
                self.assertEqual([r["drawer_facade_style"] for r in fronts],
                                 [style.lower()] * 4)
                self.assertTrue(all(
                    r["production_status"] == "BORRADOR_NO_CORTAR"
                    for r in rows
                ))
                for r in rows:
                    if r["role"] != "drawer_facade":
                        self.assertEqual(r["opening_system_intent"], "")
                        self.assertEqual(r["drawer_facade_style"], "")
                svg = modular_front_svg(model)
                for intent in INTENTS:
                    self.assertIn(
                        f"{style.lower()} | {intent} | SIN MECANIZADO", svg
                    )
                bundle = pilot_review(req)
                self.assertEqual(
                    [r["opening_system_intent"] for r in
                     csv.DictReader(StringIO(bundle["parts-review.csv"]))
                     if r["role"] == "drawer_facade"], list(INTENTS)
                )
                self.assertIn("SIN MECANIZADO", bundle["front-review.svg"])
                for flag in ("fabrication_ready", "cutting_ready",
                             "drilling_ready", "purchase_ready"):
                    self.assertIs(model[flag], False)

    def test_unselected_intent_is_not_silently_confirmed(self):
        req = fixture("OVERLAY")
        req["module_spec"]["modules"][0]["drawers"][2]["facade"]["opening_system"] = "pending"
        model = design_modular_run(req["module_spec"])
        csv_rows = list(csv.DictReader(StringIO(modular_bom_csv(model))))
        selected = next(r for r in csv_rows
                        if r["piece_id"] == "M1-D3-DRAWER_FACADE")
        self.assertEqual(selected["opening_system_intent"], "pending")
        self.assertTrue(any("decidir tirador" in s for s in model["blockers"]))

    def test_mcp_artifact_read_retains_each_decision(self):
        req = fixture("OVERLAY")
        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": tmp}):
                made = carpinova_generar_borrador(
                    json.dumps(req), "four_opening_decisions"
                )
                self.assertEqual(made["piece_count"], 28)
                csv_result = carpinova_leer_entregable(
                    "four_opening_decisions", "parts-review.csv"
                )
                svg_result = carpinova_leer_entregable(
                    "four_opening_decisions", "front-review.svg"
                )
                rows = list(csv.DictReader(StringIO(csv_result["contenido"])))
                self.assertEqual([r["opening_system_intent"] for r in rows
                                  if r["role"] == "drawer_facade"], list(INTENTS))
                self.assertIn("overlay | profile | SIN MECANIZADO",
                              svg_result["contenido"])
                self.assertIs(made["drilling_ready"], False)

    def test_invalid_model_metadata_fails_closed(self):
        model = design_modular_run(fixture("INSET")["module_spec"])
        for bad in ("unknown", True, None):
            with self.subTest(bad=bad):
                altered = copy.deepcopy(model)
                front = next(p for p in altered["parts"]
                             if p["role"] == "drawer_facade")
                front["opening_system"] = bad
                with self.assertRaises(DesignError):
                    modular_bom_csv(altered)
                with self.assertRaises(DesignError):
                    modular_front_svg(altered)


if __name__ == "__main__":
    unittest.main()
