# Personal Finance Assistant

A full-stack AI-powered personal finance application built with **React + Vite** (frontend) and **FastAPI** (backend), using **Supabase** for auth and data storage, **OpenAI GPT-4o-mini** for the AI assistant, and **Redis** for caching and rate limiting.

---

## Features Covered

### 1. Authentication
- JWT-based register and login via Supabase Auth
- Refresh token flow — access tokens auto-refresh silently on 401; users stay logged in until they explicitly log out
- Refresh token stored in `localStorage`; concurrent refresh calls deduplicated with a shared Promise

### 2. Transaction Management
- Manual transaction entry (date, amount, merchant, category)
- CSV import with robust parsing:
  - Fuzzy column detection — recognises `merchant`, `payee`, `description`, `vendor`, etc.
  - Multiple date format support: `YYYY-MM-DD`, `MM/DD/YYYY`, `DD/MM/YYYY`, `MM-DD-YYYY`, `YYYY/MM/DD`
  - Strips `Rs`, `$`, commas, and parenthetical negatives from amounts
  - Skips zero-amount rows, blank merchants, and unparseable dates
  - Reports `imported`, `skipped`, and `duplicates` counts to the user
- **Duplicate detection** — builds a `(date, amount, merchant_lower)` fingerprint set from existing transactions in the same date range; skips exact matches and prevents within-batch duplicates
- **Conflict detection** — flags rows that appear to be the same purchase from two different sources (same merchant substring, within ±2 days, within ±15% amount, different `source` field); shown as a warning in the UI
- Delete transactions with immediate cache invalidation
- Category filter and pagination

### 3. Budget Management
- Create, view, and delete budgets per category (monthly or weekly)
- Real-time spending vs budget displayed as progress bars
- Coloured portion = amount spent; dark track = remaining budget
- Dashboard alerts when spending exceeds 85% of the limit

### 4. Analytics Engine
- **Subscription detection** — groups transactions by merchant; requires amount consistency (±15%) and interval regularity (±25% of standard periods: 7/14/30/90/365 days); results stored in `subscriptions` table
- **Anomaly detection** — Z-score analysis (≥2.0 = medium, ≥3.0 = high) against 90-day historical baseline per category; results stored in `anomalies` table
- Both run as background tasks after every CSV import — pre-computed results mean dashboard reads are O(1) regardless of transaction volume

### 5. AI Financial Assistant
- Powered by **GPT-4o-mini** with native tool calling
- **Streaming responses via SSE** — user sees the first token within ~1 second of tool execution completing
- Auto-generated conversation titles (3–6 words) via GPT-4o-mini on first message
- Tool suite:

| Tool | Purpose |
|---|---|
| `get_user_context` | Load persisted user preferences (always called first) |
| `remember_user_fact` | Save preferences across sessions (pay day, exclusions, goals) |
| `create_transaction` | Save a transaction from chat or confirmed receipt |
| `get_spending_summary` | Aggregate spend by category for a date range |
| `get_transactions` | Filtered transaction lookup (capped at 50) |
| `get_monthly_trend` | Month-by-month spending for trend analysis |
| `get_subscriptions` | List detected recurring charges with annual cost |
| `get_anomalies` | Surface statistically unusual transactions |
| `get_budgets` | Budget vs actual with status (ok / warning / over) |
| `set_budget` | Create or update a budget from chat |
| `lookup_merchant` | DuckDuckGo web lookup for unknown merchant names |
| `get_conflicts` | Detect contradicting records across sources |

- Receipt image analysis — flags unreadable fields with `(?)` rather than guessing; never invents an amount it cannot read
- Cross-session memory via `user_context` table (key-value per user)
- Chat history trimmed to 40 messages to bound token cost
- Tool loop capped at 6 iterations

### 6. Dashboard
- Monthly spending, income, and net balance
- Spending by category with budget-aware progress bars
- Recent transactions, subscription monthly cost, anomaly count, budget alerts

### 7. Performance & Reliability

**Two-layer caching:**

| Endpoint | Client TTL | Server TTL |
|---|---|---|
| `getSummary` | 30s | 60s (Redis) |
| `getBudgets` | 30s | — |
| `getTransactions` | 30s per params key | — |
| `listConversations` | 15s | — |
| `getBankAccounts` | 5 min | — |

Every write operation explicitly deletes affected cache keys — TTLs are a safety net, not the primary freshness mechanism.

**Rate limiting:** AI endpoint limited to 30 requests per 60-second sliding window per user using a Redis sorted-set. Falls back to in-memory if Redis is unavailable.

**Other:** Fresh Supabase client per request eliminates stale HTTP/2 connection errors. N+1 budget query replaced with a single `IN` query.

---

## Key Architectural Decisions

### GPT-4o-mini for all turns
Handles tool calling and finance Q&A well at ~15× lower cost than GPT-4o. Title generation also uses mini.

### Tool-based AI over raw data dumps
The AI never receives a raw transaction dump. Every data access goes through a tool running a bounded DB query. A user with five years of transactions asking "how much did I spend on groceries last month?" results in one SQL aggregate call — not thousands of rows sent to the model.

### Streaming SSE for perceived speed
Tool call deltas are accumulated per index in a `tool_calls_map` dict, executed synchronously, then the final answer is streamed token by token to the frontend via `text/event-stream`. Content appears as it is generated rather than after the full response completes.

### Pre-computed analytics
Subscription and anomaly detection run once as background tasks after each import and are stored in dedicated tables. Dashboard reads are constant time regardless of how many transactions exist.

### Two-layer cache with explicit invalidation
Every write explicitly deletes affected cache keys on both client and server. This means: add a transaction → summary cache cleared immediately → next dashboard load is always fresh.

### Fresh Supabase client per request
Supabase closes idle HTTP/2 connections. A singleton held the dead connection and reused it, causing `Server disconnected` errors. A fresh client per request avoids this entirely. `create_client()` is lightweight and opens no connections eagerly.

---

## Assumptions & Trade-offs

| Decision | Trade-off |
|---|---|
| GPT-4o-mini for all turns | Trades occasional reasoning depth for 15× cost reduction |
| Fresh Supabase client per request | Eliminates stale connection errors at negligible overhead |
| In-process fallback when Redis is down | Single-process correctness only; app stays functional without Redis |
| Client cache TTL of 30s | Explicit write-invalidation prevents stale reads; TTL is a safety net |
| Subscription detection requires ≥2 occurrences | Avoids false positives; may miss cancelled-after-one-charge subscriptions |
| Anomaly detection requires ≥3 historical transactions | Z-score meaningless with fewer data points; sparse categories silently skipped |
| PKR only | System prompt, keywords, and amount thresholds tuned for Pakistani Rupees |
| Conflict detection uses substring match | Catches "KFC" vs "KFC Gulberg"; may false-positive on merchants sharing a common word |

---

## What Was Intentionally Skipped or Simplified

- **Multi-worker cache invalidation** — client-side cache is per-browser-tab; Redis invalidation works across workers, in-memory fallback does not
- **AI tool result pagination** — `get_transactions` capped at 50; AI sees only the most recent 50 for large filtered sets
- **Real bank integration** — mock data only; production would require Plaid/Teller OAuth
- **Push notifications** — anomalies and budget breaches shown on dashboard only; no email or push
- **Redis authentication** — `requirepass` disabled for local dev; must be enabled for production
- **Automated test suite** — no unit or integration tests; all verification was manual
- **Multi-currency support** — hardcoded to PKR; requires preference storage and system prompt threading

---

## Challenges & How They Were Handled

**`httpx.RemoteProtocolError: Server disconnected`**
Supabase closes idle HTTP/2 connections. The singleton client reused dead connections on the next request. Fixed by removing the singleton — fresh client per request.

**Streaming with tool call deltas**
OpenAI sends tool call data fragmented across chunks: `id` only in the first chunk, `function.name` and `function.arguments` accumulating across subsequent chunks. Solved by accumulating per tool call index in a `tool_calls_map` dict before executing. Content tokens are yielded directly to the SSE response; tool execution rounds yield nothing.

**Spending bar showing 100% when no budget set**
Top category always appeared full because it was used as the 100% denominator. Fixed: if a budget exists use `spent/budget`; if not use `spent/totalSpend` for a proportional view.

**N+1 query on dashboard summary**
One DB query per budget category to calculate current-month spending. Replaced with a single `.in_("category", budget_cats)` query and Python-side aggregation.

**Duplicate detection across re-imports**
Fingerprint set built from existing transactions before inserting. Each accepted row also added to the set to prevent within-batch duplicates.

**Conflict detection false positives**
Tightened to: merchant must be a substring of the other (not word overlap), amount within ±15%, date within ±2 days, sources must differ. Only flags CSV-vs-manual or CSV-vs-bank to avoid noise from split transactions.

---

## Local Setup

### Prerequisites
- Python 3.10+, Node.js 18+, Redis, Supabase project, OpenAI API key

### Backend
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# .env needs: SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY, REDIS_URL
uvicorn main:app --reload --port 8080
```

### Frontend
```bash
cd frontend
npm install
npm run dev   # → http://localhost:5173
```

### Redis
```bash
sudo systemctl start redis-server
redis-cli ping   # → PONG
```

### Docker (full stack)
```bash
cd backend
docker-compose up -d
```

---

## Project Structure

```
task-home/
├── backend/
│   ├── main.py                     # FastAPI app, CORS, routers
│   ├── database.py                 # Fresh Supabase client per request
│   ├── auth_utils.py               # JWT verification via Supabase
│   ├── limiter.py                  # Redis rate limiter + TTL cache with in-memory fallback
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── redis/
│   │   ├── Dockerfile
│   │   └── redis.conf              # 128 MB maxmemory, LRU eviction, RDB persistence
│   ├── routers/
│   │   ├── auth.py                 # Register, login, refresh token
│   │   ├── transactions.py         # CRUD, CSV import, duplicate + conflict detection
│   │   ├── budgets.py              # Budget CRUD
│   │   ├── analytics.py            # Summary (Redis-cached), subscriptions, anomalies
│   │   ├── chat.py                 # Conversation CRUD, streaming SSE endpoint
│   │   └── bank.py                 # Mock bank sync
│   └── services/
│       ├── ai_service.py           # GPT-4o-mini streaming tool loop, title generation
│       ├── finance_tools.py        # All AI tool definitions and handlers
│       └── analytics_service.py    # Subscription + anomaly detection algorithms
└── frontend/
    └── src/
        ├── api.js                  # All API calls, client-side cache, token refresh
        ├── App.jsx                 # Router, protected layout, ambient blobs
        ├── context/AuthContext.jsx
        ├── components/Sidebar.jsx
        └── pages/
            ├── DashboardPage.jsx
            ├── ChatPage.jsx        # SSE streaming consumer, mobile-responsive
            ├── TransactionsPage.jsx
            └── BudgetsPage.jsx
```
