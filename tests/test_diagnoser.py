import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from agent.diagnoser import diagnose, DiagnosisOutput

def test_diagnose_rule_resolved_failure():
    txn = {
        "transaction_id": "pay_test_001",
        "last_status": "failed",
        "status_history": [
            {"status": "created"},
            {
                "status": "failed",
                "error_code": "BAD_REQUEST_PAYMENT_DECLINED",
                "error_description": "Card issuing bank declined transaction"
            }
        ]
    }
    result = diagnose(txn)
    assert result["cause"] == "payment_method_failure"
    assert result["method"] == "rule"
    assert result["confidence"] >= 0.95
    assert "payment_declined" in result["reasoning"].lower() or "bad_request" in result["reasoning"].lower()

def test_diagnose_rule_resolved_expired():
    txn = {
        "transaction_id": "pay_test_002",
        "last_status": "expired",
        "status_history": [
            {"status": "issued"},
            {"status": "expired"}
        ]
    }
    result = diagnose(txn)
    assert result["cause"] == "checkout_timeout"
    assert result["method"] == "rule"
    assert result["confidence"] >= 0.90

def test_diagnose_llm_fallback_with_mocked_llm():
    # Ambiguous transaction that rules cannot definitively resolve
    txn = {
        "transaction_id": "pay_test_003",
        "last_status": "attempted",
        "status_history": [
            {"status": "created", "details": "Customer opened checkout link"},
            {"status": "viewed_payment_options", "details": "Viewed payment methods"}
        ]
    }

    mock_json = (
        '{"cause": "price_hesitation", "confidence": 0.86, '
        '"reasoning": "Mocked LLM identified hesitation at final billing page.", '
        '"signals_detected": ["cart_dwell", "price_check"]}'
    )
    mock_runnable = RunnableLambda(lambda _: AIMessage(content=mock_json))

    result = diagnose(txn, llm_override=mock_runnable)
    assert result["method"] == "llm"
    assert result["cause"] == "price_hesitation"
    assert result["confidence"] == 0.86
    assert "Mocked LLM" in result["reasoning"]
    assert "cart_dwell" in result["signals_detected"]

def test_diagnose_llm_fallback_heuristic_offline():
    # Without API key or mock, our robust heuristic LangChain fallback kicks in
    txn = {
        "transaction_id": "pay_test_004",
        "last_status": "attempted",
        "pattern_type": "abandoned_at_otp",
        "status_history": [
            {"status": "created"},
            {"status": "otp_requested"}
        ]
    }
    result = diagnose(txn)
    assert result["method"] == "llm"
    assert result["cause"] == "otp_abandonment"
    assert result["confidence"] > 0.8
