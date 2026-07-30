# -*- coding: utf-8 -*-
"""
test_stats_gaps.py — آزمون تحلیل‌های آماریِ تازه‌افزوده.

همه‌ی این‌ها با کتابخانه‌های از پیش نصب‌شده (statsmodels، scipy) ساخته شده‌اند —
هیچ وابستگی تازه‌ای اضافه نشد، چون سرور کاربر رم کمی دارد (زیر ۴۰۰ مگابایت آزاد).

هر تابع با داده‌ی مصنوعیِ «جواب‌شناخته» سنجیده می‌شود: یک سناریو که پاسخِ درستش
از قبل معلوم است (مثلاً دو گروه با میانگین واقعاً یکسان باید «معنادار: خیر» بدهد).

اجرا:  python test_stats_gaps.py
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


def _csv(df, name):
    import tempfile
    p = os.path.join(tempfile.gettempdir(), name)
    df.to_csv(p, index=False)
    return p


# ═══════════════ ۱) تعقیبی‌های تازه (بونفرونی، گیمز-هاول، دانت) ═══════════════

def test_posthoc_methods():
    section("۱) تعقیبی‌های تازه در ANOVA")
    import pandas as pd
    import numpy as np
    import stats_engine as se

    rng = np.random.default_rng(0)
    df = pd.concat([
        pd.DataFrame({"g": "A", "y": rng.normal(10, 2, 30)}),
        pd.DataFrame({"g": "B", "y": rng.normal(20, 2, 30)}),
        pd.DataFrame({"g": "C", "y": rng.normal(30, 2, 30)}),
    ])
    p = _csv(df, "ph1.csv")

    for method, key in (("tukey", "تعقیبی توکی"), ("bonferroni", "تعقیبی بونفرونی"),
                        ("games_howell", "تعقیبی گیمز-هاول")):
        r = se.anova(p, "y", "g", posthoc=True, posthoc_method=method)
        rows = r.get(key, [])
        check(f"{method}: سه مقایسه‌ی جفتی ساخته شد", len(rows) == 3, str(len(rows)))
        check(f"{method}: هر سه تفاوتِ واقعی را معنادار می‌بیند",
              all(row["معنادار"] == "بله" for row in rows))

    r_dun = se.anova(p, "y", "g", posthoc=True, posthoc_method="dunnett", control_group="A")
    rows = r_dun.get("تعقیبی دانت", [])
    check("dunnett: کنترل درست انتخاب شد", r_dun.get("گروه_کنترل") == "A")
    check("dunnett: دو مقایسه (B و C در برابر A)", len(rows) == 2, str(rows))
    check("dunnett: هر دو تفاوتِ واقعی را معنادار می‌بیند",
          all(row["معنادار"] == "بله" for row in rows))

    # حالتِ تهی: دو گروه با میانگینِ واقعاً یکسان و واریانسِ خیلی متفاوت
    df2 = pd.concat([
        pd.DataFrame({"g": "A", "y": rng.normal(50, 2, 60)}),
        pd.DataFrame({"g": "B", "y": rng.normal(50, 20, 15)}),
        pd.DataFrame({"g": "C", "y": rng.normal(80, 3, 30)}),
    ])
    p2 = _csv(df2, "ph2.csv")
    r_gh = se.anova(p2, "y", "g", posthoc=True, posthoc_method="games_howell")
    ab = next(r for r in r_gh["تعقیبی گیمز-هاول"]
             if {r["گروه ۱"], r["گروه ۲"]} == {"A", "B"})
    check("games_howell: A و B که میانگینشان واقعاً یکسان است، معنادار نیست",
          ab["معنادار"] == "خیر", str(ab))


# ═══════════════ ۲) MANOVA و اندازه‌گیری تکراری ═══════════════

def test_manova_and_repeated_measures():
    section("۲) MANOVA و ANOVA با اندازه‌گیری تکراری")
    import pandas as pd
    import numpy as np
    import stats_engine as se

    rng = np.random.default_rng(2)
    df = pd.concat([
        pd.DataFrame({"g": "A", "y1": rng.normal(10, 2, 40), "y2": rng.normal(5, 1, 40)}),
        pd.DataFrame({"g": "B", "y1": rng.normal(20, 2, 40), "y2": rng.normal(15, 1, 40)}),
    ])
    p = _csv(df, "manova.csv")
    r = se.manova(p, ["y1", "y2"], "g")
    check("MANOVA: تفاوتِ واقعیِ دو گروه را می‌بیند", r["معنادار"] == "بله")
    check("MANOVA: چهار آزمونِ چندمتغیره گزارش شد", len(r["آزمون‌های چندمتغیره"]) == 4)

    # MANOVA با حجم نمونه‌ی خیلی کم → پیام خطا، نه کرش
    small = df.head(3)
    ps = _csv(small, "manova_small.csv")
    r_small = se.manova(ps, ["y1", "y2"], "g")
    check("MANOVA با نمونه‌ی خیلی کوچک، خطا می‌دهد نه کرش", "error" in r_small)

    n = 30
    rm = pd.DataFrame({"pre": rng.normal(50, 5, n), "mid": rng.normal(60, 5, n),
                       "post": rng.normal(70, 5, n)})
    p_rm = _csv(rm, "rm.csv")
    r_rm = se.repeated_measures_anova(p_rm, ["pre", "mid", "post"])
    check("RM-ANOVA: روند صعودیِ واقعی را معنادار می‌بیند", r_rm["معنادار"] == "بله")

    rm0 = pd.DataFrame({c: rng.normal(50, 5, n) for c in ["t1", "t2", "t3"]})
    p_rm0 = _csv(rm0, "rm0.csv")
    r_rm0 = se.repeated_measures_anova(p_rm0, ["t1", "t2", "t3"])
    check("RM-ANOVA: بدون تفاوتِ واقعی، معنادار نیست", r_rm0["معنادار"] == "خیر")


# ═══════════════ ۳) رگرسیونِ ترتیبی، چندجمله‌ای و شمارشی ═══════════════

def test_regression_kinds():
    section("۳) رگرسیون ترتیبی / چندجمله‌ای / پواسون / دوجمله‌ای‌منفی")
    import pandas as pd
    import numpy as np
    import stats_engine as se

    rng = np.random.default_rng(5)
    n = 300

    x = rng.normal(0, 1, n)
    score = x * 2 + rng.normal(0, 1, n)
    y_ord = pd.cut(score, bins=[-np.inf, -1, 0, 1, np.inf], labels=[1, 2, 3, 4]).astype(int)
    p_ord = _csv(pd.DataFrame({"x": x, "y": y_ord}), "ord.csv")
    r_ord = se.regression(p_ord, "y", ["x"], kind="ordinal")
    check("ordinal: ضریب x معنادار و مثبت است", r_ord["coefficients"][0]["ضریب"] > 0 and
          r_ord["coefficients"][0]["معنادار"] == "بله")
    check("ordinal: سه آستانه برای چهار سطح ساخته شد", len(r_ord["آستانه‌ها"]) == 3)

    x2 = rng.normal(0, 1, n)
    logits = np.column_stack([np.zeros(n), 1.5 * x2, -1.2 * x2])
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    cat = [rng.choice(["A", "B", "C"], p=pr) for pr in probs]
    p_mn = _csv(pd.DataFrame({"x": x2, "y": cat}), "mn.csv")
    r_mn = se.regression(p_mn, "y", ["x"], kind="multinomial")
    check("multinomial: سطح مرجع A است", r_mn["سطح مرجع"] == "A")
    check("multinomial: جدولِ تخت (نه تودرتو) دارد",
          isinstance(r_mn["ضرایب"], list) and isinstance(r_mn["ضرایب"][0], dict) and
          "سطح (در برابر مرجع)" in r_mn["ضرایب"][0])
    signs = {row["سطح (در برابر مرجع)"]: row["ضریب"] for row in r_mn["ضرایب"] if row["متغیر"] == "x"}
    check("multinomial: علامتِ ضرایب با شبیه‌سازی همخوان است (B مثبت، C منفی)",
          signs.get("B", 0) > 0 and signs.get("C", 0) < 0, str(signs))

    x3 = rng.normal(0, 0.5, n)
    y_cnt = rng.poisson(np.exp(1 + 1.2 * x3))
    p_poi = _csv(pd.DataFrame({"x": x3, "y": y_cnt}), "poi.csv")
    r_poi = se.regression(p_poi, "y", ["x"], kind="poisson")
    b_x = next(c["ضریب B"] for c in r_poi["coefficients"] if c["متغیر"] == "x")
    check("poisson: ضریبِ بازیابی‌شده نزدیکِ مقدار واقعیِ ۱.۲ است", abs(b_x - 1.2) < 0.3, str(b_x))
    check("poisson: نسبت بروز (IRR) گزارش شد",
          all("نسبت بروز (IRR)" in c for c in r_poi["coefficients"]))

    x4 = rng.normal(0, 0.5, n)
    mu = np.exp(1 + x4)
    y_nb = rng.negative_binomial(2.0, 2.0 / (2.0 + mu))
    p_nb = _csv(pd.DataFrame({"x": x4, "y": y_nb}), "nb.csv")
    r_nb = se.regression(p_nb, "y", ["x"], kind="negbinom")
    b_x_nb = next(c["ضریب B"] for c in r_nb["coefficients"] if c["متغیر"] == "x")
    check("negbinom: ضریبِ بازیابی‌شده نزدیکِ مقدار واقعیِ ۱.۰ است", abs(b_x_nb - 1.0) < 0.4, str(b_x_nb))


# ═══════════════ ۴) تشخیصیِ سری‌زمانیِ تازه ═══════════════

def test_ts_diagnostics_additions():
    section("۴) ARCH-LM، CUSUM و چاو در ts_diagnostics")
    import pandas as pd
    import numpy as np
    import ts_engine as te

    rng = np.random.default_rng(10)
    n = 400
    y = np.zeros(n)
    sigma2 = np.zeros(n)
    sigma2[0] = 1
    for t in range(1, n):
        sigma2[t] = 0.1 + 0.85 * y[t - 1] ** 2
        y[t] = np.sqrt(sigma2[t]) * rng.normal()
    x = rng.normal(size=n)
    p_arch = _csv(pd.DataFrame({"y": y, "x": x}), "arch.csv")
    r = te.ts_diagnostics(p_arch, "y", ["x"])
    check("ARCH-LM: خوشه‌بندیِ واقعیِ نوسان را تشخیص می‌دهد",
          "دارد" in r.get("ARCH-LM (خوشه‌بندی نوسان)", {}).get("اثر ARCH", ""))

    n2 = 200
    x2 = rng.normal(size=n2)
    y2 = np.where(np.arange(n2) < n2 // 2, 2 * x2, -3 * x2) + rng.normal(scale=0.3, size=n2)
    p_chow = _csv(pd.DataFrame({"y": y2, "x": x2}), "chow.csv")
    r2 = te.ts_diagnostics(p_chow, "y", ["x"])
    check("چاو: شکستِ واقعیِ ضریب را با اطمینانِ بالا تشخیص می‌دهد",
          r2["شکست ساختاری (چاو)"]["شکست ساختاری"] == "دارد" and
          r2["شکست ساختاری (چاو)"]["sig"] < 0.001)
    check("CUSUM: در خروجی هست (حتی اگر همیشه با چاو هم‌رأی نباشد)",
          "CUSUM (پایداری ضرایب در طول زمان)" in r2)


def test_seasonal_decompose():
    section("۵) تجزیه‌ی فصلی")
    import pandas as pd
    import numpy as np
    import ts_engine as te

    rng = np.random.default_rng(11)
    n = 60
    t = np.arange(n)
    dates = pd.date_range("2020-01-01", periods=n, freq="MS")

    y = 50 + 0.5 * t + 10 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 1, n)
    p = _csv(pd.DataFrame({"date": dates, "y": y}), "seasonal.csv")
    r = te.seasonal_decompose_analysis(p, "y", period=12)
    check("قدرت روند بالاست (روند واقعی وجود دارد)", r["قدرت روند"] > 0.9, str(r["قدرت روند"]))
    check("قدرت فصلی بالاست (الگوی فصلیِ واقعی وجود دارد)", r["قدرت فصلی"] > 0.9,
          str(r["قدرت فصلی"]))

    y2 = 50 + 0.5 * t + rng.normal(0, 1, n)
    p2 = _csv(pd.DataFrame({"date": dates, "y": y2}), "seasonal_none.csv")
    r2 = te.seasonal_decompose_analysis(p2, "y", period=12)
    check("بدون الگوی فصلیِ واقعی، قدرت فصلی پایین است", r2["قدرت فصلی"] < 0.5,
          str(r2["قدرت فصلی"]))


# ═══════════════ ۶) ثبت در FUNCTIONS/SPEC/TITLES و مسیر خودکار ═══════════════

def test_registration_and_pipeline():
    section("۶) ثبت در ثبت‌نام‌ها و مسیر کاملِ خودکار (validate → execute)")
    import pandas as pd
    import numpy as np
    import stats_engine as se
    import analysis_planner as ap

    names = se.available_analyses()
    for n in ("manova", "repeated_measures_anova", "seasonal_decompose"):
        check(f"{n} در available_analyses ثبت شده", n in names)
        check(f"{n} در SPEC ثبت شده", n in ap.SPEC)
        check(f"{n} در TITLES فارسی دارد", n in ap.TITLES)

    rng = np.random.default_rng(2)
    df = pd.concat([
        pd.DataFrame({"g": "A", "y1": rng.normal(10, 2, 40), "y2": rng.normal(5, 1, 40)}),
        pd.DataFrame({"g": "B", "y1": rng.normal(20, 2, 40), "y2": rng.normal(15, 1, 40)}),
    ])
    p = _csv(df, "pipeline.csv")
    prof = ap.profile(p)
    step = {"analysis": "manova", "params": {"dependents": ["y1", "y2"], "factor": "g"}}
    validated, err = ap.validate_step(step, prof)
    check("validate_step قدمِ درست را قبول می‌کند", validated is not None, str(err))
    results = ap.execute(p, [validated]) if validated else []
    check("execute تحلیل را واقعاً اجرا می‌کند", bool(results) and "error" not in results[0]["result"])

    # داده‌ی نامناسب برای MANOVA (نمونه‌ی خیلی کوچک) باید همان‌جا رد شود
    small = df.head(5)
    ps = _csv(small, "pipeline_small.csv")
    prof_small = ap.profile(ps)
    v2, e2 = ap.validate_step(step, prof_small)
    check("validate_step داده‌ی نامناسب را رد می‌کند (نه اینکه بگذارد بترکد)",
          v2 is None and bool(e2))


# ═══════════════ ۷) گزارش‌سازی (stats_report) خروجی‌های تازه را می‌شکند؟ ═══════════════

def test_report_rendering():
    section("۷) گزارش مارک‌داون خروجی‌های تازه را بدون کرش می‌سازد")
    import pandas as pd
    import numpy as np
    import stats_engine as se
    import stats_report as sr

    rng = np.random.default_rng(2)
    df = pd.concat([
        pd.DataFrame({"g": "A", "y1": rng.normal(10, 2, 40), "y2": rng.normal(5, 1, 40)}),
        pd.DataFrame({"g": "B", "y1": rng.normal(20, 2, 40), "y2": rng.normal(15, 1, 40)}),
    ])
    p = _csv(df, "report_manova.csv")
    r_manova = se.manova(p, ["y1", "y2"], "g")
    md = sr.render_result("manova", "MANOVA", r_manova)
    check("گزارشِ MANOVA ساخته شد و جدول دارد", "| آزمون |" in md)

    x2 = rng.normal(0, 1, 300)
    logits = np.column_stack([np.zeros(300), 1.5 * x2, -1.2 * x2])
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    cat = [rng.choice(["A", "B", "C"], p=pr) for pr in probs]
    p_mn = _csv(pd.DataFrame({"x": x2, "y": cat}), "report_mn.csv")
    r_mn = se.regression(p_mn, "y", ["x"], kind="multinomial")
    md2 = sr.render_result("regression", "رگرسیون چندجمله‌ای", r_mn)
    check("گزارشِ چندجمله‌ای جدولِ تخت دارد (نه دیکشنری خام در سلول)",
          "{'متغیر'" not in md2 and "| سطح (در برابر مرجع) |" in md2)

    x = rng.normal(0, 1, 300)
    score = x * 2 + rng.normal(0, 1, 300)
    y_ord = pd.cut(score, bins=[-np.inf, -1, 0, 1, np.inf], labels=[1, 2, 3, 4]).astype(int)
    p_ord = _csv(pd.DataFrame({"x": x, "y": y_ord}), "report_ord.csv")
    r_ord = se.regression(p_ord, "y", ["x"], kind="ordinal")
    md3 = sr.render_result("regression", "رگرسیون ترتیبی", r_ord)
    check("گزارشِ ترتیبی آستانه‌ها را نشان می‌دهد", "آستانه‌ها" in md3)


def main_run():
    print("═" * 68)
    print("  آزمون تحلیل‌های آماریِ تازه")
    print("═" * 68)
    test_posthoc_methods()
    test_manova_and_repeated_measures()
    test_regression_kinds()
    test_ts_diagnostics_additions()
    test_seasonal_decompose()
    test_registration_and_pipeline()
    test_report_rendering()

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
