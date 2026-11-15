import unittest
from unittest.mock import patch

from app import main


class FactoryChannelTests(unittest.TestCase):
    def test_creates_both_missing_factory_channels(self):
        with patch.object(main.db, "query_one", side_effect=[None, None]) as query:
            with patch.object(main.db, "execute") as execute:
                with patch.object(main.db, "now", return_value="2026-11-15T12:00:00Z"):
                    with patch.object(main.db, "log") as log:
                        main._ensure_factory_channels()
        self.assertEqual(query.call_count, 2)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(log.call_count, 2)
        self.assertEqual(execute.call_args_list[0].args[1][0], "Historias")
        self.assertEqual(execute.call_args_list[1].args[1][0], "Frutinovelas")

    def test_does_not_duplicate_existing_factory_channels(self):
        with patch.object(main.db, "query_one", side_effect=[{"id": 1}, {"id": 2}]):
            with patch.object(main.db, "execute") as execute:
                with patch.object(main.db, "log") as log:
                    main._ensure_factory_channels()
        execute.assert_not_called()
        log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
