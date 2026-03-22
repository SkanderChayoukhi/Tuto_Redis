"""
src/benchmark.py — Mesure la performance du cache Redis vs MongoDB.

Ce script est la pièce maîtresse pour l'oral :
il démontre concrètement l'apport du cache sur la vélocité (V du BigData).

Usage :
  python src/benchmark.py
"""

import time
import statistics
import random
import json
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
BASE_URL = "http://localhost:8000"

# On utilise ces IDs pour les tests (films populaires du dataset MovieLens small)
POPULAR_IDS = ["1", "2", "3", "4", "5", "296", "318", "356", "593", "2571"]


def flush_cache():
    httpx.delete(f"{BASE_URL}/cache")
    console.print("[yellow]Cache vidé[/yellow]")


def fetch_movie(movie_id: str) -> tuple[float, str]:
    """Retourne (latence_ms, source)."""
    r = httpx.get(f"{BASE_URL}/movies/{movie_id}")
    data = r.json()
    return data.get("_latency_ms", 0), data.get("_source", "?")


def run_benchmark(n_requests: int = 50):
    console.print(
        Panel.fit("[bold cyan]Benchmark Redis Cache — BigData UE[/bold cyan]"))

    # ── Phase 1 : cache froid (tout vient de MongoDB) ──
    console.print("\n[bold]Phase 1 : Cache FROID (cache miss attendu)[/bold]")
    flush_cache()
    cold_latencies = []
    for i in range(n_requests):
        movie_id = random.choice(POPULAR_IDS)
        latency, source = fetch_movie(movie_id)
        cold_latencies.append(latency)
        console.print(
            f"  [{i+1:02d}] movie={movie_id:>4} → {source:<12} {latency:>7.2f} ms")

    # ── Phase 2 : cache chaud (tout vient de Redis) ──
    console.print("\n[bold]Phase 2 : Cache CHAUD (cache hit attendu)[/bold]")
    hot_latencies = []
    for i in range(n_requests):
        movie_id = random.choice(POPULAR_IDS)
        latency, source = fetch_movie(movie_id)
        hot_latencies.append(latency)
        console.print(
            f"  [{i+1:02d}] movie={movie_id:>4} → {source:<12} {latency:>7.2f} ms")

    # ── Résultats ──
    summary = _build_summary(cold_latencies, hot_latencies)
    _print_results(summary)

    # ── Stats globales ──
    stats = httpx.get(f"{BASE_URL}/stats").json()
    console.print(f"\n[bold green]Hit ratio : {stats['hit_ratio_pct']}%[/bold green]  "
                  f"(hits={stats['hits']}, misses={stats['misses']})")
    console.print(f"Mémoire Redis utilisée : {stats['redis_memory_mb']} MB")

    summary["cache_stats"] = {
        "hit_ratio_pct": stats.get("hit_ratio_pct", 0),
        "hits": stats.get("hits", 0),
        "misses": stats.get("misses", 0),
        "redis_memory_mb": stats.get("redis_memory_mb", 0),
    }
    # Machine-readable line for dashboard automation parsing.
    print(f"BENCHMARK_SUMMARY_JSON:{json.dumps(summary, ensure_ascii=True)}")
    return summary


def _build_summary(cold: list, hot: list):
    def percentile(data: list[float], p: int) -> float:
        if not data:
            return 0.0
        idx = min(max(int(len(data) * p / 100), 0), len(data) - 1)
        return float(sorted(data)[idx])

    cold_metrics = {
        "mean_ms": float(statistics.mean(cold)) if cold else 0.0,
        "p50_ms": float(statistics.median(cold)) if cold else 0.0,
        "p95_ms": percentile(cold, 95),
        "p99_ms": percentile(cold, 99),
        "max_ms": float(max(cold)) if cold else 0.0,
        "min_ms": float(min(cold)) if cold else 0.0,
    }
    hot_metrics = {
        "mean_ms": float(statistics.mean(hot)) if hot else 0.0,
        "p50_ms": float(statistics.median(hot)) if hot else 0.0,
        "p95_ms": percentile(hot, 95),
        "p99_ms": percentile(hot, 99),
        "max_ms": float(max(hot)) if hot else 0.0,
        "min_ms": float(min(hot)) if hot else 0.0,
    }

    speedup = cold_metrics["mean_ms"] / \
        hot_metrics["mean_ms"] if hot_metrics["mean_ms"] > 0 else 0.0
    return {
        "requests_per_phase": len(cold),
        "cold": cold_metrics,
        "warm": hot_metrics,
        "speedup_x": float(speedup),
    }


def _print_results(summary: dict):
    table = Table(title="Résultats du benchmark",
                  show_header=True, header_style="bold cyan")
    table.add_column("Métrique")
    table.add_column("Cache FROID (MongoDB)", justify="right")
    table.add_column("Cache CHAUD (Redis)", justify="right")
    table.add_column("Speedup", justify="right", style="bold green")

    def row(label, cold_value, hot_value):
        c = cold_value
        h = hot_value
        sp = f"{c/h:.1f}x" if h > 0 else "—"
        table.add_row(label, f"{c:.2f} ms", f"{h:.2f} ms", sp)

    row("Latence moyenne", summary["cold"]
        ["mean_ms"], summary["warm"]["mean_ms"])
    row("Médiane (p50)", summary["cold"]["p50_ms"], summary["warm"]["p50_ms"])
    row("p95", summary["cold"]["p95_ms"], summary["warm"]["p95_ms"])
    row("p99", summary["cold"]["p99_ms"], summary["warm"]["p99_ms"])
    row("Max", summary["cold"]["max_ms"], summary["warm"]["max_ms"])
    row("Min", summary["cold"]["min_ms"], summary["warm"]["min_ms"])

    console.print("\n", table)


if __name__ == "__main__":
    run_benchmark(n_requests=30)
