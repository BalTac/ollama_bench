"""SQLite database layer — schema, CRUD, import.

SQLite is canonical. All reports derive from this database.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Schema DDL
# ──────────────────────────────────────────────

SCHEMA_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS models (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    provider      TEXT NOT NULL,
    quantization  TEXT,
    parameters    TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, provider, quantization)
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id          INTEGER NOT NULL REFERENCES models(id),
    target_provider   TEXT NOT NULL,
    suite             TEXT NOT NULL,
    judge_model       TEXT NOT NULL,
    judge_provider    TEXT NOT NULL,
    started_at        TEXT NOT NULL,
    completed_at      TEXT,
    status            TEXT NOT NULL DEFAULT 'running',
    total_prompts     INTEGER DEFAULT 0,
    completed_prompts INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prompts (
    id                  TEXT PRIMARY KEY,
    category            TEXT NOT NULL,
    subcategory         TEXT NOT NULL,
    weight              REAL NOT NULL DEFAULT 1.0,
    prompt_text         TEXT NOT NULL,
    expected_format     TEXT,
    expected_answer     TEXT,
    expected_behavior   TEXT,
    deterministic_checks TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES benchmark_runs(id),
    prompt_id       TEXT NOT NULL REFERENCES prompts(id),
    model_id        INTEGER NOT NULL REFERENCES models(id),
    prompt_snapshot_text TEXT,
    expected_answer_snapshot TEXT,
    deterministic_checks_snapshot TEXT,
    response_text   TEXT NOT NULL,
    latency_ms      REAL NOT NULL,
    prompt_tokens   INTEGER,
    thinking_tokens INTEGER,
    answer_tokens   INTEGER,
    total_tokens    INTEGER,
    tokens_per_sec  REAL,
    char_count      INTEGER,
    line_count      INTEGER,
    json_valid      INTEGER,
    format_valid    INTEGER,
    executed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS judge_scores (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id         INTEGER NOT NULL UNIQUE REFERENCES benchmark_results(id),
    judge_model       TEXT NOT NULL,
    judge_provider    TEXT NOT NULL,
    accuracy          REAL NOT NULL,
    reasoning         REAL NOT NULL,
    coding            REAL NOT NULL,
    hallucination_risk REAL NOT NULL,
    overall           REAL NOT NULL,
    notes             TEXT,
    retry_count       INTEGER DEFAULT 0,
    evaluated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS composite_scores (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id         INTEGER NOT NULL UNIQUE REFERENCES benchmark_results(id),
    composite_score   REAL NOT NULL,
    judge_overall     REAL NOT NULL,
    deterministic_overall REAL,
    prompt_weight     REAL NOT NULL DEFAULT 1.0,
    scoring_version   TEXT NOT NULL DEFAULT 'v1',
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deterministic_scores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id           INTEGER NOT NULL UNIQUE REFERENCES benchmark_results(id),
    exact_match         REAL,
    allowed_values      REAL,
    forbidden_text      REAL,
    json_valid          REAL,
    required_json_keys  REAL,
    format_valid        REAL,
    regex_match         REAL,
    expected_tools      REAL,
    tool_sequence       REAL,
    expected_keywords   REAL,
    strict_compliance   REAL,
    semantic_correctness REAL,
    overall             REAL NOT NULL DEFAULT 0.0,
    performed_checks    TEXT NOT NULL DEFAULT '[]',
    details             TEXT,
    evaluated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indici
CREATE INDEX IF NOT EXISTS idx_results_run ON benchmark_results(run_id);
CREATE INDEX IF NOT EXISTS idx_results_model ON benchmark_results(model_id);
CREATE INDEX IF NOT EXISTS idx_results_prompt ON benchmark_results(prompt_id);
CREATE INDEX IF NOT EXISTS idx_scores_result ON judge_scores(result_id);
CREATE INDEX IF NOT EXISTS idx_determ_result ON deterministic_scores(result_id);
CREATE INDEX IF NOT EXISTS idx_composite_result ON composite_scores(result_id);
CREATE INDEX IF NOT EXISTS idx_runs_model ON benchmark_runs(model_id);
CREATE INDEX IF NOT EXISTS idx_runs_suite ON benchmark_runs(suite);
CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider);

-- Viste
CREATE VIEW IF NOT EXISTS v_model_scores AS
SELECT
    m.name AS model_name,
    m.provider,
    m.quantization,
    br.suite,
    br.judge_model,
    AVG(js.overall) AS avg_overall,
    COALESCE(AVG(cs.composite_score), AVG(js.overall)) AS avg_composite,
    AVG(js.accuracy) AS avg_accuracy,
    AVG(js.reasoning) AS avg_reasoning,
    AVG(js.coding) AS avg_coding,
    AVG(js.hallucination_risk) AS avg_hallucination_risk,
    AVG(ds.overall) AS avg_deterministic,
    AVG(br_e.latency_ms) AS avg_latency_ms,
    AVG(br_e.tokens_per_sec) AS avg_tokens_per_sec,
    COUNT(*) AS prompt_count
FROM models m
JOIN benchmark_results br_e ON br_e.model_id = m.id
JOIN benchmark_runs br ON br_e.run_id = br.id
LEFT JOIN judge_scores js ON js.result_id = br_e.id
LEFT JOIN deterministic_scores ds ON ds.result_id = br_e.id
LEFT JOIN composite_scores cs ON cs.result_id = br_e.id
GROUP BY m.name, m.provider, m.quantization, br.suite, br.judge_model;

CREATE VIEW IF NOT EXISTS v_model_ranking AS
SELECT
    model_name,
    provider,
    quantization,
    AVG(avg_composite) AS overall_rank,
    AVG(avg_overall) AS avg_judge_overall,
    AVG(avg_deterministic) AS avg_deterministic,
    AVG(avg_latency_ms) AS avg_latency_ms,
    AVG(avg_tokens_per_sec) AS avg_tokens_per_sec,
    SUM(prompt_count) AS total_prompts
FROM v_model_scores
GROUP BY model_name, provider, quantization;
"""

# Migrazione per database esistenti (backward compat)
MIGRATION_DDL = [
    # v1.0 → v1.1: aggiungi colonna deterministic_checks a prompts
    "ALTER TABLE prompts ADD COLUMN deterministic_checks TEXT",
    # v1.0 → v1.1: nuova tabella deterministic_scores
    """CREATE TABLE IF NOT EXISTS deterministic_scores (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        result_id           INTEGER NOT NULL UNIQUE REFERENCES benchmark_results(id),
        exact_match         REAL,
        allowed_values      REAL,
        forbidden_text      REAL,
        json_valid          REAL,
        required_json_keys  REAL,
        format_valid        REAL,
        regex_match         REAL,
        expected_tools      REAL,
        tool_sequence       REAL,
        expected_keywords   REAL,
        strict_compliance   REAL,
        semantic_correctness REAL,
        overall             REAL NOT NULL DEFAULT 0.0,
        performed_checks    TEXT NOT NULL DEFAULT '[]',
        details             TEXT,
        evaluated_at        TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_determ_result ON deterministic_scores(result_id)",
    # v1.1 → v1.2: snapshot prompt per riproducibilità storica
    "ALTER TABLE benchmark_results ADD COLUMN prompt_snapshot_text TEXT",
    "ALTER TABLE benchmark_results ADD COLUMN expected_answer_snapshot TEXT",
    "ALTER TABLE benchmark_results ADD COLUMN deterministic_checks_snapshot TEXT",
    # v1.1 → v1.2: persistenza score composito canonico
    """CREATE TABLE IF NOT EXISTS composite_scores (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        result_id         INTEGER NOT NULL UNIQUE REFERENCES benchmark_results(id),
        composite_score   REAL NOT NULL,
        judge_overall     REAL NOT NULL,
        deterministic_overall REAL,
        prompt_weight     REAL NOT NULL DEFAULT 1.0,
        scoring_version   TEXT NOT NULL DEFAULT 'v1',
        created_at        TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_composite_result ON composite_scores(result_id)",
    # riallinea viste a ranking canonico composito
    "DROP VIEW IF EXISTS v_model_scores",
    """CREATE VIEW IF NOT EXISTS v_model_scores AS
    SELECT
        m.name AS model_name,
        m.provider,
        m.quantization,
        br.suite,
        br.judge_model,
        AVG(js.overall) AS avg_overall,
        COALESCE(AVG(cs.composite_score), AVG(js.overall)) AS avg_composite,
        AVG(js.accuracy) AS avg_accuracy,
        AVG(js.reasoning) AS avg_reasoning,
        AVG(js.coding) AS avg_coding,
        AVG(js.hallucination_risk) AS avg_hallucination_risk,
        AVG(ds.overall) AS avg_deterministic,
        AVG(br_e.latency_ms) AS avg_latency_ms,
        AVG(br_e.tokens_per_sec) AS avg_tokens_per_sec,
        COUNT(*) AS prompt_count
    FROM models m
    JOIN benchmark_results br_e ON br_e.model_id = m.id
    JOIN benchmark_runs br ON br_e.run_id = br.id
    LEFT JOIN judge_scores js ON js.result_id = br_e.id
    LEFT JOIN deterministic_scores ds ON ds.result_id = br_e.id
    LEFT JOIN composite_scores cs ON cs.result_id = br_e.id
    GROUP BY m.name, m.provider, m.quantization, br.suite, br.judge_model""",
    "DROP VIEW IF EXISTS v_model_ranking",
    """CREATE VIEW IF NOT EXISTS v_model_ranking AS
    SELECT
        model_name,
        provider,
        quantization,
        AVG(avg_composite) AS overall_rank,
        AVG(avg_overall) AS avg_judge_overall,
        AVG(avg_deterministic) AS avg_deterministic,
        AVG(avg_latency_ms) AS avg_latency_ms,
        AVG(avg_tokens_per_sec) AS avg_tokens_per_sec,
        SUM(prompt_count) AS total_prompts
    FROM v_model_scores
    GROUP BY model_name, provider, quantization""",
    # v1.2 → v1.3: deterministic semantic checks + split strict/semantic
    "ALTER TABLE deterministic_scores ADD COLUMN allowed_values REAL",
    "ALTER TABLE deterministic_scores ADD COLUMN forbidden_text REAL",
    "ALTER TABLE deterministic_scores ADD COLUMN required_json_keys REAL",
    "ALTER TABLE deterministic_scores ADD COLUMN tool_sequence REAL",
    "ALTER TABLE deterministic_scores ADD COLUMN strict_compliance REAL",
    "ALTER TABLE deterministic_scores ADD COLUMN semantic_correctness REAL",
]


# ──────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────

@dataclass
class ModelInfo:
    id: Optional[int] = None
    name: str = ""
    provider: str = ""
    quantization: Optional[str] = None
    parameters: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class BenchmarkRun:
    id: Optional[int] = None
    model_id: int = 0
    target_provider: str = ""
    suite: str = ""
    judge_model: str = ""
    judge_provider: str = ""
    started_at: str = ""
    completed_at: Optional[str] = None
    status: str = "running"
    total_prompts: int = 0
    completed_prompts: int = 0


@dataclass
class BenchmarkResult:
    id: Optional[int] = None
    run_id: int = 0
    prompt_id: str = ""
    model_id: int = 0
    prompt_snapshot_text: Optional[str] = None
    expected_answer_snapshot: Optional[str] = None
    deterministic_checks_snapshot: Optional[str] = None
    response_text: str = ""
    latency_ms: float = 0.0
    prompt_tokens: Optional[int] = None
    thinking_tokens: Optional[int] = None
    answer_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    tokens_per_sec: Optional[float] = None
    char_count: int = 0
    line_count: int = 0
    json_valid: Optional[int] = None
    format_valid: Optional[int] = None
    executed_at: Optional[str] = None


@dataclass
class JudgeScore:
    id: Optional[int] = None
    result_id: int = 0
    judge_model: str = ""
    judge_provider: str = ""
    accuracy: float = 0.0
    reasoning: float = 0.0
    coding: float = 0.0
    hallucination_risk: float = 0.0
    overall: float = 0.0
    notes: str = ""
    retry_count: int = 0
    evaluated_at: Optional[str] = None


@dataclass
class DeterministicScore:
    id: Optional[int] = None
    result_id: int = 0
    exact_match: Optional[float] = None
    allowed_values: Optional[float] = None
    forbidden_text: Optional[float] = None
    json_valid: Optional[float] = None
    required_json_keys: Optional[float] = None
    format_valid: Optional[float] = None
    regex_match: Optional[float] = None
    expected_tools: Optional[float] = None
    tool_sequence: Optional[float] = None
    expected_keywords: Optional[float] = None
    strict_compliance: Optional[float] = None
    semantic_correctness: Optional[float] = None
    overall: float = 0.0
    performed_checks: str = "[]"
    details: Optional[str] = None
    evaluated_at: Optional[str] = None


@dataclass
class CompositeScoreRecord:
    id: Optional[int] = None
    result_id: int = 0
    composite_score: float = 0.0
    judge_overall: float = 0.0
    deterministic_overall: Optional[float] = None
    prompt_weight: float = 1.0
    scoring_version: str = "v1"
    created_at: Optional[str] = None


# ──────────────────────────────────────────────
# Database Manager
# ──────────────────────────────────────────────

class DatabaseManager:
    """Gestisce connessione e operazioni SQLite."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _conn(self):
        """Context manager per connessione con row_factory abilitato."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Init ────────────────────────────────

    def init_db(self) -> None:
        """Crea schema se non esiste + migrazioni per DB esistenti."""
        with self._conn() as conn:
            conn.executescript(SCHEMA_DDL)
            # Migrazioni backward-compat (ignora errori se colonna/tabella esiste)
            for ddl in MIGRATION_DDL:
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # già esiste
        logger.info("Database inizializzato: %s", self.db_path)

    # ── Models ──────────────────────────────

    def upsert_model(
        self,
        name: str,
        provider: str,
        quantization: Optional[str] = None,
        parameters: Optional[str] = None,
    ) -> int:
        """Inserisce o recupera modello. Restituisce model_id."""
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO models (name, provider, quantization, parameters)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name, provider, quantization) DO UPDATE SET
                       parameters=COALESCE(excluded.parameters, parameters)
                   RETURNING id""",
                (name, provider, quantization, parameters),
            )
            row = cur.fetchone()
            model_id = row["id"]
            logger.debug("Model upserted: id=%s, name=%s, provider=%s", model_id, name, provider)
            return model_id

    def get_model(self, model_id: int) -> Optional[ModelInfo]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()
            return ModelInfo(**dict(row)) if row else None

    def list_models(self) -> list[ModelInfo]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM models ORDER BY name, provider").fetchall()
            return [ModelInfo(**dict(r)) for r in rows]

    # ── Runs ────────────────────────────────

    def create_run(
        self,
        model_id: int,
        target_provider: str,
        suite: str,
        judge_model: str,
        judge_provider: str,
    ) -> int:
        """Crea nuova benchmark run. Restituisce run_id."""
        import datetime as dt

        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO benchmark_runs
                   (model_id, target_provider, suite, judge_model, judge_provider, started_at)
                   VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
                (model_id, target_provider, suite, judge_model, judge_provider,
                 dt.datetime.now().isoformat()),
            )
            run_id = cur.fetchone()["id"]
            logger.info("Run creata: id=%s, suite=%s", run_id, suite)
            return run_id

    def update_run_status(
        self,
        run_id: int,
        status: str,
        total_prompts: int = 0,
        completed_prompts: int = 0,
    ) -> None:
        import datetime as dt

        completed_at = dt.datetime.now().isoformat() if status in ("completed", "failed", "partial_failed") else None
        with self._conn() as conn:
            conn.execute(
                """UPDATE benchmark_runs
                   SET status=?, total_prompts=?, completed_prompts=?, completed_at=?
                   WHERE id=?""",
                (status, total_prompts, completed_prompts, completed_at, run_id),
            )

    def get_run(self, run_id: int) -> Optional[BenchmarkRun]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM benchmark_runs WHERE id=?", (run_id,)
            ).fetchone()
            return BenchmarkRun(**dict(row)) if row else None

    def list_runs(self, limit: int = 50) -> list[BenchmarkRun]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM benchmark_runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [BenchmarkRun(**dict(r)) for r in rows]

    def list_runs_by_model(self, model_id: int) -> list[BenchmarkRun]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM benchmark_runs WHERE model_id=? ORDER BY started_at DESC",
                (model_id,),
            ).fetchall()
            return [BenchmarkRun(**dict(r)) for r in rows]

    # ── Prompts ─────────────────────────────

    def upsert_prompt(self, prompt_dict: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO prompts (id, category, subcategory, weight, prompt_text,
                   expected_format, expected_answer, expected_behavior, deterministic_checks)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO NOTHING""",
                (
                    prompt_dict["id"],
                    prompt_dict.get("category", ""),
                    prompt_dict.get("subcategory", ""),
                    prompt_dict.get("weight", 1.0),
                    prompt_dict["prompt"],
                    prompt_dict.get("expected_format"),
                    prompt_dict.get("expected_answer"),
                    prompt_dict.get("expected_behavior"),
                    json.dumps(prompt_dict.get("deterministic_checks"))
                    if prompt_dict.get("deterministic_checks") else None,
                ),
            )

    def get_prompt(self, prompt_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM prompts WHERE id=?", (prompt_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_prompts_by_category(self, category: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM prompts WHERE category=? ORDER BY id", (category,)
            ).fetchall()
            return [dict(r) for r in rows]

    def list_all_prompts(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM prompts ORDER BY category, subcategory, id"
            ).fetchall()
            return [dict(r) for r in rows]

    def list_categories(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM prompts ORDER BY category"
            ).fetchall()
            return [r["category"] for r in rows]

    def import_prompts_from_dir(self, prompts_dir: str | Path) -> int:
        """Importa tutti i prompt JSON da directory ricorsivamente. Restituisce count."""
        prompts_dir = Path(prompts_dir)
        count = 0
        for json_file in sorted(prompts_dir.rglob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                prompts_list = data if isinstance(data, list) else [data]
                for p in prompts_list:
                    if "id" not in p or "prompt" not in p:
                        logger.warning("Prompt senza id/prompt in %s, saltato", json_file)
                        continue
                    self.upsert_prompt(p)
                    count += 1
            except json.JSONDecodeError as e:
                logger.error("JSON invalido in %s: %s", json_file, e)
        logger.info("Importati %d prompt da %s", count, prompts_dir)
        return count

    # ── Results ─────────────────────────────

    def insert_result(self, result: BenchmarkResult) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO benchmark_results
                   (run_id, prompt_id, model_id, prompt_snapshot_text,
                    expected_answer_snapshot, deterministic_checks_snapshot,
                    response_text, latency_ms,
                    prompt_tokens, thinking_tokens, answer_tokens, total_tokens,
                    tokens_per_sec, char_count, line_count, json_valid, format_valid)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    result.run_id, result.prompt_id, result.model_id,
                    result.prompt_snapshot_text,
                    result.expected_answer_snapshot,
                    result.deterministic_checks_snapshot,
                    result.response_text, result.latency_ms,
                    result.prompt_tokens, result.thinking_tokens,
                    result.answer_tokens, result.total_tokens,
                    result.tokens_per_sec, result.char_count, result.line_count,
                    result.json_valid, result.format_valid,
                ),
            )
            return cur.fetchone()["id"]

    def get_results_by_run(self, run_id: int) -> list[BenchmarkResult]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM benchmark_results WHERE run_id=? ORDER BY id", (run_id,)
            ).fetchall()
            return [BenchmarkResult(**dict(r)) for r in rows]

    def get_result_count_by_run(self, run_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM benchmark_results WHERE run_id=?", (run_id,)
            ).fetchone()
            return row["cnt"]

    # ── Scores ──────────────────────────────

    def insert_score(self, score: JudgeScore) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO judge_scores
                   (result_id, judge_model, judge_provider, accuracy, reasoning,
                    coding, hallucination_risk, overall, notes, retry_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    score.result_id, score.judge_model, score.judge_provider,
                    score.accuracy, score.reasoning, score.coding,
                    score.hallucination_risk, score.overall,
                    score.notes, score.retry_count,
                ),
            )
            return cur.fetchone()["id"]

    def get_scores_by_run(self, run_id: int) -> list[JudgeScore]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT js.* FROM judge_scores js
                   JOIN benchmark_results br ON js.result_id = br.id
                   WHERE br.run_id=? ORDER BY js.id""",
                (run_id,),
            ).fetchall()
            return [JudgeScore(**dict(r)) for r in rows]

    def get_score_by_result(self, result_id: int) -> Optional[JudgeScore]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM judge_scores WHERE result_id=?", (result_id,)
            ).fetchone()
            return JudgeScore(**dict(row)) if row else None

    # ── Deterministic Scores ─────────────────

    def insert_deterministic_score(self, score: DeterministicScore) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO deterministic_scores
                   (result_id, exact_match, allowed_values, forbidden_text, json_valid,
                    required_json_keys, format_valid, regex_match,
                    expected_tools, tool_sequence, expected_keywords,
                    strict_compliance, semantic_correctness,
                    overall, performed_checks, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    score.result_id,
                    score.exact_match, score.allowed_values, score.forbidden_text,
                    score.json_valid, score.required_json_keys,
                    score.format_valid, score.regex_match,
                    score.expected_tools, score.tool_sequence, score.expected_keywords,
                    score.strict_compliance, score.semantic_correctness,
                    score.overall, score.performed_checks, score.details,
                ),
            )
            return cur.fetchone()["id"]

    def get_deterministic_score(self, result_id: int) -> Optional[DeterministicScore]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM deterministic_scores WHERE result_id=?", (result_id,)
            ).fetchone()
            return DeterministicScore(**dict(row)) if row else None

    def get_deterministic_scores_by_run(self, run_id: int) -> list[DeterministicScore]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT ds.* FROM deterministic_scores ds
                   JOIN benchmark_results br ON ds.result_id = br.id
                   WHERE br.run_id=? ORDER BY ds.id""",
                (run_id,),
            ).fetchall()
            return [DeterministicScore(**dict(r)) for r in rows]

    # ── Composite Scores ─────────────────────

    def insert_composite_score(self, score: CompositeScoreRecord) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO composite_scores
                   (result_id, composite_score, judge_overall, deterministic_overall,
                    prompt_weight, scoring_version)
                   VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    score.result_id,
                    score.composite_score,
                    score.judge_overall,
                    score.deterministic_overall,
                    score.prompt_weight,
                    score.scoring_version,
                ),
            )
            return cur.fetchone()["id"]

    def get_composite_score(self, result_id: int) -> Optional[CompositeScoreRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM composite_scores WHERE result_id=?", (result_id,)
            ).fetchone()
            return CompositeScoreRecord(**dict(row)) if row else None

    def get_composite_scores_by_run(self, run_id: int) -> list[CompositeScoreRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT cs.* FROM composite_scores cs
                   JOIN benchmark_results br ON cs.result_id = br.id
                   WHERE br.run_id=? ORDER BY cs.id""",
                (run_id,),
            ).fetchall()
            return [CompositeScoreRecord(**dict(r)) for r in rows]

    # ── Ranking / Reports ───────────────────

    def get_model_ranking(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM v_model_ranking ORDER BY overall_rank DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_historical_trend(self, model_name: str, provider: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT br.started_at, br.suite,
                   COALESCE(AVG(cs.composite_score), AVG(js.overall)) as avg_overall,
                   AVG(br_e.latency_ms) as avg_latency_ms
                   FROM benchmark_runs br
                   JOIN benchmark_results br_e ON br_e.run_id = br.id
                   JOIN judge_scores js ON js.result_id = br_e.id
                   LEFT JOIN composite_scores cs ON cs.result_id = br_e.id
                   JOIN models m ON m.id = br.model_id
                   WHERE m.name=? AND m.provider=?
                   GROUP BY br.id, br.started_at
                   ORDER BY br.started_at""",
                (model_name, provider),
            ).fetchall()
            return [dict(r) for r in rows]
