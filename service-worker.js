const CACHE_NAME = 'parkwise-v1';
const STATIC_ASSETS = [
  '/login',
  '/dashboard',
  '/vehicle',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

// Install: cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch: network first, fallback to cache
self.addEventListener('fetch', event => {
  // Skip non-GET and admin routes from caching
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('/admin')) return;

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Cache successful GET responses
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => {
        // Offline fallback: serve from cache
        return caches.match(event.request).then(cached => {
          if (cached) return cached;
          // Fallback page when offline and not cached
          return new Response(`
            <!DOCTYPE html>
            <html>
            <head>
              <meta charset="UTF-8"/>
              <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
              <title>Offline | ParkWise</title>
              <link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet"/>
              <style>
                body { background:#0d0f14; color:#e8eaf0; font-family:'DM Sans',sans-serif;
                  min-height:100vh; display:flex; align-items:center; justify-content:center;
                  flex-direction:column; text-align:center; padding:20px; }
                .icon { font-size:64px; margin-bottom:20px; }
                h1 { font-family:'Syne',sans-serif; font-size:24px; font-weight:800; margin-bottom:8px; }
                p { color:#6b7280; font-size:15px; margin-bottom:28px; }
                button { background:#f5c518; color:#0d0f14; border:none; border-radius:12px;
                  padding:14px 28px; font-family:'Syne',sans-serif; font-size:15px; font-weight:700;
                  cursor:pointer; }
              </style>
            </head>
            <body>
              <div class="icon">📡</div>
              <h1>You're Offline</h1>
              <p>Please check your internet connection<br/>and try again.</p>
              <button onclick="location.reload()">Try Again</button>
            </body>
            </html>
          `, { headers: { 'Content-Type': 'text/html' } });
        });
      })
  );
});
