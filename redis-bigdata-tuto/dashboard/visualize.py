"""
dashboard/visualize.py — Dashboard matplotlib des métriques Redis.

Génère 4 graphiques en une seule figure :
    1. Hit ratio en temps réel (évolution)
    2. Latence p50 / p95 / p99 cache chaud vs froid
    3. Top 10 films les plus consultés (Sorted Set)
    4. Consommation mémoire Redis

Usage :
    python dashboard/visualize.py
    python dashboard/visualize.py --show
"""

import argparse
import os
import random

import httpx
import matplotlib

if not os.getenv("DISPLAY") and not os.getenv("MPLBACKEND"):
    matplotlib.use("Agg")

import matplotlib.pyplot as plt

BASE_URL = "http://localhost:8000"
POPULAR_IDS = ["1", "2", "3", "4", "5", "296", "318", "356", "593", "2571"]

plt.rcParams.update({
    "figure.facecolor": "#1a1a2e",
    "axes.facecolor":   "#16213e",
    "axes.edgecolor":   "#0f3460",
    "axes.labelcolor":  "#e0e0e0",
    "text.color":       "#e0e0e0",
    "xtick.color":      "#aaaaaa",
    "ytick.color":      "#aaaaaa",
    "grid.color":       "#0f3460",
    "grid.alpha":       0.5,
})


def collect_metrics():
    """Simule 60 requêtes en mesurant latence et hit ratio."""
    print("Collecte des métriques (60 requêtes)...")
    httpx.delete(f"{BASE_URL}/cache")

    cold_latencies, hot_latencies, hit_ratios = [], [], []

    for i in range(60):
        mid = random.choice(POPULAR_IDS)
        r = httpx.get(f"{BASE_URL}/movies/{mid}")
        data = r.json()
        lat = data.get("_latency_ms", 0)

        if i < 20:
            cold_latencies.append(lat)
        else:
            hot_latencies.append(lat)

        stats = httpx.get(f"{BASE_URL}/stats").json()
        hit_ratios.append(stats["hit_ratio_pct"])

        if i % 10 == 0:
            print(
                f"  {i+1}/60 requêtes — hit ratio : {stats['hit_ratio_pct']}%")

    return cold_latencies, hot_latencies, hit_ratios


def build_dashboard(cold, hot, ratios, output_path: str, show: bool = False):
    stats = httpx.get(f"{BASE_URL}/stats").json()
    top10 = stats["top10_movies"]
    mem_used = stats["redis_memory_mb"]
    mem_peak = stats["redis_peak_memory_mb"]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Redis Cache Dashboard — BigData MovieLens",
                 fontsize=16, fontweight="bold", color="#e94560")

    TEAL = "#00b4d8"
    CORAL = "#e94560"
    AMBER = "#f4a261"
    PURPLE = "#8338ec"

    # ── 1. Hit ratio (évolution) ──
    ax = axes[0, 0]
    ax.plot(range(1, len(ratios)+1), ratios, color=TEAL, linewidth=2)
    ax.fill_between(range(1, len(ratios)+1), ratios, alpha=0.15, color=TEAL)
    ax.axhline(y=80, color=AMBER, linewidth=1,
               linestyle="--", alpha=0.6, label="Cible 80%")
    ax.set_title("Hit ratio (%)", color=TEAL, fontsize=11)
    ax.set_xlabel("Requête n°")
    ax.set_ylabel("Hit ratio (%)")
    ax.set_ylim(0, 105)
    ax.grid(True)
    ax.legend(facecolor="#16213e", edgecolor="#0f3460")

    # ── 2. Comparaison latence ──
    ax = axes[0, 1]
    labels = ["p50", "p95", "p99"]

    def pct(data, p):
        return sorted(data)[int(len(data)*p/100)]

    cold_vals = [pct(cold, 50), pct(cold, 95), pct(cold, 99)]
    hot_vals = [pct(hot,  50), pct(hot,  95), pct(hot,  99)]

    x = range(len(labels))
    w = 0.35
    bars1 = ax.bar([i - w/2 for i in x], cold_vals, w,
                   label="MongoDB (miss)", color=CORAL, alpha=0.85)
    bars2 = ax.bar([i + w/2 for i in x], hot_vals,  w,
                   label="Redis (hit)",    color=TEAL,  alpha=0.85)

    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"{bar.get_height():.1f}ms", ha="center", va="bottom", fontsize=8, color=CORAL)
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"{bar.get_height():.1f}ms", ha="center", va="bottom", fontsize=8, color=TEAL)

    ax.set_title("Latence : Redis vs MongoDB", color=AMBER, fontsize=11)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Latence (ms)")
    ax.legend(facecolor="#16213e", edgecolor="#0f3460")
    ax.grid(True, axis="y")

    # ── 3. Leaderboard (Sorted Set) ──
    ax = axes[1, 0]
    if top10:
        ids = [f"Film {d['movie_id']}" for d in top10[:10]]
        views = [d["views"] for d in top10[:10]]
        colors = [PURPLE if i == 0 else TEAL for i in range(len(ids))]
        bars = ax.barh(ids[::-1], views[::-1], color=colors[::-1], alpha=0.85)
        for bar, v in zip(bars, views[::-1]):
            ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                    str(int(v)), va="center", fontsize=8, color="#e0e0e0")
    ax.set_title("Top 10 films consultés (Sorted Set)",
                 color=PURPLE, fontsize=11)
    ax.set_xlabel("Nombre de vues")
    ax.grid(True, axis="x")

    # ── 4. Mémoire Redis ──
    ax = axes[1, 1]
    mem_labels = ["Utilisée", "Pic", "Max allouée (256 MB)"]
    mem_values = [mem_used, mem_peak, 256]
    bar_colors = [TEAL, AMBER, "#444"]
    bars = ax.bar(mem_labels, mem_values,
                  color=bar_colors, alpha=0.85, width=0.5)
    for bar, v in zip(bars, mem_values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f"{v:.2f} MB", ha="center", va="bottom", fontsize=9, color="#e0e0e0")
    ax.set_title("Mémoire Redis (MB)", color=AMBER, fontsize=11)
    ax.set_ylabel("MB")
    ax.grid(True, axis="y")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"\nDashboard sauvegardé : {output_path}")
    if show:
        plt.show()
    plt.close(fig)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate the Redis matplotlib dashboard.")
    parser.add_argument(
        "--output",
        default="dashboard/redis_dashboard.png",
        help="Path to the generated PNG report."
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open the matplotlib window after saving the file."
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cold, hot, ratios = collect_metrics()
    build_dashboard(cold, hot, ratios, output_path=args.output, show=args.show)
