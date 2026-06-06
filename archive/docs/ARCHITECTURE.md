# ARCHITECTURE.md

# LLM Benchmark Framework

## Purpose

Framework per benchmark comparativi di Large Language Models.

Supporto multi-provider:

* Ollama (locale, `http://localhost:11434`)
* DeepSeek API (remoto)
* OpenRouter API (remoto)

Obiettivo:

* confrontare modelli nel tempo (cross-provider)
* raccogliere metriche oggettive
* raccogliere valutazioni tramite modello giudice
* produrre report confrontabili

---

# Runtime Environment

## Operating System

Windows 11

## Shell

PowerShell 7+

Assumere SEMPRE PowerShell come ambiente predefinito.

NON assumere:

* bash
* sh
* zsh
* fish

NON usare sintassi Linux salvo esplicita richiesta.

---

# Command Rules

Preferire:

```powershell
Get-ChildItem
Get-Content
Set-Content
Copy-Item
Move-Item
Remove-Item
```

invece di:

```bash
ls
cat
cp
mv
rm
```

---

# Path Rules

Utilizzare:

```text
C:\path\to\file
```

oppure:

```python
Path(...)
```

Mai assumere:

```text
/home/user
~/folder
```

---

# Python Environment

Versione target:

Python 3.11+

Preferire:

```python
from pathlib import Path
```

Evitare:

```python
os.path
```

quando non necessario.

---

# Package Manager

Preferenza:

pip

Non assumere:

poetry
conda
uv

a meno che non siano presenti nel repository.

---

# Provider Architecture

## Base Class

```
benchmark/providers/base.py
```

Definisce `BaseProvider` (ABC) con interfaccia comune:

* `generate(prompt: str) -> ProviderResponse`
* `list_models() -> list[str]`
* `is_available() -> bool`

`ProviderResponse` è un `@dataclass` con:

* `text`, `prompt_tokens`, `thinking_tokens`, `answer_tokens`, `total_tokens`, `latency_ms`

## Implementazioni

| File | Provider | Tipo | Auth |
|---|---|---|---|
| `providers/ollama.py` | Ollama | locale | nessuna |
| `providers/deepseek.py` | DeepSeek | remoto | API key in config.yaml |
| `providers/openrouter.py` | OpenRouter | remoto | API key in config.yaml |

Provider remoti usano `requests` (HTTP POST con Authorization header).
Provider locale usa `requests` verso `http://localhost:11434/api/generate`.

## Configurazione

```yaml
# config.yaml
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
```

API key lette da variabili d'ambiente se valore inizia con `${`.

---

# Ollama Environment

Ollama è installato localmente.

Comandi consentiti:

```powershell
ollama list

ollama show MODEL

ollama run MODEL

ollama ps
```

Assumere che Ollama sia raggiungibile tramite:

```text
http://localhost:11434
```

---

# Hardware Environment

CPU:

Intel Core i5-14400

GPU:

NVIDIA RTX 3060 12GB

NVIDIA Tesla P40 24GB

RAM:

32GB DDR5
(obiettivo futuro 64GB)

---

# Benchmark Constraints

I benchmark devono essere progettati per modelli locali.

Assumere tipicamente:

20B - 35B

quantizzati.

Non assumere disponibilità di:

* H100
* A100
* cluster GPU

---

# Project Structure

```
ollama_bench/

├── benchmark.py

├── config.yaml

├── prompts/

├── reports/

├── charts/

├── db/

└── benchmark/

    ├── __init__.py
    ├── runner.py
    ├── metrics.py
    ├── database.py
    ├── report.py
    ├── charts.py
    ├── prompts.py
    ├── scoring.py
    ├── judge.py
    │
    └── providers/
        ├── __init__.py
        ├── base.py
        ├── ollama.py
        ├── deepseek.py
        └── openrouter.py
```

---

# Data Flow

```
config.yaml
  ↓
ProviderFactory → OllamaProvider | DeepSeekProvider | OpenRouterProvider
  ↓
Prompt
  ↓
Target Model  (via provider selezionato)
  ↓
Response
  ↓
Metrics Extraction
  ↓
Judge Model   (via provider selezionato, potenzialmente diverso)
  ↓
Scoring
  ↓
SQLite
  ↓
Reports
```

Target e judge usano provider indipendenti.
Runner orchestra, mai accede direttamente a HTTP/API.

---

# SQLite Is Canonical

La fonte di verità è sempre SQLite.

Tutti i report derivano dal database.

Mai usare JSON come storage principale.

---

# Prompt Architecture

Categorie (7):

1. `general` — cultura generale, comprensione, sintesi
2. `technical` — matematica, fisica, statistica, informatica
3. `coding` — Python, SQL, regex, debugging, design
4. `agentic` — JSON compliance, tool calling, determinismo
5. `hallucination` — eventi futuri, prodotti inesistenti, fatti non verificabili
6. `instruction_following` — vincoli formato, conteggio parole, exact match
7. `user` — prompt reali dall'uso quotidiano (priorità elevata)

Prompt organizzati in directory: `prompts/<category>/<subtopic>.json`

Ogni prompt è indipendente.
Nessun prompt deve dipendere da output precedenti.

---

# Provider-Agnostic Judge

Il giudice (`benchmark/judge.py`) riceve un provider come dipendenza.
Non sa se sta chiamando Ollama, DeepSeek o OpenRouter.

```python
class Judge:
    def __init__(self, provider: BaseProvider): ...

    def evaluate(self, prompt: Prompt, response: str) -> JudgeScore: ...
```

Judge contract invariato:

```json
{
  "accuracy": 0, "reasoning": 0, "coding": 0,
  "hallucination_risk": 0,
  "overall": 0, "notes": ""
}
```

Configurazione judge in `config.yaml`:

```yaml
judge:
  provider: deepseek          # ollama | deepseek | openrouter
  model: deepseek-chat
```

Qualunque altro formato è considerato errore.

---

# Token Accounting

Quando disponibili registrare:

* prompt tokens
* thinking tokens
* answer tokens
* total tokens

Mai stimare se i dati reali sono disponibili.

---

# Historical Comparisons

Ogni benchmark deve essere confrontabile con benchmark futuri.

Non modificare metriche esistenti.

Nuove metriche devono essere additive.

---

# Agent Development Rules

Prima di modificare codice:

1. leggere file completo
2. identificare impatto minimo
3. proporre patch minima
4. implementare

Evitare:

* refactoring non richiesti
* rinomina arbitraria
* ristrutturazioni massive

---

# Platform Assumptions

Assumere SEMPRE:

Windows 11
PowerShell
Ollama locale disponibile
API key DeepSeek/OpenRouter in variabili d'ambiente (opzionali)

fino a diversa indicazione.

Qualsiasi comando Linux deve essere proposto solo se l'utente dichiara esplicitamente l'uso di:

* WSL
* Docker Linux
* macchina Linux

In assenza di tali informazioni usare esclusivamente soluzioni compatibili Windows.
