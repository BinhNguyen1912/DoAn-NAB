#!/usr/bin/env bash
# Relay webcam Windows → WSL qua HTTP MJPEG — dùng khi usbipd kẹt "Device busy (exported)".
#
#   scripts/cam_relay.sh start   # bật relay trên Windows (nếu chưa chạy), chờ tới khi có khung hình
#   scripts/cam_relay.sh url     # in URL luồng MJPEG để đưa cho tools/run_live.py
#   scripts/cam_relay.sh status  # relay có sống không + độ phân giải/fps
#   scripts/cam_relay.sh stop    # tắt relay (Windows python của venv wincam)
#
# Vì sao có: USB/IP cần driver Windows nhả thiết bị; khi driver kẹt trạng thái "exported" thì phải
# reboot đúng thứ tự. Relay chỉ cần Windows mở webcam rồi phát HTTP — WSL đọc y như "camera IP"
# (đúng tinh thần yêu cầu "Camera USB/IP" của đề cương: nhánh IP).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${CAM_RELAY_PORT:-8090}"
# IP của Windows host trong WSL2 NAT = gateway mặc định của WSL
HOST_IP="${CAM_RELAY_HOST:-$(ip route show default 2>/dev/null | awk '{print $3; exit}')}"
URL="http://${HOST_IP}:${PORT}/video"
# Ảnh JPEG rời: pipeline đọc cái này rẻ hơn MJPEG ~22 ms/frame (đo 05-11-2026:
# `cv2.VideoCapture` trên /video = 30,2 ms/frame vs imdecode /snapshot.jpg = 8,4 ms).
SNAP_URL="http://${HOST_IP}:${PORT}/snapshot.jpg"
WIN_PY_WIN='%LOCALAPPDATA%\wincam-venv\Scripts\python.exe'
SCRIPT_WIN='D:\DOAN-NAB\scripts\win_camera_relay.py'

_ps() { powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$1"; }

# Server sống (đã bind port, /info trả lời) — CHƯA chắc đã có khung hình.
alive() { curl -s -m 3 "http://${HOST_IP}:${PORT}/info" 2>/dev/null | grep -q '"serving"'; }

# Có khung hình THẬT (camera mở được và đã đọc ≥ 1 frame ⇒ "w" > 0).
# Vì sao cần: relay có thể sống mà camera bị app Windows khác giữ → /video rỗng, demo đen thui.
# Đo 05-11-2026: ngay sau khi bật, /info trả {"w": 0, "h": 0, "fps": 0.0, "serving": true}.
streaming() { curl -s -m 3 "http://${HOST_IP}:${PORT}/info" 2>/dev/null | grep -Eq '"w":[[:space:]]*[1-9]'; }

case "${1:-url}" in
  url)
    echo "$URL"
    ;;
  snapurl)
    echo "$SNAP_URL"
    ;;
  status)
    if alive && streaming; then
      echo "[relay] ĐANG CHẠY — $(curl -s -m 3 "http://${HOST_IP}:${PORT}/info")"
      echo "[relay] URL: $URL"
    elif alive; then
      echo "[relay] server sống nhưng CHƯA có khung hình — $(curl -s -m 3 "http://${HOST_IP}:${PORT}/info")"
      echo "[relay] thường là camera bị app Windows khác giữ (Zalo/Discord/Chrome). Thử:"
      echo "        ./run relay stop && ./run relay start"
      exit 1
    else
      echo "[relay] chưa chạy (bật bằng: ./run relay)"
      exit 1
    fi
    ;;
  start)
    if alive; then
      if streaming; then
        echo "[relay] đã chạy sẵn: $URL"
        exit 0
      fi
      echo "[relay] server đã chạy nhưng CHƯA có khung hình (camera bị app khác giữ?). Bật lại:"
      echo "        ./run relay stop && ./run relay start"
      exit 1
    fi
    if [ -z "$HOST_IP" ]; then
      echo "[LOI] không dò được IP Windows host (chạy lệnh này trong WSL)."
      exit 1
    fi
    if ! _ps "Test-Path \$env:LOCALAPPDATA\wincam-venv\Scripts\python.exe" 2>/dev/null | grep -qi true; then
      echo "[relay] chưa có môi trường Windows (venv + opencv)."
      echo "        Chạy 1 lần trong PowerShell:"
      echo "        powershell -ExecutionPolicy Bypass -File D:\\DOAN-NAB\\tools\\setup_cam_relay.ps1"
      exit 1
    fi
    echo "[relay] bật camera relay trên Windows (port ${PORT})…"
    # Màn hình Windows có thể hiện hộp thoại Firewall lần đầu → chọn Allow
    # Vì sao KHÔNG dùng Start-Process: `Start-Process -RedirectStandardOutput` giữ pipe của
    # powershell → lệnh trong WSL treo vô hạn (đo 04-11: `./run relay start | tail` treo >90 s).
    # Invoke-CimMethod (Win32_Process.Create) trả về ngay (1,3 s) và tiến trình con tách hẳn.
    _ps "Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c D:\\DOAN-NAB\\tools\\start_cam_relay.cmd ${PORT}'} | Out-Null" </dev/null >/dev/null 2>&1
    for _i in $(seq 1 20); do
      sleep 1
      if streaming; then
        echo "[relay] OK: $URL"
        echo "[relay] xem nhanh trong trình duyệt: http://${HOST_IP}:${PORT}/"
        exit 0
      fi
    done
    if alive; then
      echo "[LOI] relay sống nhưng KHÔNG có khung hình sau 20s ⇒ camera đang bị app Windows giữ."
      echo "      Đóng Zalo (ZaloCall/ZaloCap), Discord, Chrome… rồi: ./run relay stop && ./run relay start"
      exit 1
    fi
    echo "[LOI] relay không lên sau 20s. Xem log: data/_relay.log , data/_relay_err.log"
    echo "      Thường gặp: (1) app khác đang giữ camera → đóng Zalo/Discord/Chrome;"
    echo "                  (2) Firewall chặn → bấm Allow ở hộp thoại, hoặc thêm rule port ${PORT}."
    exit 1
    ;;
  stop)
    _ps "Get-Process python -ErrorAction SilentlyContinue | Where-Object {\$_.Path -like '*wincam-venv*'} | Stop-Process -Force" >/dev/null 2>&1
    echo "[relay] đã tắt."
    ;;
  *)
    echo "Dùng: scripts/cam_relay.sh {start|url|snapurl|status|stop}"
    exit 2
    ;;
esac
