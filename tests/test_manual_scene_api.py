import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.main import SceneIn, create_scene


class ManualSceneApiTests(unittest.TestCase):
    @patch("app.main._touch_project")
    @patch("app.main.db.execute", return_value=22)
    @patch("app.main.db.scalar", return_value=3)
    @patch("app.main.db.query_one", side_effect=[{"id": 7}, {"id": 22, "title": "Escena manual"}])
    def test_creates_scene_at_end_of_project(self, query_one, scalar, execute, touch):
        result = create_scene(
            7,
            SceneIn(
                title="Escena manual",
                narration="Narración escrita por el usuario.",
                visual_query="pedal de guitarra vintage",
                transition="fundido",
            ),
        )
        self.assertEqual(result["id"], 22)
        self.assertEqual(result["title"], "Escena manual")
        self.assertEqual(scalar.call_args.args[0].count("MAX(idx)"), 1)
        self.assertEqual(execute.call_args.args[1][1], 3)
        self.assertEqual(execute.call_args.args[1][2], "Escena manual")
        touch.assert_called_once_with(7)
        self.assertEqual(query_one.call_count, 2)

    @patch("app.main.db.query_one", return_value=None)
    def test_rejects_missing_project(self, query_one):
        with self.assertRaises(HTTPException) as error:
            create_scene(999, SceneIn())
        self.assertEqual(error.exception.status_code, 404)
        query_one.assert_called_once()


if __name__ == "__main__":
    unittest.main()
