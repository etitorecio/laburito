import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import publish, worker


class WorkerReliabilityTests(unittest.TestCase):
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
