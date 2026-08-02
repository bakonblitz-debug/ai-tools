import unittest

from textkit.lru import LRUCache


class LRUCacheTests(unittest.TestCase):
    def test_put_get(self):
        c = LRUCache(2)
        c.put("a", 1)
        self.assertEqual(c.get("a"), 1)

    def test_missing_returns_none(self):
        c = LRUCache(2)
        self.assertIsNone(c.get("nope"))

    def test_evicts_least_recently_used(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3)  # evicts "a"
        self.assertIsNone(c.get("a"))
        self.assertEqual(c.get("b"), 2)

    def test_get_refreshes_recency(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.get("a")      # "a" is now most recent
        c.put("c", 3)   # evicts "b", not "a"
        self.assertEqual(c.get("a"), 1)
        self.assertIsNone(c.get("b"))

    def test_update_existing_key(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("a", 9)
        self.assertEqual(c.get("a"), 9)
        self.assertEqual(len(c), 1)


if __name__ == "__main__":
    unittest.main()
