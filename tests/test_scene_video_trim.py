import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.main import ScenePatch, patch_scene
from app.render import _visual_input_args


class SceneVideoTrimTests(unittest.TestCase):
    def test_video_input_uses_entire_source_when_trim_is_unset(self):
        args = _visual_input_args(Path("clip.mp4"), 30)
        self.assertEqual(args, ["-stream_loop", "-1", "-i", "clip.mp4"])

    def test_video_input_uses_selected_source_window(self):
        args = _visual_input_args(Path("clip.mov"), 30, 2.25, 7.75)
        self.assertEqual(args, ["-stream_loop", "-1", "-ss", "2.250", "-t", "5.500", "-i", "clip.mov"])

    def test_video_input_can_start_at_offset_without_end_limit(self):
        args = _visual_input_args(Path("clip.webm"), 25, 3.0, 0)
        self.assertEqual(args, ["-stream_loop", "-1", "-ss", "3.000", "-i", "clip.webm"])

    def test_still_images_do_not_receive_video_trim_arguments(self):
        args = _visual_input_args(Path("still.png"), 25, 3.0, 8.0)
        self.assertEqual(args, ["-loop", "1", "-framerate", "25", "-i", "still.png"])

    def test_patch_rejects_negative_trim_values(self):
        scene = {"id": 7, "project_id": 3, "visual_trim_start_sec": 0, "visual_trim_end_sec": 0}
        with patch("app.main.db.query_one", return_value=scene):
            with self.assertRaises(HTTPException) as error:
                patch_scene(7, ScenePatch(visual_trim_start_sec=-1))
        self.assertEqual(error.exception.status_code, 400)

    def test_patch_rejects_end_before_start(self):
        scene = {"id": 7, "project_id": 3, "visual_trim_start_sec": 0, "visual_trim_end_sec": 4}
        with patch("app.main.db.query_one", return_value=scene):
            with self.assertRaises(HTTPException) as error:
                patch_scene(7, ScenePatch(visual_trim_start_sec=5))
        self.assertEqual(error.exception.status_code, 400)

    def test_patch_rejects_trim_past_source_duration(self):
        scene = {"id": 7, "project_id": 3, "visual_trim_start_sec": 0, "visual_trim_end_sec": 0, "visual_source_duration_sec": 8}
        with patch("app.main.db.query_one", return_value=scene):
            with self.assertRaises(HTTPException) as error:
                patch_scene(7, ScenePatch(visual_trim_end_sec=9))
        self.assertEqual(error.exception.status_code, 400)

    def test_patch_persists_valid_trim_window(self):
        scene = {"id": 7, "project_id": 3, "visual_trim_start_sec": 0, "visual_trim_end_sec": 0, "visual_source_duration_sec": 10}
        updated = {**scene, "visual_trim_start_sec": 2, "visual_trim_end_sec": 6}
        with patch("app.main.db.query_one", side_effect=[scene, updated]), \
             patch("app.main.db.execute") as execute, \
             patch("app.main._touch_project") as touch:
            result = patch_scene(7, ScenePatch(visual_trim_start_sec=2, visual_trim_end_sec=6))
        self.assertEqual(result["visual_trim_start_sec"], 2)
        self.assertEqual(result["visual_trim_end_sec"], 6)
        self.assertIn("visual_trim_start_sec", execute.call_args.args[0])
        touch.assert_called_once_with(3)


if __name__ == "__main__":
    unittest.main()
