import unittest

from app import options


class ShortsContractTests(unittest.TestCase):
    def test_story_and_fruit_factories_are_always_vertical(self):
        for template_id in ("shorts", "reddit_story", "frutinovela"):
            with self.subTest(template=template_id):
                resolved = options.resolve_defaults({
                    "template": template_id,
                    "aspect": "16:9",
                })
                self.assertEqual(resolved["aspect"], "9:16")
                self.assertEqual(resolved["kind"], "short")

    def test_factory_templates_never_exceed_three_minutes(self):
        for template_id in ("reddit_story", "frutinovela"):
            with self.subTest(template=template_id):
                template = options.template(template_id)
                self.assertEqual(template["aspect"], "9:16")
                self.assertLessEqual(max(template["durations"]), 180)
                self.assertLessEqual(template["default_duration"], 180)

    def test_gameplay_clip_minimums_match_the_product_contract(self):
        self.assertEqual(options.VIDEO_CLIP_MINIMUMS, {
            "stock_footage": 5,
            "minecraft": 1,
            "subway": 1,
        })


if __name__ == "__main__":
    unittest.main()
