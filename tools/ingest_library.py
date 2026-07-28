# -*- coding: utf-8 -*-
"""
ingest_library.py — افزودن کتاب و جزوه به «کتابخانه‌ی دائمی آنتانو».

هر سندی (PDF، Word، PowerPoint، متن) را می‌گیرد، متنش را بیرون می‌کشد، به قطعه‌های
قابل‌جستجو می‌شکند و در data/knowledge/ ذخیره می‌کند. آنتانو با بالا آمدن بعدی،
خودش آن‌ها را در پایگاه داده بارگذاری می‌کند.

کاربرد:
    python tools/ingest_library.py  ~/my-books/            # یک پوشه
    python tools/ingest_library.py  book.pdf notes.docx    # چند فایل
    python tools/ingest_library.py  ~/books/ --ocr         # PDFهای اسکن‌شده هم OCR شوند

پیش‌نیاز برای OCR (فقط اگر PDF اسکن‌شده داری):
    apt-get install -y tesseract-ocr tesseract-ocr-fas poppler-utils
    pip install pypdf python-docx python-pptx

نکته: PDFهای اسکن‌شده لایه‌ی متنی ندارند و بدون --ocr نادیده گرفته می‌شوند.
OCR کند است (چند ثانیه برای هر صفحه)، پس برای کتاب‌های چندصد صفحه‌ای وقت بگذار.
"""
import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "data", "knowledge")

CHUNK = 1100          # نویسه در هر قطعه
OVERLAP = 150         # همپوشانی تا جمله وسط دو قطعه گم نشود
MIN_CHARS_PER_PAGE = 40

CATS = [
    ("روش تحقیق", ("روش تحقیق", "روش_تحقیق", "کیفی", "پرسشنامه", "پروپوزال",
                   "پرپوزل", "پوپوزال", "مصاحبه", "پژوهش")),
    ("آمار و اقتصادسنجی", ("اقتصاد سنجی", "اقتصاد_سنجی", "structural_equation",
                           "pls", "آماری", "گجراتی", "درخشان", "اقتصادسنجی")),
    ("حسابداری", ("حسابداری", "حسابدای", "حسابرسی", "بهای تمام شده", "صنعتی",
                  "معاملات فصلی", "hesabdari", "accounting")),
    ("مالیات", ("مالیات", "مالیاتی", "ارزش افزوه", "ارزش افزوده", "مودیان")),
    ("مدیریت و بازاریابی", ("بازاریابی", "بازرگانی", "bazaryabi", "مدیریت مالی",
                            "کسب و کار", "احکام", "مدیریت")),
]

_WORD_RE = re.compile(r"[آ-یءأإؤئA-Za-z]{2,}")
_FA_LETTERS = "آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیءأإؤئ"
_TOKEN_RE = re.compile(r"[^\s]+")


# ---------- پاک‌سازی و سنجش کیفیت ----------

def clean(text: str) -> str:
    """شکل‌های نمایشی عربی (ﻗﺎﻧﻮن) را به حرف پایه برمی‌گرداند و نویسه‌ها را یکدست می‌کند."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("ي", "ی").replace("ك", "ک")
    t = t.replace("‌", " ")
    t = re.sub(r"[‎‏‪-‮﻿]", "", t)
    t = re.sub(r"\.{4,}", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def text_is_usable(text: str):
    """آیا متن استخراج‌شده به درد جستجو می‌خورد؟ (بعضی PDFها واژه‌ها را به هم می‌چسبانند)"""
    body = re.sub(r"<<صفحه \d+>>", " ", text or "")
    toks = _TOKEN_RE.findall(body)
    if not toks:
        return False, "متن خالی"
    avg = sum(len(t) for t in toks) / len(toks)
    long_ratio = sum(1 for t in toks if len(t) > 18) / len(toks)
    if avg > 12 or long_ratio > 0.12:
        return False, "واژه‌ها به هم چسبیده‌اند (با --ocr دوباره امتحان کن)"
    if len(body.strip()) < 400:
        return False, "متن خیلی کوتاه"
    return True, "سالم"


def useful_chunk(piece: str) -> bool:
    """قطعه‌های زباله (فرمول‌های به‌هم‌ریخته، تکرار نویسه) را کنار می‌گذارد."""
    words = _WORD_RE.findall(piece)
    if len(words) < 12:
        return False
    if sum(len(w) for w in words) / max(len(piece), 1) < 0.45:
        return False
    if len(set(w.lower() for w in words)) < len(words) * 0.45:
        return False
    return True


# ---------- استخراج ----------

def _pdf_pages(path):
    import pypdf
    r = pypdf.PdfReader(path)
    out = []
    for i, pg in enumerate(r.pages, 1):
        try:
            out.append((i, clean(pg.extract_text() or "")))
        except Exception:
            out.append((i, ""))
    return out


def _ocr_page(img):
    m = re.search(r"(\d+)\.png$", os.path.basename(img))
    r = subprocess.run(["tesseract", img, "stdout", "-l", "fas+eng", "--psm", "6",
                        "-c", "preserve_interword_spaces=1"],
                       capture_output=True, text=True)
    return (int(m.group(1)) if m else 0), clean(r.stdout)


def _ocr_pdf(path, dpi=200, workers=None):
    from concurrent.futures import ProcessPoolExecutor
    import pypdf
    n = len(pypdf.PdfReader(path).pages)
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    pages = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for start in range(1, n + 1, 12):
            end = min(start + 11, n)
            with tempfile.TemporaryDirectory() as td:
                subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(start), "-l", str(end),
                                "-png", path, os.path.join(td, "p")],
                               check=False, capture_output=True)
                imgs = sorted(os.path.join(td, f) for f in os.listdir(td) if f.endswith(".png"))
                pages.extend(pool.map(_ocr_page, imgs))
            print(f"      OCR {end}/{n}", flush=True)
    pages.sort(key=lambda x: x[0])
    return pages


def _docx_pages(path):
    import docx
    d = docx.Document(path)
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return [(1, clean("\n".join(parts)))]


def _pptx_pages(path):
    from pptx import Presentation
    pr = Presentation(path)
    out = []
    for i, slide in enumerate(pr.slides, 1):
        buf = []
        for sh in slide.shapes:
            if sh.has_text_frame:
                buf.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                for row in sh.table.rows:
                    buf.append(" | ".join(c.text.strip() for c in row.cells))
        out.append((i, clean("\n".join(buf))))
    return out


def _txt_pages(path):
    for enc in ("utf-8", "cp1256", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                return [(1, clean(f.read()))]
        except (UnicodeDecodeError, OSError):
            continue
    return [(1, "")]


def extract(path, allow_ocr=False):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        pages = _pdf_pages(path)
        good = sum(1 for _, t in pages if len(t) >= MIN_CHARS_PER_PAGE)
        if good < max(1, len(pages) * 0.25):
            if not allow_ocr:
                return None, "اسکن‌شده است — با --ocr اجرا کن"
            print("    → لایه‌ی متنی ندارد، OCR فارسی…", flush=True)
            return _ocr_pdf(path), "ocr"
        return pages, "pdf"
    if ext == ".docx":
        return _docx_pages(path), "docx"
    if ext == ".pptx":
        return _pptx_pages(path), "pptx"
    if ext in (".txt", ".md"):
        return _txt_pages(path), "txt"
    return None, f"پسوند پشتیبانی‌نشده ({ext})"


# ---------- قطعه‌بندی و ذخیره ----------

def chunk(text):
    text = re.sub(r"\n{2,}", "\n\n", text).strip()
    out, i = [], 0
    while i < len(text):
        end = min(i + CHUNK, len(text))
        if end < len(text):
            w = text[i:end]
            cut = max(w.rfind("\n\n"), w.rfind("."), w.rfind("؟"), w.rfind("!"), w.rfind("\n"))
            if cut > CHUNK * 0.5:
                end = i + cut + 1
        piece = text[i:end].strip()
        if len(piece) >= 120 and useful_chunk(piece):
            out.append(piece)
        i = end - OVERLAP if end - OVERLAP > i else end
    return out


def categorize(name):
    low = name.lower()
    for cat, keys in CATS:
        if any(k.lower() in low for k in keys):
            return cat
    return "عمومی"


def slugify(name):
    return (re.sub(r"[^\w؀-ۿ-]+", "_", name).strip("_")[:70]) or "doc"


def ingest(path, allow_ocr=False):
    title = os.path.splitext(os.path.basename(path))[0]
    pages, kind = extract(path, allow_ocr)
    if pages is None:
        return 0, kind
    body = "\n".join(f"\n<<صفحه {n}>>\n{t}" for n, t in pages if t.strip())
    ok, why = text_is_usable(body)
    if not ok:
        return 0, why
    rows = []
    for n, t in pages:
        for piece in chunk(t):
            rows.append({"page": n, "text": piece})
    if not rows:
        return 0, "قطعه‌ی قابل‌استفاده‌ای نداشت"
    rows[0]["meta"] = {"title": title, "category": categorize(title),
                       "kind": kind, "pages": len(pages)}
    os.makedirs(OUT_DIR, exist_ok=True)
    dest = os.path.join(OUT_DIR, slugify(title) + ".jsonl.gz")
    with gzip.open(dest, "wt", encoding="utf-8", compresslevel=9) as g:
        for r in rows:
            g.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows), dest


def main():
    ap = argparse.ArgumentParser(description="افزودن سند به کتابخانه‌ی دائمی آنتانو")
    ap.add_argument("paths", nargs="+", help="فایل یا پوشه")
    ap.add_argument("--ocr", action="store_true",
                    help="PDFهای اسکن‌شده را با OCR فارسی بخوان (کند است)")
    args = ap.parse_args()

    files = []
    for p in args.paths:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                files += [os.path.join(root, n) for n in sorted(names)]
        elif os.path.isfile(p):
            files.append(p)
    files = [f for f in files
             if os.path.splitext(f)[1].lower() in (".pdf", ".docx", ".pptx", ".txt", ".md")]
    if not files:
        print("سندی پیدا نشد."); return 1

    total, added, skipped = 0, 0, []
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {os.path.basename(f)[:60]}", flush=True)
        try:
            n, info = ingest(f, args.ocr)
        except Exception as e:
            n, info = 0, f"{type(e).__name__}: {e}"
        if n:
            total += n; added += 1
            print(f"    ✔ {n} قطعه", flush=True)
        else:
            skipped.append((os.path.basename(f), info))
            print(f"    ✖ {info}", flush=True)

    print(f"\n{added} سند افزوده شد ({total} قطعه).")
    if skipped:
        print(f"{len(skipped)} سند افزوده نشد:")
        for name, why in skipped:
            print(f"   - {name[:55]}: {why}")
    print("\nحالا آنتانو را ری‌استارت کن تا کتابخانه بارگذاری شود:")
    print("   docker compose up -d --build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
