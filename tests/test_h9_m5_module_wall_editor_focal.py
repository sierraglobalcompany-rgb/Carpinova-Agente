from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from carpinova_agent import room_3d_review, room_spatial
from carpinova_agent.kitchen_linear import _build
from carpinova_agent.mcp_bridge import carpinova_generar_borrador
from test_kitchen_linear import make_l1


ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "04507fb76455b2bf1c96d94c5ba05cbc074ca7d7"
FIXTURE = ROOT / "tests" / "fixtures" / "room_review_d19" / "f9a_room_public.json"
MEMBERS = {
    "LEER_PRIMERO.txt", "01-visor-3d.html", "02-planta.svg",
    "03-seccion.svg", "04-habitacion.json", "05-solicitud.json",
    "06-paneles-en-escena.csv", "MANIFEST.json",
}
FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready",
    "purchase_ready", "can_generate_f7c",
)
EXPECTED_LAYOUTS = {
    "D19_42": "fe5c492e40cb76a42fa2dba619282c4ee7544dd20b89a67782774de438d18c15",
    "D19_COMBINED_46": "b1db6d9b3f4089f0a82e12ef5cd93246160ca51ddfa2ee6721f9233f7c66ad5f",
    "D19_ROOM_LAYOUT": "b80c971e0a3e7c88d7f3dcaa28747d250e01256faca72eb3a9d16fca9c86a0bd",
}


def wall_choice(group: str, module: str, back: str, system: str,
                support: str = "keep_existing", substrate: str = "unknown") -> dict:
    return {
        "group_id": group, "module_id": module, "back_choice": back,
        "wall_system": system, "support_choice": support,
        "wall_substrate": substrate,
    }


def _stable_boxes(review: dict) -> list[tuple]:
    return sorted((box["group_id"], box["piece_id"], box["role"],
                   tuple(box["origin_xyz_mm"]), tuple(box["size_xyz_mm"]))
                  for box in review["world_boxes"])


def extract_d19(archive_path: Path, destination: Path) -> dict[str, bytes]:
    destination.mkdir(parents=True, exist_ok=False)
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise AssertionError("CRC D19 inválido")
        names = set(archive.namelist())
        if names != MEMBERS:
            raise AssertionError(f"Miembros D19 inesperados: {sorted(names)}")
        files = {name: archive.read(name) for name in names}
    manifest = json.loads(files["MANIFEST.json"])
    if set(manifest.get("files", {})) != MEMBERS - {"MANIFEST.json"}:
        raise AssertionError("El manifiesto D19 debe registrar exactamente siete archivos")
    for name, info in manifest["files"].items():
        data = files[name]
        if (len(data) != info["bytes"]
                or hashlib.sha256(data).hexdigest() != info["sha256"]):
            raise AssertionError(f"Manifiesto D19 incoherente: {name}")
    for name, content in files.items():
        if "/" in name or "\\" in name:
            raise AssertionError("Ruta anidada en D19")
        (destination / name).write_bytes(content)
    return files


class H9M5ModuleWallEditorFocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("CARPN_H9_M5_DELIVERY_ROOT")
        if not configured:
            raise RuntimeError("CARPN_H9_M5_DELIVERY_ROOT debe apuntar a staging externo nuevo")
        cls.delivery = Path(configured).resolve()
        if cls.delivery.is_symlink():
            raise RuntimeError("No se acepta staging mediante symlink")
        if cls.delivery.exists() and any(cls.delivery.iterdir()):
            raise RuntimeError("Staging no vacío; no se sobrescribe evidencia anterior")
        cls.delivery.mkdir(parents=True, exist_ok=True)
        cls.qa = cls.delivery / "QA"
        cls.qa.mkdir(exist_ok=False)
        cls._package_temp = tempfile.TemporaryDirectory(prefix="carpn-h9-m5-r2-d19-")
        cls.package_dir = Path(cls._package_temp.name).resolve()
        cls.review_state = make_l1()["review_state"]
        cls.base_request = {
            "review_kind": "kitchen_spatial_v1",
            "review_state": copy.deepcopy(cls.review_state), "service_zones": [],
        }
        cls.rebuilt = _build(copy.deepcopy(cls.review_state["working"]))
        tower_request = cls.rebuilt["_reviews"]["TORRE"]["_trusted_nominal_request"]
        tower_module = tower_request["module_spec"]["modules"][0]
        cls.tower_id = tower_module["module_id"]
        cls.carcass_back = {
            "style": "inset_full", "material_id": tower_module["material_id"],
            "thickness_mm": tower_module["panel_thickness_mm"],
            "services_present": False, "grain_axis": "none",
        }
        cls.wall_revisions = [
            wall_choice("BAJO", "KITCHEN_RIGHT", "keep_existing",
                        "floor_furniture_anti_tip"),
            wall_choice("TORRE", cls.tower_id, "keep_existing",
                        "floor_furniture_anti_tip"),
        ]
        cls.back_revisions = [
            {
                "group_id": "BAJO", "module_id": "KITCHEN_LEFT",
                "back": {
                    "style": "inset_two_strips", "material_id": "HDF_3_LAB",
                    "thickness_mm": 3, "services_present": False,
                    "top_strip_height_mm": 100, "bottom_strip_height_mm": 100,
                    "grain_axis": "none",
                },
            },
            {
                "group_id": "ALTO", "module_id": "KITCHEN_1", "back": "none",
                "wall_rear_ties": {
                    "style": "direct_pair_review", "material_id": "MELAMINA_15",
                    "thickness_mm": 15, "tie_height_mm": 80,
                },
            },
        ]
        cls.requests = {
            "D19_42": {**copy.deepcopy(cls.base_request),
                       "wall_review_revisions": copy.deepcopy(cls.wall_revisions)},
            "D19_COMBINED_46": {
                **copy.deepcopy(cls.base_request),
                "back_revisions": copy.deepcopy(cls.back_revisions),
                "wall_review_revisions": [
                    *copy.deepcopy(cls.wall_revisions),
                    wall_choice("ALTO", "KITCHEN_1", "keep_existing",
                                "direct_rear_tie"),
                ],
            },
        }
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.requests["D19_ROOM_LAYOUT"] = copy.deepcopy(fixture["request"])
        cls.requests["D19_ROOM_LAYOUT"]["wall_review_revisions"] = []

        cls.results: dict[str, dict] = {}
        cls.files: dict[str, dict[str, bytes]] = {}
        for key, request in cls.requests.items():
            result = cls._generate(request, f"H9M5R2_{key}")
            cls.results[key] = result
            cls.files[key] = extract_d19(
                Path(result["room_package_path"]), cls.delivery / key,
            )
        (cls.qa / "TOOLS.json").write_text(
            json.dumps({key: {
                field: result.get(field) for field in (
                    "status", "room_status", "proyecto", "zip_sha256",
                    "layout_sha256", "piece_count", "release", *FLAGS,
                )
            } for key, result in cls.results.items()}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )

    @classmethod
    def _generate(cls, request: dict, project: str) -> dict:
        with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": str(cls.package_dir)}):
            return carpinova_generar_borrador(
                solicitud_json=json.dumps(request, ensure_ascii=False),
                proyecto=project, incluir_planos=False, seccion_y_mm=350,
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._package_temp.cleanup()

    def test_three_public_d19_products_and_legacy_renderer(self) -> None:
        reviews = {
            key: json.loads(files["04-habitacion.json"])
            for key, files in self.files.items()
        }
        expected_counts = {"D19_42": 42, "D19_COMBINED_46": 46,
                           "D19_ROOM_LAYOUT": 9}
        for key, review in reviews.items():
            result = self.results[key]
            self.assertEqual(review["piece_count"], expected_counts[key])
            self.assertEqual(result["piece_count"], expected_counts[key])
            self.assertEqual(review["layout_sha256"], EXPECTED_LAYOUTS[key])
            self.assertEqual(result["layout_sha256"], EXPECTED_LAYOUTS[key])
            self.assertEqual(review["release"], "NO_GO")
            self.assertEqual(result["release"], "NO_GO")
            self.assertEqual(review["manufacturing_holes"], []) if "manufacturing_holes" in review else None
            for flag in FLAGS:
                self.assertIs(review[flag], False)
                self.assertIs(result[flag], False)
            self.assertEqual(set(self.files[key]), MEMBERS)
            csv_rows = list(csv.reader(io.StringIO(
                self.files[key]["06-paneles-en-escena.csv"].decode("utf-8")
            )))
            self.assertNotIn("material_id", csv_rows[0])
            self.assertEqual(len(csv_rows) - 1, expected_counts[key])

        legacy_review = room_spatial.review_room_from_kitchen_state(
            copy.deepcopy(self.base_request)
        )
        base_source = subprocess.run(
            ["git", "show", f"{BASE_SHA}:carpinova_agent/room_3d_review.py"],
            cwd=ROOT,
            env={key: value for key, value in os.environ.items()
                 if not key.startswith("GIT_")},
            check=True, capture_output=True,
        ).stdout.decode("utf-8")
        baseline = types.ModuleType("carpinova_agent.room_3d_review_h9m5_r2_base")
        baseline.__package__ = "carpinova_agent"
        exec(compile(base_source, "room_3d_review.py@04507fb", "exec"), baseline.__dict__)
        self.assertEqual(
            room_3d_review.render_room_3d_html(legacy_review).encode("utf-8"),
            baseline.render_room_3d_html(legacy_review).encode("utf-8"),
        )
        legacy_html = room_3d_review.render_room_3d_html(legacy_review).encode("utf-8")
        self.assertNotIn(b"moduleReview", legacy_html)
        self.assertIn(b"moduleReview", self.files["D19_42"]["01-visor-3d.html"])

        selected = reviews["D19_42"]
        self.assertEqual(_stable_boxes(selected), _stable_boxes(legacy_review))
        self.assertEqual(selected["source_layout_sha256"],
                         self.rebuilt["layout_sha256"])
        self.assertNotEqual(selected["source_layout_sha256"],
                            selected["layout_sha256"])
        index = {(item["group_id"], item["module_id"]): item
                 for item in selected["module_index"]}
        reviews_by_key = {(item["group_id"], item["module_id"]): item
                          for item in selected["wall_review_by_module"]}
        self.assertEqual(set(reviews_by_key), {
            ("BAJO", "KITCHEN_RIGHT"), ("TORRE", self.tower_id),
        })
        allowed_roles = {"top", "left_side", "right_side", "wall_rear_upper_tie",
                         "wall_rear_lower_tie", "upper_rear_tie", "lower_rear_tie"}
        boxes_by_id = {box["piece_id"]: box for box in selected["world_boxes"]}
        for key, row in reviews_by_key.items():
            candidates = index[key]["candidate_piece_ids"]
            self.assertEqual(row["candidate_piece_ids"], candidates)
            self.assertTrue(all(boxes_by_id[pid]["role"] in allowed_roles
                                for pid in candidates))
            self.assertFalse(row["install_ready"])
            self.assertEqual(row["manufacturing_holes"], [])
            self.assertEqual(row["wall_system"], "floor_furniture_anti_tip")
            actual_support = index[key]["support_status"]
            if actual_support in {"floor", "legs", "plinth"}:
                self.assertEqual(row["support_function"], "stability_only")
            elif actual_support == "wall":
                self.assertEqual(row["status"], "INCOMPATIBLE_FOR_SUSPENSION")
            else:
                self.assertEqual(row["support_function"], "pending")
        tower_candidates = [boxes_by_id[pid]["role"]
                            for pid in index[("TORRE", self.tower_id)]["candidate_piece_ids"]]
        self.assertIn("top", tower_candidates)
        self.assertIn("left_side", tower_candidates)
        self.assertIn("right_side", tower_candidates)

        combined = reviews["D19_COMBINED_46"]
        self.assertEqual(combined["source_layout_sha256"],
                         self.rebuilt["layout_sha256"])
        self.assertNotEqual(combined["source_layout_sha256"],
                            combined["layout_sha256"])
        alto = next(item for item in combined["wall_review_by_module"]
                    if item["group_id"] == "ALTO")
        self.assertEqual(alto["wall_system"], "direct_rear_tie")
        self.assertEqual(alto["support_function"], "wall_suspension")
        self.assertIn("TIE_POSITION_AND_CLEARANCE_PENDING", alto["constraints"])
        self.assertIn("WALL_SUBSTRATE_UNKNOWN", alto["constraints"])
        combined_tower = [box for box in combined["world_boxes"]
                          if box["group_id"] == "TORRE"]
        legacy_tower = [box for box in legacy_review["world_boxes"]
                        if box["group_id"] == "TORRE"]
        self.assertEqual(_stable_boxes({"world_boxes": combined_tower}),
                         _stable_boxes({"world_boxes": legacy_tower}))
        # The three drawers belong to BAJO/KITCHEN_RIGHT, not TORRE.
        combined_drawers = [box for box in combined["world_boxes"]
                            if box["role"].startswith("drawer_")]
        legacy_drawers = [box for box in legacy_review["world_boxes"]
                          if box["role"].startswith("drawer_")]
        self.assertEqual(len(combined_drawers), 18)
        self.assertTrue(all(box["group_id"] == "BAJO"
                            and box["module_id"] == "KITCHEN_RIGHT"
                            for box in combined_drawers))
        self.assertEqual(_stable_boxes({"world_boxes": combined_drawers}),
                         _stable_boxes({"world_boxes": legacy_drawers}))

        empty = reviews["D19_ROOM_LAYOUT"]
        self.assertEqual(empty["wall_review_by_module"], [])
        self.assertTrue(all(item["candidate_piece_ids"] is not None
                            for item in empty["module_index"]))
        self.assertIn("moduleReview", self.files["D19_ROOM_LAYOUT"]["01-visor-3d.html"].decode())
        (self.qa / "FOCAL.txt").write_text(
            "PUBLIC_TOOL=PASS · tres llamadas; D19 42/46/9 y layout SHA exactos.\n"
            "D19 internos: 8 rutas, CRC y manifiesto 7/7 SHA256/bytes.\n"
            "Revisión ausente: HTML legado byte idéntico a base 04507fb con el mismo objeto en memoria.\n"
            "D19_42: mismas piezas/roles/orígenes/tamaños; candidatos por rol y propietario reales.\n"
            "ALTO: amarre/suspensión pendientes; TORRE y cajones conservan identidad.\n"
            "Gates físicos falsos; release NO_GO.\n",
            encoding="utf-8", newline="\n",
        )

    def test_empty_editor_material_and_ownership_guards(self) -> None:
        empty = json.loads(self.files["D19_ROOM_LAYOUT"]["04-habitacion.json"])
        payload = room_3d_review._payload(empty)
        self.assertEqual(payload["wall_reviews"], [])
        none_review = copy.deepcopy(empty)
        none_review["wall_review_by_module"] = None
        with self.assertRaises(room_3d_review.RoomViewerError):
            room_3d_review._payload(none_review)

        bad_source = copy.deepcopy(self.requests["D19_ROOM_LAYOUT"])
        bad_source["wall_review_revisions"] = None
        from carpinova_agent.room_review_package import (
            RoomPackageError, _validate_source_request,
        )
        with self.assertRaises(RoomPackageError):
            _validate_source_request(bad_source)

        model = {
            "modules": [{"module_id": "M", "part_ids": ["M-TOP", "M-BOTTOM"],
                         "support": "floor", "panel_thickness_mm": 18}],
            "parts": [
                {"piece_id": "M-TOP", "module_id": "M", "role": "top"},
                {"piece_id": "M-BOTTOM", "module_id": "M", "role": "bottom"},
            ],
        }
        exchange = {"boxes": [
            {"piece_id": "M-TOP", "module_id": "M", "role": "top"},
            {"piece_id": "M-BOTTOM", "module_id": "M", "role": "bottom"},
        ]}
        result = {"world_boxes": [
            {"group_id": "G", "piece_id": "G:M-TOP", "origin_xyz_mm": [0, 0, 0],
             "size_xyz_mm": [500, 18, 400], "role": "top"},
            {"group_id": "G", "piece_id": "G:M-BOTTOM", "origin_xyz_mm": [0, 0, 0],
             "size_xyz_mm": [500, 18, 400], "role": "bottom"},
        ]}
        assembly = [{"group_id": "G", "exchange": exchange}]
        contexts = room_spatial._module_index(result, {"G": model}, assembly)
        self.assertEqual(contexts[("G", "M")]["index"]["candidate_piece_ids"], ["G:M-TOP"])
        self.assertEqual(result["world_boxes"][0]["module_id"], "M")
        bad_model = copy.deepcopy(model)
        bad_model["parts"][0]["module_id"] = "OTHER"
        with self.assertRaises(ValueError):
            room_spatial._module_index(copy.deepcopy(result), {"G": bad_model}, assembly)
        bad_exchange = copy.deepcopy(assembly)
        bad_exchange[0]["exchange"]["boxes"][0]["role"] = "left_side"
        with self.assertRaises(ValueError):
            room_spatial._module_index(copy.deepcopy(result), {"G": model}, bad_exchange)

        selected = json.loads(self.files["D19_42"]["04-habitacion.json"])
        selected_index = selected["module_index"][0]
        bad_candidate = copy.deepcopy(selected)
        noncandidate = next(box["piece_id"] for box in bad_candidate["world_boxes"]
                            if box["group_id"] == selected_index["group_id"]
                            and box["role"] not in {"top", "left_side", "right_side",
                                "wall_rear_upper_tie", "wall_rear_lower_tie",
                                "upper_rear_tie", "lower_rear_tie"})
        bad_candidate["module_index"][0]["candidate_piece_ids"].append(noncandidate)
        with self.assertRaises(room_3d_review.RoomViewerError):
            room_3d_review._payload(bad_candidate)
        bad_review_candidate = copy.deepcopy(selected)
        bad_review_candidate["wall_review_by_module"][0]["candidate_piece_ids"] = []
        with self.assertRaises(room_3d_review.RoomViewerError):
            room_3d_review._payload(bad_review_candidate)

        def material_review(back: dict) -> dict:
            request = copy.deepcopy(self.base_request)
            request["back_revisions"] = [{
                "group_id": "TORRE", "module_id": self.tower_id,
                "back": copy.deepcopy(back), "horizontal_divider_depth_mm": (
                    582 if back["material_id"] == self.carcass_back["material_id"] else 597
                ),
            }]
            request["wall_review_revisions"] = [wall_choice(
                "TORRE", self.tower_id, "inset_carcass_material_review",
                "floor_furniture_anti_tip", "keep_existing", "unknown",
            )]
            return room_spatial.review_room_from_kitchen_state(request)

        self.assertEqual(self.carcass_back["material_id"], "MELAMINA_18")
        self.assertEqual(self.carcass_back["thickness_mm"], 18)
        matched_review = material_review(self.carcass_back)
        matched = matched_review["wall_review_by_module"][0]
        self.assertEqual(matched["back_geometry_status"], "MODELED_NOMINAL")
        self.assertEqual(matched["status"], "SELECTABLE_CONCEPT_ONLY")
        self.assertFalse(matched["install_ready"])
        mismatch_back = {
            "style": "inset_full", "material_id": "HDF_3_LAB",
            "thickness_mm": 3, "services_present": False, "grain_axis": "none",
        }
        mismatch = material_review(mismatch_back)["wall_review_by_module"][0]
        self.assertEqual(mismatch["back_geometry_status"], "NEEDS_BACK_SPEC")
        self.assertEqual(mismatch["status"], "NEEDS_BACK_SPEC")
        unknown = room_spatial._back_geometry_status(
            "inset_carcass_material_review",
            {"back": copy.deepcopy(self.carcass_back)}, None, {}, {},
        )
        self.assertEqual(unknown, "NEEDS_DATA")
        (self.qa / "MATERIAL.json").write_text(json.dumps({
            "carcass_material_choice": matched["back_geometry_status"],
            "independent_installation_status": matched["status"],
            "install_ready": matched["install_ready"],
            "actual_alternative_mismatch": mismatch["back_geometry_status"],
            "unknown_carcass_material": unknown,
            "back_revision": self.carcass_back,
            "divider_depth_mm": 582,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    def test_browser_focus_candidates_placeholder_and_intent_download(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            (self.qa / "BROWSER_BLOCKED.txt").write_text(
                f"BROWSER=BLOCKED · Playwright no disponible: {exc}\n",
                encoding="utf-8", newline="\n",
            )
            self.skipTest("Playwright local no está disponible")

        errors, console_errors, requests = [], [], []
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            try:
                playwright.stop()
            except (UnboundLocalError, Exception):
                pass
            (self.qa / "BROWSER_BLOCKED.txt").write_text(
                f"BROWSER=BLOCKED · Chromium local no inició: {type(exc).__name__}: {exc}\n",
                encoding="utf-8", newline="\n",
            )
            self.skipTest("Chromium local no está disponible")

        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: console_errors.append(message.text)
                if message.type == "error" else None)
        page.on("request", lambda request: requests.append(request.url)
                if request.url.startswith(("http://", "https://")) else None)
        try:
            page.set_content(self.files["D19_42"]["01-visor-3d.html"].decode("utf-8"),
                             wait_until="load")
            page.locator("#zoom").evaluate(
                "el=>{el.value='120';el.dispatchEvent(new Event('input',{bubbles:true}))}"
            )
            page.evaluate("yaw=135;activePreset=null;updateCameraReadout();render()")
            page.locator("#cutEnabled").check()
            cut_before = page.locator("#cutHeight").input_value()
            page.select_option("#modulePicker", label="BAJO · KITCHEN_RIGHT")
            page.get_by_role("button", name="Enfocar mueble").click()
            focus = page.evaluate("""() => ({
              key:focusedModuleKey, zoom:document.querySelector('#zoom').value,
              yaw,elevation,cut:document.querySelector('#cutEnabled').checked,
              cutHeight:document.querySelector('#cutHeight').value,
              fullSpan:fullFrameMax.map((v,i)=>v-fullFrameMin[i]),
              focusSpan:frameMax.map((v,i)=>v-frameMin[i]),
              expected:movementFrame(data.boxes.filter(b=>b.group==='BAJO'&&b.module_id==='KITCHEN_RIGHT'),
                moduleIndex.find(m=>m.group_id==='BAJO'&&m.module_id==='KITCHEN_RIGHT').bounds_origin_xyz_mm,
                moduleIndex.find(m=>m.group_id==='BAJO'&&m.module_id==='KITCHEN_RIGHT').bounds_origin_xyz_mm.map((v,i)=>v+moduleIndex.find(m=>m.group_id==='BAJO'&&m.module_id==='KITCHEN_RIGHT').bounds_size_xyz_mm[i])),
              image:(()=>{const i=document.querySelector('#scene image');return i&&{
                module:i.getAttribute('data-focused-module'),opacity:i.getAttribute('data-neighbor-opacity'),
                overrides:Number(i.getAttribute('data-focused-priority-overrides'))}})(),
              pickedOutside:[...pickBuffer.ids].some(n=>n>=0&&
                (data.boxes[n].group+'::'+data.boxes[n].module_id)!==focusedModuleKey)
            })""")
            self.assertEqual(focus["key"], "BAJO::KITCHEN_RIGHT")
            self.assertEqual(focus["zoom"], "100",
                             f"zoom de foco sin aplicar; errores JS: {errors!r}")
            self.assertEqual((focus["yaw"], focus["elevation"]), (135, 35))
            self.assertTrue(focus["cut"])
            self.assertEqual(focus["cutHeight"], cut_before)
            self.assertLess(focus["focusSpan"][0], focus["fullSpan"][0])
            self.assertEqual(focus["focusSpan"],
                             [focus["expected"]["max"][i]-focus["expected"]["min"][i]
                              for i in range(3)])
            self.assertEqual(focus["image"]["module"], focus["key"])
            self.assertEqual(focus["image"]["opacity"], "0.20")
            self.assertGreater(focus["image"]["overrides"], 0)
            self.assertFalse(focus["pickedOutside"])

            motion = page.evaluate("""() => {
              const item=moduleIndex.find(m=>m.group_id==='BAJO'&&m.module_id==='KITCHEN_RIGHT');
              const boxes=data.boxes.filter(b=>b.group===item.group_id&&b.module_id===item.module_id);
              const points=[];
              for(const b of boxes){const [x,y,z]=b.origin,[w,h,d]=b.size;
                if(b.role==='front_left'||b.role==='front_right'){
                  const left=b.role==='front_left',hx=left?x:x+w,hz=z+d/2,turn=left?1:-1,a=turn*Math.PI/2,c=Math.cos(a),s=Math.sin(a);
                  for(const xx of [x,x+w])for(const yy of [y,y+h])for(const zz of [z,z+d]){const dx=xx-hx,dz=zz-hz;points.push([hx+dx*c+dz*s,yy,hz-dx*s+dz*c])}
                }
                const drawer=drawerByPiece.get(b.id);if(drawer){const travel=drawer.depth_mm*.2;for(const xx of [x,x+w])for(const yy of [y,y+h])for(const zz of [z,z+d])points.push([xx,yy,zz-travel])}
              }
              return points.every(p=>p.every((v,i)=>v>=frameMin[i]-1e-6&&v<=frameMax[i]+1e-6));
            }""")
            self.assertTrue(motion)
            candidates = page.locator("#candidateButtons button")
            self.assertGreater(candidates.count(), 0)
            self.assertFalse(any(word in " ".join(candidates.all_text_contents()).lower()
                                 for word in ("bottom", "drawer", "front_")))
            candidates.first.click()
            selected_bajo = page.evaluate("""() => ({key:selectedModuleKey,focus:focusedModuleKey,
              selected,owner:data.boxes.find(b=>b.id===selected)?.module_id,
              overrides:Number(document.querySelector('#scene image').getAttribute('data-focused-priority-overrides'))})""")
            self.assertEqual(selected_bajo["key"], "BAJO::KITCHEN_RIGHT")
            self.assertEqual(selected_bajo["focus"], selected_bajo["key"])
            self.assertEqual(selected_bajo["owner"], "KITCHEN_RIGHT")
            self.assertIn("KITCHEN_RIGHT", selected_bajo["selected"])
            page.screenshot(path=str(self.delivery / "QA" / "FOCO_BAJO.png"), full_page=True)

            page.get_by_role("button", name="Preparar revisión JSON").click()
            proposal = json.loads(page.locator("#wallIntentPreview").inner_text())
            self.assertEqual(set(proposal), {
                "group_id", "module_id", "back_choice", "wall_system",
                "support_choice", "wall_substrate",
            })
            with page.expect_download() as download_info:
                page.locator("#downloadWallIntent").click()
            download = download_info.value
            intent_path = self.delivery / "QA" / "INTENCION_DESCARGADA.json"
            download.save_as(intent_path)
            self.assertEqual(json.loads(intent_path.read_text(encoding="utf-8")), proposal)
            self.assertEqual(len(proposal), 6)

            page.select_option("#modulePicker", label=f"TORRE · {self.tower_id}")
            self.assertEqual(page.evaluate("focusedModuleKey"), "")
            tower_candidates = page.locator("#candidateButtons button")
            self.assertGreater(tower_candidates.count(), 0)
            tower_candidates.first.click()
            selected_tower = page.evaluate("""() => ({key:selectedModuleKey,focus:focusedModuleKey,
              selected,owner:data.boxes.find(b=>b.id===selected)?.group})""")
            self.assertEqual(selected_tower["key"], f"TORRE::{self.tower_id}")
            self.assertEqual(selected_tower["focus"], selected_tower["key"])
            self.assertEqual(selected_tower["owner"], "TORRE")
            page.screenshot(path=str(self.delivery / "QA" / "FOCO_TORRE.png"), full_page=True)

            # set_content writes into the current Document; reset its JS global scope.
            page.goto("about:blank")
            page.set_content(self.files["D19_COMBINED_46"]["01-visor-3d.html"].decode("utf-8"),
                             wait_until="load")
            page.select_option("#modulePicker", label="ALTO · KITCHEN_1")
            alto = page.evaluate("""() => {const r=wallReviews.find(x=>x.group_id==='ALTO');return {
              system:r.wall_system,support:r.support_function,back:r.back_geometry_status,
              constraints:r.constraints,install:r.install_ready,
              supportText:document.querySelector('#supportReviewStatus').textContent,
              wallText:document.querySelector('#wallReviewStatus').textContent
            }}""")
            self.assertEqual(alto["system"], "direct_rear_tie")
            self.assertEqual(alto["support"], "wall_suspension")
            self.assertIn("TIE_POSITION_AND_CLEARANCE_PENDING", alto["constraints"])
            self.assertIn("Apoyo real declarado: wall", alto["supportText"])
            self.assertIn(alto["back"], page.locator("#backGeometryStatus").inner_text())
            self.assertIn("CONTENT-CPNC-2025-P0141-002", alto["wallText"])
            self.assertFalse(alto["install"])

            page.goto("about:blank")
            page.set_content(self.files["D19_ROOM_LAYOUT"]["01-visor-3d.html"].decode("utf-8"),
                             wait_until="load")
            self.assertTrue(page.locator("#modulePicker").is_visible())
            entry_state = page.evaluate("""() => ({reviewCount:wallReviews.length,
              placeholder:modulePicker.value,editor:document.querySelector('#moduleReview')!==null,
              candidates:moduleIndex.reduce((n,m)=>n+m.candidate_piece_ids.length,0)})""")
            self.assertEqual(entry_state["reviewCount"], 0)
            self.assertEqual(entry_state["placeholder"], "")
            self.assertTrue(entry_state["editor"])
            self.assertGreater(entry_state["candidates"], 0)
            page.select_option("#modulePicker", label="CIEGO · CIEGO")
            self.assertGreater(page.locator("#candidateButtons button").count(), 0)
            page.select_option("#backChoice", value="keep_existing")
            page.select_option("#wallSystem", value="none")
            page.select_option("#supportChoice", value="floor_direct")
            page.select_option("#wallSubstrate", value="unknown")
            page.get_by_role("button", name="Preparar revisión JSON").click()
            old_blob = page.evaluate("wallObjectUrl")
            self.assertTrue(old_blob)
            # Observe the actual revocation without intentionally producing a
            # console/network error when fetching a revoked or opaque-origin URL.
            page.evaluate("""() => {
              window.__carpn_revoked_urls = [];
              const original = URL.revokeObjectURL.bind(URL);
              URL.revokeObjectURL = url => {
                window.__carpn_revoked_urls.push(url);
                original(url);
              };
            }""")
            page.get_by_role("button", name="Enfocar mueble").click()
            page.keyboard.press("Escape")
            self.assertEqual(page.evaluate("selectedModuleKey"), "")
            self.assertEqual(page.evaluate("focusedModuleKey"), "")
            self.assertEqual(page.evaluate("selected"), "")
            page.select_option("#modulePicker", value="")
            cleared = page.evaluate("""() => ({key:selectedModuleKey,selected,summary:moduleSummary.textContent,
              candidates:candidateButtons.children.length,wallHidden:wallEditor.hidden,
              focusDisabled:document.querySelector('#focusModule').disabled,
              selection:modulePicker.value,zoom:document.querySelector('#zoom').value,
              intentHidden:wallIntentPreview.hidden,downloadHidden:wallDownload.hidden,blob:wallObjectUrl})""")
            self.assertEqual(cleared["key"], "")
            self.assertEqual(cleared["selected"], "")
            self.assertEqual(cleared["candidates"], 0)
            self.assertTrue(cleared["wallHidden"])
            self.assertTrue(cleared["focusDisabled"])
            self.assertEqual(cleared["selection"], "")
            self.assertEqual(cleared["zoom"], "100")
            self.assertTrue(cleared["intentHidden"])
            self.assertTrue(cleared["downloadHidden"])
            self.assertIsNone(cleared["blob"])
            revoked = page.evaluate(
                "old=>window.__carpn_revoked_urls.includes(old)", old_blob)
            self.assertTrue(revoked)
        finally:
            browser.close()
            playwright.stop()

        self.assertEqual(errors, [])
        self.assertEqual(console_errors, [])
        self.assertEqual(requests, [])
        (self.qa / "INTERACCION.txt").write_text(
            "BROWSER=PASS · Playwright Chromium local · HTML exacto de los tres D19.\n"
            "BAJO: zoom 120→100→120, cámara/corte preservados, AABB menor con puertas/cajón incluidos; "
            "vecinos atenuados sin captura de picking.\n"
            "TORRE y BAJO: candidatos reales visibles, selección propia y capturas enfocadas.\n"
            "ALTO: amarre trasero, suspensión y posición permanecen pendientes.\n"
            "ROOM_LAYOUT vacío: editor accesible, Esc preserva módulo, placeholder limpia sin salto.\n"
            "Intención descargada/releída: exactamente seis campos; JS/consola/red externa=0.\n"
            "No se ejecutaron suites históricas ni se prueba montaje físico.\n",
            encoding="utf-8", newline="\n",
        )


if __name__ == "__main__":
    unittest.main()
