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
                return LiveTelemetry(display_fps=29.9, mask_fps=8.6, stability=0.96,
                                      latency_ms=108.0, lk_ms=4.6, empty_runs=2)

        monkeypatch.setattr(live_service, "_make_source", lambda *a, **k: _TelemetrySource("0"))
        live_service.start("0")
        status = live_service.status()
        assert (status.display_fps, status.mask_fps, status.stability,
                status.latency_ms, status.empty_runs) == (29.9, 8.6, 0.96, 108.0, 2)
        live_service.stop()

    def test_nguon_khong_co_telemetry_thi_so_lieu_bang_0(self, live_service, make_frame_source):
        live_service.start("0")     # FakeFrameSource: chỉ có frame, không có số liệu chi tiết
        status = live_service.status()
        assert (status.mask_fps, status.empty_runs) == (0.0, 0)
        # Nguồn không báo `stability` ⇒ **chưa đo** (`None`), KHÔNG phải "đo được 0" (ticket 18).
        assert status.stability is None and status.stability_n == 0
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
        assert set(body) == {"state", "source", "frames", "measured_fps", "display_fps",
                             # 4 trường chẩn đoán (09-11): drift + tỉ lệ mất dấu theo cửa sổ
                             "drift_p05", "drift_n", "empty_frac_window", "empty_window_n",
                             "mask_fps", "stability", "stability_n", "latency_ms", "empty_runs",
                             "message"}

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
                             json={"source": "0", "mode": "track", "vos_every": 6,
                                   "mask_smoothing": 0.6})
        assert r.status_code == 200
        assert seen == {"mode": "track", "image_size": None, "vos_every": 6,
                        "mask_smoothing": 0.6}
        live_client.post("/api/live/stop")

    @pytest.mark.parametrize("bad", [0, 31, "ba"])
    def test_vos_every_ngoai_khoang_tra_422(self, live_client, bad):
        r = live_client.post("/api/live/start", json={"source": "0", "vos_every": bad})
        assert r.status_code == 422

    @pytest.mark.parametrize("bad", [0, 0.0, 1.5, "x"])
    def test_mask_smoothing_ngoai_khoang_tra_422(self, live_client, bad):
        """0 không hợp lệ: `MaskSmoother` cần alpha > 0; trước đây schema cho 0 còn worker clamp 0.05."""
        r = live_client.post("/api/live/start", json={"source": "0", "mask_smoothing": bad})
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


class TestOpenCvSourceHealth:
    """Watchdog cho mode `raw` (webcam/RTSP/file): trước 09-11 rút webcam vẫn báo `running`.

    Dùng `capture` GIẢ (monkeypatch `open_video_source`) — không cần webcam thật, và điều khiển được
    chính xác lúc nào nguồn "không trả frame".
    """

    class _Capture:
        """`cv2.VideoCapture` giả: trả lần lượt các frame trong hàng đợi, cạn thì None."""

        def __init__(self, frames=()):
            self.frames = list(frames)
            self.closed = False

        def read(self):
            return self.frames.pop(0) if self.frames else None

        def close(self):
            self.closed = True

    @staticmethod
    def _patch(monkeypatch, *captures):
        """Ghép chuỗi capture: lần `open()` thứ i trả `captures[i]` (đuôi dùng lại cái cuối)."""
        from src.api.adapters import opencv_source

        queue = list(captures)

        class _Opener:
            def open(self):
                if len(queue) > 1:
                    return queue.pop(0)
                return queue[0]

        monkeypatch.setattr(opencv_source, "open_video_source", lambda *a, **k: _Opener())

    @staticmethod
    def _frame():
        import numpy as np

        return np.full((16, 16, 3), 90, np.uint8)

    def test_chua_start_thi_khoe(self):
        from src.api.adapters import OpenCvFrameSource

        assert OpenCvFrameSource("0").health() is None

    def test_dang_ra_frame_thi_khoe(self, monkeypatch):
        from src.api.adapters import OpenCvFrameSource

        capture = self._Capture([self._frame()])
        self._patch(monkeypatch, capture)
        source = OpenCvFrameSource("0")
        source.start()

        assert source.read_jpeg() is not None
        assert source.health() is None

    def test_camera_khong_tra_frame_qua_lau_thi_error(self, monkeypatch):
        """Rút webcam: `read()` trả None mãi ⇒ sau `STALE_S` phải là ERROR (không im lặng)."""
        from src.api.adapters import OpenCvFrameSource, opencv_source

        self._patch(monkeypatch, self._Capture())            # capture rỗng = không có frame
        source = OpenCvFrameSource("0")
        source.start()
        source._got_frame = True                             # đã từng hiện frame ⇒ dùng `STALE_S`
        for _ in range(opencv_source.MISS_MIN):
            assert source.read_jpeg() is None
        source._last_frame_at -= (opencv_source.STALE_S + 1.0)   # tua đồng hồ, không sleep

        health = source.health()
        assert health is not None and health.state is LiveState.ERROR
        assert "không trả frame" in health.message

    def test_mot_lan_truot_chua_du_ket_luan_chet(self, monkeypatch):
        """Read-timeout của nguồn (5 s) LỚN HƠN `STALE_S` ⇒ một lần trượt không được giết phiên khoẻ.

        Đây là P1 của review vòng 2: `age > STALE_S` một mình thì một cú chập mạng duy nhất (hoặc
        `read()` chạm timeout 5 s) đã làm `health()` báo `error`, `_check_health` gọi `stop()` và
        người dùng phải bật lại phiên.
        """
        from src.api.adapters import OpenCvFrameSource, opencv_source

        self._patch(monkeypatch, self._Capture([self._frame()]))
        source = OpenCvFrameSource("0")
        source.start()
        assert source.read_jpeg() is not None                 # đã có frame ⇒ `_got_frame`
        assert source.read_jpeg() is None                     # MỘT lần trượt (misses = 1)
        source._last_frame_at -= (opencv_source.STALE_S + 2.0)

        assert source.health() is None                         # chưa đủ bằng chứng

        # ... rồi nguồn cấp frame trở lại ⇒ vẫn khoẻ và bộ đếm được xoá
        source._capture.frames = [self._frame()]
        assert source.read_jpeg() is not None
        assert source._misses == 0
        assert source.health() is None

    def test_truot_lien_tiep_du_so_lan_thi_error(self, monkeypatch):
        """Trượt `MISS_MIN` lần liên tiếp + quá `STALE_S` ⇒ kết luận chết (không chờ vô hạn)."""
        from src.api.adapters import OpenCvFrameSource, opencv_source

        self._patch(monkeypatch, self._Capture([self._frame()]))
        source = OpenCvFrameSource("0")
        source.start()
        assert source.read_jpeg() is not None
        for _ in range(opencv_source.MISS_MIN - 1):
            assert source.read_jpeg() is None
            source._last_frame_at -= (opencv_source.STALE_S + 1.0)
            assert source.health() is None                  # còn thiếu 1 lần trượt
        assert source.read_jpeg() is None

        health = source.health()
        assert health is not None and health.state is LiveState.ERROR
        assert f"{opencv_source.MISS_MIN} lần liên tiếp" in health.message

    def test_chua_co_frame_nao_thi_dung_an_han_warmup(self, monkeypatch):
        """Camera mới mở nhận frame chậm: dùng `WARMUP_S` cho lần đầu, không phải `STALE_S`."""
        from src.api.adapters import OpenCvFrameSource, opencv_source

        self._patch(monkeypatch, self._Capture())
        source = OpenCvFrameSource("0")
        source.start()
        for _ in range(opencv_source.MISS_MIN):
            assert source.read_jpeg() is None
        source._last_frame_at -= (opencv_source.STALE_S + 1.0)
        assert source.health() is None                          # vẫn trong ân hạn khởi động

        source._last_frame_at -= (opencv_source.WARMUP_S + 1.0)
        health = source.health()
        assert health is not None and health.state is LiveState.ERROR

    def test_file_het_ma_khong_lap_thi_stopped_chu_khong_phai_error(self, monkeypatch):
        """Hết video (file, `loop_files=False`) là phiên KẾT THÚC bình thường — không phải lỗi."""
        from src.api.adapters import OpenCvFrameSource, opencv_source

        self._patch(monkeypatch, self._Capture())
        source = OpenCvFrameSource("video.mp4", loop_files=False)   # đuôi file ⇒ `_is_file`
        source.start()
        source._last_frame_at -= (opencv_source.STALE_S + 5.0)

        assert source.read_jpeg() is None                    # capture rỗng, không lặp
        health = source.health()
        assert health is not None and health.state is LiveState.STOPPED
        assert "hết" in health.message

    def test_da_stop_theo_lenh_thi_khong_bao_loi(self, monkeypatch):
        """`stop()` là chủ động — không được biến thành `error` sau khi đã dừng."""
        from src.api.adapters import OpenCvFrameSource

        self._patch(monkeypatch, self._Capture())
        source = OpenCvFrameSource("0")
        source.start()
        source.stop()

        assert source.health() is None

    def test_thu_muc_anh_het_thi_stopped_va_lap_lai_duoc(self, tmp_path):
        """Chuỗi ảnh (`FramesVideoSource`) là FILE, không phải camera (P2 review 09-11).

        `_looks_like_file` thiếu `is_dir()` ⇒ nguồn bị coi là camera: hết ảnh thì báo `ERROR
        "không trả frame"` (sai — phải là "nguồn đã hết") và `loop_files=True` không lặp lại được.
        """
        import cv2
        import numpy as np

        from src.api.adapters import OpenCvFrameSource

        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        for index in range(2):
            cv2.imwrite(str(frames_dir / f"{index:05d}.jpg"),
                        np.full((16, 16, 3), 90 + index, np.uint8))

        source = OpenCvFrameSource(str(frames_dir))          # loop_files mặc định True
        source.start()
        try:
            for _ in range(5):                              # nhiều hơn số ảnh ⇒ phải lặp lại
                assert source.read_jpeg() is not None
            assert source.health() is None
        finally:
            source.stop()

    def test_thu_muc_anh_het_ma_khong_lap_thi_stopped(self, tmp_path):
        import cv2
        import numpy as np

        from src.api.adapters import OpenCvFrameSource

        frames_dir = tmp_path / "frames2"
        frames_dir.mkdir()
        cv2.imwrite(str(frames_dir / "00000.jpg"), np.full((16, 16, 3), 90, np.uint8))

        source = OpenCvFrameSource(str(frames_dir), loop_files=False)
        source.start()
        try:
            assert source.read_jpeg() is not None
            assert source.read_jpeg() is None               # cạn ảnh, không lặp
            health = source.health()
            assert health is not None and health.state is LiveState.STOPPED
        finally:
            source.stop()

    def test_mo_lai_file_that_bai_thi_error_khong_im_lang(self, monkeypatch):
        """`_rewind()` lỗi (file bị xoá) ⇒ mất capture ⇒ ERROR, không phải 'khoẻ'."""
        from src.api.adapters import OpenCvFrameSource, opencv_source

        calls = {"n": 0}

        class _Opener:
            def open(self):
                calls["n"] += 1
                if calls["n"] > 1:
                    raise OSError("file đã bị xoá")
                return TestOpenCvSourceHealth._Capture()

        monkeypatch.setattr(opencv_source, "open_video_source", lambda *a, **k: _Opener())
        source = OpenCvFrameSource("video.mp4", loop_files=True)
        source.start()
        assert source.read_jpeg() is None          # capture cạn ⇒ thử rewind ⇒ lỗi

        health = source.health()
        assert health is not None and health.state is LiveState.ERROR


class TestWorkerTelemetry:
    """Seam `status.json → LiveTelemetry` — từng làm `empty_runs` "chết trong adapter" (review lần 2)."""

    def test_doc_status_json_thanh_live_telemetry(self, tmp_path):
        import json

        from src.api.adapters.worker_source import WorkerFrameSource

        (tmp_path / "status.json").write_text(json.dumps({
            "state": "tracking", "frames": 400, "measure_fps": 0, "measured_fps": 29.9,
            "vos_fps": 8.6, "vos_ms": 100.0, "lk_ms": 2.7, "stability": 0.963,
            "stability_n": 200, "stability_shown": 0.95, "empty_runs": 14, "mask_holds": 4,
            "mask_drops": 2,
            "bbox": [10, 10, 40, 60], "message": "",
        }), encoding="utf-8")

        detail = WorkerFrameSource("0", out_dir=tmp_path).telemetry()
        assert detail.display_fps == 29.9
        assert detail.mask_fps == 8.6
        assert detail.stability == 0.963
        assert detail.stability_n == 200
        assert detail.latency_ms == 100.0
        assert detail.empty_runs == 14

    def test_seam_stability_none_va_0_0(self, tmp_path):
        """Seam `status.json → LiveTelemetry` phải giữ `None` (chưa đo) — nếu ai đổi
        `_so_hoac_none` thành `float(x or 0.0)` thì bài này đỏ (review 10-11, P2)."""
        import json

        from src.api.adapters.worker_source import WorkerFrameSource

        chua_do = tmp_path / "chua_do"
        chua_do.mkdir()
        (chua_do / "status.json").write_text(json.dumps({
            "state": "tracking", "vos_fps": 8.0, "stability": None, "stability_n": 0,
        }), encoding="utf-8")
        detail = WorkerFrameSource("0", out_dir=chua_do).telemetry()
        assert detail.stability is None, "`None` (chưa đo) không được thành 0,0"
        assert detail.stability_n == 0

        do_duoc = tmp_path / "do_duoc"
        do_duoc.mkdir()
        (do_duoc / "status.json").write_text(json.dumps({
            "state": "tracking", "vos_fps": 8.0, "stability": 0.0, "stability_n": 150,
        }), encoding="utf-8")
        detail = WorkerFrameSource("0", out_dir=do_duoc).telemetry()
        assert detail.stability == 0.0 and detail.stability_n == 150, \
            "0,0 ĐO ĐƯỢC không được biến thành None"

    def test_status_json_hong_tra_so_0_khong_crash(self, tmp_path):
        from src.api.adapters.worker_source import WorkerFrameSource

        (tmp_path / "status.json").write_text("không phải json", encoding="utf-8")
        detail = WorkerFrameSource("0", out_dir=tmp_path).telemetry()
        assert (detail.display_fps, detail.mask_fps, detail.empty_runs) == (0.0, 0.0, 0)


class TestNhipDocFrame:
    def test_api_doc_frame_nhanh_bang_nhip_phat_cua_worker(self):
        """`target_fps` mặc định 15 từng làm FPS của API trần 15 (lệch 29,9 của worker)."""
        from src.api.live import LIVE_READ_FPS, LiveStreamService

        service = LiveStreamService(lambda *a, **k: None)
        assert LIVE_READ_FPS >= 30
        assert service._interval == pytest.approx(1.0 / LIVE_READ_FPS)


from tests.conftest import FakeFrameSource  # noqa: E402 — dùng cho các nguồn giả bên dưới


class _SlowStartSource(FakeFrameSource):
    """Nguồn mô phỏng worker THẬT: `start()` mất thời gian (nạp model 20–60 s)."""

    def __init__(self, source, *, delay=0.4, **kwargs):
        super().__init__(source, **kwargs)
        self._delay = delay
        self.start_calls = 0
        self.start_finished = False
        # Event để test đồng bộ KHÔNG dùng sleep: "đã vào start()" / "được phép mở xong"
        self.entered = __import__("threading").Event()
        self.release = __import__("threading").Event()

    def start(self):
        self.start_calls += 1
        self.entered.set()
        self.release.wait(timeout=5)      # test mở; hết hạn thì vẫn chạy tiếp (không treo CI)
        super().start()
        self.start_finished = True


class TestVongDoiPhienLive:
    """Review độc lập 08-11 (vòng life-cycle): double-start, dừng khi đang nạp, shutdown."""

    def test_start_dong_thoi_chi_mo_mot_nguon(self, live_service, monkeypatch):
        """POST /api/live/start đồng thời (double-click, 2 tab) không được tạo 2 worker."""
        import threading

        from src.api.domain import LiveBusy

        created = []

        def factory(*args, **kwargs):
            item = _SlowStartSource(str(args[0]))
            created.append(item)
            return item

        monkeypatch.setattr(live_service, "_make_source", factory)
        errors, results = [], []
        barrier = threading.Barrier(4)        # 4 thread gọi start() CÙNG LÚC (không dựa vào sleep)

        def _one():
            barrier.wait(timeout=5)
            _try(lambda: results.append(live_service.start("0")), errors)

        threads = [threading.Thread(target=_one) for _ in range(4)]
        for t in threads:
            t.start()
        # Chờ ĐIỀU KIỆN (3 lần LiveBusy) chứ không chờ thời gian cố định: nguồn thắng đang
        # block trong start() nên phải thả nó ra sau khi 3 request kia đã bị từ chối.
        deadline = time.monotonic() + 5
        while len(errors) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        created[0].release.set()
        for t in threads:
            t.join(timeout=10)

        assert len(created) == 1, "chỉ một nguồn được tạo (không có worker thứ hai)"
        assert created[0].start_calls == 1
        assert all(isinstance(err, LiveBusy) for err in errors), errors
        assert len(results) == 1 and results[0].state is LiveState.RUNNING
        live_service.stop()

    def test_dung_trong_luc_nap_model_thi_khong_de_worker_mo_coi(self, live_service, monkeypatch):
        """Bấm Dừng khi đang nạp model: phiên phải kết thúc 'stopped' và nguồn bị đóng."""
        import threading

        created = []

        def factory(*args, **kwargs):
            item = _SlowStartSource(str(args[0]), delay=0.5)
            created.append(item)
            return item

        monkeypatch.setattr(live_service, "_make_source", factory)
        box = {}

        def _start():
            box["status"] = live_service.start("0")

        worker = threading.Thread(target=_start)
        worker.start()
        assert created[0].entered.wait(timeout=5), "start() chưa vào nguồn"
        live_service.stop()                     # chen vào GIỮA lúc start() (đang nạp model)
        created[0].release.set()
        worker.join(timeout=10)

        assert box["status"].state is LiveState.STOPPED
        assert created and created[0].stopped is True, "nguồn vừa mở phải bị đóng, không mồ côi"

    def test_api_tra_409_khi_dang_mo_phien_khac(self, live_client, monkeypatch):
        import threading

        created, made = [], threading.Event()

        def factory(*args, **kwargs):
            item = _SlowStartSource("0", delay=0.6)
            created.append(item)
            made.set()
            return item

        monkeypatch.setattr(live_client.app.state.live, "_make_source", factory)
        codes, errors = [], []

        def _post():
            _try(lambda: codes.append(
                live_client.post("/api/live/start", json={"source": "0"}).status_code), errors)

        first = threading.Thread(target=_post)
        first.start()
        assert made.wait(timeout=5), "request đầu chưa tạo nguồn"
        assert created[0].entered.wait(timeout=5), "request đầu chưa vào start()"
        second = live_client.post("/api/live/start", json={"source": "0"})
        created[0].release.set()
        first.join(timeout=10)

        assert not errors, f"request đầu ném lỗi: {errors}"
        assert second.status_code == 409
        assert 200 in codes

    def test_shutdown_dung_worker(self, service, api_settings):
        """Thoát app (uvicorn --reload) phải dừng worker: trước đây worker mồ côi ghi đè frame.jpg."""
        from fastapi.testclient import TestClient

        from src.api.live import LiveStreamService
        from src.api.main import create_app
        from tests.conftest import FakeFrameSource

        created = []

        def factory(*args, **kwargs):
            item = FakeFrameSource(str(args[0]))
            created.append(item)
            return item

        live = LiveStreamService(factory)
        app = create_app(settings=api_settings, service=service, live=live)
        with TestClient(app) as client:
            client.post("/api/live/start", json={"source": "0"})

        assert created and created[0].stopped is True, "shutdown phải đóng nguồn"


def _try(fn, errors):
    try:
        fn()
    except Exception as exc:        # noqa: BLE001 — test cần bắt lỗi miền
        errors.append(exc)


class TestTheHePhien:
    """Thread đọc của phiên CŨ không được ghi `_latest` sau khi stop()/phiên mới dọn (race thật)."""

    def test_thread_cu_khong_ghi_de_frame_sau_khi_stop(self, live_service, monkeypatch):
        import time

        from tests.conftest import FakeFrameSource

        class _SlowSource(FakeFrameSource):
            def read_jpeg(self):
                time.sleep(0.15)          # đọc chậm ⇒ stop() join(2s) có thể timeout
                return super().read_jpeg()

        monkeypatch.setattr(live_service, "_make_source", lambda *a, **k: _SlowSource("0"))
        live_service.start("0")
        assert _wait(lambda: live_service.latest_jpeg() is not None)
        live_service.stop()

        assert live_service.latest_jpeg() is None
        time.sleep(0.5)                  # đủ để thread cũ (nếu còn sống) ghi lại
        assert live_service.latest_jpeg() is None, "thread của phiên cũ ghi lại frame sau khi dừng"


class TestCaptureNemLoi:
    """`capture.read()` NÉM (cv2.error khi capture hỏng) vẫn phải được đếm là một lần trượt."""

    class _RaisingCapture:
        def read(self):
            raise RuntimeError("cv2.error: capture hỏng")

        def close(self):
            pass

    def test_read_nem_loi_van_bao_error_sau_nguong(self, monkeypatch):
        from src.api.adapters import OpenCvFrameSource, opencv_source

        source = OpenCvFrameSource("0")

        class _Opener:
            def open(self):
                return TestCaptureNemLoi._RaisingCapture()

        monkeypatch.setattr(opencv_source, "open_video_source", lambda *a, **k: _Opener())
        source.start()
        for _ in range(opencv_source.MISS_MIN):
            assert source.read_jpeg() is None            # mỗi lần ném = một lần trượt
        source._last_frame_at -= (opencv_source.WARMUP_S + 1.0)

        health = source.health()
        assert health is not None and health.state is LiveState.ERROR

    def test_imencode_hong_thi_khong_coi_la_co_frame(self, monkeypatch):
        """`imencode` trả False mãi ⇒ `health()` không được báo khoẻ (UI không thấy frame nào)."""
        from src.api.adapters import OpenCvFrameSource, opencv_source

        capture = TestOpenCvSourceHealth._Capture([TestOpenCvSourceHealth._frame()])

        class _Opener:
            def open(self):
                return capture

        monkeypatch.setattr(opencv_source, "open_video_source", lambda *a, **k: _Opener())
        monkeypatch.setattr(opencv_source.cv2, "imencode", lambda *a, **k: (False, None))
        source = OpenCvFrameSource("0")
        source.start()
        truoc = source._last_frame_at
        assert source.read_jpeg() is None                 # encode hỏng ≠ "đã có frame"
        assert source._last_frame_at == truoc, "encode hỏng mà vẫn cập nhật mốc frame ⇒ health báo khoẻ"
        assert source._got_frame is False
        for _ in range(opencv_source.MISS_MIN - 1):
            assert source.read_jpeg() is None
        source._last_frame_at -= (opencv_source.WARMUP_S + 1.0)

        health = source.health()
        assert health is not None and health.state is LiveState.ERROR
class TestChanDoanChatLuongBam:
    """/api/live/status: `drift_*` và `empty_frac_window` phải đi qua NGUYÊN VẸN, `None` không thành 0.

    Vì sao có (review 09-11): adapter cũ dùng `float(status.get("drift_iou") or 0.0)` ⇒ "chưa đo"
    thành "đo được 0", và UI sẽ hiện drift 0,00 như thể LK hỏng hoàn toàn. Ở chiều ngược lại, không
    có cửa sổ thì UI in "mất dấu 26 lần" từ bộ đếm trọn đời cho một sự việc đã qua.
    """

    def _telemetry(self, tmp_path, **fields):
        import json

        from src.api.adapters.worker_source import WorkerFrameSource

        (tmp_path / "status.json").write_text(json.dumps(fields), encoding="utf-8")
        return WorkerFrameSource("0", out_dir=tmp_path).telemetry()

    def test_chua_do_drift_thi_none_va_drift_n_0(self, tmp_path):
        detail = self._telemetry(tmp_path, state="tracking", vos_fps=8.6, empty_runs=0)
        assert detail.drift_p05 is None            # KHÔNG phải 0.0
        assert detail.drift_n == 0
        assert detail.empty_frac_window is None
        assert detail.empty_window_n == 0

    def test_drift_0_0_do_duoc_van_la_0_0(self, tmp_path):
        """Ca xấu nhất của binh2 (p05 = 0,000) phải đi qua thành số 0, KHÔNG thành None."""
        detail = self._telemetry(tmp_path, state="tracking", vos_fps=7.4,
                                 drift_iou_p05=0.0, drift_n=198,
                                 empty_frac_window=0.112, empty_window_n=200)
        assert detail.drift_p05 == 0.0
        assert detail.drift_n == 198
        assert detail.empty_frac_window == pytest.approx(0.112)
        assert detail.empty_window_n == 200

    def test_vos_every_1_khong_do_duoc_drift(self, tmp_path):
        """Phiên `vos_every=1` (tắt LK) ⇒ `drift_iou_p05 = null` trong status.json."""
        detail = self._telemetry(tmp_path, state="tracking", vos_fps=8.0,
                                 drift_iou=None, drift_iou_p05=None, drift_n=0)
        assert detail.drift_p05 is None and detail.drift_n == 0


class _TelemetrySource:
    """Nguồn giả CÓ `telemetry()` (port `LiveTelemetrySource`) — không cần worker thật."""

    def __init__(self, *args, **kwargs):
        self.stopped = False

    def start(self):
        pass

    def read_jpeg(self):
        return b"\xff\xd8fake"

    def stop(self):
        self.stopped = True

    def telemetry(self):
        from src.api.domain import LiveTelemetry

        return LiveTelemetry(mask_fps=8.6, drift_p05=None, drift_n=0,
                             empty_frac_window=0.112, empty_window_n=200)

    @property
    def label(self):
        return "giả:telemetry"


class TestLiveStatusChanDoanQuaApi:
    def test_status_tra_hai_truong_moi_kem_null_trung_thuc(self, live_client, monkeypatch):
        monkeypatch.setattr(live_client.app.state.live, "_make_source",
                            lambda *a, **k: _TelemetrySource())
        live_client.post("/api/live/start", json={"source": "0"})
        body = live_client.get("/api/live/status").json()
        live_client.post("/api/live/stop")

        assert body["drift_p05"] is None            # null, không phải 0.0
        assert body["drift_n"] == 0
        assert body["empty_frac_window"] == pytest.approx(0.112)
        assert body["empty_window_n"] == 200


class TestMoLaiSauPhienLoi:
    """Ticket 16: sau phiên `error`, lúc bấm Bật phát lại, API **không** được trả `error` trong khi
    đang nạp nguồn (worker `track` mất 20–240 s) — nếu không, UI hiện `role="alert"` và
    `/api/live/stream` trả 409 "Phiên live đã dừng vì lỗi: Đang mở …" suốt lúc nạp bình thường."""

    def test_dang_mo_lai_thi_state_la_loading_khong_phai_error(self, live_client, monkeypatch):
        import threading

        created = []

        def factory(*args, **kwargs):
            item = _SlowStartSource("0", delay=0.4)
            created.append(item)
            return item

        monkeypatch.setattr(live_client.app.state.live, "_make_source", factory)

        # Phiên trước: kết thúc bằng `error` (worker chết) — đúng ca người dùng bấm Bật lại.
        live_client.post("/api/live/start", json={"source": "0"})
        created[-1].release.set() if created else None
        live_client.app.state.live.stop()
        with live_client.app.state.live._lock:            # mô phỏng watchdog đã báo lỗi
            live_client.app.state.live._state = LiveState.ERROR
            live_client.app.state.live._message = "worker dừng (mã 1)"

        # Bật lại: giữ `start()` trong lúc đang nạp để đọc trạng thái giữa chừng.
        errors, done = [], threading.Event()

        def _post():
            _try(lambda: live_client.post("/api/live/start", json={"source": "0"}), errors)
            done.set()

        worker = threading.Thread(target=_post)
        worker.start()
        assert created[-1].entered.wait(timeout=5), "start() chưa vào nguồn"

        status = live_client.get("/api/live/status").json()
        assert status["state"] == "loading", f"state = {status['state']} (phải 'loading')"
        assert status["state"] != "error", "đang nạp bình thường mà báo lỗi ⇒ UI hiện role=alert"

        stream = live_client.get("/api/live/stream")
        assert stream.status_code == 409
        chi_tiet = stream.json()["detail"]
        assert "đã dừng vì lỗi" not in chi_tiet, f"stream báo lỗi giả: {chi_tiet}"
        assert "Đang mở" in chi_tiet

        created[-1].release.set()
        worker.join(timeout=10)
        assert done.is_set() and not errors


class TestStabilityNoneDiQuaCaChuoi:
    """Ticket 18: `stability = None` (chưa đo) phải sống sót worker → adapter → domain → route →
    JSON. Bẫy đã gặp 3 lần trong repo: `float(x or 0.0)` biến "chưa đo" thành "đo được 0"."""

    def test_stability_none_va_0_0_khac_nhau(self, live_client, monkeypatch):
        from src.api.domain import LiveTelemetry

        class _KhongDoDuoc(FakeFrameSource):
            def telemetry(self):
                return LiveTelemetry(display_fps=30.0, mask_fps=8.0, stability=None, stability_n=0)

        class _DoDuoc0(FakeFrameSource):
            def telemetry(self):
                return LiveTelemetry(display_fps=30.0, mask_fps=8.0, stability=0.0, stability_n=150)

        monkeypatch.setattr(live_client.app.state.live, "_make_source",
                            lambda *a, **k: _KhongDoDuoc("0"))
        live_client.post("/api/live/start", json={"source": "0"})
        chua_do = live_client.get("/api/live/status").json()
        live_client.app.state.live.stop()

        monkeypatch.setattr(live_client.app.state.live, "_make_source",
                            lambda *a, **k: _DoDuoc0("0"))
        live_client.post("/api/live/start", json={"source": "0"})
        do_duoc = live_client.get("/api/live/status").json()
        live_client.app.state.live.stop()

        assert chua_do["stability"] is None and chua_do["stability_n"] == 0
        assert do_duoc["stability"] == 0.0 and do_duoc["stability_n"] == 150, \
            "0,0 ĐO ĐƯỢC không được biến thành null (và ngược lại)"
