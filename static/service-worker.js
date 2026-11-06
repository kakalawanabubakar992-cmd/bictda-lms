/* =========================================================================
   BICTDA LMS - service worker (makes the app installable and auto-updating)

   VERSION is filled in by app.py every time the app is deployed (the Git commit
   on Render). A new version = a new service worker, so phones update by themselves.
   - Pages:          always from the network (newest version, no personal data cached).
                     If offline, OR if Render answers with its own "service waking up" page
                     (the free server was asleep), our BICTDA waiting page is shown instead.
                     It reloads by itself as soon as the app is ready.
   - Icons:          cache first (they rarely change).
   - CSS and JS:     network first, cached copy only when offline.
   ========================================================================= */
const VERSION = "__APP_VERSION__";
const CACHE = "bictda-lms-" + VERSION;
const OFFLINE_URL = "/static/offline.html";
const PRECACHE = [
  OFFLINE_URL,
  "/static/css/custom.css",
  "/static/js/app.js",
  "/static/icons/bictda-logo.png",
  "/static/icons/icon-192.png",
];

/* Install: save the offline page and core files, then take over straight away */
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

/* Activate: delete caches from older versions, then control all open pages */
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key.startsWith("bictda-lms-") && key !== CACHE).map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

/* Pages: a real BICTDA page (or a redirect) is shown as normal. Render's wake-up page
   (no X-BICTDA-App header) or no internet -> the BICTDA waiting page. */
function openPage(request) {
  return fetch(request)
    .then((response) => (response.type === "opaqueredirect" || response.headers.get("X-BICTDA-App")
      ? response : caches.match(OFFLINE_URL)))
    .catch(() => caches.match(OFFLINE_URL));
}

/* Fetch the file from the network and keep a copy in the cache */
function fetchAndCache(request) {
  return fetch(request).then((response) => {
    if (response.ok) {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(request, copy));
    }
    return response;
  });
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;   // forms and CDN files: browser handles them

  if (request.mode === "navigate") {                                  // pages: network first, waiting page as fallback
    event.respondWith(openPage(request));
  } else if (url.pathname.startsWith("/static/icons/")) {             // icons: cache first
    event.respondWith(caches.match(request).then((hit) => hit || fetchAndCache(request)));
  } else if (url.pathname.startsWith("/static/")) {                   // CSS / JS: network first
    event.respondWith(fetchAndCache(request).catch(() => caches.match(request)));
  }
});
