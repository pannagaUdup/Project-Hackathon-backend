"""
Standalone PTP Fulfillment Scorer — self-contained single file.

Portability:
  - No imports from any project-local module (src.*, dashboard.*, etc.).
  - Only depends on: pandas, numpy, joblib, xgboost (installed via pip).

Artifacts you must copy alongside this script to the target platform:
  1. account_features.csv   (the enriched account dataset)
  2. fulfillment_model.pkl        (the trained XGBoost model)

Update CSV_PATH and MODEL_PATH below to point at wherever you place them.

Usage:
  # As CLI
  python standalone_scorer.py 253154 PTP
  python standalone_scorer.py 253154 NON_PTP

  # As a library
  from standalone_scorer import score_account
  result = score_account(253154, "PTP")
"""

import argparse
import json
import os
import sys
import time
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

# ────────────────────────────────────────────────────────────────────────────
# CONFIG — edit these paths for your target platform
# ────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "database", "account_features.csv")
MODEL_PATH = os.path.join(BASE_DIR, "models", "fulfillment_model.pkl")

# ────────────────────────────────────────────────────────────────────────────
# Feature contract — MUST match the 28 columns the XGBoost model was trained on
# ────────────────────────────────────────────────────────────────────────────
FEATURE_COLS = [
    "days_to_due", "ptp_dow", "ptp_dom", "ptp_month", "ptp_hour",
    "is_month_end", "is_friday", "channel_visit",
    "promised_amount_filled", "promise_to_outstanding",
    "REPROMISE_FLAG",
    "acc_dpd", "acc_total_outstanding", "acc_principal_outstanding",
    "INSTALLMENT_AMOUNT", "TOTAL_NO_OF_INSTALLMENT_OVERDUE",
    "TOTAL_NO_OF_INSTALLMENT_PAID", "overdue_ratio", "paid_ratio",
    "outstanding_to_loan", "NPA_FLAG", "CHEQUE_BOUNCE_FLAG", "MOB",
    "total_ptps", "total_repromises", "historical_repromise_rate",
    "agent_ptp_count", "agent_fulfillment_rate",
]


# ────────────────────────────────────────────────────────────────────────────
# Cached loaders — CSV and model are loaded once per process
# ────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _load_accounts() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Account CSV not found at {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, low_memory=False)
    df["last_ptp_date"] = pd.to_datetime(df["last_ptp_date"], errors="coerce")
    for col in ("NPA_FLAG", "CHEQUE_BOUNCE_FLAG"):
        if col in df.columns and df[col].dtype == object:
            df[col] = (df[col].astype(str).str.upper() == "Y").astype(int)
        else:
            df[col] = df[col].fillna(0).astype(int)
    return df


@lru_cache(maxsize=1)
def _load_model():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model pickle not found at {MODEL_PATH}")
    return joblib.load(MODEL_PATH)


# ────────────────────────────────────────────────────────────────────────────
# Feature row builder — converts one account record into the model's input
# ────────────────────────────────────────────────────────────────────────────
def _build_feature_row(acct: pd.Series) -> pd.DataFrame:
    d = acct.get("last_ptp_date")
    if pd.isna(d):
        d = pd.Timestamp.now()

    channel      = str(acct.get("last_ptp_channel") or "").lower()
    total_ptps   = _sf(acct.get("total_ptps"))
    total_reprom = _sf(acct.get("total_repromises"))
    outstanding  = _sf(acct.get("TOTAL_OUTSTANDING_AMOUNT"))
    promised     = _sf(acct.get("last_ptp_amount"))

    row = {
        "days_to_due":   _sf(acct.get("days_until_due"), 15),
        "ptp_dow":  int(d.dayofweek),
        "ptp_dom":  int(d.day),
        "ptp_month":int(d.month),
        "ptp_hour": int(d.hour),
        "is_month_end":  int(d.day >= 25),
        "is_friday":     int(d.dayofweek == 4),
        "channel_visit": int(channel == "visit"),
        "promised_amount_filled": min(promised, 1e7),
        "promise_to_outstanding": (promised / outstanding) if outstanding > 0 else 0.0,
        "REPROMISE_FLAG":               _si(acct.get("last_ptp_repromise_flag")),
        "acc_dpd":                      _sf(acct.get("DPD")),
        "acc_total_outstanding":        outstanding,
        "acc_principal_outstanding":    _sf(acct.get("PRINCIPAL_OUTSTANDING_AMOUNT")),
        "INSTALLMENT_AMOUNT":           _sf(acct.get("INSTALLMENT_AMOUNT")),
        "TOTAL_NO_OF_INSTALLMENT_OVERDUE": _sf(acct.get("TOTAL_NO_OF_INSTALLMENT_OVERDUE")),
        "TOTAL_NO_OF_INSTALLMENT_PAID":    _sf(acct.get("TOTAL_NO_OF_INSTALLMENT_PAID")),
        "overdue_ratio":        _sf(acct.get("overdue_ratio")),
        "paid_ratio":           _sf(acct.get("paid_ratio")),
        "outstanding_to_loan":  _sf(acct.get("outstanding_to_loan")),
        "NPA_FLAG":             _si(acct.get("NPA_FLAG")),
        "CHEQUE_BOUNCE_FLAG":   _si(acct.get("CHEQUE_BOUNCE_FLAG")),
        "MOB":                  _sf(acct.get("MOB")),
        "total_ptps":           total_ptps,
        "total_repromises":     total_reprom,
        "historical_repromise_rate": (total_reprom / total_ptps) if total_ptps > 0 else 0.0,
        "agent_ptp_count":       _sf(acct.get("agent_ptp_count")),
        "agent_fulfillment_rate":_sf(acct.get("agent_fulfillment_rate")),
    }
    return pd.DataFrame([row])[FEATURE_COLS]


# ────────────────────────────────────────────────────────────────────────────
# Plain-English insight based on raw feature values
# ────────────────────────────────────────────────────────────────────────────
def _insight(acct: pd.Series) -> list:
    parts = []
    dpd = _sf(acct.get("DPD"))
    if dpd >= 60:
        parts.append(f"High DPD ({int(dpd)}d) — pushes toward breach")
    elif dpd < 15:
        parts.append(f"Low DPD ({int(dpd)}d) — pushes toward fulfillment")

    if _si(acct.get("last_ptp_repromise_flag")) == 1:
        parts.append("Latest PTP is a re-promise — pushes toward breach")

    total_ptps   = _sf(acct.get("total_ptps"))
    total_reprom = _sf(acct.get("total_repromises"))
    if total_ptps > 0 and (total_reprom / total_ptps) > 0.5:
        parts.append(f"High historical re-promise rate ({total_reprom / total_ptps * 100:.0f}%)")

    if str(acct.get("last_ptp_channel") or "").lower() == "visit":
        parts.append("Visit-channel promise — historically lower fulfillment")

    overdue = _sf(acct.get("overdue_ratio"))
    if overdue > 0.2:
        parts.append(f"Overdue ratio {overdue * 100:.0f}% — pushes toward breach")

    agent_rate = _sf(acct.get("agent_fulfillment_rate"))
    if agent_rate > 0.75:
        parts.append(f"Strong agent track record ({agent_rate * 100:.0f}% fulfillment)")
    elif 0 < agent_rate < 0.30:
        parts.append(f"Weak agent track record ({agent_rate * 100:.0f}% fulfillment)")

    if _si(acct.get("NPA_FLAG")) == 1:
        parts.append("Account is NPA — pushes toward breach")

    return parts or ["Score driven by combined account signals (no single dominant driver)."]


# ────────────────────────────────────────────────────────────────────────────
# NaN-safe coercions  (NaN is truthy in Python, so `nan or 0` returns nan)
# ────────────────────────────────────────────────────────────────────────────
def _sf(v, default=0.0) -> float:
    """Safe float: return default when value is None / NaN."""
    try:
        f = float(v)
        return default if (f != f) else f   # f != f  ↔  math.isnan(f)
    except (TypeError, ValueError):
        return default

def _si(v, default=0) -> int:
    """Safe int: return default when value is None / NaN."""
    try:
        f = float(v)
        if f != f:           # NaN check
            return default
        return int(f)
    except (TypeError, ValueError):
        return default


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────
def score_account(account_id: int, disposition: str = "PTP") -> dict:
    """
    Score a single account's latest PTP.

    Parameters
    ----------
    account_id : int
        ACCOUNT_ID present in account_features.csv.
    disposition : str
        "PTP"      → run the fulfillment model.
        "NON_PTP"  → skip scoring, return a no-op response.

    Returns
    -------
    dict — JSON-serializable result.
    """
    disp = (disposition or "").upper().strip()

    if disp == "NON_PTP":
        return {
            "account_id": int(account_id),
            "disposition": "NON_PTP",
            "scored": False,
            "message": "Call ended without a promise. No fulfillment score generated.",
        }
    if disp != "PTP":
        raise ValueError("disposition must be 'PTP' or 'NON_PTP'")

    df = _load_accounts()
    match = df[df["ACCOUNT_ID"] == account_id]
    if len(match) == 0:
        raise LookupError(f"Account {account_id} not found in {os.path.basename(CSV_PATH)}")

    acct = match.iloc[0]
    X = _build_feature_row(acct)

    t0 = time.time()
    model = _load_model()
    prob = float(model.predict_proba(X)[0, 1])
    elapsed = round(time.time() - t0, 4)

    if prob >= 0.65:
        tier = "High"
    elif prob >= 0.40:
        tier = "Medium"
    else:
        tier = "Low"

    return {
        "account_id": int(account_id),
        "disposition": "PTP",
        "scored": True,
        "fulfillment_probability": round(prob, 4),
        "confidence_tier": tier,
        "scored_in_seconds": elapsed,
        "latest_ptp": {
            "PTP_DATE": str(acct.get("last_ptp_date") or ""),
            "CHANNEL":  str(acct.get("last_ptp_channel") or ""),
            "PROMISED_AMOUNT": _sf(acct.get("last_ptp_amount")),
            "AGENT_ID": _si(acct.get("last_ptp_agent_id")) if pd.notna(acct.get("last_ptp_agent_id")) else None,
            "REPROMISE_FLAG": _si(acct.get("last_ptp_repromise_flag")),
        },
        "account_context": {
            "DPD":                    _si(acct.get("DPD")),
            "TOTAL_OUTSTANDING_AMOUNT": _sf(acct.get("TOTAL_OUTSTANDING_AMOUNT")),
            "total_ptps":             _si(acct.get("total_ptps")),
            "total_repromises":       _si(acct.get("total_repromises")),
            "agent_fulfillment_rate": _sf(acct.get("agent_fulfillment_rate")),
        },
        "score_insight": _insight(acct),
    }


# ────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ────────────────────────────────────────────────────────────────────────────
def _main() -> None:
    parser = argparse.ArgumentParser(description="Standalone PTP Fulfillment Scorer")
    parser.add_argument("account_id", type=int, help="Numeric ACCOUNT_ID to score")
    parser.add_argument(
        "disposition",
        nargs="?",
        default="PTP",
        choices=["PTP", "NON_PTP"],
        help="Call disposition (default: PTP)",
    )
    args = parser.parse_args()

    try:
        result = score_account(args.account_id, args.disposition)
    except (FileNotFoundError, LookupError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    _main()
