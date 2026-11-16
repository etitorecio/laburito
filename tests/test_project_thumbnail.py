import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from starlette.datastructures import Headers, UploadFile

from app.main import upload_project_thumbnail


class ProjectThumbnailTests(unittest.TestCase):
    def test_uploads_custom_thumbnail_and_registers_asset(self):
        buffer = io.BytesIO()
        Image.new("RGB", (320, 180), (90, 40, 120)).save(buffer, format="PNG")
        buffer.seek(0)
        upload = UploadFile(
            filename="cover.png",
            file=buffer,
            headers=Headers({"content-type": "image/png"}),
        )
        with tempfile.TemporaryDirectory() as temp, \
             patch("app.main.db.query_one", return_value={"id": 5, "aspect": "16:9", "resolution": "1080p"}), \
             patch("app.main.db.MEDIA_DIR", Path(temp)), \
             patch("app.main.db.execute") as execute, \
             patch("app.main._touch_project") as touch:
            result = asyncio.run(upload_project_thumbnail(5, upload))
            saved = Path(result["path"])
            self.assertTrue(result["ok"])
            self.assertTrue(saved.is_file())
            self.assertGreater(saved.stat().st_size, 100)
            self.assertIn("thumbnail", execute.call_args.args[0])
            touch.assert_called_once_with(5)

    def test_rejects_non_image_thumbnail(self):
        upload = UploadFile(
            filename="notes.txt",
            file=io.BytesIO(b"not an image"),
            headers=Headers({"content-type": "text/plain"}),
        )
        with patch("app.main.db.query_one", return_value={"id": 5}):
            with self.assertRaises(Exception):
                asyncio.run(upload_project_thumbnail(5, upload))


if __name__ == "__main__":
    unittest.main()
