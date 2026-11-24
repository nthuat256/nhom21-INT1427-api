from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.models import (
    Device,
    DeviceStatus,
    LoanDetail,
    LoanRequest,
    LoanStatus,
    Notification,
    Room,
    Schedule,
    User,
)
from api.utils.audit import record_audit
from api.validators.schemas import LoanCreate


def _fail(code: int, message: str) -> None:
    raise HTTPException(status_code=code, detail=message)


def _notify(db: Session, user_id: str, title: str, message: str, loan_id: str) -> None:
    db.add(Notification(
        user_id=user_id,
        title=title,
        message=message,
        related_type="loan_request",
        related_id=loan_id,
    ))


def create_loan(db: Session, borrower: User, payload: LoanCreate) -> LoanRequest:
    try:
        room = db.get(Room, payload.room_id)
        if not room or not room.is_active:
            _fail(404, "Active room not found")

        schedule = db.scalar(select(Schedule).where(
            Schedule.room_id == payload.room_id,
            Schedule.is_active.is_(True),
            Schedule.starts_at <= payload.starts_at,
            Schedule.ends_at >= payload.due_at,
        ).limit(1))
        if not schedule and not (payload.reason and payload.reason.strip()):
            _fail(422, "A reason is required when the request is outside class schedule")

        devices: dict[str, Device] = {}
        for line in payload.details:
            device = db.scalar(select(Device).where(Device.id == line.device_id).with_for_update())
            if not device:
                _fail(404, f"Device {line.device_id} not found")
            if device.status != DeviceStatus.AVAILABLE:
                _fail(409, f"Device {device.name} is not available for lending")
            if device.quantity_available < line.quantity:
                _fail(409, f"Insufficient available quantity for {device.name}")
            devices[line.device_id] = device

        loan = LoanRequest(
            requester_id=borrower.id,
            room_id=payload.room_id,
            starts_at=payload.starts_at,
            due_at=payload.due_at,
            reason=payload.reason.strip() if payload.reason else None,
            status=LoanStatus.APPROVED if schedule else LoanStatus.PENDING,
            matched_schedule_id=schedule.id if schedule else None,
        )
        db.add(loan)
        db.flush()
        for line in payload.details:
            if schedule:
                changed = db.execute(
                    update(Device)
                    .where(
                        Device.id == line.device_id,
                        Device.status == DeviceStatus.AVAILABLE,
                        Device.quantity_available >= line.quantity,
                    )
                    .values(quantity_available=Device.quantity_available - line.quantity)
                ).rowcount
                if changed != 1:
                    _fail(409, "Inventory changed while processing; retry the request")
            db.add(LoanDetail(
                loan_request_id=loan.id,
                device_id=line.device_id,
                quantity=line.quantity,
                quantity_returned=0,
            ))
        if schedule:
            _notify(db, borrower.id, "Loan approved", "Your request matched the class schedule and was approved.", loan.id)
        record_audit(db, borrower, "loan.created", "loan_request", loan.id, {"status": loan.status.value})
        db.commit()
        db.refresh(loan)
        return loan
    except Exception:
        db.rollback()
        raise


def approve_loan(db: Session, actor: User, loan: LoanRequest) -> LoanRequest:
    try:
        claimed = db.execute(
            update(LoanRequest)
            .where(LoanRequest.id == loan.id, LoanRequest.status == LoanStatus.PENDING)
            .values(status=LoanStatus.APPROVED, reviewed_by=actor.id)
        ).rowcount
        if claimed != 1:
            _fail(409, "Only pending requests can be approved")
        details = db.scalars(select(LoanDetail).where(LoanDetail.loan_request_id == loan.id)).all()
        for line in details:
            changed = db.execute(
                update(Device)
                .where(
                    Device.id == line.device_id,
                    Device.status == DeviceStatus.AVAILABLE,
                    Device.quantity_available >= line.quantity,
                )
                .values(quantity_available=Device.quantity_available - line.quantity)
            ).rowcount
            if changed != 1:
                _fail(409, "Insufficient inventory to approve this request")
        loan.status = LoanStatus.APPROVED
        loan.reviewed_by = actor.id
        _notify(db, loan.requester_id, "Loan approved", "Your loan request was approved.", loan.id)
        record_audit(db, actor, "loan.approved", "loan_request", loan.id)
        db.commit()
        db.refresh(loan)
        return loan
    except Exception:
        db.rollback()
        raise


def reject_loan(db: Session, actor: User, loan: LoanRequest, reason: str | None) -> LoanRequest:
    if not reason or not reason.strip():
        _fail(422, "A rejection reason is required")
    claimed = db.execute(
        update(LoanRequest)
        .where(LoanRequest.id == loan.id, LoanRequest.status == LoanStatus.PENDING)
        .values(status=LoanStatus.REJECTED, reviewed_by=actor.id, rejection_reason=reason.strip())
    ).rowcount
    if claimed != 1:
        db.rollback()
        _fail(409, "Only pending requests can be rejected")
    loan.status = LoanStatus.REJECTED
    loan.reviewed_by = actor.id
    loan.rejection_reason = reason.strip()
    _notify(db, loan.requester_id, "Loan rejected", loan.rejection_reason, loan.id)
    record_audit(db, actor, "loan.rejected", "loan_request", loan.id, {"reason": loan.rejection_reason})
    db.commit()
    db.refresh(loan)
    return loan


def checkout_loan(db: Session, actor: User, loan: LoanRequest) -> LoanRequest:
    details = db.scalars(
        select(LoanDetail).where(LoanDetail.loan_request_id == loan.id)
    ).all()
    device_ids = sorted({line.device_id for line in details})
    devices = db.scalars(
        select(Device).where(Device.id.in_(device_ids)).order_by(Device.id).with_for_update()
    ).all()
    if any(device.status != DeviceStatus.AVAILABLE for device in devices):
        _fail(409, "A reserved device is no longer available for handover")
    checked_out_at = datetime.now(timezone.utc)
    changed = db.execute(
        update(LoanRequest)
        .where(LoanRequest.id == loan.id, LoanRequest.status == LoanStatus.APPROVED)
        .values(status=LoanStatus.CHECKED_OUT, checked_out_at=checked_out_at)
    ).rowcount
    if changed != 1:
        db.rollback()
        _fail(409, "Only approved requests can be checked out")
    loan.status = LoanStatus.CHECKED_OUT
    loan.checked_out_at = checked_out_at
    record_audit(db, actor, "loan.checked_out", "loan_request", loan.id)
    _notify(db, loan.requester_id, "Equipment checked out", "Equipment handover was confirmed.", loan.id)
    db.commit()
    db.refresh(loan)
    return loan


def return_loan(db: Session, actor: User, loan: LoanRequest) -> LoanRequest:
    try:
        changed = db.execute(
            update(LoanRequest)
            .where(
                LoanRequest.id == loan.id,
                LoanRequest.status.in_([LoanStatus.CHECKED_OUT, LoanStatus.OVERDUE]),
            )
            .values(status=LoanStatus.RETURNED, returned_at=datetime.now(timezone.utc))
        ).rowcount
        if changed != 1:
            _fail(409, "Only checked-out or overdue requests can be returned")
        details = db.scalars(select(LoanDetail).where(LoanDetail.loan_request_id == loan.id)).all()
        for line in details:
            device = db.scalar(select(Device).where(Device.id == line.device_id).with_for_update())
            if not device:
                _fail(409, "A device linked to this request no longer exists")
            outstanding = line.quantity - line.quantity_returned
            if outstanding <= 0:
                continue
            if device.quantity_available + outstanding > device.quantity_total:
                _fail(409, "Return would exceed total inventory")
            device.quantity_available += outstanding
            line.quantity_returned = line.quantity
        loan.status = LoanStatus.RETURNED
        loan.returned_at = datetime.now(timezone.utc)
        record_audit(db, actor, "loan.returned", "loan_request", loan.id)
        _notify(db, loan.requester_id, "Equipment returned", "Return was confirmed.", loan.id)
        db.commit()
        db.refresh(loan)
        return loan
    except Exception:
        db.rollback()
        raise
