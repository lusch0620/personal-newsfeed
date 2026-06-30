const CACHE = 'newsfeed-v1';
const BASE  = '/personal-newsfeed';

const PRECACHE = [
  BASE + '/',
  BASE + '/index.html',
  BASE + '/data/feeds.json',
  BASE + '/data/briefs.json',
];

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(PRECACHE))
      .catch(() => {})
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Skip non-GET and cross-origin (Cloudflare Worker, Gist API)
  if (e.request.method !== 'GET' || url.origin !== self.location.origin) return;

  const isData = url.pathname.endsWith('/data/feeds.json') ||
                 url.pathname.endsWith('/data/briefs.json');
  const isShell = url.pathname === BASE + '/' ||
                  url.pathname === BASE + '/index.html';

  if (isData || isShell) {
    // Network-first: fresh data when online, cached stale data when offline
    e.respondWith(
      fetch(e.request)
        .then(r => {
          caches.open(CACHE).then(c => c.put(e.request, r.clone()));
          return r;
        })
        .catch(() => caches.match(e.request))
    );
  } else {
    // Cache-first for everything else (icons, manifest)
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
        if (resp.ok) caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
        return resp;
      }))
    );
  }
});
