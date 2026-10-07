#!/bin/sh
# HELP: Bat/tat RGPad chay nen (dung cung Moonlight). Mo lan 1 = bat, mo lan 2 = tat.
# ICON: app

APPDIR="$(cd "$(dirname "$0")/../RGPad" && pwd)"
LOG="$APPDIR/rgpad.log"
PIDFILE=/tmp/rgpad.pid

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
	kill "$(cat "$PIDFILE")"
	rm -f "$PIDFILE"
	exit 0
fi

# tat ban RGPad cu con chay (neu co) truoc khi bat ban chay nen
pkill -f rgpad_client.py 2>/dev/null && sleep 0.5

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
	echo "Khong tim thay python3 tren may" >"$LOG"
	exit 1
fi

cd "$APPDIR" || exit 1
nohup "$PY" -u "$APPDIR/rgpad_client.py" --no-grab --no-ui >"$LOG" 2>&1 &
echo $! >"$PIDFILE"
