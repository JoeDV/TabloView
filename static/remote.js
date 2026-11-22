// TabloView Remote: a phone as the remote for an open TV view (the TV app, or /tv in a TV's browser).
// Buttons, a channel or a show go to TabloView (app/remote.py), and the TV view picks them up.
const HEADERS = { 'Content-Type': 'application/json', 'X-TabloView': '1' };
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(url, options = {}) {
  const res = await fetch(url, { headers: HEADERS, ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && data.code === 'pin_required') showPin();
    const detail = Array.isArray(data.detail) ? 'TabloView couldn’t do that' : data.detail;
    throw Object.assign(new Error(detail || `${res.status} ${res.statusText}`), { status: res.status, code: data.code });
  }
  return data;
}

const state = { screens: [], screen: null, channels: null, shows: null };
try { state.screen = localStorage.getItem('remote_screen'); } catch { /* this visit only */ }

function showPin() {
  $('#pinForm').classList.remove('hidden');
  $('#controls').classList.add('hidden');
  $('#empty').classList.add('hidden');
  $('#nowLabel').textContent = 'Sign in to use the remote';
}

$('#pinForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    await api('/api/lan/login', { method: 'POST', body: JSON.stringify({ pin: $('#pinInput').value.trim() }) });
    $('#pinForm').classList.add('hidden');
    refresh();
  } catch (err) { $('#pinError').textContent = err.message; }
});

// The screens open now, every couple of seconds; the one picked before stays picked while it's open
async function refresh() {
  if (!$('#pinForm').classList.contains('hidden')) return;
  try {
    state.screens = (await api('/api/remote/screens')).screens || [];
  } catch (err) {
    if (err.code === 'pin_not_set' || err.code === 'lan_off') return blocked(err.code);
    if (err.code !== 'pin_required') $('#nowLabel').textContent = `Can’t reach TabloView (${err.message})`;
    return;
  }
  $('#blocked').classList.add('hidden');
  if (!state.screens.some(s => s.id === state.screen)) state.screen = state.screens.length ? state.screens[0].id : null;
  draw();
}

// TabloView takes no other device until a PIN is set on the PC (or with network access off): say
// what to do there; this page tries again on its own every couple of seconds
function blocked(code) {
  $('#controls').classList.add('hidden');
  $('#empty').classList.add('hidden');
  $('#nowLabel').textContent = 'Not ready yet';
  $('#nowTitle').textContent = $('#nowSub').textContent = '';
  $('#blocked').innerHTML = code === 'pin_not_set'
    ? '<p><b>Set a PIN on the PC first.</b></p><p>On the PC running TabloView: Settings → Desktop &amp; network → PIN. Other devices, this phone included, need it once. This page carries on by itself once it’s set.</p>'
    : '<p><b>Network access is off on the PC.</b></p><p>On the PC running TabloView: Settings → Desktop &amp; network → turn on Allow other devices on my network.</p>';
  $('#blocked').classList.remove('hidden');
}

function draw() {
  const pick = $('#screenPick');
  const names = {};
  state.screens.forEach(s => { names[s.name] = (names[s.name] || 0) + 1; });
  const label = (s, i) => (names[s.name] > 1 ? `${s.name} ${i + 1}` : s.name);
  pick.innerHTML = state.screens.map((s, i) => `<option value="${esc(s.id)}" ${s.id === state.screen ? 'selected' : ''}>${esc(label(s, i))}</option>`).join('');
  pick.classList.toggle('hidden', state.screens.length < 2);
  const s = state.screens.find(x => x.id === state.screen);
  $('#controls').classList.toggle('hidden', !s);
  $('#empty').classList.toggle('hidden', !!s);
  if (!s) {
    $('#nowLabel').textContent = 'No TV screen open';
    $('#nowTitle').textContent = $('#nowSub').textContent = '';
    return;
  }
  const st = s.state || {};
  const live = st.kind === 'live';
  $('#nowLabel').textContent = `${state.screens.length > 1 ? '' : `${s.name} · `}${st.playing ? (live ? 'Watching live' : 'Playing') + (st.paused ? ', paused' : '') : 'Showing'}`;
  $('#nowTitle').textContent = st.dialog || st.playing || st.page || 'TabloView';
  $('#nowSub').textContent = st.dialog ? 'A question on the TV: use the arrows and OK' : st.sub || '';
  $('#skipBreak').classList.toggle('hidden', !st.in_break);
  $('#chRow').classList.toggle('hidden', !live);
}

$('#screenPick').addEventListener('change', e => {
  state.screen = e.target.value;
  try { localStorage.setItem('remote_screen', state.screen); } catch { /* this visit only */ }
  draw();
});

async function send(command, value = null) {
  if (!state.screen) return;
  if (navigator.vibrate) navigator.vibrate(12);
  try {
    await api('/api/remote/send', { method: 'POST', body: JSON.stringify({ screen: state.screen, command, value }) });
    setTimeout(refresh, 700);  // (what the TV shows now)
  } catch (err) {
    $('#nowSub').textContent = err.message;
    refresh();
  }
}

document.addEventListener('click', e => {
  const b = e.target.closest('[data-key], [data-cmd], [data-tune], [data-open]');
  if (!b) return;
  if (b.dataset.key) send('key', b.dataset.key);
  else if (b.dataset.cmd) send(b.dataset.cmd);
  else if (b.dataset.tune) { send('tune', b.dataset.tune); clearSearch(); }
  else if (b.dataset.open) { send('open', b.dataset.open); clearSearch(); }
});

// Search: channels by number, name or what's on now, and shows in the Library. Loaded on first use
async function loadSearch() {
  if (state.channels && state.shows) return;
  const [epg, shows] = await Promise.allSettled([api('/api/live/epg?hours=1'), api('/api/shows')]);
  const now = Date.now();
  state.channels = (epg.status === 'fulfilled' ? epg.value.channels || [] : []).filter(c => !c.hidden).map(c => {
    const on = (c.airings || []).find(a => { const t = new Date(a.air_datetime).getTime(); return t <= now && now < t + (a.duration || 0) * 1000; });
    return { id: c.channel_id, number: c.major > 0 ? `${c.major}.${c.minor}` : '', name: c.name || c.call_sign || '', call: c.call_sign || '', on: on ? on.title : '', kind: c.kind };
  });
  state.shows = shows.status === 'fulfilled' ? shows.value.shows || [] : [];
}

function clearSearch() {
  $('#search').value = '';
  $('#search').blur();
  $('#results').classList.add('hidden');
}

let searchTimer = null;
$('#search').addEventListener('focus', () => loadSearch().catch(() => {}));
$('#search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(runSearch, 150); });
$('#searchForm').addEventListener('submit', e => {
  e.preventDefault();
  runSearch().then(() => { const first = $('#results .result'); if (first) first.click(); });
});

async function runSearch() {
  const q = $('#search').value.trim().toLowerCase();
  const box = $('#results');
  if (!q) { box.classList.add('hidden'); return; }
  try { await loadSearch(); } catch { /* shows what's there */ }
  const words = q.split(/\s+/);
  const has = text => words.every(w => text.toLowerCase().includes(w));
  // A channel number first (7 or 7.1), then names and what's on
  const byNumber = (state.channels || []).filter(c => c.number && (c.number === q || c.number.split('.')[0] === q));
  const byName = (state.channels || []).filter(c => !byNumber.includes(c) && has(`${c.number} ${c.name} ${c.call} ${c.on}`));
  const channels = [...byNumber, ...byName].slice(0, 12);
  const shows = (state.shows || []).filter(s => has(s.title || '')).slice(0, 8);
  box.innerHTML = [
    ...channels.map(c => `<button class="result" data-tune="${esc(c.id)}"><span class="kind">${c.kind === 'extra' ? 'More' : 'Channel'}</span>
      <span class="what"><div class="name">${esc([c.number, c.name].filter(Boolean).join(' '))}</div><div class="meta">${esc(c.on ? `On now: ${c.on}` : c.call)}</div></span></button>`),
    ...shows.map(s => `<button class="result" data-open="#/show/${esc(encodeURIComponent(s.id))}"><span class="kind">Show</span>
      <span class="what"><div class="name">${esc(s.title)}</div><div class="meta">${s.episode_count === 1 ? '1 recording' : `${s.episode_count} recordings`}</div></span></button>`),
  ].join('') || '<div class="no-results">Nothing matches.</div>';
  box.classList.remove('hidden');
}

refresh();
setInterval(() => { if (!document.hidden) refresh(); }, 2000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
