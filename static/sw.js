/**
 * sw.js — Service Worker za Skriptorij V8 Turbo
 * Osnovna offline podrška i cache za statičke resurse.
 */

const CACHE_NAME = 'skriptorij-v8-cache-v1';
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/manifest.json',
];

// Instaliraj SW i cacheiraj statičke resurse
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS).catch(() => {
                // Nastavi čak i ako neki resursi nisu dostupni (offline install)
            });
        })
    );
    self.skipWaiting();
});

// Aktiviraj i obriši stare cache verzije
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
    self.clients.claim();
});

// Strategija: Network First, fallback na cache za GET zahtjeve
self.addEventListener('fetch', (event) => {
    // Ignoriraj API pozive i non-GET zahtjeve
    if (
        event.request.method !== 'GET' ||
        event.request.url.includes('/api/') ||
        event.request.url.includes('/control/')
    ) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                // Cacheiraj uspješne odgovore za statičke resurse
                if (
                    response.ok &&
                    (event.request.url.includes('/static/') ||
                        event.request.url.endsWith('/'))
                ) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                }
                return response;
            })
            .catch(() => {
                // Fallback na cache ako je mreža nedostupna
                return caches.match(event.request);
            })
    );
});
