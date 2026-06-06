# PROJECT_SCHEMA.md

# LLM Benchmark Framework

Version: 1.1

---

# Vision

Creare un framework per benchmark comparativi di Large Language Models.

Il sistema consente benchmark su modelli locali (Ollama) e remoti (DeepSeek API, OpenRouter).

Deve consentire:

* confronto tra modelli diversi (cross-provider)
* confronto tra quantizzazioni diverse
* confronto storico nel tempo
* benchmark riproducibili
* benchmark automatizzati
* report e grafici automatici

L'obiettivo finale è identificare quali modelli funzionano meglio per:

* uso generale
* ragionamento tecnico
* coding
* orchestrazione agentica
* obbedienza istruzioni
* resistenza allucinazioni
* casi d'uso reali dell'utente

su hardware consumer locale e provider remoti.

---

# Supported Providers

| Provider   | Tipo    | Endpoint / SDK              |
|------------|---------|-----------------------------|
| Ollama     | locale  | `http://localhost:11434`    |
| DeepSeek   | remoto  | `https://api.deepseek.com`  |
| OpenRouter | remoto  | `https://openrouter.ai/api` |

Ogni provider è implementato come classe con interfaccia comune.
Il sistema è provider-agnostic: target model e judge model possono
appartenere a provider diversi.

---

# Hardware Target

## Current Hardware

CPU

Intel Core i5-14400

GPU

RTX 3060 12GB

Tesla P40 24GB

RAM

32GB DDR5

Target Future

64GB DDR5

---

# Operating Environment

Operating System

Windows 11

Shell

PowerShell 7+

Assumere SEMPRE PowerShell.

NON assumere:

* Linux
* Bash
* Ubuntu
* WSL

salvo esplicita richiesta.

---

# Primary Runtime

Python 3.11+

Ollama (locale) + API remote (DeepSeek, OpenRouter)

SQLite

Filesystem locale

---

# Design Principles

Priorità:

1. Correttezza
2. Riproducibilità
3. Semplicità
4. Robustezza
5. Performance

Evitare complessità non necessaria.

---

# Project Structure

```
ollama_bench/                        ← root progetto

├── AGENT.md
├── ARCHITECTURE.md
├── PROJECT_SCHEMA.md
├── IMPLEMENTATION_PLAN.md
├── README.md
├── config.yaml
├── requirements.txt
├── .gitignore
│
├── benchmark.py                     ← entry point CLI
│
├── benchmark/                       ← package Python
│   ├── __init__.py
│   ├── runner.py                    ← orchestrazione benchmark
│   ├── judge.py                     ← modello giudice (provider-agnostic)
│   ├── metrics.py                   ← estrazione metriche oggettive
│   ├── scoring.py                   ← calcolo scoring composito
│   ├── prompts.py                   ← caricamento e validazione prompt
│   ├── database.py                  ← layer SQLite
│   ├── report.py                    ← generazione report (JSON/CSV/HTML)
│   ├── charts.py                    ← generazione grafici
│   │
│   └── providers/                   ← astrazione multi-provider
│       ├── __init__.py
│       ├── base.py                  ← interfaccia comune
│       ├── ollama.py                ← Ollama (API locale)
│       ├── deepseek.py              ← DeepSeek API
│       └── openrouter.py            ← OpenRouter API
│
├── prompts/                         ← prompt organizzati per directory
│   │
│   ├── general/
│   │   ├── reasoning.json
│   │   ├── knowledge.json
│   │   └── summarization.json
│   │
│   ├── technical/
│   │   ├── mathematics.json
│   │   ├── physics.json
│   │   ├── computer_science.json
│   │   └── statistics.json
│   │
│   ├── coding/
│   │   ├── python.json
│   │   ├── debugging.json
│   │   ├── sql.json
│   │   ├── regex.json
│   │   └── architecture.json
│   │
│   ├── agentic/
│   │   ├── json_compliance.json
│   │   ├── tool_calling.json
│   │   ├── instruction_compliance.json
│   │   └── determinism.json
│   │
│   ├── hallucination/
│   │   ├── future_events.json
│   │   ├── fake_products.json
│   │   └── unverifiable_facts.json
│   │
│   ├── instruction_following/
│   │   ├── format_constraints.json
│   │   ├── word_count.json
│   │   └── exact_match.json
│   │
│   └── user/
│       ├── telegram_bot.json
│       ├── orchestrator.json
│       ├── ollama_logs.json
│       └── custom.json
│
├── db/
│   └── benchmark.db                 ← SQLite (auto-creato)
│
├── exports/                         ← export intermedi
│
├── reports/                         ← output report
│
└── charts/                          ← output grafici
```

---

# Benchmark Suites

## GENERAL

Misura:

* cultura generale
* comprensione
* sintesi
* ragionamento

Target:

20+ prompt

---

## TECHNICAL

Misura:

* matematica
* fisica
* statistica
* informatica

Target:

20+ prompt

---

## CODING

Misura:

* Python
* SQL
* regex
* debugging
* refactoring
* design software

Target:

20+ prompt

---

## AGENTIC

Misura:

* JSON compliance
* tool calling
* determinismo
* obbedienza istruzioni
* output strutturati

Target:

20+ prompt

---

## HALLUCINATION

Misura:

* invenzione eventi futuri
* descrizione prodotti inesistenti
* affermazioni non verificabili
* referenze inventate

Target:

10+ prompt

---

## INSTRUCTION_FOLLOWING

Misura:

* vincoli di formato
* conteggio parole esatto
* exact match
* divieti espliciti (non dire X)

Target:

10+ prompt

---

## USER

Prompt reali derivati dall'uso quotidiano.

Questa categoria ha priorità elevata.

Scopo:

misurare le prestazioni sui casi d'uso effettivi dell'utente.

---

# Prompt Format

Ogni prompt deve essere salvato come JSON.

Schema:

{
"id": "CODING_001",
"category": "coding",
"weight": 1.5,
"prompt": "...",
"expected_format": "...",
"expected_answer": "...",
"expected_behavior": "..."
}

---

# Execution Model

```
Prompt
  ↓
Target Model  (provider: Ollama | DeepSeek | OpenRouter)
  ↓
Response
  ↓
Metrics Extraction
  ↓
Judge Model   (provider: Ollama | DeepSeek | OpenRouter)
  ↓
Scoring
  ↓
SQLite
  ↓
Report
```

Target model e judge model usano provider potenzialmente diversi.
L'astrazione provider isola il runner dalla API specifica.

---

# Provider Architecture

Interfaccia comune definita in `benchmark/providers/base.py`:

```python
class BaseProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> ProviderResponse: ...
    @abstractmethod
    def list_models(self) -> list[str]: ...
    @abstractmethod
    def is_available(self) -> bool: ...
```

`ProviderResponse` contiene:

* `text: str` — testo risposta
* `prompt_tokens: int`
* `thinking_tokens: int`
* `answer_tokens: int`
* `total_tokens: int`
* `latency_ms: float`

Implementazioni concrete:

* `OllamaProvider` → `/api/generate`
* `DeepSeekProvider` → DeepSeek API (compatibile OpenAI)
* `OpenRouterProvider` → OpenRouter API (compatibile OpenAI)

Provider remoto richiede API key in `config.yaml`.

---

# Judge Model

Configurabile, provider-agnostic.

Default: `deepseek-pro` via DeepSeek API.

Può usare qualsiasi provider configurato (Ollama locale, DeepSeek, OpenRouter).

Output obbligatorio:

```json
{
  "accuracy": 0,
  "reasoning": 0,
  "coding": 0,
  "hallucination_risk": 0,
  "overall": 0,
  "notes": ""
}
```

Mai accettare output non JSON.

---

# Objective Metrics

Latency

Prompt Tokens

Thinking Tokens

Answer Tokens

Total Tokens

Tokens/sec

Characters

Lines

JSON Validity

Format Validity

---

# Advanced Metrics

## Compliance Ratio

Valuta quanto il modello segue le istruzioni.

---

## Determinism Score

Valuta la stabilità dell'output su più esecuzioni.

---

## Verbosity Ratio

Valuta quanto il modello eccede nella lunghezza delle risposte.

---

## Hallucination Score

Valuta la tendenza a inventare informazioni.

---

# Database

SQLite è la fonte di verità.

Tutti i report devono essere generati da SQLite.

Mai usare JSON come storage principale.

---

# Reporting

Generare:

JSON

CSV

HTML

---

# Charts

Generare:

Overall Ranking

Coding Ranking

Technical Ranking

Agentic Ranking

Hallucination Ranking

Instruction Following Ranking

Latency Ranking

Tokens/sec Ranking

Historical Trends

Cross-Provider Comparison

---

# CLI

Benchmark completo

```
python benchmark.py --model MODEL --provider ollama
python benchmark.py --model deepseek-chat --provider deepseek
python benchmark.py --model openai/gpt-4o --provider openrouter
```

Benchmark singola suite

```
python benchmark.py --model MODEL --suite coding
```

Confronto modelli

```
python benchmark.py compare --models model1,model2,model3
```

Elenca provider disponibili

```
python benchmark.py --list-providers
```

---

# Agent Instructions

L'agente deve:

1. Creare automaticamente tutta la struttura directory.
2. Generare i file JSON dei prompt per tutte le 7 categorie.
3. Implementare l'astrazione provider (base + Ollama + DeepSeek + OpenRouter).
4. Generare lo schema SQLite.
5. Generare i moduli Python necessari.
6. Implementare prima una MVP funzionante.
7. Aggiungere funzionalità in modo incrementale.
8. Evitare refactoring prematuri.
9. Evitare dipendenze non necessarie.

---

# MVP Definition

La versione 1.0 è completata quando:

* viene eseguito almeno un benchmark (Ollama locale)
* provider abstraction funzionante (minimo 1 provider)
* i risultati sono salvati in SQLite
* viene generato un report JSON
* viene generato un report HTML
* è possibile confrontare due modelli

La versione 1.1 aggiunge:

* DeepSeek provider
* OpenRouter provider
* judge cross-provider
* benchmark cross-provider comparison

Tutto il resto è considerato evoluzione successiva.
