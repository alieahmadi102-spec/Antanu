# -*- coding: utf-8 -*-
"""
help_docs.py — راهنمای چندزبانه‌ی آنتانو

فارسی و انگلیسیِ راهنما دستی نوشته شده‌اند (`help_docs/fa.md` و `help_docs/en.md`).
بقیه‌ی زبان‌ها یک‌بار با هوش مصنوعی ترجمه و در پایگاه‌داده انبار می‌شوند؛ از آن
به بعد بدون هیچ فراخوانی‌ای سرو می‌شوند. اگر متنِ راهنما را ویرایش کنی،
«اثرانگشتِ» فایل عوض می‌شود و ترجمه‌ها خودکار دوباره ساخته می‌شوند — پس هرگز
ترجمه‌ی کهنه نشان داده نمی‌شود.

راهنما بخش‌بخش (روی سرفصل‌های `##`) ترجمه می‌شود تا هر فراخوانی کوچک بماند و
شکستِ یک بخش، کلِ ترجمه را از بین نبرد.
"""
import hashlib
import os
import re

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "help_docs")

# زبان‌هایی که متنشان دستی نوشته شده و ترجمه‌ی ماشینی لازم ندارند
HAND_WRITTEN = ("fa", "en")

# نام هر زبان به انگلیسی — برای دستور ترجمه
LANG_NAMES = {
    "en": "English", "fa": "Persian (Farsi)", "ar": "Arabic", "hy": "Armenian",
    "zh": "Simplified Chinese", "de": "German", "fr": "French", "ja": "Japanese",
    "ko": "Korean", "es": "Spanish", "hi": "Hindi", "tr": "Turkish",
}

# اندازه‌ی تقریبی هر تکه برای ترجمه (نویسه) — کوچک نگه داشته می‌شود تا پاسخ بریده نشود
CHUNK_CHARS = 2600

SYSTEM = (
    "You are a professional technical translator localising software documentation. "
    "Translate faithfully and naturally into the target language. "
    "Output ONLY the translation — no preamble, no notes, no explanation."
)


def _read(lang: str) -> str:
    path = os.path.join(DIR, f"{lang}.md")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""
    return ""


def source_text(lang: str):
    """متن مبدأ برای یک زبان و اینکه واقعاً به کدام زبان است.

    برمی‌گرداند: (متن، زبانِ متن). برای زبان‌های بدون فایلِ دستی، انگلیسی مبدأ
    ترجمه است (نه فارسی) — چون مدل‌ها انگلیسی→X را بهتر از فارسی→X ترجمه می‌کنند.
    """
    txt = _read(lang)
    if txt:
        return txt, lang
    en = _read("en")
    if en:
        return en, "en"
    return _read("fa"), "fa"


def fingerprint() -> str:
    """اثرانگشت متن‌های دستی — با تغییرِ راهنما، ترجمه‌های انباری باطل می‌شوند."""
    h = hashlib.sha1()
    for lang in HAND_WRITTEN:
        h.update(_read(lang).encode("utf-8"))
    return h.hexdigest()[:12]


def cache_key(lang: str) -> str:
    return f"helpdoc:{lang}:{fingerprint()}"


def needs_translation(lang: str) -> bool:
    return lang not in HAND_WRITTEN and lang in LANG_NAMES


def split_chunks(md: str, size: int = CHUNK_CHARS):
    """شکستن راهنما روی سرفصل‌های سطح دو، بعد گروه‌بندی تا نزدیکِ اندازه‌ی هدف.

    مرزِ سرفصل انتخاب شده تا هیچ تکه‌ای وسط یک جمله یا وسط یک جدول نصف نشود.
    """
    parts = re.split(r"\n(?=## )", md)
    chunks, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > size:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + "\n" + p) if cur else p
    if cur.strip():
        chunks.append(cur)
    return chunks


def build_prompt(chunk: str, lang: str) -> str:
    name = LANG_NAMES.get(lang, lang)
    return (
        f"Translate the following Markdown documentation into {name}.\n\n"
        "Rules:\n"
        "- Keep the Markdown structure exactly: headings (#, ##, ###), lists, tables, "
        "bold/italic markers, blockquotes and code fences stay where they are.\n"
        "- Keep every emoji exactly as it is and in the same position.\n"
        "- Do NOT translate: product names (ANTANU, SPSS, EViews, SmartPLS, Word, PDF, Excel, "
        "PowerPoint, Crossref, OpenAlex, Telegram), software menu names shown in Latin script "
        "(Data View, Variable View, Analyze, Output Viewer, PLS Algorithm, Bootstrapping, "
        "Method, Sample, Included observations), statistical terms and abbreviations "
        "(ANOVA, MANOVA, ARIMA, VAR, VECM, GARCH, KMO, AVE, CR, HTMT, SRMR, APA, IEEE, DOI), "
        "keyboard shortcuts, URLs, @usernames, and text inside code fences.\n"
        "- Statistical method names may be translated, but keep the Latin term in parentheses "
        "the first time if that is normal in the target language.\n"
        "- Use the natural, idiomatic register of the target language for end-user documentation.\n"
        "- Write the translation only. Do not add or remove sections.\n\n"
        "--- DOCUMENT START ---\n"
        f"{chunk}\n"
        "--- DOCUMENT END ---"
    )


def clean_output(text: str) -> str:
    """حذفِ حرف‌های اضافه‌ای که بعضی مدل‌ها دور ترجمه می‌گذارند."""
    t = (text or "").strip()
    t = re.sub(r"^---\s*DOCUMENT (START|END)\s*---\s*", "", t)
    t = re.sub(r"\s*---\s*DOCUMENT END\s*---\s*$", "", t)
    # جعبه‌ی کدی که کل خروجی را در بر گرفته باشد
    m = re.fullmatch(r"```(?:markdown|md)?\s*\n(.*)\n```", t, re.DOTALL)
    if m:
        t = m.group(1)
    return t.strip()
