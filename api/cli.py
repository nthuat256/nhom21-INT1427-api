import argparse
from getpass import getpass

from sqlalchemy import select

from api.database import Base, SessionLocal, engine
from api.demo_data import QUICK_LOGIN_ACCOUNTS, SAMPLE_ACCOUNTS, seed_sample_data
from api.models import Role, User
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
        counts = seed_sample_data(db)
        db.commit()
        print(
            "Sample data ready: "
            f"{counts['borrowers']} users, {counts['operators']} operators, "
            f"{counts['rooms']} rooms, {counts['devices']} devices, "
            f"{counts['loan_statuses']} loan statuses, "
            f"{counts['maintenance_statuses']} maintenance statuses."
        )
        print(f"All sample accounts use password: {SAMPLE_ACCOUNTS[0][2]}")
        print("Quick-login accounts:")
        for email, _, _, role, _ in QUICK_LOGIN_ACCOUNTS:
            print(f"  {role.value}: {email}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="API administration utilities")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="Create an administrator account")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    commands.add_parser("seed-demo", help="Seed local sample accounts and lending/maintenance scenarios")
    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args.email, args.name)
    elif args.command == "seed-demo":
        seed_demo()


if __name__ == "__main__":
    main()
