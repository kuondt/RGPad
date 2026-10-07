# Giao dien RGPad tren man hinh muOS (PySDL2 + SDL2_ttf co san trong PortMaster).
import ctypes
import math

import sdl2
import sdl2.sdlttf as ttf

from rgpad_osk import ALT, CTRL, ROWS, SHIFT

W, H = 640, 480

BG = (18, 20, 26)
PANEL = (30, 33, 42)
IDLE = (52, 57, 70)
TEXT = (232, 234, 240)
MUTED = (140, 146, 160)
DARK = (20, 20, 20)
ACCENT = (255, 196, 61)
GREEN = (72, 199, 116)
RED = (235, 87, 87)
YELLOW = (240, 180, 50)


class UI:
    def __init__(self, font_path):
        sdl2.SDL_SetHint(sdl2.SDL_HINT_NO_SIGNAL_HANDLERS, b"1")
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO) != 0:
            raise RuntimeError(sdl2.SDL_GetError().decode(errors="replace"))
        if ttf.TTF_Init() != 0:
            raise RuntimeError("TTF_Init loi")

        dm = sdl2.SDL_DisplayMode()
        if sdl2.SDL_GetCurrentDisplayMode(0, ctypes.byref(dm)) == 0 and dm.w > 0:
            w, h = dm.w, dm.h
        else:
            w, h = W, H
        self.window = sdl2.SDL_CreateWindow(
            b"RGPad", sdl2.SDL_WINDOWPOS_CENTERED, sdl2.SDL_WINDOWPOS_CENTERED,
            w, h, sdl2.SDL_WINDOW_SHOWN)
        if not self.window:
            raise RuntimeError(sdl2.SDL_GetError().decode(errors="replace"))
        # khong dung VSYNC de khong chan vong lap gui du lieu
        self.ren = (sdl2.SDL_CreateRenderer(self.window, -1, sdl2.SDL_RENDERER_ACCELERATED)
                    or sdl2.SDL_CreateRenderer(self.window, -1, sdl2.SDL_RENDERER_SOFTWARE))
        if not self.ren:
            raise RuntimeError(sdl2.SDL_GetError().decode(errors="replace"))
        sdl2.SDL_RenderSetLogicalSize(self.ren, W, H)
        sdl2.SDL_SetRenderDrawBlendMode(self.ren, sdl2.SDL_BLENDMODE_BLEND)

        self.fonts = {}
        for size in (14, 16, 20, 30):
            font = ttf.TTF_OpenFont(font_path.encode(), size)
            if not font:
                raise RuntimeError("Khong mo duoc font " + font_path)
            self.fonts[size] = font
        self.cache = {}
        self.snapshot_path = None   # dat duong dan .bmp de chup lai khung hinh tiep theo
        self.kb = None              # rgpad_osk.Keyboard (client gan vao)

    # ---- ve co ban ----
    def color(self, c):
        sdl2.SDL_SetRenderDrawColor(self.ren, c[0], c[1], c[2], 255)

    def rect(self, x, y, w, h, c, r=0):
        self.color(c)
        r = min(r, h // 2, w // 2)
        sdl2.SDL_RenderFillRect(self.ren, sdl2.SDL_Rect(x, y + r, w, h - 2 * r))
        for dy in range(r):
            off = r - int(math.sqrt(r * r - (r - dy - 0.5) ** 2))
            sdl2.SDL_RenderDrawLine(self.ren, x + off, y + dy, x + w - 1 - off, y + dy)
            sdl2.SDL_RenderDrawLine(self.ren, x + off, y + h - 1 - dy, x + w - 1 - off, y + h - 1 - dy)

    def circle(self, cx, cy, r, c):
        self.color(c)
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(r * r - dy * dy))
            sdl2.SDL_RenderDrawLine(self.ren, cx - dx, cy + dy, cx + dx, cy + dy)

    def text(self, s, size, color, x, y, align="left"):
        key = (s, size, color)
        t = self.cache.get(key)
        if t is None:
            surf = ttf.TTF_RenderUTF8_Blended(self.fonts[size], s.encode("utf-8"),
                                              sdl2.SDL_Color(color[0], color[1], color[2], 255))
            if not surf:
                return 0
            tex = sdl2.SDL_CreateTextureFromSurface(self.ren, surf)
            t = (tex, surf.contents.w, surf.contents.h)
            sdl2.SDL_FreeSurface(surf)
            if len(self.cache) > 300:
                self._clear_cache()
            self.cache[key] = t
        tex, w, h = t
        if align == "center":
            x -= w // 2
        elif align == "right":
            x -= w
        sdl2.SDL_RenderCopy(self.ren, tex, None, sdl2.SDL_Rect(x, y, w, h))
        return w

    def _clear_cache(self):
        for tex, _, _ in self.cache.values():
            sdl2.SDL_DestroyTexture(tex)
        self.cache.clear()

    # ---- thanh phan ----
    def key(self, x, y, w, h, label, on):
        self.rect(x, y, w, h, ACCENT if on else IDLE, 6)
        self.text(label, 14, DARK if on else TEXT, x + w // 2, y + (h - 17) // 2, "center")

    def face(self, cx, cy, label, on):
        self.circle(cx, cy, 19, ACCENT if on else IDLE)
        self.text(label, 16, DARK if on else TEXT, cx, cy - 10, "center")

    def hint(self, x, y, keys, desc):
        w = self.text(keys, 14, ACCENT, x, y)
        self.text(desc, 14, MUTED, x + w + 8, y)

    # ---- man hinh ----
    def draw(self, st):
        self.color(BG)
        sdl2.SDL_RenderClear(self.ren)
        if st.get("kb") is not None and self.kb:
            self._draw_keyboard(st)
        else:
            self._draw_pad(st)
        if self.snapshot_path:
            self._save(self.snapshot_path)
            self.snapshot_path = None
        sdl2.SDL_RenderPresent(self.ren)

    def _draw_keyboard(self, st):
        kb = self.kb
        self.text("RGPad", 30, ACCENT, 24, 12)
        self.text("Bàn phím → PC", 16, MUTED, 24, 52)
        dot = {"search": YELLOW, "ok": GREEN, "lost": RED}[st["status"]]
        self.circle(560, 31, 6, dot)
        if st["battery"] is not None:
            self.text("Pin %d%%" % st["battery"], 16, MUTED, 616, 22, "right")

        # o xem lai nhung gi da go
        self.rect(16, 82, 608, 60, PANEL, 10)
        shown = kb.text
        while shown and self._width(shown + "|", 20) > 580:   # chi hien phan cuoi vua o
            shown = shown[1:]
        self.text(shown + "|", 20, TEXT, 30, 90)
        pending = st.get("kb_pending", 0)
        sub = "Đang gửi %d phím…" % pending if pending else "Gõ vào cửa sổ đang mở trên PC"
        self.text(sub, 14, YELLOW if pending else MUTED, 30, 118)

        # cac phim
        unit, h, x0, y0 = 46, 40, 21, 152
        for r, row in enumerate(ROWS):
            x = x0
            for c, (key_id, w) in enumerate(row):
                sel = (r, c) == (kb.row, kb.col)
                mod = {"shift": SHIFT, "ctrl": CTRL, "alt": ALT}.get(key_id)
                active = mod is not None and kb.mods & mod
                fill = ACCENT if sel else (GREEN if active else IDLE)
                self.rect(x + 2, y0 + r * 46, w * unit - 4, h, fill, 6)
                label = kb.label(key_id)
                size = 20 if len(label) == 1 else 14
                self.text(label, size, DARK if sel or active else TEXT,
                          x + w * unit // 2, y0 + r * 46 + (h - (24 if size == 20 else 17)) // 2, "center")
                x += w * unit

        # huong dan
        self.hint(24, 392, "A", "Gõ")
        self.hint(84, 392, "B", "Xoá")
        self.hint(150, 392, "Y", "Cách")
        self.hint(220, 392, "X", "Shift")
        self.hint(300, 392, "L2", "Ctrl")
        self.hint(374, 392, "START", "Enter")
        self.hint(474, 392, "SELECT", "Esc")
        self.hint(24, 420, "L1 / R1", "← →")
        self.hint(150, 420, "D-pad / cần", "Chọn phím")
        self.hint(374, 420, "MENU + X", "Đóng")
        self.hint(24, 448, "MENU + START", "Thoát app")

    def _width(self, s, size):
        w, h = ctypes.c_int(), ctypes.c_int()
        ttf.TTF_SizeUTF8(self.fonts[size], s.encode("utf-8"), ctypes.byref(w), ctypes.byref(h))
        return w.value

    def _draw_pad(self, st):
        p = st["pressed"]

        # tieu de
        self.text("RGPad", 30, ACCENT, 24, 12)
        self.text("Tay cầm không dây cho PC", 16, MUTED, 24, 52)
        if st["battery"] is not None:
            self.text("Pin %d%%" % st["battery"], 16, MUTED, 616, 22, "right")

        # trang thai ket noi
        self.rect(16, 82, 608, 60, PANEL, 10)
        pc = st["pc"] or ""
        dot, title, sub = {
            "search": (YELLOW, "Đang tìm PC trong mạng…", "Hãy chạy start_server.bat trên PC"),
            "ok": (GREEN, "Đã kết nối PC  " + pc, "Cổng UDP %d" % st["port"]),
            "lost": (RED, "Mất tín hiệu từ PC  " + pc, "Vẫn đang gửi nút. Kiểm tra WiFi và server trên PC"),
        }[st["status"]]
        self.circle(42, 112, 7, dot)
        self.text(title, 20, TEXT, 62, 88)
        self.text(sub, 14, MUTED, 62, 116)

        # so do tay cam
        self.rect(16, 152, 608, 222, PANEL, 12)
        # dung thu tu tren may (nhin tu mat truoc): L1 mep ngoai, L2 phia trong
        self.key(32, 164, 70, 24, "L1", "LB" in p or st["l3"])
        self.key(108, 164, 70, 24, "L2", "LT" in p)
        self.key(462, 164, 70, 24, "R2", "RT" in p)
        self.key(538, 164, 70, 24, "R1", "RB" in p or st["r3"])

        cx, cy, s = 110, 262, 30
        up, down, left, right = st["dpad"]
        self.rect(cx - s // 2, cy - s // 2, s, s, IDLE)
        self.rect(cx - s // 2, cy - s // 2 - s, s, s, ACCENT if up else IDLE, 4)
        self.rect(cx - s // 2, cy + s // 2, s, s, ACCENT if down else IDLE, 4)
        self.rect(cx - s // 2 - s, cy - s // 2, s, s, ACCENT if left else IDLE, 4)
        self.rect(cx + s // 2, cy - s // 2, s, s, ACCENT if right else IDLE, 4)
        if st["mouse"]:
            dpad_role = "D-pad" if st["menu"] else "Di chuột"
        else:
            dpad_role = "Camera" if st["dpad_cam"] else "D-pad"
        self.text(dpad_role, 14, MUTED, cx, cy + 52, "center")

        sx, sy = 300, 262
        self.circle(sx, sy, 48, IDLE)
        self.circle(sx, sy, 45, BG)
        lx, ly = st["stick"]
        moving = math.hypot(lx, ly) > 0.1
        self.circle(int(sx + lx * 32), int(sy + ly * 32), 13, ACCENT if moving else TEXT)
        stick_role = "di chuột" if st["mouse"] else ("xoay camera" if st["menu"] else "di chuyển")
        self.text("Cần analog: " + stick_role,
                  14, MUTED, sx, 314, "center")

        fx, fy, o = 530, 262, 34
        # dung bo cuc tren may: X tren, A phai, B duoi, Y trai (gan theo chu in)
        self.face(fx, fy - o, "X", "X" in p)
        self.face(fx + o, fy, "A", "A" in p)
        self.face(fx, fy + o, "B", "B" in p)
        self.face(fx - o, fy, "Y", "Y" in p)

        self.key(190, 342, 70, 22, "SELECT", "BACK" in p)
        self.key(265, 342, 70, 22, "MENU", st["menu"])
        self.key(340, 342, 70, 22, "START", "START" in p)

        # che do
        if st["mouse"]:
            self.rect(16, 384, 608, 30, ACCENT, 8)
            self.text("CHUỘT · A trái · B phải · L1/R1 cuộn · giữ MENU: D-pad tay cầm",
                      14, DARK, 320, 390, "center")
        else:
            self.rect(16, 384, 296, 30, ACCENT if st["dpad_cam"] else PANEL, 8)
            self.text("MENU+SELECT · D-pad camera: " + ("BẬT" if st["dpad_cam"] else "TẮT"),
                      14, DARK if st["dpad_cam"] else TEXT, 164, 390, "center")
            flags, name = st.get("macro") or (0, "")
            if flags & 2:   # PC co macro: hien macro thay cho goi y xoay camera
                running = flags & 1
                self.rect(328, 384, 296, 30, GREEN if running else PANEL, 8)
                label = ("▶ " if running else "MENU+A chạy: ") + name
                while len(label) > 4 and self._width(label, 14) > 280:
                    label = label[:-2] + "…"
                self.text(label, 14, DARK if running else TEXT, 476, 390, "center")
            else:
                self.rect(328, 384, 296, 30, ACCENT if st["menu"] else PANEL, 8)
                self.text("MENU: cần analog đang xoay camera" if st["menu"] else "Giữ MENU để xoay camera",
                          14, DARK if st["menu"] else MUTED, 476, 390, "center")

        # huong dan
        self.hint(24, 426, "MENU + START", "Thoát")
        self.hint(328, 426, "MENU + Y", "Chuột ↔ tay cầm")
        self.hint(24, 452, "Giữ MENU + cần", "Xoay camera")
        self.hint(328, 452, "MENU + X", "Bàn phím")

    def _save(self, path):
        w, h = ctypes.c_int(), ctypes.c_int()
        sdl2.SDL_GetRendererOutputSize(self.ren, ctypes.byref(w), ctypes.byref(h))
        fmt = sdl2.SDL_PIXELFORMAT_ARGB8888
        surf = sdl2.SDL_CreateRGBSurfaceWithFormat(0, w.value, h.value, 32, fmt)
        if not surf:
            return
        sdl2.SDL_RenderReadPixels(self.ren, None, fmt, surf.contents.pixels, surf.contents.pitch)
        sdl2.SDL_SaveBMP(surf, path.encode())
        sdl2.SDL_FreeSurface(surf)

    def pump(self):
        """Xu ly su kien SDL. Tra ve True neu he thong yeu cau dong app."""
        ev = sdl2.SDL_Event()
        quit_req = False
        while sdl2.SDL_PollEvent(ctypes.byref(ev)):
            if ev.type == sdl2.SDL_QUIT:
                quit_req = True
        return quit_req

    def close(self):
        self._clear_cache()
        for font in self.fonts.values():
            ttf.TTF_CloseFont(font)
        sdl2.SDL_DestroyRenderer(self.ren)
        sdl2.SDL_DestroyWindow(self.window)
        ttf.TTF_Quit()
        sdl2.SDL_Quit()
