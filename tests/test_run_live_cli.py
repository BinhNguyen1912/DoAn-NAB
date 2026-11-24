"""Test CLI `tools/run_live.py` — argparse + precedence config/CLI + xuất artefacts (ticket 08).

Vì sao có file này: 3 bug của phiên implement 08 nằm đúng ở CLI (đọc source_fps sau
peek.close(); source bị validate sai kiểu; precedence config/CLI) và chỉ lộ ra khi chạy
smoke thật ~90s. Test này khoá lại toàn bộ lớp đó trong ~1.5s bằng FakeEngine (không model,
không cần `sam2` — CLI import sam2 trong khối có bảo vệ).
"""
import csv
import json
import sys
import textwrap

import cv2
import numpy as np
import pytest

from src.prompt_selector import PromptSelector
from src.synthetic_video import generate_tracking_sequence
from src.tracker_engine import TrackingResult
import tools.run_live as run_live


class FakeEngine:
    """Engine giả thay TrackerEngine.build_default — CLI không cần model/checkpoint thật."""

    def __init__(self, *a, **kw):
        self._idx = -1

    def start(self, frame, bbox):
        self._idx = 0
        return self._res(0)

    def process(self, frame):
        self._idx += 1
        return self._res(self._idx)

    def reset(self):
        self._idx = -1

    def _res(self, i):
        x = 60 + 4 * i
        mask = np.zeros((240, 320), dtype=bool)
        mask[60:100, x:x + 40] = True
        return TrackingResult(frame_idx=i, mask=mask, bbox=(x, 60, x + 40, 100),
                             score=0.9, elapsed_ms=50.0)


@pytest.fixture
def video(tmp_path):
    fx = generate_tracking_sequence(num_frames=4, frame_size=(240, 320),
                                    square_size=40, start=(60, 60))
    path = tmp_path / "seq.avi"
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 240))
    for f in fx.frames:
        out.write(f)
    out.release()
    return str(path)


@pytest.fixture
def fake_engine(monkeypatch):
    """build_default trả FakeEngine (checkpoint/model_cfg vẫn đi qua resolve thật)."""
    monkeypatch.setattr(
        run_live.TrackerEngine, "build_default",
        classmethod(lambda cls, **kw: FakeEngine()),
    )


class TestThietBiXuongEngine:
    """Mắt xích CUỐI của chuỗi GPU: `--device` phải tới `TrackerEngine.build_default(device=…)`.

    Fixture `fake_engine` ở trên nuốt mọi kwarg ⇒ xoá `device=device` trong `run_live.py` (đúng lỗi
    `live_worker.py` đã mắc) mà **toàn bộ** test vẫn xanh ⇒ job upload chạy CPU im lặng trên máy GPU
    (P2 review 10-11). Test này khoá đúng kwarg đó.
    """

    def _bat_kwargs(self, monkeypatch, *, cuda: bool):
        import torch

        ghi = {}

        def build_default(**kwargs):
            ghi.update(kwargs)
            return FakeEngine()

        monkeypatch.setattr(run_live.TrackerEngine, "build_default", staticmethod(build_default))
        # KHÔNG cần checkpoint thật: test này chỉ khoá kwarg `device` tới `build_default`, mà
        # `build_default` đã bị thay bằng engine giả. CI (ubuntu) không có
        # `samurai/sam2/checkpoints/*.pt` (bị .gitignore) nên trước đây 3 test này **đổ** ở làn nhanh
        # (`FileNotFoundError: Checkpoint không tồn tại`) ⇒ CI đỏ từ 10-11. Bỏ phép "file phải tồn tại"
        # ở đây là đúng phạm vi: đường resolve thật vẫn có test riêng trong `tests/test_config.py`.
        monkeypatch.setattr(run_live, "resolve_checkpoint", lambda checkpoint: str(checkpoint))
        monkeypatch.setattr(torch.cuda, "is_available", lambda: cuda)
        monkeypatch.setattr(torch.cuda, "get_device_name", lambda _i: "GPU giả")
        return ghi

    def test_device_cuda_truyen_xuong_engine(self, tmp_path, video, monkeypatch):
        ghi = self._bat_kwargs(monkeypatch, cuda=True)
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--source", video,
                                          "--max-frames", "1", "--device", "cuda"])
        run_live.main()
        assert ghi["device"] == "cuda", "thiếu device ⇒ máy GPU vẫn chạy CPU (lỗi 10-11)"

    def test_mac_dinh_la_cpu(self, tmp_path, video, monkeypatch):
        ghi = self._bat_kwargs(monkeypatch, cuda=False)
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--source", video, "--max-frames", "1"])
        run_live.main()
        assert ghi["device"] == "cpu"

    def test_run_info_ghi_thiet_be_da_dung(self, tmp_path, video, monkeypatch):
        """`resources.gpu` chỉ nói "MÁY có GPU"; artifact phải ghi thiết bị ĐÃ DÙNG."""
        self._bat_kwargs(monkeypatch, cuda=False)
        info = tmp_path / "run_info.json"
        monkeypatch.setattr(sys, "argv", [
            "run_live.py", "--source", video, "--max-frames", "1",
            "--metrics-csv", str(tmp_path / "m.csv"),
            "--metrics-summary", str(tmp_path / "s.json")])
        monkeypatch.setattr(run_live, "run_info_path_for", lambda *a, **k: str(info))
        run_live.main()
        data = json.loads(info.read_text(encoding="utf-8"))
        assert data["device"] == "cpu", "artifact job không ghi thiết bị ⇒ dễ bị trích như số GPU"


def _write_cfg(tmp_path, text):
    """Ghi config YAML tạm — dedent để test viết YAML thụt lề tự nhiên."""
    path = tmp_path / "cfg.yaml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(path)


class TestHeadlessArtefacts:
    def test_yaml_bat_ghi_metrics_va_mp4_ra_du_artefact(self, tmp_path, video, fake_engine,
                                                       monkeypatch):
        """1 lệnh headless qua YAML → mp4 + CSV + summary JSON (tiêu chí 1 ticket 08)."""
        rec = tmp_path / "out.mp4"
        csv_out = tmp_path / "metrics.csv"
        js_out = tmp_path / "summary.json"
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}          # engine là fake — resolve chỉ cần file tồn tại
source: {video}
record_enabled: true
record_path: {rec}
metrics_csv: {csv_out}
metrics_summary: {js_out}
max_frames: 4
""")
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])
        run_live.main()

        assert rec.is_file(), "record_enabled qua YAML phải bật ghi mp4"
        assert csv_out.is_file() and js_out.is_file()

        rows = list(csv.reader(open(csv_out, encoding="utf-8")))
        assert len(rows) == 5, "header + 4 frame"
        s = json.loads(js_out.read_text(encoding="utf-8"))
        assert s["total_frames"] == 4 and s["mean_latency_ms"] == pytest.approx(50.0)

        cap = cv2.VideoCapture(str(rec))
        n = 0
        while cap.read()[0]:
            n += 1
        cap.release()
        assert n == 4

    def test_cli_de_yaml_ghi_video(self, tmp_path, video, fake_engine, monkeypatch):
        """--record (CLI) thắng record_path trong YAML."""
        yaml_rec = tmp_path / "yaml.mp4"
        cli_rec = tmp_path / "cli.mp4"
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}
source: {video}
record_enabled: true
record_path: {yaml_rec}
max_frames: 2
""")
        monkeypatch.setattr(sys, "argv",
                            ["run_live.py", "--config", cfg, "--record", str(cli_rec)])
        run_live.main()
        assert cli_rec.is_file() and not yaml_rec.exists()

    def test_yaml_tat_ghi_thi_khong_tao_file(self, tmp_path, video, fake_engine, monkeypatch):
        """record_enabled: false (mặc định) → không ghi mp4 ngoài ý muốn."""
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}
source: {video}
max_frames: 2
""")
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])
        run_live.main()
        assert not list(tmp_path.glob("*.mp4"))


class TestConfigErrors:
    def test_source_null_bao_loi_roi_thoat_ma_1(self, tmp_path, video, fake_engine,
                                                monkeypatch, capsys):
        """source: null trong YAML → thông báo hướng dẫn + exit code 1 (không traceback)."""
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}
source: null
""")
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])
        with pytest.raises(SystemExit) as exc:
            run_live.main()
        assert exc.value.code == 1
        assert "chưa chỉ định nguồn" in capsys.readouterr().out

    def test_max_frames_tu_yaml_duoc_ap(self, tmp_path, video, fake_engine, monkeypatch):
        """max_frames trong YAML giới hạn đúng số frame (không cần truyền CLI)."""
        csv_out = tmp_path / "m.csv"
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}
source: {video}
max_frames: 2
metrics_csv: {csv_out}
""")
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])
        run_live.main()
        rows = list(csv.reader(open(csv_out, encoding="utf-8")))
        assert len(rows) == 3, "header + 2 frame (max_frames=2)"


class TestDisplayPath:
    def test_display_wiring_voi_gui_gia(self, tmp_path, video, fake_engine, monkeypatch):
        """--display: kiểm WIRING (setMouseCallback + imshow/waitKey + thoát bằng q).

        Không gọi GUI thật: trong WSL/CI `cv2.namedWindow` gọi thẳng vào backend và
        SIGABRT cả process (không phải exception catch được) — xem CODING_STANDARDS.md:
        mọi test chạm GUI phải giả lập bề mặt cv2. GUI thật kiểm thủ công trên Windows.
        """
        events = {"set_mouse_callback": 0, "imshow": 0, "destroy": 0}

        def fake_set_mouse_callback(win, cb):
            events["set_mouse_callback"] += 1
            assert callable(cb), "phải gắn selector.on_mouse"

        monkeypatch.setattr(run_live.cv2, "namedWindow", lambda *a, **k: None)
        monkeypatch.setattr(run_live.cv2, "setMouseCallback", fake_set_mouse_callback)
        monkeypatch.setattr(run_live.cv2, "imshow",
                            lambda *a, **k: events.__setitem__("imshow", events["imshow"] + 1))
        monkeypatch.setattr(run_live.cv2, "destroyAllWindows",
                            lambda *a, **k: events.__setitem__("destroy", events["destroy"] + 1))
        # q ngay lần đọc phím đầu tiên → vòng lặp thoát sạch, không treo
        monkeypatch.setattr(run_live.cv2, "waitKey", lambda *a, **k: ord("q"))

        cfg = _write_cfg(tmp_path, f"checkpoint: {video}\nsource: {video}\nmax_frames: 1\n")
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg, "--display",
                                          "--bbox", "60,60,40,40"])
        run_live.main()  # không ném SystemExit → thoát sạch

        assert events["set_mouse_callback"] == 1
        assert events["imshow"] >= 1
        assert events["destroy"] == 1  # destroyAllWindows trong finally


class TestPromptSelectorImport:
    def test_module_nap_duoc_va_co_selector(self):
        """Sanity: tools.run_live import đủ dependency cho đường --display."""
        assert PromptSelector is not None
        assert callable(run_live.main)


class InterruptingEngine(FakeEngine):
    """Engine giả ném KeyboardInterrupt ở process thứ N — mô phỏng người dùng bấm Ctrl+C."""

    def __init__(self, fail_at=2):
        super().__init__()
        self._fail_at = fail_at
        self._n = 0

    def process(self, frame):
        self._n += 1
        if self._n >= self._fail_at:
            raise KeyboardInterrupt
        return super().process(frame)


class TestCtrlCFlush:
    """Ctrl+C là đường thoát phổ biến khi demo → KHÔNG được mất metrics đã đo.

    Bug thật gặp khi kiểm GUI (18-10): run `--display --metrics-csv` bấm Ctrl+C →
    mp4 có (recorder đóng trong finally) nhưng CSV/JSON KHÔNG được ghi.
    """

    @pytest.fixture
    def interrupting_engine(self, monkeypatch):
        monkeypatch.setattr(
            run_live.TrackerEngine, "build_default",
            classmethod(lambda cls, **kw: InterruptingEngine(fail_at=2)),
        )

    def test_headless_ctrl_c_van_ghi_metrics_csv(self, tmp_path, video, interrupting_engine,
                                                 monkeypatch, capsys):
        csv_out = tmp_path / "m.csv"
        js_out = tmp_path / "s.json"
        cfg = _write_cfg(tmp_path, f"""
            checkpoint: {video}
            source: {video}
            metrics_csv: {csv_out}
            metrics_summary: {js_out}
            """)
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])

        with pytest.raises(SystemExit) as exc:
            run_live.main()
        assert exc.value.code == 0                    # thoát sạch như tài liệu
        assert "Ctrl+C" in capsys.readouterr().out     # báo cho người dùng

        assert csv_out.is_file(), "metrics đo được phải được ghi cả khi Ctrl+C"
        rows = list(csv.reader(open(csv_out, encoding="utf-8")))
        assert len(rows) == 3, "header + 2 frame đã track trước khi ngắt"
        assert js_out.is_file()

    def test_ctrl_c_trong_khi_chuyen_ma_van_giu_metrics(
            self, tmp_path, video, interrupting_engine, monkeypatch, capsys):
        """P1 review 09-11: Ctrl+C lần hai lúc ffmpeg đang chạy (im lặng) không được làm mất CSV."""
        csv_out = tmp_path / "m.csv"
        js_out = tmp_path / "s.json"
        rec = tmp_path / "demo.mp4"
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}
source: {video}
record_enabled: true
record_path: {rec}
metrics_csv: {csv_out}
metrics_summary: {js_out}
""")
        seen = {}

        def _transcode_luc_nay(*args, **kwargs):
            # Kiểm THỨ TỰ, không chỉ kiểm "có bắt KeyboardInterrupt": phải thấy CSV/JSON ĐÃ CÓ
            # tại thời điểm chuyển mã (review vòng 2, P3 — nếu đảo thứ tự mà vẫn catch thì test
            # kiểu cũ vẫn xanh).
            seen["csv"] = csv_out.is_file()
            seen["summary"] = js_out.is_file()
            raise KeyboardInterrupt

        monkeypatch.setattr(run_live, "transcode_for_web", _transcode_luc_nay)
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])

        with pytest.raises(SystemExit):
            run_live.main()

        assert seen["csv"] is True, "số liệu phải được ghi TRƯỚC khi chuyển mã"
        assert seen["summary"] is True
        assert csv_out.is_file(), "Ctrl+C lúc chuyển mã KHÔNG được làm mất CSV"
        assert js_out.is_file()

    def test_display_ctrl_c_van_ghi_metrics_csv(self, tmp_path, video, interrupting_engine,
                                                monkeypatch):
        """Đường --display: Ctrl+C vẫn ghi CSV/JSON + đóng recorder trong finally."""
        rec = tmp_path / "r.mp4"
        csv_out = tmp_path / "m.csv"
        monkeypatch.setattr(run_live.cv2, "namedWindow", lambda *a, **k: None)
        monkeypatch.setattr(run_live.cv2, "setMouseCallback", lambda *a, **k: None)
        monkeypatch.setattr(run_live.cv2, "imshow", lambda *a, **k: None)
        monkeypatch.setattr(run_live.cv2, "destroyAllWindows", lambda *a, **k: None)
        monkeypatch.setattr(run_live.cv2, "waitKey", lambda *a, **k: -1)
        monkeypatch.setattr(run_live.cv2, "getWindowProperty", lambda *a, **k: 1.0)  # cửa sổ còn mở

        cfg = _write_cfg(tmp_path, f"""
            checkpoint: {video}
            source: {video}
            record_enabled: true
            record_path: {rec}
            metrics_csv: {csv_out}
            """)
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg, "--display",
                                          "--bbox", "60,60,40,40"])

        with pytest.raises(SystemExit) as exc:
            run_live.main()
        assert exc.value.code == 0
        assert csv_out.is_file()
        assert rec.is_file() and rec.stat().st_size > 0   # recorder đóng đúng trong finally
        # Provenance đi kèm đường thật main() → ./run fast tự giải thích được lần đo
        assert (tmp_path / "m_run_info.json").is_file()

class TestGhiRunInfoKhiCoMetrics:
    """Lần đo phải tự giải thích được: `_finish_metrics` ghi run_info cạnh summary."""

    def test_ghi_run_info_canh_summary(self, tmp_path):
        from src.metrics_logger import FrameRecord, MetricsLogger
        from tools.run_live import _finish_metrics

        m = MetricsLogger()
        m.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=5.0, center=(10, 10)))
        csv_out = tmp_path / "fast_1_metrics.csv"
        js_out = tmp_path / "fast_1_summary.json"
        args = type("A", (), {"metrics_csv": str(csv_out), "metrics_summary": str(js_out),
                             "source": "0", "image_size": 256})()
        _finish_metrics(m, args)

        info_path = tmp_path / "fast_1_run_info.json"
        assert info_path.is_file()
        d = json.loads(info_path.read_text(encoding="utf-8"))
        assert d["source"] == "0"
        assert d["image_size"] == 256
        assert "git_rev" in d

    def test_args_thieu_thuoc_tinh_khong_crash(self, tmp_path):
        # args tối thiểu (chỉ có đường dẫn) vẫn phải ghi được run_info, không AttributeError
        from src.metrics_logger import FrameRecord, MetricsLogger
        from tools.run_live import _finish_metrics

        m = MetricsLogger()
        m.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=5.0, center=(10, 10)))
        csv_out = tmp_path / "x_metrics.csv"
        js_out = tmp_path / "x_summary.json"
        args = type("A", (), {"metrics_csv": str(csv_out), "metrics_summary": str(js_out)})()
        _finish_metrics(m, args)
        assert (tmp_path / "x_run_info.json").is_file()


class TestXuatBanWeb:
    """`--record` ghi mp4v (OpenCV chỉ có codec đó) — Chrome/Edge KHÔNG giải mã được.

    Đo 08-11 bằng Chrome headless thật: `canPlayType('video/mp4; codecs="mp4v.20.9"')` trả `""`,
    `videoWidth = 0`. Video demo mở bằng trình duyệt là màn hình đen ⇒ sau khi đóng recorder phải
    xuất bản H.264 cạnh file gốc (dùng đúng `src/worker/web_export.py` mà API đã dùng).
    """

    def test_ghi_video_xong_thi_xuat_ban_h264_canh_file_goc(self, tmp_path, video, fake_engine,
                                                           monkeypatch):
        rec = tmp_path / "demo.mp4"
        calls = {}

        def fake_transcode(src, dst=None, **kwargs):
            calls["src"], calls["dst"] = str(src), str(dst)
            # Recorder phải được ĐÓNG trước khi chuyển mã, nếu không moov box chưa ghi xong và
            # `cv2.VideoCapture` không đọc nổi frame nào. Đây là bằng chứng cho "thứ tự quan trọng".
            probe = cv2.VideoCapture(str(src))
            try:
                calls["doc_duoc_frame"] = probe.read()[0]
            finally:
                probe.release()
            with open(dst, "wb") as handle:
                handle.write(b"h264")
            return str(dst)

        monkeypatch.setattr(run_live, "transcode_for_web", fake_transcode)
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}
source: {video}
record_enabled: true
record_path: {rec}
max_frames: 2
""")
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])
        run_live.main()

        assert calls["src"] == str(rec)
        assert calls["dst"] == str(tmp_path / "demo_web.mp4")
        assert (tmp_path / "demo_web.mp4").is_file()
        assert rec.is_file(), "file gốc phải còn (bản web chỉ là bản chuyển mã thêm)"
        assert calls["doc_duoc_frame"] is True, "phải đóng recorder trước khi chuyển mã"

    def test_khong_co_ffmpeg_thi_canh_bao_ro_rang_ma_khong_no(self, tmp_path, video, fake_engine,
                                                            monkeypatch, capsys):
        monkeypatch.setattr(run_live, "transcode_for_web", lambda *a, **k: None)
        monkeypatch.setattr(run_live, "find_ffmpeg", lambda: None)   # máy này CÓ ffmpeg — phải giả lập
        rec = tmp_path / "demo.mp4"
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}
source: {video}
record_enabled: true
record_path: {rec}
max_frames: 2
""")
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])
        run_live.main()                       # không được ném: video gốc đã ghi xong rồi

        out = capsys.readouterr().out
        assert "không có ffmpeg" in out and "imageio-ffmpeg" in out
        assert rec.is_file()

    def test_chuyen_ma_that_bai_ma_co_ffmpeg_thi_khong_do_loi_cho_thieu_ffmpeg(
            self, tmp_path, video, fake_engine, monkeypatch, capsys):
        """`transcode_for_web` trả None vì 5 lý do — chỉ lý do "không có ffmpeg" mới được báo là thiếu."""
        monkeypatch.setattr(run_live, "transcode_for_web", lambda *a, **k: None)
        monkeypatch.setattr(run_live, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
        rec = tmp_path / "demo.mp4"
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}
source: {video}
record_enabled: true
record_path: {rec}
max_frames: 2
""")
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])
        run_live.main()

        out = capsys.readouterr().out
        assert "chuyển mã H.264 thất bại" in out
        assert "không có ffmpeg" not in out

    def test_duong_dan_ban_web_luon_la_mp4_va_khong_phai_file_goc(self):
        """`--record demo.avi` ⇒ `demo_web.mp4`: H.264 trong AVI thì Chrome vẫn không phát được."""
        from tools.run_live import _web_record_path

        assert _web_record_path("demo.avi").name == "demo_web.mp4"
        assert _web_record_path("data/x.mkv").name == "x_web.mp4"
        assert str(_web_record_path("demo.mp4")) != "demo.mp4"

    def test_recorder_khong_mo_duoc_thi_khong_chuyen_ma(
            self, tmp_path, monkeypatch, capsys):
        """P2 review 09-11: `--record` mở lỗi + file cùng tên từ lần trước còn đó ⇒ không được
        chuyển mã bản CŨ rồi báo "phát được trên Chrome" (thành công giả)."""
        called = []
        monkeypatch.setattr(run_live, "transcode_for_web", lambda *a, **k: called.append(a) or None)
        viz = run_live._make_visualizer(type("A", (), {"record": str(tmp_path / "x.mp4"),
                                                      "max_trajectory": 10,
                                                      "show_trajectory": True})())
        assert viz.recording is False          # chưa ghi frame nào ⇒ chưa mở writer

        run_live._finish_recording(viz, type("A", (), {"record": str(tmp_path / "x.mp4")})())
        assert called == [], "không được chuyển mã khi chưa ghi được frame nào"

    def test_khong_bat_ghi_thi_khong_goi_chuyen_ma(self, tmp_path, video, fake_engine, monkeypatch):
        called = []
        monkeypatch.setattr(run_live, "transcode_for_web",
                            lambda *a, **k: called.append(a) or None)
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}
source: {video}
max_frames: 2
""")
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])
        run_live.main()
        assert called == []

    def test_that_su_ra_h264_phat_duoc_bang_opencv(self, tmp_path, video, fake_engine, monkeypatch):
        """Test thật (cần ffmpeg): 4 cc của file web phải là `avc1`, không phải `mp4v`."""
        from src.worker.web_export import find_ffmpeg

        if not find_ffmpeg():
            pytest.skip("chưa có ffmpeg — cài `pip install imageio-ffmpeg` (requirements.txt)")
        rec = tmp_path / "demo.mp4"
        cfg = _write_cfg(tmp_path, f"""
checkpoint: {video}
source: {video}
record_enabled: true
record_path: {rec}
max_frames: 2
""")
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg])
        run_live.main()

        web = tmp_path / "demo_web.mp4"
        assert web.is_file(), "phải có bản H.264 cạnh file gốc"
        cap = cv2.VideoCapture(str(web))
        try:
            assert cap.isOpened()
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            # Tag phải KHÔNG phải `mp4v` — đó chính là codec Chrome không giải mã được (đo 08-11:
            # `canPlayType("video/mp4; codecs=\"mp4v.20.9\"") = ""`, `videoWidth = 0`).
            # OpenCV báo tên codec (`h264`); ffmpeg -i trên cùng file cho `h264 (High) (avc1 …)` +
            # `yuv420p` — chấp nhận cả ba tag, chỉ cấm `mp4v`.
            tag = fourcc.to_bytes(4, "little").decode("latin1")   # OpenCV trả int little-endian
            assert tag in {"avc1", "avc3", "h264"}, tag
            assert tag != "mp4v"
        finally:
            cap.release()


class TestKhongGhiDeKhiLoi:
    """Bug 21-10: mở camera lỗi → phiên 0 frame vẫn ghi CSV/JSON rỗng, đè mất số liệu tốt."""

    def test_phien_0_frame_khong_ghi_file(self, tmp_path):
        from src.metrics_logger import MetricsLogger
        from tools.run_live import _finish_metrics

        csv_out = tmp_path / "m.csv"
        js_out = tmp_path / "s.json"
        existing = tmp_path / "m.csv"
        existing.write_text("frame_idx,latency_ms\n0,123\n")     # số liệu tốt của lần trước

        args = type("A", (), {"metrics_csv": str(csv_out), "metrics_summary": str(js_out)})()
        _finish_metrics(MetricsLogger(), args)                   # logger rỗng

        assert csv_out.read_text() == "frame_idx,latency_ms\n0,123\n"   # còn nguyên
        assert not js_out.exists()


class TestDongCuaSoBangX:
    """Bug 21-10: bấm X trên cửa sổ OpenCV → process vẫn chạy mãi, phải kill tay."""

    def test_cua_so_bi_dong_tra_true(self, monkeypatch):
        import tools.run_live as rl

        monkeypatch.setattr(rl.cv2, "getWindowProperty", lambda *a, **k: 0.0)
        assert rl._window_closed("w") is True

    def test_cua_so_con_mo_tra_false(self, monkeypatch):
        import tools.run_live as rl

        monkeypatch.setattr(rl.cv2, "getWindowProperty", lambda *a, **k: 1.0)
        assert rl._window_closed("w") is False

    def test_cua_so_da_huy_khong_crash(self, monkeypatch):
        import tools.run_live as rl

        def boom(*a, **k):
            raise rl.cv2.error("window destroyed")

        monkeypatch.setattr(rl.cv2, "getWindowProperty", boom)
        assert rl._window_closed("w") is True

    def test_display_tra_quit_key_khi_cua_so_dong(self, tmp_path, video, fake_engine, monkeypatch):
        """on_display phải trả phím thoát để vòng lặp kết thúc (không treo process)."""
        import tools.run_live as rl
        from src.live_pipeline import QUIT_KEYS

        monkeypatch.setattr(rl.cv2, "namedWindow", lambda *a, **k: None)
        monkeypatch.setattr(rl.cv2, "setMouseCallback", lambda *a, **k: None)
        monkeypatch.setattr(rl.cv2, "imshow", lambda *a, **k: None)
        monkeypatch.setattr(rl.cv2, "destroyAllWindows", lambda *a, **k: None)
        monkeypatch.setattr(rl.cv2, "waitKey", lambda *a, **k: -1)
        monkeypatch.setattr(rl.cv2, "getWindowProperty", lambda *a, **k: 0.0)  # X bị bấm

        cfg = _write_cfg(tmp_path, f"""
            checkpoint: {video}
            source: {video}
            max_frames: 1
            """)
        monkeypatch.setattr(sys, "argv", ["run_live.py", "--config", cfg, "--display",
                                          "--bbox", "60,60,40,40"])
        run_live.main()          # không được treo
        assert list(QUIT_KEYS)      # sanity


class TestKhongNuotLoiBangUnboundLocalError:
    """P1 review vòng 2 (21-11): `reid_session` chưa khởi tạo trước `try` ⇒ `finally` ném

    `UnboundLocalError`, che lỗi THẬT và bỏ `cv2.destroyAllWindows()`.

    Ca thật: `--reid --reid-cue face` thiếu model (`models/` bị gitignore ⇒ clone mới) ném
    `SystemExit(1)` từ `_make_reid_session` — tức là lỗi có hướng dẫn, nhưng người dùng chỉ thấy
    traceback `UnboundLocalError`. Test này khoá đúng ca đó.
    """

    def _args(self, tmp_path, video, **kw):
        import argparse
        a = argparse.Namespace(
            source=str(video), checkpoint=str(video), device="cpu", image_size=192,
            bbox="10,10,60,60", bbox_file=None, max_frames=1, display=False,
            record=None, record_fps=10, metrics_csv=None, metrics_summary=None,
            reid=True, reid_cue="face", reid_threshold=0.36, lost_after_frames=2,
            reid_min_face_px=40, reid_min_detect_score=0.6, reid_ref_max=8,
            reid_detector_model="models/face/khong_ton_tai_det.onnx",
            reid_recognizer_model="models/face/khong_ton_tai_rec.onnx",
            reid_obj_threshold=0.75, reid_obj_ncc_min=0.4, lost_score_threshold=0.0,
            reid_confirm=2, reid_verify=2, reid_face_veto=True,
            reanchor_every=None, smooth=False, show_trajectory=False,
            hide_trajectory=False, mask_threshold=0.0, max_trajectory=100,
            smooth_display=False, record_enabled=False, record_path=None,
            progress_json=None, progress_total=None,
        )
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def test_thieu_model_mat_thi_bao_loi_huong_dan_khong_phai_unbound(self, tmp_path,
                                                                     video, monkeypatch):
        args = self._args(tmp_path, video)
        monkeypatch.setattr("src.tracker_engine.build_engine", lambda *a, **k: object(),
                            raising=False)
        with pytest.raises(SystemExit) as exc:
            run_live._run_headless(engine=object(), args=args)
        assert exc.value.code == 1          # lỗi THẬT (hướng dẫn tải model), không bị che


class TestKhongNuotLoiOHienThi:
    """P3 review vòng 3: bản vá `reid_session = None` ở `_run_display` không có test.

    Cùng ca với `_run_headless`: `--reid --reid-cue face` thiếu model ⇒ `SystemExit(1)` có hướng
    dẫn. Nếu thiếu dòng khởi tạo thì `finally` ném `UnboundLocalError`, che lỗi và bỏ đóng cửa sổ.
    """

    def test_hien_thi_thieu_model_mat_van_bao_loi_huong_dan(self, tmp_path, video, monkeypatch):
        import argparse
        args = argparse.Namespace(
            source=str(video), device="cpu", image_size=192, bbox="10,10,60,60",
            bbox_file=None, max_frames=1, display=True, record=None, record_fps=10,
            metrics_csv=None, metrics_summary=None, reid=True, reid_cue="face",
            reid_threshold=0.36, lost_after_frames=2, reid_min_face_px=40,
            reid_min_detect_score=0.6, reid_ref_max=8,
            reid_detector_model="models/face/khong_ton_tai_det.onnx",
            reid_recognizer_model="models/face/khong_ton_tai_rec.onnx",
            reid_obj_threshold=0.75, reid_obj_ncc_min=0.4, lost_score_threshold=0.0,
            reid_confirm=2, reid_verify=2, reid_face_veto=True, reanchor_every=None,
            smooth=False, show_trajectory=False, hide_trajectory=False,
            mask_threshold=0.0, max_trajectory=100, smooth_display=False,
            record_enabled=False, record_path=None, progress_json=None, progress_total=None,
        )
        closed = []
        monkeypatch.setattr("tools.run_live.cv2.namedWindow", lambda *a, **k: None)
        monkeypatch.setattr("tools.run_live.cv2.setMouseCallback", lambda *a, **k: None)
        monkeypatch.setattr("tools.run_live.cv2.destroyAllWindows",
                            lambda *a, **k: closed.append(1))
        with pytest.raises(SystemExit) as exc:
            run_live._run_display(engine=object(), args=args)
        assert exc.value.code == 1
        assert closed, "phải đóng cửa sổ kể cả khi lỗi (finally không được ném trước đó)"


class TestGitDirtyCode:
    """AGENTS §6: artifact phải phân biệt "cây bẩn" với "bẩn vì CHÍNH file artifact".

    Đo lại lần hai thì file `data/*_metrics.json` bị sửa ⇒ `git_dirty` luôn `true` vô nghĩa;
    tái lập được ⇔ `git_dirty_code == false` (quy ước `scripts/measure_watchdog.py`).
    """

    def test_bo_qua_thay_doi_trong_data(self, monkeypatch):
        import subprocess as sp
        class R:
            stdout = " M data/veto_demo_metrics.csv\n?? data/anh_tmp/x.jpg\n"
        monkeypatch.setattr(sp, "run", lambda *a, **k: R())
        assert run_live._git_dirty() == (True, False)

    def test_ban_o_code_thi_dirty_code_true(self, monkeypatch):
        import subprocess as sp
        class R:
            stdout = " M data/a.csv\n M src/reid.py\n"
        monkeypatch.setattr(sp, "run", lambda *a, **k: R())
        assert run_live._git_dirty() == (True, True)

    def test_khong_hoi_duoc_git_thi_none(self, monkeypatch):
        import subprocess as sp
        def boom(*a, **k):
            raise OSError("no git")
        monkeypatch.setattr(sp, "run", boom)
        assert run_live._git_dirty() == (None, None)


class TestProvenanceKhongDuocGietPhien:
    """BUG THẬT 21-11 (`demoip_1121-103854`): `_git_dirty()` chạy trong `finally` sau Ctrl+C ⇒

    `subprocess.run` ném **KeyboardInterrupt** ⇒ **mất `run_info.json`** và bản H.264 hỏng
    (`moov atom not found`). Cleanup không bao giờ được ném.
    """

    def test_git_dirty_khong_nem_khi_bi_ctrl_c(self, monkeypatch):
        import subprocess as sp
        def boom(*a, **k):
            raise KeyboardInterrupt
        monkeypatch.setattr(sp, "run", boom)
        assert run_live._git_dirty() == (None, None)

    def test_finish_metrics_van_in_so_lieu_khi_run_info_loi(self, tmp_path, monkeypatch, capsys):
        class FakeMetrics:
            records = [1]

            def write_csv(self, path):
                return str(path)

            def write_summary_json(self, path):
                return str(path)

            def summary(self):
                return {"total_frames": 1, "mean_latency_ms": 100.0, "mean_latency_ms_n": 1,
                        "p95_latency_ms": 110.0, "p95_latency_ms_n": 1, "lost_count": 0,
                        "lost_ratio": 0.0, "mean_score": 1.0, "resources": {}}

        import argparse
        args = argparse.Namespace(metrics_csv=str(tmp_path / "m.csv"),
                                  metrics_summary=None, source="x", device="cpu",
                                  image_size=192, reid=False)

        def boom(_args):
            raise OSError("đĩa hỏng")
        monkeypatch.setattr(run_live, "_write_run_info", boom)
        run_live._finish_metrics(FakeMetrics(), args)      # KHÔNG được ném
        out = capsys.readouterr().out
        assert "run_info" in out and "[metrics]" in out     # vẫn in số liệu cho người dùng


class TestDumpMask:
    """`--dump-mask-frames` (23-11-2026): đường CLI phải xuất được mask để `./run miou` chấm.

    Vì sao cần: chỉ `tools/live_worker.py` (web) có dump mask, còn CLI thì không ⇒ **không chấm
    được** bất kỳ phiên CLI nào, kể cả phiên có Re-ID (đường web không có Re-ID). Đo 23-11: phải có
    mask mới trả lời được "Re-ID nhận lại ĐÚNG vật hay nhận bừa" — mà đó là câu quyết định.
    """

    def _args(self, tmp_path, **kw):
        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"")
        base = {"dump_mask_frames": "0, 30,181", "dump_mask_dir": "",
                "metrics_csv": str(tmp_path / "x.csv"), "source": str(clip),
                "bbox": "1,2,3,4", "bbox_file": None}
        base.update(kw)
        return type("A", (), base)()

    def test_dump_cfg_doi_xuong_thu_muc_canh_metrics_csv(self, tmp_path):
        frames, out_dir = run_live._dump_cfg(self._args(tmp_path))
        assert frames == {0, 30, 181}
        assert out_dir == str(tmp_path / "x_masks")

    def test_dump_mask_tu_choi_nguon_khong_phai_file(self, tmp_path):
        """Webcam/relay/RTSP: số frame là bộ đếm PHIÊN ⇒ mask_NNNNNN.png không ghép được GT nào."""
        for src in ("0", "http://127.0.0.1:8090/snapshot.jpg", "rtsp://cam/s"):
            with pytest.raises(SystemExit):
                run_live._dump_cfg(self._args(tmp_path, source=src))

    def test_dump_mask_bat_buoc_co_bbox_tuong_minh(self, tmp_path):
        """Không có --bbox thì `_load_bbox` im lặng dùng ô giữa 80x80 (bẫy 'hộp mặc định vào nền')."""
        with pytest.raises(SystemExit):
            run_live._dump_cfg(self._args(tmp_path, bbox=None, bbox_file=None))
        frames, _ = run_live._dump_cfg(self._args(tmp_path, bbox=None,
                                                 bbox_file=str(tmp_path / "b.txt")))
        assert frames == {0, 30, 181}

    def test_dump_cfg_tu_choi_khi_sai_dinh_dang(self, tmp_path):
        with pytest.raises(SystemExit):
            run_live._dump_cfg(self._args(tmp_path, dump_mask_frames="0,abc"))

    def test_dump_cfg_tu_choi_so_am(self, tmp_path):
        with pytest.raises(SystemExit):
            run_live._dump_cfg(self._args(tmp_path, dump_mask_frames="0,-3"))

    def test_dump_cfg_can_thu_muc_khi_khong_co_metrics_csv(self, tmp_path):
        with pytest.raises(SystemExit):
            run_live._dump_cfg(self._args(tmp_path, dump_mask_frames="5", metrics_csv=None))

    def test_ghi_dung_frame_va_ten_file_theo_frame_video(self, tmp_path):
        """Tên file phải theo **số frame video**, KHÔNG theo `result.frame_idx` (bài học P0 14-11)."""
        cb = run_live._dump_mask_callback(str(tmp_path), {1, 3}, {"nguon": "x.mp4"}, base=None)
        for n in range(5):
            mask = np.zeros((8, 8), bool)
            mask[0:2, 0:2] = True
            # cố tình cho `frame_idx` LỆCH để bắt bug đặt tên theo engine
            res = TrackingResult(frame_idx=100 + n, mask=mask, bbox=(0, 0, 1, 1), score=1.0, elapsed_ms=1.0)
            assert cb(None, res) is True
        assert sorted(p.name for p in tmp_path.glob("mask_*.png")) == ["mask_000001.png", "mask_000003.png"]
        img = cv2.imread(str(tmp_path / "mask_000001.png"), cv2.IMREAD_GRAYSCALE)
        assert img.max() == 255 and img.min() == 0        # mask nhị phân 0/255

    def test_mask_rong_van_duoc_ghi(self, tmp_path):
        """Mask rỗng = kết quả ĐO ĐƯỢC (phải chấm 0,0 khi GT có vật), không được bỏ qua."""
        cb = run_live._dump_mask_callback(str(tmp_path), {0}, {"nguon": "x.mp4"}, base=None)
        res = TrackingResult(frame_idx=0, mask=np.zeros((8, 8), bool), bbox=(0, 0, 1, 1),
                             score=0.0, elapsed_ms=1.0)
        cb(None, res)
        img = cv2.imread(str(tmp_path / "mask_000000.png"), cv2.IMREAD_GRAYSCALE)
        assert img is not None and img.max() == 0

    def test_none_mask_khong_ghi_file(self, tmp_path):
        cb = run_live._dump_mask_callback(str(tmp_path), {0}, {"nguon": "x.mp4"}, base=None)
        res = TrackingResult(frame_idx=0, mask=None, bbox=(0, 0, 1, 1), score=0.0, elapsed_ms=1.0)
        cb(None, res)
        assert list(tmp_path.glob("mask_*.png")) == []

    def test_manifest_du_khoa_va_khong_ghi_de(self, tmp_path):
        info = {"nguon": "data/binh1.mp4", "image_size": 192, "bbox_xywh": [300, 275, 150, 410]}
        cb = run_live._dump_mask_callback(str(tmp_path), {0, 1}, info, base=None)
        for n in range(2):
            cb(None, TrackingResult(frame_idx=n, mask=np.ones((4, 4), bool), bbox=(0, 0, 1, 1),
                                    score=1.0, elapsed_ms=1.0))
        man = json.loads((tmp_path / "manifest.json").read_text())
        assert man["nguon"] == "data/binh1.mp4"
        assert man["frames_yeu_cau"] == [0, 1] and man["frames_da_ghi"] == [0, 1]
        assert man["so_file_ghi_de"] == 0 and man["frame_goc_cua_phien"] == 0
        # gọi lại: KHÔNG được ghi đè manifest (mask có thể của lần chạy khác)
        cb.write_manifest()
        assert json.loads((tmp_path / "manifest.json").read_text())["frames_da_ghi"] == [0, 1]


def test_no_reid_tat_duoc_reid_ma_run_demoip_luon_chen():
    """`--no-reid` phải THẮNG `--reid` (./run demoip luôn chèn `--reid` trước "$@").

    Không có cờ này thì người dùng không có cách nào chạy demo theo cơ chế "lan truyền liên tục"
    để tự kiểm chứng kết luận 23-11 (re-ID mIoU 0,4236 vs lan truyền 0,7794 trên cùng clip).
    """
    ap = run_live.build_parser()          # parser THẬT của CLI, không phải bản dựng lại trong test
    assert ap.parse_args(["--reid", "--no-reid"]).reid is False
    assert ap.parse_args(["--no-reid"]).reid is False
    assert ap.parse_args(["--reid"]).reid is True
    # thứ tự: cờ SAU thắng (./run demoip đặt `--reid` trước "$@")
    assert ap.parse_args(["--no-reid", "--reid"]).reid is True

def test_mask_0x0_ghi_file_toan_0_khong_giet_phien(tmp_path):
    """P0 tự bắt (23-11): `_lost_result()` trả mask **0×0** ⇒ `cv2.imwrite` NÉM và giết cả phiên đo.

    Lần chạy re-ID trên `data/clip_be2.mp4` dừng ở frame 259/444 mà không có thông báo nào — mất
    nửa sau của clip (đúng đoạn "vật vào lại") mà người đọc artifact không thể biết.
    """
    cb = run_live._dump_mask_callback(str(tmp_path), {0}, {"nguon": "x.mp4"}, base=None)
    res = TrackingResult(frame_idx=0, mask=np.zeros((0, 0), bool), bbox=(0, 0, 0, 0),
                         score=0.0, elapsed_ms=1.0)
    anh = np.zeros((48, 64, 3), np.uint8)
    assert cb(anh, res) is True                      # KHÔNG được ném
    img = cv2.imread(str(tmp_path / "mask_000000.png"), cv2.IMREAD_GRAYSCALE)
    assert img is not None and img.shape == (48, 64) and img.max() == 0


class TestRecordPacingTheoNguon:
    """Ticket #44 — dây nối: `--record` phải bật pacing khi nguồn LIVE, tắt khi nguồn FILE.

    Vì sao cần: unit test trong `test_visualizer` chỉ chốt `_write()` khi cờ đã bật. Nếu
    `_make_visualizer` quên truyền cờ thì phiên live lại ghi 1:1 và video lại ngắn hơn thực 1,5×
    (đúng lỗi đã đo 23-11: 30,76 s thực → 20,83 s file).
    """

    @staticmethod
    def _args(tmp_path, source):
        return type("A", (), {"record": str(tmp_path / "x.mp4"), "max_trajectory": 10,
                              "show_trajectory": True, "source": source})()

    def test_nguon_webcam_bat_pacing(self, tmp_path):
        viz = run_live._make_visualizer(self._args(tmp_path, "0"))
        assert viz._pace_realtime is True
        viz.close_recorder()

    def test_nguon_relay_bat_pacing(self, tmp_path):
        viz = run_live._make_visualizer(
            self._args(tmp_path, "http://172.19.176.1:8090/snapshot.jpg"))
        assert viz._pace_realtime is True
        viz.close_recorder()

    def test_nguon_file_tat_pacing(self, tmp_path):
        viz = run_live._make_visualizer(self._args(tmp_path, "data/binh1.mp4"))
        assert viz._pace_realtime is False
        viz.close_recorder()


class TestProvenanceHieuNang:
    """Ticket #44 — `run_info` phải khai TẢI MÁY lúc đo.

    Vì sao: đo 23-11, cùng một code cho 201–393 ms (±95 %) chỉ vì agent khác chạy `pytest`/`npm`
    (`loadavg` 6,2–8,2). Thiếu `loadavg_1m` thì "model chậm 4×" là kết luận không kiểm được —
    đúng loại lỗi đã xảy ra với tuyên bố "live chậm 1,8× so với file".
    """

    def test_loadavg_va_cpu_count_vao_run_info(self, tmp_path, monkeypatch):
        import json

        monkeypatch.setattr(run_live.os, "getloadavg", lambda: (7.25, 6.0, 5.0), raising=False)
        monkeypatch.setattr(run_live, "_dem_worker_mo_coi", lambda: 2)
        args = type("A", (), {"metrics_csv": str(tmp_path / "t_metrics.csv"),
                              "metrics_summary": str(tmp_path / "t_summary.json"),
                              "source": "data/binh1.mp4"})()
        run_live._write_run_info(args)
        d = json.loads((tmp_path / "t_run_info.json").read_text(encoding="utf-8"))
        assert d["loadavg_1m"] == 7.25
        assert d["cpu_count"] == run_live.os.cpu_count()
        assert d["live_workers_khac"] == 2

    def test_khong_co_getloadavg_thi_ghi_none(self, tmp_path, monkeypatch):
        """Windows không có `os.getloadavg` ⇒ ghi None, KHÔNG được ném (provenance không chặn số)."""
        import json

        def nem():
            raise AttributeError("getloadavg")

        monkeypatch.setattr(run_live.os, "getloadavg", nem, raising=False)
        args = type("A", (), {"metrics_csv": str(tmp_path / "u_metrics.csv"),
                              "metrics_summary": str(tmp_path / "u_summary.json"),
                              "source": "0"})()
        run_live._write_run_info(args)
        d = json.loads((tmp_path / "u_run_info.json").read_text(encoding="utf-8"))
        assert d["loadavg_1m"] is None


class TestSummaryCoNhipPhat:
    def test_summary_co_du_field_va_khong_doi_field_cu(self, tmp_path):
        """`extra` chỉ THÊM key: summary là hợp đồng của `web/` + notebook Colab."""
        import json
        from src.metrics_logger import MetricsLogger, write_run_info  # noqa: F401

        m = MetricsLogger()
        from src.metrics_logger import FrameRecord

        m.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=1.0, center=(5, 5), lost=False))
        out = tmp_path / "s.json"
        m.write_summary_json(str(out), extra={"wall_s": 30.76, "video_s": 20.83,
                                               "ti_le_thoi_luong": 0.677,
                                               "total_frames": 999})   # key cũ KHÔNG bị ghi đè
        d = json.loads(out.read_text(encoding="utf-8"))
        assert d["wall_s"] == 30.76 and d["ti_le_thoi_luong"] == 0.677
        assert d["total_frames"] == 1, "extra không được ghi đè số của MetricsLogger"


def test_no_reid_thang_yaml_qua_duong_hop_nhat_that():
    """P2 review 24-11: test cũ chỉ kiểm `parse_args` (thứ tự cờ) — KHÔNG đi qua bước hợp nhất
    YAML ⇒ đúng ca hỏng (YAML `reid_enabled: true`) không bị khoá.

    Đo được: `_cfg_tu_cli` phải là **tri-state** (None/True/False) và `--no-reid` phải thắng YAML.
    """
    from src.config import merge_cli_overrides

    ap = run_live.build_parser()
    cfg_yaml = {"reid_enabled": True, "source": "data/binh1.mp4", "checkpoint": "tiny"}
    cfg = merge_cli_overrides(dict(cfg_yaml), run_live._cfg_tu_cli(ap.parse_args(["--no-reid"])))
    assert cfg["reid_enabled"] is False, "YAML bật re-ID mà --no-reid không thắng ⇒ tắt không được"
    cfg = merge_cli_overrides(dict(cfg_yaml), run_live._cfg_tu_cli(ap.parse_args(["--reid"])))
    assert cfg["reid_enabled"] is True
    # không nói gì ⇒ giữ YAML
    cfg = merge_cli_overrides({"reid_enabled": False}, run_live._cfg_tu_cli(ap.parse_args([])))
    assert cfg["reid_enabled"] is False


def test_run_info_ghi_cua_so_quy_dao(tmp_path):
    """`run_info.json` phải nói quỹ đạo dài bao nhiêu — không có thì `./run demoip` (5 s) không
    phân biệt được với mặc định 100 điểm (P2 review 24-11)."""
    import inspect

    src = inspect.getsource(run_live._write_run_info)
    assert "trajectory_seconds" in src and "max_trajectory" in src
