"""
mock_controller.py - Controller GIẢ (mô phỏng APIC-EM) để kiểm thử controller_app.py khi
không có Packet Tracer. KHÔNG dùng thay cho minh chứng Packet Tracer.

Họ tên : Nguyễn Gia Huy   |   MSSV: 1822040092

Chạy:  python mock_controller.py [cổng]      (mặc định 8080)
Tài khoản: cisco / cisco.  Thêm biến môi trường MOCK_EXPIRE=1 để ticket hết hạn sau 3 yêu cầu.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

USER, PASSWORD = "cisco", "cisco"
M = "1822040092"

DEVICES = [
    {"hostname": f"R1-{M}", "type": "Router", "managementIpAddress": "10.1.1.1", "reachabilityStatus": "Reachable"},
    {"hostname": f"R2-{M}", "type": "Router", "managementIpAddress": "10.1.1.2", "reachabilityStatus": "Reachable"},
    {"hostname": f"SW1-{M}", "type": "Switch", "managementIpAddress": "10.1.1.3", "reachabilityStatus": "Reachable"},
    {"hostname": f"SW2-{M}", "type": "Switch", "managementIpAddress": "10.1.1.4", "reachabilityStatus": "Unreachable"},
]
HOSTS = [
    {"hostName": f"PC{i}-{M}", "hostType": "wired", "hostIp": f"192.168.{1 if i < 3 else 2}.{10 + i}"}
    for i in range(1, 5)
]

state = {"tickets": {}, "serial": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/api/v1/ticket":
            return self._send(404, {})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if body.get("username") != USER or body.get("password") != PASSWORD:
            return self._send(401, {"response": {"errorCode": "UNAUTHORIZED"}})
        state["serial"] += 1
        ticket = f"ST-{state['serial']:04d}-mock-ticket-{M}"
        state["tickets"][ticket] = 3 if os.environ.get("MOCK_EXPIRE") else 10 ** 9
        self._send(201, {"response": {"serviceTicket": ticket, "idleTimeout": 900, "sessionTimeout": 3600},
                         "version": "1.0"})

    def do_GET(self):
        ticket = self.headers.get("X-Auth-Token", "")
        if ticket not in state["tickets"] or state["tickets"][ticket] <= 0:
            return self._send(401, {"response": {"errorCode": "TICKET_INVALID"}})
        state["tickets"][ticket] -= 1
        if self.path == "/api/v1/network-device":
            self._send(200, {"response": DEVICES, "version": "1.0"})
        elif self.path == "/api/v1/host":
            self._send(200, {"response": HOSTS, "version": "1.0"})
        else:
            self._send(404, {})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"Mock controller đang chạy tại http://127.0.0.1:{port} (cisco / cisco)")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
