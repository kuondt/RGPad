"""Phần lõi RGPad trên PC: nhận gói UDP từ RG40XXV và điều khiển tay cầm Xbox 360 ảo.

Dùng chung cho rgpad_server.py (dòng lệnh) và rgpad_web.py (giao diện web).
"""
import ctypes
import math
import socket
import struct
import threading
import time

PKT = struct.Struct("<4sIHhhhhBB")
NEUTRAL = (0, 0, 0, 0, 0, 0, 0)
DEFAULT_PORT = 9876
MOUSE_FLAG = 0x0800   # bit trống trong XInput: máy cầm tay đang ở chế độ chuột
KEYBOARD_FLAG = 0x0400  # bit GUIDE (RGPad không dùng): máy cầm tay đang mở bàn phím ảo
MODE_FLAGS = MOUSE_FLAG | KEYBOARD_FLAG
KEY_PKT = struct.Struct("<4sIBBH")   # "RGK1", số thứ tự, hành động, phím phụ, mã VK
SHIFT, CTRL, ALT = 1, 2, 4
EXTENDED_VK = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}   # mũi tên, Home, Del...
NAMES = {
    0x0001: "UP", 0x0002: "DOWN", 0x0004: "LEFT", 0x0008: "RIGHT",
    0x0010: "START", 0x0020: "BACK", 0x0040: "L3", 0x0080: "R3",
    0x0100: "LB", 0x0200: "RB", 0x0400: "GUIDE",
    0x1000: "A", 0x2000: "B", 0x4000: "X", 0x8000: "Y",
}


def local_ips():
    try:
        return [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2]
                if not ip.startswith("127.")]
    except OSError:
        return []


class NullPad:
    def apply(self, st):
        pass


class PrintPad:
    def apply(self, st):
        b, lx, ly, rx, ry, lt, rt = st
        names = [n for bit, n in NAMES.items() if b & bit]
        print("nút=%-24s L=(%6d,%6d) R=(%6d,%6d) LT=%3d RT=%3d"
              % (",".join(names) or "-", lx, ly, rx, ry, lt, rt))


class XboxPad:
    def __init__(self):
        import vgamepad as vg
        self.vg = vg
        self.pad = vg.VX360Gamepad()

    def apply(self, st):
        b, lx, ly, rx, ry, lt, rt = st
        pad = self.pad
        pad.reset()
        for btn in self.vg.XUSB_BUTTON:
            if b & int(btn):
                pad.press_button(button=btn)
        pad.left_joystick(x_value=lx, y_value=ly)
        pad.right_joystick(x_value=rx, y_value=ry)
        pad.left_trigger(value=lt)
        pad.right_trigger(value=rt)
        pad.update()


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _KeybdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput), ("ki", _KeybdInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _InputUnion)]


class MouseDriver:
    """Điều khiển chuột/bàn phím Windows từ trạng thái nút của máy cầm tay.

    D-pad và cần analog di chuột, A/B/X = chuột trái/phải/giữa, L1/R1 = cuộn,
    giữ L2 = di chậm, START = Enter, SELECT = Esc.
    """

    # (bit nút, cờ nhấn, cờ nhả) của SendInput
    CLICKS = ((0x1000, 0x0002, 0x0004), (0x2000, 0x0008, 0x0010), (0x4000, 0x0020, 0x0040))
    KEYS = ((0x0010, 0x0D), (0x0020, 0x1B))   # START -> Enter, BACK -> Esc
    STICK_SPEED = 1600    # px/giây khi đẩy cần hết cỡ
    DPAD_MIN, DPAD_MAX, DPAD_RAMP = 250, 1200, 900

    def __init__(self):
        self.state = None     # None = không ở chế độ chuột
        self.held = 0
        self._send = ctypes.windll.user32.SendInput
        self._stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _input(self, inp):
        self._send(1, ctypes.byref(inp), ctypes.sizeof(_Input))

    def _mouse(self, flags, dx=0, dy=0, data=0):
        inp = _Input(type=0)
        inp.u.mi = _MouseInput(dx, dy, data, flags, 0, 0)
        self._input(inp)

    def _key(self, vk, down):
        inp = _Input(type=1)
        scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)   # mã quét: một số game chỉ đọc cái này
        flags = (0 if down else 0x0002) | (0x0001 if vk in EXTENDED_VK else 0)
        inp.u.ki = _KeybdInput(vk, scan, flags, 0, 0)
        self._input(inp)

    def update(self, st):
        """Gọi mỗi khi trạng thái đổi. st=None: rời chế độ chuột, nhả hết nút."""
        self.state = st
        b = st[0] if st else 0
        changed = b ^ self.held
        for bit, down, up in self.CLICKS:
            if changed & bit:
                self._mouse(down if b & bit else up)
        for bit, vk in self.KEYS:
            if changed & bit:
                self._key(vk, bool(b & bit))
        self.held = b

    def tap_key(self, vk, mods=0):
        """Gõ một phím (kèm Shift/Ctrl/Alt) như bàn phím thật, dùng được với Unikey."""
        held = [m_vk for bit, m_vk in ((CTRL, 0x11), (ALT, 0x12), (SHIFT, 0x10)) if mods & bit]
        for m_vk in held:
            self._key(m_vk, True)
        self._key(vk, True)
        self._key(vk, False)
        for m_vk in reversed(held):
            self._key(m_vk, False)

    def close(self):
        self.update(None)
        self._stop.set()

    def _run(self):
        fx = fy = 0.0
        dpad_since = None
        last_scroll = 0.0
        last = time.monotonic()
        while not self._stop.wait(1 / 120):
            now = time.monotonic()
            dt, last = min(now - last, 0.05), now
            st = self.state
            if not st:
                dpad_since = None
                continue
            b, lx, ly, _, _, lt, _ = st
            # cần analog: tốc độ tăng theo bình phương để dễ di chậm
            x, y = lx / 32767, -ly / 32767
            vx = math.copysign(x * x, x) * self.STICK_SPEED
            vy = math.copysign(y * y, y) * self.STICK_SPEED
            # D-pad: chạy nhanh dần khi giữ lâu
            dx = bool(b & 0x0008) - bool(b & 0x0004)
            dy = bool(b & 0x0002) - bool(b & 0x0001)
            if dx or dy:
                dpad_since = dpad_since or now
                speed = min(self.DPAD_MAX, self.DPAD_MIN + self.DPAD_RAMP * (now - dpad_since))
                norm = math.hypot(dx, dy)
                vx += dx / norm * speed
                vy += dy / norm * speed
            else:
                dpad_since = None
            if lt > 127:   # giữ L2: di chậm để nhắm chính xác
                vx, vy = vx * 0.3, vy * 0.3
            fx += vx * dt
            fy += vy * dt
            ix, iy = int(fx), int(fy)
            if ix or iy:
                fx -= ix
                fy -= iy
                self._mouse(0x0001, ix, iy)
            # L1 cuộn lên, R1 cuộn xuống (lặp lại khi giữ)
            scroll = bool(b & 0x0100) - bool(b & 0x0200)
            if scroll and now - last_scroll > 0.08:
                self._mouse(0x0800, data=ctypes.c_ulong(120 * scroll & 0xFFFFFFFF).value)
                last_scroll = now


class RGPadServer:
    """Chạy vòng nhận UDP trong một luồng riêng.

    Ném OSError ngay khi khởi tạo nếu cổng đã bị chương trình khác dùng.
    """

    def __init__(self, pad, port=DEFAULT_PORT, log=print, mouse=None):
        self.pad = pad
        self.mouse = mouse        # MouseDriver hoặc None (không điều khiển chuột)
        self.port = port
        self.log = log
        self.state = NEUTRAL      # trạng thái nút mới nhất nhận được
        self.client = None        # IP máy cầm tay
        self.client_addr = None   # (IP, cổng) của bản RGPad đang được nhận
        self.dup_seen = 0.0       # lần cuối thấy một bản RGPad thứ hai cùng gửi
        self.keys_done = []       # số thứ tự các phím đã gõ gần đây (bỏ gói gửi lại)
        self.keys_typed = 0
        self.macro = None         # rgpad_macro.MacroRunner (gán sau khi tạo)
        self._out_lock = threading.Lock()
        self.last_rx = 0.0
        self.rate = 0             # gói/giây
        self.paused = False
        self._count = 0
        self._rate_t = time.monotonic()
        self._stop = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):   # Windows: chỉ một RGPad được nghe cổng này
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        self.sock.bind(("0.0.0.0", port))
        self.sock.settimeout(0.1)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=1)
        self.sock.close()
        self.pad.apply(NEUTRAL)
        if self.mouse:
            self.mouse.close()

    def mouse_mode(self):
        return bool(self.state[0] & MOUSE_FLAG)

    def keyboard_mode(self):
        return bool(self.state[0] & KEYBOARD_FLAG)

    def _on_key(self, data, addr):
        """Gói phím từ bàn phím ảo: luôn xác nhận, chỉ gõ một lần dù gói bị gửi lại."""
        _magic, k_seq, action, mods, vk = KEY_PKT.unpack(data)
        self.sock.sendto(b"RGKA" + struct.pack("<I", k_seq), addr)
        if addr[0] != self.client or k_seq in self.keys_done:
            return
        self.keys_done = (self.keys_done + [k_seq])[-64:]
        if action in (2, 3):      # MENU + A: chạy/dừng macro, MENU + B: đổi macro
            if self.macro:
                self.macro.toggle() if action == 2 else self.macro.next()
            else:
                self.log("Chưa bật chức năng macro trên PC")
            self.sock.sendto(self.status_reply(), addr)
            return
        self.keys_typed += 1
        if self.paused:
            return
        if self.mouse:
            self.mouse.tap_key(vk, mods)
        else:
            self.log("Phím VK=0x%02X mods=%d (chế độ thử, không gõ thật)" % (vk, mods))

    def connected(self):
        return self.client is not None and time.monotonic() - self.last_rx < 1.0

    def set_paused(self, paused):
        """Tạm dừng: vẫn nhận và hiển thị, nhưng tay cầm ảo nhả hết nút."""
        self.paused = paused
        self.refresh()

    def status_reply(self):
        """'RGP!' + trạng thái macro (bit0 đang chạy, bit1 có macro) + tên macro đang chọn."""
        m = self.macro
        if not m or not m.macros:
            return b"RGP!"
        flags = 2 | (1 if m.running else 0)
        return b"RGP!" + bytes([flags]) + m.active_name().encode("utf-8")[:48]

    def refresh(self):
        """Áp lại đầu ra: chuột Windows, tay cầm ảo (nút thật + nút macro)."""
        with self._out_lock:
            st = self.state
            mouse = bool(st[0] & MOUSE_FLAG)
            if self.mouse:
                self.mouse.update(st if mouse and not self.paused else None)
            if self.paused:
                self.pad.apply(NEUTRAL)
                return
            # chuột hoặc bàn phím ảo: tay cầm ảo chỉ còn nút macro
            out = NEUTRAL if st[0] & MODE_FLAGS else st
            ob, olt, ort = self.macro.overlay if self.macro else (0, 0, 0)
            if ob or olt or ort:
                out = (out[0] | ob, out[1], out[2], out[3], out[4], max(out[5], olt), max(out[6], ort))
            self.pad.apply(out)

    def _apply(self, st):
        if st != self.state:
            self.state = st
            self.refresh()

    def _run(self):
        last_ack = 0.0
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(64)
            except socket.timeout:
                data = None
            except ConnectionResetError:
                continue
            except OSError:
                break
            now = time.monotonic()

            if data == b"RGP?":
                self.sock.sendto(self.status_reply(), addr)
            elif data and data[:4] == b"RGK1" and len(data) == KEY_PKT.size:
                self._on_key(data, addr)
            elif data and len(data) == PKT.size:
                magic, _seq, *new = PKT.unpack(data)
                if magic == b"RGP1":
                    # Chỉ nhận từ một bản RGPad. Bản thứ hai (vd RGPad-Nen còn chạy) sẽ gửi
                    # "không bấm gì" xen kẽ -> nút trong game bị nhả/bấm liên tục.
                    new = tuple(new)
                    other_active = new != NEUTRAL and self.state == NEUTRAL
                    if (self.client_addr and addr != self.client_addr
                            and now - self.last_rx < 1.0 and not other_active):
                        if now - self.dup_seen > 5:
                            self.log("Bỏ qua bản RGPad thứ hai đang gửi từ %s:%d" % addr)
                        self.dup_seen = now
                        continue
                    if addr != self.client_addr:
                        self.client_addr = addr
                        self.client = addr[0]
                        self.log("Đã kết nối với %s:%d" % addr)
                    self.last_rx = now
                    self._count += 1
                    # báo cho máy cầm tay biết PC vẫn đang nhận
                    if now - last_ack > 0.25:
                        self.sock.sendto(self.status_reply(), addr)
                        last_ack = now
                    self._apply(new)

            if self.client and self.state != NEUTRAL and now - self.last_rx > 0.5:
                self.log("Mất tín hiệu từ máy cầm tay, nhả hết nút.")
                self._apply(NEUTRAL)

            if now - self._rate_t >= 1.0:
                self.rate = round(self._count / (now - self._rate_t))
                self._count, self._rate_t = 0, now
