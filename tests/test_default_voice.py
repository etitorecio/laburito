import unittest
from unittest.mock import patch

from app import main


class DefaultVoiceTests(unittest.TestCase):
    def test_new_project_uses_english_default_voice_when_voice_is_not_explicit(self):
        payload = main.ProjectIn(title="An English video", topic="A topic")
        with patch.object(main.db, "query_one", return_value=None), \
             patch.object(main.db, "get_setting", return_value="en-us"), \
             patch.object(main.db, "execute", return_value=77) as execute, \
             patch.object(main, "_project_full", return_value={"id": 77}):
            main.create_project(payload)
        project_call = next(call for call in execute.call_args_list if "INSERT INTO projects" in call.args[0])
        values = project_call.args[1]
        self.assertEqual(values[7], "en-us")

    def test_explicit_spanish_voice_overrides_english_default(self):
        payload = main.ProjectIn(title="A Spanish video", topic="Un tema", voice="es")
        with patch.object(main.db, "query_one", return_value=None), \
             patch.object(main.db, "get_setting", return_value="en-us"), \
             patch.object(main.db, "execute", return_value=78) as execute, \
             patch.object(main, "_project_full", return_value={"id": 78}):
            main.create_project(payload)
        project_call = next(call for call in execute.call_args_list if "INSERT INTO projects" in call.args[0])
        values = project_call.args[1]
        self.assertEqual(values[7], "es")


if __name__ == "__main__":
    unittest.main()
