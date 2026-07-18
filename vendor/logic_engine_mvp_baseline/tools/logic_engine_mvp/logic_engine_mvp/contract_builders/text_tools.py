from __future__ import annotations

import re


def nonempty_stripped_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def find_exact_code_line_numbers(code_lines: list[str], expected: str) -> list[int]:
    return [
        line_no
        for line_no, line in enumerate(code_lines, start=1)
        if line.strip() == expected
    ]


def line_has_kwarg_value(line: str, kwarg: str, value: str) -> bool:
    return kwarg_pattern(kwarg, value).search(line) is not None


def replace_kwarg_value(line: str, kwarg: str, old_value: str, new_value: str) -> str | None:
    pattern = kwarg_pattern(kwarg, old_value)
    return pattern.sub(rf"\g<prefix>{new_value}", line, count=1)


def kwarg_pattern(kwarg: str, value: str) -> re.Pattern[str]:
    value_pattern = re.escape(value).replace(r"\ ", r"\s*")
    return re.compile(rf"(?P<prefix>{re.escape(kwarg)}\s*=\s*){value_pattern}(?=\s*[,)\n])")


def find_matching_paren(text: str, open_index: int) -> int | None:
    depth = 0
    quote: str | None = None
    escape = False
    for index in range(open_index, len(text)):
        char = text[index]
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def split_top_level_args(text: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escape = False
    for char in text:
        if quote:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            continue
        if char in "([{":
            depth += 1
            current.append(char)
            continue
        if char in ")]}":
            depth -= 1
            current.append(char)
            continue
        if char == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                args.append(item)
            current = []
            continue
        current.append(char)
    item = "".join(current).strip()
    if item:
        args.append(item)
    return args


def find_source_lines(code_text: str, needle: str) -> list[int]:
    if not needle:
        return []
    return [
        line_no
        for line_no, line in enumerate(code_text.splitlines(), start=1)
        if needle in line
    ]


def trim_agent_text(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."

