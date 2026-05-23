// ==========================================================================
// VanguardOps · Operational Console
// Vanilla ES module. No build step required.
// Talks to /api/v1 via fetch with Bearer JWT in localStorage.
// ==========================================================================

const API_BASE = "/api/v1";
const TOKEN_KEY = "vops.access_token";
const REFRESH_KEY = "vops.refresh_token";
const USER_KEY = "vops.user";

// --------------------------------------------------------------------------
// Token store
// --------------------------------------------------------------------------
const auth = {
    accessToken: () => localStorage.getItem(TOKEN_KEY),
    refreshToken: () => localStorage.getItem(REFRESH_KEY),
    user: () => {
        try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); }
        catch { return null; }
    },
    save(tokenPair, user) {
        localStorage.setItem(TOKEN_KEY, tokenPair.access_token);
        localStorage.setItem(REFRESH_KEY, tokenPair.refresh_token);
        if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    },
    clear() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
        localStorage.removeItem(USER_KEY);
    },
    role() { return (this.user() || {}).role || "viewer"; },
};

const ROLE_RANK = { viewer: 0, operator: 1, admin: 2 };
const roleAtLeast = (required) => ROLE_RANK[auth.role()] >= ROLE_RANK[required];

// --------------------------------------------------------------------------
// HTTP layer with automatic refresh on 401
// --------------------------------------------------------------------------
let refreshing = null;

async function refreshAccessToken() {
    if (refreshing) return refreshing;
    const rt = auth.refreshToken();
    if (!rt) return null;
    refreshing = (async () => {
        try {
            const res = await fetch(`${API_BASE}/auth/refresh`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ refresh_token: rt }),
            });
            if (!res.ok) return null;
            const pair = await res.json();
            auth.save(pair, auth.user());
            return pair.access_token;
        } finally {
            refreshing = null;
        }
    })();
    return refreshing;
}

async function api(path, { method = "GET", body, params, retry = true } = {}) {
    const url = new URL(`${API_BASE}${path}`, window.location.origin);
    if (params) {
        for (const [k, v] of Object.entries(params)) {
            if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
        }
    }
    const headers = { "Accept": "application/json" };
    const token = auth.accessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (body) headers["Content-Type"] = "application/json";

    const res = await fetch(url, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
    });

    if (res.status === 401 && retry && auth.refreshToken()) {
        const fresh = await refreshAccessToken();
        if (fresh) return api(path, { method, body, params, retry: false });
        signOut();
        throw new Error("Session expired");
    }

    if (!res.ok) {
        let problem;
        try { problem = await res.json(); } catch { problem = { detail: res.statusText }; }
        const err = new Error(problem.detail || `HTTP ${res.status}`);
        err.problem = problem;
        err.status = res.status;
        throw err;
    }

    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    return ct.includes("application/json") ? await res.json() : await res.text();
}

// --------------------------------------------------------------------------
// Toasts
// --------------------------------------------------------------------------
function toast(message, kind = "info") {
    const host = document.getElementById("toast-host");
    if (!host) return;
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.textContent = message;
    host.appendChild(el);
    setTimeout(() => el.remove(), 4500);
}

// --------------------------------------------------------------------------
// Auth flow
// --------------------------------------------------------------------------
async function signIn(email, password) {
    const pair = await api("/auth/login", {
        method: "POST",
        body: { email, password },
    });
    localStorage.setItem(TOKEN_KEY, pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
    const me = await api("/auth/me");
    localStorage.setItem(USER_KEY, JSON.stringify(me));
}

function signOut() {
    auth.clear();
    showAuthScreen();
    stopPolling();
}

// --------------------------------------------------------------------------
// View / route management
// --------------------------------------------------------------------------
const VIEWS = ["dashboard", "tickets", "assets", "workflows", "audit"];
const VIEW_TITLE = {
    dashboard: "Dashboard",
    tickets: "Tickets",
    assets: "Assets",
    workflows: "Workflows",
    audit: "Audit Log",
};
let currentView = "dashboard";

function showView(name) {
    if (!VIEWS.includes(name)) name = "dashboard";
    currentView = name;
    document.querySelectorAll("[data-view]").forEach((el) => {
        const isActive = el.dataset.view === name;
        if (el.tagName === "SECTION") {
            el.hidden = !isActive;
        } else {
            el.classList.toggle("active", isActive);
        }
    });
    document.getElementById("view-title").textContent = VIEW_TITLE[name];
    refreshCurrentView();
}

function showAuthScreen() {
    document.getElementById("auth-screen").hidden = false;
    document.getElementById("app-container").hidden = true;
}

function showAppShell() {
    document.getElementById("auth-screen").hidden = true;
    document.getElementById("app-container").hidden = false;
    const u = auth.user();
    if (u) {
        document.getElementById("user-email").textContent = u.email;
        document.getElementById("user-role").textContent = u.role;
    }
    // Hide privileged buttons for viewers
    document.querySelectorAll("[data-role-min]").forEach((btn) => {
        btn.hidden = !roleAtLeast(btn.dataset.roleMin);
    });
}

// --------------------------------------------------------------------------
// Renderers
// --------------------------------------------------------------------------
const fmt = {
    time(iso) {
        if (!iso) return "—";
        const d = new Date(iso);
        return d.toLocaleString([], { hour: "2-digit", minute: "2-digit", month: "short", day: "2-digit" });
    },
    timeShort(iso) {
        if (!iso) return "—";
        return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    },
    badge(value) {
        if (!value) return "";
        const k = String(value).toLowerCase().replace(/-/g, "_");
        return `<span class="badge badge-${k}">${value}</span>`;
    },
    truncate(s, n = 80) {
        if (!s) return "";
        return s.length > n ? s.slice(0, n) + "…" : s;
    },
};

function renderTicketsTable(items, tbody, { compact = false } = {}) {
    tbody.innerHTML = "";
    if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="${compact ? 5 : 8}" class="empty">No tickets yet</td></tr>`;
        return;
    }
    for (const t of items) {
        const tr = document.createElement("tr");
        if (compact) {
            tr.innerHTML = `
                <td>#${t.id}</td>
                <td><strong>${escapeHtml(t.title)}</strong></td>
                <td>${fmt.badge(t.priority)}</td>
                <td>${fmt.badge(t.status)}</td>
                <td><span class="muted">${escapeHtml(t.assigned_to || "Unassigned")}</span></td>
            `;
        } else {
            const canEdit = roleAtLeast("operator");
            tr.innerHTML = `
                <td>#${t.id}</td>
                <td><strong>${escapeHtml(t.title)}</strong></td>
                <td><span class="muted">${escapeHtml(t.category || "—")}</span></td>
                <td>${fmt.badge(t.priority)}</td>
                <td>${fmt.badge(t.status)}</td>
                <td><span class="muted">${escapeHtml(t.assigned_to || "Unassigned")}</span></td>
                <td><span class="muted">${fmt.time(t.due_at)}</span></td>
                <td>${canEdit ? `<button class="btn btn-sm" data-action="transition" data-id="${t.id}">Status</button>` : ""}</td>
            `;
        }
        tbody.appendChild(tr);
    }
}

function renderAssets(items) {
    const tbody = document.getElementById("assets-tbody");
    tbody.innerHTML = "";
    if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty">No assets registered</td></tr>`;
        return;
    }
    for (const a of items) {
        tbody.insertAdjacentHTML("beforeend", `
            <tr>
                <td>#${a.id}</td>
                <td><strong>${escapeHtml(a.name)}</strong></td>
                <td><span class="muted">${a.asset_type}</span></td>
                <td>${fmt.badge(a.status)}</td>
                <td><code>${escapeHtml(a.ip_address || "—")}</code></td>
                <td>${escapeHtml(a.owner || "—")}</td>
                <td>${escapeHtml(a.location || "—")}</td>
            </tr>
        `);
    }
}

function renderWorkflows(items) {
    const tbody = document.getElementById("workflows-tbody");
    tbody.innerHTML = "";
    if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty">No workflows</td></tr>`;
        return;
    }
    for (const w of items) {
        tbody.insertAdjacentHTML("beforeend", `
            <tr>
                <td>#${w.id}</td>
                <td><strong>${escapeHtml(w.name)}</strong></td>
                <td><span class="muted">${escapeHtml(w.trigger_type)}</span></td>
                <td>${fmt.badge(w.status)}</td>
                <td>${w.ticket_id ? `#${w.ticket_id}` : "—"}</td>
                <td><span class="muted">${fmt.time(w.updated_at)}</span></td>
            </tr>
        `);
    }
}

function renderTimeline(items, container, { limit = 30 } = {}) {
    container.innerHTML = "";
    if (!items.length) {
        container.innerHTML = `<div class="empty">No activity yet</div>`;
        return;
    }
    for (const log of items.slice(0, limit)) {
        const dotClass = log.event_type.includes("succeed") || log.event_type.includes("created")
            ? "success"
            : log.event_type.includes("fail") || log.event_type.includes("error")
            ? "danger"
            : log.event_type.includes("retry") || log.event_type.includes("started")
            ? "warning"
            : "";
        const detailsStr = log.details_json && Object.keys(log.details_json).length
            ? JSON.stringify(log.details_json, null, 2)
            : "";
        container.insertAdjacentHTML("beforeend", `
            <div class="timeline-item">
                <div class="timeline-dot ${dotClass}"></div>
                <div class="timeline-content">
                    <div class="timeline-time">${fmt.timeShort(log.timestamp_utc)} · ${log.entity_type.toUpperCase()} #${log.entity_id}</div>
                    <div class="timeline-title">${log.event_type.replace(/_/g, " ").toUpperCase()}</div>
                    ${detailsStr ? `<div class="timeline-desc">${escapeHtml(detailsStr)}</div>` : ""}
                </div>
            </div>
        `);
    }
}

function escapeHtml(s) {
    if (s === undefined || s === null) return "";
    return String(s).replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}

// --------------------------------------------------------------------------
// View loaders
// --------------------------------------------------------------------------
async function loadDashboard() {
    try {
        const [tickets, workflows, logs] = await Promise.all([
            api("/tickets/", { params: { size: 50 } }),
            api("/workflows/", { params: { size: 50 } }),
            api("/activity-log/", { params: { size: 50 } }),
        ]);
        const open = tickets.items.filter((t) => t.status !== "CLOSED" && t.status !== "RESOLVED");
        const critical = tickets.items.filter((t) => t.priority === "CRITICAL" && t.status !== "CLOSED");
        const inflight = workflows.items.filter((w) => w.status === "PENDING" || w.status === "RUNNING");

        document.getElementById("stat-tickets").textContent = open.length;
        document.getElementById("stat-tickets-sub").textContent = `${tickets.total} total`;
        document.getElementById("stat-critical").textContent = critical.length;
        document.getElementById("stat-workflows").textContent = inflight.length;
        document.getElementById("stat-events").textContent = logs.total;

        renderTicketsTable(tickets.items.slice(0, 6), document.getElementById("dashboard-tickets-tbody"), { compact: true });
        renderTimeline(logs.items, document.getElementById("dashboard-timeline"), { limit: 12 });
    } catch (e) {
        console.error(e);
    }
}

async function loadTickets() {
    const status_value = document.getElementById("ticket-filter-status").value;
    const priority = document.getElementById("ticket-filter-priority").value;
    const params = { size: 100 };
    if (status_value) params.status_value = status_value;
    if (priority) params.priority = priority;
    const path = (status_value || priority) ? "/tickets/filter" : "/tickets/";
    const data = await api(path, { params });
    renderTicketsTable(data.items, document.getElementById("tickets-tbody"));
}

async function loadAssets() {
    const data = await api("/assets/", { params: { size: 100 } });
    renderAssets(data.items);
}

async function loadWorkflows() {
    const data = await api("/workflows/", { params: { size: 100 } });
    renderWorkflows(data.items);
}

async function loadAudit() {
    const data = await api("/activity-log/", { params: { size: 100 } });
    renderTimeline(data.items, document.getElementById("audit-timeline"), { limit: 100 });
}

async function refreshCurrentView() {
    const fn = {
        dashboard: loadDashboard,
        tickets: loadTickets,
        assets: loadAssets,
        workflows: loadWorkflows,
        audit: loadAudit,
    }[currentView];
    if (fn) {
        try { await fn(); }
        catch (e) { console.error(e); }
    }
}

// --------------------------------------------------------------------------
// Polling
// --------------------------------------------------------------------------
let pollHandle = null;
function startPolling() {
    stopPolling();
    pollHandle = setInterval(refreshCurrentView, 5000);
    pollHealth();
    setInterval(pollHealth, 15000);
}
function stopPolling() {
    if (pollHandle) clearInterval(pollHandle);
    pollHandle = null;
}

async function pollHealth() {
    const pill = document.getElementById("health-pill");
    if (!pill) return;
    try {
        const res = await fetch("/livez");
        if (res.ok) {
            const body = await res.json();
            pill.classList.remove("bad");
            pill.classList.add("ok");
            pill.querySelector("span:last-child").textContent = `${body.service} · ${body.version}`;
            document.getElementById("env-badge").textContent = `v${body.version}`;
        } else {
            pill.classList.remove("ok");
            pill.classList.add("bad");
        }
    } catch {
        pill.classList.add("bad");
    }
}

// --------------------------------------------------------------------------
// Modal helpers
// --------------------------------------------------------------------------
function openModal(id) { document.getElementById(id).hidden = false; }
function closeModal(id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.hidden = true;
    const form = m.querySelector("form");
    if (form) form.reset();
}

// --------------------------------------------------------------------------
// Form handlers
// --------------------------------------------------------------------------
function formToJson(form) {
    const fd = new FormData(form);
    const out = {};
    for (const [k, v] of fd.entries()) {
        if (v === "" || v === null) continue;
        if (form.elements[k]?.type === "number") {
            out[k] = Number(v);
        } else {
            out[k] = v;
        }
    }
    return out;
}

async function handleTicketCreate(e) {
    e.preventDefault();
    try {
        const payload = formToJson(e.target);
        await api("/tickets/", { method: "POST", body: payload });
        toast("Ticket created", "success");
        closeModal("ticket-modal");
        refreshCurrentView();
    } catch (err) {
        toast(err.problem?.detail || err.message, "error");
    }
}

async function handleAssetCreate(e) {
    e.preventDefault();
    try {
        const payload = formToJson(e.target);
        await api("/assets/", { method: "POST", body: payload });
        toast("Asset created", "success");
        closeModal("asset-modal");
        refreshCurrentView();
    } catch (err) {
        toast(err.problem?.detail || err.message, "error");
    }
}

async function handleWorkflowCreate(e) {
    e.preventDefault();
    try {
        const payload = formToJson(e.target);
        await api("/workflows/", { method: "POST", body: payload });
        toast("Workflow created (status PENDING)", "success");
        closeModal("workflow-modal");
        refreshCurrentView();
    } catch (err) {
        toast(err.problem?.detail || err.message, "error");
    }
}

async function handleTicketStatusUpdate(e) {
    e.preventDefault();
    const form = e.target;
    const ticketId = form.elements.ticket_id.value;
    const status = form.elements.status.value;
    try {
        await api(`/tickets/${ticketId}`, { method: "PATCH", body: { status } });
        toast(`Ticket #${ticketId} → ${status}`, "success");
        closeModal("ticket-status-modal");
        refreshCurrentView();
    } catch (err) {
        toast(err.problem?.detail || err.message, "error");
    }
}

async function handleLogin(e) {
    e.preventDefault();
    const errEl = document.getElementById("login-error");
    errEl.hidden = true;
    const fd = new FormData(e.target);
    try {
        await signIn(fd.get("email"), fd.get("password"));
        showAppShell();
        showView("dashboard");
        startPolling();
    } catch (err) {
        errEl.textContent = err.problem?.detail || "Authentication failed";
        errEl.hidden = false;
    }
}

// --------------------------------------------------------------------------
// Wiring
// --------------------------------------------------------------------------
function wire() {
    // Login
    document.getElementById("login-form").addEventListener("submit", handleLogin);

    // Logout
    document.getElementById("logout-btn").addEventListener("click", signOut);

    // Nav clicks
    document.querySelectorAll(".nav-item[data-view]").forEach((el) => {
        el.addEventListener("click", (e) => {
            e.preventDefault();
            showView(el.dataset.view);
        });
    });
    document.querySelectorAll("[data-go-view]").forEach((el) => {
        el.addEventListener("click", () => showView(el.dataset.goView));
    });

    // Modal openers
    document.querySelectorAll("[data-open-modal]").forEach((btn) => {
        btn.addEventListener("click", () => openModal(btn.dataset.openModal));
    });
    document.querySelectorAll("[data-close-modal]").forEach((el) => {
        el.addEventListener("click", () => {
            const m = el.closest(".modal");
            if (m) closeModal(m.id);
        });
    });

    // Forms
    document.getElementById("ticket-form").addEventListener("submit", handleTicketCreate);
    document.getElementById("asset-form").addEventListener("submit", handleAssetCreate);
    document.getElementById("workflow-form").addEventListener("submit", handleWorkflowCreate);
    document.getElementById("ticket-status-form").addEventListener("submit", handleTicketStatusUpdate);

    // Ticket filter
    document.getElementById("ticket-filter-apply").addEventListener("click", () => loadTickets());

    // Tickets table actions (event delegation)
    document.getElementById("tickets-tbody").addEventListener("click", (e) => {
        const btn = e.target.closest("[data-action=transition]");
        if (!btn) return;
        const id = btn.dataset.id;
        const form = document.getElementById("ticket-status-form");
        form.elements.ticket_id.value = id;
        document.getElementById("ts-ticket-id").textContent = `#${id}`;
        openModal("ticket-status-modal");
    });
}

// --------------------------------------------------------------------------
// Boot
// --------------------------------------------------------------------------
function boot() {
    wire();
    if (auth.accessToken()) {
        showAppShell();
        showView("dashboard");
        startPolling();
    } else {
        showAuthScreen();
    }
}

document.addEventListener("DOMContentLoaded", boot);
