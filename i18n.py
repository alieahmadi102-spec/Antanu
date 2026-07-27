# -*- coding: utf-8 -*-
"""
i18n.py — چندزبانه‌سازی آنتانو.

زبان پیش‌فرض کل پروژه «انگلیسی» است و کاربر می‌تواند هر زبانی را انتخاب کند.
متن‌ها در پوشه‌ی locales/ به‌صورت JSON نگه داشته می‌شوند: locales/en.json، locales/fa.json …

افزودن زبان تازه (بدون دست‌زدن به کد):
  ۱) فایل locales/<code>.json را بساز و کلیدها را ترجمه کن
     (کلیدهای نبود‌ه، خودکار از انگلیسی پر می‌شوند؛ پس ترجمه‌ی ناقص هم مشکلی ندارد).
  ۲) یک سطر در LANGUAGES پایین اضافه کن با نام بومی زبان و جهت نوشتار.
  همین. زبان تازه فوراً در فهرست انتخاب زبانِ سایت ظاهر می‌شود.
"""
import json
import os
import threading

_BASE = os.path.dirname(os.path.abspath(__file__))
_LOCALES_DIR = os.path.join(_BASE, "locales")

DEFAULT_LANG = "en"

# ترتیب همین فهرست، ترتیب نمایش در منوی انتخاب زبان است.
LANGUAGES = {
    "en": {"native": "English",   "english": "English",  "dir": "ltr", "flag": "🇬🇧"},
    "fa": {"native": "فارسی",     "english": "Persian",  "dir": "rtl", "flag": "🇮🇷"},
    "ar": {"native": "العربية",   "english": "Arabic",   "dir": "rtl", "flag": "🇸🇦"},
    "hy": {"native": "Հայերեն",   "english": "Armenian", "dir": "ltr", "flag": "🇦🇲"},
    "zh": {"native": "中文",       "english": "Chinese",  "dir": "ltr", "flag": "🇨🇳"},
    "de": {"native": "Deutsch",   "english": "German",   "dir": "ltr", "flag": "🇩🇪"},
    "fr": {"native": "Français",  "english": "French",   "dir": "ltr", "flag": "🇫🇷"},
    "ja": {"native": "日本語",     "english": "Japanese", "dir": "ltr", "flag": "🇯🇵"},
    "ko": {"native": "한국어",     "english": "Korean",   "dir": "ltr", "flag": "🇰🇷"},
    "es": {"native": "Español",   "english": "Spanish",  "dir": "ltr", "flag": "🇪🇸"},
}

_cache = {}
_lock = threading.Lock()


def is_supported(lang) -> bool:
    return (lang or "") in LANGUAGES


def normalize(lang, fallback: str = DEFAULT_LANG) -> str:
    """کد زبان را تمیز می‌کند: «fa-IR» → «fa». اگر پشتیبانی نشود، زبان پیش‌فرض."""
    code = (lang or "").strip().lower().replace("_", "-")
    if not code:
        return fallback
    if code in LANGUAGES:
        return code
    short = code.split("-")[0]
    return short if short in LANGUAGES else fallback


def _load_file(lang: str) -> dict:
    path = os.path.join(_LOCALES_DIR, f"{lang}.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def catalog(lang: str) -> dict:
    """واژه‌نامه‌ی یک زبان — کلیدهای نبوده از انگلیسی پر می‌شوند."""
    lang = normalize(lang)
    with _lock:
        if lang in _cache:
            return _cache[lang]
    base = _load_file(DEFAULT_LANG)
    data = dict(base)
    if lang != DEFAULT_LANG:
        data.update({k: v for k, v in _load_file(lang).items() if isinstance(v, str) and v.strip()})
    with _lock:
        _cache[lang] = data
    return data


def reload_catalogs():
    """کش را خالی می‌کند (برای وقتی فایل ترجمه را دستی عوض کردی)."""
    with _lock:
        _cache.clear()


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """متن ترجمه‌شده‌ی یک کلید. اگر کلید نبود، خودِ کلید برگردانده می‌شود
    تا صفحه خالی نشود و جای ترجمه‌ی جامانده هم پیدا باشد."""
    text = catalog(lang).get(key)
    if text is None:
        text = catalog(DEFAULT_LANG).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def direction(lang: str) -> str:
    return LANGUAGES.get(normalize(lang), LANGUAGES[DEFAULT_LANG])["dir"]


def native_name(lang: str) -> str:
    return LANGUAGES.get(normalize(lang), LANGUAGES[DEFAULT_LANG])["native"]


def english_name(lang: str) -> str:
    return LANGUAGES.get(normalize(lang), LANGUAGES[DEFAULT_LANG])["english"]


def language_list():
    """فهرست زبان‌ها برای منوی انتخاب زبان: [{code, native, english, dir, flag}, …]"""
    return [{"code": c, **info} for c, info in LANGUAGES.items()]


def pick_from_header(accept_language: str) -> str:
    """از هدر Accept-Language مرورگر بهترین زبان پشتیبانی‌شده را حدس می‌زند."""
    if not accept_language:
        return DEFAULT_LANG
    best, best_q = DEFAULT_LANG, -1.0
    for part in accept_language.split(","):
        piece = part.strip()
        if not piece:
            continue
        code, _, params = piece.partition(";")
        q = 1.0
        if "q=" in params:
            try:
                q = float(params.split("q=", 1)[1])
            except ValueError:
                q = 1.0
        norm = normalize(code, fallback="")
        if norm and q > best_q:
            best, best_q = norm, q
    return best


def missing_keys(lang: str):
    """کلیدهایی که در این زبان ترجمه نشده‌اند (برای کنترل کیفیت ترجمه‌ها)."""
    en = set(_load_file(DEFAULT_LANG).keys())
    have = {k for k, v in _load_file(lang).items() if isinstance(v, str) and v.strip()}
    return sorted(en - have)
