import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import publish


class PublishReliabilityTests(unittest.TestCase):
    def test_auto_publish_can_be_enabled_for_local_delivery(self):
        with patch.object(publish, "ensure_schema"), \
             patch.object(publish.db, "query_one", return_value={"id": 12, "channel_id": 3}), \
             patch.object(publish.db, "execute") as execute, \
             patch.object(publish.db, "now", return_value="now"), \
             patch.object(publish, "auto_publish_settings", return_value={"enabled": True, "destination": "entrega"}):
            result = publish.set_auto_publish(12, True, "entrega")
        self.assertTrue(result["enabled"])
        self.assertIn("auto_publish=?", execute.call_args.args[0])
        self.assertEqual(execute.call_args.args[1], (1, "entrega", "now", 12))

    def test_auto_publish_youtube_is_rejected_for_manual_approval(self):
        with patch.object(publish, "ensure_schema"), \
             patch.object(publish.db, "query_one", return_value={"id": 12, "channel_id": 3}), \
             patch.object(publish.db, "execute") as execute:
            with self.assertRaisesRegex(publish.PublishError, "aprobación manual"):
                publish.set_auto_publish(12, True, "youtube")
        execute.assert_not_called()

    def test_youtube_processing_failure_is_not_recorded_as_published(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "final_short.mp4"
            video.write_bytes(b"x" * 2048)
            statements = []
            project = {"id": 12, "kind": "short", "notes": "Autopiloto: test"}
            upload_result = {
                "url": "https://youtu.be/rejected123",
                "external_id": "rejected123",
                "message": "Subido, pero YouTube informó un fallo de procesamiento",
                "verification": {
                    "status": "processing_failed",
                    "upload_status": "failed",
                    "processing_status": "failed",
                },
            }
            with patch.object(publish, "ensure_schema"):
                with patch.object(publish.db, "query_one", side_effect=[project, None]):
                    with patch.object(publish, "video_path", return_value=video):
                        with patch.object(publish, "_validate_autopilot_short"):
                            with patch.object(publish, "_video_fingerprint", return_value="sha256-test"):
                                with patch.object(publish.db, "query", return_value=[]), patch.object(publish, "build_metadata", return_value={"title": "test"}):
                                    with patch.object(publish, "authorize_manual_approval") as authorize:
                                        with patch.object(publish, "_youtube_upload", return_value=upload_result):
                                            with patch.object(publish.db, "execute", side_effect=lambda sql, params=(): statements.append((sql, params))):
                                                with patch.object(publish.db, "now", return_value="now"):
                                                    with patch.object(publish.db, "log"):
                                                        result = publish.publish(
                                                            12, "youtube", privacy="public",
                                                            manual_approval_id="approval-12", job_id=77,
                                                        )
            authorize.assert_called_once_with(12, "approval-12", 77, "sha256-test")
            self.assertEqual(result["status"], "procesamiento_fallido")
            insert = next(params for sql, params in statements if "INSERT INTO publicaciones" in sql)
            self.assertEqual(insert[3], "procesamiento_fallido")

    def test_youtube_upload_cannot_start_without_manual_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "final_short.mp4"
            video.write_bytes(b"x" * 2048)
            project = {"id": 13, "kind": "short", "notes": ""}
            with patch.object(publish, "ensure_schema"):
                with patch.object(publish.db, "query_one", side_effect=[project, None]):
                    with patch.object(publish, "video_path", return_value=video):
                        with patch.object(publish, "_youtube_upload") as upload:
                            with self.assertRaisesRegex(publish.ManualApprovalRequired, "aprobación manual"):
                                publish.publish(13, "youtube", privacy="public")
            upload.assert_not_called()

    def test_manual_approval_is_bound_to_one_job_and_allows_its_retries(self):
        rows = [
            {"project_id": 14, "job_id": None, "video_sha256": "sha256-test"},
            {"project_id": 14, "job_id": 88, "video_sha256": "sha256-test"},
            {"project_id": 14, "job_id": 88, "video_sha256": "sha256-test"},
            {"project_id": 14, "job_id": 88, "video_sha256": "sha256-test"},
        ]
        with patch.object(publish, "ensure_schema"):
            with patch.object(publish.db, "query_one", side_effect=rows):
                with patch.object(publish.db, "execute") as execute:
                    publish.authorize_manual_approval(14, "opaque-token", 88, "sha256-test")
                    publish.authorize_manual_approval(14, "opaque-token", 88, "sha256-test")
                    with self.assertRaises(publish.ManualApprovalRequired):
                        publish.authorize_manual_approval(14, "opaque-token", 89, "sha256-test")
        self.assertGreaterEqual(execute.call_count, 2)

    def test_manual_approval_rejects_a_video_changed_after_review(self):
        row = {"project_id": 14, "job_id": None, "video_sha256": "original-sha256"}
        with patch.object(publish, "ensure_schema"):
            with patch.object(publish.db, "query_one", return_value=row):
                with self.assertRaisesRegex(publish.ManualApprovalRequired, "cambió después de tu aprobación"):
                    publish.authorize_manual_approval(14, "opaque-token", 88, "new-sha256")

    def test_enqueue_manual_youtube_creates_an_opaque_job_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "final_short.mp4"
            video.write_bytes(b"x" * 2048)
            with patch.object(publish.db, "query_one", return_value={"id": 15, "kind": "short"}):
                with patch.object(publish, "video_path", return_value=video):
                    with patch.object(publish, "_video_fingerprint", return_value="sha256-test"):
                        with patch.object(publish, "issue_manual_approval", return_value="opaque-token") as issue:
                            with patch("app.worker.enqueue", return_value=91) as enqueue:
                                job_id = publish.enqueue_manual_publication(15, "youtube", None, "private")
        self.assertEqual(job_id, 91)
        issue.assert_called_once_with(15, "sha256-test")
        enqueue.assert_called_once_with(15, "publish_project", {
            "destination": "youtube", "calendar_id": None, "privacy": "private",
            "manual_approval_id": "opaque-token",
        })

    def test_failed_processing_fingerprint_is_not_uploaded_twice(self):
        project = {"id": 12, "kind": "short", "notes": "Autopiloto: test"}
        previous = {
            "status": "procesamiento_fallido",
            "url": "https://youtu.be/rejected123",
            "external_id": "rejected123",
            "meta_json": json.dumps({"video_sha256": "sha256-test"}),
        }
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "final_short.mp4"
            video.write_bytes(b"x" * 2048)
            with patch.object(publish, "ensure_schema"):
                with patch.object(publish.db, "query_one", side_effect=[project, previous]):
                    with patch.object(publish, "video_path", return_value=video):
                        with patch.object(publish, "_validate_autopilot_short"):
                            with patch.object(publish, "_video_fingerprint", return_value="sha256-test"):
                                with patch.object(publish, "_youtube_upload") as upload:
                                    result = publish.publish(12, "youtube", privacy="public")
            upload.assert_not_called()
            self.assertEqual(result["status"], "procesamiento_fallido")
            self.assertEqual(result["external_id"], "rejected123")


if __name__ == "__main__":
    unittest.main()
