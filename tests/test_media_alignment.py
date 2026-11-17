import unittest

from app import media


class WhisperWordTimingTests(unittest.TestCase):
    def test_whisper_tokens_are_grouped_into_words(self):
        data = {
            "transcription": [{
                "tokens": [
                    {"text": " Hola", "offsets": {"from": 100, "to": 250}},
                    {"text": " mun", "offsets": {"from": 260, "to": 400}},
                    {"text": "do", "offsets": {"from": 400, "to": 520}},
                    {"text": " !", "offsets": {"from": 520, "to": 600}},
                    {"text": "[_TT_]", "offsets": {"from": 600, "to": 600}},
                ]
            }]
        }
        words = media._whisper_tokens_to_words(data)
        self.assertEqual([word["text"] for word in words], ["Hola", "mundo!"])
        self.assertAlmostEqual(words[0]["start"], 0.1)
        self.assertAlmostEqual(words[1]["end"], 0.6)

    def test_caption_chunks_use_real_word_boundaries_when_available(self):
        words = [
            {"text": "Hola", "start": 0.12, "end": 0.42},
            {"text": "mundo", "start": 0.48, "end": 0.91},
            {"text": "de", "start": 1.1, "end": 1.24},
            {"text": "prueba", "start": 1.3, "end": 1.8},
        ]
        cues = media.caption_chunks("Hola mundo de prueba", 2.0, 2, 40, 2, word_timings=words)
        self.assertEqual(len(cues), 2)
        self.assertAlmostEqual(cues[0]["start"], 0.12)
        self.assertAlmostEqual(cues[0]["end"], 0.91)
        self.assertAlmostEqual(cues[1]["start"], 1.1)
        self.assertAlmostEqual(cues[1]["end"], 1.8)

    def test_missing_whisper_configuration_falls_back_cleanly(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"WHISPER_CPP_BIN": "", "WHISPER_MODEL_PATH": ""}), \
             patch.object(media.shutil, "which", return_value=None):
            self.assertIsNone(media.whisper_word_timings("/missing/audio.wav", "es"))


if __name__ == "__main__":
    unittest.main()
