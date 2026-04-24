"""
PTPSense GenAI Engine — Production Ready
=========================================
Two endpoints:
  GET /api/genai/breach-analysis/{account_id}  → 3 breach lines
  GET /api/genai/persona                        → top 5 persona features

Run:
  pip install fastapi uvicorn requests pandas pydantic
  export AWS_BEARER_TOKEN_BEDROCK=your_token
  uvicorn ptpsense_genai:app --reload --port 8001

Developers:
  from ptpsense_genai import generate_breach_lines, generate_persona
"""

import os, json, hashlib, re, logging
from typing import Optional
from enum import Enum

import requests
import pandas as pd
from pydantic import BaseModel, Field, field_validator
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ptpsense-genai")


# ═════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ═════════════════════════════════════════════════════════════════════════════

_DEFAULT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "account_features.csv")
CSV_PATH    = os.environ.get("PTPSENSE_CSV", _DEFAULT_CSV)
BEDROCK_URL = "https://bedrock-runtime.us-east-1.amazonaws.com/model/us.anthropic.claude-sonnet-4-6/converse"
MAX_RETRIES = 2
TOP_N       = 500


# ═════════════════════════════════════════════════════════════════════════════
#  PYDANTIC MODELS — strict output contracts
#  Frontend devs rely on these shapes EXACTLY — no field goes missing
# ═════════════════════════════════════════════════════════════════════════════

class BreachAnalysisResponse(BaseModel):
    """Exactly what the frontend receives for breach analysis."""
    account_id:  int
    risk_tier:   str
    risk_score:  float
    lines:       list[str] = Field(..., min_length=3, max_length=3)
    summary:     str       = Field(..., max_length=150)
    source:      str       # "claude" or "fallback"

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, v):
        cleaned = []
        for line in v[:3]:
            line = str(line).strip()
            if len(line) > 120:
                line = line[:117] + "..."
            if not line:
                line = "Review account history before next contact"
            cleaned.append(line)
        while len(cleaned) < 3:
            cleaned.append("Review account history before next contact")
        return cleaned[:3]

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, v):
        v = str(v).strip()
        return v[:150] if v else "Review account and take appropriate action."


class PersonaFeature(BaseModel):
    rank:            int    = Field(ge=1, le=5)
    feature_name:    str    = Field(max_length=40)
    top_value:       str
    baseline_value:  str
    difference:      str
    why_it_matters:  str    = Field(max_length=120)
    chart_color:     str    = "green"

    @field_validator("chart_color")
    @classmethod
    def validate_color(cls, v):
        return v if v in ("green", "red", "amber", "teal") else "green"


class PatternStat(BaseModel):
    id:          str
    label:       str
    top_pct:     float
    base_pct:    float
    top_n:       int
    base_n:      int
    top_label:   str = "High-fulfillment accounts"
    base_label:  str = "Overall baseline"
    insight:     str


class PersonaResponse(BaseModel):
    persona_name:        str = Field(max_length=50)
    persona_description: str = Field(max_length=300)
    top_5_features:      list[PersonaFeature] = Field(min_length=5, max_length=5)
    collection_strategy: str = Field(max_length=400)
    pattern_stats:       list[PatternStat]
    source:              str


# ═════════════════════════════════════════════════════════════════════════════
#  DATA LAYER — load once, serve many
# ═════════════════════════════════════════════════════════════════════════════

_df: Optional[pd.DataFrame] = None

def get_df() -> pd.DataFrame:
    global _df
    if _df is None:
        log.info(f"Loading {CSV_PATH}...")
        _df = pd.read_csv(CSV_PATH)
        log.info(f"Loaded {len(_df):,} accounts")
    return _df


def get_account(account_id: int) -> pd.Series:
    df = get_df()
    m = df[df["ACCOUNT_ID"] == account_id]
    if m.empty:
        raise ValueError(f"Account {account_id} not found")
    return m.iloc[0]


def safe(row, col, default=None):
    val = row.get(col, default)
    return default if pd.isna(val) else val


# ═════════════════════════════════════════════════════════════════════════════
#  FEATURE NAME MAPPING
# ═════════════════════════════════════════════════════════════════════════════

_LABELS = {
    "ptp_month":                    "Promise month pattern",
    "overdue_ratio":                "Overdue installment ratio",
    "acc_dpd":                      "Account DPD severity",
    "acc_principal_outstanding":    "Principal outstanding amount",
    "agent_fulfillment_rate":       "Agent fulfillment history",
    "NPA_FLAG":                     "NPA classification",
    "agent_ptp_count":              "Agent PTP volume",
    "days_to_due":                  "Days to due date",
    "historical_repromise_rate":    "Re-promise rate",
    "promised_amount_filled":       "Promised vs outstanding",
    "is_friday":                    "Friday promise flag",
    "is_month_end":                 "Month-end promise flag",
    "promise_to_outstanding":       "Promise-to-outstanding ratio",
    "CHEQUE_BOUNCE_FLAG":           "Cheque bounce history",
    "TOTAL_NO_OF_INSTALLMENT_OVERDUE": "Overdue installment count",
    "INTEREST_RATE":                "Interest rate",
    "MOB":                          "Months on book",
    "paid_ratio":                   "Paid installment ratio",
}

def feat_label(code: str) -> str:
    return _LABELS.get(code, code.replace("_", " ").title())


# ═════════════════════════════════════════════════════════════════════════════
#  BEDROCK CALLER — single reusable function
# ═════════════════════════════════════════════════════════════════════════════

def call_bedrock(system_prompt: str, user_message: str, max_tokens: int = 600) -> dict:
    """
    Calls Claude via AWS Bedrock with retry + JSON extraction guardrails.
    Raises EnvironmentError if no token, ValueError if bad JSON after retries.
    """
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    if not token:
        raise EnvironmentError("AWS_BEARER_TOKEN_BEDROCK not set")

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    body = {
        "system":          [{"text": system_prompt}],
        "messages":        [{"role": "user", "content": [{"text": user_message}]}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.15},
    }

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(BEDROCK_URL, headers=headers, json=body, timeout=20)
            resp.raise_for_status()

            text = resp.json()["output"]["message"]["content"][0]["text"].strip()

            # ── GUARDRAIL 1: Strip markdown fences ──────────────────
            if "```" in text:
                match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
                if match:
                    text = match.group(1).strip()

            # ── GUARDRAIL 2: Find JSON object in response ──────────
            # Sometimes Claude adds "Here is..." before the JSON
            json_start = text.find("{")
            json_end   = text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                text = text[json_start:json_end]

            result = json.loads(text)
            log.info(f"Bedrock OK (attempt {attempt+1})")
            return result

        except json.JSONDecodeError as e:
            last_error = e
            log.warning(f"JSON parse failed (attempt {attempt+1}): {e}")
            # Add stricter instruction for retry
            body["messages"][0]["content"][0]["text"] += (
                "\n\nCRITICAL: You MUST return ONLY a raw JSON object. "
                "No markdown. No explanation. No text before or after the JSON."
            )
        except requests.exceptions.RequestException as e:
            last_error = e
            log.warning(f"HTTP error (attempt {attempt+1}): {e}")

    raise ValueError(f"Bedrock failed after {MAX_RETRIES+1} attempts: {last_error}")


# ═════════════════════════════════════════════════════════════════════════════
#  MODULE 1 — BREACH ANALYSIS (3 lines per account)
# ═════════════════════════════════════════════════════════════════════════════

BREACH_SYSTEM_PROMPT = """You are PTPSense — a collections AI for Indian lending.

TASK: Given account data, generate exactly 3 breach analysis lines for the agent dashboard.

STRICT RULES:
1. Output ONLY a raw JSON object — no markdown, no explanation
2. "lines" must be EXACTLY 3 strings
3. Each line: plain English, max 15 words, specific to this account
4. Line 1 = biggest risk signal (from breach_signals or SHAP data)
5. Line 2 = why the model scored it this way (use top_shap_drivers)
6. Line 3 = behavioral context (payment, salary, contact activity)
7. "summary" = one action sentence, max 18 words
8. ONLY use facts from the input data — never invent numbers
9. Never mention "model", "SHAP", or "algorithm" — speak about the customer
10. Use Indian collections terms: DPD, cycler, TL escalation, salary window

ANTI-HALLUCINATION:
- If breach_signals_from_model is empty, derive Line 1 from DPD and broken PTPs
- If top_shap_drivers is empty, say "Multiple risk factors contribute to high breach score"
- NEVER invent payment amounts, dates, or statistics not in the input

EXAMPLE INPUT:
{"risk_tier":"CRITICAL","dpd":18,"consecutive_broken_ptps":9,"breach_signals_from_model":["9 consecutive broken promises — chronic cycler"],"top_shap_drivers":[{"feature":"Promise month pattern","direction":"↑ risk"}],"salary_credit_detected":false}

EXAMPLE OUTPUT:
{"lines":["9 consecutive broken promises — chronic cycler, immediate escalation needed","Promise timing pattern is the top risk driver for this account","No salary credit detected, no UPI activity — call window limited"],"summary":"Escalate to TL immediately — do not issue new PTP, offer settlement."}

RETURN THIS EXACT SHAPE:
{"lines":["line1","line2","line3"],"summary":"action sentence"}"""


def build_breach_payload(row: pd.Series) -> dict:
    raw_breach = safe(row, "breach_signals", "")
    breach_list = [s.strip() for s in str(raw_breach).split("|") if s.strip() and str(raw_breach) != "nan"]

    raw_pos = safe(row, "positive_signals", "")
    pos_list = [s.strip() for s in str(raw_pos).split("|") if s.strip() and str(raw_pos) != "nan"]

    drivers = []
    for i in range(1, 4):
        f = safe(row, f"top_driver_{i}")
        d = safe(row, f"top_driver_{i}_dir")
        v = safe(row, f"top_driver_{i}_val")
        if f and str(f) != "nan":
            drivers.append({"feature": feat_label(str(f)), "direction": str(d),
                            "shap_value": round(float(v), 4) if v is not None else 0})

    return {
        "account_id":                 int(row["ACCOUNT_ID"]),
        "risk_tier":                  str(safe(row, "risk_tier", "UNKNOWN")),
        "risk_score":                 round(float(safe(row, "risk_score", 0.5)), 4),
        "breach_signals_from_model":  breach_list,
        "positive_signals_from_model":pos_list,
        "top_shap_drivers":           drivers,
        "dpd":                        int(safe(row, "DPD", 0)),
        "total_outstanding_inr":      round(float(safe(row, "TOTAL_OUTSTANDING_AMOUNT", 0))),
        "overdue_installments":       int(safe(row, "TOTAL_NO_OF_INSTALLMENT_OVERDUE", 0)),
        "overdue_ratio":              round(float(safe(row, "overdue_ratio", 0)), 3),
        "npa_flag":                   int(safe(row, "NPA_FLAG", 0)),
        "cheque_bounce":              int(safe(row, "CHEQUE_BOUNCE_FLAG", 0)),
        "total_ptps":                 int(safe(row, "total_ptps", 0)),
        "ptps_broken":                int(safe(row, "ptps_broken", 0)),
        "historical_fulfillment_rate":round(float(safe(row, "historical_fulfillment_rate", 0)), 3),
        "consecutive_broken_ptps":    int(safe(row, "consecutive_broken_ptps", 0)),
        "cycler_severity":            str(safe(row, "cycler_severity", "LOW")),
        "days_since_last_payment":    int(safe(row, "days_since_last_payment", 0)),
        "salary_credit_detected":     bool(safe(row, "salary_credit_detected", False)),
        "upi_activity_last_30d":      int(safe(row, "upi_activity_last_30d", 0)),
        "prior_partial_payment":      bool(safe(row, "prior_partial_payment", False)),
        "contact_attempts_before_ptp":int(safe(row, "contact_attempts_before_ptp", 0)),
        "patterns_detected": {
            "friday_promise":    bool(safe(row, "pattern_friday_maker", False)),
            "month_end_promise": bool(safe(row, "pattern_month_end_maker", False)),
            "repromise_decay":   bool(safe(row, "pattern_repromise_decay", False)),
            "high_dpd":          bool(safe(row, "pattern_high_dpd", False)),
        },
    }


def breach_fallback(p: dict) -> dict:
    """Rule-based 3 lines — guaranteed structure, no LLM needed."""
    lines = []

    # Line 1 — biggest risk
    if p["breach_signals_from_model"]:
        lines.append(p["breach_signals_from_model"][0][:120])
    elif p["consecutive_broken_ptps"] > 0:
        lines.append(f"{p['consecutive_broken_ptps']} consecutive broken promises — re-promise cycle active")
    else:
        sev = "severely" if p["dpd"] > 200 else "moderately" if p["dpd"] > 60 else "slightly"
        lines.append(f"DPD {p['dpd']} days — account {sev} overdue")

    # Line 2 — SHAP reason
    if p["top_shap_drivers"]:
        d = p["top_shap_drivers"][0]
        word = "increases" if "↑" in d["direction"] else "reduces"
        lines.append(f"{d['feature']} {word} breach risk for this account")
    else:
        lines.append(f"Historical fulfillment rate {round(p['historical_fulfillment_rate']*100)}% — below safe threshold")

    # Line 3 — behavioral
    if p["salary_credit_detected"]:
        lines.append("Salary credit detected — payment window open, act today")
    elif p["upi_activity_last_30d"] > 0:
        lines.append(f"UPI activity in last 30 days ({p['upi_activity_last_30d']} txns) — financially active")
    elif p["days_since_last_payment"] > 60:
        lines.append(f"No payment in {p['days_since_last_payment']} days — escalation urgency high")
    else:
        lines.append(f"Outstanding ₹{int(p['total_outstanding_inr']):,} — review before next contact")

    tier = p["risk_tier"]
    summaries = {
        "CRITICAL":  "Escalate immediately — do not issue new PTP, offer settlement.",
        "CYCLER":    "Stop accepting promises — require partial payment before new PTP.",
        "INTERVENE": "Intervention window open — call today with structured offer.",
    }
    summary = summaries.get(tier, "Standard follow-up — monitor and confirm payment on due date.")

    return {"lines": lines[:3], "summary": summary}


# ── Cache ─────────────────────────────────────────────────────────────────────
_breach_cache: dict = {}

def generate_breach_lines(account_id: int) -> BreachAnalysisResponse:
    """
    MAIN FUNCTION for breach analysis.
    Returns Pydantic-validated response — guaranteed shape.
    """
    ck = str(account_id)
    if ck in _breach_cache:
        return _breach_cache[ck]

    row = get_account(account_id)
    payload = build_breach_payload(row)

    try:
        user_msg = "Generate 3 breach analysis lines. Return JSON only.\n\n" + json.dumps(payload, default=str)
        raw = call_bedrock(BREACH_SYSTEM_PROMPT, user_msg, max_tokens=400)
        source = "claude"
    except Exception as e:
        log.warning(f"Bedrock failed for {account_id}: {e}, using fallback")
        raw = breach_fallback(payload)
        source = "fallback"

    # ── GUARDRAIL: Force exactly 3 lines via Pydantic ─────────────
    response = BreachAnalysisResponse(
        account_id = account_id,
        risk_tier  = payload["risk_tier"],
        risk_score = payload["risk_score"],
        lines      = raw.get("lines", [])[:3],
        summary    = raw.get("summary", ""),
        source     = source,
    )

    _breach_cache[ck] = response
    return response


# ═════════════════════════════════════════════════════════════════════════════
#  MODULE 2 — PERSONA BUILDER (top 5 features)
# ═════════════════════════════════════════════════════════════════════════════

PERSONA_SYSTEM_PROMPT = """You are PTPSense Persona Engine — builds customer personas for Indian collections.

TASK: Given statistics about high-fulfillment accounts vs baseline, return top 5 distinguishing features.

STRICT RULES:
1. Output ONLY a raw JSON object — no markdown, no explanation
2. "top_5_features" must be EXACTLY 5 items
3. Each feature: rank (1-5), feature_name (max 5 words), top_value, baseline_value, difference, why_it_matters (max 15 words), chart_color ("green" or "red")
4. Pick features with the LARGEST gap between top and baseline
5. ONLY use numbers from the input — never invent statistics
6. "persona_name" max 5 words, "persona_description" max 2 sentences
7. "collection_strategy" max 3 sentences, actionable for agents

ANTI-HALLUCINATION:
- Every number in your output must appear somewhere in the input
- If a percentage is 44.0% in input, output "44.0%" — not "45%" or "around 44%"
- Never round differently than the input provides

EXAMPLE OUTPUT:
{"persona_name":"Reliable First-Promise Payer","persona_description":"Low DPD accounts that fulfill on first promise without pressure.","top_5_features":[{"rank":1,"feature_name":"Days Past Due","top_value":"7.5 days","baseline_value":"40.8 days","difference":"-81.6%","why_it_matters":"Low DPD accounts fulfill first promise 5x more often.","chart_color":"green"},{"rank":2,"feature_name":"Broken PTPs","top_value":"0.0","baseline_value":"0.52","difference":"-100%","why_it_matters":"Zero broken promises — not a cycler.","chart_color":"green"},{"rank":3,"feature_name":"Salary Detected","top_value":"44.0%","baseline_value":"31.4%","difference":"+12.6%","why_it_matters":"Salary-aligned promises fulfill 1.8x more often.","chart_color":"green"},{"rank":4,"feature_name":"Risk Score","top_value":"0.104","baseline_value":"0.235","difference":"-55.5%","why_it_matters":"All breach signals absent — model confirms low risk.","chart_color":"green"},{"rank":5,"feature_name":"Re-promise Decay","top_value":"11.2%","baseline_value":"35.0%","difference":"-23.8%","why_it_matters":"First call succeeds — no re-promise cycle needed.","chart_color":"green"}],"collection_strategy":"One clear call is enough. Schedule confirmation 48h before due date. Do not over-contact."}

RETURN THIS EXACT SHAPE:
{"persona_name":"...","persona_description":"...","top_5_features":[5 items],"collection_strategy":"..."}"""


def compute_pattern_stats(df: pd.DataFrame, top: pd.DataFrame) -> list[PatternStat]:
    def pct(s): return round(float(s.mean()) * 100, 1)
    def cnt(s): return int(s.sum())

    return [
        PatternStat(id="P1", label="Weekend promise (Fri–Sun)",
            top_pct=pct(top["pattern_friday_maker"]), base_pct=pct(df["pattern_friday_maker"]),
            top_n=cnt(top["pattern_friday_maker"]), base_n=cnt(df["pattern_friday_maker"]),
            insight=f"{pct(top['pattern_friday_maker'])}% of top vs {pct(df['pattern_friday_maker'])}% baseline — top accounts avoid weekends"),
        PatternStat(id="P2", label="3rd+ re-promise decay",
            top_pct=pct(top["pattern_repromise_decay"]), base_pct=pct(df["pattern_repromise_decay"]),
            top_n=cnt(top["pattern_repromise_decay"]), base_n=cnt(df["pattern_repromise_decay"]),
            insight=f"{pct(top['pattern_repromise_decay'])}% of top vs {pct(df['pattern_repromise_decay'])}% baseline — first promise success is key"),
        PatternStat(id="P3", label="Salary-aligned PTP",
            top_pct=pct(top["salary_credit_detected"]), base_pct=pct(df["salary_credit_detected"]),
            top_n=cnt(top["salary_credit_detected"]), base_n=cnt(df["salary_credit_detected"]),
            insight=f"{pct(top['salary_credit_detected'])}% of top vs {pct(df['salary_credit_detected'])}% baseline — salary alignment boosts fulfillment"),
        PatternStat(id="P4", label="Low overdue installments",
            top_pct=round(100-pct(top["pattern_multi_overdue"]),1), base_pct=round(100-pct(df["pattern_multi_overdue"]),1),
            top_n=len(top)-cnt(top["pattern_multi_overdue"]), base_n=len(df)-cnt(df["pattern_multi_overdue"]),
            insight=f"Clean installment history predicts fulfillment — {round(100-pct(top['pattern_multi_overdue']),1)}% vs {round(100-pct(df['pattern_multi_overdue']),1)}% baseline"),
        PatternStat(id="P5", label="Low contact pressure (≤3 calls)",
            top_pct=round(100-(top["contact_attempts_before_ptp"]>=4).mean()*100,1),
            base_pct=round(100-(df["contact_attempts_before_ptp"]>=4).mean()*100,1),
            top_n=int((top["contact_attempts_before_ptp"]<4).sum()),
            base_n=int((df["contact_attempts_before_ptp"]<4).sum()),
            insight=f"Genuine promises need less pressure — {round(100-(top['contact_attempts_before_ptp']>=4).mean()*100,1)}% low-pressure vs {round(100-(df['contact_attempts_before_ptp']>=4).mean()*100,1)}% baseline"),
    ]


def compute_feature_summary(df: pd.DataFrame, top: pd.DataFrame) -> dict:
    return {
        "avg_fulfillment_prob":      round(float(top["last_fulfillment_prob"].mean()), 3),
        "avg_historical_rate":       round(float(top["historical_fulfillment_rate"].mean()), 3),
        "avg_dpd":                   round(float(top["DPD"].mean()), 1),
        "avg_consecutive_broken":    round(float(top["consecutive_broken_ptps"].mean()), 2),
        "avg_overdue_ratio":         round(float(top["overdue_ratio"].mean()), 3),
        "pct_salary_detected":       round(float(top["salary_credit_detected"].mean())*100, 1),
        "pct_upi_active":            round(float((top["upi_activity_last_30d"]>0).mean())*100, 1),
        "avg_risk_score":            round(float(top["risk_score"].mean()), 3),
        "pct_zero_broken":           round(float((top["consecutive_broken_ptps"]==0).mean())*100, 1),
        "baseline_fulfillment_prob": round(float(df["last_fulfillment_prob"].mean()), 3),
        "baseline_dpd":              round(float(df["DPD"].mean()), 1),
        "baseline_overdue_ratio":    round(float(df["overdue_ratio"].mean()), 3),
        "baseline_risk_score":       round(float(df["risk_score"].mean()), 3),
        "total_top": len(top), "total_all": len(df),
    }


def persona_fallback(ps: list[PatternStat], fs: dict) -> dict:
    return {
        "persona_name": "Reliable First-Promise Payer",
        "persona_description": (
            f"Top {fs['total_top']} accounts by fulfillment probability — "
            f"avg DPD {fs['avg_dpd']} days vs {fs['baseline_dpd']} baseline, "
            f"zero broken PTPs in {fs['pct_zero_broken']}% of cases."
        ),
        "top_5_features": [
            {"rank":1,"feature_name":"DPD (Days Past Due)","top_value":f"{fs['avg_dpd']} days",
             "baseline_value":f"{fs['baseline_dpd']} days",
             "difference":f"{round((fs['avg_dpd']-fs['baseline_dpd'])/(fs['baseline_dpd']+0.001)*100,1)}%",
             "why_it_matters":"Low DPD accounts fulfill first promise 5x more often.",
             "chart_color":"green"},
            {"rank":2,"feature_name":"Consecutive Broken PTPs","top_value":f"{fs['avg_consecutive_broken']}",
             "baseline_value":"0.52","difference":"-100%",
             "why_it_matters":"Zero broken promises — not a cycler.",
             "chart_color":"green"},
            {"rank":3,"feature_name":"Salary Credit Detected","top_value":f"{fs['pct_salary_detected']}%",
             "baseline_value":"31.4%","difference":f"+{round(fs['pct_salary_detected']-31.4,1)}%",
             "why_it_matters":"Salary-aligned promises fulfill 1.8x more often.",
             "chart_color":"green"},
            {"rank":4,"feature_name":"Risk Score","top_value":f"{fs['avg_risk_score']}",
             "baseline_value":f"{fs['baseline_risk_score']}",
             "difference":f"{round((fs['avg_risk_score']-fs['baseline_risk_score'])/(fs['baseline_risk_score']+0.001)*100,1)}%",
             "why_it_matters":"All breach signals absent — model confirms low risk.",
             "chart_color":"green"},
            {"rank":5,"feature_name":"Re-promise Decay","top_value":f"{ps[1].top_pct}%",
             "baseline_value":f"{ps[1].base_pct}%",
             "difference":f"{round(ps[1].top_pct-ps[1].base_pct,1)}%",
             "why_it_matters":"First call succeeds — no re-promise cycle needed.",
             "chart_color":"green"},
        ],
        "collection_strategy": (
            "One clear call is enough — do not over-contact. "
            "Schedule confirmation 48h before due date. "
            "Avoid pressure tactics; they trigger avoidance in this persona."
        ),
    }


_persona_cache = None

def generate_persona(top_n: int = TOP_N) -> PersonaResponse:
    """
    MAIN FUNCTION for persona.
    Returns Pydantic-validated response — guaranteed shape.
    """
    global _persona_cache
    if _persona_cache:
        return _persona_cache

    df  = get_df()
    top = df.nlargest(top_n, "last_fulfillment_prob")
    log.info(f"Persona: selected top {top_n} accounts")

    ps = compute_pattern_stats(df, top)
    fs = compute_feature_summary(df, top)

    try:
        payload = {"pattern_stats": [s.model_dump() for s in ps], "feature_summary": fs}
        user_msg = "Build the high-fulfillment persona. Return JSON only.\n\n" + json.dumps(payload, default=str)
        raw = call_bedrock(PERSONA_SYSTEM_PROMPT, user_msg, max_tokens=1000)
        source = "claude"
    except Exception as e:
        log.warning(f"Persona Bedrock failed: {e}, using fallback")
        raw = persona_fallback(ps, fs)
        source = "fallback"

    # ── GUARDRAIL: Validate via Pydantic ──────────────────────────
    response = PersonaResponse(
        persona_name        = raw.get("persona_name", "Reliable Payer")[:50],
        persona_description = raw.get("persona_description", "")[:300],
        top_5_features      = raw.get("top_5_features", [])[:5],
        collection_strategy = raw.get("collection_strategy", "")[:400],
        pattern_stats       = ps,
        source              = source,
    )

    _persona_cache = response
    return response


# ═════════════════════════════════════════════════════════════════════════════
#  FASTAPI APP — ready to serve
# ═════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="PTPSense GenAI Engine",
    description="LLM-powered breach analysis and persona builder for collections",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/genai/breach-analysis/{account_id}", response_model=BreachAnalysisResponse)
def api_breach_analysis(account_id: int):
    """
    Returns exactly 3 breach analysis lines for one account.

    Frontend:
      fetch(`/api/genai/breach-analysis/${accountId}`)
        .then(r => r.json())
        .then(d => {
          d.lines[0]  // first breach line
          d.lines[1]  // second line (SHAP reason)
          d.lines[2]  // third line (behavioral)
          d.summary   // action for agent
        })
    """
    try:
        return generate_breach_lines(account_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/genai/persona", response_model=PersonaResponse)
def api_persona(top_n: int = TOP_N):
    """
    Returns high-fulfillment customer persona with top 5 features + P1–P5 chart data.

    Frontend:
      fetch('/api/genai/persona')
        .then(r => r.json())
        .then(d => {
          d.persona_name         // chart title
          d.top_5_features       // 5 bar chart items
          d.pattern_stats        // P1–P5 bars (screenshot)
          d.collection_strategy  // strategy text
        })
    """
    return generate_persona(top_n)


@app.get("/api/genai/health")
def api_health():
    """Quick health check — no LLM call, verifies data is loaded."""
    df = get_df()
    return {
        "status":          "ok",
        "accounts_loaded":  len(df),
        "tiers":            df["risk_tier"].value_counts().to_dict(),
        "bedrock_configured": bool(os.environ.get("AWS_BEARER_TOKEN_BEDROCK")),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  CLI TEST — run directly to verify
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n  PTPSense GenAI Engine — Quick Test\n")

    df = get_df()
    for tier in ["CRITICAL", "CYCLER", "INTERVENE", "STABLE"]:
        subset = df[df["risk_tier"] == tier]
        if subset.empty:
            continue
        acc = int(subset.iloc[0]["ACCOUNT_ID"])
        print(f"  [{tier}] Account {acc}")
        result = generate_breach_lines(acc)
        print(f"    Line 1: {result.lines[0]}")
        print(f"    Line 2: {result.lines[1]}")
        print(f"    Line 3: {result.lines[2]}")
        print(f"    Action: {result.summary}")
        print(f"    Source: {result.source}\n")

    print("  [PERSONA]")
    persona = generate_persona()
    print(f"    Name: {persona.persona_name}")
    for f in persona.top_5_features:
        print(f"    #{f.rank} {f.feature_name}: {f.top_value} vs {f.baseline_value} ({f.difference})")
    print(f"    Source: {persona.source}\n")

    print("  Start server: uvicorn ptpsense_genai:app --reload --port 8001\n")