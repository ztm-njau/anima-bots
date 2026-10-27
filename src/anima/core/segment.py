"""Cut a long line into the bubbles a person would actually send.

People break a thought at sentence ends, keep a question on its own, and never cut through a
link, a code span, a kaomoji or a quotation. Short sentences travel together; a sentence that
is still too long is cut at a comma; a run with nowhere safe to cut is left whole.
"""

from __future__ import annotations

import re

# Spans that must never be cut: links, code, bracketed asides and kaomoji, quotations.
_PROTECTED = re.compile(
    r"https?://[^\s，。！？、）)】」』”]+"
    r"|`[^`]*`"
    r"|[（(][^（()）\n]{0,24}[)）]"
    r"|【[^【】\n]{0,40}】|「[^「」\n]{0,60}」|『[^『』\n]{0,60}』|“[^“”\n]{0,60}”|《[^《》\n]{0,40}》"
)
_STRONG = set("。！？!?…~～.")
_WEAK = set("，,；;：:、")
# Things that cling to the end of a sentence: closing marks, more punctuation, emoji and similar.
_CLING = re.compile(r"[。！？!?…~～.」』”’)）】》\s]*(?:[\U0001F000-\U0001FAFF☀-➿️‍]+[\s]*)*")


def _protected_mask(text: str) -> list[bool]:
    mask = [False] * len(text)
    for m in _PROTECTED.finditer(text):
        for i in range(m.start(), m.end() - 1):  # a cut may still fall right after the span
            mask[i] = True
    return mask


def _cuts(text: str, marks: set[str], mask: list[bool]) -> list[int]:
    """Positions after which the text may be cut."""
    cuts: list[int] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in marks and not mask[i]:
            english_stop = ch == "." and i + 1 < n and text[i + 1] == " " and text[i - 1:i].isalpha()
            if (ch == "." and not english_stop) or (ch in ":：" and text[i + 1:i + 2].isdigit()):  # 3.14, 12:30
                i += 1
                continue
            end = _CLING.match(text, i + 1).end()
            if end < n:
                cuts.append(end)
            i = max(end, i + 1)
            continue
        i += 1
    return cuts


def _pieces(text: str, cuts: list[int]) -> list[str]:
    out, start = [], 0
    for c in cuts:
        piece = text[start:c].strip()
        if piece:
            out.append(piece)
        start = c
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def _pack(pieces: list[str], target: int) -> list[str]:
    """Join neighbouring pieces while they stay short; a question ends its bubble."""
    out: list[str] = []
    for piece in pieces:
        if out and len(out[-1]) + len(piece) <= target and not out[-1].rstrip().endswith(("？", "?")):
            joiner = " " if out[-1][-1:].isascii() and piece[:1].isascii() else ""
            out[-1] = out[-1] + joiner + piece
        else:
            out.append(piece)
    return out


def split_text(text: str, split: int = 36, hard: int = 72) -> list[str]:
    """Bubbles for one line. Lines up to ``split`` characters stay whole."""
    text = text.strip()
    if len(text) <= split:
        return [text] if text else []
    mask = _protected_mask(text)
    sentences = _pieces(text, _cuts(text, _STRONG, mask))
    target = max(12, split // 2)
    out: list[str] = []
    for sentence in _pack(sentences, target):
        if len(sentence) <= hard:
            out.append(sentence)
            continue
        sub_mask = _protected_mask(sentence)
        clauses = _pieces(sentence, _cuts(sentence, _WEAK, sub_mask))
        out.extend(_pack(clauses, split))
    return out
