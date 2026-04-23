from models import Product
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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
    {"id": 9, "name": "Divya Sharma",  "zone": "East",    "initials": "DS", "color": "#ec4899", "allocated": 6}
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
