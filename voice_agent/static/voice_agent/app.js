const page = document.body.dataset.page;
const callId = document.body.dataset.callId;
const $ = (id) => document.getElementById(id);
let serviceReady = false;



function initTrialNotice() {
  const modal = $('trialNotice');
  const backdrop = $('trialNoticeBackdrop');
  const closeButton = $('trialNoticeClose');
  const continueButton = $('trialNoticeContinue');
  if (!modal || !backdrop) return;

  const storageKey = 'vvc_exotel_trial_notice_dismissed_v1';
  const close = () => {
    modal.classList.remove('open');
    backdrop.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    modal.hidden = true;
    document.body.classList.remove('trial-notice-open');
    localStorage.setItem(storageKey, 'true');
  };

  const open = () => {
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    backdrop.classList.add('open');
    modal.classList.add('open');
    document.body.classList.add('trial-notice-open');
    setTimeout(() => closeButton?.focus(), 0);
  };

  closeButton?.addEventListener('click', close);
  continueButton?.addEventListener('click', close);
  backdrop.addEventListener('click', close);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && modal.classList.contains('open')) close();
  });

  // Show once per browser/session until the interviewer dismisses it.
  if (localStorage.getItem(storageKey) !== 'true') open();
}

function registerNavigationWorker() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('/service-worker.js', {scope: '/'})
    .catch(err => console.warn('Navigation cache unavailable:', err));
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

  document.querySelectorAll('[data-nav-link]').forEach(link => {
    link.addEventListener('click', () => {
      closeMobileMenu();
      // Keep navigation a normal full-page navigation. This avoids leaving
      // the mobile drawer/overlay state attached to the next page.
    });
  });

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
  // Prefer the live cookie, then the token rendered into the current page.
  const cookieToken = getCookie('csrftoken');
  if (cookieToken) return cookieToken;
  const domToken = getDomCsrfToken();
  if (domToken) return domToken;

  // Ask Django for a fresh token. The service worker deliberately does not
  // cache /api/ responses, so this always reaches the live server.
  try {
    const response = await fetch('/api/csrf', {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {'Accept': 'application/json'}
    });
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
    if (!csrfToken) {
      throw new Error('Security token could not be initialized. Please refresh the page and try again.');
    }
    headers['X-CSRFToken'] = csrfToken;
  }
  const opts = {...options, method, headers, credentials: 'same-origin'};
  let response;
  try {
    response = await fetch(url, opts);
  } catch {
    throw new Error('Cannot connect to the server. Please refresh and try again.');
  }
  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await response.json() : {};
  if (!response.ok) {
    if (response.status === 403) {
      throw new Error(data.error || 'Request rejected (HTTP 403). Refresh the page to renew the security token.');
    }
    throw new Error(data.error || `Request failed (HTTP ${response.status})`);
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
    const ok = Boolean(h.ready);
    serviceReady = ok;
    if ($('healthText')) $('healthText').textContent = ok ? `Ready for real call · ${h.ai_provider === 'gemini' ? 'Gemini Live' : h.ai_provider}` : (h.public_wss_ready ? (h.ai_configured ? 'Provider configuration needed' : `${h.ai_provider === 'gemini' ? 'Gemini API key' : 'AI provider'} required`) : 'Public WSS required');
    if ($('healthDot')) $('healthDot').style.background = ok ? '#41a46e' : '#d08a3e';
    const callButton = $('callButton');
    if (callButton && !ok) callButton.disabled = true;
    const callHint = $('callSetupHint');
    if (callHint && !ok) callHint.textContent = h.public_wss_message || (!h.ai_configured ? `Configure ${h.ai_provider === 'gemini' ? 'GEMINI_API_KEY' : 'the AI provider key'} before placing a real call.` : 'Provider configuration is required before a real call can be placed.');
  } catch (err) {
    if ($('healthText')) $('healthText').textContent = 'Service check failed';
    if ($('healthDot')) $('healthDot').style.background = '#a33b3b';
    console.error(err);
  }
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
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.content)}</p>
      <div class="kb-actions">
        <button class="text-button" type="button" onclick="editKb(${item.id})">Edit</button>
        <button class="text-button delete" type="button" onclick="deleteKb(${item.id})">Delete</button>
      </div>
    </article>`).join('') || '<div class="card"><p>No information has been added yet.</p></div>';
}

window.editKb = async (id) => {
  const title = prompt('Topic');
  if (title === null) return;
  const content = prompt('Information');
  if (content === null) return;
  try {
    await api(`/api/knowledge/${id}`, {method:'PUT', body:JSON.stringify({title, content, active:true})});
    await loadKnowledge();
  } catch (err) {
    alert(err.message);
  }
};

window.deleteKb = async (id) => {
  if (!confirm('Delete this information?')) return;
  try {
    await api(`/api/knowledge/${id}`, {method:'DELETE'});
    await loadKnowledge();
  } catch (err) {
    alert(err.message);
  }
};

async function initKnowledge() {
  $('kbForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    const result = $('kbResult');
    const button = $('kbForm').querySelector('button[type="submit"]');
    result.textContent = 'Saving...';
    result.className = 'result';
    button.disabled = true;
    try {
      await api('/api/knowledge', {
        method:'POST',
        body:JSON.stringify({title:$('kbTitle').value.trim(), content:$('kbContent').value.trim()})
      });
      $('kbForm').reset();
      result.textContent = 'Information added successfully.';
      await loadKnowledge();
    } catch (err) {
      result.textContent = err.message;
      result.className = 'result error';
    } finally {
      button.disabled = false;
    }
  });
}

async function initCall() {
  $('callForm')?.addEventListener('submit', async e => {
    e.preventDefault();
    const button = $('callButton'), result = $('callResult');
    if (!serviceReady) {
      result.textContent = 'Real call is blocked because the public WSS endpoint is not configured. Set PUBLIC_BASE_URL to your HTTPS tunnel URL and restart the server.';
      result.className = 'result error';
      return;
    }
    button.disabled = true; result.className = 'result'; result.textContent = 'Connecting to Exotel...';
    try {
      const data = await api('/api/call', {method:'POST', body:JSON.stringify({phone_number:$('phoneNumber').value.trim()})});
      result.innerHTML = `Call placed successfully. Exotel SID: <b>${escapeHtml(data.sid || 'pending')}</b>. Open Call history to track it.`;
    } catch (err) {
      result.textContent = err.message; result.className = 'result error';
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
  return clean.length > 110 ? `${clean.slice(0, 107)}...` : clean;
}

async function initHistory() {
  const data = await api('/api/history');
  $('historyList').innerHTML = data.calls.map(c => `
    <tr>
      <td><div class="table-primary">${escapeHtml(new Date(c.created_at).toLocaleDateString())}</div><div class="history-meta">${escapeHtml(new Date(c.created_at).toLocaleTimeString())}</div></td>
      <td><strong>${escapeHtml(c.phone_number)}</strong></td>
      <td><span class="${statusClass(c.status)}">${escapeHtml(c.status.replaceAll('_',' '))}</span></td>
      <td>${fmtDuration(c.duration_seconds)}</td>
      <td>${c.recording_url ? '<span class="table-ok">Ready</span>' : '<span class="history-meta">Pending</span>'}</td>
      <td class="summary-cell">${escapeHtml(shortSummary(c.summary))}</td>
      <td class="history-actions"><a href="/call/${c.id}" data-nav-link>View</a></td>
    </tr>`).join('') || '<tr><td colspan="7" class="empty-table">No calls yet.</td></tr>';
  document.querySelectorAll('[data-nav-link]').forEach(link => link.addEventListener('click', closeMobileMenu));
}

async function initDetail() {
  const render = (c) => {
    const terminal = ['COMPLETED','FAILED','BUSY','NO_ANSWER','CANCELED'].includes(c.status);
    const statusLabel = String(c.status || '').replaceAll('_', ' ');
    $('detail').innerHTML = `
      <div class="card"><h3>Call details</h3>
        <div class="kv"><b>Number</b><span>${escapeHtml(c.phone_number)}</span></div>
        <div class="kv"><b>Exotel SID</b><span>${escapeHtml(c.sid || '—')}</span></div>
        <div class="kv"><b>Status</b><span><span class="${statusClass(c.status)}">${escapeHtml(statusLabel)}</span></span></div>
        <div class="kv"><b>Duration</b><span>${fmtDuration(c.duration_seconds)}</span></div>
      </div>
      <div class="card"><h3>Call outcome</h3><p class="detail-note">${escapeHtml(c.error_message || (c.status === 'COMPLETED' ? 'Call completed normally.' : c.status === 'FAILED' ? 'The call did not complete successfully.' : 'The call is still being processed by the provider.'))}</p></div>
      <div class="card recording"><h3>Call recording</h3>${c.recording_url ? `<audio controls preload="metadata" src="${escapeHtml(c.recording_url)}"></audio>` : `<p class="muted">${terminal ? 'Recording is not available for this call.' : 'Recording will appear automatically when Exotel finishes preparing it.'}</p>`}</div>
      <div class="card detail-full"><h3>Transcript</h3><div class="transcript">${escapeHtml(c.transcript || (terminal ? 'No transcript was captured.' : 'Conversation transcript will appear while the call is active.'))}</div></div>
      <div class="card detail-full"><h3>Call summary</h3><div class="summary-grid">
        <div class="summary-item"><b>What was discussed</b><p>${escapeHtml(c.discussed || 'Not available yet.')}</p></div>
        <div class="summary-item"><b>What the person asked</b><p>${escapeHtml(c.questions || 'Not available yet.')}</p></div>
        <div class="summary-item"><b>Their requirements</b><p>${escapeHtml(c.requirements || 'Not available yet.')}</p></div>
        <div class="summary-item"><b>Important points</b><p>${escapeHtml(c.important_points || 'Not available yet.')}</p></div>
      </div><details class="summary-raw"><summary>View full generated summary</summary><div class="transcript">${escapeHtml(c.summary || (terminal ? 'Summary is not available.' : 'Summary will appear after the call ends.'))}</div></details></div>
      ${c.error_message ? `<div class="card detail-full"><h3>Provider / AI error</h3><div class="transcript">${escapeHtml(c.error_message)}</div></div>` : ''}`;
  };

  const load = async () => {
    const c = await api(`/api/call/${callId}`);
    render(c);
    return c;
  };

  let current = await load();
  // The call detail page is a live status page: keep it synchronized with
  // Exotel callbacks/details and the realtime transcript without requiring a
  // manual refresh. Stop polling after a terminal state.
  for (let i = 0; i < 30 && !['COMPLETED','FAILED','BUSY','NO_ANSWER','CANCELED'].includes(current.status); i += 1) {
    await new Promise(resolve => setTimeout(resolve, 2000));
    try {
      current = await load();
    } catch (err) {
      console.warn('Call detail refresh failed:', err);
    }
  }
}

(async () => {
  registerNavigationWorker();
  initNavigation();
  initTrialNotice();
  await health();

  try {
    if (page === 'knowledge') {
      await loadKnowledge();
      await initKnowledge();
    } else if (page === 'dashboard') {
      await loadKnowledge();
    } else if (page === 'call') {
      await initCall();
    } else if (page === 'history') {
      await initHistory();
    } else if (page === 'detail') {
      await initDetail();
    }
  } catch (err) {
    console.error(err);
    showPageError(err.message || 'This page could not load. Please refresh and try again.');
  }
})();
