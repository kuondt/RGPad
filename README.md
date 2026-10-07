# RGPad

Biến máy **Anbernic RG40XXV (muOS)** thành tay cầm không dây cho **PC Windows**: tay cầm Xbox 360 ảo,
chuột, bàn phím ảo và macro, điều khiển qua WiFi. Làm ra để chơi Genshin Impact nhưng dùng được cho
mọi game nhận tay cầm Xbox.

```
RG40XXV (muOS)                        WiFi / UDP                PC Windows
muos/RGPad  (giao diện trên máy)  ───────────────────────►  pc/rgpad_web.py  ──► tay cầm Xbox ảo (ViGEmBus)
  • đọc nút bấm (evdev)            ◄─── xác nhận, trạng thái ──  • chuột / bàn phím Windows (SendInput)
  • bàn phím ảo, chế độ chuột                                    • macro
                                                                 • trang điều khiển http://127.0.0.1:8740
```

## Tính năng
- **Tay cầm Xbox ảo**: game nhận như tay cầm thật. Nút gán theo **chữ in trên máy** (A = A, B = B…).
- **Xoay camera bằng 1 cần**: giữ MENU + cần analog = cần phải; hoặc bật chế độ D-pad = camera.
- **Chế độ chuột** (MENU + Y): D-pad / cần di chuột, A/B/X = chuột trái/phải/giữa, L1/R1 cuộn.
- **Bàn phím ảo** (MENU + X): gõ phím vào Windows bằng mã phím thật (dùng được với Unikey).
- **Macro** (MENU + A / B): spam một nút hoặc combo, nghỉ cố định hoặc ngẫu nhiên, quản lý trên web.
- **Trang điều khiển web (React)** trên PC: trạng thái, sơ đồ tay cầm trực tiếp, macro, nhật ký.
- Gửi phím có xác nhận (không mất, không gõ đúp), chỉ nhận từ một bản RGPad (tránh nút nhấp nháy).

## Cài đặt trên PC Windows
1. Cài **Python 3** (tick "Add python.exe to PATH").
2. Chạy **`pc/start_server.bat`**. Lần đầu nó tự cài thư viện `vgamepad` và có thể hiện trình cài
   **ViGEmBus** (driver tay cầm ảo), cứ bấm cài. Nếu không thấy: https://github.com/nefarius/ViGEmBus/releases
3. Khi Windows Firewall hỏi, cho Python truy cập mạng. Nên đặt mạng WiFi của PC là **Private**.
4. Trang điều khiển tự mở tại **http://127.0.0.1:8740**. Cửa sổ cmd chính là RGPad: **đóng cửa sổ = tắt**.

Game chạy bằng quyền Administrator (như Genshin) thì muốn **chuột / bàn phím ảo** tác động vào game phải
chạy `start_server.bat` bằng **Run as administrator**. Tay cầm ảo không cần.

Tuỳ chọn: `python pc/rgpad_web.py --dry` chạy thử không tạo tay cầm ảo; `python pc/rgpad_server.py`
là bản dòng lệnh không có giao diện web.

Sửa giao diện web: `cd pc/web && npm install && npm run build` (thư mục `pc/web/dist` đã build sẵn).

## Cài đặt trên RG40XXV (muOS)
1. Kết nối WiFi cùng mạng với PC.
2. Chép thư mục `muos/RGPad` (và `muos/RGPad-Nen` nếu dùng cùng Moonlight) vào thẻ nhớ:
   `/mnt/mmc/MUOS/application/`. Có thể chép qua trang quản lý file của muOS (Web Services, cổng 9090).
3. Mở **Applications → RGPad**. App tự tìm PC trong mạng LAN.
   Không tìm được thì điền IP của PC vào `"pc_ip"` trong `muos/RGPad/config.json`.
4. Nhật ký: `RGPad/rgpad.log`. Giao diện dùng PySDL2 và font có sẵn trong PortMaster.

## Cách bấm
| Nút trên máy | Tác dụng |
|---|---|
| Cần analog | Cần trái Xbox (di chuyển) |
| A / B / X / Y | A / B / X / Y |
| L1 / L2 / R1 / R2 | LB / LT / RB / RT |
| SELECT / START | Back / Start |
| **Giữ MENU + cần analog** | Cần phải (xoay camera, ngắm) |
| MENU + L1 / R1 | L3 / R3 |
| MENU + SELECT | Bật/tắt D-pad = camera |
| **MENU + Y** | Chế độ chuột ↔ tay cầm |
| **MENU + X** | Mở/đóng bàn phím ảo |
| **MENU + A / MENU + B** | Chạy/dừng macro đang chọn / đổi macro |
| **MENU + START** | Thoát app |

**Chế độ chuột:** D-pad (giữ lâu chạy nhanh dần) hoặc cần analog di chuột · A/B/X = chuột trái/phải/giữa
(giữ A để kéo) · L1/R1 cuộn · giữ L2 di chậm · START = Enter · SELECT = Esc ·
giữ MENU thì D-pad tạm làm D-pad tay cầm (điều khiển menu game).

**Bàn phím ảo:** D-pad / cần chọn phím · A gõ · B xoá · Y dấu cách · X Shift · L2 Ctrl · START Enter ·
SELECT Esc · L1/R1 ← →.

## Macro
Quản lý ở mục **Macro** trên trang web. Mỗi macro gồm nhiều bước chạy nối tiếp; mỗi bước giữ một hoặc
nhiều nút (bấm cùng lúc) trong *x* ms rồi nghỉ một khoảng **cố định** hoặc **ngẫu nhiên** (từ–đến).
Lặp *n* vòng hoặc tới khi dừng. Nút của macro được cộng thêm vào nút bạn đang bấm.
Lưu trong `pc/macros.json`.

> Điều khoản của nhiều game (trong đó có Genshin Impact) cấm tự động hoá lối chơi. Dùng macro là rủi ro
> của chính bạn.

## Stream màn hình PC lên máy (Sunshine + Moonlight)
1. PC: cài [Sunshine](https://github.com/LizardByte/Sunshine/releases), mở `https://localhost:47990`.
2. Máy: cài **Moonlight** qua PortMaster, ghép nối bằng mã PIN (nhập PIN ở tab PIN của Sunshine).
3. Stream 480p hoặc 720p, 60 FPS, 8–10 Mbps (màn máy chỉ 640x480).
4. Điều khiển: hoặc để Moonlight gửi nút (Sunshine → Input → *Enable Gamepad Input* bật), hoặc tắt mục đó
   và mở **RGPad-Nen** (RGPad chạy nền, không giao diện) trước khi mở Moonlight để có combo MENU.

## Công cụ khác
- `muos/RGPad-MicTest`: kiểm tra micro qua lỗ tai nghe. Kết quả trên RG40XXV: **không có đường thu âm**
  (chip âm thanh chỉ có phát), micro tai nghe 3.5mm không dùng được.
- `python3 rgpad_client.py --test` (qua SSH trên máy): in mã từng nút để chỉnh `config.json` nếu nút sai.

## Cấu trúc
```
muos/RGPad/        app trên máy: rgpad_client.py (nhận nút, gửi UDP), rgpad_ui.py (giao diện SDL2),
                   rgpad_osk.py (bàn phím ảo), config.json (mã nút), mux_launch.sh
muos/RGPad-Nen/    chạy RGPad nền (dùng cùng Moonlight)
pc/rgpad_core.py   lõi: nhận UDP, tay cầm ảo, chuột/bàn phím Windows
pc/rgpad_macro.py  macro
pc/rgpad_web.py    backend web + Server-Sent Events; pc/web: giao diện React (Vite)
pc/start_server.bat chạy RGPad trên PC
```
