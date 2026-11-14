"""P0 của review độc lập 14-11: `_dump_mask` phải đặt tên theo **chỉ số frame VIDEO**, không phải
bộ đếm nội bộ của engine.

Vì sao đây là P0: `tracker_engine` đếm số lần gọi `process()` (`idx = self._frame_count`), còn
`score_miou.py label` cắt GT theo số frame của CLIP. Với `vos_every > 1` (mặc định 3) hai bộ đếm lệch
nhau gấp N lần ⇒ `mask_000040.png` chứa mask của frame video ~120 nhưng được ghép với `gt_000040.png`
⇒ mIoU sai **mà không có cảnh báo nào**. Bài học "số sai im lặng" tệ hơn số thiếu.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from src.live_tracking import BBOX_NAME, LiveTrackConfig, LiveTrackingSession


class _Result:
    def __init__(self, frame_idx, bbox, mask):
        self.frame_idx = frame_idx
        self.bbox = bbox
        self.mask = mask
        self.elapsed_ms = 5.0


class _CountingEngine:
    """Engine giả đếm số lần gọi — giống SAM 2 thật: `frame_idx` là **số lần process**, không phải
    chỉ số frame video."""

    def __init__(self):
        self.calls = 0

    def start(self, frame, bbox):
        self.calls = 1
        return self._result(frame)

    def process(self, frame):
        self.calls += 1
        return self._result(frame)

    def _result(self, frame):
        mask = np.zeros(frame.shape[:2], bool)
        mask[2:12, 2:12] = True
        return _Result(self.calls - 1, (2, 2, 14, 14), mask)   # idx = số lần gọi tích luỹ


class _StopAfter:
    def __init__(self, checks):
        self._left = checks

    def is_set(self):
        self._left -= 1
        return self._left <= 0


@pytest.fixture
def video_source(write_video, tmp_path):
    frames = np.full((12, 40, 60, 3), 90, np.uint8)
    return str(write_video(tmp_path / "clip.mp4", frames, fps=10))


def _config(source, tmp_path, **kwargs):
    return LiveTrackConfig(source=source, out_dir=tmp_path / "live", display_fps=100, **kwargs)


def _preselect(out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / BBOX_NAME).write_text(json.dumps({"x": 2, "y": 2, "w": 12, "h": 12}),
                                     encoding="utf-8")


def test_ten_file_theo_frame_video_khi_vos_every_lon_hon_1(video_source, tmp_path):
    """`vos_every=3`: lần VOS thứ 4 xảy ra ở frame video 9 ⇒ file phải là `mask_000009.png`."""
    out = tmp_path / "live"
    _preselect(out)
    dump_dir = tmp_path / "masks"
    session = LiveTrackingSession(_CountingEngine(), _config(
        video_source, tmp_path, vos_every=3, loop_files=True,
        dump_mask_frames=(0, 9, 12), dump_mask_dir=str(dump_dir)))

    session.run(stop_event=_StopAfter(60))

    ten = sorted(p.name for p in dump_dir.glob("mask_*.png")) if dump_dir.is_dir() else []
    assert ten, "phải có ít nhất frame video 0 (lần start)"
    assert "mask_000000.png" in ten
    # Bẫy cũ: tên theo bộ đếm engine ⇒ chỉ có mask_000001/000004/… lệch so với GT
    assert all(not n.startswith("mask_000001") for n in ten), ten


def test_khong_ghi_file_cho_frame_khong_co_lan_vos(video_source, tmp_path, capsys):
    """Frame 1 không chia hết cho `vos_every=3` ⇒ không có mask, và phải CẢNH BÁO nêu lý do."""
    out = tmp_path / "live"
    _preselect(out)
    dump_dir = tmp_path / "masks"
    session = LiveTrackingSession(_CountingEngine(), _config(
        video_source, tmp_path, vos_every=3, loop_files=True,
        dump_mask_frames=(1,), dump_mask_dir=str(dump_dir)))

    session.run(stop_event=_StopAfter(40))

    assert not list(dump_dir.glob("mask_*.png")) if dump_dir.is_dir() else True
    assert "vos_every=3" in capsys.readouterr().out


def test_mask_none_khong_ghi_file_gia(video_source, tmp_path, capsys):
    """Model không trả mask: KHÔNG ghi ảnh 1×1 (nó trông như "đã đo" và làm chấm điểm lệch kích thước)."""
    class _NoMask(_CountingEngine):
        def _result(self, frame):
            return _Result(self.calls - 1, (2, 2, 14, 14), None)

    out = tmp_path / "live"
    _preselect(out)
    dump_dir = tmp_path / "masks"
    session = LiveTrackingSession(_NoMask(), _config(
        video_source, tmp_path, vos_every=1, loop_files=True,
        dump_mask_frames=(0,), dump_mask_dir=str(dump_dir)))

    session.run(stop_event=_StopAfter(20))

    assert not list(dump_dir.glob("mask_*.png")) if dump_dir.is_dir() else True
    assert "không trả mask" in capsys.readouterr().out


def test_parse_dump_frames_tu_choi_so_am():
    with pytest.raises(ValueError, match="không âm"):
        LiveTrackConfig(source="0", out_dir=Path("x"), dump_mask_frames="-1,5")


def test_parse_dump_frames_bo_trung_va_sap_xep():
    cfg = LiveTrackConfig(source="0", out_dir=Path("x"), dump_mask_frames="12, 3;3,0")
    assert cfg.dump_mask_frames == (0, 3, 12)
