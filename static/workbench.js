/* میزکار نرم‌افزارهای آماری آنتانو — SPSS / EViews / SmartPLS
   یک موتور مشترک: منوها و پنجره‌های گفت‌وگو از پیکربندی سرور ساخته می‌شوند و
   محاسبه‌ها با موتورهای واقعی (stats_engine / ts_engine / pls_engine) اجرا می‌شوند. */
(function () {
  "use strict";
  const CFG = window.WB_CONFIG || {};
  const SW = CFG.id || "spss";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* ---------------- وضعیت ---------------- */
  const S = {
    file: null,          // نام فایل روی سرور
    title: "",           // نام نمایشی داده
    columns: [],         // [{name,type,missing,unique,mean,std,min,max}]
    rows: [],            // [[cell,…]]
    totalRows: 0,
    truncated: false,
    dirty: false,
    selRow: -1, selCol: -1,
    outputs: [],         // [{title, fa, analysis, result, interpretation, time}]
    running: false,
  };
  const PLS = { constructs: [], paths: [], pos: {}, lastResult: null };

  function status(msg, busy) {
    $("#wbStatus").textContent = msg || "پردازشگر ANTANU آماده است";
    $("#wbStatus").style.color = busy ? "var(--acc)" : "";
  }
  function dims() {
    $("#wbDims").textContent = S.columns.length
      ? `${S.totalRows || S.rows.length} مشاهده × ${S.columns.length} متغیر` : "";
  }
  function setDirty(d) {
    S.dirty = d;
    $("#wbDirty").hidden = !d;
  }
  function chip() {
    $("#wbFileChip").textContent = S.title
      ? `📄 ${S.title}` : "هنوز داده‌ای باز نشده — از «داده‌های من» یا «آپلود فایل» شروع کنید";
  }

  /* ---------------- نوار منو ---------------- */
  function buildMenus() {
    const bar = $("#wbMenubar");
    bar.innerHTML = "";
    (CFG.menus || []).forEach((menu) => {
      const m = document.createElement("div");
      m.className = "wb-menu";
      m.innerHTML = `<button type="button"><b>${esc(menu.label)}</b> <small>${esc(menu.fa || "")}</small></button>`;
      const drop = document.createElement("div");
      drop.className = "wb-drop";
      (menu.items || []).forEach((item) => drop.appendChild(buildItem(item)));
      m.appendChild(drop);
      m.querySelector("button").addEventListener("click", (e) => {
        e.stopPropagation();
        const was = m.classList.contains("open");
        closeMenus();
        if (!was) m.classList.add("open");
      });
      bar.appendChild(m);
    });
    document.addEventListener("click", closeMenus);
  }
  function closeMenus() {
    document.querySelectorAll(".wb-menu.open, .wb-item.open")
      .forEach((el) => el.classList.remove("open"));
  }
  function buildItem(item) {
    const d = document.createElement("div");
    d.className = "wb-item";
    const hasKids = Array.isArray(item.children) && item.children.length;
    d.innerHTML = `<button type="button">
        <span><span class="en">${esc(item.label)}</span>
        <span class="fa2">${esc(item.fa || "")}</span></span>
        ${hasKids ? '<span class="arrow">◂</span>' : ""}</button>`;
    if (hasKids) {
      const sub = document.createElement("div");
      sub.className = "wb-sub";
      item.children.forEach((c) => sub.appendChild(buildItem(c)));
      d.appendChild(sub);
      d.querySelector("button").addEventListener("click", (e) => {
        e.stopPropagation();
        const was = d.classList.contains("open");
        d.parentElement.querySelectorAll(".wb-item.open").forEach((x) => x.classList.remove("open"));
        if (!was) d.classList.add("open");
      });
    } else {
      d.querySelector("button").addEventListener("click", (e) => {
        e.stopPropagation(); closeMenus();
        if (item.action) doAction(item.action);
        else if (item.analysis) openAnalysisDialog(item);
      });
    }
    return d;
  }

  /* ---------------- شبکه‌ی داده (Data View) ---------------- */
  function renderGrid() {
    const t = $("#wbGrid");
    if (!S.columns.length) {
      t.innerHTML = `<tbody><tr><td style="padding:30px;border:0;color:#889">
        برای شروع، از منوی File داده‌ای باز کنید یا داده‌ی جدید بسازید.</td></tr></tbody>`;
      dims(); renderVars(); renderSeries(); renderIndicators();
      return;
    }
    let h = "<thead><tr><th class='rownum-h'></th>";
    S.columns.forEach((c, i) => {
      h += `<th data-c="${i}" title="دوبار کلیک = تغییر نام">${esc(c.name)}</th>`;
    });
    h += "</tr></thead><tbody>";
    S.rows.forEach((r, ri) => {
      h += `<tr><td class="rownum" data-r="${ri}">${ri + 1}</td>`;
      S.columns.forEach((_, ci) => {
        const v = r[ci];
        h += `<td contenteditable data-r="${ri}" data-c="${ci}">${esc(v === null || v === undefined ? "" : v)}</td>`;
      });
      h += "</tr>";
    });
    h += "</tbody>";
    t.innerHTML = h;
    if (S.truncated) {
      status(`⚠️ برای نمایش، فقط ${S.rows.length} سطر اول نشان داده شده است (کل: ${S.totalRows})`);
    }
    dims(); renderVars(); renderSeries(); renderIndicators();
  }

  $("#wbGrid").addEventListener("input", (e) => {
    const td = e.target.closest("td[contenteditable]");
    if (!td) return;
    S.rows[+td.dataset.r][+td.dataset.c] = td.textContent.trim();
    setDirty(true);
  });
  $("#wbGrid").addEventListener("click", (e) => {
    const rn = e.target.closest("td.rownum");
    const th = e.target.closest("th[data-c]");
    document.querySelectorAll("#wbGrid .selrow").forEach((x) => x.classList.remove("selrow"));
    document.querySelectorAll("#wbGrid .selcol").forEach((x) => x.classList.remove("selcol"));
    if (rn) {
      S.selRow = +rn.dataset.r; S.selCol = -1;
      rn.parentElement.classList.add("selrow");
    } else if (th) {
      S.selCol = +th.dataset.c; S.selRow = -1;
      document.querySelectorAll(`#wbGrid [data-c="${S.selCol}"]`).forEach((x) => x.classList.add("selcol"));
    }
  });
  $("#wbGrid").addEventListener("dblclick", (e) => {
    const th = e.target.closest("th[data-c]");
    if (th) renameColumn(+th.dataset.c);
  });

  function renameColumn(ci) {
    const cur = S.columns[ci].name;
    const name = prompt("نام جدید متغیر:", cur);
    if (!name || name.trim() === cur) return;
    S.columns[ci].name = name.trim();
    setDirty(true); renderGrid();
  }

  /* ---------------- Variable View ---------------- */
  function renderVars() {
    const t = $("#wbVars");
    if (!S.columns.length) { t.innerHTML = ""; return; }
    let h = `<thead><tr><th>#</th><th>Name — نام</th><th>Type — نوع</th>
      <th>Missing — گمشده</th><th>Values — مقادیر یکتا</th>
      <th>میانگین</th><th>انحراف معیار</th><th>کمینه</th><th>بیشینه</th></tr></thead><tbody>`;
    S.columns.forEach((c, i) => {
      h += `<tr><td>${i + 1}</td>
        <td class="vn" contenteditable data-c="${i}">${esc(c.name)}</td>
        <td>${c.type === "numeric" ? "Numeric — عددی" : "String — متنی"}</td>
        <td>${c.missing ?? ""}</td><td>${c.unique ?? ""}</td>
        <td>${c.mean ?? ""}</td><td>${c.std ?? ""}</td>
        <td>${c.min ?? ""}</td><td>${c.max ?? ""}</td></tr>`;
    });
    t.innerHTML = h + "</tbody>";
  }
  $("#wbVars").addEventListener("blur", (e) => {
    const td = e.target.closest("td.vn");
    if (!td) return;
    const ci = +td.dataset.c;
    const name = td.textContent.trim();
    if (name && name !== S.columns[ci].name) {
      S.columns[ci].name = name; setDirty(true); renderGrid();
    }
  }, true);

  /* ---------------- فهرست سری‌ها (EViews) ---------------- */
  function renderSeries() {
    const box = $("#wbSeriesList");
    if (!box) return;
    box.innerHTML = S.columns.length ? "" :
      "<div style='padding:12px;color:#889;font-size:12px'>کاربرگ خالی است</div>";
    S.columns.forEach((c) => {
      const d = document.createElement("div");
      d.className = "wb-series";
      d.innerHTML = `<span class="ico">${c.type === "numeric" ? "📈" : "🔤"}</span>
        <span class="nm">${esc(c.name)}</span>`;
      box.appendChild(d);
    });
  }

  /* ---------------- تب‌ها ---------------- */
  document.querySelectorAll(".wb-tab").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll(".wb-tab").forEach((x) => x.classList.toggle("on", x === b));
      const tab = b.dataset.tab;
      const cv = $("#plsCanvasWrap");
      if (cv) cv.style.display = tab === "canvas" ? "block" : "none";
      $("#wbGridWrap").style.display = tab === "data" ? "block" : "none";
      $("#wbVarsWrap").style.display = tab === "vars" ? "block" : "none";
    });
  });

  /* ---------------- عملیات پرونده و ویرایش ---------------- */
  async function doAction(act) {
    if (act === "new") return newData();
    if (act === "open") return openDatasetPicker();
    if (act === "import") return $("#wbFileInput").click();
    if (act === "save") return saveGrid(true);
    if (act === "export") return exportCSV();
    if (act === "addrow") { ensureData(); S.rows.push(S.columns.map(() => "")); setDirty(true); renderGrid(); return; }
    if (act === "addcol") return addColumn();
    if (act === "delrow") {
      if (S.selRow < 0) return status("⚠️ اول با کلیک روی شماره‌ی سطر، آن را انتخاب کنید");
      S.rows.splice(S.selRow, 1); S.selRow = -1; setDirty(true); renderGrid(); return;
    }
    if (act === "delcol") {
      if (S.selCol < 0) return status("⚠️ اول با کلیک روی سرستون، ستون را انتخاب کنید");
      S.columns.splice(S.selCol, 1);
      S.rows.forEach((r) => r.splice(S.selCol, 1));
      S.selCol = -1; setDirty(true); renderGrid(); return;
    }
    if (act === "output") return showOutput();
    if (act === "panel") return togglePanel();
    if (act === "pls_algorithm") return runPLS(0);
    if (act === "bootstrapping") return runPLS(+($("#plsBoot")?.value || 500));
    if (act === "cfa") return runCFA();
  }
  document.querySelectorAll(".wb-toolbar .wb-tool").forEach((b) =>
    b.addEventListener("click", () => doAction(b.dataset.act)));
  document.querySelectorAll(".panel-close").forEach((b) =>
    b.addEventListener("click", () => doAction(b.dataset.act)));

  /* روی گوشی، پنل کناری یک برگه‌ی تمام‌صفحه است که باز و بسته می‌شود */
  function togglePanel(force) {
    const p = $("#plsPanel");
    if (!p) return;
    const on = force === undefined ? !p.classList.contains("show") : !!force;
    p.classList.toggle("show", on);
  }

  function ensureData() {
    if (!S.columns.length) {
      S.columns = [1, 2, 3, 4].map((i) => ({ name: "var" + i, type: "numeric" }));
      S.rows = [];
    }
  }
  function newData() {
    S.file = null; S.title = "داده‌ی جدید";
    S.columns = [1, 2, 3, 4].map((i) => ({ name: "var" + i, type: "numeric" }));
    S.rows = Array.from({ length: 15 }, () => ["", "", "", ""]);
    S.totalRows = 0; S.truncated = false;
    setDirty(true); chip(); renderGrid();
    status("داده‌ی خالی ساخته شد — مقدارها را در جدول وارد کنید");
  }
  function addColumn() {
    ensureData();
    const name = prompt("نام متغیر جدید:", "var" + (S.columns.length + 1));
    if (!name) return;
    S.columns.push({ name: name.trim(), type: "numeric" });
    S.rows.forEach((r) => r.push(""));
    setDirty(true); renderGrid();
  }
  function exportCSV() {
    if (!S.columns.length) return status("⚠️ داده‌ای برای دانلود نیست");
    const lines = [S.columns.map((c) => csvCell(c.name)).join(",")];
    S.rows.forEach((r) => lines.push(r.map(csvCell).join(",")));
    const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (S.title || "data") + ".csv";
    a.click();
  }
  const csvCell = (v) => {
    v = String(v ?? "");
    return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  };

  /* آپلود فایل */
  $("#wbFileInput").addEventListener("change", async () => {
    const f = $("#wbFileInput").files[0];
    if (!f) return;
    status("در حال آپلود و خواندن فایل…", true);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await fetch("/api/stats/upload", { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "خطا در آپلود");
      await loadDataset(d.file, f.name);
    } catch (e) { status("⚠️ " + e.message); }
    $("#wbFileInput").value = "";
  });

  async function loadDataset(fname, title) {
    status("در حال باز کردن داده…", true);
    const r = await fetch("/api/workbench/data?file=" + encodeURIComponent(fname));
    const d = await r.json();
    if (!r.ok) { status("⚠️ " + (d.detail || "خطا در خواندن داده")); return; }
    S.file = fname; S.title = title || fname;
    S.columns = d.columns; S.rows = d.rows;
    S.totalRows = d.total_rows; S.truncated = d.truncated;
    setDirty(false); chip(); renderGrid();
    let msg = `✅ «${S.title}» باز شد — ${d.total_rows} مشاهده، ${d.columns.length} متغیر`;
    if (SW === "smartpls" && !PLS.constructs.length) {
      msg += " — حالا «🧩 ساخت مدل» را بزنید و از دکمه‌ی «🪄 ساخت خودکار سازه‌ها» شروع کنید.";
    }
    status(msg);
  }

  async function saveGrid(announce) {
    if (!S.columns.length) { status("⚠️ داده‌ای برای ذخیره نیست"); return false; }
    status("در حال ذخیره…", true);
    try {
      const r = await fetch("/api/workbench/save", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file: S.file && S.file.endsWith(".csv") ? S.file : "",
          title: S.title || "داده‌ی میزکار",
          columns: S.columns.map((c) => c.name),
          rows: S.rows,
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "خطا در ذخیره");
      S.file = d.file;
      setDirty(false);
      if (announce) status("✅ ذخیره شد");
      return true;
    } catch (e) { status("⚠️ " + e.message); return false; }
  }

  /* گشودن داده‌های من (آپلودی، میزکار، پیوست مقاله) */
  async function openDatasetPicker() {
    const r = await fetch("/api/workbench/datasets");
    const d = await r.json();
    const list = d.datasets || [];
    const body = $("#wbDlgBody");
    $("#wbDlgTitle").textContent = "Open Data — داده‌های من";
    if (!list.length) {
      body.innerHTML = `<p style="color:#667;font-size:13px">هنوز داده‌ای ندارید.
        فایل Excel/CSV/SPSS آپلود کنید، یا در گفتگوی آنتانو به مقاله داده پیوست کنید —
        همان داده این‌جا هم ظاهر می‌شود.</p>`;
    } else {
      const ic = { upload: "📤", edit: "✏️", article: "📄" };
      body.innerHTML = '<div class="wb-collist" style="max-height:300px">' +
        list.map((x) =>
          `<label data-file="${esc(x.file)}" data-title="${esc(x.title)}">
             <span>${ic[x.source] || "📄"}</span>
             <span>${esc(x.title)}</span>
             <span style="color:#99a;font-size:11px;margin-inline-start:auto">${esc(x.created || "")}</span>
           </label>`).join("") + "</div>";
      body.querySelectorAll("label[data-file]").forEach((l) =>
        l.addEventListener("click", () => {
          closeDialog();
          loadDataset(l.dataset.file, l.dataset.title);
        }));
    }
    openDialog(() => closeDialog());
  }

  /* ---------------- پنجره‌ی گفت‌وگوی تحلیل ---------------- */
  let dlgOnOk = null;
  function openDialog(onOk) {
    dlgOnOk = onOk;
    $("#wbDlgOverlay").classList.add("show");
  }
  function closeDialog() {
    $("#wbDlgOverlay").classList.remove("show");
    dlgOnOk = null;
  }
  $("#wbDlgOverlay").addEventListener("click", (e) => {
    if (e.target.id === "wbDlgOverlay" || e.target.closest("[data-close]")) closeDialog();
  });
  $("#wbDlgOk").addEventListener("click", () => { if (dlgOnOk) dlgOnOk(); });

  function colsOf(filter) {
    let cols = S.columns;
    if (filter === "numeric") {
      const n = cols.filter((c) => c.type === "numeric");
      if (n.length) cols = n;
    } else if (filter === "categorical") {
      const n = cols.filter((c) => c.type !== "numeric" || (c.unique || 99) <= 12);
      if (n.length) cols = n;
    }
    return cols.map((c) => c.name);
  }

  function openAnalysisDialog(item) {
    if (!S.columns.length) { status("⚠️ اول داده‌ای باز کنید (منوی File)"); return; }
    const fields = item.fields || [];
    if (!fields.length) return runAnalysis(item, {});
    $("#wbDlgTitle").textContent = `${item.label}  —  ${item.fa || ""}`;
    const body = $("#wbDlgBody");
    body.innerHTML = "";
    fields.forEach((f) => {
      const w = document.createElement("div");
      w.className = "wb-field";
      const hint = f.hint ? ` <span class="hint">(${esc(f.hint)})</span>` : "";
      if (f.type === "col") {
        const opts = colsOf(f.filter).map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
        w.innerHTML = `<label>${esc(f.label)}${hint}</label>
          <select data-k="${esc(f.key)}">${f.required ? "" : '<option value="">— هیچ —</option>'}${opts}</select>`;
      } else if (f.type === "cols") {
        const opts = colsOf(f.filter).map((c) =>
          `<label><input type="checkbox" value="${esc(c)}"><span class="cn">${esc(c)}</span></label>`).join("");
        w.innerHTML = `<label>${esc(f.label)}${hint}</label>
          <div class="wb-collist" data-k="${esc(f.key)}">${opts}</div>`;
      } else if (f.type === "select") {
        const opts = (f.options || []).map((o) =>
          `<option value="${esc(o[0])}" ${o[0] === f.default ? "selected" : ""}>${esc(o[1])}</option>`).join("");
        w.innerHTML = `<label>${esc(f.label)}</label><select data-k="${esc(f.key)}">${opts}</select>`;
      } else if (f.type === "number") {
        w.innerHTML = `<label>${esc(f.label)}</label>
          <input type="number" step="any" data-k="${esc(f.key)}" value="${f.default ?? ""}">`;
      } else {
        w.innerHTML = `<label>${esc(f.label)}${hint}</label>
          <input type="text" data-k="${esc(f.key)}" value="${esc(f.default ?? "")}">`;
      }
      body.appendChild(w);
    });
    openDialog(() => {
      const params = Object.assign({}, item.fixed || {});
      let bad = null;
      fields.forEach((f) => {
        const el = body.querySelector(`[data-k="${CSS.escape(f.key)}"]`);
        if (!el) return;
        if (f.type === "cols") {
          const vals = [...el.querySelectorAll("input:checked")].map((x) => x.value);
          if (vals.length) params[f.key] = vals;
          else if (f.required) bad = f.label;
        } else if (f.type === "number") {
          if (el.value !== "" && !isNaN(+el.value)) params[f.key] = +el.value;
          else if (f.required) bad = f.label;
        } else {
          if (el.value) params[f.key] = el.value;
          else if (f.required) bad = f.label;
        }
      });
      if (bad) { status(`⚠️ «${bad}» را مشخص کنید`); return; }
      closeDialog();
      runAnalysis(item, params);
    });
  }

  /* ---------------- اجرای تحلیل ---------------- */
  async function runAnalysis(item, params) {
    if (S.running) return;
    if (!S.columns.length) { status("⚠️ اول داده‌ای باز کنید"); return; }
    if (S.dirty || !S.file) {
      const ok = await saveGrid(false);
      if (!ok) return;
    }
    S.running = true;
    status(`Running ${item.label.replace(/…/g, "")} — در حال اجرا…`, true);
    try {
      const r = await fetch("/api/stats/run", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file: S.file, analysis: item.analysis, params }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "خطا در اجرا");
      if (d.result && d.result.error) {
        status("⚠️ " + d.result.error);
        S.running = false;
        return;
      }
      addOutput(item, params, d.result || {}, d.interpretation || "");
      status("✅ اجرا کامل شد — خروجی در نمایشگر خروجی");
    } catch (e) {
      status("⚠️ " + e.message);
    }
    S.running = false;
  }

  /* ---------------- نمایشگر خروجی ---------------- */
  function addOutput(item, params, result, interpretation) {
    S.outputs.push({
      label: item.label.replace(/…/g, ""), fa: item.fa || "", analysis: item.analysis,
      params, result, interpretation,
      time: new Date().toLocaleTimeString("fa-IR"),
    });
    renderOutputs();
    showOutput();
    if (SW === "smartpls" && (result["سازه‌ها"] || result.constructs)) {
      PLS.lastResult = result;
      drawCanvas();
    }
  }
  function showOutput() {
    $("#wbOutput").classList.add("show");
    const b = $("#wbOutBody");
    b.scrollTop = b.scrollHeight;
  }
  $("#wbOutput").addEventListener("click", (e) => {
    if (e.target.closest("[data-close]")) $("#wbOutput").classList.remove("show");
  });

  function renderOutputs() {
    const tree = $("#wbOutTree");
    const body = $("#wbOutBody");
    tree.innerHTML = "";
    body.innerHTML = "";
    if (!S.outputs.length) {
      body.innerHTML = "<p style='color:#889'>هنوز خروجی‌ای ساخته نشده است.</p>";
      return;
    }
    S.outputs.forEach((o, i) => {
      const n = document.createElement("div");
      n.className = "node";
      n.textContent = `${i + 1}. ${o.label}`;
      n.title = o.fa;
      n.addEventListener("click", () => {
        document.getElementById("out-" + i)?.scrollIntoView({ behavior: "smooth" });
        tree.querySelectorAll(".node").forEach((x) => x.classList.toggle("on", x === n));
      });
      tree.appendChild(n);

      const div = document.createElement("div");
      div.id = "out-" + i;
      div.className = "spss-block";
      div.appendChild(outputBlock(o));
      body.appendChild(div);
    });
  }

  function outputBlock(o) {
    const wrap = document.createElement("div");
    const h = document.createElement("h3");
    h.textContent = `${o.label} — ${o.fa}  ⌚ ${o.time}`;
    wrap.appendChild(h);

    let diagram = null;
    const res = Object.assign({}, o.result);
    if (res.diagram) { diagram = res.diagram; delete res.diagram; }

    if (SW === "eviews") {
      wrap.appendChild(eviewsHeader(o));
      const ev = document.createElement("div");
      ev.className = "ev-out";
      ev.appendChild(renderValue(res));
      wrap.appendChild(ev);
    } else {
      wrap.appendChild(renderValue(res));
    }
    if (diagram) {
      const img = document.createElement("img");
      img.src = diagram; img.alt = "نمودار";
      wrap.appendChild(img);
    }
    if (o.interpretation) {
      const d = document.createElement("div");
      d.className = "wb-interp";
      d.innerHTML = "<h3>📝 تفسیر دانشگاهی (فصل چهارم)</h3>";
      const p = document.createElement("div");
      p.textContent = o.interpretation;
      p.style.whiteSpace = "pre-wrap";
      d.appendChild(p);
      wrap.appendChild(d);
    }
    return wrap;
  }

  function eviewsHeader(o) {
    const d = document.createElement("div");
    d.className = "ev-out";
    const now = new Date();
    const lines = [
      o.params && o.params.dependent ? "Dependent Variable: " + o.params.dependent : null,
      "Method: " + o.label,
      "Date: " + now.toLocaleDateString("en-GB") + "   Time: " + now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }),
      "Sample: 1 " + (S.totalRows || S.rows.length),
      "Included observations: " + (S.totalRows || S.rows.length),
    ].filter(Boolean);
    d.innerHTML = `<div class="ev-head">${esc(lines.join("\n"))}</div>`;
    return d;
  }

  /* رندر بازگشتی نتیجه‌ی تحلیل به جدول‌های سبک نرم‌افزار */
  function isScalar(v) {
    return v === null || v === undefined ||
      ["string", "number", "boolean"].includes(typeof v);
  }
  function fmt(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "boolean") return v ? "✓" : "✗";
    if (Array.isArray(v)) return v.map(fmt).join("، ");
    return String(v);
  }
  function renderValue(v, titleText) {
    const frag = document.createElement("div");
    if (isScalar(v)) {
      const p = document.createElement("p");
      p.innerHTML = titleText ? `<b>${esc(titleText)}:</b> ${esc(fmt(v))}` : esc(fmt(v));
      frag.appendChild(p);
      return frag;
    }
    if (Array.isArray(v)) {
      if (v.length && v.every((x) => x && typeof x === "object" && !Array.isArray(x))) {
        frag.appendChild(tableFromRows(v, titleText));
        return frag;
      }
      const p = document.createElement("p");
      p.innerHTML = (titleText ? `<b>${esc(titleText)}:</b> ` : "") + esc(fmt(v));
      frag.appendChild(p);
      return frag;
    }
    // شیء
    const keys = Object.keys(v);
    const scalarKeys = keys.filter((k) => isScalar(v[k]) ||
      (Array.isArray(v[k]) && v[k].every(isScalar) && v[k].length <= 6));
    const complexKeys = keys.filter((k) => !scalarKeys.includes(k));
    if (scalarKeys.length) {
      frag.appendChild(kvTable(v, scalarKeys, titleText));
    } else if (titleText) {
      const cap = document.createElement("p");
      cap.innerHTML = `<b>${esc(titleText)}</b>`;
      frag.appendChild(cap);
    }
    complexKeys.forEach((k) => {
      frag.appendChild(renderValue(v[k], k));
    });
    return frag;
  }
  function kvTable(obj, keys, titleText) {
    const t = document.createElement("table");
    if (titleText) {
      const cap = document.createElement("caption");
      cap.textContent = titleText;
      t.appendChild(cap);
    }
    const tb = document.createElement("tbody");
    keys.forEach((k) => {
      const tr = document.createElement("tr");
      const th = document.createElement("th");
      th.textContent = k;
      const td = document.createElement("td");
      td.textContent = fmt(obj[k]);
      tr.appendChild(th); tr.appendChild(td);
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    return t;
  }
  function tableFromRows(rows, titleText) {
    const cols = [];
    rows.forEach((r) => Object.keys(r).forEach((k) => { if (!cols.includes(k)) cols.push(k); }));
    const t = document.createElement("table");
    if (titleText) {
      const cap = document.createElement("caption");
      cap.textContent = titleText;
      t.appendChild(cap);
    }
    const th = document.createElement("thead");
    th.innerHTML = "<tr>" + cols.map((c) => `<th>${esc(c)}</th>`).join("") + "</tr>";
    t.appendChild(th);
    const tb = document.createElement("tbody");
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      cols.forEach((c, i) => {
        const cell = document.createElement(i === 0 ? "td" : "td");
        if (i === 0) cell.className = "rowhead";
        const val = r[c];
        if (isScalar(val) || Array.isArray(val)) cell.textContent = fmt(val);
        else cell.appendChild(renderValue(val));
        tr.appendChild(cell);
      });
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    return t;
  }

  /* خروجی Word */
  $("#wbOutExport").addEventListener("click", async () => {
    if (!S.outputs.length) { status("⚠️ خروجی‌ای برای دانلود نیست"); return; }
    status("در حال ساخت فایل Word…", true);
    const md = S.outputs.map((o) => {
      // نمودار مسیر باید به‌صورت تصویر بیاید، نه یک ردیفِ نشانیِ فایل داخل جدول
      const res = Object.assign({}, o.result);
      const diagram = res.diagram;
      delete res.diagram;
      let s = `## ${o.label} — ${o.fa}\n\n`;
      if (diagram) s += `![نمودار مسیر مدل](${location.origin}${diagram})\n\n`;
      s += resultToMD(res);
      if (o.interpretation) s += "\n\n### تفسیر دانشگاهی\n\n" + o.interpretation;
      return s;
    }).join("\n\n---\n\n");
    try {
      const r = await fetch("/api/export", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: md, title: CFG.name + " — گزارش خروجی‌ها", formats: ["docx"] }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "خطا");
      (d.files || []).forEach((f) => window.open(f.url, "_blank"));
      status("✅ فایل Word ساخته شد");
    } catch (e) { status("⚠️ " + e.message); }
  });

  function resultToMD(v, depth) {
    depth = depth || 3;
    if (isScalar(v)) return fmt(v);
    if (Array.isArray(v)) {
      if (v.length && v.every((x) => x && typeof x === "object" && !Array.isArray(x))) {
        const cols = [];
        v.forEach((r) => Object.keys(r).forEach((k) => { if (!cols.includes(k)) cols.push(k); }));
        let s = "| " + cols.join(" | ") + " |\n|" + cols.map(() => "---").join("|") + "|\n";
        v.forEach((r) => { s += "| " + cols.map((c) => fmt(r[c]).replace(/\|/g, "،")).join(" | ") + " |\n"; });
        return s;
      }
      return fmt(v);
    }
    let out = "";
    const kv = [];
    Object.entries(v).forEach(([k, val]) => {
      if (isScalar(val) || (Array.isArray(val) && val.every(isScalar) && val.length <= 6)) {
        kv.push(`| ${k} | ${fmt(val).replace(/\|/g, "،")} |`);
      }
    });
    if (kv.length) out += "| شاخص | مقدار |\n|---|---|\n" + kv.join("\n") + "\n\n";
    Object.entries(v).forEach(([k, val]) => {
      if (!(isScalar(val) || (Array.isArray(val) && val.every(isScalar) && val.length <= 6))) {
        // خروجی Word فقط تا سه سطح سرفصل می‌شناسد؛ سطح‌های عمیق‌تر به‌جای اینکه
        // «#### نام» خام در متن بیفتند، پررنگ نوشته می‌شوند.
        out += (depth <= 3 ? "#".repeat(depth) + " " + k : "**" + k + "**") +
               "\n\n" + resultToMD(val, depth + 1) + "\n\n";
      }
    });
    return out;
  }

  /* ---------------- SmartPLS: مدل و بوم ---------------- */
  function renderIndicators() {
    const box = $("#plsIndicators");
    if (!box) return;
    const used = new Set(PLS.constructs.flatMap((c) => c.items));
    box.innerHTML = S.columns.filter((c) => c.type === "numeric").map((c) =>
      `<label><input type="checkbox" value="${esc(c.name)}" ${used.has(c.name) ? "disabled" : ""}>
       <span class="cn">${esc(c.name)}</span>${used.has(c.name) ? " ✓" : ""}</label>`).join("") ||
      "<div style='padding:8px;color:#889;font-size:12px'>ستون عددی‌ای در داده نیست</div>";
  }
  function renderModelPanel() {
    const cbox = $("#plsConstructs");
    if (!cbox) return;
    cbox.innerHTML = PLS.constructs.map((c, i) =>
      `<div class="pls-construct"><button data-del="${i}" title="حذف">🗑</button>
       <b>${esc(c.name)}</b><div class="items">${esc(c.items.join("، "))}</div></div>`).join("") ||
      "<div style='color:#889;font-size:12px'>هنوز سازه‌ای تعریف نشده</div>";
    cbox.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => {
      const c = PLS.constructs.splice(+b.dataset.del, 1)[0];
      PLS.paths = PLS.paths.filter((p) => p[0] !== c.name && p[1] !== c.name);
      renderModelPanel(); renderIndicators(); drawCanvas();
    }));
    const names = PLS.constructs.map((c) => c.name);
    const opts = names.map((n) => `<option>${esc(n)}</option>`).join("");
    $("#plsFrom").innerHTML = "<option value=''>— از سازه —</option>" + opts;
    $("#plsTo").innerHTML = "<option value=''>— به سازه —</option>" + opts;
    const pbox = $("#plsPaths");
    pbox.innerHTML = PLS.paths.map((p, i) =>
      `<div class="pls-path"><button data-delp="${i}">🗑</button>${esc(p[0])} ← ${esc(p[1])}</div>`).join("") ||
      "<div style='color:#889;font-size:12px'>مسیری تعریف نشده (اختیاری برای CFA)</div>";
    pbox.querySelectorAll("[data-delp]").forEach((b) => b.addEventListener("click", () => {
      PLS.paths.splice(+b.dataset.delp, 1);
      renderModelPanel(); drawCanvas();
    }));
  }
  $("#plsAddConstruct")?.addEventListener("click", () => {
    const name = ($("#plsNewName").value || "").trim();
    const items = [...$("#plsIndicators").querySelectorAll("input:checked")].map((x) => x.value);
    if (!name) return status("⚠️ نام سازه را بنویسید");
    if (items.length < 2) return status("⚠️ برای هر سازه دست‌کم دو گویه انتخاب کنید");
    if (PLS.constructs.some((c) => c.name === name)) return status("⚠️ سازه‌ای با این نام هست");
    PLS.constructs.push({ name, items });
    $("#plsNewName").value = "";
    renderModelPanel(); renderIndicators(); drawCanvas();
  });
  /* ---------- ساخت خودکار سازه‌ها از روی نام ستون‌ها ----------
     پرسشنامه‌ها معمولاً ستون‌هایی مثل FA1, FA2, FA3 و IA1..IA8 دارند؛ یعنی
     گویه‌های یک سازه، ریشه‌ی نامی مشترک با شماره دارند. همان قاعده‌ای که
     analysis_planner.guess_constructs در سرور دارد، این‌جا هم اجرا می‌شود تا
     کاربر مجبور نباشد ده‌ها گویه را دستی تیک بزند. */
  function guessConstructs() {
    const groups = {};
    S.columns.filter((c) => c.type === "numeric").forEach((c) => {
      const m = String(c.name).trim().match(/^(.*?)[\s_\-]*(\d+)$/);
      if (!m) return;
      const stem = m[1].replace(/^[\s_-]+|[\s_-]+$/g, "");
      if (!stem) return;
      (groups[stem] = groups[stem] || []).push({ name: c.name, num: +m[2] });
    });
    const out = [];
    Object.entries(groups).forEach(([stem, items]) => {
      if (items.length < 2) return;                     // سازه دست‌کم دو گویه دارد
      items.sort((a, b) => a.num - b.num);
      out.push({ name: stem, items: items.map((i) => i.name) });
    });
    return out;
  }

  $("#plsAuto")?.addEventListener("click", () => {
    if (!S.columns.length) {
      status("⚠️ اول داده‌ای باز کنید (دکمه‌ی «داده‌های من» یا «آپلود فایل»)");
      return;
    }
    const found = guessConstructs();
    if (!found.length) {
      status("⚠️ از روی نام ستون‌ها سازه‌ای پیدا نشد — گویه‌های هر سازه باید نام مشترک و شماره داشته باشند (مثل A1, A2, A3). دستی بسازید.");
      return;
    }
    const fresh = found.filter((f) => !PLS.constructs.some((c) => c.name === f.name));
    if (!fresh.length) {
      status("همه‌ی سازه‌های قابل تشخیص از قبل ساخته شده‌اند.");
      return;
    }
    const list = fresh.map((f) => `• ${f.name} (${f.items.length} گویه: ${f.items.join("، ")})`).join("\n");
    if (!confirm(`آنتانو این سازه‌ها را از روی نام ستون‌ها پیدا کرد:\n\n${list}\n\nساخته شوند؟`)) return;
    fresh.forEach((f) => PLS.constructs.push(f));
    renderModelPanel(); renderIndicators(); drawCanvas();
    status(`✅ ${fresh.length} سازه ساخته شد. حالا در بخش «مسیرها» تعیین کنید کدام سازه روی کدام اثر می‌گذارد، بعد PLS Algorithm را بزنید.`);
    $("#plsHelp")?.removeAttribute("open");
  });

  $("#plsAddPath")?.addEventListener("click", () => {
    const a = $("#plsFrom").value, b = $("#plsTo").value;
    if (!a || !b || a === b) return status("⚠️ دو سازه‌ی متفاوت انتخاب کنید");
    if (PLS.paths.some((p) => p[0] === a && p[1] === b)) return;
    PLS.paths.push([a, b]);
    renderModelPanel(); drawCanvas();
  });

  function plsLevels() {
    const lv = {};
    PLS.constructs.forEach((c) => { lv[c.name] = 0; });
    for (let i = 0; i < 6; i++) {
      PLS.paths.forEach(([a, b]) => {
        if (lv[b] !== undefined && lv[a] !== undefined && lv[b] <= lv[a]) lv[b] = lv[a] + 1;
      });
    }
    return lv;
  }
  function drawCanvas() {
    const svg = $("#plsCanvas");
    if (!svg) return;
    const NS = "http://www.w3.org/2000/svg";
    svg.innerHTML = "";
    if (!PLS.constructs.length) {
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", 60); t.setAttribute("y", 60);
      t.setAttribute("fill", "#99a"); t.setAttribute("font-size", "15");
      t.textContent = "از پنل کنار، سازه‌ها و مسیرها را تعریف کنید — مدل این‌جا رسم می‌شود";
      svg.appendChild(t);
      return;
    }
    // نشانگر پیکان
    svg.innerHTML = `<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5"
      markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#345"/></marker></defs>`;
    const lv = plsLevels();
    const byLevel = {};
    PLS.constructs.forEach((c) => {
      (byLevel[lv[c.name]] = byLevel[lv[c.name]] || []).push(c);
    });
    const pos = {};
    Object.keys(byLevel).sort((a, b) => a - b).forEach((L) => {
      byLevel[L].forEach((c, i) => {
        const def = { x: 260 + L * 300, y: 130 + i * 190 };
        pos[c.name] = PLS.pos[c.name] || def;
      });
    });
    const res = PLS.lastResult || {};
    const loadings = {};
    const cres = res["سازه‌ها"] || {};
    Object.entries(cres).forEach(([n, info]) => {
      Object.assign(loadings[n] = {}, info["بارهای عاملی"] || {});
    });
    const r2 = {};
    (res["R2"] || []).forEach((row) => {
      const name = row["سازه درون‌زا"] || row["سازه"] || Object.values(row)[0];
      const val = row["R2"] ?? row["R²"];
      if (name != null && val != null) r2[name] = val;
    });
    const beta = {};
    (res["مسیرهای ساختاری"] || []).forEach((row) => {
      const m = String(row["مسیر"] || "").split("→").map((s) => s.trim());
      if (m.length === 2) beta[m[0] + "|" + m[1]] = row;
    });

    // مسیرهای ساختاری
    PLS.paths.forEach(([a, b]) => {
      if (!pos[a] || !pos[b]) return;
      const l = document.createElementNS(NS, "line");
      l.setAttribute("x1", pos[a].x + 62); l.setAttribute("y1", pos[a].y);
      l.setAttribute("x2", pos[b].x - 66); l.setAttribute("y2", pos[b].y);
      l.setAttribute("stroke", "#345"); l.setAttribute("stroke-width", "1.6");
      l.setAttribute("marker-end", "url(#arr)");
      svg.appendChild(l);
      const info = beta[a + "|" + b];
      if (info) {
        const t = document.createElementNS(NS, "text");
        t.setAttribute("x", (pos[a].x + pos[b].x) / 2);
        t.setAttribute("y", (pos[a].y + pos[b].y) / 2 - 8);
        t.setAttribute("text-anchor", "middle");
        t.setAttribute("font-size", "12"); t.setAttribute("fill", "#0b3d91");
        t.setAttribute("font-weight", "700");
        let txt = String(info["ضریب استاندارد (β)"] ?? "");
        if (info.p !== undefined && info.p !== null) txt += info.p < 0.001 ? "***" : info.p < 0.01 ? "**" : info.p < 0.05 ? "*" : "";
        t.textContent = txt;
        svg.appendChild(t);
      }
    });

    // سازه‌ها و گویه‌ها
    PLS.constructs.forEach((c) => {
      const p = pos[c.name];
      // گویه‌ها (مستطیل‌های زرد، سبک SmartPLS)
      c.items.forEach((it, i) => {
        const iy = p.y - ((c.items.length - 1) * 34) / 2 + i * 34;
        const ix = p.x - 205;
        const rect = document.createElementNS(NS, "rect");
        rect.setAttribute("x", ix); rect.setAttribute("y", iy - 12);
        rect.setAttribute("width", 95); rect.setAttribute("height", 24);
        rect.setAttribute("fill", "#ffdd57"); rect.setAttribute("stroke", "#b8962e");
        rect.setAttribute("rx", 3);
        svg.appendChild(rect);
        const tx = document.createElementNS(NS, "text");
        tx.setAttribute("x", ix + 47); tx.setAttribute("y", iy + 4);
        tx.setAttribute("text-anchor", "middle"); tx.setAttribute("font-size", "11");
        tx.textContent = it.length > 12 ? it.slice(0, 11) + "…" : it;
        svg.appendChild(tx);
        const ln = document.createElementNS(NS, "line");
        ln.setAttribute("x1", ix + 95); ln.setAttribute("y1", iy);
        ln.setAttribute("x2", p.x - 62); ln.setAttribute("y2", p.y);
        ln.setAttribute("stroke", "#888"); ln.setAttribute("stroke-width", "1");
        svg.appendChild(ln);
        const load = loadings[c.name] && loadings[c.name][it];
        if (load !== undefined) {
          const lt = document.createElementNS(NS, "text");
          lt.setAttribute("x", (ix + 95 + p.x - 62) / 2);
          lt.setAttribute("y", (iy + p.y) / 2 - 4);
          lt.setAttribute("font-size", "10.5"); lt.setAttribute("fill", "#7a5b00");
          lt.setAttribute("text-anchor", "middle");
          lt.textContent = load;
          svg.appendChild(lt);
        }
      });
      // بیضی سازه (آبی، سبک SmartPLS)
      const g = document.createElementNS(NS, "g");
      g.style.cursor = "move";
      const el = document.createElementNS(NS, "ellipse");
      el.setAttribute("cx", p.x); el.setAttribute("cy", p.y);
      el.setAttribute("rx", 62); el.setAttribute("ry", 34);
      el.setAttribute("fill", "#2f7ed8"); el.setAttribute("stroke", "#1a4f8f");
      el.setAttribute("stroke-width", "1.5");
      g.appendChild(el);
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", p.x); t.setAttribute("y", p.y + (r2[c.name] !== undefined ? -2 : 4));
      t.setAttribute("text-anchor", "middle"); t.setAttribute("fill", "#fff");
      t.setAttribute("font-size", "12.5"); t.setAttribute("font-weight", "700");
      t.textContent = c.name.length > 14 ? c.name.slice(0, 13) + "…" : c.name;
      g.appendChild(t);
      if (r2[c.name] !== undefined) {
        const rt = document.createElementNS(NS, "text");
        rt.setAttribute("x", p.x); rt.setAttribute("y", p.y + 15);
        rt.setAttribute("text-anchor", "middle"); rt.setAttribute("fill", "#dceaff");
        rt.setAttribute("font-size", "11");
        rt.textContent = "R² = " + r2[c.name];
        g.appendChild(rt);
      }
      // جابه‌جایی سازه با ماوس یا انگشت. چون بوم برای جاشدن در صفحه مقیاس
      // می‌خورد، جابه‌جاییِ صفحه باید به مقیاسِ خودِ بوم تبدیل شود.
      g.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        const box = svg.getBoundingClientRect();
        const vb = svg.viewBox.baseVal;
        const scale = (vb && vb.width && box.width) ? vb.width / box.width : 1;
        const sx = e.clientX, sy = e.clientY, ox = p.x, oy = p.y;
        const move = (ev) => {
          PLS.pos[c.name] = { x: ox + (ev.clientX - sx) * scale,
                              y: oy + (ev.clientY - sy) * scale };
          drawCanvas();
        };
        const up = () => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
          window.removeEventListener("pointercancel", up);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
        window.addEventListener("pointercancel", up);
      });
      svg.appendChild(g);
    });

    // بوم دقیقاً به اندازه‌ی مدل تنظیم می‌شود و روی صفحه‌های باریک کوچک می‌شود
    // تا کلِ مدل یک‌جا دیده شود (قبلاً روی گوشی بخشی از مدل بیرون از کادر می‌ماند).
    fitCanvas(svg);
  }

  function fitCanvas(svg) {
    let bb;
    try { bb = svg.getBBox(); } catch (e) { return; }
    if (!bb || !bb.width) return;
    const pad = 28;
    const x = bb.x - pad, y = bb.y - pad;
    const w = bb.width + pad * 2, h = bb.height + pad * 2;
    svg.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    svg.style.width = "100%";
    svg.style.maxWidth = Math.round(w) + "px";
    svg.style.height = "auto";
    svg.style.margin = "0 auto";
    svg.style.display = "block";
  }

  function plsFactors() {
    const f = {};
    PLS.constructs.forEach((c) => { f[c.name] = c.items; });
    return f;
  }
  async function runPLS(bootstrap) {
    if (!PLS.constructs.length) {
      status("⚠️ اول در پنل کنار، سازه‌ها و گویه‌هایشان را تعریف کنید");
      $("#plsPanel")?.classList.add("show");
      return;
    }
    const item = {
      label: bootstrap ? "Bootstrapping" : "PLS-SEM Algorithm",
      fa: bootstrap ? `بوت‌استرپ (${bootstrap} نمونه)` : "الگوریتم PLS",
      analysis: "pls_sem",
    };
    await runAnalysis(item, {
      factors: plsFactors(),
      structural: PLS.paths.length ? PLS.paths : undefined,
      bootstrap: bootstrap || 0,
    });
  }
  async function runCFA() {
    if (!PLS.constructs.length) {
      status("⚠️ اول سازه‌ها را تعریف کنید");
      return;
    }
    await runAnalysis(
      { label: "Confirmatory Factor Analysis", fa: "تحلیل عاملی تأییدی", analysis: "sem_cfa" },
      { factors: plsFactors() });
  }

  /* ---------------- شروع ---------------- */
  buildMenus();
  renderGrid();
  renderModelPanel && $("#plsConstructs") && renderModelPanel();
  chip();
  status();

  // اگر داده‌ای هست، فهرست را پیش‌بگیر تا «داده‌های من» سریع باز شود
  fetch("/api/workbench/datasets").catch(() => {});
})();
