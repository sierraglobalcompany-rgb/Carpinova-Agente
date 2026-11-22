"""D18-R5 door invariants plus the R6 tool-build browser regression."""
from __future__ import annotations

import json
import math
import os
import re
import unittest
from pathlib import Path

from carpinova_agent.room_3d_review import render_room_3d_html
from carpinova_agent.room_spatial import review_room_from_specs


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "room-layout-kitchen-storage-review.json"
FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready",
    "purchase_ready", "can_generate_f7c",
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
            return [hinge_x + dx * cosine + dz * sine, yy,
                    hinge_z - dx * sine + dz * cosine]

        points = [rotate(point) for point in points]
    azimuth = math.radians(45 - yaw)
    elevation_radians = math.radians(elevation)
    cosine, sine = math.cos(elevation_radians), math.sin(elevation_radians)
    camera = [math.sin(azimuth) * cosine, sine, -math.cos(azimuth) * cosine]
    right = [math.cos(azimuth), 0, math.sin(azimuth)]
    up = [-math.sin(azimuth) * sine, cosine, math.cos(azimuth) * sine]
    relative = [[point[i] - pivot[i] for i in range(3)] for point in points]
    screen = [[_dot(right, point), -_dot(up, point)] for point in relative]
    depths = [_dot(camera, point) for point in relative]
    return {"id": box["id"], "role": box["role"], "screen": screen,
            "depths": depths, "average": sum(depths) / len(depths)}


def _signed_area(poly):
    return sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
               - poly[(i + 1) % len(poly)][0] * poly[i][1]
               for i in range(len(poly))) / 2


def _clip_polygon(subject, clipper):
    output = [point[:] for point in subject]
    orientation = 1 if _signed_area(clipper) >= 0 else -1
    for index, start in enumerate(clipper):
        end = clipper[(index + 1) % len(clipper)]
        incoming, output = output, []
        if not incoming:
            break

        def side(point):
            return orientation * ((end[0] - start[0]) * (point[1] - start[1])
                                  - (end[1] - start[1]) * (point[0] - start[0]))

        for i, current in enumerate(incoming):
            following = incoming[(i + 1) % len(incoming)]
            current_side, following_side = side(current), side(following)
            inside_current, inside_following = current_side >= -1e-7, following_side >= -1e-7
            if inside_current and inside_following:
                output.append(following)
            elif inside_current != inside_following:
                ratio = current_side / (current_side - following_side)
                intersection = [current[axis] + ratio * (following[axis] - current[axis])
                                for axis in range(2)]
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
        return [hinge_x + dx * cosine + dz * sine, yy,
                hinge_z - dx * sine + dz * cosine]

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
    def test_rigid_doors_and_scene_identity_survive_r6_renderer(self):
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
        self.assertEqual(scene["digest"], review["layout_sha256"])
        self.assertEqual([box["id"] for box in scene["boxes"]],
                         [box["piece_id"] for box in review["world_boxes"]])
        script = re.search(r"<script>\s*(.*?)</script>", html, re.DOTALL).group(1)
        self.assertNotIn("painterKey", script)
        self.assertNotIn("all.sort", script)

        edge_checks = 0
        for box in scene["boxes"]:
            if box["role"] not in ("front_left", "front_right"):
                continue
            baseline = _edge_lengths(box, 0)
            for angle in (0, 30, 60, 90):
                moved = _edge_lengths(box, angle)
                self.assertEqual(len(moved), 12)
                for actual, expected in zip(moved, baseline):
                    self.assertAlmostEqual(actual, expected, delta=1e-6)
                edge_checks += len(moved)
        self.assertEqual(edge_checks, 96)

    @unittest.skipUnless(os.environ.get("CARPN_D18_R6_TOOL_HTML"),
                         "integrated tool package is supplied by the D18-R6 E2E run")
    def test_right30_pixel_hit_and_single_browser_session(self):
        html_path = Path(os.environ["CARPN_D18_R6_TOOL_HTML"])
        evidence_dir = Path(os.environ["CARPN_D18_R6_EVIDENCE_DIR"])
        evidence_dir.mkdir(parents=True, exist_ok=True)
        html = html_path.read_text(encoding="utf-8")
        match = re.search(
            r'<script id="scene-data" type="application/json">(.*?)</script>', html, re.DOTALL
        )
        self.assertIsNotNone(match)
        scene = json.loads(match.group(1))
        self.assertEqual(len(scene["boxes"]), 8)
        self.assertEqual(len({box["id"] for box in scene["boxes"]}), 8)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:  # pragma: no cover - environment-specific blocker
            self.fail(f"BROWSER=NOT_RUN_ENV: Playwright unavailable: {error}")

        js_errors, external_requests, observed, captures = [], [], [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda error: js_errors.append(str(error)))
            page.on("console", lambda message: js_errors.append(message.text)
                    if message.type == "error" else None)
            page.on("request", lambda request: external_requests.append(request.url)
                    if request.url.startswith(("http://", "https://")) else None)
            page.set_content(html, wait_until="load")
            self.assertEqual(page.locator("#panels image[data-depth-tested='true']").count(), 1)
            page.locator('#views button[data-yaw="0"]').click()
            self.assertIn("Giro 0°", page.locator("#cameraReadout").inner_text())
            _set_door(page, 0, 0)
            _set_door(page, 1, 0)
            capture = evidence_dir / "01-cerrado-frontal.png"
            page.screenshot(path=str(capture), full_page=True)
            captures.append(capture.name)

            _set_door(page, 1, 30)
            browser_scene = json.loads(page.locator("#scene-data").inner_text())
            boxes = browser_scene["boxes"]
            left = next(box for box in boxes if box["role"] == "front_left")
            right = next(box for box in boxes if box["role"] == "front_right")
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
            deltas = [_depth_at(open_face, point) - _depth_at(closed_face, point)
                      for point in samples]
            self.assertTrue(all(delta > 0.01 for delta in deltas), deltas)

            selected_from_overlap = None
            for point in samples:
                client = page.locator("#scene").evaluate(
                    "(svg, p) => {const q=svg.createSVGPoint();q.x=p[0];q.y=p[1];"
                    "const r=q.matrixTransform(svg.getScreenCTM());return [r.x,r.y]}", point,
                )
                page.mouse.click(client[0], client[1])
                if page.locator("#piecePicker").input_value() == right["id"]:
                    selected_from_overlap = right["id"]
                    break
            self.assertEqual(selected_from_overlap, right["id"],
                             "visible overlap pixel must select the nearest open right door")
            capture = evidence_dir / "02-derecha30-yaw0.png"
            page.screenshot(path=str(capture), full_page=True)
            captures.append(capture.name)
            observed.append({"case": "RIGHT30_YAW0", "overlap_area_svg_units": overlap_area,
                             "depth_delta_mm": [min(deltas), max(deltas)],
                             "selected_piece_id": selected_from_overlap, "result": "PASS"})

            before_drag_selection = page.locator("#piecePicker").input_value()
            before_drag_camera = page.locator("#cameraReadout").inner_text()
            rect = page.locator("#scene").bounding_box()
            sx, sy = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2
            page.mouse.move(sx, sy)
            page.mouse.down()
            page.mouse.move(sx + 60, sy, steps=4)
            page.mouse.up()
            self.assertIn("Giro 30°", page.locator("#cameraReadout").inner_text())
            self.assertNotEqual(before_drag_camera, page.locator("#cameraReadout").inner_text())
            self.assertEqual(before_drag_selection, page.locator("#piecePicker").input_value())
            _set_door(page, 0, 90)
            _set_door(page, 1, 90)
            capture = evidence_dir / "03-ambas90-yaw30.png"
            page.screenshot(path=str(capture), full_page=True)
            captures.append(capture.name)
            observed.append({"case": "BOTH90_YAW30_DRAG_PRESERVES_SELECTION", "result": "PASS"})

            _set_door(page, 0, 0)
            _set_door(page, 1, 60)
            rect = page.locator("#scene").bounding_box()
            sx, sy = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2
            page.mouse.move(sx, sy)
            page.mouse.down()
            page.mouse.move(sx + 30, sy, steps=3)
            page.mouse.up()
            self.assertIn("Giro 45°", page.locator("#cameraReadout").inner_text())
            capture = evidence_dir / "04-derecha60-yaw45.png"
            page.screenshot(path=str(capture), full_page=True)
            captures.append(capture.name)
            observed.append({"case": "RIGHT60_YAW45", "result": "PASS"})

            for angle in (0, 90, 180, 270):
                page.locator(f'#views button[data-yaw="{angle}"]').click()
                self.assertIn(f"Giro {angle}°", page.locator("#cameraReadout").inner_text())
            page.locator("#zoom").evaluate(
                "el => {el.value='130';el.dispatchEvent(new Event('input',{bubbles:true}))}"
            )
            self.assertEqual(page.locator("#zoomLabel").inner_text(), "130 %")
            page.locator("#interior").check()
            self.assertTrue(page.locator("#interiorBanner").is_visible())
            page.locator("#interior").uncheck()
            page.locator("#cutEnabled").check()
            page.locator("#cutHeight").fill("350")
            page.locator("#cutEnabled").uncheck()
            picker = page.locator("#piecePicker")
            picker.focus()
            picker.press("ArrowDown")
            picker.press("Enter")
            self.assertTrue(picker.input_value())
            page.locator("#resetView").click()
            self.assertIn("Giro 0°", page.locator("#cameraReadout").inner_text())
            self.assertEqual(page.locator("#zoom").input_value(), "100")
            self.assertEqual(page.locator("#doorSliders input").evaluate_all(
                "els => els.map(el => el.value)"), ["0", "0"])
            self.assertFalse(js_errors, js_errors)
            self.assertFalse(external_requests, external_requests)
            browser.close()

        report = {"browser": "PASS_SCOPED", "cases": observed,
                  "js_errors": js_errors, "external_requests": external_requests,
                  "captures": captures, "piece_count": len(scene["boxes"])}
        (evidence_dir / "TOOL_BROWSER.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("D18R6_BROWSER=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
