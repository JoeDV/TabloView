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
  trash: '<path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  play: '<path d="M6 3.8v16.4a1 1 0 0 0 1.5.86l13.2-8.2a1 1 0 0 0 0-1.72L7.5 2.94A1 1 0 0 0 6 3.8z" fill="currentColor" stroke="none"/>',
  more: '<circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="19" cy="12" r="1.6" fill="currentColor"/><circle cx="5" cy="12" r="1.6" fill="currentColor"/>',
  external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  tv: '<rect width="20" height="15" x="2" y="7" rx="2"/><path d="m17 2-5 5-5-5"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
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
    throw new Error(data.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
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

const state = {
  status: null,
  shows: null,
  guideCache: new Map(),
  library: { q: '', sort: store('tv_lib_sort', 'recent'), filter: 'all', layout: store('tv_lib_layout', 'wide') },
  guide: { q: '', highlight: '', category: 'all', rule: '', sort: 'primetime', items: [], offset: 0, hasMore: false, highlights: {} },
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
  stream: { sessionId: null, hls: null, handler: null, timer: null, episodeId: null, channelId: null },
};

let routeToken = 0;
let pageTimers = [];

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
  document.body.appendChild(menu);
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

function openModal(html, { onReady } = {}) {
  closeModal(false);
  return new Promise(resolve => {
    const el = document.createElement('div');
    el.className = 'overlay';
    el.innerHTML = `<div class="dialog" role="dialog" aria-modal="true">${html}</div>`;
    el.addEventListener('mousedown', e => { if (e.target === el) closeModal(false); });
    document.body.appendChild(el);
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
    const wasSyncing = state.isSyncing;
    setSyncState(s.is_syncing, s.last_sync);
    if (wasSyncing && !s.is_syncing) {
      if (s.last_error) toast(`Sync failed: ${s.last_error}`, 'error');
      else toast('Recordings synced from your Tablo', 'success');
      state.shows = null;
      loadStorage();
      const r = parseRoute().name;
      if (r === 'home' || r === 'library') route();
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

function setActiveExports(n) {
  state.activeExports = n;
  $('#navDownloadsCount').textContent = n > 0 ? `${n} active` : '';
}

async function refreshLibrary() {
  if (state.isSyncing) return;
  try {
    await api('/api/library/refresh', { method: 'POST' });
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
      </div>
      <div class="media-meta">
        <div class="media-title">${esc(s.title)}</div>
        <div class="media-sub">${plural(s.episode_count, 'episode')} · ${esc(fmt.dayLabel(s.latest_recording_date))}</div>
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
        <div class="media-sub">${nextAiringText(g) || esc(genres) || '&nbsp;'}</div>
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
  closeMenu();
  hideSearch();
  clearSelection();

  const navName = NAV_FOR[r.name] || r.name;
  $$('.nav-item').forEach(a => a.classList.toggle('active', a.dataset.nav === navName));
  $('#backBtn').classList.toggle('visible', r.name === 'show' || r.name === 'series');

  const render = PAGES[r.name] || PAGES.home;
  view().scrollTop = 0;
  render(r, token).catch(err => {
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

  const [shows, sched, prem, prime] = await Promise.allSettled([
    loadShows(),
    loadScheduled(),
    api('/api/guide/shows?highlight=premieres&sort=soonest&limit=24').then(r => cacheGuide(r.shows)),
    api('/api/guide/shows?highlight=primetime_new&sort=soonest&limit=30').then(r => cacheGuide(r.shows)),
  ]);
  if (stale(token)) return;

  const showList = shows.value || [];
  const schedList = sched.value || [];
  const totalEps = showList.reduce((n, s) => n + (s.episode_count || 0), 0);
  const unwatched = showList.reduce((n, s) => n + (s.unwatched_count || 0), 0);

  const parts = [];

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

  // Up next: scheduled series airing within the next 48 hours
  const horizon = Date.now() + 48 * 3600 * 1000;
  const upNext = schedList
    .filter(g => g.next_airing && g.next_airing.datetime && new Date(g.next_airing.datetime).getTime() < horizon)
    .sort((a, b) => a.next_airing.datetime.localeCompare(b.next_airing.datetime))
    .slice(0, 8);
  if (upNext.length) {
    parts.push(section({
      title: 'Coming up on your schedule',
      sub: 'Next 48 hours',
      link: '#/scheduled',
      body: `<div class="list">${upNext.map(g => {
        const n = g.next_airing;
        const se = fmt.se(n.season_number, n.episode_number);
        const startsSoon = new Date(n.datetime).getTime() <= Date.now();
        return `
          <div class="list-row upnext-row clickable" data-action="open-series" data-path="${esc(g.path)}">
            <div class="upnext-when">${startsSoon ? '<span class="tag tag-live">ON NOW</span>' : esc(fmt.time(n.datetime))}<span class="dim">${esc(fmt.dayLabel(n.datetime))}</span></div>
            ${imgUrl(g.cover_url || g.backdrop_url) ? `<img class="thumb" src="${esc(imgUrl(g.cover_url || g.backdrop_url))}" alt="" loading="lazy">` : '<div class="thumb"></div>'}
            <div style="min-width:0">
              <div class="row-title">${esc(g.title)}</div>
              <div class="row-sub">${se ? `${se} · ` : ''}${esc(n.title || '')}</div>
            </div>
            <div class="row-sub upnext-ch">${esc(n.network || '')}${n.call_sign ? ` · ${esc(n.call_sign)}` : ''}</div>
            <span class="tag tag-rec">${g.schedule_rule === 'all' ? 'All episodes' : 'New episodes'}</span>
          </div>`;
      }).join('')}</div>`,
    }));
  }

  const premList = prem.value || [];
  if (premList.length) {
    parts.push(section({
      title: 'Season premieres',
      sub: 'Upcoming on your channels',
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
  const watchedCount = eps.length - unwatched.length;
  const totalSec = eps.reduce((n, e) => n + (e.duration || 0), 0);
  const nextEp = unwatched[0] || eps[0];
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
            ${nextEp ? `<button class="btn btn-primary btn-lg" data-action="play-ep" data-id="${esc(nextEp.id)}">${icon('play', 16)}${unwatched.length ? 'Play next' : 'Play'}: ${esc(fmt.se(nextEp.season_number, nextEp.episode_number) || episodeTitle(nextEp))}</button>` : ''}
            ${watchedCount ? `<button class="btn btn-lg btn-danger" data-action="delete-watched">${icon('trash', 16)}Delete ${watchedCount} watched</button>` : ''}
            <span id="seriesLinkSlot"></span>
          </div>
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

function episodeStatus(ep) {
  if (ep.recording_state === 'recording') return '<span class="tag tag-live">Recording</span>';
  if (ep.recording_state === 'failed') {
    const mins = Math.round((ep.actual_duration || 0) / 60);
    const why = ep.recording_error && ep.recording_error.details === 'weak_signal' ? 'weak signal' : 'signal lost';
    return mins > 0
      ? `<span class="tag tag-warn" title="Recording stopped after ${mins} min (${why})">Partial · ${mins}m</span>`
      : `<span class="tag tag-rec" title="Recording failed (${why})">Failed</span>`;
  }
  return ep.status === 'Watched' ? '<span class="dim">Watched</span>' : '<span class="tag tag-accent">Unwatched</span>';
}

function episodeRow(ep) {
  const watched = ep.status === 'Watched';
  const sel = state.selected.has(ep.id);
  return `
    <div class="ep-row ${watched ? 'watched' : ''} ${sel ? 'selected' : ''}" data-ep-row="${esc(ep.id)}">
      <input type="checkbox" class="checkbox" data-change="ep-select" data-id="${esc(ep.id)}" ${sel ? 'checked' : ''}>
      <button class="icon-btn play" data-action="play-ep" data-id="${esc(ep.id)}" title="Play">${icon('play', 14)}</button>
      <div class="ep-se">${esc(fmt.se(ep.season_number, ep.episode_number) || '—')}</div>
      <div class="ep-main">
        <div class="ep-title">${esc(episodeTitle(ep))}</div>
        ${ep.description ? `<div class="ep-desc" title="${esc(ep.description)}">${esc(ep.description)}</div>` : ''}
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
    title: 'Delete this recording?',
    text: `“${ep ? episodeTitle(ep) : 'This episode'}” will be permanently removed from your Tablo.`,
    confirm: 'Delete', danger: true,
  });
  if (!ok) return;
  try {
    const res = await api(`/api/episodes/${encodeURIComponent(id)}`, { method: 'DELETE' });
    state.episodes = state.episodes.filter(e => e.id !== id);
    state.selected.delete(id);
    if (res.show) state.show = res.show;
    toast('Recording deleted', 'success');
    afterEpisodeChange();
  } catch (err) {
    toast(`Delete failed: ${err.message}`, 'error');
  }
}

async function bulkDelete() {
  const ids = Array.from(state.selected);
  if (!ids.length) return;
  const ok = await confirmDialog({ title: `Delete ${plural(ids.length, 'recording')}?`, text: 'They will be permanently removed from your Tablo.', confirm: 'Delete', danger: true });
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
  const watched = state.episodes.filter(e => e.status === 'Watched');
  if (!watched.length) return;
  const ok = await confirmDialog({ title: `Delete ${plural(watched.length, 'watched episode')}?`, text: `All watched episodes of “${state.show.title}” will be permanently removed from your Tablo.`, confirm: 'Delete watched', danger: true });
  if (!ok) return;
  try {
    const res = await api(`/api/shows/delete_watched?show_id=${encodeURIComponent(state.show.id)}`, { method: 'POST' });
    const deleted = new Set(res.deleted_ids || []);
    state.episodes = state.episodes.filter(e => !deleted.has(e.id));
    deleted.forEach(id => state.selected.delete(id));
    if (res.show) state.show = res.show;
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

PAGES.guide = async (r, token) => {
  const G = state.guide;
  if (r.query.has('q')) G.q = r.query.get('q');
  if (r.query.has('highlight')) { G.highlight = r.query.get('highlight'); G.sort = 'soonest'; }

  paint(`<div class="page">
    <div class="page-head">
      <div><h1 class="page-title">Guide</h1><div class="page-sub">Everything airing on your channels over the next two weeks</div></div>
      <div class="page-head-actions"><button class="btn btn-ghost btn-sm" data-action="sync-guide">${icon('refresh', 15)}Refresh guide</button></div>
    </div>
    <div class="toolbar">
      <div class="input-search">${icon('search', 15)}<input class="input" data-input="guide-q" placeholder="Search the guide" value="${esc(G.q)}"></div>
      <div class="segmented" id="guideHighlights">${guideHighlightButtons()}</div>
      <div class="grow"></div>
      <select class="select" data-change="guide-category">
        <option value="all">All types</option>
        <option value="series" ${G.category === 'series' ? 'selected' : ''}>TV shows</option>
        <option value="movies" ${G.category === 'movies' ? 'selected' : ''}>Movies</option>
        <option value="sports" ${G.category === 'sports' ? 'selected' : ''}>Sports</option>
      </select>
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
    <div id="guideGrid">${skeletonGrid(10)}</div>
  </div>`);
  await loadGuide(token);
};

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
  grid.innerHTML = `<div class="card-grid">${G.items.map(guideCard).join('')}</div>
    ${G.hasMore ? '<div style="text-align:center;margin-top:28px"><button class="btn" data-action="guide-more">Show more</button></div>' : ''}`;
}

const reloadGuide = debounce(() => loadGuide(routeToken), 220);

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

async function syncGuide() {
  try {
    await api('/api/guide/sync', { method: 'POST' });
    toast('Refreshing the guide from your Tablo. This takes a minute.');
    setTimeout(() => { state.scheduled.items = null; if (['guide', 'scheduled', 'home'].includes(parseRoute().name)) route(); }, 45000);
  } catch (err) {
    toast(`Guide refresh failed: ${err.message}`, 'error');
  }
}

// ---------------------------------------------------------------------------
// Scheduled
// ---------------------------------------------------------------------------
PAGES.scheduled = async (r, token) => {
  const S = state.scheduled;
  paint(`<div class="page">
    <div class="page-head">
      <div><h1 class="page-title">Scheduled</h1><div class="page-sub">Series your Tablo records automatically</div></div>
      <div class="page-head-actions"><button class="btn btn-ghost btn-sm" data-action="sync-guide">${icon('refresh', 15)}Refresh from Tablo</button></div>
    </div>
    <div class="toolbar">
      <div class="input-search">${icon('search', 15)}<input class="input" data-input="scheduled-q" placeholder="Filter scheduled series" value="${esc(S.q)}"></div>
      <div class="segmented" id="schedFilters"></div>
    </div>
    <div id="schedList"><div class="list"><div class="loading-line"><span class="spinner"></span>Loading…</div></div></div>
  </div>`);
  await loadScheduled(true);
  if (stale(token)) return;
  renderScheduledList();
};

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
  box.innerHTML = `<div class="list">${items.map(g => {
    const genres = Array.isArray(g.genres) ? g.genres.slice(0, 2).join(', ') : '';
    const n = g.next_airing;
    return `
      <div class="list-row sched-row clickable" data-action="open-series" data-path="${esc(g.path)}">
        ${imgUrl(g.cover_url || g.backdrop_url) ? `<img class="thumb" src="${esc(imgUrl(g.cover_url || g.backdrop_url))}" alt="" loading="lazy">` : '<div class="thumb"></div>'}
        <div style="min-width:0"><div class="row-title">${esc(g.title)}</div><div class="row-sub">${esc(genres)}</div></div>
        <div class="sched-col-next" style="min-width:0">
          ${n ? `<div class="row-title" style="font-weight:500">${esc(fmt.when(n.datetime))}</div><div class="row-sub">${esc(n.network || n.call_sign || '')}${n.title ? ` · ${esc(n.title)}` : ''}</div>` : '<div class="row-title dim" style="font-weight:500">No upcoming airings</div><div class="row-sub">Waiting for new episodes</div>'}
        </div>
        <div data-rule-control="${esc(g.path)}" class="segmented rule">
          <button data-action="set-rule" data-path="${esc(g.path)}" data-rule="new" class="${g.schedule_rule === 'new' ? 'active' : ''}">New</button>
          <button data-action="set-rule" data-path="${esc(g.path)}" data-rule="all" class="${g.schedule_rule === 'all' ? 'active' : ''}">All</button>
        </div>
        <button class="btn btn-sm btn-danger" data-action="stop-rule" data-path="${esc(g.path)}">Stop</button>
      </div>`;
  }).join('')}</div>`;
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
      <span class="tuner-pill" id="tunerPill" title="Tablo tuners"><span class="dot"></span><span id="tunerText">Tuners</span></span>
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
  pageTimers.push(setInterval(checkTuners, 5000));
  checkTuners();
  await loadEpg(token, true);
};

function epgCatButtons() {
  return EPG_CATS.map(([k, label]) => `<button data-action="epg-cat" data-value="${k}" class="${state.epgCategory === k ? 'active' : ''}">${label}</button>`).join('');
}

async function loadEpg(token, scrollToNow = false) {
  let startIso = '';
  if (state.epgOffset) {
    const d = new Date();
    d.setHours(d.getHours() + state.epgOffset);
    startIso = `&start_iso=${encodeURIComponent(d.toISOString())}`;
  }
  try {
    const res = await api(`/api/live/epg?hours=${EPG.HOURS}${startIso}`);
    if (token !== undefined && stale(token)) return;
    state.epg = res;
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
  if (cat === 'ota' && c.kind !== 'ota') return false;
  if (cat === 'fast' && c.kind === 'ota') return false;
  const text = `${c.name} ${c.call_sign} ${c.network}`.toLowerCase();
  if (cat === 'news' && !/news|bloomberg|scripps|cheddar|weather|wrtv|wthr|wttv|wxin/.test(text)) return false;
  if (cat === 'sports' && !/sport|outside|stadium|surf|fight|racing|motor/.test(text)) return false;
  if (cat === 'entertainment' && !/ion|movie|comedy|drama|classic|hallmark|film|bachelor|portlandia|wfyi/.test(text)) return false;
  const q = state.epgQuery;
  if (q) {
    const hit = text.includes(q) || (c.airings || []).some(a => `${a.title || ''} ${a.episode_title || ''}`.toLowerCase().includes(q));
    if (!hit) return false;
  }
  return true;
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

    const num = c.major > 0 ? `${c.major}.${c.minor}` : '';
    let name = c.name || c.call_sign || '';
    if (num && name.startsWith(num)) name = name.slice(num.length).trim();
    const sub = [c.network && c.network.toLowerCase() !== name.toLowerCase() ? c.network : '', c.resolution].filter(Boolean).join(' · ');
    return `<div class="epg-row">
      <div class="epg-ch" style="width:${EPG.CH_W}px" data-action="watch-live" data-id="${esc(c.channel_id)}" data-name="${esc(name)}" title="Watch ${esc(name)} live">
        ${c.logo_url ? `<img class="epg-ch-logo" src="${esc(c.logo_url)}" alt="" loading="lazy">` : `<div class="epg-ch-logo-fallback">${esc((c.call_sign || 'TV').slice(0, 6))}</div>`}
        <div class="epg-ch-info"><div class="epg-ch-num">${num ? `<b>${esc(num)}</b>` : ''}${esc(name)}</div>${sub ? `<div class="epg-ch-sub">${esc(sub)}</div>` : ''}</div>
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
    const pill = $('#tunerPill'), text = $('#tunerText');
    if (!pill) return;
    const total = t.total || 0, used = t.in_use || 0;
    const streams = t.streams_in_use || 0, streamsTotal = t.streams_total || 0;
    pill.classList.toggle('busy', used > 0 || streams > 0);
    if (!total) {
      text.textContent = 'Tuners unavailable';
      pill.title = "Couldn't read tuner status from the Tablo";
      return;
    }
    text.textContent = `OTA ${used}/${total}` + (streamsTotal ? ` · Stream ${streams}/${streamsTotal}` : '');
    pill.title = `Antenna (OTA) tuners in use: ${used} of ${total} (recordings and live TV)` +
      (streamsTotal ? `\nStreaming slots in use: ${streams} of ${streamsTotal} (FAST channels; these don't use the antenna)` : '');
  } catch { /* optional */ }
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
      <button class="btn" data-action="modal-live-vlc" data-id="${esc(c.channel_id)}">${icon('external', 15)}VLC</button>
      <button class="btn btn-primary" data-action="modal-watch-live" data-id="${esc(c.channel_id)}" data-name="${esc(c.name)}" data-autofocus>${icon('play', 14)}Watch ${esc(c.name)}</button>
    </div>`);
}

// ---------------------------------------------------------------------------
// Downloads
// ---------------------------------------------------------------------------
PAGES.downloads = async (r, token) => {
  paint(`<div class="page">
    <div class="page-head"><div><h1 class="page-title">Downloads</h1><div class="page-sub">MP4 exports saved to the downloads folder on this computer</div></div></div>
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
      <span class="status-text ${esc(j.status)}">${esc(j.status === 'downloading' ? 'Exporting' : j.status)}</span>
      <div>${j.status === 'completed' ? `<a class="btn btn-sm" href="/downloads/${encodeURIComponent(j.filename)}" download>${icon('download', 15)}Save</a>` : ''}</div>
    </div>`;
  }).join('')}</div>`;
}

// ---------------------------------------------------------------------------
// Device
// ---------------------------------------------------------------------------
PAGES.device = async (r, token) => {
  const [, , info, settings] = await Promise.all([
    loadStatus(), loadStorage(),
    api('/api/system/info').catch(() => ({})),
    api('/api/settings').catch(() => ({})),
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
        <p class="dim" style="margin-top:10px;font-size:12.5px">Anyone on your Wi-Fi could then watch, schedule and delete recordings. Leave this off on shared or public networks.</p>`
      : '<p class="dim" style="font-size:13px">Running from source: network access follows the <code>--host</code> option in the start command.</p>'}
      ${info.listening_on_network && info.network_url ? `<p style="margin-top:12px">On other devices, open <b>${esc(info.network_url)}</b></p>` : ''}
    </div>`;

  const about = `
    <div class="panel">
      <h3>About</h3><div class="panel-sub">TabloView ${esc(info.version || '')}${info.packaged ? '' : ' (running from source)'}</div>
      <dl class="kv">
        <dt>Playback engine</dt><dd>${info.ffmpeg_found ? 'FFmpeg ready' : '<span style="color:var(--warn)">FFmpeg not found: in-browser playback and MP4 export won’t work. VLC still works.</span>'}</dd>
        <dt>Exports folder</dt><dd>${esc(info.downloads_dir || '')}</dd>
        <dt>App data</dt><dd>${esc(info.data_dir || '')}</dd>
      </dl>
    </div>`;

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
    </div>` : '';

  paint(`<div class="page">
    <div class="page-head"><div><h1 class="page-title">Device</h1><div class="page-sub">Connection, syncing, storage and playback settings</div></div></div>
    <div class="panel-grid">
      ${connection}
      <div class="panel">
        <h3>Library sync</h3><div class="panel-sub">Recordings are cached locally so pages load instantly.</div>
        <dl class="kv">
          <dt>Last sync</dt><dd>${st.last_sync ? `${esc(fmt.ago(st.last_sync))} (${esc(new Date(st.last_sync).toLocaleString())})` : 'Never'}</dd>
          <dt>Cached</dt><dd>${plural(st.total_shows || 0, 'show')}, ${plural(st.total_episodes || 0, 'recording')}</dd>
        </dl>
        <div class="panel-actions">
          <button class="btn btn-sm" data-action="refresh-library">${icon('refresh', 15)}Sync recordings</button>
          <button class="btn btn-sm" data-action="sync-guide">${icon('guide', 15)}Refresh guide</button>
        </div>
      </div>
      <div class="panel">
        <h3>Storage</h3><div class="panel-sub">${storage.connected ? `${fmt.size(storage.used_gb)} of ${fmt.size(storage.total_gb)} used` : 'Unavailable'}</div>
        ${(storage.drives || []).map(d => `
          <div style="margin-bottom:14px">
            <div class="meter-row" style="font-size:13px"><span>${esc(d.name)}</span><span class="dim">${fmt.size(d.free_gb)} free</span></div>
            <div class="meter" style="height:6px"><div class="meter-fill" style="width:${Math.min(d.percent_used, 100)}%"></div></div>
          </div>`).join('')}
      </div>
      <div class="panel">
        <h3>Playback</h3><div class="panel-sub">How much video to buffer before playback starts. Raise it if playback stutters.</div>
        <select class="select" data-change="buffer">
          ${[4, 8, 15, 30].map(v => `<option value="${v}" ${state.bufferTarget === v ? 'selected' : ''}>${v} seconds</option>`).join('')}
        </select>
      </div>
      ${network}
      ${about}
      <div class="panel" style="grid-column:1/-1">
        <h3>Diagnostics</h3><div class="panel-sub">Probe the Tablo's local API and the cloud guide to troubleshoot connection problems.</div>
        <button class="btn btn-sm" data-action="run-inspector">${icon('info', 15)}Run API inspector</button>
        <div id="inspectorOut"></div>
      </div>
    </div>
  </div>`);
};

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

  async playEpisode(id) {
    const ep = state.episodes.find(e => e.id === id);
    const title = ep ? `${state.show ? state.show.title + ' · ' : ''}${fmt.se(ep.season_number, ep.episode_number) ? fmt.se(ep.season_number, ep.episode_number) + ' · ' : ''}${episodeTitle(ep)}` : 'Recording';
    this.stopStream();
    state.stream.episodeId = id;
    state.stream.channelId = null;
    this.open(title);
    this.setStatus(`<span class="wait">Starting stream…</span>`);
    try {
      const res = await api(`/api/episodes/${encodeURIComponent(id)}/watch?transcode=true`, { method: 'POST' });
      state.stream.sessionId = res.session_id;
      this.start(res.stream_url, 'Recording');
    } catch (err) {
      this.setStatus(`<span style="color:var(--rec)">Couldn't start playback: ${esc(err.message)}. Try “Open in VLC”.</span>`);
    }
  },

  async watchLive(channelId, name) {
    this.stopStream();
    state.stream.channelId = channelId;
    state.stream.episodeId = null;
    this.open(`Live · ${name}`);
    this.setStatus(`<span class="wait">Tuning ${esc(name)}…</span>`);
    try {
      const res = await api('/api/live/tune', { method: 'POST', body: JSON.stringify({ channel_id: channelId, transcode: true }) });
      state.stream.sessionId = res.session_id;
      checkTuners();
      this.start(res.stream_url, 'Live');
    } catch (err) {
      this.setStatus(`<span style="color:var(--rec)">Couldn't tune this channel: ${esc(err.message)}</span>`);
      checkTuners();
    }
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
          if (ahead >= target) { started = true; video.play().catch(() => {}); }
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
          if (!started && state.stream.hls === hls) { started = true; video.play().catch(() => {}); }
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
      video.play().catch(() => {});
    }
  },

  teardown() {
    const s = state.stream;
    if (s.timer) { clearInterval(s.timer); s.timer = null; }
    if (s.handler) { this.video().removeEventListener('progress', s.handler); s.handler = null; }
    if (s.hls) { s.hls.destroy(); s.hls = null; }
  },

  // Tell the backend to kill the FFmpeg transcode (and free the tuner for live TV)
  stopStream({ keepalive = false } = {}) {
    const id = state.stream.sessionId;
    if (!id) return;
    state.stream.sessionId = null;
    fetch('/api/live/stop', {
      method: 'POST', headers: API_HEADERS,
      body: JSON.stringify({ session_id: id }), keepalive,
    }).catch(() => {});
  },

  close() {
    this.teardown();
    const video = this.video();
    video.pause();
    video.removeAttribute('src');
    video.load();
    this.el().classList.add('hidden');
    this.stopStream();
    if (state.stream.channelId) setTimeout(checkTuners, 1000);
    state.stream.channelId = null;
    state.stream.episodeId = null;
  },

  openInVlc() {
    if (state.stream.channelId) openVlc(`/api/live/vlc/${encodeURIComponent(state.stream.channelId)}`);
    else if (state.stream.episodeId) openVlc(`/api/episodes/${encodeURIComponent(state.stream.episodeId)}/playlist.m3u`);
  },

  isOpen() { return !this.el().classList.contains('hidden'); },
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

  'play-ep': el => player.playEpisode(el.dataset.id),
  'ep-menu': el => {
    const id = el.dataset.id;
    openMenu(el, [
      { label: 'Play in browser', icon: 'play', run: () => player.playEpisode(id) },
      { label: 'Open in VLC', icon: 'external', run: () => openVlc(`/api/episodes/${encodeURIComponent(id)}/playlist.m3u`) },
      { label: 'Export MP4', icon: 'download', run: () => exportEpisode(id) },
      { sep: true },
      { label: 'Delete recording', icon: 'trash', danger: true, run: () => deleteEpisode(id) },
    ]);
  },
  'delete-watched': () => deleteWatched(),
  'bulk-delete': () => bulkDelete(),
  'bulk-clear': () => { state.selected.clear(); $$('.ep-row').forEach(r => r.classList.remove('selected')); $$('[data-change="ep-select"], [data-change="ep-select-all"]').forEach(c => { c.checked = false; }); updateBulkBar(); },

  'rec-menu': el => recMenu(el, el.dataset.path),
  'set-rule': el => { if (!el.classList.contains('active')) setRule(el.dataset.path, el.dataset.rule); },
  'stop-rule': async el => {
    const g = state.guideCache.get(el.dataset.path) || {};
    if (await confirmDialog({ title: `Stop recording ${g.title || 'this series'}?`, text: 'Existing recordings are kept. Future episodes won’t be recorded.', confirm: 'Stop recording', danger: true })) setRule(el.dataset.path, 'none');
  },
  'toggle-airing': el => toggleAiring(el),
  'sync-guide': () => syncGuide(),
  'guide-highlight': el => { state.guide.highlight = el.dataset.value; state.guide.sort = el.dataset.value ? 'soonest' : 'primetime'; const s = $('[data-change="guide-sort"]'); if (s) s.value = state.guide.sort; loadGuide(routeToken); },
  'guide-more': el => { el.disabled = true; loadGuide(routeToken, true); },
  'guide-reload': () => loadGuide(routeToken),
  'scheduled-filter': el => { state.scheduled.filter = el.dataset.value; renderScheduledList(); },

  'epg-cat': el => { state.epgCategory = el.dataset.value; $$('[data-action="epg-cat"]').forEach(b => b.classList.toggle('active', b === el)); renderEpg(); },
  'epg-shift': el => { state.epgOffset += Number(el.dataset.dir) * 3; $$('[data-action="epg-now"]').forEach(b => b.classList.toggle('active', state.epgOffset === 0)); loadEpg(routeToken, true); },
  'epg-now': el => { state.epgOffset = 0; el.classList.add('active'); loadEpg(routeToken, true); },
  'epg-cell': el => openAiringModal(el.dataset.key),
  'watch-live': el => player.watchLive(el.dataset.id, el.dataset.name),

  'modal-ok': () => closeModal(true),
  'modal-cancel': () => closeModal(false),
  'modal-watch-live': el => { closeModal(false); player.watchLive(el.dataset.id, el.dataset.name); },
  'modal-live-vlc': el => { closeModal(false); openVlc(`/api/live/vlc/${encodeURIComponent(el.dataset.id)}`); setTimeout(checkTuners, 2500); },
  'modal-series': el => { closeModal(false); location.hash = `#/series/${encodeURIComponent(el.dataset.path)}`; },

  'close-player': () => player.close(),
  'player-vlc': () => player.openInVlc(),

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
};

const INPUTS = {
  'library-q': el => { state.library.q = el.value; renderLibraryGrid(); },
  'guide-q': el => { state.guide.q = el.value; reloadGuide(); },
  'scheduled-q': el => { state.scheduled.q = el.value; renderScheduledList(); },
  'epg-q': debounce(el => { state.epgQuery = el.value.trim().toLowerCase(); renderEpg(); }, 180),
};

const CHANGES = {
  'library-sort': el => { state.library.sort = el.value; save('tv_lib_sort', el.value); renderLibraryGrid(); },
  'guide-category': el => { state.guide.category = el.value; loadGuide(routeToken); },
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
      const ok = await confirmDialog({
        title: 'Allow other devices on your network?',
        text: 'Anyone on your Wi-Fi will be able to open TabloView and control your Tablo. If Windows asks, allow TabloView on Private networks only.',
        confirm: 'Allow', danger: false,
      });
      if (!ok) { el.checked = false; return; }
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
  'buffer': el => { state.bufferTarget = parseInt(el.value, 10) || 8; save('tablo_buffer_target', state.bufferTarget); toast(`Buffer set to ${state.bufferTarget} seconds`); },
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
      if (openMenuEl) closeMenu();
      else if (openOverlay) closeModal(false);
      else if (player.isOpen()) player.close();
      else if (state.selected.size) ACTIONS['bulk-clear']();
    }
  });

  $('#player').addEventListener('mousemove', () => player.wake());
  $('#bufferSelect').addEventListener('change', e => { state.bufferTarget = parseInt(e.target.value, 10) || 8; save('tablo_buffer_target', state.bufferTarget); });

  window.addEventListener('hashchange', route);
  // Stop the backend FFmpeg session if the tab is closed mid-playback
  window.addEventListener('pagehide', () => player.stopStream({ keepalive: true }));
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function init() {
  hydrateIcons();
  wireEvents();
  await loadStatus();
  route();
  loadStorage();
  loadScheduled().catch(() => {});
  api('/api/exports').then(({ jobs }) => setActiveExports(jobs.filter(j => j.status === 'downloading' || j.status === 'pending').length)).catch(() => {});
  setInterval(pollStatus, 5000);
  setInterval(() => setSyncState(state.isSyncing), 60000);
}

document.addEventListener('DOMContentLoaded', init);
