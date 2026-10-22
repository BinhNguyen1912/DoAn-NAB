"""Test MetricsLogger — CSV từng frame + summary mean/p95/tỷ lệ mất dấu (ticket 07).

Spec testing decisions: thuần chức năng — cho N bản ghi giả, assert không cần chạy model;
CSV đúng cột; summary tính đúng trung bình/p95; tâm ghi đủ để vẽ quỹ đạo.
"""
import csv
import json

import cv2
import numpy as np
import pytest

from src.metrics_logger import FrameRecord, MetricsLogger, is_lost, LOST_SCORE_THRESHOLD
from src.tracker_engine import TrackingResult
from src.prompt_selector import PromptSelector


def _records(n=10, start_ms=100.0):
    """N bản ghi giả: latency tuyến tính, tâm di chuyển đều, score 0.9."""
    return [
        FrameRecord(
            frame_idx=i,
            latency_ms=start_ms + 10 * i,
            score=0.9,
            center=(50 + 2 * i, 60 + i),
            lost=False,
        )
        for i in range(n)
    ]


class TestCsv:
    def test_csv_dung_header_va_so_dong(self, tmp_path):
        out = tmp_path / "metrics.csv"
        logger = MetricsLogger()
        for r in _records(5):
            logger.log(r)
        logger.write_csv(str(out))

        with open(out, newline="") as f:
            rows = list(csv.reader(f))
        assert rows[0] == ["frame_idx", "latency_ms", "score",
                           "center_x", "center_y", "lost",
                           "state", "reid_score", "reacquired"]
        assert len(rows) == 6  # header + 5 dòng
        assert rows[1] == ["0", "100.0", "0.9", "50", "60", "0", "", "", ""]
        assert rows[5] == ["4", "140.0", "0.9", "58", "64", "0", "", "", ""]

    def test_mau_tam_ghi_rong_khi_mat_dau(self, tmp_path):
        """Mất dấu (tâm None) → cột center_x/center_y rỗng, lost=1 — không vẽ quỹ đạo sai."""
        out = tmp_path / "metrics.csv"
        logger = MetricsLogger()
        logger.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=0.9,
                               center=(50, 60), lost=False))
        logger.log(FrameRecord(frame_idx=1, latency_ms=200.0, score=0.1,
                               center=None, lost=True))
        logger.write_csv(str(out))
        with open(out, newline="") as f:
            rows = list(csv.reader(f))
        assert rows[2] == ["1", "200.0", "0.1", "", "", "1", "", "", ""]

    def test_log_mot_so_lan_cung_record_ke_du(self, tmp_path):
        logger = MetricsLogger()
        for r in _records(3):
            logger.log(r)
        logger.log(FrameRecord(frame_idx=3, latency_ms=400.0, score=0.9,
                               center=(60, 70), lost=False))
        logger.write_csv(str(tmp_path / "m.csv"))
        with open(tmp_path / "m.csv", newline="") as f:
            rows = list(csv.reader(f))
        assert len(rows) == 5  # header + 4


class TestSummary:
    def test_mean_p95_fps_hieu_dung_tinh_dung(self):
        logger = MetricsLogger()
        for r in _records(3):  # latencies 100, 110, 120
            logger.log(r)
        s = logger.summary()
        assert s["total_frames"] == 3
        assert s["mean_latency_ms"] == pytest.approx(110.0)
        # p95 của [100,110,120] nội suy tuyến tính = 100 + 0.95*(120-100) = 119.0
        assert s["p95_latency_ms"] == pytest.approx(119.0)
        assert s["effective_fps"] == pytest.approx(1000.0 / 110.0)

    def test_ty_le_mat_dau_dem_dung(self):
        logger = MetricsLogger()
        recs = _records(10)
        for i, r in enumerate(recs):
            if i in (2, 5, 6):  # 3/10 frame mất dấu
                logger.log(FrameRecord(r.frame_idx, r.latency_ms, r.score,
                                       center=None, lost=True))
            else:
                logger.log(r)
        s = logger.summary()
        assert s["lost_count"] == 3
        assert s["lost_ratio"] == pytest.approx(0.3)

    def test_summary_rong_khong_crash(self):
        s = MetricsLogger().summary()
        assert s["total_frames"] == 0
        assert s["mean_latency_ms"] == 0.0
        assert s["p95_latency_ms"] == 0.0
        assert s["effective_fps"] == 0.0
        assert s["lost_ratio"] == 0.0

    def test_write_summary_json_doc_lai_duoc(self, tmp_path):
        out = tmp_path / "summary.json"
        logger = MetricsLogger()
        for r in _records(4):
            logger.log(r)
        logger.write_summary_json(str(out))
        data = json.loads(out.read_text())
        assert data["total_frames"] == 4
        assert data["mean_latency_ms"] == pytest.approx(115.0)
        assert "p95_latency_ms" in data and "lost_ratio" in data


class TestIsLost:
    """Hàm thuần suy cờ mất dấu: mask rỗng (tâm None) hoặc điểm tin cậy dưới ngưỡng."""

    def test_tam_none_la_mat_dau(self):
        assert is_lost(FrameRecord(0, 100.0, 0.9, center=None)) is True

    def test_score_duoi_nguong_la_mat_dau(self):
        rec = FrameRecord(0, 100.0, -0.5, center=(10, 10))  # object_score <= 0
        assert is_lost(rec) is True

    def test_score_tren_nguong_khong_mat_dau(self):
        rec = FrameRecord(0, 100.0, 0.9, center=(10, 10))
        assert is_lost(rec) is False

    def test_explicit_lost_giao_cho_caller_ket_hop(self):
        """Caller kết hợp nhiều nguồn tin (mask rỗng + score thấp); logger chỉ tính lại khi thiếu."""
        rec = FrameRecord(0, 100.0, -0.5, center=(10, 10), lost=False)
        assert is_lost(rec) is False

    def test_nguong_mac_dinh_dung_y_sam2(self):
        """object_score_logits > 0 là tin cậy → ngưỡng mặc định 0.0."""
        assert LOST_SCORE_THRESHOLD == 0.0


class TestTichHop:
    def test_run_tracking_logs_moii_frame(self, tmp_path, write_video):
        """run_tracking(metrics=logger) — CSV đủ N frame, không cần model (FakeEngine)."""
        from src.synthetic_video import generate_tracking_sequence
        from src.live_pipeline import run_tracking

        class FakeEngine:
            def __init__(self):
                self._idx = -1

            def start(self, frame, bbox):
                self._idx = 0
                return self._res(0)

            def process(self, frame):
                self._idx += 1
                return self._res(self._idx)

            def _res(self, i):
                mask = np.zeros((240, 320), dtype=bool)
                x = 60 + 4 * i
                mask[60:100, x:x + 40] = True
                return TrackingResult(
                    frame_idx=i, mask=mask,
                    bbox=(x, 60, x + 40, 100), score=0.9, elapsed_ms=50.0,
                )

        fx = generate_tracking_sequence(num_frames=4, frame_size=(240, 320),
                                        square_size=40, start=(60, 60))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        csv_out = tmp_path / "metrics.csv"

        logger = MetricsLogger()
        run_tracking(source=str(path), engine=FakeEngine(), bbox=fx.bboxes[0],
                     metrics=logger)
        logger.write_csv(str(csv_out))

        with open(csv_out, newline="") as f:
            rows = list(csv.reader(f))
        assert len(rows) == 5  # header + 4 frame
        assert rows[1][:4] == ["0", "50.0", "0.9", "80"]  # tâm (60+40/2=80, 80)

    def test_run_interactive_logs_va_lost_duoc_ghi(self, tmp_path):
        from src.synthetic_video import generate_tracking_sequence
        from src.live_pipeline import run_interactive

        class FakeEngine2:
            def __init__(self):
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
                mask = np.zeros((240, 320), dtype=bool)
                bbox = (0, 0, 0, 0) if i == 2 else (100, 100, 140, 140)  # frame 2 mất dấu
                if i != 2:
                    mask[100:140, 100:140] = True
                return TrackingResult(
                    frame_idx=i, mask=mask, bbox=bbox, score=0.9, elapsed_ms=50.0,
                )

        fx = generate_tracking_sequence(num_frames=10, frame_size=(240, 320),
                                        square_size=40, start=(60, 60))
        path = tmp_path / "seq.avi"
        out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 240))
        for fr in fx.frames:
            out.write(fr)
        out.release()

        sel = PromptSelector(frame_shape=(240, 320, 3))
        logger = MetricsLogger()
        done = {"n_process": 0}

        def display(img, mode):
            if mode == "select" and len(logger.records) == 0:
                sel.on_mouse(cv2.EVENT_LBUTTONDOWN, 100, 100, 0, None)
                sel.on_mouse(cv2.EVENT_LBUTTONUP, 140, 140, 0, None)
            # đủ 4 frame (1 start + 3 process, có 1 frame lost) → thoát
            if done["n_process"] >= 4:
                return ord("q")
            return -1

        def on_result(result):
            done["n_process"] += 1

        run_interactive(source=str(path), engine=FakeEngine2(), selector=sel,
                        display=display, on_result=on_result, metrics=logger)
        s = logger.summary()
        assert s["total_frames"] == 4
        assert s["lost_count"] == 1
        assert s["lost_ratio"] == pytest.approx(0.25)

class TestTrangThaiTaiNhanDien:
    """Cột state/reid_score/reacquired + đếm số lần nhận lại (ADR-0003, ticket 09)."""

    def _log(self, logger):
        logger.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=0.9, center=(10, 10),
                               state="tracking", reid_score=-1.0, reacquired=False))
        logger.log(FrameRecord(frame_idx=1, latency_ms=100.0, score=0.0, center=None,
                               lost=True, state="lost", reid_score=-1.0, reacquired=False))
        logger.log(FrameRecord(frame_idx=2, latency_ms=100.0, score=0.0, center=None,
                               lost=True, state="reacquiring", reid_score=0.21,
                               reacquired=False))
        logger.log(FrameRecord(frame_idx=3, latency_ms=100.0, score=0.9, center=(90, 90),
                               state="tracking", reid_score=0.71, reacquired=True))

    def test_csv_co_them_cot_trang_thai(self, tmp_path):
        logger = MetricsLogger()
        self._log(logger)
        path = logger.write_csv(tmp_path / "m.csv")
        with open(path, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        header = rows[0]
        assert header[-3:] == ["state", "reid_score", "reacquired"]
        assert rows[3][header.index("state")] == "reacquiring"
        assert float(rows[3][header.index("reid_score")]) == pytest.approx(0.21)
        assert rows[4][header.index("reacquired")] == "1"

    def test_summary_dem_frame_tim_lai_va_so_lan_nhan_lai(self):
        logger = MetricsLogger()
        self._log(logger)
        s = logger.summary()
        assert s["reacquiring_frames"] == 1
        assert s["reacquired_count"] == 1
        assert s["lost_count"] == 2

    def test_ban_ghi_cu_khong_co_trang_thai_van_hop_le(self, tmp_path):
        logger = MetricsLogger()
        logger.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=0.9, center=(10, 10)))
        path = logger.write_csv(tmp_path / "old.csv")
        with open(path, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows[1][-3:] == ["", "", ""]
