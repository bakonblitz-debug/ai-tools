Work in the Python project at __WORKDIR__ (do not touch anything outside it).

Create `textkit/lru.py` containing a class `LRUCache` with:
- constructor `LRUCache(capacity)` (capacity >= 1),
- `get(key)` returning the stored value or `None`, and marking the key as
  most recently used,
- `put(key, value)` inserting/updating, evicting the least recently used
  entry when over capacity,
- `__len__` returning the current number of entries.

A test file `tests/test_lru.py` already exists and defines the expected
behavior exactly — make the whole suite pass:

    python3 -m unittest discover -s tests

When finished, write a short summary of what you changed to __WORKDIR__/ANSWER.md.
