"""Test WATCHDOG phiên live: worker chết/treo giữa phiên phải lộ ra thành `error`, không im lặng.

Vì sao có file này (plan 08-11, việc 3): sau `start()`, không chỗ nào theo dõi worker nữa. Worker
chết (OOM, rút webcam, exception model) ⇒ `frame.jpg` đứng yên, `frames()` hết thấy frame mới ⇒
API im lặng `return` sau `idle_timeout` trong khi UI vẫn báo `running` và `mask_fps` cũ. Đúng kiểu
"hỏng mà trông như đang chạy" — thứ đắt nhất lúc demo.

Hai tầng được kiểm:
  1. Adapter (`WorkerFrameSource.health`) — đọc tín hiệu thật: `proc.poll()`, `status.json`, mtime
     của `frame.jpg`. Không cần worker/torch: tiến trình giả + file giả.
  2. Service (`LiveStreamService`) — thấy nguồn "unhealthy" thì chuyển `error` + message và ĐÓNG
     luồng MJPEG, không treo client.
"""

import json
import os
import time

import pytest

from src.api.domain import LiveState, SourceHealth


def _wait(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _DeadProc:
    """Tiến trình ĐÃ CHẾT: `poll()` trả mã thoát (đúng hợp đồng subprocess.Popen)."""

    def __init__(self, code=1, pid=999999):
        self.pid = pid
        self.returncode = code

    def poll(self):
        return self.returncode


class _LiveProc:
    """Tiến trình còn sống: `poll()` trả None."""

    pid = 999998

    def poll(self):
        return None


def _write_status(tmp_path, **fields):
    (tmp_path / "status.json").write_text(json.dumps(fields), encoding="utf-8")


def _touch_frame(tmp_path, age_s=0.0):
    """Tạo `frame.jpg` có mtime lùi `age_s` giây (giả lập worker ngừng ghi frame)."""
    path = tmp_path / "frame.jpg"
    path.write_bytes(b"\xff\xd8fake")
    if age_s:
        past = time.time() - age_s
        os.utime(path, (past, past))
    return path


class TestWorkerHealth:
    """Adapter: tín hiệu nào là "khoẻ", tín hiệu nào là "đã chết/treo"."""

    def _source(self, tmp_path, proc):
        from src.api.adapters.worker_source import WorkerFrameSource

        source = WorkerFrameSource("0", out_dir=tmp_path)
        source._proc = proc          # tiêm tiến trình giả: không chạy worker thật/torch
        return source

    def test_chua_start_thi_khong_bao_loi(self, tmp_path):
        from src.api.adapters.worker_source import WorkerFrameSource

        assert WorkerFrameSource("0", out_dir=tmp_path).health() is None

    def test_worker_song_va_dang_ghi_frame_thi_khoe(self, tmp_path):
        _write_status(tmp_path, state="tracking", frames=120)
        _touch_frame(tmp_path)

        assert self._source(tmp_path, _LiveProc()).health() is None

    def test_worker_chet_thi_bao_error_kem_ma_thoat_va_duong_dan_log(self, tmp_path):
        _write_status(tmp_path, state="tracking")
        _touch_frame(tmp_path)

        health = self._source(tmp_path, _DeadProc(1)).health()

        assert health is not None
        assert health.state is LiveState.ERROR
        assert "(mã 1)" in health.message, health.message
        assert "worker.log" in health.message, health.message

    def test_worker_bao_error_trong_status_thi_message_cua_worker_duoc_giu(self, tmp_path):
        _write_status(tmp_path, state="error", message="model lỗi trong luồng VOS: CUDA OOM")
        _touch_frame(tmp_path)

        health = self._source(tmp_path, _LiveProc()).health()

        assert health is not None and health.state is LiveState.ERROR
        assert "CUDA OOM" in health.message

    def test_worker_tu_ket_thuc_binh_thuong_thi_stopped_khong_phai_error(self, tmp_path):
        """`stop_after_frames`/hết video: worker thoát mã 0 + state stopped ⇒ phiên KẾT THÚC."""
        _write_status(tmp_path, state="stopped", message="")
        _touch_frame(tmp_path)

        health = self._source(tmp_path, _DeadProc(0)).health()

        assert health is not None and health.state is LiveState.STOPPED

    def test_worker_treo_khong_ghi_frame_thi_bao_error(self, tmp_path):
        """Còn tiến trình nhưng `frame.jpg` đứng 40 s ⇒ treo thật (deadlock model), phải báo lỗi."""
        _write_status(tmp_path, state="tracking")
        _touch_frame(tmp_path, age_s=40.0)

        health = self._source(tmp_path, _LiveProc()).health()

        assert health is not None and health.state is LiveState.ERROR
        assert "frame" in health.message.lower()

    def test_ghi_cham_hop_le_khong_bi_coi_la_treo(self, tmp_path):
        """P1 review 09-11: nhịp ghi HỢP LỆ có thể là 4 s/frame.

        `image_size 1024` ≈ 4 s/frame (README) và `vos_every=1` tắt nội suy LK ⇒ nhịp ghi frame =
        nhịp model. `engine.start()` cũng chạy inline trước frame tracking đầu tiên
        (`live_tracking.py:348`). Ngưỡng cứng 2 s sẽ GIẾT phiên khoẻ — đây là test canh điều đó.
        """
        _write_status(tmp_path, state="tracking", vos_ms=4000.0)
        _touch_frame(tmp_path, age_s=5.0)            # 5 s không có frame mới, nhưng model 4 s/frame

        assert self._source(tmp_path, _LiveProc()).health() is None

    def test_nguong_treo_co_theo_do_tre_model_tu_bao(self, tmp_path):
        """Ngưỡng = max(15 s, 4 × `vos_ms`) — `vos_ms` lớn thì cho phép frame cũ lâu hơn."""
        _touch_frame(tmp_path, age_s=13.0)                                # 13 s: dưới sàn 15 s
        _write_status(tmp_path, state="tracking", vos_ms=100.0)
        assert self._source(tmp_path, _LiveProc()).health() is None

        _touch_frame(tmp_path, age_s=20.0)                                # 20 s > sàn 15 s
        _write_status(tmp_path, state="tracking", vos_ms=6000.0)          # ngưỡng = 4 × 6 s = 24 s
        assert self._source(tmp_path, _LiveProc()).health() is None

    def test_treo_that_thi_van_bao_loi_du_model_cham(self, tmp_path):
        _write_status(tmp_path, state="tracking", vos_ms=3000.0)           # ngưỡng = 15 s
        _touch_frame(tmp_path, age_s=20.0)

        health = self._source(tmp_path, _LiveProc()).health()
        assert health is not None and health.state is LiveState.ERROR

    def test_dang_cho_chon_doi_tuong_van_khoe_neu_frame_con_moi(self, tmp_path):
        """`waiting_selection`: status.json KHÔNG được ghi lại mỗi frame (chỉ frame.jpg được ghi)
        ⇒ heartbeat phải là mtime frame, không phải `ts` trong status.json (nếu không phiên chết oan
        khi người dùng mất vài phút kéo chuột — `src/live_tracking.py:342-348`).
        """
        _write_status(tmp_path, state="waiting_selection", frames=0)
        _touch_frame(tmp_path)                      # frame vẫn mới
        old = time.time() - 120
        os.utime(tmp_path / "status.json", (old, old))   # status.json cũ 2 phút

        assert self._source(tmp_path, _LiveProc()).health() is None


class _DyingSource:
    """Fake FrameSource kèm `health()`: phát N frame rồi báo lý do chết (như worker thật)."""

    def __init__(self, source="0", *, frames_before_death=3, state=LiveState.ERROR,
                 message="worker đã dừng (mã 1) — xem worker.log", health_raises=False):
        self.source = source
        self._left = frames_before_death
        self._state = state
        self._message = message
        self._raises = health_raises
        self.calls = 0                # số lần `health()` được gọi (bằng chứng watchdog CÓ chạy)
        self._seq = 0
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def read_jpeg(self):
        if not self.started:
            return None
        self._seq += 1
        return b"\xff\xd8fake-frame#" + str(self._seq).encode()

    def stop(self):
        self.stopped = True

    @property
    def label(self):
        return f"giả:{self.source}"

    def health(self):
        self.calls += 1
        if self._raises:
            raise OSError("không đọc được status.json")
        if self._left > 0:
            self._left -= 1
            return None
        return SourceHealth(state=self._state, message=self._message)


class TestServicePhatHienNguonChet:
    def test_nguon_chet_giua_phien_thi_doi_error_va_giu_message(self):
        from src.api.live import LiveStreamService

        service = LiveStreamService(lambda *a, **k: _DyingSource(), target_fps=50)
        service.start("0")

        assert _wait(lambda: service.status().state is LiveState.ERROR, timeout=2.0)
        status = service.status()
        assert "worker đã dừng" in status.message
        service.stop()

    def test_nguon_chet_thi_luong_mjpeg_ket_thuc_khong_treo(self):
        """Không có đường thoát ⇒ thread MJPEG của server treo tới `idle_timeout`."""
        from src.api.live import LiveStreamService

        service = LiveStreamService(lambda *a, **k: _DyingSource(), target_fps=50)
        service.start("0")
        stream = service.frames(idle_timeout=30.0)      # 30 s: chỉ thoát được nếu watchdog đóng luồng
        next(stream)
        assert _wait(lambda: service.status().state is LiveState.ERROR, timeout=2.0)

        # Nguồn có thể kịp ghi thêm vài frame trước khi chết ⇒ luồng phát nốt rồi mới đóng;
        # điều bắt buộc là nó ĐÓNG (không treo tới idle_timeout 30 s).
        for _ in range(10):
            try:
                next(stream)
            except StopIteration:
                break
        else:
            pytest.fail("luồng MJPEG không đóng sau khi nguồn chết — client sẽ treo")
        service.stop()

    def test_nguon_tu_ket_thuc_thi_state_stopped_chu_khong_phai_error(self):
        from src.api.live import LiveStreamService

        service = LiveStreamService(
            lambda *a, **k: _DyingSource(state=LiveState.STOPPED, message="nguồn đã hết"),
            target_fps=50)
        service.start("0")

        assert _wait(lambda: service.status().state is LiveState.STOPPED, timeout=2.0)
        assert service.status().message == "nguồn đã hết"
        service.stop()

    def test_nguon_chet_thi_dong_nguon_ngay_de_khong_giu_webcam(self):
        """Worker treo mà còn sống thì vẫn giữ camera ⇒ lần "Bật phát" sau hỏng."""
        from src.api.live import LiveStreamService

        created = []

        def factory(*args, **kwargs):
            source = _DyingSource()
            created.append(source)
            return source

        service = LiveStreamService(factory, target_fps=50)
        service.start("0")

        assert _wait(lambda: created and created[0].stopped, timeout=2.0)
        service.stop()

    def test_nguon_khoe_thi_khong_bao_loi_gia(self):
        from src.api.live import LiveStreamService

        source = _DyingSource(frames_before_death=10_000)
        service = LiveStreamService(lambda *a, **k: source, target_fps=50)
        service.start("0")
        # Đếm hành vi, không `sleep`: trên CI chậm, sleep 0,3 s có thể chưa đủ một vòng health ⇒
        # test xanh mà không chứng minh gì ("pass rỗng" — P3 review 09-11).
        assert _wait(lambda: source.calls >= 3, timeout=3.0), source.calls
        assert service.status().state is LiveState.RUNNING
        service.stop()

    def test_health_nem_loi_khong_lam_chet_phien(self):
        """Lỗi đọc status.json là lỗi TẠM THỜI, không phải bằng chứng worker chết."""
        from src.api.live import LiveStreamService

        source = _DyingSource(health_raises=True)
        service = LiveStreamService(lambda *a, **k: source, target_fps=50)
        service.start("0")
        assert _wait(lambda: source.calls >= 3, timeout=3.0), source.calls
        assert service.status().state is LiveState.RUNNING
        service.stop()

    def test_nguon_khong_co_health_thi_giu_nguyen_hanh_vi_cu(self, live_service):
        """`FakeFrameSource` (webcam/file) không có `health()` ⇒ không được kiểm tra gì."""
        live_service.start("0")
        time.sleep(0.2)
        assert live_service.status().state is LiveState.RUNNING
        live_service.stop()


class TestRouteBaoLoi:
    def test_api_tra_error_trong_2s_khi_worker_chet(self, live_client, monkeypatch):
        monkeypatch.setattr(live_client.app.state.live, "_make_source",
                            lambda *a, **k: _DyingSource())
        live_client.post("/api/live/start", json={"source": "0"})

        seen = []

        def _da_error():
            body = live_client.get("/api/live/status").json()
            seen.append(body)
            return body.get("state") == "error"

        assert _wait(_da_error, timeout=2.0), seen[-1:]
        assert "worker đã dừng" in seen[-1]["message"]
        live_client.post("/api/live/stop")


class TestDongBoVoiWorkerThat:
    """Hợp đồng với `tools/live_worker.py`: state mà worker ghi ra phải được hiểu đúng."""

    def test_state_error_cua_worker_la_error(self, tmp_path):
        from src.api.adapters.worker_source import WorkerFrameSource
        from src.live_tracking import STATE_ERROR

        _write_status(tmp_path, state=STATE_ERROR, message="nguồn frame đọc lỗi")
        _touch_frame(tmp_path)
        source = WorkerFrameSource("0", out_dir=tmp_path)
        source._proc = _LiveProc()

        health = source.health()
        assert health is not None and health.state is LiveState.ERROR
        assert "nguồn frame đọc lỗi" in health.message


class _ProcForStop:
    """Tiến trình giả đủ hợp đồng cho `WorkerFrameSource.stop()`."""

    def __init__(self, pid):
        self.pid = pid
        self.killed = False

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        self.killed = True

    def kill(self):
        self.killed = True


class TestPidfileKhongBiXoaNham:
    """P2 review 09-11: `stop()` của phiên CŨ không được xoá pidfile của phiên MỚI.

    Ca thật: watchdog phát hiện worker treo ⇒ gọi `source.stop()` trong luồng nền (có thể chờ
    `proc.wait(timeout=5)`); trong lúc đó người dùng bấm "Bật phát" ⇒ phiên mới spawn worker và ghi
    `worker.pid` mới ⇒ `finally: unlink(PID_NAME)` của luồng cũ xoá mất pidfile ⇒ lần `uvicorn
    --reload` sau không reap được worker mồ côi (bug đã sửa ở PR vòng đời 08-11).
    """

    def test_stop_phien_cu_khong_xoa_pidfile_cua_phien_moi(self, tmp_path):
        from src.api.adapters.worker_source import PID_NAME, WorkerFrameSource

        pidfile = tmp_path / PID_NAME
        pidfile.write_text("111", encoding="utf-8")

        old = WorkerFrameSource("0", out_dir=tmp_path)
        old._proc = _ProcForStop(111)          # phiên cũ, pid 111
        pidfile.write_text("222", encoding="utf-8")   # phiên MỚI đã ghi pidfile của nó

        old.stop()

        assert pidfile.read_text(encoding="utf-8") == "222", "pidfile của phiên mới bị xoá nhầm"
