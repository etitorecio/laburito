import unittest

from app.script_gen import script_from_text


class UserScriptTests(unittest.TestCase):
    def test_paragraphs_become_ordered_scenes(self):
        result = script_from_text(
            {"title": "Mi historia", "topic": "Una historia"},
            "Primera escena. Sigue la acción.\\n\\nLlega el giro final.",
        )
        self.assertEqual(result["writer"], "user-script")
        self.assertEqual(len(result["scenes"]), 2)
        self.assertEqual([scene["idx"] for scene in result["scenes"]], [0, 1])
        self.assertIn("Primera escena", result["scenes"][0]["narration"])
        self.assertIn("giro final", result["scenes"][1]["narration"])

    def test_long_text_is_split_into_renderable_chunks(self):
        raw = " ".join(["palabra"] * 150)
        result = script_from_text({"title": "Prueba"}, raw)
        self.assertGreater(len(result["scenes"]), 1)
        self.assertEqual(" ".join(s["narration"] for s in result["scenes"]).split(), raw.split())

    def test_empty_and_oversized_scripts_are_rejected(self):
        with self.assertRaises(ValueError):
            script_from_text({"title": "Prueba"}, "  ")
        with self.assertRaises(ValueError):
            script_from_text({"title": "Prueba"}, "x" * 12001)


if __name__ == "__main__":
    unittest.main()
