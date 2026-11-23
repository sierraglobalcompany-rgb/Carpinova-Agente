from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from carpinova_agent.maestro import consult_maestro
from carpinova_agent.mcp_bridge import carpinova_generar_borrador
from carpinova_agent.room_spatial import compose_verified_exchanges
from test_kitchen_linear import make_l1
from carpinova_agent.kitchen_linear import _build


FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready",
    "can_generate_f7c",
)
MEMBERS = {
    "LEER_PRIMERO.txt", "01-visor-3d.html", "02-planta.svg",
    "03-seccion.svg", "04-habitacion.json", "05-solicitud.json",
    "06-paneles-en-escena.csv", "MANIFEST.json",
}
BASE_SHA = "089ccb78c03a89113e0836948cbc9d0a402f578b"
LEGACY_LAYOUT_SHA = "fe5c492e40cb76a42fa2dba619282c4ee7544dd20b89a67782774de438d18c15"
LEGACY_ZIP_SHA = "1b48f2aa7ee7626f50df3c34e26c91ef1788cea9771357c9abd1c7ab352807ac"
LEGACY_ZIP_BYTES = 19319


class H9M4BajoAltoRearFocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.review_state = make_l1()["review_state"]
        cls.rebuilt = _build(
            copy.deepcopy(cls.review_state["working"])
        )
        cls.source_layout_sha = cls.rebuilt["layout_sha256"]
        cls.base_group_counts = {
            group: len(review["exchange"]["boxes"])
            for group, review in cls.rebuilt["_reviews"].items()
        }
        cls.delivery_root = (
            Path(os.environ["CARPN_H9_M4_DELIVERY_ROOT"]).resolve()
            if os.environ.get("CARPN_H9_M4_DELIVERY_ROOT") else None
        )
        configured_output = os.environ.get("CARPN_H9_M4_EVIDENCE_ROOT")
        cls._temporary_output = None
        if configured_output:
            cls.output_root = Path(configured_output).resolve()
            if not cls.output_root.is_dir() or any(cls.output_root.iterdir()):
                raise RuntimeError("La carpeta externa de pruebas debe existir y estar vacía")
        else:
            cls._temporary_output = tempfile.TemporaryDirectory(
                prefix="carpn-h9-m4-"
            )
            cls.output_root = Path(cls._temporary_output.name)
        cls.source_records: list[dict] = []

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._temporary_output is not None:
            cls._temporary_output.cleanup()

    @staticmethod
    def spatial_request(state: dict, revisions: list[dict] | None = None) -> dict:
        request = {
            "review_kind": "kitchen_spatial_v1",
            "review_state": copy.deepcopy(state),
            "service_zones": [],
        }
        if revisions is not None:
            request["back_revisions"] = copy.deepcopy(revisions)
        return request

    @staticmethod
    def tie_revision() -> dict:
        return {
            "group_id": "ALTO", "module_id": "KITCHEN_1", "back": "none",
            "wall_rear_ties": {
                "style": "direct_pair_review", "material_id": "MELAMINA_15",
                "thickness_mm": 15, "tie_height_mm": 80,
            },
        }

    def call_public_tool(self, project: str, revisions: list[dict] | None = None):
        request = self.spatial_request(self.review_state, revisions)
        calls: list[dict] = []
        compositions: list[list[dict]] = []

        def consult_spy(raw_request, *args, **kwargs):
            answer = consult_maestro(raw_request, *args, **kwargs)
            calls.append({"request": copy.deepcopy(raw_request),
                          "answer": copy.deepcopy(answer)})
            return answer

        def compose_spy(assemblies, service_zones=None):
            compositions.append(copy.deepcopy(assemblies))
            return compose_verified_exchanges(assemblies, service_zones)

        with patch("carpinova_agent.maestro.consult_maestro",
                   side_effect=consult_spy), patch(
                       "carpinova_agent.room_spatial.compose_verified_exchanges",
                       side_effect=compose_spy):
            response = carpinova_generar_borrador(
                json.dumps(request, ensure_ascii=False),
                proyecto=project, incluir_planos=False, seccion_y_mm=350,
            )
        self._record_source(project, revisions or [], calls, compositions)
        return response, request

    def _record_source(self, project: str, revisions: list[dict],
                       calls: list[dict], compositions: list[list[dict]]) -> None:
        if self.delivery_root is None:
            return
        targets = {(item["group_id"], item["module_id"]) for item in revisions}
        f6_models = []
        for call in calls:
            request = call["request"]
            answer = call["answer"]
            model = answer.get("modular") if type(answer) is dict else None
            if type(model) is not dict:
                continue
            modules = [m for m in model.get("modules", [])
                       if type(m) is dict]
            if not modules:
                continue
            for module in modules:
                if targets and module.get("module_id") not in {
                        module_id for _group, module_id in targets}:
                    continue
                selected = module
                f6_models.append({
                    "maestro_request": request,
                    "module_review": selected,
                    "parts": [part for part in model.get("parts", [])
                              if type(part) is dict
                              and part.get("module_id") == selected.get("module_id")],
                    "model_status": model.get("status"),
                    "piece_count": model.get("piece_count"),
                    "blockers": model.get("blockers", []),
                })
        cad_runs = []
        for assembly_set in compositions:
            cad_runs.append([{
                "group_id": assembly["group_id"],
                "origin_xyz_mm": assembly["origin_xyz_mm"],
                "rotation_deg": assembly["rotation_deg"],
                "source_engine": assembly["exchange"]["source_engine"],
                "geometry_sha256": assembly["exchange"]["geometry_sha256"],
                "bounds_xyz_mm": assembly["exchange"]["bounds_xyz_mm"],
                "boxes": assembly["exchange"]["boxes"],
            } for assembly in assembly_set])
        self.source_records.append({
            "project": project, "revisions": revisions,
            "maestro_f6": f6_models, "validated_cadexchange_inputs": cad_runs,
        })
        qa = self.delivery_root / "QA"
        qa.mkdir(parents=True, exist_ok=True)
        target = qa / "CAD_ORIGEN.json"
        target.write_text(json.dumps(self.source_records, ensure_ascii=False,
                                      sort_keys=True, indent=2) + "\n",
                          encoding="utf-8", newline="\n")

    def audit_d19(self, response: dict, request: dict, case: str) -> dict:
        path = Path(response["room_package_path"])
        payload = path.read_bytes()
        with ZipFile(io.BytesIO(payload)) as archive:
            self.assertIsNone(archive.testzip())
            names = archive.namelist()
            self.assertEqual(len(names), 8)
            self.assertEqual(set(names), MEMBERS)
            files = {name: archive.read(name) for name in names}
        manifest = json.loads(files["MANIFEST.json"])
        self.assertEqual(set(manifest["files"]), MEMBERS - {"MANIFEST.json"})
        for name, facts in manifest["files"].items():
            self.assertEqual(len(files[name]), facts["bytes"], name)
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(),
                             facts["sha256"], name)
        review = json.loads(files["04-habitacion.json"])
        self.assertEqual(json.loads(files["05-solicitud.json"]), request)
        self.assertEqual(response["piece_count"], review["piece_count"])
        self.assertEqual(manifest["piece_count"], review["piece_count"])
        self.assertEqual(manifest["release"], "NO_GO")
        self.assertEqual(response["status"], "REVIEW_ONLY")
        self.assertEqual(manifest["room_status"], "REVIEW_ONLY")
        self.assertEqual(review["status"], "REVIEW_ONLY")
        self.assertEqual(review["panel_collisions"], [])
        self.assertEqual(review["envelope_collisions"], [])
        for flag in FLAGS:
            self.assertIs(response[flag], False, flag)
            self.assertIs(review[flag], False, flag)
        ids = [box["piece_id"] for box in review["world_boxes"]]
        self.assertEqual(len(ids), len(set(ids)))

        csv_rows = list(csv.DictReader(io.StringIO(
            files["06-paneles-en-escena.csv"].decode("utf-8")
        )))
        self.assertEqual(len(csv_rows), len(review["world_boxes"]))
        json_rows = {
            (box["group_id"], box["piece_id"], box["role"]):
            (box["origin_xyz_mm"], box["size_xyz_mm"])
            for box in review["world_boxes"]
        }
        csv_map = {}
        for row in csv_rows:
            key = (row["group_id"], row["piece_id"], row["role"])
            csv_map[key] = (
                [int(row[f"{axis}_world_mm"]) for axis in "xyz"],
                [int(row[f"size_{axis}_world_mm"]) for axis in "xyz"],
            )
            self.assertEqual(row["NOT_FOR_CUTTING"], "TRUE")
        self.assertEqual(csv_map, json_rows)

        html = files["01-visor-3d.html"].decode("utf-8")
        match = re.search(
            r'<script id="scene-data" type="application/json">(.*?)</script>',
            html, re.DOTALL,
        )
        self.assertIsNotNone(match)
        scene = json.loads(match.group(1))
        html_map = {
            (box["group"], box["id"], box["role"]):
            (box["origin"], box["size"])
            for box in scene["boxes"]
        }
        self.assertEqual(html_map, json_rows)

        if self.delivery_root is not None:
            case_dir = self.delivery_root / "D19" / case
            case_dir.mkdir(parents=True, exist_ok=False)
            for name in sorted(MEMBERS):
                (case_dir / name).write_bytes(files[name])
        return {"response": response, "review": review,
                "manifest": manifest, "zip_sha256": hashlib.sha256(payload).hexdigest(),
                "zip_bytes": len(payload)}

    @staticmethod
    def world_box(review: dict, group: str, piece_id: str) -> dict:
        qualified = f"{group}:{piece_id}"
        return next(box for box in review["world_boxes"]
                    if box["piece_id"] == qualified)

    def test_h9_m4_bajo_strips_full_and_legacy(self) -> None:
        legacy_response, legacy_request = self.call_public_tool("M4-LEGACY")
        legacy = self.audit_d19(legacy_response, legacy_request, "LEGACY")
        self.assertEqual(legacy_response["piece_count"], 42)
        self.assertEqual(legacy_response["layout_sha256"], LEGACY_LAYOUT_SHA)
        self.assertEqual(legacy["zip_sha256"], LEGACY_ZIP_SHA)
        self.assertEqual(legacy["zip_bytes"], LEGACY_ZIP_BYTES)

        strips = {
            "group_id": "BAJO", "module_id": "KITCHEN_LEFT",
            "back": {
                "style": "inset_two_strips", "material_id": "HDF_3_LAB",
                "thickness_mm": 3, "services_present": False,
                "top_strip_height_mm": 100, "bottom_strip_height_mm": 100,
                "grain_axis": "none",
            },
        }
        strip_response, strip_request = self.call_public_tool(
            "M4-BAJO-STRIPS", [strips]
        )
        strip_result = self.audit_d19(strip_response, strip_request,
                                      "BAJO_LEFT_STRIPS")
        strip_room = strip_result["review"]
        self.assertEqual(strip_response["piece_count"], 44)
        self.assertEqual(strip_room["source_layout_sha256"], self.source_layout_sha)
        self.assertNotEqual(strip_room["layout_sha256"], LEGACY_LAYOUT_SHA)
        bottom = self.world_box(strip_room, "BAJO", "KITCHEN_LEFT-BACK_BOTTOM")
        top = self.world_box(strip_room, "BAJO", "KITCHEN_LEFT-BACK_TOP")
        self.assertEqual(bottom["origin_xyz_mm"], [18, 18, 515])
        self.assertEqual(bottom["size_xyz_mm"], [464, 100, 3])
        self.assertEqual(top["origin_xyz_mm"], [18, 682, 515])
        self.assertEqual(top["size_xyz_mm"], [464, 100, 3])
        self.assertTrue(any("sin instalaciones" in item
                            for row in self.source_records
                            if row["project"] == "M4-BAJO-STRIPS"
                            for call in row["maestro_f6"]
                            for item in call["blockers"]))

        full = {
            "group_id": "BAJO", "module_id": "KITCHEN_LEFT",
            "back": {
                "style": "inset_full", "material_id": "HDF_3_LAB",
                "thickness_mm": 3, "services_present": False,
                "grain_axis": "none",
            },
            "horizontal_divider_depth_mm": 497,
        }
        full_response, full_request = self.call_public_tool(
            "M4-BAJO-FULL", [full]
        )
        full_result = self.audit_d19(full_response, full_request, "BAJO_LEFT_FULL")
        full_room = full_result["review"]
        self.assertEqual(full_response["piece_count"], 43)
        back = self.world_box(full_room, "BAJO", "KITCHEN_LEFT-BACK_FULL")
        self.assertEqual(back["origin_xyz_mm"], [18, 18, 515])
        self.assertEqual(back["size_xyz_mm"], [464, 764, 3])
        legacy_bajo = {box["piece_id"]: box for box in legacy["review"]["world_boxes"]
                       if box["group_id"] == "BAJO"}
        full_bajo = {box["piece_id"]: box for box in full_room["world_boxes"]
                     if box["group_id"] == "BAJO"}
        shelf_id = "BAJO:KITCHEN_LEFT-SHELF"
        self.assertEqual(legacy_bajo[shelf_id]["size_xyz_mm"][2], 500)
        self.assertEqual(full_bajo[shelf_id]["size_xyz_mm"][2], 497)
        self.assertEqual(
            {key: value for key, value in legacy_bajo.items() if key != shelf_id},
            {key: value for key, value in full_bajo.items()
             if key not in {shelf_id, "BAJO:KITCHEN_LEFT-BACK_FULL"}},
        )

    def test_h9_m4_alto_back_ties_and_combined(self) -> None:
        alto_back = {
            "group_id": "ALTO", "module_id": "KITCHEN_1",
            "back": {
                "style": "inset_full", "material_id": "HDF_3_LAB",
                "thickness_mm": 3, "services_present": False,
                "grain_axis": "none",
            },
        }
        back_response, back_request = self.call_public_tool(
            "M4-ALTO-BACK", [alto_back]
        )
        back_result = self.audit_d19(back_response, back_request, "ALTO_BACK")
        self.assertEqual(back_response["piece_count"], 43)
        back_room = back_result["review"]
        alto = self.world_box(back_room, "ALTO", "KITCHEN_1-BACK_FULL")
        self.assertEqual(alto["origin_xyz_mm"], [15, 1465, 362])
        self.assertEqual(alto["size_xyz_mm"], [970, 670, 3])
        self.assertEqual(back_room["construction_review_by_group"]["ALTO"], {
            "back_status": "inset_full",
            "wall_support_status": "REAR_WALL_SUPPORT_PENDING",
            "wall_tie_mode": "NOT_IMPLEMENTED", "install_ready": False,
            "module_count": 1,
        })

        tie = self.tie_revision()
        tie_response, tie_request = self.call_public_tool("M4-ALTO-TIES", [tie])
        tie_result = self.audit_d19(tie_response, tie_request, "ALTO_TIES")
        self.assertEqual(tie_response["piece_count"], 44)
        tie_room = tie_result["review"]
        lower = self.world_box(tie_room, "ALTO", "KITCHEN_1-WALL_REAR_LOWER_TIE")
        upper = self.world_box(tie_room, "ALTO", "KITCHEN_1-WALL_REAR_UPPER_TIE")
        self.assertEqual(lower["role"], "wall_rear_lower_tie")
        self.assertEqual(lower["origin_xyz_mm"], [15, 1465, 350])
        self.assertEqual(lower["size_xyz_mm"], [970, 80, 15])
        self.assertEqual(upper["role"], "wall_rear_upper_tie")
        self.assertEqual(upper["origin_xyz_mm"], [15, 2055, 350])
        self.assertEqual(upper["size_xyz_mm"], [970, 80, 15])
        self.assertFalse(any(box["group_id"] == "ALTO"
                             and box["role"].startswith("back_")
                             for box in tie_room["world_boxes"]))
        self.assertEqual(tie_room["construction_review_by_group"]["ALTO"], {
            "back_status": "none",
            "wall_support_status": "REAR_WALL_SUPPORT_PENDING",
            "wall_tie_mode": "DIRECT_PAIR_CONCEPT_ONLY_UNVERIFIED",
            "install_ready": False, "module_count": 1,
        })
        self.assertIn(
            "DIRECT_PAIR_CONCEPT_ONLY_UNVERIFIED_NO_LOADS_ANCHORS_OR_HOLES",
            tie_room["warnings"],
        )
        self.assertTrue(any(
            model["module_review"].get("wall_rear_ties_review", {}).get(
                "structural_engineering") == "UNVERIFIED"
            and model["module_review"]["wall_rear_ties_review"].get(
                "cabinet_wall_anchoring") == "NOT_DESIGNED"
            for row in self.source_records if row["project"] == "M4-ALTO-TIES"
            for model in row["maestro_f6"]
        ))

        bajo_strips = {
            "group_id": "BAJO", "module_id": "KITCHEN_LEFT",
            "back": {
                "style": "inset_two_strips", "material_id": "HDF_3_LAB",
                "thickness_mm": 3, "services_present": False,
                "top_strip_height_mm": 100, "bottom_strip_height_mm": 100,
                "grain_axis": "none",
            },
        }
        combined_response, combined_request = self.call_public_tool(
            "M4-COMBINED", [bajo_strips, tie]
        )
        combined_result = self.audit_d19(combined_response, combined_request,
                                         "COMBINED")
        combined = combined_result["review"]
        self.assertEqual(combined_response["piece_count"], 46)
        self.assertEqual(combined["source_layout_sha256"], self.source_layout_sha)
        self.assertNotEqual(combined["layout_sha256"], LEGACY_LAYOUT_SHA)
        combined_ids = [box["piece_id"] for box in combined["world_boxes"]]
        self.assertEqual(len(combined_ids), len(set(combined_ids)))
        combined_group_counts = {group["group_id"]: group["piece_count"]
                                 for group in combined["groups"]}
        self.assertEqual(combined_group_counts["BAJO"], self.base_group_counts["BAJO"] + 2)
        self.assertEqual(combined_group_counts["ALTO"], self.base_group_counts["ALTO"] + 2)
        self.assertEqual(combined_group_counts["TORRE"], self.base_group_counts["TORRE"])

        # Compare the exact F6 pair returned by Maestro with the CAD boxes that
        # were passed into the compositor for the same public-tool generation.
        record = next(row for row in self.source_records
                      if row["project"] == "M4-ALTO-TIES")
        source_model = next(item for item in record["maestro_f6"]
                            if item["module_review"].get("wall_rear_ties_review"))
        f6_parts = {part["role"]: part for part in source_model["parts"]
                    if part["role"].startswith("wall_rear_")}
        self.assertEqual(set(f6_parts), {
            "wall_rear_lower_tie", "wall_rear_upper_tie",
        })
        assembly = next(item for run in record["validated_cadexchange_inputs"]
                        for item in run if item["group_id"] == "ALTO")
        cad = {box["role"]: box for box in assembly["boxes"]
               if box["role"].startswith("wall_rear_")}
        for role in f6_parts:
            part = f6_parts[role]
            self.assertEqual(cad[role]["piece_id"], part["piece_id"])
            self.assertEqual(cad[role]["material_id"], part["material_id"])
            self.assertEqual(cad[role]["size_xyz_mm"], [970, 80, 15])
            self.assertEqual(
                cad[role]["origin_xyz_mm"],
                [part["nominal_origin_xyz_mm"][0],
                 part["nominal_origin_xyz_mm"][1],
                 part["nominal_origin_xyz_mm"][2] + 15],
            )

    def test_h9_m4_fail_closed_cases_do_not_write_zip(self) -> None:
        right_full = {
            "group_id": "BAJO", "module_id": "KITCHEN_RIGHT",
            "back": {
                "style": "inset_full", "material_id": "HDF_3_LAB",
                "thickness_mm": 3, "services_present": False,
                "grain_axis": "none",
            },
        }
        right_project = "M4-BAJO-RIGHT-REJECT"
        with self.assertRaisesRegex(ValueError, "invade fondo posterior"):
            self.call_public_tool(right_project, [right_full])
        self.assertFalse((self.output_root / f"{right_project}-room-review.zip").exists())

        invalid_revisions = []
        tied_back = self.tie_revision()
        tied_back["back"] = {
            "style": "inset_full", "material_id": "HDF_3_LAB",
            "thickness_mm": 3, "services_present": False,
            "grain_axis": "none",
        }
        invalid_revisions.append(("M4-TIE-AND-BACK", [tied_back]))
        invalid_revisions.append(("M4-DUPLICATE", [self.tie_revision(),
                                                     self.tie_revision()]))
        bad_height = self.tie_revision()
        bad_height["wall_rear_ties"]["tie_height_mm"] = True
        invalid_revisions.append(("M4-BOOL-HEIGHT", [bad_height]))
        extra = self.tie_revision()
        extra["wall_rear_ties"]["anchor_count"] = 2
        invalid_revisions.append(("M4-UNKNOWN-FIELD", [extra]))
        bad_material = self.tie_revision()
        bad_material["wall_rear_ties"]["material_id"] = "HDF_3_LAB"
        invalid_revisions.append(("M4-MATERIAL-MISMATCH", [bad_material]))
        bad_thickness = self.tie_revision()
        bad_thickness["wall_rear_ties"]["thickness_mm"] = 18
        invalid_revisions.append(("M4-THICKNESS-MISMATCH", [bad_thickness]))
        for project, revisions in invalid_revisions:
            with self.subTest(project=project), self.assertRaises(ValueError):
                self.call_public_tool(project, revisions)
            self.assertFalse((self.output_root / f"{project}-room-review.zip").exists())

        base = _build(copy.deepcopy(self.review_state["working"]))
        trusted = copy.deepcopy(
            base["_reviews"]["ALTO"]["_trusted_nominal_request"]
        )
        module = trusted["module_spec"]["modules"][0]
        module["support"] = "floor"
        module["wall_rear_ties"] = copy.deepcopy(
            self.tie_revision()["wall_rear_ties"]
        )
        with self.assertRaisesRegex(ValueError, "apoyo wall|support=wall|cocina mural"):
            consult_maestro(trusted)

        service_back = {
            "group_id": "BAJO", "module_id": "KITCHEN_LEFT",
            "back": {
                "style": "inset_full", "material_id": "HDF_3_LAB",
                "thickness_mm": 3, "services_present": True,
                "grain_axis": "none",
            },
        }
        project = "M4-SERVICES-REJECT"
        with self.assertRaises(ValueError):
            self.call_public_tool(project, [service_back])
        self.assertFalse((self.output_root / f"{project}-room-review.zip").exists())


if __name__ == "__main__":
    unittest.main()
