# LLM Benchmark Framework

Framework Python per benchmark comparativi di LLM locali/remoti con persistenza SQLite, scoring composito canonico e report JSON/CSV/HTML.

Provider supportati:
- Ollama (locale)
- DeepSeek API
- OpenRouter API

## Installazione

```powershell
cd ollama_bench
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configurazione

Config principale: `config.yaml`.

Esempio variabili ambiente per provider remoti:

```powershell
$env:DEEPSEEK_API_KEY = "sk-..."
$env:OPENROUTER_API_KEY = "sk-or-..."
```

Nota:
- il loader provider supporta anche file `.env` (`${DEEPSEEK_API_KEY}`, `${OPENROUTER_API_KEY}` in `config.yaml`).

## Comandi principali

```powershell
# run benchmark
python benchmark.py run --model gpt-oss:20b --provider ollama --suite agentic

# confronto modelli
python benchmark.py compare --models gpt-oss:20b,nemotron-cascade-2:latest --provider ollama

# list (read-only, senza side effects DB)
python benchmark.py list --providers
python benchmark.py list --models --provider ollama
python benchmark.py list --prompts --category agentic

# report
python benchmark.py report --run-id 1 --format all

# charts
python benchmark.py charts --run-id 1

# statistiche
python benchmark.py stats

# pulizia run/output
python benchmark.py clean --all
```

## Stato attuale scoring

### Quality vs performance
- `quality_score` e `performance_score` sono separati.
- ranking canonico usa qualità, non throughput hardware.

### Scoring composito canonico
- score canonico persistito in `composite_scores`.
- `v_model_scores` / `v_model_ranking` usano composito con fallback retrocompatibile.

### Deterministico avanzato
Check supportati includono:
- `exact_match`, `allowed_values`, `forbidden_text`
- `json_valid`, `required_json_keys`
- `expected_tools`, `tool_sequence`, `expected_keywords`
- split aggregato: `strict_compliance` e `semantic_correctness`

### Stato run
- `completed`
- `partial_failed`
- `failed`

## Validita statistica minima (M17)

Gli output includono una policy minima di validita:
- soglia minima prompt completati: 10
- soglia raccomandata: 30
- failure ratio raccomandato: <= 10%

La policy appare in:
- `benchmark.py stats` (ultima run)
- report JSON (`statistical_validity_policy`)
- report HTML e comparison HTML

## Database

SQLite e la fonte di verita.

Tabelle principali:
- `models`
- `benchmark_runs`
- `prompts`
- `benchmark_results`
- `judge_scores`
- `deterministic_scores`
- `composite_scores`

Viste:
- `v_model_scores`
- `v_model_ranking`

## Prompt e riproducibilita

- Prompt caricati da `prompts/**/*.json`.
- Snapshot prompt per run salvato in `benchmark_results`:
  - `prompt_snapshot_text`
  - `expected_answer_snapshot`
  - `deterministic_checks_snapshot`

## Report prodotti

- JSON: `reports/report_<run_id>.json`
- CSV: `reports/report_<run_id>.csv`
- HTML: `reports/report_<run_id>.html`
- Comparison HTML: `reports/comparison_<timestamp>.html`

## Note operative

- Il `clean --all` pulisce correttamente anche `composite_scores` rispettando le FK.
- `VACUUM` e eseguito dopo `commit` per evitare errori di transazione.

## Pubblicazione sicura su GitHub

Checklist rapida prima del push:

```powershell
# 1) controlla di NON avere segreti tracciati
git check-ignore -v .env .env.example benchmark.log graphify-out/graph.json

# 2) scansione veloce su file versionati
git grep -nEi "api[_-]?key|secret|token|password|bearer|sk-[a-z0-9]|ghp_[a-z0-9]|-----BEGIN"
```

Se il secondo comando trova credenziali reali, rimuovile prima del commit.

Flusso consigliato per primo push:

```powershell
git init
git add .
git commit -m "chore: initial public release"

# crea repo su GitHub (richiede gh auth login)
gh repo create ollama_bench --private --source . --remote origin --push

# quando vuoi renderla pubblica:
gh repo edit --visibility public
```

## Licenza

Questo progetto e distribuito con licenza MIT. Vedi [LICENSE](LICENSE).

## Attribuzioni

Dipendenze open-source e note di attribuzione sono elencate in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
