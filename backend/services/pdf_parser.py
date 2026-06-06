"""
PDF bank statement parser.
Strategy:
  1. Try extracting tables page-by-page (pdfplumber).
  2. If no usable table found, fall back to line-by-line text parsing with regex.
Returns a list of dicts: {date, amount, merchant, description}
"""
import re
import io
from datetime import datetime
from typing import List, Dict, Optional

import pdfplumber

# Date patterns to try
_DATE_FMTS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y",
              "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%d/%m/%y", "%d-%b-%Y"]

# Regex to find amounts like 1,234.56 or -500 or (1,200)
_AMOUNT_RE = re.compile(r"[\-\(]?\s*[\d,]+(?:\.\d{1,2})?\s*\)?")
# Date regex covers DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, "01 Jan 2025"
_DATE_RE = re.compile(
    r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{2}[\/\-]\d{2}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
    re.IGNORECASE,
)


def _parse_date(raw: str) -> Optional[datetime.date]:
    raw = raw.strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _clean_amount(raw: str) -> Optional[float]:
    """Convert '(1,234.56)' or '-1234.56' or '1,234' → float. Parentheses = negative."""
    s = raw.strip().replace(",", "").replace(" ", "")
    negative = s.startswith("(") or s.startswith("-")
    s = s.replace("(", "").replace(")", "").replace("-", "").strip()
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return None


# ── Table extraction ──────────────────────────────────────────────────────────

def _col_index(headers: List[str], keywords: List[str]) -> Optional[int]:
    for i, h in enumerate(headers):
        if h and any(k in h.lower() for k in keywords):
            return i
    return None


def _parse_table(table: List[List]) -> List[Dict]:
    if not table or len(table) < 2:
        return []

    headers = [str(c).strip().lower() if c else "" for c in table[0]]

    date_i = _col_index(headers, ["date", "txn date", "trans date", "value date"])
    desc_i = _col_index(headers, ["description", "narration", "particulars", "details",
                                   "merchant", "payee", "remarks", "reference"])
    # Separate debit/credit columns
    debit_i  = _col_index(headers, ["debit", "withdrawal", "dr", "charge", "spent"])
    credit_i = _col_index(headers, ["credit", "deposit", "cr", "inflow"])
    amount_i = _col_index(headers, ["amount", "value", "sum"]) if not (debit_i or credit_i) else None

    if date_i is None or (desc_i is None):
        return []

    results = []
    for row in table[1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        def cell(i):
            return str(row[i]).strip() if i is not None and i < len(row) and row[i] else ""

        raw_date = cell(date_i)
        parsed_date = _parse_date(raw_date)
        if not parsed_date:
            continue

        merchant = cell(desc_i)
        if not merchant or merchant.lower() in ("nan", "none"):
            continue

        # Resolve amount
        amount = None
        if debit_i is not None and cell(debit_i):
            val = _clean_amount(cell(debit_i))
            if val and val != 0:
                amount = -abs(val)  # debit = expense

        if credit_i is not None and cell(credit_i) and amount is None:
            val = _clean_amount(cell(credit_i))
            if val and val != 0:
                amount = abs(val)  # credit = income

        if amount is None and amount_i is not None and cell(amount_i):
            amount = _clean_amount(cell(amount_i))

        if amount is None or amount == 0:
            continue

        results.append({
            "date": parsed_date.isoformat(),
            "amount": round(amount, 2),
            "merchant": merchant,
            "description": merchant,
        })

    return results


# ── Text fallback ─────────────────────────────────────────────────────────────

def _parse_text_lines(text: str) -> List[Dict]:
    """Line-by-line heuristic: look for lines that have a date and an amount."""
    results = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 8:
            continue

        date_match = _DATE_RE.search(line)
        if not date_match:
            continue

        parsed_date = _parse_date(date_match.group(0))
        if not parsed_date:
            continue

        # Find all number-like tokens
        amounts = _AMOUNT_RE.findall(line)
        clean_amounts = [_clean_amount(a) for a in amounts]
        clean_amounts = [a for a in clean_amounts if a is not None and a != 0]
        if not clean_amounts:
            continue

        # Use the last numeric token as the amount (usually balance is last, amount before it)
        amount = clean_amounts[-1] if len(clean_amounts) == 1 else clean_amounts[-2]

        # Merchant = text between date and first amount token
        after_date = line[date_match.end():].strip()
        merchant_part = re.split(r"[\d,]+(?:\.\d{1,2})?", after_date)[0].strip()
        merchant = re.sub(r"[^\w\s&\-\.]", " ", merchant_part).strip()
        if not merchant:
            merchant = "Unknown"

        results.append({
            "date": parsed_date.isoformat(),
            "amount": round(amount, 2),
            "merchant": merchant[:100],
            "description": line[:200],
        })

    return results


# ── Public API ────────────────────────────────────────────────────────────────

def parse_pdf(content: bytes) -> List[Dict]:
    """
    Parse a bank-statement PDF and return a list of raw transaction dicts.
    Each dict has: date (ISO str), amount (float), merchant (str), description (str).
    """
    rows: List[Dict] = []

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            # Try all tables on this page
            for table in page.extract_tables():
                rows.extend(_parse_table(table))

            # Fallback: if no rows from tables yet, parse raw text
            if not rows:
                text = page.extract_text() or ""
                rows.extend(_parse_text_lines(text))

    # Deduplicate by (date, amount, merchant)
    seen = set()
    unique = []
    for r in rows:
        key = (r["date"], r["amount"], r["merchant"][:30])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique
