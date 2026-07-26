# -*- coding: utf-8 -*-
"""
router.py — «مسیریاب هوشمند مدل‌ها» در آنتانو.

کار این ماژول دو چیز است:
۱) از متن درخواست کاربر تشخیص می‌دهد که این پیام چه «نوع کاری» است
   (ترجمه، کدنویسی، آمار، مقاله بلند، دیدن عکس، پاسخ سریع و…).
۲) فهرست مدل‌های تنظیم‌شده را طوری مرتب می‌کند که مدلِ مناسبِ همان کار اول بیاید
   و بقیه پشت سرش بمانند تا اگر مدل اول خطا داد، خودکار به بعدی سوئیچ شود.

اگر مدیر هیچ «کار»ی به مدل‌ها نداده باشد، رفتار سیستم دقیقاً مثل قبل می‌ماند
(مدل اصلی اول، بعد بقیه) — پس هیچ تنظیم قبلی خراب نمی‌شود.
"""
import re

# کارهایی که می‌شود به یک مدل سپرد. کلید در دیتابیس ذخیره می‌شود، مقدار برای نمایش در پنل است.
ROLES = {
    "general":   "گفتگوی عمومی (پیش‌فرض)",
    "fast":      "پاسخ کوتاه و سریع",
    "translate": "ترجمه و زبان‌ها",
    "code":      "کدنویسی و رفع خطا",
    "stats":     "آمار، ریاضی و تحلیل داده",
    "article":   "مقاله و متن بلند پژوهشی",
    "vision":    "دیدن عکس و تحلیل فایل",
    "image":     "ساخت عکس",
    "video":     "ساخت ویدیو",
}

# ترتیب اولویت تشخیص: هرچه بالاتر، تخصصی‌تر. اولین موردی که بخورد برنده است.
_PRIORITY = ("image", "video", "vision", "translate", "code", "stats", "article", "fast", "general")

# ---------- الگوهای تشخیص نوع کار ----------

_CODE_RE = re.compile(
    r"(کد\s*(بنویس|بزن|بده|این)|کدنویسی|برنامه\s*بنویس|اسکریپت|تابع|فانکشن|دیباگ|"
    r"ارور|خطای?\s*(کد|برنامه|سینتکس)|باگ|کامپایل|دیتابیس|کوئری|"
    r"\bpython\b|\bjavascript\b|\bjava\b|\bsql\b|\bhtml\b|\bcss\b|\bapi\b|\bjson\b|"
    r"\breact\b|\bdjango\b|\bflask\b|\bnode\b|\bgit\b|\bdocker\b)",
    re.IGNORECASE,
)
_STATS_RE = re.compile(
    r"(آمار|رگرسیون|همبستگی|واریانس|کوواریانس|انحراف\s*معیار|میانگین|میانه|نما|"
    r"آزمون\s*(t|تی|فرض|کای|نرمال)|کای\s*دو|آنووا|anova|spss|eviews|smart\s*pls|"
    r"پایایی|آلفای\s*کرونباخ|میانجی|تعدیل‌?گر|معادلات\s*ساختاری|"
    r"ریاضی|معادله|محاسبه\s*کن|حل\s*کن|درصد\s*بگیر|احتمال)",
    re.IGNORECASE,
)
_ARTICLE_RE = re.compile(
    r"(مقاله|پایان\s*نامه|پایان‌نامه|پروپوزال|رساله|تحقیق|پژوهش|فصل\s*(اول|دوم|سوم|چهارم|پنجم)|"
    r"پیشینه|مبانی\s*نظری|چکیده|منابع|رفرنس|ارجاع|"
    r"متن\s*بلند|مفصل|به\s*طور\s*کامل|به‌طور\s*کامل|کامل\s*توضیح|تفصیلی|جامع)",
    re.IGNORECASE,
)
_LONG_HINT_RE = re.compile(r"(بنویس|تدوین|تألیف|تالیف|تهیه\s*کن|آماده\s*کن)")


def detect_task(message: str, has_images: bool = False, has_files: bool = False,
                is_translate: bool = False, kind: str = "chat") -> str:
    """نوع کار این پیام را برمی‌گرداند (یکی از کلیدهای ROLES).

    kind از خودِ آنتانو می‌آید (chat/image/video) و بالاترین اولویت را دارد،
    چون سهمیه هم بر همان اساس حساب شده است.
    """
    msg = (message or "").strip()

    if kind == "image":
        return "image"
    if kind == "video":
        return "video"
    if has_images:
        return "vision"
    if is_translate:
        return "translate"
    if not msg:
        return "general"

    # بلوک کد در پیام → قطعاً کار کدنویسی است
    if "```" in msg:
        return "code"
    if _CODE_RE.search(msg):
        return "code"
    if _STATS_RE.search(msg):
        return "stats"
    # مقاله: یا واژه‌های پژوهشی، یا درخواستِ نوشتنِ متنِ طولانی، یا پیام خیلی بلند با فایل
    if _ARTICLE_RE.search(msg) and _LONG_HINT_RE.search(msg):
        return "article"
    if _ARTICLE_RE.search(msg) and len(msg) > 40:
        return "article"
    if has_files and len(msg) > 120:
        return "article"
    # پیام کوتاه و ساده → مدل سریع
    if len(msg) <= 60 and not has_files:
        return "fast"
    return "general"


# ---------- مرتب‌سازی مدل‌ها بر اساس کار ----------

# اگر برای یک کار مدلِ اختصاصی تنظیم نشده باشد، این جانشین‌ها به‌ترتیب امتحان می‌شوند
_FALLBACK_ROLES = {
    "fast":      ("general",),
    "translate": ("general",),
    "code":      ("stats", "general"),
    "stats":     ("code", "general"),
    "article":   ("general",),
    "vision":    ("general",),
    "image":     ("general",),
    "video":     ("image", "general"),
    "general":   (),
}


def order_catalog(catalog, task: str):
    """فهرست مدل‌ها را برای این کار مرتب می‌کند: مناسب‌ترین اول، بعد جانشین‌ها، بعد بقیه.

    همیشه همه‌ی مدل‌ها در خروجی می‌مانند تا زنجیره‌ی failover قطع نشود.
    """
    if not catalog:
        return []
    entries = list(catalog)

    def role_of(c):
        return (c.get("role") or "").strip().lower()

    groups, seen = [], set()

    def take(pred):
        picked = []
        for c in entries:
            key = id(c)
            if key in seen or not pred(c):
                continue
            seen.add(key)
            picked.append(c)
        return picked

    # ۱) مدل‌هایی که مدیر دقیقاً برای همین کار تعیین کرده
    groups += take(lambda c: role_of(c) == task)
    # ۲) جانشین‌های منطقی همان کار
    for alt in _FALLBACK_ROLES.get(task, ()):
        groups += take(lambda c, a=alt: role_of(c) == a)
    # ۳) مدل اصلی «آنتانو (خودکار)» به‌عنوان تکیه‌گاه همیشگی
    groups += take(lambda c: c.get("id") == "auto")
    # ۴) مدل‌های بی‌نقش (تنظیمات قدیمی) و در آخر هر چیز باقی‌مانده
    groups += take(lambda c: not role_of(c))
    groups += take(lambda c: True)
    return groups


def role_label(role: str) -> str:
    return ROLES.get((role or "").strip().lower(), ROLES["general"])
