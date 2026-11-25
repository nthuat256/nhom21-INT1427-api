from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from api.models import DeviceStatus, LoanStatus, MaintenanceStatus, Role


def _reject_null_fields(model: BaseModel, fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in model.model_fields_set and getattr(model, field) is None:
            raise ValueError(f"{field} cannot be null")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class RegisterInput(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=10, max_length=72)
    student_or_staff_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def password_fits_bcrypt(self):
        if len(self.password.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return self


class UserRead(ORMModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role
    student_or_staff_id: str | None
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    role: Role | None = None
    is_active: bool | None = None
    student_or_staff_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_non_nullable_fields(self):
        _reject_null_fields(self, ("full_name", "role", "is_active"))
        return self


class TokenRead(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RoomCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    location: str | None = None
    capacity: int = Field(default=1, ge=1)
    is_active: bool = True


class RoomUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    location: str | None = None
    capacity: int | None = Field(default=None, ge=1)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_non_nullable_fields(self):
        _reject_null_fields(self, ("code", "name", "capacity", "is_active"))
        return self


class RoomRead(ORMModel):
    id: str
    code: str
    name: str
    location: str | None
    capacity: int
    is_active: bool
    created_at: datetime


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None

    @model_validator(mode="after")
    def validate_non_nullable_fields(self):
        _reject_null_fields(self, ("name",))
        return self


class CategoryRead(ORMModel):
    id: str
    name: str
    description: str | None
    created_at: datetime


class DeviceCreate(BaseModel):
    asset_tag: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    description: str | None = None
    category_id: str
    room_id: str | None = None
    quantity_total: int = Field(ge=1)


class DeviceUpdate(BaseModel):
    asset_tag: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    category_id: str | None = None
    room_id: str | None = None
    quantity_total: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_non_nullable_fields(self):
        _reject_null_fields(self, ("asset_tag", "name", "category_id", "quantity_total"))
        return self


class DeviceRead(ORMModel):
    id: str
    asset_tag: str
    name: str
    description: str | None
    category_id: str
    room_id: str | None
    quantity_total: int
    quantity_available: int
    status: DeviceStatus
    created_at: datetime


class ScheduleCreate(BaseModel):
    course_name: str = Field(min_length=1, max_length=180)
    course_code: str = Field(min_length=1, max_length=80)
    room_id: str
    instructor_id: str | None = None
    starts_at: datetime
    ends_at: datetime
    is_active: bool = True

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalize_schedule_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("Schedule timestamps must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class ScheduleUpdate(BaseModel):
    course_name: str | None = Field(default=None, min_length=1, max_length=180)
    course_code: str | None = Field(default=None, min_length=1, max_length=80)
    room_id: str | None = None
    instructor_id: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_non_nullable_fields(self):
        _reject_null_fields(
            self,
            ("course_name", "course_code", "room_id", "starts_at", "ends_at", "is_active"),
        )
        return self

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalize_optional_schedule_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("Schedule timestamps must include a timezone")
        return value.astimezone(timezone.utc)


class ScheduleRead(ORMModel):
    id: str
    course_name: str
    course_code: str
    room_id: str
    instructor_id: str | None
    starts_at: datetime
    ends_at: datetime
    is_active: bool


class LoanLineInput(BaseModel):
    device_id: str
    quantity: int = Field(ge=1)


class LoanCreate(BaseModel):
    room_id: str
    starts_at: datetime
    due_at: datetime
    reason: str | None = Field(default=None, max_length=2000)
    details: list[LoanLineInput] = Field(min_length=1)

    @field_validator("starts_at", "due_at")
    @classmethod
    def normalize_loan_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("Loan timestamps must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def valid_request(self):
        if self.due_at <= self.starts_at:
            raise ValueError("due_at must be later than starts_at")
        if self.starts_at <= datetime.now(timezone.utc):
            raise ValueError("starts_at must be in the future")
        if len({line.device_id for line in self.details}) != len(self.details):
            raise ValueError("Each device may appear only once")
        return self


class LoanDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class LoanDetailRead(ORMModel):
    id: str
    loan_request_id: str
    device_id: str
    quantity: int
    quantity_returned: int


class LoanRead(ORMModel):
    id: str
    requester_id: str
    room_id: str
    starts_at: datetime
    due_at: datetime
    reason: str | None
    status: LoanStatus
    matched_schedule_id: str | None
    reviewed_by: str | None
    rejection_reason: str | None
    checked_out_at: datetime | None
    returned_at: datetime | None
    created_at: datetime
    details: list[LoanDetailRead] = Field(default_factory=list)


class MaintenanceCreate(BaseModel):
    device_id: str
    description: str = Field(min_length=3, max_length=5000)


class MaintenanceUpdate(BaseModel):
    status: MaintenanceStatus | None = None
    progress_note: str | None = Field(default=None, max_length=5000)
    inspection_passed: bool | None = None


class MaintenanceRead(ORMModel):
    id: str
    device_id: str
    reported_by: str
    technician_id: str | None
    description: str
    status: MaintenanceStatus
    progress_note: str | None
    inspection_passed: bool
    completed_at: datetime | None
    created_at: datetime


class NotificationRead(ORMModel):
    id: str
    user_id: str
    title: str
    message: str
    is_read: bool
    related_type: str | None
    related_id: str | None
    created_at: datetime


class SettingCreate(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    value: dict[str, Any]
    description: str | None = None


class SettingUpdate(BaseModel):
    value: dict[str, Any]
    description: str | None = None


class SettingRead(ORMModel):
    id: str
    key: str
    value: dict[str, Any]
    description: str | None


class Page(BaseModel):
    items: list[Any]
    page: int
    page_size: int
    total: int
