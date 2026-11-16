import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image
from starlette.datastructures import Headers, UploadFile

from app.main import upload_scene_image


class SceneImageUploadTests(unittest.TestCase):
    def make_png(self):
        buffer = io.BytesIO()
        Image.new("RGB", (64, 48), (30, 90, 140)).save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    def test_uploads_and_registers_user_image_for_scene(self):
        scene = {"id": 7, "project_id": 3}
        upload = UploadFile(
            filename="mi-imagen.png",
            file=self.make_png(),
            headers=Headers({"content-type": "image/png"}),
        )
        with tempfile.TemporaryDirectory() as temp, \
             patch("app.main.db.MEDIA_DIR", Path(temp)), \
             patch("app.main.db.query_one", side_effect=[scene, scene]), \
             patch("app.main.db.execute") as execute, \
             patch("app.main._touch_project") as touch:
            result = asyncio.run(upload_scene_image(7, upload))
            files = list((Path(temp) / "uploads" / "3").glob("scene-7-*.jpg"))
            self.assertTrue(result["ok"])
            self.assertEqual(len(files), 1)
            self.assertGreater(files[0].stat().st_size, 100)
            self.assertEqual(execute.call_count, 2)
            touch.assert_called_once_with(3)

    def test_rejects_non_image_uploads(self):
        upload = UploadFile(
            filename="script.txt",
            file=io.BytesIO(b"not an image"),
            headers=Headers({"content-type": "text/plain"}),
        )
        with patch("app.main.db.query_one", return_value={"id": 7, "project_id": 3}):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(upload_scene_image(7, upload))
        self.assertEqual(error.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
