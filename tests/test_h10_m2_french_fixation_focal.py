from __future__ import annotations

import copy
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from zipfile import ZipFile

from playwright.sync_api import sync_playwright

from carpinova_agent.kitchen_linear import _build
from carpinova_agent.room_3d_review import render_room_3d_html
from carpinova_agent.room_editor_local import EditorSession, _read_input, create_server
from carpinova_agent.room_review_package import render_room_panel_section_svg
from carpinova_agent.room_spatial import render_top_view_svg, review_room_from_specs
from carpinova_agent.wall_fixation_review import (
    append_section_detail, canonical_sha256, validate_geometry,
)


M1_D19 = Path(
    r"D:\codex\_REPORTES\CarpiNova-Agente\CARPN_H10_M1_M2_V4\QA\M1\RUN_01\HOST\editor-v000004-room-review.zip"
)
MEMBERS = {
    "LEER_PRIMERO.txt", "01-visor-3d.html", "02-planta.svg", "03-seccion.svg",
    "04-habitacion.json", "05-solicitud.json", "06-paneles-en-escena.csv",
    "MANIFEST.json",
}
FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready",
    "can_generate_f7c",
)
EMPTY_FIXATION_SHA256 = hashlib.sha256(b"[]").hexdigest()


def _read_d19(path: Path) -> tuple[dict[str, bytes], dict, dict, dict]:
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 8 or set(names) != MEMBERS or archive.testzip() is not None:
            raise AssertionError(f"D19 inválido: {names}")
        files = {name: archive.read(name) for name in names}
    manifest = json.loads(files["MANIFEST.json"])
    if set(manifest.get("files", {})) != MEMBERS - {"MANIFEST.json"}:
        raise AssertionError("El manifiesto D19 no cubre siete archivos")
    for name, record in manifest["files"].items():
        if (len(files[name]) != record.get("bytes")
                or hashlib.sha256(files[name]).hexdigest() != record.get("sha256")):
            raise AssertionError(f"Hash D19 inválido: {name}")
    return (files, manifest, json.loads(files["04-habitacion.json"]),
            json.loads(files["05-solicitud.json"]))


def _copy_d19(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise AssertionError(f"No se sobrescribe evidencia: {destination}")
    files, _, _, _ = _read_d19(source)
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        (destination / name).write_bytes(content)
    if {item.name for item in destination.iterdir()} != MEMBERS:
        raise AssertionError("El D19 extraído no contiene ocho miembros exactos")
    copied = json.loads((destination / "MANIFEST.json").read_bytes())
    if set(copied["files"]) != MEMBERS - {"MANIFEST.json"}:
        raise AssertionError("Manifiesto extraído no es 7/7")


@contextmanager
def _capture_apply_responses(server):
    captured: list[dict[str, object]] = []
    handler = server.RequestHandlerClass
    original = handler._headers

    def record(self, status, body=b"", content_type="application/json"):
        if getattr(self, "command", None) == "POST" and urlsplit(self.path).path == "/apply":
            captured.append({"status": status, "body": body.decode("utf-8", "replace")})
        return original(self, status, body, content_type)

    with patch.object(handler, "_headers", record):
        yield captured


def _assert_safe_review(test: unittest.TestCase, review: dict, piece_count: int) -> None:
    test.assertEqual(review["status"], "REVIEW_ONLY")
    test.assertIs(review["can_generate_f7c"], False)
    test.assertEqual(review["piece_count"], piece_count)
    if "release" in review:
        test.assertEqual(review["release"], "NO_GO")
    if "manufacturing_holes" in review:
        test.assertEqual(review["manufacturing_holes"], [])
    for flag in FLAGS:
        test.assertIs(review[flag], False)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class H10M2FrenchFixationFocalTests(unittest.TestCase):
    def test_pure_geometry_specs_entrypoint_rotation_and_guards(self) -> None:
        self.assertTrue(M1_D19.is_file(), f"Falta fuente M1 D19 comprobada: {M1_D19}")
        _, _, source_review, source_request = _read_d19(M1_D19)
        self.assertEqual(source_review["layout_sha256"],
                         "757c8665b48ec374b0163f6bb2e1906e93f98f544982bd01dedc09846979ea44")
        rebuilt = _build(source_request["review_state"]["working"])
        module_spec = copy.deepcopy(
            rebuilt["_reviews"]["ALTO"]["_trusted_nominal_request"]["module_spec"]
        )
        module_spec["modules"][0]["back"] = {
            "style": "inset_full", "material_id": "MELAMINA_15",
            "thickness_mm": 15, "services_present": False, "grain_axis": "none",
        }
        assembly = {"group_id": "ALTO", "module_spec": module_spec,
                    "origin_xyz_mm": [100, 0, 100], "rotation_deg": 0}
        base = {"review_kind": "room_layout_v1", "assemblies": [assembly],
                "service_zones": []}
        legacy = review_room_from_specs(copy.deepcopy(base))
        self.assertNotIn("wall_fixation_geometry", legacy)
        self.assertNotIn("wall_fixation_sha256", legacy)
        _assert_safe_review(self, legacy, legacy["piece_count"])

        wall_revision = {
            "group_id": "ALTO", "module_id": "KITCHEN_1",
            "back_choice": "inset_carcass_material_review",
            "wall_system": "french_cleat_45", "support_choice": "keep_existing",
            "wall_substrate": "unknown",
        }
        fixation = {
            "group_id": "ALTO", "module_id": "KITCHEN_1",
            "system": "french_cleat_45", "length_mm": 900,
            "section_height_mm": 100, "thickness_mm": 15,
            "base_y_from_carcass_mm": 500, "rear_clearance_mm": 20,
            "confirm_external_clearance": True,
        }
        revisions: dict[int, dict] = {}
        for angle in (0, 90, 180, 270):
            request = copy.deepcopy(base)
            request["assemblies"][0]["origin_xyz_mm"] = [100, 0, 100]
            request["assemblies"][0]["rotation_deg"] = angle
            baseline_angle = review_room_from_specs(copy.deepcopy(request))
            request["wall_review_revisions"] = [wall_revision]
            request["wall_fixation_revisions"] = [fixation]
            review = review_room_from_specs(request)
            pair = review["wall_fixation_geometry"][0]
            validate_geometry(review["wall_fixation_geometry"],
                              review["wall_fixation_sha256"])
            self.assertEqual(review["wall_fixation_sha256"],
                             canonical_sha256(review["wall_fixation_geometry"]))
            self.assertEqual(review["layout_sha256"], baseline_angle["layout_sha256"])
            _assert_safe_review(self, review, legacy["piece_count"])
            self.assertEqual(pair["clearance_status"], "DECLARED_NOMINAL_SPACE_ONLY")
            self.assertEqual(pair["material_status"], "UNSPECIFIED_REVIEW_ONLY")
            self.assertIs(pair["install_ready"], False)
            self.assertEqual(len(pair["profiles"]), 2)
            self.assertEqual([len(profile["vertices_xyz_mm"]) for profile in pair["profiles"]],
                             [8, 8])
            self.assertEqual([len(profile["faces"]) for profile in pair["profiles"]],
                             [6, 6])
            expected_size = ([900, 58, 15] if angle in {0, 180}
                             else [15, 58, 900])
            self.assertEqual(pair["profiles"][0]["bounds_size_xyz_mm"], expected_size)
            self.assertTrue(all(value >= 0 for profile in pair["profiles"]
                                for point in profile["vertices_xyz_mm"] for value in point))
            revisions[angle] = review

        pair = revisions[0]["wall_fixation_geometry"][0]
        cabinet = pair["section_vertices_yz_mm"]["french_cleat_cabinet"]
        wall = pair["section_vertices_yz_mm"]["french_cleat_wall"]
        self.assertEqual({tuple(point) for point in cabinet[:2]},
                         {tuple(point) for point in wall[2:]})
        self.assertEqual(abs(cabinet[0][0] - cabinet[1][0]), 15)
        self.assertEqual(abs(cabinet[0][1] - cabinet[1][1]), 15)

        def area(points: list[list[int]]) -> float:
            return abs(sum(points[i][0] * points[(i + 1) % len(points)][1]
                           - points[(i + 1) % len(points)][0] * points[i][1]
                           for i in range(len(points)))) / 2

        combined_volume = (area(cabinet) + area(wall)) * fixation["length_mm"]
        self.assertEqual(combined_volume, 900 * 100 * 15)
        top = render_top_view_svg(pair_review := revisions[0])
        section = append_section_detail(
            render_room_panel_section_svg(pair_review, y_mm=350),
            pair_review["wall_fixation_geometry"],
        )
        html = render_room_3d_html(pair_review)
        self.assertIn("data-profile-id", top)
        self.assertIn("DETALLE VERTICAL YZ", section)
        self.assertIn("FRANCÉS 45°", section)
        self.assertIn("renderEntities", html)
        self.assertIn("WALLFIX:ALTO:KITCHEN_1:FRENCH_CLEAT_WALL", html)

        for choice, back in (
            ("none", "none"),
            ("inset_board_3mm_review", {
                "style": "inset_full", "material_id": "HDF_3_LAB",
                "thickness_mm": 3, "services_present": False, "grain_axis": "none",
            }),
            ("inset_board_15mm_review", {
                "style": "inset_full", "material_id": "MELAMINA_15",
                "thickness_mm": 15, "services_present": False, "grain_axis": "none",
            }),
            ("inset_board_18mm_review", {
                "style": "inset_full", "material_id": "MELAMINA_18",
                "thickness_mm": 18, "services_present": False, "grain_axis": "none",
            }),
        ):
            variant = copy.deepcopy(base)
            variant["assemblies"][0]["module_spec"]["modules"][0]["back"] = back
            baseline_variant = review_room_from_specs(copy.deepcopy(variant))
            variant["wall_review_revisions"] = [{
                **wall_revision, "back_choice": choice,
            }]
            variant["wall_fixation_revisions"] = [fixation]
            result = review_room_from_specs(variant)
            self.assertEqual(len(result["wall_fixation_geometry"]), 1, choice)
            self.assertEqual(result["wall_fixation_geometry"][0]["profiles"][0]["role"],
                             "french_cleat_cabinet", choice)
            self.assertEqual(result["layout_sha256"], baseline_variant["layout_sha256"])
            _assert_safe_review(self, result, baseline_variant["piece_count"])

        rejected = copy.deepcopy(base)
        rejected["wall_review_revisions"] = [wall_revision]
        rejected["wall_fixation_revisions"] = [{
            **fixation, "rear_clearance_mm": 14,
        }]
        with self.assertRaisesRegex(ValueError, "reserva posterior.*igual o mayor"):
            review_room_from_specs(rejected)
        rejected["wall_fixation_revisions"] = [{
            **fixation, "confirm_external_clearance": 1,
        }]
        with self.assertRaisesRegex(ValueError, "Confirma explícitamente"):
            review_room_from_specs(rejected)
        boundary = copy.deepcopy(base)
        boundary["assemblies"][0]["origin_xyz_mm"] = [100, 0, 19620]
        review_room_from_specs(copy.deepcopy(boundary))
        boundary["wall_review_revisions"] = [wall_revision]
        boundary["wall_fixation_revisions"] = [fixation]
        with self.assertRaisesRegex(ValueError, "excede el dominio espacial"):
            review_room_from_specs(boundary)

    def test_single_host_apply_reopen_offline_reject_and_remove(self) -> None:
        configured = os.environ.get("CARPN_H10_M2_QA_ROOT")
        self.assertTrue(configured, "CARPN_H10_M2_QA_ROOT debe apuntar a staging nuevo y absoluto")
        qa = Path(configured).resolve()
        self.assertTrue(qa.is_absolute())
        self.assertFalse(qa.exists(), f"No se sobrescribe evidencia previa: {qa}")
        qa.mkdir(parents=True, exist_ok=False)
        host_root = qa / "HOST"
        reopen_root = qa / "REOPEN_HOST"
        host_root.mkdir()
        source_files, source_manifest, source_review, source_request = _read_d19(M1_D19)
        self.assertNotIn("wall_fixation_geometry", source_review)
        self.assertEqual(hashlib.sha256(source_files["05-solicitud.json"]).hexdigest(),
                         "15985b8f4130da729045cf2e055e9e5b53924304bca3b0a7da3918e0c23f1f59")
        session = EditorSession(_read_input(M1_D19), host_root, 350)
        session.initialize()
        self.assertEqual(session.version, 1)
        self.assertEqual(session.current_review["layout_sha256"], source_review["layout_sha256"])
        _assert_safe_review(self, session.current_review, 45)

        server = create_server(session)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host_responses: list[dict[str, object]] = []
        page_errors: list[str] = []
        console_errors: list[str] = []
        external_requests: list[str] = []
        try:
            with _capture_apply_responses(server) as captured, sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 1180})
                page = context.new_page()
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on("console", lambda message: console_errors.append(message.text)
                        if message.type == "error" else None)
                page.on("request", lambda request: external_requests.append(request.url)
                        if request.url.startswith(("http://", "https://"))
                        and not request.url.startswith("http://127.0.0.1:") else None)
                page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="load")
                page.locator("#modulePicker").select_option(label="ALTO · KITCHEN_1")
                page.locator("#wallSystem").select_option("french_cleat_45")
                page.locator("#fixationAction").select_option("model")
                for selector, value in (
                    ("#fixLength", "900"), ("#fixHeight", "100"),
                    ("#fixThickness", "15"), ("#fixBaseY", "500"),
                    ("#fixClearance", "20"),
                ):
                    page.locator(selector).fill(value)
                page.locator("#confirmFixClearance").check()
                with page.expect_navigation(wait_until="load", timeout=60000):
                    page.locator("#applyModuleChanges").click()
                self.assertEqual(len(captured), 1)
                self.assertEqual(captured[0]["status"], 200)
                first_body = json.loads(captured[0]["body"])
                self.assertTrue(first_body["ok"])
                self.assertEqual(first_body["version"], 2)
                self.assertEqual(first_body["result"], "GEOMETRY_UPDATED")
                self.assertNotIn(session.token, captured[0]["body"])
                self.assertEqual(session.version, 2)
                applied_zip = host_root / "editor-v000002-room-review.zip"
                self.assertTrue(applied_zip.is_file())
                _copy_d19(applied_zip, qa / "D19_FRENCH_APPLIED")
                applied_files, applied_manifest, applied_review, applied_request = _read_d19(applied_zip)
                _assert_safe_review(self, applied_review, 45)
                self.assertEqual(applied_review["layout_sha256"], source_review["layout_sha256"])
                self.assertEqual(applied_files["06-paneles-en-escena.csv"],
                                 source_files["06-paneles-en-escena.csv"])
                self.assertEqual(set(applied_manifest["files"]), MEMBERS - {"MANIFEST.json"})
                pair = applied_review["wall_fixation_geometry"][0]
                self.assertEqual(pair["parameters"], {
                    "length_mm": 900, "section_height_mm": 100, "thickness_mm": 15,
                    "base_y_from_carcass_mm": 500, "rear_clearance_mm": 20,
                    "confirm_external_clearance": True,
                })
                self.assertEqual(pair["clearance_reservation"]["origin_xyz_mm"],
                                 [50, 1950, 365])
                self.assertEqual(pair["clearance_reservation"]["size_xyz_mm"],
                                 [900, 100, 20])
                self.assertEqual(pair["profiles"][0]["bounds_origin_xyz_mm"],
                                 [50, 1992, 365])
                self.assertEqual(pair["profiles"][0]["bounds_size_xyz_mm"],
                                 [900, 58, 15])
                self.assertEqual(pair["profiles"][1]["bounds_origin_xyz_mm"],
                                 [50, 1950, 365])
                self.assertEqual(pair["profiles"][1]["bounds_size_xyz_mm"],
                                 [900, 57, 15])
                self.assertEqual(applied_manifest["wall_fixation_sha256"],
                                 applied_review["wall_fixation_sha256"])
                self.assertEqual(len(pair["profiles"]), 2)
                self.assertEqual({box["piece_id"] for box in applied_review["world_boxes"]},
                                 set(source_review["global_piece_ids"]))

                page.wait_for_selector("#fixationView:not([hidden])")
                page.wait_for_function("document.getElementById('sceneCount').textContent.includes('45 tableros + 2 perfiles')")
                page.locator("#fixationVisibility").select_option("both")
                page.locator("#fixationRearView").click()
                page.screenshot(path=str(qa / "M2_FRENCH_APPLIED_REAR_BOTH.png"), full_page=True)
                page.locator("#focusModule").click()
                profile_id = "WALLFIX:ALTO:KITCHEN_1:FRENCH_CLEAT_WALL"
                page.locator("#piecePicker").select_option(profile_id)
                self.assertIn("Perfil nominal de revisión", page.locator("#details").inner_text())
                self.assertIn(profile_id, page.locator("#details").inner_text())
                page.screenshot(path=str(qa / "M2_FRENCH_PROFILE_PICK.png"), full_page=True)
                self.assertEqual(page_errors, [])
                self.assertEqual(console_errors, [])
                self.assertEqual(external_requests, [])
                host_responses = list(captured)
                browser.close()

            reopen_root.mkdir()
            reopened_request = _read_input(applied_zip)
            reopened = EditorSession(reopened_request, reopen_root, 350)
            reopened.initialize()
            self.assertEqual(reopened.version, 1)
            self.assertEqual(reopened.current_review["layout_sha256"], applied_review["layout_sha256"])
            self.assertEqual(reopened.current_review["wall_fixation_sha256"],
                             applied_review["wall_fixation_sha256"])
            _assert_safe_review(self, reopened.current_review, 45)
            reopen_server = create_server(reopened)
            reopen_thread = threading.Thread(target=reopen_server.serve_forever, daemon=True)
            reopen_thread.start()
            try:
                with _capture_apply_responses(reopen_server) as reopen_captured, sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    context = browser.new_context(accept_downloads=True,
                                                  viewport={"width": 1440, "height": 1180})
                    host_page = context.new_page()
                    host_page.on("pageerror", lambda error: page_errors.append(str(error)))
                    host_page.on("console", lambda message: console_errors.append(message.text)
                                 if message.type == "error" else None)
                    host_page.goto(f"http://127.0.0.1:{reopen_server.server_port}/", wait_until="load")
                    host_page.locator("#modulePicker").select_option(label="ALTO · KITCHEN_1")
                    self.assertEqual(host_page.locator("#fixLength").input_value(), "900")
                    self.assertEqual(host_page.locator("#fixHeight").input_value(), "100")
                    self.assertEqual(host_page.locator("#fixThickness").input_value(), "15")
                    self.assertEqual(host_page.locator("#fixBaseY").input_value(), "500")
                    self.assertEqual(host_page.locator("#fixClearance").input_value(), "20")

                    offline_path = (reopen_root / "editor-v000001" / "01-visor-3d.html").resolve()
                    self.assertTrue(offline_path.is_file())
                    offline_page = context.new_page()
                    offline_page_errors: list[str] = []
                    offline_external: list[str] = []
                    offline_page.on("pageerror", lambda error: offline_page_errors.append(str(error)))
                    offline_page.on("request", lambda request: offline_external.append(request.url)
                                    if request.url.startswith(("http://", "https://")) else None)
                    offline_page.goto(offline_path.as_uri(), wait_until="load")
                    offline_page.locator("#modulePicker").select_option(label="ALTO · KITCHEN_1")
                    offline_page.locator("#downloadFullRequest").click()
                    with offline_page.expect_download() as download_info:
                        offline_page.locator("#downloadFullRequestLink").click()
                    download = download_info.value
                    offline_json = qa / "offline-request.json"
                    download.save_as(str(offline_json))
                    offline_request = json.loads(offline_json.read_text(encoding="utf-8"))
                    self.assertEqual(offline_request, reopened.request)
                    self.assertNotIn(reopened.token, offline_json.read_text(encoding="utf-8"))
                    self.assertEqual(offline_page_errors, [])
                    self.assertEqual(offline_external, [])

                    before_zip_count = len(list(reopen_root.glob("*.zip")))
                    self.assertEqual(before_zip_count, 1)
                    host_page.locator("#fixationAction").select_option("model")
                    host_page.locator("#fixClearance").fill("14")
                    host_page.locator("#confirmFixClearance").check()
                    host_page.locator("#applyModuleChanges").click()
                    host_page.wait_for_function("document.getElementById('moduleEditStatus').textContent.includes('igual o mayor')")
                    self.assertEqual(len(reopen_captured), 1)
                    reject_body = json.loads(reopen_captured[0]["body"])
                    self.assertEqual(reopen_captured[0]["status"], 422)
                    self.assertFalse(reject_body["ok"])
                    self.assertEqual(reopened.version, 1)
                    self.assertEqual(len(list(reopen_root.glob("*.zip"))), before_zip_count)
                    self.assertEqual(reopened.current_review["wall_fixation_sha256"],
                                     applied_review["wall_fixation_sha256"])

                    host_page.locator("#fixationAction").select_option("preserve")
                    host_page.locator("#wallSystem").select_option("none")
                    with host_page.expect_navigation(wait_until="load", timeout=60000):
                        host_page.locator("#applyModuleChanges").click()
                    self.assertEqual(len(reopen_captured), 2)
                    remove_body = json.loads(reopen_captured[1]["body"])
                    self.assertEqual(reopen_captured[1]["status"], 200)
                    self.assertTrue(remove_body["ok"])
                    self.assertEqual(remove_body["version"], 2)
                    self.assertEqual(remove_body["result"], "GEOMETRY_UPDATED")
                    removed_zip = reopen_root / "editor-v000002-room-review.zip"
                    _copy_d19(removed_zip, qa / "D19_FRENCH_REMOVED")
                    removed_files, removed_manifest, removed_review, removed_request = _read_d19(removed_zip)
                    _assert_safe_review(self, removed_review, 45)
                    self.assertEqual(removed_review["layout_sha256"], applied_review["layout_sha256"])
                    self.assertEqual(removed_review["wall_fixation_geometry"], [])
                    self.assertEqual(removed_review["wall_fixation_sha256"], EMPTY_FIXATION_SHA256)
                    self.assertEqual(removed_manifest["wall_fixation_sha256"], EMPTY_FIXATION_SHA256)
                    self.assertEqual(removed_files["06-paneles-en-escena.csv"],
                                     source_files["06-paneles-en-escena.csv"])
                    self.assertEqual(removed_review["global_piece_ids"], source_review["global_piece_ids"])
                    self.assertEqual(len(list(reopen_root.glob("*.zip"))), before_zip_count + 1)
                    self.assertEqual(page_errors, [])
                    expected_rejection_console = (
                        "Failed to load resource: the server responded with a status of 422 "
                        "(Unprocessable Entity)"
                    )
                    self.assertEqual(
                        console_errors.count(expected_rejection_console), 1,
                    )
                    self.assertEqual(
                        [error for error in console_errors
                         if error != expected_rejection_console], [],
                    )
                    self.assertEqual(external_requests, [])
                    self.assertEqual(offline_external, [])
                    browser.close()
                    host_responses.extend(reopen_captured)
            finally:
                reopen_server.shutdown()
                reopen_server.server_close()
                reopen_thread.join(timeout=5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        _write_json(qa / "M2_EVIDENCE.json", {
            "result": "PASS_SCOPED",
            "source_d19_sha256": hashlib.sha256(M1_D19.read_bytes()).hexdigest(),
            "source_layout_sha256": source_review["layout_sha256"],
            "applied_layout_sha256": applied_review["layout_sha256"],
            "applied_wall_fixation_sha256": applied_review["wall_fixation_sha256"],
            "removed_wall_fixation_sha256": removed_review["wall_fixation_sha256"],
            "piece_count_wood_only": 45,
            "profile_entities_for_render": 2,
            "d19_members": 8,
            "manifest_members": 7,
            "http_responses": host_responses,
            "reopened_version": 1,
            "offline_request_semantically_equal": offline_request == reopened.request,
            "offline_token_absent": True,
            "rejected_clearance_created_no_version_or_file": True,
            "native_cad_generated": False,
            "physical_permissions": {flag: False for flag in FLAGS},
            "page_errors": page_errors,
            "console_errors": console_errors,
            "external_requests": external_requests + offline_external,
        })


if __name__ == "__main__":
    unittest.main()
