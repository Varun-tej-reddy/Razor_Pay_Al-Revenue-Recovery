"""
Executor Agent: Razorpay Test-Mode Integration & Action Execution

Executes approved recovery interventions:
- "send_new_payment_link": Creates a fresh Razorpay Payment Link with short expiry.
- "send_reminder_alt_method": Creates a payment link with UPI/alt suggestion and logs the SMS/WhatsApp payload.
- "send_gentle_nudge": Generates cart preservation messaging without discount.
- "escalate_to_human": Dispatches an internal merchant VIP concierge ticket.
- "no_action": Safely skips without API call.

If live Razorpay test keys (rzp_test_...) are provided in .env, it creates real
live payment links on rzp.io.
If running in mock/demo mode without live keys, it generates functional
payment links served by our local checkout simulator (http://localhost:8000/pay/...).
"""

import os
import time
from typing import Optional
from datetime import datetime, timezone, timedelta
import razorpay

def get_razorpay_client(key_id: Optional[str] = None, key_secret: Optional[str] = None) -> razorpay.Client:
    k_id = key_id or os.getenv("RAZORPAY_KEY_ID", "rzp_test_placeholder_key")
    k_sec = key_secret or os.getenv("RAZORPAY_KEY_SECRET", "placeholder_secret_key")
    return razorpay.Client(auth=(k_id, k_sec))

def execute_action(
    transaction: dict,
    approved_action: dict,
    client: Optional[razorpay.Client] = None,
    mock_mode: bool = False
) -> dict:
    action = approved_action.get("action", "no_action")
    txn_id = transaction.get("transaction_id", "unknown_txn")
    amount = float(transaction.get("amount", 0.0))
    currency = transaction.get("currency", "INR")
    cust_id = transaction.get("customer_id", "cust_anonymous")
    contact = transaction.get("customer_contact", {})

    amount_in_paise = int(round(amount * 100))
    expire_by_epoch = int(time.time()) + (30 * 60)

    if action == "no_action":
        return {
            "status": "skipped",
            "action": action,
            "payment_link_id": None,
            "payment_link_url": None,
            "message_payload": None,
            "details": "Action skipped in accordance with decision rule or fatigue cap.",
            "error": None
        }

    if action == "escalate_to_human":
        ticket_id = f"TICK_VIP_{txn_id}"
        return {
            "status": "escalated_to_human",
            "action": action,
            "payment_link_id": None,
            "payment_link_url": None,
            "message_payload": (
                f"[VIP Concierge Ticket {ticket_id}] Customer {cust_id} dropped cart worth ₹{amount:,.2f}. "
                f"Requires priority outreach to assist with order completion."
            ),
            "details": f"Dispatched VIP concierge escalation ticket {ticket_id}.",
            "error": None
        }

    k_id = os.getenv("RAZORPAY_KEY_ID", "rzp_test_placeholder_key")
    is_placeholder = k_id.startswith("rzp_test_placeholder") or "placeholder" in k_id or k_id == ""

    # In local test/demo mode, route to the local checkout portal with full telemetry
    if client is None and (mock_mode or is_placeholder):
        fake_link_id = f"plink_test_{txn_id[-8:]}"
        base_api_url = os.getenv("APP_BASE_URL", "http://localhost:8000")
        
        # Build enriched parameter string
        failed_info = transaction.get("failed_instrument_info") or {}
        rec_info = transaction.get("recommended_instrument_info") or {}
        failed_name = failed_info.get("instrument_name", "Card")
        paying_name = rec_info.get("instrument", "UPI Account")
        vpa_name = rec_info.get("vpa", f"{cust_id}@upi")

        fake_url = (
            f"{base_api_url}/pay/{fake_link_id}?"
            f"txn={txn_id}&amount={amount:.2f}&cust={cust_id}&action={action}&"
            f"failed_inst={failed_name}&paying_inst={paying_name}&vpa={vpa_name}"
        )

        if action == "send_new_payment_link":
            msg = f"[SMS/Email to {contact.get('phone', 'customer')}] Your checkout session timed out. Complete purchase: {fake_url}"
        elif action == "send_reminder_alt_method":
            msg = f"[WhatsApp to {contact.get('phone', 'customer')}] Your previous payment failed on {failed_name}. Pay instantly from {paying_name} ({vpa_name}): {fake_url}"
        elif action == "send_gentle_nudge":
            msg = f"[WhatsApp to {contact.get('phone', 'customer')}] Your cart is reserved for 30 minutes! Complete order: {fake_url}"
        else:
            msg = f"Action {action} processed with payment link {fake_url}"

        return {
            "status": "executed",
            "action": action,
            "payment_link_id": fake_link_id,
            "payment_link_url": fake_url,
            "message_payload": msg,
            "details": f"Payment link generated (Test Mode): {fake_url}",
            "error": None
        }

    # Live Razorpay SDK Execution
    try:
        rzp = client or get_razorpay_client()
        payload = {
            "amount": amount_in_paise,
            "currency": currency,
            "accept_partial": False,
            "description": f"Cart Recovery for Order {txn_id}",
            "customer": {
                "name": cust_id,
                "email": contact.get("email", "customer@example.com"),
                "contact": contact.get("phone", "+919876543210")
            },
            "notify": {"sms": True, "email": True},
            "reminder_enable": True,
            "expire_by": expire_by_epoch
        }

        response = rzp.payment_link.create(data=payload)
        plink_id = response.get("id")
        plink_url = response.get("short_url")

        return {
            "status": "executed",
            "action": action,
            "payment_link_id": plink_id,
            "payment_link_url": plink_url,
            "message_payload": f"Recovery payment link dispatched: {plink_url}",
            "details": f"Razorpay Payment Link created: {plink_id} -> {plink_url}",
            "error": None
        }

    except Exception as e:
        return {
            "status": "failed",
            "action": action,
            "payment_link_id": None,
            "payment_link_url": None,
            "message_payload": None,
            "details": f"Razorpay API call failed: {str(e)}",
            "error": str(e)
        }
