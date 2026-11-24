from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.database import get_db
from api.dependencies import get_current_user, require_roles
from api.models import (
    Category, Device, DeviceStatus, MaintenanceRecord, MaintenanceStatus,
    Role, Room, Schedule, Setting, User,
)
from api.utils.audit import record_audit
from api.utils.pagination import paginate
from api.validators.schemas import (
    CategoryCreate, CategoryRead, CategoryUpdate, DeviceCreate, DeviceRead,
    DeviceUpdate, RoomCreate, RoomRead, RoomUpdate, ScheduleCreate,
    ScheduleRead, ScheduleUpdate, SettingCreate, SettingRead, SettingUpdate,
    UserRead, UserUpdate,
)

router = APIRouter(tags=["Resources"])
admin_only = require_roles(Role.ADMIN)


def ensure_schedule_has_no_conflict(
    db: Session,
    room_id: str,
    starts_at: datetime,
    ends_at: datetime,
    exclude_id: str | None = None,
) -> None:
    query = select(Schedule.id).where(
        Schedule.room_id == room_id,
        Schedule.is_active.is_(True),
        Schedule.starts_at < ends_at,
        Schedule.ends_at > starts_at,
    )
    if exclude_id:
        query = query.where(Schedule.id != exclude_id)
    if db.scalar(query.limit(1)):
        raise HTTPException(status_code=409, detail="Schedule overlaps another active schedule in this room")


@router.get("/users", response_model=dict)
def list_users(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    q: str | None = None, role: Role | None = None,
    db: Session = Depends(get_db), _: User = Depends(admin_only),
):
    query = select(User)
    if q:
        query = query.where(or_(User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    if role:
        query = query.where(User.role == role)
    result = paginate(db, User, page, page_size, query.order_by(User.created_at.desc()))
    return {**result, "items": [UserRead.model_validate(item) for item in result["items"]]}


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: str, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: str, payload: UserUpdate, db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    record_audit(db, actor, "user.updated", "user", user.id, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(user)
    return user


@router.get("/rooms", response_model=dict)
def list_rooms(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    q: str | None = None, active: bool | None = None,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    query = select(Room)
    if q:
        query = query.where(or_(Room.code.ilike(f"%{q}%"), Room.name.ilike(f"%{q}%")))
    if active is not None:
        query = query.where(Room.is_active == active)
    result = paginate(db, Room, page, page_size, query.order_by(Room.code))
    return {**result, "items": [RoomRead.model_validate(item) for item in result["items"]]}


@router.post("/rooms", response_model=RoomRead, status_code=201)
def create_room(payload: RoomCreate, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    room = Room(**payload.model_dump())
    db.add(room)
    db.flush()
    record_audit(db, actor, "room.created", "room", room.id)
    db.commit()
    db.refresh(room)
    return room


@router.get("/rooms/{room_id}", response_model=RoomRead)
def get_room(room_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.patch("/rooms/{room_id}", response_model=RoomRead)
def update_room(room_id: str, payload: RoomUpdate, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(room, key, value)
    record_audit(db, actor, "room.updated", "room", room.id)
    db.commit()
    db.refresh(room)
    return room


@router.delete("/rooms/{room_id}", status_code=204)
def delete_room(room_id: str, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    room.is_active = False
    record_audit(db, actor, "room.deactivated", "room", room.id)
    db.commit()


@router.get("/categories", response_model=dict)
def list_categories(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    q: str | None = None, db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(Category)
    if q:
        query = query.where(Category.name.ilike(f"%{q}%"))
    result = paginate(db, Category, page, page_size, query.order_by(Category.name))
    return {**result, "items": [CategoryRead.model_validate(item) for item in result["items"]]}


@router.post("/categories", response_model=CategoryRead, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    category = Category(**payload.model_dump())
    db.add(category)
    db.flush()
    record_audit(db, actor, "category.created", "category", category.id)
    db.commit()
    db.refresh(category)
    return category


@router.get("/categories/{category_id}", response_model=CategoryRead)
def get_category(category_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.patch("/categories/{category_id}", response_model=CategoryRead)
def update_category(category_id: str, payload: CategoryUpdate, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, key, value)
    record_audit(db, actor, "category.updated", "category", category.id)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: str, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    try:
        db.delete(category)
        record_audit(db, actor, "category.deleted", "category", category_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category is referenced by devices") from exc


@router.get("/devices", response_model=dict)
def list_devices(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    q: str | None = None, category_id: str | None = None,
    room_id: str | None = None, device_status: DeviceStatus | None = Query(default=None, alias="status"),
    available_only: bool = False, db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(Device)
    if q:
        query = query.where(or_(Device.name.ilike(f"%{q}%"), Device.asset_tag.ilike(f"%{q}%")))
    if category_id:
        query = query.where(Device.category_id == category_id)
    if room_id:
        query = query.where(Device.room_id == room_id)
    if device_status:
        query = query.where(Device.status == device_status)
    if available_only:
        query = query.where(Device.status == DeviceStatus.AVAILABLE, Device.quantity_available > 0)
    result = paginate(db, Device, page, page_size, query.order_by(Device.name))
    return {**result, "items": [DeviceRead.model_validate(item) for item in result["items"]]}


@router.post("/devices", response_model=DeviceRead, status_code=201)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    if not db.get(Category, payload.category_id):
        raise HTTPException(status_code=404, detail="Category not found")
    if payload.room_id and not db.get(Room, payload.room_id):
        raise HTTPException(status_code=404, detail="Room not found")
    device = Device(
        **payload.model_dump(),
        quantity_available=payload.quantity_total,
        status=DeviceStatus.AVAILABLE,
    )
    db.add(device)
    db.flush()
    record_audit(db, actor, "device.created", "device", device.id)
    db.commit()
    db.refresh(device)
    return device


@router.get("/devices/{device_id}", response_model=DeviceRead)
def get_device(device_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.patch("/devices/{device_id}", response_model=DeviceRead)
def update_device(device_id: str, payload: DeviceUpdate, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("category_id") and not db.get(Category, changes["category_id"]):
        raise HTTPException(status_code=404, detail="Category not found")
    if changes.get("room_id") and not db.get(Room, changes["room_id"]):
        raise HTTPException(status_code=404, detail="Room not found")
    if "quantity_total" in changes:
        borrowed_or_reserved = device.quantity_total - device.quantity_available
        if changes["quantity_total"] < borrowed_or_reserved:
            raise HTTPException(status_code=409, detail="Total quantity cannot be lower than borrowed or reserved quantity")
        device.quantity_available = changes["quantity_total"] - borrowed_or_reserved
    for key, value in changes.items():
        if key != "quantity_total":
            setattr(device, key, value)
    record_audit(db, actor, "device.updated", "device", device.id, changes)
    db.commit()
    db.refresh(device)
    return device


@router.delete("/devices/{device_id}", status_code=204)
def retire_device(device_id: str, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.quantity_available != device.quantity_total:
        raise HTTPException(status_code=409, detail="Cannot retire a device with borrowed or reserved units")
    if device.status == DeviceStatus.MAINTENANCE:
        raise HTTPException(status_code=409, detail="Cannot retire a device during maintenance")
    active_maintenance = db.scalar(select(MaintenanceRecord.id).where(
        MaintenanceRecord.device_id == device.id,
        MaintenanceRecord.status != MaintenanceStatus.COMPLETED,
    ).limit(1))
    if active_maintenance:
        raise HTTPException(status_code=409, detail="Cannot retire a device with active maintenance")
    device.status = DeviceStatus.RETIRED
    record_audit(db, actor, "device.retired", "device", device.id)
    db.commit()


@router.get("/schedules", response_model=dict)
def list_schedules(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    room_id: str | None = None, course_code: str | None = None,
    starts_after: datetime | None = None, ends_before: datetime | None = None,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    query = select(Schedule)
    if room_id:
        query = query.where(Schedule.room_id == room_id)
    if course_code:
        query = query.where(Schedule.course_code.ilike(f"%{course_code}%"))
    if starts_after:
        query = query.where(Schedule.starts_at >= starts_after)
    if ends_before:
        query = query.where(Schedule.ends_at <= ends_before)
    result = paginate(db, Schedule, page, page_size, query.order_by(Schedule.starts_at))
    return {**result, "items": [ScheduleRead.model_validate(item) for item in result["items"]]}


@router.post("/schedules", response_model=ScheduleRead, status_code=201)
def create_schedule(payload: ScheduleCreate, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    if not db.get(Room, payload.room_id):
        raise HTTPException(status_code=404, detail="Room not found")
    if payload.is_active:
        ensure_schedule_has_no_conflict(db, payload.room_id, payload.starts_at, payload.ends_at)
    if payload.instructor_id and not db.get(User, payload.instructor_id):
        raise HTTPException(status_code=404, detail="Instructor not found")
    schedule = Schedule(**payload.model_dump())
    db.add(schedule)
    db.flush()
    record_audit(db, actor, "schedule.created", "schedule", schedule.id)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.get("/schedules/{schedule_id}", response_model=ScheduleRead)
def get_schedule(schedule_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.patch("/schedules/{schedule_id}", response_model=ScheduleRead)
def update_schedule(schedule_id: str, payload: ScheduleUpdate, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    changes = payload.model_dump(exclude_unset=True)
    start = changes.get("starts_at", schedule.starts_at)
    end = changes.get("ends_at", schedule.ends_at)
    room_id = changes.get("room_id", schedule.room_id)
    if end <= start:
        raise HTTPException(status_code=422, detail="ends_at must be later than starts_at")
    if "room_id" in changes and not db.get(Room, room_id):
        raise HTTPException(status_code=404, detail="Room not found")
    if changes.get("instructor_id") and not db.get(User, changes["instructor_id"]):
        raise HTTPException(status_code=404, detail="Instructor not found")
    if changes.get("is_active", schedule.is_active):
        ensure_schedule_has_no_conflict(db, room_id, start, end, schedule.id)
    for key, value in changes.items():
        setattr(schedule, key, value)
    record_audit(db, actor, "schedule.updated", "schedule", schedule.id)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: str, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule.is_active = False
    record_audit(db, actor, "schedule.deactivated", "schedule", schedule.id)
    db.commit()


@router.get("/settings", response_model=dict)
def list_settings(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return {"items": db.scalars(select(Setting).order_by(Setting.key)).all()}


@router.put("/settings/{key}", response_model=SettingRead)
def upsert_setting(key: str, payload: SettingCreate, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    if key != payload.key:
        raise HTTPException(status_code=422, detail="Path key must match payload key")
    setting = db.scalar(select(Setting).where(Setting.key == key))
    if setting:
        setting.value = payload.value
        setting.description = payload.description
    else:
        setting = Setting(**payload.model_dump())
        db.add(setting)
    db.flush()
    record_audit(db, actor, "setting.upserted", "setting", setting.id, {"key": key})
    db.commit()
    db.refresh(setting)
    return setting


@router.patch("/settings/{key}", response_model=SettingRead)
def update_setting(key: str, payload: SettingUpdate, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    setting = db.scalar(select(Setting).where(Setting.key == key))
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    setting.value = payload.value
    if payload.description is not None:
        setting.description = payload.description
    record_audit(db, actor, "setting.updated", "setting", setting.id, {"key": key})
    db.commit()
    db.refresh(setting)
    return setting


@router.delete("/settings/{key}", status_code=204)
def delete_setting(key: str, db: Session = Depends(get_db), actor: User = Depends(admin_only)):
    setting = db.scalar(select(Setting).where(Setting.key == key))
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    record_audit(db, actor, "setting.deleted", "setting", setting.id, {"key": key})
    db.delete(setting)
    db.commit()
