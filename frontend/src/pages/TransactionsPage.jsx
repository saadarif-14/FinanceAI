import { useState, useEffect } from "react";
import { api } from "../api";

const CATEGORIES = [
  "All", "Groceries", "Dining", "Entertainment", "Transportation",
  "Subscriptions", "Healthcare", "Shopping", "Utilities", "Income", "Other",
];

function pkr(amount) {
  return `Rs ${Number(amount).toLocaleString("en-PK", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

/* ── Bank Sync Modal ─────────────────────────────────────────────────────── */
function BankSyncModal({ onClose, onSynced }) {
  const [accounts, setAccounts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getBankAccounts().then((d) => {
      setAccounts(d.accounts || []);
      if (d.accounts?.length) setSelected(d.accounts[0].account_id);
    });
    // Default date range: 3 years ago → today
    const today = new Date();
    const threeYearsAgo = new Date(today);
    threeYearsAgo.setFullYear(today.getFullYear() - 3);
    setToDate(today.toISOString().split("T")[0]);
    setFromDate(threeYearsAgo.toISOString().split("T")[0]);
  }, []);

  const handlePreview = async () => {
    if (!selected) return;
    setLoadingPreview(true);
    setError("");
    try {
      const data = await api.getBankTransactions(selected, fromDate, toDate, 1);
      setPreview(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleSync = async () => {
    if (!selected) return;
    setSyncing(true);
    setError("");
    try {
      const data = await api.syncBank(selected, fromDate, toDate);
      setResult(data);
      onSynced();
    } catch (e) {
      setError(e.message);
    } finally {
      setSyncing(false);
    }
  };

  const selectedAccount = accounts.find((a) => a.account_id === selected);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800">
          <div>
            <h2 className="text-slate-100 font-semibold">Connect Bank Account</h2>
            <p className="text-slate-500 text-xs mt-0.5">Import your transaction history from a mock bank</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg">✕</button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {result ? (
            /* Success state */
            <div className="text-center py-4">
              <div className="w-14 h-14 bg-emerald-500/15 rounded-full flex items-center justify-center mx-auto mb-3">
                <svg className="w-7 h-7 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-slate-100 font-semibold">{result.imported} transactions imported</p>
              <p className="text-slate-400 text-sm mt-1">From {result.account}</p>
              <p className="text-slate-500 text-xs mt-0.5">{result.from_date} → {result.to_date}</p>
              <button
                onClick={onClose}
                className="mt-5 w-full bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium py-2.5 rounded-lg transition-colors"
              >
                Done
              </button>
            </div>
          ) : (
            <>
              {/* Account selector */}
              <div>
                <label className="block text-xs text-slate-400 mb-2">Select Account</label>
                <div className="space-y-2">
                  {accounts.map((a) => (
                    <label
                      key={a.account_id}
                      className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                        selected === a.account_id
                          ? "border-indigo-500/60 bg-indigo-500/10"
                          : "border-slate-800 hover:border-slate-700"
                      }`}
                    >
                      <input
                        type="radio"
                        name="account"
                        value={a.account_id}
                        checked={selected === a.account_id}
                        onChange={() => { setSelected(a.account_id); setPreview(null); }}
                        className="accent-indigo-500"
                      />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-slate-200">{a.bank_name}</p>
                        <p className="text-xs text-slate-500">{a.account_type} · {a.account_number}</p>
                      </div>
                      <span className="text-xs text-emerald-400 font-medium">{pkr(a.balance)}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Date range */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1.5">From Date</label>
                  <input
                    type="date"
                    value={fromDate}
                    onChange={(e) => { setFromDate(e.target.value); setPreview(null); }}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1.5">To Date</label>
                  <input
                    type="date"
                    value={toDate}
                    onChange={(e) => { setToDate(e.target.value); setPreview(null); }}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              {/* Preview result */}
              {preview && (
                <div className="bg-slate-800/60 rounded-xl p-4 border border-slate-700">
                  <p className="text-slate-300 text-sm font-medium">Preview</p>
                  <p className="text-slate-400 text-xs mt-1">
                    <span className="text-indigo-400 font-semibold text-base">{preview.total}</span> transactions
                    found from <span className="text-slate-300">{preview.from_date}</span> to <span className="text-slate-300">{preview.to_date}</span>
                  </p>
                  {preview.transactions.slice(0, 3).map((t, i) => (
                    <div key={i} className="flex justify-between text-xs text-slate-500 mt-1.5">
                      <span>{t.date} · {t.merchant}</span>
                      <span className={t.amount < 0 ? "text-red-400" : "text-emerald-400"}>
                        {t.amount < 0 ? "-" : "+"}{pkr(Math.abs(t.amount))}
                      </span>
                    </div>
                  ))}
                  {preview.total > 3 && (
                    <p className="text-xs text-slate-600 mt-1">…and {preview.total - 3} more</p>
                  )}
                </div>
              )}

              {error && (
                <p className="text-red-400 text-sm bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2">{error}</p>
              )}

              {/* Actions */}
              <div className="flex gap-3">
                {!preview ? (
                  <button
                    onClick={handlePreview}
                    disabled={loadingPreview || !selected}
                    className="flex-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 text-sm font-medium py-2.5 rounded-lg transition-colors"
                  >
                    {loadingPreview ? "Loading preview…" : "Preview Transactions"}
                  </button>
                ) : (
                  <>
                    <button
                      onClick={() => setPreview(null)}
                      className="px-4 py-2.5 text-sm text-slate-400 hover:text-slate-200 rounded-lg transition-colors"
                    >
                      Back
                    </button>
                    <button
                      onClick={handleSync}
                      disabled={syncing}
                      className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium py-2.5 rounded-lg transition-colors"
                    >
                      {syncing ? `Importing ${preview.total} transactions…` : `Import ${preview.total} Transactions`}
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Main Page ───────────────────────────────────────────────────────────── */
export default function TransactionsPage() {
  const [transactions, setTransactions] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [category, setCategory] = useState("All");
  const [page, setPage] = useState(0);
  const [showBankModal, setShowBankModal] = useState(false);
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
    <div className="p-8 max-w-5xl mx-auto overflow-y-auto">
      {showBankModal && (
        <BankSyncModal
          onClose={() => setShowBankModal(false)}
          onSynced={() => { setShowBankModal(false); load(); }}
        />
      )}

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Transactions</h1>
          <p className="text-slate-400 text-sm mt-1">{total} total transactions</p>
        </div>
        <div className="flex gap-2">
          {/* Bank sync button */}
          <button
            onClick={() => setShowBankModal(true)}
            className="flex items-center gap-2 bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2.5 rounded-lg transition-colors"
          >
            🏦 Sync from Bank
          </button>
          {/* CSV import */}
          <label className={`flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium px-4 py-2.5 rounded-lg cursor-pointer transition-colors ${importing ? "opacity-50 pointer-events-none" : ""}`}>
            {importing ? "Importing…" : "Import CSV"}
            <input type="file" accept=".csv" className="hidden" onChange={handleImport} disabled={importing} />
          </label>
        </div>
      </div>

      {/* Import result */}
      {importResult && (
        <div className="mb-4 space-y-2">
          <div className={`rounded-xl p-4 text-sm border ${importResult.success ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-red-500/10 border-red-500/30 text-red-400"}`}>
            {importResult.success
              ? `✓ Imported ${importResult.imported} transactions${importResult.duplicates > 0 ? `, ${importResult.duplicates} duplicates skipped` : ""}${importResult.skipped > 0 ? `, ${importResult.skipped} invalid rows skipped` : ""}. Analytics recomputing in background.`
              : `✗ ${importResult.message}`}
          </div>
          {importResult.success && importResult.conflicts?.length > 0 && (
            <div className="rounded-xl p-4 text-sm border bg-amber-500/10 border-amber-500/30 text-amber-400">
              <p className="font-semibold mb-2">⚠ {importResult.conflicts.length} possible conflict{importResult.conflicts.length > 1 ? "s" : ""} detected</p>
              <p className="text-amber-400/70 text-xs mb-3">These CSV rows look like transactions you already entered manually. Review and delete the duplicate.</p>
              <div className="space-y-2">
                {importResult.conflicts.map((c, i) => (
                  <div key={i} className="rounded-lg p-3 bg-amber-500/5 border border-amber-500/15 text-xs space-y-1">
                    <div className="flex justify-between">
                      <span className="text-amber-300/80 font-medium">{c.imported.merchant}</span>
                      <span className="text-amber-400/60">{c.date_difference_days === 0 ? "same day" : `${c.date_difference_days}d apart`}</span>
                    </div>
                    <div className="flex gap-4 text-amber-400/60">
                      <span>{c.existing.source}: Rs {Math.abs(c.existing.amount).toLocaleString()} on {c.existing.date}</span>
                      <span>CSV: Rs {Math.abs(c.imported.amount).toLocaleString()} on {c.imported.date}</span>
                    </div>
                    {c.amount_difference > 0 && (
                      <span className="text-amber-400/50">Amount differs by Rs {c.amount_difference.toLocaleString()}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
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
                <th className="text-left text-xs text-slate-500 font-medium px-4 py-3">Source</th>
                <th className="text-right text-xs text-slate-500 font-medium px-4 py-3">Amount</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {transactions.map((t) => (
                <tr key={t.id} className="hover:bg-slate-800/50 transition-colors">
                  <td className="px-4 py-3 text-xs text-slate-400">{t.date}</td>
                  <td className="px-4 py-3 text-sm text-slate-200 max-w-[180px] truncate">{t.merchant}</td>
                  <td className="px-4 py-3">
                    <span className="inline-block text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
                      {t.category}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block text-xs px-2 py-0.5 rounded ${
                      t.source === "bank"
                        ? "bg-emerald-500/10 text-emerald-400"
                        : t.source === "csv"
                        ? "bg-indigo-500/10 text-indigo-400"
                        : "bg-slate-800 text-slate-500"
                    }`}>
                      {t.source}
                    </span>
                  </td>
                  <td className={`px-4 py-3 text-sm text-right font-medium ${t.amount < 0 ? "text-red-400" : "text-emerald-400"}`}>
                    {t.amount < 0 ? "-" : "+"}{pkr(Math.abs(t.amount))}
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
