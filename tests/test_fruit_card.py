import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app import media


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


if __name__ == "__main__":
    unittest.main()
