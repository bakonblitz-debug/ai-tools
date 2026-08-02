import unittest

from textkit import normalize_whitespace, truncate, word_frequencies


class TruncateTests(unittest.TestCase):
    def test_short_text_unchanged(self):
        self.assertEqual(truncate("hi", 10), "hi")

    def test_exact_limit_unchanged(self):
        self.assertEqual(truncate("abcde", 5), "abcde")

    def test_long_text_cut_to_limit(self):
        self.assertEqual(len(truncate("a" * 50, 10)), 10)

    def test_ellipsis_present(self):
        self.assertTrue(truncate("a" * 50, 10).endswith("..."))


class NormalizeWhitespaceTests(unittest.TestCase):
    def test_collapses_runs(self):
        self.assertEqual(normalize_whitespace("a  b\t\nc"), "a b c")

    def test_strips_ends(self):
        self.assertEqual(normalize_whitespace("  x  "), "x")


class WordFrequenciesTests(unittest.TestCase):
    def test_counts_repeats(self):
        self.assertEqual(word_frequencies("the cat the")["the"], 2)

    def test_case_insensitive(self):
        self.assertEqual(word_frequencies("Dog dog DOG")["dog"], 3)


if __name__ == "__main__":
    unittest.main()
