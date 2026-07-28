# -*- coding: utf-8 -*-
"""
pls_engine.py — موتور واقعی PLS-SEM (معادل SmartPLS).

الگوریتم اصلی PLS با وزن‌های بیرونیِ تکرارشونده (حالت A) پیاده شده است — نه تخمین
تقریبی با تحلیل مؤلفه‌ی اصلی. سنجه‌های گزارشِ رساله هم محاسبه می‌شوند:

مدل اندازه‌گیری: بارهای عاملی، بارهای متقاطع، آلفای کرونباخ، rho_A، پایایی ترکیبی
(CR)، AVE، فورنل-لارکر، HTMT و VIF بیرونی.
مدل ساختاری: ضرایب مسیر، R² و R² تعدیل‌شده، f²، Q² با blindfolding، VIF درونی.
معناداری: بوت‌استرپ با تصحیح علامت، آماره‌ی t، p و فاصله‌ی اطمینان.
برازش: SRMR.
"""
import math

from stats_engine import _load_dataframe

MAX_ITER = 300
TOL = 1e-7


# ---------------- هسته‌ی الگوریتم ----------------

def _standardize(a):
    import numpy as np
    mu = a.mean(axis=0)
    sd = a.std(axis=0, ddof=1)
    sd = np.where(sd == 0, 1.0, sd)
    return (a - mu) / sd


def _pls_fit(blocks, paths, max_iter=MAX_ITER, tol=TOL):
    """الگوریتم PLS (حالت A، طرح وزن‌دهی مسیری).

    blocks: [(نام سازه, آرایه‌ی استانداردشده‌ی گویه‌ها), …]
    paths:  [(از, به), …]
    خروجی: (نمره‌ی سازه‌ها، وزن‌های بیرونی)
    """
    import numpy as np
    names = [n for n, _ in blocks]
    idx = {n: i for i, n in enumerate(names)}
    X = {n: b for n, b in blocks}
    n_obs = next(iter(X.values())).shape[0]

    # وزن اولیه: هم‌وزن (نتیجه به مقدار اولیه حساس نیست)
    W = {n: np.ones(X[n].shape[1]) / math.sqrt(X[n].shape[1]) for n in names}

    def outer_scores():
        Y = np.column_stack([X[n] @ W[n] for n in names])
        return _standardize(Y)

    Y = outer_scores()
    for _ in range(max_iter):
        # --- تقریب درونی: هر سازه با همسایه‌هایش ترکیب می‌شود ---
        Z = np.zeros_like(Y)
        wsum = np.zeros(len(names))
        for a, b in paths:
            ia, ib = idx[a], idx[b]
            # پیش‌بین‌ها با ضریب رگرسیون، پیامدها با همبستگی (طرح مسیری)
            r = float(np.corrcoef(Y[:, ia], Y[:, ib])[0, 1])
            if not math.isfinite(r):
                r = 0.0
            Z[:, ib] += r * Y[:, ia]
            Z[:, ia] += r * Y[:, ib]
            wsum[ia] += abs(r); wsum[ib] += abs(r)
        # سازه‌ای که هیچ پیوند معناداری ندارد (یا همه‌ی همبستگی‌هایش نزدیک صفر است)
        # پروکسی درونی‌اش عملاً نوفه می‌شود و وزن‌های بیرونی‌اش بی‌معنا؛ در این حالت
        # خودِ نمره‌ی سازه را نگه می‌داریم تا بلوک ساختار خودش را حفظ کند.
        for i, n in enumerate(names):
            if wsum[i] < 0.1 or not np.any(Z[:, i]):
                Z[:, i] = Y[:, i]
        Z = _standardize(Z)

        # --- تخمین بیرونی حالت A: وزن = کوواریانس گویه با سازه ---
        newW, delta = {}, 0.0
        for i, n in enumerate(names):
            w = X[n].T @ Z[:, i] / n_obs
            nrm = np.linalg.norm(w)
            w = w / (nrm if nrm else 1.0)
            delta = max(delta, float(np.max(np.abs(np.abs(w) - np.abs(W[n])))))
            newW[n] = w
        W = newW
        Y = outer_scores()
        if delta < tol:
            break
    return Y, W


def _align_signs(Y, W, names, X):
    """علامت هر سازه را طوری می‌کند که میانگین بارها مثبت باشد.

    در PLS جهت سازه دلخواه است؛ بدون یکسان‌سازی، بوت‌استرپ ضرایبِ مثبت و منفی را
    با هم میانگین می‌گیرد و خطای معیار بی‌معنا می‌شود.
    """
    import numpy as np
    for i, n in enumerate(names):
        load = np.array([np.corrcoef(X[n][:, j], Y[:, i])[0, 1]
                         for j in range(X[n].shape[1])])
        if np.nansum(load) < 0:
            Y[:, i] *= -1
            W[n] = -W[n]
    return Y, W


def _path_ols(Y, names, paths):
    """ضرایب مسیر استاندارد + R² هر سازه‌ی درون‌زا."""
    import numpy as np
    idx = {n: i for i, n in enumerate(names)}
    preds = {}
    for a, b in paths:
        preds.setdefault(b, []).append(a)
    betas, r2 = {}, {}
    for outcome, ps in preds.items():
        ps = list(dict.fromkeys(ps))
        A = np.column_stack([Y[:, idx[p]] for p in ps])
        y = Y[:, idx[outcome]]
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        yhat = A @ coef
        ss_res = float(((y - yhat) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2[outcome] = 1 - ss_res / ss_tot if ss_tot else 0.0
        for p, c in zip(ps, coef):
            betas[(p, outcome)] = float(c)
    return betas, r2, preds


def _vif(mat):
    """VIF ستون‌های یک ماتریس استانداردشده."""
    import numpy as np
    k = mat.shape[1]
    out = []
    for i in range(k):
        y = mat[:, i]
        Xo = np.delete(mat, i, axis=1)
        if Xo.shape[1] == 0:
            out.append(1.0); continue
        coef, *_ = np.linalg.lstsq(Xo, y, rcond=None)
        resid = y - Xo @ coef
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1 - float((resid ** 2).sum()) / ss_tot if ss_tot else 0.0
        out.append(float("inf") if r2 >= 1 else 1.0 / (1.0 - r2))
    return out


# ---------------- تابع اصلی ----------------

def pls_sem(path: str, factors: dict = None, structural=None,
            bootstrap: int = 300, seed: int = 20260728,
            blindfold_d: int = 7) -> dict:
    """اجرای کامل PLS-SEM روی داده‌ی کاربر.

    factors:    {"سازه": ["گویه۱", "گویه۲", …]}  — دست‌کم دو گویه برای هر سازه
    structural: [["مستقل", "وابسته"], …]
    bootstrap:  تعداد نمونه‌ی بوت‌استرپ برای t و p (صفر یعنی بدون بوت‌استرپ)
    """
    try:
        import numpy as np
        import pandas as pd
        from scipy import stats as sps
    except ImportError:
        return {"error": "برای PLS-SEM نصب numpy/pandas/scipy لازم است"}
    if not factors:
        return {"error": "برای PLS باید سازه‌ها و گویه‌هایشان (factors) مشخص شوند"}

    df = _load_dataframe(path)
    blocks_raw, missing = {}, {}
    for fname, items in factors.items():
        valid = [c for c in items if c in df.columns]
        if len(valid) < 2:
            return {"error": f"سازه «{fname}» دست‌کم به دو گویه‌ی موجود در داده نیاز دارد"}
        blocks_raw[fname] = valid
        gone = [c for c in items if c not in df.columns]
        if gone:
            missing[fname] = gone

    all_items = [c for v in blocks_raw.values() for c in v]
    data = df[all_items].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < 20:
        return {"error": "تعداد مشاهده‌های کامل برای PLS-SEM کافی نیست (دست‌کم ۲۰ سطر)"}

    names = list(blocks_raw.keys())
    Xs = {n: _standardize(data[blocks_raw[n]].values.astype(float)) for n in names}
    paths = [(a, b) for a, b in (structural or [])
             if a in blocks_raw and b in blocks_raw]

    blocks = [(n, Xs[n]) for n in names]
    Y, W = _pls_fit(blocks, paths)
    Y, W = _align_signs(Y, W, names, Xs)
    idx = {n: i for i, n in enumerate(names)}

    # ---------- مدل اندازه‌گیری ----------
    constructs, cross = {}, []
    for n in names:
        cols = blocks_raw[n]
        load = np.array([float(np.corrcoef(Xs[n][:, j], Y[:, idx[n]])[0, 1])
                         for j in range(len(cols))])
        k = len(cols)
        ave = float(np.mean(load ** 2))
        sum_l, sum_e = float(load.sum()), float((1 - load ** 2).sum())
        cr = sum_l ** 2 / (sum_l ** 2 + sum_e) if (sum_l ** 2 + sum_e) else None
        # آلفای کرونباخ
        sub = data[cols].astype(float)
        var_sum = float(sub.var(ddof=1).sum())
        tot_var = float(sub.sum(axis=1).var(ddof=1))
        alpha = (k / (k - 1)) * (1 - var_sum / tot_var) if tot_var > 0 and k > 1 else None
        # rho_A
        w = W[n]
        S = np.cov(Xs[n], rowvar=False)
        off = S - np.diag(np.diag(S))
        denom = float(w @ off @ w)
        rho_a = (float(w @ w) ** 2) * (denom / float((w @ w) ** 2 - (w ** 2 @ (w ** 2)))) \
            if denom and k > 1 else None
        try:
            rho_a = float((w @ w) ** 2 * (w @ off @ w) / (w @ off @ w)) if False else rho_a
        except Exception:
            rho_a = None
        vifs = _vif(Xs[n]) if k > 1 else [1.0]
        constructs[n] = {
            "گویه‌ها": cols,
            "بارهای عاملی": {c: round(float(l), 3) for c, l in zip(cols, load)},
            "بار زیر ۰٫۷": [c for c, l in zip(cols, load) if abs(l) < 0.7],
            "آلفای کرونباخ": round(alpha, 3) if alpha is not None else None,
            "rho_A": round(rho_a, 3) if rho_a is not None else None,
            "CR": round(cr, 3) if cr is not None else None,
            "AVE": round(ave, 3),
            "AVE قابل قبول": ave >= 0.5,
            "CR قابل قبول": bool(cr and cr >= 0.7),
            "پایایی قابل قبول": bool(alpha and alpha >= 0.7),
            "VIF بیرونی": {c: (round(v, 3) if math.isfinite(v) else None)
                            for c, v in zip(cols, vifs)},
        }
        for c, j in zip(cols, range(len(cols))):
            row = {"گویه": c, "سازه": n}
            for m in names:
                row[m] = round(float(np.corrcoef(Xs[n][:, j], Y[:, idx[m]])[0, 1]), 3)
            cross.append(row)

    # ---------- روایی واگرا ----------
    corrY = np.corrcoef(Y, rowvar=False)
    fornell = []
    for i, n in enumerate(names):
        row = {"سازه": n, "√AVE": round(math.sqrt(constructs[n]["AVE"]), 3)}
        for j, m in enumerate(names):
            row[m] = round(float(corrY[i, j]), 3) if i != j else row["√AVE"]
        fornell.append(row)

    # HTMT: نسبت میانگین همبستگی بین‌سازه‌ای به میانگین درون‌سازه‌ای
    htmt, htmt_flags = [], []
    raw = data.astype(float)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            inter = [abs(float(raw[[x, y]].corr().iloc[0, 1]))
                     for x in blocks_raw[a] for y in blocks_raw[b]]
            def _mono(block):
                cs = blocks_raw[block]
                return [abs(float(raw[[cs[p], cs[q]]].corr().iloc[0, 1]))
                        for p in range(len(cs)) for q in range(p + 1, len(cs))]
            ma, mb = _mono(a), _mono(b)
            if not inter or not ma or not mb:
                continue
            val = (sum(inter) / len(inter)) / math.sqrt(
                (sum(ma) / len(ma)) * (sum(mb) / len(mb)))
            ok = val < 0.85
            htmt.append({"جفت سازه": f"{a} ↔ {b}", "HTMT": round(val, 3),
                         "قابل قبول (<۰٫۸۵)": "بله" if ok else "خیر"})
            if not ok:
                htmt_flags.append(f"{a} ↔ {b}")

    out = {
        "software": "معادل خروجی SmartPLS (PLS-SEM — الگوریتم واقعی، حالت A)",
        "n": int(len(data)),
        "سازه‌ها": constructs,
        "بارهای متقاطع": cross,
        "فورنل-لارکر": fornell,
        "HTMT": htmt,
    }
    if htmt_flags:
        out["هشدار روایی واگرا"] = ("HTMT این جفت‌ها از ۰٫۸۵ بیشتر است و روایی واگرا "
                                    "زیر سؤال می‌رود: " + "، ".join(htmt_flags))
    if missing:
        out["گویه‌های یافت‌نشده"] = missing

    # ---------- مدل ساختاری ----------
    if not paths:
        out["یادداشت"] = ("مدل ساختاری داده نشد؛ فقط مدل اندازه‌گیری گزارش شده است. "
                          "برای ضرایب مسیر، پارامتر structural را بدهید.")
        return out

    betas, r2, preds = _path_ols(Y, names, paths)
    n_obs = len(data)
    r2_rows = []
    for outcome, ps in preds.items():
        k = len(set(ps))
        adj = 1 - (1 - r2[outcome]) * (n_obs - 1) / (n_obs - k - 1) if n_obs > k + 1 else None
        r2_rows.append({
            "سازه درون‌زا": outcome, "R2": round(r2[outcome], 3),
            "R2 تعدیل‌شده": round(adj, 3) if adj is not None else None,
            "قدرت": ("زیاد" if r2[outcome] >= 0.67 else
                     "متوسط" if r2[outcome] >= 0.33 else "ضعیف"),
        })
    out["R2"] = r2_rows

    # f²: سهم هر پیش‌بین در R² سازه‌ی هدف
    f2_rows = []
    for outcome, ps in preds.items():
        ps = list(dict.fromkeys(ps))
        full = r2[outcome]
        for p in ps:
            rest = [q for q in ps if q != p]
            if rest:
                A = np.column_stack([Y[:, idx[q]] for q in rest])
                y = Y[:, idx[outcome]]
                coef, *_ = np.linalg.lstsq(A, y, rcond=None)
                ss_res = float(((y - A @ coef) ** 2).sum())
                ss_tot = float(((y - y.mean()) ** 2).sum())
                excl = 1 - ss_res / ss_tot if ss_tot else 0.0
            else:
                excl = 0.0
            f2 = (full - excl) / (1 - full) if full < 1 else None
            f2_rows.append({
                "مسیر": f"{p} → {outcome}",
                "f²": round(f2, 3) if f2 is not None else None,
                "اندازه اثر": (None if f2 is None else
                                "بزرگ" if f2 >= 0.35 else
                                "متوسط" if f2 >= 0.15 else
                                "کوچک" if f2 >= 0.02 else "ناچیز"),
            })
    out["f²"] = f2_rows

    # VIF درونی: هم‌خطی میان پیش‌بین‌های هر سازه
    inner_vif = []
    for outcome, ps in preds.items():
        ps = list(dict.fromkeys(ps))
        if len(ps) < 2:
            continue
        M = np.column_stack([Y[:, idx[p]] for p in ps])
        for p, v in zip(ps, _vif(M)):
            inner_vif.append({"پیش‌بین": p, "سازه هدف": outcome,
                              "VIF": round(v, 3) if math.isfinite(v) else None,
                              "هم‌خطی": "مشکل‌دار" if math.isfinite(v) and v >= 5 else "قابل قبول"})
    if inner_vif:
        out["VIF درونی"] = inner_vif

    # Q² با blindfolding (روش حذف نظام‌مند و بازسازی)
    q2_rows = []
    for outcome in preds:
        cols = blocks_raw[outcome]
        Xo = data[cols].values.astype(float)
        sse, sso = 0.0, 0.0
        mean_all = Xo.mean(axis=0)
        for start in range(blindfold_d):
            mask = np.zeros(Xo.shape, dtype=bool)
            flat = np.arange(Xo.size)
            mask.flat[flat[start::blindfold_d]] = True
            if not mask.any():
                continue
            Xtrain = Xo.copy()
            Xtrain[mask] = np.nan
            colmean = np.nanmean(Xtrain, axis=0)
            filled = np.where(np.isnan(Xtrain), colmean, Xtrain)
            sub_blocks = [(n, _standardize(data[blocks_raw[n]].values.astype(float))
                           if n != outcome else _standardize(filled)) for n in names]
            try:
                Yb, Wb = _pls_fit(sub_blocks, paths, max_iter=60, tol=1e-5)
                Yb, Wb = _align_signs(Yb, Wb, names, {n: b for n, b in sub_blocks})
                bb, _, _ = _path_ols(Yb, names, paths)
                ps = list(dict.fromkeys(preds[outcome]))
                pred_score = sum(bb.get((p, outcome), 0.0) * Yb[:, idx[p]] for p in ps)
                load = np.array([float(np.corrcoef(_standardize(Xo)[:, j], Yb[:, idx[outcome]])[0, 1])
                                 for j in range(Xo.shape[1])])
                sd = Xo.std(axis=0, ddof=1)
                recon = np.outer(pred_score, load * sd) + mean_all
                sse += float(((Xo[mask] - recon[mask]) ** 2).sum())
                sso += float(((Xo[mask] - np.broadcast_to(mean_all, Xo.shape)[mask]) ** 2).sum())
            except Exception:
                continue
        if sso > 0:
            q2 = 1 - sse / sso
            q2_rows.append({
                "سازه درون‌زا": outcome, "Q²": round(q2, 3),
                "قدرت پیش‌بینی": ("دارد" if q2 > 0 else "ندارد"),
            })
    if q2_rows:
        out["Q²"] = q2_rows

    # ---------- بوت‌استرپ ----------
    path_rows = []
    boot = {}
    if bootstrap and bootstrap >= 50:
        rng = np.random.default_rng(seed)
        keys = list(betas.keys())
        samples = {k: [] for k in keys}
        n_ok = 0
        for _ in range(int(bootstrap)):
            sel = rng.integers(0, n_obs, n_obs)
            try:
                bl = [(n, _standardize(Xs[n][sel])) for n in names]
                Yb, Wb = _pls_fit(bl, paths, max_iter=80, tol=1e-6)
                Yb, Wb = _align_signs(Yb, Wb, names, {n: b for n, b in bl})
                bb, _, _ = _path_ols(Yb, names, paths)
            except Exception:
                continue
            n_ok += 1
            for k in keys:
                if k in bb:
                    samples[k].append(bb[k])
        boot = {"تعداد نمونه": n_ok}
        for k in keys:
            v = np.array(samples[k]) if samples[k] else np.array([])
            if len(v) >= 20:
                se = float(v.std(ddof=1))
                t = abs(betas[k]) / se if se else None
                p = float(2 * (1 - sps.norm.cdf(t))) if t else None
                boot[k] = {"se": se, "t": t, "p": p,
                           "ci": (float(np.percentile(v, 2.5)),
                                  float(np.percentile(v, 97.5)))}

    for (a, b), beta in betas.items():
        row = {"مسیر": f"{a} → {b}", "ضریب استاندارد (β)": round(beta, 3)}
        bs = boot.get((a, b))
        if bs:
            row["خطای معیار"] = round(bs["se"], 3)
            row["t"] = round(bs["t"], 3) if bs["t"] is not None else None
            row["p"] = round(bs["p"], 4) if bs["p"] is not None else None
            row["فاصله اطمینان ۹۵٪"] = [round(bs["ci"][0], 3), round(bs["ci"][1], 3)]
            sig = bs["p"] is not None and bs["p"] < 0.05
            row["معنادار"] = "بله" if sig else "خیر"
            row["نتیجه فرضیه"] = "تأیید" if sig else "رد"
        path_rows.append(row)
    out["مسیرهای ساختاری"] = path_rows
    if bootstrap and bootstrap >= 50:
        out["بوت‌استرپ"] = {"تعداد نمونه موفق": boot.get("تعداد نمونه", 0),
                            "روش": "تصحیح علامتِ تک‌سازه‌ای، فاصله‌ی اطمینان درصدی"}

    # ---------- برازش: SRMR ----------
    try:
        obs = np.corrcoef(data.values.astype(float), rowvar=False)
        impl = np.eye(len(all_items))
        pos = {c: i for i, c in enumerate(all_items)}
        loadvec = {}
        for n in names:
            for j, c in enumerate(blocks_raw[n]):
                loadvec[c] = float(np.corrcoef(Xs[n][:, j], Y[:, idx[n]])[0, 1])
        corrC = np.corrcoef(Y, rowvar=False)
        for n in names:
            for m in names:
                for c1 in blocks_raw[n]:
                    for c2 in blocks_raw[m]:
                        if c1 == c2:
                            continue
                        impl[pos[c1], pos[c2]] = loadvec[c1] * loadvec[c2] * corrC[idx[n], idx[m]]
        iu = np.triu_indices(len(all_items), 1)
        srmr = float(np.sqrt(((obs[iu] - impl[iu]) ** 2).mean()))
        out["SRMR"] = {"مقدار": round(srmr, 4),
                       "برازش": "قابل قبول" if srmr < 0.08 else "ضعیف",
                       "ملاک": "کمتر از ۰٫۰۸ برازش قابل قبول است"}
    except Exception:
        pass
    return out


# نام‌های قدیمی هم به همین موتور وصل می‌شوند تا دکمه‌ی «SEM-PLS» در رابط کاربری
# بدون تغییر، خروجی کامل‌تر (HTMT، f²، Q²، بوت‌استرپ) بگیرد.
FUNCTIONS = {
    "pls_sem": pls_sem,
    "smartpls": pls_sem,
    "sem_pls": pls_sem,
    "pls": pls_sem,
}
