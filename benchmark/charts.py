"""Charts generator — grafici matplotlib da dati SQLite.

I grafici sono generati dai dati salvati. Mai ricalcolare benchmark.
Output: PNG 1200×800, DPI 100.
"""

from __future__ import annotations

import logging
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless, no GUI

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from benchmark.database import DatabaseManager

logger = logging.getLogger(__name__)

# Stile dark coerente con report HTML
DARK_BG = "#0d1117"
CARD_BG = "#161b22"
TEXT_COLOR = "#c9d1d9"
ACCENT = "#58a6ff"
GREEN = "#3fb950"
YELLOW = "#d29922"
RED = "#f85149"


class ChartGenerator:
    """Genera grafici per benchmark."""

    def __init__(self, db: DatabaseManager, output_dir: str | Path = "charts"):
        self.db = db
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── Bar Chart: Ranking ──────────────────

    def bar_chart_ranking(self, run_ids: list[int], title: str = "Model Ranking") -> Path:
        """Bar chart confronto modelli per overall score."""
        data: list[tuple[str, float, float]] = []  # (label, overall, latency)

        for run_id in run_ids:
            run = self.db.get_run(run_id)
            if run is None:
                continue
            model = self.db.get_model(run.model_id)
            scores = self.db.get_scores_by_run(run_id)
            results = self.db.get_results_by_run(run_id)

            if not scores:
                continue

            label = f"{model.name if model else '?'}\n({run.suite})"
            avg_overall = statistics.mean(s.overall for s in scores)
            avg_latency = statistics.mean(r.latency_ms for r in results) if results else 0
            data.append((label, avg_overall, avg_latency))

        if not data:
            logger.warning("Nessun dato per bar_chart_ranking")
            return self.output_dir / "empty.png"

        # Ordina per overall
        data.sort(key=lambda x: x[1], reverse=True)

        fig, ax = plt.subplots(figsize=(12, 8))
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(CARD_BG)

        labels = [d[0] for d in data]
        values = [d[1] for d in data]
        colors = [
            GREEN if v > 0.7 else (YELLOW if v > 0.4 else RED)
            for v in values
        ]

        bars = ax.barh(labels, values, color=colors, height=0.6)
        ax.set_xlim(0, 1.0)
        ax.set_xlabel("Overall Score", color=TEXT_COLOR, fontsize=11)
        ax.set_title(title, color=ACCENT, fontsize=14, fontweight="bold")
        ax.tick_params(colors=TEXT_COLOR, labelsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#30363d")
        ax.spines["bottom"].set_color("#30363d")

        # Valori sulle barre
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:.2f}", va="center", color=TEXT_COLOR, fontsize=9,
            )

        plt.tight_layout()
        output_path = self.output_dir / f"ranking_{_safe_filename(title)}.png"
        fig.savefig(output_path, dpi=100, facecolor=DARK_BG, edgecolor="none")
        plt.close(fig)
        logger.info("Bar chart salvato: %s", output_path)
        return output_path

    # ── Line Chart: Historical Trend ────────

    def line_chart_trend(
        self, model_name: str, provider: str, title: str = ""
    ) -> Path:
        """Line chart trend storico per un modello."""
        trend = self.db.get_historical_trend(model_name, provider)
        if not trend:
            logger.warning("Nessun trend per %s/%s", model_name, provider)
            return self.output_dir / "empty.png"

        dates = [t["started_at"][:10] for t in trend]
        overalls = [t["avg_overall"] for t in trend]
        latencies = [t["avg_latency_ms"] for t in trend]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
        fig.patch.set_facecolor(DARK_BG)
        ax1.set_facecolor(CARD_BG)
        ax2.set_facecolor(CARD_BG)

        title_text = title or f"Historical Trend — {model_name} ({provider})"

        # Overall
        ax1.plot(dates, overalls, color=ACCENT, marker="o", linewidth=2, markersize=6)
        ax1.set_ylabel("Overall Score", color=TEXT_COLOR, fontsize=11)
        ax1.set_title(title_text, color=ACCENT, fontsize=14, fontweight="bold")
        ax1.set_ylim(0, 1.0)
        ax1.fill_between(range(len(overalls)), overalls, alpha=0.15, color=ACCENT)
        ax1.tick_params(colors=TEXT_COLOR, labelsize=9)
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)
        ax1.spines["left"].set_color("#30363d")
        ax1.spines["bottom"].set_color("#30363d")

        # Grid
        ax1.grid(axis="y", color="#30363d", linestyle="--", alpha=0.5)

        # Latency
        ax2.plot(dates, latencies, color=GREEN, marker="s", linewidth=2, markersize=6)
        ax2.set_xlabel("Data", color=TEXT_COLOR, fontsize=11)
        ax2.set_ylabel("Latency (ms)", color=TEXT_COLOR, fontsize=11)
        ax2.tick_params(colors=TEXT_COLOR, labelsize=9)
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_visible(False)
        ax2.spines["left"].set_color("#30363d")
        ax2.spines["bottom"].set_color("#30363d")
        ax2.grid(axis="y", color="#30363d", linestyle="--", alpha=0.5)

        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        output_path = self.output_dir / f"trend_{_safe_filename(model_name)}.png"
        fig.savefig(output_path, dpi=100, facecolor=DARK_BG, edgecolor="none")
        plt.close(fig)
        logger.info("Trend chart salvato: %s", output_path)
        return output_path

    # ── Radar Chart: Model Profile ──────────

    def radar_chart_model(self, run_id: int, title: str = "") -> Path:
        """Radar chart metriche per un modello."""
        import numpy as np

        run = self.db.get_run(run_id)
        scores = self.db.get_scores_by_run(run_id)
        if not scores:
            logger.warning("Nessun dato per radar_chart (run %d)", run_id)
            return self.output_dir / "empty.png"

        model = self.db.get_model(run.model_id) if run else None

        categories = ["Accuracy", "Reasoning", "Coding", "Overall", "Halluc.↓"]
        values = [
            statistics.mean(s.accuracy for s in scores),
            statistics.mean(s.reasoning for s in scores),
            statistics.mean(s.coding for s in scores),
            statistics.mean(s.overall for s in scores),
            1.0 - statistics.mean(s.hallucination_risk for s in scores),  # invertito
        ]

        N = len(categories)
        angles = [n / float(N) * 2 * np.pi for n in range(N)]
        angles += angles[:1]
        values += values[:1]

        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(CARD_BG)

        ax.fill(angles, values, alpha=0.25, color=ACCENT)
        ax.plot(angles, values, color=ACCENT, linewidth=2)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, color=TEXT_COLOR, fontsize=11)
        ax.set_ylim(0, 1.0)
        ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], color="#8b949e", fontsize=8)
        ax.spines["polar"].set_color("#30363d")

        title_text = title or f"Model Profile — {model.name if model else '?'}"
        ax.set_title(title_text, color=ACCENT, fontsize=14, fontweight="bold", pad=20)

        plt.tight_layout()
        output_path = self.output_dir / f"radar_{_safe_filename(title_text)}.png"
        fig.savefig(output_path, dpi=100, facecolor=DARK_BG, edgecolor="none")
        plt.close(fig)
        logger.info("Radar chart salvato: %s", output_path)
        return output_path

    # ── Generate All Charts ─────────────────

    def generate_all_charts(self, run_id: int) -> list[Path]:
        """Genera tutti i grafici per una run."""
        paths: list[Path] = []

        # Ranking
        ranking_path = self.bar_chart_ranking([run_id], title="Model Ranking")
        paths.append(ranking_path)

        # Radar
        radar_path = self.radar_chart_model(run_id)
        paths.append(radar_path)

        # Trend
        run = self.db.get_run(run_id)
        if run:
            model = self.db.get_model(run.model_id)
            if model:
                trend_path = self.line_chart_trend(
                    model.name, model.provider,
                    title=f"Trend — {model.name}",
                )
                paths.append(trend_path)

        logger.info("Generati %d grafici per run %d", len(paths), run_id)
        return paths


def _safe_filename(text: str) -> str:
    """Rimuove caratteri non validi per filename."""
    import re
    return re.sub(r"[^\w\-]", "_", text)[:80]
