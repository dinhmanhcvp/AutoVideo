"use strict";
// =====================================================================================
//  AutoVideo — giao diện web. Không dùng thư viện ngoài; mọi dữ liệu lấy qua /api/*.
// =====================================================================================

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => (n == null ? "–" : Number(n).toLocaleString("vi-VN"));
const fileUrl = (rel, bust = "") => `/files?p=${encodeURIComponent(rel)}${bust ? "&v=" + bust : ""}`;

const STATUS = {
  pending: ["Chờ duyệt", "warn"], uploading: ["Đang đăng", "info"], scheduled: ["Đã hẹn giờ", "info"],
  published: ["Đã đăng", "ok"], published_manual: ["Đã đăng (tự đăng)", "ok"], approved: ["Đã duyệt", "ok"],
  rejected: ["Đã bỏ", "bad"], failed: ["Đăng lỗi", "bad"],
};
const statusPill = (s) => { const [t, c] = STATUS[s] || [s, ""]; return `<span class="pill ${c}">${esc(t)}</span>`; };
const TASK = { running: ["Đang chạy", "info"], done: ["Xong", "ok"], failed: ["Lỗi", "bad"] };
const taskPill = (s) => { const [t, c] = TASK[s] || [s, ""]; return `<span class="pill ${c}">${t}</span>`; };

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Lỗi ${r.status}`);
  return data;
}

function toast(msg, bad = false) {
  const el = document.createElement("div");
  el.className = "toast" + (bad ? " bad" : "");
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), bad ? 6000 : 3000);
}
async function safe(fn) { try { return await fn(); } catch (e) { toast(e.message, true); } }

function openModal(html) { $("#modal-body").innerHTML = html; $("#modal").hidden = false; }
function closeModal() { $("#modal").hidden = true; $("#modal-body").innerHTML = ""; stopAllLogs(); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast("Đã sao chép"); }
  catch { const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); toast("Đã sao chép"); }
}

// ---------------------------------------------------------------- nhật ký việc chạy nền
const logWatchers = new Set();
function stopAllLogs() { logWatchers.forEach((w) => (w.stopped = true)); logWatchers.clear(); }

/** Gắn nhật ký trực tiếp của 1 việc vào phần tử `el`. onDone(task) gọi khi việc kết thúc. */
function watchTask(taskId, el, onDone) {
  const w = { stopped: false };
  logWatchers.add(w);
  let offset = 0;
  el.innerHTML = `<div class="row" style="margin-bottom:8px"><span class="t-status"></span><span class="t-label muted small"></span>
    <span class="spacer"></span><button class="btn sm danger t-stop">Dừng</button></div><div class="log"></div>`;
  const log = $(".log", el);
  $(".t-stop", el).onclick = () => safe(async () => { await api(`/api/tasks/${taskId}/stop`, {}); toast("Đã gửi lệnh dừng"); });
  const tick = async () => {
    if (w.stopped) return;
    try {
      const r = await api(`/api/tasks/${taskId}/log?offset=${offset}`);
      offset = r.offset;
      if (r.text) {
        const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 30;
        log.textContent += r.text;
        if (atBottom) log.scrollTop = log.scrollHeight;
      }
      $(".t-status", el).innerHTML = taskPill(r.task.status);
      $(".t-label", el).textContent = r.task.label;
      if (r.task.status !== "running") {
        $(".t-stop", el).hidden = true;
        logWatchers.delete(w);
        refreshShell();
        onDone && onDone(r.task);
        return;
      }
    } catch (e) { /* mất kết nối tạm: thử lại */ }
    setTimeout(tick, 1000);
  };
  tick();
}

function showTaskModal(task, title) {
  openModal(`<h2>${esc(title || task.label)}</h2><div id="task-log"></div>`);
  watchTask(task.id, $("#task-log"));
}

async function startTask(body, title, onDone) {
  return safe(async () => {
    const task = await api("/api/tasks", body);
    if (onDone === undefined) showTaskModal(task, title);
    refreshShell();
    return task;
  });
}

// ---------------------------------------------------------------- khung chung
let OV = null; // dữ liệu tổng quan gần nhất

async function refreshShell() {
  try {
    OV = await api("/api/overview");
    $("#channel-name").textContent = OV.channel;
    const pending = (OV.counts.pending || 0) + (OV.counts.failed || 0);
    const b = $("#nav-pending");
    b.hidden = !pending; b.textContent = pending;
    const running = OV.tasks.find((t) => t.status === "running");
    $("#running-box").hidden = !running;
    if (running) $("#running-label").textContent = running.label;
  } catch (e) { /* bỏ qua */ }
}
setInterval(refreshShell, 5000);

const PAGES = { overview: pageOverview, create: pageCreate, ready: pageReady, market: pageMarket, report: pageReport, settings: pageSettings };

async function route() {
  stopAllLogs();
  const [page, arg] = (location.hash.slice(1) || "overview").split("/");
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === page));
  const view = $("#view");
  view.innerHTML = `<div class="loading">Đang tải…</div>`;
  try { await (PAGES[page] || pageOverview)(view, arg ? decodeURIComponent(arg) : null); }
  catch (e) { view.innerHTML = `<div class="notice">${esc(e.message)}</div>`; }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

// ================================================================ TỔNG QUAN
async function pageOverview(view) {
  await refreshShell();
  const o = OV;
  const missing = Object.entries(o.keys).filter(([, v]) => !v).map(([k]) => k);
  const needKeys = [];
  if (o.engines.llm.startsWith("anthropic")) needKeys.push("ANTHROPIC_API_KEY"); else needKeys.push("GEMINI_API_KEY");
  if (o.engines.asr === "groq") needKeys.push("GROQ_API_KEY");
  if (o.engines.tts === "google") needKeys.push("GOOGLE_TTS_API_KEY");
  if (o.engines.tts === "elevenlabs") needKeys.push("ELEVENLABS_API_KEY");
  if (o.engines.image === "cloud") needKeys.push("GEMINI_API_KEY");
  if (o.engines.review) needKeys.push("TELEGRAM_BOT_TOKEN");
  const lacking = [...new Set(needKeys)].filter((k) => missing.includes(k));
  const topics = o.topics.filter((t) => t.enabled);

  view.innerHTML = `
  <div class="page-head"><div><h1>Xin chào 👋</h1><p class="muted">Kênh <b>${esc(o.channel)}</b> · ${topics.length} chủ đề đang bật</p></div></div>
  ${!o.config_exists ? `<div class="notice" style="margin-bottom:16px">Chưa có cấu hình riêng. Vào <a href="#settings">Cài đặt</a> để đặt tên kênh, chọn giọng đọc và nhập khóa API.</div>` : ""}
  ${lacking.length ? `<div class="notice" style="margin-bottom:16px">⚠ Còn thiếu khóa API: <b>${lacking.join(", ")}</b> — <a href="#settings">nhập trong Cài đặt</a>.</div>` : ""}
  <div class="grid g4" style="margin-bottom:16px">
    <a class="card stat" href="#ready/pending"><div class="num">${o.counts.pending || 0}</div><div class="lbl">Video chờ duyệt</div></a>
    <a class="card stat" href="#ready/published"><div class="num">${(o.counts.published || 0) + (o.counts.published_manual || 0) + (o.counts.scheduled || 0)}</div><div class="lbl">Đã đăng / hẹn giờ</div></a>
    <div class="card stat"><div class="num">${o.total}</div><div class="lbl">Tổng thành phẩm</div></div>
    <div class="card stat"><div class="num">$${o.cost_month}</div><div class="lbl">Chi phí AI tháng này</div></div>
  </div>
  <div class="grid g2">
    <div class="card stack">
      <div><h2>Chạy tự động</h2><p class="muted small">Tìm truyện theo chủ đề → chấm điểm, loại truyện yếu → dịch → hook → giọng đọc → thumbnail → video YouTube + TikTok + Shorts.</p></div>
      <div class="row">
        <button class="btn primary big" id="run-auto">▶ Chạy 1 lượt</button>
        <button class="btn" id="run-dry">Xem trước sẽ lấy truyện nào</button>
      </div>
      <div class="small muted">Chủ đề đang bật: ${topics.map((t) => `<span class="pill brand">${esc(t.label)}</span>`).join(" ") || "chưa có — bật trong Cài đặt"}</div>
    </div>
    <div class="card">
      <h2>Cấu hình đang dùng</h2>
      <div class="scores" style="grid-template-columns:120px 1fr">
        <span class="muted">Dịch & viết</span><span>${esc(o.engines.llm)}</span>
        <span class="muted">Bóc băng</span><span>${esc(o.engines.asr)}</span>
        <span class="muted">Giọng đọc</span><span>${esc(o.engines.tts)}</span>
        <span class="muted">Ảnh</span><span>${esc(o.engines.image)} ${o.engines.image === "placeholder" ? '<span class="pill warn">ảnh giữ chỗ</span>' : ""}</span>
        <span class="muted">Telegram</span><span>${o.engines.review ? "bật" : "tắt"}</span>
        <span class="muted">Đăng YouTube</span><span>${o.engines.youtube ? "tự động" : "tự đăng tay"}</span>
      </div>
      <div class="row" style="margin-top:14px"><button class="btn sm" id="run-doctor">Kiểm tra cài đặt</button><a class="btn sm" href="#settings">Đổi cài đặt</a></div>
    </div>
  </div>
  <div class="card" style="margin-top:16px">
    <h2>Việc gần đây</h2>
    ${o.tasks.length ? o.tasks.map((t) => `<div class="task-row">${t.status === "running" ? '<div class="spinner"></div>' : ""}${taskPill(t.status)}
      <span>${esc(t.label)}</span><span class="spacer"></span><span class="muted small">${esc(t.started.replace("T", " "))}</span>
      <button class="btn sm" data-task="${t.id}">Nhật ký</button></div>`).join("") : '<p class="muted">Chưa có việc nào trong phiên này.</p>'}
  </div>`;
  $("#run-auto").onclick = () => startTask({ kind: "auto" }, "Chạy 1 lượt tự động");
  $("#run-dry").onclick = () => startTask({ kind: "auto", dry_run: true }, "Xem trước lượt tự động");
  $("#run-doctor").onclick = () => startTask({ kind: "doctor" }, "Kiểm tra cài đặt");
  $$("[data-task]", view).forEach((b) => (b.onclick = () => {
    const t = o.tasks.find((x) => x.id === b.dataset.task); showTaskModal(t);
  }));
}

// ================================================================ TẠO VIDEO
async function pageCreate(view) {
  const { config } = await api("/api/config");
  const topics = config.topics;
  const opts = topics.map((t) => `<option value="${esc(t.name)}" ${t.enabled === false ? "" : ""}>${esc(t.label || t.name)}${t.enabled === false ? " (đang tắt)" : ""}</option>`).join("");
  view.innerHTML = `
  <div class="page-head"><div><h1>Tạo video</h1><p class="muted">Làm 1 video từ truyện bạn chọn. Truyện bạn tự chọn sẽ không bị loại vì điểm thấp (chỉ cảnh báo).</p></div></div>
  <div class="grid g2">
    <div class="card stack">
      <div class="seg" id="src-seg"><button data-s="link" class="on">🔗 Dán link</button><button data-s="text">📝 Dán văn bản</button><button data-s="file">📄 Tải file .txt</button></div>
      <div id="src-link"><label class="f">Link truyện</label><input type="url" id="in-link" placeholder="https://www.bilibili.com/video/BV… hoặc link YouTube">
        <div class="hint">Bilibili, YouTube, Douyin, Ximalaya… (truyện audio tiếng Trung)</div></div>
      <div id="src-text" hidden><label class="f">Văn bản truyện (tiếng Trung hoặc tiếng Việt)</label><textarea id="in-text" style="min-height:220px" placeholder="Dán toàn văn truyện vào đây…"></textarea>
        <div class="hint" id="text-count">0 ký tự</div></div>
      <div id="src-file" hidden><div class="drop" id="drop">Kéo thả file .txt vào đây hoặc bấm để chọn<input type="file" id="in-file" accept=".txt,text/plain" hidden></div>
        <div class="hint" id="file-info"></div></div>
      <div class="field"><label class="f">Chủ đề (giọng đọc, văn phong, kiểu thumbnail)</label><select id="in-topic">${opts}</select></div>
      <div class="row"><button class="btn primary big" id="go">✨ Tạo video</button>
        <button class="btn" id="to-inbox" title="Lưu vào hàng chờ, lượt chạy tự động kế tiếp sẽ làm trước">＋ Thêm vào hàng chờ</button></div>
    </div>
    <div class="card"><h2>Tiến trình</h2><div id="create-log"><p class="muted">Bấm “Tạo video” để bắt đầu. Video 1 tiếng thường mất 15–40 phút tùy máy và dịch vụ.</p></div>
      <div id="create-done" hidden class="notice ok" style="margin-top:12px">✅ Xong! <a href="#ready">Mở Thành phẩm</a> để xem, chọn thumbnail và đăng.</div></div>
  </div>
  <div class="card" style="margin-top:16px"><h2>Hàng chờ (inbox)</h2><div id="inbox-list" class="small muted">Đang tải…</div></div>`;

  let mode = "link", fileText = "", fileName = "";
  $$("#src-seg button").forEach((b) => (b.onclick = () => {
    mode = b.dataset.s;
    $$("#src-seg button").forEach((x) => x.classList.toggle("on", x === b));
    ["link", "text", "file"].forEach((m) => ($("#src-" + m).hidden = m !== mode));
  }));
  $("#in-text").oninput = (e) => ($("#text-count").textContent = `${fmt(e.target.value.length)} ký tự`);
  const drop = $("#drop"), inFile = $("#in-file");
  const readFile = async (f) => { fileText = await f.text(); fileName = f.name.replace(/\.txt$/i, ""); $("#file-info").textContent = `${f.name} · ${fmt(fileText.length)} ký tự`; };
  drop.onclick = () => inFile.click();
  inFile.onchange = () => inFile.files[0] && readFile(inFile.files[0]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && readFile(e.dataTransfer.files[0]); };

  const payload = () => {
    const topic = $("#in-topic").value;
    if (mode === "link") return { source: $("#in-link").value.trim(), topic };
    if (mode === "text") return { text: $("#in-text").value, topic };
    return { text: fileText, name: fileName, topic };
  };
  $("#go").onclick = () => safe(async () => {
    const p = payload();
    if (!p.source && !(p.text || "").trim()) throw new Error("Hãy dán link hoặc văn bản truyện");
    const task = await api("/api/tasks", { kind: "make", ...p });
    $("#create-done").hidden = true;
    watchTask(task.id, $("#create-log"), (t) => { if (t.status === "done") $("#create-done").hidden = false; });
    refreshShell();
  });
  $("#to-inbox").onclick = () => safe(async () => {
    const p = payload();
    if (!p.text) throw new Error("Hàng chờ chỉ nhận văn bản truyện (dán hoặc tải file)");
    const r = await api("/api/inbox", { text: p.text, name: p.name, topic: p.topic });
    toast("Đã thêm vào hàng chờ: " + r.path);
    loadInbox();
  });
  const loadInbox = async () => {
    const files = await api("/api/inbox");
    $("#inbox-list").innerHTML = files.length ? files.map((f) => `<div>📄 ${esc(f)}</div>`).join("") : "Hàng chờ trống. Truyện trong hàng chờ được ưu tiên làm ở lượt chạy tự động kế tiếp.";
  };
  loadInbox();
}

// ================================================================ THÀNH PHẨM
async function pageReady(view, arg) {
  const FILTERS = { all: "Tất cả", pending: "Chờ duyệt", published: "Đã đăng", rejected: "Đã bỏ" };
  if (arg && !FILTERS[arg]) return pageItem(view, arg);
  const filter = arg || "pending";
  const items = await api("/api/ready");
  const match = (it) => filter === "all" || (filter === "pending" ? ["pending", "failed", "uploading"].includes(it.status)
    : filter === "published" ? ["published", "published_manual", "scheduled", "approved"].includes(it.status) : it.status === filter);
  const shown = items.filter(match);
  view.innerHTML = `
  <div class="page-head"><div><h1>Thành phẩm</h1><p class="muted">Bấm vào video để xem, chọn thumbnail/tiêu đề, sao chép nội dung và đăng.</p></div></div>
  <div class="chips">${Object.entries(FILTERS).map(([k, v]) => `<a class="pill ${k === filter ? "brand" : ""}" href="#ready/${k}">${v} (${items.filter((it) => k === "all" || (k === "pending" ? ["pending", "failed", "uploading"].includes(it.status) : k === "published" ? ["published", "published_manual", "scheduled", "approved"].includes(it.status) : it.status === k)).length})</a>`).join("")}</div>
  ${shown.length ? `<div class="cards">${shown.map((it) => `
    <div class="vcard" data-id="${esc(it.id)}">
      <img loading="lazy" src="${fileUrl(it.rel + "/thumbnail.jpg", it.variant)}" alt="">
      <div class="body"><div class="t">${esc(it.title)}</div>
        <div class="row" style="margin-top:8px">${statusPill(it.status)}${it.score != null ? `<span class="pill">⭐ ${it.score}</span>` : ""}
          ${it.files.includes("tiktok.mp4") ? '<span class="pill">TikTok</span>' : ""}${it.files.includes("short.mp4") ? '<span class="pill">Shorts</span>' : ""}</div>
        <div class="muted small" style="margin-top:6px">${esc(it.id.slice(0, 10))}${it.cost != null ? ` · $${it.cost}` : ""}</div></div>
    </div>`).join("")}</div>`
    : `<div class="card"><p class="muted">Chưa có video ở mục này. ${filter === "pending" ? 'Vào <a href="#create">Tạo video</a> hoặc chạy tự động ở <a href="#overview">Tổng quan</a>.' : ""}</p></div>`}`;
  $$(".vcard", view).forEach((c) => (c.onclick = () => (location.hash = "#ready/" + encodeURIComponent(c.dataset.id))));
}

async function pageItem(view, id) {
  const it = await api("/api/ready/" + encodeURIComponent(id));
  const has = (f) => it.files.includes(f);
  const bust = Date.now();
  const players = [["video.mp4", "YouTube"], ["tiktok.mp4", "TikTok"], ["short.mp4", "Shorts"]].filter(([f]) => has(f));
  const variants = [1, 2, 3].map((n) => {
    const f = n === 1 ? (has("thumbnail_1.jpg") ? "thumbnail_1.jpg" : "thumbnail.jpg") : `thumbnail_${n}.jpg`;
    return has(f) ? { n, f, title: it.titles[n - 1] || "" } : null;
  }).filter(Boolean);
  const cur = it.variant || 1;
  const s = it.scores || {};
  const SCORE_NAMES = { hook: "Hook", premise: "Tiền đề", twist: "Twist", emotion: "Cảm xúc", pacing: "Nhịp", vn_fit: "Hợp khán giả" };
  const textBox = (file, label, rows = 3, hint = "") => `
    <div class="field"><label class="f">${label}</label><textarea data-file="${file}" rows="${rows}" style="min-height:${rows * 24 + 20}px">${esc(it.texts[file] || "")}</textarea>
      ${hint ? `<div class="hint">${hint}</div>` : ""}
      <div class="copyrow"><button class="btn sm" data-copy="${file}">📋 Sao chép</button><button class="btn sm" data-save="${file}">💾 Lưu</button></div></div>`;
  const ytOn = OV && OV.engines.youtube;
  view.innerHTML = `
  <div class="page-head"><div><a href="#ready" class="small">← Thành phẩm</a><h1 style="margin-top:6px">${esc(it.title)}</h1>
    <div class="row">${statusPill(it.status)}${it.score != null ? `<span class="pill">⭐ Điểm truyện ${it.score}/10</span>` : ""}
    ${it.cost != null ? `<span class="pill">Chi phí AI $${it.cost}</span>` : ""}
    ${it.youtube_id ? `<a class="pill ok" target="_blank" href="https://youtu.be/${esc(it.youtube_id)}">▶ Xem trên YouTube</a>` : ""}
    ${it.shorts_id ? `<a class="pill ok" target="_blank" href="https://youtube.com/shorts/${esc(it.shorts_id)}">Shorts</a>` : ""}</div></div></div>
  ${it.logline ? `<div class="notice info" style="margin-bottom:16px">💬 ${esc(it.logline)}</div>` : ""}
  <div class="detail">
    <div class="stack">
      <div class="card">
        <div class="seg" id="pl-seg" style="margin-bottom:12px">${players.map(([f, n], i) => `<button data-f="${f}" class="${i ? "" : "on"}">${n}</button>`).join("")}</div>
        <div class="player" id="player"></div>
        <div class="row" style="margin-top:10px"><a class="btn sm" id="dl" download>⬇ Tải file này</a><span class="muted small" id="pl-hint"></span></div>
      </div>
      <div class="card"><h3>Chọn phương án tên + thumbnail</h3><p class="muted small">3 phương án do AI đặt theo công thức tiêu đề của ngách. Có thể dùng cả 3 cho “Thử nghiệm & so sánh” trong YouTube Studio.</p>
        <div class="variants">${variants.map((v) => `<div class="variant ${v.n === cur ? "on" : ""}" data-n="${v.n}">
          <img src="${fileUrl(it.rel + "/" + v.f, bust)}" alt=""><span class="pill ${v.n === cur ? "brand" : ""} tag">${v.n === cur ? "✓ Đang dùng" : "PA " + v.n}</span>
          <div class="small" style="padding:6px 8px">${esc(v.title.replace(/^\[Truyện Audio\]\s*/i, ""))}</div></div>`).join("")}</div></div>
      ${Object.keys(s).length ? `<div class="card"><h3>Chấm điểm truyện</h3><div class="scores">${Object.entries(SCORE_NAMES).map(([k, n]) => `
        <span class="muted">${n}</span><div class="bar"><i style="width:${(s[k] || 0) * 10}%"></i></div><b>${s[k] ?? "–"}</b>`).join("")}</div></div>` : ""}
    </div>
    <div class="stack">
      <div class="card">
        <h3>Đăng video</h3>
        ${ytOn ? `<div class="row"><button class="btn primary" data-act="publish">⬆ Đăng ngay</button><button class="btn" data-act="schedule">🕒 Hẹn giờ</button></div>
          <p class="hint">Tự upload video + thumbnail, thêm playlist, đăng Shorts có link sang video dài.</p>`
        : `<p class="muted small">Chưa bật tự đăng YouTube. Tải video + thumbnail, sao chép tiêu đề/mô tả bên dưới để đăng tay, rồi bấm “Đã đăng”.</p>`}
        <div class="row" style="margin-top:8px"><button class="btn sm" data-act="manual">✓ Đã đăng (tự đăng tay)</button>
          ${it.status === "rejected" ? '<button class="btn sm" data-act="restore">↩ Khôi phục</button>' : '<button class="btn sm danger" data-act="reject">🗑 Bỏ video này</button>'}</div>
        <div id="pub-log" style="margin-top:12px"></div>
      </div>
      <div class="card">
        <div class="field"><label class="f">Tiêu đề YouTube</label><input type="text" data-file="title.txt" value="${esc(it.texts["title.txt"].trim())}" maxlength="100">
          <div class="copyrow"><button class="btn sm" data-copy="title.txt">📋 Sao chép</button><button class="btn sm" data-save="title.txt">💾 Lưu</button></div></div>
        ${textBox("description.txt", "Mô tả (có mục lục chương)", 8)}
        ${textBox("tags.txt", "Thẻ (tags)", 2)}
        ${textBox("pinned_comment.txt", "Bình luận để ghim", 2, "Dán dưới video sau khi đăng rồi ghim lại — kéo tương tác.")}
        ${has("tiktok_caption.txt") ? textBox("tiktok_caption.txt", "Caption TikTok", 2) : ""}
      </div>
      <p class="muted small">Thư mục: ${esc(it.path)}</p>
    </div>
  </div>`;

  // trình phát
  const setPlayer = (f) => {
    const vertical = f !== "video.mp4";
    $("#player").className = "player" + (vertical ? " vertical" : "");
    $("#player").innerHTML = `<video controls preload="metadata" ${vertical ? 'style="max-width:420px;margin:auto"' : ""} src="${fileUrl(it.rel + "/" + f)}" poster="${vertical ? "" : fileUrl(it.rel + "/thumbnail.jpg", bust)}"></video>`;
    $("#dl").href = fileUrl(it.rel + "/" + f);
    $("#dl").setAttribute("download", f);
    $("#pl-hint").textContent = f === "tiktok.mp4" ? "Clip hook để đăng TikTok" : f === "short.mp4" ? "Shorts ≤ 3 phút" : "Bản đầy đủ cho YouTube";
  };
  $$("#pl-seg button").forEach((b) => (b.onclick = () => { $$("#pl-seg button").forEach((x) => x.classList.toggle("on", x === b)); setPlayer(b.dataset.f); }));
  if (players.length) setPlayer(players[0][0]);

  // phương án
  $$(".variant", view).forEach((v) => (v.onclick = () => safe(async () => {
    await api(`/api/ready/${encodeURIComponent(id)}/variant`, { n: Number(v.dataset.n) });
    toast("Đã đổi sang phương án " + v.dataset.n);
    pageItem(view, id);
  })));
  // chữ: sao chép / lưu
  const field = (f) => $(`[data-file="${f}"]`, view);
  $$("[data-copy]", view).forEach((b) => (b.onclick = () => copy(field(b.dataset.copy).value)));
  $$("[data-save]", view).forEach((b) => (b.onclick = () => safe(async () => {
    await api(`/api/ready/${encodeURIComponent(id)}/text`, { file: b.dataset.save, content: field(b.dataset.save).value });
    toast("Đã lưu");
  })));
  // thao tác
  $$("[data-act]", view).forEach((b) => (b.onclick = () => safe(async () => {
    const act = b.dataset.act;
    if (act === "reject" && !confirm("Bỏ video này? (chuyển vào ready/_rejected, có thể khôi phục)")) return;
    const r = await api(`/api/ready/${encodeURIComponent(id)}/${act}`, {});
    if (r.id) watchTask(r.id, $("#pub-log"), () => setTimeout(() => pageItem(view, id), 800));
    else { toast("Đã cập nhật"); act === "reject" ? (location.hash = "#ready") : pageItem(view, id); }
  })));
}

// ================================================================ THỊ TRƯỜNG
async function pageMarket(view) {
  const m = await api("/api/market");
  const rows = m.niches ? Object.entries(m.niches).sort((a, b) => (b[1].score || 0) - (a[1].score || 0)) : [];
  view.innerHTML = `
  <div class="page-head"><div><h1>Thị trường</h1><p class="muted">Ngách truyện audio nào đang ăn view trên YouTube Việt Nam (video dài &gt;20 phút đăng trong 31 ngày).</p></div>
    <button class="btn primary" id="rerun">🔄 Khảo sát lại (~3 phút)</button></div>
  ${rows.length ? `<div class="card"><div class="row" style="margin-bottom:10px"><b>Kết quả ngày ${esc(m.date)}</b><span class="muted small">— bấm vào ngách để xem video nổi nhất</span></div>
    <div class="table-wrap"><table><thead><tr><th>#</th><th>Ngách</th><th class="num">Trung vị view/ngày</th><th class="num">% trúng</th><th class="num">Kênh trúng</th><th class="num">Độ dài</th><th style="width:160px">Điểm cơ hội</th></tr></thead>
    <tbody>${rows.map(([k, n], i) => `<tr class="${i < 3 ? "top" : ""}" data-k="${esc(k)}" style="cursor:pointer"><td>${i + 1}</td><td><b>${esc(n.label)}</b></td>
      <td class="num">${fmt(n.median_vpd)}</td><td class="num">${n.n ? Math.round(n.hit_rate * 100) + "%" : "–"}</td>
      <td class="num">${n.n ? `${n.hit_channels}/${n.channels}` : "–"}</td><td class="num">${n.median_len_min ? n.median_len_min + "'" : "–"}</td>
      <td><div class="row" style="flex-wrap:nowrap"><div class="bar" style="flex:1"><i style="width:${n.score}%"></i></div><b>${n.score}</b></div></td></tr>
      <tr data-detail="${esc(k)}" hidden><td></td><td colspan="6">${(n.top_videos || []).map((v) => `<div class="small" style="padding:3px 0">
        <b>${fmt(v.views_per_day)}</b> view/ngày · ${esc(v.channel)} — <a target="_blank" href="https://www.youtube.com/watch?v=${esc(v.id)}">${esc(v.title)}</a></div>`).join("")}</td></tr>`).join("")}
    </tbody></table></div>
    <p class="hint" style="margin-top:10px">Điểm = độ đều (trung vị) + trần (P75) + tỷ lệ video ≥1.000 view/ngày + số kênh cùng ăn view. Dùng để so sánh giữa các ngách, không phải kỳ vọng view tuyệt đối. Phân tích đầy đủ: docs/market-analysis.md</p></div>`
    : `<div class="card"><p class="muted">Chưa có dữ liệu. Bấm “Khảo sát lại”.</p></div>`}`;
  $("#rerun").onclick = () => safe(async () => {
    const task = await api("/api/tasks", { kind: "market" });
    openModal(`<h2>Khảo sát thị trường</h2><div id="task-log"></div>`);
    watchTask(task.id, $("#task-log"), (t) => { if (t.status === "done") { closeModal(); pageMarket(view); toast("Đã cập nhật khảo sát"); } });
  });
  $$("tr[data-k]", view).forEach((tr) => (tr.onclick = () => { const d = $(`tr[data-detail="${tr.dataset.k}"]`, view); d.hidden = !d.hidden; }));
}

// ================================================================ BÁO CÁO
async function pageReport(view) {
  const r = await api("/api/report");
  view.innerHTML = `
  <div class="page-head"><div><h1>Báo cáo kênh</h1><p class="muted">Lượt xem/ngày và % giữ chân theo chủ đề — dựa trên video đã đăng qua công cụ.</p></div>
    <button class="btn primary" id="fetch">🔄 Cập nhật số liệu YouTube</button></div>
  <div class="card"><pre style="white-space:pre-wrap;margin:0;font:inherit">${esc(r.text)}</pre></div>
  <div class="notice info" style="margin-top:16px">Cách đọc: so các video của chính kênh bạn với nhau. CTR thấp → đổi phương án thumbnail. Giữ chân &lt; 25% → nghe lại hook. Chủ đề vượt trội sau ~10 video → bật “Tự dồn sản lượng” trong Cài đặt.</div>`;
  $("#fetch").onclick = () => safe(async () => {
    const task = await api("/api/tasks", { kind: "report" });
    openModal(`<h2>Cập nhật số liệu</h2><div id="task-log"></div>`);
    watchTask(task.id, $("#task-log"), () => pageReport(view));
  });
}

// ================================================================ CÀI ĐẶT
const KEY_INFO = {
  ANTHROPIC_API_KEY: ["Claude (dịch, viết hook, đặt tên)", "console.anthropic.com → API Keys"],
  GEMINI_API_KEY: ["Google AI (vẽ ảnh Imagen / dịch bằng Gemini)", "aistudio.google.com → Get API key"],
  GROQ_API_KEY: ["Groq (bóc băng trên cloud, có miễn phí)", "console.groq.com → API Keys"],
  GOOGLE_TTS_API_KEY: ["Google Cloud TTS (giọng Chirp 3 HD)", "console.cloud.google.com → bật Text-to-Speech API → Credentials"],
  ELEVENLABS_API_KEY: ["ElevenLabs (giọng biểu cảm)", "elevenlabs.io → Profile → API Keys"],
  TELEGRAM_BOT_TOKEN: ["Bot Telegram (duyệt bằng điện thoại)", "nhắn @BotFather → /newbot"],
};

async function pageSettings(view) {
  const { config: c, keys } = await api("/api/config");
  const sel = (path, options, value) => `<select data-path="${path}">${options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(value) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  const txt = (path, value, ph = "", type = "text") => `<input type="${type}" data-path="${path}" value="${esc(value ?? "")}" placeholder="${esc(ph)}">`;
  const chk = (path, value, label) => `<label class="switch"><input type="checkbox" data-path="${path}" ${value ? "checked" : ""}><span>${label}</span></label>`;
  const fld = (label, inner, hint = "") => `<div class="field"><label class="f">${label}</label>${inner}${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;

  view.innerHTML = `
  <div class="page-head"><div><h1>Cài đặt</h1><p class="muted">Lưu vào config.yaml và .env trong thư mục công cụ. Tùy chọn nâng cao: xem config.example.yaml.</p></div>
    <div class="row"><button class="btn" id="doctor">🩺 Kiểm tra</button><button class="btn" id="brand">🎨 Xem trước nhận diện</button><button class="btn primary" id="save">💾 Lưu cài đặt</button></div></div>
  <div class="grid g2">
    <div class="stack">
      <div class="card"><h2>Kênh</h2>
        ${fld("Tên kênh", txt("channel.name", c.channel.name))}
        ${fld("Mẫu tiêu đề", txt("channel.title_template", c.channel.title_template), "Biến: {story_title} {channel_name} {episode}")}
        ${fld("Link đăng ký kênh (hiện trong mô tả)", txt("channel.subscribe_url", c.channel.subscribe_url, "https://www.youtube.com/@tenkenh?sub_confirmation=1"))}
      </div>
      <div class="card"><h2>Chủ đề</h2><p class="muted small">Kênh mới nên bật 1–2 chủ đề. Xem mục Thị trường để chọn theo dữ liệu.</p>
        ${c.topics.map((t) => `<label class="switch"><input type="checkbox" data-topic="${esc(t.name)}" ${t.enabled === false ? "" : "checked"}><span>${esc(t.label || t.name)}</span></label>`).join("")}
      </div>
      <div class="card"><h2>Chất lượng & hook</h2>
        ${chk("quality.enabled", c.quality.enabled, "Chấm điểm truyện, loại truyện yếu/dở dang")}
        ${fld("Điểm tối thiểu (thang 10)", txt("quality.min_score", c.quality.min_score, "", "number"), "6,5 mặc định; tăng lên 7 khi nguồn truyện dồi dào")}
        ${chk("hook.enabled", c.hook.enabled, "Mở đầu video bằng hook 2–5 phút")}
        <div class="grid g2">${fld("Hook tối thiểu (phút)", txt("hook.min_minutes", c.hook.min_minutes, "", "number"))}${fld("Hook tối đa (phút)", txt("hook.max_minutes", c.hook.max_minutes, "", "number"))}</div>
        ${chk("tiktok.enabled", c.tiktok.enabled, "Tạo clip TikTok từ hook")}
        ${chk("shorts.enabled", c.shorts.enabled, "Tạo YouTube Shorts")}
      </div>
      <div class="card"><h2>Chạy tự động</h2>
        ${fld("Số video mỗi chủ đề mỗi lượt", txt("auto.per_topic", c.auto.per_topic, "", "number"))}
        ${chk("auto.adaptive", c.auto.adaptive, "Tự dồn sản lượng cho chủ đề ăn khách (cần đăng YouTube tự động)")}
        ${fld("Tổng video mỗi lượt khi tự dồn", txt("auto.daily_total", c.auto.daily_total, "", "number"))}
      </div>
    </div>
    <div class="stack">
      <div class="card"><h2>AI & giọng đọc</h2>
        ${fld("Mô hình dịch & viết", sel("llm.model", [["claude-opus-5-5", "Claude Opus 5.5 — tốt nhất"], ["claude-sonnet-5-5", "Claude Sonnet 5.5 — rẻ hơn ~½"], ["gemini-2.5-pro", "Gemini 2.5 Pro"]], c.llm.model))}
        ${fld("Bóc băng tiếng Trung", sel("asr.engine", [["groq", "Groq cloud (máy yếu, có miễn phí)"], ["local", "Trên máy (cần card NVIDIA)"], ["gemini", "Gemini cloud"]], c.asr.engine))}
        ${fld("Giọng đọc", sel("tts.engine", [["edge", "Edge — miễn phí (giọng phổ biến)"], ["google", "Google Chirp 3 HD — tự nhiên, khuyên dùng"], ["elevenlabs", "ElevenLabs — biểu cảm, đắt"]], c.tts.engine))}
        <div class="grid g2">${fld("Giọng Edge", txt("tts.voice", c.tts.voice))}${fld("Giọng Google", txt("tts.google.voice", c.tts.google?.voice))}</div>
        ${fld("ElevenLabs voice_id", txt("tts.elevenlabs.voice_id", c.tts.elevenlabs?.voice_id))}
        <p class="hint">Mỗi chủ đề có thể đặt giọng riêng trong config.yaml (mục topics). Xem danh sách giọng: <code>python -m autovideo voices --engine google</code></p>
        ${fld("Vẽ ảnh thumbnail", sel("thumbnail.image_engine", [["cloud", "Google Imagen (cloud) — khuyên dùng"], ["comfyui", "ComfyUI trên máy"], ["placeholder", "Ảnh giữ chỗ (chỉ để thử)"]], c.thumbnail.image_engine))}
      </div>
      <div class="card"><h2>Duyệt & đăng</h2>
        ${chk("review.enabled", c.review.enabled, "Gửi video về Telegram để duyệt bằng điện thoại")}
        <div class="grid g2">${fld("Chat ID Telegram", txt("review.chat_id", c.review.chat_id, "nhắn /id cho bot"))}${fld("Giờ tự chạy hằng ngày", txt("review.daily_run", c.review.daily_run, "02:00"))}</div>
        ${chk("youtube.enabled", c.youtube.enabled, "Tự upload YouTube khi bấm Đăng")}
        ${fld("Khung giờ hẹn đăng", `<input type="text" data-path="youtube.schedule_slots" data-list="1" value="${esc((c.youtube.schedule_slots || []).join(", "))}">`, "Cách nhau dấu phẩy, ví dụ 19:30, 21:30")}
        ${chk("shorts.upload", c.shorts.upload, "Đăng Shorts kèm link sang video dài khi đăng")}
      </div>
      <div class="card"><h2>Khóa API</h2><p class="muted small">Lưu vào file .env trên máy bạn. Để trống = giữ khóa cũ.</p>
        ${Object.entries(KEY_INFO).map(([k, [name, how]]) => `<div class="field"><label class="f">${name} ${keys[k] ? '<span class="pill ok">✔ đã có</span>' : '<span class="pill">chưa có</span>'}</label>
          <input type="password" data-key="${k}" placeholder="${keys[k] ? "•••••••• (đã lưu)" : k}" autocomplete="off"><div class="hint">${how}</div></div>`).join("")}
        <button class="btn" id="save-keys">🔑 Lưu khóa</button>
      </div>
    </div>
  </div>`;

  const collect = () => {
    const patch = {};
    $$("[data-path]", view).forEach((el) => {
      let v = el.type === "checkbox" ? el.checked : el.value;
      if (el.type === "number") v = v === "" ? null : Number(v);
      if (el.dataset.list) v = v.split(",").map((x) => x.trim()).filter(Boolean);
      if (v === "" && el.type !== "checkbox") v = null;
      const parts = el.dataset.path.split(".");
      let o = patch;
      parts.slice(0, -1).forEach((p) => (o = o[p] = o[p] || {}));
      o[parts.at(-1)] = v;
    });
    if (patch.llm) patch.llm.provider = String(patch.llm.model).startsWith("gemini") ? "gemini" : "anthropic";
    patch.topics_enabled = Object.fromEntries($$("[data-topic]", view).map((el) => [el.dataset.topic, el.checked]));
    return patch;
  };
  $("#save").onclick = () => safe(async () => { await api("/api/config", collect()); toast("Đã lưu cài đặt"); refreshShell(); });
  $("#save-keys").onclick = () => safe(async () => {
    const vals = Object.fromEntries($$("[data-key]", view).map((el) => [el.dataset.key, el.value]).filter(([, v]) => v.trim()));
    if (!Object.keys(vals).length) throw new Error("Chưa nhập khóa nào");
    await api("/api/env", vals);
    toast("Đã lưu khóa API");
    pageSettings(view);
  });
  $("#doctor").onclick = () => startTask({ kind: "doctor", online: confirm("Gọi thử thật các dịch vụ (LLM, giọng đọc, Telegram)? Tốn vài đồng.\nOK = gọi thử · Hủy = chỉ kiểm tra cài đặt") }, "Kiểm tra cài đặt");
  $("#brand").onclick = () => safe(async () => {
    const real = confirm("Vẽ ảnh nền thật bằng AI (tốn phí ảnh)?\nOK = vẽ thật · Hủy = dùng ảnh giữ chỗ");
    const task = await api("/api/tasks", { kind: "brand", real });
    openModal(`<h2>Xem trước nhận diện kênh</h2><div id="task-log"></div><div id="brand-img"></div>`);
    watchTask(task.id, $("#task-log"), (t) => {
      if (t.status === "done") $("#brand-img").innerHTML = `<img style="width:100%;border-radius:12px;margin-top:12px" src="${fileUrl("output/brand_preview/index.jpg", Date.now())}">`;
    });
  });
}

// ---------------------------------------------------------------- khởi động
route();
refreshShell();
