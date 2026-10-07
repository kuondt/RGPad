# Ban phim ao (on-screen keyboard) cua RGPad: chon phim bang D-pad / can analog,
# go sang PC Windows bang ma phim that (VK) de dung chung voi Unikey.
import time

SHIFT, CTRL, ALT = 1, 2, 4

# ky tu -> (ky tu khi giu Shift, ma phim Windows VK) theo ban phim US
CHARS = {
    "`": ("~", 0xC0), "-": ("_", 0xBD), "=": ("+", 0xBB), "[": ("{", 0xDB), "]": ("}", 0xDD),
    "\\": ("|", 0xDC), ";": (":", 0xBA), "'": ('"', 0xDE), ",": ("<", 0xBC), ".": (">", 0xBE),
    "/": ("?", 0xBF),
    "1": ("!", 0x31), "2": ("@", 0x32), "3": ("#", 0x33), "4": ("$", 0x34), "5": ("%", 0x35),
    "6": ("^", 0x36), "7": ("&", 0x37), "8": ("*", 0x38), "9": ("(", 0x39), "0": (")", 0x30),
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    CHARS[_c] = (_c.upper(), ord(_c.upper()))

# phim dac biet: id -> (nhan, VK)
SPECIAL = {
    "bksp": ("Xoá", 0x08), "enter": ("Enter", 0x0D), "tab": ("Tab", 0x09), "space": ("Cách", 0x20),
    "esc": ("Esc", 0x1B), "left": ("←", 0x25), "up": ("↑", 0x26), "right": ("→", 0x27),
    "down": ("↓", 0x28), "shift": ("Shift", None), "ctrl": ("Ctrl", None), "alt": ("Alt", None),
}

# moi hang 13 o; (id, do rong)
ROWS = [
    [(c, 1) for c in "`1234567890-="],
    [(c, 1) for c in "qwertyuiop[]\\"],
    [(c, 1) for c in "asdfghjkl;'"] + [("enter", 2)],
    [("shift", 2)] + [(c, 1) for c in "zxcvbnm,./"] + [("bksp", 1)],
    [("ctrl", 2), ("alt", 2), ("space", 4), ("left", 1), ("up", 1), ("down", 1), ("right", 1), ("tab", 1)],
]

NAV_DELAY, NAV_REPEAT = 0.35, 0.09     # giu D-pad / can: tu lap
KEY_DELAY, KEY_REPEAT = 0.45, 0.06     # giu B / L1 / R1: tu lap


class Keyboard:
    def __init__(self):
        self.row, self.col = 1, 0
        self.mods = 0              # Shift/Ctrl/Alt dang bat (chi ap dung cho phim ke tiep)
        self.text = ""             # nhung gi da go (de xem lai tren man hinh may)
        self.out = []              # (vk, mods) cho vong lap chinh gui sang PC
        self.version = 0           # tang moi khi can ve lai
        self._nav = None           # (dx, dy, lan lap ke tiep)
        self._held = {}            # nut dang giu -> lan lap ke tiep

    # ---- tra cuu ----
    def label(self, key_id):
        if key_id in SPECIAL:
            return SPECIAL[key_id][0]
        normal, (shifted, _) = key_id, CHARS[key_id]
        return shifted if self.mods & SHIFT else normal

    def selected(self):
        return ROWS[self.row][self.col][0]

    def _center(self, row, col):
        x = sum(w for _, w in ROWS[row][:col])
        return x + ROWS[row][col][1] / 2

    # ---- di chuyen ----
    def move(self, dx, dy):
        if dy:
            cx = self._center(self.row, self.col)
            self.row = (self.row + dy) % len(ROWS)
            self.col = min(range(len(ROWS[self.row])), key=lambda c: abs(self._center(self.row, c) - cx))
        if dx:
            self.col = (self.col + dx) % len(ROWS[self.row])
        self.version += 1

    # ---- go phim ----
    def _emit(self, vk, mods=0, ch=None):
        self.out.append((vk, mods | self.mods))
        if ch is not None and not (self.mods & (CTRL | ALT)):
            self.text = (self.text + ch)[-200:]
        self.mods = 0              # Shift/Ctrl/Alt chi dung cho mot phim
        self.version += 1

    def tap_special(self, key_id):
        vk = SPECIAL[key_id][1]
        if key_id == "bksp":
            self.text = self.text[:-1]
        ch = {"space": " ", "enter": "↵ ", "tab": "  "}.get(key_id)
        self._emit(vk, ch=ch)

    def activate(self):
        key_id = self.selected()
        if key_id in ("shift", "ctrl", "alt"):
            self.mods ^= {"shift": SHIFT, "ctrl": CTRL, "alt": ALT}[key_id]
            self.version += 1
        elif key_id in SPECIAL:
            self.tap_special(key_id)
        else:
            shifted, vk = CHARS[key_id]
            ch = shifted if self.mods & SHIFT else key_id
            self._emit(vk, ch=ch)

    # ---- nut cua may cam tay ----
    def press(self, name, now):
        if name == "A":
            self.activate()
        elif name == "B":
            self.tap_special("bksp")
            self._held[name] = now + KEY_DELAY
        elif name == "Y":
            self.tap_special("space")
        elif name == "X":
            self.mods ^= SHIFT
            self.version += 1
        elif name == "LT":
            self.mods ^= CTRL
            self.version += 1
        elif name == "START":
            self.tap_special("enter")
        elif name == "BACK":
            self.tap_special("esc")
        elif name in ("LB", "RB"):
            self.tap_special("left" if name == "LB" else "right")
            self._held[name] = now + KEY_DELAY

    def release(self, name):
        self._held.pop(name, None)

    def tick(self, now, dpad, stick):
        """Goi deu dan: tu lap khi giu D-pad / can analog / B / L1 / R1."""
        up, down, left, right = dpad
        dx, dy = right - left, down - up
        sx, sy = stick
        if not (dx or dy):
            if abs(sx) > 0.6 or abs(sy) > 0.6:
                if abs(sx) >= abs(sy):
                    dx = 1 if sx > 0 else -1
                else:
                    dy = 1 if sy > 0 else -1
        if dx or dy:
            if self._nav is None or self._nav[:2] != (dx, dy):
                self.move(dx, dy)
                self._nav = (dx, dy, now + NAV_DELAY)
            elif now >= self._nav[2]:
                self.move(dx, dy)
                self._nav = (dx, dy, now + NAV_REPEAT)
        else:
            self._nav = None
        for name, at in list(self._held.items()):
            if now >= at:
                self.tap_special({"B": "bksp", "LB": "left", "RB": "right"}[name])
                self._held[name] = now + KEY_REPEAT


if __name__ == "__main__":
    # tu kiem tra nhanh tren may tinh
    kb = Keyboard()
    t = time.monotonic()
    kb.press("X", t)                 # Shift
    kb.move(0, 0)
    kb.row, kb.col = 1, 0            # 'q'
    kb.activate()                    # 'Q'
    kb.row, kb.col = 0, 1            # '1'
    kb.activate()                    # '1'
    kb.press("Y", t)                 # cach
    kb.press("B", t)                 # xoa
    print(kb.out, repr(kb.text))
