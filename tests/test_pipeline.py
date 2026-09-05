import pytest
import tempfile
import os
from datetime import datetime, timezone
from agent.pipeline import run_batch
from storage.db import get_audit_trail, get_audit_records

def test_pipeline_run_batch_end_to_end():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    db_url = f"sqlite:///{db_path}"
    test_time = datetime(2026, 9, 4, 9, 0, 0, tzinfo=timezone.utc)

    small_batch = [
        # 1. Paid control transaction (should not be flagged)
        {
            "transaction_id": "t_paid_1",
            "customer_id": "c_1",
            "amount": 2500.0,
            "currency": "INR",
            "last_status": "paid",
            "created_at": "2026-09-04T08:00:00Z",
            "status_history": [{"status": "created"}, {"status": "paid"}],
            "prior_reminder_count": 0,
            "opt_out": False
        },
        # 2. Failed payment with error code
        {
            "transaction_id": "t_failed_2",
            "customer_id": "c_2",
            "amount": 1800.0,
            "currency": "INR",
            "last_status": "failed",
            "created_at": "2026-09-04T08:10:00Z",
            "status_history": [
                {"status": "created"},
                {"status": "failed", "error_code": "BAD_REQUEST_PAYMENT_DECLINED"}
            ],
            "prior_reminder_count": 0,
            "opt_out": False
        },
        # 3. High value basket (> 10000)
        {
            "transaction_id": "t_vip_3",
            "customer_id": "c_3",
            "amount": 16000.0,
            "currency": "INR",
            "last_status": "expired",
            "created_at": "2026-09-04T08:15:00Z",
            "status_history": [{"status": "issued"}, {"status": "expired"}],
            "prior_reminder_count": 0,
            "opt_out": False
        },
        # 4. Opted-out customer
        {
            "transaction_id": "t_optout_4",
            "customer_id": "c_4",
            "amount": 3200.0,
            "currency": "INR",
            "last_status": "failed",
            "created_at": "2026-09-04T08:20:00Z",
            "status_history": [{"status": "failed", "error_code": "GATEWAY_TIMEOUT"}],
            "prior_reminder_count": 0,
            "opt_out": True
        }
    ]

    try:
        report = run_batch(
            transactions=small_batch,
            batch_id="test_pipeline_batch",
            db_url=db_url,
            current_time=test_time
        )

        assert report["summary"]["total_processed"] == 4
        assert report["summary"]["flagged_at_risk_count"] == 3  # t_paid_1 is not at risk
        assert report["summary"]["guardrail_blocked_count"] == 1  # t_optout_4 is blocked

        # Check audit trail row count
        df = get_audit_trail(batch_id="test_pipeline_batch", db_url=db_url)
        assert len(df) == 4

        # Check individual records
        paid_row = df[df["transaction_id"] == "t_paid_1"].iloc[0]
        assert paid_row["detector_flagged"] == False
        assert paid_row["execution_status"] == "not_flagged"

        vip_row = df[df["transaction_id"] == "t_vip_3"].iloc[0]
        assert vip_row["detector_flagged"] == True
        assert vip_row["proposed_action"] == "escalate_to_human"
        assert vip_row["execution_status"] == "escalated_to_human"

        optout_row = df[df["transaction_id"] == "t_optout_4"].iloc[0]
        assert optout_row["guardrail_approved"] == False
        assert optout_row["execution_status"] == "blocked"

        # Verify exceptions report
        assert report["exceptions_count"] >= 1
        exception_txns = [e["transaction_id"] for e in report["exceptions"]]
        assert "t_optout_4" in exception_txns

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
