"""Test hàm THUẦN của `scripts/ab_o_hien_thi_vs_gt.py` (không cần model/video)."""

from __future__ import annotations

import json

import pytest

from scripts.ab_o_hien_thi_vs_gt import cham, hop_tu_gt, so_sanh, tong_hop


def _gt_dir(tmp_path, frames_masks, rong=()):
    """Dựng `docs/gt/<tên>` tối thiểu: index.json + gt_%06d.png (mask 100×100)."""
    import cv2
    import numpy as np

    d = tmp_path / "gt"
    d.mkdir()
    (d / "index.json").write_text(json.dumps({
        "frames": [{"frame_idx": f} for f in frames_masks],
        "gt_rong": list(rong), "dang_gt": "silhouette"}), encoding="utf-8")
    for frame, box in frames_masks.items():
        m = np.zeros((100, 100), dtype=np.uint8)
        if box is not None:
            x1, y1, x2, y2 = box
            m[y1:y2 + 1, x1:x2 + 1] = 255
        cv2.imwrite(str(d / f"gt_{frame:06d}.png"), m)
    return d


def test_hop_tu_gt_suy_hop_tu_mask_va_bo_gt_rong(tmp_path):
    """Hộp GT phải là **bao** của mask người tô; frame `gt_rong` bị bỏ (không có vật ⇒ không chấm)."""
    d = _gt_dir(tmp_path, {0: (10, 20, 30, 40), 7: None}, rong=[7])
    assert hop_tu_gt(d) == {0: (10, 20, 30, 40)}


def test_mask_rong_ma_khong_khai_gt_rong_thi_bo():
    """Mask toàn đen mà KHÔNG khai `gt_rong` là dữ liệu mâu thuẫn ⇒ bỏ, không chấm bừa."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        d = _gt_dir(Path(tmp), {0: None, 5: (1, 1, 9, 9)})
        assert hop_tu_gt(d) == {5: (1, 1, 9, 9)}


def test_cham_ba_ca_phai_tach_nhau():
    """Ba ca KHÁC nghĩa: không vẽ ô nào (0,0), ô suy biến (None), thiếu frame (chưa chạy tới)."""
    hop_gt = {0: (0, 0, 10, 10), 1: (0, 0, 10, 10), 2: (0, 0, 10, 10)}
    shown = {0: ((0, 0, 10, 10), True),      # trùng khít ⇒ IoU 1,0
             1: (None, False)}               # GT có vật mà KHÔNG có ô hiển thị ⇒ 0,0
    kq = cham(hop_gt, shown)
    assert kq["n_gt_co_vat"] == 3 and kq["n_cham"] == 2
    assert kq["thieu_frame"] == [2], "frame 2 không có trong CSV ⇒ 'chưa chạy tới', không phải 0,0"
    theo = {r["frame_idx"]: r for r in kq["theo_frame"]}
    assert theo[0]["iou"] == 1.0
    assert theo[1]["iou"] == 0.0 and "bám sai" in theo[1]["vi_sao"]
    assert kq["iou_mean"] == 0.5


def test_cham_hop_dao_toa_do_la_khong_do_duoc_khong_phai_0():
    """Hộp ĐẢO toạ độ ⇒ `None` + không vào `n_cham`; quy thành 0,0 là làm điểm thấp giả.

    Chú ý: hộp MỎNG 1 px (`x1 == x2`) **không** phải suy biến — repo coi là vật thật ở xa
    (`_bbox_hop_le`), nên `_bbox_iou` vẫn chấm được và test này dùng hộp đảo.
    """
    kq = cham({0: (0, 0, 10, 10)}, {0: ((5, 5, 4, 4), True)})
    assert kq["n_cham"] == 0 and kq["iou_mean"] is None
    assert kq["theo_frame"][0]["iou"] is None


def test_so_sanh_dung_nguong_nhieu_lon_hon_cua_hai_ben():
    a = {"iou_mean": {"mean": 0.50, "std": 0.02, "n": 3}}
    b = {"iou_mean": {"mean": 0.515, "std": 0.01, "n": 3}}
    assert so_sanh(a, b)["phan_biet_duoc"] is False, "chênh 0,015 < nhiễu 0,02 ⇒ chưa rõ"

    b2 = {"iou_mean": {"mean": 0.60, "std": 0.01, "n": 3}}
    ss = so_sanh(a, b2)
    assert ss["phan_biet_duoc"] is True and "TỐT HƠN" in ss["ket_luan"]


def test_so_sanh_khong_co_so_thi_khong_ket_luan():
    ss = so_sanh({"iou_mean": {"mean": None, "std": None, "n": 0}},
                 {"iou_mean": {"mean": 0.5, "std": 0.01, "n": 3}})
    assert "KHÔNG kết luận" in ss["ket_luan"]


def test_tong_hop_tra_none_khi_rong():
    t = tong_hop([])
    assert t["iou_mean"]["mean"] is None and t["iou_mean"]["n"] == 0


def test_tong_hop_tinh_trung_binh_va_do_lech_chuan():
    lan = [{"cham": {"iou_mean": 0.5, "iou_min": 0.3, "lk_ok_frac": 0.2, "n_cham": 7},
            "status": {}},
           {"cham": {"iou_mean": 0.6, "iou_min": 0.4, "lk_ok_frac": 0.4, "n_cham": 7},
            "status": {}}]
    t = tong_hop(lan)
    assert t["iou_mean"]["mean"] == pytest.approx(0.55)
    assert t["iou_mean"]["std"] == pytest.approx(0.0707, abs=0.001)
    assert t["lk_ok_frac"]["mean"] == pytest.approx(0.3)
