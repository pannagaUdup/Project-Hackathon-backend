from models import Product
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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

PTPSENSE_REC_DATA = {
    "deepak": {
        "name": "Deepak Menon", "meta": "ACC-1204 · Personal Loan · DPD 58 · 3 re-promises",
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
    "anita": {
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
    "suresh": {
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
    "meera": {
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
}

# ── PTPSense endpoints ────────────────────────────────────────────────────────

@app.get("/api/ptpsense/accounts")
def ptpsense_accounts():
    return PTPSENSE_ACCOUNTS

@app.get("/api/ptpsense/breach-alerts")
def ptpsense_breach_alerts():
    return PTPSENSE_BREACH_CARDS

@app.get("/api/ptpsense/lifecycle")
def ptpsense_lifecycle():
    return PTPSENSE_LIFECYCLE

@app.get("/api/ptpsense/cyclers")
def ptpsense_cyclers():
    return PTPSENSE_CYCLERS

@app.get("/api/ptpsense/recommendations")
def ptpsense_rec_accounts():
    return PTPSENSE_REC_ACCOUNTS

@app.get("/api/ptpsense/recommendations/{key}")
def ptpsense_rec_detail(key: str):
    if key not in PTPSENSE_REC_DATA:
        raise HTTPException(status_code=404, detail=f"Recommendation key '{key}' not found")
    return PTPSENSE_REC_DATA[key]
