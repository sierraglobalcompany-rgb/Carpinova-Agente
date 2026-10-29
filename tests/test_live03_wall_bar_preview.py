"""Focal LIVE03 tests for a nominal, not-yet-accepted wall-bar preview."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from carpinova_agent.cad_exchange import cad_exchange
from carpinova_agent.conversation_flow import prepare_wall_bar_nominal_review
from carpinova_agent.maestro import MaestroError, consult_maestro
from carpinova_agent.wall_bar_delivery import review_booklet_svgs
from test_live02_wall_bar_flow import OWNER_CLARIFICATION, OWNER_FIRST


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "wall-bar-900-review.json"
FIXTURE_SHA256 = "a580cc0d1c58e288f67615f7bd66a601e1c4f32be1c63cfac9d1cbf7b60113b0"
CAD_SHA256 = "a81504b9e04745ef746b9a7d249fc6e805524260dca954444056fb1b02a5bd8a"


class Live03WallBarPreviewTests(unittest.TestCase):
    def prepare(self, clarification: str = OWNER_CLARIFICATION):
        return prepare_wall_bar_nominal_review(OWNER_FIRST, [clarification])

    def test_real_measurements_prepare_fixture_visuals_without_approval_record(self):
        prepared = self.prepare()
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), FIXTURE_SHA256)
        self.assertEqual(prepared["status"], "DRAFT_PENDING_OWNER_VISUAL")
        self.assertEqual(prepared["request"], fixture)
        self.assertEqual(prepared["request_sha256"], hashlib.sha256(
            json.dumps(fixture, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest())
        self.assertEqual(prepared["source_provenance"]["owner_measurements"],
                         "CARPN_LIVE01_TRANSCRIPT_AND_CLARIFICATION")
        self.assertEqual(prepared["source_provenance"]["prior_design_choices"],
                         "PRIOR_DESIGN_DECISION_REPORTED")
        self.assertEqual(prepared["source_provenance"]["technical_fixture_values"],
                         "TEST_FIXTURE_NOT_USER_CHOICE")
        self.assertEqual(prepared["owner_visual_acceptance"], "PENDING")
        self.assertEqual(prepared["authorization"], "NOT_FABRICATION_APPROVAL")
        self.assertNotIn("confirmation", prepared)
        self.assertNotIn("layout_approved", prepared)
        self.assertNotIn("construction_approved", prepared)
        self.assertNotIn("flow_review_json", prepared)
        self.assertTrue(prepared["source_provenance"]["standard_claim_unverified"])
        spec = prepared["request"]["module_spec"]
        self.assertEqual(spec["design_choices"]["aesthetic_presentation"],
                         "bicolor_modern_preliminary")
        self.assertTrue(all(d["facade"]["opening_system"] == "handle"
                            for d in spec["cabinet_module"]["drawers"]))
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(prepared[flag], False)

    def test_maestro_geometry_is_unchanged_and_booklet_uses_reported_visual_choices(self):
        prepared = self.prepare()
        answer = consult_maestro(prepared["request"])
        model = answer["modular"]
        cad = cad_exchange(model)
        self.assertEqual(answer["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(len(model["parts"]), 24)
        self.assertEqual(cad["geometry_sha256"], CAD_SHA256)
        pages = review_booklet_svgs(model)
        self.assertEqual(len(pages), 7)
        cover = pages[0]
        self.assertIn("Bicolor preliminar · no acabado aprobado", cover)
        self.assertIn("Cubierta roble claro · lateral/frentes blanco mate", cover)
        self.assertIn("Veta X decorativa; veta productiva sin confirmar", cover)
        self.assertIn("Tirador recto negro · concepto", cover)
        self.assertIn("Sin herraje, SKU, cantidad, posición ni taladros", cover)
        self.assertIn('fill="#f2f3f0"', cover)
        self.assertIn('data-axis="X"', cover)
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(answer[flag], False)
            self.assertIs(model[flag], False)

    def test_ambiguous_or_missing_owner_measurements_block_request(self):
        with self.assertRaisesRegex(MaestroError, "medidas explícitas verificadas"):
            prepare_wall_bar_nominal_review(OWNER_FIRST)
        with self.assertRaisesRegex(MaestroError, "medidas explícitas verificadas"):
            self.prepare(OWNER_CLARIFICATION + " La altura total es 91 centímetros.")

    def test_mutating_request_breaks_protected_fixture_binding(self):
        first = self.prepare()
        second = self.prepare()
        first["request"]["module_spec"]["design_choices"][
            "aesthetic_presentation"] = "undecided"
        mutated_sha = hashlib.sha256(json.dumps(
            first["request"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        self.assertNotEqual(first["request_sha256"], mutated_sha)
        self.assertEqual(second["request"]["module_spec"]["design_choices"][
            "aesthetic_presentation"], "bicolor_modern_preliminary")
        self.assertEqual(json.loads(FIXTURE.read_text(encoding="utf-8"))["module_spec"][
            "design_choices"]["aesthetic_presentation"], "bicolor_modern_preliminary")


if __name__ == "__main__":
    unittest.main()
