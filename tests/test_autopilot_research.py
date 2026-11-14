import json
import json
import os
import unittest
from unittest.mock import patch
import urllib.parse

from app import publish, script_gen, topic_engine, tts


class AutopilotResearchTests(unittest.TestCase):
    def test_piper_cli_is_installed_by_backend_requirements(self):
        self.assertTrue(tts.piper_path())
        self.assertEqual(tts.VOICES["es-es-piper"]["language"], "es")
    def test_topic_normalization_helps_avoid_repeats(self):
        self.assertEqual(topic_engine._normal("Historia: del Rock!"), "historia del rock")

    def test_youtube_device_start_requests_supported_youtube_scope(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"device_code":"device-123","user_code":"ABCD-EFGH","verification_url":"https://www.google.com/device","expires_in":1800,"interval":5}'

        with patch.dict(os.environ, {
            "YOUTUBE_CLIENT_ID": "client-id",
            "YOUTUBE_CLIENT_SECRET": "client-secret",
            "YOUTUBE_REFRESH_TOKEN": "existing-refresh",
        }):
            with patch("app.publish.db.get_setting", return_value=""):
                with patch("app.publish.urllib.request.urlopen", return_value=FakeResponse()) as request:
                    result = publish.youtube_device_start()
        body = urllib.parse.parse_qs(request.call_args.args[0].data.decode())
        self.assertEqual(body["scope"], ["https://www.googleapis.com/auth/youtube"])
        self.assertEqual(result["user_code"], "ABCD-EFGH")

    def test_youtube_device_poll_saves_refresh_token(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"access_token":"access","refresh_token":"new-refresh","scope":"https://www.googleapis.com/auth/youtube"}'

        with patch.dict(os.environ, {
            "YOUTUBE_CLIENT_ID": "client-id",
            "YOUTUBE_CLIENT_SECRET": "client-secret",
            "YOUTUBE_REFRESH_TOKEN": "",
        }):
            with patch("app.publish.db.get_setting", return_value=""):
                with patch("app.publish.urllib.request.urlopen", return_value=FakeResponse()):
                    with patch("app.publish.db.set_setting") as save:
                        result = publish.youtube_device_poll("device-123")
        self.assertEqual(result["status"], "connected")
        save.assert_called_once_with("youtube_refresh_token", "new-refresh")

    def test_ollama_rewrite_keeps_scene_structure(self):
        from unittest.mock import patch

        project = {"id": 1000, "topic": "Tema", "kind": "short", "template": "shorts", "duration_target_sec": 60}
        notes = [{"source_url": "https://example.org/source", "claim": " ".join(["Hecho documentado con suficiente contexto para redactar una escena completa."] * 12)}]
        script = script_gen.generate_script(project, notes, [])
        response = {"scenes": [{"idx": scene["idx"], "narration": "Esta es una narración original basada solamente en los datos aportados por la fuente."} for scene in script["scenes"]]}
        with patch.object(script_gen, "expand_with_ollama", return_value=json.dumps(response)):
            rewritten = script_gen.rewrite_with_ollama("http://localhost:11434", "llama3.2", project, script, notes)
        self.assertEqual(rewritten["writer"], "ollama-local")
        self.assertEqual(len(rewritten["scenes"]), len(script["scenes"]))
    def test_topic_picker_skips_previously_used_titles(self):
        from unittest.mock import patch

        article = " ".join(
            ["Este artículo contiene información histórica suficiente para investigar el tema."]
            * 12
        )
        responses = [
            {"query": {"search": [{"title": "Tema repetido"}, {"title": "Tema nuevo"}]}},
            {"query": {"search": []}},
            {"query": {"search": []}},
            {"query": {"search": []}},
            {"query": {"pages": {"1": {"extract": article, "fullurl": "https://es.wikipedia.org/wiki/Tema_nuevo"}}}},
            {"query": {"pages": {"1": {"extlinks": []}}}},
        ]
        with patch.object(topic_engine, "_get", side_effect=responses):
            result = topic_engine.choose_topic("misterio", ["Tema repetido"])
        self.assertEqual(result["topic"], "Tema nuevo")
    def test_script_uses_retrieved_source_sentences(self):
        extract = "La fuente describe un proceso histórico documentado con detalles verificables y fechas precisas. "
        extract += "Los investigadores analizaron los registros conservados durante varias décadas. "
        extract += "El descubrimiento modificó la manera en que se entendía el fenómeno en su época. "
        extract += "Los documentos posteriores permitieron reconstruir las decisiones de sus protagonistas. "
        extract += "La evolución técnica produjo cambios importantes en las comunidades relacionadas. "
        extract += "Las consecuencias todavía se estudian mediante archivos y publicaciones especializadas."
        result = script_gen.generate_script(
            {"id": 999, "topic": "Un tema documentado", "kind": "short", "template": "shorts", "duration_target_sec": 60},
            [{"source_url": "https://example.org/source", "claim": extract, "evidence_level": "indicio"}],
            [],
        )
        narration = " ".join(scene["narration"] for scene in result["scenes"])
        self.assertIn("La fuente describe", narration)
        self.assertIn("Las consecuencias todavía se estudian", narration)
        self.assertIn("Guion local basado en texto de fuente", result["warnings"][0])


if __name__ == "__main__":
    unittest.main()