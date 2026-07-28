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
SCRIPT_RANGES = {
    "hy": (0x0530, 0x058F),   # ارمنی
}
LANG_NAMES = {
    "hy": "ارمنی", "en": "انگلیسی", "ru": "روسی", "hi": "هندی", "zh": "چینی",
    "ar": "عربی", "de": "آلمانی", "fr": "فرانسوی", "it": "ایتالیایی",
}

# زبان‌هایی که خطشان یکتاست و می‌شود خودکار در متن تشخیصشان داد.
# آلمانی/فرانسوی/ایتالیایی خط لاتین دارند و با انگلیسی اشتباه می‌شوند؛
# برای آن‌ها فقط وقتی راهنما می‌دهیم که صفحه‌ی ترجمه صراحتاً بخواهد (force_langs).
HINT_LANGS = ("hy", "ru", "hi", "zh", "ar", "en")

# همه‌ی زبان‌هایی که واژه‌نامه‌ی ذخیره‌شده دارند
GLOSSARY_LANGS = ("hy", "en", "ru", "hi", "zh", "ar", "de", "fr", "it")

# فایل‌های اولیه‌ی هر زبان
_SEED_FILES = {lang: f"glossary_{lang}.tsv" for lang in GLOSSARY_LANGS}

# الگوهای واژه بر اساس خط هر زبان
_ARM_CHAR = "Ա-֏"
_ARM_WORD_RE = re.compile(f"[{_ARM_CHAR}]+(?:\\s+[{_ARM_CHAR}]+)*")
_EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_FA_WORD_RE = re.compile(r"[آ-یءئؤإأ]{2,}")
_RU_WORD_RE = re.compile(r"[А-Яа-яЁё]{2,}(?:\s+[А-Яа-яЁё]{2,})*")
_HI_WORD_RE = re.compile(r"[ऀ-ॿ]+(?:\s+[ऀ-ॿ]+)*")
_AR_WORD_RE = re.compile(r"[ء-ي]{2,}(?:\s+[ء-ي]{2,})*")
_ZH_RUN_RE = re.compile(r"[一-鿿]+")
# لاتینِ لهجه‌دار برای آلمانی/فرانسوی/ایتالیایی
_LATIN_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'\-]+")

_WORD_RES = {
    "hy": _ARM_WORD_RE, "en": _EN_WORD_RE, "ru": _RU_WORD_RE,
    "hi": _HI_WORD_RE, "ar": _AR_WORD_RE,
    "de": _LATIN_WORD_RE, "fr": _LATIN_WORD_RE, "it": _LATIN_WORD_RE,
}
# نشانه‌های «درخواست ترجمه/معنی» — تا راهنمای انگلیسی فقط وقتی لازم است تزریق شود
_TRANSLATE_CUES = (
    "ترجمه", "معنی", "معنا", "معادل", "برگردان", "به فارسی", "به انگلیسی",
    "به ارمنی", "به روسی", "به هندی", "به چینی", "به عربی", "به آلمانی",
    "به فرانسوی", "به ایتالیایی", "دیکشنری", "واژه", "translate", "meaning",
)


def _seed_lang(db, lang):
    """یک زبان را از فایل TSV بارگذاری می‌کند و تعداد افزوده‌شده را برمی‌گرداند.

    اگر تعداد مدخل‌های دیتابیس کمتر از سطرهای فایل باشد یعنی فایل تازه یا کامل‌تر شده،
    پس دوباره خوانده می‌شود. تکراری‌ها با INSERT OR IGNORE رد می‌شوند، بنابراین
    واژه‌های ثبت‌شده‌ی قبلی (و ویرایش‌های دستی) دست‌نخورده می‌مانند.
    """
    fname = _SEED_FILES.get(lang)
    if not fname:
        return 0
    path = os.path.join(_BASE, "data", fname)
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            file_rows = sum(1 for line in f if line.strip())
    except OSError:
        return 0
    have = db.execute("SELECT COUNT(*) AS c FROM glossary WHERE lang = ?", (lang,)).fetchone()["c"]
    if have >= file_rows:
        return 0                      # از قبل کامل بارگذاری شده
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
    """همه‌ی واژه‌نامه‌های data/glossary_*.tsv را در صورت نیاز بارگذاری می‌کند.
    افزودن زبان تازه: کافی است فایل TSV را بگذاری و کد زبان را به GLOSSARY_LANGS اضافه کنی."""
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
    text = text or ""
    if lang == "zh":
        # چینی فاصله ندارد؛ هر رشته‌ی پیوسته را به پنجره‌های ۱ تا ۴ نویسه‌ای می‌شکنیم
        # تا واژه‌های واژه‌نامه در آن پیدا شوند (سقف دارد تا کند نشود).
        found = []
        for run in _ZH_RUN_RE.findall(text):
            found.append(run)
            for size in (4, 3, 2, 1):
                for i in range(len(run) - size + 1):
                    found.append(run[i:i + size])
                    if len(found) > 400:
                        break
                if len(found) > 400:
                    break
    else:
        rx = _WORD_RES.get(lang)
        if not rx:
            return []
        # الگوها عبارت‌های چندکلمه‌ای را هم می‌گیرند (مثل «كتاب الجيب»)؛
        # ولی تک‌کلمه‌ها را هم جدا می‌کنیم وگرنه یک جمله‌ی کامل می‌شود «یک واژه» و هیچ‌وقت پیدا نمی‌شود.
        found = []
        for run in rx.findall(text):
            found.append(run)
            if " " in run:
                found.extend(run.split())
        if lang in ("en", "de", "fr", "it"):
            found = [w.lower() for w in found]
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
    caps = {"hy": 40, "en": 15, "ru": 25, "hi": 25, "zh": 25, "ar": 20,
            "de": 20, "fr": 20, "it": 20}
    hints = []
    # زبان‌های خودکار + هر زبانی که صفحه‌ی ترجمه صراحتاً خواسته (مثل آلمانی/فرانسوی/ایتالیایی)
    langs = list(HINT_LANGS) + [l for l in force_langs if l in GLOSSARY_LANGS and l not in HINT_LANGS]
    for lang in langs:
        words = extract_words(text, lang)
        if not words:
            continue
        # انگلیسی در متن فارسی زیاد پیدا می‌شود. برای اینکه چت عادی شلوغ نشود، راهنمای انگلیسی فقط وقتی
        # تزریق می‌شود که: صفحه‌ی ترجمه آن را اجبار کند، یا «واژه‌ی نشانه‌ی ترجمه» باشد (معنی/translate…)،
        # یا پیام عملاً از خودِ واژه‌های انگلیسی تشکیل شده باشد (کمتر از ۳ واژه‌ی فارسی) — یعنی پرسشِ معنی.
        if (lang in ("en", "ar") and lang not in force_langs
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
            f"برای کلمه‌های {lname}ِ بالا، عیناً همان ترجمه و همان تلفظ ثبت‌شده را به کار ببر. "
            "توجه: تلفظِ نوشته‌شده در واژه‌نامه، تلفظِ خودِ واژه‌ی همان زبان است — "
            "پس هر جا تلفظ می‌دهی، تلفظِ واژه‌ی زبان مقصد باشد، نه تلفظِ معنیِ فارسی."
        )
        hints.append("\n".join(block))
    return "\n".join(hints)
