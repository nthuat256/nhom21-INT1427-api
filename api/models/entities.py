import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base
from api.types.utc_datetime import UTCDateTime


def new_id() -> str:
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    BORROWER = "BORROWER"
    ADMIN = "ADMIN"
    TECHNICIAN = "TECHNICIAN"


class DeviceStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    MAINTENANCE = "MAINTENANCE"
    RETIRED = "RETIRED"


class LoanStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHECKED_OUT = "CHECKED_OUT"
    RETURNED = "RETURNED"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class MaintenanceStatus(str, enum.Enum):
    REPORTED = "REPORTED"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.BORROWER, index=True)
    student_or_staff_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Room(TimestampMixin, Base):
    __tablename__ = "rooms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    location: Mapped[str | None] = mapped_column(String(255))
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)


class Device(TimestampMixin, Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    asset_tag: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), index=True)
    room_id: Mapped[str | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), index=True)
    quantity_total: Mapped[int] = mapped_column(Integer)
    quantity_available: Mapped[int] = mapped_column(Integer)
    status: Mapped[DeviceStatus] = mapped_column(Enum(DeviceStatus), default=DeviceStatus.AVAILABLE, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        CheckConstraint("quantity_total > 0", name="ck_device_total_positive"),
        CheckConstraint("quantity_available >= 0", name="ck_device_available_nonnegative"),
        CheckConstraint("quantity_available <= quantity_total", name="ck_device_available_lte_total"),
        Index("ix_devices_category_status", "category_id", "status"),
    )


class Schedule(TimestampMixin, Base):
    __tablename__ = "schedules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    course_name: Mapped[str] = mapped_column(String(180))
    course_code: Mapped[str] = mapped_column(String(80), index=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    instructor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (Index("ix_schedules_room_time", "room_id", "starts_at", "ends_at"),)


class LoanRequest(TimestampMixin, Base):
    __tablename__ = "loan_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), index=True)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[LoanStatus] = mapped_column(Enum(LoanStatus), default=LoanStatus.PENDING, index=True)
    matched_schedule_id: Mapped[str | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), index=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    checked_out_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    returned_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    details: Mapped[list["LoanDetail"]] = relationship(
        back_populates="loan_request", cascade="all, delete-orphan"
    )
    __table_args__ = (
        Index("ix_loans_room_period_status", "room_id", "starts_at", "due_at", "status"),
        Index("ix_loans_requester_status", "requester_id", "status"),
    )


class LoanDetail(Base):
    __tablename__ = "loan_details"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    loan_request_id: Mapped[str] = mapped_column(ForeignKey("loan_requests.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    quantity_returned: Mapped[int] = mapped_column(Integer, default=0)
    loan_request: Mapped[LoanRequest] = relationship(back_populates="details")
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_loan_detail_quantity_positive"),
        CheckConstraint("quantity_returned >= 0", name="ck_loan_detail_returned_nonnegative"),
        CheckConstraint("quantity_returned <= quantity", name="ck_loan_detail_returned_lte_quantity"),
        UniqueConstraint("loan_request_id", "device_id", name="uq_loan_device"),
    )


class MaintenanceRecord(TimestampMixin, Base):
    __tablename__ = "maintenance_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"), index=True)
    reported_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    technician_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[MaintenanceStatus] = mapped_column(Enum(MaintenanceStatus), default=MaintenanceStatus.REPORTED, index=True)
    progress_note: Mapped[str | None] = mapped_column(Text)
    inspection_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class MaintenanceUpdate(Base):
    __tablename__ = "maintenance_updates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    maintenance_id: Mapped[str] = mapped_column(
        ForeignKey("maintenance_records.id", ondelete="CASCADE"), index=True
    )
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    status: Mapped[MaintenanceStatus] = mapped_column(Enum(MaintenanceStatus))
    note: Mapped[str | None] = mapped_column(Text)
    inspection_passed: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    related_type: Mapped[str | None] = mapped_column(String(60))
    related_id: Mapped[str | None] = mapped_column(String(36))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now(), index=True)


class Setting(TimestampMixin, Base):
    __tablename__ = "settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(Text)
