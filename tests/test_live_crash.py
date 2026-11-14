"""Việc #2 của plan: **crash phải trở thành `state=error`, không được giả dạng "người dùng bấm Dừng"**.

Bối cảnh (plan 14-11, mục #2): trước bản này, ngoại lệ ở luồng chính của `LiveTrackingSession`
(`open_video_source(...).open()`, `engine.start()` với ô chọn xấu, `read()` ném, `_annotate`) thoát
khỏi vòng lặp rồi `finally` ghi `state = stopped` ⇒ API trả "worker đã kết thúc phiên", UI hiện như
một phiên kết thúc bình thường. Đó là ca tệ nhất có thể xảy ra trước hội đồng và chi phí sửa = 0 ms.

Ba hành vi được ghim ở đây:
1. ngoại lệ ở luồng chính ⇒ `status.json` + `stats.state` = `error`, message nói lỗi từ đâu;
2. `worker_source.health()` phân biệt "thoát mã 0" (người dùng dừng) với "thoát mã ≠ 0" (chết);
3. `_rewind()` chỉ mở lại nguồn **có điểm kết thúc** — không bao giờ mở lại webcam/HTTP giữa phiên.
"""

import json

import numpy as np
import pytest

from src.live_tracking import BBOX_NAME, STATE_ERROR, STATE_STOPPED, LiveTrackConfig
from src.live_tracking import LiveTrackingSession


class _Result:
    def __init__(self, frame_idx, bbox, mask):
        self.frame_idx = frame_idx
        self.bbox = bbox
        self.mask = mask
        self.elapsed_ms = 5.0


class _FakeEngine:
    """Engine tối thiểu: `start` có thể được cho ném (mô phỏng ô chọn xấu)."""

    def __init__(self, start_exc=None):
        self._start_exc = start_exc

    def start(self, frame, bbox):
        if self._start_exc is not None:
            raise self._start_exc
        x1, y1, x2, y2 = (int(v) for v in bbox)
        mask = np.zeros(frame.shape[:2], bool)
        mask[y1:y2, x1:x2] = True
        return _Result(0, (x1, y1, x2, y2), mask)

    def process(self, frame):
        return _Result(1, (0, 0, 4, 4), np.zeros(frame.shape[:2], bool))


class _StopAfter:
    def __init__(self, checks):
        self._left = checks

    def is_set(self):
        self._left -= 1
        return self._left <= 0


def _pre_select(out_dir, bbox=(2, 2, 8, 8)):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / BBOX_NAME).write_text(
        json.dumps({"x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3]}), encoding="utf-8"
    )


@pytest.fixture
def video_source(write_video, tmp_path):
    frames = np.full((6, 32, 48, 3), 90, np.uint8)
    return str(write_video(tmp_path / "live.mp4", frames, fps=10))


def _config(source, tmp_path, **kwargs):
    return LiveTrackConfig(source=source, out_dir=tmp_path / "live", display_fps=100,
                           vos_every=1, **kwargs)


def _status(tmp_path):
    return json.loads((tmp_path / "live" / "status.json").read_text(encoding="utf-8"))


class TestNgoaiLeThanhError:
    def test_o_chon_xau_lam_engine_start_nem_thi_la_error(self, video_source, tmp_path):
        """Ca thật: bbox.json hỏng/hộp cao âm ⇒ `engine.start()` ném. Trước đây báo `stopped`."""
        _pre_select(tmp_path / "live")
        session = LiveTrackingSession(_FakeEngine(RuntimeError("box rỗng")), _config(video_source, tmp_path))

        stats = session.run(stop_event=_StopAfter(10))

        status = _status(tmp_path)
        assert status["state"] == STATE_ERROR, "crash mà báo 'stopped' là nói dối người vận hành"
        assert "lỗi trong vòng lặp chính" in status["message"]
        assert "box rỗng" in status["message"], "message phải giữ nguyên nhân gốc để đọc log"
        assert stats.state == STATE_ERROR
        assert stats.state != STATE_STOPPED

    def test_mo_nguon_nem_thi_error_chu_khong_ket_o_loading(self, tmp_path, monkeypatch):
        """`.open()` ném (thiết bị bận/không tồn tại): trước đây nằm NGOÀI `try` ⇒ không ai ghi
        trạng thái, `status.json` giữ `loading` trong khi tiến trình đã chết."""
        import src.live_tracking as lt

        class _Boom:
            def open(self):
                raise RuntimeError("Device busy")

        monkeypatch.setattr(lt, "open_video_source", lambda *_a, **_k: _Boom())
        config = _config("0", tmp_path)
        stats = LiveTrackingSession(_FakeEngine(), config).run()

        status = _status(tmp_path)
        assert status["state"] == STATE_ERROR
        assert "Device busy" in status["message"]
        assert stats.state == STATE_ERROR

    def test_message_loi_vong_lap_khac_message_loi_luong_vos(self, video_source, tmp_path):
        """Hai nguồn lỗi phải phân biệt được khi đọc `status.json` (không gộp thành một câu)."""
        _pre_select(tmp_path / "live")
        stats = LiveTrackingSession(_FakeEngine(RuntimeError("x")), _config(video_source, tmp_path)).run(
            stop_event=_StopAfter(10)
        )

        assert "vòng lặp chính" in _status(tmp_path)["message"]
        assert "luồng VOS" not in _status(tmp_path)["message"]
        assert stats.state == STATE_ERROR


class TestLoiDauTienThang:
    def test_loi_thu_hai_khong_ghi_de_message_cua_loi_dau(self, video_source, tmp_path):
        """Luồng chính và luồng VOS có thể cùng chết; `status.json` phải nêu NGUỒN GỐC đầu tiên."""
        _pre_select(tmp_path / "live")
        session = LiveTrackingSession(_FakeEngine(), _config(video_source, tmp_path))
        session._set_error(RuntimeError("nguồn mất"), "lỗi trong vòng lặp chính")
        session._set_error(RuntimeError("OOM"), "model lỗi trong luồng VOS")
        assert "nguồn mất" in session._stats.message
        assert "OOM" not in session._stats.message
        assert session._stats.state == STATE_ERROR


class TestRewindChiChoNguonCoDiemKetThuc:
    def test_read_none_tren_nguon_kieu_camera_khong_mo_lai_thiet_bi(self, tmp_path, monkeypatch):
        """Webcam/RTSP/HTTP: `read()` trả None **không** được mở lại nguồn.

        Mở lại giữa phiên là bắn vào chân: relay/`usbipd` còn giữ thiết bị ⇒ "Device busy" và phiên
        đang khoẻ chết theo (AGENTS §6). Đếm số lần `open()` để chứng minh.
        """
        import src.live_tracking as lt

        opens = {"n": 0}

        class _DeadCamera:
            def read(self):
                return None                      # mất tín hiệu, KHÔNG phải hết video

            def open(self):
                opens["n"] += 1
                return self

            def close(self):
                pass

        monkeypatch.setattr(lt, "open_video_source", lambda *_a, **_k: _DeadCamera())
        session = LiveTrackingSession(_FakeEngine(), _config("http://relay/snapshot.jpg", tmp_path))
        stats = session.run(stop_event=_StopAfter(20))

        assert opens["n"] == 1, "nguồn kiểu camera bị mở lại ⇒ nguy cơ 'Device busy'"
        assert stats.frames == 0
        # Hết tín hiệu ở nguồn KHÔNG phải lỗi của phiên: worker kết thúc bình thường (mã 0),
        # watchdog ở `raw` mới là nơi báo lỗi cho ca này.
        assert stats.state == STATE_STOPPED

    def test_file_van_duoc_lap_lai(self, video_source, tmp_path):
        """Hồi quy: guard mới không được tắt tính năng lặp file (demo bằng video)."""
        out = tmp_path / "live"
        _pre_select(out)
        stats = LiveTrackingSession(_FakeEngine(), _config(video_source, tmp_path, loop_files=True)).run(
            stop_event=_StopAfter(25)
        )
        assert stats.frames >= 10, "file 6 frame phải lặp lại, không dừng sau vòng đầu"

    def test_loop_files_false_thi_khong_lap(self, video_source, tmp_path):
        out = tmp_path / "live"
        _pre_select(out)
        stats = LiveTrackingSession(_FakeEngine(), _config(video_source, tmp_path)).run(
            stop_event=_StopAfter(25)
        )
        assert stats.frames >= 1
        stats = LiveTrackingSession(_FakeEngine(), _config(video_source, tmp_path, loop_files=False)).run(
            stop_event=_StopAfter(200)
        )
        assert stats.frames <= 6


class TestLooksLikeFile:
    """Một định nghĩa duy nhất dùng cho cả đường `track` và `raw` (`src/video_source.py`)."""

    @pytest.mark.parametrize("source", ["0", 0, "1", " 2 "])
    def test_chi_so_camera(self, source):
        from src.video_source import looks_like_file

        assert looks_like_file(source) is False

    @pytest.mark.parametrize("source", [
        "rtsp://cam/stream", "http://relay/snapshot.jpg", "https://x/y.mjpg",
    ])
    def test_nguon_mang(self, source):
        from src.video_source import looks_like_file

        assert looks_like_file(source) is False

    def test_chuoi_so_nhung_CO_file_that_trung_ten_thi_la_file(self, tmp_path, monkeypatch):
        """Ngoại lệ có chủ đích của factory: một file tên `0` là đường dẫn hợp lệ (AGENTS §6).

        Thiếu test này thì lần sau ai "dọn gọn" điều kiện `not os.path.exists(...)` cũng không ai
        biết — và web gửi chuỗi `"0"` sẽ mở nhầm file trong repo thay vì webcam (hoặc ngược lại).
        """
        from src.video_source import looks_like_file

        (tmp_path / "0").write_bytes(b"x")
        monkeypatch.chdir(tmp_path)
        assert looks_like_file("0") is True
        (tmp_path / "1").mkdir()
        assert looks_like_file("1") is True

    def test_file_va_thu_muc(self, tmp_path):
        from src.video_source import looks_like_file

        clip = tmp_path / "a.mp4"
        clip.write_bytes(b"x")
        assert looks_like_file(str(clip)) is True
        assert looks_like_file(str(tmp_path)) is True          # dãy ảnh (FramesVideoSource)
        assert looks_like_file(str(tmp_path / "chua_co.mp4")) is True   # chưa tồn tại nhưng đúng đuôi


class TestHealthPhanBietMaThoat:
    """`worker_source.health()`: `state=stopped` do `finally` ghi KHÔNG đủ để kết luận "bình thường"."""

    def _source(self, tmp_path, code):
        from src.api.adapters.worker_source import WorkerFrameSource

        class _Proc:
            pid = 999999

            def poll(self):
                return code

        source = WorkerFrameSource("0", out_dir=tmp_path)
        source._proc = _Proc()
        return source

    def _write(self, tmp_path, **fields):
        (tmp_path / "status.json").write_text(json.dumps(fields), encoding="utf-8")
        (tmp_path / "frame.jpg").write_bytes(b"\xff\xd8fake")

    def test_thoat_ma_0_thi_stopped(self, tmp_path):
        from src.api.domain import LiveState

        self._write(tmp_path, state="stopped")
        health = self._source(tmp_path, 0).health()
        assert health is not None and health.state is LiveState.STOPPED

    def test_thoat_ma_khac_0_du_status_ghi_stopped_van_la_error(self, tmp_path):
        from src.api.domain import LiveState

        self._write(tmp_path, state="stopped")      # chính crash cũng đi qua nhánh `stopped`
        health = self._source(tmp_path, 1).health()
        assert health is not None and health.state is LiveState.ERROR
        assert "(mã 1)" in health.message

    def test_status_ghi_error_du_tien_trinh_con_song_van_la_error(self, tmp_path):
        from src.api.domain import LiveState

        self._write(tmp_path, state="error", message="lỗi trong vòng lặp chính: box rỗng")
        source = self._source(tmp_path, 0)
        # còn sống (poll None) nhưng worker đã tự báo lỗi
        source._proc = type("P", (), {"pid": 1, "poll": lambda self: None})()
        health = source.health()
        assert health is not None and health.state is LiveState.ERROR
        assert "box rỗng" in health.message


class TestWorkerTraMaThoat:
    def test_worker_tra_ma_1_khi_phien_ket_thuc_vi_loi(self):
        """Mã thoát là tín hiệu DUY NHẤT còn lại cho phụ huynh (systemd/runner/test)."""
        from src.live_tracking import session_exit_code, LiveTrackStats

        assert session_exit_code(LiveTrackStats(state=STATE_ERROR)) == 1
        assert session_exit_code(LiveTrackStats(state=STATE_STOPPED)) == 0
        assert session_exit_code(LiveTrackStats()) == 0
