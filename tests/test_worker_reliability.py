import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import publish, worker


class WorkerReliabilityTests(unittest.TestCase):
    def test_auto_publish_blocks_missing_voice_engine(self):
        message = worker._auto_publish_blocker({"quality": {"tts_engines": []}})
        self.assertIn("sin narración", message)

    def test_auto_publish_blocks_silence_fallback(self):
        message = worker._auto_publish_blocker({"quality": {"tts_engines": ["silencio"]}})
        self.assertIn("sin narración", message)

    def test_render_result_requires_real_nonempty_mp4_and_probe_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "final_short.mp4"
            video.write_bytes(b"x" * 2048)
            with patch.object(worker.render.media, "probe_video", return_value={
                "width": 1080, "height": 1920, "duration": 42.5
            }):
                checked = worker._validate_render_result({"video": str(video)})
        self.assertEqual(checked["width"], 1080)
        self.assertEqual(checked["height"], 1920)
        self.assertEqual(checked["duration"], 42.5)

    def test_render_result_rejects_missing_video(self):
        with self.assertRaisesRegex(RuntimeError, "no devolvió la ruta"):
            worker._validate_render_result({})

    def test_scheduled_settings_preserve_youtube_destination_after_project_lookup_error(self):
        with patch.object(worker.db, "query_one", return_value={
            "auto_publish": 1, "destination": "youtube", "privacy": "public"
        }):
            settings = worker._scheduled_publish_settings(12)
        self.assertEqual(settings, {
            "enabled": True, "destination": "youtube", "privacy": "public"
        })

    def test_render_keeps_manual_approval_when_autopublish_is_disabled(self):
        job = {
            "id": 95, "project_id": 12, "kind": "render_project",
            "payload_json": '{"privacy":"public"}', "attempts": 1,
        }
        statements = []
        with patch.object(worker.render, "render_project", return_value={
            "video": "/tmp/final_short.mp4",
            "quality": {"tts_engines": ["espeak-ng"]},
        }):
            with patch.object(worker, "_validate_render_result", return_value={"path": "/tmp/final_short.mp4"}):
                with patch.object(worker, "_scheduled_publish_settings", return_value={"enabled": False, "destination": "youtube", "privacy": "public"}):
                    with patch.object(worker, "enqueue") as enqueue:
                        with patch.object(worker.db, "execute", side_effect=lambda sql, params=(): statements.append((sql, params))):
                            with patch.object(worker.db, "now", return_value="now"):
                                with patch.object(worker.db, "log"):
                                    worker.run_job(job)
        enqueue.assert_not_called()
        self.assertTrue(any(
            "usá Publicar" in params[0]
            for sql, params in statements
            if "UPDATE jobs SET message" in sql
        ))
        self.assertTrue(any(
            "UPDATE jobs SET status='completado'" in sql
            for sql, _ in statements
        ))

    def test_render_queues_autopublish_after_validated_render(self):
        job = {
            "id": 96, "project_id": 13, "kind": "render_project",
            "payload_json": '{"privacy":"unlisted"}', "attempts": 1,
        }
        with patch.object(worker.render, "render_project", return_value={
            "video": "/tmp/final_short.mp4",
            "quality": {"tts_engines": ["espeak-ng"]},
        }):
            with patch.object(worker, "_validate_render_result", return_value={"path": "/tmp/final_short.mp4"}):
                with patch.object(worker, "_scheduled_publish_settings", return_value={"enabled": True, "destination": "youtube", "privacy": "unlisted"}):
                    with patch.object(worker.persistence, "configured", return_value=True):
                        with patch.object(worker.persistence, "sync_pending_video") as sync_video:
                            with patch.object(worker, "enqueue", return_value=321) as enqueue:
                                with patch.object(worker.db, "execute"):
                                    with patch.object(worker.db, "now", return_value="now"):
                                        with patch.object(worker.db, "log"):
                                            worker.run_job(job)
        sync_video.assert_called_once_with(13, "/tmp/final_short.mp4")
        enqueue.assert_called_once_with(13, "publish_project", {
            "destination": "youtube", "calendar_id": None, "privacy": "unlisted"
        })

    def test_failed_youtube_publish_is_never_marked_completed(self):
        job = {
            "id": 91, "project_id": 12, "kind": "publish_project",
            "payload_json": '{"destination":"youtube","privacy":"public"}',
            "attempts": 3,
        }
        statements = []
        with patch.object(publish, "publish", side_effect=publish.PublishError("OAuth rechazado")):
            with patch.object(worker.db, "execute", side_effect=lambda sql, params=(): statements.append((sql, params))):
                with patch.object(worker.db, "now", return_value="2026-11-15T00:00:00Z"):
                    with patch.object(worker.db, "log"):
                        worker.run_job(job)
        job_updates = [sql for sql, _ in statements if "UPDATE jobs SET status='error'" in sql]
        self.assertEqual(len(job_updates), 1)
        self.assertFalse(any("status='completado'" in sql for sql, _ in statements))

    def test_enqueue_deduplicates_same_pending_publication_payload(self):
        with patch.object(worker.db, "query", return_value=[
            {"id": 501, "payload_json": '{"destination":"youtube","privacy":"public"}'}
        ]):
            with patch.object(worker.db, "execute") as execute:
                job_id = worker.enqueue(12, "publish_project", {
                    "destination": "youtube", "privacy": "public"
                })
        self.assertEqual(job_id, 501)
        execute.assert_not_called()

    def test_enqueue_allows_a_different_publication_destination(self):
        with patch.object(worker.db, "query", return_value=[
            {"id": 502, "payload_json": '{"destination":"entrega"}'}
        ]):
            with patch.object(worker.db, "execute", return_value=503):
                with patch.object(worker.db, "now", return_value="now"):
                    job_id = worker.enqueue(12, "publish_project", {"destination": "youtube"})
        self.assertEqual(job_id, 503)

    def test_youtube_processing_rejection_marks_job_failed_without_retry(self):
        job = {
            "id": 94, "project_id": 12, "kind": "publish_project",
            "payload_json": '{"destination":"youtube","privacy":"public"}',
            "attempts": 1,
        }
        statements = []
        with patch.object(publish, "publish", return_value={
            "destination": "youtube",
            "status": "procesamiento_fallido",
            "url": "https://youtu.be/rejected123",
            "external_id": "rejected123",
            "message": "YouTube rechazó el procesamiento",
        }):
            with patch.object(worker.persistence, "restore_pending_video"):
                with patch.object(worker.db, "execute", side_effect=lambda sql, params=(): statements.append((sql, params))):
                    with patch.object(worker.db, "now", return_value="now"):
                        with patch.object(worker.db, "log"):
                            worker.run_job(job)
        update = next((params for sql, params in statements if "UPDATE jobs SET status=?" in sql), None)
        self.assertIsNotNone(update)
        self.assertEqual(update[0], "error")
        self.assertIn("YouTube rechazó", update[1])

    def test_transient_youtube_publish_error_is_requeued(self):
        job = {
            "id": 92, "project_id": 12, "kind": "publish_project",
            "payload_json": '{"destination":"youtube"}',
            "attempts": 1,
        }
        statements = []
        with patch.object(publish, "publish", side_effect=publish.PublishError("timeout")):
            with patch.object(worker.db, "execute", side_effect=lambda sql, params=(): statements.append((sql, params))):
                with patch.object(worker.db, "now", return_value="2026-11-15T00:00:00Z"):
                    with patch.object(worker.db, "log"):
                        with patch.object(worker.time, "sleep"):
                            worker.run_job(job)
        self.assertTrue(any("status='en_cola'" in sql for sql, _ in statements))
        self.assertFalse(any("status='completado'" in sql for sql, _ in statements))


if __name__ == "__main__":
    unittest.main()
