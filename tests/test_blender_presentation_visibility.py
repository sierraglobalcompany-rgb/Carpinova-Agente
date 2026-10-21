"""Unit regressions for visibility of Blender's saved PNG (not geometry)."""
import unittest

from integrations.blender_presentation import assert_visible_preview


class PresentationVisibilityTests(unittest.TestCase):
    def test_reject_real_ci_black_rgb_zero_or_one(self):
        pixels = ([0.0, 0.0, 0.0, 1.0] * 100
                  + [1 / 255, 1 / 255, 1 / 255, 1.0] * 100)
        with self.assertRaisesRegex(ValueError, "oscuro"):
            assert_visible_preview(pixels)

    def test_reject_plain_white_without_objects(self):
        with self.assertRaisesRegex(ValueError, "contraste"):
            assert_visible_preview([0.9, 0.9, 0.9, 1.0] * 200)

    def test_allow_studio_scene_with_visible_panels(self):
        assert_visible_preview(([0.9, 0.92, 0.95, 1.0] * 100
                               + [0.48, 0.34, 0.15, 1.0] * 100))

    def test_invalid_rgba_length_is_rejected(self):
        for pixels in ([], [0.9], [0.9, 0.9, 0.9, 1.0] * 2):
            with self.subTest(pixels=pixels), self.assertRaises(ValueError):
                assert_visible_preview(pixels)


if __name__ == "__main__":
    unittest.main()
