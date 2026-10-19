// Shared helpers for TabloView browser tests: launches headless Chrome/Edge, talks to it over the
// DevTools protocol, and installs a fetch shim in the page so tests can never change the Tablo.
import { spawn, execSync } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';

export const BASE = process.env.TABLOVIEW_URL || 'http://localhost:7070';
export const sleep = ms => new Promise(r => setTimeout(r, ms));

const BROWSERS = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  `${os.homedir()}/AppData/Local/Google/Chrome/Application/chrome.exe`,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
];

// Requests that are allowed through for real. Everything else that isn't a GET is faked, so tests
// can't skip recordings, change rules, delete, save progress or tune live TV on the real Tablo.
// (Starting/stopping playback of a recording is read-only on the Tablo.)
const ALLOWED_WRITES = [/^\/api\/episodes\/[^/]+\/watch/, /^\/api\/live\/stop$/,
  // Live TV tuning takes a tuner, so it's only real when a test run asks for it
  ...(process.env.TABLOVIEW_ALLOW_TUNE ? [/^\/api\/live\/tune$/] : [])];

const SHIM = `(() => {
  if (window.__shim) return; window.__shim = true;
  window.__writes = []; window.__fake = {};
  // No "What's new" card in tests (its "seen" request is faked, so it would show on every page)
  window.__fake['/api/system/whatsnew'] = { show: false, notes: [] };
  const realFetch = window.fetch.bind(window);
  const allowed = ${JSON.stringify(ALLOWED_WRITES.map(r => r.source))}.map(s => new RegExp(s));
  const reply = b => new Response(JSON.stringify(b), { status: 200, headers: { 'Content-Type': 'application/json' } });
  window.fetch = async (url, opts = {}) => {
    const u = String(url), method = (opts.method || 'GET').toUpperCase();
    // Faked answers stand in for reads only, so a write to a longer path (e.g. .../swap) is still caught below
    for (const [prefix, body] of Object.entries(window.__fake)) {
      if (method === 'GET' && u.startsWith(prefix)) return reply(typeof body === 'function' ? body(await realFetch(url, opts).then(r => r.json())) : body);
    }
    if (method !== 'GET' && !allowed.some(r => r.test(u.split('?')[0]))) {
      window.__writes.push([method, u, opts.body || '']);
      return reply({ success: true, deleted_count: 0, deleted_ids: JSON.parse(opts.body || '{}').episode_ids || [], errors: [], changed_ids: [], session_id: null, stream_url: '' });
    }
    return realFetch(url, opts);
  };
})();`;

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => { const { port } = srv.address(); srv.close(() => resolve(port)); });
    srv.on('error', reject);
  });
}

// Kill the browser and all its helper processes (killing only the parent can leave children behind)
function killTree(proc) {
  try { execSync(`taskkill /PID ${proc.pid} /T /F`, { stdio: 'ignore' }); } catch { try { proc.kill(); } catch {} }
}

async function startBrowser() {
  const exe = BROWSERS.find(p => fs.existsSync(p));
  if (!exe) throw new Error('Chrome or Edge not found');
  const port = await freePort();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'tabloview-ui-'));
  const proc = spawn(exe, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
    '--no-first-run', '--hide-scrollbars', '--autoplay-policy=no-user-gesture-required', 'about:blank'], { stdio: 'ignore' });
  for (let i = 0; i < 160; i++) {
    try {
      const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(t => t.type === 'page');
      const ws = new WebSocket(page.webSocketDebuggerUrl);
      await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
      return { proc, ws, profile };
    } catch { await sleep(250); }
  }
  killTree(proc);
  return null;
}

export async function launch() {
  const started = (await startBrowser()) || (await startBrowser());  // one retry
  if (!started) throw new Error('Could not start a headless browser');
  const { proc, ws, profile } = started;

  let id = 0;
  const pending = new Map();
  const errors = [];
  ws.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
    if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  });
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async expr => {
    const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description || 'evaluation failed');
    return r.result?.result?.value;
  };

  await send('Runtime.enable');
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  // Install the fetch shim before any page script runs, on every navigation
  await send('Page.addScriptToEvaluateOnNewDocument', { source: SHIM });

  const waitFor = async (expr, timeoutMs = 20000) => {
    const end = Date.now() + timeoutMs;
    while (Date.now() < end) { if (await ev(`!!(${expr})`).catch(() => false)) return true; await sleep(300); }
    return false;
  };
  const go = async (hash, readyExpr, timeoutMs) => {
    await ev(`location.hash = ${JSON.stringify(hash)}`);
    await sleep(300);
    return readyExpr ? waitFor(readyExpr, timeoutMs) : true;
  };
  const open = async (hash = '#/') => {
    await send('Page.navigate', { url: `${BASE}/${hash}` });
    return waitFor(`typeof state !== 'undefined' && document.querySelector('.page, .welcome, .empty')`);
  };
  const close = () => {
    try { ws.close(); } catch {}
    killTree(proc);
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
  };

  return { send, ev, waitFor, go, open, close, errors };
}

export async function api(p) {
  const r = await fetch(BASE + p);
  if (!r.ok) throw new Error(`${p}: HTTP ${r.status}`);
  return r.json();
}

export function reporter(suite) {
  const results = [];
  return {
    results,
    check(name, ok, detail = '') { results.push({ suite, name, ok: !!ok, detail }); },
    skip(name, why) { results.push({ suite, name, ok: true, skipped: true, detail: why }); },
  };
}
