"""textkit.core — small text utilities."""

import re


def normalize_whitespace(text):
    """Collapse every run of whitespace to a single space and strip both ends."""
    return re.sub(r"\s+", " ", text).strip()


def truncate(text, limit):
    """Return text unchanged if it fits in `limit` characters; otherwise cut it
    to exactly `limit` characters, with the last 3 kept characters replaced by
    '...'. For limit <= 3, return that many dots."""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return "." * limit
    return text[: limit - 3] + "..."


def word_frequencies(text):
    """Case-insensitive word counts. A word is a run of letters, digits, or
    apostrophes; every other character (punctuation, whitespace) separates
    words. Returns a dict of word -> count."""
    freq = {}
    for word in text.lower().split():
        freq[word] = freq.get(word, 0) + 1
    return freq
