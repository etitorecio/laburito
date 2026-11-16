import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import render


class SceneSoundEffectMixTests(unittest.TestCase):
    def test_mixes_effect_with_voice_and_caches_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            voice = root / "voice.wav"
            effect = root / "effect.wav"
            output = root / "cache" / "mixed.wav"
            voice.write_bytes(b"voice")
            effect.write_bytes(b"effect")
            def fake_ff(args, timeout=900):
                Path(args[-1]).write_bytes(b"mixed-audio" * 300)
            with patch("app.render._ff", side_effect=fake_ff) as ff:
                result = render._mix_scene_audio(voice, effect, 12.0, 0.6, 1.5, output)
                self.assertEqual(result, output)
                self.assertEqual(ff.call_count, 1)
                command = ff.call_args.args[0]
                filter_graph = command[command.index("-filter_complex") + 1]
                self.assertIn("amix=inputs=2:duration=first", filter_graph)
                self.assertIn("adelay=1500|1500", filter_graph)
                render._mix_scene_audio(voice, effect, 12.0, 0.6, 1.5, output)
                self.assertEqual(ff.call_count, 1)

    def test_missing_effect_keeps_original_voice(self):
        with tempfile.TemporaryDirectory() as temp:
            voice = Path(temp) / "voice.wav"
            voice.write_bytes(b"voice")
            result = render._mix_scene_audio(
                voice, Path(temp) / "missing.wav", 8.0, 0.8, 0.0, Path(temp) / "mixed.wav"
            )
            self.assertEqual(result, voice)


if __name__ == "__main__":
    unittest.main()
