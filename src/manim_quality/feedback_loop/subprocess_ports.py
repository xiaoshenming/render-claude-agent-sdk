from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .grading import GRADE_POLICY_VERSION, grade_assurance_row
from .models import AssuranceOutcome, Candidate
from .process_io import (
    copy_coder_evidence,
    read_json,
    run_command,
    sha256,
    write_json,
)


@dataclass(frozen=True, slots=True)
class ProcessConfig:
    repo: Path
    root: Path
    case_id: str
    question: str
    assets_dir: Path | None
    model: str
    manim_python: Path
    runtime_python_paths: tuple[Path, ...]
    max_turns: int = 24
    max_tool_calls: int = 40
    tts_mode: str = "disabled"


class SubprocessCoder:
    def __init__(self, config: ProcessConfig) -> None:
        self.config = config

    def repair(self, candidate, issues, repair_round):
        round_root = self.config.root / f"coder-{repair_round}"
        package = round_root / "package"
        source_dir = package / "cases" / self.config.case_id / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate.source_path, source_dir / "main.py")
        if issues:
            write_json(source_dir / "final_assurance_issues.json", {
                "schema_version": "assurance-feedback-v1",
                "issues": list(issues),
            })
        if self.config.assets_dir and self.config.assets_dir.is_dir():
            shutil.copytree(
                self.config.assets_dir,
                package / "cases" / self.config.case_id / "assets",
                dirs_exist_ok=True,
            )
        output = round_root / "output"
        argv = [
            sys.executable,
            str(self.config.repo / "scripts/run_unified_quality_batch.py"),
            "--package", str(package),
            "--output", str(output),
            "--repo", str(self.config.repo),
            "--model", self.config.model,
            "--manim-python", str(self.config.manim_python),
            "--agent-concurrency", "1",
            "--render-concurrency", "1",
            "--max-turns", str(self.config.max_turns),
            "--max-tool-calls", str(self.config.max_tool_calls),
        ]
        for path in self.config.runtime_python_paths:
            argv.extend(("--runtime-python-path", str(path)))
        run_command(argv, round_root / "batch.log", self.config.repo)
        summary = read_json(output / "batch_summary.json")
        rows = summary.get("results") or []
        if len(rows) != 1 or rows[0].get("status") != "PROPOSED":
            raise RuntimeError("Coder did not produce a PROPOSED candidate")
        row = rows[0]
        decision = row.get("decision") or {}
        validation = decision.get("validation") or {}
        details = validation.get("details") or {}
        source = Path(row["output"]) / "output/proposed_candidate.py"
        video = Path(str(details.get("video_path") or ""))
        if not validation.get("passed") or not source.is_file() or not video.is_file():
            raise RuntimeError("Coder candidate lacks fresh render evidence")
        revision_id = str(
            decision.get("final_revision_id")
            or decision.get("submitted_revision_id")
            or ""
        )
        if not revision_id:
            raise RuntimeError("Coder candidate lacks a real revision identity")
        return Candidate(
            revision_id=revision_id,
            source_sha256=sha256(source),
            video_sha256=sha256(video),
            source_path=str(source),
            video_path=str(video),
        )


class SubprocessAssurance:
    def __init__(self, config: ProcessConfig) -> None:
        self.config = config

    def review(self, candidate: Candidate, assurance_pass: int) -> AssuranceOutcome:
        pass_root = self.config.root / f"assurance-{assurance_pass}"
        package = pass_root / "package"
        source = package / "sources" / self.config.case_id / "main.py"
        video = package / "videos" / f"{self.config.case_id}.mp4"
        source.parent.mkdir(parents=True, exist_ok=True)
        video.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate.source_path, source)
        shutil.copy2(candidate.video_path, video)
        if self.config.assets_dir and self.config.assets_dir.is_dir():
            shutil.copytree(
                self.config.assets_dir,
                source.parent / "assets",
                dirs_exist_ok=True,
            )
        logs = pass_root / "logs" / self.config.case_id
        logs.mkdir(parents=True, exist_ok=True)
        copy_coder_evidence(Path(candidate.source_path), logs)
        write_json(package / "cases.json", [{
            "key": self.config.case_id,
            "question": self.config.question,
            "group": "three-pass-feedback-loop",
            "final_revision_id": candidate.revision_id,
            "tts_mode": self.config.tts_mode,
            "source": {"sha256": candidate.source_sha256},
            "video": {"sha256": candidate.video_sha256},
        }])
        output = pass_root / "output"
        argv = _assurance_argv(self.config, package, pass_root, output)
        run_command(argv, pass_root / "assurance.log", self.config.repo)
        rows = read_json(output / "results.json").get("cases") or []
        if len(rows) != 1:
            raise RuntimeError("Final Assurance did not return exactly one case")
        row = rows[0]
        grade = grade_assurance_row(row)
        if grade == "E":
            raise RuntimeError(str(row.get("agent_error") or "assurance incomplete"))
        agent = row.get("agent") or {}
        usage = row.get("agent_usage") or {}
        write_json(pass_root / "grade.json", {
            "policy_version": GRADE_POLICY_VERSION,
            "grade": grade,
            "row": row,
        })
        return AssuranceOutcome(
            grade=grade,
            status=str(agent.get("status") or ""),
            issues=tuple(agent.get("issues") or ()),
            usage={key: int(value) for key, value in usage.items()},
        )


def _assurance_argv(config, package, pass_root, output) -> list[str]:
    argv = [
        sys.executable,
        str(config.repo / "scripts/run_final_assurance_demo.py"),
        "--case-manifest", str(package / "cases.json"),
        "--logs", str(pass_root / "logs"),
        "--output", str(output),
        "--with-agent", "--full-verification",
        "--manim-python", str(config.manim_python),
        "--workers", "1",
        "--model", config.model,
    ]
    for path in config.runtime_python_paths:
        argv.extend(("--runtime-python-path", str(path)))
    return argv
