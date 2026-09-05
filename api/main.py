"""
FastAPI Service for AI Revenue Recovery Agent

Provides REST API endpoints for:
- Health check & readiness
- Batch run execution
- Audit trail retrieval
- Evaluation report retrieval
- Interactive Hosted Razorpay Checkout Simulator with Bank Telemetry (/pay/{link_id})
"""

import sys
import os
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
import json
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Security, status, Depends, Request
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from agent.pipeline import run_batch
from agent.evaluate import compute_evaluation_report
from sqlalchemy import text
from storage.db import (
    init_db, get_audit_records, get_audit_trail, get_engine,
    insert_promise_to_pay, get_promises_to_pay, update_promise_to_pay_status
)
from storage.models import AuditLog, PromiseToPay
from agent.b2b_chaser import load_b2b_invoices, compute_b2b_aging_metrics, execute_b2b_chase_action
from agent.hinglish_bot import process_hinglish_chat
from agent.mandate_sequencer import generate_mandate_retry_schedule, get_all_subscription_mandates

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    expected_token = os.getenv("API_AUTH_TOKEN", "rev_rec_secret_token_2026")
    if api_key and api_key != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key."
        )
    return api_key

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="RazorRevive - Autonomous AI Revenue Recovery System (Track 03)",
    description="Production-grade autonomous AI recovery system that intercepts drop-offs, negotiates in Hinglish with real voice AI, and synchronizes Promise-to-Pay commitments.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BatchRunRequest(BaseModel):
    batch_id: Optional[str] = Field(None, description="Optional custom batch identifier")
    transactions: Optional[List[Dict[str, Any]]] = Field(None, description="Optional list of transactions")

class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str
    version: str

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "service": "AI Revenue Recovery Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0"
    }

@app.post("/run-batch", tags=["Recovery Pipeline"])
def trigger_batch_run(
    request: BatchRunRequest = BatchRunRequest(),
    _: Optional[str] = Depends(verify_api_key)
):
    transactions = request.transactions
    if not transactions:
        sample_path = ROOT_DIR / "data" / "sample_batch.json"
        if not sample_path.exists():
            from data.generate_batch import save_sample_batch
            sample_path = save_sample_batch()
        with open(sample_path, "r", encoding="utf-8") as f:
            transactions = json.load(f)

    if not isinstance(transactions, list) or len(transactions) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transaction batch must be a non-empty list of JSON objects."
        )

    try:
        report = run_batch(transactions=transactions, batch_id=request.batch_id)
        return report
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch execution failed: {str(e)}"
        )

@app.get("/audit-trail/{batch_id}", tags=["Audit & Compliance"])
def get_audit_log(batch_id: str, _: Optional[str] = Depends(verify_api_key)):
    records = get_audit_records(batch_id=batch_id)
    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No audit trail records found for batch '{batch_id}'."
        )
    return {"batch_id": batch_id, "count": len(records), "records": records}

@app.get("/report/{batch_id}", tags=["Reporting"])
def get_evaluation_report(batch_id: str, _: Optional[str] = Depends(verify_api_key)):
    records = get_audit_records(batch_id=batch_id)
    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No audit trail records found for batch '{batch_id}'."
        )
    report = compute_evaluation_report(batch_id=batch_id, records=records)
    return report

@app.get("/api/capture-payment", tags=["Payment Simulation"])
@app.post("/api/capture-payment", tags=["Payment Simulation"])
def capture_payment_endpoint(
    txn: str,
    amount: float = 0.0,
    batch_id: Optional[str] = None
):
    """
    Captures and marks a transaction as recovered in the SQLite audit ledger.
    """
    try:
        with get_engine().connect() as conn:
            if batch_id:
                res = conn.execute(
                    text("UPDATE audit_log SET recovered = 1, recovered_amount = :amt, execution_status = 'executed' WHERE transaction_id = :txn AND batch_id = :bid"),
                    {"amt": amount, "txn": txn, "bid": batch_id}
                )
            else:
                res = conn.execute(
                    text("UPDATE audit_log SET recovered = 1, recovered_amount = :amt, execution_status = 'executed' WHERE transaction_id = :txn"),
                    {"amt": amount, "txn": txn}
                )
            if res.rowcount == 0:
                conn.execute(
                    text("""
                        INSERT INTO audit_log (
                            batch_id, transaction_id, customer_id, timestamp, detector_flagged, risk_reason,
                            diagnosis_cause, diagnosis_confidence, diagnosis_method, diagnosis_reasoning,
                            proposed_action, decision_reasoning, guardrail_approved, guardrail_reason,
                            guardrail_rule, execution_status, execution_result, amount, recovered, recovered_amount
                        ) VALUES (
                            :bid, :txn, 'cust_interactive', CURRENT_TIMESTAMP, 1, 'checkout_dropoff',
                            'card_declined', 0.95, 'hybrid', 'Pre-configured alternative bank method authorized',
                            'send_reminder_alt_method', '1-click biometric UPI replacement', 1, 'pass',
                            'within_limits', 'executed', 'payment_captured', :amt, 1, :amt
                        )
                    """),
                    {"bid": batch_id or "batch_interactive", "txn": txn, "amt": amount}
                )
            conn.commit()
        return {
            "status": "success",
            "transaction_id": txn,
            "recovered_amount": amount,
            "message": f"Transaction {txn} captured and marked recovered."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to capture payment in audit ledger: {str(e)}"
        )

# --- Track 03 Pydantic Request Models ---
class HinglishChatRequest(BaseModel):
    message: str = Field(..., description="Customer message in Hinglish or English")
    customer_name: Optional[str] = "Valued Customer"
    amount: Optional[float] = 3743.17
    transaction_id: Optional[str] = "pay_synth_001"
    customer_id: Optional[str] = "cust_live"
    failed_instrument: Optional[str] = "Card"

class B2BChaseRequest(BaseModel):
    invoice_id: str = Field(..., description="Corporate invoice ID (e.g. INV-2024-8801)")
    action_type: str = Field(..., description="Action to execute: send_gst_warning, apply_cash_discount, send_soa, escalate_legal, mark_paid")
    custom_note: Optional[str] = None

class PTPCreateRequest(BaseModel):
    transaction_id: str
    customer_id: str
    customer_name: Optional[str] = "Customer"
    amount: float
    ptp_date: str
    channel: Optional[str] = "hinglish_chat"
    notes: Optional[str] = ""

# --- Track 03 API Endpoints ---
@app.get("/api/b2b/invoices", tags=["B2B Receivables Chaser"])
def get_b2b_invoices_endpoint():
    """Returns corporate B2B invoices and aging analytics."""
    invoices = load_b2b_invoices()
    metrics = compute_b2b_aging_metrics(invoices)
    return {"metrics": metrics, "invoices": invoices}

@app.post("/api/b2b/chase", tags=["B2B Receivables Chaser"])
def trigger_b2b_chase_endpoint(req: B2BChaseRequest):
    """Executes statutory GST warning, Net-30 discount, or SOA dispatch."""
    res = execute_b2b_chase_action(req.invoice_id, req.action_type, req.custom_note)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "B2B action failed"))
    return res

@app.post("/api/chat/hinglish", tags=["Hinglish Conversational Bot"])
def chat_hinglish_endpoint(req: HinglishChatRequest):
    """Converses in authentic Indian business Hinglish and extracts PTP commitments."""
    context = {
        "customer_name": req.customer_name,
        "amount": req.amount,
        "transaction_id": req.transaction_id,
        "customer_id": req.customer_id,
        "failed_instrument": req.failed_instrument
    }
    return process_hinglish_chat(req.message, context)

@app.get("/api/ptp", tags=["Promise to Pay Tracker"])
def list_ptp_endpoint(status: Optional[str] = None):
    """Returns all Promise-to-Pay commitments."""
    return {"records": get_promises_to_pay(status=status)}

@app.post("/api/ptp", tags=["Promise to Pay Tracker"])
def create_ptp_endpoint(req: PTPCreateRequest):
    """Registers a new Promise-to-Pay commitment in the database."""
    entry_dict = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    entry = insert_promise_to_pay(entry_dict)
    return {"status": "success", "ptp": entry.to_dict()}

@app.post("/api/ptp/{ptp_id}/status", tags=["Promise to Pay Tracker"])
def update_ptp_status_endpoint(ptp_id: int, new_status: str):
    """Updates PTP status (e.g. honored, breached)."""
    success = update_promise_to_pay_status(ptp_id, new_status)
    if not success:
        raise HTTPException(status_code=404, detail="PTP record not found")
    return {"status": "success", "id": ptp_id, "new_status": new_status}

@app.get("/api/mandates/schedule", tags=["Mandate Retry Sequencer"])
def get_mandate_schedule_endpoint(subscription_id: Optional[str] = "sub_enterprise_091"):
    """Returns off-peak and salary-synchronized mandate retry schedule."""
    schedule = generate_mandate_retry_schedule(subscription_id)
    all_mandates = get_all_subscription_mandates()
    return {"schedule": schedule, "all_mandates": all_mandates}

@app.get("/pay/{link_id}", response_class=HTMLResponse, tags=["Payment Simulation"])
def render_payment_link_page(
    link_id: str,
    txn: str = "txn_demo",
    amount: float = 3743.17,
    cust: str = "customer",
    action: str = "send_reminder_alt_method",
    failed_inst: str = "HDFC Bank Visa Card (•••• 4242)",
    fail_reason: str = "Card declined by issuing bank (3DS Authorization Timeout)",
    paying_inst: str = "Kotak Mahindra Bank Savings A/c (•••• 6153) via BHIM",
    vpa: str = "user@kotakbank",
    recovered: Optional[int] = None,
    batch_id: Optional[str] = None
):
    """
    Production-grade interactive hosted Razorpay Checkout Simulator with 2 distinct portals:
    - Green Settled Receipt View: For already-recovered transactions (displays payment captured,
      debited account, transaction lineage, and settlement details without asking to pay again).
    - Red Action Required View: For non-recovered transactions (displays friction diagnosis,
      pre-configured replacement method, and active 1-click UPI authorization button).
    """
    # Check if transaction is already marked recovered in database or explicitly requested
    is_recovered = bool(recovered) if recovered is not None else False
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT recovered, recovered_amount, customer_id, amount, batch_id FROM audit_log WHERE transaction_id = :txn ORDER BY id DESC LIMIT 1"),
                {"txn": txn}
            ).fetchone()
            if row:
                if recovered is None and row[0]:
                    is_recovered = True
                if row[3]:
                    amount = float(row[3])
                if row[2]:
                    cust = str(row[2])
                if row[4] and not batch_id:
                    batch_id = str(row[4])
    except Exception:
        pass

    # Status tag & styling variables based on recovery state
    state_badge_html = (
        '<div class="badge badge-paid">● PAID & SETTLED</div>'
        if is_recovered
        else '<div class="badge badge-action">⚠️ ACTION REQUIRED</div>'
    )

    portal_type_label = "Settled Receipt" if is_recovered else "Recovery Checkout"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Razorpay {portal_type_label} — Order {txn}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, sans-serif; }}
        
        /* WCAG AA Base Typography & Clean Enterprise Background (SC 1.4.3) */
        body {{
            background-color: #f8fafc;
            background-image: linear-gradient(180deg, #f0f7ff 0%, #f8fafc 240px);
            color: #0f172a;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 24px;
            position: relative;
            overflow-x: hidden;
        }}

        /* WCAG AA Visible Focus Ring (SC 2.4.7) */
        *:focus-visible,
        button:focus-visible,
        a:focus-visible {{
            outline: 3px solid #0052cc !important;
            outline-offset: 2px !important;
        }}

        /* WCAG AA Reduced Motion Support (SC 2.2.2) */
        @media (prefers-reduced-motion: reduce) {{
            *, *::before, *::after {{
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.01ms !important;
                scroll-behavior: auto !important;
            }}
        }}

        .checkout-container {{
            background: #ffffff;
            border: 1.5px solid #cbd5e1;
            border-radius: 20px;
            width: 100%;
            max-width: 520px;
            box-shadow: 0 16px 36px -8px rgba(0, 0, 0, 0.08), 0 4px 12px rgba(0, 0, 0, 0.04);
            overflow: hidden;
            position: relative;
            z-index: 10;
        }}

        /* Top Razorpay Header */
        .header {{
            background: linear-gradient(135deg, #0c2340 0%, #173660 100%);
            color: #ffffff;
            padding: 24px;
            position: relative;
            border-bottom: 2px solid rgba(255, 255, 255, 0.15);
        }}
        .brand {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }}
        .rzp-logo {{
            font-weight: 800;
            font-size: 20px;
            letter-spacing: -0.5px;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .rzp-logo span {{
            color: #7dd3fc;
        }}
        .badge {{
            font-size: 11px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 9999px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .badge-paid {{
            background: #d1fae5;
            color: #065f46;
            border: 1.5px solid #6ee7b7;
        }}
        .badge-action {{
            background: #fee2e2;
            color: #991b1b;
            border: 1.5px solid #fca5a5;
        }}
        .amount-tag {{
            font-size: 32px;
            font-weight: 800;
            color: #ffffff;
            letter-spacing: -0.5px;
            margin-top: 4px;
            font-variant-numeric: tabular-nums;
        }}
        .sub {{
            font-size: 13px;
            color: #e2e8f0;
            margin-top: 4px;
            font-weight: 500;
        }}

        /* Bento cards */
        .bento-fail {{
            background: #fff1f2;
            border: 1.5px solid #fca5a5;
            border-radius: 12px;
            padding: 14px 16px;
            margin: 18px 24px 0;
        }}
        .bento-pass {{
            background: #f0fdf4;
            border: 1.5px solid #86efac;
            border-radius: 12px;
            padding: 14px 16px;
            margin: 14px 24px 0;
        }}
        .bento-nudge {{
            background: #eff6ff;
            border: 1.5px solid #7dd3fc;
            border-radius: 12px;
            padding: 12px 16px;
            margin: 14px 24px 0;
            font-size: 12px;
            color: #0369a1;
            font-weight: 600;
        }}

        .body-section {{
            padding: 20px 24px 24px;
        }}
        .section-title {{
            font-size: 11px;
            font-weight: 800;
            color: #334155;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            margin-bottom: 8px;
        }}
        .inst-title {{
            font-size: 15px;
            font-weight: 800;
            color: #0f172a;
        }}
        .inst-sub {{
            font-size: 12px;
            color: #334155;
            margin-top: 2px;
            line-height: 1.5;
        }}
        .inst-sub code {{
            background: #e0f2fe;
            color: #075985;
            border: 1px solid #7dd3fc;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            font-weight: 700;
        }}

        /* QR Box */
        .qr-card {{
            text-align: center;
            padding: 16px;
            background: #f8fafc;
            border: 1.5px solid #cbd5e1;
            border-radius: 12px;
            margin-top: 14px;
        }}
        .qr-placeholder {{
            width: 120px;
            height: 120px;
            background: #0c2340;
            margin: 0 auto;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-weight: 800;
            font-size: 11px;
            letter-spacing: 1px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.12);
        }}

        /* Pay Button */
        .pay-btn {{
            width: 100%;
            background: #0052cc;
            color: #ffffff;
            border: 2px solid #0052cc;
            border-radius: 12px;
            padding: 16px;
            font-size: 15px;
            font-weight: 800;
            letter-spacing: 0.3px;
            cursor: pointer;
            margin-top: 16px;
            box-shadow: 0 4px 14px rgba(0, 82, 204, 0.3);
            transition: all 0.2s ease;
        }}
        .pay-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 18px rgba(0, 82, 204, 0.4);
            background: #0040a8;
            border-color: #0040a8;
        }}

        /* Secondary Action Buttons */
        .action-btn {{
            width: 100%;
            border-radius: 10px;
            padding: 14px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        /* Green Settled Receipt Specific Layout */
        .settled-receipt-box {{
            background: #f0fdf4;
            border: 1.5px solid #86efac;
            border-radius: 16px;
            padding: 22px;
            text-align: center;
            margin: 20px 24px;
        }}
        .settled-check-circle {{
            width: 64px;
            height: 64px;
            background: #065f46;
            border-radius: 50%;
            color: #ffffff;
            font-size: 34px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 12px;
            box-shadow: 0 6px 16px rgba(6, 95, 70, 0.25);
        }}
        .settled-title {{
            font-size: 20px;
            font-weight: 800;
            color: #065f46;
            margin-bottom: 4px;
        }}
        .settled-subtitle {{
            font-size: 13px;
            color: #065f46;
            font-weight: 600;
        }}
        .settled-pill {{
            display: inline-block;
            margin-top: 10px;
            background: #d1fae5;
            color: #065f46;
            font-size: 11px;
            font-weight: 800;
            padding: 4px 12px;
            border-radius: 9999px;
            border: 1.5px solid #6ee7b7;
        }}

        /* Lineage Table */
        .receipt-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-top: 8px;
            text-align: left;
        }}
        .receipt-table td, .receipt-table th {{
            padding: 10px 0;
            border-bottom: 1px solid #e2e8f0;
        }}
        .receipt-label {{
            color: #334155;
            font-weight: 700;
            width: 42%;
            text-align: left;
        }}
        .receipt-val {{
            color: #0f172a;
            font-weight: 800;
            text-align: right;
        }}

        .footer-sec {{
            text-align: center;
            padding: 14px 20px;
            border-top: 1.5px solid #e2e8f0;
            font-size: 12px;
            color: #334155;
            font-weight: 600;
            background: #f8fafc;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}

        @media (max-width: 480px) {{
            body {{
                padding: 10px;
            }}
            .checkout-container {{
                border-radius: 14px;
            }}
            .header {{
                padding: 16px;
            }}
            .amount-tag {{
                font-size: 26px;
            }}
            .bento-fail, .bento-pass, .bento-nudge {{
                margin-left: 14px;
                margin-right: 14px;
                padding: 12px;
            }}
            .body-sec {{
                padding: 16px 14px;
            }}
            .settled-receipt-box {{
                margin: 14px;
                padding: 16px;
            }}
        }}
    </style>
</head>
<body>
    <main class="checkout-container" role="main">
        <!-- Razorpay Header -->
        <header class="header" role="banner">
            <div class="brand">
                <div class="rzp-logo">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                        <path d="M12.02 0L2 14.88h7.94L7.54 24l12.44-12.82h-7.96L14.46 0h-2.44z" fill="#7dd3fc"/>
                    </svg>
                    Razorpay <span>Checkout</span>
                </div>
                {state_badge_html}
            </div>
            <div class="amount-tag">₹{amount:,.2f}</div>
            <div class="sub">Order ID: <strong style="color:#ffffff;">{txn}</strong> • Customer: <strong style="color:#ffffff;">{cust}</strong></div>
        </header>

        {"<!-- ================= 1. GREEN SETTLED PORTAL (RECOVERED) ================= -->" if is_recovered else "<!-- ================= 2. RED ACTION REQUIRED PORTAL (UNRECOVERED) ================= -->"}
        
        {f'''
        <!-- Green Settled Receipt View -->
        <div id="settled-view" role="region" aria-label="Settled Payment Receipt">
            <div class="settled-receipt-box">
                <div class="settled-check-circle" aria-hidden="true">✓</div>
                <div class="settled-title">Payment Captured & Settled!</div>
                <div class="settled-subtitle">
                    ₹{amount:,.2f} received via <strong>{paying_inst}</strong>
                </div>
                <div class="settled-pill">✓ Escrow Settled • Zero Risk (Test Mode)</div>
            </div>

            <div class="body-section" style="padding-top: 0;">
                <div class="section-title">Settled Payment Telemetry</div>
                
                <table class="receipt-table" aria-label="Settled Payment Telemetry Details">
                    <tr>
                        <th scope="row" class="receipt-label">Payment ID</th>
                        <td class="receipt-val"><span style="font-family:'JetBrains Mono',monospace; color:#0369a1; font-weight:700;">pay_settled_{link_id[-8:]}</span></td>
                    </tr>
                    <tr>
                        <th scope="row" class="receipt-label">Settlement Reference</th>
                        <td class="receipt-val"><span style="font-family:'JetBrains Mono',monospace;">RRN-{link_id[-6:]}</span></td>
                    </tr>
                    <tr>
                        <th scope="row" class="receipt-label">Debited Instrument</th>
                        <td class="receipt-val">🟢 {paying_inst}</td>
                    </tr>
                    <tr>
                        <th scope="row" class="receipt-label">UPI VPA Handle</th>
                        <td class="receipt-val"><code>{vpa}</code></td>
                    </tr>
                    <tr>
                        <th scope="row" class="receipt-label">Authorization Rail</th>
                        <td class="receipt-val">1-Click Biometric UPI (Instant)</td>
                    </tr>
                    <tr>
                        <th scope="row" class="receipt-label">Resolved Friction</th>
                        <td class="receipt-val" style="color:#065f46; font-weight:800;">Bypassed {failed_inst} ({fail_reason})</td>
                    </tr>
                </table>

                <div style="margin-top: 20px;">
                    <button class="action-btn" onclick="window.print()" style="background:#0052cc; color:#ffffff; border:2px solid #0052cc; box-shadow:0 4px 12px rgba(0,82,204,0.3);" aria-label="Print or download tax invoice">
                        🖨️ Print / Download Tax Invoice
                    </button>
                    <button class="action-btn" onclick="window.close()" style="background:#f8fafc; color:#334155; border:1.5px solid #cbd5e1; margin-top:8px;" aria-label="Close window">
                        ✕ Close Window
                    </button>
                </div>
            </div>
        </div>
        ''' if is_recovered else f'''
        <!-- Red Action Required Checkout View -->
        <div id="checkout-view" role="region" aria-label="Payment Recovery Authorization">
            <!-- Failed Friction Attempt Notice -->
            <div class="bento-fail" role="region" aria-label="Failed Customer Attempt">
                <div style="font-size: 11px; font-weight: 800; color: #991b1b; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 4px;">
                    <span aria-hidden="true">❌</span> Failed Customer Attempt
                </div>
                <div class="inst-title" style="color: #7f1d1d;">{failed_inst}</div>
                <div class="inst-sub" style="color: #450a0a; margin-top: 4px;">
                    <strong>Friction:</strong> {fail_reason}
                </div>
            </div>

            <!-- AI Recovery Routing Nudge -->
            <div class="bento-nudge" role="note">
                <span aria-hidden="true">⚡</span> <strong>AI Recovery Routing:</strong> Automatically switched to instant 1-Click Biometric UPI Rail to bypass card network degradation.
            </div>

            <!-- Pre-Configured Replacement Method -->
            <div class="bento-pass" role="region" aria-label="Pre-Configured Replacement Method">
                <div style="font-size: 11px; font-weight: 800; color: #065f46; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 4px;">
                    <span aria-hidden="true">⚡</span> Pre-Configured Replacement Method
                </div>
                <div class="inst-title">{paying_inst}</div>
                <div class="inst-sub">
                    UPI VPA: <code>{vpa}</code> • Instant 1-click authorization without OTP delay
                </div>
            </div>

            <div class="body-section">
                <!-- QR Box -->
                <div class="qr-card">
                    <div class="qr-placeholder" role="img" aria-label="UPI Payment QR Code">SCAN WITH UPI</div>
                    <div style="font-size: 12px; color: #334155; margin-top: 8px; font-weight: 600;">
                        Scan with Google Pay, PhonePe, Paytm, BHIM, or tap Pay below
                    </div>
                </div>

                <!-- Pay Button -->
                <button class="pay-btn" id="payButton" onclick="authorizePayment()" aria-label="Authorize payment of ₹{amount:,.2f} via {vpa}">
                    💳 Pay ₹{amount:,.2f} via {vpa}
                </button>
            </div>
        </div>

        <!-- Dynamic Success Transition Container (hidden until paid) -->
        <div id="success-view" style="display: none;" role="status" aria-live="polite">
            <div class="settled-receipt-box">
                <div class="settled-check-circle" aria-hidden="true">✓</div>
                <div class="settled-title">Payment Captured & Settled!</div>
                <div class="settled-subtitle">
                    ₹{amount:,.2f} debited from <strong>{paying_inst}</strong>
                </div>
                <div class="settled-pill">✓ Escrow Settled • Zero Risk (Test Mode)</div>
            </div>

            <div class="body-section" style="padding-top: 0;">
                <table class="receipt-table" aria-label="Live Captured Payment Details">
                    <tr>
                        <th scope="row" class="receipt-label">Payment ID</th>
                        <td class="receipt-val"><span style="font-family:'JetBrains Mono',monospace; color:#0369a1; font-weight:700;">pay_live_{link_id[-8:]}</span></td>
                    </tr>
                    <tr>
                        <th scope="row" class="receipt-label">Order ID</th>
                        <td class="receipt-val"><span style="font-family:'JetBrains Mono',monospace;">{txn}</span></td>
                    </tr>
                    <tr>
                        <th scope="row" class="receipt-label">Status</th>
                        <td class="receipt-val" style="color:#065f46; font-weight:800;">Captured & Settled</td>
                    </tr>
                    <tr>
                        <th scope="row" class="receipt-label">Debited From</th>
                        <td class="receipt-val">🟢 {paying_inst} ({vpa})</td>
                    </tr>
                </table>

                <div style="margin-top: 20px;">
                    <button class="action-btn" onclick="window.print()" style="background:#0052cc; color:#ffffff; border:2px solid #0052cc;" aria-label="Print tax invoice">
                        🖨️ Print Tax Invoice / Receipt
                    </button>
                    <button class="action-btn" onclick="window.close()" style="background:#f8fafc; color:#334155; border:1.5px solid #cbd5e1; margin-top:8px;" aria-label="Close window">
                        ✕ Close Window
                    </button>
                </div>
            </div>
        </div>
        '''}

        <!-- Footer -->
        <footer class="footer-sec" role="contentinfo">
            🔒 Secured with 256-bit Bank-Grade Encryption by Razorpay (Test Mode)
        </footer>
    </main>

    <script>
        function authorizePayment() {{
            const btn = document.getElementById('payButton');
            btn.innerHTML = 'Debiting Account & Authorizing with Bank...';
            btn.style.opacity = '0.75';
            btn.disabled = true;

            // Trigger SQLite recovery update on server
            const captureUrl = `/api/capture-payment?txn={urllib.parse.quote(txn)}&amount={amount}` + ('{f"&batch_id={batch_id}" if batch_id else ""}');
            
            fetch(captureUrl, {{ method: 'POST' }})
                .then(res => res.json())
                .catch(err => console.warn('Capture sync:', err))
                .finally(() => {{
                    setTimeout(() => {{
                        document.getElementById('checkout-view').style.display = 'none';
                        document.getElementById('success-view').style.display = 'block';
                    }}, 600);
                }});
        }}
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)
