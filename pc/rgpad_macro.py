"""Macro của RGPad: tự bấm một nút hoặc combo nút trên tay cầm Xbox ảo.

Mỗi macro gồm các bước chạy nối tiếp; mỗi bước giữ một nhóm nút trong `hold` ms rồi
nghỉ một khoảng cố định hoặc ngẫu nhiên trong [gapMin, gapMax] ms. `repeat` = số vòng
(0 = lặp tới khi dừng). Lưu trong macros.json, quản lý trên trang web, bật/tắt từ máy
cầm tay bằng MENU + A (chạy/dừng) và MENU + B (đổi macro).
"""
import ctypes
import json
import os
import random
import threading
import uuid

# tên nút -> bit XInput; LT/RT là cò nên xử lý riêng
BUTTON_BITS = {
    "UP": 0x0001, "DOWN": 0x0002, "LEFT": 0x0004, "RIGHT": 0x0008,
    "START": 0x0010, "BACK": 0x0020, "L3": 0x0040, "R3": 0x0080,
    "LB": 0x0100, "RB": 0x0200,
    "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000,
}
TRIGGERS = ("LT", "RT")
ALL_BUTTONS = tuple(BUTTON_BITS) + TRIGGERS

LIMITS = {"macros": 30, "steps": 50, "name": 40, "hold": (10, 10000),
          "gap": (0, 600000), "repeat": (0, 100000)}

DEFAULT_MACROS = [{
    "id": "vi-du-spam-a", "name": "Spam A (ví dụ)", "repeat": 0,
    "steps": [{"buttons": ["A"], "hold": 50, "gapMin": 100, "gapMax": 100}],
}]


def _int(v, lo, hi, name):
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise ValueError("%s phải là số" % name)
    if not lo <= v <= hi:
        raise ValueError("%s phải trong khoảng %d–%d" % (name, lo, hi))
    return v


def normalize(macros):
    """Kiểm tra dữ liệu gửi từ trang web; ném ValueError với thông báo tiếng Việt."""
    if not isinstance(macros, list) or len(macros) > LIMITS["macros"]:
        raise ValueError("Tối đa %d macro" % LIMITS["macros"])
    out, seen = [], set()
    for i, m in enumerate(macros, 1):
        name = str(m.get("name") or "").strip()[:LIMITS["name"]] or "Macro %d" % i
        steps = m.get("steps") or []
        if not 1 <= len(steps) <= LIMITS["steps"]:
            raise ValueError("%s: cần 1–%d bước" % (name, LIMITS["steps"]))
        clean = []
        for j, s in enumerate(steps, 1):
            where = "%s, bước %d" % (name, j)
            buttons = [b for b in ALL_BUTTONS if b in (s.get("buttons") or [])]
            if not buttons:
                raise ValueError("%s: chưa chọn nút nào" % where)
            gap_min = _int(s.get("gapMin", 0), *LIMITS["gap"], name=where + " – nghỉ tối thiểu")
            gap_max = _int(s.get("gapMax", gap_min), *LIMITS["gap"], name=where + " – nghỉ tối đa")
            if gap_max < gap_min:
                raise ValueError("%s: nghỉ tối đa phải ≥ nghỉ tối thiểu" % where)
            clean.append({"buttons": buttons,
                          "hold": _int(s.get("hold", 50), *LIMITS["hold"], name=where + " – giữ"),
                          "gapMin": gap_min, "gapMax": gap_max})
        mid = str(m.get("id") or "")[:40]
        if not mid or mid in seen:
            mid = uuid.uuid4().hex[:12]
        seen.add(mid)
        out.append({"id": mid, "name": name,
                    "repeat": _int(m.get("repeat", 0), *LIMITS["repeat"], name=name + " – số vòng"),
                    "steps": clean})
    return out


class MacroRunner:
    def __init__(self, path, log=print):
        self.path = path
        self.log = log
        self.on_change = lambda: None     # server gán: áp lại tay cầm ảo khi overlay đổi
        self.overlay = (0, 0, 0)          # (bit nút, LT, RT) macro đang giữ
        self.running = None               # id macro đang chạy
        self.loops = 0
        self.step = 0
        self.version = 0                  # tăng khi danh sách macro đổi
        self._lock = threading.Lock()
        self._stop = None
        self._thread = None
        self.macros = self._load()
        self.active = self.macros[0]["id"] if self.macros else None

    # ---- lưu / đọc ----
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return normalize(data.get("macros", []))
        except FileNotFoundError:
            return normalize(DEFAULT_MACROS)
        except (ValueError, OSError) as e:
            self.log("Không đọc được %s (%s), dùng macro ví dụ" % (os.path.basename(self.path), e))
            return normalize(DEFAULT_MACROS)

    def save(self, macros):
        macros = normalize(macros)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"macros": macros}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        ids = [m["id"] for m in macros]
        if self.running and self.running not in ids:
            self.stop()
        with self._lock:
            self.macros = macros
            if self.active not in ids:
                self.active = ids[0] if ids else None
            self.version += 1
        return macros

    def find(self, mid):
        return next((m for m in self.macros if m["id"] == mid), None)

    def active_name(self):
        m = self.find(self.active)
        return m["name"] if m else ""

    def set_active(self, mid):
        if self.find(mid):
            self.active = mid
            self.version += 1

    # ---- điều khiển ----
    def start(self, mid=None):
        macro = self.find(mid or self.active)
        if not macro:
            return False
        self.stop()
        self.active = macro["id"]
        self._stop = threading.Event()
        self.running, self.loops, self.step = macro["id"], 0, 0
        self._thread = threading.Thread(target=self._run, args=(macro, self._stop), daemon=True)
        self._thread.start()
        self.log("Chạy macro: " + macro["name"])
        return True

    def stop(self):
        thread, evt = self._thread, self._stop
        if evt:
            evt.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = self._stop = None

    def toggle(self):
        if self.running:
            name = self.active_name()
            self.stop()
            self.log("Dừng macro: " + name)
        else:
            self.start()

    def next(self):
        """Chuyển sang macro kế tiếp; nếu đang chạy thì chạy luôn macro mới."""
        if not self.macros:
            return
        ids = [m["id"] for m in self.macros]
        i = ids.index(self.active) if self.active in ids else -1
        was_running = bool(self.running)
        self.active = ids[(i + 1) % len(ids)]
        self.version += 1
        if was_running:
            self.start()
        else:
            self.log("Chọn macro: " + self.active_name())

    def status(self):
        return {"running": self.running, "active": self.active, "loops": self.loops,
                "step": self.step, "version": self.version}

    # ---- chạy ----
    def _set(self, buttons):
        bits = 0
        for b in buttons:
            bits |= BUTTON_BITS.get(b, 0)
        self.overlay = (bits, 255 if "LT" in buttons else 0, 255 if "RT" in buttons else 0)
        self.on_change()

    def _run(self, macro, evt):
        winmm = getattr(ctypes, "windll", None) and ctypes.windll.winmm
        if winmm:
            winmm.timeBeginPeriod(1)    # hẹn giờ chính xác ~1 ms thay vì ~15 ms
        try:
            while not evt.is_set():
                for i, s in enumerate(macro["steps"]):
                    self.step = i
                    self._set(s["buttons"])
                    if evt.wait(s["hold"] / 1000.0):
                        break
                    self._set(())
                    if evt.wait(random.uniform(s["gapMin"], s["gapMax"]) / 1000.0):
                        break
                else:
                    self.loops += 1
                    if macro["repeat"] and self.loops >= macro["repeat"]:
                        self.log("Macro %s xong %d vòng" % (macro["name"], self.loops))
                        break
                    continue
                break
        finally:
            if winmm:
                winmm.timeEndPeriod(1)
            self.overlay = (0, 0, 0)
            if self.running == macro["id"]:
                self.running = None
            self.on_change()
