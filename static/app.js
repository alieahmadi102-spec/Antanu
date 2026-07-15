/* app.js — منطق صفحه چت آنتانو (چندمدلی + فایل + میکروفون + جستجوی وب + صدا) */

const $ = s => document.querySelector(s);
const msgsEl = $("#messages");
const inputEl = $("#input");
const sendBtn = $("#send");
const convListEl = $("#convList");

let currentConv = null;
let sending = false;
let attachments = [];              // فایل‌های پیوست: {id, filename}
let webOn = false;                 // جستجوی وب
let researchOn = false;            // تحقیق گروهی
let abortCtrl = null;              // کنترل توقف استریم
let models = [];                   // فهرست مدل‌ها از سرور
let selected = JSON.parse(localStorage.getItem("antanu_models") || '["auto"]');

marked.setOptions({ breaks: true, gfm: true });

const WELCOME_HTML = `
  <div id="welcome">
    <img src="/static/logo.png" class="logo-lg" alt="ANTANU" width="110" height="110" style="width:110px;height:110px;border-radius:50%">
    <h2>سلام! من آنتانو هستم</h2>
    <p>دستیار هوشمند فارسی‌زبان شما. سؤال بپرسید، فایل بفرستید،
    با میکروفون صحبت کنید یا چند هوش مصنوعی را همزمان به کار بگیرید.</p>
    <div class="sugg">
      <button class="sug" data-q="یک مقاله کوتاه درباره تأثیر هوش مصنوعی بر آموزش بنویس">✍️ مقاله درباره هوش مصنوعی</button>
      <button class="sug" data-q="آزمون تی مستقل را با یک مثال ساده توضیح بده">📊 آموزش آزمون آماری</button>
      <button class="sug" data-q="قیمت دلار امروز چند است؟">🌐 قیمت دلار امروز</button>
      <button class="sug" data-q="یک برنامه مطالعه یک‌ماهه برای امتحانات برایم بچین">🗓 برنامه مطالعه</button>
    </div>
  </div>`;

/* ---------- ابزارها ---------- */

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function renderMD(text) {
  // عکس‌های تولیدشده با نشانه ویژه می‌آیند تا خرابی مارک‌داون (بک‌تیک و...) رویشان اثر نکند
  const imgs = [];
  const cleaned = (text || "").replace(/\[\[ANTANU_IMG:([^\]\s]+)\]\]/g, (m, u) => {
    if (u.startsWith("/download/")) imgs.push(u);
    return "";
  });
  let html = "";
  // اگر همراه عکس فقط خرده‌ریز (بک‌تیک، پرانتز، علائم) آمده، متن را نمایش نده
  const meaningful = cleaned.replace(/[`'"()\[\]{}\s.,،:؛!؟\-_*#>~|=+]/g, "");
  if (!imgs.length || meaningful.length > 2) {
    html = DOMPurify.sanitize(marked.parse(cleaned));
  }
  for (const u of imgs) {
    html += `<img src="${u}" class="gen-img" loading="lazy" alt="تصویر تولیدشده">`;
  }
  return html;
}

let toastTimer = null;
function toast(msg) {
  let t = $("#toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; document.body.appendChild(t); }
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2400);
}
function el(html) { const d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; }

/* ---------- انتخابگر مدل‌ها ---------- */

async function loadModels() {
  const r = await fetch("/api/models");
  if (!r.ok) return;
  models = await r.json();
  const list = $("#modelList");
  list.innerHTML = "";
  // اگر انتخاب ذخیره‌شده معتبر نیست، برگرد به پیش‌فرض
  selected = selected.filter(id => models.some(m => m.id === id));
  if (!selected.length) selected = [models[0].id];

  models.forEach(m => {
    const item = el(`<div class="model-item">
      <input type="checkbox" value="${m.id}" ${selected.includes(m.id) ? "checked" : ""} title="افزودن به انتخاب چندتایی">
      <span class="mname" data-id="${m.id}">${escapeHtml(m.name)}</span>
    </div>`);
    list.appendChild(item);
  });
  updateModelUI();
}

/* حالت کشویی: کلیک روی «نام» مدل = فقط همان انتخاب می‌شود و منو بسته می‌شود
   تیک‌زدن چک‌باکس = انتخاب چندتایی */
$("#modelList").addEventListener("click", e => {
  const nameEl = e.target.closest(".mname");
  if (!nameEl) return;
  selected = [nameEl.dataset.id];
  document.querySelectorAll("#modelList input").forEach(i => (i.checked = i.value === nameEl.dataset.id));
  updateModelUI();
  $("#modelPanel").classList.remove("show");
  toast("مدل انتخاب شد: " + nameEl.textContent);
});

function updateModelUI() {
  localStorage.setItem("antanu_models", JSON.stringify(selected));
  const label = $("#modelLabel");
  if (selected.length === models.length && models.length > 1) label.textContent = `همه (${models.length} مدل)`;
  else if (selected.length === 1) label.textContent = models.find(m => m.id === selected[0])?.name || "مدل";
  else label.textContent = `${selected.length} مدل انتخاب شده`;
  $("#modelAll").checked = selected.length === models.length;
}

$("#modelBtn").addEventListener("click", e => {
  e.stopPropagation();
  $("#modelPanel").classList.toggle("show");
});
document.addEventListener("click", e => {
  if (!e.target.closest(".model-wrap")) $("#modelPanel").classList.remove("show");
});
$("#modelPanel").addEventListener("change", e => {
  if (e.target.id === "modelAll") {
    selected = e.target.checked ? models.map(m => m.id) : [models[0].id];
    document.querySelectorAll("#modelList input").forEach(i => (i.checked = selected.includes(i.value)));
  } else if (e.target.value) {
    selected = [...document.querySelectorAll("#modelList input:checked")].map(i => i.value);
    if (!selected.length) { selected = [models[0].id]; e.target.checked = e.target.value === models[0].id; }
  }
  updateModelUI();
});

/* ---------- پیوست فایل ---------- */

$("#attachBtn").addEventListener("click", () => $("#fileInput").click());

$("#fileInput").addEventListener("change", async e => {
  for (const file of e.target.files) {
    const chip = el(`<span class="chip">⏳ ${escapeHtml(file.name)}</span>`);
    $("#chips").appendChild(chip);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        chip.remove();
        toast(err.detail || "خطا در آپلود فایل");
        continue;
      }
      const data = await r.json();
      attachments.push({ id: data.id, filename: data.filename, kind: data.kind, preview: data.preview });
      if (data.kind === "image" && data.preview) {
        chip.innerHTML = `<img src="${data.preview}" class="chip-thumb"> ${escapeHtml(data.filename)} <b class="x">✕</b>`;
      } else {
        chip.innerHTML = `📎 ${escapeHtml(data.filename)} <b class="x">✕</b>`;
      }
      chip.querySelector(".x").addEventListener("click", () => {
        attachments = attachments.filter(a => a.id !== data.id);
        chip.remove();
      });
    } catch { chip.remove(); toast("خطا در آپلود فایل"); }
  }
  e.target.value = "";
});

function clearChips() { attachments = []; $("#chips").innerHTML = ""; }

/* ---------- جستجوی وب ---------- */

$("#webBtn").addEventListener("click", () => {
  webOn = !webOn;
  $("#webBtn").classList.toggle("on", webOn);
  toast(webOn ? "جستجوی وب روشن شد 🌐" : "جستجوی وب خاموش شد");
});

/* ---------- میکروفون (تبدیل گفتار به متن) ---------- */

let recog = null, recording = false;
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

let micBase = "";
let micManualStop = false;

/* حذف کلمات تکراری پشت‌سرهم (باگ معروف کروم اندروید: «سلام سلام سلام») */
function dedupeWords(s) {
  const out = [];
  for (const w of s.split(/\s+/)) {
    if (w && w !== out[out.length - 1]) out.push(w);
  }
  return out.join(" ");
}

$("#micBtn").addEventListener("click", () => {
  if (!SR) { toast("مرورگر شما میکروفون را پشتیبانی نمی‌کند (از Chrome استفاده کنید)"); return; }
  if (recording) { micManualStop = true; recog.stop(); return; }

  recog = new SR();
  recog.lang = "fa-IR";
  recog.interimResults = true;
  recog.continuous = true;
  micManualStop = false;
  micBase = inputEl.value.trim();

  recog.onresult = ev => {
    // هر بار کل متن از صفر ساخته می‌شود (نه افزودنی) → تکرار غیرممکن
    let finals = "", interim = "";
    for (let i = 0; i < ev.results.length; i++) {
      const r = ev.results[i];
      if (r.isFinal) finals += r[0].transcript + " ";
      else interim += r[0].transcript + " ";
    }
    inputEl.value = dedupeWords((micBase ? micBase + " " : "") + finals + interim);
    autosize();
  };
  recog.onstart = () => {
    recording = true;
    $("#micBtn").classList.add("rec");
    toast("🎤 در حال شنیدن… برای پایان دوباره روی میکروفون بزنید");
  };
  recog.onend = () => {
    // ادامه خودکار تا کاربر خودش قطع کند (ضبط طولانی تا ~۱ ساعت)
    if (recording && !micManualStop) {
      micBase = inputEl.value.trim();
      try { recog.start(); return; } catch {}
    }
    recording = false;
    $("#micBtn").classList.remove("rec");
  };
  recog.onerror = ev => {
    if ((ev.error === "no-speech" || ev.error === "network") && recording && !micManualStop) return;
    recording = false;
    $("#micBtn").classList.remove("rec");
  };
  recog.start();
});

/* ---------- خواندن پاسخ با صدا ---------- */

let speaking = false;
function detectLang(text) {
  // تشخیص ساده زبان از روی نویسه‌ها
  if (/[\u0600-\u06FF]/.test(text)) {
    // فارسی یا عربی — تفکیک با واژه‌های پرتکرار فارسی
    if (/[پچژگ]|است|می‌|های|این|را\b/.test(text)) return "fa-IR";
    return "ar-SA";
  }
  if (/[\u0400-\u04FF]/.test(text)) return "ru-RU";
  if (/[\u4E00-\u9FFF]/.test(text)) return "zh-CN";
  if (/[a-zA-Z]/.test(text)) return "en-US";
  return "fa-IR";
}

function speak(text) {
  if (!window.speechSynthesis) { toast("مرورگر شما پخش صدا را پشتیبانی نمی‌کند"); return; }
  if (speaking) { speechSynthesis.cancel(); speaking = false; return; }
  const plain = text.replace(/[#*_`>\[\]()-]/g, " ").replace(/\s+/g, " ").trim();
  const lang = detectLang(plain);
  const u = new SpeechSynthesisUtterance(plain.slice(0, 3000));
  u.lang = lang;
  const voices = speechSynthesis.getVoices();
  const match = voices.find(v => v.lang === lang) || voices.find(v => v.lang.startsWith(lang.split("-")[0]));
  if (match) u.voice = match;
  u.onend = () => (speaking = false);
  speaking = true;
  speechSynthesis.speak(u);
}

/* ---------- نمایش پیام‌ها ---------- */

function addMsg(role, content) {
  const w = $("#welcome");
  if (w) w.remove();

  const isUser = role === "user";
  const div = el(`
    <div class="msg ${role}">
      <div class="avatar">${isUser
        ? (window.USER_AVATAR ? `<img src="${window.USER_AVATAR}" alt="" style="width:100%;height:100%;border-radius:9px;object-fit:cover">` : "👤")
        : `<img src="/static/logo.png" alt="" style="width:100%;height:100%;border-radius:9px;object-fit:cover">`}</div>
      <div class="bubble">
        <div class="md"></div>
        <div class="actions">
          <button class="act copy">📋 کپی</button>
          <button class="act share">↗️ اشتراک‌گذاری</button>
          ${isUser ? "" : '<button class="act voice">🔊 خواندن</button><button class="act export">📄 خروجی</button><button class="act regen">🔄 دوباره</button><button class="act cont">⤵️ ادامه</button>'}
        </div>
      </div>
    </div>`);

  div.dataset.raw = content;
  const md = div.querySelector(".md");
  if (isUser) md.textContent = content;
  else md.innerHTML = renderMD(content);

  msgsEl.appendChild(div);
  msgsEl.scrollTop = msgsEl.scrollHeight;
  return div;
}

msgsEl.addEventListener("click", async e => {
  const msg = e.target.closest(".msg");
  if (!msg) return;
  const raw = msg.dataset.raw || "";

  if (e.target.classList.contains("copy")) {
    try { await navigator.clipboard.writeText(raw); toast("متن کپی شد ✅"); }
    catch { toast("کپی انجام نشد"); }
  }
  if (e.target.classList.contains("share")) {
    if (navigator.share) { try { await navigator.share({ title: "پاسخ آنتانو", text: raw }); } catch {} }
    else { try { await navigator.clipboard.writeText(raw); toast("متن کپی شد؛ در رسانه موردنظر جای‌گذاری کنید"); } catch {} }
  }
  if (e.target.classList.contains("voice")) speak(raw);
  if (e.target.classList.contains("export")) openDocOverlay("export", raw, msg);
  if (e.target.classList.contains("regen")) {
    let prev = msg.previousElementSibling;
    while (prev && !prev.classList.contains("user")) prev = prev.previousElementSibling;
    const q = (prev?.dataset.raw || "")
      .split("\n").filter(l => !l.startsWith("📎") && !l.startsWith("🌐")).join("\n").trim();
    if (q) send(q);
    else toast("پیامی برای تولید دوباره پیدا نشد");
  }
  if (e.target.classList.contains("cont")) {
    send("ادامه بده — دقیقاً از همان‌جا که پاسخ قبلی تمام شد، بدون تکرار مطالب قبلی ادامه بده و کامل کن.");
  }
  if (e.target.classList.contains("sug")) {
    inputEl.value = e.target.dataset.q || e.target.textContent.replace(/^[^ ]+ /, "");
    autosize();
    send();
  }
});

/* ---------- لیست گفتگوها ---------- */

async function loadConvs() {
  const r = await fetch("/api/conversations");
  if (r.status === 401) { location.href = "/login"; return; }
  const list = await r.json();
  convListEl.innerHTML = "";
  list.forEach(c => {
    const item = el(`
      <div class="conv ${c.id === currentConv ? "active" : ""}" data-id="${c.id}">
        <span class="t">${escapeHtml(c.title || "گفتگوی بدون عنوان")}</span>
        <button class="ren" title="تغییر نام">✏️</button>
        <button class="del" title="حذف گفتگو">🗑</button>
      </div>`);
    convListEl.appendChild(item);
  });
  if (typeof filterConvs === "function") filterConvs();
}

convListEl.addEventListener("click", async e => {
  const item = e.target.closest(".conv");
  if (!item) return;
  const id = Number(item.dataset.id);
  if (e.target.classList.contains("ren")) {
    const cur = item.querySelector(".t").textContent;
    const name = prompt("نام جدید گفتگو:", cur);
    if (name && name.trim() && name.trim() !== cur) {
      await fetch(`/api/conversations/${id}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: name.trim() }),
      });
      loadConvs();
      toast("نام گفتگو تغییر کرد ✏️");
    }
    return;
  }
  if (e.target.classList.contains("del")) {
    if (confirm("این گفتگو برای همیشه حذف شود؟")) {
      await fetch("/api/conversations/" + id, { method: "DELETE" });
      if (currentConv === id) { currentConv = null; msgsEl.innerHTML = WELCOME_HTML; }
      loadConvs();
    }
    return;
  }
  openConv(id);
});

async function openConv(id) {
  currentConv = id;
  const r = await fetch(`/api/conversations/${id}/messages`);
  if (!r.ok) return;
  const msgs = await r.json();
  msgsEl.innerHTML = "";
  msgs.forEach(m => addMsg(m.role, m.content));
  msgsEl.scrollTop = msgsEl.scrollHeight;
  loadConvs();
  closeSidebar();
}

$("#newChat").addEventListener("click", () => {
  currentConv = null;
  msgsEl.innerHTML = WELCOME_HTML;
  loadConvs();
  closeSidebar();
  inputEl.focus();
});

/* ---------- ارسال پیام و دریافت استریم ---------- */

async function send(textOverride) {
  if (sending) return;
  const text = (typeof textOverride === "string" ? textOverride : inputEl.value).trim();
  if (!text) return;

  sending = true;
  sendBtn.disabled = true;
  inputEl.value = "";
  autosize();

  let displayText = text;
  if (webOn) displayText += "\n🌐 با جستجوی وب";
  const userDiv = addMsg("user", displayText);
  // نمایش عکس‌ها و فایل‌ها داخل حباب پیام
  if (attachments.length) {
    const media = document.createElement("div");
    media.className = "msg-media";
    attachments.forEach(a => {
      if (a.kind === "image" && a.preview) {
        const im = document.createElement("img");
        im.src = a.preview; im.className = "msg-img"; im.title = a.filename;
        media.appendChild(im);
      } else {
        const f = document.createElement("span");
        f.className = "msg-file"; f.textContent = "📎 " + a.filename;
        media.appendChild(f);
      }
    });
    userDiv.querySelector(".bubble").insertBefore(media, userDiv.querySelector(".actions"));
  }

  const payload = {
    conversation_id: currentConv,
    message: text,
    models: selected,
    web: webOn,
    research: researchOn,
    attachments: attachments.map(a => a.id),
  };
  clearChips();

  const aDiv = addMsg("assistant", "");
  const mdEl = aDiv.querySelector(".md");
  mdEl.innerHTML = '<span class="typing">آنتانو در حال فکر کردن است</span>';

  abortCtrl = new AbortController();
  setStopMode(true);

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: abortCtrl.signal,
    });

    if (resp.status === 401) { location.href = "/login"; return; }
    if (!resp.ok) {
      const e2 = await resp.json().catch(() => ({}));
      const msg = "⚠️ " + (e2.detail || "خطایی رخ داد.");
      mdEl.innerHTML = renderMD(msg);
      aDiv.dataset.raw = msg;
      return;
    }

    const isNew = !currentConv;
    const cid = resp.headers.get("X-Conversation-Id");
    if (cid) currentConv = Number(cid);

    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let full = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      full += dec.decode(value, { stream: true });
      mdEl.innerHTML = renderMD(full);
      aDiv.dataset.raw = full;
      msgsEl.scrollTop = msgsEl.scrollHeight;
    }
    if (isNew) loadConvs();
  } catch (err) {
    if (err.name === "AbortError") {
      const cur = aDiv.dataset.raw || "";
      aDiv.dataset.raw = cur + "\n\n⏹ متوقف شد.";
      mdEl.innerHTML = renderMD(aDiv.dataset.raw);
    } else {
      mdEl.innerHTML = renderMD("⚠️ ارتباط با سرور قطع شد. دوباره تلاش کنید.");
    }
  } finally {
    sending = false;
    abortCtrl = null;
    setStopMode(false);
    inputEl.focus();
  }
}

sendBtn.addEventListener("click", () => {
  if (sending) { stopStreaming(); return; }
  send();
});
inputEl.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});

function autosize() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
}

function setStopMode(on) {
  if (on) {
    sendBtn.innerHTML = "■";
    sendBtn.title = "توقف";
    sendBtn.classList.add("stop");
    sendBtn.disabled = false;
  } else {
    sendBtn.innerHTML = "➤";
    sendBtn.title = "ارسال";
    sendBtn.classList.remove("stop");
    sendBtn.disabled = false;
  }
}

function stopStreaming() {
  if (abortCtrl) { abortCtrl.abort(); abortCtrl = null; }
}
inputEl.addEventListener("input", autosize);

/* ---------- پنجره حافظه ---------- */

$("#memBtn")?.addEventListener("click", async e => {
  e.preventDefault();
  const overlay = $("#memOverlay");
  const listEl = overlay.querySelector(".mem-list");
  listEl.innerHTML = '<div class="mem-empty">در حال بارگذاری…</div>';
  overlay.classList.add("show");
  const r = await fetch("/api/memories");
  const mems = await r.json();
  if (!mems.length) {
    listEl.innerHTML = '<div class="mem-empty">حافظه خالی است. با دکمه «حافظه» زیر هر پیام، مطالب مهم را ماندگار کنید.</div>';
    return;
  }
  listEl.innerHTML = "";
  mems.forEach(m => {
    const item = el(`
      <div class="mem-item" data-id="${m.id}">
        <span>${escapeHtml(m.content.length > 180 ? m.content.slice(0, 180) + "…" : m.content)}</span>
        <button title="حذف از حافظه">حذف</button>
      </div>`);
    item.querySelector("button").addEventListener("click", async () => {
      await fetch("/api/memories/" + m.id, { method: "DELETE" });
      item.remove();
      toast("از حافظه حذف شد");
    });
    listEl.appendChild(item);
  });
});

$("#memOverlay")?.addEventListener("click", e => {
  if (e.target.id === "memOverlay" || e.target.classList.contains("close")) {
    $("#memOverlay").classList.remove("show");
  }
});

/* ---------- منوی موبایل ---------- */

function closeSidebar() {
  $("#sidebar").classList.remove("open");
  $("#sideBackdrop")?.classList.remove("show");
}
$("#menuBtn").addEventListener("click", () => {
  $("#sidebar").classList.toggle("open");
  $("#sideBackdrop")?.classList.toggle("show");
});
$("#sideBackdrop")?.addEventListener("click", closeSidebar);

/* ---------- خروجی کل گفتگو ---------- */

$("#convExportBtn").addEventListener("click", e => {
  e.preventDefault();
  const parts = [...msgsEl.querySelectorAll(".msg")].map(m => {
    const who = m.classList.contains("user") ? "## 👤 کاربر" : "## 🤖 آنتانو";
    return who + "\n\n" + (m.dataset.raw || "");
  });
  if (!parts.length) { toast("گفتگویی برای خروجی وجود ندارد"); return; }
  closeSidebar();
  openDocOverlay("export", parts.join("\n\n"), null);
});

/* ---------- تحقیق گروهی ---------- */

$("#researchBtn").addEventListener("click", () => {
  researchOn = !researchOn;
  $("#researchBtn").classList.toggle("on", researchOn);
  toast(researchOn
    ? "🔬 تحقیق گروهی روشن شد — همه هوش مصنوعی‌ها + جستجوی وب باهم پژوهش می‌کنند"
    : "تحقیق گروهی خاموش شد");
});

/* ---------- پنجره سند: مقاله بلند / خروجی پاسخ ---------- */

let docMode = "longdoc";
let exportContent = "";
let exportMsgEl = null;
let docAttachments = [];           // منابع پنجره مقاله بلند

function openDocOverlay(mode, content = "", msgEl = null) {
  docMode = mode;
  exportContent = content;
  exportMsgEl = msgEl;
  const isExport = mode === "export";
  $("#docTitle").textContent = isExport ? "📄 خروجی (Word / PDF / Excel)" : "📄 ساخت مقاله بلند";
  $("#topicField").style.display = isExport ? "none" : "block";
  $("#pagesField").style.display = isExport ? "none" : "block";
  $("#docSrcField").style.display = isExport ? "none" : "block";
  $("#docHint").style.display = isExport ? "none" : "block";
  $("#docStart").textContent = isExport ? "ساخت فایل" : "شروع ساخت";
  $("#docOverlay").classList.add("show");
}

/* آپلود منابع پنجره مقاله بلند */
$("#docAttachBtn").addEventListener("click", () => $("#docFileInput").click());
$("#docFileInput").addEventListener("change", async e => {
  for (const file of e.target.files) {
    const chip = el(`<span class="chip">⏳ ${escapeHtml(file.name)}</span>`);
    $("#docChips").appendChild(chip);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        chip.remove();
        toast(err.detail || "خطا در آپلود");
        continue;
      }
      const data = await r.json();
      docAttachments.push({ id: data.id, filename: data.filename });
      const icon = data.kind === "image" ? "🖼" : "📎";
      chip.innerHTML = `${icon} ${escapeHtml(data.filename)} <b class="x">✕</b>`;
      chip.querySelector(".x").addEventListener("click", () => {
        docAttachments = docAttachments.filter(a => a.id !== data.id);
        chip.remove();
      });
    } catch { chip.remove(); toast("خطا در آپلود"); }
  }
  e.target.value = "";
});

$("#docBtn").addEventListener("click", () => openDocOverlay("longdoc"));

$("#docOverlay").addEventListener("click", e => {
  if (e.target.id === "docOverlay" || e.target.classList.contains("close"))
    $("#docOverlay").classList.remove("show");
});

function docFormats() {
  const v = $("#docFormat").value;
  if (v === "both") return ["docx", "pdf"];
  if (v === "all") return ["docx", "pdf", "xlsx"];
  return [v];
}

$("#docStart").addEventListener("click", async () => {
  const font = $("#docFont").value;
  const size = Number($("#docSize").value) || 14;

  if (docMode === "export") {
    $("#docOverlay").classList.remove("show");
    toast("در حال ساخت فایل…");
    const r = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: exportContent, font, size, align: $("#docAlign").value, formats: docFormats() }),
    });
    if (!r.ok) { toast("خطا در ساخت فایل"); return; }
    const data = await r.json();
    if (!exportMsgEl) {
      const links = data.files.map(f => `[${f.label}](${f.url})`).join("  |  ");
      addMsg("assistant", "📄 خروجی گفتگو آماده شد:\n\n" + links);
      toast("فایل آماده شد ✅");
      return;
    }
    if (exportMsgEl) {
      const box = document.createElement("div");
      box.className = "dl-links";
      data.files.forEach(f => {
        const a = document.createElement("a");
        a.href = f.url; a.textContent = f.label; a.className = "dl-link";
        box.appendChild(a);
      });
      (data.notes || []).forEach(n => {
        const s = document.createElement("span");
        s.className = "dl-note"; s.textContent = "⚠️ " + n;
        box.appendChild(s);
      });
      exportMsgEl.querySelector(".bubble").appendChild(box);
    }
    toast("فایل آماده شد ✅");
    return;
  }

  // مقاله بلند
  const topic = $("#docTopic").value.trim();
  if (!topic) { toast("موضوع مقاله را بنویسید"); return; }
  const pages = Number($("#docPages").value) || 10;
  $("#docOverlay").classList.remove("show");
  const clearDocChips = () => { docAttachments = []; $("#docChips").innerHTML = ""; $("#docWeb").checked = false; };
  setTimeout(clearDocChips, 500);

  currentConv = null;
  addMsg("user", `📄 درخواست مقاله ${pages} صفحه‌ای: ${topic}`);
  const aDiv = addMsg("assistant", "");
  const mdEl = aDiv.querySelector(".md");
  mdEl.innerHTML = '<span class="typing">شروع ساخت مقاله</span>';

  abortCtrl = new AbortController();
  sending = true;
  setStopMode(true);

  try {
    const resp = await fetch("/api/longdoc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic, pages, font, size,
        align: $("#docAlign").value,
        formats: docFormats(),
        attachments: docAttachments.map(a => a.id),
        use_web: $("#docWeb").checked,
      }),
      signal: abortCtrl.signal,
    });
    if (!resp.ok) {
      const e2 = await resp.json().catch(() => ({}));
      mdEl.innerHTML = renderMD("⚠️ " + (e2.detail || "خطا"));
      return;
    }
    const cid = resp.headers.get("X-Conversation-Id");
    if (cid) currentConv = Number(cid);
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let full = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      full += dec.decode(value, { stream: true });
      mdEl.innerHTML = renderMD(full);
      aDiv.dataset.raw = full;
      msgsEl.scrollTop = msgsEl.scrollHeight;
    }
    loadConvs();
  } catch (err) {
    if (err.name === "AbortError") {
      const cur = aDiv.dataset.raw || "";
      mdEl.innerHTML = renderMD(cur + "\n\n⏹ ساخت مقاله متوقف شد.");
    } else {
      mdEl.innerHTML = renderMD("⚠️ ارتباط قطع شد.");
    }
  } finally {
    sending = false;
    abortCtrl = null;
    setStopMode(false);
  }
});

/* ---------- جستجوی گفتگوها ---------- */

function filterConvs() {
  const q = ($("#convSearch")?.value || "").trim();
  document.querySelectorAll("#convList .conv").forEach(c => {
    c.style.display = !q || c.querySelector(".t").textContent.includes(q) ? "" : "none";
  });
}
$("#convSearch")?.addEventListener("input", filterConvs);

/* ---------- بنر اطلاع‌رسانی (با یک بار بستن، دیگر نمایش داده نمی‌شود تا پیام عوض شود) ---------- */

const annEl = $("#announce");
if (annEl) {
  const text = annEl.querySelector("span").textContent;
  if (localStorage.getItem("antanu_ann_dismissed") === text) annEl.remove();
  else $("#announceClose").addEventListener("click", () => {
    localStorage.setItem("antanu_ann_dismissed", text);
    annEl.remove();
  });
}

/* ---------- بزرگ‌نمایی عکس با کلیک ---------- */
let zoomEl = null;
msgsEl.addEventListener("click", e => {
  if (e.target.classList.contains("msg-img") || (e.target.tagName === "IMG" && e.target.closest(".md"))) {
    if (!zoomEl) {
      zoomEl = document.createElement("div");
      zoomEl.id = "imgZoom";
      zoomEl.innerHTML = '<img>';
      zoomEl.addEventListener("click", () => zoomEl.classList.remove("show"));
      document.body.appendChild(zoomEl);
    }
    zoomEl.querySelector("img").src = e.target.src;
    zoomEl.classList.add("show");
  }
});

/* ---------- پروفایل کاربر ---------- */

function setProfileAvatar(src) {
  const img = $("#pAvatar"), ph = $("#pAvatarPh");
  if (src) { img.src = src; img.style.display = "flex"; ph.style.display = "none"; }
  else { img.style.display = "none"; ph.style.display = "flex"; }
}

async function openProfile() {
  const r = await fetch("/api/profile");
  if (!r.ok) return;
  const p = await r.json();
  $("#pUser").textContent = p.username;
  $("#pStars").textContent = "★".repeat(p.stars) + ` (${p.stars} ستاره)`;
  $("#pJoined").textContent = p.joined || "—";
  $("#pUsage").textContent = p.daily_limit
    ? `${p.used_today} از ${p.daily_limit} پیام`
    : `${p.used_today} پیام (نامحدود)`;
  setProfileAvatar(p.avatar);
  $("#pOld").value = ""; $("#pNew").value = ""; $("#pMsg").textContent = "";
  closeSidebar();
  $("#profileOverlay").classList.add("show");
}

$("#profileBtn")?.addEventListener("click", openProfile);
$("#profileOverlay")?.addEventListener("click", e => {
  if (e.target.id === "profileOverlay" || e.target.classList.contains("close"))
    $("#profileOverlay").classList.remove("show");
});

$("#pAvatarBtn")?.addEventListener("click", () => $("#pAvatarInput").click());
$("#pAvatarInput")?.addEventListener("change", async e => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/profile/avatar", { method: "POST", body: fd });
  if (!r.ok) { toast("خطا در آپلود عکس"); e.target.value = ""; return; }
  const d = await r.json();
  window.USER_AVATAR = d.avatar;
  setProfileAvatar(d.avatar);
  const sideAva = document.querySelector("#profileBtn .user-avatar");
  if (sideAva) sideAva.outerHTML = `<img src="${d.avatar}" class="user-avatar">`;
  toast("عکس پروفایل ذخیره شد ✅");
  e.target.value = "";
});

$("#pPassBtn")?.addEventListener("click", async () => {
  const r = await fetch("/api/profile/password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old: $("#pOld").value, new: $("#pNew").value }),
  });
  const d = await r.json().catch(() => ({}));
  $("#pMsg").textContent = r.ok ? "✅ گذرواژه با موفقیت تغییر کرد" : "❌ " + (d.detail || "خطا");
  if (r.ok) { $("#pOld").value = ""; $("#pNew").value = ""; }
});

/* ---------- شروع ---------- */
loadConvs();
loadModels();
if (window.speechSynthesis) speechSynthesis.getVoices();
inputEl.focus();
