// =========================================
// REDIS INSPECTOR PRO - DASHBOARD JAVASCRIPT
// =========================================

// Global state
const state = {
    metrics: {
        hits: 0,
        misses: 0,
        requests: [],
        latencies: [],
        memory: 0,
        peakMemory: 0,
        topMovies: [],
        rps: 0
    },
    benchmark: {
        coldMs: 0,
        warmMs: 0
    },
    automation: {
        busy: false,
        activeJob: null,
        recentJobs: [],
        scripts: []
    },
    lastSample: {
        ts: Date.now(),
        total: 0
    },
    charts: {},
    ws: null,
    connected: false
};

// Chart instances
let latencyChart = null;
let leaderboardChart = null;
let memoryChart = null;
let hitRatioChart = null;
let benchmarkChart = null;

// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', function() {
    initCharts();
    setupEventListeners();
    startMetricsPolling();
    startDatasetPolling();
    startAutomationPolling();
    loadKeysInspector();
});

// ===== CHARTS INITIALIZATION =====
function initCharts() {
    const ctx1 = document.getElementById('latencyChart').getContext('2d');
    latencyChart = new Chart(ctx1, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Request Latency (ms)',
                data: [],
                borderColor: '#1a73e8',
                backgroundColor: 'rgba(26, 115, 232, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true, position: 'top' }
            },
            scales: {
                y: { beginAtZero: true, max: 100 }
            }
        }
    });

    const ctx2 = document.getElementById('leaderboardChart').getContext('2d');
    leaderboardChart = new Chart(ctx2, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Views',
                data: [],
                backgroundColor: '#34a853',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { beginAtZero: true }
            }
        }
    });

    const ctx3 = document.getElementById('memoryChart').getContext('2d');
    memoryChart = new Chart(ctx3, {
        type: 'doughnut',
        data: {
            labels: ['Used', 'Available'],
            datasets: [{
                data: [50, 50],
                backgroundColor: ['#1a73e8', '#e8e8e8'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });

    const ctx4 = document.getElementById('hitRatioChart').getContext('2d');
    hitRatioChart = new Chart(ctx4, {
        type: 'doughnut',
        data: {
            labels: ['Hits', 'Misses'],
            datasets: [{
                data: [0, 100],
                backgroundColor: ['#34a853', '#ea4335'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });

    const ctx5 = document.getElementById('benchmarkChart').getContext('2d');
    benchmarkChart = new Chart(ctx5, {
        type: 'bar',
        data: {
            labels: ['Cold Cache', 'Warm Cache'],
            datasets: [{
                label: 'Latency (ms)',
                data: [0, 0],
                backgroundColor: ['#ea4335', '#34a853'],
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

// ===== EVENT LISTENERS =====
function setupEventListeners() {
    document.getElementById('executeBtn').addEventListener('click', executeCommand);
    document.getElementById('commandInput').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') executeCommand();
    });
    document.getElementById('flushCacheBtn').addEventListener('click', flushCache);
    document.getElementById('warmCacheBtn').addEventListener('click', warmCache);
    document.querySelectorAll('.script-run-btn').forEach(button => {
        button.addEventListener('click', () => runAutomationScript(button.dataset.script));
    });
    document.getElementById('cancelScriptBtn').addEventListener('click', cancelActiveScript);
}

// ===== COMMAND EXECUTOR =====
function executeCommand() {
    const input = document.getElementById('commandInput');
    const command = input.value.trim();
    
    if (!command) return;

    const output = document.getElementById('terminalOutput');

    // Add command to output
    const cmdLine = document.createElement('div');
    cmdLine.className = 'command-line';
    cmdLine.textContent = `redis> ${command}`;
    output.appendChild(cmdLine);

    // Send command to server
    fetch('/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            const errLine = document.createElement('div');
            errLine.className = 'error-line';
            errLine.textContent = `Error: ${data.error}`;
            output.appendChild(errLine);
        } else {
            const resultLine = document.createElement('div');
            resultLine.className = 'output-line';
            resultLine.textContent = JSON.stringify(data.result, null, 2);
            output.appendChild(resultLine);
        }
        output.scrollTop = output.scrollHeight;
    })
    .catch(err => {
        const errLine = document.createElement('div');
        errLine.className = 'error-line';
        errLine.textContent = `Error: ${err.message}`;
        output.appendChild(errLine);
    });

    input.value = '';
}

// ===== METRICS POLLING =====
function startMetricsPolling() {
    fetch('/api/metrics')
        .then(res => res.json())
        .then(data => updateMetrics(data))
        .catch(err => console.error('Metrics error:', err));

    setInterval(() => {
        fetch('/api/metrics')
            .then(res => res.json())
            .then(data => {
                updateMetrics(data);
            })
            .catch(err => console.error('Metrics error:', err));
    }, 1000);
}

function startDatasetPolling() {
    const refresh = () => {
        fetch('/api/dataset-status')
            .then(res => res.json())
            .then(data => updateDatasetStatus(data))
            .catch(err => {
                console.error('Dataset status error:', err);
                document.getElementById('datasetStatusBadge').className = 'badge bg-danger';
                document.getElementById('datasetStatusBadge').textContent = 'Unavailable';
                document.getElementById('datasetHint').textContent = 'Cannot fetch dataset status from API.';
            });
    };

    refresh();
    setInterval(refresh, 5000);
}

function updateDatasetStatus(data) {
    const moviesEl = document.getElementById('datasetMovies');
    const ratingsEl = document.getElementById('datasetRatings');
    const tagsEl = document.getElementById('datasetTags');
    const badge = document.getElementById('datasetStatusBadge');
    const hint = document.getElementById('datasetHint');
    const updatedAt = document.getElementById('datasetUpdatedAt');

    if (!moviesEl || !ratingsEl || !tagsEl || !badge || !hint || !updatedAt) {
        return;
    }

    moviesEl.textContent = data.movies || 0;
    ratingsEl.textContent = data.ratings || 0;
    tagsEl.textContent = data.tags || 0;

    if (data.loaded) {
        badge.className = 'badge bg-success';
        badge.textContent = 'Loaded';
        hint.textContent = `MovieLens loaded in ${data.database}. Ready for demos.`;
    } else {
        badge.className = 'badge bg-warning text-dark';
        badge.textContent = 'Not Loaded';
        hint.textContent = 'Run: docker compose exec api python src/ingest.py';
    }

    const now = new Date();
    updatedAt.textContent = `Last update: ${now.toLocaleTimeString()}`;
}

function updateMetrics(data) {
    // Update counters
    state.metrics.hits = data.hits;
    state.metrics.misses = data.misses;
    
    document.getElementById('hitCount').textContent = data.hits;
    document.getElementById('totalCount').textContent = data.hits + data.misses;
    
    const ratio = data.hit_ratio_pct;
    document.getElementById('hitRatioValue').textContent = ratio.toFixed(1) + '%';
    document.getElementById('memoryValue').textContent = data.redis_memory_mb.toFixed(2) + ' MB';
    document.getElementById('peakMemory').textContent = data.redis_peak_memory_mb.toFixed(2);

    const now = Date.now();
    const elapsedSec = Math.max((now - state.lastSample.ts) / 1000, 0.001);
    const delta = Math.max((data.total_requests || 0) - state.lastSample.total, 0);
    const rps = delta / elapsedSec;
    state.metrics.rps = rps;
    document.getElementById('rpsValue').textContent = rps.toFixed(2);
    state.lastSample = { ts: now, total: data.total_requests || 0 };

    // Update charts
    updateLatencyChart(data.avg_latency || 0);
    updateLeaderboardChart(data.top10_movies);
    updateHitRatioChart(data.hits, data.misses);
    
    // Update top movies
    state.metrics.topMovies = data.top10_movies || [];
}

function updateLatencyChart(latency) {
    state.metrics.latencies.push(latency);
    if (state.metrics.latencies.length > 20) {
        state.metrics.latencies.shift();
    }

    const labels = state.metrics.latencies.map((_, i) => i + 1);
    latencyChart.data.labels = labels;
    latencyChart.data.datasets[0].data = state.metrics.latencies;
    latencyChart.update('none');

    document.getElementById('latencyValue').textContent = latency.toFixed(2) + ' ms';
}

function updateLeaderboardChart(movies) {
    if (!movies || movies.length === 0) return;

    movies = movies.slice(0, 10);
    const labels = movies.map(m => 'Movie ' + m.movie_id);
    const data = movies.map(m => m.views);

    leaderboardChart.data.labels = labels;
    leaderboardChart.data.datasets[0].data = data;
    leaderboardChart.update('none');
}

function updateHitRatioChart(hits, misses) {
    hitRatioChart.data.datasets[0].data = [hits, misses];
    hitRatioChart.update('none');
}

// ===== KEYS INSPECTOR =====
function loadKeysInspector() {
    fetch('/api/keys')
        .then(res => res.json())
        .then(data => {
            displayKeys(data.keys);
        })
        .catch(err => console.error('Keys error:', err));
}

function displayKeys(keys) {
    const list = document.getElementById('keysList');
    list.innerHTML = '';

    if (!keys || keys.length === 0) {
        list.innerHTML = '<p class="text-muted text-center">No keys found</p>';
        return;
    }

    keys.forEach(key => {
        const item = document.createElement('div');
        item.className = 'key-item';
        item.innerHTML = `
            <span class="key-type-badge bg-primary" style="color: white;">${key.type}</span>
            <span>${key.name}</span>
            <small class="text-muted d-block" style="margin-left: 4rem;">ttl: ${key.ttl}</small>
        `;
        item.addEventListener('click', () => inspectKey(key.name));
        list.appendChild(item);
    });
}

function inspectKey(keyName) {
    fetch(`/api/key/${encodeURIComponent(keyName)}`)
        .then(res => res.json())
        .then(data => {
            displayKeyDetails(keyName, data);
        })
        .catch(err => console.error('Key inspect error:', err));
}

function displayKeyDetails(keyName, data) {
    const details = document.getElementById('keyDetails');
    
    let html = `<h6>${keyName}</h6>`;
    html += `<small class="text-muted mb-3">Type: ${data.type} | TTL: ${data.ttl}</small><br><br>`;

    if (data.type === 'string') {
        html += `<code>${data.value}</code>`;
    } else if (data.type === 'hash') {
        html += '<table class="detail-table table">';
        html += '<thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>';
        Object.entries(data.value).forEach(([field, value]) => {
            html += `<tr><td>${field}</td><td><code>${value}</code></td></tr>`;
        });
        html += '</tbody></table>';
    } else if (data.type === 'list' || data.type === 'set') {
        html += `<pre>${JSON.stringify(data.value, null, 2)}</pre>`;
    } else if (data.type === 'zset') {
        html += '<table class="detail-table table">';
        html += '<thead><tr><th>Member</th><th>Score</th></tr></thead><tbody>';
        data.value.forEach(item => {
            html += `<tr><td>${item.member}</td><td>${item.score}</td></tr>`;
        });
        html += '</tbody></table>';
    }

    details.innerHTML = html;
}

// ===== CACHE OPERATIONS =====
function flushCache() {
    if (!confirm('Clear all cache? This will measure cold start performance.')) return;

    fetch('/cache', { method: 'DELETE' })
        .then(res => res.json())
        .then(() => measureRequestLatency(1))
        .then(latency => {
            state.benchmark.coldMs = latency;
            updateBenchmarkChart();
            addBenchmarkResult('Cold Cache', `${latency.toFixed(2)} ms`);
        })
        .catch(err => addBenchmarkResult('Cold Cache Error', err.message));
}

function warmCache() {
    addBenchmarkResult('Warming Cache', 'Fetching popular items to warm the cache...');

    const warmups = [];
    for (let i = 1; i <= 10; i++) {
        warmups.push(fetch(`/movies/${i}`));
    }

    Promise.allSettled(warmups)
        .then(() => measureRequestLatency(1))
        .then(latency => {
            state.benchmark.warmMs = latency;
            updateBenchmarkChart();
            addBenchmarkResult('Warm Cache', `${latency.toFixed(2)} ms`);
        })
        .catch(err => addBenchmarkResult('Warm Cache Error', err.message));
}

function updateBenchmarkChart() {
    benchmarkChart.data.datasets[0].data = [
        state.benchmark.coldMs || 0,
        state.benchmark.warmMs || 0
    ];
    benchmarkChart.update();
}

function measureRequestLatency(movieId) {
    const t0 = performance.now();
    return fetch(`/movies/${movieId}`)
        .then(res => {
            if (!res.ok) {
                throw new Error(`Request failed with status ${res.status}`);
            }
            return res.json();
        })
        .then(() => performance.now() - t0);
}

function addBenchmarkResult(label, value) {
    const results = document.getElementById('benchmarkResults');
    const result = document.createElement('div');
    result.className = 'benchmark-result';
    result.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>`;
    results.insertBefore(result, results.firstChild);
}

// ===== AUTOMATION =====
function startAutomationPolling() {
    const refresh = () => {
        fetch('/api/scripts')
            .then(res => res.json())
            .then(data => updateAutomationState(data))
            .catch(err => console.error('Automation error:', err));
    };

    refresh();
    setInterval(refresh, 2000);
}

function updateAutomationState(data) {
    state.automation.busy = Boolean(data.busy);
    state.automation.activeJob = data.active_job || null;
    state.automation.recentJobs = data.recent_jobs || [];
    state.automation.scripts = data.scripts || [];

    renderAutomationCards();
    renderActiveScriptJob();
    renderScriptLogs();
    renderRecentJobs();
    updateVisualizationPreview();
}

function renderAutomationCards() {
    state.automation.scripts.forEach(script => {
        const badge = document.getElementById(`scriptStatus-${script.name}`);
        const meta = document.getElementById(`scriptMeta-${script.name}`);
        const button = document.querySelector(`.script-run-btn[data-script="${script.name}"]`);

        if (!badge || !meta || !button) {
            return;
        }

        const latestJob = script.latest_job;
        const status = script.is_running
            ? 'Running'
            : (latestJob ? latestJob.status : 'Idle');

        badge.className = `badge ${statusBadgeClass(status)}`;
        badge.textContent = statusLabel(status);

        if (latestJob) {
            const timing = latestJob.finished_at
                ? `Finished ${formatRelativeTime(latestJob.finished_at)}`
                : `Started ${formatRelativeTime(latestJob.started_at)}`;
            meta.textContent = `${timing} • ${latestJob.logs.length} log lines`;
        } else if (script.name === 'visualize' && script.artifact_available) {
            meta.textContent = 'Visualization artifact detected and ready to preview.';
        } else {
            meta.textContent = 'Never launched from dashboard.';
        }

        button.disabled = state.automation.busy;
    });
}

function renderActiveScriptJob() {
    const container = document.getElementById('activeScriptJob');
    const cancelBtn = document.getElementById('cancelScriptBtn');
    const job = state.automation.activeJob;

    if (!job) {
        container.innerHTML = '<p class="text-muted text-center mb-0">No automation job running.</p>';
        cancelBtn.disabled = true;
        return;
    }

    cancelBtn.disabled = job.status !== 'running';
    container.innerHTML = `
        <div class="job-summary">
            <div class="job-label">${job.label}</div>
            <div><span class="badge ${statusBadgeClass(job.status)}">${statusLabel(job.status)}</span></div>
            <div class="job-meta">Started: ${formatDateTime(job.started_at)}</div>
            <div class="job-meta">Command: ${job.command.join(' ')}</div>
            ${job.finished_at ? `<div class="job-meta">Finished: ${formatDateTime(job.finished_at)}</div>` : ''}
            ${job.error ? `<div class="text-danger small">${job.error}</div>` : ''}
        </div>
    `;
}

function renderScriptLogs() {
    const output = document.getElementById('scriptLogOutput');
    const activeJob = state.automation.activeJob;
    const sourceJob = activeJob || state.automation.recentJobs[0];

    if (!sourceJob || !sourceJob.logs || sourceJob.logs.length === 0) {
        output.innerHTML = '<div class="output-line">No script output yet.</div>';
        return;
    }

    output.innerHTML = sourceJob.logs
        .map(line => `<div class="output-line">${escapeHtml(line)}</div>`)
        .join('');
    output.scrollTop = output.scrollHeight;
}

function renderRecentJobs() {
    const list = document.getElementById('recentJobsList');
    const jobs = state.automation.recentJobs;

    if (!jobs || jobs.length === 0) {
        list.innerHTML = '<p class="text-muted text-center mb-0">No jobs yet.</p>';
        return;
    }

    list.innerHTML = jobs.map(job => `
        <div class="recent-job-item">
            <div class="d-flex justify-content-between align-items-center gap-2">
                <div class="title">${job.label}</div>
                <span class="badge ${statusBadgeClass(job.status)}">${statusLabel(job.status)}</span>
            </div>
            <div class="meta mt-2">Started: ${formatDateTime(job.started_at)}</div>
            ${job.finished_at ? `<div class="meta">Finished: ${formatDateTime(job.finished_at)}</div>` : ''}
            ${job.returncode !== null && job.returncode !== undefined ? `<div class="meta">Exit code: ${job.returncode}</div>` : ''}
        </div>
    `).join('');
}

function updateVisualizationPreview() {
    const preview = document.getElementById('visualizationPreview');
    const emptyState = document.getElementById('visualizationEmptyState');
    const openBtn = document.getElementById('openVisualizationBtn');
    const visualizationScript = state.automation.scripts.find(script => script.name === 'visualize');
    const artifactUrl = visualizationScript?.latest_job?.artifact_url || state.automation.recentJobs.find(job => job.script === 'visualize' && job.artifact_url)?.artifact_url;

    if (!artifactUrl) {
        preview.classList.add('d-none');
        emptyState.classList.remove('d-none');
        openBtn.classList.add('d-none');
        openBtn.href = '#';
        return;
    }

    preview.src = artifactUrl;
    preview.classList.remove('d-none');
    emptyState.classList.add('d-none');
    openBtn.href = artifactUrl;
    openBtn.classList.remove('d-none');
}

function runAutomationScript(scriptName) {
    fetch(`/api/scripts/${scriptName}/run`, { method: 'POST' })
        .then(async res => {
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || data.detail || 'Unable to start script');
            }
            return data;
        })
        .then(data => {
            state.automation.activeJob = data.job;
            renderActiveScriptJob();
            renderScriptLogs();
        })
        .catch(err => {
            const output = document.getElementById('scriptLogOutput');
            output.innerHTML = `<div class="error-line">${escapeHtml(err.message)}</div>`;
        });
}

function cancelActiveScript() {
    const job = state.automation.activeJob;
    if (!job) {
        return;
    }

    fetch(`/api/scripts/jobs/${job.id}/cancel`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            state.automation.activeJob = data.job;
            renderActiveScriptJob();
            renderScriptLogs();
        })
        .catch(err => console.error('Cancel script error:', err));
}

function statusBadgeClass(status) {
    const normalized = String(status).toLowerCase();
    if (normalized === 'running') return 'bg-primary';
    if (normalized === 'completed') return 'bg-success';
    if (normalized === 'failed') return 'bg-danger';
    if (normalized === 'cancelled') return 'bg-warning text-dark';
    return 'bg-secondary';
}

function statusLabel(status) {
    const normalized = String(status).toLowerCase();
    if (normalized === 'running') return 'Running';
    if (normalized === 'completed') return 'Completed';
    if (normalized === 'failed') return 'Failed';
    if (normalized === 'cancelled') return 'Cancelled';
    return 'Idle';
}

function formatDateTime(value) {
    if (!value) return '—';
    return new Date(value).toLocaleString();
}

function formatRelativeTime(value) {
    if (!value) return 'just now';
    const diffMs = Date.now() - new Date(value).getTime();
    const diffSec = Math.max(Math.floor(diffMs / 1000), 0);
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    return `${Math.floor(diffSec / 3600)}h ago`;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

// ===== UTILITIES =====
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

console.log('Redis Inspector Pro loaded');
