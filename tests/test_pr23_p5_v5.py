"""P5 human booklet, finished-front targets, per-edge policy and safe draft gates."""
from __future__ import annotations

import csv
import hashlib
from io import StringIO
import json
from pathlib import Path
import re
import unittest
from xml.etree import ElementTree

from carpinova_agent.cad_exchange import cad_exchange
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.wall_bar_delivery import (
    reference_rows, review_booklet_svgs, review_files,
)
from carpinova_agent.wall_bar_sheets import (
    classify_edge_context, edge_policy_rows, wall_bar_review_dimensions,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "wall-bar-900-review-p5.json"
EXPECTED_GEOMETRY_SHA = "5c0b8944ba015ef537688afac3ee58b9dd52011267c28278c9134a473cecf947"
EXPECTED_UNCHANGED_P4_SHA = "6a0f875e8c552f5941cc66ed32ddc62f8f8ef481c8c8ad0817cfd85b2ce0b9af"


def page_text(svg: str) -> str:
    root = ElementTree.fromstring(svg)
    return " ".join(" ".join(node.itertext()) for node in root.iter()
                   if node.tag.endswith("text"))


class PR23P5HumanBookletTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        request = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.model = consult_maestro(request)["modular"]
        cls.cad = cad_exchange(cls.model)
        cls.human = wall_bar_review_dimensions(cls.model)
        cls.pages = review_booklet_svgs(cls.model)
        cls.files = review_files(cls.model)

    def test_first_page_reuses_real_isometric_and_identifies_each_cover_edge(self):
        self.assertEqual(self.cad["geometry_sha256"], EXPECTED_GEOMETRY_SHA)
        root = ElementTree.fromstring(self.pages[0])
        text = page_text(self.pages[0])
        for phrase in (
            "90 cm largo", "46 cm fondo", "90 cm alto",
            "60 cm libres", "30 cm cajonera", "4 cm",
            "E01 · cubierta · vista superior", "x_min · muro",
            "x_max · libre", "y_min · frente usuario", "y_max · posterior",
            "PVC rígido 2 mm candidato", "revisar; visibilidad/agua no confirmadas",
            "NO FABRICAR, CORTAR NI PERFORAR",
        ):
            self.assertIn(phrase, text)
        self.assertEqual({node.get("data-edge") for node in root.iter()
                          if node.get("data-edge")},
                         {"x_min", "x_max", "y_min", "y_max"})
        self.assertTrue(any(node.tag.endswith("svg")
                            and node.get("viewBox") == "0 113 1038 740"
                            for node in root.iter()))

    def test_each_drawer_page_distinguishes_visible_front_and_sliding_box(self):
        expected = {
            "A": ("superior", "D1", (292, 178, 15), (244, 120, 400),
                  (214, 105, 370)),
            "B": ("intermedio", "D2", (292, 178, 15), (244, 120, 400),
                  (214, 105, 370)),
            "C": ("inferior", "D3", (292, 473, 15), (244, 390, 400),
                  (214, 375, 370)),
        }
        for letter, (position, drawer_id, face, outside, inside) in expected.items():
            with self.subTest(drawer=letter):
                summary = self.human["facades"][letter]
                box = self.human["drawer_boxes"][drawer_id]
                self.assertEqual((summary["width_mm"], summary["height_mm"],
                                  summary["thickness_mm"]), face)
                self.assertEqual((box["width_mm"], box["height_mm"],
                                  box["depth_mm"]), outside)
                self.assertEqual(tuple(box["internal_clear_dimensions_mm"]), inside)
                svg = self.files[f"CN-BAR-001-cajon-{letter}.svg"]
                root = ElementTree.fromstring(svg)
                text = page_text(svg)
                self.assertEqual(len([n for n in root.iter()
                                      if n.get("data-piece-id")]), 6)
                for phrase in (
                    f"Cajón {letter} · {position}",
                    "Frente blanco visible cuando cierra",
                    "Caja de madera que se desliza detrás",
                    "Medida por fuera de la caja que se desliza",
                    "Espacio útil final: pendiente de validar",
                    f"{letter}02", f"{letter}06",
                    "Pared frontal INTERIOR", "no es otra fachada visible",
                    "Frente decorativo EXTERIOR aplicado", "Fondo inferior",
                ):
                    self.assertIn(phrase, text)
                physical_ids = [node.get("data-piece-id") for node in root.iter()
                                if node.get("data-piece-id")]
                self.assertEqual(len(physical_ids), 6)
                self.assertEqual(len(set(physical_ids)), 6)
                expected_ids = {row["id_cad"] for row in reference_rows(self.model)
                                if row["referencia"].startswith(letter)}
                self.assertEqual(set(physical_ids), expected_ids)
                projection_nodes = [
                    node for node in root.iter()
                    if node.get("data-projection-view") == "assembled"
                ]
                self.assertEqual(
                    {node.get("data-projection-piece-id")
                     for node in projection_nodes},
                    expected_ids,
                )
                self.assertEqual(
                    {node.get("data-projection-reference")
                     for node in projection_nodes},
                    {row["referencia"] for row in reference_rows(self.model)
                     if row["referencia"].startswith(letter)},
                )
                front_wall_label = next(
                    node for node in root.iter()
                    if node.tag.endswith("text")
                    and (node.text or "").strip()
                    == f"{letter}02 · pared frontal INTERIOR"
                )
                width_dimension_label = next(
                    node for group in root.iter()
                    if group.get("data-dimension-id") == f"{letter}-box-width"
                    for node in group.iter()
                    if node.tag.endswith("text")
                )
                self.assertGreater(
                    float(width_dimension_label.get("y"))
                    - float(front_wall_label.get("y")),
                    16,
                )
                for node in projection_nodes:
                    for pair in node.get("points", "").split():
                        px, py = (float(value) for value in pair.split(","))
                        self.assertGreaterEqual(px, 1020)
                        self.assertLessEqual(px, 1560)
                        self.assertGreaterEqual(py, 200)
                        self.assertLessEqual(py, 630)
                self.assertIn("Primero se forma la caja con cuatro paredes y el fondo", text)
                self.assertIn("Después se fija el frente decorativo aplicado", text)
                self.assertIn("la unión y su fijación no están definidas", text)
                self.assertIn("no es una segunda fachada exterior", text)
                self.assertIn("Sin rieles, tornillos ni fijación dibujados", text)
                self.assertNotIn("Caja exterior:", text)
                self.assertNotIn("revelado", text.lower())

    def test_gap_page_distinguishes_finished_targets_from_invalid_raw_interpretation(self):
        root = ElementTree.fromstring(self.pages[4])
        text = page_text(self.pages[4])
        gaps = {node.get("data-gap-id"): node.get("data-nominal-gap-mm")
                for node in root.iter() if node.get("data-gap-id")}
        self.assertEqual(gaps, {
            "PERIMETER-LEFT": "4", "PERIMETER-RIGHT": "4",
            "PERIMETER-TOP": "4", "PERIMETER-BOTTOM": "4",
            "A-B": "4", "B-C": "4",
        })
        self.assertEqual(
            {node.get("data-gap-detail-for") for node in root.iter()
             if node.get("data-gap-detail-for")},
            {"A-B", "B-C"},
        )
        cabinet = next(node for node in root.iter()
                       if node.get("data-cabinet-outline") == "drawer-module")
        self.assertEqual(cabinet.get("data-source-width-mm"), "300")
        self.assertEqual(cabinet.get("data-source-height-mm"), "845")
        fronts = {node.get("data-front-letter"): node for node in root.iter()
                  if node.get("data-front-letter")}
        self.assertEqual(
            {letter: (
                fronts[letter].get("data-cad-piece-id"),
                fronts[letter].get("data-origin-x-mm"),
                fronts[letter].get("data-origin-y-mm"),
                fronts[letter].get("data-width-mm"),
                fronts[letter].get("data-height-mm"),
            ) for letter in "ABC"},
            {
                "A": ("CAJONERA_DERECHA-D1-DRAWER_FACADE", "604", "703", "292", "178"),
                "B": ("CAJONERA_DERECHA-D2-DRAWER_FACADE", "604", "521", "292", "178"),
                "C": ("CAJONERA_DERECHA-D3-DRAWER_FACADE", "604", "44", "292", "473"),
            },
        )
        for phrase in (
            "4 mm entre envolventes exteriores terminadas propuestas",
            "holgura física sigue sin verificar", "NO CORTAR",
            "SIN HOLGURA FÍSICA CERTIFICADA",
            "INVALID_RAW_VS_FINISHED", "el cero no se acepta como holgura",
            "4 → 0 mm teóricos",
            "288 × 174", "no es la luz en profundidad para push-to-open",
            "Cajonera completa · elevación frontal proporcional al CAD",
        ):
            self.assertIn(phrase, text)
        self.assertEqual(sum(1 for node in root.iter()
                             if node.tag.endswith("text")
                             and node.text == "Ampliación esquemática · NO A ESCALA"), 2)
        edge = self.model["wall_bar_review"]["front_edgebanding_review"]
        self.assertEqual(edge["finished_outer_target"], "PROPOSED")
        self.assertEqual(edge["physical_edge_model"], "NOT_MODELED")
        self.assertEqual(edge["cut_dimensions"], "NOT_VERIFIED")
        self.assertEqual(edge["actual_gap"], "NOT_VERIFIED")
        self.assertEqual(edge["gaps_if_nominal_panels_are_cut_raw_then_banded_mm"],
                         {"D3_D2": 0, "D2_D1": 0})
        self.assertEqual(edge["raw_interpretation_scenario"]["status"],
                         "INVALID_RAW_VS_FINISHED")
        self.assertFalse(edge["raw_interpretation_scenario"]["zero_gap_is_accepted"])
        self.assertIs(edge["cutting_dimensions_authorized"], False)

    def test_25_nonfacade_geometries_are_byte_stable_by_id_role_origin_and_size(self):
        records = sorted(({
            key: box[key] for key in
            ("piece_id", "role", "origin_xyz_mm", "size_xyz_mm")
        } for box in self.cad["boxes"] if box["role"] != "drawer_facade"),
            key=lambda item: item["piece_id"])
        digest = hashlib.sha256(json.dumps(
            records, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        self.assertEqual(len(records), 25)
        self.assertEqual(digest, EXPECTED_UNCHANGED_P4_SHA)
        fronts = {box["piece_id"]: (box["origin_xyz_mm"], box["size_xyz_mm"])
                  for box in self.cad["boxes"] if box["role"] == "drawer_facade"}
        self.assertEqual(fronts, {
            "CAJONERA_DERECHA-D1-DRAWER_FACADE": ([604, 703, 0], [292, 178, 15]),
            "CAJONERA_DERECHA-D2-DRAWER_FACADE": ([604, 521, 0], [292, 178, 15]),
            "CAJONERA_DERECHA-D3-DRAWER_FACADE": ([604, 44, 0], [292, 473, 15]),
        })

    def test_one_96_edge_table_drives_csv_json_and_summary_categories(self):
        rows = edge_policy_rows(self.model)
        self.assertEqual(len(rows), 96)
        self.assertTrue(all(row["moisture"] == "unknown" for row in rows
                            if row["conditional_candidate_policy"]
                            == "RIGID_PVC_2MM_CANDIDATE_MOISTURE_UNVERIFIED"))
        self.assertEqual(len({(row["piece_id"], row["face_edge"])
                              for row in rows}), 96)
        files = self.files
        csv_rows = list(csv.DictReader(StringIO(
            files["CN-BAR-001-cantos-por-borde-REVISION.csv"])))
        json_rows = json.loads(
            files["CN-BAR-001-cantos-por-borde-REVISION.json"])
        self.assertEqual(len(csv_rows), 96)
        self.assertEqual(json_rows, rows)
        cover = {row["face_edge"]: row for row in rows
                 if row["piece_id"] == "BAR-COVER-TOP"}
        self.assertEqual(cover["x_max"]["edge_axis"], "X")
        self.assertEqual(cover["y_min"]["edge_axis"], "Z")
        self.assertEqual(cover["x_max"]["edge_policy"],
                         "RIGID_PVC_2MM_CANDIDATE")
        self.assertEqual(cover["y_min"]["edge_policy"],
                         "RIGID_PVC_2MM_CANDIDATE")
        self.assertEqual(cover["x_min"]["conditional_candidate_policy"],
                         "NO_DECORATIVE_EDGE_CANDIDATE")
        self.assertEqual(cover["x_min"]["certainty"],
                         "CONDITIONAL_NOT_VERIFIED")
        self.assertEqual(cover["y_max"]["edge_policy"], "REVIEW_REQUIRED")
        self.assertTrue(all(row["physical_edge_model"] == "NOT_MODELED"
                            for row in rows))

    def test_synthetic_context_policy_keeps_exposure_and_moisture_distinct(self):
        cases = (
            (("visible", "low", "dry", False),
             "FLEXIBLE_PVC_0_45MM_CANDIDATE"),
            (("hidden", "none", "dry", True),
             "NO_DECORATIVE_EDGE_CANDIDATE"),
            (("hidden", "none", "exposed", True),
             "PROTECTION_OR_SEAL_REVIEW_REQUIRED"),
            (("unknown", "unknown", "unknown", False), "REVIEW_REQUIRED"),
            (("visible", "impact", "dry", False),
             "RIGID_PVC_2MM_CANDIDATE"),
            (("visible", "impact", "unknown", False),
             "RIGID_PVC_2MM_CANDIDATE"),
        )
        for (exposure, contact, moisture, protected), expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_edge_context(
                    exposure, contact, moisture, protected=protected
                )["edge_policy"], expected)

    def test_native_ci_jobs_are_guarded_at_job_level_for_this_pr(self):
        workflow_dir = ROOT / ".github" / "workflows"
        expected_guards = {
            ("mcp-bridge-ci.yml", "native-cad-deliverables"):
                "    if: ${{ false }} # desactivado por política en PR/push; "
                "reactivación futura fuera de P5",
            ("wall-bar-native.yml", "native-wall-bar"):
                "    if: ${{ false }} # desactivado por política P5; "
                "reactivación futura fuera del alcance",
        }
        for (filename, job), expected_guard in expected_guards.items():
            with self.subTest(job=job):
                lines = (workflow_dir / filename).read_text(encoding="utf-8").splitlines()
                start = lines.index(f"  {job}:")
                end = next((index for index in range(start + 1, len(lines))
                            if re.fullmatch(r"  [A-Za-z0-9_-]+:", lines[index])),
                           len(lines))
                block = lines[start:end]
                self.assertEqual(block[1], expected_guard)
                self.assertIn("    steps:", block)
                self.assertNotIn("workflow_dispatch", "\n".join(lines))
        for filename in ("freecad-native.yml", "maestro-ci.yml"):
            text = (workflow_dir / filename).read_text(encoding="utf-8")
            self.assertIn("startsWith(github.head_ref, 'feat/f7')", text)

    def test_last_page_is_a_technical_annex_not_28_wood_boards_to_cut(self):
        svg = self.pages[-1]
        root = ElementTree.fromstring(svg)
        text = page_text(svg)
        cards = [node for node in root.iter()
                 if node.tag.endswith("rect") and node.get("data-reference")]
        wood = [node for node in cards if node.get("data-category") == "wood-panel"]
        concepts = [node for node in cards
                    if node.get("data-category") == "support-concept"]
        self.assertEqual(len(cards), 28)
        self.assertEqual(len(wood), 24)
        self.assertEqual(len(concepts), 4)
        self.assertIn("ANEXO TÉCNICO", text)
        self.assertIn("24 paneles nominales de madera", text)
        self.assertIn("4 marcadores conceptuales", text)
        self.assertIn("no son 28 piezas de madera para cortar", text)
        self.assertIn("Medidas en mm · nominales · NO autoriza corte", text)
        self.assertEqual({node.get("data-reference") for node in cards},
                         {row["referencia"] for row in reference_rows(self.model)})
        for key in ("fabrication_ready", "cutting_ready",
                    "drilling_ready", "purchase_ready"):
            self.assertIs(self.model[key], False)


if __name__ == "__main__":
    unittest.main()
