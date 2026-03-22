"""
src/ingest.py — Télécharge MovieLens small et charge dans MongoDB.

Dataset : https://grouplens.org/datasets/movielens/latest/
Fichier  : ml-latest-small.zip (~1 Mo, 9 000 films, 100 000 ratings)

Usage :
  python src/ingest.py
  docker compose exec api python src/ingest.py
"""

import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

try:
    import requests
    import pandas as pd
    from pymongo import MongoClient, ASCENDING
    from rich.console import Console
    from rich.progress import track
except ModuleNotFoundError as exc:
    missing = exc.name
    req_file = ROOT_DIR / "requirements.txt"
    print(f"[WARN] Missing Python package: {missing}")

    if req_file.exists():
        print(f"[INFO] Auto-installing dependencies from: {req_file}")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file)])
            print("[INFO] Dependencies installed. Restarting ingestion...")
            os.execv(sys.executable, [sys.executable, *sys.argv])
        except Exception as install_error:
            print(f"[ERROR] Auto-install failed: {install_error}")

    print("Install dependencies manually with: pip install -r requirements.txt")
    print("Or run ingestion in container: docker compose exec api python src/ingest.py")
    sys.exit(1)

console = Console()
ML_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
DATA_DIR = ROOT_DIR / "data"
DATASET_ARCHIVE = DATA_DIR / "ml-latest-small.zip"


def _resolve_mongo_uri() -> str:
    """
    Priority:
    1) explicit MONGO_URI env var
    2) docker network URI when running in a container
    3) localhost URI for host execution
    """
    env_uri = os.getenv("MONGO_URI")
    if env_uri:
        return env_uri

    if Path("/.dockerenv").exists() or os.getenv("DOCKER_CONTAINER"):
        return "mongodb://mongo:27017/movielens"

    return "mongodb://localhost:27017/movielens"


def download_movielens() -> dict[str, pd.DataFrame]:
    archive_bytes = None

    if DATASET_ARCHIVE.exists():
        console.print(
            f"[cyan]Archive locale détectée : {DATASET_ARCHIVE}[/cyan]")
        archive_bytes = DATASET_ARCHIVE.read_bytes()
    else:
        console.print(
            "[cyan]Téléchargement du dataset MovieLens Small...[/cyan]")
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        last_error = None
        for attempt in range(1, 4):
            try:
                console.print(
                    f"[cyan]Tentative {attempt}/3 depuis {ML_URL}[/cyan]")
                response = requests.get(ML_URL, timeout=(10, 180))
                response.raise_for_status()
                archive_bytes = response.content
                DATASET_ARCHIVE.write_bytes(archive_bytes)
                console.print(
                    f"[green]✓ Archive sauvegardée dans {DATASET_ARCHIVE}[/green]")
                break
            except Exception as exc:
                last_error = exc
                console.print(
                    f"[yellow]! Échec du téléchargement: {exc}[/yellow]")

        if archive_bytes is None:
            raise RuntimeError(
                "Impossible de télécharger MovieLens après 3 tentatives. "
                f"Dernière erreur: {last_error}"
            ) from last_error

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
        with z.open("ml-latest-small/movies.csv") as f:
            movies = pd.read_csv(f)
        with z.open("ml-latest-small/ratings.csv") as f:
            ratings = pd.read_csv(f)
        with z.open("ml-latest-small/tags.csv") as f:
            tags = pd.read_csv(f)
    console.print(
        f"[green]✓ {len(movies)} films, {len(ratings)} ratings, {len(tags)} tags[/green]")
    return {"movies": movies, "ratings": ratings, "tags": tags}


def load_into_mongo(dfs: dict[str, pd.DataFrame], mongo_uri: str):
    console.print(f"[cyan]Connexion MongoDB: {mongo_uri}[/cyan]")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client["movielens"]

    # ── Movies ──
    console.print("[cyan]Chargement des films...[/cyan]")
    db["movies"].drop()
    movies_docs = []
    for _, row in track(dfs["movies"].iterrows(), total=len(dfs["movies"]), description="Films"):
        movies_docs.append({
            "movieId": str(row["movieId"]),
            "title": row["title"],
            "genres": row["genres"].split("|") if row["genres"] != "(no genres listed)" else [],
            # Dénormalisation : on pré-calcule aussi l'année depuis le titre
            "year": _extract_year(row["title"]),
        })
    db["movies"].insert_many(movies_docs)
    db["movies"].create_index([("movieId", ASCENDING)], unique=True)
    db["movies"].create_index([("genres", ASCENDING)])

    # ── Ratings ──
    console.print("[cyan]Chargement des ratings...[/cyan]")
    db["ratings"].drop()
    ratings_docs = [
        {"movieId": str(r["movieId"]), "userId": str(r["userId"]),
         "rating": float(r["rating"]), "timestamp": int(r["timestamp"])}
        for _, r in track(dfs["ratings"].iterrows(), total=len(dfs["ratings"]), description="Ratings")
    ]
    db["ratings"].insert_many(ratings_docs)
    db["ratings"].create_index([("movieId", ASCENDING)])

    # ── Tags (pour la partie recherche) ──
    console.print("[cyan]Chargement des tags...[/cyan]")
    db["tags"].drop()
    tags_docs = [
        {"movieId": str(t["movieId"]), "userId": str(t["userId"]),
         "tag": t["tag"], "timestamp": int(t["timestamp"])}
        for _, t in track(dfs["tags"].iterrows(), total=len(dfs["tags"]), description="Tags")
    ]
    db["tags"].insert_many(tags_docs)

    counts = {
        "movies": db["movies"].count_documents({}),
        "ratings": db["ratings"].count_documents({}),
        "tags": db["tags"].count_documents({}),
    }

    client.close()
    console.print("[bold green]✓ Données chargées dans MongoDB ![/bold green]")
    console.print(
        f"[green]Counts -> movies={counts['movies']}, ratings={counts['ratings']}, tags={counts['tags']}[/green]"
    )


def _extract_year(title: str):
    import re
    m = re.search(r"\((\d{4})\)$", title.strip())
    return int(m.group(1)) if m else None


def warmup_dashboard_metrics(api_base: str = "http://localhost:8000"):
    """
    Optional warm-up: generate a few misses/hits so dashboard metrics are non-zero
    right after ingestion.
    """
    movie_ids = ["1", "2", "3"]
    console.print(f"[cyan]Warm-up API metrics via {api_base}...[/cyan]")

    success_calls = 0
    for movie_id in movie_ids:
        url = f"{api_base}/movies/{movie_id}"
        try:
            # First request: likely miss -> Mongo -> populate cache
            r1 = requests.get(url, timeout=5)
            # Second request: likely hit from Redis
            r2 = requests.get(url, timeout=5)
            if r1.ok:
                success_calls += 1
            if r2.ok:
                success_calls += 1
        except Exception:
            # Keep ingestion successful even if API is not running.
            continue

    if success_calls > 0:
        console.print(
            f"[green]✓ Warm-up done ({success_calls} successful API calls)[/green]")
    else:
        console.print(
            "[yellow]! API warm-up skipped (API not reachable).[/yellow]")


if __name__ == "__main__":
    mongo_uri = _resolve_mongo_uri()
    dfs = download_movielens()
    load_into_mongo(dfs, mongo_uri)
    warmup_dashboard_metrics()
    console.print(
        "[bold]Ingestion terminée. Lance l'API avec : docker-compose up[/bold]")
