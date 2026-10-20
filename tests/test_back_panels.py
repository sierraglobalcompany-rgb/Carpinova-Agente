"""F7C: explicit inset backs only; no cut authority or implied pipe holes."""
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


def spec(name="modular-kitchen-services.json"):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))


class BackPanelTests(unittest.TestCase):
    def test_service_example_generates_exact_two_strips(self):
        r=design_modular_run(spec())
        self.assertEqual(r["status"],"DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(r["piece_count"],10)
        self.assertEqual(len(r["parts"]),10)
        panels={p["piece_id"]:p for p in r["parts"]}
        self.assertEqual(panels["SINK-BACK_BOTTOM"]["nominal_face_x_mm"],564)
        self.assertEqual(panels["SINK-BACK_BOTTOM"]["nominal_face_y_mm"],120)
        self.assertEqual(panels["SINK-BACK_BOTTOM"]["nominal_origin_xyz_mm"],[18,18,554])
        self.assertEqual(panels["SINK-BACK_TOP"]["nominal_face_y_mm"],90)
        self.assertEqual(panels["SINK-BACK_TOP"]["nominal_origin_xyz_mm"],[18,612,554])
        self.assertEqual(r["modules"][0]["part_ids"][-2:],
                         ["SINK-BACK_BOTTOM","SINK-BACK_TOP"])
        self.assertTrue(any("474 mm" in msg for msg in r["blockers"]))
        self.assertFalse(r["cutting_ready"])
        self.assertFalse(r["fabrication_ready"])
        self.assertFalse(r["drilling_ready"])
        self.assertFalse(r["purchase_ready"])

    def test_inset_full_cabinet(self):
        r=design_modular_run(spec("modular-closet-inset-back.json"))
        self.assertEqual(r["piece_count"],5)
        back=r["parts"][-1]
        self.assertEqual(back["role"],"back_full")
        self.assertEqual(back["nominal_face_x_mm"],864)
        self.assertEqual(back["nominal_face_y_mm"],1764)
        self.assertEqual(back["nominal_origin_xyz_mm"],[18,18,544])
        self.assertEqual(back["face_plane"],"XY")
        self.assertEqual(back["grain_axis"],"face_y")
        self.assertIsNone(back["finished_cut_dimensions_mm"])

    def test_geometry_identical_to_F6_for_first_four_panels(self):
        updated=spec()
        legacy=copy.deepcopy(updated)
        legacy["modules"][0]["back"]="none"
        a=design_modular_run(legacy)["parts"][:4]
        b=design_modular_run(updated)["parts"][:4]
        self.assertEqual(a,b)

    def test_back_panels_have_real_rear_plane_bounding_boxes(self):
        c=cad_exchange(design_modular_run(spec()))
        self.assertEqual(c["source_engine"],"F7C_INSET_BACKS_FROM_F6")
        self.assertEqual(len(c["boxes"]),10)
        self.assertEqual(validate_exchange(c),c)
        by_id={a["piece_id"]:a for a in c["boxes"]}
        bottom=by_id["SINK-BACK_BOTTOM"]
        self.assertEqual(bottom["size_xyz_mm"],[564,120,6])
        self.assertEqual(bottom["origin_xyz_mm"],[18,18,554])
        self.assertEqual(bottom["grain_world_axis"],"none")
        self.assertEqual(c["manufacturing_holes"],[])
        self.assertFalse(c["fabrication_ready"])
        self.assertEqual(len(native_boxes(c)),10)

    def test_old_exchange_keeps_old_contract_source(self):
        c=cad_exchange(design_modular_run(spec("modular-kitchen.json")))
        self.assertEqual(c["source_engine"],"F6_OPEN_MODULES_FROM_F1")
        self.assertEqual(len(c["boxes"]),8)

    def test_csv_and_svg_reuse_same_back_parts(self):
        r=design_modular_run(spec())
        rows=list(csv.DictReader(StringIO(modular_bom_csv(r))))
        self.assertEqual(len(rows),10)
        self.assertEqual(rows[-1]["piece_id"],"SINK-BACK_TOP")
        self.assertEqual(rows[-1]["face_plane"],"XY")
        self.assertEqual(rows[-1]["production_status"],"BORRADOR_NO_CORTAR")
        svg=modular_front_svg(r)
        root=ElementTree.fromstring(svg)
        self.assertEqual(len(root.findall("{http://www.w3.org/2000/svg}rect")),10)
        self.assertIn("SINK-BACK_TOP",svg)
        self.assertIn("NO CORTAR",svg)

    def test_all_missing_edges_unconfirmed(self):
        r=design_modular_run(spec())
        for part in r["parts"]:
            if part["role"].startswith("back_"):
                self.assertEqual(part["edgebanding_edges"],"UNCONFIRMED")
                self.assertIsNone(part["edgebanding_nominal_total_mm"])

    def test_strips_not_claimed_to_be_pipe_holes(self):
        r=design_modular_run(spec())
        self.assertTrue(any("cotejar tuberías" in msg for msg in r["blockers"]))
        self.assertTrue(all(p["role"] != "pipe_hole" for p in r["parts"]))

    def test_no_back_stays_open(self):
        r=design_modular_run(spec("modular-kitchen.json"))
        self.assertEqual(r["piece_count"],8)

    def test_full_back_with_services_must_fail(self):
        d=spec("modular-closet-inset-back.json")
        d["modules"][0]["back"]["services_present"]=True
        with self.assertRaisesRegex(DesignError,"obstruiría"):
            design_modular_run(d)

    def test_strips_without_heights_must_fail(self):
        d=spec()
        del d["modules"][0]["back"]["top_strip_height_mm"]
        with self.assertRaises(DesignError):
            design_modular_run(d)

    def test_no_services_flag_fails(self):
        d=spec()
        del d["modules"][0]["back"]["services_present"]
        with self.assertRaises(DesignError):
            design_modular_run(d)

    def test_unknown_back_model_fails(self):
        d=spec()
        d["modules"][0]["back"]["style"]="curved_routed"
        with self.assertRaises(DesignError):
            design_modular_run(d)

    def test_unknown_dimensions_must_fail(self):
        d=spec()
        d["modules"][0]["back"]["router_diameter_mm"]=12
        with self.assertRaises(DesignError):
            design_modular_run(d)

    def test_invalid_material_id_fails(self):
        d=spec()
        d["modules"][0]["back"]["material_id"]="=HYPERLINK()"
        with self.assertRaises(DesignError):
            design_modular_run(d)

    def test_strip_overlap_fails(self):
        d=spec()
        d["modules"][0]["back"]["top_strip_height_mm"]=600
        d["modules"][0]["back"]["bottom_strip_height_mm"]=120
        with self.assertRaisesRegex(DesignError,"acceso"):
            design_modular_run(d)

    def test_boolean_dimensions_fail(self):
        d=spec()
        d["modules"][0]["back"]["thickness_mm"]=True
        with self.assertRaises(DesignError):
            design_modular_run(d)

    def test_too_thick_back_fails(self):
        d=spec()
        d["modules"][0]["back"]["thickness_mm"]=560
        with self.assertRaises(DesignError):
            design_modular_run(d)

    def test_string_boolean_fails(self):
        d=spec()
        d["modules"][0]["back"]["services_present"]="false"
        with self.assertRaises(DesignError):
            design_modular_run(d)

    def test_full_with_strips_fields_fails(self):
        d=spec("modular-closet-inset-back.json")
        d["modules"][0]["back"]["top_strip_height_mm"]=100
        with self.assertRaises(DesignError):
            design_modular_run(d)

    def test_missing_grain_remains_unconfirmed(self):
        d=spec()
        del d["modules"][0]["back"]["grain_axis"]
        r=design_modular_run(d)
        self.assertEqual(r["parts"][-1]["grain_axis"],"UNCONFIRMED")
        self.assertTrue(any("orientar veta" in msg for msg in r["blockers"]))

    def test_inputs_not_mutated(self):
        d=spec()
        snapshot=copy.deepcopy(d)
        design_modular_run(d)
        self.assertEqual(d,snapshot)

    def test_cad_hash_changes_if_service_strip_changes(self):
        d=spec()
        baseline=cad_exchange(design_modular_run(d))["geometry_sha256"]
        d["modules"][0]["back"]["top_strip_height_mm"]=100
        alt=cad_exchange(design_modular_run(d))["geometry_sha256"]
        self.assertNotEqual(baseline,alt)

    def test_reject_non_rectangular_perforation(self):
        d=spec()
        d["modules"][0]["back"]["hole_x_mm"]=55
        with self.assertRaises(DesignError):
            design_modular_run(d)


if __name__=="__main__":
    unittest.main()
