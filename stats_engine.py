# -*- coding: utf-8 -*-
"""
stats_engine.py — موتور تحلیل آماری واقعی آنتانو برای فصل چهارم رساله
اجرای واقعی محاسبات با pandas/scipy/statsmodels/pingouin و گزارش دانشگاهی فارسی
"""
import io
import os
import json
import traceback


def _clean_columns(df):
    """نام ستون‌ها را تمیز می‌کند.

    اکسل هنگام ذخیره‌ی CSV یک نشانه‌ی BOM اول فایل می‌گذارد که به نام ستون اول
    می‌چسبد؛ آن‌وقت «گروه» با «﻿گروه» برابر نمی‌شود و کاربر خطای «ستون پیدا نشد»
    می‌گیرد. فاصله‌های اضافه و نویسه‌های جهت‌نما هم پاک می‌شوند.
    """
    import re as _re
    try:
        df.columns = [
            _re.sub(r"[‎‏‪-‮]", "",
                    str(c).replace("﻿", "")).strip()
            for c in df.columns
        ]
    except Exception:
        pass
    return df


def _load_dataframe(path: str):
    """خواندن فایل داده با هر فرمت رایج، با نام ستون‌های تمیزشده."""
    return _clean_columns(_load_dataframe_raw(path))


def _load_dataframe_raw(path: str):
    """خواندن فایل داده با هر فرمت رایج — و در صورت پسوند ناشناخته، تلاش هوشمند"""
    import pandas as pd
    ext = os.path.splitext(path)[1].lower()

    def _read_delimited(p):
        # چند جداکننده را امتحان کن و آن را که بیشترین ستون معنادار را می‌دهد انتخاب کن
        best = None
        for kwargs in ({"sep": None, "engine": "python"}, {}, {"sep": "\t"},
                       {"sep": ";"}, {"sep": "|"}, {"delim_whitespace": True}):
            try:
                # utf-8-sig یعنی اگر فایل BOM داشت (خروجی اکسل) خودکار برداشته شود
                d = pd.read_csv(p, encoding="utf-8-sig", **kwargs)
            except Exception:
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


def _regression_ordinal(data, dependent, independents) -> dict:
    """رگرسیون لجستیک ترتیبی — برای متغیر وابسته‌ی رتبه‌ای (مثل طیف لیکرت: خیلی‌کم…خیلی‌زیاد).
    معادل PLUM در SPSS (Analyze ▸ Regression ▸ Ordinal)."""
    from statsmodels.miscmodels.ordinal_model import OrderedModel
    y = data[dependent].astype("category")
    X = data[list(independents)]
    model = OrderedModel(y, X, distr="logit").fit(method="bfgs", disp=0)
    n_th = len(y.cat.categories) - 1
    coefs = [{"متغیر": str(name), "ضریب": round(float(model.params[name]), 4),
             "sig": round(float(model.pvalues[name]), 4),
             "معنادار": "بله" if model.pvalues[name] < 0.05 else "خیر"}
            for name in independents]
    cuts = [{"آستانه": i + 1, "مقدار": round(float(model.params[p]), 4)}
           for i, p in enumerate(model.params.index[-n_th:])]
    return {"kind": "ordinal", "n": int(len(data)),
           "software": "معادل خروجی SPSS (رگرسیون ترتیبی — PLUM)",
           "coefficients": coefs, "آستانه‌ها": cuts,
           "سطوح متغیر وابسته": [str(c) for c in y.cat.categories],
           "llr_p": round(float(model.llr_pvalue), 4) if hasattr(model, "llr_pvalue") else None}


def _regression_multinomial(data, dependent, independents) -> dict:
    """رگرسیون لجستیک چندجمله‌ای — برای متغیر وابسته‌ی طبقه‌ای با بیش از دو سطح
    بدون ترتیب (مثل انتخاب برند). معادل NOMREG در SPSS."""
    import statsmodels.api as sm
    y = data[dependent].astype("category")
    ref = str(y.cat.categories[0])
    X = sm.add_constant(data[list(independents)])
    model = sm.MNLogit(y.cat.codes, X).fit(disp=0, method="bfgs")
    # جدول تخت (نه تودرتو) تا در گزارش مارک‌داون یک جدول تمیز بشود، نه یک
    # دیکشنری خام داخل سلول.
    rows = []
    for j, level in enumerate(y.cat.categories[1:]):
        for name in X.columns:
            rows.append({
                "سطح (در برابر مرجع)": str(level),
                "متغیر": "ثابت (Constant)" if name == "const" else str(name),
                "ضریب": round(float(model.params.loc[name, j]), 4),
                "sig": round(float(model.pvalues.loc[name, j]), 4),
                "معنادار": "بله" if model.pvalues.loc[name, j] < 0.05 else "خیر",
            })
    return {"kind": "multinomial", "n": int(len(data)),
           "software": "معادل خروجی SPSS (رگرسیون لجستیک چندجمله‌ای — NOMREG)",
           "سطح مرجع": ref, "ضرایب": rows,
           "pseudo_r2": round(float(model.prsquared), 3)}


def _regression_count(data, dependent, independents, kind) -> dict:
    """رگرسیون پواسون/دوجمله‌ای‌منفی — برای متغیر وابسته‌ی شمارشی (مثل تعداد مراجعه،
    تعداد خطا). دوجمله‌ای‌منفی وقتی واریانس خیلی بیشتر از میانگین است (پراپخشیدگی)."""
    import numpy as np
    import statsmodels.api as sm
    y = data[dependent]
    X = sm.add_constant(data[list(independents)])
    Model = sm.NegativeBinomial if kind == "negbinom" else sm.Poisson
    model = Model(y, X).fit(disp=0)
    coefs = []
    for name in X.columns:
        b = float(model.params[name])
        coefs.append({"متغیر": "ثابت (Constant)" if name == "const" else str(name),
                     "ضریب B": round(b, 4),
                     "نسبت بروز (IRR)": round(float(np.exp(b)), 3),
                     "sig": round(float(model.pvalues[name]), 4),
                     "معنادار": "بله" if model.pvalues[name] < 0.05 else "خیر"})
    label = "دوجمله‌ای‌منفی" if kind == "negbinom" else "پواسون"
    return {"kind": kind, "n": int(len(data)),
           "software": f"معادل خروجی SPSS/EViews (رگرسیون {label})",
           "coefficients": coefs,
           "pseudo_r2": round(float(model.prsquared), 3) if hasattr(model, "prsquared") else None,
           "llr_p": round(float(model.llr_pvalue), 4)}


def regression(path: str, dependent: str, independents, kind="linear") -> dict:
    """رگرسیون خطی/چندگانه/لجستیک/ترتیبی/چندجمله‌ای/شمارشی با گزارش کامل.

    kind: linear (پیش‌فرض) / logistic / ordinal (وابسته‌ی رتبه‌ای مثل لیکرت) /
    multinomial (وابسته‌ی طبقه‌ایِ بدون ترتیب) / poisson یا negbinom (وابسته‌ی شمارشی).
    """
    import pandas as pd
    import numpy as np
    import statsmodels.api as sm
    df = _load_dataframe(path)
    cols = [dependent] + list(independents)
    data = df[cols].dropna()

    if kind == "ordinal":
        return _regression_ordinal(data, dependent, independents)
    if kind == "multinomial":
        return _regression_multinomial(data, dependent, independents)
    if kind in ("poisson", "negbinom"):
        return _regression_count(data, dependent, independents, kind)

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


def _posthoc_bonferroni(sub, dependent, factor, groups, names) -> list:
    """تعقیبیِ بونفرونی: مثل توکی، واریانسِ برابر فرض می‌شود؛ p با تعداد جفت‌مقایسه‌ها ضرب می‌شود."""
    from scipy import stats
    import itertools
    k = len(groups)
    ss_within = sum(((g - g.mean()) ** 2).sum() for g in groups)
    df_within = sum(len(g) for g in groups) - k
    mse = ss_within / df_within if df_within > 0 else None
    m = k * (k - 1) // 2
    rows = []
    for (i, gi), (j, gj) in itertools.combinations(enumerate(groups), 2):
        diff = float(gi.mean() - gj.mean())
        se = (mse * (1 / len(gi) + 1 / len(gj))) ** 0.5 if mse else None
        t = diff / se if se else None
        p = float(2 * stats.t.sf(abs(t), df_within)) if t is not None else None
        p_adj = min(1.0, p * m) if p is not None else None
        rows.append({"گروه ۱": names[i], "گروه ۲": names[j],
                     "اختلاف میانگین": round(diff, 3),
                     "sig": round(p_adj, 4) if p_adj is not None else None,
                     "معنادار": "بله" if (p_adj is not None and p_adj < 0.05) else "خیر"})
    return rows


def _posthoc_games_howell(groups, names) -> list:
    """تعقیبیِ گیمز-هاول: برای وقتی فرضِ برابریِ واریانس‌ها (لِوین) نقض شده.

    مثل توکی از توزیعِ دامنه‌ی دانشجویی‌شده استفاده می‌کند، ولی df با فرمول
    ولچ-ساترثویت محاسبه می‌شود (به‌جای df ساده‌ی درون‌گروهی)."""
    import numpy as np
    from statsmodels.stats.libqsturng import psturng
    import itertools
    k = len(groups)
    rows = []
    for (i, gi), (j, gj) in itertools.combinations(enumerate(groups), 2):
        ni, nj = len(gi), len(gj)
        vi, vj = float(gi.var(ddof=1)), float(gj.var(ddof=1))
        diff = float(gi.mean() - gj.mean())
        se = ((vi / ni + vj / nj) / 2) ** 0.5
        df = ((vi / ni + vj / nj) ** 2 /
             ((vi / ni) ** 2 / (ni - 1) + (vj / nj) ** 2 / (nj - 1))) if ni > 1 and nj > 1 else None
        if se == 0 or df is None:
            rows.append({"گروه ۱": names[i], "گروه ۲": names[j],
                        "اختلاف میانگین": round(diff, 3), "sig": None, "معنادار": "نامشخص"})
            continue
        q = abs(diff) / se * (2 ** 0.5)
        p = float(np.asarray(psturng(q, k, df)).reshape(-1)[0])
        rows.append({"گروه ۱": names[i], "گروه ۲": names[j],
                    "اختلاف میانگین": round(diff, 3),
                    "sig": round(p, 4), "معنادار": "بله" if p < 0.05 else "خیر"})
    return rows


def _posthoc_dunnett(groups, names, control_idx: int = 0) -> list:
    """تعقیبیِ دانت: هر گروه فقط با یک گروهِ کنترل مقایسه می‌شود (نه همه با همه) —
    مناسبِ طرح‌هایی که یک گروهِ شاهد/کنترل مشخص دارند."""
    from scipy import stats as sstats
    control = groups[control_idx]
    others = [g for i, g in enumerate(groups) if i != control_idx]
    other_names = [n for i, n in enumerate(names) if i != control_idx]
    if len(others) < 1:
        return []
    res = sstats.dunnett(*others, control=control)
    rows = []
    for name, stat, p in zip(other_names, res.statistic, res.pvalue):
        rows.append({"گروه": name, "کنترل": names[control_idx],
                    "آماره": round(float(stat), 3), "sig": round(float(p), 4),
                    "معنادار": "بله" if p < 0.05 else "خیر"})
    return rows


def anova(path: str, dependent: str, factor: str, factor2: str = None,
          posthoc: bool = True, posthoc_method: str = "tukey",
          control_group: str = None) -> dict:
    """تحلیل واریانس یک‌راهه یا دوراهه، با آزمون لِوین، اندازه‌ی اثر و آزمون تعقیبی.

    اگر factor2 داده شود، ANOVA دوراهه با اثر تعاملی اجرا می‌شود.
    posthoc_method: tukey (پیش‌فرض) / bonferroni / games_howell (واریانس نابرابر) /
    dunnett (مقایسه با یک گروهِ کنترل — control_group را هم بده).
    """
    import pandas as pd
    import numpy as np
    from scipy import stats
    df = _load_dataframe(path)
    if dependent not in df.columns:
        return {"error": f"متغیر وابسته «{dependent}» در داده نیست"}
    df[dependent] = pd.to_numeric(df[dependent], errors="coerce")

    # ---------- دوراهه ----------
    if factor2:
        try:
            import statsmodels.api as sm
            from statsmodels.formula.api import ols
        except ImportError:
            return {"error": "برای ANOVA دوراهه نصب statsmodels لازم است"}
        sub = df[[dependent, factor, factor2]].dropna()
        if len(sub) < 6:
            return {"error": "تعداد مشاهده‌های کامل برای ANOVA دوراهه کافی نیست"}
        sub = sub.rename(columns={dependent: "_y", factor: "_a", factor2: "_b"})
        model = ols("_y ~ C(_a) + C(_b) + C(_a):C(_b)", data=sub).fit()
        table = sm.stats.anova_lm(model, typ=2)
        ss_resid = float(table.loc["Residual", "sum_sq"])
        rows = []
        label = {"C(_a)": factor, "C(_b)": factor2, "C(_a):C(_b)": f"{factor} × {factor2}"}
        for src in table.index:
            if src == "Residual":
                continue
            ss = float(table.loc[src, "sum_sq"])
            rows.append({
                "منبع": label.get(src, src),
                "مجموع مجذورات": round(ss, 3),
                "df": int(table.loc[src, "df"]),
                "F": round(float(table.loc[src, "F"]), 3),
                "sig": round(float(table.loc[src, "PR(>F)"]), 4),
                "اتای مجذور تفکیکی": round(ss / (ss + ss_resid), 3) if (ss + ss_resid) else None,
                "معنادار": "بله" if float(table.loc[src, "PR(>F)"]) < 0.05 else "خیر",
            })
        return {"software": "معادل خروجی SPSS (Two-Way ANOVA)",
                "نوع": "دوراهه با اثر تعاملی", "اثرها": rows,
                "R2": round(float(model.rsquared), 3), "n": int(len(sub))}

    # ---------- یک‌راهه ----------
    if factor not in df.columns:
        return {"error": f"متغیر گروه‌بندی «{factor}» در داده نیست"}
    sub = df[[dependent, factor]].dropna()
    groups, names = [], []
    for name, g in sub.groupby(factor):
        vals = g[dependent].dropna().values
        if len(vals) > 0:
            groups.append(vals); names.append(str(name))
    if len(groups) < 2:
        return {"error": "برای تحلیل واریانس دست‌کم دو گروه لازم است"}

    f, p = stats.f_oneway(*groups)
    grand = np.concatenate(groups)
    ss_between = sum(len(g) * (g.mean() - grand.mean()) ** 2 for g in groups)
    ss_total = ((grand - grand.mean()) ** 2).sum()
    eta2 = float(ss_between / ss_total) if ss_total else None

    out = {
        "software": "معادل خروجی SPSS (One-Way ANOVA)",
        "نوع": "یک‌راهه",
        "f": round(float(f), 3), "sig": round(float(p), 4),
        "df_بین": len(groups) - 1, "df_درون": int(len(grand) - len(groups)),
        "groups": len(groups), "n": int(len(grand)),
        "اتای مجذور": round(eta2, 3) if eta2 is not None else None,
        "اندازه اثر": ("بزرگ" if eta2 and eta2 >= 0.14 else
                       "متوسط" if eta2 and eta2 >= 0.06 else "کوچک"),
        "آمار توصیفی": [{"گروه": n, "میانگین": round(float(g.mean()), 3),
                          "انحراف معیار": round(float(g.std(ddof=1)), 3) if len(g) > 1 else None,
                          "n": int(len(g))} for n, g in zip(names, groups)],
        "معنادار": "بله" if p < 0.05 else "خیر",
    }
    # آزمون لِوین: برابری واریانس‌ها (پیش‌فرض ANOVA)
    try:
        lev_f, lev_p = stats.levene(*groups)
        out["لِوین"] = {"F": round(float(lev_f), 3), "sig": round(float(lev_p), 4),
                        "برابری واریانس": "برقرار" if lev_p >= 0.05 else "نقض شده"}
        if lev_p < 0.05:
            out["هشدار"] = ("فرض همگنی واریانس‌ها نقض شده است؛ استفاده از آزمون ولچ یا "
                            "کروسکال-والیس توصیه می‌شود.")
    except Exception:
        pass
    # تعقیبی: کدام جفت گروه با هم تفاوت دارند
    if posthoc and len(groups) > 2:
        method = (posthoc_method or "tukey").lower()
        label = {"tukey": "تعقیبی توکی", "bonferroni": "تعقیبی بونفرونی",
                 "games_howell": "تعقیبی گیمز-هاول", "dunnett": "تعقیبی دانت"}.get(method, "تعقیبی توکی")
        try:
            if method == "bonferroni":
                out[label] = _posthoc_bonferroni(sub, dependent, factor, groups, names)
            elif method == "games_howell":
                out[label] = _posthoc_games_howell(groups, names)
            elif method == "dunnett":
                ctrl_idx = names.index(str(control_group)) if control_group in names else 0
                out[label] = _posthoc_dunnett(groups, names, ctrl_idx)
                out["گروه_کنترل"] = names[ctrl_idx]
            else:
                from statsmodels.stats.multicomp import pairwise_tukeyhsd
                res = pairwise_tukeyhsd(sub[dependent].values, sub[factor].astype(str).values)
                out[label] = [
                    {"گروه ۱": str(r[0]), "گروه ۲": str(r[1]),
                     "اختلاف میانگین": round(float(r[2]), 3),
                     "sig": round(float(r[3]), 4),
                     "معنادار": "بله" if float(r[3]) < 0.05 else "خیر"}
                    for r in res._results_table.data[1:]
                ]
        except Exception:
            pass
    return out


def manova(path: str, dependents, factor: str) -> dict:
    """تحلیل واریانس چندمتغیره — وقتی چند متغیر وابسته با هم بررسی می‌شوند
    (نه یکی‌یکی با چند ANOVA جدا). معادل Analyze ▸ General Linear Model ▸ Multivariate در SPSS."""
    import pandas as pd
    from statsmodels.multivariate.manova import MANOVA
    df = _load_dataframe(path)
    deps = [c for c in dependents if c in df.columns]
    if len(deps) < 2:
        return {"error": "MANOVA به دست‌کم دو متغیر وابسته نیاز دارد"}
    if factor not in df.columns:
        return {"error": f"متغیر گروه‌بندی «{factor}» در داده نیست"}
    sub = df[deps + [factor]].copy()
    for c in deps:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
    sub = sub.dropna()
    if sub[factor].nunique() < 2:
        return {"error": "برای MANOVA دست‌کم دو گروه لازم است"}
    if len(sub) <= len(deps) + sub[factor].nunique():
        return {"error": "تعداد مشاهده‌ها برای این تعداد متغیر وابسته کافی نیست"}

    formula = " + ".join(f"Q('{c}')" for c in deps) + f" ~ C(Q('{factor}'))"
    fit = MANOVA.from_formula(formula, data=sub)
    res = fit.mv_test()
    key = [k for k in res.results if k != "Intercept"][0]
    stats = res.results[key]["stat"]
    rows = []
    for name in stats.index:
        rows.append({
            "آزمون": name,
            "مقدار": round(float(stats.loc[name, "Value"]), 4),
            "F": round(float(stats.loc[name, "F Value"]), 3),
            "df صورت": round(float(stats.loc[name, "Num DF"]), 2),
            "df مخرج": round(float(stats.loc[name, "Den DF"]), 2),
            "sig": round(float(stats.loc[name, "Pr > F"]), 4),
            "معنادار": "بله" if float(stats.loc[name, "Pr > F"]) < 0.05 else "خیر",
        })
    return {
        "software": "معادل خروجی SPSS (MANOVA — Multivariate Tests)",
        "متغیرهای وابسته": deps, "عامل": factor, "n": int(len(sub)),
        "آزمون‌های چندمتغیره": rows,
        "معنادار": "بله" if any(r["معنادار"] == "بله" for r in rows) else "خیر",
    }


def repeated_measures_anova(path: str, cols, subject: str = None) -> dict:
    """تحلیل واریانس با اندازه‌گیری تکراری — برای طرح‌های پیش‌آزمون/پس‌آزمون/پیگیری
    که همان افراد چند بار سنجیده شده‌اند. معادل Repeated Measures در SPSS."""
    import pandas as pd
    from statsmodels.stats.anova import AnovaRM
    df = _load_dataframe(path)
    use = [c for c in (cols or []) if c in df.columns]
    if len(use) < 2:
        return {"error": "اندازه‌گیری تکراری به دست‌کم دو سنجش (دو ستون) نیاز دارد"}
    sub = df[use].apply(pd.to_numeric, errors="coerce").dropna().reset_index(drop=True)
    if len(sub) < 3:
        return {"error": "تعداد آزمودنی‌های کامل کافی نیست"}
    sub["_subject"] = sub.index
    long = sub.melt(id_vars="_subject", value_vars=use, var_name="_time", value_name="_y")
    res = AnovaRM(long, depvar="_y", subject="_subject", within=["_time"]).fit()
    t = res.anova_table
    row = t.iloc[0]
    return {
        "software": "معادل خروجی SPSS (Repeated Measures ANOVA)",
        "سنجش‌ها": use, "n": int(len(sub)),
        "F": round(float(row["F Value"]), 3),
        "df صورت": round(float(row["Num DF"]), 2),
        "df مخرج": round(float(row["Den DF"]), 2),
        "sig": round(float(row["Pr > F"]), 4),
        "میانگین‌ها": {c: round(float(sub[c].mean()), 3) for c in use},
        "معنادار": "بله" if float(row["Pr > F"]) < 0.05 else "خیر",
    }


def frequencies(path: str, cols=None, max_levels: int = 30) -> dict:
    """جدول فراوانی و درصد — معادل Analyze ▸ Descriptive Statistics ▸ Frequencies در SPSS."""
    import pandas as pd
    df = _load_dataframe(path)
    if cols:
        use = [c for c in cols if c in df.columns]
    else:
        # ستون‌هایی که تعداد مقدارهای یکتایشان کم است، طبقه‌ای‌اند
        use = [c for c in df.columns if df[c].nunique(dropna=True) <= max_levels]
    if not use:
        return {"error": "ستون طبقه‌ای مناسبی پیدا نشد (همه‌ی ستون‌ها مقدارهای یکتای زیادی دارند)"}
    out = {"software": "معادل خروجی SPSS (Frequencies)", "tables": {}}
    for c in use:
        s = df[c].dropna()
        if s.empty:
            continue
        vc = s.value_counts().sort_index()
        total = int(vc.sum())
        cum = 0
        rows = []
        for val, cnt in vc.items():
            cum += int(cnt)
            rows.append({
                "مقدار": str(val),
                "فراوانی": int(cnt),
                "درصد": round(100 * cnt / total, 1),
                "درصد تجمعی": round(100 * cum / total, 1),
            })
        out["tables"][str(c)] = {
            "rows": rows, "n": total,
            "گمشده": int(df[c].isna().sum()),
            "مد": str(s.mode().iloc[0]) if not s.mode().empty else None,
        }
    return out


def crosstab(path: str, row: str, col: str) -> dict:
    """جدول توافقی + کای‌دو + Cramér's V — معادل Crosstabs در SPSS."""
    import pandas as pd
    import numpy as np
    from scipy import stats
    df = _load_dataframe(path)
    for c in (row, col):
        if c not in df.columns:
            return {"error": f"ستون «{c}» در داده نیست"}
    tab = pd.crosstab(df[row], df[col])
    if tab.size == 0 or tab.shape[0] < 2 or tab.shape[1] < 2:
        return {"error": "برای جدول توافقی، هر دو متغیر باید دست‌کم دو سطح داشته باشند"}
    chi2, p, dof, expected = stats.chi2_contingency(tab)
    n = int(tab.values.sum())
    min_dim = min(tab.shape) - 1
    cramer = float(np.sqrt(chi2 / (n * min_dim))) if n and min_dim else None
    # فرض کای‌دو: کمتر از ۲۰٪ خانه‌ها فراوانی مورد انتظار زیر ۵
    low = int((expected < 5).sum())
    return {
        "software": "معادل خروجی SPSS (Crosstabs — Chi-Square)",
        "table": {str(i): {str(c2): int(v) for c2, v in r.items()} for i, r in tab.iterrows()},
        "chi2": round(float(chi2), 3), "df": int(dof), "sig": round(float(p), 4),
        "cramers_v": round(cramer, 3) if cramer is not None else None,
        "n": n,
        "خانه‌های_کم‌فراوانی": low,
        "هشدار": ("بیش از ۲۰٪ خانه‌ها فراوانی مورد انتظار کمتر از ۵ دارند؛ نتیجه‌ی کای‌دو "
                  "محتاطانه تفسیر شود." if low > 0.2 * expected.size else None),
        "معنادار": "بله" if p < 0.05 else "خیر",
    }


def nonparametric(path: str, kind: str, col: str = None, group: str = None,
                  cols=None, value2: str = None) -> dict:
    """آزمون‌های ناپارامتری SPSS: من‌ویتنی، ویلکاکسون، کروسکال‌والیس، فریدمن.

    وقتی داده نرمال نیست، این‌ها جایگزین t و ANOVA می‌شوند.
    """
    import pandas as pd
    from scipy import stats
    df = _load_dataframe(path)

    if kind in ("mannwhitney", "mann_whitney", "u"):
        if not col or not group:
            return {"error": "برای من‌ویتنی، ستون کمّی و ستون گروه لازم است"}
        levels = df[group].dropna().unique()[:2]
        if len(levels) < 2:
            return {"error": f"ستون «{group}» باید دو گروه داشته باشد"}
        a = pd.to_numeric(df[df[group] == levels[0]][col], errors="coerce").dropna()
        b = pd.to_numeric(df[df[group] == levels[1]][col], errors="coerce").dropna()
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        return {"software": "معادل خروجی SPSS (Mann-Whitney U)", "kind": "من‌ویتنی",
                "U": round(float(u), 3), "sig": round(float(p), 4),
                "گروه‌ها": [str(levels[0]), str(levels[1])],
                "میانه۱": round(float(a.median()), 3), "میانه۲": round(float(b.median()), 3),
                "n1": len(a), "n2": len(b), "معنادار": "بله" if p < 0.05 else "خیر"}

    if kind in ("wilcoxon", "signed_rank"):
        if not col or not value2:
            return {"error": "برای ویلکاکسون، دو ستون زوجی لازم است"}
        a = pd.to_numeric(df[col], errors="coerce")
        b = pd.to_numeric(df[value2], errors="coerce")
        pair = pd.concat([a, b], axis=1).dropna()
        if len(pair) < 3:
            return {"error": "تعداد جفت‌های معتبر کافی نیست"}
        w, p = stats.wilcoxon(pair.iloc[:, 0], pair.iloc[:, 1])
        return {"software": "معادل خروجی SPSS (Wilcoxon Signed-Rank)", "kind": "ویلکاکسون",
                "W": round(float(w), 3), "sig": round(float(p), 4), "n": len(pair),
                "معنادار": "بله" if p < 0.05 else "خیر"}

    if kind in ("kruskal", "kruskal_wallis"):
        if not col or not group:
            return {"error": "برای کروسکال-والیس، ستون کمّی و ستون گروه لازم است"}
        groups = [pd.to_numeric(g[col], errors="coerce").dropna()
                  for _, g in df.groupby(group)]
        groups = [g for g in groups if len(g) > 0]
        if len(groups) < 2:
            return {"error": "دست‌کم دو گروه لازم است"}
        h, p = stats.kruskal(*groups)
        return {"software": "معادل خروجی SPSS (Kruskal-Wallis H)", "kind": "کروسکال-والیس",
                "H": round(float(h), 3), "df": len(groups) - 1, "sig": round(float(p), 4),
                "تعداد_گروه": len(groups), "معنادار": "بله" if p < 0.05 else "خیر"}

    if kind == "friedman":
        use = [c for c in (cols or []) if c in df.columns]
        if len(use) < 3:
            return {"error": "آزمون فریدمن به دست‌کم سه سنجش تکراری (سه ستون) نیاز دارد"}
        sub = df[use].apply(pd.to_numeric, errors="coerce").dropna()
        if len(sub) < 3:
            return {"error": "تعداد سطرهای کامل کافی نیست"}
        chi2, p = stats.friedmanchisquare(*[sub[c] for c in use])
        return {"software": "معادل خروجی SPSS (Friedman Test)", "kind": "فریدمن",
                "chi2": round(float(chi2), 3), "df": len(use) - 1, "sig": round(float(p), 4),
                "میانگین_رتبه": {c: round(float(sub[c].rank(axis=0).mean()), 2) for c in use},
                "n": len(sub), "معنادار": "بله" if p < 0.05 else "خیر"}

    return {"error": "نوع آزمون ناپارامتری نامعتبر است "
                     "(mannwhitney / wilcoxon / kruskal / friedman)"}


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
    "frequencies": frequencies,
    "crosstab": crosstab,
    "nonparametric": nonparametric,
    "manova": manova,
    "repeated_measures_anova": repeated_measures_anova,
}


def _all_functions():
    """توابع این ماژول به‌علاوه‌ی موتور سری‌زمانی/تابلویی و موتور PLS."""
    reg = dict(FUNCTIONS)
    for mod in ("ts_engine", "pls_engine"):
        try:
            m = __import__(mod)
            reg.update(getattr(m, "FUNCTIONS", {}))
        except Exception:
            pass
    return reg


def available_analyses():
    """نام همه‌ی تحلیل‌های قابل اجرا — برای اعتبارسنجی نقشه‌ی تحلیل خودکار."""
    return sorted(_all_functions().keys())


def run(func_name: str, path: str, **kwargs) -> dict:
    """اجرای امن یک تحلیل و بازگرداندن نتیجه یا خطا"""
    try:
        fn = _all_functions().get(func_name)
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
