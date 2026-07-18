import json
from pathlib import Path

import pytest

from scripts.build_logic_mutation_pack import (
    MutationSpecError,
    build_pack,
    freeze_pack,
)


def test_build_pack_keeps_ground_truth_out_of_reviewer_artifacts(
    tmp_path: Path,
) -> None:
    source = _source_case(tmp_path)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "pack_id": "logic-mutation-test",
                "cases": [
                    {
                        "sample_id": "MUT001_wrong_answer",
                        "source_dir": str(source),
                        "difficulty": "easy",
                        "mutation_type": "answer_value_change",
                        "issue_type": "wrong_final_answer",
                        "replacements": [
                            {"old": 'answer = "4"', "new": 'answer = "5"'}
                        ],
                        "expected": "The displayed answer is 4.",
                        "observed": "The displayed answer is 5.",
                        "acceptance_predicates": ["answer equals 4"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    pack = build_pack(spec, tmp_path / "dataset")

    sample = tmp_path / "dataset" / "logic-mutation-test" / "samples"
    sample /= "MUT001_wrong_answer"
    (sample / "before.mp4").write_bytes(b"rendered-mutant")
    frozen = freeze_pack(pack, tmp_path / "dataset", tmp_path / "frozen.json")
    assert 'answer = "5"' in (sample / "candidate.py").read_text(encoding="utf-8")
    assert 'answer = "4"' in (sample / "original_candidate.py").read_text(
        encoding="utf-8"
    )
    assert (sample / "source_correct.mp4").read_bytes() == b"rendered-baseline"
    public = "\n".join(
        (sample / name).read_text(encoding="utf-8")
        for name in ("problem_text.txt", "case_manifest.json", "sample_meta.json")
    )
    assert "wrong_final_answer" not in public
    assert "answer equals 4" not in public
    assert frozen["sample_count"] == 1
    assert frozen["samples"][0]["target_lines"] == [4]
    assert "before.mp4" in frozen["samples"][0]["artifacts"]


def test_build_pack_rejects_non_unique_replacement(tmp_path: Path) -> None:
    source = _source_case(tmp_path)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "pack_id": "logic-mutation-test",
                "cases": [
                    {
                        "sample_id": "MUT001_ambiguous",
                        "source_dir": str(source),
                        "difficulty": "easy",
                        "mutation_type": "ambiguous",
                        "issue_type": "wrong_final_answer",
                        "replacements": [{"old": "pass", "new": "return"}],
                        "expected": "valid code",
                        "observed": "invalid mutation target",
                        "acceptance_predicates": ["target is uniquely identified"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MutationSpecError, match="exactly once"):
        build_pack(spec, tmp_path / "dataset")


def _source_case(root: Path) -> Path:
    source = root / "source"
    source.mkdir()
    (source / "candidate_final.py").write_text(
        "from manim import *\n\nclass Solution(Scene):\n    answer = \"4\"\n\n"
        "    def construct(self):\n        pass\n        pass\n",
        encoding="utf-8",
    )
    (source / "task.json").write_text(
        json.dumps(
            {
                "task_id": "math-1",
                "knowledge_point": "addition",
                "problem": "What is 2 + 2?",
                "expected_solution": "4",
            }
        ),
        encoding="utf-8",
    )
    (source / "video_final.mp4").write_bytes(b"rendered-baseline")
    return source
