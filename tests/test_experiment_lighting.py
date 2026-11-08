"""Test `scripts/experiment_lighting.py` — thí nghiệm đổi ánh sáng (yêu cầu 11 của GVHD).

Hai tầng:
  - **Làn nhanh**: hàm thuần `apply_lighting` + điều phối `run_sweep` với engine GIẢ
    (không cần checkpoint) → khoá được lỗi tràn số uint8 và lỗi "quên reset engine giữa các mức sáng".
  - **Làn slow**: engine SAMURAI thật với 2 mức sáng × 3 khung → chứng minh chạy được end-to-end.
"""
import numpy as np
import pytest

from scripts.experiment_lighting import apply_lighting, iou, run_gain, run_sweep, write_csv
from src.tracker_engine import TrackingResult


def _fake_fixture(frames_n=6, size=(90, 120), square=20):
    """Fixture nhỏ tự sinh (không dùng model): ô vuông trắng trên nền đen, dịch 2 px/frame."""
    frames = np.zeros((frames_n, size[0], size[1], 3), dtype=np.uint8)
    bboxes = []
    for i in range(frames_n):
        x = 10 + 2 * i
        frames[i, 20:20 + square, x:x + square] = 255
        bboxes.append((x, 20, x + square, 20 + square))

    class Fixture:
        pass

    fx = Fixture()
    fx.frames = frames
    fx.bboxes = bboxes
    fx.frame_size = size
    return fx


class FakeEngine:
    """Engine giả: trả đúng bbox thật của khung → IoU = 1 bất kể ánh sáng (chỉ kiểm điều phối)."""

    def __init__(self, lost_every=None):
        self._fixture = None
        self.reset_calls = 0
        self.start_calls = 0
        self.process_calls = 0
        self.lost_every = lost_every

    def start(self, frame, bbox):
        self.start_calls += 1
        return self._res(bbox, 0)

    def process(self, frame):
        self.process_calls += 1
        fixture = self._fixture
        idx = self.process_calls
        return self._res(fixture.bboxes[idx], idx)

    def reset(self):
        self.reset_calls += 1
        self.process_calls = 0          # mỗi mức sáng là một lần chạy mới → đếm lại từ 0

    def _res(self, bbox, idx):
        mask = np.ones((90, 120), dtype=bool)
        if self.lost_every and idx % self.lost_every == 1:
            mask = np.zeros_like(mask)
        return TrackingResult(frame_idx=idx, mask=mask, bbox=tuple(bbox), score=1.0, elapsed_ms=1.0)


class TestApplyLighting:
    def test_gain_1_giu_nguyen_khung_hinh(self):
        frame = np.full((4, 4, 3), 100, dtype=np.uint8)
        out = apply_lighting(frame, 1.0)
        assert np.array_equal(out, frame)

    def test_giam_sang_dung_mot_nua(self):
        frame = np.full((2, 2, 3), 100, dtype=np.uint8)
        assert np.allclose(apply_lighting(frame, 0.5), 50)

    def test_gain_0_thanh_den(self):
        frame = np.full((2, 2, 3), 200, dtype=np.uint8)
        assert apply_lighting(frame, 0.0).max() == 0

    def test_khong_tran_so_khi_tang_sang(self):
        """uint8 nhân trực tiếp sẽ tràn (250×2 = 244) → phải cắt về 255 và giữ uint8."""
        frame = np.full((2, 2, 3), 250, dtype=np.uint8)
        out = apply_lighting(frame, 2.0)
        assert out.dtype == np.uint8
        assert out.max() == 255, "tràn số uint8 — phải ép float32 trước khi nhân"

    def test_do_sang_trung_binh_giam_theo_gain(self):
        rng = np.random.default_rng(0)
        frame = rng.integers(40, 200, size=(32, 32, 3), dtype=np.uint8)
        means = [apply_lighting(frame, g).mean() for g in (1.0, 0.6, 0.35, 0.1)]
        assert means == sorted(means, reverse=True)
        assert all(0.0 <= m <= 255.0 for m in means)

    def test_khong_sua_khung_hinh_goc(self):
        frame = np.full((2, 2, 3), 120, dtype=np.uint8)
        apply_lighting(frame, 0.5)
        assert np.all(frame == 120), "hàm không được sửa mảng đầu vào (dùng lại cho mức sáng khác)"


class TestIou:
    def test_trung_khop_hoan_toan(self):
        assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0

    def test_khong_giao_nhau(self):
        assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0

    def test_giao_mot_nua(self):
        assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == 50 / 150


class TestRunGain:
    def test_tra_ve_do_dai_bang_so_khung(self):
        fx = _fake_fixture(frames_n=6)
        engine = FakeEngine()
        engine._fixture = fx
        ious, lost = run_gain(engine, fx, gain=0.5)
        assert ious.size == 6 and lost.size == 6
        assert np.all((ious >= 0.0) & (ious <= 1.0))
        assert engine.start_calls == 1
        assert engine.process_calls == 5

    def test_reset_truoc_moi_muc_sang(self):
        """Không reset → bộ nhớ SAM 2 mức trước rò sang mức sau, số đo mất nghĩa."""
        fx = _fake_fixture(frames_n=4)
        engine = FakeEngine()
        engine._fixture = fx
        run_gain(engine, fx, gain=1.0)
        assert engine.reset_calls == 1

    def test_engine_gia_luon_dung_bbox_thi_iou_1(self):
        fx = _fake_fixture(frames_n=5)
        engine = FakeEngine()
        engine._fixture = fx
        ious, _lost = run_gain(engine, fx, gain=0.2)
        assert np.allclose(ious, 1.0), "engine giả trả đúng đáp án nên IoU phải = 1"


class TestRunSweep:
    def test_moi_muc_sang_mot_dong_va_du_khoa(self):
        fx = _fake_fixture(frames_n=5)
        engine = FakeEngine()
        engine._fixture = fx
        rows = run_sweep(engine, gains=(1.0, 0.5, 0.2), fixture=fx)
        assert [r["gain"] for r in rows] == [1.0, 0.5, 0.2]
        assert all({"gain", "frames", "mean_iou", "min_iou", "lost_frames"} <= set(r) for r in rows)
        assert all(r["frames"] == 5 for r in rows)
        assert engine.reset_calls == 3, "phải reset engine đúng 1 lần cho mỗi mức sáng"

    def test_khung_mat_dau_duoc_dem(self):
        """Mức sáng nào engine giả trả mask rỗng thì `lost_frames` phải > 0 (không lúc nào ra 0)."""
        fx = _fake_fixture(frames_n=5)
        engine = FakeEngine(lost_every=2)
        engine._fixture = fx
        rows = run_sweep(engine, gains=(1.0, 0.3), fixture=fx)
        assert all(r["lost_frames"] > 0 for r in rows)


class TestWriteCsv:
    def test_ghi_csv_doc_lai_duoc(self, tmp_path):
        import csv

        rows = [{"gain": 1.0, "frames": 5, "mean_iou": 0.9, "min_iou": 0.8, "lost_frames": 0},
                {"gain": 0.2, "frames": 5, "mean_iou": 0.4, "min_iou": 0.0, "lost_frames": 2}]
        path = write_csv(rows, str(tmp_path / "sub" / "lighting.csv"))
        with open(path, encoding="utf-8") as f:
            got = list(csv.DictReader(f))
        assert len(got) == 2
        assert got[1]["gain"] == "0.2" and got[1]["lost_frames"] == "2"


@pytest.mark.slow
class TestVoiEngineThat:
    """Chạy SAMURAI thật: đổi ánh sáng phải xử lý được (không crash) và IoU mức gốc đạt ngưỡng."""

    def test_hai_muc_sang_chay_duoc_va_muc_goc_dat_nguong(self, samurai_engine):
        fx = _fake_fixture(frames_n=3, size=(240, 320), square=40)
        rows = run_sweep(samurai_engine, gains=(1.0, 0.3), fixture=fx)
        assert len(rows) == 2
        goc = rows[0]
        assert goc["gain"] == 1.0
        assert goc["mean_iou"] >= 0.5, f"IoU ảnh gốc chỉ {goc['mean_iou']:.2f} — engine có vấn đề"
        assert all(0.0 <= r["mean_iou"] <= 1.0 for r in rows)


class TestWriteJson:
    def test_ghi_json_lam_bang_chung_do(self, tmp_path):
        """JSON `*_summary.json` là file được git giữ lại → phải ghi đúng rows cho báo cáo."""
        import json

        from scripts.experiment_lighting import write_json

        rows = [{"gain": 1.0, "frames": 12, "mean_iou": 0.974, "min_iou": 0.952, "lost_frames": 0}]
        path = write_json(rows, str(tmp_path / "lighting_iou_320_summary.json"))
        data = json.loads(open(path, encoding="utf-8").read())
        assert data["experiment"] == "do-i-anh-sang"
        assert data["rows"] == rows
