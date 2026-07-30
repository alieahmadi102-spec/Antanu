# -*- coding: utf-8 -*-
"""
test_footnotes.py — آزمون پاورقیِ واقعیِ Word: فونت/سایز/فاصله‌ی خط قابل‌تنظیم.

پاورقی‌های واقعی امروز فقط در مسیر آکادمیک استفاده می‌شوند (اصطلاح‌های تخصصی و،
بعد از این تغییر، نام لاتین نویسنده‌های خارجی)، پس پیش‌فرض طبق قراردادِ رایج
پایان‌نامه‌های فارسی است: Times New Roman، سایز ۹، فاصله‌ی خط تک.

اجرا:  python test_footnotes.py
"""
import os
import re
import sys
import warnings
import zipfile

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  — {detail}" if detail else ""))


def section(title):
    print("\n" + "─" * 68 + f"\n{title}\n" + "─" * 68)


def _footnotes_xml(name):
    import export_utils
    path = os.path.join(export_utils.EXPORT_DIR, name)
    return zipfile.ZipFile(path).read("word/footnotes.xml").decode("utf-8")


def test_default_style():
    section("۱) پیش‌فرض: Times New Roman ۹، فاصله‌ی خط تک")
    import export_utils

    blocks = export_utils.md_to_blocks(
        "متن با اصطلاح[^1] و نویسنده‌ی خارجی[^2].\n\n"
        "[^1]: توضیح اصطلاح\n[^2]: Porter, M. E.\n"
    )
    name = export_utils.build_docx(blocks, "Vazirmatn", 14, "تست", "right", False, False, True)
    xml = _footnotes_xml(name)

    check("فونت پیش‌فرض پاورقی Times New Roman است", 'w:ascii="Times New Roman"' in xml)
    check("سایز پیش‌فرض ۹pt است (نیم‌نقطه = ۱۸)", 'w:sz w:val="18"' in xml)
    check("szCs هم ست شده (برای فونت راست‌به‌چپ)", 'w:szCs w:val="18"' in xml)
    check("فاصله‌ی خط تک ست شده", 'w:spacing w:line="240" w:lineRule="auto"' in xml)
    check("متن هر دو پاورقی در فایل هست",
          "توضیح اصطلاح" in xml and "Porter, M. E." in xml)


def test_customizable():
    section("۲) قابل‌تنظیم: فونت/سایز/فاصله‌ی دیگر هم می‌شود خواست")
    import export_utils

    blocks = export_utils.md_to_blocks("متن[^1].\n\n[^1]: توضیح\n")
    name = export_utils.build_docx(blocks, "Vazirmatn", 14, "تست۲", "right", False, False, True,
                                   footnote_font="Vazirmatn", footnote_size=11,
                                   footnote_single_spacing=False)
    xml = _footnotes_xml(name)
    check("فونت سفارشی اعمال شد", 'w:ascii="Vazirmatn"' in xml and
          'w:ascii="Times New Roman"' not in xml)
    check("سایز سفارشی اعمال شد (۱۱pt = ۲۲)", 'w:sz w:val="22"' in xml)
    check("فاصله‌ی خط وقتی خواسته نشده تزریق نمی‌شود",
          "w:spacing" not in xml.split('w:footnote w:id="1"')[1].split("</w:pPr>")[0])


def test_valid_xml_order():
    section("۳) ترتیب عنصرها طبق شِمای OOXML (نه فقط اینکه python-docx تحمل کند)")
    import export_utils

    blocks = export_utils.md_to_blocks("متن[^1].\n\n[^1]: توضیح\n")
    name = export_utils.build_docx(blocks, "Vazirmatn", 14, "تست۳", "right", False, False, True)
    xml = _footnotes_xml(name)

    # داخل rPr، ترتیبِ درستِ CT_RPr: rFonts سپس sz/szCs و در آخر vertAlign —
    # این همان باگی بود که LibreOffice کل فایل را با آن رد می‌کرد، هرچند
    # python-docx بی‌سروصدا بازش می‌کرد.
    ref_run = re.search(r"<w:footnoteRef/>", xml)
    check("ران شماره‌ی پاورقی پیدا شد", ref_run is not None)
    rpr = re.search(r"<w:r><w:rPr>(.*?)</w:rPr><w:footnoteRef/>", xml)
    check("rPrِ ران شماره‌ی پاورقی پیدا شد", rpr is not None)
    if rpr:
        order = re.findall(r"<w:(sz|szCs|vertAlign)\b", rpr.group(1))
        check("ترتیب: sz و szCs قبل از vertAlign",
              order.index("vertAlign") > order.index("sz") and
              order.index("vertAlign") > order.index("szCs"),
              str(order))


def test_docx_opens_cleanly():
    section("۴) فایل ساخته‌شده با python-docx سالم باز می‌شود")
    import export_utils
    from docx import Document

    blocks = export_utils.md_to_blocks(
        "متن با سه پاورقی[^1][^2][^3].\n\n[^1]: یک\n[^2]: دو\n[^3]: سه\n")
    name = export_utils.build_docx(blocks, "Vazirmatn", 14, "تست۴", "right", True, True, True)
    path = os.path.join(export_utils.EXPORT_DIR, name)
    try:
        doc = Document(path)
        check("سند بدون استثنا باز شد", True, f"{len(doc.paragraphs)} پاراگراف")
    except Exception as e:
        check("سند بدون استثنا باز شد", False, str(e))

    body = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    refs = re.findall(r'w:footnoteReference w:id="(\d+)"', body)
    check("هر سه ارجاع پاورقی در بدنه هست", refs == ["1", "2", "3"], str(refs))


def test_no_footnotes_untouched():
    section("۵) بدون پاورقی، هیچ چیزِ اضافه‌ای به سند نمی‌خورد")
    import export_utils

    blocks = export_utils.md_to_blocks("متن بدون هیچ پاورقی‌ای.")
    name = export_utils.build_docx(blocks, "Vazirmatn", 14, "تست۵", "right", False, False, True)
    names = zipfile.ZipFile(os.path.join(export_utils.EXPORT_DIR, name)).namelist()
    check("word/footnotes.xml وقتی پاورقی‌ای نیست ساخته نمی‌شود",
          "word/footnotes.xml" not in names)


def main_run():
    print("═" * 68)
    print("  آزمون پاورقی واقعی Word")
    print("═" * 68)
    test_default_style()
    test_customizable()
    test_valid_xml_order()
    test_docx_opens_cleanly()
    test_no_footnotes_untouched()

    print("\n" + "═" * 68)
    print(f"  نتیجه: {len(PASS)} پاس، {len(FAIL)} ناموفق")
    if FAIL:
        print("  ناموفق‌ها:")
        for f in FAIL:
            print("    ✗", f)
    print("═" * 68)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main_run())
