#!/bin/sh
# HELP: Bien RG40XXV thanh tay cam Xbox khong day cho PC Windows. Bam MENU + START de thoat.
# ICON: app

APPDIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$APPDIR/rgpad.log"
cd "$APPDIR" || exit 1

# PySDL2 va font cho giao dien lay tu PortMaster
for PM in /mnt/mmc/MUOS/PortMaster /opt/muos/PortMaster /opt/system/Tools/PortMaster /opt/tools/PortMaster /roms/ports/PortMaster; do
	if [ -d "$PM/exlibs/sdl2" ]; then
		export PYTHONPATH="$PM/exlibs:$PYTHONPATH"
		export RGPAD_FONT="$PM/pylibs/resources/DejaVuSans.ttf"
		break
	fi
done

# tat moi ban RGPad con chay (RGPad-Nen, ban cu chua thoat): 2 ban cung gui se lam nut nhap nhay
pkill -f rgpad_client.py 2>/dev/null && sleep 0.5
rm -f /tmp/rgpad.pid

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
	echo "Khong tim thay python3 tren may" >"$LOG"
	exit 1
fi

"$PY" -u "$APPDIR/rgpad_client.py" >"$LOG" 2>&1
