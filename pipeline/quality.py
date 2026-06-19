"""Batch-quality monitoring (ANNOTATION_PIPELINE_V2 §3.5).

At scale we don't read every annotation. Two cheap, deterministic tools:
- `sample_for_judging` picks a stable ~fraction subset (by hash, no RNG -> reproducible)
  so a batch run can spend judge calls on a representative slice, not the whole corpus.
- `judge_report` aggregates a judge's verdicts into a flag list + counts.

The golden fact-line regression (golden/fact_lines.json) is checked in the test suite: the
DETERMINISTIC fact layer must stay byte-stable when prompts/models/bands change.
"""

from __future__ import annotations

import hashlib


def sample_for_judging(ids: list[str], fraction: float) -> list[str]:
    """A deterministic ~`fraction` subset of `ids`, stable across runs (hash-bucketed, no
    randomness so a batch job samples the same slice every time). fraction clamped to [0,1]."""
    if fraction <= 0:
        return []
    if fraction >= 1:
        return list(ids)
    cut = int(fraction * 1000)
    return [i for i in ids
            if int(hashlib.sha1(i.encode("utf-8")).hexdigest(), 16) % 1000 < cut]


def judge_report(items: list[tuple[str, str]], judge_fn) -> dict:
    """Run `judge_fn(text) -> list[str] issues` over (id, text) items; aggregate.
    Returns {total, revised, issues: {id: [issue, ...]}} — outliers to inspect, not a
    requirement to read everything."""
    issues: dict[str, list[str]] = {}
    for ident, text in items:
        found = judge_fn(text)
        if found:
            issues[ident] = list(found)
    return {"total": len(items), "revised": len(issues), "issues": issues}
