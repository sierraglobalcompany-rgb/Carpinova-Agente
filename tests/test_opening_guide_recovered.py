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
        self.assertIn("W − 2·t", svg)
        self.assertNotIn("470 mm", svg)
        self.assertNotIn("C01 · 500 mm", svg)
        self.assertIn("SIN DEFINIR", svg)
        self.assertIn("NO FABRICAR", svg)
        self.assertIn("inverted-t-lower-flange", r["sketch_svg"])
        self.assertFalse(r["can_generate_f7c"])
        self.assertEqual(r["piece_count"], 0)
        for flag in ("fabrication_ready", "cutting_ready",
                     "drilling_ready", "purchase_ready"):
            self.assertFalse(r[flag])

    def test_g30_only_on_relevant_focus_not_on_unrelated_handle_guides(self):
        all_items = guide_opening_systems({"type": "opening_system_guide"})
        self.assertIn("between_sides_concept_svg", all_items)
        self.assertEqual(all_items["between_sides_concept_svg"],
                         guide_opening_systems({"type": "opening_system_guide",
                                                "focus": "t_rail_concept"})["between_sides_concept_svg"])
        for focus in ("handle", "finger_pull", "profile", "push_to_open"):
            with self.subTest(focus=focus):
                item = guide_opening_systems({"type": "opening_system_guide",
                                              "focus": focus})
                self.assertNotIn("between_sides_concept_svg", item)
                self.assertFalse(item["can_generate_f7c"])

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


    def test_legacy_focus_responses_remain_exact(self):
        """Catch accidental response changes outside the opt-in G39 focus."""
        import hashlib
        import json
        expected = {
            "all": "9202e639fe2f2de4993b5ed6e94802557b1043e88eccad9a5d0bdddbf2a00e59",
            "handle": "c6ff15ebf6520fb56ecc63908dff288bc68c559202fb7458933a150157b7f52c",
            "finger_pull": "cd81b9e8670371e694ed2ee3b3dabc43654465038bf5f88da8deb068e1794c16",
            "profile": "d72c1c8ac07d451aba34ec1fb305b35ee578984c934bb1c7f2e0441c5f034cbe",
            "push_to_open": "1a4f89fdfe4fe65218ae03894aeec4df8de01501571218a2a087bb69465f5135",
            "t_rail_concept": "afc0314f0906788fda56ed823b11aeeb057d6b017b34d4cde0edeae9328c6cb1",
        }
        for focus, digest in expected.items():
            with self.subTest(focus=focus):
                result = guide_opening_systems({"type": "opening_system_guide", "focus": focus})
                encoded = json.dumps(
                    result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), digest)

    def test_g39_focus_is_opt_in_and_keeps_ordinary_outputs_compatible(self):
        focus = "t_rail_ab_review"
        result = guide_opening_systems({"type": "opening_system_guide", "focus": focus})
        rail = guide_opening_systems({"type": "opening_system_guide", "focus": "t_rail_concept"})
        self.assertEqual(result["focus"], focus)
        self.assertEqual(result["sketch_svg"], rail["sketch_svg"])
        self.assertEqual(result["between_sides_concept_svg"], rail["between_sides_concept_svg"])
        self.assertIn("shared_grip_ab_concept_svg", result)
        for old_focus in ("all", "handle", "finger_pull", "profile", "push_to_open", "t_rail_concept"):
            prior = guide_opening_systems({"type": "opening_system_guide", "focus": old_focus})
            self.assertNotIn("shared_grip_ab_concept_svg", prior)

    def test_g39_svg_explains_nominal_edges_and_unverified_routes(self):
        result = guide_opening_systems({
            "type": "opening_system_guide", "focus": "t_rail_ab_review"
        })
        svg = result["shared_grip_ab_concept_svg"]
        root = ET.fromstring(svg)
        self.assertEqual(root.get("role"), "img")
        self.assertEqual(root.get("data-review"), "G39")
        self.assertEqual(root.get("data-verified"), "false")
        self.assertEqual(root.get("data-fabrication-ready"), "false")
        self.assertEqual(root.get("data-piece-count"), "0")
        self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}title"))
        self.assertIsNotNone(root.find("{http://www.w3.org/2000/svg}desc"))
        text = " ".join(" ".join(root.itertext()).split())
        for phrase in (
            "500 mm ancho × 800 mm alto", "15 mm", "A · 137 mm", "B · 137 mm",
            "C · 137 mm", "D · 275 mm", "3 franjas ilustrativas de 28 mm",
            "borde inferior de A", "borde superior de B",
            "G_AB = 28 − S_A,inferior − S_B,superior",
            "separación frontal proyectada", "Solapes sin definir",
            "G_AB > 0 no demuestra acceso", "NO VERIFICADA",
            "Muestra aislada", "sin ubicación ni fijación",
            "MONTANTE ↑", "ALA INFERIOR ↓", "65 × 50 mm",
            "no valida su uso en cajones", "0 PIEZAS", "NO FABRICAR",
        ):
            self.assertIn(phrase, text)
        self.assertIn("3 × 137 + 275 + 3 × 28 + 2 × 15 = 800 mm", text)
        bands = [node for node in root.iter()
                 if node.get("data-kind") == "illustrative-band"]
        self.assertEqual(len(bands), 3)
        self.assertTrue(all(node.get("data-nominal-mm") == "28" for node in bands))
        self.assertTrue(all(node.get("data-physical-part") == "false" for node in bands))
        parts = [node for node in root.iter() if node.get("data-part")]
        for part in ("A", "B", "T"):
            self.assertTrue(any(node.get("data-part") == part for node in parts), part)
        edges = {node.get("id"): node for node in root.iter() if node.get("id")}
        self.assertEqual(edges["edge-A-lower"].get("data-part"), "A")
        self.assertEqual(edges["edge-B-upper"].get("data-part"), "B")
        routes = {node.get("data-route"): node for node in root.iter()
                  if node.get("data-route")}
        self.assertEqual(set(routes), {"A-lower", "B-upper"})
        self.assertEqual(routes["A-lower"].get("data-target"), "edge-A-lower")
        self.assertEqual(routes["B-upper"].get("data-target"), "edge-B-upper")
        for route in routes.values():
            self.assertEqual(route.get("data-verified"), "false")
        t_parts = {node.get("data-role"): node for node in parts
                   if node.get("data-role", "").startswith("t-")}
        stem, flange = t_parts["t-stem"], t_parts["t-lower-flange"]
        self.assertEqual(stem.get("data-verified"), "false")
        self.assertEqual(flange.get("data-verified"), "false")
        self.assertLessEqual(float(stem.get("y")) + float(stem.get("height")),
                             float(flange.get("y")))
        self.assertLess(float(flange.get("x")), float(stem.get("x")))
        self.assertGreater(float(flange.get("x")) + float(flange.get("width")),
                           float(stem.get("x")) + float(stem.get("width")))
        self.assertEqual(root.get("data-join"), "unverified")
        self.assertFalse(any(node.tag.endswith("circle") for node in root.iter()))
        self.assertNotIn("data-action=\"insert-fingers\"", svg)
        self.assertNotIn("H =", text)
        self.assertNotIn("V =", text)

    def test_g39_maestro_route_stays_educational_and_blocked(self):
        from carpinova_agent.maestro import consult_maestro
        response = consult_maestro({
            "action": "modular",
            "module_spec": {
                "type": "opening_system_guide", "focus": "t_rail_ab_review"
            },
        })
        modular = response["modular"]
        self.assertIn("shared_grip_ab_concept_svg", modular)
        self.assertEqual(modular["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(modular["piece_count"], 0)
        self.assertFalse(modular["can_generate_f7c"])
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(modular[flag], False)
            self.assertIs(response[flag], False)

    def test_g39_focus_still_rejects_authorization_and_unknown_inputs(self):
        for spec in (
            {"type": "opening_system_guide", "focus": "not_a_focus"},
            {"type": "opening_system_guide", "focus": "t_rail_ab_review",
             "fabrication_ready": True},
            {"type": "opening_system_guide", "focus": "t_rail_ab_review",
             "authorized_cutting": True},
        ):
            with self.subTest(spec=spec), self.assertRaises(DesignError):
                guide_opening_systems(spec)

if __name__ == "__main__":
    unittest.main()
