#!/usr/bin/env bash
set -euo pipefail

PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PACKAGE_ROOT"

sha256sum -c MANIFEST.sha256

case_count="$(find cases -mindepth 1 -maxdepth 1 -type d | wc -l)"
code_count="$(find cases -path '*/source/main.py' -type f | wc -l)"
record_count="$(find cases -path '*/source/record.json' -type f | wc -l)"
background_count="$(find cases -path '*/assets/reference_bg_02.png' -type f | wc -l)"
logo_count="$(find cases -path '*/assets/logo_text_trim.png' -type f | wc -l)"

[[ "$case_count" -eq 17 ]]
[[ "$code_count" -eq 17 ]]
[[ "$record_count" -eq 17 ]]
[[ "$background_count" -eq 17 ]]
[[ "$logo_count" -eq 17 ]]

python -m py_compile scripts/run_read_edit_batch.py scripts/preview_entry_480p.py

echo "package verification passed: 17 cases"

