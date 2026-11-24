import argparse
from datetime import datetime, timedelta, timezone
from getpass import getpass

from sqlalchemy import select

from api.database import Base, SessionLocal, engine
from api.models import Category, Device, DeviceStatus, Role, Room, Schedule, User
from api.security import hash_password


def create_admin(email: str, full_name: str) -> None:
    Base.metadata.create_all(bind=engine)
    password = getpass("Admin password (10+ characters): ")
    if not 10 <= len(password.encode("utf-8")) <= 72:
        raise SystemExit("Password must contain between 10 and 72 UTF-8 bytes")
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == email.lower())):
            raise SystemExit("An account with this email already exists")
        db.add(User(
            email=email.lower(),
            full_name=full_name,
            password_hash=hash_password(password),
            role=Role.ADMIN,
            is_active=True,
        ))
        db.commit()
        print(f"Administrator created: {email.lower()}")
    finally:
        db.close()


def seed_demo() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        room = db.scalar(select(Room).where(Room.code == "LAB-DEMO"))
        if not room:
            room = Room(code="LAB-DEMO", name="Demonstration Lab", location="Building A", capacity=30)
            db.add(room)
            db.flush()
        category = db.scalar(select(Category).where(Category.name == "Demo peripherals"))
        if not category:
            category = Category(name="Demo peripherals", description="Optional sample inventory category")
            db.add(category)
            db.flush()
        device = db.scalar(select(Device).where(Device.asset_tag == "DEMO-DEVICE-001"))
        if not device:
            db.add(Device(
                asset_tag="DEMO-DEVICE-001",
                name="Demo presentation remote",
                category_id=category.id,
                room_id=room.id,
                quantity_total=5,
                quantity_available=5,
                status=DeviceStatus.AVAILABLE,
            ))
        schedule = db.scalar(select(Schedule).where(Schedule.course_code == "DEMO101"))
        if not schedule:
            start = (datetime.now(timezone.utc) + timedelta(days=7)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            db.add(Schedule(
                course_name="Demonstration laboratory class",
                course_code="DEMO101",
                room_id=room.id,
                starts_at=start,
                ends_at=start + timedelta(hours=2),
            ))
        db.commit()
        print("Demo room, category, device, and future schedule are ready.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="API administration utilities")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="Create an administrator account")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    commands.add_parser("seed-demo", help="Insert optional demonstration room/category/device")
    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args.email, args.name)
    elif args.command == "seed-demo":
        seed_demo()


if __name__ == "__main__":
    main()
