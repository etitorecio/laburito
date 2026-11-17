import json
import unittest
from unittest.mock import patch

from app import script_gen


class EnglishScriptTranslationTests(unittest.TestCase):
    def test_translates_generated_scenes_and_preserves_structure(self):
        source = {
            "writer": "template",
            "scenes": [{
                "idx": 0,
                "title": "Apertura",
                "narration": "Esta es una narración suficientemente larga para traducir al inglés.",
                "purpose": "Presentar el tema",
                "visual_query": "tema imagen documental",
                "duration_target_sec": 12,
                "transition": "fundido",
            }],
        }
        translated = {
            "title": "An unexpected secret",
            "topic": "An unexpected secret",
            "scenes": [{
                "idx": 0,
                "title": "Opening",
                "narration": "This is a sufficiently long narration translated into natural English.",
                "purpose": "Introduce the topic",
                "visual_query": "topic documentary image",
            }]
        }
        with patch.object(script_gen, "expand_with_ollama", return_value=json.dumps(translated)):
            result = script_gen.translate_script_with_ollama(
                "http://localhost:11434", "qwen2.5:1.5b-instruct",
                {"topic": "A topic"}, source,
            )
        self.assertEqual(result["language"], "en")
        self.assertEqual(result["translated_title"], "An unexpected secret")
        self.assertEqual(result["translated_topic"], "An unexpected secret")
        self.assertIn("ollama-english-translation", result["writer"])
        self.assertEqual(result["scenes"][0]["narration"], translated["scenes"][0]["narration"])
        self.assertEqual(result["scenes"][0]["duration_target_sec"], 12)
        self.assertEqual(result["scenes"][0]["transition"], "fundido")

    def test_rejects_translation_that_drops_a_scene(self):
        source = {"scenes": [
            {"idx": 0, "narration": "Una narración original suficientemente larga."},
            {"idx": 1, "narration": "Otra narración original suficientemente larga."},
        ]}
        with patch.object(script_gen, "expand_with_ollama", return_value='{"scenes":[]}'):
            with self.assertRaisesRegex(RuntimeError, "cantidad de escenas"):
                script_gen.translate_script_with_ollama(
                    "http://localhost:11434", "qwen2.5:1.5b-instruct", {}, source
                )


if __name__ == "__main__":
    unittest.main()
