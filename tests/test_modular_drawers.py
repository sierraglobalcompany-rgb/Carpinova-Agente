"""F7C Task3: two stackable drawers reuse F1's five-panel calculation."""
import copy
import csv
import json
from io import StringIO
from pathlib import Path
import unittest
from xml.etree import ElementTree

from carpinova_agent.core import DesignError, design
from carpinova_agent.modular import design_modular_run
from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.modular_outputs import modular_bom_csv, modular_front_svg
from integrations.cad_native import native_boxes

ROOT = Path(__file__).resolve().parent.parent / "examples"


def fixture():
    return json.loads((ROOT / "modular-two-drawers-inset.json").read_text(encoding="utf-8"))


class ModularDrawerTests(unittest.TestCase):
    def test_two_drawers_and_one_back(self):
        model = design_modular_run(fixture())
        self.assertEqual(model["piece_count"], 17)
        self.assertEqual(len(model["modules"][0]["drawer_ids"]), 2)
        self.assertEqual(model["modules"][0]["drawer_ids"], ["TOP", "LOW"])
        self.assertEqual(len({p["piece_id"] for p in model["parts"]}), 17)
        self.assertEqual(model["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertFalse(model["fabrication_ready"])
        self.assertFalse(model["purchase_ready"])
        self.assertFalse(model["drilling_ready"])

    def test_box_nominal_dimensions_are_exact_F1_calculation(self):
        data=fixture()
        run=design_modular_run(data)
        box={p["piece_id"]:p for p in run["parts"]}
        spec=data["modules"][0]["drawers"][0]
        f1=design({
            "type":"drawer", "opening_width_mm":564,
            **{k:spec[k] for k in (
              "opening_height_mm","opening_depth_mm","box_height_mm",
              "panel_thickness_mm","bottom_thickness_mm","slide_clearance_left_mm",
              "slide_clearance_right_mm","front_setback_mm","rear_setback_mm")}
        })
        self.assertEqual(f1["dimensions"]["box_external_width_mm"],538)
        self.assertEqual(f1["dimensions"]["box_external_depth_mm"],460)
        self.assertEqual(box["BASE-TOP-DRAWER_SIDE_LEFT"]["nominal_face_x_mm"],
                         f1["parts"][0]["face_x_mm"])
        self.assertEqual(box["BASE-TOP-DRAWER_SIDE_LEFT"]["nominal_face_y_mm"],
                         f1["parts"][0]["face_y_mm"])
        self.assertEqual(box["BASE-TOP-DRAWER_FRONT_WALL"]["nominal_face_x_mm"],
                         f1["parts"][1]["face_x_mm"])
        self.assertEqual(box["BASE-TOP-DRAWER_BOTTOM"]["nominal_face_x_mm"],
                         f1["parts"][2]["face_x_mm"])

    def test_xy_yz_xz_physical_panel_positions(self):
        panels={p["piece_id"]:p for p in design_modular_run(fixture())["parts"]}
        expected={
          "BASE-TOP-DRAWER_SIDE_LEFT":("YZ",[31,24,30],460,224,18),
          "BASE-TOP-DRAWER_SIDE_RIGHT":("YZ",[551,24,30],460,224,18),
          "BASE-TOP-DRAWER_FRONT_WALL":("XY",[49,24,30],502,224,18),
          "BASE-TOP-DRAWER_REAR_WALL":("XY",[49,24,472],502,224,18),
          "BASE-TOP-DRAWER_BOTTOM":("XZ",[31,18,30],538,460,6),
          "BASE-TOP-DRAWER_FACADE":("XY",[21,21,0],558,294,18),
        }
        for name, (plane,pos,fx,fy,t) in expected.items():
            with self.subTest(name=name):
                p=panels[name]
                self.assertEqual(p["face_plane"],plane)
                self.assertEqual(p["nominal_origin_xyz_mm"],pos)
                self.assertEqual((p["nominal_face_x_mm"],p["nominal_face_y_mm"],
                                  p["thickness_mm"]),(fx,fy,t))

    def test_stacked_drawer_origins_separate_by_344_mm(self):
        panels={p["piece_id"]:p for p in design_modular_run(fixture())["parts"]}
        top=panels["BASE-TOP-DRAWER_BOTTOM"]["nominal_origin_xyz_mm"][1]
        low=panels["BASE-LOW-DRAWER_BOTTOM"]["nominal_origin_xyz_mm"][1]
        self.assertEqual(low-top,344)

    def test_lower_drawer_bottom_is_not_decorative_front(self):
        p={x["piece_id"]:x for x in design_modular_run(fixture())["parts"]}
        self.assertEqual(p["BASE-LOW-DRAWER_BOTTOM"]["thickness_mm"],6)
        self.assertEqual(p["BASE-LOW-DRAWER_FACADE"]["thickness_mm"],18)
        self.assertEqual(p["BASE-LOW-DRAWER_FACADE"]["material_id"],"OAK_MELAMINE_18")

    def test_cad_17_boxes_and_no_factory_coordinates(self):
        cad=cad_exchange(design_modular_run(fixture()))
        self.assertEqual(cad["source_engine"],"F7C_DRAWER_BOXES_FROM_F1")
        self.assertEqual(len(cad["boxes"]),17)
        self.assertEqual(cad["bounds_xyz_mm"],[600,720,560])
        self.assertEqual(validate_exchange(cad),cad)
        self.assertEqual(len(native_boxes(cad)),17)
        self.assertEqual(cad["manufacturing_holes"],[])
        self.assertFalse(cad["fabrication_ready"])
        self.assertFalse(cad["drilling_ready"])
        self.assertFalse(cad["hardware_included"])

    def test_cad_boxes_true_orientation(self):
        cad=cad_exchange(design_modular_run(fixture()))
        b={x["piece_id"]:x for x in cad["boxes"]}
        self.assertEqual(b["BASE-TOP-DRAWER_SIDE_LEFT"]["size_xyz_mm"],[18,224,460])
        self.assertEqual(b["BASE-TOP-DRAWER_BOTTOM"]["size_xyz_mm"],[538,6,460])
        self.assertEqual(b["BASE-TOP-DRAWER_FACADE"]["size_xyz_mm"],[558,294,18])

    def test_csv_svg_same_model(self):
        m=design_modular_run(fixture())
        rows=list(csv.DictReader(StringIO(modular_bom_csv(m))))
        self.assertEqual(len(rows),17)
        self.assertEqual(sum(r["role"]=="drawer_facade" for r in rows),2)
        self.assertEqual({r["drawer_id"] for r in rows if r["role"]=="drawer_facade"},
                         {"TOP","LOW"})
        self.assertTrue(all(r["production_status"]=="BORRADOR_NO_CORTAR" for r in rows))
        svg=modular_front_svg(m)
        self.assertIn("sin bisagras, correderas ni mecanizados",svg)
        root=ElementTree.fromstring(svg)
        ns="{http://www.w3.org/2000/svg}"
        self.assertEqual(len(root.findall(f"{ns}rect")),17)
        self.assertEqual(sum(r.get("class")=="front" for r in root.findall(f"{ns}rect")),2)

    def test_slides_always_unconfirmed(self):
        m=design_modular_run(fixture())
        self.assertTrue(any("SIN validar SKU" in b for b in m["blockers"]))
        for p in m["parts"]:
            self.assertNotIn("drilling_coordinates",p)
            self.assertIsNone(p["finished_cut_dimensions_mm"])

    def test_cabinet_legacy_has_no_drawer(self):
        old=json.loads((ROOT/"modular-kitchen-door-fronts.json").read_text())
        self.assertEqual(design_modular_run(old)["piece_count"],13)

    def test_drawer_cannot_exceed_opening(self):
        data=fixture()
        data["modules"][0]["drawers"][0]["opening_height_mm"]=700
        with self.assertRaises(DesignError):design_modular_run(data)

    def test_drawer_apertures_cannot_overlap_or_touch(self):
        for value in (200,300):
            d=fixture()
            d["modules"][0]["drawers"][1]["opening_bottom_offset_mm"]=value
            with self.subTest(value=value),self.assertRaises(DesignError):
                design_modular_run(d)

    def test_slides_clearance_must_be_user_data(self):
        d=fixture()
        del d["modules"][0]["drawers"][0]["slide_clearance_left_mm"]
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_facade_must_fit_in_opening(self):
        d=fixture()
        d["modules"][0]["drawers"][0]["facade"]["left_clearance_mm"]=564
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_facade_rejects_box_overlap(self):
        d=fixture()
        d["modules"][0]["drawers"][0]["front_setback_mm"]=18
        with self.assertRaisesRegex(DesignError,"retranqueo"):
            design_modular_run(d)

    def test_box_collides_with_back(self):
        d=fixture()
        d["modules"][0]["drawers"][0]["rear_setback_mm"]=5
        d["modules"][0]["drawers"][0]["opening_depth_mm"]=560
        with self.assertRaisesRegex(DesignError,"fondo posterior"):
            design_modular_run(d)

    def test_missing_facade_explicit_pending(self):
        d=fixture()
        d["modules"][0]["drawers"][0]["facade"]="pending"
        m=design_modular_run(d)
        self.assertEqual(m["piece_count"],16)
        self.assertTrue(any("falta frente decorativo" in b for b in m["blockers"]))

    def test_no_drawers_backwards_compatible(self):
        d=fixture()
        del d["modules"][0]["drawers"]
        m=design_modular_run(d)
        self.assertEqual(m["piece_count"],5)
        self.assertEqual(m["modules"][0]["drawer_ids"],[])

    def test_no_guessed_door_collision(self):
        d=fixture()
        d["modules"][0]["fronts"]=json.loads(
            (ROOT/"modular-kitchen-door-fronts.json").read_text()
        )["modules"][1]["fronts"]
        with self.assertRaisesRegex(DesignError,"puertas configuradas"):
            design_modular_run(d)

    def test_no_injected_identifiers(self):
        d=fixture()
        d["modules"][0]["drawers"][0]["drawer_id"]="=SUM(1,2)"
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_boolean_slide_measure_fails(self):
        d=fixture()
        d["modules"][0]["drawers"][0]["slide_clearance_left_mm"]=True
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_cabinet_more_than_four_drawers_fails(self):
        d=fixture()
        d["modules"][0]["drawers"]=d["modules"][0]["drawers"]*3
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_facade_only_inset(self):
        d=fixture()
        d["modules"][0]["drawers"][0]["facade"]["style"]="overlay"
        with self.assertRaises(DesignError):design_modular_run(d)

    def test_cad_hash_differs_with_box_geometry(self):
        d=fixture()
        a=cad_exchange(design_modular_run(d))["geometry_sha256"]
        d["modules"][0]["drawers"][0]["rear_setback_mm"]=42
        b=cad_exchange(design_modular_run(d))["geometry_sha256"]
        self.assertNotEqual(a,b)

    def test_no_input_mutation(self):
        d=fixture()
        before=copy.deepcopy(d)
        design_modular_run(d)
        self.assertEqual(d,before)

if __name__=="__main__":
    unittest.main()
