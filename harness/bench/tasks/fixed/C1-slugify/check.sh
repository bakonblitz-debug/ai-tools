#!/usr/bin/env bash
# $1 = workdir
cd "$1" || exit 1
python3 -m unittest discover -s tests 2>&1
