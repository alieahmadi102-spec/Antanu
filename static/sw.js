/* آنتانو — سرویس‌ورکر (PWA)
   استراتژی: «شبکه اول» برای فایل‌های ثابت تا هر آپدیت بلافاصله دیده شود؛
   کش فقط برای حالت آفلاین استفاده می‌شود. با هر تغییر نسخه، کش قدیمی پاک می‌شود. */
const CACHE = "antanu-v3";
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
  // فقط منابع همین دامنه؛ CDN و سرویس‌های بیرونی دست‌نخورده بمانند
  if (url.origin !== location.origin) return;

  // مسیرهای پویا و محرمانه هرگز کش نمی‌شوند (چت، پنل، ورود، دانلود، اشتراک)
  if (/^\/(api|admin|login|logout|register|guest|download|share)(\/|$)/.test(url.pathname)) return;

  // فایل‌های ثابت و صفحه‌ها: «شبکه اول» — همیشه تازه‌ترین نسخه؛ اگر آفلاین بودیم از کش
  e.respondWith(
    fetch(req)
      .then(res => {
        // فقط پاسخ‌های سالمِ همین دامنه را کش کن
        if (res && res.status === 200 && url.pathname.startsWith("/static/")) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: true }))
  );
});
