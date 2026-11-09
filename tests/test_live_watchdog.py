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
import sys
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

    def test_nguon_khong_co_health_thi_giu_nguyen_hanh_vi_cu(self, live_service,
                                                             make_frame_source):
        """`FakeFrameSource` (webcam/file) không có `health()` ⇒ không bị đụng tới.

        Bằng chứng phải là **vòng đọc vẫn chạy** (số frame của nguồn tăng), không phải `sleep`:
        nếu ai đó gọi `health()` vô điều kiện, `AttributeError` bị `_check_health` nuốt và test
        `sleep + assert RUNNING` vẫn xanh ⇒ "pass rỗng" (P3 review vòng 2).
        """
        live_service.start("0")
        source = make_frame_source.created[-1]
        assert _wait(lambda: source._seq >= 3, timeout=3.0), source._seq
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
    """Tiến trình THẬT (sleep) bọc qua `Popen` thật — KHÔNG bịa pid.

    Vì sao: `stop()` gọi `os.killpg(os.getpgid(pid), SIGTERM)`. Dùng pid giả (vd 111) thì trên máy/CI
    có tiến trình thật trùng pid, test sẽ gửi SIGTERM vào process group của người khác (P3 review
    vòng 2).
    """

    def __init__(self):
        import subprocess

        self._proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      start_new_session=True)
        self.pid = self._proc.pid

    def wait(self, timeout=None):
        return self._proc.wait(timeout=timeout)

    def terminate(self):
        self._proc.terminate()

    def kill(self):
        self._proc.kill()


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

        proc = _ProcForStop()
        pidfile.write_text(str(proc.pid), encoding="utf-8")
        old = WorkerFrameSource("0", out_dir=tmp_path)
        old._proc = proc                        # phiên cũ (tiến trình thật)
        pidfile.write_text("222", encoding="utf-8")   # phiên MỚI đã ghi pidfile của nó

        old.stop()

        assert pidfile.read_text(encoding="utf-8") == "222", "pidfile của phiên mới bị xoá nhầm"
        assert proc.wait(timeout=5) is not None, "worker cũ phải bị dừng thật"


class TestLuongMjpegBaoDungLyDo:
    """P3 review 09-11: `/api/live/stream` trả cùng một câu 409 cho cả `error` và "chưa bật".

    Khi watchdog báo worker chết, client chỉ thấy "Chưa có phiên live nào đang chạy" ⇒ mất đúng
    thông tin vừa có được.
    """

    def test_phien_loi_thi_409_kem_ly_do_cua_watchdog(self, live_client, monkeypatch):
        monkeypatch.setattr(live_client.app.state.live, "_make_source",
                            lambda *a, **k: _DyingSource())
        live_client.post("/api/live/start", json={"source": "0"})
        assert _wait(lambda: live_client.get("/api/live/status").json()["state"] == "error",
                     timeout=2.0)

        response = live_client.get("/api/live/stream")
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail.startswith("Phiên live đã dừng vì lỗi: ")
        assert "worker đã dừng" in detail        # lý do của watchdog phải đi vào HTTP
        live_client.post("/api/live/stop")

    def test_chua_bat_thi_409_cau_cu(self, live_client):
        response = live_client.get("/api/live/stream")
        assert response.status_code == 409
        assert response.json()["detail"] == "Chưa có phiên live nào đang chạy"


class _RaisingSource:
    """Nguồn ném lỗi ở N lần đọc đầu rồi mới chạy bình thường (capture hỏng tạm thời)."""

    def __init__(self, source="0", *, raises=5):
        self.source = source
        self._left = raises
        self._seq = 0
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def read_jpeg(self):
        if self._left > 0:
            self._left -= 1
            raise RuntimeError("capture hỏng")
        self._seq += 1
        return b"\xff\xd8fake#" + str(self._seq).encode()

    def stop(self):
        self.stopped = True

    @property
    def label(self):
        return f"giả:{self.source}"


class TestDocFrameNemLoi:
    def test_read_jpeg_nem_loi_khong_lam_chet_thread_doc(self):
        """Lỗi đọc là lỗi TẠM THỜI: thread đọc phải sống tiếp, không để `_state` kẹt `running` mà
        không còn frame nào (đúng lớp lỗi "hỏng mà trông như đang chạy").

        Bằng chứng: nguồn ném lỗi 5 lần đầu rồi mới trả frame — nếu ngoại lệ thoát khỏi `_run` thì
        thread chết và `frames` mãi = 0 ⇒ test đỏ.
        """
        from src.api.live import LiveStreamService

        service = LiveStreamService(lambda *a, **k: _RaisingSource(raises=5), target_fps=50)
        service.start("0")

        assert _wait(lambda: service.status().frames >= 1, timeout=3.0), service.status()
        service.stop()
        assert service.status().state is LiveState.STOPPED


class _AlwaysFailingSource:
    """Nguồn ném lỗi Ở MỌI lần đọc và KHÔNG tự khai sức sống (không có `health()`).

    Đây là tấm chắn cuối của service: adapter `FrameSource` trơn mà đọc lỗi mãi thì `_read_safely`
    nuốt lỗi ⇒ phiên kẹt `running` với 0 frame (review độc lập 09-11 vòng 2, P3).
    """

    def __init__(self, source="0"):
        self.source = source
        self.reads = 0
        self.stopped = False

    def start(self):
        pass

    def read_jpeg(self):
        self.reads += 1
        raise RuntimeError("capture hỏng vĩnh viễn")

    def stop(self):
        self.stopped = True

    @property
    def label(self):
        return f"giả:{self.source}"


class TestDocFrameLoiLienTuc:
    def test_loi_lien_tuc_qua_nguong_thi_error_chu_khong_running_mai(self, monkeypatch):
        """Nguồn không có `health()`: nếu `read_jpeg()` ném mãi thì phải thành `error` có message."""
        from src.api import live as live_module
        from src.api.live import LiveStreamService

        monkeypatch.setattr(live_module, "_READ_ERROR_GIVE_UP_S", 0.0)
        service = LiveStreamService(lambda *a, **k: _AlwaysFailingSource(), target_fps=50)
        service.start("0")

        assert _wait(lambda: service.status().state is LiveState.ERROR, timeout=3.0), service.status()
        status = service.status()
        assert "lỗi liên tiếp" in status.message
        assert _wait(lambda: service._read_errors >= 1, timeout=2.0)
        service.stop()

    def test_doc_lai_duoc_thi_xoa_chuoi_loi(self):
        """Lỗi TẠM THỜI (vài lần) không được tích thành `error`: đọc lại được là reset bộ đếm."""
        from src.api.live import LiveStreamService

        service = LiveStreamService(lambda *a, **k: _RaisingSource(raises=5), target_fps=50)
        service.start("0")
        try:
            assert _wait(lambda: service.status().frames >= 1, timeout=3.0), service.status()
            assert service.status().state is LiveState.RUNNING
            assert service._read_errors == 0
        finally:
            service.stop()


class _FailThenWorkSource:
    """Ném lỗi đúng `raises` lần rồi trả frame — dùng để kiểm bộ đếm lỗi có reset theo phiên."""

    def __init__(self, source="0", *, raises=1):
        self.source = source
        self._left = raises
        self.stopped = False
        self._seq = 0

    def start(self):
        pass

    def read_jpeg(self):
        if self._left > 0:
            self._left -= 1
            raise RuntimeError("capture hỏng")
        self._seq += 1
        return b"\xff\xd8ok#" + str(self._seq).encode()

    def stop(self):
        self.stopped = True

    @property
    def label(self):
        return f"giả:{self.source}"


class TestBoDemLoiDocTheoPhien:
    def test_bo_dem_loi_doc_khong_ro_tu_phien_truoc(self, monkeypatch):
        """P1 vòng 3: `_read_errors`/`_read_error_since` để rò qua `start()` ⇒ lần đọc lỗi ĐẦU TIÊN
        của phiên mới thấy `stuck_s` hàng chục giây ⇒ give-up ngay, giết phiên khoẻ.

        Kịch bản thật: phiên A chết vì give-up (lần đọc cuối luôn ném ⇒ `_read_errors ≥ 1`), người
        dùng bật lại (phiên B) và nguồn trượt MỘT lần ⇒ nếu không reset, B bị `error` oan.
        """
        from src.api import live as live_module
        from src.api.live import LiveStreamService

        monkeypatch.setattr(live_module, "_READ_ERROR_GIVE_UP_S", 0.0)
        dying = _AlwaysFailingSource()
        service = LiveStreamService(lambda *a, **k: dying, target_fps=50)
        service.start("0")
        assert _wait(lambda: service.status().state is LiveState.ERROR, timeout=3.0)
        service.stop()
        # Tua đồng hồ: người dùng thật bật lại sau vài chục giây, không phải sau 10 ms. Không tua
        # thì test vô nghĩa (mốc rò cũ cách hiện tại ~0 s < mọi ngưỡng).
        service._read_error_since = time.monotonic() - 30.0

        # Phiên B: nguồn chỉ trượt 1 lần rồi chạy bình thường — phải KHỎE. Ngưỡng give-up trả về
        # mặc định để test đo đúng thứ cần đo (rò `_read_error_since`), không phải ngưỡng 0.
        monkeypatch.setattr(live_module, "_READ_ERROR_GIVE_UP_S", 5.0)
        healthy = _FailThenWorkSource(raises=1)
        service._make_source = lambda *a, **k: healthy      # noqa: SLF001 — test bơm nguồn giả
        service.start("0")
        try:
            assert _wait(lambda: service.status().frames >= 1, timeout=3.0), service.status()
            assert service.status().state is LiveState.RUNNING
            assert service._read_errors == 0
        finally:
            service.stop()

    def test_bo_dem_ve_0_ngay_ca_khi_phien_moi_loi_dung_mot_lan(self, monkeypatch):
        """`_read_errors = 0` trong `start()` phải được GHIM (review vòng 4, P3-4).

        Nguồn phiên B lỗi **đúng một lần** rồi không trả frame nữa: nếu bộ đếm rò từ phiên A (đã có
        ≥ 1 lần lỗi) thì con số sau lần lỗi đầu tiên của B là **≥ 2**, còn đúng phải là **1**. Không
        dùng nguồn "không bao giờ lỗi" vì `_read_safely` tự reset khi đọc THÀNH CÔNG ⇒ test sẽ xanh
        vô nghĩa.
        """
        from src.api import live as live_module
        from src.api.live import LiveStreamService

        class _MotLanRoiIm:
            def __init__(self, *args, **kwargs):
                self.da = 0
                self.stopped = False

            def start(self):
                pass

            def read_jpeg(self):
                self.da += 1
                if self.da == 1:
                    raise RuntimeError("lỗi tạm thời")
                # Chặn (như `read()` của V4L2 đang chờ) để KHÔNG có lần đọc thành công nào ⇒ bộ đếm
                # không được reset bởi đường khác, chỉ có `start()` mới reset được nó.
                time.sleep(2.0)
                return None

            def stop(self):
                self.stopped = True

            @property
            def label(self):
                return "giả:một-lần"

        monkeypatch.setattr(live_module, "_READ_ERROR_GIVE_UP_S", 0.0)
        service = LiveStreamService(lambda *a, **k: _AlwaysFailingSource(), target_fps=50)
        service.start("0")
        assert _wait(lambda: service.status().state is LiveState.ERROR, timeout=3.0)
        service.stop()
        assert service._read_errors >= 1

        monkeypatch.setattr(live_module, "_READ_ERROR_GIVE_UP_S", 5.0)
        dich = _MotLanRoiIm()
        service._make_source = lambda *a, **k: dich       # noqa: SLF001 — nguồn giả
        service.start("0")
        try:
            assert _wait(lambda: dich.da >= 1, timeout=3.0)
            assert _wait(lambda: service._read_errors >= 1, timeout=2.0)
            assert service._read_errors == 1, (
                f"bộ đếm lỗi đọc rò từ phiên trước: {service._read_errors} (đúng phải là 1)")
        finally:
            service.stop()

    def test_give_up_dong_nguon_de_lan_sau_mo_duoc(self, monkeypatch):
        """Đóng nguồn ngay khi give-up (như `_check_health`) — nếu không, thiết bị bị giữ."""
        from src.api import live as live_module
        from src.api.live import LiveStreamService

        monkeypatch.setattr(live_module, "_READ_ERROR_GIVE_UP_S", 0.0)
        source = _AlwaysFailingSource()
        service = LiveStreamService(lambda *a, **k: source, target_fps=50)
        service.start("0")
        try:
            assert _wait(lambda: source.stopped, timeout=3.0), "give-up phải đóng nguồn"
        finally:
            service.stop()
