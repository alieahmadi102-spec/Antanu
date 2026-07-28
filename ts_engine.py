# -*- coding: utf-8 -*-
"""
ts_engine.py — آزمون‌های سری‌زمانی و داده‌ی تابلویی (معادل EViews).

ریشه‌ی واحد، هم‌انباشتگی، علیت گرنجر، ARIMA، VAR، VECM، GARCH،
داده‌ی تابلویی (اثرات ثابت/تصادفی و هاوسمن) و آزمون‌های تشخیصی رگرسیون.

همه‌ی توابع همان قرارداد stats_engine را دارند: مسیر فایل می‌گیرند و dict
برمی‌گردانند؛ در صورت مشکل، کلید "error" با پیام فارسیِ روشن.
"""
import os

from stats_engine import _load_dataframe


# ---------------- کمکی‌ها ----------------

def _numeric(df, cols=None):
    """ستون‌های عددی را برمی‌گرداند (با تبدیل امن)."""
    import pandas as pd
    use = [c for c in (cols or df.columns) if c in df.columns]
    out = df[use].apply(pd.to_numeric, errors="coerce")
    return out.dropna(axis=1, how="all")


def _series(df, col):
    """یک ستون را به سری عددیِ بدون گمشده تبدیل می‌کند."""
    import pandas as pd
    if col not in df.columns:
        return None, f"ستون «{col}» در داده نیست"
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(s) < 12:
        return None, f"ستون «{col}» برای تحلیل سری‌زمانی داده‌ی کافی ندارد (دست‌کم ۱۲ مشاهده لازم است)"
    return s.reset_index(drop=True), None


def detect_time_column(df):
    """ستون تاریخ/زمان را حدس می‌زند (برای تشخیص خودکار سری‌زمانی بودن داده).

    نکته‌ی مهم: pandas یک ستون عددیِ معمولی را هم به‌عنوان «تعداد نانوثانیه از مبدأ»
    به تاریخ تبدیل می‌کند؛ اگر همین را ملاک بگیریم، ستونی مثل «نمره» تاریخ حساب
    می‌شود. پس ستون عددی فقط وقتی زمان است که مثل «سال» یا شماره‌ی دوره‌ی مرتب
    به‌نظر برسد.
    """
    import pandas as pd
    n = len(df)
    best, best_score = None, 0
    for c in df.columns:
        name = str(c).lower()
        hinted = any(k in name for k in
                     ("date", "time", "year", "period", "quarter", "month",
                      "تاریخ", "زمان", "سال", "ماه", "فصل", "دوره"))
        s = df[c].dropna()
        if s.empty:
            continue
        nums = pd.to_numeric(s, errors="coerce")
        is_numeric = float(nums.notna().mean()) > 0.9
        ok = 0
        if is_numeric:
            v = nums.dropna()
            whole = float((v % 1 == 0).mean()) > 0.95
            year_like = whole and float(v.between(1300, 2100).mean()) > 0.9
            # شماره‌ی دوره: عدد صحیحِ کوچک، مرتب و بدون تکرارِ زیاد
            seq_like = (whole and hinted and v.min() >= 0 and v.max() <= 5000
                        and v.nunique() >= max(3, 0.5 * len(v)))
            if year_like or seq_like:
                ok = len(v)
        else:
            # ستون متنی/تاریخی: تبدیل واقعی به تاریخ معنا دارد
            try:
                parsed = pd.to_datetime(s, errors="coerce")
                ok = int(parsed.notna().sum())
            except Exception:
                ok = 0
        if not ok:
            continue
        score = ok * (2 if hinted else 1)
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= max(5, 0.6 * n) else None


def detect_panel(df):
    """ساختار تابلویی را تشخیص می‌دهد: (ستون شناسه، ستون زمان) یا (None, None).

    ملاک: یک ستون با تکرارِ منظم (شناسه‌ی واحدها) به‌همراه یک ستون زمان، طوری که
    ترکیبشان تقریباً یکتا باشد.
    """
    tcol = detect_time_column(df)
    if not tcol or len(df) < 12:
        return None, None
    n = len(df)
    best, best_score = None, 0
    for c in df.columns:
        if c == tcol:
            continue
        k = df[c].nunique(dropna=True)
        if k < 2 or k >= n:            # نه ثابت، نه یکتا برای هر سطر
            continue
        pairs = df.groupby([c, tcol]).size()
        if len(pairs) == 0:
            continue
        uniq_ratio = float((pairs == 1).mean())        # هر (واحد، زمان) یک سطر
        per_unit = n / k
        if uniq_ratio > 0.9 and per_unit >= 2:
            score = uniq_ratio * min(per_unit, 50)
            if score > best_score:
                best, best_score = c, score
    return (best, tcol) if best else (None, None)


def _stars(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""


# ---------------- ریشه‌ی واحد ----------------

def unit_root(path: str, cols=None, regression: str = "c", max_diff: int = 2) -> dict:
    """آزمون ریشه‌ی واحد: دیکی-فولر تعمیم‌یافته، فیلیپس-پرون و KPSS.

    ADF و PP: فرض صفر «ریشه‌ی واحد دارد» (نامانا) — p کوچک یعنی مانا.
    KPSS: فرض صفر «مانا است» — p کوچک یعنی نامانا. (جهت فرض برعکس است.)
    اگر سری نامانا باشد، مرتبه‌ی هم‌جمعی با تفاضل‌گیری پیدا می‌شود.
    """
    try:
        from statsmodels.tsa.stattools import adfuller, kpss
    except ImportError:
        return {"error": "برای آزمون ریشه‌ی واحد نصب statsmodels لازم است"}
    df = _load_dataframe(path)
    num = _numeric(df, cols)
    if num.shape[1] == 0:
        return {"error": "ستون عددی برای آزمون ریشه‌ی واحد پیدا نشد"}

    rows = []
    for c in num.columns:
        s, err = _series(num, c)
        if err:
            rows.append({"متغیر": str(c), "خطا": err})
            continue
        item = {"متغیر": str(c)}
        # --- ADF روی سطح و سپس تفاضل‌ها ---
        order = None
        for d in range(0, max_diff + 1):
            x = s.diff(d).dropna() if d else s
            if len(x) < 12:
                break
            try:
                stat, p, lags, nobs, crit, _ = adfuller(x, regression=regression, autolag="AIC")
            except Exception as e:
                item["خطا"] = str(e)
                break
            key = "سطح" if d == 0 else f"تفاضل مرتبه {d}"
            item[f"ADF ({key})"] = round(float(stat), 3)
            item[f"sig ({key})"] = round(float(p), 4)
            if p < 0.05 and order is None:
                order = d
                item["مقدار بحرانی ۵٪"] = round(float(crit["5%"]), 3)
                item["وقفه"] = int(lags)
                break
        item["مرتبه هم‌جمعی"] = (f"I({order})" if order is not None
                                 else f"مانا نشد تا مرتبه {max_diff}")
        item["مانا در سطح"] = "بله" if order == 0 else "خیر"
        # --- فیلیپس-پرون ---
        try:
            from arch.unitroot import PhillipsPerron
            pp = PhillipsPerron(s, trend=regression)
            item["PP"] = round(float(pp.stat), 3)
            item["sig (PP)"] = round(float(pp.pvalue), 4)
        except Exception:
            pass
        # --- KPSS (فرض صفر برعکس است) ---
        try:
            # وقتی آماره بیرون از جدولِ مقدارهای بحرانی باشد، statsmodels هشدار
            # می‌دهد و p را به نزدیک‌ترین کران می‌بَرد؛ همین کافی است و هشدارش
            # فقط لاگ را شلوغ می‌کند.
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore")
                kstat, kp, _, _ = kpss(s, regression=regression, nlags="auto")
            item["KPSS"] = round(float(kstat), 3)
            item["sig (KPSS)"] = round(float(kp), 4)
            item["KPSS نتیجه"] = "مانا" if kp >= 0.05 else "نامانا"
        except Exception:
            pass
        rows.append(item)

    return {
        "software": "معادل خروجی EViews (Unit Root Test)",
        "نوع معادله": {"c": "با عرض از مبدأ", "ct": "با عرض از مبدأ و روند",
                        "n": "بدون عرض از مبدأ"}.get(regression, regression),
        "نتایج": rows,
        "راهنما": ("در ADF و PP فرض صفر «وجود ریشه‌ی واحد» است، پس sig کمتر از ۰٫۰۵ "
                   "یعنی سری مانا است. در KPSS برعکس: فرض صفر «مانایی» است."),
    }


# ---------------- هم‌انباشتگی ----------------

def cointegration(path: str, cols=None, det_order: int = 0, k_ar_diff: int = 1) -> dict:
    """هم‌انباشتگی: انگل-گرنجر (دو متغیره) و یوهانسن (چند متغیره)."""
    try:
        from statsmodels.tsa.stattools import coint
        from statsmodels.tsa.vector_ar.vecm import coint_johansen
    except ImportError:
        return {"error": "برای آزمون هم‌انباشتگی نصب statsmodels لازم است"}
    df = _load_dataframe(path)
    num = _numeric(df, cols).dropna()
    if num.shape[1] < 2:
        return {"error": "برای آزمون هم‌انباشتگی دست‌کم دو متغیر عددی لازم است"}
    if len(num) < 20:
        return {"error": "تعداد مشاهده‌ها برای آزمون هم‌انباشتگی کافی نیست"}

    out = {"software": "معادل خروجی EViews (Cointegration Test)", "متغیرها": list(map(str, num.columns))}

    # --- انگل-گرنجر برای هر جفت ---
    eg = []
    cs = list(num.columns)
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            try:
                t, p, crit = coint(num[cs[i]], num[cs[j]])
                eg.append({"جفت": f"{cs[i]} و {cs[j]}", "آماره": round(float(t), 3),
                           "sig": round(float(p), 4),
                           "مقدار بحرانی ۵٪": round(float(crit[1]), 3),
                           "هم‌انباشته": "بله" if p < 0.05 else "خیر"})
            except Exception as e:
                eg.append({"جفت": f"{cs[i]} و {cs[j]}", "خطا": str(e)[:80]})
    out["انگل-گرنجر"] = eg

    # --- یوهانسن (اثر و حداکثر مقدار ویژه) ---
    if num.shape[1] >= 2:
        try:
            jres = coint_johansen(num.values, det_order, k_ar_diff)
            trace, maxeig = [], []
            for r in range(len(jres.lr1)):
                trace.append({
                    "فرض": f"حداکثر {r} بردار هم‌انباشتگی",
                    "آماره اثر": round(float(jres.lr1[r]), 3),
                    "مقدار بحرانی ۵٪": round(float(jres.cvt[r][1]), 3),
                    "رد فرض صفر": "بله" if jres.lr1[r] > jres.cvt[r][1] else "خیر",
                })
                maxeig.append({
                    "فرض": f"حداکثر {r} بردار هم‌انباشتگی",
                    "آماره حداکثر مقدار ویژه": round(float(jres.lr2[r]), 3),
                    "مقدار بحرانی ۵٪": round(float(jres.cvm[r][1]), 3),
                    "رد فرض صفر": "بله" if jres.lr2[r] > jres.cvm[r][1] else "خیر",
                })
            n_vec = sum(1 for r in trace if r["رد فرض صفر"] == "بله")
            out["یوهانسن_اثر"] = trace
            out["یوهانسن_حداکثر_مقدار_ویژه"] = maxeig
            out["تعداد بردار هم‌انباشتگی"] = n_vec
            out["نتیجه"] = ("رابطه‌ی بلندمدت (هم‌انباشتگی) وجود دارد" if n_vec > 0
                            else "شواهدی از رابطه‌ی بلندمدت یافت نشد")
        except Exception as e:
            out["یوهانسن_خطا"] = str(e)[:120]
    return out


# ---------------- علیت گرنجر ----------------

def granger(path: str, cause: str = None, effect: str = None,
            cols=None, maxlag: int = 4) -> dict:
    """آزمون علیت گرنجر. اگر cause/effect داده نشود، همه‌ی جفت‌ها آزمون می‌شوند.

    فرض صفر: «cause علت گرنجریِ effect نیست». sig کمتر از ۰٫۰۵ یعنی علیت وجود دارد.
    """
    try:
        from statsmodels.tsa.stattools import grangercausalitytests
    except ImportError:
        return {"error": "برای آزمون گرنجر نصب statsmodels لازم است"}
    import pandas as pd
    df = _load_dataframe(path)
    num = _numeric(df, cols).dropna()
    if num.shape[1] < 2:
        return {"error": "برای آزمون گرنجر دست‌کم دو متغیر عددی لازم است"}

    pairs = ([(cause, effect)] if cause and effect
             else [(a, b) for a in num.columns for b in num.columns if a != b])
    rows = []
    for a, b in pairs:
        if a not in num.columns or b not in num.columns:
            rows.append({"رابطه": f"{a} → {b}", "خطا": "ستون در داده نیست"})
            continue
        try:
            data = num[[b, a]].dropna()          # ستون اول: وابسته، دوم: علت
            if len(data) < maxlag + 10:
                rows.append({"رابطه": f"{a} → {b}", "خطا": "مشاهده‌ی کافی نیست"})
                continue
            # statsmodels نتیجه را روی خروجی استاندارد هم چاپ می‌کند؛
            # جلویش را می‌گیریم تا لاگ سرور شلوغ نشود.
            import contextlib, io as _io
            with contextlib.redirect_stdout(_io.StringIO()):
                res = grangercausalitytests(data, maxlag=maxlag)
            best = min(range(1, maxlag + 1),
                       key=lambda L: res[L][0]["ssr_ftest"][1])
            f, p = res[best][0]["ssr_ftest"][0], res[best][0]["ssr_ftest"][1]
            rows.append({
                "رابطه": f"{a} → {b}", "وقفه بهینه": best,
                "F": round(float(f), 3), "sig": round(float(p), 4),
                "معناداری": _stars(float(p)),
                "علیت": "بله" if p < 0.05 else "خیر",
            })
        except Exception as e:
            rows.append({"رابطه": f"{a} → {b}", "خطا": str(e)[:80]})
    return {"software": "معادل خروجی EViews (Granger Causality Test)",
            "حداکثر وقفه": maxlag, "نتایج": rows,
            "راهنما": "فرض صفر «نبود علیت گرنجری» است؛ sig کمتر از ۰٫۰۵ یعنی علیت وجود دارد."}


# ---------------- ARIMA ----------------

def arima(path: str, col: str = None, order=None, max_p: int = 3, max_q: int = 3,
          forecast: int = 6) -> dict:
    """برازش ARIMA با انتخاب خودکار مرتبه بر پایه‌ی AIC، به‌همراه پیش‌بینی."""
    try:
        from statsmodels.tsa.arima.model import ARIMA
        from statsmodels.tsa.stattools import adfuller
    except ImportError:
        return {"error": "برای ARIMA نصب statsmodels لازم است"}
    df = _load_dataframe(path)
    num = _numeric(df)
    col = col or (num.columns[0] if num.shape[1] else None)
    if col is None:
        return {"error": "ستون عددی برای ARIMA پیدا نشد"}
    s, err = _series(num, col)
    if err:
        return {"error": err}

    # مرتبه‌ی تفاضل با ADF
    d = 0
    x = s.copy()
    while d < 2:
        try:
            if adfuller(x, autolag="AIC")[1] < 0.05:
                break
        except Exception:
            break
        x = x.diff().dropna(); d += 1

    if order:
        best_order, best = tuple(order), None
        try:
            best = ARIMA(s, order=best_order).fit()
        except Exception as e:
            return {"error": f"برازش ARIMA با مرتبه‌ی داده‌شده ممکن نشد: {e}"}
    else:
        best, best_order, best_aic = None, None, float("inf")
        for p in range(max_p + 1):
            for q in range(max_q + 1):
                if p == 0 and q == 0:
                    continue
                try:
                    m = ARIMA(s, order=(p, d, q)).fit()
                except Exception:
                    continue
                if m.aic < best_aic:
                    best, best_order, best_aic = m, (p, d, q), m.aic
        if best is None:
            return {"error": "هیچ مدل ARIMA‌ای روی این سری برازش نشد"}

    coefs = []
    for name, val, se_, pv in zip(best.params.index, best.params.values,
                                  best.bse.values, best.pvalues.values):
        coefs.append({"پارامتر": str(name), "ضریب": round(float(val), 4),
                      "خطای معیار": round(float(se_), 4),
                      "sig": round(float(pv), 4), "معناداری": _stars(float(pv))})
    out = {
        "software": "معادل خروجی EViews (ARIMA)",
        "متغیر": str(col), "مرتبه": f"ARIMA{best_order}",
        "AIC": round(float(best.aic), 3), "BIC": round(float(best.bic), 3),
        "ضرایب": coefs, "n": int(len(s)),
    }
    try:
        fc = best.forecast(steps=forecast)
        out["پیش‌بینی"] = [{"دوره": i + 1, "مقدار": round(float(v), 4)}
                            for i, v in enumerate(fc)]
    except Exception:
        pass
    # لیونگ-باکس: آیا پسماند خودهمبستگی دارد؟
    try:
        from statsmodels.stats.diagnostic import acorr_ljungbox
        lb = acorr_ljungbox(best.resid, lags=[min(10, len(s) // 5)], return_df=True)
        p = float(lb["lb_pvalue"].iloc[0])
        out["لیونگ-باکس"] = {"sig": round(p, 4),
                             "پسماند سفید": "بله" if p >= 0.05 else "خیر"}
    except Exception:
        pass
    return out


# ---------------- VAR ----------------

def var_model(path: str, cols=None, maxlags: int = 5, irf_periods: int = 10) -> dict:
    """خودرگرسیون برداری: انتخاب وقفه، ضرایب، توابع واکنش آنی و تجزیه‌ی واریانس."""
    try:
        from statsmodels.tsa.api import VAR
    except ImportError:
        return {"error": "برای VAR نصب statsmodels لازم است"}
    df = _load_dataframe(path)
    num = _numeric(df, cols).dropna()
    if num.shape[1] < 2:
        return {"error": "برای VAR دست‌کم دو متغیر عددی لازم است"}
    if len(num) < maxlags + 20:
        return {"error": "تعداد مشاهده‌ها برای VAR کافی نیست"}
    try:
        model = VAR(num)
        sel = model.select_order(maxlags=min(maxlags, len(num) // 5))
        lag = int(sel.aic) if getattr(sel, "aic", None) else 1
        lag = max(1, lag)
        res = model.fit(lag)
    except Exception as e:
        return {"error": f"برازش VAR ممکن نشد: {e}"}

    out = {
        "software": "معادل خروجی EViews (VAR)",
        "متغیرها": list(map(str, num.columns)),
        "وقفه بهینه": lag,
        "معیار انتخاب": {"AIC": round(float(res.aic), 3), "BIC": round(float(res.bic), 3)},
        "n": int(len(num)),
    }
    try:
        out["ضرایب"] = [
            {"معادله": str(eq), **{str(k): round(float(v), 4)
                                    for k, v in res.params[eq].items()}}
            for eq in res.params.columns
        ]
    except Exception:
        pass
    try:
        irf = res.irf(irf_periods)
        out["واکنش آنی"] = {
            f"{src} → {dst}": [round(float(irf.irfs[t][j][i]), 4)
                               for t in range(min(irf_periods, len(irf.irfs)))]
            for i, src in enumerate(num.columns) for j, dst in enumerate(num.columns)
        }
    except Exception:
        pass
    try:
        fevd = res.fevd(irf_periods)
        out["تجزیه واریانس"] = {
            str(v): [round(float(x), 4) for x in fevd.decomp[i][-1]]
            for i, v in enumerate(num.columns)
        }
    except Exception:
        pass
    return out


def vecm(path: str, cols=None, k_ar_diff: int = 1, coint_rank: int = 1) -> dict:
    """مدل تصحیح خطای برداری — برای متغیرهای هم‌انباشته."""
    try:
        from statsmodels.tsa.vector_ar.vecm import VECM
    except ImportError:
        return {"error": "برای VECM نصب statsmodels لازم است"}
    df = _load_dataframe(path)
    num = _numeric(df, cols).dropna()
    if num.shape[1] < 2:
        return {"error": "برای VECM دست‌کم دو متغیر عددی لازم است"}
    try:
        res = VECM(num, k_ar_diff=k_ar_diff, coint_rank=coint_rank,
                   deterministic="ci").fit()
    except Exception as e:
        return {"error": f"برازش VECM ممکن نشد: {e}"}
    out = {"software": "معادل خروجی EViews (VECM)",
           "متغیرها": list(map(str, num.columns)),
           "رتبه هم‌انباشتگی": coint_rank, "وقفه تفاضلی": k_ar_diff, "n": int(len(num))}
    try:
        out["بردار هم‌انباشتگی (بلندمدت)"] = [
            {str(c): round(float(v), 4) for c, v in zip(num.columns, res.beta[:, r])}
            for r in range(res.beta.shape[1])
        ]
        out["سرعت تعدیل (آلفا)"] = {
            str(c): round(float(res.alpha[i][0]), 4) for i, c in enumerate(num.columns)
        }
        out["تفسیر"] = ("ضریب سرعت تعدیل باید منفی و معنادار باشد تا بازگشت به تعادل "
                        "بلندمدت تأیید شود.")
    except Exception:
        pass
    return out


# ---------------- GARCH ----------------

def garch(path: str, col: str = None, p: int = 1, q: int = 1,
          mean: str = "Constant", dist: str = "normal") -> dict:
    """مدل ARCH/GARCH برای نوسان — کاربرد در داده‌های مالی."""
    try:
        from arch import arch_model
    except ImportError:
        return {"error": "برای GARCH نصب کتابخانه‌ی arch لازم است (pip install arch)"}
    df = _load_dataframe(path)
    num = _numeric(df)
    col = col or (num.columns[0] if num.shape[1] else None)
    if col is None:
        return {"error": "ستون عددی برای GARCH پیدا نشد"}
    s, err = _series(num, col)
    if err:
        return {"error": err}
    # مقیاس‌دهی برای همگرایی بهتر بهینه‌ساز (مثل تبدیل بازده به درصد)
    scaled = s.abs().mean() < 1
    try:
        res = arch_model(s * 100 if scaled else s,
                         mean=mean, vol="GARCH", p=p, q=q, dist=dist).fit(disp="off")
    except Exception as e:
        return {"error": f"برازش GARCH ممکن نشد: {e}"}
    coefs = []
    for name in res.params.index:
        pv = float(res.pvalues[name])
        coefs.append({"پارامتر": str(name), "ضریب": round(float(res.params[name]), 4),
                      "خطای معیار": round(float(res.std_err[name]), 4),
                      "sig": round(pv, 4), "معناداری": _stars(pv)})
    out = {"software": "معادل خروجی EViews (GARCH)",
           "متغیر": str(col), "مدل": f"GARCH({p},{q})",
           "میانگین": mean, "توزیع": dist,
           "AIC": round(float(res.aic), 3), "BIC": round(float(res.bic), 3),
           "لگاریتم درست‌نمایی": round(float(res.loglikelihood), 3),
           "ضرایب": coefs, "n": int(len(s))}
    if scaled:
        out["یادداشت مقیاس"] = ("سری برای همگرایی بهتر در ۱۰۰ ضرب شد (مثل تبدیل بازده به "
                                "درصد)؛ ضرایب واریانس بر همین مقیاس‌اند و نتیجه‌گیری "
                                "درباره‌ی پایداری نوسان تغییری نمی‌کند.")
    try:
        a = float(res.params.get("alpha[1]", 0)); b = float(res.params.get("beta[1]", 0))
        out["پایداری نوسان (alpha+beta)"] = round(a + b, 4)
        out["تفسیر"] = ("مجموع نزدیک به یک یعنی شوک‌های نوسانی ماندگارند."
                        if a + b > 0.9 else "شوک‌های نوسانی نسبتاً زودگذرند.")
    except Exception:
        pass
    return out


# ---------------- داده‌ی تابلویی ----------------

def panel(path: str, dependent: str = None, independents=None,
          entity: str = None, time: str = None) -> dict:
    """داده‌ی تابلویی: تلفیقی، اثرات ثابت، اثرات تصادفی و آزمون هاوسمن."""
    try:
        from linearmodels.panel import PanelOLS, RandomEffects, PooledOLS
    except ImportError:
        return {"error": "برای داده‌ی تابلویی نصب linearmodels لازم است (pip install linearmodels)"}
    import numpy as np
    import pandas as pd
    df = _load_dataframe(path)

    if not entity or not time:
        e, t = detect_panel(df)
        entity = entity or e
        time = time or t
    if not entity or not time:
        return {"error": "ساختار تابلویی تشخیص داده نشد؛ ستون شناسه‌ی واحدها و ستون زمان را مشخص کنید"}

    num = _numeric(df)
    if dependent is None:
        cand = [c for c in num.columns if c not in (entity, time)]
        dependent = cand[-1] if cand else None
    if dependent is None or dependent not in df.columns:
        return {"error": "متغیر وابسته مشخص نیست"}
    if not independents:
        independents = [c for c in num.columns if c not in (dependent, entity, time)]
    independents = [c for c in independents if c in num.columns]
    if not independents:
        return {"error": "متغیر مستقلِ عددی پیدا نشد"}

    work = df[[entity, time, dependent] + independents].dropna()
    if len(work) < 12:
        return {"error": "تعداد مشاهده‌های کامل برای تحلیل تابلویی کافی نیست"}
    try:
        work[time] = pd.to_datetime(work[time], errors="coerce")
        if work[time].isna().all():
            work[time] = df.loc[work.index, time]
    except Exception:
        pass
    work = work.set_index([entity, time])
    y = pd.to_numeric(work[dependent], errors="coerce")
    X = work[independents].apply(pd.to_numeric, errors="coerce")

    def _fmt(res, name):
        rows = []
        for k in res.params.index:
            pv = float(res.pvalues[k])
            rows.append({"متغیر": str(k), "ضریب": round(float(res.params[k]), 4),
                         "خطای معیار": round(float(res.std_errors[k]), 4),
                         "t": round(float(res.tstats[k]), 3),
                         "sig": round(pv, 4), "معناداری": _stars(pv)})
        return {"مدل": name, "ضرایب": rows,
                "R2": round(float(res.rsquared), 4),
                "n": int(res.nobs)}

    out = {"software": "معادل خروجی EViews (Panel Data)",
           "شناسه واحدها": str(entity), "ستون زمان": str(time),
           "متغیر وابسته": str(dependent), "متغیرهای مستقل": list(map(str, independents)),
           "تعداد واحد": int(work.index.get_level_values(0).nunique()),
           "تعداد دوره": int(work.index.get_level_values(1).nunique())}
    import statsmodels.api as sm
    Xc = sm.add_constant(X)
    fe = re = None
    try:
        out["تلفیقی (Pooled OLS)"] = _fmt(PooledOLS(y, Xc).fit(), "تلفیقی")
    except Exception as e:
        out["تلفیقی_خطا"] = str(e)[:100]
    try:
        fe = PanelOLS(y, Xc, entity_effects=True).fit()
        out["اثرات ثابت (Fixed Effects)"] = _fmt(fe, "اثرات ثابت")
    except Exception as e:
        out["اثرات_ثابت_خطا"] = str(e)[:100]
    try:
        re = RandomEffects(y, Xc).fit()
        out["اثرات تصادفی (Random Effects)"] = _fmt(re, "اثرات تصادفی")
    except Exception as e:
        out["اثرات_تصادفی_خطا"] = str(e)[:100]

    # --- آزمون هاوسمن: کدام مدل مناسب‌تر است ---
    if fe is not None and re is not None:
        try:
            from scipy import stats as sps
            shared = [k for k in fe.params.index if k in re.params.index and k != "const"]
            b_diff = fe.params[shared] - re.params[shared]
            v_diff = fe.cov.loc[shared, shared] - re.cov.loc[shared, shared]
            stat = float(b_diff.values @ np.linalg.pinv(v_diff.values) @ b_diff.values)
            dfree = len(shared)
            if stat < 0:
                # آماره‌ی منفی یعنی ماتریس تفاضل کوواریانس معین مثبت نیست — در
                # نمونه‌های محدود و وقتی برآورد دو مدل بسیار نزدیک‌اند رخ می‌دهد.
                # گزارش‌کردن نتیجه از روی چنین آماره‌ای گمراه‌کننده است.
                out["آزمون هاوسمن"] = {
                    "chi2": round(stat, 3), "df": dfree, "sig": None,
                    "مدل مناسب": "نامشخص",
                    "توضیح": ("آماره منفی شد؛ یعنی ماتریس تفاضل کوواریانس معین مثبت نیست. "
                              "این معمولاً وقتی پیش می‌آید که برآورد اثرات ثابت و تصادفی "
                              "بسیار نزدیک‌اند و شواهدی علیه اثرات تصادفی وجود ندارد. "
                              "آزمون بی‌نتیجه است؛ انتخاب مدل را بر پایه‌ی نظریه و "
                              "ساختار داده انجام دهید."),
                }
            else:
                pv = float(1 - sps.chi2.cdf(stat, dfree))
                out["آزمون هاوسمن"] = {
                    "chi2": round(stat, 3), "df": dfree, "sig": round(pv, 4),
                    "مدل مناسب": "اثرات ثابت" if pv < 0.05 else "اثرات تصادفی",
                    "توضیح": ("فرض صفر «سازگاری اثرات تصادفی» است؛ رد آن یعنی باید از "
                              "اثرات ثابت استفاده کرد."),
                }
        except Exception as e:
            out["هاوسمن_خطا"] = str(e)[:100]
    return out


# ---------------- تشخیصی رگرسیون ----------------

def ts_diagnostics(path: str, dependent: str, independents=None) -> dict:
    """آزمون‌های تشخیصی EViews: خودهمبستگی، ناهمسانی واریانس، نرمالیتی و شکل تبعی."""
    try:
        import statsmodels.api as sm
        from statsmodels.stats.stattools import durbin_watson, jarque_bera
        from statsmodels.stats.diagnostic import (acorr_breusch_godfrey, het_breuschpagan,
                                                  het_white, linear_reset)
    except ImportError:
        return {"error": "برای آزمون‌های تشخیصی نصب statsmodels لازم است"}
    import pandas as pd
    df = _load_dataframe(path)
    num = _numeric(df)
    if dependent not in num.columns:
        return {"error": f"متغیر وابسته «{dependent}» عددی نیست یا در داده نیست"}
    if not independents:
        independents = [c for c in num.columns if c != dependent]
    independents = [c for c in independents if c in num.columns]
    if not independents:
        return {"error": "متغیر مستقل عددی پیدا نشد"}
    data = num[[dependent] + independents].dropna()
    if len(data) < 15:
        return {"error": "تعداد مشاهده‌ها برای آزمون‌های تشخیصی کافی نیست"}
    X = sm.add_constant(data[independents])
    res = sm.OLS(data[dependent], X).fit()

    out = {"software": "معادل خروجی EViews (Residual Diagnostics)",
           "متغیر وابسته": str(dependent),
           "R2": round(float(res.rsquared), 4),
           "R2 تعدیل‌شده": round(float(res.rsquared_adj), 4),
           "F": round(float(res.fvalue), 3), "sig (F)": round(float(res.f_pvalue), 4),
           "n": int(len(data))}
    try:
        dw = float(durbin_watson(res.resid))
        out["دوربین-واتسون"] = {
            "آماره": round(dw, 3),
            "نتیجه": ("خودهمبستگی مثبت" if dw < 1.5 else
                      "خودهمبستگی منفی" if dw > 2.5 else "بدون خودهمبستگی جدی")}
    except Exception:
        pass
    try:
        lm, lmp, f, fp = acorr_breusch_godfrey(res, nlags=min(4, len(data) // 5))
        out["بروش-گادفری (خودهمبستگی)"] = {
            "LM": round(float(lm), 3), "sig": round(float(lmp), 4),
            "خودهمبستگی": "دارد" if lmp < 0.05 else "ندارد"}
    except Exception:
        pass
    for label, fn in (("بروش-پاگان", het_breuschpagan), ("وایت", het_white)):
        try:
            lm, lmp, f, fp = fn(res.resid, X)
            out[f"{label} (ناهمسانی واریانس)"] = {
                "LM": round(float(lm), 3), "sig": round(float(lmp), 4),
                "ناهمسانی": "دارد" if lmp < 0.05 else "ندارد"}
        except Exception:
            pass
    try:
        jb, jbp, skew, kurt = jarque_bera(res.resid)
        out["جارک-برا (نرمالیتی پسماند)"] = {
            "JB": round(float(jb), 3), "sig": round(float(jbp), 4),
            "چولگی": round(float(skew), 3), "کشیدگی": round(float(kurt), 3),
            "نرمال": "بله" if jbp >= 0.05 else "خیر"}
    except Exception:
        pass
    try:
        rr = linear_reset(res, power=2, use_f=True)
        out["رمزی RESET (شکل تبعی)"] = {
            "F": round(float(rr.fvalue), 3), "sig": round(float(rr.pvalue), 4),
            "شکل تبعی درست": "بله" if rr.pvalue >= 0.05 else "خیر — احتمال حذف متغیر یا رابطه‌ی غیرخطی"}
    except Exception:
        pass
    try:
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        out["هم‌خطی (VIF)"] = [
            {"متغیر": str(c),
             "VIF": round(float(variance_inflation_factor(X.values, i)), 3)}
            for i, c in enumerate(X.columns) if c != "const"]
    except Exception:
        pass
    return out


FUNCTIONS = {
    "unit_root": unit_root,
    "cointegration": cointegration,
    "granger": granger,
    "arima": arima,
    "var": var_model,
    "var_model": var_model,
    "vecm": vecm,
    "garch": garch,
    "panel": panel,
    "ts_diagnostics": ts_diagnostics,
}
