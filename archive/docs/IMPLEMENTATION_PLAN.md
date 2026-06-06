# IMPLEMENTATION_PLAN.md

# LLM Benchmark Framework — Implementation Plan

Version: 1.1
Status: DRAFT — awaiting approval

---

## 1. Directory Structure

```
ollama_bench/                        ← root progetto
├── .gitignore
├── README.md
├── requirements.txt
├── config.yaml                      ← configurazione centrale
├── benchmark.py                     ← entry point CLI
├── AGENT.md                         ← guida comportamentale
├── ARCHITECTURE.md                  ← specifica tecnica
├── PROJECT_SCHEMA.md                ← visione e design
├── IMPLEMENTATION_PLAN.md           ← questo file
│
├── benchmark/                       ← package Python
│   ├── __init__.py
│   ├── runner.py                    ← orchestrazione benchmark
│   ├── judge.py                     ← modello giudice (provider-agnostic)
│   ├── metrics.py                   ← estrazione metriche oggettive
│   ├── scoring.py                   ← calcolo scoring composito
│   ├── prompts.py                   ← caricamento e validazione prompt
│   ├── database.py                  ← layer SQLite (schema + CRUD)
│   ├── report.py                    ← generazione report JSON/CSV/HTML
│   ├── charts.py                    ← generazione grafici (matplotlib)
│   │
│   └── providers/                   ← astrazione multi-provider
│       ├── __init__.py
│       ├── base.py                  ← BaseProvider (ABC) + ProviderResponse
│       ├── ollama.py                ← OllamaProvider
│       ├── deepseek.py              ← DeepSeekProvider
│       └── openrouter.py            ← OpenRouterProvider
│
├── prompts/                         ← prompt organizzati per directory
│   ├── general/
│   │   ├── reasoning.json
│   │   ├── knowledge.json
│   │   └── summarization.json
│   ├── technical/
│   │   ├── mathematics.json
│   │   ├── physics.json
│   │   ├── computer_science.json
│   │   └── statistics.json
│   ├── coding/
│   │   ├── python.json
│   │   ├── debugging.json
│   │   ├── sql.json
│   │   ├── regex.json
│   │   └── architecture.json
│   ├── agentic/
│   │   ├── json_compliance.json
│   │   ├── tool_calling.json
│   │   ├── instruction_compliance.json
│   │   └── determinism.json
│   ├── hallucination/
│   │   ├── future_events.json
│   │   ├── fake_products.json
│   │   └── unverifiable_facts.json
│   ├── instruction_following/
│   │   ├── format_constraints.json
│   │   ├── word_count.json
│   │   └── exact_match.json
│   └── user/
│       ├── telegram_bot.json
│       ├── orchestrator.json
│       ├── ollama_logs.json
│       └── custom.json
│
├── db/
│   └── benchmark.db                 ← SQLite (creato automaticamente)
│
├── exports/                         ← export intermedi
│
├── reports/                         ← output report
│
└── charts/                          ← output grafici
```

---

## 2. File Creation Checklist

| # | File | Fase | Descrizione |
|---|---|---|---|
| 1 | `.gitignore` | 0 | Esclusioni: `__pycache__/`, `*.db`, `*.pyc`, `exports/`, `reports/`, `charts/` |
| 2 | `requirements.txt` | 0 | Dipendenze Python |
| 3 | `config.yaml` | 0 | Configurazione provider, judge, path, timeout |
| 4 | `README.md` | 8 | Documentazione utente finale |
| 5 | `benchmark.py` | 8 | CLI principale (argparse) |
| 6 | `benchmark/__init__.py` | 0 | Package init vuoto |
| 7 | `benchmark/providers/__init__.py` | 2 | Provider factory |
| 8 | `benchmark/providers/base.py` | 2 | `BaseProvider` (ABC) + `ProviderResponse` dataclass |
| 9 | `benchmark/providers/ollama.py` | 2 | `OllamaProvider` |
| 10 | `benchmark/providers/deepseek.py` | 2 | `DeepSeekProvider` |
| 11 | `benchmark/providers/openrouter.py` | 2 | `OpenRouterProvider` |
| 12 | `benchmark/database.py` | 1 | Schema DDL + CRUD operations |
| 13 | `benchmark/prompts.py` | 3 | Caricamento prompt da directory JSON |
| 14 | `benchmark/metrics.py` | 3 | Estrazione metriche oggettive dalla risposta |
| 15 | `benchmark/judge.py` | 4 | Giudice provider-agnostic |
| 16 | `benchmark/scoring.py` | 4 | Calcolo score pesato per categoria |
| 17 | `benchmark/runner.py` | 5 | Orchestrazione benchmark |
| 18 | `benchmark/report.py` | 6 | Report JSON, CSV, HTML |
| 19 | `benchmark/charts.py` | 7 | Grafici matplotlib |
| 20-26 | `prompts/general/*.json` | 0 | Prompt categoria general (seed da prompts.json) |
| 27-30 | `prompts/technical/*.json` | 0 | Prompt categoria technical (placeholder) |
| 31-35 | `prompts/coding/*.json` | 0 | Prompt categoria coding (seed da prompts.json) |
| 36-39 | `prompts/agentic/*.json` | 0 | Prompt categoria agentic (seed da prompts.json) |
| 40-42 | `prompts/hallucination/*.json` | 0 | Prompt categoria hallucination (seed da prompts.json) |
| 43-45 | `prompts/instruction_following/*.json` | 0 | Prompt categoria instruction_following (seed da prompts.json) |
| 46-49 | `prompts/user/*.json` | 0 | Prompt categoria user (placeholder) |

**Totale: 49 file da creare.**

---

## 3. Dependencies

```text
# requirements.txt
pyyaml>=6.0           # parsing config.yaml
requests>=2.31        # HTTP client (Ollama + API remote)
matplotlib>=3.8       # generazione grafici
```

Tutto il resto è Python stdlib:

`sqlite3`, `json`, `csv`, `argparse`, `logging`, `pathlib`, `dataclasses`, `typing`, `datetime`, `statistics`, `abc`, `os`, `re`, `time`

---

## 4. SQLite Schema

```sql
-- ============================================
-- Modelli testati
-- ============================================
CREATE TABLE models (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,              -- es. "qwen2.5:32b"
    provider      TEXT NOT NULL,             -- "ollama" | "deepseek" | "openrouter"
    quantization  TEXT,                       -- es. "Q4_K_M" (solo Ollama)
    parameters    TEXT,                       -- es. "32B"
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, provider, quantization)
);

-- ============================================
-- Sessione benchmark (una run)
-- ============================================
CREATE TABLE benchmark_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id         INTEGER NOT NULL REFERENCES models(id),
    target_provider  TEXT NOT NULL,           -- provider del modello testato
    suite            TEXT NOT NULL,           -- categoria (general, coding, ...)
    judge_model      TEXT NOT NULL,           -- nome modello giudice
    judge_provider   TEXT NOT NULL,           -- provider del giudice
    started_at       TEXT NOT NULL,
    completed_at     TEXT,
    status           TEXT NOT NULL DEFAULT 'running',  -- running|completed|failed
    total_prompts    INTEGER DEFAULT 0,
    completed_prompts INTEGER DEFAULT 0
);

-- ============================================
-- Prompt (immutabili, caricati da JSON)
-- ============================================
CREATE TABLE prompts (
    id               TEXT PRIMARY KEY,         -- es. "CODING_001"
    category         TEXT NOT NULL,            -- general|technical|coding|agentic|...
    subcategory      TEXT NOT NULL,            -- es. "python", "debugging"
    weight           REAL NOT NULL DEFAULT 1.0,
    prompt_text      TEXT NOT NULL,
    expected_format  TEXT,
    expected_answer  TEXT,
    expected_behavior TEXT
);

-- ============================================
-- Risultato singolo prompt
-- ============================================
CREATE TABLE benchmark_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES benchmark_runs(id),
    prompt_id       TEXT NOT NULL REFERENCES prompts(id),
    model_id        INTEGER NOT NULL REFERENCES models(id),
    response_text   TEXT NOT NULL,
    latency_ms      REAL NOT NULL,
    prompt_tokens   INTEGER,
    thinking_tokens INTEGER,
    answer_tokens   INTEGER,
    total_tokens    INTEGER,
    tokens_per_sec  REAL,
    char_count      INTEGER,
    line_count      INTEGER,
    json_valid      INTEGER,                  -- 0/1
    format_valid    INTEGER,                  -- 0/1
    executed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================
-- Valutazione giudice
-- ============================================
CREATE TABLE judge_scores (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id         INTEGER NOT NULL UNIQUE REFERENCES benchmark_results(id),
    judge_model       TEXT NOT NULL,
    judge_provider    TEXT NOT NULL,
    accuracy          REAL NOT NULL,           -- 0.0 - 1.0
    reasoning         REAL NOT NULL,
    coding            REAL NOT NULL,
    hallucination_risk REAL NOT NULL,
    overall           REAL NOT NULL,
    notes             TEXT,
    retry_count       INTEGER DEFAULT 0,
    evaluated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================
-- Indici
-- ============================================
CREATE INDEX idx_results_run ON benchmark_results(run_id);
CREATE INDEX idx_results_model ON benchmark_results(model_id);
CREATE INDEX idx_results_prompt ON benchmark_results(prompt_id);
CREATE INDEX idx_scores_result ON judge_scores(result_id);
CREATE INDEX idx_runs_model ON benchmark_runs(model_id);
CREATE INDEX idx_runs_suite ON benchmark_runs(suite);
CREATE INDEX idx_models_provider ON models(provider);

-- ============================================
-- Viste utili per reporting
-- ============================================
CREATE VIEW v_model_scores AS
SELECT
    m.name AS model_name,
    m.provider,
    m.quantization,
    br.suite,
    br.judge_model,
    AVG(js.overall) AS avg_overall,
    AVG(js.accuracy) AS avg_accuracy,
    AVG(js.reasoning) AS avg_reasoning,
    AVG(js.coding) AS avg_coding,
    AVG(js.hallucination_risk) AS avg_hallucination_risk,
    AVG(br_e.latency_ms) AS avg_latency_ms,
    AVG(br_e.tokens_per_sec) AS avg_tokens_per_sec,
    COUNT(*) AS prompt_count
FROM models m
JOIN benchmark_results br_e ON br_e.model_id = m.id
JOIN benchmark_runs br ON br_e.run_id = br.id
JOIN judge_scores js ON js.result_id = br_e.id
GROUP BY m.name, m.provider, m.quantization, br.suite, br.judge_model;

CREATE VIEW v_model_ranking AS
SELECT
    model_name,
    provider,
    quantization,
    AVG(avg_overall) AS overall_rank,
    AVG(avg_latency_ms) AS avg_latency_ms,
    AVG(avg_tokens_per_sec) AS avg_tokens_per_sec,
    SUM(prompt_count) AS total_prompts
FROM v_model_scores
GROUP BY model_name, provider, quantization;
```

---

## 5. config.yaml Template

```yaml
# LLM Benchmark Framework — Configurazione
# Version: 1.1

# Provider
providers:
  ollama:
    base_url: "http://localhost:11434"
    timeout: 120

  deepseek:
    base_url: "https://api.deepseek.com"
    api_key: "${DEEPSEEK_API_KEY}"
    timeout: 120

  openrouter:
    base_url: "https://openrouter.ai/api/v1"
    api_key: "${OPENROUTER_API_KEY}"
    timeout: 120

# Giudice
judge:
  provider: deepseek           # ollama | deepseek | openrouter
  model: deepseek-chat
  max_retries: 1

# Path
paths:
  prompts_dir: "prompts"
  db_path: "db/benchmark.db"
  reports_dir: "reports"
  charts_dir: "charts"
  exports_dir: "exports"

# Benchmark defaults
benchmark:
  default_provider: ollama
  default_suite: all           # all | general | technical | coding | agentic | hallucination | instruction_following | user

# Logging
logging:
  level: INFO                  # DEBUG | INFO | WARNING | ERROR
  file: "benchmark.log"
```

---

## 6. Implementation Roadmap

### Fase 0 — Scaffolding
**File creati:** `.gitignore`, `requirements.txt`, `config.yaml`, `benchmark/__init__.py`, `prompts/` (tutte directory + file JSON seed)

- [ ] Creare struttura directory completa
- [ ] `.gitignore` con esclusioni standard Python + `*.db`
- [ ] `requirements.txt` con 3 dipendenze
- [ ] `config.yaml` con valori default
- [ ] Spacchettare `prompts.json` esistente nei file per categoria/sottocategoria
- [ ] Creare file placeholder per categorie senza dati (`technical/`, `user/`)

---

### Fase 1 — Database Layer
**File creati:** `benchmark/database.py`

- [ ] Schema DDL (tabelle + indici + viste)
- [ ] `init_db(db_path)` — crea schema se non esiste
- [ ] `get_connection()` — context manager per connessioni
- [ ] CRUD models: `upsert_model()`, `get_model()`, `list_models()`
- [ ] CRUD runs: `create_run()`, `update_run_status()`, `get_run()`, `list_runs()`
- [ ] CRUD prompts: `upsert_prompt()`, `get_prompt()`, `list_prompts_by_category()`
- [ ] CRUD results: `insert_result()`, `get_results_by_run()`
- [ ] CRUD scores: `insert_score()`, `get_scores_by_run()`
- [ ] Query ranking: `get_model_ranking()`, `get_historical_trend()`
- [ ] Import prompt: `import_prompts_from_dir(prompts_dir)`

---

### Fase 2 — Provider Layer
**File creati:** `benchmark/providers/__init__.py`, `base.py`, `ollama.py`, `deepseek.py`, `openrouter.py`

- [ ] `ProviderResponse` dataclass
- [ ] `BaseProvider` ABC con `generate()`, `list_models()`, `is_available()`
- [ ] `OllamaProvider` — HTTP POST a `/api/generate`, parsing risposta
- [ ] `DeepSeekProvider` — HTTP POST a chat completions endpoint
- [ ] `OpenRouterProvider` — HTTP POST a OpenRouter API
- [ ] `get_provider(name, config)` factory function in `__init__.py`
- [ ] Gestione errori HTTP, timeout, retry
- [ ] Test: `is_available()` per ogni provider

---

### Fase 3 — Prompt Loader + Metrics
**File creati:** `benchmark/prompts.py`, `benchmark/metrics.py`

- [ ] `load_prompts(prompts_dir)` — carica tutti i JSON ricorsivamente
- [ ] `validate_prompt(prompt_dict)` — valida schema obbligatorio
- [ ] `get_prompts_by_category(prompts_dir, category)` — filtro per suite
- [ ] `extract_metrics(response, latency_ms)` — estrae: token count, char, lines, json_valid, format_valid
- [ ] `is_valid_json(text)` — verifica JSON validity
- [ ] `check_format_compliance(text, expected_format)` — verifica formato atteso

---

### Fase 4 — Judge + Scoring
**File creati:** `benchmark/judge.py`, `benchmark/scoring.py`

- [ ] `Judge(provider, model, max_retries=1)` — costruttore
- [ ] `Judge.evaluate(prompt, response)` — invia a giudice, restituisce `JudgeScore`
- [ ] Parsing JSON risposta giudice con retry
- [ ] `compute_score(metrics, judge_score, prompt_weight)` — score composito
- [ ] `compute_suite_score(scores)` — aggregazione per suite
- [ ] Gestione errore: JSON invalido → retry 1x → errore loggato

---

### Fase 5 — Runner (Orchestrazione)
**File creati:** `benchmark/runner.py`

- [ ] `Runner(config)` — inizializza provider, judge, db
- [ ] `Runner.run_benchmark(model, provider, suite)` — loop principale
- [ ] Per ogni prompt: genera → estrai metriche → giudica → calcola score → persisti
- [ ] Crash-safe: ogni risultato salvato immediatamente dopo evaluation
- [ ] Progress logging con `logging` (non `print`)
- [ ] `Runner.run_all_suites(model, provider)` — esegue tutte le suite
- [ ] `Runner.compare_models(models)` — confronto multi-modello

---

### Fase 6 — Report
**File creati:** `benchmark/report.py`

- [ ] `generate_json_report(run_id, output_path)` — report JSON strutturato
- [ ] `generate_csv_report(run_id, output_path)` — export CSV
- [ ] `generate_html_report(run_id, output_path)` — report HTML standalone
- [ ] `generate_comparison_report(model_ids, output_path)` — confronto HTML
- [ ] Template HTML inline (nessuna dipendenza esterna)

---

### Fase 7 — Charts
**File creati:** `benchmark/charts.py`

- [ ] `ChartGenerator(output_dir)`
- [ ] `bar_chart_ranking(title, data, output_path)` — bar chart ranking
- [ ] `line_chart_trend(title, data, output_path)` — trend storico
- [ ] `radar_chart_model(title, model_data, output_path)` — radar per metriche
- [ ] `generate_all_charts(run_id)` — generazione batch
- [ ] Output PNG 1200×800, DPI 100

---

### Fase 8 — CLI
**File creati:** `benchmark.py`

- [ ] Argparse con subcommands
- [ ] `benchmark.py run --model MODEL [--provider ollama] [--suite coding]`
- [ ] `benchmark.py compare --models m1,m2[,m3] [--suite coding]`
- [ ] `benchmark.py list --models`
- [ ] `benchmark.py list --providers`
- [ ] `benchmark.py list --prompts [--category coding]`
- [ ] `benchmark.py report --run-id ID [--format json|csv|html]`
- [ ] `benchmark.py charts --run-id ID`
- [ ] `benchmark.py import-prompts`
- [ ] Help text in italiano

---

### Fase 9 — Polish & README
**File creati:** `README.md`

- [ ] README completo con esempi
- [ ] Validazione edge case (prompt vuoti, model offline, API key mancante)
- [ ] Logging uniforme in tutti i moduli
- [ ] Docstring in tutti i moduli pubblici
- [ ] Test manuale: eseguire 1 benchmark Ollama → report HTML

---

## 7. Data Flow (Dettaglio)

```
┌─────────────────────────────────────────────────────────┐
│                       benchmark.py                       │
│                      (CLI argparse)                      │
└──────────┬──────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────┐
│                     Runner.run_benchmark()                │
│                                                          │
│  1. Carica prompt per suite                               │
│  2. Per ogni prompt:                                      │
│     ┌──────────────────────────────────────────────┐     │
│     │ a. Provider.generate(prompt) → response       │     │
│     │ b. Metrics.extract(response) → metrics        │     │
│     │ c. Judge.evaluate(prompt, response) → score   │     │
│     │ d. Scoring.compute(metrics, score) → final    │     │
│     │ e. Database.insert_result() + insert_score()  │     │
│     └──────────────────────────────────────────────┘     │
│  3. Update benchmark_runs status = completed              │
└─────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────┐
│                   Report / Charts                         │
│                                                          │
│  Report.generate(run_id) → JSON + CSV + HTML              │
│  Charts.generate(run_id) → PNG in charts/                 │
└─────────────────────────────────────────────────────────┘
```

---

## 8. Key Design Decisions (Consolidated)

| Decisione | Motivazione |
|---|---|
| Root = `ollama_bench/`, package = `benchmark/` | Evita collisione nomi; coerente col workspace |
| 7 categorie prompt (non 4, non 5) | Allineato a `prompts.json` + USER + HALLUCINATION + INSTRUCTION_FOLLOWING |
| Directory-based prompts (`prompts/<cat>/<sub>.json`) | Richiesto esplicitamente; permette organizzazione granulare |
| Provider abstraction (ABC + factory) | Disaccoppia runner/judge da API specifiche |
| 3 provider (Ollama, DeepSeek, OpenRouter) | Copertura locale + remoto; estendibile |
| Judge provider-agnostic | Giudice può essere remoto anche se target è locale |
| `ollama_client.py` → `providers/ollama.py` | Rinominato per coerenza con astrazione |
| 3 dipendenze esterne max (pyyaml, requests, matplotlib) | Minimalismo come da AGENT.md |
| SQLite canonical, report derivati | Coerente con tutti i documenti |
| 120s timeout default, configurabile | Realistico per modelli locali 20B-35B |
| API key in variabili d'ambiente, referenziate in config.yaml | Sicurezza; mai hardcoded |
| Crash-safe: persistenza immediata dopo ogni valutazione | AGENT.md: "In caso di crash non devono andare persi benchmark già eseguiti" |

---

## 9. MVP Scope (v1.0)

Al completamento della Fase 6, il sistema deve:

- [x] Eseguire benchmark con Ollama su almeno 1 suite
- [x] Provider abstraction funzionante (OllamaProvider)
- [x] Salvare tutti i risultati in SQLite
- [x] Generare report JSON
- [x] Generare report HTML
- [x] Confrontare 2 modelli via CLI

DeepSeek e OpenRouter sono v1.1 (Fase 2 già implementata, ma testabili solo con API key).

---

*Piano generato il 2026-06-06. In attesa di approvazione.*
