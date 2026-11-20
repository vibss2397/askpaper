/* Paper Agent service worker (migration plan §5.5).
 * Shell (paths under /app): network-first so dev iterations are never stale,
 * falling back to cache when offline. API and everything else: network only.
 * Bump CACHE when the shell must hard-update for installed PWA users. */
"use strict";

const CACHE = "paper-agent-v1";
const SHELL = ["./", "./index.html", "./styles.css", "./app.js", "./sse.js", "./marked.min.js", "./manifest.json", "./icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches
      .open(CACHE)
      .then((c) => c.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname !== "/app" && !url.pathname.startsWith("/app/")) return; /* API: network only */

  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true }))
  );
});
