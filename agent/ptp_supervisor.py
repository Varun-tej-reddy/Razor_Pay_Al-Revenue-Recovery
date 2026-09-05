# PTP Risk & Anti-Fatigue Policy Supervisor Agent (Track 03)

import os
from typing import Dict, Any, Optional
from agent.llm_client import call_gemini, clean_json_response, get_gemini_api_key

def assess_ptp_credibility(ptp_record: Dict[str, Any]) -> Dict[str, Any]:
    amount = float(ptp_record.get("amount", 0.0))
    customer = ptp_record.get("customer_name", "Customer")
    ptp_date = ptp_record.get("ptp_date", "Pending")
    notes = ptp_record.get("notes", "")
    status = ptp_record.get("status", "scheduled")

    base_score = 0.88 if status == "scheduled" else (0.95 if status == "honored" else 0.25)
    base_tier = "Low" if base_score >= 0.8 else ("Medium" if base_score >= 0.5 else "High")
    base_directive = "SUPPRESS_ALL_DUNNING" if status == "scheduled" else ("RECONCILED" if status == "honored" else "RESUME_DUNNING")

    api_key = get_gemini_api_key()
    if api_key:
        sys_inst = (
            "You are the Anti-Fatigue Dunning Supervisor AI for Razorpay. "
            "Analyze debtor commitments to pay and evaluate credibility to prevent customer contact fatigue. "
            "Return strictly valid JSON with keys: credibility_score (float 0-1), risk_tier (Low, Medium, High), "
            "dunning_directive (SUPPRESS_ALL_DUNNING, SOFT_REMINDER, RESUME_ESCALATION), rationale (string)."
        )
        prompt = (
            f"Evaluate PTP commitment:\n"
            f"Customer: {customer}\n"
            f"Amount: INR {amount:,.2f}\n"
            f"Promised Date: {ptp_date}\n"
            f"Status: {status}\n"
            f"Transcript Notes: {notes}"
        )
        try:
            res = call_gemini(prompt, system_instruction=sys_inst, temperature=0.1, response_mime_type="application/json")
            if res["success"]:
                data = clean_json_response(res["text"])
                if "credibility_score" in data:
                    rat = data.get("rationale", "Commitment analyzed.")
                    return {
                        "credibility_score": float(data.get("credibility_score", base_score)),
                        "risk_tier": data.get("risk_tier", base_tier),
                        "dunning_directive": data.get("dunning_directive", base_directive),
                        "rationale": f"[Gemini 3.6 Flash] {rat}",
                        "ai_model": res["model"],
                        "latency_ms": res["latency_ms"]
                    }
        except Exception:
            pass

    return {
        "credibility_score": base_score,
        "risk_tier": base_tier,
        "dunning_directive": base_directive,
        "rationale": f"Anti-fatigue policy active: Grace period scheduled for {ptp_date}. Automated dunning touches halted.",
        "ai_model": "heuristic",
        "latency_ms": 0
    }
