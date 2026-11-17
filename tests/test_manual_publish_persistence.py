import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import main, publish


class ManualPublishPersistenceTests(unittest.TestCase):
    def test_manual_publish_backs_up_video_before_enqueue_when_remote_storage_is_configured(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "short.mp4"
            video.write_bytes(b"mp4" * 1024)
            with patch.object(main.publish, "ensure_schema"):
                with patch.object(main.db, "query_one", return_value={"id": 1, "title": "Short"}):
                    with patch.object(main.publish, "video_path", return_value=video):
                        with patch.object(main.persistence, "configured", return_value=True):
                            with patch.object(main.persistence, "sync_pending_video") as sync_video:
                                with patch.object(main.worker, "enqueue", return_value=55) as enqueue:
                                    response = main.publish_project(1, publish.PublishIn(destination="entrega"))
        sync_video.assert_called_once_with(1, video)
        enqueue.assert_called_once()
        self.assertEqual(response["job_id"], 55)

    def test_manual_youtube_publish_issues_per_video_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "short.mp4"
            video.write_bytes(b"mp4" * 1024)
            with patch.object(main.publish, "ensure_schema"):
                with patch.object(main.db, "query_one", return_value={"id": 1, "channel_id": 3, "title": "Short"}):
                    with patch.object(main.publish, "video_path", return_value=video):
                        with patch.object(main.publish, "youtube_account_status"):
                            with patch.object(main.publish, "enqueue_manual_publication", return_value=56) as enqueue:
                                response = main.publish_project(1, publish.PublishIn(destination="youtube"))
        enqueue.assert_called_once_with(1, "youtube", None, "unlisted")
        self.assertEqual(response["job_id"], 56)

    def test_manual_publish_stops_if_remote_video_backup_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "short.mp4"
            video.write_bytes(b"mp4" * 1024)
            with patch.object(main.publish, "ensure_schema"):
                with patch.object(main.db, "query_one", return_value={"id": 1, "title": "Short"}):
                    with patch.object(main.publish, "video_path", return_value=video):
                        with patch.object(main.persistence, "configured", return_value=True):
                            with patch.object(main.persistence, "sync_pending_video", side_effect=RuntimeError("storage unavailable")):
                                with patch.object(main.worker, "enqueue") as enqueue:
                                    with self.assertRaises(HTTPException) as raised:
                                        main.publish_project(1, publish.PublishIn(destination="entrega"))
        self.assertEqual(raised.exception.status_code, 503)
        enqueue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
