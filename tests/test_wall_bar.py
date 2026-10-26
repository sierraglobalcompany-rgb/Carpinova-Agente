"""Focused regression for a wall-mounted-left bar with right-side floor drawer pedestal."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from carpinova_agent.core import DesignError
from carpinova_agent.wall_bar import design_wall_bar
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.wall_bar_sheets import (part_schedule, part_schedule_csv,
                                              part_schedule_svg, wall_bar_orientation_svg,
                                              wall_bar_front_contacts_svg,
                                              wall_bar_isometric_svg)
from xml.etree import ElementTree
from integrations.cad_native import native_boxes

FILE = Path(__file__).resolve().parents[1] / "examples/wall-bar-900-review.json"


def spec():
    return json.loads(FILE.read_text(encoding="utf-8"))["module_spec"]


class WallBarTests(unittest.TestCase):
    def model(self):
        return design_wall_bar(spec())

    def test_21_real_panels_and_cad_agree(self):
        m = self.model()
        cad = cad_exchange(m)
        self.assertEqual(m["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(cad["bounds_xyz_mm"], [900, 900, 460])
        self.assertEqual(len(m["parts"]), 21)
        self.assertEqual(len(cad["boxes"]), 21)
        self.assertEqual({p["piece_id"] for p in m["parts"]},
                         {p["piece_id"] for p in cad["boxes"]})
        self.assertEqual(len(native_boxes(cad)), 21)
        self.assertEqual(validate_exchange(cad), cad)
        for key in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(m[key], False)
        for key in ("fabrication_ready", "cutting_ready", "drilling_ready"):
            self.assertIs(cad[key], False)

    def test_exactly_one_cover_no_left_panel(self):
        boxes = cad_exchange(self.model())["boxes"]
        cover = [b for b in boxes if b["piece_id"] == "BAR-COVER-TOP"]
        self.assertEqual(len(cover), 1)
        self.assertEqual(cover[0]["origin_xyz_mm"], [0, 885, 0])
        self.assertEqual(cover[0]["size_xyz_mm"], [900, 15, 460])
        self.assertTrue(all(b["origin_xyz_mm"][0] >= 600 or b["origin_xyz_mm"][1] >= 885
                            for b in boxes))
        self.assertEqual(len([b for b in boxes if b["role"] == "back_full"]), 1)

    def test_no_double_front_and_drawer_order(self):
        boxes = cad_exchange(self.model())["boxes"]
        self.assertFalse(any(b["role"] == "drawer_front_wall" for b in boxes))
        faces = {b["piece_id"].split("-")[1]: b for b in boxes
                 if b["role"] == "drawer_facade"}
        self.assertEqual(set(faces), {"D1", "D2", "D3"})
        self.assertEqual([faces[k]["size_xyz_mm"][1] for k in ("D1", "D2", "D3")],
                         [180, 180, 477])
        self.assertGreater(faces["D1"]["origin_xyz_mm"][1],
                           faces["D2"]["origin_xyz_mm"][1])
        self.assertGreater(faces["D2"]["origin_xyz_mm"][1],
                           faces["D3"]["origin_xyz_mm"][1])

    def test_panels_and_sheets_share_ids(self):
        m = self.model()
        ids = {b["piece_id"] for b in cad_exchange(m)["boxes"]}
        schedule = part_schedule(m)
        self.assertEqual(ids, {p["piece_id"] for p in schedule})
        self.assertIn("CAJONERA_DERECHA-D1-DRAWER_FACADE", part_schedule_csv(m))
        self.assertIn("BAR-COVER-TOP", part_schedule_svg(m))
        self.assertEqual(sum(p["edge_policy"].startswith("RIGIDO") for p in schedule), 3)

    def test_orientation_A_is_explicit_and_cad_proven(self):
        model = self.model()
        review = model["wall_bar_review"]
        self.assertEqual(review["drawer_opening_face"], "long_side_front")
        self.assertEqual(review["drawer_open_direction"], "negative_Z")
        cad = validate_exchange(cad_exchange(model))
        fronts = [b for b in cad["boxes"] if b["role"] == "drawer_facade"]
        self.assertEqual(len(fronts), 3)
        self.assertTrue(all(b["origin_xyz_mm"][2] == 0 and
                            b["origin_xyz_mm"][0] >= 600 and
                            b["origin_xyz_mm"][0] + b["size_xyz_mm"][0] <= 900 and
                            b["size_xyz_mm"][0] == 296 for b in fronts))
        sheet = wall_bar_orientation_svg(model)
        ElementTree.fromstring(sheet)
        self.assertIn("ORIENTACION A CONFIRMADA", sheet)
        self.assertIn("BAR-COVER-TOP", sheet)
        self.assertIn("CAJONERA_DERECHA-D1-DRAWER_FACADE", sheet)

    def test_physical_interfaces_are_derived_and_not_approved(self):
        m = self.model()
        review = m["wall_bar_review"]
        self.assertEqual(review["drawer_base_clearance_mm"]["D3"], 2)
        self.assertEqual(review["drawer_rear_clearance_mm"]["D3"], 30)
        self.assertEqual(set(review["drawer_front_side_contact"]), {"D1", "D2", "D3"})
        self.assertTrue(all(v == "GEOMETRIC_PLANE_ONLY_NOT_FASTENED"
                            for v in review["drawer_front_side_contact"].values()))
        self.assertTrue(any("D3: holgura vertical inferior nominal de 2 mm"
                            in blocker for blocker in m["blockers"]))
        self.assertEqual(len(m["parts"]), 21)
        self.assertEqual(cad_exchange(m)["geometry_sha256"],
                         "a689b5742709e83ae691ec5c16ec4d81b82ac19ba021ecc62f3d92211eeba58b")
        self.assertFalse(m["fabrication_ready"])
        self.assertFalse(m["cutting_ready"])
        self.assertFalse(m["drilling_ready"])
        self.assertFalse(m["purchase_ready"])

    def test_three_front_contacts_are_complete_but_not_fastened(self):
        m = self.model()
        joints = m["wall_bar_review"]["front_joint_interfaces"]
        self.assertEqual(set(joints), {"D1", "D2", "D3"})
        for did in ("D1", "D2", "D3"):
            one = joints[did]
            self.assertTrue(one["single_external_front"])
            self.assertTrue(one["contact_is_not_a_mechanical_joint"])
            self.assertFalse(one["fixing_holes_specified"])
            self.assertFalse(one["fabrication_ready"])
            self.assertEqual(set(one["surfaces"]),
                             {"left_side", "right_side", "bottom"})
            self.assertTrue(all(v["front_contact_plane_z_mm"] == 15
                                and v["attachment_method"] == "NOT_SPECIFIED"
                                and v["load_capacity_verified"] is False
                                for v in one["surfaces"].values()))
            wall_h = 105 if did in ("D1", "D2") else 375
            self.assertEqual(one["surfaces"]["left_side"]["nominal_contact_patch_xy_mm"],
                             [15, wall_h])
            self.assertEqual(one["surfaces"]["right_side"]["nominal_contact_patch_xy_mm"],
                             [15, wall_h])
            self.assertEqual(one["surfaces"]["bottom"]["nominal_contact_patch_xy_mm"],
                             [244, 15])
        self.assertEqual(m["piece_count"], 21)
        self.assertFalse(m["fabrication_ready"])

    def test_shifted_side_must_not_count_as_a_valid_joint(self):
        from unittest.mock import patch
        from carpinova_agent import wall_bar
        original = wall_bar.design_modular_run

        def misaligned(specification):
            model = original(specification)
            side = next(p for p in model["parts"]
                        if p["piece_id"].endswith("D3-DRAWER_SIDE_LEFT"))
            side["nominal_origin_xyz_mm"][0] -= 30
            return model

        with patch.object(wall_bar, "design_modular_run", misaligned):
            with self.assertRaisesRegex(DesignError, "sin contacto frontal completo"):
                self.model()

    def test_contact_drawing_is_exactly_from_cad_and_explicitly_non_fabricable(self):
        model = self.model()
        sheet = wall_bar_front_contacts_svg(model)
        root = ElementTree.fromstring(sheet)
        self.assertEqual(root.attrib["viewBox"], "0 0 1210 750")
        self.assertIn("VISTA", sheet.upper())
        for did in ("D1", "D2", "D3"):
            self.assertIn(f"CAJONERA_DERECHA-{did}-DRAWER_FACADE", sheet)
        self.assertIn("Sujeción sin definir", sheet)
        self.assertIn(cad_exchange(model)["geometry_sha256"], sheet)
        self.assertNotIn("manufacturing_holes", sheet)
        self.assertEqual(len(model["parts"]), 21)
        self.assertFalse(model["drilling_ready"])
        self.assertFalse(model["cutting_ready"])

    def test_contact_drawing_rejects_missing_or_unapproved_connection(self):
        good = self.model()
        for mode in ("missing_side", "fake_holes"):
            data = copy.deepcopy(good)
            iface = data["wall_bar_review"]["front_joint_interfaces"]["D3"]
            if mode == "missing_side":
                del iface["surfaces"]["left_side"]
            else:
                iface["fixing_holes_specified"] = True
            with self.subTest(mode=mode), self.assertRaises(DesignError):
                wall_bar_front_contacts_svg(data)

    def test_four_edge_pvc_does_not_become_unapproved_cut_dimensions(self):
        model = self.model()
        review = model["wall_bar_review"]["front_edgebanding_review"]
        self.assertEqual(review["status"], "PENDING_FINISHED_VS_RAW_INTERPRETATION")
        self.assertFalse(review["cutting_dimensions_authorized"])
        self.assertEqual(review["nominal_gaps_between_fronts_mm"],
                         {"D3_D2": 2, "D2_D1": 2})
        self.assertEqual(review["gaps_if_nominal_panels_are_cut_raw_then_banded_mm"],
                         {"D3_D2": -2, "D2_D1": -2})
        self.assertEqual(review["nominal_cabinet_side_reveal_each_mm"], 2)
        self.assertEqual(review["side_reveal_if_nominal_is_raw_and_2mm_band_each_side_mm"], 0)
        self.assertEqual(review["fronts"]["D1"]["if_nominal_is_finished_theoretical_raw_width_mm"], 292)
        self.assertEqual(review["fronts"]["D1"]["if_nominal_is_finished_theoretical_raw_height_mm"], 176)
        self.assertEqual(review["fronts"]["D3"]["if_nominal_is_finished_theoretical_raw_height_mm"], 473)
        self.assertTrue(all(p["finished_cut_dimensions_mm"] is None
                            for p in model["parts"]))
        self.assertFalse(model["cutting_ready"])
        self.assertEqual(len(model["parts"]), 21)

    def test_reject_unapproved_front_cantoning(self):
        for edit in ("thickness", "missing_edge"):
            data = spec()
            face = data["cabinet_module"]["drawers"][0]["facade"]
            if edit == "thickness":
                face["edgeband_thickness_mm"] = 1
            else:
                face["edgebanding_edges"].remove("y_min")
            with self.subTest(edit=edit), self.assertRaises(DesignError):
                design_wall_bar(data)

    def test_installation_scope_and_cosmetic_edge_choices_do_not_change_cad(self):
        baseline = self.model()
        old_cad = cad_exchange(baseline)
        options = baseline["wall_bar_review"]["design_choices"]
        self.assertEqual(options["wall_support_presentation"], "installer_defined")
        self.assertEqual(options["top_edge_presentation"], "actual_15mm")
        self.assertTrue(options["wall_attachment_by_installer"])
        self.assertFalse(options["site_wall_material_required_for_design"])
        self.assertFalse(options["support_parts_modeled"])
        self.assertFalse(options["false_thickness_parts_modeled"])
        self.assertTrue(options["options_are_design_notes_only"])
        for wall in ("installer_defined", "wood_cleat", "metal_l_brackets",
                     "metal_support", "other_pending"):
            for edge in ("actual_15mm", "false_thickness_pending", "undecided"):
                data = spec()
                data["design_choices"] = {
                    "wall_support_presentation": wall,
                    "top_edge_presentation": edge,
                }
                result = design_wall_bar(data)
                self.assertEqual(cad_exchange(result), old_cad)
                self.assertEqual(result["piece_count"], 21)
                self.assertFalse(result["fabrication_ready"])
                self.assertFalse(result["purchase_ready"])
                self.assertFalse(result["cutting_ready"])
                self.assertFalse(result["drilling_ready"])
                self.assertEqual(
                    result["wall_bar_review"]["design_choices"][
                        "selected_elements_require_dimensions_and_owner_approval"
                    ], wall != "installer_defined" or edge == "false_thickness_pending")

    def test_maestro_offers_independent_optional_questions(self):
        result = consult_maestro({"action": "modular", "module_spec": spec()},
                                 max_questions=6)
        fields = {q["field"] for q in result["questions"]}
        self.assertIn("module_spec.design_choices.wall_support_presentation", fields)
        self.assertIn("module_spec.design_choices.top_edge_presentation", fields)
        self.assertEqual(result["modular"]["wall_bar_review"]["design_choices"][
            "aesthetic_presentation"], "bicolor_modern_preliminary")
        self.assertFalse(result["fabrication_ready"])
        self.assertEqual(len(result["modular"]["parts"]), 21)
        selected = spec()
        selected["design_choices"] = {
            "wall_support_presentation": "installer_defined",
            "top_edge_presentation": "actual_15mm",
        }
        resolved = consult_maestro({"action": "modular", "module_spec": selected},
                                   max_questions=6)
        self.assertFalse(any("design_choices" in q["field"]
                             for q in resolved["questions"]))

    def test_mounting_options_fail_closed_on_bad_input(self):
        for invalid in (
            {"wall_support_presentation": "blind_invisible_anchor"},
            {"top_edge_presentation": "automatic_40mm_fascia"},
            {"mounting_screw_mm": 50},
            ["wood_cleat"],
        ):
            data = spec()
            data["design_choices"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(DesignError):
                design_wall_bar(data)

    def test_isometric_client_preview_comes_from_all_21_verified_panels(self):
        model = self.model()
        cad = cad_exchange(model)
        sheet = wall_bar_isometric_svg(model)
        root = ElementTree.fromstring(sheet)
        self.assertEqual(root.attrib["viewBox"], "0 0 1460 960")
        ns = "{http://www.w3.org/2000/svg}"
        faces = [e for e in root.iter(ns+"polygon")
                 if e.get("data-piece-id") is not None]
        # 21 CAD boxes remain; only external surfaces belong in this view.
        self.assertEqual(len(cad["boxes"]), 21)
        self.assertEqual(len(faces), 7)
        expected_visible = {"BAR-COVER-TOP",
                            "CAJONERA_DERECHA-RIGHT_SIDE"}
        expected_visible.update(
            b["piece_id"] for b in cad["boxes"] if b["role"] == "drawer_facade")
        self.assertEqual({e.attrib["data-piece-id"] for e in faces},
                         expected_visible)
        self.assertFalse(any("DRAWER_REAR_WALL" in e.attrib["data-piece-id"]
                             for e in faces))
        self.assertFalse(any("DRAWER_BOTTOM" in e.attrib["data-piece-id"]
                             for e in faces))
        self.assertIn(cad["geometry_sha256"], sheet)
        self.assertIn("El extremo CORTO va al muro", sheet)
        self.assertIn("600 mm libres", sheet)
        self.assertIn("NO tablero", sheet)
        for did in ("D1", "D2", "D3"):
            self.assertIn(did, sheet)
        self.assertNotIn("data-hardware-id", sheet)
        self.assertFalse(model["fabrication_ready"])

    def test_isometric_choices_change_notes_not_the_cad_or_parts(self):
        baseline = self.model()
        same_cad = cad_exchange(baseline)
        altered = spec()
        altered["design_choices"] = {
            "wall_support_presentation": "wood_cleat",
            "top_edge_presentation": "false_thickness_pending",
        }
        chosen = design_wall_bar(altered)
        sheet = wall_bar_isometric_svg(chosen)
        ElementTree.fromstring(sheet)
        self.assertIn("Listón bajo cubierta (no modelado)", sheet)
        self.assertIn("Falso espesor: pendiente de medidas", sheet)
        self.assertEqual(cad_exchange(chosen), same_cad)
        self.assertEqual(len(chosen["parts"]), 21)
        self.assertFalse(chosen["drilling_ready"])
        self.assertFalse(chosen["cutting_ready"])

    def test_isometric_never_invents_selected_finishes_or_handle_sku(self):
        undecided = spec()
        undecided.pop("design_choices", None)
        model = design_wall_bar(undecided)
        drawing = wall_bar_isometric_svg(model)
        self.assertEqual(model["wall_bar_review"]["design_choices"][
            "aesthetic_presentation"], "undecided")
        self.assertIn("Apariencia por definir", drawing)
        self.assertIn("Veta productiva sin confirmar", drawing)
        self.assertIn("Tirador indicado; SKU pendiente", drawing)
        self.assertNotIn("Tirador instalado", drawing)
        self.assertEqual(len(model["parts"]), 21)
        self.assertFalse(model["purchase_ready"])
        changed = copy.deepcopy(model)
        for part in changed["parts"]:
            if part["role"] == "drawer_facade":
                part["opening_system"] = "pending"
        without_intent = wall_bar_isometric_svg(changed)
        self.assertIn("Apertura sin herraje verificado", without_intent)
        self.assertNotIn("Tirador indicado; SKU pendiente", without_intent)

    def test_aesthetic_presentation_defaults_undecided_and_fails_closed(self):
        undecided = spec()
        undecided.pop("design_choices", None)
        self.assertEqual(
            design_wall_bar(undecided)["wall_bar_review"]["design_choices"][
                "aesthetic_presentation"], "undecided")
        invalid = spec()
        invalid["design_choices"]["aesthetic_presentation"] = "oak_selected"
        with self.assertRaises(DesignError):
            design_wall_bar(invalid)

    def test_bicolor_preview_preserves_cad_and_has_five_ids_seven_faces(self):
        proposal = design_wall_bar(spec())
        undecided_spec = spec()
        undecided_spec["design_choices"]["aesthetic_presentation"] = "undecided"
        undecided = design_wall_bar(undecided_spec)
        cad = validate_exchange(cad_exchange(proposal))
        self.assertEqual(cad_exchange(proposal), cad_exchange(undecided))
        self.assertEqual(cad["geometry_sha256"],
                         "a689b5742709e83ae691ec5c16ec4d81b82ac19ba021ecc62f3d92211eeba58b")
        self.assertEqual(cad["bounds_xyz_mm"], [900, 900, 460])
        self.assertEqual(len(cad["boxes"]), 21)
        self.assertEqual(len({b["piece_id"] for b in cad["boxes"]}), 21)
        self.assertEqual(proposal["piece_count"], 21)
        self.assertEqual(proposal["status"], "DRAFT_NOT_FOR_CUTTING")
        design_choices = proposal["wall_bar_review"]["design_choices"]
        self.assertEqual(design_choices["aesthetic_presentation"],
                         "bicolor_modern_preliminary")
        self.assertTrue(design_choices["aesthetic_is_illustrative_only"])
        cover = next(p for p in proposal["parts"]
                     if p["piece_id"] == "BAR-COVER-TOP")
        self.assertEqual(cover["grain_axis"], "UNCONFIRMED")
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertIs(proposal[flag], False)

        drawing = wall_bar_isometric_svg(proposal)
        root = ElementTree.fromstring(drawing)
        ns = "{http://www.w3.org/2000/svg}"
        faces = [e for e in root.iter(ns + "polygon")
                 if e.get("data-piece-id") is not None]
        self.assertEqual(len(faces), 7)
        expected_ids = {"BAR-COVER-TOP", "CAJONERA_DERECHA-RIGHT_SIDE"}
        expected_ids.update(b["piece_id"] for b in cad["boxes"]
                            if b["role"] == "drawer_facade")
        self.assertEqual(len(expected_ids), 5)
        self.assertEqual({e.get("data-piece-id") for e in faces}, expected_ids)
        fills = {(e.get("data-piece-id"), e.get("data-face")): e.get("fill")
                 for e in faces}
        self.assertEqual(fills[("BAR-COVER-TOP", "top")], "#e8d2a8")
        self.assertEqual(fills[("CAJONERA_DERECHA-RIGHT_SIDE", "right")], "#f2f3f0")
        for piece_id in expected_ids - {"BAR-COVER-TOP", "CAJONERA_DERECHA-RIGHT_SIDE"}:
            self.assertEqual(fills[(piece_id, "front")], "#f2f3f0")
        grain = [e for e in root.iter(ns + "path")
                 if e.get("data-concept") == "decorative-grain"]
        self.assertEqual(len(grain), 5)
        for line in grain:
            self.assertEqual(line.get("data-axis"), "X")
            x1, y1, x2, y2 = map(
                float, line.get("d").replace("M", "").replace("L", "").split())
            self.assertGreater(x2, x1)
            self.assertAlmostEqual((y2 - y1) / (x2 - x1), 0.12 / 0.76, places=2)
        legend = [e for e in root.iter(ns + "g")
                  if e.get("data-concept") == "handle-legend"]
        self.assertEqual(len(legend), 1)
        self.assertFalse(any(e.get("data-hardware-id") for e in root.iter()))
        self.assertTrue(all(e.get("data-piece-id") is None for e in legend[0].iter()))
        text = " ".join(root.itertext())
        self.assertIn("5 IDs CAD · 7 caras exteriores", text)
        self.assertIn("Bicolor preliminar · no acabado aprobado", text)
        self.assertIn("Cubierta roble claro · lateral/frentes blanco mate", text)
        self.assertIn("Tirador recto negro · concepto", text)
        self.assertIn("Sin herraje, SKU, cantidad, posición ni taladros", text)
        self.assertIn(cad["geometry_sha256"], text)

    def test_no_mutation(self):
        request = spec()
        before = copy.deepcopy(request)
        design_wall_bar(request)
        self.assertEqual(request, before)

    def test_wrong_configuration_fails_closed(self):
        for scenario in ("wall", "orientation_B", "orientation_missing", "feet", "cabinet", "front", "span", "extra"):
            request = spec()
            if scenario == "wall":
                request["wall_side"] = "right"
            elif scenario == "orientation_B":
                request["drawer_opening_face"] = "short_free_end"
            elif scenario == "orientation_missing":
                del request["drawer_opening_face"]
            elif scenario == "feet":
                request["feet_height_mm"] = 80
            elif scenario == "cabinet":
                request["cabinet_module"]["width_mm"] = 900
            elif scenario == "front":
                request["cabinet_module"]["drawers"][0]["front_construction"] = "separate"
            elif scenario == "span":
                request["free_span_mm"] = 900
            else:
                request["extra_phantom_left_panel"] = True
            with self.subTest(scenario=scenario), self.assertRaises(DesignError):
                design_wall_bar(request)


if __name__ == "__main__":
    unittest.main()
