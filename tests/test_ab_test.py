"""`scripts/ab_test.py` (việc #11) — A/B có kiểm định nhiễu. Phần THUẦN: parse cấu hình + so sánh.

Điều được ghim: **không có ngưỡng nhiễu thì không có kết luận** — `n < 2` phải ra "không kết luận
được", và chênh lệch ≤ std phải ra "không phân biệt được" (AGENTS §6: chênh lệch nhỏ hơn ngưỡng
nhiễu thì cấm viết "tốt hơn").
"""

import pytest

from scripts import ab_test as ab


class TestParseCauHinh:
    def test_doc_binh_thuong(self):
        assert ab.parse_cau_hinh("image_size=192,vos_every=3") == {"image_size": 192, "vos_every": 3}

    def test_mask_smoothing_giu_so_thuc(self):
        assert ab.parse_cau_hinh("mask_smoothing=0.5") == {"mask_smoothing": 0.5}

    def test_khoa_la_bi_tu_choi(self):
        with pytest.raises(ValueError, match="không hỗ trợ"):
            ab.parse_cau_hinh("image_size=192,foo=1")

    def test_ngoai_khoang_bi_tu_choi_som(self):
        """Kiểm ở cửa vào: để worker báo thì ta mất 4 s nạp model mới biết tham số sai."""
        with pytest.raises(ValueError, match="ngoài khoảng"):
            ab.parse_cau_hinh("image_size=4096")

    def test_thieu_dau_bang(self):
        with pytest.raises(ValueError, match="khoá=giá_trị"):
            ab.parse_cau_hinh("image_size")

    def test_rong(self):
        with pytest.raises(ValueError, match="rỗng"):
            ab.parse_cau_hinh(" , ")


class TestSoSanh:
    def test_chenh_lech_lon_hon_nhieu_thi_co_ket_luan(self):
        """Ngưỡng nhiễu = max(spread, sàn tuyệt đối); với `vos_fps` sàn là 0,2 nên ngưỡng 0,2."""
        kq = ab.so_sanh([9.0, 9.1, 8.9], [4.9, 5.0, 5.1], uu_tien=1, key="vos_fps")
        assert kq["ket_luan"] == "A tốt hơn"
        assert kq["nhieu"] == pytest.approx(0.2, abs=1e-9)
        assert kq["spread_a"] == pytest.approx(0.2, abs=1e-9)
        assert kq["n_a"] == 3 and kq["n_b"] == 3

    def test_dung_chung_dinh_nghia_nhieu_voi_repeatability(self):
        """Một định nghĩa nhiễu cho cả repo: `scripts/repeatability.py` nay có caller thật."""
        from scripts import repeatability as rp

        kq = ab.so_sanh([1.0, 2.0, 3.0], [5.0, 6.0, 7.0], uu_tien=1)
        assert kq["nhieu"] == pytest.approx(max(rp.spread([1, 2, 3])["spread"],
                                                rp.spread([5, 6, 7])["spread"]))

    def test_chenh_lech_nho_hon_nhieu_la_khong_phan_biet_duoc(self):
        """Hai dãy chồng nhau: chênh mean 0,3 nhưng độ tản mỗi bên 1,4–1,6 ⇒ inconclusive."""
        kq = ab.so_sanh([9.0, 9.8, 8.2], [9.3, 9.9, 8.7], uu_tien=1)
        assert kq["ket_luan"].startswith("không phân biệt được")

    def test_uu_tien_am_dao_chieu_ket_luan(self):
        """`vos_ms` nhỏ mới tốt: B chậm hơn ⇒ 'A tốt hơn'."""
        kq = ab.so_sanh([90.0, 92.0, 88.0], [140.0, 142.0, 138.0], uu_tien=-1, key="vos_ms")
        assert kq["ket_luan"] == "A tốt hơn"
        assert kq["chenh_lech"] == pytest.approx(50.0)
        assert kq["nhieu"] == pytest.approx(4.0)          # spread mỗi bên = 4

    def test_ba_lan_trung_khit_van_khong_ket_luan_o_chi_so_bi_chan_tran(self):
        """P1 review 14-11: `measured_fps` 29,9 vs 29,8 từng bị kết luận "A tốt hơn" — chênh lệch đó là
        nhiễu lượng tử của `--max-fps 30`, không phải hiệu năng."""
        kq = ab.so_sanh([29.9] * 3, [29.8] * 3, uu_tien=1, key="measured_fps")
        assert kq["ket_luan"].startswith("không kết luận được")
        assert "chặn trần" in kq["ket_luan"]

    def test_lap_trung_khit_van_co_san_nhieu(self):
        """Hai bên trùng khít (`spread = 0`) mà khác nhau 0,1 ms ⇒ vẫn KHÔNG phân biệt được."""
        kq = ab.so_sanh([90.0] * 3, [90.1] * 3, uu_tien=-1, key="vos_ms")
        assert kq["ket_luan"].startswith("không phân biệt được")
        assert kq["nhieu"] == pytest.approx(3.0)          # sàn của vos_ms

    def test_so_do_that_van_thang_du_co_san(self):
        """Sàn không được làm câm phát hiện thật: 90 ms vs 250 ms chênh 160 ≫ sàn 3."""
        kq = ab.so_sanh([90.0] * 3, [250.0] * 3, uu_tien=-1, key="vos_ms")
        assert kq["ket_luan"] == "A tốt hơn"

    def test_n_1_khong_ket_luan_duoc(self):
        kq = ab.so_sanh([9.0], [5.0], uu_tien=1)
        assert kq["ket_luan"].startswith("không kết luận được (n < 2")
        assert kq["n_a"] == 1 and kq["n_b"] == 1
        # PHẢI có đủ khoá: thiếu `std_a` từng làm `main` chết `KeyError` SAU khi artifact đã ghi
        assert kq["std_a"] is None and kq["std_b"] is None and kq["chenh_lech"] is None
        assert kq["nhieu"] is None

    def test_none_bi_bo_khong_thanh_0(self):
        kq = ab.so_sanh([None, 9.0, 9.2], [None, 5.0, 5.2], uu_tien=1)
        assert kq["mean_a"] == pytest.approx(9.1) and kq["mean_b"] == pytest.approx(5.1)

    def test_b_thang_khi_so_lon_hon_va_uu_tien_duong(self):
        kq = ab.so_sanh([5.0, 5.1, 4.9], [9.0, 9.2, 8.8], uu_tien=1)
        assert kq["ket_luan"] == "B tốt hơn"


class TestCliKiemTraDauVao:
    def _clip(self, tmp_path):
        path = tmp_path / "a.mp4"
        path.write_bytes(b"x")
        return path

    def test_ab_giong_het_bi_tu_choi(self, tmp_path, capsys):
        ma = ab.main(["--clip", str(self._clip(tmp_path)), "--bbox", "1,1,10,10",
                      "--a", "image_size=192", "--b", "image_size=192"])
        assert ma == 2 and "giống hệt" in capsys.readouterr().out

    def test_lan_1_bi_tu_choi(self, tmp_path, capsys):
        ma = ab.main(["--clip", str(self._clip(tmp_path)), "--bbox", "1,1,10,10",
                      "--a", "image_size=192", "--b", "image_size=320", "--lan", "1"])
        assert ma == 2 and "n=1" in capsys.readouterr().out

    def test_bbox_suy_bien_bi_tu_choi(self, tmp_path, capsys):
        ma = ab.main(["--clip", str(self._clip(tmp_path)), "--bbox", "1,1,0,10",
                      "--a", "image_size=192", "--b", "image_size=320"])
        assert ma == 2 and "w,h > 0" in capsys.readouterr().out

    def test_clip_khong_ton_tai(self, tmp_path, capsys):
        ma = ab.main(["--clip", str(tmp_path / "khong_co.mp4"), "--bbox", "1,1,10,10",
                      "--a", "image_size=192", "--b", "image_size=320"])
        assert ma == 2 and "không thấy clip" in capsys.readouterr().out


class TestChayThatGia:
    def test_artifact_co_provenance_va_bang_ket_luan(self, tmp_path, monkeypatch, capsys):
        """Chạy với `_run_once` giả: kiểm artifact + bảng, không nạp model."""
        clip = tmp_path / "a.mp4"
        clip.write_bytes(b"x")
        def fake(*_a, **_k):
            return {"measured_fps": 29.8, "vos_fps": 9.0, "vos_ms": 90.0, "mask_age_p95": 300.0}

        monkeypatch.setattr(ab, "_run_once", fake)
        import scripts.measure_watchdog as mw

        monkeypatch.setattr(mw, "_git_provenance", lambda: ("abc1234", False, False, None))
        out = tmp_path / "ab.json"
        ma = ab.main(["--clip", str(clip), "--bbox", "1,1,10,10",
                      "--a", "image_size=192,vos_every=3", "--b", "image_size=320,vos_every=3",
                      "--lan", "3", "--frames", "1", "--out", str(out)])
        assert ma == 0
        payload = out.read_text(encoding="utf-8")
        assert '"git_rev": "abc1234"' in payload
        assert "chèn kẽ" in payload
        text = capsys.readouterr().out
        assert "nhiễu" in text and "không phân biệt được" in text


class TestLoiKhongBiBoQua:
    """AGENTS §6: "không phát hiện được là THẤT BẠI, không phải đạt"."""

    def test_toan_bo_lan_chay_loi_thi_exit_1(self, tmp_path, capsys):
        clip = tmp_path / "a.mp4"
        clip.write_bytes(b"x")
        import scripts.measure_watchdog as mw

        mw_orig = mw._git_provenance
        import scripts.ab_test as ab2

        ab2._run_once = lambda *a, **k: {"loi": "worker thoát mã 1"}
        try:
            ma = ab2.main(["--clip", str(clip), "--bbox", "1,1,10,10",
                           "--a", "image_size=192", "--b", "image_size=320",
                           "--lan", "2", "--out", str(tmp_path / "ab.json")])
        finally:
            del ab2._run_once
            mw._git_provenance = mw_orig
        assert ma == 1
        assert "KHÔNG ĐO ĐƯỢC" in capsys.readouterr().out


class TestBangKhongCrashKhiMotBenCo1Mau:
    """P1 review hẹp 14-11: `so_sanh` nhánh `n < 2` trả dict **thiếu** `std_a`/`std_b`, nhưng `main`
    rẽ nhánh theo `mean_*` ⇒ `KeyError` ngay sau khi artifact đã ghi: bảng không in, tiến trình chết
    bằng traceback. Kích hoạt thật khi `_run_once` trả `{"loi": …}` ở 2/3 lần (state=error/timeout) —
    log 14-11 đã ghi "3 lần đo đầu có lỗi rải rác"."""

    def test_2_tren_3_lan_loi_thi_van_in_bang(self, tmp_path, capsys):
        import scripts.ab_test as ab2

        good = {"measured_fps": 29.7, "vos_fps": 7.5, "vos_ms": 100.0, "mask_age_p95": 320.0}
        dem = {"a": 0}

        def fake(clip, bbox, image_size, vos_every, frames, device, timeout, **kw):
            if image_size == 192:
                dem["a"] += 1
                return {"loi": "worker thoát mã 1"} if dem["a"] <= 2 else dict(good)
            return dict(good, vos_fps=3.1, vos_ms=280.0, mask_age_p95=650.0)

        ab2.__dict__["_run_once"] = fake
        try:
            clip = tmp_path / "a.mp4"
            clip.write_bytes(b"x")
            ma = ab2.main(["--clip", str(clip), "--bbox", "1,1,10,10",
                           "--a", "image_size=192", "--b", "image_size=320",
                           "--lan", "3", "--out", str(tmp_path / "ab.json")])
        finally:
            del ab2._run_once
        out = capsys.readouterr().out
        assert "| chỉ số |" in out, "bảng phải in được (trước đây KeyError)"
        assert "lần chạy LỖI: A 2/3" in out
        assert ma == 0
