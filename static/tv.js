// TabloView TV: Home, Library, Live TV, the Watch list and Coming up for the TabloView TV app and TV
// browsers (TV Bro, Silk...), driven by a remote: arrows move between big tiles, Left past the first
// one opens the menu, OK picks, Back goes back. Screens are hash routes, so the browser's own Back
// button works too. The Guide, series scheduling, settings and exports stay on the PC page. Uses the
// same API and streams as the PC page.

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
  // Today, Tomorrow, or the day
  dayLabel: iso => {
    const d = new Date(iso), today = new Date();
    const days = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - new Date(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000);
    return days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
  },
};

// The menu's pictures (the PC page's icons)
const ICONS = {
  logo: '<rect x="2" y="6" width="20" height="15" rx="3" fill="currentColor" stroke="none"/><path d="m8 2 4 4 4-4"/>',
  home: '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
  library: '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
  live: '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
  queue: '<path d="M3 6h13M3 12h9M3 18h9"/><path d="M16 12.5v6.8a.5.5 0 0 0 .77.42l5-3.4a.5.5 0 0 0 0-.84l-5-3.4a.5.5 0 0 0-.77.42z" fill="currentColor" stroke="none"/>',
  calendar: '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  monitor: '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8M12 17v4"/>',
};
const svg = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;

const state = {
  live: null,        // /api/live/epg
  liveTab: 'ota',    // Antenna or Streaming channels
  shapes: {},        // picture shapes per channel, chosen on the PC (Settings page player)
  focus: {},         // screen -> data-key focused last, so Back returns to the same tile
  eps: new Map(),    // recordings seen on any screen, by ID: what a recording's page shows
  shows: {},         // show ID -> /api/shows/episodes, for switching seasons without asking again
  season: {},        // show ID -> the season showing
  // Shared with the PC page in the same browser: captions on or off, and playing the next episode
  captions: stored('tablo_cc', '0') === '1',
  autoplay: stored('tablo_autoplay', '1') !== '0',
};

function stored(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}

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
  if (el.dataset.key && !el.closest('.rail') && !el.closest('.dialog')) state.focus[location.hash || '#/'] = el.dataset.key;
}

const inRail = el => !!(el && el.closest && el.closest('.rail'));
const dialogOpen = () => !$('#dialog').classList.contains('hidden');

// Into the menu, on the page showing
function focusRail() {
  const items = [...document.querySelectorAll('.rail .f')];
  focusEl(items.find(el => el.classList.contains('active')) || items[0]);
}

// Back onto the page, where it was
function focusContent() {
  const all = focusables().filter(el => !inRail(el));
  const key = state.focus[location.hash || '#/'];
  focusEl((key && all.find(el => el.dataset.key === key)) || all[0]);
}

function move(dir) {
  const all = focusables();
  const cur = document.activeElement && all.includes(document.activeElement) ? document.activeElement : null;
  if (!cur) { focusEl(all.find(el => !inRail(el)) || all[0]); return; }
  // The menu goes up and down; Right goes back onto the page. The page's arrows stay on the page,
  // except Left past the first thing in a row, which opens the menu.
  const rail = !dialogOpen() && inRail(cur);
  if (!rail && !dialogOpen() && cur.closest('#epg') && guideMove(cur, dir)) return;
  if (rail && dir === 'right') { focusContent(); return; }
  if (rail && dir === 'left') return;
  const a = cur.getBoundingClientRect();
  const ax = a.left + a.width / 2, ay = a.top + a.height / 2;
  let best = null, bestScore = Infinity;
  for (const el of all) {
    if (el === cur || inRail(el) !== rail) continue;
    const b = el.getBoundingClientRect();
    const bx = b.left + b.width / 2, by = b.top + b.height / 2;
    let main, cross;
    // Left and right stay in the same row
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
  else if (dir === 'left' && !rail && !dialogOpen()) focusRail();
}

// ---------------------------------------------------------------------------
// Screens
// ---------------------------------------------------------------------------
// The screens the menu opens; others (a show, a recording) are reached from them, and Back returns
const TOP_SCREENS = ['#/', '#/library', '#/live', '#/watchlist', '#/upcoming'];

function setScreen(html, tab) {
  document.querySelectorAll('.nav').forEach(t => t.classList.toggle('active', t.dataset.go === tab));
  $('#screen').innerHTML = html;
  $('#screen').scrollTop = 0;
  // Onto the page where it was last, or its first tile. While it's loading (nothing to pick yet),
  // the highlight stays where it is: in the menu, if a page was just picked there
  const key = state.focus[location.hash || '#/'];
  const all = focusables().filter(el => !inRail(el));
  const el = (key && all.find(x => x.dataset.key === key)) || all[0];
  if (el && !dialogOpen()) focusEl(el);
}

function remember(eps) { for (const e of eps) state.eps.set(e.id, e); return eps; }

function loading(tab) { setScreen('<div class="empty">Loading…</div>', tab); }

function failed(err, tab) {
  if (err.code === 'pin_required' || err.code === 'pin_not_set') return;  // the PIN screen is up
  setScreen(`<div class="empty">Couldn't load this: ${esc(err.message)}<br><button class="btn primary f" data-act="reload">Try again</button></div>`, tab);
}

const progressBar = (pos, dur) => (pos > 30 && dur ? `<div class="progress"><div style="width:${Math.min(100, (pos / dur) * 100)}%"></div></div>` : '');
const art = url => (url ? `style="background-image:url('${esc(url)}')"` : '');

const epLine = e => [fmt.se(e.season_number, e.episode_number), e.title && e.title !== e.show_title ? e.title : ''].filter(Boolean).join(' · ');
const timeLeft = e => (e.position > 30 && e.status !== 'Watched' && e.duration ? `${fmt.mins((e.actual_duration || e.duration) - e.position)} left` : '');

// How a recording turned out, as the PC's Library says it: recording now, failed, partial or short;
// the commercial breaks found (or being found) and signal dropouts; protected
function recTags(e) {
  const tags = [];
  const mins = Math.round((e.actual_duration || 0) / 60);
  if (e.recording_state === 'recording') tags.push(['live', '● Recording']);
  else if (e.recording_state === 'failed') {
    // The Tablo can keep going after losing the signal: then nothing's cut short, but parts may be missing
    if (e.duration && (e.actual_duration || 0) >= e.duration - 60) tags.push(['caution', 'Signal problems']);
    else tags.push(mins > 0 ? ['caution', `Partial · ${mins}m`] : ['warn', 'Failed']);
  } else if (e.ended_early) tags.push(['caution', `Short · ${mins}m`]);
  if (e.commercials === 'done' && e.commercial_breaks) tags.push(['ads', `⏭ ${e.commercial_breaks === 1 ? '1 break' : `${e.commercial_breaks} breaks`}`]);
  else if (e.commercials === 'done') tags.push(['', 'No breaks found']);
  else if (e.commercials === 'analyzing') tags.push(['', 'Finding commercials']);
  else if (e.commercials === 'queued') tags.push(['', 'Commercials: waiting']);
  if (e.finding_dropouts) tags.push(['', 'Checking signal']);
  else if ((e.dropouts || []).length) tags.push(['caution', e.dropouts.length === 1 ? '1 dropout' : `${e.dropouts.length} dropouts`]);
  if (e.protected) tags.push(['', 'Protected']);
  return tags.map(([kind, text]) => `<span class="tag ${kind}">${esc(text)}</span>`).join('');
}
const chNum = c => (c.major > 0 ? `${c.major}.${c.minor}` : '');

// Home: rows to scroll along (Continue watching, On now, Recently recorded, Recording soon), as on the PC
const HOME_ROWS = ['continue', 'onnow', 'recent', 'soon'];  // TV view's rows, as designed

async function showHome() {
  loading('#/');
  const [progress, shows, , upcoming, settings] = await Promise.allSettled([
    api('/api/episodes/in_progress'), api('/api/shows'), loadLive(), api('/api/guide/upcoming'), api('/api/settings'),
  ]);
  if (progress.status === 'rejected' && shows.status === 'rejected') return failed(progress.reason, '#/');
  // The rows in the order chosen under Customize on the PC's Home, without the ones turned off there
  const prefs = settings.status === 'fulfilled' ? settings.value : {};
  const hidden = new Set(prefs.home_hidden || []);
  const order = prefs.home_order || [];
  const shelves = {};
  const shelf = (id, title, tiles) => {
    if (tiles.length && !hidden.has(id)) shelves[id] = `<section class="shelf"><h2>${esc(title)}</h2><div class="strip">${tiles.join('')}</div></section>`;
  };

  const eps = remember(progress.status === 'fulfilled' ? progress.value.episodes || [] : []);
  shelf('continue', 'Continue watching', eps.map(e => `
    <button class="tile f" data-go="#/ep/${encodeURIComponent(e.id)}" data-key="cw-${esc(e.id)}">
      <div class="art" ${art(e.snapshot_url || e.backdrop_url || e.cover_url)}>${progressBar(e.position, e.duration)}</div>
      <div class="label"><div class="name">${esc(e.show_title)}</div>
        <div class="meta">${esc([epLine(e), timeLeft(e)].filter(Boolean).join(' · '))}</div></div>
    </button>`));

  // On now: the favorite channels if there are any (chosen on the PC), else the antenna ones
  const channels = (state.live && state.live.channels) || [];
  const fav = channels.some(c => c.favorite);
  const now = Date.now();
  shelf('onnow', fav ? 'On now · Your favorite channels' : 'On now', channels.filter(c => (fav ? c.favorite : c.kind !== 'fast') && nowNext(c, now).now).slice(0, 16).map(c => {
    const on = nowNext(c, now).now;
    const start = new Date(on.air_datetime).getTime();
    const pct = on.duration ? Math.min(100, ((now - start) / (on.duration * 1000)) * 100) : 0;
    return `<button class="tile f" data-act="tune" data-id="${esc(c.channel_id)}" data-key="on-${esc(c.channel_id)}">
      <div class="art"><div class="logo">${c.logo_url ? `<img src="${esc(c.logo_url)}" alt="">` : esc(c.call_sign || c.name)}</div>
        <div class="now-bar"><div style="width:${pct}%"></div></div></div>
      <div class="label"><div class="name">${esc(on.title)}${on.recording_now ? '<span class="rec">● REC</span>' : ''}</div>
        <div class="meta">${esc([chNum(c), c.name].filter(Boolean).join(' '))} · until ${esc(fmt.time(start + on.duration * 1000))}</div></div>
    </button>`;
  }));

  const recent = (shows.status === 'fulfilled' ? shows.value.shows || [] : [])
    .sort((a, b) => String(b.latest_recording_date || '').localeCompare(String(a.latest_recording_date || ''))).slice(0, 20);
  shelf('recent', 'Recently recorded', recent.map(s => showTile(s, 'wide', 'rr')));

  // What the Tablo will record in the next 48 hours
  const horizon = now + 48 * 3600000;
  const soon = (upcoming.status === 'fulfilled' ? upcoming.value.recordings || [] : []).filter(a => new Date(a.air_datetime).getTime() < horizon).slice(0, 12);
  shelf('soon', 'Recording soon', soon.map((a, i) => {
    const t = new Date(a.air_datetime).getTime();
    const when = t <= now ? '<span class="tag live">REC</span>' : esc(`${fmt.dayLabel(a.air_datetime)} ${fmt.time(t)}`);
    return `<button class="tile f" data-go="#/upcoming" data-key="rs-${i}">
      <div class="art" ${art(a.backdrop_url || a.cover_url)}></div>
      <div class="label"><div class="name">${esc(a.show_title)}${a.wont_record || a.missed_new ? '<span class="tag warn">Won\'t record</span>' : ''}</div>
        <div class="meta">${when} · ${esc([a.channel_number, a.channel_call_sign].filter(Boolean).join(' '))}</div></div>
    </button>`;
  }));

  const ids = Object.keys(shelves).sort((a, b) => rank(a) - rank(b));
  function rank(id) { const i = order.indexOf(id); return i < 0 ? 100 + HOME_ROWS.indexOf(id) : i; }
  if (!ids.length) {
    return setScreen(`<div class="empty">Nothing here yet.<br>
      <button class="btn primary f" data-go="#/library" data-key="go-lib">Go to your Library</button></div>`, '#/');
  }
  setScreen(ids.map(id => shelves[id]).join(''), '#/');
}

function showTile(s, layout, prefix) {
  return `<button class="tile f" data-go="#/show/${encodeURIComponent(s.id)}" data-key="${prefix}-${esc(s.id)}">
    <div class="art" ${art(layout === 'wide' ? s.backdrop_url || s.cover_url : s.cover_url || s.backdrop_url)}>${s.unwatched_count ? `<span class="badge">${s.unwatched_count}</span>` : ''}</div>
    <div class="label"><div class="name">${esc(s.title)}</div>
      <div class="meta">${s.episode_count === 1 ? '1 recording' : `${s.episode_count} recordings`}</div></div>
  </button>`;
}

// The Library's choices, kept in this browser: wide pictures or posters (the same choice as the PC
// Library's), newest first or A to Z, and all shows or only ones with something not watched yet
function libraryPrefs() {
  const get = (k, d) => stored(k, d);
  return { layout: get('tv_lib_layout', 'wide') === 'posters' ? 'posters' : 'wide', sort: get('tv_lib_sort', 'recent') === 'az' ? 'az' : 'recent', unwatched: get('tv_lib_unwatched', '0') === '1' };
}

async function showLibrary() {
  loading('#/library');
  let shows;
  try { shows = (await api('/api/shows')).shows || []; } catch (err) { return failed(err, '#/library'); }
  if (!shows.length) return setScreen('<div class="empty">No recordings yet.</div>', '#/library');
  const p = libraryPrefs();
  if (p.unwatched) shows = shows.filter(s => s.unwatched_count > 0);
  // A to Z without "The", "A" or "An", as on the PC
  const bare = t => String(t || '').replace(/^(the|an|a)\s+/i, '');
  if (p.sort === 'az') shows.sort((a, b) => bare(a.title).localeCompare(bare(b.title)));
  else shows.sort((a, b) => String(b.latest_recording_date || '').localeCompare(String(a.latest_recording_date || '')));
  const opt = (key, value, label, on) => `<button class="btn f ${on ? 'primary' : ''}" data-act="lib-opt" data-opt="${key}" data-value="${value}" data-key="lib-${key}-${value}">${label}</button>`;
  setScreen(`<h1>Library</h1>
    <div class="subtabs">
      ${opt('layout', 'wide', 'Wide', p.layout === 'wide')}${opt('layout', 'posters', 'Posters', p.layout === 'posters')}<span class="gap"></span>
      ${opt('sort', 'recent', 'Newest', p.sort === 'recent')}${opt('sort', 'az', 'A to Z', p.sort === 'az')}<span class="gap"></span>
      ${opt('unwatched', p.unwatched ? '0' : '1', p.unwatched ? '✓ Not watched only' : 'Not watched only', p.unwatched)}
    </div>
    ${shows.length ? `<div class="grid ${p.layout}">${shows.map(s => showTile(s, p.layout, 'show')).join('')}</div>`
      : '<div class="empty">Everything here has been watched.</div>'}`, '#/library');
}

const seasonOf = e => (Number(e.season_number) > 0 ? Number(e.season_number) : 0);

async function showShow(id) {
  loading('#/library');
  let d;
  try { d = await api(`/api/shows/episodes?show_id=${encodeURIComponent(id)}`); } catch (err) { return failed(err, '#/library'); }
  state.shows[id] = d;
  renderShow(id);
}

// A show: its picture and description, then its episodes in the show's own order (oldest first, as
// on the PC), a season at a time when there are several
function renderShow(id) {
  const d = state.shows[id];
  const show = d.show || {};
  const all = remember(d.episodes || []);
  const seasons = [...new Set(all.map(seasonOf))].sort((a, b) => a - b);
  // Opening a show the first time: start at the first one not watched yet, not the oldest
  const firstNew = all.find(e => e.status !== 'Watched' && e.recording_state !== 'recording');
  if (!(id in state.season) || !seasons.includes(state.season[id])) state.season[id] = firstNew ? seasonOf(firstNew) : seasons[seasons.length - 1];
  const season = state.season[id];
  const eps = seasons.length > 1 ? all.filter(e => seasonOf(e) === season) : all;
  const at = location.hash;
  if (firstNew && eps.includes(firstNew) && !state.focus[at]) state.focus[at] = `ep-${firstNew.id}`;
  const unwatched = all.filter(e => e.status !== 'Watched').length;
  setScreen(`<div class="show-head" ${art(show.backdrop_url || show.cover_url)}>
      <h1>${esc(d.show_title || show.title || '')}</h1>
      <div class="dim">${all.length === 1 ? '1 recording' : `${all.length} recordings`}${unwatched ? ` · ${unwatched} not watched` : ''}</div>
      ${show.description ? `<p class="desc">${esc(show.description)}</p>` : ''}
    </div>
    ${seasons.length > 1 ? `<div class="subtabs">${seasons.map(n => `<button class="btn f ${n === season ? 'primary' : ''}" data-act="season" data-show="${esc(id)}" data-season="${n}" data-key="season-${n}">${n ? `Season ${n}` : 'Other'}</button>`).join('')}</div>` : ''}
    ${eps.length ? `<div class="rows">${eps.map(e => {
      const watched = e.status === 'Watched';
      return `<button class="row f" data-go="#/ep/${encodeURIComponent(e.id)}" data-key="ep-${esc(e.id)}">
        <div class="thumb" ${art(e.snapshot_url)}>${progressBar(watched ? 0 : e.position, e.duration)}</div>
        <div class="body"><div class="name">${watched ? '' : '<span class="dot"></span>'}${esc([fmt.se(e.season_number, e.episode_number), e.title].filter(Boolean).join(' · '))}${recTags(e)}</div>
          <div class="meta">${esc([e.air_date ? fmt.day(e.air_date) : '', e.duration ? fmt.mins(e.actual_duration || e.duration) : '', timeLeft(e), e.channel_name].filter(Boolean).join(' · '))}</div></div>
      </button>`;
    }).join('')}</div>` : '<div class="empty">No recordings left.</div>'}`, '#/library');
}

// A recording: what it is, and what you can do with it (play, the Watch list, watched, protect, delete)
async function showEpisode(id) {
  const e = state.eps.get(id);
  if (!e) { location.replace('#/library'); return; }
  let inList = false;
  try { inList = ((await api('/api/watchlist')).episodes || []).some(x => x.id === id); } catch { /* shown as not on it */ }
  if (location.hash !== `#/ep/${encodeURIComponent(id)}`) return;  // moved on meanwhile
  const watched = e.status === 'Watched';
  const resume = !watched && e.position > 30;
  const facts = [e.air_date ? fmt.day(e.air_date) : '', e.channel_name, e.duration ? fmt.mins(e.actual_duration || e.duration) : '',
    watched ? 'Watched' : timeLeft(e), inList ? 'On your Watch list' : ''].filter(Boolean);
  const btn = (act, label, extra = '') => `<button class="btn f ${extra}" data-act="${act}" data-id="${esc(id)}" data-key="${act}">${label}</button>`;
  setScreen(`<div class="detail">
      <div class="detail-body">
        <div class="kicker">${esc(e.show_title || '')}</div>
        <h1>${esc(epLine(e) || e.show_title || 'Recording')}</h1>
        <div class="meta">${esc(facts.join(' · '))}</div>
        ${recTags(e) ? `<div class="detail-tags">${recTags(e)}</div>` : ''}
        ${e.description ? `<p class="desc">${esc(e.description)}</p>` : ''}
        <div class="actions">
          ${resume ? `<div class="pair">${btn('play-resume', `▶ Resume at ${fmt.clock(e.position)}`, 'primary')}${btn('play-start', 'Start over')}</div>` : btn('play-start', '▶ Play', 'primary')}
          ${btn('watchlist', inList ? 'Remove from Watch list' : 'Add to Watch list')}
          ${btn('watched', watched ? 'Mark as not watched' : 'Mark as watched')}
          ${btn('protect', e.protected ? 'Unprotect' : 'Protect')}
          ${btn('delete', 'Delete')}
        </div>
      </div>
      <div class="detail-art" ${art(e.snapshot_url || e.backdrop_url || e.cover_url)}>${progressBar(watched ? 0 : e.position, e.duration)}</div>
    </div>`, '#/library');
}

// The recording page's buttons; the page is drawn again afterwards, on the same button
async function episodeAction(act, id) {
  const e = state.eps.get(id);
  if (!e) return;
  try {
    if (act === 'watchlist') {
      const on = ((await api('/api/watchlist')).episodes || []).some(x => x.id === id);
      if (on) await api(`/api/watchlist/${encodeURIComponent(id)}`, { method: 'DELETE' });
      else await api('/api/watchlist', { method: 'POST', body: JSON.stringify({ episode_ids: [id] }) });
    } else if (act === 'watched') {
      const watched = e.status !== 'Watched';
      await api(`/api/episodes/${encodeURIComponent(id)}/watched`, { method: 'POST', body: JSON.stringify({ watched }) });
      Object.assign(e, { status: watched ? 'Watched' : 'Unwatched', position: watched ? e.position : 0 });
    } else if (act === 'protect') {
      await api(`/api/episodes/${encodeURIComponent(id)}/protected`, { method: 'POST', body: JSON.stringify({ protected: !e.protected }) });
      e.protected = !e.protected;
    } else if (act === 'delete') {
      const ok = await choose(e.protected ? 'Delete this protected recording?' : 'Delete this recording?',
        `${[e.show_title, epLine(e)].filter(Boolean).join(' · ')} will be removed from your Tablo for good.${e.protected ? ' It\'s protected, so it would otherwise be kept.' : ''}`,
        [{ label: 'Cancel', value: false }, { label: 'Delete', value: true, danger: true }]);
      if (!ok) return;
      await api(`/api/episodes/${encodeURIComponent(id)}`, { method: 'DELETE' });
      state.eps.delete(id);
      history.back();
      return;
    }
  } catch (err) {
    await choose("Couldn't do that", err.message, [{ label: 'OK', value: 1 }]);
  }
  if (location.hash === `#/ep/${encodeURIComponent(id)}`) showEpisode(id);
}

async function showWatchlist() {
  loading('#/watchlist');
  let eps;
  try { eps = (await api('/api/watchlist')).episodes || []; } catch (err) { return failed(err, '#/watchlist'); }
  eps = remember(eps.filter(e => e.recording_state !== 'recording'));
  state.watchList = eps;
  if (!eps.length) {
    return setScreen(`<div class="empty">Your Watch list is empty.<br>Add recordings to it from a recording's page (pick one in a show in your Library),<br>then play them here one after another.</div>`, '#/watchlist');
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

const isRecording = a => a.schedule_state === 'scheduled' || !!a.recording_now || !!a.recording;

function nowNext(c, now = Date.now()) {
  const list = c.airings || [];
  const i = list.findIndex(a => { const s = new Date(a.air_datetime).getTime(); return s <= now && now < s + (a.duration || 0) * 1000; });
  return { now: list[i], next: i >= 0 ? list[i + 1] : list.find(a => new Date(a.air_datetime).getTime() > now) };
}

async function loadLive() {
  const end = state.live ? new Date(state.live.window_end).getTime() : 0;
  if (end - Date.now() > 30 * 60000) return state.live;
  // From half an hour back (the guide's own start) to the Guide view's last slot
  state.live = await api(`/api/live/epg?hours=${GUIDE_HOURS + 1}`);
  return state.live;
}

function liveChannels() {
  return ((state.live && state.live.channels) || []).filter(c => (state.liveTab === 'fast' ? c.kind === 'fast' : c.kind !== 'fast'));
}

// Live TV as a list (what's on now, and next) or as the Guide (the next GUIDE_HOURS, a row per channel)
const GUIDE_HOURS = 6;
const GUIDE_SLOT = 15;  // vw per half hour
const liveView = () => (stored('tv_live_view', 'list') === 'guide' ? 'guide' : 'list');

async function showLive() {
  loading('#/live');
  try { await loadLive(); } catch (err) { return failed(err, '#/live'); }
  const view = liveView();
  const tab = (act, key, value, label, on) => `<button class="btn f ${on ? 'primary' : ''}" data-act="${act}" data-${key}="${value}" data-key="${act}-${value}">${label}</button>`;
  setScreen(`<div class="subtabs">
      ${tab('live-tab', 'tab', 'ota', 'Antenna', state.liveTab === 'ota')}${tab('live-tab', 'tab', 'fast', 'Streaming', state.liveTab === 'fast')}<span class="gap"></span>
      ${tab('live-view', 'view', 'list', 'On now', view === 'list')}${tab('live-view', 'view', 'guide', 'Guide', view === 'guide')}
    </div>
    ${!liveChannels().length ? '<div class="empty">No channels here.</div>' : view === 'guide' ? guideGrid() : liveList()}`, '#/live');
}

function liveList() {
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
  return `<div class="rows">${rows.join('')}</div>`;
}

// The Guide: channels down the side, the next hours across, starting at this half hour. Every row has
// something to land on (a channel without listings is one long "No listings" that tunes it)
function guideGrid() {
  const now = Date.now();
  const start = Math.floor(now / 1800000) * 1800000, end = start + GUIDE_HOURS * 3600000;
  const x = t => Number((((t - start) / 1800000) * GUIDE_SLOT).toFixed(2));
  const times = Array.from({ length: GUIDE_HOURS * 2 }, (_, i) => `<div class="g-time" style="left:${x(start + i * 1800000)}vw">${esc(fmt.time(start + i * 1800000))}</div>`).join('');
  const rows = liveChannels().map(c => {
    const cells = (c.airings || []).map((a, i) => {
      const aStart = new Date(a.air_datetime).getTime(), aEnd = aStart + (a.duration || 0) * 1000;
      if (aEnd <= start || aStart >= end) return '';
      const s = Math.max(start, aStart), e = Math.min(end, aEnd);
      const mark = a.recording_now ? '<span class="rec">● REC</span>' : isRecording(a) ? '<span class="rec">●</span>' : a.is_new ? '<span class="tag new">NEW</span>' : '';
      return `<button class="g-cell f ${aStart <= now && now < aEnd ? 'now' : ''}" style="left:${x(s)}vw;width:${(x(e) - x(s)).toFixed(2)}vw"
        data-act="g-air" data-ch="${esc(c.channel_id)}" data-i="${i}" data-start="${s}" data-end="${e}" data-key="g-${esc(c.channel_id)}-${aStart}">
        <span class="g-title">${esc(a.title)}${mark}</span><span class="g-sub">${esc(fmt.time(aStart))} – ${esc(fmt.time(aEnd))}</span></button>`;
    }).join('') || `<button class="g-cell f" style="left:0;width:${x(end)}vw" data-act="tune" data-id="${esc(c.channel_id)}" data-start="${start}" data-end="${end}"
        data-key="g-${esc(c.channel_id)}-none"><span class="g-title dim">No listings</span></button>`;
    return `<div class="g-row"><div class="g-ch"><span class="ch-num">${esc(chNum(c))}</span>
        <span class="g-logo">${c.logo_url ? `<img src="${esc(c.logo_url)}" alt="">` : `<b>${esc(c.call_sign || c.name)}</b>`}</span></div>
      <div class="g-cells" style="width:${x(end)}vw">${cells}</div></div>`;
  }).join('');
  return `<div class="epg" id="epg"><div class="g-head"><div class="g-ch"></div><div class="g-cells" style="width:${x(end)}vw">${times}
      <div class="g-now" style="left:${x(now)}vw"></div></div></div>${rows}</div>`;
}

// Moving in the Guide, row by row (a streaming lineup has thousands of listings; measuring them all
// on every press was slow on a TV): along a row, then up and down to what's on at the same time.
// False hands over to the usual moving (up from the first row, to the buttons above)
function guideMove(cur, dir) {
  const start = Number(cur.dataset.start), end = Number(cur.dataset.end);
  if (dir === 'left' || dir === 'right') {
    const next = dir === 'right' ? cur.nextElementSibling : cur.previousElementSibling;
    if (next) { state.guideAt = Number(next.dataset.start); focusEl(next); } else if (dir === 'left') focusRail();
    return true;
  }
  // The time being looked at: kept while going up and down, so a long show doesn't pull it along
  const at = Math.min(Math.max(state.guideAt ?? start, start), end - 1);
  const rows = [...document.querySelectorAll('#epg .g-row')];
  const row = rows[rows.indexOf(cur.closest('.g-row')) + (dir === 'down' ? 1 : -1)];
  if (!row) return dir === 'down';
  const cells = [...row.querySelectorAll('.g-cell')];
  const target = cells.find(c => Number(c.dataset.start) <= at && at < Number(c.dataset.end))
    || cells.reduce((best, c) => (!best || Math.abs(Number(c.dataset.start) - at) < Math.abs(Number(best.dataset.start) - at) ? c : best), null);
  if (target) { state.guideAt = at; focusEl(target); }
  return true;
}

// OK on a listing: on now, watch it; later, record it (or not, if it's set to record)
async function guideAiring(chId, i) {
  const c = ((state.live && state.live.channels) || []).find(x => x.channel_id === chId);
  const a = c && (c.airings || [])[i];
  if (!a) return;
  const aStart = new Date(a.air_datetime).getTime(), aEnd = aStart + (a.duration || 0) * 1000;
  if (aStart <= Date.now() && Date.now() < aEnd) { player.tune(chId); return; }
  const recordable = a.airing_id ? c.can_record : a.path && !a.path.startsWith('/channel/') && !a.path.startsWith('/cloud/');
  const on = isRecording(a);
  const what = [fmt.se(a.season_number, a.episode_number), a.episode_title && a.episode_title !== a.title ? a.episode_title : ''].filter(Boolean).join(' · ');
  const text = `${fmt.dayLabel(a.air_datetime)}, ${fmt.time(aStart)} – ${fmt.time(aEnd)} · ${[chNum(c), c.name].filter(Boolean).join(' ')}`
    + (what ? ` · ${what}` : '') + (on ? '. Set to record.' : '') + (recordable ? '' : ". This channel can't be recorded.");
  const buttons = [...(recordable ? [{ label: on ? "Don't record it" : '● Record it', value: on ? 'skip' : 'record' }] : []), { label: 'Close', value: null }];
  const pick = await choose(a.title, text, buttons);
  if (!pick) return;
  try {
    const scheduled = pick === 'record';
    if (a.airing_id) await api('/api/streaming/record', { method: 'POST', body: JSON.stringify({ airing_id: a.airing_id, scheduled }) });
    else await api('/api/guide/episodes/schedule', { method: 'POST', body: JSON.stringify({ path: a.path, scheduled }) });
    a.schedule_state = scheduled ? 'scheduled' : 'none';
    showLive();
  } catch (err) {
    await choose("Couldn't do that", err.message, [{ label: 'OK', value: 1 }]);
  }
}

// Coming up: what the Tablo will record, by day. OK on one skips it (or records one the Tablo
// skipped as not new); changing what a series records stays on the PC's Guide.
async function showUpcoming() {
  loading('#/upcoming');
  let u;
  try { u = await api('/api/guide/upcoming'); } catch (err) { return failed(err, '#/upcoming'); }
  state.upcoming = u.recordings || [];
  if (!state.upcoming.length) return setScreen('<div class="empty">Nothing is set to record.<br>Choose shows to record in the Guide on the PC.</div>', '#/upcoming');
  const now = Date.now();
  const days = [];
  state.upcoming.forEach((a, i) => {
    const day = fmt.dayLabel(a.air_datetime);
    if (!days.length || days[days.length - 1].day !== day) days.push({ day, rows: [] });
    const start = new Date(a.air_datetime).getTime();
    const tags = (start <= now && !a.wont_record && !a.missed_new ? '<span class="tag live">REC</span>' : '')
      + (a.wont_record || a.missed_new ? '<span class="tag warn">Won\'t record</span>' : a.conflict ? '<span class="tag warn">Conflict</span>' : '')
      + (a.is_new ? '<span class="tag new">NEW</span>' : '');
    days[days.length - 1].rows.push(`<button class="row f" data-act="upcoming" data-i="${i}" data-key="up-${esc(a.path)}">
      <div class="when">${esc(fmt.time(start))}</div>
      <div class="thumb" ${art(a.backdrop_url || a.cover_url)}></div>
      <div class="body"><div class="name">${esc(a.show_title)}${tags}</div>
        <div class="meta">${esc([fmt.se(a.season_number, a.episode_number), a.episode_title, [a.channel_number, a.channel_call_sign].filter(Boolean).join(' '), `until ${fmt.time(start + (a.duration || 0) * 1000)}`].filter(Boolean).join(' · '))}</div></div>
    </button>`);
  });
  const wont = state.upcoming.filter(a => a.wont_record || a.missed_new).length;
  setScreen(`<h1>Coming up</h1>
    ${wont ? `<div class="dim" style="margin-bottom:1.6vw">${wont === 1 ? '1 recording' : `${wont} recordings`} won't record: more shows overlap than your Tablo has tuners, or the Tablo decided an episode isn't new. The PC's Scheduled page can fix overlaps.</div>` : ''}
    ${days.map(d => `<h2>${esc(d.day)}</h2><div class="rows">${d.rows.join('')}</div>`).join('')}`, '#/upcoming');
}

async function upcomingAction(i) {
  const a = state.upcoming && state.upcoming[i];
  if (!a) return;
  const schedule = scheduled => (a.streaming
    ? api('/api/streaming/record', { method: 'POST', body: JSON.stringify({ airing_id: a.path, scheduled }) })
    : api('/api/guide/episodes/schedule', { method: 'POST', body: JSON.stringify({ path: a.path, scheduled }) }));
  const title = [a.show_title, fmt.se(a.season_number, a.episode_number)].filter(Boolean).join(' · ');
  try {
    if (a.missed_new) {
      const go = await choose(title, "The guide calls this episode new, but your Tablo decided it isn't, so the series' Record New skips it.",
        [{ label: 'Record it anyway', value: true }, { label: 'Cancel', value: false }]);
      if (!go) return;
      await schedule(true);
    } else if (new Date(a.air_datetime).getTime() <= Date.now() && !a.wont_record) {
      await choose(title, 'This is recording now.', [{ label: 'OK', value: 1 }]);
      return;
    } else {
      const skip = await choose(`Skip this recording of ${a.show_title}?`,
        a.streaming ? "Your Tablo won't record this airing." : 'Only this airing is skipped. The series stays scheduled.',
        [{ label: 'Keep it', value: false }, { label: 'Skip recording', value: true, danger: true }]);
      if (!skip) return;
      await schedule(false);
    }
  } catch (err) {
    await choose("Couldn't do that", err.message, [{ label: 'OK', value: 1 }]);
    return;
  }
  showUpcoming();
}

function route() {
  const h = location.hash || '#/';
  if (h !== '#/play' && player.open) player.close();
  if (h === '#/play') { if (!player.open) location.replace('#/'); return; }
  if (h === '#/library' || h === '#/recordings') return showLibrary();  // #/recordings: its 1.2.5 name
  if (h.startsWith('#/show/')) return showShow(decodeURIComponent(h.slice(7)));
  if (h.startsWith('#/ep/')) return showEpisode(decodeURIComponent(h.slice(5)));
  if (h === '#/live') return showLive();
  if (h === '#/watchlist') return showWatchlist();
  if (h === '#/upcoming') return showUpcoming();
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
    <div class="dialog-actions">${buttons.map((b, i) => `<button class="btn f ${b.danger ? 'danger' : i === 0 ? 'primary' : ''}" data-choice="${i}">${esc(b.label)}</button>`).join('')}</div></div>`;
  const was = document.activeElement;
  box.classList.remove('hidden');
  focusEl(box.querySelector('.f'));
  return new Promise(resolve => {
    dialogDone = i => {
      box.classList.add('hidden');
      box.innerHTML = '';
      dialogDone = null;
      if (was && was.isConnected && !player.open) was.focus({ preventScroll: true });  // back where it was
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
        <div class="dialog-text">On the PC running TabloView, open the Settings page and set a PIN for other devices under Network access. Then try again here.</div>
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

// Broadcast captions moved up to `bottom` (% from the top), clear of the title and bar. Roll-up captions
// have two or three rows up at once, each its own cue (hls.js numbers them by row): they're kept a row
// apart in their order. Moved all to one spot, the line scrolling away showed through the new one
// (a forum report from the Google TV app, 2026-10-28)
const CAPTION_ROW = 5.5;
function stackCues(track, bottom) {
  const cues = [...(track.activeCues || [])];
  for (const c of cues) if (c.__row === undefined) c.__row = typeof c.line === 'number' ? c.line : 99;
  cues.sort((a, b) => b.__row - a.__row || b.startTime - a.startTime);
  let top = bottom;
  cues.forEach((c, i) => {
    if (i) top -= CAPTION_ROW * String(c.text || '').split('\n').length;
    if (c.line !== top || c.snapToLines) { c.snapToLines = false; c.line = top; }
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
    if (APP) APP.setPlaying(true);
    $('#osdTitle').textContent = title;
    $('#osdSub').textContent = sub || '';
    $('#player').classList.remove('hidden');
    if (location.hash !== '#/play') { this.returnTo = location.hash || '#/'; location.hash = '#/play'; }
    this.open = true;
    this.wake();
  },

  // OK: Pause, skip, Back to live, Captions, Shape, Close
  showControls(index = 0) {
    const live = this.s.kind === 'live';
    const shape = this.s.shapeKey ? [['shape', `Shape: ${SHAPE_NAMES[shapeOf(this.s.shapeKey)]}`]] : [];
    const cc = ['cc', state.captions ? 'CC: On' : 'CC: Off'];
    const hit = live && this.liveAiring();
    const record = hit ? [['record', isRecording(hit.a) ? '● Recording' : '● Record']] : [];
    this.controlList = live
      ? [['pause', this.video().paused ? '▶ Play' : '❚❚ Pause'], ['live', 'Back to live'], ...record, cc, ...shape, ['close', '✕ Close']]
      : [['pause', this.video().paused ? '▶ Play' : '❚❚ Pause'], ['back', '◀◀ 10 s'], ['fwd', '30 s ▶▶'], cc, ...shape, ['close', '✕ Close']];
    this.controlIndex = Math.min(index, this.controlList.length - 1);
    this.controls = true;
    this.shapeMenu = false;
    this.renderControls();
  },

  // Shape: the choices in place of the buttons, the current one highlighted
  showShapes() {
    const now = shapeOf(this.s.shapeKey);
    this.controlList = SHAPES.map(v => [v, SHAPE_NAMES[v]]);
    this.controlIndex = SHAPES.indexOf(now);
    this.shapeMenu = true;
    this.renderControls();
  },

  async pickShape(shape) {
    const key = this.s.shapeKey;
    if (shape === 'auto') delete state.shapes[key]; else state.shapes[key] = shape;
    applyShape(this.video(), key);
    this.showControls();  // back to the buttons, on Shape
    this.controlIndex = this.controlList.findIndex(([v]) => v === 'shape');
    this.renderControls();
    try {
      const res = await api('/api/settings/picture_shape', { method: 'POST', body: JSON.stringify({ channel: key, shape }) });
      state.shapes = res.picture_shapes || state.shapes;
    } catch (err) { this.message(`Couldn't save the shape: ${err.message}`); setTimeout(() => this.message(''), 4000); }
  },

  renderControls() {
    const box = $('#osdControls');
    // The shape choices are short names; the highlighted one is explained underneath
    const hint = this.shapeMenu ? SHAPE_HINTS[this.controlList[this.controlIndex][0]] : '';
    box.innerHTML = `<div class="ctl-row">${this.controlList.map(([, label], i) => `<button class="ctl ${i === this.controlIndex ? 'on' : ''}" data-ctl="${i}">${esc(label)}</button>`).join('')}</div>`
      + (hint ? `<div class="ctl-hint">${esc(hint)}</div>` : '');
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
    if (this.shapeMenu) { this.pickShape(what); return; }
    if (what === 'shape') { this.showShapes(); return; }
    if (what === 'close') { this.hideControls(); this.exit(); return; }
    if (what === 'record') { this.recordLive(); return; }
    if (what === 'cc') {
      this.toggleCaptions();
      this.controlList[this.controlIndex][1] = state.captions ? 'CC: On' : 'CC: Off';
    } else if (what === 'pause') this.togglePlay();
    else if (what === 'back') this.skip(-10);
    else if (what === 'fwd') this.skip(30);
    else if (what === 'live') { const w = this.liveWindow(); if (w) this.video().currentTime = Math.max(w.start, w.end - 6); this.video().play().catch(() => {}); }
    this.controlList[0][1] = this.video().paused ? '▶ Play' : '❚❚ Pause';
    this.renderControls();
  },

  hideControls() {
    this.controls = false;
    this.shapeMenu = false;
    clearTimeout(this.controlsTimer);
    $('#osdControls').classList.add('hidden');
    // The title bar's own timer ran out while the buttons were up: start it again, or the bar
    // stayed on screen until the next key
    if (this.open) this.wake();
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
    this.placeCaptions();
    clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => {
      if (!this.video().paused && !this.controls) { p.classList.add('idle'); this.placeCaptions(); }
    }, 4000);
  },

  // Closed captions: the broadcast's own, carried in the converted video; hls.js makes them a text
  // track, which this shows or hides (the same switch as the PC page's CC button)
  toggleCaptions() {
    state.captions = !state.captions;
    try { localStorage.setItem('tablo_cc', state.captions ? '1' : '0'); } catch { /* this visit only */ }
    this.applyCaptions();
    if (state.captions && !this.video().textTracks.length) this.banner('Captions appear as soon as the broadcast sends them');
  },

  applyCaptions() {
    for (const t of this.video().textTracks) {
      t.mode = state.captions ? 'showing' : 'hidden';
      if (t.__raised) continue;
      t.__raised = true;
      t.addEventListener('cuechange', () => this.placeCaptions());
    }
  },

  // Broadcast captions sit on the bottom rows: above the title and bar while they're up, low
  // down once they fade
  placeCaptions() {
    const line = $('#player').classList.contains('idle') ? 84 : 64;
    for (const t of this.video().textTracks) stackCues(t, line);
  },

  message(text) {
    const m = $('#osdMsg');
    m.style.whiteSpace = 'pre-line';
    m.textContent = text || '';
    m.classList.toggle('hidden', !text);
  },

  // run: playing the Watch list; next: the episode after one that just ended. Both pick up where
  // you left off, without asking. from: 'resume' or 'start', chosen on the recording's page
  async playEpisode(id, { run = false, next = null, from = null } = {}) {
    const ep = next || (run ? state.run.eps.find(e => e.id === id) : state.eps.get(id));
    if (!ep) return;
    if (!run) state.run = null;
    let start = ep.program_start || 0;
    if (run || next || from === 'resume') {
      if (ep.status !== 'Watched' && ep.position > 30) start = ep.position;
    } else if (!from && ep.status !== 'Watched' && ep.position > 30) {
      const pick = await choose(ep.show_title || 'Recording', `You stopped at ${fmt.clock(ep.position)}.`,
        [{ label: `Resume at ${fmt.clock(ep.position)}`, value: 'resume' }, { label: 'Start over', value: 'start' }]);
      if (!pick) return;
      if (pick === 'resume') start = ep.position;
    }
    const previous = this.open ? this.s.sessionId : null;  // the Watch list's recording before this one
    this.s = { kind: 'rec', id, ep, duration: ep.actual_duration || ep.duration || 0, shapeKey: ep.channel_identifier || ep.channel_name };
    if (previous) { this.teardown(); await this.stopById(previous); }
    this.loadBreaks(this.s);
    this.loadPreviews(this.s);
    if (!run) this.findNext(this.s);
    const counter = run && state.run.eps.length > 1 ? ` · ${state.run.index + 1} of ${state.run.eps.length}` : '';
    this.show(ep.show_title || 'Recording', [fmt.se(ep.season_number, ep.episode_number), ep.title !== ep.show_title ? ep.title : ''].filter(Boolean).join(' · ') + counter);
    await this.startRecording(start);
  },

  // The show's next episode not yet watched (in the show's own order, as on the PC), for Up next
  async findNext(s) {
    if (!s.ep.show_id) return;
    let list;
    try { list = (await api(`/api/shows/episodes?show_id=${encodeURIComponent(s.ep.show_id)}`)).episodes || []; } catch { return; }
    const i = list.findIndex(e => e.id === s.id);
    if (this.s === s && i >= 0) s.nextEp = list.slice(i + 1).find(e => e.status !== 'Watched' && e.recording_state !== 'recording') || null;
  },

  // Commercial breaks found in this recording, and signal dropouts: marked on the bar, skipped
  // automatically when that's on (Settings → Playback, the same settings as the PC), else OK skips
  async loadBreaks(s) {
    let res;
    try { res = await api(`/api/episodes/${encodeURIComponent(s.id)}/commercials`); } catch { return; }
    if (this.s !== s) return;
    Object.assign(s, { breaks: res.breaks || [], dropouts: res.dropouts || [], autoSkip: !!res.auto_skip,
      autoSkipDropouts: !!res.auto_skip_dropouts, skippedBreaks: new Set(), skippedDropouts: new Set() });
    this.drawMarks();
  },

  // Timeline previews from the Tablo's own trick-play file, as on the PC (the server fetches it in
  // the background once the recording starts, so ask again for a few seconds)
  async loadPreviews(s) {
    for (let i = 0; i < 6; i++) {
      await new Promise(r => setTimeout(r, i ? 1500 : 500));
      if (this.s !== s) return;
      try {
        const res = await api(`/api/episodes/${encodeURIComponent(s.id)}/previews`);
        if (res.times && res.times.length) { s.previewTimes = res.times; return; }
      } catch { /* try again */ }
    }
  },

  // The picture for a time in the recording: the Tablo's (whole recording) or, without those, the
  // frames FFmpeg saves as it converts (only what's converted so far)
  previewUrl(t) {
    const s = this.s, times = s.previewTimes || [];
    if (times.length) {
      let n = 0;
      while (n + 1 < times.length && times[n + 1] <= t) n++;
      return `/api/episodes/${encodeURIComponent(s.id)}/previews/${n}`;
    }
    return s.sessionId ? `/api/transcoded/${s.sessionId}/p${String(Math.floor(t / 5)).padStart(5, '0')}.jpg` : '';
  },

  // While skipping: the picture at the time being skipped to, until a moment after the last press
  showPreview(t) {
    const s = this.s, box = $('#osdPreview'), img = $('#osdPreviewImg');
    if (!s.duration) return;
    const url = this.previewUrl(t);
    img.onerror = () => img.classList.add('none');
    img.onload = () => img.classList.remove('none');
    if (url && img.getAttribute('src') !== url) img.src = url;
    img.classList.toggle('none', !url);
    $('#osdPreviewTime').textContent = fmt.clock(t);
    box.style.left = `${Math.max(11, Math.min(89, (t / s.duration) * 100))}%`;
    box.classList.remove('hidden');
    clearTimeout(this.previewTimer);
    this.previewTimer = setTimeout(() => box.classList.add('hidden'), 1500);
  },

  drawMarks() {
    const s = this.s, bar = $('#osdMarks');
    if (!s.duration || !s.breaks) { bar.innerHTML = ''; return; }
    const span = (b, cls) => `<span class="${cls}" style="left:${(b.start / s.duration) * 100}%;width:${Math.max(0.3, ((b.end - b.start) / s.duration) * 100)}%"></span>`;
    bar.innerHTML = s.breaks.map(b => span(b, 'osd-mark')).join('') + s.dropouts.map(d => span(d, 'osd-mark drop')).join('');
  },

  // In a break (or a dropout): skip it once automatically, or offer OK to skip
  checkBreak(pos) {
    const s = this.s;
    const find = (list, edge) => (list || []).findIndex(b => pos >= b.start && pos < b.end - edge);
    let i = find(s.breaks, 2), kind = 'break';
    if (i < 0) { i = find(s.dropouts, 0.5); kind = 'dropout'; }
    if (i < 0) { this.showSkip(null); return; }
    const b = (kind === 'break' ? s.breaks : s.dropouts)[i];
    const auto = kind === 'break' ? s.autoSkip : s.autoSkipDropouts;
    const done = kind === 'break' ? s.skippedBreaks : s.skippedDropouts;
    if (auto && !done.has(i)) {
      done.add(i);
      this.showSkip(null);
      this.banner(kind === 'break' ? `Skipped a ${fmt.mins(b.end - b.start)} commercial break` : 'Skipped a signal dropout');
      this.seekTo(b.end);
      return;
    }
    // Watching it anyway (or went back into one already skipped): OK skips it
    this.showSkip({ end: b.end, text: `${kind === 'break' ? 'Commercial break' : 'Signal dropout'} · ${fmt.clock(b.end - pos)} · OK to skip` });
  },

  showSkip(skip) {
    this.inBreak = skip;
    const el = $('#skipBanner');
    el.textContent = skip ? skip.text : '';
    el.classList.toggle('hidden', !skip);
  },

  skipBreak() {
    const end = this.inBreak && this.inBreak.end;
    this.showSkip(null);
    if (end) this.seekTo(end);
  },

  async startRecording(start) {
    const s = this.s;
    // Each start overtakes the one before: a stream that arrives after a newer start was asked for
    // is stopped at once (quick skips each left an FFmpeg running, seven at a time)
    const gen = s.gen = (s.gen || 0) + 1;
    clearTimeout(this.seekTimer);
    this.pendingSeek = null;
    this.teardown();
    await this.stopSession();
    s.offset = start;
    s.lastSaved = start;
    this.message('Starting…');
    try {
      const res = await api(`/api/episodes/${encodeURIComponent(s.id)}/watch?transcode=true&start=${Math.floor(start)}`, { method: 'POST' });
      if (this.s !== s || s.gen !== gen) return this.stopById(res.session_id);  // closed, or overtaken
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

  // What's on the channel playing, if the Tablo can record it (as the PC player's Record button):
  // streaming channels that allow recording, by the airing's ID; antenna ones with guide data
  liveAiring() {
    const c = this.s.kind === 'live' && ((state.live && state.live.channels) || []).find(x => x.channel_id === this.s.id);
    const a = c && nowNext(c).now;
    if (!a) return null;
    if (a.airing_id) return c.can_record ? { c, a } : null;
    return a.path && !a.path.startsWith('/channel/') && !a.path.startsWith('/cloud/') ? { c, a } : null;
  },

  // Record what's on, from now until it ends
  async recordLive() {
    const hit = this.liveAiring();
    if (!hit) return;
    if (isRecording(hit.a)) { this.banner(`${hit.a.title} is recording on your Tablo`); return; }
    try {
      if (hit.a.airing_id) await api('/api/streaming/record', { method: 'POST', body: JSON.stringify({ airing_id: hit.a.airing_id, scheduled: true }) });
      else await api('/api/guide/episodes/schedule', { method: 'POST', body: JSON.stringify({ path: hit.a.path, scheduled: true }) });
      hit.a.schedule_state = 'scheduled';
      this.banner(`Recording ${hit.a.title} until it ends. It'll be in your Library.`);
    } catch (err) {
      this.banner(`Couldn't record it: ${err.message}`);
    }
    if (this.controls) {
      const i = this.controlList.findIndex(([v]) => v === 'record');
      if (i >= 0) this.controlList[i][1] = isRecording(hit.a) ? '● Recording' : '● Record';
      this.renderControls();
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

  position() {
    if (this.pendingSeek !== null && this.pendingSeek !== undefined) return this.pendingSeek;  // a jump about to start
    return Math.floor((this.s.offset || 0) + (this.video().currentTime || 0));
  },

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
      $('#osdHint').textContent = v.paused ? 'Paused' : '';
      if (s.breaks) this.checkBreak(pos);
    } else {
      const w = this.liveWindow();
      const behind = w ? Math.max(0, w.end - v.currentTime) : 0;
      $('#osdNow').textContent = behind < 12 ? 'LIVE' : `−${fmt.clock(behind)}`;
      $('#osdEnd').textContent = '';
      $('#osdPlayed').style.width = w && w.end > w.start ? `${Math.min(100, ((v.currentTime - w.start) / (w.end - w.start)) * 100)}%` : '100%';
      $('#osdHint').textContent = v.paused ? 'Paused' : '';
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
    this.seekTo(this.position() + seconds);
    this.showPreview(this.position());
  },

  seekTo(time) {
    const s = this.s, v = this.video();
    const target = Math.max(0, Math.min((s.duration || Infinity) - 5, time));
    const rel = target - (s.offset || 0);
    const w = this.liveWindow();  // for a recording: what's converted so far
    // Within what's been converted: jump there; earlier than the stream starts or past what's
    // converted, start the stream again at that point
    if (this.pendingSeek == null && rel >= 0 && w && rel <= w.end - 1) { v.currentTime = rel; return; }
    // Wait for the presses to stop, then start the stream once at the total (▶▶▶ = one 90 s jump)
    this.pendingSeek = target;
    this.tick();
    clearTimeout(this.seekTimer);
    this.seekTimer = setTimeout(() => this.startRecording(this.pendingSeek), 800);
  },

  // Save the resume point on the Tablo; near the end, mark the recording watched instead
  saveProgress(final = false) {
    const s = this.s;
    if (s.kind !== 'rec' || s.markedWatched) return;
    const pos = this.position();
    const keepalive = final;
    // The recording's page shows it straight away on coming back
    const ep = state.eps.get(s.id) || s.ep;
    if (s.duration && pos >= s.duration - Math.max(120, s.duration * 0.05)) {
      s.markedWatched = true;
      if (ep) Object.assign(ep, { status: 'Watched', position: 0 });
      fetch(`/api/episodes/${encodeURIComponent(s.id)}/watched`, { method: 'POST', headers: API_HEADERS, body: JSON.stringify({ watched: true }), keepalive }).catch(() => {});
    } else if (pos > 30 && Math.abs(pos - (s.lastSaved || 0)) >= 10) {
      s.lastSaved = pos;
      if (ep) ep.position = pos;
      fetch(`/api/episodes/${encodeURIComponent(s.id)}/progress`, { method: 'POST', headers: API_HEADERS, body: JSON.stringify({ position: pos }), keepalive }).catch(() => {});
    }
  },

  ended() {
    if (this.s.kind !== 'rec') return;
    this.saveProgress(true);
    const next = state.run ? state.run.eps[state.run.index + 1] : state.autoplay && this.s.nextEp;
    if (!next) {
      if (state.run) this.runFinished();
      this.message(state.run ? 'That was the last one on your Watch list' : 'Finished');

      setTimeout(() => { if (this.open && location.hash === '#/play') history.back(); }, 3000);
      return;
    }
    // The Watch list's next one, or the show's next episode, starts by itself in a few seconds (OK
    // starts it now, Back stops)
    let left = 8;
    const title = [next.show_title || this.s.ep.show_title, fmt.se(next.season_number, next.episode_number)].filter(Boolean).join(' · ');
    const say = () => this.message(`Up next: ${title} in ${left} s\nOK to play it now · Back to stop`);
    say();
    this.upNext = setInterval(() => { left -= 1; if (left <= 0) this.playNext(); else say(); }, 1000);
  },

  playNext() {
    clearInterval(this.upNext);
    this.upNext = null;
    if (!state.run) {
      if (this.s.nextEp) this.playEpisode(this.s.nextEp.id, { next: this.s.nextEp });
      return;
    }
    if (!state.run.eps[state.run.index + 1]) return;
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
    if (APP) APP.setPlaying(false);
    clearTimeout(this.seekTimer);
    this.pendingSeek = null;
    if (this.s.kind === 'rec') this.s.gen = (this.s.gen || 0) + 1;  // a stream still starting is stopped when it arrives
    this.saveProgress(true);
    this.runFinished();
    state.run = null;
    clearInterval(this.upNext);
    this.upNext = null;
    this.hideControls();
    this.showSkip(null);
    $('#osdMarks').innerHTML = '';
    clearTimeout(this.previewTimer);
    $('#osdPreview').classList.add('hidden');
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

// Picture shape per channel (4:3, 16:9 or Zoom; Auto = as sent): the same choices as the PC player,
// saved for the channel, so either view can set them
const SHAPES = ['auto', '4:3', '16:9', 'zoom'];
const SHAPE_NAMES = { auto: 'Auto', '4:3': '4:3', '16:9': '16:9', zoom: 'Zoom' };
// When to use each, by what you see (forcing a shape on a picture that was right distorts it)
const SHAPE_HINTS = { auto: 'As the channel sends it', '4:3': 'For when people look too wide',
  '16:9': 'For when people look too thin', zoom: 'For black bars on all four sides; crops the edges' };
const shapeOf = key => (key && state.shapes[key]) || 'auto';

function applyShape(video, key) {
  const shape = shapeOf(key);
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
// A TV or streaming stick rather than a PC: Android TV, Fire TV, Chromecast, Tizen, webOS, Bravia, or
// anything without a mouse
const ON_A_TV = /Android|AFT|CrKey|SMART-TV|SmartTV|Tizen|Web0S|webOS|BRAVIA|GoogleTV/i.test(navigator.userAgent)
  || !window.matchMedia('(any-pointer: fine)').matches;
// Away from the TV's browser this long with something paused in it: close it
const AWAY_CLOSE_SECONDS = 30;
// Inside the TabloView TV app (tvapp/): it passes the remote's keys to this page, asks it about Back
// (window.tvBack), and keeps the TV awake while something plays
const APP = window.TabloViewApp || null;

const BACK_KEYS = ['Escape', 'Backspace', 'BrowserBack', 'GoBack'];
// Android's Back (4), browsers' Back (166), LG webOS (461), Samsung Tizen (10009)
const isBack = e => BACK_KEYS.includes(e.key) || [4, 8, 27, 166, 461, 10009].includes(e.keyCode);

// The app's Back button: do what Back does here, or say there's nothing to go back to (the app
// then closes, as Back on an app's first screen does): on Home, with the menu open
window.tvBack = () => {
  const home = (location.hash || '#/') === '#/' && !player.open && !dialogDone && inRail(document.activeElement);
  if (home) return false;
  onKey({ key: 'GoBack', keyCode: 4, target: document.body, preventDefault() {} });
  return true;
};

function onKey(e) {
  const k = e.key;
  // Typing the PIN: leave its keys alone, except moving off the box
  if (e.target.id === 'pinInput' && !['ArrowDown', 'ArrowUp', 'Enter'].includes(k)) return;

  if (dialogDone && isBack(e)) { e.preventDefault(); dialogDone(null); return; }

  if (player.open && $('#dialog').classList.contains('hidden')) {
    if (player.upNext && (k === 'Enter' || k === ' ')) { e.preventDefault(); player.playNext(); return; }
    if (player.inBreak && !player.controls && k === 'Enter') { e.preventDefault(); player.skipBreak(); return; }
    // The button row: arrows move along it, OK presses, Back/up/down put it away
    if (player.controls) {
      e.preventDefault();
      if (k === 'ArrowLeft' || k === 'ArrowRight') player.moveControl(k === 'ArrowLeft' ? -1 : 1);
      else if (k === 'Enter' || k === ' ') player.pressControl();
      else if (player.shapeMenu && (isBack(e) || k === 'ArrowUp' || k === 'ArrowDown')) player.showControls();
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
  // Back: from a show or a recording, to where it was opened from; on a page the menu opens, the
  // menu first, then Home. Back in Home's menu is left to the browser (leaving).
  if (!isBack(e)) return;
  const h = location.hash || '#/';
  if (!TOP_SCREENS.includes(h) && h !== '#/recordings') { e.preventDefault(); history.back(); return; }
  if (!inRail(cur)) { e.preventDefault(); focusRail(); return; }
  if (h !== '#/') { e.preventDefault(); history.back(); }
}

function onClick(e) {
  // A mouse in the player (TV view on a PC): the controls are buttons too
  const ctl = e.target.closest('[data-ctl]');
  if (ctl && player.controls) { player.controlIndex = Number(ctl.dataset.ctl); player.pressControl(); return; }
  if (player.open && !player.controls && e.target.closest('#player')) { player.showControls(); return; }
  // The logo opens or closes the menu with its names; a tap anywhere else closes it
  const rail = $('#rail');
  if (e.target.closest('.rail-brand')) { rail.classList.toggle('open'); return; }
  if (!e.target.closest('.rail .f')) rail.classList.remove('open');
  const el = e.target.closest('[data-go], [data-act], [data-choice]');
  if (!el) return;
  if (el.dataset.choice !== undefined && dialogDone) return dialogDone(Number(el.dataset.choice));
  if (el.dataset.go) {
    // A page picked in the menu with a tap or click: the menu closes (it stayed open, holding the focus,
    // until a tap elsewhere). With the remote, the page's first tile takes the focus once it's loaded
    if (el.classList.contains('nav') && e.detail > 0) { el.blur(); $('#rail').classList.remove('open'); }
    const home = (location.hash || '#/') === '#/';
    // Between the menu's pages, Back goes to Home rather than through each one
    if (el.classList.contains('nav') && !home) location.replace(el.dataset.go === '#/' ? '#/' : el.dataset.go);
    else location.hash = el.dataset.go;
    return;
  }
  const act = el.dataset.act;
  if (act === 'skip-break') { player.skipBreak(); return; }
  if (act === 'play-resume' || act === 'play-start') player.playEpisode(el.dataset.id, { from: act === 'play-resume' ? 'resume' : 'start' });
  else if (['watchlist', 'watched', 'protect', 'delete'].includes(act)) episodeAction(act, el.dataset.id);
  else if (act === 'tune') player.tune(el.dataset.id);
  else if (act === 'run') startRun(Number(el.dataset.from), el.dataset.how);
  else if (act === 'run-from') startRun(Number(el.dataset.from));
  else if (act === 'live-tab') { state.liveTab = el.dataset.tab; state.focus['#/live'] = el.dataset.key; showLive(); }
  else if (act === 'live-view') {
    try { localStorage.setItem('tv_live_view', el.dataset.view); } catch { /* this visit only */ }
    state.focus['#/live'] = el.dataset.key;
    showLive();
  }
  else if (act === 'g-air') guideAiring(el.dataset.ch, Number(el.dataset.i));
  else if (act === 'reload') location.reload();
  else if (act === 'upcoming') upcomingAction(Number(el.dataset.i));
  else if (act === 'season') {
    state.season[el.dataset.show] = Number(el.dataset.season);
    state.focus[location.hash] = el.dataset.key;
    renderShow(el.dataset.show);
  }
  else if (act === 'lib-opt') {
    const { opt, value } = el.dataset;
    try { localStorage.setItem(`tv_lib_${opt}`, value); } catch { /* this visit only */ }
    // Stay on the choice (the Not watched only switch changes its own value)
    state.focus['#/library'] = opt === 'unwatched' ? `lib-unwatched-${value === '1' ? '0' : '1'}` : el.dataset.key;
    showLibrary();
  }
  else if (act === 'app-address') APP.changeAddress();
  else if (act === 'pc-view') {
    try { localStorage.setItem('tv_view', 'pc'); } catch { /* the PC page opens anyway */ }
    location.href = '/';
  }
}

function tickClock() { $('#clock').textContent = fmt.time(Date.now()); }

function init() {
  // In the app, PC view can't be used (no pointer): its place changes which PC the app uses (as the
  // remote's Menu button does; not every remote has one)
  const pcView = document.querySelector('[data-act="pc-view"]');
  if (APP && pcView) { pcView.querySelector('span').textContent = 'PC address'; pcView.dataset.act = 'app-address'; }
  document.querySelectorAll('[data-icon]').forEach(i => { i.outerHTML = svg(i.dataset.icon); });
  // TV view is now this browser's view: the plain address opens it from here on (PC view undoes it)
  try { localStorage.setItem('tv_view', 'tv'); } catch { /* storage unavailable: /tv still works */ }
  document.addEventListener('keydown', onKey);
  document.addEventListener('click', onClick);
  // A pointer (TV Bro's or Silk's cursor mode) moves the highlight too
  document.addEventListener('mouseover', e => { const el = e.target.closest('.f'); if (el && el !== document.activeElement) el.focus({ preventScroll: true }); });
  // Moving the mouse over the picture brings up the controls
  let lastPointer = '';
  document.addEventListener('mousemove', e => {
    // Only a pointer that really moved: browsers also send moves when what's under a resting
    // pointer changes, which kept the controls and title up
    const at = `${e.screenX},${e.screenY}`;
    if (at === lastPointer) return;
    lastPointer = at;
    if (!player.open || !$('#dialog').classList.contains('hidden')) return;
    if (!player.controls) { player.showControls(); return; }
    player.wake();
    clearTimeout(player.controlsTimer);  // still in use: keep them up
    player.controlsTimer = setTimeout(() => player.hideControls(), 8000);
  });
  // A caption track appears once the stream's first captions arrive: show it if captions are on
  player.video().textTracks.addEventListener('addtrack', () => player.applyCaptions());
  window.addEventListener('hashchange', route);
  window.addEventListener('resize', () => player.open && applyShape(player.video(), player.s.shapeKey));
  // Leaving the page: save where the recording got to and free the stream (and its tuner)
  window.addEventListener('pagehide', () => player.close(true));
  // Leaving the TV's browser (the remote's Home button) while something plays: it kept playing unseen
  // and was still going on coming back. Pause at once, and close after a while away (place saved,
  // live TV's tuner freed). Not on a PC: switching to another window counts as leaving there too,
  // and TV view on a PC should keep playing like the PC view
  document.addEventListener('visibilitychange', () => {
    clearTimeout(player.awayTimer);
    if (!document.hidden || !player.open || !ON_A_TV) return;
    player.video().pause();
    player.awayTimer = setTimeout(() => { if (document.hidden && player.open) player.exit(); }, AWAY_CLOSE_SECONDS * 1000);
  });
  // While something plays (paused too), tell TabloView every minute, so it isn't closed as unused
  setInterval(() => {
    if (player.s.sessionId) api('/api/live/alive', { method: 'POST', body: JSON.stringify({ session_ids: [player.s.sessionId] }) }).catch(() => {});
  }, 60000);
  // TabloView updated on the PC: load the new page. The TV app keeps this page open for days (Home
  // and back only hides it), so it went on running the old version's player after an update
  let version = null;
  const checkVersion = async () => {
    if (player.open || document.hidden) return;
    try {
      const v = (await api('/api/system/info')).version;
      if (version && v && v !== version && !player.open) location.reload();
      version = version || v;
    } catch { /* PC asleep or restarting: try again later */ }
  };
  checkVersion();
  setInterval(checkVersion, 5 * 60000);
  document.addEventListener('visibilitychange', checkVersion);
  tickClock();
  setInterval(tickClock, 15000);
  api('/api/settings').then(s => { state.shapes = s.picture_shapes || {}; }).catch(() => {});
  if (location.hash === '#/play') location.replace('#/');
  route();
}

init();
