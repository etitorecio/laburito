import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.main import regenerate_scene_visual


class SceneVisualRegenerationTests(unittest.TestCase):
    def test_regenerates_visual_from_a_different_open_license_source(self):
        scene = {
            "id": 12, "project_id": 4, "title": "Historia del pedal",
            "visual_query": "vintage guitar pedal", "visual_url": "https://commons.test/current-page",
        }
        updated = {**scene, "visual_url": "https://commons.test/new-page", "visual_path": "/tmp/new.jpg"}
        results = [
            {"provider": "Wikimedia Commons", "url": "https://commons.test/current.jpg",
             "page": "https://commons.test/current-page", "license": "CC BY-SA", "author": "A"},
            {"provider": "Openverse", "url": "https://openverse.test/new.jpg",
             "page": "https://commons.test/new-page", "license": "CC BY 4.0", "author": "B", "title": "New pedal"},
        ]
        with patch("app.main.db.query_one", side_effect=[scene, updated]), \
             patch("app.main.media.search_media", return_value={"results": results, "errors": {}}), \
             patch("app.main.media.download_asset", return_value={
                 "path": "/tmp/new.jpg", "bytes": 2048, "content_type": "image/jpeg",
             }) as download, \
             patch("app.main.db.execute", side_effect=[1, 2, 3]) as execute, \
             patch("app.main._touch_project") as touch:
            result = regenerate_scene_visual(12, variant=0)

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"]["title"], "New pedal")
        self.assertEqual(download.call_args.args[0], "https://openverse.test/new.jpg")
        self.assertIn("visual_trim_start_sec=0", execute.call_args_list[0].args[0])
        touch.assert_called_once_with(4)

    def test_reports_unavailable_when_no_open_image_source_is_found(self):
        scene = {"id": 12, "project_id": 4, "title": "Historia", "visual_query": "unknown"}
        with patch("app.main.db.query_one", return_value=scene), \
             patch("app.main.media.search_media", return_value={"results": [], "errors": {"openverse": "offline"}}):
            with self.assertRaises(HTTPException) as error:
                regenerate_scene_visual(12)
        self.assertEqual(error.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
