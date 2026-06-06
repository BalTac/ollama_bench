# PHASE 2 REPORT

## Scope executed
- A04 Prompt immutability
- A05 Canonical composite score persistence

Only Phase 2 scope was implemented.

---

## 1) Files changed

- benchmark/database.py
- benchmark/runner.py
- benchmark/report.py

---

## 2) Schema changes

### `benchmark_results` (additive)
Added snapshot fields for historical reproducibility:
- `prompt_snapshot_text` TEXT
- `expected_answer_snapshot` TEXT
- `deterministic_checks_snapshot` TEXT

### New table `composite_scores` (additive)
- `id` INTEGER PK
- `result_id` INTEGER UNIQUE FK -> `benchmark_results.id`
- `composite_score` REAL NOT NULL
- `judge_overall` REAL NOT NULL
- `deterministic_overall` REAL NULL
- `prompt_weight` REAL NOT NULL DEFAULT 1.0
- `scoring_version` TEXT NOT NULL DEFAULT 'v1'
- `created_at` TEXT default now

### New index
- `idx_composite_result` on `composite_scores(result_id)`

### Views updated to canonical composite ranking
- `v_model_scores` now exposes `avg_composite = COALESCE(AVG(cs.composite_score), AVG(js.overall))`
- `v_model_ranking.overall_rank` now uses `AVG(avg_composite)`
- Backward fallback retained via `COALESCE(..., AVG(js.overall))`

---

## 3) Migration requirements

Migration style:
- Backward-compatible additive migrations only
- No destructive table changes

Applied migration operations:
- `ALTER TABLE benchmark_results ADD COLUMN ...` for 3 snapshot fields
- `CREATE TABLE IF NOT EXISTS composite_scores ...`
- `CREATE INDEX IF NOT EXISTS idx_composite_result ...`
- `DROP VIEW IF EXISTS` + recreate `v_model_scores` and `v_model_ranking` to align canonical ranking

Notes:
- Existing historical data remains valid.
- Existing runs without composite rows continue to work through fallback logic.

---

## 4) Tests performed

### Static validation
- Workspace errors check: PASS (`get_errors` -> no errors)

### End-to-end run validation
Command:
- `python benchmark.py run --model gpt-oss:20b --suite instruction_following`

Result:
- PASS
- Run completed (`run_id=5`, 7/7 prompts)
- Auto reports generated (`report_5.json`, `report_5.csv`, `report_5.html`)

### DB persistence validation
Query checks on `run_id=5`:
- rows in run: 7
- rows with `prompt_snapshot_text`: 7/7
- rows with `expected_answer_snapshot`: 4/7 (expected: only prompts with expected answer)
- rows with `deterministic_checks_snapshot`: 3/7 (expected: only prompts with deterministic checks)
- rows with persisted composite score: 7/7

### Report validation
- `report_5.json` now includes:
  - `prompt_snapshot` (prompt, expected_answer, deterministic_checks)
  - `composite_score` block per prompt
- `report_5.csv` now includes:
  - `composite_score`, `composite_judge_overall`, `composite_det_overall`, `composite_weight`

### Ranking view validation
Verified via SQLite metadata:
- `v_model_scores` contains `avg_composite` with fallback to judge overall
- `v_model_ranking.overall_rank` uses composite-based aggregation

---

## 5) Expected benchmark impact

### Reliability
- Historical benchmark rows are now self-contained for prompt content and deterministic config.
- Future prompt edits no longer invalidate historical report interpretation.

### Methodological correctness
- Canonical score is now persisted, not only computed in memory.
- Ranking views can consistently use composite score where available.

### Backward compatibility
- Existing runs remain queryable.
- Runs without composite data still rank/report via judge fallback.

---

## Implementation notes

Prompt immutability handling in this phase includes:
- Result-level immutable snapshots (primary guarantee for historical reproducibility).
- Prompt import conflict policy changed to `ON CONFLICT(id) DO NOTHING` to avoid mutating existing prompt definitions by ID.

---

## Stop condition
Phase 2 completed and stopped as requested.
Awaiting approval before starting Phase 3.
