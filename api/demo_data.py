from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.models import (
    AuditLog,
    Category,
    Device,
    DeviceStatus,
    LoanDetail,
    LoanRequest,
    LoanStatus,
    MaintenanceRecord,
    MaintenanceStatus,
    MaintenanceUpdate,
    Notification,
    Role,
    Room,
    Schedule,
    Setting,
    User,
)
from api.security import hash_password

SAMPLE_PASSWORD = "LabEquip123!"

BORROWER_ACCOUNTS = (
    ("tran.van.binh@university.edu", "Trần Văn Bình - Sinh viên", "SV2025001"),
    ("nguyen.thi.hoa@university.edu", "Nguyễn Thị Hoa - Sinh viên", "SV2025002"),
    ("le.minh.tuan@university.edu", "Lê Minh Tuấn - Sinh viên", "SV2025003"),
    ("pham.ngoc.anh@university.edu", "Phạm Ngọc Anh - Sinh viên", "SV2025004"),
    ("hoang.quoc.viet@university.edu", "Hoàng Quốc Việt - Sinh viên", "SV2025005"),
    ("vu.thi.thao@university.edu", "Vũ Thị Thảo - Sinh viên", "SV2025006"),
    ("do.minh.khang@university.edu", "Đỗ Minh Khang - Sinh viên", "SV2025007"),
    ("bui.thu.trang@university.edu", "Bùi Thu Trang - Sinh viên", "SV2025008"),
    ("dang.duc.long@university.edu", "Đặng Đức Long - Sinh viên", "SV2025009"),
    ("ngo.phuong.linh@university.edu", "Ngô Phương Linh - Sinh viên", "SV2025010"),
    ("duong.gia.huy@university.edu", "Dương Gia Huy - Sinh viên", "SV2025011"),
    ("ly.thanh.ha@university.edu", "Lý Thanh Hà - Sinh viên", "SV2025012"),
    ("mai.tuan.kiet@university.edu", "Mai Tuấn Kiệt - Sinh viên", "SV2025013"),
    ("trinh.ngoc.mai@university.edu", "Trịnh Ngọc Mai - Sinh viên", "SV2025014"),
    ("truong.hai.nam@university.edu", "Trương Hải Nam - Sinh viên", "SV2025015"),
    ("phan.thi.yen@university.edu", "Phan Thị Yến - Sinh viên", "SV2025016"),
    ("cao.anh.khoa@university.edu", "Cao Anh Khoa - Sinh viên", "SV2025017"),
    ("ho.thi.kim.ngan@university.edu", "Hồ Thị Kim Ngân - Sinh viên", "SV2025018"),
    ("dang.huu.phuc@university.edu", "Đặng Hữu Phúc - Sinh viên", "SV2025019"),
    ("la.my.dung@university.edu", "La Mỹ Dung - Sinh viên", "SV2025020"),
    ("vo.thanh.dat@university.edu", "Võ Thành Đạt - Sinh viên", "SV2025021"),
    ("dinh.thi.quynh@university.edu", "Đinh Thị Quỳnh - Sinh viên", "SV2025022"),
    ("tran.huu.nhan@university.edu", "Trần Hữu Nhân - Sinh viên", "SV2025023"),
    ("nguyen.tuan.kiet@university.edu", "Nguyễn Tuấn Kiệt - Sinh viên", "SV2025024"),
    ("le.thi.thanh@university.edu", "Lê Thị Thanh - Sinh viên", "SV2025025"),
    ("pham.gia.bao@university.edu", "Phạm Gia Bảo - Sinh viên", "SV2025026"),
    ("nguyen.viet.khoa@university.edu", "Nguyễn Việt Khoa - Giảng viên", "GV2025001"),
    ("tran.thi.lan@university.edu", "Trần Thị Lan - Giảng viên", "GV2025002"),
    ("le.quang.huy@university.edu", "Lê Quang Huy - Giảng viên", "GV2025003"),
    ("vo.thi.hong@university.edu", "Võ Thị Hồng - Giảng viên", "GV2025004"),
)

SCHOOL_ACCOUNT = (
    "nguyen.thi.lan@university.edu",
    "Nguyễn Thị Lan - Cán bộ nhà trường",
    SAMPLE_PASSWORD,
    Role.ADMIN,
    "QL2025001",
)

OPERATOR_ACCOUNTS = (
    ("le.quoc.huy@university.edu", "Lê Quốc Huy - Kỹ thuật viên thiết bị", "KT2025001"),
    ("pham.minh.khoa@university.edu", "Phạm Minh Khoa - Kỹ thuật viên điện tử", "KT2025002"),
    ("nguyen.tien.dung@university.edu", "Nguyễn Tiến Dũng - Kỹ thuật viên mạng", "KT2025003"),
    ("do.thanh.tung@university.edu", "Đỗ Thanh Tùng - Kỹ thuật viên phòng thí nghiệm", "KT2025004"),
    ("vu.hoang.nam@university.edu", "Vũ Hoàng Nam - Kỹ thuật viên thiết bị", "KT2025005"),
)

SAMPLE_ACCOUNTS = (
    *((email, name, SAMPLE_PASSWORD, Role.BORROWER, staff_id) for email, name, staff_id in BORROWER_ACCOUNTS),
    SCHOOL_ACCOUNT,
    *((email, name, SAMPLE_PASSWORD, Role.TECHNICIAN, staff_id) for email, name, staff_id in OPERATOR_ACCOUNTS),
)

QUICK_LOGIN_ACCOUNTS = (
    SAMPLE_ACCOUNTS[0],
    SCHOOL_ACCOUNT,
    SAMPLE_ACCOUNTS[-len(OPERATOR_ACCOUNTS)],
)

LEGACY_ACCOUNT_EMAILS = {
    "tran.van.binh@university.edu": ("demo.user@university.edu",),
    "nguyen.thi.lan@university.edu": ("demo.school@university.edu",),
    "le.quoc.huy@university.edu": ("demo.operator@university.edu",),
}

ROOMS = (
    ("MAU-A101", "Phòng thực hành máy tính A101", "Tòa A - Tầng 1", 36, True, ("LAB-DEMO",)),
    ("MAU-B202", "Phòng thực hành điện tử B202", "Tòa B - Tầng 2", 28, True, ()),
    ("MAU-C303", "Phòng thiết bị đa phương tiện C303", "Tòa C - Tầng 3", 24, True, ()),
    ("MAU-D404", "Kho thiết bị D404", "Tòa D - Tầng 4", 12, False, ()),
)

CATEGORIES = (
    ("Máy tính - Thực hành", "Máy tính phục vụ các học phần thực hành.", ()),
    ("Thiết bị trình chiếu - Thực hành", "Máy chiếu và thiết bị hiển thị.", ("Demo peripherals",)),
    ("Thiết bị đo lường - Thực hành", "Thiết bị đo và kiểm tra mạch điện.", ()),
    ("Dụng cụ điện tử - Thực hành", "Bộ kit và dụng cụ thực hành điện tử.", ()),
)

DEVICES = (
    ("MAU-LT-A101-001", "Máy tính xách tay Dell Latitude", "Máy tính thực hành cài sẵn bộ công cụ học tập.", "Máy tính - Thực hành", "MAU-A101", 20, 17, DeviceStatus.AVAILABLE, ("DEMO-DEVICE-001",)),
    ("MAU-MC-B202-001", "Máy chiếu Epson PowerLite", "Máy chiếu phục vụ bài giảng và báo cáo.", "Thiết bị trình chiếu - Thực hành", "MAU-B202", 5, 5, DeviceStatus.AVAILABLE, ()),
    ("MAU-OSC-C303-001", "Máy hiện sóng Rigol", "Máy hiện sóng số dùng trong thực hành điện tử.", "Thiết bị đo lường - Thực hành", "MAU-C303", 3, 3, DeviceStatus.AVAILABLE, ()),
    ("MAU-ARD-A101-001", "Bộ kit Arduino Uno", "Bộ vi điều khiển phục vụ học phần IoT.", "Dụng cụ điện tử - Thực hành", "MAU-A101", 12, 12, DeviceStatus.AVAILABLE, ()),
    ("MAU-MC-A101-002", "Máy chiếu cần kiểm tra bóng đèn", "Hình ảnh mờ, cần kiểm tra cụm bóng đèn.", "Thiết bị trình chiếu - Thực hành", "MAU-A101", 2, 2, DeviceStatus.MAINTENANCE, ()),
    ("MAU-3D-C303-001", "Máy in 3D Creality Ender", "Trục chuyển động phát tiếng ồn khi vận hành.", "Dụng cụ điện tử - Thực hành", "MAU-C303", 1, 1, DeviceStatus.MAINTENANCE, ()),
    ("MAU-NGUON-B202-001", "Bộ nguồn DC chỉnh áp", "Cần thay thế đầu nối nguồn đầu ra.", "Thiết bị đo lường - Thực hành", "MAU-B202", 4, 4, DeviceStatus.MAINTENANCE, ()),
    ("MAU-CAM-C303-001", "Camera ghi hình bài giảng", "Camera đã sửa xong và chờ bàn giao.", "Thiết bị trình chiếu - Thực hành", "MAU-C303", 2, 2, DeviceStatus.AVAILABLE, ()),
    ("MAU-PC-D404-001", "Máy tính để bàn đời cũ", "Thiết bị ngừng sử dụng, lưu tại kho.", "Máy tính - Thực hành", "MAU-D404", 1, 0, DeviceStatus.RETIRED, ()),
)

SCHEDULES = (
    ("MAU-IT205-TH01", "Lập trình Python - Thực hành", "IT205", "MAU-A101", 0, 4, 9, True, ("DEMO101",)),
    ("MAU-DT101-TH01", "Điện tử cơ bản - Thực hành", "DT101", "MAU-B202", 1, 5, 13, True, ()),
    ("MAU-MM101-TH01", "Sản xuất đa phương tiện", "MM101", "MAU-C303", 2, 6, 9, True, ()),
)


def _upsert_named(db: Session, model, field, value: str, aliases: tuple[str, ...] = ()):
    record = db.scalar(
        select(model).where(field.in_((value, *aliases))).limit(1)
    )
    if record is None:
        record = model()
        db.add(record)
    setattr(record, field.key, value)
    return record


def _upsert_user(db: Session, account) -> User:
    email, full_name, password, role, staff_id = account
    user = None
    for candidate in (email, *LEGACY_ACCOUNT_EMAILS.get(email, ())):
        user = db.scalar(select(User).where(func.lower(User.email) == candidate.lower()))
        if user:
            break
    if user is None:
        user = User(email=email)
        db.add(user)
    user.email = email
    user.full_name = full_name
    user.password_hash = hash_password(password)
    user.role = role
    user.student_or_staff_id = staff_id
    user.is_active = True
    return user


def _upsert_audit(db: Session, actor_id: str, action: str, entity_type: str, entity_id: str, details: dict):
    log = db.scalar(
        select(AuditLog).where(
            AuditLog.action == action,
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )
    )
    if log is None:
        log = AuditLog(action=action, entity_type=entity_type, entity_id=entity_id)
        db.add(log)
    log.actor_id = actor_id
    log.details = details


def _upsert_notification(
    db: Session,
    user_id: str,
    related_type: str,
    related_id: str,
    title: str,
    message: str,
    is_read: bool,
):
    notification = db.scalar(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.related_type == related_type,
            Notification.related_id == related_id,
        )
    )
    if notification is None:
        notification = Notification(
            user_id=user_id,
            related_type=related_type,
            related_id=related_id,
            title=title,
            message=message,
        )
        db.add(notification)
    notification.title = title
    notification.message = message
    notification.is_read = is_read


def _seed_loans(
    db: Session,
    borrowers: list[User],
    school: User,
    rooms: dict[str, Room],
    schedules: dict[str, Schedule],
    device: Device,
    now: datetime,
):
    scheduled = schedules["MAU-IT205-TH01"]
    cases = (
        ("Mẫu: yêu cầu đang chờ duyệt", 1, "MAU-A101", LoanStatus.PENDING, now + timedelta(days=6), None, None, None, None, None),
        ("Mẫu: đã duyệt theo lịch học", 0, "MAU-A101", LoanStatus.APPROVED, scheduled.starts_at + timedelta(minutes=15), scheduled.id, school.id, None, None, None),
        ("Mẫu: yêu cầu bị từ chối", 2, "MAU-A101", LoanStatus.REJECTED, now + timedelta(days=8), None, school.id, "Thiết bị đã được bố trí cho lớp học khác.", None, None),
        ("Mẫu: thiết bị đang được mượn", 3, "MAU-A101", LoanStatus.CHECKED_OUT, now - timedelta(days=1), None, None, None, now - timedelta(days=1), None),
        ("Mẫu: phiếu mượn đã hoàn trả", 4, "MAU-A101", LoanStatus.RETURNED, now - timedelta(days=8), None, school.id, None, now - timedelta(days=7), now - timedelta(days=6)),
        ("Mẫu: phiếu mượn quá hạn", 5, "MAU-A101", LoanStatus.OVERDUE, now - timedelta(days=5), None, None, None, now - timedelta(days=4), None),
        ("Mẫu: yêu cầu đã hủy", 6, "MAU-A101", LoanStatus.CANCELLED, now + timedelta(days=10), None, None, None, None, None),
    )
    action_by_status = {
        LoanStatus.PENDING: "loan.created",
        LoanStatus.APPROVED: "loan.approved",
        LoanStatus.REJECTED: "loan.rejected",
        LoanStatus.CHECKED_OUT: "loan.checked_out",
        LoanStatus.RETURNED: "loan.returned",
        LoanStatus.OVERDUE: "loan.overdue",
        LoanStatus.CANCELLED: "loan.cancelled",
    }
    notification_copy = {
        LoanStatus.PENDING: ("Yêu cầu mượn đang chờ duyệt", "Nhà trường sẽ xem xét yêu cầu của bạn."),
        LoanStatus.APPROVED: ("Yêu cầu mượn đã được duyệt", "Thiết bị đã được giữ theo lịch học."),
        LoanStatus.REJECTED: ("Yêu cầu mượn bị từ chối", "Vui lòng xem lý do trong chi tiết phiếu."),
        LoanStatus.CHECKED_OUT: ("Đang mượn thiết bị", "Hãy hoàn trả thiết bị trước hạn."),
        LoanStatus.RETURNED: ("Đã hoàn trả thiết bị", "Phiếu mượn đã hoàn tất."),
        LoanStatus.OVERDUE: ("Phiếu mượn quá hạn", "Vui lòng liên hệ nhà trường để hoàn trả thiết bị."),
        LoanStatus.CANCELLED: ("Yêu cầu mượn đã hủy", "Phiếu mượn đã được hủy."),
    }
    now = now.replace(microsecond=0)
    for marker, borrower_index, room_code, status, starts_at, schedule_id, reviewer_id, rejection, checked_out_at, returned_at in cases:
        loan = db.scalar(select(LoanRequest).where(LoanRequest.reason == marker))
        if loan is None:
            loan = LoanRequest(requester_id=borrowers[borrower_index].id, room_id=rooms[room_code].id)
            db.add(loan)
        loan.requester_id = borrowers[borrower_index].id
        loan.room_id = rooms[room_code].id
        loan.starts_at = starts_at.replace(microsecond=0)
        loan.due_at = (
            schedules["MAU-IT205-TH01"].ends_at
            if schedule_id
            else now + timedelta(days=1)
            if status == LoanStatus.CHECKED_OUT
            else starts_at + timedelta(days=4)
            if status == LoanStatus.OVERDUE
            else starts_at + timedelta(days=5)
            if status == LoanStatus.RETURNED
            else starts_at + timedelta(hours=2)
        ).replace(microsecond=0)
        loan.reason = marker
        loan.status = status
        loan.matched_schedule_id = schedule_id
        loan.reviewed_by = reviewer_id
        loan.rejection_reason = rejection
        loan.checked_out_at = checked_out_at
        loan.returned_at = returned_at
        db.flush()

        detail = db.scalar(
            select(LoanDetail).where(
                LoanDetail.loan_request_id == loan.id,
                LoanDetail.device_id == device.id,
            )
        )
        if detail is None:
            detail = LoanDetail(loan_request_id=loan.id, device_id=device.id, quantity=1)
            db.add(detail)
        detail.quantity = 1
        detail.quantity_returned = 1 if status == LoanStatus.RETURNED else 0

        _upsert_audit(
            db,
            reviewer_id or borrowers[borrower_index].id,
            action_by_status[status],
            "loan_request",
            loan.id,
            {"sample": True, "status": status.value},
        )
        title, message = notification_copy[status]
        _upsert_notification(
            db,
            borrowers[borrower_index].id,
            "loan_request",
            loan.id,
            title,
            message,
            is_read=status in {LoanStatus.APPROVED, LoanStatus.REJECTED, LoanStatus.RETURNED, LoanStatus.CANCELLED},
        )


def _seed_maintenance(db: Session, school: User, operators: list[User], devices: dict[str, Device]):
    cases = (
        ("Mẫu bảo trì: máy chiếu cần tiếp nhận", "MAU-MC-A101-002", MaintenanceStatus.REPORTED, None),
        ("Mẫu bảo trì: máy in 3D đã tiếp nhận", "MAU-3D-C303-001", MaintenanceStatus.ACCEPTED, 0),
        ("Mẫu bảo trì: bộ nguồn đang sửa", "MAU-NGUON-B202-001", MaintenanceStatus.IN_PROGRESS, 1),
        ("Mẫu bảo trì: camera đã sửa xong", "MAU-CAM-C303-001", MaintenanceStatus.COMPLETED, 2),
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    records = []
    for description, asset_tag, status, operator_index in cases:
        device = devices[asset_tag]
        record = db.scalar(select(MaintenanceRecord).where(MaintenanceRecord.description == description))
        if record is None:
            record = MaintenanceRecord(device_id=device.id, reported_by=school.id, description=description)
            db.add(record)
        record.device_id = device.id
        record.reported_by = school.id
        record.technician_id = operators[operator_index].id if operator_index is not None else None
        record.description = description
        record.status = status
        record.progress_note = {
            MaintenanceStatus.REPORTED: None,
            MaintenanceStatus.ACCEPTED: "Đã kiểm tra thông tin và lên kế hoạch sửa chữa.",
            MaintenanceStatus.IN_PROGRESS: "Đang thay linh kiện và kiểm tra nguồn.",
            MaintenanceStatus.COMPLETED: "Đã thay cáp, chạy thử và xác nhận hoạt động ổn định.",
        }[status]
        record.inspection_passed = status == MaintenanceStatus.COMPLETED
        record.completed_at = now - timedelta(days=1) if status == MaintenanceStatus.COMPLETED else None
        device.status = DeviceStatus.AVAILABLE if status == MaintenanceStatus.COMPLETED else DeviceStatus.MAINTENANCE
        records.append((record, status, operator_index))
    db.flush()

    for record, final_status, operator_index in records:
        position = list(MaintenanceStatus).index(final_status)
        history = list(MaintenanceStatus)[: position + 1]
        for update_status in history:
            actor = school if update_status == MaintenanceStatus.REPORTED else operators[operator_index]
            note = {
                MaintenanceStatus.REPORTED: record.description,
                MaintenanceStatus.ACCEPTED: "Đã tiếp nhận yêu cầu bảo trì.",
                MaintenanceStatus.IN_PROGRESS: "Bắt đầu sửa chữa và kiểm tra thiết bị.",
                MaintenanceStatus.COMPLETED: "Sửa chữa hoàn tất, kiểm tra đạt.",
            }[update_status]
            update = db.scalar(
                select(MaintenanceUpdate).where(
                    MaintenanceUpdate.maintenance_id == record.id,
                    MaintenanceUpdate.status == update_status,
                )
            )
            if update is None:
                update = MaintenanceUpdate(
                    maintenance_id=record.id,
                    updated_by=actor.id,
                    status=update_status,
                )
                db.add(update)
            update.updated_by = actor.id
            update.status = update_status
            update.note = note
            update.inspection_passed = True if update_status == MaintenanceStatus.COMPLETED else None

        _upsert_audit(
            db,
            operators[operator_index].id if operator_index is not None else school.id,
            f"maintenance.{final_status.value.lower()}",
            "maintenance_record",
            record.id,
            {"sample": True, "status": final_status.value},
        )
        if final_status == MaintenanceStatus.COMPLETED:
            _upsert_notification(
                db, school.id, "maintenance_record", record.id,
                "Thiết bị đã sửa xong", "Camera ghi hình đã được kiểm tra và sẵn sàng sử dụng.", False,
            )
        else:
            for index, operator in enumerate(operators):
                _upsert_notification(
                    db,
                    operator.id,
                    "maintenance_record",
                    record.id,
                    "Có yêu cầu bảo trì thiết bị",
                    record.description,
                    is_read=index != operator_index,
                )


def seed_sample_data(db: Session) -> dict[str, int]:
    users = {account[0]: _upsert_user(db, account) for account in SAMPLE_ACCOUNTS}
    db.flush()
    borrowers = [users[email] for email, _, _ in BORROWER_ACCOUNTS]
    school = users[SCHOOL_ACCOUNT[0]]
    operators = [users[email] for email, _, _ in OPERATOR_ACCOUNTS]
    lecturers = [users[email] for email, _, staff_id in BORROWER_ACCOUNTS if staff_id.startswith("GV")]

    rooms = {}
    for code, name, location, capacity, active, aliases in ROOMS:
        room = _upsert_named(db, Room, Room.code, code, aliases)
        room.name = name
        room.location = location
        room.capacity = capacity
        room.is_active = active
        rooms[code] = room
    categories = {}
    for name, description, aliases in CATEGORIES:
        category = _upsert_named(db, Category, Category.name, name, aliases)
        category.description = description
        categories[name] = category
    db.flush()

    devices = {}
    for tag, name, description, category_name, room_code, total, available, status, aliases in DEVICES:
        device = _upsert_named(db, Device, Device.asset_tag, tag, aliases)
        device.name = name
        device.description = description
        device.category_id = categories[category_name].id
        device.room_id = rooms[room_code].id
        device.quantity_total = total
        device.quantity_available = available
        device.status = status
        devices[tag] = device
    db.flush()

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    schedules = {}
    for code, name, course_code, room_code, lecturer_index, day_offset, hour, active, aliases in SCHEDULES:
        schedule = _upsert_named(db, Schedule, Schedule.course_code, course_code, aliases)
        starts_at = (now + timedelta(days=day_offset)).replace(hour=hour, minute=0)
        schedule.course_name = name
        schedule.course_code = course_code
        schedule.room_id = rooms[room_code].id
        schedule.instructor_id = lecturers[lecturer_index].id
        schedule.starts_at = starts_at
        schedule.ends_at = starts_at + timedelta(hours=2)
        schedule.is_active = active
        schedules[code] = schedule
    db.flush()

    _seed_loans(
        db,
        borrowers,
        school,
        rooms,
        schedules,
        devices["MAU-LT-A101-001"],
        now,
    )
    _seed_maintenance(db, school, operators, devices)

    settings = (
        ("loan_limits", {"max_active_requests": 3, "max_loan_days": 14}, "Giới hạn mượn mẫu cho tài khoản người dùng."),
        ("maintenance_policy", {"inspection_required": True, "operator_count": 5}, "Quy trình bảo trì yêu cầu kiểm tra đạt."),
    )
    for key, value, description in settings:
        setting = db.scalar(select(Setting).where(Setting.key == key))
        if setting is None:
            setting = Setting(key=key, value=value, description=description)
            db.add(setting)
        setting.value = value
        setting.description = description

    return {
        "borrowers": len(borrowers),
        "operators": len(operators),
        "rooms": len(rooms),
        "devices": len(devices),
        "loan_statuses": len(LoanStatus),
        "maintenance_statuses": len(MaintenanceStatus),
    }
