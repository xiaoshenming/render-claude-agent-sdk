"""Build and freeze rendered, paired logic-mutation evaluation packs."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
from pathlib import Path

PACK_SCHEMA = "manim-quality.logic-mutation-pack.v1"
FROZEN_SCHEMA = "manim-quality.logic-eval.v1"


class MutationSpecError(ValueError):
    pass


def build_pack(spec_path: Path, dataset_root: Path) -> Path:
    spec = _read_object(spec_path)
    pack_id = _text(spec.get("pack_id"), "pack_id")
    cases = _objects(spec.get("cases"), "cases")
    if not cases:
        raise MutationSpecError("cases must not be empty")
    root = Path(dataset_root).resolve()
    pack = root / pack_id
    if pack.exists():
        raise MutationSpecError(f"pack already exists: {pack}")
    pack.mkdir(parents=True)
    labels: dict[str, object] = {}
    public_cases = []
    for raw in cases:
        item, label = _build_case(pack, raw)
        public_cases.append(item)
        labels[item["sample_id"]] = label
    manifest = {
        "schema_version": PACK_SCHEMA,
        "pack_id": pack_id,
        "sample_count": len(public_cases),
        "samples": public_cases,
    }
    _write_json(pack / "manifest.json", manifest)
    _write_json(pack / "evaluation_ground_truth_private.json", labels)
    return pack


def freeze_pack(pack: Path, dataset_root: Path, output_path: Path) -> dict[str, object]:
    root = Path(dataset_root).resolve(strict=True)
    pack = Path(pack).resolve(strict=True)
    if not pack.is_relative_to(root):
        raise MutationSpecError("pack must be contained by dataset_root")
    source = _read_object(pack / "manifest.json")
    labels = _read_object(pack / "evaluation_ground_truth_private.json")
    samples = []
    for item in _objects(source.get("samples"), "samples"):
        sample_id = _text(item.get("sample_id"), "sample_id")
        label = _object(labels.get(sample_id), f"ground truth {sample_id}")
        sample = pack / "samples" / sample_id
        samples.append(_frozen_case(root, sample, sample_id, label))
    frozen = {
        "schema_version": FROZEN_SCHEMA,
        "pack_id": _text(source.get("pack_id"), "pack_id"),
        "truth": "known_bad",
        "frozen": True,
        "dataset_root_env": "MANIM_LOGIC_EVAL_PACKS_ROOT",
        "source_manifest": _artifact(root, pack / "manifest.json"),
        "private_ground_truth": _artifact(
            root, pack / "evaluation_ground_truth_private.json"
        ),
        "sample_count": len(samples),
        "samples": samples,
    }
    _write_json(output_path, frozen)
    return frozen


def _build_case(pack: Path, raw: dict[str, object]):
    sample_id = _text(raw.get("sample_id"), "sample_id")
    source = Path(_text(raw.get("source_dir"), "source_dir")).resolve(strict=True)
    sample = pack / "samples" / sample_id
    sample.mkdir(parents=True)
    original = (source / "candidate_final.py").read_text(encoding="utf-8")
    mutated, target_lines = _mutate(original, raw.get("replacements"))
    ast.parse(mutated)
    task = _read_object(source / "task.json")
    (sample / "candidate.py").write_text(mutated, encoding="utf-8")
    (sample / "original_candidate.py").write_text(original, encoding="utf-8")
    shutil.copyfile(source / "video_final.mp4", sample / "source_correct.mp4")
    _write_problem(sample / "problem_text.txt", task)
    _write_public_metadata(sample, sample_id, source, task, mutated)
    public = {"sample_id": sample_id, "source_task_id": task.get("task_id")}
    label = {
        "issue_type": _text(raw.get("issue_type"), "issue_type"),
        "mutation_type": _text(raw.get("mutation_type"), "mutation_type"),
        "difficulty": _text(raw.get("difficulty"), "difficulty"),
        "target_lines": target_lines,
        "line_no": target_lines[0],
        "expected": _text(raw.get("expected"), "expected"),
        "observed": _text(raw.get("observed"), "observed"),
        "acceptance_predicates": _texts(
            raw.get("acceptance_predicates"), "acceptance_predicates"
        ),
    }
    _write_json(sample / "mutation_ground_truth.json", label)
    return public, label


def _mutate(code: str, value: object) -> tuple[str, list[int]]:
    replacements = _objects(value, "replacements")
    if not replacements:
        raise MutationSpecError("replacements must not be empty")
    mutated = code
    targets = []
    for item in replacements:
        old = _text(item.get("old"), "replacement.old")
        new = _text(item.get("new"), "replacement.new")
        if mutated.count(old) != 1:
            raise MutationSpecError(
                f"replacement target must occur exactly once: {old!r}"
            )
        mutated = mutated.replace(old, new, 1)
        targets.append(mutated[: mutated.index(new)].count("\n") + 1)
    return mutated, sorted(set(targets))


def _write_problem(path: Path, task: dict[str, object]) -> None:
    knowledge = _text(task.get("knowledge_point"), "knowledge_point")
    problem = _text(task.get("problem"), "problem")
    solution = _text(task.get("expected_solution"), "expected_solution")
    path.write_text(
        f"【知识点】\n{knowledge}\n\n【题目】\n{problem}\n\n【参考答案】\n{solution}\n",
        encoding="utf-8",
    )


def _write_public_metadata(
    sample: Path,
    sample_id: str,
    source: Path,
    task: dict[str, object],
    code: str,
) -> None:
    scene_name = _scene_name(code)
    _write_json(
        sample / "case_manifest.json",
        {
            "schema_version": "manim-quality.logic-case.v1",
            "case_id": sample_id,
            "scene_name": scene_name,
        },
    )
    _write_json(
        sample / "sample_meta.json",
        {
            "schema_version": "manim-quality.logic-sample.v1",
            "source": "workbench_e2e_20260713",
            "source_task_id": task.get("task_id"),
            "source_slot_id": task.get("slot_id"),
            "source_dir": str(source),
            "scene_name": scene_name,
        },
    )


def _frozen_case(root: Path, sample: Path, sample_id: str, label):
    names = (
        "candidate.py",
        "original_candidate.py",
        "problem_text.txt",
        "case_manifest.json",
        "sample_meta.json",
        "source_correct.mp4",
        "before.mp4",
    )
    return {
        "sample_id": sample_id,
        "truth": "known_bad",
        "expected_issue_type": _text(label.get("issue_type"), "issue_type"),
        "difficulty": _text(label.get("difficulty"), "difficulty"),
        "target_lines": _positive_ints(label.get("target_lines")),
        "artifacts": {name: _artifact(root, sample / name) for name in names},
    }


def _scene_name(code: str) -> str:
    tree = ast.parse(code)
    classes = [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            isinstance(child, ast.FunctionDef) and child.name == "construct"
            for child in node.body
        )
    ]
    if "Solution" in classes:
        return "Solution"
    if not classes:
        raise MutationSpecError("candidate has no renderable Scene")
    return classes[-1]


def _artifact(root: Path, path: Path) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise MutationSpecError(f"artifact escapes dataset root: {path}")
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return {
        "path": resolved.relative_to(root).as_posix(),
        "sha256": f"sha256:{digest}",
    }


def _read_object(path: Path) -> dict[str, object]:
    return _object(json.loads(Path(path).read_text(encoding="utf-8-sig")), str(path))


def _object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise MutationSpecError(f"{name} must be an object")
    return value


def _objects(value: object, name: str) -> list[dict[str, object]]:
    if type(value) is not list or not all(type(item) is dict for item in value):
        raise MutationSpecError(f"{name} must be an array of objects")
    return value


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise MutationSpecError(f"{name} must be non-empty text")
    return value


def _texts(value: object, name: str) -> list[str]:
    if type(value) is not list:
        raise MutationSpecError(f"{name} must be an array")
    return [_text(item, name) for item in value]


def _positive_ints(value: object) -> list[int]:
    if type(value) is not list or not value:
        raise MutationSpecError("target_lines must be a non-empty array")
    if any(type(item) is not int or item < 1 for item in value):
        raise MutationSpecError("target_lines must contain positive integers")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--spec", type=Path, required=True)
    build.add_argument("--dataset-root", type=Path, required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--pack", type=Path, required=True)
    freeze.add_argument("--dataset-root", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if args.command == "build":
        print(build_pack(args.spec, args.dataset_root))
    else:
        freeze_pack(args.pack, args.dataset_root, args.output)
        print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
