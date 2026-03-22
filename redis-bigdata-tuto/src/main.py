"""
src/main.py — FastAPI + Redis cache + MongoDB source + Interactive Dashboard

Architecture BigData :
  Client → FastAPI → Redis (cache hit) → réponse rapide
                   → MongoDB (cache miss) → Redis (populate) → réponse

Dashboard :
  Browser → /dashboard → Redis Inspector Pro (real-time metrics, command executor)
"""

import asyncio
import json
import time
import os
import logging
import re
import sys
import uuid
from io import BytesIO
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
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
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in {
    "1", "true", "yes", "on"}
PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_DIR / "static"
DASHBOARD_DIR = PROJECT_DIR / "dashboard"
MAX_SCRIPT_LOG_LINES = 400

_redis: aioredis.Redis = None
_mongo_client = None
_db = None
_script_jobs = {}
_latest_script_jobs = {}
_active_script_job_id = None

# Metrics tracking
_metrics = {
    "hits": 0,
    "misses": 0,
    "avg_latency": 0,
    "latencies": [],
    "total_requests": 0,
    "last_request_ts": 0.0
}

SCRIPT_DEFS = {
    "ingest": {
        "label": "Dataset Ingestion",
        "description": "Download MovieLens, reload MongoDB, and warm the dashboard metrics.",
        "script_path": PROJECT_DIR / "src" / "ingest.py",
        "artifact_path": None,
        "env": {}
    },
    "benchmark": {
        "label": "Benchmark Script",
        "description": "Run the rich benchmark comparing cold-cache and warm-cache latency.",
        "script_path": PROJECT_DIR / "src" / "benchmark.py",
        "artifact_path": None,
        "env": {}
    },
    "visualize": {
        "label": "Visualization Report",
        "description": "Generate the matplotlib report image used for your oral demo.",
        "script_path": PROJECT_DIR / "dashboard" / "visualize.py",
        "artifact_path": PROJECT_DIR / "dashboard" / "redis_dashboard.png",
        "env": {"MPLBACKEND": "Agg"}
    }
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_job(job: dict) -> dict:
    script_name = job["script"]
    script_def = SCRIPT_DEFS[script_name]
    artifact_url = None
    artifact_path = script_def.get("artifact_path")

    if artifact_path and artifact_path.exists() and job.get("status") == "completed":
        artifact_url = f"/api/scripts/artifacts/{script_name}?t={int(artifact_path.stat().st_mtime)}"

    return {
        "id": job["id"],
        "script": script_name,
        "label": script_def["label"],
        "description": script_def["description"],
        "status": job["status"],
        "started_at": job["started_at"],
        "finished_at": job.get("finished_at"),
        "returncode": job.get("returncode"),
        "logs": job.get("logs", []),
        "command": job["command"],
        "artifact_url": artifact_url,
        "error": job.get("error"),
        "summary": job.get("summary")
    }


async def _run_script_job(job_id: str):
    global _active_script_job_id

    job = _script_jobs[job_id]
    script_def = SCRIPT_DEFS[job["script"]]
    env = os.environ.copy()
    env.update(script_def.get("env", {}))

    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_def["script_path"]),
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        job["process"] = process
        job["pid"] = process.pid

        while True:
            line = await process.stdout.readline()
            if not line:
                break

            decoded = line.decode("utf-8", errors="replace").rstrip()
            if not decoded:
                continue

            if decoded.startswith("BENCHMARK_SUMMARY_JSON:"):
                payload = decoded.split(
                    "BENCHMARK_SUMMARY_JSON:", 1)[1].strip()
                try:
                    job["summary"] = json.loads(payload)
                except Exception as parse_error:
                    job["logs"].append(
                        f"[runner] Failed to parse benchmark summary: {parse_error}")

            job["logs"].append(decoded)
            if len(job["logs"]) > MAX_SCRIPT_LOG_LINES:
                job["logs"] = job["logs"][-MAX_SCRIPT_LOG_LINES:]

        returncode = await process.wait()
        job["returncode"] = returncode
        job["finished_at"] = _utc_now_iso()

        if job["status"] != "cancelled":
            job["status"] = "completed" if returncode == 0 else "failed"
            if returncode != 0 and not job.get("error"):
                job["error"] = f"Script exited with code {returncode}"
    except Exception as exc:
        job["status"] = "failed"
        job["finished_at"] = _utc_now_iso()
        job["returncode"] = -1
        job["error"] = str(exc)
        job["logs"].append(f"[runner] {exc}")
    finally:
        job.pop("process", None)
        if _active_script_job_id == job_id:
            _active_script_job_id = None


def _get_active_job() -> dict | None:
    if not _active_script_job_id:
        return None
    return _script_jobs.get(_active_script_job_id)


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
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    log.info(f"✓ Static files mounted: {STATIC_DIR}")
else:
    log.warning(f"⚠ Static directory not found at {STATIC_DIR}")


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
    _metrics["total_requests"] += 1
    _metrics["last_request_ts"] = time.time()

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
        _metrics["latencies"].append(latency_ms)
        if len(_metrics["latencies"]) > 500:
            _metrics["latencies"] = _metrics["latencies"][-500:]
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
    _metrics["latencies"].append(latency_ms)
    if len(_metrics["latencies"]) > 500:
        _metrics["latencies"] = _metrics["latencies"][-500:]
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
    return FileResponse(str(STATIC_DIR / "index.html"))


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

    requests_last_min = 0
    now = time.time()
    if _metrics["last_request_ts"] and (now - _metrics["last_request_ts"]) <= 60:
        requests_last_min = _metrics["total_requests"]

    return {
        "hits": hits,
        "misses": misses,
        "total_requests": total,
        "hit_ratio_pct": ratio,
        "top10_movies": top10,
        "redis_memory_mb": round(info["used_memory"] / 1024 / 1024, 2),
        "redis_peak_memory_mb": round(info["used_memory_peak"] / 1024 / 1024, 2),
        "avg_latency": avg_latency,
        "app_total_requests": _metrics["total_requests"],
        "requests_last_min": requests_last_min
    }


@app.get("/api/dataset-status")
async def dataset_status_api():
    """Return MongoDB dataset loading status for dashboard visibility."""
    movies_count = await _db["movies"].count_documents({})
    ratings_count = await _db["ratings"].count_documents({})
    tags_count = await _db["tags"].count_documents({})

    loaded = movies_count > 0 and ratings_count > 0

    return {
        "loaded": loaded,
        "movies": movies_count,
        "ratings": ratings_count,
        "tags": tags_count,
        "database": "movielens"
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
        withscores = any(a.upper() == "WITHSCORES" for a in args)

        # Execute command
        if cmd == "GET" and len(args) == 1:
            result = await _redis.get(args[0])
        elif cmd == "SET" and len(args) >= 2:
            key = args[0]
            value = args[1]
            ex = None
            if len(args) >= 4 and args[2].upper() == "EX":
                ex = int(args[3])
            result = await _redis.set(key, value, ex=ex)
        elif cmd == "KEYS" and len(args) >= 1:
            result = await _redis.keys(args[0])
        elif cmd == "DEL" and len(args) >= 1:
            result = await _redis.delete(*args)
        elif cmd == "INCR" and len(args) == 1:
            result = await _redis.incr(args[0])
        elif cmd == "DECR" and len(args) == 1:
            result = await _redis.decr(args[0])
        elif cmd == "ZRANGE" and len(args) >= 3:
            result = await _redis.zrange(args[0], int(args[1]), int(args[2]), withscores=withscores)
        elif cmd == "ZREVRANGE" and len(args) >= 3:
            result = await _redis.zrevrange(args[0], int(args[1]), int(args[2]), withscores=withscores)
        elif cmd == "HGETALL" and len(args) == 1:
            result = await _redis.hgetall(args[0])
        elif cmd == "HGET" and len(args) == 2:
            result = await _redis.hget(args[0], args[1])
        elif cmd == "SMEMBERS" and len(args) == 1:
            result = list(await _redis.smembers(args[0]))
        elif cmd == "LRANGE" and len(args) == 3:
            result = await _redis.lrange(args[0], int(args[1]), int(args[2]))
        elif cmd == "EXISTS" and len(args) >= 1:
            result = await _redis.exists(*args)
        elif cmd == "TTL" and len(args) == 1:
            result = await _redis.ttl(args[0])
        elif cmd == "EXPIRE" and len(args) == 2:
            result = await _redis.expire(args[0], int(args[1]))
        elif cmd == "TYPE" and len(args) == 1:
            result = await _redis.type(args[0])
        elif cmd == "DBSIZE":
            result = await _redis.dbsize()
        elif cmd == "INFO":
            section = args[0] if args else None
            info = await _redis.info(section=section)
            result = json.dumps(info, indent=2, default=str)
        else:
            return {"error": f"Command '{cmd}' not supported in this tutorial"}

        return {"result": result, "error": None}

    except Exception as e:
        return {"error": str(e), "result": None}


@app.get("/api/scripts")
async def get_scripts_catalog():
    """Expose available automation scripts and current job state to the UI."""
    active_job = _get_active_job()
    scripts = []

    for name, script_def in SCRIPT_DEFS.items():
        latest_job_id = _latest_script_jobs.get(name)
        latest_job = _script_jobs.get(latest_job_id) if latest_job_id else None
        artifact_path = script_def.get("artifact_path")

        scripts.append({
            "name": name,
            "label": script_def["label"],
            "description": script_def["description"],
            "is_running": bool(active_job and active_job["script"] == name and active_job["status"] == "running"),
            "latest_job": _serialize_job(latest_job) if latest_job else None,
            "artifact_available": bool(artifact_path and artifact_path.exists())
        })

    recent_jobs = [
        _serialize_job(job)
        for job in sorted(_script_jobs.values(), key=lambda item: item["started_at"], reverse=True)[:10]
    ]

    return {
        "busy": bool(active_job and active_job["status"] == "running"),
        "demo_mode": DEMO_MODE,
        "tutorial_only_notice": "Automation endpoints are tutorial-only and intended for classroom demos.",
        "active_job": _serialize_job(active_job) if active_job else None,
        "scripts": scripts,
        "recent_jobs": recent_jobs
    }


@app.post("/api/scripts/{script_name}/run")
async def run_automation_script(script_name: str):
    """Launch a project script as a background job."""
    global _active_script_job_id

    if not DEMO_MODE:
        raise HTTPException(
            status_code=403,
            detail="Script launch is disabled. Set DEMO_MODE=true for tutorial/demo usage."
        )

    script_def = SCRIPT_DEFS.get(script_name)
    if not script_def:
        raise HTTPException(status_code=404, detail="Unknown script")

    if not script_def["script_path"].exists():
        raise HTTPException(
            status_code=500, detail=f"Script not found: {script_def['script_path']}")

    active_job = _get_active_job()
    if active_job and active_job["status"] == "running":
        return JSONResponse(
            status_code=409,
            content={
                "error": "Another automation script is already running",
                "active_job": _serialize_job(active_job)
            }
        )

    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "script": script_name,
        "status": "running",
        "started_at": _utc_now_iso(),
        "finished_at": None,
        "returncode": None,
        "logs": [f"[runner] Launching {script_def['label']}"],
        "command": [sys.executable, str(script_def["script_path"])],
        "error": None,
    }
    _script_jobs[job_id] = job
    _latest_script_jobs[script_name] = job_id
    _active_script_job_id = job_id

    asyncio.create_task(_run_script_job(job_id))
    return {"job": _serialize_job(job)}


@app.get("/api/scripts/jobs/{job_id}")
async def get_script_job(job_id: str):
    """Return detailed job status and log output."""
    job = _script_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": _serialize_job(job)}


@app.post("/api/scripts/jobs/{job_id}/cancel")
async def cancel_script_job(job_id: str):
    """Terminate a running automation job."""
    global _active_script_job_id

    if not DEMO_MODE:
        raise HTTPException(
            status_code=403,
            detail="Script cancellation is disabled when DEMO_MODE is off."
        )

    job = _script_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    process = job.get("process")
    if job["status"] != "running" or process is None:
        return {"job": _serialize_job(job)}

    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()

    job["status"] = "cancelled"
    job["finished_at"] = _utc_now_iso()
    job["returncode"] = -15
    job["error"] = "Cancelled from dashboard"
    job["logs"].append("[runner] Job cancelled from dashboard")
    job.pop("process", None)

    if _active_script_job_id == job_id:
        _active_script_job_id = None

    return {"job": _serialize_job(job)}


@app.get("/api/scripts/artifacts/{script_name}")
async def get_script_artifact(script_name: str):
    """Serve generated script artifacts such as the visualization PNG."""
    script_def = SCRIPT_DEFS.get(script_name)
    if not script_def:
        raise HTTPException(status_code=404, detail="Unknown artifact")

    artifact_path = script_def.get("artifact_path")
    if not artifact_path or not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")

    media_type = "image/png" if artifact_path.suffix == ".png" else None
    return FileResponse(str(artifact_path), media_type=media_type)


@app.get("/api/scripts/jobs/{job_id}/export")
async def export_script_job(job_id: str, format: str = "txt"):
    """Download script job logs and metadata for reporting."""
    job = _script_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    serialized = _serialize_job(job)
    safe_script = re.sub(r"[^a-zA-Z0-9_-]", "_", serialized["script"])
    safe_job = re.sub(r"[^a-zA-Z0-9_-]", "_", serialized["id"])

    if format == "json":
        payload = json.dumps(serialized, indent=2, ensure_ascii=True)
        filename = f"{safe_script}_{safe_job}.json"
        return StreamingResponse(
            BytesIO(payload.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    if format == "txt":
        lines = [
            f"Script: {serialized['label']} ({serialized['script']})",
            f"Job ID: {serialized['id']}",
            f"Status: {serialized['status']}",
            f"Started: {serialized['started_at']}",
            f"Finished: {serialized.get('finished_at')}",
            f"Return code: {serialized.get('returncode')}",
            "",
            "=== Logs ===",
            *serialized.get("logs", []),
        ]
        filename = f"{safe_script}_{safe_job}.log.txt"
        return StreamingResponse(
            BytesIO("\n".join(lines).encode("utf-8")),
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    raise HTTPException(status_code=400, detail="Supported formats: txt, json")
