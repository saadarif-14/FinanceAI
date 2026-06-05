const BASE = "/api";

function getToken() {
  return localStorage.getItem("fa_token");
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(method, path, body, isForm = false) {
  const headers = { ...authHeaders() };
  if (!isForm && body) headers["Content-Type"] = "application/json";

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export const api = {
  // Auth
  register: (email, password) => request("POST", "/auth/register", { email, password }),
  login: (email, password) => request("POST", "/auth/login", { email, password }),
  me: () => request("GET", "/auth/me"),

  // Transactions
  getTransactions: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request("GET", `/transactions${q ? `?${q}` : ""}`);
  },
  createTransaction: (data) => request("POST", "/transactions", data),
  deleteTransaction: (id) => request("DELETE", `/transactions/${id}`),
  importCSV: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request("POST", "/transactions/import", fd, true);
  },
  getCategoryStats: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request("GET", `/transactions/stats/categories${q ? `?${q}` : ""}`);
  },

  // Chat
  chat: (message, imageData = null, imageType = null) =>
    request("POST", "/chat", { message, image_data: imageData, image_type: imageType }),
  getChatHistory: () => request("GET", "/chat/history"),
  clearChatHistory: () => request("DELETE", "/chat/history"),

  // Budgets
  getBudgets: () => request("GET", "/budgets"),
  createBudget: (data) => request("POST", "/budgets", data),
  deleteBudget: (id) => request("DELETE", `/budgets/${id}`),

  // Analytics
  getSummary: () => request("GET", "/analytics/summary"),
  getSubscriptions: () => request("GET", "/analytics/subscriptions"),
  getAnomalies: () => request("GET", "/analytics/anomalies"),
  recompute: () => request("POST", "/analytics/recompute"),
};
