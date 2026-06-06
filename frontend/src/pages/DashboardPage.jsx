import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../context/AuthContext";

const CATEGORY_COLORS = {
  Groceries:      "#10b981",
  Dining:         "#f59e0b",
  Entertainment:  "#8b5cf6",
  Transportation: "#3b82f6",
  Subscriptions:  "#ec4899",
  Healthcare:     "#ef4444",
  Shopping:       "#f97316",
  Utilities:      "#6b7280",
  Income:         "#22c55e",
  Other:          "#64748b",
};

function pkr(amount, decimals = 0) {
  return `Rs ${Number(amount).toLocaleString("en-PK", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function currentMonth() {
  return new Date().toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

/* ── Stat card ─────────────────────────────────────────────────────────────── */
function StatCard({ label, value, sub, accentColor, icon }) {
  return (
    <div
      className="relative overflow-hidden rounded-2xl p-5 border border-white/8"
      style={{ background: "rgba(255,255,255,0.04)", backdropFilter: "blur(20px)" }}
    >
      {/* Glow spot */}
      <div
        className="absolute -top-6 -right-6 w-24 h-24 rounded-full blur-2xl opacity-30 pointer-events-none"
        style={{ backgroundColor: accentColor }}
      />
      <div className="relative">
        <div className="flex items-center justify-between mb-4">
          <p className="text-xs font-semibold text-white/40 uppercase tracking-widest">{label}</p>
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center"
            style={{ background: `${accentColor}20` }}
          >
            <span style={{ color: accentColor }}>{icon}</span>
          </div>
        </div>
        <p className="text-2xl font-bold text-white tracking-tight">{value}</p>
        {sub && <p className="text-xs mt-1" style={{ color: `${accentColor}99` }}>{sub}</p>}
      </div>
    </div>
  );
}

/* ── Spending bar ──────────────────────────────────────────────────────────── */
function SpendingBar({ category, total, budget, maxTotal }) {
  const color = CATEGORY_COLORS[category] || "#64748b";
  const hasBudget = budget > 0;
  const pct = hasBudget
    ? Math.min((total / budget) * 100, 100)
    : maxTotal > 0 ? (total / maxTotal) * 100 : 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
          <span className="text-sm text-white/70">{category}</span>
          {hasBudget && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-white/5 text-white/40">
              {Math.round(pct)}%
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white">{pkr(total)}</span>
          {hasBudget && <span className="text-xs text-white/25">/ {pkr(budget)}</span>}
        </div>
      </div>
      <div className="w-full rounded-full h-1.5" style={{ background: "rgba(255,255,255,0.06)" }}>
        <div
          className="h-1.5 rounded-full transition-all duration-700"
          style={{ width: `${Math.max(pct, 1)}%`, backgroundColor: color, boxShadow: `0 0 8px ${color}60` }}
        />
      </div>
    </div>
  );
}

/* ── Main ──────────────────────────────────────────────────────────────────── */
export default function DashboardPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [budgetMap, setBudgetMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.getSummary(), api.getBudgets()])
      .then(([s, b]) => {
        setSummary(s);
        const map = {};
        (b.budgets || []).forEach((bud) => { map[bud.category] = bud.amount; });
        setBudgetMap(map);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-white/30 text-sm">Loading your finances…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 rounded-2xl p-4 text-sm">{error}</div>
      </div>
    );
  }

  const categories = summary?.current_month?.categories || [];
  const maxCat = categories.length > 0 ? categories[0].total : 1;
  const totalSpending = summary?.current_month?.total_spending || 0;
  const totalIncome = summary?.current_month?.total_income || 0;
  const net = totalIncome - totalSpending;
  const hasData = summary?.total_transactions > 0;

  return (
    <div className="min-h-full px-6 sm:px-8 pt-8 pb-10 max-w-6xl mx-auto">

      {/* Header */}
      <div className="mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-violet-500/20 bg-violet-500/10 mb-3">
          <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
          <span className="text-xs text-violet-300 font-medium">{currentMonth()}</span>
        </div>
        <h1 className="text-3xl font-bold text-white">
          {getGreeting()}, <span className="bg-gradient-to-r from-violet-400 to-indigo-400 bg-clip-text text-transparent">{user?.name?.split(" ")[0] || "there"}</span>
        </h1>
        <p className="text-white/30 text-sm mt-1">Here's your financial overview</p>
      </div>

      {/* No data */}
      {!hasData && (
        <div className="mb-6 rounded-2xl p-5 border border-violet-500/20 flex items-start gap-4"
          style={{ background: "rgba(139,92,246,0.07)", backdropFilter: "blur(20px)" }}>
          <div className="w-10 h-10 rounded-xl bg-violet-500/15 flex items-center justify-center flex-shrink-0">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-5 h-5 text-violet-400">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
          </div>
          <div className="flex-1">
            <p className="text-white font-semibold">Import your transactions to get started</p>
            <p className="text-white/40 text-sm mt-0.5">Sync from your bank or upload a CSV to unlock AI-powered insights.</p>
          </div>
          <Link to="/transactions" className="flex-shrink-0 text-sm bg-violet-600 hover:bg-violet-500 text-white px-4 py-2 rounded-xl transition-colors font-medium">
            Import →
          </Link>
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Spent this month"
          value={pkr(totalSpending)}
          sub={`${categories.length} categories`}
          accentColor="#f43f5e"
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6L9 12.75l4.286-4.286a11.948 11.948 0 014.306 6.43l.776 2.898m0 0l3.182-5.511m-3.182 5.51l-5.511-3.181" />
            </svg>
          }
        />
        <StatCard
          label="Income this month"
          value={pkr(totalIncome)}
          sub={totalIncome > 0 ? "Received" : "No income yet"}
          accentColor="#10b981"
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
            </svg>
          }
        />
        <StatCard
          label="Subscriptions"
          value={`${pkr(summary?.subscriptions?.monthly_cost || 0)}/mo`}
          sub={`${summary?.subscriptions?.count || 0} active`}
          accentColor="#f59e0b"
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
            </svg>
          }
        />
        <StatCard
          label="Anomalies"
          value={summary?.anomalies?.count || 0}
          sub="unusual transactions"
          accentColor={summary?.anomalies?.count > 0 ? "#f43f5e" : "#8b5cf6"}
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          }
        />
      </div>

      {/* Net balance */}
      {hasData && (
        <div className="mb-6 rounded-2xl px-6 py-5 border border-white/5 flex items-center gap-6"
          style={{ background: "rgba(255,255,255,0.03)", backdropFilter: "blur(20px)" }}>
          <div className="flex-1">
            <p className="text-xs text-white/30 uppercase tracking-widest mb-1">Net balance this month</p>
            <p className={`text-3xl font-bold tracking-tight ${net >= 0 ? "text-emerald-400" : "text-rose-400"}`}
              style={{ textShadow: net >= 0 ? "0 0 30px rgba(16,185,129,0.4)" : "0 0 30px rgba(244,63,94,0.4)" }}>
              {net >= 0 ? "+" : ""}{pkr(net)}
            </p>
          </div>
          <div className="text-xs text-white/25 text-right leading-relaxed">
            <p>{pkr(totalIncome)} income</p>
            <p>− {pkr(totalSpending)} spent</p>
          </div>
          <div
            className={`w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0`}
            style={{ background: net >= 0 ? "rgba(16,185,129,0.12)" : "rgba(244,63,94,0.12)" }}
          >
            {net >= 0 ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-5 h-5 text-emerald-400">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-5 h-5 text-rose-400">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 13.5L12 21m0 0l-7.5-7.5M12 21V3" />
              </svg>
            )}
          </div>
        </div>
      )}

      {/* Main grid */}
      <div className="grid lg:grid-cols-5 gap-5 mb-5">

        {/* Spending by category */}
        <div className="lg:col-span-3 rounded-2xl p-6 border border-white/5"
          style={{ background: "rgba(255,255,255,0.03)", backdropFilter: "blur(20px)" }}>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-base font-bold text-white">Spending by Category</h2>
              <p className="text-xs text-white/30 mt-0.5">{currentMonth()}</p>
            </div>
            {categories.length > 0 && (
              <span className="text-xs text-white/30 font-medium">{pkr(totalSpending)} total</span>
            )}
          </div>
          {categories.length === 0 ? (
            <div className="flex flex-col items-center py-10 text-center">
              <p className="text-white/20 text-sm">No expenses this month</p>
            </div>
          ) : (
            <div className="space-y-5">
              {categories.slice(0, 7).map((c) => (
                <SpendingBar
                  key={c.category}
                  category={c.category}
                  total={c.total}
                  budget={budgetMap[c.category] || 0}
                  maxTotal={maxCat}
                />
              ))}
            </div>
          )}
        </div>

        {/* Recent transactions */}
        <div className="lg:col-span-2 rounded-2xl p-6 border border-white/5"
          style={{ background: "rgba(255,255,255,0.03)", backdropFilter: "blur(20px)" }}>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-base font-bold text-white">Recent</h2>
            <Link to="/transactions" className="text-xs text-violet-400 hover:text-violet-300 transition-colors">
              View all →
            </Link>
          </div>
          {(summary?.recent_transactions || []).length === 0 ? (
            <div className="flex flex-col items-center py-10">
              <p className="text-white/20 text-sm">No transactions yet</p>
            </div>
          ) : (
            <div className="space-y-1">
              {(summary?.recent_transactions || []).map((t, i) => {
                const color = CATEGORY_COLORS[t.category] || "#64748b";
                return (
                  <div key={i} className="flex items-center gap-3 p-2.5 rounded-xl hover:bg-white/4 transition-colors group">
                    <div
                      className="w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold flex-shrink-0"
                      style={{ background: `${color}18`, color }}
                    >
                      {t.merchant?.slice(0, 2).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-white/80 font-medium truncate">{t.merchant}</p>
                      <p className="text-[11px] text-white/25">{t.category} · {t.date}</p>
                    </div>
                    <span className={`text-sm font-bold flex-shrink-0 ${t.amount < 0 ? "text-rose-400" : "text-emerald-400"}`}>
                      {t.amount < 0 ? "-" : "+"}{pkr(Math.abs(t.amount))}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Budget alerts */}
      {summary?.budget_alerts?.length > 0 && (
        <div className="mb-5 rounded-2xl p-5 border border-amber-500/15"
          style={{ background: "rgba(245,158,11,0.06)", backdropFilter: "blur(20px)" }}>
          <div className="flex items-center gap-2 mb-4">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4 text-amber-400">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z" />
            </svg>
            <h2 className="text-sm font-semibold text-amber-400">Budget Alerts</h2>
          </div>
          <div className="space-y-3">
            {summary.budget_alerts.map((b, i) => (
              <div key={i} className="flex items-center gap-4">
                <span className="text-sm text-white/70 w-28 truncate">{b.category}</span>
                <div className="flex-1 rounded-full h-1.5" style={{ background: "rgba(255,255,255,0.06)" }}>
                  <div className="h-1.5 rounded-full bg-amber-400" style={{ width: `${Math.min(b.percent, 100)}%`, boxShadow: "0 0 8px rgba(245,158,11,0.5)" }} />
                </div>
                <span className="text-xs text-amber-400 w-10 text-right">{b.percent}%</span>
              </div>
            ))}
          </div>
          <Link to="/budgets" className="inline-block mt-3 text-xs text-amber-400/50 hover:text-amber-400 transition-colors">
            Manage budgets →
          </Link>
        </div>
      )}

      {/* Quick actions */}
      <div className="grid grid-cols-3 gap-4">
        {[
          {
            to: "/chat",
            color: "#8b5cf6",
            icon: (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
            ),
            label: "Ask AI",
            sub: "Chat about finances",
          },
          {
            to: "/transactions",
            color: "#10b981",
            icon: (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
              </svg>
            ),
            label: "Import",
            sub: "CSV or bank sync",
          },
          {
            to: "/budgets",
            color: "#f59e0b",
            icon: (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            ),
            label: "Budgets",
            sub: "Track spending limits",
          },
        ].map((a) => (
          <Link
            key={a.to}
            to={a.to}
            className="group rounded-2xl p-5 border border-white/5 hover:border-white/10 transition-all duration-200"
            style={{ background: "rgba(255,255,255,0.03)", backdropFilter: "blur(20px)" }}
          >
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center mb-3 transition-transform group-hover:scale-110"
              style={{ background: `${a.color}15`, color: a.color }}
            >
              {a.icon}
            </div>
            <p className="text-sm font-semibold text-white/80 group-hover:text-white transition-colors">{a.label}</p>
            <p className="text-xs text-white/25 mt-0.5">{a.sub}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
