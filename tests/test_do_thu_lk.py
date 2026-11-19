"""Test cho `scripts/do_thu_lk.py` — phần THUẦN (không cần video/checkpoint)."""

from __future__ import annotations

import csv

import pytest

from scripts.do_thu_lk import SAI_NGUONG, cap_ke, doc_moc, tom_tat


def _ghi_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["frame_idx", "seq", "vos_ms", "empty", "drift_iou",
                         "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
                         "hien_thi_x1", "hien_thi_y1", "hien_thi_x2", "hien_thi_y2", "lk_ok"])
        writer.writerows(rows)
    return path


def test_doc_moc_bo_dong_khong_co_bbox(tmp_path):
    """Dòng mask rỗng (bbox trống) là "GT rỗng" — phải BỎ, không được thành mốc (0,0,0,0).

    Bẫy quen của repo: ô diện tích 0 làm IoU trả `None`/0 và kéo mọi chỉ số lệch một cách vô nghĩa.
    """
    path = _ghi_csv(tmp_path / "d.csv", [
        [5, 1, 12.0, 0, 0.9, 10, 20, 40, 80, 10, 20, 40, 80, 1],
        [8, 2, 12.0, 1, "", "", "", "", "", "", "", "", "", ""],       # mask rỗng ⇒ bỏ
        [9, 3, 12.0, 0, 0.8, 30, 30, 30, 90, "", "", "", "", 0],      # x1 == x2 ⇒ bỏ
        [12, 4, 12.0, 0, 0.7, 11, 21, 41, 81, 11, 21, 41, 81, 1],
    ])
    assert doc_moc(path) == {5: (10, 20, 40, 80), 12: (11, 21, 41, 81)}


def test_cap_ke_la_hai_lan_vos_lien_tiep():
    """Cặp phải là (base, target) = hai lần VOS liên tiếp, KHÔNG phải (a,b) bất kỳ."""
    moc = {0: (0, 0, 9, 9), 3: (0, 0, 9, 9), 7: (0, 0, 9, 9)}
    assert cap_ke(moc) == [(0, 3), (3, 7)]
    assert cap_ke(moc, toi_da=1) == [(0, 3)]
    assert cap_ke({4: (0, 0, 9, 9)}) == []


def _dong(base, target, ok, iou):
    return {"base": base, "target": target, "ok": ok, "box": [0, 0, 1, 1], "iou": iou}


def test_tom_tat_tach_ok_khoi_iou_va_dem_nhan_bua():
    """Ba đại lượng phải đo riêng: `ok_frac` (dám nhận), `iou_median_khi_ok` (nhận có đúng không),
    `ok_va_sai_frac` (nhận mà sai — nguy hiểm nhất vì HUD không cảnh báo)."""
    ket_qua = [
        _dong(0, 3, True, 0.95),
        _dong(3, 7, True, 0.90),
        _dong(7, 9, True, 0.40),      # ok mà sai ⇒ phải nằm trong ok_va_sai
        _dong(9, 12, False, 0.10),    # not-ok ⇒ KHÔNG được tính vào iou_median_khi_ok
    ]
    kq = tom_tat(ket_qua, max_mad=6.0, grid=8)
    assert kq["n_cap"] == 4
    assert kq["ok_n"] == 3 and kq["ok_frac"] == 0.75
    assert kq["iou_median_khi_ok"] == 0.9, "trung vị chỉ trên mẫu ok"
    # Trung vị trên TẤT CẢ mẫu = (0,40 + 0,90)/2 = 0,65 — thấp hơn hẳn "khi-ok" 0,90 vì gồm cả mẫu
    # not-ok (ô BASE bị phát lại). Đây chính là lý do phải đọc chỉ số "khi-ok" khi chọn `max_mad`.
    assert kq["iou_median_tat_ca"] == pytest.approx(0.65, abs=0.005)
    assert kq["ok_va_sai_n"] == 1 and kq["ok_va_sai_frac"] == 0.333
    assert SAI_NGUONG == 0.5


def test_tom_tat_rong_tra_none_khong_tra_0():
    """Không có cặp nào ⇒ `None` + `n_cap 0` (bẫy "0,0 nghĩa là đã đo, bằng 0")."""
    kq = tom_tat([], max_mad=1.5, grid=8)
    assert kq["n_cap"] == 0 and kq["ok_frac"] is None
    assert kq["iou_median_khi_ok"] is None and kq["ok_va_sai_frac"] is None


def test_tom_tat_bo_iou_none_khoi_trung_vi():
    """IoU `None` (ô diện tích 0) phải BỎ khỏi trung vị, không quy thành 0,0."""
    kq = tom_tat([_dong(0, 3, True, None), _dong(3, 7, True, 0.8)], max_mad=1.5, grid=8)
    assert kq["iou_median_khi_ok"] == 0.8
    assert kq["ok_n"] == 2
