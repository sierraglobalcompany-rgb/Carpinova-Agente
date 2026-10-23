"""Regression for functional PR37 recovery, not a claim of original commit identity."""
import unittest
from xml.etree import ElementTree as ET

from carpinova_agent.core import DesignError
from carpinova_agent.opening_guide import guide_opening_systems, opening_guide_svg


class PR37RecoveredTests(unittest.TestCase):
    def test_exact_g20_svg_and_four_original_cards(self):
        import hashlib
        svg = opening_guide_svg("all")
        self.assertEqual(hashlib.sha256(svg.encode("utf-8")).hexdigest(),
                         "dc4dc701b80247683fefb2214f8976019c43f0e1ade7e08524e7685511730a6d")
        first = svg.index('<rect x="58" y="146" width="554" height="290" rx="13" class="card"/>')
        fifth = svg.index('<rect x="58" y="795" width="1127" height="306" rx="13" class="card"/>')
        four_cards = svg[first:fifth]
        self.assertEqual(hashlib.sha256(four_cards.encode("utf-8")).hexdigest(),
                         "35ad6aa765479ae758e82a4264539779de3a8cbd8650a9e8205472e5bd2116c8")

    def test_preserve_four_openings_and_correct_inverted_t_section(self):
        svg = opening_guide_svg("all")
        root = ET.fromstring(svg)
        for text in ("1. Manija externa", "2. Uñero",
                     "3. Perfil / gola", "4. Por presión"):
            self.assertIn(text, svg)
        shapes = {node.attrib["data-concept"]: node for node in root.iter()
                  if "data-concept" in node.attrib}
        stem = shapes["inverted-t-stem"]
        flange = shapes["inverted-t-lower-flange"]
        front = next(node for node in root.iter()
                     if node.get("data-part") == "moving-drawer-front")
        stem_left = float(stem.get("x"))
        stem_right = stem_left + float(stem.get("width"))
        flange_left = float(flange.get("x"))
        flange_right = flange_left + float(flange.get("width"))
        self.assertLess(flange_left, stem_left)
        self.assertGreater(flange_right, stem_right)
        self.assertGreater(float(flange.get("y")), float(stem.get("y")))
        self.assertGreater(float(front.get("x")), flange_right)
        self.assertIn("ALETA INFERIOR", svg)
        self.assertIn("TOPE DE CAJÓN NO VERIFICADO", svg)
        self.assertIn("PDF 124-125", svg)
        self.assertNotIn("unvalidated-t-crosspiece", svg)
        self.assertEqual(root.get("viewBox"), "0 0 1240 1240")

    def test_all_focus_modes_render_valid_accessible_svg(self):
        for focus in ("all", "handle", "finger_pull", "profile",
                      "push_to_open", "t_rail_concept"):
            with self.subTest(focus=focus):
                root = ET.fromstring(opening_guide_svg(focus))
                self.assertEqual(root.attrib["role"], "img")
                self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}title"))
                self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}desc"))
                assert root.attrib["viewBox"] == "0 0 1240 1240"

    def test_only_one_highlight_and_human_gestures(self):
        for focus in ("handle", "finger_pull", "profile",
                      "push_to_open", "t_rail_concept"):
            with self.subTest(focus=focus):
                r = guide_opening_systems({"type":"opening_system_guide", "focus":focus})
                root = ET.fromstring(r["sketch_svg"])
                self.assertEqual(sum(node.attrib.get("class") == "selected"
                                     for node in root.iter()), 1)
                actions = {node.attrib.get("data-action") for node in root.iter()}
                self.assertIn("insert-fingers", actions)
                self.assertIn("pull-front", actions)

    def test_stays_review_only_and_preserves_intents(self):
        r = guide_opening_systems({"type":"opening_system_guide"})
        self.assertEqual(r["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual([x["intent"] for x in r["opening_options"]],
                         ["handle", "finger_pull", "profile", "push_to_open", None])
        self.assertFalse(r["opening_options"][-1]["selectable_for_drawer"])
        self.assertFalse(r["can_generate_f7c"])
        self.assertEqual(r["piece_count"], 0)
        for field in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(r[field], False)

    def test_rejects_unapproved_fabrication_and_unknown_focus(self):
        for spec in ("invalid", {"type":"opening_system_guide", "focus":"t_profile"},
                     {"type":"opening_system_guide", "fabrication_ready":True},
                     {"type":"opening_system_guide", "focus":0}):
            with self.subTest(spec=spec), self.assertRaises(DesignError):
                guide_opening_systems(spec)

    def test_manual_recover_preserves_base_vocabulary(self):
        from carpinova_agent.drawer_modules import OPENING_CHOICES
        self.assertEqual(OPENING_CHOICES,
                         frozenset(("pending","handle","finger_pull","profile","push_to_open")))


if __name__ == "__main__":
    unittest.main()
