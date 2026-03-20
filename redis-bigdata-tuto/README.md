# Redis BigData Cache — Tutoriel IMT Atlantique

> **UE BigData FISE A3 — Tutoriel NoSQL : Redis (key-value store)**
> Auteurs : `[vos noms]` | Dataset : MovieLens Small (GroupLens)

---

## Présentation

Ce tutoriel démontre l'utilisation de **Redis** comme système de cache intelligent dans un pipeline BigData, en réponse au problème de **vélocité** (V du BigData) : comment répondre à des millions de requêtes rapidement sans surcharger la source de données ?

### Cas d'usage

Une API de recommandation de films reçoit des milliers de requêtes par seconde. Chaque requête sans cache implique un aller-retour MongoDB coûteux. Redis agit comme couche intermédiaire ultra-rapide grâce à son stockage **en mémoire** et son modèle **clé-valeur**.

### Ce que ce tutoriel illustre (liens avec le cours)

| Concept du cours        | Implémentation dans ce projet                    |
| ----------------------- | ------------------------------------------------ |
| NoSQL key-value         | Redis stocke `movie:{id}` → JSON                 |
| Vélocité (V BigData)    | Cache réduit la latence de 10x à 50x             |
| Scalabilité horizontale | Redis Cluster ready (architecture `allkeys-lru`) |
| CAP Theorem             | Redis = AP (Available + Partition Tolerant)      |
| Dénormalisation         | Documents MongoDB enrichis (avg_rating embarqué) |
| TTL (Time To Live)      | Expiration automatique des entrées stales        |
| Sorted Sets             | Leaderboard des films les plus consultés         |

---

## Architecture

```
Client (Python / curl)
        │
        ▼
  ┌─────────────┐
  │   FastAPI   │  ← REST endpoint /movies/{id}
  └──────┬──────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌─────────┐
│ Redis │ │ MongoDB │
│ Cache │ │ Source  │
│ (RAM) │ │ (disk)  │
└───────┘ └─────────┘
    ▲         │
    └─────────┘
    populate cache
```

**Flux de données :**

1. Requête entrante → vérification rate limit (Redis INCR)
2. Lecture clé `movie:{id}` dans Redis → **cache hit** → réponse < 2ms
3. Si absent → requête MongoDB → calcul avg_rating → **populate Redis** → réponse ~50ms
4. Chaque accès → `ZINCRBY leaderboard:movies` pour le classement temps réel

---

## Stack technique

| Service            | Version  | Rôle                                       |
| ------------------ | -------- | ------------------------------------------ |
| **Redis**          | 7-alpine | Cache key-value, rate limiter, leaderboard |
| **MongoDB**        | 7        | Source de données principale               |
| **FastAPI**        | 0.111    | API REST asynchrone                        |
| **Python**         | 3.11     | Scripts de benchmark et ingestion          |
| **Docker Compose** | v2       | Orchestration locale                       |

---

## Démarrage rapide

### Prérequis

- Docker Desktop (ou Docker Engine + Docker Compose v2)
- Python 3.10+ (pour les scripts hors-container)

### 1. Cloner le repo

```bash
git clone https://github.com/[votre-username]/redis-bigdata-tuto.git
cd redis-bigdata-tuto
```

### 2. Démarrer les services

```bash
docker-compose up --build
```

Les trois services démarrent :

- FastAPI → http://localhost:8000
- Redis → localhost:6379
- MongoDB → localhost:27017

### 3. Charger le dataset MovieLens

Dans un second terminal :

```bash
# Recommandé (utilise l'environnement du conteneur API)
docker compose exec api python src/ingest.py

# Alternative locale (si vous avez un venv Python prêt)
# pip install -r requirements.txt
# python src/ingest.py
```

Cette étape télécharge automatiquement [MovieLens Small](https://grouplens.org/datasets/movielens/latest/) (~1 Mo) et charge les données dans MongoDB.

### 4. Tester l'API

```bash
# Vérifier que tout fonctionne
curl http://localhost:8000/health

# Premier appel → cache miss (MongoDB)
curl http://localhost:8000/movies/1

# Second appel → cache hit (Redis, beaucoup plus rapide)
curl http://localhost:8000/movies/1

# Voir les stats du cache
curl http://localhost:8000/stats

# Recherche par genre
curl "http://localhost:8000/movies?genre=Action&limit=10"
```

### 5. Lancer le benchmark

```bash
python src/benchmark.py
```

Résultat attendu (sur machine standard) :

```
╭──────────────────────────────────────────────────────────────────────╮
│             Résultats du benchmark                                   │
├─────────────────┬────────────────────┬───────────────────┬─────────┤
│ Métrique        │ Cache FROID (MongoDB) │ Cache CHAUD (Redis) │ Speedup │
├─────────────────┼────────────────────┼───────────────────┼─────────┤
│ Latence moyenne │ 48.32 ms           │ 1.84 ms           │ 26.3x   │
│ Médiane (p50)   │ 45.10 ms           │ 1.60 ms           │ 28.2x   │
│ p95             │ 89.40 ms           │ 3.20 ms           │ 27.9x   │
│ p99             │ 112.80 ms          │ 4.80 ms           │ 23.5x   │
└─────────────────┴────────────────────┴───────────────────┴─────────┘
```

### 6. Access the Interactive Dashboard

**IMPORTANT**: The tutorial now includes a professional interactive dashboard!

```bash
# The dashboard is automatically available at:
http://localhost:8000
```

**Dashboard Features**:

- 📊 **Real-time Metrics**: Cache hit ratio, memory usage, latency
- 💻 **Redis Command Executor**: Type Redis commands in the browser
- 🔍 **Data Inspector**: Browse all keys and their values
- ⚡ **Performance Lab**: Compare cold vs warm cache speeds
- 📈 **Live Charts**: Visualize latency trends and leaderboards

**No need for terminal commands anymore!** Everything is clickable and visual.

---

## 📚 Complete Documentation

### Main Files to Read

1. **[TUTORIAL.md](./TUTORIAL.md)** - Full Big Data concepts and theory
   - Why Redis matters for Big Data
   - Data modeling and caching strategies
   - CAP theorem and consistency
   - Real-world case studies

2. **[USER_GUIDE.md](./USER_GUIDE.md)** - Interactive learning exercises
   - Dashboard walkthrough
   - Hands-on Redis commands
   - Learning challenges
   - Troubleshooting guide

3. **[CREATIVE_IMPROVEMENTS.md](./CREATIVE_IMPROVEMENTS.md)** - Architecture details
   - System design
   - API endpoints
   - Implementation notes

---

## 🚀 Quick Start (Dashboard Version)

### 1. Start Everything

```bash
docker-compose up --build
```

### 2. Load Data

```bash
pip install -r requirements.txt
python src/ingest.py
```

### 3. Open Dashboard

**Browser**: `http://localhost:8000`

### 4. Try the Redis Command Executor

In the **Command Executor** tab:

```redis
GET movie:1              # Get a cached movie
ZREVRANGE leaderboard:movies 0 4  # Top 5 movies
DBSIZE                   # How many keys cached
```

### 5. Watch the Metrics Update

Dashboard shows real-time:

- Cache hit/miss ratio
- Memory usage
- Request latency
- Top accessed movies

---

### 6. Visualiser le dashboard

```bash
python dashboard/visualize.py
```

Génère `dashboard/redis_dashboard.png` avec 4 graphiques :

- Évolution du hit ratio
- Comparaison latence Redis vs MongoDB
- Leaderboard (Top 10 films les plus vus)
- Consommation mémoire Redis

---

## Structures de données Redis utilisées

### Strings (cache principal)

```
SET movie:1  '{"movieId":"1","title":"Toy Story","genres":["Animation"],"avg_rating":3.92}'  EX 60
GET movie:1
```

### Counters (stats & rate limiting)

```
INCR stats:hits
INCR stats:misses
INCR rate:192.168.1.1        # compteur par IP
EXPIRE rate:192.168.1.1 60   # fenêtre de 1 minute
```

### Sorted Sets (leaderboard)

```
ZINCRBY leaderboard:movies 1 "296"    # +1 vue pour le film 296
ZREVRANGE leaderboard:movies 0 9 WITHSCORES  # Top 10
```

---

## Concepts BigData illustrés

### Pourquoi Redis est un outil BigData ?

1. **Vélocité** : Redis opère entièrement en RAM. Latence < 1ms pour les opérations simples.
2. **Volume** : Redis Cluster permet le sharding horizontal sur N nœuds. Chaque nœud gère une partie du keyspace (hash slots 0-16383).
3. **Scalabilité horizontale** : La politique `allkeys-lru` (Least Recently Used) permet d'éviter l'OOM sur des volumes importants.

### CAP Theorem et Redis

Redis se positionne comme système **AP** (Available + Partition Tolerant) :

- En mode cluster, Redis préfère rester disponible plutôt que de garantir une cohérence parfaite lors d'une partition réseau.
- La réplication Redis est **asynchrone** : une panne du master pendant une réplication peut causer une légère perte de données.
- Pour des cas nécessitant une cohérence forte (CP), Redis propose le mode `WAIT` pour forcer une écriture synchrone sur les répliques.

### TTL et fraîcheur des données

```python
CACHE_TTL = 60  # secondes

# Stratégies de cache :
# - Cache-aside (ce projet) : l'application gère le cache manuellement
# - Write-through : écriture simultanée DB + cache
# - Write-behind : écriture différée en DB (Redis en tampon)
```

---

## Structure du projet

```
redis-bigdata-tuto/
├── docker-compose.yml    # Orchestration des 3 services
├── Dockerfile            # Image FastAPI
├── requirements.txt      # Dépendances Python
├── src/
│   ├── main.py           # API FastAPI + logique cache Redis
│   ├── ingest.py         # Téléchargement et chargement MovieLens → MongoDB
│   └── benchmark.py      # Mesure de performance cache froid vs chaud
├── dashboard/
│   └── visualize.py      # Dashboard matplotlib (4 graphiques)
└── README.md
```

---

## Pour aller plus loin

- **Redis Cluster** : modifier `docker-compose.yml` pour ajouter des nœuds Redis en sharding
- **Pub/Sub** : ajouter un channel Redis pour les notifications temps réel
- **Redis Streams** : remplacer MongoDB comme source par des streams Redis (IoT-style)
- **Grafana + RedisTimeSeries** : dashboard temps réel avec persistance des métriques

---

## Références

- [Redis documentation](https://redis.io/docs/)
- [MovieLens Dataset — GroupLens](https://grouplens.org/datasets/movielens/)
- Cours UE BigData — Hélène Coullon, IMT Atlantique (2025-2026)
- [CAP Theorem — Gilbert & Lynch, 2002](https://dl.acm.org/doi/10.1145/564585.564601)
