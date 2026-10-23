// TabloView TV: Continue watching, Recordings and Live TV for a TV's browser (TV Bro, Silk...),
// driven by a remote: arrows move between big tiles, OK picks, Back goes back. Screens are hash
// routes, so the browser's own Back button works too. Everything else (Guide, scheduling,
// settings, exports) stays on the PC page. Uses the same API and streams as the PC page.

const $ = sel => document.querySelector(sel);
const API_HEADERS = { 'Content-Type': 'application/json', 'X-TabloView': '1' };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(url, options = {}) {
  const res = await fetch(url, { headers: API_HEADERS, ...options });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && (data.code === 'pin_required' || data.code === 'pin_not_set')) showPin(data.code);
    throw Object.assign(new Error(data.detail || `${res.status} ${res.statusText}`), { status: res.status, code: data.code });
  }
  return res.json();
}

const fmt = {
  clock: s => {
    s = Math.max(0, Math.floor(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`;
  },
  mins: s => { const m = Math.round(s / 60); return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`; },
  day: iso => new Date(iso).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' }),
  time: d => new Date(d).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }),
  se: (s, e) => (s > 0 && e > 0 ? `S${s} E${e}` : ''),
};

const state = {
  live: null,        // /api/live/epg
  liveTab: 'ota',    // Antenna or Streaming channels
  shapes: {},        // picture shapes per channel, chosen on the PC (Device page player)
  focus: {},         // screen -> data-key focused last, so Back returns to the same tile
};

// ---------------------------------------------------------------------------
// Moving with the arrows: to the nearest focusable thing in that direction
// ---------------------------------------------------------------------------
function focusables() {
  const scope = !$('#dialog').classList.contains('hidden') ? $('#dialog') : document;
  return [...scope.querySelectorAll('.f')].filter(el => el.offsetParent !== null && !el.disabled);
}

function focusEl(el) {
  if (!el) return;
  el.focus({ preventScroll: true });
  el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' });
  if (el.dataset.key && !el.closest('.top') && !el.closest('.dialog')) state.focus[location.hash || '#/'] = el.dataset.key;
}

function move(dir) {
  const all = focusables();
  const cur = document.activeElement && all.includes(document.activeElement) ? document.activeElement : null;
  if (!cur) { focusEl(all.find(el => !el.closest('.top')) || all[0]); return; }
  const a = cur.getBoundingClientRect();
  const ax = a.left + a.width / 2, ay = a.top + a.height / 2;
  let best = null, bestScore = Infinity;
  for (const el of all) {
    if (el === cur) continue;
    const b = el.getBoundingClientRect();
    const bx = b.left + b.width / 2, by = b.top + b.height / 2;
    let main, cross;
    // Left and right stay in the same row: off the end of a row, nothing happens (instead of
    // jumping up to the tabs)
    const sameRow = b.top < a.bottom - 2 && b.bottom > a.top + 2;
    if (dir === 'right') { if (b.left < a.right - 2 || !sameRow) continue; main = b.left - a.right; cross = Math.abs(by - ay); }
    else if (dir === 'left') { if (b.right > a.left + 2 || !sameRow) continue; main = a.left - b.right; cross = Math.abs(by - ay); }
    else if (dir === 'down') { if (b.top < a.bottom - 2) continue; main = b.top - a.bottom; cross = Math.abs(bx - ax); }
    else { if (b.bottom > a.top + 2) continue; main = a.top - b.bottom; cross = Math.abs(bx - ax); }
    // Straight across matters most: a tile in the next row beats one far along the same row
    const score = main + cross * 2;
    if (score < bestScore) { bestScore = score; best = el; }
  }
  if (best) focusEl(best);
}

// ---------------------------------------------------------------------------
// Screens
// ---------------------------------------------------------------------------
function setScreen(html, tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.go === tab));
  $('#screen').innerHTML = html;
  $('#screen').scrollTop = 0;
  const key = state.focus[location.hash || '#/'];
  const all = focusables();
  focusEl((key && all.find(el => el.dataset.key === key)) || all.find(el => !el.closest('.top')) || all[0]);
}

function loading(tab) { setScreen('<div class="empty">Loading…</div>', tab); }

function failed(err, tab) {
  if (err.code === 'pin_required' || err.code === 'pin_not_set') return;  // the PIN screen is up
  setScreen(`<div class="empty">Couldn't load this: ${esc(err.message)}<br><button class="btn primary f" data-act="reload">Try again</button></div>`, tab);
}

const progressBar = (pos, dur) => (pos > 30 && dur ? `<div class="progress"><div style="width:${Math.min(100, (pos / dur) * 100)}%"></div></div>` : '');
const art = url => (url ? `style="background-image:url('${esc(url)}')"` : '');

async function showHome() {
  loading('#/');
  let eps;
  try { eps = (await api('/api/episodes/in_progress')).episodes || []; } catch (err) { return failed(err, '#/'); }
  state.episodes = eps;
  if (!eps.length) {
    return setScreen(`<div class="empty">Nothing to continue right now.<br>
      <button class="btn primary f" data-go="#/recordings" data-key="go-rec">Browse recordings</button></div>`, '#/');
  }
  setScreen(`<h1>Continue watching</h1><div class="grid wide">${eps.map(e => `
    <button class="tile f" data-act="play" data-id="${esc(e.id)}" data-key="cw-${esc(e.id)}">
      <div class="art" ${art(e.snapshot_url || e.backdrop_url || e.cover_url)}>${progressBar(e.position, e.duration)}</div>
      <div class="label"><div class="name">${esc(e.show_title)}</div>
        <div class="meta">${esc([fmt.se(e.season_number, e.episode_number), e.title !== e.show_title ? e.title : ''].filter(Boolean).join(' · '))}${e.duration ? ` · ${fmt.mins(e.duration - e.position)} left` : ''}</div></div>
    </button>`).join('')}</div>`, '#/');
}

async function showRecordings() {
  loading('#/recordings');
  let shows;
  try { shows = (await api('/api/shows')).shows || []; } catch (err) { return failed(err, '#/recordings'); }
  shows.sort((a, b) => String(b.latest_recording_date || '').localeCompare(String(a.latest_recording_date || '')));
  if (!shows.length) return setScreen('<div class="empty">No recordings yet.</div>', '#/recordings');
  setScreen(`<h1>Recordings</h1><div class="grid posters">${shows.map(s => `
    <button class="tile f" data-go="#/show/${encodeURIComponent(s.id)}" data-key="show-${esc(s.id)}">
      <div class="art" ${art(s.cover_url || s.backdrop_url)}>${s.unwatched_count ? `<span class="badge">${s.unwatched_count}</span>` : ''}</div>
      <div class="label"><div class="name">${esc(s.title)}</div>
        <div class="meta">${s.episode_count === 1 ? '1 recording' : `${s.episode_count} recordings`}</div></div>
    </button>`).join('')}</div>`, '#/recordings');
}

async function showShow(id) {
  loading('#/recordings');
  let d;
  try { d = await api(`/api/shows/episodes?show_id=${encodeURIComponent(id)}`); } catch (err) { return failed(err, '#/recordings'); }
  const eps = (d.episodes || []).slice().sort((a, b) => String(b.air_date || '').localeCompare(String(a.air_date || '')));
  state.episodes = eps;
  setScreen(`<h1>${esc(d.show_title || (d.show && d.show.title) || '')}</h1><div class="rows">${eps.map(e => {
    const watched = e.status === 'Watched';
    const left = e.position > 30 && !watched && e.duration ? ` · ${fmt.mins(e.duration - e.position)} left` : '';
    return `<button class="row f" data-act="play" data-id="${esc(e.id)}" data-key="ep-${esc(e.id)}">
      <div class="thumb" ${art(e.snapshot_url)}>${progressBar(watched ? 0 : e.position, e.duration)}</div>
      <div class="body"><div class="name">${watched ? '' : '<span class="dot"></span>'}${esc([fmt.se(e.season_number, e.episode_number), e.title].filter(Boolean).join(' · '))}</div>
        <div class="meta">${e.air_date ? esc(fmt.day(e.air_date)) : ''}${e.duration ? ` · ${fmt.mins(e.actual_duration || e.duration)}` : ''}${left}${e.channel_name ? ` · ${esc(e.channel_name)}` : ''}</div></div>
    </button>`;
  }).join('')}</div>`, '#/recordings');
}

async function showWatchlist() {
  loading('#/watchlist');
  let eps;
  try { eps = (await api('/api/watchlist')).episodes || []; } catch (err) { return failed(err, '#/watchlist'); }
  eps = eps.filter(e => e.recording_state !== 'recording');
  state.watchList = eps;
  if (!eps.length) {
    return setScreen(`<div class="empty">Your Watch list is empty.<br>Add recordings to it on the PC (a recording's … menu, or select several),<br>then play them here one after another.</div>`, '#/watchlist');
  }
  setScreen(`<h1>Watch list</h1>
    <div class="subtabs">
      <button class="btn primary f" data-act="run" data-how="keep" data-from="0" data-key="run-keep">▶ Watch and keep</button>
      <button class="btn f" data-act="run" data-how="delete" data-from="0" data-key="run-delete">Watch and delete</button>
    </div>
    <div class="dim" style="margin-bottom:1.6vw">They play one after another, picking up where you left off. With Watch and delete, each one is deleted from your Tablo once you've watched it to the end; ones you stop partway, and protected recordings, are kept.</div>
    <div class="rows">${eps.map((e, i) => {
      const left = e.position > 30 && e.status !== 'Watched' && e.duration ? ` · ${fmt.mins(e.duration - e.position)} left` : '';
      return `<button class="row f" data-act="run-from" data-from="${i}" data-key="wl-${esc(e.id)}">
        <div class="ch-num">${i + 1}</div>
        <div class="thumb" ${art(e.snapshot_url || e.cover_url)}>${progressBar(e.status === 'Watched' ? 0 : e.position, e.duration)}</div>
        <div class="body"><div class="name">${esc(e.show_title || '')}</div>
          <div class="meta">${esc([fmt.se(e.season_number, e.episode_number), e.title !== e.show_title ? e.title : ''].filter(Boolean).join(' · '))}${e.duration ? ` · ${fmt.mins(e.actual_duration || e.duration)}` : ''}${left}${e.protected ? ' · Protected' : ''}</div></div>
      </button>`;
    }).join('')}</div>`, '#/watchlist');
}

// Play the Watch list from one of its recordings: keep or delete each once it's watched to the end
async function startRun(from, how) {
  const eps = (state.watchList || []).slice(from);
  if (!eps.length) return;
  if (!how) {
    how = await choose(`Watch ${eps.length === 1 ? 'this recording' : `${eps.length} recordings in a row`}`,
      "With Watch and delete, each one is deleted from your Tablo once you've watched it to the end. Ones you stop partway, and protected recordings, are kept.",
      [{ label: 'Watch and keep', value: 'keep' }, { label: 'Watch and delete', value: 'delete' }]);
    if (!how) return;
  }
  state.run = { eps, index: 0, deleteAfter: how === 'delete' };
  player.playEpisode(eps[0].id, { run: true });
}

function nowNext(c, now = Date.now()) {
  const list = c.airings || [];
  const i = list.findIndex(a => { const s = new Date(a.air_datetime).getTime(); return s <= now && now < s + (a.duration || 0) * 1000; });
  return { now: list[i], next: i >= 0 ? list[i + 1] : list.find(a => new Date(a.air_datetime).getTime() > now) };
}

async function loadLive() {
  const end = state.live ? new Date(state.live.window_end).getTime() : 0;
  if (end - Date.now() > 30 * 60000) return state.live;
  state.live = await api('/api/live/epg?hours=3');
  return state.live;
}

function liveChannels() {
  return ((state.live && state.live.channels) || []).filter(c => (state.liveTab === 'fast' ? c.kind === 'fast' : c.kind !== 'fast'));
}

async function showLive() {
  loading('#/live');
  try { await loadLive(); } catch (err) { return failed(err, '#/live'); }
  const now = Date.now();
  const rows = liveChannels().map(c => {
    const { now: on, next } = nowNext(c, now);
    const start = on ? new Date(on.air_datetime).getTime() : 0;
    const pct = on && on.duration ? Math.min(100, ((now - start) / (on.duration * 1000)) * 100) : 0;
    const num = c.major > 0 ? `${c.major}.${c.minor}` : '';
    return `<button class="row f" data-act="tune" data-id="${esc(c.channel_id)}" data-key="ch-${esc(c.channel_id)}">
      <div class="ch-num">${esc(num)}</div>
      <div class="ch-logo">${c.logo_url ? `<img src="${esc(c.logo_url)}" alt="">` : `<b>${esc(c.call_sign || c.name)}</b>`}</div>
      <div class="body"><div class="name">${esc(on ? on.title : c.name)}${on && on.recording_now ? '<span class="rec">● REC</span>' : ''}</div>
        <div class="meta">${esc(c.name)}${on ? ` · until ${esc(fmt.time(start + on.duration * 1000))}` : ''}${next ? ` · Next: ${esc(next.title)}` : ''}</div>
        ${on ? `<div class="now-bar"><div style="width:${pct}%"></div></div>` : ''}</div>
    </button>`;
  });
  setScreen(`<div class="subtabs">
      <button class="btn f ${state.liveTab === 'ota' ? 'primary' : ''}" data-act="live-tab" data-tab="ota" data-key="lt-ota">Antenna</button>
      <button class="btn f ${state.liveTab === 'fast' ? 'primary' : ''}" data-act="live-tab" data-tab="fast" data-key="lt-fast">Streaming</button>
    </div>
    ${rows.length ? `<div class="rows">${rows.join('')}</div>` : '<div class="empty">No channels here.</div>'}`, '#/live');
}

function route() {
  const h = location.hash || '#/';
  if (h !== '#/play' && player.open) player.close();
  if (h === '#/play') { if (!player.open) location.replace('#/'); return; }
  if (h === '#/recordings') return showRecordings();
  if (h.startsWith('#/show/')) return showShow(decodeURIComponent(h.slice(7)));
  if (h === '#/live') return showLive();
  if (h === '#/watchlist') return showWatchlist();
  return showHome();
}

// ---------------------------------------------------------------------------
// Choices: a small box of big buttons. Resolves with the chosen value (null for Back)
// ---------------------------------------------------------------------------
let dialogDone = null;
function choose(title, text, buttons) {
  const box = $('#dialog');
  box.innerHTML = `<div class="dialog-box"><div class="dialog-title">${esc(title)}</div>
    ${text ? `<div class="dialog-text">${esc(text)}</div>` : ''}
    <div class="dialog-actions">${buttons.map((b, i) => `<button class="btn f ${i === 0 ? 'primary' : ''}" data-choice="${i}">${esc(b.label)}</button>`).join('')}</div></div>`;
  box.classList.remove('hidden');
  focusEl(box.querySelector('.f'));
  return new Promise(resolve => {
    dialogDone = i => {
      box.classList.add('hidden');
      box.innerHTML = '';
      dialogDone = null;
      resolve(i === null ? null : buttons[i].value);
    };
  });
}

// Other devices sign in once with the PIN set on the PC (remembered for 90 days)
function showPin(code) {
  const box = $('#dialog');
  if (!box.classList.contains('hidden')) return;
  box.innerHTML = code === 'pin_not_set'
    ? `<div class="dialog-box"><div class="dialog-title">Set a PIN on the PC first</div>
        <div class="dialog-text">On the PC running TabloView, open the Device page and set a PIN for other devices under Network access. Then try again here.</div>
        <div class="dialog-actions"><button class="btn primary f" data-act="reload">Try again</button></div></div>`
    : `<form class="dialog-box" id="pinForm"><div class="dialog-title">Enter the PIN</div>
        <div class="dialog-text">The PIN set on the PC running TabloView. This TV is remembered afterwards.</div>
        <input class="pin-input f" id="pinInput" type="password" inputmode="numeric" maxlength="6" autocomplete="current-password">
        <div class="error" id="pinError"></div>
        <div class="dialog-actions"><button class="btn primary f" type="submit">Sign in</button></div></form>`;
  box.classList.remove('hidden');
  focusEl(box.querySelector('.f'));
  const form = $('#pinForm');
  if (form) form.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('/api/lan/login', { method: 'POST', body: JSON.stringify({ pin: $('#pinInput').value.trim() }) });
      location.reload();
    } catch (err) { $('#pinError').textContent = err.message; }
  });
}

// ---------------------------------------------------------------------------
// Player: recordings (resume, skip, progress saved to the Tablo) and live TV (channel up/down)
// ---------------------------------------------------------------------------
const player = {
  open: false,
  s: {},  // what's playing: { kind: 'rec' | 'live', id, sessionId, offset, duration, ... }

  video: () => $('#video'),

  show(title, sub) {
    $('#osdTitle').textContent = title;
    $('#osdSub').textContent = sub || '';
    $('#player').classList.remove('hidden');
    if (location.hash !== '#/play') { this.returnTo = location.hash || '#/'; location.hash = '#/play'; }
    this.open = true;
    this.wake();
  },

  // OK: Pause, skip, Back to live, Close
  showControls() {
    const live = this.s.kind === 'live';
    this.controlList = live
      ? [['pause', this.video().paused ? '▶ Play' : '❚❚ Pause'], ['live', 'Back to live'], ['close', '✕ Close']]
      : [['pause', this.video().paused ? '▶ Play' : '❚❚ Pause'], ['back', '◀◀ 10 s'], ['fwd', '30 s ▶▶'], ['close', '✕ Close']];
    this.controlIndex = 0;
    this.controls = true;
    this.renderControls();
  },

  renderControls() {
    const box = $('#osdControls');
    box.innerHTML = this.controlList.map(([, label], i) => `<span class="ctl ${i === this.controlIndex ? 'on' : ''}">${esc(label)}</span>`).join('');
    box.classList.remove('hidden');
    this.wake();
    clearTimeout(this.controlsTimer);
    this.controlsTimer = setTimeout(() => this.hideControls(), 8000);
  },

  moveControl(dir) {
    this.controlIndex = Math.max(0, Math.min(this.controlList.length - 1, this.controlIndex + dir));
    this.renderControls();
  },

  pressControl() {
    const what = this.controlList[this.controlIndex][0];
    if (what === 'close') { this.hideControls(); this.exit(); return; }
    if (what === 'pause') this.togglePlay();
    else if (what === 'back') this.skip(-10);
    else if (what === 'fwd') this.skip(30);
    else if (what === 'live') { const w = this.liveWindow(); if (w) this.video().currentTime = Math.max(w.start, w.end - 6); this.video().play().catch(() => {}); }
    this.controlList[0][1] = this.video().paused ? '▶ Play' : '❚❚ Pause';
    this.renderControls();
  },

  hideControls() {
    this.controls = false;
    clearTimeout(this.controlsTimer);
    $('#osdControls').classList.add('hidden');
  },

  // Close the player and go back to the screen it was opened from
  exit() {
    if (location.hash === '#/play') history.back();
    // Some TV browsers don't step back through #/ addresses: close it ourselves then
    setTimeout(() => {
      if (!this.open) return;
      this.close();
      location.replace(this.returnTo || '#/');
    }, 400);
  },

  wake() {
    const p = $('#player');
    p.classList.remove('idle');
    clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => { if (!this.video().paused && !this.controls) p.classList.add('idle'); }, 4000);
  },

  message(text) {
    const m = $('#osdMsg');
    m.style.whiteSpace = 'pre-line';
    m.textContent = text || '';
    m.classList.toggle('hidden', !text);
  },

  // run: playing the Watch list (picks up where you left off, without asking)
  async playEpisode(id, { run = false } = {}) {
    const ep = (run ? state.run.eps : state.episodes || []).find(e => e.id === id);
    if (!ep) return;
    if (!run) state.run = null;
    let start = ep.program_start || 0;
    if (run) {
      if (ep.status !== 'Watched' && ep.position > 30) start = ep.position;
    } else if (ep.status !== 'Watched' && ep.position > 30) {
      const pick = await choose(ep.show_title || 'Recording', `You stopped at ${fmt.clock(ep.position)}.`,
        [{ label: `Resume at ${fmt.clock(ep.position)}`, value: 'resume' }, { label: 'Start over', value: 'start' }]);
      if (!pick) return;
      if (pick === 'resume') start = ep.position;
    }
    const previous = this.open ? this.s.sessionId : null;  // the Watch list's recording before this one
    this.s = { kind: 'rec', id, ep, duration: ep.actual_duration || ep.duration || 0, shapeKey: ep.channel_identifier || ep.channel_name };
    if (previous) { this.teardown(); await this.stopById(previous); }
    const counter = run && state.run.eps.length > 1 ? ` · ${state.run.index + 1} of ${state.run.eps.length}` : '';
    this.show(ep.show_title || 'Recording', [fmt.se(ep.season_number, ep.episode_number), ep.title !== ep.show_title ? ep.title : ''].filter(Boolean).join(' · ') + counter);
    await this.startRecording(start);
  },

  async startRecording(start) {
    const s = this.s;
    await this.stopSession();
    s.offset = start;
    s.lastSaved = start;
    this.message('Starting…');
    try {
      const res = await api(`/api/episodes/${encodeURIComponent(s.id)}/watch?transcode=true&start=${Math.floor(start)}`, { method: 'POST' });
      if (this.s !== s) return this.stopById(res.session_id);  // closed while it was starting
      s.sessionId = res.session_id;
      this.attach(res.stream_url);
      clearInterval(this.progressTimer);
      this.progressTimer = setInterval(() => this.saveProgress(), 30000);
    } catch (err) {
      this.message(`Couldn't start it: ${err.message}`);
    }
  },

  async tune(channelId) {
    const c = ((state.live && state.live.channels) || []).find(x => x.channel_id === channelId);
    if (!c) return;
    if (c.kind !== 'fast' && !this.open) {
      let check = null;
      try { check = await api('/api/live/tune_check'); } catch { /* don't block watching on a failed check */ }
      if (check && check.no_free_tuner) {
        if (!await choose('All tuners are busy', 'Tuning may fail until one frees up.', [{ label: 'Try anyway', value: 1 }, { label: 'Cancel', value: 0 }])) return;
      } else if (check && check.warn && check.recordings_soon && check.recordings_soon.length) {
        const first = check.recordings_soon[0];
        if (!await choose('Not enough tuners', `${first.title} will start recording at ${fmt.time(first.start)}, and watching now could make it fail.`,
          [{ label: 'Watch anyway', value: 1 }, { label: 'Cancel', value: 0 }])) return;
      }
    }
    const previous = this.s.sessionId;  // the channel playing now (changing channel), if any
    const s = { kind: 'live', id: channelId, channel: c, shapeKey: channelId };
    this.s = s;
    const on = nowNext(c).now;
    this.show(on ? on.title : c.name, `${c.major > 0 ? `${c.major}.${c.minor} ` : ''}${c.name}`);
    this.banner(`${c.major > 0 ? `${c.major}.${c.minor} ` : ''}${c.name}`);
    this.teardown();
    await this.stopById(previous);  // its tuner goes back to the Tablo before this one asks for one
    this.message(`Tuning ${c.name}…`);
    try {
      const res = await api('/api/live/tune', { method: 'POST', body: JSON.stringify({ channel_id: channelId, transcode: true, kind: c.kind }) });
      if (this.s !== s) return this.stopById(res.session_id);  // changed channel again meanwhile
      s.sessionId = res.session_id;
      this.attach(res.stream_url);
    } catch (err) {
      this.message(err.status === 409 || err.status === 503 ? `${err.message} Press Back to choose something else.` : `Couldn't tune ${c.name}: ${err.message}`);
    }
  },

  // Channel up/down in live TV, through the list it was picked from
  surf(dir) {
    const list = liveChannels();
    const i = list.findIndex(c => c.channel_id === this.s.id);
    if (i < 0 || !list.length) return;
    const next = list[(i + dir + list.length) % list.length];
    clearTimeout(this.surfTimer);
    this.banner(`${next.major > 0 ? `${next.major}.${next.minor} ` : ''}${next.name}`);
    this.surfTarget = next.channel_id;
    // Wait a moment, so pressing several times goes straight to the last channel
    this.surfTimer = setTimeout(() => this.tune(this.surfTarget), 700);
    this.s = { ...this.s, id: next.channel_id };
  },

  banner(text) {
    let b = $('#player .chan-banner');
    if (!b) { b = document.createElement('div'); b.className = 'chan-banner'; $('#player').appendChild(b); }
    b.textContent = text;
    b.classList.remove('hidden');
    clearTimeout(this.bannerTimer);
    this.bannerTimer = setTimeout(() => b.classList.add('hidden'), 3000);
  },

  attach(url) {
    const video = this.video();
    this.teardown();
    applyShape(video, this.s.shapeKey);
    if (window.Hls && Hls.isSupported()) {
      const hls = new Hls({ enableWorker: true, backBufferLength: 90, maxBufferLength: 60, maxBufferSize: 80 * 1000 * 1000 });
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
      hls.on(Hls.Events.ERROR, (evt, data) => {
        if (!data.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
        else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
        else this.message('The stream stopped. Press Back and try again.');
      });
      this.hls = hls;
    } else {
      video.src = url;  // Safari-style browsers play HLS themselves
      video.play().catch(() => {});
    }
    video.onplaying = () => this.message('');
    video.onended = () => this.ended();
    clearInterval(this.tickTimer);
    this.tickTimer = setInterval(() => this.tick(), 500);
  },

  position() { return Math.floor((this.s.offset || 0) + (this.video().currentTime || 0)); },

  liveWindow() {
    const v = this.video();
    return v.seekable && v.seekable.length ? { start: v.seekable.start(0), end: v.seekable.end(v.seekable.length - 1) } : null;
  },

  tick() {
    const s = this.s, v = this.video();
    if (s.kind === 'rec') {
      const pos = this.position();
      $('#osdNow').textContent = fmt.clock(pos);
      $('#osdEnd').textContent = s.duration ? fmt.clock(s.duration) : '';
      $('#osdPlayed').style.width = s.duration ? `${Math.min(100, (pos / s.duration) * 100)}%` : '0';
      $('#osdHint').textContent = v.paused ? 'Paused · OK for controls' : '◀ 10 s   OK controls   30 s ▶';
    } else {
      const w = this.liveWindow();
      const behind = w ? Math.max(0, w.end - v.currentTime) : 0;
      $('#osdNow').textContent = behind < 12 ? 'LIVE' : `−${fmt.clock(behind)}`;
      $('#osdEnd').textContent = '';
      $('#osdPlayed').style.width = w && w.end > w.start ? `${Math.min(100, ((v.currentTime - w.start) / (w.end - w.start)) * 100)}%` : '100%';
      $('#osdHint').textContent = v.paused ? 'Paused · OK for controls' : '▲ ▼ channel   ◀ ▶ skip   OK controls';
    }
  },

  togglePlay() {
    const v = this.video();
    if (v.paused) v.play().catch(() => {}); else v.pause();
    this.wake();
  },

  skip(seconds) {
    const s = this.s, v = this.video();
    this.wake();
    if (s.kind === 'live') {
      const w = this.liveWindow();
      if (w) v.currentTime = Math.max(w.start, Math.min(w.end - 2, v.currentTime + seconds));
      return;
    }
    const target = Math.max(0, Math.min((s.duration || Infinity) - 5, this.position() + seconds));
    const rel = target - (s.offset || 0);
    const w = this.liveWindow();  // for a recording: what's converted so far
    // Within what's been converted: jump there; earlier than the stream starts or past what's
    // converted, start the stream again at that point
    if (rel >= 0 && w && rel <= w.end - 1) v.currentTime = rel;
    else this.startRecording(target);
  },

  // Save the resume point on the Tablo; near the end, mark the recording watched instead
  saveProgress(final = false) {
    const s = this.s;
    if (s.kind !== 'rec' || s.markedWatched) return;
    const pos = this.position();
    const keepalive = final;
    if (s.duration && pos >= s.duration - Math.max(120, s.duration * 0.05)) {
      s.markedWatched = true;
      fetch(`/api/episodes/${encodeURIComponent(s.id)}/watched`, { method: 'POST', headers: API_HEADERS, body: JSON.stringify({ watched: true }), keepalive }).catch(() => {});
    } else if (pos > 30 && Math.abs(pos - (s.lastSaved || 0)) >= 10) {
      s.lastSaved = pos;
      fetch(`/api/episodes/${encodeURIComponent(s.id)}/progress`, { method: 'POST', headers: API_HEADERS, body: JSON.stringify({ position: pos }), keepalive }).catch(() => {});
    }
  },

  ended() {
    if (this.s.kind !== 'rec') return;
    this.saveProgress(true);
    const next = state.run && state.run.eps[state.run.index + 1];
    if (!next) {
      if (state.run) this.runFinished();
      this.message(state.run ? 'That was the last one on your Watch list' : 'Finished');
      setTimeout(() => { if (this.open && location.hash === '#/play') history.back(); }, 3000);
      return;
    }
    // Watch list: the next one starts by itself in a few seconds (OK starts it now, Back stops)
    let left = 8;
    const title = [next.show_title, fmt.se(next.season_number, next.episode_number)].filter(Boolean).join(' · ');
    const say = () => this.message(`Up next: ${title} in ${left} s\nOK to play it now · Back to stop`);
    say();
    this.upNext = setInterval(() => { left -= 1; if (left <= 0) this.playNext(); else say(); }, 1000);
  },

  playNext() {
    clearInterval(this.upNext);
    this.upNext = null;
    if (!state.run || !state.run.eps[state.run.index + 1]) return;
    this.runFinished();
    state.run.index += 1;
    this.playEpisode(state.run.eps[state.run.index].id, { run: true });
  },

  // The Watch list's current recording, if it was watched to the end: it comes off the list and,
  // with Watch and delete, is deleted from the Tablo (never when it's protected there). Only on
  // moving on or closing, as on the PC.
  runFinished() {
    const ep = state.run && state.run.eps[state.run.index];
    if (!ep || ep.id !== this.s.id || !this.s.markedWatched || ep.finished) return;
    ep.finished = true;
    api(`/api/watchlist/${encodeURIComponent(ep.id)}/finished`, { method: 'POST', body: JSON.stringify({ delete: state.run.deleteAfter }) }).catch(() => {});
  },

  teardown() {
    clearInterval(this.tickTimer);
    if (this.hls) { this.hls.destroy(); this.hls = null; }
    const v = this.video();
    v.pause();
    v.removeAttribute('src');
    v.load();
  },

  stopById(sessionId, keepalive = false) {
    if (!sessionId) return Promise.resolve();
    return fetch('/api/live/stop', { method: 'POST', headers: API_HEADERS, body: JSON.stringify({ session_id: sessionId }), keepalive }).catch(() => {});
  },

  // The Tablo's session ends too, so a live channel's tuner is freed at once
  stopSession(keepalive = false) {
    const id = this.s.sessionId;
    this.s.sessionId = null;
    return this.stopById(id, keepalive);
  },

  close(keepalive = false) {
    if (!this.open) return;
    this.saveProgress(true);
    this.runFinished();
    state.run = null;
    clearInterval(this.upNext);
    this.upNext = null;
    this.hideControls();
    clearInterval(this.progressTimer);
    clearTimeout(this.surfTimer);
    this.teardown();
    this.stopSession(keepalive);
    this.s = {};
    this.open = false;
    this.message('');
    $('#player').classList.add('hidden');
  },
};

// Picture shape for the channel, as chosen in the PC player (4:3, 16:9 or Zoom; Auto = as sent)
function applyShape(video, key) {
  const shape = (key && state.shapes[key]) || 'auto';
  const st = video.style;
  Object.assign(st, { left: '', top: '', width: '', height: '', objectFit: '', transform: '' });
  if (shape === 'zoom') { st.transform = 'scale(1.3333)'; return; }
  if (shape === 'auto') return;
  const W = window.innerWidth, H = window.innerHeight, ratio = shape === '4:3' ? 4 / 3 : 16 / 9;
  let w = W, h = W / ratio;
  if (h > H) { h = H; w = H * ratio; }
  Object.assign(st, { left: `${(W - w) / 2}px`, top: `${(H - h) / 2}px`, width: `${w}px`, height: `${h}px`, objectFit: 'fill' });
}

// ---------------------------------------------------------------------------
// Keys and clicks
// ---------------------------------------------------------------------------
const BACK_KEYS = ['Escape', 'Backspace', 'BrowserBack', 'GoBack'];
// Android's Back (4), browsers' Back (166), LG webOS (461), Samsung Tizen (10009)
const isBack = e => BACK_KEYS.includes(e.key) || [4, 8, 27, 166, 461, 10009].includes(e.keyCode);

function onKey(e) {
  const k = e.key;
  // Typing the PIN: leave its keys alone, except moving off the box
  if (e.target.id === 'pinInput' && !['ArrowDown', 'ArrowUp', 'Enter'].includes(k)) return;

  if (dialogDone && isBack(e)) { e.preventDefault(); dialogDone(null); return; }

  if (player.open && $('#dialog').classList.contains('hidden')) {
    if (player.upNext && (k === 'Enter' || k === ' ')) { e.preventDefault(); player.playNext(); return; }
    // The button row: arrows move along it, OK presses, Back/up/down put it away
    if (player.controls) {
      e.preventDefault();
      if (k === 'ArrowLeft' || k === 'ArrowRight') player.moveControl(k === 'ArrowLeft' ? -1 : 1);
      else if (k === 'Enter' || k === ' ') player.pressControl();
      else if (isBack(e) || k === 'ArrowUp' || k === 'ArrowDown') player.hideControls();
      return;
    }
    const live = player.s.kind === 'live';
    const keys = {
      Enter: () => player.showControls(), ' ': () => player.togglePlay(), MediaPlayPause: () => player.togglePlay(),
      MediaPlay: () => player.video().play(), MediaPause: () => player.video().pause(),
      ArrowLeft: () => player.skip(-10), MediaRewind: () => player.skip(-10),
      ArrowRight: () => player.skip(30), MediaFastForward: () => player.skip(30),
      ArrowUp: () => (live ? player.surf(-1) : player.wake()), ArrowDown: () => (live ? player.surf(1) : player.wake()),
      ChannelUp: () => live && player.surf(-1), ChannelDown: () => live && player.surf(1),
      PageUp: () => live && player.surf(-1), PageDown: () => live && player.surf(1),
    };
    if (keys[k]) { e.preventDefault(); keys[k](); player.wake(); return; }
    if (isBack(e)) { e.preventDefault(); player.exit(); }
    return;
  }

  const dirs = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' };
  if (dirs[k]) { e.preventDefault(); move(dirs[k]); return; }
  // OK presses what's highlighted, without relying on the browser to turn Enter into a click
  const cur = document.activeElement;
  if (k === 'Enter' && cur && cur.classList.contains('f') && cur.tagName === 'BUTTON' && !cur.closest('form')) {
    e.preventDefault();
    cur.click();
    return;
  }
  // Back on a screen: to Continue watching; on Continue watching it's left to the browser (leaving)
  if (isBack(e) && (location.hash || '#/') !== '#/') { e.preventDefault(); history.back(); }
}

function onClick(e) {
  const el = e.target.closest('[data-go], [data-act], [data-choice]');
  if (!el) return;
  if (el.dataset.choice !== undefined && dialogDone) return dialogDone(Number(el.dataset.choice));
  if (el.dataset.go) {
    const home = (location.hash || '#/') === '#/';
    if (el.classList.contains('tab') && !home) location.replace(el.dataset.go === '#/' ? '#/' : el.dataset.go);
    else location.hash = el.dataset.go;
    return;
  }
  const act = el.dataset.act;
  if (act === 'play') player.playEpisode(el.dataset.id);
  else if (act === 'tune') player.tune(el.dataset.id);
  else if (act === 'run') startRun(Number(el.dataset.from), el.dataset.how);
  else if (act === 'run-from') startRun(Number(el.dataset.from));
  else if (act === 'live-tab') { state.liveTab = el.dataset.tab; state.focus['#/live'] = `lt-${el.dataset.tab}`; showLive(); }
  else if (act === 'reload') location.reload();
  else if (act === 'pc-view') {
    try { localStorage.setItem('tv_view', 'pc'); } catch { /* the PC page opens anyway */ }
    location.href = '/';
  }
}

function tickClock() { $('#clock').textContent = fmt.time(Date.now()); }

function init() {
  // TV view is now this browser's view: the plain address opens it from here on (PC view undoes it)
  try { localStorage.setItem('tv_view', 'tv'); } catch { /* storage unavailable: /tv still works */ }
  document.addEventListener('keydown', onKey);
  document.addEventListener('click', onClick);
  // A pointer (TV Bro's or Silk's cursor mode) moves the highlight too
  document.addEventListener('mouseover', e => { const el = e.target.closest('.f'); if (el && el !== document.activeElement) el.focus({ preventScroll: true }); });
  document.addEventListener('mousemove', () => player.open && player.wake());
  window.addEventListener('hashchange', route);
  window.addEventListener('resize', () => player.open && applyShape(player.video(), player.s.shapeKey));
  // Leaving the page: save where the recording got to and free the stream (and its tuner)
  window.addEventListener('pagehide', () => player.close(true));
  // Leaving the browser (the remote's Home button) while something plays: it kept playing unseen and
  // was still going on coming back. Close it instead (place saved, live TV's tuner freed)
  document.addEventListener('visibilitychange', () => { if (document.hidden && player.open) player.exit(); });
  // While something plays (paused too), tell TabloView every minute, so it isn't closed as unused
  setInterval(() => {
    if (player.s.sessionId) api('/api/live/alive', { method: 'POST', body: JSON.stringify({ session_ids: [player.s.sessionId] }) }).catch(() => {});
  }, 60000);
  tickClock();
  setInterval(tickClock, 15000);
  api('/api/settings').then(s => { state.shapes = s.picture_shapes || {}; }).catch(() => {});
  if (location.hash === '#/play') location.replace('#/');
  route();
}

init();
