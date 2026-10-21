"""Test phần logic của scripts/experiment_occlusion.py (không cần model thật)."""
import numpy as np

from scripts.experiment_occlusion import iou, run_scenario


class TestIou:
    def test_trung_khop_hoan_toan(self):
        assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0

    def test_khong_giao_nhau(self):
        assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0

    def test_giao_mot_nua(self):
        assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == 50 / 150


class TestRunScenario:
    def test_tra_ve_mang_dung_do_dai_voi_engine_gia(self):
        from src.tracker_engine import TrackingResult

        class FakeEngine:
            def __init__(self):
                self._bbox = None

            def start(self, frame, bbox):
                self._bbox = bbox
                return self._res()

            def process(self, frame):
                return self._res()

            def reset(self):
                self._bbox = None

            def _res(self):
                mask = np.ones((360, 640), dtype=bool)
                return TrackingResult(frame_idx=0, mask=mask, bbox=(80, 80, 140, 140),
                                      score=1.0, elapsed_ms=1.0)

        ious, lost, occluded = run_scenario(FakeEngine(), fraction=0.5, frames_n=20, cover=4,
                                           start_cover=8)
        assert len(ious) == 20 and len(lost) == 20 and len(occluded) == 20
        assert occluded[8] and not occluded[0]
        # engine giả luôn trả đúng bbox frame 0 → IoU giảm dần vì đáp án di chuyển, nhưng phải là số
        assert np.all((ious >= 0) & (ious <= 1))
