#!/usr/bin/env python3
"""Build the LIVE timing-weather PWA index.html from the three-lens dashboard,
re-injecting the PWA shell (manifest, icons, apple metas, self-healing cache
buster + service-worker registration) preserved from the prior index.html."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
TW = os.path.dirname(HERE)                       # timing-weather/
SRC = os.path.join(HERE, "three-lens-dashboard.html")
OUT = os.path.join(TW, "index.html")

PWA = '''  <link rel="manifest" href="manifest.json" />
  <link rel="apple-touch-icon" href="apple-touch-icon.png" />
  <meta name="theme-color" content="#06070a" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="apple-mobile-web-app-title" content="Timing" />
  <!-- Self-healing cache buster + service worker (preserved from prior PWA; docs/cache-busting.md) -->
  <script>
(async () => {
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get('clear') === '1') {
      try { const dbs = (await indexedDB.databases?.()) || [];
            await Promise.all(dbs.map(db => indexedDB.deleteDatabase(db.name))); } catch (e) {}
      if ('caches' in window) { const keys = await caches.keys(); await Promise.all(keys.map(k => caches.delete(k))); }
      if ('serviceWorker' in navigator) { const regs = await navigator.serviceWorker.getRegistrations(); await Promise.all(regs.map(r => r.unregister())); }
      try { localStorage.clear(); sessionStorage.clear(); } catch (e) {}
      url.searchParams.delete('clear');
      window.location.replace(url.pathname + url.search + (url.search ? '&' : '?') + 't=' + Date.now());
      return;
    }
    const resp = await fetch('version.json?t=' + Date.now(), { cache: 'no-store' });
    if (!resp.ok) return;
    const remote = await resp.json();
    const local = localStorage.getItem('dashboard_version');
    if (local !== remote.version) {
      if ('caches' in window) { const keys = await caches.keys(); await Promise.all(keys.map(k => caches.delete(k))); }
      localStorage.setItem('dashboard_version', remote.version);
      if (local !== null) { window.location.reload(); return; }
    }
    if ('serviceWorker' in navigator) { try { await navigator.serviceWorker.register('sw.js'); } catch (e) {} }
  } catch (e) { /* never block load */ }
})();
  </script>
'''

html = open(SRC, encoding="utf-8").read()
html = html.replace("<title>Timing Weather · Three Lenses</title>",
                    "<title>Timing Weather</title>\n" + PWA, 1)
assert PWA.strip() in html, "PWA block injection failed"
open(OUT, "w", encoding="utf-8").write(html)
print("wrote", OUT, "(", len(html), "bytes )")
