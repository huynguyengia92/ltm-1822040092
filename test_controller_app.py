"""
Kiểm thử pytest cho controller_app.py - dùng mock thay cho lời gọi API thật.
Chạy:  pytest -v
"""
import csv
from unittest.mock import MagicMock, patch

import pytest
import requests

import controller_app as app

BASE = "http://controller.local"


def make_response(status=200, json_data=None, json_error=False):
    """Tạo Response giả."""
    resp = MagicMock()
    resp.status_code = status
    if json_error:
        resp.json.side_effect = ValueError("không phải JSON")
    else:
        resp.json.return_value = json_data
    return resp


SAMPLE_DEVICES = {"response": [
    {"hostname": "R1-1822040092", "type": "Router", "managementIpAddress": "10.1.1.1",
     "reachabilityStatus": "Reachable"},
    {"hostname": "SW1-1822040092", "type": "Switch", "managementIpAddress": "10.1.1.2",
     "reachabilityStatus": "Unreachable"},
], "version": "1.0"}


# ---- 1. Hàm phân tích JSON (không cần mock) ----
def test_parse_devices_extracts_fields():
    rows = app.parse_devices(SAMPLE_DEVICES)
    assert len(rows) == 2
    assert rows[0] == {"source": "device", "hostname": "R1-1822040092", "type": "Router",
                       "ip": "10.1.1.1", "status": "Reachable"}
    assert rows[1]["status"] == "Unreachable"


def test_parse_devices_missing_fields_use_default():
    rows = app.parse_devices({"response": [{"hostname": "X"}]})
    assert rows[0]["ip"] == "N/A" and rows[0]["type"] == "N/A"


PT_RESPONSE = {"response": [
    {   # router: Controller không trả hostname, type rỗng
        "collectionStatus": "Unsupported", "type": "",
        "ipAddresses": ["192.168.1.1", "10.0.0.1"],
        "managementIpAddress": "10.0.0.1", "reachabilityStatus": "Reachable",
    },
    {   # switch: có hostname và danh sách láng giềng
        "hostname": "SW1-1822040092", "type": "Switch", "collectionStatus": "Managed",
        "managementIpAddress": "192.168.1.2", "reachabilityStatus": "Reachable",
        "connectedNetworkDeviceName": ["PC1-1822040092", "R1-1822040092"],
        "connectedNetworkDeviceIpAddress": ["192.168.1.11", "192.168.1.1"],
    },
], "version": "1.0"}


def test_parse_devices_router_hostname_from_neighbor_names():
    rows = app.parse_devices(PT_RESPONSE)
    router = rows[0]
    assert router["hostname"] == "R1-1822040092"
    assert router["type"] == "Router"
    assert router["ip"] == "10.0.0.1"


def test_parse_devices_unknown_hostname_stays_na():
    rows = app.parse_devices({"response": [
        {"type": "", "ipAddresses": ["172.16.0.1"], "managementIpAddress": "172.16.0.1"}]})
    assert rows[0]["hostname"] == "N/A" and rows[0]["type"] == "N/A"


def test_parse_devices_empty_response_returns_empty_list():
    assert app.parse_devices({"response": []}) == []


def test_parse_devices_no_response_key_with_version_is_empty():
    assert app.parse_devices({"version": "1.0"}) == []


def test_parse_devices_bad_format_raises():
    with pytest.raises(app.ControllerError):
        app.parse_devices({"khong_co_response": 1})


# ---- 2. get_ticket với requests.post bị mock ----
def test_get_ticket_success():
    fake = make_response(201, {"response": {"serviceTicket": "ST-123"}})
    with patch("controller_app.requests.post", return_value=fake) as post:
        assert app.get_ticket(BASE, "cisco", "cisco") == "ST-123"
    post.assert_called_once()
    assert post.call_args.kwargs["json"] == {"username": "cisco", "password": "cisco"}
    assert post.call_args.kwargs["timeout"] == app.TIMEOUT


def test_get_ticket_wrong_password():
    with patch("controller_app.requests.post", return_value=make_response(401, {})):
        with pytest.raises(app.ControllerError, match="Sai tài khoản"):
            app.get_ticket(BASE, "cisco", "sai")


def test_get_ticket_connection_error():
    with patch("controller_app.requests.post", side_effect=requests.exceptions.ConnectionError("refused")):
        with pytest.raises(app.ControllerError, match="Không kết nối"):
            app.get_ticket(BASE, "cisco", "cisco")


# ---- 3. get_devices với requests.get bị mock ----
def test_get_devices_sends_token_header():
    with patch("controller_app.requests.get", return_value=make_response(200, SAMPLE_DEVICES)) as get:
        rows = app.get_devices(BASE, "ST-123")
    assert len(rows) == 2
    assert get.call_args.kwargs["headers"] == {"X-Auth-Token": "ST-123"}
    assert get.call_args.args[0] == BASE + "/api/v1/network-device"


def test_get_devices_expired_ticket_raises_ticket_invalid():
    with patch("controller_app.requests.get", return_value=make_response(401, {})):
        with pytest.raises(app.TicketInvalid):
            app.get_devices(BASE, "ST-cu")


# ---- 4. Tự lấy ticket mới khi hết hạn ----
def test_fetch_with_retry_renews_ticket():
    calls = []

    def fake_fetch(base, ticket):
        calls.append(ticket)
        if ticket == "ST-cu":
            raise app.TicketInvalid("hết hạn")
        return ["ok"]

    with patch("controller_app.get_ticket", return_value="ST-moi") as gt:
        result, ticket = app.fetch_with_retry(fake_fetch, BASE, "ST-cu", "cisco", "cisco")
    assert result == ["ok"] and ticket == "ST-moi"
    assert calls == ["ST-cu", "ST-moi"]
    gt.assert_called_once()


# ---- 5. Lưu CSV và đọc .env ----
def test_save_csv_writes_header_and_rows(tmp_path):
    out = tmp_path / "inv.csv"
    app.save_csv(app.parse_devices(SAMPLE_DEVICES), str(out))
    with open(out, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2 and rows[0]["hostname"] == "R1-1822040092"


def test_load_env_reads_values_without_overriding(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# ghi chú\nCONTROLLER_URL=http://1.2.3.4\nCONTROLLER_USER = admin\n", encoding="utf-8")
    monkeypatch.delenv("CONTROLLER_URL", raising=False)
    monkeypatch.setenv("CONTROLLER_USER", "da-co")
    app.load_env(str(env))
    import os
    assert os.environ["CONTROLLER_URL"] == "http://1.2.3.4"
    assert os.environ["CONTROLLER_USER"] == "da-co"      # không bị ghi đè


def test_get_config_missing_raises(monkeypatch):
    for k in ("CONTROLLER_URL", "CONTROLLER_USER", "CONTROLLER_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(app.ConfigError):
        app.get_config()