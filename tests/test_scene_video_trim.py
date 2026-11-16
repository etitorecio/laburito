import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import db
from app.main import ScenePatch, patch_scene
from app.render import _apply_timeline_overlays, _trim_audio_source, _trim_visual_source, _visual_input_args


class SceneVideoTrimTests(unittest.TestCase):
    def test_database_migration_adds_source_trim_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.multiple(
                "app.db",
                DATA_DIR=root,
                DB_PATH=root / "test.sqlite3",
                MEDIA_DIR=root / "media",
                RENDER_DIR=root / "renders",
                EXPORT_DIR=root / "exports",
                MUSIC_DIR=root / "music",
                TMP_DIR=root / "tmp",
            ):
                db.init_db()
                columns = {row["name"] for row in db.query("PRAGMA table_info(scenes)")}
                version = db.scalar("SELECT value FROM meta WHERE key='schema_version'")
                overlays_table = db.query_one("SELECT name FROM sqlite_master WHERE type='table' AND name='timeline_overlays'")
                overlay_columns = {row["name"] for row in db.query("PRAGMA table_info(timeline_overlays)")}
                history_table = db.query_one("SELECT name FROM sqlite_master WHERE type='table' AND name='editor_history'")
        self.assertIn("visual_trim_start_sec", columns)
        self.assertIn("visual_trim_end_sec", columns)
        self.assertIn("visual_source_duration_sec", columns)
        self.assertEqual(version, "11")
        self.assertTrue(overlays_table)
        self.assertIn("volume", overlay_columns)
        self.assertTrue(history_table)
        self.assertTrue({"source_start_sec", "source_end_sec", "source_duration_sec"}.issubset(overlay_columns))

    def test_timeline_overlay_composition_adds_positioned_video_layer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "base.mp4"
            clip = root / "overlay.mp4"
            output = root / "out.mp4"
            base.write_bytes(b"base-video")
            clip.write_bytes(b"overlay-video")
            def fake_ff(args):
                output.write_bytes(b"rendered-overlay-video" * 100)
            with patch("app.render._ff", side_effect=fake_ff) as ff:
                result = _apply_timeline_overlays(
                    base,
                    [{"kind": "video", "path": str(clip), "start_sec": 2, "duration_sec": 3,
                      "x": 0.6, "y": 0.7, "width": 0.3, "opacity": 0.8}],
                    output, 1920, 1080, 12,
                )
            self.assertEqual(result, output)
            command = ff.call_args.args[0]
            filter_graph = command[command.index("-filter_complex") + 1]
            self.assertIn("overlay=", filter_graph)
            self.assertIn("between(t,2.000,5.000)", filter_graph)
            self.assertIn("(main_w-overlay_w)*0.6000", filter_graph)
            self.assertIn("colorchannelmixer=aa=0.800", filter_graph)

    def test_timeline_audio_layer_is_mixed_at_its_offset_and_volume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "base.mp4"
            audio = root / "voiceover.wav"
            output = root / "out.mp4"
            base.write_bytes(b"base-video")
            audio.write_bytes(b"audio-source")
            def fake_ff(args):
                output.write_bytes(b"rendered-audio-layer" * 100)
            with patch("app.render._ff", side_effect=fake_ff) as ff:
                result = _apply_timeline_overlays(
                    base,
                    [{"kind": "audio", "path": str(audio), "start_sec": 1.5, "duration_sec": 4,
                      "volume": 0.75}],
                    output, 1920, 1080, 12,
                )
            self.assertEqual(result, output)
            command = ff.call_args.args[0]
            graph = command[command.index("-filter_complex") + 1]
            self.assertIn("volume=0.750,adelay=1500|1500[a1]", graph)
            self.assertIn("amix=inputs=2:duration=first", graph)
            self.assertIn("[aout]", command)

    def test_trimmed_video_is_materialized_once_as_a_loopable_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            source.write_bytes(b"video-source")
            scene_dir = root / "scene"
            def fake_ff(args):
                Path(args[-1]).write_bytes(b"trimmed-video" * 300)
            with patch("app.render._ff", side_effect=fake_ff) as ff:
                trimmed = _trim_visual_source(source, scene_dir, 0.2, 1.8, 2.0)
                again = _trim_visual_source(source, scene_dir, 0.2, 1.8, 2.0)
                trimmed_size = trimmed.stat().st_size

        command = ff.call_args.args[0]
        self.assertEqual(trimmed, again)
        self.assertEqual(ff.call_count, 1)
        self.assertIn("-ss", command)
        self.assertEqual(command[command.index("-ss") + 1], "0.200")
        self.assertEqual(command[command.index("-t") + 1], "1.600")
        self.assertGreater(trimmed_size, 1000)

    def test_trimmed_audio_is_materialized_once_as_a_loopable_wav(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp3"
            source.write_bytes(b"audio-source")
            workdir = root / "overlay-trims"
            def fake_ff(args):
                Path(args[-1]).write_bytes(b"trimmed-audio" * 300)
            with patch("app.render._ff", side_effect=fake_ff) as ff:
                trimmed = _trim_audio_source(source, workdir, 1.0, 3.0, 5.0)
                again = _trim_audio_source(source, workdir, 1.0, 3.0, 5.0)
                trimmed_size = trimmed.stat().st_size

        command = ff.call_args.args[0]
        self.assertEqual(trimmed, again)
        self.assertEqual(ff.call_count, 1)
        self.assertEqual(command[command.index("-ss") + 1], "1.000")
        self.assertEqual(command[command.index("-t") + 1], "2.000")
        self.assertIn("pcm_s16le", command)
        self.assertGreater(trimmed_size, 1000)

    def test_video_input_uses_entire_source_when_trim_is_unset(self):
        args = _visual_input_args(Path("clip.mp4"), 30)
        self.assertEqual(args, ["-stream_loop", "-1", "-i", "clip.mp4"])

    def test_materialized_trimmed_video_loops_without_an_input_duration_cap(self):
        args = _visual_input_args(Path("trimmed.mp4"), 25)
        self.assertEqual(args, ["-stream_loop", "-1", "-i", "trimmed.mp4"])

    def test_still_images_use_a_static_loop_input(self):
        args = _visual_input_args(Path("still.png"), 25)
        self.assertEqual(args, ["-loop", "1", "-framerate", "25", "-i", "still.png"])

    def test_editing_narration_invalidates_stale_rendered_voice_duration(self):
        scene = {"id": 7, "project_id": 3, "narration": "Texto anterior", "audio_path": "old.wav", "audio_sec": 5}
        updated = {**scene, "narration": "Texto nuevo", "audio_path": "", "audio_sec": 0}
        with patch("app.main.db.query_one", side_effect=[scene, updated]), \
             patch("app.main.db.execute") as execute, \
             patch("app.main._touch_project"):
            result = patch_scene(7, ScenePatch(narration="Texto nuevo"))
        self.assertEqual(result["audio_sec"], 0)
        self.assertEqual(result["audio_path"], "")
        self.assertIn("audio_sec", execute.call_args.args[0])

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
