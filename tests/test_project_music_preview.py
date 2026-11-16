import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.main import project_music_preview


class ProjectMusicPreviewTests(unittest.TestCase):
    def test_returns_selected_local_music_for_editor_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            music = Path(temp) / "bed.wav"
            music.write_bytes(b"audio" * 100)
            with patch("app.main.db.query_one", return_value={"id": 5, "music": "auto"}), \
                 patch("app.main.render._music_track", return_value=music):
                response = project_music_preview(5)
        self.assertIsInstance(response, FileResponse)
        self.assertEqual(response.path, str(music))
        self.assertEqual(response.media_type, "audio/wav")

    def test_returns_not_found_when_project_has_no_music(self):
        with patch("app.main.db.query_one", return_value={"id": 5, "music": "none"}), \
             patch("app.main.render._music_track", return_value=None):
            with self.assertRaises(HTTPException) as error:
                project_music_preview(5)
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
