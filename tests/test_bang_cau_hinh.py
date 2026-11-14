"""`scripts/bang_cau_hinh.py` (việc #5) — phần THUẦN: tổng hợp, ngưỡng nhiễu, bảng markdown.

Không chạy model ở đây (mỗi lần chạy thật tốn ~10 s và cần checkpoint). Điều được ghim:
- `n = 1` ⇒ `std = None` (không được bịa ±0,0 rồi kết luận "ổn định");
- giá trị `None` (chưa đo) **không** bị tính thành 0 khi lấy trung bình;
- chênh lệch **nhỏ hơn** độ lệch chuẩn ⇒ coi là "không phân biệt được";
- lần chạy LỖI không được làm hỏng dòng thống kê, nhưng phải được đếm (`so_lan_loi`).
"""

import json

import pytest

from scripts import bang_cau_hinh as bch


def _row(**kw):
    base = {"measured_fps": 29.8, "vos_fps": 9.0, "vos_ms": 90.0, "pre_ms": 12.0,
            "cycle_ms": 100.0, "mask_age_total_ms": 280.0, "mask_age_p95": 290.0,
            "frames": 60, "age_n": 30, "elapsed_s": 9.0}
    base.update(kw)
    return base


class TestThongKe:
    def test_hai_lan_co_std(self):
        s = bch._thong_ke([90.0, 94.0])
        assert s["n"] == 2 and s["mean"] == pytest.approx(92.0)
        assert s["std"] == pytest.approx(2.828, abs=2e-2)   # làm tròn 2 chữ số

    def test_mot_lan_khong_co_std(self):
        """`n = 1` thì std phải None: `±0,0` là lời khẳng định "rất ổn định" mà ta không có căn cứ."""
        s = bch._thong_ke([90.0])
        assert s["n"] == 1 and s["mean"] == 90.0 and s["std"] is None

    def test_none_khong_duoc_tinh_thanh_0(self):
        s = bch._thong_ke([None, 90.0, None, 92.0])
        assert s["n"] == 2 and s["mean"] == pytest.approx(91.0)

    def test_toan_none_thi_mean_none(self):
        s = bch._thong_ke([None, None])
        assert s == {"n": 0, "mean": None, "std": None, "min": None, "max": None}

    def test_bool_khong_bi_coi_la_so(self):
        s = bch._thong_ke([True, True])
        assert s["n"] == 0


class TestTongHop:
    def test_dem_loi_rieng_va_van_co_thong_ke(self):
        runs = {(192, 3): [_row(), {"loi": "quá 180 s"}, _row(vos_ms=96.0)]}
        bang = bch.tong_hop(None, [192], [3], runs)
        dong = bang["192_3"]
        assert dong["so_lan"] == 3 and dong["so_lan_loi"] == 1
        assert dong["vos_ms"]["n"] == 2
        assert dong["loi"] == ["quá 180 s"]

    def test_cau_hinh_khong_chay_duoc_van_co_dong(self):
        bang = bch.tong_hop(None, [320], [6], {(320, 6): [{"loi": "worker thoát mã 1"}]})
        dong = bang["320_6"]
        assert dong["so_lan_loi"] == 1
        assert dong["measured_fps"]["mean"] is None        # không bịa 0


class TestNguongNhieu:
    def test_chenh_lech_nho_hon_std_la_khong_phan_biet_duoc(self):
        a = {"vos_fps": {"mean": 8.95, "std": 0.49}}
        b = {"vos_fps": {"mean": 9.30, "std": 0.49}}
        assert bch.chenh_lech_duoi_nhieu(a, b, "vos_fps") is True

    def test_chenh_lech_lon_hon_std_thi_phan_biet_duoc(self):
        a = {"vos_fps": {"mean": 9.0, "std": 0.2}}
        b = {"vos_fps": {"mean": 5.2, "std": 0.2}}
        assert bch.chenh_lech_duoi_nhieu(a, b, "vos_fps") is False

    def test_thieu_so_thi_khong_ket_luan(self):
        assert bch.chenh_lech_duoi_nhieu({"x": {"mean": None}}, {"x": {"mean": 1.0}}, "x") is True


class TestBangMarkdown:
    def _meta(self, **kw):
        base = {"git_rev": "abc1234def", "git_dirty_code": False, "so_lan": 3,
                "moi_truong": "cpu, sam2.1_hiera_tiny, clip binh1.mp4"}
        base.update(kw)
        return base

    def test_co_cot_va_canh_bao_cam_trich(self):
        bang = bch.tong_hop(None, [192], [3], {(192, 3): [_row(), _row()]})
        md = bch.bang_markdown(self._meta(), bang, [192], [3])
        assert "| 192 | 3 |" in md
        assert "không phân biệt được" in md
        assert "cấm viết" in md and "mask 30 FPS" in md
        assert "abc1234" in md

    def test_cay_ban_duoc_neu_ro(self):
        bang = bch.tong_hop(None, [192], [3], {(192, 3): [_row()]})
        md = bch.bang_markdown(self._meta(git_dirty_code=True), bang, [192], [3])
        assert "cây BẨN" in md

    def test_o_thieu_so_la_dash_khong_phai_0(self):
        bang = bch.tong_hop(None, [320], [6], {(320, 6): [{"loi": "x"}]})
        md = bch.bang_markdown(self._meta(), bang, [320], [6])
        assert "—" in md and "0 ±" not in md


class TestCliKiemTraDauVao:
    def test_bbox_suy_bien_bi_tu_choi(self, tmp_path, capsys):
        clip = tmp_path / "a.mp4"
        clip.write_bytes(b"x")
        assert bch.main(["--clip", str(clip), "--bbox", "10,10,0,50"]) == 2
        assert "w,h > 0" in capsys.readouterr().out

    def test_lan_1_bi_canh_bao_la_khong_ket_luan_duoc(self, tmp_path, capsys):
        """`--lan 1` bị TỪ CHỐI (exit 2): bảng không có `±` sẽ bị trích như "ổn định" (AGENTS §6:
        n < 2 thì không kết luận được gì)."""
        clip = tmp_path / "a.mp4"
        clip.write_bytes(b"x")
        assert bch.main(["--clip", str(clip), "--bbox", "10,10,20,20", "--lan", "1"]) == 2

    def test_clip_khong_ton_tai(self, tmp_path, capsys):
        assert bch.main(["--clip", str(tmp_path / "khong_co.mp4"), "--bbox", "1,1,5,5"]) == 2
        assert "không thấy clip" in capsys.readouterr().out


class TestArtifactVaCheck:
    def test_ghi_artifact_va_check_kiem_lai(self, tmp_path, monkeypatch):
        """`--check` phải bắt được file .md lệch artifact (cùng cơ chế với so_lieu_bao_cao.py)."""
        clip = tmp_path / "a.mp4"
        clip.write_bytes(b"x")
        monkeypatch.setattr(bch, "_run_once", lambda *a, **k: _row())
        import scripts.measure_watchdog as mw

        monkeypatch.setattr(mw, "_git_provenance", lambda: ("abc1234", False, False, None))
        out = tmp_path / "art.json"
        md = tmp_path / "bang.md"
        base = ["--clip", str(clip), "--bbox", "10,10,20,20", "--sizes", "192", "--every", "3",
                "--lan", "2", "--frames", "1", "--out", str(out), "--md", str(md)]

        assert bch.main(base) == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["meta"]["git_rev"] == "abc1234"
        assert payload["cau_hinh"]["192_3"]["so_lan"] == 2
        assert md.is_file()

        # `--check` phải THUẦN ĐỌC: không chạy worker, không ghi file (P2 review 14-11)
        goi = {"n": 0}
        monkeypatch.setattr(bch, "_run_once", lambda *a, **k: goi.__setitem__("n", goi["n"] + 1))
        truoc = out.stat().st_mtime_ns
        assert bch.main(base + ["--check"]) == 0          # khớp
        assert goi["n"] == 0, "--check không được chạy phiên worker nào"
        assert out.stat().st_mtime_ns == truoc, "--check không được ghi đè artifact"
        md.write_text(md.read_text(encoding="utf-8").replace("| 192 | 3 |", "| 192 | 3 | (sửa tay)"),
                      encoding="utf-8")
        assert bch.main(base + ["--check"]) == 1          # lệch ⇒ đỏ


class TestAgeNTrongArtifact:
    """P2 review 14-11: cảnh báo nói "p95 trên cửa sổ `age_n`" thì `age_n` phải có trong artifact."""

    def test_tong_hop_giu_age_n_va_frames(self):
        bang = bch.tong_hop(None, [192], [3], {(192, 3): [_row(), _row()]})
        assert bang["192_3"]["age_n"]["mean"] == 30
        assert bang["192_3"]["frames"]["mean"] == 60

    def test_bang_markdown_co_cot_age_n(self):
        bang = bch.tong_hop(None, [192], [3], {(192, 3): [_row()]})
        md = bch.bang_markdown({"do_luc": "x", "moi_truong": "cpu", "git_rev": "abc1234",
                                "so_lan": 2, "git_dirty_code": False}, bang, [192], [3])
        header = next(ln for ln in md.splitlines() if ln.startswith("| image_size"))
        assert "| age_n |" in header
        assert "| 30 |" in md
