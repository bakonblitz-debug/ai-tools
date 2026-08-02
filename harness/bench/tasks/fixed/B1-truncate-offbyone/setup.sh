#!/usr/bin/env bash
# Plant an off-by-one in truncate: keeps limit-2 chars + "..." -> length limit+1.
sed -i 's/text\[: limit - 3\]/text[: limit - 2]/' "$1/textkit/core.py"
grep -q "limit - 2" "$1/textkit/core.py" || { echo "setup failed to plant bug"; exit 1; }
