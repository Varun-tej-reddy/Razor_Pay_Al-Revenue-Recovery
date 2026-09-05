"""
SQLAlchemy Data Models for AI Revenue Recovery Audit Trail

Every transaction processed by the recovery agent pipeline generates exactly ONE
complete immutable audit log record capturing the complete decision lineage:
Detection -> Diagnosis -> Strategy Decision -> Guardrail Validation -> Execution -> Recovery Outcome.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    Index
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(64), nullable=False, index=True)
    transaction_id = Column(String(64), nullable=False, index=True)
    customer_id = Column(String(64), nullable=False, default="unknown_customer")
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Detector Stage
    detector_flagged = Column(Boolean, nullable=False, default=False)
    risk_reason = Column(String(128), nullable=False, default="none")
    
    # Diagnoser Stage
    diagnosis_cause = Column(String(64), nullable=False, default="none")
    diagnosis_confidence = Column(Float, nullable=False, default=0.0)
    diagnosis_method = Column(String(32), nullable=False, default="n/a")  # "rule", "llm", or "n/a"
    diagnosis_reasoning = Column(Text, nullable=False, default="none")
    
    # Decider Stage
    proposed_action = Column(String(64), nullable=False, default="none")
    decision_reasoning = Column(Text, nullable=False, default="none")
    
    # Guardrail Stage
    guardrail_approved = Column(Boolean, nullable=False, default=False)
    guardrail_reason = Column(Text, nullable=False, default="none")
    guardrail_rule = Column(String(64), nullable=False, default="none")
    
    # Executor Stage
    execution_status = Column(String(64), nullable=False, default="pending")  # "executed", "blocked", "skipped", "not_flagged", "failed", "escalated_to_human"
    execution_result = Column(Text, nullable=False, default="none")
    
    # Financials & Recovery Measurement
    amount = Column(Float, nullable=False, default=0.0)
    recovered = Column(Boolean, nullable=False, default=False)
    recovered_amount = Column(Float, nullable=False, default=0.0)

    __table_args__ = (
        Index("idx_batch_txn", "batch_id", "transaction_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "transaction_id": self.transaction_id,
            "customer_id": self.customer_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "detector_flagged": self.detector_flagged,
            "risk_reason": self.risk_reason,
            "diagnosis_cause": self.diagnosis_cause,
            "diagnosis_confidence": self.diagnosis_confidence,
            "diagnosis_method": self.diagnosis_method,
            "diagnosis_reasoning": self.diagnosis_reasoning,
            "proposed_action": self.proposed_action,
            "decision_reasoning": self.decision_reasoning,
            "guardrail_approved": self.guardrail_approved,
            "guardrail_reason": self.guardrail_reason,
            "guardrail_rule": self.guardrail_rule,
            "execution_status": self.execution_status,
            "execution_result": self.execution_result,
            "amount": self.amount,
            "recovered": self.recovered,
            "recovered_amount": self.recovered_amount
        }


class PromiseToPay(Base):
    __tablename__ = "promise_to_pay"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(64), nullable=False, index=True)
    customer_id = Column(String(64), nullable=False, default="unknown")
    customer_name = Column(String(128), nullable=False, default="Customer")
    amount = Column(Float, nullable=False, default=0.0)
    ptp_date = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="scheduled")  # "scheduled", "due_today", "honored", "breached"
    channel = Column(String(32), nullable=False, default="hinglish_chat")
    notes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "amount": self.amount,
            "ptp_date": self.ptp_date,
            "status": self.status,
            "channel": self.channel,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

