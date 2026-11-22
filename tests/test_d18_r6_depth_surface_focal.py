"""D18-R6 focal contract for the offline per-pixel depth viewer."""
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


class D18R6DepthSurfaceFocal(unittest.TestCase):
    def test_verified_scene_uses_depth_and_id_buffers_without_changing_cad(self):
        request = json.loads(SAMPLE.read_text(encoding="utf-8"))
        review = review_room_from_specs(request)
        original = json.dumps(review, sort_keys=True, separators=(",", ":"))
        html = render_room_3d_html(review)
        self.assertEqual(original, json.dumps(review, sort_keys=True, separators=(",", ":")))
        self.assertEqual(review["piece_count"], 8)
        self.assertTrue(all(review[flag] is False for flag in PHYSICAL_FLAGS))

        embedded = re.search(
            r'<script id="scene-data" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(embedded)
        scene = json.loads(embedded.group(1))
        self.assertEqual(scene["digest"], review["layout_sha256"])
        self.assertEqual(
            [box["id"] for box in scene["boxes"]],
            [box["piece_id"] for box in review["world_boxes"]],
        )
        self.assertEqual(len(set(box["id"] for box in scene["boxes"])), 8)

        match = re.search(r"<script>\s*(.*?)</script>", html, re.DOTALL)
        self.assertIsNotNone(match)
        script = match.group(1)
        for observable in (
            "MAX_RASTER_PIXELS=1000000",
            "new Float32Array(pixelCount)",
            "new Int16Array(pixelCount)",
            "ctx.putImageData(imageData,0,0)",
            "canvas.toDataURL('image/png')",
            "data-depth-tested",
            "const panelAt=",
            "matrix.inverse()",
            "Math.abs(determinant)",
            "VISOR_NO_DISPONIBLE",
        ):
            self.assertTrue(observable in script + html,
                            f"missing renderer observable: {observable}")
        self.assertNotIn("all.sort", script)
        self.assertNotIn("painterKey", script)
        self.assertNotIn("data-piece-id", script)
        self.assertIn("piecePicker", html)
        self.assertIn("NO FABRICAR / NO CORTAR / NO PERFORAR / NO COMPRAR", html)
        self.assertNotRegex(html, r"(?i)<script\s+src=")
        self.assertNotIn("https://", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
