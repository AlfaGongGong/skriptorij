/**
 * sw.js — Service Worker za Skriptorij V8 Turbo
 * Osnovna offline podrška i cache za statičke resurse.
 */

// PODIGNUTA VERZIJA: Ovo forsira brisanje starog keša i učitavanje novog app.js!
const CACHE_NAME = "skriptorij-v8-cache-v2";
const STATIC_ASSETS = [
    "/",
    "/static/css/style.css",
    "/static/js/app.js",
    "/static/manifest.json"
];

// Instaliraj SW i cacheiraj statičke resurse
self.addEventListener("install", event => {
    console.log("[SW] Instalacija nove verzije keša:", CACHE_NAME);
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(STATIC_ASSETS).catch(err => {
                console.warn(
                    "[SW] Neki resursi nisu dostupni za keširanje:",
                    err
                );
                // Nastavi čak i ako neki resursi nisu dostupni (offline install)
            });
        })
    );
    // Forsiraj da novi SW odmah preuzme kontrolu
    self.skipWaiting();
});

// Aktiviraj i obriši stare cache verzije
self.addEventListener("activate", event => {
    console.log("[SW] Aktivacija i čišćenje starih verzija...");
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

// Strategija: Network First, fallback na cache za GET zahtjeve
self.addEventListener("fetch", event => {
    // Ignoriraj API pozive i non-GET zahtjeve
    if (
        event.request.method !== "GET" ||
        event.request.url.includes("/api/") ||
        event.request.url.includes("/control/")
    ) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then(response => {
                // Cacheiraj uspješne odgovore za statičke resurse
                if (
                    response.ok &&
                    (event.request.url.includes("/static/") ||
                        event.request.url.endsWith("/"))
                ) {
                    const clone = response.clone();
                    caches
                        .open(CACHE_NAME)
                        .then(cache => cache.put(event.request, clone));
                }
                return response;
            })
            .catch(() => {
                console.log(
                    "[SW] Mreža nedostupna, vučem iz keša:",
                    event.request.url
                );
                // Fallback na cache ako je mreža nedostupna
                return caches.match(event.request);
            })
    );
});
