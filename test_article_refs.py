# -*- coding: utf-8 -*-
"""
test_article_refs.py — آزمون اتصال منابع علمیِ واقعی (Crossref/OpenAlex) به مقاله.

قبل از این تغییر، بخش «منابع» مقاله‌ی بلند کاملاً از دانش منجمدِ مدل نوشته
می‌شد — دقیقاً همان چیزی که کاربر نگرانش بود: اگر منبعِ سال ۲۰۲۵/۲۰۲۶ خواسته
شود، یا مدل رد می‌کند («دسترسی ندارم») یا ممکن است منبعِ باورپذیر ولی جعلی
بسازد. حالا پیش از نوشتن بخشِ منابع، جست‌وجوی واقعی با lookup_reference_online
(همان تابعی که ابزار «ارجاع‌دهی» هم استفاده می‌کند) انجام می‌شود و مدل فقط
همان نتایج را فهرست می‌کند.

نکته: api.crossref.org و api.openalex.org در محیط توسعه‌ی این آزمون توسط
سیاست شبکه مسدودند (تأییدشده با /__agentproxy/status)، پس اینجا
lookup_reference_online با داده‌ی ساختگیِ هم‌شکل با خروجی واقعی جایگزین
می‌شود. **دسترسی واقعی به این دو API باید روی سرورِ خودت تأیید شود:**
    python -c "import asyncio, main; print(asyncio.run(main.lookup_reference_online('machine learning')))"

اجرا:  python test_article_refs.py
"""
import os
import sys
import warnings

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


# ═══════════════ ۱) دستور صداقتِ ارجاع در پرامپت پایه ═══════════════

def test_system_prompt_rule():
    section("۱) قاعده‌ی صداقتِ ارجاع در BASE_SYSTEM_PROMPT")
    import main
    p = main.BASE_SYSTEM_PROMPT
    check("قاعده‌ی صداقتِ ارجاع هست", "صداقتِ ارجاع" in p)
    check("منع صریح ساختن منبع/DOI جعلی هست", "ساختگی" in p and "DOI" in p)
    check("راهنمایی برای درخواستِ منبعِ ۲۰۲۵/۲۰۲۶ هست", "۲۰۲۵" in p or "۲۰۲۶" in p)
    check("اشاره به Crossref/OpenAlex هست", "Crossref" in p and "OpenAlex" in p)


def test_auto_search_words():
    section("۲) درخواستِ منبعِ تازه، جستجوی وبِ خودکار را روشن می‌کند")
    import main
    cases = [
        "منابع جدید ۲۰۲۵ درباره‌ی هوش مصنوعی می‌خوام",
        "یک مقاله جدید در این زمینه معرفی کن",
        "پژوهش جدید در حوزه بازاریابی چیه",
        "رفرنس جدید برای این موضوع بده",
    ]
    for msg in cases:
        hit = any(w in msg for w in main.AUTO_SEARCH_WORDS)
        check(f"«{msg[:35]}…» جستجوی وب را روشن می‌کند", hit)


# ═══════════════ ۳) واکشیِ منابع واقعی روی مقاله ═══════════════

def test_references_wired_into_article():
    section("۳) سرتاسری: بخش «منابع» فقط از نتایج واقعیِ Crossref/OpenAlex نوشته می‌شود")
    from fastapi.testclient import TestClient
    import main

    u = _test_user()
    if not u:
        print("  ⏭  کاربر آزمایشی پیدا نشد — این بخش رد شد.")
        return

    main.get_ai_catalog = lambda: [{"id": "x", "key": "fake", "model": "m",
                                    "base": "https://example.invalid/v1", "name": "F"}]

    async def fake_lookup(q):
        return [
            {"ref_type": "article", "authors": "Porter M. E.", "title": "Competitive Strategy",
             "year": "2025", "source": "Journal of Management", "url": "https://doi.org/10.1/abc"},
            {"ref_type": "article", "authors": "Kotler P.", "title": "Modern Marketing 6.0",
             "year": "2026", "source": "Marketing Review", "url": "https://doi.org/10.1/xyz"},
        ]
    main.lookup_reference_online = fake_lookup

    async def fake_call(cc, prompt=None, system=None, max_tokens=1500, **kw):
        p = prompt or ""
        if "دقیقاً" in p and "عنوان بخش بنویس" in p:
            return "چکیده\nمقدمه\nمنابع"
        if "بخش «منابع»" in p:
            if "Competitive Strategy" not in p or "Modern Marketing 6.0" not in p:
                raise AssertionError("منابع واقعی در پرامپت نبود")
            if "هرگز DOI یا نویسنده‌ی ساختگی نساز" not in p:
                raise AssertionError("دستور منع ساختن منبع جعلی نبود")
            return "- پورتر (۲۰۲۵). استراتژی رقابتی. مجله مدیریت.\n- کاتلر (۲۰۲۶). بازاریابی مدرن ۶.۰."
        return "متن نمونه‌ی این بخش."
    main._call_model_once = fake_call

    c = TestClient(main.app)
    c.cookies.set("antanu_session", main.make_session(u["id"]))
    with c.stream("POST", "/api/longdoc",
                  json={"topic": "بازاریابی نوین", "pages": 4, "formats": ["docx"]}) as r:
        text = "".join(r.iter_text())

    check("درخواست موفق بود", r.status_code == 200)
    check("گام جست‌وجوی منابع علمی اجرا شد", "جست‌وجوی منابع علمی واقعی" in text)
    check("تعداد منابع واقعی گزارش شد", "2 منبع علمیِ واقعی پیدا شد" in text, text[:400])
    check("مقاله ساخته شد", "مقاله آماده شد" in text)


def test_no_results_is_honest_not_broken():
    section("۴) نتیجه‌ی خالی از جست‌وجو: مقاله نمی‌ترکد و صادقانه اعلام می‌شود")
    from fastapi.testclient import TestClient
    import main

    u = _test_user()
    if not u:
        print("  ⏭  کاربر آزمایشی پیدا نشد — این بخش رد شد.")
        return

    main.get_ai_catalog = lambda: [{"id": "x", "key": "fake", "model": "m",
                                    "base": "https://example.invalid/v1", "name": "F"}]

    async def fake_lookup_empty(q):
        return []
    main.lookup_reference_online = fake_lookup_empty

    async def fake_call(cc, prompt=None, system=None, max_tokens=1500, **kw):
        p = prompt or ""
        if "دقیقاً" in p and "عنوان بخش بنویس" in p:
            return "چکیده\nمنابع"
        if "بخش «منابع»" in p:
            if "منبعِ تأییدشده‌ای در دسترس نبود" not in p:
                raise AssertionError("راهنمای صداقت برای نبود منبع نیامد")
            return "این بخش بدون منبع تأییدشده نوشته شد."
        return "متن نمونه."
    main._call_model_once = fake_call

    c = TestClient(main.app)
    c.cookies.set("antanu_session", main.make_session(u["id"]))
    with c.stream("POST", "/api/longdoc",
                  json={"topic": "موضوعی بسیار نامتعارف", "pages": 2, "formats": ["docx"]}) as r:
        text = "".join(r.iter_text())

    check("درخواست موفق بود", r.status_code == 200)
    check("نبودِ نتیجه صادقانه اعلام شد", "نتیجه‌ای نداد" in text)
    check("مقاله همچنان ساخته شد", "مقاله آماده شد" in text)


def test_lookup_exception_is_graceful():
    section("۵) خطای شبکه در جست‌وجوی منبع، کل مقاله را نمی‌شکند")
    from fastapi.testclient import TestClient
    import main

    u = _test_user()
    if not u:
        print("  ⏭  کاربر آزمایشی پیدا نشد — این بخش رد شد.")
        return

    main.get_ai_catalog = lambda: [{"id": "x", "key": "fake", "model": "m",
                                    "base": "https://example.invalid/v1", "name": "F"}]

    async def fake_lookup_error(q):
        raise ConnectionError("شبکه در دسترس نیست")
    main.lookup_reference_online = fake_lookup_error

    async def fake_call(cc, prompt=None, system=None, max_tokens=1500, **kw):
        p = prompt or ""
        if "دقیقاً" in p and "عنوان بخش بنویس" in p:
            return "چکیده\nمنابع"
        return "متن نمونه."
    main._call_model_once = fake_call

    c = TestClient(main.app)
    c.cookies.set("antanu_session", main.make_session(u["id"]))
    with c.stream("POST", "/api/longdoc",
                  json={"topic": "تست خطای شبکه", "pages": 2, "formats": ["docx"]}) as r:
        text = "".join(r.iter_text())

    check("درخواست موفق بود (بدون کرش)", r.status_code == 200)
    check("مقاله همچنان ساخته شد", "مقاله آماده شد" in text)


def main_run():
    print("═" * 68)
    print("  آزمون اتصال منابع علمی واقعی به مقاله")
    print("═" * 68)
    test_system_prompt_rule()
    test_auto_search_words()
    test_references_wired_into_article()
    test_no_results_is_honest_not_broken()
    test_lookup_exception_is_graceful()

    print("\n" + "═" * 68)
    print(f"  نتیجه: {len(PASS)} پاس، {len(FAIL)} ناموفق")
    if FAIL:
        print("  ناموفق‌ها:")
        for f in FAIL:
            print("    ✗", f)
    print("  ⚠ دسترسیِ واقعیِ api.crossref.org و api.openalex.org روی این سرور تأیید نشد "
          "(در این محیط توسعه مسدودند). روی سرور خودت با دستور بالای فایل چک کن.")
    print("═" * 68)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main_run())
