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
