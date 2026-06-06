import { useState, useEffect } from "react";
import { api } from "../api";

const CATEGORIES = [
  "Groceries", "Dining", "Entertainment", "Transportation",
  "Subscriptions", "Healthcare", "Shopping", "Utilities", "Other",
];

function pkr(amount, decimals = 0) {
  return `Rs ${Number(amount).toLocaleString("en-PK", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

function BudgetCard({ budget, onDelete }) {
  const { category, budget: limit, spent, remaining, percent_used, period, status } = budget;

  const statusColors = {
    ok: { bar: "bg-emerald-500", text: "text-emerald-400", badge: "bg-emerald-500/10 text-emerald-400" },
    warning: { bar: "bg-amber-500", text: "text-amber-400", badge: "bg-amber-500/10 text-amber-400" },
    over: { bar: "bg-red-500", text: "text-red-400", badge: "bg-red-500/10 text-red-400" },
  };
  const colors = statusColors[status] || statusColors.ok;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-slate-100 font-medium">{category}</h3>
          <span className={`text-xs px-2 py-0.5 rounded mt-1 inline-block ${colors.badge}`}>
            {status === "over" ? "Over budget" : status === "warning" ? "Near limit" : "On track"}
          </span>
        </div>
        <button
          onClick={() => onDelete(budget.id)}
          className="text-slate-600 hover:text-red-400 text-xs transition-colors"
        >
          ✕
        </button>
      </div>

      <div className="mb-3">
        <div className="flex justify-between text-xs text-slate-400 mb-1.5">
          <span>{pkr(spent)} spent</span>
          <span>{pkr(limit)} {period}</span>
        </div>
        <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${colors.bar}`}
            style={{ width: `${Math.min(percent_used, 100)}%` }}
          />
        </div>
      </div>

      <div className="flex justify-between text-xs">
        <span className="text-slate-500">{percent_used.toFixed(0)}% used</span>
        <span className={colors.text}>
          {remaining >= 0 ? `${pkr(remaining)} left` : `${pkr(Math.abs(remaining))} over`}
        </span>
      </div>
    </div>
  );
}

export default function BudgetsPage() {
  const [budgets, setBudgets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ category: "Groceries", amount: "", period: "monthly" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    api.getBudgets()
      .then((data) => setBudgets(data.budgets || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    if (!form.amount || parseFloat(form.amount) <= 0) return setError("Enter a valid amount");
    setSaving(true);
    setError("");
    try {
      await api.createBudget({ ...form, amount: parseFloat(form.amount) });
      setShowForm(false);
      setForm({ category: "Groceries", amount: "", period: "monthly" });
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Remove this budget?")) return;
    await api.deleteBudget(id).catch(() => {});
    load();
  };

  return (
    <div className="p-8 max-w-4xl mx-auto overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Budgets</h1>
          <p className="text-slate-400 text-sm mt-1">Set spending limits by category</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium px-4 py-2.5 rounded-lg transition-colors"
        >
          + Add Budget
        </button>
      </div>

      {/* Add form */}
      {showForm && (
        <form onSubmit={handleSave} className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-6">
          <h2 className="text-slate-100 font-semibold mb-4">New Budget</h2>
          {error && (
            <div className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2">
              {error}
            </div>
          )}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Category</label>
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Amount (Rs)</label>
              <input
                type="number"
                min="1"
                step="1"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
                placeholder="50000"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Period</label>
              <select
                value={form.period}
                onChange={(e) => setForm({ ...form, period: e.target.value })}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="monthly">Monthly</option>
                <option value="weekly">Weekly</option>
              </select>
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <button
              type="submit"
              disabled={saving}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors"
            >
              {saving ? "Saving…" : "Save Budget"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="text-sm text-slate-400 hover:text-slate-200 px-4 py-2 rounded-lg">
              Cancel
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="text-center text-slate-400 text-sm py-12">Loading…</div>
      ) : budgets.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-3xl mb-3">🎯</p>
          <p className="text-slate-300 font-medium">No budgets set yet</p>
          <p className="text-slate-500 text-sm mt-1">Create a budget to track your spending by category</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {budgets.map((b) => (
            <BudgetCard key={b.id} budget={b} onDelete={handleDelete} />
          ))}
        </div>
      )}

      <div className="mt-6 bg-slate-900 border border-slate-800 rounded-xl p-4 text-sm text-slate-400">
        💡 You can also set budgets via the AI Assistant — just say "Set a Rs 30,000 monthly budget for Dining"
      </div>
    </div>
  );
}
