# PROJECT IMPROVEMENT PLAN

## Purpose
This document captures the architecture/code audit report and concrete fix considerations, without introducing new product features.

## Reference Baseline
The review is aligned against:
- PROJECT_SCHEMA.md
- AGENT.md
- ARCHITECTURE.md
- IMPLEMENTATION_PLAN.md

---

## Executive Summary
The project is solid in structure and provider abstraction intent, but has several correctness and consistency gaps that impact reliability and benchmark trustworthiness.

Current critical path:
1. Fix runtime crashes (charts, stats)
2. Re-align judge schema contract across code/docs
3. Make score pipeline coherent (composite vs judge-only ranking)
4. Restore historical reproducibility guarantees for prompts

---

## Audit Findings And Fix Considerations

### 1) Charts command runtime crash (formatting field mismatch)
- Severity: critical
- Affected files:
  - benchmark/charts.py
  - benchmark/judge.py
  - benchmark/database.py
  - ARCHITECTURE.md
  - IMPLEMENTATION_PLAN.md
- Problem:
  - `radar_chart_model()` reads `JudgeScore.formatting`, but current JudgeScore schema no longer has `formatting`.
  - `python benchmark.py charts --run-id 1` crashes with `AttributeError`.
- Fix options:
  1. Reintroduce `formatting` end-to-end (judge prompt + parser + DB + charts + docs).
  2. Keep current model (no formatting in judge) and remove/replace formatting references in charts/docs.
- Recommended fix:
  - Option 2 (minimal, coherent with deterministic checks owning format validation).
- Considerations:
  - Update radar axis labels to existing metrics only.
  - Ensure charts gracefully handle missing judge scores.

### 2) Stats command uses closed SQLite connection
- Severity: high
- Affected files:
  - benchmark.py
- Problem:
  - In `cmd_stats`, `conn.execute(...)` is called after the `with db._conn() as conn:` block has exited.
  - `python benchmark.py stats` fails at runtime with `sqlite3.ProgrammingError`.
- Recommended fix:
  - Move `last_model` query inside the active context manager block, or open a second connection.
- Considerations:
  - Keep all stats SQL in one connection for consistency and lower overhead.

### 3) Prompt immutability contract is violated
- Severity: high
- Affected files:
  - benchmark/database.py
  - benchmark/report.py
  - IMPLEMENTATION_PLAN.md
- Problem:
  - Plan states prompts are immutable, but `upsert_prompt()` updates existing prompt content on conflict.
  - Reports resolve prompt text by prompt id at read time, so old runs can display modified prompt text.
- Recommended fix:
  - Enforce prompt immutability by id (fail or skip updates for existing ids), OR version prompts explicitly.
  - Persist prompt snapshot text in `benchmark_results` (preferred for historical integrity).
- Considerations:
  - If introducing prompt versioning, migration must be additive and backward compatible.

### 4) Composite score computed but not persisted/used in ranking
- Severity: high
- Affected files:
  - benchmark/runner.py
  - benchmark/scoring.py
  - benchmark/database.py
  - benchmark/report.py
- Problem:
  - Composite score is computed in memory, but DB views and reports rank with judge `overall` only.
  - Deterministic checks influence neither primary ranking nor comparison outputs.
- Recommended fix:
  - Persist composite score per result and use it as canonical ranking metric.
  - Keep judge-only and deterministic-only values as separate columns for traceability.
- Considerations:
  - Migration should add columns/table, not break existing runs.
  - Update report labels to clearly state metric source.

### 5) Judge schema drift between docs and implementation
- Severity: high
- Affected files:
  - ARCHITECTURE.md
  - IMPLEMENTATION_PLAN.md
  - README.md
  - benchmark/judge.py
  - benchmark/database.py
- Problem:
  - Docs still describe a `formatting` judge metric, implementation removed it.
  - Causes confusion and downstream bugs (charts).
- Recommended fix:
  - Choose one canonical schema and align all layers in a single migration/update.
- Considerations:
  - If keeping current schema, explicitly document that format checks are deterministic-only.

### 6) Objective and subjective signals are mixed in one final quality score
- Severity: medium
- Affected files:
  - benchmark/scoring.py
  - AGENT.md
- Problem:
  - `tokens_per_sec` is blended into score used as quality proxy.
  - This mixes performance/hardware effects with response quality.
- Recommended fix:
  - Keep separate outputs:
    - Quality score (subjective + deterministic correctness)
    - Performance score (latency/tokens/sec)
  - Composite score can remain optional and clearly labeled.
- Considerations:
  - Preserve backward compatibility by exposing legacy metric during transition.

### 7) Ollama provider ignores JSON mode input used by judge
- Severity: medium
- Affected files:
  - benchmark/providers/ollama.py
  - benchmark/judge.py
- Problem:
  - Judge passes `response_format={"type":"json_object"}` but Ollama payload ignores it.
  - Deterministic parse reliability is weaker when judge provider is Ollama.
- Recommended fix:
  - Map `response_format` to Ollama JSON mode option where supported.
  - Keep strict parse/retry behavior unchanged.
- Considerations:
  - Add compatibility fallback for Ollama versions lacking exact option semantics.

### 8) Run status can be misleadingly marked completed with partial failures
- Severity: medium
- Affected files:
  - benchmark/runner.py
- Problem:
  - Prompt failures are logged and skipped; run status becomes `completed` if at least one prompt succeeded.
- Recommended fix:
  - Add failure counters and statuses (`completed`, `partial_failed`, `failed`) with clear thresholds.
- Considerations:
  - Reports should display failure ratio to avoid hidden quality bias.

### 9) CLI list commands have side effects and path inconsistency
- Severity: low
- Affected files:
  - benchmark.py
  - benchmark/runner.py
- Problem:
  - `list` command constructs Runner, which initializes DB/imports prompts.
  - Prompt listing path logic may diverge from configured `paths.prompts_dir`.
- Recommended fix:
  - Implement read-only list path/provider utilities independent of Runner side effects.
  - Resolve prompt dir from loaded config consistently.
- Considerations:
  - Preserve current CLI flags and outputs for user familiarity.

---

## Proposed Fix Sequence (No Feature Expansion)

### Phase 0 - Immediate stability hotfixes
- Fix stats closed-connection bug.
- Fix charts formatting mismatch crash.
- Add quick regression checks for `stats` and `charts` commands.

### Phase 1 - Contract alignment
- Decide canonical judge schema.
- Align judge parser, DB dataclasses/schema, charts, report, and design docs in one pass.

### Phase 2 - Scoring correctness
- Persist composite score.
- Update DB views/ranking/report summary to use canonical score definitions.
- Keep judge/deterministic components visible for auditability.

### Phase 3 - Reproducibility hardening
- Enforce prompt immutability or introduce prompt versioning.
- Snapshot prompt text (and deterministic_checks config) in result records.

### Phase 4 - Methodology and CLI reliability
- Separate quality vs performance reporting dimensions.
- Improve run status semantics for partial failures.
- Remove side effects from list commands and harmonize config path resolution.

---

## Validation Checklist

### Runtime
- `python benchmark.py stats` exits code 0.
- `python benchmark.py charts --run-id <id>` exits code 0 and writes PNG files.

### Data correctness
- Ranking metric used in DB views matches metric presented in report summaries.
- Deterministic checks visibly impact the canonical score when configured.
- Historical run report still shows original prompt snapshot after prompt file edits.

### Contract consistency
- Judge schema is identical in:
  - docs (ARCHITECTURE.md, IMPLEMENTATION_PLAN.md, README.md)
  - parser (judge.py)
  - storage model (database.py)
  - chart/report usage

### CLI behavior
- `list` commands do not modify DB state.
- Prompt discovery uses configured `paths.prompts_dir`.

---

## Risk Notes
- Schema changes around scoring and prompt snapshots require additive migrations and backward compatibility checks.
- Re-ranking historical data should be explicitly versioned/documented to avoid silent metric shifts.

---

## Current Scores (from audit)
- Architecture score: 6.2/10
- Code quality score: 6.0/10
- Benchmark methodology score: 5.4/10
- Production readiness score: 5.8/10

Target after phases 0-2: stable runtime and scoring coherence suitable for dependable comparative runs.

---

## Methodology-Only Review (Benchmark Design)

Scope of this section:
- Prompt quality
- Deterministic scoring design
- Judge model design
- Scoring bias
- Hallucination detection
- Compliance evaluation
- Tool-calling evaluation
- Statistical validity

This section intentionally ignores implementation details and focuses only on benchmark methodology quality for objective comparison of local LLMs.

### Methodology Verdict (Extremely Critical)
- The benchmark currently behaves more like a small mixed sanity suite than a statistically robust comparative benchmark.
- It is vulnerable to benchmark gaming through pattern memorization and format-first optimization.
- Hallucination and tool-calling evaluations are under-specified, making both false positives and false negatives likely.
- Prompt count per skill is too small and too homogeneous to support strong objective rankings.

---

## False Positives (Model penalized when actually good)

### FP-1: Exact-match rigidity penalizes semantically correct outputs
- Risk area: instruction compliance, determinism, some reasoning/math prompts.
- Example pattern: model returns "Rex e nero." vs expected "nero" and is penalized despite correctness.
- Why this is a false positive:
  - Compliance signal is conflated with literal string identity rather than task truth.
- Improvement proposal:
  - Split metrics into:
    - strict compliance score (exact output contract)
    - semantic correctness score (content-level correctness)
  - Do not let strict-only failures fully dominate quality ranking.

### FP-2: Hallucination prompts may punish justified forecasting uncertainty styles
- Risk area: future events, unverifiable facts.
- Example pattern: cautious answer with scenario language may still be judged as weak vs ideal "I do not know" style.
- Why this is a false positive:
  - The benchmark rewards a narrow response style rather than calibrated epistemic behavior.
- Improvement proposal:
  - Define acceptable refusal/uncertainty templates as an equivalence class, not a single phrasing.
  - Add rubric dimensions: uncertainty calibration, explicit unverifiability, non-fabrication.

### FP-3: Tool-calling prompts penalize valid multi-step decomposition
- Risk area: tool_calling.
- Example pattern: model proposes two calls when prompt implies compositional workflow, but evaluation expects one tool token.
- Why this is a false positive:
  - Evaluation under-specifies whether planning + execution can be multi-tool.
- Improvement proposal:
  - Add per-prompt contract field:
    - allowed_single_tool
    - allowed_multi_tool
    - required_tool_order (optional)

---

## False Negatives (Model rewarded when actually weak)

### FN-1: JSON-valid outputs can pass despite wrong schema/semantics
- Risk area: json_compliance, tool_calling.
- Why this is a false negative:
  - JSON validity alone does not prove correct structure, required keys, argument types, or intent mapping.
- Improvement proposal:
  - Add deterministic JSON schema validation per prompt.
  - Add argument-level checks (required keys, type, enum constraints).

### FN-2: Reasoning quality can pass with shallow pattern responses
- Risk area: general reasoning and technical explanation prompts.
- Why this is a false negative:
  - Small set of canonical textbook prompts is highly exposed in training corpora.
- Improvement proposal:
  - Expand with adversarial variants, counterfactual versions, and numeric perturbations.
  - Use isomorphic prompt families to test robustness, not only memorized answers.

### FN-3: Hallucination risk under-detected in partial fabrication
- Risk area: hallucination suite.
- Why this is a false negative:
  - Current tasks mainly test blatant fabricated facts; subtle mixed truth + fabrication is not stressed enough.
- Improvement proposal:
  - Add prompts requiring citations or explicit confidence buckets.
  - Include near-plausible fake entities mixed with real entities.

---

## Benchmark Gaming Opportunities

### G-1: Format-over-content optimization
- Models can maximize score by obeying output shape while minimizing substantive quality.
- Proposal:
  - Introduce minimum content adequacy checks (length/rationale constraints where relevant).

### G-2: Refusal-template memorization for hallucination category
- Models can memorize safe refusals and score high without real epistemic competence.
- Proposal:
  - Mix hallucination prompts with answerable adjacent prompts in same category.
  - Evaluate discrimination ability: refuse unknown, answer known.

### G-3: Tool token spoofing
- If evaluation mostly checks presence of tool name, model can emit tool keyword without valid call intent.
- Proposal:
  - Validate full call object contract:
    - selected tool correctness
    - argument grounding from user request
    - no extraneous unsafe actions

### G-4: Prompt leakage from static small pool
- Fixed tiny prompt pool encourages overfitting and repeated-run memorization.
- Proposal:
  - Build templated prompt generators with controlled random seeds.
  - Preserve reproducibility through run-level seed logging.

---

## Weak Prompt Analysis

### W-1: Several prompts are too trivial for model separation
- Examples:
  - one-word capital questions
  - simple trick riddles
  - basic true/false arithmetic
- Impact:
  - Low discrimination power between modern local models.
- Proposal:
  - Replace a portion with medium-hard tasks that produce rank spread.

### W-2: Ambiguous expected answers
- Example pattern:
  - prompts allowing multiple valid formulations but scored as one canonical answer.
- Impact:
  - Inflates variance due to wording preference, not capability.
- Proposal:
  - Define acceptable answer sets or semantic equivalence criteria.

### W-3: Underconstrained architecture prompts
- Architecture questions are open-ended with limited deterministic anchors.
- Impact:
  - Scores become judge-style-sensitive and harder to compare objectively.
- Proposal:
  - Add structured requirements checklist per prompt (must-cover constraints).

### W-4: User category has placeholder-like prompt
- Example:
  - custom prompt instructing user to edit file.
- Impact:
  - Non-evaluable item contaminates suite statistics.
- Proposal:
  - Remove non-task placeholders from benchmark runs.

---

## Missing Benchmark Categories (for objective local LLM comparison)

### M-1: Long-context retrieval and consistency
- Missing capability:
  - maintaining consistency across long inputs and multi-part constraints.

### M-2: Grounded QA with provided context
- Missing capability:
  - distinguishing faithful extraction from hallucinated additions.

### M-3: Robustness to prompt perturbation
- Missing capability:
  - stability under paraphrases, typo noise, reordered constraints.

### M-4: Safety-critical instruction boundaries
- Missing capability:
  - obeying constraints under adversarial framing without over-refusal.

### M-5: Multi-turn state tracking
- Missing capability:
  - conversational memory correctness across turns.

### M-6: Deterministic reproducibility under repeated runs
- Missing capability:
  - explicit run-to-run variance reporting per prompt/model.

---

## Deterministic Scoring Design Critique

### D-1: Deterministic checks are too narrow per task
- Many prompts have none or only one deterministic check.
- Proposal:
  - Require at least one task-specific correctness check where possible.

### D-2: Check composition lacks hierarchy
- Not all checks are equal (schema correctness vs stylistic format).
- Proposal:
  - Define critical vs non-critical checks with asymmetric penalties.

### D-3: Compliance checks are mostly surface-level
- Lowercase/word count/exact text does not guarantee instruction fidelity depth.
- Proposal:
  - Add semantic instruction constraints and contradiction traps.

---

## Judge Model Design Critique

### J-1: Single-judge dependence risks model-specific bias
- A single judge style can systematically prefer certain answer styles.
- Proposal:
  - Use judge-ensemble agreement or rotating judge baselines for audits.

### J-2: Subjective dimensions are under-anchored
- "overall" can dominate without strict anchor descriptions.
- Proposal:
  - Add rubric anchors with concrete score bands and examples.

### J-3: Potential contamination by deterministic summary text
- Informative deterministic check context can anchor judge scoring.
- Proposal:
  - Blind judge from pass/fail outcomes when measuring subjective reasoning quality.
  - Keep deterministic checks as separate channel for final aggregation.

---

## Scoring Bias And Statistical Validity Critique

### S-1: Sample size is too small for stable model ranking
- Current suite sizes per subdomain are low.
- Statistical risk:
  - Rank flips due to few prompts rather than capability differences.
- Proposal:
  - Increase per-category prompt counts and report confidence intervals.

### S-2: No uncertainty reporting
- Means alone are insufficient for objective comparison.
- Proposal:
  - Report variance, bootstrap confidence intervals, and effect sizes.

### S-3: Weighting is judgmental but not calibrated
- Prompt weights appear hand-tuned without validation study.
- Proposal:
  - Calibrate weights using discriminative power and reliability metrics.

### S-4: Category imbalance distorts global score
- Some categories have very few prompts and still influence global ranking.
- Proposal:
  - Use balanced macro-averaging or minimum-sample gating per category.

---

## High-Priority Methodology Improvements (No Feature Bloat)

### P0 - Anti-gaming hardening
- Introduce schema-level deterministic validation for JSON/tool calls.
- Separate strict-format compliance from semantic correctness in scoring.
- Remove placeholder/non-evaluable prompts from scoring sets.

### P1 - Hallucination evaluation upgrade
- Add mixed known/unknown items to test selective refusal.
- Add subtle fabrication scenarios, not only obvious fake/future entities.
- Score calibrated uncertainty explicitly.

### P2 - Statistical reliability upgrade
- Expand prompt bank with seeded variants.
- Publish confidence intervals and per-category reliability indicators.
- Enforce minimum prompt count before claiming category winner.

### P3 - Judge-bias controls
- Define anchored rubrics.
- Run periodic dual-judge calibration audits.
- Monitor agreement and drift over time.

---

## Methodology Acceptance Criteria

Benchmark design can be considered objective-enough for local LLM comparison only when all of the following hold:
- False-positive and false-negative rates are measured on a labeled validation subset.
- Tool-calling tasks validate schema, tool choice, and argument correctness.
- Hallucination tasks include both unknown and known controls with discrimination scoring.
- Each category has sufficient sample size and published uncertainty metrics.
- Global ranking is robust under prompt-paraphrase and seed perturbation tests.

---

## Methodology Execution Roadmap (Versioned)

This roadmap translates methodology proposals into phased deliverables with objective pass/fail criteria.

### v1.2 - Measurement Integrity Baseline

Goal:
- Eliminate the highest-risk benchmark gaming vectors and obvious label-noise causes.

Deliverables:
- Remove or quarantine non-evaluable prompts from scored suites.
- Introduce per-task deterministic schema checks for all JSON/tool-calling prompts.
- Split strict-compliance scoring from semantic-correctness scoring.
- Add known-vs-unknown control pairs in hallucination suite.

KPIs:
- 100% of tool-calling prompts have explicit schema constraints.
- 100% of hallucination prompts are tagged as `known_control` or `unknown_control`.
- At least 80% of instruction prompts have deterministic checks beyond plain exact-match.
- Placeholder/non-task prompts included in scoring: 0.

Go/No-Go Gate:
- NO-GO if any ranked category still contains prompts without evaluable success criteria.

### v1.3 - Robustness And Anti-Gaming Hardening

Goal:
- Reduce susceptibility to pattern memorization and format-only optimization.

Deliverables:
- Build prompt families with isomorphic variants (paraphrase, perturbation, reordered constraints).
- Add mixed easy/medium/hard stratification per category.
- Add adversarial "near-miss" prompts for hallucination and tool selection.
- Add refusal discrimination tests (must refuse unknown, must answer known).

KPIs:
- Minimum 3 variants per critical prompt family.
- Category difficulty mix target: 30% easy, 40% medium, 30% hard.
- Rank stability under paraphrase variants: Spearman >= 0.80 for top-5 models.
- Refusal discrimination accuracy >= 0.85 on hallucination control set.

Go/No-Go Gate:
- NO-GO if rank ordering collapses under minor paraphrase/noise perturbations.

### v1.4 - Statistical Validity Layer

Goal:
- Make rankings statistically defensible, not just point-estimate driven.

Deliverables:
- Report confidence intervals for all core scores (category and global).
- Add bootstrap/effect-size reporting for model comparisons.
- Establish minimum sample thresholds per category before public ranking.
- Publish variance and reliability diagnostics per suite.

KPIs:
- 100% reported aggregate metrics include CI.
- Category ranking shown only when n >= threshold (recommended >= 30 prompts/category).
- Pairwise comparison includes effect size + CI in 100% of comparisons.
- Coefficient of variation tracked for each category and model.

Go/No-Go Gate:
- NO-GO if global leaderboard is published without uncertainty intervals.

### v1.5 - Judge Calibration And Bias Control

Goal:
- Reduce dependence on one judge style and improve subjective score reliability.

Deliverables:
- Add anchored rubric with concrete examples for each score band.
- Run periodic dual-judge calibration batches.
- Track inter-judge agreement and drift over time.
- Define tie-break policy favoring deterministic signals when subjective disagreement is high.

KPIs:
- Inter-judge agreement target: weighted kappa >= 0.70 on calibration set.
- Monthly drift report produced for judge dimensions.
- Subjective disagreement escalation rule defined and enforced.

Go/No-Go Gate:
- NO-GO if subjective ranking relies on uncalibrated single-judge output.

---

## Benchmark Category Coverage Targets

To support objective local-LLM comparison, category inventory should satisfy:
- Hallucination:
  - unknown-only tasks <= 50% of category
  - known-control tasks >= 30%
  - mixed-plausibility tasks >= 20%
- Tool-calling:
  - single-tool tasks <= 50%
  - multi-step tool routing >= 30%
  - argument-grounding checks >= 80% of tasks
- Compliance:
  - surface-format tasks <= 40%
  - semantic-constraint tasks >= 40%
  - contradiction/adversarial tasks >= 20%
- Reasoning/technical/coding:
  - at least 30 prompts per category for stable comparative inference

---

## Statistical Policy For Leaderboards

Leaderboard publication rules:
- Do not publish raw mean-only rankings.
- Publish rank tiers when confidence intervals overlap strongly.
- Mark "insufficient evidence" when sample threshold not met.
- Freeze benchmark set per release; treat revisions as new benchmark versions.

Recommended outputs per release:
- Point estimate
- 95% CI
- Effect size vs baseline model
- Prompt-count coverage and category reliability flag

---

## Short-Term Action Backlog (Methodology Only)

1. Curate and relabel current prompt inventory into evaluable/non-evaluable.
2. Add deterministic schema contracts to all agentic JSON/tool tasks.
3. Add hallucination control pairs and refusal discrimination labels.
4. Create first paraphrase-robust prompt families in 3 categories.
5. Define and publish statistical minimums before leaderboard use.

Expected outcome:
- Transition from "small mixed sanity suite" to "defensible comparative benchmark" for local LLMs.
