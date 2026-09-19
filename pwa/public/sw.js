// Build replaces the version. Only this public, unpersonalized document is cached.
const CACHE = 'psychology-public-__BUILD_VERSION__';
const OFFLINE = '/offline.html';
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.add(new Request(OFFLINE, { cache: 'reload' }))));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('psychology-public-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  // API, mail proofs and all other requests remain network-only. No opaque responses.
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || event.request.mode !== 'navigate' || url.origin !== self.location.origin || url.pathname.startsWith('/web/')) return;
  event.respondWith(fetch(event.request).catch(async () => (await caches.open(CACHE)).match(OFFLINE)));
});
