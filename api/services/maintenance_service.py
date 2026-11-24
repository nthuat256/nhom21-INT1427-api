from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import (
    Device,
    DeviceStatus,
    MaintenanceRecord,
    MaintenanceStatus,
    MaintenanceUpdate,
    Notification,
    Role,
    User,
)
from api.utils.audit import record_audit


def report_damage(db: Session, actor: User, device_id: str, description: str) -> MaintenanceRecord:
    device = db.scalar(select(Device).where(Device.id == device_id).with_for_update())
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.status == DeviceStatus.RETIRED:
        raise HTTPException(status_code=409, detail="Retired devices cannot enter maintenance")
    active_record = db.scalar(select(MaintenanceRecord).where(
        MaintenanceRecord.device_id == device_id,
        MaintenanceRecord.status != MaintenanceStatus.COMPLETED,
    ))
    if active_record:
        raise HTTPException(status_code=409, detail="Device already has an active maintenance record")
    device.status = DeviceStatus.MAINTENANCE
    record = MaintenanceRecord(
        device_id=device_id,
        reported_by=actor.id,
        description=description,
        status=MaintenanceStatus.REPORTED,
    )
    db.add(record)
    db.flush()
    db.add(MaintenanceUpdate(
        maintenance_id=record.id,
        updated_by=actor.id,
        status=MaintenanceStatus.REPORTED,
        note=description,
    ))
    technicians = db.scalars(select(User).where(User.role == Role.TECHNICIAN, User.is_active.is_(True))).all()
    for technician in technicians:
        db.add(Notification(
            user_id=technician.id,
            title="Equipment reported for maintenance",
            message=f"Device {device.asset_tag} requires repair.",
            related_type="maintenance_record",
            related_id=record.id,
        ))
    record_audit(db, actor, "maintenance.reported", "maintenance_record", record.id)
    db.commit()
    db.refresh(record)
    return record


def update_maintenance(
    db: Session,
    actor: User,
    record: MaintenanceRecord,
    status_value: MaintenanceStatus | None,
    progress_note: str | None,
    inspection_passed: bool | None,
) -> MaintenanceRecord:
    target_status = status_value or record.status
    if record.status == MaintenanceStatus.REPORTED and target_status != MaintenanceStatus.ACCEPTED:
        raise HTTPException(status_code=409, detail="A technician must accept the report first")
    valid_transitions = {
        MaintenanceStatus.REPORTED: {MaintenanceStatus.ACCEPTED},
        MaintenanceStatus.ACCEPTED: {MaintenanceStatus.IN_PROGRESS},
        MaintenanceStatus.IN_PROGRESS: {MaintenanceStatus.IN_PROGRESS, MaintenanceStatus.COMPLETED},
        MaintenanceStatus.COMPLETED: set(),
    }
    if target_status != record.status and target_status not in valid_transitions[record.status]:
        raise HTTPException(status_code=409, detail="Invalid maintenance status transition")
    if record.status == MaintenanceStatus.REPORTED and target_status == MaintenanceStatus.ACCEPTED:
        record.technician_id = actor.id
    if record.technician_id and record.technician_id != actor.id:
        raise HTTPException(status_code=403, detail="Maintenance record is assigned to another technician")
    if target_status == MaintenanceStatus.COMPLETED and inspection_passed is not True:
        raise HTTPException(status_code=422, detail="Successful inspection is required before completion")
    record.status = target_status
    record.progress_note = progress_note if progress_note is not None else record.progress_note
    if inspection_passed is not None:
        record.inspection_passed = inspection_passed
    if target_status == MaintenanceStatus.COMPLETED:
        if not record.inspection_passed:
            raise HTTPException(status_code=422, detail="Successful inspection is required before completion")
        record.completed_at = datetime.now(timezone.utc)
        device = db.scalar(select(Device).where(Device.id == record.device_id).with_for_update())
        if not device:
            raise HTTPException(status_code=409, detail="Maintained device no longer exists")
        device.status = DeviceStatus.AVAILABLE
        db.add(Notification(
            user_id=record.reported_by,
            title="Maintenance completed",
            message=f"Device {device.asset_tag} passed inspection and is available again.",
            related_type="maintenance_record",
            related_id=record.id,
        ))
    db.add(MaintenanceUpdate(
        maintenance_id=record.id,
        updated_by=actor.id,
        status=target_status,
        note=progress_note,
        inspection_passed=inspection_passed,
    ))
    record_audit(db, actor, "maintenance.updated", "maintenance_record", record.id, {"status": target_status.value})
    db.commit()
    db.refresh(record)
    return record
