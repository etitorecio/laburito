import unittest
from unittest.mock import patch

from app import main


class NaturalCreateEndpointTests(unittest.TestCase):
    def test_natural_order_creates_project_and_queues_complete_production(self):
        with patch.object(main.db, "query", return_value=[]):
            with patch.object(main, "create_project", return_value={"id": 42}) as create:
                with patch.object(main.worker, "enqueue", return_value=91) as enqueue:
                    result = main.create_from_prompt(
                        main.NaturalCreateIn(prompt="haceme un short sobre la historia de Nirvana")
                    )
        self.assertEqual(result["project_id"], 42)
        self.assertEqual(result["job_id"], 91)
        self.assertEqual(result["status"], "en_cola")
        self.assertEqual(create.call_args.args[0].template, "shorts")
        self.assertIsNone(create.call_args.args[0].duration_target_sec)
        enqueue.assert_called_once_with(42, "create_from_prompt", {})
        self.assertEqual(result["warnings"], [])

    def test_natural_prompt_can_request_english_voice(self):
        with patch.object(main.db, "query", return_value=[]):
            with patch.object(main, "create_project", return_value={"id": 45}) as create:
                with patch.object(main.worker, "enqueue", return_value=94):
                    main.create_from_prompt(
                        main.NaturalCreateIn(prompt="haceme un short en inglés sobre la historia de Nirvana")
                    )
        self.assertEqual(create.call_args.args[0].voice, "en-us")

    def test_natural_prompt_can_override_english_default_with_spanish(self):
        with patch.object(main.db, "query", return_value=[]):
            with patch.object(main, "create_project", return_value={"id": 46}) as create:
                with patch.object(main.worker, "enqueue", return_value=95):
                    main.create_from_prompt(
                        main.NaturalCreateIn(prompt="haceme un short en español sobre la historia de Nirvana")
                    )
        self.assertEqual(create.call_args.args[0].voice, "es")

    def test_natural_story_reserves_duration_margin_for_real_voice(self):
        with patch.object(main.db, "query", return_value=[]):
            with patch.object(main, "create_project", return_value={"id": 47}) as create:
                with patch.object(main.worker, "enqueue", return_value=96):
                    main.create_from_prompt(main.NaturalCreateIn(prompt="haceme una historia de terror"))
        self.assertEqual(create.call_args.args[0].template, "reddit_story")
        self.assertEqual(create.call_args.args[0].duration_target_sec, 100)
        self.assertEqual(create.call_args.args[0].channel_id, None)

    def test_natural_frutinovela_keeps_its_factory_channel(self):
        with patch.object(main.db, "query_one", return_value={"id": 8}):
            with patch.object(main, "create_project", return_value={"id": 48}) as create:
                with patch.object(main.worker, "enqueue", return_value=97):
                    main.create_from_prompt(main.NaturalCreateIn(prompt="haceme una frutinovela"))
        self.assertEqual(create.call_args.args[0].template, "frutinovela")
        self.assertEqual(create.call_args.args[0].channel_id, 8)

    def test_automatic_channel_selection_respects_the_requested_format(self):
        channels = [
            {"id": 1, "name": "Historias", "topic": "Relatos de terror", "formats": "short"},
            {"id": 2, "name": "Documentales de música", "topic": "Historia de música y artistas", "formats": "documental,short"},
            {"id": 3, "name": "Frutinovelas", "topic": "Ficción episódica", "formats": "short"},
        ]
        with patch.object(main.db, "query", return_value=channels):
            with patch.object(main, "create_project", return_value={"id": 49}) as create:
                with patch.object(main.worker, "enqueue", return_value=98):
                    main.create_from_prompt(
                        main.NaturalCreateIn(prompt="haceme un documental sobre la historia de Nirvana")
                    )
        self.assertEqual(create.call_args.args[0].template, "longform")
        self.assertEqual(create.call_args.args[0].channel_id, 2)


if __name__ == "__main__":
    unittest.main()
