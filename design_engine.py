# -*- coding: utf-8 -*-
"""
design_engine.py — موتور طراحی هوشمند اسناد و ارائه‌های آنتانو

هدف: هر بار بر اساس موضوع/مخاطب/هدف، یک «طرح» اختصاصی (پالت رنگ، فونت، حال‌وهوا،
چیدمان) از صفر ساخته می‌شود و محتوای تولیدشده داخل همان طرح قرار می‌گیرد — بدون قالب آماده.

ماژولار و قابل توسعه: برای افزودن سبک جدید کافی است یک ورودی به THEMES اضافه شود.
"""
import os
import re
import colorsys
import secrets

import i18n

# رنگ‌ها به‌صورت رشته‌ی HEX بدون # ذخیره می‌شوند
# هر تم: پالت کامل + فونت‌های امن (که روی همه سیستم‌ها موجودند) + حال‌وهوا
THEMES = {
    # فناوری → مدرن و تیره
    "tech": {
        "label": "فناوری (مدرن و تیره)",
        "primary": "0EA5E9", "secondary": "6366F1", "accent": "22D3EE",
        "dark": "0B1220", "light": "F1F5F9", "text": "0F172A",
        "mode": "dark", "heading_font": "Tahoma", "body_font": "Tahoma",
        "mood": ["نوآوری", "دقت", "سرعت"],
    },
    # پزشکی → سفید و آبی
    "medical": {
        "label": "پزشکی (سفید و آبی)",
        "primary": "0284C7", "secondary": "0D9488", "accent": "38BDF8",
        "dark": "0C4A6E", "light": "F0F9FF", "text": "134E4A",
        "mode": "light", "heading_font": "Tahoma", "body_font": "Tahoma",
        "mood": ["سلامت", "اعتماد", "پاکیزگی"],
    },
    # مالی/کسب‌وکار → رسمی و مینیمال
    "finance": {
        "label": "مالی و رسمی (مینیمال)",
        "primary": "1E3A5F", "secondary": "B8860B", "accent": "475569",
        "dark": "0F1E2E", "light": "F8FAFC", "text": "1E293B",
        "mode": "light", "heading_font": "Times New Roman", "body_font": "Tahoma",
        "mood": ["اعتبار", "ثبات", "دقت"],
    },
    # آموزشی → رنگی و خوانا
    "education": {
        "label": "آموزشی (رنگی و خوانا)",
        "primary": "7C3AED", "secondary": "F59E0B", "accent": "10B981",
        "dark": "3B0764", "light": "FAF5FF", "text": "1F2937",
        "mode": "light", "heading_font": "Tahoma", "body_font": "Tahoma",
        "mood": ["یادگیری", "شفافیت", "انگیزه"],
    },
    # کودک → شاد و کارتونی
    "kids": {
        "label": "کودک (شاد و کارتونی)",
        "primary": "F43F5E", "secondary": "FB923C", "accent": "34D399",
        "dark": "7C2D12", "light": "FFF7ED", "text": "3F3F46",
        "mode": "light", "heading_font": "Tahoma", "body_font": "Tahoma",
        "mood": ["شادی", "بازی", "رنگارنگی"],
    },
    # دانشگاهی/پژوهشی → کلاسیک و رسمی (پیش‌فرض پایان‌نامه)
    "academic": {
        "label": "دانشگاهی (کلاسیک)",
        "primary": "0F766E", "secondary": "B8860B", "accent": "115E59",
        "dark": "042F2E", "light": "F0FDFA", "text": "1F2937",
        "mode": "light", "heading_font": "B Nazanin", "body_font": "Vazirmatn",
        "mood": ["علمی", "دقیق", "منسجم"],
    },
    # خلاق/بازاریابی → پرانرژی
    "creative": {
        "label": "خلاق و پرانرژی",
        "primary": "DB2777", "secondary": "8B5CF6", "accent": "F59E0B",
        "dark": "500724", "light": "FDF2F8", "text": "1F2937",
        "mode": "light", "heading_font": "Tahoma", "body_font": "Tahoma",
        "mood": ["خلاقیت", "جسارت", "تأثیر"],
    },
}

DEFAULT_STYLE = "academic"

# کلیدواژه‌ها برای تشخیص خودکار سبک از روی موضوع
_KEYWORDS = {
    "tech": ["فناوری", "هوش مصنوعی", "نرم‌افزار", "برنامه‌نویسی", "دیجیتال", "بلاک‌چین",
             "داده", "شبکه", "الگوریتم", "استارتاپ", "ربات", "اینترنت", "امنیت سایبری", "فنی"],
    "medical": ["پزشکی", "سلامت", "بیمار", "درمان", "دارو", "پرستاری", "بهداشت", "بیمارستان",
                "کرونا", "ویروس", "تغذیه", "روان", "بالینی", "تشخیص"],
    "finance": ["مالی", "حسابداری", "اقتصاد", "سرمایه", "بورس", "بانک", "بودجه", "مالیات",
                "سود", "سرمایه‌گذاری", "بازار", "پول", "تجارت", "حسابرسی", "مدیریت مالی"],
    "education": ["آموزش", "یادگیری", "درس", "مدرسه", "دانش‌آموز", "تدریس", "پرورش",
                  "کلاس", "معلم", "آموزشی", "برنامه درسی"],
    "kids": ["کودک", "بچه", "کودکان", "داستان کودک", "مهدکودک", "بازی کودک", "قصه"],
    "creative": ["بازاریابی", "برند", "تبلیغات", "خلاق", "طراحی", "هنر", "رسانه",
                 "شبکه اجتماعی", "کمپین", "محتوا"],
    "academic": ["پایان‌نامه", "رساله", "مقاله", "پژوهش", "تحقیق", "علمی", "دانشگاه",
                 "فرضیه", "روش تحقیق", "پروپوزال", "نظری"],
}


def classify_topic(text: str) -> str:
    """تشخیص سبک طراحی از روی موضوع (بر پایه کلیدواژه). اگر چیزی پیدا نشد → دانشگاهی."""
    t = (text or "").lower()
    best, best_score = DEFAULT_STYLE, 0
    for style, words in _KEYWORDS.items():
        score = sum(1 for w in words if w in t)
        if score > best_score:
            best, best_score = style, score
    return best


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "".join(f"{max(0, min(255, int(c))):02X}" for c in rgb)


def _shade(hex_color, factor):
    """روشن‌تر (factor>1) یا تیره‌تر (factor<1) کردن یک رنگ برای پالت مشتق"""
    r, g, b = _hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    l = max(0.0, min(1.0, l * factor))
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return _rgb_to_hex((r2 * 255, g2 * 255, b2 * 255))


def _mix(hex_a, hex_b, t=0.5):
    a, b = _hex_to_rgb(hex_a), _hex_to_rgb(hex_b)
    return _rgb_to_hex(tuple(a[i] * (1 - t) + b[i] * t for i in range(3)))


def build_spec(style=None, topic="", overrides=None):
    """طرح نهایی را می‌سازد: پالت گسترده + فونت‌ها + رنگ‌های مشتق.
    style='auto' یا None → از روی topic تشخیص داده می‌شود.
    overrides: دیکشنری اختیاری (مثلاً از هوش مصنوعی) برای بازنویسی رنگ‌ها/فونت‌ها."""
    if not style or style == "auto":
        style = classify_topic(topic)
    if style not in THEMES:
        style = DEFAULT_STYLE
    base = dict(THEMES[style])
    if overrides:
        for k in ("primary", "secondary", "accent", "dark", "light", "text",
                  "heading_font", "body_font", "mode"):
            v = (overrides.get(k) or "").strip() if isinstance(overrides.get(k), str) else overrides.get(k)
            if v:
                base[k] = v.lstrip("#") if k in ("primary", "secondary", "accent", "dark", "light", "text") else v
    # رنگ‌های مشتق برای باکس‌ها و سایه‌روشن‌ها
    base["primary_light"] = _shade(base["primary"], 1.7)
    base["primary_soft"] = _mix(base["primary"], "FFFFFF", 0.85)
    base["accent_soft"] = _mix(base["accent"], "FFFFFF", 0.82)
    base["band"] = base["primary"]
    base["style"] = style
    # اطمینان از فونت‌های امن برای پاورپوینت (تا روی سیستم‌ها به‌هم نریزد)
    SAFE = {"Tahoma", "Arial", "Calibri", "Times New Roman", "Segoe UI", "B Nazanin", "Vazirmatn"}
    base["pptx_font"] = base["heading_font"] if base["heading_font"] in SAFE else "Tahoma"
    return base


# ================= ساخت Word طراحی‌شده (اختصاصی هر موضوع) =================

def _fa_digits(s):
    return i18n.to_local_digits(s)


def build_designed_docx(blocks, spec, title=None, subtitle="", font_size=13,
                        align="justify", toc=True, numbering=True):
    """سند Word با طراحی اختصاصی: جلد، سربرگ/پابرگ، تیترهای رنگی، باکس نکته،
    جدول‌های تم‌دار، فهرست مطالب و شماره صفحه."""
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.section import WD_SECTION
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    body_font = spec.get("body_font", "Vazirmatn")
    head_font = spec.get("heading_font", body_font)
    PRIMARY = _hex_to_rgb(spec["primary"])
    SECONDARY = _hex_to_rgb(spec["secondary"])
    ACCENT = _hex_to_rgb(spec["accent"])
    TEXT = _hex_to_rgb(spec["text"])

    # پاراگراف‌ها w:bidi هستند؛ در RTL مقدار jc="right" به لبه‌ی فیزیکی چپ و
    # jc="left" به لبه‌ی فیزیکی راست نگاشت می‌شود. پس راست/چپ را جابه‌جا می‌کنیم
    # تا انتخاب کاربر با سمت نمایش هم‌خوان باشد.
    ALIGN_MAP = {"right": WD_ALIGN_PARAGRAPH.LEFT, "left": WD_ALIGN_PARAGRAPH.RIGHT,
                 "center": WD_ALIGN_PARAGRAPH.CENTER, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
    body_align = ALIGN_MAP.get(align, WD_ALIGN_PARAGRAPH.JUSTIFY)

    doc = Document()

    def _el(tag, **attrs):
        e = OxmlElement(tag)
        for k, v in attrs.items():
            e.set(qn(k), str(v))
        return e

    def style_run(run, size, font=None, bold=False, color=None):
        run.font.name = font or body_font
        run.font.size = Pt(size)
        run.font.bold = bold
        if color:
            run.font.color.rgb = RGBColor(*color)
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rFonts.set(qn(a), font or body_font)
        szCs = _el("w:szCs"); szCs.set(qn("w:val"), str(int(size * 2)))
        rPr.append(szCs)
        rPr.append(_el("w:rtl"))

    def rtl(p, a=None, before=0, after=8, level=None):
        p.alignment = a if a is not None else body_align
        pf = p.paragraph_format
        pf.line_spacing = 1.5
        pf.space_before = Pt(before)
        pf.space_after = Pt(after)
        pPr = p._p.get_or_add_pPr()
        pPr.append(_el("w:bidi"))
        if level is not None:
            pPr.append(_el("w:outlineLvl", **{"w:val": level}))
        return pPr

    def shade(pPr, fill):
        pPr.append(_el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": fill}))

    def side_border(pPr, color, side="right", sz=24):
        pbdr = _el("w:pBdr")
        b = _el("w:" + side, **{"w:val": "single", "w:sz": sz, "w:space": "8", "w:color": color})
        pbdr.append(b)
        pPr.append(pbdr)

    # ---------- جلد اختصاصی ----------
    if title:
        for _ in range(3):
            doc.add_paragraph()
        band = doc.add_paragraph()
        pPr = rtl(band, WD_ALIGN_PARAGRAPH.CENTER, before=6, after=6)
        shade(pPr, spec["primary"])
        style_run(band.add_run(title), font_size + 16, font=head_font, bold=True,
                  color=(255, 255, 255))
        if subtitle:
            sp = doc.add_paragraph()
            rtl(sp, WD_ALIGN_PARAGRAPH.CENTER, before=10)
            style_run(sp.add_run(subtitle), font_size + 3, color=SECONDARY, bold=True)
        # نوار لهجه‌ای زیر عنوان
        acc = doc.add_paragraph()
        pPr2 = rtl(acc, WD_ALIGN_PARAGRAPH.CENTER, before=4, after=4)
        shade(pPr2, spec["accent"])
        style_run(acc.add_run(" "), 4)
        import datetime as _dt
        dp = doc.add_paragraph()
        rtl(dp, WD_ALIGN_PARAGRAPH.CENTER, before=30)
        style_run(dp.add_run("تهیه‌شده توسط آنتانو (ANTANU)"), font_size, color=ACCENT)
        doc.add_page_break()

    # ---------- سربرگ و پابرگ ----------
    section = doc.sections[0]
    hdr = section.header.paragraphs[0]
    rtl(hdr, WD_ALIGN_PARAGRAPH.RIGHT, after=0)
    if title:
        style_run(hdr.add_run(title[:70]), font_size - 3, font=head_font, color=PRIMARY, bold=True)
    ftr = section.footer.paragraphs[0]
    rtl(ftr, WD_ALIGN_PARAGRAPH.CENTER, after=0)
    style_run(ftr.add_run("آنتانو  —  صفحه "), font_size - 4, color=ACCENT)
    # فیلد شماره صفحه
    run = ftr.add_run()
    run._r.append(_el("w:fldChar", **{"w:fldCharType": "begin"}))
    instr = _el("w:instrText", **{"xml:space": "preserve"}); instr.text = "PAGE"
    run._r.append(instr)
    run._r.append(_el("w:fldChar", **{"w:fldCharType": "end"}))
    style_run(run, font_size - 4, color=ACCENT, bold=True)

    # ---------- فهرست مطالب (آماده و چیده‌شده: عنوان … نقطه‌چین … شماره صفحه) ----------
    from export_utils import (compute_headings, add_heading_bookmark, add_pageref_run,
                              set_dot_leader_tab, set_update_fields, estimate_heading_pages)
    _heads = compute_headings(blocks, numbering) if (toc or numbering) else []
    _est_pages = estimate_heading_pages(blocks, numbering, cover=bool(title)) if (toc or numbering) else []
    if toc and _heads:
        h = doc.add_paragraph()
        rtl(h, WD_ALIGN_PARAGRAPH.CENTER, before=6, after=10)
        style_run(h.add_run("فهرست مطالب"), font_size + 6, font=head_font, bold=True, color=PRIMARY)
        # نوار لهجه‌ای زیر عنوان فهرست
        acc = doc.add_paragraph()
        pAcc = rtl(acc, WD_ALIGN_PARAGRAPH.CENTER, before=2, after=8)
        shade(pAcc, spec["accent"])
        style_run(acc.add_run(" "), 3)
        for idx, (bm, text, lvl) in enumerate(_heads):
            tp = doc.add_paragraph()
            pPr = rtl(tp, after=4)
            tp.paragraph_format.right_indent = Pt(lvl * 16)
            set_dot_leader_tab(tp, 15.5)
            col = PRIMARY if lvl == 0 else (SECONDARY if lvl == 1 else TEXT)
            style_run(tp.add_run(text), font_size, font=head_font if lvl == 0 else body_font,
                      bold=(lvl <= 1), color=col)
            tp.add_run("\t")
            est = _fa_digits(_est_pages[idx]) if idx < len(_est_pages) else "۱"
            style_run(add_pageref_run(tp, bm, est), font_size, bold=(lvl == 0), color=col)
        set_update_fields(doc)
        doc.add_page_break()
    _head_iter = iter(_heads)

    # ---------- پانوشت‌ها ----------
    fn_defs = {}
    for k, v in blocks:
        if k == "footnotes":
            fn_defs = v
    fn_order, fn_num = [], {}
    _FN = re.compile(r"\[\^([^\]]+)\]")

    def add_text_fn(p, text, size, font=None, bold=False, color=None, bullet=False):
        if bullet:
            text = "◆ " + text
        pos = 0
        for m in _FN.finditer(text):
            fid = m.group(1).strip()
            if fid not in fn_defs:
                continue
            before = text[pos:m.start()]
            if before:
                style_run(p.add_run(before), size, font=font, bold=bold, color=color)
            if fid not in fn_num:
                fn_order.append(fid); fn_num[fid] = len(fn_order)
            sup = p.add_run(_fa_digits(fn_num[fid]))
            style_run(sup, max(8, size - 3), bold=True, color=PRIMARY)
            sup.font.superscript = True
            pos = m.end()
        rest = text[pos:]
        if rest or pos == 0:
            style_run(p.add_run(rest), size, font=font, bold=bold, color=color)

    def themed_table(rows):
        if not rows:
            return
        ncol = len(rows[0])
        tbl = doc.add_table(rows=len(rows), cols=ncol)
        tbl.style = "Table Grid"
        tbl._tbl.tblPr.append(_el("w:bidiVisual"))
        for ri, row in enumerate(rows):
            for ci, val in enumerate(row):
                # w:bidiVisual جدول را خودکار راست‌به‌چپ می‌کند؛ ستون‌ها طبیعی پر می‌شوند.
                cell = tbl.cell(ri, ci)
                cell.text = ""
                if ri == 0:
                    cell._tc.get_or_add_tcPr().append(
                        _el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": spec["primary"]}))
                elif ri % 2 == 0:
                    cell._tc.get_or_add_tcPr().append(
                        _el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": spec["primary_soft"]}))
                cp = cell.paragraphs[0]
                cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cp._p.get_or_add_pPr().append(_el("w:bidi"))
                style_run(cp.add_run(_fa_digits(str(val))), max(9, font_size - 2), bold=(ri == 0),
                          color=(255, 255, 255) if ri == 0 else TEXT)
        doc.add_paragraph()

    HLEVEL = {"h1": 0, "h2": 1, "h3": 2}
    _bid = [100]
    for kind, txt in blocks:
        if kind == "footnotes":
            continue
        if kind == "table":
            themed_table(txt)
            continue
        if kind == "quote":
            # باکس نکته: پس‌زمینه‌ی ملایم + نوار کناری لهجه‌ای
            p = doc.add_paragraph()
            pPr = rtl(p, before=6, after=6)
            shade(pPr, spec["accent_soft"])
            side_border(pPr, spec["accent"], "right", 30)
            add_text_fn(p, "❝ " + txt, font_size, color=TEXT, bold=True)
            continue
        lvl = HLEVEL.get(kind)
        p = doc.add_paragraph()
        bm = None
        if lvl is not None:
            pPr = rtl(p, before=14, after=6, level=lvl)
            he = next(_head_iter, None)
            if he:
                bm, txt, _ = he  # متن شماره‌دار یکسان با فهرست
            if kind == "h1":
                shade(pPr, spec["primary_soft"])
                side_border(pPr, spec["primary"], "right", 40)
                add_text_fn(p, txt, font_size + 7, font=head_font, bold=True, color=PRIMARY)
            elif kind == "h2":
                side_border(pPr, spec["secondary"], "right", 30)
                add_text_fn(p, txt, font_size + 3, font=head_font, bold=True, color=SECONDARY)
            else:
                add_text_fn(p, txt, font_size + 1, font=head_font, bold=True, color=TEXT)
            if bm:
                add_heading_bookmark(p, bm, _bid[0]); _bid[0] += 1
        elif kind == "li":
            rtl(p)
            add_text_fn(p, txt, font_size, color=TEXT, bullet=True)
        else:
            rtl(p)
            add_text_fn(p, txt, font_size, color=TEXT)

    # بخش پانوشت‌ها
    if fn_order:
        doc.add_paragraph()
        hp = doc.add_paragraph()
        pPr = rtl(hp, before=8)
        side_border(pPr, spec["primary"], "right", 24)
        style_run(hp.add_run("پانوشت‌ها"), font_size + 2, font=head_font, bold=True, color=PRIMARY)
        for fid in fn_order:
            np = doc.add_paragraph()
            rtl(np, after=3)
            style_run(np.add_run(f"{_fa_digits(fn_num[fid])}. "), max(9, font_size - 1),
                      bold=True, color=PRIMARY)
            style_run(np.add_run(fn_defs[fid]), max(9, font_size - 1), color=TEXT)

    from export_utils import EXPORT_DIR, _new_name
    name = _new_name("docx")
    doc.save(os.path.join(EXPORT_DIR, name))
    return name


# ================= ساخت PowerPoint طراحی‌شده (هر اسلاید متفاوت اما هماهنگ) =================

def build_designed_pptx(content, spec, title="ارائه آنتانو", subtitle=""):
    """ارائه‌ی پاورپوینت با تم اختصاصی: اسلاید عنوان، اسلایدهای بخش، محتوا با نوار لهجه‌ای،
    جدول‌های تم‌دار، نمودار خودکار از داده‌های عددی، و چیدمان متغیر اما هماهنگ."""
    from pptx import Presentation
    from pptx.util import Pt, Inches, Emu
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.dml.color import RGBColor
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from export_utils import md_to_blocks, _flatten_footnotes, _new_name, EXPORT_DIR

    def C(key):
        return RGBColor(*_hex_to_rgb(spec[key]))

    font = spec.get("pptx_font", "Tahoma")
    dark_mode = spec.get("mode") == "dark"
    BG = C("dark") if dark_mode else RGBColor(0xFF, 0xFF, 0xFF)
    BODY_TEXT = RGBColor(0xF1, 0xF5, 0xF9) if dark_mode else C("text")

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    SW, SH = prs.slide_width, prs.slide_height
    blank = prs.slide_layouts[6]

    def set_bg(slide, color):
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = color

    def rect(slide, x, y, w, h, color, line=False):
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
        shp.fill.solid(); shp.fill.fore_color.rgb = color
        if not line:
            shp.line.fill.background()
        shp.shadow.inherit = False
        return shp

    def rrect(slide, x, y, w, h, color):
        shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        shp.fill.solid(); shp.fill.fore_color.rgb = color
        shp.line.fill.background()
        shp.shadow.inherit = False
        return shp

    def textbox(slide, x, y, w, h, text, size, color, bold=False, align=PP_ALIGN.RIGHT,
                anchor=MSO_ANCHOR.TOP, font_name=None):
        tb = slide.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
        p = tf.paragraphs[0]; p.alignment = align
        pPr = p._p.get_or_add_pPr(); pPr.set("rtl", "1")
        r = p.add_run(); r.text = text
        r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color
        r.font.name = font_name or font
        return tb

    def add_points(slide, x, y, w, h, points, size=18):
        tb = slide.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame; tf.word_wrap = True
        first = True
        for pt in points:
            para = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            para.alignment = PP_ALIGN.RIGHT
            para._p.get_or_add_pPr().set("rtl", "1")
            r1 = para.add_run(); r1.text = "◆ "
            r1.font.size = Pt(size); r1.font.color.rgb = C("accent"); r1.font.bold = True; r1.font.name = font
            r2 = para.add_run(); r2.text = pt
            r2.font.size = Pt(size); r2.font.color.rgb = BODY_TEXT; r2.font.name = font
            para.space_after = Pt(9)
        return tb

    # ---------- اسلاید عنوان ----------
    s = prs.slides.add_slide(blank)
    set_bg(s, C("primary"))
    rect(s, 0, Emu(int(SH * 0.72)), SW, Emu(int(SH * 0.28)), C("secondary"))
    rect(s, Emu(int(SW * 0.30)), Emu(int(SH * 0.60)), Emu(int(SW * 0.40)), Pt(6), C("accent"))
    textbox(s, Inches(1), Inches(2.4), Inches(11.3), Inches(1.8), title,
            40, RGBColor(0xFF, 0xFF, 0xFF), bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if subtitle:
        textbox(s, Inches(1), Inches(4.2), Inches(11.3), Inches(1), subtitle,
                20, C("accent_soft"), align=PP_ALIGN.CENTER)
    textbox(s, Inches(0.5), Inches(6.7), Inches(12.3), Inches(0.6), "آنتانو (ANTANU)",
            14, RGBColor(0xFF, 0xFF, 0xFF), align=PP_ALIGN.CENTER)

    # ---------- تقسیم محتوا به بخش‌ها ----------
    blocks, _ = _flatten_footnotes(md_to_blocks(content))
    slides_data = []
    cur = None
    for kind, txt in blocks:
        if kind in ("h1", "h2"):
            if cur:
                slides_data.append(cur)
            cur = {"title": txt, "level": kind, "points": [], "tables": []}
        elif kind == "h3":
            if cur is None:
                cur = {"title": txt, "level": "h2", "points": [], "tables": []}
            else:
                cur["points"].append(txt)
        elif kind == "table":
            if cur is None:
                cur = {"title": "جدول", "level": "h2", "points": [], "tables": []}
            cur["tables"].append(txt)
        elif kind == "quote":
            if cur is None:
                cur = {"title": "نکته", "level": "h2", "points": [], "tables": []}
            cur["points"].append("❝ " + txt)
        else:
            if cur is None:
                cur = {"title": "مطالب", "level": "h2", "points": [], "tables": []}
            cur["points"].append(txt)
    if cur:
        slides_data.append(cur)

    def numeric_chart(slide, rows):
        """اگر جدول ستون عددی داشته باشد، نمودار ستونی رسم می‌کند"""
        if len(rows) < 2 or len(rows[0]) < 2:
            return False
        cats, vals = [], []
        for r in rows[1:]:
            num = None
            for c in r[1:]:
                cc = str(c).replace("٫", ".").replace(",", "").replace("%", "").strip()
                try:
                    num = float(cc); break
                except ValueError:
                    continue
            if num is not None:
                cats.append(str(r[0])[:20]); vals.append(num)
        if len(vals) < 2:
            return False
        cd = CategoryChartData()
        cd.categories = cats
        cd.add_series(rows[0][1] if len(rows[0]) > 1 else "مقدار", vals)
        gf = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,
                                    Inches(0.7), Inches(1.7), Inches(11.9), Inches(5.2), cd)
        chart = gf.chart
        chart.has_legend = False
        try:
            plot = chart.plots[0]
            plot.vary_by_categories = True
        except Exception:
            pass
        return True

    palette_cycle = ["primary", "secondary", "accent"]
    for i, sd in enumerate(slides_data):
        slide = prs.slides.add_slide(blank)
        set_bg(slide, BG)
        band_color = C(palette_cycle[i % 3])
        is_section = sd["level"] == "h1"

        if is_section:
            # اسلاید جداکننده‌ی بخش: پس‌زمینه‌ی رنگی و عنوان بزرگ
            set_bg(slide, band_color)
            rect(slide, Emu(int(SW * 0.30)), Emu(int(SH * 0.58)), Emu(int(SW * 0.40)), Pt(6), C("accent"))
            textbox(slide, Inches(1), Inches(2.8), Inches(11.3), Inches(1.8), sd["title"],
                    34, RGBColor(0xFF, 0xFF, 0xFF), bold=True, align=PP_ALIGN.CENTER,
                    anchor=MSO_ANCHOR.MIDDLE)
            if sd["points"]:
                add_points(slide, Inches(1.5), Inches(4.6), Inches(10.3), Inches(2.5), sd["points"][:4], size=16)
            continue

        # نوار لهجه‌ای بالا (جای متغیر برای تنوع)
        if i % 2 == 0:
            rect(slide, 0, 0, SW, Inches(0.28), band_color)
        else:
            rect(slide, Emu(SW - Inches(0.28)), 0, Inches(0.28), SH, band_color)
        # عنوان اسلاید
        textbox(slide, Inches(0.6), Inches(0.45), Inches(12), Inches(0.9), sd["title"],
                26, band_color, bold=True)
        rect(slide, Emu(int(SW * 0.55)), Inches(1.35), Emu(int(SW * 0.40)), Pt(3), C("accent"))

        if sd["tables"]:
            rows = sd["tables"][0]
            # اگر عددی بود نمودار، وگرنه جدول
            if not numeric_chart(slide, rows):
                nrow, ncol = len(rows), len(rows[0])
                gt = slide.shapes.add_table(nrow, ncol, Inches(0.7), Inches(1.7),
                                            Inches(11.9), Inches(0.5 * nrow)).table
                for ri, row in enumerate(rows):
                    for ci, val in enumerate(row):
                        # جدول پاورپوینت mirror خودکار ندارد؛ ستون‌ها دستی معکوس می‌شوند.
                        cell = gt.cell(ri, ncol - 1 - ci)
                        cell.text = _fa_digits(str(val))
                        para = cell.text_frame.paragraphs[0]
                        para.alignment = PP_ALIGN.CENTER
                        para._p.get_or_add_pPr().set("rtl", "1")
                        rr = para.runs[0]
                        rr.font.size = Pt(13); rr.font.name = font
                        rr.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF) if ri == 0 else BODY_TEXT
                        rr.font.bold = (ri == 0)
                        cell.fill.solid()
                        cell.fill.fore_color.rgb = band_color if ri == 0 else (
                            C("primary_soft") if ri % 2 == 0 else RGBColor(0xFF, 0xFF, 0xFF) if not dark_mode else C("dark"))
            if sd["points"]:
                add_points(slide, Inches(0.7), Inches(6.2), Inches(11.9), Inches(1.1), sd["points"][:2], size=14)
        elif sd["points"]:
            add_points(slide, Inches(0.8), Inches(1.7), Inches(11.7), Inches(5.2), sd["points"][:8])

    name = _new_name("pptx")
    prs.save(os.path.join(EXPORT_DIR, name))
    return name
