import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

_db_fd, _db_path = tempfile.mkstemp(suffix=".sqlite3")
os.close(_db_fd)
os.environ["DATABASE_URL"] = "sqlite:///" + _db_path.replace("\\", "/")
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-tests-123456"

from fastapi.testclient import TestClient

from api.database import SessionLocal, engine
from api.main import app
from api.models import (
    Category, Device, DeviceStatus, LoanRequest, LoanStatus, Notification, Role, Room,
    MaintenanceRecord, MaintenanceStatus, MaintenanceUpdate, Schedule, User,
)
from api.security import hash_password


class EquipmentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()
        db = SessionLocal()
        try:
            cls.admin = User(
                email="admin@example.test",
                full_name="Test Admin",
                password_hash=hash_password("admin-test-pass"),
                role=Role.ADMIN,
                is_active=True,
            )
            cls.technician = User(
                email="technician@example.test",
                full_name="Test Technician",
                password_hash=hash_password("technician-test-pass"),
                role=Role.TECHNICIAN,
                is_active=True,
            )
            db.add_all([cls.admin, cls.technician])
            room = Room(code="T-LAB", name="Test Lab", capacity=20, is_active=True)
            category = Category(name="Test category")
            db.add_all([room, category])
            db.flush()
            device = Device(
                asset_tag="T-DEVICE",
                name="Test device",
                category_id=category.id,
                room_id=room.id,
                quantity_total=5,
                quantity_available=5,
                status=DeviceStatus.AVAILABLE,
            )
            db.add(device)
            db.flush()
            start = datetime.now(timezone.utc) + timedelta(days=2)
            db.add(Schedule(
                course_name="Test class",
                course_code="TEST101",
                room_id=room.id,
                starts_at=start - timedelta(minutes=10),
                ends_at=start + timedelta(hours=2),
            ))
            db.commit()
            cls.room_id, cls.device_id = room.id, device.id
            cls.schedule_start = start
        finally:
            db.close()
        cls.admin_token = cls._login("admin@example.test", "admin-test-pass")
        cls.technician_token = cls._login("technician@example.test", "technician-test-pass")

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        engine.dispose()
        try:
            os.remove(_db_path)
        except FileNotFoundError:
            pass

    @classmethod
    def _login(cls, email, password):
        response = cls.client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": password},
        )
        if response.status_code != 200:
            raise AssertionError(response.text)
        return response.json()["access_token"]

    def setUp(self):
        response = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": "borrower@example.com",
                "full_name": "Test Borrower",
                "password": "borrower-test-pass",
            },
        )
        if response.status_code == 201:
            self.borrower_id = response.json()["id"]
        else:
            with SessionLocal() as db:
                self.borrower_id = db.query(User).filter_by(email="borrower@example.com").one().id
        self.borrower_token = self._login("borrower@example.com", "borrower-test-pass")

    def test_schedule_auto_approval_return_and_stock(self):
        response = self.client.post(
            "/api/v1/loan-requests",
            headers={"Authorization": f"Bearer {self.borrower_token}"},
            json={
                "room_id": self.room_id,
                "starts_at": self.schedule_start.isoformat(),
                "due_at": (self.schedule_start + timedelta(hours=1)).isoformat(),
                "details": [{"device_id": self.device_id, "quantity": 2}],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        loan = response.json()
        self.assertEqual(loan["status"], LoanStatus.APPROVED.value)
        self.assertEqual(len(loan["details"]), 1)
        self.assertEqual(datetime.fromisoformat(loan["starts_at"]).utcoffset(), timedelta(0))
        duplicate_approval = self.client.post(
            f"/api/v1/loan-requests/{loan['id']}/approve",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(duplicate_approval.status_code, 409)

        headers = {"Authorization": f"Bearer {self.admin_token}"}
        checkout = self.client.post(f"/api/v1/loan-requests/{loan['id']}/checkout", headers=headers)
        self.assertEqual(checkout.status_code, 200, checkout.text)
        returned = self.client.post(f"/api/v1/loan-requests/{loan['id']}/return", headers=headers)
        self.assertEqual(returned.status_code, 200, returned.text)
        self.assertEqual(returned.json()["status"], LoanStatus.RETURNED.value)
        device = self.client.get(
            f"/api/v1/devices/{self.device_id}",
            headers={"Authorization": f"Bearer {self.borrower_token}"},
        )
        self.assertEqual(device.json()["quantity_available"], 5)

    def test_out_of_schedule_requires_reason_and_admin_approval(self):
        start = self.schedule_start + timedelta(days=3)
        body = {
            "room_id": self.room_id,
            "starts_at": start.isoformat(),
            "due_at": (start + timedelta(minutes=30)).isoformat(),
            "details": [{"device_id": self.device_id, "quantity": 4}],
        }
        headers = {"Authorization": f"Bearer {self.borrower_token}"}
        self.assertEqual(self.client.post("/api/v1/loan-requests", json=body, headers=headers).status_code, 422)
        body["reason"] = "Independent research"
        response = self.client.post("/api/v1/loan-requests", json=body, headers=headers)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["status"], LoanStatus.PENDING.value)
        scheduled = self.client.post(
            "/api/v1/loan-requests",
            headers=headers,
            json={
                "room_id": self.room_id,
                "starts_at": self.schedule_start.isoformat(),
                "due_at": (self.schedule_start + timedelta(hours=1)).isoformat(),
                "details": [{"device_id": self.device_id, "quantity": 2}],
            },
        )
        self.assertEqual(scheduled.status_code, 201, scheduled.text)
        self.assertEqual(scheduled.json()["status"], LoanStatus.APPROVED.value)
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        denied = self.client.post(
            f"/api/v1/loan-requests/{response.json()['id']}/approve",
            headers=admin_headers,
        )
        self.assertEqual(denied.status_code, 409)
        self.assertEqual(
            self.client.get(
                f"/api/v1/devices/{self.device_id}",
                headers={"Authorization": f"Bearer {self.borrower_token}"},
            ).json()["quantity_available"],
            3,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/loan-requests/{scheduled.json()['id']}/checkout",
                headers=admin_headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/loan-requests/{scheduled.json()['id']}/return",
                headers=admin_headers,
            ).status_code,
            200,
        )

    def test_maintenance_requires_successful_inspection(self):
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        report = self.client.post(
            "/api/v1/maintenance",
            headers=admin_headers,
            json={"device_id": self.device_id, "description": "Intermittent connection"},
        )
        self.assertEqual(report.status_code, 201, report.text)
        record_id = report.json()["id"]
        unavailable_loan = self.client.post(
            "/api/v1/loan-requests",
            headers={"Authorization": f"Bearer {self.borrower_token}"},
            json={
                "room_id": self.room_id,
                "starts_at": self.schedule_start.isoformat(),
                "due_at": (self.schedule_start + timedelta(hours=1)).isoformat(),
                "details": [{"device_id": self.device_id, "quantity": 1}],
            },
        )
        self.assertEqual(unavailable_loan.status_code, 409)
        tech_headers = {"Authorization": f"Bearer {self.technician_token}"}
        for state in ("ACCEPTED", "IN_PROGRESS"):
            result = self.client.patch(
                f"/api/v1/maintenance/{record_id}",
                headers=tech_headers,
                json={"status": state, "progress_note": f"State {state}"},
            )
            self.assertEqual(result.status_code, 200, result.text)
        blocked = self.client.patch(
            f"/api/v1/maintenance/{record_id}",
            headers=tech_headers,
            json={"status": "COMPLETED", "inspection_passed": False},
        )
        self.assertEqual(blocked.status_code, 422)
        completed = self.client.patch(
            f"/api/v1/maintenance/{record_id}",
            headers=tech_headers,
            json={"status": "COMPLETED", "inspection_passed": True, "progress_note": "Test passed"},
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["status"], "COMPLETED")

    def test_overdue_job_notifies_borrower_once(self):
        db = SessionLocal()
        try:
            loan = LoanRequest(
                requester_id=self.borrower_id,
                room_id=self.room_id,
                starts_at=datetime.now(timezone.utc) - timedelta(days=3),
                due_at=datetime.now(timezone.utc) - timedelta(days=1),
                status=LoanStatus.CHECKED_OUT,
            )
            db.add(loan)
            db.commit()
            loan_id = loan.id
        finally:
            db.close()
        from api.jobs.overdue import mark_overdue

        self.assertEqual(mark_overdue(), 1)
        self.assertEqual(mark_overdue(), 0)
        with SessionLocal() as db:
            loan = db.get(LoanRequest, loan_id)
            notifications = db.query(Notification).filter_by(related_id=loan_id).all()
            self.assertEqual(loan.status, LoanStatus.OVERDUE)
            self.assertEqual(len(notifications), 1)

    def test_borrower_cannot_approve_requests(self):
        response = self.client.post(
            "/api/v1/loan-requests/00000000-0000-0000-0000-000000000001/approve",
            headers={"Authorization": f"Bearer {self.borrower_token}"},
        )
        self.assertEqual(response.status_code, 403)

    def test_registered_account_logs_in_with_borrower_permissions(self):
        self.assertEqual(self.client.post("/api/v1/auth/oidc", json={}).status_code, 404)
        account = {
            "email": "new.user@example.com",
            "full_name": "New User",
            "password": "new-user-test-pass",
            "role": "ADMIN",
        }
        created = self.client.post("/api/v1/auth/register", json=account)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["role"], Role.BORROWER.value)
        duplicate = self.client.post(
            "/api/v1/auth/register",
            json={**account, "email": account["email"].upper()},
        )
        self.assertEqual(duplicate.status_code, 409)

        invalid_login = self.client.post(
            "/api/v1/auth/token",
            data={"username": account["email"], "password": "incorrect-password"},
        )
        self.assertEqual(invalid_login.status_code, 401)
        token = self._login(account["email"], account["password"])
        headers = {"Authorization": f"Bearer {token}"}
        profile = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(profile.json()["role"], Role.BORROWER.value)
        self.assertEqual(self.client.get("/api/v1/users", headers=headers).status_code, 403)

    def test_demo_seed_creates_full_role_data_and_is_idempotent(self):
        from api.cli import seed_demo
        from api.demo_data import (
            BORROWER_ACCOUNTS,
            OPERATOR_ACCOUNTS,
            LOAN_SAMPLE_COUNTS,
            QUICK_LOGIN_ACCOUNTS,
            SAMPLE_ACCOUNTS,
            SCHOOL_ACCOUNT,
            SAMPLE_PASSWORD,
        )

        seed_demo()
        with SessionLocal() as db:
            sample_role_counts = {role: 0 for role in Role}
            for email, full_name, _, role, staff_id in SAMPLE_ACCOUNTS:
                account = db.query(User).filter_by(email=email).one()
                self.assertEqual(account.full_name, full_name)
                self.assertEqual(account.role, role)
                self.assertEqual(account.student_or_staff_id, staff_id)
                sample_role_counts[account.role] += 1
            self.assertEqual(len(BORROWER_ACCOUNTS), 30)
            self.assertEqual(len(OPERATOR_ACCOUNTS), 5)
            self.assertEqual(sample_role_counts[Role.BORROWER], 30)
            self.assertEqual(sample_role_counts[Role.ADMIN], 1)
            self.assertEqual(sample_role_counts[Role.TECHNICIAN], 5)

            demo_user = db.query(User).filter_by(email=QUICK_LOGIN_ACCOUNTS[0][0]).one()
            demo_user.password_hash = hash_password("ChangedDemoPass123!")
            demo_user.role = Role.ADMIN
            demo_user.is_active = False
            db.commit()
        seed_demo()

        tokens = {}
        for email, _, password, role, _ in QUICK_LOGIN_ACCOUNTS:
            token = self._login(email, password)
            tokens[role.value] = {"Authorization": f"Bearer {token}"}
            profile = self.client.get("/api/v1/auth/me", headers=tokens[role.value])
            self.assertEqual(profile.status_code, 200, profile.text)
            self.assertEqual(profile.json()["role"], role.value)

        settings = self.client.get("/api/v1/settings", headers=tokens["ADMIN"])
        self.assertEqual(settings.status_code, 200, settings.text)
        self.assertEqual(len(settings.json()["items"]), 2)
        self.assertEqual(self.client.get("/api/v1/settings", headers=tokens["BORROWER"]).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/maintenance", headers=tokens["TECHNICIAN"]).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/loan-requests", headers=tokens["TECHNICIAN"]).status_code, 403)
        self.assertEqual(QUICK_LOGIN_ACCOUNTS[1], SCHOOL_ACCOUNT)
        self.assertEqual(SAMPLE_PASSWORD, QUICK_LOGIN_ACCOUNTS[0][2])

        with SessionLocal() as db:
            sample_loans = [
                loan for loan in db.query(LoanRequest).all()
                if loan.reason and loan.reason.startswith("Mẫu:")
            ]
            self.assertEqual(len(sample_loans), sum(LOAN_SAMPLE_COUNTS.values()))
            sample_status_counts = {
                status: sum(loan.status == status for loan in sample_loans)
                for status in LoanStatus
            }
            self.assertEqual(sample_status_counts, LOAN_SAMPLE_COUNTS)
            sample_statuses = {loan.status for loan in sample_loans}
            self.assertEqual(sample_statuses, set(LoanStatus))
            sample_device = db.query(Device).filter_by(asset_tag="MAU-LT-A101-001").one()
            self.assertEqual(sample_device.quantity_total, 20)
            self.assertEqual(sample_device.quantity_available, 2)

            sample_maintenance = [
                record for record in db.query(MaintenanceRecord).all()
                if record.description.startswith("Mẫu bảo trì:")
            ]
            self.assertEqual(len(sample_maintenance), len(MaintenanceStatus))
            self.assertEqual(
                db.query(MaintenanceUpdate)
                .filter(MaintenanceUpdate.maintenance_id.in_([record.id for record in sample_maintenance]))
                .count(),
                sum(range(1, len(MaintenanceStatus) + 1)),
            )


if __name__ == "__main__":
    unittest.main()
