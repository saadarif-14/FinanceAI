const BASE = "/api";

// ── Client-side cache ─────────────────────────────────────────────────────────
// Stores { data, expiresAt } per cache key. Returns instantly on repeat
// navigations, avoiding the loading spinner every time a page remounts.
const _clientCache = {};

function _cacheGet(key) {
  const entry = _clientCache[key];
  return entry && Date.now() < entry.expiresAt ? entry.data : null;
}

function _cacheSet(key, data, ttlMs = 30_000) {
  _clientCache[key] = { data, expiresAt: Date.now() + ttlMs };
}

function _cacheDelete(key) {
  delete _clientCache[key];
}

function _cacheDeletePrefix(prefix) {
  Object.keys(_clientCache).forEach((k) => { if (k.startsWith(prefix)) delete _clientCache[k]; });
}

async function cached(key, fn, ttlMs = 30_000) {
  const hit = _cacheGet(key);
  if (hit) return hit;
  const data = await fn();
  _cacheSet(key, data, ttlMs);
  return data;
}

function getToken() {
  return localStorage.getItem("fa_token");
}

function getRefreshToken() {
  return localStorage.getItem("fa_refresh_token");
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function _refreshAccessToken() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) throw new Error("No refresh token");

  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!res.ok) {
    localStorage.removeItem("fa_token");
    localStorage.removeItem("fa_refresh_token");
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  const data = await res.json();
  localStorage.setItem("fa_token", data.token);
  if (data.refresh_token) localStorage.setItem("fa_refresh_token", data.refresh_token);
  return data.token;
}

let _refreshing = null;

async function request(method, path, body, isForm = false) {
  const doRequest = async (token) => {
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    if (!isForm && body) headers["Content-Type"] = "application/json";

    return fetch(`${BASE}${path}`, {
      method,
      headers,
      body: isForm ? body : body ? JSON.stringify(body) : undefined,
    });
  };

  let res = await doRequest(getToken());

  if (res.status === 401 && path !== "/auth/login" && path !== "/auth/refresh") {
    // Deduplicate concurrent refresh calls
    if (!_refreshing) {
      _refreshing = _refreshAccessToken().finally(() => { _refreshing = null; });
    }
    try {
      const newToken = await _refreshing;
      res = await doRequest(newToken);
    } catch {
      throw new Error("Session expired. Please log in again.");
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export const api = {
  // Auth
  register: (name, email, password) => request("POST", "/auth/register", { name, email, password }),
  login: (email, password) => request("POST", "/auth/login", { email, password }),
  me: () => request("GET", "/auth/me"),

  // Transactions
  getTransactions: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    const key = `transactions:${q}`;
    return cached(key, () => request("GET", `/transactions${q ? `?${q}` : ""}`), 30_000);
  },
  createTransaction: async (data) => {
    const res = await request("POST", "/transactions", data);
    _cacheDeletePrefix("transactions:");
    _cacheDelete("summary");
    return res;
  },
  deleteTransaction: async (id) => {
    const res = await request("DELETE", `/transactions/${id}`);
    _cacheDeletePrefix("transactions:");
    _cacheDelete("summary");
    return res;
  },
  importCSV: async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await request("POST", "/transactions/import", fd, true);
    _cacheDeletePrefix("transactions:");
    _cacheDelete("summary");
    return res;
  },
  getCategoryStats: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request("GET", `/transactions/stats/categories${q ? `?${q}` : ""}`);
  },

  // Chat
  chat: (message, conversationId = null, imageData = null, imageType = null) =>
    request("POST", "/chat", { message, conversation_id: conversationId, image_data: imageData, image_type: imageType }),

  // Streaming chat — calls onChunk(str) for each token, onDone({conversation_id, title}) at end
  chatStream: async (message, conversationId, imageData, imageType, onChunk, onDone) => {
    const token = getToken();
    const res = await fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId || null,
        image_data: imageData || null,
        image_type: imageType || null,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(err.detail || "Request failed");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const parsed = JSON.parse(line.slice(6));
          if (parsed.type === "chunk") onChunk(parsed.content);
          else if (parsed.type === "done") onDone(parsed);
          else if (parsed.type === "error") throw new Error(parsed.message);
        } catch (e) {
          if (e.message && !e.message.startsWith("JSON")) throw e;
        }
      }
    }
  },
  listConversations: () => cached("conversations", () => request("GET", "/chat/conversations"), 15_000),
  newConversation: () => request("POST", "/chat/conversations"),
  getConversation: (id) => request("GET", `/chat/conversations/${id}`),
  deleteConversation: async (id) => {
    const res = await request("DELETE", `/chat/conversations/${id}`);
    _cacheDelete("conversations");
    return res;
  },

  // Mock Bank
  getBankAccounts: () => cached("bankAccounts", () => request("GET", "/bank/accounts"), 300_000),
  getBankTransactions: (accountId, fromDate, toDate, page = 1) => {
    const q = new URLSearchParams({ account_id: accountId, page });
    if (fromDate) q.set("from_date", fromDate);
    if (toDate) q.set("to_date", toDate);
    return request("GET", `/bank/transactions?${q}`);
  },
  syncBank: (accountId, fromDate, toDate) =>
    request("POST", "/bank/sync", { account_id: accountId, from_date: fromDate, to_date: toDate }),

  // Budgets
  getBudgets: () => cached("budgets", () => request("GET", "/budgets"), 30_000),
  createBudget: async (data) => {
    const res = await request("POST", "/budgets", data);
    _cacheDelete("budgets");
    _cacheDelete("summary");
    return res;
  },
  deleteBudget: async (id) => {
    const res = await request("DELETE", `/budgets/${id}`);
    _cacheDelete("budgets");
    _cacheDelete("summary");
    return res;
  },

  // Analytics
  getSummary: () => cached("summary", () => request("GET", "/analytics/summary"), 30_000),
  getSubscriptions: () => request("GET", "/analytics/subscriptions"),
  getAnomalies: () => request("GET", "/analytics/anomalies"),
  recompute: () => request("POST", "/analytics/recompute"),

  // Cache control — call when you know data has changed and need a fresh fetch
  invalidate: (...keys) => keys.forEach((k) => k.endsWith(":") ? _cacheDeletePrefix(k) : _cacheDelete(k)),
};
