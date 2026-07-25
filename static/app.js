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
  const vids = [];
  const cleaned2 = cleaned.replace(/\[\[ANTANU_VID:([^\]\s]+)\]\]/g, (m, u) => {
    if (u.startsWith("/download/")) vids.push(u);
    return "";
  });
  let html = "";
  // اگر همراه عکس/ویدیو فقط خرده‌ریز (بک‌تیک، پرانتز، علائم) آمده، متن را نمایش نده
  const meaningful = cleaned2.replace(/[`'"()\[\]{}\s.,،:؛!؟\-_*#>~|=+]/g, "");
  if ((!imgs.length && !vids.length) || meaningful.length > 2) {
    html = DOMPurify.sanitize(marked.parse(cleaned2));
  }
  // دکمه‌ی «کپی» فقط برای بلوک‌های کد (‌pre‌) تا کاربر کل کد را یک‌جا کپی کند
  if (html.includes("<pre")) {
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    tmp.querySelectorAll("pre").forEach(pre => {
      if (pre.parentElement && pre.parentElement.classList.contains("code-wrap")) return;
      const wrap = document.createElement("div");
      wrap.className = "code-wrap";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "code-copy";
      btn.textContent = "📋 کپی";
      pre.parentNode.insertBefore(wrap, pre);
      wrap.appendChild(btn);
      wrap.appendChild(pre);
    });
    html = tmp.innerHTML;
  }
  for (const u of imgs) {
    html += `<img src="${u}" class="gen-img" loading="lazy" alt="تصویر تولیدشده">`;
  }
  for (const u of vids) {
    html += `<video src="${u}" class="gen-vid" controls playsinline preload="metadata"></video>`;
  }
  return html;
}

// کپی کل کد یک بلوک با کلیک روی دکمه‌ی «کپی» (event delegation برای همه‌ی پیام‌ها)
document.addEventListener("click", e => {
  const btn = e.target.closest(".code-copy");
  if (!btn) return;
  const pre = btn.parentElement.querySelector("pre");
  if (!pre) return;
  const codeEl = pre.querySelector("code") || pre;
  const text = codeEl.innerText;
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = "✓ کپی شد";
    setTimeout(() => (btn.textContent = "📋 کپی"), 1500);
  }).catch(() => {
    btn.textContent = "خطا";
    setTimeout(() => (btn.textContent = "📋 کپی"), 1500);
  });
});

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
  // با یک گزینه‌ی واحد، ردیف «انتخاب همه» بی‌معناست
  const allRow = document.querySelector("#modelPanel .model-item.all");
  if (allRow) allRow.style.display = models.length > 1 ? "" : "none";
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

/* منوی مدل‌ها را با مختصات ثابت (fixed) بالای دکمه می‌گذارد تا در موبایل
   داخل نوار افقیِ اسکرول‌دار (overflow) بریده و پنهان نشود */
function positionModelPanel() {
  const panel = $("#modelPanel");
  const btn = $("#modelBtn");
  const r = btn.getBoundingClientRect();
  const w = Math.min(300, window.innerWidth - 20);
  panel.style.position = "fixed";
  panel.style.width = w + "px";
  panel.style.bottom = (window.innerHeight - r.top + 8) + "px";
  panel.style.top = "auto";
  let right = window.innerWidth - r.right;
  right = Math.max(10, Math.min(right, window.innerWidth - w - 10));
  panel.style.right = right + "px";
  panel.style.left = "auto";
  panel.style.maxHeight = "55vh";
  panel.style.overflowY = "auto";
}

$("#modelBtn").addEventListener("click", e => {
  e.stopPropagation();
  const panel = $("#modelPanel");
  const willShow = !panel.classList.contains("show");
  panel.classList.toggle("show");
  if (willShow) positionModelPanel();
});
window.addEventListener("resize", () => {
  if ($("#modelPanel").classList.contains("show")) positionModelPanel();
});
document.addEventListener("click", e => {
  if (!e.target.closest(".model-wrap") && !e.target.closest("#modelPanel"))
    $("#modelPanel").classList.remove("show");
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
    const chip = el(`<span class="chip"><span class="spin"></span> ${escapeHtml(file.name)}</span>`);
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

/* حذف کلمات و «عبارت‌های» تکراری پشت‌سرهم (باگ کروم اندروید: «سلام خوبی سلام خوبی») */
function dedupeWords(s) {
  const w = s.split(/\s+/).filter(Boolean);
  const out = [];
  for (let i = 0; i < w.length; ) {
    let skipped = false;
    // عبارت‌های ۵ تا ۱ کلمه‌ای تکراری را رد کن
    for (let n = Math.min(5, out.length); n >= 1; n--) {
      if (i + n <= w.length) {
        let same = true;
        for (let k = 0; k < n; k++) {
          if (w[i + k] !== out[out.length - n + k]) { same = false; break; }
        }
        if (same) { i += n; skipped = true; break; }
      }
    }
    if (!skipped) { out.push(w[i]); i++; }
  }
  return out.join(" ");
}

const IS_ANDROID = /Android/i.test(navigator.userAgent);

$("#micBtn").addEventListener("click", () => {
  if (!SR) { toast("مرورگر شما میکروفون را پشتیبانی نمی‌کند (از Chrome استفاده کنید)"); return; }
  if (recording) { micManualStop = true; recog.stop(); return; }

  recog = new SR();
  recog.lang = "fa-IR";
  recog.interimResults = true;
  recog.continuous = !IS_ANDROID;  // در اندروید continuous باعث تکرار می‌شود
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
  if (/[\u0600-\u06FF]/.test(text)) {
    if (/[پچژگ]|است|می‌|های|این/.test(text)) return "fa-IR";
    return "ar-SA";
  }
  if (/[\u0400-\u04FF]/.test(text)) return "ru-RU";
  if (/[\u4E00-\u9FFF]/.test(text)) return "zh-CN";
  if (/[a-zA-Z]/.test(text)) return "en-US";
  return "fa-IR";
}

/* صداهای دستگاه ممکن است با تأخیر لود شوند */
let voicesCache = [];
function loadVoices() { voicesCache = speechSynthesis.getVoices() || []; }
if (window.speechSynthesis) {
  loadVoices();
  speechSynthesis.onvoiceschanged = loadVoices;
}

let speakKeepAlive = null;
function stopSpeaking() {
  speaking = false;
  clearInterval(speakKeepAlive);
  try { speechSynthesis.cancel(); } catch (e) {}
}

function speak(text) {
  if (!window.speechSynthesis) { toast("مرورگر شما پخش صدا را پشتیبانی نمی‌کند"); return; }
  if (speaking) { stopSpeaking(); toast("خواندن متوقف شد"); return; }

  const plain = (text || "")
    .replace(/\[\[ANTANU_[^\]]+\]\]/g, " ")
    .replace(/[#*_`>\[\]()|~-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!plain) { toast("متنی برای خواندن نیست"); return; }

  const lang = detectLang(plain);
  loadVoices();
  const voice = voicesCache.find(v => v.lang === lang)
    || voicesCache.find(v => v.lang && v.lang.startsWith(lang.split("-")[0]));

  // اگر صدای فارسی روی دستگاه نصب نیست، به کاربر پیشنهاد صدای حرفه‌ای بده
  if (!voice && lang.startsWith("fa") && voicesCache.length) {
    toast("صدای فارسی روی دستگاه شما نیست؛ برای کیفیت بهتر «🎧 صدای حرفه‌ای» را بزنید");
  }

  // تکه‌تکه کردن متن — رفع باگ کروم/اندروید که متن بلند را نمی‌خواند
  const chunks = [];
  let cur = "";
  for (const part of plain.split(/(?<=[.!؟?؛;:])\s+/)) {
    if ((cur + " " + part).length > 180) {
      if (cur) chunks.push(cur);
      cur = part;
    } else {
      cur = cur ? cur + " " + part : part;
    }
  }
  if (cur) chunks.push(cur);

  speechSynthesis.cancel();
  speaking = true;
  // رفع باگ کروم که پخش بعد از ~۱۵ ثانیه قطع می‌شود
  clearInterval(speakKeepAlive);
  speakKeepAlive = setInterval(() => {
    if (!speaking) { clearInterval(speakKeepAlive); return; }
    try { speechSynthesis.pause(); speechSynthesis.resume(); } catch (e) {}
  }, 9000);

  let i = 0;
  const next = () => {
    if (!speaking || i >= chunks.length) { stopSpeaking(); return; }
    const u = new SpeechSynthesisUtterance(chunks[i++]);
    u.lang = lang;
    if (voice) u.voice = voice;
    u.rate = 1;
    u.onend = next;
    u.onerror = next;
    speechSynthesis.speak(u);
  };
  // تأخیر کوتاه تا cancel کامل شود (رفع افت اولین جمله در بعضی مرورگرها)
  setTimeout(next, 60);
  toast("🔊 در حال خواندن… دوباره بزنید تا متوقف شود");
}

/* ---------- صدای حرفه‌ای (TTS با API) ---------- */
function ttsClean(text) {
  return (text || "")
    .replace(/\[\[ANTANU_[^\]]+\]\]/g, " ")
    .replace(/[#*_`>\[\]()|~]/g, " ")
    .replace(/\s+/g, " ").trim().slice(0, 1000);
}
async function proTTS(btn, raw) {
  const bubble = btn.closest(".bubble");
  const text = ttsClean(raw);
  if (!text) { toast("متنی برای صدا نیست"); return; }
  let box = bubble.querySelector(".tts-box");
  if (box) { box.remove(); return; }   // دکمه‌ی دوباره = بستن
  box = document.createElement("div");
  box.className = "tts-box";
  box.innerHTML = `<span class="tts-lbl">انتخاب صدا:</span>
    <button class="tts-v" data-v="self" type="button">🧑‍💼 آنتانو</button>
    <button class="tts-v" data-v="female" type="button">👩 خانم</button>
    <button class="tts-v" data-v="male" type="button">👨 آقا</button>
    <span class="tts-status"></span>`;
  bubble.appendChild(box);
  box.querySelectorAll(".tts-v").forEach(vb => vb.addEventListener("click", async () => {
    const status = box.querySelector(".tts-status");
    box.querySelectorAll(".tts-v").forEach(x => (x.disabled = true));
    status.innerHTML = '<span class="spin"></span> در حال ساخت صدا…';
    try {
      const r = await fetch("/api/tts", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: vb.dataset.v }),
      });
      const d = await r.json();
      if (!r.ok) { status.textContent = "⚠️ " + (d.detail || "خطا در ساخت صدا"); }
      else {
        status.textContent = "";
        const old = box.querySelector("audio"); if (old) old.remove();
        const audio = document.createElement("audio");
        audio.controls = true; audio.src = d.url; audio.autoplay = true;
        audio.style.cssText = "width:100%;margin-top:8px";
        box.appendChild(audio);
      }
    } catch (e) { status.textContent = "خطای شبکه"; }
    box.querySelectorAll(".tts-v").forEach(x => (x.disabled = false));
  }));
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
          ${isUser ? "" : '<button class="act voice">🔊 خواندن</button><button class="act protts">🎧 صدای حرفه‌ای</button><button class="act export">📄 خروجی</button><button class="act regen">🔄 دوباره</button><button class="act cont">⤵️ ادامه</button>'}
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
  if (e.target.classList.contains("protts")) proTTS(e.target, raw);
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
  let text = (typeof textOverride === "string" ? textOverride : inputEl.value).trim();

  // اگر نوع محتوا (مقاله/پروپوزال/...) تیک خورده باشد، صف تولید محتوا اجرا می‌شود
  const ctypes = (typeof textOverride === "string") ? [] : selectedCtypes();
  if (ctypes.length) {
    // موضوع می‌تواند نوشته‌شده باشد یا از روی فایل پیوست‌شده گرفته شود
    if (!text && !attachments.length) {
      toast("موضوع را بنویسید یا یک فایل پیوست کنید تا بر اساس آن انجام شود");
      return;
    }
    if (!text && attachments.length) {
      // فقط فایل — موضوع را از محتوای فایل استخراج کن
      text = "بر اساس اطلاعات، داده‌ها و محتوای فایل پیوست‌شده" +
             (attachments.length === 1 ? ` («${attachments[0].filename}»)` : "");
    }
    inputEl.value = "";
    autosize();
    $("#ctypePanel").classList.remove("show");
    await runContentQueue(text, ctypes);
    return;
  }

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
    tone: ($("#toneSelect") && $("#toneSelect").value) || "",
    attachments: attachments.map(a => a.id),
  };
  clearChips();

  const aDiv = addMsg("assistant", "");
  const mdEl = aDiv.querySelector(".md");
  mdEl.innerHTML = '<span class="spin"></span> <span class="typing">آنتانو در حال فکر کردن است</span>';

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

/* ---------- صف تولید محتوا (چند نوع باهم) ---------- */

// استریم یک درخواست چت و نمایش در حباب — برای ابزارهای پایان‌نامه
async function streamChat(promptText, label) {
  if (attachments.length) label += "\n📎 " + attachments.map(a => a.filename).join("، ");
  addMsg("user", label);
  const aDiv = addMsg("assistant", "");
  const mdEl = aDiv.querySelector(".md");
  mdEl.innerHTML = '<span class="spin"></span> <span class="typing">در حال ساخت ' + label + "</span>";
  abortCtrl = new AbortController();
  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: currentConv,
        message: promptText,
        models: selected,
        web: webOn,
        attachments: attachments.map(a => a.id),
      }),
      signal: abortCtrl.signal,
    });
    if (resp.status === 401) { location.href = "/login"; return; }
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
  } catch (err) {
    if (err.name !== "AbortError")
      mdEl.innerHTML = renderMD("⚠️ ارتباط با سرور قطع شد.");
  }
}

// ساخت مقاله بلند از پنل نوع محتوا
async function makeArticleFromPanel(topic) {
  const pages = Number($("#cPages").value) || 10;
  const fmt = $("#cFormat").value;
  const formats = fmt === "both" ? ["docx", "pdf"] : fmt === "all" ? ["docx", "pdf", "xlsx"] : [fmt];
  let userLabel = `📄 درخواست مقاله ${pages} صفحه‌ای: ${topic}`;
  if (attachments.length) userLabel += "\n📎 " + attachments.map(a => a.filename).join("، ");
  addMsg("user", userLabel);
  const aDiv = addMsg("assistant", "");
  const mdEl = aDiv.querySelector(".md");
  mdEl.innerHTML = '<span class="spin"></span> <span class="typing">شروع ساخت مقاله</span>';
  abortCtrl = new AbortController();
  try {
    const resp = await fetch("/api/longdoc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic, pages,
        font: $("#cFont").value, size: Number($("#cSize").value) || 14,
        align: $("#cAlign").value, formats,
        attachments: attachments.map(a => a.id),
        use_web: $("#cWeb").checked,
        smart_design: true, style: "auto",
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
  } catch (err) {
    if (err.name !== "AbortError")
      mdEl.innerHTML = renderMD("⚠️ ارتباط با سرور قطع شد.");
  }
}

async function runContentQueue(topic, ctypes) {
  sending = true;
  sendBtn.disabled = true;
  setStopMode(true);

  // ترتیب منطقی: موضوع → پروپوزال → فهرست → مبانی → پیشینه → فرضیه → منبع → داور → مقاله → آماری
  const order = ["موضوع", "پروپوزال", "فهرست", "مبانی", "پیشینه", "فرضیه", "منبع", "داور", "پرسشنامه", "دلفی", "مصاحبه", "مقاله", "آماری"];
  const chosen = order.filter(t => ctypes.includes(t));

  try {
    for (const t of chosen) {
      if (t === "مقاله") {
        await makeArticleFromPanel(topic);
      } else if (t === "آماری") {
        // تحلیل آماری نیاز به فایل داده دارد → پنجره اختصاصی باز می‌شود
        toast("برای تحلیل آماری، فایل داده را در پنجره باز شده آپلود کنید");
        $("#statsOverlay").classList.add("show");
      } else {
        const fn = ACAD_PROMPTS[t];
        if (fn) await streamChat(fn(topic), CTYPE_LABELS[t] || t);
      }
    }
    clearChips();
    loadConvs();
  } finally {
    sending = false;
    abortCtrl = null;
    setStopMode(false);
    // تیک‌ها را پاک کن
    document.querySelectorAll(".ctype").forEach(c => (c.checked = false));
    $("#ctypeDocOpts").style.display = "none";
    updateCtypeBtn();
    inputEl.focus();
  }
}

const CTYPE_LABELS = {
  "موضوع": "💡 موضوع‌یابی", "پروپوزال": "📋 پروپوزال", "فهرست": "📑 فهرست پایان‌نامه",
  "پیشینه": "📚 پیشینه پژوهش", "مبانی": "🧠 مبانی نظری", "فرضیه": "🎯 فرضیه‌سازی",
  "منبع": "🔖 منبع و ارجاع", "داور": "⚖️ نقد داور علمی",
  "پرسشنامه": "📝 ساخت پرسشنامه", "دلفی": "🔢 پرسشنامه دلفی فازی", "مصاحبه": "🎤 مصاحبه با خبرگان",
};

sendBtn.addEventListener("click", () => {
  if (sending) { stopStreaming(); return; }
  send();
});
inputEl.addEventListener("keydown", e => {
  // Enter = رفتن به خط بعد (پیش‌فرض textarea). ارسال فقط با دکمه ارسال یا Ctrl/Cmd+Enter.
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); }
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

/* ---------- کتابخانه منابع ---------- */

const REF_TYPE_FA = { article: "مقاله", book: "کتاب", website: "وب‌سایت", thesis: "پایان‌نامه", conference: "کنفرانس" };

$("#refBtn")?.addEventListener("click", e => {
  e.preventDefault();
  closeSidebar();
  $("#refOverlay").classList.add("show");
  loadReferences();
});
$("#refOverlay")?.addEventListener("click", e => {
  if (e.target.id === "refOverlay" || e.target.classList.contains("close"))
    $("#refOverlay").classList.remove("show");
});

async function loadReferences() {
  const r = await fetch("/api/references");
  if (!r.ok) return;
  const list = await r.json();
  $("#refCount").textContent = list.length;
  const box = $("#refList");
  box.innerHTML = "";
  if (!list.length) {
    box.innerHTML = '<div class="ref-empty">هنوز منبعی اضافه نکرده‌اید.</div>';
    return;
  }
  list.forEach(ref => {
    const item = el(`
      <div class="ref-item" data-id="${ref.id}">
        <div class="ref-main">
          <span class="ref-badge">${REF_TYPE_FA[ref.ref_type] || ref.ref_type}</span>
          <b>${escapeHtml(ref.title)}</b>
          <div class="ref-sub">${escapeHtml([ref.authors, ref.year, ref.source].filter(Boolean).join(" — "))}</div>
        </div>
        <button class="ref-del" title="حذف">🗑</button>
      </div>`);
    item.querySelector(".ref-del").addEventListener("click", async () => {
      if (!confirm("این منبع حذف شود؟")) return;
      await fetch("/api/references/" + ref.id, { method: "DELETE" });
      loadReferences();
    });
    box.appendChild(item);
  });
}

function refFormData() {
  return {
    ref_type: $("#refType").value,
    authors: $("#refAuthors").value.trim(),
    title: $("#refTitle").value.trim(),
    year: $("#refYear").value.trim(),
    source: $("#refSource").value.trim(),
    volume: $("#refVolume").value.trim(),
    issue: $("#refIssue").value.trim(),
    pages: $("#refPages").value.trim(),
    url: $("#refUrl").value.trim(),
  };
}

$("#refAddBtn")?.addEventListener("click", async () => {
  const data = refFormData();
  if (!data.title) { toast("عنوان منبع الزامی است"); return; }
  const r = await fetch("/api/reference", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); toast(e.detail || "خطا"); return; }
  ["refAuthors", "refTitle", "refYear", "refSource", "refVolume", "refIssue", "refPages", "refUrl"]
    .forEach(id => ($("#" + id).value = ""));
  toast("منبع اضافه شد ✅");
  loadReferences();
});

$("#refParseBtn")?.addEventListener("click", async () => {
  const text = $("#refParseText").value.trim();
  if (text.length < 8) { toast("متن ارجاع را کامل بچسبانید"); return; }
  const msg = $("#refParseMsg");
  msg.innerHTML = '<span class="spin"></span> در حال تشخیص…';
  try {
    const r = await fetch("/api/references/parse", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const d = await r.json();
    if (!r.ok) { msg.textContent = "❌ " + (d.detail || "خطا"); return; }
    if (d.ref_type && REF_TYPE_FA[d.ref_type]) $("#refType").value = d.ref_type;
    $("#refAuthors").value = d.authors || "";
    $("#refTitle").value = d.title || "";
    $("#refYear").value = d.year || "";
    $("#refSource").value = d.source || "";
    $("#refVolume").value = d.volume || "";
    $("#refIssue").value = d.issue || "";
    $("#refPages").value = d.pages || "";
    $("#refUrl").value = d.url || "";
    msg.textContent = "✅ فیلدها پر شد — بررسی و «افزودن» کنید";
  } catch { msg.textContent = "❌ خطا در تشخیص"; }
});

function fillRefForm(d) {
  if (d.ref_type && REF_TYPE_FA[d.ref_type]) $("#refType").value = d.ref_type;
  $("#refAuthors").value = d.authors || "";
  $("#refTitle").value = d.title || "";
  $("#refYear").value = d.year || "";
  $("#refSource").value = d.source || "";
  $("#refVolume").value = d.volume || "";
  $("#refIssue").value = d.issue || "";
  $("#refPages").value = d.pages || "";
  $("#refUrl").value = d.url || "";
}

/* جست‌وجوی خودکار منبع در Crossref/OpenAlex */
$("#refLookupBtn")?.addEventListener("click", async () => {
  const q = $("#refLookupQuery").value.trim();
  if (q.length < 4) { toast("عنوان مقاله یا DOI را وارد کنید"); return; }
  const msg = $("#refLookupMsg");
  msg.innerHTML = '<span class="spin"></span> در حال جست‌وجو…';
  $("#refLookupResults").innerHTML = "";
  try {
    const r = await fetch("/api/references/lookup", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q }),
    });
    const d = await r.json();
    if (!r.ok) { msg.textContent = "❌ " + (d.detail || "منبعی پیدا نشد"); return; }
    msg.textContent = `✅ ${d.results.length} منبع پیدا شد — یکی را انتخاب کنید:`;
    const box = $("#refLookupResults");
    d.results.forEach(ref => {
      const item = el(`<div class="ref-hit"><b>${escapeHtml(ref.title)}</b>
        <div class="ref-sub">${escapeHtml([ref.authors, ref.year, ref.source].filter(Boolean).join(" — "))}</div></div>`);
      item.addEventListener("click", () => {
        fillRefForm(ref);
        msg.textContent = "✅ فیلدها پر شد — بررسی و «افزودن» کنید";
        box.innerHTML = "";
      });
      box.appendChild(item);
    });
  } catch { msg.textContent = "❌ خطا در جست‌وجو (اتصال اینترنت سرور را بررسی کنید)"; }
});

/* ترجمه‌ی ارجاع انگلیسی به فارسی */
$("#refTranslateBtn")?.addEventListener("click", async () => {
  const text = $("#refParseText").value.trim();
  if (text.length < 5) { toast("ارجاع انگلیسی را در کادر بچسبانید"); return; }
  const out = $("#refTranslateOut");
  out.style.display = "block";
  out.innerHTML = '<span class="spin"></span> در حال ترجمه…';
  try {
    const r = await fetch("/api/references/translate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const d = await r.json();
    if (!r.ok) { out.textContent = "❌ " + (d.detail || "خطا"); return; }
    out.innerHTML = `<b>ترجمه:</b><br>${escapeHtml(d.translated)}
      <br><button class="mini" id="refTrCopy" type="button">📋 کپی</button>`;
    $("#refTrCopy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(d.translated); toast("کپی شد ✅"); } catch {}
    });
  } catch { out.textContent = "❌ خطا در ترجمه"; }
});

/* استخراج منابع از آخرین فایل آپلودشده */
$("#refImportBtn")?.addEventListener("click", async () => {
  const textFile = [...attachments].reverse().find(a => a.kind === "text");
  if (!textFile) { toast("ابتدا فایل منابع (Word/PDF/متن) را با 📎 آپلود کنید"); return; }
  const box = $("#refImportResults");
  box.innerHTML = '<span class="spin"></span> در حال استخراج منابع…';
  try {
    const r = await fetch("/api/references/import", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: textFile.id }),
    });
    const d = await r.json();
    if (!r.ok) { box.textContent = "❌ " + (d.detail || "خطا"); return; }
    if (!d.count) { box.textContent = "منبعی در فایل تشخیص داده نشد."; return; }
    box.innerHTML = `<div style="font-size:12px;color:var(--muted);margin:6px 0">${d.count} منبع پیدا شد — روی هرکدام بزنید تا در کادر تشخیص برود:</div>`;
    d.candidates.forEach(c => {
      const item = el(`<div class="ref-hit"><div class="ref-sub" style="direction:ltr">${escapeHtml(c)}</div></div>`);
      item.addEventListener("click", () => { $("#refParseText").value = c; toast("در کادر تشخیص قرار گرفت"); });
      box.appendChild(item);
    });
  } catch { box.textContent = "❌ خطا در استخراج"; }
});

$("#refGenBtn")?.addEventListener("click", async () => {
  const r = await fetch("/api/references/bibliography", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ style: $("#refStyle").value }),
  });
  const d = await r.json();
  if (!r.ok) { toast(d.detail || "خطا"); return; }
  if (!d.count) { toast("ابتدا چند منبع اضافه کنید"); return; }
  $("#refBibBox").style.display = "block";
  $("#refBib").value = d.text;
});

$("#refCopyBib")?.addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("#refBib").value); toast("فهرست منابع کپی شد ✅"); }
  catch { toast("کپی نشد"); }
});

/* ---------- تبدیل فایل (Word/PDF/PPT) ---------- */

let convFileObj = null;
$("#convertBtn")?.addEventListener("click", e => {
  e.preventDefault();
  closeSidebar();
  $("#convertOverlay").classList.add("show");
});
$("#convertOverlay")?.addEventListener("click", e => {
  if (e.target.id === "convertOverlay" || e.target.classList.contains("close"))
    $("#convertOverlay").classList.remove("show");
});

/* ---------- پاورقی‌گذاری روی فایل ---------- */
let fnFileObj = null;
$("#footnoteBtn")?.addEventListener("click", e => {
  e.preventDefault(); closeSidebar();
  $("#fnResult").innerHTML = ""; $("#fnFileName").textContent = ""; fnFileObj = null;
  $("#footnoteOverlay").classList.add("show");
});
$("#footnoteOverlay")?.addEventListener("click", e => {
  if (e.target.id === "footnoteOverlay" || e.target.classList.contains("close"))
    $("#footnoteOverlay").classList.remove("show");
});
$("#fnUpBtn")?.addEventListener("click", () => $("#fnFile").click());
$("#fnFile")?.addEventListener("change", e => {
  fnFileObj = e.target.files[0] || null;
  $("#fnFileName").textContent = fnFileObj ? "📎 " + fnFileObj.name : "";
});
$("#fnGo")?.addEventListener("click", async () => {
  const res = $("#fnResult");
  if (!fnFileObj) { res.innerHTML = '<span style="color:var(--danger,#e06)">اول یک فایل انتخاب کنید.</span>'; return; }
  $("#fnGo").disabled = true;
  res.innerHTML = '<span class="spin"></span> در حال خواندن فایل و افزودن پاورقی…';
  try {
    const fd = new FormData(); fd.append("file", fnFileObj);
    const r = await fetch("/api/footnote", { method: "POST", body: fd });
    const d = await r.json();
    if (!r.ok) { res.innerHTML = `<span style="color:var(--danger,#e06)">⚠️ ${escapeHtml(d.detail || "خطا")}</span>`; }
    else {
      res.innerHTML = `✅ فایل با ${d.count || 0} پاورقی آماده شد: ` +
        `<a href="${d.url}" class="dl-link">📄 دانلود Word</a>`;
    }
  } catch (e) { res.innerHTML = '<span style="color:var(--danger,#e06)">خطای شبکه؛ دوباره تلاش کنید.</span>'; }
  $("#fnGo").disabled = false;
});

/* ---------- ترجمه چند‌لحنه ---------- */
let trLoaded = false;
async function loadTrLangs() {
  if (trLoaded) return;
  try {
    const r = await fetch("/api/translate/langs");
    if (!r.ok) return;
    const d = await r.json();
    const src = $("#trSource"), tgt = $("#trTarget");
    src.innerHTML = ""; tgt.innerHTML = "";
    Object.entries(d.languages).forEach(([code, name]) => {
      src.insertAdjacentHTML("beforeend", `<option value="${code}">${escapeHtml(name)}</option>`);
      if (code !== "auto") tgt.insertAdjacentHTML("beforeend", `<option value="${code}">${escapeHtml(name)}</option>`);
    });
    src.value = "auto"; tgt.value = "en";
    const tones = $("#trTones"); tones.innerHTML = "";
    const defaults = ["formal", "polite", "friendly", "casual"];
    Object.entries(d.tones).forEach(([k, name]) => {
      tones.insertAdjacentHTML("beforeend",
        `<label><input type="checkbox" class="tr-tone-cb" value="${k}" ${defaults.includes(k) ? "checked" : ""}> ${escapeHtml(name)}</label>`);
    });
    trLoaded = true;
  } catch (e) {}
}
$("#translateBtn")?.addEventListener("click", e => {
  e.preventDefault(); closeSidebar();
  loadTrLangs();
  $("#trResult").innerHTML = "";
  $("#translateOverlay").classList.add("show");
});
$("#translateOverlay")?.addEventListener("click", e => {
  if (e.target.id === "translateOverlay" || e.target.classList.contains("close"))
    $("#translateOverlay").classList.remove("show");
});
/* ضبط صدا → تبدیل به متن (STT) برای ترجمه‌ی صوتی */
let trRecorder = null, trChunks = [], trRecording = false;
$("#trRec")?.addEventListener("click", async () => {
  const status = $("#trRecStatus");
  if (trRecording) {   // پایان ضبط
    try { trRecorder.stop(); } catch (e) {}
    return;
  }
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    status.textContent = "مرورگر شما ضبط صدا را پشتیبانی نمی‌کند."; return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    trChunks = [];
    trRecorder = new MediaRecorder(stream);
    trRecorder.ondataavailable = e => { if (e.data.size) trChunks.push(e.data); };
    trRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      trRecording = false;
      $("#trRec").classList.remove("on"); $("#trRec").textContent = "🎙 ضبط صدا";
      status.innerHTML = '<span class="spin"></span> در حال تبدیل صدا به متن…';
      const blob = new Blob(trChunks, { type: trRecorder.mimeType || "audio/webm" });
      const fd = new FormData();
      fd.append("file", blob, "voice.webm");
      const srcVal = $("#trSource").value;
      if (srcVal && srcVal !== "auto") fd.append("lang", srcVal);
      try {
        const r = await fetch("/api/stt", { method: "POST", body: fd });
        const d = await r.json();
        if (!r.ok) { status.textContent = "⚠️ " + (d.detail || "خطا در تبدیل صدا"); return; }
        const t = (d.text || "").trim();
        $("#trText").value = $("#trText").value ? ($("#trText").value + " " + t) : t;
        status.textContent = t ? "✅ متن آماده شد؛ حالا «ترجمه کن» را بزن." : "چیزی شنیده نشد.";
      } catch (e) { status.textContent = "خطای شبکه در تبدیل صدا."; }
    };
    trRecorder.start();
    trRecording = true;
    $("#trRec").classList.add("on"); $("#trRec").textContent = "⏹ پایان ضبط";
    status.textContent = "🎙 در حال ضبط… برای پایان دوباره بزن.";
  } catch (e) {
    status.textContent = "دسترسی به میکروفون داده نشد.";
  }
});

$("#trGo")?.addEventListener("click", async () => {
  const text = $("#trText").value.trim();
  const res = $("#trResult");
  if (!text) { res.innerHTML = '<div style="color:var(--danger,#e06)">متن را وارد کنید.</div>'; return; }
  const tones = [...document.querySelectorAll(".tr-tone-cb:checked")].map(i => i.value);
  $("#trGo").disabled = true;
  res.innerHTML = '<span class="spin"></span> در حال ترجمه…';
  try {
    const r = await fetch("/api/translate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, source: $("#trSource").value, target: $("#trTarget").value, tones }),
    });
    const d = await r.json();
    if (!r.ok) { res.innerHTML = `<div style="color:var(--danger,#e06)">${escapeHtml(d.detail || "خطا در ترجمه")}</div>`; $("#trGo").disabled = false; return; }
    res.innerHTML = "";
    (d.translations || []).forEach(t => {
      const card = el(`<div class="tr-card">
        <div class="tr-head"><span class="tr-tone">${escapeHtml(t.tone || "ترجمه")}</span>
        <button class="tr-copy" type="button">📋 کپی</button></div>
        <div class="tr-body"></div></div>`);
      card.querySelector(".tr-body").textContent = t.text;
      card.querySelector(".tr-copy").addEventListener("click", () => {
        navigator.clipboard.writeText(t.text).then(() => {
          const b = card.querySelector(".tr-copy"); b.textContent = "✓ کپی شد";
          setTimeout(() => (b.textContent = "📋 کپی"), 1500);
        });
      });
      res.appendChild(card);
    });
    if (!(d.translations || []).length) res.innerHTML = '<div style="color:var(--muted)">ترجمه‌ای برنگشت.</div>';
  } catch (e) {
    res.innerHTML = '<div style="color:var(--danger,#e06)">خطای شبکه؛ دوباره تلاش کنید.</div>';
  }
  $("#trGo").disabled = false;
});

/* ---------- صندوق ایده‌ها و نظرات ---------- */
$("#feedbackBtn")?.addEventListener("click", e => {
  e.preventDefault();
  closeSidebar();
  $("#fbResult").textContent = "";
  $("#feedbackOverlay").classList.add("show");
});
$("#feedbackOverlay")?.addEventListener("click", e => {
  if (e.target.id === "feedbackOverlay" || e.target.classList.contains("close"))
    $("#feedbackOverlay").classList.remove("show");
});
$("#fbSendBtn")?.addEventListener("click", async () => {
  const content = $("#fbContent").value.trim();
  const category = $("#fbCategory").value;
  const res = $("#fbResult");
  if (content.length < 3) { res.style.color = "var(--danger,#e06)"; res.textContent = "لطفاً متن نظر را بنویسید."; return; }
  $("#fbSendBtn").disabled = true;
  res.style.color = "var(--muted)";
  res.textContent = "در حال ارسال…";
  try {
    const r = await fetch("/api/feedback", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, category }),
    });
    const d = await r.json();
    if (r.ok) {
      res.style.color = "var(--accent)";
      res.textContent = d.message || "🙏 نظر شما ثبت شد.";
      $("#fbContent").value = "";
    } else {
      res.style.color = "var(--danger,#e06)";
      res.textContent = d.detail || "خطا در ارسال نظر.";
    }
  } catch (err) {
    res.style.color = "var(--danger,#e06)";
    res.textContent = "خطای شبکه؛ دوباره تلاش کنید.";
  }
  $("#fbSendBtn").disabled = false;
});

$("#convUpBtn")?.addEventListener("click", () => $("#convFile").click());
$("#convFile")?.addEventListener("change", e => {
  convFileObj = e.target.files[0] || null;
  $("#convFileName").textContent = convFileObj ? "📎 " + convFileObj.name : "";
});
$("#convGoBtn")?.addEventListener("click", async () => {
  if (!convFileObj) { toast("ابتدا فایل ورودی را انتخاب کنید"); return; }
  const res = $("#convResult");
  res.innerHTML = '<span class="spin"></span> در حال تبدیل…';
  const fd = new FormData();
  fd.append("file", convFileObj);
  fd.append("target", $("#convTarget").value);
  try {
    const r = await fetch("/api/convert", { method: "POST", body: fd });
    const d = await r.json();
    if (!r.ok) { res.textContent = "❌ " + (d.detail || "خطا در تبدیل"); return; }
    res.innerHTML = "✅ آماده شد: " +
      d.files.map(f => `<a href="${f.url}" class="dl-link">${escapeHtml(f.label)}</a>`).join(" ");
  } catch { res.textContent = "❌ خطا در تبدیل"; }
});

/* ---------- تغییر تم (روشن / تیره) ---------- */

$("#themeBtn")?.addEventListener("click", e => {
  e.preventDefault();
  const cur = document.documentElement.dataset.theme === "light" ? "light" : "dark";
  const next = cur === "light" ? "dark" : "light";
  if (next === "dark") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = "light";
  try { localStorage.setItem("antanu_theme", next); } catch {}
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = next === "light" ? "#f4f6fb" : "#0d1017";
  toast(next === "light" ? "تم روشن ☀️" : "تم تیره 🌙");
});

/* ---------- اشتراک‌گذاری گفتگو (لینک عمومی فقط‌خواندنی) ---------- */

$("#shareConvBtn")?.addEventListener("click", async e => {
  e.preventDefault();
  if (!currentConv) { toast("ابتدا یک گفتگو را باز کنید"); return; }
  try {
    const r = await fetch(`/api/conversations/${currentConv}/share`, { method: "POST" });
    if (!r.ok) { const er = await r.json().catch(() => ({})); toast(er.detail || "خطا"); return; }
    const d = await r.json();
    const link = location.origin + d.url;
    if (navigator.share) {
      try { await navigator.share({ title: "گفتگوی آنتانو", url: link }); closeSidebar(); return; } catch {}
    }
    try { await navigator.clipboard.writeText(link); toast("🔗 لینک اشتراک کپی شد — هر کسی با این لینک می‌تواند گفتگو را ببیند"); }
    catch { prompt("لینک اشتراک‌گذاری این گفتگو:", link); }
    closeSidebar();
  } catch { toast("خطا در ساخت لینک"); }
});

/* ---------- ابزار پایان‌نامه ---------- */

const ACAD_PROMPTS = {
  "موضوع": t => `برای این حوزه ۵ موضوع دقیق و به‌روز پایان‌نامه پیشنهاد بده که قابلیت پژوهش داشته باشند و متغیرهایشان مشخص باشد:\n${t}`,
  "پروپوزال": t => `یک پروپوزال کامل پایان‌نامه بنویس شامل: بیان مسئله، اهمیت و ضرورت، اهداف، سؤالات و فرضیه‌ها، روش پژوهش و جامعه آماری. موضوع:\n${t}`,
  "فهرست": t => `فهرست کامل و استاندارد یک پایان‌نامه (۵ فصل با همه زیربخش‌ها) برای این موضوع بنویس:\n${t}`,
  "پیشینه": t => `پیشینه پژوهش (پژوهش‌های داخلی و خارجی مرتبط) برای این موضوع بنویس با ذکر نویسنده و سال و یافته اصلی هر پژوهش:\n${t}`,
  "مبانی": t => `مبانی نظری کامل و دانشگاهی برای این موضوع بنویس شامل تعاریف، نظریه‌های پایه و چارچوب نظری:\n${t}`,
  "فرضیه": t => `برای این موضوع فرضیه‌های اصلی و فرعی پژوهش را به‌صورت علمی و آزمون‌پذیر بنویس:\n${t}`,
  "منبع": t => `برای این موضوع ۱۰ منبع علمی معتبر به سبک APA بنویس (فارسی و انگلیسی) و نحوه ارجاع درون‌متنی هرکدام را نشان بده:\n${t}`,
  "داور": t => `تو یک داور سخت‌گیر مجله علمی هستی. این متن/موضوع را نقد کن: منطق استدلال‌ها، کافی بودن ارجاعات، رعایت لحن آکادمیک. ایرادات را موردی لیست کن:\n${t}`,
  "پرسشنامه": t => `یک پرسشنامه‌ی استاندارد و کامل پژوهشی برای این موضوع طراحی کن:\n${t}\n\nشامل: مقدمه و توضیح هدف، بخش اطلاعات جمعیت‌شناختی، و گویه‌ها را برای هر متغیر/سازه جداگانه و شماره‌دار بنویس. از طیف لیکرت پنج‌گزینه‌ای (کاملاً مخالفم تا کاملاً موافقم) استفاده کن. برای هر سازه دست‌کم ۴ تا ۶ گویه‌ی روا و دقیق بنویس و منبع اقتباس گویه‌ها را در صورت امکان ذکر کن. خروجی را با عنوان‌بندی و جدول‌بندی مرتب ارائه بده.`,
  "دلفی": t => `یک پرسشنامه‌ی دلفی فازی (Fuzzy Delphi) کامل برای غربال و اعتبارسنجی شاخص‌های این پژوهش طراحی کن:\n${t}\n\nشامل: توضیح روش دلفی فازی برای خبره، فهرست شاخص‌ها/معیارهای پیشنهادی، و برای هر شاخص یک طیف کلامی فازی هفت‌درجه‌ای (بسیار کم، کم، نسبتاً کم، متوسط، نسبتاً زیاد، زیاد، بسیار زیاد) همراه با اعداد فازی مثلثی متناظر هر گزینه در یک جدول. راهنمای تکمیل و معیار توقف (اختلاف میانگین دو مرحله کمتر از ۰٫۱) را هم توضیح بده.`,
  "مصاحبه": t => `یک راهنمای مصاحبه‌ی نیمه‌ساختاریافته با خبرگان برای این پژوهش طراحی کن:\n${t}\n\nشامل: پروتکل آغاز مصاحبه و بیان هدف و اخلاق پژوهش، پرسش‌های اصلی (باز) دسته‌بندی‌شده بر اساس اهداف/سؤالات پژوهش، پرسش‌های کاوشی (probe) برای عمق بیشتر، و پرسش‌های پایانی. پرسش‌ها را شماره‌دار و حرفه‌ای بنویس و مناسب تحلیل مضمون (تماتیک) باشند.`,
};

$("#acadBtn")?.addEventListener("click", () => $("#acadOverlay").classList.add("show"));
$("#acadOverlay")?.addEventListener("click", e => {
  if (e.target.id === "acadOverlay" || e.target.classList.contains("close"))
    $("#acadOverlay").classList.remove("show");
});
document.querySelectorAll(".acad-t").forEach(btn => {
  btn.addEventListener("click", () => {
    const topic = $("#acadTopic").value.trim();
    if (!topic) { toast("موضوع یا متغیرهای پژوهش را بنویسید"); return; }
    const fn = ACAD_PROMPTS[btn.dataset.t];
    if (!fn) return;
    $("#acadOverlay").classList.remove("show");
    send(fn(topic));
  });
});

/* ---------- تحلیل آماری ---------- */

let statsFileName = null;

$("#statsBtn")?.addEventListener("click", () => $("#statsOverlay").classList.add("show"));
$("#statsOverlay")?.addEventListener("click", e => {
  if (e.target.id === "statsOverlay" || e.target.classList.contains("close"))
    $("#statsOverlay").classList.remove("show");
});
$("#statsUpBtn")?.addEventListener("click", () => $("#statsFile").click());
$("#statsFile")?.addEventListener("change", async e => {
  const file = e.target.files[0];
  if (!file) return;
  $("#statsInfo").innerHTML = '<span class="spin"></span> در حال خواندن داده…';
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await fetch("/api/stats/upload", { method: "POST", body: fd });
    if (!r.ok) {
      const er = await r.json().catch(() => ({}));
      $("#statsInfo").textContent = "❌ " + (er.detail || "خطا در آپلود");
      return;
    }
    const d = await r.json();
    statsFileName = d.file;
    const o = d.overview;
    $("#statsInfo").innerHTML =
      `✅ داده خوانده شد: <b>${o.rows}</b> ردیف، <b>${o.cols}</b> متغیر` +
      (o.total_missing ? ` — ${o.total_missing} داده گمشده` : "") +
      `<br><span style="color:var(--muted);font-size:12px">متغیرها: ${o.columns.join("، ")}</span>`;
    $("#statsTools").style.display = "grid";
  } catch { $("#statsInfo").textContent = "❌ خطا در آپلود"; }
  e.target.value = "";
});

/* برچسب فارسی برای کلیدهای انگلیسی خروجی آماری (برای نمایش زیباتر جدول) */
const STAT_FA = {
  rows: "تعداد ردیف", cols: "تعداد متغیر", columns: "متغیرها", numeric_columns: "متغیرهای عددی",
  describe: "آمار توصیفی", total_missing: "کل داده‌های گمشده", normality: "آزمون نرمال‌بودن (شاپیرو-ویلک)",
  outliers: "داده‌های پرت", multicollinearity: "هم‌خطی (VIF)", alpha: "آلفای کرونباخ", items: "تعداد گویه",
  quality: "کیفیت", method: "روش", pairs: "همبستگی جفت‌متغیرها", coefficients: "ضرایب مدل",
  r2: "ضریب تعیین (R²)", adj_r2: "R² تعدیل‌شده", f_stat: "آماره F", f_sig: "معناداری F",
  durbin_watson: "دوربین-واتسون", pseudo_r2: "R² شبه", llr_p: "معناداری مدل", kind: "نوع",
  n: "تعداد نمونه", sig: "سطح معناداری", f: "آماره F", groups: "تعداد گروه", mean: "میانگین",
  mean1: "میانگین گروه ۱", mean2: "میانگین گروه ۲", t: "آماره t", kmo: "شاخص KMO",
  bartlett_sig: "معناداری بارتلت", kmo_quality: "کیفیت KMO", loadings: "بارهای عاملی",
  direct_effect: "اثر مستقیم", indirect_effect: "اثر غیرمستقیم", total_effect: "اثر کل",
  boot_ci: "بازه اطمینان بوت‌استرپ", indirect_significant: "معناداری اثر غیرمستقیم",
  mediation_type: "نوع میانجی‌گری", type: "نوع تحلیل", fit_indices: "شاخص‌های برازش",
  fit_verdict: "ارزیابی برازش", cmin_df: "χ²/df", model_spec: "مدل", constructs: "سازه‌ها",
  fornell_larcker: "روایی واگرا (فورنل-لارکر)", paths: "ضرایب مسیر", note: "توضیح",
  CR: "پایایی ترکیبی (CR)", AVE: "میانگین واریانس (AVE)", cronbach_alpha: "آلفای کرونباخ",
  beta: "ضریب مسیر (β)", from: "از", to: "به",
  software: "معادل نرم‌افزار", r: "ضریب همبستگی (R)", std_error_est: "خطای استاندارد برآورد",
};
function faKey(k) { return STAT_FA[k] || k; }

function mdCell(v) {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.join("، ");
  if (typeof v === "object") return Object.entries(v).map(([k, x]) => `${faKey(k)}: ${x}`).join("، ");
  return String(v).replace(/\|/g, "/");
}

/* جدول مارک‌داون از فهرستی از شیءهای تخت */
function mdTableFromList(list) {
  const cols = [];
  list.forEach(o => Object.keys(o).forEach(k => { if (!cols.includes(k)) cols.push(k); }));
  if (!cols.length) return "";
  let md = "| " + cols.map(faKey).join(" | ") + " |\n";
  md += "| " + cols.map(() => "---").join(" | ") + " |\n";
  list.forEach(o => { md += "| " + cols.map(c => mdCell(o[c])).join(" | ") + " |\n"; });
  return md + "\n";
}

/* جدول کلید/مقدار از یک شیء تخت */
function mdKeyVal(obj) {
  const keys = Object.keys(obj);
  if (!keys.length) return "";
  let md = "| شاخص | مقدار |\n| --- | --- |\n";
  keys.forEach(k => { md += `| ${faKey(k)} | ${mdCell(obj[k])} |\n`; });
  return md + "\n";
}

function isFlat(v) {
  return v === null || typeof v !== "object" || Array.isArray(v) && v.every(x => typeof x !== "object");
}

/* هر خروجی آماری (شیء/فهرست تودرتو) را به مارک‌داون با جدول‌های واقعی تبدیل می‌کند */
function statsResultToMD(node, level = 3) {
  if (node === null || typeof node !== "object") return String(node) + "\n\n";

  if (Array.isArray(node)) {
    if (!node.length) return "_(خالی)_\n\n";
    if (node.every(x => x && typeof x === "object" && !Array.isArray(x))) return mdTableFromList(node);
    if (node.every(x => Array.isArray(x))) {
      // فهرستی از ردیف‌ها (مثل ارزیابی برازش)
      const rows = node.map(r => { const o = {}; r.forEach((c, i) => (o["س" + i] = c)); return o; });
      let md = "| " + node[0].map((_, i) => (i === 0 ? "شاخص" : i === 1 ? "مقدار" : "وضعیت")).join(" | ") + " |\n";
      md += "| " + node[0].map(() => "---").join(" | ") + " |\n";
      node.forEach(r => { md += "| " + r.map(c => mdCell(c)).join(" | ") + " |\n"; });
      return md + "\n";
    }
    return node.map(x => "- " + mdCell(x)).join("\n") + "\n\n";
  }

  // شیء: مقادیر ساده در یک جدول کلید/مقدار، و بخش‌های پیچیده به‌صورت زیربخش
  const flat = {}, complex = [];
  for (const [k, v] of Object.entries(node)) {
    if (v !== null && typeof v === "object") complex.push([k, v]);
    else flat[k] = v;
  }
  let md = "";
  if (Object.keys(flat).length) md += mdKeyVal(flat);
  const h = "#".repeat(Math.min(level, 6));
  for (const [k, v] of complex) {
    md += `${h} ${faKey(k)}\n\n` + statsResultToMD(v, level + 1);
  }
  return md;
}

document.querySelectorAll(".stat-t").forEach(btn => {
  btn.addEventListener("click", async () => {
    if (!statsFileName) { toast("ابتدا فایل داده را آپلود کنید"); return; }
    const analysis = btn.dataset.a;
    let params = {};
    // برای تحلیل‌هایی که متغیر لازم دارند، از کاربر بپرس
    if (analysis === "regression") {
      const dep = prompt("نام متغیر وابسته (دقیقاً مثل ستون داده):");
      if (!dep) return;
      const inds = prompt("متغیرهای مستقل (با کاما جدا کنید):");
      if (!inds) return;
      params = { dependent: dep.trim(), independents: inds.split(",").map(s => s.trim()) };
    } else if (analysis === "mediation") {
      const x = prompt("متغیر مستقل (X):"); if (!x) return;
      const m = prompt("متغیر میانجی (M):"); if (!m) return;
      const y = prompt("متغیر وابسته (Y):"); if (!y) return;
      params = { x: x.trim(), m: m.trim(), y: y.trim() };
    } else if (analysis === "anova") {
      const dep = prompt("متغیر وابسته (عددی):"); if (!dep) return;
      const fac = prompt("متغیر گروه‌بندی:"); if (!fac) return;
      params = { dependent: dep.trim(), factor: fac.trim() };
    } else if (analysis === "sem_pls" || analysis === "sem_cfa") {
      const raw = prompt(
        "سازه‌ها و گویه‌هایشان را وارد کنید.\nهر سازه در یک خط: نام سازه = گویه۱، گویه۲، ...\n\nمثال:\nکیفیت = q1, q2, q3\nرضایت = s1, s2",
      );
      if (!raw) return;
      const factors = {};
      raw.split("\n").forEach(line => {
        const [name, items] = line.split("=");
        if (name && items) factors[name.trim()] = items.split(/[,،]/).map(s => s.trim()).filter(Boolean);
      });
      if (!Object.keys(factors).length) { toast("قالب سازه‌ها نامعتبر بود"); return; }
      params = { factors };
      if (analysis === "sem_pls") {
        const st = prompt("مسیرهای ساختاری (اختیاری) — هر مسیر: مستقل ← وابسته\nمثال:\nکیفیت ← رضایت\nرضایت ← وفاداری", "");
        if (st) {
          params.structural = st.split("\n").map(l => l.split(/←|->|<-/).map(s => s.trim())).filter(p => p.length === 2 && p[0] && p[1]);
        }
      }
    }
    $("#statsOverlay").classList.remove("show");
    const aDiv = addMsg("assistant", "");
    const mdEl = aDiv.querySelector(".md");
    mdEl.innerHTML = '<span class="spin"></span> در حال تحلیل آماری…';
    try {
      const r = await fetch("/api/stats/run", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file: statsFileName, analysis, params }),
      });
      const d = await r.json();
      if (d.result && d.result.error) {
        mdEl.innerHTML = renderMD("⚠️ " + d.result.error);
        return;
      }
      let out = "## 📊 نتیجه تحلیل: " + btn.textContent.trim() + "\n\n";
      // نمودار مسیر مدل (SmartPLS) — اگر ساخته شده باشد
      let diagram = null;
      if (d.result && d.result.diagram) { diagram = d.result.diagram; delete d.result.diagram; }
      if (diagram) out += `### 📈 نمودار مسیر مدل (SmartPLS)\n\n![نمودار مسیر مدل](${diagram})\n\n`;
      out += statsResultToMD(d.result);
      if (d.interpretation) out += "\n\n### 📝 تفسیر دانشگاهی\n\n" + d.interpretation;
      mdEl.innerHTML = renderMD(out);
      aDiv.dataset.raw = out;
    } catch { mdEl.innerHTML = renderMD("⚠️ خطا در تحلیل"); }
  });
});

/* ---------- لحن و سبک پاسخ (به‌خاطر سپردن انتخاب کاربر) ---------- */
(() => {
  const sel = $("#toneSelect");
  if (!sel) return;
  const saved = localStorage.getItem("antanu_tone");
  if (saved) sel.value = saved;
  sel.addEventListener("change", () => {
    localStorage.setItem("antanu_tone", sel.value);
    if (sel.value) toast("🎨 لحن پاسخ تغییر کرد");
  });
})();

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
  const hub = document.getElementById("docHubTools");
  if (hub) hub.style.display = isExport ? "none" : "grid";
  $("#docHint").style.display = isExport ? "none" : "block";
  $("#docStart").textContent = isExport ? "ساخت فایل" : "شروع ساخت";
  $("#docOverlay").classList.add("show");
}

/* شورت‌کات ابزار پایان‌نامه و تحلیل آماری داخل پنجره مقاله بلند */
document.getElementById("docHubTools")?.addEventListener("click", e => {
  const b = e.target.closest("[data-hub]");
  if (!b) return;
  $("#docOverlay").classList.remove("show");
  if (b.dataset.hub === "acad") $("#acadOverlay").classList.add("show");
  else $("#statsOverlay").classList.add("show");
});

/* آپلود منابع پنجره مقاله بلند */
$("#docAttachBtn").addEventListener("click", () => $("#docFileInput").click());
$("#docFileInput").addEventListener("change", async e => {
  for (const file of e.target.files) {
    const chip = el(`<span class="chip"><span class="spin"></span> ${escapeHtml(file.name)}</span>`);
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

/* ---------- پنل نوع محتوا (تیک‌دار) ---------- */
$("#ctypeBtn")?.addEventListener("click", () => {
  $("#ctypePanel").classList.toggle("show");
});
$("#ctypeClear")?.addEventListener("click", () => {
  document.querySelectorAll(".ctype").forEach(c => (c.checked = false));
  $("#ctypeDocOpts").style.display = "none";
  updateCtypeBtn();
});
function selectedCtypes() {
  return [...document.querySelectorAll(".ctype:checked")].map(c => c.value);
}
function updateCtypeBtn() {
  const n = selectedCtypes().length;
  $("#ctypeBtn").classList.toggle("on", n > 0);
  $("#ctypeBtn").textContent = n > 0 ? "✍️" + n : "✍️";
}
document.querySelectorAll(".ctype").forEach(c => {
  c.addEventListener("change", () => {
    // تنظیمات خروجی فقط وقتی «مقاله بلند» تیک خورده
    const wantsDoc = document.querySelector('.ctype[value="مقاله"]').checked;
    $("#ctypeDocOpts").style.display = wantsDoc ? "block" : "none";
    updateCtypeBtn();
  });
});

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

async function makePptx(content, msgEl) {
  const firstLine = (content.split("\n").find(l => l.trim()) || "ارائه آنتانو")
    .replace(/^#+\s*/, "").slice(0, 80);
  const r = await fetch("/api/pptx", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, title: firstLine,
      smart_design: $("#docSmart") ? $("#docSmart").checked : true,
      style: $("#docStyle") ? $("#docStyle").value : "auto" }),
  });
  if (!r.ok) { toast("خطا در ساخت پاورپوینت"); return; }
  const data = await r.json();
  const links = data.files.map(f => `[${f.label}](${f.url})`).join("  ");
  if (msgEl) {
    const box = document.createElement("div");
    box.className = "dl-links";
    data.files.forEach(f => {
      const a = document.createElement("a");
      a.href = f.url; a.textContent = f.label; a.className = "dl-link";
      box.appendChild(a);
    });
    msgEl.querySelector(".bubble").appendChild(box);
  } else {
    addMsg("assistant", "📊 پاورپوینت آماده شد:\n\n" + links);
  }
  toast("پاورپوینت آماده شد ✅");
}

$("#docStart").addEventListener("click", async () => {
  const font = $("#docFont").value;
  const size = Number($("#docSize").value) || 14;

  if (docMode === "export") {
    const btn = $("#docStart");
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> در حال ساخت فایل…';
    const restore = () => { btn.disabled = false; btn.textContent = "ساخت فایل"; $("#docOverlay").classList.remove("show"); };
    if ($("#docFormat").value === "pptx") {
      restore();
      await makePptx(exportContent, exportMsgEl);
      return;
    }
    const r = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: exportContent, font, size, align: $("#docAlign").value,
        formats: docFormats(), toc: $("#docToc").checked, numbering: $("#docNumbering").checked,
        smart_design: $("#docSmart").checked, style: $("#docStyle").value }),
    });
    if (!r.ok) { restore(); toast("خطا در ساخت فایل"); return; }
    const data = await r.json();
    restore();
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
  mdEl.innerHTML = '<span class="spin"></span> <span class="typing">شروع ساخت مقاله</span>';

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
        smart_design: $("#docSmart").checked, style: $("#docStyle").value,
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

/* ---------- جستجوی گفتگوها (عنوان فوری + تمام‌متن با تأخیر) ---------- */

function filterConvs() {
  const q = ($("#convSearch")?.value || "").trim();
  document.querySelectorAll("#convList .conv").forEach(c => {
    c.style.display = !q || c.querySelector(".t").textContent.includes(q) ? "" : "none";
  });
}

let searchDebounce = null;
$("#convSearch")?.addEventListener("input", () => {
  filterConvs(); // فیلتر فوری بر اساس عنوان
  const q = $("#convSearch").value.trim();
  clearTimeout(searchDebounce);
  if (q.length < 2) { loadConvs(); return; }
  searchDebounce = setTimeout(() => searchConvs(q), 350);
});

async function searchConvs(q) {
  let results;
  try {
    const r = await fetch(`/api/conversations/search?q=${encodeURIComponent(q)}`);
    if (!r.ok) return;
    results = await r.json();
  } catch { return; }
  // اگر کاربر در این فاصله چیز دیگری تایپ کرده، این نتایج قدیمی را نادیده بگیر
  if ($("#convSearch").value.trim() !== q) return;

  convListEl.innerHTML = "";
  if (!results.length) {
    convListEl.appendChild(el(`<div class="conv-empty">چیزی با «${escapeHtml(q)}» پیدا نشد</div>`));
    return;
  }
  results.forEach(rres => {
    const item = el(`
      <div class="conv search-hit ${rres.id === currentConv ? "active" : ""}" data-id="${rres.id}">
        <span class="t">${escapeHtml(rres.title)}</span>
        <div class="hit-snip">${escapeHtml(rres.snippet)}</div>
      </div>`);
    convListEl.appendChild(item);
  });
}

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
  $("#pStars").textContent = p.unlimited
    ? "مدیر — نامحدود ∞"
    : "★".repeat(p.stars) + ` (${p.stars} ستاره)`;
  $("#pJoined").textContent = p.joined || "—";
  // اعتبار اشتراک
  const exp = $("#pExpire");
  if (p.unlimited) {
    exp.textContent = "همیشگی";
    exp.style.color = "";
  } else if (!p.sub_active) {
    exp.textContent = `⛔ منقضی شده (${p.end_date || "—"}) — برای تمدید به مدیر پیام دهید`;
    exp.style.color = "var(--danger)";
  } else {
    exp.textContent = `${p.days_left} روز دیگر (تا ${p.end_date || "—"})`;
    exp.style.color = p.days_left <= 5 ? "var(--danger)" : "";
  }
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

/* ---------- ثبت سرویس‌ورکر (PWA — نصب‌پذیری و بارگذاری سریع‌تر) ---------- */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

/* ---------- شروع ---------- */
loadConvs();
loadModels();
if (window.speechSynthesis) speechSynthesis.getVoices();
inputEl.focus();
