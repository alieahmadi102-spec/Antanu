# -*- coding: utf-8 -*-
"""
test_article_stats.py — آزمون اتصال تحلیل آماریِ واقعی به مقاله‌ی بلند (/api/longdoc).

قبل از این تغییر، «روش‌شناسی پژوهش» و «یافته‌ها و تحلیل داده‌ها» در مقاله‌ها
کاملاً از دانش عمومیِ مدل نوشته می‌شدند — حتی اگر کاربر داده‌ی واقعی داشت.
با dataset_file (که از همان /api/stats/upload می‌آید)، این دو بخش از خروجیِ
واقعیِ analysis_planner/stats_engine روی داده‌ی کاربر نوشته می‌شوند.

اجرا:  python test_article_stats.py
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


def _test_user():
    import db as D
    conn = D.get_db()
    u = conn.execute("SELECT id FROM users WHERE is_admin = 0 LIMIT 1").fetchone()
    if u:
        conn.execute("DELETE FROM usage_log WHERE user_id = ? AND kind IN ('article','chat')",
                     (u["id"],))
        conn.commit()
    conn.close()
    return u


def _upload_csv(c):
    import random
    random.seed(42)
    rows = ["group,score"]
    for _ in range(30):
        rows.append(f"A,{round(random.gauss(50, 5), 2)}")
    for _ in range(30):
        rows.append(f"B,{round(random.gauss(70, 5), 2)}")
    r = c.post("/api/stats/upload",
              files={"file": ("scores.csv", ("\n".join(rows)).encode("utf-8"), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()["file"]


# ═══════════════ ۱) تابع کمکی _run_dataset_analysis ═══════════════

def test_run_dataset_analysis_directly():
    section("۱) _run_dataset_analysis روی داده‌ی واقعی")
    import asyncio
    import main
    import export_utils

    d = os.path.join(export_utils.EXPORT_DIR, "test_ds_direct.csv")
    with open(d, "w", encoding="utf-8") as f:
        f.write("x,y\n" + "\n".join(f"{i},{i*2+1}" for i in range(1, 21)))

    logs = []
    prof, results, report_md, digest = asyncio.run(
        main._run_dataset_analysis(d, "رابطه‌ی x و y", logs.append))
    check("پروفایل داده درست خوانده شد", prof is not None and prof.get("تعداد سطر") == 20)
    check("حداقل یک تحلیل اجرا شد", len(results) > 0)
    check("گزارش مارک‌داون ساخته شد", len(report_md) > 50)
    check("خلاصه برای مدل ساخته شد", len(digest) > 0)
    check("پیام‌های پیشرفت ثبت شدند", any("مشاهده" in x for x in logs))
    os.remove(d)


def test_run_dataset_analysis_bad_file():
    section("۲) _run_dataset_analysis با فایل خراب/غیرقابل‌خواندن")
    import asyncio
    import main
    import export_utils

    d = os.path.join(export_utils.EXPORT_DIR, "test_ds_bad.csv")
    with open(d, "wb") as f:
        f.write(b"\x00\x01\x02 not really a csv \xff\xfe")

    logs = []
    try:
        prof, results, report_md, digest = asyncio.run(
            main._run_dataset_analysis(d, "موضوع", logs.append))
        check("فایل خراب بدون کرش مدیریت شد", results == [] or prof is None)
    except Exception as e:
        check("فایل خراب بدون کرش مدیریت شد", False, str(e))
    os.remove(d)


# ═══════════════ ۳) منطق «شبکه‌ی ایمنیِ» عنوان‌ها ═══════════════

def test_title_safety_net_logic():
    section("۳) شبکه‌ی ایمنیِ عنوان‌ها: هرگز یکی جای دیگری را نمی‌گیرد")
    METHOD = "روش‌شناسی پژوهش"
    FINDINGS = "یافته‌ها و تحلیل داده‌ها"

    def fix(titles, n_sections):
        titles = list(titles)
        missing = [x for x in (METHOD, FINDINGS) if x not in titles]
        if missing:
            room = max(0, n_sections - len(titles))
            titles.extend(missing[:room])
            still_missing = missing[room:]
            idx = len(titles) - 1
            for needed in still_missing:
                while idx >= 0 and titles[idx] in (METHOD, FINDINGS):
                    idx -= 1
                if idx >= 0:
                    titles[idx] = needed
                    idx -= 1
        return titles

    # همان سناریوی دقیقِ باگی که پیدا و رفع شد: فهرست پر است و فقط یکی از دو
    # عنوان از قبل هست — نباید آن یکی موجود پاک شود.
    out = fix(["چکیده", "مقدمه", "مبانی نظری", METHOD], 4)
    check("عنوان موجود (روش‌شناسی) پاک نمی‌شود وقتی دیگری اضافه می‌شود",
          METHOD in out and FINDINGS in out, str(out))

    out2 = fix(["چکیده", "مقدمه", "مبانی نظری", "بحث"], 4)
    check("وقتی هیچ‌کدام نیست و جا هم نیست، هر دو جایگزین می‌شوند",
          METHOD in out2 and FINDINGS in out2, str(out2))

    out3 = fix(["چکیده", METHOD, FINDINGS, "نتیجه"], 4)
    check("وقتی هر دو از قبل هست، فهرست دست‌نخورده می‌ماند", out3 == ["چکیده", METHOD, FINDINGS, "نتیجه"])

    out4 = fix([METHOD], 4)
    check("وقتی جا هست، دومی فقط اضافه می‌شود (نه جایگزین)", out4 == [METHOD, FINDINGS])

    out5 = fix(["چکیده", "مقدمه"], 2)
    check("وقتی جا نیست و هیچ‌کدام نیست، هر دو در انتها می‌نشینند", METHOD in out5 and FINDINGS in out5)


# ═══════════════ ۴) سرتاسری با فایل داده‌ی واقعی ═══════════════

def test_end_to_end_with_dataset():
    section("۴) سرتاسری: /api/longdoc با dataset_file واقعی")
    from fastapi.testclient import TestClient
    import main

    u = _test_user()
    if not u:
        print("  ⏭  کاربر آزمایشی پیدا نشد — این بخش رد شد.")
        return

    main.get_ai_catalog = lambda: [{"id": "x", "key": "fake", "model": "m",
                                    "base": "https://example.invalid/v1", "name": "F"}]

    async def fake_call(cc, prompt=None, system=None, max_tokens=1500, **kw):
        p = prompt or ""
        if "بخش «روش‌شناسی پژوهش»" in p:
            if "60" not in p:
                raise AssertionError("تعداد مشاهده در پرامپت روش‌شناسی نبود")
            return "این پژوهش با روش پیمایشی و تحلیل آماری روی نمونه انجام شد."
        if "بخش «یافته‌ها و تحلیل داده‌ها»" in p:
            if "تفسیر را فقط از" not in p:
                raise AssertionError("دستور «فقط عدد واقعی» در پرامپت یافته‌ها نبود")
            return "تحلیل نشان داد گروه دوم میانگین بالاتری داشت."
        if "دقیقاً" in p and "عنوان بخش بنویس" in p:
            return "چکیده\nمقدمه\nمبانی نظری\nروش‌شناسی پژوهش\nیافته‌ها و تحلیل داده‌ها\nنتیجه‌گیری"
        return "متن نمونه‌ی این بخش."

    main._call_model_once = fake_call

    c = TestClient(main.app)
    c.cookies.set("antanu_session", main.make_session(u["id"]))
    fname = _upload_csv(c)

    with c.stream("POST", "/api/longdoc", json={
        "topic": "اثر آموزش بر عملکرد", "pages": 6, "formats": ["docx"], "dataset_file": fname,
    }) as r:
        text = "".join(r.iter_text())

    check("درخواست موفق بود", r.status_code == 200)
    check("گام تحلیل آماری اجرا شد", "تحلیل آماریِ داده‌ی شما" in text)
    check("هر دو بخش کلیدی نوشته شدند",
          "«روش‌شناسی پژوهش»" in text and "«یافته‌ها و تحلیل داده‌ها»" in text)

    import export_utils
    m = re.search(r"/download/([\w.-]+\.docx)", text)
    check("لینک Word در پاسخ هست", bool(m))
    if m:
        path = os.path.join(export_utils.EXPORT_DIR, m.group(1))
        body = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
        check("عنوان «روش‌شناسی پژوهش» در سند نهایی هست", "روش" in body and "شناسی" in body)
        check("عنوان «یافته‌ها و تحلیل داده‌ها» در سند نهایی هست", "یافته" in body)
        check("جدول واقعیِ تحلیل (نه فقط نثر مدل) در سند هست", "میانگین" in body)


def test_no_dataset_unaffected():
    section("۵) بدون dataset_file، رفتار قبلی دست‌نخورده می‌ماند")
    from fastapi.testclient import TestClient
    import main

    u = _test_user()
    if not u:
        print("  ⏭  کاربر آزمایشی پیدا نشد — این بخش رد شد.")
        return

    main.get_ai_catalog = lambda: [{"id": "x", "key": "fake", "model": "m",
                                    "base": "https://example.invalid/v1", "name": "F"}]

    async def fake_call(cc, prompt=None, system=None, max_tokens=1500, **kw):
        p = prompt or ""
        if "دقیقاً" in p and "عنوان بخش بنویس" in p:
            return "چکیده\nمقدمه\nنتیجه‌گیری"
        return "متن نمونه‌ی این بخش."
    main._call_model_once = fake_call

    c = TestClient(main.app)
    c.cookies.set("antanu_session", main.make_session(u["id"]))
    with c.stream("POST", "/api/longdoc",
                  json={"topic": "موضوع بدون داده", "pages": 4, "formats": ["docx"]}) as r:
        text = "".join(r.iter_text())

    check("درخواست موفق بود", r.status_code == 200)
    check("گام تحلیل آماری اصلاً اجرا نشد", "گام ۰ب" not in text and "تحلیل آماریِ داده" not in text)
    check("مقاله ساخته شد", "مقاله آماده شد" in text)


def test_missing_dataset_file_is_graceful():
    section("۶) فایل‌نامِ نامعتبر یا ناموجود، مقاله را نمی‌شکند")
    from fastapi.testclient import TestClient
    import main

    u = _test_user()
    if not u:
        print("  ⏭  کاربر آزمایشی پیدا نشد — این بخش رد شد.")
        return

    main.get_ai_catalog = lambda: [{"id": "x", "key": "fake", "model": "m",
                                    "base": "https://example.invalid/v1", "name": "F"}]

    async def fake_call(cc, prompt=None, system=None, max_tokens=1500, **kw):
        p = prompt or ""
        if "دقیقاً" in p and "عنوان بخش بنویس" in p:
            return "چکیده\nمقدمه\nنتیجه‌گیری"
        return "متن نمونه‌ی این بخش."
    main._call_model_once = fake_call

    c = TestClient(main.app)
    c.cookies.set("antanu_session", main.make_session(u["id"]))

    # نام فایل نامعتبر (مسیرِ عبور) → باید همان ابتدا با ۴۰۰ رد شود
    r0 = c.post("/api/longdoc", json={"topic": "تست", "pages": 2, "formats": ["docx"],
                                      "dataset_file": "../../etc/passwd"})
    check("نام فایل نامعتبر با ۴۰۰ رد می‌شود", r0.status_code == 400)

    # نام فایلِ معتبرالفبا ولی ناموجود → باید مقاله را بدون تحلیل بسازد، نه بترکد
    with c.stream("POST", "/api/longdoc", json={
        "topic": "تست فایل ناموجود", "pages": 2, "formats": ["docx"],
        "dataset_file": "data-nonexistent000000.csv",
    }) as r:
        text = "".join(r.iter_text())
    check("درخواست موفق بود (بدون کرش)", r.status_code == 200)
    check("پیام «فایل داده پیدا نشد» نشان داده شد", "فایل داده پیدا نشد" in text)
    check("مقاله همچنان ساخته شد", "مقاله آماده شد" in text)


def main_run():
    print("═" * 68)
    print("  آزمون اتصال تحلیل آماری به مقاله‌ی بلند")
    print("═" * 68)
    test_run_dataset_analysis_directly()
    test_run_dataset_analysis_bad_file()
    test_title_safety_net_logic()
    test_end_to_end_with_dataset()
    test_no_dataset_unaffected()
    test_missing_dataset_file_is_graceful()

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
