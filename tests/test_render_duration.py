import unittest

from app.render import _duration_target_warning


class RenderDurationWarningTests(unittest.TestCase):
    def test_warns_when_render_is_shorter_than_requested(self):
        warning = _duration_target_warning(600, 240)
        self.assertIn("4.0 min", warning)
        self.assertIn("10.0 min", warning)
        self.assertIn("ampliá las escenas", warning)

    def test_does_not_warn_when_duration_is_close_enough(self):
        self.assertEqual(_duration_target_warning(600, 500), "")

    def test_does_not_warn_when_no_target_was_set(self):
        self.assertEqual(_duration_target_warning(0, 90), "")


if __name__ == "__main__":
    unittest.main()
