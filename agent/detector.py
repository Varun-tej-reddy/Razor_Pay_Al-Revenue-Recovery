"""
Detector Agent: Rule-Based At-Risk Checkout Identification

Scans incoming raw checkout transaction records and flags transactions that
represent recoverable revenue at risk.
Criteria:
- Checkout was initiated but not completed in a terminal successful state (status != 'paid', 'refunded')
- Occurred within the actionable recovery window (default: within 72 hours of reference time)
- Has not exceeded the unrecoverable staleness boundary (> 72 hours)

Deterministic and 100% auditable.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

# Maximum recovery eligibility window (in hours)
DEFAULT_RECOVERY_WINDOW_HOURS = 72.0

def parse_iso_datetime(dt_str: str) -> datetime:
    """Parses ISO-8601 string, ensuring timezone-aware UTC datetime."""
    # Strip trailing Z if present and treat as UTC
    clean_str = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def evaluate_transaction_risk(
    txn: dict,
    reference_time: Optional[datetime] = None,
    max_window_hours: float = DEFAULT_RECOVERY_WINDOW_HOURS
) -> tuple[bool, str]:
    """
    Evaluates whether a single transaction represents recoverable revenue at risk.
    Returns (is_at_risk, risk_reason).
    """
    last_status = txn.get("last_status", "").lower()
    
    # Terminal successful or settled transactions are never at risk
    if last_status in ("paid", "refunded", "settled", "captured"):
        return False, "terminal_successful_payment"

    # Evaluate transaction age and recovery eligibility window
    created_at_str = txn.get("created_at")
    if created_at_str:
        created_dt = parse_iso_datetime(created_at_str)
        ref_dt = reference_time or datetime.now(timezone.utc)
        if ref_dt.tzinfo is None:
            ref_dt = ref_dt.replace(tzinfo=timezone.utc)
            
        age_hours = (ref_dt - created_dt).total_seconds() / 3600.0
        
        # Transactions older than recovery window are stale / unrecoverable
        if age_hours > max_window_hours:
            return False, f"past_recovery_window_stale_{age_hours:.1f}h"

    # Analyze status and history for explicit recoverable patterns
    history = txn.get("status_history", [])
    history_statuses = [h.get("status", "").lower() for h in history]

    if last_status == "failed" or "failed" in history_statuses:
        return True, "failed_payment_retryable"

    if last_status == "expired" or "expired" in history_statuses:
        return True, "payment_link_expired_unpaid"

    if "abandoned_at_otp" in history_statuses or "otp_requested" in history_statuses:
        return True, "checkout_abandoned_otp"

    if "idle_abandonment" in history_statuses or "viewed_payment_options" in history_statuses:
        return True, "checkout_idle_hesitation"

    if last_status in ("attempted", "pending", "issued", "created"):
        return True, "checkout_incomplete_abandoned"

    return False, "unknown_terminal_or_non_recoverable"

def detect_at_risk(
    batch: list[dict],
    reference_time: Optional[datetime] = None,
    max_window_hours: float = DEFAULT_RECOVERY_WINDOW_HOURS
) -> list[dict]:
    """
    Scans a batch of transactions and returns deep-copied records flagged as at-risk,
    each enriched with 'risk_reason' and 'is_at_risk'.
    """
    flagged_records = []
    for txn in batch:
        is_risk, reason = evaluate_transaction_risk(
            txn,
            reference_time=reference_time,
            max_window_hours=max_window_hours
        )
        if is_risk:
            flagged = deepcopy(txn)
            flagged["is_at_risk"] = True
            flagged["risk_reason"] = reason
            flagged_records.append(flagged)
            
    return flagged_records
