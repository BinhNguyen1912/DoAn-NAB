"""
Relay camera Windows → WSL qua HTTP MJPEG (dùng khi usbipd kẹt "Device busy (exported)").

Vì sao có file này: USB/IP (usbipd) chuyển webcam nguyên thiết bị vào WSL, nhưng khi driver kẹt
trạng thái "exported" thì không attach được nữa (phải reboot đúng thứ tự). Cách khác rẻ hơn:
để **Windows** mở webcam rồi phát thành luồng MJPEG — WSL đọc như một "camera IP":

    (Windows) python scripts/win_camera_relay.py --port 8090
    (WSL)     ./run view http://172.19.176.1:8090/video

Chức năng:
    GET /             → trang HTML xem nhanh (tiện kiểm tra bằng trình duyệt)
    GET /video        → luồng MJPEG (dùng cho OpenCV/VideoSource — đúng định dạng "camera IP")
    GET /snapshot.jpg → 1 khung JPEG (kiểm tra nhanh bằng curl)
    GET /info         → JSON: kích thước, fps phát (trung bình 1 s), camera index

Input  : --camera (chỉ số webcam Windows, mặc định 0), --port (mặc định 8090), --fps, --width/--height.
Output : log ra stdout; luồng MJPEG cho client.
Lưu ý  : chạy bằng **python của Windows** (không phải python trong WSL). Cần `pip install opencv-python`.
         Chỉ đọc camera, không ghi đĩa, không gửi dữ liệu ra ngoài máy.
         Mở camera bằng DirectShow (CAP_DSHOW) vì MSMF của OpenCV hay chậm 2–3 s ở khung đầu.
"""
import argparse
import json
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

# Console Windows mặc định cp1252 → in chữ Việt sẽ UnicodeEncodeError và chết cả relay.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

_LOCK = threading.Lock()
_LATEST = {"jpeg": None, "w": 0, "h": 0, "fps": 0.0, "t": 0.0}

# Cửa sổ lấy fps trong `/info`. Một chu kỳ đơn lẻ là số **nhiễu**: nó có thể vượt trần `--fps`
# (khi vòng trước chậm hơn vòng này) và bằng ~0 ngay sau một lần camera hỏng. Đo 13-11-2026:
# `/info` báo 21,3 FPS trong khi `--fps 20`, còn sau một lần `read()` fail thì mẫu kế tiếp méo hẳn.
_FPS_WINDOW_S = 1.0


def _fps_smoothed(stamps) -> float:
    """FPS trung bình trong `_FPS_WINDOW_S` gần nhất — 0.0 khi chưa đủ 2 mốc."""
    if len(stamps) < 2:
        return 0.0
    dt = stamps[-1] - stamps[0]
    return (len(stamps) - 1) / dt if dt > 0 else 0.0

_HTML = """<!doctype html><meta charset=utf-8><title>Camera relay</title>
<body style="background:#111;color:#eee;font-family:sans-serif;text-align:center">
<h3>Camera relay (Windows → WSL)</h3>
<img src="/video" style="max-width:95vw;border:2px solid #444">
<p>Luồng cho WSL: <code>http://HOST_IP:%(port)d/video</code></p></body>"""


def _reader(cam_index: int, fps: float, width: int, height: int, stop: threading.Event):
    """Vòng đọc camera → luôn giữ khung MỚI NHẤT (client chậm không làm trễ camera)."""
    cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
    if width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not cap.isOpened():
        print(f"[relay] KHÔNG mở được camera {cam_index}. Thử --camera 1, hoặc đóng app đang dùng cam.")
        stop.set()
        return
    interval = 1.0 / max(1.0, fps)
    stamps: deque = deque()          # mốc thời gian để lấy fps san phằng (xem `_fps_smoothed`)
    print(f"[relay] camera {cam_index} mở OK: {int(cap.get(3))}x{int(cap.get(4))} — bắt đầu phát")
    while not stop.is_set():
        # Mốc ĐẦU vòng: nhịp phải trừ cả thời gian `read()` + `imencode()` vừa tốn.
        # Bug thật 13-11-2026: mốc cũ lấy SAU `imencode` ⇒ `sleep(interval)` mỗi vòng bất kể
        # camera/encode chậm bao nhiêu ⇒ chu kỳ = công việc + interval. Lần đo lúc sửa: camera
        # ~22 FPS (read ≈ 44 ms) + interval 50 ms ⇒ 94 ms ⇒ relay chỉ ra **10,6 FPS**.
        loop_start = time.monotonic()
        ok, frame = cap.read()
        if not ok:
            # Nhịp *thử lại* (không phải nhịp phát): `stop.wait` để tắt ngay, không phải chờ sleep.
            stop.wait(0.05)
            continue
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            # Đường DUY NHẤT không ngủ tới đây — không có `wait` thì lặp vô hạn ăn 100 % CPU.
            stop.wait(0.01)
            continue
        now = time.monotonic()
        stamps.append(now)
        while stamps and now - stamps[0] > _FPS_WINDOW_S:
            stamps.popleft()
        with _LOCK:
            _LATEST.update(jpeg=buf.tobytes(), w=frame.shape[1], h=frame.shape[0],
                           fps=_fps_smoothed(stamps), t=now)
        stop.wait(max(0.0, interval - (time.monotonic() - loop_start)))
    cap.release()
    print("[relay] đã đóng camera")


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    port = 8090

    def log_message(self, *args):        # giữ console sạch để đọc log
        pass

    def do_GET(self):                    # noqa: N802 — tên do http.server quy định
        path = self.path.split("?")[0]
        if path == "/":
            body = (_HTML % {"port": self.port}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/info":
            with _LOCK:
                info = {k: _LATEST[k] for k in ("w", "h", "fps")}
            info.update(camera=self.server.camera_index, serving=True)
            body = json.dumps(info, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/snapshot.jpg":
            jpeg = self._wait_frame(timeout=10.0)
            if jpeg is None:
                self.send_error(503, "no frame yet")   # ASCII: status line HTTP là latin-1
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.end_headers()
            self.wfile.write(jpeg)
        elif path == "/video":
            self._stream()
        else:
            self.send_error(404)

    @staticmethod
    def _wait_frame(timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with _LOCK:
                if _LATEST["jpeg"]:
                    return _LATEST["jpeg"]
            time.sleep(0.02)
        return None

    def _stream(self):
        """MJPEG multipart — đúng định dạng cv2.VideoCapture("http://…/video") đọc được."""
        if self._wait_frame() is None:
            self.send_error(503, "no frame yet")   # ASCII: status line HTTP là latin-1
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while True:
                with _LOCK:
                    jpeg = _LATEST["jpeg"]
                if jpeg is None:
                    time.sleep(0.02)
                    continue
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                 b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n")
                self.wfile.write(jpeg + b"\r\n")
                time.sleep(0.03)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    ap = argparse.ArgumentParser(description="Relay webcam Windows → MJPEG cho WSL")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--fps", type=float, default=20.0)
    ap.add_argument("--width", type=int, default=0)
    ap.add_argument("--height", type=int, default=0)
    args = ap.parse_args()
    # `--fps <= 0` từng bị `max(1.0, fps)` nuốt im lặng thành 1 FPS (review 13-11, P3-2).
    # Cùng hợp đồng với `src/live_tracking.py` (raise thay vì clamp im lặng).
    if args.fps <= 0:
        raise SystemExit("[LOI] --fps phải > 0")

    stop = threading.Event()
    threading.Thread(target=_reader, args=(args.camera, args.fps, args.width, args.height, stop),
                     daemon=True, name="reader").start()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), _Handler)
    server.camera_index = args.camera
    _Handler.port = args.port
    print(f"[relay] nghe http://0.0.0.0:{args.port}/video  (Ctrl+C để dừng)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
