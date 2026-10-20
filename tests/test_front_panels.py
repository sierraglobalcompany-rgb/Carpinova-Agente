"""F7C Task2 front leaves: geometry and safety before hinge manufacturer validation."""
import copy
import csv
import json
from io import StringIO
from pathlib import Path
import unittest
from xml.etree import ElementTree

from carpinova_agent.core import DesignError
from carpinova_agent.modular import design_modular_run
from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.modular_outputs import modular_bom_csv, modular_front_svg
from integrations.cad_native import native_boxes

ROOT=Path(__file__).resolve().parent.parent/"examples"


def fixture(file="modular-kitchen-door-fronts.json"):
    return json.loads((ROOT/file).read_text(encoding="utf-8"))


class FrontTests(unittest.TestCase):
    def test_kitchen_has_13_panels_and_exact_overlay_dimensions(self):
        out=design_modular_run(fixture())
        self.assertEqual(out["piece_count"], 13)
        part={p["piece_id"]:p for p in out["parts"]}
        self.assertEqual(part["SINK-FRONT_LEFT"]["nominal_face_x_mm"],295)
        self.assertEqual(part["SINK-FRONT_LEFT"]["nominal_face_y_mm"],712)
        self.assertEqual(part["SINK-FRONT_LEFT"]["nominal_origin_xyz_mm"],[3,4,-18])
        self.assertEqual(part["SINK-FRONT_RIGHT"]["nominal_origin_xyz_mm"],[302,4,-18])
        self.assertEqual(part["STORAGE-FRONT_SINGLE"]["nominal_face_x_mm"],560)
        self.assertEqual(part["STORAGE-FRONT_SINGLE"]["nominal_face_y_mm"],680)
        self.assertEqual(part["STORAGE-FRONT_SINGLE"]["nominal_origin_xyz_mm"],[620,20,0])
        self.assertEqual(part["SINK-FRONT_LEFT"]["hinge_side_requested"],"left")
        self.assertEqual(part["SINK-FRONT_RIGHT"]["hinge_side_requested"],"right")
        self.assertTrue(all(p["finished_cut_dimensions_mm"] is None for p in out["parts"]))
        self.assertFalse(out["fabrication_ready"])
        self.assertFalse(out["purchase_ready"])
        self.assertFalse(out["cutting_ready"])
        self.assertFalse(out["drilling_ready"])

    def test_inset_closet_double_doors_and_back(self):
        out=design_modular_run(fixture("modular-closet-inset-doors.json"))
        self.assertEqual(out["piece_count"],7)
        p={x["piece_id"]:x for x in out["parts"]}
        self.assertEqual(p["WARDROBE-FRONT_LEFT"]["nominal_face_x_mm"],428)
        self.assertEqual(p["WARDROBE-FRONT_LEFT"]["nominal_face_y_mm"],1760)
        self.assertEqual(p["WARDROBE-FRONT_LEFT"]["nominal_origin_xyz_mm"],[20,20,0])
        self.assertEqual(p["WARDROBE-FRONT_RIGHT"]["nominal_origin_xyz_mm"],[452,20,0])

    def test_F1_carcase_parts_unchanged(self):
        d=fixture()
        baseline=copy.deepcopy(d)
        for m in baseline["modules"]:
            m["fronts"]="none"
        current={p["piece_id"]:p for p in design_modular_run(d)["parts"]}
        old={p["piece_id"]:p for p in design_modular_run(baseline)["parts"]}
        for k in old:
            self.assertEqual(current[k],old[k])
    
    def test_formula_provenance_has_single_center_gap(self):
        d=design_modular_run(fixture())
        panels={p["piece_id"]:p for p in d["parts"]}
        dual=panels["SINK-FRONT_LEFT"]["source_formula"]
        one=panels["STORAGE-FRONT_SINGLE"]["source_formula"]
        self.assertEqual(dual.count("fronts.center_gap_mm"),1)
        self.assertEqual(one.count("fronts.center_gap_mm"),0)
        self.assertIn("F1.clear_width_mm",one)
        self.assertIn("fronts.leaf_count",dual)

    def test_explicit_grain_and_edges(self):
        d=fixture()
        r=design_modular_run(d)
        door=next(x for x in r["parts"] if x["piece_id"]=="SINK-FRONT_LEFT")
        self.assertEqual(door["grain_axis"],"face_y")
        self.assertEqual(door["edgebanding_nominal_total_mm"],2014)
        self.assertEqual(door["edgebanding_thickness_mm"],1)
        self.assertEqual(door["edgebanding_edges"],
                         ["x_max","x_min","y_max","y_min"])

    def test_missing_grain_and_canto_remains_unconfirmed(self):
        d=fixture()
        x=d["modules"][0]["fronts"]
        for k in ("grain_axis","edgebanding_edges","edgeband_thickness_mm"):
            del x[k]
        out=design_modular_run(d)
        p=next(p for p in out["parts"] if p["role"]=="front_left")
        self.assertEqual(p["grain_axis"],"UNCONFIRMED")
        self.assertEqual(p["edgebanding_edges"],"UNCONFIRMED")
        self.assertIsNone(p["edgebanding_nominal_total_mm"])
        self.assertTrue(any("veta" in b.lower() for b in out["blockers"]))

    def test_cad_explicit_front_shift_for_both_apps(self):
        d=fixture()
        model=design_modular_run(d)
        cad=cad_exchange(model)
        self.assertEqual(validate_exchange(cad),cad)
        self.assertEqual(cad["source_engine"],"F7C_EXPLICIT_FRONTS_FROM_F6")
        self.assertEqual(cad["front_shift_mm"],18)
        self.assertEqual(cad["bounds_xyz_mm"],[1200,720,578])
        boxes={p["piece_id"]:p for p in cad["boxes"]}
        self.assertEqual(boxes["SINK-FRONT_LEFT"]["origin_xyz_mm"],[3,4,0])
        self.assertEqual(boxes["SINK-FRONT_LEFT"]["size_xyz_mm"],[295,712,18])
        self.assertEqual(boxes["SINK-BACK_TOP"]["origin_xyz_mm"],[18,612,572])
        self.assertEqual(boxes["STORAGE-FRONT_SINGLE"]["origin_xyz_mm"],[620,20,18])
        self.assertEqual(len(native_boxes(cad)),13)
        self.assertEqual(cad["manufacturing_holes"],[])
        self.assertFalse(cad["hardware_included"])

    def test_inset_only_cad_needs_no_shift(self):
        out=cad_exchange(design_modular_run(fixture("modular-closet-inset-doors.json")))
        self.assertEqual(out["front_shift_mm"],0)
        self.assertEqual(out["bounds_xyz_mm"],[900,1800,550])

    def test_legacy_contract_unchanged(self):
        r=cad_exchange(design_modular_run(fixture("modular-kitchen-services.json")))
        self.assertNotIn("front_shift_mm",r)
        self.assertEqual(r["source_engine"],"F7C_INSET_BACKS_FROM_F6")

    def test_svg_and_csv_exact_leaf_count(self):
        out=design_modular_run(fixture())
        rows=list(csv.DictReader(StringIO(modular_bom_csv(out))))
        self.assertEqual(len(rows),13)
        doors=[x for x in rows if x["role"].startswith("front_")]
        self.assertEqual(len(doors),3)
        self.assertEqual({r["hinge_side_requested"] for r in doors},{"left","right"})
        self.assertTrue(all(r["production_status"]=="BORRADOR_NO_CORTAR" for r in doors))
        svg=modular_front_svg(out)
        root=ElementTree.fromstring(svg)
        rects=root.findall("{http://www.w3.org/2000/svg}rect")
        self.assertEqual(len(rects),13)
        self.assertEqual(len([r for r in rects if r.get("class")=="front"]),3)
        self.assertIn("NO CORTAR",svg)

    def test_no_auto_drill_or_hinge_sku(self):
        out=design_modular_run(fixture())
        self.assertTrue(any("bisagra SKU" in b for b in out["blockers"]))
        self.assertFalse(any("drill_pattern" in x for x in out["parts"]))
        self.assertFalse(any("hinge_sku" in x for x in out["parts"]))

    def test_hinge_side_not_inferred(self):
        d=fixture()
        del d["modules"][0]["fronts"]["hinge_sides"]
        with self.assertRaises(DesignError): design_modular_run(d)

    def test_adjacent_overlay_seam_cannot_touch(self):
        d=fixture()
        d["modules"][1]["fronts"]=copy.deepcopy(d["modules"][0]["fronts"])
        d["modules"][0]["fronts"]["right_reveal_mm"]=0
        d["modules"][0]["fronts"]["left_reveal_mm"]=4
        d["modules"][1]["fronts"]["left_reveal_mm"]=0
        d["modules"][1]["fronts"]["right_reveal_mm"]=4
        with self.assertRaisesRegex(DesignError,"adyacentes"):
            design_modular_run(d)

    def test_adjacent_overlay_seam_with_gap_ok(self):
        d=fixture()
        d["modules"][1]["fronts"]=copy.deepcopy(d["modules"][0]["fronts"])
        out=design_modular_run(d)
        self.assertEqual(out["piece_count"],14)

    def test_overlay_must_cover_some_structure(self):
        d=fixture()
        d["modules"][0]["fronts"]["left_reveal_mm"]=18
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_even_leaf_width_required_no_silent_1mm_imbalance(self):
        d=fixture()
        d["modules"][0]["fronts"]["center_gap_mm"]=3
        with self.assertRaisesRegex(DesignError,"ancho par"):
            design_modular_run(d)

    def test_missing_center_gap_blocks(self):
        d=fixture()
        del d["modules"][0]["fronts"]["center_gap_mm"]
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_extra_gap_single_blocks(self):
        d=fixture()
        d["modules"][1]["fronts"]["center_gap_mm"]=3
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_inset_clearance_zero_blocks(self):
        d=fixture()
        d["modules"][1]["fronts"]["left_clearance_mm"]=0
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_oversized_inset_clearances_fail(self):
        d=fixture()
        d["modules"][1]["fronts"]["left_clearance_mm"]=565
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_hinge_side_wrong_or_unknown(self):
        for choice in (["right","left"], ["left","left"], ["left"], "left", [], None):
            d=fixture()
            d["modules"][0]["fronts"]["hinge_sides"]=choice
            with self.subTest(choice=choice),self.assertRaises(DesignError):
                design_modular_run(d)

    def test_unknown_style_and_fields(self):
        for val in ([], {}, 12, "slide", None):
            d=fixture()
            d["modules"][0]["fronts"]["style"]=val
            with self.subTest(val=val),self.assertRaises(DesignError):
                design_modular_run(d)
        d=fixture()
        d["modules"][0]["fronts"]["bore_distance_mm"]=21
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_grain_invalid(self):
        for val in ([], {}, True, 3, "diagonal"):
            d=fixture()
            d["modules"][0]["fronts"]["grain_axis"]=val
            with self.subTest(val=val),self.assertRaises(DesignError):
                design_modular_run(d)

    def test_canto_duplicate_or_fake_or_injected_material(self):
        for edges in (["x_min","x_min"], ["bad"], ["x_min",None], 4):
            d=fixture()
            d["modules"][0]["fronts"]["edgebanding_edges"]=edges
            with self.subTest(edges=edges),self.assertRaises(DesignError):
                design_modular_run(d)
        d=fixture()
        d["modules"][0]["fronts"]["material_id"]="=SUM(1,2)"
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_canto_thickness_and_no_canto_validity(self):
        d=fixture()
        d["modules"][0]["fronts"]["edgeband_thickness_mm"]=0
        with self.assertRaises(DesignError):design_modular_run(d)
        d=fixture()
        d["modules"][0]["fronts"]["edgebanding_edges"]=[]
        d["modules"][0]["fronts"]["edgeband_thickness_mm"]=1
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_non_integer_and_boolean_lengths_fail(self):
        for val in (True, 2.5, "4", None, -1):
            d=fixture()
            d["modules"][0]["fronts"]["center_gap_mm"]=val
            with self.subTest(val=val),self.assertRaises(DesignError):
                design_modular_run(d)

    def test_no_request_mutation(self):
        d=fixture()
        before=copy.deepcopy(d)
        design_modular_run(d)
        self.assertEqual(d,before)

    def test_hash_changes_with_clearance(self):
        d=fixture()
        a=cad_exchange(design_modular_run(d))["geometry_sha256"]
        d["modules"][1]["fronts"]["left_clearance_mm"]=4
        b=cad_exchange(design_modular_run(d))["geometry_sha256"]
        self.assertNotEqual(a,b)

    def test_hardened_exchange_validates_shift(self):
        c=cad_exchange(design_modular_run(fixture()))
        c["front_shift_mm"]=-3
        with self.assertRaises(DesignError):validate_exchange(c)
        c=cad_exchange(design_modular_run(fixture()))
        c["manufacturing_holes"]=[[12,35]]
        with self.assertRaises(DesignError):validate_exchange(c)


if __name__=="__main__":
    unittest.main()
