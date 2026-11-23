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
                           "state", "reid_score", "reacquired", "ncc", "vetoed",
                           "bbox_w", "bbox_h", "mask_area", "track_cos",
                           "nghi_doi_tuong",    # 21-11: cổng nhảy có NHỚ (0/1/trống)
                           "verify_cos",        # 23-11: cos mask-vs-mask ở frame NHẬN LẠI
                           "cos_truoc_cong",    # 23-11: cos cao nhất TRƯỚC mọi cổng
                           "cand_n",            # 23-11: số ứng viên đã chấm (sau prefilter NCC)
                           "cand_sinh_n",       # 23-11: số ô BỘ SINH đưa ra (trước bán kính/NCC)
                           "cand_ncc_loai",     # 23-11: số ứng viên bị cổng NCC loại
                           "bbox_area_ratio"]   # 24-11: diện tích ô / EMA — CHỈ chẩn đoán
        assert len(rows) == 6  # header + 5 dòng
        assert rows[1] == ["0", "100.0", "0.9", "50", "60", "0", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]
        assert rows[5] == ["4", "140.0", "0.9", "58", "64", "0", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]

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
        assert rows[2] == ["1", "200.0", "0.1", "", "", "1", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]

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
        """Ticket #32: `p95` CHƯA ĐO phải là `None`, không phải `0,0` (0 ms là số đo được)."""
        s = MetricsLogger().summary()
        assert s["total_frames"] == 0
        assert s["mean_latency_ms"] == 0.0     # mean giữ 0,0 vì `effective_fps` hợp đồng cũ
        assert s["p95_latency_ms"] is None
        assert s["p95_latency_ms_n"] == 0
        assert s["effective_fps"] == 0.0
        assert s["lost_ratio"] == 0.0

    def test_p95_None_khi_toan_bo_frame_dong_bang(self):
        """Có frame nhưng TẤT CẢ bị đóng băng (mất dấu → không gọi model) ⇒ không có mẫu latency."""
        records = [FrameRecord(frame_idx=i, latency_ms=0.0, score=0.0, center=None,
                               lost=True, state="lost")
                   for i in range(3)]
        logger = MetricsLogger()
        for r in records:
            logger.log(r)
        s = logger.summary()
        assert s["total_frames"] == 3
        assert s["p95_latency_ms"] is None and s["p95_latency_ms_n"] == 0

    def test_p95_kem_co_mau_de_doc_can_nhau(self):
        """p95 của 1 frame ≈ chính frame đó ⇒ phải đọc kèm `_n` để biết nó không phải phân vị thật."""
        logger = MetricsLogger()
        for r in _records(4):
            logger.log(r)
        s = logger.summary()
        assert s["p95_latency_ms"] is not None
        assert s["p95_latency_ms_n"] == 4

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
        # 21-11: thêm cột `vetoed` (ứng viên bị BỎ vì trùng khuôn mặt) — thiếu nó thì
        # `state=reacquiring` không phân biệt được "đang tìm" với "đã thấy nhưng bỏ".
        # 21-11 (cổng nhảy CÓ NHỚ): thêm cột `nghi_doi_tuong` ở CUỐI ⇒ 10 cột cuối.
        assert header[-16:] == ["state", "reid_score", "reacquired", "ncc", "vetoed",
                                "bbox_w", "bbox_h", "mask_area", "track_cos", "nghi_doi_tuong",
                                "verify_cos", "cos_truoc_cong", "cand_n", "cand_sinh_n",
                                "cand_ncc_loai",
                                # 24-11: cột chẩn đoán tràn, đặt ở CUỐI để CSV cũ vẫn đọc được
                                "bbox_area_ratio"]
        assert rows[3][header.index("state")] == "reacquiring"
        assert float(rows[3][header.index("reid_score")]) == pytest.approx(0.21)
        assert rows[4][header.index("reacquired")] == "1"

    def test_cot_ncc_ghi_diem_cua_o_duoc_chon(self, tmp_path):
        """Cột `ncc` (ticket 11) để hiệu chuẩn cổng NCC cho vật đen; trống khi không dùng."""
        logger = MetricsLogger()
        logger.log(FrameRecord(frame_idx=0, latency_ms=10.0, score=1.0, center=(5, 5),
                               state="reacquiring", reid_score=0.99, reacquired=True,
                               ncc=0.941))
        with open(logger.write_csv(tmp_path / "m.csv"), encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert float(rows[1][rows[0].index("ncc")]) == pytest.approx(0.941)

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


class TestThongKeKhongBiLechBoiFrameDongBang:
    """Frame đóng băng (mất dấu → không suy luận) có latency 0 → phải loại khỏi thống kê latency.

    Lỗi thật gặp khi chạy `./run demo` 22-10: 35/145 dòng có latency 0 ms làm mean tụt
    từ 311 ms xuống 236 ms → báo cáo FPS sai (4,24 thay vì 3,22).
    """

    def test_loai_frame_dong_bang_khoi_mean_p95(self):
        logger = MetricsLogger()
        logger.log(FrameRecord(frame_idx=0, latency_ms=300.0, score=1.0, center=(10, 10),
                               state="tracking"))
        logger.log(FrameRecord(frame_idx=1, latency_ms=310.0, score=1.0, center=(11, 11),
                               state="tracking"))
        # frame đóng băng: không gọi model nên latency 0
        logger.log(FrameRecord(frame_idx=2, latency_ms=0.0, score=0.0, center=None, lost=True,
                               state="reacquiring", reid_score=-1.0))
        s = logger.summary()
        assert s["mean_latency_ms"] == pytest.approx(305.0)
        assert s["effective_fps"] == pytest.approx(1000 / 305.0, rel=1e-6)
        assert s["frozen_frames"] == 1
        assert s["total_frames"] == 3

    def test_ban_ghi_khong_co_state_van_tinh_nhu_cu(self):
        logger = MetricsLogger()
        logger.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=1.0, center=(1, 1)))
        logger.log(FrameRecord(frame_idx=1, latency_ms=200.0, score=1.0, center=(2, 2)))
        s = logger.summary()
        assert s["mean_latency_ms"] == pytest.approx(150.0)
        assert s["frozen_frames"] == 0

    def test_toan_bo_frame_dong_bang_thi_khong_chia_cho_0(self):
        logger = MetricsLogger()
        logger.log(FrameRecord(frame_idx=0, latency_ms=0.0, score=0.0, center=None, lost=True,
                               state="lost"))
        s = logger.summary()
        assert s["mean_latency_ms"] == 0.0
        assert s["effective_fps"] == 0.0
        assert s["frozen_frames"] == 1


class TestMeanVaP95CoMauKemTheo:
    """P2 review 17-11 (ticket #32): `mean_latency_ms` giữ `0,0` khi rỗng nhưng phải kèm `_n`,
    nếu không người sau vẫn trích được "mean 0 ms" như số đo được."""

    def test_summary_rong_co_mean_n_bang_0(self):
        s = MetricsLogger().summary()
        assert s["mean_latency_ms"] == 0.0 and s["mean_latency_ms_n"] == 0
        assert s["p95_latency_ms"] is None and s["p95_latency_ms_n"] == 0

    def test_mean_n_bang_so_frame_do_duoc(self):
        logger = MetricsLogger()
        for r in _records(4):
            logger.log(r)
        s = logger.summary()
        assert s["mean_latency_ms_n"] == 4 and s["p95_latency_ms_n"] == 4

    def test_toan_bo_dong_bang_mean_n_bang_0(self):
        logger = MetricsLogger()
        for i in range(3):
            logger.log(FrameRecord(frame_idx=i, latency_ms=0.0, score=0.0, center=None,
                                   lost=True, state="lost"))
        s = logger.summary()
        assert s["mean_latency_ms_n"] == 0 and s["mean_latency_ms"] == 0.0


class TestChiPhiTimLai:
    """23-11-2026 (review độc lập 3 ý kiến, F2): frame ĐÓNG BĂNG bị loại khỏi `mean_latency_ms`.

    Hệ quả đo được: phiên `demoip_1123-095901` in `mean 161,8 ms (n=93)` trong khi nó có **160** bước
    tìm lại (66 ms/bước) không nằm trong con số nào ⇒ mọi tuyên bố "thêm bước thử ứng viên có làm
    chậm phiên không" trước đây KHÔNG kiểm được.
    """

    def _rec(self, idx, ms, state):
        return FrameRecord(frame_idx=idx, latency_ms=ms, score=1.0, center=(1, 1),
                           lost=(state != "tracking"), state=state)

    def test_search_latency_tach_khoi_mean_va_co_n(self):
        lg = MetricsLogger()
        lg.log(self._rec(0, 100.0, "tracking"))
        lg.log(self._rec(1, 200.0, "lost"))
        lg.log(self._rec(2, 500.0, "reacquiring"))
        s = lg.summary()
        # mean cũ KHÔNG đổi (chỉ tracking) — giữ hợp đồng
        assert s["mean_latency_ms"] == 100.0 and s["mean_latency_ms_n"] == 1
        assert s["search_n"] == 2
        assert s["search_mean_ms"] == 350.0
        assert s["search_p95_ms"] >= 350.0

    def test_khong_co_frame_dong_bang_thi_search_la_None_khong_phai_0(self):
        """`None` = chưa đo; `0` = đo được 0 ms — hai thứ khác nhau (bẫy đã gặp nhiều lần)."""
        lg = MetricsLogger()
        lg.log(self._rec(0, 120.0, "tracking"))
        s = lg.summary()
        assert s["search_mean_ms"] is None and s["search_p95_ms"] is None and s["search_n"] == 0

    def test_csv_co_cot_verify_cos_va_de_trong_khi_chua_cham(self, tmp_path):
        lg = MetricsLogger()
        lg.log(FrameRecord(frame_idx=0, latency_ms=10.0, score=1.0, center=(5, 5), lost=False,
                           state="tracking", verify_cos=0.83))
        lg.log(FrameRecord(frame_idx=1, latency_ms=10.0, score=1.0, center=(5, 5), lost=False,
                           state="tracking"))
        out = tmp_path / "m.csv"
        lg.write_csv(str(out))
        import csv as _csv
        rows = list(_csv.reader(open(out, newline="")))
        i = rows[0].index("verify_cos")
        assert rows[1][i] == "0.83"
        assert rows[2][i] == "", "chưa chấm phải để TRỐNG (không ghi 0)"

    def test_frame_bail_out_0ms_khong_pha_loang_search_mean(self):
        """P1 review độc lập 23-11: frame KHÔNG gọi model (`latency_ms = 0.0`) không được vào mean.

        Trước khi sửa: `_auto_recover`/`_abandon_reacquire` trả `LostResult.elapsed_ms = 0.0`, và
        `search_lat` gom cả 0,0 ⇒ **càng thêm cờ nghi (càng nhiều frame bail-out) thì "chi phí tìm
        lại" càng GIẢM** — ngược chiều sự thật, đúng loại bẫy "số đẹp lên sau khi thêm tính năng".
        """
        lg = MetricsLogger()
        lg.log(self._rec(0, 100.0, "tracking"))
        lg.log(self._rec(1, 0.0, "lost"))          # bail-out: KHÔNG gọi model ⇒ 0 ms
        lg.log(self._rec(2, 0.0, "lost"))
        lg.log(self._rec(3, 400.0, "reacquiring"))  # bước tìm THẬT SỰ chạy
        s = lg.summary()
        assert s["search_n"] == 1, "chỉ frame ĐO ĐƯỢC mới vào mẫu"
        assert s["search_mean_ms"] == 400.0, "0,0 không được kéo mean xuống"
        assert s["search_khong_do_n"] == 2, "phải khai riêng số frame đóng băng KHÔNG đo được"


class TestCotChanDoanTran:
    """Plan 24-11 việc 4 — `bbox_area_ratio` là cột CUỐI của CSV, TRỐNG = chưa đo.

    Vì sao phải là cột CUỐI: `DictReader` của mọi script phân tích cũ đọc theo tên, nhưng CSV cũ
    (trước 24-11) không có cột này ⇒ chèn vào giữa sẽ làm lệch thứ tự giữa header và dòng dữ liệu
    (đã xảy ra trong lúc làm: header 22 cột còn dòng 22 giá trị nhưng lệch vị trí, cột đọc ra rỗng).
    """

    def _m(self):
        from src.metrics_logger import MetricsLogger

        return MetricsLogger()

    def test_cot_nam_o_cuoi_va_csv_cu_van_doc_duoc(self, tmp_path):
        import csv

        from src.metrics_logger import CSV_HEADER, FrameRecord

        assert CSV_HEADER[-1] == "bbox_area_ratio"
        m = self._m()
        m.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=1.0, center=(10, 10),
                          lost=False, bbox_w=76, bbox_h=76))
        out = tmp_path / "c.csv"
        m.write_csv(str(out))
        rows = list(csv.DictReader(open(out, encoding="utf-8")))
        assert len(rows[0]) == len(CSV_HEADER), "header và dòng dữ liệu lệch số cột"
        assert rows[0]["bbox_area_ratio"] == "1.000"
        assert rows[0]["bbox_w"] == "76"          # cột cũ vẫn đúng chỗ

    def test_o_rong_thi_cot_trong_khong_phai_0(self, tmp_path):
        import csv

        from src.metrics_logger import FrameRecord

        m = self._m()
        m.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=0.0, center=None, lost=True,
                          bbox_w=0, bbox_h=0))
        out = tmp_path / "d.csv"
        m.write_csv(str(out))
        rows = list(csv.DictReader(open(out, encoding="utf-8")))
        assert rows[0]["bbox_area_ratio"] == "", "mất dấu phải TRỐNG (chưa đo), không phải 0"
