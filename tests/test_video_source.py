"""Test seam VideoSource — interface thống nhất cho webcam / RTSP / video file.

Chỉ test hành vi công khai qua factory `open_video_source` + adapter (open/read/close/properties).
Số liệu kỳ vọng lấy từ fixture giả lập (nguồn độc lập với code chạy).
"""
import numpy as np
import pytest

from src.synthetic_video import generate_tracking_sequence
from src.video_source import open_video_source


class TestFileAdapter:
    """Seam VideoSource — file adapter đọc đúng số frame/kích thước/dtype (tiêu chí 1)."""

    def test_doc_dung_so_frame_kich_thuoc_dtype_tu_fixture(self, tmp_path, write_video):
        fx = generate_tracking_sequence(num_frames=12, frame_size=(120, 160), square_size=30)
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)

        src = open_video_source(str(path)).open()
        assert src.frame_size == (160, 120)  # (W, H)
        assert src.source_fps == pytest.approx(30)

        frames = []
        while True:
            frame = src.read()
            if frame is None:
                break
            frames.append(frame)
        assert len(frames) == 12
        assert all(f.shape == (120, 160, 3) for f in frames)
        assert all(f.dtype == np.uint8 for f in frames)

        # Sau khi cạn nguồn, read tiếp vẫn None (an toàn khi gọi nhầm lần nữa)
        assert src.read() is None
        src.close()


class TestFactoryDinhTuyenKieuNguon:
    """Yêu cầu 4 của ticket: một interface duy nhất, chọn nguồn qua tham số (lazy — chưa mở)."""

    def test_int_chon_webcam_string_chon_kieu_roi_dinh(self):
        from src.video_source import CameraVideoSource, FileVideoSource, RtspVideoSource

        assert isinstance(open_video_source(0), CameraVideoSource)
        assert isinstance(open_video_source("1"), FileVideoSource)  # chuỗi thường xem là path
        assert isinstance(open_video_source("rtsp://192.168.1.10:554/stream"), RtspVideoSource)


class TestNguonLoi:
    """Yêu cầu 3 của ticket: nguồn lỗi → báo lỗi rõ ràng thay vì treo."""

    def test_file_khong_ton_tai_bao_file_not_found_ro_rang(self, tmp_path):
        src = open_video_source(str(tmp_path / "khong-co.avi"))
        with pytest.raises(FileNotFoundError, match="khong-co.avi"):
            src.open()

    def test_rtsp_khong_ket_noi_duoc_bao_connection_error(self):
        # Port 9 (discard) trên loopback — từ chối kết nối nhanh, không treo lâu
        src = open_video_source("rtsp://127.0.0.1:9/stream", open_timeout_ms=2000)
        with pytest.raises(ConnectionError, match="RTSP"):
            src.open()

    def test_read_truoc_open_bao_loi_ro_rang(self, tmp_path, write_video):
        fx = generate_tracking_sequence(num_frames=2, frame_size=(120, 160), square_size=30)
        src = open_video_source(str(write_video(tmp_path / "seq.avi", fx.frames)))
        with pytest.raises(RuntimeError, match="open()"):
            src.read()

class TestHttpSource:
    """Nguồn MJPEG/HTTP (điện thoại: IP Webcam, DroidCam…).

    Lỗi thật 18-10: `--source http://192.168.x.x:8080/video` bị coi là FILE →
    `FileNotFoundError: Không mở được video file` (thông báo sai đường, dễ gây lạc hướng).
    """

    def test_http_duoc_dinh_tuyen_sang_nguon_mang(self):
        from src.video_source import HttpVideoSource, open_video_source

        src = open_video_source("http://192.168.1.25:8080/video")
        assert isinstance(src, HttpVideoSource)
        assert isinstance(src, __import__("src.video_source", fromlist=["VideoSource"]).VideoSource)

    def test_https_cung_la_nguon_mang(self):
        from src.video_source import HttpVideoSource, open_video_source

        assert isinstance(open_video_source("https://cam.local/video"), HttpVideoSource)

    def test_loi_http_bao_huong_dan_lay_ip_that(self, monkeypatch):
        """Mở thất bại → thông báo nêu: kiểm tra IP thật, cùng Wi-Fi, đúng đường dẫn /video."""
        import cv2

        from src.video_source import open_video_source

        class FakeCap:
            def isOpened(self):
                return False

            def release(self):
                pass

            def set(self, *a, **k):
                return True

        monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: FakeCap())
        src = open_video_source("http://192.168.1.25:8080/video")
        try:
            src.open()
        except ConnectionError as err:
            msg = str(err)
            assert "http://192.168.1.25:8080/video" in msg
            assert "IP" in msg and ("Wi-Fi" in msg or "mạng" in msg)
        else:
            raise AssertionError("phải ném ConnectionError")

    def test_placeholder_bi_canh_bao_som(self, monkeypatch):
        """IP placeholder kiểu 192.168.x.x → báo lỗi nêu rõ 'IP thật' thay vì lỗi DNS thô."""
        import cv2

        from src.video_source import open_video_source

        class FakeCap:
            def isOpened(self):
                return False

            def release(self):
                pass

            def set(self, *a, **k):
                return True

        monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: FakeCap())
        with pytest.raises(ConnectionError, match="IP thật|placeholder"):
            open_video_source("http://192.168.x.x:8080/video").open()

    def test_file_that_su_van_bao_loi_file(self):
        from src.video_source import open_video_source

        with pytest.raises(FileNotFoundError, match="video file"):
            open_video_source("data/khong_ton_tai.mp4").open()


class TestCameraBackend:
    """Webcam trên Linux: OpenCV 5.0 thử backend obsensor trước → MỞ được nhưng KHÔNG có frame.

    Đo thật 18-10 với webcam laptop qua usbipd: `cv2.VideoCapture(0)` (default) → isOpened True,
    read() False; `cv2.VideoCapture(0, CAP_V4L2)` → read OK (640x480). Vì vậy phải ưu tiên V4L2.
    """

    def _fake_capture(self, monkeypatch, opened_backends):
        import cv2

        import src.video_source as vs

        calls = []

        class FakeCap:
            def __init__(self, backend):
                self.backend = backend

            def isOpened(self):
                return self.backend in opened_backends

            def set(self, prop, value):   # adapter ép MJPG khi mở trên Linux
                return True

            def release(self):
                pass

        def fake_capture(index, backend=cv2.CAP_ANY):
            calls.append(backend)
            return FakeCap(backend)

        monkeypatch.setattr(vs.cv2, "VideoCapture", fake_capture)
        return vs, calls

    def test_linux_uu_tien_v4l2(self, monkeypatch):
        import cv2

        vs, calls = self._fake_capture(monkeypatch, opened_backends={cv2.CAP_V4L2})
        monkeypatch.setattr(vs.sys, "platform", "linux")
        cap = vs.CameraVideoSource(0)._create_capture()
        assert calls[0] == cv2.CAP_V4L2          # thử V4L2 trước
        assert cap.backend == cv2.CAP_V4L2

    def test_linux_fallback_khi_v4l2_khong_mo_duoc(self, monkeypatch):
        import cv2

        vs, calls = self._fake_capture(monkeypatch, opened_backends={cv2.CAP_ANY})
        monkeypatch.setattr(vs.sys, "platform", "linux")
        cap = vs.CameraVideoSource(0)._create_capture()
        assert calls == [cv2.CAP_V4L2, cv2.CAP_ANY]
        assert cap.backend == cv2.CAP_ANY

    def test_windows_chi_dung_backend_mac_dinh(self, monkeypatch):
        import cv2

        vs, calls = self._fake_capture(monkeypatch, opened_backends={cv2.CAP_ANY})
        monkeypatch.setattr(vs.sys, "platform", "win32")
        vs.CameraVideoSource(0)._create_capture()
        assert calls == [cv2.CAP_ANY]


class TestCameraFormat:
    """Webcam UVC qua usbipd: KHÔNG set format → isOpened True nhưng read() luôn False.

    Đo thật 18-10 (4 tổ hợp): V4L2 + set FOURCC=MJPG + 640x480 → read OK; không set (kể cả
    chờ 1s hay retry 10 lần) → read False. Vì vậy adapter phải set MJPG khi mở trên Linux.
    """

    def test_linux_set_mjpeg_640x480_khi_mo(self, monkeypatch):
        import cv2

        import src.video_source as vs

        sets = {}

        class FakeCap:
            def isOpened(self):
                return True

            def set(self, prop, value):
                sets[prop] = value
                return True

            def release(self):
                pass

        monkeypatch.setattr(vs.cv2, "VideoCapture", lambda *a, **k: FakeCap())
        monkeypatch.setattr(vs.sys, "platform", "linux")
        vs.CameraVideoSource(0)._create_capture()

        assert sets[cv2.CAP_PROP_FOURCC] == cv2.VideoWriter_fourcc(*"MJPG")
        assert sets[cv2.CAP_PROP_FRAME_WIDTH] == 640
        assert sets[cv2.CAP_PROP_FRAME_HEIGHT] == 480

    def test_windows_khong_ep_format(self, monkeypatch):
        import cv2

        import src.video_source as vs

        sets = {}

        class FakeCap:
            def isOpened(self):
                return True

            def set(self, prop, value):
                sets[prop] = value
                return True

            def release(self):
                pass

        monkeypatch.setattr(vs.cv2, "VideoCapture", lambda *a, **k: FakeCap())
        monkeypatch.setattr(vs.sys, "platform", "win32")
        vs.CameraVideoSource(0)._create_capture()
        # Windows tự thương lượng format (không ép FOURCC/kích thước), nhưng vẫn ép đệm 1 frame
        assert cv2.CAP_PROP_FOURCC not in sets
        assert cv2.CAP_PROP_BUFFERSIZE in sets


class TestCameraBuffer:
    """Driver V4L2 mặc định đệm 4 frame (đo thật 18-10) → sau mỗi lần suy luận 0.5-3s,
    hàng đợi chứa toàn frame cũ nên người dùng thấy "di chuyển rồi lâu mới hiện".
    Adapter phải ép đệm = 1 frame để luôn đọc frame mới nhất.
    """

    def test_ep_buffer_bang_1(self, monkeypatch):
        import cv2

        import src.video_source as vs

        sets = {}

        class FakeCap:
            def isOpened(self):
                return True

            def set(self, prop, value):
                sets[prop] = value
                return True

            def release(self):
                pass

        monkeypatch.setattr(vs.cv2, "VideoCapture", lambda *a, **k: FakeCap())
        monkeypatch.setattr(vs.sys, "platform", "linux")
        vs.CameraVideoSource(0)._create_capture()
        assert sets[cv2.CAP_PROP_BUFFERSIZE] == 1


class TestHttpSnapshotSource:
    """Nguồn ảnh JPEG rời (`/snapshot.jpg`) — thay MJPEG để giảm chi phí decode.

    Vì sao có: 05-11-2026 đo trên relay camera của repo → `cv2.VideoCapture` (MJPEG)
    tốn 30,2 ms/frame, còn hỏi từng ảnh + `cv2.imdecode` chỉ 8,4 ms/frame.
    """

    URL = "http://192.168.1.25:8090/snapshot.jpg"

    def test_url_snapshot_duoc_dinh_tuyen_sang_nguon_anh_roi(self):
        from src.video_source import HttpSnapshotSource, open_video_source

        assert isinstance(open_video_source(self.URL), HttpSnapshotSource)
        assert isinstance(open_video_source("http://cam.local/snapshot"), HttpSnapshotSource)
        # `/video` vẫn là MJPEG (hành vi cũ không đổi)
        from src.video_source import HttpVideoSource

        assert isinstance(open_video_source("http://cam.local/video"), HttpVideoSource)

    def test_open_loi_bao_duong_dan_anh_jpeg(self, monkeypatch):
        import src.video_source as vs

        monkeypatch.setattr(vs.HttpSnapshotSource, "_fetch", lambda self, attempts=1: None)
        with pytest.raises(ConnectionError) as err:
            vs.HttpSnapshotSource(self.URL).open()
        assert "snapshot.jpg" in str(err.value)

    def test_read_giai_ma_jpeg_that(self, monkeypatch):
        import cv2

        import src.video_source as vs

        ok, buf = cv2.imencode(".jpg", np.full((48, 64, 3), 90, dtype=np.uint8))
        assert ok
        payload = buf.tobytes()

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return payload

        monkeypatch.setattr(vs.urllib.request, "urlopen", lambda *a, **k: FakeResp())
        src = vs.HttpSnapshotSource(self.URL).open()
        assert src.frame_size == (64, 48)
        frame = src.read()
        assert frame.shape == (48, 64, 3)

    def test_loi_tam_thoi_tra_frame_cu_va_het_nguon_sau_nhieu_lan_hong(self, monkeypatch):
        """Nguồn live không được chết vì mạng chập chờn: giữ frame cuối, chỉ kết thúc sau
        `max_misses` lần hỏng liên tiếp."""
        import cv2

        import src.video_source as vs

        ok, buf = cv2.imencode(".jpg", np.full((8, 8, 3), 10, dtype=np.uint8))
        payload = buf.tobytes()
        calls = {"n": 0}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                calls["n"] += 1
                if calls["n"] > 1:
                    raise OSError("mất mạng")
                return payload

        monkeypatch.setattr(vs.urllib.request, "urlopen", lambda *a, **k: FakeResp())
        src = vs.HttpSnapshotSource(self.URL, max_misses=3).open()
        assert src.read() is not None          # lần 1 OK, sau đó hỏng → trả frame cũ
        assert src.read() is not None
        assert src.read() is None              # đủ 3 lần hỏng liên tiếp → hết nguồn
