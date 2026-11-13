"""Test hợp đồng HTTP của `scripts/win_camera_relay.py` — KHÔNG cần camera.

Vì sao cần test: relay là đường demo chính khi usbipd kẹt "Device busy (exported)". Nếu định dạng
MJPEG sai thì `cv2.VideoCapture(url)` im lặng trả None → mất cả buổi demo. Test khoá đúng 3 hợp đồng:
`/info` (JSON), `/snapshot.jpg` (JPEG), `/video` (multipart/x-mixed-replace đúng boundary).
"""
import http.client
import json
import threading

import pytest

from scripts import win_camera_relay as relay

# JPEG 1x1 hợp lệ tối thiểu (đủ để test luồng, không cần camera)
_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043000806060706050807070709"
    "090a0c100b0a0b0a0d0d0d0d0f1210101010101010101010101010101010101010101010"
    "10101010101010ffc9000b080001000101011100ffcc000600101005ffda000801010000"
    "3f00d2cf20ffd9"
)


@pytest.fixture
def server():
    """Dựng server thật trên cổng tự do với 1 khung JPEG giả trong bộ đệm."""
    relay._LATEST.update(jpeg=_JPEG, w=640, h=480, fps=20.0, t=0.0)
    httpd = relay.ThreadingHTTPServer(("127.0.0.1", 0), relay._Handler)
    httpd.camera_index = 0
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    relay._LATEST.update(jpeg=None, w=0, h=0, fps=0.0)


def _get(port, path, timeout=5):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp, body


class TestEndpoints:
    def test_info_tra_json_hop_le(self, server):
        resp, body = _get(server, "/info")
        assert resp.status == 200
        data = json.loads(body)
        assert data["w"] == 640 and data["h"] == 480
        assert data["camera"] == 0 and data["serving"] is True

    def test_snapshot_tra_jpeg(self, server):
        resp, body = _get(server, "/snapshot.jpg")
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "image/jpeg"
        assert body[:2] == b"\xff\xd8" and body[-2:] == b"\xff\xd9", "không phải JPEG hợp lệ"

    def test_trang_chu_co_nhuong_dan_luong(self, server):
        resp, body = _get(server, "/")
        assert resp.status == 200
        assert b"/video" in body

    def test_duong_dan_la_tra_404(self, server):
        resp, _body = _get(server, "/khong-ton-tai")
        assert resp.status == 404

    def test_video_dung_dinh_dang_mjpeg(self, server):
        """`/video` phải trả multipart/x-mixed-replace + boundary=frame (cv2 đọc được)."""
        conn = http.client.HTTPConnection("127.0.0.1", server, timeout=5)
        conn.request("GET", "/video")
        resp = conn.getresponse()
        assert resp.status == 200
        ctype = resp.getheader("Content-Type")
        assert ctype.startswith("multipart/x-mixed-replace") and "boundary=frame" in ctype
        head = resp.read(200)
        assert head.startswith(b"--frame")
        assert b"Content-Type: image/jpeg" in head
        conn.close()          # đóng giữa luồng: server phải chịu được (BrokenPipe đã bắt)


class TestKhiChuaCoKhungHinh:
    def test_snapshot_503_khi_camera_chua_san_sang(self):
        relay._LATEST.update(jpeg=None, w=0, h=0, fps=0.0)
        httpd = relay.ThreadingHTTPServer(("127.0.0.1", 0), relay._Handler)
        httpd.camera_index = 0
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            resp, _ = _get(httpd.server_address[1], "/snapshot.jpg", timeout=15)
            assert resp.status == 503, "chưa có khung hình phải báo 503, không được treo client"
        finally:
            httpd.shutdown()
            httpd.server_close()


class TestNhipPhat:
    """Nhịp `--fps` phải tính cả thời gian đọc + nén frame (bug thật 13-11-2026).

    Đo trên máy này: webcam Windows cho 16,6 FPS ở 640x480, nhưng relay chỉ phát **10,6 FPS**
    vì `sleep(interval)` không trừ thời gian `read()`+`imencode()` ⇒ chu kỳ = công việc + interval.
    Test dùng capture GIẢ có `read()` chậm 40 ms: nhịp đúng ⇒ ~20 FPS (camera không phải nút cổ
    chai), nhịp sai ⇒ ~11 FPS. Không cần webcam thật.
    """

    def test_read_cham_khong_lam_tut_nhip(self, monkeypatch):
        import time

        import numpy as np

        class _SlowCap:
            """`read()` tốn 40 ms như webcam thật; frame 16x16 để `imencode` không đáng kể."""

            def __init__(self, *a, **k):
                self.released = False

            def isOpened(self):
                return True

            def get(self, _prop):
                return 640

            def read(self):
                time.sleep(0.04)
                return True, np.full((16, 16, 3), 90, np.uint8)

            def release(self):
                self.released = True

        monkeypatch.setattr(relay.cv2, "VideoCapture", lambda *a, **k: _SlowCap())
        stop = threading.Event()
        thread = threading.Thread(target=relay._reader, args=(0, 20.0, 0, 0, stop), daemon=True)
        thread.start()
        time.sleep(1.0)                       # để nhịp ổn định rồi mới đo
        with relay._LOCK:                     # fps relay tự báo = 1/chu kỳ thật
            do_duoc = relay._LATEST["fps"]
        stop.set()
        thread.join(timeout=5)

        assert not thread.is_alive(), "vòng đọc phải dừng theo stop"
        assert do_duoc > 15.0, (
            f"nhịp chỉ {do_duoc:.1f} FPS — `sleep(interval)` đang không trừ thời gian read()+encode()"
        )
