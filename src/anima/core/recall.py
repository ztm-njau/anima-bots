"""Associative recall: what she "suddenly remembers" when a topic comes up.

BM25 over character bigrams (plus whole latin words), which works for Chinese without a word
segmenter or an embedding model. Searches her facts about everyone and the older part of this
chat that has scrolled out of the prompt.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anima.core.memory import Memory

_CJK = re.compile(r"[一-鿿]+")
_WORD = re.compile(r"[a-zA-Z0-9]{2,}")
_STOP = set("你我他她它的了是在吗呢吧啊哦嗯呀和就也都还很这那有没不要会可以什么怎么一个今天")


def terms(text: str) -> list[str]:
    out = [w.lower() for w in _WORD.findall(text)]
    for run in _CJK.findall(text):
        chars = [c for c in run]
        out += [a + b for a, b in zip(chars, chars[1:], strict=False) if not (a in _STOP and b in _STOP)]
    return out


def bm25(query: list[str], docs: list[list[str]], k1: float = 1.4, b: float = 0.75) -> list[float]:
    if not docs or not query:
        return [0.0] * len(docs)
    n = len(docs)
    avg = sum(map(len, docs)) / n or 1
    df = Counter(t for d in docs for t in set(d))
    q = set(query)
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for t in q:
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        scores.append(s)
    return scores


async def recall(memory: Memory, chat_key: str, text: str, *, skip_subjects: set[str], before_id: int,
                 names: dict[str, str], clock, facts: int = 4, moments: int = 3) -> tuple[list[str], list[str]]:
    query = terms(text)
    if len(query) < 2:
        return [], []
    q = set(query)
    fact_rows = [f for f in await memory.all_facts() if f.subject not in skip_subjects]
    fact_terms = [terms(f.content) for f in fact_rows]
    fact_scores = bm25(query, fact_terms)
    # BM25 ranks; shared bigrams decide relevance (absolute BM25 scores mean little in a small memory).
    ranked = sorted(zip(fact_scores, fact_rows, fact_terms, strict=True), key=lambda x: -x[0])
    best_facts = [(s, f) for s, f, t in ranked if len(q & set(t)) >= 2][:facts]
    fact_lines = []
    for _score, fact in best_facts:
        who = "你自己" if fact.subject == "self" else names.get(fact.subject) or (await _name(memory, fact.subject))
        fact_lines.append(f"{who}：{fact.content}")

    rows = [m for m in await memory.older_messages(chat_key, before_id) if len(m.text) >= 4]
    row_terms = [terms(m.text) for m in rows]
    msg_scores = bm25(query, row_terms)
    ranked_rows = sorted(zip(msg_scores, rows, row_terms, strict=True), key=lambda x: -x[0])
    best = [m for _s, m, t in ranked_rows if len(q & set(t)) >= 3][:moments]
    moment_lines = [
        f"{clock.to_local(m.ts):%m-%d} {'你' if m.is_self else m.sender_name}：{m.text[:70]}"
        for m in sorted(best, key=lambda m: m.id)
    ]
    return fact_lines, moment_lines


async def _name(memory: Memory, subject: str) -> str:
    if subject.count(":") == 2:
        return "这个聊天"
    user = await memory.get_user(subject)
    return user.call_name if user else "某人"
