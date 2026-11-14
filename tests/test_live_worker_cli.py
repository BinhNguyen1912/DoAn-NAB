"""Kiểm validate Ở CỬA VÀO của `tools/live_worker.py` (không nạp model — argparse dừng trước).

Vì sao cần: `--dump-mask-frames` là dụng cụ đo mIoU, và một tham số sai không được biến thành
"số đo trông hợp lý". `main()` đọc `sys.argv`, nên test gán `monkeypatch.setattr(sys, "argv", ...)`.
"""

import sys

import pytest

import tools.live_worker as lw


def _parser():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--dump-mask-frames", default="")
    p.add_argument("--vos-every", type=int, default=3)
    return p


def _run(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["live_worker.py", *argv])
    return lw.main()


class TestDumpMaskCanVosEvery1:
    """P0 (dư âm) review hẹp 14-11: với `vos_every > 1` model KHÔNG hề thấy frame không chia hết cho
    N ⇒ mask của frame đó không tồn tại. Cho chạy rồi cảnh báo cuối phiên là quá muộn: người dùng đã
    tưởng có mask của frame 40 và chấm GT vào một thư mục thiếu file."""

    def test_tu_choi_dump_khi_vos_every_lon_hon_1(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"),
                               "--out-dir", str(tmp_path / "o"),
                               "--dump-mask-frames", "0,40", "--vos-every", "3"])
        assert exc.value.code == 2

    def test_frame_am_bi_tu_choi(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"),
                               "--out-dir", str(tmp_path / "o"),
                               "--dump-mask-frames", "-1", "--vos-every", "1"])
        assert exc.value.code == 2

    def test_frame_khong_phai_so_bi_tu_choi(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"),
                               "--out-dir", str(tmp_path / "o"),
                               "--dump-mask-frames", "abc", "--vos-every", "1"])
        assert exc.value.code == 2

    def test_vos_every_1_khong_bi_chan_o_buoc_validate(self, tmp_path):
        """Không được chặn nhầm cấu hình ĐÚNG (`vos_every=1` + dump). Kiểm bằng chính hàm validate
        (không gọi `main` — nó nạp model 20–240 s và mở nguồn, không liên quan điều đang kiểm)."""
        assert lw._kiem_dump_mask_args(_parser(), "0,4,8", 1) == [0, 4, 8]
