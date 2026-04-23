/**
 * sw.js — Service Worker za Booklyfi Turbo Charged
 * ISPRAVLJENA VERZIJA: uklonjen duplikat koji je uzrokovao SyntaxError
 */

const CACHE_NAME = "booklyfi-cache-v3";
const STATIC_ASSETS = [
    "/",
    "/static/css/style.css",
    "/static/css/intro.css",
    "/static/js/app.js",
    "/static/js/api-client.js",
    "/static/manifest.json",
];

// Instaliraj SW i cacheiraj statičke resurse
self.addEventListener("install", event => {
    console.log("[SW] Instalacija:", CACHE_NAME);
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache =>
            cache.addAll(STATIC_ASSETS).catch(err =>
                console.warn("[SW] Neki resursi nisu keširani:", err)
            )
        )
    );
    self.skipWaiting();
});

// Aktiviraj i obriši stare cache verzije
self.addEventListener("activate", event => {
    console.log("[SW] Aktivacija, čišćenje starih keša...");
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys
                    .filter(key => key !== CACHE_NAME)
                    .map(key => {
                        console.log("[SW] Brišem stari keš:", key);
                        return caches.delete(key);
                    })
            )
        )
    );
    self.clients.claim();
});

// Network First, fallback na cache
self.addEventListener("fetch", event => {
    // Ignoriraj API pozive, control rute i non-GET zahtjeve
    if (
        event.request.method !== "GET" ||
        event.request.url.includes("/api/") ||
        event.request.url.includes("/control/") ||
        event.request.url.includes("/intro")
    ) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then(response => {
                if (
                    response.ok &&
                    (event.request.url.includes("/static/") ||
                        event.request.url.endsWith("/"))
                ) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache =>
                        cache.put(event.request, clone)
                    );
                }
                return response;
            })
            .catch(() => {
                console.log("[SW] Offline fallback:", event.request.url);
                return caches.match(event.request);
            })
    );
});
