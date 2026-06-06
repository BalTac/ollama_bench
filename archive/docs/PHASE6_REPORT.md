# PHASE 6 REPORT

## Scope executed
- M17 policy minima di validita statistica in output benchmark

Only Phase 6 scope was implemented.

---

## 1) Files changed

- benchmark/report.py
- benchmark.py

---

## 2) Schema changes

- Nessuna modifica schema DB.

---

## 3) Migration requirements

- Nessuna migration SQL necessaria.
- Retrocompatibilita preservata.

---

## 4) Runtime/logic changes

### M17 - Statistical validity minimum policy
Implemented in `benchmark/report.py`:
- Introdotta policy minima con soglie fisse:
  - `MIN_PROMPTS_MINIMUM = 10`
  - `MIN_PROMPTS_RECOMMENDED = 30`
  - `MAX_FAILURE_RATIO_RECOMMENDED = 0.10`
- Nuovo helper `_statistical_validity_policy(...)` che produce:
  - `status`: `insufficient` | `minimum_only` | `recommended`
  - `warnings` coerenti con campione/failure ratio
- JSON report ora include:
  - `statistical_validity_policy` (top-level)
  - `summary.statistical_validity_status`
- HTML report ora mostra:
  - stato validita statistica
  - card dedicata con soglie e warning
- Comparison HTML ora mostra:
  - badge di validita statistica per run
  - nota policy soglie in header

Implemented in `benchmark.py` (`stats` command):
- Valutazione policy sull'ultima run e output warning espliciti:
  - insufficienza campione
  - failure ratio sopra soglia

Nota metodologica:
- Nessun calcolo avanzato (CI/effect size) introdotto, in linea con vincolo di evitare moduli statistici aggiuntivi in questa fase.

---

## 5) Tests performed

### Static validation
- `get_errors` su file modificati: PASS (no errors)

### CLI smoke validation
Command:
- `python benchmark.py stats`

Result:
- PASS
- Output include warning policy M17 (esempio su run 9):
  - `Statistical validity: INSUFFICIENT (6 < 10 prompt completati)`
  - `Failure ratio elevato: 14.3% (raccomandato <= 10%)`

### Report generation validation
Command:
- `python benchmark.py report --run-id 9 --format all`

Result:
- PASS
- `reports/report_9.json`, `reports/report_9.csv`, `reports/report_9.html` rigenerati senza errori.
- JSON verificato: presenti `statistical_validity_policy` e `summary.statistical_validity_status`.

---

## 6) Expected benchmark impact

- Migliore trasparenza metodologica nei report: il lettore vede se una classifica e sotto soglia campionaria.
- Riduzione rischio di interpretazione eccessiva di run con pochi prompt o alto tasso di fallimento.
- Nessuna rottura compatibilita dati/esecuzioni esistenti.

---

## Stop condition
Phase 6 completed and stopped as requested.
