# app/formatting.py
"""Convert Markdown-formatted LLM responses to Telegram-compatible HTML.

Telegram's HTML parse mode supports only a limited tag set:
  <b>, <strong>, <i>, <em>, <u>, <ins>, <s>, <strike>, <del>,
  <code>, <pre>, <a href="...">, <tg-spoiler>

Unsupported constructs are approximated:
  - ATX headers (# … ######) → <b>header text</b>
  - Pipe tables              → <pre> (preformatted ASCII)
"""

import re
import html as _html


def markdown_to_html(text: str) -> str:
    """Convert a Markdown string to Telegram-compatible HTML.

    Handles fenced code blocks, pipe tables, ATX headers (H1–H6),
    bold (**text** / __text__), italic (*text*), and inline code (`text`).
    """
    if not text:
        return text

    lines = text.split("\n")
    result: list[str] = []
    code_lines: list[str] = []
    table_lines: list[str] = []
    in_code_block = False

    for line in lines:
        # ── Fenced code block ──────────────────────────────────────────────
        if line.startswith("```"):
            if in_code_block:
                code_text = _html.escape("\n".join(code_lines))
                result.append(f"<pre><code>{code_text}</code></pre>")
                code_lines.clear()
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        # ── Pipe table row ─────────────────────────────────────────────────
        if line.startswith("|"):
            table_lines.append(line)
            continue

        # Flush a pending table before processing the next non-table line
        if table_lines:
            table_text = _html.escape("\n".join(table_lines))
            result.append(f"<pre>{table_text}</pre>")
            table_lines.clear()

        # ── Regular line ───────────────────────────────────────────────────
        result.append(_process_line(line))

    # Flush any unclosed blocks at end of text
    if code_lines or in_code_block:
        code_text = _html.escape("\n".join(code_lines))
        result.append(f"<pre><code>{code_text}</code></pre>")
    if table_lines:
        table_text = _html.escape("\n".join(table_lines))
        result.append(f"<pre>{table_text}</pre>")

    return "\n".join(result)


def _process_line(line: str) -> str:
    """HTML-escape a line and convert inline Markdown to HTML tags."""
    # Escape HTML special characters first; markdown markers (* _ ` #)
    # are not HTML-special, so they survive the escape unchanged.
    line = _html.escape(line)

    # ATX headers: # … ######
    m = re.match(r"^(#{1,6})\s+(.*)", line)
    if m:
        return f"<b>{_apply_inline(m.group(2))}</b>"

    return _apply_inline(line)


def _apply_inline(text: str) -> str:
    """Apply inline Markdown → HTML patterns to already-HTML-escaped text.

    Processing order matters: inline code is extracted first so that bold/
    italic patterns are not applied inside code spans.
    """
    # 1. Stash inline code spans to prevent further processing of their content
    stash: dict[str, str] = {}
    counter = [0]

    def _save(m: re.Match) -> str:
        key = f"\x00{counter[0]}\x00"
        counter[0] += 1
        stash[key] = f"<code>{m.group(1)}</code>"
        return key

    text = re.sub(r"`([^`\n]+?)`", _save, text)

    # 2. Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # 3. Italic: *text* (single asterisk, not adjacent to another asterisk)
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", text)

    # 4. Restore stashed inline code spans
    for key, value in stash.items():
        text = text.replace(key, value)

    return text
