# -*- coding: utf-8 -*-
"""
knowledge_base.py — «کتابخانه‌ی دائمی آنتانو».

متنِ کتاب‌ها، جزوه‌ها، مقاله‌ها و پروپوزال‌هایی که مالک سایت اضافه می‌کند اینجا
نگه داشته می‌شود تا آنتانو هنگام مقاله‌نویسی و پاسخ‌دادن از آن‌ها استفاده کند.

مثل واژه‌نامه (glossary.py) کار می‌کند:
  • داده‌ها به‌صورت فایل‌های فشرده در data/knowledge/*.jsonl.gz کنار پروژه‌اند،
    پس با هر دیپلوی همراه پروژه می‌آیند و هیچ‌وقت گم نمی‌شوند.
  • هنگام بالا آمدن سرور، اگر چیزی در پایگاه داده کم باشد، از همان فایل‌ها پر می‌شود.
    این کار idempotent است: اجرای دوباره چیزی را تکراری یا خراب نمی‌کند.

جستجو با FTS5 پایگاه داده انجام می‌شود (سریع، بدون نیاز به سرویس بیرونی).

افزودن سند تازه: فایل jsonl.gz تازه را در data/knowledge/ بگذار — همین.
"""
import glob
import gzip
import json
import os
import re
import unicodedata

from db import get_db

_BASE = os.path.dirname(os.path.abspath(__file__))
_KB_DIR = os.path.join(_BASE, "data", "knowledge")

# واژه‌های پرتکرار فارسی که در جستجو کمکی نمی‌کنند
_STOP = {
    "از", "به", "با", "در", "که", "را", "این", "آن", "های", "ها", "برای", "تا",
    "است", "بود", "شد", "شده", "می", "هم", "یا", "اگر", "چه", "چون", "هر",
    "یک", "دو", "کن", "کند", "کرد", "کردن", "دارد", "داشت", "باید", "نیز",
    "بر", "بین", "روی", "طور", "مورد", "همه", "بیشتر", "کمتر", "خود", "دیگر",
    "the", "and", "for", "with", "that", "this", "are", "was", "were", "from",
    "چیست", "چیه", "کدام", "چگونه", "چطور", "درباره", "راجع",
}

_FA_LETTERS = "آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیءأإؤئ"
_TOKEN_RE = re.compile(f"[{_FA_LETTERS}A-Za-z0-9]{{2,}}")


def normalize(text: str) -> str:
    """یکدست‌کردن متن فارسی: شکل‌های نمایشی عربی، ی/ک عربی، نیم‌فاصله و فاصله‌ها.

    بعضی PDFها حروف را به‌صورت «شکل نمایشی» (ﻗﺎﻧﻮن به‌جای قانون) بیرون می‌دهند؛
    NFKC آن‌ها را به حرفِ پایه برمی‌گرداند تا جستجو کار کند.
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("ي", "ی").replace("ك", "ک")
    t = t.replace("‌", " ")                       # نیم‌فاصله
    t = re.sub(r"[‎‏‪-‮﻿]", "", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


# ---------- ساختار جدول‌ها ----------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_sources (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    slug       TEXT UNIQUE NOT NULL,     -- نام فایل داده (برای بارگذاری idempotent)
    title      TEXT NOT NULL,            -- عنوان خواناسِ سند
    category   TEXT DEFAULT '',          -- حسابداری، روش تحقیق، …
    kind       TEXT DEFAULT '',          -- pdf | docx | pptx | ocr
    pages      INTEGER DEFAULT 0,
    chunks     INTEGER DEFAULT 0,
    added_at   TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks USING fts5(
    content,
    title,
    source_slug UNINDEXED,
    page        UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def init_kb(db=None):
    own = db is None
    db = db or get_db()
    try:
        db.executescript(_SCHEMA)
        db.commit()
    finally:
        if own:
            db.close()


# ---------- بارگذاری از فایل‌های داده ----------

def _data_files():
    return sorted(glob.glob(os.path.join(_KB_DIR, "*.jsonl.gz")))


def _seed_file(db, path) -> int:
    """یک فایل داده را در صورت نیاز بارگذاری می‌کند و تعداد قطعه‌های افزوده را می‌دهد.

    اگر تعداد قطعه‌های ثبت‌شده با تعداد سطرهای فایل برابر باشد، کاری نمی‌کند؛
    پس اجرای دوباره‌ی سرور هزینه‌ای ندارد و داده تکراری نمی‌شود.
    """
    slug = os.path.basename(path)[:-len(".jsonl.gz")]
    with gzip.open(path, "rt", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if not rows:
        return 0
    have = db.execute("SELECT chunks FROM kb_sources WHERE slug = ?", (slug,)).fetchone()
    real = db.execute("SELECT COUNT(*) AS c FROM kb_chunks WHERE source_slug = ?",
                      (slug,)).fetchone()["c"]
    # هر اختلافی (کم یا زیاد) یعنی فایل عوض شده؛ مقایسه‌ی «کمتر بودن» کافی نیست،
    # وگرنه وقتی نسخه‌ی تازه‌ی فایل کوچک‌تر شود، قطعه‌های قدیمی سرِ جایشان می‌مانند.
    if have and have["chunks"] == len(rows) and real == len(rows):
        return 0                                   # از قبل دقیقاً همین نسخه بارگذاری شده

    # اگر ناقص مانده بود، همان منبع را از نو می‌نویسیم تا نصفه‌کاره نماند
    db.execute("DELETE FROM kb_chunks WHERE source_slug = ?", (slug,))
    meta = rows[0].get("meta") or {}
    title = meta.get("title") or slug
    for r in rows:
        db.execute(
            "INSERT INTO kb_chunks (content, title, source_slug, page) VALUES (?, ?, ?, ?)",
            (r.get("text", ""), title, slug, r.get("page") or 0),
        )
    db.execute(
        "INSERT INTO kb_sources (slug, title, category, kind, pages, chunks) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(slug) DO UPDATE SET title=excluded.title, category=excluded.category, "
        "kind=excluded.kind, pages=excluded.pages, chunks=excluded.chunks",
        (slug, title, meta.get("category", ""), meta.get("kind", ""),
         meta.get("pages", 0), len(rows)),
    )
    return len(rows)


def seed_knowledge_if_needed() -> int:
    """همه‌ی فایل‌های data/knowledge/ را در صورت نیاز بارگذاری می‌کند."""
    if not os.path.isdir(_KB_DIR):
        return 0
    db = get_db()
    try:
        init_kb(db)
        total = 0
        for path in _data_files():
            try:
                total += _seed_file(db, path)
            except Exception:
                continue
        db.commit()
        return total
    except Exception:
        return 0
    finally:
        try:
            db.close()
        except Exception:
            pass


# ---------- جستجو ----------

def _fts_query(text: str) -> str:
    """پرسش کاربر را به عبارت جستجوی FTS5 تبدیل می‌کند."""
    toks = [t for t in _TOKEN_RE.findall(normalize(text).lower())
            if t not in _STOP and len(t) > 2]
    seen, out = set(), []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append('"' + t.replace('"', '') + '"')
        if len(out) >= 12:
            break
    return " OR ".join(out)


def search(query: str, limit: int = 5, max_chars: int = 1200):
    """مرتبط‌ترین بخش‌های کتابخانه را برمی‌گرداند: [{title, page, text}, …]"""
    q = _fts_query(query)
    if not q:
        return []
    try:
        db = get_db()
        try:
            rows = db.execute(
                "SELECT content, title, page, bm25(kb_chunks) AS rank "
                "FROM kb_chunks WHERE kb_chunks MATCH ? "
                "ORDER BY rank LIMIT ?",
                (q, limit),
            ).fetchall()
        finally:
            db.close()
    except Exception:
        return []
    out = []
    for r in rows:
        txt = (r["content"] or "").strip()
        out.append({"title": r["title"], "page": r["page"],
                    "text": txt[:max_chars]})
    return out


def context_for(query: str, limit: int = 4, budget: int = 4000) -> str:
    """متن آماده برای گذاشتن در پرامپت مدل. اگر چیزی پیدا نشد، رشته‌ی خالی."""
    hits = search(query, limit=limit)
    if not hits:
        return ""
    parts, used = [], 0
    for h in hits:
        piece = f"[{h['title']}" + (f" — صفحه {h['page']}]" if h["page"] else "]") + f"\n{h['text']}"
        if used + len(piece) > budget:
            break
        parts.append(piece)
        used += len(piece)
    if not parts:
        return ""
    return "\n\n".join(parts)


def stats() -> dict:
    """آمار کتابخانه برای پنل مدیریت."""
    try:
        db = get_db()
        try:
            init_kb(db)
            srcs = db.execute(
                "SELECT title, category, kind, pages, chunks FROM kb_sources "
                "ORDER BY chunks DESC"
            ).fetchall()
            n = db.execute("SELECT COUNT(*) AS c FROM kb_chunks").fetchone()["c"]
        finally:
            db.close()
        return {"sources": len(srcs), "chunks": n,
                "items": [dict(r) for r in srcs]}
    except Exception:
        return {"sources": 0, "chunks": 0, "items": []}
