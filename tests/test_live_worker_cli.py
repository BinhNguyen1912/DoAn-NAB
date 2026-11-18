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


class _DungNgaySauCuaVao(Exception):
    """Sentinel: `main()` đã qua các cửa validate VÀ chưa nạp model (CI không có `sam2`)."""


def _sentinel():
    raise _DungNgaySauCuaVao


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
        """Có `bbox.json` ⇒ đi QUA cửa validate (dừng ngay sau đó bằng một sentinel).

        Không để chạy tới `TrackerEngine`: CI ubuntu **không có `sam2`** ⇒
        `ModuleNotFoundError: No module named 'sam2'` chứ không phải lỗi của test này (CI đã bắt đúng
        18-11). Sentinel đặt ở `_cuda_available` — bước đầu tiên SAU cửa vào.
        """
        out = tmp_path / "o"
        out.mkdir()
        (out / "bbox.json").write_text('{"x":1,"y":1,"w":5,"h":5}', encoding="utf-8")
        monkeypatch.setattr(lw, "_cuda_available", _sentinel)
        with pytest.raises(_DungNgaySauCuaVao):
            _run(monkeypatch, ["--source", str(tmp_path / "khong-co.mp4"),
                               "--out-dir", str(out),
                               "--dump-mask-frames", "0", "--vos-every", "1"])

    def test_bbox_giai_ma_va_ghi_bbox_json(self, tmp_path, monkeypatch, capsys):
        """`--bbox x,y,w,h` (dạng xywh) ghi `bbox.json` TRƯỚC khi phiên chạy ⇒ dump đúng frame clip."""
        import json as _json

        out = tmp_path / "o"
        monkeypatch.setattr(lw, "_cuda_available", _sentinel)
        with pytest.raises(_DungNgaySauCuaVao):   # qua được cửa vào ⇒ không bị chặn vì bbox
            _run(monkeypatch, ["--source", str(tmp_path / "khong-co.mp4"),
                               "--out-dir", str(out), "--bbox", "10,20,30,40",
                               "--dump-mask-frames", "0", "--vos-every", "1"])
        assert _json.loads((out / "bbox.json").read_text()) == {"x": 10, "y": 20, "w": 30, "h": 40}

    def test_bbox_xyxy_bi_tu_choi(self, tmp_path, monkeypatch):
        """Lỗi kinh điển của repo: truyền `x1,y1,x2,y2` vào chỗ `x,y,w,h` (AGENTS §6)."""
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"), "--out-dir", str(tmp_path / "o"),
                               "--bbox", "100,100,-90,-60"])   # truyền xyxy ⇒ w/h âm
        assert exc.value.code == 2

    def test_bbox_so_thuc_bi_tu_choi(self, tmp_path, monkeypatch):
        """`read_bbox` đọc bằng `int()` ⇒ `10,20,0.5,0.5` thành hộp RỖNG `w=h=0` lúc chạy.

        Guard `w > 0` trên số thực không bắt được (0.5 > 0), nên phải đòi SỐ NGUYÊN ngay ở cửa vào
        (P3 vòng review 2; tài liệu đã quy ước "hộp phải là số nguyên").
        """
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"), "--out-dir", str(tmp_path / "o"),
                               "--bbox", "10,20,0.5,0.5"])
        assert exc.value.code == 2

    def test_bbox_toa_do_am_bi_tu_choi(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"), "--out-dir", str(tmp_path / "o"),
                               "--bbox", "-5,10,20,20"])
        assert exc.value.code == 2

    def test_bbox_hong_trong_file_bi_tu_choi(self, tmp_path, monkeypatch, capsys):
        """`bbox.json` viết dở (`{"x":1}`) vẫn `.exists()` ⇒ phải kiểm ĐỌC ĐƯỢC, không chỉ tồn tại."""
        out = tmp_path / "o"
        out.mkdir()
        (out / "bbox.json").write_text('{"x":1}', encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"), "--out-dir", str(out),
                               "--dump-mask-frames", "0", "--vos-every", "1"])
        assert exc.value.code == 2
        assert "ĐỌC ĐƯỢC" in capsys.readouterr().err

    def test_bbox_khong_duoc_ghi_khi_lenh_sai_tham_so(self, tmp_path, monkeypatch):
        """Ghi bbox.json TRƯỚC validate sẽ để lại ô cũ rác cho lần chạy sau (P3 vòng review 2)."""
        out = tmp_path / "o"
        with pytest.raises(SystemExit):
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"), "--out-dir", str(out),
                               "--bbox", "10,20,30,40", "--vos-every", "0"])
        assert not (out / "bbox.json").exists(), "lệnh bị từ chối thì không được để lại bbox.json"


class TestCauHinhDumpMaskLaSo:
    """P3 vòng review 3: `cau_hinh.dump_mask_frames` từng là **danh sách KÝ TỰ** (`['0', ',', '6']`)
    vì main truyền chuỗi `"0,6"` vào `cau_hinh_yeu_cau` (hàm đó `list(...)`). `status.json` khai sai
    đúng thứ mà `score_miou` dùng để đối chiếu."""

    def test_truyen_list_so_khong_phai_chuoi(self):
        from src.live_tracking import cau_hinh_yeu_cau

        assert cau_hinh_yeu_cau(dump_mask_frames=[0, 6, 12])["dump_mask_frames"] == [0, 6, 12]

    def test_main_truyen_list_so(self, tmp_path, monkeypatch):
        """Đường thật: `--dump-mask-frames "0,6"` ⇒ `cau_hinh` ghi `[0, 6]` (main parse TRƯỚC)."""
        import json as _json

        monkeypatch.setattr(lw, "_cuda_available", _sentinel)
        out = tmp_path / "o"
        out.mkdir()
        (out / "bbox.json").write_text('{"x":1,"y":1,"w":5,"h":5}', encoding="utf-8")
        with pytest.raises(_DungNgaySauCuaVao):
            _run(monkeypatch, ["--source", str(tmp_path / "khong-co.mp4"), "--out-dir", str(out),
                               "--dump-mask-frames", "6,0,6", "--vos-every", "1"])
        cau_hinh = _json.loads((out / "status.json").read_text(encoding="utf-8"))["cau_hinh"]
        # Đúng bằng tập SẼ THI HÀNH (`LiveTrackConfig` cũng `sorted(set(...))`) ⇒ `loading` và
        # `running` của cùng phiên không khai hai giá trị khác nhau (P3 vòng review 4).
        assert cau_hinh["dump_mask_frames"] == [0, 6]


class TestBboxKhongCuopPhienKhac:
    """Ticket #37: `--bbox` ghi `<out-dir>/bbox.json` mà thư mục đó có thể là của một phiên API đang
    `waiting_selection` ⇒ ghi vào là cướp ô chọn của phiên đó, không cảnh báo."""

    def test_tu_choi_khi_co_phien_khac_dang_giu(self, tmp_path, monkeypatch, capsys):
        import os

        out = tmp_path / "live"
        out.mkdir()
        # pid sống thật nhưng KHÔNG phải mình: dùng tiến trình con của chính test.
        import subprocess

        proc = subprocess.Popen(["sleep", "30"])
        try:
            (out / "worker.pid").write_text(str(proc.pid), encoding="utf-8")
            monkeypatch.setattr(lw, "_cuda_available", _sentinel)
            with pytest.raises(SystemExit) as exc:
                _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"), "--out-dir", str(out),
                                   "--bbox", "10,20,30,40"])
            assert exc.value.code == 2
            assert "đang bị một phiên live khác dùng" in capsys.readouterr().err
            assert not (out / "bbox.json").exists(), "bị chặn thì không được ghi bbox.json"
        finally:
            proc.kill()
            proc.wait()
            assert proc.pid != os.getpid()

    def test_pid_da_chet_thi_khong_chan(self, tmp_path, monkeypatch):
        """`worker.pid` của phiên cũ đã chết (kể cả zombie) ⇒ không được chặn oan."""
        out = tmp_path / "live"
        out.mkdir()
        import subprocess

        proc = subprocess.Popen(["true"])
        proc.wait()                      # đã chết + đã reap ⇒ /proc có thể còn (zombie) hoặc không
        (out / "worker.pid").write_text(str(proc.pid), encoding="utf-8")
        monkeypatch.setattr(lw, "_cuda_available", _sentinel)
        with pytest.raises(_DungNgaySauCuaVao):     # qua được cửa ⇒ không bị chặn vì pid
            _run(monkeypatch, ["--source", str(tmp_path / "a.mp4"), "--out-dir", str(out),
                               "--bbox", "10,20,30,40"])
