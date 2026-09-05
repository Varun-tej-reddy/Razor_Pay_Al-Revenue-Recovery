"""
B2B Receivables Chaser & Corporate Debt Recovery Engine (Track 03)

Specialized agent module for B2B enterprise invoices:
- Dynamic aging analysis (1-15d, 16-30d, 30+d)
- Indian GST Law Section 16(2) Input Tax Credit (ITC) Risk Warning:
  Under Indian GST law, recipients must pay invoices within 180 days or reverse
  their claimed input tax credit with penal interest. The agent leverages this
  statutory compliance trigger to accelerate B2B payments.
- Dynamic early-payment settlement discounts (e.g. 2% cash discount for 48h settlement)
- Statement of Account (SOA) generator for Corporate Accounts Payable teams
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "b2b_invoices.json"

def load_b2b_invoices() -> List[Dict[str, Any]]:
    """Loads all corporate invoice records from storage and normalizes field aliases."""
    if not DATA_PATH.exists():
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        invoices = json.load(f)
    for inv in invoices:
        company = inv.get("company_name") or inv.get("buyer_name", "")
        amt = float(inv.get("invoice_amount") if inv.get("invoice_amount") is not None else inv.get("amount", 0.0))
        gstin_val = inv.get("gstin") or inv.get("buyer_gstin", "")
        itc_val = float(inv.get("gst_input_credit_amount") if inv.get("gst_input_credit_amount") is not None else inv.get("gst_itc_at_risk_inr", round(amt * 0.18 / 1.18, 2)))
        
        inv["company_name"] = company
        inv["buyer_name"] = company
        inv["invoice_amount"] = amt
        inv["amount"] = amt
        inv["gstin"] = gstin_val
        inv["buyer_gstin"] = gstin_val
        inv["gst_input_credit_amount"] = itc_val
        inv["gst_itc_at_risk_inr"] = itc_val
        
        # Standardize aging bucket representation
        b_str = str(inv.get("aging_bucket", ""))
        if "1-15" in b_str or "1_15" in b_str:
            inv["aging_bucket"] = "1-15 Days"
            inv["aging_bucket_key"] = "1_15_days"
        elif "16-30" in b_str or "16_30" in b_str:
            inv["aging_bucket"] = "16-30 Days"
            inv["aging_bucket_key"] = "16_30_days"
        else:
            inv["aging_bucket"] = "30+ Days"
            inv["aging_bucket_key"] = "30_plus_days"

    return invoices

def save_b2b_invoices(invoices: List[Dict[str, Any]]) -> None:
    """Persists updated invoice states to storage."""
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(invoices, f, indent=2)

def compute_b2b_aging_metrics(invoices: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Computes corporate aging summaries, GST input credit at risk,
    and portfolio recovery status with full backwards-compatible field aliases.
    """
    if invoices is None:
        invoices = load_b2b_invoices()

    total_invoices = len(invoices)
    overdue_invoices = [inv for inv in invoices if inv.get("status") == "overdue"]
    paid_invoices = [inv for inv in invoices if inv.get("status") == "paid"]

    total_overdue_capital = sum(inv.get("invoice_amount", inv.get("amount", 0.0)) for inv in overdue_invoices)
    total_recovered_capital = sum(inv.get("invoice_amount", inv.get("amount", 0.0)) for inv in paid_invoices)
    total_gst_credit_at_risk = sum(inv.get("gst_input_credit_amount", inv.get("gst_itc_at_risk_inr", 0.0)) for inv in overdue_invoices)

    # Aging Buckets
    bucket_1_15 = [inv for inv in overdue_invoices if inv.get("aging_bucket") == "1-15 Days" or inv.get("aging_bucket_key") == "1_15_days"]
    bucket_16_30 = [inv for inv in overdue_invoices if inv.get("aging_bucket") == "16-30 Days" or inv.get("aging_bucket_key") == "16_30_days"]
    bucket_30_plus = [inv for inv in overdue_invoices if inv.get("aging_bucket") == "30+ Days" or inv.get("aging_bucket_key") == "30_plus_days"]

    avg_days_overdue = (
        round(sum(inv.get("days_overdue", 0) for inv in overdue_invoices) / len(overdue_invoices), 1)
        if overdue_invoices else 0.0
    )

    buckets_dict = {
        "1_15_days": {
            "count": len(bucket_1_15),
            "amount": sum(inv.get("invoice_amount", inv.get("amount", 0.0)) for inv in bucket_1_15),
            "strategy": "Mild Corporate Nudge & Virtual Account Link"
        },
        "16_30_days": {
            "count": len(bucket_16_30),
            "amount": sum(inv.get("invoice_amount", inv.get("amount", 0.0)) for inv in bucket_16_30),
            "strategy": "GST ITC Clawback Advisory + 2% Early Settlement Offer"
        },
        "30_plus_days": {
            "count": len(bucket_30_plus),
            "amount": sum(inv.get("invoice_amount", inv.get("amount", 0.0)) for inv in bucket_30_plus),
            "strategy": "Executive & Legal Hold Escalation Notice"
        }
    }

    return {
        "total_invoices": total_invoices,
        "total_invoices_count": total_invoices,
        "overdue_count": len(overdue_invoices),
        "paid_count": len(paid_invoices),
        "total_overdue_capital": total_overdue_capital,
        "total_receivables_inr": total_overdue_capital,
        "total_recovered_capital": total_recovered_capital,
        "total_gst_credit_at_risk": total_gst_credit_at_risk,
        "total_gst_itc_at_risk_inr": total_gst_credit_at_risk,
        "avg_days_overdue": avg_days_overdue,
        "buckets": buckets_dict,
        "aging_buckets": buckets_dict
    }

def execute_b2b_chase_action(invoice_id: str, action_type: str, custom_note: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes an autonomous or manual B2B chaser workflow on an overdue invoice.
    Supported action_types:
    - "send_gst_warning": Formats GST Section 16(2) reversal risk advisory
    - "apply_cash_discount": Applies 2% instant Net-30 settlement incentive
    - "send_soa": Generates and dispatches formal Statement of Account
    - "escalate_legal": Dispatches final demand notice to finance director
    - "mark_paid": Simulates corporate treasury clearance
    """
    invoices = load_b2b_invoices()
    target = next((inv for inv in invoices if inv["invoice_id"] == invoice_id), None)
    if not target:
        return {"success": False, "error": f"Invoice {invoice_id} not found"}

    result = {
        "invoice_id": invoice_id,
        "company_name": target["company_name"],
        "action_type": action_type,
        "timestamp": "2026-09-04T12:00:00Z"
    }

    if action_type == "send_gst_warning":
        msg = (
            f"URGENT COMPLIANCE NOTICE: Invoice #{invoice_id} (₹{target['invoice_amount']:,.2f}) for "
            f"{target['company_name']} is {target['days_overdue']} days overdue. "
            f"Under Section 16(2) of the CGST Act, failure to settle within 180 days triggers statutory "
            f"reversal of ₹{target.get('gst_input_credit_amount', 0.0):,.2f} Input Tax Credit with 18% p.a. interest. "
            f"Please authorize payment via corporate RTGS or Razorpay Virtual Account."
        )
        try:
            from agent.llm_client import call_gemini, get_gemini_api_key
            if get_gemini_api_key():
                p_text = (
                    f"Draft a formal, urgent B2B compliance notice to Accounts Payable at {target['company_name']} (GSTIN: {target['gstin']}) "
                    f"regarding Invoice #{invoice_id} for ₹{target['invoice_amount']:,.2f} which is {target['days_overdue']} days overdue. "
                    f"Warn them that under Section 16(2) of the CGST Act, failure to settle within 180 days mandates reversal of ₹{target.get('gst_input_credit_amount', 0.0):,.2f} "
                    f"Input Tax Credit with 18% p.a. interest. Keep professional, under 100 words."
                )
                llm_res = call_gemini(p_text, temperature=0.1)
                if llm_res["success"] and "Section 16(2)" in llm_res["text"] and "CGST Act" in llm_res["text"]:
                    msg = llm_res["text"]
                    result["ai_generated"] = True
                    result["ai_model"] = llm_res["model"]
        except Exception:
            pass

        target["last_chaser_action"] = "GST Section 16(2) Advisory Dispatched"
        result["message_dispatched"] = msg
        result["channel"] = "Corporate Email & Tax Compliance Portal"

    elif action_type == "apply_cash_discount":
        discount = round(target["invoice_amount"] * 0.02, 2)
        discounted_amount = round(target["invoice_amount"] - discount, 2)
        msg = (
            f"SPECIAL EARLY SETTLEMENT OFFER: Pay Invoice #{invoice_id} within 48 hours to avail a 2% "
            f"commercial prompt-payment discount (Save ₹{discount:,.2f}). Revised settlement amount: ₹{discounted_amount:,.2f}. "
            f"Instant Razorpay Corporate UPI/NEFT link generated."
        )
        target["last_chaser_action"] = f"2% Cash Discount Offered (Save ₹{discount:,.2f})"
        result["discount_amount"] = discount
        result["discounted_amount"] = discounted_amount
        result["message_dispatched"] = msg
        result["channel"] = "Vendor Accounts Payable Desk"

    elif action_type == "send_soa":
        soa_text = (
            f"STATEMENT OF ACCOUNT (SOA)\n"
            f"Client: {target['company_name']} | GSTIN: {target['gstin']}\n"
            f"Outstanding Invoice: #{invoice_id} | PO Ref: {target['po_number']}\n"
            f"Due Date: {target['due_date']} | Days Overdue: {target['days_overdue']}\n"
            f"Principal Amount: ₹{target['invoice_amount']:,.2f}\n"
            f"Applicable GST ({target.get('gst_rate_pct', 18)}%): ₹{target.get('gst_input_credit_amount', 0.0):,.2f}\n"
            f"Status: DELINQUENT — ACTION REQUIRED"
        )
        target["last_chaser_action"] = "Statement of Account (SOA) Dispatched"
        result["soa_content"] = soa_text
        result["channel"] = "Accounts Payable Statement Download"

    elif action_type == "escalate_legal":
        msg = (
            f"FINAL DEMAND FOR PAYMENT: Invoice #{invoice_id} is {target['days_overdue']} days overdue. "
            f"Matter referred to Legal & Commercial Disputes Counsel. Credit line suspended pending clearance."
        )
        target["last_chaser_action"] = "Executive & Legal Escalation Initiated"
        result["message_dispatched"] = msg
        result["channel"] = "Registered Corporate Legal Notice"

    elif action_type == "mark_paid":
        target["status"] = "paid"
        target["days_overdue"] = 0
        target["last_chaser_action"] = "Captured & Settled via Corporate RTGS"
        result["status"] = "paid"
        result["recovered_amount"] = target["invoice_amount"]

    if custom_note:
        target["last_chaser_action"] += f" • Note: {custom_note}"

    save_b2b_invoices(invoices)
    result["success"] = True
    result["updated_invoice"] = target
    return result
