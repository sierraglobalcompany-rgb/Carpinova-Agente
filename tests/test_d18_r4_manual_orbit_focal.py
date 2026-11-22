"""One focal D18-R4 contract test over the existing eight-panel sample."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from carpinova_agent.room_3d_review import render_room_3d_html
from carpinova_agent.room_spatial import review_room_from_specs


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "room-layout-kitchen-storage-review.json"
PHYSICAL_FLAGS = (
    "fabrication_ready", "cutting_ready", "drilling_ready",
    "purchase_ready", "can_generate_f7c",
)


class D18R4ManualOrbitFocal(unittest.TestCase):
    def test_continuous_orbit_controls_preserve_real_scene_and_safety(self):
        request = json.loads(SAMPLE.read_text(encoding="utf-8"))
        review = review_room_from_specs(request)
        original = json.dumps(review, sort_keys=True, separators=(",", ":"))
        html = render_room_3d_html(review)

        self.assertEqual(review["piece_count"], 8)
        self.assertTrue(all(review[flag] is False for flag in PHYSICAL_FLAGS))
        self.assertEqual(
            original,
            json.dumps(review, sort_keys=True, separators=(",", ":")),
        )
        embedded = re.search(
            r'<script id="scene-data" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(embedded)
        scene = json.loads(embedded.group(1))
        expected_boxes = [
            {
                "id": box["piece_id"],
                "group": box["group_id"],
                "role": box["role"],
                "origin": box["origin_xyz_mm"],
                "size": box["size_xyz_mm"],
            }
            for box in review["world_boxes"]
        ]
        self.assertEqual(scene["boxes"], expected_boxes)
        self.assertEqual(scene["digest"], review["layout_sha256"])
        self.assertEqual(len({box["id"] for box in scene["boxes"]}), 8)

        script = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
        self.assertIsNotNone(script)
        js = script.group(1)
        self.assertIn("let yaw=0,elevation=INITIAL_ELEVATION", js)
        self.assertIn("const cameraState=", js)
        self.assertIn("dot(normals[index],camera.position)", js)
        self.assertIn('id="cameraReadout"', html)
        self.assertNotRegex(js, r"\bheading\s*={2,3}")
        self.assertNotIn("paintLayer", js)

        for control in (
            'id="scene"', 'id="zoom"',
            'id="resetView"', 'id="interior"', 'id="cutEnabled"',
            'id="piecePicker"', 'id="doorSliders"',
            "pointerdown", "pointermove", "pointerup", "pointercancel",
            "lostpointercapture", "setPointerCapture", "suppressClickUntil",
            "aria-pressed", "addEventListener('wheel'", "{passive:false}",
            "Arrastra sobre el mueble para girar · rueda para ampliar.",
        ):
            self.assertIn(control, html)
        self.assertIn("clamp(pointerDrag.elevation-dy*.35,15,75)", js)
        self.assertIn("zoom.value", js)
        self.assertIn("doorAngles.clear()", js)
        self.assertIn("doorAngles.set(box.id,a)", js)
        self.assertIn("document.querySelectorAll('#groups input[type=checkbox]')", js)
        self.assertIn("NO FABRICAR / NO CORTAR / NO PERFORAR / NO COMPRAR", html)
        self.assertNotRegex(html, r"(?i)<script\s+src=")
        self.assertNotIn("WebGL", html)


if __name__ == "__main__":
    unittest.main()
