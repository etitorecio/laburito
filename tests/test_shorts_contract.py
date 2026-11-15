import unittest
from unittest.mock import patch

from app import autopilot, options, script_gen


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

    def test_factory_channels_have_one_matching_template_each(self):
        self.assertEqual(options.factory_template_for_channel_name("Historias"), "reddit_story")
        self.assertEqual(options.factory_template_for_channel_name("Frutinovelas"), "frutinovela")
        self.assertIsNone(options.factory_template_for_channel_name("Otro canal"))

    def test_autopilot_rejects_crossed_factory_channel(self):
        with patch.object(autopilot.db, "query_one", return_value={"name": "Historias"}):
            with self.assertRaisesRegex(ValueError, "solo admite su fábrica"):
                autopilot._validate_factory_channel({"channel_id": 1, "template": "frutinovela"})

    def test_autopilot_accepts_matching_factory_channel(self):
        with patch.object(autopilot.db, "query_one", return_value={"name": "Frutinovelas"}):
            autopilot._validate_factory_channel({"channel_id": 2, "template": "frutinovela"})

    def test_vertical_shorts_duration_is_clamped_to_three_minutes(self):
        self.assertEqual(options.clamp_vertical_short_duration("reddit_story", 999), 180)
        self.assertEqual(options.clamp_vertical_short_duration("frutinovela", 5), 15)
        self.assertEqual(options.clamp_vertical_short_duration("longform", 999), 999)

    def test_fiction_word_targets_scale_with_short_duration(self):
        self.assertEqual(script_gen.fiction_word_range(180), (342, 432))
        self.assertEqual(script_gen.fiction_word_range(90), (171, 216))
        self.assertEqual(script_gen.fiction_word_range(45), (86, 108))

    def test_gameplay_clip_minimums_match_the_product_contract(self):
        self.assertEqual(options.VIDEO_CLIP_MINIMUMS, {
            "stock_footage": 5,
            "minecraft": 1,
            "subway": 1,
        })


if __name__ == "__main__":
    unittest.main()
