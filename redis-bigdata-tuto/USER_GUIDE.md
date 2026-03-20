# Redis Inspector Pro - User Guide & Learning Exercises

## Getting Started with the Dashboard

### Accessing the Dashboard

1. **Start the system**:

   ```bash
   cd redis-bigdata-tuto
   docker-compose up --build
   ```

2. **Load data**:

   ```bash
   python src/ingest.py
   ```

3. **Open in browser**:
   ```
   http://localhost:8000
   ```

You should see a colorful dashboard with real-time metrics!

---

## Dashboard Walkthrough

### 📊 Dashboard Tab (Default View)

This tab shows live metrics from your Redis cache:

```
┌─────────────────────────────────────────┐
│ Redis Inspector Pro          [Connected]│
├─────────────────────────────────────────┤
│  Cache Hit Ratio    Memory Used    Avg Latency    RPS
│    85.3%            12.5 MB        2.1 ms        4200
│ 85 hits / 100 req   Peak: 15 MB    Last 100 req  (req/sec)
└─────────────────────────────────────────┘

[Charts Below]
```

**What Each Metric Means**:

- **Cache Hit Ratio (85%)**: Of the last 100 requests, 85 were answered by Redis (fast), 15 hit MongoDB (slow)
- **Memory Used (12.5 MB)**: Redis is consuming 12.5 MB of your computer's RAM
- **Avg Latency (2.1 ms)**: Average response time for the last request batch
- **RPS (4200)**: Redis is handling 4,200 requests per second

**Interactive Charts**:

1. **Latency Trend**: Line chart showing response times over last ~20 requests
   - Flat line = consistent performance ✓
   - Spikes up = possible cache misses

2. **Top 10 Movies**: Bar chart showing which movies are accessed most
   - This data comes from the `leaderboard:movies` Sorted Set
   - Taller bars = more popular movies

3. **Memory Distribution**: Pie chart of RAM usage
   - All data is currently in single Redis instance
   - In production, this helps you understand storage needs

4. **Cache Efficiency**: Gauge showing hit/miss ratio
   - Green = high ratio (> 80%)
   - Red = low ratio (data not cached well)

---

## 💻 Command Executor Tab

This is like a **Redis CLI in your browser**. Type any Redis command!

### Example Workflow

#### Exercise 1: Explore Cached Movies

```
> KEYS movie:*
(Returns all movie keys like: movie:1, movie:110, movie:27, ...)

> GET movie:1
(Returns: {"movieId":"1", "title":"Toy Story", "avg_rating":4.14, ...})

> TTL movie:1
(Returns: 3598 - expires in 3598 seconds = ~1 hour)
```

**What You Learned**:

- `KEYS pattern` = find all keys matching pattern
- `GET key` = retrieve a cached value
- `TTL key` = time until key expires (in seconds)

#### Exercise 2: Check Cache Statistics

```
> DBSIZE
(Returns: 437 - there are 437 keys in Redis)

> INFO stats
(Returns: detailed info about hits, misses, evictions, etc.)
```

#### Exercise 3: Explore the Leaderboard

```
> ZREVRANGE leaderboard:movies 0 4 WITHSCORES
([["1", "487"], ["110", "382"], ["27", "273"], ["48", "214"], ["227", "195"]])

Interpretation:
  - Movie 1 has been viewed/accessed 487 times ⭐ MOST POPULAR
  - Movie 110 has been viewed 382 times
  - Movie 27 has been viewed 273 times
  - ... and so on
```

**What You Learned**:

- `ZREVRANGE key 0 N WITHSCORES` = get top N by score
- This is useful for **leaderboards**, **trending items**, **popularity rankings**

#### Exercise 4: Add New Data

```
> SET my_test_key "Hello Redis!"
(Returns: OK)

> GET my_test_key
(Returns: "Hello Redis!")

> EXPIRE my_test_key 10
(Set expiration to 10 seconds - then watch it disappear!)

> GET my_test_key
(After 10 seconds: returns nil - expired!)
```

**What You Learned**:

- You can set arbitrary data in Redis
- TTL makes cache automatically clean up old data
- This prevents memory from filling up forever

#### Exercise 5: Rate Limiting Check

```
> GET rate:127.0.0.1
(Returns your IP's request count in current minute)

> INCR rate:127.0.0.1
(Simulate a new request - count goes up)
```

---

## 🔍 Data Inspector Tab

This tab shows all keys stored in Redis and their details.

### Walkthrough

**Left panel**: List of all keys

```
movie:1               (string)  ttl: 3456s
movie:110             (string)  ttl: 3421s
movie:27              (string)  ttl: 3398s
leaderboard:movies    (zset)    ttl: -1 (never expires)
rate:127.0.0.1        (string)  ttl: 45s
search:genre:Action   (string)  ttl: 2134s
...
```

**Right panel**: Details when you click a key

```
Key: movie:1
Type: string
TTL: 3455

Value:
{
  "movieId": "1",
  "title": "Toy Story (1995)",
  "genres": ["Adventure", "Animation", "Comedy"],
  "avg_rating": 4.14,
  "rating_count": 247
}
```

### Analysis Tasks

1. **Count movies cached**: Count how many `movie:*` keys exist (tells you cache size)
2. **Find expiring soon**: Look for keys with low TTL (< 60s)
3. **Check leaderboard**: Click `leaderboard:movies` to see top movies
4. **Inspect searches**: Look at `search:genre:*` keys to see cached searches

---

## ⚡ Performance Tab

Compare how fast Redis is vs MongoDB.

### Benchmark Challenge

1. **Click "Flush Cache (Cold Start)"**
   - This deletes all cached data
   - Next request will be slow (hits MongoDB)
2. **Make a request** (via Command Executor):

   ```
   > GET movie:1
   ```

   - Response: data + slow latency (50ms)

3. **Click "Warm Cache"**
   - Rebuilds the most popular movies in cache
4. **Make the same request again**:

   ```
   > GET movie:1
   ```

   - Response: same data + FAST latency (2ms)

5. **Watch the chart**: Compare "Cold Cache" vs "Warm Cache" bars

---

## 🚀 Learning Exercises

### Exercise 1: Cache Hit Ratio Optimization

**Goal**: Get cache hit ratio above 90%

**Steps**:

1. Go to Command Executor
2. Run: `GET movie:1`, `GET movie:110`, `GET movie:27` (multiple times)
3. Watch Cache Hit Ratio in Dashboard
4. If still low, request more different movies to populate cache

**Learning**: High hit ratios require frequently accessing the same data (Zipf's Law)

---

### Exercise 2: TTL (Time To Live) Experiment

**Goal**: Watch keys expire

**Steps**:

1. Command Executor: `SET temporary_key "This will expire" EX 5`
2. Data Inspector: Click on `temporary_key` and note the TTL (should be ~5)
3. Wait 6 seconds
4. Refresh Data Inspector: key should be gone!

**Learning**: TTL keeps cache fresh without manual invalidation

---

### Exercise 3: Leaderboard Ranking

**Goal**: Find the top 5 most accessed movies

**Steps**:

1. Command Executor: `ZREVRANGE leaderboard:movies 0 4 WITHSCORES`
2. Alternatively, view "Top 10 Movies" chart in Dashboard
3. Note which movies are popular

**Question**: Why are certain movies more popular?

- **Answer**: Depends on the dataset, but typically:
  - Newer movies (recent releases)
  - Well-known movies (Toy Story, Avatar)
  - Highly-rated movies

**Learning**: Sorted Sets enable efficient ranking without expensive sorting

---

### Exercise 4: Memory vs Speed Tradeoff

**Goal**: Understand why caching uses more storage

**Steps**:

1. Dashboard: Check "Memory Used" - note the amount
2. Command Executor: `DBSIZE` - count of keys
3. Calculate: Memory Used / DBSIZE = bytes per key

**Analysis**:

- MovieLens data: ~3KB per movie (with stats)
- 100 movies in cache = 300KB
- 1000 movies in cache = 3MB

**Question**: If we cache all 10,000 movies, memory needed?

- **Answer**: 30MB (acceptable)
- But what if data was 10x larger (photos)? 300MB needed!

**Learning**: Cache effectively requires balancing memory vs coverage

---

### Exercise 5: Rate Limiting Simulation

**Goal**: See rate limiting in action

**Steps**:

1. Rapidly send requests to `/movies/1` (use benchmark)
2. Check rate limit key: `GET rate:127.0.0.1`
3. Request counter increases
4. Wait 60 seconds
5. Check again: counter resets!

**Learning**: Redis `INCR` enables fast rate limiting without database

---

### Exercise 6: Consistency Check

**Goal**: Detect stale cache

**Steps**:

1. Command Executor: `GET movie:1` - note the `avg_rating`
2. Imagine MongoDB was updated with new ratings
3. Command Executor: `DEL movie:1` - invalidate cache
4. Request again: `GET movie:1` - should be slow (updated from MongoDB)
5. Second request: fast again (re-cached)

**Learning**: Cache invalidation is important for consistency (CAP theorem A vs C)

---

## 📈 Real-World Scenarios

### Scenario 1: Black Friday Flash Sale

**Situation**: A movie gets 1000 searches in 1 minute

**Without Redis**:

- Every search hits MongoDB
- Database gets 1000 req/sec - CRASHES ❌

**With Redis**:

- First search: cold miss → MongoDB (slow)
- Next 999 searches: cache hit → Redis (instant)
- Database gets 1 req/sec - NO PROBLEM ✓

**Redis benefit**: 1000x amplification of cache hit = system survives traffic spike

---

### Scenario 2: Global User Base

**Situation**: Users from US, Europe, and Asia all accessing movies

**Architecture**:

```
┌─────────────────────────────────┐
│ Global Load Balancer            │
├─────────────────────────────────┤
│ US Servers                      │ Europe Servers              │ Asia Servers
│ ├─ Redis (cache)                │ ├─ Redis (cache)           │ ├─ Redis (cache)
│ ├─ FastAPI      |               │ ├─ FastAPI                 │ ├─ FastAPI
│ └─ MongoDB copy │               │ └─ MongoDB replica         │ └─ MongoDB copy
└──────────────────────────────────────────────────────────────┘
```

**Without local Redis**:

- US user requests → latency 100ms
- Europe user requests → latency 100ms (same servers)
- Asia user requests → latency 500ms (far away)

**With local Redis**:

- All users: latency 2ms (cache is local)

**Learning**: Caching solves geographic latency problems

---

### Scenario 3: Peak vs Off-Peak

**Peak Hours (8-11pm TV watching)**:

- 10 million concurrent users
- Need 5000 cache servers to handle load

**Off-Peak Hours (3-6am)**:

- 100,000 users
- Need 5 cache servers

**Cost Optimization**:

- Use auto-scaling: add cache servers during peak
- Redis Cluster can add/remove nodes dynamically
- Save costs by scaling down at night

**Learning**: Cloud-native caching enables cost-efficient operations

---

## 🎓 Quiz & Assessment

### Questions for Your Portfolio

1. **What is the hit ratio you can achieve?**
   - Run benchmark, take screenshot of dashboard
2. **How much memory does 100 cached movies use?**
   - Use `INFO memory` before and after caching
3. **What's the latency reduction between cold and warm cache?**
   - Use Performance tab, calculate speedup
4. **Design a caching strategy for 1 billion users**
   - How many cache servers needed? (Assume 2MB per customer session)
   - How much would it cost?
   - What's the ROI vs not caching?

5. **If cache memory is limited to 256MB, which 1000 movies should we keep?**
   - Answer: Top 1000 by view count (Zipf's Law)
   - Verify using leaderboard

---

## 🐛 Troubleshooting

### Dashboard shows 0% hit ratio

**Cause**: Cache is empty (just started)

**Solution**:

1. Generate traffic: repeatedly request `/movies/1`
2. Wait for 20+ requests
3. Hit ratio will increase as cache fills

### Memory keeps increasing

**Cause**: No TTL on keys, cache growing unbounded

**Solution**:

1. Check: `INFO memory` - how much used?
2. Set maxmemory: `CONFIG SET maxmemory 256mb`
3. Set eviction: `CONFIG SET maxmemory-policy allkeys-lru`

### Command Executor shows "Command not supported"

**Cause**: That command isn't in the tutorial whitelist

**Solution**: Use only these commands:

- GET, SET, INCR, DECR, DEL, KEYS, TTL, EXPIRE, TYPE, DBSIZE
- HGET, HGETALL, HSET, HLEN
- ZRANGE, ZREVRANGE, ZADD, ZCARD, ZINCRBY
- SADD, SMEMBERS, SCARD
- INFO

---

## 📚 Resources

### Inside the Tutorial

- `TUTORIAL.md` - Complete Big Data concepts
- `CREATIVE_IMPROVEMENTS.md` - Architecture details
- `src/main.py` - Source code comments
- `src/benchmark.py` - Performance testing code

### External

- [Redis Commands](https://redis.io/commands/)
- [Redis Best Practices](https://docs.redis.com/latest/rs/references/best-practices/)
- [Big Data Architecture Patterns](https://aws.amazon.com/big-data/)

---

## 🎉 You've Completed the Tutorial!

You've learned:

- ✅ How Redis works (key-value store)
- ✅ Cache hit/miss ratios
- ✅ TTL and cache expiration
- ✅ Data structures (strings, sorted sets, hashes)
- ✅ Leaderboards and rankings
- ✅ Rate limiting
- ✅ Performance optimization (25x speedups!)
- ✅ Big Data concepts (velocity, scalability, CAP theorem)

**Next Steps**:

1. Modify `src/main.py` to add new features
2. Implement more complex caching strategies
3. Set up Redis Cluster (bonus!)
4. Deploy to cloud (AWS, Azure, GCP)

**Congratulations!** 🎓

---

_Interactive Big Data Learning | IMT Atlantique 2026_
