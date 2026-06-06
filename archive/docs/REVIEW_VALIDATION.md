# REVIEW VALIDATION

## Scope
Validazione delle osservazioni contenute in:
- PROJECT_IMPROVEMENT_PLAN.md
- PROMPTS_VALUTATION_AND_IMPROVEMENT.md

Vincoli rispettati in questa fase:
- Nessuna modifica al codice
- Nessuna implementazione
- Solo analisi e classificazione

Classi usate:
- VALID
- PARTIALLY_VALID
- INVALID

Nota:
- Le osservazioni duplicate tra i due documenti sono state deduplicate per tema e tracciate con riferimenti multipli.

---

## Metodo di verifica
1. Confronto osservazioni vs baseline documentale:
   - PROJECT_SCHEMA.md
   - AGENT.md
   - ARCHITECTURE.md
   - IMPLEMENTATION_PLAN.md
2. Confronto con evidenze benchmark disponibili (report CSV/JSON esistenti).
3. Classificazione per robustezza dell’evidenza e allineamento ai requisiti di progetto.

---

## A) Validazione osservazioni affidabilita/correttezza (Project Improvement)

| ID | Osservazione | Classificazione | File coinvolti | Impatto | Rischio |
|---|---|---|---|---|---|
| A01 | Crash charts per riferimento a formatting non piu presente nello schema judge | VALID | benchmark/charts.py, benchmark/judge.py, benchmark/database.py, ARCHITECTURE.md, IMPLEMENTATION_PLAN.md | Alto: comando charts inutilizzabile | Alto |
| A02 | Crash stats per uso connessione SQLite dopo chiusura context manager | VALID | benchmark.py | Alto: comando stats inaffidabile | Alto |
| A03 | Drift schema judge tra documenti (formatting presente) e schema operativo corrente (senza formatting) | VALID | PROJECT_SCHEMA.md, ARCHITECTURE.md, IMPLEMENTATION_PLAN.md, README.md, benchmark/judge.py, benchmark/database.py | Alto: ambiguita metodologica e regressioni | Alto |
| A04 | Prompt immutability non garantita per comparazioni storiche | VALID | IMPLEMENTATION_PLAN.md, benchmark/database.py, benchmark/report.py | Alto: riproducibilita storica compromessa | Alto |
| A05 | Composite score non canonico nella persistenza/report/ranking | VALID | benchmark/scoring.py, benchmark/runner.py, benchmark/database.py, benchmark/report.py | Alto: ranking incoerente | Alto |
| A06 | Mescolanza segnali oggettivi/soggettivi nel quality score | VALID | AGENT.md, benchmark/scoring.py | Medio-Alto: bias verso performance hardware | Medio-Alto |
| A07 | JSON mode judge non coerente cross-provider (specialmente lato Ollama) | PARTIALLY_VALID | benchmark/judge.py, benchmark/providers/ollama.py, ARCHITECTURE.md | Medio: affidabilita parsing non uniforme | Medio |
| A08 | Stato run puo risultare completed anche con fallimenti parziali rilevanti | VALID | benchmark/runner.py, benchmark/report.py | Medio: reporting ottimistico | Medio |
| A09 | Comandi list con possibili side effect non metodologici | PARTIALLY_VALID | benchmark.py, benchmark/runner.py | Basso-Medio: UX/integrita operativa, impatto benchmark indiretto | Basso-Medio |

### Considerazioni sintetiche A
- I punti A01-A06 sono direttamente coerenti con priorita documentale (correttezza, riproducibilita, robustezza).
- A07 e A09 hanno evidenza parziale perche dipendono da comportamenti provider/scope d’uso specifici.

---

## B) Validazione osservazioni metodologiche (Prompts Valutation + sezione methodology del piano)

| ID | Osservazione | Classificazione | File coinvolti | Impatto | Rischio |
|---|---|---|---|---|---|
| M01 | Benchmark attuale piu vicino a sanity suite che a comparativa robusta | VALID | prompts/**, PROJECT_SCHEMA.md, IMPLEMENTATION_PLAN.md | Alto: ranking fragile | Alto |
| M02 | Possibilita di benchmark gaming (format-first, refusal template, tool token spoofing) | VALID | prompts/agentic/*.json, prompts/hallucination/*.json, prompts/instruction_following/*.json | Alto: metriche gonfiabili | Alto |
| M03 | Copertura prompt insufficiente rispetto target dichiarati (20+ / 10+) | VALID | PROJECT_SCHEMA.md, prompts/** | Alto: bassa validita statistica | Alto |
| M04 | False positive da exact-match rigido su output semanticamente corretti | VALID | prompts/instruction_following/*.json, prompts/agentic/*.json | Medio-Alto: penalita ingiuste | Medio-Alto |
| M05 | False negative: json_valid non garantisce schema/semantica corretta | VALID | prompts/agentic/json_compliance.json, prompts/agentic/tool_calling.json | Alto: promozione output errati | Alto |
| M06 | Tool-calling sottovalutato: mancano controlli completi su ordine/argomenti | VALID | prompts/agentic/tool_calling.json | Alto: benchmark agentic poco affidabile | Alto |
| M07 | Hallucination suite sbilanciata su unknown ovvi; bassa discriminazione di calibratura epistemica | VALID | prompts/hallucination/*.json | Medio-Alto: separazione modelli limitata | Medio-Alto |
| M08 | Compliance troppo orientata a superficie (formato) vs correttezza semantica | VALID | prompts/instruction_following/*.json, prompts/agentic/instruction_compliance.json | Alto: metrica facilmente manipolabile | Alto |
| M09 | Prompt deboli/triviali con scarso potere discriminativo | VALID | prompts/general/reasoning.json, prompts/instruction_following/*.json | Medio-Alto: ceiling effect | Medio-Alto |
| M10 | Presenza di prompt non valutabile in user/custom | VALID | prompts/user/custom.json | Medio: rumore nel punteggio | Medio |
| M11 | Mancano categorie critiche (long-context, grounded QA, perturbation robustness, multi-turn) | PARTIALLY_VALID | PROJECT_SCHEMA.md, prompts/** | Medio-Alto: gap metodologici reali ma scope estensivo | Medio |
| M12 | Single-judge bias possibile in assenza di calibrazione periodica | PARTIALLY_VALID | ARCHITECTURE.md, benchmark/judge.py (contratto), PROJECT_SCHEMA.md | Medio: rischio qualitativo plausibile ma non quantificato qui | Medio |
| M13 | Metriche ridondanti (answer_tokens/total_tokens/char_count/line_count) | VALID | reports/report_*.csv, PROJECT_SCHEMA.md | Medio: rumore analitico e doppio conteggio | Medio |
| M14 | Metriche non informative nel campione (format_valid costante, judge_coding costante fuori coding) | VALID | reports/report_*.csv | Medio: scarsa utilita discriminativa | Medio |
| M15 | Correlazione forte judge_accuracy vs judge_overall nel campione (quasi duplicazione asse soggettivo) | VALID | reports/report_*.csv | Medio: ridondanza scoring | Medio |
| M16 | Speed metriche (latency/tps) utili ma non da confondere con quality | VALID | AGENT.md, reports/report_*.csv | Alto: bias hardware se miscelate | Alto |
| M17 | Mancanza di incertezza statistica (CI/effect size) limita robustezza confronti | VALID | reports/report_*.json, PROJECT_SCHEMA.md | Alto: classifiche poco difendibili | Alto |
| M18 | Richiesta di rank stability su varianti/parafrasi utile per anti-overfitting | PARTIALLY_VALID | prompts/** | Medio: valida metodologicamente ma richiede espansione suite | Medio |
| M19 | Proposta di policy category-aware per applicabilita metriche | VALID | PROJECT_SCHEMA.md, prompts/**, reports/report_*.csv | Medio-Alto: migliora correttezza aggregazione | Medio |
| M20 | Proposta di separazione strict compliance vs semantic correctness | VALID | prompts/instruction_following/*.json, prompts/agentic/instruction_compliance.json | Alto: migliora affidabilita valutativa | Alto |

### Considerazioni sintetiche B
- Le osservazioni M01-M10 e M13-M17 sono fortemente supportate da documenti di progetto + evidenze empiriche dei report.
- M11, M12, M18 sono PARTIALLY_VALID: corrette in linea metodologica, ma richiedono baseline/esperimenti aggiuntivi per essere rese prescrittive in modo forte.

---

## C) Osservazioni classificate INVALID

Nessuna osservazione dei due documenti risulta chiaramente INVALID alla luce di:
- requisiti dichiarati (correttezza, riproducibilita, confrontabilita)
- baseline architetturale
- evidenze dei report esistenti

Nota:
- Alcune osservazioni restano PARTIALLY_VALID per limiti campionari o perche rappresentano raccomandazioni metodologiche avanzate non ancora testate nel contesto corrente.

---

## D) Priorita operative suggerite per Fase 1 (coerenti con classificazione)

Priorita alta (VALID + rischio alto):
1. A01 charts crash
2. A02 stats crash
3. A03 schema judge canonico

Priorita alta successiva:
4. A04 immutabilita prompt
5. A05 score canonico persistito
6. M05/M06 hardening deterministic su JSON/tool semantics

Priorita media:
7. A06 separazione quality/performance
8. M20 separazione strict compliance vs semantic correctness
9. M17 policy minima di validita statistica in output benchmark

---

## Stato fase
FASE 0 completata.
Nessuna modifica al codice applicata in questa fase.
