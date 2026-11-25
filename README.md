# Lab Equipment Lending API

Backend REST API cho hệ thống mượn–trả thiết bị phòng thực hành. Stack: Python 3.12+, FastAPI, SQLAlchemy 2, MySQL 8, JWT/OAuth2 và Docker Compose.

## Chạy nhanh bằng Docker

Trong thư mục `nhom21-INT1427-api`:

```powershell
Copy-Item .env.example .env
# Sửa JWT_SECRET trong .env thành chuỗi ngẫu nhiên riêng (ít nhất 32 ký tự).
docker compose up --build
```

Mở Swagger UI tại `http://localhost:8000/docs`, OpenAPI JSON tại `/openapi.json`; kiểm tra tiến trình tại `/health`. Docker Compose tạo MySQL, chờ healthcheck rồi chạy API. Bảng được tạo khi ứng dụng khởi động. `.env.example` là cấu hình local; đổi toàn bộ mật khẩu mặc định trước khi dùng ngoài máy cá nhân.

### Chạy API trực tiếp trên Windows

Yêu cầu Python 3.12+ và MySQL 8 đang chạy. Tạo database `lab_equipment`, tạo file `.env` từ `.env.example` và cập nhật `DATABASE_URL`, `JWT_SECRET`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn api.main:app --reload
```

Tạo tài khoản quản trị đầu tiên bằng prompt mật khẩu (không truyền mật khẩu qua command line):

```powershell
python -m api.cli create-admin --email admin@university.edu --name "System Administrator"
```

Tạo dữ liệu mẫu cho phòng, danh mục, thiết bị, lịch học, phiếu mượn/bảo trì ở mọi trạng thái và tài khoản theo ba vai trò:

```powershell
python -m api.cli seed-demo
```

Seed tạo 30 tài khoản Người dùng (`BORROWER`), 1 tài khoản Nhà trường (`ADMIN`) và 5 tài khoản Người vận hành (`TECHNICIAN`). Hồ sơ có họ tên, chức danh và mã định danh mẫu. Ba tài khoản tiện dùng cho đăng nhập nhanh:

| Vai trò | Email | Mật khẩu |
|---|---|---|
| Người dùng (`BORROWER`) — Trần Văn Bình, Sinh viên | `tran.van.binh@university.edu` | `LabEquip123!` |
| Nhà trường (`ADMIN`) — Nguyễn Thị Lan, Cán bộ nhà trường | `nguyen.thi.lan@university.edu` | `LabEquip123!` |
| Người vận hành (`TECHNICIAN`) — Lê Quốc Huy, Kỹ thuật viên thiết bị | `le.quoc.huy@university.edu` | `LabEquip123!` |

Các tài khoản còn lại được định nghĩa tập trung trong `api/demo_data.py` và xuất hiện trong danh sách người dùng sau khi seed. Chạy lại seed sẽ đặt lại thông tin, mật khẩu và vai trò của tài khoản mẫu, đồng thời cập nhật dữ liệu minh họa theo các trạng thái chuẩn. Chỉ dùng dữ liệu/mật khẩu này trong môi trường phát triển local, không dùng trên môi trường thật.

## Cấu trúc

```text
api/
  config.py, database.py, main.py, security.py, dependencies.py, cli.py
  models/entities.py                 SQLAlchemy models, constraints, indexes, enums
  controllers/loans.py               Shared loan lookup and owner authorization
  middlewares/security_headers.py    API security response headers and request ID
  validators/schemas.py              Request/response validation
  routes/auth.py                     Register, OAuth2 token, refresh, profile
  routes/resources.py                Users, rooms, categories, devices, schedules, settings
  routes/operations.py               Loans, loan details, maintenance, notifications, audit
  services/loan_service.py           Inventory reservation, approve/return transactions
  services/maintenance_service.py    Repair lifecycle and append-only history
  jobs/overdue.py                    Overdue detection and borrower notification
  types/                              Typed page result and UTC datetime DB type
  utils/                              Audit and pagination
tests/test_api.py                    API integration tests with isolated SQLite
```

## ERD tóm tắt

```text
users 1---* loan_requests *---1 rooms
users 1---* schedules *---1 rooms
categories 1---* devices *---0..1 rooms
loan_requests 1---* loan_details *---1 devices
devices 1---* maintenance_records 1---* maintenance_updates
users 1---* notifications
users 1---* audit_logs
```

PK là UUID dạng chuỗi; FK dùng `ON DELETE` phù hợp để bảo vệ lịch sử. Email, mã phòng, tên danh mục, asset tag, mã định danh người dùng và key cấu hình có UNIQUE. Các FK/trường truy vấn trạng thái, người dùng, khoảng thời gian có INDEX; một số tổ hợp có composite index. Timestamps dùng UTC ở API. SQLAlchemy tự tạo các bảng khi khởi động; thay đổi schema production nên được quản lý bằng Alembic trước khi triển khai liên tục.

## RBAC và xác thực

| Vai trò | Quyền chính |
|---|---|
| `BORROWER` | Xem tài nguyên/lịch; tạo yêu cầu; xem/hủy yêu cầu của mình; xem thông báo của mình |
| `ADMIN` | Quản lý người dùng, phòng, danh mục, thiết bị, lịch, settings; quyết định mượn; bàn giao/nhận trả; báo hỏng; xem audit |
| `TECHNICIAN` | Xem hồ sơ bảo trì; tiếp nhận và cập nhật tiến độ/kiểm định |

Đăng ký luôn cấp `BORROWER`; không nhận role từ body. Tạo admin bằng CLI. `POST /api/v1/auth/token` dùng OAuth2 password form, chỉ chấp nhận email và mật khẩu hợp lệ, trả access JWT (mặc định 30 phút) và refresh JWT. Bảo vệ API bằng `Authorization: Bearer <access_token>`. Refresh gửi form `refresh_token`.

## Quy tắc mượn/trả và bảo trì

* Yêu cầu phải có phòng đang hoạt động, khoảng thời gian hợp lệ, thiết bị AVAILABLE và đủ tồn kho.
* Yêu cầu nằm trọn trong lịch học active cùng phòng được tự động `APPROVED`. Ngoài lịch yêu cầu lý do và ở `PENDING`.
* `APPROVED` giữ tồn kho; cập nhật tồn kho dùng điều kiện atomic `UPDATE ... quantity_available >= requested` trong transaction để không âm khi nhiều yêu cầu cùng lúc. Admin chỉ duyệt `PENDING`; không đủ hàng thì trả 409 và rollback toàn bộ.
* Admin xác nhận `CHECKED_OUT`, sau đó `RETURNED`; trả hàng cộng lại đúng số lượng chưa trả và không vượt tồn kho tổng. Job nền chuyển `CHECKED_OUT` quá hạn sang `OVERDUE`, tạo thông báo và audit event.
* Chỉ Admin báo hỏng. Technician nhận, chuyển tiến độ, rồi chỉ được hoàn tất nếu xác nhận inspection đạt; thiết bị chỉ chuyển lại AVAILABLE khi hoàn tất. Mỗi lần cập nhật bảo trì được lưu vào `maintenance_updates`.
* Trạng thái chỉ được sửa qua thao tác nghiệp vụ có role phù hợp; endpoint update thiết bị không cho sửa trực tiếp trạng thái.

## API chính (`/api/v1`)

Tất cả collection hỗ trợ `page` (1-based), `page_size` (tối đa 100; audit tối đa 200). Tìm kiếm/lọc có `q`, `status`, `room_id`, `category_id`, khoảng thời gian tùy endpoint. Tất cả tài nguyên có Swagger schema.

| Nhóm | Endpoint | Quyền |
|---|---|---|
| Auth | `POST /auth/register`, `POST /auth/token`, `POST /auth/refresh`, `GET /auth/me` | Public / account |
| Users | `GET /users`, `GET /users/{id}`, `PATCH /users/{id}` | Admin |
| Rooms | `GET/POST /rooms`, `GET/PATCH/DELETE /rooms/{id}` | đọc có token / Admin ghi |
| Categories | `GET/POST /categories`, `GET/PATCH/DELETE /categories/{id}` | đọc có token / Admin ghi |
| Devices | `GET/POST /devices`, `GET/PATCH/DELETE /devices/{id}` | đọc có token / Admin ghi; delete retire |
| Schedules | `GET/POST /schedules`, `GET/PATCH/DELETE /schedules/{id}` | đọc có token / Admin ghi |
| Loans | `POST/GET /loan-requests`, `GET /loan-requests/{id}`, `GET /loan-requests/{id}/details`, `POST /loan-requests/{id}/approve|reject|checkout|return|cancel` | owner / Admin thao tác quản trị |
| Maintenance | `POST/GET /maintenance`, `GET/PATCH /maintenance/{id}`, `GET /maintenance/{id}/history` | Admin báo hỏng; Technician cập nhật/sửa |
| Notifications | `GET /notifications`, `POST /notifications/{id}/read` | chính chủ |
| Audit | `GET /audit-logs` | Admin |
| Settings | `GET /settings`, `PUT/PATCH/DELETE /settings/{key}` | Admin |

API lỗi dùng HTTP status và `{"detail": ...}`; ràng buộc UNIQUE/FK trả 409. Không xóa cứng phòng/lịch sử mượn; phòng/lịch được vô hiệu hóa, thiết bị được retire.

## Postman/cURL kiểm thử thủ công

1. Tạo Admin bằng CLI và khởi động API. Tạo tài khoản BORROWER:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/auth/register -H "Content-Type: application/json" -d "{\"email\":\"student@university.edu\",\"full_name\":\"Test Student\",\"password\":\"ChangeThisPassword123\"}"
```

2. Lấy token (form-urlencoded) và dùng Bearer token:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/auth/token -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin@university.edu&password=YOUR_ADMIN_PASSWORD"
```

3. Với token Admin, tạo phòng, category, device và schedule qua `POST /api/v1/rooms`, `/categories`, `/devices`, `/schedules`. Dùng ID trả về. Ngày giờ phải ISO-8601 có timezone, ví dụ `2027-01-15T09:00:00+07:00`.
4. Với token borrower, gọi `POST /api/v1/loan-requests` với `room_id`, `starts_at`, `due_at`, `details: [{"device_id":"...","quantity":1}]`. Khớp lịch trả APPROVED; ngoài lịch thêm `reason` và nhận PENDING.
5. Admin gọi `POST /loan-requests/{id}/checkout`, rồi `/return`. Kiểm tra tồn kho qua `GET /devices/{id}`; ngoài lịch admin duyệt trước bằng `/approve`, hoặc từ chối bằng `/reject` với `{"reason":"..."}`.
6. Admin báo hỏng bằng `POST /maintenance`; Technician cập nhật `PATCH /maintenance/{id}` lần lượt `ACCEPTED`, `IN_PROGRESS`, `COMPLETED` cùng `inspection_passed: true`. Xem lịch sử ở `/history`.

## Kiểm thử tự động

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Integration test chạy trên SQLite tạm riêng, không dùng dữ liệu MySQL thực. Dùng MySQL cho môi trường triển khai:

```powershell
docker compose up --build
```

## Vận hành/bảo mật

Đặt `JWT_SECRET` ngẫu nhiên, dài, riêng biệt; nếu không khai báo, API tạo secret ngẫu nhiên mới mỗi lần khởi động (token cũ sẽ hết hiệu lực). Không dùng mật khẩu mặc định của Compose trên môi trường chia sẻ. Đặt HTTPS sau reverse proxy, giới hạn `CORS_ORIGINS`, bảo vệ backup DB và giám sát logs. MySQL root/password trong Compose chỉ là cấu hình local có thể override bằng biến môi trường.
