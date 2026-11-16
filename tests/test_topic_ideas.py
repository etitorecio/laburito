import unittest
from unittest.mock import patch

from app import topic_engine


class TopicIdeaFinderTests(unittest.TestCase):
    def test_suggests_unique_documented_wikipedia_topics(self):
        with patch.object(topic_engine, "trending_searches", return_value=[]), \
             patch.object(topic_engine, "_get", return_value={
                 "query": {"search": [
                     {"title": "Historia del cine", "snippet": "Una <b>historia</b> breve."},
                     {"title": "Historia del cine", "snippet": "Duplicado."},
                     {"title": "Cine mudo", "snippet": "El cine <i>mudo</i>."},
                 ]}
             }):
            ideas = topic_engine.suggest_topics("cine", limit=2)
        self.assertEqual([idea["title"] for idea in ideas], ["Historia del cine", "Cine mudo"])
        self.assertEqual(ideas[0]["summary"], "Una historia breve.")
        self.assertTrue(ideas[0]["url"].startswith("https://es.wikipedia.org/wiki/"))

    def test_idea_search_still_works_when_trends_are_unavailable(self):
        with patch.object(topic_engine, "trending_searches", side_effect=RuntimeError("offline")), \
             patch.object(topic_engine, "_get", return_value={
                 "query": {"search": [
                     {"title": "Historia de los videojuegos", "snippet": "Los videojuegos <b>cambiaron</b> la cultura."}
                 ]}
             }):
            ideas = topic_engine.suggest_topics("videojuegos", limit=1)
        self.assertEqual(ideas[0]["title"], "Historia de los videojuegos")

    def test_requires_a_niche(self):
        with self.assertRaisesRegex(ValueError, "nicho"):
            topic_engine.suggest_topics("  ")


if __name__ == "__main__":
    unittest.main()
