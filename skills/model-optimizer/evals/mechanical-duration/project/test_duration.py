import unittest
from duration import parse_duration


class DurationTests(unittest.TestCase):
    def test_combined_units(self):
        self.assertEqual(parse_duration("1h 30m 5s"), 5405)

    def test_single_unit(self):
        self.assertEqual(parse_duration("45m"), 2700)

    def test_whitespace_and_case(self):
        self.assertEqual(parse_duration(" 2H   3m "), 7380)

    def test_rejects_unknown_text(self):
        with self.assertRaises(ValueError):
            parse_duration("tomorrow")

    def test_rejects_non_string(self):
        with self.assertRaises(TypeError):
            parse_duration(None)
