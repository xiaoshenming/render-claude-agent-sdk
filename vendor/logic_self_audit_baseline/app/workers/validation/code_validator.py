"""Manim 代码验证：从 LLM 输出提取代码、验证结构、提取 Scene 信息。

从 video_worker.py 提取的代码验证相关方法（均为无状态纯函数）。
"""
import re
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# 中文标点 → ASCII 映射表
_CN_PUNCT_MAP = str.maketrans({
    "\uff0c": ",", "\u3002": ".", "\uff1b": ";", "\uff1a": ":",
    "\uff08": "(", "\uff09": ")", "\u3010": "[", "\u3011": "]",
    "\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
})


def extract_python_code(text: str) -> str:
    """从 LLM 原始输出中提取 Python 代码块。"""
    # 策略 1: 找所有 ```python ... ``` 代码块，取最长的
    blocks = re.findall(
        r"```(?:python|Python|py)?\s*\n([\s\S]+?)\n```", text, re.IGNORECASE)
    if blocks:
        code = max(blocks, key=len).strip()
        return sanitize_latex_branch_typo(code)
    # 策略 2: 宽松匹配（无换行要求）
    blocks = re.findall(
        r"```(?:python|Python|py)?\s*([\s\S]+?)```", text, re.IGNORECASE)
    if blocks:
        code = max(blocks, key=len).strip()
        return sanitize_latex_branch_typo(code)
    # 策略 3: 文本以 ``` 开头，直接去掉首尾标记
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:python|Python|py)?\s*\n?", "", stripped)
        stripped = re.sub(r"\n?```\s*$", "", stripped)
        return sanitize_latex_branch_typo(stripped.strip())
    return sanitize_latex_branch_typo(stripped)


def sanitize_chinese_punctuation(code: str) -> str:
    """将中文标点替换为 ASCII 等价物，防止 Manim 渲染报错。"""
    return code.translate(_CN_PUNCT_MAP)


# 已知 LLM 高频笔误：写 `r"\\"` (literal `\\`，匹配两个反斜杠) 来检测 LaTeX 命令，
# 但 LaTeX 命令实际只有一个反斜杠，导致 `\div / \frac / \sqrt` 等被当作纯文本渲染，
# 屏幕上看到 "/div" "/frac" 等现象。统一纠正为 `"\\"`（单反斜杠）。
_LATEX_TYPO_PATTERNS = [
    # if r"\\" in xxx / elif r"\\" in xxx （双引号 if/elif 形式）
    (re.compile(r'(\bif\s+|elif\s+)r"\\\\"\s+in\s+'), r'\1"\\\\" in '),
    # if r'\\' in xxx / elif r'\\' in xxx （单引号 if/elif 形式）
    (re.compile(r"(\bif\s+|elif\s+)r'\\\\'\s+in\s+"), r"\1'\\\\' in "),
    # 兜底：r"\\" in content / r'\\' in content（不带 if 前缀）
    (re.compile(r'r"\\\\"\s+in\s+content\b'), r'"\\\\" in content'),
    (re.compile(r"r'\\\\'\s+in\s+content\b"), r"'\\\\' in content"),
    # any/all 模式：any(c in r"\\" for ...) → any(c in "\\" for ...)
    (re.compile(r'\bin\s+r"\\\\"'), r'in "\\\\"'),
    (re.compile(r"\bin\s+r'\\\\'"), r"in '\\\\'"),
]


def sanitize_latex_branch_typo(code: str) -> str:
    r"""修正 LLM 高频笔误：将 `r"\\"` 检测改为 `"\\"`，避免 `\div` 类 LaTeX 命令
    被错判为纯文本而显示成 "/div"。"""
    if not code or "content" not in code:
        return code
    fixed = code
    for pat, repl in _LATEX_TYPO_PATTERNS:
        fixed = pat.sub(repl, fixed)
    return fixed


def validate_generated_code_shape(
    code: str,
    expected_scene_name: Optional[str] = None,
) -> tuple[bool, str]:
    """过滤明显不是 Python/Manim 代码的 LLM 输出。"""
    stripped = (code or "").strip()
    if not stripped:
        return False, "LLM输出为空"

    nonempty_lines = [
        line.strip() for line in stripped.splitlines() if line.strip()]
    if not nonempty_lines:
        return False, "LLM输出为空"

    first_line = nonempty_lines[0]
    code_marker_re = (
        r"^\s*(from\s+\w+\s+import|import\s+\w+|class\s+\w+\s*\(|"
        r"def\s+\w+\s*\(|async\s+def\s+\w+\s*\()"
    )
    has_code_marker = bool(re.search(code_marker_re, stripped, re.MULTILINE))
    has_scene_signal = "Scene" in stripped or "self." in stripped
    has_markdown_preamble = bool(
        re.search(
            r"(?m)^(#{1,6}\s|\*\*.+\*\*|- )",
            "\n".join(nonempty_lines[:8]),
        )
    )
    prose_start_re = (
        r"(?i)^(i['']ll|here['']s|let['']s|sure[, ]|first[, ]|"
        r"below is|the following|we need to|math verification)"
    )

    if expected_scene_name:
        scene_pattern = (
            rf"class\s+{re.escape(expected_scene_name)}\s*\([^)]*\)\s*:"
        )
        if not re.search(scene_pattern, stripped):
            return False, f"LLM输出缺少目标 Scene 类: {expected_scene_name}"

    if not has_code_marker and not has_scene_signal:
        return False, "LLM输出为非代码内容"

    if re.match(prose_start_re, first_line) and not re.match(
        code_marker_re, first_line
    ):
        return False, "LLM输出为非代码内容"

    if has_markdown_preamble and not has_code_marker:
        return False, "LLM输出为非代码内容"

    # --- 截断检测 ---
    last_line = nonempty_lines[-1].rstrip()
    truncation_signs = [
        last_line.endswith("\\"),
        last_line.endswith(",") and not last_line.endswith("),"),
        last_line.count("(") > last_line.count(")"),
        last_line.count("[") > last_line.count("]"),
        last_line.count("{") > last_line.count("}"),
    ]

    has_construct = "def construct(self" in stripped
    has_scene_class = bool(re.search(r"class\s+\w+.*Scene", stripped))
    if has_scene_class and not has_construct:
        return False, "LLM输出被截断：有 Scene 类但缺少 construct 方法"

    if last_line.rstrip().endswith("=") or last_line.rstrip().endswith("def"):
        return False, (
            f"LLM输出疑似被截断，末尾不完整: ...{last_line[-40:]}")

    if any(truncation_signs):
        return False, (
            f"LLM输出疑似被截断，末尾不完整: ...{last_line[-40:]}")

    if expected_scene_name:
        scene_body_match = re.search(
            rf"class\s+{re.escape(expected_scene_name)}\s*\([^)]*\)\s*:(.*)",
            stripped,
            re.DOTALL,
        )
        if scene_body_match and "self.play(" not in scene_body_match.group(1):
            return False, (
                f"LLM输出疑似不完整：目标 Scene {expected_scene_name} "
                f"缺少有效动画代码")

    base_match = re.search(r"class\s+BaseConfigScene\s*(\([^)]*\))?\s*:", stripped)
    if base_match:
        base_decl = base_match.group(0)
        if "(Scene)" not in base_decl and "(VoiceoverScene)" not in base_decl and \
                "(ThreeDScene)" not in base_decl and "(VoiceoverScene, ThreeDScene)" not in base_decl:
            return False, "LLM输出中的 BaseConfigScene 缺少对 Scene 基类的继承"

        base_body_match = re.search(
            r"class\s+BaseConfigScene\s*\([^)]*\)\s*:(.*?)(?=\nclass\s+\w|\Z)",
            stripped,
            re.DOTALL,
        )
        if base_body_match:
            base_body = base_body_match.group(1)
            required_methods = ("def setup_layout", "def show_text", "def restore_text")
            missing = [name for name in required_methods if name not in base_body]
            if missing:
                return False, (
                    "LLM输出中的 BaseConfigScene 不完整，缺少方法: "
                    + ", ".join(missing)
                )

    scene_count = len(
        re.findall(r"class\s+Scene_\d+_\w+\s*\(", stripped))
    if 2 <= scene_count < 4:
        return False, (
            f"LLM输出内容不足：只生成了 {scene_count} 个 Scene 切片"
            f"（最少需要 4 个），可能被截断或内容过于简略"
        )

    if scene_count >= 4 and "# END" not in stripped:
        last_scene_match = list(
            re.finditer(
                r"class\s+Scene_\d+_\w+\s*\([^)]*\)\s*:", stripped))
        if last_scene_match:
            last_scene_code = stripped[last_scene_match[-1].start():]
            if "def construct(self" not in last_scene_code:
                return False, (
                    "LLM输出被截断：最后一个 Scene 缺少 construct 方法")

    return True, ""


def extract_all_scene_names(code: str) -> List[str]:
    """提取所有 Scene_XX_Name 格式的类名，按序号排序。"""
    matches = re.findall(
        r"class\s+(Scene_\d+_\w+)\s*\([^)]*\)\s*:", code)
    if not matches:
        return []
    return sorted(
        matches,
        key=lambda x: int(re.search(r"Scene_(\d+)", x).group(1)))


def is_slice_mode(code: str) -> bool:
    """检测代码是否包含切片架构（2+ 个 Scene_XX 类）。"""
    return len(extract_all_scene_names(code)) >= 2


def extract_class_name(code: str) -> Optional[str]:
    """提取场景类名，支持所有继承自 *Scene 的类。"""
    match = re.search(
        r"class\s+([A-Za-z0-9_]+)\s*\([^)]*Scene[^)]*\)\s*:", code)
    return match.group(1) if match else None


def extract_title_from_code(code: str) -> str:
    """从 Manim 代码中提取标题（比调用大模型更快）。

    4 级回退策略:
    1. show_text(r"$$\\text{标题}$$", "title") 格式
    2. Tex(r"$$\\text{标题}$$") 格式
    3. Text("标题") 格式
    4. Scene_XX_Name 类名 / 其他 Scene 子类名
    """
    # 优先: show_text 槽位系统
    match = re.search(
        r'show_text\s*\(\s*r"\$\$\\text\{([^}]+)\}\$\$"\s*,\s*["\']title["\']',
        code,
    )
    if match:
        title = match.group(1).strip()
        return title[:15] if len(title) > 15 else title

    # 备选: Tex 格式
    match = re.search(r'title\s*=\s*Tex\s*\(\s*r"\$\$\\text\{([^}]+)\}', code)
    if match:
        title = match.group(1).strip()
        return title[:15] if len(title) > 15 else title

    # 备选: Text 格式
    match = re.search(r'title\s*=\s*Text\s*\(\s*["\']([^"\']+)["\']', code)
    if match:
        title = match.group(1).strip()
        return title[:15] if len(title) > 15 else title

    # 备选: Scene_XX_Name 类名
    match = re.search(r'class\s+(Scene_\d+_\w+)\s*\(', code)
    if match:
        parts = match.group(1).split('_', 2)
        title = parts[2] if len(parts) >= 3 else match.group(1)
        title = re.sub(r'([a-z])([A-Z])', r'\1 \2', title)
        return title[:15] if len(title) > 15 else title

    # 最后备选: 任意非基类 Scene 子类
    for m in re.finditer(r'class\s+([A-Za-z0-9_]+)\s*\([^)]*Scene', code):
        name = m.group(1)
        if name not in ('BaseConfigScene', 'VoiceoverScene'):
            title = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
            return title[:15] if len(title) > 15 else title

    return "Shuxuepai动画视频"


def extract_scene_standalone_code(full_code: str, scene_name: str) -> str:
    """提取 header + 指定 Scene 类的完整可独立执行代码。"""
    first_scene_match = re.search(
        r"(?m)^class\s+Scene_\d+_\w+\s*\([^)]*\)\s*:",
        full_code,
    )
    header = full_code[:first_scene_match.start()] if first_scene_match else full_code

    scene_match = re.search(
        rf"(?ms)^class\s+{re.escape(scene_name)}\s*\([^)]*\)\s*:.*?(?=^class\s+Scene_\d+_\w+\s*\(|\Z)",
        full_code,
    )
    if not scene_match:
        return header.rstrip()

    scene_code = scene_match.group(0).strip()
    header = header.rstrip()
    return f"{header}\n\n{scene_code}" if header else scene_code


def extract_scene_class_code(full_code: str, scene_name: str) -> str:
    """仅提取目标 Scene 类定义，不包含 header。"""
    scene_match = re.search(
        rf"(?ms)^class\s+{re.escape(scene_name)}\s*\([^)]*\)\s*:.*?(?=^class\s+Scene_\d+_\w+\s*\(|\Z)",
        full_code,
    )
    return scene_match.group(0).strip() if scene_match else ""


def extract_slice_header(full_code: str) -> str:
    """提取切片独立代码中的公共 header。"""
    first_scene_match = re.search(
        r"(?m)^class\s+Scene_\d+_\w+\s*\([^)]*\)\s*:",
        full_code,
    )
    if not first_scene_match:
        return (full_code or "").strip()
    return full_code[:first_scene_match.start()].rstrip()
