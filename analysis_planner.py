# -*- coding: utf-8 -*-
"""
analysis_planner.py — «مغز خودکار» تحلیل آماری آنتانو.

کاربر فایل داده می‌دهد و به زبان ساده می‌گوید چه می‌خواهد؛ اینجا سه کار انجام می‌شود:

  ۱) شناسنامه‌ی داده  — نوع ستون‌ها، طیف لیکرت، سری‌زمانی یا تابلویی بودن، سازه‌های
     احتمالی (گویه‌هایی که با یک نام و شماره آمده‌اند: رضایت۱، رضایت۲، …)
  ۲) ساخت نقشه‌ی تحلیل — شناسنامه + درخواست کاربر به مدل داده می‌شود و مدل فهرست
     تحلیل‌ها و پارامترهایشان را به‌صورت JSON برمی‌گرداند.
  ۳) اعتبارسنجی سخت‌گیرانه — هر نام تحلیل و هر نام ستون در برابر داده و فهرست
     توابع بررسی می‌شود. چیزی که مدل از خودش ساخته باشد اجرا نمی‌شود.

اگر مدل در دسترس نباشد یا نقشه‌ی معتبری ندهد، یک نقشه‌ی پیش‌فرضِ منطقی بر پایه‌ی
ساختار داده ساخته می‌شود تا کاربر دست‌خالی نماند.
"""
import json
import re

import stats_engine


# ---------------- شناسنامه‌ی داده ----------------

_LIKERT_MAX = 11          # طیف لیکرت معمولاً ۵ یا ۷ درجه است


def profile(path: str) -> dict:
    """ساختار داده را می‌شناسد تا هم مدل و هم خودِ ما بدانیم چه چیزی در دست است."""
    import pandas as pd
    try:
        df = stats_engine._load_dataframe(path)
    except Exception as e:
        return {"error": f"خواندن فایل داده ممکن نشد: {e}"}
    if df is None or df.empty:
        return {"error": "فایل داده خالی است"}

    cols = []
    numeric, categorical, likert = [], [], []
    for c in df.columns:
        s = df[c]
        nun = int(s.nunique(dropna=True))
        num = pd.to_numeric(s, errors="coerce")
        is_num = float(num.notna().mean()) > 0.8
        info = {"نام": str(c), "یکتا": nun,
                "گمشده": round(float(s.isna().mean()) * 100, 1)}
        if is_num:
            info["نوع"] = "عددی"
            info["میانگین"] = round(float(num.mean()), 3) if num.notna().any() else None
            info["کمینه"] = round(float(num.min()), 3) if num.notna().any() else None
            info["بیشینه"] = round(float(num.max()), 3) if num.notna().any() else None
            numeric.append(str(c))
            vals = num.dropna()
            if (nun <= _LIKERT_MAX and len(vals) and
                    float(vals.min()) >= 1 and float(vals.max()) <= _LIKERT_MAX and
                    float((vals % 1 == 0).mean()) > 0.95):
                likert.append(str(c))
                info["نوع"] = "عددی (احتمالاً لیکرت)"
        else:
            info["نوع"] = "طبقه‌ای"
            info["سطوح"] = [str(v) for v in s.dropna().unique()[:8]]
            categorical.append(str(c))
        cols.append(info)

    out = {
        "تعداد سطر": int(len(df)),
        "تعداد ستون": int(df.shape[1]),
        "ستون‌ها": cols,
        "ستون‌های عددی": numeric,
        "ستون‌های طبقه‌ای": categorical,
        "ستون‌های لیکرت": likert,
    }
    # سری‌زمانی / تابلویی
    try:
        import ts_engine
        tcol = ts_engine.detect_time_column(df)
        ent, tim = ts_engine.detect_panel(df)
        out["ستون زمان"] = str(tcol) if tcol else None
        out["ساختار تابلویی"] = ({"شناسه": str(ent), "زمان": str(tim)}
                                  if ent and tim else None)
        out["سری‌زمانی است"] = bool(tcol) and not (ent and tim)
    except Exception:
        out["ستون زمان"] = None
        out["ساختار تابلویی"] = None
        out["سری‌زمانی است"] = False

    out["سازه‌های حدسی"] = guess_constructs(likert or numeric)
    return out


def guess_constructs(cols) -> dict:
    """گویه‌هایی که یک ریشه‌ی نامی مشترک و شماره دارند را یک سازه فرض می‌کند.

    مثال: رضایت۱، رضایت۲، رضایت۳ → سازه‌ی «رضایت».
    """
    groups = {}
    for c in cols:
        m = re.match(r"^(.*?)[\s_\-]*(\d+)$", str(c).strip())
        if not m:
            continue
        stem = m.group(1).strip(" _-")
        if not stem:
            continue
        groups.setdefault(stem, []).append(str(c))
    return {k: v for k, v in groups.items() if len(v) >= 2}


# ---------------- امضای تحلیل‌ها ----------------
# برای هر تحلیل: پارامترهای مجاز و اینکه کدام‌شان «نام ستون» است.
# هر چیزی خارج از این‌ها از نقشه‌ی مدل حذف می‌شود.

SPEC = {
    "overview":       {"args": {"": None}, "cols": [], "collists": []},
    "assumptions":    {"args": {"cols": list}, "cols": [], "collists": ["cols"]},
    "frequencies":    {"args": {"cols": list, "max_levels": int}, "cols": [], "collists": ["cols"]},
    "reliability":    {"args": {"cols": list}, "cols": [], "collists": ["cols"]},
    "correlation":    {"args": {"method": str, "cols": list}, "cols": [], "collists": ["cols"]},
    "crosstab":       {"args": {"row": str, "col": str}, "cols": ["row", "col"], "collists": []},
    "ttest":          {"args": {"kind": str, "col": str, "group": str, "value2": str,
                                 "popmean": float},
                       "cols": ["col", "group", "value2"], "collists": []},
    "anova":          {"args": {"dependent": str, "factor": str, "factor2": str,
                                 "posthoc": bool, "posthoc_method": str, "control_group": str},
                       "cols": ["dependent", "factor", "factor2", "control_group"], "collists": []},
    "manova":         {"args": {"dependents": list, "factor": str},
                       "cols": ["factor"], "collists": ["dependents"]},
    "repeated_measures_anova": {"args": {"cols": list},
                       "cols": [], "collists": ["cols"]},
    "nonparametric":  {"args": {"kind": str, "col": str, "group": str, "cols": list,
                                 "value2": str},
                       "cols": ["col", "group", "value2"], "collists": ["cols"]},
    "regression":     {"args": {"dependent": str, "independents": list, "kind": str},
                       "cols": ["dependent"], "collists": ["independents"]},
    "mediation":      {"args": {"x": str, "m": str, "y": str},
                       "cols": ["x", "m", "y"], "collists": []},
    "factor_analysis": {"args": {"cols": list, "n_factors": int},
                        "cols": [], "collists": ["cols"]},
    "sem_cfa":        {"args": {"model_spec": str, "factors": dict},
                       "cols": [], "collists": [], "factors": True},
    "pls_sem":        {"args": {"factors": dict, "structural": list, "bootstrap": int},
                       "cols": [], "collists": [], "factors": True, "structural": True},
    "unit_root":      {"args": {"cols": list, "regression": str, "max_diff": int},
                       "cols": [], "collists": ["cols"]},
    "cointegration":  {"args": {"cols": list, "det_order": int, "k_ar_diff": int},
                       "cols": [], "collists": ["cols"]},
    "granger":        {"args": {"cause": str, "effect": str, "cols": list, "maxlag": int},
                       "cols": ["cause", "effect"], "collists": ["cols"]},
    "arima":          {"args": {"col": str, "order": list, "max_p": int, "max_q": int,
                                 "forecast": int},
                       "cols": ["col"], "collists": []},
    "var_model":      {"args": {"cols": list, "maxlags": int, "irf_periods": int},
                       "cols": [], "collists": ["cols"]},
    "vecm":           {"args": {"cols": list, "k_ar_diff": int, "coint_rank": int},
                       "cols": [], "collists": ["cols"]},
    "garch":          {"args": {"col": str, "p": int, "q": int, "mean": str, "dist": str},
                       "cols": ["col"], "collists": []},
    "panel":          {"args": {"dependent": str, "independents": list,
                                 "entity": str, "time": str},
                       "cols": ["dependent", "entity", "time"], "collists": ["independents"]},
    "ts_diagnostics": {"args": {"dependent": str, "independents": list},
                       "cols": ["dependent"], "collists": ["independents"]},
    "seasonal_decompose": {"args": {"col": str, "period": int, "model": str},
                       "cols": ["col"], "collists": []},
}

# نام‌های فارسی برای نمایش در گزارش
TITLES = {
    "overview": "توصیف داده", "assumptions": "بررسی پیش‌فرض‌ها",
    "frequencies": "جدول فراوانی", "reliability": "پایایی (آلفای کرونباخ)",
    "correlation": "همبستگی", "crosstab": "جدول توافقی و کای‌دو",
    "ttest": "آزمون t", "anova": "تحلیل واریانس",
    "nonparametric": "آزمون ناپارامتری", "regression": "رگرسیون",
    "mediation": "تحلیل میانجی‌گری", "factor_analysis": "تحلیل عاملی اکتشافی",
    "sem_cfa": "تحلیل عاملی تأییدی / معادلات ساختاری",
    "pls_sem": "معادلات ساختاری حداقل مربعات جزئی (SmartPLS)",
    "unit_root": "آزمون ریشه‌ی واحد", "cointegration": "آزمون هم‌انباشتگی",
    "granger": "آزمون علیت گرنجر", "arima": "مدل ARIMA",
    "var_model": "خودرگرسیون برداری (VAR)", "vecm": "مدل تصحیح خطا (VECM)",
    "garch": "مدل GARCH", "panel": "داده‌ی تابلویی",
    "ts_diagnostics": "آزمون‌های تشخیصی رگرسیون",
    "manova": "تحلیل واریانس چندمتغیره (MANOVA)",
    "repeated_measures_anova": "تحلیل واریانس با اندازه‌گیری تکراری",
    "seasonal_decompose": "تجزیه‌ی فصلیِ سری زمانی",
}


def _colset(prof):
    return {c["نام"] for c in prof.get("ستون‌ها", [])}


def validate_step(step, prof):
    """یک گام از نقشه را بررسی می‌کند. یا گامِ تمیزشده برمی‌گرداند یا دلیل رد."""
    if not isinstance(step, dict):
        return None, "گام نامعتبر است"
    name = str(step.get("analysis") or step.get("تحلیل") or "").strip()
    if name in ("sem_pls", "pls", "smartpls"):
        name = "pls_sem"
    if name in ("var", "VAR"):
        name = "var_model"
    if name not in SPEC:
        return None, f"تحلیل «{name}» پشتیبانی نمی‌شود"
    spec = SPEC[name]
    cols = _colset(prof)
    raw = step.get("params") or step.get("پارامترها") or {}
    if not isinstance(raw, dict):
        raw = {}

    params = {}
    for k, v in raw.items():
        if k not in spec["args"]:
            continue                       # پارامتر ناشناخته دور ریخته می‌شود
        if k in ("factors", "structural"):
            continue                       # این‌ها پایین‌تر جداگانه اعتبارسنجی می‌شوند
        if k in spec["cols"]:
            if not isinstance(v, str) or v not in cols:
                return None, f"ستون «{v}» در داده نیست"
            params[k] = v
        elif k in spec["collists"]:
            if isinstance(v, str):
                v = [v]
            if not isinstance(v, list):
                continue
            keep = [x for x in v if isinstance(x, str) and x in cols]
            if not keep:
                return None, "هیچ‌کدام از ستون‌های خواسته‌شده در داده نیست"
            params[k] = keep
        else:
            params[k] = v

    # سازه‌ها: {"نام سازه": ["گویه", …]}
    if spec.get("factors"):
        f = raw.get("factors") or raw.get("سازه‌ها")
        if isinstance(f, dict):
            clean = {}
            for cname, items in f.items():
                if isinstance(items, str):
                    items = [items]
                keep = [x for x in (items or []) if isinstance(x, str) and x in cols]
                if len(keep) >= 2:
                    clean[str(cname)] = keep
            if clean:
                params["factors"] = clean
        if "factors" not in params:
            return None, "سازه‌ها و گویه‌هایشان مشخص نشده یا در داده نیستند"

    # مدل ساختاری: [["از","به"], …] فقط میان سازه‌های تعریف‌شده
    if spec.get("structural"):
        st = raw.get("structural") or raw.get("ساختاری")
        known = set((params.get("factors") or {}).keys())
        keep = []
        for pair in (st or []):
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                a, b = str(pair[0]), str(pair[1])
                if a in known and b in known and a != b:
                    keep.append([a, b])
        if keep:
            params["structural"] = keep

    # سازگاری داده با تحلیل
    ok, why = _data_supports(name, params, prof)
    if not ok:
        return None, why
    return {"analysis": name, "params": params,
            "title": step.get("title") or TITLES.get(name, name),
            "why": step.get("why") or step.get("چرا") or ""}, None


def _data_supports(name, params, prof):
    """آیا داده اصلاً برای این آزمون مناسب است؟ (پیام فارسی به‌جای خطای خام)"""
    n = prof.get("تعداد سطر", 0)
    if name in ("unit_root", "cointegration", "granger", "arima",
                "var_model", "vecm", "garch", "seasonal_decompose"):
        if not prof.get("ستون زمان") and not prof.get("سری‌زمانی است"):
            return False, ("این داده ساختار سری‌زمانی ندارد (ستون تاریخ/دوره پیدا نشد)، "
                           "پس آزمون‌های سری‌زمانی روی آن معنا ندارد.")
        if n < 30:
            return False, "برای آزمون‌های سری‌زمانی دست‌کم ۳۰ مشاهده لازم است."
    if name == "manova" and n < 20:
        return False, "برای MANOVA، حجم نمونه بسیار کم است."
    if name == "repeated_measures_anova" and n < 10:
        return False, "برای اندازه‌گیری تکراری، تعداد آزمودنی بسیار کم است."
    if name == "panel" and not prof.get("ساختار تابلویی"):
        return False, ("ساختار تابلویی (شناسه‌ی واحد + دوره‌ی زمانی) در این داده "
                       "تشخیص داده نشد.")
    if name in ("pls_sem", "sem_cfa", "factor_analysis") and n < 30:
        return False, "برای مدل‌های عاملی و ساختاری، حجم نمونه بسیار کم است."
    return True, ""


# ---------------- ساخت نقشه ----------------

PLAN_SYSTEM = (
    "تو یک متخصص آمار و روش تحقیق هستی که برای کاربر فارسی‌زبان تحلیل آماری طراحی می‌کند. "
    "بر پایه‌ی ساختار داده و خواسته‌ی کاربر، فهرست تحلیل‌های لازم را می‌سازی. "
    "فقط و فقط یک JSON معتبر برگردان، بدون هیچ توضیح اضافه و بدون بلوک کد."
)


def build_prompt(prof: dict, request: str) -> str:
    names = ", ".join(sorted(SPEC.keys()))
    slim = {k: v for k, v in prof.items() if k != "ستون‌ها"}
    sample_cols = [{"نام": c["نام"], "نوع": c["نوع"], "یکتا": c["یکتا"]}
                   for c in prof.get("ستون‌ها", [])[:60]]
    return (
        f"ساختار داده:\n{json.dumps(slim, ensure_ascii=False)}\n\n"
        f"ستون‌ها:\n{json.dumps(sample_cols, ensure_ascii=False)}\n\n"
        f"خواسته‌ی کاربر:\n«{request}»\n\n"
        f"تحلیل‌های مجاز (فقط از همین نام‌ها استفاده کن): {names}\n\n"
        "قالب خروجی دقیقاً این است:\n"
        '{"steps":[{"analysis":"نام_تحلیل","params":{...},"why":"چرا این تحلیل"}]}\n\n'
        "قاعده‌ها:\n"
        "- نام ستون‌ها را عیناً از فهرست بالا بردار؛ ستونی که در فهرست نیست ننویس.\n"
        "- برای pls_sem و sem_cfa پارامتر factors را بده: "
        '{"نام سازه":["گویه۱","گویه۲",...]} و در صورت نیاز structural: [["سازه۱","سازه۲"]].\n'
        "- اگر داده سری‌زمانی نیست، آزمون سری‌زمانی پیشنهاد نده.\n"
        "- ترتیب منطقی باشد: اول توصیف و پیش‌فرض‌ها، بعد آزمون‌های اصلی.\n"
        "- حداکثر ۸ گام. اگر خواسته‌ی کاربر مبهم است، تحلیل‌های متعارفِ همین داده را بده."
    )


def parse_plan(text: str):
    """JSON را از پاسخ مدل بیرون می‌کشد (حتی اگر داخل بلوک کد آمده باشد)."""
    if not text:
        return []
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    steps = data.get("steps") if isinstance(data, dict) else data
    return steps if isinstance(steps, list) else []


def fallback_plan(prof: dict) -> list:
    """نقشه‌ی پیش‌فرض بر پایه‌ی ساختار داده — وقتی مدل در دسترس نیست."""
    steps = [{"analysis": "overview", "params": {}}]
    num = prof.get("ستون‌های عددی") or []
    cat = prof.get("ستون‌های طبقه‌ای") or []
    likert = prof.get("ستون‌های لیکرت") or []
    constructs = prof.get("سازه‌های حدسی") or {}

    if cat:
        steps.append({"analysis": "frequencies", "params": {"cols": cat[:6]}})
    if len(num) >= 2:
        steps.append({"analysis": "assumptions", "params": {"cols": num[:8]}})
        steps.append({"analysis": "correlation", "params": {"cols": num[:8]}})
    if len(likert) >= 3:
        steps.append({"analysis": "reliability", "params": {"cols": likert}})
    if len(constructs) >= 2:
        f = {k: v for k, v in list(constructs.items())[:5]}
        keys = list(f.keys())
        steps.append({"analysis": "pls_sem",
                      "params": {"factors": f,
                                 "structural": [[keys[i], keys[-1]]
                                                for i in range(len(keys) - 1)]}})
    if prof.get("ساختار تابلویی"):
        steps.append({"analysis": "panel", "params": {}})
    elif prof.get("سری‌زمانی است") and num:
        steps.append({"analysis": "unit_root", "params": {"cols": num[:6]}})
        if len(num) >= 2:
            steps.append({"analysis": "cointegration", "params": {"cols": num[:4]}})
    elif len(num) >= 2 and cat:
        steps.append({"analysis": "anova",
                      "params": {"dependent": num[0], "factor": cat[0]}})
    return steps


def validate_plan(steps, prof, limit: int = 8):
    """نقشه را پالایش می‌کند: فقط گام‌های معتبر می‌مانند، بقیه با دلیل کنار می‌روند."""
    good, dropped, seen = [], [], set()
    for st in (steps or [])[: limit * 3]:
        clean, why = validate_step(st, prof)
        if clean is None:
            nm = (st or {}).get("analysis") if isinstance(st, dict) else str(st)
            dropped.append({"تحلیل": str(nm), "دلیل": why})
            continue
        key = (clean["analysis"], json.dumps(clean["params"], ensure_ascii=False, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        good.append(clean)
        if len(good) >= limit:
            break
    return good, dropped


def execute(path: str, steps, on_step=None) -> list:
    """گام‌ها را اجرا می‌کند. خطای یک گام، بقیه را متوقف نمی‌کند."""
    results = []
    for i, st in enumerate(steps, 1):
        if on_step:
            try:
                on_step(i, len(steps), st)
            except Exception:
                pass
        try:
            res = stats_engine.run(st["analysis"], path, **(st["params"] or {}))
        except Exception as e:
            res = {"error": f"اجرای تحلیل ممکن نشد: {e}"}
        results.append({"analysis": st["analysis"], "title": st.get("title") or
                        TITLES.get(st["analysis"], st["analysis"]),
                        "params": st["params"], "why": st.get("why", ""),
                        "result": res})
    return results
