from agent.decider import decide_action

def test_decide_action_expired_timeout():
    txn = {"amount": 1499.0, "prior_reminder_count": 0, "method": "card"}
    diag = {"cause": "checkout_timeout"}
    res = decide_action(txn, diag)
    assert res["action"] == "send_new_payment_link"
    assert "fresh" in res["reasoning"].lower() or "payment link" in res["reasoning"].lower()

def test_decide_action_payment_failure_alt_method():
    txn = {"amount": 2500.0, "prior_reminder_count": 0, "method": "card"}
    diag = {"cause": "payment_method_failure"}
    res = decide_action(txn, diag)
    assert res["action"] == "send_reminder_alt_method"
    assert "upi" in res["reasoning"].lower()

def test_decide_action_otp_abandonment_alt_method():
    txn = {"amount": 1800.0, "prior_reminder_count": 1, "method": "card"}
    diag = {"cause": "otp_abandonment"}
    res = decide_action(txn, diag)
    assert res["action"] == "send_reminder_alt_method"

def test_decide_action_price_hesitation():
    txn = {"amount": 999.0, "prior_reminder_count": 0, "method": "upi"}
    diag = {"cause": "price_hesitation"}
    res = decide_action(txn, diag)
    assert res["action"] == "send_gentle_nudge"
    assert "without discounting" in res["reasoning"].lower()

def test_decide_action_high_value_escalation():
    txn = {"amount": 15000.0, "prior_reminder_count": 0, "method": "card"}
    diag = {"cause": "checkout_timeout"}
    res = decide_action(txn, diag)
    assert res["action"] == "escalate_to_human"
    assert "vip" in res["reasoning"].lower() or "concierge" in res["reasoning"].lower()

def test_decide_action_prior_reminders_cap():
    txn = {"amount": 1200.0, "prior_reminder_count": 2, "method": "upi"}
    diag = {"cause": "payment_method_failure"}
    res = decide_action(txn, diag)
    assert res["action"] == "no_action"
    assert "anti-fatigue" in res["reasoning"].lower()

def test_decide_action_unknown_cause():
    txn = {"amount": 1200.0, "prior_reminder_count": 0, "method": "upi"}
    diag = {"cause": "unknown"}
    res = decide_action(txn, diag)
    assert res["action"] == "no_action"
