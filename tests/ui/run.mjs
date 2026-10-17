// Runs the browser test suites against a running TabloView (default http://localhost:7070).
//   node tests/ui/run.mjs                 all suites
//   node tests/ui/run.mjs live resume     just these
// Set TABLOVIEW_URL to test another address. Exit code 1 if anything fails.
import { launch, reporter, api, BASE } from './lib.mjs';
import { SUITES } from './suites.mjs';

const wanted = process.argv.slice(2);
const names = wanted.length ? wanted : Object.keys(SUITES);
const unknown = names.filter(n => !SUITES[n]);
if (unknown.length) { console.error(`Unknown suite(s): ${unknown.join(', ')}. Available: ${Object.keys(SUITES).join(', ')}`); process.exit(2); }

try { await api('/api/system/info'); } catch { console.error(`TabloView isn't reachable at ${BASE}. Start it first.`); process.exit(2); }
const status = await api('/api/auth/status');
if (!status.authenticated) { console.error('TabloView is not signed in to a Tablo; the browser tests need real data.'); process.exit(2); }

const all = [];
for (const name of names) {
  const t = reporter(name);
  const b = await launch();
  const started = Date.now();
  try {
    await SUITES[name](b, t);
  } catch (e) {
    t.check('suite finished without errors', false, e.message);
  } finally {
    t.check('no JavaScript errors', b.errors.length === 0, b.errors.join(' | ').slice(0, 300));
    // Always stop playback so a failed check can't leave a stream (and FFmpeg) running
    try { if (await b.ev('player.isOpen()')) { await b.ev('player.close()'); await new Promise(r => setTimeout(r, 1500)); } } catch {}
    b.close();
  }
  console.log(`\n${name} (${Math.round((Date.now() - started) / 1000)}s)`);
  for (const r of t.results) console.log(`  ${r.skipped ? 'SKIP' : r.ok ? 'PASS' : 'FAIL'}  ${r.name}${r.detail ? `  (${r.detail})` : ''}`);
  all.push(...t.results);
}

const failed = all.filter(r => !r.ok);
const skipped = all.filter(r => r.skipped);
console.log(`\n${all.length - failed.length - skipped.length} passed, ${failed.length} failed, ${skipped.length} skipped`);
process.exit(failed.length ? 1 : 0);
