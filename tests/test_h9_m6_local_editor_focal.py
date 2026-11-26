from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from carpinova_agent import room_3d_review
from carpinova_agent.kitchen_linear import _build
from carpinova_agent.mcp_bridge import carpinova_generar_borrador
from carpinova_agent.module_edits import apply_group_revisions, validate_revision_list
from carpinova_agent.room_editor_local import EditorSession, create_server
from carpinova_agent.room_spatial import review_room_from_kitchen_state, review_room_from_specs
from test_kitchen_linear import make_l1

ROOT = Path(__file__).resolve().parents[1]
M5 = Path(r"D:\codex\_REPORTES\CarpiNova-Agente\CARPN_H9_M6_V4\QA\M5_GATE\RUN_01")
FIXTURE = ROOT / "tests" / "fixtures" / "room_review_d19" / "f9a_room_public.json"
MEMBERS = {
    "LEER_PRIMERO.txt", "01-visor-3d.html", "02-planta.svg",
    "03-seccion.svg", "04-habitacion.json", "05-solicitud.json",
    "06-paneles-en-escena.csv", "MANIFEST.json",
}
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready",
         "purchase_ready", "can_generate_f7c")


def revision(group: str, module: str, *, width=500, height=800, depth=500,
             style="floor_direct", support=0) -> dict:
    return {
        "group_id": group, "module_id": module, "width_mm": width,
        "overall_height_mm": height, "carcass_depth_mm": depth,
        "support_style": style, "support_height_mm": support,
    }


def read_d19(path: Path) -> tuple[dict[str, bytes], dict]:
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 8 or set(names) != MEMBERS or archive.testzip() is not None:
            raise AssertionError(f"D19 inválido: {names}")
        files = {name: archive.read(name) for name in names}
    manifest = json.loads(files["MANIFEST.json"])
    if set(manifest["files"]) != MEMBERS - {"MANIFEST.json"}:
        raise AssertionError("Manifest D19 distinto de 7/7")
    for name, entry in manifest["files"].items():
        data = files[name]
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise AssertionError(f"Hash/tamaño D19 inválido: {name}")
    return files, json.loads(files["04-habitacion.json"])


class H9M6LocalEditorFocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("CARPN_H9_M6_DELIVERY_ROOT")
        if not configured:
            raise RuntimeError("CARPN_H9_M6_DELIVERY_ROOT debe indicar staging absoluto nuevo")
        cls.qa = Path(configured).resolve()
        if cls.qa.is_symlink() or cls.qa.exists():
            raise RuntimeError("El staging M6 debe ser nuevo y no estar enlazado")
        cls.qa.mkdir(parents=True, exist_ok=False)
        cls.logs = cls.qa / "LOGS"
        cls.logs.mkdir()
        cls.tool_output = cls.qa / "P1_OUTPUT"
        cls.tool_output.mkdir()
        base42 = json.loads((M5 / "D19_42" / "05-solicitud.json").read_text(encoding="utf-8"))
        base42["module_edit_revisions"] = []
        cls.base42 = base42
        cls.combined = json.loads(
            (M5 / "D19_COMBINED_46" / "05-solicitud.json").read_text(encoding="utf-8")
        )
        cls.combined["module_edit_revisions"] = []
        cls.room_base = json.loads(FIXTURE.read_text(encoding="utf-8"))["request"]
        cls.room_base["wall_review_revisions"] = []
        cls.room_base["module_edit_revisions"] = []

    @classmethod
    def _generate(cls, request: dict, project: str) -> Path:
        result = carpinova_generar_borrador(
            solicitud_json=json.dumps(request, ensure_ascii=False),
            proyecto=project, incluir_planos=False, seccion_y_mm=350,
        )
        if (result["release"] != "NO_GO" or result["can_generate_f7c"] is not False
                or any(result[flag] is not False for flag in FLAGS)):
            raise AssertionError("Guardrails del borrador alterados")
        return Path(result["room_package_path"])

    def test_p1_public_f6_edits_b_and_c(self) -> None:
        request_b = copy.deepcopy(self.base42)
        request_b["module_edit_revisions"] = [revision(
            "BAJO", "KITCHEN_RIGHT", width=540, height=800, depth=500,
        )]
        with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": str(self.tool_output)}):
            zip_b = self._generate(request_b, "H9M6_P1_B")
        files_b, review_b = read_d19(zip_b)
        dest_b = self.qa / "D19_BAJO_DRAWER_EDIT"
        dest_b.mkdir()
        for name, data in files_b.items():
            (dest_b / name).write_bytes(data)
        bajo = next(item for item in review_b["groups"] if item["group_id"] == "BAJO")
        tower = next(item for item in review_b["groups"] if item["group_id"] == "TORRE")
        self.assertEqual(bajo["bounds_xyz_mm"][0], 1040)
        self.assertEqual(tower["origin_xyz_mm"][0] - bajo["bounds_xyz_mm"][0], 60)
        self.assertEqual(review_b["status"], "REVIEW_ONLY")
        self.assertEqual(review_b["piece_count"], 42)
        self.assertFalse(review_b["envelope_collisions"])
        self.assertFalse(review_b["panel_collisions"])
        drawer_boxes = [box for box in review_b["world_boxes"]
                        if box["group_id"] == "BAJO" and box["role"].startswith("drawer_")]
        old = json.loads((M5 / "D19_42" / "04-habitacion.json").read_text(encoding="utf-8"))
        old_drawers = [box for box in old["world_boxes"]
                       if box["group_id"] == "BAJO" and box["role"].startswith("drawer_")]
        self.assertEqual(len(drawer_boxes), 18)
        self.assertEqual({box["piece_id"] for box in drawer_boxes},
                         {box["piece_id"] for box in old_drawers})
        self.assertEqual({(box["origin_xyz_mm"][1], box["size_xyz_mm"][1]) for box in drawer_boxes},
                         {(box["origin_xyz_mm"][1], box["size_xyz_mm"][1]) for box in old_drawers})

        request_c = copy.deepcopy(self.room_base)
        request_c["module_edit_revisions"] = [revision(
            "RECTO", "RECTO", width=580, height=720, depth=540,
        )]
        with patch.dict(os.environ, {"CARPINOVA_OUTPUT_ROOT": str(self.tool_output)}):
            zip_c = self._generate(request_c, "H9M6_P1_C")
        files_c, review_c = read_d19(zip_c)
        dest_c = self.qa / "D19_ROOM_EDIT"
        dest_c.mkdir()
        for name, data in files_c.items():
            (dest_c / name).write_bytes(data)
        recto = next(item for item in review_c["groups"] if item["group_id"] == "RECTO")
        self.assertEqual(recto["rotation_deg"], 90)
        self.assertEqual(recto["bounds_xyz_mm"], [540, 720, 580])
        edit_c = next(item for item in review_c["module_edit_index"]
                      if item["group_id"] == "RECTO")
        self.assertEqual((edit_c["width_mm"], edit_c["carcass_depth_mm"]), (580, 540))
        self.assertEqual(review_c["piece_count"], 9)
        for review in (review_b, review_c):
            self.assertEqual(review["release"], "NO_GO")
            for flag in FLAGS:
                self.assertIs(review[flag], False)
        (self.logs / "P1.json").write_text(json.dumps({
            "B": {"layout_sha256": review_b["layout_sha256"], "piece_count": review_b["piece_count"],
                  "BAJO_width": bajo["bounds_xyz_mm"][0], "gap_to_TORRE_mm": 60,
                  "drawer_panels": len(drawer_boxes)},
            "C": {"layout_sha256": review_c["layout_sha256"], "piece_count": review_c["piece_count"],
                  "RECTO_local": [580, 720, 540], "RECTO_rotated_bounds": recto["bounds_xyz_mm"]},
        }, indent=2) + "\n", encoding="utf-8")

    def test_p2_invalid_and_interference_rejections(self) -> None:
        before = set(self.tool_output.glob("*.zip"))
        base = copy.deepcopy(self.combined)
        for bad in (
            [revision("BAJO", "KITCHEN_RIGHT", width=True)],
            [revision("BAJO", "KITCHEN_RIGHT", style="not_a_support")],
            [revision("BAJO", "KITCHEN_RIGHT"), revision("BAJO", "KITCHEN_RIGHT")],
        ):
            with self.assertRaises(ValueError):
                validate_revision_list(bad)
        for edit in (
            revision("BAJO", "KITCHEN_RIGHT", height=801),
            revision("BAJO", "KITCHEN_RIGHT", depth=501),
            revision("BAJO", "KITCHEN_RIGHT", style="legs", support=40),
            revision("BAJO", "KITCHEN_RIGHT", width=650),
        ):
            candidate = copy.deepcopy(base)
            candidate["module_edit_revisions"] = [edit]
            with self.assertRaises(ValueError):
                review_room_from_kitchen_state(candidate)
        tower = _build(make_l1()["review_state"]["working"])["_reviews"]["TORRE"]["_trusted_nominal_request"]["module_spec"]
        for support, style in ((40, "legs"), (60, "legs"), (0, "floor_direct")):
            result, offsets = apply_group_revisions(tower, [revision(
                "TORRE", "KITCHEN_1", width=600, height=2100,
                depth=600, style=style, support=support,
            )])
            self.assertEqual(result["height_mm"], 2100 - support)
            self.assertEqual(offsets["KITCHEN_1"], support)
            self.assertEqual(tower["height_mm"], 2100)
        self.assertEqual(set(self.tool_output.glob("*.zip")), before)
        (self.logs / "P2.json").write_text(json.dumps({
            "invalid_types": "REJECTED", "shared_height_depth_support": "REJECTED",
            "BAJO_width_overlaps_TORRE": "REJECTED", "support_offsets_from_source": [40, 60, 0],
            "new_zip_on_rejection": False,
        }, indent=2) + "\n", encoding="utf-8")

    def test_p3_live_local_editor_interaction_apply_and_rollback(self) -> None:
        host_root = self.qa / "HOST_SESSION"
        host_root.mkdir()
        session = EditorSession(copy.deepcopy(self.combined), host_root, 350)
        session.initialize()
        server = create_server(session)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_files, base_review = read_d19(host_root / "editor-v000001-room-review.zip")
        (self.qa / "D19_HOST_INITIAL").mkdir()
        for name, data in base_files.items():
            (self.qa / "D19_HOST_INITIAL" / name).write_bytes(data)
        url = f"http://127.0.0.1:{server.server_port}/"
        browser_result = "BROWSER=BLOCKED"
        try:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                sync_playwright = None
            if sync_playwright is None:
                self._p3_http_fallback(session, server.server_port, base_review)
            else:
                pw = sync_playwright().start()
                try:
                    browser = pw.chromium.launch(headless=True)
                except Exception as exc:
                    self._p3_http_fallback(session, server.server_port, base_review)
                    browser_result = f"BROWSER=BLOCKED · Chromium: {type(exc).__name__}: {exc}"
                    pw.stop()
                    pw = None
                else:
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    errors, external, torre_requests, torre_responses = [], [], [], []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("request", lambda req: external.append(req.url)
                            if req.url.startswith(("http://", "https://")) and not req.url.startswith(url) else None)
                    page.on("request", lambda req: torre_requests.append({
                        "method": req.method, "url": req.url,
                        "post_data_json": req.post_data_json,
                    }) if req.method == "POST" and req.url == url + "apply" else None)

                    def capture_torre_response(response):
                        if response.request.method == "POST" and response.url == url + "apply":
                            record = {"status": response.status, "url": response.url}
                            try:
                                record["body"] = json.loads(response.body())
                            except Exception as exc:
                                record["body_error"] = f"{type(exc).__name__}: {exc}"
                            torre_responses.append(record)

                    page.on("response", capture_torre_response)
                    page.goto(url, wait_until="load")
                    point = page.evaluate("""() => {
                      const target=data.boxes.findIndex(b=>b.group==='BAJO'&&b.module_id==='KITCHEN_RIGHT');
                      const i=pickBuffer.ids.findIndex(owner=>owner===target);if(i<0)throw Error('No hay píxel BAJO RIGHT');
                      const x=pickBuffer.x+((i%pickBuffer.width)+.5)/pickBuffer.width*pickBuffer.w;
                      const y=pickBuffer.y+(Math.floor(i/pickBuffer.width)+.5)/pickBuffer.height*pickBuffer.h;
                      const p=svg.createSVGPoint();p.x=x;p.y=y;const s=p.matrixTransform(svg.getScreenCTM());return {x:s.x,y:s.y};
                    }""")
                    page.mouse.click(point["x"], point["y"])
                    selected = page.evaluate("({key:selectedModuleKey,piece:selected})")
                    self.assertEqual(selected["key"], "BAJO::KITCHEN_RIGHT")
                    yellow = page.locator("#scene image").evaluate("""async image=>{
                      const bitmap=await createImageBitmap(await (await fetch(image.getAttribute('href'))).blob());
                      const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;
                      const ctx=canvas.getContext('2d');ctx.drawImage(bitmap,0,0);const data=ctx.getImageData(0,0,bitmap.width,bitmap.height).data;let n=0;
                      for(let i=0;i<data.length;i+=4)if(data[i]===249&&data[i+1]===209&&data[i+2]===84)n++;return n;
                    }""")
                    self.assertGreater(yellow, 0)
                    page.screenshot(path=str(self.qa / "HOST_PICK_BAJO_RIGHT.png"), full_page=True)
                    page.mouse.dblclick(point["x"], point["y"])
                    self.assertEqual(page.evaluate("focusedModuleKey"), "BAJO::KITCHEN_RIGHT")
                    page.get_by_role("button", name="Volver al conjunto").click()
                    page.select_option("#modulePicker", label="TORRE · KITCHEN_1")
                    page.get_by_role("button", name="Enfocar mueble").click()
                    page.keyboard.press("Escape")
                    self.assertEqual(page.evaluate("({selectedModuleKey,focusedModuleKey,selected})"),
                                     {"selectedModuleKey": "", "focusedModuleKey": "", "selected": ""})

                    page.select_option("#modulePicker", label="ALTO · KITCHEN_1")
                    page.select_option("#backChoice", value="keep_existing")
                    page.select_option("#wallSystem", value="french_cleat_45")
                    page.select_option("#supportChoice", value="keep_existing")
                    page.select_option("#wallSubstrate", value="unknown")
                    with page.expect_navigation(wait_until="load"):
                        page.locator("#applyModuleChanges").click()
                    self.assertEqual(session.version, 2)
                    french = session.current_review
                    alto_french = next(row for row in french["wall_review_by_module"]
                                       if row["group_id"] == "ALTO")
                    self.assertEqual(alto_french["wall_system"], "french_cleat_45")
                    self.assertEqual(french["piece_count"], 46)
                    self.assertEqual(french["layout_sha256"], base_review["layout_sha256"])
                    self.assertTrue(any(box["role"] == "wall_rear_upper_tie"
                                        for box in french["world_boxes"]))
                    page.screenshot(path=str(self.qa / "HOST_ALTO_FRENCH_REVIEW.png"), full_page=True)
                    self._copy_version(host_root, "editor-v000002", self.qa / "D19_ALTO_FRENCH_REVIEW")

                    page.select_option("#modulePicker", label="ALTO · KITCHEN_1")
                    page.select_option("#backChoice", value="inset_board_3mm_review")
                    page.select_option("#backMaterial", value="HDF_3_LAB")
                    page.select_option("#backServices", value="false")
                    page.select_option("#backGrain", value="none")
                    page.locator("#replaceTies").check()
                    with page.expect_navigation(wait_until="load"):
                        page.locator("#applyModuleChanges").click()
                    self.assertEqual(session.version, 3)
                    alto = [box for box in session.current_review["world_boxes"]
                            if box["group_id"] == "ALTO"]
                    self.assertEqual(session.current_review["piece_count"], 45)
                    self.assertEqual(sum(box["role"] == "back_full" and box["size_xyz_mm"][2] == 3
                                         for box in alto), 1)
                    self.assertFalse(any("tie" in box["role"] for box in alto))
                    self.assertEqual(sum(box["group_id"] == "BAJO" and box["role"].startswith("drawer_")
                                         for box in session.current_review["world_boxes"]), 18)
                    self.assertEqual(session.current_review["layout_sha256"] != french["layout_sha256"], True)
                    page.screenshot(path=str(self.qa / "HOST_ALTO_3MM_APPLIED.png"), full_page=True)
                    self._copy_version(host_root, "editor-v000003", self.qa / "D19_ALTO_3MM_APPLIED")

                    before_reject = len(list(host_root.glob("*.zip")))
                    last_digest = session.layout_sha256
                    page.select_option("#modulePicker", label="BAJO · KITCHEN_RIGHT")
                    page.select_option("#backChoice", value="inset_board_3mm_review")
                    page.select_option("#backMaterial", value="HDF_3_LAB")
                    page.select_option("#backServices", value="false")
                    page.select_option("#backGrain", value="none")
                    page.locator("#applyModuleChanges").click()
                    page.wait_for_timeout(300)
                    self.assertEqual(session.version, 3)
                    self.assertEqual(session.layout_sha256, last_digest)
                    self.assertEqual(len(list(host_root.glob("*.zip"))), before_reject)
                    self.assertNotIn("aplicados", page.locator("#moduleEditStatus").inner_text().lower())

                    bad_payload = {"version": 2, "group_id": "TORRE", "module_id": "KITCHEN_1",
                                   "wall_revision": None, "back_spec": None,
                                   "replace_existing_ties": False, "module_edit": None}
                    self.assertEqual(self._post_status(server.server_port, bad_payload, "invalid-token"), 403)
                    self.assertEqual(self._post_status(server.server_port, bad_payload, session.token), 409)
                    self.assertEqual(len(list(host_root.glob("*.zip"))), before_reject)

                    page.select_option("#modulePicker", label="TORRE · KITCHEN_1")
                    page.locator("#editWidth").fill("650")
                    page.locator("#editHeight").fill("2100")
                    page.locator("#editDepth").fill("550")
                    page.select_option("#editSupportStyle", value="legs")
                    page.locator("#editSupportHeight").fill("40")
                    try:
                        with page.expect_response(
                            lambda response: response.request.method == "POST"
                            and response.url == url + "apply", timeout=60000,
                        ) as pending:
                            page.locator("#applyModuleChanges").click()
                        response = pending.value
                        response_capture = torre_responses[-1] if torre_responses else {}
                        response_body = response_capture.get("body")
                        response_payload = torre_requests[-1]["post_data_json"] if torre_requests else None
                        expected_payload = {
                            "version": 3, "group_id": "TORRE", "module_id": "KITCHEN_1",
                            "wall_revision": None, "back_spec": None,
                            "replace_existing_ties": False,
                            "module_edit": {
                                "group_id": "TORRE", "module_id": "KITCHEN_1",
                                "width_mm": 650, "overall_height_mm": 2100,
                                "carcass_depth_mm": 550, "support_style": "legs",
                                "support_height_mm": 40,
                            },
                        }
                        (self.logs / "P3_TORRE_HTTP.json").write_text(json.dumps({
                            "status": response_capture.get("status", response.status),
                            "body": response_body, "body_capture_error": response_capture.get("body_error"),
                            "post_data_json": response_payload,
                        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                        self.assertIsNotNone(response_body, "No se retuvo el cuerpo HTTP antes de la recarga")
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response_payload, expected_payload)
                        self.assertEqual(response_body.get("ok"), True)
                        self.assertEqual(response_body.get("version"), 4)
                        self.assertEqual(response_body.get("result"), "GEOMETRY_UPDATED")
                        self.assertEqual(response_body.get("layout_sha256"), session.layout_sha256)
                    except Exception as exc:
                        (self.logs / "P3_TORRE_HTTP_FAILURE.json").write_text(json.dumps({
                            "error_type": type(exc).__name__, "error": str(exc),
                            "version": session.version, "layout_sha256": session.layout_sha256,
                            "output_zip_count": len(list(host_root.glob("*.zip"))),
                            "output_zip_names": sorted(path.name for path in host_root.glob("*.zip")),
                            "last_module_status": page.locator("#moduleEditStatus").inner_text(),
                            "requests": torre_requests, "responses": torre_responses,
                            "page_errors": errors,
                        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                        raise
                    page.wait_for_function(
                        "() => window.CARPNOVA_EDITOR_SESSION?.version === 4 "
                        "&& document.getElementById('selectionStatus')?.textContent.includes('TORRE')",
                        timeout=30000,
                    )
                    self.assertEqual(page.evaluate("selectedModuleKey"), "TORRE::KITCHEN_1")
                    self.assertEqual(page.locator("#editWidth").input_value(), "650")
                    self.assertEqual(page.locator("#editHeight").input_value(), "2100")
                    self.assertEqual(page.locator("#editDepth").input_value(), "550")
                    self.assertEqual(page.locator("#editSupportStyle").input_value(), "legs")
                    self.assertEqual(page.locator("#editSupportHeight").input_value(), "40")
                    final = session.current_review
                    self.assertEqual(session.version, 4)
                    self.assertEqual(final["piece_count"], 45)
                    tower_edit = next(row for row in final["module_edit_index"]
                                      if row["group_id"] == "TORRE")
                    self.assertEqual((tower_edit["width_mm"], tower_edit["overall_height_mm"],
                                      tower_edit["carcass_height_mm"], tower_edit["carcass_depth_mm"],
                                      tower_edit["support_style"], tower_edit["support_height_mm"]),
                                     (650, 2100, 2060, 550, "legs", 40))
                    tower_boxes = [box for box in final["world_boxes"] if box["group_id"] == "TORRE"]
                    sides = [box for box in tower_boxes if box["role"] in {"left_side", "right_side"}]
                    self.assertEqual(len(sides), 2)
                    self.assertTrue(all(box["origin_xyz_mm"][1] == 40
                                        and box["size_xyz_mm"][1] == 2060
                                        and box["size_xyz_mm"][2] == 550 for box in sides))
                    shelf = next(box for box in tower_boxes if box["role"] == "shelf_horizontal")
                    self.assertEqual(shelf["size_xyz_mm"], [614, 18, 550])
                    self.assertTrue(all(box["origin_xyz_mm"][1] + box["size_xyz_mm"][1] <= 2100
                                        for box in tower_boxes))
                    page.screenshot(path=str(self.qa / "HOST_TORRE_EDIT_FINAL.png"), full_page=True)
                    self._copy_version(host_root, "editor-v000004", self.qa / "D19_A_TORRE_EDIT")

                    source_saved = json.loads((session.last_valid_path / "05-solicitud.json").read_text(encoding="utf-8"))
                    self.assertEqual(source_saved["review_state"]["working"]["positions"]["TORRE"], [1100, 0, 0])
                    self.assertEqual(source_saved["module_edit_revisions"], [revision(
                        "TORRE", "KITCHEN_1", width=650, height=2100, depth=550,
                        style="legs", support=40,
                    )])
                    offline_errors, offline_external = [], []
                    offline_page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
                    offline_page.on("pageerror", lambda error: offline_errors.append(str(error)))
                    offline_page.on("request", lambda req: offline_external.append(req.url)
                                    if req.url.startswith(("http://", "https://")) else None)
                    offline_page.set_content(
                        (session.last_valid_path / "01-visor-3d.html").read_text(encoding="utf-8"),
                        wait_until="load",
                    )
                    offline_page.select_option("#modulePicker", label="TORRE · KITCHEN_1")
                    self.assertTrue(offline_page.locator("#offlineNotice").is_visible())
                    self.assertTrue(offline_page.locator("#applyModuleChanges").is_hidden())
                    self.assertEqual(offline_page.locator("#editWidth").input_value(), "650")
                    self.assertEqual(offline_page.locator("#editHeight").input_value(), "2100")
                    self.assertEqual(offline_page.locator("#editDepth").input_value(), "550")
                    self.assertEqual(offline_page.locator("#editSupportStyle").input_value(), "legs")
                    self.assertEqual(offline_page.locator("#editSupportHeight").input_value(), "40")
                    offline_page.locator("#downloadFullRequest").click()
                    link = offline_page.locator("#downloadFullRequestLink")
                    link.wait_for(state="visible")
                    self.assertTrue((link.get_attribute("href") or "").startswith("blob:"))
                    with offline_page.expect_download(timeout=15000) as download_info:
                        link.click()
                    download = download_info.value
                    path = self.qa / "OFFLINE_REQUEST.json"
                    download.save_as(path)
                    downloaded_text = path.read_text(encoding="utf-8")
                    downloaded = json.loads(downloaded_text)
                    self.assertEqual(downloaded, source_saved)
                    self.assertNotIn(session.token, downloaded_text)
                    self.assertNotIn(session.token, (session.last_valid_path / "01-visor-3d.html").read_text(encoding="utf-8"))
                    self.assertEqual(offline_errors, [])
                    self.assertEqual(offline_external, [])
                    self.assertEqual(errors, [])
                    self.assertEqual(external, [])
                    browser_result = "BROWSER=PASS · clic raster, doble clic, retorno, Escape, aplicar y descarga offline reales"
                    browser.close()
                finally:
                    if pw is not None:
                        pw.stop()
            for version, folder in ((2, "D19_ALTO_FRENCH_REVIEW"),
                                    (3, "D19_ALTO_3MM_APPLIED"),
                                    (4, "D19_A_TORRE_EDIT")):
                destination = self.qa / folder
                if not destination.exists():
                    self._copy_version(host_root, f"editor-v{version:06d}", destination)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        (self.logs / "P3.json").write_text(json.dumps({
            "browser": browser_result, "version": session.version,
            "piece_count": session.current_review.get("piece_count"),
            "layout_sha256": session.layout_sha256,
            "flags": {flag: session.current_review.get(flag) for flag in FLAGS},
            "http_auth_invalid": 403, "http_stale": 409,
            "rollback": "PASS", "offline_request": "PASS" if browser_result.startswith("BROWSER=PASS") else "NOT_RUN",
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @staticmethod
    def _copy_version(root: Path, name: str, destination: Path) -> None:
        destination.mkdir()
        for member in MEMBERS:
            (destination / member).write_bytes((root / name / member).read_bytes())
        read_d19_from_dir(destination)

    @staticmethod
    def _post_status(port: int, payload: dict, token: str) -> int:
        req = Request(f"http://127.0.0.1:{port}/apply", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json",
                               "Origin": f"http://127.0.0.1:{port}",
                               "X-CarpiNova-Session": token}, method="POST")
        try:
            with urlopen(req) as response:
                return response.status
        except HTTPError as exc:
            return exc.code

    @staticmethod
    def _p3_http_fallback(session: EditorSession, port: int, _base: dict) -> None:
        def post(payload: dict, token: str | None = None) -> tuple[int, dict]:
            req = Request(
                f"http://127.0.0.1:{port}/apply", data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}",
                         "X-CarpiNova-Session": token or session.token}, method="POST",
            )
            try:
                with urlopen(req) as response:
                    return response.status, json.loads(response.read())
            except HTTPError as exc:
                return exc.code, json.loads(exc.read())

        count_before = len(list(session.output_dir.glob("*.zip")))
        french = {"group_id": "ALTO", "module_id": "KITCHEN_1",
                  "back_choice": "keep_existing", "wall_system": "french_cleat_45",
                  "support_choice": "keep_existing", "wall_substrate": "unknown"}
        status, _ = post({"version": 1, "group_id": "ALTO", "module_id": "KITCHEN_1",
                          "wall_revision": french, "back_spec": None,
                          "replace_existing_ties": False, "module_edit": None})
        if status != 200 or session.version != 2 or session.current_review["piece_count"] != 46:
            raise AssertionError("Revisión HTTP francesa no aplicada")
        full = {"style": "inset_full", "material_id": "HDF_3_LAB", "thickness_mm": 3,
                "services_present": False, "grain_axis": "none"}
        french["back_choice"] = "inset_board_3mm_review"
        status, _ = post({"version": 2, "group_id": "ALTO", "module_id": "KITCHEN_1",
                          "wall_revision": french, "back_spec": full,
                          "replace_existing_ties": True, "module_edit": None})
        if status != 200 or session.version != 3 or session.current_review["piece_count"] != 45:
            raise AssertionError("Fondo 3 mm ALTO no aplicado")
        before_reject, digest = len(list(session.output_dir.glob("*.zip"))), session.layout_sha256
        bajo = {"group_id": "BAJO", "module_id": "KITCHEN_RIGHT",
                "back_choice": "inset_board_3mm_review", "wall_system": "floor_furniture_anti_tip",
                "support_choice": "keep_existing", "wall_substrate": "unknown"}
        status, _ = post({"version": 3, "group_id": "BAJO", "module_id": "KITCHEN_RIGHT",
                          "wall_revision": bajo, "back_spec": full,
                          "replace_existing_ties": False, "module_edit": None})
        if status != 422 or session.version != 3 or session.layout_sha256 != digest:
            raise AssertionError("Rechazo BAJO no preservó la última versión válida")
        stale = {"version": 2, "group_id": "TORRE", "module_id": "KITCHEN_1",
                 "wall_revision": None, "back_spec": None,
                 "replace_existing_ties": False, "module_edit": None}
        if post(stale, "not-the-session-token")[0] != 403 or post(stale)[0] != 409:
            raise AssertionError("No se bloquearon token inválido y versión obsoleta")
        edit = revision("TORRE", "KITCHEN_1", width=650, height=2100, depth=550,
                        style="legs", support=40)
        status, _ = post({"version": 3, "group_id": "TORRE", "module_id": "KITCHEN_1",
                          "wall_revision": None, "back_spec": None,
                          "replace_existing_ties": False, "module_edit": edit})
        if status != 200 or session.version != 4 or session.current_review["piece_count"] != 45:
            raise AssertionError("Edición dimensional TORRE no aplicada")
        tower = next(row for row in session.current_review["module_edit_index"]
                     if row["group_id"] == "TORRE")
        if (tower["width_mm"], tower["carcass_height_mm"], tower["carcass_depth_mm"],
                tower["support_style"], tower["support_height_mm"]) != (650, 2060, 550, "legs", 40):
            raise AssertionError("Dimensiones efectivas de TORRE no coinciden")
        if len(list(session.output_dir.glob("*.zip"))) != count_before + 3:
            raise AssertionError("Se guardó un ZIP para un rechazo o una versión antigua")


def read_d19_from_dir(path: Path) -> None:
    names = {item.name for item in path.iterdir()}
    if names != MEMBERS:
        raise AssertionError("D19 extraído debe contener exactamente ocho archivos")
    manifest = json.loads((path / "MANIFEST.json").read_text(encoding="utf-8"))
    if set(manifest["files"]) != MEMBERS - {"MANIFEST.json"}:
        raise AssertionError("El manifiesto interno no es 7/7")
    for name, record in manifest["files"].items():
        data = (path / name).read_bytes()
        if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise AssertionError(f"Hash D19 inválido: {name}")


if __name__ == "__main__":
    unittest.main()
