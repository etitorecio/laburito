import json
import unittest
from unittest.mock import patch

from app import script_gen


class DocumentaryScriptTests(unittest.TestCase):
    def test_documentary_blueprint_is_topic_neutral_and_complete(self):
        beats = script_gen.blueprint("documentary")
        self.assertEqual(len(beats), 10)
        self.assertAlmostEqual(sum(beat["weight"] for beat in beats), 1.0)
        joined = " ".join(beat["narration"] for beat in beats).lower()
        self.assertNotIn("guitarra", joined)
        self.assertNotIn("pedal", joined)
        self.assertTrue(all(beat["title"] and beat["purpose"] for beat in beats))


    def test_sparse_research_never_creates_empty_documentary_scenes(self):
        claim = "El registro describe un cambio documentado en el proceso. " * 12
        result = script_gen.generate_script(
            {
                "kind": "long",
                "template": "longform",
                "duration_target_sec": 600,
                "title": "Historia de una innovación",
                "topic": "Historia de una innovación",
            },
            notes=[{
                "source_url": "https://example.org/history",
                "claim": claim,
                "evidence_level": "hecho",
            }],
            sources=[],
        )
        self.assertEqual(len(result["scenes"]), 10)
        self.assertTrue(all(scene["narration"].strip() for scene in result["scenes"]))

    def test_longform_ollama_prompt_requests_documentary_length(self):
        scenes = [
            {"idx": i, "title": f"Escena {i + 1}", "duration_target_sec": 60}
            for i in range(10)
        ]
        narration = " ".join(["contexto"] * 90)
        response = json.dumps({
            "scenes": [{"idx": i, "narration": narration} for i in range(10)]
        })
        notes = [{
            "source_url": "https://example.org/source",
            "claim": "Evidencia documentada. " * 25,
        }]
        with patch.object(script_gen, "expand_with_ollama", return_value=response) as expand:
            result = script_gen.rewrite_with_ollama(
                "http://localhost:11434", "qwen2.5:1.5b-instruct",
                {"kind": "long", "duration_target_sec": 600, "topic": "Historia de prueba"},
                {"scenes": scenes, "warnings": []}, notes,
            )
        self.assertEqual(result["writer"], "ollama-local")
        self.assertEqual(len(result["scenes"]), 10)
        args, kwargs = expand.call_args
        self.assertIn("DOCUMENTAL HORIZONTAL DE FORMATO LARGO", args[2])
        self.assertIn("Duración total objetivo: 600 segundos", args[2])
        self.assertEqual(kwargs["timeout"], 900)
        self.assertEqual(kwargs["num_predict"], 6144)

    def test_longform_rejects_a_short_summary(self):
        scenes = [{"idx": i, "title": f"Escena {i}", "duration_target_sec": 60} for i in range(10)]
        short_text = " ".join(["resumen"] * 20)
        response = json.dumps({"scenes": [{"idx": i, "narration": short_text} for i in range(10)]})
        notes = [{"source_url": "https://example.org/source", "claim": "Dato documentado. " * 30}]
        with patch.object(script_gen, "expand_with_ollama", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "se requieren"):
                script_gen.rewrite_with_ollama(
                    "http://localhost:11434", "qwen2.5:1.5b-instruct",
                    {"kind": "long", "duration_target_sec": 600, "topic": "Historia de prueba"},
                    {"scenes": scenes, "warnings": []}, notes,
                )


if __name__ == "__main__":
    unittest.main()
