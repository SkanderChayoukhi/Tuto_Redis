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
    console.print(Panel.fit("[bold cyan]Benchmark Redis Cache — BigData UE[/bold cyan]"))

    # ── Phase 1 : cache froid (tout vient de MongoDB) ──
    console.print("\n[bold]Phase 1 : Cache FROID (cache miss attendu)[/bold]")
    flush_cache()
    cold_latencies = []
    for i in range(n_requests):
        movie_id = random.choice(POPULAR_IDS)
        latency, source = fetch_movie(movie_id)
        cold_latencies.append(latency)
        console.print(f"  [{i+1:02d}] movie={movie_id:>4} → {source:<12} {latency:>7.2f} ms")

    # ── Phase 2 : cache chaud (tout vient de Redis) ──
    console.print("\n[bold]Phase 2 : Cache CHAUD (cache hit attendu)[/bold]")
    hot_latencies = []
    for i in range(n_requests):
        movie_id = random.choice(POPULAR_IDS)
        latency, source = fetch_movie(movie_id)
        hot_latencies.append(latency)
        console.print(f"  [{i+1:02d}] movie={movie_id:>4} → {source:<12} {latency:>7.2f} ms")

    # ── Résultats ──
    _print_results(cold_latencies, hot_latencies, n_requests)

    # ── Stats globales ──
    stats = httpx.get(f"{BASE_URL}/stats").json()
    console.print(f"\n[bold green]Hit ratio : {stats['hit_ratio_pct']}%[/bold green]  "
                  f"(hits={stats['hits']}, misses={stats['misses']})")
    console.print(f"Mémoire Redis utilisée : {stats['redis_memory_mb']} MB")


def _print_results(cold: list, hot: list, n: int):
    table = Table(title="Résultats du benchmark", show_header=True, header_style="bold cyan")
    table.add_column("Métrique")
    table.add_column("Cache FROID (MongoDB)", justify="right")
    table.add_column("Cache CHAUD (Redis)", justify="right")
    table.add_column("Speedup", justify="right", style="bold green")

    def row(label, fn):
        c = fn(cold)
        h = fn(hot)
        sp = f"{c/h:.1f}x" if h > 0 else "—"
        table.add_row(label, f"{c:.2f} ms", f"{h:.2f} ms", sp)

    row("Latence moyenne", statistics.mean)
    row("Médiane (p50)",   statistics.median)
    row("p95",             lambda d: sorted(d)[int(len(d)*0.95)])
    row("p99",             lambda d: sorted(d)[int(len(d)*0.99)])
    row("Max",             max)
    row("Min",             min)

    console.print("\n", table)


if __name__ == "__main__":
    run_benchmark(n_requests=30)
