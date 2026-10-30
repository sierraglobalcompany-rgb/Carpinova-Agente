"""Human-facing P4 acceptance from Maestro/CADExchange, without geometry changes."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from xml.etree import ElementTree

from carpinova_agent.cad_exchange import cad_exchange
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.wall_bar_delivery import reference_rows, review_booklet_svgs, review_files
from carpinova_agent.wall_bar_sheets import wall_bar_review_dimensions

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "wall-bar-900-review.json"
EXPECTED_GEOMETRY_SHA = "1e560b4856e3483ff6772a4da477d967d10aa6070fb2e96242c58f494c003492"


def page_text(svg: str) -> str:
    root = ElementTree.fromstring(svg)
    return " ".join("".join(node.itertext()) for node in root.iter()
                   if node.tag.endswith("text"))


class PR23P4HumanBookletTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        request = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.model = consult_maestro(request)["modular"]
        cls.cad = cad_exchange(cls.model)
        cls.human = wall_bar_review_dimensions(cls.model)
        cls.pages = review_booklet_svgs(cls.model)
        cls.files = review_files(cls.model)

    def test_first_page_explains_the_bar_with_dimension_lines(self):
        self.assertEqual(self.cad["geometry_sha256"], EXPECTED_GEOMETRY_SHA)
        root = ElementTree.fromstring(self.pages[0])
        text = page_text(self.pages[0])
        for phrase in (
            "90 cm de largo", "46 cm de fondo", "90 cm de alto",
            "60 cm libres", "30 cm cajonera", "4 cm",
            "Muro en el extremo corto", "cajones abren por el costado largo",
        ):
            self.assertIn(phrase, text)
        dimension_ids = {node.get("data-dimension-id") for node in root.iter()
                         if node.get("data-dimension-id")}
        self.assertEqual(dimension_ids, {
            "plan-length", "plan-depth", "plan-free-span",
            "plan-cabinet-width", "elevation-length", "elevation-height",
        })

    def test_each_drawer_page_distinguishes_visible_front_and_sliding_box(self):
        expected = {
            "A": ("superior", "D1", (296, 180, 15), (244, 120, 400),
                  (214, 105, 370)),
            "B": ("intermedio", "D2", (296, 180, 15), (244, 120, 400),
                  (214, 105, 370)),
            "C": ("inferior", "D3", (296, 477, 15), (244, 390, 400),
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
                    "no es otra tapa visible", "fondo horizontal de abajo",
                ):
                    self.assertIn(phrase, text)
                self.assertNotIn("Caja exterior:", text)
                self.assertNotIn("revelado", text.lower())

    def test_gap_page_shows_both_nominal_gaps_and_edgeband_risk(self):
        root = ElementTree.fromstring(self.pages[4])
        text = page_text(self.pages[4])
        gaps = {node.get("data-gap-id"): node.get("data-nominal-gap-mm")
                for node in root.iter() if node.get("data-gap-id")}
        self.assertEqual(gaps, {"A-B": "2", "B-C": "2"})
        for phrase in (
            "2 mm nominales", "NO RESUELTO", "NO CORTAR",
            "interferencia teórica de -2 mm", "292 mm teóricos, no para sierra",
            "3 mm finales: alternativa a evaluar, no seleccionada",
            "no es la luz en profundidad para push-to-open",
        ):
            self.assertIn(phrase, text)
        edge = self.model["wall_bar_review"]["front_edgebanding_review"]
        self.assertEqual(edge["gaps_if_nominal_panels_are_cut_raw_then_banded_mm"],
                         {"D3_D2": -2, "D2_D1": -2})
        self.assertIs(edge["cutting_dimensions_authorized"], False)

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
