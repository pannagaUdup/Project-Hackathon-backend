from models import Product
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import csv
import os
import json
import re
from datetime import datetime, timedelta
from ptpsense_genai import (
    generate_breach_lines, BreachAnalysisResponse,
    generate_persona, PersonaResponse, TOP_N,
)

# ── Load account_features.csv once at startup ────────────────────────────────
_CSV_PATH = os.path.join(os.path.dirname(__file__), "database", "account_features.csv")
_PTP_COLUMNS = [
    ("ACCOUNT_ID",                "accountId"),
    ("CUSTOMER_ID",               "customerId"),
    ("PRODUCT_CODE",              "product"),
    ("DPD",                       "dpd"),
    ("TOTAL_OUTSTANDING_AMOUNT",  "outstanding"),
    ("DUE_DATE",                  "dueDate"),
    ("total_ptps",                "totalPtps"),
    ("ptps_fulfilled",            "ptpsFulfilled"),
    ("ptps_broken",               "ptpsBroken"),
    ("repromise_count",           "repromiseCount"),
    ("last_ptp_date",             "lastPtpDate"),
    ("last_ptp_outcome_label",    "lastPtpOutcome"),
    ("historical_fulfillment_rate", "fulfillmentRate"),
    ("risk_score",                "breachScore"),
    ("risk_tier",                 "severity"),
    ("cycler_severity",           "cyclerSeverity"),
]

def _parse(value: str):
    if value is None or value == "":
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value

def _load_account_features():
    rows = []
    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            item = {}
            for src, dst in _PTP_COLUMNS:
                item[dst] = _parse(r.get(src, ""))
            rows.append(item)
    return rows

ACCOUNT_FEATURES = _load_account_features()

# Pre-computed severity buckets (thresholds on risk_score / breachScore)
def _score(a): return a.get("breachScore") or 0

_SEVERITY_BUCKETS = {
    "all":      ACCOUNT_FEATURES,
    "critical": [a for a in ACCOUNT_FEATURES if _score(a) > 0.75],
    "high":     [a for a in ACCOUNT_FEATURES if 0.5 <= _score(a) <= 0.75],
    "low":      [a for a in ACCOUNT_FEATURES if _score(a) < 0.5],
}
_SEVERITY_COUNTS = {k: len(v) for k, v in _SEVERITY_BUCKETS.items()}

def _parse_due(s):
    if not s: return None
    try:
        return datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d")
        except ValueError:
            return None

def _due_before(account, cutoff: datetime) -> bool:
    d = _parse_due(account.get("dueDate"))
    return d is not None and d <= cutoff

# ── Last-3 activity (per-account agent call dispositions) ────────────────────
_LAST3_BY_ID = {}
_DATE_PREFIX = re.compile(r"^(\d{1,2})-\s*(.*)")

def _classify_activity(remark: str) -> str:
    r = remark.upper()
    if any(k in r for k in ("PAID", "PAYMENT", "RECEIVED", "CREDIT")):         return "payment"
    if any(k in r for k in ("PTP", "PROMIS", "WILL PAY", "COMMIT", "PLEDGE")):  return "promise"
    if any(k in r for k in ("MAINTAIN", "BALANCE", "AUTO DEBIT", "NACH")):      return "auto_debit"
    if "VISIT" in r or "RESIDEN" in r:                                           return "visit"
    if any(k in r for k in ("CALL", "SPOKE", "DISCUSS", "CONTACT")):             return "contact"
    return "other"

def _parse_last3(raw: str):
    if not raw:
        return []
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(obj, dict):
        return []
    remarks_str = obj.get("last_3_remarks", "")
    if not remarks_str:
        return []

    ptp_dates = [d.strip() for d in obj.get("last_3_ptp_date", "").split(":")]
    promised  = [d.strip() for d in obj.get("last_3_promised_date", "").split(":")]
    outstanding_raw = [v.strip() for v in obj.get("last_3_Total_Outstanding", "").split("|")]

    out = []
    for i, entry in enumerate(remarks_str.split("|")):
        text = entry.strip().rstrip("/").strip()
        if not text:
            continue
        m = _DATE_PREFIX.match(text)
        day_hint, remark = (m.group(1), m.group(2).strip()) if m else (None, text)

        total_out = None
        if i < len(outstanding_raw) and outstanding_raw[i]:
            try:
                total_out = float(outstanding_raw[i])
            except ValueError:
                pass

        out.append({
            "index":            i + 1,
            "dayHint":          day_hint,
            "remark":           remark,
            "category":         _classify_activity(remark),
            "ptpDate":          ptp_dates[i] if i < len(ptp_dates) and ptp_dates[i] else None,
            "promisedDate":     promised[i]  if i < len(promised)  and promised[i]  else None,
            "totalOutstanding": total_out,
        })
    return out

def _load_last3():
    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            parsed = _parse_last3(row.get("last_3_activity", ""))
            if parsed:
                _LAST3_BY_ID[row["ACCOUNT_ID"]] = parsed

_load_last3()

# ── Agent coaching data (coaching_agent_data.csv) ────────────────────────────
_COACHING_CSV = os.path.join(os.path.dirname(__file__), "database", "coaching_agent_data.csv")
COACHING_AGENTS = []
COACHING_AGENTS_BY_ID = {}
# Language-pattern aggregates: {tier: {"unigrams": [(word, count),...], "bigrams": [...], "total_words": N}}
LANGUAGE_PATTERNS = {}

_STOPWORDS = set("""a an and as at be been but by cm cus customer for from had has have he her him his i if
in is it its me my not of on or our she so some such that the their them then there these they this
to was we were what when which who will with would you your said says say ask asked tell told said
today tomorrow yesterday day date month week time very also being""".split())

def _tokenize(text: str):
    import re as _re
    text = _re.sub(r"[^A-Za-z ]+", " ", (text or "").lower())
    return [w for w in text.split() if len(w) >= 3 and w not in _STOPWORDS]

def _parse_agent_last3(raw: str) -> list[str]:
    """Returns just the remark strings for language analysis."""
    if not raw: return []
    try: obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError): return []
    if not isinstance(obj, dict): return []
    remarks = obj.get("last_3_remarks", "") or ""
    return [r.strip().rstrip("/").strip() for r in remarks.split("|") if r.strip()]

def _load_agents():
    from collections import Counter
    tier_tokens = {"Top Quartile": [], "Mid": [], "Bottom Quartile": []}
    tier_bigrams = {"Top Quartile": [], "Mid": [], "Bottom Quartile": []}

    with open(_COACHING_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            agent = {
                "agentId":         _parse(r.get("AGENT_ID", "")),
                "totalPtps":       _parse(r.get("total_ptps", "")),
                "fulfilled":       _parse(r.get("fulfilled", "")),
                "fulfillmentRate": _parse(r.get("fulfillment_rate", "")),
                "avgDpd":          _parse(r.get("avg_dpd", "")),
                "repromiseRate":   _parse(r.get("repromise_rate", "")),
                "visitRate":       _parse(r.get("visit_rate", "")),
                "remarksCount":    _parse(r.get("remarks_count", "")),
                "tier":            r.get("tier", "").strip() or "Mid",
                "tierInsight":     r.get("tier_insight", "").strip(),
                "recentActivities": _parse_last3(r.get("last_3_activity", "")),
            }
            COACHING_AGENTS.append(agent)
            COACHING_AGENTS_BY_ID[str(agent["agentId"])] = agent

            # Collect language tokens keyed by tier
            remarks = _parse_agent_last3(r.get("last_3_activity", ""))
            t = agent["tier"] if agent["tier"] in tier_tokens else "Mid"
            for rem in remarks:
                toks = _tokenize(rem)
                tier_tokens[t].extend(toks)
                tier_bigrams[t].extend(" ".join(pair) for pair in zip(toks, toks[1:]))

    # Rank by fulfillment_rate (desc) for leaderboard
    COACHING_AGENTS.sort(key=lambda x: (-(x["fulfillmentRate"] or 0), x["avgDpd"] or 999))

    # Pre-compute top phrases per tier (top 15 unigrams + 10 bigrams)
    for t in tier_tokens:
        c_uni = Counter(tier_tokens[t])
        c_bi  = Counter(tier_bigrams[t])
        LANGUAGE_PATTERNS[t] = {
            "unigrams":   [{"term": w, "count": c} for w, c in c_uni.most_common(15)],
            "bigrams":    [{"term": w, "count": c} for w, c in c_bi.most_common(10)],
            "totalWords": sum(c_uni.values()),
            "agentCount": sum(1 for a in COACHING_AGENTS if a["tier"] == t),
        }

_load_agents()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── existing products ────────────────────────────────────────────────────────
products = [
    Product(id=1, name="dsc", description="cscdd", price=3.4, qty=1),
    Product(id=2, name="dsc", description="cscdd", price=3.4, qty=1),
    Product(id=3, name="dsc", description="cscdd", price=3.4, qty=1),
]

@app.get("/products")
def greet():
    return products

@app.get("/get-product/{id}")
def getproduct(id: int):
    for product in products:
        if product.id == id:
            return product

@app.post("/add-product")
def createproduct(product: Product):
    products.append(product)
    return product

# ── collections dashboard data ───────────────────────────────────────────────
AGENTS = [
    {"id": 1, "name": "Rahul Desai",   "zone": "North",   "initials": "RD", "color": "#3b82f6", "allocated": 6},
    {"id": 2, "name": "Priya Nair",    "zone": "South",   "initials": "PN", "color": "#8b5cf6", "allocated": 7},
    {"id": 3, "name": "Arjun Mehta",   "zone": "East",    "initials": "AM", "color": "#f59e0b", "allocated": 5},
    {"id": 4, "name": "Sunita Rao",    "zone": "West",    "initials": "SR", "color": "#ef4444", "allocated": 6},
    {"id": 5, "name": "Vikram Singh",  "zone": "North",   "initials": "VS", "color": "#10b981", "allocated": 5},
    {"id": 6, "name": "Kavya Pillai",  "zone": "Central", "initials": "KP", "color": "#f97316", "allocated": 6},
    {"id": 7, "name": "Nikhil Patil",  "zone": "South",   "initials": "NP", "color": "#06b6d4", "allocated": 6},
    {"id": 8, "name": "Divya Sharma",  "zone": "East",    "initials": "DS", "color": "#ec4899", "allocated": 6},
    {"id": 9, "name": "Divya Sharma",  "zone": "East",    "initials": "DS", "color": "#ec4899", "allocated": 6},
]

BORROWERS = [
    {"id": 1,  "name": "Rajesh Kumar",   "dpd": 90, "amount": "₹1.2L", "zone": "North",   "addr": "Malad West",       "contact": "12 days ago", "score": 0.87},
    {"id": 2,  "name": "Meena Iyer",     "dpd": 60, "amount": "₹45K",  "zone": "South",   "addr": "Bandra East",      "contact": "5 days ago",  "score": 0.72},
    {"id": 3,  "name": "Suresh Pillai",  "dpd": 90, "amount": "₹2.1L", "zone": "East",    "addr": "Andheri East",     "contact": "21 days ago", "score": 0.91},
    {"id": 4,  "name": "Anita Shetty",   "dpd": 30, "amount": "₹32K",  "zone": "West",    "addr": "Borivali East",    "contact": "2 days ago",  "score": 0.45},
    {"id": 5,  "name": "Ravi Chandran",  "dpd": 90, "amount": "₹88K",  "zone": "North",   "addr": "Kandivali West",   "contact": "--",          "score": 0.83},
    {"id": 6,  "name": "Pooja Verma",    "dpd": 60, "amount": "₹67K",  "zone": "Central", "addr": "Dadar West",       "contact": "8 days ago",  "score": 0.68},
    {"id": 7,  "name": "Mohan Das",      "dpd": 30, "amount": "₹24K",  "zone": "South",   "addr": "Chembur",          "contact": "1 day ago",   "score": 0.38},
    {"id": 8,  "name": "Lakshmi Nair",   "dpd": 90, "amount": "₹3.4L", "zone": "East",    "addr": "Vikhroli",         "contact": "31 days ago", "score": 0.94},
    {"id": 9,  "name": "Anil Bhosale",   "dpd": 60, "amount": "₹56K",  "zone": "West",    "addr": "Dahisar",          "contact": "9 days ago",  "score": 0.61},
    {"id": 10, "name": "Geeta Singh",    "dpd": 90, "amount": "₹1.8L", "zone": "North",   "addr": "Goregaon West",    "contact": "18 days ago", "score": 0.89},
    {"id": 11, "name": "Santosh Yadav",  "dpd": 30, "amount": "₹41K",  "zone": "Central", "addr": "Worli",            "contact": "3 days ago",  "score": 0.52},
    {"id": 12, "name": "Usha Reddy",     "dpd": 60, "amount": "₹79K",  "zone": "South",   "addr": "Sion",             "contact": "11 days ago", "score": 0.74},
    {"id": 13, "name": "Deepak Joshi",   "dpd": 90, "amount": "₹1.1L", "zone": "East",    "addr": "Kurla West",       "contact": "25 days ago", "score": 0.88},
    {"id": 14, "name": "Nalini Menon",   "dpd": 30, "amount": "₹28K",  "zone": "West",    "addr": "Mira Road",        "contact": "4 days ago",  "score": 0.41},
    {"id": 15, "name": "Harish Gupta",   "dpd": 60, "amount": "₹94K",  "zone": "North",   "addr": "Jogeshwari West",  "contact": "7 days ago",  "score": 0.66},
]

MAP_NODES = {
    "1":  {"x": 180, "y": 120}, "2":  {"x": 290, "y": 380}, "3":  {"x": 420, "y": 200},
    "4":  {"x": 100, "y": 290}, "5":  {"x": 160, "y": 160}, "6":  {"x": 340, "y": 320},
    "7":  {"x": 310, "y": 430}, "8":  {"x": 480, "y": 240}, "9":  {"x": 90,  "y": 230},
    "10": {"x": 210, "y": 100}, "11": {"x": 350, "y": 290}, "12": {"x": 290, "y": 410},
    "13": {"x": 450, "y": 310}, "14": {"x": 80,  "y": 340}, "15": {"x": 200, "y": 170},
}

DEPOTS = {
    "1": {"x": 120, "y": 80},  "2": {"x": 260, "y": 450}, "3": {"x": 500, "y": 160},
    "4": {"x": 60,  "y": 200}, "5": {"x": 380, "y": 140}, "6": {"x": 320, "y": 260},
    "7": {"x": 280, "y": 480}, "8": {"x": 540, "y": 280},
}

ROUTES = {
    "1": [1, 5, 10, 15],
    "2": [2, 7, 12],
    "3": [3, 8, 13],
    "4": [4, 9, 14],
    "5": [6, 11],
    "6": [15, 1],
}

@app.get("/api/collections/overview")
def collections_overview():
    high_dpd = sum(1 for b in BORROWERS if b["dpd"] >= 90)
    return {
        "accounts": len(BORROWERS),
        "agents": len(AGENTS),
        "high_dpd": high_dpd,
        "target": "₹24L",
    }

@app.get("/api/collections/agents")
def collections_agents():
    return AGENTS

@app.get("/api/collections/borrowers")
def collections_borrowers(dpd_filter: str = "all"):
    result = BORROWERS
    if dpd_filter == "high":
        result = [b for b in BORROWERS if b["dpd"] >= 90]
    elif dpd_filter == "mid":
        result = [b for b in BORROWERS if 60 <= b["dpd"] < 90]
    elif dpd_filter == "low":
        result = [b for b in BORROWERS if 30 <= b["dpd"] < 60]
    return result

@app.post("/api/collections/dispatch")
def collections_dispatch():
    return {
        "routes": ROUTES,
        "map_nodes": MAP_NODES,
        "depots": DEPOTS,
        "savings": {
            "accounts_allocated": 47,
            "dispatch_time": "2.3s",
            "avg_route_km": 38,
            "expected_recovery": "₹18.4L",
        },
    }

# ═══════════════════════════════════════════════════════════════════
#  PTPSENSE — Collections Intelligence
# ═══════════════════════════════════════════════════════════════════

PTPSENSE_ACCOUNTS = [
    {"id": "ACC-0342", "name": "Ramesh Nair",     "product": "Personal Loan",  "dpd": 67, "amt": "1,28,500", "score": 0.88, "tier": "crit", "cyc": True,  "rp": 3, "lastPtp": "Apr 20 · ₹40K", "ptpSt": "at risk"},
    {"id": "ACC-0819", "name": "Kavitha Suresh",  "product": "Business Loan",  "dpd": 45, "amt": "3,72,000", "score": 0.83, "tier": "crit", "cyc": False, "rp": 2, "lastPtp": "Apr 22 · ₹80K", "ptpSt": "at risk"},
    {"id": "ACC-2891", "name": "Sundar Krishnan", "product": "Credit Card",    "dpd": 72, "amt": "67,300",   "score": 0.81, "tier": "crit", "cyc": True,  "rp": 5, "lastPtp": "Apr 18 · ₹20K", "ptpSt": "broken"},
    {"id": "ACC-5512", "name": "Usha Menon",      "product": "Business Loan",  "dpd": 61, "amt": "1,88,000", "score": 0.82, "tier": "crit", "cyc": True,  "rp": 3, "lastPtp": "Apr 20 · ₹60K", "ptpSt": "broken"},
    {"id": "ACC-1204", "name": "Deepak Menon",    "product": "Personal Loan",  "dpd": 58, "amt": "89,200",   "score": 0.79, "tier": "warn", "cyc": True,  "rp": 3, "lastPtp": "Apr 23 · ₹30K", "ptpSt": "at risk"},
    {"id": "ACC-0567", "name": "Anita Joshi",     "product": "Credit Card",    "dpd": 34, "amt": "42,100",   "score": 0.77, "tier": "warn", "cyc": False, "rp": 1, "lastPtp": "Apr 22 · ₹42K", "ptpSt": "active"},
    {"id": "ACC-2301", "name": "Suresh Kumar",    "product": "Personal Loan",  "dpd": 22, "amt": "61,800",   "score": 0.71, "tier": "warn", "cyc": False, "rp": 2, "lastPtp": "Apr 25 · ₹30K", "ptpSt": "active"},
    {"id": "ACC-4401", "name": "Pradeep Shetty",  "product": "Personal Loan",  "dpd": 44, "amt": "55,200",   "score": 0.74, "tier": "warn", "cyc": False, "rp": 1, "lastPtp": "Apr 21 · ₹55K", "ptpSt": "active"},
    {"id": "ACC-3344", "name": "Vikram Bose",     "product": "Personal Loan",  "dpd": 51, "amt": "74,000",   "score": 0.73, "tier": "warn", "cyc": False, "rp": 2, "lastPtp": "Apr 24 · ₹35K", "ptpSt": "active"},
    {"id": "ACC-0991", "name": "Meera Pillai",    "product": "Personal Loan",  "dpd": 15, "amt": "28,400",   "score": 0.28, "tier": "ok",   "cyc": False, "rp": 1, "lastPtp": "Apr 24 · ₹13K", "ptpSt": "active"},
    {"id": "ACC-1877", "name": "Arjun Reddy",     "product": "Business Loan",  "dpd": 29, "amt": "2,14,000", "score": 0.34, "tier": "ok",   "cyc": False, "rp": 1, "lastPtp": "Apr 26 · ₹50K", "ptpSt": "active"},
    {"id": "ACC-3312", "name": "Lakshmi Nair",    "product": "Personal Loan",  "dpd": 8,  "amt": "19,600",   "score": 0.21, "tier": "ok",   "cyc": False, "rp": 1, "lastPtp": "Apr 25 · ₹19K", "ptpSt": "active"},
]

PTPSENSE_BREACH_CARDS = [
    {
        "id": "ACC-0342", "name": "Ramesh Nair", "product": "Personal Loan", "dpd": 67,
        "amt": "₹1,28,500", "score": 0.88, "tier": "crit", "rp": 3, "cyc": True, "timer": "18h 24m",
        "signals": [
            "No payment activity in 67 days · salary credit delayed 8 days",
            "Last 6 calls unanswered · promise made Thursday evening (low quality)",
            "3rd consecutive re-promise — P2 pattern match (2.3× breach rate)",
        ],
        "sigs_good": [],
        "acts": [
            {"l": "Call Now",             "s": "btn-d", "pg": None},
            {"l": "Offer Split ₹20K+₹20K","s": "btn-g", "pg": None},
            {"l": "Flag Cycler",          "s": "btn-g", "pg": None},
            {"l": "View Rec →",           "s": "btn-g", "pg": "rec"},
        ],
    },
    {
        "id": "ACC-0819", "name": "Kavitha Suresh", "product": "Business Loan", "dpd": 45,
        "amt": "₹3,72,000", "score": 0.83, "tier": "crit", "rp": 2, "cyc": False, "timer": "31h 12m",
        "signals": [
            "PTP made on Sunday (P1 pattern — weekend promises breach at 61%)",
            "Business cashflow irregular · no UPI activity in 14 days",
        ],
        "sigs_good": [],
        "acts": [
            {"l": "Call Now",        "s": "btn-d", "pg": None},
            {"l": "Restructure Offer","s": "btn-g", "pg": None},
        ],
    },
    {
        "id": "ACC-1204", "name": "Deepak Menon", "product": "Personal Loan", "dpd": 58,
        "amt": "₹89,200", "score": 0.79, "tier": "high", "rp": 3, "cyc": True, "timer": "41h 05m",
        "signals": [
            "3rd re-promise · pressure PTP (5 calls same day — P5 pattern)",
        ],
        "sigs_good": ["Salary credit detected yesterday — call window open"],
        "acts": [
            {"l": "Call Today (salary window)", "s": "btn-warn", "pg": None},
            {"l": "Partial Ask ₹30K",           "s": "btn-g",    "pg": None},
            {"l": "View Rec →",                 "s": "btn-g",    "pg": "rec"},
        ],
    },
    {
        "id": "ACC-0567", "name": "Anita Joshi", "product": "Credit Card", "dpd": 34,
        "amt": "₹42,100", "score": 0.77, "tier": "high", "rp": 1, "cyc": False, "timer": "44h 30m",
        "signals": [
            "PTP logged after 4 calls in one day (P5 pattern — pressure promise)",
            "Weekend PTP (Saturday)",
        ],
        "sigs_good": ["First re-promise — not yet a cycler"],
        "acts": [
            {"l": "WhatsApp Payment Link", "s": "btn-warn", "pg": None},
            {"l": "Partial Ask ₹20K",      "s": "btn-g",    "pg": None},
        ],
    },
]

PTPSENSE_LIFECYCLE = [
    {
        "id": "ACC-0342", "name": "Ramesh Nair", "product": "Personal Loan", "dpd": 67,
        "amt": "₹1,28,500", "chips": ["cr|Critical", "cp|cycler"],
        "summary": "3 PTPs · 0 fulfilled", "open": True,
        "nodes": [
            {"cls": "br", "date": "Feb 18", "title": "PTP #1 — ₹40,000 promised by Mar 2",
             "detail": 'Logged after 2 call attempts. Agent note: "Borrower said salary delayed, will pay by 2nd." Monday promise — medium quality.',
             "out": "br|Broken — ₹0 received"},
            {"cls": "br", "date": "Mar 10", "title": "PTP #2 — ₹40,000 promised by Mar 22",
             "detail": 'Re-promise after PTP #1 broke. 5 contact attempts before this call. P5 pressure pattern match. Agent note: "Finally picked up, promised full amount."',
             "out": "br|Broken — ₹0 received"},
            {"cls": "ac", "date": "Apr 8",  "title": "PTP #3 — ₹40,000 promised by Apr 20  ← ACTIVE",
             "detail": "3rd consecutive re-promise. Thursday evening. Salary credit not detected. P2 + P5 pattern match. Breach probability: 0.88.",
             "out": "ac|⚠ At risk — due in 18 hours"},
        ],
        "sum": [
            {"n": "0 / 3", "l": "PTPs fulfilled",  "c": "red"},
            {"n": "₹0",    "l": "Total collected",  "c": "red"},
            {"n": "Cycler","l": "Account status",   "c": "purple"},
        ],
    },
    {
        "id": "ACC-0991", "name": "Meera Pillai", "product": "Personal Loan", "dpd": 15,
        "amt": "₹28,400", "chips": ["cg|Stable"],
        "summary": "2 PTPs · 1 fulfilled", "open": False,
        "nodes": [
            {"cls": "fu", "date": "Mar 5",  "title": "PTP #1 — ₹15,000 promised by Mar 12",
             "detail": 'Promise made Monday after 1 call. Salary-aligned date (+3 days post credit). Agent note: "Borrower cooperative, gave specific date." Low breach risk — P3 pattern.',
             "out": "fu|✓ Fulfilled — ₹15,000 received Mar 11"},
            {"cls": "mo", "date": "Apr 15", "title": "PTP #2 — ₹13,400 promised by Apr 24  ← ACTIVE",
             "detail": "Second PTP — residual balance. 1st promise fulfilled, positive signal. Salary credit expected Apr 21. Breach probability: 0.28.",
             "out": "mo|● Monitoring — breach prob. 0.28"},
        ],
        "sum": [
            {"n": "1 / 2",   "l": "PTPs fulfilled",  "c": "green"},
            {"n": "₹15,000", "l": "Total collected",  "c": "green"},
            {"n": "Active",  "l": "Account status",   "c": "blue"},
        ],
    },
    {
        "id": "ACC-2891", "name": "Sundar Krishnan", "product": "Credit Card", "dpd": 72,
        "amt": "₹67,300", "chips": ["ca|High", "cp|cycler"],
        "summary": "5 PTPs · 0 fulfilled", "open": False,
        "nodes": [
            {"cls": "br", "date": "Jan 10", "title": "PTP #1 — ₹20,000 promised by Jan 20",
             "detail": 'First promise. Seemed genuine on call. Agent note: "Committed clearly."',
             "out": "br|Broken — ₹0 received"},
            {"cls": "br", "date": "Feb 3",  "title": "PTP #2 — ₹20,000 promised by Feb 15",
             "detail": 'Re-promise. Agent note: "Said job issue resolved, will pay."',
             "out": "br|Broken — ₹0 received"},
            {"cls": "br", "date": "Feb 28", "title": "PTP #3 — ₹20,000 promised by Mar 10",
             "detail": "3rd promise. Cycler threshold crossed. No escalation taken.",
             "out": "br|Broken — ₹0 received"},
            {"cls": "br", "date": "Mar 22", "title": "PTP #4 — ₹20,000 promised by Apr 1",
             "detail": "4th re-promise. TL escalation recommended, not actioned.",
             "out": "br|Broken — ₹0 received"},
            {"cls": "br", "date": "Apr 18", "title": "PTP #5 — ₹20,000 promised by Apr 28",
             "detail": "5th re-promise. Legal notice eligibility assessment triggered. DPD 72.",
             "out": "br|Broken — ₹0 received"},
        ],
        "sum": [
            {"n": "0 / 5", "l": "PTPs fulfilled",    "c": "red"},
            {"n": "₹0",    "l": "Total collected",    "c": "red"},
            {"n": "Legal", "l": "Assess eligibility", "c": "red"},
        ],
    },
    {
        "id": "ACC-1877", "name": "Arjun Reddy", "product": "Business Loan", "dpd": 29,
        "amt": "₹2,14,000", "chips": ["cg|Stable"],
        "summary": "1 PTP · Active", "open": False,
        "nodes": [
            {"cls": "mo", "date": "Apr 17", "title": "PTP #1 — ₹50,000 promised by Apr 26  ← ACTIVE",
             "detail": "First promise. Tuesday call, 1 attempt only. Salary-aligned. Business UPI active past 3 days. Breach probability: 0.34. Low risk.",
             "out": "mo|● Monitoring — breach prob. 0.34"},
        ],
        "sum": [
            {"n": "0 / 1",   "l": "Pending",           "c": "blue"},
            {"n": "₹0",      "l": "Collected (pending)","c": "blue"},
            {"n": "Low risk","l": "Account status",     "c": "green"},
        ],
    },
]

PTPSENSE_CYCLERS = [
    {
        "id": "ACC-0342", "name": "Ramesh Nair", "product": "Personal Loan", "dpd": 67,
        "amt": "₹1,28,500", "score": 0.88, "initials": "RN", "color": "red", "cnt": 3, "open": True,
        "pills": [
            {"d": "Mar 2",  "a": "₹40K", "o": "BROKEN",  "c": "red"},
            {"d": "Mar 22", "a": "₹40K", "o": "BROKEN",  "c": "red"},
            {"d": "Apr 20", "a": "₹40K", "o": "AT RISK", "c": "amber"},
        ],
        "paid": "₹0 of ₹1,28,500", "segs": 3, "escColor": "red",
        "esc": [
            "Stop accepting full-amount PTPs — borrower is using promises to delay collections",
            "Offer settlement at 55–60% of outstanding: ₹70,675 – ₹77,100",
            "Escalate to Team Lead for supervisor-level call — agent calls not effective",
            "If no response in 7 days: assess for legal notice eligibility (DPD 67, ₹1.28L)",
        ],
    },
    {
        "id": "ACC-1204", "name": "Deepak Menon", "product": "Personal Loan", "dpd": 58,
        "amt": "₹89,200", "score": 0.79, "initials": "DM", "color": "amber", "cnt": 3, "open": False,
        "pills": [
            {"d": "Feb 28", "a": "₹30K", "o": "BROKEN",  "c": "red"},
            {"d": "Mar 25", "a": "₹30K", "o": "BROKEN",  "c": "red"},
            {"d": "Apr 23", "a": "₹30K", "o": "AT RISK", "c": "amber"},
        ],
        "paid": "₹0 of ₹89,200", "segs": 3, "escColor": "amber",
        "esc": [
            "Salary credit detected yesterday — call today, not after due date",
            "Offer partial ₹30K now + restructure remaining ₹59,200 over 3 months",
            "Do not take another full-amount promise without partial payment received first",
        ],
    },
    {
        "id": "ACC-2891", "name": "Sundar Krishnan", "product": "Credit Card", "dpd": 72,
        "amt": "₹67,300", "score": 0.81, "initials": "SK", "color": "red", "cnt": 5, "open": False,
        "pills": [
            {"d": "Jan 10", "a": "₹20K", "o": "BROKEN", "c": "red"},
            {"d": "Feb 3",  "a": "₹20K", "o": "BROKEN", "c": "red"},
            {"d": "Feb 28", "a": "₹20K", "o": "BROKEN", "c": "red"},
            {"d": "Mar 22", "a": "₹20K", "o": "BROKEN", "c": "red"},
            {"d": "Apr 18", "a": "₹20K", "o": "BROKEN", "c": "red"},
        ],
        "paid": "₹0 of ₹67,300", "segs": 5, "escColor": "red",
        "esc": [
            "Immediate legal notice assessment — DPD 72, credit card ₹67,300",
            "No further agent-level calls — escalate to Legal Officer directly",
            "Final settlement offer: 50% (₹33,650) — accept or trigger legal notice",
        ],
    },
    {
        "id": "ACC-5512", "name": "Usha Menon", "product": "Business Loan", "dpd": 61,
        "amt": "₹1,88,000", "score": 0.82, "initials": "UM", "color": "amber", "cnt": 3, "open": False,
        "pills": [
            {"d": "Mar 5",  "a": "₹60K", "o": "BROKEN", "c": "red"},
            {"d": "Mar 28", "a": "₹60K", "o": "BROKEN", "c": "red"},
            {"d": "Apr 20", "a": "₹60K", "o": "BROKEN", "c": "red"},
        ],
        "paid": "₹0 of ₹1,88,000", "segs": 3, "escColor": "amber",
        "esc": [
            "Business cashflow severely disrupted — request bank statement before next call",
            "Offer restructure: ₹20K/month for 10 months vs lump sum demand",
            "TL escalation required — 3 broken promises on high-value business loan",
        ],
    },
]

PTPSENSE_REC_ACCOUNTS = [
    {"id": "ACC-1204", "name": "Deepak Menon", "score": 0.79, "meta": "ACC-1204 · Personal Loan · DPD 58", "key": "deepak"},
    {"id": "ACC-0567", "name": "Anita Joshi",  "score": 0.77, "meta": "ACC-0567 · Credit Card · DPD 34",   "key": "anita"},
    {"id": "ACC-2301", "name": "Suresh Kumar", "score": 0.71, "meta": "ACC-2301 · Personal Loan · DPD 22", "key": "suresh"},
    {"id": "ACC-0991", "name": "Meera Pillai", "score": 0.28, "meta": "ACC-0991 · Personal Loan · DPD 15", "key": "meera"},
]

PTPSENSE_RECOMMENDATIONS = [
    {
        "key": "deepak", "accountId": "ACC-0342",
        "name": "Deepak Menon", "meta": "ACC-0342 · Personal Loan · DPD 58 · 3 re-promises",
        "score": 0.79, "col": "var(--amber)",
        "shap": [
            {"n": "3rd re-promise (P2 pattern)",        "v": 88, "neg": False, "d": "↑ risk"},
            {"n": "No payment activity 58 days",        "v": 77, "neg": False, "d": "↑ risk"},
            {"n": "Pressure PTP — 5 calls logged",      "v": 65, "neg": False, "d": "↑ risk"},
            {"n": "Salary credit detected yesterday",   "v": 70, "neg": True,  "d": "↓ risk"},
            {"n": "Partial payment exists (prior)",     "v": 30, "neg": True,  "d": "↓ risk"},
        ],
        "sim": [
            {"m": "94%", "n": "Krishnan M. (resolved)", "d": "DPD 61 · ₹91K · 3 re-promises · Personal loan", "o": "Paid ₹35K partial after salary call",      "oc": "var(--green)"},
            {"m": "88%", "n": "Pradeep S. (resolved)",  "d": "DPD 54 · ₹78K · 2 re-promises · Personal loan", "o": "Accepted restructure ₹25K×3 months",       "oc": "var(--green)"},
            {"m": "81%", "n": "Velu R. (resolved)",     "d": "DPD 62 · ₹1.1L · 3 re-promises · Personal loan","o": "TL escalation → 55% settlement",           "oc": "var(--teal)"},
        ],
        "acts": [
            {"t": "★ Call today — salary window open",              "c": "87%", "cc": "var(--green)", "r": "Salary credit arrived yesterday. Similar accounts show 2.1× higher payment rate when contacted within 48h of salary credit. Ask for partial ₹30K — do not demand full ₹89K.", "b": "Based on 847 salary-aligned contacts → 73% partial payment rate", "bc": "var(--green-s)", "bf": "var(--green)", "bd": "var(--green-b)"},
            {"t": "Offer split: ₹30K now + ₹59K restructured",     "c": "71%", "cc": "var(--amber)", "r": "Full-amount demands on 3rd re-promise accounts succeed only 22% of the time. Split offers succeed 71% on salary-aligned accounts in this DPD range.", "b": "Based on 234 split-offer outcomes in 45–65 DPD personal loans", "bc": "var(--amber-s)", "bf": "var(--amber)", "bd": "var(--amber-b)"},
            {"t": "Escalate to Team Lead if no response in 48h",    "c": "62%", "cc": "var(--sub)",   "r": "After 3 re-promises and salary-window lapse, agent-level calls have only 18% success rate. TL-level calls on similar profiles recover 41% of accounts.", "b": "Based on 312 TL escalations on 3rd re-promise accounts", "bc": "var(--bg4)", "bf": "var(--hint)", "bd": "var(--border2)"},
        ],
    },
    {
        "key": "anita", "accountId": "ACC-0567",
        "name": "Anita Joshi", "meta": "ACC-0567 · Credit Card · DPD 34 · 1 re-promise",
        "score": 0.77, "col": "var(--amber)",
        "shap": [
            {"n": "Pressure PTP — 4 calls same day",    "v": 79, "neg": False, "d": "↑ risk"},
            {"n": "Weekend promise (Saturday)",          "v": 72, "neg": False, "d": "↑ risk"},
            {"n": "DPD 34 — early stage",               "v": 60, "neg": True,  "d": "↓ risk"},
            {"n": "No prior broken PTPs",               "v": 65, "neg": True,  "d": "↓ risk"},
            {"n": "Small outstanding ₹42K",             "v": 35, "neg": True,  "d": "↓ risk"},
        ],
        "sim": [
            {"m": "91%", "n": "Rekha D. (resolved)", "d": "DPD 38 · ₹38K · Credit card · 1 re-promise", "o": "WhatsApp link — paid ₹20K same day",        "oc": "var(--green)"},
            {"m": "84%", "n": "Nalini S. (resolved)", "d": "DPD 31 · ₹44K · Credit card · 1 re-promise","o": "SMS commitment device — paid in 3 days",     "oc": "var(--green)"},
        ],
        "acts": [
            {"t": "★ Send WhatsApp payment link — low friction", "c": "78%", "cc": "var(--green)", "r": "Low DPD (34), small outstanding (₹42K), first re-promise. Similar credit card profiles pay via WhatsApp link 78% of the time within 48h without a call.", "b": "Based on 1,204 WhatsApp nudge outcomes on early DPD credit cards", "bc": "var(--green-s)", "bf": "var(--green)", "bd": "var(--green-b)"},
            {"t": "Partial ask: ₹20K now vs ₹42K full amount",   "c": "65%", "cc": "var(--amber)", "r": "P5 pattern (pressure PTP) — the full-amount promise was likely coerced. Smaller ask = higher follow-through on low-DPD accounts.", "b": "Based on 876 partial-ask outcomes in 30–45 DPD", "bc": "var(--amber-s)", "bf": "var(--amber)", "bd": "var(--amber-b)"},
        ],
    },
    {
        "key": "suresh", "accountId": "ACC-2301",
        "name": "Suresh Kumar", "meta": "ACC-2301 · Personal Loan · DPD 22 · 2 re-promises",
        "score": 0.71, "col": "var(--amber)",
        "shap": [
            {"n": "Salary credit delayed 5 days",       "v": 74, "neg": False, "d": "↑ risk"},
            {"n": "2nd re-promise",                     "v": 61, "neg": False, "d": "↑ risk"},
            {"n": "DPD only 22 — early stage",          "v": 70, "neg": True,  "d": "↓ risk"},
            {"n": "UPI activity in last 3 days",        "v": 60, "neg": True,  "d": "↓ risk"},
            {"n": "Partial payment 14 days ago",        "v": 45, "neg": True,  "d": "↓ risk"},
        ],
        "sim": [
            {"m": "89%", "n": "Balu K. (resolved)", "d": "DPD 25 · ₹58K · 2 re-promises · Salary delayed", "o": "Waited for salary, called +2 days — paid full", "oc": "var(--green)"},
        ],
        "acts": [
            {"t": "★ Wait 3 days — salary expected, then call", "c": "82%", "cc": "var(--green)", "r": "Salary credit only 5 days delayed. UPI activity shows borrower is financially active. Calling now risks a hollow 3rd promise. Call in 3 days when salary lands — 82% payment rate on similar profiles.", "b": "Based on 634 salary-timing optimised contacts", "bc": "var(--green-s)", "bf": "var(--green)", "bd": "var(--green-b)"},
            {"t": "Send SMS with specific payment date",         "c": "58%", "cc": "var(--sub)",   "r": 'Implementation intention nudge — "When your salary arrives on Apr 24, pay ₹5,000 immediately." Specific plans increase follow-through 34% vs generic reminders.', "b": "Based on 1,100 nudge A/B test outcomes", "bc": "var(--bg4)", "bf": "var(--hint)", "bd": "var(--border2)"},
        ],
    },
    {
        "key": "meera", "accountId": "ACC-0991",
        "name": "Meera Pillai", "meta": "ACC-0991 · Personal Loan · DPD 15 · 1 active PTP",
        "score": 0.28, "col": "var(--green)",
        "shap": [
            {"n": "PTP made Monday (good signal)",      "v": 60, "neg": True, "d": "↓ risk"},
            {"n": "Salary-aligned date (+2 days)",      "v": 55, "neg": True, "d": "↓ risk"},
            {"n": "Previous PTP fulfilled",             "v": 70, "neg": True, "d": "↓ risk"},
            {"n": "DPD only 15",                        "v": 80, "neg": True, "d": "↓ risk"},
            {"n": "No contact non-response",            "v": 50, "neg": True, "d": "↓ risk"},
        ],
        "sim": [
            {"m": "96%", "n": "Chandra V. (resolved)", "d": "DPD 18 · ₹31K · 1 prior fulfilled PTP", "o": "No intervention — paid on due date", "oc": "var(--green)"},
        ],
        "acts": [
            {"t": "★ No action needed — standard monitoring",        "c": "91%", "cc": "var(--green)", "r": "Breach probability 0.28. Salary-aligned PTP, prior fulfillment history, low DPD. 91% of similar accounts pay on time without any intervention. Intervening can reduce payment likelihood (over-contact effect).", "b": "Based on 2,341 low-risk accounts — intervention vs no-intervention", "bc": "var(--green-s)", "bf": "var(--green)", "bd": "var(--green-b)"},
            {"t": "Confirmation SMS 2 days before due date only",    "c": "74%", "cc": "var(--teal)", "r": "A single gentle reminder 48h before due date increases on-time payment by 12% without triggering avoidance behaviour.", "b": "Based on 1,800 reminder timing experiments", "bc": "var(--teal-s)", "bf": "var(--teal)", "bd": "var(--teal-b)"},
        ],
    },
]

class AccountLookupRequest(BaseModel):
    accountId: str

# ── PTPSense endpoints ────────────────────────────────────────────────────────

@app.get("/api/ptpsense/accounts")
def ptpsense_accounts():
    return PTPSENSE_ACCOUNTS

@app.get("/api/ptpsense/accounts-v2")
def ptpsense_accounts_paginated(
    page: int = 1,
    page_size: int = 10,
    severity: str = "all",
    due_within_48h: bool = False,
):
    if page < 1: page = 1
    if page_size < 1 or page_size > 100: page_size = 10
    bucket = _SEVERITY_BUCKETS.get(severity, _SEVERITY_BUCKETS["all"])
    if due_within_48h:
        cutoff = datetime.now() + timedelta(hours=48)
        bucket = [a for a in bucket if _due_before(a, cutoff)]
    total = len(bucket)
    start = (page - 1) * page_size
    end = start + page_size
    items = []
    for a in bucket[start:end]:
        row = dict(a)
        acts = _LAST3_BY_ID.get(str(a["accountId"]))
        row["lastActivity"] = acts[0] if acts else None
        items.append(row)
    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": (total + page_size - 1) // page_size,
        "severity": severity if severity in _SEVERITY_BUCKETS else "all",
        "dueWithin48h": due_within_48h,
        "counts": _SEVERITY_COUNTS,
    }

@app.get("/api/ptpsense/urgent-count")
def ptpsense_urgent_count():
    """Count of CRITICAL accounts whose due date is within next 48 hours (or already overdue)."""
    cutoff = datetime.now() + timedelta(hours=48)
    count = sum(1 for a in _SEVERITY_BUCKETS["critical"] if _due_before(a, cutoff))
    return {"count": count, "severity": "critical", "withinHours": 48}

@app.get("/api/ptpsense/breach-alerts")
def ptpsense_breach_alerts():
    return PTPSENSE_BREACH_CARDS

@app.get("/api/ptpsense/breach-alerts/{account_id}")
def ptpsense_breach_alert_by_account(account_id: str):
    card = next((c for c in PTPSENSE_BREACH_CARDS if c["id"] == account_id), None)
    if card is None:
        raise HTTPException(status_code=404, detail=f"No breach alert for account '{account_id}'")
    return card

@app.get("/api/ptpsense/lifecycle")
def ptpsense_lifecycle():
    return PTPSENSE_LIFECYCLE

@app.get("/api/ptpsense/lifecycle/{account_id}")
def ptpsense_lifecycle_by_account(account_id: str):
    rec = next((r for r in PTPSENSE_LIFECYCLE if r["id"] == account_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"No lifecycle data for account '{account_id}'")
    return rec

@app.get("/api/ptpsense/cyclers")
def ptpsense_cyclers():
    return PTPSENSE_CYCLERS

@app.get("/api/ptpsense/recommendations")
def ptpsense_rec_accounts():
    return PTPSENSE_REC_ACCOUNTS

@app.post("/api/ptpsense/recommendations/by-account")
def ptpsense_rec_by_account(body: AccountLookupRequest):
    rec = next((r for r in PTPSENSE_RECOMMENDATIONS if r["accountId"] == body.accountId), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"No recommendation data for '{body.accountId}'")
    return rec

@app.get("/api/ptpsense/recommendations/{key}")
def ptpsense_rec_detail(key: str):
    rec = next((r for r in PTPSENSE_RECOMMENDATIONS if r["key"] == key), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Recommendation key '{key}' not found")
    return rec

# ── GenAI breach analysis (delegates to ptpsense_genai module) ────────────────

@app.get("/api/genai/breach-analysis/{account_id}", response_model=BreachAnalysisResponse)
def genai_breach_analysis(account_id: int):
    try:
        return generate_breach_lines(account_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/genai/persona", response_model=PersonaResponse)
def genai_persona(top_n: int = TOP_N):
    return generate_persona(top_n)

@app.get("/api/genai/last-activity/{account_id}")
def genai_last_activity(account_id: str):
    activities = _LAST3_BY_ID.get(str(account_id))
    if not activities:
        raise HTTPException(status_code=404, detail=f"No recent activity for account '{account_id}'")
    return {"account_id": account_id, "count": len(activities), "activities": activities}

# ── Agent Coaching endpoints ─────────────────────────────────────────────────

@app.get("/api/coaching/agents")
def coaching_agents(page: int = 1, page_size: int = 20, tier: str = "all"):
    if page < 1: page = 1
    if page_size < 1 or page_size > 100: page_size = 20
    pool = COACHING_AGENTS if tier == "all" else [a for a in COACHING_AGENTS if a["tier"].lower() == tier.lower()]
    total = len(pool)
    start = (page - 1) * page_size
    items = [{k: v for k, v in a.items() if k not in ("tierInsight", "recentActivities")}
             for a in pool[start:start + page_size]]
    return {
        "items": items, "total": total, "page": page, "pageSize": page_size,
        "totalPages": (total + page_size - 1) // page_size,
        "summary": {
            "topQuartile":    sum(1 for a in COACHING_AGENTS if a["tier"] == "Top Quartile"),
            "mid":            sum(1 for a in COACHING_AGENTS if a["tier"] == "Mid"),
            "bottomQuartile": sum(1 for a in COACHING_AGENTS if a["tier"] == "Bottom Quartile"),
            "avgFulfillment": round(sum(a["fulfillmentRate"] or 0 for a in COACHING_AGENTS) / len(COACHING_AGENTS), 4) if COACHING_AGENTS else 0,
        },
    }

@app.get("/api/coaching/agents/{agent_id}")
def coaching_agent_detail(agent_id: str):
    a = COACHING_AGENTS_BY_ID.get(str(agent_id))
    if not a:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return a

@app.get("/api/coaching/language-patterns")
def coaching_language_patterns():
    """Returns top words/bigrams per tier, plus phrases distinctive to Top vs Bottom quartile."""
    top = LANGUAGE_PATTERNS.get("Top Quartile", {})
    bot = LANGUAGE_PATTERNS.get("Bottom Quartile", {})
    # Compute distinctive: words appearing much more in Top vs Bottom (by rate)
    def _rate_map(bucket):
        total = bucket.get("totalWords", 1) or 1
        return {u["term"]: u["count"] / total for u in bucket.get("unigrams", [])}
    top_rate, bot_rate = _rate_map(top), _rate_map(bot)
    all_terms = set(top_rate) | set(bot_rate)
    diff = []
    for term in all_terms:
        tr, br = top_rate.get(term, 0), bot_rate.get(term, 0)
        if tr + br >= 0.002:  # only count if reasonably frequent
            diff.append({"term": term, "topRate": round(tr * 1000, 2), "bottomRate": round(br * 1000, 2),
                         "delta": round((tr - br) * 1000, 2)})
    diff.sort(key=lambda x: x["delta"], reverse=True)
    return {
        "tiers": LANGUAGE_PATTERNS,
        "distinctiveTop":    diff[:8],
        "distinctiveBottom": diff[-8:][::-1],
    }

class CoachingResponse(BaseModel):
    agent_id:        str
    tier:            str
    fulfillment:     float
    recommendations: list[str]
    strengths:       list[str]
    source:          str

_coaching_cache: dict = {}

@app.get("/api/coaching/recommendations/{agent_id}", response_model=CoachingResponse)
def coaching_recommendations(agent_id: str):
    """3-point LLM-generated coaching brief for an agent (focused on bottom-quartile)."""
    a = COACHING_AGENTS_BY_ID.get(str(agent_id))
    if not a:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    if agent_id in _coaching_cache:
        return _coaching_cache[agent_id]

    payload = {
        "agent_id":         str(a["agentId"]),
        "tier":             a["tier"],
        "fulfillment_rate": a["fulfillmentRate"],
        "total_ptps":       a["totalPtps"],
        "fulfilled":        a["fulfilled"],
        "avg_dpd":          a["avgDpd"],
        "repromise_rate":   a["repromiseRate"],
        "visit_rate":       a["visitRate"],
        "tier_insight":     a["tierInsight"],
        "sample_remarks":   [r["remark"] for r in (a["recentActivities"] or [])[:3]],
        "top_quartile_top_phrases":    [u["term"] for u in LANGUAGE_PATTERNS.get("Top Quartile", {}).get("unigrams", [])[:10]],
        "bottom_quartile_top_phrases": [u["term"] for u in LANGUAGE_PATTERNS.get("Bottom Quartile", {}).get("unigrams", [])[:10]],
    }

    system = """You are a collections-agent coach. Given an agent's PTP performance metrics, tier insight, and sample call remarks, produce a structured JSON coaching brief.
STRICT RULES:
1. Output ONLY raw JSON — no markdown, no preface.
2. "recommendations" must be EXACTLY 3 strings, each max 22 words, each a concrete action the agent can take tomorrow.
3. "strengths" = 2 short strings (max 15 words each) — what this agent already does well.
4. Use plain Indian collections terms (DPD, PTP, NACH, TL escalation, salary window, settlement).
5. For Bottom Quartile agents: focus on what distinguishes Top-tier language/behaviour from theirs.
6. Never invent numbers — only cite what's in the payload.
RETURN: {"recommendations":["..","..",".."],"strengths":["..",".."]}"""

    try:
        from ptpsense_genai import call_bedrock
        raw = call_bedrock(system, "Generate the coaching brief.\n\n" + json.dumps(payload, default=str), max_tokens=500)
        recs = (raw.get("recommendations") or [])[:3]
        strengths = (raw.get("strengths") or [])[:2]
        source = "claude"
    except Exception:
        recs, strengths, source = _coaching_fallback(a), _strengths_fallback(a), "fallback"

    # Enforce exactly 3 + 2
    while len(recs) < 3: recs.append("Review top-quartile call recordings for language patterns.")
    while len(strengths) < 2: strengths.append("Engaged with account remarks regularly.")

    resp = CoachingResponse(
        agent_id=str(a["agentId"]), tier=a["tier"],
        fulfillment=a["fulfillmentRate"] or 0,
        recommendations=recs[:3], strengths=strengths[:2], source=source,
    )
    _coaching_cache[agent_id] = resp
    return resp

def _coaching_fallback(a):
    tier = a["tier"]
    fr = (a["fulfillmentRate"] or 0) * 100
    dpd = a["avgDpd"] or 0
    rep = (a["repromiseRate"] or 0) * 100
    if tier == "Bottom Quartile":
        return [
            f"Fulfillment rate is {fr:.0f}% — target +15pt by offering salary-window calls in next 10 days before issuing a new PTP.",
            f"Re-promise rate {rep:.0f}% is high — require a partial ₹ before accepting a 2nd PTP from any account.",
            "Study 3 top-quartile agents' remarks: they confirm specific dates/amounts and log outcome within 24h.",
        ]
    if tier == "Mid":
        return [
            "Shadow a top-quartile agent for 1 day — note their objection-handling phrases.",
            f"Your avg DPD {dpd:.0f} is close to cohort — push for earlier-DPD queues to lift fulfillment.",
            "Cut pressure PTPs: do not log a PTP after >3 contact attempts in a single day.",
        ]
    return [
        "Mentor 2 bottom-quartile peers weekly — share your opening and close-out scripts.",
        f"Fulfillment {fr:.0f}% is elite — request harder cohorts (higher DPD) to scale impact.",
        "Document your best 3 language patterns for the coaching library.",
    ]

def _strengths_fallback(a):
    fr = (a["fulfillmentRate"] or 0) * 100
    dpd = a["avgDpd"] or 0
    s = []
    if fr >= 80: s.append(f"Excellent fulfillment rate ({fr:.0f}%)")
    elif fr >= 50: s.append(f"Steady fulfillment ({fr:.0f}%)")
    else: s.append(f"Consistent engagement — {a['totalPtps']} PTPs logged")
    if dpd < 30: s.append(f"Works clean early-DPD accounts (avg {dpd:.0f}d)")
    elif dpd < 90: s.append(f"Handles mid-DPD range (avg {dpd:.0f}d)")
    else: s.append(f"Takes on difficult high-DPD cases (avg {dpd:.0f}d)")
    return s[:2]
