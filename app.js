let token = sessionStorage.getItem("verita-token") || "";
let cases = [];
let selectedReviewId = "";
let activeFilter = "all";
let onboardingStep = 1;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) logout(false);
    throw new Error(payload.error || `Request failed with status ${response.status}`);
  }
  return payload;
}

function statusClass(status) {
  return `status-${status.toLowerCase()}`;
}

function renderTable(items, compact = false) {
  return `<table>
    <thead><tr><th>Customer</th><th>Case ID</th><th>Market</th>${compact ? "" : "<th>Type</th>"}<th>Status</th><th>Patronum risk</th><th></th></tr></thead>
    <tbody>${items.map((item) => `<tr>
      <td><div class="customer-cell"><span class="mini-avatar">${escapeHtml(item.initials)}</span><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.created)}</small></span></div></td>
      <td>${escapeHtml(item.id)}</td>
      <td>${escapeHtml(item.market)}</td>
      ${compact ? "" : `<td>${escapeHtml(item.type)}</td>`}
      <td><span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td>
      <td><span class="status risk-${item.risk.toLowerCase()}">${escapeHtml(item.risk)} · ${item.score}</span></td>
      <td><button class="open-case" data-open-review="${escapeHtml(item.id)}">${item.status === "Review" ? "Review →" : "Details →"}</button></td>
    </tr>`).join("")}</tbody>
  </table>`;
}

async function loadCases() {
  cases = await api("/api/cases");
  renderDashboardTable();
  renderCases();
  renderReviews();
}

async function loadDashboard() {
  const dashboard = await api("/api/dashboard");
  const cards = $$(".metric-card strong");
  cards[0].textContent = dashboard.activeCases.toLocaleString();
  cards[1].textContent = `${dashboard.straightThroughRate}%`;
  cards[2].textContent = dashboard.medianActivationTime;
  cards[3].textContent = `${dashboard.dataQualityScore}%`;
}

function renderDashboardTable() {
  $("#attention-table").innerHTML = renderTable(cases.filter((item) => item.status === "Review").slice(0, 3), true);
}

function renderCases() {
  const query = $("#case-search").value.trim().toLowerCase();
  const visible = cases.filter((item) => {
    const matchesFilter = activeFilter === "all" || item.status === activeFilter;
    const matchesQuery = !query || [item.name, item.id, item.market, item.type].join(" ").toLowerCase().includes(query);
    return matchesFilter && matchesQuery;
  });
  $("#cases-table").innerHTML = renderTable(visible);
}

function renderReviews() {
  const reviews = cases.filter((item) => item.status === "Review");
  $("#review-badge").textContent = reviews.length;
  $("#queue-count").textContent = reviews.length;
  if (!reviews.some((item) => item.id === selectedReviewId)) selectedReviewId = reviews[0]?.id || "";
  $("#review-list").innerHTML = reviews.length ? reviews.map((item) => `
    <button class="review-list-card ${item.id === selectedReviewId ? "active" : ""}" data-review-id="${item.id}">
      <div><strong>${escapeHtml(item.name)}</strong><span class="status risk-${item.risk.toLowerCase()}">${escapeHtml(item.risk)}</span></div>
      <p><small>${escapeHtml(item.id)} · ${escapeHtml(item.market)}</small><small>${escapeHtml(item.created)}</small></p>
    </button>`).join("") : `<div class="empty-review"><h3>Queue cleared</h3><p>No decisions are waiting for manual review.</p></div>`;
  renderReviewDetail();
}

async function renderReviewDetail() {
  if (!selectedReviewId) {
    $("#review-detail").innerHTML = `<div class="empty-review"><h3>All caught up</h3><p>Patronum has no cases requiring a human decision.</p></div>`;
    return;
  }
  const item = await api(`/api/cases/${encodeURIComponent(selectedReviewId)}`);
  $("#review-detail").innerHTML = `
    <header class="detail-header">
      <div><p class="eyebrow">Patronum decision support</p><h3>${escapeHtml(item.name)}</h3><p>${escapeHtml(item.id)} · opened ${escapeHtml(item.created)}</p></div>
      <div class="risk-score"><strong>${item.score}</strong><span>CONFIDENCE SCORE</span></div>
    </header>
    <div class="detail-body">
      <div class="detail-meta">
        <div><span>Market</span><strong>${escapeHtml(item.market)}</strong></div>
        <div><span>Customer type</span><strong>${escapeHtml(item.type)}</strong></div>
        <div><span>Risk level</span><strong>${escapeHtml(item.risk)}</strong></div>
        <div><span>Service address</span><strong>${escapeHtml(item.address)}</strong></div>
      </div>
      <div class="ai-explanation">
        <h4>Why Patronum requested a human review</h4>
        <ul>${item.reason.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>
      </div>
      <div class="decision-actions">
        <button class="primary-button approve-button" data-decision="approve">Approve onboarding</button>
        <button class="secondary-button escalate-button" data-decision="escalate">Escalate for investigation</button>
      </div>
    </div>`;
}

async function loadAudit() {
  const audit = await api("/api/audit?limit=10");
  $("#audit-chain-status").textContent = audit.chain.valid
    ? `Verified hash chain · ${audit.chain.entries} evidence entries`
    : `Integrity warning · failed at entry ${audit.chain.failedAt}`;
  $("#audit-table").innerHTML = `<table>
    <thead><tr><th>Timestamp</th><th>Actor</th><th>Action</th><th>Entity</th><th>Evidence hash</th></tr></thead>
    <tbody>${audit.entries.map((entry) => `<tr>
      <td>${escapeHtml(new Date(entry.createdAt).toLocaleString())}</td>
      <td>${escapeHtml(entry.actor)}</td>
      <td>${escapeHtml(entry.action)}</td>
      <td>${escapeHtml(entry.entityId)}</td>
      <td><code>${escapeHtml(entry.entryHash.slice(0, 14))}…</code></td>
    </tr>`).join("")}</tbody>
  </table>`;
}

async function switchView(view) {
  const titles = { dashboard: "Operations overview", cases: "Onboarding cases", reviews: "Compliance review queue", governance: "Data governance" };
  $$(".view").forEach((section) => section.classList.toggle("active", section.id === `${view}-view`));
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("#page-title").textContent = titles[view];
  if (view === "governance") await loadAudit();
}

function showToast(message) {
  $("#toast").textContent = message;
  $("#toast").classList.remove("hidden");
  setTimeout(() => $("#toast").classList.add("hidden"), 2600);
}

function openCreate() {
  onboardingStep = 1;
  $("#onboarding-form").reset();
  $("#uploaded-file").classList.add("hidden");
  $("#ai-loading").classList.remove("hidden");
  $("#ai-result").classList.add("hidden");
  $("#create-modal").classList.remove("hidden");
  updateStepper();
}

function updateStepper() {
  $$(".form-step").forEach((step) => step.classList.toggle("active", Number(step.dataset.step) === onboardingStep));
  $$(".step").forEach((step) => step.classList.toggle("active", Number(step.dataset.stepMarker) <= onboardingStep));
  $("#previous-step").classList.toggle("hidden", onboardingStep === 1);
  $("#next-step").textContent = onboardingStep === 3 ? "Create and activate" : "Continue";
}

async function createCase() {
  const body = Object.fromEntries(new FormData($("#onboarding-form")));
  const item = await api("/api/cases", { method: "POST", body: JSON.stringify(body) });
  $("#create-modal").classList.add("hidden");
  await Promise.all([loadCases(), loadDashboard()]);
  showToast(item.status === "Approved"
    ? "Customer activated automatically · audit evidence recorded"
    : "Case created · human review required");
}

async function login() {
  try {
    const session = await api("/api/auth/login", { method: "POST", body: "{}" });
    token = session.token;
    sessionStorage.setItem("verita-token", token);
    $("#login-screen").classList.add("hidden");
    $("#app-shell").classList.remove("hidden");
    await Promise.all([loadCases(), loadDashboard()]);
  } catch (error) {
    showToast(error.message);
  }
}

function logout(notify = true) {
  token = "";
  sessionStorage.removeItem("verita-token");
  $("#app-shell").classList.add("hidden");
  $("#login-screen").classList.remove("hidden");
  if (notify) showToast("Cerberus session closed");
}

$("#login-button").addEventListener("click", login);
$("#logout-button").addEventListener("click", () => logout());
$("#open-create-button").addEventListener("click", openCreate);
$("#close-create-button").addEventListener("click", () => $("#create-modal").classList.add("hidden"));
$("#simulate-upload").addEventListener("click", () => $("#uploaded-file").classList.remove("hidden"));
$("#previous-step").addEventListener("click", () => { onboardingStep -= 1; updateStepper(); });
$("#next-step").addEventListener("click", async () => {
  if (onboardingStep === 1 && !$("#onboarding-form").reportValidity()) return;
  if (onboardingStep === 2 && $("#uploaded-file").classList.contains("hidden")) return showToast("Upload identity evidence before continuing");
  if (onboardingStep < 3) {
    onboardingStep += 1;
    updateStepper();
    if (onboardingStep === 3) setTimeout(() => { $("#ai-loading").classList.add("hidden"); $("#ai-result").classList.remove("hidden"); }, 1100);
  } else if (!$("#ai-result").classList.contains("hidden")) {
    try { await createCase(); } catch (error) { showToast(error.message); }
  }
});
$("#case-search").addEventListener("input", renderCases);
$("#refresh-audit-button").addEventListener("click", loadAudit);

document.addEventListener("click", async (event) => {
  const nav = event.target.closest("[data-view]");
  const shortcut = event.target.closest("[data-switch-view]");
  const filter = event.target.closest("[data-filter]");
  const review = event.target.closest("[data-review-id]");
  const openReview = event.target.closest("[data-open-review]");
  const decision = event.target.closest("[data-decision]");
  if (nav) await switchView(nav.dataset.view);
  if (shortcut) await switchView(shortcut.dataset.switchView);
  if (filter) {
    activeFilter = filter.dataset.filter;
    $$(".filter-button").forEach((button) => button.classList.toggle("active", button === filter));
    renderCases();
  }
  if (review) {
    selectedReviewId = review.dataset.reviewId;
    renderReviews();
  }
  if (openReview) {
    const item = cases.find((candidate) => candidate.id === openReview.dataset.openReview);
    if (item?.status === "Review") {
      selectedReviewId = item.id;
      await switchView("reviews");
      renderReviews();
    } else if (item) {
      showToast(`${item.id} · audit-ready customer record available`);
    }
  }
  if (decision) {
    try {
      const item = await api(`/api/cases/${encodeURIComponent(selectedReviewId)}/decision`, {
        method: "POST",
        body: JSON.stringify({ decision: decision.dataset.decision, comment: "Decision completed in Verita compliance console" }),
      });
      showToast(item.status === "Approved" ? "Onboarding approved · decision logged" : "Case escalated · investigation workflow opened");
      await Promise.all([loadCases(), loadDashboard()]);
    } catch (error) {
      showToast(error.message);
    }
  }
});
