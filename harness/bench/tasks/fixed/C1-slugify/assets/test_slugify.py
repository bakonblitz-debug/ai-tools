import unittest

from textkit import slugify


class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_collapses_separator_runs(self):
        self.assertEqual(slugify("A  B__C"), "a-b-c")

    def test_all_separators_is_empty(self):
        self.assertEqual(slugify("--- !!"), "")

    def test_already_clean(self):
        self.assertEqual(slugify("already-good"), "already-good")


if __name__ == "__main__":
    unittest.main()
