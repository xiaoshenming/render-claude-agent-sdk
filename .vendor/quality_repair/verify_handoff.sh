#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider \
  libs/quality_repair/tests \
  tools/quality_repair_m0/tests \
  -q

python3 -m compileall -q \
  libs/quality_repair \
  quality_repair \
  tools/quality_repair_checkers \
  tools/quality_repair_m0

PYTHONDONTWRITEBYTECODE=1 python3 -m quality_repair --help >/dev/null

if find . -type f \( \
  -name '.env' -o \
  -name '.env.*' -o \
  -name '*.pem' -o \
  -name '*.key' -o \
  -name '*token*' \
\) -print -quit | grep -q .; then
  printf 'sensitive-looking file name found\n' >&2
  exit 1
fi

oversized="$({
  find libs/quality_repair quality_repair tools/quality_repair_checkers tools/quality_repair_m0 \
    -type f \( -name '*.py' -o -name '*.md' \) -print0 \
    | xargs -0 wc -l \
    | awk '$1 > 300 && $2 != "total" {print $1, $2}' \
    | sort -nr
} || true)"

if [[ -n "$oversized" ]]; then
  printf 'warning: source files over 300 lines:\n%s\n' "$oversized" >&2
  if [[ "${STRICT_SOURCE_SIZE:-0}" == "1" ]]; then
    exit 1
  fi
fi

printf 'quality_repair handoff verification passed\n'
