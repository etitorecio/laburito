import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.main import scene_voice_preview


class SceneVoicePreviewTests(unittest.TestCase):
    def test_creates_cached_scene_audio_with_project_voice(self):
        scene = {"id": 4, "project_id": 2, "narration": "Una narración breve para probar la voz."}
        project = {"voice": "es", "speed": 155, "pitch": 48}
        with tempfile.TemporaryDirectory() as temp, \
             patch("app.main.db.DATA_DIR", Path(temp)), \
             patch("app.main.db.query_one", side_effect=[scene, project]), \
             patch("app.main.tts.synthesize", side_effect=lambda text, path, **kwargs: Path(path).write_bytes(b"RIFF" + b"x" * 1200)) as synth:
            response = scene_voice_preview(4)
            self.assertIsInstance(response, FileResponse)
            self.assertTrue(Path(response.path).is_file())
            self.assertEqual(synth.call_args.kwargs["voice"], "es")
            self.assertEqual(synth.call_args.kwargs["speed"], 155)

    @patch("app.main.db.query_one", return_value={"id": 4, "project_id": 2, "narration": "  "})
    def test_requires_scene_narration(self, query_one):
        with self.assertRaises(HTTPException) as error:
            scene_voice_preview(4)
        self.assertEqual(error.exception.status_code, 400)
        query_one.assert_called_once()


if __name__ == "__main__":
    unittest.main()
