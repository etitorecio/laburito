import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO

from fastapi import UploadFile
from starlette.datastructures import Headers
from PIL import Image
import urllib.parse

from app import autopilot, main as main_app, options, publish, render, script_gen, topic_engine, tts, worker


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
        self.assertEqual(clean["duration_target_sec"], 180)
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

    def test_autopilot_supports_longform_and_landscape(self):
        clean = autopilot._clean({
            "template": "longform",
            "duration_target_sec": 1200,
            "aspect": "16:9",
        })
        self.assertEqual(clean["template"], "longform")
        self.assertEqual(clean["duration_target_sec"], 1200)
        self.assertEqual(clean["aspect"], "16:9")

    def test_longform_autopilot_creates_documentary_project(self):
        project = {"id": 42, "title": "Documental de prueba", "notes": ""}
        research = {
            "topic": "La historia del universo",
            "url": "https://es.wikipedia.org/wiki/Universo",
            "source_title": "Universo",
            "trend_signals": [],
            "references": [],
            "academic_sources": [],
            "note_ids": [],
        }
        rule = {"template": "longform", "niche": "ciencia", "duration_target_sec": 600, "voice": "es"}
        with patch.object(topic_engine, "research_topic", return_value=research):
            with patch.object(autopilot.db, "query", side_effect=[[], []]):
                with patch.object(autopilot.db, "query_one", return_value=project):
                    with patch.object(autopilot.db, "execute", return_value=42) as execute:
                        with patch.object(autopilot.db, "get_setting", return_value=""):
                            with patch.object(autopilot.db, "now", return_value="2026-11-15T00:00:00Z"):
                                with patch.object(script_gen, "generate_script", return_value={"scenes": [], "writer": "template", "evidence_sources": 0}):
                                    with patch.object(autopilot.db, "log"):
                                        autopilot._create_project(rule)
        inserted = execute.call_args_list[0].args[1]
        self.assertEqual(inserted[3], "documentary")
        self.assertEqual(inserted[4], "16:9")
        self.assertEqual(inserted[6], 600)

    def test_autopilot_longform_duration_is_bounded_to_twenty_minutes(self):
        self.assertEqual(
            autopilot._clean({"template": "longform", "duration_target_sec": 1800})["duration_target_sec"],
            1200,
        )

    def test_autopilot_rejects_unsupported_aspect_ratio(self):
        with self.assertRaisesRegex(ValueError, "Formato de video no válido"):
            autopilot._clean({"aspect": "3:2"})

    def test_skeleton_autopilot_is_limited_to_seven_minutes(self):
        with self.assertRaisesRegex(ValueError, "máxima de 7 minutos"):
            autopilot._clean({"template": "longform", "duration_target_sec": 600, "video_type": "skeleton"})

    def test_autopilot_can_disable_captions_without_affecting_regular_projects(self):
        notes = "Autopiloto: ciencia. [LABURITO_META]" + json.dumps({"captions_enabled": False})
        self.assertFalse(render._captions_enabled({"notes": notes}))
        self.assertTrue(render._captions_enabled({"notes": "Proyecto normal"}))

    def test_thumbnail_generation_is_enabled_by_default_and_can_be_disabled(self):
        self.assertTrue(render._thumbnail_enabled({"notes": ""}))
        notes = "[LABURITO_META]" + json.dumps({"create_thumbnail": False})
        self.assertFalse(render._thumbnail_enabled({"notes": notes}))

    def test_custom_visual_prompt_selects_a_local_filter_and_search_hint(self):
        notes = "[LABURITO_META]" + json.dumps({
            "captions_enabled": True,
            "visual_style_prompt": "Anime cyberpunk con luces de neón",
        })
        project = {"notes": notes, "visual_style": "automatico"}
        self.assertEqual(render._custom_visual_style_id(project), "cyberpunk")
        self.assertEqual(render._project_metadata(project)["visual_style_prompt"], "Anime cyberpunk con luces de neón")

    def test_visual_reference_image_is_analyzed_locally(self):
        buffer = BytesIO()
        Image.new("RGB", (24, 24), (20, 45, 190)).save(buffer, format="PNG")
        buffer.seek(0)
        upload = UploadFile(
            filename="referencia.png",
            file=buffer,
            headers=Headers({"content-type": "image/png"}),
        )
        result = asyncio.run(main_app.analyze_visual_style_reference(upload))
        self.assertIn("azulada", result["visual_style_prompt"])
        self.assertIn("localmente", result["analysis"])

    def test_autopilot_short_duration_supports_youtube_three_minute_limit(self):
        self.assertEqual(autopilot._clean({"template": "shorts", "duration_target_sec": 180})["duration_target_sec"], 180)
        self.assertEqual(autopilot._clean({"template": "shorts", "duration_target_sec": 240})["duration_target_sec"], 180)

    def test_manual_video_defaults_to_cpu_friendly_720p(self):
        self.assertEqual(options.resolve_defaults({"template": "shorts"})["resolution"], "720p")

    def test_youtube_autopilot_requires_valid_vertical_short_file(self):
        from pathlib import Path
        project = {"kind": "short", "notes": "Autopiloto: diario"}
        with patch("app.media.probe_video", return_value={"width": 1080, "height": 1920, "duration": 180.1}):
            with self.assertRaisesRegex(publish.PublishError, "máximo es 180"):
                publish._validate_autopilot_short(project, Path("fake.mp4"))
        with patch("app.media.probe_video", return_value={"width": 1920, "height": 1080, "duration": 30}):
            with self.assertRaisesRegex(publish.PublishError, "debe ser vertical o cuadrado"):
                publish._validate_autopilot_short(project, Path("fake.mp4"))

    def test_youtube_autopilot_accepts_square_shorts(self):
        from pathlib import Path
        project = {"kind": "short", "aspect": "1:1", "notes": "Autopiloto: lista"}
        info = {"width": 1080, "height": 1080, "duration": 45}
        with patch("app.media.probe_video", return_value=info):
            self.assertEqual(publish._validate_autopilot_short(project, Path("fake.mp4")), info)

    def test_youtube_autopilot_accepts_valid_longform_video(self):
        from pathlib import Path
        project = {"kind": "documentary", "notes": "Autopiloto: ciencia"}
        info = {"width": 1920, "height": 1080, "duration": 600}
        with patch("app.media.probe_video", return_value=info):
            self.assertEqual(publish._validate_autopilot_video(project, Path("fake.mp4")), info)

    def test_youtube_autopilot_rejects_longform_over_twenty_minutes(self):
        from pathlib import Path
        project = {"kind": "documentary", "notes": "Autopiloto: ciencia"}
        with patch("app.media.probe_video", return_value={"width": 1920, "height": 1080, "duration": 1201}):
            with self.assertRaisesRegex(publish.PublishError, "máximo es 20 minutos"):
                publish._validate_autopilot_video(project, Path("fake.mp4"))

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

    def test_autopilot_blocks_auto_publish_when_render_has_silence(self):
        self.assertIn("sin narración", worker._auto_publish_blocker({
            "quality": {"tts_engines": ["silencio"]},
        }))
        self.assertEqual(worker._auto_publish_blocker({
            "quality": {"tts_engines": ["espeak-ng"]},
        }), "")

    def test_manual_generation_does_not_move_future_schedule(self):
        rule = {"next_run_at": "2026-11-16T13:00:00Z"}
        self.assertEqual(
            autopilot._next_after_run(rule, force=True, now="2026-11-15T13:00:00Z"),
            "2026-11-16T13:00:00Z",
        )
        with patch.object(autopilot, "_next_run_at", return_value="next-slot"):
            self.assertEqual(
                autopilot._next_after_run({"next_run_at": "2026-11-14T13:00:00Z"}, force=True, now="2026-11-15T13:00:00Z"),
                "next-slot",
            )

    def test_piper_cli_is_installed_by_backend_requirements(self):
        self.assertTrue(tts.piper_path())
        self.assertEqual(tts.VOICES["es-es-piper"]["language"], "es")
    def test_reactivating_autopilot_schedules_immediate_run(self):
        current = {"id": 7, "enabled": False, "niche": "ciencia", "cadence_hours": 24}
        updated = {**current, "enabled": True}
        with patch.object(autopilot, "ensure_schema"):
            with patch.object(autopilot, "get_rule", side_effect=[current, updated]):
                with patch.object(autopilot, "_ts", return_value="now"):
                    with patch.object(autopilot.db, "execute") as execute:
                        autopilot.update_rule(7, {"enabled": True})
        self.assertIn("next_run_at", execute.call_args.args[0])
        self.assertIn("now", execute.call_args.args[1])

    def test_autopilot_accepts_english_voice(self):
        self.assertEqual(autopilot._clean({"voice": "en-us"})["voice"], "en-us")

    def test_autopilot_voice_speed_and_pitch_are_bounded(self):
        clean = autopilot._clean({"speed": 999, "pitch": -5})
        self.assertEqual(clean["speed"], 300)
        self.assertEqual(clean["pitch"], 0)

    def test_autopilot_accepts_music_bed_picker_identifier(self):
        bed_id = sorted(options.MUSIC_IDS)[0]
        self.assertEqual(autopilot._clean({"music": "bed:" + bed_id})["music"], "bed:" + bed_id)

    def test_autopilot_counts_all_supported_clip_extensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            clip_dir = Path(temporary) / "background_clips" / "minecraft"
            clip_dir.mkdir(parents=True)
            for index in range(5):
                (clip_dir / f"clip-{index}.webm").write_bytes(b"video")
            with patch.object(autopilot.db, "DATA_DIR", Path(temporary)):
                clean = autopilot._clean({"video_type": "minecraft"})
            self.assertEqual(clean["video_type"], "minecraft")

    def test_script_uses_autopilot_hook_cta_and_visual_style(self):
        project = {
            "id": 777, "title": "La exploración espacial", "topic": "La exploración espacial",
            "kind": "short", "template": "shorts", "duration_target_sec": 30,
            "hook_style": "Pregunta intrigante",
            "tone": "Documental y riguroso",
            "cta": "Invitá a seguir el canal",
            "visual_style": "Fotografía de archivo histórica",
        }
        script = script_gen.generate_script(project, [], [])
        self.assertTrue(script["scenes"][0]["narration"].startswith("¿Qué hay detrás de La exploración espacial?"))
        self.assertIn("Vamos a los datos:", script["scenes"][0]["narration"])
        self.assertIn("Seguime para ver más historias", script["scenes"][-1]["narration"])
        self.assertNotIn("Guardá este vídeo", script["scenes"][-1]["narration"])
        self.assertIn("Fotografía de archivo histórica", script["scenes"][0]["visual_query"])

    def test_topic_research_uses_content_pillars_and_excludes_avoided_topics(self):
        queries = []
        extract = " ".join(["La investigación documenta el desarrollo histórico de este campo y sus principales descubrimientos."] * 12)
        def fake_get(params):
            if params.get("list") == "search":
                queries.append(params["srsearch"])
                if "espacio" in params["srsearch"]:
                    return {"query": {"search": [{"title": "Política espacial"}, {"title": "Astrobiología"}]}}
                return {"query": {"search": []}}
            return {"query": {"pages": {"1": {
                "title": "Astrobiología", "extract": extract,
                "fullurl": "https://es.wikipedia.org/wiki/Astrobiologia",
            }}}}
        with patch.object(topic_engine, "trending_searches", return_value=[]):
            with patch.object(topic_engine, "_get", side_effect=fake_get):
                result = topic_engine.choose_topic("ciencia", [], "espacio", "política")
        self.assertEqual(result["topic"], "Astrobiología")
        self.assertTrue(any("ciencia espacio" in q for q in queries))

    def test_tick_retries_failed_rule_after_fifteen_minutes(self):
        with patch.object(autopilot, "ensure_schema"):
            with patch.object(autopilot.db, "now", return_value="now"):
                with patch.object(autopilot.db, "query", return_value=[{"id": 4}]):
                    with patch.object(autopilot, "run_rule", side_effect=RuntimeError("temporary network error")):
                        with patch.object(autopilot, "get_rule", return_value={"id": 4}):
                            with patch.object(autopilot, "_retry_at", return_value="retry-in-15"):
                                with patch.object(autopilot.db, "execute") as execute:
                                    with patch.object(autopilot.db, "log"):
                                        fired = autopilot.tick()
        self.assertEqual(fired, 0)
        self.assertEqual(execute.call_args.args[1][0], "retry-in-15")
        self.assertIn("temporary network error", execute.call_args.args[1][1])

    def test_autopilot_metadata_controls_change_title_and_tags(self):
        project = {
            "id": 778, "title": "Space exploration", "topic": "Space exploration",
            "kind": "short", "voice": "en-gb", "notes": "[LABURITO_META]" + json.dumps({
                "title_style": "pregunta", "custom_tags": "astronomía, universo",
            }),
        }
        with patch.object(publish.db, "query", return_value=[]):
            metadata = publish.build_metadata(project, [])
        self.assertEqual(metadata["title"], "What's behind Space exploration?")
        self.assertIn("astronomía", metadata["tags"])
        self.assertIn("universo", metadata["tags"])
        self.assertEqual(metadata["language"], "en")
        self.assertIn("scenes · short format · narration in English", metadata["description"])

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

    def test_legacy_youtube_autopilot_is_downgraded_to_manual_approval(self):
        rule = {"id": 10, "auto_publish": True, "cadence_hours": 24, "destination": "youtube", "privacy": "public", "channel_id": 10}
        with patch.object(autopilot, "get_rule", return_value=rule):
            with patch.object(autopilot, "_create_project", return_value={"project_id": 78, "script_writer": "source-extract", "evidence_sources": 1}):
                with patch("app.publish.set_auto_publish") as set_publish:
                    with patch("app.worker.enqueue", return_value=89):
                        with patch.object(autopilot.db, "execute") as execute:
                            with patch.object(autopilot.db, "now", return_value="now"):
                                with patch.object(autopilot.db, "log"):
                                    result = autopilot.run_rule(10)
        set_publish.assert_not_called()
        self.assertEqual(result["publish_warning"], "YouTube requiere aprobación manual; se desactivó la autopublicación de esta regla.")
        self.assertTrue(any("auto_publish=0" in call.args[0] for call in execute.call_args_list))

    def test_new_youtube_rule_defaults_to_manual_approval(self):
        with patch.object(autopilot, "ensure_schema"):
            with patch.object(autopilot, "_validate_factory_channel"):
                with patch.object(autopilot, "_validate_auto_publish"):
                    with patch.object(autopilot.db, "execute", return_value=11):
                        with patch.object(autopilot, "get_rule", return_value={"id": 11, "auto_publish": 0, "destination": "youtube"}):
                            with patch.object(autopilot.db, "now", return_value="now"):
                                result = autopilot.create_rule({"niche": "ciencia"})
        self.assertEqual(result["auto_publish"], 0)

    def test_api_accepts_complete_autopilot_schedule_and_editorial_settings(self):
        from app.main import AutopilotIn, AutopilotPatch
        create = AutopilotIn(
            niche="ciencia", videos_per_period=1, period_days=1,
            schedule_time="09:30", timezone="America/Argentina/Buenos_Aires",
            audience="Jóvenes", tone="Ágil", hook_style="Pregunta",
            cta="Comentá", content_pillars="Espacio", avoid_topics="Rumores",
            speed=165, pitch=52, visual_style="Archivo histórico",
            title_style="pregunta", custom_tags="ciencia, espacio",
        )
        self.assertEqual(create.videos_per_period, 1)
        self.assertEqual(create.schedule_time, "09:30")
        self.assertEqual(create.content_pillars, "Espacio")
        self.assertEqual(create.speed, 165)
        self.assertEqual(create.visual_style, "Archivo histórico")
        patch = AutopilotPatch(videos_per_period=2, period_days=1, schedule_time="12:00", custom_tags="misterio")
        self.assertEqual(patch.videos_per_period, 2)
        self.assertEqual(patch.schedule_time, "12:00")
        self.assertEqual(patch.custom_tags, "misterio")

    def test_autopilot_holds_publication_for_unrewritten_script(self):
        rule = {"id": 9, "auto_publish": True, "cadence_hours": 24, "destination": "youtube", "privacy": "unlisted", "channel_id": 9}
        with patch.object(autopilot, "get_rule", return_value=rule):
            with patch("app.persistence.durable_storage_available", return_value=True):
                with patch("app.publish.youtube_account_status", return_value={"channel_title": "Test channel"}):
                    with patch.object(autopilot, "_create_project", return_value={"project_id": 77, "script_writer": "source-extract"}):
                        with patch("app.publish.set_auto_publish") as set_publish:
                            with patch("app.worker.enqueue", return_value=88):
                                with patch.object(autopilot.db, "execute"):
                                    with patch.object(autopilot.db, "now", return_value="now"):
                                        with patch.object(autopilot, "_ts", return_value="later"):
                                            result = autopilot.run_rule(9)
        set_publish.assert_not_called()
        self.assertEqual(result["project_id"], 77)
        self.assertIn("requiere aprobación manual", result["publish_warning"])

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

    def test_google_trends_only_adds_signals_related_to_the_niche(self):
        trends = [
            {"title": "Historia de Roma antigua"},
            {"title": "Boca Juniors"},
            {"title": "La ciencia del espacio"},
        ]
        selected = topic_engine._relevant_trends("historia", "Roma, imperio", trends)
        self.assertEqual([item["title"] for item in selected], ["Historia de Roma antigua"])

    def test_google_trends_rss_parser_returns_titles_and_dates(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return b'<rss><channel><item><title>Historia de Roma</title><link>https://example.org</link><pubDate>Sat, 14 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>'

        with patch("app.topic_engine.urllib.request.urlopen", return_value=FakeResponse()):
            items = topic_engine.trending_searches()
        self.assertEqual(items[0]["title"], "Historia de Roma")
        self.assertEqual(items[0]["url"], "https://example.org")
        self.assertIn("2026", items[0]["published_at"])

    def test_topic_normalization_helps_avoid_repeats(self):
        self.assertEqual(topic_engine._normal("Historia: del Rock!"), "historia del rock")

    def test_youtube_autopilot_requires_connection_before_saving_rule(self):
        with patch("app.persistence.durable_storage_available", return_value=True):
            with patch.object(publish, "youtube_account_status", side_effect=publish.PublishError("refresh token inválido")):
                with self.assertRaisesRegex(ValueError, "refresh token inválido"):
                    autopilot._validate_auto_publish({"auto_publish": 1, "destination": "youtube", "channel_id": 1})

    def test_youtube_autopilot_requires_durable_storage_before_saving_rule(self):
        with patch("app.persistence.durable_storage_available", return_value=False):
            with patch.object(publish, "youtube_account_status") as verify:
                with self.assertRaisesRegex(ValueError, "volumen local persistente"):
                    autopilot._validate_auto_publish({"auto_publish": 1, "destination": "youtube", "channel_id": 1})
        verify.assert_not_called()

    def test_publish_does_not_upload_same_video_twice_on_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            video = publish.Path(folder) / "short.mp4"
            video.write_bytes(b"same rendered video")
            fingerprint = publish._video_fingerprint(video)
            project = {"id": 42, "kind": "short"}
            previous = {
                "meta_json": json.dumps({"video_sha256": fingerprint}),
                "url": "https://youtu.be/already-uploaded",
                "external_id": "already-uploaded",
            }
            with patch.object(publish, "ensure_schema"):
                with patch.object(publish.db, "query_one", side_effect=[project, previous]):
                    with patch.object(publish, "video_path", return_value=video):
                        result = publish.publish(42, destination="youtube", privacy="public")
            self.assertEqual(result["external_id"], "already-uploaded")
            self.assertIn("evitó una segunda subida", result["message"])

    def test_youtube_credentials_are_isolated_by_workspace_channel(self):
        with patch.dict(os.environ, {
            "YOUTUBE_CLIENT_ID": "client-id",
            "YOUTUBE_CLIENT_SECRET": "client-secret",
            "YOUTUBE_REFRESH_TOKEN": "legacy-global-token",
        }):
            with patch.object(publish, "ensure_schema"):
                with patch.object(publish.db, "query_one", return_value={"refresh_token": "historias-token"}) as query:
                    credentials = publish.youtube_credentials(channel_id=10)
                self.assertEqual(credentials["refresh_token"], "historias-token")
                query.assert_called_once_with("SELECT refresh_token FROM youtube_accounts WHERE channel_id=?", (10,))
                with patch.object(publish.db, "query_one", return_value={"refresh_token": "frutinovelas-token"}):
                    second = publish.youtube_credentials(channel_id=20)
                self.assertEqual(second["refresh_token"], "frutinovelas-token")
            with patch.object(publish, "ensure_schema"):
                with patch.object(publish.db, "query_one") as query:
                    legacy = publish.youtube_credentials()
                query.assert_not_called()
        self.assertEqual(legacy["refresh_token"], "")
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

    def test_youtube_autopublish_requires_manual_approval_even_without_storage(self):
        with patch.object(publish, "ensure_schema"):
            with patch.object(publish.db, "query_one", return_value={"id": 1, "channel_id": 10}):
                with patch.object(publish.persistence, "durable_storage_available", return_value=False):
                    with self.assertRaisesRegex(publish.PublishError, "aprobación manual"):
                        publish.set_auto_publish(1, True, "youtube")

    def test_youtube_autopublish_is_rejected_until_manual_approval(self):
        with patch.object(publish, "ensure_schema"):
            with patch.object(publish.db, "query_one", return_value={"id": 1, "channel_id": 10}):
                with patch.object(publish, "youtube_account_status") as verify:
                    with patch.object(publish.db, "execute") as execute:
                        with self.assertRaisesRegex(publish.PublishError, "aprobación manual"):
                            publish.set_auto_publish(1, True, "youtube")
        verify.assert_not_called()
        execute.assert_not_called()

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
        with patch.object(topic_engine, "trending_searches", return_value=[]):
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


    def test_frutinovela_is_accepted_by_autopilot_as_vertical_short(self):
        clean = autopilot._clean({
            "template": "frutinovela",
            "duration_target_sec": 90,
            "aspect": "9:16",
        })
        self.assertEqual(clean["template"], "frutinovela")
        self.assertEqual(clean["duration_target_sec"], 90)
        self.assertEqual(clean["aspect"], "9:16")

    def test_frutinovela_autopilot_skips_research_and_keeps_character_names(self):
        project = {"id": 84, "title": "Frutinovela · Episodio 1", "topic": "La familia Frutal", "template": "frutinovela", "kind": "short", "duration_target_sec": 90, "notes": ""}
        with patch.object(autopilot.db, "query", side_effect=[[], []]):
            with patch.object(autopilot.db, "query_one", side_effect=[{"total": 0}, project]):
                with patch.object(autopilot.db, "execute", return_value=84) as execute:
                    with patch.object(autopilot.db, "now", return_value="2026-11-15T00:00:00Z"):
                        with patch.object(autopilot.db, "get_setting", return_value=""):
                            with patch.object(autopilot.db, "log"):
                                with patch.object(topic_engine, "research_topic", side_effect=AssertionError("La ficción no debe investigar temas reales")):
                                    result = autopilot._create_project({
                                    "template": "frutinovela",
                                    "niche": "La familia Frutal",
                                    "content_pillars": "Manzana, Banana y Pera",
                                    "duration_target_sec": 90,
                                })
        statements = [call.args[0] for call in execute.call_args_list]
        self.assertFalse(any("INSERT INTO sources" in sql for sql in statements))
        scene_calls = [call.args[1] for call in execute.call_args_list if "INSERT INTO scenes" in call.args[0]]
        self.assertGreaterEqual(len(scene_calls), 5)
        self.assertIn("Manzana, Banana y Pera", " ".join(str(row[3]) for row in scene_calls))
        self.assertIn("Esto no termina acá", scene_calls[-1][3])
        self.assertNotIn("Te leo en los comentarios", scene_calls[-1][3])
        self.assertEqual(result["evidence_sources"], 0)

    def test_frutinovela_template_builds_vertical_episode_with_cliffhanger(self):
        template = options.template("frutinovela")
        self.assertEqual(template["kind"], "short")
        self.assertEqual(template["aspect"], "9:16")
        self.assertEqual(template["script"], "frutinovela")
        result = script_gen.generate_script(
            {
                "id": 731,
                "title": "La herencia de la familia Frutal",
                "topic": "La herencia de la familia Frutal",
                "kind": "short",
                "template": "frutinovela",
                "duration_target_sec": 90,
            },
            [{"source_url": "https://example.org/fact", "claim": "Dato documental que no debe reemplazar la ficción. " * 40}],
            [],
        )
        narration = " ".join(scene["narration"] for scene in result["scenes"])
        self.assertGreaterEqual(len(result["scenes"]), 5)
        self.assertIn("Continuará", result["scenes"][-1]["title"])
        self.assertIn("Esto no termina acá", result["scenes"][-1]["narration"])
        self.assertNotIn("Dato documental", narration)
        self.assertIn("Ficción original", result["warnings"][0])


    def test_manual_video_creation_integrates_research_and_saves_project_sources(self):
        project = {
            "id": 991, "title": "Historia del cine", "topic": "Historia del cine",
            "kind": "short", "template": "shorts", "notes": "",
        }
        research = {
            "topic": "Historia del cine",
            "title": "Historia del cine",
            "url": "https://es.wikipedia.org/wiki/Historia_del_cine",
            "source_title": "Historia del cine — Wikipedia",
            "notes": [
                {
                    "niche": "Historia del cine", "title": "Historia del cine — Wikipedia",
                    "claim": "Un extracto introductorio documentado. " * 20,
                    "evidence_level": "orientación",
                    "source_url": "https://es.wikipedia.org/wiki/Historia_del_cine",
                    "methodology": "Fuente introductoria; contrastar con estudios.",
                },
                {
                    "niche": "Historia del cine", "title": "Estudio académico",
                    "claim": "Un resumen académico sobre el tema. " * 20,
                    "evidence_level": "resumen académico",
                    "source_url": "https://doi.org/10.0000/cinema",
                    "methodology": "Resumen OpenAlex; consultar publicación.",
                },
            ],
            "academic_sources": [{"title": "Estudio académico"}],
        }
        script = {"scenes": [{
            "idx": 0, "title": "Inicio", "narration": "Narración basada en las fuentes.",
            "visual_query": "Historia del cine", "transition": "fundido",
        }], "warnings": []}
        with patch.object(main_app.db, "query_one", return_value=project):
            with patch.object(main_app.db, "query", return_value=[]):
                with patch.object(topic_engine, "research_specific_topic", return_value=research):
                    with patch.object(script_gen, "generate_script", return_value=script):
                        with patch.object(main_app.db, "execute", return_value=1) as execute:
                            with patch.object(main_app.db, "execute_many"):
                                with patch.object(main_app.db, "scalar", return_value=-1):
                                    with patch.object(main_app.db, "now", return_value="2026-11-16T00:00:00Z"):
                                        with patch.object(main_app.db, "log"):
                                            with patch.object(main_app.db, "get_setting", return_value=""):
                                                with patch.object(main_app, "_touch_project"):
                                                    with patch.object(main_app, "_project_full", return_value=project):
                                                        result = main_app.generate_script(991)

        inserts = [call.args[0] for call in execute.call_args_list]
        self.assertEqual(sum("INSERT INTO research_notes" in sql for sql in inserts), 2)
        self.assertEqual(sum("INSERT INTO sources" in sql for sql in inserts), 2)
        self.assertTrue(any("Estudio académico" in str(call.args[1]) for call in execute.call_args_list))
        self.assertTrue(any("Investigación integrada" in warning for warning in result["warnings"]))

    def test_specific_topic_research_returns_scoped_wikipedia_and_academic_evidence(self):
        def fake_get(params):
            if params.get("list") == "search":
                return {"query": {"search": [{"title": "Historia del cine", "snippet": "Historia"}]}}
            return {"query": {"pages": {"1": {
                "title": "Historia del cine",
                "fullurl": "https://es.wikipedia.org/wiki/Historia_del_cine",
                "extract": "La historia del cine estudia su desarrollo técnico, artístico y social. " * 18,
            }}}}

        academic = [{
            "title": "Early cinema and society",
            "url": "https://doi.org/10.0000/example",
            "abstract": "An academic abstract about early cinema. " * 20,
            "author": "A. Researcher",
            "provider": "OpenAlex",
        }]
        with patch.object(topic_engine, "_get", side_effect=fake_get):
            with patch.object(topic_engine, "_openalex_abstracts", return_value=academic):
                with patch.object(topic_engine, "_external_references", return_value=[]):
                    result = topic_engine.research_specific_topic("historia del cine")

        self.assertEqual(result["topic"], "historia del cine")
        self.assertEqual(len(result["notes"]), 2)
        self.assertEqual(result["notes"][0]["evidence_level"], "orientación")
        self.assertEqual(result["notes"][1]["evidence_level"], "resumen académico")
        self.assertEqual(result["notes"][1]["title"], "Early cinema and society")
        self.assertTrue(all(note["source_url"] for note in result["notes"]))


if __name__ == "__main__":
    unittest.main()