import asyncio
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.main import TimelineOverlayTextIn, create_timeline_text_overlay, upload_timeline_overlay


class TimelineOverlayUploadTests(unittest.TestCase):
    def test_uploads_video_as_independent_timeline_overlay(self):
        overlay = {
            "id": 71, "project_id": 3, "kind": "video", "title": "overlay",
            "start_sec": 2.0, "duration_sec": 6.0,
        }
        upload = UploadFile(
            filename="overlay.mp4",
            file=io.BytesIO(b"fake-video-source"),
            headers=Headers({"content-type": "video/mp4"}),
        )

        def fake_ffmpeg(command, timeout=900):
            Path(command[-1]).write_bytes(b"converted-overlay-video" * 100)
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with tempfile.TemporaryDirectory() as temp, \
             patch("app.main.db.MEDIA_DIR", Path(temp) / "media"), \
             patch("app.main.db.TMP_DIR", Path(temp) / "tmp"), \
             patch("app.main.db.query_one", side_effect=[{"id": 3}, overlay]), \
             patch("app.main.db.execute", side_effect=[71, 0]) as execute, \
             patch("app.main._touch_project") as touch, \
             patch("app.main.media.probe_video", return_value={"width": 1280, "height": 720, "duration": 6.0}), \
             patch("app.main.media.run", side_effect=fake_ffmpeg):
            result = asyncio.run(upload_timeline_overlay(3, upload, start_sec=2.0))
            saved = list((Path(temp) / "media" / "overlays" / "3").glob("overlay-*.mp4"))
            saved_size = saved[0].stat().st_size if saved else 0

        self.assertEqual(result["id"], 71)
        self.assertEqual(result["kind"], "video")
        self.assertEqual(len(saved), 1)
        self.assertGreater(saved_size, 1024)
        self.assertIn("timeline_overlays", execute.call_args_list[0].args[0])
        self.assertEqual(execute.call_args_list[0].args[1][4], 2.0)
        touch.assert_called_once_with(3)

    def test_uploads_audio_as_independent_timeline_clip(self):
        overlay = {
            "id": 72, "project_id": 3, "kind": "audio", "title": "audio",
            "start_sec": 1.5, "duration_sec": 4.0, "volume": 1.0,
        }
        upload = UploadFile(
            filename="audio.mp3",
            file=io.BytesIO(b"fake-audio-source"),
            headers=Headers({"content-type": "audio/mpeg"}),
        )
        with tempfile.TemporaryDirectory() as temp, \
             patch("app.main.db.MEDIA_DIR", Path(temp) / "media"), \
             patch("app.main.db.TMP_DIR", Path(temp) / "tmp"), \
             patch("app.main.db.query_one", side_effect=[{"id": 3}, overlay]), \
             patch("app.main.db.execute", side_effect=[72, 0]) as execute, \
             patch("app.main._touch_project") as touch, \
             patch("app.main.media.probe_audio", return_value={"codec": "mp3", "duration": 4.0}):
            result = asyncio.run(upload_timeline_overlay(3, upload, start_sec=1.5))
            saved = list((Path(temp) / "media" / "overlays" / "3").glob("overlay-*.mp3"))
            saved_size = saved[0].stat().st_size if saved else 0

        self.assertEqual(result["kind"], "audio")
        self.assertEqual(len(saved), 1)
        self.assertGreater(saved_size, 0)
        self.assertIn("timeline_overlays", execute.call_args_list[0].args[0])
        touch.assert_called_once_with(3)

    def test_creates_editable_text_overlay_as_transparent_png(self):
        overlay = {
            "id": 81, "project_id": 3, "kind": "text", "title": "Texto de prueba",
            "start_sec": 2.0, "duration_sec": 5.0,
        }
        with tempfile.TemporaryDirectory() as temp, \
             patch("app.main.db.MEDIA_DIR", Path(temp) / "media"), \
             patch("app.main.db.query_one", side_effect=[{"id": 3}, overlay]), \
             patch("app.main.db.execute", side_effect=[81, 0]) as execute, \
             patch("app.main._touch_project") as touch:
            result = create_timeline_text_overlay(
                3, TimelineOverlayTextIn(text="Texto de prueba", start_sec=2, duration_sec=5)
            )
            image_path = Path(execute.call_args_list[0].args[1][2])
            exists = image_path.is_file()
            image_size = image_path.stat().st_size if exists else 0

        self.assertEqual(result["kind"], "text")
        self.assertTrue(exists)
        self.assertGreater(image_size, 1000)
        self.assertIn("timeline_overlays", execute.call_args_list[0].args[0])
        touch.assert_called_once_with(3)

    def test_rejects_unsupported_overlay_file_types(self):
        upload = UploadFile(
            filename="script.txt",
            file=io.BytesIO(b"not media"),
            headers=Headers({"content-type": "text/plain"}),
        )
        with patch("app.main.db.query_one", return_value={"id": 3}):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(upload_timeline_overlay(3, upload))
        self.assertEqual(error.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
