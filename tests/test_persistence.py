import gzip
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import persistence


class PersistenceTests(unittest.TestCase):
    def test_status_reports_missing_external_storage(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(persistence.status()["configured"])

    def test_restore_validates_and_restores_private_bucket_backup(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return compressed

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.sqlite3"
            target = Path(folder) / "restored.sqlite3"
            with sqlite3.connect(source) as connection:
                connection.execute("CREATE TABLE restore_test(value TEXT)")
                connection.execute("INSERT INTO restore_test VALUES('kept')")
            compressed = gzip.compress(source.read_bytes())
            with patch.object(persistence, "configured", return_value=True):
                with patch.object(persistence, "_ensure_bucket"):
                    with patch.object(persistence, "_request", return_value=FakeResponse()):
                        with patch.object(persistence.db, "ensure_dirs"):
                            with patch.object(persistence.db, "DB_PATH", target):
                                restored = persistence.restore_if_available()
            self.assertTrue(restored)
            with sqlite3.connect(target) as connection:
                value = connection.execute("SELECT value FROM restore_test").fetchone()[0]
            self.assertEqual(value, "kept")

    def test_sync_uploads_compressed_backup_to_private_object_with_upsert(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return b""

        with tempfile.TemporaryDirectory() as folder:
            backup = Path(folder) / "backup.sqlite3"
            with sqlite3.connect(backup) as connection:
                connection.execute("CREATE TABLE backup_test(value TEXT)")
                connection.execute("INSERT INTO backup_test VALUES('saved')")
            with patch.object(persistence, "configured", return_value=True):
                with patch.object(persistence, "_ensure_bucket"):
                    with patch.object(persistence.db, "backup", return_value=str(backup)):
                        with patch.object(persistence, "_request", return_value=FakeResponse()) as request:
                            with patch.object(persistence.db, "log"):
                                self.assertTrue(persistence.sync_backup())
            args, kwargs = request.call_args
            self.assertEqual(args[0], "POST")
            self.assertEqual(args[3], "application/gzip")
            self.assertEqual(kwargs["extra_headers"], {"x-upsert": "true"})
            self.assertEqual(gzip.decompress(args[2]), backup.read_bytes())


if __name__ == "__main__":
    unittest.main()
