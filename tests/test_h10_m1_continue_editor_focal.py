from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import unittest
from urllib.parse import urlsplit
from zipfile import ZipFile

from carpinova_agent import room_spatial
from carpinova_agent.room_editor_local import EditorSession, _read_input, create_server


MEMBERS = {
    "LEER_PRIMERO.txt", "01-visor-3d.html", "02-planta.svg",
    "03-seccion.svg", "04-habitacion.json", "05-solicitud.json",
    "06-paneles-en-escena.csv", "MANIFEST.json",
}
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready",
         "purchase_ready", "can_generate_f7c")
SOURCE_SHA256 = "83ddbf967d3eb291fcfbea287df491f17bbf38ceb4b9651941a13755ad7ce163"


def read_d19(path: Path) -> tuple[dict[str, bytes], dict, dict]:
    with ZipFile(path) as archive:
        if (len(archive.namelist()) != 8 or set(archive.namelist()) != MEMBERS
                or archive.testzip() is not None):
            raise AssertionError("D19 debe contener exactamente ocho miembros íntegros")
        files = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files["MANIFEST.json"])
    if set(manifest.get("files", {})) != MEMBERS - {"MANIFEST.json"}:
        raise AssertionError("El manifiesto D19 no cubre 7/7 archivos")
    for name, record in manifest["files"].items():
        content = files[name]
        if (record.get("bytes") != len(content)
                or record.get("sha256") != hashlib.sha256(content).hexdigest()):
            raise AssertionError("Hash o tamaño D19 inválido: " + name)
    return files, json.loads(files["04-habitacion.json"]), json.loads(files["05-solicitud.json"])


def stable_boxes(review: dict) -> list[tuple]:
    return sorted((box["group_id"], box["piece_id"], box["role"],
                   tuple(box["origin_xyz_mm"]), tuple(box["size_xyz_mm"]))
                  for box in review["world_boxes"])


def save_d19(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise AssertionError("No se sobrescribe evidencia D19: " + str(target))
    files, _, _ = read_d19(source)
    target.mkdir(parents=True)
    for name, content in files.items():
        (target / name).write_bytes(content)


class H10M1ContinueEditorFocalTests(unittest.TestCase):
    def test_m1_index_guard_precedence(self) -> None:
        result = {}
        piece_ids = ["SPECIAL-LEFT", "SPECIAL-RIGHT", "SPECIAL-TOP", "SPECIAL-BOTTOM"]
        roles = ["left_side", "right_side", "top", "bottom"]
        parts = [{"piece_id": piece_id, "module_id": "SPECIAL", "role": role,
                  "material_id": "MELAMINA_15", "thickness_mm": 15}
                 for piece_id, role in zip(piece_ids, roles)]
        boxes = [{"piece_id": piece_id, "module_id": "SPECIAL", "role": role,
                  "material_id": "MELAMINA_15", "size_xyz_mm": [15, 760, 500]}
                 for piece_id, role in zip(piece_ids, roles)]
        model = {"modules": [{
            "module_id": "SPECIAL", "part_ids": piece_ids, "support": "legs",
            "external_width_mm": 500, "external_height_mm": 760,
            "external_depth_mm": 500, "panel_thickness_mm": 15,
        }], "parts": parts}
        source = {"height_mm": 800, "depth_mm": 500, "installation": "freestanding",
                  "modules": [{"module_id": "SPECIAL", "support": "legs",
                               "support_concept": {"style": "legs", "support_height_mm": 40,
                                                   "overall_height_mm": 800},
                               "countertop": {"depth_mm": 650}}]}
        assembly = [{"group_id": "CAFE", "exchange": {
            "bounds_xyz_mm": [500, 800, 500], "boxes": boxes,
        }}]
        room_spatial._attach_module_edit_index(
            result, {"CAFE": model}, assembly, {"CAFE": source},
        )
        row = result["module_edit_index"][0]
        self.assertEqual(row["editable_fields"], [])
        self.assertIn("café", row["edit_block_reason"].lower())

    def test_m1_live_editor_applies_and_reopens_without_repeating_posts(self) -> None:
        report = Path(os.environ["CARPN_H10_M1_QA_ROOT"]).resolve()
        source_dir = Path(os.environ["CARPN_H10_M1_SOURCE_D19"]).resolve()
        source_path = source_dir / "05-solicitud.json"
        self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), SOURCE_SHA256)
        run = report / "RUN_01"
        host_root = run / "HOST"
        host_root.mkdir(parents=True, exist_ok=False)
        logs = run / "LOGS"
        logs.mkdir()

        session = EditorSession(_read_input(source_path), host_root, 350)
        session.initialize()
        initial_zip = host_root / "editor-v000001-room-review.zip"
        _, initial_review, initial_request = read_d19(initial_zip)
        self.assertEqual(initial_review["piece_count"], 45)
        self.assertEqual(initial_review["layout_sha256"],
                         "15611b9e89758d86691f931dc2b93f1c598b4c9dc7c6f22d95f298963efa2795")
        torre_edit = next(row for row in initial_review["module_edit_index"]
                          if (row["group_id"], row["module_id"]) == ("TORRE", "KITCHEN_1"))
        self.assertEqual(torre_edit["editable_fields"], [
            "width_mm", "overall_height_mm", "carcass_depth_mm",
            "support_style", "support_height_mm",
        ])
        alto_edit = next(row for row in initial_review["module_edit_index"]
                         if (row["group_id"], row["module_id"]) == ("ALTO", "KITCHEN_1"))
        self.assertEqual(alto_edit["carcass_material"],
                         {"material_id": "MELAMINA_15", "thickness_mm": 15})
        self.assertEqual(alto_edit["effective_back_spec"], {
            "style": "inset_full", "material_id": "HDF_3_LAB", "thickness_mm": 3,
            "services_present": False, "grain_axis": "none",
        })
        self.assertTrue(all(initial_review.get(flag) is False for flag in FLAGS))
        self.assertEqual(initial_request, session.request)

        server = create_server(session)
        server_events: list[dict] = []
        handler = server.RequestHandlerClass
        original_headers = handler._headers

        def capture_headers(instance, status, body=b"", content_type="application/json"):
            if instance.command == "POST" and urlsplit(instance.path).path == "/apply":
                raw = bytes(body)
                server_events.append({"status": status, "body_utf8": raw.decode("utf-8")})
            return original_headers(instance, status, body, content_type)

        handler._headers = capture_headers
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}/"
        browser_events = {"responses": [], "posts": [], "page_errors": [],
                          "console_errors": [], "external_requests": []}
        browser_result = "PLAYWRIGHT=PASS"
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: browser_events["page_errors"].append(str(error)))
                page.on("console", lambda message: browser_events["console_errors"].append(message.text)
                        if message.type == "error" else None)
                page.on("request", lambda request: browser_events["external_requests"].append(request.url)
                        if request.url.startswith(("http://", "https://"))
                        and not request.url.startswith(base_url) else None)
                page.on("request", lambda request: browser_events["posts"].append({
                    "method": request.method, "url": request.url,
                    "payload": request.post_data_json,
                }) if request.method == "POST" and request.url == base_url + "apply" else None)
                page.on("response", lambda response: browser_events["responses"].append({
                    "url": response.url, "status": response.status,
                }) if response.request.method == "POST" and response.url == base_url + "apply" else None)

                page.goto(base_url, wait_until="load")
                page.select_option("#modulePicker", label="ALTO · KITCHEN_1")
                # A1 changes only the wall-system intention; all other saved choices stay hydrated.
                initial_wall = page.evaluate("wallSelects.map(select=>select.value)")
                self.assertEqual(initial_wall[0], "inset_board_3mm_review")
                self.assertEqual(initial_wall[1], "french_cleat_45")
                page.select_option("#wallSystem", value="metal_L_bracket")
                self.assertEqual(page.evaluate("wallSelects.map(select=>select.value)"), [
                    initial_wall[0], "metal_L_bracket", initial_wall[2], initial_wall[3],
                ])
                with page.expect_response(lambda response: response.request.method == "POST"
                                          and response.url == base_url + "apply") as pending:
                    page.locator("#applyModuleChanges").click()
                self.assertEqual(pending.value.status, 200)
                page.wait_for_function("window.CARPNOVA_EDITOR_SESSION?.version === 2")
                self.assertEqual(session.version, 2)
                a1_response = json.loads(server_events[-1]["body_utf8"])
                self.assertEqual(server_events[-1]["status"], 200)
                self.assertEqual(a1_response["result"], "REVIEW_SAVED_NO_GEOMETRY_CHANGE")
                a1_payload = browser_events["posts"][-1]["payload"]
                self.assertIsNone(a1_payload["back_spec"])
                self.assertEqual(set(a1_payload["wall_revision"]), {
                    "group_id", "module_id", "back_choice", "wall_system",
                    "support_choice", "wall_substrate",
                })
                a1_zip = host_root / "editor-v000002-room-review.zip"
                _, a1_review, a1_request = read_d19(a1_zip)
                self.assertEqual(a1_review["layout_sha256"], initial_review["layout_sha256"])
                self.assertEqual(stable_boxes(a1_review), stable_boxes(initial_review))
                self.assertEqual(a1_review["piece_count"], 45)
                self.assertEqual(a1_request["back_revisions"], initial_request["back_revisions"])
                alto_wall = next(row for row in a1_request["wall_review_revisions"]
                                 if row["group_id"] == "ALTO")
                self.assertEqual(alto_wall["wall_system"], "metal_L_bracket")
                save_d19(a1_zip, run / "D19_A1_V2")

                # A2 uses material/espesor read from the reconciled carcass, not a production constant.
                page.select_option("#modulePicker", label="ALTO · KITCHEN_1")
                page.select_option("#backChoice", value="inset_carcass_material_review")
                page.select_option("#backServices", value="false")
                page.select_option("#backGrain", value="none")
                with page.expect_response(lambda response: response.request.method == "POST"
                                          and response.url == base_url + "apply") as pending:
                    page.locator("#applyModuleChanges").click()
                self.assertEqual(pending.value.status, 200)
                page.wait_for_function("window.CARPNOVA_EDITOR_SESSION?.version === 3")
                self.assertEqual(session.version, 3)
                a2_payload = browser_events["posts"][-1]["payload"]
                self.assertEqual(a2_payload["wall_revision"]["back_choice"],
                                 "inset_carcass_material_review")
                self.assertEqual(a2_payload["back_spec"], {
                    "style": "inset_full", "material_id": "MELAMINA_15",
                    "thickness_mm": 15, "services_present": False, "grain_axis": "none",
                })
                a2_response = json.loads(server_events[-1]["body_utf8"])
                self.assertEqual(a2_response["result"], "GEOMETRY_UPDATED")
                _, a2_review, a2_request = read_d19(host_root / "editor-v000003-room-review.zip")
                self.assertEqual(a2_review["piece_count"], 45)
                self.assertNotEqual(a2_review["layout_sha256"], a1_review["layout_sha256"])
                self.assertEqual(
                    stable_boxes({"world_boxes": [box for box in a2_review["world_boxes"]
                                                   if box["group_id"] != "ALTO"]}),
                    stable_boxes({"world_boxes": [box for box in a1_review["world_boxes"]
                                                   if box["group_id"] != "ALTO"]}),
                )
                alto_boxes = [box for box in a2_review["world_boxes"] if box["group_id"] == "ALTO"]
                self.assertEqual(sum(box["role"] == "back_full" and box["size_xyz_mm"][2] == 15
                                     for box in alto_boxes), 1)
                self.assertFalse(any("tie" in box["role"] for box in alto_boxes))
                self.assertEqual(a2_review["status"], "REVIEW_ONLY")
                self.assertTrue(all(a2_review.get(flag) is False for flag in FLAGS))
                save_d19(host_root / "editor-v000003-room-review.zip", run / "D19_A2_V3")

                # B changes only the already validated, absolute leg height of TORRE.
                page.select_option("#modulePicker", label="TORRE · KITCHEN_1")
                self.assertFalse(page.locator("#editSupportHeight").is_disabled())
                page.locator("#editSupportHeight").fill("60")
                with page.expect_response(lambda response: response.request.method == "POST"
                                          and response.url == base_url + "apply") as pending:
                    page.locator("#applyModuleChanges").click()
                self.assertEqual(pending.value.status, 200)
                page.wait_for_function("window.CARPNOVA_EDITOR_SESSION?.version === 4")
                self.assertEqual(session.version, 4)
                b_payload = browser_events["posts"][-1]["payload"]
                self.assertIsNone(b_payload["wall_revision"])
                self.assertEqual(b_payload["module_edit"]["support_height_mm"], 60)
                b_response = json.loads(server_events[-1]["body_utf8"])
                self.assertEqual(b_response["result"], "GEOMETRY_UPDATED")
                b_zip = host_root / "editor-v000004-room-review.zip"
                _, b_review, b_request = read_d19(b_zip)
                self.assertEqual(b_review["piece_count"], 45)
                self.assertNotEqual(b_review["layout_sha256"], a2_review["layout_sha256"])
                for group in ("ALTO", "BAJO"):
                    self.assertEqual(
                        stable_boxes({"world_boxes": [box for box in b_review["world_boxes"]
                                                      if box["group_id"] == group]}),
                        stable_boxes({"world_boxes": [box for box in a2_review["world_boxes"]
                                                      if box["group_id"] == group]}),
                    )
                tower = [box for box in b_review["world_boxes"] if box["group_id"] == "TORRE"]
                sides = [box for box in tower if box["role"] in {"left_side", "right_side"}]
                self.assertEqual(len(sides), 2)
                self.assertTrue(all(box["origin_xyz_mm"][1] == 60
                                    and box["size_xyz_mm"][1] == 2040 for box in sides))
                shelf = next(box for box in tower if box["role"] == "shelf_horizontal")
                self.assertEqual(shelf["size_xyz_mm"], [614, 18, 550])
                reservation = next(item for item in b_review["support_reservations"]
                                   if item["group_id"] == "TORRE")
                self.assertEqual(reservation["origin_xyz_mm"], [1100, 0, 0])
                self.assertEqual(reservation["size_xyz_mm"], [650, 60, 550])
                self.assertEqual(b_review["envelope_collisions"], [])
                self.assertEqual(b_review["panel_collisions"], [])
                self.assertTrue(all(b_review.get(flag) is False for flag in FLAGS))
                self.assertEqual(b_request["module_edit_revisions"][0]["support_height_mm"], 60)
                page.screenshot(path=str(run / "M1_HOST_REVIEW.png"), full_page=True)
                browser.close()

            # C starts from a real saved ZIP via _read_input, not an in-memory request shortcut.
            reopen_dir = run / "REOPEN"
            reopen_dir.mkdir()
            reopened_host = run / "REOPEN_HOST"
            reopened_host.mkdir()
            reopened = EditorSession(_read_input(b_zip), reopened_host, 350)
            reopened.initialize()
            reopened_zip = reopened_host / "editor-v000001-room-review.zip"
            _, reopened_review, reopened_request = read_d19(reopened_zip)
            self.assertEqual(reopened.version, 1)
            self.assertEqual(reopened_review["layout_sha256"], b_review["layout_sha256"])
            self.assertEqual(reopened_review["piece_count"], 45)
            self.assertEqual(reopened_request, b_request)
            reopened_alto = next(row for row in reopened_review["module_edit_index"]
                                 if row["group_id"] == "ALTO")
            self.assertEqual(reopened_alto["effective_back_spec"]["thickness_mm"], 15)
            reopened_torre = next(row for row in reopened_review["module_edit_index"]
                                  if row["group_id"] == "TORRE")
            self.assertEqual((reopened_torre["overall_height_mm"],
                              reopened_torre["support_height_mm"]), (2100, 60))
            save_d19(b_zip, report / "D19_M1_FINAL")

            offline_html = (reopened_host / "editor-v000001" / "01-visor-3d.html").read_text(
                encoding="utf-8")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(accept_downloads=True)
                page.on("pageerror", lambda error: browser_events["page_errors"].append(str(error)))
                page.set_content(offline_html, wait_until="load")
                page.select_option("#modulePicker", label="ALTO · KITCHEN_1")
                page.locator("#downloadFullRequest").click()
                page.locator("#downloadFullRequestLink").wait_for(state="visible")
                with page.expect_download() as pending_download:
                    page.locator("#downloadFullRequestLink").click()
                download = pending_download.value
                offline_path = report / "QA" / "M1" / "offline-request.json"
                download.save_as(offline_path)
                offline_request = json.loads(offline_path.read_text(encoding="utf-8"))
                self.assertEqual(offline_request, b_request)
                self.assertNotIn(reopened.token, offline_path.read_text(encoding="utf-8"))
                self.assertEqual(browser_events["external_requests"], [])
                browser.close()
        finally:
            handler._headers = original_headers
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=5)
        self.assertEqual(len(server_events), 3)
        self.assertEqual([event["status"] for event in server_events], [200, 200, 200])
        self.assertEqual(len(browser_events["posts"]), 3)
        self.assertEqual([event["status"] for event in browser_events["responses"]], [200, 200, 200])
        self.assertEqual(browser_events["page_errors"], [])
        self.assertEqual(browser_events["console_errors"], [])
        self.assertEqual(browser_events["external_requests"], [])
        (logs / "SERVER_RESPONSES.json").write_text(
            json.dumps(server_events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (logs / "BROWSER_EVENTS.json").write_text(
            json.dumps(browser_events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (logs / "M1_RUN_SUMMARY.json").write_text(json.dumps({
            "source_sha256": SOURCE_SHA256, "versions": [1, 2, 3, 4],
            "piece_count": session.current_review["piece_count"],
            "layout_sha256": session.layout_sha256, "browser": browser_result,
            "physical_flags": {flag: session.current_review[flag] for flag in FLAGS},
            "install_ready": False, "release": "NO_GO",
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
