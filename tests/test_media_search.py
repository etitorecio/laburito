import unittest
from unittest.mock import patch

from app import media


class MediaSearchTests(unittest.TestCase):
    def test_archive_results_have_a_downloadable_cover_image(self):
        payload = {
            "response": {
                "docs": [
                    {
                        "identifier": "historic-film",
                        "title": "Historic Film",
                        "year": 1940,
                        "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/",
                    }
                ]
            }
        }
        with patch.object(media, "_get_json", return_value=payload):
            results = media.search_archive("historic film", limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["url"],
            "https://archive.org/services/img/historic-film",
        )
        self.assertEqual(results[0]["url"], results[0]["thumb"])
        self.assertTrue(results[0]["page"].startswith("https://archive.org/details/"))


if __name__ == "__main__":
    unittest.main()
