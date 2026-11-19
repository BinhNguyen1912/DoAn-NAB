"""Test hàm THUẦN của `scripts/ab_lk_max_mad.py` (không cần model/video)."""

from __future__ import annotations

import csv

from scripts.ab_lk_max_mad import doc_csv, ket_luan


def _ghi(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_idx", "seq", "vos_ms", "empty", "drift_iou",
                    "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
                    "hien_thi_x1", "hien_thi_y1", "hien_thi_x2", "hien_thi_y2", "lk_ok"])
        w.writerows(rows)
    return path


def test_lk_ok_frac_mau_so_la_so_dong_CO_lk_ok(tmp_path):
    """32/83 dòng trống `lk_ok` từng bị trộn vào mẫu số ⇒ `lk_ok_frac` sai (review 19-11).

    Mẫu số phải là số dòng **có** `lk_ok`, không phải tổng số dòng.
    """
    p = _ghi(tmp_path / "d.csv", [
        [0, 1, 12, 0, "", 1, 1, 9, 9, 1, 1, 9, 9, ""],      # chưa phát ⇒ không có lk_ok
        [3, 2, 12, 0, 0.9, 1, 1, 9, 9, 1, 1, 9, 9, 1],
        [6, 3, 12, 0, 0.8, 1, 1, 9, 9, 1, 1, 9, 9, 0],
        [9, 4, 12, 1, "", "", "", "", "", "", "", "", "", ""],
    ])
    kq = doc_csv(str(p))
    assert kq["n_dong"] == 4
    assert kq["n_lk_do_duoc"] == 2, "chỉ 2 dòng có lk_ok"
    assert kq["lk_ok_n"] == 1 and kq["lk_ok_frac"] == 0.5
    assert kq["drift_n"] == 2 and kq["drift_iou"] == 0.85


def test_loc_khung_bo_mau_ngoai_khung(tmp_path):
    p = _ghi(tmp_path / "d.csv", [
        [5, 1, 12, 0, 0.9, 1, 1, 9, 9, 1, 1, 9, 9, 1],
        [150, 2, 12, 0, 0.3, 1, 1, 9, 9, 1, 1, 9, 9, 0],   # vật đã rời khung
    ])
    kq = doc_csv(str(p), khung=[(0, 110)])
    assert kq["n_dong"] == 1 and kq["lk_ok_frac"] == 1.0


def test_csv_khong_ton_tai_tra_none():
    kq = doc_csv("/tmp/khong_he_ton_tai_12345.csv")
    assert kq["n_dong"] == 0 and kq["lk_ok_frac"] is None and kq["drift_iou"] is None


def _tong(lk, drift, empty=0.0):
    return {"lk_ok_frac": {"mean": lk, "std": 0.01, "n": 3},
            "drift_iou": {"mean": drift, "std": 0.002, "n": 3},
            "empty_frac": {"mean": empty, "std": 0.0, "n": 3}}


def test_ket_luan_doi_mac_dinh_can_tang_2x_va_drift_trong_nguong_nhieu():
    """Đổi mặc định cần: `lk_ok_frac` tăng ≥ 2× VÀ `drift_iou` chênh ≤ 0,010 (ngưỡng ô chai)."""
    du = ket_luan(_tong(0.22, 0.44), _tong(0.57, 0.43))
    assert du["lk_ok_frac_tang_lan"] == 2.59
    assert du["drift_khong_phan_biet_duoc"] is True and du["du_dieu_kien_doi_mac_dinh"] is True


def test_ket_luan_tang_nhung_drift_giam_qua_nguong_thi_KHONG_doi():
    kq = ket_luan(_tong(0.22, 0.44), _tong(0.57, 0.40))   # drift giảm 0,04 > 0,010
    assert kq["du_dieu_kien_doi_mac_dinh"] is False
    assert "KHÔNG đủ" in kq["ket_luan"]


def test_ket_luan_a_bang_0_la_truong_hop_manh_nhat_khong_phai_thieu_du_lieu():
    """`lk_ok_frac` cấu hình cũ = 0 ⇒ tỉ lệ là vô hạn; ghi `None` sẽ bị đọc thành "thiếu dữ liệu"."""
    kq = ket_luan(_tong(0.0, 0.655), _tong(0.63, 0.660))   # drift chênh 0,005 < 0,010
    assert kq["lk_ok_frac_tang_lan"] == "inf"
    assert kq["du_dieu_kien_doi_mac_dinh"] is True


def test_ket_luan_thieu_so_thi_khong_ket_luan():
    kq = ket_luan(_tong(None, None), _tong(0.5, 0.6))
    assert kq["lk_ok_frac_tang_lan"] is None and kq["du_dieu_kien_doi_mac_dinh"] is False
