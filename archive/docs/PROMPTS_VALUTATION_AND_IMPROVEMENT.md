# PROMPTS VALUTATION AND IMPROVEMENT

## Scope
This document analyzes benchmark results only (reports), without reviewing implementation.

Data used:
- 3 benchmark reports
- 24 prompt-level rows total
- 2 comparable runs on same suite (agentic), 9 paired prompts

Important statistical caveat:
- Current sample is too small for strong global conclusions.
- Findings below are valid as diagnostic signals, not final scientific claims.

---

## 1) Which metrics are actually discriminative

A metric is considered discriminative if it changes meaningfully across prompts/models and helps separate model quality outcomes.

### High practical discrimination
- judge_reasoning
  - high spread and low tie rate in paired prompts (2/9 ties)
  - captures real differences where outputs are both valid format-wise
- judge_overall
  - moderate separation (mean abs delta 0.083 on paired prompts)
  - sensitive mainly on harder prompts (example: TOOL_CALL_003)
- tokens_per_sec (for performance-only comparisons)
  - always changing between models and prompts
  - useful for throughput profiling, not quality ranking
- latency_ms (for performance-only comparisons)
  - high variance across prompts/models
  - useful for cost/speed profiling, not capability score

### Medium discrimination
- judge_accuracy
  - mostly tied (7/9 ties in paired prompts), but still useful on failure prompts
- judge_hallucination_risk
  - mostly tied in this dataset, but can separate when model fabricates

### Context-dependent discrimination
- json_valid
  - discriminative in agentic/compliance tasks only
  - meaningless in non-JSON tasks
- det_overall
  - currently low dynamic range in observed data (0.8 to 1.0)
  - can become discriminative only if deterministic checks are richer and stricter

---

## 2) Which metrics are redundant

Strong redundancy observed:
- total_tokens vs answer_tokens
  - near-perfect correlation (r ~ 0.999)
  - keep one as primary for ranking analysis; keep the other only for diagnostics
- char_count vs answer_tokens/total_tokens/line_count
  - very strong correlation cluster
  - largely same verbosity signal repeated in 3-4 forms
- judge_overall vs judge_accuracy
  - extremely high correlation in this dataset (r ~ 0.993)
  - indicates overall is currently dominated by accuracy judgments

Operational redundancy:
- format_valid
  - constant 1.0 in all observed rows, zero information
- judge_coding
  - constant 0.0 in all observed rows, zero information (at least in analyzed runs)

---

## 3) Which metrics correlate strongly

Observed strong correlations from report data:
- answer_tokens <-> total_tokens: r ~ 0.999
- judge_accuracy <-> judge_overall: r ~ 0.993
- total_tokens <-> char_count: r ~ 0.900
- char_count <-> line_count: r ~ 0.896
- answer_tokens <-> char_count: r ~ 0.894
- total_tokens <-> line_count: r ~ 0.860
- latency_ms <-> answer_tokens/total_tokens/char_count: r ~ 0.70-0.73

Interpretation:
- One verbosity axis is being measured multiple times.
- One subjective quality axis (accuracy/overall) is effectively duplicated.
- Speed metrics partly proxy response length rather than pure model efficiency.

---

## 4) Which metrics should be removed (or demoted)

### Remove from primary benchmark ranking
- format_valid
  - no observed variance, no discrimination value
- judge_coding (outside coding suite)
  - always zero in current analyzed suites
  - should not contribute globally when task type is non-coding
- char_count and line_count (as ranking features)
  - mostly verbosity proxies
  - keep for observability only

### Demote to secondary diagnostics
- prompt_tokens and total_tokens together
  - keep both in raw logs, but avoid double-counting in scoring/analysis
- latency_ms and tokens_per_sec in quality score
  - should be separate performance score, not quality score

### Keep as core quality dimensions
- judge_reasoning
- judge_accuracy
- judge_hallucination_risk (with improved hallucination suite design)
- deterministic correctness metrics (but expanded beyond basic json_valid)

---

## 5) Validity gaps found in current benchmark outcomes

### A) Ceiling effects in agentic suite
- Many prompts produce near-identical top scores for both models.
- Only one prompt (TOOL_CALL_003) creates large separation.
- Implication:
  - Ranking is fragile and highly sensitive to a single item.

### B) Deterministic checks too shallow
- In observed data, deterministic signal often collapses to json_valid only.
- This creates low dynamic range and weak anti-gaming power.

### C) Mixed objective and performance interpretation
- Speed and verbosity metrics are present with strong internal correlations.
- Without strict separation, quality interpretation becomes confounded.

### D) Incomplete category evidence for global conclusions
- Only hallucination + agentic seen in current reports.
- No robust evidence here for coding/general/technical cross-category validity.

---

## 6) Improvement proposals (methodology and benchmark validity)

## Proposal P0 - Metric set simplification
- Define two score families:
  - Quality score: correctness/reasoning/hallucination/compliance semantics
  - Performance score: latency/tokens-per-sec/tokens usage
- Remove non-informative metrics from primary ranking:
  - format_valid
  - judge_coding when suite != coding
  - char_count/line_count as scoring inputs

## Proposal P1 - Anti-redundancy policy
- Keep one primary metric per information axis:
  - verbosity axis: choose total_tokens OR answer_tokens for ranking views
  - subjective axis: keep sub-dimensions, do not let overall duplicate them blindly
- Publish correlation audit per release and prune metrics with |r| > 0.95 unless justified.

## Proposal P2 - Deterministic score expansion
- Replace minimal deterministic checks with richer contracts:
  - JSON schema validity (not only parseability)
  - required field presence/types
  - tool argument grounding checks
  - multi-step tool sequence correctness where needed
- Goal: increase deterministic score dynamic range and reduce judge subjectivity load.

## Proposal P3 - Discriminative prompt redesign
- For each suite, include:
  - easy, medium, hard distribution
  - adversarial/near-miss items
  - paired prompts with similar surface format but different correct actions
- Target: reduce ceiling effects and increase model separation beyond one or two outlier prompts.

## Proposal P4 - Statistical validity protocol
- Do not publish single-number leaderboard without uncertainty.
- Minimum reporting:
  - mean
  - confidence interval
  - effect size vs baseline
  - prompt count per category
- Add rank-stability checks under prompt paraphrase/seed variants.

## Proposal P5 - Category-aware metric applicability
- Apply metrics only where semantically valid:
  - judge_coding contributes only in coding category
  - json_valid contributes only for JSON-constrained tasks
  - hallucination-risk emphasized only where factual uncertainty is task-relevant
- Prevent global score contamination from non-applicable dimensions.

---

## 7) Recommended final metric portfolio

### Keep in primary quality model
- judge_accuracy
- judge_reasoning
- judge_hallucination_risk
- deterministic_contract_score (expanded)
- task_success_binary (strict pass/fail for hard constraints)

### Keep in performance model (separate)
- latency_ms
- tokens_per_sec
- total_tokens (or answer_tokens, choose one as primary)

### Keep only in diagnostics
- char_count
- line_count
- prompt_tokens (unless cost modeling requires it)
- format_valid (until it gains variance)

### Remove from global aggregate unless category-applicable
- judge_coding outside coding suite
- any metric with persistent near-constant behavior across a release

---

## 8) Immediate actions for next benchmark cycle

1. Freeze a reduced metric set for quality ranking and split performance into a separate scoreboard.
2. Add deterministic schema/argument checks to all agentic JSON/tool prompts.
3. Redesign at least 30% of agentic prompts to reduce ceiling effects.
4. Introduce category-aware metric gating before global aggregation.
5. Publish correlation and variance table with every benchmark release.

Expected result:
- higher discriminative power
- lower metric redundancy
- less gaming potential
- stronger objective validity for local LLM comparison
