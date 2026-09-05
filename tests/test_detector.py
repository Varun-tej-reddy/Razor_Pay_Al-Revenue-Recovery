from datetime import datetime, timezone, timedelta
from agent.detector import detect_at_risk, evaluate_transaction_risk

def test_clear_flag_failed_payment():
    ref_time = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    txn = {
        "transaction_id": "txn_001",
        "last_status": "failed",
        "created_at": (ref_time - timedelta(hours=2)).isoformat(),
        "status_history": [
            {"status": "created"},
            {"status": "failed", "error_code": "BAD_REQUEST_PAYMENT_DECLINED"}
        ]
    }
    is_risk, reason = evaluate_transaction_risk(txn, reference_time=ref_time)
    assert is_risk is True
    assert reason == "failed_payment_retryable"

    flagged = detect_at_risk([txn], reference_time=ref_time)
    assert len(flagged) == 1
    assert flagged[0]["transaction_id"] == "txn_001"
    assert flagged[0]["is_at_risk"] is True
    assert flagged[0]["risk_reason"] == "failed_payment_retryable"

def test_clear_non_flag_successful_payment():
    ref_time = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    txn = {
        "transaction_id": "txn_002",
        "last_status": "paid",
        "created_at": (ref_time - timedelta(hours=1)).isoformat(),
        "status_history": [
            {"status": "created"},
            {"status": "attempted"},
            {"status": "paid"}
        ]
    }
    is_risk, reason = evaluate_transaction_risk(txn, reference_time=ref_time)
    assert is_risk is False
    assert reason == "terminal_successful_payment"

    flagged = detect_at_risk([txn], reference_time=ref_time)
    assert len(flagged) == 0

def test_edge_case_past_recovery_window_stale():
    ref_time = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    # Created 100 hours ago (beyond 72-hour window)
    txn = {
        "transaction_id": "txn_003",
        "last_status": "failed",
        "created_at": (ref_time - timedelta(hours=100)).isoformat(),
        "status_history": [
            {"status": "created"},
            {"status": "failed"}
        ]
    }
    is_risk, reason = evaluate_transaction_risk(txn, reference_time=ref_time, max_window_hours=72)
    assert is_risk is False
    assert "past_recovery_window_stale" in reason

    flagged = detect_at_risk([txn], reference_time=ref_time, max_window_hours=72)
    assert len(flagged) == 0
