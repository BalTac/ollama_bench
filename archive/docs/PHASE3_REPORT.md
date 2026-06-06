# PHASE 3 REPORT

## Scope executed
- M05 JSON semantic validation
- M06 Tool semantic validation
- M20 Strict compliance vs semantic correctness separation

Only Phase 3 scope was implemented.

---

## 1) Files changed

Core logic:
- benchmark/deterministic_scoring.py
- benchmark/database.py
- benchmark/runner.py
- benchmark/report.py

Prompt enablement:
- prompts/agentic/tool_calling.json
- prompts/agentic/instruction_compliance.json

---

## 2) Schema changes

### `deterministic_scores` (additive)
Added new deterministic dimensions:
- `allowed_values` REAL
- `forbidden_text` REAL
- `required_json_keys` REAL
- `tool_sequence` REAL
- `strict_compliance` REAL
- `semantic_correctness` REAL

No destructive schema changes were applied.

---

## 3) Migration requirements

Migration style:
- Backward-compatible additive migrations only

Applied migration operations:
- `ALTER TABLE deterministic_scores ADD COLUMN ...` (6 new columns)

Compatibility notes:
- Existing rows remain valid (new fields are nullable).
- Existing deterministic logic still works for legacy prompts.
- New checks are opt-in through `deterministic_checks` in prompt definitions.

---

## 4) Runtime/logic changes

### M05 - JSON semantic validation
Implemented:
- `required_json_keys` check

Behavior:
- Parses JSON response (including extracted JSON blocks).
- Verifies required keys presence on top-level object.
- Returns partial credit when only a subset of required keys is present.

### M06 - Tool semantic validation
Implemented:
- `tool_sequence` check

Behavior:
- Extracts ordered tool sequence from common formats (`tool`, `action`, `function`, `name`, and `tool_calls`).
- Compares against expected ordered sequence.
- Returns partial credit on ordered prefix match.

### M20 - Strict vs semantic separation
Implemented:
- `strict_compliance` aggregate score
- `semantic_correctness` aggregate score

Aggregation policy:
- Strict checks: `exact_match`, `allowed_values`, `forbidden_text`, `json_valid`, `required_json_keys`, `format_valid`, `regex_match`
- Semantic checks: `expected_tools`, `tool_sequence`, `expected_keywords`

Persistence/reporting:
- New fields are written to DB and exported in JSON/CSV report outputs.
- Runner now includes strict/semantic values in deterministic context shown to judge.

---

## 5) Prompt updates for activation

### `prompts/agentic/tool_calling.json`
- `AGENTIC_001`: added `required_json_keys` (`tool`, `args`)
- `AGENTIC_003`: added `json_valid`, `required_json_keys(action)`, strict regex for allowed JSON outputs
- `TOOL_CALL_003`: updated prompt to explicit `tool_calls` list format and added checks:
  - `json_valid`
  - `required_json_keys(tool_calls)`
  - `tool_sequence([calculate, send_email])`
  - `expected_tools([calculate])`

### `prompts/agentic/instruction_compliance.json`
- Added deterministic strict checks to both prompts:
  - `exact_match`
  - `allowed_values`

---

## 6) Tests performed

### Static validation
- Workspace errors check on changed code files: PASS (no errors)

### CLI smoke validation
Command:
- `python benchmark.py stats`

Result:
- PASS
- No crashes after schema and reporting updates

### Deterministic logic validation (targeted snippet)
Executed deterministic scoring directly with synthetic JSON/tool response.

Result:
- PASS
- Expected output observed:
  - `overall = 1.0`
  - `strict_compliance = 1.0`
  - `semantic_correctness = 1.0`
  - `required_json_keys = 1.0`
  - `tool_sequence = 1.0`
  - `expected_tools = 1.0`

### DB migration validation
Checked `PRAGMA table_info(deterministic_scores)` after initialization.

Result:
- PASS
- All new columns present: `allowed_values`, `forbidden_text`, `required_json_keys`, `tool_sequence`, `strict_compliance`, `semantic_correctness`

### Full run status
A full `agentic` run was started but manually interrupted because the provider call remained long-running in this session.

Impact:
- End-to-end live scoring for the full suite was not fully completed in this phase report.
- Core deterministic logic and migration paths were validated independently.

---

## 7) Expected benchmark impact

- Better discrimination between:
  - strict instruction/format compliance
  - semantic task correctness
- More robust evaluation for tool-calling prompts with multi-step execution intent.
- Better forensic analysis in reports through explicit strict/semantic deterministic dimensions.
- No regression to legacy prompts that do not define new checks.

---

## Stop condition
Phase 3 completed and stopped as requested.
Awaiting approval before starting Phase 4.
