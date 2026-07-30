# -*- coding: utf-8 -*-
"""
test_digits.py — آزمون ارقامِ زبان‌آگاه (فارسی برای خروجی فارسی، انگلیسی برای بقیه).

قبل از این تغییر، export_utils/design_engine/stats_report هر عددی را همیشه به
فارسی تبدیل می‌کردند، حتی برای کاربری که سایت را روی انگلیسی (یا هر زبان دیگری)
گذاشته بود. i18n.to_local_digits این را با یک contextvar مشترک (همان الگوی
_lang_ctx که main.py برای فیلتر متن خارجی دارد) شرطی می‌کند.

اجرا:  python test_digits.py
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


def test_core():
    section("۱) i18n.to_local_digits — تبدیل صریح و از روی زمینه")
    import i18n

    t = i18n.to_local_digits
    check("fa صریح: انگلیسی→فارسی", t("Test 123", "fa") == "Test ۱۲۳")
    check("en صریح: فارسی→انگلیسی", t("تست ۱۲۳", "en") == "تست 123")
    check("fa صریح روی رقم فارسیِ موجود بی‌اثر است", t("۴۵۶", "fa") == "۴۵۶")
    check("زبان ناشناخته هم مثل غیرفارسی، انگلیسی می‌شود", t("۴۵۶", "de") == "456")
    check("عدد صحیح هم می‌پذیرد (نه فقط رشته)", t(42, "fa") == "۴۲")

    i18n.set_digit_lang("en")
    check("زمینه: بعد از set_digit_lang('en')", t("123 و ۴۵۶") == "123 و 456")
    i18n.set_digit_lang("fa")
    check("زمینه: بعد از set_digit_lang('fa')", t("123") == "۱۲۳")
    i18n.set_digit_lang(None)
    check("set_digit_lang(None) → پیش‌فرض fa (رفتار قبلی حفظ می‌شود)", t("123") == "۱۲۳")
    i18n.set_digit_lang("fa")  # حالت پیش‌فرض را برای آزمون‌های بعدی برمی‌گردانیم


def test_delegates():
    section("۲) ماژول‌های صادرکننده به i18n.to_local_digits واگذار می‌کنند")
    import i18n
    import export_utils
    import design_engine
    import stats_report

    for lang, want_fn in (("fa", lambda s: s.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))),
                          ("en", lambda s: s)):
        i18n.set_digit_lang(lang)
        check(f"export_utils._to_fa_digits ({lang})",
              export_utils._to_fa_digits("12") == want_fn("12"))
        check(f"export_utils._to_fa_digits_mod ({lang})",
              export_utils._to_fa_digits_mod(3) == want_fn("3"))
        check(f"design_engine._fa_digits ({lang})",
              design_engine._fa_digits("7") == want_fn("7"))
        check(f"stats_report._fa ({lang})",
              stats_report._fa(9) == want_fn("9"))
    i18n.set_digit_lang("fa")


def test_report_language():
    section("۳) گزارش آماری کامل: همان عدد، دو زبان متفاوت")
    import i18n
    import stats_report

    result = {"analysis": "ttest", "title": "آزمون تی",
              "result": {"t": 2.451, "p": 0.013, "software": "معادل SPSS"}}

    i18n.set_digit_lang("fa")
    r_fa = stats_report.build_report([result])
    i18n.set_digit_lang("en")
    r_en = stats_report.build_report([result])
    i18n.set_digit_lang("fa")

    check("گزارش فارسی: مقدار محاسبه‌شده با رقم فارسی", "۲.۴۵۱" in r_fa)
    check("گزارش انگلیسی: همان مقدار با رقم انگلیسی", "2.451" in r_en)
    # راهنمای نشانه‌ها (ستاره‌های معناداری) هم باید از زبان گزارش پیروی کند —
    # قبلاً این خط با ۰٫۰۱/۰٫۰۵ ثابت داخل کد نوشته شده بود و به هیچ زبانی
    # واکنش نمی‌داد؛ حالا باید در گزارش انگلیسی هم رقم انگلیسی داشته باشد.
    legend_en = r_en.rsplit("<small>", 1)[-1]
    check("راهنمای نشانه‌ها در گزارش انگلیسی رقم انگلیسی دارد (0.01)", "0.01" in legend_en)
    check("راهنمای نشانه‌ها در گزارش انگلیسی رقم فارسی ندارد",
          not re.search(r"[۰-۹]", legend_en))
    legend_fa = r_fa.rsplit("<small>", 1)[-1]
    check("راهنمای نشانه‌ها در گزارش فارسی رقم فارسی دارد (۰٫۰۱)", "۰٫۰۱" in legend_fa)


def test_end_to_end_export():
    section("۴) سرتاسری: /api/export با کاربر انگلیسی و فارسی")
    from fastapi.testclient import TestClient
    import main
    import db as D
    import export_utils

    conn = D.get_db()
    u = conn.execute("SELECT id FROM users WHERE is_admin = 0 LIMIT 1").fetchone()
    conn.close()
    if not u:
        print("  ⏭  کاربر آزمایشی پیدا نشد — این بخش رد شد.")
        return

    c = TestClient(main.app)
    c.cookies.set("antanu_session", main.make_session(u["id"]))
    content = "# Chapter One\n\nBody text.\n\n# Chapter Two\n\nBody text."

    def build_for(lang):
        db = D.get_db()
        db.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, u["id"]))
        db.commit()
        db.close()
        r = c.post("/api/export", json={"content": content, "formats": ["docx"],
                                        "title": "T", "toc": True, "numbering": True})
        name = r.json()["files"][0]["url"].split("/")[-1]
        path = os.path.join(export_utils.EXPORT_DIR, name)
        xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
        return re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)

    texts_en = build_for("en")
    texts_fa = build_for("fa")

    check("کاربر انگلیسی: شماره‌ی سرفصل با رقم انگلیسی («1- »)",
          any(x.startswith("1- Chapter One") for x in texts_en), str(texts_en[:3]))
    check("کاربر فارسی: همان سند، شماره‌ی سرفصل با رقم فارسی («۱- »)",
          any(x.startswith("۱- Chapter One") for x in texts_fa), str(texts_fa[:3]))
    check("کاربر انگلیسی هیچ رقم فارسی‌ای در سرفصل‌ها ندارد",
          not any(re.search(r"[۰-۹]", x) for x in texts_en if "Chapter" in x))


def main_run():
    print("═" * 68)
    print("  آزمون ارقام زبان‌آگاه")
    print("═" * 68)
    test_core()
    test_delegates()
    test_report_language()
    test_end_to_end_export()

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
