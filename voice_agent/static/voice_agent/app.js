const page = document.body.dataset.page;
const callId = document.body.dataset.callId;
const $ = (id) => document.getElementById(id);
let serviceReady = false;
let healthState = null;

function updateBrowserConnectivityNotice() {
  const content = document.querySelector('.content');
  if (!content) return;
  let banner = document.getElementById('browserConnectivityNotice');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'browserConnectivityNotice';
    banner.className = 'browser-connectivity-notice';
    banner.setAttribute('role', 'status');
    content.prepend(banner);
  }
  if (navigator.onLine === false) {
    banner.hidden = false;
    banner.textContent = 'Offline mode: the cached Vardha interface is available, but live Exotel/Gemini/API data is unavailable until the connection returns.';
  } else {
    banner.hidden = true;
  }
}

window.addEventListener('online', updateBrowserConnectivityNotice);
window.addEventListener('offline', updateBrowserConnectivityNotice);

function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 220);
  }, 2600);
}

function initTrialNotice() {
  const modal = $('trialNotice');
  const closeButton = $('trialNoticeClose');
  const continueButton = $('trialNoticeContinue');
  if (!modal) return;
  const storageKey = 'vvc_exotel_trial_notice_dismissed_v2';
  const close = () => {
    modal.classList.remove('open');
    modal.hidden = true;
    document.body.classList.remove('trial-notice-open');
    localStorage.setItem(storageKey, 'true');
  };
  const open = () => {
    modal.hidden = false;
    modal.classList.add('open');
    document.body.classList.add('trial-notice-open');
    setTimeout(() => closeButton?.focus(), 0);
  };
  closeButton?.addEventListener('click', close);
  continueButton?.addEventListener('click', close);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && modal.classList.contains('open')) close();
  });
  if (localStorage.getItem(storageKey) !== 'true') open();
}

async function registerNavigationWorker() {
  if (!('serviceWorker' in navigator)) return;
  try {
    const version = document.body.dataset.appVersion || 'dev';
    const registration = await navigator.serviceWorker.register(`/service-worker.js?v=${encodeURIComponent(version)}`, {
      scope: '/',
      updateViaCache: 'none',
    });
    await registration.update().catch(() => {});
    if (registration.waiting) {
      registration.waiting.postMessage({type: 'SKIP_WAITING'});
    }
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      // A new worker takes control without forcing a reload loop.
    }, {once: true});
  } catch (err) {
    console.warn('Service worker update skipped:', err);
  }
}

function openMobileMenu() {
  document.body.classList.add('mobile-nav-open');
  $('mobileMenuOpen')?.setAttribute('aria-expanded', 'true');
}
function closeMobileMenu() {
  document.body.classList.remove('mobile-nav-open');
  $('mobileMenuOpen')?.setAttribute('aria-expanded', 'false');
}
function initNavigation() {
  $('mobileMenuOpen')?.addEventListener('click', openMobileMenu);
  $('mobileMenuClose')?.addEventListener('click', closeMobileMenu);
  $('mobileNavBackdrop')?.addEventListener('click', closeMobileMenu);
  document.querySelectorAll('[data-nav-link]').forEach(link => link.addEventListener('click', closeMobileMenu));
  window.addEventListener('pageshow', closeMobileMenu);
  window.addEventListener('resize', () => {
    if (window.innerWidth > 820) closeMobileMenu();
  });
}

function getCookie(name) {
  const prefix = `${name}=`;
  return document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(prefix))?.slice(prefix.length) || '';
}

function getDomCsrfToken() {
  const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
  if (input?.value) return input.value;
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta?.getAttribute('content') || '';
}

async function ensureCsrfToken() {
  const cookieToken = getCookie('csrftoken');
  if (cookieToken) return cookieToken;
  const domToken = getDomCsrfToken();
  if (domToken) return domToken;
  try {
    const response = await fetch('/api/csrf', {method: 'GET', credentials: 'same-origin', cache: 'no-store', headers: {'Accept': 'application/json'}});
    if (response.ok) {
      const data = await response.json();
      return data.csrfToken || getCookie('csrftoken') || '';
    }
  } catch (err) {
    console.warn('CSRF bootstrap failed:', err);
  }
  return '';
}

async function api(url, options = {}) {
  const method = String(options.method || 'GET').toUpperCase();
  const headers = {'Content-Type': 'application/json', ...(options.headers || {})};
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    const csrfToken = await ensureCsrfToken();
    if (!csrfToken) throw new Error('Security token could not be initialized. Please refresh the page and try again.');
    headers['X-CSRFToken'] = csrfToken;
  }
  let response;
  try {
    response = await fetch(url, {...options, method, headers, credentials: 'same-origin'});
  } catch (error) {
    if (navigator.onLine === false) {
      throw new Error('Browser is offline. The local interface is available, but live server data is unavailable until the connection returns.');
    }
    throw new Error('Cannot connect to the local server. Please check that Vardha Voice Connect is running on http://127.0.0.1:8000.');
  }
  const contentType = response.headers.get('content-type') || '';
  let data = {};
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch (err) {
      throw new Error(`Server returned invalid JSON (HTTP ${response.status}). Please refresh the page.`);
    }
  }
  if (!response.ok) {
    throw new Error(data.error || data.detail || `Request failed (HTTP ${response.status})`);
  }
  return data;
}

function showPageError(message) {
  const content = document.querySelector('.content');
  if (!content || content.querySelector('.page-error')) return;
  const box = document.createElement('div');
  box.className = 'page-error';
  box.textContent = message;
  content.prepend(box);
}

async function health() {
  try {
    const h = await api('/api/health');
    healthState = h;
    serviceReady = Boolean(h.ready);
    const message = h.ready ? `Ready · ${h.ai_provider === 'gemini' ? 'Gemini Live' : h.ai_provider}` : (h.public_wss_ready ? (h.ai_configured ? 'Provider configuration needed' : 'AI provider key required') : 'Public WSS required');
    if ($('healthText')) $('healthText').textContent = message;
    if ($('healthDot')) $('healthDot').style.background = h.ready ? '#41a46e' : '#d08a3e';
    const callButton = $('callButton');
    if (callButton) callButton.disabled = !h.ready;
    const callHint = $('callSetupHint');
    if (callHint && !h.ready) callHint.textContent = h.public_wss_message || (!h.ai_configured ? 'Configure the AI provider key before placing a real call.' : 'Provider configuration is required before a real call can be placed.');
    updateCallReadiness(h);
    updateDashboardReadiness(h);
  } catch (err) {
    if ($('healthText')) $('healthText').textContent = 'Service check failed';
    if ($('healthDot')) $('healthDot').style.background = '#a33b3b';
    if ($('callButton')) $('callButton').disabled = true;
    console.error(err);
  }
}

function updateCallReadiness(h) {
  const node = $('callReadiness');
  if (!node) return;
  const dot = node.querySelector('.dot');
  const text = node.querySelector('span:last-child');
  if (dot) dot.style.background = h.ready ? '#41a46e' : '#d08a3e';
  if (text) text.textContent = h.ready ? 'Ready for a real call' : (h.public_wss_message || 'Provider configuration needs attention');
}

function updateDashboardReadiness(h) {
  const node = $('dashboardReadiness');
  if (!node) return;
  const summary = node.querySelector('.status-summary strong');
  const dot = node.querySelector('.status-summary .dot');
  if (summary) summary.textContent = h.ready ? 'Ready for calling' : 'Setup needs attention';
  if (dot) dot.style.background = h.ready ? '#41a46e' : '#d08a3e';
  const items = node.querySelector('.status-items');
  if (items) items.innerHTML = [
    `Exotel ${h.exotel_configured ? 'ready' : 'needs config'}`,
    `Gemini ${h.gemini_live_ready ? 'ready' : 'needs config'}`,
    `Knowledge Base ${h.knowledge_base_ready ? 'ready' : 'empty'}`
  ].map(label => `<span>${escapeHtml(label)}</span>`).join('');
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

async function loadKnowledge() {
  const data = await api('/api/knowledge');
  if ($('kbCount')) $('kbCount').textContent = data.items.filter(x => x.active).length;
  if (!$('kbList')) return;
  $('kbList').innerHTML = data.items.map(item => `
    <article class="card kb-card">
      <div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.content)}</p></div>
      <div class="kb-meta"><span>${item.active ? 'Active' : 'Inactive'}</span><span>Updated ${escapeHtml(new Date(item.updated_at).toLocaleString())}</span></div>
      <div class="kb-actions">
        <button class="text-button" type="button" onclick="editKb(${item.id})">Edit</button>
        <button class="text-button delete" type="button" onclick="deleteKb(${item.id})">Delete</button>
      </div>
    </article>`).join('') || '<div class="card empty-state">No business information has been added yet.</div>';
}

window.editKb = async (id) => {
  const title = prompt('Topic');
  if (title === null) return;
  const content = prompt('Information');
  if (content === null) return;
  try {
    await api(`/api/knowledge/${id}`, {method:'PUT', body:JSON.stringify({title, content, active:true})});
    await loadKnowledge();
    showToast('Knowledge item updated.');
  } catch (err) {
    showToast(err.message, 'error');
  }
};

window.deleteKb = async (id) => {
  if (!confirm('Delete this knowledge item?')) return;
  try {
    await api(`/api/knowledge/${id}`, {method:'DELETE'});
    await loadKnowledge();
    showToast('Knowledge item deleted.');
  } catch (err) {
    showToast(err.message, 'error');
  }
};

async function initKnowledge() {
  $('kbForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    const result = $('kbResult');
    const button = $('kbForm').querySelector('button[type="submit"]');
    result.textContent = 'Saving…';
    result.className = 'result';
    button.disabled = true;
    try {
      await api('/api/knowledge', {method:'POST', body:JSON.stringify({title:$('kbTitle').value.trim(), content:$('kbContent').value.trim()})});
      $('kbForm').reset();
      result.textContent = 'Information added successfully.';
      await loadKnowledge();
      showToast('Knowledge item added.');
    } catch (err) {
      result.textContent = err.message;
      result.className = 'result error';
    } finally {
      button.disabled = false;
    }
  });
}

function selectedVoice() {
  return document.querySelector('input[name="voice"]:checked')?.value || 'primary';
}

function initVoiceOptions() {
  document.querySelectorAll('.voice-option input').forEach(input => {
    input.addEventListener('change', () => {
      document.querySelectorAll('.voice-option').forEach(node => node.classList.toggle('active', node.querySelector('input')?.checked));
    });
  });
}

async function initCall() {
  initVoiceOptions();
  $('callForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    const button = $('callButton'), result = $('callResult');
    if (!serviceReady) {
      result.textContent = healthState?.public_wss_message || 'Real call is blocked until provider readiness is available.';
      result.className = 'result error';
      return;
    }
    button.disabled = true;
    result.className = 'result';
    result.textContent = 'Connecting to Exotel…';
    try {
      const voice = selectedVoice();
      const data = await api('/api/call', {method:'POST', body:JSON.stringify({phone_number:$('phoneNumber').value.trim(), voice})});
      result.innerHTML = `Call placed successfully. Voice: <b>${escapeHtml(voice === 'female' ? 'Female Voice' : 'Main Voice')}</b>. Exotel SID: <b>${escapeHtml(data.sid || 'pending')}</b>.`;
      showToast('Outbound call request accepted.');
    } catch (err) {
      result.textContent = err.message;
      result.className = 'result error';
      showToast(err.message, 'error');
    } finally {
      button.disabled = false;
    }
  });
}

function fmtDuration(sec) {
  if (sec == null) return '—';
  const total = Math.max(0, Number(sec) || 0);
  const m = Math.floor(total/60), s = total%60;
  return `${m}m ${String(s).padStart(2,'0')}s`;
}

function statusClass(status) {
  return `status status-${String(status || '').toLowerCase()}`;
}

function shortSummary(text) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim();
  if (!clean) return 'Not available';
  return clean.length > 110 ? `${clean.slice(0, 107)}…` : clean;
}

function renderHistoryRows(calls) {
  const list = $('historyList');
  if (!list) return;
  list.innerHTML = calls.map(c => {
    const date = new Date(c.created_at);
    return `<tr data-call-row="${c.id}">
      <td><div class="table-primary">${escapeHtml(date.toLocaleDateString())}</div><div class="history-meta">${escapeHtml(date.toLocaleTimeString())}</div></td>
      <td><strong>${escapeHtml(c.phone_number)}</strong></td>
      <td><span class="${statusClass(c.status)}">${escapeHtml(String(c.status || '').replaceAll('_',' '))}</span></td>
      <td>${fmtDuration(c.duration_seconds)}</td>
      <td>${c.recording_url ? '<span class="table-ok">Ready</span>' : '<span class="history-meta">Pending</span>'}</td>
      <td class="summary-cell">${escapeHtml(shortSummary(c.summary))}</td>
      <td class="history-actions"><div class="action-group"><a class="view-action" href="/call/${c.id}" data-nav-link>View</a><button class="delete-action" type="button" onclick="deleteCall(${c.id}, '${escapeHtml(c.phone_number).replace(/'/g, "\\'")}', '${escapeHtml(date.toLocaleString()).replace(/'/g, "\\'")}')">Delete</button></div></td>
    </tr>`;
  }).join('') || '<tr><td colspan="7" class="empty-table">No calls yet. Place your first outbound call from Make a call.</td></tr>';
}

async function initHistory() {
  const load = async () => {
    const data = await api('/api/history');
    renderHistoryRows(data.calls);
    if ($('historyCount')) $('historyCount').textContent = `${data.calls.length} recent record${data.calls.length === 1 ? '' : 's'}`;
  };
  await load();
  $('historyRefresh')?.addEventListener('click', async () => {
    const button = $('historyRefresh');
    button.disabled = true;
    try { await load(); showToast('Call history refreshed.'); } catch (err) { showToast(err.message, 'error'); } finally { button.disabled = false; }
  });
}

window.deleteCall = async (id, phone, createdAt) => {
  const confirmed = confirm(`Delete call record?\n\nNumber: ${phone}\nDate: ${createdAt}\n\nThis deletes only the local application history record.`);
  if (!confirmed) return;
  try {
    await api(`/api/call/${id}`, {method:'DELETE'});
    document.querySelector(`[data-call-row="${id}"]`)?.remove();
    const remaining = document.querySelectorAll('#historyList tr[data-call-row]').length;
    if (!remaining && $('historyList')) $('historyList').innerHTML = '<tr><td colspan="7" class="empty-table">No calls yet. Place your first outbound call from Make a call.</td></tr>';
    if ($('historyCount')) $('historyCount').textContent = `${remaining} recent record${remaining === 1 ? '' : 's'}`;
    showToast('Call history record deleted.');
  } catch (err) {
    showToast(`Delete failed: ${err.message}`, 'error');
  }
};

async function initDashboard() {
  const data = await api('/api/dashboard');
  if ($('statTotal')) $('statTotal').textContent = data.total_calls;
  if ($('statCompleted')) $('statCompleted').textContent = data.completed_calls;
  if ($('statFailed')) $('statFailed').textContent = data.failed_calls;
  if ($('statActive')) $('statActive').textContent = data.active_calls;
  if ($('kbCount')) $('kbCount').textContent = data.knowledge_base_items;
  if ($('dashboardRecent')) {
    $('dashboardRecent').innerHTML = data.recent_calls.map(call => `
      <a class="recent-item" href="/call/${call.id}">
        <div><strong>${escapeHtml(call.phone_number)}</strong><span>${escapeHtml(new Date(call.created_at).toLocaleString())}</span></div>
        <span class="${statusClass(call.status)}">${escapeHtml(String(call.status).replaceAll('_',' '))}</span>
      </a>`).join('') || '<div class="empty-state">No calls have been created yet.</div>';
  }
}

async function initDetail() {
  const render = (c) => {
    const terminal = ['COMPLETED','FAILED','BUSY','NO_ANSWER','CANCELED'].includes(c.status);
    const statusLabel = String(c.status || '').replaceAll('_', ' ');
    $('detail').innerHTML = `
      <div class="card"><div class="card-kicker">OVERVIEW</div><h3>Call details</h3>
        <div class="kv"><b>Number</b><span>${escapeHtml(c.phone_number)}</span></div>
        <div class="kv"><b>Exotel SID</b><span>${escapeHtml(c.sid || '—')}</span></div>
        <div class="kv"><b>Status</b><span><span class="${statusClass(c.status)}">${escapeHtml(statusLabel)}</span></span></div>
        <div class="kv"><b>Duration</b><span>${fmtDuration(c.duration_seconds)}</span></div>
      </div>
      <div class="card"><div class="card-kicker">OUTCOME</div><h3>Call outcome</h3><p class="detail-note">${escapeHtml(c.error_message || (c.status === 'COMPLETED' ? 'Call completed normally.' : c.status === 'FAILED' ? 'The call did not complete successfully.' : 'The call is still being processed by the provider.'))}</p></div>
      <div class="card recording"><div class="card-kicker">RECORDING</div><h3>Call recording</h3>${c.recording_url ? `<audio controls preload="metadata" src="${escapeHtml(c.recording_url)}"></audio>` : `<p class="muted">${terminal ? 'Recording is not available for this call.' : 'Recording will appear when Exotel finishes preparing it.'}</p>`}</div>
      <div class="card detail-full"><div class="card-kicker">TRANSCRIPT</div><h3>Conversation transcript</h3><div class="transcript">${escapeHtml(c.transcript || (terminal ? 'No transcript was captured.' : 'Conversation transcript will appear while the call is active.'))}</div></div>
      <div class="card detail-full"><div class="card-kicker">SUMMARY</div><h3>Call summary</h3><div class="summary-grid">
        <div class="summary-item"><b>What was discussed</b><p>${escapeHtml(c.discussed || 'Not stated')}</p></div>
        <div class="summary-item"><b>What the person asked</b><p>${escapeHtml(c.questions || 'Not stated')}</p></div>
        <div class="summary-item"><b>Their requirements</b><p>${escapeHtml(c.requirements || 'Not stated')}</p></div>
        <div class="summary-item"><b>Important points</b><p>${escapeHtml(c.important_points || 'Not stated')}</p></div>
      </div><details class="summary-raw"><summary>View full generated summary</summary><div class="transcript">${escapeHtml(c.summary || (terminal ? 'Summary is not available.' : 'Summary will appear after the call ends.'))}</div></details></div>
      ${c.error_message ? `<div class="card detail-full"><div class="card-kicker">TECHNICAL CONTEXT</div><h3>Provider / AI error</h3><div class="transcript">${escapeHtml(c.error_message)}</div></div>` : ''}`;
  };
  const load = async () => { const c = await api(`/api/call/${callId}`); render(c); return c; };
  let current = await load();
  for (let i = 0; i < 30 && !['COMPLETED','FAILED','BUSY','NO_ANSWER','CANCELED'].includes(current.status); i += 1) {
    await new Promise(resolve => setTimeout(resolve, 2000));
    try { current = await load(); } catch (err) { console.warn('Call detail refresh failed:', err); }
  }
}

(async () => {
  await registerNavigationWorker();
  initNavigation();
  initTrialNotice();
  await health();
  try {
    if (page === 'knowledge') { await loadKnowledge(); await initKnowledge(); }
    else if (page === 'dashboard') { await initDashboard(); }
    else if (page === 'call') { await initCall(); }
    else if (page === 'history') { await initHistory(); }
    else if (page === 'detail') { await initDetail(); }
  } catch (err) {
    console.error(err);
    showPageError(err.message || 'This page could not load. Please refresh and try again.');
  }
})();

updateBrowserConnectivityNotice();
