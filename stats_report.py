# -*- coding: utf-8 -*-
"""
stats_report.py — تبدیل نتیجه‌ی خام تحلیل‌ها به گزارشِ مرتبِ فارسی.

خروجی، مارک‌داون با جدول‌های استاندارد است؛ همان چیزی که export_utils می‌تواند
مستقیم به Word، PDF یا Excel تبدیل کند. اعداد با تعداد رقم یکسان، ستاره‌ی
معناداری و پانویسِ ملاک‌ها نوشته می‌شوند تا آماده‌ی فصل چهارم رساله باشد.
"""
import re

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

# کلیدهایی که در جدول‌ها به‌عنوان «معناداری» شناخته می‌شوند
_SIG_KEYS = ("sig", "p", "p-value", "pvalue", "معناداری", "sig (F)")


def _fa(x) -> str:
    return str(x).translate(FA_DIGITS)


def _num(v, nd=3):
    """عدد را با تعداد رقم اعشار یکنواخت می‌نویسد."""
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "بله" if v else "خیر"
    if isinstance(v, (int,)):
        return _fa(v)
    if isinstance(v, float):
        if v != v:                       # NaN
            return "—"
        if v in (float("inf"), float("-inf")):
            return "∞"
        if abs(v) < 0.001 and v != 0:
            return _fa(f"{v:.2e}")
        return _fa(f"{v:.{nd}f}".rstrip("0").rstrip(".") or "0")
    return str(v)


def _cell(key, v):
    if isinstance(v, (list, tuple)):
        return "، ".join(_num(x) for x in v)
    if isinstance(v, dict):
        return "، ".join(f"{k}: {_num(x)}" for k, x in list(v.items())[:6])
    s = _num(v)
    # ستاره‌ی معناداری برای ستون‌های p
    if any(k == str(key).lower() for k in _SIG_KEYS) and isinstance(v, (int, float)):
        try:
            f = float(v)
            s += "***" if f < 0.01 else "**" if f < 0.05 else "*" if f < 0.1 else ""
        except (TypeError, ValueError):
            pass
    return s


def _md_table(rows, headers=None):
    """فهرستی از دیکشنری‌ها را به جدول مارک‌داون تبدیل می‌کند."""
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return ""
    if headers is None:
        headers = []
        for r in rows:
            for k in r:
                if k not in headers:
                    headers.append(k)
    headers = headers[:9]                     # جدول خیلی پهن در Word بد جا می‌شود
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "|" + "|".join([" --- "] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_cell(h, r.get(h)) for h in headers) + " |")
    return "\n".join(out)


def _dict_table(d, key_name="مورد", val_name="مقدار"):
    rows = [{key_name: str(k), val_name: v} for k, v in d.items()]
    return _md_table(rows, [key_name, val_name])


def _scalars_block(d):
    """کلیدهای ساده‌ی یک نتیجه را به‌صورت فهرست می‌نویسد."""
    skip = {"software", "trace", "diagram"}
    lines = []
    for k, v in d.items():
        if k in skip or isinstance(v, (list, dict)):
            continue
        lines.append(f"- **{k}:** {_cell(k, v)}")
    return "\n".join(lines)


def render_result(name: str, title: str, res: dict, why: str = "") -> str:
    """یک نتیجه‌ی تحلیل را به بخشی از گزارش تبدیل می‌کند."""
    parts = [f"## {title}"]
    if why:
        parts.append(f"*{why}*")
    if not isinstance(res, dict):
        parts.append(str(res))
        return "\n\n".join(parts)
    if res.get("error"):
        parts.append(f"⚠️ این تحلیل اجرا نشد: {res['error']}")
        return "\n\n".join(parts)
    if res.get("software"):
        parts.append(f"<small>{res['software']}</small>")

    scal = _scalars_block(res)
    if scal:
        parts.append(scal)

    for k, v in res.items():
        if k in ("software", "trace", "diagram"):
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict):
            parts.append(f"**{k}**\n\n" + _md_table(v))
        elif isinstance(v, list) and v:
            parts.append(f"**{k}:** " + "، ".join(_num(x) for x in v[:20]))
        elif isinstance(v, dict) and v:
            inner = list(v.values())
            if inner and all(isinstance(x, dict) for x in inner):
                rows = []
                for rk, rv in v.items():
                    row = {"مورد": str(rk)}
                    for ik, iv in rv.items():
                        row[ik] = iv
                    rows.append(row)
                parts.append(f"**{k}**\n\n" + _md_table(rows))
            else:
                parts.append(f"**{k}**\n\n" + _dict_table(v))
    return "\n\n".join(p for p in parts if p)


def render_profile(prof: dict) -> str:
    """بخش «شناخت داده» در ابتدای گزارش."""
    if not prof or prof.get("error"):
        return ""
    lines = ["## شناخت داده",
             f"- **تعداد مشاهده:** {_fa(prof.get('تعداد سطر', 0))}",
             f"- **تعداد متغیر:** {_fa(prof.get('تعداد ستون', 0))}"]
    if prof.get("ستون زمان"):
        lines.append(f"- **ستون زمان:** {prof['ستون زمان']}")
    if prof.get("ساختار تابلویی"):
        p = prof["ساختار تابلویی"]
        lines.append(f"- **ساختار تابلویی:** شناسه «{p['شناسه']}» و زمان «{p['زمان']}»")
    if prof.get("ستون‌های لیکرت"):
        lines.append(f"- **گویه‌های طیفی:** {_fa(len(prof['ستون‌های لیکرت']))} گویه")
    cols = prof.get("ستون‌ها") or []
    if cols:
        rows = [{"متغیر": c["نام"], "نوع": c["نوع"], "مقدار یکتا": c.get("یکتا"),
                 "گمشده (٪)": c.get("گمشده"), "میانگین": c.get("میانگین"),
                 "کمینه": c.get("کمینه"), "بیشینه": c.get("بیشینه")}
                for c in cols[:40]]
        lines.append("\n**مشخصات متغیرها**\n\n" + _md_table(rows))
    return "\n".join(lines)


def build_report(results, prof=None, request: str = "", interpretation: str = "",
                 title: str = "گزارش تحلیل آماری") -> str:
    """گزارش کامل به‌صورت مارک‌داون."""
    parts = [f"# {title}"]
    if request:
        parts.append(f"**درخواست کاربر:** {request}")
    p = render_profile(prof or {})
    if p:
        parts.append(p)
    for r in results or []:
        parts.append(render_result(r.get("analysis", ""), r.get("title") or "تحلیل",
                                   r.get("result") or {}, r.get("why", "")))
    if interpretation:
        parts.append("## تفسیر نتایج\n\n" + interpretation.strip())
    parts.append(
        "---\n\n"
        "<small>راهنمای نشانه‌ها: \\*\\*\\* معنادار در سطح ۰٫۰۱، "
        "\\*\\* معنادار در سطح ۰٫۰۵، \\* معنادار در سطح ۰٫۱٪. "
        "علامت — یعنی مقدار محاسبه نشده است.</small>"
    )
    return "\n\n".join(x for x in parts if x)


def summarize_for_model(results, max_chars: int = 9000) -> str:
    """خلاصه‌ی فشرده‌ی نتایج برای فرستادن به مدل جهت تفسیر.

    خروجی خام گاهی چند ده هزار نویسه است؛ اینجا فقط چیزی می‌ماند که برای تفسیر
    لازم است تا پرامپت بی‌جهت بزرگ (و پرهزینه) نشود.
    """
    import json
    out, used = [], 0
    for r in results or []:
        res = r.get("result") or {}
        if res.get("error"):
            piece = f"[{r.get('title')}] اجرا نشد: {res['error']}"
        else:
            slim = {k: v for k, v in res.items()
                    if k not in ("software", "trace", "diagram", "بارهای متقاطع",
                                 "واکنش آنی", "تجزیه واریانس", "ضرایب")}
            piece = f"[{r.get('title')}] " + json.dumps(slim, ensure_ascii=False)
        if used + len(piece) > max_chars:
            piece = piece[: max(0, max_chars - used)]
        out.append(piece)
        used += len(piece)
        if used >= max_chars:
            break
    return "\n\n".join(out)
