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
    def test_topic_picker_skips_near_duplicate_titles(self):
        self.assertTrue(topic_engine._is_duplicate("Historia de la radio", ["La historia de la radio"]))
        self.assertFalse(topic_engine._is_duplicate("Historia de la televisión", ["Historia de la radio"]))

    def test_topic_normalization_helps_avoid_repeats(self):
        self.assertEqual(topic_engine._normal("Historia: del Rock!"), "historia del rock")

    def test_youtube_credentials_prefer_server_stored_refresh_token(self):
        with patch.dict(os.environ, {
            "YOUTUBE_CLIENT_ID": "client-id",
            "YOUTUBE_CLIENT_SECRET": "client-secret",
            "YOUTUBE_REFRESH_TOKEN": "old-environment-token",
        }):
            with patch("app.publish.db.get_setting", return_value="stored-refresh-token"):
                credentials = publish.youtube_credentials()
        self.assertEqual(credentials["refresh_token"], "stored-refresh-token")
        self.assertEqual(credentials["client_id"], "client-id")

    def test_youtube_account_status_uses_authorized_channel_api(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"items":[{"id":"UC123","snippet":{"title":"Canal de prueba"}}]}'

        with patch("app.publish._youtube_token", return_value="access-token"):
            with patch("app.publish.urllib.request.urlopen", return_value=FakeResponse()) as request:
                result = publish.youtube_account_status()
        self.assertEqual(result["channel_title"], "Canal de prueba")
        self.assertEqual(request.call_args.args[0].get_header("Authorization"), "Bearer access-token")

    def test_youtube_autopublish_requires_live_channel_verification(self):
        with patch.object(publish, "ensure_schema"):
            with patch.object(publish.db, "query_one", return_value={"id": 1}):
                with patch.object(publish.db, "execute"):
                    with patch.object(publish, "youtube_account_status") as verify:
                        publish.set_auto_publish(1, True, "youtube")
        verify.assert_called_once_with()

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