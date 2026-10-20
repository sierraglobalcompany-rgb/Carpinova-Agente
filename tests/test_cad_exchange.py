"""F7: FreeCAD/Blender share exactly one checked 3D geometry contract."""
import copy
import json
from pathlib import Path
import unittest

from carpinova_agent.core import DesignError
from carpinova_agent.modular import design_modular_run
from carpinova_agent.cad_exchange import cad_exchange,validate_exchange
from integrations.cad_native import native_boxes

ROOT=Path(__file__).resolve().parent.parent
def model():
    spec=json.loads((ROOT/"examples/modular-closet.json").read_text(encoding="utf-8"))
    return design_modular_run(spec)


class CadExchangeTests(unittest.TestCase):
    def test_exact_boxes_and_single_snapshot(self):
        data=cad_exchange(model())
        self.assertEqual(data["status"],"DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(data["unit"],"mm")
        self.assertEqual(data["bounds_xyz_mm"],[2000,2400,600])
        self.assertEqual(len(data["boxes"]),8)
        self.assertEqual(validate_exchange(data),data)
        self.assertEqual(data["manufacturing_holes"],[])
        self.assertFalse(data["cutting_ready"])

    def test_source_dimensions_for_lateral_and_top(self):
        data=cad_exchange(model())
        pieces={x["piece_id"]:x for x in data["boxes"]}
        left=pieces["LEFT-LEFT_SIDE"]
        top=pieces["LEFT-TOP"]
        self.assertEqual(left["size_xyz_mm"],[18,2400,600])
        self.assertEqual(top["size_xyz_mm"],[914,18,600])
        self.assertEqual(left["origin_xyz_mm"],[0,0,0])
        self.assertEqual(top["origin_xyz_mm"],[18,2382,0])
        self.assertEqual(left["grain_world_axis"],"Y")
        self.assertEqual(top["grain_world_axis"],"X")

    def test_native_axes_transform_for_both_apps(self):
        source=cad_exchange(model())
        panels={x["piece_id"]:x for x in native_boxes(source)}
        self.assertEqual(panels["LEFT-LEFT_SIDE"]["native_origin_xyz_mm"],[0,-600,0])
        self.assertEqual(panels["LEFT-LEFT_SIDE"]["native_size_xyz_mm"],[18,600,2400])
        self.assertEqual(panels["LEFT-TOP"]["native_origin_xyz_mm"],[18,-600,2382])
        self.assertEqual(panels["LEFT-TOP"]["native_size_xyz_mm"],[914,600,18])

    def test_deterministic_sha(self):
        a=cad_exchange(model())
        b=cad_exchange(model())
        self.assertEqual(a["geometry_sha256"],b["geometry_sha256"])

    def test_change_in_module_changes_digest(self):
        spec=json.loads((ROOT/"examples/modular-closet.json").read_text())
        a=cad_exchange(design_modular_run(spec))
        spec["modules"][0]["width_mm"]=900
        spec["modules"][1]["width_mm"]=1100
        b=cad_exchange(design_modular_run(spec))
        self.assertNotEqual(a["geometry_sha256"],b["geometry_sha256"])

    def test_reject_tampered_dimensions(self):
        data=cad_exchange(model())
        data["boxes"][0]["size_xyz_mm"][0]=500
        with self.assertRaises(DesignError):
            validate_exchange(data)

    def test_reject_invented_holes(self):
        data=cad_exchange(model())
        data["manufacturing_holes"]=[[37,32]]
        with self.assertRaises(DesignError):
            validate_exchange(data)

    def test_reject_new_flags(self):
        data=cad_exchange(model())
        data["cutting_ready"]=True
        with self.assertRaises(DesignError):
            validate_exchange(data)

    def test_reject_unknown_geometry_version(self):
        data=cad_exchange(model())
        data["schema_version"]="999"
        with self.assertRaises(DesignError):
            validate_exchange(data)

    def test_reject_injected_extra_fields(self):
        data=cad_exchange(model())
        data["execute_code"]="import os"
        with self.assertRaises(DesignError):
            validate_exchange(data)

    def test_reject_out_of_bounds_even_with_valid_checksum(self):
        data=cad_exchange(model())
        data["boxes"][0]["origin_xyz_mm"][0]=1999
        import hashlib
        payload={k:v for k,v in data.items() if k!="geometry_sha256"}
        data["geometry_sha256"]=hashlib.sha256(json.dumps(
            payload,sort_keys=True,ensure_ascii=False,separators=(",",":")
        ).encode("utf-8")).hexdigest()
        with self.assertRaises(DesignError):
            validate_exchange(data)

    def test_reject_overlapping_panels_with_valid_checksum(self):
        # A valid SHA proves only consistency of bytes, NOT clash-free CAD.
        import hashlib
        data=cad_exchange(model())
        left=next(x for x in data["boxes"] if x["piece_id"]=="LEFT-LEFT_SIDE")
        top=next(x for x in data["boxes"] if x["piece_id"]=="LEFT-TOP")
        top["origin_xyz_mm"]=left["origin_xyz_mm"].copy()
        payload={k:v for k,v in data.items() if k!="geometry_sha256"}
        data["geometry_sha256"]=hashlib.sha256(json.dumps(
            payload,sort_keys=True,ensure_ascii=False,separators=(",",":")
        ).encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(DesignError,"mismo volumen"):
            validate_exchange(data)

    def test_cad_generation_fails_when_source_panels_overlap(self):
        draft=model()
        left=next(x for x in draft["parts"] if x["piece_id"]=="LEFT-LEFT_SIDE")
        right=next(x for x in draft["parts"] if x["piece_id"]=="LEFT-RIGHT_SIDE")
        right["nominal_origin_xyz_mm"]=left["nominal_origin_xyz_mm"].copy()
        with self.assertRaisesRegex(DesignError,"mismo volumen"):
            cad_exchange(draft)

    def test_butt_join_contacts_still_valid(self):
        # The opening carcass has butt joints at zero shared volume;
        # those are not a collision in this mathematical audit.
        result=cad_exchange(model())
        self.assertEqual(validate_exchange(result),result)

    def test_reject_site_conflicts(self):
        spec=json.loads((ROOT/"examples/modular-closet.json").read_text())
        spec["site_width_mm"]["bottom"]=1950
        with self.assertRaises(DesignError):
            cad_exchange(design_modular_run(spec))

    def test_reject_missing_piece(self):
        data=cad_exchange(model())
        data["boxes"]=[]
        with self.assertRaises(DesignError):
            validate_exchange(data)

    def test_no_input_mutation(self):
        original=model()
        copy_=copy.deepcopy(original)
        cad_exchange(original)
        self.assertEqual(original,copy_)

    def test_full_3d_geometry_only_not_hardware(self):
        cad=cad_exchange(model())
        self.assertFalse(cad["hardware_included"])
        self.assertFalse(cad["finished_panel_edges_included"])


if __name__=="__main__":
    unittest.main()
