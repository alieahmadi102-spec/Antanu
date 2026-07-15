/* آنتانو — سرویس‌ورکر برای نصب‌پذیری و بارگذاری سریع‌تر (PWA) */
const CACHE = "antanu-v1";
const ASSETS = [
  "/static/style.css",
  "/static/app.js",
  "/static/fingerprint.js",
  "/static/logo.png",
  "/static/manifest.json",
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  // فقط منابع همین دامنه را مدیریت کن؛ CDN و سرویس‌های بیرونی دست‌نخورده بمانند
  if (url.origin !== location.origin) return;

  // مسیرهای پویا و محرمانه هرگز کش نمی‌شوند (چت، پنل، ورود، دانلود، اشتراک)
  if (/^\/(api|admin|login|logout|register|download|share)(\/|$)/.test(url.pathname)) return;

  // فایل‌های ثابت: اول از کش (سریع)، بعد شبکه
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(req, { ignoreSearch: true }).then(hit =>
        hit || fetch(req).then(res => {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
          return res;
        })
      )
    );
    return;
  }

  // ناوبری صفحات: اول شبکه، اگر آفلاین بودیم از کش
  e.respondWith(fetch(req).catch(() => caches.match(req, { ignoreSearch: true })));
});
