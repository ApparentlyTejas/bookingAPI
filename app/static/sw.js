// App-shell cache only. Every API call (auth/bookings/resources/admin) lives
// under different, non-/ui/ paths and is never intercepted here — booking
// data must always come from the network, never a stale cache. This service
// worker exists to satisfy PWA installability and give the static shell
// (HTML/icons/manifest) an offline fallback, nothing more.
const CACHE_NAME = "booking-api-shell-v1";
const SHELL_URLS = [
  "/ui/",
  "/ui/index.html",
  "/ui/admin.html",
  "/ui/manifest.json",
  "/ui/icon-192.png",
  "/ui/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_URLS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || !url.pathname.startsWith("/ui/")) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
