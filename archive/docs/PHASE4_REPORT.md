# PHASE 4 REPORT

## Scope executed
- A06 separazione quality/performance
- A08 semantica stato run con fallimenti parziali
- A09 `list` read-only senza side effects e path prompt da config

Only Phase 4 scope was implemented.

---

## 1) Files changed

Core scoring/status:
- benchmark/scoring.py
- benchmark/runner.py
- benchmark/database.py

CLI reliability:
- benchmark.py

Reporting:
- benchmark/report.py

---

## 2) Schema changes

- Nessuna modifica distruttiva.
- Nessuna nuova tabella/colonna richiesta in questa fase.

Nota:
- È stato introdotto il nuovo valore di stato run `partial_failed` nel campo esistente `benchmark_runs.status`.

---

## 3) Migration requirements

Migration style:
- Backward-compatible only

Applied migrations:
- Nessuna migration SQL addizionale.

Compatibility notes:
- `status='partial_failed'` è compatibile con schema attuale (`TEXT`).
- `completed_at` viene ora valorizzato anche per `partial_failed`.

---

## 4) Runtime/logic changes

### A06 - Quality vs performance separation
Implemented in `benchmark/scoring.py`:
- Rimosso il contributo `tokens_per_sec` dal punteggio qualità canonico.
- Nuovi output separati per prompt:
  - `quality_score` (usato per ranking/canonical score)
  - `performance_score` (dimensione separata, non usata nel ranking qualità)
- `weighted_score` ora = `quality_score * weight`.

Weighting quality:
- Con deterministic checks: `0.45 * deterministic + 0.55 * judge_overall`
- Senza deterministic checks: `judge_overall`

### A08 - Run status semantics
Implemented in `benchmark/runner.py` + `benchmark/database.py`:
- Nuova semantica finale run:
  - `failed` se `completed == 0`
  - `partial_failed` se `0 < completed < total`
  - `completed` se `completed == total`
- Esposizione nel risultato suite:
  - `failed_prompts`
  - `failure_ratio`
- `update_run_status()` valorizza `completed_at` anche per `partial_failed`.

### A09 - CLI list reliability
Implemented in `benchmark.py`:
- `cmd_list` non inizializza più `Runner`.
- Rimozione side effects su DB/import prompt nei comandi `list`.
- Caricamento config diretto (`yaml.safe_load`) per risolvere:
  - provider default
  - `paths.prompts_dir`
- Risoluzione path prompt armonizzata su `config.yaml` (`paths.prompts_dir`), con supporto path relativo/assoluto.

### Reporting alignment
Implemented in `benchmark/report.py`:
- JSON run block include:
  - `failed_prompts`
  - `failure_ratio`
- JSON summary include:
  - `avg_quality_score`
  - `avg_performance_score`
- HTML summary card mostra:
  - `Quality Score`
  - `Performance Score`
  - prompt falliti con ratio
  - stato run
- Persistenza composite marcata come `scoring_version="v2_quality_only"`.

---

## 5) Tests performed

### Static validation
- `get_errors` sui file modificati: PASS (no errors)

### CLI smoke tests
Commands:
- `python benchmark.py list --prompts --category agentic`
- `python benchmark.py list --providers`
- `python benchmark.py stats`

Result:
- PASS
- Comandi `list` eseguiti senza inizializzazione `Runner`/DB side effects.
- `stats` mostra nuovo conteggio run parziali.

### Scoring separation validation
Targeted snippet executed on `compute_score` with stesso judge e token/s diversi.

Observed:
- `quality_score` invariato al variare di `tokens_per_sec`
- `performance_score` varia correttamente

Result:
- PASS

### Partial-failure status validation
Targeted suite execution con provider fake (un prompt fallito intenzionalmente):
- `status='partial_failed'`
- `completed=6`, `failed=1`, `total=7`, `failure_ratio=0.143`

Result:
- PASS

### Report generation validation
Command:
- `python benchmark.py report --run-id 9 --format all`

Result:
- PASS
- Generati:
  - `reports/report_9.json`
  - `reports/report_9.csv`
  - `reports/report_9.html`
- JSON contiene `failure_ratio` e `scoring_version="v2_quality_only"`.

---

## 6) Expected benchmark impact

- Migliore correttezza metodologica:
  - qualità del contenuto non contaminata da throughput hardware.
- Migliore trasparenza operativa:
  - run parzialmente fallite non classificate come completate.
- Migliore affidabilità CLI:
  - `list` non produce side effects su DB/import.
- Migliore leggibilità report:
  - separazione esplicita quality/performance e failure ratio.

---

## Notes

- Durante la validazione è stata creata una run tecnica di test (`run_id=9`, modello `phase4-fake-model`) per verificare `partial_failed` e reporting.

---

## Stop condition
Phase 4 completed and stopped as requested.
Awaiting approval before starting Phase 5.
