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


def test_design_engine_real_footnotes():
    section("۶) design_engine.build_designed_docx هم پاورقی واقعی پشتیبانی می‌کند")
    import design_engine
    import export_utils
    from docx import Document

    blocks = export_utils.md_to_blocks(
        "# فصل اول\n\nمتن با نویسنده‌ی خارجی[^1].\n\n[^1]: Porter, M. E.\n")
    spec = design_engine.build_spec(topic="مدیریت استراتژیک")

    name = design_engine.build_designed_docx(blocks, spec, title="تست", font_size=13,
                                             align="justify", toc=False, numbering=False,
                                             real_footnotes=True)
    path = os.path.join(export_utils.EXPORT_DIR, name)
    names = zipfile.ZipFile(path).namelist()
    check("word/footnotes.xml ساخته شد", "word/footnotes.xml" in names)
    fn_xml = zipfile.ZipFile(path).read("word/footnotes.xml").decode("utf-8")
    check("فونت پیش‌فرض Times New Roman است", "Times New Roman" in fn_xml)
    body = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    check("«پانوشت‌ها»ی جعلیِ انتهای سند تکرار نشده (چون پاورقی واقعی هست)",
          "پانوشت‌ها" not in body)
    check("سند سالم باز می‌شود", len(Document(path).paragraphs) > 0)

    # رفتار پیش‌فرض (real_footnotes=False) باید دقیقاً مثل قبل بماند
    name2 = design_engine.build_designed_docx(blocks, spec, title="تست قدیمی", font_size=13,
                                              align="justify", toc=False, numbering=False)
    names2 = zipfile.ZipFile(os.path.join(export_utils.EXPORT_DIR, name2)).namelist()
    check("پیش‌فرض بدون real_footnotes، footnotes.xml نمی‌سازد (رفتار قبلی حفظ شد)",
          "word/footnotes.xml" not in names2)
    body2 = zipfile.ZipFile(os.path.join(export_utils.EXPORT_DIR, name2)).read(
        "word/document.xml").decode("utf-8")
    check("پیش‌فرض همچنان «پانوشت‌ها»ی انتهای سند را می‌سازد (رفتار قبلی حفظ شد)",
          "پانوشت‌ها" in body2)


def test_cross_section_id_collision():
    section("۷) شناسه‌ی پاورقیِ تکراری بین دو «بخش» مقاله با هم تداخل نمی‌کند")
    import export_utils
    import design_engine

    # این دقیقاً همان چیزی است که main._citation_footnote_rule جلویش را می‌گیرد:
    # هر بخشِ مقاله جداگانه نوشته می‌شود و از شماره‌ی پاورقیِ بخش‌های دیگر خبر ندارد.
    article_prefixed = (
        "# موضوع\n\n"
        "## بخش اول\n\nطبق نظریه‌ی پورتر[^s1-1]، مزیت رقابتی...\n\n[^s1-1]: Porter, M. E.\n\n"
        "## بخش دوم\n\nکاتلر[^s2-1] در تعریف بازاریابی می‌گوید...\n\n[^s2-1]: Kotler, P.\n"
    )
    blocks = export_utils.md_to_blocks(article_prefixed)
    name = export_utils.build_docx(blocks, "Vazirmatn", 14, "تست ارجاع", "right", True, True, True)
    fn_xml = zipfile.ZipFile(os.path.join(export_utils.EXPORT_DIR, name)).read(
        "word/footnotes.xml").decode("utf-8")
    check("با پیشوندِ بخش، هر دو نویسنده پاورقیِ جدا دارند",
          "Porter, M. E." in fn_xml and "Kotler, P." in fn_xml)

    # اثبات اینکه پیشوند واقعاً لازم است: بدون آن، دومی اولی را جای‌زده می‌کند
    article_unprefixed = (
        "# موضوع\n\n"
        "## بخش اول\n\nطبق نظریه‌ی پورتر[^1]، مزیت رقابتی...\n\n[^1]: Porter, M. E.\n\n"
        "## بخش دوم\n\nکاتلر[^1] در تعریف بازاریابی می‌گوید...\n\n[^1]: Kotler, P.\n"
    )
    blocks2 = export_utils.md_to_blocks(article_unprefixed)
    name2 = export_utils.build_docx(blocks2, "Vazirmatn", 14, "تست خراب", "right", True, True, True)
    fn_xml2 = zipfile.ZipFile(os.path.join(export_utils.EXPORT_DIR, name2)).read(
        "word/footnotes.xml").decode("utf-8")
    check("بدون پیشوند، همان مشکلی که انتظار می‌رفت رخ می‌دهد (اثباتِ ضرورتِ پیشوند)",
          "Porter, M. E." not in fn_xml2 and "Kotler, P." in fn_xml2)

    # همان آزمون روی مسیر طراحی‌شده هم
    spec = design_engine.build_spec(topic="بازاریابی")
    name3 = design_engine.build_designed_docx(blocks, spec, title="طراحی‌شده", font_size=13,
                                              align="justify", toc=False, numbering=False,
                                              real_footnotes=True)
    fn_xml3 = zipfile.ZipFile(os.path.join(export_utils.EXPORT_DIR, name3)).read(
        "word/footnotes.xml").decode("utf-8")
    check("در مسیر طراحی‌شده هم هر دو نویسنده با پیشوند جدا می‌مانند",
          "Porter, M. E." in fn_xml3 and "Kotler, P." in fn_xml3)


def test_citation_rule_prompt():
    section("۸) دستورِ پرامپت برای پاورقی نویسنده‌ی خارجی")
    import main

    r1 = main._citation_footnote_rule(1)
    r2 = main._citation_footnote_rule(2)
    check("پیشوند شامل شماره‌ی بخش است", "s1-1" in r1 and "s2-1" in r2)
    check("دو بخشِ مختلف پیشوند متفاوت می‌گیرند (کلید اصلی جلوگیری از تداخل)",
          "s1-1" in r1 and "s1-1" not in r2)
    check("قاعده به فارسی‌نویسیِ نام در متن تصریح دارد", "فارسی معیار بنویس" in r1)
    check("قاعده مثال نام لاتین در تعریف پاورقی دارد", "Porter" in r1)


def test_longdoc_endpoint_uses_real_footnotes():
    section("۹) سرتاسری: /api/longdoc واقعاً پاورقیِ صفحه‌ی واقعی می‌سازد")
    from fastapi.testclient import TestClient
    import main
    import db as D
    import export_utils
    import re as _re

    conn = D.get_db()
    u = conn.execute("SELECT id FROM users WHERE is_admin = 0 LIMIT 1").fetchone()
    if u:
        # سهمیه‌ی «مقاله بلند» را برای این کاربرِ آزمایشی صفر می‌کنیم — وگرنه اجراهای
        # قبلی همین آزمون (یا آزمون‌های دستی) سهمیه‌ی روزانه را مصرف کرده‌اند و
        # درخواست با ۴۲۹ رد می‌شود، که ربطی به درستیِ کد ندارد.
        conn.execute("DELETE FROM usage_log WHERE user_id = ? AND kind = 'article'", (u["id"],))
        conn.commit()
    conn.close()
    if not u:
        print("  ⏭  کاربر آزمایشی پیدا نشد — این بخش رد شد.")
        return

    saved_catalog = main.get_ai_catalog
    saved_call = main._call_model_once
    main.get_ai_catalog = lambda: [{"id": "x", "key": "fake", "model": "m",
                                    "base": "https://example.invalid/v1", "name": "F"}]

    async def fake_call(c, prompt=None, system=None, max_tokens=1500, **kw):
        # نکته: پرامپتِ هر بخش هم رشته‌ی «عنوان بخش» را دارد (در جمله‌ی
        # «خودِ عنوان بخش را ننویس» که در کد اصلی هست)، پس شرط‌های اختصاصی‌تر
        # باید اول بررسی شوند، وگرنه هر سه پرامپت به شرط فهرست می‌خورند.
        p = prompt or ""
        if "بخش «مقدمه»" in p:
            return "طبق نظریه‌ی پورتر[^s1-1] چنین است.\n\n[^s1-1]: Porter, M. E."
        if "بخش «یافته‌ها»" in p:
            return "کاتلر[^s2-1] می‌گوید.\n\n[^s2-1]: Kotler, P."
        if "دقیقاً" in p and "عنوان بخش بنویس" in p:
            return "مقدمه\nیافته‌ها"
        return "متن نمونه"

    main._call_model_once = fake_call
    try:
        c = TestClient(main.app)
        c.cookies.set("antanu_session", main.make_session(u["id"]))
        with c.stream("POST", "/api/longdoc",
                      json={"topic": "بازاریابی", "pages": 4, "formats": ["docx"]}) as r:
            text = "".join(r.iter_text())
        check("درخواست موفق بود", r.status_code == 200)
        m = _re.search(r"/download/([\w.-]+\.docx)", text)
        check("لینک دانلود Word در پاسخ هست", bool(m))
        if m:
            path = os.path.join(export_utils.EXPORT_DIR, m.group(1))
            names = zipfile.ZipFile(path).namelist()
            check("فایل نهایی پاورقی واقعی دارد", "word/footnotes.xml" in names)
            if "word/footnotes.xml" in names:
                fn_xml = zipfile.ZipFile(path).read("word/footnotes.xml").decode("utf-8")
                check("هر دو نویسنده در پاورقی‌ها هستند (بدون تداخل بین بخش‌ها)",
                      "Porter, M. E." in fn_xml and "Kotler, P." in fn_xml)
                check("فونت پاورقی Times New Roman است", "Times New Roman" in fn_xml)
    finally:
        main.get_ai_catalog = saved_catalog
        main._call_model_once = saved_call


def main_run():
    print("═" * 68)
    print("  آزمون پاورقی واقعی Word")
    print("═" * 68)
    test_default_style()
    test_customizable()
    test_valid_xml_order()
    test_docx_opens_cleanly()
    test_no_footnotes_untouched()
    test_design_engine_real_footnotes()
    test_cross_section_id_collision()
    test_citation_rule_prompt()
    test_longdoc_endpoint_uses_real_footnotes()

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
