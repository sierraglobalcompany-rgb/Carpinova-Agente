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

    def test_24_real_panels_and_cad_agree(self):
        m = self.model()
        cad = cad_exchange(m)
        self.assertEqual(m["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(cad["bounds_xyz_mm"], [900, 900, 460])
        self.assertEqual(len(m["parts"]), 24)
        self.assertEqual(len(cad["boxes"]), 24)
        self.assertEqual({p["piece_id"] for p in m["parts"]},
                         {p["piece_id"] for p in cad["boxes"]})
        self.assertEqual(len(native_boxes(cad)), 24)
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
        self.assertEqual(sum(b["role"] == "drawer_front_wall" for b in boxes), 3)
        for did in ("D1", "D2", "D3"):
            roles = {b["role"] for b in boxes
                     if f"CAJONERA_DERECHA-{did}-" in b["piece_id"]}
            self.assertEqual(roles, {
                "drawer_side_left", "drawer_side_right", "drawer_front_wall",
                "drawer_rear_wall", "drawer_bottom", "drawer_facade",
            })
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
        self.assertEqual(set(review["drawer_front_contact"]), {"D1", "D2", "D3"})
        self.assertTrue(all(v == "GEOMETRIC_PLANES_ONLY_NOT_FASTENED"
                            for v in review["drawer_front_contact"].values()))
        self.assertTrue(any("D3: holgura vertical inferior nominal de 2 mm"
                            in blocker for blocker in m["blockers"]))
        self.assertEqual(len(m["parts"]), 24)
        self.assertEqual(cad_exchange(m)["geometry_sha256"],
                         "a81504b9e04745ef746b9a7d249fc6e805524260dca954444056fb1b02a5bd8a")
        self.assertFalse(m["fabrication_ready"])
        self.assertFalse(m["cutting_ready"])
        self.assertFalse(m["drilling_ready"])
        self.assertFalse(m["purchase_ready"])

    def test_facade_contacts_front_wall_and_box_edges_but_is_not_fastened(self):
        m = self.model()
        joints = m["wall_bar_review"]["front_joint_interfaces"]
        self.assertEqual(set(joints), {"D1", "D2", "D3"})
        for did in ("D1", "D2", "D3"):
            one = joints[did]
            self.assertEqual(one["front_construction"], "separate")
            self.assertEqual(one["front_style"], "overlay")
            self.assertIs(one["decorative_front_is_structural"], False)
            self.assertIn("DRAWER_FRONT_WALL", one["box_front_wall_piece_id"])
            self.assertTrue(one["contact_is_not_a_mechanical_joint"])
            self.assertFalse(one["fixing_holes_specified"])
            self.assertFalse(one["fabrication_ready"])
            self.assertEqual(set(one["surfaces"]),
                             {"front_wall", "left_side", "right_side", "bottom"})
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
            front_wall = next(p for p in m["parts"]
                              if p["piece_id"] == one["box_front_wall_piece_id"])
            self.assertEqual(one["surfaces"]["front_wall"][
                "nominal_contact_patch_xy_mm"],
                [front_wall["nominal_face_x_mm"], front_wall["nominal_face_y_mm"]])
        self.assertEqual(m["piece_count"], 24)
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
        self.assertIn("montaje sin definir", sheet)
        self.assertIn(cad_exchange(model)["geometry_sha256"], sheet)
        self.assertNotIn("manufacturing_holes", sheet)
        self.assertEqual(len(model["parts"]), 24)
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
        self.assertEqual(len(model["parts"]), 24)

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
                self.assertEqual(result["piece_count"], 24)
                self.assertFalse(result["fabrication_ready"])
                self.assertFalse(result["purchase_ready"])
                self.assertFalse(result["cutting_ready"])
                self.assertFalse(result["drilling_ready"])
                self.assertEqual(
                    result["wall_bar_review"]["design_choices"][
                        "selected_elements_require_dimensions_and_owner_approval"
                    ], wall != "installer_defined" or edge == "false_thickness_pending")

    def test_maestro_uses_safe_defaults_without_optional_question_loop(self):
        draft = consult_maestro({"action": "modular", "module_spec": spec()},
                               max_questions=6)
        fields = {q["field"] for q in draft["questions"]}
        self.assertFalse(any("design_choices" in field or field.endswith(".finish")
                             for field in fields))
        choices = draft["modular"]["wall_bar_review"]["design_choices"]
        self.assertEqual(choices["wall_support_presentation"], "installer_defined")
        self.assertEqual(choices["top_edge_presentation"], "actual_15mm")
        self.assertEqual(choices["aesthetic_presentation"], "bicolor_modern_preliminary")
        self.assertEqual(len(draft["modular"]["parts"]), 24)
        for key in ("fabrication_ready", "cutting_ready", "drilling_ready",
                    "purchase_ready"):
            self.assertFalse(draft[key])

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

    def test_isometric_client_preview_comes_from_all_24_verified_panels(self):
        model = self.model()
        cad = cad_exchange(model)
        sheet = wall_bar_isometric_svg(model)
        root = ElementTree.fromstring(sheet)
        self.assertEqual(root.attrib["viewBox"], "0 0 1460 960")
        ns = "{http://www.w3.org/2000/svg}"
        faces = [e for e in root.iter(ns+"polygon")
                 if e.get("data-piece-id") is not None]
        # All 24 CAD boxes remain; only external surfaces belong in this view.
        self.assertEqual(len(cad["boxes"]), 24)
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
        self.assertEqual(len(chosen["parts"]), 24)
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
        self.assertEqual(len(model["parts"]), 24)
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
                         "a81504b9e04745ef746b9a7d249fc6e805524260dca954444056fb1b02a5bd8a")
        self.assertEqual(cad["bounds_xyz_mm"], [900, 900, 460])
        self.assertEqual(len(cad["boxes"]), 24)
        self.assertEqual(len({b["piece_id"] for b in cad["boxes"]}), 24)
        self.assertEqual(proposal["piece_count"], 24)
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
                request["cabinet_module"]["drawers"][0]["front_construction"] = "integrated_overlay"
            elif scenario == "span":
                request["free_span_mm"] = 900
            else:
                request["extra_phantom_left_panel"] = True
            with self.subTest(scenario=scenario), self.assertRaises(DesignError):
                design_wall_bar(request)


    def test_review_package_gives_three_drawer_sheets_24_traceable_codes(self):
        from carpinova_agent.wall_bar_delivery import reference_rows, review_files
        from xml.etree import ElementTree
        model = self.model()
        rows = reference_rows(model)
        files = review_files(model)
        self.assertEqual(len(rows), 24)
        self.assertEqual(len({r["referencia"] for r in rows}), 24)
        self.assertEqual(len({r["id_cad"] for r in rows}), 24)
        self.assertEqual(len(files), 5)
        self.assertIn("E01", files["CN-BAR-001-referencias.csv"])
        self.assertIn("C06", files["CN-BAR-001-referencias.csv"])
        for letter in "ABC":
            sheet = files[f"CN-BAR-001-cajon-{letter}.svg"]
            root = ElementTree.fromstring(sheet)
            self.assertEqual(
                len([item for item in root.iter()
                if item.get("data-piece-id") is not None]), 6)
            self.assertIn("NO CORTAR", sheet)
            for n in ("01", "02", "03", "04", "05", "06"):
                self.assertIn(letter + n, sheet)
            self.assertIn(cad_exchange(model)["geometry_sha256"], sheet)
        self.assertIn("instalador", files["CN-BAR-001-guia-de-armado-REVISION.md"])
        self.assertEqual(len(model["parts"]), 24)
        self.assertFalse(model["fabrication_ready"])
        self.assertFalse(model["cutting_ready"])
        self.assertFalse(model["drilling_ready"])
        self.assertFalse(model["purchase_ready"])


    def test_review_booklet_has_seven_traceable_svg_pages(self):
        import csv
        from io import StringIO
        from carpinova_agent.wall_bar_delivery import (
            reference_rows, review_booklet_svgs, review_files,
        )
        from xml.etree import ElementTree
        model = self.model()
        pages = review_booklet_svgs(model)
        files = review_files(model)
        rows = reference_rows(model)
        self.assertEqual(len(pages), 7)
        sha = cad_exchange(model)["geometry_sha256"]
        for page in pages:
            ElementTree.fromstring(page)
            self.assertIn(sha, page)
        self.assertIn("A = superior (CAD D1)", pages[1])
        self.assertIn("B = intermedio (CAD D2)", pages[1])
        self.assertIn("C = inferior (CAD D3)", pages[1])
        self.assertIn("E01 cubierta", pages[0])
        for letter in "ABC":
            self.assertIn(f'>{letter}</text>', pages[0])
            self.assertIn(f'>{letter}</text>', pages[1])

        # Every visible BOM card maps back to the same reference, dimensions,
        # and CAD ID used by the CSV and CADExchange.
        bom_root = ElementTree.fromstring(pages[5])
        bom_viewbox = list(map(float, bom_root.get("viewBox").split()))
        _, _, bom_width, bom_height = bom_viewbox
        cards = [item for item in bom_root.iter()
                 if item.tag.endswith("rect") and item.get("data-reference")]
        self.assertEqual(len(cards), 24)
        self.assertEqual({item.get("data-reference") for item in cards},
                         {row["referencia"] for row in rows})
        csv_rows = list(csv.DictReader(StringIO(
            files["CN-BAR-001-referencias.csv"])))
        self.assertEqual(len(csv_rows), 24)
        self.assertEqual(len({row["referencia"] for row in csv_rows}), 24)
        self.assertEqual(len({row["id_cad"] for row in csv_rows}), 24)
        text_by_ref = {}
        for item in bom_root.iter():
            if item.tag.endswith("text") and item.get("data-bom-field"):
                text_by_ref.setdefault(item.get("data-reference"), {})[
                    item.get("data-bom-field")
                ] = "".join(item.itertext())
        csv_by_ref = {row["referencia"]: row for row in csv_rows}
        rows_by_ref = {row["referencia"]: row for row in rows}
        for card in cards:
            ref = card.get("data-reference")
            row = rows_by_ref[ref]
            csv_row = csv_by_ref[ref]
            x, y = float(card.get("x")), float(card.get("y"))
            width, height = float(card.get("width")), float(card.get("height"))
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 130)
            self.assertLessEqual(x + width, bom_width)
            self.assertLessEqual(y + height, bom_height - 60)
            self.assertEqual(card.get("data-cad-id"), row["id_cad"])
            self.assertEqual(card.get("data-nominal-size"),
                             f'{row["cara_a_mm"]} × {row["cara_b_mm"]} '
                             f'× {row["espesor_mm"]} mm')
            self.assertEqual(card.get("data-cad-id"), csv_row["id_cad"])
            fields = text_by_ref[ref]
            self.assertEqual(fields["label"],
                             f'{row["referencia"]} · {row["descripcion"]}')
            self.assertEqual(fields["size"], card.get("data-nominal-size"))
            self.assertEqual(fields["cad-id"], row["id_cad"])
            label_node = next(item for item in bom_root.iter()
                              if item.tag.endswith("text")
                              and item.get("data-reference") == ref
                              and item.get("data-bom-field") == "label")
            size_node = next(item for item in bom_root.iter()
                             if item.tag.endswith("text")
                             and item.get("data-reference") == ref
                             and item.get("data-bom-field") == "size")
            id_node = next(item for item in bom_root.iter()
                           if item.tag.endswith("text")
                           and item.get("data-reference") == ref
                           and item.get("data-bom-field") == "cad-id")
            label_width = len(fields["label"]) * float(label_node.get("font-size")) * .62
            size_width = len(fields["size"]) * float(size_node.get("font-size")) * .62
            id_width = len(fields["cad-id"]) * float(id_node.get("font-size")) * .62
            self.assertLessEqual(float(label_node.get("x")) + label_width,
                                 float(size_node.get("x")) - size_width - 8)
            self.assertLessEqual(float(id_node.get("x")) + id_width,
                                 x + width - 8)
        self.assertTrue({"C05", "C06"}.issubset(text_by_ref))

        # Recover every source step from the rendered SVG tspans. This checks
        # wrapping, card spacing and page bounds rather than XML validity alone.
        guide_root = ElementTree.fromstring(pages[6])
        guide_viewbox = list(map(float, guide_root.get("viewBox").split()))
        _, _, guide_width, guide_height = guide_viewbox
        source_steps = [line.split(". ", 1)[1]
                        for line in files[
                            "CN-BAR-001-guia-de-armado-REVISION.md"
                        ].splitlines()
                        if len(line) > 3 and line[0] in "123456"
                        and line[1:3] == ". "]
        self.assertEqual(len(source_steps), 6)
        guide_cards = {item.get("data-guide-step"): item
                       for item in guide_root.iter()
                       if item.tag.endswith("rect")
                       and item.get("data-guide-step")}
        guide_text = {item.get("data-guide-step"): item
                      for item in guide_root.iter()
                      if item.tag.endswith("text")
                      and item.get("data-guide-step")}
        self.assertEqual(set(guide_cards), {f"{n:02d}" for n in range(1, 7)})
        self.assertEqual(set(guide_text), set(guide_cards))
        for index, step in enumerate(source_steps, start=1):
            key = f"{index:02d}"
            card = guide_cards[key]
            text_node = guide_text[key]
            tspans = [item for item in text_node
                      if item.tag.endswith("tspan")]
            rendered_lines = [item.text or "" for item in tspans]
            self.assertGreaterEqual(len(rendered_lines), 1)
            self.assertEqual(" ".join(rendered_lines), step)
            self.assertTrue(all(line == line.strip() for line in rendered_lines))
            card_x, card_y = float(card.get("x")), float(card.get("y"))
            card_w, card_h = float(card.get("width")), float(card.get("height"))
            self.assertGreaterEqual(card_x, 0)
            self.assertGreaterEqual(card_y, 130)
            self.assertLessEqual(card_x + card_w, guide_width)
            self.assertLessEqual(card_y + card_h, 950)
            line_widths = [len(line) * float(text_node.get("font-size")) * .65
                           for line in rendered_lines]
            self.assertTrue(all(width <= card_w - 180 for width in line_widths))
            last_baseline = (float(text_node.get("y")) +
                             sum(float(item.get("dy", "0")) for item in tspans))
            self.assertLessEqual(last_baseline + 6, card_y + card_h)
        self.assertIn("NO FABRICAR", pages[6])
        self.assertIn("El apoyo mural y su seguridad los verifica el instalador en obra.",
                      pages[6])
        self.assertFalse(model["fabrication_ready"])

    def test_review_booklet_wraps_arbitrarily_long_guide_steps(self):
        from unittest.mock import patch
        from carpinova_agent.wall_bar_delivery import (
            review_booklet_svgs, review_files,
        )
        from xml.etree import ElementTree
        model = self.model()
        files = review_files(model)
        long_step = ("Secuencia conceptual: "
                     + ("palabra larga y verificable " * 12).strip())
        guide = files["CN-BAR-001-guia-de-armado-REVISION.md"]
        guide = guide.replace(
            "3. Secuencia conceptual: caja cerrada de cuatro paredes y fondo; "
            "validar la corredera exacta y presentarla nivelada; solo después "
            "montar y ajustar la fachada decorativa separada. La fijación aún "
            "no está especificada.",
            "3. " + long_step,
        )
        files["CN-BAR-001-guia-de-armado-REVISION.md"] = guide
        with patch("carpinova_agent.wall_bar_delivery.review_files",
                   return_value=files):
            pages = review_booklet_svgs(model)
        root = ElementTree.fromstring(pages[6])
        step = next(item for item in root.iter()
                    if item.tag.endswith("text")
                    and item.get("data-guide-step") == "03")
        lines = [item.text or "" for item in step
                 if item.tag.endswith("tspan")]
        self.assertGreater(len(lines), 2)
        self.assertEqual(" ".join(lines), long_step)
        self.assertTrue(all(len(line) <= 100 for line in lines))


if __name__ == "__main__":
    unittest.main()
