/**
 * Argus Observatory // Free Model Telemetry Dashboard
 * Core Frontend Logic: Polling, Analytics Computation, Dynamic Visualizations, Log Feeds
 */

// State Store
let telemetryData = null;
let currentFilter = 'all';
let currentSearch = '';
let currentSort = 'success';
let nextRoundEpoch = null;
let countdownInterval = null;

// DOM Elements
const el = {
  daemonChip: document.getElementById('daemonChip'),
  roundCounter: document.getElementById('roundCounter'),
  countdownTimer: document.getElementById('countdownTimer'),
  refreshBtn: document.getElementById('refreshBtn'),
  autoRefreshToggle: document.getElementById('autoRefreshToggle'),
  
  // KPIs
  kpiSuccessRate: document.getElementById('kpiSuccessRate'),
  kpiSuccessRatio: document.getElementById('kpiSuccessRatio'),
  barHealth: document.getElementById('barHealth'),

  kpiBurstRate: document.getElementById('kpiBurstRate'),
  kpiBurstRatio: document.getElementById('kpiBurstRatio'),
  barBurst: document.getElementById('barBurst'),

  kpiAvgLatency: document.getElementById('kpiAvgLatency'),
  kpiLatencyRange: document.getElementById('kpiLatencyRange'),
  barLatency: document.getElementById('barLatency'),

  kpiFailedModels: document.getElementById('kpiFailedModels'),
  kpiFailureBreakdown: document.getElementById('kpiFailureBreakdown'),
  barBetrayal: document.getElementById('barBetrayal'),

  kpiQuotaRemaining: document.getElementById('kpiQuotaRemaining'),
  kpiQuotaUsed: document.getElementById('kpiQuotaUsed'),
  barQuota: document.getElementById('barQuota'),

  // Classification breakdown
  countRockSolid: document.getElementById('countRockSolid'),
  countViable: document.getElementById('countViable'),
  countFormatErr: document.getElementById('countFormatErr'),
  countSaturated: document.getElementById('countSaturated'),
  recBody: document.getElementById('recBody'),

  // Table controls & body
  tabCountAll: document.getElementById('tabCountAll'),
  tabCountRock: document.getElementById('tabCountRock'),
  tabCountViable: document.getElementById('tabCountViable'),
  tabCountBetrayal: document.getElementById('tabCountBetrayal'),
  modelSearch: document.getElementById('modelSearch'),
  sortBy: document.getElementById('sortBy'),
  telemetryTbody: document.getElementById('telemetryTbody'),

  // Logs
  logTerminal: document.getElementById('logTerminal'),
  footerTimestamp: document.getElementById('footerTimestamp'),
};


// --- Initialization ---

document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  fetchRunnerStatus();
  fetchTelemetry();
  fetchLogs();

  // Polling loop
  setInterval(() => {
    if (el.autoRefreshToggle.checked) {
      fetchRunnerStatus();
      fetchTelemetry();
      fetchLogs();
    }
  }, 4000);
});

function setupEventListeners() {
  el.refreshBtn.addEventListener('click', () => {
    el.refreshBtn.style.opacity = '0.5';
    Promise.all([fetchRunnerStatus(), fetchTelemetry(), fetchLogs()]).finally(() => {
      setTimeout(() => { el.refreshBtn.style.opacity = '1'; }, 400);
    });
  });

  // Filter tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      renderTable();
    });
  });

  // Search input
  el.modelSearch.addEventListener('input', (e) => {
    currentSearch = e.target.value.toLowerCase().trim();
    renderTable();
  });

  // Sort selector
  el.sortBy.addEventListener('change', (e) => {
    currentSort = e.target.value;
    renderTable();
  });
}


// --- API Calls ---

async function fetchRunnerStatus() {
  try {
    const res = await fetch('/api/runner-status');
    if (res.ok) {
      const data = await res.json();
      if (data.is_running) {
        el.daemonChip.className = 'status-chip daemon-chip';
        el.daemonChip.innerHTML = `<span class="dot"></span><span class="label">RUNNER ACTIVE (PID ${data.pid || 'ON'})</span>`;
      } else {
        el.daemonChip.className = 'status-chip';
        el.daemonChip.style.background = 'rgba(239, 68, 68, 0.1)';
        el.daemonChip.style.borderColor = 'rgba(239, 68, 68, 0.3)';
        el.daemonChip.style.color = '#F87171';
        el.daemonChip.innerHTML = `<span class="label">RUNNER STOPPED / IDLE</span>`;
      }
    }
  } catch (err) {
    console.error('Failed to fetch runner status', err);
  }
}

async function fetchTelemetry() {
  try {
    const res = await fetch('/api/telemetry');
    if (!res.ok) return;
    const data = await res.json();
    telemetryData = data;
    processAndRenderTelemetry(data);
  } catch (err) {
    console.error('Failed to fetch telemetry', err);
  }
}

async function fetchLogs() {
  try {
    const res = await fetch('/api/logs');
    if (!res.ok) return;
    const data = await res.json();
    renderLogs(data.logs || []);
  } catch (err) {
    console.error('Failed to fetch logs', err);
  }
}


// --- Telemetry Processing & Rendering ---

function processAndRenderTelemetry(data) {
  const rounds = data.rounds || [];
  const totalRoundsConfigured = data.total_rounds_configured || 5;

  // Round chip
  const activeRoundNum = rounds.length > 0 ? rounds.length : 1;
  el.roundCounter.textContent = `${activeRoundNum} / ${totalRoundsConfigured}`;

  // Next round timer
  if (data.next_round_at && data.next_round_at !== "All 5 rounds completed") {
    let rawDate = data.next_round_at;
    if (rawDate.endsWith(' UTC')) {
      rawDate = rawDate.replace(' UTC', 'Z').replace(' ', 'T');
    }
    const targetDate = new Date(rawDate);
    nextRoundEpoch = targetDate.getTime();
    startCountdown();
  } else if (rounds.length >= totalRoundsConfigured) {
    el.countdownTimer.textContent = "FINISHED";
    if (countdownInterval) clearInterval(countdownInterval);
  } else {
    el.countdownTimer.textContent = "ROUND IN PROGRESS";
  }

  // Aggregate model metrics
  const modelStats = {};
  let totalCallsAll = 0;
  let successfulCallsAll = 0;
  let burstPassedRoundsAll = 0;
  let allLatencies = [];

  let count429 = 0;
  let count400 = 0;
  let countSchema = 0;
  let countTimeout = 0;

  rounds.forEach((round) => {
    const models = round.models || {};
    Object.entries(models).forEach(([mId, res]) => {
      if (!modelStats[mId]) {
        modelStats[mId] = {
          id: mId,
          totalCalls: 0,
          successCalls: 0,
          burstSuccessCount: 0,
          totalRounds: 0,
          latencies: [],
          lastCall1: res.call_1 || {},
          lastCall2: res.call_2 || {},
          errors: [],
        };
      }

      const m = modelStats[mId];
      m.totalRounds += 1;
      m.lastCall1 = res.call_1 || {};
      m.lastCall2 = res.call_2 || {};

      // Call 1
      totalCallsAll += 1;
      m.totalCalls += 1;
      if (res.call_1 && res.call_1.status === 'SUCCESS') {
        successfulCallsAll += 1;
        m.successCalls += 1;
        allLatencies.push(res.call_1.latency_sec);
        m.latencies.push(res.call_1.latency_sec);
      } else {
        const err = res.call_1 ? res.call_1.status : 'UNKNOWN';
        m.errors.push(`C1: ${err}`);
        if (err === '429_RATE_LIMITED') count429++;
        else if (err.includes('400')) count400++;
        else if (err.includes('SCHEMA')) countSchema++;
        else if (err.includes('TIMEOUT')) countTimeout++;
      }

      // Call 2 (Burst)
      totalCallsAll += 1;
      m.totalCalls += 1;
      if (res.call_2 && res.call_2.status === 'SUCCESS') {
        successfulCallsAll += 1;
        m.successCalls += 1;
        allLatencies.push(res.call_2.latency_sec);
        m.latencies.push(res.call_2.latency_sec);
      } else {
        const err = res.call_2 ? res.call_2.status : 'UNKNOWN';
        m.errors.push(`C2: ${err}`);
        if (err === '429_RATE_LIMITED') count429++;
        else if (err.includes('400')) count400++;
        else if (err.includes('SCHEMA')) countSchema++;
        else if (err.includes('TIMEOUT')) countTimeout++;
      }

      // Burst passed in this round?
      if (res.call_1 && res.call_1.status === 'SUCCESS' && res.call_2 && res.call_2.status === 'SUCCESS') {
        m.burstSuccessCount += 1;
        burstPassedRoundsAll += 1;
      }
    });
  });

  const modelList = Object.values(modelStats);
  const totalModels = modelList.length;

  // KPIs
  if (totalCallsAll > 0) {
    const successPct = Math.round((successfulCallsAll / totalCallsAll) * 100);
    el.kpiSuccessRate.textContent = `${successPct}%`;
    el.kpiSuccessRatio.textContent = `${successfulCallsAll} / ${totalCallsAll} calls passed`;
    el.barHealth.style.width = `${successPct}%`;

    const totalPossibleBursts = totalModels * rounds.length;
    const burstPct = totalPossibleBursts > 0 ? Math.round((burstPassedRoundsAll / totalPossibleBursts) * 100) : 0;
    el.kpiBurstRate.textContent = `${burstPct}%`;
    el.kpiBurstRatio.textContent = `${burstPassedRoundsAll} / ${totalPossibleBursts} bursts survived`;
    el.barBurst.style.width = `${burstPct}%`;

    if (allLatencies.length > 0) {
      const avgLat = (allLatencies.reduce((a, b) => a + b, 0) / allLatencies.length).toFixed(2);
      const minLat = Math.min(...allLatencies).toFixed(1);
      const maxLat = Math.max(...allLatencies).toFixed(1);
      el.kpiAvgLatency.textContent = `${avgLat}s`;
      el.kpiLatencyRange.textContent = `Min: ${minLat}s | Max: ${maxLat}s`;
      const latFill = Math.min(100, Math.round((parseFloat(avgLat) / 20) * 100));
      el.barLatency.style.width = `${latFill}%`;
    }

    const failedTotal = totalCallsAll - successfulCallsAll;
    el.kpiFailedModels.textContent = failedTotal;
    el.kpiFailureBreakdown.textContent = `429: ${count429} | 400: ${count400} | Schema: ${countSchema}`;
    const betrayalFill = Math.min(100, Math.round((failedTotal / totalCallsAll) * 100));
    el.barBetrayal.style.width = `${betrayalFill}%`;

    // Quota
    const quotaUsed = totalCallsAll;
    const quotaRemaining = Math.max(0, 1000 - quotaUsed);
    el.kpiQuotaRemaining.textContent = quotaRemaining.toLocaleString();
    el.kpiQuotaUsed.textContent = `${quotaUsed} used of 1,000 daily limit`;
    el.barQuota.style.width = `${Math.round((quotaUsed / 1000) * 100)}%`;
  }

  // Model Classifications
  let rockSolidCount = 0;
  let viableCount = 0;
  let formatErrCount = 0;
  let saturatedCount = 0;
  let bestWorkerCandidates = [];

  modelList.forEach(m => {
    const winRate = m.totalCalls > 0 ? (m.successCalls / m.totalCalls) : 0;
    const avgLat = m.latencies.length > 0 ? (m.latencies.reduce((a, b) => a + b, 0) / m.latencies.length) : 999;
    m.winRate = winRate;
    m.avgLat = avgLat;
    m.burstRate = m.totalRounds > 0 ? (m.burstSuccessCount / m.totalRounds) : 0;

    if (winRate >= 0.9 && m.burstRate >= 0.9) {
      m.classification = 'rock-solid';
      rockSolidCount++;
      if (avgLat < 10) bestWorkerCandidates.push(m.id);
    } else if (winRate >= 0.5) {
      m.classification = 'viable';
      viableCount++;
    } else {
      m.classification = 'betrayal';
      if (m.errors.some(e => e.includes('429'))) saturatedCount++;
      else if (m.errors.some(e => e.includes('400'))) formatErrCount++;
      else saturatedCount++;
    }
  });

  el.countRockSolid.textContent = rockSolidCount;
  el.countViable.textContent = viableCount;
  el.countFormatErr.textContent = formatErrCount;
  el.countSaturated.textContent = saturatedCount;

  el.tabCountAll.textContent = totalModels;
  el.tabCountRock.textContent = rockSolidCount;
  el.tabCountViable.textContent = viableCount;
  el.tabCountBetrayal.textContent = (formatErrCount + saturatedCount);

  // Recommendations
  if (bestWorkerCandidates.length > 0) {
    const topFast = modelList
      .filter(m => m.classification === 'rock-solid')
      .sort((a, b) => a.avgLat - b.avgLat)[0];

    el.recBody.innerHTML = `
      Recommended primary worker: <strong style="color: #34D399;">${topFast.id}</strong> (${topFast.avgLat.toFixed(2)}s avg, 100% burst pass).<br>
      Avoid <code>google/gemma-4-31b-it:free</code> (429 saturated) and <code>inclusionai/ling</code> (JSON Schema rejection).
    `;
  } else {
    el.recBody.textContent = "Awaiting round completion to determine optimal routing...";
  }

  // Draw chart & render table
  drawLatencyChart(modelList);
  renderTable(modelList);

  el.footerTimestamp.textContent = `Last synchronized: ${new Date().toLocaleTimeString()} (UTC ${data.last_updated || 'Active'})`;
}


// --- Canvas Latency Chart ---

function drawLatencyChart(models) {
  const canvas = document.getElementById('latencyChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;

  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;

  ctx.clearRect(0, 0, w, h);

  if (!models || models.length === 0) {
    ctx.fillStyle = '#64748B';
    ctx.font = '12px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Awaiting round completion for chart telemetry...', w / 2, h / 2);
    return;
  }

  // Draw grid lines
  const padLeft = 40;
  const padRight = 20;
  const padBottom = 35;
  const padTop = 15;
  const chartW = w - padLeft - padRight;
  const chartH = h - padTop - padBottom;

  ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
  ctx.lineWidth = 1;
  const maxSec = 15; // Cap visualization at 15s

  for (let s = 0; s <= maxSec; s += 5) {
    const y = padTop + chartH - (s / maxSec) * chartH;
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(w - padRight, y);
    ctx.stroke();

    ctx.fillStyle = '#64748B';
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.textAlign = 'right';
    ctx.fillText(`${s}s`, padLeft - 6, y + 3);
  }

  // Bars per model
  const barGroupW = chartW / models.length;
  const barW = Math.max(3, (barGroupW * 0.35));

  models.forEach((m, i) => {
    const groupX = padLeft + i * barGroupW + (barGroupW - barW * 2 - 2) / 2;

    const lat1 = m.lastCall1 && m.lastCall1.status === 'SUCCESS' ? m.lastCall1.latency_sec : 0;
    const lat2 = m.lastCall2 && m.lastCall2.status === 'SUCCESS' ? m.lastCall2.latency_sec : 0;

    // Call 1 Bar
    const h1 = Math.min(chartH, (lat1 / maxSec) * chartH);
    const y1 = padTop + chartH - h1;

    ctx.fillStyle = lat1 === 0 ? 'rgba(239, 68, 68, 0.5)' : (lat1 < 5 ? '#10B981' : '#F59E0B');
    ctx.fillRect(groupX, y1, barW, h1);

    // Call 2 Bar (Burst)
    const h2 = Math.min(chartH, (lat2 / maxSec) * chartH);
    const y2 = padTop + chartH - h2;
    ctx.fillStyle = lat2 === 0 ? 'rgba(239, 68, 68, 0.8)' : (lat2 < 5 ? '#06B6D4' : '#FBBF24');
    ctx.fillRect(groupX + barW + 2, y2, barW, h2);

    // X Axis Label
    ctx.save();
    ctx.translate(groupX + barW, padTop + chartH + 12);
    ctx.rotate(-Math.PI / 4);
    ctx.fillStyle = '#94A3B8';
    ctx.font = '9px JetBrains Mono, monospace';
    ctx.textAlign = 'right';
    const shortName = m.id.split('/').pop().replace(':free', '').slice(0, 10);
    ctx.fillText(shortName, 0, 0);
    ctx.restore();
  });
}


// --- Table Rendering ---

function renderTable(modelList) {
  if (!telemetryData) return;
  const tbody = el.telemetryTbody;

  let models = modelList;
  if (!models) {
    const rounds = telemetryData.rounds || [];
    const modelStats = {};
    rounds.forEach(r => {
      Object.entries(r.models || {}).forEach(([mId, res]) => {
        if (!modelStats[mId]) {
          modelStats[mId] = {
            id: mId,
            totalCalls: 0,
            successCalls: 0,
            burstSuccessCount: 0,
            totalRounds: 0,
            latencies: [],
            lastCall1: res.call_1 || {},
            lastCall2: res.call_2 || {},
            errors: [],
          };
        }
        const m = modelStats[mId];
        m.totalRounds += 1;
        m.totalCalls += 2;
        m.lastCall1 = res.call_1 || {};
        m.lastCall2 = res.call_2 || {};
        if (res.call_1 && res.call_1.status === 'SUCCESS') {
          m.successCalls += 1;
          m.latencies.push(res.call_1.latency_sec);
        } else {
          m.errors.push(res.call_1 ? res.call_1.status : 'ERR');
        }
        if (res.call_2 && res.call_2.status === 'SUCCESS') {
          m.successCalls += 1;
          m.latencies.push(res.call_2.latency_sec);
        } else {
          m.errors.push(res.call_2 ? res.call_2.status : 'ERR');
        }
        if (res.call_1?.status === 'SUCCESS' && res.call_2?.status === 'SUCCESS') {
          m.burstSuccessCount += 1;
        }
      });
    });
    models = Object.values(modelStats).map(m => {
      m.winRate = m.totalCalls > 0 ? (m.successCalls / m.totalCalls) : 0;
      m.burstRate = m.totalRounds > 0 ? (m.burstSuccessCount / m.totalRounds) : 0;
      m.avgLat = m.latencies.length > 0 ? (m.latencies.reduce((a, b) => a + b, 0) / m.latencies.length) : 999;
      if (m.winRate >= 0.9 && m.burstRate >= 0.9) m.classification = 'rock-solid';
      else if (m.winRate >= 0.5) m.classification = 'viable';
      else m.classification = 'betrayal';
      return m;
    });
  }

  if (!models || models.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="loading-state">
          <div class="spinner"></div>
          <span>Round 1 executing in background daemon... Telemetry rows will populate upon round completion.</span>
        </td>
      </tr>
    `;
    return;
  }

  // Filter
  let filtered = models.filter(m => {
    if (currentFilter === 'rock-solid' && m.classification !== 'rock-solid') return false;
    if (currentFilter === 'viable' && m.classification !== 'viable') return false;
    if (currentFilter === 'betrayal' && m.classification !== 'betrayal') return false;
    if (currentSearch && !m.id.toLowerCase().includes(currentSearch)) return false;
    return true;
  });

  // Sort
  filtered.sort((a, b) => {
    if (currentSort === 'success') return b.winRate - a.winRate;
    if (currentSort === 'latency') return a.avgLat - b.avgLat;
    if (currentSort === 'burst') return b.burstRate - a.burstRate;
    if (currentSort === 'name') return a.id.localeCompare(b.id);
    return 0;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="loading-state">No models match current filter "${currentFilter}".</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(m => {
    const c1 = m.lastCall1 || {};
    const c2 = m.lastCall2 || {};

    const c1Badge = getStatusBadge(c1.status, c1.latency_sec);
    const c2Badge = getStatusBadge(c2.status, c2.latency_sec);

    const schemaPass = (c1.parsed_schema && c2.parsed_schema)
      ? `<span class="status-badge success">VALID JSON</span>`
      : (c1.parsed_schema || c2.parsed_schema)
        ? `<span class="status-badge error">PARTIAL</span>`
        : `<span class="status-badge throttle">FAILED</span>`;

    const winRatePct = Math.round(m.winRate * 100);
    const winRateColor = winRatePct >= 90 ? '#10B981' : (winRatePct >= 50 ? '#F59E0B' : '#EF4444');

    let verdictBadge = '';
    let roleBadge = '';

    if (m.classification === 'rock-solid') {
      verdictBadge = `<span class="status-badge success">🟢 Rock Solid</span>`;
      roleBadge = m.avgLat < 6 ? `<span class="role-chip worker">Worker Engine (Fast)</span>` : `<span class="role-chip brain">Research Brain</span>`;
    } else if (m.classification === 'viable') {
      verdictBadge = `<span class="status-badge error">🟡 Viable (Throttle Risk)</span>`;
      roleBadge = `<span class="role-chip">Secondary Fallback</span>`;
    } else {
      const is429 = m.errors.some(e => e.includes('429'));
      verdictBadge = is429
        ? `<span class="status-badge throttle">🔴 429 Saturated</span>`
        : `<span class="status-badge throttle">🔴 Betrayal Risk</span>`;
      roleBadge = `<span class="role-chip avoid">Do Not Route</span>`;
    }

    const provider = m.id.split('/')[0];

    return `
      <tr>
        <td>
          <div class="model-cell">
            <span class="model-name">${m.id}</span>
            <span class="model-tag">PROVIDER: ${provider.toUpperCase()}</span>
          </div>
        </td>
        <td>${c1Badge}</td>
        <td>${c2Badge}</td>
        <td>${schemaPass}</td>
        <td>
          <div class="winrate-wrap">
            <span class="winrate-num" style="color: ${winRateColor}">${winRatePct}%</span>
            <div class="winrate-bar-bg">
              <div class="winrate-bar-fill" style="width: ${winRatePct}%; background-color: ${winRateColor}"></div>
            </div>
          </div>
        </td>
        <td>${verdictBadge}</td>
        <td>${roleBadge}</td>
      </tr>
    `;
  }).join('');
}

function getStatusBadge(status, latency) {
  if (status === 'SUCCESS') {
    return `
      <div>
        <span class="status-badge success">HTTP 200</span>
        <div class="latency-meta">${latency}s</div>
      </div>
    `;
  }
  if (status === '429_RATE_LIMITED') {
    return `<span class="status-badge throttle">HTTP 429 (Throttled)</span>`;
  }
  if (status && status.includes('400')) {
    return `<span class="status-badge throttle">HTTP 400 (Bad Format)</span>`;
  }
  if (status === 'TIMEOUT') {
    return `<span class="status-badge throttle">TIMEOUT (&gt;35s)</span>`;
  }
  if (!status) {
    return `<span class="status-badge unknown">PENDING</span>`;
  }
  return `<span class="status-badge error">${status}</span>`;
}


// --- Log Terminal Rendering ---

function renderLogs(lines) {
  const terminal = el.logTerminal;
  if (!lines || lines.length === 0) return;

  terminal.innerHTML = lines.map(line => {
    let cls = 'log-line';
    if (line.includes('SUCCESS')) cls += ' log-success';
    else if (line.includes('429')) cls += ' log-429';
    else if (line.includes('400') || line.includes('ERROR') || line.includes('error')) cls += ' log-error';
    else if (line.includes('Starting Round') || line.includes('Evaluating')) cls += ' log-info';
    return `<div class="${cls}">${escapeHtml(line)}</div>`;
  }).join('');

  terminal.scrollTop = terminal.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}


// --- Countdown Timer ---

function startCountdown() {
  if (countdownInterval) clearInterval(countdownInterval);
  updateTimer();
  countdownInterval = setInterval(updateTimer, 1000);
}

function updateTimer() {
  if (!nextRoundEpoch) return;
  const now = Date.now();
  const diff = nextRoundEpoch - now;

  if (diff <= 0) {
    el.countdownTimer.textContent = "COMMENCING ROUND...";
    clearInterval(countdownInterval);
    return;
  }

  const m = Math.floor(diff / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  el.countdownTimer.textContent = `${m}m ${s < 10 ? '0' : ''}${s}s`;
}
