import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import db
from app.main import SceneSplitIn, split_scene


class SceneSplitTests(unittest.TestCase):
    def make_database(self, root: Path):
        db.init_db()
        stamp = db.now()
        project_id = db.execute(
            "INSERT INTO projects(title,topic,kind,aspect,status,duration_target_sec,voice,speed,pitch,notes,quality_json,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("Proyecto", "Tema", "documentary", "16:9", "borrador", 600, "es", 150, 45, "", "{}", stamp, stamp),
        )
        narration = (
            "La primera parte presenta el contexto y explica por qué comenzó este proceso. "
            "La segunda parte desarrolla las consecuencias y muestra cómo cambió la situación."
        )
        scene_id = db.execute(
            "INSERT INTO scenes(project_id,idx,title,narration,visual_query,visual_path,transition,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (project_id, 0, "Escena original", narration, "Tema", "/tmp/visual.jpg", "fundido", "renderizada", stamp, stamp),
        )
        return project_id, scene_id, narration

    def test_split_creates_two_ordered_editable_scenes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.multiple(
                "app.db",
                DB_PATH=root / "app.sqlite3",
                DATA_DIR=root,
                MEDIA_DIR=root / "media",
                RENDER_DIR=root / "renders",
                EXPORT_DIR=root / "exports",
                MUSIC_DIR=root / "music",
                TMP_DIR=root / "tmp",
            ):
                project_id, scene_id, narration = self.make_database(root)
                result = split_scene(scene_id, SceneSplitIn(narration=narration, split_at=82))
                scenes = db.query("SELECT * FROM scenes WHERE project_id=? ORDER BY idx", (project_id,))
                self.assertEqual(len(scenes), 2)
                self.assertEqual(scenes[0]["id"], scene_id)
                self.assertEqual(scenes[1]["id"], result["second"]["id"])
                self.assertEqual(scenes[0]["idx"], 0)
                self.assertEqual(scenes[1]["idx"], 1)
                self.assertTrue(scenes[0]["narration"])
                self.assertTrue(scenes[1]["narration"])
                self.assertEqual(scenes[0]["audio_path"], "")
                self.assertEqual(scenes[1]["visual_path"], "/tmp/visual.jpg")

    def test_split_rejects_a_cursor_too_close_to_the_edge(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.multiple(
                "app.db",
                DB_PATH=root / "app.sqlite3",
                DATA_DIR=root,
                MEDIA_DIR=root / "media",
                RENDER_DIR=root / "renders",
                EXPORT_DIR=root / "exports",
                MUSIC_DIR=root / "music",
                TMP_DIR=root / "tmp",
            ):
                _, scene_id, narration = self.make_database(root)
                with self.assertRaises(HTTPException) as error:
                    split_scene(scene_id, SceneSplitIn(narration=narration, split_at=5))
                self.assertEqual(error.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
