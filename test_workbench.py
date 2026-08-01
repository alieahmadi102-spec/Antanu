# -*- coding: utf-8 -*-
"""
test_workbench.py — آزمون میزکارهای نرم‌افزاری (SPSS / EViews / SmartPLS)

چه چیزهایی سنجیده می‌شود:
  ۱) درستی پیکربندی منوها: هر تحلیلِ منو واقعاً در موتورها موجود و مجاز باشد
  ۲) شبکه‌ی داده: ذخیره/خواندن رفت‌وبرگشتی با ستون فارسی و نام تکراری
  ۳) صفحه‌های /spss /eviews /smartpls برای کاربر واردشده باز شوند
  ۴) فهرست داده‌ها: آپلود ثبت شود؛ داده‌ی کاربرِ دیگر قابل خواندن نباشد (۴۰۳)
  ۵) اجرای تحلیل از مسیر واقعی API (ANOVA و PLS) و ساخت نمودار PLS از کلیدهای فارسی

اجرا:  python test_workbench.py
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
        conn.execute("DELETE FROM usage_log WHERE user_id = ?", (u["id"],))
        conn.commit()
    conn.close()
    return u


def _sample_grid():
    """داده‌ی نمونه با سه گروه واقعی و چهار گویه‌ی لیکرت."""
    import random
    random.seed(11)
    cols = ["گروه", "نمره", "q1", "q2", "q3", "q4"]
    rows = []
    for i in range(45):
        g = ["الف", "ب", "ج"][i % 3]
        base = {"الف": 12, "ب": 14, "ج": 16}[g]
        q1 = random.randint(2, 5)
        rows.append([g, round(base + random.gauss(0, 1.5), 2), q1,
                     min(5, max(1, q1 + random.choice([-1, 0, 1]))),
                     random.randint(2, 5), random.randint(2, 5)])
    return cols, rows


# ═══════════════ ۱) درستی پیکربندی منوها ═══════════════

def test_config_integrity():
    section("۱) هر تحلیلِ منو در موتورها موجود و برای همان میزکار مجاز است")
    import workbench, stats_engine
    available = set(stats_engine.available_analyses())

    def leaves(items):
        for it in items:
            if it.get("children"):
                yield from leaves(it["children"])
            elif it.get("analysis"):
                yield it

    bad_missing, bad_disallowed, bad_fields = [], [], []
    for sw_id, sw in workbench.SOFTWARES.items():
        for menu in sw["menus"]:
            for leaf in leaves(menu.get("items", [])):
                a = leaf["analysis"]
                if a not in available:
                    bad_missing.append(f"{sw_id}:{a}")
                if a not in workbench.ALLOWED[sw_id]:
                    bad_disallowed.append(f"{sw_id}:{a}")
                for f in leaf.get("fields", []):
                    if f.get("type") not in ("col", "cols", "select", "number", "text", "check"):
                        bad_fields.append(f"{sw_id}:{a}:{f.get('key')}")
    check("همه‌ی تحلیل‌های منو در موتورها موجودند", not bad_missing, str(bad_missing))
    check("همه‌ی تحلیل‌های منو در فهرست مجاز همان میزکارند", not bad_disallowed, str(bad_disallowed))
    check("نوع همه‌ی فیلدهای پنجره‌ها معتبر است", not bad_fields, str(bad_fields))
    check("سه میزکار تعریف شده‌اند", set(workbench.SOFTWARES) == {"spss", "eviews", "smartpls"})


# ═══════════════ ۲) شبکه‌ی داده: ذخیره/خواندن ═══════════════

def test_grid_roundtrip():
    section("۲) ذخیره و خواندن شبکه‌ی داده (ستون فارسی + نام تکراری)")
    import tempfile
    import workbench
    p = os.path.join(tempfile.gettempdir(), "wb-roundtrip.csv")
    cols, rows = _sample_grid()
    info = workbench.save_grid(p, cols, rows)
    check("ذخیره انجام شد", info["rows"] == 45 and info["columns"] == 6)
    g = workbench.load_grid(p)
    check("تعداد سطر و ستون بعد از خواندن درست است",
          g["total_rows"] == 45 and len(g["columns"]) == 6)
    names = [c["name"] for c in g["columns"]]
    check("نام ستون فارسی سالم ماند", "گروه" in names and "نمره" in names, str(names))
    types = {c["name"]: c["type"] for c in g["columns"]}
    check("نوع ستون‌ها درست تشخیص داده شد",
          types.get("گروه") == "text" and types.get("نمره") == "numeric")
    check("آماره‌های Variable View ساخته شدند",
          all(k in g["columns"][1] for k in ("mean", "std", "min", "max")))

    # نام تکراری ستون باید خودکار یکتا شود
    workbench.save_grid(p, ["x", "x", "x"], [[1, 2, 3]])
    g2 = workbench.load_grid(p)
    n2 = [c["name"] for c in g2["columns"]]
    check("نام‌های تکراری ستون یکتا شدند", len(set(n2)) == 3, str(n2))

    # سقف‌ها
    try:
        workbench.save_grid(p, ["a"], [[1]] * (workbench.MAX_SAVE_ROWS + 1))
        check("سقف سطرها اعمال می‌شود", False)
    except ValueError:
        check("سقف سطرها اعمال می‌شود", True)


# ═══════════════ ۳) صفحه‌ها و API با کاربر واقعی ═══════════════

def test_pages_and_api():
    section("۳) صفحه‌های میزکار و APIهای شبکه/فهرست داده")
    from fastapi.testclient import TestClient
    import main

    u = _test_user()
    if not u:
        print("  ⏭  کاربر آزمایشی پیدا نشد — این بخش رد شد.")
        return
    c = TestClient(main.app)

    r = c.get("/spss", follow_redirects=False)
    check("بدون ورود، به صفحه‌ی ورود می‌فرستد", r.status_code in (302, 303, 307))

    c.cookies.set("antanu_session", main.make_session(u["id"]))
    for path, name in (("/spss", "ANTANU SPSS"), ("/eviews", "ANTANU EViews"),
                       ("/smartpls", "ANTANU SmartPLS")):
        r = c.get(path)
        check(f"صفحه‌ی {path} باز می‌شود", r.status_code == 200 and name in r.text
              and "workbench.js" in r.text, str(r.status_code))

    # ذخیره‌ی شبکه → فهرست → خواندن
    cols, rows = _sample_grid()
    r = c.post("/api/workbench/save",
               json={"title": "داده‌ی آزمون میزکار", "columns": cols, "rows": rows})
    check("ذخیره‌ی شبکه از API", r.status_code == 200 and r.json().get("file"), r.text[:150])
    fname = r.json()["file"]

    r = c.get("/api/workbench/datasets")
    ds = r.json().get("datasets", [])
    check("داده‌ی ذخیره‌شده در فهرست هست",
          any(d["file"] == fname and d["source"] == "edit" for d in ds))

    r = c.get("/api/workbench/data", params={"file": fname})
    check("خواندن شبکه از API", r.status_code == 200 and r.json()["total_rows"] == 45)

    r = c.get("/api/workbench/data", params={"file": "../../etc/passwd"})
    check("نام فایل خطرناک رد می‌شود", r.status_code == 400)

    # مالکیت: کاربر دیگر نتواند بخواند
    import db as D
    conn = D.get_db()
    other = conn.execute("SELECT id FROM users WHERE id != ? AND is_admin = 0 LIMIT 1",
                         (u["id"],)).fetchone()
    if not other:
        import secrets as _s
        from db import hash_pw
        conn.execute("INSERT INTO users (username, password, stars) VALUES (?, ?, 1)",
                     ("wb_other_" + _s.token_hex(3), hash_pw("x12345"), ))
        other = conn.execute("SELECT id FROM users ORDER BY id DESC LIMIT 1").fetchone()
        conn.commit()
    conn.close()
    c2 = TestClient(main.app)
    c2.cookies.set("antanu_session", main.make_session(other["id"]))
    r = c2.get("/api/workbench/data", params={"file": fname})
    check("داده‌ی کاربر دیگر خوانده نمی‌شود (۴۰۳)", r.status_code == 403, str(r.status_code))

    return fname


# ═══════════════ ۴) اجرای تحلیل از مسیر واقعی ═══════════════

def test_run_analyses(fname):
    section("۴) اجرای ANOVA و PLS از مسیر واقعی /api/stats/run")
    if not fname:
        print("  ⏭  فایل داده‌ای از بخش قبل نیست — رد شد.")
        return
    from fastapi.testclient import TestClient
    import main

    u = _test_user()

    async def fake_ai(c, prompt=None, system=None, max_tokens=1500, **kw):
        return "تفسیر آزمایشی: اثر معنادار است."
    main._call_model_once = fake_ai
    # حتی اگر در پایگاه‌داده کلید سرویس هوش مصنوعی نباشد، مسیر تفسیر آزموده شود
    main.pick_model_for = lambda task: {"id": "t", "key": "k", "model": "m",
                                        "base": "https://example.invalid/v1", "name": "آزمایشی"}

    c = TestClient(main.app)
    c.cookies.set("antanu_session", main.make_session(u["id"]))

    r = c.post("/api/stats/run", json={"file": fname, "analysis": "anova",
                                       "params": {"dependent": "نمره", "factor": "گروه"}})
    d = r.json()
    res = d.get("result") or {}
    check("ANOVA بدون خطا اجرا شد", r.status_code == 200 and not res.get("error"),
          str(res.get("error", ""))[:120])
    check("تفسیر دانشگاهی برگشت", "آزمایشی" in (d.get("interpretation") or ""))

    r = c.post("/api/stats/run", json={
        "file": fname, "analysis": "pls_sem",
        "params": {"factors": {"کیفیت": ["q1", "q2"], "رضایت": ["q3", "q4"]},
                   "structural": [["کیفیت", "رضایت"]], "bootstrap": 60}})
    res = (r.json().get("result") or {})
    check("PLS-SEM اجرا شد و سازه‌ها/مسیرها را داد",
          "سازه‌ها" in res and "مسیرهای ساختاری" in res, str(res.get("error", ""))[:120])
    boot = res.get("بوت‌استرپ") or {}
    check("بوت‌استرپ واقعاً اجرا شد", bool(boot), str(list(res.keys()))[:150])
    try:
        import matplotlib  # noqa: F401
        check("نمودار مسیر PLS از کلیدهای فارسی ساخته شد", bool(res.get("diagram")),
              str(list(res.keys()))[:150])
    except ImportError:
        print("  ⏭  matplotlib نصب نیست — آزمون نمودار رد شد (روی سرور اصلی نصب است).")

    r = c.post("/api/stats/run", json={"file": fname, "analysis": "unit_root",
                                       "params": {"cols": ["نمره"]}})
    res = (r.json().get("result") or {})
    check("آزمون ریشه‌ی واحد (EViews) اجرا شد", "نتایج" in res, str(res.get("error", ""))[:120])


def main_run():
    test_config_integrity()
    test_grid_roundtrip()
    fname = test_pages_and_api()
    test_run_analyses(fname)

    print("\n" + "═" * 68)
    print(f"نتیجه: {len(PASS)} موفق، {len(FAIL)} ناموفق")
    if FAIL:
        print("ناموفق‌ها:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    main_run()
