import unittest

from app.render import _music_ducking_filter


class MusicDuckingTests(unittest.TestCase):
    def test_music_is_sidechain_compressed_by_narration(self):
        filter_graph = _music_ducking_filter(0.2)
        self.assertIn("[bg][0:a]sidechaincompress", filter_graph)
        self.assertIn("threshold=0.03:ratio=8:attack=20:release=300", filter_graph)
        self.assertIn("[0:a][ducked]amix", filter_graph)
        self.assertIn("volume=0.200", filter_graph)

    def test_music_volume_is_clamped(self):
        self.assertIn("volume=1.000", _music_ducking_filter(3))
        self.assertIn("volume=0.000", _music_ducking_filter(-1))


if __name__ == "__main__":
    unittest.main()
