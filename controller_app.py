"""
controller_app.py - Làm việc với Network Controller (APIC-EM / Packet Tracer) qua REST API.

Họ tên : Nguyễn Gia Huy
MSSV   : 1822040092  ->  N = 92

Luồng chạy:
  1. Đọc địa chỉ controller và tài khoản từ tệp .env (không ghi cứng trong mã).
  2. POST /api/v1/ticket  -> lấy service ticket.
  3. GET /api/v1/network-device và /api/v1/host (header X-Auth-Token: <ticket>).
  4. In bảng (hostname, loại, IP, trạng thái) và lưu ra inventory.csv.

Chạy:  python controller_app.py
"""
import csv
import os
import sys

import requests

API_PREFIX = "/api/v1"
TICKET_PATH = f"{API_PREFIX}/ticket"
DEVICE_PATH = f"{API_PREFIX}/network-device"
HOST_PATH = f"{API_PREFIX}/host"
TIMEOUT = 5                     # giây
OUTPUT_CSV = "inventory.csv"
CSV_FIELDS = ["source", "hostname", "type", "ip", "status"]


# ---------------------------------------------------------------- ngoại lệ
class ControllerError(Exception):
    """Lỗi chung khi làm việc với controller (kết nối, phản hồi sai...)."""


class TicketInvalid(ControllerError):
    """Ticket hết hạn hoặc không hợp lệ (HTTP 401/403)."""


class ConfigError(Exception):
    """Thiếu cấu hình trong .env."""


# ---------------------------------------------------------------- cấu hình
def load_env(path=".env"):
    """Đọc tệp .env (dạng KEY=VALUE) vào os.environ. Không ghi đè biến đã có."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_config():
    """Trả về (base_url, username, password) từ biến môi trường."""
    base_url = os.environ.get("CONTROLLER_URL", "").rstrip("/")
    username = os.environ.get("CONTROLLER_USER", "")
    password = os.environ.get("CONTROLLER_PASSWORD", "")
    missing = [k for k, v in (("CONTROLLER_URL", base_url), ("CONTROLLER_USER", username),
                              ("CONTROLLER_PASSWORD", password)) if not v]
    if missing:
        raise ConfigError("Thiếu cấu hình trong .env: " + ", ".join(missing)
                          + " (xem tệp .env.example)")
    return base_url, username, password


# ---------------------------------------------------------------- gọi API
def get_ticket(base_url, username, password):
    """POST /api/v1/ticket, trả về chuỗi serviceTicket."""
    url = base_url + TICKET_PATH
    try:
        resp = requests.post(url, json={"username": username, "password": password},
                             headers={"Content-Type": "application/json"}, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        raise ControllerError(f"Hết thời gian chờ ({TIMEOUT}s) khi kết nối {url}")
    except requests.exceptions.RequestException as e:
        raise ControllerError(f"Không kết nối được tới controller: {e}")

    if resp.status_code in (401, 403):
        raise ControllerError("Sai tài khoản hoặc mật khẩu (controller từ chối đăng nhập)")
    if resp.status_code not in (200, 201):
        raise ControllerError(f"Lấy ticket thất bại, mã trạng thái {resp.status_code}")
    try:
        ticket = resp.json()["response"]["serviceTicket"]
    except (ValueError, KeyError, TypeError):
        raise ControllerError("Phản hồi lấy ticket không đúng định dạng")
    if not ticket:
        raise ControllerError("Controller trả về ticket rỗng")
    return ticket


def _api_get(base_url, path, ticket):
    """GET một endpoint với header X-Auth-Token; trả về danh sách trong khóa 'response'."""
    url = base_url + path
    try:
        resp = requests.get(url, headers={"X-Auth-Token": ticket}, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        raise ControllerError(f"Hết thời gian chờ ({TIMEOUT}s) khi gọi {path}")
    except requests.exceptions.RequestException as e:
        raise ControllerError(f"Lỗi kết nối khi gọi {path}: {e}")

    if resp.status_code in (401, 403):
        raise TicketInvalid("Ticket hết hạn hoặc không hợp lệ")
    if resp.status_code != 200:
        raise ControllerError(f"{path} trả về mã trạng thái {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        raise ControllerError(f"{path} trả về dữ liệu không phải JSON")
    return data


def get_devices(base_url, ticket):
    """Lấy danh sách thiết bị mạng đã chuẩn hóa."""
    return parse_devices(_api_get(base_url, DEVICE_PATH, ticket))


def get_hosts(base_url, ticket):
    """Lấy danh sách host đã chuẩn hóa."""
    return parse_hosts(_api_get(base_url, HOST_PATH, ticket))


# ---------------------------------------------------------------- xử lý dữ liệu
def _items(data):
    """Lấy danh sách phần tử từ phản hồi {"response": [...]}; ném lỗi nếu sai dạng."""
    if not isinstance(data, dict):
        raise ControllerError("Phản hồi không phải đối tượng JSON")
    if "response" not in data:
        if "version" in data:       # Controller chưa có dữ liệu (chưa discovery): coi như rỗng
            return []
        raise ControllerError("Phản hồi thiếu khóa 'response'")
    items = data["response"]
    if not isinstance(items, list):
        raise ControllerError("Khóa 'response' không phải danh sách")
    return items


def _as_list(value):
    """Đưa giá trị (chuỗi, danh sách hoặc None) về danh sách."""
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _build_name_map(devices):
    """Tạo bảng IP -> tên thiết bị từ các trường connectedNetworkDevice* của mọi thiết bị.

    Controller (Packet Tracer) không trả hostname cho router (collectionStatus "Unsupported"),
    nhưng tên router xuất hiện trong danh sách thiết bị láng giềng của switch."""
    names = {}
    for d in devices:
        ips = _as_list(d.get("connectedNetworkDeviceIpAddress"))
        for ip, name in zip(ips, _as_list(d.get("connectedNetworkDeviceName"))):
            if ip and name:
                names.setdefault(ip, name)
    return names


def parse_devices(data):
    """Chuyển JSON thiết bị mạng thành list dict (source, hostname, type, ip, status).

    - hostname: lấy từ trường hostname; nếu thiếu thì tra theo IP trong tên các thiết bị láng giềng.
    - type: lấy từ type/family; nếu rỗng và thiết bị có từ 2 địa chỉ IP trở lên thì suy ra là Router.
    """
    devices = _items(data)
    names = _build_name_map(devices)
    rows = []
    for d in devices:
        ips = _as_list(d.get("ipAddresses"))
        mgmt = d.get("managementIpAddress") or ""
        hostname = d.get("hostname")
        if not hostname:
            hostname = next((names[ip] for ip in [mgmt] + ips if ip in names), "N/A")
        dev_type = d.get("type") or d.get("family")
        if not dev_type:
            dev_type = "Router" if len(ips) >= 2 else "N/A"
        rows.append({
            "source": "device",
            "hostname": hostname,
            "type": dev_type,
            "ip": mgmt or "N/A",
            "status": d.get("reachabilityStatus") or d.get("status") or "N/A",
        })
    return rows


def parse_hosts(data):
    """Chuyển JSON host thành list dict cùng cấu trúc với thiết bị."""
    rows = []
    for h in _items(data):
        rows.append({
            "source": "host",
            "hostname": h.get("hostName") or h.get("hostname") or "N/A",
            "type": h.get("hostType") or "host",
            "ip": h.get("hostIp") or "N/A",
            "status": h.get("status") or "connected",
        })
    return rows


def print_table(rows, title=""):
    """In bảng hostname - loại - IP - trạng thái."""
    if title:
        print(f"\n== {title} ==")
    if not rows:
        print("(không có dữ liệu)")
        return
    header = f"{'Hostname':<28}{'Loại':<18}{'IP':<18}{'Trạng thái'}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['hostname']:<28}{r['type']:<18}{r['ip']:<18}{r['status']}")


def save_csv(rows, path=OUTPUT_CSV):
    """Lưu danh sách ra CSV (UTF-8 có BOM để Excel đọc đúng)."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------- chương trình chính
def fetch_with_retry(fetch_func, base_url, ticket, username, password):
    """Gọi fetch_func(base_url, ticket); nếu ticket hết hạn thì lấy ticket mới và thử lại 1 lần.
    Trả về (kết quả, ticket đang dùng)."""
    try:
        return fetch_func(base_url, ticket), ticket
    except TicketInvalid:
        print("  Ticket hết hạn, đang lấy ticket mới...")
        ticket = get_ticket(base_url, username, password)
        return fetch_func(base_url, ticket), ticket


def main():
    load_env()
    try:
        base_url, username, password = get_config()
        ticket = get_ticket(base_url, username, password)
        print(f"Đã lấy service ticket: {ticket[:12]}...")

        devices, ticket = fetch_with_retry(get_devices, base_url, ticket, username, password)
        hosts, ticket = fetch_with_retry(get_hosts, base_url, ticket, username, password)
    except ConfigError as e:
        print(f"[LỖI CẤU HÌNH] {e}")
        sys.exit(1)
    except ControllerError as e:
        print(f"[LỖI] {e}")
        sys.exit(1)

    if not devices and not hosts:
        print("[CẢNH BÁO] Controller trả về danh sách rỗng, không có gì để lưu.")
        sys.exit(1)

    print_table(devices, "Thiết bị mạng (network-device)")
    print_table(hosts, "Host (host)")
    save_csv(devices + hosts)
    print(f"\nĐã lưu {len(devices) + len(hosts)} dòng vào {OUTPUT_CSV}")


if __name__ == "__main__":
    main()