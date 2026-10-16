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