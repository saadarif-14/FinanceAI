import { useState, useEffect } from "react";
import { api } from "../api";

const CATEGORIES = [
  "All", "Groceries", "Dining", "Entertainment", "Transportation",
  "Subscriptions", "Healthcare", "Shopping", "Utilities", "Income", "Other",
];

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [category, setCategory] = useState("All");
  const [page, setPage] = useState(0);
  const limit = 50;

  const load = async () => {
    setLoading(true);
    try {
      const params = { limit, offset: page * limit };
      if (category !== "All") params.category = category;
      const data = await api.getTransactions(params);
      setTransactions(data.transactions);
      setTotal(data.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [category, page]);

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportResult(null);
    try {
      const result = await api.importCSV(file);
      setImportResult({ success: true, ...result });
      load();
    } catch (err) {
      setImportResult({ success: false, message: err.message });
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Delete this transaction?")) return;
    await api.deleteTransaction(id).catch(() => {});
    load();
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Transactions</h1>
          <p className="text-slate-400 text-sm mt-1">{total} total transactions</p>
        </div>
        <label className={`flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium px-4 py-2.5 rounded-lg cursor-pointer transition-colors ${importing ? "opacity-50 pointer-events-none" : ""}`}>
          {importing ? "Importing…" : "Import CSV"}
          <input type="file" accept=".csv" className="hidden" onChange={handleImport} disabled={importing} />
        </label>
      </div>

      {/* Import result */}
      {importResult && (
        <div className={`mb-4 rounded-xl p-4 text-sm border ${importResult.success ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-red-500/10 border-red-500/30 text-red-400"}`}>
          {importResult.success
            ? `✓ Imported ${importResult.imported} transactions (${importResult.skipped} skipped). Analytics are recomputing in the background.`
            : `✗ ${importResult.message}`}
        </div>
      )}

      {/* CSV format hint */}
      {total === 0 && (
        <div className="mb-6 bg-slate-900 border border-slate-800 rounded-xl p-5 text-sm text-slate-400">
          <p className="font-medium text-slate-300 mb-2">Expected CSV format:</p>
          <code className="block bg-slate-800 rounded-lg p-3 text-xs font-mono text-slate-300">
            date,amount,merchant,category,description<br />
            2025-01-15,-45.23,Whole Foods Market,Groceries,Weekly groceries<br />
            2025-01-16,-15.99,Netflix,Subscriptions,Monthly plan<br />
            2025-01-01,5000.00,Employer Payroll,Income,Monthly salary
          </code>
          <p className="mt-2 text-xs">Columns are auto-detected. Negative amounts = expenses. A sample file is in <code>sample_data/transactions.csv</code>.</p>
        </div>
      )}

      {/* Category filter */}
      <div className="flex gap-2 flex-wrap mb-4">
        {CATEGORIES.map((c) => (
          <button
            key={c}
            onClick={() => { setCategory(c); setPage(0); }}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${category === c ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
          >
            {c}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-400 text-sm">Loading…</div>
        ) : transactions.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">No transactions found</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="text-left text-xs text-slate-500 font-medium px-4 py-3">Date</th>
                <th className="text-left text-xs text-slate-500 font-medium px-4 py-3">Merchant</th>
                <th className="text-left text-xs text-slate-500 font-medium px-4 py-3">Category</th>
                <th className="text-right text-xs text-slate-500 font-medium px-4 py-3">Amount</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {transactions.map((t) => (
                <tr key={t.id} className="hover:bg-slate-800/50 transition-colors">
                  <td className="px-4 py-3 text-xs text-slate-400">{t.date}</td>
                  <td className="px-4 py-3 text-sm text-slate-200 max-w-[200px] truncate">{t.merchant}</td>
                  <td className="px-4 py-3">
                    <span className="inline-block text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
                      {t.category}
                    </span>
                  </td>
                  <td className={`px-4 py-3 text-sm text-right font-medium ${t.amount < 0 ? "text-red-400" : "text-emerald-400"}`}>
                    {t.amount < 0 ? "-" : "+"}${Math.abs(t.amount).toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDelete(t.id)}
                      className="text-slate-600 hover:text-red-400 text-xs transition-colors"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-xs text-slate-500">
            Showing {page * limit + 1}–{Math.min((page + 1) * limit, total)} of {total}
          </span>
          <div className="flex gap-2">
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1.5 text-xs bg-slate-800 text-slate-300 rounded-lg disabled:opacity-40 hover:bg-slate-700 transition-colors"
            >
              ← Prev
            </button>
            <button
              disabled={(page + 1) * limit >= total}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1.5 text-xs bg-slate-800 text-slate-300 rounded-lg disabled:opacity-40 hover:bg-slate-700 transition-colors"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
