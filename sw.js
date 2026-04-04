const CACHE_NAME = 'uniserve-cache-v1';
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/manifest.json',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
        .then(cache => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cache => {
                    if (cache !== CACHE_NAME) {
                        return caches.delete(cache);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    // Network first for HTML and API requests to ensure fresh data
    if (event.request.mode === 'navigate' || event.request.url.includes('/api/')) {
        event.respondWith(
            fetch(event.request).catch(() => {
                return caches.match(event.request);
            })
        );
    } else {
        // Cache first for static assets
        event.respondWith(
            caches.match(event.request).then(response => {
                return response || fetch(event.request).then(fetchResponse => {
                    return caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, fetchResponse.clone());
                        return fetchResponse;
                    });
                });
            })
        );
    }
});
