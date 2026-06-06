"""Report generator — JSON, CSV, HTML da dati SQLite.

Tutti i report derivano dal database. Mai ricalcolare benchmark.
"""

from __future__ import annotations

import csv
import datetime
import json
import logging
from pathlib import Path
from typing import Optional

from benchmark.database import DatabaseManager

logger = logging.getLogger(__name__)

# Policy minima di validita statistica (M17)
MIN_PROMPTS_MINIMUM = 10
MIN_PROMPTS_RECOMMENDED = 30
MAX_FAILURE_RATIO_RECOMMENDED = 0.10


class ReportGenerator:
    """Genera report in formati JSON, CSV, HTML."""

    def __init__(self, db: DatabaseManager, output_dir: str | Path = "reports"):
        self.db = db
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── JSON ───────────────────────────────

    def generate_json_report(self, run_id: int) -> dict:
        """Genera report JSON completo per una run."""
        run = self.db.get_run(run_id)
        if run is None:
            raise ValueError(f"Run non trovata: {run_id}")

        results = self.db.get_results_by_run(run_id)
        model = self.db.get_model(run.model_id)

        report = {
            "report_type": "benchmark_run",
            "generated_at": datetime.datetime.now().isoformat(),
            "run": {
                "id": run.id,
                "suite": run.suite,
                "status": run.status,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "total_prompts": run.total_prompts,
                "completed_prompts": run.completed_prompts,
                "failed_prompts": max(0, (run.total_prompts or 0) - (run.completed_prompts or 0)),
                "failure_ratio": (
                    max(0, (run.total_prompts or 0) - (run.completed_prompts or 0)) / (run.total_prompts or 1)
                ),
            },
            "model": {
                "name": model.name if model else "unknown",
                "provider": run.target_provider,
            },
            "judge": {
                "model": run.judge_model,
                "provider": run.judge_provider,
            },
            "results": [],
            "summary": {},
        }

        stat_policy = _statistical_validity_policy(
            completed_prompts=run.completed_prompts or 0,
            total_prompts=run.total_prompts or 0,
        )
        report["statistical_validity_policy"] = stat_policy

        judge_scores = []
        composite_scores = []
        for r in results:
            score = self.db.get_score_by_result(r.id)
            det_score = self.db.get_deterministic_score(r.id)
            comp_score = self.db.get_composite_score(r.id)
            entry = {
                "prompt_id": r.prompt_id,
                "response_text": r.response_text[:500],
                "prompt_snapshot": {
                    "prompt": r.prompt_snapshot_text,
                    "expected_answer": r.expected_answer_snapshot,
                    "deterministic_checks": (
                        json.loads(r.deterministic_checks_snapshot)
                        if r.deterministic_checks_snapshot else None
                    ),
                },
                "metrics": {
                    "latency_ms": r.latency_ms,
                    "prompt_tokens": r.prompt_tokens,
                    "answer_tokens": r.answer_tokens,
                    "total_tokens": r.total_tokens,
                    "tokens_per_sec": r.tokens_per_sec,
                    "char_count": r.char_count,
                    "line_count": r.line_count,
                    "json_valid": bool(r.json_valid),
                    "format_valid": bool(r.format_valid),
                },
            }
            if det_score:
                entry["deterministic_scores"] = {
                    "overall": det_score.overall,
                    "strict_compliance": det_score.strict_compliance,
                    "semantic_correctness": det_score.semantic_correctness,
                    "exact_match": det_score.exact_match,
                    "allowed_values": det_score.allowed_values,
                    "forbidden_text": det_score.forbidden_text,
                    "json_valid": det_score.json_valid,
                    "required_json_keys": det_score.required_json_keys,
                    "format_valid": det_score.format_valid,
                    "regex_match": det_score.regex_match,
                    "expected_tools": det_score.expected_tools,
                    "tool_sequence": det_score.tool_sequence,
                    "expected_keywords": det_score.expected_keywords,
                    "performed_checks": det_score.performed_checks,
                }
            if score:
                entry["judge_scores"] = {
                    "accuracy": score.accuracy,
                    "reasoning": score.reasoning,
                    "coding": score.coding,
                    "hallucination_risk": score.hallucination_risk,
                    "overall": score.overall,
                    "notes": score.notes,
                }
                judge_scores.append(score)
            if comp_score:
                entry["composite_score"] = {
                    "score": comp_score.composite_score,
                    "judge_overall": comp_score.judge_overall,
                    "deterministic_overall": comp_score.deterministic_overall,
                    "prompt_weight": comp_score.prompt_weight,
                    "scoring_version": comp_score.scoring_version,
                }
                composite_scores.append(comp_score)
            report["results"].append(entry)

        # Summary
        if judge_scores:
            avg_tps = sum((r.tokens_per_sec or 0) for r in results) / len(results)
            report["summary"] = {
                "avg_judge_overall": sum(s.overall for s in judge_scores) / len(judge_scores),
                "avg_composite": (
                    sum(c.composite_score for c in composite_scores) / len(composite_scores)
                    if composite_scores else None
                ),
                "avg_quality_score": (
                    sum(c.composite_score for c in composite_scores) / len(composite_scores)
                    if composite_scores else (sum(s.overall for s in judge_scores) / len(judge_scores))
                ),
                "avg_performance_score": min(1.0, avg_tps / 100.0),
                "avg_accuracy": sum(s.accuracy for s in judge_scores) / len(judge_scores),
                "avg_reasoning": sum(s.reasoning for s in judge_scores) / len(judge_scores),
                "avg_coding": sum(s.coding for s in judge_scores) / len(judge_scores),
                "avg_latency_ms": sum(r.latency_ms for r in results) / len(results),
                "prompt_count": len(results),
                "statistical_validity_status": stat_policy["status"],
            }

        # Salva su file
        output_path = self.output_dir / f"report_{run_id}.json"
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Report JSON salvato: %s", output_path)

        return report

    # ── CSV ────────────────────────────────

    def generate_csv_report(self, run_id: int) -> Path:
        """Genera report CSV per una run."""
        results = self.db.get_results_by_run(run_id)
        if not results:
            raise ValueError(f"Nessun risultato per run {run_id}")

        output_path = self.output_dir / f"report_{run_id}.csv"

        fieldnames = [
            "prompt_id", "latency_ms", "prompt_tokens", "answer_tokens",
            "total_tokens", "tokens_per_sec", "char_count", "line_count",
            "json_valid", "format_valid",
            "composite_score", "composite_judge_overall", "composite_det_overall", "composite_weight",
            "det_overall", "det_strict_compliance", "det_semantic_correctness",
            "det_exact_match", "det_allowed_values", "det_forbidden_text",
            "det_json_valid", "det_required_json_keys", "det_format_valid",
            "det_regex_match", "det_expected_tools", "det_tool_sequence", "det_expected_keywords",
            "judge_accuracy", "judge_reasoning", "judge_coding",
            "judge_hallucination_risk", "judge_overall",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()

            for r in results:
                score = self.db.get_score_by_result(r.id)
                det_score = self.db.get_deterministic_score(r.id)
                comp_score = self.db.get_composite_score(r.id)
                row = {
                    "prompt_id": r.prompt_id,
                    "latency_ms": r.latency_ms,
                    "prompt_tokens": r.prompt_tokens or 0,
                    "answer_tokens": r.answer_tokens or 0,
                    "total_tokens": r.total_tokens or 0,
                    "tokens_per_sec": round(r.tokens_per_sec or 0, 2),
                    "char_count": r.char_count,
                    "line_count": r.line_count,
                    "json_valid": r.json_valid,
                    "format_valid": r.format_valid,
                }
                if comp_score:
                    row.update({
                        "composite_score": round(comp_score.composite_score, 3),
                        "composite_judge_overall": round(comp_score.judge_overall, 3),
                        "composite_det_overall": _safe_round(comp_score.deterministic_overall),
                        "composite_weight": round(comp_score.prompt_weight, 3),
                    })
                if det_score:
                    row.update({
                        "det_overall": round(det_score.overall, 3),
                        "det_strict_compliance": _safe_round(det_score.strict_compliance),
                        "det_semantic_correctness": _safe_round(det_score.semantic_correctness),
                        "det_exact_match": _safe_round(det_score.exact_match),
                        "det_allowed_values": _safe_round(det_score.allowed_values),
                        "det_forbidden_text": _safe_round(det_score.forbidden_text),
                        "det_json_valid": _safe_round(det_score.json_valid),
                        "det_required_json_keys": _safe_round(det_score.required_json_keys),
                        "det_format_valid": _safe_round(det_score.format_valid),
                        "det_regex_match": _safe_round(det_score.regex_match),
                        "det_expected_tools": _safe_round(det_score.expected_tools),
                        "det_tool_sequence": _safe_round(det_score.tool_sequence),
                        "det_expected_keywords": _safe_round(det_score.expected_keywords),
                    })
                if score:
                    row.update({
                        "judge_accuracy": round(score.accuracy, 3),
                        "judge_reasoning": round(score.reasoning, 3),
                        "judge_coding": round(score.coding, 3),
                        "judge_hallucination_risk": round(score.hallucination_risk, 3),
                        "judge_overall": round(score.overall, 3),
                    })
                writer.writerow(row)

        logger.info("Report CSV salvato: %s", output_path)
        return output_path

    # ── HTML ───────────────────────────────

    def generate_html_report(self, run_id: int) -> Path:
        """Genera report HTML standalone per una run."""
        run = self.db.get_run(run_id)
        if run is None:
            raise ValueError(f"Run non trovata: {run_id}")

        model = self.db.get_model(run.model_id)
        results = self.db.get_results_by_run(run_id)

        # Prepara dati
        rows_html = ""
        overalls = []
        for i, r in enumerate(results):
            score = self.db.get_score_by_result(r.id)
            det_score = self.db.get_deterministic_score(r.id)
            comp_score = self.db.get_composite_score(r.id)
            prompt_text = r.prompt_snapshot_text or ""

            accuracy = score.accuracy if score else 0
            reasoning = score.reasoning if score else 0
            coding = score.coding if score else 0
            hallucination = score.hallucination_risk if score else 0
            judge_overall = score.overall if score else 0
            canonical_overall = comp_score.composite_score if comp_score else judge_overall
            det_overall = det_score.overall if det_score else 0
            overalls.append(canonical_overall)

            det_html = ""
            if det_score and det_score.performed_checks:
                checks = json.loads(det_score.performed_checks) if isinstance(det_score.performed_checks, str) else det_score.performed_checks
                det_badges = []
                for c in checks:
                    val = getattr(det_score, c, None)
                    if val is not None:
                        color = "green" if val > 0.7 else ("yellow" if val > 0.3 else "red")
                        det_badges.append(
                            f'<span style="background:#21262d;padding:2px 6px;border-radius:4px;font-size:.75rem;margin-right:4px;">'
                            f'{c}: <b style="color:var(--{color})">{val:.0%}</b></span>'
                        )
                det_html = "".join(det_badges)

            rows_html += f"""
            <tr>
                <td>{i + 1}</td>
                <td title="{_escape_html(prompt_text[:200])}">{_escape_html(r.prompt_id)}</td>
                <td>{r.latency_ms:.0f}ms</td>
                <td>{r.total_tokens or 0}</td>
                <td>{r.tokens_per_sec:.1f}</td>
                <td>{_score_bar(accuracy)}</td>
                <td>{_score_bar(reasoning)}</td>
                <td>{_score_bar(coding)}</td>
                <td>{_score_bar(hallucination, invert=True)}</td>
                <td><strong>{canonical_overall:.2f}</strong></td>
                <td style="min-width:250px">{det_html} <small>{det_overall:.2f}</small></td>
                <td>{'✓' if r.json_valid else '✗'} {'✓' if r.format_valid else '✗'}</td>
            </tr>"""

        avg_overall = sum(overalls) / len(overalls) if overalls else 0
        failed_prompts = max(0, (run.total_prompts or 0) - (run.completed_prompts or 0))
        failure_ratio = (failed_prompts / run.total_prompts) if (run.total_prompts or 0) > 0 else 0.0
        avg_tps = sum((r.tokens_per_sec or 0) for r in results) / len(results) if results else 0.0
        avg_performance_score = min(1.0, avg_tps / 100.0)
        stat_policy = _statistical_validity_policy(
            completed_prompts=run.completed_prompts or 0,
            total_prompts=run.total_prompts or 0,
        )

        stat_color = "#f85149" if stat_policy["status"] == "insufficient" else (
            "#d29922" if stat_policy["status"] == "minimum_only" else "#3fb950"
        )
        stat_warnings_html = "".join(
            f"<li>{_escape_html(w)}</li>" for w in stat_policy["warnings"]
        )

        html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Benchmark Report — {_escape_html(model.name if model else '?')}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#0d1117; color:#c9d1d9; padding:2rem; }}
h1 {{ color:#58a6ff; margin-bottom:.5rem; }}
h2 {{ color:#8b949e; font-weight:400; margin-bottom:2rem; }}
.card {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:1.5rem; margin-bottom:1.5rem; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:1rem; margin-bottom:2rem; }}
.metric {{ text-align:center; }}
.metric .value {{ font-size:1.8rem; font-weight:700; color:#58a6ff; }}
.metric .label {{ font-size:.8rem; color:#8b949e; margin-top:.3rem; text-transform:uppercase; }}
table {{ width:100%; border-collapse:collapse; }}
th {{ background:#21262d; padding:.6rem .8rem; text-align:left; font-size:.8rem; text-transform:uppercase; color:#8b949e; }}
td {{ padding:.5rem .8rem; border-bottom:1px solid #21262d; font-size:.9rem; }}
tr:hover {{ background:#1c2128; }}
.bar {{ display:inline-block; height:8px; border-radius:4px; background:#30363d; width:100px; vertical-align:middle; }}
.bar-fill {{ height:100%; border-radius:4px; }}
.green {{ background:#3fb950; }}
.yellow {{ background:#d29922; }}
.red {{ background:#f85149; }}
</style>
</head>
<body>
<h1>🤖 LLM Benchmark Report</h1>
<h2>{_escape_html(model.name if model else '?')} · {run.target_provider} · suite: {run.suite}</h2>

<div class="card">
<div class="grid">
<div class="metric"><div class="value">{avg_overall:.2f}</div><div class="label">Quality Score</div></div>
<div class="metric"><div class="value">{avg_performance_score:.2f}</div><div class="label">Performance Score</div></div>
<div class="metric"><div class="value">{run.completed_prompts}/{run.total_prompts}</div><div class="label">Prompt Completati</div></div>
<div class="metric"><div class="value">{failed_prompts} ({failure_ratio:.0%})</div><div class="label">Prompt Falliti</div></div>
<div class="metric"><div class="value">{run.judge_model}</div><div class="label">Giudice</div></div>
<div class="metric"><div class="value">{run.status}</div><div class="label">Stato Run</div></div>
<div class="metric"><div class="value" style="color:{stat_color}">{stat_policy['status']}</div><div class="label">Statistical Validity</div></div>
</div>
</div>

<div class="card">
<h3 style="margin-bottom:.8rem;color:{stat_color};">Policy minima validita statistica</h3>
<div style="margin-bottom:.6rem;">
Completati: <b>{stat_policy['completed_prompts']}</b> / <b>{stat_policy['total_prompts']}</b> ·
soglie: minimo <b>{stat_policy['policy']['min_prompts_minimum']}</b>, raccomandato <b>{stat_policy['policy']['min_prompts_recommended']}</b>
</div>
<ul style="padding-left:1.2rem; line-height:1.5;">{stat_warnings_html or '<li>Nessun warning.</li>'}</ul>
</div>

<div class="card">
<table>
<thead>
<tr>
<th>#</th><th>Prompt</th><th>Latency</th><th>Tokens</th><th>Tok/s</th>
<th>Acc</th><th>Reas</th><th>Code</th><th>Hallu</th>
<th>Judge</th><th>Deterministic</th><th>Valid</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>

<p style="text-align:center;color:#484f58;margin-top:2rem;font-size:.8rem;">
LLM Benchmark Framework · Generato {datetime.datetime.now().isoformat()}
</p>
</body>
</html>"""

        output_path = self.output_dir / f"report_{run_id}.html"
        output_path.write_text(html, encoding="utf-8")
        logger.info("Report HTML salvato: %s", output_path)
        return output_path

    # ── Comparison Report ───────────────────

    def generate_comparison_report(self, run_ids: list[int]) -> Path:
        """Genera HTML di confronto tra più run."""
        runs_data = []
        all_scores: list[dict] = []

        for run_id in run_ids:
            run = self.db.get_run(run_id)
            if run is None:
                continue
            model = self.db.get_model(run.model_id)
            comp_scores = self.db.get_composite_scores_by_run(run_id)
            judge_scores = self.db.get_scores_by_run(run_id)
            avg_overall = (
                sum(s.composite_score for s in comp_scores) / len(comp_scores)
                if comp_scores else (
                    sum(s.overall for s in judge_scores) / len(judge_scores) if judge_scores else 0
                )
            )

            all_scores.append({
                "model": model.name if model else "?",
                "provider": run.target_provider,
                "suite": run.suite,
                "avg_overall": avg_overall,
                "prompt_count": len(comp_scores) if comp_scores else len(judge_scores),
                "stat_policy": _statistical_validity_policy(
                    completed_prompts=run.completed_prompts or 0,
                    total_prompts=run.total_prompts or 0,
                ),
            })

        # Bar chart HTML semplice
        bars_html = ""
        max_score = max((s["avg_overall"] for s in all_scores), default=0.01)
        for s in all_scores:
            pct = (s["avg_overall"] / max_score * 100) if max_score > 0 else 0
            color = "green" if s["avg_overall"] > 0.7 else ("yellow" if s["avg_overall"] > 0.4 else "red")
            stat = s["stat_policy"]
            badge_color = "#f85149" if stat["status"] == "insufficient" else (
                "#d29922" if stat["status"] == "minimum_only" else "#3fb950"
            )
            bars_html += f"""
            <div style="margin-bottom:1rem;">
                <div style="display:flex; justify-content:space-between; margin-bottom:.3rem;">
                    <span><strong>{_escape_html(s['model'])}</strong> <small>({s['provider']})</small></span>
                    <span>{s['avg_overall']:.2f} · {s['prompt_count']} prompt · <b style=\"color:{badge_color};\">{stat['status']}</b></span>
                </div>
                <div class="bar" style="width:100%">
                    <div class="bar-fill {color}" style="width:{pct:.1f}%"></div>
                </div>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="UTF-8"><title>Model Comparison</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#0d1117; color:#c9d1d9; padding:2rem; }}
h1 {{ color:#58a6ff; }}
.card {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:1.5rem; margin:1rem 0; }}
.bar {{ display:inline-block; height:12px; border-radius:6px; background:#30363d; }}
.bar-fill {{ height:100%; border-radius:6px; }}
.green {{ background:#3fb950; }} .yellow {{ background:#d29922; }} .red {{ background:#f85149; }}
</style></head>
<body>
<h1>📊 Model Comparison</h1>
<p style="color:#8b949e;margin:.4rem 0 1rem 0;">Policy statistica: minimo {MIN_PROMPTS_MINIMUM} prompt completati, raccomandato {MIN_PROMPTS_RECOMMENDED}; failure ratio raccomandato <= {MAX_FAILURE_RATIO_RECOMMENDED:.0%}.</p>
<div class="card">{bars_html}</div>
<p style="color:#484f58;font-size:.8rem;text-align:center;margin-top:2rem;">
LLM Benchmark Framework · {datetime.datetime.now().isoformat()}
</p>
</body></html>"""

        output_path = self.output_dir / f"comparison_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        output_path.write_text(html, encoding="utf-8")
        logger.info("Comparison report salvato: %s", output_path)
        return output_path


# ── Helpers ────────────────────────────────

def _safe_round(value: Optional[float], digits: int = 3) -> Optional[float]:
    if value is None:
        return None
    return round(value, digits)


def _statistical_validity_policy(completed_prompts: int, total_prompts: int) -> dict:
    """Valuta policy minima di validita statistica senza CI/effect size."""
    failed_prompts = max(0, total_prompts - completed_prompts)
    failure_ratio = (failed_prompts / total_prompts) if total_prompts > 0 else 0.0

    warnings: list[str] = []
    if completed_prompts < MIN_PROMPTS_MINIMUM:
        status = "insufficient"
        warnings.append(
            f"Campione troppo piccolo: {completed_prompts} prompt completati (< {MIN_PROMPTS_MINIMUM})."
        )
    elif completed_prompts < MIN_PROMPTS_RECOMMENDED:
        status = "minimum_only"
        warnings.append(
            f"Campione minimo raggiunto ma sotto soglia raccomandata ({completed_prompts} < {MIN_PROMPTS_RECOMMENDED})."
        )
    else:
        status = "recommended"

    if failure_ratio > MAX_FAILURE_RATIO_RECOMMENDED:
        warnings.append(
            f"Failure ratio elevato: {failure_ratio:.1%} (> {MAX_FAILURE_RATIO_RECOMMENDED:.0%})."
        )

    return {
        "status": status,
        "completed_prompts": completed_prompts,
        "total_prompts": total_prompts,
        "failed_prompts": failed_prompts,
        "failure_ratio": failure_ratio,
        "policy": {
            "min_prompts_minimum": MIN_PROMPTS_MINIMUM,
            "min_prompts_recommended": MIN_PROMPTS_RECOMMENDED,
            "max_failure_ratio_recommended": MAX_FAILURE_RATIO_RECOMMENDED,
        },
        "warnings": warnings,
    }


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _score_bar(value: float, invert: bool = False) -> str:
    """Barra visuale colorata per score."""
    if invert:
        value = 1.0 - value  # inverti per hallucination (meno è meglio)
    pct = value * 100
    if value > 0.7:
        color = "green"
    elif value > 0.4:
        color = "yellow"
    else:
        color = "red"
    return f'<span class="bar"><span class="bar-fill {color}" style="width:{pct:.0f}%"></span></span> {value:.2f}'
