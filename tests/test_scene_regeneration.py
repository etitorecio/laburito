import unittest
from unittest.mock import patch

from app import script_gen


class SceneRegenerationTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "title": "Historia de los pedales",
            "topic": "pedales de guitarra",
            "template": "documentary",
        }
        self.scene = {
            "title": "El primer efecto",
            "narration": (
                "En 1962, una modificación del circuito cambió el sonido de la guitarra. "
                "El efecto empezó a llamar la atención de músicos y fabricantes."
            ),
        }

    @patch("app.script_gen.expand_with_ollama")
    def test_regenerates_one_scene_and_preserves_local_writer_label(self, expand):
        expand.return_value = (
            '{"narration":"En 1962, una modificación del circuito transformó el sonido de la guitarra. '
            'Ese efecto empezó a despertar el interés de músicos y fabricantes."}'
        )
        result = script_gen.regenerate_scene_with_ollama(
            "http://localhost:11434", "qwen2.5:1.5b-instruct",
            self.project, self.scene,
        )
        self.assertEqual(result["writer"], "ollama-local-scene")
        self.assertIn("1962", result["narration"])
        self.assertGreater(len(result["narration"]), 40)

    @patch("app.script_gen.expand_with_ollama")
    def test_rejects_non_json_response(self, expand):
        expand.return_value = "No pude generar la escena."
        with self.assertRaisesRegex(RuntimeError, "JSON válido"):
            script_gen.regenerate_scene_with_ollama(
                "http://localhost:11434", "qwen2.5:1.5b-instruct",
                self.project, self.scene,
            )

    @patch("app.script_gen.expand_with_ollama")
    def test_rejects_too_short_response(self, expand):
        expand.return_value = '{"narration":"Texto corto."}'
        with self.assertRaisesRegex(RuntimeError, "demasiado corta"):
            script_gen.regenerate_scene_with_ollama(
                "http://localhost:11434", "qwen2.5:1.5b-instruct",
                self.project, self.scene,
            )


if __name__ == "__main__":
    unittest.main()
