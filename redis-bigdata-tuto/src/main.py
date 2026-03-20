"""
src/main.py — FastAPI + Redis cache + MongoDB source + Interactive Dashboard

Architecture BigData :
  Client → FastAPI → Redis (cache hit) → réponse rapide
                   → MongoDB (cache miss) → Redis (populate) → réponse

Dashboard :
  Browser → /dashboard → Redis Inspector Pro (real-time metrics, command executor)
"""

import json
import time
import os
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import redis.asyncio as aioredis
import motor.motor_asyncio as motor

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/movielens")
CACHE_TTL = int(os.getenv("CACHE_TTL", 60))         # secondes
RATE_LIMIT = int(os.getenv("RATE_LIMIT", 100))       # req / minute / IP

_redis: aioredis.Redis = None
_mongo_client = None
_db = None

# Metrics tracking
_metrics = {
    "hits": 0,
    "misses": 0,
    "avg_latency": 0,
    "latencies": [],
    "total_requests": 0
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _mongo_client, _db
    _redis = aioredis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    _mongo_client = motor.AsyncIOMotorClient(MONGO_URI)
    _db = _mongo_client["movielens"]
    log.info("✓ Redis et MongoDB connectés")
    yield
    await _redis.aclose()
    _mongo_client.close()
    log.info("✓ Connexions fermées")


app = FastAPI(title="Redis Inspector Pro",
              description="Interactive Redis tutorial", lifespan=lifespan)

# Mount static files
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    log.info(f"✓ Static files mounted: {static_dir}")
else:
    log.warning(f"⚠ Static directory not found at {static_dir}")


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
        raise HTTPException(
            status_code=429, detail="Rate limit dépassé (100 req/min)")

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
        raise HTTPException(
            status_code=404, detail=f"Film {movie_id} introuvable")

    # Enrichissement : ajouter la note moyenne depuis la collection ratings
    pipeline = [
        {"$match": {"movieId": movie_id}},
        {"$group": {"_id": None, "avg_rating": {
            "$avg": "$rating"}, "count": {"$sum": 1}}}
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
    # TTL plus long pour les listes
    await cache_set(cache_key, result, ttl=120)
    return JSONResponse({**result, "_source": "mongodb"})


@app.get("/stats")
async def get_stats():
    """
    Métriques Redis en temps réel :
    - hits / misses / hit ratio
    - top 10 films les plus consultés (Sorted Set)
    - mémoire utilisée par Redis
    """
    hits = int(await _redis.get("stats:hits") or 0)
    misses = int(await _redis.get("stats:misses") or 0)
    total = hits + misses
    ratio = round(hits / total * 100, 1) if total > 0 else 0.0

    top10_raw = await _redis.zrevrange("leaderboard:movies", 0, 9, withscores=True)
    top10 = [{"movie_id": mid, "views": int(score)}
             for mid, score in top10_raw]

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


# ──────────────────────────────────────────────
# DASHBOARD API ENDPOINTS
# ──────────────────────────────────────────────

@app.get("/")
async def dashboard_root():
    """Serve dashboard at root path"""
    static_dir = Path(__file__).parent.parent / "static" / "index.html"
    return FileResponse(str(static_dir))


@app.get("/api/metrics")
async def get_metrics_api():
    """
    Endpoint for dashboard — métriques en temps réel.
    JSON avec statistiques de cache et performance.
    """
    hits = int(await _redis.get("stats:hits") or 0)
    misses = int(await _redis.get("stats:misses") or 0)
    total = hits + misses
    ratio = round(hits / total * 100, 1) if total > 0 else 0.0

    top10_raw = await _redis.zrevrange("leaderboard:movies", 0, 9, withscores=True)
    top10 = [{"movie_id": mid, "views": int(score)}
             for mid, score in top10_raw]

    info = await _redis.info("memory")

    # Calculate average latency
    avg_latency = 0
    if _metrics["latencies"]:
        avg_latency = sum(_metrics["latencies"][-100:]) / \
            min(len(_metrics["latencies"]), 100)

    return {
        "hits": hits,
        "misses": misses,
        "total_requests": total,
        "hit_ratio_pct": ratio,
        "top10_movies": top10,
        "redis_memory_mb": round(info["used_memory"] / 1024 / 1024, 2),
        "redis_peak_memory_mb": round(info["used_memory_peak"] / 1024 / 1024, 2),
        "avg_latency": avg_latency
    }


@app.get("/api/keys")
async def get_keys_api():
    """List all keys in Redis with their types and TTL"""
    keys_list = []
    cursor = 0

    while True:
        cursor, keys = await _redis.scan(cursor, count=100)

        for key in keys:
            key_type = await _redis.type(key)
            ttl = await _redis.ttl(key)
            ttl_str = f"{ttl}s" if ttl > 0 else (
                "never" if ttl == -1 else "expired")

            keys_list.append({
                "name": key,
                "type": key_type,
                "ttl": ttl_str
            })

        if cursor == 0:
            break

    return {"keys": sorted(keys_list, key=lambda x: x["name"])}


@app.get("/api/key/{key_name}")
async def inspect_key(key_name: str):
    """Get detailed information about a specific key"""
    key_type = await _redis.type(key_name)
    ttl = await _redis.ttl(key_name)

    if key_type == "none":
        raise HTTPException(status_code=404, detail="Key not found")

    value = None

    if key_type == "string":
        value = await _redis.get(key_name)
    elif key_type == "hash":
        value = await _redis.hgetall(key_name)
    elif key_type == "list":
        value = await _redis.lrange(key_name, 0, -1)
    elif key_type == "set":
        value = list(await _redis.smembers(key_name))
    elif key_type == "zset":
        members = await _redis.zrange(key_name, 0, -1, withscores=True)
        value = [{"member": m, "score": float(s)} for m, s in members]

    return {
        "name": key_name,
        "type": key_type,
        "ttl": ttl,
        "value": value
    }


@app.post("/api/command")
async def execute_redis_command(request: Request):
    """
    Execute arbitrary Redis command from dashboard.
    Dangerous in production, safe for tutorial.
    """
    data = await request.json()
    command = data.get("command", "").strip()

    if not command:
        raise HTTPException(status_code=400, detail="Command required")

    # Parse command
    parts = command.split()
    cmd = parts[0].upper()
    args = parts[1:]

    try:
        # Execute command
        if cmd == "GET" and len(args) == 1:
            result = await _redis.get(args[0])
        elif cmd == "SET" and len(args) == 2:
            result = await _redis.set(args[0], args[1])
        elif cmd == "KEYS" and len(args) >= 1:
            result = await _redis.keys(args[0])
        elif cmd == "DEL" and len(args) >= 1:
            result = await _redis.delete(*args)
        elif cmd == "INCR" and len(args) == 1:
            result = await _redis.incr(args[0])
        elif cmd == "DECR" and len(args) == 1:
            result = await _redis.decr(args[0])
        elif cmd == "ZRANGE" and len(args) >= 3:
            result = await _redis.zrange(args[0], int(args[1]), int(args[2]), withscores=True)
        elif cmd == "ZREVRANGE" and len(args) >= 3:
            result = await _redis.zrevrange(args[0], int(args[1]), int(args[2]), withscores=True)
        elif cmd == "HGETALL" and len(args) == 1:
            result = await _redis.hgetall(args[0])
        elif cmd == "HGET" and len(args) == 2:
            result = await _redis.hget(args[0], args[1])
        elif cmd == "SMEMBERS" and len(args) == 1:
            result = list(await _redis.smembers(args[0]))
        elif cmd == "LRANGE" and len(args) == 3:
            result = await _redis.lrange(args[0], int(args[1]), int(args[2]))
        elif cmd == "TTL" and len(args) == 1:
            result = await _redis.ttl(args[0])
        elif cmd == "EXPIRE" and len(args) == 2:
            result = await _redis.expire(args[0], int(args[1]))
        elif cmd == "TYPE" and len(args) == 1:
            result = await _redis.type(args[0])
        elif cmd == "DBSIZE":
            result = await _redis.dbsize()
        elif cmd == "INFO":
            info = await _redis.info()
            result = json.dumps(info, indent=2, default=str)
        else:
            return {"error": f"Command '{cmd}' not supported in this tutorial"}

        return {"result": result, "error": None}

    except Exception as e:
        return {"error": str(e), "result": None}
