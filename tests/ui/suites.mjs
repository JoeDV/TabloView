// Browser test suites. They work with whatever is on your Tablo (no show names are hard-coded) and
// skip checks that need data you don't have (e.g. an in-progress recording). All writes are faked
// by the fetch shim in lib.mjs; the only real requests are page loads and recording playback.
import fs from 'node:fs';
import path from 'node:path';
import { api, sleep, BASE } from './lib.mjs';

async function transcodeSessions() {
  const info = await api('/api/system/info');
  const dir = path.join(info.data_dir, 'transcode');
  return fs.existsSync(dir) ? fs.readdirSync(dir, { withFileTypes: true }).filter(d => d.isDirectory()).length : 0;
}

export const SUITES = {
  // Home → Customize: turn a section off and save (1.4.1 couldn't: the server refused every layout,
  // and the page showed [object Object]). The save is faked, but checked with the server first
  async homecustomize(b, t) {
    await b.open('#/');
    await b.waitFor(`document.querySelector('[data-action="home-customize"]')`, 20000);
    await b.ev(`document.querySelector('[data-action="home-customize"]').click()`);
    t.check('Customize opens with every section', await b.waitFor(`document.querySelectorAll('.hs-row').length === HOME_SECTIONS.length`, 10000));
    await b.ev(`(() => { const box = document.querySelector('.hs-row[data-id="onnow"] input'); box.checked = false; box.dispatchEvent(new Event('change', { bubbles: true })); })()`);
    await b.ev(`document.querySelector('.overlay [data-action="modal-ok"]').click()`);
    await sleep(1500);
    const saved = await b.ev(`(window.__writes || []).filter(w => w[1].startsWith('/api/settings')).map(w => JSON.parse(w[2]))`);
    t.check('Saving sends the layout, On now turned off', saved.length === 1 && saved[0].home_hidden.includes('onnow') && saved[0].home_order.length === await b.ev('HOME_SECTIONS.length'),
      JSON.stringify(saved).slice(0, 200));
    t.check('No error shown', !(await b.ev(`[...document.querySelectorAll('.toast')].some(x => /couldn|object Object/i.test(x.textContent))`)));
  },

  async pages(b, t) {
    await b.open('#/');
    for (const [hash, ready, label] of [
      ['#/', '.page-title', 'Home'],
      ['#/library', '#libGrid .media-card, #libGrid .empty', 'Library'],
      ['#/guide', '#guideGrid .media-card, #guideGrid .empty', 'Guide'],
      ['#/live', '.epg-cell, #epgScroll .empty', 'Live TV'],
      ['#/scheduled', '.sched-row, #schedList .empty', 'Scheduled (series)'],
      ['#/scheduled?view=upcoming', '.upcoming-row, #schedList .empty', 'Scheduled (upcoming)'],
      ['#/downloads', '#dlList .list, #dlList .empty', 'Downloads'],
      ['#/settings', '.set-card', 'Settings'],
      ['#/help', '.help section', 'Help'],
    ]) {
      t.check(`${label} page renders`, await b.go(hash, `document.querySelector(${JSON.stringify(ready)})`, 30000));
    }
    await b.ev(`location.hash = '#/device?tab=playback'`);
    t.check('An old Device link opens Settings', await b.waitFor(`location.hash === '#/settings?tab=playback' && document.querySelector('.page-title').textContent === 'Settings'`));
    await b.go('#/settings?tab=diagnostics', `document.querySelector('[data-action="version-history"]')`);
    t.check('Settings → About shows the app version', /TabloView \d+\.\d+\.\d+/.test(await b.ev(`document.querySelector('.set-content').textContent`)));
    t.check('Settings → About has backup and restore', await b.ev(`!!document.querySelector('[data-action="backup-save"]') && !!document.querySelector('[data-action="backup-restore"]')`));
    await b.go('#/settings?tab=commercials', `document.querySelector('[data-change="skip-commercials"]')`);
    t.check('Each section has its own place in the list', (await b.ev(`document.querySelectorAll('.set-nav-item').length`)) === 9
      && /Commercials/.test(await b.ev(`document.querySelector('.set-nav-item.active').textContent`)));
    // Settings search: the matching rows from every section, the rest hidden
    await b.ev(`(() => { const s = document.getElementById('settingsSearch'); s.value = 'pin'; s.dispatchEvent(new Event('input')); })()`);
    const pinRows = await b.ev(`[...document.querySelectorAll('.set-section .set-row')].filter(r => r.offsetParent).map(r => r.querySelector('.set-label').textContent.trim())`);
    t.check('Settings search finds the PIN, from another section', pinRows.includes('PIN') && pinRows.length < 6, pinRows.join(', '));
    await b.ev(`(() => { const s = document.getElementById('settingsSearch'); s.value = 'zzqx'; s.dispatchEvent(new Event('input')); })()`);
    t.check('Settings search says when nothing matches', await b.ev(`!document.querySelector('.set-none').classList.contains('hidden')`));
    await b.ev(`(() => { const s = document.getElementById('settingsSearch'); s.value = ''; s.dispatchEvent(new Event('input')); })()`);
    // The drive almost full: a notice across the top, hidden with × until it's fuller
    await b.ev(`save('space_dismissed', 0); showSpaceBanner({ connected: true, almost_full: 90, free_gb: 90, percent_used: 91, deletable: [{ title: 'Show A', count: 3, bytes: 5e9 }] })`);
    t.check('Almost-full notice shows with the shows to delete from', await b.ev(`!document.getElementById('spaceBanner').classList.contains('hidden') && /Show A/.test(document.getElementById('spaceBannerText').textContent)`));
    await b.ev(`document.querySelector('[data-action="space-dismiss"]').click(); showSpaceBanner({ connected: true, almost_full: 90, free_gb: 90, percent_used: 91 })`);
    const stillHidden = await b.ev(`document.getElementById('spaceBanner').classList.contains('hidden')`);
    await b.ev(`showSpaceBanner({ connected: true, almost_full: 95, free_gb: 40, percent_used: 96 })`);
    t.check('Hidden until 95%', stillHidden && await b.ev(`!document.getElementById('spaceBanner').classList.contains('hidden')`));
    await b.ev(`save('space_dismissed', 0); loadStorage()`);
    await b.go('#/help', `document.querySelector('#helpSearch')`);
    await b.ev(`(() => { const s = document.getElementById('helpSearch'); s.value = 'tailscale'; s.dispatchEvent(new Event('input')); })()`);
    const shown = await b.ev(`[...document.querySelectorAll('.help-page .set-nav-item:not(.hidden)')].length`);
    t.check('Help search narrows the topics', shown > 0 && shown < (await b.ev(`document.querySelectorAll('.help-page .set-nav-item').length`)), `${shown} topics`);
    await b.go('#/help?topic=help-faq', `document.querySelector('#help-faq .help-q')`);
    t.check('A Help link opens its topic, questions folded', /Questions/.test(await b.ev(`document.querySelector('.help h2').textContent`)) && !(await b.ev(`document.querySelector('.help-q').open`)));
  },

  async library(b, t) {
    await b.open('#/library');
    await b.waitFor(`document.querySelector('#libGrid .media-card')`);
    const shows = await api('/api/shows');
    const show = shows.shows.find(s => s.episode_count >= 2);
    if (!show) return t.skip('Show page bulk actions', 'needs a show with at least 2 recordings');
    await b.go(`#/show/${encodeURIComponent(show.id)}`, `document.querySelector('.ep-row')`);
    const before = await b.ev(`document.querySelectorAll('.ep-row').length`);
    t.check('Show page lists its episodes', before === show.episode_count, `${before} rows`);
    await b.ev(`(() => { const c = document.querySelectorAll('[data-change="ep-select"]'); [c[0], c[1]].forEach(x => { x.checked = true; x.dispatchEvent(new Event('change', { bubbles: true })); }); })()`);
    await sleep(300);
    t.check('Selecting 2 episodes shows the delete bar', (await b.ev(`document.getElementById('bulkCount').textContent`)) === '2 selected');
    await b.ev(`document.querySelector('[data-action="bulk-delete"]').click()`); await sleep(300);
    t.check('Bulk delete asks first', /Delete 2 recordings/.test(await b.ev(`(document.querySelector('.overlay .dialog-title') || {}).textContent || ''`)));
    await b.ev(`document.querySelector('[data-action="modal-ok"]').click()`); await sleep(800);
    t.check('Rows removed after (faked) delete', (await b.ev(`document.querySelectorAll('.ep-row').length`)) === before - 2);
    t.check('Delete request was intercepted, not sent', await b.ev(`window.__writes.some(w => w[1].includes('bulk_delete'))`));
    await b.ev(`document.querySelector('[data-action="ep-menu"]').click()`); await sleep(300);
    const menu = await b.ev(`[...document.querySelectorAll('.menu-item')].map(x => x.textContent.trim()).join('|')`);
    t.check('Episode menu has watched / VLC / export / delete', /watched/i.test(menu) && /VLC/.test(menu) && /Export/.test(menu) && /Delete/.test(menu), menu);
  },

  async guide(b, t) {
    await b.open('#/guide');
    await b.waitFor(`document.querySelector('#guideGrid .media-card')`, 30000);
    const path_ = await b.ev(`(() => { const x = document.querySelector('#guideGrid .rec-btn.off'); return x && x.dataset.path; })()`);
    if (!path_) return t.skip('Record menu', 'every show in view is already recording');
    await b.ev(`document.querySelector('#guideGrid .rec-btn.off').click()`); await sleep(300);
    t.check('Record menu opens', await b.ev(`!!document.querySelector('.menu')`));
    await b.ev(`[...document.querySelectorAll('.menu-item')].find(x => x.textContent.includes('New episodes only')).click()`); await sleep(600);
    t.check('Rule change was intercepted, not sent', await b.ev(`window.__writes.some(w => w[1].startsWith('/api/guide/series/schedule') && w[2].includes('"rule":"new"'))`));
    t.check('Card switches to Recording new', (await b.ev(`[...document.querySelectorAll('[data-rule-path]')].find(x => x.dataset.rulePath === ${JSON.stringify(path_)}).textContent.trim()`)) === 'Recording new');
    await b.ev(`document.querySelector('[data-change="guide-rule"]').value = 'scheduled'; document.querySelector('[data-change="guide-rule"]').dispatchEvent(new Event('change', { bubbles: true }))`);
    await sleep(2000);
    const sched = await api('/api/guide/shows?rule=scheduled&limit=500');
    t.check('Recording filter lists every series with a rule', (await b.ev(`document.querySelectorAll('#guideGrid .media-card').length`)) === sched.shows.length, `${sched.shows.length} series`);
  },

  async live(b, t) {
    await b.open('#/live');
    if (!await b.waitFor(`document.querySelector('.epg-cell')`, 40000)) return t.check('Live TV grid loads', false);
    t.check('Toolbar fits on one line', (await b.ev(`document.querySelector('.live-bar').offsetHeight`)) < 80);
    await b.ev(`document.querySelector('.epg-cell').click()`); await sleep(400);
    t.check('Program details dialog opens', await b.ev(`!!document.querySelector('.overlay .dialog-title')`));
    await b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))`); await sleep(300);
    t.check('Esc closes the dialog', await b.ev(`!document.querySelector('.overlay')`));
    // Simulated: 2 tuners held, a recording due soon
    await b.ev(`window.__fake['/api/live/tuners'] = { total: 4, in_use: 3, held: 2, recording: 1, streams_in_use: 0, streams_total: 4, tuners: [] };
      window.__fake['/api/live/tune_check'] = { total: 4, in_use: 3, held: 2, free_after_tuning: 0, needed: 1, warn: true, no_free_tuner: false, recordings_soon: [{ title: 'Test Show', start: new Date(Date.now() + 1800000).toISOString() }] }; checkTuners()`);
    await sleep(800);
    t.check('Tuner badge shows tuners in use and recording', (await b.ev(`document.getElementById('tunerText').textContent`)) === 'Tuners 3/4 · 1 recording');
    if (await b.ev(`!!document.querySelector('.epg-ch[data-kind="ota"]')`)) {
      await b.ev(`document.querySelector('.epg-ch[data-kind="ota"]').click()`); await sleep(800);
      t.check('Antenna channel warns before taking the last tuner', /Test Show will start recording/.test(await b.ev(`(document.querySelector('.overlay .dialog-text') || {}).textContent || ''`)));
      await b.ev(`document.querySelector('[data-action="modal-cancel"]').click()`); await sleep(400);
      t.check('Cancel means nothing is tuned', await b.ev(`document.getElementById('player').classList.contains('hidden') && !window.__writes.some(w => w[1].startsWith('/api/live/tune'))`));
    } else t.skip('Tuner warning', 'no antenna channels in the lineup');
  },

  async scheduled(b, t) {
    const up = await api('/api/guide/upcoming');
    await b.open('#/scheduled?view=upcoming');
    await b.waitFor(`document.querySelector('.upcoming-row, #schedList .empty')`, 30000);
    t.check('Upcoming lists every planned recording', (await b.ev(`document.querySelectorAll('.upcoming-row').length`)) === up.count, `${up.count} recordings`);
    t.check('Conflict banner matches the server', (await b.ev(`!!document.querySelector('.conflict-banner')`)) === up.conflicts.length > 0);
    if (up.count >= 2) {
      await b.ev(`window.__fake['/api/guide/upcoming'] = real => { const r = real.recordings.map((x, i) => i < 2 ? { ...x, conflict: true } : x);
        return { ...real, recordings: r, conflicts: [{ start: r[0].air_datetime, end: r[1].air_datetime, count: 5, tuners: 4, titles: [r[0].show_title, r[1].show_title], paths: [] }] }; }; route()`);
      await sleep(2000);
      t.check('Simulated conflict shows banner and tags', await b.ev(`!!document.querySelector('.conflict-banner') && document.querySelectorAll('.upcoming-row.conflict').length === 2`));
      await b.ev(`location.hash = '#/'`);
      await b.waitFor(`document.querySelector('.page-title')`); await sleep(2500);
      t.check('Home shows the conflict warning', await b.ev(`!!document.querySelector('.conflict-banner a[href*="upcoming"]')`));
    }
  },

  async playback(b, t) {
    const shows = (await api('/api/shows')).shows;
    if (!shows.length) return t.skip('Playback', 'no recordings');
    const eps = (await api(`/api/shows/episodes?show_id=${encodeURIComponent(shows[0].id)}`)).episodes;
    await b.open(`#/show/${encodeURIComponent(shows[0].id)}`);
    await b.waitFor(`document.querySelector('.ep-row')`);
    const before = await transcodeSessions();
    await b.ev(`player.playEpisode(${JSON.stringify(eps[0].id)}, 'start')`);
    const playing = await b.waitFor(`document.getElementById('video').currentTime > 2`, 45000);
    t.check('Recording plays in the browser', playing, await b.ev(`document.getElementById('playerStatus').textContent`));
    t.check('A transcode session is running', (await transcodeSessions()) === before + 1);
    await b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))`);
    let gone = false;
    for (let i = 0; i < 20 && !gone; i++) { await sleep(500); gone = (await transcodeSessions()) === before; }
    t.check('Closing the player ends the session', gone);
  },

  async controls(b, t) {
    const shows = (await api('/api/shows')).shows;
    if (!shows.length) return t.skip('Player controls', 'no recordings');
    const eps = (await api(`/api/shows/episodes?show_id=${encodeURIComponent(shows[0].id)}`)).episodes;
    const ep = eps.find(e => e.recording_state === 'finished' && e.status !== 'Watched') || eps[0];
    await b.open(`#/show/${encodeURIComponent(shows[0].id)}`);
    await b.waitFor(`document.querySelector('.ep-row')`);
    await b.ev(`player.playEpisode(${JSON.stringify(ep.id)}, 'start')`);
    t.check('Recording starts playing', await b.waitFor(`document.getElementById('video').currentTime > 4`, 45000));
    t.check('Player bar with controls is shown', await b.ev(`!document.getElementById('playerTimeline').classList.contains('hidden') && !!document.querySelector('[data-action="pb-fwd"]')`));
    const key = k => b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(k)}, bubbles: true }))`);
    await key(' '); await sleep(400);
    t.check('Space pauses', await b.ev(`document.getElementById('video').paused`));
    await key(' '); await sleep(600);
    t.check('Space plays again', await b.ev(`!document.getElementById('video').paused`));
    // Far enough in that 10 s back stays within what's already converted (no restart)
    await b.waitFor(`document.getElementById('video').currentTime > 14`, 30000);
    const before = await b.ev('player.position()');
    await key('ArrowLeft'); await sleep(800);
    const back = await b.ev('player.position()');
    t.check('← goes back 10 seconds', back <= before - 7 && back >= before - 13, `${before}s → ${back}s`);
    t.check('...and stops there until Play', await b.ev(`document.getElementById('video').paused && state.stream.held`));
    await key(' '); await b.waitFor(`!document.getElementById('video').paused`, 20000);
    await key('m'); await sleep(200);
    t.check('M mutes', await b.ev(`document.getElementById('video').muted`));
    await key('m');
    await key('>'); await sleep(200);
    t.check('> speeds up', (await b.ev(`document.getElementById('video').playbackRate`)) > 1);
    await key('<');
    await key('?'); await sleep(300);
    t.check('? shows the keyboard shortcuts', /Keyboard shortcuts/.test(await b.ev(`(document.querySelector('.overlay .dialog-title') || {}).textContent || ''`)));
    await b.ev(`closeModal(false)`);
    // Simulated stall: stop loading and jump to the end of what's buffered; the watchdog should restart
    // from the same point (spied, not sent)
    await b.ev(`window.__restart = null; player.__realPlay = player.playEpisode; player.playEpisode = (id, mode) => { window.__restart = mode; return Promise.resolve(); };
      state.stream.hls.stopLoad(); (() => { const v = document.getElementById('video'); v.currentTime = v.buffered.end(v.buffered.length - 1) - 1; })()`);
    const restarted = await b.waitFor(`window.__restart !== null`, 40000);
    t.check('A stalled stream restarts from where it stopped', restarted && Math.abs((await b.ev('window.__restart')) - (await b.ev('player.position()'))) < 5,
      restarted ? `restart at ${await b.ev('window.__restart')}s` : `no restart: ${await b.ev(`(() => { const v = $('#video'), s = state.stream; return JSON.stringify({ t: v.currentTime, paused: v.paused, seeking: v.seeking, ended: v.ended, stallSince: s.stallSince, msg: ($('#playerMsg') || {}).textContent, overlay: !!openOverlay }); })()`)}`);
    await b.ev(`player.playEpisode = player.__realPlay; player.close()`);
    await sleep(1500);
  },

  async conflicts(b, t) {
    const soon = h => new Date(Date.now() + h * 3600000).toISOString().replace(/\.\d+Z$/, 'Z');
    await b.open('#/');
    await b.ev(`window.__fake['/api/guide/conflicts'] = { tuners: 2, conflicts: [{ start: ${JSON.stringify(soon(3))}, end: ${JSON.stringify(soon(4))}, count: 3, tuners: 2, titles: ['A', 'B', 'C'],
      recordings: [{ path: '/guide/series/episodes/1', show_title: 'Show A', episode_title: 'Pilot', season_number: 1, episode_number: 1, air_datetime: ${JSON.stringify(soon(3))}, channel_call_sign: 'WAAA',
                     alternatives: [{ path: '/guide/series/episodes/2', air_datetime: ${JSON.stringify(soon(30))}, channel_call_sign: 'WBBB', resolves: true }] },
                   { path: '/guide/series/episodes/3', show_title: 'Show B', episode_title: '', season_number: 0, episode_number: 0, air_datetime: ${JSON.stringify(soon(3))}, channel_call_sign: 'WCCC', alternatives: [] }] }] };
      fixConflicts()`);
    await sleep(600);
    t.check('Conflict helper lists alternatives', /Record this one instead/.test(await b.ev(`document.querySelector('.overlay').textContent`)));
    t.check('A show without reruns offers Don’t record', !!(await b.ev(`document.querySelector('[data-action="skip-conflict"]')`)));
    await b.ev(`document.querySelector('[data-action="swap-recording"]').click()`); await sleep(800);
    t.check('Moving a recording was intercepted, not sent', await b.ev(`window.__writes.some(w => w[1].startsWith('/api/guide/conflicts/swap') && w[2].includes('episodes/2'))`),
      await b.ev(`JSON.stringify(window.__writes).slice(0, 200)`));
    await b.ev(`closeModal(false)`);
  },

  async rules(b, t) {
    const shows = await api('/api/shows');
    const show = shows.shows.find(s => s.episode_count >= 3 && (s.path || '').startsWith('/recordings/series/'));
    if (!show) return t.skip('Keep and cleanup rules', 'needs a recorded series with at least 3 recordings');
    await b.open(`#/show/${encodeURIComponent(show.id)}`);
    await b.waitFor(`document.querySelector('.ep-row')`);
    t.check('Show page has Keep and Delete watched rules', await b.ev(`!!document.querySelector('[data-change="show-keep"]') && !!document.querySelector('[data-change="show-cleanup"]')`));
    await b.ev(`(() => { const s = document.querySelector('[data-change="show-keep"]'); s.value = '1'; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
    await sleep(400);
    t.check('Keep newest 1 warns how many the Tablo will delete', /Keep only the newest 1 recording/.test(await b.ev(`(document.querySelector('.overlay .dialog-title') || {}).textContent || ''`))
      && new RegExp(`now \\(${show.episode_count - 1} recordings\\)`).test(await b.ev(`document.querySelector('.overlay .dialog-text').textContent`)));
    await b.ev(`document.querySelector('[data-action="modal-cancel"]').click()`); await sleep(400);
    t.check('Cancel puts the choice back and sends nothing', await b.ev(`document.querySelector('[data-change="show-keep"]').value === '${show.keep || ''}' && !window.__writes.some(w => w[1].includes('/keep'))`));
    await b.ev(`(() => { const s = document.querySelector('[data-change="show-cleanup"]'); s.value = '7'; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
    await sleep(400);
    await b.ev(`document.querySelector('[data-action="modal-ok"]').click()`); await sleep(600);
    t.check('Cleanup rule saved (intercepted)', await b.ev(`window.__writes.some(w => w[1].startsWith('/api/shows/cleanup') && w[2].includes('"days":7'))`));
    await b.ev(`document.querySelector('[data-action="ep-menu"]').click()`); await sleep(300);
    await b.ev(`[...document.querySelectorAll('.menu-item')].find(x => /Protect from deletion|Unprotect/.test(x.textContent)).click()`); await sleep(600);
    t.check('Protect sent to the episode (intercepted)', await b.ev(`window.__writes.some(w => /\\/api\\/episodes\\/.+\\/protected/.test(w[1]))`));
  },

  async channels(b, t) {
    await b.open('#/live');
    if (!await b.waitFor(`document.querySelector('.epg-cell')`, 40000)) return t.check('Live TV grid loads', false);
    // Pretend a channel is playing (nothing is tuned), with a tuner warning so a channel change stops at the dialog
    await b.ev(`window.__fake['/api/live/tune_check'] = { total: 4, in_use: 4, held: 0, free_after_tuning: 0, needed: 0, warn: false, no_free_tuner: true, recordings_soon: [] };
      (() => { const c = state.epg.channels.filter(epgFilter)[0]; state.stream.channelId = c.channel_id; player.open('Live · test'); player.showTimeline(true); })()`);
    t.check('Live player shows the Channels button', await b.ev(`!document.getElementById('pbChannels').classList.contains('hidden')`));
    await b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'c' }))`); await sleep(600);
    const rows = await b.ev(`document.querySelectorAll('#chanPanel .chan-row').length`);
    t.check('C opens the channel list with what’s on', rows > 0 && await b.ev(`!!document.querySelector('#chanPanel .chan-row.current') && !!document.querySelector('#chanPanel .chan-now')`), `${rows} channels`);
    await b.ev(`player.toggleChannels(false)`); await sleep(300);  // (with the list open, Page Down moves in it)
    await b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'PageDown' }))`); await sleep(200);
    await b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'PageDown' }))`); await sleep(300);
    t.check('Page Down shows where it’s heading', await b.ev(`!document.getElementById('chanOsd').classList.contains('hidden')`));
    await sleep(1600);
    const target = await b.ev(`(() => { const l = state.epg.channels.filter(epgFilter); return l[2 % l.length].channel_id; })()`);
    const dialog = await b.ev(`(document.querySelector('.overlay .dialog-title') || {}).textContent || ''`);
    const kind = await b.ev(`state.epg.channels.find(c => c.channel_id === ${JSON.stringify(target)}).kind`);
    if (kind === 'ota') {
      t.check('Two presses then a pause tunes once, two channels on (tuner check first)', dialog === 'Not enough tuners');
      await b.ev(`document.querySelector('[data-action="modal-cancel"]').click()`); await sleep(300);
    } else t.skip('Tuner check on channel change', 'the channel two down isn’t an antenna channel');
    t.check('Nothing was tuned', !await b.ev(`window.__writes.some(w => w[1].startsWith('/api/live/tune'))`) || kind !== 'ota');
    await b.ev(`state.stream.channelId = null; player.close()`);
  },

  async guideload(b, t) {
    await b.open('#/guide');
    await b.ev(`window.__fake['/api/library/status'] = real => ({ ...real, guide_progress: { first: true, step: 'airings', done: 1200, total: 4300, minutes_left: 7, waiting_seconds: null } }); pollStatus()`);
    await sleep(800);
    const text = await b.ev(`document.getElementById('guideBanner').textContent.replace(/\\s+/g, ' ')`);
    t.check('First guide load shows a banner with progress and time left', await b.ev(`!document.getElementById('guideBanner').classList.contains('hidden')`)
      && /first time/.test(text) && /1,200 of 4,300/.test(text) && /about 7 minutes left/.test(text), text.slice(0, 160));
    await b.ev(`window.__fake['/api/library/status'] = real => ({ ...real, tablo_unreachable: true, guide_progress: { first: true, step: 'airings', done: 1300, total: 4300, minutes_left: 7, waiting_seconds: 70 } }); pollStatus()`);
    await sleep(800);
    t.check('While it waits out the Tablo’s break it says so, instead of the not-responding warning',
      /short break/.test(await b.ev(`document.getElementById('guideBannerText').textContent`)) && await b.ev(`document.getElementById('reachBanner').classList.contains('hidden')`));
    await b.ev(`window.__fake['/api/library/status'] = real => ({ ...real, guide_progress: null }); pollStatus()`);
    await sleep(800);
    t.check('The banner goes away when the guide is loaded', await b.ev(`document.getElementById('guideBanner').classList.contains('hidden')`));
  },

  async sleep(b, t) {
    await b.open('#/');
    // The player's controls without a stream (nothing is played or tuned)
    await b.ev(`state.stream.episodeId = 'test'; state.stream.duration = 1800; state.stream.programEnd = 1800; player.open('Test'); player.showTimeline(true)`);
    await b.ev(`document.getElementById('pbSleep').click()`); await sleep(300);
    const items = await b.ev(`[...document.querySelectorAll('.menu-item')].map(x => x.textContent.trim()).join('|')`);
    t.check('Sleep timer menu offers minutes and end of show', /15 minutes/.test(items) && /End of this show/.test(items), items);
    await b.ev(`[...document.querySelectorAll('.menu-item')].find(x => /30 minutes/.test(x.textContent)).click()`); await sleep(300);
    t.check('The button shows the time left', (await b.ev(`document.getElementById('pbSleepLeft').textContent`)) === '30m');
    await b.ev(`state.sleep.until = Date.now() + 1500`); await sleep(3000);
    t.check('When it runs out the player closes', await b.ev(`document.getElementById('player').classList.contains('hidden') && !state.sleep`));
    t.check('…and says why', /Sleep timer/.test(await b.ev(`document.getElementById('toasts').textContent`)));
    await b.ev(`player.open('Test'); player.showTimeline(true); const was = state.captions; document.getElementById('pbCC').click(); window.__cc = [was, state.captions, document.getElementById('pbCC').classList.contains('on')]; player.toggleCaptions()`);
    const [was, now, on] = await b.ev('window.__cc');
    t.check('CC button turns captions on and off', now === !was && on === now);
    await b.ev(`state.stream.episodeId = null`);
  },

  async exports(b, t) {
    const shows = await api('/api/shows');
    const show = shows.shows.find(s => s.episode_count >= 2);
    if (!show) return t.skip('Export several', 'needs a show with at least 2 recordings');
    await b.open(`#/show/${encodeURIComponent(show.id)}`);
    await b.waitFor(`document.querySelector('.ep-row')`);
    await b.ev(`(() => { const c = document.querySelectorAll('[data-change="ep-select"]'); [c[0], c[1]].forEach(x => { x.checked = true; x.dispatchEvent(new Event('change', { bubbles: true })); }); })()`);
    await sleep(300);
    await b.ev(`document.querySelector('[data-action="bulk-export"]').click()`); await sleep(600);
    t.check('Export MP4 on 2 selected episodes queues both (intercepted)', await b.ev(`window.__writes.some(w => w[1] === '/api/episodes/export_batch' && JSON.parse(w[2]).episode_ids.length === 2)`));
    await b.go('#/settings?tab=storage', `document.querySelector('[data-change="export-format"]')`);
    t.check('Settings page has the export format setting', (await b.ev(`document.querySelector('[data-change="export-format"]').options.length`)) === 2);
  },

  async rerecord(b, t) {
    const shows = (await api('/api/shows')).shows;
    const show = shows.find(s => s.incomplete_count > 0);
    if (!show) return t.skip('Record again', 'no failed or partial recordings');
    await b.open(`#/show/${encodeURIComponent(show.id)}`);
    await b.waitFor(`document.querySelector('[data-action="rerecord"]')`);
    const soon = new Date(Date.now() + 86400000).toISOString();
    await b.ev(`window.__fake['/api/episodes/'] = { airings: [{ path: '/guide/series/episodes/123', air_datetime: '${soon}', channel_network: 'NBC', channel_call_sign: 'WTHR', schedule_state: 'none' }] };
      document.querySelector('[data-action="rerecord"]').click()`);
    await sleep(800);
    t.check('Record again lists the rerun', /Record this one/.test(await b.ev(`(document.querySelector('.overlay') || {}).textContent || ''`)));
    await b.ev(`document.querySelector('[data-action="rerecord-pick"]').click()`); await sleep(600);
    t.check('Choosing it schedules that airing (intercepted)', await b.ev(`window.__writes.some(w => w[1] === '/api/guide/episodes/schedule' && w[2].includes('episodes/123'))`));
    await b.ev(`closeModal(false)`);
    await b.go('#/settings', `document.querySelector('[data-change="rerecord-failed"]')`);
    t.check('Settings page has the Record failed recordings again switch', true);
  },

  async commercials(b, t) {
    const shows = (await api('/api/shows')).shows;
    if (!shows.length) return t.skip('Skip commercials', 'no recordings');
    await b.open(`#/show/${encodeURIComponent(shows[0].id)}`);
    await b.waitFor(`document.querySelector('[data-change="show-commercials"]')`);
    await b.ev(`(() => { const x = document.querySelector('[data-change="show-commercials"]'); x.checked = !x.checked; x.dispatchEvent(new Event('change', { bubbles: true })); })()`);
    await sleep(500);
    t.check('Skip commercials switch saves for the show (intercepted)', await b.ev(`window.__writes.some(w => w[1].startsWith('/api/shows/commercials'))`));
    const menuEp = await b.ev(`(() => { const e = state.episodes.find(e => e.recording_state === 'finished' && !['done', 'analyzing', 'queued'].includes(e.commercials)); return e && e.id; })()`);
    if (menuEp) {
      await b.ev(`document.querySelector('[data-action="ep-menu"][data-id="${menuEp}"]').click()`); await sleep(300);
      await b.ev(`[...document.querySelectorAll('.menu-item')].find(x => /Find commercials/.test(x.textContent)).click()`); await sleep(500);
      t.check('Find commercials queues just that recording (intercepted)', await b.ev(`window.__writes.some(w => w[1] === '/api/episodes/${menuEp}/find_commercials')`));
    } else t.skip('Find commercials for one recording', 'every recording is already done or queued');
    await b.ev(`window.__fake['/api/library/status'] = real => ({ ...real, commercials: { state: 'running', episode_id: 'x', title: 'Show S1E2', percent: 42, minutes_left: 5, waiting: 0 } }); pollStatus()`);
    await sleep(600);
    t.check('Sidebar shows the commercial finder’s progress', /Finding commercials · 42%/.test(await b.ev(`$('#adText').textContent`)) && await b.ev(`!$('#adLine').classList.contains('hidden')`));
    await b.ev(`delete window.__fake['/api/library/status']; pollStatus()`);
    // The player with a 30-minute recording and one break at 5:00-7:00 (nothing is played)
    await b.ev(`window.__seek = null; player.__realPlay = player.playEpisode; player.playEpisode = (id, mode) => { window.__seek = mode; return Promise.resolve(); };
      Object.assign(state.stream, { episodeId: 'test', duration: 1800, offset: 0, breaks: [{ start: 300, end: 420 }], skippedBreaks: new Set(), autoSkip: false });
      player.open('Test'); player.showTimeline(true); player.drawBreaks(); player.checkBreak(310)`);
    t.check('The break is marked on the timeline', (await b.ev(`document.querySelectorAll('#tlBreaks span').length`)) === 1);
    t.check('In a break, a Skip break button shows', await b.ev(`!document.getElementById('skipBreak').classList.contains('hidden')`));
    await b.ev(`document.getElementById('skipBreak').click()`); await sleep(300);
    t.check('Skip break jumps to the end of the break', (await b.ev('window.__seek')) === 420);
    await b.ev(`Object.defineProperty(player.video(), 'paused', { configurable: true, get: () => false }); state.stream.autoSkip = true; player.checkBreak(305); delete player.video().paused`); await sleep(300);
    t.check('With auto-skip on it jumps by itself', (await b.ev('window.__seek')) === 420 && /Skipped/.test(await b.ev(`document.getElementById('toasts').textContent`)));
    await b.ev(`player.playEpisode = player.__realPlay; state.stream.episodeId = null; player.close()`);
  },

  async pin(b, t) {
    await b.open('#/settings');
    // Set PIN dialog (on the PC): rejects a 3-digit PIN, saves a 4-digit one (intercepted)
    await b.ev(`void ACTIONS['set-pin']()`); await sleep(400);
    await b.ev(`document.getElementById('newPin').value = '123'; document.getElementById('savePin').click()`); await sleep(300);
    t.check('Set PIN rejects fewer than 4 digits', /4 to 6 digits/.test(await b.ev(`document.getElementById('newPinError').textContent`)));
    await b.ev(`document.getElementById('newPin').value = '2468'; document.getElementById('savePin').click()`); await sleep(500);
    t.check('Set PIN saves it (intercepted)', await b.ev(`window.__writes.some(w => w[1] === '/api/lan/pin' && w[2].includes('2468'))`));
    // What another device sees
    await b.ev(`askForPin('pin_required')`); await sleep(300);
    t.check('Another device gets a PIN screen', await b.ev(`!!document.getElementById('pinInput') && /Enter the PIN/.test(document.querySelector('.pin-box').textContent)`));
  },

  async storeupdate(b, t) {
    await b.open('#/');
    await sleep(2000);  // let the page's own update check finish first
    await b.ev(`window.__fake['/api/system/update'] = { current: '1.1.6', latest: '1.1.7', update_available: true, store: true, enabled: true, download_url: 'ms-windows-store://pdp/?productid=9NCWVSC7KX2N', notes: null, error: null }; checkForUpdate(true)`);
    await sleep(600);
    t.check('Store copy shows Update available, linking to the Store',
      await b.ev(`!$('#updateNotice').classList.contains('hidden') && $('#updateNotice').href.startsWith('ms-windows-store:') && /1\\.1\\.7/.test($('#updateNoticeText').textContent)`));
    await b.ev(`window.__fake['/api/system/update'] = { current: '1.1.7', latest: null, update_available: false, store: true, enabled: true, download_url: 'ms-windows-store://pdp/?productid=9NCWVSC7KX2N', error: null }; void checkForUpdate(true)`);
    await sleep(800);
    await b.go('#/settings?tab=diagnostics', `document.querySelector('[data-action="check-update"]')`);
    t.check('Settings → About offers Check now and Open in the Store', /Open in the Store/.test(await b.ev(`document.getElementById('view').textContent`)));
  },

  async returning(b, t) {
    await b.open('#/guide');
    await b.waitFor(`state.guideCache && state.guideCache.size > 0`, 30000);
    // Any guide show, presented as one you used to record that's coming back
    await b.ev(`(() => { const g = [...state.guideCache.values()][0]; window.__fake['/api/guide/returning'] = { shows: [{ ...g, schedule_rule: 'none', premiere_at: new Date(Date.now() + 86400000).toISOString(), premiere_season: 5 }] }; })(); location.hash = '#/'`);
    await b.waitFor(`document.getElementById('rowBack')`, 30000);
    t.check('Home shows Back for a new season with a Record button', await b.ev(`!!document.querySelector('#rowBack .rec-btn, #rowBack [data-action]')`));
  },

    // Uses an antenna tuner for about a minute: runs only with TABLOVIEW_ALLOW_TUNE=1
  async dual(b, t) {
    if (!process.env.TABLOVIEW_ALLOW_TUNE) return t.skip('Two channels at once', 'set TABLOVIEW_ALLOW_TUNE=1 to tune for real');
    const shows = (await api('/api/shows')).shows;
    const eps = (await api(`/api/shows/episodes?show_id=${encodeURIComponent(shows[0].id)}`)).episodes;
    const ep = eps.find(e => e.recording_state === 'finished') || eps[0];
    await b.open(`#/show/${encodeURIComponent(shows[0].id)}`);
    await b.waitFor(`document.querySelector('.ep-row')`);
    await b.ev(`player.playEpisode(${JSON.stringify(ep.id)}, 'start')`);
    await b.waitFor(`$('#video').currentTime > 3`, 60000);
    await b.ev(`$('#pbDual').click()`);
    await b.waitFor(`document.querySelector('#chanPanel .chan-row')`, 30000);
    t.check('The channel list asks for a second channel', /second channel/.test(await b.ev(`document.querySelector('.chan-head span').textContent`)));
    await b.ev(`[...document.querySelectorAll('#chanPanel .chan-row')].find(r => r.dataset.kind === 'ota').click()`);
    t.check('A live channel plays alongside the recording', await b.waitFor(`dual.on && $('#video2').currentTime > 3 && !$('#video').paused`, 60000));
    await b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab' }))`); await sleep(500);
    t.check('Tab moves the sound to the other channel', await b.ev(`dual.active === 'second' && $('#video').__audio.gain.gain.value === 0 && $('#video2').__audio.gain.gain.value === 1`));
    await b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'v' }))`); await sleep(300);
    t.check('V changes the layout', await b.ev(`player.el().classList.contains('dual-pip')`));
    // Each picture's CC is its own; the player's CC is for the channel you're hearing (the second, now)
    const cc2 = await b.ev(`state.captions2`), cc1 = await b.ev(`state.captions`);
    const shownSecond = `(() => { const t = captionTrack($('#video2')); return t ? t.mode === 'showing' : null; })()`;
    await b.ev(`document.querySelector('#paneSecond .pane-cc').click()`); await sleep(300);
    t.check("The second picture's CC turns its captions over", await b.ev(`state.captions2 === ${!cc2} && state.captions === ${cc1}`)
      && [null, !cc2].includes(await b.ev(shownSecond)) && (await b.ev(`$('#paneSecond .pane-cc').classList.contains('on')`)) === !cc2);
    t.check("The player's CC shows the heard channel's setting", (await b.ev(`$('#pbCC').classList.contains('on')`)) === !cc2);
    await b.ev(`$('#pbCC').click()`); await sleep(300);
    t.check("The player's CC changes the channel you're hearing", await b.ev(`state.captions2 === ${cc2} && state.captions === ${cc1}`));
    await b.ev(`document.querySelector('#paneMain .pane-cc').click()`); await sleep(300);
    t.check("The first picture's CC leaves the second alone", await b.ev(`state.captions === ${!cc1} && state.captions2 === ${cc2}`));
    await b.ev(`player.toggleCaptions('main')`); await sleep(300);
    await b.ev(`dual.close('second')`); await sleep(1000);
    t.check('Closing the live channel leaves the recording playing with its sound', await b.ev(`!dual.on && !$('#video').paused && $('#video').__audio.gain.gain.value === 1`));
  },

  // Guide → For you: shows to try, from the series being recorded, with why; premieres first
  async foryou(b, t) {
    await b.send('Page.navigate', { url: `${BASE}/#/guide` });
    await b.waitFor(`!!document.querySelector('[data-action="guide-highlight"][data-value="foryou"]')`, 20000);
    await b.ev(`document.querySelector('[data-action="guide-highlight"][data-value="foryou"]').click()`);
    const res = await api('/api/guide/recommendations');
    if (!res.recorded) return t.skip('Guide: For you', 'nothing set to record');
    t.check('Guide: For you lists shows, each saying why', await b.waitFor(`document.querySelectorAll('#guideGrid .media-card .media-why').length > 0`, 120000)
      && await b.ev(`document.querySelectorAll('#guideGrid .media-card').length === document.querySelectorAll('#guideGrid .media-why').length`));
    t.check('Guide: For you hides the TV shows / Movies / Sports chips', await b.ev(`$('#guideTypes').classList.contains('hidden')`));
    t.check('Guide: For you says how they were picked', await b.ev(`/(Picked by Claude|Matched by genre)/.test($('#guideGrid').textContent)`));
    const premiering = (res.shows || []).filter(s => s.premiere && ['series', 'season'].includes(s.premiere.kind));
    if (premiering.length) {
      t.check('Guide: For you puts premieres first, under Premiering soon', await b.ev(`(() => {
        const head = [...document.querySelectorAll('#guideGrid .section-title')].map(h => h.textContent);
        const first = document.querySelector('#guideGrid .media-card .media-title').textContent;
        return head[0] === 'Premiering soon' && first === ${JSON.stringify(premiering[0].title)}
          && /premiere/i.test(document.querySelector('#guideGrid .media-card .art-badge').textContent);
      })()`));
    }
    t.check('Guide: none of them is already recorded', !(res.shows || []).some(s => ['new', 'all'].includes(s.schedule_rule)));
    await b.ev(`document.querySelector('[data-action="guide-highlight"][data-value=""]').click()`);
    t.check('Guide: Everything brings the chips back', await b.waitFor(`!$('#guideTypes').classList.contains('hidden')`, 10000));
  },

  // Live TV with a provider's playlist of 386,496 channels (a forum user's: 1.3.7 hung the page). The
  // guide gets the favorites only, and More asks for 200 at a time, searched and grouped on the server
  async bigplaylist(b, t) {
    await b.open('#/');
    await b.ev(`(() => {
      const groups = Array.from({ length: 12000 }, (_, i) => ({ name: 'US| GROUP ' + i, count: 32, hidden: i === 5 }));
      const ch = (i, g) => ({ channel_id: 'x-' + String(i).padStart(10, '0'), identifier: 'x-' + i, call_sign: 'Channel ' + i, major: 0, minor: 0,
        number: '', network: g, kind: 'extra', name: 'Channel ' + i, logo_url: null, resolution: 'HD', can_record: false,
        extra_key: 'k' + i, favorite: i === 7, hidden: false, group_hidden: false, categories: [],
        airings: [{ path: '/channel/x/live', title: 'Channel ' + i, show_title: 'Channel ' + i, episode_title: 'Live',
          air_datetime: new Date(Date.now() - 1800000).toISOString(), duration: 6 * 3600, qualifiers: [] }] });
      window.__gets = [];
      const f = window.fetch;
      window.fetch = (u, o) => { if (!o || !o.method || o.method === 'GET') window.__gets.push(String(u)); return f(u, o); };
      window.__fake['/api/live/epg'] = real => ({ ...real, channels: [...real.channels.filter(c => c.kind !== 'extra'), ch(7, 'US| GROUP 0')], extra_left_out: 386495 });
      window.__fake['/api/live/extra/rows'] = { rows: Array.from({ length: 200 }, (_, i) => ch(i, 'US| GROUP 0')), total: 386496, hidden: 0, groups };
    })()`);
    await b.go('#/live', `document.querySelector('.epg-cell')`, 30000);
    t.check('Live TV opens on Antenna without the playlist', await b.ev(`state.epg.channels.filter(c => c.kind === 'extra').length === 1`));
    t.check('More is offered for a playlist this big', await b.ev(`!!document.querySelector('[data-action="epg-cat"][data-value="extra"]')`));
    const t0 = Date.now();
    await b.ev(`document.querySelector('[data-action="epg-cat"][data-value="extra"]').click()`);
    const drawn = await b.waitFor(`document.querySelectorAll('#epgScroll .epg-row').length === 200`, 20000);
    t.check(`More draws a page of 200 channels (${Date.now() - t0} ms)`, drawn && Date.now() - t0 < 5000);
    t.check('More says how many and to search', await b.ev(`/Showing 200 of 386,496 channels: search to find one/.test($('#epgScroll').textContent)`));
    t.check('More offers the playlist’s groups, hidden ones apart', await b.ev(`document.querySelectorAll('[data-change="extra-group"] option').length === 12001
      && document.querySelectorAll('[data-change="extra-group"] optgroup option').length === 1`));
    await b.ev(`document.querySelector('[data-action="extra-more"]').click()`);
    t.check('Show more asks for the next 200', await b.waitFor(`window.__gets.some(u => u.includes('/api/live/extra/rows') && u.includes('offset=200'))`, 10000)
      && await b.waitFor(`document.querySelectorAll('#epgScroll .epg-row').length === 400`, 10000));
    await b.ev(`(() => { const i = document.querySelector('[data-input="epg-q"]'); i.value = 'ESPN'; i.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    t.check('Search asks the server', await b.waitFor(`window.__gets.some(u => u.includes('/api/live/extra/rows') && u.includes('q=espn') && u.includes('offset=0'))`, 10000));
    await b.ev(`(() => { const i = document.querySelector('[data-input="epg-q"]'); i.value = ''; i.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await b.waitFor(`document.querySelector('[data-change="extra-group"]')`, 10000);
    await b.ev(`(() => { const s = document.querySelector('[data-change="extra-group"]'); s.value = 'US| GROUP 3'; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
    t.check('Picking a group asks for that group', await b.waitFor(`window.__gets.some(u => u.includes('group=US%7C%20GROUP%203'))`, 10000));
    t.check('A picked group can be hidden', await b.waitFor(`/Hide this group/.test(document.querySelector('[data-action="extra-group-hide"]')?.textContent || '')`, 10000));
    await b.ev(`document.querySelector('[data-action="epg-cat"][data-value="ota"]').click()`);
  },

  // TV view → Live TV → More: the playlist's groups first, then a group's channels (a big playlist's
  // from the server), and ‹ Groups back. Nothing is tuned
  async tvgroups(b, t) {
    await b.send('Page.navigate', { url: `${BASE}/tv#/live` });
    await b.waitFor(`typeof showLive === 'function' && state.live`, 30000);
    if (!(await b.ev(`state.live.channels.some(c => c.kind === 'extra') || !!state.live.extra_left_out`))) return t.skip('TV: playlist groups', 'no playlist');
    await b.ev(`document.querySelector('[data-act="live-tab"][data-tab="extra"]').click()`);
    const many = await b.waitFor(`document.querySelectorAll('[data-act="tv-group"]').length > 1`, 20000);
    if (!many) return t.skip('TV: playlist groups', 'the playlist has one group');
    t.check('TV: More lists the playlist’s groups', true);
    const name = await b.ev(`[...document.querySelectorAll('[data-act="tv-group"]')].find(x => !x.dataset.group.startsWith('\\u0001')).dataset.group`);
    await b.ev(`[...document.querySelectorAll('[data-act="tv-group"]')].find(x => x.dataset.group === ${JSON.stringify(name)}).click()`);
    t.check('TV: picking a group lists its channels, and nothing else', await b.waitFor(`document.querySelectorAll('[data-act="tune"]').length > 0`, 20000)
      && await b.ev(`liveChannels().every(c => c.network === ${JSON.stringify(name)}) && !document.querySelector('[data-act="tv-group"]')`));
    t.check('TV: a group’s channel can be found to tune', await b.ev(`!!allChannels().find(c => c.channel_id === document.querySelector('[data-act="tune"]').dataset.id)`));
    await b.ev(`document.querySelector('[data-act="tv-groups"]').click()`);
    t.check('TV: ‹ Groups goes back to the groups', await b.waitFor(`document.querySelectorAll('[data-act="tv-group"]').length > 1`, 10000));
    await b.ev(`document.querySelector('[data-act="live-tab"][data-tab="ota"]').click()`);
  },

  // TV view's Home: Guide alerts set on the PC show as a row when something is found, and OK on one
  // offers to record it (the record is faked, but checked with the server)
  async tvalerts(b, t) {
    await b.send('Page.navigate', { url: `${BASE}/tv#/` });
    await b.waitFor(`typeof showHome === 'function' && !!document.querySelector('.shelf, .empty')`, 30000);
    t.check('TV: no Guide alerts row when nothing is found', await b.ev(`![...document.querySelectorAll('.shelf h2')].some(h => h.textContent === 'Guide alerts')`)
      || await b.ev(`fetch('/api/guide/alerts').then(r => r.json()).then(d => d.matches.length > 0)`));
    const later = new Date(Date.now() + 2 * 86400000).toISOString();
    const match = { path: '/guide/series/episodes/test-1', series_path: '/guide/series/test', show_title: 'Test Show', episode_title: 'Pilot',
      season_number: 1, episode_number: 1, air_datetime: later, duration: 3600, channel_call_sign: 'TEST', channel_network: 'NET',
      is_new: true, is_premiere: false, schedule_state: 'none', scheduled: false, alert: 'pilot', cover_url: null, backdrop_url: null };
    await b.ev(`window.__fake['/api/guide/alerts'] = { words: ['pilot'], matches: [${JSON.stringify(match)}] }; showHome(), true`);
    t.check('TV: Guide alerts row shows what was found', await b.waitFor(`[...document.querySelectorAll('.shelf h2')].some(h => h.textContent === 'Guide alerts')
      && !!document.querySelector('[data-act="alert"]')`, 15000));
    await b.ev(`document.querySelector('[data-act="alert"]').click(), true`);
    t.check('TV: OK on an alert offers to record it', await b.waitFor(`!!document.querySelector('#dialog:not(.hidden) [data-choice]')
      && document.querySelector('#dialog .dialog-title').textContent === 'Test Show'`, 5000));
    await b.ev(`window.__writes = [], document.querySelector('#dialog [data-choice="0"]').click(), true`);
    const sent = `window.__writes.filter(w => w[1].endsWith('/api/guide/episodes/schedule')).map(w => JSON.parse(w[2]))`;
    t.check('TV: Record it sends the recording', await b.waitFor(`JSON.stringify(${sent}) === ${JSON.stringify(JSON.stringify([{ path: match.path, scheduled: true }]))}`, 5000));
    await b.ev(`delete window.__fake['/api/guide/alerts'], true`);
  },

  // Phone as a remote: an open TV view picks up what's sent for it (a page, buttons), says what it
  // shows, and the phone's page lists it, with its search. Nothing is tuned or played
  async phoneremote(b, t) {
    const post = (p, body) => fetch(BASE + p, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-TabloView': '1' }, body: JSON.stringify(body) });
    await b.send('Page.navigate', { url: `${BASE}/tv#/` });
    await b.waitFor(`typeof phoneRemote === 'object' && !!phoneRemote.id && !!document.querySelector('.shelf, .empty')`, 30000);
    const id = await b.ev(`phoneRemote.id`);
    let listed = false;
    for (let i = 0; i < 20 && !listed; i++) {
      listed = ((await api('/api/remote/screens')).screens || []).some(s => s.id === id);
      if (!listed) await sleep(500);
    }
    t.check('Remote: an open TV view is listed', listed);
    const sent = Date.now();
    await post('/api/remote/send', { screen: id, command: 'open', value: '#/library' });
    t.check('Remote: the TV view opens what the phone sent, at once', await b.waitFor(`location.hash === '#/library'`, 3000), `${Date.now() - sent} ms`);
    const reported = async page => {
      for (let i = 0; i < 20; i++) {
        const s = ((await api('/api/remote/screens')).screens || []).find(x => x.id === id);
        if (s && s.state && s.state.page === page) return true;
        await sleep(300);
      }
      return false;
    };
    t.check('Remote: the TV view says what it shows', await reported('Library'));
    await post('/api/remote/send', { screen: id, command: 'key', value: 'home' });
    t.check('Remote: Home goes home', await b.waitFor(`(location.hash || '#/') === '#/'`, 3000) && await reported('Home'));
    const refused = await post('/api/remote/send', { screen: id, command: 'open', value: 'https://example.com' });
    t.check('Remote: only TabloView’s own pages can be opened', refused.status === 400);

    // Menu → Use your phone: a QR code of the remote's address
    await b.ev(`document.querySelector('[data-act="phone-remote"]').click(), true`);
    t.check('Remote: Use your phone shows a QR code of /remote', await b.waitFor(`!!document.querySelector('#dialog:not(.hidden) .qr svg')
      && document.querySelector('#dialog .qr-url').textContent.endsWith('/remote')`, 10000));
    await b.ev(`dialogDone && dialogDone(null), true`);
    // Going down Home and back up again ends at the very top: the first row's heading was cut off
    // (a wide, short window, as on a PC: the rows are sized by the width)
    await b.send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 680, deviceScaleFactor: 1, mobile: false });
    await b.ev(`showHome(), true`);
    await b.waitFor(`document.querySelectorAll('.shelf').length > 0`, 20000);
    if (await b.ev(`document.querySelectorAll('.shelf').length >= 3`)) {
      await b.ev(`$('#screen').scrollTop = 0, focusContent(), true`);
      for (const k of ['ArrowDown', 'ArrowDown', 'ArrowDown', 'ArrowUp', 'ArrowUp', 'ArrowUp']) {
        await b.ev(`onKey({ key: '${k}', keyCode: 0, target: document.activeElement, preventDefault() {} }), true`);
        await sleep(400);
      }
      await sleep(800);
      t.check('TV: back up at the first row, the page is at the very top', await b.ev(`$('#screen').scrollTop < 2`), await b.ev(`$('#screen').scrollTop`));
      // Down a row: that row and its heading at the top, nothing cut in half above it
      await b.ev(`onKey({ key: 'ArrowDown', keyCode: 0, target: document.activeElement, preventDefault() {} }), true`);
      await b.ev(`onKey({ key: 'ArrowDown', keyCode: 0, target: document.activeElement, preventDefault() {} }), true`);
      await sleep(1200);
      t.check('TV: the row picked is at the top with its heading, none cut off above', await b.ev(`(() => {
        const scr = $('#screen').getBoundingClientRect().top, shelf = document.activeElement.closest('.shelf');
        const h = shelf.querySelector('h2').getBoundingClientRect().top;
        const above = shelf.previousElementSibling;
        return h >= scr - 1 && h < scr + 60 && (!above || above.getBoundingClientRect().bottom <= scr + 1);
      })()`));
    }
    await b.send('Emulation.clearDeviceMetricsOverride', {});

    // The PC's Settings → Desktop & network has the same code (shown when other devices can connect)
    await b.ev(`localStorage.setItem('tv_view', 'pc'), true`);  // (TV view above made it this browser's view)
    await b.send('Page.navigate', { url: `${BASE}/#/settings?tab=desktop` });
    await b.waitFor(`typeof phoneRemoteQr === 'function'`, 20000);
    await b.ev(`phoneRemoteQr('http://192.168.1.50:7070/remote'), true`);
    t.check('Remote: Settings shows the QR code too', await b.waitFor(`!!document.querySelector('.overlay .qr-box svg')
      && document.querySelector('.overlay .qr-url').textContent === 'http://192.168.1.50:7070/remote'`, 10000));
    await b.ev(`document.querySelector('.overlay [data-action="modal-ok"]').click(), true`);

    await b.send('Page.navigate', { url: `${BASE}/remote` });
    t.check('Remote: the phone page lists the screen and its buttons', await b.waitFor(`!document.querySelector('#controls').classList.contains('hidden')`, 10000));
    await b.ev(`(() => { const s = document.querySelector('#search'); s.value = 'a'; s.dispatchEvent(new Event('input')); })()`);
    t.check('Remote: search finds channels or shows', await b.waitFor(`document.querySelectorAll('#results .result').length > 0`, 20000));
  },

  // Splash: the intro plays the first time a browser opens this version, then gets out of the way
  // (by itself, or on a key, which doesn't reach the page); not again until the next version
  async splash(b, t) {
    for (const page of ['/', '/tv']) {
      await b.send('Page.navigate', { url: `${BASE}${page}` });
      await b.waitFor(`document.readyState === 'complete'`, 20000);
      await b.ev(`localStorage.setItem('tv_view', ${JSON.stringify(page === '/' ? 'pc' : 'tv')}), localStorage.removeItem('splash_version'), sessionStorage.setItem('splash_test', '1'), true`);
      await b.send('Page.reload', {});
      t.check(`Splash (${page}): shown the first time`, await b.waitFor(`!!document.querySelector('#splash')`, 5000));
      t.check(`Splash (${page}): the video plays`, await b.waitFor(`document.querySelector('#splash video').currentTime > 0.3`, 5000));
      t.check(`Splash (${page}): gone by itself`, await b.waitFor(`!document.querySelector('#splash')`, 8000));
      await b.ev(`sessionStorage.setItem('splash_test', '1'), true`);  // (allowed, but already seen)
      await b.send('Page.reload', {});
      await b.waitFor(`document.readyState === 'complete'`, 20000);
      t.check(`Splash (${page}): not again for the same version`, !(await b.ev(`!!document.querySelector('#splash')`)));
    }
    // A key skips it, and isn't passed on to the page
    await b.ev(`localStorage.setItem('splash_version', '0.0.1'), sessionStorage.setItem('splash_test', '1'), true`);  // (a new version)
    await b.send('Page.reload', {});
    await b.waitFor(`!!document.querySelector('#splash')`, 5000);
    await b.ev(`window.__keys = 0, document.addEventListener('keydown', () => window.__keys++), true`);
    await b.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    t.check('Splash: a key skips it, without reaching the page', await b.waitFor(`!document.querySelector('#splash')`, 2000) && await b.ev(`window.__keys === 0`));
  },

  // Add to Home Screen: PC view and the phone remote each have a manifest the browser reads without
  // errors, with icons it can load
  async homescreen(b, t) {
    for (const [page, name, start] of [['/', 'TabloView', '/'], ['/remote', 'TabloView Remote', '/remote']]) {
      await b.send('Page.navigate', { url: `${BASE}${page}` });
      await b.waitFor(`document.readyState === 'complete'`, 20000);
      const m = (await b.send('Page.getAppManifest', {})).result || {};
      const parsed = (() => { try { return JSON.parse(m.data || '{}'); } catch { return {}; } })();
      t.check(`Home screen: ${name} has its manifest, without errors`, m.url && !(m.errors || []).length && parsed.name === name
        && new URL(parsed.start_url, BASE).pathname === start, JSON.stringify(m.errors || []));
      const icons = await Promise.all((parsed.icons || []).map(i => fetch(new URL(i.src, BASE)).then(r => r.ok && r.headers.get('content-type') === 'image/png')));
      t.check(`Home screen: ${name}'s icons load`, icons.length >= 3 && icons.every(Boolean));
    }
  },

  // TV view on a PC: the menu opened with the mouse closes once the arrow keys move off it, with the
  // mouse still resting on it (it stayed open)
  async tvmenu(b, t) {
    await b.send('Page.navigate', { url: `${BASE}/tv#/` });
    await b.waitFor(`typeof showHome === 'function' && !!document.querySelector('.shelf, .empty')`, 30000);
    await sleep(800);  // (Home settled: it puts the highlight on the page when it's drawn)
    const open = `$('#rail').getBoundingClientRect().width > innerWidth * 0.12`;
    const home = await b.ev(`(() => { const r = document.querySelector('.rail .nav').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()`);
    for (const dx of [0, 3]) await b.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: home[0] + dx, y: home[1] });
    t.check('TV menu: the mouse over it opens it', await b.waitFor(open, 3000));
    await b.ev(`onKey({ key: 'ArrowRight', keyCode: 0, target: document.activeElement, preventDefault() {} }), true`);
    await sleep(600);
    t.check('TV menu: the arrows moving off it close it, the mouse still on it', await b.ev(`!(${open}) && !document.activeElement.closest('.rail')`), await b.ev(`JSON.stringify({ w: $('#rail').getBoundingClientRect().width, cls: $('#rail').className, fw: !!$('#rail').matches(':focus-within'), act: document.activeElement.className })`));
    await b.ev(`showHome(), true`);  // the page changing under the resting mouse
    await sleep(1500);
    t.check('TV menu: the page changing under a resting mouse doesn’t pull the highlight back', await b.ev(`!document.activeElement.closest('.rail') && !(${open})`));
  },

  // Add a channel offers every channel, not only the first one's list: watching a playlist group's
  // channel, antenna channels and favorites of every kind are there too (a forum user couldn't add
  // an antenna channel to one from a group). Nothing is tuned
  async pickany(b, t) {
    const fake = (id, kind, extra = {}) => ({ channel_id: id, call_sign: id, name: id, major: 0, minor: 0, network: 'G1', kind, hidden: false, favorite: false, categories: [], airings: [], ...extra });
    const chans = JSON.stringify([fake('ota-a', 'ota', { major: 2, minor: 1 }), fake('ota-fav', 'ota', { major: 4, minor: 1, favorite: true }),
      fake('fast-a', 'fast', { network: 'Pluto' }), fake('x-1', 'extra'), fake('x-2', 'extra'), fake('x-other', 'extra', { network: 'G2' })]);
    // Computer
    await b.open('#/');
    await b.ev(`(() => {
      window.__keep = { epg: state.epg, cat: state.epgCategory, group: state.epgGroup, stream: state.stream };
      state.epg = { window_end: new Date(Date.now() + 6 * 3600000).toISOString(), channels: ${chans} };
      state.epgCategory = 'extra'; state.epgGroup = 'G1'; state.stream = { channelId: 'x-1' };
    })()`);
    const pc = await b.ev(`player.pickSections().map(([label, list]) => label + ':' + list.map(c => c.channel_id).join(','))`);
    t.check(`Computer: a second channel can come from any list (${pc.join(' | ')})`,
      pc.join('|') === 'Favorites:ota-fav|G1:x-2|Antenna:ota-a|Streaming:fast-a|More:x-other');
    await b.ev(`dual.picking = true; $('#chanPanel').classList.remove('hidden'); player.renderChannels()`);
    t.check('Computer: the picker shows each list under its name', await b.ev(`document.querySelectorAll('#chanPanel .chan-sec').length === 5 && document.querySelectorAll('#chanPanel .chan-row').length === 5`));
    await b.ev(`dual.picking = false; $('#chanPanel').classList.add('hidden');
      state.epg = __keep.epg; state.epgCategory = __keep.cat; state.epgGroup = __keep.group; state.stream = __keep.stream`);
    // TV view
    await b.send('Page.navigate', { url: `${BASE}/tv#/live` });
    await b.waitFor(`typeof dual !== 'undefined' && state.live`, 30000);
    await b.ev(`state.live = { ...state.live, channels: ${chans} }; state.liveTab = 'extra'; state.tvGroup = { name: 'G1' };
      player.s = { kind: 'live', id: 'x-1' }; dual.list = dual.pickList(); dual.index = 0; dual.picking = true; dual.renderPicker()`);
    const tv = await b.ev(`dual.list.map(e => e.sec + ':' + e.c.channel_id).join('|')`);
    t.check(`TV: a second channel can come from any list (${tv})`, tv === 'Favorites:ota-fav|G1:x-2|Antenna:ota-a|Streaming:fast-a|More:x-other');
    t.check('TV: the picker shows each list under its name', await b.ev(`document.querySelectorAll('#chPicker .pick-sec').length === 5`));
    const key = k => b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(k)}, bubbles: true }))`);
    await b.ev(`$('#player').classList.remove('hidden'); player.open = true`);
    await key('ArrowRight'); await key('ArrowRight');
    t.check('TV: ▶ jumps a list at a time', await b.ev(`dual.picking && dual.list[dual.index].c.channel_id === 'ota-a'`));
    await key('ArrowLeft'); await key('ArrowLeft'); await key('ArrowLeft');
    t.check('TV: ◀ jumps back, round to the last list', await b.ev(`dual.picking && dual.list[dual.index].c.channel_id === 'x-other'`));
    await key('Escape');
    t.check('TV: Back closes the picker', await b.ev(`!dual.picking && $('#chPicker').classList.contains('hidden')`));
    await b.ev(`player.open = false; player.s = {}; $('#player').classList.add('hidden')`);
  },

  // Captions after a second stream in the same player (a jump, a resume, the next recording): hls.js
  // adds a new track each time and old ones can't be removed, so the newest is shown (a forum user
  // lost captions after scrubbing until the page was reloaded). Nothing is played
  async cctrack(b, t) {
    const probe = `(() => { const v = document.createElement('video');
      const a = v.addTextTrack('captions', 'English', 'en'), es = v.addTextTrack('captions', 'Spanish', 'es'), c = v.addTextTrack('captions', 'English', 'en');
      return captionTrack(v) === c; })()`;
    await b.open('#/');
    t.check('Computer: captions come from the newest stream’s track', await b.ev(probe));
    await b.send('Page.navigate', { url: `${BASE}/tv#/live` });
    await b.waitFor(`typeof captionTrack === 'function'`, 30000);
    t.check('TV: captions come from the newest stream’s track', await b.ev(probe));
  },

  // TV view on a stick with 1 GB (most Fire TV Sticks): Add a channel is still offered, and says why
  // it can't when pressed, instead of opening the channel list. Nothing is tuned
  async tvlowmem(b, t) {
    await b.send('Page.navigate', { url: `${BASE}/tv#/live` });
    await b.waitFor(`typeof dual !== 'undefined' && state.live`, 30000);
    await b.ev(`Object.defineProperty(navigator, 'deviceMemory', { value: 1, configurable: true })`);
    const c = await b.ev(`(liveChannels()[0] || {}).channel_id || null`);
    if (!c) return t.skip('TV: Add a channel on a 1 GB TV', 'no channels');
    await b.ev(`player.s = { kind: 'live', id: ${JSON.stringify(c)}, channel: liveChannels()[0] }; $('#player').classList.remove('hidden'); player.showControls()`);
    t.check('TV (1 GB): OK still offers Add a channel', await b.ev(`player.controlList.some(([v]) => v === 'second')`));
    await b.ev(`player.controlIndex = player.controlList.findIndex(([v]) => v === 'second'); player.pressControl()`); await sleep(300);
    t.check('TV (1 GB): pressing it says there isn’t enough memory, no channel list', await b.ev(`!dual.picking && $('#chPicker').classList.contains('hidden') && /enough memory/.test($('#player .chan-banner').textContent) && !$('#player .chan-banner').classList.contains('hidden')`));
    await b.ev(`player.s = {}; player.hideControls && player.hideControls()`);
  },

  // TV view: two channels at once, with the remote's keys. Streaming channels, so no antenna tuner
  // is taken; still plays for real, so only with TABLOVIEW_ALLOW_TUNE=1
  async tvdual(b, t) {
    if (!process.env.TABLOVIEW_ALLOW_TUNE) return t.skip('TV: two channels at once', 'set TABLOVIEW_ALLOW_TUNE=1 to play for real');
    await b.send('Page.navigate', { url: `${BASE}/tv#/live` });
    await b.waitFor(`typeof dual !== 'undefined' && state.live`, 30000);
    await b.ev(`state.liveTab = 'fast'`);
    const chans = await b.ev(`liveChannels().slice(0, 3).map(c => c.channel_id)`);
    if (chans.length < 3) return t.skip('TV: two channels at once', 'fewer than 3 streaming channels');
    const key = k => b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(k)}, bubbles: true }))`);
    await b.ev(`player.tune(${JSON.stringify(chans[0])})`);
    t.check('TV: a channel plays', await b.waitFor(`!player.video().paused && player.video().currentTime > 2`, 60000));
    await key('Enter'); await sleep(300);
    t.check('TV: OK offers Add a channel', await b.ev(`player.controlList.some(([v]) => v === 'second')`));
    await b.ev(`player.controlIndex = player.controlList.findIndex(([v]) => v === 'second'); player.pressControl()`); await sleep(300);
    t.check('TV: the channel list opens, without the one playing', await b.ev(`dual.picking && !$('#chPicker').classList.contains('hidden') && !dual.list.some(e => e.c.channel_id === player.s.id)`));
    await key('ArrowDown'); await key('ArrowUp');
    await key('Enter');
    t.check('TV: both play, side by side, the first one heard', await b.waitFor(`dual.on && dual.video().currentTime > 2 && !player.video().paused && $('#player').classList.contains('dual-side')`, 60000)
      && await b.ev(`!player.video().muted && dual.video().muted && /🔊/.test($('#paneLabel1').textContent)`));
    await key('ArrowRight'); await sleep(300);
    t.check('TV: ▶ hears the right-hand one', await b.ev(`dual.active === 'second' && player.video().muted && !dual.video().muted && /🔊/.test($('#paneLabel2').textContent)`));
    const was = await b.ev(`dual.s.id`), first = await b.ev(`player.s.id`);
    await key('ArrowDown');
    t.check('TV: ▼ changes the channel you hear, not the other', await b.waitFor(`dual.s.id && dual.s.id !== ${JSON.stringify(was)} && dual.s.id !== player.s.id && dual.video().currentTime > 2`, 60000)
      && await b.ev(`player.s.id === ${JSON.stringify(first)}`));
    await key('Enter'); await sleep(300);
    await b.ev(`player.controlIndex = player.controlList.findIndex(([v]) => v === 'layout'); player.pressControl()`); await sleep(300);
    t.check('TV: Layout switches to Big and small', await b.ev(`$('#player').classList.contains('dual-pip') && /Big and small/.test($('#osdControls .ctl.on').textContent)`));
    await key('Escape'); await sleep(200);  // the buttons away
    const heard = await b.ev(`dual.s.id`), heardSession = await b.ev(`dual.s.sessionId`);
    await key('Escape'); await sleep(1500);
    t.check('TV: Back closes the other, the one you hear carries on full screen', await b.ev(`!dual.on && player.s.id === ${JSON.stringify(heard)} && player.s.sessionId === ${JSON.stringify(heardSession)} && !$('#player').classList.contains('dual')`)
      && await b.waitFor(`!player.video().paused && !player.video().muted`, 20000));
    await b.ev(`player.exit()`); await sleep(1500);
  },

    async whatsnew(b, t) {
    await b.open('#/');
    await b.ev(`window.__fake['/api/system/whatsnew'] = { show: true, version: '9.9.9', notes: ['First thing', 'Second thing'] }; void showWhatsNew()`);
    await sleep(600);
    t.check('What’s new card shows the notes', /What’s new in TabloView 9\.9\.9/.test(await b.ev(`(document.querySelector('.overlay .dialog-title') || {}).textContent || ''`))
      && (await b.ev(`document.querySelectorAll('.whatsnew-list li').length`)) === 2);
    await b.ev(`document.querySelector('[data-action="modal-ok"]').click()`); await sleep(500);
    t.check('Closing it records it as seen (intercepted)', await b.ev(`window.__writes.some(w => w[1] === '/api/system/whatsnew/seen')`));
    await b.go('#/settings?tab=diagnostics', `document.querySelector('[data-action="version-history"]')`);
    await b.ev(`document.querySelector('[data-action="version-history"]').click()`); await sleep(800);
    t.check('Settings → Version history lists every version, newest first', await b.ev(`(() => {
      const v = [...document.querySelectorAll('.changelog-version')].map(h => h.textContent);
      return v.length > 3 && v[v.length - 1].startsWith('1.0.0') && /You have this/.test(v[0]);
    })()`));
    await b.ev(`closeModal(false)`);
  },

  // Searching stops on the spot; a break found too long isn't skipped on its own; on a TV, OK in a
  // break brings up the controls with Skip first (PC player, then the TV view)
  // Live TV → More → Arrange groups (needs a playlist with 2 or more groups in Settings → Live TV).
  // The saves are caught by the test shim (window.__writes), so the real order isn't changed
  async grouporder(b, t) {
    await b.open('#/live');
    await b.waitFor(`document.querySelector('[data-action="epg-cat"][data-value="extra"]')`, 30000);
    await b.ev(`document.querySelector('[data-action="epg-cat"][data-value="extra"]').click(), true`);
    if (!await b.waitFor(`document.querySelector('[data-action="extra-group-arrange"]')`, 60000))
      return t.skip('Arrange groups', 'needs a playlist with two or more groups');
    const names = await b.ev(`state.extraGroups.map(g => g.name)`);
    await b.ev(`document.querySelector('[data-action="extra-group-arrange"]').click(), true`);
    t.check('The dialog lists every group', await b.waitFor(`document.querySelectorAll('.grp-row').length === ${names.length}`));
    // The last group to the top, then the (new) second one down a place
    await b.ev(`[...document.querySelectorAll('[data-grp="top"]')].pop().click(), true`);
    t.check('Top moves a group first', await b.ev(`document.querySelector('.grp-name').textContent.startsWith(${JSON.stringify(names[names.length - 1])})`));
    await b.ev(`document.querySelector('[data-grp="down"][data-i="1"]').click(), true`);
    // Bottom sends the first group to the end
    const first = await b.ev(`document.querySelector('.grp-name').firstChild.textContent.trim()`);
    await b.ev(`document.querySelector('[data-grp="bottom"][data-i="0"]').click(), true`);
    t.check('Bottom moves a group last', await b.ev(`[...document.querySelectorAll('.grp-name')].pop().textContent.startsWith(${JSON.stringify(first)})`));
    await b.ev(`document.querySelector('[data-grp="top"][data-i="${names.length - 1}"]').click(), true`);  // (and back)
    const want = [names[names.length - 1], names[1], names[0], ...names.slice(2, -1)];
    // Hide the second group from here (the switch at the start of its row)
    const hideName = want[1], wasHidden = await b.ev(`state.extraGroups.find(g => g.name === ${JSON.stringify(hideName)}).hidden`);
    await b.ev(`(() => { const box = document.querySelector('[data-grp-show="1"]'); box.checked = !box.checked; box.dispatchEvent(new Event('change', { bubbles: true })); })()`);
    t.check('The switch marks a group hidden (or shown)', await b.ev(`document.querySelectorAll('.grp-row')[1].classList.contains('dim') === ${!wasHidden}`));
    await b.ev(`window.__writes = [], document.querySelector('.overlay [data-action="modal-ok"]').click(), true`);
    const sent = `window.__writes.filter(w => w[1].includes('/api/live/extra/group_order')).map(w => JSON.parse(w[2]).order)`;
    t.check('Save sends the new order', await b.waitFor(`JSON.stringify(${sent}) === ${JSON.stringify(JSON.stringify([want]))}`, 5000));
    const hid = `window.__writes.filter(w => w[1].endsWith('/api/live/extra/group')).map(w => JSON.parse(w[2]))`;
    t.check('Save hides (or shows) that group', await b.waitFor(`JSON.stringify(${hid}) === ${JSON.stringify(JSON.stringify([{ group: hideName, hidden: !wasHidden }]))}`, 5000));
    await b.ev(`document.querySelector('[data-action="extra-group-arrange"]').click(), true`);
    await b.waitFor(`document.querySelector('#grpReset')`);
    await b.ev(`window.__writes = [], document.querySelector('#grpReset').click(), true`);
    t.check('Playlist order sends an empty order', await b.waitFor(`JSON.stringify(${sent}) === '[[]]'`, 5000));
  },

  // TV view: only one caption track shows. Something else turning on a second (hls.js, a second
  // caption channel) drew two sets of captions over each other until CC was toggled (1.4.4 forum report)
  async tvcaptions(b, t) {
    await b.send('Page.navigate', { url: `${BASE}/tv#/` });
    await b.waitFor(`typeof player === 'object' && !!document.querySelector('.shelf, .empty')`, 30000);
    await b.ev(`(() => {
      const v = player.video();
      window.__en = v.addTextTrack('captions', 'English', 'en');
      state.captions = true;
      player.applyCaptions();
      return true;
    })()`);
    t.check('TV captions: the English track shows', await b.waitFor(`__en.mode === 'showing'`, 3000));
    // A second track that appeared earlier (hidden then), turned on later by something else
    await b.ev(`(() => { window.__cc3 = player.video().addTextTrack('captions', 'Unknown CC', 'es'); return true; })()`);
    await sleep(500);
    await b.ev(`__cc3.mode = 'showing', true`);
    t.check('TV captions: a second track turned on goes off again, the English one stays', await b.waitFor(`__cc3.mode !== 'showing' && __en.mode === 'showing'`, 3000),
      await b.ev(`JSON.stringify([__en.mode, __cc3.mode])`));
    await b.ev(`state.captions = false, player.applyCaptions(), true`);
    await sleep(500);
    t.check('TV captions: off means none show', await b.ev(`[...player.video().textTracks].every(tr => tr.mode !== 'showing')`));
  },

  async seekhold(b, t) {
    const shows = (await api('/api/shows')).shows;
    const eps = (await api(`/api/shows/episodes?show_id=${encodeURIComponent(shows[0].id)}`)).episodes;
    const ep = eps.find(e => e.recording_state === 'finished' && (e.duration || 0) >= 1500);
    if (!ep) return t.skip('Searching a recording', 'needs a finished recording of 25 minutes or more');
    await b.open(`#/show/${encodeURIComponent(shows[0].id)}`);
    await b.waitFor(`document.querySelector('.ep-row')`);
    await b.ev(`player.playEpisode(${JSON.stringify(ep.id)}, 60)`);
    t.check('PC: the recording plays', await b.waitFor(`!$('#video').paused && $('#video').currentTime > 3`, 120000));
    await b.ev(`player.skip(30)`); await sleep(3000);
    t.check('PC: ▶▶ stops on the spot', await b.ev(`$('#video').paused && state.stream.held`));
    let p = await b.ev(`player.position()`);
    await b.ev(`player.hold(); player.seekTo(${p} + 900)`);  // past what's converted: the stream starts again there
    t.check('PC: a jump past what is converted stays stopped there', await b.waitFor(`/Paused at/.test($('#playerStatus').textContent) && Math.abs(player.position() - ${p + 900}) < 5`, 120000)
      && await b.ev(`$('#video').paused`));
    await sleep(2000);
    t.check('PC: ...and does not start on its own', await b.ev(`$('#video').paused`));
    await b.ev(`$('#video').play().catch(() => {}), true`);
    t.check('PC: Play carries on from there', await b.waitFor(`!$('#video').paused && !state.stream.held && player.position() > ${p + 901}`, 20000));
    // Settings → Playback → Stop where I land when searching, off: plays on as before 1.3.6
    await b.ev(`state.stopAfterSearch = false, player.skip(30), true`); await sleep(3000);
    t.check('PC: with the switch off, ▶▶ plays on', await b.ev(`!$('#video').paused && !state.stream.held`));
    await b.ev(`state.stopAfterSearch = true`);
    p = await b.ev(`player.position()`);
    await b.ev(`Object.assign(state.stream, { autoSkip: true, skippedBreaks: new Set(), breaks: [{ start: ${p}, end: ${p + 600} }] })`); await sleep(2500);
    t.check('PC: a 10-minute "break" is offered, not skipped', await b.ev(`player.position() < ${p + 30} && !$('#skipBreak').classList.contains('hidden')`));
    await b.ev(`$('#skipBreak .skip-x').click()`); await sleep(1500);
    t.check('PC: × puts Skip break away and it keeps playing', await b.ev(`$('#skipBreak').classList.contains('hidden') && !$('#video').paused && player.position() < ${p + 30}`));
    p = await b.ev(`player.position()`);
    await b.ev(`Object.assign(state.stream, { skippedBreaks: new Set(), breaks: [{ start: ${p}, end: ${p + 60} }] })`);
    t.check('PC: a normal break is still skipped', await b.waitFor(`player.position() >= ${p + 58}`, 15000));
    await b.ev(`player.close()`); await sleep(1500);

    // TV view
    await b.send('Page.navigate', { url: `${BASE}/tv` });
    await b.waitFor(`typeof player !== 'undefined' && typeof remember === 'function'`, 30000);
    await b.ev(`remember([${JSON.stringify(ep)}])`);  // (as a recording's page would have)
    await b.ev(`player.playEpisode(${JSON.stringify(ep.id)}, { from: 'start' })`);
    t.check('TV: the recording plays', await b.waitFor(`!player.video().paused && player.video().currentTime > 3`, 120000));
    const key = k => b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(k)}, bubbles: true }))`);
    await key('ArrowRight'); await sleep(3000);
    t.check('TV: ▶▶ stops on the spot', await b.ev(`player.video().paused && player.held && /Paused here/.test($('#osdHint').textContent)`));
    await key('Enter');
    t.check('TV: OK carries on', await b.waitFor(`!player.video().paused && !player.held`, 20000));
    // (once it's moving: starting again at a spot fetches the breaks afresh, over a made-up one)
    p = await b.ev(`player.position()`);
    await b.waitFor(`player.position() > ${p} + 2`, 60000); await sleep(2000);
    p = await b.ev(`player.position()`);
    await b.ev(`Object.assign(player.s, { autoSkip: true, skippedBreaks: new Set(), breaks: [{ start: ${p}, end: ${p + 600} }] })`); await sleep(1500);
    t.check('TV: a 10-minute "break" is offered, not skipped', await b.ev(`player.position() < ${p + 30} && /Long break/.test($('#skipBanner').textContent)`),
      await b.ev(`JSON.stringify({ p0: ${p}, pos: player.position(), paused: player.video().paused, banner: $('#skipBanner').textContent, pending: player.pendingSeek })`));
    await key('Escape'); await sleep(1500);
    t.check('TV: Back puts the banner away and it keeps playing', await b.ev(`$('#skipBanner').classList.contains('hidden') && !player.inBreak && player.open && !player.video().paused`));
    await b.ev(`player.dismissed = new Set()`); await sleep(1000);  // (offered again, for the next checks)
    await key('Enter'); await sleep(300);
    t.check('TV: OK in a break brings up the controls, Skip first', await b.ev(`player.controls && player.controlIndex === 0 && /Skip break/.test($('#osdControls .ctl.on').textContent) && !player.video().paused`));
    await key('Enter');
    t.check('TV: OK again skips it', await b.waitFor(`player.position() >= ${p + 595}`, 30000));
    await b.waitFor(`!player.video().paused`, 30000);
    p = await b.ev(`player.position()`);
    await b.ev(`Object.assign(player.s, { skippedBreaks: new Set(), breaks: [{ start: ${p}, end: ${p + 60} }] })`);
    t.check('TV: a normal break is still skipped', await b.waitFor(`player.position() >= ${p + 58}`, 15000));
    await b.ev(`player.exit()`); await sleep(1500);
  },

  async resume(b, t) {
    const inProgress = (await api('/api/episodes/in_progress')).episodes;
    if (!inProgress.length) return t.skip('Resume', 'no partly watched recordings');
    const ep = inProgress[0];
    await b.open('#/');
    await b.waitFor(`document.querySelector('#rowContinue .media-card')`);
    t.check('Home shows Continue watching', true);
    await b.go(`#/show/${encodeURIComponent(ep.show_id)}`, `document.querySelector('.ep-row')`);
    // The episode row's play button asks; the show page's big Resume button resumes straight away
    await b.ev(`document.querySelector('.ep-row[data-ep-row=${JSON.stringify(ep.id)}] [data-action="play-ep"]').click()`); await sleep(500);
    t.check('Asks to resume or start over', /You stopped at/.test(await b.ev(`(document.querySelector('.overlay .dialog-text') || {}).textContent || ''`)));
    await b.ev(`document.querySelector('[data-value="resume"]').click()`);
    const ok = await b.waitFor(`document.getElementById('video').currentTime > 2`, 45000);
    t.check('Resumes at the saved point', ok && (await b.ev('player.position()')) >= ep.position, `position ${await b.ev('player.position()')}s, saved ${ep.position}s`);
    t.check('Timeline shows the real time', (await b.ev(`document.getElementById('tlNow').textContent`)) !== '0:00');
    const session = await b.ev('state.stream.sessionId');
    await b.ev('player.seekTo(player.position() + 3)'); await sleep(1500);
    t.check('Small jump stays in the same stream', (await b.ev('state.stream.sessionId')) === session);
    // Force a save (normally only after moving 10+ s from the last one) and confirm the shim caught it
    await b.ev('state.stream.lastSaved = 0; player.saveProgress()'); await sleep(500);
    t.check('Progress save was intercepted, not sent', await b.ev(`window.__writes.some(w => /\\/progress$/.test(w[1]))`));
    await b.ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))`); await sleep(1500);
  },
};
