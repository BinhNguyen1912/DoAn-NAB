"""Test seam live pipeline — nối VideoSource → TrackerEngine → overlay + metrics (ticket 04).

Màn hình hiển thị tiêm qua callback `on_frame` để test headless (không cần cửa sổ).
Chạy chậm (propagation thật) — đánh dấu `slow`.
"""
import numpy as np
import pytest

from src.synthetic_video import generate_tracking_sequence
from src.live_pipeline import run_tracking


@pytest.mark.slow
class TestLivePipeline:
    def test_chay_qua_video_fixture_dem_du_frame_va_overlay_co_tac_dong(
        self, samurai_engine, tmp_path, write_video
    ):
        fx = generate_tracking_sequence(num_frames=6, frame_size=(240, 320), square_size=40, start=(60, 60))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)

        shown = []
        summary = run_tracking(
            source=str(path),
            engine=samurai_engine,
            bbox=fx.bboxes[0],
            on_frame=lambda img, res: shown.append((img, res)),
        )

        # Đủ 6 frame xử lý + hiển thị từng frame
        assert summary.total_frames == 6
        assert len(shown) == 6
        # Thứ tự frame đúng (result.frame_idx tăng dần)
        assert [res.frame_idx for _, res in shown] == [0, 1, 2, 3, 4, 5]
        # Overlay thêm nét — frame hiển thị phải khác frame gốc đọc từ file (tô mask + vẽ ô)
        img0, res0 = shown[0]
        assert img0.shape == (240, 320, 3)
        assert not np.array_equal(img0, fx.frames[0])
        # Metrics trung thực: danh sách latency đủ N, mean > 0, fps hiệu dụng > 0
        assert len(summary.latencies_ms) == summary.total_frames
        assert summary.mean_ms > 0
        assert summary.effective_fps > 0

class TestReanchor:
    """Tối ưu tốc độ: re-anchor định kỳ (reset + chọn lại bbox hiện tại).

    Đo thật 18-10 trên fixture 20 frame (ô vuông + che 5 frame):
      baseline      : 5340 ms/frame, IoU sau che 0.981, mất dấu 5/19
      re-anchor 3   : 3053 ms/frame (2.2x nhanh hơn), IoU sau che 0.969, mất dấu 0/19
    Vì vậy đây là TUỲ CHỌN (mặc định tắt) — đánh đổi memory dài hạn lấy tốc độ.
    """

    def _engine(self):
        from src.tracker_engine import TrackingResult

        class FakeEngine:
            def __init__(self):
                self.calls = []
                self._idx = -1

            def start(self, frame, bbox):
                self.calls.append(("start", tuple(bbox)))
                self._idx = 0
                return self._res(0, bbox)

            def process(self, frame):
                self._idx += 1
                self.calls.append(("process",))
                x = 60 + 4 * self._idx
                return self._res(self._idx, (x, 60, x + 40, 100))

            def reset(self):
                self.calls.append(("reset",))
                self._idx = -1

            @staticmethod
            def _res(i, bbox):
                import numpy as np

                mask = np.zeros((240, 320), dtype=bool)
                x1, y1, x2, y2 = bbox
                mask[y1:y2, x1:x2] = True
                return TrackingResult(frame_idx=i, mask=mask, bbox=tuple(bbox),
                                      score=0.9, elapsed_ms=50.0)

        return FakeEngine()

    def test_reanchor_dung_nhip_va_dung_bbox_cuoi(self, tmp_path, write_video):
        from src.live_pipeline import run_tracking

        fx = generate_tracking_sequence(num_frames=7, frame_size=(240, 320),
                                        square_size=40, start=(60, 60))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine = self._engine()

        run_tracking(source=str(path), engine=engine, bbox=fx.bboxes[0], reanchor_every=3)

        names = [c[0] for c in engine.calls]
        # frame 0 start, f1 process, f2 process, f3 re-anchor (reset+start), ...
        assert names.count("reset") >= 2
        assert names.count("start") >= 3
        # bbox truyền vào lần re-anchor phải là bbox của frame NGAY TRƯỚC (không phải bbox gốc)
        starts = [c[1] for c in engine.calls if c[0] == "start"]
        assert starts[0] == tuple(fx.bboxes[0])
        assert starts[1] != starts[0]              # đã tiến theo quỹ đạo
        assert starts[1][0] == 60 + 4 * 2          # bbox của frame 2 (trước re-anchor ở frame 3)

    def test_mac_dinh_khong_reanchor(self, tmp_path, write_video):
        from src.live_pipeline import run_tracking

        fx = generate_tracking_sequence(num_frames=5, frame_size=(240, 320),
                                        square_size=40, start=(60, 60))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine = self._engine()

        run_tracking(source=str(path), engine=engine, bbox=fx.bboxes[0])
        names = [c[0] for c in engine.calls]
        assert names.count("reset") == 0
        assert names.count("start") == 1
