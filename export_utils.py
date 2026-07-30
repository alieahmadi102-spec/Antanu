# -*- coding: utf-8 -*-
"""
export_utils.py — ساخت خروجی Word و PDF فارسی (راست‌به‌چپ) با فونت و سایز دلخواه
"""
import os
import re
import secrets

import i18n

# پوشه خروجی‌ها — اگر قابل نوشتن نبود (مثل Hugging Face) به /tmp می‌رود
_BASE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.environ.get("ANTANU_EXPORT_DIR", os.path.join(_BASE, "exports"))
try:
    os.makedirs(EXPORT_DIR, exist_ok=True)
    _t = os.path.join(EXPORT_DIR, ".w")
    open(_t, "w").close()
    os.remove(_t)
except Exception:
    EXPORT_DIR = "/tmp/antanu_exports"
    os.makedirs(EXPORT_DIR, exist_ok=True)

FONT_DIR = os.path.join(_BASE, "static", "fonts")
os.makedirs(FONT_DIR, exist_ok=True)
PDF_FONT_PATH = os.path.join(FONT_DIR, "Vazirmatn-Regular.ttf")
FONT_URLS = [
    "https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/ttf/Vazirmatn-Regular.ttf",
    "https://raw.githubusercontent.com/rastikerdar/vazirmatn/v33.003/fonts/ttf/Vazirmatn-Regular.ttf",
]


def ensure_pdf_font() -> str | None:
    """فونت فارسی برای PDF — اگر نبود، بار اول دانلود می‌شود"""
    if os.path.exists(PDF_FONT_PATH) and os.path.getsize(PDF_FONT_PATH) > 50_000:
        return PDF_FONT_PATH
    try:
        import httpx
        for url in FONT_URLS:
            try:
                r = httpx.get(url, timeout=30, follow_redirects=True)
                if r.status_code == 200 and len(r.content) > 50_000:
                    with open(PDF_FONT_PATH, "wb") as f:
                        f.write(r.content)
                    return PDF_FONT_PATH
            except Exception:
                continue
    except Exception:
        pass
    return None


# ---------------- تبدیل مارک‌داون ساده به بلوک‌ها ----------------

def _clean_md(line: str) -> str:
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    line = re.sub(r"[*_`]", "", line)
    return line.strip()


def _is_table_sep(line: str) -> bool:
    """خط جداکننده‌ی جدول مارک‌داون مثل | --- | :---: |"""
    s = line.strip()
    if "-" not in s or "|" not in s:
        return False
    return bool(re.fullmatch(r"[\s|:\-]+", s))


def _table_cells(line: str):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [_clean_md(c.strip()) for c in s.split("|")]


_ORD_WORDS = "اول|دوم|سوم|چهارم|پنجم|ششم|هفتم|هشتم|نهم|دهم|یازدهم|دوازدهم|سیزدهم"
_HEAD_NUM_RE = re.compile(r"^([۰-۹0-9]+([.\-)][۰-۹0-9]+){1,4})[.\-)]?\s+(.+)$")
_CHAPTER_RE = re.compile(r"^(فصل|بخش)\s+(" + _ORD_WORDS + r"|[۰-۹0-9]+)\b")
_META_TOC_RE = re.compile(r"^(فهرست\s+(مطالب|جداول|نمودار|شکل|علائم|اختصار|منابع)|پیوست‌?ها)")


def _strip_leading_number(s: str) -> str:
    out = re.sub(r"^[۰-۹0-9]+([.\-)][۰-۹0-9]+)*[.\-)]?\s*", "", s).strip()
    return out or s


def _trim_heading(t: str) -> str:
    """عنوان‌های خیلی بلند را کوتاه می‌کند (توضیح داخل پرانتزِ طولانی را حذف می‌کند)
    ولی معادل انگلیسی کوتاه را نگه می‌دارد تا سرفصل تمیز بماند."""
    t = t.strip()
    if len(t) <= 75:
        return t
    idx = t.find(" (")
    if idx == -1:
        idx = t.find(" (")
    if 3 < idx <= 75:
        return t[:idx].strip()
    return t[:73].rstrip() + "…"


def normalize_structure(text: str) -> str:
    """ساختار خروجی هوش مصنوعی را یکدست می‌کند تا فهرست کامل و شماره‌گذاری بدون تکرار شود:
    خطوط «فصل …» و خطوط شماره‌دار (۱-۱، ۱-۲-۳) به سرفصل مارک‌داون با سطح درست تبدیل می‌شوند،
    شماره‌های دستی حذف می‌شوند (آنتانو خودش یک‌بار شماره می‌زند) و «فهرست …» تکراری حذف می‌شود."""
    out = []
    for raw in (text or "").split("\n"):
        s = raw.strip()
        if not s:
            out.append("")
            continue
        if "|" in s and s.count("|") >= 2:   # خطوط جدول را دست نزن
            out.append(raw)
            continue
        mmd = re.match(r"^(#{1,6})\s+(.*)$", s)
        core = (mmd.group(2) if mmd else s).strip()
        core = re.sub(r"^\*\*(.+?)\*\*$", r"\1", core).strip()  # حذف بولد دور کل خط
        # ابتدا شماره‌ی ابتدای خط را جدا کن (چه شماره‌ی خود هوش مصنوعی، چه شماره‌ی قبلی آنتانو)
        mnum = _HEAD_NUM_RE.match(core)
        if mnum:
            n_parts = len(re.split(r"[.\-)]", mnum.group(1).rstrip(".-)")))
            body_txt = mnum.group(3).strip()
        else:
            n_parts, body_txt = None, core
        # «فهرست مطالب/جداول…» حذف می‌شود (آنتانو خودش فهرست می‌سازد)
        if _META_TOC_RE.match(body_txt):
            continue
        # عنوان فصل → سطح ۱
        if _CHAPTER_RE.match(body_txt) and len(body_txt) < 90:
            out.append("# " + _trim_heading(body_txt))
            continue
        # عنوان شماره‌دار (۲ بخش به بالا) → سطح بر اساس تعداد بخش‌ها
        if n_parts and n_parts >= 2 and len(body_txt) < 200:
            level = min(n_parts, 3)
            out.append("#" * level + " " + _trim_heading(body_txt))
            continue
        # سرفصل مارک‌داونِ بدون شماره را حفظ کن
        if mmd:
            out.append(mmd.group(1) + " " + body_txt)
            continue
        out.append(raw)
    return "\n".join(out)


def md_to_blocks(text: str):
    """('h1'|'h2'|'h3'|'li'|'p'|'table'|'footnotes', محتوا) — علامت‌های مارک‌داون حذف می‌شوند.
    پانوشت‌ها: تعریف با «[^شناسه]: متن» و ارجاع درون‌متنی با «[^شناسه]».
    برای 'table' محتوا فهرستی از ردیف‌هاست؛ برای 'footnotes' دیکشنری {شناسه: متن}."""
    blocks = []
    footnotes = {}
    lines = normalize_structure(text).split("\n")
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        line = raw.strip()

        # تعریف پانوشت:  [^۱]: توضیح اصطلاح
        mfn = re.match(r"^\[\^([^\]]+)\]:\s*(.+)$", line)
        if mfn:
            footnotes[mfn.group(1).strip()] = _clean_md(mfn.group(2).strip())
            i += 1
            continue

        # تشخیص جدول: خط دارای | و خط بعدی جداکننده‌ی --- باشد
        if "|" in line and i + 1 < n and _is_table_sep(lines[i + 1]):
            header = _table_cells(line)
            rows = [header]
            i += 2
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_table_cells(lines[i]))
                i += 1
            # هم‌طول‌سازی ستون‌ها
            ncol = max(len(r) for r in rows)
            rows = [r + [""] * (ncol - len(r)) for r in rows]
            blocks.append(("table", rows))
            continue

        if not line or line in ("---", "***"):
            i += 1
            continue
        line = _clean_md(line)
        if line.startswith("### "):
            blocks.append(("h3", line[4:].strip()))
        elif line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
        elif line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
        elif line.startswith("> "):
            blocks.append(("quote", _clean_md(line[2:])))
        elif re.match(r"^[-•]\s+", line):
            blocks.append(("li", re.sub(r"^[-•]\s+", "", line)))
        elif re.match(r"^\d+[.)]\s+", line):
            blocks.append(("li", re.sub(r"^\d+[.)]\s+", "", line)))
        else:
            blocks.append(("p", line))
        i += 1
    if footnotes:
        blocks.append(("footnotes", footnotes))
    return blocks


_FN_MARKER_RE = re.compile(r"\[\^([^\]]+)\]")


def _to_fa_digits_mod(s) -> str:
    # با وجود نامش، فقط برای خروجیِ فارسی به فارسی تبدیل می‌کند — زبان از
    # main.py با i18n.set_digit_lang() برای همین درخواست تعیین شده است.
    return i18n.to_local_digits(s)


# ---------------- ابزارهای فهرست دستی Word (عنوان … نقطه‌چین … شماره صفحه) ----------------

def compute_headings(blocks, numbering=True):
    """فهرست سرفصل‌ها را با شماره‌گذاری و نام نشانک (bookmark) از پیش محاسبه می‌کند.
    خروجی: [(bookmark, numbered_text, level), ...]"""
    HLEVEL = {"h1": 0, "h2": 1, "h3": 2}
    cnt = [0, 0, 0]
    heads = []
    hi = 0
    for kind, txt in blocks:
        lvl = HLEVEL.get(kind)
        if lvl is None:
            continue
        # هیچ سطح والدی نباید صفر بماند (جلوگیری از «۱-۰-۱»)
        for k in range(lvl):
            if cnt[k] == 0:
                cnt[k] = 1
        cnt[lvl] += 1
        for j in range(lvl + 1, 3):
            cnt[j] = 0
        is_chapter = bool(re.match(r"^\s*(فصل|بخش)\b", str(txt)))
        if numbering and not (lvl == 0 and is_chapter):
            num = "-".join(_to_fa_digits_mod(cnt[k]) for k in range(lvl + 1)) + "- "
        else:
            num = ""  # عنوان «فصل …» بدون پیشوند شماره (ولی شمارنده جلو می‌رود تا زیربخش‌ها درست شوند)
        heads.append((f"_Toc_ant_{hi}", num + str(txt), lvl))
        hi += 1
    return heads


def add_heading_bookmark(paragraph, name, bid):
    """نشانک (bookmark) دور یک پاراگراف سرفصل می‌گذارد تا شماره صفحه‌اش قابل ارجاع باشد."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bid))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bid))
    p_el = paragraph._p
    pPr = p_el.find(qn("w:pPr"))
    if pPr is not None:
        pPr.addnext(start)
    else:
        p_el.insert(0, start)
    p_el.append(end)


def estimate_heading_pages(blocks, numbering=True, cover=True, chars_per_line=88,
                           lines_per_page=26):
    """شماره صفحه‌ی تقریبی هر سرفصل را از روی حجم محتوا برآورد می‌کند (چون بدون
    رندر واقعی نمی‌توان صفحه‌بندی دقیق داشت). خروجی: فهرست اعداد هم‌ترتیب با سرفصل‌ها."""
    import math
    HLEVEL = {"h1": 0, "h2": 1, "h3": 2}
    heads = [1 for k, _ in blocks if k in HLEVEL]
    n_head = len(heads)
    toc_pages = max(1, math.ceil((n_head + 3) / lines_per_page))
    start_page = (1 if cover else 0) + toc_pages + 1  # کاور + صفحات فهرست + شروع بدنه

    def lines_of(kind, txt):
        if kind in HLEVEL:
            return 2  # سرفصل + فاصله
        if kind == "table":
            return len(txt) + 1 if isinstance(txt, list) else 2
        if kind == "footnotes":
            return 0
        s = str(txt)
        return max(1, math.ceil(len(s) / chars_per_line)) + 1

    pages = []
    cum = 0
    for kind, txt in blocks:
        if kind in HLEVEL:
            pages.append(start_page + cum // lines_per_page)
        cum += lines_of(kind, txt)
    return pages


def add_pageref_run(paragraph, bookmark_name, placeholder="۱"):
    """یک فیلد PAGEREF می‌سازد که شماره صفحه‌ی نشانک را نشان می‌دهد.
    placeholder = شماره‌ی تقریبیِ از پیش‌نوشته که در نمایشگرهای بدون به‌روزرسانی (موبایل) دیده می‌شود."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    run = paragraph.add_run()
    fb = OxmlElement("w:fldChar"); fb.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve")
    it.text = f" PAGEREF {bookmark_name} \\h "
    fs = OxmlElement("w:fldChar"); fs.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t"); t.text = str(placeholder)
    fe = OxmlElement("w:fldChar"); fe.set(qn("w:fldCharType"), "end")
    for x in (fb, it, fs, t, fe):
        run._r.append(x)
    return run


def set_dot_leader_tab(paragraph, position_cm=15.5):
    """یک ایست‌تب راست‌چین با نقطه‌چین می‌گذارد تا شماره صفحه در لبه‌ی مقابل بنشیند."""
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.shared import Cm
    paragraph.paragraph_format.tab_stops.add_tab_stop(
        Cm(position_cm), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)


def set_update_fields(doc):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    try:
        uf = OxmlElement("w:updateFields")
        uf.set(qn("w:val"), "true")
        doc.settings.element.append(uf)
    except Exception:
        pass


def _flatten_footnotes(blocks):
    """برای خروجی‌های غیر Word: نشانه‌های [^id] را به «(n)» تبدیل می‌کند و فهرست پانوشت‌ها را برمی‌گرداند."""
    fn_defs = {}
    for k, t in blocks:
        if k == "footnotes":
            fn_defs = t
    if not fn_defs:
        return [b for b in blocks if b[0] != "footnotes"], []
    order, num = [], {}

    def repl(text):
        def _r(m):
            fid = m.group(1).strip()
            if fid not in fn_defs:
                return ""
            if fid not in num:
                order.append(fid)
                num[fid] = len(order)
            return f"({_to_fa_digits_mod(num[fid])})"
        return _FN_MARKER_RE.sub(_r, str(text))

    new = []
    for k, t in blocks:
        if k == "footnotes":
            continue
        if k == "table":
            new.append((k, [[repl(c) for c in row] for row in t]))
        else:
            new.append((k, repl(t)))
    notes = [(num[f], fn_defs[f]) for f in order]
    return new, notes


def _new_name(ext: str) -> str:
    return f"antanu-{secrets.token_hex(6)}.{ext}"


def _inject_real_footnotes(docx_path: str, notes, font_name: str = "Vazirmatn",
                           font_size: float = 9, single_spacing: bool = True):
    """پاورقی‌های واقعیِ پایین صفحه را به یک فایل docxِ ازپیش‌ساخته اضافه می‌کند.
    notes: فهرست (شماره، متن) با شماره‌ی ۱..N. بدنه‌ی سند باید از قبل w:footnoteReference
    با همان شماره‌ها را داشته باشد.

    پیش‌فرض‌ها طبق قرارداد رایج پایان‌نامه‌های فارسی است: پاورقی سایز ۹ و
    فاصله‌ی خطوط تک (single) — جدا از فونت/سایز بدنه‌ی سند، چون پاورقی‌های
    واقعی امروز فقط در مسیر آکادمیک استفاده می‌شوند (اضافه‌کردن پاورقی به
    اصطلاحات تخصصی و ارجاع نویسندگان خارجی)."""
    import zipfile
    import shutil
    import re as _re
    from xml.sax.saxutils import escape
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    sz = str(max(1, round(font_size * 2)))  # نیم‌نقطه (OOXML)
    spacing_xml = '<w:spacing w:line="240" w:lineRule="auto"/>' if single_spacing else ""

    def _note_xml(num, text):
        t = escape(text or "")
        return (
            f'<w:footnote w:id="{num}">'
            f'<w:p><w:pPr><w:pStyle w:val="FootnoteText"/><w:bidi/>{spacing_xml}'
            f'<w:rPr><w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/></w:rPr></w:pPr>'
            # ترتیب عنصرها داخل rPr باید دقیقاً طبق شِمای OOXML باشد (rFonts سپس
            # sz/szCs و در آخر vertAlign) — وگرنه Word باز می‌کند ولی LibreOffice
            # با خطای اعتبارسنجی، کل فایل را رد می‌کند.
            f'<w:r><w:rPr><w:rFonts w:ascii="{font_name}" w:hAnsi="{font_name}" w:cs="{font_name}"/>'
            f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/><w:vertAlign w:val="superscript"/></w:rPr><w:footnoteRef/></w:r>'
            f'<w:r><w:rPr><w:rFonts w:ascii="{font_name}" w:hAnsi="{font_name}" w:cs="{font_name}"/>'
            f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/><w:rtl/></w:rPr>'
            f'<w:t xml:space="preserve"> {t}</w:t></w:r></w:p></w:footnote>'
        )

    footnotes_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:footnotes xmlns:w="{W}">'
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
        '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
        + "".join(_note_xml(n, t) for n, t in notes)
        + '</w:footnotes>'
    )

    zin = zipfile.ZipFile(docx_path, "r")
    names = zin.namelist()
    ct = zin.read("[Content_Types].xml").decode("utf-8")
    rels = zin.read("word/_rels/document.xml.rels").decode("utf-8")

    if "footnotes+xml" not in ct:
        ct = ct.replace(
            "</Types>",
            '<Override PartName="/word/footnotes.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/></Types>',
        )
    if "relationships/footnotes" not in rels:
        nid = max((int(x) for x in _re.findall(r'Id="rId(\d+)"', rels)), default=0) + 1
        rels = rels.replace(
            "</Relationships>",
            f'<Relationship Id="rId{nid}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" '
            'Target="footnotes.xml"/></Relationships>',
        )

    tmp = docx_path + ".tmp"
    zout = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
    for n in names:
        data = zin.read(n)
        if n == "[Content_Types].xml":
            data = ct.encode("utf-8")
        elif n == "word/_rels/document.xml.rels":
            data = rels.encode("utf-8")
        zout.writestr(n, data)
    zout.writestr("word/footnotes.xml", footnotes_xml.encode("utf-8"))
    zout.close()
    zin.close()
    shutil.move(tmp, docx_path)


# ---------------- ساخت فایل Word (راست‌به‌چپ) ----------------

def _to_fa_digits(s) -> str:
    return i18n.to_local_digits(s)


def build_docx(blocks, font_name: str = "Vazirmatn", font_size: int = 14,
               title: str | None = None, align: str = "right",
               toc: bool = False, numbering: bool = False,
               real_footnotes: bool = False,
               footnote_font: str = "Times New Roman", footnote_size: float = 9,
               footnote_single_spacing: bool = True) -> str:
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    # همه‌ی پاراگراف‌ها w:bidi (راست‌به‌چپ) دارند. در پاراگراف RTL، مقدار
    # w:jc="right" به لبه‌ی «پایان» (فیزیکی چپ) و w:jc="left" به لبه‌ی «شروع»
    # (فیزیکی راست) نگاشت می‌شود. برای اینکه انتخاب کاربر «راست/چپ» دقیقاً همان
    # سمت فیزیکی نمایش داده شود، راست و چپ را جابه‌جا می‌کنیم.
    ALIGN_MAP = {"right": WD_ALIGN_PARAGRAPH.LEFT, "left": WD_ALIGN_PARAGRAPH.RIGHT,
                 "center": WD_ALIGN_PARAGRAPH.CENTER, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
    body_align = ALIGN_MAP.get(align, WD_ALIGN_PARAGRAPH.LEFT)

    def style_run(run, size, bold=False, color=None):
        run.font.name = font_name
        run.font.size = Pt(size)
        run.font.bold = bold
        if color:
            run.font.color.rgb = RGBColor(*color)
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rFonts.set(qn(attr), font_name)
        szCs = OxmlElement("w:szCs")
        szCs.set(qn("w:val"), str(int(size * 2)))
        rPr.append(szCs)
        rPr.append(OxmlElement("w:rtl"))

    def rtl_para(p, align=WD_ALIGN_PARAGRAPH.RIGHT, heading=False, level=None):
        p.alignment = align
        pf = p.paragraph_format
        pf.line_spacing = 1.5
        pf.space_after = Pt(8)
        if heading:
            pf.space_before = Pt(14)
            pf.space_after = Pt(6)
            pf.keep_with_next = True
        pPr = p._p.get_or_add_pPr()
        pPr.append(OxmlElement("w:bidi"))
        # سطح رئوس مطالب تا در فهرست خودکار (TOC) بیاید
        if level is not None:
            ol = OxmlElement("w:outlineLvl")
            ol.set(qn("w:val"), str(level))
            pPr.append(ol)

    # فهرست از پیش محاسبه‌شده (عنوان‌های شماره‌دار + نشانک)
    _heads = compute_headings(blocks, numbering) if (toc or numbering) else []

    _est_pages = estimate_heading_pages(blocks, numbering, cover=bool(title)) if (toc or numbering) else []

    def add_toc(heads):
        """فهرست مطالبِ آماده و چیده‌شده: عنوان (راست) … نقطه‌چین … شماره صفحه (چپ)"""
        from docx.shared import Pt as _Pt
        h = doc.add_paragraph()
        rtl_para(h, WD_ALIGN_PARAGRAPH.CENTER, heading=True)
        style_run(h.add_run("فهرست مطالب"), font_size + 6, bold=True, color=(0x0F, 0x76, 0x6E))
        for idx, (bm, text, lvl) in enumerate(heads):
            p = doc.add_paragraph()
            pPr = p._p.get_or_add_pPr()
            pPr.append(OxmlElement("w:bidi"))
            p.paragraph_format.space_after = _Pt(4)
            p.paragraph_format.right_indent = _Pt(lvl * 16)
            set_dot_leader_tab(p, 15.5)
            color = (0x0F, 0x76, 0x6E) if lvl == 0 else None
            style_run(p.add_run(text), font_size, bold=(lvl == 0), color=color)
            p.add_run("\t")
            est = _to_fa_digits(_est_pages[idx]) if idx < len(_est_pages) else "۱"
            style_run(add_pageref_run(p, bm, est), font_size, bold=(lvl == 0), color=color)
        doc.add_page_break()

    doc = Document()

    if title:
        p = doc.add_paragraph()
        rtl_para(p, WD_ALIGN_PARAGRAPH.CENTER)
        style_run(p.add_run(title), font_size + 10, bold=True, color=(0x0F, 0x76, 0x6E))

    if toc and _heads:
        add_toc(_heads)
        set_update_fields(doc)

    # آیتم‌های فهرست به‌ترتیب برای بدنه (نشانک + متن شماره‌دار یکسان با فهرست)
    _head_iter = iter(_heads)

    def add_table(rows):
        if not rows:
            return
        ncol = len(rows[0])
        tbl = doc.add_table(rows=len(rows), cols=ncol)
        tbl.style = "Table Grid"
        tbl.alignment = ALIGN_MAP.get("center", WD_ALIGN_PARAGRAPH.CENTER)
        # جدول راست‌به‌چپ
        tblPr = tbl._tbl.tblPr
        bidi = OxmlElement("w:bidiVisual")
        tblPr.append(bidi)
        for ri, row in enumerate(rows):
            for ci, val in enumerate(row):
                # با w:bidiVisual جدول به‌طور خودکار راست‌به‌چپ نمایش داده می‌شود؛
                # پس ستون‌ها را به‌ترتیب طبیعی پر می‌کنیم (بدون معکوس‌سازی دستی).
                cell = tbl.cell(ri, ci)
                cell.text = ""
                cp = cell.paragraphs[0]
                cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                pPr = cp._p.get_or_add_pPr()
                pPr.append(OxmlElement("w:bidi"))
                style_run(cp.add_run(_to_fa_digits_mod(str(val))), max(9, font_size - 2),
                          bold=(ri == 0), color=(0x0F, 0x76, 0x6E) if ri == 0 else None)
        doc.add_paragraph()

    # پانوشت‌ها: شماره‌گذاری به‌ترتیب اولین ظهور در متن
    fn_defs = {}
    for kind, txt in blocks:
        if kind == "footnotes":
            fn_defs = txt
    fn_order = []        # فهرست شناسه‌ها به‌ترتیب ظهور
    fn_num = {}          # شناسه → شماره

    def add_run_with_fn(p, text, size, bold=False, color=None, bullet=False):
        """متن را با تبدیل نشانه‌های [^id] به شماره‌ی بالانویسِ پانوشت درج می‌کند"""
        if bullet:
            text = "• " + text
        pos = 0
        for m in _FN_MARKER_RE.finditer(text):
            fid = m.group(1).strip()
            if fid not in fn_defs:
                continue
            before = text[pos:m.start()]
            if before:
                style_run(p.add_run(before), size, bold=bold, color=color)
            if fid not in fn_num:
                fn_order.append(fid)
                fn_num[fid] = len(fn_order)
            if real_footnotes:
                # ارجاع پاورقی واقعی (پایین صفحه) — به‌جای شماره‌ی بالانویسِ ساده
                run = p.add_run()
                rPr = run._element.get_or_add_rPr()
                va = OxmlElement("w:vertAlign"); va.set(qn("w:val"), "superscript"); rPr.append(va)
                ref = OxmlElement("w:footnoteReference"); ref.set(qn("w:id"), str(fn_num[fid]))
                run._element.append(ref)
            else:
                sup = p.add_run(_to_fa_digits(fn_num[fid]))
                style_run(sup, max(8, size - 3), bold=True, color=(0x0F, 0x76, 0x6E))
                sup.font.superscript = True
            pos = m.end()
        rest = text[pos:]
        if rest or pos == 0:
            style_run(p.add_run(rest), size, bold=bold, color=color)

    HLEVEL = {"h1": 0, "h2": 1, "h3": 2}
    _bid = [100]
    for kind, txt in blocks:
        if kind == "footnotes":
            continue
        if kind == "table":
            add_table(txt)
            continue
        lvl = HLEVEL.get(kind)
        p = doc.add_paragraph()
        rtl_para(p, body_align, heading=lvl is not None, level=lvl)
        bm = None
        if lvl is not None:
            he = next(_head_iter, None)
            if he:
                bm, txt, _ = he  # متن شماره‌دار یکسان با فهرست
        if kind == "h1":
            add_run_with_fn(p, txt, font_size + 8, bold=True, color=(0x0F, 0x76, 0x6E))
        elif kind == "h2":
            add_run_with_fn(p, txt, font_size + 4, bold=True, color=(0xB8, 0x86, 0x0B))
        elif kind == "h3":
            add_run_with_fn(p, txt, font_size + 2, bold=True)
        elif kind == "li":
            add_run_with_fn(p, txt, font_size, bullet=True)
        else:
            add_run_with_fn(p, txt, font_size)
        if bm:
            add_heading_bookmark(p, bm, _bid[0]); _bid[0] += 1

    # بخش پانوشت‌ها در انتهای سند (فقط در حالت غیرِ پاورقی‌واقعی)
    if fn_order and not real_footnotes:
        doc.add_paragraph()
        hp = doc.add_paragraph()
        rtl_para(hp, body_align, heading=True)
        style_run(hp.add_run("پانوشت‌ها"), font_size + 3, bold=True, color=(0x0F, 0x76, 0x6E))
        for fid in fn_order:
            np = doc.add_paragraph()
            rtl_para(np, body_align)
            style_run(np.add_run(f"{_to_fa_digits(fn_num[fid])}. "), max(9, font_size - 1),
                      bold=True, color=(0x0F, 0x76, 0x6E))
            style_run(np.add_run(fn_defs[fid]), max(9, font_size - 1))

    name = _new_name("docx")
    out_path = os.path.join(EXPORT_DIR, name)
    doc.save(out_path)

    # پاورقی واقعیِ پایین صفحه: تزریق word/footnotes.xml به فایل ذخیره‌شده
    if real_footnotes and fn_order:
        try:
            notes = [(fn_num[fid], fn_defs[fid]) for fid in fn_order]
            _inject_real_footnotes(out_path, notes, footnote_font, footnote_size,
                                   footnote_single_spacing)
        except Exception:
            pass

    return name


# ---------------- ساخت فایل PDF فارسی ----------------

def build_pdf(blocks, font_size: int = 14, title: str | None = None, align: str = "right"):
    """خروجی: (نام فایل، None) یا (None، پیام خطا)"""
    try:
        from fpdf import FPDF
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        return None, "برای PDF این کتابخانه‌ها لازم است: pip install fpdf2 arabic-reshaper python-bidi"

    font = ensure_pdf_font()
    if not font:
        return None, "فونت فارسی PDF دانلود نشد (اینترنت سرور را بررسی کنید) — فایل Word ساخته شد"

    def shape(t):
        try:
            return get_display(arabic_reshaper.reshape(t))
        except Exception:
            return t

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()
    pdf.add_font("Vazir", "", font)
    epw = pdf.w - pdf.l_margin - pdf.r_margin

    blocks, fn_notes = _flatten_footnotes(blocks)
    # شماره‌گذاری سرفصل‌ها هماهنگ با نسخه‌ی Word
    heads = compute_headings(blocks, numbering=True)
    _hi = iter(heads)

    def write_par(text, size, align_code="R"):
        """یک پاراگراف را می‌نویسد و همیشه مکان‌نما را به ابتدای خط برمی‌گرداند
        تا خطای «فضای افقی کافی نیست» رخ ندهد و محتوا ناقص نشود."""
        pdf.set_font("Vazir", size=size)
        # هر تکه‌ی متن که با \n جدا شده، جداگانه (برای جلوگیری از سرریز)
        for chunk in str(text).split("\n"):
            pdf.set_x(pdf.l_margin)          # ← رفع باگ ناقص شدن PDF
            try:
                pdf.multi_cell(epw, size * 0.72, shape(chunk), align=align_code)
            except Exception:
                # اگر باز هم فضای کافی نبود، واژه‌به‌واژه بشکن
                pdf.set_x(pdf.l_margin)
                try:
                    pdf.multi_cell(epw, size * 0.72, shape(chunk[:200]), align=align_code)
                except Exception:
                    pass

    def draw_table(rows):
        if not rows:
            return
        ncol = len(rows[0])
        cw = epw / ncol
        tsize = max(8, font_size - 3)
        lh = tsize * 1.1
        pdf.set_font("Vazir", size=tsize)
        for row in rows:
            disp = list(reversed(row))  # ستون‌ها راست‌به‌چپ
            if pdf.get_y() + lh > pdf.h - pdf.b_margin:
                pdf.add_page()
            pdf.set_x(pdf.l_margin)
            for val in disp:
                try:
                    pdf.cell(cw, lh, shape(_to_fa_digits_mod(str(val))), border=1, align="C")
                except Exception:
                    pdf.cell(cw, lh, "", border=1)
            pdf.ln(lh)
        pdf.ln(2)

    body_code = {"right": "R", "left": "L", "center": "C", "justify": "J"}.get(align, "R")

    if title:
        write_par(title, font_size + 8, "C")
        pdf.ln(3)

    for kind, txt in blocks:
        if kind == "footnotes":
            continue
        if kind == "table":
            draw_table(txt)
            continue
        if kind in ("h1", "h2", "h3"):
            he = next(_hi, None)
            if he:
                _, txt, _ = he
            size = font_size + (8 if kind == "h1" else 4 if kind == "h2" else 2)
            pdf.ln(2)
            write_par(txt, size, "R")
            pdf.ln(1)
        elif kind == "li":
            write_par("• " + txt, font_size, body_code)
        elif kind == "quote":
            write_par("❝ " + txt, font_size, body_code)
        else:
            write_par(txt, font_size, body_code)

    if fn_notes:
        pdf.ln(4)
        write_par("پانوشت‌ها", font_size + 1, "R")
        for num, note in fn_notes:
            write_par(f"{_to_fa_digits_mod(num)}. {note}", max(9, font_size - 2), "R")

    name = _new_name("pdf")
    pdf.output(os.path.join(EXPORT_DIR, name))
    return name, None


# ---------------- ساخت فایل Excel (راست‌به‌چپ) ----------------

def build_xlsx(blocks, font_name: str = "Vazirmatn", font_size: int = 14,
               title: str | None = None, align: str = "right") -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    blocks, fn_notes = _flatten_footnotes(blocks)
    if fn_notes:
        blocks = list(blocks) + [("h3", "پانوشت‌ها")] + \
            [("li", f"{_to_fa_digits_mod(n)}. {t}") for n, t in fn_notes]

    wb = Workbook()
    ws = wb.active
    ws.title = "آنتانو"
    ws.sheet_view.rightToLeft = True
    ws.column_dimensions["A"].width = 55

    from openpyxl.utils import get_column_letter

    xl_align = Alignment(
        horizontal={"right": "right", "left": "left", "center": "center",
                    "justify": "justify"}.get(align, "right"),
        vertical="top", wrap_text=True,
    )
    row = 1

    def put(text, size, bold=False, color="1F2937", fill=None):
        nonlocal row
        cell = ws.cell(row=row, column=1, value=text)
        cell.font = Font(name=font_name, size=size, bold=bold, color=color)
        cell.alignment = xl_align if not (fill and title) else Alignment(horizontal="center", vertical="center", wrap_text=True)
        if fill:
            cell.fill = PatternFill(start_color=fill, end_color=fill, fill_type="solid")
        row += 1

    if title:
        cell = ws.cell(row=row, column=1, value=title)
        cell.font = Font(name=font_name, size=font_size + 8, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
        row += 2

    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def put_table(rows):
        nonlocal row
        ncol = len(rows[0])
        for ri, r in enumerate(rows):
            for ci, val in enumerate(r):
                cell = ws.cell(row=row, column=ci + 1, value=val)
                cell.font = Font(name=font_name, size=max(9, font_size - 2), bold=(ri == 0),
                                 color="FFFFFF" if ri == 0 else "1F2937")
                cell.alignment = center
                if ri == 0:
                    cell.fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
            row += 1
        # عرض ستون‌های جدول
        for ci in range(1, ncol + 1):
            letter = get_column_letter(ci)
            cur = ws.column_dimensions[letter].width or 0
            ws.column_dimensions[letter].width = max(cur, 18)
        row += 1

    for kind, txt in blocks:
        if kind == "table":
            put_table(txt)
        elif kind == "h1":
            put(txt, font_size + 6, bold=True, color="0F766E")
        elif kind == "h2":
            put(txt, font_size + 3, bold=True, color="B8860B")
        elif kind == "h3":
            put(txt, font_size + 1, bold=True)
        elif kind == "li":
            put("• " + txt, font_size)
        else:
            put(txt, font_size)

    name = _new_name("xlsx")
    wb.save(os.path.join(EXPORT_DIR, name))
    return name


# ---------------- ساخت فایل متنی ساده (.txt) ----------------

def build_txt(blocks, title: str | None = None) -> str:
    """خروجی متن ساده — بدون قالب‌بندی، مناسب کپی و ویرایش سریع."""
    blocks2, notes = _flatten_footnotes(blocks)
    lines = []
    if title:
        t = str(title)
        lines += [t, "═" * min(len(t), 48), ""]
    for kind, txt in blocks2:
        if kind == "table":
            for row in txt:
                lines.append("   ".join(str(c) for c in row))
            lines.append("")
        elif kind in ("h1", "h2", "h3"):
            lines += ["", str(txt), ""]
        elif kind == "li":
            lines.append("• " + str(txt))
        elif kind == "quote":
            lines.append("❝ " + str(txt))
        else:
            lines += [str(txt), ""]
    if notes:
        lines += ["", "پانوشت‌ها:"]
        for n, note in notes:
            lines.append(f"{_to_fa_digits_mod(n)}. {note}")
    name = _new_name("txt")
    with open(os.path.join(EXPORT_DIR, name), "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    return name


# ---------------- ساخت فایل مارک‌داون (.md) ----------------

def build_md(blocks, title: str | None = None) -> str:
    """خروجی مارک‌داون — عنوان‌ها، فهرست‌ها، جدول‌ها و پانوشت‌ها با قالب استاندارد."""
    fn_defs = {}
    lines = []
    if title:
        lines += [f"# {title}", ""]
    for kind, txt in blocks:
        if kind == "footnotes":
            fn_defs = txt
            continue
        if kind == "table":
            if txt:
                ncol = len(txt[0])
                lines.append("| " + " | ".join(str(c) for c in txt[0]) + " |")
                lines.append("| " + " | ".join("---" for _ in range(ncol)) + " |")
                for row in txt[1:]:
                    lines.append("| " + " | ".join(str(c) for c in row) + " |")
                lines.append("")
        elif kind == "h1":
            lines += ["", f"# {txt}", ""]
        elif kind == "h2":
            lines += ["", f"## {txt}", ""]
        elif kind == "h3":
            lines += ["", f"### {txt}", ""]
        elif kind == "li":
            lines.append(f"- {txt}")
        elif kind == "quote":
            lines.append(f"> {txt}")
        else:
            lines += [str(txt), ""]
    if fn_defs:
        lines.append("")
        for fid, d in fn_defs.items():
            lines.append(f"[^{fid}]: {d}")
    name = _new_name("md")
    with open(os.path.join(EXPORT_DIR, name), "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    return name


# ---------------- ساخت پاورپوینت (راست‌به‌چپ فارسی) ----------------

def build_pptx(content: str, title: str = "ارائه آنتانو", font: str = "Tahoma") -> str:
    from pptx import Presentation
    from pptx.util import Pt, Inches
    from pptx.enum.text import PP_ALIGN
    from pptx.dml.color import RGBColor

    # فونت‌های امن و رایج که روی همه سیستم‌ها موجودند (تا ارائه به‌هم نریزد)
    SAFE_FONTS = {"Tahoma", "Arial", "Calibri", "Times New Roman", "Segoe UI", "B Nazanin"}
    if font not in SAFE_FONTS:
        font = "Tahoma"

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    TEAL = RGBColor(0x0F, 0x76, 0x6E)
    GOLD = RGBColor(0xB8, 0x86, 0x0B)
    DARK = RGBColor(0x1F, 0x29, 0x37)

    def set_rtl(tf):
        for p in tf.paragraphs:
            p.alignment = PP_ALIGN.RIGHT
            pPr = p._pPr
            if pPr is None:
                pPr = p._p.get_or_add_pPr()
            pPr.set("rtl", "1")

    # اسلاید عنوان
    s = prs.slides.add_slide(prs.slide_layouts[6])
    box = s.shapes.add_textbox(Inches(1), Inches(2.6), Inches(11.3), Inches(2))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = title
    r.font.size = Pt(44); r.font.bold = True; r.font.color.rgb = TEAL; r.font.name = font
    p.alignment = PP_ALIGN.CENTER

    # تقسیم محتوا به اسلایدها بر اساس عنوان‌ها (خطوط # یا ##)
    blocks, _ = _flatten_footnotes(md_to_blocks(content))
    cur_title = None
    cur_points = []

    def flush():
        if cur_title is None and not cur_points:
            return
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        # نوار عنوان
        t = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(12), Inches(1))
        ttf = t.text_frame; ttf.word_wrap = True
        tp = ttf.paragraphs[0]
        tr = tp.add_run(); tr.text = cur_title or "•"
        tr.font.size = Pt(30); tr.font.bold = True; tr.font.color.rgb = GOLD; tr.font.name = font
        tp.alignment = PP_ALIGN.RIGHT
        set_rtl(ttf)
        # محتوا
        body = slide.shapes.add_textbox(Inches(0.6), Inches(1.6), Inches(12), Inches(5.4))
        btf = body.text_frame; btf.word_wrap = True
        first = True
        for pt in cur_points:
            para = btf.paragraphs[0] if first else btf.add_paragraph()
            first = False
            run = para.add_run(); run.text = "• " + pt
            run.font.size = Pt(20); run.font.color.rgb = DARK; run.font.name = font
            para.alignment = PP_ALIGN.RIGHT
            para.space_after = Pt(10)
        set_rtl(btf)

    for kind, txt in blocks:
        if kind in ("h1", "h2", "h3"):
            flush()
            cur_title = txt
            cur_points = []
        elif kind == "table":
            # هر ردیف جدول را به یک خط متن تبدیل کن
            for r in txt:
                cur_points.append(" | ".join(str(c) for c in r))
                if len(cur_points) >= 6:
                    flush()
                    cur_points = []
        else:
            cur_points.append(txt)
            if len(cur_points) >= 6:  # حداکثر ۶ نکته در هر اسلاید
                flush()
                cur_points = []
    flush()

    name = _new_name("pptx")
    prs.save(os.path.join(EXPORT_DIR, name))
    return name


# ---------------- استخراج متن از اسناد (برای تبدیل فرمت‌ها) ----------------

def _docx_tables_to_md(table) -> str:
    rows = []
    for row in table.rows:
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        if any(cells):
            rows.append(cells)
    if len(rows) < 1:
        return ""
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * ncol) + " |"]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def extract_markdown(path: str) -> str:
    """متن یک سند (Word/PDF/PowerPoint/متن) را به مارک‌داون ساده تبدیل می‌کند"""
    ext = os.path.splitext(path)[1].lower()
    parts = []

    if ext == ".docx":
        from docx import Document
        doc = Document(path)
        # پاراگراف‌ها و جدول‌ها را به ترتیب بدنه بخوان
        from docx.oxml.ns import qn
        body = doc.element.body
        tbl_iter = iter(doc.tables)
        para_iter = iter(doc.paragraphs)
        for child in body.iterchildren():
            if child.tag == qn("w:p"):
                try:
                    p = next(para_iter)
                except StopIteration:
                    continue
                t = p.text.strip()
                if not t:
                    continue
                style = (p.style.name or "").lower() if p.style else ""
                if "heading 1" in style or "title" in style:
                    parts.append("# " + t)
                elif "heading 2" in style:
                    parts.append("## " + t)
                elif "heading 3" in style or "heading" in style:
                    parts.append("### " + t)
                else:
                    parts.append(t)
            elif child.tag == qn("w:tbl"):
                try:
                    tb = next(tbl_iter)
                    md = _docx_tables_to_md(tb)
                    if md:
                        parts.append(md)
                except StopIteration:
                    continue

    elif ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        for page in reader.pages:
            txt = page.extract_text() or ""
            for ln in txt.split("\n"):
                if ln.strip():
                    parts.append(ln.strip())

    elif ext == ".pptx":
        from pptx import Presentation
        prs = Presentation(path)
        for i, slide in enumerate(prs.slides, 1):
            texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        s = "".join(r.text for r in para.runs).strip()
                        if s:
                            texts.append(s)
            if texts:
                parts.append("## " + texts[0])        # اولین خط اسلاید = عنوان
                for t in texts[1:]:
                    parts.append("- " + t)

    else:  # متن ساده
        with open(path, encoding="utf-8", errors="ignore") as f:
            parts = [ln.rstrip() for ln in f]

    return "\n\n".join(parts).strip()


def _find_soffice():
    """یافتن مسیر LibreOffice/soffice برای تبدیل Word→PDF."""
    import shutil
    for cand in ("soffice", "libreoffice"):
        p = shutil.which(cand)
        if p:
            return p
    for p in ("/usr/bin/soffice", "/usr/bin/libreoffice",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice",
              r"C:\Program Files\LibreOffice\program\soffice.exe"):
        if os.path.exists(p):
            return p
    return None


def docx_to_pdf(docx_name: str):
    """تبدیل یک فایل Wordِ ازپیش‌ساخته‌شده در EXPORT_DIR به PDF با حفظ کاملِ ظاهر
    (همان چیدمان، جدول، فهرست و راست‌به‌چپ که در Word ساخته شد).
    خروجی: (نام‌فایل PDF | None، خطا | None). اگر None برگردد، فراخواننده به روش fpdf برمی‌گردد."""
    import subprocess
    src = os.path.join(EXPORT_DIR, docx_name)
    if not os.path.exists(src):
        return None, "فایل Word برای تبدیل پیدا نشد"
    pdf_name = os.path.splitext(docx_name)[0] + ".pdf"
    pdf_path = os.path.join(EXPORT_DIR, pdf_name)

    # ۱) LibreOffice/soffice — بهترین حفظ ظاهرِ Word
    soffice = _find_soffice()
    if soffice:
        try:
            env = dict(os.environ)
            env.setdefault("HOME", EXPORT_DIR)
            profile = "file://" + os.path.join(EXPORT_DIR, ".lo_profile")
            subprocess.run(
                [soffice, "--headless", "-env:UserInstallation=" + profile,
                 "--convert-to", "pdf:writer_pdf_Export", "--outdir", EXPORT_DIR, src],
                check=True, timeout=180, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if os.path.exists(pdf_path):
                return pdf_name, None
        except Exception:
            pass

    # ۲) docx2pdf — روی ویندوز/مک با Microsoft Word نصب‌شده
    try:
        from docx2pdf import convert as _d2p
        _d2p(src, pdf_path)
        if os.path.exists(pdf_path):
            return pdf_name, None
    except Exception:
        pass

    return None, None  # تبدیل ممکن نشد → استفاده از روش fpdf


def convert_document(src_path: str, target: str, font_name: str = "Vazirmatn",
                     font_size: int = 14, align: str = "justify", title=None):
    """تبدیل یک سند به فرمت هدف (docx/pdf/pptx). خروجی: (نام فایل | None، خطا | None)"""
    md = extract_markdown(src_path)
    if not md:
        return None, "متنی برای تبدیل در فایل پیدا نشد (شاید فایل اسکن‌شده یا خالی است)."
    blocks = md_to_blocks(md)
    if target == "docx":
        return build_docx(blocks, font_name, font_size, title, align), None
    if target == "pdf":
        return build_pdf(blocks, font_size, title, align)
    if target == "pptx":
        return build_pptx(md, title or "ارائه آنتانو"), None
    return None, "فرمت هدف پشتیبانی نمی‌شود"
