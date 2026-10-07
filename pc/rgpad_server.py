"""RGPad server (dòng lệnh) - chạy trên PC Windows.

Nhận dữ liệu tay cầm từ RG40XXV qua UDP và tạo một tay cầm Xbox 360 ảo
(ViGEmBus) để Genshin / game khác nhận như tay cầm thật.
Bản có giao diện: rgpad_web.py (shortcut "RGPad PC").

    python rgpad_server.py           chạy bình thường
    python rgpad_server.py --dry     chỉ in dữ liệu nhận được (để kiểm tra kết nối)
"""
import argparse
import os
import sys
import time

from rgpad_core import DEFAULT_PORT, MouseDriver, PrintPad, RGPadServer, XboxPad, local_ips
from rgpad_macro import MacroRunner


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--dry", action="store_true", help="không tạo tay cầm ảo, chỉ in dữ liệu")
    args = ap.parse_args()

    if args.dry:
        pad = PrintPad()
    else:
        try:
            pad = XboxPad()
        except ImportError:
            print("Thiếu thư viện vgamepad. Chạy: python -m pip install vgamepad")
            return 1
        except Exception as e:
            print("Không tạo được tay cầm ảo (đã cài ViGEmBus chưa?):", e)
            return 1
        print("Đã tạo tay cầm Xbox 360 ảo.")

    try:
        server = RGPadServer(pad, args.port, mouse=None if args.dry else MouseDriver())
    except OSError:
        print("Cổng UDP %d đang bị chương trình khác dùng (app RGPad PC đang mở?)" % args.port)
        return 1
    server.macro = MacroRunner(os.path.join(os.path.dirname(os.path.abspath(__file__)), "macros.json"))
    server.macro.on_change = server.refresh
    print("Đang chờ RG40XXV ở cổng UDP %d. IP của PC: %s"
          % (args.port, ", ".join(local_ips()) or "?"))
    server.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
