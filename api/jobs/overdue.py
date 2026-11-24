import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from api.config import settings
from api.database import SessionLocal
from api.models import LoanRequest, LoanStatus, Notification
from api.utils.audit import record_audit

logger = logging.getLogger(__name__)


def mark_overdue() -> int:
    db = SessionLocal()
    try:
        loans = db.scalars(
            select(LoanRequest).where(
                LoanRequest.status == LoanStatus.CHECKED_OUT,
                LoanRequest.due_at < datetime.now(timezone.utc),
            ).with_for_update()
        ).all()
        for loan in loans:
            changed = db.execute(
                update(LoanRequest)
                .where(LoanRequest.id == loan.id, LoanRequest.status == LoanStatus.CHECKED_OUT)
                .values(status=LoanStatus.OVERDUE)
            ).rowcount
            if changed != 1:
                continue
            loan.status = LoanStatus.OVERDUE
            db.add(Notification(
                user_id=loan.requester_id,
                title="Equipment overdue",
                message=f"Loan {loan.id} is overdue. Please return the equipment.",
                related_type="loan_request",
                related_id=loan.id,
            ))
            record_audit(db, None, "loan.overdue", "loan_request", loan.id)
        db.commit()
        return len(loans)
    except Exception:
        db.rollback()
        logger.exception("Failed to process overdue loans")
        raise
    finally:
        db.close()


async def overdue_worker() -> None:
    while True:
        try:
            mark_overdue()
        except Exception:
            logger.exception("Overdue worker iteration failed")
        await asyncio.sleep(max(30, settings.overdue_check_interval_seconds))
