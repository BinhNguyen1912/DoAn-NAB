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


class TestDumpMaskCanBBoxCoSan:
    """P1 review 17-11 (ticket #36): dump mask chỉ đúng khi phiên bám từ frame ĐẦU.

    Nếu `bbox.json` chưa có, phiên đọc N frame trong lúc chờ chọn ô ⇒ `mask_NNNNNN.png` là frame của
    PHIÊN, không phải của clip; và vì nguồn `loop_files` quay vòng nên **không** suy ra được frame clip
    từ N (`offset + idx` phải mod độ dài clip). Chặn ở cửa vào thay vì đoán.
    """

    def test_tu_choi_dump_khi_chua_co_bbox(self, tmp_path, monkeypatch, capsys):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"),
                               "--out-dir", str(tmp_path / "o"),
                               "--dump-mask-frames", "0", "--vos-every", "1"])
        assert exc.value.code == 2
        assert "bbox.json" in capsys.readouterr().err

    def test_co_bbox_roi_thi_khong_bi_chan(self, tmp_path, monkeypatch):
        """Có `bbox.json` ⇒ đi qua cửa validate (rồi dừng ở bước mở nguồn vì file không tồn tại)."""
        out = tmp_path / "o"
        out.mkdir()
        (out / "bbox.json").write_text('{"x":1,"y":1,"w":5,"h":5}', encoding="utf-8")
        try:
            _run(monkeypatch, ["--source", str(tmp_path / "khong-co.mp4"),
                               "--out-dir", str(out),
                               "--dump-mask-frames", "0", "--vos-every", "1"])
        except SystemExit as exc:            # chặn Ở BƯỚC KHÁC (không thấy nguồn) là chấp nhận được
            assert "bbox.json" not in str(exc.value.code)

    def test_bbox_giai_ma_va_ghi_bbox_json(self, tmp_path, monkeypatch, capsys):
        """`--bbox x,y,w,h` (dạng xywh) ghi `bbox.json` TRƯỚC khi phiên chạy ⇒ dump đúng frame clip."""
        import json as _json

        out = tmp_path / "o"
        try:
            _run(monkeypatch, ["--source", str(tmp_path / "khong-co.mp4"),
                               "--out-dir", str(out), "--bbox", "10,20,30,40",
                               "--dump-mask-frames", "0", "--vos-every", "1"])
        except SystemExit as exc:
            assert "bbox" not in str(exc.value.code), "không được chặn vì lý do bbox khi đã có --bbox"
        assert _json.loads((out / "bbox.json").read_text()) == {"x": 10, "y": 20, "w": 30, "h": 40}

    def test_bbox_xyxy_bi_tu_choi(self, tmp_path, monkeypatch):
        """Lỗi kinh điển của repo: truyền `x1,y1,x2,y2` vào chỗ `x,y,w,h` (AGENTS §6)."""
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"), "--out-dir", str(tmp_path / "o"),
                               "--bbox", "100,100,-90,-60"])   # truyền xyxy ⇒ w/h âm
        assert exc.value.code == 2
