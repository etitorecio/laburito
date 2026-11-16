import unittest

from app.commands import interpret_prompt


class NaturalLanguageCommandTests(unittest.TestCase):
    def test_short_about_topic(self):
        result = interpret_prompt("haceme un short sobre la historia de Nirvana")
        self.assertEqual(result["template"], "shorts")
        self.assertEqual(result["topic"], "la historia de Nirvana")
        self.assertEqual(result["aspect"], "9:16")

    def test_terror_story_uses_historias_factory(self):
        result = interpret_prompt("haceme una historia de terror sobre un bosque")
        self.assertEqual(result["template"], "reddit_story")
        self.assertEqual(result["channel_name"], "Historias")
        self.assertEqual(result["topic"], "un bosque")

    def test_frutinovela_uses_episodic_factory(self):
        result = interpret_prompt("haceme una frutinovela")
        self.assertEqual(result["template"], "frutinovela")
        self.assertEqual(result["channel_name"], "Frutinovelas")
        self.assertEqual(result["topic"], "Frutinovela original")

    def test_documentary_is_landscape_longform(self):
        result = interpret_prompt("creame un documental sobre la historia de los pedales")
        self.assertEqual(result["template"], "longform")
        self.assertEqual(result["topic"], "la historia de los pedales")
        self.assertEqual(result["aspect"], "16:9")

    def test_empty_command_is_rejected(self):
        with self.assertRaises(ValueError):
            interpret_prompt("   ")


if __name__ == "__main__":
    unittest.main()
