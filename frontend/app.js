const TAB_TITLES = {
  india: "India market",
  us: "US market",
};

const TAB_SUBTITLES = {
  india: "Amazon.in · Flipkart · Google Trends (India)",
  us: "Amazon.com · TikTok Shop (US signals for India)",
};

const GLOBAL_BUCKET_LABELS = {
  already_available_in_india: "Already in India",
  not_yet_available_in_india: "Not yet in India",
  watch_only: "Watch only",
};

const GLOBAL_SOURCE_LABELS = {
  amazon_us: "Amazon US",
  tiktok_shop_us: "TikTok Shop US",
};

const ACTION_LABELS = {
  BUY_TEST: "Priority buy",
  WATCHLIST: "Top pick",
  MONITOR: "On radar",
  IGNORE: "Low priority",
  REVIEW_MANUALLY: "Needs review",
};

const QUICK_FILTERS = [
  { id: "hot", label: "Top picks", test: (r) => ["BUY_TEST", "WATCHLIST"].includes(r.recommended_action) },
  { id: "breakout", label: "Hot momentum", test: (r) => r.trend_tier === "breakout" },
  { id: "rising", label: "Growing", test: (r) => r.trend_tier === "rising" },
  { id: "cross", label: "Both marketplaces", test: (r) => (r.sources || "").includes("amazon") && (r.sources || "").includes("flipkart") },
  { id: "priced", label: "Prices on both", test: (r) => Number(r.amazon_price_inr) > 0 && Number(r.flipkart_price_inr) > 0 },
];

const GLOBAL_QUICK_FILTERS = [
  { id: "white_space", label: "Not in India yet", test: (r) => r.global_opportunity_bucket === "not_yet_available_in_india" },
  { id: "in_india", label: "Already in India", test: (r) => r.global_opportunity_bucket === "already_available_in_india" },
  { id: "rated", label: "4.5+ rating", test: (r) => Number(r.rating) >= 4.5 },
  { id: "reviewed", label: "10k+ reviews", test: (r) => Number(r.review_count) >= 10000 },
];

const state = {
  tab: "india",
  gold: [],
  global: [],
  goldPage: 0,
  goldPageSize: 48,
  goldQuick: null,
  globalQuick: null,
  globalPage: 0,
  globalPageSize: 48,
  view: "cards",
  searchTimer: null,
};

const multiSelectState = {
  goldCategory: new Set(),
  globalCategory: new Set(),
  globalBucket: new Set(),
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function fmt(val) {
  if (val === null || val === undefined || val === "" || Number.isNaN(val)) return "—";
  return val;
}

function fmtNum(val, digits = 1) {
  const n = Number(val);
  if (!Number.isFinite(n)) return "—";
  if (n === 0 && digits > 0) return "0";
  return n.toLocaleString("en-IN", { maximumFractionDigits: digits });
}

function fmtPct(val) {
  const n = Number(val);
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(n * 100)}%`;
}

function fmtPrice(val) {
  const n = Number(val);
  if (!Number.isFinite(n) || n <= 0) return "—";
  return `₹${n.toLocaleString("en-IN")}`;
}

function fmtPriceUsd(val, currency) {
  const n = Number(val);
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (!currency || currency === "USD") {
    return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `${currency} ${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtCategory(cat) {
  return String(cat || "").replace(/_/g, " ");
}

function fmtAction(action) {
  return ACTION_LABELS[action] || action || "—";
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

function scoreClass(score) {
  const n = Number(score) || 0;
  if (n >= 80) return "score-hot";
  if (n >= 65) return "score-good";
  if (n >= 45) return "score-mid";
  return "score-low";
}

function imgOrPlaceholder(url, alt) {
  if (url && String(url).startsWith("http")) {
    return `<img src="${escapeAttr(url)}" alt="${escapeAttr(alt || "")}" loading="lazy" onerror="this.closest('.card-img').innerHTML='<span class=no-img>No image</span>'">`;
  }
  return '<span class="no-img">No image</span>';
}

function sourceBadges(sources) {
  const labels = { amazon: "Amazon", flipkart: "Flipkart", gtrends: "Google" };
  const list = String(sources || "").split("|").filter((s) => labels[s]);
  if (!list.length) return "";
  return `<div class="source-row">${list.map((s) => `<span class="badge badge-src ${escapeAttr(s)}">${labels[s]}</span>`).join("")}</div>`;
}

function signalBadges(codes) {
  const list = String(codes || "").split("|").filter(Boolean).slice(0, 3);
  if (!list.length) return "";
  const more = String(codes || "").split("|").filter(Boolean).length - list.length;
  return `<div class="signal-row">${list.map((c) => `<span class="badge badge-signal" title="${escapeAttr(c)}">${escapeHtml(c.replace(/_/g, " "))}</span>`).join("")}${more > 0 ? `<span class="badge badge-more">+${more}</span>` : ""}</div>`;
}

function inferSpecies(row, isGlobal = false) {
  if (isGlobal && row.species) return String(row.species).toLowerCase();
  const cat = String(row.category || "").toLowerCase();
  if (cat.startsWith("dog_")) return "dog";
  if (cat.startsWith("cat_")) return "cat";
  const title = String(row.canonical_title || row.product_title || "").toLowerCase();
  const hasDog = /\bdog(s)?\b/.test(title);
  const hasCat = /\bcat(s)?\b/.test(title);
  if (hasDog && hasCat) return "both";
  if (hasDog) return "dog";
  if (hasCat) return "cat";
  return "both";
}

function speciesMatches(filterSpecies, rowSpecies) {
  if (!filterSpecies) return true;
  if (filterSpecies === "both") return rowSpecies === "both";
  if (filterSpecies === "dog") return rowSpecies === "dog" || rowSpecies === "both";
  if (filterSpecies === "cat") return rowSpecies === "cat" || rowSpecies === "both";
  return true;
}

function setupMultiSelect(rootId, stateKey, onChange, formatLabel) {
  const root = $(`#${rootId}`);
  if (!root) return;
  const placeholder = root.dataset.placeholder || "All";
  const trigger = root.querySelector(".multi-select-trigger");
  const panel = root.querySelector(".multi-select-panel");
  const optionsEl = root.querySelector(".multi-select-options");
  const searchInput = root.querySelector(".multi-select-search");
  const labelEl = root.querySelector(".multi-select-label");
  const selected = multiSelectState[stateKey];

  const updateLabel = () => {
    if (!selected.size) {
      labelEl.textContent = placeholder;
      return;
    }
    if (selected.size === 1) {
      const val = [...selected][0];
      labelEl.textContent = formatLabel ? formatLabel(val) : fmtCategory(val);
      return;
    }
    labelEl.textContent = `${selected.size} selected`;
  };

  root._renderOptions = (items) => {
    if (!optionsEl) return;
    optionsEl.innerHTML = items.map((val) => {
      const checked = selected.has(val) ? "checked" : "";
      const label = formatLabel ? formatLabel(val) : fmtCategory(val);
      return `<label class="multi-select-option"><input type="checkbox" value="${escapeAttr(val)}" ${checked}><span>${escapeHtml(label)}</span></label>`;
    }).join("");
    optionsEl.querySelectorAll("input").forEach((cb) => {
      cb.addEventListener("change", () => {
        if (cb.checked) selected.add(cb.value);
        else selected.delete(cb.value);
        updateLabel();
        onChange();
      });
    });
    updateLabel();
  };

  optionsEl?.querySelectorAll("input").forEach((cb) => {
    cb.addEventListener("change", () => {
      if (cb.checked) selected.add(cb.value);
      else selected.delete(cb.value);
      updateLabel();
      onChange();
    });
  });

  trigger?.addEventListener("click", (e) => {
    e.stopPropagation();
    const willOpen = panel.hidden;
    $$(".multi-select-panel").forEach((p) => { p.hidden = true; });
    panel.hidden = !willOpen;
  });

  panel?.addEventListener("click", (e) => e.stopPropagation());

  searchInput?.addEventListener("input", () => {
    const q = searchInput.value.toLowerCase();
    optionsEl?.querySelectorAll(".multi-select-option").forEach((lab) => {
      lab.style.display = lab.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  });

  root.querySelector('[data-action="all"]')?.addEventListener("click", () => {
    optionsEl?.querySelectorAll("input").forEach((cb) => {
      cb.checked = true;
      selected.add(cb.value);
    });
    updateLabel();
    onChange();
  });

  root.querySelector('[data-action="none"]')?.addEventListener("click", () => {
    selected.clear();
    optionsEl?.querySelectorAll("input").forEach((cb) => { cb.checked = false; });
    if (searchInput) searchInput.value = "";
    updateLabel();
    onChange();
  });

  root._clear = () => {
    selected.clear();
    optionsEl?.querySelectorAll("input").forEach((cb) => { cb.checked = false; });
    if (searchInput) searchInput.value = "";
    updateLabel();
  };

  updateLabel();
}

function initMultiSelects() {
  setupMultiSelect("gold-category-ms", "goldCategory", () => { state.goldPage = 0; renderGold(); });
  setupMultiSelect("global-category-ms", "globalCategory", () => { state.globalPage = 0; renderGlobal(); });
  setupMultiSelect(
    "global-bucket-ms",
    "globalBucket",
    () => { state.globalPage = 0; renderGlobal(); },
    (val) => GLOBAL_BUCKET_LABELS[val] || val,
  );
}

function exportCsv(rows, columns, filename) {
  const esc = (v) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [columns.map((c) => esc(c.label)).join(",")];
  rows.forEach((r) => lines.push(columns.map((c) => esc(c.get(r))).join(",")));
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function paginate(rows, page, pageSize) {
  const total = rows.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(0, page), totalPages - 1);
  const start = safePage * pageSize;
  const end = Math.min(start + pageSize, total);
  return { rows: rows.slice(start, end), page: safePage, totalPages, total, start, end };
}

function renderPaginationBar(containerId, { page, totalPages, total, start, end }, onPage) {
  const el = $(`#${containerId}`);
  if (!el) return;
  if (total === 0) {
    el.innerHTML = "";
    return;
  }

  const pages = [];
  const window = 2;
  for (let i = 0; i < totalPages; i++) {
    if (i === 0 || i === totalPages - 1 || (i >= page - window && i <= page + window)) {
      pages.push(i);
    } else if (pages[pages.length - 1] !== "…") {
      pages.push("…");
    }
  }

  el.innerHTML = `
    <div class="pagination-info">Showing <strong>${start + 1}–${end}</strong> of <strong>${total.toLocaleString()}</strong></div>
    <div class="pagination-controls">
      <button class="page-btn" data-page="0" ${page === 0 ? "disabled" : ""} title="First">«</button>
      <button class="page-btn" data-page="${page - 1}" ${page === 0 ? "disabled" : ""}>Prev</button>
      ${pages.map((p) => p === "…"
    ? `<span class="page-ellipsis">…</span>`
    : `<button class="page-btn ${p === page ? "active" : ""}" data-page="${p}">${p + 1}</button>`).join("")}
      <button class="page-btn" data-page="${page + 1}" ${page >= totalPages - 1 ? "disabled" : ""}>Next</button>
      <button class="page-btn" data-page="${totalPages - 1}" ${page >= totalPages - 1 ? "disabled" : ""} title="Last">»</button>
    </div>`;

  el.querySelectorAll(".page-btn[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const next = Number(btn.dataset.page);
      if (!Number.isFinite(next) || btn.disabled) return;
      onPage(next);
      el.closest(".panel")?.querySelector(".toolbar")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  });
}

async function fetchJson(url, timeoutMs = 60000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctrl.signal, cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    if (err.name === "AbortError") throw new Error("Request timed out — restart serve_dashboard.py");
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function showApp() {
  $("#loading")?.setAttribute("hidden", "");
  $("#app")?.removeAttribute("hidden");
}

function showLoading() {
  $("#loading")?.removeAttribute("hidden");
  $("#app")?.setAttribute("hidden", "");
}

function setLoadStatus(msg) {
  const el = $("#load-status");
  if (el) el.textContent = msg;
}

function debounceGoldRender() {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(() => {
    state.goldPage = 0;
    renderGold();
  }, 200);
}

function getGoldFilters() {
  return {
    q: ($("#gold-search")?.value || "").trim().toLowerCase(),
    categories: multiSelectState.goldCategory,
    species: $("#gold-species")?.value || "",
    source: $("#gold-source")?.value || "",
    tier: $("#gold-tier")?.value || "",
    action: $("#gold-action")?.value || "",
    minScore: Number($("#gold-min-score")?.value) || 0,
    minRating: Number($("#gold-min-rating")?.value) || 0,
    maxPrice: Number($("#gold-max-price")?.value) || 0,
    sort: $("#gold-sort")?.value || "score-desc",
    quick: state.goldQuick,
  };
}

function filterGoldRows(rows) {
  const f = getGoldFilters();
  return rows.filter((r) => {
    if (f.categories.size > 0 && !f.categories.has(r.category)) return false;
    if (!speciesMatches(f.species, inferSpecies(r))) return false;
    if (f.tier && r.trend_tier !== f.tier) return false;
    if (f.action && r.recommended_action !== f.action) return false;
    if (f.minScore > 0 && (Number(r.trend_score) || 0) < f.minScore) return false;
    const rating = Math.max(Number(r.amazon_rating) || 0, Number(r.flipkart_rating) || 0);
    if (f.minRating > 0 && rating < f.minRating) return false;
    const price = Math.max(Number(r.amazon_price_inr) || 0, Number(r.flipkart_price_inr) || 0);
    if (f.maxPrice > 0 && (price <= 0 || price > f.maxPrice)) return false;
    if (f.source) {
      const src = String(r.sources || "");
      const hasAm = src.includes("amazon");
      const hasFk = src.includes("flipkart");
      const gtInterest = Number(r.gtrends_category_interest) || 0;
      if (f.source === "amazon" && !hasAm) return false;
      if (f.source === "flipkart" && !hasFk) return false;
      if (f.source === "both_market" && !(hasAm && hasFk)) return false;
      if (f.source === "gt_signal" && gtInterest <= 0) return false;
    }
    if (f.quick) {
      const qf = QUICK_FILTERS.find((x) => x.id === f.quick);
      if (qf && !qf.test(r)) return false;
    }
    if (f.q) {
      const blob = [
        r.canonical_title, r.normalized_brand, r.product_id, r.amazon_asin,
        r.reason_codes, r.category, r.recommended_action,
      ].join(" ").toLowerCase();
      if (!blob.includes(f.q)) return false;
    }
    return true;
  });
}

function sortGoldRows(rows) {
  const mode = $("#gold-sort")?.value || "score-desc";
  const copy = [...rows];
  const cmp = {
    "score-desc": (a, b) => (Number(b.trend_score) || 0) - (Number(a.trend_score) || 0),
    "score-asc": (a, b) => (Number(a.trend_score) || 0) - (Number(b.trend_score) || 0),
    "confidence-desc": (a, b) => (Number(b.trend_confidence) || 0) - (Number(a.trend_confidence) || 0),
    "reviews-desc": (a, b) => (Number(b.amazon_review_count || b.flipkart_review_count) || 0) - (Number(a.amazon_review_count || a.flipkart_review_count) || 0),
    "gtrends-desc": (a, b) => (Number(b.gtrends_category_interest) || 0) - (Number(a.gtrends_category_interest) || 0),
    "price-asc": (a, b) => {
      const pricesA = [Number(a.amazon_price_inr), Number(a.flipkart_price_inr)].filter((n) => n > 0);
      const pricesB = [Number(b.amazon_price_inr), Number(b.flipkart_price_inr)].filter((n) => n > 0);
      const pa = pricesA.length ? Math.min(...pricesA) : Infinity;
      const pb = pricesB.length ? Math.min(...pricesB) : Infinity;
      return pa - pb;
    },
    "price-desc": (a, b) => {
      const pa = Math.max(Number(a.amazon_price_inr) || 0, Number(a.flipkart_price_inr) || 0);
      const pb = Math.max(Number(b.amazon_price_inr) || 0, Number(b.flipkart_price_inr) || 0);
      return pb - pa;
    },
    "title-asc": (a, b) => String(a.canonical_title || "").localeCompare(String(b.canonical_title || "")),
  };
  copy.sort(cmp[mode] || cmp["score-desc"]);
  return copy;
}

function renderActiveFilterPills() {
  const f = getGoldFilters();
  const pills = [];
  if (f.q) pills.push({ label: `Search: ${f.q}`, clear: () => { $("#gold-search").value = ""; } });
  if (f.categories.size) pills.push({ label: `${f.categories.size} categories`, clear: () => { $("#gold-category-ms")?._clear(); } });
  if (f.species) pills.push({ label: f.species, clear: () => { $("#gold-species").value = ""; } });
  if (f.source) pills.push({ label: f.source, clear: () => { $("#gold-source").value = ""; } });
  if (f.tier) pills.push({ label: f.tier, clear: () => { $("#gold-tier").value = ""; } });
  if (f.action) pills.push({ label: fmtAction(f.action), clear: () => { $("#gold-action").value = ""; } });
  if (f.minScore > 0) pills.push({ label: `Score ≥ ${f.minScore}`, clear: () => { $("#gold-min-score").value = ""; } });
  if (f.minRating > 0) pills.push({ label: `★ ≥ ${f.minRating}`, clear: () => { $("#gold-min-rating").value = ""; } });
  if (f.maxPrice > 0) pills.push({ label: `≤ ₹${f.maxPrice}`, clear: () => { $("#gold-max-price").value = ""; } });
  if (f.quick) {
    const qf = QUICK_FILTERS.find((x) => x.id === f.quick);
    pills.push({ label: qf?.label || f.quick, clear: () => { state.goldQuick = null; } });
  }
  const el = $("#gold-active-filters");
  if (!el) return;
  el.innerHTML = pills.length
    ? pills.map((p, i) => `<button type="button" class="filter-pill" data-idx="${i}">${escapeHtml(p.label)} <span>×</span></button>`).join("")
    : `<span class="filter-hint">No filters active</span>`;
  el.querySelectorAll(".filter-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      pills[Number(btn.dataset.idx)]?.clear();
      state.goldPage = 0;
      renderGoldQuickFilters();
      renderGold();
    });
  });
}

function renderGoldQuickFilters() {
  const el = $("#gold-quick-filters");
  if (!el) return;
  el.innerHTML = QUICK_FILTERS.map((qf) =>
    `<button type="button" class="quick-chip ${state.goldQuick === qf.id ? "active" : ""}" data-quick="${qf.id}">${escapeHtml(qf.label)}</button>`
  ).join("");
  el.querySelectorAll(".quick-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.quick;
      state.goldQuick = state.goldQuick === id ? null : id;
      state.goldPage = 0;
      renderGoldQuickFilters();
      renderGold();
    });
  });
}

function resetGoldFilters() {
  $("#gold-search").value = "";
  $("#gold-category-ms")?._clear();
  $("#gold-species").value = "";
  $("#gold-source").value = "";
  $("#gold-tier").value = "";
  $("#gold-action").value = "";
  $("#gold-min-score").value = "";
  $("#gold-min-rating").value = "";
  $("#gold-max-price").value = "";
  $("#gold-sort").value = "score-desc";
  state.goldQuick = null;
  state.goldPage = 0;
  renderGoldQuickFilters();
  renderGold();
}

function getGlobalFilters() {
  return {
    q: ($("#global-search")?.value || "").trim().toLowerCase(),
    categories: multiSelectState.globalCategory,
    buckets: multiSelectState.globalBucket,
    species: $("#global-species")?.value || "",
    source: $("#global-source")?.value || "",
    minScore: Number($("#global-min-score")?.value) || 0,
    minRating: Number($("#global-min-rating")?.value) || 0,
    maxPrice: Number($("#global-max-price")?.value) || 0,
    sort: $("#global-sort")?.value || "score-desc",
    quick: state.globalQuick,
  };
}

function filterGlobalRows(rows) {
  const f = getGlobalFilters();
  return rows.filter((r) => {
    const cat = r.category || r.mapped_india_category;
    if (f.categories.size > 0 && !f.categories.has(cat)) return false;
    if (f.buckets.size > 0 && !f.buckets.has(r.global_opportunity_bucket)) return false;
    if (!speciesMatches(f.species, inferSpecies(r, true))) return false;
    if (f.source && r.source !== f.source) return false;
    if (f.minScore > 0 && (Number(r.global_signal_score) || 0) < f.minScore) return false;
    if (f.minRating > 0 && (Number(r.rating) || 0) < f.minRating) return false;
    if (f.maxPrice > 0) {
      const price = Number(r.price) || 0;
      if (price <= 0 || price > f.maxPrice) return false;
    }
    if (f.quick) {
      const qf = GLOBAL_QUICK_FILTERS.find((x) => x.id === f.quick);
      if (qf && !qf.test(r)) return false;
    }
    if (f.q) {
      const blob = [r.product_title, r.brand, cat, r.source, r.reason].join(" ").toLowerCase();
      if (!blob.includes(f.q)) return false;
    }
    return true;
  });
}

function renderGlobalActiveFilterPills() {
  const f = getGlobalFilters();
  const pills = [];
  if (f.q) pills.push({ label: `Search: ${f.q}`, clear: () => { $("#global-search").value = ""; } });
  if (f.categories.size) pills.push({ label: `${f.categories.size} categories`, clear: () => { $("#global-category-ms")?._clear(); } });
  if (f.buckets.size) pills.push({ label: `${f.buckets.size} India fit`, clear: () => { $("#global-bucket-ms")?._clear(); } });
  if (f.species) pills.push({ label: f.species, clear: () => { $("#global-species").value = ""; } });
  if (f.source) pills.push({ label: GLOBAL_SOURCE_LABELS[f.source] || f.source, clear: () => { $("#global-source").value = ""; } });
  if (f.minScore > 0) pills.push({ label: `Score ≥ ${f.minScore}`, clear: () => { $("#global-min-score").value = ""; } });
  if (f.minRating > 0) pills.push({ label: `★ ≥ ${f.minRating}`, clear: () => { $("#global-min-rating").value = ""; } });
  if (f.maxPrice > 0) pills.push({ label: `≤ $${f.maxPrice}`, clear: () => { $("#global-max-price").value = ""; } });
  if (f.quick) {
    const qf = GLOBAL_QUICK_FILTERS.find((x) => x.id === f.quick);
    pills.push({ label: qf?.label || f.quick, clear: () => { state.globalQuick = null; } });
  }
  const el = $("#global-active-filters");
  if (!el) return;
  el.innerHTML = pills.length
    ? pills.map((p, i) => `<button type="button" class="filter-pill" data-idx="${i}">${escapeHtml(p.label)} <span>×</span></button>`).join("")
    : `<span class="filter-hint">No filters active</span>`;
  el.querySelectorAll(".filter-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      pills[Number(btn.dataset.idx)]?.clear();
      state.globalPage = 0;
      renderGlobalQuickFilters();
      renderGlobal();
    });
  });
}

function renderGlobalQuickFilters() {
  const el = $("#global-quick-filters");
  if (!el) return;
  el.innerHTML = GLOBAL_QUICK_FILTERS.map((qf) =>
    `<button type="button" class="quick-chip ${state.globalQuick === qf.id ? "active" : ""}" data-quick="${qf.id}">${escapeHtml(qf.label)}</button>`
  ).join("");
  el.querySelectorAll(".quick-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.quick;
      state.globalQuick = state.globalQuick === id ? null : id;
      state.globalPage = 0;
      renderGlobalQuickFilters();
      renderGlobal();
    });
  });
}

function resetGlobalFilters() {
  $("#global-search").value = "";
  $("#global-category-ms")?._clear();
  $("#global-bucket-ms")?._clear();
  $("#global-species").value = "";
  $("#global-source").value = "";
  $("#global-min-score").value = "";
  $("#global-min-rating").value = "";
  $("#global-max-price").value = "";
  $("#global-sort").value = "score-desc";
  state.globalQuick = null;
  state.globalPage = 0;
  renderGlobalQuickFilters();
  renderGlobal();
}

async function loadAll() {
  showLoading();
  try {
    const [gold, global] = await Promise.all([
      fetchJson("/api/gold"),
      fetchJson("/api/global").catch(() => ({ rows: [] })),
    ]);
    state.gold = gold.rows || [];
    state.global = global.rows || [];
    showApp();
    initMultiSelects();
    populateGoldFilters();
    populateGlobalFilters();
    renderGoldQuickFilters();
    renderGlobalQuickFilters();
    updateNavCounts();
    renderHeaderStats();
    renderActivePanel();
  } catch (err) {
    showApp();
    $(".content").innerHTML = `<div class="empty"><div class="empty-icon">⚠</div><p>${escapeHtml(err.message)}</p><button class="btn btn-primary" onclick="location.reload()">Retry</button></div>`;
  }
}

function updateNavCounts() {
  $("#nav-india-count").textContent = state.gold.length;
  $("#nav-us-count").textContent = state.global.length;
}

function renderHeaderStats() {
  const top = state.gold[0];
  const watch = state.gold.filter((r) => ["BUY_TEST", "WATCHLIST"].includes(r.recommended_action)).length;
  const updated = top?.computed_ts?.slice(0, 10) || "—";
  $("#sidebar-updated").textContent = `Updated ${updated}`;
  $("#page-subtitle").textContent = TAB_SUBTITLES[state.tab] || "";

  if (state.tab === "india") {
    $("#header-stats").innerHTML = `
      <div class="stat stat-accent"><strong>${fmtNum(top?.trend_score)}</strong>Top score</div>
      <div class="stat"><strong>${state.gold.length}</strong>Products</div>
      <div class="stat"><strong>${watch}</strong>Top picks</div>`;
  } else {
    const topUs = state.global[0];
    const amazonUs = state.global.filter((r) => r.source === "amazon_us").length;
    $("#header-stats").innerHTML = `
      <div class="stat stat-accent"><strong>${fmtNum(topUs?.global_signal_score)}</strong>Top score</div>
      <div class="stat"><strong>${state.global.length}</strong>Products</div>
      <div class="stat"><strong>${amazonUs}</strong>Amazon US</div>`;
  }
}

function renderGold() {
  state.goldPageSize = Number($("#gold-pagesize")?.value) || 48;
  const filtered = sortGoldRows(filterGoldRows(state.gold));
  const pg = paginate(filtered, state.goldPage, state.goldPageSize);
  state.goldPage = pg.page;

  $("#gold-count").textContent = `${pg.total.toLocaleString()} products`;
  renderActiveFilterPills();

  const rowsWithRank = pg.rows.map((r, i) => ({ ...r, _displayRank: pg.start + i + 1 }));

  if (state.view === "cards") {
    $("#gold-content").innerHTML = rowsWithRank.length
      ? `<div class="grid">${rowsWithRank.map(goldCard).join("")}</div>`
      : '<div class="empty"><div class="empty-icon">🔍</div><p>No products match. <button type="button" class="btn btn-ghost btn-sm" id="empty-reset">Clear filters</button></p></div>';
    $("#empty-reset")?.addEventListener("click", resetGoldFilters);
  } else {
    $("#gold-content").innerHTML = goldTable(rowsWithRank);
  }

  renderPaginationBar("gold-pagination", pg, (p) => { state.goldPage = p; renderGold(); });
}

function goldCard(r) {
  const rank = r._displayRank;
  const score = Number(r.trend_score) || 0;
  const rating = r.amazon_rating || r.flipkart_rating;
  const reviews = r.amazon_review_count || r.flipkart_review_count;
  const links = [];
  if (r.amazon_url) links.push(`<a class="link-btn amazon" href="${escapeAttr(r.amazon_url)}" target="_blank" rel="noopener">Amazon</a>`);
  if (r.flipkart_url) links.push(`<a class="link-btn flipkart" href="${escapeAttr(r.flipkart_url)}" target="_blank" rel="noopener">Flipkart</a>`);

  return `
    <article class="card">
      <div class="card-img-wrap">
        <span class="rank-badge">#${rank}</span>
        <span class="score-badge ${scoreClass(score)}">${fmtNum(score)}</span>
        <div class="card-img">${imgOrPlaceholder(r.image_url, r.canonical_title)}</div>
      </div>
      <div class="card-body">
        <div class="card-head">
          <span class="badge badge-action action-${escapeAttr(r.recommended_action)}">${escapeHtml(fmtAction(r.recommended_action))}</span>
          <span class="badge badge-tier ${escapeHtml(r.trend_tier || "stable")}">${escapeHtml(r.trend_tier || "—")}</span>
        </div>
        <div class="card-title" title="${escapeAttr(r.canonical_title)}">${escapeHtml(r.canonical_title)}</div>
        ${r.normalized_brand ? `<div class="card-brand">${escapeHtml(r.normalized_brand)} · ${escapeHtml(fmtCategory(r.category))}</div>` : `<div class="card-brand">${escapeHtml(fmtCategory(r.category))}</div>`}
        ${sourceBadges(r.sources)}
        ${signalBadges(r.reason_codes)}
        <div class="score-meta">
          <span>Conf <strong>${fmtPct(r.trend_confidence)}</strong></span>
          ${gtrendsLine(r)}
          ${rating ? `<span>★ <strong>${fmtNum(rating)}</strong>${reviews ? ` (${fmtNum(reviews, 0)})` : ""}</span>` : ""}
          <span>AMZ <strong>${fmtPrice(r.amazon_price_inr)}</strong></span>
          <span>FK <strong>${fmtPrice(r.flipkart_price_inr)}</strong></span>
        </div>
        ${links.length ? `<div class="links">${links.join("")}</div>` : ""}
      </div>
    </article>`;
}

function goldTable(rows) {
  if (!rows.length) return '<div class="empty"><p>No rows</p></div>';
  return `
    <div class="table-wrap table-gold">
      <table>
        <thead><tr>
          <th>#</th><th></th><th>Product</th><th>Score</th><th>Action</th><th>Tier</th>
            <th>Conf</th><th>GT interest</th><th>GT Δ</th><th>Category</th><th>Price AMZ/FK</th><th>Links</th>
        </tr></thead>
        <tbody>${rows.map((r) => `
          <tr>
            <td class="mono">${r._displayRank}</td>
            <td>${r.image_url?.startsWith("http") ? `<img class="thumb" src="${escapeAttr(r.image_url)}" loading="lazy">` : ""}</td>
            <td class="cell-product">
              <div class="cell-title">${escapeHtml(r.canonical_title)}</div>
              <div class="cell-sub">${escapeHtml(r.normalized_brand || "")} ${escapeHtml((r.reason_codes || "").replace(/\|/g, ", "))}</div>
            </td>
            <td class="mono score-cell ${scoreClass(r.trend_score)}">${fmtNum(r.trend_score)}</td>
            <td><span class="badge badge-action action-${escapeAttr(r.recommended_action)}">${escapeHtml(fmtAction(r.recommended_action))}</span></td>
            <td><span class="badge badge-tier ${escapeHtml(r.trend_tier)}">${escapeHtml(r.trend_tier)}</span></td>
              <td>${fmtPct(r.trend_confidence)}</td>
              <td class="mono">${fmtNum(r.gtrends_category_interest, 0)}</td>
              <td class="mono gt-delta-cell ${Number(r.gtrends_interest_delta_7d) > 0 ? "up" : ""}">${Number(r.gtrends_interest_delta_7d) ? ((Number(r.gtrends_interest_delta_7d) > 0 ? "+" : "") + fmtNum(r.gtrends_interest_delta_7d, 0)) : "—"}</td>
              <td>${escapeHtml(fmtCategory(r.category))}</td>
            <td class="mono-sm">${fmtPrice(r.amazon_price_inr)} / ${fmtPrice(r.flipkart_price_inr)}</td>
            <td class="cell-links">
              ${r.amazon_url ? `<a class="table-link" href="${escapeAttr(r.amazon_url)}" target="_blank">AMZ</a>` : ""}
              ${r.flipkart_url ? `<a class="table-link" href="${escapeAttr(r.flipkart_url)}" target="_blank">FK</a>` : ""}
            </td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

function gtrendsLine(r) {
  const interest = Number(r.gtrends_category_interest);
  const delta = Number(r.gtrends_interest_delta_7d);
  if (!Number.isFinite(interest) || interest <= 0) return "";
  const deltaStr = Number.isFinite(delta) && delta !== 0
    ? `<span class="gt-delta ${delta > 0 ? "up" : "down"}">${delta > 0 ? "+" : ""}${fmtNum(delta, 0)}</span>`
    : "";
  return `<span class="gt-line">GT <strong>${fmtNum(interest, 0)}</strong>${deltaStr}</span>`;
}

function renderGlobal() {
  state.globalPageSize = Number($("#global-pagesize")?.value) || 48;
  const filtered = sortGlobalRows(filterGlobalRows(state.global));
  const pg = paginate(filtered, state.globalPage, state.globalPageSize);
  state.globalPage = pg.page;
  $("#global-count").textContent = `${pg.total.toLocaleString()} products`;
  renderGlobalActiveFilterPills();

  const rowsWithRank = pg.rows.map((r, i) => ({ ...r, _displayRank: pg.start + i + 1 }));

  if (state.view === "cards") {
    $("#global-content").innerHTML = rowsWithRank.length
      ? `<div class="grid">${rowsWithRank.map(usCard).join("")}</div>`
      : '<div class="empty"><div class="empty-icon">🌐</div><p>No US products match. <button type="button" class="btn btn-ghost btn-sm" id="global-empty-reset">Clear filters</button></p></div>';
    $("#global-empty-reset")?.addEventListener("click", resetGlobalFilters);
  } else {
    $("#global-content").innerHTML = usTable(rowsWithRank);
  }

  renderPaginationBar("global-pagination", pg, (p) => { state.globalPage = p; renderGlobal(); });
}

function sortGlobalRows(rows) {
  const sort = $("#global-sort")?.value || "score-desc";
  const list = [...rows];
  switch (sort) {
    case "score-asc":
      return list.sort((a, b) => (Number(a.global_signal_score) || 0) - (Number(b.global_signal_score) || 0));
    case "price-asc":
      return list.sort((a, b) => (Number(a.price) || 0) - (Number(b.price) || 0));
    case "price-desc":
      return list.sort((a, b) => (Number(b.price) || 0) - (Number(a.price) || 0));
    case "reviews-desc":
      return list.sort((a, b) => (Number(b.review_count) || 0) - (Number(a.review_count) || 0));
    case "rating-desc":
      return list.sort((a, b) => (Number(b.rating) || 0) - (Number(a.rating) || 0));
    case "title-asc":
      return list.sort((a, b) => String(a.product_title || "").localeCompare(String(b.product_title || "")));
    default:
      return list.sort((a, b) => (Number(b.global_signal_score) || 0) - (Number(a.global_signal_score) || 0));
  }
}

function globalSourceBadge(source) {
  const label = GLOBAL_SOURCE_LABELS[source] || source || "—";
  return `<span class="badge badge-src ${escapeAttr(source)}">${escapeHtml(label)}</span>`;
}

function usCard(r) {
  const rank = r._displayRank;
  const score = Number(r.global_signal_score) || 0;
  const rating = Number(r.rating);
  const reviews = Number(r.review_count);
  const bucket = r.global_opportunity_bucket;
  const bucketBadge = bucket
    ? `<span class="badge badge-bucket">${escapeHtml(GLOBAL_BUCKET_LABELS[bucket] || bucket)}</span>`
    : "";
  const link = r.source_url
    ? `<a class="link-btn ${escapeAttr(r.source === "amazon_us" ? "amazon" : r.source)}" href="${escapeAttr(r.source_url)}" target="_blank" rel="noopener">${escapeHtml(GLOBAL_SOURCE_LABELS[r.source] || "View")}</a>`
    : "";

  return `
    <article class="card">
      <div class="card-img-wrap">
        <span class="rank-badge">#${rank}</span>
        <span class="score-badge ${scoreClass(score)}">${fmtNum(score)}</span>
        <div class="card-img">${imgOrPlaceholder(r.image_url, r.product_title)}</div>
      </div>
      <div class="card-body">
        <div class="card-head">
          ${globalSourceBadge(r.source)}
          ${bucketBadge}
        </div>
        <div class="card-title" title="${escapeAttr(r.product_title)}">${escapeHtml(r.product_title)}</div>
        <div class="card-brand">${escapeHtml(r.brand || "—")} · ${escapeHtml(fmtCategory(r.category || r.mapped_india_category))}</div>
        <div class="score-meta">
          <span>Price <strong>${fmtPriceUsd(r.price, r.currency)}</strong></span>
          ${Number.isFinite(rating) && rating > 0 ? `<span>★ <strong>${fmtNum(rating)}</strong>${reviews > 0 ? ` (${fmtNum(reviews, 0)})` : ""}</span>` : ""}
          ${Number(r.sold_count) > 0 ? `<span>Sold <strong>${fmtNum(r.sold_count, 0)}</strong></span>` : ""}
        </div>
        ${r.reason ? `<div class="card-reason">${escapeHtml(r.reason)}</div>` : ""}
        ${link ? `<div class="links">${link}</div>` : ""}
      </div>
    </article>`;
}

function usTable(rows) {
  if (!rows.length) {
    return '<div class="empty"><div class="empty-icon">🌐</div><p>No US market data available yet.</p></div>';
  }
  return `
    <div class="table-wrap table-gold">
      <table>
        <thead><tr>
          <th>#</th><th></th><th>Product</th><th>Score</th><th>Source</th><th>India fit</th>
          <th>Price</th><th>Rating</th><th>Category</th><th>Link</th>
        </tr></thead>
        <tbody>${rows.map((r) => `
          <tr>
            <td class="mono">${r._displayRank}</td>
            <td>${r.image_url?.startsWith("http") ? `<img class="thumb" src="${escapeAttr(r.image_url)}" loading="lazy">` : ""}</td>
            <td class="cell-product">
              <div class="cell-title">${escapeHtml(r.product_title || "")}</div>
              <div class="cell-sub">${escapeHtml(r.brand || "")}</div>
            </td>
            <td class="mono score-cell ${scoreClass(r.global_signal_score)}">${fmtNum(r.global_signal_score)}</td>
            <td><span class="badge badge-src ${escapeAttr(r.source)}">${escapeHtml(GLOBAL_SOURCE_LABELS[r.source] || r.source || "")}</span></td>
            <td><span class="badge">${escapeHtml(GLOBAL_BUCKET_LABELS[r.global_opportunity_bucket] || r.global_opportunity_bucket || "—")}</span></td>
            <td class="mono-sm">${fmtPriceUsd(r.price, r.currency)}</td>
            <td>${Number(r.rating) > 0 ? `★ ${fmtNum(r.rating)}` : "—"}</td>
            <td>${escapeHtml(fmtCategory(r.category || r.mapped_india_category))}</td>
            <td class="cell-links">${r.source_url ? `<a class="table-link" href="${escapeAttr(r.source_url)}" target="_blank" rel="noopener">Open</a>` : ""}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

function populateGlobalFilters() {
  const cats = [...new Set(state.global.map((r) => r.category || r.mapped_india_category).filter(Boolean))].sort();
  $("#global-category-ms")?._renderOptions?.(cats);
}

function populateGoldFilters() {
  const cats = [...new Set(state.gold.map((r) => r.category).filter(Boolean))].sort();
  $("#gold-category-ms")?._renderOptions?.(cats);
}

function renderActivePanel() {
  if (state.tab === "india") renderGold();
  if (state.tab === "us") renderGlobal();
  renderHeaderStats();
}

function setTab(tab) {
  state.tab = tab;
  $("#page-title").textContent = TAB_TITLES[tab] || tab;
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${tab}`));
  renderActivePanel();
}

function setView(view) {
  state.view = view;
  ["view-cards", "global-view-cards"].forEach((id) => $(`#${id}`)?.classList.toggle("active", view === "cards"));
  ["view-table", "global-view-table"].forEach((id) => $(`#${id}`)?.classList.toggle("active", view === "table"));
  renderActivePanel();
}

function bindEvents() {
  document.addEventListener("click", () => {
    $$(".multi-select-panel").forEach((p) => { p.hidden = true; });
  });

  $$(".nav-item").forEach((btn) => btn.addEventListener("click", () => setTab(btn.dataset.tab)));

  $("#gold-search")?.addEventListener("input", debounceGoldRender);
  ["gold-species", "gold-source", "gold-tier", "gold-action", "gold-sort", "gold-pagesize"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", () => { state.goldPage = 0; renderGold(); });
  });
  ["gold-min-score", "gold-min-rating", "gold-max-price"].forEach((id) => {
    $(`#${id}`)?.addEventListener("input", debounceGoldRender);
  });
  $("#gold-reset")?.addEventListener("click", resetGoldFilters);
  $("#gold-export")?.addEventListener("click", () => {
    const rows = sortGoldRows(filterGoldRows(state.gold));
    exportCsv(rows, [
      { label: "Rank", get: (r) => r.rank_position },
      { label: "Title", get: (r) => r.canonical_title },
      { label: "Brand", get: (r) => r.normalized_brand },
      { label: "Category", get: (r) => r.category },
      { label: "Score", get: (r) => r.trend_score },
      { label: "Action", get: (r) => r.recommended_action },
      { label: "Tier", get: (r) => r.trend_tier },
      { label: "Amazon Price INR", get: (r) => r.amazon_price_inr },
      { label: "Flipkart Price INR", get: (r) => r.flipkart_price_inr },
      { label: "Amazon URL", get: (r) => r.amazon_url },
      { label: "Flipkart URL", get: (r) => r.flipkart_url },
    ], `india-market-${new Date().toISOString().slice(0, 10)}.csv`);
  });
  $("#view-cards")?.addEventListener("click", () => setView("cards"));
  $("#view-table")?.addEventListener("click", () => setView("table"));
  $("#global-view-cards")?.addEventListener("click", () => setView("cards"));
  $("#global-view-table")?.addEventListener("click", () => setView("table"));

  $("#global-search")?.addEventListener("input", () => {
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(() => { state.globalPage = 0; renderGlobal(); }, 200);
  });
  ["global-species", "global-source", "global-sort", "global-pagesize"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", () => { state.globalPage = 0; renderGlobal(); });
  });
  ["global-min-score", "global-min-rating", "global-max-price"].forEach((id) => {
    $(`#${id}`)?.addEventListener("input", () => {
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => { state.globalPage = 0; renderGlobal(); }, 200);
    });
  });
  $("#global-reset")?.addEventListener("click", resetGlobalFilters);
  $("#global-export")?.addEventListener("click", () => {
    const rows = sortGlobalRows(filterGlobalRows(state.global));
    exportCsv(rows, [
      { label: "Rank", get: (r) => r.rank_position },
      { label: "Title", get: (r) => r.product_title },
      { label: "Brand", get: (r) => r.brand },
      { label: "Category", get: (r) => r.category || r.mapped_india_category },
      { label: "Score", get: (r) => r.global_signal_score },
      { label: "India Fit", get: (r) => r.global_opportunity_bucket },
      { label: "Price USD", get: (r) => r.price },
      { label: "Rating", get: (r) => r.rating },
      { label: "Reviews", get: (r) => r.review_count },
      { label: "Source URL", get: (r) => r.source_url },
    ], `us-market-${new Date().toISOString().slice(0, 10)}.csv`);
  });

  $("#reload-btn")?.addEventListener("click", loadAll);
}

bindEvents();
loadAll().then(() => setTab("india"));
