from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.models import LoanRequest, Role, User


def get_loan_or_404(db: Session, loan_id: str) -> LoanRequest:
    loan = db.scalar(
        select(LoanRequest)
        .options(selectinload(LoanRequest.details))
        .where(LoanRequest.id == loan_id)
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan request not found")
    return loan


def ensure_loan_access(loan: LoanRequest, user: User) -> None:
    if user.role == Role.TECHNICIAN:
        raise HTTPException(status_code=403, detail="Technicians cannot access loan requests")
    if user.role == Role.BORROWER and loan.requester_id != user.id:
        raise HTTPException(status_code=404, detail="Loan request not found")
