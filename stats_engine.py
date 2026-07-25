# -*- coding: utf-8 -*-
"""
stats_engine.py — موتور تحلیل آماری واقعی آنتانو برای فصل چهارم رساله
اجرای واقعی محاسبات با pandas/scipy/statsmodels/pingouin و گزارش دانشگاهی فارسی
"""
import io
import os
import json
import traceback


def _load_dataframe(path: str):
    """خواندن فایل داده با هر فرمت رایج — و در صورت پسوند ناشناخته، تلاش هوشمند"""
    import pandas as pd
    ext = os.path.splitext(path)[1].lower()

    def _read_delimited(p):
        # چند جداکننده را امتحان کن و آن را که بیشترین ستون معنادار را می‌دهد انتخاب کن
        best = None
        for kwargs in ({"sep": None, "engine": "python"}, {}, {"sep": "\t"},
                       {"sep": ";"}, {"sep": "|"}, {"delim_whitespace": True}):
            try:
                d = pd.read_csv(p, **kwargs)
            except Exception:
                continue
            if d.shape[0] < 1:
                continue
            if best is None or d.shape[1] > best.shape[1]:
                best = d
        if best is not None:
            return best
        return pd.read_csv(p)  # آخرین تلاش — خطایش را بالا بده

    if ext in (".csv", ".txt", ".tsv", ".tab", ".dat", ".data"):
        return _read_delimited(path)
    if ext in (".xlsx", ".xls", ".xlsm", ".xlsb", ".ods"):
        return pd.read_excel(path)
    if ext == ".sav":
        try:
            import pyreadstat
            df, _ = pyreadstat.read_sav(path)
            return df
        except Exception:
            return pd.read_spss(path)
    if ext == ".dta":
        return pd.read_stata(path)
    if ext in (".json", ".jsonl"):
        try:
            return pd.read_json(path)
        except Exception:
            return pd.read_json(path, lines=True)
    if ext in (".parquet", ".pq"):
        return pd.read_parquet(path)
    if ext in (".html", ".htm"):
        tables = pd.read_html(path)
        if tables:
            return tables[0]
        raise ValueError("جدولی در فایل HTML پیدا نشد")
    if ext == ".pdf":
        return _pdf_to_df(path)
    if ext in (".docx", ".doc"):
        return _docx_to_df(path)
    # پسوند ناشناخته: اول Excel، بعد جداکننده‌ی متنی
    try:
        return pd.read_excel(path)
    except Exception:
        return _read_delimited(path)


def _rows_to_df(rows):
    """چند ردیف (هرکدام فهرستی از سلول‌ها) → دیتافریم با تشخیص سرستون و تبدیل عددی"""
    import pandas as pd
    rows = [r for r in rows if r]
    if len(rows) < 2:
        raise ValueError("ساختار جدولی در فایل تشخیص داده نشد (حداقل یک سرستون و یک ردیف داده لازم است)")
    from collections import Counter
    ncol = Counter(len(r) for r in rows).most_common(1)[0][0]
    if ncol < 2:
        raise ValueError("ساختار جدولی چندستونی در فایل پیدا نشد")
    data = [r for r in rows if len(r) == ncol]
    if len(data) < 2:
        raise ValueError("تعداد ستون‌ها در ردیف‌ها یکسان نیست؛ داده‌ی جدولی منظم پیدا نشد")

    def _is_num(x):
        try:
            float(str(x).replace("٫", ".").replace("،", "").replace(",", ""))
            return True
        except (ValueError, TypeError):
            return False

    header = data[0]
    if all(_is_num(h) for h in header):  # سرستون عددی است → خودمان نام می‌گذاریم
        cols = [f"ستون{i + 1}" for i in range(ncol)]
        body = data
    else:
        cols = [str(h).strip() or f"ستون{i + 1}" for i, h in enumerate(header)]
        body = data[1:]
    df = pd.DataFrame(body, columns=cols)
    # ستون‌های عددی را واقعاً عددی کن (با پشتیبانی از اعشار فارسی)
    for c in df.columns:
        conv = pd.to_numeric(
            df[c].astype(str).str.replace("٫", ".", regex=False)
                 .str.replace("،", "", regex=False).str.replace(",", "", regex=False),
            errors="coerce",
        )
        if conv.notna().sum() >= max(1, int(0.6 * len(conv))):  # اگر بیشترش عدد بود
            df[c] = conv
    return df


def _split_row(line: str):
    """یک خط متن را به سلول‌ها می‌شکند (تب یا دو فاصله یا بیشتر)"""
    import re as _re
    cells = _re.split(r"\t|\s{2,}", line.strip())
    return [c.strip() for c in cells if c.strip() != ""]


def _text_fallback_df(lines):
    """وقتی هیچ ساختار جدولی پیدا نشد: اگر عدد هست یک ستون عددی بساز، وگرنه یک ستون متنی.
    این تضمین می‌کند فایل‌های بدون جدول هم پذیرفته شوند و آپلود شکست نخورد."""
    import pandas as pd
    import re as _re
    nums = []
    for ln in lines:
        for tok in _re.findall(r"-?\d+(?:[.,٫]\d+)?", str(ln)):
            try:
                nums.append(float(tok.replace("٫", ".").replace(",", "")))
            except ValueError:
                pass
    if len(nums) >= 3:
        return pd.DataFrame({"مقدار": nums})
    clean = [str(ln).strip() for ln in lines if str(ln).strip()]
    if not clean:
        raise ValueError("هیچ داده‌ای در فایل پیدا نشد")
    return pd.DataFrame({"متن": clean})


def _rows_to_df_or_text(rows, lines):
    """اول تلاش برای جدول؛ اگر نشد، بازگشت به تک‌ستونی (پذیرش فایل بدون جدول)"""
    try:
        return _rows_to_df(rows)
    except Exception:
        return _text_fallback_df(lines)


def _pdf_to_df(path: str):
    """استخراج جدول/داده از فایل PDF (حتی اگر جدول واقعی نباشد، از ساختار متن حدس می‌زند)"""
    from pypdf import PdfReader
    reader = PdfReader(path)
    lines = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        for ln in txt.split("\n"):
            if ln.strip():
                lines.append(ln)
    if not lines:
        raise ValueError("متنی در PDF پیدا نشد (احتمالاً اسکن‌شده است)؛ لطفاً فایل Excel/CSV بفرستید")
    rows = [_split_row(ln) for ln in lines]
    rows = [r for r in rows if r]
    # اگر با تب/دوفاصله ستون‌بندی نشد، با تک‌فاصله تلاش کن
    from collections import Counter
    import re as _re
    if Counter(len(r) for r in rows).most_common(1)[0][0] < 2:
        rows = [[c for c in _re.split(r"\s+", ln.strip()) if c] for ln in lines]
    # اگر جدولی پیدا نشد، فایل را به‌صورت تک‌ستونی بپذیر (نه رد کن)
    return _rows_to_df_or_text(rows, lines)


def _docx_to_df(path: str):
    """استخراج داده از Word: اول جدول‌های واقعی، بعد متن پاراگراف‌ها"""
    from docx import Document
    doc = Document(path)
    # ۱) اگر جدول واقعی دارد، همان را بردار
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                rows.append(cells)
        if len(rows) >= 2:
            return _rows_to_df(rows)
    # ۲) از متن پاراگراف‌ها حدس بزن؛ اگر جدولی نبود، تک‌ستونی بپذیر
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    if not lines:
        raise ValueError("هیچ متن یا داده‌ای در فایل Word پیدا نشد")
    rows = [_split_row(ln) for ln in lines]
    return _rows_to_df_or_text(rows, lines)


def dataset_overview(path: str) -> dict:
    """توصیف کلی داده: ابعاد، ستون‌ها، نوع، گمشده‌ها، آمار توصیفی"""
    import pandas as pd
    df = _load_dataframe(path)
    num = df.select_dtypes("number")
    desc_rows = []
    for col in df.columns:
        s = df[col]
        row = {
            "متغیر": str(col),
            "نوع": "عددی" if pd.api.types.is_numeric_dtype(s) else "متنی/رسته‌ای",
            "تعداد معتبر": int(s.notna().sum()),
            "گمشده": int(s.isna().sum()),
        }
        if pd.api.types.is_numeric_dtype(s):
            row.update({
                "میانگین": round(float(s.mean()), 3) if s.notna().any() else None,
                "انحراف معیار": round(float(s.std()), 3) if s.notna().any() else None,
                "کمینه": round(float(s.min()), 3) if s.notna().any() else None,
                "بیشینه": round(float(s.max()), 3) if s.notna().any() else None,
            })
        desc_rows.append(row)
    return {
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "columns": [str(c) for c in df.columns],
        "numeric_columns": [str(c) for c in num.columns],
        "describe": desc_rows,
        "total_missing": int(df.isna().sum().sum()),
    }


def assumptions(path: str, cols=None) -> dict:
    """آزمون پیش‌فرض‌ها: نرمال‌بودن، پرت، همسانی واریانس، هم‌خطی"""
    import pandas as pd
    import numpy as np
    from scipy import stats
    df = _load_dataframe(path)
    num = df.select_dtypes("number")
    if cols:
        num = num[[c for c in cols if c in num.columns]]
    out = {"normality": [], "outliers": [], "multicollinearity": []}

    # نرمال‌بودن (شاپیرو-ویلک)
    for col in num.columns:
        s = num[col].dropna()
        if len(s) >= 3:
            try:
                w, p = stats.shapiro(s[:5000])
                out["normality"].append({
                    "متغیر": str(col), "آماره شاپیرو-ویلک": round(float(w), 3),
                    "sig": round(float(p), 3), "نرمال": "بله" if p > 0.05 else "خیر",
                })
            except Exception:
                pass
        # پرت (روش IQR)
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        n_out = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
        out["outliers"].append({"متغیر": str(col), "تعداد داده پرت": n_out})

    # هم‌خطی (VIF)
    try:
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        from statsmodels.tools.tools import add_constant
        X = add_constant(num.dropna())
        for i, col in enumerate(X.columns):
            if col == "const":
                continue
            vif = variance_inflation_factor(X.values, i)
            out["multicollinearity"].append({
                "متغیر": str(col), "VIF": round(float(vif), 3),
                "وضعیت": "مشکل هم‌خطی" if vif > 10 else ("هشدار" if vif > 5 else "سالم"),
            })
    except Exception:
        pass
    return out


def reliability(path: str, cols=None) -> dict:
    """آلفای کرونباخ برای پایایی پرسشنامه"""
    import pandas as pd
    import numpy as np
    df = _load_dataframe(path)
    num = df.select_dtypes("number")
    if cols:
        num = num[[c for c in cols if c in num.columns]]
    data = num.dropna()
    k = data.shape[1]
    if k < 2:
        return {"error": "برای آلفای کرونباخ حداقل ۲ متغیر لازم است"}
    item_var = data.var(axis=0, ddof=1).sum()
    total_var = data.sum(axis=1).var(ddof=1)
    alpha = (k / (k - 1)) * (1 - item_var / total_var) if total_var else 0
    quality = ("عالی" if alpha >= 0.9 else "خوب" if alpha >= 0.8
               else "قابل قبول" if alpha >= 0.7 else "ضعیف")
    return {"software": "معادل خروجی SPSS (Reliability — Cronbach's Alpha)",
            "alpha": round(float(alpha), 3), "items": int(k), "quality": quality}


def correlation(path: str, method="pearson", cols=None) -> dict:
    """ماتریس همبستگی پیرسون/اسپیرمن با سطح معناداری"""
    import pandas as pd
    from scipy import stats
    df = _load_dataframe(path)
    num = df.select_dtypes("number")
    if cols:
        num = num[[c for c in cols if c in num.columns]]
    num = num.dropna()
    corr = num.corr(method=method).round(3)
    result = []
    colnames = list(num.columns)
    for i, a in enumerate(colnames):
        for b in colnames[i + 1:]:
            if method == "pearson":
                r, p = stats.pearsonr(num[a], num[b])
            else:
                r, p = stats.spearmanr(num[a], num[b])
            result.append({
                "متغیر ۱": str(a), "متغیر ۲": str(b),
                "ضریب همبستگی": round(float(r), 3), "sig": round(float(p), 3),
                "معنادار": "بله" if p < 0.05 else "خیر",
            })
    return {"software": "معادل خروجی SPSS (Correlations)", "method": method, "pairs": result}


def regression(path: str, dependent: str, independents, kind="linear") -> dict:
    """رگرسیون خطی/چندگانه/لجستیک با گزارش کامل"""
    import pandas as pd
    import numpy as np
    import statsmodels.api as sm
    df = _load_dataframe(path)
    cols = [dependent] + list(independents)
    data = df[cols].dropna()
    y = data[dependent]
    X = sm.add_constant(data[list(independents)])

    if kind == "logistic":
        model = sm.Logit(y, X).fit(disp=0)
    else:
        model = sm.OLS(y, X).fit()

    # بتای استاندارد (مثل ستون Beta در جدول ضرایب SPSS)
    sy = float(y.std(ddof=1)) or 1.0
    coefs = []
    for name in X.columns:
        b = float(model.params[name])
        se = float(model.bse[name])
        if name == "const":
            beta = None
        else:
            sx = float(data[name].std(ddof=1))
            beta = round(b * sx / sy, 3)
        coefs.append({
            "متغیر": "ثابت (Constant)" if name == "const" else str(name),
            "ضریب B": round(b, 4),
            "خطای استاندارد": round(se, 4),
            "بتای استاندارد": beta if beta is not None else "—",
            "آماره t": round(float(model.tvalues[name]), 3),
            "sig": round(float(model.pvalues[name]), 4),
            "معنادار": "بله" if model.pvalues[name] < 0.05 else "خیر",
        })

    out = {"kind": kind, "n": int(data.shape[0]),
           "software": "معادل خروجی SPSS / EViews (رگرسیون OLS)",
           "coefficients": coefs}
    if kind == "logistic":
        out.update({
            "software": "معادل خروجی SPSS (رگرسیون لجستیک)",
            "pseudo_r2": round(float(model.prsquared), 3),
            "llr_p": round(float(model.llr_pvalue), 4),
        })
    else:
        out.update({
            "r": round(float(model.rsquared ** 0.5), 3),
            "r2": round(float(model.rsquared), 3),
            "adj_r2": round(float(model.rsquared_adj), 3),
            "std_error_est": round(float((model.mse_resid) ** 0.5), 4),
            "f_stat": round(float(model.fvalue), 3),
            "f_sig": round(float(model.f_pvalue), 4),
            "durbin_watson": round(float(sm.stats.durbin_watson(model.resid)), 3),
        })
    return out


def ttest(path: str, kind, col, group=None, value2=None, popmean=0) -> dict:
    """آزمون t تک‌نمونه‌ای / مستقل / زوجی"""
    import pandas as pd
    from scipy import stats
    df = _load_dataframe(path)
    if kind == "one_sample":
        s = df[col].dropna()
        t, p = stats.ttest_1samp(s, popmean)
        return {"kind": "تک‌نمونه‌ای", "t": round(float(t), 3), "sig": round(float(p), 4),
                "mean": round(float(s.mean()), 3), "معنادار": "بله" if p < 0.05 else "خیر"}
    if kind == "independent":
        groups = df[group].dropna().unique()[:2]
        g1 = df[df[group] == groups[0]][col].dropna()
        g2 = df[df[group] == groups[1]][col].dropna()
        t, p = stats.ttest_ind(g1, g2)
        return {"kind": "مستقل", "t": round(float(t), 3), "sig": round(float(p), 4),
                "mean1": round(float(g1.mean()), 3), "mean2": round(float(g2.mean()), 3),
                "معنادار": "بله" if p < 0.05 else "خیر"}
    if kind == "paired":
        a = df[col].dropna()
        b = df[value2].dropna()
        n = min(len(a), len(b))
        t, p = stats.ttest_rel(a[:n], b[:n])
        return {"kind": "زوجی", "t": round(float(t), 3), "sig": round(float(p), 4),
                "معنادار": "بله" if p < 0.05 else "خیر"}
    return {"error": "نوع آزمون نامعتبر"}


def anova(path: str, dependent: str, factor: str) -> dict:
    """تحلیل واریانس یک‌راهه"""
    import pandas as pd
    from scipy import stats
    df = _load_dataframe(path)
    groups = [g[dependent].dropna().values for _, g in df.groupby(factor)]
    f, p = stats.f_oneway(*groups)
    return {"software": "معادل خروجی SPSS (One-Way ANOVA)",
            "f": round(float(f), 3), "sig": round(float(p), 4),
            "groups": int(len(groups)), "معنادار": "بله" if p < 0.05 else "خیر"}


def factor_analysis(path: str, cols=None, n_factors=None) -> dict:
    """تحلیل عاملی اکتشافی + KMO و بارتلت"""
    import pandas as pd
    df = _load_dataframe(path)
    num = df.select_dtypes("number")
    if cols:
        num = num[[c for c in cols if c in num.columns]]
    data = num.dropna()
    out = {"software": "معادل خروجی SPSS (Factor Analysis — KMO / Bartlett / Varimax)"}
    try:
        from factor_analyzer.factor_analyzer import calculate_kmo, calculate_bartlett_sphericity
        chi2, p = calculate_bartlett_sphericity(data)
        kmo_all, kmo_model = calculate_kmo(data)
        out["kmo"] = round(float(kmo_model), 3)
        out["bartlett_sig"] = round(float(p), 4)
        out["kmo_quality"] = ("عالی" if kmo_model >= 0.8 else "خوب" if kmo_model >= 0.7
                              else "متوسط" if kmo_model >= 0.6 else "ضعیف")
        from factor_analyzer import FactorAnalyzer
        nf = n_factors or min(3, data.shape[1] - 1)
        fa = FactorAnalyzer(n_factors=nf, rotation="varimax")
        fa.fit(data)
        loadings = fa.loadings_
        out["loadings"] = [
            {"متغیر": str(c), **{f"عامل {j+1}": round(float(loadings[i][j]), 3)
                                 for j in range(loadings.shape[1])}}
            for i, c in enumerate(data.columns)
        ]
    except ImportError:
        out["error"] = "برای تحلیل عاملی نصب factor_analyzer لازم است"
    except Exception as e:
        out["error"] = str(e)
    return out


def mediation(path: str, x: str, m: str, y: str) -> dict:
    """تحلیل میانجی‌گری با بوت‌استرپ (اثر مستقیم، غیرمستقیم، کل)"""
    import pandas as pd
    import numpy as np
    import statsmodels.api as sm
    df = _load_dataframe(path)
    data = df[[x, m, y]].dropna()
    # مسیر a: X → M
    a_model = sm.OLS(data[m], sm.add_constant(data[x])).fit()
    a = a_model.params[x]
    # مسیر b و c': M,X → Y
    by_model = sm.OLS(data[y], sm.add_constant(data[[x, m]])).fit()
    b = by_model.params[m]
    c_prime = by_model.params[x]
    # اثر کل c: X → Y
    c_model = sm.OLS(data[y], sm.add_constant(data[x])).fit()
    c = c_model.params[x]
    indirect = a * b
    # بوت‌استرپ برای معناداری اثر غیرمستقیم
    rng = np.random.default_rng(42)
    boot = []
    n = len(data)
    for _ in range(1000):
        idx = rng.integers(0, n, n)
        d = data.iloc[idx]
        try:
            aa = sm.OLS(d[m], sm.add_constant(d[x])).fit().params[x]
            bb = sm.OLS(d[y], sm.add_constant(d[[x, m]])).fit().params[m]
            boot.append(aa * bb)
        except Exception:
            continue
    lo, hi = np.percentile(boot, [2.5, 97.5])
    sig = not (lo <= 0 <= hi)
    return {
        "software": "معادل خروجی PROCESS Macro / SmartPLS (تحلیل میانجی با بوت‌استرپ)",
        "direct_effect": round(float(c_prime), 4),
        "indirect_effect": round(float(indirect), 4),
        "total_effect": round(float(c), 4),
        "boot_ci": [round(float(lo), 4), round(float(hi), 4)],
        "indirect_significant": "بله" if sig else "خیر",
        "mediation_type": ("میانجی کامل" if sig and abs(c_prime) < 0.05
                           else "میانجی جزئی" if sig else "بدون میانجی‌گری"),
    }


# نگاشت نام تابع → تابع (برای فراخوانی از main)
FUNCTIONS = {
    "overview": dataset_overview,
    "assumptions": assumptions,
    "reliability": reliability,
    "correlation": correlation,
    "regression": regression,
    "ttest": ttest,
    "anova": anova,
    "factor_analysis": factor_analysis,
    "mediation": mediation,
}


def run(func_name: str, path: str, **kwargs) -> dict:
    """اجرای امن یک تحلیل و بازگرداندن نتیجه یا خطا"""
    try:
        fn = FUNCTIONS.get(func_name)
        if not fn:
            return {"error": f"تحلیل «{func_name}» پشتیبانی نمی‌شود"}
        return fn(path, **kwargs)
    except Exception as e:
        return {"error": f"خطا در اجرای تحلیل: {e}", "trace": traceback.format_exc()[-500:]}


# ---------------- معادلات ساختاری مبتنی بر کوواریانس (CFA/SEM) ----------------

def sem_cfa(path: str, model_spec: str = None, factors: dict = None) -> dict:
    """
    تحلیل عاملی تأییدی و مدل ساختاری با semopy.
    model_spec: توصیف مدل به زبان lavaan/semopy، مثل:
        "F1 =~ x1 + x2 + x3\nF2 =~ y1 + y2\nF2 ~ F1"
    یا factors: دیکشنری {"نام سازه": ["گویه۱","گویه۲",...]} برای ساخت خودکار CFA
    """
    try:
        import semopy
    except ImportError:
        return {"error": "کتابخانه semopy نصب نیست. برای SEM این دستور را اجرا کنید: pip install semopy"}
    df = _load_dataframe(path)

    if not model_spec:
        if not factors:
            return {"error": "برای SEM باید model_spec یا factors بدهید"}
        lines = []
        for fname, items in factors.items():
            valid = [c for c in items if c in df.columns]
            if len(valid) < 2:
                return {"error": f"سازه «{fname}» حداقل به ۲ گویه معتبر نیاز دارد"}
            lines.append(f"{fname} =~ " + " + ".join(valid))
        model_spec = "\n".join(lines)

    mod = semopy.Model(model_spec)
    mod.fit(df)
    stats = semopy.calc_stats(mod)
    ins = mod.inspect(std_est=True)

    def g(name):
        try:
            return round(float(stats[name].iloc[0]), 3)
        except Exception:
            return None

    fit = {
        "chi_square": g("chi2"), "df": g("DoF"),
        "p_value": g("chi2 p-value"),
        "CFI": g("CFI"), "TLI": g("TLI"), "RMSEA": g("RMSEA"),
        "GFI": g("GFI"), "AGFI": g("AGFI"), "NFI": g("NFI"), "SRMR": g("SRMR"),
    }
    cmin_df = None
    if fit["chi_square"] and fit["df"]:
        cmin_df = round(fit["chi_square"] / fit["df"], 3)

    # بارهای عاملی استانداردشده
    loadings = []
    try:
        for _, r in ins.iterrows():
            if r["op"] == "=~":
                loadings.append({
                    "factor": r["lval"], "item": r["rval"],
                    "loading": round(float(r["Est. Std"]), 3) if "Est. Std" in r else None,
                    "p_value": round(float(r["p-value"]), 4) if r.get("p-value") not in (None, "-") else None,
                })
    except Exception:
        pass

    # ارزیابی برازش
    verdict = []
    if cmin_df is not None:
        verdict.append(("χ²/df", cmin_df, "خوب" if cmin_df < 3 else "قابل قبول" if cmin_df < 5 else "ضعیف"))
    if fit["RMSEA"] is not None:
        verdict.append(("RMSEA", fit["RMSEA"], "خوب" if fit["RMSEA"] < 0.08 else "ضعیف"))
    if fit["CFI"] is not None:
        verdict.append(("CFI", fit["CFI"], "خوب" if fit["CFI"] > 0.9 else "ضعیف"))
    if fit["TLI"] is not None:
        verdict.append(("TLI", fit["TLI"], "خوب" if fit["TLI"] > 0.9 else "ضعیف"))

    return {
        "type": "CFA/SEM مبتنی بر کوواریانس (semopy)",
        "model_spec": model_spec,
        "fit_indices": fit,
        "cmin_df": cmin_df,
        "loadings": loadings,
        "fit_verdict": verdict,
        "n": len(df),
    }


# ---------------- معادلات ساختاری حداقل مربعات جزئی (PLS-SEM) ----------------

def sem_pls(path: str, factors: dict = None, structural: list = None) -> dict:
    """
    PLS-SEM ساده: بارهای عاملی، آلفای کرونباخ، پایایی ترکیبی (CR)، AVE و روایی واگرا.
    factors: {"سازه": ["گویه۱",...]}
    structural: [["مستقل","وابسته"], ...] (اختیاری، برای ضرایب مسیر)
    """
    try:
        import numpy as np
        import pandas as pd
        from sklearn.decomposition import PCA
    except ImportError:
        return {"error": "numpy/pandas/scikit-learn لازم است"}
    if not factors:
        return {"error": "برای PLS باید سازه‌ها و گویه‌ها (factors) را بدهید"}

    df = _load_dataframe(path)
    constructs = {}
    scores = {}
    for fname, items in factors.items():
        valid = [c for c in items if c in df.columns]
        if len(valid) < 2:
            return {"error": f"سازه «{fname}» حداقل به ۲ گویه معتبر نیاز دارد"}
        sub = df[valid].dropna().apply(pd.to_numeric, errors="coerce").dropna()
        # نمره سازه = مؤلفه اصلی اول
        pca = PCA(n_components=1)
        comp = pca.fit_transform((sub - sub.mean()) / sub.std(ddof=1))
        loadings = []
        for c in valid:
            loadings.append(round(float(np.corrcoef(sub[c], comp[:, 0])[0, 1]), 3))
        loadings = [abs(x) for x in loadings]
        # AVE و CR
        ave = round(float(np.mean([l**2 for l in loadings])), 3)
        sum_l = sum(loadings)
        sum_e = sum(1 - l**2 for l in loadings)
        cr = round(sum_l**2 / (sum_l**2 + sum_e), 3)
        # آلفای کرونباخ
        k = len(valid)
        var_sum = sub.var(ddof=1).sum()
        tot_var = sub.sum(axis=1).var(ddof=1)
        alpha = round((k / (k - 1)) * (1 - var_sum / tot_var), 3) if tot_var > 0 else None
        constructs[fname] = {
            "items": valid, "loadings": dict(zip(valid, loadings)),
            "cronbach_alpha": alpha, "CR": cr, "AVE": ave,
            "ave_ok": ave >= 0.5, "cr_ok": cr >= 0.7,
        }
        scores[fname] = comp[:, 0]

    # روایی واگرا (فورنل-لارکر): جذر AVE در برابر همبستگی سازه‌ها
    fornell = {}
    names = list(constructs.keys())
    sdf = pd.DataFrame(scores)
    corr = sdf.corr()
    for f in names:
        fornell[f] = {"sqrt_AVE": round(constructs[f]["AVE"] ** 0.5, 3)}
        for g2 in names:
            if f != g2:
                fornell[f][f"r_با_{g2}"] = round(float(corr.loc[f, g2]), 3)

    # ضرایب مسیر ساختاری استانداردشده + R² هر سازه‌ی درون‌زا (رگرسیون چندگانه)
    paths = []
    r2_by_construct = {}
    if structural:
        from sklearn.linear_model import LinearRegression
        # نمرات سازه‌ها را استاندارد می‌کنیم تا ضرایب، «بتای استاندارد» شوند
        z = (sdf - sdf.mean()) / sdf.std(ddof=1)
        outcomes = {}
        for pair in structural:
            if len(pair) == 2 and pair[0] in scores and pair[1] in scores:
                outcomes.setdefault(pair[1], []).append(pair[0])
        for outcome, preds in outcomes.items():
            preds = list(dict.fromkeys(preds))  # حذف تکراری، حفظ ترتیب
            X = z[preds].values
            y = z[outcome].values
            lr = LinearRegression().fit(X, y)
            r2 = round(float(lr.score(X, y)), 3)
            r2_by_construct[outcome] = r2
            for i, p in enumerate(preds):
                paths.append({
                    "from": p, "to": outcome,
                    "beta": round(float(lr.coef_[i]), 3),
                    "R2": r2,
                })

    return {
        "type": "PLS-SEM (تخمین با PCA و رگرسیون)",
        "constructs": constructs,
        "fornell_larcker": fornell,
        "paths": paths,
        "r2_by_construct": r2_by_construct,
        "n": len(sdf),
        "note": "این تخمین سبک PLS است؛ برای گزارش رسمی رساله، خروجی SmartPLS نیز توصیه می‌شود.",
    }


FUNCTIONS["sem_cfa"] = sem_cfa
FUNCTIONS["sem"] = sem_cfa
FUNCTIONS["sem_pls"] = sem_pls
FUNCTIONS["pls"] = sem_pls
