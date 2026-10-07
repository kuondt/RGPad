#!/bin/sh
# HELP: Kiem tra micro tai nghe 3.5mm. Cam tai nghe co mic, mo app roi noi lien tuc khoang 15 giay.
# ICON: app

DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DIR/mic_report.txt"
rm -f "$DIR/mic_test.wav" "$DIR/mic_test_hw.wav"

{
	echo "=== Thoi gian: $(date)"
	echo "=== uname"; uname -a
	echo "=== /proc/asound/cards"; cat /proc/asound/cards
	echo "=== /proc/asound/devices"; cat /proc/asound/devices
	echo "=== /proc/asound/pcm"; cat /proc/asound/pcm
	echo "=== luong thu am (capture)"; ls -d /proc/asound/card*/pcm*c 2>&1
	for f in /proc/asound/card*/pcm*c/info; do [ -e "$f" ] && { echo "--- $f"; cat "$f"; }; done
	echo "=== /proc/bus/input/devices"; cat /proc/bus/input/devices
	echo "=== extcon / switch"
	for f in /sys/class/extcon/*/name /sys/class/extcon/*/state /sys/class/switch/*/name /sys/class/switch/*/state; do
		[ -e "$f" ] && echo "$f: $(cat "$f")"
	done
	echo "=== cong cu"
	for t in arecord aplay amixer alsactl; do echo "$t: $(command -v $t)"; done
	echo "=== amixer scontrols"; amixer scontrols 2>&1
	echo "=== amixer contents"; amixer contents 2>&1 | head -400
	echo "=== dmesg (am thanh / lo cam / mic)"
	dmesg 2>/dev/null | grep -i -E "jack|mic|headset|codec|audio|sound|snd" | tail -80
} >"$OUT" 2>&1

# ghi am thu (chi doc, khong doi cai dat am luong)
if command -v arecord >/dev/null 2>&1; then
	{
		echo "=== arecord -l"; arecord -l
		echo "=== ghi am 8 giay tu thiet bi mac dinh"
		arecord -d 8 -f S16_LE -r 16000 -c 1 "$DIR/mic_test.wav"; echo "ket thuc: $?"
		echo "=== ghi am 5 giay tu hw:0,0 (stereo 48kHz)"
		arecord -D hw:0,0 -d 5 -f S16_LE -r 48000 -c 2 "$DIR/mic_test_hw.wav"; echo "ket thuc: $?"
	} >>"$OUT" 2>&1
else
	echo "=== khong co arecord tren may" >>"$OUT"
fi

PY="$(command -v python3 || command -v python)"
[ -n "$PY" ] && "$PY" "$DIR/mic_check.py" "$DIR/mic_test.wav" "$DIR/mic_test_hw.wav" >>"$OUT" 2>&1
echo "=== XONG" >>"$OUT"
