#!/bin/sh
# Depoloma launcher for macOS and Linux:  ./depoloma.sh   (or  ./depoloma.sh --report)
cd "$(dirname "$0")" || exit 1
for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
        exec "$py" -m depoloma "$@"
    fi
done
echo "Depoloma needs Python 3.8+ (https://www.python.org/downloads/)." >&2
exit 1
