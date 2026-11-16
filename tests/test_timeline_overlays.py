import asyncio
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.main import TimelineOverlayMusicIn, TimelineOverlayPatch, TimelineOverlaySfxIn, TimelineOverlayTextIn, TimelineOverlayVoiceIn, create_timeline_music_overlay, create_timeline_sfx_overlay, create_timeline_text_overlay, create_timeline_voice_overlay, patch_timeline_overlay, upload_timeline_overlay


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

    def test_generates_local_sound_effect_as_an_independent_audio_layer(self):
        overlay = {
            "id": 89, "project_id": 3, "kind": "audio", "title": "Campanilla",
            "start_sec": 2.0, "duration_sec": 1.5, "volume": 0.7,
        }
        def fake_ffmpeg(command, timeout=60):
            Path(command[-1]).write_bytes(b"generated-sfx" * 200)
            return subprocess.CompletedProcess(command, 0, b"", b"")
        with tempfile.TemporaryDirectory() as temp, \
             patch("app.main.db.MEDIA_DIR", Path(temp) / "media"), \
             patch("app.main.db.query_one", side_effect=[{"id": 3}, overlay]), \
             patch("app.main.db.execute", side_effect=[89, 0]) as execute, \
             patch("app.main._touch_project") as touch, \
             patch("app.main.media.run", side_effect=fake_ffmpeg) as run, \
             patch("app.main.media.probe_audio", return_value={"codec": "pcm_s16le", "duration": 1.5}):
            result = create_timeline_sfx_overlay(3, TimelineOverlaySfxIn(effect="chime", start_sec=2, volume=0.7))

        self.assertEqual(result["title"], "Campanilla")
        self.assertEqual(result["kind"], "audio")
        self.assertIn("sine=frequency=880:duration=1.5", run.call_args.args[0])
        self.assertEqual(execute.call_args_list[0].args[1][10], 0.7)
        touch.assert_called_once_with(3)

    def test_generates_local_music_bed_as_an_independent_audio_layer(self):
        with tempfile.TemporaryDirectory() as temp:
            music_path = Path(temp) / "ambient.wav"
            music_path.write_bytes(b"local-music-bed" * 100)
            overlay = {
                "id": 90, "project_id": 3, "kind": "audio", "title": "Ambiente oscuro",
                "start_sec": 4.0, "duration_sec": 20.0, "volume": 0.35,
            }
            with patch("app.main.db.query_one", side_effect=[{"id": 3}, overlay]), \
                 patch("app.main.media.ensure_music_bed", return_value=music_path), \
                 patch("app.main.media.probe_audio", return_value={"codec": "pcm_s16le", "duration": 45}), \
                 patch("app.main.db.execute", side_effect=[90, 0]) as execute, \
                 patch("app.main._touch_project") as touch:
                result = create_timeline_music_overlay(
                    3, TimelineOverlayMusicIn(bed_id="ambiente", start_sec=4, duration_sec=20, volume=0.35)
                )

        self.assertEqual(result["kind"], "audio")
        self.assertEqual(result["title"], "Ambiente oscuro")
        self.assertIn("timeline_overlays", execute.call_args_list[0].args[0])
        self.assertEqual(execute.call_args_list[0].args[1][10], 0.35)
        touch.assert_called_once_with(3)

    def test_generates_local_voiceover_as_an_independent_audio_layer(self):
        overlay = {
            "id": 91, "project_id": 3, "kind": "audio", "title": "Voz de prueba",
            "start_sec": 2.0, "duration_sec": 3.5, "volume": 0.8,
        }
        def fake_synthesize(text, target, **kwargs):
            Path(target).write_bytes(b"generated-voice-audio")
            return {"engine": "espeak-ng"}
        with tempfile.TemporaryDirectory() as temp, \
             patch("app.main.db.MEDIA_DIR", Path(temp) / "media"), \
             patch("app.main.db.query_one", side_effect=[{"id": 3, "voice": "es-ar", "speed": 150, "pitch": 45}, overlay]), \
             patch("app.main.db.execute", side_effect=[91, 0]) as execute, \
             patch("app.main._touch_project") as touch, \
             patch("app.main.tts.synthesize", side_effect=fake_synthesize) as synthesize, \
             patch("app.main.media.probe_audio", return_value={"codec": "pcm_s16le", "duration": 3.5}):
            result = create_timeline_voice_overlay(
                3, TimelineOverlayVoiceIn(text="Esta es una voz en off", start_sec=2, volume=0.8)
            )
            target = Path(execute.call_args_list[0].args[1][2])
            saved_size = target.stat().st_size if target.is_file() else 0

        self.assertEqual(result["kind"], "audio")
        self.assertEqual(result["duration_sec"], 3.5)
        self.assertGreater(saved_size, 0)
        synthesize.assert_called_once()
        self.assertEqual(synthesize.call_args.kwargs["voice"], "es-ar")
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

    def test_rejects_source_trim_end_before_start(self):
        overlay = {
            "id": 82, "project_id": 3, "kind": "video", "path": "/tmp/clip.mp4",
            "title": "Clip", "start_sec": 0, "duration_sec": 5,
            "source_start_sec": 0, "source_end_sec": 0, "source_duration_sec": 10,
            "x": 0.5, "y": 0.5, "width": 0.5, "opacity": 1, "volume": 1,
        }
        with patch("app.main.db.query_one", return_value=overlay), \
             patch("app.main.db.execute") as execute:
            with self.assertRaises(HTTPException) as error:
                patch_timeline_overlay(82, TimelineOverlayPatch(source_start_sec=4, source_end_sec=3))
        self.assertEqual(error.exception.status_code, 400)
        execute.assert_not_called()

    def test_editing_text_overlay_regenerates_its_image_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "text.png"
            image_path.write_bytes(b"old")
            overlay = {
                "id": 82, "project_id": 3, "kind": "text", "path": str(image_path),
                "title": "Texto viejo", "start_sec": 0, "duration_sec": 4,
                "x": 0.5, "y": 0.75, "width": 0.82, "opacity": 1, "volume": 1,
            }
            updated = {**overlay, "title": "Texto nuevo"}
            with patch("app.main.db.query_one", side_effect=[overlay, updated]), \
                 patch("app.main.db.execute") as execute, \
                 patch("app.main._touch_project") as touch:
                result = patch_timeline_overlay(82, TimelineOverlayPatch(title="Texto nuevo"))
            image_size = image_path.stat().st_size

        self.assertEqual(result["title"], "Texto nuevo")
        self.assertGreater(image_size, 1000)
        self.assertIn("title=?", execute.call_args.args[0])
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
