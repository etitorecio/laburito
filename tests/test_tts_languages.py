import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import tts


class TtsLanguageTests(unittest.TestCase):
    def test_voice_catalog_is_limited_to_spanish_and_english(self):
        languages = {voice["language"] for voice in tts.VOICES.values()}
        self.assertEqual(languages, {"es", "en"})
        self.assertEqual(tts.VOICES["en"]["engine_voice"], "en")
        self.assertEqual(tts.VOICES["en-us"]["engine_voice"], "en-us")
        self.assertEqual(tts.VOICES["en-gb"]["engine_voice"], "en-gb")

    def test_english_voice_uses_espeak_english_variant(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "voice.wav"

            def fake_run(command, **kwargs):
                output.write_bytes(b"RIFF")
                class Result:
                    returncode = 0
                    stderr = b""
                return Result()

            with patch.object(tts, "piper_path", return_value=None), \
                 patch.object(tts, "engine_path", return_value="/usr/bin/espeak-ng"), \
                 patch.object(tts.db, "get_setting", return_value=""), \
                 patch.object(tts.subprocess, "run", side_effect=fake_run) as run:
                result = tts.synthesize("Hello world", output, voice="en-us")
            self.assertEqual(result["language"], "en")
            self.assertIn("en-us", run.call_args.args[0])

    def test_unknown_voice_falls_back_to_spanish(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "voice.wav"

            def fake_run(command, **kwargs):
                output.write_bytes(b"RIFF")
                class Result:
                    returncode = 0
                    stderr = b""
                return Result()

            with patch.object(tts, "piper_path", return_value=None), \
                 patch.object(tts, "engine_path", return_value="/usr/bin/espeak-ng"), \
                 patch.object(tts.db, "get_setting", return_value=""), \
                 patch.object(tts.subprocess, "run", side_effect=fake_run) as run:
                result = tts.synthesize("Hola mundo", output, voice="unsupported")
            self.assertEqual(result["language"], "es")
            self.assertIn('"es"', run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
