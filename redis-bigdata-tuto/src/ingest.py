"""
src/ingest.py — Télécharge MovieLens small et charge dans MongoDB.

Dataset : https://grouplens.org/datasets/movielens/latest/
Fichier  : ml-latest-small.zip (~1 Mo, 9 000 films, 100 000 ratings)

Usage :
  python src/ingest.py
"""

import io
import zipfile
import requests
import pandas as pd
from pymongo import MongoClient, ASCENDING
from rich.console import Console
from rich.progress import track

console = Console()
MONGO_URI = "mongodb://localhost:27017/movielens"
ML_URL    = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"


def download_movielens() -> dict[str, pd.DataFrame]:
    console.print("[cyan]Téléchargement du dataset MovieLens Small...[/cyan]")
    r = requests.get(ML_URL, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open("ml-latest-small/movies.csv") as f:
            movies = pd.read_csv(f)
        with z.open("ml-latest-small/ratings.csv") as f:
            ratings = pd.read_csv(f)
        with z.open("ml-latest-small/tags.csv") as f:
            tags = pd.read_csv(f)
    console.print(f"[green]✓ {len(movies)} films, {len(ratings)} ratings, {len(tags)} tags[/green]")
    return {"movies": movies, "ratings": ratings, "tags": tags}


def load_into_mongo(dfs: dict[str, pd.DataFrame]):
    client = MongoClient(MONGO_URI)
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

    client.close()
    console.print("[bold green]✓ Données chargées dans MongoDB ![/bold green]")


def _extract_year(title: str):
    import re
    m = re.search(r"\((\d{4})\)$", title.strip())
    return int(m.group(1)) if m else None


if __name__ == "__main__":
    dfs = download_movielens()
    load_into_mongo(dfs)
    console.print("[bold]Ingestion terminée. Lance l'API avec : docker-compose up[/bold]")
