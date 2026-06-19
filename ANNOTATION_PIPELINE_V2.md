# Annotation Pipeline v2 — scalable, self-converging move explanations

Status: **proposal** (no code yet). Author: pipeline redesign, 2026-06-19.
Read alongside `TECH_SPEC.md` §5 and `pipeline/facts.py` / `annotate.py` / `validate.py`.

## 1. Problem

Today stage 4 asks one LLM call to write a whole free-prose annotation (facts **and**
interpretation), and stage 5 polices it. When the model slips on any one of many
constraints we either tighten the prompt or re-roll the **whole game**, trading one
violation for another — the "反复小修小改" loop.

Root pattern from the bugs we actually hit:

| Recurring bug | Layer |
|---|---|
| wrong "mate in N" | fact (eval_mate) |
| mating move called "mate in 1" | fact (is_checkmate) |
| material claim with no capture | fact (captures) |
| "the quieter queen moves keep the advantage" | fact (it generalized over moves it never saw) |
| bare squares `g5`/`b5` | half fact / half style |
| sentence too long | style |

**~4 of 6 are the fact layer leaking into free prose.** And because we regenerate the
whole game on any failure, 7 good annotations get re-rolled to fix 1.

This does not scale: with many puzzles we cannot human-review every move of every game.

## 2. Design principles

1. **Facts are deterministic, never narrated by the LLM.** Numbers, mate status,
   material, legality, tactic labels, eval verdict come from `facts.py` as fixed text.
2. **The LLM writes only "why / the plan"** — plan-language reasoning, grounded in the
   supplied facts, no numbers/captures/mate-claims/squares of its own.
3. **The pipeline is the gate, not a human.** Determinism + automated judging + a repair
   loop must converge without per-move human review.
4. **Humans see exceptions only.** The few moves that won't pass after N repairs are
   flagged; human effort scales with failures, not with puzzle count.
5. **Worst case is "bland, not wrong."** Deterministic validation guarantees factual
   correctness; constraining the why-layer bounds the downside to dull, never false.

## 3. Target architecture

```
facts.py ──► FactSheet (structured, deterministic)
                 │
                 ├─► fact_line  (templated sentence, EN+ZH)         ── deterministic, final
                 │
                 └─► prompt facts ──► LLM (rationale only) ──► rationale text
                                                                   │
   final annotation = fact_line + rationale                        │
                                                                   ▼
                          ┌──────────── automated gates ───────────┐
                          │ 1 deterministic validate.py            │
                          │ 2 LLM-judge (grounding/consistency)    │
                          └────────────────┬───────────────────────┘
                                  pass │           │ fail
                                       ▼           ▼
                                   accept    targeted repair (this field only)
                                                   │  loop ≤ N
                                                   ▼ still failing
                                              flag for human queue
```

### 3.1 Fact layer — `FactSheet` + deterministic `fact_line`

Extend `facts.py` with a single `build_fact_sheet(move) -> FactSheet` that composes
everything already computed (mate_pattern, line_material, tactical_motifs,
mate_in_two_defenses, castling, eval verdict, mate distance) into one structured object,
plus a **deterministic `fact_line`** in EN and ZH — the verifiable claims as fixed text:

- checkmate → `"Checkmate."` / `"将杀。"`
- forced mate (not yet mate) → `"Forced mate in {N}."` / `"{N} 步强制将杀。"`
- material in the line → `"Wins a {piece}."` / `"得一{子}。"` (only if `line_material` shows it)
- eval verdict bucket → `"White is clearly better (+2.5)."` (from `eval_cp` band, same
  buckets as `ScoringConfig`)
- key tactic → only motifs `facts.tactical_motifs` actually returns

The `fact_line` is **never** generated or editable by the LLM. It cannot be wrong because
it is the same engine fact the validator checks. This removes bug classes 1–4 by
construction.

(Open question A: do we still want the motif words in the fact line? The "skewer" mislabel
on the Opera queen-sac shows `tactical_motifs` is geometric, not intent-aware. Option:
keep motifs out of the fact line until the detector is intent-aware.)

### 3.2 Interpretation layer — slim prompt, narrow schema

- `MoveAnnotationResult.annotation` is replaced by **`rationale`**: 1–2 sentences of
  plan-language *why*, ≤ limit, **forbidden** from stating any number, capture, mate
  claim, or bare square (those live in `fact_line`).
- System prompt shrinks dramatically: most current hard-rules become unnecessary because
  the model no longer narrates facts. What remains: stay grounded in supplied facts, plan
  language for 800–2000, coach tone, no spoilers, no bare squares, length.
- Final stored annotation = `fact_line + " " + rationale` (per language). The app renders
  it as one string (no app change needed) — or we store the two parts separately for
  richer rendering later (Open question B).

### 3.3 Automated gates

1. **Deterministic `validate.py`** — unchanged role, keeps growing. Now it mostly only has
   to police the *rationale* (style + grounding), since facts are templated.
2. **LLM-judge** (new, pipeline-only — does NOT violate hard rule #2, which is about the
   *app* runtime). A separate model call returns `{verdict: pass|revise, issues: [...]}`,
   checking: names no tactic outside the detected set; doesn't contradict the engine verdict;
   isn't generic filler.

   **Hard-won rule (2026-06-19 live run): the judge must NOT be given the FEN to re-derive
   legality/geometry/mate.** When it was, it hallucinated — called the *actual played* move
   "illegal," mis-derived diagonals, waffled, and flagged all 3 moves NEEDS_HUMAN. LLMs are
   bad at board geometry; that's the whole reason facts are deterministic. So the judge gets
   the *authoritative facts* (move is legal & played, engine verdict, detected motifs) and is
   explicitly forbidden to re-derive — it only checks the prose against those facts, and is
   told "when unsure, pass." After this change the same 3 moves passed clean and the loose
   "pin/skewer" labels disappeared. Corollary: the judge canNOT catch motif-detector
   looseness (fix the detector for that — deferred, open question A).

### 3.4 Repair loop (replaces whole-game re-roll)

`4_annotate` becomes, per guess point per language:

```
generate rationale
loop up to N (e.g. 3):
    errs = validate(field) + judge(field)
    if none: accept; break
    regenerate THIS field only, with errs fed back ("your sentence was 65 chars > 60; ...")
else:
    mark move.review_status = NEEDS_HUMAN with the residual errs
```

- Per-field, not per-game → a clean annotation is never re-rolled.
- Error-fed repair converges in 1–2 tries instead of blind resampling.
- Low temperature (already 0.2 on OpenRouter) for compliance.

### 3.5 Exceptions, regression, monitoring (the scale unlock)

- **Exception queue**: moves that exhaust the repair cap get `review_status = NEEDS_HUMAN`
  and a reason. `6_review.py` shows only these. Target: < ~2% of moves.
- **Golden set**: a small curated set of human-approved annotations; a test runs the
  current prompt/model over their FactSheets and diffs/judges against the golden to catch
  regressions when we change prompts or models.
- **Sampled judging at batch time**: when building many games, run the judge over a random
  N% and report an aggregate quality score + flag outliers. Never read everything.

## 4. What this fixes

- Bug classes 1–4 become **structurally impossible** (facts not LLM-generated).
- Class 5–6 (squares, length) are policed on a 1–2 sentence rationale only → far smaller
  failure surface, and repaired per-field.
- "Stable explanation" = the *fact_line* is identical and correct every run; only the short
  *why* varies, and its worst case is bland.
- Scales: 95%+ auto-converge; humans touch only flagged exceptions; golden + sampling guard
  quality across volume.

## 5. Rollout (incremental, no big-bang)

- **Phase 0** — `build_fact_sheet` + `fact_line` (EN/ZH) in `facts.py` + unit tests. No
  behaviour change yet (compute, don't use). *(small)*
- **Phase 1** — switch the prompt/schema to `rationale`-only; compose final =
  `fact_line + rationale`. Re-run the 2 existing games; compare against current shipped
  prose. *(medium)*
- **Phase 2** — repair loop + `NEEDS_HUMAN` status in `4_annotate`/`store`. *(medium)*
- **Phase 3** — LLM-judge gate + judge rubric + sampled judging report. *(medium)*
- **Phase 4** — golden regression set + CI hook. *(small/ongoing)*

Each phase ships independently; current validator guards stay throughout.

## 6. Cost / metrics

- Templating cuts generated tokens (facts no longer written) → cheaper, faster.
- Per-field repair << whole-game re-roll.
- Judge adds ~1 call per field; gate it to first-pass-failures + the N% sample to bound cost.
- Track: first-pass validator pass-rate, post-repair pass-rate, % flagged NEEDS_HUMAN,
  judge score distribution, tokens/game.

## 7. Open questions for Jerry

- **A. Motifs in fact_line?** Keep `skewer/fork/...` out until the detector is intent-aware,
  or accept geometric labels?
- **B. Store fact_line + rationale separately** (richer app rendering, schema change) or
  compose into one `annotation` string (zero app change)?
- **C. Judge model** — same model (cheap, but correlated blind spots) or a different one
  (less correlated, more cost)?
- **D. NEEDS_HUMAN budget** — what auto-flag rate is acceptable before we treat it as a
  prompt/model problem? (proposed ≤ 2%)
- **E. Alt-move notes** — same fact_line+rationale split, or keep alts fully templated from
  the engine reply line (they are short and the app already templates them in
  `GuessExplainer`)?
```
