const API_BASE = (window.ECONSCOPE_CONFIG?.API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

const state = {
  view: "dashboard",
  summary: null,
  dashboardRange: 12,
  dashboardIndicator: "exchange_rate",
  comparison: null,
  conversationId: null,
  conversations: [],
  data: [],
  dataPage: 1,
  dataPageSize: 30,
};

const indicatorMeta = {
  exchange_rate: { label: "원/달러 환율", short: "환율", unit: "원/USD", digits: 2 },
  base_rate: { label: "한국은행 기준금리", short: "기준금리", unit: "%", digits: 2 },
  cpi: { label: "소비자물가지수(CPI)", short: "CPI", unit: "2020=100", digits: 2 },
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 70000);
  const coldstart = setTimeout(() => $("#coldstartBanner")?.classList.remove("hidden"), 2500);
  try {
    const response = await fetch(apiUrl(path), {
      ...options,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    if (!response.ok) {
      let detail = `요청을 처리하지 못했습니다. (${response.status})`;
      try {
        const body = await response.json();
        detail = body.detail || detail;
        if (Array.isArray(detail)) detail = detail.map((item) => item.msg).join(", ");
      } catch (_) {}
      throw new Error(detail);
    }
    if (response.status === 204) return null;
    return response.json();
  } catch (error) {
    if (error.name === "AbortError") throw new Error("서버 응답 시간이 너무 길어졌습니다. 잠시 후 다시 시도해주세요.");
    throw error;
  } finally {
    clearTimeout(timeout);
    clearTimeout(coldstart);
    $("#coldstartBanner")?.classList.add("hidden");
  }
}

function toast(message, type = "success") {
  const item = document.createElement("div");
  item.className = `toast ${type}`;
  item.textContent = message;
  $("#toastRegion").append(item);
  setTimeout(() => item.remove(), 4200);
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function formatTimestamp(value) {
  if (!value) return "아직 갱신 기록 없음";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function shiftMonth(period, offset) {
  const [year, month] = period.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1 + offset, 1));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function directionClass(direction) {
  return direction === "상승" ? "rise" : direction === "하락" ? "fall" : "neutral";
}

function directionArrow(direction) {
  return direction === "상승" ? "↑" : direction === "하락" ? "↓" : "→";
}

function setView(view) {
  state.view = view;
  $$(".view").forEach((section) => section.classList.toggle("active", section.id === `view-${view}`));
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("#sidebar").classList.remove("open");
  $("#sidebarBackdrop").classList.remove("open");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (view === "data") loadData();
  if (view === "conversations") loadConversations();
  if (view === "compare" && !state.comparison) initializeComparison();
  if (view === "chat") renderChatContext();
}

async function loadSummary(force = false) {
  if (state.summary && !force) return state.summary;
  state.summary = await api("/api/data/summary");
  renderSummary();
  return state.summary;
}

function renderSummary() {
  const summary = state.summary;
  if (!summary) return;
  const cards = Object.entries(summary.indicators).map(([key, item]) => {
    const meta = indicatorMeta[key];
    if (!item.latest) return `<article class="metric-card"><span class="metric-label">${meta.label}</span><div class="metric-value">—</div></article>`;
    const yoy = item.year_over_year;
    const change = item.recent_3.change;
    const yoyValue = key === "base_rate" ? yoy?.absolute : yoy?.percent;
    const yoyUnit = key === "base_rate" ? "%p" : "%";
    return `<article class="metric-card">
      <div class="metric-top"><span class="metric-label">${meta.label}</span><span class="metric-date">${item.latest.date}</span></div>
      <div class="metric-value">${formatNumber(item.latest.value, meta.digits)} <small>${meta.unit}</small></div>
      <div class="metric-bottom">
        <span class="trend-badge ${directionClass(change.direction)}">${directionArrow(change.direction)} 최근 3개월 ${change.direction}</span>
        <span class="metric-caption">전년 동월 대비<strong>${yoyValue == null ? "—" : `${yoyValue >= 0 ? "+" : ""}${formatNumber(yoyValue)}${yoyUnit}`}</strong></span>
      </div>
    </article>`;
  }).join("");
  $("#metricGrid").innerHTML = cards;
  const sync = summary.last_sync;
  $("#dashboardUpdated").textContent = sync?.last_success_at ? `마지막 갱신 ${formatTimestamp(sync.last_success_at)}` : "저장된 초기 데이터 사용 중";
  $("#sidebarLatest").textContent = `최신 관측 ${summary.period.end}`;
  renderQuickInsight();
  renderChatContext();
}

function renderQuickInsight() {
  if (!state.summary) return;
  const { cpi, exchange_rate: exchange, base_rate: rate } = state.summary.indicators;
  $("#quickInsight").innerHTML = `
    <div class="insight-signal"><span class="signal-line"></span><div><small>최근 3개월</small><strong>물가는 ${cpi.recent_3.change.direction}, 환율은 ${exchange.recent_3.change.direction} 흐름입니다.</strong></div></div>
    <p class="insight-copy">최신 CPI는 ${formatNumber(cpi.latest.value)}이고 기준금리는 ${formatNumber(rate.latest.value)}%입니다. 세 지표가 함께 움직여도 실제 원인은 국제유가·수요·공급망 등 다른 요인과 함께 살펴봐야 합니다.</p>`;
}

function renderChatContext() {
  if (!state.summary) return;
  $("#chatContextCards").innerHTML = Object.entries(state.summary.indicators).map(([key, item]) => {
    const meta = indicatorMeta[key];
    return `<div class="context-card"><small>${meta.label} · ${item.latest?.date || "—"}</small><div><strong>${formatNumber(item.latest?.value, meta.digits)}</strong><span>${meta.unit}</span></div></div>`;
  }).join("");
}

async function loadDashboardChart() {
  const records = await api(`/api/data?indicator=${state.dashboardIndicator}&limit=10000`);
  const ordered = records.filter((item) => item.status !== "deleted").sort((a, b) => a.date.localeCompare(b.date));
  const visible = state.dashboardRange >= 900 ? ordered : ordered.slice(-state.dashboardRange);
  const meta = indicatorMeta[state.dashboardIndicator];
  drawLineChart($("#dashboardChart"), [{ name: meta.short, values: visible.map((item) => ({ label: item.date, value: Number(item.value) })), color: "var(--primary)" }], meta.unit, true);
}

function drawLineChart(container, datasets, unit, showArea = false) {
  const all = datasets.flatMap((dataset) => dataset.values.map((item) => item.value));
  if (!all.length) {
    container.innerHTML = `<div class="chart-empty">선택한 기간에 표시할 데이터가 없습니다.</div>`;
    return;
  }
  const width = 820, height = 285, pad = { left: 54, right: 18, top: 26, bottom: 42 };
  let min = Math.min(...all), max = Math.max(...all);
  const span = max - min || Math.abs(max) * .1 || 1;
  min -= span * .12; max += span * .12;
  const x = (index, length) => pad.left + (length <= 1 ? 0 : index / (length - 1)) * (width - pad.left - pad.right);
  const y = (value) => pad.top + ((max - value) / (max - min)) * (height - pad.top - pad.bottom);
  const grid = Array.from({ length: 5 }, (_, index) => {
    const lineY = pad.top + index * (height - pad.top - pad.bottom) / 4;
    const value = max - index * (max - min) / 4;
    return `<line class="chart-grid-line" x1="${pad.left}" y1="${lineY}" x2="${width - pad.right}" y2="${lineY}"/><text class="chart-axis-label" x="${pad.left - 9}" y="${lineY + 4}" text-anchor="end">${formatNumber(value, max < 10 ? 2 : 0)}</text>`;
  }).join("");
  const id = `gradient-${Math.random().toString(36).slice(2)}`;
  const paths = datasets.map((dataset, datasetIndex) => {
    const points = dataset.values.map((item, index) => `${x(index, dataset.values.length)},${y(item.value)}`).join(" ");
    const line = `<polyline points="${points}" fill="none" stroke="${dataset.color}" stroke-width="${datasetIndex ? 2.3 : 3}" stroke-linecap="round" stroke-linejoin="round"/>`;
    let area = "";
    if (showArea && datasetIndex === 0 && dataset.values.length > 1) {
      const firstX = x(0, dataset.values.length), lastX = x(dataset.values.length - 1, dataset.values.length), bottom = height - pad.bottom;
      area = `<polygon points="${firstX},${bottom} ${points} ${lastX},${bottom}" fill="url(#${id})"/>`;
    }
    const dotStep = dataset.values.length > 24 ? Math.ceil(dataset.values.length / 12) : 1;
    const dots = dataset.values.map((item, index) => index % dotStep === 0 || index === dataset.values.length - 1 ? `<circle cx="${x(index, dataset.values.length)}" cy="${y(item.value)}" r="3.3" fill="var(--surface)" stroke="${dataset.color}" stroke-width="2"><title>${escapeHtml(item.label)} · ${formatNumber(item.value)} ${escapeHtml(unit)}</title></circle>` : "").join("");
    return area + line + dots;
  }).join("");
  const labels = datasets[0].values;
  const labelIndexes = [...new Set([0, Math.floor((labels.length - 1) / 4), Math.floor((labels.length - 1) / 2), Math.floor((labels.length - 1) * .75), labels.length - 1])];
  const xLabels = labelIndexes.map((index) => `<text class="chart-axis-label" x="${x(index, labels.length)}" y="${height - 14}" text-anchor="middle">${escapeHtml(labels[index]?.label || "")}</text>`).join("");
  const legend = datasets.length > 1 ? `<div class="chart-summary">${datasets.map((d) => `<span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${d.color};margin-right:4px"></i>${escapeHtml(d.name)}</span>`).join("")}</div>` : `<div class="chart-summary"><strong>${formatNumber(labels.at(-1).value)}</strong><span>${unit} · ${labels.at(-1).label}</span></div>`;
  container.innerHTML = `${legend}<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(datasets.map((d) => d.name).join(", "))} 시계열 그래프"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--primary)" stop-opacity=".20"/><stop offset="1" stop-color="var(--primary)" stop-opacity="0"/></linearGradient></defs>${grid}${paths}${xLabels}</svg>`;
}

function initializeComparison() {
  if (!state.summary?.period?.end) return;
  const endA = state.summary.period.end;
  const startA = shiftMonth(endA, -2);
  const endB = shiftMonth(startA, -1);
  const startB = shiftMonth(endB, -2);
  $("#periodAStart").value = startA; $("#periodAEnd").value = endA;
  $("#periodBStart").value = startB; $("#periodBEnd").value = endB;
  runComparison();
}

async function runComparison() {
  const indicators = $$("#compareIndicators input:checked").map((input) => input.value);
  if (!indicators.length) return toast("비교할 지표를 하나 이상 선택해주세요.", "error");
  const params = new URLSearchParams({
    period_a_start: $("#periodAStart").value,
    period_a_end: $("#periodAEnd").value,
    period_b_start: $("#periodBStart").value,
    period_b_end: $("#periodBEnd").value,
  });
  indicators.forEach((item) => params.append("indicators", item));
  $("#compareResults").innerHTML = `<div class="panel empty-state">두 기간의 수치를 비교하고 있습니다.</div>`;
  try {
    state.comparison = await api(`/api/data/compare?${params}`);
    renderComparison();
  } catch (error) {
    $("#compareResults").innerHTML = `<div class="panel empty-state">${escapeHtml(error.message)}</div>`;
    toast(error.message, "error");
  }
}

function renderComparison() {
  const result = state.comparison;
  const entries = Object.entries(result.indicators);
  $("#compareResults").innerHTML = entries.map(([key, item]) => {
    const a = item.period_a, b = item.period_b;
    if (!a.count || !b.count) return `<article class="panel compare-block"><h3>${item.label}</h3><p class="insight-copy">선택한 기간 중 한쪽에 데이터가 없습니다.</p></article>`;
    return `<article class="panel compare-block">
      <div class="compare-block-header"><div><span class="overline">${escapeHtml(item.unit)}</span><h3>${escapeHtml(item.label)}</h3></div><span class="trend-badge ${directionClass(a.change.direction)}">기간 A ${a.change.direction}</span></div>
      <div class="comparison-table">
        <div class="table-head">항목</div><div class="table-head">기간 A · ${a.start}~${a.end}</div><div class="table-head">기간 B · ${b.start}~${b.end}</div>
        <div>평균</div><div class="value-cell">${formatNumber(a.average)}</div><div class="value-cell">${formatNumber(b.average)}</div>
        <div>최고</div><div class="value-cell">${formatNumber(a.maximum.value)} · ${a.maximum.date}</div><div class="value-cell">${formatNumber(b.maximum.value)} · ${b.maximum.date}</div>
        <div>최저</div><div class="value-cell">${formatNumber(a.minimum.value)} · ${a.minimum.date}</div><div class="value-cell">${formatNumber(b.minimum.value)} · ${b.minimum.date}</div>
        <div>기간 변화</div><div class="value-cell">${a.change.absolute >= 0 ? "+" : ""}${formatNumber(a.change.absolute)} ${item.unit}</div><div class="value-cell">${b.change.absolute >= 0 ? "+" : ""}${formatNumber(b.change.absolute)} ${item.unit}</div>
        <div>가장 큰 월간 변화</div><div class="value-cell">${a.largest_monthly_change ? `${a.largest_monthly_change.date} · ${formatNumber(a.largest_monthly_change.change)}` : "—"}</div><div class="value-cell">${b.largest_monthly_change ? `${b.largest_monthly_change.date} · ${formatNumber(b.largest_monthly_change.change)}` : "—"}</div>
      </div>
      <div class="compare-chart" id="compare-chart-${key}"></div>
    </article>`;
  }).join("");
  entries.forEach(([key, item]) => {
    if (!item.period_a.count || !item.period_b.count) return;
    drawLineChart($(`#compare-chart-${key}`), [
      { name: `기간 A ${item.period_a.start}~${item.period_a.end}`, color: "var(--primary)", values: item.period_a.values.map((value, index) => ({ label: `${index + 1}개월`, value: Number(value.value) })) },
      { name: `기간 B ${item.period_b.start}~${item.period_b.end}`, color: "#7185d8", values: item.period_b.values.map((value, index) => ({ label: `${index + 1}개월`, value: Number(value.value) })) },
    ], item.unit);
  });
  $("#compareExplainCard").classList.remove("hidden");
  $("#compareAiAnswer").innerHTML = "";
}

function markdownToHtml(markdown) {
  const lines = escapeHtml(markdown).split("\n");
  let html = "", inList = false;
  const formatInline = (line) => line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>");
  lines.forEach((line) => {
    if (line.startsWith("- ")) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${formatInline(line.slice(2))}</li>`;
      return;
    }
    if (inList) { html += "</ul>"; inList = false; }
    if (!line.trim()) return;
    if (line.startsWith("### ")) html += `<h3>${formatInline(line.slice(4))}</h3>`;
    else if (line.startsWith("## ")) html += `<h3>${formatInline(line.slice(3))}</h3>`;
    else if (line.startsWith("# ")) html += `<h2>${formatInline(line.slice(2))}</h2>`;
    else html += `<p>${formatInline(line)}</p>`;
  });
  if (inList) html += "</ul>";
  return html;
}

function assistantExtras(metadata = {}, allowDetail = true) {
  const sources = metadata.sources || [];
  const sourceHtml = sources.length ? `<div class="source-card"><strong>근거 자료</strong>${sources.map((source) => `<a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer"><span>${escapeHtml(source.title)}<br/><small>${escapeHtml(source.organization || "외부 자료")} ${escapeHtml(source.date || "")}</small></span><span>↗</span></a>`).join("")}</div>` : "";
  const noticeHtml = metadata.source_notice ? `<div class="notice-card"><svg><use href="#icon-info"/></svg><span>${escapeHtml(metadata.source_notice)}</span></div>` : "";
  const outlook = metadata.outlook;
  const outlookHtml = outlook ? `<div class="outlook-card"><div class="outlook-top"><span class="outlook-chip">예상 방향 <strong>${escapeHtml(outlook.direction)}</strong></span><span class="outlook-chip">확신 수준 <strong>${escapeHtml(outlook.confidence)}</strong></span><span class="outlook-chip">기간 <strong>${outlook.months}개월</strong></span></div><p class="confidence-reason"><strong>왜 이런 수준인가요?</strong><br/>${escapeHtml(outlook.confidence_reason)}</p><div class="scenario-list">${outlook.scenarios.map((scenario) => `<details><summary>${escapeHtml(scenario.title)}</summary><p>${escapeHtml(scenario.content)}</p></details>`).join("")}</div></div>` : "";
  const aiProvider = metadata.generated_by === "gemini" ? "Gemini + 데이터" : metadata.generated_by === "openai" ? "OpenAI + 데이터" : "데이터 분석";
  const tools = allowDetail ? `<div class="message-tools"><button class="detail-button">자세히 분석</button><span class="status-badge ${metadata.generated_by === "gemini" || metadata.generated_by === "openai" ? "official" : "user"}">${aiProvider}</span></div>` : "";
  return outlookHtml + sourceHtml + noticeHtml + tools;
}

function assistantMessageHtml(content, metadata = {}, allowDetail = true) {
  return `<div class="message assistant"><div class="assistant-message"><div class="assistant-avatar"><svg><use href="#icon-spark"/></svg></div><div class="message-content">${markdownToHtml(content)}${assistantExtras(metadata, allowDetail)}</div></div></div>`;
}

function addMessage(role, content, metadata = {}) {
  const messages = $("#chatMessages");
  $(".chat-welcome", messages)?.remove();
  if (role === "user") messages.insertAdjacentHTML("beforeend", `<div class="message user"><div class="user-bubble">${escapeHtml(content)}</div></div>`);
  else messages.insertAdjacentHTML("beforeend", assistantMessageHtml(content, metadata));
  messages.scrollTop = messages.scrollHeight;
}

function addTyping(target = $("#chatMessages")) {
  const id = `typing-${Date.now()}`;
  target.insertAdjacentHTML("beforeend", `<div class="message assistant" id="${id}"><div class="assistant-message"><div class="assistant-avatar"><svg><use href="#icon-spark"/></svg></div><div class="typing"><span></span><span></span><span></span></div></div></div>`);
  target.scrollTop = target.scrollHeight;
  return id;
}

async function sendChat(question, options = {}) {
  const value = question.trim();
  if (!value) return;
  setView("chat");
  addMessage("user", value);
  const typingId = addTyping();
  $("#chatInput").value = "";
  try {
    const response = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        question: value,
        conversation_id: state.conversationId,
        detailed: Boolean(options.detailed),
        outlook_months: options.outlookMonths || 3,
        comparison_context: options.comparison || null,
      }),
    });
    $(`#${typingId}`)?.remove();
    state.conversationId = response.conversation_id;
    $("#chatTitle").textContent = response.title;
    addMessage("assistant", response.answer, response);
  } catch (error) {
    $(`#${typingId}`)?.remove();
    addMessage("assistant", `## 답변을 불러오지 못했습니다\n${error.message}\n\n잠시 후 다시 시도해주세요.`, { generated_by: "local-analysis" });
    toast(error.message, "error");
  }
}

function resetChat() {
  state.conversationId = null;
  $("#chatTitle").textContent = "새 경제 대화";
  $("#chatMessages").innerHTML = `<div class="chat-welcome"><div class="assistant-orb"><svg><use href="#icon-spark"/></svg></div><h2>무엇이 궁금한가요?</h2><p>저장된 경제지표를 바탕으로 쉬운 말로 설명해드릴게요.</p><div class="welcome-prompts"><button>최근 물가 흐름을 설명해줘</button><button>최근 6개월을 비교해줘</button><button>앞으로 3개월 물가 흐름은?</button></div></div>`;
}

async function explainComparison() {
  if (!state.comparison) return;
  const container = $("#compareAiAnswer");
  container.innerHTML = `<article class="panel compare-block"><div class="typing"><span></span><span></span><span></span></div></article>`;
  try {
    const response = await api("/api/chat", { method: "POST", body: JSON.stringify({ question: "선택한 두 기간의 차이와 가능한 경제적 배경을 초보자도 이해하기 쉽게 설명해줘.", comparison_context: state.comparison, detailed: true, outlook_months: 3 }) });
    container.innerHTML = `<article class="panel compare-block">${assistantMessageHtml(response.answer, response, false)}</article>`;
  } catch (error) {
    container.innerHTML = `<article class="panel empty-state">${escapeHtml(error.message)}</article>`;
  }
}

async function loadData() {
  const params = new URLSearchParams({ limit: "10000", include_deleted: $("#showDeleted").checked ? "true" : "false" });
  if ($("#dataIndicator").value) params.set("indicator", $("#dataIndicator").value);
  if ($("#dataStart").value) params.set("start", $("#dataStart").value);
  if ($("#dataEnd").value) params.set("end", $("#dataEnd").value);
  $("#dataTableBody").innerHTML = `<tr><td colspan="6" class="empty-cell">데이터를 불러오고 있습니다.</td></tr>`;
  try {
    state.data = await api(`/api/data?${params}`);
    state.dataPage = 1;
    renderDataTable();
    renderSyncStatus();
  } catch (error) {
    $("#dataTableBody").innerHTML = `<tr><td colspan="6" class="empty-cell">${escapeHtml(error.message)}</td></tr>`;
  }
}

function renderDataTable() {
  if (!state.data.length) {
    $("#dataTableBody").innerHTML = `<tr><td colspan="6" class="empty-cell">조건에 맞는 데이터가 없습니다.</td></tr>`;
    $("#dataPagination").innerHTML = "";
    return;
  }
  const totalPages = Math.max(1, Math.ceil(state.data.length / state.dataPageSize));
  state.dataPage = Math.min(state.dataPage, totalPages);
  const startIndex = (state.dataPage - 1) * state.dataPageSize;
  const visibleRows = state.data.slice(startIndex, startIndex + state.dataPageSize);
  const statusLabels = { official: "ECOS 공식", user: "사용자 입력", modified: "수정됨", deleted: "삭제됨" };
  $("#dataTableBody").innerHTML = visibleRows.map((item) => {
    const meta = indicatorMeta[item.indicator];
    const sourceBadge = item.source === "ecos" && item.status !== "official" ? `<span class="status-badge official">ECOS 공식</span>` : "";
    const actions = item.status === "deleted"
      ? `<button data-action="restore" data-id="${item.id}" title="복원"><svg><use href="#icon-refresh"/></svg></button>`
      : `<button data-action="edit" data-id="${item.id}" title="수정"><svg><use href="#icon-edit"/></svg></button><button data-action="delete" data-id="${item.id}" title="삭제"><svg><use href="#icon-trash"/></svg></button>${item.status === "modified" ? `<button data-action="restore" data-id="${item.id}" title="원본 복원"><svg><use href="#icon-refresh"/></svg></button>` : ""}`;
    return `<tr><td>${item.date}</td><td>${meta.label}</td><td><span class="value-number">${formatNumber(item.value, meta.digits)}</span> <small>${meta.unit}</small></td><td class="memo-cell" title="${escapeHtml(item.memo)}">${escapeHtml(item.memo || "—")}</td><td><div class="status-wrap">${sourceBadge}<span class="status-badge ${item.status}">${statusLabels[item.status]}</span></div></td><td><div class="row-actions">${actions}</div></td></tr>`;
  }).join("");
  $("#dataPagination").innerHTML = `<span>${state.data.length.toLocaleString("ko-KR")}개 중 ${startIndex + 1}–${Math.min(startIndex + state.dataPageSize, state.data.length)}개</span><div class="pagination-buttons"><button data-page="prev" ${state.dataPage === 1 ? "disabled" : ""}>이전</button><strong>${state.dataPage} / ${totalPages}</strong><button data-page="next" ${state.dataPage === totalPages ? "disabled" : ""}>다음</button></div>`;
}

function openDataModal(record = null) {
  $("#dataForm").reset();
  $("#editingId").value = record?.id || "";
  $("#dataModalTitle").textContent = record ? "데이터 수정" : "데이터 추가";
  $("#officialWarning").classList.toggle("hidden", record?.source !== "ecos");
  $("#formDate").disabled = Boolean(record);
  $("#formIndicator").disabled = Boolean(record);
  if (record) {
    $("#formDate").value = record.date;
    $("#formIndicator").value = record.indicator;
    $("#formValue").value = record.value;
    $("#formMemo").value = record.memo || "";
  }
  $("#dataModal").classList.remove("hidden");
}

function closeDataModal() { $("#dataModal").classList.add("hidden"); }

async function saveData(event) {
  event.preventDefault();
  const id = $("#editingId").value;
  const payload = id
    ? { value: Number($("#formValue").value), memo: $("#formMemo").value.trim() }
    : { date: $("#formDate").value, indicator: $("#formIndicator").value, value: Number($("#formValue").value), memo: $("#formMemo").value.trim() };
  try {
    await api(id ? `/api/data/${id}` : "/api/data", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    closeDataModal();
    toast(id ? "데이터를 수정했습니다." : "새 데이터를 추가했습니다.");
    state.summary = null;
    await Promise.all([loadSummary(true), loadData()]);
    loadDashboardChart();
  } catch (error) { toast(error.message, "error"); }
}

function confirmAction(title, text, acceptLabel = "계속하기") {
  $("#confirmTitle").textContent = title;
  $("#confirmText").textContent = text;
  $("#confirmAccept").textContent = acceptLabel;
  $("#confirmModal").classList.remove("hidden");
  return new Promise((resolve) => {
    const finish = (value) => {
      $("#confirmModal").classList.add("hidden");
      $("#confirmAccept").onclick = null; $("#confirmCancel").onclick = null;
      resolve(value);
    };
    $("#confirmAccept").onclick = () => finish(true);
    $("#confirmCancel").onclick = () => finish(false);
  });
}

async function handleDataAction(action, id) {
  const record = state.data.find((item) => item.id === id);
  if (!record) return;
  if (action === "edit") return openDataModal(record);
  if (action === "delete") {
    const ok = await confirmAction("데이터를 삭제할까요?", `${indicatorMeta[record.indicator].label} ${record.date} 값을 기본 목록에서 숨깁니다.\n삭제 후에도 원본 복원이 가능합니다.`, "삭제하기");
    if (!ok) return;
    await api(`/api/data/${id}`, { method: "DELETE" });
    toast("데이터를 삭제 상태로 변경했습니다.");
  }
  if (action === "restore") {
    const ok = await confirmAction("데이터를 복원할까요?", record.source === "ecos" ? "수정 또는 삭제된 값을 한국은행 ECOS 원본값으로 되돌립니다." : "삭제된 사용자 입력 데이터를 다시 활성화합니다.", "복원하기");
    if (!ok) return;
    await api(`/api/data/${id}/restore`, { method: "POST" });
    toast("데이터를 복원했습니다.");
  }
  state.summary = null;
  await Promise.all([loadSummary(true), loadData()]);
  loadDashboardChart();
}

async function renderSyncStatus() {
  try {
    const sync = await api("/api/data/sync-status");
    const latest = state.summary?.period?.end || "—";
    $("#syncStrip").querySelector("strong").textContent = `최종 관측 월 ${latest}`;
    $("#syncStrip").querySelector("small").textContent = sync.last_success_at ? `마지막 갱신 ${formatTimestamp(sync.last_success_at)} · 추가 ${sync.added || 0}개` : "저장된 초기 데이터 사용 중";
  } catch (_) {}
}

async function syncData() {
  const button = $("#syncData");
  button.disabled = true; button.innerHTML = `<svg><use href="#icon-refresh"/></svg> 확인 중`;
  try {
    const result = await api("/api/data/sync", { method: "POST" });
    toast(result.message || "최신 데이터를 확인했습니다.", result.status === "failed" ? "error" : "success");
    state.summary = null;
    await Promise.all([loadSummary(true), loadData()]);
    loadDashboardChart();
  } catch (error) { toast(error.message, "error"); }
  finally { button.disabled = false; button.innerHTML = `<svg><use href="#icon-refresh"/></svg> 최신 데이터 확인`; }
}

async function loadConversations() {
  try {
    state.conversations = await api("/api/conversations");
    if (!state.conversations.length) {
      $("#conversationList").innerHTML = `<div class="panel empty-state"><div><strong>아직 저장된 대화가 없습니다.</strong><p>AI에게 첫 질문을 보내면 자동으로 저장됩니다.</p></div></div>`;
      return;
    }
    $("#conversationList").innerHTML = state.conversations.map((item) => `<article class="conversation-card"><div class="conversation-icon"><svg><use href="#icon-chat"/></svg></div><div class="conversation-main" data-open-conversation="${item.id}"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.preview)}</p></div><div class="conversation-meta"><time>${formatTimestamp(item.updated_at)}</time><span>${item.message_count}개 메시지</span><button data-delete-conversation="${item.id}" aria-label="대화 삭제"><svg><use href="#icon-trash"/></svg></button></div></article>`).join("");
  } catch (error) { $("#conversationList").innerHTML = `<div class="panel empty-state">${escapeHtml(error.message)}</div>`; }
}

async function openConversation(id) {
  try {
    const conversation = await api(`/api/conversations/${id}`);
    state.conversationId = id;
    $("#chatTitle").textContent = conversation.title;
    $("#chatMessages").innerHTML = conversation.messages.map((message) => message.role === "user" ? `<div class="message user"><div class="user-bubble">${escapeHtml(message.content)}</div></div>` : assistantMessageHtml(message.content, message.metadata || {})).join("");
    setView("chat");
    $("#chatMessages").scrollTop = $("#chatMessages").scrollHeight;
  } catch (error) { toast(error.message, "error"); }
}

async function deleteConversation(id) {
  const ok = await confirmAction("대화를 삭제할까요?", "삭제한 대화 기록은 복원할 수 없습니다.", "삭제하기");
  if (!ok) return;
  try {
    await api(`/api/conversations/${id}`, { method: "DELETE" });
    if (state.conversationId === id) resetChat();
    toast("대화를 삭제했습니다.");
    loadConversations();
  } catch (error) { toast(error.message, "error"); }
}

function bindEvents() {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  $$('[data-view-link]').forEach((button) => button.addEventListener("click", () => setView(button.dataset.viewLink)));
  $("#menuButton").addEventListener("click", () => { $("#sidebar").classList.add("open"); $("#sidebarBackdrop").classList.add("open"); });
  $("#sidebarBackdrop").addEventListener("click", () => { $("#sidebar").classList.remove("open"); $("#sidebarBackdrop").classList.remove("open"); });

  const applyTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("econscope-theme", theme);
    $("#themeToggle span").textContent = theme === "dark" ? "라이트 모드" : "다크 모드";
  };
  const toggleTheme = () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  $("#themeToggle").addEventListener("click", toggleTheme);
  $(".mobile-theme").addEventListener("click", toggleTheme);
  applyTheme(localStorage.getItem("econscope-theme") || "light");

  $("#dashboardQuestionForm").addEventListener("submit", (event) => { event.preventDefault(); sendChat($("#dashboardQuestion").value); $("#dashboardQuestion").value = ""; });
  $("#dashboardQuestions").addEventListener("click", (event) => { if (event.target.matches("button")) sendChat(event.target.textContent); });
  $("#dashboardIndicator").addEventListener("change", (event) => { state.dashboardIndicator = event.target.value; loadDashboardChart(); });
  $("#dashboardRange").addEventListener("click", (event) => { if (!event.target.matches("button")) return; $$("#dashboardRange button").forEach((button) => button.classList.toggle("active", button === event.target)); state.dashboardRange = Number(event.target.dataset.months); loadDashboardChart(); });

  $("#runCompare").addEventListener("click", runComparison);
  $("#explainCompare").addEventListener("click", explainComparison);

  $("#chatForm").addEventListener("submit", (event) => { event.preventDefault(); sendChat($("#chatInput").value); });
  $("#chatInput").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#chatForm").requestSubmit(); } });
  $("#chatInput").addEventListener("input", (event) => { event.target.style.height = "auto"; event.target.style.height = `${Math.min(event.target.scrollHeight, 130)}px`; });
  $("#chatMessages").addEventListener("click", (event) => {
    if (event.target.matches(".welcome-prompts button")) sendChat(event.target.textContent);
    if (event.target.matches(".detail-button")) sendChat("방금 답변을 더 자세히 분석해줘.", { detailed: true });
  });
  $("#newChat").addEventListener("click", resetChat);
  $("#historyNewChat").addEventListener("click", () => { resetChat(); setView("chat"); });

  $("#addData").addEventListener("click", () => openDataModal());
  $$(".modal-close, .modal-cancel").forEach((button) => button.addEventListener("click", closeDataModal));
  $("#dataModal").addEventListener("click", (event) => { if (event.target === $("#dataModal")) closeDataModal(); });
  $("#dataForm").addEventListener("submit", saveData);
  $("#dataTableBody").addEventListener("click", (event) => { const button = event.target.closest("button[data-action]"); if (button) handleDataAction(button.dataset.action, button.dataset.id).catch((error) => toast(error.message, "error")); });
  $("#dataPagination").addEventListener("click", (event) => { const button = event.target.closest("button[data-page]"); if (!button || button.disabled) return; state.dataPage += button.dataset.page === "next" ? 1 : -1; renderDataTable(); $(".data-panel").scrollIntoView({ behavior: "smooth", block: "start" }); });
  ["#dataIndicator", "#dataStart", "#dataEnd", "#showDeleted"].forEach((selector) => $(selector).addEventListener("change", loadData));
  $("#syncData").addEventListener("click", syncData);
  $("#restoreAll").addEventListener("click", async () => {
    const ok = await confirmAction("전체 원본을 복원할까요?", "수정·삭제된 ECOS 데이터를 원본값으로 되돌리고 삭제된 사용자 입력을 다시 활성화합니다.", "전체 복원");
    if (!ok) return;
    try { const result = await api("/api/data/restore-all", { method: "POST" }); toast(`${result.restored}개 데이터를 복원했습니다.`); state.summary = null; await Promise.all([loadSummary(true), loadData()]); loadDashboardChart(); } catch (error) { toast(error.message, "error"); }
  });
  $("#exportCsv").addEventListener("click", () => window.open(apiUrl("/api/data/export?format=csv"), "_blank"));
  $("#exportJson").addEventListener("click", () => window.open(apiUrl("/api/data/export?format=json"), "_blank"));

  $("#conversationList").addEventListener("click", (event) => {
    const opener = event.target.closest("[data-open-conversation]");
    const deleter = event.target.closest("[data-delete-conversation]");
    if (opener) openConversation(opener.dataset.openConversation);
    if (deleter) deleteConversation(deleter.dataset.deleteConversation);
  });
}

async function init() {
  bindEvents();
  try {
    await loadSummary();
    await loadDashboardChart();
  } catch (error) {
    toast(`서버에 연결하지 못했습니다: ${error.message}`, "error");
    $("#metricGrid").innerHTML = `<div class="panel empty-state" style="grid-column:1/-1">백엔드 서버 연결을 확인해주세요.<br/>${escapeHtml(API_BASE)}</div>`;
  }
}

init();
