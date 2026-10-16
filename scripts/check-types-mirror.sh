#!/usr/bin/env bash
set -euo pipefail

if ! cmp -s types/src/index.ts connectors/types/index.ts; then
  echo "Error: types/src/index.ts and connectors/types/index.ts differ!" >&2
  diff -u types/src/index.ts connectors/types/index.ts >&2 || true
  exit 1
fi

echo "OK: types mirror is byte-identical."
