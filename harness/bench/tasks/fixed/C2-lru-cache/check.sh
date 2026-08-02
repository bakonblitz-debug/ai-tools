#!/usr/bin/env bash
cd "$1" || exit 1
python3 -m unittest discover -s tests 2>&1
