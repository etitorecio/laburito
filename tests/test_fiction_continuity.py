import unittest

from unittest.mock import patch

from app import script_gen
from app.script_gen import generate_script


class FictionContinuityTests(unittest.TestCase):
    def test_local_fiction_writer_receives_series_context(self):
        project = {
            "template": "frutinovela",
            "duration_target_sec": 90,
            "title": "Los Frutos · Episodio 2",
            "topic": "Una herencia cambia las alianzas",
            "content_pillars": "Manzana, Banana, Pera y Naranja",
            "series_context": "Continuar después de que Manzana encontró una carta y ocultó su contenido.",
        }
        script = {"scenes": [{"idx": 0, "title": "La carta", "duration_target_sec": 15}]}
        captured = {}

        def stop_after_capture(url, model, prompt, timeout=240):
            captured["prompt"] = prompt
            raise RuntimeError("captured")

        with patch.object(script_gen, "expand_with_ollama", side_effect=stop_after_capture):
            with self.assertRaisesRegex(RuntimeError, "captured"):
                script_gen.rewrite_fiction_with_ollama("http://localhost", "qwen", project, script)
        self.assertIn(project["series_context"], captured["prompt"])

    def test_frutinovela_opening_carries_previous_episode_recap(self):
        result = generate_script({
            "id": 101,
            "title": "Los Frutos · Episodio 2",
            "topic": "Los Frutos: una herencia cambia las alianzas",
            "kind": "short",
            "template": "frutinovela",
            "duration_target_sec": 90,
            "content_pillars": "Manzana, Banana, Pera y Naranja",
            "tone": "Dinámico y cercano",
            "hook_style": "Dato sorprendente",
            "cta": "En el próximo seguimos",
            "continuity_recap": "Manzana encontró una carta escondida y decidió no contarle nada a Banana",
        })
        self.assertIn("Manzana encontró una carta escondida", result["scenes"][0]["narration"])


if __name__ == "__main__":
    unittest.main()
