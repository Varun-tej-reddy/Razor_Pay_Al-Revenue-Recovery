"""
Guardrail Agent: Compliance, Anti-Fatigue & Risk Boundary Layer

Evaluates proposed recovery interventions against strict compliance invariants:
1. Consent & Opt-Out: Strict block if opt_out is True.
2. Batch Deduplication: Blocks duplicate interventions for the same transaction.
3. High-Value Safeguard: Hard block on automated recovery for amounts > ₹10,000 (only escalate_to_human permitted).
4. Contact Fatigue Limit: Max 2 prior touches per customer.
5. Do-Not-Disturb (DND) Window: No automated customer outreach between 9:00 PM and 8:00 AM IST (UTC+5:30).

Every evaluation produces a non-nullable compliance audit log entry.
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

DEFAULT_HIGH_VALUE_THRESHOLD = 10000.0
# IST offset is UTC + 5 hours 30 minutes
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

def get_ist_time(dt: Optional[datetime] = None) -> datetime:
    """Converts a datetime to Indian Standard Time (IST)."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST_OFFSET)

def check_guardrails(
    transaction: dict,
    proposed_action: dict,
    seen_transactions: Optional[set] = None,
    current_time: Optional[datetime] = None,
    high_value_threshold: Optional[float] = None
) -> dict:
    """
    Evaluates proposed action against compliance and safety guardrails.
    Returns:
    {
        "approved": bool,
        "block_reason": str or None,
        "guardrail_rule": str,
        "audit_note": str
    }
    """
    action = proposed_action.get("action", "no_action")
    amount = float(transaction.get("amount", 0.0))
    txn_id = transaction.get("transaction_id", "unknown_txn")
    prior_reminders = int(transaction.get("prior_reminder_count", 0))
    opt_out = bool(transaction.get("opt_out", False))

    if high_value_threshold is None:
        try:
            high_value_threshold = float(os.getenv("HIGH_VALUE_THRESHOLD", DEFAULT_HIGH_VALUE_THRESHOLD))
        except ValueError:
            high_value_threshold = DEFAULT_HIGH_VALUE_THRESHOLD

    # If action is already "no_action", approve immediately without outreach risk
    if action == "no_action":
        return {
            "approved": True,
            "block_reason": None,
            "guardrail_rule": "no_action_passthrough",
            "audit_note": "No active customer intervention requested; compliant by default."
        }

    # 1. Opt-Out & Regulatory Consent Check
    if opt_out:
        return {
            "approved": False,
            "block_reason": "Customer has explicitly opted out of automated recovery communications.",
            "guardrail_rule": "opt_out_compliance",
            "audit_note": f"Blocked outreach to {txn_id}: customer consent status is opt_out=True."
        }

    # 2. Batch Run Deduplication Check
    if seen_transactions is not None and txn_id in seen_transactions:
        return {
            "approved": False,
            "block_reason": f"Duplicate intervention detected for transaction '{txn_id}' in current batch run.",
            "guardrail_rule": "batch_deduplication",
            "audit_note": f"Blocked redundant action '{action}' on already processed transaction {txn_id}."
        }

    # 3. High-Value Financial Protection Policy (> ₹10,000)
    # Hard rule: automated bots/messages must NEVER trigger on high-value orders; only human escalation is permitted
    if amount > high_value_threshold and action != "escalate_to_human":
        return {
            "approved": False,
            "block_reason": (
                f"Automated action '{action}' prohibited for high-value basket "
                f"(₹{amount:,.2f} > ₹{high_value_threshold:,.2f}). Hard policy mandates 'escalate_to_human'."
            ),
            "guardrail_rule": "high_value_automated_action_block",
            "audit_note": f"Violated high-value safety threshold; redirected to risk review."
        }

    # 4. Anti-Fatigue Customer Contact Cap (Max 2 prior touches)
    if prior_reminders >= 2:
        return {
            "approved": False,
            "block_reason": (
                f"Customer contact fatigue cap reached (prior_reminders={prior_reminders} >= 2). "
                f"Further automated touches prohibited."
            ),
            "guardrail_rule": "contact_frequency_cap",
            "audit_note": f"Blocked outreach: customer already received {prior_reminders} touchpoints."
        }

    # 5. Do-Not-Disturb (DND) Window (9:00 PM to 8:00 AM IST)
    # Prohibits customer-facing notifications during unsociable hours.
    # Note: internal merchant tickets ('escalate_to_human') are exempt from customer DND.
    if action in ("send_new_payment_link", "send_reminder_alt_method", "send_gentle_nudge"):
        ist_time = get_ist_time(current_time)
        hour = ist_time.hour
        if hour >= 21 or hour < 8:
            return {
                "approved": False,
                "block_reason": (
                    f"Do-Not-Disturb (DND) restriction active. Time in IST is {ist_time.strftime('%I:%M %p')} "
                    f"(prohibited window: 9:00 PM to 8:00 AM IST)."
                ),
                "guardrail_rule": "dnd_window_ist",
                "audit_note": f"Blocked customer notification during night hours ({ist_time.strftime('%H:%M')} IST)."
            }

    # All compliance invariants satisfied
    return {
        "approved": True,
        "block_reason": None,
        "guardrail_rule": "all_compliance_checks_passed",
        "audit_note": f"Action '{action}' fully compliant with consent, fatigue, DND, and risk constraints."
    }
