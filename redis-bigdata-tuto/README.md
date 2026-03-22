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

````
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
   # Redis Inspector Pro - Tutoriel NoSQL Redis (Big Data)

   Tutoriel conteneurise pour la presentation orale du mardi 24/03 apres-midi.

   Objectif du projet: montrer, de maniere concrete et demo-ready, comment Redis resout le probleme de velocite dans un systeme Big Data grace au cache en memoire.

   ## 1. Contexte et objectif pedagogique

   Ce tutoriel couvre les rendus demandes:

   1. Tutoriel conteneurise: Docker Compose lance Redis, MongoDB et FastAPI.
   2. Repo GitHub avec README complet: ce fichier est le document principal de reference.
   3. Dataset en ligne: MovieLens Small, telecharge automatiquement.
   4. Visualisation des donnees: dashboard web interactif + script de visualisation matplotlib.

   Cas d usage choisi: API movies avec cache Redis devant MongoDB.

   Lecture Big Data associee:

   1. Vitesse de reponse: cache hit en quelques ms.
   2. Scalabilite: reduction de charge sur la base source.
   3. Tradeoff coherence/fraicheur: TTL + cache-aside.

   ## 2. Architecture

   Flux principal:

   1. Le client appelle GET /movies/{movie_id}.
   2. FastAPI interroge Redis (cle movie:{id}).
   3. Si hit: reponse immediate.
   4. Si miss: lecture MongoDB, enrichissement, ecriture Redis avec TTL, reponse.
   5. Chaque appel alimente des stats Redis et un leaderboard (Sorted Set).

   Services Docker:

   1. redis (cache + stats + rate-limit + leaderboard)
   2. mongo (source de verite)
   3. api (FastAPI + UI + scripts automatises)

   ## 3. Dataset et modelisation

   Dataset en ligne utilise:

   1. Source: GroupLens MovieLens Small
   2. Taille: environ 1 Mo
   3. Contenu: movies, ratings, tags

   Collections MongoDB:

   1. movies
   2. ratings
   3. tags

   Cles Redis principales:

   1. movie:{id}: cache film enrichi
   2. search:genre:*: cache des recherches
   3. leaderboard:movies: classement des films les plus consultes
   4. stats:hits et stats:misses: compteurs de performance
   5. rate:{ip}: compteur rate limiting

   ## 4. Installation a partager a la classe

   Prerequis a envoyer avant la seance:

   1. Docker Desktop (ou Docker Engine + compose v2)
   2. Git
   3. Port 8000 libre (et 6379, 27017)

   Commandes d installation:

   ```bash
   git clone https://github.com/SkanderChayoukhi/Tuto_Redis.git
   cd Tuto_Redis/redis-bigdata-tuto
   docker compose up --build
````

Chargement du dataset (recommande):

```bash
docker compose exec api python src/ingest.py
```

Acces interface:

1.  URL UI: http://localhost:8000
2.  Healthcheck API: http://localhost:8000/health

## 5. Demonstration rapide (15 minutes)

Plan oral recommande avec participation de tout le groupe:

1.  Intro (2 min): probleme Big Data + role du cache.
2.  Architecture (2 min): Redis, MongoDB, FastAPI, Docker.
3.  Live UI (7 min): Dashboard, Command Executor, Data Inspector, Performance, Automation.
4.  Scripts (2 min): ingestion, benchmark, visualization lances depuis l UI.
5.  Conclusion (2 min): gains observes, limites et extensions.

Repartition de parole suggeree:

1.  Personne A: contexte et architecture
2.  Personne B: demo UI et commandes Redis
3.  Personne C: benchmark, graphs, conclusion

## 6. Ce qui est executable dans le projet

Depuis l UI:

1.  Visualisation metriques en temps reel
2.  Execution de commandes Redis
3.  Inspection des cles et valeurs
4.  Benchmark cold vs warm cache
5.  Lancement des scripts ingest.py, benchmark.py, visualize.py

Depuis terminal:

```bash
docker compose exec api python src/ingest.py
python src/benchmark.py
python dashboard/visualize.py
```

## 7. API utile pour la demo

Endpoints principaux:

1.  GET /health
2.  GET /movies/{movie_id}
3.  GET /movies?genre=Action&limit=10
4.  GET /stats
5.  DELETE /cache

Endpoints UI:

1.  GET /
2.  GET /api/metrics
3.  GET /api/dataset-status
4.  GET /api/keys
5.  GET /api/key/{key_name}
6.  POST /api/command
7.  GET /api/scripts
8.  POST /api/scripts/{script_name}/run

## 8. Concepts NoSQL et metriques a expliquer a l oral

1.  Hit: donnee trouvee dans Redis.
2.  Miss: donnee absente de Redis, lecture MongoDB necessaire.
3.  Hot cache: cache deja rempli, latence faible.
4.  Cold cache: cache vide, latence plus elevee.
5.  TTL: duree de vie d une cle en cache.
6.  p50, p95, p99: percentiles de latence.

Interpretation simple:

1.  p50 = mediane (latence typique)
2.  p95 = latence des cas lents frequents
3.  p99 = latence de queue (cas extremes)

## 9. Structure projet

```text
redis-bigdata-tuto/
   docker-compose.yml
   Dockerfile
   requirements.txt
   src/
      main.py
      ingest.py
      benchmark.py
   dashboard/
      visualize.py
   static/
      index.html
      css/dashboard.css
      js/dashboard.js
   data/
   README.md
   USER_GUIDE.md
```

## 10. Troubleshooting express

1.  UI ne charge pas: docker compose up --build
2.  Pas de donnees: lancer ingest.py
3.  Commandes Redis vides: chauffer le cache via onglet Performance ou appel /movies/{id}
4.  Script ingestion timeout internet: relancer ingestion, l archive locale est reutilisee si deja telechargee

## 11. Valeur pedagogique du tuto

Ce projet n est pas un simple CRUD.

Il montre:

1.  un vrai pattern cache-aside
2.  des structures Redis utiles en production
3.  des gains de latence mesurables
4.  une demo integrale exploitable devant une classe

## 12. A lire ensuite

Le guide complet de l interface, des commandes et des termes est dans USER_GUIDE.md.

- Comparaison latence Redis vs MongoDB
