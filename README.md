# ltm-1822040092 – Ứng dụng làm việc với Network Controller

Bài kiểm tra thường xuyên số 3 – Lập trình mạng (0370090)

- **Họ tên:** Nguyễn Gia Huy
- **MSSV:** 1822040092 → **N = 92**
- **Repository:** https://github.com/<TEN-GITHUB>/ltm-1822040092  <!-- thay <TEN-GITHUB> bằng tên tài khoản GitHub của bạn -->
- **Môi trường:** Python 3.10+

## Nội dung

| Tệp | Mô tả |
|---|---|
| `controller_app.py` | Ứng dụng chính: lấy service ticket, lấy thiết bị và host, in bảng, lưu `inventory.csv` |
| `test_controller_app.py` | 13 ca kiểm thử pytest, dùng mock thay cho lời gọi API thật |
| `mock_controller.py` | Controller giả (mô phỏng APIC-EM) để thử khi không mở Packet Tracer |
| `.env.example` | Mẫu cấu hình; sao chép thành `.env` (tệp `.env` bị `.gitignore` loại trừ) |
| `requirements.txt` | `requests`, `pytest` |

## Cài đặt

```bash
python -m venv venv
venv\Scripts\activate          # Windows (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env         # rồi sửa CONTROLLER_URL, CONTROLLER_USER, CONTROLLER_PASSWORD
```

## Chạy ứng dụng

```bash
python controller_app.py
```

Các bước ứng dụng thực hiện:

1. Đọc `CONTROLLER_URL`, `CONTROLLER_USER`, `CONTROLLER_PASSWORD` từ `.env` (không ghi cứng trong mã).
2. `POST /api/v1/ticket` → lấy `serviceTicket`.
3. `GET /api/v1/network-device` và `GET /api/v1/host` với header `X-Auth-Token: <ticket>`.
4. In bảng (hostname, loại, IP, trạng thái) và lưu `inventory.csv`.

Các hàm chính: `get_ticket`, `get_devices`, `get_hosts`, `print_table`.

Xử lý lỗi: lỗi kết nối, timeout 5 giây, sai tài khoản, ticket hết hạn (tự lấy ticket mới và thử lại một lần), phản hồi rỗng hoặc sai định dạng, thiếu cấu hình `.env`.

### Thử không cần Packet Tracer

```bash
python mock_controller.py          # cửa sổ 1 (tài khoản cisco / cisco, cổng 8080)
python controller_app.py           # cửa sổ 2, với CONTROLLER_URL=http://127.0.0.1:8080
```

## Kiểm thử

```bash
pytest -v
```

Kết quả:

```
test_controller_app.py::test_parse_devices_extracts_fields PASSED
test_controller_app.py::test_parse_devices_missing_fields_use_default PASSED
test_controller_app.py::test_parse_devices_empty_response_returns_empty_list PASSED
test_controller_app.py::test_parse_devices_bad_format_raises PASSED
test_controller_app.py::test_get_ticket_success PASSED
test_controller_app.py::test_get_ticket_wrong_password PASSED
test_controller_app.py::test_get_ticket_connection_error PASSED
test_controller_app.py::test_get_devices_sends_token_header PASSED
test_controller_app.py::test_get_devices_expired_ticket_raises_ticket_invalid PASSED
test_controller_app.py::test_fetch_with_retry_renews_ticket PASSED
test_controller_app.py::test_save_csv_writes_header_and_rows PASSED
test_controller_app.py::test_load_env_reads_values_without_overriding PASSED
test_controller_app.py::test_get_config_missing_raises PASSED
============================== 13 passed ==============================
```

## Minh chứng

> Thêm ảnh vào thư mục `screenshots/` rồi chèn bằng cú pháp `![mô tả](screenshots/ten_anh.png)`:
> 1. Sơ đồ mạng Packet Tracer (2 router, 2 switch, 4 PC, Network Controller; hostname chứa MSSV).
> 2. Kết quả chạy `python controller_app.py` trên Packet Tracer.
> 3. Kết quả `pytest -v`.
> 4. Trang pull request đã merge trên GitHub.
