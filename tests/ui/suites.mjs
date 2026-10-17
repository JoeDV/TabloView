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
