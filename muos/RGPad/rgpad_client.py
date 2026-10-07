#!/usr/bin/env python3
# RGPad client - chay tren Anbernic RG40XXV (muOS).
# Doc tay cam qua evdev, gui trang thai toi PC Windows qua UDP.
#
#   python3 rgpad_client.py          chay binh thuong
#   python3 rgpad_client.py --test   in ma nut / truc de chinh config.json
#   python3 rgpad_client.py --no-grab   khong chiem tay cam (chay nen cung Moonlight)
import fcntl
import glob
import json
import math
import os
import select
import signal
import socket
import struct
import random
import sys
import time
from collections import deque

from rgpad_osk import Keyboard

HERE = os.path.dirname(os.path.abspath(__file__))
EVENT = struct.Struct("llHHi")
EV_KEY, EV_ABS = 0x01, 0x03
PKT = struct.Struct("<4sIHhhhhBB")


def _ioc(direction, nr, size):
    return (direction << 30) | (size << 16) | (ord("E") << 8) | nr


def EVIOCGNAME(n):
    return _ioc(2, 0x06, n)


def EVIOCGBIT(ev, n):
    return _ioc(2, 0x20 + ev, n)


def EVIOCGABS(axis):
    return _ioc(2, 0x40 + axis, 24)


EVIOCGRAB = _ioc(1, 0x90, 4)

# Bit nut theo chuan XInput (server dung dung cac gia tri nay)
XB = {
    "UP": 0x0001, "DOWN": 0x0002, "LEFT": 0x0004, "RIGHT": 0x0008,
    "START": 0x0010, "BACK": 0x0020, "LTHUMB": 0x0040, "RTHUMB": 0x0080,
    "LB": 0x0100, "RB": 0x0200, "GUIDE": 0x0400,
    "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000,
}
MOUSE_FLAG = 0x0800   # bit trong XInput khong dung: bao PC dang o che do chuot
KEYBOARD_FLAG = 0x0400  # bit GUIDE (khong dung): bao PC dang o che do ban phim
KEY_PKT = struct.Struct("<4sIBBH")   # "RGK1", so thu tu, hanh dong, phim phu (Shift/Ctrl/Alt), ma VK

DEFAULT_CONFIG = {
    "pc_ip": "",            # de trong = tu tim PC trong mang LAN
    "port": 9876,
    "device": "",           # de trong = tu do /dev/input/event*
    "grab": True,           # chiem tay cam de muOS khong xu ly nut
    "rate_hz": 125,
    "deadzone": 0.10,
    "dpad_camera_speed": 0.85,
    "dpad_camera_on_start": False,
    # ma phim Linux -> nut Xbox (theo VI TRI: nut duoi = A, phai = B, tren = Y, trai = X)
    "keys": {
        "304": "A", "305": "B", "307": "Y", "308": "X",
        "310": "LB", "311": "RB", "312": "LT", "313": "RT",
        "314": "BACK", "315": "START", "316": "MENU",
        "317": "LTHUMB", "318": "RTHUMB",
        "544": "UP", "545": "DOWN", "546": "LEFT", "547": "RIGHT",
    },
    # ma truc Linux -> ten truc
    "axes": {
        "0": "LX", "1": "LY", "3": "RX", "4": "RY",
        "2": "LT", "5": "RT", "16": "HATX", "17": "HATY",
    },
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    path = os.path.join(HERE, "config.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def dev_name(fd):
    buf = bytearray(256)
    try:
        fcntl.ioctl(fd, EVIOCGNAME(len(buf)), buf)
    except OSError:
        return "?"
    return buf.split(b"\0", 1)[0].decode(errors="replace")


def has_key(fd, code):
    buf = bytearray(96)
    try:
        fcntl.ioctl(fd, EVIOCGBIT(EV_KEY, len(buf)), buf)
    except OSError:
        return False
    return bool(buf[code // 8] & (1 << (code % 8)))


def abs_range(fd, axis):
    buf = bytearray(24)
    try:
        fcntl.ioctl(fd, EVIOCGABS(axis), buf)
    except OSError:
        return None
    _, lo, hi, _, _, _ = struct.unpack("6i", buf)
    return (lo, hi) if hi > lo else None


def find_device(cfg):
    if cfg["device"]:
        return cfg["device"]
    paths = sorted(glob.glob("/dev/input/event*"), key=lambda p: int(p.rsplit("event", 1)[1]))
    for p in paths:
        try:
            fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            if has_key(fd, 304) or has_key(fd, 305):
                return p
        finally:
            os.close(fd)
    return None


def deadzone(x, y, dz):
    mag = math.hypot(x, y)
    if mag < dz:
        return 0.0, 0.0
    scale = min(1.0, (mag - dz) / (1.0 - dz)) / mag
    return x * scale, y * scale


def to_i16(v):
    return max(-32767, min(32767, int(round(v * 32767))))


class Mapper:
    """Bien su kien evdev thanh trang thai tay cam Xbox.

    Combo (giu nut MENU):
      MENU + can analog  -> xoay camera (right stick)
      MENU + L1 / R1     -> L3 / R3 (bam can trai / phai)
      MENU + SELECT      -> bat/tat che do D-pad = camera
      MENU + Y           -> bat/tat che do chuot (PC di chuot thay vi tay cam)
      MENU + X           -> mo/dong ban phim ao (go phim sang PC)
      MENU + A / B       -> chay/dung macro / doi macro (macro cai tren trang web PC)
      MENU + START       -> thoat app
    """

    def __init__(self, cfg, ranges):
        self.cfg = cfg
        self.keys = {int(k): v for k, v in cfg["keys"].items()}
        self.axes = {int(k): v for k, v in cfg["axes"].items()}
        self.ranges = ranges            # ma truc -> (min, max)
        self.pressed = set()            # ten nut dang giu
        self.remap = {}                 # nut -> vai tro duoc gan luc bam (combo)
        self.ax = {"LX": 0.0, "LY": 0.0, "RX": 0.0, "RY": 0.0,
                   "LT": 0.0, "RT": 0.0, "HATX": 0, "HATY": 0}
        self.dpad_cam = bool(cfg["dpad_camera_on_start"])
        self.mouse_mode = False
        self.kb = Keyboard()
        self.kb_mode = False
        self.actions = []               # lenh gui PC qua hang doi tin cay: 2 = chay/dung macro, 3 = doi macro
        self.exit_requested = False
        self.messages = []

    def handle(self, etype, code, value):
        if etype == EV_KEY and code in self.keys:
            name = self.keys[code]
            if value:                   # 1 = bam, 2 = giu lap
                if name not in self.pressed:
                    self._press(name)
            else:
                self.pressed.discard(name)
                self.remap.pop(name, None)
                self.kb.release(name)
        elif etype == EV_ABS and code in self.axes:
            name = self.axes[code]
            if name in ("HATX", "HATY"):
                self.ax[name] = (value > 0) - (value < 0)
                return
            rng = self.ranges.get(code)
            if not rng:
                return
            lo, hi = rng
            if name in ("LT", "RT"):
                self.ax[name] = max(0.0, min(1.0, (value - lo) / (hi - lo)))
            else:
                half = (hi - lo) / 2.0
                self.ax[name] = max(-1.0, min(1.0, (value - lo - half) / half))

    def _press(self, name):
        self.pressed.add(name)
        if name == "MENU":
            if "START" in self.pressed:
                self.exit_requested = True
            return
        if "MENU" not in self.pressed:
            if self.kb_mode:
                self.kb.press(name, time.monotonic())
            return
        if name == "LB":
            self.remap[name] = "LTHUMB"
        elif name == "RB":
            self.remap[name] = "RTHUMB"
        elif name == "BACK":
            self.remap[name] = None
            self.dpad_cam = not self.dpad_cam
            self.messages.append("D-pad camera: " + ("BAT" if self.dpad_cam else "TAT"))
        elif name == "START":
            self.remap[name] = None
            self.exit_requested = True
        elif name == "Y":
            self.remap[name] = None
            self.kb_mode = False
            self.mouse_mode = not self.mouse_mode
            self.messages.append("Che do chuot: " + ("BAT" if self.mouse_mode else "TAT"))
        elif name == "X":
            self.remap[name] = None
            self.kb_mode = not self.kb_mode
            self.kb.version += 1
            self.messages.append("Ban phim: " + ("MO" if self.kb_mode else "DONG"))
        elif name in ("A", "B"):
            self.remap[name] = None
            self.actions.append(2 if name == "A" else 3)

    def tick(self, now):
        if self.kb_mode:
            self.kb.tick(now, self.dpad(), (self.ax["LX"], self.ax["LY"]))

    def want_exit(self):
        return self.exit_requested

    def dpad(self):
        return ("UP" in self.pressed or self.ax["HATY"] < 0,
                "DOWN" in self.pressed or self.ax["HATY"] > 0,
                "LEFT" in self.pressed or self.ax["HATX"] < 0,
                "RIGHT" in self.pressed or self.ax["HATX"] > 0)

    def build(self):
        dz = self.cfg["deadzone"]
        menu = "MENU" in self.pressed
        sx, sy = deadzone(self.ax["LX"], self.ax["LY"], dz)
        lt = 255 if "LT" in self.pressed else int(self.ax["LT"] * 255)
        rt = 255 if "RT" in self.pressed else int(self.ax["RT"] * 255)

        if self.kb_mode:
            # ban phim: nut chi dung de go phim, tay cam ao nha het
            return (KEYBOARD_FLAG, 0, 0, 0, 0, 0, 0)

        if self.mouse_mode and menu:
            # giu MENU: D-pad tam thoi la D-pad tay cam (dieu khien menu trong game),
            # thoat che do chuot tam thoi nen chuot nha nut; tha MENU la di chuot lai
            buttons = 0
            for on, name in zip(self.dpad(), ("UP", "DOWN", "LEFT", "RIGHT")):
                if on:
                    buttons |= XB[name]
            return (buttons, 0, 0, 0, 0, 0, 0)

        if self.mouse_mode:
            # gui nguyen trang thai nut + can trai, PC tu doi thanh chuot
            buttons = MOUSE_FLAG
            for name in self.pressed:
                target = self.remap.get(name, name)
                if target in XB:
                    buttons |= XB[target]
            for on, name in zip(self.dpad(), ("UP", "DOWN", "LEFT", "RIGHT")):
                if on:
                    buttons |= XB[name]
            return (buttons, to_i16(sx), to_i16(-sy), 0, 0, lt, rt)

        rx, ry = deadzone(self.ax["RX"], self.ax["RY"], dz)
        lx, ly = sx, sy
        if menu:
            rx, ry, lx, ly = sx, sy, 0.0, 0.0

        up, down, left, right = self.dpad()

        buttons = 0
        for name in self.pressed:
            target = self.remap.get(name, name)
            if target in ("UP", "DOWN", "LEFT", "RIGHT"):
                continue
            if target in XB:
                buttons |= XB[target]

        if self.dpad_cam:
            dx, dy = right - left, down - up
            if (dx or dy) and not (menu and (sx or sy)):
                speed = self.cfg["dpad_camera_speed"]
                norm = math.hypot(dx, dy)
                rx, ry = dx / norm * speed, dy / norm * speed
        else:
            buttons |= (XB["UP"] if up else 0) | (XB["DOWN"] if down else 0)
            buttons |= (XB["LEFT"] if left else 0) | (XB["RIGHT"] if right else 0)

        # Linux: xuong = duong; Xbox: len = duong
        return (buttons, to_i16(lx), to_i16(-ly), to_i16(rx), to_i16(-ry), lt, rt)


def read_events(fd):
    try:
        data = os.read(fd, EVENT.size * 64)
    except BlockingIOError:
        return []
    out = []
    for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
        _, _, etype, code, value = EVENT.unpack_from(data, i)
        out.append((etype, code, value))
    return out


def run_test(fd, cfg):
    keys = {int(k): v for k, v in cfg["keys"].items()}
    axes = {int(k): v for k, v in cfg["axes"].items()}
    print("Bam tung nut / gat can de xem ma. Ctrl+C de thoat.")
    while True:
        select.select([fd], [], [])
        for etype, code, value in read_events(fd):
            if etype == EV_KEY:
                print("KEY  code=%-4d value=%d  -> %s" % (code, value, keys.get(code, "(chua gan)")))
            elif etype == EV_ABS:
                print("ABS  code=%-4d value=%-6d -> %s" % (code, value, axes.get(code, "(chua gan)")))


PORTMASTER_DIRS = ("/mnt/mmc/MUOS/PortMaster", "/opt/muos/PortMaster",
                   "/opt/system/Tools/PortMaster", "/opt/tools/PortMaster", "/roms/ports/PortMaster")


def find_font():
    paths = [os.environ.get("RGPAD_FONT", "")]
    paths += [os.path.join(d, "pylibs/resources/DejaVuSans.ttf") for d in PORTMASTER_DIRS]
    paths += sorted(glob.glob("/usr/share/fonts/**/*.ttf", recursive=True))
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return None


def open_ui():
    """Mo giao dien tren man hinh. Tra ve None neu khong co PySDL2 / font."""
    try:
        import sdl2  # noqa: F401
    except ImportError:
        for d in PORTMASTER_DIRS:
            sys.path.append(os.path.join(d, "exlibs"))
    try:
        from rgpad_ui import UI
        font = find_font()
        if not font:
            raise RuntimeError("khong tim thay font .ttf")
        return UI(font)
    except Exception as e:  # thieu thu vien / loi man hinh: van chay khong giao dien
        print("Khong mo duoc giao dien:", e)
        return None


def read_battery():
    for path in glob.glob("/sys/class/power_supply/*/capacity"):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            pass
    return None


def main():
    cfg = load_config()
    path = find_device(cfg)
    if not path:
        print("Khong tim thay tay cam trong /dev/input")
        return 1
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    print("Tay cam: %s (%s)" % (dev_name(fd), path))

    ranges = {}
    for code in (int(k) for k in cfg["axes"]):
        r = abs_range(fd, code)
        if r:
            ranges[code] = r
            print("  truc %d: %d..%d" % (code, r[0], r[1]))

    if "--test" in sys.argv:
        try:
            run_test(fd, cfg)
        except KeyboardInterrupt:
            pass
        return 0

    # --no-grab: de Moonlight / muOS van doc duoc tay cam (chay nen cung Moonlight)
    if cfg["grab"] and "--no-grab" not in sys.argv:
        try:
            fcntl.ioctl(fd, EVIOCGRAB, 1)
        except OSError as e:
            print("Khong grab duoc tay cam:", e)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    port = int(cfg["port"])
    fixed_ip = cfg["pc_ip"]
    target = (fixed_ip, port) if fixed_ip else None
    print("Gui toi %s:%d" % target if target else "Dang tim PC trong mang LAN...")

    running = [True]

    def stop(*_):
        running[0] = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    ui = None if "--no-ui" in sys.argv else open_ui()

    mapper = Mapper(cfg, ranges)
    if ui:
        ui.kb = mapper.kb
    period = 1.0 / cfg["rate_hz"]
    next_tick = 0.0
    last_discover = 0.0
    last_reply = 0.0               # lan cuoi PC tra loi (server gui "RGP!")
    last_state, last_sent = None, 0.0
    last_draw, last_view = 0.0, None
    last_status = None
    macro = (0, "")                # (co: bit0 dang chay, bit1 co macro; ten macro dang chon)
    battery, last_battery = read_battery(), time.monotonic()
    # co file "chup_man_hinh" trong thu muc app -> luu giao dien ra screen.bmp sau 3 giay
    snap_flag = os.path.exists(os.path.join(HERE, "chup_man_hinh"))
    snapshot_at = time.monotonic() + 3 if snap_flag else None
    kb_snapped = False
    seq = 0
    # phim go tu ban phim ao: gui lai cho toi khi PC xac nhan "RGKA" (khong mat, khong go dup)
    key_queue = deque()
    key_seq = random.randrange(1, 1 << 31)
    key_sent_at, key_tries = 0.0, 0

    def send(state):
        nonlocal seq
        seq = (seq + 1) & 0xFFFFFFFF
        try:
            sock.sendto(PKT.pack(b"RGP1", seq, *state), target)
        except OSError:
            pass  # mat WiFi tam thoi

    try:
        while running[0]:
            timeout = max(0.0, next_tick - time.monotonic())
            try:
                r, _, _ = select.select([fd, sock], [], [], timeout)
            except InterruptedError:
                continue
            if fd in r:
                try:
                    for ev in read_events(fd):
                        mapper.handle(*ev)
                except OSError as e:
                    print("Mat ket noi tay cam:", e)
                    break
            if sock in r:
                try:
                    data, addr = sock.recvfrom(64)
                    if data[:4] == b"RGKA" and len(data) == 8:
                        acked = struct.unpack("<I", data[4:])[0]
                        if key_queue and key_queue[0][0] == acked:
                            key_queue.popleft()
                            key_sent_at, key_tries = 0.0, 0
                    elif data[:4] == b"RGP!":
                        last_reply = time.monotonic()
                        if len(data) > 4:       # trang thai macro: bit0 dang chay, bit1 co macro
                            macro = (data[4], data[5:].decode("utf-8", "replace"))
                        else:
                            macro = (0, "")
                        if target is None or (not fixed_ip and addr[0] != target[0]):
                            target = (addr[0], port)
                            print("Da tim thay PC:", addr[0])
                except OSError:
                    pass

            for msg in mapper.messages:
                print(msg)
            mapper.messages.clear()
            if mapper.want_exit():
                print("Thoat (MENU + START)")
                break

            now = time.monotonic()
            if now < next_tick:
                continue
            next_tick = now + period

            if target is None:
                status = "search"
            elif now - last_reply < 3.0:
                status = "ok"
            else:
                status = "lost"
            if status != last_status:
                print({"search": "Dang tim PC...", "ok": "Da ket noi PC",
                       "lost": "Mat tin hieu tu PC"}[status])
                last_status = status

            # chua co PC, hoac PC im lang lau (vd doi IP): phat goi tim PC.
            # Van tiep tuc gui nut toi dia chi cu de game khong bi khung.
            if target is None or (not fixed_ip and now - last_reply > 10.0):
                if now - last_discover > (1.0 if target is None else 2.0):
                    last_discover = now
                    try:
                        sock.sendto(b"RGP?", ("255.255.255.255", port))
                    except OSError:
                        pass
            mapper.tick(now)
            for vk, mods in mapper.kb.out:
                if len(key_queue) < 64:
                    key_seq = (key_seq + 1) & 0xFFFFFFFF
                    key_queue.append((key_seq, 1, vk, mods))
            mapper.kb.out.clear()
            for action in mapper.actions:
                key_seq = (key_seq + 1) & 0xFFFFFFFF
                key_queue.append((key_seq, action, 0, 0))
            mapper.actions.clear()
            if target and key_queue and now - key_sent_at > 0.08:
                if key_tries >= 25:      # PC khong tra loi (server cu?): bo phim nay
                    print("PC khong xac nhan phim, bo qua")
                    key_queue.popleft()
                    key_tries = 0
                else:
                    k_seq, action, vk, mods = key_queue[0]
                    try:
                        sock.sendto(KEY_PKT.pack(b"RGK1", k_seq, action, mods, vk), target)
                    except OSError:
                        pass
                    key_sent_at, key_tries = now, key_tries + 1

            if target:
                state = mapper.build()
                if state != last_state or now - last_sent > 0.05:
                    send(state)
                    last_state, last_sent = state, now

            if ui:
                if ui.pump():
                    break
                if now - last_battery > 30:
                    battery, last_battery = read_battery(), now
                pressed = mapper.pressed
                view = {
                    "status": status,
                    "pc": target[0] if target else None,
                    "port": port,
                    "battery": battery,
                    "pressed": frozenset(pressed),
                    "menu": "MENU" in pressed,
                    "l3": mapper.remap.get("LB") == "LTHUMB",
                    "r3": mapper.remap.get("RB") == "RTHUMB",
                    "dpad": mapper.dpad(),
                    "dpad_cam": mapper.dpad_cam,
                    "mouse": mapper.mouse_mode,
                    "kb": mapper.kb.version if mapper.kb_mode else None,
                    "kb_pending": len(key_queue),
                    "macro": macro,
                    "stick": (round(mapper.ax["LX"], 2), round(mapper.ax["LY"], 2)),
                }
                if snap_flag and mapper.kb_mode and not kb_snapped:   # chup ca man hinh ban phim
                    ui.snapshot_path = os.path.join(HERE, "screen_kb.bmp")
                    kb_snapped, last_view = True, None
                if snapshot_at and now >= snapshot_at:
                    ui.snapshot_path = os.path.join(HERE, "screen.bmp")
                    snapshot_at, last_view = None, None
                # ve lai khi co thay doi (toi da 30 hinh/giay)
                if view != last_view and now - last_draw > 1 / 30:
                    ui.draw(view)
                    last_view, last_draw = view, now
    finally:
        if target:
            send((0, 0, 0, 0, 0, 0, 0))
        if ui:
            ui.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
