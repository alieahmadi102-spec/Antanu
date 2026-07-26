# -*- coding: utf-8 -*-
"""
glossary.py — «مغز واژگان» چندزبانه‌ی آنتانو.
واژه‌نامه‌ی ارمنی (و هر زبان دیگر) را در پایگاه داده نگه می‌دارد و هنگام ترجمه،
کلمه‌ی اصلی + ترجمه‌ی فارسی + تلفظ فینگلیش را برمی‌گرداند. کلمات ناشناخته‌ای که
کاربران به کار می‌برند به‌صورت خودکار استخراج و ثبت می‌شوند.
"""
import os
import re
from db import get_db

_BASE = os.path.dirname(os.path.abspath(__file__))

# بازه‌های یونیکد برای تشخیص خط هر زبان (برای استخراج خودکارِ واژه‌های ناشناخته)
# فقط زبان‌هایی که «یاد می‌گیریم» اینجا هستند؛ انگلیسی واژه‌نامه‌ی کاملِ ۱۰٬۰۰۰تایی دارد و نیازی به یادگیری خودکار ندارد.
SCRIPT_RANGES = {
    "hy": (0x0530, 0x058F),   # ارمنی
}
LANG_NAMES = {"hy": "ارمنی", "en": "انگلیسی"}

# زبان‌هایی که هنگام ترجمه از واژه‌نامه راهنما می‌گیرند
HINT_LANGS = ("hy", "en")

# فایل‌های اولیه‌ی هر زبان: (نام فایل، حداقل تعداد برای «پُر بودن»)
_SEED_FILES = {
    "hy": ("glossary_hy.tsv", 100),
    "en": ("glossary_en.tsv", 100),
}

# الگوی کلمه‌ی ارمنی (حروف ارمنی، شامل عبارت‌های چندکلمه‌ای با فاصله)
_ARM_CHAR = "Ա-֏"
_ARM_WORD_RE = re.compile(f"[{_ARM_CHAR}]+(?:\\s+[{_ARM_CHAR}]+)*")
# الگوی واژه‌ی انگلیسی و فارسی
_EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_FA_WORD_RE = re.compile(r"[آ-یءئؤإأ]{2,}")
# نشانه‌های «درخواست ترجمه/معنی» — تا راهنمای انگلیسی فقط وقتی لازم است تزریق شود
_TRANSLATE_CUES = (
    "ترجمه", "معنی", "معنا", "معادل", "برگردان", "به فارسی", "به انگلیسی",
    "به ارمنی", "دیکشنری", "واژه", "translate", "meaning",
)


def _seed_lang(db, lang):
    """یک زبان را در صورت خالی‌بودن از فایل TSV بارگذاری می‌کند و تعداد افزوده‌شده را برمی‌گرداند."""
    fname, min_count = _SEED_FILES.get(lang, (None, 100))
    if not fname:
        return 0
    n = db.execute("SELECT COUNT(*) AS c FROM glossary WHERE lang = ?", (lang,)).fetchone()["c"]
    if n and n > min_count:
        return 0
    path = os.path.join(_BASE, "data", fname)
    if not os.path.exists(path):
        return 0
    count = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2 or not parts[0].strip():
                continue
            term = parts[0].strip()
            tr = parts[1].strip() if len(parts) > 1 else ""
            pr = parts[2].strip() if len(parts) > 2 else ""
            db.execute(
                "INSERT OR IGNORE INTO glossary (lang, term, translation, pronunciation, status, source) "
                "VALUES (?, ?, ?, ?, 'done', 'seed')",
                (lang, term, tr, pr),
            )
            count += 1
    return count


def seed_glossary_if_empty():
    """واژه‌نامه‌های ارمنی و انگلیسی را در صورت خالی‌بودن از فایل‌های data/*.tsv بارگذاری می‌کند."""
    db = get_db()
    try:
        total = 0
        for lang in _SEED_FILES:
            total += _seed_lang(db, lang)
        db.commit()
        return total
    except Exception:
        return 0
    finally:
        try:
            db.close()
        except Exception:
            pass


def _variants(w):
    """گونه‌های حروف‌بزرگ/کوچکِ یک واژه برای تطبیق مقاوم (ارمنی Title-case، انگلیسی lowercase)."""
    w = (w or "").strip()
    out, seen = [], set()
    for v in (w, w.capitalize(), w.lower(), w.upper()):
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def lookup_terms(terms, lang="hy"):
    """ترجمه‌ی مجموعه‌ای از کلمه‌ها را از واژه‌نامه برمی‌گرداند (فقط موارد موجود)."""
    if not terms:
        return []
    db = get_db()
    out = []
    try:
        for t in terms:
            cand = _variants(t)
            ph = ",".join("?" * len(cand))
            row = db.execute(
                f"SELECT term, translation, pronunciation FROM glossary "
                f"WHERE lang = ? AND term IN ({ph}) AND status = 'done' LIMIT 1",
                (lang, *cand),
            ).fetchone()
            if row and row["translation"]:
                out.append({"term": row["term"], "translation": row["translation"],
                            "pronunciation": row["pronunciation"] or ""})
    finally:
        db.close()
    return out


def extract_words(text, lang="hy"):
    """همه‌ی کلمه‌های آن زبان را از متن استخراج می‌کند (بدون تکرار)."""
    if lang == "hy":
        found = _ARM_WORD_RE.findall(text or "")
    elif lang == "en":
        found = [w.lower() for w in _EN_WORD_RE.findall(text or "")]
    else:
        return []
    seen, res = set(), []
    for w in found:
        w = w.strip()
        if w and w not in seen:
            seen.add(w)
            res.append(w)
    return res


def known_and_unknown(text, lang="hy"):
    """کلمه‌های متن را به «شناخته‌شده در واژه‌نامه» و «ناشناخته» تقسیم می‌کند."""
    words = extract_words(text, lang)
    if not words:
        return [], []
    db = get_db()
    known, unknown = [], []
    try:
        for w in words:
            cand = _variants(w)
            ph = ",".join("?" * len(cand))
            row = db.execute(
                f"SELECT term, translation, pronunciation, status FROM glossary "
                f"WHERE lang = ? AND term IN ({ph}) LIMIT 1",
                (lang, *cand),
            ).fetchone()
            if row and row["status"] == "done" and row["translation"]:
                known.append({"term": row["term"], "translation": row["translation"],
                              "pronunciation": row["pronunciation"] or ""})
            elif not row:
                unknown.append(w)
    finally:
        db.close()
    return known, unknown


def add_term(term, translation, pronunciation="", lang="hy", source="auto", status="done"):
    """یک واژه را به واژه‌نامه اضافه یا به‌روزرسانی می‌کند."""
    if not term or not term.strip():
        return False
    db = get_db()
    try:
        db.execute(
            "INSERT INTO glossary (lang, term, translation, pronunciation, status, source) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(lang, term) DO UPDATE SET "
            "translation = CASE WHEN excluded.translation <> '' THEN excluded.translation ELSE glossary.translation END, "
            "pronunciation = CASE WHEN excluded.pronunciation <> '' THEN excluded.pronunciation ELSE glossary.pronunciation END, "
            "status = excluded.status",
            (lang, term.strip(), (translation or "").strip(), (pronunciation or "").strip(), status, source),
        )
        db.commit()
        return True
    except Exception:
        return False
    finally:
        db.close()


def glossary_stats():
    db = get_db()
    try:
        total = db.execute("SELECT COUNT(*) AS c FROM glossary").fetchone()["c"]
        pend = db.execute("SELECT COUNT(*) AS c FROM glossary WHERE status='pending'").fetchone()["c"]
        return {"total": total, "pending": pend}
    finally:
        db.close()


def prompt_hint_for_text(text, force_langs=()):
    """اگر متن حاوی کلمه‌های زبان‌های واژه‌نامه‌ای باشد، یک راهنمای دقیق برای مدل می‌سازد
    تا از ترجمه‌های ثبت‌شده استفاده کند و خروجی را در قالب [[TR: کلمه || ترجمه || تلفظ]] بدهد.
    force_langs: زبان‌هایی که (مثلاً در صفحه‌ی ترجمه) حتماً راهنما بگیرند، فارغ از گِیت."""
    text = text or ""
    force_langs = set(force_langs or ())
    has_cue = any(c in text for c in _TRANSLATE_CUES)
    fa_count = len(_FA_WORD_RE.findall(text))
    caps = {"hy": 40, "en": 15}
    hints = []
    for lang in HINT_LANGS:
        words = extract_words(text, lang)
        if not words:
            continue
        # انگلیسی در متن فارسی زیاد پیدا می‌شود. برای اینکه چت عادی شلوغ نشود، راهنمای انگلیسی فقط وقتی
        # تزریق می‌شود که: صفحه‌ی ترجمه آن را اجبار کند، یا «واژه‌ی نشانه‌ی ترجمه» باشد (معنی/translate…)،
        # یا پیام عملاً از خودِ واژه‌های انگلیسی تشکیل شده باشد (کمتر از ۳ واژه‌ی فارسی) — یعنی پرسشِ معنی.
        if (lang == "en" and lang not in force_langs
                and not (has_cue or fa_count <= 2)):
            continue
        known, unknown = known_and_unknown(text, lang)
        if not known:
            continue
        lname = LANG_NAMES.get(lang, lang)
        block = [f"\n[واژه‌نامه‌ی {lname} آنتانو — هنگام ترجمه‌ی این کلمات، دقیقاً از همین ترجمه و تلفظ استفاده کن]:"]
        for k in known[:caps.get(lang, 20)]:
            block.append(f"- {k['term']} = {k['translation']} (تلفظ: {k['pronunciation']})")
        block.append(
            f"قاعده‌ی مهم ترجمه‌ی {lname}: هر ترجمه را در قالب "
            "[[TR: کلمه‌ی اصلی || ترجمه‌ی فارسی || تلفظ فینگلیش]] بده. "
            "برای کلمه‌هایی که در واژه‌نامه‌ی بالا آمده‌اند، عیناً همان ترجمه و تلفظ را بنویس."
        )
        hints.append("\n".join(block))
    return "\n".join(hints)
