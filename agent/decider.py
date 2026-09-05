"""
Decider Agent: Intervention Selection & Strategy Planner

Maps root cause diagnosis and transaction context to exactly ONE bounded
recovery action from a strictly enforced closed action vocabulary:
- "send_new_payment_link"
- "send_reminder_alt_method"
- "send_gentle_nudge"
- "escalate_to_human"
- "no_action"

Never invents actions outside the bounded set; enforces strict Pydantic typing.
"""

import os
from typing import Literal
from pydantic import BaseModel, Field

ActionType = Literal[
    "send_new_payment_link",
    "send_reminder_alt_method",
    "send_gentle_nudge",
    "escalate_to_human",
    "no_action"
]

DEFAULT_HIGH_VALUE_THRESHOLD = 10000.0

class DecisionResult(BaseModel):
    action: ActionType = Field(description="Strictly bounded recovery action")
    reasoning: str = Field(description="Auditable business and strategic rationale for selected action")
    channel_suggested: Literal["payment_link", "sms_notification", "whatsapp_nudge", "concierge_ticket", "none"]
    priority: Literal["low", "medium", "high", "urgent"]

def decide_action(
    transaction: dict,
    diagnosis: dict,
    high_value_threshold: float = None
) -> dict:
    """
    Decides the optimal bounded recovery intervention for a transaction given its diagnosis.
    Returns dictionary conforming to DecisionResult schema.
    """
    if high_value_threshold is None:
        try:
            high_value_threshold = float(os.getenv("HIGH_VALUE_THRESHOLD", DEFAULT_HIGH_VALUE_THRESHOLD))
        except ValueError:
            high_value_threshold = DEFAULT_HIGH_VALUE_THRESHOLD

    amount = float(transaction.get("amount", 0.0))
    prior_reminders = int(transaction.get("prior_reminder_count", 0))
    cause = diagnosis.get("cause", "unknown")
    method = transaction.get("method", "card").lower()

    # Rule 1: Customer Contact Fatigue Boundary (Max 2 prior reminders)
    if prior_reminders >= 2:
        decision = DecisionResult(
            action="no_action",
            reasoning=f"Anti-fatigue policy triggered: customer already received {prior_reminders} prior reminders. Suppressing further automated outreach.",
            channel_suggested="none",
            priority="low"
        )
        return decision.model_dump()

    # Rule 2: High-Value VIP Transaction Boundary (> threshold, default ₹10,000)
    # VIP transactions must never receive automated bulk reminders; require personal concierge outreach
    if amount >= high_value_threshold:
        decision = DecisionResult(
            action="escalate_to_human",
            reasoning=f"High basket value (₹{amount:,.2f} >= threshold ₹{high_value_threshold:,.2f}). Escalated to merchant VIP concierge to preserve customer relationship.",
            channel_suggested="concierge_ticket",
            priority="urgent"
        )
        return decision.model_dump()

    # Rule 3: Strategy Mapping by Diagnosed Root Cause
    if cause == "checkout_timeout":
        decision = DecisionResult(
            action="send_new_payment_link",
            reasoning="Payment link or session timed out. Issuing a fresh, friction-free Razorpay payment link with 30-minute validity.",
            channel_suggested="payment_link",
            priority="high"
        )
    elif cause == "payment_method_failure":
        alt_suggestion = "UPI / Instant Netbanking" if method == "card" else "Cards / Netbanking"
        decision = DecisionResult(
            action="send_reminder_alt_method",
            reasoning=f"Initial payment failed on {method.upper()}. Recommending alternative payment rail ({alt_suggestion}) with direct payment link.",
            channel_suggested="sms_notification",
            priority="high"
        )
    elif cause == "otp_abandonment":
        decision = DecisionResult(
            action="send_reminder_alt_method",
            reasoning="Customer abandoned during 3DS/SMS OTP step. Proposing UPI Intent or QR payment to bypass telecom OTP delays.",
            channel_suggested="whatsapp_nudge",
            priority="medium"
        )
    elif cause == "price_hesitation":
        decision = DecisionResult(
            action="send_gentle_nudge",
            reasoning="Cart abandoned due to idle price deliberation. Sending reassuring cart preservation nudge without discounting (avoids training customers to abandon).",
            channel_suggested="whatsapp_nudge",
            priority="medium"
        )
    else:  # unknown or unclassifiable
        decision = DecisionResult(
            action="no_action",
            reasoning=f"Drop-off cause '{cause}' is ambiguous or unrecoverable. Withholding intervention to prevent negative customer experience.",
            channel_suggested="none",
            priority="low"
        )

    return decision.model_dump()
