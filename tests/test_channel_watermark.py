import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import main


class Upload:
    content_type = "image/png"

    def __init__(self, data):
        self.data = data

    async def read(self, size=-1):
        return self.data[:size]


class ChannelWatermarkTests(unittest.TestCase):
    def test_upload_normalizes_and_enables_channel_logo(self):
        buffer = io.BytesIO()
        Image.new("RGBA", (40, 20), (255, 0, 0, 128)).save(buffer, format="PNG")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(main.db, "DATA_DIR", Path(tmp)), \
                 patch.object(main.db, "query_one", side_effect=[{"id": 4}, {"id": 4, "watermark_enabled": 1}]), \
                 patch.object(main.db, "execute") as execute:
                result = asyncio.run(main.upload_channel_watermark(4, Upload(buffer.getvalue())))
            target = Path(result.get("watermark_path") or (Path(tmp) / "channels" / "4" / "watermark.png"))
            self.assertTrue(target.is_file())
            self.assertEqual(result["watermark_enabled"], 1)
            self.assertEqual(execute.call_count, 1)

    def test_watermark_settings_are_clamped_and_validated(self):
        with patch.object(main.db, "query_one", return_value={"id": 4}), \
             patch.object(main.db, "execute") as execute:
            main.update_channel_watermark(
                4,
                main.ChannelWatermarkIn(enabled=True, position="top_right", scale=0.9, opacity=0.01),
            )
        values = execute.call_args.args[1]
        self.assertEqual(values[0], 1)
        self.assertEqual(values[1], "top_right")
        self.assertEqual(values[2], 0.35)
        self.assertEqual(values[3], 0.1)

    def test_watermark_rejects_unknown_positions(self):
        with patch.object(main.db, "query_one", return_value={"id": 4}):
            with self.assertRaises(main.HTTPException):
                main.update_channel_watermark(
                    4,
                    main.ChannelWatermarkIn(enabled=True, position="off_canvas"),
                )


if __name__ == "__main__":
    unittest.main()
