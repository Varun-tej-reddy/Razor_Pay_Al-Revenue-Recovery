"""
Database Access & Session Management for Audit Trail

Provides session management, schema initialization, and high-performance
DataFrame / JSON query utilities for audit inspection.
"""

import os
from typing import Optional, List, Any
import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from storage.models import Base, AuditLog, PromiseToPay

DEFAULT_DB_URL = "sqlite:///./recovery_audit.db"

def get_db_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DB_URL)

def get_engine(db_url: Optional[str] = None):
    url = db_url or get_db_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, echo=False)

def seed_initial_ptps_if_empty(session: Optional[Session] = None, db_url: Optional[str] = None):
    """Populates initial realistic PTP registry data if the table is currently empty."""
    own_session = False
    if session is None:
        session = get_db_session(db_url)
        own_session = True
    try:
        count = session.scalars(select(PromiseToPay)).first()
        if count is None:
            initial_seeds = [
                {
                    "transaction_id": "txn_kotak_4499",
                    "customer_id": "cust_rohan_01",
                    "customer_name": "Rohan Sharma",
                    "amount": 4499.0,
                    "ptp_date": "Tomorrow 10:00 AM IST",
                    "status": "scheduled",
                    "channel": "Hinglish Chat",
                    "notes": "Customer promised morning payment post salary credit; dunning suppressed."
                },
                {
                    "transaction_id": "INV-2024-001",
                    "customer_id": "cust_b2b_rel",
                    "customer_name": "Reliance Retail Ltd",
                    "amount": 85000.0,
                    "ptp_date": "2026-09-08 04:00 PM IST",
                    "status": "scheduled",
                    "channel": "WhatsApp Concierge",
                    "notes": "Finance Director approved 2% prompt settlement via RTGS."
                },
                {
                    "transaction_id": "txn_hdfc_12850",
                    "customer_id": "cust_priya_02",
                    "customer_name": "Priya Patel",
                    "amount": 12850.0,
                    "ptp_date": "2026-09-05 11:30 AM IST",
                    "status": "honored",
                    "channel": "Voice Telephony",
                    "notes": "Settled and reconciled via 1-Click Biometric UPI authorization."
                }
            ]
            for s in initial_seeds:
                entry = PromiseToPay(
                    transaction_id=s["transaction_id"],
                    customer_id=s["customer_id"],
                    customer_name=s["customer_name"],
                    amount=s["amount"],
                    ptp_date=s["ptp_date"],
                    status=s["status"],
                    channel=s["channel"],
                    notes=s["notes"]
                )
                session.add(entry)
            session.commit()
    except Exception:
        session.rollback()
    finally:
        if own_session:
            session.close()

def init_db(db_url: Optional[str] = None):
    """Creates tables if they do not exist and seeds initial records."""
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    seed_initial_ptps_if_empty(db_url=db_url)
    return engine

def get_db_session(db_url: Optional[str] = None) -> Session:
    """Yields a database session with expire_on_commit=False."""
    engine = get_engine(db_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return factory()

def insert_audit_entry(entry_dict: dict, session: Optional[Session] = None, db_url: Optional[str] = None) -> AuditLog:
    """Inserts a single AuditLog record into the database."""
    own_session = False
    if session is None:
        session = get_db_session(db_url)
        own_session = True

    try:
        entry = AuditLog(
            batch_id=entry_dict.get("batch_id", "batch_default"),
            transaction_id=entry_dict.get("transaction_id", "unknown_txn"),
            customer_id=entry_dict.get("customer_id", "unknown_customer"),
            detector_flagged=bool(entry_dict.get("detector_flagged", False)),
            risk_reason=str(entry_dict.get("risk_reason", "none")),
            diagnosis_cause=str(entry_dict.get("diagnosis_cause", "none")),
            diagnosis_confidence=float(entry_dict.get("diagnosis_confidence", 0.0)),
            diagnosis_method=str(entry_dict.get("diagnosis_method", "n/a")),
            diagnosis_reasoning=str(entry_dict.get("diagnosis_reasoning", "none")),
            proposed_action=str(entry_dict.get("proposed_action", "none")),
            decision_reasoning=str(entry_dict.get("decision_reasoning", "none")),
            guardrail_approved=bool(entry_dict.get("guardrail_approved", False)),
            guardrail_reason=str(entry_dict.get("guardrail_reason", "none")),
            guardrail_rule=str(entry_dict.get("guardrail_rule", "none")),
            execution_status=str(entry_dict.get("execution_status", "pending")),
            execution_result=str(entry_dict.get("execution_result", "none")),
            amount=float(entry_dict.get("amount", 0.0)),
            recovered=bool(entry_dict.get("recovered", False)),
            recovered_amount=float(entry_dict.get("recovered_amount", 0.0))
        )
        session.add(entry)
        session.commit()
        return entry
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if own_session:
            session.close()

def get_audit_trail(batch_id: Optional[str] = None, session: Optional[Session] = None, db_url: Optional[str] = None) -> pd.DataFrame:
    """
    Returns the audit trail for a batch (or all batches) as a Pandas DataFrame.
    """
    own_session = False
    if session is None:
        session = get_db_session(db_url)
        own_session = True

    try:
        stmt = select(AuditLog).order_by(AuditLog.id.desc())
        if batch_id:
            stmt = stmt.where(AuditLog.batch_id == batch_id)

        records = session.scalars(stmt).all()
        data = [r.to_dict() for r in records]
        df = pd.DataFrame(data)
        return df
    finally:
        if own_session:
            session.close()

def get_audit_records(batch_id: Optional[str] = None, session: Optional[Session] = None, db_url: Optional[str] = None) -> List[dict]:
    """Returns raw list of audit dictionary records for JSON responses."""
    own_session = False
    if session is None:
        session = get_db_session(db_url)
        own_session = True

    try:
        stmt = select(AuditLog).order_by(AuditLog.id.asc())
        if batch_id:
            stmt = stmt.where(AuditLog.batch_id == batch_id)
        records = session.scalars(stmt).all()
        return [r.to_dict() for r in records]
    finally:
        if own_session:
            session.close()

def insert_promise_to_pay(ptp_dict: dict, session: Optional[Session] = None, db_url: Optional[str] = None) -> PromiseToPay:
    """Inserts a PromiseToPay record into the database."""
    own_session = False
    if session is None:
        session = get_db_session(db_url)
        own_session = True
    try:
        entry = PromiseToPay(
            transaction_id=str(ptp_dict.get("transaction_id", "unknown_txn")),
            customer_id=str(ptp_dict.get("customer_id", "unknown_customer")),
            customer_name=str(ptp_dict.get("customer_name", "Customer")),
            amount=float(ptp_dict.get("amount", 0.0)),
            ptp_date=str(ptp_dict.get("ptp_date", "")),
            status=str(ptp_dict.get("status", "scheduled")),
            channel=str(ptp_dict.get("channel", "hinglish_chat")),
            notes=str(ptp_dict.get("notes", ""))
        )
        session.add(entry)
        session.commit()
        return entry
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if own_session:
            session.close()

class AttrDict(dict):
    """A dictionary that also permits attribute-style access."""
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            return None
    def __setattr__(self, key, value):
        self[key] = value

def get_promises_to_pay(status: Optional[str] = None, session: Optional[Session] = None, db_url: Optional[str] = None) -> List[Any]:
    """Retrieves all Promise-to-Pay commitments from the database as AttrDict objects."""
    own_session = False
    if session is None:
        session = get_db_session(db_url)
        own_session = True
    try:
        stmt = select(PromiseToPay).order_by(PromiseToPay.id.desc())
        if status:
            stmt = stmt.where(PromiseToPay.status == status)
        records = session.scalars(stmt).all()
        return [AttrDict(r.to_dict()) for r in records]
    finally:
        if own_session:
            session.close()

def update_promise_to_pay_status(ptp_id: int, new_status: str, session: Optional[Session] = None, db_url: Optional[str] = None) -> bool:
    """Updates the status of a Promise-to-Pay commitment."""
    own_session = False
    if session is None:
        session = get_db_session(db_url)
        own_session = True
    try:
        entry = session.get(PromiseToPay, ptp_id)
        if entry:
            entry.status = new_status
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if own_session:
            session.close()

