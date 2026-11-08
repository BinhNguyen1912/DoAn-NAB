"""Test phiên phát trực tiếp (`src/api/live.py` + endpoint `/api/live/*`).

Dùng nguồn frame GIẢ (không cần webcam/OpenCV). Chỉ 1 test dùng adapter OpenCV thật.
"""

import time

import pytest

from src.api.domain import LiveState, SourceUnavailable


def _wait(predicate, timeout=3.0):
    """Chờ có điều kiện (thread live chạy nền) — luôn có hạn để test không treo."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestLiveStreamService:
    def test_ban_dau_chua_phat(self, live_service):
        status = live_service.status()
        assert status.state is LiveState.STOPPED
        assert live_service.latest_jpeg() is None

    def test_start_phat_duoc_frame_va_do_duoc_fps(self, live_service, make_frame_source):
        status = live_service.start("0")

        assert status.state is LiveState.RUNNING
        assert status.source == "giả:0"
        assert _wait(lambda: live_service.status().frames >= 3)
        assert live_service.latest_jpeg().startswith(b"\xff\xd8fake-frame")
        assert live_service.status().measured_fps > 0

    def test_nguon_co_telemetry_thi_status_phoi_so_lieu(self, live_service, monkeypatch):
        """Nguồn là LiveTelemetrySource (worker) ⇒ status có mask_fps/stability/latency_ms."""
        from src.api.domain import LiveTelemetry

        from tests.conftest import FakeFrameSource

        class _TelemetrySource(FakeFrameSource):
            def telemetry(self):
                return LiveTelemetry(mask_fps=8.6, stability=0.96, latency_ms=108.0, lk_ms=4.6)

        monkeypatch.setattr(live_service, "_make_source", lambda *a, **k: _TelemetrySource("0"))
        live_service.start("0")
        status = live_service.status()
        assert (status.mask_fps, status.stability, status.latency_ms) == (8.6, 0.96, 108.0)
        live_service.stop()

    def test_nguon_khong_co_telemetry_thi_so_lieu_bang_0(self, live_service, make_frame_source):
        live_service.start("0")     # FakeFrameSource: chỉ có frame, không có số liệu chi tiết
        status = live_service.status()
        assert (status.mask_fps, status.stability) == (0.0, 0.0)
        live_service.stop()

    def test_stop_dong_nguon_va_xoa_frame(self, live_service, make_frame_source):
        live_service.start("0")
        source = make_frame_source.created[-1]

        status = live_service.stop()
        assert status.state is LiveState.STOPPED
        assert source.stopped is True
        assert live_service.latest_jpeg() is None

    def test_start_lan_hai_dong_nguon_cu(self, live_service, make_frame_source):
        live_service.start("nguon-1")
        first = make_frame_source.created[0]
        live_service.start("nguon-2")

        assert first.stopped is True
        assert live_service.status().source == "giả:nguon-2"

    def test_nguon_loi_nem_source_unavailable_va_o_error(self, failing_source):
        from src.api.live import LiveStreamService

        service = LiveStreamService(failing_source, target_fps=50)
        with pytest.raises(SourceUnavailable, match="nguồn đang bận"):
            service.start("0")

        status = service.status()
        assert status.state is LiveState.ERROR
        assert "nguồn đang bận" in status.message

    def test_luong_frames_ket_thuc_khi_stop(self, live_service):
        """Generator MJPEG phải có đường thoát — không thì thread server treo."""
        live_service.start("0")
        stream = live_service.frames(idle_timeout=0.3)
        first = next(stream)
        assert first.startswith(b"--frame\r\nContent-Type: image/jpeg")
        assert b"\xff\xd8fake-frame" in first

        live_service.stop()
        with pytest.raises(StopIteration):
            next(stream)

    def test_luong_frames_sinh_ra_part_dung_dinh_dang_mjpeg(self, live_service):
        live_service.start("0")
        part = next(live_service.frames(idle_timeout=0.3))

        header, _, payload = part.partition(b"\r\n\r\n")
        assert header.startswith(b"--frame\r\nContent-Type: image/jpeg")
        # Content-Length phải khớp độ dài THẬT của ảnh — lệch là trình duyệt treo
        declared = int(header.split(b"Content-Length: ")[1].split(b"\r\n")[0])
        assert declared == len(payload[:-2])            # payload kết thúc bằng CRLF
        assert payload[:2] == b"\xff\xd8"
        live_service.stop()


class TestLiveRoutes:
    def test_start_status_frame_stop(self, live_client):
        r = live_client.post("/api/live/start", json={"source": "0"})
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "running"
        assert body["source"] == "giả:0"
        assert set(body) == {"state", "source", "frames", "measured_fps", "mask_fps",
                             "stability", "latency_ms", "message"}

        assert _wait(lambda: live_client.get("/api/live/status").json()["frames"] >= 2)
        assert live_client.get("/api/live/status").json()["state"] == "running"

        frame = live_client.get("/api/live/frame")
        assert frame.status_code == 200
        assert frame.headers["content-type"] == "image/jpeg"
        assert frame.content[:2] == b"\xff\xd8"

        stopped = live_client.post("/api/live/stop").json()
        assert stopped["state"] == "stopped"

    def test_chua_bat_thi_frame_va_stream_tra_loi_ro_rang(self, live_client):
        assert live_client.get("/api/live/frame").status_code == 404
        assert live_client.get("/api/live/stream").status_code == 409

    def test_stream_tra_multipart_mjpeg(self, live_client, monkeypatch):
        """Chỉ kiểm HEADER của route stream.

        Lưu ý (bug CI 08-11): luồng MJPEG **vô hạn** qua `TestClient` treo trên CI (starlette/httpx
        đệm body tới khi generator kết thúc) ⇒ timeout 120 s. Vì vậy ở đây thay generator của
        service bằng bản **chỉ phát 1 part rồi kết thúc**: vẫn kiểm đủ route + HTTP + định dạng
        part, mà test luôn kết thúc được. Định dạng part đầy đủ đã kiểm ở tầng service
        (`test_luong_frames_sinh_ra_part_dung_dinh_dang_mjpeg`).
        """
        live_client.post("/api/live/start", json={"source": "0"})
        assert _wait(lambda: live_client.get("/api/live/status").json()["frames"] >= 1)

        part = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 2\r\n\r\n\xff\xd8\r\n"
        service = live_client.app.state.live
        monkeypatch.setattr(service, "frames", lambda **kwargs: iter([part]))

        with live_client.stream("GET", "/api/live/stream") as response:
            assert response.status_code == 200
            assert "multipart/x-mixed-replace" in response.headers["content-type"]
            assert next(response.iter_raw()).startswith(b"--frame")

        live_client.post("/api/live/stop")

    def test_vos_every_duoc_truyen_xuong_nha_may_nguon(self, live_client, monkeypatch):
        """Phase 4c: `vos_every` phải đi từ JSON request → service → nhà máy nguồn (worker)."""
        seen = {}

        def spy(source, mode="raw", bbox=None, image_size=None, vos_every=None,
                mask_smoothing=None):
            from tests.conftest import FakeFrameSource

            seen.update(mode=mode, image_size=image_size, vos_every=vos_every,
                        mask_smoothing=mask_smoothing)
            return FakeFrameSource(source)

        monkeypatch.setattr(live_client.app.state.live, "_make_source", spy)
        r = live_client.post("/api/live/start",
                             json={"source": "0", "mode": "track", "vos_every": 6})
        assert r.status_code == 200
        assert seen == {"mode": "track", "image_size": None, "vos_every": 6,
                        "mask_smoothing": None}
        live_client.post("/api/live/stop")

    @pytest.mark.parametrize("bad", [0, 31, "ba"])
    def test_vos_every_ngoai_khoang_tra_422(self, live_client, bad):
        r = live_client.post("/api/live/start", json={"source": "0", "vos_every": bad})
        assert r.status_code == 422

    def test_nguon_sai_tra_400(self, live_client, monkeypatch, failing_source):
        monkeypatch.setattr(live_client.app.state.live, "_make_source",
                            lambda *args, **kwargs: failing_source("0"))

        r = live_client.post("/api/live/start", json={"source": "0"})
        assert r.status_code == 400
        assert "đang bận" in r.json()["detail"]


class TestOpenCvFrameSource:
    """Adapter thật: đọc video file và LẶP LẠI (để demo live không cần webcam)."""

    def test_doc_file_video_va_lap_lai(self, write_video, tmp_path):
        import numpy as np

        from src.api.adapters import OpenCvFrameSource

        frames = np.full((4, 48, 64, 3), 100, np.uint8)
        video = write_video(tmp_path / "v.mp4", frames, fps=10)

        source = OpenCvFrameSource(str(video))
        source.start()
        try:
            first = source.read_jpeg()
            assert first is not None and first[:2] == b"\xff\xd8"
            # đọc nhiều hơn số frame của file → phải lặp lại, không trả None
            for _ in range(9):
                assert source.read_jpeg() is not None
        finally:
            source.stop()

    def test_nguon_khong_ton_tai_nem_loi(self, tmp_path):
        from src.api.adapters import OpenCvFrameSource

        source = OpenCvFrameSource(str(tmp_path / "khong-co.mp4"))
        with pytest.raises(Exception):
            source.start()
