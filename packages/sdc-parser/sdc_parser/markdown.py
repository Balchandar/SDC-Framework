"""A tiny, dependency-free Markdown block reader.

We do not need a full CommonMark implementation. SDC specifications use a
constrained subset: headings, paragraphs, bullet/number lists, simple pipe
tables, and fenced code blocks. This reader turns text into an ordered list of
typed blocks that the section normalizers consume.

Keeping this in-house keeps the toolchain dependency-free and, crucially,
deterministic across environments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Block:
    kind: str  # "heading" | "paragraph" | "list" | "table" | "code"
    # heading
    level: int = 0
    text: str = ""
    # list
    items: list[str] = field(default_factory=list)
    ordered: bool = False
    # table
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    # code
    lang: str = ""
    code: str = ""


def _split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    if not cells:
        return False
    for c in cells:
        c = c.strip()
        if not c or set(c) - set("-: "):
            return False
    return True


def parse_blocks(text: str) -> list[Block]:
    """Parse Markdown ``text`` into an ordered list of :class:`Block`."""
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[Block] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # blank line
        if not stripped:
            i += 1
            continue

        # fenced code
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            lang = stripped[3:].strip()
            i += 1
            code_lines: list[str] = []
            while i < n and not lines[i].strip().startswith(fence):
                code_lines.append(lines[i])
                i += 1
            i += 1  # consume closing fence
            blocks.append(Block(kind="code", lang=lang, code="\n".join(code_lines)))
            continue

        # heading
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            blocks.append(Block(kind="heading", level=level, text=stripped[level:].strip()))
            i += 1
            continue

        # table: current line has a pipe and the next line is a separator
        if "|" in line and i + 1 < n and _is_table_separator(lines[i + 1]):
            headers = _split_table_row(line)
            i += 2  # skip header + separator
            rows: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_table_row(lines[i]))
                i += 1
            blocks.append(Block(kind="table", headers=headers, rows=rows))
            continue

        # list
        if _list_marker(stripped) is not None:
            ordered = stripped[0].isdigit()
            items: list[str] = []
            while i < n:
                s = lines[i].strip()
                marker = _list_marker(s)
                if marker is None:
                    if not s:
                        break
                    # continuation line of the previous item
                    if items and not s.startswith("#") and "|" not in s:
                        items[-1] += " " + s
                        i += 1
                        continue
                    break
                items.append(s[marker:].strip())
                i += 1
            blocks.append(Block(kind="list", ordered=ordered, items=items))
            continue

        # paragraph (accumulate consecutive non-structural lines)
        para: list[str] = []
        while i < n:
            s = lines[i].strip()
            if (
                not s
                or s.startswith("#")
                or s.startswith("```")
                or s.startswith("~~~")
                or _list_marker(s) is not None
                or ("|" in lines[i] and i + 1 < n and _is_table_separator(lines[i + 1]))
            ):
                break
            para.append(s)
            i += 1
        blocks.append(Block(kind="paragraph", text=" ".join(para)))

    return blocks


def _list_marker(stripped: str) -> Optional[int]:
    """Return the length of a leading list marker, or None if not a list item."""
    if stripped[:2] in ("- ", "* ", "+ "):
        return 2
    # ordered: "1." / "12)" ...
    j = 0
    while j < len(stripped) and stripped[j].isdigit():
        j += 1
    if j > 0 and j < len(stripped) and stripped[j] in ".)" and stripped[j + 1 : j + 2] == " ":
        return j + 2
    return None
