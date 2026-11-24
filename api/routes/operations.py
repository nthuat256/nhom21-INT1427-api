from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from api.controllers.loans import ensure_loan_access, get_loan_or_404
from api.database import get_db
from api.dependencies import get_current_user, require_roles
from api.models import (
    AuditLog, Device, LoanRequest, LoanStatus, MaintenanceRecord,
    MaintenanceStatus, MaintenanceUpdate, Notification, Role, User,
)
from api.services.loan_service import (
    approve_loan, checkout_loan, create_loan, reject_loan, return_loan,
)
from api.services.maintenance_service import report_damage, update_maintenance
from api.utils.pagination import paginate
from api.utils.audit import record_audit
from api.validators.schemas import (
    LoanCreate, LoanDecision, LoanDetailRead, LoanRead, MaintenanceCreate,
    MaintenanceRead, MaintenanceUpdate as MaintenanceUpdateInput,
    NotificationRead,
)

router = APIRouter(tags=["Operations"])
admin_only = require_roles(Role.ADMIN)
technical_staff = require_roles(Role.ADMIN, Role.TECHNICIAN)


@router.post("/loan-requests", response_model=LoanRead, status_code=201)
def request_loan(
    payload: LoanCreate,
    db: Session = Depends(get_db),
    borrower: User = Depends(require_roles(Role.BORROWER)),
):
    loan = create_loan(db, borrower, payload)
    return get_loan_or_404(db, loan.id)


@router.get("/loan-requests", response_model=dict)
def list_loans(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    loan_status: LoanStatus | None = Query(default=None, alias="status"),
    starts_after: datetime | None = None, ends_before: datetime | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    if user.role == Role.TECHNICIAN:
        raise HTTPException(status_code=403, detail="Technicians cannot access loan requests")
    if user.role == Role.TECHNICIAN:
        raise HTTPException(status_code=403, detail="Technicians cannot access loan requests")
    query = select(LoanRequest).options(selectinload(LoanRequest.details))
    if user.role == Role.BORROWER:
        query = query.where(LoanRequest.requester_id == user.id)
    if loan_status:
        query = query.where(LoanRequest.status == loan_status)
    if starts_after:
        query = query.where(LoanRequest.starts_at >= starts_after)
    if ends_before:
        query = query.where(LoanRequest.due_at <= ends_before)
    result = paginate(db, LoanRequest, page, page_size, query.order_by(LoanRequest.created_at.desc()))
    return {**result, "items": [LoanRead.model_validate(item) for item in result["items"]]}


@router.get("/loan-requests/{loan_id}", response_model=LoanRead)
def get_loan(loan_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    loan = get_loan_or_404(db, loan_id)
    ensure_loan_access(loan, user)
    return loan


@router.get("/loan-requests/{loan_id}/details", response_model=list[LoanDetailRead])
def list_loan_details(loan_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    loan = get_loan_or_404(db, loan_id)
    ensure_loan_access(loan, user)
    return loan.details


@router.post("/loan-requests/{loan_id}/approve", response_model=LoanRead)
def approve_request(loan_id: str, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    loan = get_loan_or_404(db, loan_id)
    approve_loan(db, actor, loan)
    return get_loan_or_404(db, loan_id)


@router.post("/loan-requests/{loan_id}/reject", response_model=LoanRead)
def reject_request(
    loan_id: str, payload: LoanDecision,
    db: Session = Depends(get_db), actor: User = Depends(admin_only),
):
    loan = get_loan_or_404(db, loan_id)
    reject_loan(db, actor, loan, payload.reason)
    return get_loan_or_404(db, loan_id)


@router.post("/loan-requests/{loan_id}/checkout", response_model=LoanRead)
def checkout_request(loan_id: str, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    loan = get_loan_or_404(db, loan_id)
    checkout_loan(db, actor, loan)
    return get_loan_or_404(db, loan_id)


@router.post("/loan-requests/{loan_id}/return", response_model=LoanRead)
def return_request(loan_id: str, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    loan = get_loan_or_404(db, loan_id)
    return_loan(db, actor, loan)
    return get_loan_or_404(db, loan_id)


@router.post("/loan-requests/{loan_id}/cancel", response_model=LoanRead)
def cancel_request(loan_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    loan = get_loan_or_404(db, loan_id)
    ensure_loan_access(loan, user)
    if loan.status not in (LoanStatus.PENDING, LoanStatus.APPROVED):
        raise HTTPException(status_code=409, detail="This request can no longer be cancelled")
    previous_status = loan.status
    try:
        changed = db.execute(
            update(LoanRequest)
            .where(
                LoanRequest.id == loan.id,
                LoanRequest.requester_id == loan.requester_id,
                LoanRequest.status.in_([LoanStatus.PENDING, LoanStatus.APPROVED]),
            )
            .values(status=LoanStatus.CANCELLED)
        ).rowcount
        if changed != 1:
            raise HTTPException(status_code=409, detail="This request can no longer be cancelled")
        if previous_status == LoanStatus.APPROVED:
            for line in loan.details:
                changed = db.execute(
                    update(Device)
                    .where(
                        Device.id == line.device_id,
                        Device.quantity_available + line.quantity <= Device.quantity_total,
                    )
                    .values(quantity_available=Device.quantity_available + line.quantity)
                ).rowcount
                if changed != 1:
                    raise HTTPException(status_code=409, detail="Inventory changed while cancelling the request")
        loan.status = LoanStatus.CANCELLED
        from api.utils.audit import record_audit
        record_audit(db, user, "loan.cancelled", "loan_request", loan.id)
        db.add(Notification(
            user_id=loan.requester_id,
            title="Loan request cancelled",
            message="Your loan request was cancelled.",
            related_type="loan_request",
            related_id=loan.id,
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_loan_or_404(db, loan_id)


@router.post("/maintenance", response_model=MaintenanceRead, status_code=201)
def report_maintenance(
    payload: MaintenanceCreate, db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
):
    return report_damage(db, actor, payload.device_id, payload.description)


@router.get("/maintenance", response_model=dict)
def list_maintenance(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    maintenance_status: MaintenanceStatus | None = Query(default=None, alias="status"),
    device_id: str | None = None,
    db: Session = Depends(get_db), _: User = Depends(technical_staff),
):
    query = select(MaintenanceRecord)
    if maintenance_status:
        query = query.where(MaintenanceRecord.status == maintenance_status)
    if device_id:
        query = query.where(MaintenanceRecord.device_id == device_id)
    result = paginate(db, MaintenanceRecord, page, page_size, query.order_by(MaintenanceRecord.created_at.desc()))
    return {**result, "items": [MaintenanceRead.model_validate(item) for item in result["items"]]}


@router.get("/maintenance/{record_id}", response_model=MaintenanceRead)
def get_maintenance(record_id: str, db: Session = Depends(get_db), _: User = Depends(technical_staff)):
    record = db.get(MaintenanceRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Maintenance record not found")
    return record


@router.get("/maintenance/{record_id}/history")
def maintenance_history(
    record_id: str, db: Session = Depends(get_db), _: User = Depends(technical_staff),
):
    if not db.get(MaintenanceRecord, record_id):
        raise HTTPException(status_code=404, detail="Maintenance record not found")
    return db.scalars(
        select(MaintenanceUpdate).where(MaintenanceUpdate.maintenance_id == record_id)
        .order_by(MaintenanceUpdate.created_at)
    ).all()


@router.patch("/maintenance/{record_id}", response_model=MaintenanceRead)
def edit_maintenance(
    record_id: str, payload: MaintenanceUpdateInput,
    db: Session = Depends(get_db), actor: User = Depends(require_roles(Role.TECHNICIAN)),
):
    record = db.scalar(
        select(MaintenanceRecord).where(MaintenanceRecord.id == record_id).with_for_update()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Maintenance record not found")
    return update_maintenance(
        db, actor, record, payload.status, payload.progress_note, payload.inspection_passed
    )


@router.get("/notifications", response_model=dict)
def list_notifications(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    result = paginate(db, Notification, page, page_size, query.order_by(Notification.created_at.desc()))
    return {**result, "items": [NotificationRead.model_validate(item) for item in result["items"]]}


@router.post("/notifications/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notification = db.get(Notification, notification_id)
    if not notification or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    record_audit(db, user, "notification.read", "notification", notification.id)
    db.commit()
    db.refresh(notification)
    return notification


@router.get("/audit-logs", response_model=dict)
def list_audit_logs(
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    action: str | None = None, entity_type: str | None = None,
    actor_id: str | None = None, db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    result = paginate(db, AuditLog, page, page_size, query.order_by(AuditLog.created_at.desc()))
    return result
