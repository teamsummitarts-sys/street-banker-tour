/* Street Banker service worker — conservative on purpose:
   static assets cache-first, pages always network (dashboards must
   never go stale), offline navigations get a friendly fallback.

   One exception, for the road: TOUR's Tour Home, My Day and Show Command
   pages are network-first with a cached fallback, so a schedule that was
   open an hour ago still opens in a venue basement with no signal. The
   copy is per-URL - query string included, because Show Command tabs and
   My Day dates live in the query - is whatever the server last sent that
   signed-in person, and is replaced on every successful load. */
var VERSION = "sb-v140";   /* design system v1 */
var PAGES = VERSION + "-tour";
var PRECACHE = ["/static/offline.html", "/static/img/streetbanker-logo.svg",
                "/static/img/icon-192.png", "/static/manifest.json"];
var TOUR_PAGE = /^\/tours\/[a-f0-9]{32}(\/my-day|\/shows\/[a-f0-9]{32})?$/;

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(VERSION).then(function (c) { return c.addAll(PRECACHE); })
    .then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== VERSION && k !== PAGES; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var url = new URL(e.request.url);
  if (e.request.mode === "navigate") {
    if (url.origin === location.origin && TOUR_PAGE.test(url.pathname)) {
      e.respondWith(fetch(e.request).then(function (resp) {
        if (resp.ok) {
          var copy = resp.clone();
          caches.open(PAGES).then(function (c) { c.put(e.request, copy); });
        }
        return resp;
      }).catch(function () {
        return caches.open(PAGES).then(function (c) { return c.match(e.request); })
          .then(function (hit) { return hit || caches.match("/static/offline.html"); });
      }));
      return;
    }
    e.respondWith(fetch(e.request).catch(function () {
      return caches.match("/static/offline.html");
    }));
    return;
  }
  if (url.origin === location.origin && url.pathname.indexOf("/static/") === 0) {
    e.respondWith(caches.open(VERSION).then(function (c) {
      return c.match(e.request).then(function (hit) {
        return hit || fetch(e.request).then(function (resp) {
          if (resp.ok) c.put(e.request, resp.clone());
          return resp;
        });
      });
    }));
  }
});
