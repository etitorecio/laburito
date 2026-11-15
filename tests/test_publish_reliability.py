import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import publish


class PublishReliabilityTests(unittest.TestCase):
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
                                    with patch.object(publish, "_youtube_upload", return_value=upload_result):
                                        with patch.object(publish.db, "execute", side_effect=lambda sql, params=(): statements.append((sql, params))):
                                            with patch.object(publish.db, "now", return_value="now"):
                                                with patch.object(publish.db, "log"):
                                                    result = publish.publish(12, "youtube", privacy="public")
            self.assertEqual(result["status"], "procesamiento_fallido")
            insert = next(params for sql, params in statements if "INSERT INTO publicaciones" in sql)
            self.assertEqual(insert[3], "procesamiento_fallido")

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
