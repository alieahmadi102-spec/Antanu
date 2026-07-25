# -*- coding: utf-8 -*-
"""
sem_plot.py — ترسیم نمودار مسیر مدل به سبک SmartPLS برای خروجی PLS-SEM آنتانو.
سازه‌ها (متغیرهای پنهان) = دایره‌ی آبی، گویه‌ها = جعبه‌ی زرد، ضرایب مسیر و بارهای
عاملی روی فلش‌ها نوشته می‌شوند و R² داخل سازه‌های درون‌زا نمایش داده می‌شود.
خروجی: نام فایل PNG در EXPORT_DIR (یا None اگر رسم ممکن نبود).
"""
import os

_FONT = None


def _ensure_font():
    """فونت فارسی برای matplotlib (وزیرمتن اگر موجود بود)."""
    global _FONT
    if _FONT is not None:
        return _FONT
    try:
        from matplotlib import font_manager
        cand = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "static", "fonts", "Vazirmatn-Regular.ttf")
        if os.path.exists(cand):
            font_manager.fontManager.addfont(cand)
            _FONT = font_manager.FontProperties(fname=cand)
        else:
            _FONT = font_manager.FontProperties()
    except Exception:
        _FONT = False
    return _FONT


def _fa(text):
    """اصلاح شکل و ترتیب حروف فارسی برای نمایش درست در تصویر."""
    s = str(text)
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def _fa_num(x):
    try:
        s = f"{float(x):.3f}".rstrip("0").rstrip(".")
    except Exception:
        s = str(x)
    return s


def render_pls_diagram(result, title=None):
    """از خروجی sem_pls یک نمودار مسیر SmartPLS‌مانند می‌سازد."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Ellipse, FancyBboxPatch, FancyArrowPatch
    except Exception:
        return None

    constructs = result.get("constructs") or {}
    if not constructs:
        return None
    paths = result.get("paths") or []
    r2map = result.get("r2_by_construct") or {}
    fp = _ensure_font()
    fkw = {"fontproperties": fp} if fp else {}

    names = list(constructs.keys())
    # گراف ساختاری
    incoming = {n: [] for n in names}   # (from, beta)
    outgoing = {n: [] for n in names}
    for p in paths:
        f, t, b = p.get("from"), p.get("to"), p.get("beta")
        if f in names and t in names:
            outgoing[f].append(t)
            incoming[t].append((f, b))

    # لایه‌بندی (ستون) بر اساس بلندترین مسیر از سازه‌های برون‌زا
    col = {}

    def depth(n, seen=None):
        seen = seen or set()
        if n in seen:
            return 0
        seen.add(n)
        ins = incoming[n]
        if not ins:
            return 0
        return 1 + max((depth(f, seen) for f, _ in ins), default=0)

    for n in names:
        col[n] = depth(n)
    maxcol = max(col.values()) if col else 0

    # موقعیت سازه‌ها: ستون افقی، توزیع عمودی
    from collections import defaultdict
    bycol = defaultdict(list)
    for n in names:
        bycol[col[n]].append(n)

    COL_W = 5.0
    ROW_H = 3.2
    pos = {}
    max_rows = max((len(v) for v in bycol.values()), default=1)
    for c in range(maxcol + 1):
        nodes = bycol.get(c, [])
        total = len(nodes)
        for i, n in enumerate(nodes):
            x = c * COL_W
            # وسط‌چین عمودی هر ستون
            y = (max_rows - 1) / 2 * ROW_H - (i - (total - 1) / 2) * ROW_H
            pos[n] = (x, y)

    # سمت گویه‌ها: ستون اول → چپ، ستون آخر → راست، ستون‌های میانی → بالا/پایین
    _mid_toggle = {"i": 0}

    def item_side(n):
        c = col[n]
        if maxcol == 0:
            return "left"
        if c == 0:
            return "left"
        if c == maxcol:
            return "right"
        _mid_toggle["i"] += 1
        return "top" if _mid_toggle["i"] % 2 == 1 else "bottom"

    # اندازه‌ها
    R_W, R_H = 1.5, 1.05          # شعاع افقی/عمودی دایره سازه
    BOX_W, BOX_H = 2.1, 0.62      # جعبه گویه
    ITEM_GAP = 0.9
    ITEM_DX = 2.9                 # فاصله افقی گویه از سازه

    # ابعاد شکل بر اساس تعداد گویه‌ها
    max_items = max((len(v["items"]) for v in constructs.values()), default=3)
    fig_w = (maxcol + 1) * COL_W + 2 * (ITEM_DX + BOX_W)
    fig_h = max(max_rows * ROW_H, max_items * ITEM_GAP * len(names) / max(1, maxcol + 1)) + 3
    fig_h = max(fig_h, 6)
    fig, ax = plt.subplots(figsize=(min(fig_w * 0.5, 20), min(fig_h * 0.5, 16)), dpi=150)
    ax.set_axis_off()

    BLUE = "#5aa6e8"
    BLUE_EDGE = "#2f79c4"
    YELLOW = "#fff4b0"
    YELLOW_EDGE = "#d9b93a"
    GREY = "#7a7a7a"

    item_pos = {}   # (construct, item) -> (x,y)

    ITEM_DY = 1.9   # فاصله عمودی گویه از سازه (برای حالت بالا/پایین)

    # رسم گویه‌ها و اتصال‌شان به سازه
    for n in names:
        cx, cy = pos[n]
        items = constructs[n]["items"]
        loadings = constructs[n].get("loadings", {})
        side = item_side(n)
        k = len(items)
        for j, it in enumerate(items):
            if side in ("left", "right"):
                iy = cy + ((k - 1) / 2 - j) * ITEM_GAP
                ix = cx - (R_W + ITEM_DX) if side == "left" else cx + (R_W + ITEM_DX)
                edge = (cx - R_W if side == "left" else cx + R_W, cy)
                box_anchor = (ix + (BOX_W / 2 if side == "left" else -BOX_W / 2), iy)
            else:  # top / bottom → ردیف افقی
                ix = cx + ((k - 1) / 2 - j) * (BOX_W + 0.35)
                iy = cy + (R_H + ITEM_DY) if side == "top" else cy - (R_H + ITEM_DY)
                edge = (cx, cy + R_H if side == "top" else cy - R_H)
                box_anchor = (ix, iy - BOX_H / 2 if side == "top" else iy + BOX_H / 2)
            item_pos[(n, it)] = (ix, iy)
            box = FancyBboxPatch((ix - BOX_W / 2, iy - BOX_H / 2), BOX_W, BOX_H,
                                 boxstyle="round,pad=0.02,rounding_size=0.05",
                                 fc=YELLOW, ec=YELLOW_EDGE, lw=1.1, zorder=2)
            ax.add_patch(box)
            ax.text(ix, iy, _fa(it), ha="center", va="center", fontsize=7.5,
                    color="#333", zorder=3, **fkw)
            arr = FancyArrowPatch(edge, box_anchor, arrowstyle="-|>", mutation_scale=9,
                                  color=GREY, lw=0.8, zorder=1)
            ax.add_patch(arr)
            lv = loadings.get(it)
            if lv is not None:
                mx, my = (edge[0] + ix) / 2, (edge[1] + iy) / 2
                ax.text(mx, my + 0.12, _fa_num(lv), ha="center", va="center",
                        fontsize=6.8, color="#444", zorder=4,
                        bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.75), **fkw)

    # رسم فلش‌های ساختاری بین سازه‌ها با ضریب مسیر
    for p in paths:
        f, t, b = p.get("from"), p.get("to"), p.get("beta")
        if f not in pos or t not in pos:
            continue
        (x1, y1), (x2, y2) = pos[f], pos[t]
        # از لبه‌ی دایره‌ها شروع/پایان بگیر
        import math
        ang = math.atan2(y2 - y1, x2 - x1)
        sx = x1 + R_W * math.cos(ang)
        sy = y1 + R_H * math.sin(ang)
        ex = x2 - R_W * math.cos(ang)
        ey = y2 - R_H * math.sin(ang)
        arr = FancyArrowPatch((sx, sy), (ex, ey), arrowstyle="-|>", mutation_scale=14,
                              color="#3a3a3a", lw=1.4, zorder=4,
                              connectionstyle="arc3,rad=0.03")
        ax.add_patch(arr)
        if b is not None:
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            ax.text(mx, my + 0.14, _fa_num(b), ha="center", va="center", fontsize=9,
                    color="#0b3d91", fontweight="bold", zorder=5,
                    bbox=dict(boxstyle="round,pad=0.14", fc="white", ec="#bcd", alpha=0.92), **fkw)

    # رسم دایره‌ی سازه‌ها (روی همه) + نام و R²
    for n in names:
        cx, cy = pos[n]
        el = Ellipse((cx, cy), R_W * 2, R_H * 2, fc=BLUE, ec=BLUE_EDGE, lw=1.6, zorder=5)
        ax.add_patch(el)
        label = _fa(n)
        r2 = r2map.get(n)
        if r2 is not None:
            ax.text(cx, cy + 0.18, label, ha="center", va="center", fontsize=8.5,
                    color="white", fontweight="bold", zorder=6, **fkw)
            ax.text(cx, cy - 0.28, _fa_num(r2), ha="center", va="center", fontsize=8,
                    color="#eaffea", zorder=6, **fkw)
        else:
            ax.text(cx, cy, label, ha="center", va="center", fontsize=8.5,
                    color="white", fontweight="bold", zorder=6, **fkw)

    if title:
        ax.set_title(_fa(title), fontsize=12, color="#0f766e", pad=12, **fkw)

    ax.autoscale_view()
    ax.margins(0.08)
    ax.set_aspect("equal", adjustable="datalim")

    import secrets
    try:
        import export_utils
        outdir = export_utils.EXPORT_DIR
    except Exception:
        outdir = "."
    name = f"antanu-pls-{secrets.token_hex(6)}.png"
    fig.savefig(os.path.join(outdir, name), bbox_inches="tight", facecolor="white", dpi=150)
    plt.close(fig)
    return name


# ==================== نمودارهای سبک SPSS ====================

def _outdir():
    try:
        import export_utils
        return export_utils.EXPORT_DIR
    except Exception:
        return "."


def _save(fig, prefix):
    import secrets
    name = f"antanu-{prefix}-{secrets.token_hex(6)}.png"
    fig.savefig(os.path.join(_outdir(), name), bbox_inches="tight", facecolor="white", dpi=140)
    return name


def render_histograms(path, cols=None, max_charts=9):
    """هیستوگرام هر متغیر عددی همراه منحنی نرمال — مثل خروجی SPSS (Frequencies → Histogram)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import stats_engine
    except Exception:
        return None
    try:
        df = stats_engine._load_dataframe(path)
    except Exception:
        return None
    num = df.select_dtypes("number")
    if cols:
        keep = [c for c in cols if c in num.columns]
        if keep:
            num = num[keep]
    numcols = list(num.columns)[:max_charts]
    if not numcols:
        return None

    fp = _ensure_font()
    fkw = {"fontproperties": fp} if fp else {}
    ncol = min(3, len(numcols))
    nrow = (len(numcols) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(ncol * 3.4, nrow * 2.7), dpi=140)
    axes = np.array(axes).reshape(-1)
    for ax in axes[len(numcols):]:
        ax.set_axis_off()
    for i, c in enumerate(numcols):
        ax = axes[i]
        s = num[c].dropna().astype(float)
        if len(s) < 2:
            ax.set_axis_off(); continue
        ax.hist(s, bins=min(15, max(5, len(s) // 8)), color="#8ec5f0",
                edgecolor="#2f79c4", alpha=0.9, density=True)
        mu, sd = float(s.mean()), float(s.std(ddof=1) or 1)
        xs = np.linspace(s.min(), s.max(), 100)
        ax.plot(xs, np.exp(-((xs - mu) ** 2) / (2 * sd ** 2)) / (sd * (2 * np.pi) ** 0.5),
                color="#c0392b", lw=1.6)
        ax.set_title(_fa(str(c)), fontsize=9, color="#1f2937", **fkw)
        ax.tick_params(labelsize=6)
        for lab in ax.get_xticklabels():
            lab.set_fontsize(6)
    fig.suptitle(_fa("نمودار توزیع متغیرها با منحنی نرمال (سبک SPSS)"),
                 fontsize=11, color="#0f766e", **fkw)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    name = _save(fig, "hist")
    plt.close(fig)
    return name


def render_corr_heatmap(path, method="pearson", cols=None):
    """نقشه‌ی حرارتی همبستگی متغیرها — مثل SPSS/آنالیز همبستگی."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import stats_engine
    except Exception:
        return None
    try:
        df = stats_engine._load_dataframe(path)
    except Exception:
        return None
    num = df.select_dtypes("number")
    if cols:
        keep = [c for c in cols if c in num.columns]
        if len(keep) >= 2:
            num = num[keep]
    if num.shape[1] < 2:
        return None
    corr = num.corr(method=method if method in ("pearson", "spearman", "kendall") else "pearson")
    labels = [str(c) for c in corr.columns]

    fp = _ensure_font()
    fkw = {"fontproperties": fp} if fp else {}
    k = len(labels)
    fig, ax = plt.subplots(figsize=(max(4, k * 0.8), max(3.5, k * 0.75)), dpi=140)
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(k)); ax.set_yticks(range(k))
    ax.set_xticklabels([_fa(l) for l in labels], rotation=45, ha="right", fontsize=7, **fkw)
    ax.set_yticklabels([_fa(l) for l in labels], fontsize=7, **fkw)
    for i in range(k):
        for j in range(k):
            v = corr.values[i, j]
            ax.text(j, i, _fa_num(v), ha="center", va="center", fontsize=7,
                    color="white" if abs(v) > 0.55 else "#222", **fkw)
    ax.set_title(_fa("نقشه‌ی همبستگی متغیرها"), fontsize=11, color="#0f766e", pad=10, **fkw)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    name = _save(fig, "corr")
    plt.close(fig)
    return name
