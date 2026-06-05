import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../context/AuthContext";

const CATEGORY_COLORS = {
  Groceries: "#10b981",
  Dining: "#f59e0b",
  Entertainment: "#8b5cf6",
  Transportation: "#3b82f6",
  Subscriptions: "#ec4899",
  Healthcare: "#ef4444",
  Shopping: "#f97316",
  Utilities: "#6b7280",
  Income: "#22c55e",
  Other: "#64748b",
};

function StatCard({ label, value, sub, color = "indigo" }) {
  const colors = {
    indigo: "border-indigo-500/30 bg-indigo-500/5",
    emerald: "border-emerald-500/30 bg-emerald-500/5",
    amber: "border-amber-500/30 bg-amber-500/5",
    red: "border-red-500/30 bg-red-500/5",
  };
  return (
    <div className={`rounded-xl border p-5 ${colors[color] || colors.indigo}`}>
      <p className="text-sm text-slate-400">{label}</p>
      <p className="text-2xl font-bold text-slate-100 mt-1">{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}

function SpendingBar({ category, total, maxTotal }) {
  const pct = maxTotal > 0 ? (total / maxTotal) * 100 : 0;
  const color = CATEGORY_COLORS[category] || "#64748b";
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-slate-400 w-24 truncate">{category}</span>
      <div className="flex-1 bg-slate-800 rounded-full h-2">
        <div className="h-2 rounded-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs text-slate-300 w-16 text-right">${total.toFixed(0)}</span>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getSummary()
      .then(setSummary)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400 text-sm">Loading dashboard…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg p-4 text-sm">{error}</div>
      </div>
    );
  }

  const categories = summary?.current_month?.categories || [];
  const maxCat = categories.length > 0 ? categories[0].total : 1;
  const totalSpending = summary?.current_month?.total_spending || 0;
  const totalIncome = summary?.current_month?.total_income || 0;

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-100">
          Good {getGreeting()}, {user?.email?.split("@")[0]}
        </h1>
        <p className="text-slate-400 text-sm mt-1">Here's your financial overview for {currentMonth()}</p>
      </div>

      {/* No data banner */}
      {summary?.total_transactions === 0 && (
        <div className="mb-6 bg-indigo-500/10 border border-indigo-500/30 rounded-xl p-5 flex items-start gap-4">
          <span className="text-2xl">💡</span>
          <div>
            <p className="text-slate-100 font-medium">Import your transactions to get started</p>
            <p className="text-slate-400 text-sm mt-1">Upload a CSV file on the Transactions page to unlock AI-powered insights.</p>
            <Link to="/transactions" className="inline-block mt-3 text-sm bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-1.5 rounded-lg transition-colors">
              Import transactions →
            </Link>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Spent this month" value={`$${totalSpending.toFixed(0)}`} color="red" />
        <StatCard label="Income this month" value={`$${totalIncome.toFixed(0)}`} color="emerald" />
        <StatCard
          label="Subscriptions"
          value={`$${summary?.subscriptions?.monthly_cost?.toFixed(0) || 0}/mo`}
          sub={`${summary?.subscriptions?.count || 0} detected`}
          color="amber"
        />
        <StatCard
          label="Anomalies"
          value={summary?.anomalies?.count || 0}
          sub="unusual transactions"
          color={summary?.anomalies?.count > 0 ? "red" : "indigo"}
        />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Spending by category */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h2 className="text-slate-100 font-semibold mb-4">Spending by Category</h2>
          {categories.length === 0 ? (
            <p className="text-slate-500 text-sm">No expenses yet this month</p>
          ) : (
            <div className="space-y-3">
              {categories.slice(0, 8).map((c) => (
                <SpendingBar key={c.category} category={c.category} total={c.total} maxTotal={maxCat} />
              ))}
            </div>
          )}
        </div>

        {/* Recent transactions */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-slate-100 font-semibold">Recent Transactions</h2>
            <Link to="/transactions" className="text-xs text-indigo-400 hover:text-indigo-300">View all →</Link>
          </div>
          {summary?.recent_transactions?.length === 0 ? (
            <p className="text-slate-500 text-sm">No transactions yet</p>
          ) : (
            <div className="space-y-3">
              {(summary?.recent_transactions || []).map((t, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-semibold flex-shrink-0"
                    style={{ backgroundColor: `${CATEGORY_COLORS[t.category] || "#64748b"}20`, color: CATEGORY_COLORS[t.category] || "#64748b" }}
                  >
                    {t.category?.[0] || "?"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-200 truncate">{t.merchant}</p>
                    <p className="text-xs text-slate-500">{t.category} · {t.date}</p>
                  </div>
                  <span className={`text-sm font-medium ${t.amount < 0 ? "text-red-400" : "text-emerald-400"}`}>
                    {t.amount < 0 ? "-" : "+"}${Math.abs(t.amount).toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Budget alerts */}
      {summary?.budget_alerts?.length > 0 && (
        <div className="mt-6 bg-amber-500/10 border border-amber-500/30 rounded-xl p-5">
          <h2 className="text-amber-400 font-semibold mb-3">⚠ Budget Alerts</h2>
          <div className="space-y-2">
            {summary.budget_alerts.map((b, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-slate-300">{b.category}</span>
                <span className="text-amber-400">{b.percent}% used (${b.spent.toFixed(0)} / ${b.budget.toFixed(0)})</span>
              </div>
            ))}
          </div>
          <Link to="/budgets" className="inline-block mt-3 text-xs text-amber-400 hover:text-amber-300">
            Manage budgets →
          </Link>
        </div>
      )}

      {/* Quick actions */}
      <div className="mt-6 grid grid-cols-2 md:grid-cols-3 gap-3">
        <Link
          to="/chat"
          className="bg-slate-900 border border-slate-800 hover:border-indigo-500/50 rounded-xl p-4 transition-colors group"
        >
          <p className="text-lg mb-1">💬</p>
          <p className="text-sm font-medium text-slate-200 group-hover:text-indigo-400">Ask AI Assistant</p>
          <p className="text-xs text-slate-500 mt-0.5">Chat about your finances</p>
        </Link>
        <Link
          to="/transactions"
          className="bg-slate-900 border border-slate-800 hover:border-emerald-500/50 rounded-xl p-4 transition-colors group"
        >
          <p className="text-lg mb-1">📂</p>
          <p className="text-sm font-medium text-slate-200 group-hover:text-emerald-400">Import Transactions</p>
          <p className="text-xs text-slate-500 mt-0.5">Upload a CSV file</p>
        </Link>
        <Link
          to="/budgets"
          className="bg-slate-900 border border-slate-800 hover:border-amber-500/50 rounded-xl p-4 transition-colors group"
        >
          <p className="text-lg mb-1">🎯</p>
          <p className="text-sm font-medium text-slate-200 group-hover:text-amber-400">Set Budgets</p>
          <p className="text-xs text-slate-500 mt-0.5">Track spending limits</p>
        </Link>
      </div>
    </div>
  );
}

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  return "evening";
}

function currentMonth() {
  return new Date().toLocaleDateString("en-US", { month: "long", year: "numeric" });
}
