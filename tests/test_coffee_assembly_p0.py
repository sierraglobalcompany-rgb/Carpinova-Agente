"""Focused review-only contract for the owner's coffee cabinet concept."""
from __future__ import annotations

import csv
from copy import deepcopy
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.core import DesignError
from carpinova_agent.drawing_sheet import three_views_svg
from carpinova_agent.modular import design_modular_run
from carpinova_agent.modular_outputs import modular_bom_csv, modular_front_svg
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.pilot_cli import PilotError, pilot_review, verify_pilot_bundle


def coffee_spec() -> dict:
    return {
        "type": "modular_run",
        "application": "kitchen",
        "width_mm": 890,
        "height_mm": 770,
        "depth_mm": 600,
        "installation": "freestanding",
        "modules": [{
            "module_id": "COFFEE",
            "width_mm": 890,
            "panel_thickness_mm": 15,
            "material_id": "MELAMINE_15",
            "construction": "sides_full",
            "fronts": {
                "style": "overlay", "leaf_count": 2,
                "material_id": "MELAMINE_15", "thickness_mm": 15,
                "hinge_sides": ["left", "right"],
                "left_reveal_mm": 3, "right_reveal_mm": 3,
                "top_reveal_mm": 3, "bottom_reveal_mm": 3,
                "center_gap_mm": 4,
            },
            "back": "pending",
            "support": "floor",
            "support_concept": {
                "style": "legs", "support_height_mm": 100,
                "overall_height_mm": 900,
            },
            "horizontal_divider": {
                "material_id": "MELAMINE_15", "thickness_mm": 15,
                "position_from_clear_bottom_mm": 370,
                "depth_mm": 600, "depth_from_front_mm": 0,
            },
            "countertop": {
                "material_id": "MDF_RH", "thickness_mm": 30,
                "width_mm": 940, "depth_mm": 650,
                "left_overhang_mm": 25, "right_overhang_mm": 25,
                "front_overhang_mm": 50, "rear_overhang_mm": 0,
                "finish_note": "Acabado impermeable indicado por el propietario; ficha pendiente",
            },
            "upper_support": {
                "style": "coffee_three_upright_ties",
                "tie_height_mm": 80,
                "tie_height_status": "REVIEW_HEIGHT_HYPOTHESIS_ONLY",
            },
        }],
    }


def rehash_exchange(exchange: dict) -> None:
    payload = {key: value for key, value in exchange.items()
               if key != "geometry_sha256"}
    exchange["geometry_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def strictly_intersects(a: dict, b: dict) -> bool:
    return all(
        max(a["origin_xyz_mm"][axis], b["origin_xyz_mm"][axis])
        < min(a["origin_xyz_mm"][axis] + a["size_xyz_mm"][axis],
              b["origin_xyz_mm"][axis] + b["size_xyz_mm"][axis])
        for axis in range(3)
    )


def shares_nominal_face(a: dict, b: dict) -> bool:
    for axis in range(3):
        a_end = a["origin_xyz_mm"][axis] + a["size_xyz_mm"][axis]
        b_end = b["origin_xyz_mm"][axis] + b["size_xyz_mm"][axis]
        if a_end == b["origin_xyz_mm"][axis] or b_end == a["origin_xyz_mm"][axis]:
            if all(
                max(a["origin_xyz_mm"][other], b["origin_xyz_mm"][other])
                < min(a["origin_xyz_mm"][other] + a["size_xyz_mm"][other],
                      b["origin_xyz_mm"][other] + b["size_xyz_mm"][other])
                for other in range(3) if other != axis
            ):
                return True
    return False


class CoffeeAssemblyP0Tests(unittest.TestCase):
    def test_coffee_front_svg_notes_wrap_without_overlap(self):
        model = design_modular_run(coffee_spec())
        front = modular_front_svg(model)
        root = ET.fromstring(front)
        text = " ".join(" ".join(root.itertext()).casefold().split())

        self.assertNotIn("bajo cajonera", text)
        self.assertNotIn("40 mm conceptuales", text)
        self.assertNotIn("apoyos conceptuales en cad", text)
        self.assertIn("review_height_hypothesis_only; hypothesis_preview_only", text)
        bottom_notes = [item for item in root.iter()
                        if item.tag.endswith("text")
                        and item.get("class") == "note"
                        and int(item.get("y", "0")) >= 600]
        self.assertEqual(sorted((item.get("y") for item in bottom_notes),
                                key=int),
                         ["675", "715", "740", "765"])
        self.assertTrue(any(child.tag.endswith("tspan")
                            and child.get("dy") == "18"
                            for item in bottom_notes for child in item))

    def test_coffee_front_svg_excludes_bar_specific_leg_label(self):
        model = design_modular_run(coffee_spec())
        front = modular_front_svg(model)
        root = ET.fromstring(front)
        text = " ".join(root.itertext()).casefold()

        self.assertNotIn("bajo cajonera", text)
        self.assertNotIn("40 mm conceptuales", text)
        self.assertNotIn("apoyos conceptuales en cad", text)

    def test_owner_geometry_is_ten_cad_volumes_with_three_upright_ties(self):
        model = design_modular_run(coffee_spec())
        self.assertEqual(model["dimensions_mm"],
                         {"width": 940, "height": 900, "depth": 650})
        self.assertEqual(model["carcass_dimensions_mm"],
                         {"width": 890, "height": 770, "depth": 600})
        self.assertEqual(model["piece_count"], 10)
        self.assertEqual(len({p["piece_id"] for p in model["parts"]}), 10)
        by_role = {p["role"]: p for p in model["parts"]}
        self.assertEqual(set(by_role), {
            "left_side", "right_side", "bottom", "upper_front_tie",
            "upper_rear_tie", "lower_rear_tie", "countertop",
            "shelf_horizontal", "front_left", "front_right",
        })
        self.assertNotIn("top", by_role)
        self.assertEqual(by_role["countertop"]["nominal_origin_xyz_mm"], [0, 870, 0])
        self.assertEqual(by_role["countertop"]["nominal_face_x_mm"], 940)
        self.assertEqual(by_role["countertop"]["nominal_face_y_mm"], 650)
        self.assertEqual(by_role["countertop"]["thickness_mm"], 30)
        self.assertEqual(by_role["shelf_horizontal"]["nominal_origin_xyz_mm"],
                         [40, 485, 50])
        self.assertEqual(by_role["shelf_horizontal"]["nominal_face_x_mm"], 860)
        self.assertEqual(by_role["shelf_horizontal"]["nominal_face_y_mm"], 600)
        self.assertEqual(by_role["shelf_horizontal"]["thickness_mm"], 15)
        for role, origin in (
            ("upper_front_tie", [40, 790, 50]),
            ("upper_rear_tie", [40, 790, 635]),
            ("lower_rear_tie", [40, 115, 635]),
        ):
            piece = by_role[role]
            self.assertEqual(piece["nominal_origin_xyz_mm"], origin)
            self.assertEqual(piece["face_plane"], "XY")
            self.assertEqual(piece["nominal_face_x_mm"], 860)
            self.assertEqual(piece["nominal_face_y_mm"], 80)
            self.assertEqual(piece["thickness_mm"], 15)
            self.assertIsNone(piece["finished_cut_dimensions_mm"])
        for role, origin in (
            ("front_left", [28, 103, 35]),
            ("front_right", [472, 103, 35]),
        ):
            self.assertEqual(by_role[role]["nominal_origin_xyz_mm"], origin)
            self.assertEqual(by_role[role]["nominal_face_x_mm"], 440)
            self.assertEqual(by_role[role]["nominal_face_y_mm"], 764)
            self.assertEqual(by_role[role]["thickness_mm"], 15)
        self.assertEqual(model["upper_support_review"]["tie_height_status"],
                         "REVIEW_HEIGHT_HYPOTHESIS_ONLY")
        self.assertEqual(model["assembly_review"]["review_status"],
                         "HYPOTHESIS_PREVIEW_ONLY")
        self.assertEqual(model["assembly_review"]["wall_vertical_load_role"],
                         "NONE_OWNER_CONFIRMED")
        self.assertEqual(model["assembly_review"]["support_height_mm"], 100)
        self.assertEqual(model["modules"][0]["review_hypotheses"]["front_style"],
                         "overlay")
        self.assertEqual(model["modules"][0]["review_hypotheses"]["front_leaf_count"], 2)
        self.assertNotIn("support_leg_concept", {p["role"] for p in model["parts"]})

    def test_cad_is_collision_free_and_all_manufacturing_flags_stay_false(self):
        model = design_modular_run(coffee_spec())
        cad = cad_exchange(model)
        self.assertEqual(cad["bounds_xyz_mm"], [940, 900, 650])
        self.assertEqual(len(cad["boxes"]), 10)
        for i, first in enumerate(cad["boxes"]):
            for second in cad["boxes"][i + 1:]:
                self.assertFalse(strictly_intersects(first, second),
                                 (first["piece_id"], second["piece_id"]))
        for box in cad["boxes"]:
            self.assertTrue(
                any(shares_nominal_face(box, other)
                    for other in cad["boxes"] if other is not box),
                f"Pieza sin contacto nominal: {box['piece_id']}",
            )
        for obj in (model, cad):
            self.assertFalse(obj["fabrication_ready"])
            self.assertFalse(obj["cutting_ready"])
            self.assertFalse(obj["drilling_ready"])
        self.assertFalse(model["purchase_ready"])
        self.assertEqual(cad["manufacturing_holes"], [])
        self.assertNotIn("drilling_coordinates", cad)
        self.assertEqual(cad["upper_support_review"]["countertop_wall_vertical_support"],
                         "EXCLUDED_BY_OWNER")

    def test_legacy_modular_cabinet_keeps_its_full_top_without_coffee_opt_in(self):
        spec = {
            "type": "modular_run", "application": "kitchen",
            "width_mm": 890, "height_mm": 770, "depth_mm": 600,
            "installation": "freestanding", "modules": [{
                "module_id": "PLAIN", "width_mm": 890,
                "panel_thickness_mm": 15, "material_id": "MELAMINE_15",
                "construction": "sides_full", "fronts": "none",
                "back": "none", "support": "floor",
            }],
        }
        model = design_modular_run(spec)
        self.assertEqual([p["role"] for p in model["parts"]].count("top"), 1)
        self.assertNotIn("upper_support_review", model)
        self.assertNotIn("lower_rear_tie", {p["role"] for p in model["parts"]})
        self.assertEqual(model["piece_count"], 4)

    def test_old_flat_two_tie_request_and_approved_height_are_rejected(self):
        spec = coffee_spec()
        spec["modules"][0]["upper_support"] = {
            "style": "front_rear_ties", "tie_width_mm": 70,
            "tie_width_status": "VISUAL_PROPOSAL_ONLY",
        }
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_owner_envelope_overhang_leg_and_front_contract_reject_drift(self):
        mutations = (
            ("left overhang changed", lambda s:
             s["modules"][0]["countertop"].__setitem__("left_overhang_mm", 30)),
            ("front overhang changed", lambda s:
             s["modules"][0]["countertop"].__setitem__("front_overhang_mm", 51)),
            ("countertop envelope changed", lambda s:
             s["modules"][0]["countertop"].__setitem__("width_mm", 941)),
            ("countertop depth changed", lambda s:
             s["modules"][0]["countertop"].__setitem__("depth_mm", 651)),
            ("carcass depth changed", lambda s:
             s.__setitem__("depth_mm", 601)),
            ("overall height changed", lambda s:
             s.__setitem__("height_mm", 901)),
            ("cabinet width changed", lambda s:
             (s.__setitem__("width_mm", 891),
              s["modules"][0].__setitem__("width_mm", 891))),
            ("leg height changed", lambda s:
             s["modules"][0]["support_concept"].__setitem__("support_height_mm", 110)),
            ("inset doors", lambda s:
             s["modules"][0]["fronts"].__setitem__("style", "inset")),
            ("reversed hinges", lambda s:
             s["modules"][0]["fronts"].__setitem__("hinge_sides", ["right", "left"])),
            ("duplicated hinges", lambda s:
             s["modules"][0]["fronts"].__setitem__("hinge_sides", ["left", "left"])),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                spec = coffee_spec()
                mutate(spec)
                with self.assertRaises(DesignError):
                    design_modular_run(spec)

    def test_review_statuses_remain_hypotheses_and_wall_is_not_load_bearing(self):
        model = design_modular_run(coffee_spec())
        module = model["modules"][0]
        self.assertEqual(module["review_hypotheses"]["status"],
                         "HYPOTHESIS_PREVIEW_ONLY")
        self.assertEqual(module["review_hypotheses"]["front_center_gap_mm"], 4)
        self.assertEqual(model["upper_support_review"]["tie_height_status"],
                         "REVIEW_HEIGHT_HYPOTHESIS_ONLY")
        self.assertEqual(model["assembly_review"]["wall_vertical_load_role"],
                         "NONE_OWNER_CONFIRMED")
        self.assertEqual(model["assembly_review"]["front_gaps_status"],
                         "HYPOTHESIS_PREVIEW_ONLY")
        spec = coffee_spec()
        spec["modules"][0]["upper_support"]["tie_height_status"] = "OWNER_APPROVED"
        with self.assertRaises(DesignError):
            design_modular_run(spec)

    def test_cad_validator_rejects_missing_or_flat_tie_with_recomputed_hash(self):
        valid = cad_exchange(design_modular_run(coffee_spec()))
        missing = json.loads(json.dumps(valid))
        missing["boxes"] = [b for b in missing["boxes"]
                             if b["role"] != "lower_rear_tie"]
        missing["piece_count"] = len(missing["boxes"])
        rehash_exchange(missing)
        with self.assertRaises(DesignError):
            validate_exchange(missing)
        flat = json.loads(json.dumps(valid))
        box = next(b for b in flat["boxes"] if b["role"] == "upper_front_tie")
        box["origin_xyz_mm"] = [40, 855, 50]
        box["size_xyz_mm"] = [860, 15, 80]
        rehash_exchange(flat)
        with self.assertRaises(DesignError):
            validate_exchange(flat)

    def test_cad_validator_rejects_wall_load_claim_after_rehash(self):
        cad = cad_exchange(design_modular_run(coffee_spec()))
        cad["upper_support_review"]["wall_vertical_load_role"] = "SUPPORTS_COUNTERTOP"
        rehash_exchange(cad)
        with self.assertRaises(DesignError):
            validate_exchange(cad)

    def test_cad_validator_rejects_physical_permission_or_hole_mutations(self):
        valid = cad_exchange(design_modular_run(coffee_spec()))
        for field in ("fabrication_ready", "cutting_ready", "drilling_ready"):
            with self.subTest(field=field):
                changed = deepcopy(valid)
                changed[field] = True
                rehash_exchange(changed)
                with self.assertRaises(DesignError):
                    validate_exchange(changed)
        drilled = deepcopy(valid)
        drilled["manufacturing_holes"] = [{"xyz_mm": [1, 2, 3]}]
        rehash_exchange(drilled)
        with self.assertRaises(DesignError):
            validate_exchange(drilled)

    def test_csv_svg_manifest_and_cad_share_one_piece_set_and_dimensions(self):
        request = {"action": "modular", "module_spec": coffee_spec()}
        bundle = pilot_review(request)
        manifest = json.loads(bundle["manifest.json"])
        model = json.loads(bundle["maestro-review.json"])["modular"]
        cad = json.loads(bundle["cad-exchange.json"])
        boxes = {box["piece_id"]: box for box in cad["boxes"]}
        rows = list(csv.DictReader(StringIO(bundle["parts-review.csv"])))
        csv_ids = {row["piece_id"] for row in rows}
        cad_ids = set(boxes)
        svg_root = ET.fromstring(bundle["front-review.svg"])
        svg_ids = {node.attrib["data-piece-id"] for node in svg_root.iter()
                   if "data-piece-id" in node.attrib}
        self.assertEqual(csv_ids, cad_ids)
        self.assertEqual(svg_ids, cad_ids)
        self.assertEqual(set(manifest["piece_ids"]), cad_ids)
        self.assertEqual(manifest["piece_count"], 10)
        self.assertNotIn("three-views.pdf", manifest["files"])
        self.assertEqual(manifest["geometry_sha256"], cad["geometry_sha256"])
        self.assertEqual(manifest["assembly_review"], model["assembly_review"])
        self.assertEqual(manifest["upper_support_review"], model["upper_support_review"])
        role_order = {
            "left_side": "side", "right_side": "side",
            "bottom": "horizontal", "shelf_horizontal": "horizontal",
            "countertop": "horizontal", "upper_front_tie": "upright",
            "upper_rear_tie": "upright", "lower_rear_tie": "upright",
            "front_left": "front", "front_right": "front",
        }
        for row in rows:
            box = boxes[row["piece_id"]]
            self.assertEqual(row["role"], box["role"])
            self.assertEqual([int(row[f"origin_{axis}_mm"]) for axis in "xyz"],
                             box["origin_xyz_mm"])
            fx, fy, thick = (int(row[key]) for key in (
                "nominal_face_x_mm", "nominal_face_y_mm", "thickness_mm"))
            expected = ([thick, fy, fx] if role_order[row["role"]] == "side" else
                        [fx, fy, thick] if role_order[row["role"]] in (
                            "upright", "front") else [fx, thick, fy])
            self.assertEqual(box["size_xyz_mm"], expected, row["piece_id"])
        formula = " ".join(row["dimension_formula"] for row in rows)
        self.assertIn("REVIEW_HEIGHT_HYPOTHESIS_ONLY", formula)
        self.assertIn("HYPOTHESIS_PREVIEW_ONLY", formula)
        self.assertEqual(verify_pilot_bundle_dict(bundle), cad)

    def test_front_and_rear_views_are_cad_backed_and_show_visibility_states(self):
        model = design_modular_run(coffee_spec())
        cad = cad_exchange(model)
        sheet = three_views_svg(cad, review_model=model)
        root = ET.fromstring(sheet)
        views: dict[str, set[str]] = {}
        for node in root.iter():
            view = node.attrib.get("data-view")
            piece_id = node.attrib.get("data-piece-id")
            if view and piece_id:
                views.setdefault(view, set()).add(piece_id)
        front = views["01  FRENTE CERRADO / CAD"]
        interior = views["02  FRENTE INTERIOR / CAD"]
        rear = views["03  POSTERIOR / CAD"]
        self.assertIn("COFFEE-FRONT_LEFT", front)
        self.assertNotIn("COFFEE-UPPER_FRONT_TIE", front)
        self.assertIn("COFFEE-SHELF", interior)
        self.assertIn("COFFEE-UPPER_FRONT_TIE", interior)
        self.assertNotIn("COFFEE-FRONT_LEFT", interior)
        self.assertIn("COFFEE-UPPER_REAR_TIE", rear)
        self.assertIn("COFFEE-LOWER_REAR_TIE", rear)
        self.assertNotIn("COFFEE-UPPER_FRONT_TIE", rear)
        for title in ("04  LATERAL / Z-Y · CAD", "05  PLANTA / X-Z · CAD"):
            self.assertIn(title, views)
        self.assertIn("Muro:", sheet)
        self.assertIn("NO soporta carga vertical", sheet)
        self.assertNotIn("soporte mural vertical", sheet.lower())
        self.assertIn("NONE_OWNER_CONFIRMED", model["upper_support_review"]["wall_vertical_load_role"])
        self.assertNotIn("<path", sheet)

    def test_bundle_verifier_rejects_svg_piece_id_not_in_cad(self):
        bundle = pilot_review({"action": "modular", "module_spec": coffee_spec()})
        tampered = dict(bundle)
        tampered["front-review.svg"] = tampered["front-review.svg"].replace(
            'data-piece-id="COFFEE-LEFT_SIDE"',
            'data-piece-id="COFFEE-INVENTED_SIDE"', 1)
        self.assertNotEqual(tampered["front-review.svg"], bundle["front-review.svg"])
        with self.assertRaises(PilotError):
            verify_pilot_bundle_dict(tampered)

    def test_bundle_verifier_rejects_purchase_permission(self):
        bundle = pilot_review({"action": "modular", "module_spec": coffee_spec()})
        tampered = dict(bundle)
        manifest = json.loads(tampered["manifest.json"])
        manifest["purchase_ready"] = True
        tampered["manifest.json"] = json.dumps(manifest, ensure_ascii=False)
        with self.assertRaises(PilotError):
            verify_pilot_bundle_dict(tampered)

    def test_protected_wall_bar_fixture_digest_is_unchanged(self):
        fixture = Path(__file__).resolve().parents[1] / "examples" / "wall-bar-900-review-p5.json"
        request = json.loads(fixture.read_text(encoding="utf-8"))
        answer = consult_maestro(request)
        cad = cad_exchange(answer["modular"])
        self.assertEqual(cad["geometry_sha256"],
                         "5c0b8944ba015ef537688afac3ee58b9dd52011267c28278c9134a473cecf947")
        self.assertEqual(len(cad["boxes"]), 28)
        flags = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
        self.assertEqual({key: answer[key] for key in flags},
                         {key: False for key in flags})


def verify_pilot_bundle_dict(bundle: dict[str, str]) -> dict:
    """Write the real pilot bundle to a temporary folder and verify its manifest."""
    with TemporaryDirectory(prefix="carpn-coffee-bundle-") as temporary:
        folder = Path(temporary) / "review"
        folder.mkdir()
        for name, content in bundle.items():
            (folder / name).write_text(content, encoding="utf-8", newline="")
        return verify_pilot_bundle(folder)


if __name__ == "__main__":
    unittest.main()
