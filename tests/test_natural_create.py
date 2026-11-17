import unittest
from unittest.mock import patch

from app import main


class NaturalCreateEndpointTests(unittest.TestCase):
    def test_natural_order_creates_script_and_queues_render(self):
        with patch.object(main.db, "query_one", return_value={"id": 3}):
            with patch.object(main, "create_project", return_value={"id": 42}) as create:
                with patch.object(main, "generate_script", return_value={"warnings": []}) as script:
                    with patch.object(main.worker, "enqueue", return_value=91) as enqueue:
                        result = main.create_from_prompt(
                            main.NaturalCreateIn(prompt="haceme un short sobre la historia de Nirvana")
                        )
        self.assertEqual(result["project_id"], 42)
        self.assertEqual(result["job_id"], 91)
        self.assertEqual(result["status"], "en_cola")
        self.assertEqual(create.call_args.args[0].template, "shorts")
        self.assertIsNone(create.call_args.args[0].duration_target_sec)
        script.assert_called_once_with(42, replace=True)
        enqueue.assert_called_once_with(42, "render_project", {})

    def test_natural_horror_uses_safe_duration_headroom(self):
        with patch.object(main.db, "query_one", return_value={"id": 3}):
            with patch.object(main, "create_project", return_value={"id": 44}) as create:
                with patch.object(main, "generate_script", return_value={"warnings": []}):
                    with patch.object(main.worker, "enqueue", return_value=93):
                        main.create_from_prompt(main.NaturalCreateIn(prompt="haceme una historia de terror"))
        self.assertEqual(create.call_args.args[0].template, "reddit_story")
        self.assertEqual(create.call_args.args[0].duration_target_sec, 100)

    def test_natural_order_selects_the_frutinovela_factory(self):
        with patch.object(main.db, "query_one", return_value={"id": 8}):
            with patch.object(main, "create_project", return_value={"id": 43}) as create:
                with patch.object(main, "generate_script", return_value={"warnings": []}):
                    with patch.object(main.worker, "enqueue", return_value=92):
                        result = main.create_from_prompt(
                            main.NaturalCreateIn(prompt="haceme una frutinovela")
                        )
        self.assertEqual(result["interpretation"]["template"], "frutinovela")
        self.assertEqual(create.call_args.args[0].template, "frutinovela")
        self.assertEqual(create.call_args.args[0].channel_id, 8)
        self.assertIn('"characters": "Manzana, Banana, Pera y Naranja"', create.call_args.args[0].notes)


if __name__ == "__main__":
    unittest.main()
