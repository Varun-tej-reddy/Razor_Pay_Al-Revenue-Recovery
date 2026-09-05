"""
Unit & Integration Tests for Track 03 Expansion Suite:
- B2B Receivables Chaser & Overdue Invoice Engine
- Hinglish Conversational AI Recovery Bot & Voice Recovery Simulator
- Promise-to-Pay (PTP) Commitment Tracker
- Mandate Retry Sequencer (Subscriptions & UPI AutoPay)
- Corresponding REST Endpoints in FastAPI
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from agent.b2b_chaser import (
    load_b2b_invoices,
    compute_b2b_aging_metrics,
    execute_b2b_chase_action
)
from agent.hinglish_bot import process_hinglish_chat, parse_ptp_intent
from agent.mandate_sequencer import (
    generate_mandate_retry_schedule,
    get_all_subscription_mandates
)
from storage.db import (
    init_db,
    insert_promise_to_pay,
    get_promises_to_pay,
    update_promise_to_pay_status
)

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    init_db()

# --- 1. B2B Receivables Chaser Tests ---
def test_b2b_invoices_loading():
    invoices = load_b2b_invoices()
    assert len(invoices) >= 10
    first = invoices[0]
    assert "invoice_id" in first
    assert "company_name" in first
    assert "gst_input_credit_amount" in first
    assert first["invoice_amount"] > 0

def test_b2b_aging_metrics():
    metrics = compute_b2b_aging_metrics()
    assert metrics["total_invoices"] >= 10
    assert metrics["total_overdue_capital"] > 0
    assert metrics["total_gst_credit_at_risk"] > 0
    assert "1_15_days" in metrics["buckets"]
    assert "16_30_days" in metrics["buckets"]
    assert "30_plus_days" in metrics["buckets"]

def test_b2b_chase_actions():
    # Test GST Section 16(2) warning
    res_gst = execute_b2b_chase_action("INV-2024-8801", "send_gst_warning")
    assert res_gst["success"] is True
    assert "Section 16(2)" in res_gst["message_dispatched"]

    # Test 2% cash discount
    res_disc = execute_b2b_chase_action("INV-2024-8802", "apply_cash_discount")
    assert res_disc["success"] is True
    assert res_disc["discount_amount"] > 0
    assert res_disc["discounted_amount"] < 84500.0

    # Test Statement of Account (SOA)
    res_soa = execute_b2b_chase_action("INV-2024-8803", "send_soa")
    assert res_soa["success"] is True
    assert "STATEMENT OF ACCOUNT" in res_soa["soa_content"]

# --- 2. Hinglish Bot & Intent Parsing Tests ---
def test_hinglish_intent_technical_otp():
    res = process_hinglish_chat("OTP nahi aaya bahut der se wait kar raha hu")
    assert res["detected_intent"] == "TECHNICAL_ISSUE_OTP"
    assert "1-Click Biometric" in res["reply"]
    assert "voice_synthesis_script" in res

def test_hinglish_intent_discount_negotiation():
    res = process_hinglish_chat("kuch discount milega kya agar abhi pay karein?")
    assert res["detected_intent"] == "DISCOUNT_NEGOTIATION"
    assert "2% instant" in res["reply"] or "2% discount" in res["reply"]

def test_hinglish_intent_not_interested_offers_discount():
    res = process_hinglish_chat(
        "bohot mehenga lag raha hai, abhi nahi lena mujhe drop kar do",
        context={"customer_name": "Rohan", "amount": 4000.0}
    )
    assert res["detected_intent"] == "DISCOUNT_NEGOTIATION"
    assert "2% instant" in res["reply"] or "Save ₹80.00" in res["reply"] or "2%" in res["reply"]

def test_hinglish_ptp_intent_and_auto_booking():
    res = process_hinglish_chat(
        "kal subah 10 baje pakka pay kar dunga",
        context={"customer_name": "Sharma Ji", "amount": 5500.0, "transaction_id": "txn_ptp_unit_01"}
    )
    assert res["detected_intent"] == "PROMISE_TO_PAY"
    assert "Promise-to-Pay" in res["reply"] or "PTP" in res["reply"]
    assert res["ptp_commitment"] is not None
    assert res["ptp_commitment"]["amount"] == 5500.0
    # Strict margin protection: No discount offered to willing buyers!
    assert "2% instant" not in res["reply"]
    assert "discount" not in res["reply"].lower()

# --- 3. Promise to Pay (PTP) Ledger Tests ---
def test_ptp_lifecycle():
    ptp_entry = insert_promise_to_pay({
        "transaction_id": "txn_test_ptp_lifecycle",
        "customer_id": "cust_lifecycle",
        "customer_name": "Arjun Kapoor",
        "amount": 7800.0,
        "ptp_date": "2026-09-07 11:00 AM IST",
        "status": "scheduled",
        "channel": "hinglish_chat",
        "notes": "Promised via Hinglish bot"
    })
    assert ptp_entry.id is not None

    # Retrieve PTPs
    all_ptp = get_promises_to_pay()
    assert any(p["transaction_id"] == "txn_test_ptp_lifecycle" for p in all_ptp)

    # Update PTP status to honored
    success = update_promise_to_pay_status(ptp_entry.id, "honored")
    assert success is True

# --- 4. Mandate Retry Sequencer Tests ---
def test_mandate_sequencer_schedule():
    res = generate_mandate_retry_schedule("sub_enterprise_091")
    assert "subscription" in res
    assert len(res["recommended_sequencing"]) == 4
    # Verify off-peak window is in step 2
    step_2 = res["recommended_sequencing"][1]
    assert "06:00 AM IST" in step_2["time_slot"]
    # Verify salary cycle is handled in step 3
    step_3 = res["recommended_sequencing"][2]
    assert "Salary" in step_3["time_slot"] or "Salary" in step_3["action"]

# --- 5. API Endpoints Integration Tests ---
def test_api_b2b_endpoints():
    res = client.get("/api/b2b/invoices")
    assert res.status_code == 200
    data = res.json()
    assert "metrics" in data
    assert "invoices" in data

    res_chase = client.post("/api/b2b/chase", json={
        "invoice_id": "INV-2024-8804",
        "action_type": "send_gst_warning"
    })
    assert res_chase.status_code == 200
    assert res_chase.json()["success"] is True

def test_api_hinglish_chat_endpoint():
    res = client.post("/api/chat/hinglish", json={
        "message": "kaha pay kare link bhejo",
        "customer_name": "Vikram",
        "amount": 2499.00,
        "transaction_id": "pay_test_api_01"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Razorpay secure checkout link" in data["reply"]
    assert data["detected_intent"] == "PAYMENT_LINK_REQUEST"

def test_api_ptp_endpoints():
    res = client.get("/api/ptp")
    assert res.status_code == 200
    assert "records" in res.json()

    res_create = client.post("/api/ptp", json={
        "transaction_id": "txn_api_ptp_99",
        "customer_id": "cust_api_99",
        "customer_name": "Kavita Nair",
        "amount": 4200.0,
        "ptp_date": "2026-09-08 03:00 PM IST"
    })
    assert res_create.status_code == 200
    ptp_id = res_create.json()["ptp"]["id"]

    res_status = client.post(f"/api/ptp/{ptp_id}/status?new_status=honored")
    assert res_status.status_code == 200
    assert res_status.json()["new_status"] == "honored"

def test_api_mandates_schedule_endpoint():
    res = client.get("/api/mandates/schedule?subscription_id=sub_saas_042")
    assert res.status_code == 200
    data = res.json()
    assert "schedule" in data
    assert "all_mandates" in data
