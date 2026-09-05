"""
Pipeline Orchestrator: End-to-End AI Revenue Recovery Execution

Orchestrates sequential or graph-based execution:
[Transaction Record]
       │
       ▼
1. DETECTOR (rule-based risk filter)
       │
       ▼
2. DIAGNOSER (hybrid telemetry rules + LangChain LLM reasoning)
       │
       ▼
3. DECIDER (bounded intervention strategy planning)
       │
       ▼
4. GUARDRAIL (compliance, consent, DND, and anti-fatigue checks)
       │
       ▼
5. EXECUTOR (Razorpay test-mode API execution)
       │
       ▼
6. AUDIT LOG (immutable SQL persistence of complete decision lineage)
       │
       ▼
7. EVALUATOR (quantitative recovery ROI, breakdown & exceptions reporting)
"""

import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pathlib import Path

from agent.detector import evaluate_transaction_risk
from agent.diagnoser import diagnose
from agent.decider import decide_action
from agent.guardrail import check_guardrails
from agent.executor import execute_action
from agent.evaluate import compute_evaluation_report, print_console_summary, CONVERSION_ASSUMPTIONS
from storage.db import init_db, insert_audit_entry, get_audit_trail

def simulate_conversion(txn_id: str, action: str) -> bool:
    """
    Deterministically simulates whether an executed recovery action converted
    into a captured payment based on calibrated historical benchmarks.
    """
    prob = CONVERSION_ASSUMPTIONS.get(action, 0.0)
    if prob <= 0.0:
        return False
    score = (abs(hash(txn_id + "_conv_salt")) % 100) / 100.0
    return score < prob

def process_single_transaction(
    txn: dict,
    batch_id: str,
    seen_transactions: set,
    current_time: Optional[datetime] = None,
    client=None,
    llm_override=None
) -> dict:
    """
    Processes one transaction through the complete multi-agent pipeline.
    Returns complete audit entry dictionary.
    """
    txn_id = txn.get("transaction_id", "unknown_txn")
    cust_id = txn.get("customer_id", "unknown_customer")
    amount = float(txn.get("amount", 0.0))

    # Base Audit Record Template
    audit_entry = {
        "batch_id": batch_id,
        "transaction_id": txn_id,
        "customer_id": cust_id,
        "amount": amount,
        "detector_flagged": False,
        "risk_reason": "none",
        "diagnosis_cause": "none",
        "diagnosis_confidence": 0.0,
        "diagnosis_method": "n/a",
        "diagnosis_reasoning": "none",
        "proposed_action": "none",
        "decision_reasoning": "none",
        "guardrail_approved": False,
        "guardrail_reason": "none",
        "guardrail_rule": "none",
        "execution_status": "pending",
        "execution_result": "none",
        "recovered": False,
        "recovered_amount": 0.0
    }

    # 1. Detector Stage
    is_at_risk, risk_reason = evaluate_transaction_risk(txn, reference_time=current_time)
    audit_entry["detector_flagged"] = is_at_risk
    audit_entry["risk_reason"] = risk_reason

    # Terminal or non-recoverable transactions bypass intervention
    if not is_at_risk:
        audit_entry["execution_status"] = "not_flagged"
        audit_entry["execution_result"] = f"Filtered by detector: {risk_reason}."
        audit_entry["guardrail_approved"] = True
        audit_entry["guardrail_rule"] = "detector_passthrough"
        return audit_entry

    # 2. Diagnoser Stage (Hybrid rules + LangChain LLM)
    diag = diagnose(txn, llm_override=llm_override)
    audit_entry["diagnosis_cause"] = diag["cause"]
    audit_entry["diagnosis_confidence"] = diag["confidence"]
    audit_entry["diagnosis_method"] = diag["method"]
    audit_entry["diagnosis_reasoning"] = diag["reasoning"]

    # 3. Decider Stage (Bounded Strategy Selection)
    decision = decide_action(txn, diag)
    action = decision["action"]
    audit_entry["proposed_action"] = action
    audit_entry["decision_reasoning"] = decision["reasoning"]

    # 4. Guardrail Stage (Compliance & Policy Enforcement)
    guard = check_guardrails(
        transaction=txn,
        proposed_action=decision,
        seen_transactions=seen_transactions,
        current_time=current_time
    )
    seen_transactions.add(txn_id)
    audit_entry["guardrail_approved"] = guard["approved"]
    audit_entry["guardrail_rule"] = guard["guardrail_rule"]
    audit_entry["guardrail_reason"] = guard["block_reason"] or guard["audit_note"]

    if not guard["approved"]:
        audit_entry["execution_status"] = "blocked"
        audit_entry["execution_result"] = f"Intervention blocked: {guard['block_reason']}"
        return audit_entry

    # 5. Executor Stage (Razorpay API / Concierge Dispatch)
    exec_res = execute_action(txn, decision, client=client)
    exec_status = exec_res.get("status", "executed")
    audit_entry["execution_status"] = exec_status
    audit_entry["execution_result"] = exec_res.get("details", "")

    # 6. Evaluation & Recovery Measurement
    if exec_status in ("executed", "escalated_to_human") and action != "no_action":
        did_recover = simulate_conversion(txn_id, action)
        audit_entry["recovered"] = did_recover
        audit_entry["recovered_amount"] = amount if did_recover else 0.0
    else:
        audit_entry["recovered"] = False
        audit_entry["recovered_amount"] = 0.0

    return audit_entry

def run_batch(
    transactions: List[dict],
    batch_id: Optional[str] = None,
    db_url: Optional[str] = None,
    current_time: Optional[datetime] = None,
    client=None,
    llm_override=None
) -> dict:
    """
    Runs the complete multi-agent pipeline over a batch of transactions,
    writes audit logs to the database, and returns the evaluation report.
    """
    if batch_id is None:
        batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:6]}"

    # Reference daytime in IST: default to 2:30 PM IST if not supplied (to simulate active operational day)
    if current_time is None:
        current_time = datetime(2026, 9, 4, 9, 0, 0, tzinfo=timezone.utc)  # 2:30 PM IST

    # Ensure DB schema exists
    init_db(db_url)

    seen_transactions = set()
    processed_records = []

    for txn in transactions:
        audit_dict = process_single_transaction(
            txn=txn,
            batch_id=batch_id,
            seen_transactions=seen_transactions,
            current_time=current_time,
            client=client,
            llm_override=llm_override
        )
        # Persist to database
        insert_audit_entry(audit_dict, db_url=db_url)
        processed_records.append(audit_dict)

    # Compute evaluation metrics
    report = compute_evaluation_report(batch_id=batch_id, records=processed_records)
    return report

if __name__ == "__main__":
    sample_path = Path(__file__).parent.parent / "data" / "sample_batch.json"
    if not sample_path.exists():
        from data.generate_batch import save_sample_batch
        sample_path = save_sample_batch()

    with open(sample_path, "r", encoding="utf-8") as f:
        sample_data = json.load(f)

    print(f"Loaded {len(sample_data)} transactions from {sample_path}")
    print("Initiating Multi-Agent Revenue Recovery Pipeline...")
    evaluation_report = run_batch(sample_data)
    print_console_summary(evaluation_report)
