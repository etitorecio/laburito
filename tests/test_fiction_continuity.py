import unittest

from app.script_gen import generate_script


class FictionContinuityTests(unittest.TestCase):
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
