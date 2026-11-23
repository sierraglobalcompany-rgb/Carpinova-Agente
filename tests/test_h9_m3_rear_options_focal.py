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

from carpinova_agent.mcp_bridge import carpinova_generar_borrador
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
LEGACY_LAYOUT_SHA256 = "fe5c492e40cb76a42fa2dba619282c4ee7544dd20b89a67782774de438d18c15"
LEGACY_ZIP_SHA256 = "1b48f2aa7ee7626f50df3c34e26c91ef1788cea9771357c9abd1c7ab352807ac"
LEGACY_ZIP_BYTES = 19319


class H9M3RearOptionsFocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.review_state = make_l1()["review_state"]
        cls.rebuilt = _build(copy.deepcopy(cls.review_state["working"]))
        cls.tower_request = cls.rebuilt["_reviews"]["TORRE"][
            "_trusted_nominal_request"
        ]
        cls.tower_modules = cls.tower_request["module_spec"]["modules"]
        if not cls.tower_modules:
            raise AssertionError("La solicitud revalidada de TORRE no tiene módulos")
        cls.tower_module = copy.deepcopy(cls.tower_modules[0])
        cls.module_id = cls.tower_module["module_id"]

    @staticmethod
    def spatial_request(state: dict, back_revisions: list[dict] | None = None) -> dict:
        request = {
            "review_kind": "kitchen_spatial_v1",
            "review_state": copy.deepcopy(state),
            "service_zones": [],
        }
        if back_revisions is not None:
            request["back_revisions"] = copy.deepcopy(back_revisions)
        return request

    @staticmethod
    def revision(group_id: str, module_id: str, back: dict) -> dict:
        return {"group_id": group_id, "module_id": module_id,
                "back": copy.deepcopy(back)}

    @staticmethod
    def call(request: dict, project: str) -> dict:
        return carpinova_generar_borrador(
            solicitud_json=json.dumps(request, ensure_ascii=False),
            proyecto=project, incluir_planos=False, seccion_y_mm=350,
        )

    @staticmethod
    def read_package(path: Path) -> tuple[bytes, dict, dict, dict, str, str]:
        raw = path.read_bytes()
        with ZipFile(io.BytesIO(raw)) as archive:
            if set(archive.namelist()) != MEMBERS:
                raise AssertionError("El paquete D19 cambió sus ocho archivos")
            if archive.testzip() is not None:
                raise AssertionError("D19 testzip no pasó")
            manifest = json.loads(archive.read("MANIFEST.json"))
            if len(manifest.get("files", {})) != 7:
                raise AssertionError("El manifiesto D19 debe registrar siete archivos")
            if set(manifest["files"]) != MEMBERS - {"MANIFEST.json"}:
                raise AssertionError("El manifiesto D19 no enumera sus siete archivos exactos")
            review = json.loads(archive.read("04-habitacion.json"))
            request = json.loads(archive.read("05-solicitud.json"))
            html = archive.read("01-visor-3d.html").decode("utf-8")
            csv_text = archive.read("06-paneles-en-escena.csv").decode("utf-8")
            for name, info in manifest["files"].items():
                data = archive.read(name)
                if (len(data) != info["bytes"]
                        or hashlib.sha256(data).hexdigest() != info["sha256"]):
                    raise AssertionError(f"Manifiesto D19 incoherente: {name}")
        return raw, manifest, review, request, html, csv_text

    def call_with_cad_source(self, request: dict, project: str,
                             divider_depth: int) -> tuple[dict, dict]:
        from carpinova_agent import cad_exchange, kitchen_linear, maestro

        captured: dict[str, list] = {"maestro": [], "cad": []}
        real_consult = maestro.consult_maestro
        real_cad_exchange = cad_exchange.cad_exchange

        def consult_spy(spec: dict) -> dict:
            answer = real_consult(spec)
            captured["maestro"].append((copy.deepcopy(spec), copy.deepcopy(answer)))
            return answer

        def cad_spy(model: dict) -> dict:
            exchange = real_cad_exchange(model)
            captured["cad"].append((copy.deepcopy(model), copy.deepcopy(exchange)))
            return exchange

        with patch("carpinova_agent.maestro.consult_maestro", side_effect=consult_spy), \
                patch("carpinova_agent.kitchen_linear.consult_maestro",
                      side_effect=consult_spy), \
                patch("carpinova_agent.cad_exchange.cad_exchange",
                      side_effect=cad_spy), \
                patch("carpinova_agent.kitchen_linear.cad_exchange",
                      side_effect=cad_spy):
            result = self.call(request, project)

        expected_back = request["back_revisions"][0]["back"]
        candidates = []
        for spec, answer in captured["maestro"]:
            model = answer.get("modular")
            if type(model) is not dict:
                continue
            module = next((item for item in model.get("modules", [])
                           if item.get("module_id") == self.module_id), None)
            if type(module) is dict and module.get("back") == expected_back:
                candidates.append((spec, model))
        self.assertEqual(len(candidates), 1, "Debe capturarse la respuesta F6 revisada")
        maestro_request, f6_model = candidates[0]
        request_module = next(
            item for item in maestro_request["module_spec"]["modules"]
            if item["module_id"] == self.module_id
        )
        self.assertEqual(request_module["horizontal_divider"]["depth_mm"], divider_depth)
        self.assertEqual(maestro_request["module_spec"]["depth_mm"], 600)

        cad_candidates = []
        for model, exchange in captured["cad"]:
            module = next((item for item in model.get("modules", [])
                           if item.get("module_id") == self.module_id), None)
            boxes = [box for box in exchange.get("boxes", [])
                     if box.get("module_id") == self.module_id]
            if (type(module) is dict and module.get("back") == expected_back
                    and any(box.get("role") == "shelf_horizontal"
                            and box.get("size_xyz_mm", [None, None, None])[2]
                            == divider_depth for box in boxes)
                    and any(box.get("role") == "back_full" for box in boxes)):
                cad_candidates.append((model, exchange))
        self.assertEqual(len(cad_candidates), 1, "Debe capturarse el CADExchange revisado")
        _, exchange = cad_candidates[0]
        f6_parts = [part for part in f6_model.get("parts", [])
                    if part.get("module_id") == self.module_id
                    and part.get("role") in ("shelf_horizontal", "back_full")]
        cad_boxes = [box for box in exchange["boxes"]
                     if box.get("module_id") == self.module_id
                     and box.get("role") in ("shelf_horizontal", "back_full")]
        self.assertEqual({part["role"] for part in f6_parts},
                         {"shelf_horizontal", "back_full"})
        self.assertEqual({box["role"] for box in cad_boxes},
                         {"shelf_horizontal", "back_full"})
        f6_back = next(part for part in f6_parts if part["role"] == "back_full")
        f6_shelf = next(part for part in f6_parts
                        if part["role"] == "shelf_horizontal")
        cad_back = next(box for box in cad_boxes if box["role"] == "back_full")
        cad_shelf = next(box for box in cad_boxes
                         if box["role"] == "shelf_horizontal")
        self.assertEqual(f6_back["material_id"], expected_back["material_id"])
        self.assertEqual(f6_back["thickness_mm"], expected_back["thickness_mm"])
        self.assertEqual(f6_shelf["nominal_face_y_mm"], divider_depth)
        self.assertEqual(f6_shelf["material_id"],
                         request_module["horizontal_divider"]["material_id"])
        self.assertEqual(cad_back["material_id"], expected_back["material_id"])
        self.assertEqual(cad_back["size_xyz_mm"][2], expected_back["thickness_mm"])
        self.assertEqual(cad_shelf["material_id"], f6_shelf["material_id"])
        self.assertEqual(cad_shelf["size_xyz_mm"][2], divider_depth)
        return result, {
            "project": project,
            "module_id": self.module_id,
            "run_depth_mm": maestro_request["module_spec"]["depth_mm"],
            "requested_back": copy.deepcopy(expected_back),
            "requested_horizontal_divider_depth_mm": divider_depth,
            "f6_source_engine": f6_model.get("source_engine"),
            "f6_parts": [
                {key: part[key] for key in (
                    "piece_id", "module_id", "role", "material_id",
                    "nominal_face_x_mm", "nominal_face_y_mm", "thickness_mm",
                    "nominal_origin_xyz_mm", "source_engine", "source_formula",
                )}
                for part in f6_parts
            ],
            "cad_exchange": {
                "source_engine": exchange["source_engine"],
                "geometry_sha256": exchange["geometry_sha256"],
                "bounds_xyz_mm": exchange["bounds_xyz_mm"],
                "front_shift_mm": exchange.get("front_shift_mm", 0),
                "boxes": [
                    {key: box[key] for key in (
                        "piece_id", "module_id", "role", "material_id",
                        "origin_xyz_mm", "size_xyz_mm",
                    )}
                    for box in cad_boxes
                ],
            },
        }

    @staticmethod
    def capture_evidence(name: str, data: bytes) -> None:
        evidence_dir = os.environ.get("CARPN_H9_M3_EVIDENCE_DIR")
        if not evidence_dir:
            return
        root = Path(evidence_dir)
        if not root.is_dir():
            raise AssertionError("CARPN_H9_M3_EVIDENCE_DIR debe ser carpeta precreada")
        target = root / name
        if target.exists():
            raise AssertionError(f"No se sobrescribe evidencia existente: {target.name}")
        target.write_bytes(data)

    def test_original_and_two_tower_back_variants_generate_nominal_packages(self) -> None:
        original_request = self.spatial_request(self.review_state)
        three_mm_back = {
            "style": "inset_full", "material_id": "HDF_3_LAB",
            "thickness_mm": 3, "services_present": False,
            "grain_axis": "none",
        }
        carcass_back = {
            "style": "inset_full", "material_id": self.tower_module["material_id"],
            "thickness_mm": self.tower_module["panel_thickness_mm"],
            "services_present": False, "grain_axis": "none",
        }
        cases = (
            ("H9M3_ORIGINAL", original_request, None, None),
            ("H9M3_TORRE_3MM", self.spatial_request(
                self.review_state,
                [{**self.revision("TORRE", self.module_id, three_mm_back),
                  "horizontal_divider_depth_mm": 597}],
            ), ("TORRE_3MM.zip", three_mm_back), 597),
            ("H9M3_TORRE_CARCASS", self.spatial_request(
                self.review_state,
                [{**self.revision("TORRE", self.module_id, carcass_back),
                  "horizontal_divider_depth_mm": 582}],
            ), ("TORRE_CARCASS.zip", carcass_back), 582),
        )
        records: dict[str, dict] = {}
        cad_origins: list[dict] = []
        original_bytes: bytes | None = None
        baseline_boxes: dict[str, dict] = {}
        source_layout_sha256: str | None = None
        changed_ids = {
            f"TORRE:{self.module_id}-SHELF",
            f"TORRE:{self.module_id}-BACK_FULL",
        }
        layout_hashes: set[str] = set()

        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": output_root}
        ):
            for project, request, evidence_case, divider_depth in cases:
                with self.subTest(project=project):
                    request_before = copy.deepcopy(request)
                    if divider_depth is None:
                        result = self.call(request, project)
                    else:
                        result, source = self.call_with_cad_source(
                            request, project, divider_depth,
                        )
                        cad_origins.append(source)
                    raw, manifest, review, saved_request, html, csv_text = self.read_package(
                        Path(result["room_package_path"])
                    )
                    self.assertEqual(result["status"], "REVIEW_ONLY")
                    self.assertEqual(result["room_status"], "REVIEW_ONLY")
                    self.assertEqual(review["status"], "REVIEW_ONLY")
                    self.assertEqual(review["panel_collisions"], [])
                    self.assertEqual(review["envelope_collisions"], [])
                    if source_layout_sha256 is None:
                        source_layout_sha256 = review["source_layout_sha256"]
                    self.assertEqual(review["source_layout_sha256"], source_layout_sha256)
                    self.assertTrue(all(result[flag] is False for flag in FLAGS))
                    self.assertTrue(all(review[flag] is False for flag in FLAGS))
                    self.assertEqual(result["release"], "NO_GO")
                    self.assertEqual(manifest["release"], "NO_GO")
                    self.assertEqual(saved_request, request)
                    self.assertEqual(request, request_before)
                    self.assertEqual(manifest["layout_sha256"], result["layout_sha256"])
                    if divider_depth is None:
                        self.assertNotIn("BACK_OPTIONS_UNAPPROVED", review["warnings"])
                    else:
                        self.assertIn("BACK_OPTIONS_UNAPPROVED", review["warnings"])
                    self.assertEqual(
                        review["construction_review_by_group"]["ALTO"][
                            "wall_support_status"], "REAR_WALL_SUPPORT_PENDING"
                    )
                    self.assertEqual(
                        review["construction_review_by_group"]["ALTO"][
                            "wall_tie_mode"], "NOT_IMPLEMENTED"
                    )
                    self.assertFalse(review["construction_review_by_group"]["ALTO"][
                        "install_ready"])
                    layout_hashes.add(result["layout_sha256"])

                    boxes_by_id = {box["piece_id"]: box for box in review["world_boxes"]}
                    html_match = re.search(
                        r'<script id="scene-data" type="application/json">(.*?)</script>',
                        html, re.DOTALL,
                    )
                    self.assertIsNotNone(html_match)
                    scene = json.loads(html_match.group(1))
                    scene_boxes = {box["id"]: box for box in scene["boxes"]}
                    csv_rows = list(csv.DictReader(io.StringIO(csv_text)))
                    csv_boxes = {row["piece_id"]: row for row in csv_rows}
                    self.assertEqual(set(boxes_by_id), set(scene_boxes))
                    self.assertEqual(set(boxes_by_id), set(csv_boxes))
                    for piece_id, box in boxes_by_id.items():
                        self.assertEqual(scene_boxes[piece_id]["role"], box["role"])
                        self.assertEqual(scene_boxes[piece_id]["group"], box["group_id"])
                        self.assertEqual(scene_boxes[piece_id]["origin"], box["origin_xyz_mm"])
                        self.assertEqual(scene_boxes[piece_id]["size"], box["size_xyz_mm"])
                        row = csv_boxes[piece_id]
                        self.assertEqual(row["group_id"], box["group_id"])
                        self.assertEqual(row["role"], box["role"])
                        self.assertEqual(
                            [int(row[key]) for key in ("x_world_mm", "y_world_mm", "z_world_mm")],
                            box["origin_xyz_mm"],
                        )
                        self.assertEqual(
                            [int(row[key]) for key in (
                                "size_x_world_mm", "size_y_world_mm", "size_z_world_mm",
                            )], box["size_xyz_mm"],
                        )
                    if divider_depth is None:
                        self.assertEqual(len(raw), LEGACY_ZIP_BYTES)
                        self.assertEqual(hashlib.sha256(raw).hexdigest(), LEGACY_ZIP_SHA256)
                        self.assertEqual(result["piece_count"], 42)
                        self.assertEqual(result["layout_sha256"], LEGACY_LAYOUT_SHA256)
                        self.assertEqual(len(review["world_boxes"]), 42)
                        self.assertFalse(any(box["role"].startswith("back_")
                                             for box in review["world_boxes"]))
                        baseline_boxes = {
                            piece_id: box for piece_id, box in boxes_by_id.items()
                            if piece_id not in changed_ids
                        }
                        original_bytes = raw
                        records[project] = {
                            "status": result["status"],
                            "layout_sha256": result["layout_sha256"],
                            "source_layout_sha256": review["source_layout_sha256"],
                            "piece_count": result["piece_count"],
                            "zip_sha256": hashlib.sha256(raw).hexdigest(),
                            "zip_bytes": len(raw),
                            "back_piece_count": 0,
                            "flags": {flag: False for flag in FLAGS},
                        }
                        self.capture_evidence("ORIGINAL.zip", raw)
                    else:
                        expected_back = evidence_case[1]
                        self.assertEqual(result["piece_count"], 43)
                        self.assertEqual(len(review["world_boxes"]), 43)
                        self.assertEqual(
                            len([box for box in review["world_boxes"]
                                 if box["group_id"] == "TORRE"
                                 and box["role"].startswith("back_")]), 1,
                        )
                        shelf_id = f"TORRE:{self.module_id}-SHELF"
                        back_id = f"TORRE:{self.module_id}-BACK_FULL"
                        shelf = boxes_by_id[shelf_id]
                        back = boxes_by_id[back_id]
                        self.assertEqual(shelf["role"], "shelf_horizontal")
                        self.assertEqual(back["role"], "back_full")
                        self.assertEqual(shelf["size_xyz_mm"], [564, 18, divider_depth])
                        self.assertEqual(back["size_xyz_mm"], [564, 2064,
                                                               expected_back["thickness_mm"]])
                        self.assertEqual(
                            shelf["origin_xyz_mm"][2] + shelf["size_xyz_mm"][2],
                            back["origin_xyz_mm"][2],
                        )
                        self.assertEqual(
                            {key: value for key, value in boxes_by_id.items()
                             if key not in changed_ids},
                            baseline_boxes,
                        )
                        self.assertEqual(
                            request["back_revisions"][0]["horizontal_divider_depth_mm"],
                            divider_depth,
                        )
                        records[project] = {
                            "status": result["status"],
                            "requested_back": expected_back,
                            "horizontal_divider_depth_mm": divider_depth,
                            "module_id": self.module_id,
                            "layout_sha256": result["layout_sha256"],
                            "source_layout_sha256": review["source_layout_sha256"],
                            "piece_count": result["piece_count"],
                            "back_piece_count": 1,
                            "back_world_box": back,
                            "shelf_world_box": shelf,
                            "zip_sha256": hashlib.sha256(raw).hexdigest(),
                            "zip_bytes": len(raw),
                            "flags": {flag: False for flag in FLAGS},
                        }
                        evidence_name = evidence_case[0]
                        self.capture_evidence(evidence_name, raw)

        self.assertEqual(len(layout_hashes), 3)
        self.assertIsNotNone(source_layout_sha256)
        self.assertEqual({item["source_layout_sha256"] for item in records.values()},
                         {source_layout_sha256})
        self.assertEqual(len(cad_origins), 2)
        evidence_dir = os.environ.get("CARPN_H9_M3_EVIDENCE_DIR")
        if evidence_dir:
            self.capture_evidence(
                "public_calls.json",
                (json.dumps({"tool": "carpinova_generar_borrador:kitchen_spatial_v1",
                             "calls": records,
                             "legacy_flags": {flag: False for flag in FLAGS}},
                            ensure_ascii=False, sort_keys=True,
                            indent=2) + "\n").encode("utf-8"),
            )
            self.capture_evidence(
                "cad_origin.json",
                (json.dumps({"source": "captured from Maestro F6 and CADExchange "
                                      "inside the three public API tests",
                             "variants": cad_origins},
                            ensure_ascii=False, sort_keys=True,
                            indent=2) + "\n").encode("utf-8"),
            )

    def test_untrusted_revisions_fail_without_new_or_modified_zip(self) -> None:
        valid_revision = self.revision("TORRE", self.module_id, {
            "style": "inset_full", "material_id": "HDF_3_LAB",
            "thickness_mm": 3, "services_present": False, "grain_axis": "none",
        })
        valid_revision["horizontal_divider_depth_mm"] = 597
        base_request = self.spatial_request(self.review_state)
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": output_root}
        ):
            prior = self.call(base_request, "H9M3_NEGATIVE_KEEP")
            prior_path = Path(prior["room_package_path"])
            prior_bytes = prior_path.read_bytes()
            existing = {path.name for path in Path(output_root).glob("*-room-review.zip")}
            invalid: list[tuple[str, dict]] = []

            invalid.append(("empty", self.spatial_request(
                self.review_state, [])))
            invalid.append(("too-long", self.spatial_request(
                self.review_state, [valid_revision] * 13)))
            invalid.append(("duplicate", self.spatial_request(
                self.review_state, [valid_revision, valid_revision])))
            invalid.append(("foreign-group", self.spatial_request(
                self.review_state, [self.revision("OTHER", self.module_id,
                                                  valid_revision["back"])])))
            invalid.append(("cross-group-module", self.spatial_request(
                self.review_state, [self.revision("BAJO", self.module_id,
                                                  valid_revision["back"])])))
            extra = copy.deepcopy(valid_revision)
            extra["exchange"] = {}
            invalid.append(("extra-revision-field", self.spatial_request(
                self.review_state, [extra])))
            invalid.append(("boolean-thickness", self.spatial_request(
                self.review_state, [self.revision("TORRE", self.module_id, {
                    **valid_revision["back"], "thickness_mm": True,
                })])))
            invalid.append(("full-back-with-services", self.spatial_request(
                self.review_state, [self.revision("TORRE", self.module_id, {
                    **valid_revision["back"], "services_present": True,
                })])))
            invalid.append(("missing-explicit-divider-depth", self.spatial_request(
                self.review_state,
                [self.revision("TORRE", self.module_id, valid_revision["back"])],
            )))
            boolean_depth = copy.deepcopy(valid_revision)
            boolean_depth["horizontal_divider_depth_mm"] = True
            invalid.append(("boolean-divider-depth", self.spatial_request(
                self.review_state, [boolean_depth])))
            extending_depth = copy.deepcopy(valid_revision)
            extending_depth["horizontal_divider_depth_mm"] = 601
            invalid.append(("divider-depth-expands-existing", self.spatial_request(
                self.review_state, [extending_depth])))
            colliding_depth = copy.deepcopy(valid_revision)
            colliding_depth["horizontal_divider_depth_mm"] = 598
            invalid.append(("divider-depth-intersects-back", self.spatial_request(
                self.review_state, [colliding_depth])))
            no_last_valid = copy.deepcopy(self.review_state)
            no_last_valid["last_valid"] = None
            invalid.append(("no-last-valid", self.spatial_request(
                no_last_valid, [valid_revision])))
            pending = copy.deepcopy(self.review_state)
            pending["pending_candidate"] = {
                "status": "PENDING_REVIEW",
                "base_layout_sha256": pending["last_valid"]["layout_sha256"],
                "candidate_layout_sha256": "0" * 64,
            }
            invalid.append(("pending-candidate", self.spatial_request(
                pending, [valid_revision])))
            client_geometry = self.spatial_request(self.review_state, [valid_revision])
            client_geometry["world_boxes"] = []
            invalid.append(("client-world-boxes", client_geometry))

            for index, (label, request) in enumerate(invalid):
                project = f"H9M3_NEG_{index:02d}"
                with self.subTest(case=label), self.assertRaises(ValueError):
                    self.call(request, project)
                self.assertFalse(
                    (Path(output_root) / f"{project}-room-review.zip").exists()
                )
                self.assertEqual(
                    {path.name for path in Path(output_root).glob("*-room-review.zip")},
                    existing,
                )
                self.assertEqual(prior_path.read_bytes(), prior_bytes)

            overwrite_request = self.spatial_request(self.review_state, [valid_revision])
            with self.assertRaises(ValueError):
                self.call(overwrite_request, "H9M3_NEGATIVE_KEEP")
            self.assertEqual(prior_path.read_bytes(), prior_bytes)
            self.assertEqual(
                {path.name for path in Path(output_root).glob("*-room-review.zip")},
                existing,
            )


if __name__ == "__main__":
    unittest.main()
