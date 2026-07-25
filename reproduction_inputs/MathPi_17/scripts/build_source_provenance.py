from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    rows = []
    for case in sorted((ROOT / "cases").iterdir()):
        if not case.is_dir():
            continue
        code = case / "source" / "main.py"
        record_path = case / "source" / "record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        actual = digest(code)
        declared = str(record.get("code_sha256") or "")
        rows.append(
            {
                "folder": case.name,
                "packed_main_py_sha256": actual,
                "record_declared_code_sha256": declared,
                "record_hash_matches_packed_file": declared == actual,
            }
        )
    payload = {
        "schema_version": "mathpi-17-original-source-provenance-v1",
        "case_count": len(rows),
        "fact_source": "packed source/main.py bytes copied from the source bundle",
        "record_hash_mismatch_count": sum(
            not row["record_hash_matches_packed_file"] for row in rows
        ),
        "cases": rows,
    }
    (ROOT / "source-provenance.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

