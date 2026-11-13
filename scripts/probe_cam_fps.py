"""Đo trần FPS của webcam (Windows hoặc bất kỳ máy có camera) — chạy bằng python CỦA WINDOWS.

Vì sao có file này: con số "camera cho bao nhiêu FPS" được dùng để giải thích vì sao relay/web chỉ
ra được ngần ấy FPS. Trước 13-11-2026 số đó đo bằng script tạm rồi xoá ⇒ không tái lập được
(review độc lập bắt đúng: ADR-0002 + `AGENTS.md` §6 yêu cầu số đo tái tạo được).

Cách chạy (WSL, dùng relay venv của Windows — camera nằm ở Windows):

    powershell.exe -NoProfile -Command "& \\"$env:LOCALAPPDATA\\wincam-venv\\Scripts\\python.exe\\" \\"D:\\doan-nab\\scripts\\probe_cam_fps.py\\""

    (trên Windows, gọi trực tiếp)  %LOCALAPPDATA%\\wincam-venv\\Scripts\\python.exe scripts\\probe_cam_fps.py

Input  : --camera (index, mặc định 0), --seconds (thời gian đo mỗi tổ hợp, mặc định 2.0).
Output : bảng FPS/kích thước/fourcc ra stdout + 1 dòng `json` để chép vào log/artifact.
Lưu ý  : PHẢI đóng các app đang giữ camera (Zalo/Discord/Chrome) và tắt relay (`./run relay stop`)
         trước khi đo, nếu không số đo là của "camera bị chia sẻ".
         Số đo **dao động theo ánh sáng**: webcam tự phơi sáng, phòng tối ⇒ camera tự tụt nhịp.
         Đo 2-3 lần ở cùng điều kiện sáng rồi báo khoảng, đừng trích một con số đẹp nhất.
"""
import argparse
import json
import sys
import time

import cv2

# Console Windows mặc định cp1252 → in chữ Việt sẽ UnicodeEncodeError (gặp thật 13-11 khi chạy probe).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# (tên, fourcc, W, H) — 0/None = không set (giữ mặc định của driver)
_CAU_HINH = [
    ("mặc định (không set gì)", None, 0, 0),
    ("640x480 MJPG", "MJPG", 640, 480),
    ("640x480 YUY2", "YUY2", 640, 480),
    ("1280x720 MJPG", "MJPG", 1280, 720),
]


def do_mot(cam_index: int, fourcc: str | None, w: int, h: int, seconds: float) -> dict | None:
    """Mở camera với một cấu hình, trả FPS đo được (None nếu không mở được)."""
    cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    if w and h:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, 30)
    try:
        if not cap.isOpened():
            return None
        for _ in range(10):                  # 10 frame đầu: driver + tự phơi sáng chưa ổn định
            cap.read()
        t0 = time.time()
        n = 0
        while time.time() - t0 < seconds:
            ok, _frame = cap.read()
            n += 1 if ok else 0
        return {
            "fps": round(n / (time.time() - t0), 1),
            "size": f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
                    f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}",
            "fourcc": int(cap.get(cv2.CAP_PROP_FOURCC)),
        }
    finally:
        cap.release()
        time.sleep(0.5)                      # nhả camera cho cấu hình kế tiếp (DSHOW cần thời gian)


def main() -> int:
    ap = argparse.ArgumentParser(description="Đo trần FPS webcam theo cấu hình (Windows/DSHOW)")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--seconds", type=float, default=2.0)
    args = ap.parse_args()

    ket_qua = {}
    for ten, fourcc, w, h in _CAU_HINH:
        r = do_mot(args.camera, fourcc, w, h, args.seconds)
        ket_qua[ten] = r
        print(f"{ten}: " + (f"{r['fps']} FPS | {r['size']} | fourcc={r['fourcc']}"
                            if r else "KHÔNG mở được"))
    print("json:", json.dumps({"camera": args.camera, "do_luc": time.strftime("%Y-%m-%d %H:%M:%S"),
                               "ket_qua": ket_qua}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
