from datetime import datetime, timezone, timedelta
from agent.guardrail import check_guardrails, IST_OFFSET

# Helper datetime for daytime in IST: 2:00 PM IST (08:30 UTC)
DAYTIME_UTC = datetime(2026, 9, 4, 8, 30, 0, tzinfo=timezone.utc)
# Nighttime in IST: 11:30 PM IST (18:00 UTC)
NIGHTTIME_UTC = datetime(2026, 9, 4, 18, 0, 0, tzinfo=timezone.utc)

def test_guardrail_clean_approval():
    txn = {
        "transaction_id": "txn_ok_001",
        "amount": 2499.0,
        "prior_reminder_count": 0,
        "opt_out": False
    }
    action = {"action": "send_new_payment_link"}
    res = check_guardrails(txn, action, current_time=DAYTIME_UTC)
    assert res["approved"] is True
    assert res["block_reason"] is None
    assert res["guardrail_rule"] == "all_compliance_checks_passed"

def test_guardrail_block_opt_out():
    txn = {
        "transaction_id": "txn_optout_002",
        "amount": 1500.0,
        "prior_reminder_count": 0,
        "opt_out": True
    }
    action = {"action": "send_new_payment_link"}
    res = check_guardrails(txn, action, current_time=DAYTIME_UTC)
    assert res["approved"] is False
    assert "opted out" in res["block_reason"].lower()
    assert res["guardrail_rule"] == "opt_out_compliance"

def test_guardrail_block_deduplication():
    txn = {
        "transaction_id": "txn_dup_003",
        "amount": 1500.0,
        "prior_reminder_count": 0,
        "opt_out": False
    }
    action = {"action": "send_gentle_nudge"}
    seen = {"txn_dup_003"}
    res = check_guardrails(txn, action, seen_transactions=seen, current_time=DAYTIME_UTC)
    assert res["approved"] is False
    assert "duplicate" in res["block_reason"].lower()
    assert res["guardrail_rule"] == "batch_deduplication"

def test_guardrail_block_high_value_automated_action():
    # Trying to send automated payment link on a ₹25,000 order
    txn = {
        "transaction_id": "txn_highval_004",
        "amount": 25000.0,
        "prior_reminder_count": 0,
        "opt_out": False
    }
    action = {"action": "send_new_payment_link"}
    res = check_guardrails(txn, action, current_time=DAYTIME_UTC, high_value_threshold=10000.0)
    assert res["approved"] is False
    assert "high-value" in res["block_reason"].lower()
    assert res["guardrail_rule"] == "high_value_automated_action_block"

    # But escalate_to_human IS permitted for high-value orders
    action_human = {"action": "escalate_to_human"}
    res_human = check_guardrails(txn, action_human, current_time=DAYTIME_UTC, high_value_threshold=10000.0)
    assert res_human["approved"] is True

def test_guardrail_block_contact_fatigue():
    txn = {
        "transaction_id": "txn_fatigue_005",
        "amount": 999.0,
        "prior_reminder_count": 2,
        "opt_out": False
    }
    action = {"action": "send_reminder_alt_method"}
    res = check_guardrails(txn, action, current_time=DAYTIME_UTC)
    assert res["approved"] is False
    assert "fatigue" in res["block_reason"].lower() or "exceeded" in res["block_reason"].lower()
    assert res["guardrail_rule"] == "contact_frequency_cap"

def test_guardrail_block_dnd_window_ist():
    txn = {
        "transaction_id": "txn_dnd_006",
        "amount": 1999.0,
        "prior_reminder_count": 0,
        "opt_out": False
    }
    action = {"action": "send_new_payment_link"}
    res = check_guardrails(txn, action, current_time=NIGHTTIME_UTC)
    assert res["approved"] is False
    assert "do-not-disturb" in res["block_reason"].lower() or "dnd" in res["block_reason"].lower()
    assert res["guardrail_rule"] == "dnd_window_ist"
