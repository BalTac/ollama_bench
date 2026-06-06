# CHANGELOG

## 2026-06-06

### Stabilita runtime e allineamento schema (Fase 1)
- Fix crash `charts` dovuto a riferimento obsoleto a `formatting`.
- Fix crash `stats` per uso connessione SQLite fuori contesto.
- Allineata documentazione al judge schema canonico:
  - `accuracy`, `reasoning`, `coding`, `hallucination_risk`, `overall`, `notes`.

### Riproducibilita e scoring canonico (Fase 2)
- Persistenza snapshot prompt in `benchmark_results`:
  - `prompt_snapshot_text`, `expected_answer_snapshot`, `deterministic_checks_snapshot`.
- Introdotta tabella `composite_scores` e ranking canonico su score composito.
- Aggiornate viste `v_model_scores` e `v_model_ranking` con fallback retrocompatibile.

### Hardening deterministico (Fase 3)
- Aggiunti check deterministici avanzati:
  - `required_json_keys`, `tool_sequence`, `allowed_values`, `forbidden_text`.
- Introdotta separazione `strict_compliance` vs `semantic_correctness`.
- Persistenza e reporting dei nuovi campi deterministici.
- Aggiornati prompt agentic per attivare i nuovi check.

### Metodologia e affidabilita CLI (Fase 4)
- Separazione quality/performance nello scoring:
  - quality score canonico separato da performance score.
- Nuova semantica run:
  - `completed`, `partial_failed`, `failed`.
- `list` reso read-only (senza side effects DB/import).
- Allineamento reporting su quality/performance e failure ratio.

### Coerenza JSON mode cross-provider (Fase 5)
- Provider Ollama aggiornato per rispettare `response_format={"type":"json_object"}`
  con `format: "json"` su `/api/generate`.

### Policy minima validita statistica (Fase 6)
- Introduzione policy minima negli output:
  - soglia minima prompt completati,
  - soglia raccomandata,
  - warning su failure ratio elevato.
- Esposizione policy in:
  - `stats` CLI,
  - report JSON,
  - report HTML,
  - comparison HTML.

### Hotfix post-fasi
- Fix `clean --all`:
  - risolto errore FK includendo cleanup `composite_scores`.
  - risolto errore `VACUUM` eseguito dentro transazione.
  - aggiornato messaggio scope pulizia.
