#!/usr/bin/env python3
"""LLM Benchmark Framework — CLI entry point.

Comandi:
    python benchmark.py run --model MODEL [--provider ollama] [--suite coding]
    python benchmark.py compare --models m1,m2 [--suite coding]
    python benchmark.py list --models [--provider ollama]
    python benchmark.py list --providers
    python benchmark.py list --prompts [--category coding]
    python benchmark.py report --run-id ID [--format json|csv|html]
    python benchmark.py charts --run-id ID
    python benchmark.py import-prompts
    python benchmark.py stats
    python benchmark.py clean --runs|--reports|--all
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sqlite3
import sys
from pathlib import Path

import yaml

from benchmark.runner import Runner
from benchmark.report import ReportGenerator
from benchmark.charts import ChartGenerator
from benchmark.database import DatabaseManager
from benchmark.prompts import list_available_categories
from benchmark.providers import get_provider

logger = logging.getLogger("benchmark")


MIN_PROMPTS_MINIMUM = 10
MIN_PROMPTS_RECOMMENDED = 30
MAX_FAILURE_RATIO_RECOMMENDED = 0.10


def _load_config_file(config_path: str) -> dict:
    """Carica config.yaml senza inizializzare Runner/DB."""
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _resolve_prompts_dir(config_path: str, config: dict) -> Path:
    """Risolvi prompts_dir dalla configurazione (fallback: prompts)."""
    prompts_raw = config.get("paths", {}).get("prompts_dir", "prompts")
    prompts_path = Path(prompts_raw)
    if prompts_path.is_absolute():
        return prompts_path

    base = Path(config_path).parent if Path(config_path).exists() else Path.cwd()
    return (base / prompts_path).resolve()


def cmd_run(args: argparse.Namespace) -> None:
    """Esegue benchmark."""
    runner = Runner(args.config)

    print(f"\n🚀 Benchmark avviato: model={args.model}, provider={args.provider}")
    if args.suite:
        print(f"   Suite: {args.suite}")

    result = runner.run_benchmark(
        model=args.model,
        provider=args.provider,
        suite=args.suite or "all",
    )

    for suite_name, suite_data in result.items():
        status = suite_data.get("status", "?")
        completed = suite_data.get("completed_prompts", 0)
        failed = suite_data.get("failed_prompts", 0)
        total = suite_data.get("total_prompts", 0)
        avg = suite_data.get("avg_weighted_score", 0)
        print(f"  {suite_name}: {status} ({completed}/{total}, failed={failed}) avg={avg:.3f}")

    print("✅ Benchmark completato.\n")

    # Genera report automatici se run_id presente
    for suite_name, suite_data in result.items():
        run_id = suite_data.get("run_id")
        if run_id:
            _auto_report(runner.db, run_id)


def cmd_compare(args: argparse.Namespace) -> None:
    """Confronta più modelli."""
    runner = Runner(args.config)
    models = [m.strip() for m in args.models.split(",")]

    print(f"\n📊 Confronto modelli: {', '.join(models)}")
    results = runner.compare_models(
        models=models,
        provider=args.provider,
        suite=args.suite or "all",
    )

    print("\n┌─────────────────────────────────────────────────────┐")
    print(f"│ {'Model':<20} │ {'Suite':<15} │ {'Score':>8} │")
    print("├─────────────────────────────────────────────────────┤")
    for r in results:
        for suite_name, suite_data in r["results"].items():
            avg = suite_data.get("avg_weighted_score", 0)
            print(f"│ {r['model']:<20} │ {suite_name:<15} │ {avg:>8.3f} │")
    print("└─────────────────────────────────────────────────────┘\n")

    # Genera comparison report
    run_ids = [
        rd.get("run_id")
        for r in results
        for rd in r["results"].values()
        if rd.get("run_id")
    ]
    if len(run_ids) >= 2:
        report_gen = ReportGenerator(runner.db)
        path = report_gen.generate_comparison_report(run_ids)
        print(f"📄 Comparison report: {path}")


def cmd_list(args: argparse.Namespace) -> None:
    """Elenca modelli, provider o prompt."""
    config = _load_config_file(args.config)

    if args.models:
        provider = args.provider or config.get("benchmark", {}).get("default_provider", "ollama")
        try:
            models = get_provider(provider, config).list_models()
            print(f"\n📋 Modelli disponibili ({provider}):")
            if models:
                for m in models:
                    print(f"  - {m}")
            else:
                print("  (nessun modello trovato o provider non raggiungibile)")
        except Exception as e:
            print(f"⚠️  Provider '{provider}' non disponibile: {e}")
        print()

    elif args.providers:
        from benchmark.providers import list_available_providers as _list
        print("\n🔌 Provider configurati:")
        for name in _list():
            try:
                p = get_provider(name, config)
                ok = "✅" if p.is_available() else "❌"
            except Exception:
                ok = "❌"
            print(f"  {ok} {name}")
        print()

    elif args.prompts:
        prompts_dir = _resolve_prompts_dir(args.config, config)
        if args.category:
            from benchmark.prompts import get_prompts_by_category
            prompts = get_prompts_by_category(prompts_dir, args.category)
            print(f"\n📝 Prompt in '{args.category}': {len(prompts)}")
            for p in prompts:
                print(f"  [{p['id']}] {p.get('subcategory','')} - {p['prompt'][:80]}...")
        else:
            categories = list_available_categories(prompts_dir)
            print(f"\n📁 Categorie prompt ({len(categories)}):")
            for cat in categories:
                from benchmark.prompts import get_prompts_by_category
                count = len(get_prompts_by_category(prompts_dir, cat))
                print(f"  {cat}/ ({count} prompt)")
        print()


def cmd_report(args: argparse.Namespace) -> None:
    """Genera report per una run."""
    db_path = args.db or "db/benchmark.db"
    db = DatabaseManager(db_path)
    report_gen = ReportGenerator(db)

    run = db.get_run(args.run_id)
    if run is None:
        print(f"❌ Run {args.run_id} non trovata.")
        return

    fmt = args.format or "all"

    print(f"\n📄 Generazione report per run {args.run_id}...")

    if fmt in ("json", "all"):
        report_gen.generate_json_report(args.run_id)
        print(f"  ✅ JSON: reports/report_{args.run_id}.json")

    if fmt in ("csv", "all"):
        report_gen.generate_csv_report(args.run_id)
        print(f"  ✅ CSV: reports/report_{args.run_id}.csv")

    if fmt in ("html", "all"):
        report_gen.generate_html_report(args.run_id)
        print(f"  ✅ HTML: reports/report_{args.run_id}.html")

    print()


def cmd_charts(args: argparse.Namespace) -> None:
    """Genera grafici per una run."""
    db_path = args.db or "db/benchmark.db"
    db = DatabaseManager(db_path)
    chart_gen = ChartGenerator(db)

    print(f"\n📈 Generazione grafici per run {args.run_id}...")
    paths = chart_gen.generate_all_charts(args.run_id)
    for p in paths:
        print(f"  ✅ {p}")
    print()


def cmd_import_prompts(args: argparse.Namespace) -> None:
    """Importa prompt da directory JSON nel database."""
    db_path = args.db or "db/benchmark.db"
    db = DatabaseManager(db_path)
    db.init_db()
    count = db.import_prompts_from_dir(args.prompts_dir or "prompts")
    print(f"\n📥 Importati {count} prompt nel database.\n")


def cmd_stats(args: argparse.Namespace) -> None:
    """Mostra statistiche del database benchmark."""
    db_path = args.db or "db/benchmark.db"
    db = DatabaseManager(db_path)

    if not Path(db_path).exists():
        print(f"\n⚠️  Database non trovato: {db_path}")
        print("   Esegui almeno un benchmark per crearlo.\n")
        return

    db.init_db()

    # Raccogli statistiche via SQL
    with db._conn() as conn:
        # Numero run
        total_runs = conn.execute(
            "SELECT COUNT(*) FROM benchmark_runs"
        ).fetchone()[0]

        # Run completate
        completed_runs = conn.execute(
            "SELECT COUNT(*) FROM benchmark_runs WHERE status='completed'"
        ).fetchone()[0]

        # Run con fallimenti parziali
        partial_runs = conn.execute(
            "SELECT COUNT(*) FROM benchmark_runs WHERE status='partial_failed'"
        ).fetchone()[0]

        # Numero risultati
        total_results = conn.execute(
            "SELECT COUNT(*) FROM benchmark_results"
        ).fetchone()[0]

        # Numero modelli unici testati
        total_models = conn.execute(
            "SELECT COUNT(DISTINCT name) FROM models"
        ).fetchone()[0]

        # Provider utilizzati
        providers = conn.execute(
            "SELECT DISTINCT provider FROM models ORDER BY provider"
        ).fetchall()
        provider_list = [r[0] for r in providers]

        # Numero prompt nel DB
        total_prompts = conn.execute(
            "SELECT COUNT(*) FROM prompts"
        ).fetchone()[0]

        # Categorie
        categories = conn.execute(
            "SELECT DISTINCT category FROM prompts ORDER BY category"
        ).fetchall()
        cat_list = [r[0] for r in categories]

        # Numero valutazioni giudice
        total_judge = conn.execute(
            "SELECT COUNT(*) FROM judge_scores"
        ).fetchone()[0]

        # Numero check deterministici
        total_det = conn.execute(
            "SELECT COUNT(*) FROM deterministic_scores"
        ).fetchone()[0]

        # Score medio complessivo
        avg_score = conn.execute(
            "SELECT AVG(overall) FROM judge_scores"
        ).fetchone()[0] or 0.0

        # Miglior modello
        best = conn.execute(
            """SELECT m.name, m.provider, AVG(js.overall) as avg
               FROM judge_scores js
               JOIN benchmark_results br ON js.result_id = br.id
               JOIN models m ON br.model_id = m.id
               GROUP BY m.name, m.provider
               ORDER BY avg DESC LIMIT 3"""
        ).fetchall()

        # Ultima run
        last_run = conn.execute(
            "SELECT * FROM benchmark_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

        last_name = "?"
        if last_run:
            last_model = conn.execute(
                "SELECT name FROM models WHERE id=?", (last_run["model_id"],)
            ).fetchone()
            if last_model:
                last_name = last_model[0]

    # Spazio disco
    db_size = Path(db_path).stat().st_size if Path(db_path).exists() else 0
    db_size_mb = db_size / (1024 * 1024)

    print(f"\n📊 LLM Benchmark Statistics\n")
    print(f"  Database:        {db_path} ({db_size_mb:.1f} MB)")
    print(f"  ─────────────────────────────────────────")
    print(f"  Benchmark run:   {total_runs} ({completed_runs} completate, {partial_runs} parziali)")
    print(f"  Risultati:       {total_results}")
    print(f"  Valutazioni:     {total_judge} (giudice) + {total_det} (deterministiche)")
    print(f"  ─────────────────────────────────────────")
    print(f"  Modelli testati: {total_models}")
    print(f"  Provider usati:  {', '.join(provider_list) if provider_list else '(nessuno)'}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Prompt caricati: {total_prompts} in {len(cat_list)} categorie")
    print(f"  Categorie:       {', '.join(cat_list) if cat_list else '(nessuna)'}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Score medio:     {avg_score:.3f}" if total_judge > 0 else "  Score medio:     N/A")
    if best:
        print(f"  Top 3 modelli:")
        for i, (name, prov, avg) in enumerate(best, 1):
            print(f"    {i}. {name} ({prov}) — {avg:.3f}")
    if last_run:
        last_date = last_run["started_at"][:19] if last_run["started_at"] else "?"
        last_total = last_run["total_prompts"] or 0
        last_completed = last_run["completed_prompts"] or 0
        last_failed = max(0, last_total - last_completed)
        last_failure_ratio = (last_failed / last_total) if last_total > 0 else 0.0

        print(f"  ─────────────────────────────────────────")
        print(f"  Ultima run:      {last_date}")
        print(f"  Ultimo modello:  {last_name} ({last_run['suite']})")

        if last_completed < MIN_PROMPTS_MINIMUM:
            print(
                f"  ⚠️  Statistical validity: INSUFFICIENT "
                f"({last_completed} < {MIN_PROMPTS_MINIMUM} prompt completati)"
            )
        elif last_completed < MIN_PROMPTS_RECOMMENDED:
            print(
                f"  ⚠️  Statistical validity: MINIMUM_ONLY "
                f"({last_completed} < {MIN_PROMPTS_RECOMMENDED} raccomandati)"
            )
        else:
            print("  ✅ Statistical validity: RECOMMENDED")

        if last_failure_ratio > MAX_FAILURE_RATIO_RECOMMENDED:
            print(
                f"  ⚠️  Failure ratio elevato: {last_failure_ratio:.1%} "
                f"(raccomandato <= {MAX_FAILURE_RATIO_RECOMMENDED:.0%})"
            )
    print()


def cmd_clean(args: argparse.Namespace) -> None:
    """Pulisce benchmark run e/o file di report."""

    if not args.runs and not args.reports:
        args.all = True  # default: clean all

    scope_parts = []
    if args.runs or args.all:
        scope_parts.append("benchmark_runs, benchmark_results, judge_scores, deterministic_scores, composite_scores")
    if args.reports or args.all:
        scope_parts.append("file in reports/ exports/ charts/")

    scope = " e ".join(scope_parts)

    print(f"\n⚠️  Operazione: eliminare {scope}")
    print(f"   Database: {args.db or 'db/benchmark.db'}")
    print()
    confirm = input("   Digita YES per confermare: ").strip()

    if confirm != "YES":
        print("   Operazione annullata.\n")
        return

    print()

    db_path = args.db or "db/benchmark.db"

    # Clean database tables
    if args.runs or args.all:
        if Path(db_path).exists():
            try:
                conn = sqlite3.connect(db_path)
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("DELETE FROM deterministic_scores")
                conn.execute("DELETE FROM judge_scores")
                conn.execute("DELETE FROM composite_scores")
                conn.execute("DELETE FROM benchmark_results")
                conn.execute("DELETE FROM benchmark_runs")
                conn.commit()
                conn.execute("VACUUM")
                conn.close()
                print("  ✅ Tabelle benchmark pulite")
            except sqlite3.Error as e:
                print(f"  ❌ Errore database: {e}")
        else:
            print("  ⚠️  Database non trovato, nessuna pulizia DB")

    # Clean report/output files
    if args.reports or args.all:
        for dir_name in ("reports", "exports", "charts"):
            dir_path = Path(dir_name)
            if dir_path.is_dir():
                for f in dir_path.iterdir():
                    if f.name == ".gitkeep":
                        continue
                    try:
                        if f.is_file():
                            f.unlink()
                        elif f.is_dir():
                            shutil.rmtree(f)
                    except OSError as e:
                        print(f"  ❌ Errore cancellando {f}: {e}")
                print(f"  ✅ Directory '{dir_name}/' pulita")

    print("   Pulizia completata.\n")


def _auto_report(db: DatabaseManager, run_id: int) -> None:
    """Genera report automaticamente dopo benchmark."""
    try:
        report_gen = ReportGenerator(db)
        report_gen.generate_json_report(run_id)
        report_gen.generate_csv_report(run_id)
        report_gen.generate_html_report(run_id)
        print(f"📄 Report generati in reports/ (run {run_id})")
    except Exception as e:
        logger.warning("Auto-report fallito: %s", e)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM Benchmark Framework — benchmark comparativi per LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config", default="config.yaml",
        help="Percorso config.yaml (default: config.yaml)",
    )

    sub = parser.add_subparsers(dest="command", help="Comando")

    # ── run ─────────────────────────────────
    run_parser = sub.add_parser("run", help="Esegui benchmark")
    run_parser.add_argument("--model", required=True, help="Modello da testare")
    run_parser.add_argument("--provider", default="ollama", help="Provider (default: ollama)")
    run_parser.add_argument("--suite", help="Suite specifica (default: tutte)")
    run_parser.set_defaults(func=cmd_run)

    # ── compare ─────────────────────────────
    cmp_parser = sub.add_parser("compare", help="Confronta modelli")
    cmp_parser.add_argument("--models", required=True, help="Modelli separati da virgola")
    cmp_parser.add_argument("--provider", default="ollama", help="Provider")
    cmp_parser.add_argument("--suite", help="Suite specifica")
    cmp_parser.set_defaults(func=cmd_compare)

    # ── list ────────────────────────────────
    list_parser = sub.add_parser("list", help="Elenca risorse")
    list_group = list_parser.add_mutually_exclusive_group(required=True)
    list_group.add_argument("--models", action="store_true", help="Elenca modelli")
    list_group.add_argument("--providers", action="store_true", help="Elenca provider")
    list_group.add_argument("--prompts", action="store_true", help="Elenca prompt")
    list_parser.add_argument("--provider", help="Provider per --models")
    list_parser.add_argument("--category", help="Categoria per --prompts")
    list_parser.set_defaults(func=cmd_list)

    # ── report ──────────────────────────────
    rep_parser = sub.add_parser("report", help="Genera report")
    rep_parser.add_argument("--run-id", type=int, required=True, help="ID run")
    rep_parser.add_argument("--format", choices=["json", "csv", "html", "all"], default="all")
    rep_parser.add_argument("--db", help="Percorso database")
    rep_parser.set_defaults(func=cmd_report)

    # ── charts ──────────────────────────────
    ch_parser = sub.add_parser("charts", help="Genera grafici")
    ch_parser.add_argument("--run-id", type=int, required=True, help="ID run")
    ch_parser.add_argument("--db", help="Percorso database")
    ch_parser.set_defaults(func=cmd_charts)

    # ── import-prompts ──────────────────────
    imp_parser = sub.add_parser("import-prompts", help="Importa prompt nel DB")
    imp_parser.add_argument("--prompts-dir", help="Directory prompt (default: prompts)")
    imp_parser.add_argument("--db", help="Percorso database")
    imp_parser.set_defaults(func=cmd_import_prompts)

    # ── stats ───────────────────────────────
    stats_parser = sub.add_parser("stats", help="Statistiche benchmark")
    stats_parser.add_argument("--db", help="Percorso database")
    stats_parser.set_defaults(func=cmd_stats)

    # ── clean ───────────────────────────────
    clean_parser = sub.add_parser("clean", help="Pulisci benchmark e report")
    clean_group = clean_parser.add_mutually_exclusive_group()
    clean_group.add_argument("--runs", action="store_true", help="Elimina solo dati benchmark")
    clean_group.add_argument("--reports", action="store_true", help="Elimina solo file report")
    clean_group.add_argument("--all", action="store_true", help="Reset completo (default)")
    clean_parser.add_argument("--db", help="Percorso database")
    clean_parser.set_defaults(func=cmd_clean)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
