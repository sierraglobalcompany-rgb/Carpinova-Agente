"""D18-R5 focal browser check for open/closed door painter ordering."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from carpinova_agent.room_3d_review import render_room_3d_html
from carpinova_agent.room_spatial import review_room_from_specs


SAMPLE = ROOT / "examples" / "room-layout-kitchen-storage-review.json"
FLAGS = (
    "fabrication_ready",
    "cutting_ready",
    "drilling_ready",
    "purchase_ready",
    "can_generate_f7c",
)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _front_face(box, angle_deg, pivot, yaw=0, elevation=35):
    x, y, z = box["origin"]
    w, h, d = box["size"]
    points = [[x, y, z], [x + w, y, z], [x + w, y + h, z], [x, y + h, z]]
    if angle_deg:
        left = box["role"] == "front_left"
        hinge_x = x if left else x + w
        hinge_z = z + d / 2
        theta = (1 if left else -1) * math.radians(angle_deg)
        cosine, sine = math.cos(theta), math.sin(theta)

        def rotate(point):
            xx, yy, zz = point
            dx, dz = xx - hinge_x, zz - hinge_z
            return [hinge_x + dx * cosine + dz * sine, yy, hinge_z - dx * sine + dz * cosine]

        points = [rotate(point) for point in points]

    azimuth = math.radians(45 - yaw)
    elevation = math.radians(elevation)
    cosine, sine = math.cos(elevation), math.sin(elevation)
    camera = [math.sin(azimuth) * cosine, sine, -math.cos(azimuth) * cosine]
    right = [math.cos(azimuth), 0, math.sin(azimuth)]
    up = [-math.sin(azimuth) * sine, cosine, math.cos(azimuth) * sine]
    relative = [[point[i] - pivot[i] for i in range(3)] for point in points]
    screen = [[_dot(right, point), -_dot(up, point)] for point in relative]
    depths = [_dot(camera, point) for point in relative]
    return {
        "id": box["id"],
        "role": box["role"],
        "screen": screen,
        "depths": depths,
        "average": sum(depths) / len(depths),
        "world": points,
    }


def _signed_area(poly):
    return sum(
        poly[i][0] * poly[(i + 1) % len(poly)][1]
        - poly[(i + 1) % len(poly)][0] * poly[i][1]
        for i in range(len(poly))
    ) / 2


def _clip_polygon(subject, clipper):
    output = [point[:] for point in subject]
    orientation = 1 if _signed_area(clipper) >= 0 else -1
    for index, start in enumerate(clipper):
        end = clipper[(index + 1) % len(clipper)]
        incoming, output = output, []
        if not incoming:
            break

        def side(point):
            return orientation * (
                (end[0] - start[0]) * (point[1] - start[1])
                - (end[1] - start[1]) * (point[0] - start[0])
            )

        for i, current in enumerate(incoming):
            following = incoming[(i + 1) % len(incoming)]
            current_side, following_side = side(current), side(following)
            inside_current, inside_following = current_side >= -1e-7, following_side >= -1e-7
            if inside_current and inside_following:
                output.append(following)
            elif inside_current != inside_following:
                ratio = current_side / (current_side - following_side)
                intersection = [
                    current[axis] + ratio * (following[axis] - current[axis])
                    for axis in range(2)
                ]
                output.append(intersection)
                if inside_following:
                    output.append(following)
    return output


def _depth_at(face, point):
    (x0, y0), (x1, y1), (x2, y2) = face["screen"][:3]
    d0, d1, d2 = face["depths"][:3]
    determinant = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    a = ((d1 - d0) * (y2 - y0) - (d2 - d0) * (y1 - y0)) / determinant
    b = ((x1 - x0) * (d2 - d0) - (x2 - x0) * (d1 - d0)) / determinant
    c = d0 - a * x0 - b * y0
    return a * point[0] + b * point[1] + c


def _edge_lengths(box, angle_deg):
    x, y, z = box["origin"]
    w, h, d = box["size"]
    corners = [[x + w * ix, y + h * iy, z + d * iz]
               for ix, iy, iz in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                                  (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))]
    left = box["role"] == "front_left"
    hinge_x = x if left else x + w
    hinge_z = z + d / 2
    theta = (1 if left else -1) * math.radians(angle_deg)
    cosine, sine = math.cos(theta), math.sin(theta)

    def rotate(point):
        xx, yy, zz = point
        dx, dz = xx - hinge_x, zz - hinge_z
        return [hinge_x + dx * cosine + dz * sine, yy, hinge_z - dx * sine + dz * cosine]

    moved = [rotate(point) for point in corners]
    edges = [(i, j) for i in range(8) for j in range(i + 1, 8)
             if sum(a != b for a, b in zip(corners[i], corners[j])) == 1]
    return sorted(math.dist(moved[i], moved[j]) for i, j in edges)


def _set_door(page, index, angle):
    page.locator("#doorSliders input").nth(index).evaluate(
        "(el, value) => { el.value = String(value); el.dispatchEvent(new Event('input', {bubbles: true})); }",
        angle,
    )


class D18R5DoorOcclusionFocal(unittest.TestCase):
    def test_rigid_doors_and_adversarial_painter_output(self):
        request = json.loads(SAMPLE.read_text(encoding="utf-8"))
        review = review_room_from_specs(request)
        original = json.dumps(review, sort_keys=True, separators=(",", ":"))
        html = render_room_3d_html(review)
        self.assertEqual(original, json.dumps(review, sort_keys=True, separators=(",", ":")))
        self.assertEqual(review["piece_count"], 8)
        self.assertTrue(all(review[flag] is False for flag in FLAGS))

        embedded = re.search(
            r'<script id="scene-data" type="application/json">(.*?)</script>', html, re.DOTALL
        )
        self.assertIsNotNone(embedded)
        scene = json.loads(embedded.group(1))
        expected_boxes = [
            {"id": box["piece_id"], "group": box["group_id"], "role": box["role"],
             "origin": box["origin_xyz_mm"], "size": box["size_xyz_mm"]}
            for box in review["world_boxes"]
        ]
        self.assertEqual(scene["boxes"], expected_boxes)
        self.assertEqual(scene["digest"], review["layout_sha256"])
        self.assertEqual(len({box["id"] for box in scene["boxes"]}), 8)
        script = re.search(r"<script>\s*(.*?)</script>", html, re.DOTALL).group(1)
        self.assertIn("const painterKey=entry=>[", script)
        self.assertIn("ka[0]-kb[0]||ka[1]-kb[1]||ka[2]-kb[2]", script)
        self.assertIn("order:boxIndex*6+face.faceIndex", script)

        edge_checks = 0
        for box in scene["boxes"]:
            if box["role"] not in ("front_left", "front_right"):
                continue
            baseline = _edge_lengths(box, 0)
            for angle in (0, 30, 60, 90):
                moved = _edge_lengths(box, angle)
                self.assertEqual(len(moved), 12)
                self.assertEqual(len(baseline), 12)
                for actual, expected in zip(moved, baseline):
                    self.assertAlmostEqual(actual, expected, delta=1e-6)
                edge_checks += len(moved)
        self.assertEqual(edge_checks, 96)

        v2_zip = Path(os.environ["CARPN_D18_R5_V2_ZIP"])
        with zipfile.ZipFile(v2_zip) as archive:
            self.assertIsNone(archive.testzip())
            v2_html_bytes = archive.read("EVIDENCIA/VISOR_FINAL.html")
            manifest = json.loads(archive.read("MANIFEST.json"))
            html_record = next(item for item in manifest["files_excluding_manifest"]
                               if item["path"] == "EVIDENCIA/VISOR_FINAL.html")
            self.assertEqual(hashlib.sha256(v2_html_bytes).hexdigest(), html_record["sha256"])
        v2_html = v2_html_bytes.decode("utf-8")
        v2_scene_match = re.search(
            r'<script id="scene-data" type="application/json">(.*?)</script>', v2_html, re.DOTALL
        )
        self.assertIsNotNone(v2_scene_match)
        self.assertEqual(json.loads(v2_scene_match.group(1)), scene)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:  # pragma: no cover - environment-specific blocker
            self.fail(f"BROWSER=NOT_RUN_ENV: Playwright unavailable: {error}")

        js_errors, external_requests, observed = [], [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda error: js_errors.append(str(error)))
            page.on("console", lambda message: js_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("request", lambda request: external_requests.append(request.url)
                    if request.url.startswith(("http://", "https://")) else None)
            # RED_V2: exercise the delivered HTML, not a recreated approximation.
            page.set_content(v2_html, wait_until="load")
            page.locator('#views button[data-yaw="0"]').click()
            _set_door(page, 0, 0)
            _set_door(page, 1, 30)
            browser_scene = json.loads(page.locator("#scene-data").inner_text())
            browser_boxes = browser_scene["boxes"]
            left = next(box for box in browser_boxes if box["role"] == "front_left")
            right = next(box for box in browser_boxes if box["role"] == "front_right")
            mins = [min(group["origin"][i] for group in browser_scene["groups"]) for i in range(3)]
            maxs = [max(group["origin"][i] + group["size"][i]
                        for group in browser_scene["groups"]) for i in range(3)]
            pivot = [(mins[i] + maxs[i]) / 2 for i in range(3)]
            closed_face = _front_face(left, 0, pivot)
            open_face = _front_face(right, 30, pivot)
            overlap = _clip_polygon(open_face["screen"], closed_face["screen"])
            overlap_area = abs(_signed_area(overlap))
            self.assertGreater(overlap_area, 1000)
            samples = overlap + [[sum(p[0] for p in overlap) / len(overlap),
                                  sum(p[1] for p in overlap) / len(overlap)]]
            depth_deltas = [_depth_at(open_face, point) - _depth_at(closed_face, point)
                            for point in samples]
            self.assertTrue(all(delta > 0.01 for delta in depth_deltas), depth_deltas)

            def rendered_index(face):
                rendered = page.locator("#panels polygon").evaluate_all(
                    "els => els.map((el, index) => ({index, id: el.dataset.pieceId, "
                    "role: el.dataset.role, depth: Number(el.dataset.depth)}))"
                )
                matches = [entry["index"] for entry in rendered
                           if entry["id"] == face["id"]
                           and abs(entry["depth"] - face["average"]) < 1e-4]
                self.assertEqual(len(matches), 1, (face["role"], face["average"], matches))
                return matches[0]

            red_open_index = rendered_index(open_face)
            red_closed_index = rendered_index(closed_face)
            self.assertLess(red_open_index, red_closed_index,
                            "V2 must reproduce the false overlay in right-30 case")
            observed.append({"case": "RED_V2_yaw0_left0_right30", "overlap_area": overlap_area,
                             "open_minus_closed_depth_mm": [min(depth_deltas), max(depth_deltas)],
                             "open_dom_index": red_open_index,
                             "closed_dom_index": red_closed_index,
                             "result": "FAIL_REPRODUCED"})

            # GREEN_V4 uses the actual updated renderer at the same state.
            # A new page avoids redeclaring the prior document's top-level const bindings.
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda error: js_errors.append(str(error)))
            page.on("console", lambda message: js_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("request", lambda request: external_requests.append(request.url)
                    if request.url.startswith(("http://", "https://")) else None)
            page.set_content(html, wait_until="load")
            self.assertEqual(json.loads(page.locator("#scene-data").inner_text()), scene)
            page.locator('#views button[data-yaw="0"]').click()
            _set_door(page, 0, 0)
            _set_door(page, 1, 30)
            green_open_index = rendered_index(open_face)
            green_closed_index = rendered_index(closed_face)
            self.assertGreater(green_open_index, green_closed_index,
                               "the nearer open leaf must be painted after its closed sibling")

            # Three actual DOM trios follow the fixed lexicographic layer/depth key.
            records = page.locator("#panels polygon").evaluate_all(
                "els => els.map((el,index)=>({index,id:el.dataset.pieceId,role:el.dataset.role,depth:Number(el.dataset.depth)}))"
            )
            layer = lambda role: 0 if role in ("back_full", "shelf_horizontal") else 1
            by_role = {role: [item for item in records if item["role"] == role]
                       for role in {item["role"] for item in records}}
            def face_record(face):
                return next(item for item in records if item["id"] == face["id"]
                            and abs(item["depth"] - face["average"]) < 1e-4)
            closed_record, open_record = face_record(closed_face), face_record(open_face)
            triples = []
            for label, role in (("doors_top", "top"), ("doors_shelf", "shelf_horizontal"),
                                ("doors_side", "right_side")):
                self.assertTrue(by_role.get(role), role)
                choices = ([closed_record, open_record, third]
                           for third in by_role[role])
                triple = next((items for items in choices
                               if len({(layer(item["role"]), item["depth"]) for item in items}) == 3), None)
                self.assertIsNotNone(triple, label)
                expected = sorted(triple, key=lambda item: (layer(item["role"]), item["depth"]))
                actual = sorted(triple, key=lambda item: item["index"])
                self.assertEqual([item["index"] for item in actual],
                                 [item["index"] for item in expected], label)
                triples.append({"name": label,
                                "keys": [[layer(item["role"]), item["depth"]] for item in triple],
                                "dom_indexes": [item["index"] for item in triple]})
            observed.append({"case": "GREEN_V4_yaw0_left0_right30", "overlap_area": overlap_area,
                             "open_minus_closed_depth_mm": [min(depth_deltas), max(depth_deltas)],
                             "open_dom_index": green_open_index,
                             "closed_dom_index": green_closed_index,
                             "transitivity_triples": triples, "result": "PASS"})

            # Closed fronts retain priority over the cabinet interior from the front.
            _set_door(page, 1, 0)
            closed_dom = page.locator("#panels polygon").evaluate_all(
                "els => els.map((el, index) => ({index, role: el.dataset.role, depth: Number(el.dataset.depth)}))"
            )
            left_face_depth = _front_face(left, 0, pivot)["average"]
            left_face_index = next(entry["index"] for entry in closed_dom
                                   if entry["role"] == "front_left"
                                   and abs(entry["depth"] - left_face_depth) < 1e-4)
            shelf_indices = [entry["index"] for entry in closed_dom
                             if entry["role"] == "shelf_horizontal"]
            self.assertTrue(shelf_indices)
            self.assertGreater(left_face_index, max(shelf_indices))

            # Keep the affected 60° regression; door input must preserve camera and zoom.
            page.locator("#zoom").evaluate(
                "el => {el.value='120';el.dispatchEvent(new Event('input',{bubbles:true}))}"
            )
            before_camera = page.locator("#cameraReadout").inner_text()
            _set_door(page, 1, 60)
            self.assertEqual(page.locator("#cameraReadout").inner_text(), before_camera)
            self.assertEqual(page.locator("#zoom").input_value(), "120")
            sixty_open = _front_face(right, 60, pivot)
            self.assertGreater(rendered_index(sixty_open), rendered_index(closed_face))
            observed.append({"case": "regression_yaw0_left0_right60", "result": "PASS"})

            # A drag rotates; it must not become a click that changes the selected piece.
            page.locator('#views button[data-yaw="0"]').click()
            polygon = page.locator("#panels polygon").last
            selected_id = polygon.get_attribute("data-piece-id")
            polygon.click(force=True)
            self.assertEqual(page.locator("#piecePicker").input_value(), selected_id)
            before_drag = page.locator("#cameraReadout").inner_text()
            rect = polygon.bounding_box()
            sx, sy = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2
            page.mouse.move(sx, sy)
            page.mouse.down()
            page.mouse.move(sx + 30, sy + 14, steps=5)
            page.mouse.up()
            self.assertNotEqual(page.locator("#cameraReadout").inner_text(), before_drag)
            drag_selected_after = page.locator("#piecePicker").input_value()
            self.assertEqual(drag_selected_after, selected_id)
            observed.append({
                "case": "drag_vs_click",
                "selected_before": selected_id,
                "selected_after": drag_selected_after,
                "result": "PASS",
            })

            page.locator("#interior").check()
            self.assertTrue(page.locator("#interiorBanner").is_visible())
            page.locator("#interior").uncheck()
            page.locator("#cutEnabled").check()
            page.locator("#cutHeight").fill("350")
            page.locator("#cutEnabled").uncheck()
            page.locator("#resetView").click()
            self.assertIn("Giro 0°", page.locator("#cameraReadout").inner_text())
            self.assertEqual(page.locator("#zoom").input_value(), "100")
            self.assertEqual(page.locator("#doorSliders input").evaluate_all(
                "els => els.map(el => el.value)"), ["0", "0"])
            self.assertEqual(json.loads(page.locator("#scene-data").inner_text()), scene)
            warning = page.locator("div.warn").first.inner_text()
            self.assertIn("APERTURA VISUAL NOMINAL", warning)
            self.assertIn("NO FABRICAR / NO CORTAR / NO PERFORAR / NO COMPRAR",
                          warning)
            self.assertFalse(js_errors, js_errors)
            self.assertFalse(external_requests, external_requests)
            browser.close()

        print("D18R5_FOCAL_CASES=" + json.dumps(observed, sort_keys=True))
        print("D18R5_EDGE_LENGTHS=96/96; PIECES=8; FLAGS=false; JS_ERRORS=0; NETWORK_REQUESTS=0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
