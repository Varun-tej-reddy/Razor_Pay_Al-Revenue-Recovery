"""
Synthetic Transaction Batch Generator for AI Revenue Recovery System (Track 03)

Generates 60 production-grade checkout records with comprehensive payment instrument
telemetry (issuing bank, masked card/account, UPI VPAs, failure diagnostics, and
AI-recommended payment instruments).
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

BANKS = ["HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank", "Kotak Mahindra Bank"]
CARD_NETWORKS = ["Visa", "Mastercard", "RuPay"]
UPI_APPS = ["Google Pay", "PhonePe", "Paytm", "BHIM"]

def generate_batch(count: int = 60, seed: int = 42) -> list[dict]:
    random.seed(seed)
    base_time = datetime(2026, 9, 4, 10, 0, 0)

    patterns = (
        ["payment_failed"] * 15 +
        ["payment_link_expired"] * 12 +
        ["abandoned_at_otp"] * 9 +
        ["price_hesitation"] * 9 +
        ["successful"] * 15
    )
    random.shuffle(patterns)

    batch = []
    for i, pattern in enumerate(patterns, start=1):
        txn_id = f"pay_synth_{i:04d}"
        cust_id = f"cust_synth_{random.randint(100, 999)}"
        created_dt = base_time - timedelta(minutes=random.randint(20, 360))
        
        # High value variation (> ₹10,000 to test VIP concierge guardrail)
        if random.random() < 0.15:
            amount = round(random.uniform(11000.0, 38000.0), 2)
        else:
            amount = round(random.uniform(399.0, 8999.0), 2)

        bank = random.choice(BANKS)
        card_network = random.choice(CARD_NETWORKS)
        upi_app = random.choice(UPI_APPS)
        masked_card = f"•••• •••• •••• {random.randint(1000, 9999)}"
        masked_acct = f"•••• {random.randint(1000, 9999)}"
        upi_handle = f"user_{i}@{bank.split()[0].lower()}bank"

        method = random.choice(["card", "upi", "netbanking"])
        prior_reminders = random.choices([0, 1, 2], weights=[0.55, 0.30, 0.15])[0]
        opt_out = random.random() < 0.05

        status_history = []
        created_str = created_dt.isoformat() + "Z"
        status_history.append({
            "status": "created",
            "timestamp": created_str,
            "details": "Checkout initiated by customer"
        })

        failed_instrument_info = None
        recommended_instrument_info = {
            "method": "UPI",
            "instrument": f"{bank} Savings A/c ({masked_acct}) via {upi_app}",
            "vpa": upi_handle,
            "routing_reason": "Direct 1-click biometric authorization (0% SMS OTP latency, bypasses card rails)"
        }

        if pattern == "payment_failed":
            last_status = "failed"
            error_type = random.choice([
                ("BAD_REQUEST_PAYMENT_DECLINED", f"{bank} declined transaction (Authorization failed)", "card"),
                ("GATEWAY_TIMEOUT", f"{bank} network timeout during 3DS card challenge", "card"),
                ("INSUFFICIENT_FUNDS", f"{bank} account balance insufficient for mandate debit", "upi"),
                ("AUTHENTICATION_FAILED", "3D Secure auth failed: incorrect OTP entered", "card")
            ])
            method = error_type[2]
            fail_dt = created_dt + timedelta(seconds=random.randint(45, 180))
            
            failed_instrument_info = {
                "type": method,
                "instrument_name": f"{bank} {card_network} Card ({masked_card})" if method == "card" else f"{bank} Account via {upi_handle}",
                "error_code": error_type[0],
                "error_description": error_type[1],
                "failure_timestamp": fail_dt.isoformat() + "Z"
            }

            status_history.append({
                "status": "attempted",
                "timestamp": (created_dt + timedelta(seconds=20)).isoformat() + "Z",
                "details": f"Attempting payment via {failed_instrument_info['instrument_name']}"
            })
            status_history.append({
                "status": "failed",
                "timestamp": fail_dt.isoformat() + "Z",
                "error_code": error_type[0],
                "error_description": error_type[1],
                "failed_instrument": failed_instrument_info['instrument_name'],
                "details": f"Payment failed: {error_type[1]}"
            })

        elif pattern == "payment_link_expired":
            last_status = "expired"
            exp_dt = created_dt + timedelta(minutes=15)
            failed_instrument_info = {
                "type": "checkout_session",
                "instrument_name": f"Hosted Checkout Link (Reserved for {bank} Netbanking / Card)",
                "error_code": "LINK_EXPIRED_UNPAID",
                "error_description": "15-minute checkout reservation expired before customer authorized payment",
                "failure_timestamp": exp_dt.isoformat() + "Z"
            }
            status_history.append({
                "status": "issued",
                "timestamp": (created_dt + timedelta(seconds=10)).isoformat() + "Z",
                "details": "Payment link generated with 15m validity"
            })
            status_history.append({
                "status": "expired",
                "timestamp": exp_dt.isoformat() + "Z",
                "details": "Payment link expired without customer payment"
            })

        elif pattern == "abandoned_at_otp":
            last_status = "attempted"
            otp_dt = created_dt + timedelta(seconds=40)
            failed_instrument_info = {
                "type": "card_3ds",
                "instrument_name": f"{bank} {card_network} Debit Card ({masked_card})",
                "error_code": "OTP_DELIVERY_FRICTION",
                "error_description": f"Customer waited at {bank} 3DS OTP verification screen; SMS delayed or window closed",
                "failure_timestamp": (otp_dt + timedelta(minutes=8)).isoformat() + "Z"
            }
            status_history.append({
                "status": "otp_requested",
                "timestamp": otp_dt.isoformat() + "Z",
                "details": f"Customer reached {bank} 3DS OTP verification screen"
            })
            status_history.append({
                "status": "abandoned_at_otp",
                "timestamp": (otp_dt + timedelta(minutes=8)).isoformat() + "Z",
                "details": "No OTP entered; customer closed checkout tab"
            })

        elif pattern == "price_hesitation":
            last_status = "attempted"
            idle_dt = created_dt + timedelta(seconds=30)
            failed_instrument_info = {
                "type": "cart_hesitation",
                "instrument_name": f"Selected Payment Rail: {bank} UPI ({upi_handle})",
                "error_code": "IDLE_PRICE_HESITATION",
                "error_description": "Cart left idle on payment method review screen for >10 minutes",
                "failure_timestamp": (idle_dt + timedelta(minutes=12)).isoformat() + "Z"
            }
            status_history.append({
                "status": "viewed_payment_options",
                "timestamp": idle_dt.isoformat() + "Z",
                "details": "Customer viewed payment method screen with total price"
            })
            status_history.append({
                "status": "idle_abandonment",
                "timestamp": (idle_dt + timedelta(minutes=12)).isoformat() + "Z",
                "details": "Cart left idle for >10 minutes without interaction or retry"
            })

        elif pattern == "successful":
            last_status = "paid"
            pay_dt = created_dt + timedelta(seconds=random.randint(40, 110))
            status_history.append({
                "status": "attempted",
                "timestamp": (created_dt + timedelta(seconds=20)).isoformat() + "Z",
                "details": f"Customer authorized payment via {bank} {method}"
            })
            status_history.append({
                "status": "paid",
                "timestamp": pay_dt.isoformat() + "Z",
                "details": f"Payment captured successfully via {bank}"
            })

        phone_suffix = f"{random.randint(1000, 9999)}"
        email_prefix = f"user_{i}"

        record = {
            "transaction_id": txn_id,
            "customer_id": cust_id,
            "pattern_type": pattern,
            "amount": amount,
            "currency": "INR",
            "method": method,
            "created_at": created_str,
            "last_status": last_status,
            "status_history": status_history,
            "customer_contact": {
                "email": f"{email_prefix[:3]}***@example.com",
                "phone": f"+91-98765{phone_suffix}"
            },
            "prior_reminder_count": prior_reminders,
            "opt_out": opt_out,
            "failed_instrument_info": failed_instrument_info,
            "recommended_instrument_info": recommended_instrument_info
        }
        batch.append(record)

    return batch

def save_sample_batch(filepath: Path = None) -> Path:
    if filepath is None:
        filepath = Path(__file__).parent / "sample_batch.json"
    batch = generate_batch(count=60, seed=42)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(batch, f, indent=2)
    print(f"Generated {len(batch)} synthetic transaction records -> {filepath}")
    return filepath

if __name__ == "__main__":
    save_sample_batch()
