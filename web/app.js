// 拼豆工坊前端逻辑
let META = null;
const state = { tier: "主力款", style: "classic", styles: [], compareMode: false, file: null, orderId: null };

const $ = id => document.getElementById(id);

async function init() {
  const r = await fetch("/api/meta");
  META = await r.json();
  renderTiers();
  renderStyles();
  renderColorcards();
  bindUpload();
  $("compare-mode").addEventListener("change", e => {
    state.compareMode = e.target.checked;
    state.styles = [];
    renderStyles();
    $("generate-btn").textContent = e.target.checked ? "⚡ 批量生成对比" : "⚡ 一键生成拼豆图纸";
  });
  $("generate-btn").addEventListener("click", generate);
  bindFeedbackSave();
  bindTune();
  bindHot();
  bindBilling();
  loadPackages();
  loadHotspot();
}

function renderTiers() {
  const box = $("tiers");
  box.innerHTML = "";
  Object.entries(META.tiers).forEach(([name, t]) => {
    const d = document.createElement("div");
    d.className = "tier-card" + (name === state.tier ? " active" : "");
    d.innerHTML = `
      <div class="price">¥${t.price}</div>
      <div class="tname">${name}</div>
      <div class="tdesc">${t.desc}</div>
      <div class="feat">${t.features.join(" · ")}</div>`;
    d.onclick = () => { state.tier = name; document.querySelectorAll(".tier-card").forEach(x => x.classList.remove("active")); d.classList.add("active"); };
    box.appendChild(d);
  });
}

// 风格色板预览圆点
const SWATCH = {
  classic: ["#2b2b2b","#e85d3f","#3f7de8","#f4c542","#7fb069"],
  chibi_pastel: ["#f7c8d8","#c8e6f5","#f8e7b5","#d5f0d5","#f0d0f0"],
  retro8bit: ["#ff004d","#00e436","#29adff","#ffa300","#5a4fcf"],
  minimal: ["#2b2b2b","#f5f5f5","#999999"],
  neon: ["#0a0a1a","#ff2fd6","#00f0ff","#b026ff"],
  popart: ["#ff3855","#ffb300","#1cade4","#0ebd76"],
  crayon: ["#e57373","#ffb74d","#fff176","#81c784"],
  watercolor: ["#aed6f1","#f9e79f","#d7bde2","#a9dfbf"],
  festive: ["#c0392b","#27ae60","#f1c40f","#ffffff"],
  mono: ["#1a1a1a","#808080","#d9d9d9","#ffffff"],
  dither: ["#333","#888","#bbb","#222"],
  vaporwave: ["#ff71ce","#01cdfe","#05ffa1","#b967ff"],
  inkwash: ["#f5f5f0","#8a8a80","#3a3a34","#1a1a16"],
  comic: ["#ff3855","#ffb300","#1cade4","#0ebd76","#000"],
  kawaii: ["#ffb6c1","#ffe4e1","#f8e7b5","#d5f0d5","#ffd1dc"],
  stainedglass: ["#2b2b2b","#7b241c","#1a5276","#196f3d","#7d6608"],
  embroider: ["#d5c8b0","#a89070","#7a6a55","#e8dcc8"],
  halloween: ["#1a1a1a","#ff8c00","#9b59b6","#27ae60"],
  pixel_pet: ["#e8a87c","#c97b4a","#8b5a2b","#f5d0a9"],
};

function renderStyles() {
  const box = $("styles");
  box.innerHTML = "";
  const health = META.style_health || {};
  // 排序：降级推荐置后
  const order = Object.entries(META.styles).sort((a, b) => {
    const la = (health[a[0]] || {}).level, lb = (health[b[0]] || {}).level;
    const rank = { bad: 3, caution: 2, insufficient: 1, good: 0, undefined: 1 };
    return (rank[la] ?? 1) - (rank[lb] ?? 1);
  });
  order.forEach(([id, s]) => {
    const d = document.createElement("div");
    const active = state.compareMode ? state.styles.includes(id) : (id === state.style);
    const h = health[id] || {};
    const cls = ["style-btn", active ? "active" : "", h.level === "bad" ? "health-bad" : "", h.level === "caution" ? "health-caution" : ""].join(" ").trim();
    d.className = cls;
    const sw = (SWATCH[id] || ["#ccc"]).map(c => `<span class="style-swatch" style="background:${c}"></span>`).join("");
    let badge = "";
    if (h.level === "bad") badge = `<span class="h-badge h-bad">⚠️ 降级推荐</span>`;
    else if (h.level === "caution") badge = `<span class="h-badge h-caution">需谨慎</span>`;
    else if (h.level === "good") badge = `<span class="h-badge h-good">👍 好评</span>`;
    const hint = h.level === "bad" && h.top_reason ? `<div class="sdesc h-reason">常反馈: ${h.top_reason} (${h.unsatisfied_rate}%)</div>` : "";
    d.innerHTML = `${sw}<div class="sname">${s.name} ${badge}</div><div class="sdesc">${s.desc}</div>${hint}`;
    d.onclick = () => {
      if (state.compareMode) {
        const i = state.styles.indexOf(id);
        if (i >= 0) state.styles.splice(i, 1); else if (state.styles.length < 3) state.styles.push(id);
        renderStyles();
      } else {
        state.style = id;
        document.querySelectorAll(".style-btn").forEach(x => x.classList.remove("active"));
        d.classList.add("active");
      }
    };
    box.appendChild(d);
  });
}

function renderColorcards() {
  const sel = $("colorcard");
  sel.innerHTML = "";
  Object.entries(META.colorcards).forEach(([id, c]) => {
    const o = document.createElement("option");
    o.value = id;
    o.textContent = `${c.brand}（${c.color_count}色）`;
    sel.appendChild(o);
  });
}

function bindUpload() {
  const dz = $("dropzone"), input = $("file-input");
  dz.onclick = () => input.click();
  input.onchange = e => setFile(e.target.files[0]);
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("drag"); };
  dz.ondragleave = () => dz.classList.remove("drag");
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("drag"); setFile(e.dataTransfer.files[0]); };
  $("change-btn").onclick = () => input.click();
}

function setFile(f) {
  if (!f) return;
  state.file = f;
  $("preview-img").src = URL.createObjectURL(f);
  $("preview-wrap").hidden = false;
  $("dropzone").hidden = true;
  if (!$("subject").value) {
    // 简单猜测主题
    $("subject").value = f.name.replace(/\.[^.]+$/, "") || "宠物";
  }
}

async function generate() {
  if (!state.file) { alert("请先上传图片"); return; }
  const btn = $("generate-btn");
  btn.disabled = true;
  $("progress").hidden = false;
  $("result-card").hidden = true;
  setFill(15); $("status-text").textContent = "上传图片…";

  const fd = new FormData();
  fd.append("file", state.file);
  fd.append("tier", state.tier);
  fd.append("style", state.style);
  fd.append("width", $("width").value || "");
  fd.append("colors", $("colors").value || "");
  fd.append("colorcard", $("colorcard").value);
  fd.append("bead", $("bead").value);
  fd.append("subject", $("subject").value || "宠物");
  fd.append("title", $("title").value || "");
  fd.append("do_qc", $("qc").checked ? "true" : "false");

  setFill(30); $("status-text").textContent = "AI 像素化中（约 30-60 秒）…";
  try {
    const r = await fetch("/api/generate", { method: "POST", body: fd });
    setFill(85);
    const res = await r.json();
    if (!r.ok || !res.success) {
      throw new Error(res.error || "生成失败");
    }
    setFill(100); $("status-text").textContent = "完成！";
    state.orderId = res.order_id;
    renderResult(res);
    renderLessons(res.lessons);
    $("result-card").hidden = false;
    if (state.compareMode && state.styles.length > 1) {
      const rest = state.styles.filter(s => s !== state.style);
      for (const s of rest) {
        $("status-text").textContent = "对比模式: 生成 " + s + " …";
        const fd2 = new FormData();
        fd2.append("file", state.file);
        fd2.append("tier", state.tier);
        fd2.append("style", s);
        fd2.append("width", $("width").value || "");
        fd2.append("colors", $("colors").value || "");
        fd2.append("colorcard", $("colorcard").value);
        fd2.append("bead", $("bead").value);
        fd2.append("subject", $("subject").value || "宠物");
        fd2.append("do_qc", $("qc").checked ? "true" : "false");
        const r2 = await fetch("/api/generate", { method: "POST", body: fd2 });
        const res2 = await r2.json();
        if (res2.success) appendResult(res2);
      }
      $("status-text").textContent = "对比完成！";
    }
  } catch (e) {
    $("status-text").textContent = "❌ " + e.message;
    setFill(0);
  } finally {
    btn.disabled = false;
    setTimeout(() => { $("progress").hidden = true; }, 1200);
  }
}

function setFill(p) { $("fill").style.width = p + "%"; }

// 历史经验建议展示（反馈学习闭环）
function renderLessons(lessons) {
  const box = $("lessons-box");
  if (!lessons || !lessons.hit_count) { box.hidden = true; return; }
  const L = lessons;
  box.hidden = false;
  let html = `<div class="lessons-title">📚 历史经验提醒（${L.hit_count} 条相关不满意案例，主要问题：${L.top_reason} ×${L.top_reason_count}）</div>`;
  if (L.lessons.length) html += `<div class="lesson-item">💡 经验：${L.lessons.map(l => "「" + l + "」").join("；")}</div>`;
  if (L.actions.length) html += `<div class="lesson-item">🔧 上次做法：${L.actions.map(a => "「" + a + "」").join("；")}</div>`;
  box.innerHTML = html;
}

// 人工微调
function bindTune() {
  const doTune = async (action, colors) => {
    if (!state.orderId) { alert("先生成订单"); return; }
    $("tune-status").textContent = "重生成中…";
    const fd = new FormData();
    fd.append("order_id", state.orderId);
    fd.append("action", action);
    if (colors) fd.append("colors", colors);
    const r = await fetch("/api/tune", { method: "POST", body: fd });
    const res = await r.json();
    if (res.success) {
      $("tune-status").textContent = "✅ 已重生成: " + res.order_id;
      state.orderId = res.order_id;
      renderResult(res);
      renderLessons(res.lessons);
    } else {
      $("tune-status").textContent = "❌ " + (res.error || "失败");
    }
  };
  $("tune-denoise").onclick = () => doTune("denoise");
  $("tune-reduce8").onclick = () => doTune("reduce_colors", 8);
  $("tune-reduce12").onclick = () => doTune("reduce_colors", 12);
}

// 反馈保存
function bindFeedbackSave() {
  $("fb-save").addEventListener("click", async () => {
    if (!state.orderId) { alert("请先生成订单"); return; }
    const fd = new FormData();
    fd.append("order_id", state.orderId);
    fd.append("satisfied", $("fb-satisfied").value);
    fd.append("reason", $("fb-reason").value || "");
    fd.append("detail", $("fb-detail").value || "");
    fd.append("action", $("fb-action").value || "");
    fd.append("lesson", $("fb-lesson").value || "");
    const r = await fetch("/api/feedback", { method: "POST", body: fd });
    const res = await r.json();
    $("fb-status").textContent = res.success ? "✅ 已保存到经验库" : "❌ 保存失败";
    setTimeout(() => { $("fb-status").textContent = ""; }, 3000);
  });
}

function appendResult(res) {
  const IMG_LABEL = { "1_施工主图.png": "施工主图", "4_成品预览.png": "成品预览" };
  const h = document.createElement("div");
  h.className = "compare-block";
  h.innerHTML = `<div class="cmp-title">订单 ${res.order_id} · ${res.grid} · ${res.colors}色</div><div class="gallery-row"></div>`;
  const row = h.querySelector(".gallery-row");
  res.files.forEach(fn => {
    if (!IMG_LABEL[fn]) return;
    const d = document.createElement("div");
    d.className = "g-item";
    d.innerHTML = `<img src="/api/orders/${res.order_id}/delivery/${encodeURIComponent(fn)}"><div class="g-label"><span>${IMG_LABEL[fn]}</span><a href="/api/orders/${res.order_id}/delivery/${encodeURIComponent(fn)}" download>下载</a></div>`;
    row.appendChild(d);
  });
  $("gallery").appendChild(h);
}

function renderResult(res) {
  $("result-meta").innerHTML = `
    订单 <b>${res.order_id}</b> · 网格 <b>${res.grid}</b> · <b>${res.colors}</b> 色 · <b>${res.total}</b> 颗
    ${res.qc ? (res.qc.passed ? " · 🟢 质检通过" : " · 🔴 质检未通过") : ""}
  `;
  const gallery = $("gallery");
  gallery.innerHTML = "";
  const IMG_LABEL = {
    "1_施工主图.png": "施工主图（坐标+色号）",
    "2_色卡与用量统计.png": "色卡与用量",
    "4_成品预览.png": "成品预览",
    "5_小红书素材_对比图.png": "小红书对比图",
  };
  res.files.forEach(fn => {
    if (!IMG_LABEL[fn]) return;
    const d = document.createElement("div");
    d.className = "g-item";
    d.innerHTML = `<img src="/api/orders/${res.order_id}/delivery/${encodeURIComponent(fn)}"><div class="g-label"><span>${IMG_LABEL[fn]}</span><a href="/api/orders/${res.order_id}/delivery/${encodeURIComponent(fn)}" download>下载</a></div>`;
    gallery.appendChild(d);
  });
  $("downloads").innerHTML = `<a class="primary" href="/api/orders/${res.order_id}/zip">📦 下载完整交付包 (zip)</a>`;
}


// ===== 三轨计费 =====
async function loadPackages() {
  try {
    const r = await fetch("/api/credits/packages");
    const d = await r.json();
    const box = $("bill-packages");
    box.innerHTML = Object.entries(d.packages).map(([k, p]) => `
      <div class="pkg-card">
        <div class="pkg-name">${k}</div>
        <div class="pkg-price">¥${p.price}</div>
        <div class="pkg-desc">${p.desc}</div>
        <button class="mini-btn bill-buy" data-pkg="${k}">收款后充值</button>
      </div>`).join("");
    box.querySelectorAll(".bill-buy").forEach(b => {
      b.onclick = async () => {
        const name = $("bill-name").value.trim();
        if (!name) { alert("先填客户名"); return; }
        const pkg = b.dataset.pkg;
        const ok = confirm(`确认 ${name} 已支付 ¥${d.packages[pkg].price} 购买 ${pkg}？`);
        if (!ok) return;
        const fd = new FormData();
        fd.append("name", name); fd.append("package", pkg);
        const r2 = await fetch("/api/credits/purchase", { method: "POST", body: fd });
        const res = await r2.json();
        if (res.success) {
          alert(`充值成功！${name} 剩余 ${res.credits} 次${res.member_until ? '，会员至 ' + res.member_until.slice(0,10) : ''}`);
          refreshBill();
        } else alert("失败: " + res.error);
      };
    });
    loadAllCustomers();
  } catch (e) { $("bill-packages").innerHTML = '<p class="hint">计费加载失败</p>'; }
}

async function loadAllCustomers() {
  try {
    const r = await fetch("/api/credits/all");
    const d = await r.json();
    const box = $("bill-all");
    const rows = Object.entries(d.customers).map(([n, c]) => `
      <div class="cust-row">${c.note || n} | 次数: <b>${c.credits}</b> | 会员: ${c.member_until ? "✅至" + c.member_until.slice(0,10) : "❌"} | 累计: ¥${c.total_spent}</div>`).join("");
    box.innerHTML = rows ? `<div class="cust-title">客户台账</div>${rows}` : '<p class="hint">暂无客户记录</p>';
  } catch (e) {}
}

async function refreshBill() {
  const name = $("bill-name").value.trim();
  $("bill-status").innerHTML = "";
  if (!name) { loadAllCustomers(); return; }
  try {
    const r = await fetch("/api/credits/check?name=" + encodeURIComponent(name));
    const d = await r.json();
    $("bill-status").innerHTML = d.success ? `${d.note || name}: 次数 <b>${d.credits}</b> | 会员 ${d.is_member ? "✅" + (d.member_until || "").slice(0,10) : "❌"}` : "客户不存在";
  } catch (e) {}
}

function bindBilling() {
  $("bill-check").onclick = refreshBill;
  $("credits-refresh").onclick = () => { loadPackages(); refreshBill(); };
}

// ===== 热点雷达 =====
async function loadHotspot() {
  try {
    const [h, g] = await Promise.all([
      fetch("/api/hotspots").then(r => r.json()),
      fetch("/api/hotgallery").then(r => r.json()),
    ]);
    HOT_STATE.items = h.items || [];
    renderCatTabs(HOT_STATE.items);
    renderTrending(HOT_STATE.items);
    renderHotGallery(g.items || []);
  } catch (e) {
    $("hot-trending").innerHTML = '<p class="hint">热点加载失败: ' + e.message + '</p>';
  }
}

let HOT_STATE = { items: [], cat: "全部" };

function renderCatTabs(items) {
  const box = $("hot-cats");
  const counts = {};
  items.forEach(it => { const c = it.category || "其他"; counts[c] = (counts[c] || 0) + 1; });
  // 抖音式：按数量降序，全部在最前
  const cats = ["全部", ...Object.keys(counts).sort((a, b) => counts[b] - counts[a])];
  box.innerHTML = cats.map(c => {
    const n = c === "全部" ? items.length : (counts[c] || 0);
    return `<span class="cat-tab${c === HOT_STATE.cat ? " active" : ""}" data-cat="${c}">${c} <b>${n}</b></span>`;
  }).join("");
  box.querySelectorAll(".cat-tab").forEach(tab => {
    tab.onclick = () => { HOT_STATE.cat = tab.dataset.cat; renderCatTabs(HOT_STATE.items); renderTrending(HOT_STATE.items); };
  });
}

function renderTrending(items) {
  const box = $("hot-trending");
  if (!items.length) { box.innerHTML = '<p class="hint">暂无热点，点"刷新热点"抓取</p>'; return; }
  const shown = HOT_STATE.cat === "全部" ? items : items.filter(it => (it.category || "其他") === HOT_STATE.cat);
  if (!shown.length) { box.innerHTML = '<p class="hint">该分类暂无热点</p>'; return; }
  const sorted = [...shown].sort((a, b) => (b.heat || 0) - (a.heat || 0));
  box.innerHTML = sorted.map((it, i) => `
    <div class="hot-item" data-word="${it.word}" data-char="${it.character || ''}">
      <span class="hot-rank">${i + 1}</span>
      <span class="hot-word">${it.word}</span>
      <span class="hot-char">${it.character || ''}</span>
      <span class="hot-cat-badge">${it.category || ''}</span>
      <span class="hot-src">${it.source}</span>
      <span class="hot-heat">${it.heat ? '🔥' + it.heat.toLocaleString() : ''}</span>
      <button class="mini-btn gen-one">出图</button>
    </div>`).join("");
  box.querySelectorAll(".gen-one").forEach(btn => {
    btn.onclick = async e => {
      const row = e.target.closest(".hot-item");
      const kw = row.dataset.word, ch = row.dataset.char;
      btn.disabled = true; btn.textContent = "生成中…";
      const fd = new FormData();
      fd.append("keyword", kw); fd.append("character", ch);
      fd.append("styles", "classic,chibi_pastel");
      try {
        const r = await fetch("/api/hotgallery/generate", { method: "POST", body: fd });
        const res = await r.json();
        btn.textContent = res.success ? "✅ 已出图" : "❌ " + (res.error || "失败");
        if (res.success) loadHotspot();
      } catch (err) { btn.textContent = "❌ 失败"; }
      setTimeout(() => { btn.disabled = false; btn.textContent = "出图"; }, 3000);
    };
  });
}

function renderHotGallery(items) {
  const box = $("hot-gallery");
  if (!items.length) { box.innerHTML = '<p class="hint">热点图纸库为空——刷新热点后点"给热点批量出图"</p>'; return; }
  box.innerHTML = items.map(g => `
    <div class="hot-g-item">
      <div class="hot-g-title">${g.character || g.keyword} <span class="hint">${g.styles.length}风格</span> <button class="mini-btn xy-export" data-char="${g.character || ''}" data-kw="${g.keyword || ''}">🐟 导出闲鱼物料</button></div>
      <div class="hot-g-styles">
        ${g.styles.map(s => `
          <div class="hot-g-style">
            <span class="hint">${s.style}</span>
            <span class="hint">${s.grid} · QC ${s.qc ? '✅' : '❌'}</span>
            <a href="/api/orders/${s.order_id}/zip" class="mini-link">📦</a>
          </div>`).join("")}
      </div>
    </div>`).join("");
  box.querySelectorAll(".xy-export").forEach(btn => {
    btn.onclick = async () => {
      btn.disabled = true; btn.textContent = "导出中…";
      const fd = new FormData();
      fd.append("keyword", btn.dataset.kw || "");
      fd.append("character", btn.dataset.char || "");
      try {
        const r = await fetch("/api/xianyu/export", { method: "POST", body: fd });
        const res = await r.json();
        btn.textContent = res.success ? "✅ 已导出到 xianyu_posts/" : "❌ " + (res.error || "失败");
      } catch (e) { btn.textContent = "❌ 失败"; }
      setTimeout(() => { btn.disabled = false; btn.textContent = "🐟 导出闲鱼物料"; }, 3000);
    };
  });
}

function bindHot() {
  $("hot-refresh").onclick = async () => {
    $("hot-refresh").disabled = true;
    $("hot-refresh").textContent = "抓取中…";
    try {
      const r = await fetch("/api/hotspots/refresh", { method: "POST" });
      const res = await r.json();
      alert("热点刷新完成: " + res.count + " 条（动漫/影视/角色类）");
      loadHotspot();
    } catch (e) { alert("刷新失败: " + e.message); }
    $("hot-refresh").disabled = false;
    $("hot-refresh").textContent = "🔄 刷新热点";
  };
  $("hot-add").onclick = async () => {
    const word = $("hot-word").value.trim();
    if (!word) { alert("请输入热点词"); return; }
    const fd = new FormData();
    fd.append("word", word);
    fd.append("character", $("hot-char").value.trim());
    fd.append("category", $("hot-cat").value);
    const r = await fetch("/api/hotspots/add", { method: "POST", body: fd });
    const res = await r.json();
    if (res.success) {
      $("hot-word").value = ""; $("hot-char").value = "";
      alert("已添加，可立即出图");
      loadHotspot();
    }
  };
  $("hot-batch").onclick = async () => {
    const items = (await fetch("/api/hotspots").then(r => r.json())).items || [];
    if (!items.length) { alert("先刷新热点"); return; }
    $("hot-batch").disabled = true;
    $("hot-batch").textContent = "批量出图中…";
    for (let i = 0; i < Math.min(items.length, 3); i++) {
      const it = items[i];
      const fd = new FormData();
      fd.append("keyword", it.word); fd.append("character", it.character || "");
      fd.append("styles", "classic,chibi_pastel");
      try { await fetch("/api/hotgallery/generate", { method: "POST", body: fd }); } catch (e) {}
    }
    $("hot-batch").disabled = false;
    $("hot-batch").textContent = "⚡ 给热点批量出图";
    loadHotspot();
  };
}

init();
