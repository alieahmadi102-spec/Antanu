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

# بازه‌های یونیکد برای تشخیص خط هر زبان (برای استخراج خودکار کلمات)
SCRIPT_RANGES = {
    "hy": (0x0530, 0x058F),   # ارمنی
}
LANG_NAMES = {"hy": "ارمنی"}

# الگوی کلمه‌ی ارمنی (حروف ارمنی، شامل عبارت‌های چندکلمه‌ای با فاصله)
_ARM_CHAR = "Ա-֏"
_ARM_WORD_RE = re.compile(f"[{_ARM_CHAR}]+(?:\\s+[{_ARM_CHAR}]+)*")


def seed_glossary_if_empty():
    """اگر واژه‌نامه‌ی ارمنی خالی بود، از فایل data/glossary_hy.tsv بارگذاری می‌شود."""
    db = get_db()
    try:
        n = db.execute("SELECT COUNT(*) AS c FROM glossary WHERE lang = 'hy'").fetchone()["c"]
        if n and n > 100:
            db.close()
            return 0
        path = os.path.join(_BASE, "data", "glossary_hy.tsv")
        if not os.path.exists(path):
            db.close()
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
                    "VALUES ('hy', ?, ?, ?, 'done', 'seed')",
                    (term, tr, pr),
                )
                count += 1
        db.commit()
        return count
    except Exception:
        return 0
    finally:
        try:
            db.close()
        except Exception:
            pass


def lookup_terms(terms, lang="hy"):
    """ترجمه‌ی مجموعه‌ای از کلمه‌ها را از واژه‌نامه برمی‌گرداند (فقط موارد موجود)."""
    if not terms:
        return []
    db = get_db()
    out = []
    try:
        for t in terms:
            row = db.execute(
                "SELECT term, translation, pronunciation FROM glossary "
                "WHERE lang = ? AND term = ? AND status = 'done'",
                (lang, t),
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
        seen, res = set(), []
        for w in found:
            w = w.strip()
            if w and w not in seen:
                seen.add(w)
                res.append(w)
        return res
    return []


def known_and_unknown(text, lang="hy"):
    """کلمه‌های متن را به «شناخته‌شده در واژه‌نامه» و «ناشناخته» تقسیم می‌کند."""
    words = extract_words(text, lang)
    if not words:
        return [], []
    db = get_db()
    known, unknown = [], []
    try:
        for w in words:
            row = db.execute(
                "SELECT term, translation, pronunciation, status FROM glossary WHERE lang = ? AND term = ?",
                (lang, w),
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


def prompt_hint_for_text(text):
    """اگر متن حاوی کلمه‌های زبان‌های واژه‌نامه‌ای باشد، یک راهنمای دقیق برای مدل می‌سازد
    تا از ترجمه‌های ثبت‌شده استفاده کند و خروجی سه‌ستونه بدهد."""
    hints = []
    for lang in SCRIPT_RANGES:
        known, unknown = known_and_unknown(text, lang)
        if not known and not unknown:
            continue
        lname = LANG_NAMES.get(lang, lang)
        block = [f"\n[واژه‌نامه‌ی {lname} آنتانو — هنگام ترجمه‌ی این کلمات، دقیقاً از همین ترجمه و تلفظ استفاده کن]:"]
        for k in known[:40]:
            block.append(f"- {k['term']} = {k['translation']} (تلفظ: {k['pronunciation']})")
        block.append(
            f"قاعده‌ی مهم ترجمه‌ی {lname}: هر ترجمه را در سه بخش بده — "
            "«کلمه‌ی اصلی»، «ترجمه‌ی فارسی»، «تلفظ فینگلیش (با حروف انگلیسی)». "
            "برای کلمه‌هایی که در واژه‌نامه‌ی بالا آمده‌اند، عیناً همان ترجمه و تلفظ را بنویس."
        )
        hints.append("\n".join(block))
    return "\n".join(hints)
