#!/usr/bin/env bash
# Swap in the buggy word_frequencies (naive whitespace split — violates docstring).
cp "$2/assets/core_buggy.py" "$1/textkit/core.py"
