#!/usr/bin/env python3
# Phan tich ket qua kiem tra micro: trang thai lo cam tai nghe (evdev switch) va file ghi am.
import array
import fcntl
import glob
import math
import os
import sys
import wave

EV_SW = 0x05
SW_NAMES = {2: "HEADPHONE_INSERT", 4: "MICROPHONE_INSERT", 6: "LINEOUT_INSERT",
            7: "JACK_PHYSICAL_INSERT"}


def _ioc(direction, nr, size):
    return (direction << 30) | (size << 16) | (ord("E") << 8) | nr


def jack_switches():
    print("=== Cong tac lo cam tai nghe (evdev EV_SW)")
    found = False
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            print(path, "khong mo duoc:", e)
            continue
        try:
            name = bytearray(256)
            fcntl.ioctl(fd, _ioc(2, 0x06, 256), name)
            name = name.split(b"\0", 1)[0].decode(errors="replace")
            caps = bytearray(4)
            try:
                fcntl.ioctl(fd, _ioc(2, 0x20 + EV_SW, 4), caps)   # EVIOCGBIT(EV_SW)
            except OSError:
                continue
            bits = int.from_bytes(caps, "little")
            if not bits:
                continue
            state = bytearray(4)
            fcntl.ioctl(fd, _ioc(2, 0x1B, 4), state)                # EVIOCGSW
            st = int.from_bytes(state, "little")
            found = True
            for code, label in SW_NAMES.items():
                if bits & (1 << code):
                    print("%s (%s): %s = %s" % (path, name, label, "CO" if st & (1 << code) else "khong"))
        finally:
            os.close(fd)
    if not found:
        print("Khong co thiet bi nao bao trang thai lo cam tai nghe")


def analyze(path):
    print("=== Phan tich", os.path.basename(path))
    if not os.path.exists(path) or os.path.getsize(path) <= 44:
        print("Khong co du lieu ghi am")
        return
    with wave.open(path) as w:
        ch, rate, width, n = w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()
        data = w.readframes(n)
    print("kenh=%d tan so=%d do dai=%.1f giay" % (ch, rate, n / float(rate)))
    if width != 2:
        print("Chi phan tich duoc mau 16-bit")
        return
    samples = array.array("h", data)
    if sys.byteorder == "big":
        samples.byteswap()
    win = rate // 2  # moi 0.5 giay
    for c in range(ch):
        chan = samples[c::ch]
        peaks, rmss = [], []
        for i in range(0, len(chan), win):
            seg = chan[i:i + win]
            if not seg:
                continue
            peaks.append(max(abs(x) for x in seg))
            rmss.append(math.sqrt(sum(x * x for x in seg) / len(seg)))
        print("kenh %d: dinh cao nhat=%d / 32767, RMS tung 0.5s: %s" % (
            c, max(peaks) if peaks else 0, " ".join("%d" % r for r in rmss)))
        if not peaks or max(peaks) == 0:
            verdict = "IM LANG HOAN TOAN (khong co tin hieu)"
        elif max(peaks) < 200:
            verdict = "chi co nhieu rat nho (gan nhu khong co tin hieu)"
        elif max(rmss) > 4 * (min(rmss) + 1):
            verdict = "CO TIN HIEU thay doi theo thoi gian (giong noi?)"
        else:
            verdict = "co tin hieu deu (nhieu nen?)"
        print("  -> " + verdict)


if __name__ == "__main__":
    jack_switches()
    for f in sys.argv[1:]:
        analyze(f)
