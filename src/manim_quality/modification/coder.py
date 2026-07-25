"""Scene-scoped user modification coder over the shared Agent runtime."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from manim_quality.agents._runtime_models import AgentRunFailed
from manim_quality.agents.profile import AgentProfile, AgentRole
from manim_quality.agents.runtime import AgentRunRequest, AgentRuntime
from manim_quality.agents.usage import AgentCallRecord

from .planner import ModificationPlan, validate_modification

_PROMPT_PATH = Path(__file__).with_name("prompts") / "coder.md"
_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "summary"],
    "properties": {
        "status": {"type": "string", "enum": ["edited"]},
        "summary": {"type": "string", "minLength": 1},
    },
}


class ModificationCoderError(RuntimeError):
    def __init__(self, message: str, record: AgentCallRecord | None = None) -> None:
        self.record = record
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ModificationCoderResult:
    source_code: str
    changed_scene_ids: tuple[str, ...]
    call_record: AgentCallRecord


class ModificationCoder:
    def __init__(self, runtime: AgentRuntime, profile: AgentProfile) -> None:
        if not isinstance(runtime, AgentRuntime):
            raise TypeError("runtime must be AgentRuntime")
        if not isinstance(profile, AgentProfile) or profile.role is not AgentRole.CODER:
            raise ValueError("modification coder requires Read+Edit coder profile")
        self._runtime = runtime
        self._profile = profile

    def patch_source(
        self,
        *,
        run_id: str,
        instruction: str,
        source_code: str,
        plan: ModificationPlan,
    ) -> ModificationCoderResult:
        with tempfile.TemporaryDirectory(prefix="manim-modification-") as directory:
            workspace = Path(directory)
            candidate = workspace / "candidate.py"
            candidate.write_text(source_code, encoding="utf-8")
            return self.patch(
                run_id=run_id,
                instruction=instruction,
                plan=plan,
                workspace=workspace,
                candidate_path=candidate,
                estimated_input_tokens=max(1, len(source_code) // 4),
                reserved_output_tokens=2_000,
            )

    def patch(
        self,
        *,
        run_id: str,
        instruction: str,
        plan: ModificationPlan,
        workspace: Path,
        candidate_path: Path,
        estimated_input_tokens: int,
        reserved_output_tokens: int,
    ) -> ModificationCoderResult:
        candidate = _candidate(workspace, candidate_path)
        before = _read(candidate)
        prompt = _prompt(instruction, plan)
        request = AgentRunRequest(
            run_id=run_id,
            profile=self._profile,
            prompt=prompt,
            output_schema=_OUTPUT_SCHEMA,
            workspace=workspace,
            readable_paths=(candidate,),
            editable_paths=(candidate,),
            context_bytes=len(prompt.encode()) + len(before.encode()),
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            reserved_cache_read_tokens=0,
            reserved_cache_write_tokens=0,
        )
        try:
            call = self._runtime.run(request)
            after = _read(candidate)
            changed = validate_modification(before, after, plan)
        except AgentRunFailed as error:
            _restore(candidate, before)
            raise ModificationCoderError(str(error), error.record) from error
        except Exception:
            _restore(candidate, before)
            raise
        return ModificationCoderResult(after, changed, call.record)


def _candidate(workspace: Path, candidate_path: Path) -> Path:
    root = Path(workspace).resolve(strict=True)
    candidate = Path(candidate_path).resolve(strict=True)
    if not candidate.is_file() or not candidate.is_relative_to(root):
        raise ModificationCoderError("candidate must be a file inside workspace")
    return candidate


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ModificationCoderError("candidate must be readable UTF-8") from error


def _restore(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")


def _prompt(instruction: str, plan: ModificationPlan) -> str:
    if not isinstance(instruction, str) or not instruction.strip():
        raise ModificationCoderError("instruction must be non-empty")
    payload = {
        "instruction": instruction,
        "target_scenes": list(plan.target_scene_ids),
        "editable_regions": [
            [item.scene_id, item.line_start, item.line_end]
            for item in plan.editable_regions
        ],
        "read_only_neighbors": [item.scene_id for item in plan.context_regions],
    }
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace(
        "{{MODIFICATION_JSON}}",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )
