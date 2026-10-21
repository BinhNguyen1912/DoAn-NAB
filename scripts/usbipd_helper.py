"""
Trợ giúp usbipd: tìm BUSID hiện tại của webcam và gắn vào WSL.

Vì sao cần: BUSID của thiết bị USB **đổi sau mỗi lần khởi động lại** (đã gặp: 1-8 → 2-8),
nên lệnh `usbipd attach --busid 1-8` sẽ báo "There is no device with busid". Script này tự
đọc `usbipd list`, tìm dòng camera, rồi attach đúng BUSID mới.

Input  : văn bản `usbipd list` (chuẩn Windows) hoặc gọi trực tiếp qua powershell.exe.
Output : busid + trạng thái; lệnh attach; kiểm tra /dev/video0.
Lưu ý  : `attach` KHÔNG cần quyền Admin (chỉ `bind` mới cần). Phải có một phiên WSL đang chạy.
"""
import argparse
import os
import re
import subprocess
import sys

# Dòng trong `usbipd list`:  "1-8    5986:211c  HD Webcam    Shared (forced)"
_ROW = re.compile(r"^(?P<busid>\d+-\d+)\s+(?P<vidpid>\S+)\s+(?P<device>.+?)\s{2,}(?P<state>\S.*)$")
_CAMERA_WORDS = ("webcam", "camera", "uvc", "video")


def parse_rows(text):
    """Tách `usbipd list` thành list dict {busid, vidpid, device, state}."""
    rows = []
    for raw in text.splitlines():
        line = raw.replace("\r", "").rstrip()
        m = _ROW.match(line)
        if m:
            rows.append({k: v.strip() for k, v in m.groupdict().items()})
    return rows


def find_camera_busid(text, words=_CAMERA_WORDS):
    """BUSID của thiết bị camera đầu tiên trong `usbipd list` (None nếu không thấy)."""
    for row in parse_rows(text):
        name = row["device"].lower()
        if any(w in name for w in words):
            return row["busid"]
    return None


def _usbipd_list():
    """Chạy `usbipd list` trên Windows qua interop (rỗng nếu không có powershell.exe)."""
    try:
        return subprocess.run(["powershell.exe", "-NoProfile", "-Command", "usbipd list"],
                              capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _attach(busid):
    print(f"[cam] usbipd attach --wsl --busid {busid}")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                          f"usbipd attach --wsl --busid {busid}"],
                         capture_output=True, text=True, timeout=60)
    print((out.stdout + out.stderr).strip())
    return out.returncode == 0


def main():
    ap = argparse.ArgumentParser(description="Trợ giúp usbipd cho webcam trong WSL")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("busid", help="in BUSID hiện tại của camera")
    sub.add_parser("status", help="in bảng thiết bị usbipd")
    sub.add_parser("attach", help="tự tìm BUSID rồi attach vào WSL")
    args = ap.parse_args()

    text = _usbipd_list()
    if not text.strip():
        print("[LOI] không chạy được 'usbipd list' — cài usbipd trên Windows: "
              "winget install -e --id dorssel.usbipd-win")
        return 1

    if args.cmd == "status" or args.cmd is None:
        for row in parse_rows(text):
            print(f"  {row['busid']:6} {row['device']:32} {row['state']}")

    busid = find_camera_busid(text)
    if busid is None:
        print("[LOI] không thấy thiết bị camera trong usbipd list (webcam đang tắt/bị vô hiệu?).")
        return 2
    print(f"[cam] camera hiện ở BUSID = {busid}")

    if args.cmd == "busid":
        return 0

    if args.cmd == "attach":
        ok = _attach(busid)
        got = os.path.exists("/dev/video0")
        print(f"[cam] /dev/video0: {'CÓ' if got else 'CHƯA có'}")
        if not got:
            print("[cam] nếu báo 'Device busy (exported)': reset WSL rồi attach lại "
                  "→ (PowerShell) wsl --shutdown → mở Ubuntu → ./run cam attach")
        return 0 if (ok and got) else 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
