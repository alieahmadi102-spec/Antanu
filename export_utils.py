# -*- coding: utf-8 -*-
"""
export_utils.py — ساخت خروجی Word و PDF فارسی (راست‌به‌چپ) با فونت و سایز دلخواه
"""
import os
import re
import secrets

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

def md_to_blocks(text: str):
    """('h1'|'h2'|'h3'|'li'|'p', متن) — علامت‌های مارک‌داون حذف می‌شوند"""
    blocks = []
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if not line or line in ("---", "***"):
            continue
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"[*_`]", "", line)
        if line.startswith("### "):
            blocks.append(("h3", line[4:].strip()))
        elif line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
        elif line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
        elif re.match(r"^[-•]\s+", line):
            blocks.append(("li", re.sub(r"^[-•]\s+", "", line)))
        elif re.match(r"^\d+[.)]\s+", line):
            blocks.append(("li", re.sub(r"^\d+[.)]\s+", "", line)))
        else:
            blocks.append(("p", line))
    return blocks


def _new_name(ext: str) -> str:
    return f"antanu-{secrets.token_hex(6)}.{ext}"


# ---------------- ساخت فایل Word (راست‌به‌چپ) ----------------

def build_docx(blocks, font_name: str = "Vazirmatn", font_size: int = 14,
               title: str | None = None, align: str = "right") -> str:
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    ALIGN_MAP = {"right": WD_ALIGN_PARAGRAPH.RIGHT, "left": WD_ALIGN_PARAGRAPH.LEFT,
                 "center": WD_ALIGN_PARAGRAPH.CENTER}
    body_align = ALIGN_MAP.get(align, WD_ALIGN_PARAGRAPH.RIGHT)

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

    def rtl_para(p, align=WD_ALIGN_PARAGRAPH.RIGHT, heading=False):
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

    doc = Document()

    if title:
        p = doc.add_paragraph()
        rtl_para(p, WD_ALIGN_PARAGRAPH.CENTER)
        style_run(p.add_run(title), font_size + 10, bold=True, color=(0x0F, 0x76, 0x6E))

    for kind, txt in blocks:
        p = doc.add_paragraph()
        rtl_para(p, body_align, heading=kind in ("h1", "h2", "h3"))
        if kind == "h1":
            style_run(p.add_run(txt), font_size + 8, bold=True, color=(0x0F, 0x76, 0x6E))
        elif kind == "h2":
            style_run(p.add_run(txt), font_size + 4, bold=True, color=(0xB8, 0x86, 0x0B))
        elif kind == "h3":
            style_run(p.add_run(txt), font_size + 2, bold=True)
        elif kind == "li":
            style_run(p.add_run("• " + txt), font_size)
        else:
            style_run(p.add_run(txt), font_size)

    name = _new_name("docx")
    doc.save(os.path.join(EXPORT_DIR, name))
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
    pdf.add_page()
    pdf.add_font("Vazir", "", font)

    if title:
        pdf.set_font("Vazir", size=font_size + 8)
        pdf.multi_cell(0, (font_size + 8) * 0.62, shape(title), align="C")
        pdf.ln(3)

    for kind, txt in blocks:
        size = font_size + (8 if kind == "h1" else 4 if kind == "h2" else 2 if kind == "h3" else 0)
        pdf.set_font("Vazir", size=size)
        text = ("• " + txt) if kind == "li" else txt
        pdf_align = {"right": "R", "left": "L", "center": "C"}.get(align, "R")
        try:
            pdf.multi_cell(0, size * 0.62, shape(text), align=pdf_align)
        except Exception:
            continue
        if kind in ("h1", "h2", "h3"):
            pdf.ln(1)

    name = _new_name("pdf")
    pdf.output(os.path.join(EXPORT_DIR, name))
    return name, None


# ---------------- ساخت فایل Excel (راست‌به‌چپ) ----------------

def build_xlsx(blocks, font_name: str = "Vazirmatn", font_size: int = 14,
               title: str | None = None, align: str = "right") -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "آنتانو"
    ws.sheet_view.rightToLeft = True
    ws.column_dimensions["A"].width = 110

    xl_align = Alignment(
        horizontal={"right": "right", "left": "left", "center": "center"}.get(align, "right"),
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

    for kind, txt in blocks:
        if kind == "h1":
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


# ---------------- ساخت پاورپوینت (راست‌به‌چپ فارسی) ----------------

def build_pptx(content: str, title: str = "ارائه آنتانو") -> str:
    from pptx import Presentation
    from pptx.util import Pt, Inches
    from pptx.enum.text import PP_ALIGN
    from pptx.dml.color import RGBColor

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
    r.font.size = Pt(44); r.font.bold = True; r.font.color.rgb = TEAL; r.font.name = "Vazirmatn"
    p.alignment = PP_ALIGN.CENTER

    # تقسیم محتوا به اسلایدها بر اساس عنوان‌ها (خطوط # یا ##)
    blocks = md_to_blocks(content)
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
        tr.font.size = Pt(30); tr.font.bold = True; tr.font.color.rgb = GOLD; tr.font.name = "Vazirmatn"
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
            run.font.size = Pt(20); run.font.color.rgb = DARK; run.font.name = "Vazirmatn"
            para.alignment = PP_ALIGN.RIGHT
            para.space_after = Pt(10)
        set_rtl(btf)

    for kind, txt in blocks:
        if kind in ("h1", "h2", "h3"):
            flush()
            cur_title = txt
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
