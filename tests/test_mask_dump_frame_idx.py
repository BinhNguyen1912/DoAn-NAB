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


def test_manifest_ghi_dieu_kien_sinh_mask(video_source, tmp_path):
    """Manifest trả lời "mask này sinh ở image_size/vos_every/ô chọn nào" — nếu thiếu, artifact mIoU
    không tự kiểm được cấu hình (P0/P2 review hẹp 14-11)."""
    import json

    out = tmp_path / "live"
    _preselect(out)
    dump_dir = tmp_path / "masks"
    session = LiveTrackingSession(_CountingEngine(), _config(
        video_source, tmp_path, vos_every=1, loop_files=True,
        dump_mask_frames=(0,), dump_mask_dir=str(dump_dir)))

    session.run(stop_event=_StopAfter(20))

    man = json.loads((dump_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "image_size" in man and man["vos_every"] == 1
    assert man["bbox_xywh"] == [2, 2, 12, 12]
    assert "THÔ" in man["ghi_chu"]


def test_record_vos_khong_tu_gan_dump_ms(video_source, tmp_path):
    """P3 review độc lập 17-11: `dump_ms` phải gán CÙNG lock với `post_ms` ở người gọi.

    Nếu `_record_vos` tự gán `_stats.dump_ms` rồi người gọi mới gán `post_ms`, một lần VOS chen giữa
    sẽ khiến `status.json` ghép `post_ms` của lần N với `dump_ms` của lần N+1 (hai pha của hai lần
    chạy khác nhau, đúng thứ snapshot `_vos_state` sinh ra để chặn).
    """
    out = tmp_path / "live"
    _preselect(out)
    dump_dir = tmp_path / "masks"
    session = LiveTrackingSession(_CountingEngine(), _config(
        video_source, tmp_path, vos_every=1, loop_files=True,
        dump_mask_frames=(0,), dump_mask_dir=str(dump_dir)))

    result = session._engine.start(np.full((40, 60, 3), 90, np.uint8), (2, 2, 14, 14))
    dump_ms, da_ghi = session._record_vos(result, frame_video=0)

    assert da_ghi is True and dump_ms >= 0.0
    assert session._stats.dump_ms is None, "`_record_vos` không được tự gán `_stats.dump_ms`"

    session._after_vos(np.full((40, 60, 3), 90, np.uint8), result)
    assert session._stats.dump_ms is not None, "người gọi gán `dump_ms` cùng lock với `post_ms`"


def test_chon_o_ngay_tu_dau_thi_manifest_khai_0(video_source, tmp_path, capsys):
    """Đường CLI `--bbox` (ô chọn có sẵn): offset 0, tên file đúng là frame của clip."""
    out = tmp_path / "live"
    _preselect(out)
    dump_dir = tmp_path / "masks"
    session = LiveTrackingSession(_CountingEngine(), _config(
        video_source, tmp_path, vos_every=1, loop_files=True,
        dump_mask_frames=(0,), dump_mask_dir=str(dump_dir)))

    session.run(stop_event=_StopAfter(20))

    man = json.loads((dump_dir / "manifest.json").read_text(encoding="utf-8"))
    assert man["frame_goc_cua_phien"] == 0
    assert (dump_dir / "mask_000000.png").is_file()
    assert "TỪ CHỐI" not in capsys.readouterr().out


def test_chon_o_MUON_thi_TU_CHOI_dump(video_source, tmp_path, capsys):
    """P1/P2 review 17-11: phiên chờ chọn ô ⇒ tên `mask_NNNNNN.png` KHÔNG phải frame của clip (nguồn
    còn quay vòng nên `offset + idx` cũng sai) ⇒ **từ chối ghi** thay vì ghi file mang tên sai frame."""
    out = tmp_path / "live"
    out.mkdir(parents=True, exist_ok=True)          # KHÔNG đặt bbox.json trước
    dump_dir = tmp_path / "masks"
    session = LiveTrackingSession(_CountingEngine(), _config(
        video_source, tmp_path, vos_every=1, loop_files=True,
        dump_mask_frames=(0, 5, 8), dump_mask_dir=str(dump_dir)))

    so_lan = {"n": 0}

    class _ChonOSau3Lan:
        """`bbox.json` chỉ xuất hiện ở lần kiểm thứ 3 ⇒ phiên đọc 2 frame trong lúc chờ chọn ô."""

        def is_set(self):
            so_lan["n"] += 1
            if so_lan["n"] == 3:
                _preselect(out)
            return so_lan["n"] > 12

    session.run(stop_event=_ChonOSau3Lan())

    assert session._frame_goc > 0, "phiên phải đếm được số frame đã đọc lúc chờ chọn ô"
    assert not list(dump_dir.glob("mask_*.png")), (
        "phiên chờ chọn ô KHÔNG được ghi mask mang tên frame của phiên")
    man = dump_dir / "manifest.json"
    assert not man.exists(), "không ghi file ⇒ không được ghi manifest như thể đã đo"
    out_txt = capsys.readouterr().out
    assert "TỪ CHỐI dump mask" in out_txt and "ticket #36" in out_txt
    # Cảnh báo MỘT lần nhưng TỪ CHỐI **mọi** frame yêu cầu: bản trước đặt cả hai trong
    # `not self._da_canh_bao_offset` ⇒ từ frame yêu cầu thứ hai guard hết tác dụng và ghi đúng thứ
    # file mà ticket cấm (P1 vòng review 2). Test chỉ xanh khi guard nằm NGOÀI cờ đó.
    assert out_txt.count("TỪ CHỐI dump mask") == 1, "chỉ cảnh báo một lần"
    assert "TỪ CHỐI dump 3 frame" in out_txt, "phải nêu CẢ số frame bị từ chối"


def test_run_hai_lan_tren_cung_session_bi_tu_choi(video_source, tmp_path):
    """`run()` lần hai: `_frame_index`/`_dumped` không reset ⇒ tên file tiếp tục từ lần trước (lệch
    frame) và `_da_canh_bao_offset` đã True nên guard offset mất tác dụng (P3 vòng review 2)."""
    out = tmp_path / "live"
    _preselect(out)
    session = LiveTrackingSession(_CountingEngine(), _config(
        video_source, tmp_path, vos_every=1, loop_files=False))
    session.run(stop_event=_StopAfter(6))

    with pytest.raises(RuntimeError, match="chỉ được gọi MỘT lần"):
        session.run(stop_event=_StopAfter(6))


def test_quay_vong_nguon_thi_TU_CHOI_dump(video_source, tmp_path, capsys):
    """P3 vòng review 3: sau khi nguồn quay vòng (`loop_files`, mặc định BẬT), `_frame_index` tiếp tục
    tăng ⇒ `mask_000015.png` trên clip 12 frame thực chất là frame 3 ⇒ tên SAI. Không bị guard offset
    bắt vì `_frame_goc == 0`."""
    out = tmp_path / "live"
    _preselect(out)
    dump_dir = tmp_path / "masks"
    frames = list(range(0, 20))          # yêu cầu frame vượt quá độ dài clip (12) ⇒ phải quay vòng
    session = LiveTrackingSession(_CountingEngine(), _config(
        video_source, tmp_path, vos_every=1, loop_files=True,
        dump_mask_frames=tuple(frames), dump_mask_dir=str(dump_dir)))

    session.run(stop_event=_StopAfter(40))

    assert session._so_lan_quay_vong >= 1, "nguồn phải đã quay vòng"
    ten = sorted(p.name for p in dump_dir.glob("mask_*.png"))
    assert ten == [f"mask_{i:06d}.png" for i in range(12)], (
        f"chỉ được ghi mask của 12 frame THẬT của clip, thấy {ten}")
    assert "quay vòng" in capsys.readouterr().out


def test_manifest_ghim_frames_da_ghi(video_source, tmp_path):
    """P2 vòng review 3: xoá dòng `"frames_da_ghi": sorted(self._dumped)` thì cổng ở `score_miou` biến
    mất mà KHÔNG test nào đỏ. Ghim producer."""
    out = tmp_path / "live"
    _preselect(out)
    dump_dir = tmp_path / "masks"
    session = LiveTrackingSession(_CountingEngine(), _config(
        video_source, tmp_path, vos_every=1, loop_files=False,
        dump_mask_frames=(0, 4), dump_mask_dir=str(dump_dir)))

    session.run(stop_event=_StopAfter(20))

    man = json.loads((dump_dir / "manifest.json").read_text(encoding="utf-8"))
    assert man["frames_da_ghi"] == [0, 4]
    assert man["frames_yeu_cau"] == [0, 4]
