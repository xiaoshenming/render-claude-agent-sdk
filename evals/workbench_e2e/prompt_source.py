from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

END_MARKER_RULE = "【重要】代码末尾必须添加注释 # === END === 作为结束标记"
RENDER_SAFETY_RULE = (
    "【渲染稳定性】Text 的 t2c/t2f/t2s 映射键必须两两不包含、不重叠，"
    "即使映射到相同样式也不允许重复命中；中文必须使用 Text，严禁放入 Tex/MathTex；"
    "数学表达式优先使用 MathTex，Tex/MathTex 字符串必须是可独立编译的合法 LaTeX。"
)
DEFAULT_VOICE = "zh-CN-XiaoxiaoMultilingualNeural"


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    prompt_id: int
    name: str
    version: int
    text: str


class PromptSource:
    def __init__(self, database: Path) -> None:
        self._database = Path(database).resolve(strict=True)

    def render(self, prompt_id: int, *, problem: str, solution: str) -> RenderedPrompt:
        name, version, template = self._latest(prompt_id)
        problem_with_solution = f"{problem}\n\n【解题过程】\n{solution}"
        text = template.replace("{{problem}}", problem_with_solution)
        text = text.replace("__VOICE__", DEFAULT_VOICE)
        text = f"{text.rstrip()}\n\n{RENDER_SAFETY_RULE}\n\n{END_MARKER_RULE}"
        return RenderedPrompt(prompt_id, name, version, text)

    def _latest(self, prompt_id: int) -> tuple[str, int, str]:
        query = """
            select p.name, v.version_number, v.content
            from prompts p join prompt_versions v on v.prompt_id = p.id
            where p.id = ? order by v.version_number desc limit 1
        """
        with sqlite3.connect(self._database) as connection:
            row = connection.execute(query, (prompt_id,)).fetchone()
        if row is None:
            raise ValueError(f"prompt not found: {prompt_id}")
        return str(row[0]), int(row[1]), str(row[2])
