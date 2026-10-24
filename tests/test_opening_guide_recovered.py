"""Regression for functional PR37 recovery, not a claim of original commit identity."""
import unittest
from xml.etree import ElementTree as ET

from carpinova_agent.core import DesignError
from carpinova_agent.opening_guide import guide_opening_systems, opening_guide_svg


class PR37RecoveredTests(unittest.TestCase):
    def test_g23_svg_and_first_four_openings_remain_identical(self):
        import hashlib
        svg = opening_guide_svg("all")
        self.assertEqual(hashlib.sha256(svg.encode("utf-8")).hexdigest(),
                         "11f5c3fdd7a6ad14da1da9a6b9b20b6468311b46a77a5c495c87c2fb5f9574a7")
        first = svg.index('<rect x="58" y="146" width="554" height="290" rx="13" class="card"/>')
        fifth = svg.index('<rect x="58" y="795" width="1127" height="573" rx="13" class="card"/>')
        self.assertEqual(hashlib.sha256(svg[first:fifth].encode("utf-8")).hexdigest(),
                         "35ad6aa765479ae758e82a4264539779de3a8cbd8650a9e8205472e5bd2116c8")

    def test_g23_blocked_vs_accessible_is_an_honest_explanation(self):
        svg = opening_guide_svg("all")
        root = ET.fromstring(svg)
        self.assertEqual(root.get("viewBox"), "0 0 1240 1510")
        for text in ("A · ENTRADA BLOQUEADA", "B · ACCESO POSIBLE",
                     "La T es FIJA", "AGARRAR el borde gris",
                     "H ≈ 20 mm es propuesta del usuario",
                     "NO es mínimo recomendado",
                     "SIN VALIDAR"):
            self.assertIn(text, svg)
        shapes = {node.get("data-concept"): node for node in root.iter()
                  if node.get("data-concept")}
        stem = shapes["inverted-t-stem"]
        flange = shapes["inverted-t-lower-flange"]
        self.assertLess(float(flange.get("x")), float(stem.get("x")))
        self.assertGreater(float(flange.get("x")) + float(flange.get("width")),
                           float(stem.get("x")) + float(stem.get("width")))
        self.assertGreater(float(flange.get("y")), float(stem.get("y")))
        for field in ("H-vertical-clearance", "V-top-overhang",
                      "access-height-h-unverified"):
            self.assertIn(field, shapes)
        parts = {node.get("data-part"): node for node in root.iter()
                 if node.get("data-part")}
        closed_top = parts["blocked-fixed-top-board"]
        closed_front = parts["blocked-drawer-front"]
        open_top = parts["accessible-fixed-top-board"]
        open_front = parts["moving-drawer-front"]
        self.assertEqual(float(closed_top.get("y")) + float(closed_top.get("height")),
                         float(closed_front.get("y")))
        self.assertLess(float(open_top.get("y")) + float(open_top.get("height")),
                        float(open_front.get("y")))
        actions = {node.get("data-action") for node in root.iter()
                   if node.get("data-action")}
        self.assertTrue({"insert-fingers", "grip-drawer-front", "pull-front"} <= actions)
        self.assertFalse(any(node.get("class") == "finger" for node in root.iter()))
        self.assertNotIn("touch-lower-flange", svg)
        self.assertIn("T invertida", root.get("aria-label"))
        self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}desc"))

    def test_all_focus_modes_render_valid_accessible_svg(self):
        for focus in ("all", "handle", "finger_pull", "profile",
                      "push_to_open", "t_rail_concept"):
            with self.subTest(focus=focus):
                root = ET.fromstring(opening_guide_svg(focus))
                self.assertEqual(root.attrib["role"], "img")
                self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}title"))
                self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}desc"))
                assert root.attrib["viewBox"] == "0 0 1240 1510"

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

    def test_g30_true_transverse_inverted_t_is_in_existing_maestro_output(self):
        """Prove the orientation and side-to-side span without a fabricated joint."""
        r = guide_opening_systems({"type": "opening_system_guide",
                                   "focus": "t_rail_concept"})
        svg = r["between_sides_concept_svg"]
        root = ET.fromstring(svg)
        self.assertEqual(root.get("role"), "img")
        self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}title"))
        self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}desc"))
        parts = {node.get("data-part"): node for node in root.iter()
                 if node.get("data-part")}
        li, ld = parts["LI"], parts["LD"]
        rail = parts["rail-spanning-between-sides"]
        self.assertEqual(float(li.get("x")) + float(li.get("width")),
                         float(rail.get("x")))
        self.assertEqual(float(rail.get("x")) + float(rail.get("width")),
                         float(ld.get("x")))
        self.assertEqual(rail.get("data-join"), "unverified")
        stem = parts["inverted-t-vertical-stem"]
        flange = parts["inverted-t-bottom-flange"]
        self.assertLess(float(flange.get("x")), float(stem.get("x")))
        self.assertGreater(float(flange.get("x")) + float(flange.get("width")),
                           float(stem.get("x")) + float(stem.get("width")))
        self.assertEqual(float(flange.get("y")),
                         float(stem.get("y")) + float(stem.get("height")))
        self.assertNotIn("external-bracket", parts)
        self.assertIn("470 mm", svg)
        self.assertIn("SIN DEFINIR", svg)
        self.assertIn("NO FABRICAR", svg)
        self.assertIn("inverted-t-lower-flange", r["sketch_svg"])
        self.assertFalse(r["can_generate_f7c"])
        self.assertEqual(r["piece_count"], 0)
        for flag in ("fabrication_ready", "cutting_ready",
                     "drilling_ready", "purchase_ready"):
            self.assertFalse(r[flag])

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
