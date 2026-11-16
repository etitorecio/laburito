import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app import render


class ProjectExportTests(unittest.TestCase):
    def test_export_contains_original_assets_and_editable_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workdir = root / "work"
            workdir.mkdir()
            (workdir / "final_short.mp4").write_bytes(b"final-video")
            (workdir / "short.srt").write_text("1\\n00:00:00,000 --> 00:00:01,000\\nHola\\n", encoding="utf-8")
            source_media = root / "uploaded-image.png"
            source_media.write_bytes(b"original-image")
            project = {"id": 7, "title": "Proyecto portable", "kind": "short", "quality_json": "{}"}
            scene = {"id": 3, "idx": 0, "title": "Escena"}
            overlay = {"id": 9, "kind": "video", "start_sec": 2.0, "duration_sec": 5.0}
            asset = {"id": 11, "kind": "imagen_escena", "path": str(source_media), "label": "Imagen original"}

            def query(sql, params=()):
                if "FROM scenes" in sql:
                    return [scene]
                if "FROM sources" in sql:
                    return []
                if "FROM assets" in sql:
                    return [asset]
                if "FROM timeline_overlays" in sql:
                    return [overlay]
                raise AssertionError(sql)

            with patch.object(render.db, "query_one", return_value=project), \\
                 patch.object(render.db, "query", side_effect=query), \\
                 patch.object(render.db, "EXPORT_DIR", root / "exports"), \\
                 patch.object(render, "_workdir", return_value=workdir), \\
                 patch.object(render.db, "execute"), \\
                 patch.object(render.db, "now", return_value="2026-11-16T00:00:00"):
                archive = render.export_project(7)

            with zipfile.ZipFile(archive) as bundle:
                names = bundle.namelist()
                self.assertIn("short/video_final.mp4", names)
                self.assertIn("recursos/imagen_escena/11_Imagen_original", names)
                self.assertIn("timeline/capas.json", names)
                timeline = json.loads(bundle.read("timeline/capas.json"))
                self.assertEqual(timeline[0]["id"], 9)
                metadata = json.loads(bundle.read("metadatos/metadatos.json"))
                self.assertEqual(metadata["capas_de_tiempo"][0]["kind"], "video")
                self.assertNotIn(str(root), bundle.read("metadatos/metadatos.json").decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
