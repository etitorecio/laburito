import json
import unittest
from unittest.mock import patch

from app.main import (
    EditorHistoryIn,
    TimelineOverlayPatch,
    ProjectPatch,
    ScenePatch,
    get_editor_history,
    record_editor_history,
    redo_editor_history,
    undo_editor_history,
)


class EditorHistoryTests(unittest.TestCase):
    def test_records_scene_change_and_discards_redo_branch(self):
        stored = {
            "id": 12, "target": "scene", "target_id": 7,
            "before_json": '{"narration":"old"}', "after_json": '{"narration":"new"}',
            "label": "Escena 1", "undone": 0,
        }
        with patch("app.main.db.query_one", side_effect=[{"id": 3}, {"id": 7}, stored]), \
             patch("app.main.db.execute", side_effect=[0, 12, 0]) as execute:
            result = record_editor_history(
                3, EditorHistoryIn(
                    target="scene", target_id=7,
                    before={"narration": "old"}, after={"narration": "new"}, label="Escena 1",
                )
            )
        self.assertEqual(result["id"], 12)
        self.assertIn("DELETE FROM editor_history WHERE project_id=? AND undone=1", execute.call_args_list[0].args[0])
        inserted = execute.call_args_list[1].args[1]
        self.assertEqual(json.loads(inserted[3]), {"narration": "old"})
        self.assertEqual(json.loads(inserted[4]), {"narration": "new"})

    def test_undo_applies_previous_scene_values_and_marks_entry_undone(self):
        entry = {
            "id": 15, "target": "scene", "target_id": 7,
            "before_json": '{"narration":"before"}', "after_json": '{"narration":"after"}',
            "label": "Escena", "undone": 0,
        }
        with patch("app.main.db.query_one", side_effect=[{"id": 3}, entry]), \
             patch("app.main.patch_scene", return_value={"id": 7}) as patch_scene, \
             patch("app.main.db.execute") as execute:
            result = undo_editor_history(3)
        self.assertTrue(result["ok"])
        self.assertIsInstance(patch_scene.call_args.args[1], ScenePatch)
        self.assertEqual(patch_scene.call_args.args[1].narration, "before")
        self.assertIn("undone=1", execute.call_args.args[0])

    def test_redo_applies_next_overlay_values(self):
        entry = {
            "id": 16, "target": "overlay", "target_id": 22,
            "before_json": '{"volume":0.2}', "after_json": '{"volume":0.8}',
            "label": "Música", "undone": 1,
        }
        with patch("app.main.db.query_one", side_effect=[{"id": 3}, entry]), \
             patch("app.main.patch_timeline_overlay", return_value={"id": 22}) as patch_overlay, \
             patch("app.main.db.execute") as execute:
            result = redo_editor_history(3)
        self.assertTrue(result["ok"])
        self.assertIsInstance(patch_overlay.call_args.args[1], TimelineOverlayPatch)
        self.assertEqual(patch_overlay.call_args.args[1].volume, 0.8)
        self.assertIn("undone=0", execute.call_args.args[0])

    def test_undo_applies_previous_project_settings(self):
        entry = {
            "id": 17, "target": "project", "target_id": 3,
            "before_json": '{"music_volume":0.2}', "after_json": '{"music_volume":0.8}',
            "label": "Proyecto", "undone": 0,
        }
        with patch("app.main.db.query_one", side_effect=[{"id": 3}, entry]), \
             patch("app.main.patch_project", return_value={"id": 3}) as patch_project_mock, \
             patch("app.main.db.execute"):
            result = undo_editor_history(3)
        self.assertTrue(result["ok"])
        self.assertIsInstance(patch_project_mock.call_args.args[1], ProjectPatch)
        self.assertEqual(patch_project_mock.call_args.args[1].music_volume, 0.2)

    def test_returns_history_cursor_and_available_directions(self):
        entries = [
            {"id": 1, "undone": 0},
            {"id": 2, "undone": 1},
        ]
        with patch("app.main.db.query_one", return_value={"id": 3}), \
             patch("app.main.db.query", return_value=entries):
            result = get_editor_history(3)
        self.assertEqual(result["cursor"], 1)
        self.assertTrue(result["can_undo"])
        self.assertTrue(result["can_redo"])


if __name__ == "__main__":
    unittest.main()
