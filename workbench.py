# -*- coding: utf-8 -*-
"""
workbench.py — میزکار نرم‌افزارهای آماری آنتانو (SPSS / EViews / SmartPLS)

هر میزکار یک صفحه‌ی وب است که ظاهر و منوهای همان نرم‌افزار ویندوزی را دارد:
کاربر داده را وارد یا آپلود می‌کند (یا از داده‌ی پیوست‌شده به مقاله برمی‌دارد)،
از منوها تحلیل را انتخاب می‌کند و خروجی را به همان سبک نرم‌افزار اصلی می‌بیند.
محاسبه‌ها همگی با موتورهای واقعی موجود انجام می‌شوند
(stats_engine / ts_engine / pls_engine) — این‌جا فقط پیکربندی منوها،
مشخصات پنجره‌های گفت‌وگو (dialog) و کمکی‌های شبکه‌ی داده است.

قالب فیلدهای پنجره‌ی هر تحلیل (برای ساخت فرم در مرورگر):
  type: col (یک ستون) | cols (چند ستون) | select | number | text | check
  filter: numeric | categorical | all   ← فقط برای col/cols
"""
import os
import re


# ---------------------------------------------------------------- فیلدسازها

def _col(key, label, filter="all", required=True, hint=""):
    return {"key": key, "label": label, "type": "col", "filter": filter,
            "required": required, "hint": hint}


def _cols(key, label, filter="all", required=True, hint=""):
    return {"key": key, "label": label, "type": "cols", "filter": filter,
            "required": required, "hint": hint}


def _sel(key, label, options, default=None):
    return {"key": key, "label": label, "type": "select", "options": options,
            "default": default if default is not None else options[0][0]}


def _num(key, label, default=None, required=False):
    return {"key": key, "label": label, "type": "number", "default": default,
            "required": required}


# ---------------------------------------------------------------- SPSS

_POSTHOC = _sel("posthoc_method", "آزمون تعقیبی (Post Hoc)", [
    ["tukey", "Tukey HSD"],
    ["bonferroni", "Bonferroni"],
    ["games_howell", "Games-Howell (واریانس نابرابر)"],
    ["dunnett", "Dunnett (مقایسه با گروه کنترل)"],
])

SPSS = {
    "id": "spss",
    "name": "ANTANU SPSS Statistics",
    "tagline": "ویرایشگر داده — به سبک IBM SPSS Statistics",
    "window": "Untitled1 [DataSet0] - ANTANU SPSS Statistics Data Editor",
    "menus": [
        {"label": "File", "fa": "پرونده", "items": [
            {"action": "new", "label": "New Data", "fa": "داده‌ی جدید (صفحه‌ی خالی)"},
            {"action": "open", "label": "Open Data…", "fa": "باز کردن داده‌های من"},
            {"action": "import", "label": "Import Data…", "fa": "آپلود فایل (Excel/CSV/SPSS/…)"},
            {"action": "save", "label": "Save", "fa": "ذخیره‌ی تغییرها"},
            {"action": "export", "label": "Export CSV", "fa": "دانلود داده (CSV)"},
        ]},
        {"label": "Edit", "fa": "ویرایش", "items": [
            {"action": "addrow", "label": "Insert Case", "fa": "افزودن سطر (Case)"},
            {"action": "addcol", "label": "Insert Variable", "fa": "افزودن متغیر (ستون)"},
            {"action": "delrow", "label": "Delete Case", "fa": "حذف سطر انتخاب‌شده"},
            {"action": "delcol", "label": "Delete Variable", "fa": "حذف ستون انتخاب‌شده"},
        ]},
        {"label": "Analyze", "fa": "تحلیل", "items": [
            {"label": "Descriptive Statistics", "fa": "آمار توصیفی", "children": [
                {"analysis": "frequencies", "label": "Frequencies…", "fa": "فراوانی‌ها",
                 "fields": [_cols("cols", "متغیرها", "all", required=False,
                                  hint="خالی = همه‌ی متغیرهای طبقه‌ای")]},
                {"analysis": "overview", "label": "Descriptives…", "fa": "شاخص‌های توصیفی", "fields": []},
                {"analysis": "assumptions", "label": "Explore… (Normality)", "fa": "بررسی نرمال بودن و پیش‌فرض‌ها",
                 "fields": [_cols("cols", "متغیرها", "numeric", required=False, hint="خالی = همه‌ی متغیرهای عددی")]},
                {"analysis": "crosstab", "label": "Crosstabs… (Chi-Square)", "fa": "جدول توافقی و خی‌دو",
                 "fields": [_col("row", "متغیر سطر", "all"), _col("col", "متغیر ستون", "all")]},
            ]},
            {"label": "Compare Means", "fa": "مقایسه‌ی میانگین‌ها", "children": [
                {"analysis": "ttest", "label": "One-Sample T Test…", "fa": "t تک‌نمونه‌ای",
                 "fixed": {"kind": "one_sample"},
                 "fields": [_col("col", "متغیر آزمون", "numeric"),
                            _num("popmean", "مقدار آزمون (Test Value)", 3, required=True)]},
                {"analysis": "ttest", "label": "Independent-Samples T Test…", "fa": "t مستقل (دو گروه)",
                 "fixed": {"kind": "independent"},
                 "fields": [_col("col", "متغیر آزمون", "numeric"),
                            _col("group", "متغیر گروه‌بندی", "all")]},
                {"analysis": "ttest", "label": "Paired-Samples T Test…", "fa": "t زوجی",
                 "fixed": {"kind": "paired"},
                 "fields": [_col("col", "متغیر اول", "numeric"),
                            _col("value2", "متغیر دوم", "numeric")]},
                {"analysis": "anova", "label": "One-Way ANOVA…", "fa": "تحلیل واریانس یک‌راهه",
                 "fields": [_col("dependent", "متغیر وابسته", "numeric"),
                            _col("factor", "عامل (Factor)", "all"), _POSTHOC]},
            ]},
            {"label": "General Linear Model", "fa": "مدل خطی عمومی", "children": [
                {"analysis": "anova", "label": "Univariate… (Two-Way)", "fa": "تحلیل واریانس دوراهه",
                 "fields": [_col("dependent", "متغیر وابسته", "numeric"),
                            _col("factor", "عامل اول", "all"),
                            _col("factor2", "عامل دوم", "all")]},
                {"analysis": "manova", "label": "Multivariate… (MANOVA)", "fa": "تحلیل واریانس چندمتغیره",
                 "fields": [_cols("dependents", "متغیرهای وابسته (دست‌کم دو تا)", "numeric"),
                            _col("factor", "عامل (Factor)", "all")]},
                {"analysis": "repeated_measures_anova", "label": "Repeated Measures…", "fa": "اندازه‌گیری مکرر",
                 "fields": [_cols("cols", "سنجش‌ها به ترتیب زمان", "numeric",
                                  hint="مثل پیش‌آزمون، پس‌آزمون، پیگیری")]},
            ]},
            {"label": "Correlate", "fa": "همبستگی", "children": [
                {"analysis": "correlation", "label": "Bivariate…", "fa": "همبستگی دومتغیره",
                 "fields": [_cols("cols", "متغیرها", "numeric", required=False, hint="خالی = همه"),
                            _sel("method", "ضریب", [["pearson", "Pearson"],
                                                    ["spearman", "Spearman"],
                                                    ["kendall", "Kendall's tau-b"]])]},
            ]},
            {"label": "Regression", "fa": "رگرسیون", "children": [
                {"analysis": "regression", "label": "Linear…", "fa": "رگرسیون خطی",
                 "fixed": {"kind": "linear"},
                 "fields": [_col("dependent", "متغیر وابسته", "numeric"),
                            _cols("independents", "متغیرهای مستقل", "numeric")]},
                {"analysis": "regression", "label": "Binary Logistic…", "fa": "لجستیک دودویی",
                 "fixed": {"kind": "logistic"},
                 "fields": [_col("dependent", "متغیر وابسته (۰/۱)", "all"),
                            _cols("independents", "متغیرهای مستقل", "numeric")]},
                {"analysis": "regression", "label": "Ordinal…", "fa": "رگرسیون ترتیبی (لیکرت)",
                 "fixed": {"kind": "ordinal"},
                 "fields": [_col("dependent", "متغیر وابسته‌ی رتبه‌ای", "all"),
                            _cols("independents", "متغیرهای مستقل", "numeric")]},
                {"analysis": "regression", "label": "Multinomial Logistic…", "fa": "لجستیک چندجمله‌ای",
                 "fixed": {"kind": "multinomial"},
                 "fields": [_col("dependent", "متغیر وابسته‌ی طبقه‌ای", "all"),
                            _cols("independents", "متغیرهای مستقل", "numeric")]},
                {"analysis": "regression", "label": "Poisson / Negative Binomial…", "fa": "رگرسیون شمارشی",
                 "fields": [_col("dependent", "متغیر شمارشی", "numeric"),
                            _cols("independents", "متغیرهای مستقل", "numeric"),
                            _sel("kind", "نوع مدل", [["poisson", "Poisson"],
                                                     ["negbinom", "Negative Binomial"]])]},
            ]},
            {"label": "Dimension Reduction", "fa": "کاهش بُعد", "children": [
                {"analysis": "factor_analysis", "label": "Factor… (EFA + KMO)", "fa": "تحلیل عاملی اکتشافی",
                 "fields": [_cols("cols", "گویه‌ها", "numeric", required=False, hint="خالی = همه‌ی عددی‌ها"),
                            _num("n_factors", "تعداد عامل (خالی = خودکار)")]},
            ]},
            {"label": "Scale", "fa": "مقیاس", "children": [
                {"analysis": "reliability", "label": "Reliability Analysis… (Cronbach's α)", "fa": "پایایی (آلفای کرونباخ)",
                 "fields": [_cols("cols", "گویه‌های مقیاس", "numeric", required=False, hint="خالی = همه")]},
            ]},
            {"label": "Nonparametric Tests", "fa": "آزمون‌های ناپارامتری", "children": [
                {"analysis": "nonparametric", "label": "Mann-Whitney U…", "fa": "من‌ویتنی (دو گروه مستقل)",
                 "fixed": {"kind": "mannwhitney"},
                 "fields": [_col("col", "متغیر کمّی", "numeric"), _col("group", "متغیر گروه‌بندی", "all")]},
                {"analysis": "nonparametric", "label": "Kruskal-Wallis H…", "fa": "کروسکال-والیس (چند گروه)",
                 "fixed": {"kind": "kruskal"},
                 "fields": [_col("col", "متغیر کمّی", "numeric"), _col("group", "متغیر گروه‌بندی", "all")]},
                {"analysis": "nonparametric", "label": "Wilcoxon Signed-Rank…", "fa": "ویلکاکسون (دو سنجش زوجی)",
                 "fixed": {"kind": "wilcoxon"},
                 "fields": [_col("col", "سنجش اول", "numeric"), _col("value2", "سنجش دوم", "numeric")]},
                {"analysis": "nonparametric", "label": "Friedman…", "fa": "فریدمن (چند سنجش تکراری)",
                 "fixed": {"kind": "friedman"},
                 "fields": [_cols("cols", "سنجش‌های تکراری", "numeric")]},
            ]},
            {"label": "Mediation (PROCESS)", "fa": "میانجی‌گری", "children": [
                {"analysis": "mediation", "label": "Simple Mediation (Model 4)…", "fa": "تحلیل میانجی با بوت‌استرپ",
                 "fields": [_col("x", "متغیر مستقل (X)", "numeric"),
                            _col("m", "متغیر میانجی (M)", "numeric"),
                            _col("y", "متغیر وابسته (Y)", "numeric")]},
            ]},
        ]},
        {"label": "Graphs", "fa": "نمودار", "items": [
            {"analysis": "overview", "label": "Histograms", "fa": "هیستوگرام متغیرها", "fields": []},
            {"analysis": "correlation", "label": "Correlation Heatmap", "fa": "نقشه‌ی حرارتی همبستگی",
             "fields": [_sel("method", "ضریب", [["pearson", "Pearson"], ["spearman", "Spearman"]])]},
        ]},
    ],
}

# ---------------------------------------------------------------- EViews

_UR_TYPE = _sel("regression", "اجزای قطعی (Deterministics)", [
    ["c", "Intercept (عرض از مبدأ)"],
    ["ct", "Trend and intercept (روند و عرض از مبدأ)"],
    ["n", "None (هیچ‌کدام)"],
])

EVIEWS = {
    "id": "eviews",
    "name": "ANTANU EViews",
    "tagline": "اقتصادسنجی و سری‌زمانی — به سبک EViews",
    "window": "Workfile: UNTITLED - ANTANU EViews",
    "menus": [
        {"label": "File", "fa": "پرونده", "items": [
            {"action": "new", "label": "New Workfile", "fa": "کاربرگ جدید (خالی)"},
            {"action": "open", "label": "Open Workfile…", "fa": "باز کردن داده‌های من"},
            {"action": "import", "label": "Import…", "fa": "آپلود فایل (Excel/CSV/…)"},
            {"action": "save", "label": "Save", "fa": "ذخیره‌ی تغییرها"},
            {"action": "export", "label": "Export CSV", "fa": "دانلود داده (CSV)"},
        ]},
        {"label": "Edit", "fa": "ویرایش", "items": [
            {"action": "addrow", "label": "Add Observation", "fa": "افزودن مشاهده (سطر)"},
            {"action": "addcol", "label": "Add Series", "fa": "افزودن سری (ستون)"},
            {"action": "delrow", "label": "Delete Observation", "fa": "حذف سطر انتخاب‌شده"},
            {"action": "delcol", "label": "Delete Series", "fa": "حذف سری انتخاب‌شده"},
        ]},
        {"label": "Quick", "fa": "سریع", "items": [
            {"analysis": "overview", "label": "Series Statistics", "fa": "آماره‌های توصیفی سری‌ها", "fields": []},
            {"analysis": "correlation", "label": "Group Statistics → Correlations", "fa": "ماتریس همبستگی",
             "fields": [_cols("cols", "سری‌ها", "numeric", required=False, hint="خالی = همه")]},
            {"analysis": "regression", "label": "Estimate Equation… (LS)", "fa": "برآورد معادله (حداقل مربعات)",
             "fixed": {"kind": "linear"},
             "fields": [_col("dependent", "متغیر وابسته", "numeric"),
                        _cols("independents", "متغیرهای توضیحی", "numeric")]},
        ]},
        {"label": "Unit Root / Coint.", "fa": "ریشه واحد و هم‌جمعی", "items": [
            {"analysis": "unit_root", "label": "Unit Root Test… (ADF / PP / KPSS)", "fa": "آزمون ریشه‌ی واحد و مانایی",
             "fields": [_cols("cols", "سری‌ها", "numeric", required=False, hint="خالی = همه"),
                        _UR_TYPE,
                        _num("max_diff", "بیشینه‌ی تفاضل‌گیری", 2)]},
            {"analysis": "cointegration", "label": "Johansen Cointegration Test…", "fa": "هم‌جمعی یوهانسن",
             "fields": [_cols("cols", "سری‌ها", "numeric", required=False, hint="خالی = همه"),
                        _num("k_ar_diff", "وقفه‌ی تفاضلی (Lag)", 1)]},
            {"analysis": "granger", "label": "Granger Causality…", "fa": "علیت گرنجر",
             "fields": [_col("cause", "متغیر علت (خالی = همه‌ی جفت‌ها)", "numeric", required=False),
                        _col("effect", "متغیر معلول", "numeric", required=False),
                        _num("maxlag", "بیشینه‌ی وقفه", 4)]},
        ]},
        {"label": "Estimate", "fa": "برآورد مدل", "items": [
            {"analysis": "arima", "label": "ARIMA…", "fa": "مدل ARIMA (با انتخاب خودکار مرتبه)",
             "fields": [_col("col", "سری‌زمانی", "numeric", required=False, hint="خالی = اولین سری عددی"),
                        _num("forecast", "تعداد دوره‌ی پیش‌بینی", 6)]},
            {"analysis": "var", "label": "VAR…", "fa": "خودرگرسیون برداری",
             "fields": [_cols("cols", "سری‌ها", "numeric", required=False, hint="خالی = همه"),
                        _num("maxlags", "بیشینه‌ی وقفه", 5)]},
            {"analysis": "vecm", "label": "VECM…", "fa": "تصحیح خطای برداری",
             "fields": [_cols("cols", "سری‌ها", "numeric", required=False, hint="خالی = همه"),
                        _num("k_ar_diff", "وقفه‌ی تفاضلی", 1),
                        _num("coint_rank", "رتبه‌ی هم‌جمعی", 1)]},
            {"analysis": "garch", "label": "ARCH / GARCH…", "fa": "مدل نوسان GARCH",
             "fields": [_col("col", "سری بازده", "numeric", required=False, hint="خالی = اولین سری عددی"),
                        _num("p", "مرتبه‌ی GARCH (p)", 1), _num("q", "مرتبه‌ی ARCH (q)", 1)]},
            {"analysis": "panel", "label": "Panel Estimation… (FE/RE + Hausman)", "fa": "داده‌ی تابلویی (پانل)",
             "fields": [_col("dependent", "متغیر وابسته (خالی = خودکار)", "numeric", required=False),
                        _cols("independents", "متغیرهای توضیحی", "numeric", required=False,
                              hint="خالی = بقیه‌ی سری‌های عددی"),
                        _col("entity", "ستون شناسه‌ی مقطع (خالی = خودکار)", "all", required=False),
                        _col("time", "ستون زمان (خالی = خودکار)", "all", required=False)]},
            {"analysis": "seasonal_decompose", "label": "Seasonal Decomposition…", "fa": "تجزیه‌ی فصلی",
             "fields": [_col("col", "سری‌زمانی", "numeric", required=False, hint="خالی = اولین سری عددی"),
                        _num("period", "دوره‌ی فصلی (۱۲=ماهانه، ۴=فصلی؛ خالی=خودکار)")]},
        ]},
        {"label": "Residual Diagnostics", "fa": "تشخیص باقیمانده‌ها", "items": [
            {"analysis": "ts_diagnostics", "label": "Full Diagnostics (BG/White/ARCH/Chow/CUSUM…)", "fa": "آزمون‌های کامل تشخیصی",
             "fields": [_col("dependent", "متغیر وابسته", "numeric"),
                        _cols("independents", "متغیرهای توضیحی", "numeric", required=False,
                              hint="خالی = بقیه‌ی سری‌های عددی")]},
        ]},
    ],
}

# ---------------------------------------------------------------- SmartPLS

SMARTPLS = {
    "id": "smartpls",
    "name": "ANTANU SmartPLS",
    "tagline": "مدل‌سازی معادلات ساختاری — به سبک SmartPLS",
    "window": "Project: ANTANU - PLS-SEM Model",
    # منوی SmartPLS ساده‌تر است؛ بخش اصلی، بومِ مدل است که در صفحه ساخته می‌شود.
    "menus": [
        {"label": "File", "fa": "پرونده", "items": [
            {"action": "open", "label": "Open Data…", "fa": "باز کردن داده‌های من"},
            {"action": "import", "label": "Import Data…", "fa": "آپلود فایل (Excel/CSV/…)"},
        ]},
        {"label": "Calculate", "fa": "محاسبه", "items": [
            {"action": "pls_algorithm", "label": "PLS-SEM Algorithm", "fa": "الگوریتم PLS (بدون بوت‌استرپ)"},
            {"action": "bootstrapping", "label": "Bootstrapping", "fa": "بوت‌استرپ (t و p مسیرها)"},
            {"action": "cfa", "label": "Confirmatory Factor Analysis (CB-SEM)", "fa": "تحلیل عاملی تأییدی"},
        ]},
    ],
}

SOFTWARES = {"spss": SPSS, "eviews": EVIEWS, "smartpls": SMARTPLS}

# تحلیل‌هایی که هر میزکار اجازه‌ی اجرایشان را دارد (برای اعتبارسنجی سمت سرور)
ALLOWED = {
    "spss": {"overview", "assumptions", "frequencies", "crosstab", "ttest", "anova",
             "manova", "repeated_measures_anova", "correlation", "regression",
             "factor_analysis", "reliability", "nonparametric", "mediation"},
    "eviews": {"overview", "correlation", "regression", "unit_root", "cointegration",
               "granger", "arima", "var", "vecm", "garch", "panel",
               "ts_diagnostics", "seasonal_decompose"},
    "smartpls": {"pls_sem", "sem_cfa", "reliability", "overview"},
}


# ---------------------------------------------------------------- شبکه‌ی داده

MAX_GRID_ROWS = 1000       # سقف نمایش در مرورگر
MAX_SAVE_ROWS = 20000      # سقف ذخیره از مرورگر
MAX_SAVE_COLS = 200

_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")


def load_grid(path: str, max_rows: int = MAX_GRID_ROWS) -> dict:
    """خواندن فایل داده و آماده‌سازی برای شبکه‌ی ویرایش (Data View / Variable View)."""
    import pandas as pd
    import stats_engine
    df = stats_engine._load_dataframe(path)
    total = int(len(df))
    truncated = total > max_rows
    view = df.head(max_rows)

    columns = []
    for c in df.columns:
        s = df[c]
        num = pd.to_numeric(s, errors="coerce")
        is_num = num.notna().sum() >= max(1, int(s.notna().sum() * 0.7))
        info = {
            "name": str(c),
            "type": "numeric" if is_num else "text",
            "missing": int(s.isna().sum()),
            "unique": int(s.nunique(dropna=True)),
        }
        if is_num and num.notna().any():
            info["mean"] = round(float(num.mean()), 3)
            info["std"] = round(float(num.std()), 3) if num.notna().sum() > 1 else 0.0
            info["min"] = round(float(num.min()), 3)
            info["max"] = round(float(num.max()), 3)
        columns.append(info)

    rows = []
    for _, r in view.iterrows():
        row = []
        for v in r:
            if v is None or (isinstance(v, float) and v != v):   # NaN
                row.append("")
            elif isinstance(v, float) and v == int(v):
                row.append(int(v))
            else:
                row.append(v if isinstance(v, (int, float)) else str(v))
        rows.append(row)

    return {"columns": columns, "rows": rows, "total_rows": total, "truncated": truncated}


def save_grid(path: str, columns, rows) -> dict:
    """ذخیره‌ی شبکه‌ی ویرایش‌شده به‌صورت CSV (با BOM تا اکسل فارسی را درست بخواند)."""
    import csv
    names = [str(c).strip() or f"var{i+1}" for i, c in enumerate(columns)]
    if not names:
        raise ValueError("دست‌کم یک ستون لازم است")
    if len(names) > MAX_SAVE_COLS:
        raise ValueError(f"بیشینه‌ی ستون‌ها {MAX_SAVE_COLS} است")
    if len(rows) > MAX_SAVE_ROWS:
        raise ValueError(f"بیشینه‌ی سطرها {MAX_SAVE_ROWS} است")
    # نام‌های تکراری ستون را یکتا کن تا pandas بعداً قاطی نکند
    seen = {}
    for i, n in enumerate(names):
        if n in seen:
            seen[n] += 1
            names[i] = f"{n}.{seen[n]}"
        else:
            seen[n] = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(names)
        for r in rows:
            cells = list(r)[:len(names)]
            cells += [""] * (len(names) - len(cells))
            w.writerow(["" if c is None else c for c in cells])
    return {"columns": len(names), "rows": len(rows)}
