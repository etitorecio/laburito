import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import media, render


class FrutinovelaVisualTests(unittest.TestCase):
    def test_generates_original_fruit_cast_art_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "frutinovela.png"
            media.make_fruit_card(
                output,
                "La traición de Pera",
                "Manzana (protagonista), Banana (pareja), Pera (rival)",
                360,
                640,
            )
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1000)
            with Image.open(output) as image:
                self.assertEqual(image.size, (360, 640))
                self.assertEqual(image.format, "PNG")

    def test_frutinovela_render_uses_local_cast_art_instead_of_stock_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(render, "_size", return_value=(360, 640)):
                with patch.object(render, "_visual_dir", return_value=Path(tmp)):
                    with patch.object(render, "_project_metadata", return_value={
                        "characters": "Manzana (protagonista), Banana (pareja), Pera (rival)"
                    }):
                        visual, kind, info = render.ensure_visual(
                            {"id": 1, "template": "frutinovela", "video_type": "moving_images", "kind": "short"},
                            {"idx": 0, "title": "La traición de Pera", "visual_path": ""},
                        )
            self.assertTrue(visual.exists())
            self.assertEqual(kind, "frutinovela_local")
            self.assertIn("procedural", info["license"].lower())


if __name__ == "__main__":
    unittest.main()
