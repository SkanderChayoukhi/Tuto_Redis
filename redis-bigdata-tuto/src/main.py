"""
src/main.py — FastAPI + Redis cache + MongoDB source

Architecture BigData :
  Client → FastAPI → Redis (cache hit) → réponse rapide
                   → MongoDB (cache miss) → Redis (populate) → réponse
"""

import json
import time
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import redis.asyncio as aioredis
import motor.motor_asyncio as motor

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
MONGO_URI  = os.getenv("MONGO_URI", "mongodb://localhost:27017/movielens")
CACHE_TTL  = int(os.getenv("CACHE_TTL", 60))         # secondes
RATE_LIMIT  = int(os.getenv("RATE_LIMIT", 100))       # req / minute / IP

_redis: aioredis.Redis = None
_mongo_client = None
_db = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _mongo_client, _db
    _redis = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    _mongo_client = motor.AsyncIOMotorClient(MONGO_URI)
    _db = _mongo_client["movielens"]
    log.info("Connexions Redis et MongoDB établies")
    yield
    await _redis.aclose()
    _mongo_client.close()
    log.info("Connexions fermées")


app = FastAPI(title="MovieLens Cache API", lifespan=lifespan)


# ──────────────────────────────────────────────
# Helpers Redis
# ──────────────────────────────────────────────

async def cache_get(key: str):
    """Lecture cache — retourne None si absent."""
    raw = await _redis.get(key)
    if raw:
        await _redis.incr("stats:hits")
        return json.loads(raw)
    await _redis.incr("stats:misses")
    return None


async def cache_set(key: str, value: dict, ttl: int = CACHE_TTL):
    """Écriture cache avec TTL."""
    await _redis.setex(key, ttl, json.dumps(value))


async def rate_limit_check(ip: str) -> bool:
    """
    Rate limiting via INCR + EXPIRE.
    Retourne True si la requête est autorisée.
    Pattern classique BigData : compteur glissant par fenêtre de 60s.
    """
    key = f"rate:{ip}"
    count = await _redis.incr(key)
    if count == 1:
        await _redis.expire(key, 60)
    return count <= RATE_LIMIT


async def record_access(movie_id: str):
    """
    Enregistre chaque accès dans un Sorted Set Redis.
    Clé : leaderboard:movies  —  score = nombre de vues.
    Utile pour le dashboard (top films les plus consultés).
    """
    await _redis.zincrby("leaderboard:movies", 1, movie_id)


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    ping = await _redis.ping()
    return {"redis": ping, "status": "ok"}


@app.get("/movies/{movie_id}")
async def get_movie(movie_id: str, request: Request):
    """
    Endpoint principal :
    1. Rate limiting
    2. Lecture cache Redis  (O(1))
    3. Si absent → MongoDB  → populate cache
    """
    ip = request.client.host

    # ── Rate limiting ──
    if not await rate_limit_check(ip):
        raise HTTPException(status_code=429, detail="Rate limit dépassé (100 req/min)")

    t0 = time.perf_counter()

    # ── Cache Redis ──
    cache_key = f"movie:{movie_id}"
    cached = await cache_get(cache_key)

    if cached:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        await record_access(movie_id)
        return JSONResponse({**cached, "_source": "redis_cache", "_latency_ms": latency_ms})

    # ── Cache miss → MongoDB ──
    doc = await _db["movies"].find_one({"movieId": movie_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Film {movie_id} introuvable")

    # Enrichissement : ajouter la note moyenne depuis la collection ratings
    pipeline = [
        {"$match": {"movieId": movie_id}},
        {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}, "count": {"$sum": 1}}}
    ]
    async for agg in _db["ratings"].aggregate(pipeline):
        doc["avg_rating"] = round(agg["avg_rating"], 2)
        doc["rating_count"] = agg["count"]

    await cache_set(cache_key, doc)
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    await record_access(movie_id)
    return JSONResponse({**doc, "_source": "mongodb", "_latency_ms": latency_ms})


@app.get("/movies")
async def search_movies(genre: str = None, limit: int = 20):
    """
    Recherche par genre avec cache de liste.
    Illustre la dénormalisation NoSQL : les genres sont embarqués dans le document.
    """
    cache_key = f"search:genre:{genre or 'all'}:limit:{limit}"
    cached = await cache_get(cache_key)
    if cached:
        return JSONResponse({**cached, "_source": "redis_cache"})

    query = {}
    if genre:
        query["genres"] = {"$regex": genre, "$options": "i"}

    cursor = _db["movies"].find(query, {"_id": 0}).limit(limit)
    movies = await cursor.to_list(length=limit)

    result = {"movies": movies, "count": len(movies), "genre_filter": genre}
    await cache_set(cache_key, result, ttl=120)     # TTL plus long pour les listes
    return JSONResponse({**result, "_source": "mongodb"})


@app.get("/stats")
async def get_stats():
    """
    Métriques Redis en temps réel :
    - hits / misses / hit ratio
    - top 10 films les plus consultés (Sorted Set)
    - mémoire utilisée par Redis
    """
    hits   = int(await _redis.get("stats:hits")   or 0)
    misses = int(await _redis.get("stats:misses") or 0)
    total  = hits + misses
    ratio  = round(hits / total * 100, 1) if total > 0 else 0.0

    top10_raw = await _redis.zrevrange("leaderboard:movies", 0, 9, withscores=True)
    top10 = [{"movie_id": mid, "views": int(score)} for mid, score in top10_raw]

    info = await _redis.info("memory")
    return {
        "hits": hits,
        "misses": misses,
        "total_requests": total,
        "hit_ratio_pct": ratio,
        "top10_movies": top10,
        "redis_memory_mb": round(info["used_memory"] / 1024 / 1024, 2),
        "redis_peak_memory_mb": round(info["used_memory_peak"] / 1024 / 1024, 2),
    }


@app.delete("/cache")
async def flush_cache():
    """Vide le cache — utile pour les démos de comparaison de latence."""
    await _redis.flushdb()
    return {"message": "Cache vidé"}


@app.get("/leaderboard")
async def leaderboard(top: int = 20):
    """Top N films les plus consultés (Sorted Set ZREVRANGE)."""
    raw = await _redis.zrevrange("leaderboard:movies", 0, top - 1, withscores=True)
    return [{"rank": i + 1, "movie_id": mid, "views": int(score)} for i, (mid, score) in enumerate(raw)]
