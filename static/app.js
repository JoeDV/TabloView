/**
 * TabloView — single-page client.
 * Hash-routed pages (Home, Library, Show, Guide, Series, Live TV, Scheduled, Downloads, Device),
 * delegated event handling via data-action / data-input / data-change attributes.
 */
'use strict';

// ---------------------------------------------------------------------------
// Icons (Lucide-style strokes)
// ---------------------------------------------------------------------------
const ICONS = {
  home: '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
  library: '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
  guide: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  live: '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
  calendar: '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  settings: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  next: '<path d="m9 18 6-6-6-6"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  dual: '<rect x="2" y="5" width="9" height="14" rx="2"/><rect x="13" y="5" width="9" height="14" rx="2"/>',
  layout: '<rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/>',
  cc: '<rect x="2" y="5" width="20" height="14" rx="3"/><path d="M10 10.2a2.5 2.5 0 1 0 0 3.6M17 10.2a2.5 2.5 0 1 0 0 3.6"/>',
  up: '<path d="m18 15-6-6-6 6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  trash: '<path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  play: '<path d="M6 3.8v16.4a1 1 0 0 0 1.5.86l13.2-8.2a1 1 0 0 0 0-1.72L7.5 2.94A1 1 0 0 0 6 3.8z" fill="currentColor" stroke="none"/>',
  more: '<circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="19" cy="12" r="1.6" fill="currentColor"/><circle cx="5" cy="12" r="1.6" fill="currentColor"/>',
  external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  queue: '<path d="M3 6h13M3 12h9M3 18h9"/><path d="M16 12.5v6.8a.5.5 0 0 0 .77.42l5-3.4a.5.5 0 0 0 0-.84l-5-3.4a.5.5 0 0 0-.77.42z" fill="currentColor" stroke="none"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  tv: '<rect width="20" height="15" x="2" y="7" rx="2"/><path d="m17 2-5 5-5-5"/>',
  antenna: '<path d="M12 12 6 2M12 12l6-10"/><circle cx="12" cy="13" r="1.6"/><path d="M12 15v6M8 21h8"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  pause: '<rect x="6" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/><rect x="14" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/>',
  rewind: '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><text x="12" y="15.5" text-anchor="middle" font-size="7.5" font-weight="700" fill="currentColor" stroke="none">10</text>',
  forward: '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/><text x="12" y="15.5" text-anchor="middle" font-size="7.5" font-weight="700" fill="currentColor" stroke="none">30</text>',
  volume: '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a10 10 0 0 1 0 14"/>',
  mute: '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="m22 9-6 6M16 9l6 6"/>',
  pip: '<rect x="2" y="4" width="20" height="16" rx="2"/><rect x="12" y="11" width="8" height="7" rx="1" fill="currentColor" stroke="none"/>',
  fullscreen: '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>',
  keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
  star: '<path d="M11.5 2.3a.6.6 0 0 1 1 0l2.8 5.7 6.3.9a.6.6 0 0 1 .3 1l-4.5 4.4 1 6.2a.6.6 0 0 1-.8.6L12 18.2l-5.6 2.9a.6.6 0 0 1-.8-.6l1-6.2L2.1 9.9a.6.6 0 0 1 .3-1l6.3-.9z" fill="currentColor"/>',
};

function icon(name, size = 18) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
}

function hydrateIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach(el => {
    if (el.dataset.hydrated) return;
    el.innerHTML = icon(el.dataset.icon, Number(el.dataset.size) || 18);
    el.style.display = 'inline-flex';
    el.dataset.hydrated = '1';
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const view = () => document.getElementById('view');

function esc(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function plural(n, word, pluralWord) {
  return `${n} ${n === 1 ? word : (pluralWord || word + 's')}`;
}

// The server rejects state-changing requests without X-TabloView (blocks other websites)
const API_HEADERS = { 'Content-Type': 'application/json', 'X-TabloView': '1' };

async function api(url, options = {}) {
  const res = await fetch(url, { headers: API_HEADERS, ...options });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && (data.code === 'pin_required' || data.code === 'pin_not_set')) askForPin(data.code);
    throw Object.assign(new Error(data.detail || `${res.status} ${res.statusText}`), { status: res.status });
  }
  return res.json();
}

// Other devices on the network sign in with the PIN set on the PC (once; remembered for 90 days)
let pinScreen = null;
function askForPin(code) {
  if (pinScreen) return;
  pinScreen = document.createElement('div');
  pinScreen.className = 'pin-screen';
  pinScreen.innerHTML = code === 'pin_not_set'
    ? `<div class="pin-box"><div class="brand-mark" data-icon="tv"></div><h2>TabloView</h2>
        <p>To use TabloView on this device, first set a PIN on the PC running TabloView: <b>Device → Network access</b>.</p>
        <button class="btn btn-primary" onclick="location.reload()">Try again</button></div>`
    : `<form class="pin-box" id="pinForm"><div class="brand-mark" data-icon="tv"></div><h2>TabloView</h2>
        <p>Enter the PIN to use TabloView on this device.</p>
        <input class="input pin-input" id="pinInput" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="6" autocomplete="current-password" autofocus>
        <div class="pin-error" id="pinError"></div>
        <button class="btn btn-primary" type="submit">Sign in</button></form>`;
  document.body.appendChild(pinScreen);
  hydrateIcons(pinScreen);
  const form = $('#pinForm');
  if (!form) return;
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const err = $('#pinError');
    err.textContent = '';
    const res = await fetch('/api/lan/login', { method: 'POST', headers: API_HEADERS, body: JSON.stringify({ pin: $('#pinInput').value }) });
    if (res.ok) { location.reload(); return; }
    const data = await res.json().catch(() => ({}));
    err.textContent = (data.detail && typeof data.detail === 'string') ? data.detail : 'The PIN must be 4 to 6 digits.';
    $('#pinInput').select();
  });
  setTimeout(() => $('#pinInput') && $('#pinInput').focus(), 50);
}

const debounce = (fn, ms) => {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
};

const fmt = {
  date(iso) { return iso ? new Date(iso) : null; },
  dayLabel(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return '';
    const now = new Date();
    const tmrw = new Date(now); tmrw.setDate(now.getDate() + 1);
    const yest = new Date(now); yest.setDate(now.getDate() - 1);
    if (d.toDateString() === now.toDateString()) return 'Today';
    if (d.toDateString() === tmrw.toDateString()) return 'Tomorrow';
    if (d.toDateString() === yest.toDateString()) return 'Yesterday';
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  },
  day(iso) {
    const d = new Date(iso);
    if (!iso || isNaN(d)) return '';
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  },
  time(iso) {
    const d = new Date(iso);
    if (!iso || isNaN(d)) return '';
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  },
  when(iso) {
    if (!iso) return '';
    const label = fmt.dayLabel(iso);
    return `${label}${label === 'Today' || label === 'Tomorrow' ? ' ' : ' · '}${fmt.time(iso)}`;
  },
  dur(sec) {
    const m = Math.round((sec || 0) / 60);
    if (m <= 0) return '';
    if (m < 60) return `${m}m`;
    return m % 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${Math.floor(m / 60)}h`;
  },
  se(s, e) {
    const sn = Number(s) > 0 ? `S${s}` : '';
    const en = Number(e) > 0 ? `E${e}` : '';
    return [sn, en].filter(Boolean).join(' ');
  },
  ago(iso) {
    if (!iso) return 'never';
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    return `${Math.round(s / 86400)}d ago`;
  },
  size(gb) {
    if (gb === undefined || gb === null) return '';
    return gb >= 1000 ? `${(gb / 1024).toFixed(1)} TB` : `${Math.round(gb * 10) / 10} GB`;
  },
  bytes(n) {
    if (!n) return '';
    return n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(2)} GB` : `${Math.round(n / 1024 ** 2)} MB`;
  },
};

function imgUrl(url) {
  if (!url || url.includes('placeholder')) return null;
  return url.includes('?') ? `${url}&v=2` : `${url}?v=2`;
}

// Image with a text fallback if the Tablo has no artwork
function artImg(url, title) {
  const src = imgUrl(url);
  if (!src) return `<div class="art-fallback">${esc(title)}</div>`;
  return `<img src="${esc(src)}" alt="${esc(title)}" loading="lazy" onerror="this.outerHTML='<div class=&quot;art-fallback&quot;>'+this.alt.replace(/</g,'&lt;')+'</div>'">`;
}

function episodeTitle(ep) {
  const n = ep.episode_number || ep.number || 0;
  let t = (ep.title || '').trim();
  if (!t || t === 'Episode') t = n > 0 ? `Episode ${n}` : (ep.air_date ? `Episode (${fmt.day(ep.air_date)})` : 'Episode');
  return t;
}

const RULE_LABEL = { new: 'Recording new', all: 'Recording all', none: 'Record' };

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const store = (k, fallback) => { try { return localStorage.getItem(k) ?? fallback; } catch { return fallback; } };
const save = (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } };

// Device → Appearance → Open TabloView on (per browser)
const START_PAGES = [['home', 'Home'], ['library', 'Library'], ['guide', 'Guide'], ['live', 'Live TV'], ['scheduled', 'Scheduled']];

const state = {
  status: null,
  shows: null,
  guideCache: new Map(),
  library: { q: '', sort: store('tv_lib_sort', 'recent'), filter: 'all', layout: store('tv_lib_layout', 'wide') },
  guide: { q: '', highlight: '', category: 'all', sport: '', rule: '', sort: 'primetime', items: [], offset: 0, hasMore: false, highlights: {} },
  // The Guide's Streaming tab
  fast: { q: '', category: 'all', recordable: false, data: null },
  scheduled: { items: null, filter: 'all', q: '' },
  show: null,
  episodes: [],
  selected: new Set(),
  series: null,
  epg: null,
  epgCategory: 'ota',
  epgOffset: 0,
  epgQuery: '',
  epgItems: {},
  isSyncing: false,
  activeExports: 0,
  bufferTarget: parseInt(store('tablo_buffer_target', '8'), 10) || 8,
  captions: store('tablo_cc', '0') === '1',
  autoplay: store('tablo_autoplay', '1') !== '0',
  stream: { sessionId: null, hls: null, handler: null, timer: null, episodeId: null, channelId: null },
};

let routeToken = 0;
let pageTimers = [];
let pageLeave = [];  // run when the page is left

// ---------------------------------------------------------------------------
// Toasts, menus, dialogs
// ---------------------------------------------------------------------------
function toast(message, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  $('#toasts').appendChild(el);
  setTimeout(() => { el.classList.add('leaving'); setTimeout(() => el.remove(), 260); }, 4200);
}

let openMenuEl = null;
function closeMenu() { if (openMenuEl) { openMenuEl.remove(); openMenuEl = null; } }

function openMenu(anchor, items) {
  closeMenu();
  const menu = document.createElement('div');
  menu.className = 'menu';
  menu.innerHTML = items.map((it, i) => {
    if (it.sep) return '<div class="menu-sep"></div>';
    if (it.heading) return `<div class="menu-label">${esc(it.heading)}</div>`;
    return `<button class="menu-item ${it.danger ? 'danger' : ''}" data-menu-index="${i}">
      ${it.icon ? icon(it.icon, 16) : ''}<span>${esc(it.label)}</span>${it.checked ? `<span class="check">${icon('check', 16)}</span>` : ''}
    </button>`;
  }).join('');
  menu.addEventListener('click', e => {
    const btn = e.target.closest('[data-menu-index]');
    if (!btn) return;
    const item = items[Number(btn.dataset.menuIndex)];
    closeMenu();
    item.run && item.run();
  });
  (document.fullscreenElement || document.body).appendChild(menu);
  const r = anchor.getBoundingClientRect();
  const mw = menu.offsetWidth, mh = menu.offsetHeight;
  let left = r.right - mw;
  if (left < 8) left = r.left;
  let top = r.bottom + 6;
  if (top + mh > window.innerHeight - 8) top = r.top - mh - 6;
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${Math.max(8, top)}px`;
  openMenuEl = menu;
}

let openOverlay = null;
function closeModal(result) {
  if (!openOverlay) return;
  const { el, resolve } = openOverlay;
  openOverlay = null;
  el.remove();
  resolve && resolve(result);
}

function openModal(html, { onReady, wide = false } = {}) {
  closeModal(false);
  return new Promise(resolve => {
    const el = document.createElement('div');
    el.className = 'overlay';
    el.innerHTML = `<div class="dialog ${wide ? 'wide' : ''}" role="dialog" aria-modal="true">${html}</div>`;
    el.addEventListener('mousedown', e => { if (e.target === el) closeModal(false); });
    (document.fullscreenElement || document.body).appendChild(el);
    hydrateIcons(el);
    openOverlay = { el, resolve };
    onReady && onReady(el);
    const primary = el.querySelector('[data-autofocus]');
    primary && primary.focus();
  });
}

function confirmDialog({ title, text, confirm = 'Confirm', danger = false }) {
  return openModal(`
    <div class="dialog-body">
      <div class="dialog-title">${esc(title)}</div>
      ${text ? `<div class="dialog-text">${esc(text)}</div>` : ''}
    </div>
    <div class="dialog-foot">
      <button class="btn" data-action="modal-cancel">Cancel</button>
      <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-action="modal-ok" data-autofocus>${esc(confirm)}</button>
    </div>`);
}

// ---------------------------------------------------------------------------
// Status, storage, sync polling
// ---------------------------------------------------------------------------
async function loadStatus() {
  try {
    state.status = await api('/api/auth/status');
    showAuthProblem(state.status.auth_problem);
    const dev = state.status.active_device;
    $('#deviceName').textContent = dev ? dev.name : 'Not connected';
    setSyncState(state.status.is_syncing, state.status.last_sync);
  } catch {
    $('#deviceName').textContent = 'Server unreachable';
  }
}

async function loadStorage() {
  try {
    const s = await api('/api/storage');
    state.storage = s;
    if (s.connected) {
      $('#storageUsed').textContent = `${fmt.size(s.used_gb)} used`;
      $('#storageFree').textContent = `${fmt.size(s.free_gb)} free`;
      $('#storageFill').style.width = `${Math.min(s.percent_used, 100)}%`;
    } else {
      $('#storageUsed').textContent = 'Storage unavailable';
      $('#storageFree').textContent = '';
    }
  } catch { /* shown as unavailable */ }
}

function setSyncState(syncing, lastSync) {
  state.isSyncing = syncing;
  if (lastSync !== undefined) state.lastSync = lastSync;
  const dot = $('#syncDot'), text = $('#syncText');
  dot.className = `sync-dot ${syncing ? 'busy' : (state.lastSync ? '' : 'off')}`;
  text.textContent = syncing ? 'Syncing recordings…' : (state.lastSync ? `Synced ${fmt.ago(state.lastSync)}` : 'Not synced yet');
  const btn = $('#topRefreshBtn');
  if (btn) {
    btn.disabled = syncing;
    const svg = btn.querySelector('svg');
    svg && svg.classList.toggle('spin', syncing);
  }
}

async function pollStatus() {
  try {
    const s = await api('/api/library/status');
    showAuthProblem(s.auth_problem);
    state.guidePartial = s.guide_incomplete;
    showGuideProgress(s.guide_progress);
    showGuidePartial(s.guide_progress ? null : s.guide_incomplete);
    showCommercialProgress(s.commercials);
    // While a guide load waits out the Tablo's break, its banner already says so
    const waiting = s.guide_progress && s.guide_progress.waiting_seconds !== null;
    $('#reachBanner').classList.toggle('hidden', !s.tablo_unreachable || !!s.auth_problem || !!waiting);
    const wasSyncing = state.isSyncing;
    const prevSync = state.lastSync;
    setSyncState(s.is_syncing, s.last_sync);
    // A sync finished: either we saw it running, or last_sync moved on between polls
    // (automatic syncs are quick and can start and end between two polls)
    const finished = !s.is_syncing && ((wasSyncing) || (prevSync && s.last_sync && s.last_sync !== prevSync));
    if (finished) {
      if (state.manualSync) {
        if (s.last_error) toast(`Sync failed: ${s.last_error}`, 'error');
        else toast('Recordings synced from your Tablo', 'success');
        state.manualSync = false;
      }
      state.shows = null;
      state.scheduled.items = null;
      loadStorage();
      refreshCurrentPageQuietly();
      if (!state.shows) loadShows().catch(() => {});  // keep the sidebar's Library count current on any page
    }
  } catch { /* transient */ }

  if (state.activeExports > 0) {
    try {
      const { jobs } = await api('/api/exports');
      const active = jobs.filter(j => j.status === 'downloading' || j.status === 'pending').length;
      if (active < state.activeExports) {
        const done = jobs.find(j => j.status === 'completed');
        toast(done ? `Export finished: ${done.filename}` : 'An export finished', 'success');
      }
      setActiveExports(active);
    } catch { /* transient */ }
  }
}

// Re-render list pages after new data arrives, unless the user is busy (menu, dialog, player,
// episodes selected); keeps the scroll position
function refreshCurrentPageQuietly() {
  const name = parseRoute().name;
  const busy = openMenuEl || openOverlay || player.isOpen() || state.selected.size || document.activeElement.matches('input, select');
  if (busy || !['home', 'library', 'scheduled', 'show'].includes(name)) return;
  const scroll = view().scrollTop;
  Promise.resolve(route()).then(() => { view().scrollTop = scroll; });
}

// A long guide load (the first on this PC takes several minutes): say what's happening and how far along
// it is, and refresh the pages built from the guide as it fills in
function showGuideProgress(p) {
  const banner = $('#guideBanner');
  const was = state.guideProgress;
  state.guideProgress = p;
  banner.classList.toggle('hidden', !p);
  if (!p) {
    if (was) {
      if (!state.guidePartial) toast('The TV guide has finished loading', 'success');
      refreshGuidePages();
    }
    return;
  }
  $('#guideBannerTitle').textContent = p.first ? 'Loading the TV guide from your Tablo for the first time…' : 'Updating the TV guide from your Tablo…';
  let detail;
  if (p.waiting_seconds !== null) {
    detail = `Your Tablo needs a short break after this many requests. Continuing in about ${Math.max(1, Math.ceil(p.waiting_seconds / 60))} minute${p.waiting_seconds > 60 ? 's' : ''}.`;
  } else if (p.step === 'airings' && p.total) {
    detail = `${p.done.toLocaleString()} of ${p.total.toLocaleString()} upcoming airings` +
      (p.minutes_left ? `, about ${p.minutes_left} minute${p.minutes_left === 1 ? '' : 's'} left.` : '.');
  } else {
    detail = 'Getting the list of shows.';
  }
  if (p.first) detail += ' First time only. Recordings and Live TV work now; the Guide, Scheduled and Recording soon fill in as it loads.';
  $('#guideBannerText').textContent = detail;
  // Show what's loaded so far every few hundred airings
  if (p.step === 'airings' && (!was || p.done - (state.guideRefreshedAt || 0) >= 500)) {
    state.guideRefreshedAt = p.done;
    refreshGuidePages();
  }
}

// The last guide load stopped short (the Tablo stopped answering): some recordings and airings are
// missing until it's tried again, which happens by itself after a few minutes
function showGuidePartial(g) {
  const banner = $('#guidePartialBanner');
  banner.classList.toggle('hidden', !g);
  if (!g) return;
  const missing = g.missing ? `${g.missing.toLocaleString()} of ${g.total.toLocaleString()} upcoming airings are missing, so Scheduled and the Guide may have gaps. ` : 'Scheduled and the Guide may have gaps. ';
  const when = g.retry_at ? fmt.time(new Date(g.retry_at * 1000).toISOString()) : '';
  $('#guidePartialText').textContent = `${missing}Your Tablo stopped answering partway through. TabloView will try again${when ? ` at ${when}` : ' soon'}.`;
}

// Commercial finding: a line in the sidebar, and live progress on the episode being analyzed
function showCommercialProgress(c) {
  const line = $('#adLine');
  const was = state.adProgress;
  state.adProgress = c;
  line.classList.toggle('hidden', !c);
  if (c) {
    const left = c.minutes_left ? ` · about ${c.minutes_left} min left` : '';
    const more = c.waiting ? ` (${c.waiting} more waiting)` : '';
    $('#adText').innerHTML = c.state === 'running'
      ? `<b>Finding commercials${c.percent != null ? ` · ${c.percent}%` : ''}</b><span>${esc(c.title || '')}${left}${more}</span>`
      : c.state === 'paused'
        ? `<b>Finding commercials paused</b><span>while something plays · ${plural(c.waiting, 'recording')} waiting</span>`
        : `<b>Finding commercials</b><span>${plural(c.waiting, 'recording')} waiting</span>`;
    $('#adSpin').classList.toggle('hidden', c.state !== 'running');
  }
  for (const el of $$('[data-ad-ep]')) {
    const mine = c && c.state === 'running' && c.episode_id === el.dataset.adEp;
    el.textContent = mine ? `Finding commercials${c.percent != null ? ` · ${c.percent}%` : ''}`
      : c && c.state === 'paused' ? 'Paused while playing' : 'Waiting';
  }
  // One finished: show its result on the show page
  if (was && was.state === 'running' && (!c || c.episode_id !== was.episode_id)) refreshCurrentPageQuietly();
}

function refreshGuidePages() {
  const name = parseRoute().name;
  const busy = openMenuEl || openOverlay || player.isOpen() || document.activeElement.matches('input, select');
  if (!busy && ['home', 'guide', 'scheduled'].includes(name)) {
    const scroll = view().scrollTop;
    Promise.resolve(route()).then(() => { view().scrollTop = scroll; });
  }
}

function showAuthProblem(message) {
  const banner = $('#authBanner');
  if (!banner) return;
  banner.classList.toggle('hidden', !message);
  if (message) $('#authBannerText').textContent = message;
}

async function checkForUpdate(force = false) {
  try {
    const u = await api(`/api/system/update${force ? '?force=true' : ''}`);
    state.update = u;
    const notice = $('#updateNotice');
    notice.classList.toggle('hidden', !u.update_available);
    if (u.update_available) {
      $('#updateNoticeText').textContent = `Update available: ${u.latest}`;
      notice.href = u.download_url || '#';
      notice.title = u.store ? 'Get it from the Microsoft Store' : u.notes ? `What's new: ${u.notes}` : 'Download the new version';
      notice.target = u.store ? '_self' : '_blank';
    }
    return u;
  } catch {
    return null;
  }
}

function setActiveExports(n) {
  state.activeExports = n;
  $('#navDownloadsCount').textContent = n > 0 ? `${n} active` : '';
}

async function refreshLibrary() {
  if (state.isSyncing) return;
  try {
    await api('/api/library/refresh', { method: 'POST' });
    state.manualSync = true;
    setSyncState(true);
    toast('Syncing recordings from your Tablo…');
  } catch (err) {
    toast(`Sync failed: ${err.message}`, 'error');
  }
}

// ---------------------------------------------------------------------------
// Data loaders
// ---------------------------------------------------------------------------
async function loadShows(force = false) {
  if (state.shows && !force) return state.shows;
  const res = await api('/api/shows?sort=recent');
  state.shows = res.shows || [];
  $('#navLibraryCount').textContent = state.shows.length || '';
  return state.shows;
}

function cacheGuide(list) {
  (list || []).forEach(g => {
    const prev = state.guideCache.get(g.path);
    state.guideCache.set(g.path, prev ? { ...prev, ...g } : g);
  });
  return list || [];
}

async function loadScheduled(force = false) {
  if (state.scheduled.items && !force) return state.scheduled.items;
  const res = await api('/api/guide/shows?rule=scheduled&sort=soonest&limit=500');
  state.scheduled.items = cacheGuide(res.shows);
  $('#navScheduledCount').textContent = state.scheduled.items.length || '';
  return state.scheduled.items;
}

// ---------------------------------------------------------------------------
// Shared components
// ---------------------------------------------------------------------------
function showCard(s) {
  const unwatched = s.unwatched_count || 0;
  return `
    <div class="media-card" data-action="open-show" data-id="${esc(s.id)}" title="${esc(s.title)}">
      <div class="media-art">
        ${artImg(s.cover_url || s.backdrop_url, s.title)}
        ${unwatched ? `<span class="art-badge new">${unwatched} unwatched</span>` : `<span class="art-badge">${s.episode_count}</span>`}
        ${s.incomplete_count ? `<span class="art-badge art-badge-left warn" title="${plural(s.incomplete_count, 'recording')} didn’t record completely">${icon('alert', 12)}${s.incomplete_count}</span>` : ''}
      </div>
      <div class="media-meta">
        <div class="media-title">${esc(s.title)}</div>
        <div class="media-sub">${plural(s.episode_count, 'episode')} · ${esc(fmt.dayLabel(s.latest_recording_date))}</div>
      </div>
    </div>`;
}

function continueCard(ep) {
  const pct = ep.duration ? Math.min(100, Math.round((ep.position / ep.duration) * 100)) : 0;
  const left = fmt.dur((ep.duration || 0) - (ep.position || 0));
  const se = fmt.se(ep.season_number, ep.episode_number);
  return `
    <div class="media-card" data-action="play-ep" data-id="${esc(ep.id)}" data-mode="resume" title="Resume ${esc(ep.show_title)}">
      <div class="media-art">
        ${artImg(ep.snapshot_url || ep.backdrop_url || ep.cover_url, ep.show_title)}
        <div class="art-play"><span>${icon('play', 20)}</span></div>
        <div class="art-progress"><div style="width:${pct}%"></div></div>
      </div>
      <div class="media-meta">
        <div class="media-title">${esc(ep.show_title)}</div>
        <div class="media-sub">${se ? `${se} · ` : ''}${esc(episodeTitle(ep))}${left ? ` · <span class="hl">${left} left</span>` : ''}</div>
      </div>
    </div>`;
}

function recButton(g) {
  const rule = g.schedule_rule || 'none';
  const on = rule === 'new' || rule === 'all';
  return `<button class="rec-btn ${on ? 'on' : 'off'}" data-action="rec-menu" data-path="${esc(g.path)}" data-rule-path="${esc(g.path)}" title="Series recording">
    <span class="rec-dot"></span>${RULE_LABEL[rule] || 'Record'}</button>`;
}

function nextAiringText(g) {
  const n = g.next_airing;
  if (!n || !n.datetime) return '';
  const se = fmt.se(n.season_number, n.episode_number);
  return `<span class="hl">${esc(fmt.when(n.datetime))}</span>${n.network || n.call_sign ? ` · ${esc(n.network || n.call_sign)}` : ''}${se ? ` · ${se}` : ''}`;
}

function guideCard(g) {
  const genres = Array.isArray(g.genres) ? g.genres.slice(0, 2).join(', ') : '';
  let badge = '';
  if (g.has_premiere) badge = '<span class="art-badge art-badge-left" style="background:var(--warn);color:#1d1400">Premiere</span>';
  else if (g.has_primetime_new) badge = '<span class="art-badge art-badge-left">New episodes</span>';
  return `
    <div class="media-card" data-action="open-series" data-path="${esc(g.path)}" title="${esc(g.title)}">
      <div class="media-art">${artImg(g.cover_url || g.backdrop_url, g.title)}${badge}</div>
      <div class="media-meta">
        <div class="media-title">${esc(g.title)}</div>
        <div class="media-sub">${nextAiringText(g) || (['new', 'all'].includes(g.schedule_rule) ? 'Waiting for new episodes' : esc(genres)) || '&nbsp;'}</div>
        <div class="media-foot">${recButton(g)}</div>
      </div>
    </div>`;
}

function section({ title, sub = '', link = '', rowId = '', body }) {
  return `
    <section class="section">
      <div class="section-head">
        <h2 class="section-title">${esc(title)}</h2>
        ${sub ? `<span class="section-sub">${sub}</span>` : ''}
        ${link ? `<a class="section-link" href="${link}">See all ${icon('next', 14)}</a>` : ''}
        ${rowId ? `<div class="row-scroll-btns" ${link ? '' : 'style="margin-left:auto"'}>
          <button class="icon-btn" data-action="row-scroll" data-target="${rowId}" data-dir="-1" title="Scroll left">${icon('back')}</button>
          <button class="icon-btn" data-action="row-scroll" data-target="${rowId}" data-dir="1" title="Scroll right">${icon('next')}</button>
        </div>` : ''}
      </div>
      ${body}
    </section>`;
}

function skeletonGrid(n = 10) {
  return `<div class="card-grid">${Array.from({ length: n }, () => '<div><div class="skeleton" style="aspect-ratio:16/9"></div><div class="skeleton" style="height:14px;width:70%;margin-top:12px"></div></div>').join('')}</div>`;
}

function emptyState(title, text, actionHtml = '') {
  return `<div class="empty"><h3>${esc(title)}</h3><p>${esc(text)}</p>${actionHtml}</div>`;
}

function errorState(err, retryAction = 'retry-route') {
  return `<div class="empty"><h3>Couldn't load this page</h3><p>${esc(err.message || err)}</p><button class="btn" data-action="${retryAction}">Try again</button></div>`;
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------
function parseRoute() {
  const h = location.hash.replace(/^#/, '') || '/';
  const [path, qs] = h.split('?');
  const parts = path.split('/').filter(Boolean);
  return {
    name: parts[0] || 'home',
    arg: parts.length > 1 ? decodeURIComponent(parts.slice(1).join('/')) : null,
    query: new URLSearchParams(qs || ''),
  };
}

const PAGES = {};
const NAV_FOR = { show: 'library', series: 'guide' };

function route() {
  const r = parseRoute();
  // Not signed in: everything except the sign-in screen redirects there
  const signedOut = !!(state.status && !state.status.authenticated);
  document.body.classList.toggle('signed-out', signedOut || r.name === 'welcome');
  if (signedOut && r.name !== 'welcome') { location.replace('#/welcome'); return; }
  if (!signedOut && r.name === 'welcome' && !state.pickingDevice) { location.replace('#/'); return; }

  const token = ++routeToken;
  pageTimers.forEach(t => clearInterval(t));
  pageTimers = [];
  pageLeave.splice(0).forEach(f => f());  // e.g. the antenna helper frees its tuner
  closeMenu();
  hideSearch();
  clearSelection();

  const navName = NAV_FOR[r.name] || r.name;
  $$('.nav-item').forEach(a => a.classList.toggle('active', a.dataset.nav === navName));
  $('#backBtn').classList.toggle('visible', r.name === 'show' || r.name === 'series');

  const render = PAGES[r.name] || PAGES.home;
  view().scrollTop = 0;
  return render(r, token).catch(err => {
    if (token !== routeToken) return;
    console.error(err);
    view().innerHTML = `<div class="page">${errorState(err)}</div>`;
    hydrateIcons(view());
  });
}

function stale(token) { return token !== routeToken; }

function paint(html) {
  view().innerHTML = html;
  hydrateIcons(view());
}

// ---------------------------------------------------------------------------
// Welcome / sign-in (first run, or after signing out)
// ---------------------------------------------------------------------------
PAGES.welcome = async () => {
  const devices = (state.status && state.status.devices) || [];
  const picking = state.pickingDevice && devices.length > 1;
  paint(`<div class="welcome">
    <div class="welcome-card">
      <div class="brand-mark welcome-mark">${icon('tv', 26)}</div>
      ${picking ? `
        <h1 class="welcome-title">Choose your Tablo</h1>
        <p class="welcome-text">Your account has more than one Tablo. Which one should TabloView use?</p>
        <div class="device-pick">
          ${devices.map(d => `<button class="device-option" data-action="pick-device" data-sid="${esc(d.sid)}">
            ${icon('tv', 20)}<span><b>${esc(d.name)}</b><span class="dim">${esc(d.local_url || '')}</span></span>${icon('next', 16)}
          </button>`).join('')}
        </div>` : `
        <h1 class="welcome-title">Welcome to TabloView</h1>
        <p class="welcome-text">Sign in with your Tablo account to find the Tablo DVR on your home network.</p>
        <form class="form-col welcome-form" data-form="login">
          <input class="input" name="email" type="email" placeholder="Tablo account email" required autocomplete="username" autofocus>
          <input class="input" name="password" type="password" placeholder="Password" required autocomplete="current-password">
          <button class="btn btn-primary btn-lg" type="submit">Sign in</button>
        </form>
        <p class="welcome-fine">Your password is sent only to Tablo's sign-in service and is never saved. TabloView keeps just the device access it gets back, on this computer.</p>`}
    </div>
  </div>`);
};

function friendlyLoginError(msg) {
  // The server already passes through Tablo's own message (e.g. wrong password); translate the rest
  if (/no tablo devices/i.test(msg)) return 'No Tablo was found on this account.';
  if (/timed? ?out|connection|resolve|unreachable|getaddrinfo/i.test(msg)) return "Couldn't reach Tablo's sign-in service. Check your internet connection.";
  return msg;
}

async function pickDevice(sid) {
  try {
    await api(`/api/auth/select/${encodeURIComponent(sid)}`, { method: 'POST' });
    state.pickingDevice = false;
    state.shows = null;
    await loadStatus();
    setSyncState(true);
    location.hash = '#/';
  } catch (err) {
    toast(`Couldn't select that Tablo: ${err.message}`, 'error');
  }
}

// ---------------------------------------------------------------------------
// Home
// ---------------------------------------------------------------------------
PAGES.home = async (r, token) => {
  paint(`<div class="page"><div class="page-head"><div><h1 class="page-title">Home</h1><div class="page-sub">&nbsp;</div></div></div>${skeletonGrid(5)}</div>`);

  const [shows, sched, prem, prime, progress, upcomingRes, , back] = await Promise.allSettled([
    loadShows(),
    loadScheduled(),
    api('/api/guide/shows?highlight=premieres&sort=soonest&limit=24').then(r => cacheGuide(r.shows)),
    api('/api/guide/shows?highlight=primetime_new&sort=soonest&limit=30').then(r => cacheGuide(r.shows)),
    api('/api/episodes/in_progress').then(r => r.episodes || []),
    loadUpcoming(),
    player.ensureEpg(),
    api('/api/guide/returning').then(r => cacheGuide(r.shows)),
  ]);
  if (stale(token)) return;
  state.inProgress = progress.value || [];
  const homeConflicts = (upcomingRes.value && upcomingRes.value.conflicts) || [];

  const showList = shows.value || [];
  const schedList = sched.value || [];
  const totalEps = showList.reduce((n, s) => n + (s.episode_count || 0), 0);
  const unwatched = showList.reduce((n, s) => n + (s.unwatched_count || 0), 0);

  const parts = [];

  if (homeConflicts.length) parts.push(`<section class="section">${conflictBanner(homeConflicts, { compact: true })}</section>`);
  const missed = missedNew(upcomingRes.value);
  if (missed.length) parts.push(`<section class="section">${missedNewBanner(missed, { compact: true })}</section>`);

  if (state.inProgress.length) {
    parts.push(section({
      title: 'Continue watching',
      rowId: state.inProgress.length > 5 ? 'rowContinue' : '',
      body: `<div class="card-row" id="rowContinue">${state.inProgress.map(continueCard).join('')}</div>`,
    }));
  }

  const onNow = onNowCards();
  if (onNow) {
    parts.push(section({
      title: 'On now',
      sub: hasFavorites() ? 'Your favorite channels' : 'Antenna channels',
      link: '#/live',
      rowId: 'rowOnNow',
      body: `<div class="card-row onnow-row" id="rowOnNow">${onNow}</div>`,
    }));
  }

  if (shows.status === 'rejected') {
    parts.push(section({ title: 'Recordings', body: errorState(shows.reason) }));
  } else if (showList.length) {
    parts.push(section({
      title: 'Recently recorded',
      sub: unwatched ? `${unwatched} unwatched` : '',
      link: '#/library',
      rowId: 'rowRecent',
      body: `<div class="card-row" id="rowRecent">${showList.slice(0, 20).map(showCard).join('')}</div>`,
    }));
  } else if (state.isSyncing) {
    parts.push(section({ title: 'Recordings', body: `<div class="list"><div class="loading-line"><span class="spinner"></span>Syncing your recordings from your Tablo. The first sync takes a minute or two; this page updates when it's done.</div></div>` }));
  } else {
    parts.push(section({ title: 'Recordings', body: emptyState('No recordings yet', 'Schedule a series from the guide and it will show up here.', '<a class="btn btn-primary" href="#/guide">Browse the guide</a>') }));
  }

  // Recordings the Tablo will actually make in the next 48 hours (not just each series' next airing,
  // which may be a rerun it won't record)
  const horizon = Date.now() + 48 * 3600 * 1000;
  const upcoming = (upcomingRes.value && upcomingRes.value.recordings) || [];
  const upNext = upcoming.filter(a => new Date(a.air_datetime).getTime() < horizon).slice(0, 8);
  if (upNext.length) {
    parts.push(section({
      title: 'Recording soon',
      sub: 'Next 48 hours',
      link: '#/scheduled?view=upcoming',
      body: `<div class="list">${upNext.map(a => {
        const se = fmt.se(a.season_number, a.episode_number);
        const onNow = new Date(a.air_datetime).getTime() <= Date.now() && !a.wont_record && !a.missed_new;
        const art = imgUrl(a.cover_url || a.backdrop_url);
        return `
          <div class="list-row upnext-row clickable ${a.conflict ? 'conflict' : ''}" ${rowOpen(a)}>
            <div class="upnext-when">${onNow ? '<span class="tag tag-rec-live"><span class="rec-pulse"></span>REC</span>' : esc(fmt.time(a.air_datetime))}<span class="dim">${esc(fmt.dayLabel(a.air_datetime))}</span></div>
            ${art ? `<img class="thumb" src="${esc(art)}" alt="" loading="lazy">` : '<div class="thumb"></div>'}
            <div style="min-width:0">
              <div class="row-title">${esc(a.show_title)}</div>
              <div class="row-sub">${se ? `${se} · ` : ''}${esc(a.episode_title || '')}</div>
            </div>
            <div class="row-sub upnext-ch ch-cell">${channelCell(a)}</div>
            ${conflictTag(a) || (a.is_new ? '<span class="tag tag-new">NEW</span>' : '<span></span>')}
          </div>`;
      }).join('')}</div>`,
    }));
  }

  // Series you recorded before, back with a new season and not set to record
  const backList = back.value || [];
  if (backList.length) {
    parts.push(section({
      title: 'Back for a new season',
      sub: 'Shows you’ve recorded before',
      rowId: 'rowBack',
      body: `<div class="card-row" id="rowBack">${backList.map(guideCard).join('')}</div>`,
    }));
  }
  const backPaths = new Set(backList.map(g => g.path));

  const premList = (prem.value || []).filter(g => !backPaths.has(g.path));
  if (premList.length) {
    parts.push(section({
      title: 'Season premieres',
      sub: 'Upcoming on your antenna channels',
      link: '#/guide?highlight=premieres',
      rowId: 'rowPrem',
      body: `<div class="card-row" id="rowPrem">${premList.map(guideCard).join('')}</div>`,
    }));
  }

  const premPaths = new Set(premList.map(g => g.path));
  const primeList = (prime.value || []).filter(g => !premPaths.has(g.path));
  if (primeList.length) {
    parts.push(section({
      title: 'New in primetime',
      sub: 'Fresh episodes this week',
      link: '#/guide?highlight=primetime_new',
      rowId: 'rowPrime',
      body: `<div class="card-row" id="rowPrime">${primeList.map(guideCard).join('')}</div>`,
    }));
  }

  const subBits = [plural(showList.length, 'show'), plural(totalEps, 'recording')];
  if (schedList.length) subBits.push(`${schedList.length} series scheduled`);
  if (state.storage && state.storage.connected) subBits.push(`${fmt.size(state.storage.free_gb)} free`);

  paint(`<div class="page">
    <div class="page-head"><div><h1 class="page-title">Home</h1><div class="page-sub">${esc(subBits.join(' · '))}</div></div></div>
    ${parts.join('')}
  </div>`);
};

// ---------------------------------------------------------------------------
// Library
// ---------------------------------------------------------------------------
PAGES.library = async (r, token) => {
  const L = state.library;
  paint(`<div class="page">
    <div class="page-head">
      <div><h1 class="page-title">Library</h1><div class="page-sub" id="libSub">&nbsp;</div></div>
    </div>
    <div class="toolbar">
      <div class="input-search">${icon('search', 15)}<input class="input" data-input="library-q" placeholder="Filter recordings" value="${esc(L.q)}"></div>
      <div class="segmented">
        <button data-action="library-filter" data-value="all" class="${L.filter === 'all' ? 'active' : ''}">All</button>
        <button data-action="library-filter" data-value="unwatched" class="${L.filter === 'unwatched' ? 'active' : ''}">Unwatched</button>
      </div>
      <div class="grow"></div>
      <select class="select" data-change="library-sort">
        <option value="recent" ${L.sort === 'recent' ? 'selected' : ''}>Recently recorded</option>
        <option value="title" ${L.sort === 'title' ? 'selected' : ''}>Title A–Z</option>
        <option value="episodes" ${L.sort === 'episodes' ? 'selected' : ''}>Most episodes</option>
        <option value="unwatched" ${L.sort === 'unwatched' ? 'selected' : ''}>Most unwatched</option>
      </select>
      <div class="segmented" title="Card style">
        <button data-action="library-layout" data-value="wide" class="${L.layout === 'wide' ? 'active' : ''}">Wide</button>
        <button data-action="library-layout" data-value="posters" class="${L.layout === 'posters' ? 'active' : ''}">Posters</button>
      </div>
    </div>
    <div id="libGrid">${skeletonGrid(8)}</div>
  </div>`);

  await loadShows();
  if (stale(token)) return;
  renderLibraryGrid();
};

function renderLibraryGrid() {
  const L = state.library;
  const grid = $('#libGrid');
  if (!grid || !state.shows) return;
  let items = state.shows.slice();
  const q = L.q.trim().toLowerCase();
  if (q) items = items.filter(s => s.title.toLowerCase().includes(q));
  if (L.filter === 'unwatched') items = items.filter(s => s.unwatched_count > 0);
  const by = {
    recent: (a, b) => (b.latest_recording_date || '').localeCompare(a.latest_recording_date || ''),
    title: (a, b) => a.title.localeCompare(b.title),
    episodes: (a, b) => b.episode_count - a.episode_count,
    unwatched: (a, b) => b.unwatched_count - a.unwatched_count,
  }[L.sort];
  items.sort(by);

  const totalEps = state.shows.reduce((n, s) => n + s.episode_count, 0);
  $('#libSub').textContent = `${plural(state.shows.length, 'show')} · ${plural(totalEps, 'recording')}`;

  if (!items.length) {
    grid.innerHTML = state.shows.length
      ? emptyState('Nothing matches', q ? `No recordings match “${L.q}”.` : 'No shows with unwatched episodes.')
      : emptyState('No recordings yet', 'Recordings on your Tablo will appear here after a sync.', '<button class="btn btn-primary" data-action="refresh-library">Sync now</button>');
    return;
  }
  grid.innerHTML = `<div class="card-grid ${L.layout === 'posters' ? 'posters' : ''}">${items.map(showCard).join('')}</div>`;
}

// ---------------------------------------------------------------------------
// Show (recorded episodes)
// ---------------------------------------------------------------------------
PAGES.show = async (r, token) => {
  paint(`<div class="page">${skeletonGrid(1)}</div>`);
  const res = await api(`/api/shows/episodes?show_id=${encodeURIComponent(r.arg)}`);
  if (stale(token)) return;
  state.show = res.show;
  state.episodes = res.episodes || [];
  state.selected.clear();
  state.seriesLink = null;
  renderShowPage();
  findSeriesForShow(state.show.title, token);
};

function renderShowPage() {
  const s = state.show;
  const eps = state.episodes;
  const unwatched = eps.filter(e => e.status !== 'Watched');
  const watchedCount = eps.filter(e => e.status === 'Watched' && !e.protected).length;
  const totalSec = eps.reduce((n, e) => n + (e.duration || 0), 0);
  // Prefer an episode in progress, then the oldest unwatched one
  const nextEp = unwatched.find(e => (e.position || 0) > 30) || unwatched[0] || eps[0];
  const nextLabel = nextEp && nextEp.status !== 'Watched' && (nextEp.position || 0) > 30 ? 'Resume' : (unwatched.length ? 'Play next' : 'Play');
  const bg = imgUrl(s.backdrop_url || s.cover_url);
  const network = (eps.find(e => e.network) || {}).network;

  paint(`
    <div class="hero">
      ${bg ? `<div class="hero-bg" style="background-image:url('${esc(bg)}')"></div>` : ''}
      <div class="hero-inner">
        <div class="hero-art">${artImg(s.cover_url || s.backdrop_url, s.title)}</div>
        <div class="hero-body">
          <div class="hero-kicker">
            <span class="tag">Recorded series</span>
            ${network ? `<span class="tag">${esc(network)}</span>` : ''}
          </div>
          <h1 class="hero-title">${esc(s.title)}</h1>
          <div class="hero-stats">${plural(eps.length, 'episode')} · ${unwatched.length} unwatched${totalSec ? ` · ${fmt.dur(totalSec)} total` : ''}</div>
          ${s.description ? `<p class="hero-desc" data-action="toggle-desc" title="Click to expand">${esc(s.description)}</p>` : ''}
          <div class="hero-actions">
            ${nextEp ? `<button class="btn btn-primary btn-lg" data-action="play-ep" data-id="${esc(nextEp.id)}" ${nextLabel === 'Resume' ? 'data-mode="resume"' : ''}>${icon('play', 16)}${nextLabel}: ${esc(fmt.se(nextEp.season_number, nextEp.episode_number) || episodeTitle(nextEp))}</button>` : ''}
            ${unwatched.length
              ? `<button class="btn btn-lg" data-action="mark-show-watched" data-value="true">${icon('check', 16)}Mark all watched</button>`
              : (eps.length ? `<button class="btn btn-lg" data-action="mark-show-watched" data-value="false">${icon('x', 16)}Mark all unwatched</button>` : '')}
            ${watchedCount ? `<button class="btn btn-lg btn-danger" data-action="delete-watched">${icon('trash', 16)}Delete ${watchedCount} watched</button>` : ''}
            <span id="seriesLinkSlot"></span>
          </div>
          ${showRules(s, eps)}
        </div>
      </div>
    </div>
    <div class="ep-table">
      <div class="ep-head">
        <input type="checkbox" class="checkbox" data-change="ep-select-all" title="Select all" ${state.selected.size && state.selected.size === eps.length ? 'checked' : ''}>
        <span></span><span>Episode</span><span>Title</span><span>Aired</span><span>Length</span><span class="ep-col-status">Status</span><span></span>
      </div>
      ${eps.length ? eps.map(episodeRow).join('') : emptyState('No episodes left', 'Everything from this show has been deleted.', '<a class="btn" href="#/library">Back to library</a>')}
    </div>
    <div style="height:60px"></div>`);
  updateBulkBar();
  if (state.seriesLink) placeSeriesLink(state.seriesLink);
}

const KEEP_CHOICES = [1, 2, 3, 5, 10, 20];
const CLEANUP_CHOICES = [1, 3, 7, 14, 30];

// Keep (a rule on the Tablo, which deletes older recordings itself) and automatic cleanup (TabloView
// deletes watched ones some days after watching)
function showRules(s, eps) {
  if (!eps.length) return '';
  const keepOpts = [...new Set([...KEEP_CHOICES, ...(s.keep ? [s.keep] : [])])].sort((a, b) => a - b);
  const cleanOpts = [...new Set([...CLEANUP_CHOICES, ...(s.cleanup_days ? [s.cleanup_days] : [])])].sort((a, b) => a - b);
  const keep = (s.path || '').startsWith('/recordings/series/') ? `
    <label class="rule-field" title="A rule on your Tablo: it deletes older recordings of this show itself, even when TabloView isn’t running">
      <span>Keep</span>
      <select class="select select-sm" data-change="show-keep">
        <option value="">All recordings</option>
        ${keepOpts.map(n => `<option value="${n}" ${s.keep === n ? 'selected' : ''}>Newest ${n}</option>`).join('')}
      </select>
    </label>` : '';
  return `
    <div class="hero-rules">
      <label class="rule-field" title="TabloView finds the commercial breaks in this show’s recordings in the background (on this PC), so you can skip them">
        <input type="checkbox" class="switch" data-change="show-commercials" ${s.find_commercials ? 'checked' : ''}>
        <span>Skip commercials</span>
      </label>
      ${keep}
      <label class="rule-field" title="TabloView deletes watched recordings of this show this long after you watch them, while it’s running (also in the tray). Protected recordings are kept.">
        <span>Delete watched</span>
        <select class="select select-sm" data-change="show-cleanup">
          <option value="">Never</option>
          ${cleanOpts.map(n => `<option value="${n}" ${s.cleanup_days === n ? 'selected' : ''}>${n === 1 ? 'After 1 day' : `After ${n} days`}</option>`).join('')}
        </select>
      </label>
    </div>`;
}

function mergeShow(show) {
  state.show = state.show && state.show.id === show.id ? { ...state.show, ...show } : show;
}

async function setKeep(el) {
  const s = state.show;
  const count = el.value ? Number(el.value) : null;
  if (count) {
    const newestFirst = [...state.episodes].sort((a, b) => (b.air_date || '').localeCompare(a.air_date || ''));
    const goes = newestFirst.slice(count);
    const ok = await confirmDialog({
      title: `Keep only the newest ${plural(count, 'recording')} of ${s.title}?`,
      text: `Your Tablo will delete older recordings of this show, ${goes.length ? `now (${plural(goes.length, 'recording')}) and ` : ''}as new ones are recorded, even when TabloView isn’t running.`,
      confirm: goes.length ? 'Keep newest only' : 'Save', danger: goes.length > 0,
    });
    if (!ok) { el.value = s.keep || ''; return; }
  }
  el.disabled = true;
  try {
    const res = await api(`/api/shows/keep?show_id=${encodeURIComponent(s.id)}`, { method: 'POST', body: JSON.stringify({ count }) });
    if (res.show) mergeShow(res.show);
    toast(count ? `Your Tablo will keep the newest ${plural(count, 'recording')}` : 'Your Tablo will keep all recordings', 'success');
    // The Tablo removes the extras itself; pick that up shortly
    if (count && count < state.episodes.length) setTimeout(() => !state.isSyncing && refreshLibrary(), 8000);
  } catch (err) {
    el.value = s.keep || '';
    toast(`Couldn't change the keep rule: ${err.message}`, 'error');
  } finally {
    el.disabled = false;
  }
}

async function setCleanup(el) {
  const s = state.show;
  const days = el.value ? Number(el.value) : null;
  if (days) {
    const ok = await confirmDialog({
      title: `Delete watched episodes of ${s.title} automatically?`,
      text: `TabloView will permanently delete each watched recording ${days === 1 ? '1 day' : `${days} days`} after you watch it (checked after each sync, while TabloView is running or in the tray). Protected recordings are kept.`,
      confirm: 'Turn on',
    });
    if (!ok) { el.value = s.cleanup_days || ''; return; }
  }
  try {
    const res = await api(`/api/shows/cleanup?show_id=${encodeURIComponent(s.id)}`, { method: 'POST', body: JSON.stringify({ days }) });
    if (res.show) mergeShow(res.show);
    toast(days ? `Watched episodes will be deleted ${days === 1 ? '1 day' : `${days} days`} after watching` : 'Automatic cleanup off', 'success');
  } catch (err) {
    el.value = s.cleanup_days || '';
    toast(`Couldn't save: ${err.message}`, 'error');
  }
}

// A recording that failed or came out short: pick another airing of the same episode to record
async function rerecordDialog(id) {
  const ep = findEpisode(id) || {};
  let airings;
  try { airings = (await api(`/api/episodes/${encodeURIComponent(id)}/rerecord`)).airings; } catch (err) { toast(err.message, 'error'); return; }
  const name = [fmt.se(ep.season_number, ep.episode_number), episodeTitle(ep)].filter(Boolean).join(' · ');
  await openModal(`
    <div class="dialog-body">
      <div class="dialog-title">Record ${esc(name || 'this episode')} again</div>
      ${airings.length ? `<div class="dialog-text">It airs again ${airings.length === 1 ? 'once' : `${airings.length} times`} in the next two weeks:</div>
        <div class="list" style="margin-top:12px">${airings.map(a => `
          <div class="list-row rerecord-row">
            <div><div class="row-title">${esc(fmt.dayLabel(a.air_datetime))} · ${esc(fmt.time(a.air_datetime))}</div>
              <div class="row-sub">${esc([a.channel_network, a.channel_call_sign].filter(Boolean).join(' · '))}</div></div>
            ${a.schedule_state === 'scheduled'
              ? '<span class="tag tag-accent">Set to record</span>'
              : `<button class="btn btn-sm btn-primary" data-action="rerecord-pick" data-path="${esc(a.path)}">${icon('plus', 14)}Record this one</button>`}
          </div>`).join('')}</div>`
        : `<div class="dialog-text">It doesn’t air again in the next two weeks of the guide. With “Record failed recordings again” on (Device page), TabloView keeps checking and records it if it comes up.</div>`}
    </div>
    <div class="dialog-foot"><button class="btn" data-action="modal-ok" data-autofocus>Close</button></div>`);
}

// Which channels' recordings fail, why and when (from the Tablo's own failure reasons, kept over time)
function signalPanel(sig) {
  const list = (sig && sig.channels) || [];
  if (!list.length) return '';
  const badge = { frequent: '<span class="tag tag-warn">Frequent problems</span>', some: '<span class="tag">Some problems</span>', ok: '<span class="dim">Fine</span>' };
  const signalTrouble = list.some(c => c.status !== 'ok' && c.signal);
  return `
    <div class="panel" style="grid-column:1/-1">
      <h3>Signal health</h3><div class="panel-sub">How recordings on each channel turned out over the last ${sig.days} days, and why the Tablo says any failed.</div>
      <div class="signal-list">${list.map(c => `
        <div class="signal-row ${c.status}">
          <div class="signal-ch"><b>${esc(c.channel)}</b> ${esc(c.call_sign)}${c.network ? ` <span class="dim">${esc(c.network)}</span>` : ''}</div>
          <div>${c.problems ? `${c.problems} of ${plural(c.recordings, 'recording')} had problems` : `${plural(c.recordings, 'recording')}, no problems`}</div>
          <div class="dim">${esc([c.reason, c.when].filter(Boolean).join(', '))}${c.last_problem ? ` · last ${esc(fmt.day(c.last_problem))}` : ''}</div>
          <div>${badge[c.status]}</div>
        </div>`).join('')}</div>
      ${signalTrouble ? `<p class="dim" style="margin-top:12px;font-size:12.5px">Weak or lost signal is almost always the antenna, not the Tablo. Check where the channel’s tower is (rabbitears.info or antennaweb.org) and aim the antenna toward it; try it higher up or at a different window, or add an amplifier for long cable runs. Then run a channel scan in the Tablo app, which also shows each channel’s signal strength. Storms and heavy rain can cause it too.</p>` : ''}
    </div>`;
}

// Where MP4 exports go: the Windows folder picker on the PC, or a typed path where there isn't one
async function chooseExportFolder(btn) {
  let path = null;
  btn.disabled = true;
  try {
    toast('Choose a folder in the window that opened (it may be behind the browser)');
    path = (await api('/api/system/pick_folder', { method: 'POST' })).path;
    if (!path) return;
  } catch {
    path = await promptExportFolder();
    if (!path) return;
  } finally {
    btn.disabled = false;
  }
  try {
    const res = await api('/api/system/export_folder', { method: 'POST', body: JSON.stringify({ path }) });
    toast(`Exports will be saved to ${res.downloads_dir}`, 'success');
    route();
  } catch (err) { toast(err.message, 'error'); }
}

function promptExportFolder() {
  let value = null;
  return openModal(`
    <form class="dialog-body" id="folderForm">
      <div class="dialog-title">Save exports to</div>
      <div class="dialog-text">Type the full path of a folder on this computer, for example <code>/home/you/Videos/Tablo</code>. It's created if it doesn't exist.</div>
      <input class="input" id="folderInput" style="width:100%;margin-top:12px" data-autofocus>
    </form>
    <div class="dialog-foot">
      <button class="btn" data-action="modal-cancel">Cancel</button>
      <button class="btn btn-primary" id="folderSave">Save</button>
    </div>`, {
    onReady: el => {
      const save = e => { e && e.preventDefault(); value = el.querySelector('#folderInput').value.trim(); closeModal(true); };
      el.querySelector('#folderForm').addEventListener('submit', save);
      el.querySelector('#folderSave').addEventListener('click', save);
    },
  }).then(() => value);
}

// Set or change the PIN (on the PC). Resolves true once it's saved.
async function setPinDialog(title = 'PIN for other devices', text = 'Phones, tablets and other computers on your network sign in with it once. Changing it signs them all out.') {
  let saved = false;
  await openModal(`
    <form class="dialog-body" id="setPinForm">
      <div class="dialog-title">${esc(title)}</div>
      <div class="dialog-text">${esc(text)}</div>
      <input class="input pin-input" id="newPin" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="6" placeholder="4 to 6 digits" autocomplete="new-password" data-autofocus style="margin-top:14px">
      <div class="pin-error" id="newPinError"></div>
    </form>
    <div class="dialog-foot">
      <button class="btn" data-action="modal-cancel">Cancel</button>
      <button class="btn btn-primary" id="savePin">Save PIN</button>
    </div>`, {
    onReady: el => {
      const save = async e => {
        e && e.preventDefault();
        const pin = el.querySelector('#newPin').value.trim();
        if (!/^[0-9]{4,6}$/.test(pin)) { el.querySelector('#newPinError').textContent = 'Use 4 to 6 digits.'; return; }
        try {
          await api('/api/lan/pin', { method: 'POST', body: JSON.stringify({ pin }) });
          saved = true;
          toast('PIN saved', 'success');
          closeModal(true);
        } catch (err) { el.querySelector('#newPinError').textContent = err.message; }
      };
      el.querySelector('#setPinForm').addEventListener('submit', save);
      el.querySelector('#savePin').addEventListener('click', save);
    },
  });
  return saved;
}

// Just this recording, whatever its show's Skip commercials setting
async function findCommercials(id) {
  try {
    const res = await api(`/api/episodes/${encodeURIComponent(id)}/find_commercials`, { method: 'POST' });
    const ep = findEpisode(id);
    if (ep && res.queued) ep.commercials = 'queued';
    toast(res.queued
      ? `TabloView will find the commercials in this recording${res.ahead ? ` after ${plural(res.ahead, 'other')}` : ''} (about 8 minutes per half hour, while nothing is playing)`
      : 'Its commercial breaks are already marked', 'success');
    rerenderAfterProgress();
  } catch (err) { toast(err.message, 'error'); }
}

async function setProtected(id, value) {
  try {
    await api(`/api/episodes/${encodeURIComponent(id)}/protected`, { method: 'POST', body: JSON.stringify({ protected: value }) });
    const ep = findEpisode(id);
    if (ep) ep.protected = value;
    toast(value ? 'Protected: it won’t be deleted automatically' : 'No longer protected', 'success');
    rerenderAfterProgress();
  } catch (err) {
    toast(`Couldn't change protection: ${err.message}`, 'error');
  }
}

function episodeStatus(ep) {
  const tag = episodeStatusTag(ep) + commercialTag(ep) + dropoutTag(ep);
  return ep.incomplete
    ? `${tag}<button class="link-btn" data-action="rerecord" data-id="${esc(ep.id)}" title="Find another airing of this episode to record">Record again</button>`
    : tag;
}

// What the background commercial finder has done with this recording (shows with Skip commercials on)
function commercialTag(ep) {
  if (ep.commercials === 'done') {
    return ep.commercial_breaks
      ? `<span class="ad-tag" title="${plural(ep.commercial_breaks, 'commercial break')} marked; skip them in the player">${icon('next', 11)}${ep.commercial_breaks}</span>`
      : '<span class="ad-tag dim" title="No commercial breaks found">0</span>';
  }
  if (ep.commercials === 'queued' || ep.commercials === 'analyzing') {
    const running = ep.commercials === 'analyzing' || (state.adProgress && state.adProgress.episode_id === ep.id);
    return `<span class="ad-tag ad-progress ${running ? '' : 'dim'}" data-ad-ep="${esc(ep.id)}" title="Commercial breaks are found in the background while nothing is playing">${running ? 'Finding commercials' : 'Waiting'}</span>`;
  }
  if (ep.commercials === 'unreliable') return '<span class="ad-tag dim" title="The show and its ads look too much alike to mark the breaks safely">–</span>';
  return '';
}

// Signal dropouts found in this recording (the Tablo flagged it as not clean): marked in red in the player
function dropoutTag(ep) {
  if (ep.finding_dropouts) return '<span class="ad-tag drop-tag dim" title="Looking for signal dropouts in this recording (in the background, while nothing is playing)">Checking signal</span>';
  const d = ep.dropouts || [];
  if (!d.length) return '';
  const secs = Math.round(d.reduce((sum, x) => sum + (x.end - x.start), 0));
  return `<span class="ad-tag drop-tag" title="${plural(d.length, 'signal dropout')} (${fmt.dur(secs) || `${secs} s`} in all) where the picture breaks up or freezes; marked in red on the timeline, and skippable">${plural(d.length, 'dropout')}</span>`;
}

function episodeStatusTag(ep) {
  if (ep.recording_state === 'recording') return '<span class="tag tag-live">Recording</span>';
  if (ep.recording_state === 'failed') {
    const mins = Math.round((ep.actual_duration || 0) / 60);
    const why = ep.recording_error && ep.recording_error.details === 'weak_signal' ? 'weak signal' : 'signal lost';
    // A failed recording can also run past the show's end (the Tablo keeps retrying after losing signal):
    // then nothing was cut short, but parts may be missing or glitchy
    if (ep.duration && (ep.actual_duration || 0) >= ep.duration - 60) {
      return `<span class="tag tag-warn" title="The Tablo lost the signal during this recording (${why}); parts may be missing or glitchy">Signal problems</span>`;
    }
    return mins > 0
      ? `<span class="tag tag-warn" title="Recording stopped after ${mins} min (${why})">Partial · ${mins}m</span>`
      : `<span class="tag tag-rec" title="Recording failed (${why})">Failed</span>`;
  }
  if (ep.ended_early) {
    const mins = Math.round((ep.actual_duration || 0) / 60);
    return `<span class="tag tag-warn" title="The recording stopped ${fmt.dur(ep.ended_early)} before the show ended">Short · ${mins}m</span>`;
  }
  if (ep.status === 'Watched') return '<span class="dim">Watched</span>';
  if ((ep.position || 0) > 30) {
    const left = fmt.dur((ep.duration || 0) - ep.position);
    return `<span class="tag tag-accent" title="Stopped at ${fmtClock(ep.position)}">${left ? `${left} left` : 'In progress'}</span>`;
  }
  return '<span class="tag tag-accent">Unwatched</span>';
}

function progressBar(ep) {
  if (ep.status === 'Watched' || !((ep.position || 0) > 30) || !ep.duration) return '';
  const pct = Math.min(100, Math.round((ep.position / ep.duration) * 100));
  return `<div class="ep-progress"><div style="width:${pct}%"></div></div>`;
}

function episodeRow(ep) {
  const watched = ep.status === 'Watched';
  const sel = state.selected.has(ep.id);
  // A frame from the recording itself; the series art stands in when the Tablo has none
  const thumb = imgUrl(ep.snapshot_url || (state.show && (state.show.backdrop_url || state.show.cover_url)));
  return `
    <div class="ep-row ${watched ? 'watched' : ''} ${sel ? 'selected' : ''}" data-ep-row="${esc(ep.id)}">
      <input type="checkbox" class="checkbox" data-change="ep-select" data-id="${esc(ep.id)}" ${sel ? 'checked' : ''}>
      <button class="ep-thumb" data-action="play-ep" data-id="${esc(ep.id)}" title="Play">
        ${thumb ? `<img src="${esc(thumb)}" alt="" loading="lazy">` : ''}
        <span class="ep-thumb-play">${icon('play', 14)}</span>
      </button>
      <div class="ep-se">${esc(fmt.se(ep.season_number, ep.episode_number) || '—')}</div>
      <div class="ep-main">
        <div class="ep-title">${ep.protected ? `<span class="ep-lock" title="Protected on your Tablo: it won’t be deleted automatically, and Delete watched skips it">${icon('lock', 13)}</span>` : ''}${esc(episodeTitle(ep))}</div>
        ${ep.description ? `<div class="ep-desc" title="${esc(ep.description)}">${esc(ep.description)}</div>` : ''}
        ${progressBar(ep)}
      </div>
      <div class="ep-cell">${esc(fmt.day(ep.air_date))}</div>
      <div class="ep-cell">${esc(fmt.dur(ep.duration))}</div>
      <div class="ep-col-status">${episodeStatus(ep)}</div>
      <button class="icon-btn" data-action="ep-menu" data-id="${esc(ep.id)}" title="More actions">${icon('more')}</button>
    </div>`;
}

// Link a recorded show to its guide series (for schedule controls), matched by title
async function findSeriesForShow(title, token) {
  state.seriesLink = null;
  try {
    const res = await api(`/api/guide/shows?search=${encodeURIComponent(title)}&limit=10`);
    if (stale(token)) return;
    const match = cacheGuide(res.shows).find(g => g.title.toLowerCase() === title.toLowerCase());
    if (match) { state.seriesLink = match; placeSeriesLink(match); }
  } catch { /* optional */ }
}

function placeSeriesLink(g) {
  const slot = $('#seriesLinkSlot');
  if (!slot) return;
  slot.innerHTML = `${recButton(g).replace('rec-btn', 'rec-btn btn-lg')}
    <button class="btn btn-lg btn-ghost" data-action="open-series" data-path="${esc(g.path)}">Upcoming airings ${icon('next', 16)}</button>`;
  slot.style.display = 'contents';
}

function clearSelection() {
  state.selected.clear();
  updateBulkBar();
}

function updateBulkBar() {
  const n = state.selected.size;
  $('#bulkBar').classList.toggle('visible', n > 0);
  $('#bulkCount').textContent = `${n} selected`;
}

async function deleteEpisode(id) {
  const ep = state.episodes.find(e => e.id === id);
  const ok = await confirmDialog({
    title: ep && ep.protected ? 'Delete this protected recording?' : 'Delete this recording?',
    text: `“${ep ? episodeTitle(ep) : 'This episode'}” will be permanently removed from your Tablo.${ep && ep.protected ? ' It’s protected on your Tablo, so it would otherwise be kept.' : ''}`,
    confirm: 'Delete', danger: true,
  });
  if (!ok) return;
  try {
    const res = await api(`/api/episodes/${encodeURIComponent(id)}`, { method: 'DELETE' });
    state.episodes = state.episodes.filter(e => e.id !== id);
    state.selected.delete(id);
    if (res.show) mergeShow(res.show);
    toast('Recording deleted', 'success');
    afterEpisodeChange();
  } catch (err) {
    toast(`Delete failed: ${err.message}`, 'error');
  }
}

async function bulkDelete() {
  const ids = Array.from(state.selected);
  if (!ids.length) return;
  const prot = state.episodes.filter(e => state.selected.has(e.id) && e.protected).length;
  const ok = await confirmDialog({
    title: `Delete ${plural(ids.length, 'recording')}?`,
    text: `They will be permanently removed from your Tablo.${prot ? ` ${prot === 1 ? 'One of them is' : `${prot} of them are`} protected on your Tablo.` : ''}`,
    confirm: 'Delete', danger: true,
  });
  if (!ok) return;
  try {
    const res = await api('/api/episodes/bulk_delete', { method: 'POST', body: JSON.stringify({ episode_ids: ids }) });
    const deleted = new Set(res.deleted_ids || []);
    state.episodes = state.episodes.filter(e => !deleted.has(e.id));
    deleted.forEach(id => state.selected.delete(id));
    toast(`Deleted ${plural(res.deleted_count, 'recording')}`, 'success');
    if (res.errors && res.errors.length) toast(`${res.errors.length} couldn't be deleted: ${res.errors[0]}`, 'error');
    afterEpisodeChange();
  } catch (err) {
    toast(`Delete failed: ${err.message}`, 'error');
  }
}

async function deleteWatched() {
  // Protected recordings are kept (the server skips them too)
  const watched = state.episodes.filter(e => e.status === 'Watched' && !e.protected);
  const kept = state.episodes.filter(e => e.status === 'Watched' && e.protected).length;
  if (!watched.length) return;
  const ok = await confirmDialog({
    title: `Delete ${plural(watched.length, 'watched episode')}?`,
    text: `${kept ? 'The' : 'All'} watched episodes of “${state.show.title}” will be permanently removed from your Tablo.${kept ? ` ${plural(kept, 'protected recording')} will be kept.` : ''}`,
    confirm: 'Delete watched', danger: true,
  });
  if (!ok) return;
  try {
    const res = await api(`/api/shows/delete_watched?show_id=${encodeURIComponent(state.show.id)}`, { method: 'POST' });
    const deleted = new Set(res.deleted_ids || []);
    state.episodes = state.episodes.filter(e => !deleted.has(e.id));
    deleted.forEach(id => state.selected.delete(id));
    if (res.show) mergeShow(res.show);
    toast(`Deleted ${plural(res.deleted_count, 'watched episode')}`, 'success');
    if (res.errors && res.errors.length) toast(`${res.errors.length} couldn't be deleted: ${res.errors[0]}`, 'error');
    afterEpisodeChange();
  } catch (err) {
    toast(`Delete failed: ${err.message}`, 'error');
  }
}

function afterEpisodeChange() {
  state.shows = null;
  loadStorage();
  if (!state.episodes.length) { location.hash = '#/library'; return; }
  const scroll = view().scrollTop;
  renderShowPage();
  view().scrollTop = scroll;
}

async function bulkExport() {
  const ids = Array.from(state.selected);
  if (!ids.length) return;
  try {
    const res = await api('/api/episodes/export_batch', { method: 'POST', body: JSON.stringify({ episode_ids: ids }) });
    setActiveExports(state.activeExports + (res.count || ids.length));
    toast(`${plural(res.count || ids.length, 'export')} queued. They run one at a time; track them under Downloads.`, 'success');
    ACTIONS['bulk-clear']();
  } catch (err) {
    toast(`Export failed: ${err.message}`, 'error');
  }
}

async function exportEpisode(id) {
  try {
    await api(`/api/episodes/${encodeURIComponent(id)}/export`, { method: 'POST' });
    setActiveExports(state.activeExports + 1);
    toast('Export started. Track it under Downloads.', 'success');
  } catch (err) {
    toast(`Export failed: ${err.message}`, 'error');
  }
}

// ---------------------------------------------------------------------------
// Guide
// ---------------------------------------------------------------------------
const GUIDE_PAGE = 120;

function guideTabs(streamingTab) {
  const tab = (href, label, active) => `<a href="${href}" class="${active ? 'active' : ''}" style="display:inline-flex;align-items:center;height:28px;padding:0 12px;border-radius:7px;font-weight:500;font-size:13px">${label}</a>`;
  return `<div class="segmented tabs">${tab('#/guide', 'Antenna channels', !streamingTab)}${tab('#/guide?tab=streaming', 'Streaming channels', streamingTab)}</div>`;
}

PAGES.guide = async (r, token) => {
  if (r.query.get('tab') === 'streaming') return streamingGuide(token);
  const G = state.guide;
  if (r.query.has('q')) G.q = r.query.get('q');
  if (r.query.has('highlight')) { G.highlight = r.query.get('highlight'); G.sort = 'soonest'; }

  paint(`<div class="page">
    <div class="page-head">
      <div><h1 class="page-title">Guide</h1><div class="page-sub">Shows on your antenna channels over the next two weeks</div></div>
      <div class="page-head-actions"><button class="btn btn-ghost btn-sm" data-action="sync-guide">${icon('refresh', 15)}Refresh guide</button></div>
    </div>
    <div class="toolbar">${guideTabs(false)}</div>
    <div class="toolbar">
      <div class="input-search">${icon('search', 15)}<input class="input" data-input="guide-q" placeholder="Search the guide" value="${esc(G.q)}"></div>
      <div class="segmented" id="guideHighlights">${guideHighlightButtons()}</div>
      <div class="grow"></div>
      <select class="select" data-change="guide-rule">
        <option value="">Any status</option>
        <option value="scheduled" ${G.rule === 'scheduled' ? 'selected' : ''}>Recording</option>
        <option value="unscheduled" ${G.rule === 'unscheduled' ? 'selected' : ''}>Not recording</option>
      </select>
      <select class="select" data-change="guide-sort">
        <option value="primetime" ${G.sort === 'primetime' ? 'selected' : ''}>Recommended</option>
        <option value="soonest" ${G.sort === 'soonest' ? 'selected' : ''}>Airing soonest</option>
        <option value="title" ${G.sort === 'title' ? 'selected' : ''}>Title A–Z</option>
        <option value="airings" ${G.sort === 'airings' ? 'selected' : ''}>Most airings</option>
        <option value="recent" ${G.sort === 'recent' ? 'selected' : ''}>Newest series</option>
      </select>
    </div>
    <div class="chip-row" id="guideTypes">${guideTypeChips()}</div>
    <div id="guideGrid">${skeletonGrid(10)}</div>
  </div>`);
  await loadGuide(token);
};

// The same chips as the Streaming tab's categories
function guideTypeChips() {
  const G = state.guide;
  return [['all', 'All'], ['series', 'TV shows'], ['movies', 'Movies'], ['sports', 'Sports']]
    .map(([v, label]) => `<button class="chip ${G.category === v ? 'active' : ''}" data-action="guide-type" data-value="${v}">${label}</button>`).join('');
}

function guideHighlightButtons() {
  const G = state.guide, h = G.highlights || {};
  const b = (value, label, count) => `<button data-action="guide-highlight" data-value="${value}" class="${G.highlight === value ? 'active' : ''}">${label}${count !== undefined ? ` <span class="count">${count}</span>` : ''}</button>`;
  return b('', 'Everything') + b('premieres', 'Premieres', h.premieres) + b('primetime_new', 'New in primetime', h.primetime_new);
}

async function loadGuide(token, append = false) {
  const G = state.guide;
  const params = new URLSearchParams({ sort: G.sort, limit: String(GUIDE_PAGE), offset: String(append ? G.offset : 0) });
  if (G.q.trim()) params.set('search', G.q.trim());
  if (G.highlight) params.set('highlight', G.highlight);
  if (G.category !== 'all') params.set('category', G.category);
  if (G.rule) params.set('rule', G.rule);
  try {
    const res = await api(`/api/guide/shows?${params}`);
    if (token !== undefined && stale(token)) return;
    const items = cacheGuide(res.shows);
    G.items = append ? G.items.concat(items) : items;
    G.offset = G.items.length;
    G.hasMore = items.length === GUIDE_PAGE;
    G.highlights = res.highlights || G.highlights;
    $('#navScheduledCount').textContent = res.total_scheduled || '';
    renderGuideGrid();
  } catch (err) {
    const grid = $('#guideGrid');
    if (grid) { grid.innerHTML = errorState(err, 'guide-reload'); hydrateIcons(grid); }
  }
}

function renderGuideGrid() {
  const G = state.guide;
  const grid = $('#guideGrid');
  if (!grid) return;
  const hl = $('#guideHighlights');
  if (hl) hl.innerHTML = guideHighlightButtons();
  if (!G.items.length) {
    grid.innerHTML = emptyState('Nothing found', G.q ? `Nothing in the guide matches “${G.q}”.` : 'Try a different filter.');
    return;
  }
  // Only the Recording view includes series with no upcoming airings; list those after a divider
  const airing = G.items.filter(g => g.next_airing);
  const waiting = G.items.filter(g => !g.next_airing);
  if (G.category === 'sports' && airing.length) {
    grid.innerHTML = sportsGrid(airing);
    hydrateIcons(grid);
    return;
  }
  grid.innerHTML = `${airing.length ? `<div class="card-grid">${airing.map(guideCard).join('')}</div>` : ''}
    ${G.hasMore ? '<div style="text-align:center;margin-top:28px"><button class="btn" data-action="guide-more">Show more</button></div>' : ''}
    ${waiting.length ? `
      <div class="section-head" style="margin:${airing.length ? '36px' : '0'} 0 14px">
        <h2 class="section-title">No upcoming airings</h2>
        <span class="section-sub">${plural(waiting.length, 'series', 'series')} · the Tablo keeps these rules and records new episodes when they're in the guide</span>
      </div>
      <div class="card-grid">${waiting.map(guideCard).join('')}</div>` : ''}`;
}

// Sports: each Tablo sports entry is a league ("NFL Football", "Premier League Soccer") tagged with its
// sport, so group the leagues under their sport instead of one long list, with buttons to pick a sport
const SPORT_GENERIC = new Set(['sports', 'sports event', 'sports non-event', 'sports talk']);

function sportOf(g) {
  const genre = (g.genres || []).find(x => !SPORT_GENERIC.has(String(x).toLowerCase()));
  return genre || 'Other sports';
}

function sportsGrid(items) {
  const G = state.guide;
  const groups = new Map();
  for (const g of items) {
    const s = sportOf(g);
    if (!groups.has(s)) groups.set(s, []);
    groups.get(s).push(g);
  }
  // Busiest sports first; 'Other sports' last
  const sports = [...groups.keys()].sort((a, b) =>
    (a === 'Other sports') - (b === 'Other sports') || groups.get(b).length - groups.get(a).length || a.localeCompare(b));
  if (G.sport && !groups.has(G.sport)) G.sport = '';
  const b = (value, label, count) => `<button data-action="guide-sport" data-value="${esc(value)}" class="${G.sport === value ? 'active' : ''}">${esc(label)}${count !== undefined ? ` <span class="count">${count}</span>` : ''}</button>`;
  const picker = `<div class="segmented" style="margin-bottom:22px;flex-wrap:wrap">${b('', 'All sports')}${sports.map(s => b(s, s, groups.get(s).length)).join('')}</div>`;
  const shown = G.sport ? [G.sport] : sports;
  return picker + shown.map((s, i) => `
    <div class="section-head" style="margin:${i ? '32px' : '0'} 0 14px">
      <h2 class="section-title">${esc(s)}</h2>
      <span class="section-sub">${plural(groups.get(s).length, 'league')}</span>
    </div>
    <div class="card-grid">${groups.get(s).map(guideCard).join('')}</div>`).join('');
}

const reloadGuide = debounce(() => loadGuide(routeToken), 220);

// ---------------------------------------------------------------------------
// Guide → Streaming channels: Tablo's online guide for the free streaming channels, by category
// ---------------------------------------------------------------------------
async function streamingGuide(token) {
  const F = state.fast;
  paint(`<div class="page">
    <div class="page-head">
      <div><h1 class="page-title">Guide</h1><div class="page-sub">Shows on the free streaming channels over the next week</div></div>
    </div>
    <div class="toolbar">${guideTabs(true)}</div>
    <div class="toolbar">
      <div class="input-search">${icon('search', 15)}<input class="input" data-input="fast-q" placeholder="Search streaming channels" value="${esc(F.q)}"></div>
      <label class="switch-row" style="margin:0" title="Channels whose shows your Tablo is allowed to record">
        <input type="checkbox" class="switch" data-change="fast-recordable" ${F.recordable ? 'checked' : ''}>
        <span>Recordable channels only</span>
      </label>
    </div>
    <div class="chip-row" id="fastCategories"></div>
    <div id="fastGrid">${skeletonGrid(10)}</div>
  </div>`);
  await loadStreaming(token);
}

async function loadStreaming(token) {
  const F = state.fast;
  const params = new URLSearchParams({ category: F.category, recordable: F.recordable ? 'true' : 'false' });
  if (F.q.trim()) params.set('q', F.q.trim());
  try {
    const res = await api(`/api/streaming/shows?${params}`);
    if (token !== undefined && stale(token)) return;
    F.data = res;
    renderStreaming();
    // First visit: the listings are still loading (about ten seconds); look again shortly
    if (res.loading && !res.shows.length) setTimeout(() => { if (parseRoute().name === 'guide' && !stale(token)) loadStreaming(token); }, 3000);
  } catch (err) {
    const grid = $('#fastGrid');
    if (grid) { grid.innerHTML = errorState(err, 'fast-reload'); hydrateIcons(grid); }
  }
}

const reloadStreaming = debounce(() => loadStreaming(routeToken), 220);

function renderStreaming() {
  const F = state.fast, d = F.data;
  const grid = $('#fastGrid'), chips = $('#fastCategories');
  if (!grid || !d) return;
  const total = d.categories.reduce((n, c) => n + c.count, 0);
  const chip = (id, label, n) => `<button class="chip ${F.category === id ? 'active' : ''}" data-action="fast-category" data-value="${id}">${esc(label)} <span class="count">${n}</span></button>`;
  chips.innerHTML = d.categories.length ? chip('all', 'All', total) + d.categories.map(c => chip(c.id, c.label, c.count)).join('') : '';
  if (!d.shows.length) {
    grid.innerHTML = d.loading
      ? '<div class="loading-line" style="padding:28px"><span class="spinner"></span>Loading the streaming channels’ listings…</div>'
      : emptyState('Nothing found', d.error ? `Couldn’t load the streaming listings: ${d.error}` : F.q ? `No streaming show matches “${F.q}”.` : 'Try a different category.');
    return;
  }
  grid.innerHTML = `<div class="card-grid">${d.shows.map(streamCard).join('')}</div>`;
}

function streamCard(s) {
  const n = s.next_airing;
  const when = s.on_now ? '<span class="hl">On now</span>' : `<span class="hl">${esc(fmt.when(n.datetime))}</span>`;
  return `
    <div class="media-card" data-action="fast-show" data-id="${esc(s.show_id)}" title="${esc(s.title)}">
      <div class="media-art">${artImg(s.image, s.title)}${s.on_now ? '<span class="art-badge art-badge-left" style="background:var(--rec)">On now</span>' : ''}</div>
      <div class="media-meta">
        <div class="media-title">${esc(s.title)}</div>
        <div class="media-sub">${when} · ${esc(n.channel_name)}${s.channels.length > 1 ? ` +${s.channels.length - 1}` : ''}</div>
        <div class="media-foot fast-foot">
          ${n.channel_logo ? `<img class="fast-logo" src="${esc(n.channel_logo)}" alt="" loading="lazy">` : ''}
          ${s.can_record ? '<span class="tag" title="Your Tablo is allowed to record this channel">Recordable</span>' : ''}
        </div>
      </div>
    </div>`;
}

// Record, or stop recording, a streaming airing on the Tablo; then show the airings again
async function recordStreaming(el) {
  const on = el.dataset.on === '1';
  el.disabled = true;
  try {
    const res = await api('/api/streaming/record', { method: 'POST', body: JSON.stringify({ airing_id: el.dataset.id, scheduled: on }) });
    const ok = on ? res.schedule_state === 'scheduled' || res.schedule_state === 'recording' : res.schedule_state !== 'scheduled';
    toast(on ? (ok ? 'Your Tablo will record it' : 'Your Tablo didn’t confirm the recording; check Scheduled')
             : (ok ? 'Recording cancelled' : 'Your Tablo still has it set to record'), ok ? 'success' : 'error');
    state.upcoming = null;
    const item = el.dataset.key && state.epgItems[el.dataset.key];
    if (item && ok) {
      item.airing.schedule_state = on ? 'scheduled' : 'none';
      if (!on) item.airing.recording_now = false;
      renderEpg();
    }
  } catch (err) {
    toast(`Couldn't ${on ? 'record' : 'cancel'} it: ${err.message}`, 'error');
  }
  if (el.dataset.key) openAiringModal(el.dataset.key);
  else openStreamShow(el.dataset.show);
}

// A streaming show's upcoming airings, with Watch for the one on now
async function openStreamShow(showId) {
  const s = ((state.fast.data && state.fast.data.shows) || []).find(x => x.show_id === showId);
  let airings = [];
  try { airings = (await api(`/api/streaming/shows/${encodeURIComponent(showId)}/airings`)).airings; } catch { /* shown empty */ }
  const now = Date.now();
  const rows = airings.slice(0, 40).map(a => {
    const start = new Date(a.air_datetime).getTime(), end = start + (a.duration || 0) * 1000;
    const onNow = start <= now && now < end;
    const se = fmt.se(a.season_number, a.episode_number);
    const ep = [se, a.title && a.title !== a.show_title ? a.title : ''].filter(Boolean).join(' · ');
    return `<div class="fast-airing">
      <div class="upnext-when">${onNow ? '<span class="tag tag-rec-live"><span class="rec-pulse"></span>ON NOW</span>' : esc(fmt.when(a.air_datetime))}<span class="dim">until ${esc(fmt.time(new Date(end).toISOString()))}</span></div>
      <div style="min-width:0">
        <div class="row-title" style="font-weight:600">${esc(ep || a.show_title)}</div>
        ${a.description ? `<div class="row-sub" title="${esc(a.description)}">${esc(a.description)}</div>` : ''}
      </div>
      <div class="ch-cell">${a.channel_logo ? `<img class="ch-logo" src="${esc(a.channel_logo)}" alt="" loading="lazy">` : ''}<span class="ch-label">${esc(a.channel_name)}</span></div>
      <div class="fast-acts">
        ${onNow ? `<button class="btn btn-sm btn-primary" data-action="modal-watch-live" data-id="${esc(a.channel_identifier)}" data-name="${esc(a.channel_name)}" data-kind="fast">${icon('play', 13)}Watch</button>` : ''}
        ${!a.can_record ? '' : ['scheduled', 'recording'].includes(a.schedule_state)
          ? `<button class="btn btn-sm rec-set" data-action="fast-record" data-id="${esc(a.id)}" data-show="${esc(showId)}" data-on="0" title="Your Tablo will record this. Click to cancel.">${icon('check', 13)}Recording</button>`
          : `<button class="btn btn-sm" data-action="fast-record" data-id="${esc(a.id)}" data-show="${esc(showId)}" data-on="1" title="Record this on your Tablo">${onNow ? 'Record from now' : 'Record'}</button>`}
      </div>
    </div>`;
  }).join('');
  const recordable = airings.some(a => a.can_record);
  await openModal(`
    <div class="dialog-body scroll">
      <div class="dialog-title">${esc((s && s.title) || (airings[0] && airings[0].show_title) || 'Show')}</div>
      <div class="dialog-text">${airings.length ? `${plural(airings.length, 'airing')} on the streaming channels this week.` : 'No more airings this week.'}
        ${recordable ? ' Choose Record to have your Tablo record one.' : ''}</div>
      <div class="fast-airings">${rows}</div>
    </div>
    <div class="dialog-foot"><button class="btn" data-action="modal-ok" data-autofocus>Close</button></div>`, { wide: true });
}

// ---------------------------------------------------------------------------
// Series (guide show detail + upcoming airings)
// ---------------------------------------------------------------------------
PAGES.series = async (r, token) => {
  const path = r.arg;
  let g = state.guideCache.get(path);
  if (!g) {
    paint(`<div class="page">${skeletonGrid(1)}</div>`);
    g = await api(`/api/guide/series?path=${encodeURIComponent(path)}`);
    if (stale(token)) return;
    cacheGuide([g]);
  }
  state.series = g;
  await loadShows().catch(() => []);
  if (stale(token)) return;
  renderSeriesPage();
  loadSeriesAirings(path, token);
};

function ruleControl(g) {
  const rule = g.schedule_rule || 'none';
  const b = (value, label) => `<button data-action="set-rule" data-path="${esc(g.path)}" data-rule="${value}" class="${rule === value ? 'active' : ''}">${label}</button>`;
  return `<div class="segmented rule" data-rule-control="${esc(g.path)}">${b('none', "Don't record")}${b('new', 'New episodes')}${b('all', 'All episodes')}</div>`;
}

function renderSeriesPage() {
  const g = state.series;
  const bg = imgUrl(g.backdrop_url || g.cover_url);
  const genres = Array.isArray(g.genres) ? g.genres : [];
  const libShow = (state.shows || []).find(s => s.title.toLowerCase() === (g.title || '').toLowerCase());
  const cat = { series: 'TV series', movies: 'Movie', sports: 'Sports' }[g.category] || 'TV series';

  paint(`
    <div class="hero">
      ${bg ? `<div class="hero-bg" style="background-image:url('${esc(bg)}')"></div>` : ''}
      <div class="hero-inner">
        <div class="hero-art">${artImg(g.cover_url || g.backdrop_url, g.title)}</div>
        <div class="hero-body">
          <div class="hero-kicker">
            <span class="tag">${esc(cat)}</span>
            ${genres.slice(0, 3).map(x => `<span class="tag">${esc(x)}</span>`).join('')}
            ${g.has_premiere ? '<span class="tag tag-premiere">Premiere coming up</span>' : ''}
          </div>
          <h1 class="hero-title">${esc(g.title)}</h1>
          <div class="hero-stats">${g.orig_air_date ? `Premiered ${esc(String(g.orig_air_date).slice(0, 4))}` : ''}</div>
          ${g.description ? `<p class="hero-desc" data-action="toggle-desc" title="Click to expand">${esc(g.description)}</p>` : ''}
          <div class="hero-actions">
            <div class="rule-control"><span class="rule-label">Series recording</span>${ruleControl(g)}</div>
            ${libShow ? `<button class="btn btn-lg" data-action="open-show" data-id="${esc(libShow.id)}" style="align-self:flex-end">${icon('library', 16)}${plural(libShow.episode_count, 'recording')} in library</button>` : ''}
          </div>
        </div>
      </div>
    </div>
    <div class="page">
      <div class="section-head"><h2 class="section-title">Upcoming airings</h2><span class="section-sub" id="airingsSub"></span></div>
      <div class="list" id="seriesAirings"><div class="loading-line"><span class="spinner"></span>Checking upcoming airings on your Tablo…</div></div>
    </div>`);
}

async function loadSeriesAirings(path, token) {
  const box = $('#seriesAirings');
  try {
    const res = await api(`/api/guide/series/episodes?series_path=${encodeURIComponent(path)}`);
    if (token !== undefined && stale(token)) return;
    const eps = res.episodes || [];
    const sub = $('#airingsSub');
    if (sub) sub.textContent = eps.length ? `${plural(eps.length, 'airing')} · ${eps.filter(e => e.is_scheduled).length} set to record` : '';
    if (!eps.length) { box.innerHTML = emptyState('No upcoming airings', 'Nothing from this series is in the guide for the next two weeks.'); return; }
    box.innerHTML = eps.map(airingRow).join('');
  } catch (err) {
    if (box) box.innerHTML = `<div class="loading-line" style="color:var(--rec)">${icon('alert', 16)}Couldn't load airings: ${esc(err.message)}</div>`;
  }
}

function airingRow(ep) {
  const ch = ep.channel || {};
  const num = ch.major ? `${ch.major}.${ch.minor}` : '';
  const end = ep.air_datetime ? new Date(new Date(ep.air_datetime).getTime() + (ep.duration || 0) * 1000).toISOString() : '';
  const se = fmt.se(ep.season_number, ep.episode_number);
  const isNew = (ep.qualifiers || []).map(q => String(q).toLowerCase()).includes('new');
  const title = episodeTitle(ep);
  return `
    <div class="list-row airing-row">
      <div class="airing-when"><b>${esc(fmt.dayLabel(ep.air_datetime))}</b><span>${esc(fmt.time(ep.air_datetime))}–${esc(fmt.time(end))}</span></div>
      <div class="channel-chip">
        ${ch.logo_url ? `<img src="${esc(ch.logo_url)}" alt="" loading="lazy">` : ''}
        <div class="ch-text"><div class="ch-name">${esc(ch.network || ch.call_sign || 'Channel')}</div><div class="ch-sub">${esc([num, ch.call_sign].filter(Boolean).join(' '))}</div></div>
      </div>
      <div style="min-width:0">
        <div class="row-title">${se ? `<span class="dim">${se}</span> ` : ''}${esc(title)}</div>
        ${ep.description ? `<div class="row-sub" title="${esc(ep.description)}">${esc(ep.description)}</div>` : ''}
      </div>
      <div>${isNew ? '<span class="tag tag-new">NEW</span>' : ''}</div>
      <button class="toggle-rec ${ep.is_scheduled ? 'on' : ''}" data-action="toggle-airing" data-path="${esc(ep.path)}" data-on="${ep.is_scheduled ? '1' : ''}">
        ${ep.is_scheduled ? `${icon('check', 14)}Recording` : `${icon('plus', 14)}Record`}
      </button>
    </div>`;
}

async function setRule(path, rule) {
  const g = state.guideCache.get(path) || { path, title: 'Series' };
  try {
    await api('/api/guide/series/schedule', { method: 'POST', body: JSON.stringify({ path, rule }) });
    g.schedule_rule = rule;
    state.guideCache.set(path, g);
    state.scheduled.items = null;
    // Refresh every record button / rule control for this series in place
    $$('[data-rule-path]').filter(el => el.dataset.rulePath === path).forEach(el => {
      const lg = el.classList.contains('btn-lg');
      el.outerHTML = lg ? recButton(g).replace('rec-btn', 'rec-btn btn-lg') : recButton(g);
    });
    $$('[data-rule-control]').filter(el => el.dataset.ruleControl === path).forEach(el => { el.outerHTML = ruleControl(g); });
    const label = rule === 'new' ? 'recording new episodes' : rule === 'all' ? 'recording all episodes' : 'no longer recording';
    toast(`${g.title}: ${label}`, rule === 'none' ? 'info' : 'success');
    loadScheduled(true).catch(() => {});
    if (parseRoute().name === 'series' && state.series && state.series.path === path) loadSeriesAirings(path);
    if (parseRoute().name === 'scheduled') renderScheduledList();
  } catch (err) {
    toast(`Couldn't change recording: ${err.message}`, 'error');
  }
}

function recMenu(anchor, path) {
  const g = state.guideCache.get(path) || { path };
  const rule = g.schedule_rule || 'none';
  openMenu(anchor, [
    { heading: 'Record this series' },
    { label: 'New episodes only', icon: 'plus', checked: rule === 'new', run: () => setRule(path, 'new') },
    { label: 'All episodes', icon: 'plus', checked: rule === 'all', run: () => setRule(path, 'all') },
    ...(rule !== 'none' ? [{ sep: true }, { label: 'Stop recording', icon: 'x', danger: true, run: () => setRule(path, 'none') }] : []),
    { sep: true },
    { label: 'Upcoming airings', icon: 'calendar', run: () => { location.hash = `#/series/${encodeURIComponent(path)}`; } },
  ]);
}

async function toggleAiring(btn) {
  const path = btn.dataset.path;
  const on = !btn.dataset.on;
  btn.disabled = true;
  try {
    await api('/api/guide/episodes/schedule', { method: 'POST', body: JSON.stringify({ path, scheduled: on }) });
    btn.dataset.on = on ? '1' : '';
    btn.classList.toggle('on', on);
    btn.innerHTML = on ? `${icon('check', 14)}Recording` : `${icon('plus', 14)}Record`;
    toast(on ? 'Episode will be recorded' : 'Episode recording cancelled', on ? 'success' : 'info');
  } catch (err) {
    toast(`Couldn't change this episode: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
  }
}

// Refresh guide: your Tablo downloads the latest guide, then TabloView reads it (a few minutes)
async function syncGuide() {
  try {
    await api('/api/guide/sync', { method: 'POST' });
    toast('Your Tablo is downloading the latest guide. TabloView updates when it’s done, in a few minutes.');
  } catch (err) {
    toast(`Guide refresh failed: ${err.message}`, 'error');
    return;
  }
  let said = false;
  for (let i = 0; i < 120; i++) {
    await new Promise(r => setTimeout(r, 5000));
    let s;
    try { s = await api('/api/guide/sync/status'); } catch { continue; }
    if (s.stage === 'syncing' && !said) { said = true; toast('Your Tablo has the new guide. Reading it now…'); }
    if (s.stage === 'done' || s.stage === 'failed') {
      if (s.stage === 'failed') toast(`Guide refresh failed: ${s.error || 'unknown error'}`, 'error');
      else toast('Guide updated', 'success');
      state.scheduled.items = null;
      state.upcoming = null;
      if (['guide', 'scheduled', 'home', 'live'].includes(parseRoute().name)) route();
      return;
    }
  }
}

// ---------------------------------------------------------------------------
// Scheduled
// ---------------------------------------------------------------------------
PAGES.scheduled = async (r, token) => {
  const S = state.scheduled;
  const upcomingView = r.query.get('view') === 'upcoming';
  const tab = (href, label, active, id) => `<a href="${href}" class="${active ? 'active' : ''}" style="display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 12px;border-radius:7px;font-weight:500;font-size:13px">${label}<span class="count" id="${id}"></span></a>`;
  paint(`<div class="page">
    <div class="page-head">
      <div><h1 class="page-title">Scheduled</h1><div class="page-sub">${upcomingView ? 'Every recording your Tablo plans to make over the next two weeks' : 'Series your Tablo records automatically'}</div></div>
      <div class="page-head-actions">
        ${upcomingView ? `<button class="btn btn-ghost btn-sm" data-action="calendar-help">${icon('calendar', 15)}Add to calendar</button>` : ''}
        <button class="btn btn-ghost btn-sm" data-action="sync-guide">${icon('refresh', 15)}Refresh from Tablo</button>
      </div>
    </div>
    <div class="toolbar">
      <div class="segmented tabs">${tab('#/scheduled', 'Series', !upcomingView, 'tabSeriesCount')}${tab('#/scheduled?view=upcoming', 'Upcoming recordings', upcomingView, 'tabUpcomingCount')}</div>
      ${upcomingView ? '' : `<div class="input-search">${icon('search', 15)}<input class="input" data-input="scheduled-q" placeholder="Filter scheduled series" value="${esc(S.q)}"></div>
      <div class="segmented" id="schedFilters"></div>`}
    </div>
    <div id="schedList"><div class="list"><div class="loading-line"><span class="spinner"></span>Loading…</div></div></div>
  </div>`);
  const [, upcoming] = await Promise.all([loadScheduled(true), loadUpcoming()]);
  if (stale(token)) return;
  $('#tabSeriesCount').textContent = S.items.length;
  $('#tabUpcomingCount').textContent = upcoming ? upcoming.count : '';
  if (upcomingView) renderUpcomingList();
  else renderScheduledList();
};

async function loadUpcoming() {
  try {
    state.upcoming = await api('/api/guide/upcoming');
  } catch {
    state.upcoming = null;
  }
  return state.upcoming;
}

function conflictBanner(conflicts, { compact = false } = {}) {
  if (!conflicts || !conflicts.length) return '';
  const items = conflicts.map(c =>
    `<li><b>${esc(fmt.dayLabel(c.start))} ${esc(fmt.time(c.start))}–${esc(fmt.time(c.end))}</b>: ${c.count} recordings at once with ${c.tuners} tuners (${esc(c.titles.join(', '))})</li>`).join('');
  return `<div class="conflict-banner">
    <div class="conflict-head">${icon('alert', 18)}<b>${plural(conflicts.length, 'recording conflict')}</b>
      <span class="dim">One of the overlapping shows won't record. Cancel one, or record it from another airing.</span>
      <span style="margin-left:auto;display:flex;gap:8px">
        <button class="btn btn-sm btn-primary" data-action="fix-conflicts">Fix…</button>
        ${compact ? '<a class="btn btn-sm" href="#/scheduled?view=upcoming">Review</a>' : ''}
      </span></div>
    ${compact ? '' : `<ul>${items}</ul>`}
  </div>`;
}

// New episodes of Record New series that the Tablo decided aren't new, so it won't record them
// (a Tablo problem since the fall 2026 season: toggling the series rule fixed it until the next one)
function missedNew(u) {
  return ((u && u.recordings) || []).filter(a => a.missed_new);
}

function missedNewBanner(list, { compact = false } = {}) {
  if (!list.length) return '';
  return `<div class="conflict-banner">
    <div class="conflict-head">${icon('alert', 18)}<b>${plural(list.length, 'new episode')} your Tablo won't record</b>
      <span class="dim">The guide marks ${list.length === 1 ? 'it' : 'them'} New, but your Tablo decided ${list.length === 1 ? 'it isn’t' : 'they aren’t'}, so Record New skips ${list.length === 1 ? 'it' : 'them'}.</span>
      <span style="margin-left:auto;display:flex;gap:8px">
        <button class="btn btn-sm btn-primary" data-action="record-missed-new">Record ${list.length === 1 ? 'it' : 'all'}</button>
        ${compact ? '<a class="btn btn-sm" href="#/scheduled?view=upcoming">Review</a>' : ''}
      </span></div>
  </div>`;
}

async function recordMissedNew(paths) {
  let done = 0;
  for (const path of paths) {
    try {
      await api('/api/guide/episodes/schedule', { method: 'POST', body: JSON.stringify({ path, scheduled: true }) });
      done++;
    } catch (err) {
      toast(`Couldn't record it: ${err.message}`, 'error');
    }
  }
  if (done) toast(`Your Tablo will record ${plural(done, 'more episode')}`, 'success');
  await loadUpcoming();
  route();
}

// Conflict helper: for each recording in a conflict, other airings of the same episode to record instead
async function fixConflicts() {
  let data;
  try { data = await api('/api/guide/conflicts'); } catch (err) { toast(err.message, 'error'); return; }
  if (!data.conflicts.length) { toast('No recording conflicts right now', 'success'); return; }
  const when = iso => `${fmt.dayLabel(iso)} ${fmt.time(iso)}`;
  const body = data.conflicts.map(c => `
    <div class="fix-conflict">
      <h4>${esc(when(c.start))}–${esc(fmt.time(c.end))} · ${c.count} recordings, ${c.tuners} tuners</h4>
      ${c.recordings.map(r => {
        const se = fmt.se(r.season_number, r.episode_number);
        const alts = r.alternatives.length
          ? r.alternatives.map(a => `
              <div class="fix-alt">
                <span class="grow">${esc(when(a.air_datetime))} on ${esc(a.channel_call_sign || a.channel_network || '')}
                  ${a.resolves ? '<span class="tag tag-accent">Fixes it</span>' : '<span class="tag tag-warn" title="Recording this airing instead would still clash with something">Still busy then</span>'}</span>
                <button class="btn btn-sm ${a.resolves ? 'btn-primary' : ''}" data-action="swap-recording" data-skip="${esc(r.path)}" data-record="${esc(a.path)}">Record this one instead</button>
              </div>`).join('')
          : `<div class="fix-alt"><span class="grow dim">No other airing of this episode in the next two weeks.</span>
               <button class="btn btn-sm" data-action="skip-conflict" data-path="${esc(r.path)}" data-title="${esc(r.show_title)}">Don’t record</button></div>`;
        return `<div class="fix-rec">
          <div class="fix-rec-title">${esc(r.show_title)}${se ? ` <span class="dim">${esc(se)}</span>` : ''}${r.episode_title ? ` · ${esc(r.episode_title)}` : ''}</div>
          <div class="dim" style="font-size:12.5px">${esc(when(r.air_datetime))} on ${esc(r.channel_call_sign || '')}</div>
          ${alts}
        </div>`;
      }).join('')}
    </div>`).join('');
  openModal(`
    <div class="dialog-body scroll">
      <div class="dialog-title">Fix recording conflicts</div>
      <div class="dialog-text">Your Tablo can record ${data.tuners} shows at once. Move one of these to another airing of the same episode, or don’t record it.</div>
      ${body}
    </div>
    <div class="dialog-foot"><button class="btn" data-action="modal-ok">Done</button></div>`, { wide: true });
}

async function afterScheduleFix() {
  state.upcoming = null;
  closeModal(false);
  route();
  // Show what's left, if anything
  const left = await api('/api/guide/conflicts').catch(() => null);
  if (left && left.conflicts.length) fixConflicts();
  else toast('No more recording conflicts', 'success');
}

async function showWhatsNew() {
  try {
    const w = await api('/api/system/whatsnew');
    if (!w.show) return;
    await openModal(`
      <div class="dialog-body">
        <div class="dialog-title">What’s new in TabloView ${esc(w.version)}</div>
        <ul class="whatsnew-list">${w.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>
      </div>
      <div class="dialog-foot">
        <button class="btn btn-ghost" data-action="version-history">Earlier versions</button>
        <button class="btn btn-primary" data-action="modal-ok" data-autofocus>Got it</button>
      </div>`);
    api('/api/system/whatsnew/seen', { method: 'POST' }).catch(() => {});
  } catch { /* not important */ }
}

async function showVersionHistory() {
  try {
    const c = await api('/api/system/changelog');
    closeModal(false);
    await openModal(`
      <div class="dialog-body scroll">
        <div class="dialog-title">Version history</div>
        ${c.versions.map(v => `
          <h4 class="changelog-version">${esc(v.version)}${v.version === c.current ? ' <span class="tag tag-accent">You have this</span>' : ''}</h4>
          <ul class="whatsnew-list">${v.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>`).join('')}
      </div>
      <div class="dialog-foot"><button class="btn btn-primary" data-action="modal-ok" data-autofocus>Close</button></div>`, { wide: true });
  } catch (err) {
    toast(`Couldn't load the version history: ${err.message}`, 'error');
  }
}

function renderUpcomingList() {
  const box = $('#schedList');
  const u = state.upcoming;
  if (!box) return;
  if (!u) { box.innerHTML = errorState(new Error("Couldn't load upcoming recordings")); hydrateIcons(box); return; }
  if (!u.recordings.length) {
    box.innerHTML = emptyState('Nothing set to record', 'Choose Record on a show in the guide and its airings appear here.', '<a class="btn btn-primary" href="#/guide">Browse the guide</a>');
    return;
  }
  const byDay = {};
  u.recordings.forEach(a => { (byDay[fmt.dayLabel(a.air_datetime)] = byDay[fmt.dayLabel(a.air_datetime)] || []).push(a); });
  box.innerHTML = conflictBanner(u.conflicts) + missedNewBanner(missedNew(u)) + Object.entries(byDay).map(([day, list]) => `
    <div class="section-head" style="margin:22px 0 10px"><h2 class="section-title">${esc(day)}</h2><span class="section-sub">${plural(list.length, 'recording')}${list.some(a => a.wont_record || a.missed_new) ? ` · ${list.filter(a => a.wont_record || a.missed_new).length} won't record` : ''}</span></div>
    <div class="list">${list.map(upcomingRow).join('')}</div>`).join('');
  hydrateIcons(box);
}

// The Tablo marks a recording 'conflicted' when more overlap than it has tuners (the first scheduled wins)
const WONT_RECORD_TAG = `<span class="tag tag-rec" title="Your Tablo has no tuner free for this: more shows overlap than it has tuners, and the ones scheduled first win. Use Fix… to record another airing.">Won't record</span>`;

const MISSED_NEW_TAG = `<span class="tag tag-rec" title="The guide marks this episode New, but your Tablo decided it isn't, so the series' Record New rule skips it. Click Record to record it anyway.">Won't record</span>`;

// Logo, number and call sign, e.g. [NBC logo] 13.1 WTHR; the network's name when there's no logo
// Where a recording row leads: its antenna series, or for streaming recordings the show's airings
function rowOpen(a) {
  return a.streaming ? `data-action="fast-show" data-id="${esc(a.show_id)}"` : `data-action="open-series" data-path="${esc(a.series_path)}"`;
}

function channelCell(a) {
  const logo = a.channel_logo
    ? `<img class="ch-logo" src="${esc(a.channel_logo)}" alt="${esc(a.channel_network || '')}" title="${esc(a.channel_network || '')}" loading="lazy">`
    : `<span class="ch-logo">${esc(a.channel_network || '')}</span>`;
  return `${logo}<span class="ch-label">${a.channel_number ? `<b>${esc(a.channel_number)}</b> ` : ''}${esc(a.channel_call_sign || '')}</span>`;
}

function conflictTag(a) {
  return a.missed_new ? MISSED_NEW_TAG : a.wont_record ? WONT_RECORD_TAG : a.conflict ? '<span class="tag tag-warn">Conflict</span>' : '';
}

function upcomingRow(a) {
  const end = new Date(new Date(a.air_datetime).getTime() + (a.duration || 0) * 1000).toISOString();
  const onNow = new Date(a.air_datetime).getTime() <= Date.now() && !a.wont_record && !a.missed_new;
  const se = fmt.se(a.season_number, a.episode_number);
  const art = imgUrl(a.cover_url || a.backdrop_url);
  return `
    <div class="list-row upcoming-row clickable ${a.conflict ? 'conflict' : ''}" ${rowOpen(a)}>
      <div class="upnext-when">${onNow ? '<span class="tag tag-rec-live"><span class="rec-pulse"></span>REC</span>' : esc(fmt.time(a.air_datetime))}<span class="dim">until ${esc(fmt.time(end))}</span></div>
      ${art ? `<img class="thumb" src="${esc(art)}" alt="" loading="lazy">` : '<div class="thumb"></div>'}
      <div style="min-width:0">
        <div class="row-title">${esc(a.show_title)}</div>
        <div class="row-sub">${se ? `${se} · ` : ''}${esc(a.episode_title || '')}</div>
      </div>
      <div class="row-sub ch-cell">${channelCell(a)}</div>
      <div class="hero-kicker" style="margin:0;flex-wrap:nowrap">
        ${conflictTag(a)}${a.is_premiere ? '<span class="tag tag-premiere">PREMIERE</span>' : ''}${a.is_new ? '<span class="tag tag-new">NEW</span>' : ''}
      </div>
      ${a.missed_new ? `<button class="btn btn-sm btn-primary" data-action="record-missed-new" data-path="${esc(a.path)}">Record</button>`
        : onNow ? '<span></span>' : `<button class="btn btn-sm" data-action="cancel-recording" data-path="${esc(a.path)}" data-title="${esc(a.show_title)}" ${a.streaming ? 'data-streaming="1"' : ''}>Skip</button>`}
    </div>`;
}

function renderScheduledList() {
  const S = state.scheduled;
  const box = $('#schedList');
  if (!box || !S.items) return;
  const all = S.items;
  const counts = { all: all.length, new: all.filter(g => g.schedule_rule === 'new').length, every: all.filter(g => g.schedule_rule === 'all').length };
  const b = (value, label, n) => `<button data-action="scheduled-filter" data-value="${value}" class="${S.filter === value ? 'active' : ''}">${label} <span class="count">${n}</span></button>`;
  $('#schedFilters').innerHTML = b('all', 'All', counts.all) + b('new', 'New episodes', counts.new) + b('every', 'All episodes', counts.every);

  let items = all;
  if (S.filter === 'new') items = items.filter(g => g.schedule_rule === 'new');
  if (S.filter === 'every') items = items.filter(g => g.schedule_rule === 'all');
  const q = S.q.trim().toLowerCase();
  if (q) items = items.filter(g => g.title.toLowerCase().includes(q));

  if (!items.length) {
    box.innerHTML = all.length
      ? emptyState('Nothing matches', 'Try a different filter.')
      : emptyState('Nothing scheduled', 'Pick a series in the guide and choose Record.', '<a class="btn btn-primary" href="#/guide">Browse the guide</a>');
    return;
  }
  // Two groups: series with airings in the guide, then ones between seasons
  const upcoming = items.filter(g => g.next_airing);
  const waiting = items.filter(g => !g.next_airing);
  const group = (title, sub, list) => list.length ? `
    <div class="section-head" style="margin:${title === 'Upcoming' ? '0' : '28px'} 0 12px">
      <h2 class="section-title">${title}</h2><span class="section-sub">${plural(list.length, 'series', 'series')}${sub ? ` · ${sub}` : ''}</span>
    </div>
    <div class="list">${list.map(scheduledRow).join('')}</div>` : '';
  box.innerHTML = group('Upcoming', 'next airing in the guide', upcoming) +
    group('No upcoming airings', "the Tablo keeps these rules and records new episodes when they're in the guide", waiting);
}

function scheduledRow(g) {
  const genres = Array.isArray(g.genres) ? g.genres.slice(0, 2).join(', ') : '';
  const n = g.next_airing;
  return `
    <div class="list-row sched-row clickable" data-action="open-series" data-path="${esc(g.path)}">
      ${imgUrl(g.cover_url || g.backdrop_url) ? `<img class="thumb" src="${esc(imgUrl(g.cover_url || g.backdrop_url))}" alt="" loading="lazy">` : '<div class="thumb"></div>'}
      <div style="min-width:0"><div class="row-title">${esc(g.title)}</div><div class="row-sub">${esc(genres)}</div></div>
      <div class="sched-col-next" style="min-width:0">
        ${n ? `<div class="row-title" style="font-weight:500">${esc(fmt.when(n.datetime))}</div><div class="row-sub">${esc(n.title || '')}</div>` : '<span class="dim">Waiting for new episodes</span>'}
      </div>
      <div class="row-sub ch-cell">${n ? channelCell(n) : ''}</div>
      <div data-rule-control="${esc(g.path)}" class="segmented rule">
        <button data-action="set-rule" data-path="${esc(g.path)}" data-rule="new" class="${g.schedule_rule === 'new' ? 'active' : ''}">New</button>
        <button data-action="set-rule" data-path="${esc(g.path)}" data-rule="all" class="${g.schedule_rule === 'all' ? 'active' : ''}">All</button>
      </div>
      <button class="btn btn-sm btn-danger" data-action="stop-rule" data-path="${esc(g.path)}">Stop</button>
    </div>`;
}

// ---------------------------------------------------------------------------
// Live TV
// ---------------------------------------------------------------------------
const EPG = { CH_W: 232, PPM: 7, HOURS: 6 };
const EPG_CATS = [
  ['ota', 'Local'], ['fast', 'Streaming'], ['all', 'All'],
  ['news', 'News'], ['sports', 'Sports'], ['entertainment', 'Entertainment'],
];

PAGES.live = async (r, token) => {
  paint(`<div class="page full">
    <div class="live-bar">
      <div class="segmented" id="epgCats">${epgCatButtons()}</div>
      <div class="segmented">
        <button data-action="epg-shift" data-dir="-1" title="Earlier">${icon('back', 15)}</button>
        <button data-action="epg-now" class="${state.epgOffset === 0 ? 'active' : ''}">Now</button>
        <button data-action="epg-shift" data-dir="1" title="Later">${icon('next', 15)}</button>
      </div>
      <span class="muted" id="epgDate"></span>
      <div class="grow"></div>
      <div class="input-search live-search">${icon('search', 15)}<input class="input" data-input="epg-q" placeholder="Find a channel or show" value="${esc(state.epgQuery)}"></div>
      <span class="clock" id="epgClock"></span>
    </div>
    <div class="epg-scroll" id="epgScroll"><div class="loading-line" style="padding:28px"><span class="spinner"></span>Loading the channel guide…</div></div>
  </div>`);

  const tick = () => {
    const c = $('#epgClock');
    if (c) c.textContent = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    positionNowLine();
  };
  tick();
  pageTimers.push(setInterval(tick, 15000));
  pageTimers.push(setInterval(checkTuners, 15000));  // and straight after tuning or closing a channel
  checkTuners();
  await loadEpg(token, true);
};

// Favorites come from the Tablo (set in its TV apps); the filter only appears when there are some
// Home: what's airing now on your favorite channels (or antenna channels), one click to watch
function onNowCards() {
  if (!state.epg) return '';
  const fav = hasFavorites();
  const now = Date.now();
  const list = state.epg.channels.filter(c => (fav ? c.favorite : c.kind === 'ota') && nowNext(c, now).now).slice(0, 16);
  return list.map(c => {
    const { num, name } = channelName(c);
    const on = nowNext(c, now).now;
    const start = new Date(on.air_datetime).getTime();
    const end = start + (on.duration || 0) * 1000;
    const pct = on.duration ? Math.min(100, Math.round(((now - start) / (end - start)) * 100)) : 0;
    return `<button class="onnow-card" data-action="watch-live" data-id="${esc(c.channel_id)}" data-name="${esc(name)}" data-kind="${esc(c.kind)}" title="Watch ${esc(name)} live">
      <span class="onnow-ch">${c.logo_url ? `<img src="${esc(c.logo_url)}" alt="" loading="lazy">` : ''}<span>${num ? `<b>${esc(num)}</b> ` : ''}${esc(name)}</span></span>
      <span class="onnow-title">${esc(on.title)}</span>
      <span class="chan-bar"><span style="width:${pct}%"></span></span>
      <span class="onnow-sub">Until ${esc(fmt.time(new Date(end).toISOString()))}</span>
    </button>`;
  }).join('');
}

function hasFavorites() {
  return !!(state.epg && state.epg.channels.some(c => c.favorite));
}

function epgCatButtons() {
  const cats = hasFavorites() ? [['favorites', 'Favorites'], ...EPG_CATS] : EPG_CATS;
  return cats.map(([k, label]) => `<button data-action="epg-cat" data-value="${k}" class="${state.epgCategory === k ? 'active' : ''}">${label}</button>`).join('');
}

async function loadEpg(token, scrollToNow = false) {
  let startIso = '';
  if (state.epgOffset) {
    // Pages line up with the Now view (which starts at the half hour before now), so the column
    // times stay put however often the arrows are pressed
    const d = new Date();
    d.setMinutes(d.getMinutes() >= 30 ? 30 : 0, 0, 0);
    d.setMinutes(d.getMinutes() - 30 + state.epgOffset * 60);
    startIso = `&start_iso=${encodeURIComponent(d.toISOString())}`;
  }
  try {
    const res = await api(`/api/live/epg?hours=${EPG.HOURS}${startIso}`);
    if (token !== undefined && stale(token)) return;
    state.epg = res;
    if (state.epgCategory === 'favorites' && !hasFavorites()) state.epgCategory = 'ota';
    const cats = $('#epgCats');
    if (cats) cats.innerHTML = epgCatButtons();
    renderEpg(scrollToNow);
  } catch (err) {
    const el = $('#epgScroll');
    if (el) { el.innerHTML = `<div class="page">${errorState(err)}</div>`; hydrateIcons(el); }
  }
}

function epgFilter(c) {
  const cat = state.epgCategory;
  if (cat === 'favorites' && !c.favorite) return false;
  if (cat === 'ota' && c.kind !== 'ota') return false;
  if (cat === 'fast' && c.kind === 'ota') return false;
  const text = `${c.name} ${c.call_sign} ${c.network}`.toLowerCase();
  // Categories come from the server, based on the genres each channel actually airs
  if (['news', 'sports', 'entertainment'].includes(cat) && !(c.categories || []).includes(cat)) return false;
  const q = state.epgQuery;
  if (q) {
    const hit = text.includes(q) || (c.airings || []).some(a => `${a.title || ''} ${a.episode_title || ''}`.toLowerCase().includes(q));
    if (!hit) return false;
  }
  return true;
}

function channelName(c) {
  const num = c.major > 0 ? `${c.major}.${c.minor}` : '';
  let name = c.name || c.call_sign || '';
  if (num && name.startsWith(num)) name = name.slice(num.length).trim();
  return { num, name };
}

// What a channel is airing now, and next
function nowNext(c, now = Date.now()) {
  const list = c.airings || [];
  const i = list.findIndex(a => {
    const start = new Date(a.air_datetime).getTime();
    return start <= now && now < start + (a.duration || 0) * 1000;
  });
  return { now: list[i], next: i >= 0 ? list[i + 1] : list.find(a => new Date(a.air_datetime).getTime() > now) };
}

function renderEpg(scrollToNow = false) {
  const scroll = $('#epgScroll');
  if (!scroll || !state.epg) return;
  const { window_start, window_end, slots, channels } = state.epg;
  const ws = new Date(window_start).getTime();
  const we = new Date(window_end).getTime();
  const slotW = 30 * EPG.PPM;
  const trackW = slots.length * slotW;
  const now = Date.now();

  const dateEl = $('#epgDate');
  if (dateEl) dateEl.textContent = state.epgOffset ? `${fmt.dayLabel(window_start)} · ${fmt.time(window_start)}` : '';

  const list = channels.filter(epgFilter);
  if (!list.length) {
    scroll.innerHTML = emptyState('No channels match', 'Try another category or clear the search.');
    return;
  }

  state.epgItems = {};
  const rows = list.map((c, ci) => {
    const cells = (c.airings || []).map((a, ai) => {
      const start = new Date(a.air_datetime).getTime();
      const end = start + (a.duration || 0) * 1000;
      const s = Math.max(ws, start), e = Math.min(we, end);
      if (e <= s) return '';
      const key = `${ci}_${ai}`;
      state.epgItems[key] = { airing: a, channel: c };
      const left = Math.round(((s - ws) / 60000) * EPG.PPM);
      const width = Math.max(44, Math.round(((e - s) / 60000) * EPG.PPM) - 4);
      const onAir = start <= now && now < end;
      const se = fmt.se(a.season_number, a.episode_number);
      const rec = recordBadge(a, onAir);
      return `<div class="epg-cell ${onAir ? 'on-air' : ''} ${rec.cls}" style="left:${left + 2}px;width:${width}px" data-left="${left}" data-width="${width}" data-action="epg-cell" data-key="${key}" title="${esc(a.title)}${rec.title}">
        <div class="epg-cell-inner">
          <div class="epg-cell-title">${esc(a.title)}</div>
          <div class="epg-cell-sub">${rec.html}${a.is_new ? '<span class="tag tag-new">NEW</span>' : ''}${a.is_premiere ? '<span class="tag tag-premiere">PREMIERE</span>' : ''}<span>${esc(fmt.time(a.air_datetime))}${se ? ` · ${se}` : ''}${a.episode_title ? ` · ${esc(a.episode_title)}` : ''}</span></div>
        </div>
      </div>`;
    }).join('');

    const { num, name } = channelName(c);
    const sub = [c.network && c.network.toLowerCase() !== name.toLowerCase() ? c.network : '', c.resolution].filter(Boolean).join(' · ');
    return `<div class="epg-row">
      <div class="epg-ch" style="width:${EPG.CH_W}px" data-action="watch-live" data-id="${esc(c.channel_id)}" data-name="${esc(name)}" data-kind="${esc(c.kind)}" title="Watch ${esc(name)} live">
        ${c.logo_url ? `<img class="epg-ch-logo" src="${esc(c.logo_url)}" alt="" loading="lazy">` : `<div class="epg-ch-logo-fallback">${esc((c.call_sign || 'TV').slice(0, 6))}</div>`}
        <div class="epg-ch-info"><div class="epg-ch-num">${num ? `<b>${esc(num)}</b>` : ''}${esc(name)}${c.favorite ? `<span class="epg-fav" title="Favorite">${icon('star', 11)}</span>` : ''}</div>${sub ? `<div class="epg-ch-sub">${esc(sub)}</div>` : ''}</div>
        <span class="icon-btn play">${icon('play', 12)}</span>
      </div>
      <div class="epg-track" style="width:${trackW}px">${cells}</div>
    </div>`;
  }).join('');

  const head = `<div class="epg-head"><div class="epg-head-ch" style="width:${EPG.CH_W}px"></div>${slots.map(s => `<div class="epg-slot" style="width:${slotW}px">${esc(fmt.time(s.iso))}</div>`).join('')}</div>`;
  scroll.innerHTML = `<div class="epg-board" id="epgBoard">${head}${rows}<div class="epg-now hidden" id="epgNow"></div></div>`;
  hydrateIcons(scroll);
  positionNowLine();

  if (!scroll.dataset.bound) {
    scroll.dataset.bound = '1';
    let ticking = false;
    scroll.addEventListener('scroll', () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => { stickEpgTitles(); ticking = false; });
    }, { passive: true });
  }
  if (scrollToNow) {
    const nowLeft = ((Date.now() - ws) / 60000) * EPG.PPM;
    scroll.scrollLeft = Math.max(0, nowLeft - 120);
  }
  stickEpgTitles();
}

// Recording badges: "REC" while a tuner is recording it right now, "Rec" for airings set to record
function recordBadge(a, onAir) {
  if (a.recording_now) {
    return { cls: 'recording', title: ' (recording now)', html: '<span class="tag tag-rec-live"><span class="rec-pulse"></span>REC</span>' };
  }
  if (a.schedule_state === 'scheduled' && !onAir) {
    return { cls: 'scheduled', title: ' (set to record)', html: '<span class="tag tag-rec-sched">● Rec</span>' };
  }
  return { cls: '', title: '', html: '' };
}

function positionNowLine() {
  const line = $('#epgNow');
  if (!line || !state.epg) return;
  const ws = new Date(state.epg.window_start).getTime();
  const we = new Date(state.epg.window_end).getTime();
  const now = Date.now();
  if (now < ws || now > we) { line.classList.add('hidden'); return; }
  line.classList.remove('hidden');
  line.style.left = `${EPG.CH_W + Math.round(((now - ws) / 60000) * EPG.PPM)}px`;
}

// Keep program titles visible when a long program starts left of the viewport
function stickEpgTitles() {
  const scroll = $('#epgScroll');
  if (!scroll) return;
  const x = scroll.scrollLeft;
  scroll.querySelectorAll('.epg-cell').forEach(cell => {
    const left = +cell.dataset.left, width = +cell.dataset.width;
    const inner = cell.firstElementChild;
    if (x > left && x < left + width - 60) inner.style.transform = `translateX(${Math.min(x - left, width - 80)}px)`;
    else if (inner.style.transform) inner.style.transform = '';
  });
}

async function checkTuners() {
  try {
    const t = await api('/api/live/tuners');
    state.tuners = t;
    const pill = $('#tunerPill'), text = $('#tunerText');
    if (!pill) return;
    pill.classList.remove('hidden');
    if (!$('#tunerPanel').classList.contains('hidden')) renderTunerPanel();
    const total = t.total || 0, used = t.in_use || 0, held = t.held || 0, rec = t.recording || 0;
    const streams = t.streams_in_use || 0, streamsTotal = t.streams_total || 0;
    pill.classList.toggle('busy', used > 0 || streams > 0);
    pill.classList.toggle('down', !total);
    if (!total) {
      text.textContent = t.unreachable ? 'Tablo not responding' : 'Tuners unavailable';
      pill.title = t.unreachable
        ? "TabloView can't reach your Tablo right now. This usually clears up on its own: wait a minute."
        : "Couldn't read tuner status from the Tablo";
      return;
    }
    text.textContent = `Tuners ${used}/${total}` + (rec ? ` · ${rec} recording` : '');
    pill.title = 'What your Tablo’s tuners are doing';
  } catch { /* optional */ }
}

// The header's tuner list: what each antenna tuner is doing right now
function renderTunerPanel() {
  const t = state.tuners;
  const box = $('#tunerPanel');
  if (!t || !t.total) {
    box.innerHTML = `<div class="tuner-row"><span class="dim">${t && t.unreachable ? 'TabloView can’t reach your Tablo right now. This usually clears up on its own: wait a minute.' : 'Couldn’t read the tuners from your Tablo.'}</span></div>`;
    return;
  }
  const what = s => {
    const ch = s.channel || {};
    const chName = [ch.number, ch.call_sign].filter(Boolean).join(' ');
    const on = s.on_now ? [s.on_now.show_title, s.on_now.episode_title && s.on_now.episode_title !== s.on_now.show_title ? s.on_now.episode_title : ''].filter(Boolean).join(' · ') : '';
    if (s.state === 'recording') return `<span class="tuner-state rec"><span class="rec-pulse"></span>Recording</span><span class="tuner-what"><b>${esc(on || chName || 'a show')}</b>${on && chName ? `<span class="dim">${esc(chName)}</span>` : ''}</span>`;
    if (s.state === 'watching') return `<span class="tuner-state live">Watching</span><span class="tuner-what"><b>${esc(chName || 'Live TV')}</b><span class="dim">${esc(s.closing ? 'Closed in TabloView; your Tablo lets go of it shortly' : [on, s.tabloview ? 'in TabloView' : 'in another app'].filter(Boolean).join(' · '))}</span></span>`;
    if (s.state === 'releasing') return `<span class="tuner-state held">Releasing</span><span class="tuner-what"><span class="dim">From live TV closed recently. Your Tablo frees it on its own, usually within 10–30 minutes.</span></span>`;
    return '<span class="tuner-state free">Free</span><span class="tuner-what"></span>';
  };
  box.innerHTML = `
    <div class="tuner-head">Antenna tuners <span class="dim">${t.in_use} of ${t.total} in use</span></div>
    ${(t.slots || []).map(s => `<div class="tuner-row"><span class="tuner-num">${s.tuner}</span>${what(s)}</div>`).join('')}
    ${t.streams_total ? `<div class="tuner-foot dim">Streaming channels: ${t.streams_in_use} of ${t.streams_total} in use (these don’t use the antenna tuners)</div>` : ''}`;
}

function toggleTunerPanel(show) {
  const box = $('#tunerPanel');
  const open = show ?? box.classList.contains('hidden');
  box.classList.toggle('hidden', !open);
  if (open) { renderTunerPanel(); checkTuners(); }
}

function openAiringModal(key) {
  const item = state.epgItems[key];
  if (!item) return;
  const { airing: a, channel: c } = item;
  const end = new Date(new Date(a.air_datetime).getTime() + (a.duration || 0) * 1000).toISOString();
  const se = fmt.se(a.season_number, a.episode_number);
  const onAir = new Date(a.air_datetime).getTime() <= Date.now() && Date.now() < new Date(end).getTime();
  openModal(`
    <div class="dialog-body">
      <div class="airing-modal-head">
        ${c.logo_url ? `<img src="${esc(c.logo_url)}" alt="">` : ''}
        <div><div style="font-weight:600">${esc(c.name)}</div><div class="dim" style="font-size:12.5px">${esc([c.network, c.resolution].filter(Boolean).join(' · '))}</div></div>
      </div>
      <div class="dialog-title">${esc(a.title || c.name)}</div>
      ${a.episode_title || se ? `<div style="margin-top:4px;font-weight:500">${se ? `<span class="dim">${se}</span> ` : ''}${esc(a.episode_title || '')}</div>` : ''}
      <div class="hero-kicker" style="margin-top:12px">
        ${onAir ? '<span class="tag tag-live">ON NOW</span>' : ''}
        ${a.recording_now ? '<span class="tag tag-rec-live"><span class="rec-pulse"></span>RECORDING NOW</span>' : (a.schedule_state === 'scheduled' ? '<span class="tag tag-rec-sched">● Set to record</span>' : '')}
        <span class="tag">${esc(fmt.dayLabel(a.air_datetime))} ${esc(fmt.time(a.air_datetime))}–${esc(fmt.time(end))}</span>
        <span class="tag">${esc(fmt.dur(a.duration))}</span>
        ${a.is_new ? '<span class="tag tag-new">NEW</span>' : ''}${a.is_premiere ? '<span class="tag tag-premiere">PREMIERE</span>' : ''}
      </div>
      ${a.description ? `<p class="dialog-text">${esc(a.description)}</p>` : ''}
    </div>
    <div class="dialog-foot">
      ${a.series_path ? `<button class="btn" data-action="modal-series" data-path="${esc(a.series_path)}">Series &amp; recording</button>` : ''}
      ${a.airing_id && c.can_record && Date.now() < new Date(end).getTime()
        ? (a.schedule_state === 'scheduled' || a.recording_now
          ? `<button class="btn rec-set" data-action="fast-record" data-id="${esc(a.airing_id)}" data-key="${esc(key)}" data-on="0" title="Your Tablo will record this. Click to cancel.">${icon('check', 14)}Recording</button>`
          : `<button class="btn" data-action="fast-record" data-id="${esc(a.airing_id)}" data-key="${esc(key)}" data-on="1" title="Record this on your Tablo">${onAir ? 'Record from now' : 'Record'}</button>`)
        : ''}
      <button class="btn" data-action="modal-live-vlc" data-id="${esc(c.channel_id)}">${icon('external', 15)}VLC</button>
      <button class="btn btn-primary" data-action="modal-watch-live" data-id="${esc(c.channel_id)}" data-name="${esc(c.name)}" data-kind="${esc(c.kind)}" data-autofocus>${icon('play', 14)}Watch ${esc(c.name)}</button>
    </div>`);
}

// ---------------------------------------------------------------------------
// Downloads
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Antenna helper: the picture quality meter on its own page, made to be used on a phone at the
// antenna. One channel is measured without video (light on the PC), with a big readout and an
// optional tone that rises as reception improves; "Check all channels" gives a scorecard per antenna
// position, and positions can be saved on this device to compare.
// ---------------------------------------------------------------------------
const ANT_SPOTS_KEY = 'tabloview.antennaSpots';
const ANT_SCAN_SECONDS = 20;

const antenna = {
  sessionId: null, channel: null, data: null, timer: null, starting: false,
  scan: null,  // { list, index, results, cancelled }
  tone: { on: false, ctx: null, timer: null },

  channels() {
    return ((state.epg && state.epg.channels) || []).filter(c => c.kind === 'ota');
  },

  label(c) {
    const { num, name } = channelName(c);
    return num ? `${num} ${name}` : name;
  },

  async start(c, { quiet = false } = {}) {
    await this.stop();
    if (!quiet && !(await tunerOk('ota', this.label(c)))) return false;
    this.starting = true;
    this.channel = c;
    this.data = null;
    this.noPickup = false;
    this.render();
    try {
      const res = await api('/api/live/measure', { method: 'POST', body: JSON.stringify({ channel_id: c.channel_id }) });
      this.sessionId = res.session_id;
    } catch (err) {
      this.starting = false;
      this.lastStatus = err.status;
      // 502: a tuner was free but the Tablo couldn't tune the station, so as far as aiming goes: no signal
      this.noPickup = err.status === 502;
      if (!this.noPickup) this.channel = null;
      if (!quiet) toast(this.noPickup ? err.message : `Couldn't tune ${this.label(c)}: ${err.message}`, 'error');
      this.render();
      return false;
    }
    this.starting = false;
    this.timer = setInterval(() => this.poll(), 1000);
    this.poll();
    return true;
  },

  // Resolves once the backend has the stop (the next channel waits for it)
  stop({ keepalive = false } = {}) {
    clearInterval(this.timer);
    this.timer = null;
    const id = this.sessionId;
    this.sessionId = null;
    this.data = null;
    if (!this.scan) { this.channel = null; this.noPickup = false; }
    this.render();
    if (!id) return Promise.resolve();
    return fetch('/api/live/stop', { method: 'POST', headers: API_HEADERS, body: JSON.stringify({ session_id: id }), keepalive })
      .catch(() => {});
  },

  async poll() {
    const id = this.sessionId;
    if (!id) return;
    let d;
    try { d = await api(`/api/live/reception/${id}`); } catch { return; }
    if (id !== this.sessionId || !d.available) return;
    this.data = d;
    this.render();
    this.beepFor(d);
  },

  // --- Tone: short beeps whose pitch rises with the score, so the antenna can be turned without looking
  toggleTone() {
    this.tone.on = !this.tone.on;
    if (this.tone.on) {
      try {
        this.tone.ctx = this.tone.ctx || new (window.AudioContext || window.webkitAudioContext)();
        this.tone.ctx.resume();
      } catch { this.tone.on = false; toast("This browser can't play the tone", 'error'); }
    }
    this.render();
  },

  beepFor(d) {
    const ctx = this.tone.ctx;
    if (!this.tone.on || !ctx || d.score == null) return;
    const lost = d.state === 'no_signal';
    // Three beeps a second: 220 Hz at 0% up to 1,320 Hz at 100%; a low buzz for no signal
    for (let i = 0; i < 3; i++) {
      const t = ctx.currentTime + i * 0.33;
      const osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.type = lost ? 'sawtooth' : 'sine';
      osc.frequency.value = lost ? 110 : 220 + d.score * 11;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.25, t + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + (lost ? 0.3 : 0.12));
      osc.connect(gain).connect(ctx.destination);
      osc.start(t);
      osc.stop(t + 0.32);
    }
  },

  // The Tablo keeps a tuner busy for 10-45 minutes after a channel is closed, so checking channel after
  // channel uses them up (3 held after a few checks on a 4-tuner Tablo). Wait for one to free up.
  async waitForTuner() {
    for (;;) {
      if (!this.scan || this.scan.cancelled) return false;
      let t = null;
      try { t = await api('/api/live/tuners'); } catch { /* try anyway */ }
      if (!t || !t.total || t.available > 0) {
        if (this.scan) this.scan.waiting = null;
        return true;
      }
      if (!this.scan.waiting) this.scan.waiting = { since: Date.now() };
      this.scan.waiting.held = t.held || 0;
      this.scan.waiting.total = t.total;
      this.renderScan();
      for (let s = 0; s < 15 && this.scan && !this.scan.cancelled; s++) await new Promise(r => setTimeout(r, 1000));
    }
  },

  // --- Check all channels: ANT_SCAN_SECONDS each, one tuner at a time
  async checkAll() {
    const list = this.channels();
    if (!list.length) return;
    if (!(await tunerOk('ota', 'each antenna channel in turn'))) return;
    let tuners = null;
    try { tuners = await api('/api/live/tuners'); } catch { /* not important */ }
    if (tuners && tuners.total && tuners.total <= 2 && list.length > tuners.available) {
      const go = await confirmDialog({
        title: 'This may take a while',
        text: `Your Tablo has ${tuners.total} tuners, and it keeps each one busy for 10–45 minutes after a channel is checked. So after every ${tuners.total === 1 ? 'channel' : 'couple of channels'} the check waits for a tuner to free up. You can leave it running, or check one channel at a time with Start instead.`,
        confirm: 'Check all channels',
      });
      if (!go) return;
    }
    this.scan = { list, index: 0, results: {}, cancelled: false, waiting: null };
    for (let i = 0; i < list.length && !this.scan.cancelled; i++) {
      this.scan.index = i;
      const c = list[i];
      if (!(await this.waitForTuner())) break;
      let ok = await this.start(c, { quiet: true });
      if (!ok && this.lastStatus === 409 && (await this.waitForTuner())) ok = await this.start(c, { quiet: true });
      const scores = [];
      for (let s = 0; s < ANT_SCAN_SECONDS && this.scan && !this.scan.cancelled; s++) {
        await new Promise(r => setTimeout(r, 1000));
        this.renderScan();
      }
      if (!this.scan || this.scan.cancelled) break;
      for (const [, sc] of (this.data && this.data.history) || []) scores.push(sc);
      this.scan.results[c.channel_id] = {
        name: this.label(c),
        score: ok && scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0,
        worst: ok && scores.length ? Math.round(Math.min(...scores)) : 0,
        failed: !ok || !scores.length,
        noPickup: !ok && this.noPickup,
      };
      this.renderScan();
    }
    const done = this.scan && !this.scan.cancelled;
    const results = this.scan ? this.scan.results : {};
    this.scan = null;
    await this.stop();
    this.lastScan = done ? results : null;
    this.render();
  },

  cancelScan() {
    if (this.scan) this.scan.cancelled = true;
  },

  // --- Saved antenna positions (this device only: it's where you stand with the antenna)
  spots() {
    try { return JSON.parse(localStorage.getItem(ANT_SPOTS_KEY) || '[]'); } catch { return []; }
  },

  saveSpots(spots) {
    try { localStorage.setItem(ANT_SPOTS_KEY, JSON.stringify(spots.slice(-8))); } catch { /* private window */ }
  },

  saveSpot() {
    if (!this.lastScan) return;
    const input = $('#antSpotName');
    const spots = this.spots();
    const name = (input && input.value.trim()) || `Position ${spots.length + 1}`;
    spots.push({ name, at: new Date().toISOString(), results: this.lastScan });
    this.saveSpots(spots);
    this.lastScan = null;
    toast(`Saved “${name}”`, 'success');
    this.render();
  },

  deleteSpot(i) {
    const spots = this.spots();
    spots.splice(i, 1);
    this.saveSpots(spots);
    this.render();
  },

  // --- Drawing
  render() {
    const big = $('#antBig');
    if (!big) return;
    const d = this.data;
    const state_ = this.starting || (this.sessionId && (!d || d.score == null)) ? 'starting'
      : d ? d.state : this.noPickup ? 'no_signal' : 'idle';
    const score = d && d.score != null ? (d.state === 'no_signal' ? 'No signal' : `${d.score}%`)
      : this.noPickup ? 'No signal' : '';
    const LABELS = { clean: 'Clean picture', minor: 'Minor glitches', breaking: 'Breaking up', losing: 'Losing signal',
                     no_signal: this.noPickup ? "The Tablo can't pick up this channel" : 'Nothing is arriving',
                     starting: 'Tuning and measuring…', idle: 'Pick a channel and press Start' };
    big.className = `ant-big q-${state_}`;
    const hist = (d && d.history) || [];
    const recent = hist.filter(([ago]) => ago >= -60);
    const pts = recent.map(([ago, s]) => `${((60 + ago) / 60 * 300).toFixed(1)},${(58 - s * 0.56).toFixed(1)}`).join(' ');
    big.innerHTML = `
      <div class="ant-chan">${this.channel ? esc(this.label(this.channel)) : 'Antenna helper'}</div>
      <div class="ant-score">${esc(score) || (state_ === 'starting' ? '…' : '—')}</div>
      <div class="ant-label">${esc(LABELS[state_] || '')}</div>
      ${d && d.worst ? `<div class="ant-worst">Worst in the last 5 min: ${d.worst.score}% · ${plural(d.dropouts, 'dropout')}</div>` : ''}
      ${pts ? `<svg class="ant-spark" viewBox="0 0 300 60" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round"/></svg>
        <div class="ant-spark-axis"><span>1 min ago</span><span>now</span></div>` : ''}`;
    const go = $('#antGo');
    if (go) {
      go.textContent = this.sessionId || this.starting ? 'Stop' : 'Start';
      go.classList.toggle('btn-primary', !(this.sessionId || this.starting));
      go.disabled = !!this.scan;
    }
    const sel = $('#antChannel');
    if (sel) sel.disabled = !!this.scan;
    const tone = $('#antTone');
    if (tone) { tone.classList.toggle('active', this.tone.on); tone.textContent = this.tone.on ? 'Tone on' : 'Tone off'; }
    const all = $('#antAll');
    if (all) { all.textContent = this.scan ? 'Cancel check' : 'Check all channels'; }
    this.renderScan();
    this.renderSpots();
  },

  renderScan() {
    const box = $('#antScan');
    if (!box) return;
    const sc = this.scan;
    const results = sc ? sc.results : this.lastScan;
    if (!results) { box.innerHTML = ''; return; }
    const list = sc ? sc.list : this.channels().filter(c => results[c.channel_id]);
    const rows = list.map((c, i) => {
      const r = results[c.channel_id];
      const now = sc && i === sc.index && !r;
      const cls = r ? (r.failed ? 'q-no_signal' : `q-${state_for(r.score)}`) : '';
      return `<tr class="${cls}"><td>${esc(this.label(c))}</td>
        <td class="num">${r ? (r.noPickup ? 'No signal' : r.failed ? 'Couldn’t measure' : `${r.score}%`) : now ? '<span class="spinner"></span>' : ''}</td>
        <td class="num dim">${r && !r.failed ? `worst ${r.worst}%` : ''}</td></tr>`;
    }).join('');
    box.innerHTML = `
      <div class="panel">
        <h3>${sc ? (sc.waiting ? `Waiting for a free tuner to check ${esc(this.label(sc.list[sc.index]))} (${sc.index + 1} of ${sc.list.length})…`
                               : `Checking ${esc(this.label(sc.list[sc.index]))} (${sc.index + 1} of ${sc.list.length})…`) : 'This position'}</h3>
        <div class="panel-sub">${sc ? (sc.waiting
            ? `All ${sc.waiting.total} tuners are busy${sc.waiting.held ? ` (${sc.waiting.held} still held by the Tablo from channels just checked)` : ''}. The Tablo frees them on its own, usually within 10–45 minutes; the check carries on by itself. Waiting ${Math.round((Date.now() - sc.waiting.since) / 60000)} min so far.`
            : `About ${ANT_SCAN_SECONDS} seconds per channel. Leave the antenna still.`) : 'Average picture quality per channel while it was checked.'}</div>
        <table class="ant-table">${rows}</table>
        ${!sc ? `<div class="ant-save"><input class="input" id="antSpotName" placeholder="Name this position, e.g. Attic, facing north">
          <button class="btn btn-primary" data-action="ant-save">Save</button></div>` : ''}
      </div>`;
  },

  renderSpots() {
    const box = $('#antSpots');
    if (!box) return;
    const spots = this.spots();
    if (!spots.length) { box.innerHTML = ''; return; }
    const ids = [];
    const names = {};
    for (const s of spots) for (const [id, r] of Object.entries(s.results)) { if (!names[id]) { ids.push(id); names[id] = r.name; } }
    const rows = ids.map(id => {
      const scores = spots.map(s => s.results[id] && !s.results[id].failed ? s.results[id].score : null);
      const best = Math.max(...scores.map(x => x == null ? -1 : x));
      return `<tr><td>${esc(names[id])}</td>${scores.map(x => `<td class="num ${x != null && x === best && spots.length > 1 ? 'best' : ''} ${x == null ? 'dim' : `q-${state_for(x)}`}">${x == null ? '—' : `${x}%`}</td>`).join('')}</tr>`;
    }).join('');
    box.innerHTML = `
      <div class="panel">
        <h3>Saved positions</h3><div class="panel-sub">Kept on this device. The best position for each channel is highlighted.</div>
        <div class="ant-table-wrap"><table class="ant-table">
          <tr><th></th>${spots.map((s, i) => `<th>${esc(s.name)}<button class="link-btn" data-action="ant-delete" data-index="${i}" title="Remove">${icon('x', 12)}</button></th>`).join('')}</tr>
          ${rows}
        </table></div>
      </div>`;
    hydrateIcons(box);
  },
};

function state_for(score) {
  return score >= 99 ? 'clean' : score >= 90 ? 'minor' : score >= 50 ? 'breaking' : score > 0 ? 'losing' : 'no_signal';
}

PAGES.antenna = async (r, token) => {
  paint(`<div class="page ant-page">
    <div class="page-head">
      <div><h1 class="page-title">Antenna helper</h1>
        <div class="page-sub">Live picture quality from your Tablo while you adjust your antenna. Open TabloView on your phone and take it with you.</div></div>
    </div>
    <div class="ant-controls">
      <select class="select" id="antChannel" data-change="ant-channel"><option>Loading channels…</option></select>
      <button class="btn btn-primary" id="antGo" data-action="ant-go">Start</button>
      <button class="btn" id="antTone" data-action="ant-tone" title="Beeps that rise in pitch as reception improves">Tone off</button>
      <button class="btn" id="antAll" data-action="ant-all" title="Measure every antenna channel for about ${ANT_SCAN_SECONDS} seconds each">Check all channels</button>
    </div>
    <div class="ant-big q-idle" id="antBig"></div>
    <div id="antScan"></div>
    <div id="antSpots"></div>
    <p class="dim ant-note">How it works: TabloView watches the channel through your Tablo and counts the parts of the picture that arrive damaged or not at all. 100% means a perfect picture right now. Digital TV is all or nothing, though: a channel can show 100% while only just strong enough, so a channel that dips now and then needs attention even if it's usually at 100%. It uses one of your Tablo's tuners while it measures.</p>
  </div>`);
  pageLeave.push(() => { antenna.cancelScan(); antenna.stop(); });
  antenna.render();
  await player.ensureEpg();
  if (stale(token)) return;
  const sel = $('#antChannel');
  const list = antenna.channels();
  sel.innerHTML = list.length ? list.map(c => `<option value="${esc(c.channel_id)}">${esc(antenna.label(c))}</option>`).join('')
    : '<option>No antenna channels</option>';
  if (antenna.channel) sel.value = antenna.channel.channel_id;
};

PAGES.downloads = async (r, token) => {
  paint(`<div class="page">
    <div class="page-head"><div><h1 class="page-title">Downloads</h1><div class="page-sub">MP4 exports saved to this computer (choose the folder under <a href="#/device?tab=storage">Device → Storage → Exports</a>)</div></div></div>
    <div id="dlList"><div class="list"><div class="loading-line"><span class="spinner"></span>Loading…</div></div></div>
  </div>`);
  const refresh = async () => {
    const { jobs } = await api('/api/exports');
    if (stale(token)) return;
    setActiveExports(jobs.filter(j => j.status === 'downloading' || j.status === 'pending').length);
    renderDownloads(jobs);
  };
  await refresh();
  pageTimers.push(setInterval(() => refresh().catch(() => {}), 3000));
};

function renderDownloads(jobs) {
  const box = $('#dlList');
  if (!box) return;
  if (!jobs.length) {
    box.innerHTML = emptyState('No exports', 'Use “Export MP4” from an episode’s ⋯ menu to save a recording to this computer.');
    return;
  }
  box.innerHTML = `<div class="list">${jobs.map(j => {
    const pct = Math.round(j.progress || 0);
    return `<div class="list-row dl-row">
      <div style="min-width:0"><div class="row-title">${esc(j.filename)}</div><div class="row-sub">${esc(fmt.bytes(j.file_size))}${j.created_at ? ` · started ${esc(fmt.ago(j.created_at))}` : ''}${j.error ? ` · ${esc(j.error.slice(-140))}` : ''}</div></div>
      <div>${j.status === 'downloading' ? `<div class="progress"><div style="width:${pct}%"></div></div><div class="row-sub" style="margin-top:4px">${pct}%</div>` : ''}</div>
      <span class="status-text ${esc(j.status)}">${esc({ downloading: 'Exporting', pending: 'Waiting' }[j.status] || j.status)}</span>
      <div>${j.status === 'completed' ? `<a class="btn btn-sm" href="/downloads/${encodeURIComponent(j.filename)}" download>${icon('download', 15)}Save</a>`
        : ['downloading', 'pending'].includes(j.status) ? `<button class="btn btn-sm" data-action="export-cancel" data-id="${esc(j.job_id)}" data-name="${esc(j.filename)}">Cancel</button>`
        : `<button class="btn btn-sm btn-ghost" data-action="export-remove" data-id="${esc(j.job_id)}" title="Remove from this list">${icon('x', 14)}</button>`}</div>
    </div>`;
  }).join('')}</div>`;
}

// ---------------------------------------------------------------------------
// Device
// ---------------------------------------------------------------------------
PAGES.device = async (r, token) => {
  const [, , info, settings, space, boot, playback, signal] = await Promise.all([
    loadStatus(), loadStorage(),
    api('/api/system/info').catch(() => ({})),
    api('/api/settings').catch(() => ({})),
    api('/api/storage/shows').catch(() => null),
    api('/api/system/startup').catch(() => ({})),
    api('/api/system/playback').catch(() => ({})),
    api('/api/system/signal').catch(() => null),
  ]);
  if (stale(token)) return;
  const st = state.status || {};
  const dev = st.active_device;
  const storage = state.storage || {};

  const network = `
    <div class="panel">
      <h3>Network access</h3><div class="panel-sub">Let phones, tablets and other computers on your home network open TabloView.</div>
      ${info.packaged ? `
        <label class="switch-row">
          <input type="checkbox" class="switch" data-change="allow-lan" ${settings.allow_lan ? 'checked' : ''}>
          <span>Allow other devices on my network</span>
        </label>
        <p class="dim" style="margin-top:10px;font-size:12.5px">Other devices sign in with a PIN; this PC never asks for it. Leave this off on shared or public networks.</p>
        ${settings.allow_lan && !info.lan_pin_set ? '<p style="margin-top:10px;color:var(--warn);font-size:13px;font-weight:600">Set a PIN: other devices can’t use TabloView until you do.</p>' : ''}
        <div class="panel-actions">
          <button class="btn btn-sm" data-action="set-pin">${info.lan_pin_set ? 'Change PIN' : 'Set PIN'}</button>
          ${info.lan_pin_set ? '<button class="btn btn-sm btn-ghost" data-action="pin-signout">Sign out other devices</button>' : ''}
        </div>`
      : '<p class="dim" style="font-size:13px">Running from source: network access follows the <code>--host</code> option in the start command.</p>'}
      ${info.listening_on_network && info.network_url ? `<p style="margin-top:12px">On other devices, open <b>${esc(info.network_url)}</b></p>` : ''}
    </div>`;

  // Run from a start script (Mac, Linux, or from source): no tray icon, so stop it from here
  const desktop = !info.packaged ? `
    <div class="panel">
      <h3>Running TabloView</h3><div class="panel-sub">TabloView runs in the window you started it from. Closing the browser doesn't stop it.</div>
      ${info.this_computer
        ? '<button class="btn btn-danger btn-sm" data-action="stop-app">Stop TabloView</button>'
        : '<p class="dim" style="font-size:13px">It can be stopped on the computer running it.</p>'}
      <p class="dim" style="margin-top:10px;font-size:12.5px">To start it again, run its start script as before (start-mac.sh on a Mac, start-linux.sh on Linux).</p>
    </div>` : `
    <div class="panel">
      <h3>Desktop app</h3><div class="panel-sub">Run TabloView in the background so it can let you know when something needs attention.</div>
      ${boot.supported ? `
        <label class="switch-row">
          <input type="checkbox" class="switch" data-change="startup" ${boot.enabled ? 'checked' : ''} ${boot.locked ? 'disabled' : ''}>
          <span>Start TabloView when I sign in to Windows</span>
        </label>
        <p class="dim" style="margin-top:6px;font-size:12.5px">${boot.locked
          ? 'This was turned off in Task Manager. To turn it back on, open Task Manager → Startup apps and enable TabloView for TabloTV.'
          : 'It starts quietly in the system tray; your browser opens only when you click the tray icon.'}</p>`
      : '<p class="dim" style="font-size:13px">Starting with Windows is available in the installed app.</p>'}
      ${boot.notifications_available ? `
        <label class="switch-row" style="margin-top:14px">
          <input type="checkbox" class="switch" data-change="notifications" ${settings.notifications !== false ? 'checked' : ''}>
          <span>Notify me about recording problems and conflicts</span>
        </label>
        <p class="dim" style="margin-top:6px;font-size:12.5px">A Windows notification when a recording fails or stops early, or when more shows are set to record at once than you have tuners (in the next 2 days). Each one is shown once.</p>`
      : '<p class="dim" style="margin-top:10px;font-size:13px">Notifications are available in the installed app.</p>'}
    </div>`;

  const aboutHead = `TabloView ${esc(info.version || '')}${info.packaged ? '' : ' (running from source)'} · <a href="#" data-action="version-history">Version history</a>`;
  const aboutList = `
      <dl class="kv">
        <dt>Updates</dt><dd>${updateStatusHtml()}</dd>
        <dt>Playback engine</dt><dd>${info.ffmpeg_found ? 'FFmpeg ready' : '<span style="color:var(--warn)">FFmpeg not found: in-browser playback and MP4 export won’t work. VLC still works.</span>'}</dd>
        <dt>App data</dt><dd>${esc(info.data_dir || '')}</dd>
      </dl>`;

  const connection = st.authenticated && dev ? `
    <div class="panel">
      <h3>Tablo</h3><div class="panel-sub">Connected</div>
      <dl class="kv">
        <dt>Name</dt><dd>${esc(dev.name)}</dd>
        <dt>Address</dt><dd>${esc(dev.local_url)}</dd>
        <dt>Device ID</dt><dd>${esc(dev.sid)}</dd>
        <dt>Account</dt><dd>${esc(st.email || '')}</dd>
      </dl>
      ${(st.devices || []).length > 1 ? `<div class="panel-actions"><select class="select" data-change="select-device">${st.devices.map(d => `<option value="${esc(d.sid)}" ${d.sid === dev.sid ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}</select></div>` : ''}
      <div class="panel-actions"><button class="btn btn-danger btn-sm" data-action="logout">Sign out</button></div>
      <div style="border-top:1px solid var(--border);margin-top:18px;padding-top:16px">
        <h3>${aboutHead}</h3>${aboutList}
      </div>
    </div>` : `
    <div class="panel">
      <h3>About</h3><div class="panel-sub">${aboutHead}</div>${aboutList}
    </div>`;

  const libraryPanel = `
      <div class="panel">
        <h3>Library sync</h3><div class="panel-sub">Recordings are cached locally so pages load instantly.</div>
        <dl class="kv">
          <dt>Last sync</dt><dd>${st.last_sync ? `${esc(fmt.ago(st.last_sync))} (${esc(new Date(st.last_sync).toLocaleString())})` : 'Never'}</dd>
          <dt>Cached</dt><dd>${plural(st.total_shows || 0, 'show')}, ${plural(st.total_episodes || 0, 'recording')}</dd>
        </dl>
        <label class="switch-row" style="margin-top:16px;font-weight:400;cursor:default">
          <span>Check for new recordings</span>
          <select class="select" data-change="auto-sync" style="height:32px">
            ${[[0, 'Off'], [5, 'Every 5 minutes'], [15, 'Every 15 minutes'], [30, 'Every 30 minutes'], [60, 'Every hour']]
              .map(([v, label]) => `<option value="${v}" ${Number(settings.auto_sync_minutes ?? 15) === v ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </label>
        <p class="dim" style="font-size:12.5px;margin-top:8px">When on, the guide also refreshes every 6 hours. Changes you make in TabloView show up immediately either way.</p>
        <label class="switch-row" style="margin-top:14px">
          <input type="checkbox" class="switch" data-change="rerecord-failed" ${settings.rerecord_failed !== false ? 'checked' : ''}>
          <span>Record failed recordings again</span>
        </label>
        <p class="dim" style="font-size:12.5px;margin-top:6px">When a recording fails or comes out short, TabloView sets a rerun of the same episode to record (one that doesn’t clash with other recordings), if the guide has one in the next two weeks.</p>
        <div class="panel-actions">
          <button class="btn btn-sm" data-action="refresh-library">${icon('refresh', 15)}Sync recordings</button>
          <button class="btn btn-sm" data-action="sync-guide">${icon('guide', 15)}Refresh guide</button>
        </div>
      </div>
`;
  const storagePanel = `
      <div class="panel">
        <h3>Storage</h3><div class="panel-sub">${storage.connected ? `${fmt.size(storage.used_gb)} of ${fmt.size(storage.total_gb)} used` : 'Unavailable'}</div>
        ${(storage.drives || []).map(d => `
          <div style="margin-bottom:14px">
            <div class="meter-row" style="font-size:13px"><span>${esc(d.name)}</span><span class="dim">${fmt.size(d.free_gb)} free</span></div>
            <div class="meter" style="height:6px"><div class="meter-fill" style="width:${Math.min(d.percent_used, 100)}%"></div></div>
          </div>`).join('')}
      </div>
`;
  const playbackPanel = `
      <div class="panel">
        <h3>Playback</h3><div class="panel-sub">Picture quality, skipping and buffering for watching in TabloView.</div>
        <label class="switch-row" style="font-weight:400;cursor:default">
          <span>Video quality</span>
          <select class="select" data-change="video-quality" style="height:32px">
            ${[['auto', 'Automatic (recommended)'], ['best', 'Best quality'], ['fastest', 'Fastest (older PCs)']]
              .map(([v, label]) => `<option value="${v}" ${(playback.quality || 'auto') === v ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </label>
        ${playback.encoder ? `<p class="dim" style="margin-top:6px;font-size:12.5px">Converting with ${esc(playback.encoder)}${playback.hardware ? ' (your graphics chip, so the CPU stays free)' : ''}.</p>` : ''}
        <label class="switch-row" style="margin-top:14px">
          <input type="checkbox" class="switch" data-change="smooth-motion" ${playback.smooth_motion ? 'checked' : ''} ${playback.quality === 'fastest' ? 'disabled' : ''}>
          <span>Smooth motion (60 fps)</span>
        </label>
        <p class="dim" style="margin-top:6px;font-size:12.5px">Shows antenna TV at its full 60 motion steps a second, like on the TV. Best for sports. It works your PC much harder: if you see glitches or stutters, or live TV falls behind, turn it off. (If live TV can't keep up, TabloView switches that channel back to standard motion by itself.)</p>
        <label class="switch-row" style="font-weight:400;cursor:default;margin-top:14px">
          <span>Buffer before playing</span>
          <select class="select" data-change="buffer" style="height:32px">
            ${[4, 8, 15, 30].map(v => `<option value="${v}" ${state.bufferTarget === v ? 'selected' : ''}>${v} seconds</option>`).join('')}
          </select>
        </label>
        <label class="switch-row" style="margin-top:16px">
          <input type="checkbox" class="switch" data-change="skip-commercials" ${settings.skip_commercials ? 'checked' : ''}>
          <span>Skip commercial breaks automatically</span>
        </label>
        <p class="dim" style="margin-top:6px;font-size:12.5px">For shows with “Skip commercials” turned on (on the show’s page). Off: a Skip break button appears instead (or press S).</p>
        <label class="switch-row" style="margin-top:16px">
          <input type="checkbox" class="switch" data-change="skip-dropouts" ${settings.skip_dropouts ? 'checked' : ''}>
          <span>Skip signal dropouts automatically</span>
        </label>
        <p class="dim" style="margin-top:6px;font-size:12.5px">When a weak signal left part of a recording broken up or frozen, TabloView finds it in the background and marks it in red on the timeline. Off: a Skip dropout button appears instead (or press S).</p>
        <label class="switch-row" style="margin-top:16px">
          <input type="checkbox" class="switch" data-change="autoplay" ${state.autoplay ? 'checked' : ''}>
          <span>Play the next episode automatically</span>
        </label>
        <p class="dim" style="margin-top:6px;font-size:12.5px">When a show ends, TabloView counts down 10 seconds to the next unwatched episode. You can cancel and keep watching.</p>
      </div>
`;
  const exportsPanel = `
      <div class="panel">
        <h3>Exports</h3><div class="panel-sub">Recordings saved as MP4 files from the Downloads page.</div>
        <label class="switch-row" style="font-weight:400;cursor:default">
          <span>Format</span>
          <select class="select" data-change="export-format" style="height:32px">
            ${[['smaller', 'Smaller (about a third smaller)'], ['original', 'Original (exact copy, larger)']]
              .map(([v, label]) => `<option value="${v}" ${(settings.export_format || 'smaller') === v ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </label>
        <p class="dim" style="margin-top:6px;font-size:12.5px">Smaller exports are converted to H.264 (with your graphics chip when it can): about 2.2 GB per hour of HD instead of 3.2 GB, and they play on almost anything. Original keeps the broadcast video exactly as recorded.</p>
        <div class="switch-row" style="font-weight:400;cursor:default;margin-top:14px;align-items:center">
          <span style="flex-shrink:0">Save exports to</span>
          <code class="path-box" title="${esc(info.downloads_dir || '')}">${esc(info.downloads_dir || '')}</code>
          <button class="btn btn-sm" data-action="export-folder">Change…</button>
          ${info.downloads_dir && info.default_downloads_dir && info.downloads_dir !== info.default_downloads_dir
            ? '<button class="btn btn-sm btn-ghost" data-action="export-folder-reset">Reset</button>' : ''}
        </div>
      </div>
`;
  const appearancePanel = `
      <div class="panel">
        <h3>Appearance</h3><div class="panel-sub">How TabloView looks.</div>
        <label class="switch-row" style="font-weight:400;cursor:default">
          <span>Channel logos</span>
          <select class="select" data-change="logo-style" style="height:32px">
            <option value="color" ${settings.logo_style !== 'white' ? 'selected' : ''}>In color</option>
            <option value="white" ${settings.logo_style === 'white' ? 'selected' : ''}>All white</option>
          </select>
        </label>
        <p class="dim" style="margin-top:6px;font-size:12.5px">The stations' own logos in color, or all in white like before.</p>
        <label class="switch-row" style="font-weight:400;cursor:default;margin-top:14px">
          <span>Open TabloView on</span>
          <select class="select" data-change="start-page" style="height:32px">
            ${START_PAGES.map(([v, label]) => `<option value="${v}" ${store('tv_start_page', 'home') === v ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </label>
        <p class="dim" style="margin-top:6px;font-size:12.5px">The page you see when TabloView opens, on this computer.</p>
      </div>
`;
  const diagnosticsPanel = `
      <div class="panel" style="grid-column:1/-1">
        <h3>Diagnostics</h3><div class="panel-sub">Probe the Tablo's local API and the cloud guide to troubleshoot connection problems.</div>
        <button class="btn btn-sm" data-action="run-inspector">${icon('info', 15)}Run API inspector</button>
        <div id="inspectorOut"></div>
      </div>
`;
  const signalHtml = signalPanel(signal) || `
      <div class="panel" style="grid-column:1/-1">
        <h3>Signal health</h3><div class="panel-sub">How recordings on each channel turned out, and why the Tablo says any failed.</div>
        <p class="dim" style="font-size:13px">Nothing to show yet: this fills in as your Tablo records.</p>
      </div>`;
  const TABS = [
    ['general', 'General', connection + libraryPanel + appearancePanel],
    ['playback', 'Playback', playbackPanel],
    ['storage', 'Storage', storagePanel + exportsPanel + spaceByShowPanel(space, storage.connected ? storage.used_gb : 0)],
    ['signal', 'Signal health', signalHtml],
    ['desktop', 'Desktop & network', desktop + network],
    ['diagnostics', 'Diagnostics', diagnosticsPanel],
  ];
  const current = TABS.find(([id]) => id === r.query.get('tab')) || TABS[0];
  const tab = ([id, label]) => `<a href="#/device${id === 'general' ? '' : `?tab=${id}`}" class="${id === current[0] ? 'active' : ''}" style="display:inline-flex;align-items:center;height:28px;padding:0 12px;border-radius:7px;font-weight:500;font-size:13px">${label}</a>`;

  paint(`<div class="page">
    <div class="page-head"><div><h1 class="page-title">Device</h1><div class="page-sub">Your Tablo and TabloView's settings</div></div></div>
    <div class="toolbar"><div class="segmented tabs">${TABS.map(tab).join('')}</div></div>
    <div class="panel-grid">
${current[2]}
    </div>
  </div>`);
};

// Which shows use the most space. The Tablo's per-recording sizes don't add up to the drive's usage
// figure, so each show gets its share of the drive's real usage, labelled as approximate.
function spaceByShowPanel(data, usedGb) {
  const shows = (data && data.shows || []).filter(s => s.bytes > 0);
  const total = data && data.total_bytes;
  if (!shows.length || !total) return '';
  const gb = bytes => (usedGb ? (bytes / total) * usedGb : bytes / 1024 ** 3);
  const top = shows[0].bytes;
  const rows = shows.map(s => `
    <div class="space-row">
      <button class="space-title" data-action="open-show" data-id="${esc(s.show_id)}" title="Open ${esc(s.title)}">${esc(s.title)}</button>
      <div class="space-bar" title="${Math.round((s.bytes / total) * 100)}% of recordings">
        <div class="space-fill" style="width:${(s.bytes / top) * 100}%"></div>
        <div class="space-watched" style="width:${(s.watched_bytes / top) * 100}%"></div>
      </div>
      <div class="space-amt">about ${fmt.size(gb(s.bytes))}<span class="dim"> · ${plural(s.count, 'recording')}</span></div>
      <div class="space-act">${s.watched_count
        ? `<button class="btn btn-sm btn-danger" data-action="space-delete-watched" data-id="${esc(s.show_id)}" data-title="${esc(s.title)}" data-count="${s.watched_count}" data-kept="${s.protected_watched}" data-size="${esc(fmt.size(gb(s.watched_bytes)))}">${icon('trash', 13)}Delete ${s.watched_count} watched · ${fmt.size(gb(s.watched_bytes))}</button>`
        : '<span class="dim">Nothing watched yet</span>'}</div>
    </div>`).join('');
  return `
    <div class="panel" style="grid-column:1/-1">
      <h3>Space by show</h3>
      <div class="panel-sub">Biggest first. The orange part of each bar is recordings you’ve watched. Amounts are approximate.</div>
      <div class="space-list">${rows}</div>
    </div>`;
}

async function deleteWatchedForShow(el) {
  const { id, title, count, kept, size } = el.dataset;
  const ok = await confirmDialog({
    title: `Delete ${plural(Number(count), 'watched episode')}?`,
    text: `The watched episodes of “${title}” (about ${size}) will be permanently removed from your Tablo.${Number(kept) ? ` ${plural(Number(kept), 'protected recording')} will be kept.` : ''}`,
    confirm: 'Delete watched', danger: true,
  });
  if (!ok) return;
  try {
    const res = await api(`/api/shows/delete_watched?show_id=${encodeURIComponent(id)}`, { method: 'POST' });
    toast(`Deleted ${plural(res.deleted_count, 'watched episode')}`, 'success');
    if (res.errors && res.errors.length) toast(`${res.errors.length} couldn't be deleted: ${res.errors[0]}`, 'error');
    state.shows = null;
    route();
  } catch (err) {
    toast(`Delete failed: ${err.message}`, 'error');
  }
}

function updateStatusHtml() {
  const u = state.update;
  if (u && u.store) {
    if (u.update_available) return `<a href="${esc(u.download_url)}" style="color:var(--accent);font-weight:600">Version ${esc(u.latest)} is available in the Microsoft Store, open it</a>`;
    return `Kept up to date by the Microsoft Store <button class="btn btn-sm btn-ghost" data-action="check-update">Check now</button> <a class="btn btn-sm btn-ghost" href="${esc(u.download_url)}">Open in the Store</a>`;
  }
  if (!u || !u.enabled) return '<span class="dim">Update checks aren’t set up for this copy</span>';
  const btn = ' <button class="btn btn-sm btn-ghost" data-action="check-update">Check now</button>';
  if (u.update_available) {
    return `<a href="${esc(u.download_url || '#')}" target="_blank" rel="noopener" style="color:var(--accent);font-weight:600">Version ${esc(u.latest)} is available, download</a>${u.notes ? `<div class="dim" style="font-size:12.5px;margin-top:4px">${esc(u.notes)}</div>` : ''}`;
  }
  if (u.error) return `<span style="color:var(--warn)">Couldn’t check right now</span>${btn}`;
  return `Up to date${btn}`;
}

// After a settings-triggered restart, wait until the server answers again
async function waitForServer(timeoutMs = 25000) {
  await new Promise(r => setTimeout(r, 1200));
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { await api('/api/system/info'); return true; } catch { await new Promise(r => setTimeout(r, 700)); }
  }
  toast('TabloView is taking a while to restart. Try reloading the page.', 'error');
  return false;
}

async function runInspector() {
  const out = $('#inspectorOut');
  out.innerHTML = '<div class="loading-line"><span class="spinner"></span>Probing your Tablo and the cloud guide…</div>';
  try {
    const data = await api('/api/debug/endpoints');
    out.innerHTML = `<pre class="code-block">${esc(JSON.stringify(data, null, 2))}</pre>`;
  } catch (err) {
    out.innerHTML = `<pre class="code-block">Inspector error: ${esc(err.message)}</pre>`;
  }
}

// ---------------------------------------------------------------------------
// Player
// ---------------------------------------------------------------------------
const player = {
  el: () => $('#player'),
  video: () => $('#video'),
  // With two channels open, play/pause and picture-in-picture act on the one you're hearing
  activeVideo: () => (dual.on && dual.active === 'second' ? $('#video2') : $('#video')),
  setStatus(html) { $('#playerStatus').innerHTML = html; },

  open(title) {
    $('#playerTitle').textContent = title;
    $('#bufferSelect').value = String(state.bufferTarget);
    this.el().classList.remove('hidden');
    this.wake();
  },

  wake() {
    const el = this.el();
    el.classList.remove('idle');
    clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => el.classList.add('idle'), 2800);
  },

  // mode: undefined = ask if there's a resume point, 'resume', or 'start' (from the beginning)
  // mode may also be a number: start at that many seconds (used by the timeline to jump)
  async playEpisode(id, mode) {
    const ep = findEpisode(id);
    const resumable = ep && ep.status !== 'Watched' && (ep.position || 0) > 30;
    if (resumable && !mode) {
      mode = await chooseResume(ep);
      if (!mode) return;
    }
    const resuming = resumable && mode === 'resume';
    // From the beginning means where the show starts: the Tablo begins recording a few seconds early
    const start = typeof mode === 'number' ? Math.max(0, Math.floor(mode)) : (resuming ? ep.position : (ep && ep.program_start) || 0);
    const showTitle = ep ? ep.show_title || (state.show && state.show.title) || '' : '';
    const se = ep ? fmt.se(ep.season_number, ep.episode_number) : '';
    const title = ep ? [showTitle, se, episodeTitle(ep)].filter(Boolean).join(' · ') : 'Recording';

    const sameEpisode = state.stream.episodeId === id;
    this.finishEpisode();
    this.stopStream();
    this.hideUpNext();
    this.clearMessage();
    Object.assign(state.stream, {
      recoveries: 0, stallSince: 0, stallShown: false,
      // Commercial breaks skipped so far stay skipped when the same recording restarts (seek, stall)
      breaks: sameEpisode ? state.stream.breaks : [], skippedBreaks: sameEpisode ? state.stream.skippedBreaks : new Set(),
      dropouts: sameEpisode ? state.stream.dropouts : [], skippedDropouts: sameEpisode ? state.stream.skippedDropouts : new Set(),
      episodeId: id, channelId: null, offset: start,
      duration: ep ? ep.actual_duration || ep.duration || 0 : 0,
      lastSaved: start, markedWatched: false,
      // The show itself ends here; the recording runs on a little past it
      programEnd: ep && ep.duration ? (ep.program_start || 0) + ep.duration : 0,
      nextEp: null, upNextOffered: false,
    });
    // Playing something other than the run's current recording ends the run
    const inRun = state.run && runEpisode() && runEpisode().id === id;
    if (state.run && !inRun) state.run = null;
    if (inRun) state.stream.nextEp = state.run.eps[state.run.index + 1] || null;
    else if (ep) this.findNext(ep).then(next => { if (state.stream.episodeId === id) state.stream.nextEp = next; });
    this.showTimeline(true);
    // A restart of the same recording (a jump past what's converted, a stall) keeps its breaks;
    // showTimeline(false) in finishEpisode cleared the marks, so draw them again
    if (sameEpisode) this.drawBreaks();
    else this.loadBreaks(id);
    this.open(title);
    this.setStatus(`<span class="wait">${resuming ? `Resuming at ${fmtClock(start)}…` : 'Starting stream…'}</span>`);
    try {
      const res = await api(`/api/episodes/${encodeURIComponent(id)}/watch?transcode=true&start=${start}`, { method: 'POST' });
      state.stream.sessionId = res.session_id;
      if (!sameEpisode || !(state.stream.previewTimes || []).length) this.loadPreviews(id);
      this.start(res.stream_url, start && (resuming || typeof mode === 'number') ? `Resumed at ${fmtClock(start)}` : 'Recording');
      state.stream.progressTimer = setInterval(() => this.saveProgress(), 30000);
    } catch (err) {
      this.setStatus(`<span style="color:var(--rec)">Couldn't start playback: ${esc(err.message)}. Try “Open in VLC”.</span>`);
    }
  },

  // --- Player bar: whole-recording timeline, or the kept part of live TV, plus controls ---
  showTimeline(on) {
    const live = !!state.stream.channelId;
    $('#playerTimeline').classList.toggle('hidden', !on);
    $('#pbLive').classList.toggle('hidden', !live);
    $('#pbSpeed').disabled = live;  // live TV can't run faster than it's broadcast
    $('#pbChannels').classList.toggle('hidden', !live);
    if (!live) { $('#pbRecord').classList.add('hidden'); $('#pbRecord').dataset.key = ''; }
    $('#pbDual').classList.toggle('hidden', !on || dual.on);
    $('#pbLayout').classList.toggle('hidden', !on || !dual.on);
    if (live || !on) { $('#tlBreaks').innerHTML = ''; $('#tlDropouts').innerHTML = ''; $('#skipBreak').classList.add('hidden'); }
    if (!live) this.toggleChannels(false);
    clearInterval(state.stream.timelineTimer);
    state.stream.timelineTimer = on ? setInterval(() => this.updateTimeline(), 500) : null;
    if (on) this.updateTimeline();
  },

  // Live antenna TV: Record the show on now, on the Tablo, without leaving the channel
  liveAiring() {
    const s = state.stream;
    if (!s.channelId || !state.epg) return null;
    const c = state.epg.channels.find(x => x.channel_id === s.channelId);
    const a = c && nowNext(c).now;
    if (!a) return null;
    // Streaming channels: recordable ones only, by the cloud guide's airing ID
    if (a.airing_id) return c.can_record ? { c, a } : null;
    // Placeholder entries (no guide data) have nothing on the Tablo to schedule
    return a.path && !a.path.startsWith('/channel/') && !a.path.startsWith('/cloud/') ? { c, a } : null;
  },

  updateRecordButton() {
    const btn = $('#pbRecord');
    const hit = this.liveAiring();
    const recording = hit && (hit.a.schedule_state === 'scheduled' || hit.a.recording_now || hit.a.recording);
    const key = hit ? `${hit.a.path}|${recording ? 1 : 0}` : '';
    if (btn.dataset.key === key) return;
    btn.dataset.key = key;
    btn.classList.toggle('hidden', !hit);
    btn.classList.toggle('on', !!recording);
    btn.disabled = !!recording;
    $('#pbRecordText').textContent = recording ? 'Recording' : 'Record';
    btn.title = !hit ? '' : recording ? `${hit.a.title} is recording on your Tablo`
      : `Record ${hit.a.title} on your Tablo, from now until it ends`;
  },

  async recordLive() {
    const hit = this.liveAiring();
    if (!hit) return;
    try {
      if (hit.a.airing_id) await api('/api/streaming/record', { method: 'POST', body: JSON.stringify({ airing_id: hit.a.airing_id, scheduled: true }) });
      else await api('/api/guide/episodes/schedule', { method: 'POST', body: JSON.stringify({ path: hit.a.path, scheduled: true }) });
      hit.a.schedule_state = 'scheduled';
      state.upcoming = null;
      toast(`Recording ${hit.a.title} on your Tablo from now until it ends. It'll be in your Library.`, 'success');
    } catch (err) {
      toast(`Couldn't record it: ${err.message}`, 'error');
    }
    this.updateRecordButton();
  },

  // Live TV: the window kept for pause/rewind ([start, end] in video time)
  liveWindow() {
    const v = this.video();
    if (!v.seekable || !v.seekable.length) return null;
    return { start: v.seekable.start(0), end: v.seekable.end(v.seekable.length - 1) };
  },

  updateLiveTimeline() {
    this.updateRecordButton();
    const w = this.liveWindow();
    const v = this.video();
    if (!w || w.end <= w.start) {
      $('#tlNow').textContent = 'LIVE';
      $('#tlTotal').textContent = '';
      return;
    }
    const span = w.end - w.start;
    const behind = Math.max(0, w.end - v.currentTime);
    const atLive = behind < 12;
    $('#tlNow').textContent = atLive ? 'LIVE' : `−${fmtClock(behind)}`;
    $('#tlTotal').textContent = fmtClock(span);
    $('#tlTotal').title = 'How far back you can rewind';
    $('#tlPlayed').style.width = `${Math.min(100, ((v.currentTime - w.start) / span) * 100)}%`;
    $('#tlAvail').style.left = '0%';
    $('#tlAvail').style.width = '100%';
    const btn = $('#pbLive');
    btn.classList.toggle('at-live', atLive);
    btn.title = atLive ? 'You are watching live' : 'Jump to live';
  },

  // --- Controls (buttons and keyboard) ---
  togglePlay() {
    const v = this.activeVideo();
    if (v.paused) v.play().catch(() => {}); else v.pause();
  },

  skip(seconds) {
    const s = state.stream, v = this.video();
    if (s.channelId) {
      const w = this.liveWindow();
      if (w) v.currentTime = Math.max(w.start, Math.min(w.end - 2, v.currentTime + seconds));
    } else if (s.episodeId) {
      this.seekTo(this.position() + seconds);
    }
    this.wake();
  },

  goLive() {
    const w = this.liveWindow();
    if (w) this.video().currentTime = Math.max(w.start, w.end - 6);
    this.video().play().catch(() => {});
  },

  setSpeed(rate) {
    state.playbackRate = rate;
    $('#pbSpeed').value = String(rate);
    if (!state.stream.channelId) this.video().playbackRate = rate;
  },

  stepSpeed(dir) {
    const rates = [1, 1.1, 1.25, 1.5];
    const i = Math.max(0, rates.indexOf(state.playbackRate || 1));
    this.setSpeed(rates[Math.max(0, Math.min(rates.length - 1, i + dir))]);
    toast(`Speed ${state.playbackRate}×`);
  },

  toggleMute() {
    const v = this.video();
    v.muted = !v.muted;
  },

  setVolume(value) {
    const v = this.video();
    v.volume = Math.max(0, Math.min(1, value));
    v.muted = v.volume === 0;
    save('tablo_volume', String(v.volume));
  },

  toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else this.el().requestFullscreen().catch(() => {});
  },

  async togglePip() {
    try {
      if (document.pictureInPictureElement) await document.exitPictureInPicture();
      else await this.activeVideo().requestPictureInPicture();
    } catch { toast('Picture in picture isn’t available in this browser', 'error'); }
  },

  // Keep the play/mute buttons in step with the video
  syncButtons() {
    const v = this.video();
    // Volume and mute apply to both channels (which one you hear is chosen separately)
    const v2 = $('#video2');
    if (v2.volume !== v.volume) v2.volume = v.volume;
    if (v2.muted !== v.muted) v2.muted = v.muted;
    $('#pbPlay').innerHTML = icon(v.paused ? 'play' : 'pause', 22);
    $('#pbPlay').title = v.paused ? 'Play (Space)' : 'Pause (Space)';
    $('#pbMute').innerHTML = icon(v.muted || v.volume === 0 ? 'mute' : 'volume', 18);
    $('#pbVolume').value = v.muted ? 0 : v.volume;
  },

  showHelp() {
    const keys = [['Space or K', 'Play / pause'], ['← or J', 'Back 10 seconds'], ['→ or L', 'Ahead 30 seconds'],
      ['↑ ↓', 'Volume'], ['M', 'Mute'], ['F', 'Full screen'], ['P', 'Picture in picture'],
      ['&lt; &gt;', 'Slower / faster (recordings)'], ['Home', 'Back to live (live TV)'],
      ['Page Up / Down', 'Previous / next channel (live TV)'], ['S', 'Skip a commercial break'], ['T', 'Captions on / off'], ['2', 'Watch a live channel alongside'], ['Tab', 'Hear the other channel'], ['L', 'Layout of two channels'], ['C', 'Channel list (live TV)'], ['↑ ↓ / Page Up / Down', 'In the channel list: move through it (Enter picks)'], ['Esc', 'Close the player']];
    openModal(`<div class="dialog-body"><div class="dialog-title">Keyboard shortcuts</div>
      <div class="kbd-list">${keys.map(([k, d]) => `<kbd>${k}</kbd><span>${d}</span>`).join('')}</div></div>
      <div class="dialog-foot"><button class="btn btn-primary" data-action="modal-ok" data-autofocus>Got it</button></div>`);
  },

  // --- Stall watchdog: playing, but the picture hasn't moved ---
  watchdog() {
    const s = state.stream, v = this.video();
    // A recording that "ended" well before its end had its stream cut off: treat it as stalled
    const endedEarly = v.ended && s.episodeId && s.duration && this.position() < s.duration - 90;
    if (!s.sessionId || (!endedEarly && (v.paused || v.seeking || v.ended))) { s.stallSince = 0; s.lastTime = v.currentTime; return; }
    if (v.currentTime !== s.lastTime) {
      s.lastTime = v.currentTime;
      if (s.stallSince) this.clearMessage();
      s.stallSince = 0;
      return;
    }
    s.stallSince = s.stallSince || Date.now();
    const secs = (Date.now() - s.stallSince) / 1000;
    if (secs > 5 && !s.stallShown) {
      s.stallShown = true;
      this.message('<span class="spinner"></span>Waiting for your Tablo…');
    }
    // TabloView restarts a stuck stream itself after 10 s (on the same Tablo session); give that time
    // to work before starting over (recordings) or asking to tune again (live TV)
    if (secs < (s.channelId ? 30 : 25)) return;
    s.stallSince = 0;
    s.stallShown = false;
    if (s.episodeId && (s.recoveries || 0) < 3) {
      // Recordings: start the stream again from the same point (doesn't use a tuner)
      const recoveries = (s.recoveries || 0) + 1;
      console.warn(`[Player] Stalled; restarting at ${this.position()} s (attempt ${recoveries})`);
      this.playEpisode(s.episodeId, this.position()).then(() => { state.stream.recoveries = recoveries; });
    } else if (s.channelId) {
      // Live TV: re-tuning could take another tuner, so ask rather than doing it automatically
      this.message(`Live TV stopped responding. <button class="btn btn-sm btn-primary" data-action="pb-retune">Tune again</button>`);
    } else {
      this.message(`Your Tablo isn’t sending the recording. <button class="btn btn-sm" data-action="close-player">Close</button>`);
    }
  },

  message(html) {
    let el = $('#playerMsg');
    if (!el) {
      el = document.createElement('div');
      el.id = 'playerMsg';
      el.className = 'player-msg';
      this.el().appendChild(el);
    }
    el.innerHTML = html;
  },

  clearMessage() {
    const el = $('#playerMsg');
    if (el) el.remove();
  },

  // Seconds of the recording already converted and playable without restarting
  availableEnd() {
    const v = this.video();
    let end = 0;
    if (v.seekable && v.seekable.length) end = v.seekable.end(v.seekable.length - 1);
    if (v.buffered && v.buffered.length) end = Math.max(end, v.buffered.end(v.buffered.length - 1));
    return (state.stream.offset || 0) + (isFinite(end) ? end : 0);
  },

  // Timeline previews from the Tablo's own trick-play file (fetched in the background as playback starts)
  async loadPreviews(id) {
    if (state.stream.previewsFor !== id) state.stream.previewTimes = [];
    state.stream.previewsFor = id;
    for (let i = 0; i < 6; i++) {
      await new Promise(r => setTimeout(r, i ? 1500 : 500));
      if (state.stream.episodeId !== id) return;
      try {
        const res = await api(`/api/episodes/${encodeURIComponent(id)}/previews`);
        if (res.times && res.times.length) { state.stream.previewTimes = res.times; return; }
      } catch { /* try again */ }
    }
  },

  // The preview image for a time in the recording: the Tablo's (whole recording) or, without those,
  // the frames FFmpeg saves as it converts (only what's converted so far)
  previewUrl(t) {
    const s = state.stream;
    const times = s.previewTimes || [];
    if (times.length && s.previewsFor === s.episodeId) {
      let n = 0;
      while (n + 1 < times.length && times[n + 1] <= t) n++;
      return `/api/episodes/${encodeURIComponent(s.episodeId)}/previews/${n}`;
    }
    return s.sessionId ? `/api/transcoded/${s.sessionId}/p${String(Math.floor(t / 5)).padStart(5, '0')}.jpg` : '';
  },

  // --- Commercial breaks (found in the background for shows with "Skip commercials" on) ---
  async loadBreaks(id) {
    let res;
    try { res = await api(`/api/episodes/${encodeURIComponent(id)}/commercials`); } catch { return; }
    if (state.stream.episodeId !== id) return;
    state.stream.breaks = res.breaks || [];
    state.stream.autoSkip = !!res.auto_skip;
    state.stream.dropouts = res.dropouts || [];
    state.stream.autoSkipDropouts = !!res.auto_skip_dropouts;
    this.drawBreaks();
  },

  drawBreaks() {
    const s = state.stream, dur = s.duration;
    const mark = (list, title) => dur && s.episodeId ? (list || []).map(b =>
      `<span style="left:${(b.start / dur) * 100}%;width:${Math.max(0.25, ((b.end - b.start) / dur) * 100)}%" title="${title}"></span>`).join('') : '';
    $('#tlBreaks').innerHTML = mark(s.breaks, 'Commercial break');
    $('#tlDropouts').innerHTML = mark(s.dropouts, 'Signal dropout: the picture breaks up or freezes here');
  },

  // In a break: skip it (automatically if that's on, once per break) or offer a button.
  // Signal dropouts work the same way, with their own setting.
  checkBreak(pos) {
    const s = state.stream;
    const i = (s.breaks || []).findIndex(b => pos >= b.start && pos < b.end - 2);
    const btn = $('#skipBreak');
    if (i < 0) { this.checkDropout(pos); return; }
    const b = s.breaks[i];
    if (s.autoSkip && !s.skippedBreaks.has(i)) {
      s.skippedBreaks.add(i);
      btn.classList.add('hidden');
      toast(`Skipped a ${fmt.dur(b.end - b.start) || 'short'} commercial break`);
      this.seekTo(b.end);
      return;
    }
    btn.dataset.end = b.end;
    btn.innerHTML = `Skip break ${icon('next', 16)}<span>${fmtClock(b.end - pos)}</span>`;
    btn.classList.remove('hidden');
  },

  checkDropout(pos) {
    const s = state.stream;
    const i = (s.dropouts || []).findIndex(d => pos >= d.start && pos < d.end - 0.5);
    const btn = $('#skipBreak');
    if (i < 0) { btn.classList.add('hidden'); return; }
    const d = s.dropouts[i];
    if (s.autoSkipDropouts && !s.skippedDropouts.has(i)) {
      s.skippedDropouts.add(i);
      btn.classList.add('hidden');
      toast(`Skipped ${fmt.dur(d.end - d.start) || 'a few seconds'} of signal dropout`);
      this.seekTo(d.end);
      return;
    }
    btn.dataset.end = d.end;
    btn.innerHTML = `Skip dropout ${icon('next', 16)}<span>${fmtClock(d.end - pos)}</span>`;
    btn.classList.remove('hidden');
  },

  skipBreak() {
    const end = parseFloat($('#skipBreak').dataset.end);
    $('#skipBreak').classList.add('hidden');
    if (end) this.seekTo(end);
  },

  updateTimeline() {
    const s = state.stream, dur = s.duration;
    if (s.channelId) return this.updateLiveTimeline();
    if (!dur || !s.episodeId) return;
    const pct = x => `${Math.min(100, Math.max(0, (x / dur) * 100))}%`;
    const pos = this.position();
    $('#tlNow').textContent = fmtClock(pos);
    $('#tlTotal').textContent = fmtClock(dur);
    $('#tlPlayed').style.width = pct(pos);
    const avail = $('#tlAvail');
    avail.style.left = pct(s.offset || 0);
    avail.style.width = `calc(${pct(this.availableEnd())} - ${pct(s.offset || 0)})`;
    if (s.programEnd && pos >= s.programEnd) this.offerUpNext();
    this.checkBreak(pos);
  },

  // --- Up next: when a show ends, count down to the next unwatched episode of the same show ---
  async findNext(ep) {
    let list = state.show && state.show.id === ep.show_id ? state.episodes : null;
    if (!list) {
      try { list = (await api(`/api/shows/episodes?show_id=${encodeURIComponent(ep.show_id)}`)).episodes || []; } catch { return null; }
    }
    state.stream.list = list;
    const i = list.findIndex(e => e.id === ep.id);
    return list.slice(i + 1).find(e => e.status !== 'Watched' && e.recording_state !== 'recording') || null;
  },

  offerUpNext() {
    const s = state.stream;
    if ((!state.autoplay && !state.run) || s.upNextOffered || !s.nextEp || !s.episodeId || (state.sleep && state.sleep.endOfShow)) return;
    s.upNextOffered = true;
    const n = s.nextEp;
    let left = 10;
    const thumb = imgUrl(n.snapshot_url || (state.show && (state.show.backdrop_url || state.show.cover_url)));
    const box = $('#upNext');
    box.innerHTML = `
      ${thumb ? `<img class="upnext-thumb" src="${esc(thumb)}" alt="">` : ''}
      <div class="upnext-body">
        <div class="upnext-label">Up next${state.run ? ` · ${state.run.index + 2} of ${state.run.eps.length}` : ''} · <span id="upNextCount">${left}</span>s</div>
        <div class="upnext-title">${esc([state.run ? n.show_title : '', fmt.se(n.season_number, n.episode_number), episodeTitle(n)].filter(Boolean).join(' · '))}</div>
        <div class="upnext-actions">
          <button class="btn btn-primary btn-sm" data-action="upnext-play">${icon('play', 13)}Play now</button>
          <button class="btn btn-sm" data-action="upnext-cancel">Cancel</button>
        </div>
      </div>`;
    box.classList.remove('hidden');
    s.upNextTimer = setInterval(() => {
      left -= 1;
      const c = $('#upNextCount');
      if (c) c.textContent = left;
      if (left <= 0) this.playNext();
    }, 1000);
  },

  playNext() {
    const n = state.stream.nextEp;
    this.hideUpNext();
    if (n && state.run) {
      this.runFinished();
      state.run.index += 1;
    }
    if (n) this.playEpisode(n.id, (n.position || 0) > 30 ? 'resume' : 'start');
  },

  // The run's current recording, if it was watched to the end (as for marking it Watched): it comes
  // off the Watch list and, with "watch and delete", is deleted (the server keeps protected ones).
  // Only on moving on or closing, so rewinding over the ending never loses it.
  runFinished() {
    const s = state.stream, ep = runEpisode();
    if (!ep || ep.id !== s.episodeId) return;
    this.saveProgress();
    if (!s.markedWatched) return;
    const name = [ep.show_title, fmt.se(ep.season_number, ep.episode_number)].filter(Boolean).join(' ');
    api(`/api/watchlist/${encodeURIComponent(ep.id)}/finished`, { method: 'POST', body: JSON.stringify({ delete: state.run.deleteAfter }) })
      .then(res => {
        if (res.deleted) {
          state.episodes = state.episodes.filter(e => e.id !== ep.id);
          state.shows = null;
          loadStorage();
          toast(`Deleted ${name} from your Tablo`, 'success');
        } else if (res.protected && state.run && state.run.deleteAfter) {
          toast(`Kept ${name}: it's protected on your Tablo`);
        } else if (res.error) {
          toast(`Couldn't delete ${name}: ${res.error}`, 'error');
        }
        loadWatchCount({ redraw: true });
      })
      .catch(() => {});
  },

  hideUpNext() {
    clearInterval(state.stream.upNextTimer);
    state.stream.upNextTimer = null;
    const box = $('#upNext');
    if (box) { box.classList.add('hidden'); box.innerHTML = ''; }
  },

  // Jump within what's converted; anywhere else restarts conversion at that point
  seekTo(target) {
    const s = state.stream;
    if (!s.episodeId) return;
    target = Math.max(0, Math.min(target, (s.duration || target) - 5));
    if (target >= (s.offset || 0) && target <= this.availableEnd() - 3) {
      this.video().currentTime = target - (s.offset || 0);
      this.updateTimeline();
    } else {
      this.setStatus(`<span class="wait">Jumping to ${fmtClock(target)}…</span>`);
      this.playEpisode(s.episodeId, target);
    }
  },

  // Position in the recording (the stream may have started at a resume point)
  position() {
    return Math.floor((state.stream.offset || 0) + (this.video().currentTime || 0));
  },

  // Save the resume point on the Tablo; near the end, mark the recording watched instead
  saveProgress({ final = false } = {}) {
    const s = state.stream;
    if (!s.episodeId || s.markedWatched) return;
    const pos = this.position();
    const nearEnd = s.duration && pos >= s.duration - Math.max(120, s.duration * 0.05);
    if (nearEnd) {
      s.markedWatched = true;
      sendProgress(s.episodeId, { watched: true }, final);
      return;
    }
    if (pos > 30 && Math.abs(pos - (s.lastSaved || 0)) >= 10) {
      s.lastSaved = pos;
      sendProgress(s.episodeId, { position: pos }, final);
    }
  },

  async watchLive(channelId, name, kind) {
    this.finishEpisode();
    const stopping = this.stopStream();
    this.hideUpNext();
    this.clearMessage();
    Object.assign(state.stream, { channelId, channelName: name, channelKind: kind, episodeId: null,
                                  stallSince: 0, stallShown: false });
    this.showTimeline(true);
    this.open(`Live · ${name}`);
    this.setStatus(`<span class="wait">Tuning ${esc(name)}…</span>`);
    try {
      await stopping;  // the old channel's tuner goes back to the Tablo before this one asks for one
      const res = await api('/api/live/tune', { method: 'POST', body: JSON.stringify({ channel_id: channelId, transcode: true, kind }) });
      state.stream.sessionId = res.session_id;
      checkTuners();
      this.start(res.stream_url, 'Live');
      if (kind !== 'fast') reception.start(res.session_id);
      dual.render();
    } catch (err) {
      if (err.status === 409) {
        this.setStatus('');
        this.message(`${esc(err.message)}
          <button class="btn btn-sm btn-primary" data-action="pb-retune">Try again</button>
          <button class="btn btn-sm" data-action="pb-recordings">Watch a recording</button>`);
      } else {
        this.setStatus(`<span style="color:var(--rec)">Couldn't tune this channel: ${esc(err.message)}</span>`);
      }
      checkTuners();
    }
  },

  // --- Live TV: channel list beside the picture, and channel up/down ---
  // The guide's data, loaded (or refreshed when it's about to run out) on demand
  async ensureEpg() {
    const end = state.epg ? new Date(state.epg.window_end).getTime() : 0;
    if (end - Date.now() > 30 * 60000) return;
    try { state.epg = await api(`/api/live/epg?hours=${EPG.HOURS}`); } catch { /* the list stays as it was */ }
  },

  // Surf within the Live TV page's current filter, unless the channel being watched isn't in it
  liveChannels() {
    const all = (state.epg && state.epg.channels) || [];
    const list = all.filter(epgFilter);
    return list.some(c => c.channel_id === state.stream.channelId) ? list : all;
  },

  async toggleChannels(show) {
    const panel = $('#chanPanel');
    show = show === undefined ? panel.classList.contains('hidden') : show;
    if (!show) dual.picking = false;
    clearInterval(this.chanTimer);
    this.el().classList.toggle('chan-open', show);
    if (!show) { panel.classList.add('hidden'); return; }
    panel.classList.remove('hidden');
    if (!state.epg) panel.innerHTML = '<div class="loading-line" style="padding:20px"><span class="spinner"></span>Loading channels…</div>';
    await this.ensureEpg();
    this.renderChannels();
    const cur = panel.querySelector('.current');
    if (cur) cur.scrollIntoView({ block: 'center' });
    this.chanTimer = setInterval(() => { this.ensureEpg().then(() => this.renderChannels()); }, 30000);
  },

  renderChannels() {
    const panel = $('#chanPanel');
    if (panel.classList.contains('hidden')) return;
    const list = this.liveChannels();
    const now = Date.now();
    const scroll = panel.querySelector('.chan-list');
    const top = scroll ? scroll.scrollTop : null;
    const focused = document.activeElement && document.activeElement.closest('.chan-row');
    const focusedId = focused && panel.contains(focused) ? focused.dataset.id : null;
    // The surf buttons change the main channel: not while picking the second one
    const surfButtons = dual.picking ? '' : `
        <button class="pb-btn" data-action="pb-surf" data-dir="-1" title="Previous channel (Page Up)">${icon('up', 16)}</button>
        <button class="pb-btn" data-action="pb-surf" data-dir="1" title="Next channel (Page Down)">${icon('down', 16)}</button>`;
    panel.innerHTML = `<div class="chan-head">
        <span>${dual.picking ? 'Pick a second channel' : dual.on ? `Change ${esc(dual.active === 'second' ? dual.s.name : state.stream.channelName)}` : 'Channels'}</span>${surfButtons}
        <button class="pb-btn" data-action="pb-channels" title="Close (C)">${icon('x', 16)}</button>
      </div>
      <div class="chan-list">${list.length ? list.map(c => {
        const { num, name } = channelName(c);
        const { now: on, next } = nowNext(c, now);
        const start = on ? new Date(on.air_datetime).getTime() : 0;
        const pct = on && on.duration ? Math.min(100, Math.round(((now - start) / (on.duration * 1000)) * 100)) : 0;
        return `<button class="chan-row ${c.channel_id === state.stream.channelId ? 'current' : ''}" data-action="pb-tune" data-id="${esc(c.channel_id)}" data-name="${esc(name)}" data-kind="${esc(c.kind)}">
          ${c.logo_url ? `<img class="chan-logo" src="${esc(c.logo_url)}" alt="" loading="lazy">` : `<span class="chan-logo chan-logo-text">${esc((c.call_sign || 'TV').slice(0, 6))}</span>`}
          <span class="chan-info">
            <span class="chan-name">${num ? `<b>${esc(num)}</b>` : ''}${esc(name)}</span>
            <span class="chan-now">${on ? esc(on.title) : '<span class="dim">No guide info</span>'}</span>
            ${on ? `<span class="chan-bar"><span style="width:${pct}%"></span></span>` : ''}
            ${next ? `<span class="chan-next">${esc(fmt.time(next.air_datetime))} ${esc(next.title)}</span>` : ''}
          </span>
        </button>`;
      }).join('') : '<div class="dim" style="padding:20px">No channels in the guide yet.</div>'}</div>`;
    hydrateIcons(panel);
    if (top !== null) panel.querySelector('.chan-list').scrollTop = top;
    if (focusedId) {
      const row = [...panel.querySelectorAll('.chan-row')].find(r => r.dataset.id === focusedId);
      if (row) row.focus({ preventScroll: true });
    }
  },

  // Keys while the channel list is open move through it (they'd otherwise change the channel or the
  // volume, and picking a second channel couldn't page through the list). True if the key was used.
  moveInChannels(key) {
    const rows = [...$$('#chanPanel .chan-row')];
    if (!rows.length) return false;
    const at = rows.indexOf(document.activeElement);
    if ((key === 'Enter' || key === ' ') && at >= 0) { rows[at].click(); return true; }
    const list = $('#chanPanel .chan-list');
    const page = Math.max(1, Math.floor(list.clientHeight / (rows[0].offsetHeight || 60)) - 1);
    const from = at >= 0 ? at : Math.max(0, rows.findIndex(r => r.classList.contains('current')));
    const to = { ArrowDown: from + 1, ArrowUp: from - 1, PageDown: from + page, PageUp: from - page,
                 Home: 0, End: rows.length - 1 }[key];
    if (to === undefined) return false;
    // First press: start on the channel that's playing
    const target = rows[at >= 0 ? Math.max(0, Math.min(rows.length - 1, to)) : from];
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: 'nearest' });
    return true;
  },

  // Channel up/down: show where you're headed, and tune once the presses stop, so flipping past
  // channels doesn't tie up tuners (the Tablo holds a tuner for a while after each one)
  async surf(dir) {
    const s = state.stream;
    if (!s.channelId) return;
    await this.ensureEpg();
    const list = this.liveChannels();
    if (!list.length) return;
    const from = s.surfIndex ?? list.findIndex(c => c.channel_id === s.channelId);
    const idx = ((from < 0 ? 0 : from + dir) + list.length) % list.length;
    s.surfIndex = idx;
    const c = list[idx];
    const { num, name } = channelName(c);
    const on = nowNext(c).now;
    const osd = $('#chanOsd');
    osd.innerHTML = `<div><b>${esc(num)}</b> ${esc(name)}</div>${on ? `<span>${esc(on.title)}</span>` : ''}`;
    osd.classList.remove('hidden');
    clearTimeout(s.surfTimer);
    s.surfTimer = setTimeout(() => {
      s.surfIndex = null;
      osd.classList.add('hidden');
      if (c.channel_id !== s.channelId) this.tune(c.channel_id, name, c.kind);
    }, 900);
  },

  async tune(channelId, name, kind) {
    if (dual.picking) return dual.start(channelId, name, kind);
    if (dual.on && dual.active === 'second') return dual.retune(channelId, name, kind);
    if (channelId === state.stream.channelId) return;
    await watchLiveChecked(channelId, name, kind);
    this.renderChannels();
  },

  // --- Closed captions: the broadcast's own captions travel inside the converted video (FFmpeg keeps
  // them), and hls.js turns them into a text track; this only shows or hides it
  applyCaptions() {
    const tracks = [...[...this.video().textTracks].map(t => [t, 'main']), ...[...$('#video2').textTracks].map(t => [t, 'second'])];
    for (const [t, pane] of tracks) {
      // With two channels, the one you aren't hearing shows captions so you can still follow it
      t.mode = state.captions || (dual.on && dual.active !== pane) ? 'showing' : 'hidden';
      if (!t.__raised) {
        // Broadcast captions sit on the bottom rows, under the player bar: lift them above it
        t.__raised = true;
        t.addEventListener('cuechange', () => {
          for (const c of t.activeCues || []) if (c.line !== 78) { c.snapToLines = false; c.line = 78; }
        });
      }
    }
    const b = $('#pbCC');
    b.classList.toggle('on', state.captions);
    b.title = state.captions ? 'Turn captions off (T)' : 'Captions (T)';
  },

  toggleCaptions() {
    state.captions = !state.captions;
    save('tablo_cc', state.captions ? '1' : '0');
    this.applyCaptions();
    toast(state.captions
      ? (this.video().textTracks.length ? 'Captions on' : 'Captions on: they appear as soon as the broadcast sends them')
      : 'Captions off');
  },

  // --- Sleep timer: stop after some minutes, or when the current show ends. Survives auto-play to the
  // next episode; cleared when the player closes. The last 15 seconds fade the sound out.
  sleepMenu(anchor) {
    const s = state.sleep;
    const set = (minutes, endOfShow = false) => () => this.setSleep(minutes, endOfShow);
    openMenu(anchor, [
      { heading: 'Sleep timer' },
      { label: 'Off', checked: !s, run: () => this.setSleep(null) },
      ...[15, 30, 60, 90].map(m => ({ label: `${m} minutes`, checked: !!(s && s.minutes === m), run: set(m) })),
      { label: 'End of this show', checked: !!(s && s.endOfShow), run: set(null, true) },
    ]);
  },

  // When the current show ends, in wall-clock time: recordings from the playback position,
  // live TV from the guide
  showEndsAt() {
    const st = state.stream;
    if (st.episodeId) {
      const end = st.programEnd || st.duration;
      return end ? Date.now() + Math.max(0, end - this.position()) * 1000 / (this.video().playbackRate || 1) : null;
    }
    const c = ((state.epg && state.epg.channels) || []).find(x => x.channel_id === st.channelId);
    const on = c && nowNext(c).now;
    return on ? new Date(on.air_datetime).getTime() + (on.duration || 0) * 1000 : null;
  },

  setSleep(minutes, endOfShow = false) {
    clearInterval(this.sleepTimer);
    this.video().volume = state.sleep ? state.sleep.volume : this.video().volume;
    state.sleep = null;
    if (minutes || endOfShow) {
      const until = endOfShow ? this.showEndsAt() : Date.now() + minutes * 60000;
      if (!until) { toast('The end of this show isn’t known; choose a number of minutes instead', 'error'); this.syncSleep(); return; }
      state.sleep = { minutes, endOfShow, until, volume: this.video().volume };
      this.sleepTimer = setInterval(() => this.sleepTick(), 1000);
      toast(endOfShow ? `Playback stops at the end of this show (${fmt.time(new Date(until).toISOString())})` : `Playback stops in ${minutes} minutes`);
    }
    this.syncSleep();
  },

  sleepTick() {
    const s = state.sleep;
    if (!s) return;
    // A recording's end moves when it's paused or skipped through
    if (s.endOfShow && state.stream.episodeId) s.until = this.showEndsAt() || s.until;
    const left = s.until - Date.now();
    const v = this.video();
    if (left <= 15000 && !v.paused) v.volume = s.volume * Math.max(0, left / 15000);
    if (left <= 0) {
      this.setSleep(null);
      this.close();
      toast('Sleep timer: playback stopped');
      return;
    }
    this.syncSleep();
  },

  syncSleep() {
    const b = $('#pbSleep');
    const s = state.sleep;
    const mins = s ? Math.max(1, Math.ceil((s.until - Date.now()) / 60000)) : 0;
    b.classList.toggle('on', !!s);
    $('#pbSleepLeft').textContent = s ? `${mins}m` : '';
    b.title = s ? `Sleep timer: stops in ${mins} minute${mins === 1 ? '' : 's'}` : 'Sleep timer';
  },

  // Pre-buffer to the target before playing, then report buffer health
  start(url, label) {
    const video = this.video();
    const target = state.bufferTarget;
    this.teardown();

    if (window.Hls && Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true, lowLatencyMode: false, backBufferLength: 90,
        maxBufferLength: 60, maxMaxBufferLength: 180, maxBufferSize: 80 * 1000 * 1000,
        startFragPrefetch: true, maxBufferHole: 0.5, highBufferWatchdogPeriod: 2,
      });
      let started = false;
      const check = () => {
        let ahead = 0;
        for (let i = 0; i < video.buffered.length; i++) {
          const s = video.buffered.start(i), e = video.buffered.end(i);
          if (s <= video.currentTime && video.currentTime <= e) { ahead = Math.round(e - video.currentTime); break; }
          if (video.currentTime === 0) { ahead = Math.round(e); break; }
        }
        if (!started) {
          this.setStatus(`<span class="wait">Buffering ${ahead}s of ${target}s…</span>`);
          if (ahead >= target) { started = true; this.begin(); }
        } else {
          const cls = ahead >= 4 ? 'good' : 'wait';
          this.setStatus(`${label} · <span class="${cls}">${ahead}s buffered</span>`);
        }
      };
      hls.loadSource(url);
      hls.attachMedia(video);
      video.pause();
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        state.stream.timer = setInterval(check, 500);
        setTimeout(() => {
          if (!started && state.stream.hls === hls) { started = true; this.begin(); }
        }, 8000);
      });
      hls.on(Hls.Events.FRAG_BUFFERED, check);
      video.addEventListener('progress', check);
      state.stream.handler = check;
      hls.on(Hls.Events.ERROR, (evt, data) => {
        if (!data.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
        else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
        else { hls.destroy(); this.setStatus('<span style="color:var(--rec)">Playback error. Try “Open in VLC”.</span>'); }
      });
      state.stream.hls = hls;
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url;
      this.begin();
    } else {
      // e.g. Firefox on Fedora, which leaves out H.264 unless a codec package is added
      this.setStatus('');
      this.message(`This browser can't play TabloView's video (H.264). Try Chrome or Edge, or use
        <b>Open in VLC</b>. On Fedora, Firefox plays it once the full codecs are installed
        (<code>libavcodec-freeworld</code> from RPM Fusion; the Firefox Flatpak includes them).`);
    }
    state.stream.watchdogTimer = setInterval(() => this.watchdog(), 1000);
  },

  // Start playing, at the chosen speed for recordings (live TV always plays at 1x)
  begin() {
    const video = this.video();
    const rate = state.stream.channelId ? 1 : (state.playbackRate || 1);
    video.defaultPlaybackRate = rate;
    video.playbackRate = rate;
    video.play().catch(() => {});
  },

  teardown() {
    const s = state.stream;
    if (s.watchdogTimer) { clearInterval(s.watchdogTimer); s.watchdogTimer = null; }
    if (s.timer) { clearInterval(s.timer); s.timer = null; }
    if (s.handler) { this.video().removeEventListener('progress', s.handler); s.handler = null; }
    if (s.hls) { s.hls.destroy(); s.hls = null; }
  },

  // Tell the backend to kill the FFmpeg transcode (and free the tuner for live TV)
  // Resolves once the backend has the stop (callers that tune next wait for it)
  stopStream({ keepalive = false } = {}) {
    reception.stop();
    const id = state.stream.sessionId;
    if (!id) return Promise.resolve();
    state.stream.sessionId = null;
    return fetch('/api/live/stop', {
      method: 'POST', headers: API_HEADERS,
      body: JSON.stringify({ session_id: id }), keepalive,
    }).catch(() => {});
  },

  // Save where the current recording got to before switching or closing
  finishEpisode() {
    if (state.stream.episodeId) this.saveProgress({ final: true });
    clearInterval(state.stream.progressTimer);
    state.stream.progressTimer = null;
    this.showTimeline(false);
  },

  close() {
    const hadEpisode = !!state.stream.episodeId;
    if (state.run) {
      this.runFinished();
      state.run = null;
    }
    this.hideUpNext();
    this.clearMessage();
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    if (document.pictureInPictureElement) document.exitPictureInPicture().catch(() => {});
    this.finishEpisode();
    this.teardown();
    const video = this.video();
    video.pause();
    video.removeAttribute('src');
    video.load();
    this.el().classList.add('hidden');
    dual.stop();
    if (state.sleep) this.setSleep(null);
    this.toggleChannels(false);
    clearTimeout(state.stream.surfTimer);
    state.stream.surfIndex = null;
    $('#chanOsd').classList.add('hidden');
    this.stopStream();
    if (state.stream.channelId) setTimeout(checkTuners, 1000);
    state.stream.channelId = null;
    state.stream.episodeId = null;
    if (hadEpisode) rerenderAfterProgress();
  },

  openInVlc() {
    if (state.stream.channelId) openVlc(`/api/live/vlc/${encodeURIComponent(state.stream.channelId)}`);
    else if (state.stream.episodeId) openVlc(`/api/episodes/${encodeURIComponent(state.stream.episodeId)}/playlist.m3u`);
  },

  isOpen() { return !this.el().classList.contains('hidden'); },
};

function fmtClock(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}

// ---------------------------------------------------------------------------
// Watch list, and runs: recordings played one after another (from the list, or ticked on a show page)
// ---------------------------------------------------------------------------
function runEpisode() {
  return state.run ? state.run.eps[state.run.index] : null;
}

// Watch and keep, or watch and delete? null if cancelled
function chooseRun(count) {
  return openModal(`
    <div class="dialog-body">
      <div class="dialog-title">Watch ${count === 1 ? 'this recording' : `${count} recordings in a row`}</div>
      <div class="dialog-text">${count === 1 ? 'It plays' : 'They play one after another'}, picking up where you left off. With <b>Watch and delete</b>, each one is deleted from your Tablo once you’ve watched it to the end. Ones you stop partway, and protected recordings, are kept.</div>
    </div>
    <div class="dialog-foot">
      <button class="btn" data-action="modal-cancel">Cancel</button>
      <button class="btn btn-danger" data-action="modal-value" data-value="delete">${icon('trash', 14)}Watch and delete</button>
      <button class="btn btn-primary" data-action="modal-value" data-value="keep" data-autofocus>${icon('play', 14)}Watch and keep</button>
    </div>`).then(v => (v === 'keep' || v === 'delete' ? v : null));
}

async function startRun(eps, fromList) {
  eps = eps.filter(e => e && e.recording_state !== 'recording');
  if (!eps.length) return;
  const how = await chooseRun(eps.length);
  if (!how) return;
  state.run = { eps, index: 0, deleteAfter: how === 'delete', fromList };
  const first = eps[0];
  player.playEpisode(first.id, first.status !== 'Watched' && (first.position || 0) > 30 ? 'resume' : 'start');
}

async function loadWatchCount({ redraw = false } = {}) {
  try {
    const { count } = await api('/api/watchlist');
    $('#navWatchCount').textContent = count || '';
    // A recording just finished in a run: show the list without it (once the player is closed)
    if (redraw && parseRoute().name === 'watchlist' && !player.isOpen()) route();
  } catch { /* not important */ }
}

async function addToWatchList(ids) {
  try {
    const res = await api('/api/watchlist', { method: 'POST', body: JSON.stringify({ episode_ids: ids }) });
    $('#navWatchCount').textContent = res.count || '';
    toast(res.added ? `Added ${plural(res.added, 'recording')} to your Watch list` : 'Already on your Watch list', 'success');
  } catch (err) {
    toast(`Couldn't add to the Watch list: ${err.message}`, 'error');
  }
}

async function saveWatchList(ids) {
  try {
    const res = await api('/api/watchlist', { method: 'PUT', body: JSON.stringify({ episode_ids: ids }) });
    $('#navWatchCount').textContent = res.count || '';
  } catch (err) {
    toast(`Couldn't change the Watch list: ${err.message}`, 'error');
  }
  route();
}

PAGES.watchlist = async (r, token) => {
  const { episodes } = await api('/api/watchlist');
  if (stale(token)) return;
  state.watchList = episodes;
  $('#navWatchCount').textContent = episodes.length || '';
  const total = episodes.reduce((n, e) => n + Math.max(0, (e.duration || 0) - (e.status !== 'Watched' ? e.position || 0 : 0)), 0);
  const row = (ep, i) => {
    const partway = ep.status !== 'Watched' && (ep.position || 0) > 30;
    const thumb = imgUrl(ep.snapshot_url || ep.show_art);
    return `
      <div class="list-row watch-row clickable" data-action="watchlist-play-from" data-index="${i}" title="Play from here">
        <div class="watch-num">${i + 1}</div>
        ${thumb ? `<img class="thumb" src="${esc(thumb)}" alt="" loading="lazy">` : '<div class="thumb"></div>'}
        <div style="min-width:0">
          <div class="row-title">${ep.protected ? `<span class="ep-lock" title="Protected on your Tablo: never deleted by Watch and delete">${icon('lock', 13)}</span>` : ''}${esc(ep.show_title || '')}</div>
          <div class="row-sub">${esc([fmt.se(ep.season_number, ep.episode_number), episodeTitle(ep)].filter(Boolean).join(' · '))}</div>
        </div>
        <div class="row-sub">${partway ? `${esc(fmt.dur(ep.duration - ep.position))} left` : esc(fmt.dur(ep.duration))}</div>
        <div class="watch-acts">
          <button class="icon-btn" data-action="watchlist-move" data-index="${i}" data-dir="-1" title="Move up" ${i === 0 ? 'disabled' : ''}>${icon('up', 16)}</button>
          <button class="icon-btn" data-action="watchlist-move" data-index="${i}" data-dir="1" title="Move down" ${i === episodes.length - 1 ? 'disabled' : ''}>${icon('down', 16)}</button>
          <button class="icon-btn" data-action="watchlist-remove" data-index="${i}" title="Take off the list">${icon('x', 16)}</button>
        </div>
      </div>`;
  };
  paint(`<div class="page">
    <div class="page-head">
      <div><h1 class="page-title">Watch list</h1><div class="page-sub">${episodes.length ? `${plural(episodes.length, 'recording')} · about ${esc(fmt.dur(total))} to watch, one after another` : 'Recordings to watch one after another'}</div></div>
      ${episodes.length ? `<div class="page-head-actions">
        <button class="btn btn-ghost btn-sm" data-action="watchlist-clear">Clear list</button>
        <button class="btn btn-primary" data-action="watchlist-play">${icon('play', 15)}Play all</button>
      </div>` : ''}
    </div>
    ${episodes.length ? `<div class="list">${episodes.map(row).join('')}</div>
      <p class="dim" style="margin-top:12px;font-size:12.5px">Click a recording to start from there. Ones you watch to the end come off the list.</p>`
      : emptyState('Your Watch list is empty', 'On a show’s page, tick the episodes you want and choose Add to watch list. Add from as many shows as you like, then play them one after another.', '<a class="btn btn-primary" href="#/library">Go to the Library</a>')}
  </div>`);
};

function findEpisode(id) {
  return state.episodes.find(e => e.id === id) || (state.inProgress || []).find(e => e.id === id)
    || (state.stream.list || []).find(e => e.id === id) || ((state.run && state.run.eps) || []).find(e => e.id === id) || null;
}

function chooseResume(ep) {
  const left = fmt.dur((ep.duration || 0) - (ep.position || 0));
  return openModal(`
    <div class="dialog-body">
      <div class="dialog-title">${esc(episodeTitle(ep))}</div>
      <div class="dialog-text">You stopped at ${fmtClock(ep.position)}${left ? ` (${left} left)` : ''}.</div>
    </div>
    <div class="dialog-foot">
      <button class="btn" data-action="modal-value" data-value="start">Start from beginning</button>
      <button class="btn btn-primary" data-action="modal-value" data-value="resume" data-autofocus>${icon('play', 14)}Resume from ${fmtClock(ep.position)}</button>
    </div>`);
}

// Save progress / watched on the Tablo and mirror it locally. keepalive lets it finish while closing.
function sendProgress(id, body, keepalive = false) {
  const url = body.watched !== undefined
    ? `/api/episodes/${encodeURIComponent(id)}/watched`
    : `/api/episodes/${encodeURIComponent(id)}/progress`;
  fetch(url, { method: 'POST', headers: API_HEADERS, body: JSON.stringify(body), keepalive })
    .then(r => { if (!r.ok) throw new Error(r.status); })
    .catch(err => console.warn('Saving progress failed:', err));
  applyProgressLocally(id, body);
}

function applyProgressLocally(id, body) {
  for (const list of [state.episodes, state.inProgress || []]) {
    const ep = list.find(e => e.id === id);
    if (!ep) continue;
    if (body.watched === true) { ep.status = 'Watched'; }
    if (body.watched === false) { ep.status = 'Unwatched'; ep.position = 0; }
    if (body.position !== undefined) { ep.position = body.position; ep.status = 'Unwatched'; }
  }
  if (state.show) {
    state.show.unwatched_count = state.episodes.filter(e => e.status !== 'Watched').length;
  }
  state.shows = null;
}

async function setWatched(id, watched) {
  try {
    const res = await api(`/api/episodes/${encodeURIComponent(id)}/watched`, { method: 'POST', body: JSON.stringify({ watched }) });
    applyProgressLocally(id, { watched });
    if (res.show) mergeShow(res.show);
    toast(watched ? 'Marked as watched' : 'Marked as unwatched', 'success');
    rerenderAfterProgress();
  } catch (err) {
    toast(`Couldn't update: ${err.message}`, 'error');
  }
}

async function markShowWatched(watched) {
  if (!state.show) return;
  try {
    const res = await api(`/api/shows/mark_watched?show_id=${encodeURIComponent(state.show.id)}&watched=${watched}`, { method: 'POST' });
    (res.changed_ids || []).forEach(id => applyProgressLocally(id, { watched }));
    if (res.show) mergeShow(res.show);
    toast(`${watched ? 'Marked' : 'Unmarked'} ${plural((res.changed_ids || []).length, 'episode')} as watched`, 'success');
    if (res.errors && res.errors.length) toast(`${res.errors.length} couldn't be updated: ${res.errors[0]}`, 'error');
    rerenderAfterProgress();
  } catch (err) {
    toast(`Couldn't update: ${err.message}`, 'error');
  }
}

function rerenderAfterProgress() {
  const name = parseRoute().name;
  if (name === 'show' && state.show) {
    const scroll = view().scrollTop;
    renderShowPage();
    view().scrollTop = scroll;
  } else if (name === 'home') {
    refreshCurrentPageQuietly();
  } else if (name === 'watchlist') {
    route();
  }
}

// Antenna channels use a tuner the Tablo keeps for a while after you stop watching. Before tuning,
// warn if that would leave too few tuners for recordings starting soon (or none are free).
async function watchLiveChecked(channelId, name, kind) {
  if (await tunerOk(kind, name)) player.watchLive(channelId, name, kind);
}

// Before taking an antenna tuner: warn if that would leave too few for recordings about to start
async function tunerOk(kind, name) {
  if (kind === 'ota') {
    let c = null;
    try { c = await api('/api/live/tune_check'); } catch { /* don't block watching on a failed check */ }
    if (c && (c.warn || c.no_free_tuner)) {
      const heldNote = c.held ? ` (${c.held} still held from live TV closed recently; the Tablo frees those on its own)` : '';
      let text;
      if (c.no_free_tuner) {
        text = `All ${c.total} antenna tuners are busy${heldNote}. Tuning may fail until one frees up.`;
      } else {
        const first = c.recordings_soon[0];
        const others = c.recordings_soon.length - 1;
        text = `${first.title}${others > 0 ? ` and ${plural(others, 'other recording')}` : ''} will start recording at ${fmt.time(first.start)}. ` +
          `Watching ${name} now would leave ${plural(c.free_after_tuning, 'free tuner')}${heldNote}, so ${others > 0 ? 'some recordings' : 'the recording'} could fail.`;
      }
      return confirmDialog({ title: 'Not enough tuners', text, confirm: 'Watch anyway', danger: true });
    }
  }
  return true;
}

// ---------------------------------------------------------------------------
// Picture quality meter (live antenna channels). The Tablo doesn't report signal strength, so this
// is the share of the picture arriving intact, worked out from what FFmpeg throws away
// (app/reception.py): a badge with bars beside the channel name, and a 5-minute graph on click.
// ---------------------------------------------------------------------------
const reception = {
  sessionId: null, timer: null, data: null,
  LABELS: { clean: 'Clean', minor: 'Minor glitches', breaking: 'Breaking up', losing: 'Losing signal',
            no_signal: 'No signal', starting: 'Measuring' },

  start(sessionId) {
    this.stop();
    this.sessionId = sessionId;
    this.render();
    this.timer = setInterval(() => this.poll(), 2000);
    this.poll();
  },

  stop() {
    clearInterval(this.timer);
    this.timer = null;
    this.sessionId = null;
    this.data = null;
    $('#reception').classList.add('hidden');
    $('#receptionPanel').classList.add('hidden');
  },

  async poll() {
    const id = this.sessionId;
    if (!id) return;
    let d = null;
    try { d = await api(`/api/live/reception/${id}`); } catch { return; }
    if (id !== this.sessionId) return;  // changed channel meanwhile
    if (!d.available) { this.stop(); return; }
    this.data = d;
    this.render();
  },

  bars(score) {
    if (score == null) return 0;
    return score >= 99 ? 5 : score >= 90 ? 4 : score >= 70 ? 3 : score >= 50 ? 2 : score > 0 ? 1 : 0;
  },

  render() {
    const el = $('#reception');
    const d = this.data || { state: 'starting', score: null };
    const on = this.bars(d.score);
    const text = d.state === 'no_signal' ? 'No signal' : d.score == null ? 'Signal …' : `Signal ${d.score}%`;
    el.className = `reception q-${d.state}`;
    el.title = `${this.LABELS[d.state]}: picture quality from your antenna (click for the last 5 minutes)`;
    el.innerHTML = `<span class="bars">${[1, 2, 3, 4, 5].map(n => `<i class="${n <= on ? 'on' : ''}"></i>`).join('')}</span>${esc(text)}`;
    if (!$('#receptionPanel').classList.contains('hidden')) this.renderPanel();
  },

  toggle() {
    const panel = $('#receptionPanel');
    panel.classList.toggle('hidden');
    if (!panel.classList.contains('hidden')) this.renderPanel();
  },

  renderPanel() {
    const d = this.data || { history: [], state: 'starting', score: null };
    const W = 360, H = 96, SPAN = 300;
    const x = ago => W * (1 + ago / SPAN), y = s => H - 4 - (H - 8) * s / 100;
    const pts = d.history.map(([ago, s]) => `${x(ago).toFixed(1)},${y(s).toFixed(1)}`).join(' ');
    const color = { clean: 'var(--ok)', minor: '#b5d334', breaking: 'var(--warn)', losing: 'var(--rec)', no_signal: 'var(--rec)' }[d.state] || 'var(--text-2)';
    const worst = d.worst ? `Worst: ${d.worst.score}% ${fmtAgo(d.worst.seconds_ago)}` : 'No glitches in the last 5 minutes';
    const drops = d.dropouts ? ` · ${plural(d.dropouts, 'dropout')}` : '';
    $('#receptionPanel').innerHTML = `
      <div class="rp-head"><span>Signal quality</span><span class="dim">${esc(state.stream.channelName || '')}</span>
        <span style="color:${color}">${d.state === 'no_signal' ? 'No signal' : d.score == null ? '…' : `now ${d.score}%`}</span></div>
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <line x1="0" x2="${W}" y1="${y(100)}" y2="${y(100)}" stroke="rgba(255,255,255,0.12)"/>
        <line x1="0" x2="${W}" y1="${y(50)}" y2="${y(50)}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3 4"/>
        ${pts ? `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>` : ''}
      </svg>
      <div class="rp-axis"><span>5 min ago</span><span>now</span></div>
      <div class="rp-foot">${d.history.length ? esc(worst + drops) : 'Measuring…'}</div>
      <div class="rp-note">How much of the picture is arriving intact from your antenna, updated every second. Handy while aiming an antenna. (The Tablo doesn't report signal strength itself.)</div>`;
  },
};

function fmtAgo(seconds) {
  if (seconds < 60) return `${seconds} s ago`;
  return `${Math.round(seconds / 60)} min ago`;
}

// ---------------------------------------------------------------------------
// Two channels at once (live TV). The player keeps running the first channel (timeline, pause,
// rewind); this runs the second in #video2. Both go through Web Audio: a gain per channel picks the
// one you hear (a muted element would also be silent to the level meter), and an analyser per
// channel notices when the one you aren't hearing suddenly gets loud.
// ---------------------------------------------------------------------------
const dual = {
  on: false, picking: false, active: 'main', layout: 'side', s: {},
  LAYOUTS: ['side', 'pip', 'full'],
  LAYOUT_NAMES: { side: 'Side by side', pip: 'Big and small', full: 'Full screen (Tab flips)' },

  // "+ Second channel": pick one from the channel list
  async add() {
    if (this.on || !(state.stream.channelId || state.stream.episodeId)) return;
    this.picking = true;
    await player.toggleChannels(true);
  },

  async start(channelId, name, kind) {
    this.picking = false;
    player.toggleChannels(false);
    if (channelId === state.stream.channelId) { toast('That channel is already playing'); return; }
    if (!await tunerOk(kind, name)) return;
    this.ensureAudio();
    if (!await this.load(channelId, name, kind)) return;
    this.on = true;
    this.active = 'main';
    player.el().classList.add('dual');
    $('#paneSecond').classList.remove('hidden');
    this.setLayout(this.layout);
    player.showTimeline(true);
    this.applySound();
    this.startMeter();
    checkTuners();
  },

  async load(channelId, name, kind) {
    const v = $('#video2');
    this.teardown();
    try {
      const res = await api('/api/live/tune', { method: 'POST', body: JSON.stringify({ channel_id: channelId, transcode: true, kind }) });
      this.s = { channelId, name, kind, sessionId: res.session_id, url: res.stream_url };
    } catch (err) {
      toast(`Couldn't tune ${name}: ${err.message}`, 'error');
      return false;
    }
    if (window.Hls && Hls.isSupported()) {
      const hls = new Hls({ enableWorker: true, backBufferLength: 30, maxBufferLength: 30 });
      hls.loadSource(this.s.url);
      hls.attachMedia(v);
      hls.on(Hls.Events.MANIFEST_PARSED, () => v.play().catch(() => {}));
      hls.on(Hls.Events.ERROR, (evt, data) => {
        if (!data.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
        else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
      });
      this.hls = hls;
    } else {
      v.src = this.s.url;
      v.play().catch(() => {});
    }
    v.volume = player.video().volume;
    v.muted = player.video().muted;
    this.render();
    return true;
  },

  // Change the second channel (from the channel list while you're hearing it)
  async retune(channelId, name, kind) {
    if (channelId === this.s.channelId || channelId === state.stream.channelId) return;
    if (!await tunerOk(kind, name)) return;
    this.stopSession();
    await this.load(channelId, name, kind);
    this.applySound();
    checkTuners();
  },

  teardown() {
    if (this.hls) { this.hls.destroy(); this.hls = null; }
    const v = $('#video2');
    v.pause();
    v.removeAttribute('src');
    v.load();
  },

  stopSession(keepalive = false) {
    if (this.s.sessionId) {
      fetch('/api/live/stop', { method: 'POST', headers: API_HEADERS, body: JSON.stringify({ session_id: this.s.sessionId }), keepalive }).catch(() => {});
    }
    this.s = {};
  },

  // Back to one channel (the second one's tuner is freed)
  stop() {
    this.picking = false;
    if (!this.on) return;
    this.on = false;
    this.stopSession();
    this.teardown();
    this.end();
  },

  end() {
    this.on = false;
    this.active = 'main';
    clearInterval(this.meterTimer);
    const p = player.el();
    p.classList.remove('dual', 'dual-side', 'dual-pip', 'dual-full');
    $('#paneSecond').classList.add('hidden');
    $('#paneMain').classList.add('active');
    $('#paneSecond').classList.remove('active', 'buzz');
    this.applySound();
    player.applyCaptions();
    if (player.isOpen()) player.showTimeline(true);
    setTimeout(checkTuners, 1000);
  },

  // The × on a picture: closing the first channel keeps the second playing as the only one
  close(pane) {
    if (!this.on) return;
    if (pane === 'second') { this.stop(); return; }
    const s = this.s;
    player.finishEpisode();  // a recording: keep where you got to
    player.stopStream();
    player.teardown();
    this.teardown();
    this.s = {};
    Object.assign(state.stream, { episodeId: null, channelId: s.channelId, channelName: s.name, channelKind: s.kind, sessionId: s.sessionId });
    $('#playerTitle').textContent = `Live · ${s.name}`;
    this.end();
    player.start(s.url, 'Live');
  },

  swap() {
    if (!this.on) return;
    this.active = this.active === 'main' ? 'second' : 'main';
    this.applySound();
    player.renderChannels();
  },

  paneClick(pane) {
    if (this.active !== pane) this.swap();
    else player.togglePlay();
  },

  setLayout(layout) {
    this.layout = layout;
    const p = player.el();
    p.classList.remove('dual-side', 'dual-pip', 'dual-full');
    if (this.on) p.classList.add(`dual-${layout}`);
  },

  cycleLayout() {
    if (!this.on) return;
    this.setLayout(this.LAYOUTS[(this.LAYOUTS.indexOf(this.layout) + 1) % this.LAYOUTS.length]);
    toast(this.LAYOUT_NAMES[this.layout]);
  },

  // Labels: channel name, and a speaker on the one you're hearing
  render() {
    const label = (el, name, on) => { el.innerHTML = `${on ? icon('volume', 14) : ''}<span>${esc(name || '')}</span>`; };
    label($('#labelMain'), state.stream.channelId ? state.stream.channelName : $('#playerTitle').textContent, this.active === 'main');
    label($('#labelSecond'), this.s.name, this.active === 'second');
  },

  ensureAudio() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.ctx.resume().catch(() => {});
    for (const v of [$('#video'), $('#video2')]) {
      if (v.__audio) continue;
      const src = this.ctx.createMediaElementSource(v);
      const analyser = this.ctx.createAnalyser();
      analyser.fftSize = 2048;
      const gain = this.ctx.createGain();
      src.connect(analyser);
      src.connect(gain).connect(this.ctx.destination);
      v.__audio = { analyser, gain, samples: new Float32Array(2048) };
    }
  },

  applySound() {
    const main = $('#video').__audio, second = $('#video2').__audio;
    if (main) main.gain.gain.value = !this.on || this.active === 'main' ? 1 : 0;
    if (second) second.gain.gain.value = this.on && this.active === 'second' ? 1 : 0;
    $('#paneMain').classList.toggle('active', !this.on || this.active === 'main');
    $('#paneSecond').classList.toggle('active', this.on && this.active === 'second');
    player.applyCaptions();
    this.render();
  },

  // "Something's happening": the channel you aren't hearing gets much louder than it has been
  startMeter() {
    clearInterval(this.meterTimer);
    this.level = { fast: 0, slow: 0, ticks: 0, quietUntil: 0 };
    this.meterTimer = setInterval(() => this.meter(), 200);
  },

  meter() {
    const silent = this.active === 'main' ? $('#video2') : $('#video');
    const a = silent.__audio;
    if (!this.on || !a || silent.paused) return;
    a.analyser.getFloatTimeDomainData(a.samples);
    let sum = 0;
    for (const x of a.samples) sum += x * x;
    const rms = Math.sqrt(sum / a.samples.length);
    const L = this.level;
    L.fast = L.fast * 0.7 + rms * 0.3;
    L.ticks++;
    const loud = L.ticks > 50 && L.fast > Math.max(0.02, L.slow * 2.2);
    if (loud && Date.now() > L.quietUntil) {
      L.quietUntil = Date.now() + 30000;
      const pane = this.active === 'main' ? $('#paneSecond') : $('#paneMain');
      pane.classList.remove('buzz');
      void pane.offsetWidth;
      pane.classList.add('buzz');
      const label = pane.querySelector('.pane-label span');
      const was = label.textContent;
      label.textContent = `${was} · Something’s happening`;
      setTimeout(() => { pane.classList.remove('buzz'); this.render(); }, 6000);
    }
    if (!loud) L.slow = L.ticks < 25 ? (L.slow + rms) / 2 : L.slow * 0.99 + rms * 0.01;
  },
};

function openVlc(url) {
  window.location.href = url;
  toast('Downloaded a .m3u playlist. Open it with VLC to play.');
}

// ---------------------------------------------------------------------------
// Global search
// ---------------------------------------------------------------------------
function hideSearch() {
  const box = $('#searchResults');
  if (box) { box.classList.add('hidden'); box.innerHTML = ''; }
}

const runSearch = debounce(async q => {
  const box = $('#searchResults');
  q = q.trim();
  if (!q) { hideSearch(); return; }
  const shows = await loadShows().catch(() => []);
  const lib = shows.filter(s => s.title.toLowerCase().includes(q.toLowerCase())).slice(0, 5);
  let guide = [];
  try {
    guide = cacheGuide((await api(`/api/guide/shows?search=${encodeURIComponent(q)}&sort=soonest&limit=6`)).shows);
  } catch { /* library results still useful */ }
  if ($('#globalSearch').value.trim() !== q) return;

  const thumb = url => imgUrl(url) ? `<img src="${esc(imgUrl(url))}" alt="" loading="lazy">` : '<div class="thumb-fallback"></div>';
  let html = '';
  if (lib.length) {
    html += '<div class="search-group-label">Your recordings</div>' + lib.map(s => `
      <div class="search-item" data-action="open-show" data-id="${esc(s.id)}">${thumb(s.cover_url)}
        <div><div class="search-item-title">${esc(s.title)}</div><div class="search-item-sub">${plural(s.episode_count, 'episode')}${s.unwatched_count ? ` · ${s.unwatched_count} unwatched` : ''}</div></div></div>`).join('');
  }
  if (guide.length) {
    html += '<div class="search-group-label">In the guide</div>' + guide.map(g => `
      <div class="search-item" data-action="open-series" data-path="${esc(g.path)}">${thumb(g.cover_url)}
        <div><div class="search-item-title">${esc(g.title)}</div><div class="search-item-sub">${g.next_airing ? esc(fmt.when(g.next_airing.datetime)) : 'No upcoming airings'}${g.schedule_rule && g.schedule_rule !== 'none' ? ' · Recording' : ''}</div></div></div>`).join('');
    html += `<div class="search-item" data-action="search-all" data-q="${esc(q)}"><div class="thumb-fallback" style="display:grid;place-items:center">${icon('search', 16)}</div><div class="search-item-title">See all guide results for “${esc(q)}”</div></div>`;
  }
  box.innerHTML = html || `<div class="search-empty">Nothing found for “${esc(q)}”</div>`;
  box.classList.remove('hidden');
  const first = box.querySelector('.search-item');
  first && first.classList.add('selected');
}, 180);

function moveSearchSelection(delta) {
  const items = $$('#searchResults .search-item');
  if (!items.length) return;
  let i = items.findIndex(el => el.classList.contains('selected'));
  items.forEach(el => el.classList.remove('selected'));
  i = (i + delta + items.length) % items.length;
  items[i].classList.add('selected');
  items[i].scrollIntoView({ block: 'nearest' });
}

// ---------------------------------------------------------------------------
// Event wiring
// ---------------------------------------------------------------------------
const ACTIONS = {
  'back': () => history.length > 1 ? history.back() : (location.hash = '#/'),
  'retry-route': () => route(),
  'refresh-library': () => refreshLibrary(),
  'row-scroll': el => { const row = document.getElementById(el.dataset.target); row && row.scrollBy({ left: Number(el.dataset.dir) * row.clientWidth * 0.9, behavior: 'smooth' }); },
  'toggle-desc': el => el.classList.toggle('expanded'),

  'open-show': el => { hideSearch(); $('#globalSearch').value = ''; location.hash = `#/show/${encodeURIComponent(el.dataset.id)}`; },
  'open-series': el => { hideSearch(); $('#globalSearch').value = ''; location.hash = `#/series/${encodeURIComponent(el.dataset.path)}`; },
  'search-all': el => { hideSearch(); $('#globalSearch').value = ''; state.guide.q = el.dataset.q; state.guide.highlight = ''; location.hash = `#/guide?q=${encodeURIComponent(el.dataset.q)}`; },

  'library-filter': el => { state.library.filter = el.dataset.value; $$('[data-action="library-filter"]').forEach(b => b.classList.toggle('active', b === el)); renderLibraryGrid(); },
  'library-layout': el => { state.library.layout = el.dataset.value; save('tv_lib_layout', el.dataset.value); $$('[data-action="library-layout"]').forEach(b => b.classList.toggle('active', b === el)); renderLibraryGrid(); },

  'play-ep': el => player.playEpisode(el.dataset.id, el.dataset.mode),
  'ep-menu': el => {
    const id = el.dataset.id;
    const ep = findEpisode(id) || {};
    const inProgress = ep.status !== 'Watched' && (ep.position || 0) > 30;
    openMenu(el, [
      { label: inProgress ? `Resume from ${fmtClock(ep.position)}` : 'Play in browser', icon: 'play', run: () => player.playEpisode(id, 'resume') },
      ...(inProgress ? [{ label: 'Play from beginning', icon: 'refresh', run: () => player.playEpisode(id, 'start') }] : []),
      ep.status === 'Watched'
        ? { label: 'Mark as unwatched', icon: 'x', run: () => setWatched(id, false) }
        : { label: 'Mark as watched', icon: 'check', run: () => setWatched(id, true) },
      // Partly watched: start over (clears the resume point, on the Tablo too)
      ...(inProgress ? [{ label: 'Mark as unwatched', icon: 'x', run: () => setWatched(id, false) }] : []),
      { label: 'Add to watch list', icon: 'queue', run: () => addToWatchList([id]) },
      { label: 'Open in VLC', icon: 'external', run: () => openVlc(`/api/episodes/${encodeURIComponent(id)}/playlist.m3u`) },
      { label: 'Export MP4', icon: 'download', run: () => exportEpisode(id) },
      ...(ep.incomplete ? [{ label: 'Record again…', icon: 'refresh', run: () => rerecordDialog(id) }] : []),
      ...(ep.recording_state === 'finished' && !['done', 'analyzing', 'queued'].includes(ep.commercials)
        ? [{ label: 'Find commercials', icon: 'next', run: () => findCommercials(id) }] : []),
      ep.protected
        ? { label: 'Unprotect', icon: 'lock', run: () => setProtected(id, false) }
        : { label: 'Protect from deletion', icon: 'lock', run: () => setProtected(id, true) },
      { sep: true },
      { label: 'Delete recording', icon: 'trash', danger: true, run: () => deleteEpisode(id) },
    ]);
  },
  'delete-watched': () => deleteWatched(),
  'bulk-delete': () => bulkDelete(),
  'bulk-export': () => bulkExport(),
  // Ticked episodes in the order they're listed on the page
  'bulk-watch': () => startRun(state.episodes.filter(e => state.selected.has(e.id)), false),
  'bulk-watchlist': () => { addToWatchList(state.episodes.filter(e => state.selected.has(e.id)).map(e => e.id)); ACTIONS['bulk-clear'](); },
  'watchlist-play': () => startRun(state.watchList || [], true),
  'watchlist-play-from': el => startRun((state.watchList || []).slice(Number(el.dataset.index)), true),
  'watchlist-move': el => {
    const ids = (state.watchList || []).map(e => e.id), i = Number(el.dataset.index), j = i + Number(el.dataset.dir);
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    saveWatchList(ids);
  },
  'watchlist-remove': el => saveWatchList((state.watchList || []).filter((_, i) => i !== Number(el.dataset.index)).map(e => e.id)),
  'watchlist-clear': async () => {
    if (await confirmDialog({ title: 'Clear your Watch list?', text: 'The recordings stay on your Tablo; they just come off the list.', confirm: 'Clear list' })) saveWatchList([]);
  },
  'bulk-clear': () => { state.selected.clear(); $$('.ep-row').forEach(r => r.classList.remove('selected')); $$('[data-change="ep-select"], [data-change="ep-select-all"]').forEach(c => { c.checked = false; }); updateBulkBar(); },

  'rec-menu': el => recMenu(el, el.dataset.path),
  'set-rule': el => { if (!el.classList.contains('active')) setRule(el.dataset.path, el.dataset.rule); },
  'stop-rule': async el => {
    const g = state.guideCache.get(el.dataset.path) || {};
    if (await confirmDialog({ title: `Stop recording ${g.title || 'this series'}?`, text: 'Existing recordings are kept. Future episodes won’t be recorded.', confirm: 'Stop recording', danger: true })) setRule(el.dataset.path, 'none');
  },
  'toggle-airing': el => toggleAiring(el),
  'cancel-recording': async el => {
    const ok = await confirmDialog({
      title: `Skip this recording of ${el.dataset.title}?`,
      text: el.dataset.streaming ? 'Your Tablo won’t record this airing.' : 'Only this airing is skipped. The series stays scheduled.',
      confirm: 'Skip recording', danger: true,
    });
    if (!ok) return;
    try {
      if (el.dataset.streaming) await api('/api/streaming/record', { method: 'POST', body: JSON.stringify({ airing_id: el.dataset.path, scheduled: false }) });
      else await api('/api/guide/episodes/schedule', { method: 'POST', body: JSON.stringify({ path: el.dataset.path, scheduled: false }) });
      toast('Recording skipped', 'success');
      await loadUpcoming();
      if (parseRoute().name === 'scheduled') {
        $('#tabUpcomingCount').textContent = state.upcoming ? state.upcoming.count : '';
        const scroll = view().scrollTop;
        renderUpcomingList();
        view().scrollTop = scroll;
      }
    } catch (err) {
      toast(`Couldn't skip it: ${err.message}`, 'error');
    }
  },
  'sync-guide': () => syncGuide(),
  'guide-highlight': el => { state.guide.highlight = el.dataset.value; state.guide.sort = el.dataset.value ? 'soonest' : 'primetime'; const s = $('[data-change="guide-sort"]'); if (s) s.value = state.guide.sort; loadGuide(routeToken); },
  'guide-more': el => { el.disabled = true; loadGuide(routeToken, true); },
  'guide-sport': el => { state.guide.sport = el.dataset.value; renderGuideGrid(); },
  'export-cancel': async el => {
    const ok = await confirmDialog({ title: 'Cancel this export?', text: `${el.dataset.name}: the part made so far is deleted, and the next export in the list starts.`, confirm: 'Cancel export', danger: true });
    if (!ok) return;
    try {
      await api(`/api/exports/${encodeURIComponent(el.dataset.id)}/cancel`, { method: 'POST' });
      toast('Export cancelled');
    } catch (err) { toast(err.message, 'error'); }
    if (parseRoute().name === 'downloads') route();
  },
  'export-remove': async el => {
    try { await api(`/api/exports/${encodeURIComponent(el.dataset.id)}`, { method: 'DELETE' }); } catch (err) { toast(err.message, 'error'); }
    if (parseRoute().name === 'downloads') route();
  },
  'guide-retry': async el => {
    el.disabled = true;
    try {
      await api('/api/guide/sync', { method: 'POST' });
      $('#guidePartialBanner').classList.add('hidden');
      toast('Loading the TV guide again…');
    } catch (err) { toast(err.message, 'error'); }
    el.disabled = false;
  },
  'ant-go': () => {
    if (antenna.sessionId || antenna.starting) { antenna.stop(); return; }
    const c = antenna.channels().find(x => x.channel_id === $('#antChannel').value);
    if (c) antenna.start(c);
  },
  'ant-tone': () => antenna.toggleTone(),
  'ant-all': () => (antenna.scan ? antenna.cancelScan() : antenna.checkAll()),
  'ant-save': () => antenna.saveSpot(),
  'ant-delete': el => antenna.deleteSpot(Number(el.dataset.index)),
  'guide-reload': () => loadGuide(routeToken),
  'scheduled-filter': el => { state.scheduled.filter = el.dataset.value; renderScheduledList(); },

  'epg-cat': el => { state.epgCategory = el.dataset.value; $$('[data-action="epg-cat"]').forEach(b => b.classList.toggle('active', b === el)); renderEpg(); },
  'epg-shift': el => { state.epgOffset += Number(el.dataset.dir) * 3; $$('[data-action="epg-now"]').forEach(b => b.classList.toggle('active', state.epgOffset === 0)); loadEpg(routeToken, true); },
  'epg-now': el => { state.epgOffset = 0; el.classList.add('active'); loadEpg(routeToken, true); },
  'epg-cell': el => openAiringModal(el.dataset.key),
  'watch-live': el => watchLiveChecked(el.dataset.id, el.dataset.name, el.dataset.kind),

  'modal-ok': () => closeModal(true),
  'modal-value': el => closeModal(el.dataset.value),
  'mark-show-watched': el => markShowWatched(el.dataset.value !== 'false'),
  'modal-cancel': () => closeModal(false),
  'modal-watch-live': el => { closeModal(false); watchLiveChecked(el.dataset.id, el.dataset.name, el.dataset.kind); },
  'modal-live-vlc': el => { closeModal(false); openVlc(`/api/live/vlc/${encodeURIComponent(el.dataset.id)}`); setTimeout(checkTuners, 2500); },
  'modal-series': el => { closeModal(false); location.hash = `#/series/${encodeURIComponent(el.dataset.path)}`; },

  'close-player': () => player.close(),
  'tuner-panel': () => toggleTunerPanel(),
  'stop-app': async () => {
    const ok = await confirmDialog({
      title: 'Stop TabloView?',
      text: 'It stops on this computer, along with anything playing or exporting. Your Tablo keeps recording as usual.',
      confirm: 'Stop TabloView', danger: true,
    });
    if (!ok) return;
    try {
      await api('/api/system/stop', { method: 'POST' });
    } catch (err) {
      toast(`Couldn't stop TabloView: ${err.message}`, 'error');
      return;
    }
    player.close();
    document.body.innerHTML = `<div class="empty" style="margin-top:20vh"><h3>TabloView has stopped</h3>
      <p>You can close this tab. To use TabloView again, run its start script as before.</p></div>`;
  },
  'guide-type': el => {
    state.guide.category = el.dataset.value;
    $('#guideTypes').innerHTML = guideTypeChips();
    loadGuide(routeToken);
  },
  'fast-category': el => { state.fast.category = el.dataset.value; loadStreaming(routeToken); },
  'fast-show': el => openStreamShow(el.dataset.id),
  'fast-record': el => recordStreaming(el),
  'fast-reload': () => loadStreaming(routeToken),
  'player-vlc': () => player.openInVlc(),
  'space-delete-watched': el => deleteWatchedForShow(el),
  'fix-conflicts': () => fixConflicts(),
  'record-missed-new': el => recordMissedNew(el.dataset.path ? [el.dataset.path] : missedNew(state.upcoming).map(a => a.path)),
  'swap-recording': async el => {
    el.disabled = true;
    try {
      const res = await api('/api/guide/conflicts/swap', { method: 'POST', body: JSON.stringify({ skip_path: el.dataset.skip, record_path: el.dataset.record }) });
      if (res.success) toast('Recording moved to the other airing', 'success');
      else toast(res.error, 'error');
      afterScheduleFix();
    } catch (err) { el.disabled = false; toast(`Couldn't change the recording: ${err.message}`, 'error'); }
  },
  'skip-conflict': async el => {
    const ok = await confirmDialog({ title: `Don’t record ${el.dataset.title}?`, text: 'Your Tablo will skip this airing. The series stays scheduled.', confirm: 'Don’t record' });
    if (!ok) { fixConflicts(); return; }
    try {
      await api('/api/guide/episodes/schedule', { method: 'POST', body: JSON.stringify({ path: el.dataset.path, scheduled: false }) });
      toast('Skipped', 'success');
      afterScheduleFix();
    } catch (err) { toast(`Couldn't skip: ${err.message}`, 'error'); }
  },
  'pb-play': () => player.togglePlay(),
  'pb-back': () => player.skip(-10),
  'pb-fwd': () => player.skip(30),
  'pb-mute': () => player.toggleMute(),
  'pb-full': () => player.toggleFullscreen(),
  'pb-pip': () => player.togglePip(),
  'pb-live': () => player.goLive(),
  'pb-help': () => player.showHelp(),
  'export-folder': el => chooseExportFolder(el),
  'export-folder-reset': async () => {
    try { await api('/api/system/export_folder', { method: 'POST', body: JSON.stringify({ path: null }) }); toast('Exports will be saved to Downloads\\TabloView again'); route(); }
    catch (err) { toast(err.message, 'error'); }
  },
  'dual-add': () => dual.add(),
  'dual-layout': () => dual.cycleLayout(),
  'dual-close': el => dual.close(el.dataset.pane),
  'calendar-help': () => openModal(`
    <div class="dialog-body">
      <div class="dialog-title">Add your recordings to a calendar</div>
      <div class="dialog-text">Download a calendar file with everything your Tablo will record in the next two weeks, then import it:</div>
      <ol class="whatsnew-list">
        <li><b>Google Calendar:</b> on calendar.google.com, open Settings (gear) → <b>Import &amp; export</b> → choose the file. Tip: first create a calendar named “TabloView” (Settings → Add calendar) and import into it, so it’s easy to hide or remove.</li>
        <li><b>Outlook:</b> open the file, or File → Open &amp; Export → Import.</li>
        <li><b>iPhone / Mac:</b> open the file and choose a calendar.</li>
      </ol>
      <div class="dialog-text" style="margin-top:12px">It doesn’t update itself: import a new file to add recordings you’ve set up since. Importing again doesn’t duplicate anything, but recordings already in the calendar stay as they were, so if times change or you skip some, delete the TabloView calendar and import a fresh file.</div>
    </div>
    <div class="dialog-foot">
      <button class="btn" data-action="modal-cancel">Close</button>
      <a class="btn btn-primary" href="/api/guide/upcoming.ics" download onclick="setTimeout(() => closeModal(true), 300)">${icon('download', 15)}Download calendar file</a>
    </div>`),
  'set-pin': async () => { if (await setPinDialog()) route(); },
  'pin-signout': async () => {
    if (!await confirmDialog({ title: 'Sign out other devices?', text: 'Every phone, tablet and other computer will have to enter the PIN again.', confirm: 'Sign out' })) return;
    try { await api('/api/lan/signout', { method: 'POST' }); toast('Other devices will have to enter the PIN again', 'success'); } catch (err) { toast(err.message, 'error'); }
  },
  'pb-cc': () => player.toggleCaptions(),
  'skip-break': () => player.skipBreak(),
  'rerecord': el => rerecordDialog(el.dataset.id),
  'rerecord-pick': async el => {
    el.disabled = true;
    try {
      await api('/api/guide/episodes/schedule', { method: 'POST', body: JSON.stringify({ path: el.dataset.path, scheduled: true }) });
      el.outerHTML = '<span class="tag tag-accent">Set to record</span>';
      toast('It will be recorded again', 'success');
    } catch (err) { el.disabled = false; toast(`Couldn't schedule it: ${err.message}`, 'error'); }
  },
  'pb-sleep': el => player.sleepMenu(el),
  'version-history': () => showVersionHistory(),
  'pb-channels': () => player.toggleChannels(),
  'pb-surf': el => player.surf(Number(el.dataset.dir)),
  'pb-tune': el => player.tune(el.dataset.id, el.dataset.name, el.dataset.kind),
  'pb-retune': () => { const s = state.stream; player.watchLive(s.channelId, s.channelName, s.channelKind); },
  'pb-recordings': () => { player.close(); location.hash = '#/library'; },
  'pb-record': () => player.recordLive(),
  'reception-panel': () => reception.toggle(),
  'upnext-play': () => player.playNext(),
  'upnext-cancel': () => player.hideUpNext(),

  'run-inspector': () => runInspector(),
  'logout': async () => {
    if (!await confirmDialog({ title: 'Sign out of Tablo?', text: 'TabloView will stop syncing until you sign in again.', confirm: 'Sign out', danger: true })) return;
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {});
    state.shows = null;
    state.scheduled.items = null;
    await loadStatus();
    route();
  },
  'pick-device': el => pickDevice(el.dataset.sid),
  'reauth': async () => {
    const ok = await confirmDialog({
      title: 'Sign in to Tablo again?',
      text: "You'll be signed out, then asked for your Tablo email and password. Your recordings and schedule on the Tablo aren't affected.",
      confirm: 'Continue',
    });
    if (!ok) return;
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {});
    state.shows = null;
    state.scheduled.items = null;
    await loadStatus();
    route();
  },
  'check-update': async el => {
    el.disabled = true;
    const u = await checkForUpdate(true);
    el.disabled = false;
    if (!u) toast("Couldn't check for updates", 'error');
    else if (u.error) toast(u.error, 'error');
    else if (u.update_available) toast(`Version ${u.latest} is available`, 'success');
    else toast(`You're on the latest version (${u.current})`, 'success');
    if (parseRoute().name === 'device') route();
  },
};

const INPUTS = {
  'library-q': el => { state.library.q = el.value; renderLibraryGrid(); },
  'guide-q': el => { state.guide.q = el.value; reloadGuide(); },
  'fast-q': el => { state.fast.q = el.value; reloadStreaming(); },
  'scheduled-q': el => { state.scheduled.q = el.value; renderScheduledList(); },
  'epg-q': debounce(el => { state.epgQuery = el.value.trim().toLowerCase(); renderEpg(); }, 180),
};

const CHANGES = {
  // Antenna helper: picking another channel while measuring switches to it
  'ant-channel': el => {
    const c = antenna.channels().find(x => x.channel_id === el.value);
    if (c && antenna.sessionId) antenna.start(c);
  },
  'library-sort': el => { state.library.sort = el.value; save('tv_lib_sort', el.value); renderLibraryGrid(); },
  'guide-category': el => { state.guide.category = el.value; loadGuide(routeToken); },
  'fast-recordable': el => { state.fast.recordable = el.checked; loadStreaming(routeToken); },
  'guide-rule': el => { state.guide.rule = el.value; loadGuide(routeToken); },
  'guide-sort': el => { state.guide.sort = el.value; loadGuide(routeToken); },
  'ep-select': el => {
    el.checked ? state.selected.add(el.dataset.id) : state.selected.delete(el.dataset.id);
    const row = el.closest('.ep-row');
    row && row.classList.toggle('selected', el.checked);
    const all = $('[data-change="ep-select-all"]');
    if (all) all.checked = state.selected.size === state.episodes.length;
    updateBulkBar();
  },
  'ep-select-all': el => {
    state.selected.clear();
    if (el.checked) state.episodes.forEach(e => state.selected.add(e.id));
    $$('[data-change="ep-select"]').forEach(c => { c.checked = el.checked; c.closest('.ep-row').classList.toggle('selected', el.checked); });
    updateBulkBar();
  },
  'allow-lan': async el => {
    const enable = el.checked;
    if (enable) {
      // A PIN first, so nothing on the network can use TabloView without it
      let st = {};
      try { st = await api('/api/lan/status'); } catch { /* ask anyway */ }
      if (!st.pin_set && !(await setPinDialog('Choose a PIN for other devices', 'Phones, tablets and other computers will ask for it once; this PC never does. If Windows asks, allow TabloView on Private networks only.'))) {
        el.checked = false;
        return;
      }
    }
    el.disabled = true;
    try {
      const res = await api('/api/settings', { method: 'POST', body: JSON.stringify({ allow_lan: enable }) });
      if (!res.restarting) { toast('Saved. Restart TabloView to apply.'); el.disabled = false; return; }
      toast('Restarting TabloView to apply…');
      await waitForServer();
      route();
    } catch (err) {
      toast(`Couldn't change network access: ${err.message}`, 'error');
      el.checked = !enable;
      el.disabled = false;
    }
  },
  'auto-sync': async el => {
    try {
      const res = await api('/api/settings', { method: 'POST', body: JSON.stringify({ auto_sync_minutes: Number(el.value) }) });
      toast(res.auto_sync_minutes ? `Checking for new recordings every ${res.auto_sync_minutes} minutes` : 'Automatic sync turned off');
    } catch (err) {
      toast(`Couldn't save: ${err.message}`, 'error');
    }
  },
  'show-keep': el => setKeep(el),
  'show-commercials': async el => {
    const s = state.show;
    try {
      const res = await api(`/api/shows/commercials?show_id=${encodeURIComponent(s.id)}`, { method: 'POST', body: JSON.stringify({ on: el.checked }) });
      if (res.show) mergeShow(res.show);
      toast(el.checked
        ? `TabloView will find the commercials in ${s.title}${res.waiting ? ` (${plural(res.waiting, 'recording')} to go; about 8 minutes per half hour, while nothing is playing)` : ''}`
        : `Commercials in ${s.title} won’t be looked for any more`, 'success');
    } catch (err) { el.checked = !el.checked; toast(err.message, 'error'); }
  },
  'show-cleanup': el => setCleanup(el),
  'buffer': el => { state.bufferTarget = parseInt(el.value, 10) || 8; save('tablo_buffer_target', state.bufferTarget); toast(`Buffer set to ${state.bufferTarget} seconds`); },
  'autoplay': el => { state.autoplay = el.checked; save('tablo_autoplay', el.checked ? '1' : '0'); },
  'start-page': el => {
    save('tv_start_page', el.value);
    toast(`TabloView will open on ${START_PAGES.find(([v]) => v === el.value)[1]}`);
  },
  'startup': async el => {
    try {
      const res = await api('/api/system/startup', { method: 'POST', body: JSON.stringify({ enabled: el.checked }) });
      el.checked = !!res.enabled;
      if (res.enabled) toast('TabloView will start in the tray when you sign in', 'success');
      else if (res.locked) { toast('Windows blocked this: turn TabloView on in Task Manager → Startup apps', 'error'); route(); }
      else toast('TabloView won’t start with Windows');
    } catch (err) { el.checked = !el.checked; toast(err.message, 'error'); }
  },
  'video-quality': async el => {
    try {
      await api('/api/settings', { method: 'POST', body: JSON.stringify({ video_quality: el.value }) });
      toast('Video quality saved. It applies to the next thing you play.');
      route();
    } catch (err) { toast(err.message, 'error'); }
  },
  'rerecord-failed': async el => {
    try {
      await api('/api/settings', { method: 'POST', body: JSON.stringify({ rerecord_failed: el.checked }) });
      toast(el.checked ? 'Failed recordings will be recorded again when they rerun' : 'Failed recordings won’t be recorded again automatically');
    } catch (err) { el.checked = !el.checked; toast(err.message, 'error'); }
  },
  'skip-commercials': async el => {
    try {
      await api('/api/settings', { method: 'POST', body: JSON.stringify({ skip_commercials: el.checked }) });
      toast(el.checked ? 'Commercial breaks will be skipped automatically' : 'A Skip break button will appear instead');
    } catch (err) { el.checked = !el.checked; toast(err.message, 'error'); }
  },
  'skip-dropouts': async el => {
    try {
      await api('/api/settings', { method: 'POST', body: JSON.stringify({ skip_dropouts: el.checked }) });
      toast(el.checked ? 'Signal dropouts will be skipped automatically' : 'A Skip dropout button will appear instead');
    } catch (err) { el.checked = !el.checked; toast(err.message, 'error'); }
  },
  'export-format': async el => {
    try {
      await api('/api/settings', { method: 'POST', body: JSON.stringify({ export_format: el.value }) });
      toast(el.value === 'smaller' ? 'Exports will be converted to smaller files' : 'Exports will keep the original video');
    } catch (err) { toast(err.message, 'error'); }
  },
  'logo-style': async el => {
    try {
      await api('/api/settings', { method: 'POST', body: JSON.stringify({ logo_style: el.value }) });
      state.epg = null;  // channel lists load again with the new logos
      toast(el.value === 'white' ? 'Channel logos will be shown in white' : 'Channel logos will be shown in color', 'success');
    } catch (err) { toast(err.message, 'error'); }
  },
  'smooth-motion': async el => {
    try {
      await api('/api/settings', { method: 'POST', body: JSON.stringify({ smooth_motion: el.checked }) });
      toast(el.checked
        ? 'Smooth motion on for the next thing you play. If you see glitches or stutters, turn it back off.'
        : 'Smooth motion off. It applies to the next thing you play.');
    } catch (err) { el.checked = !el.checked; toast(err.message, 'error'); }
  },
  'notifications': async el => {
    try {
      await api('/api/settings', { method: 'POST', body: JSON.stringify({ notifications: el.checked }) });
      toast(el.checked ? 'Notifications on' : 'Notifications off');
    } catch (err) { el.checked = !el.checked; toast(err.message, 'error'); }
  },
  'select-device': async el => {
    try { await api(`/api/auth/select/${encodeURIComponent(el.value)}`, { method: 'POST' }); toast('Switched device. Syncing…', 'success'); await loadStatus(); state.shows = null; } catch (err) { toast(err.message, 'error'); }
  },
};

function wireEvents() {
  document.addEventListener('click', e => {
    const el = e.target.closest('[data-action]');
    if (!el || el.disabled) return;
    const fn = ACTIONS[el.dataset.action];
    if (!fn) return;
    e.preventDefault();
    fn(el, e);
  });

  document.addEventListener('dblclick', e => {
    const row = e.target.closest('[data-ep-row]');
    if (row && !e.target.closest('button, input')) player.playEpisode(row.dataset.epRow);
  });

  document.addEventListener('input', e => {
    const el = e.target.closest('[data-input]');
    if (el && INPUTS[el.dataset.input]) INPUTS[el.dataset.input](el);
  });

  document.addEventListener('change', e => {
    const el = e.target.closest('[data-change]');
    if (el && CHANGES[el.dataset.change]) CHANGES[el.dataset.change](el);
  });

  document.addEventListener('submit', async e => {
    const form = e.target.closest('[data-form="login"]');
    if (!form) return;
    e.preventDefault();
    const btn = form.querySelector('button');
    btn.disabled = true;
    btn.textContent = 'Signing in…';
    try {
      await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: form.email.value, password: form.password.value }) });
      form.password.value = '';
      await loadStatus();
      state.shows = null;
      state.scheduled.items = null;
      state.manualSync = true;
      setSyncState(true);
      if ((state.status.devices || []).length > 1) {
        state.pickingDevice = true;
        route();
      } else {
        toast('Signed in. Syncing your recordings…', 'success');
        location.hash = '#/';
      }
    } catch (err) {
      toast(`Sign-in failed: ${friendlyLoginError(err.message)}`, 'error');
      btn.disabled = false;
      btn.textContent = 'Sign in';
    }
  });

  document.addEventListener('mousedown', e => {
    if (openMenuEl && !openMenuEl.contains(e.target) && !e.target.closest('[data-action$="-menu"]')) closeMenu();
    if (!e.target.closest('.global-search')) hideSearch();
  });
  view().addEventListener('scroll', closeMenu, { passive: true });

  const search = $('#globalSearch');
  search.addEventListener('input', () => runSearch(search.value));
  search.addEventListener('focus', () => { if (search.value.trim()) runSearch(search.value); });
  search.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); moveSearchSelection(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); moveSearchSelection(-1); }
    else if (e.key === 'Enter') {
      const sel = $('#searchResults .search-item.selected');
      if (sel) sel.click();
      else if (search.value.trim()) ACTIONS['search-all']({ dataset: { q: search.value.trim() } });
    } else if (e.key === 'Escape') { search.value = ''; hideSearch(); search.blur(); }
  });

  document.addEventListener('keydown', e => {
    const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
    if (e.key === '/' && !typing) { e.preventDefault(); search.focus(); search.select(); return; }
    if (e.key === 'Escape') {
      // In full screen the browser leaves full screen on Esc; don't also close the player
      if (document.fullscreenElement) return;
      if (openMenuEl) closeMenu();
      else if (openOverlay) closeModal(false);
      else if (player.isOpen()) player.close();
      else if (state.selected.size) ACTIONS['bulk-clear']();
      return;
    }
    // Player shortcuts
    if (!player.isOpen() || openOverlay || (typing && document.activeElement.id !== 'pbVolume') || e.ctrlKey || e.altKey || e.metaKey) return;
    if (!$('#chanPanel').classList.contains('hidden') && player.moveInChannels(e.key)) {
      e.preventDefault();
      player.wake();
      return;
    }
    const v = $('#video');
    const keys = {
      ' ': () => player.togglePlay(), k: () => player.togglePlay(),
      ArrowLeft: () => player.skip(-10), j: () => player.skip(-10),
      ArrowRight: () => player.skip(30), l: () => player.skip(30),
      ArrowUp: () => player.setVolume(v.volume + 0.1), ArrowDown: () => player.setVolume(v.volume - 0.1),
      m: () => player.toggleMute(), f: () => player.toggleFullscreen(), p: () => player.togglePip(),
      '>': () => player.stepSpeed(1), '<': () => player.stepSpeed(-1),
      Home: () => { if (state.stream.channelId) player.goLive(); },
      PageUp: () => player.surf(-1), PageDown: () => player.surf(1),
      c: () => { if (state.stream.channelId) player.toggleChannels(); },
      s: () => { if (!$('#skipBreak').classList.contains('hidden')) player.skipBreak(); },
      t: () => player.toggleCaptions(),
      2: () => dual.add(),
      l: () => dual.cycleLayout(),
      Tab: () => { if (dual.on) dual.swap(); },
      '?': () => player.showHelp(),
    };
    const fn = keys[e.key] || keys[e.key.toLowerCase()];
    if (fn) { e.preventDefault(); fn(); player.wake(); }
  });

  $('#player').addEventListener('mousemove', () => player.wake());

  const track = $('#tlTrack');
  const fractionAt = e => {
    const r = track.getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  };
  const timeAt = e => fractionAt(e) * (state.stream.duration || 0);
  track.addEventListener('click', e => {
    if (state.stream.channelId) {
      // Live TV: jump within what's been kept
      const w = player.liveWindow();
      if (w) $('#video').currentTime = Math.min(w.end - 2, w.start + fractionAt(e) * (w.end - w.start));
    } else {
      player.seekTo(timeAt(e));
    }
  });
  track.addEventListener('mousemove', e => {
    const hover = $('#tlHover');
    const w = state.stream.channelId && player.liveWindow();
    const label = w ? `−${fmtClock((1 - fractionAt(e)) * (w.end - w.start))}` : fmtClock(timeAt(e));
    // Recordings: a preview frame, once that part has been converted (frames every 5 s, named by position)
    const frame = w ? '' : player.previewUrl(timeAt(e));
    let img = hover.querySelector('img');
    if (frame) {
      if (!img) {
        hover.innerHTML = '<img alt=""><span></span>';
        img = hover.querySelector('img');
        img.onerror = () => { img.style.display = 'none'; };
        img.onload = () => { img.style.display = ''; };
      }
      if (img.getAttribute('src') !== frame) img.src = frame;
      hover.querySelector('span').textContent = label;
    } else {
      hover.textContent = label;
    }
    hover.classList.remove('hidden');
    // Keep the bubble (with its preview frame) inside the player at either end of the timeline
    const tr = track.getBoundingClientRect(), half = hover.offsetWidth / 2;
    const x = e.clientX - tr.left;
    hover.style.left = `${Math.max(half - tr.left + 8, Math.min(window.innerWidth - tr.left - half - 8, x))}px`;
  });
  track.addEventListener('mouseleave', () => $('#tlHover').classList.add('hidden'));
  $('#bufferSelect').addEventListener('change', e => { state.bufferTarget = parseInt(e.target.value, 10) || 8; save('tablo_buffer_target', state.bufferTarget); });
  const video = $('#video');
  // A caption track appears once the stream's first captions arrive: show it if captions are on
  video.textTracks.addEventListener('addtrack', () => player.applyCaptions());
  try { video.volume = Math.max(0, Math.min(1, parseFloat(store('tablo_volume', '1')))); } catch { /* default */ }
  ['play', 'pause', 'volumechange'].forEach(ev => video.addEventListener(ev, () => player.syncButtons()));
  video.addEventListener('click', () => (dual.on ? dual.paneClick('main') : player.togglePlay()));
  $('#video2').addEventListener('click', () => dual.paneClick('second'));
  $('#video2').textTracks.addEventListener('addtrack', () => player.applyCaptions());
  video.addEventListener('dblclick', () => player.toggleFullscreen());
  $('#pbVolume').addEventListener('input', e => player.setVolume(parseFloat(e.target.value)));
  $('#pbSpeed').addEventListener('change', e => { player.setSpeed(parseFloat(e.target.value)); e.target.blur(); });
  // Don't leave player buttons focused: Space would press the button and the shortcut at once
  $('#playerTimeline').addEventListener('click', e => { const b = e.target.closest('button'); if (b) setTimeout(() => b.blur()); });
  // Recordings without a known show length still offer the next episode when the video ends.
  // A stalled stream can also fire 'ended', so only near the end of the recording itself.
  $('#video').addEventListener('ended', () => {
    const s = state.stream;
    if (s.episodeId && s.duration && player.position() >= s.duration - 90) player.offerUpNext();
  });

  window.addEventListener('hashchange', route);
  // Stop the backend FFmpeg session if the tab is closed mid-playback
  window.addEventListener('pagehide', () => {
    if (state.stream.episodeId) player.saveProgress({ final: true });
    player.stopStream({ keepalive: true });
    dual.stopSession(true);  // the second channel's tuner too
    antenna.cancelScan();
    antenna.stop({ keepalive: true });  // and the antenna helper's
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function init() {
  hydrateIcons();
  wireEvents();
  await loadStatus();
  // Opened without a page in the address (the tray, a bookmark to the site): the chosen start page
  const start = store('tv_start_page', 'home');
  if ((!location.hash || location.hash === '#/' || location.hash === '#') && start !== 'home'
      && START_PAGES.some(([v]) => v === start)) {
    history.replaceState(null, '', `#/${start}`);
  }
  route();
  showWhatsNew();
  loadStorage();
  loadShows().catch(() => {});  // the Library count in the sidebar, whichever page opened first
  loadScheduled().catch(() => {});
  loadWatchCount();
  if (state.status && state.status.authenticated) checkTuners();
  setInterval(() => { if (!document.hidden && state.status && state.status.authenticated) checkTuners(); }, 30000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && state.status && state.status.authenticated) checkTuners(); });
  // Click anywhere else: close the tuner list
  document.addEventListener('mousedown', e => {
    if (!e.target.closest('#tunerPanel, #tunerPill')) $('#tunerPanel').classList.add('hidden');
  });
  api('/api/exports').then(({ jobs }) => setActiveExports(jobs.filter(j => j.status === 'downloading' || j.status === 'pending').length)).catch(() => {});
  setInterval(pollStatus, 5000);
  setInterval(() => setSyncState(state.isSyncing), 60000);
  checkForUpdate();
  setInterval(() => checkForUpdate(), 6 * 3600 * 1000);
}

document.addEventListener('DOMContentLoaded', init);
