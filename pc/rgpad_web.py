"""RGPad PC - bảng điều khiển web (React) thay cho start_server.bat.

Chạy lõi RGPad (nhận nút từ RG40XXV, tạo tay cầm Xbox ảo) và phục vụ giao diện
tại http://127.0.0.1:8740. Mở bằng start_server.bat / shortcut "RGPad PC": chạy trong
cửa sổ cmd, đóng cửa sổ (hoặc Ctrl+C, hoặc nút "Tắt RGPad" trên web) là tắt.

    python rgpad_web.py           chạy và tự mở trình duyệt
    python rgpad_web.py --dry     không tạo tay cầm ảo (để thử giao diện)
"""
import argparse
import collections
import ctypes
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import socket
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rgpad_core import (DEFAULT_PORT, KEYBOARD_FLAG, MOUSE_FLAG, NEUTRAL, MouseDriver, NullPad, RGPadServer,
                        XboxPad, local_ips)
from rgpad_macro import MacroRunner

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "web", "dist")
WEB_PORT = 8740
SUNSHINE_URL = "https://localhost:47990"


class App:
    """Giữ trạng thái chung cho các yêu cầu HTTP."""

    def __init__(self, dry, udp_port, macros_path):
        self.dry = dry
        self.udp_port = udp_port
        self.log = collections.deque(maxlen=50)
        self.pad = None
        self.pad_error = None
        self.server = None
        self.server_error = None
        self.mouse = None
        self.sunshine = None
        self.quit = threading.Event()
        self.lock = threading.Lock()
        self.macro = MacroRunner(macros_path, log=self.add_log)
        self.macro.on_change = lambda: self.server and self.server.refresh()
        self.start()
        threading.Thread(target=self._watch_sunshine, daemon=True).start()

    def add_log(self, msg):
        entry = {"t": time.strftime("%H:%M:%S"), "msg": msg}
        self.log.append(entry)
        if sys.stdout:  # pythonw khong co cua so -> sys.stdout la None
            print(entry["t"], msg, flush=True)

    def start(self):
        """Tạo tay cầm ảo và mở cổng UDP. Gọi lại được khi bấm "Thử lại"."""
        with self.lock:
            if self.pad is None:
                if self.dry:
                    self.pad = NullPad()
                else:
                    try:
                        self.pad = XboxPad()
                        self.pad_error = None
                        self.add_log("Đã tạo tay cầm Xbox 360 ảo")
                    except Exception as e:
                        self.pad_error = "Không tạo được tay cầm ảo (ViGEmBus): %s" % e
                        self.add_log(self.pad_error)
                        return
            if self.server is None:
                try:
                    if self.mouse is None and not self.dry:
                        self.mouse = MouseDriver()
                    self.server = RGPadServer(self.pad, self.udp_port, log=self.add_log, mouse=self.mouse)
                    self.server.macro = self.macro
                    self.server.start()
                    self.server_error = None
                    self.add_log("Đang chờ RG40XXV ở cổng UDP %d" % self.udp_port)
                except OSError:
                    self.server_error = ("Cổng UDP %d đang bị chương trình khác dùng. "
                                         "Hãy đóng cửa sổ start_server.bat rồi bấm Thử lại." % self.udp_port)
                    self.add_log(self.server_error)

    def stop(self):
        self.macro.stop()
        with self.lock:
            if self.server:
                self.server.stop()
                self.server = None

    def _watch_sunshine(self):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        while not self.quit.is_set():
            try:
                out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq sunshine.exe", "/NH"],
                                     capture_output=True, text=True, creationflags=flags).stdout
                self.sunshine = "sunshine.exe" in out.lower()
            except OSError:
                self.sunshine = None
            self.quit.wait(3)

    def snapshot(self):
        srv = self.server
        if srv is None:
            status = "error"
        elif srv.connected():
            status = "ok"
        elif srv.client:
            status = "lost"
        else:
            status = "waiting"
        b, lx, ly, rx, ry, lt, rt = srv.state if srv else NEUTRAL
        return {
            "status": status,
            "error": self.pad_error or self.server_error,
            "client": srv.client if srv else None,
            "rate": srv.rate if srv and status == "ok" else 0,
            "paused": bool(srv and srv.paused),
            "mouse": bool(b & MOUSE_FLAG),
            "keyboard": bool(b & KEYBOARD_FLAG),
            "keysTyped": srv.keys_typed if srv else 0,
            "macro": dict(self.macro.status(), activeName=self.macro.active_name()),
            "duplicate": bool(srv and time.monotonic() - srv.dup_seen < 3),
            "dry": self.dry,
            "padOk": self.pad is not None and self.pad_error is None,
            "sunshine": self.sunshine,
            "sunshineUrl": SUNSHINE_URL,
            "ips": local_ips(),
            "port": self.udp_port,
            "pad": {"buttons": b, "lx": lx, "ly": ly, "rx": rx, "ry": ry, "lt": lt, "rt": rt},
            "log": list(self.log)[-12:],
        }


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/state":
                return self._json(app.snapshot())
            if path == "/api/events":
                return self._events()
            if path == "/api/macros":
                return self._json({"macros": app.macro.macros, "active": app.macro.active})
            return self._static(path)

        def do_POST(self):
            # header riêng -> trình duyệt chặn trang web lạ gọi tới đây (cần CORS preflight)
            if self.headers.get("X-RGPad") != "1":
                return self._json({"error": "forbidden"}, 403)
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            path = self.path.split("?", 1)[0]
            if path == "/api/pause":
                if app.server:
                    app.server.set_paused(bool(body.get("paused")))
                    app.add_log("Tạm dừng tay cầm ảo" if body.get("paused") else "Tiếp tục nhận nút")
            elif path == "/api/retry":
                app.start()
            elif path == "/api/macros":
                try:
                    app.macro.save(body.get("macros"))
                except ValueError as e:
                    return self._json({"error": str(e)}, 400)
                app.add_log("Đã lưu %d macro" % len(app.macro.macros))
                return self._json({"macros": app.macro.macros, "active": app.macro.active})
            elif path == "/api/macro/start":
                app.macro.start(body.get("id"))
            elif path == "/api/macro/stop":
                if app.macro.running:
                    app.add_log("Dừng macro: " + app.macro.active_name())
                app.macro.stop()
            elif path == "/api/macro/active":
                app.macro.set_active(body.get("id"))
            elif path == "/api/quit":
                app.add_log("Đang tắt RGPad")
                self._json({"ok": True})
                app.quit.set()
                return
            else:
                return self._json({"error": "not found"}, 404)
            return self._json(app.snapshot())

        def _events(self):
            """Server-Sent Events: đẩy trạng thái khi thay đổi (tối đa 30 lần/giây)."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            last, last_sent = None, 0.0
            try:
                while not app.quit.is_set():
                    snap = json.dumps(app.snapshot())
                    now = time.monotonic()
                    if snap != last or now - last_sent > 1.0:
                        self.wfile.write(b"data: " + snap.encode() + b"\n\n")
                        self.wfile.flush()
                        last, last_sent = snap, now
                    time.sleep(1 / 30)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _static(self, path):
            rel = os.path.normpath(path.lstrip("/") or "index.html")
            full = os.path.join(DIST, rel)
            if rel.startswith("..") or not os.path.isfile(full):
                full = os.path.join(DIST, "index.html")
            if not os.path.isfile(full):
                body = "Chưa build giao diện: chạy 'npm run build' trong thư mục web".encode()
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            with open(full, "rb") as f:
                data = f.read()
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


class ExclusiveHTTPServer(ThreadingHTTPServer):
    """Không cho chương trình khác dùng chung cổng.

    Mặc định Python bật SO_REUSEADDR, trên Windows điều đó cho phép nhiều RGPad
    cùng nghe một cổng -> mỗi lần mở lại sinh thêm một bản chạy ngầm.
    """
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def on_console_close(app, cleaned):
    """Đóng cửa sổ cmd -> dọn dẹp (nhả tay cầm ảo, chuột) trước khi Windows tắt tiến trình."""
    if not hasattr(ctypes, "windll"):
        return None

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    def handler(event):
        if event not in (2, 5, 6):   # chỉ đóng cửa sổ / đăng xuất / tắt máy; Ctrl+C để Python xử lý
            return False
        app.quit.set()
        cleaned.wait(3)
        return False

    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)
    return handler   # giữ tham chiếu để không bị thu hồi bộ nhớ


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:  # pythonw: khong co stdout
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="không tạo tay cầm ảo")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="cổng UDP nhận từ RG40XXV")
    ap.add_argument("--web-port", type=int, default=WEB_PORT)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--macros", default=os.path.join(HERE, "macros.json"), help="file lưu macro")
    args = ap.parse_args()
    url = "http://127.0.0.1:%d" % args.web_port

    try:
        httpd = ExclusiveHTTPServer(("127.0.0.1", args.web_port), None)
    except OSError:
        print("RGPad đang chạy rồi (ở một cửa sổ khác). Đã mở lại trang %s" % url)
        print("Muốn tắt bản đang chạy: đóng cửa sổ cmd của nó, hoặc bấm 'Tắt RGPad' trên trang.")
        if not args.no_browser:
            webbrowser.open(url)
        return 2

    app = App(args.dry, args.port, args.macros)
    cleaned = threading.Event()
    _handler = on_console_close(app, cleaned)  # noqa: F841 (giữ cho tới khi thoát)
    httpd.RequestHandlerClass = make_handler(app)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print("Trang điều khiển: %s" % url)
    print("Tắt RGPad: đóng cửa sổ này, bấm Ctrl+C, hoặc nút 'Tắt RGPad' trên trang.")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        while not app.quit.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        app.quit.set()
        app.stop()
        httpd.shutdown()
        httpd.server_close()
        print("Đã tắt RGPad.")
        cleaned.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
