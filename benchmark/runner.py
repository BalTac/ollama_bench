"""Runner — orchestrazione benchmark.

Orchestra il flusso: prompt → target model → metrics → deterministic checks → judge → score → SQLite.
Crash-safe: ogni risultato salvato immediatamente dopo valutazione.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import yaml

from benchmark.database import (
    BenchmarkResult,
    BenchmarkRun,
    CompositeScoreRecord,
    DatabaseManager,
    DeterministicScore as DBDeterministicScore,
    JudgeScore as DBJudgeScore,
)
from benchmark.deterministic_scoring import DeterministicResults, run_deterministic_checks
from benchmark.judge import Judge, JudgeScore
from benchmark.metrics import ExtractedMetrics, extract_metrics
from benchmark.prompts import get_prompts_by_category, list_available_categories
from benchmark.providers import get_provider
from benchmark.providers.base import BaseProvider
from benchmark.scoring import CompositeScore, compute_score, compute_suite_score

logger = logging.getLogger(__name__)


class Runner:
    """Esegue benchmark completi."""

    def __init__(self, config_path: str | Path = "config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._setup_logging()

        # Path
        self.prompts_dir = Path(self.config.get("paths", {}).get("prompts_dir", "prompts"))
        self.db_path = Path(self.config.get("paths", {}).get("db_path", "db/benchmark.db"))

        # Database
        self.db = DatabaseManager(self.db_path)
        self.db.init_db()

        # Importa prompt automaticamente
        self.db.import_prompts_from_dir(self.prompts_dir)

        # Provider cache
        self._providers: dict[str, BaseProvider] = {}

        logger.info("Runner inizializzato con config: %s", self.config_path)

    def _load_config(self) -> dict:
        """Carica config.yaml."""
        if not self.config_path.exists():
            logger.warning("config.yaml non trovato: %s", self.config_path)
            return {}
        with open(self.config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _setup_logging(self) -> None:
        """Configura logging da config."""
        log_config = self.config.get("logging", {})
        level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
        log_file = log_config.get("file", "")
        if log_file:
            logging.basicConfig(
                level=level,
                format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                handlers=[
                    logging.FileHandler(log_file, encoding="utf-8"),
                    logging.StreamHandler(),
                ],
            )
        else:
            logging.basicConfig(
                level=level,
                format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            )

    def _get_provider(self, name: str) -> BaseProvider:
        """Recupera provider (con cache)."""
        if name not in self._providers:
            self._providers[name] = get_provider(name, self.config)
        return self._providers[name]

    # ── Main Benchmark ──────────────────────

    def run_benchmark(
        self,
        model: str,
        provider: str = "ollama",
        suite: str = "all",
        judge_provider_name: Optional[str] = None,
        judge_model: Optional[str] = None,
    ) -> dict:
        """Esegue benchmark per un modello su una (o tutte) le suite.

        Args:
            model: Nome modello da testare
            provider: Provider name (ollama, deepseek, openrouter)
            suite: Suite da eseguire ('all' per tutte)
            judge_provider_name: Provider del giudice (default da config)
            judge_model: Modello giudice (default da config)

        Returns:
            dict con risultati aggregati per suite
        """
        # Provider e modello
        target_provider = self._get_provider(provider)

        # Judge config
        judge_cfg = self.config.get("judge", {})
        if judge_provider_name is None:
            judge_provider_name = judge_cfg.get("provider", "deepseek")
        if judge_model is None:
            judge_model = judge_cfg.get("model", "deepseek-chat")

        judge_provider = self._get_provider(judge_provider_name)
        judge = Judge(
            provider=judge_provider,
            model=judge_model,
            max_retries=judge_cfg.get("max_retries", 1),
        )

        # Registra modello
        model_id = self.db.upsert_model(model, provider)

        # Suite da eseguire
        if suite == "all":
            suites = list_available_categories(self.prompts_dir)
        else:
            suites = [suite]

        logger.info("Benchmark avviato: model=%s, provider=%s, suites=%s", model, provider, suites)

        all_results: dict[str, dict] = {}

        for cat in suites:
            suite_result = self._run_suite(
                target_provider=target_provider,
                target_provider_name=provider,
                model=model,
                model_id=model_id,
                judge=judge,
                judge_model=judge_model,
                judge_provider_name=judge_provider_name,
                suite=cat,
            )
            all_results[cat] = suite_result

        return all_results

    def _run_suite(
        self,
        target_provider: BaseProvider,
        target_provider_name: str,
        model: str,
        model_id: int,
        judge: Judge,
        judge_model: str,
        judge_provider_name: str,
        suite: str,
    ) -> dict:
        """Esegue benchmark su una suite specifica."""
        prompts = get_prompts_by_category(self.prompts_dir, suite)
        if not prompts:
            logger.warning("Nessun prompt per suite '%s'", suite)
            return {"status": "no_prompts", "prompt_count": 0}

        logger.info("Suite '%s': %d prompt da eseguire", suite, len(prompts))

        # Crea run
        run_id = self.db.create_run(
            model_id=model_id,
            target_provider=target_provider_name,
            suite=suite,
            judge_model=judge_model,
            judge_provider=judge_provider_name,
        )

        self.db.update_run_status(run_id, "running", total_prompts=len(prompts))

        scores: list[CompositeScore] = []
        completed = 0
        failed = 0

        for i, prompt_info in enumerate(prompts):
            prompt_id = prompt_info["id"]
            logger.info("[%d/%d] Prompt %s", i + 1, len(prompts), prompt_id)

            try:
                composite = self._execute_single_prompt(
                    target_provider=target_provider,
                    model=model,
                    model_id=model_id,
                    run_id=run_id,
                    judge=judge,
                    judge_model=judge_model,
                    judge_provider_name=judge_provider_name,
                    prompt_info=prompt_info,
                )
                scores.append(composite)
                completed += 1

                # Crash-safe: aggiorna progresso dopo ogni prompt
                self.db.update_run_status(
                    run_id, "running",
                    total_prompts=len(prompts),
                    completed_prompts=completed,
                )

            except Exception as e:
                logger.error("Prompt %s fallito: %s", prompt_id, e)
                failed += 1
                # Continua con prossimo prompt (non perdere risultati già salvati)
                continue

        # Finalizza run
        if completed == 0:
            status = "failed"
        elif completed < len(prompts):
            status = "partial_failed"
        else:
            status = "completed"

        self.db.update_run_status(
            run_id, status,
            total_prompts=len(prompts),
            completed_prompts=completed,
        )

        suite_scores = compute_suite_score(scores)
        logger.info(
            "Suite '%s' completata: %d/%d prompt, avg_overall=%.3f",
            suite, completed, len(prompts), suite_scores.get("avg_weighted_score", 0.0),
        )

        return {
            "run_id": run_id,
            "status": status,
            "completed_prompts": completed,
            "failed_prompts": failed,
            "total_prompts": len(prompts),
            "failure_ratio": (failed / len(prompts)) if prompts else 0.0,
            **suite_scores,
        }

    def _execute_single_prompt(
        self,
        target_provider: BaseProvider,
        model: str,
        model_id: int,
        run_id: int,
        judge: Judge,
        judge_model: str,
        judge_provider_name: str,
        prompt_info: dict,
    ) -> CompositeScore:
        """Esegue singolo prompt: genera → metrics → judge → score → persist."""

        prompt_text = prompt_info["prompt"]
        prompt_id = prompt_info["id"]
        weight = prompt_info.get("weight", 1.0)
        expected_format = prompt_info.get("expected_format")
        expected_answer = prompt_info.get("expected_answer")
        expected_behavior = prompt_info.get("expected_behavior")
        deterministic_checks = prompt_info.get("deterministic_checks")

        # 1. Genera risposta
        response = target_provider.generate(prompt=prompt_text, model=model)

        # 2. Estrai metriche
        metrics = extract_metrics(
            response_text=response.text,
            prompt_tokens=response.prompt_tokens,
            thinking_tokens=response.thinking_tokens,
            answer_tokens=response.answer_tokens,
            total_tokens=response.total_tokens,
            latency_ms=response.latency_ms,
            expected_format=expected_format,
        )

        # 3. Salva risultato metriche
        result = BenchmarkResult(
            run_id=run_id,
            prompt_id=prompt_id,
            model_id=model_id,
            prompt_snapshot_text=prompt_text,
            expected_answer_snapshot=expected_answer,
            deterministic_checks_snapshot=(
                json.dumps(deterministic_checks, ensure_ascii=False)
                if deterministic_checks is not None else None
            ),
            response_text=response.text,
            latency_ms=metrics.latency_ms,
            prompt_tokens=metrics.prompt_tokens,
            thinking_tokens=metrics.thinking_tokens,
            answer_tokens=metrics.answer_tokens,
            total_tokens=metrics.total_tokens,
            tokens_per_sec=metrics.tokens_per_sec,
            char_count=metrics.char_count,
            line_count=metrics.line_count,
            json_valid=metrics.json_valid,
            format_valid=metrics.format_valid,
        )
        result_id = self.db.insert_result(result)

        # 3.5 Esegui check deterministici (PRIMA del giudice)
        det_results = DeterministicResults()

        if deterministic_checks:
            logger.info(
                "Check deterministici per prompt %s: %s",
                prompt_id, list(deterministic_checks.keys()) if isinstance(deterministic_checks, dict) else "?",
            )
            det_results = run_deterministic_checks(response.text, deterministic_checks)

            det_db = DBDeterministicScore(
                result_id=result_id,
                exact_match=det_results.exact_match,
                allowed_values=det_results.allowed_values,
                forbidden_text=det_results.forbidden_text,
                json_valid=det_results.json_valid,
                required_json_keys=det_results.required_json_keys,
                format_valid=det_results.format_valid,
                regex_match=det_results.regex_match,
                expected_tools=det_results.expected_tools,
                tool_sequence=det_results.tool_sequence,
                expected_keywords=det_results.expected_keywords,
                strict_compliance=det_results.strict_compliance,
                semantic_correctness=det_results.semantic_correctness,
                overall=det_results.overall,
                performed_checks=json.dumps(det_results.performed_checks),
                details=json.dumps(det_results.details, ensure_ascii=False),
            )
            self.db.insert_deterministic_score(det_db)
            logger.info(
                "Deterministic checks salvati per prompt %s: overall=%.3f",
                prompt_id, det_results.overall,
            )

        # 4. Valuta con giudice (SOLO metriche soggettive)
        deterministic_info = None
        if det_results.performed_checks:
            info_parts = [
                "Check deterministici già eseguiti "
                f"(overall={det_results.overall:.2f}, "
                f"strict={det_results.strict_compliance:.2f}, "
                f"semantic={det_results.semantic_correctness:.2f}):"
            ]
            for check_name in det_results.performed_checks:
                info_parts.append(
                    f"  - {check_name}: {det_results.details.get(check_name, '?')} "
                    f"(score {getattr(det_results, check_name, 0):.2f})"
                )
            deterministic_info = "\n".join(info_parts)

        logger.info("Chiamata judge per prompt %s (model=%s)...", prompt_id, judge_model)
        judge_score = judge.evaluate(
            prompt_text=prompt_text,
            response_text=response.text,
            deterministic_info=deterministic_info,
        )
        logger.info(
            "Judge completato per prompt %s: overall=%.3f",
            prompt_id, judge_score.overall,
        )

        # 5. Salva score giudice
        db_score = DBJudgeScore(
            result_id=result_id,
            judge_model=judge_model,
            judge_provider=judge_provider_name,
            accuracy=judge_score.accuracy,
            reasoning=judge_score.reasoning,
            coding=judge_score.coding,
            hallucination_risk=judge_score.hallucination_risk,
            overall=judge_score.overall,
            notes=judge_score.notes,
            retry_count=0,
        )
        self.db.insert_score(db_score)

        # 6. Calcola score composito (ibrido se deterministico)
        composite = compute_score(metrics, judge_score, weight, det_results)
        self.db.insert_composite_score(
            CompositeScoreRecord(
                result_id=result_id,
                composite_score=composite.weighted_score,
                judge_overall=composite.judge_overall,
                deterministic_overall=composite.det_overall,
                prompt_weight=weight,
                scoring_version="v2_quality_only",
            )
        )
        logger.debug(
            "Prompt %s: weighted=%.3f, judge_overall=%.2f, det_overall=%.2f, latency=%.0fms",
            prompt_id, composite.weighted_score, composite.judge_overall,
            composite.det_overall, composite.latency_ms,
        )

        return composite

    # ── Compare Models ──────────────────────

    def compare_models(
        self,
        models: list[str],
        provider: str = "ollama",
        suite: str = "all",
    ) -> list[dict]:
        """Esegue benchmark per più modelli e restituisce confronto.

        Args:
            models: Lista nomi modello
            provider: Provider
            suite: Suite

        Returns:
            Lista risultati per modello
        """
        results = []
        for model in models:
            logger.info("Benchmark confronto: model=%s", model)
            result = self.run_benchmark(model=model, provider=provider, suite=suite)
            results.append({"model": model, "provider": provider, "results": result})
        return results

    # ── Utility ─────────────────────────────

    def list_available_models(self, provider: str = "ollama") -> list[str]:
        """Elenca modelli disponibili per un provider."""
        p = self._get_provider(provider)
        return p.list_models()

    def list_available_providers(self) -> list[str]:
        """Elenca provider configurati con disponibilità."""
        from benchmark.providers import list_available_providers as _list

        available = []
        for name in _list():
            try:
                p = self._get_provider(name)
                ok = p.is_available()
            except Exception:
                ok = False
            available.append(name)
        return available
