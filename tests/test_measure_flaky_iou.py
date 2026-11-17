"""Test `scripts/measure_flaky_iou.py` — P1 review độc lập 17-11: con số "cổng test" công bố SAI.

Bản trước lấy `min` trên **cả 10 frame** rồi gọi là "cổng test" (cổng thật của
`tests/test_tracker_engine.py` là {0, 2, 5, 9}). Trong artifact khi đó `0,928` là **frame 4** — NGOÀI
cổng — nên câu "cách ngưỡng 0,5 bao nhiêu σ" bị tính trên đại lượng không phải thứ quyết định test đỏ.
Test này chạy với engine GIẢ (không cần checkpoint) nên nằm trong làn nhanh.
"""

from __future__ import annotations

import numpy as np
import pytest

from scripts import measure_flaky_iou as mfi

FRAME_LE = tuple(mfi.CONG_TEST)


class _Result:
    def __init__(self, bbox, score=0.9):
        self.bbox = bbox
        self.score = score
        self.elapsed_ms = 1.0
        self.mask = np.ones((8, 8), bool)


class _EngineLech:
    """Engine giả: ĐÚNG ở mọi frame thuộc cổng test, LỆCH nặng ở frame 4 (ngoài cổng)."""

    def __init__(self):
        self._i = 0
        self._gt = None

    def start(self, frame, bbox):
        from src.synthetic_video import generate_tracking_sequence

        self._gt = generate_tracking_sequence(num_frames=10, frame_size=(240, 320),
                                             square_size=40, start=(60, 60)).bboxes
        self._i = 0
        return self._bbox()

    def process(self, frame):
        self._i += 1
        return self._bbox()

    def _bbox(self):
        x1, y1, x2, y2 = self._gt[self._i]
        if self._i == 4:                      # frame NGOÀI cổng: lệch hẳn nửa khung
            return _Result((x1 + 140, y1, x2 + 140, y2))
        return _Result((x1, y1, x2, y2))

    def reset(self):                           # script gọi tường minh trước mỗi vòng
        self._i = 0


class _EngineHong(_EngineLech):
    """Engine trả `score = NaN` ⇒ `score_min` phải là `None`, KHÔNG được để `NaN` vào JSON."""

    def _bbox(self):
        r = super()._bbox()
        r.score = float("nan")
        return r


def test_cong_test_chi_gom_bon_frame_ma_test_cham():
    assert set(mfi.CONG_TEST) == {0, 2, 5, 9}
    assert set(FRAME_LE) == {0, 2, 5, 9}


def test_min_iou_cong_test_khong_bi_frame_ngoai_cong_keo_xuong():
    """P1: `min_iou_cong_test` phải = min trên {0,2,5,9} (ở đây = 1,0), còn min 10 frame < 0,5."""
    ket = mfi.mot_lan(_EngineLech())
    assert ket["min_iou_cong_test"] == pytest.approx(1.0, abs=1e-6)
    assert ket["min_iou_moi_frame"] < 0.5, "frame 4 lệch nửa khung ⇒ min 10 frame phải rất thấp"
    assert ket["min_iou_cong_test"] > ket["min_iou_moi_frame"], (
        "hai đại lượng phải TÁCH nhau: bản trước gọi min-10-frame là 'cổng test'")


def test_duoi_nguong_tinh_theo_cong_test():
    ket = mfi.mot_lan(_EngineLech())
    assert [f for f in mfi.CONG_TEST if ket["iou_tat_ca"][f] < mfi.NGUONG_IOU] == []


def test_tom_tat_tach_hai_mau_so():
    """Một lần chạy có frame NGOÀI cổng trượt ⇒ `0/4 lượt-frame` và `0/1 lần chạy`, không lẫn nhau."""
    lan = [{"lan": 1, **mfi.mot_lan(_EngineLech())}]
    ra = mfi.tom_tat(lan)
    assert ra["cong_test"]["n"] == 1
    assert ra["cong_test"]["so_luot_frame"] == 4
    assert ra["cong_test"]["so_luot_frame_duoi_nguong"] == 0
    assert ra["cong_test"]["so_lan_chay_duoi_nguong"] == 0
    assert ra["cong_test"]["min"] == pytest.approx(1.0, abs=1e-6)


def test_score_nan_thanh_none_khong_vao_json():
    ket = mfi.mot_lan(_EngineHong())
    assert ket["score_min"] is None and ket["score_n"] == 0


def test_lan_duoi_3_bi_tu_choi(capsys):
    assert mfi.main(["--lan", "2", "--out", "/tmp/khong-ghi.json"]) == 2
    assert "cần >= 3" in capsys.readouterr().err
