/* SafetyCheck service worker: app-shell cache. Never caches API, streams or websockets. */
const VERSION = 'sc-v1.0.0';
const SHELL = [
  '/', '/offline.html', '/manifest.webmanifest',
  '/static/css/app.css', '/static/js/theme.js', '/static/js/app.js', '/static/js/ui.js',
  '/static/fonts/Vazirmatn-subset.woff2', '/static/icons/sprite.svg', '/static/icons/icon-192.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname === '/ws') return;

  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req).then((r) => { const copy = r.clone(); caches.open(VERSION).then((c) => c.put('/', copy)); return r; })
        .catch(() => caches.match('/').then((r) => r || caches.match('/offline.html'))));
    return;
  }
  if (url.pathname.startsWith('/static/')) {  // stale-while-revalidate
    e.respondWith(caches.open(VERSION).then(async (c) => {
      const hit = await c.match(req);
      const net = fetch(req).then((r) => { if (r.ok) c.put(req, r.clone()); return r; }).catch(() => hit);
      return hit || net;
    }));
  }
});
