# Personal Finance Assistant

An AI-driven personal finance companion built for the Revonix Full Stack AI Engineer assessment.

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env: add your ANTHROPIC_API_KEY and optionally a SECRET_KEY

uvicorn main:app --reload
# → http://localhost:8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### 3. Load sample data

Go to **Transactions → Import CSV** and upload `sample_data/transactions.csv` (250+ transactions, Jan–Jun 2025).

Then ask the AI assistant anything:
- "How much did I spend on groceries in April?"
- "What are my recurring subscriptions?"
- "Am I spending more this month than usual?"
- Upload a receipt photo to record it automatically

---

## Architecture

### Stack

| Layer | Tech | Why |
|---|---|---|
| Frontend | React + Vite + Tailwind v4 | Fast dev, known stack |
| Backend | FastAPI + SQLite (SQLAlchemy) | Async, easy to run locally, swap to Postgres for prod |
| Auth | JWT (python-jose + bcrypt) | Stateless, no external service needed |
| AI | Anthropic Claude API | Tool use, vision, best reasoning |

### The Core AI Design

**Tool-based architecture** — Claude never sees raw transaction dumps. Instead it gets a set of DB-backed tools:

```
get_user_context()        → stored user preferences
get_spending_summary()    → pre-aggregated category totals (fast)
get_transactions()        → filtered raw rows, max 50 per call
get_monthly_trend()       → month-by-month spending trend
get_subscriptions()       → pre-computed recurring charges
get_anomalies()           → pre-computed statistical outliers
get_budgets()             → budgets with current spending
set_budget()              → create/update a budget
remember_user_fact()      → persist user context across sessions
lookup_merchant()         → DuckDuckGo search for unknown merchants
```

Why this matters for scale: a user with 5 years of transactions (~3,000+ rows) never sends those to the model. A "how much did I spend on groceries last month?" query becomes one SQL aggregate call returning a single number, then Claude formats the answer. The model context stays small; costs stay low.

**Conversation history** is capped at 40 messages in the DB. This bounds token costs regardless of how long users chat.

### Routing & Model Selection

Currently uses `claude-sonnet-4-6` for all queries with tool use. The architectural decision was:

1. **Tool use replaces routing**: Rather than a separate haiku classification pass, the tool definitions themselves encode what data to fetch. Claude picks the right tool automatically.
2. **Cost comes from tool results, not model choice**: Pre-computed aggregates (subscriptions, anomalies, monthly totals) are computed once on CSV import, not per-request. This is the real cost lever.
3. **Production improvement**: Add a haiku routing layer for queries that can be answered without tools (e.g. "what categories do you track?") to avoid unnecessary sonnet invocations.

### Analytics Pipeline

Runs in background after CSV import:

**Subscription detection**: Groups transactions by merchant → checks amount consistency (±15%) → checks interval regularity against [7, 14, 30, 90, 365] day patterns (±25% tolerance). Stored in DB for O(1) retrieval.

**Anomaly detection**: Builds per-category baseline (mean + std dev) from historical data (>90 days old) → flags recent transactions with z-score ≥ 2.0. Severity: high if z ≥ 3.0.

**Receipt parsing**: Passes image to Claude with vision. Handles blurry/rotated/partial images gracefully — Claude's vision is robust to poor quality. Foreign language receipts work because claude-sonnet-4-6 is multilingual.

### Data Resilience

CSV import handles:
- Multiple date formats (YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY, etc.)
- Currency symbols and parenthetical negatives: `$45.00`, `(45.00)`, `45,00`
- Flexible column naming (merchant/payee/description/vendor all detected)
- Missing categories (auto-assigned from merchant name)
- Junk/empty rows (skipped with count)
- Duplicate imports (no dedup currently — assumption: users import once; production would add a hash-based dedup)

### Scale Considerations

| Constraint | Approach |
|---|---|
| Fast responses | Pre-computed analytics; SQL aggregates over AI scans |
| Low cost per query | Tools return aggregates, not rows; 40-message history cap |
| Large data | Tool results are bounded (max 50 rows); aggregates are O(1) |
| Many users | Stateless JWT; SQLite swaps to Postgres + connection pool |
| Growing history | Anomaly baseline uses 90-day window; trend uses 6-month window |

### What Was Skipped / Simplified

- **Real bank integration**: Replaced with CSV import + mock data. Production: Plaid/MX.
- **Streaming responses**: Chat is request/response. Production: SSE for faster perceived latency.
- **haiku routing layer**: Would reduce cost ~30% for simple queries. Architecture supports it — just add a classify() call before the main tool loop.
- **Duplicate transaction detection**: Hash-based dedup would prevent reimporting the same CSV.
- **Real-time web search**: Using DuckDuckGo instant answers. Production: Brave Search API or Tavily for richer merchant data.
- **Push notifications**: Budget alerts shown on dashboard; production would add email/push.
- **Multi-currency**: Assumes USD. Architecture supports it — add currency field to Transaction model.

### Assumptions

- Negative amounts = expenses, positive = income (standard bank export convention)
- One conversation thread per user (sufficient for the use case; production might add threads)
- SQLite for local dev; designed to drop-in replace with PostgreSQL (just change DATABASE_URL)
- Users import their own CSV; no live bank connection in this version

## API Reference

```
POST /auth/register        { email, password }
POST /auth/login           { email, password }
GET  /auth/me

GET  /transactions         ?category=&start_date=&end_date=&limit=&offset=
POST /transactions          { date, amount, merchant, category, description }
POST /transactions/import  multipart/form-data file=<csv>
DELETE /transactions/{id}
GET  /transactions/stats/categories

POST /chat                 { message, image_data?, image_type? }
GET  /chat/history
DELETE /chat/history

GET  /budgets
POST /budgets              { category, amount, period }
DELETE /budgets/{id}

GET  /analytics/summary
GET  /analytics/subscriptions
GET  /analytics/anomalies
POST /analytics/recompute
```

## Challenges

**Conversation serialization**: Anthropic's SDK returns typed objects (TextBlock, ToolUseBlock) that aren't directly JSON-serializable for DB storage. Solved by normalizing to plain dicts before persistence and reconstructing on load.

**Subscription detection false positives**: Initial algorithm flagged any repeated charge as a subscription. Fixed by requiring both amount consistency AND interval regularity against standard periods, with tolerance bounds.

**Tool loop termination**: Added a max-iterations guard (6) to prevent runaway tool loops on edge cases where Claude keeps calling tools without reaching a conclusion.
