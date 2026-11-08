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

        ious, lost, occluded, mask_ious = run_scenario(FakeEngine(), fraction=0.5, frames_n=20,
                                                       cover=4, start_cover=8)
        assert len(ious) == 20 and len(lost) == 20 and len(occluded) == 20
        assert len(mask_ious) == 20, "phải đo cả mIoU mask vs GT, không chỉ IoU bbox"
        assert np.all((mask_ious >= 0) & (mask_ious <= 1))
        assert occluded[8] and not occluded[0]
        # engine giả luôn trả đúng bbox frame 0 → IoU giảm dần vì đáp án di chuyển, nhưng phải là số
        assert np.all((ious >= 0) & (ious <= 1))


class TestSummarizeVaMasksGt:
    """`summarize` gom số cho báo cáo; GT mask phải khớp pixel (không chỉ bbox)."""

    def test_summarize_tinh_dung_cac_cua_so(self):
        import numpy as np

        from scripts.experiment_occlusion import summarize

        ious = np.array([1.0, 0.9, 0.8, 0.8, 0.5, 0.9])
        mask_ious = np.array([1.0, 0.8, 0.6, 0.6, 0.2, 0.9])
        lost = np.array([0, 0, 0, 1, 1, 0])
        occl = np.array([False, False, True, True, False, False])

        row = summarize(ious, lost, mask_ious, occl, start=2, cover=2)

        assert row["bbox_iou_truoc"] == 0.9                 # frame 1
        assert row["bbox_iou_trong"] == 0.8                 # frame 2,3
        assert row["bbox_iou_sau"] == 0.7                   # frame 4,5
        assert row["mask_miou_trong"] == 0.6
        assert row["so_frame_do_miou"] == 6
        assert row["mat_dau_trong_che"] == 1
        assert row["mat_dau_sau_che"] == 1
        assert row["so_frame"] == 6

    def test_che_kin_khong_duoc_tinh_la_miou_1(self):
        """GT rỗng (che kín) ⇒ KHÔNG vào mẫu; nếu không sẽ báo "phân đoạn hoàn hảo khi bị che"."""
        import numpy as np

        from scripts.experiment_occlusion import summarize

        ious = np.array([1.0, 1.0, 1.0])
        mask_ious = np.array([0.9, np.nan, 0.8])      # frame 1 bị che kín
        lost = np.array([0, 1, 0])
        occl = np.array([False, True, False])

        row = summarize(ious, lost, mask_ious, occl, start=1, cover=1)

        assert row["mask_miou_trong"] is None, "không có frame đo được ⇒ phải là None, không phải 1.0"
        assert row["so_frame_do_miou"] == 2
        assert row["mask_miou_truoc"] is None         # không có frame nào trước vùng che
        assert row["mask_miou_sau"] == 0.8

    def test_chay_khong_che_thi_miou_mask_bang_1_neu_mask_dung(self):
        """Fixture + mask GT: nếu "model" trả đúng GT thì mIoU phải = 1,0 ở mọi frame."""
        from src.mask_filter import mask_iou
        from src.synthetic_video import generate_tracking_sequence

        fx = generate_tracking_sequence(num_frames=8, frame_size=(120, 160), square_size=24,
                                        start=(10, 10), velocity=(6, 2),
                                        occlusion_frames=(3, 4), occlusion_fraction=0.5)

        mious = [mask_iou(fx.masks[i], fx.masks[i]) for i in range(8)]
        assert all(value == 1.0 for value in mious)
        assert fx.masks[3].sum() == 24 * 12               # che nửa ⇒ đúng nửa diện tích
