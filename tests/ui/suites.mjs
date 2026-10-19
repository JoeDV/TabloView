// Browser test suites. They work with whatever is on your Tablo (no show names are hard-coded) and
// skip checks that need data you don't have (e.g. an in-progress recording). All writes are faked
// by the fetch shim in lib.mjs; the only real requests are page loads and recording playback.
import fs from 'node:fs';
import path from 'node:path';
import { api, sleep } from './lib.mjs';

async function transcodeSessions() {
  const info = await api('/api/system/info');
  const dir = path.join(info.data_dir, 'transcode');
  return fs.existsSync(dir) ? fs.readdirSync(dir, { withFileTypes: true }).filter(d => d.isDirectory()).length : 0;
}

export const SUITES = {
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
      ['#/device', '.panel', 'Device'],
    ]) {
      t.check(`${label} page renders`, await b.go(hash, `document.querySelector(${JSON.stringify(ready)})`, 30000));
    }
    t.check('Device page shows the app version', /TabloView \d+\.\d+\.\d+/.test(await b.ev(`document.querySelector('.panel-grid').textContent`)));
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
    t.check('Tuner badge shows tuners still releasing', /2 releasing/.test(await b.ev(`document.getElementById('tunerText').textContent`)));
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
    await b.go('#/device', `document.querySelector('[data-change="export-format"]')`);
    t.check('Device page has the export format setting', (await b.ev(`document.querySelector('[data-change="export-format"]').options.length`)) === 2);
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
    await b.go('#/device', `document.querySelector('[data-change="rerecord-failed"]')`);
    t.check('Device page has the Record failed recordings again switch', true);
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
    await b.ev(`state.stream.autoSkip = true; player.checkBreak(305)`); await sleep(300);
    t.check('With auto-skip on it jumps by itself', (await b.ev('window.__seek')) === 420 && /Skipped/.test(await b.ev(`document.getElementById('toasts').textContent`)));
    await b.ev(`player.playEpisode = player.__realPlay; state.stream.episodeId = null; player.close()`);
  },

  async pin(b, t) {
    await b.open('#/device');
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
    await b.go('#/device', `document.querySelector('[data-action="check-update"]')`);
    t.check('Device → About offers Check now and Open in the Store', /Open in the Store/.test(await b.ev(`document.getElementById('view').textContent`)));
  },

  async whatsnew(b, t) {
    await b.open('#/');
    await b.ev(`window.__fake['/api/system/whatsnew'] = { show: true, version: '9.9.9', notes: ['First thing', 'Second thing'] }; void showWhatsNew()`);
    await sleep(600);
    t.check('What’s new card shows the notes', /What’s new in TabloView 9\.9\.9/.test(await b.ev(`(document.querySelector('.overlay .dialog-title') || {}).textContent || ''`))
      && (await b.ev(`document.querySelectorAll('.whatsnew-list li').length`)) === 2);
    await b.ev(`document.querySelector('[data-action="modal-ok"]').click()`); await sleep(500);
    t.check('Closing it records it as seen (intercepted)', await b.ev(`window.__writes.some(w => w[1] === '/api/system/whatsnew/seen')`));
    await b.go('#/device', `document.querySelector('[data-action="version-history"]')`);
    await b.ev(`document.querySelector('[data-action="version-history"]').click()`); await sleep(800);
    t.check('Device → Version history lists every version, newest first', await b.ev(`(() => {
      const v = [...document.querySelectorAll('.changelog-version')].map(h => h.textContent);
      return v.length > 3 && v[v.length - 1].startsWith('1.0.0') && /You have this/.test(v[0]);
    })()`));
    await b.ev(`closeModal(false)`);
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
