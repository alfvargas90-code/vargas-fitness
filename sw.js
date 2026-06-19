// sw.js — Layer 3: defense-in-depth cache busting (fitness dashboard).
//
// The load-bearing layer is the inline version check in index.html. This
// service worker is belt-and-suspenders: it guarantees fresh HTML/JS/JSON on
// every deploy via NETWORK-FIRST, while keeping big static assets (icons,
// images, fonts) CACHE-FIRST so the app still paints instantly and works
// offline. If this SW ever fails to register, the inline check still works.
//
// Cache names are namespaced with PREFIX so this dashboard's activate cleanup
// never deletes the sibling (timing-weather) dashboard's cache, and vice versa.
const PREFIX = 'fitness';
const CACHE_NAME = PREFIX + '-static-v1';

const STATIC_RE = /\.(png|jpe?g|gif|svg|ico|webp|avif|woff2?|ttf|otf)$/i;

// Live per-day data — sync timestamps (polar/manifest.json), sleep/recharge/
// daily_activity, macro-fire + per-day state, nutrition, vesync, and the
// sibling astrology output. These must NEVER be served stale, so they bypass
// BOTH the SW cache and the browser HTTP cache (NetworkOnly + no-store).
// version.json (the deploy gate) and the PWA /manifest.json deliberately fall
// through to the cached paths below — they benefit from caching.
const LIVE_DATA_RE = /\/(polar|nutrition|vesync|timing-weather)\/.*\.(json|jsonl)$/i;

// Take over as soon as installed — no waiting for old tabs to close.
self.addEventListener('install', () => self.skipWaiting());

// On activate, drop any of THIS dashboard's old caches, then claim clients.
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((k) => k.startsWith(PREFIX + '-') && k !== CACHE_NAME)
        .map((k) => caches.delete(k))
    );
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  let url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return; // only manage same-origin

  if (LIVE_DATA_RE.test(url.pathname)) {
    // NetworkOnly + no-store — live data is never cached and never served
    // stale. no-store also bypasses the browser HTTP disk cache underneath.
    event.respondWith(fetch(req, { cache: 'no-store' }));
    return;
  }

  if (STATIC_RE.test(url.pathname)) {
    // Cache-first for static assets.
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      const hit = await cache.match(req);
      if (hit) return hit;
      try {
        const resp = await fetch(req);
        if (resp && resp.ok) cache.put(req, resp.clone());
        return resp;
      } catch (e) {
        return hit || Response.error();
      }
    })());
  } else {
    // Network-first for HTML / JS / JSON / everything dynamic.
    event.respondWith((async () => {
      try {
        const resp = await fetch(req);
        if (resp && resp.ok) {
          const cache = await caches.open(CACHE_NAME);
          cache.put(req, resp.clone());
        }
        return resp;
      } catch (e) {
        const cache = await caches.open(CACHE_NAME);
        const hit = await cache.match(req);
        return hit || Response.error();
      }
    })());
  }
});
