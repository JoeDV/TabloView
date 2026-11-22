// Splash: TabloView's intro (static/splash.mp4, 3 s) the first time a browser opens a new version
// of TabloView, in PC view and TV view, while the page loads behind it (each start of the TV app
// got old fast). Served as /splash.js with the version filled in (app/main.py). Any click or key skips it (the key isn't
// passed on to the page). Left out where it can't play quickly, and for people who asked their
// device for less motion. Runs at the top of <body>, so the page never shows before it.
(() => {
  // PC view's address on a browser set to TV view: it goes straight on to /tv, which shows it
  try { if (location.pathname === '/' && localStorage.getItem('tv_view') === 'tv') return; } catch { /* shown here */ }
  const VERSION = '__APP_VERSION__';
  let seen = false;
  try {
    // (splash_off: the browser tests, which don't want it over the page)
    seen = localStorage.getItem('splash_version') === VERSION || sessionStorage.getItem('splash_off') === '1';
    localStorage.setItem('splash_version', VERSION);
  } catch { /* storage off: shown each load */ }
  if (seen || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const style = document.createElement('style');
  style.textContent = `
    #splash { position: fixed; inset: 0; z-index: 2147483000; display: flex; align-items: center; justify-content: center;
      background: #081013; transition: opacity 0.45s ease; cursor: pointer; }
    #splash.gone { opacity: 0; pointer-events: none; }
    #splash video { width: min(720px, 92vw); height: auto; aspect-ratio: 16 / 9;
      -webkit-mask-image: radial-gradient(ellipse at center, #000 52%, transparent 72%);
      mask-image: radial-gradient(ellipse at center, #000 52%, transparent 72%); }`;
  document.head.appendChild(style);
  const el = document.createElement('div');
  el.id = 'splash';
  el.innerHTML = '<video src="/static/splash.mp4?v=1" muted playsinline autoplay preload="auto" aria-hidden="true"></video>';
  document.body.prepend(el);
  const video = el.querySelector('video');

  let done = false;
  const finish = (wait = 0) => {
    if (done) return;
    done = true;
    document.removeEventListener('keydown', onKey, true);
    setTimeout(() => {
      el.classList.add('gone');
      setTimeout(() => el.remove(), 500);
    }, wait);
  };
  const onKey = e => { e.preventDefault(); e.stopPropagation(); finish(); };
  document.addEventListener('keydown', onKey, true);
  el.addEventListener('click', () => finish());
  video.addEventListener('ended', () => finish(400));  // (a moment on the logo)
  video.addEventListener('error', () => finish());
  const started = video.play();
  if (started && started.catch) started.catch(() => finish());  // autoplay refused
  // Slow to arrive (a TV stick, or away from home): don't hold the page up for it
  setTimeout(() => { if (video.currentTime === 0) finish(); }, 1500);
  setTimeout(() => finish(), 6000);
})();
