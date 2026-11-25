#!/usr/bin/env bash
set -euo pipefail
BUNDLE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if (( $# > 1 )); then
    echo 'Usage: install.sh [optional-project-directory]' >&2
    exit 2
fi
if (( $# == 1 )); then
    exec /usr/bin/python3 "$BUNDLE/packager.py" install --project "$1"
else
    exec /usr/bin/python3 "$BUNDLE/packager.py" install
fi
