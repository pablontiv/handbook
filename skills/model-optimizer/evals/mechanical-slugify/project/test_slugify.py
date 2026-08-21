import unittest
from slugify import slugify


class SlugifyTests(unittest.TestCase):
    def test_words_and_whitespace(self):
        self.assertEqual(slugify("  Hello,   World!  "), "hello-world")

    def test_collapses_separators(self):
        self.assertEqual(slugify("one___two---three"), "one-two-three")

    def test_ascii_normalization(self):
        self.assertEqual(slugify("Crème Brûlée"), "creme-brulee")

    def test_empty_after_normalization(self):
        self.assertEqual(slugify("!!!"), "")

    def test_rejects_non_string(self):
        with self.assertRaises(TypeError):
            slugify(123)


if __name__ == "__main__":
    unittest.main()
