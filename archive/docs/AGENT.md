# AGENT.md

# LLM Benchmark Framework

## Mission

Costruire e mantenere un framework Python per benchmark comparativi di Large Language Models.

Supporto multi-provider: Ollama (locale), DeepSeek API, OpenRouter API.

L'obiettivo primario è ottenere risultati riproducibili e confrontabili nel tempo, indipendentemente dal provider.

L'obiettivo NON è sperimentare architetture complesse o introdurre dipendenze inutili.

---

# Core Principles

1. Preferire semplicità a complessità.
2. Preferire codice leggibile a codice intelligente.
3. Preferire robustezza a ottimizzazioni premature.
4. Ogni modifica deve mantenere la compatibilità con benchmark precedenti.
5. Evitare refactoring non richiesti.

---

# Anti Goals

Non implementare:

* dashboard web
* frontend React
* microservizi
* Docker
* Kubernetes
* architetture distribuite
* plugin system
* dependency injection framework

a meno che non venga richiesto esplicitamente.

---

# Development Rules

Prima di modificare codice:

1. Leggere il file intero.
2. Comprendere il flusso esistente.
3. Cercare soluzioni locali.
4. Evitare modifiche trasversali.

Non riscrivere file interi per correggere piccoli problemi.

Preferire patch minimali.

---

# Token Conservation Policy

Ridurre al minimo:

* spiegazioni verbose
* commenti inutili
* duplicazioni

Quando proponi modifiche:

Mostrare solo:

* problema
* causa
* patch

Non generare tutorial.

Non spiegare concetti Python di base.

---

# Architecture Constraints

Il progetto deve rimanere:

* single process
* SQLite based
* filesystem based

Evitare:

* PostgreSQL
* Redis
* RabbitMQ
* Celery

senza richiesta esplicita.

---

# Provider Rules

Ogni provider deve implementare `BaseProvider` (ABC).

Provider diversi non devono condividere stato.

API key per provider remoti in `config.yaml` (mai hardcoded).

Provider timeout: 120s default, configurabile.

Aggiungere nuovo provider = creare una classe in `benchmark/providers/`, mai modificare `runner.py` o `judge.py`.

---

# Python Standards

Target:

Python >= 3.11

Usare:

* dataclass
* pathlib
* typing
* abc (ABC, abstractmethod)

Preferire:

* list
* dict
* tuple

Evitare dipendenze terze se la libreria standard è sufficiente.

---

# Error Handling

Mai usare:

except:

Usare sempre:

except SpecificException:

Registrare sempre gli errori.

Non silenziare eccezioni.

---

# Logging

Usare:

logging

Non usare:

print()

eccetto per output CLI richiesto.

Livelli:

DEBUG
INFO
WARNING
ERROR

---

# Database Rules

SQLite è la fonte di verità.

Non salvare stato in memoria oltre il necessario.

Ogni benchmark deve essere persistito appena completato.

In caso di crash non devono andare persi benchmark già eseguiti.

---

# Benchmark Rules

Ogni prompt deve essere indipendente.

I prompt non devono condividere stato.

Ogni esecuzione deve essere ripetibile.

---

# Judge Rules

Il modello giudice deve restituire JSON valido.

Giudice provider-agnostic: può usare Ollama, DeepSeek, OpenRouter.

Mai accettare output libero.

Se il JSON è invalido:

* ritentare una volta
* poi registrare errore

---

# Scoring Rules

Separare:

metriche oggettive

* latency
* token count
* tokens/sec
* json validity

metriche soggettive

* reasoning
* coding
* accuracy
* hallucination_risk

Mai mescolare le due categorie.

---

# Performance Rules

Ottimizzare solo dopo aver misurato.

Mai introdurre caching preventivo.

Mai introdurre parallelismo preventivo.

---

# Testing Rules

Ogni nuova feature deve includere:

* test positivo
* test negativo

Non creare test inutilmente complessi.

---

# File Size Rules

Quando un file supera:

500 linee

valutare la divisione.

Quando supera:

1000 linee

proporre la divisione.

---

# Refactoring Rules

Non cambiare API pubbliche senza motivo.

Non rinominare file o funzioni per preferenze personali.

Non modificare strutture dati esistenti senza necessità.

---

# Reporting Rules

Ogni report deve essere generabile da SQLite.

Il database è la sorgente primaria.

CSV, JSON e HTML sono derivati.

---

# Graph Rules

I grafici devono essere generati dai dati salvati.

Mai ricalcolare benchmark.

Mai usare dati temporanei.

---

# Bug Fix Procedure

Quando viene segnalato un bug:

1. Identificare causa.
2. Proporre soluzione minima.
3. Implementare patch minima.
4. Verificare regressioni.
5. Aggiornare test se necessario.

Evitare refactoring durante bug fixing.

---

# Decision Hierarchy

In caso di conflitto:

Correttezza

>

Riproducibilità

>

Semplicità

>

Performance

>

Eleganza

Seguire sempre questa priorità.

---

# Expected Agent Behaviour

Prima di generare codice:

* ragionare sul codice esistente
* individuare il punto minimo da modificare
* proporre la soluzione più piccola possibile

Preferire:

20 righe corrette

a

200 righe "più belle".

La stabilità del benchmark è più importante della creatività dell'implementazione.
