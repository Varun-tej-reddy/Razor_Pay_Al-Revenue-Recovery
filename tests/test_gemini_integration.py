import os
import pytest
from dotenv import load_dotenv

load_dotenv()

from agent.llm_client import get_gemini_api_key, call_gemini
from agent.hinglish_bot import process_hinglish_chat
from agent.ptp_supervisor import assess_ptp_credibility

def test_gemini_api_key_configured():
    key = get_gemini_api_key()
    assert key is not None
    assert len(key) > 20

def test_gemini_llm_call():
    res = call_gemini("Say: Gemini Online in 2 words")
    assert res["success"] is True
    assert len(res["text"]) > 0
    assert "gemini" in res["model"].lower()

def test_gemini_hinglish_chat_real_ai():
    ctx = {
        "customer_name": "Deepak Verma",
        "amount": 5500.0,
        "failed_instrument": "Kotak Mahindra Bank UPI",
        "failure_reason": "Bank switch timeout"
    }
    res = process_hinglish_chat("Bhai OTP nahi aaya, payment kaise karein?", context=ctx)
    assert len(res["reply"]) > 20
    assert res["detected_intent"] in ["TECHNICAL_ISSUE_OTP", "GENERAL_RECOVERY", "otp_issue"]

def test_gemini_ptp_extraction():
    ctx = {
        "customer_name": "Arjun Rao",
        "amount": 7500.0,
        "transaction_id": "txn_unit_test_ptp"
    }
    res = process_hinglish_chat("Kal sham 6 baje pakka pay kar dunga", context=ctx)
    assert res["ptp_detected"] is True
    assert res["ptp_commitment"] is not None
    assert res["ptp_commitment"]["amount"] == 7500.0

def test_ptp_supervisor_evaluation():
    record = {
        "customer_name": "Pooja Hegde",
        "amount": 14000.0,
        "ptp_date": "Tomorrow at 11:00 AM IST",
        "status": "scheduled",
        "notes": "Spoke via live voice call; promised prompt clearance"
    }
    res = assess_ptp_credibility(record)
    assert "credibility_score" in res
    assert res["risk_tier"] in ["Low", "Medium", "High"]
    assert "SUPPRESS" in res["dunning_directive"]
