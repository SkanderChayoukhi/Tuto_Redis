# USER GUIDE - Redis Inspector

Ce guide explique litteralement tout ce qui est visible et executable dans l interface UI, ainsi que les scripts et fichiers de code associes.

Objectif: pouvoir utiliser le tutoriel en autonomie, faire une demo complete en classe, et comprendre chaque terme technique utilise.

## 1. Avant de commencer

Demarrage minimal:

```bash
docker compose up --build
docker compose exec api python src/ingest.py
```

Puis ouvrir:

1. UI: http://localhost:8000
2. Health: http://localhost:8000/health

## 2. Vue d ensemble de l interface

L UI contient 5 onglets principaux:

1. Dashboard
2. Command Executor
3. Data Inspector
4. Performance
5. Automation

Chaque onglet est lie a des endpoints backend FastAPI et a des structures Redis precises.

## 3. Dashboard (metriques et graphs live)

### 3.1 Cartes metriques

1. Cache Hit Ratio
2. Memory Used
3. Avg Latency
4. Requests/sec

Definitions:

1. Hit: requete servie depuis Redis.
2. Miss: requete servie depuis MongoDB puis mise en cache.
3. Avg Latency: moyenne des latences recentes.
4. Requests/sec: debit instantane observe.

### 3.2 Dataset Status

Ce bloc affiche:

1. nombre de movies
2. nombre de ratings
3. nombre de tags
4. badge Loaded ou Not Loaded
5. Last update

Source API: endpoint dataset status.

Interpretation:

1. Loaded = donnees presentes en base, demo possible.
2. Not Loaded = lancer ingestion.

### 3.3 Graphiques

1. Request Latency Trend
2. Top 10 Movies (views)
3. Memory Distribution
4. Cache Efficiency

Que regarder pendant la demo:

1. baisse de latence apres warm cache
2. progression du hit ratio
3. evolution du leaderboard pendant les requetes

## 4. Command Executor (CLI Redis integre)

Cet onglet envoie des commandes Redis depuis l UI.

Important: il parle directement a Redis. Il ne remplace pas les endpoints applicatifs.

### 4.1 Commandes a tester en live

```redis
KEYS *
KEYS movie:*
GET movie:1
TTL movie:1
DBSIZE
INFO stats
ZREVRANGE leaderboard:movies 0 4 WITHSCORES
```

### 4.2 Pourquoi parfois GET movie:1 renvoie null

Cause typique:

1. cache pas encore chauffe
2. TTL expire

Solution:

1. onglet Performance puis Warm Cache
2. ou appeler /movies/1

## 5. Data Inspector (exploration des cles)

Fonction:

1. lister les cles Redis
2. afficher type, ttl et valeur
3. inspecter string, hash, list, set, zset

Cas d usage:

1. verifier qu une cle movie:{id} existe
2. verifier TTL et expiration
3. expliquer la structure leaderboard:movies

## 6. Performance (comparaison cold vs warm)

### 6.1 Boutons

1. Flush Cache (Cold Start)
2. Warm Cache

### 6.2 Logique

1. Flush: vide Redis, prochaine requete plus lente
2. Warm: precharge des films populaires, requetes suivantes plus rapides

### 6.3 Graphique Latency Comparison

Affiche 2 barres:

1. Cold Cache
2. Warm Cache

Objectif pedagogique:

1. visualiser clairement le gain de cache
2. relier la theorie au comportement observe

## 7. Automation (scripts depuis UI)

Cet onglet permet de lancer les scripts Python sans terminal.

Scripts disponibles:

1. ingest.py
2. benchmark.py
3. visualize.py

### 7.1 Ce que montre cet onglet

1. statut des scripts (Idle, Running, Completed, Failed)
2. job actif
3. logs en direct
4. historique des jobs
5. preview image de visualize.py

### 7.2 Comportement de chaque script

1. ingest.py
   1. telecharge ou reutilise l archive locale du dataset
   2. recharge MongoDB
   3. warmup de metriques
2. benchmark.py
   1. lance serie de requetes cold puis warm
   2. imprime latences et speedup
3. visualize.py
   1. collecte metriques
   2. genere image dashboard/redis_dashboard.png

### 7.3 Bonnes pratiques demo

1. lancer ingest avant la presentation
2. lancer benchmark en direct pour montrer le gain
3. lancer visualize a la fin pour obtenir une figure exportable

## 8. Tous les termes a connaitre

1. Cache Hit: donnee disponible en cache
2. Cache Miss: donnee absente du cache
3. Hot Cache: cache deja rempli
4. Cold Cache: cache vide ou peu rempli
5. TTL: Time To Live d une cle
6. p50: mediane des latences
7. p95: 95 percent des latences sous ce seuil
8. p99: 99 percent des latences sous ce seuil
9. RPS: Requests Per Second
10. Leaderboard: classement dans un Sorted Set
11. Rate Limiting: limitation du nombre de requetes par IP
12. Cache-Aside: pattern applicatif de cache utilise ici

## 9. Commandes CLI utiles hors UI

### 9.1 Docker

```bash
docker compose ps
docker compose logs api
docker compose restart api
```

### 9.2 Ingestion et benchmark

```bash
docker compose exec api python src/ingest.py
python src/benchmark.py
python dashboard/visualize.py
```

### 9.3 API test rapide

```bash
curl http://localhost:8000/health
curl http://localhost:8000/movies/1
curl http://localhost:8000/stats
curl http://localhost:8000/api/metrics
```

## 10. Lien UI <-> code files (ce qui fait quoi)

1. src/main.py
   1. endpoints metier movies/stats/cache
   2. endpoints UI /api/metrics /api/keys /api/command
   3. endpoints automation scripts/jobs/artifacts
2. src/ingest.py
   1. telechargement dataset
   2. chargement MongoDB
   3. warmup
3. src/benchmark.py
   1. scenario cold/warm
   2. affichage des mesures
4. dashboard/visualize.py
   1. generation figure matplotlib
5. static/index.html
   1. structure de tous les onglets
6. static/js/dashboard.js
   1. logique frontend, polling, charts, actions
7. static/css/dashboard.css
   1. styles UI

## 11. Checklist de demo 15 min

1. Verifier containers UP
2. Verifier dataset loaded
3. Ouvrir Dashboard et commenter les 4 KPIs
4. Montrer Command Executor avec commandes tests
5. Montrer Data Inspector
6. Faire Flush puis Warm dans Performance
7. Lancer benchmark et visualize depuis Automation
8. Conclure sur gains et limites

## 12. FAQ rapide

1. Pourquoi les compteurs ne bougent pas?
   1. verifier polling UI
   2. verifier endpoint /api/metrics
2. Pourquoi aucune cle movie:\*?
   1. cache pas chauffe
   2. lancer warm cache
3. Pourquoi ingest peut echouer?
   1. timeout internet sur le download initial
   2. relancer, archive locale reutilisable

## 13. Message final pour la classe

Ce tutoriel montre en pratique:

1. comment un cache Redis transforme les performances
2. comment instrumenter et visualiser un systeme NoSQL
3. comment relier theorie Big Data et demonstration live

Si la classe veut reproduire rapidement:

1. cloner le repo
2. docker compose up --build
3. docker compose exec api python src/ingest.py
4. ouvrir http://localhost:8000
