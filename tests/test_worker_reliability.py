import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main, publish, worker


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

    def test_scheduled_settings_always_require_manual_youtube_approval(self):
        for row in (
            {"auto_publish": 1, "destination": "youtube", "privacy": "public"},
            {"auto_publish": 1, "destination": None, "privacy": "public"},
            {"auto_publish": 1, "privacy": "public"},
        ):
            with self.subTest(row=row):
                with patch.object(worker.db, "query_one", return_value=row):
                    settings = worker._scheduled_publish_settings(12)
                self.assertEqual(settings, {
                    "enabled": False, "destination": "youtube", "privacy": "unlisted"
                })

    def test_scheduled_settings_still_allow_automatic_local_delivery(self):
        with patch.object(worker.db, "query_one", return_value={
            "auto_publish": 1, "destination": "entrega", "privacy": "private"
        }):
            settings = worker._scheduled_publish_settings(12)
        self.assertEqual(settings, {
            "enabled": True, "destination": "entrega", "privacy": "private"
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

    def test_manual_review_render_is_backed_up_for_later_publishing(self):
        job = {
            "id": 98, "project_id": 15, "kind": "render_project",
            "payload_json": "{}", "attempts": 1,
        }
        with patch.object(worker.render, "render_project", return_value={
            "video": "/tmp/final_short.mp4",
            "quality": {"tts_engines": ["espeak-ng"]},
        }):
            with patch.object(worker, "_validate_render_result", return_value={"path": "/tmp/final_short.mp4"}):
                with patch.object(worker, "_scheduled_publish_settings", return_value={"enabled": False, "destination": "youtube", "privacy": "unlisted"}):
                    with patch.object(worker.persistence, "configured", return_value=True):
                        with patch.object(worker.persistence, "sync_pending_video") as sync_video:
                            with patch.object(worker, "enqueue") as enqueue:
                                with patch.object(worker.db, "execute"):
                                    with patch.object(worker.db, "now", return_value="now"):
                                        with patch.object(worker.db, "log"):
                                            worker.run_job(job)
        sync_video.assert_called_once_with(15, "/tmp/final_short.mp4")
        enqueue.assert_not_called()

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
                with patch.object(worker, "_scheduled_publish_settings", return_value={"enabled": True, "destination": "entrega", "privacy": "unlisted"}):
                    with patch.object(worker.persistence, "configured", return_value=True):
                        with patch.object(worker.persistence, "sync_pending_video") as sync_video:
                            with patch.object(worker, "enqueue", return_value=321) as enqueue:
                                with patch.object(worker.db, "execute"):
                                    with patch.object(worker.db, "now", return_value="now"):
                                        with patch.object(worker.db, "log"):
                                            worker.run_job(job)
        sync_video.assert_called_once_with(13, "/tmp/final_short.mp4")
        enqueue.assert_called_once_with(13, "publish_project", {
            "destination": "entrega", "calendar_id": None, "privacy": "unlisted"
        })

    def test_render_does_not_queue_autopublish_if_remote_mp4_backup_fails(self):
        job = {
            "id": 97, "project_id": 14, "kind": "render_project",
            "payload_json": "{}", "attempts": 1,
        }
        statements = []
        with patch.object(worker.render, "render_project", return_value={
            "video": "/tmp/final_short.mp4",
            "quality": {"tts_engines": ["espeak-ng"]},
        }):
            with patch.object(worker, "_validate_render_result", return_value={"path": "/tmp/final_short.mp4"}):
                with patch.object(worker, "_scheduled_publish_settings", return_value={"enabled": True, "destination": "entrega", "privacy": "unlisted"}):
                    with patch.object(worker.persistence, "configured", return_value=True):
                        with patch.object(worker.persistence, "sync_pending_video", side_effect=RuntimeError("storage unavailable")):
                            with patch.object(worker, "enqueue") as enqueue:
                                with patch.object(worker.db, "execute", side_effect=lambda sql, params=(): statements.append((sql, params))):
                                    with patch.object(worker.db, "now", return_value="now"):
                                        with patch.object(worker.db, "log"):
                                            worker.run_job(job)
        enqueue.assert_not_called()
        self.assertTrue(any(
            "no se pudo respaldar el MP4" in params[0]
            for sql, params in statements
            if "UPDATE jobs SET message" in sql
        ))

    def test_natural_creation_generates_script_then_renders_in_the_same_persistent_job(self):
        job = {
            "id": 110, "project_id": 42, "kind": "create_from_prompt",
            "payload_json": "{}", "attempts": 1,
        }
        statements = []

        def render_job(project_id, should_cancel, on_progress):
            self.assertEqual(project_id, 42)
            on_progress(50, "Renderizando escenas")
            return {"video": "/tmp/final_short.mp4", "quality": {"tts_engines": ["espeak-ng"]}}

        with patch.object(main, "generate_script", return_value={"warnings": ["investigación parcial"]}) as script:
            with patch.object(worker.render, "render_project", side_effect=render_job):
                with patch.object(worker, "_validate_render_result", return_value={"path": "/tmp/final_short.mp4"}):
                    with patch.object(worker, "_scheduled_publish_settings", return_value={
                        "enabled": False, "destination": "youtube", "privacy": "unlisted"
                    }):
                        with patch.object(worker, "_is_cancelled", return_value=False):
                            with patch.object(worker.persistence, "configured", return_value=False):
                                with patch.object(worker.db, "execute", side_effect=lambda sql, params=(): statements.append((sql, params))):
                                    with patch.object(worker.db, "now", return_value="now"):
                                        with patch.object(worker.db, "log"):
                                            worker.run_job(job)

        script.assert_called_once_with(42, replace=True)
        payload_update = next(params for sql, params in statements if "UPDATE jobs SET payload_json=?" in sql)
        self.assertIn('"script_ready": true', payload_update[0])
        self.assertTrue(any("status='completado'" in sql for sql, _ in statements))
        self.assertTrue(any(params[0] >= 60 for sql, params in statements if "UPDATE jobs SET progress=?" in sql))

    def test_natural_creation_retry_does_not_regenerate_a_saved_script(self):
        job = {
            "id": 111, "project_id": 43, "kind": "create_from_prompt",
            "payload_json": '{"script_ready":true,"script_warnings":[]}', "attempts": 2,
        }
        with patch.object(main, "generate_script") as script:
            with patch.object(worker.render, "render_project", return_value={
                "video": "/tmp/final_short.mp4", "quality": {"tts_engines": ["espeak-ng"]}
            }):
                with patch.object(worker, "_validate_render_result", return_value={"path": "/tmp/final_short.mp4"}):
                    with patch.object(worker, "_scheduled_publish_settings", return_value={
                        "enabled": False, "destination": "youtube", "privacy": "unlisted"
                    }):
                        with patch.object(worker, "_is_cancelled", return_value=False):
                            with patch.object(worker.persistence, "configured", return_value=False):
                                with patch.object(worker.db, "execute"):
                                    with patch.object(worker.db, "now", return_value="now"):
                                        with patch.object(worker.db, "log"):
                                            worker.run_job(job)
        script.assert_not_called()

    def test_legacy_youtube_job_without_manual_approval_fails_without_retry(self):
        job = {
            "id": 112, "project_id": 44, "kind": "publish_project",
            "payload_json": '{"destination":"youtube","privacy":"public"}', "attempts": 1,
        }
        statements = []
        with patch.object(publish, "publish", side_effect=publish.ManualApprovalRequired("Aprobación manual requerida")) as upload:
            with patch.object(worker.persistence, "restore_pending_video"):
                with patch.object(worker.db, "execute", side_effect=lambda sql, params=(): statements.append((sql, params))):
                    with patch.object(worker.db, "now", return_value="now"):
                        with patch.object(worker.db, "log"):
                            worker.run_job(job)
        upload.assert_called_once()
        self.assertIsNone(upload.call_args.kwargs["manual_approval_id"])
        self.assertEqual(upload.call_args.kwargs["job_id"], 112)
        self.assertTrue(any("UPDATE jobs SET status='error'" in sql for sql, _ in statements))
        self.assertFalse(any("status='en_cola'" in sql for sql, _ in statements))

    def test_worker_passes_the_manual_approval_to_the_exact_youtube_job(self):
        job = {
            "id": 113, "project_id": 45, "kind": "publish_project",
            "payload_json": '{"destination":"youtube","privacy":"private","manual_approval_id":"opaque-token"}',
            "attempts": 1,
        }
        with patch.object(publish, "publish", return_value={
            "destination": "youtube", "status": "publicado", "url": "https://youtu.be/test",
            "external_id": "test", "message": "Publicado", "verification": {"status": "uploaded"},
        }) as upload:
            with patch.object(worker.persistence, "restore_pending_video"):
                with patch.object(worker.db, "execute"):
                    with patch.object(worker.db, "now", return_value="now"):
                        with patch.object(worker.db, "log"):
                            worker.run_job(job)
        self.assertEqual(upload.call_args.kwargs["manual_approval_id"], "opaque-token")
        self.assertEqual(upload.call_args.kwargs["job_id"], 113)

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
