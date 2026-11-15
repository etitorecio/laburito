import json
import json
import os
import unittest
from unittest.mock import patch
import urllib.parse

from app import autopilot, publish, script_gen, topic_engine, tts


class AutopilotResearchTests(unittest.TestCase):
    def test_shorts_autopilot_saves_editorial_brief_and_bounds_duration(self):
        clean = autopilot._clean({
            "template": "shorts",
            "duration_target_sec": 180,
            "audience": "Jóvenes interesados en ciencia",
            "tone": "Dinámico y cercano",
            "hook_style": "Pregunta intrigante",
            "cta": "Invitá a comentar una opinión",
            "content_pillars": "Espacio, física, curiosidades",
            "avoid_topics": "Desinformación médica",
        })
        self.assertEqual(clean["duration_target_sec"], 90)
        self.assertEqual(clean["audience"], "Jóvenes interesados en ciencia")
        self.assertEqual(clean["hook_style"], "Pregunta intrigante")
        self.assertEqual(clean["content_pillars"], "Espacio, física, curiosidades")
        self.assertEqual(clean["avoid_topics"], "Desinformación médica")


    def test_short_quantity_maps_to_exact_interval(self):
        clean = autopilot._clean({
            "videos_per_period": 1,
            "period_days": 1,
            "schedule_time": "09:30",
            "timezone": "America/Argentina/Buenos_Aires",
        })
        self.assertEqual(clean["cadence_minutes"], 1440)
        self.assertEqual(clean["cadence_hours"], 24)
        self.assertEqual(clean["schedule_time"], "09:30")

    def test_two_shorts_per_day_maps_to_twelve_hours(self):
        clean = autopilot._clean({"videos_per_period": 2, "period_days": 1})
        self.assertEqual(clean["cadence_minutes"], 720)

    def test_next_run_respects_argentina_local_time(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        rule = {
            "schedule_time": "10:00",
            "timezone": "America/Argentina/Buenos_Aires",
            "cadence_minutes": 1440,
        }
        after = datetime(2026, 11, 14, 9, 0, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires"))
        self.assertEqual(autopilot._next_run_at(rule, after), "2026-11-14T13:00:00Z")

    def test_piper_cli_is_installed_by_backend_requirements(self):
        self.assertTrue(tts.piper_path())
        self.assertEqual(tts.VOICES["es-es-piper"]["language"], "es")
    def test_reactivating_autopilot_schedules_immediate_run(self):
        current = {"id": 7, "enabled": False, "niche": "ciencia", "cadence_hours": 24}
        updated = {**current, "enabled": True}
        with patch.object(autopilot, "ensure_schema"):
            with patch.object(autopilot, "get_rule", side_effect=[current, updated]):
                with patch.object(autopilot, "_next_run_at", return_value="next-slot"):
                    with patch.object(autopilot.db, "execute") as execute:
                        autopilot.update_rule(7, {"enabled": True})
        self.assertIn("next_run_at", execute.call_args.args[0])
        self.assertIn("next-slot", execute.call_args.args[1])

    def test_autopilot_builds_script_from_only_the_current_topics_sources(self):
        extract = " ".join([
            "Este estudio describe con evidencia documentada un proceso histórico y sus consecuencias.",
            "Los registros analizados permiten reconstruir el contexto y las decisiones de sus protagonistas.",
            "Los investigadores compararon documentos originales con publicaciones posteriores.",
            "Los resultados modificaron la interpretación que existía sobre este fenómeno.",
            "El análisis identifica límites y preguntas que todavía requieren investigación adicional.",
            "Nuevos documentos permitieron revisar las hipótesis y ampliar el conocimiento disponible.",
        ])
        notes = [
            {"id": 501, "source_url": "https://es.wikipedia.org/wiki/Tema", "claim": extract},
            {"id": 502, "source_url": "https://doi.org/10.1234/example", "claim": extract},
        ]
        research = {
            "title": "Tema recién descubierto",
            "topic": "Tema recién descubierto",
            "summary": extract,
            "url": "https://es.wikipedia.org/wiki/Tema",
            "note_ids": [501, 502],
            "academic_sources": [{
                "title": "Estudio independiente",
                "url": "https://doi.org/10.1234/example",
                "author": "Equipo de investigación",
            }],
            "references": [],
        }
        project = {
            "id": 999,
            "title": "Tema recién descubierto",
            "topic": "Tema recién descubierto",
            "kind": "short",
            "template": "shorts",
            "duration_target_sec": 60,
        }
        rule = {
            "id": 4, "name": "Prueba", "niche": "historia",
            "channel_id": None, "template": "shorts", "duration_target_sec": 60,
            "voice": "es", "aspect": "9:16", "caption_style": "short_pop",
            "transition_default": "fundido", "resolution": "1080p", "fps": 25,
            "music": "auto", "music_volume": 0.12,
        }
        with patch.object(topic_engine, "research_topic", return_value=research):
            with patch.object(autopilot.db, "query", side_effect=[[], notes, []]) as query:
                with patch.object(autopilot.db, "query_one", return_value=project):
                    with patch.object(autopilot.db, "execute", return_value=999):
                        with patch.object(autopilot.db, "get_setting", return_value=""):
                            result = autopilot._create_project(rule)
        self.assertEqual(result["project_id"], 999)
        self.assertEqual(result["evidence_sources"], 2)
        self.assertEqual(result["script_writer"], "source-extract")
        self.assertIn("id IN", query.call_args_list[1].args[0])
        self.assertEqual(query.call_args_list[1].args[1], (501, 502))

    def test_autopilot_holds_publication_for_unrewritten_script(self):
        rule = {"id": 9, "auto_publish": True, "cadence_hours": 24, "destination": "youtube", "privacy": "unlisted"}
        with patch.object(autopilot, "get_rule", return_value=rule):
            with patch.object(autopilot, "_create_project", return_value={"project_id": 77, "script_writer": "source-extract"}):
                with patch("app.publish.set_auto_publish") as set_publish:
                    with patch("app.worker.enqueue", return_value=88):
                        with patch.object(autopilot.db, "execute"):
                            with patch.object(autopilot.db, "now", return_value="now"):
                                with patch.object(autopilot, "_ts", return_value="later"):
                                    result = autopilot.run_rule(9)
        set_publish.assert_not_called()
        self.assertEqual(result["project_id"], 77)
        self.assertIn("retenida", result["publish_warning"])

    def test_script_without_sources_is_marked_as_template_only(self):
        result = script_gen.generate_script(
            {"id": 1001, "topic": "Tema sin fuentes", "kind": "short", "template": "shorts", "duration_target_sec": 45},
            [],
            [],
        )
        self.assertEqual(result["writer"], "template")
        self.assertIn("no publicar automáticamente", result["warnings"][0])

    def test_research_topic_returns_only_its_own_note_ids(self):
        topic = {"title": "Tema nuevo", "summary": "Resumen de orientación", "url": "https://es.wikipedia.org/wiki/Tema"}
        academic = [{"title": "Artículo", "url": "https://doi.org/10.1/test", "abstract": "Resumen académico"}]
        with patch.object(topic_engine, "choose_topic", return_value=topic):
            with patch.object(topic_engine, "_openalex_abstracts", return_value=academic):
                with patch.object(topic_engine.db, "now", return_value="now"):
                    with patch.object(topic_engine.db, "execute", side_effect=[101, 102]):
                        result = topic_engine.research_topic("ciencia", [])
        self.assertEqual(result["note_ids"], [101, 102])
        self.assertEqual(result["academic_sources"], academic)

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
        self.assertIn("extractos de una fuente de orientación", result["warnings"][0])
        self.assertTrue(all(len(scene["narration"]) >= 45 for scene in result["scenes"]))


if __name__ == "__main__":
    unittest.main()