import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db
from app.main import duplicate_project


class ProjectDuplicateTests(unittest.TestCase):
    def test_duplicate_preserves_scenes_sources_and_assets_as_draft(self):
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
                db.init_db()
                stamp = db.now()
                project_id = db.execute(
                    "INSERT INTO projects(title,topic,kind,aspect,status,duration_target_sec,voice,speed,pitch,notes,quality_json,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("Video original", "Tema", "documentary", "16:9", "renderizado", 600, "es", 150, 45, "", '{"duration_sec":42}', stamp, stamp),
                )
                scene_id = db.execute(
                    "INSERT INTO scenes(project_id,idx,title,narration,visual_query,visual_path,transition,status,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (project_id, 0, "Escena uno", "Narración de prueba", "Tema", "/tmp/visual.jpg", "fundido", "renderizada", stamp, stamp),
                )
                db.execute(
                    "INSERT INTO sources(project_id,scene_id,title,url,author,license,accessed_at,attribution,kind,notes,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (project_id, scene_id, "Fuente", "https://example.org", "Autor", "CC0", stamp, "Autor CC0", "investigacion", "Nota", stamp),
                )
                db.execute(
                    "INSERT INTO assets(project_id,scene_id,kind,path,label,license,author,url,bytes,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (project_id, scene_id, "imagen", "/tmp/visual.jpg", "Visual", "CC0", "Autor", "", 123, stamp),
                )
                duplicate = duplicate_project(project_id)
                self.assertNotEqual(duplicate["id"], project_id)
                self.assertEqual(duplicate["title"], "Video original (copia)")
                self.assertEqual(duplicate["status"], "borrador")
                self.assertEqual(duplicate["quality"], {})
                self.assertEqual(len(duplicate["scenes"]), 1)
                self.assertEqual(duplicate["scenes"][0]["narration"], "Narración de prueba")
                self.assertEqual(duplicate["scenes"][0]["audio_path"], "")
                self.assertEqual(len(duplicate["sources"]), 1)
                copied_assets = db.query("SELECT * FROM assets WHERE project_id=?", (duplicate["id"],))
                self.assertEqual(len(copied_assets), 1)
                self.assertEqual(copied_assets[0]["scene_id"], duplicate["scenes"][0]["id"])


if __name__ == "__main__":
    unittest.main()
