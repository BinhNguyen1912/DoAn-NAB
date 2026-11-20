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
    from scripts.ab_o_hien_thi_vs_gt import KHONG_CO_O

    hop_gt = {0: (0, 0, 10, 10), 1: (0, 0, 10, 10), 2: (0, 0, 10, 10)}
    shown = {0: ((0, 0, 10, 10), True),      # trùng khít ⇒ IoU 1,0
             1: (KHONG_CO_O, False)}          # GT có vật mà KHÔNG có ô hiển thị ⇒ 0,0
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


def _lan(iou_theo_frame):
    return {"cham": {"theo_frame": [{"frame_idx": f, "iou": v} for f, v in iou_theo_frame.items()]}}


def test_so_sanh_theo_cap_khu_dao_dong_giua_lan_chay():
    """Cặp (cùng lần chạy, cùng frame) mới là so sánh đúng: 20-11 trung bình nói "không phân biệt được"
    (std 0,065 ở 1,5 > chênh 0,027) trong khi TỪNG frame thì cấu hình nới không bao giờ tệ hơn.
    """
    from scripts.ab_o_hien_thi_vs_gt import so_sanh_theo_cap

    a = [_lan({0: 0.55, 30: 0.51, 60: 0.18}), _lan({0: 0.55, 30: 0.50, 60: 0.18})]
    b = [_lan({0: 0.55, 30: 0.61, 60: 0.18}), _lan({0: 0.56, 30: 0.60, 60: 0.18})]
    kq = so_sanh_theo_cap(a, b)
    assert kq["so_cap"] == 6
    assert kq["a_tot_hon"] == 0 and kq["b_khong_bao_gio_te_hon"] is True
    assert kq["b_tot_hon"] == 3 and kq["bang"] == 3
    assert kq["frame_b_tot_hon"][30] == pytest.approx(0.20, abs=0.01)
    assert kq["chenh_lon_nhat"] > 0 and kq["chenh_nho_nhat"] == 0.0


def test_so_sanh_theo_cap_bo_cap_khi_mot_ben_khong_do_duoc():
    from scripts.ab_o_hien_thi_vs_gt import so_sanh_theo_cap

    kq = so_sanh_theo_cap([_lan({0: None, 30: 0.5})], [_lan({0: 0.5, 30: 0.5})])
    assert kq["so_cap"] == 1 and kq["bang"] == 1


def test_so_sanh_theo_cap_rong_tra_khong_ket_luan():
    from scripts.ab_o_hien_thi_vs_gt import so_sanh_theo_cap

    kq = so_sanh_theo_cap([], [])
    assert kq["so_cap"] == 0 and kq["b_khong_bao_gio_te_hon"] is False
    assert kq["chenh_trung_binh"] is None


def test_doc_shown_phan_biet_khong_co_o_va_o_hong(tmp_path):
    """P1 review #61: 4 cột rỗng (không có ô) ≠ toạ độ đảo (ô HỎNG) — chấm 0,0 cho ca sau là tự hạ điểm.

    Bản đầu còn test "cham trực tiếp" nên xanh giả: nó không đi qua `doc_shown`, tức không kiểm được
    đúng chỗ sinh lỗi.
    """
    from scripts.ab_o_hien_thi_vs_gt import KHONG_CO_O, O_HONG, doc_shown

    p = tmp_path / "shown.csv"
    p.write_text("frame_idx,x1,y1,x2,y2,lk_ok\n"
                 "0,,,,\n"                     # không có ô hiển thị
                 "1,9,9,4,4,1\n"              # đảo toạ độ ⇒ ô hỏng
                 "2,10,20,30,40,0\n", encoding="utf-8")
    d = doc_shown(p)
    assert d[0][0] is KHONG_CO_O
    assert d[1][0] is O_HONG
    assert d[2][0] == (10, 20, 30, 40) and d[2][1] is False

    kq = cham({0: (0, 0, 50, 50), 1: (0, 0, 50, 50)}, d)
    theo = {r["frame_idx"]: r for r in kq["theo_frame"]}
    assert theo[0]["iou"] == 0.0, "không có ô hiển thị ⇒ 0,0 (bám sai thật)"
    assert theo[1]["iou"] is None and kq["khong_do_duoc"] == 1


def test_so_sanh_khong_ket_luan_khi_mot_ben_chi_1_lan_chay():
    """P1 review #61: `std = None` (n < 2) KHÔNG được coi là nhiễu 0 — sẽ biến mọi chênh thành "tốt hơn"."""
    a = {"iou_mean": {"mean": 0.50, "std": None, "n": 1}}
    b = {"iou_mean": {"mean": 0.52, "std": 0.01, "n": 3}}
    ss = so_sanh(a, b)
    assert ss["phan_biet_duoc"] is None and ss["nguong_nhieu"] is None
    assert "KHÔNG kết luận" in ss["ket_luan"]


def test_lan_chay_hop_le_chan_worker_chet():
    """P1 review #61: worker chết / state lạ / CSV rỗng KHÔNG được tính là "bám sai thật"."""
    from scripts.ab_o_hien_thi_vs_gt import lan_chay_hop_le

    ok = {"ma_thoat": 0, "state": "stopped", "so_dong_shown": 50}
    assert lan_chay_hop_le(ok) is True
    assert lan_chay_hop_le({**ok, "ma_thoat": 1}) is False
    assert lan_chay_hop_le({**ok, "state": "error"}) is False
    assert lan_chay_hop_le({**ok, "state": "running"}) is False
    assert lan_chay_hop_le({**ok, "so_dong_shown": 1}) is False, "chỉ có dòng tiêu đề ⇒ chưa ghi gì"


def test_doc_shown_canh_bao_frame_trung_thay_vi_ghi_de_im_lang(tmp_path, capsys):
    """P3 review #61: `frame_idx` trùng từng ghi đè im lặng ⇒ số của frame đó không đáng tin."""
    from scripts.ab_o_hien_thi_vs_gt import doc_shown

    p = tmp_path / "shown.csv"
    p.write_text("frame_idx,x1,y1,x2,y2,lk_ok\n"
                 "5,10,10,20,20,1\n"
                 "5,30,30,40,40,0\n", encoding="utf-8")
    d = doc_shown(p)
    assert d[5][0] == (30, 30, 40, 40), "dòng SAU thắng (hành vi cũ), nhưng phải cảnh báo"
    assert "TRÙNG" in capsys.readouterr().out


def test_so_sanh_theo_cap_co_co_lech_so_lan_chay():
    """P2 review #61: một bên thiếu lần chạy ⇒ `zip` bỏ cặp lặng lẽ; hàm phải tự khai `can_bo_cap`."""
    from scripts.ab_o_hien_thi_vs_gt import so_sanh_theo_cap

    kq = so_sanh_theo_cap([_lan({0: 0.5})], [_lan({0: 0.6}), _lan({0: 0.6})])
    assert kq["so_lan_a"] == 1 and kq["so_lan_b"] == 2 and kq["can_bo_cap"] is True
    assert kq["so_cap"] == 1
    assert so_sanh_theo_cap([_lan({0: 0.5})], [_lan({0: 0.6})])["can_bo_cap"] is False


def test_so_dong_khop_frame_chan_mat_mau_hoac_ghi_trung():
    """P3 review #61: `shown.csv` phải đúng 1 dòng/frame đã phát — lệch thì IoU tính trên tập khác."""
    from scripts.ab_o_hien_thi_vs_gt import so_dong_khop_frame

    assert so_dong_khop_frame({"status": {"frames": 120}, "so_dong_shown": 121}) is True
    assert so_dong_khop_frame({"status": {"frames": 120}, "so_dong_shown": 100}) is False
    assert so_dong_khop_frame({"status": {"frames": 120}, "so_dong_shown": 130}) is False
    assert so_dong_khop_frame({"status": {}, "so_dong_shown": 10}) is False


def test_cau_hinh_lech_tach_ba_trang_thai_image_size():
    """`None` = CHƯA KIỂM ĐƯỢC, không phải "đã khớp" — `lech == []` từng bị đọc sai như vậy."""
    from scripts.ab_o_hien_thi_vs_gt import cau_hinh_lech
    khop = {"max_mad_yeu_cau": 1.5, "max_mad_hieu_luc": 1.5,
            "image_size_yeu_cau": 192, "image_size_hieu_luc": 192}
    lech_ = {"max_mad_yeu_cau": 1.5, "max_mad_hieu_luc": 1.5,
             "image_size_yeu_cau": 192, "image_size_hieu_luc": 320}
    chua = {"max_mad_yeu_cau": 1.5, "max_mad_hieu_luc": 1.5,
            "image_size_yeu_cau": 192, "image_size_hieu_luc": None}
    khong_mad = {"max_mad_yeu_cau": 1.5, "max_mad_hieu_luc": None,
                 "image_size_yeu_cau": 192, "image_size_hieu_luc": 192}
    lech, chua_kiem = cau_hinh_lech([khop, lech_, chua, khong_mad])
    assert lech == [lech_, khong_mad]          # hiệu lực khác yêu cầu, và mad không khai
    assert chua_kiem == [chua]                 # riêng, KHÔNG nằm trong `lech`


def test_danh_sach_cau_hinh_la_TICH_DE_cac_truc():
    """Bản đầu dựng khoá cấu hình ở 2 nơi; thêm trục `vos_every` thì một chỗ quên ⇒ `KeyError` chỉ lộ
    khi có > 1 giá trị (chạy 1 giá trị vẫn xanh). Test này khoá đúng lỗi đó."""
    from scripts.ab_o_hien_thi_vs_gt import danh_sach_cau_hinh
    d = danh_sach_cau_hinh([192, 320], [1, 3], [1.5, 6.0])
    assert len(d) == 8
    assert d["192/3/1.5"] == (192, 3, 1.5)
    assert d["320/1/6.0"] == (320, 1, 6.0)
    # Hai assert CŨ ở đây là RỖNG (`set(d)==set(d)`) — review #64 chỉ đúng. Nay kiểm thật:
    assert len(set(d.values())) == len(d)          # nhãn ↔ khoá 1-1 (không hai nhãn cùng một tuple)
    assert len(d) == len({*d})                     # không nhãn trùng
    assert d["320/1/6.0"] != d["192/1/6.0"]        # đổi trục image_size phải đổi khoá


def test_thu_tu_vong_dao_chieu_vong_le():
    from scripts.ab_o_hien_thi_vs_gt import danh_sach_cau_hinh, thu_tu_vong
    d = danh_sach_cau_hinh([192], [1, 3], [1.5])
    v0, v1 = thu_tu_vong(d, 0), thu_tu_vong(d, 1)
    assert v0 == list(d) and v1 == v0[::-1]      # "chạy sau" không luôn là cấu hình được ưu ái
    assert set(v0) == set(v1) == set(d)


def test_chieu_cua_bang_nhan_khong_bi_lan():
    """`tong`/`lan_chay` khoá bằng NHÃN ("192/1/1.5"), `theo_cau_hinh` khoá bằng TUPLE (192,1,1.5).

    Lẫn hai chiều ⇒ `KeyError` **sau khi đã chạy xong 9 lần** (gặp thật 20-11). Test khoá chiều.
    """
    from scripts.ab_o_hien_thi_vs_gt import danh_sach_cau_hinh
    d = danh_sach_cau_hinh([192], [1, 3], [1.5])
    khoa_cua = dict(d)                                  # nhãn → tuple
    nhan = {tup: nhan_ch for nhan_ch, tup in d.items()}  # tuple → nhãn
    assert nhan[(192, 1, 1.5)] == "192/1/1.5"
    assert khoa_cua["192/1/1.5"] == (192, 1, 1.5)
    # và mọi nhãn đều quy ngược được về khoá có thật trong dict cấu hình
    assert all(khoa_cua[n] in d.values() for n in nhan.values())


def test_main_khoa_bang_nhan_va_ghep_cap_dung_chieu(monkeypatch, tmp_path):
    """Chạy `main()` với pipeline GIẢ (vá `chay_mot_lan`) — khoá cả bảng nhãn lẫn phần ghép cặp.

    Vì sao cần: lỗi "dùng nhãn làm khoá cho `theo_cau_hinh`" chỉ lộ **sau khi chạy xong 9 lần** (gặp
    2 lần, 20-11) vì nó nằm ở đoạn CUỐI của `main()`. Test này chạy hết `main()` mà không nạp model.
    """
    from scripts import ab_o_hien_thi_vs_gt as ab
    ham = {"iou_mean": 0.5, "iou_min": 0.3, "lk_ok_frac": 0.0, "n_cham": 7, "n_gt_co_vat": 7,
           "khong_do_duoc": 0, "thieu_frame": [], "theo_frame": [
               {"frame_idx": 2, "iou": 0.5, "lk_ok": False, "hop": [0, 0, 1, 1], "hop_gt": [0, 0, 1, 1]}]}

    def fake_chay(*, clip, bbox, image_size, vos_every, max_mad, frames, out_dir):
        return {"shown": str(tmp_path / "s.csv"), "so_dong_shown": 8, "ma_thoat": 0, "state": "stopped",
                "status": {"frames": 7, "cau_hinh": {"lk_max_mad": max_mad,
                                                     "image_size_hieu_luc": image_size}}}

    monkeypatch.setattr(ab, "hop_tu_gt", lambda _d: {2: (0, 0, 10, 10)})
    monkeypatch.setattr(ab, "cham", lambda _g, _s, **_kw: ham)
    monkeypatch.setattr(ab, "doc_shown", lambda _p: {})
    monkeypatch.setattr(ab, "chay_mot_lan", fake_chay)
    out = tmp_path / "a.json"
    rc = ab.main(["--gt", "g", "--clip", "c", "--bbox", "0,0,10,10", "--image-size", "192", "320",
                  "--vos-every", "1", "3", "--max-mad", "1.5", "--lan", "2",
                  "--out", str(out)])
    assert rc == 0, "main() phải chạy hết và ghi artifact"
    d = json.loads(out.read_text(encoding="utf-8"))
    assert set(d["tong_hop"]) == {"192/1/1.5", "192/3/1.5", "320/1/1.5", "320/3/1.5"}
    assert set(d["lan_chay"]) == set(d["tong_hop"])
    assert d["so_sanh_theo_cap"]["a"] in d["tong_hop"]
    assert d["so_sanh_theo_cap"]["b"] in d["tong_hop"]
    assert d["so_sanh_theo_cap"]["so_cap"] > 0


# --- 4 P2 của review #64 ---
def test_so_sanh_KHONG_ket_luan_khi_ca_hai_std_bang_0():
    """`max(0, 0) = 0` ⇒ mọi chênh lệch thành "TỐT HƠN (nhiễu 0.000)".

    Cùng lớp lỗi đã vá cho `std = None` (review #61) nhưng bỏ sót `std = 0` (review #64).
    """
    from scripts.ab_o_hien_thi_vs_gt import so_sanh
    a = {"iou_mean": {"mean": 0.8460, "std": 0.0}, "iou_min": {"mean": 0.8, "std": 0.0},
         "lk_ok_frac": {"mean": 0.0, "std": 0.0}}
    b = {"iou_mean": {"mean": 0.8461, "std": 0.0}, "iou_min": {"mean": 0.8, "std": 0.0},
         "lk_ok_frac": {"mean": 0.0, "std": 0.0}}
    r = so_sanh(a, b)
    assert r["phan_biet_duoc"] is None and "KHÔNG kết luận" in r["ket_luan"]
    assert r["nguong_nhieu"] == 0.0


def test_cham_KHONG_bao_lk_ok_frac_khi_vos_every_1():
    """`vos_every=1` ⇒ không có LK. Ghi 0,0 ở đó bị đọc thành "LK từ chối 100 %" (review #64)."""
    from scripts.ab_o_hien_thi_vs_gt import cham
    gt = {2: (0, 0, 10, 10)}
    shown = {2: ((0, 0, 10, 10), False)}
    r = cham(gt, shown, lk_khong_ap_dung=True)
    assert r["lk_ok_frac"] is None and r["lk_khong_ap_dung"] is True
    assert r["iou_mean"] == 1.0                    # IoU vẫn chấm bình thường
    r2 = cham(gt, shown)                           # cấu hình có khe ⇒ giữ số thật (0,0 = LK từ chối)
    assert r2["lk_ok_frac"] == 0.0 and r2["lk_khong_ap_dung"] is False


def test_so_dong_lech_lam_lan_chay_khong_hop_le():
    """`shown.csv` thiếu/trùng dòng ⇒ IoU chấm trên tập frame KHÁC tập đã phát ⇒ phải LOẠI."""
    from scripts.ab_o_hien_thi_vs_gt import lan_chay_hop_le, so_dong_khop_frame
    ok = {"ma_thoat": 0, "state": "stopped", "so_dong_shown": 8, "status": {"frames": 7}}
    lech = {"ma_thoat": 0, "state": "stopped", "so_dong_shown": 5, "status": {"frames": 7}}
    assert so_dong_khop_frame(ok) and so_dong_khop_frame(lech) is False
    assert lan_chay_hop_le(ok) and lan_chay_hop_le(lech)          # hàm cũ KHÔNG thấy lỗi này
    # ghép đúng như main(): phải loại
    assert (lan_chay_hop_le(lech) and so_dong_khop_frame(lech)) is False


def test_chay_ken_vong_le_dao_chieu_va_moi_cap_duoc_so(monkeypatch, tmp_path):
    """Hai tiêu chí review #64: (a) thứ tự chèn kẽ A,B,A,B… và vòng lẻ đảo; (b) so MỌI cặp."""
    from scripts import ab_o_hien_thi_vs_gt as ab
    ham = {"iou_mean": 0.5, "iou_min": 0.3, "lk_ok_frac": 0.0, "n_cham": 7, "n_gt_co_vat": 7,
           "khong_do_duoc": 0, "thieu_frame": [], "lk_khong_ap_dung": False,
           "theo_frame": [{"frame_idx": 2, "iou": 0.5, "lk_ok": False}]}
    thu_tu = []

    def fake_chay(*, clip, bbox, image_size, vos_every, max_mad, frames, out_dir):
        thu_tu.append(f"{image_size}/{vos_every}/{max_mad}")
        return {"shown": str(tmp_path / "s.csv"), "so_dong_shown": 8, "ma_thoat": 0, "state": "stopped",
                "status": {"frames": 7, "cau_hinh": {"lk_max_mad": max_mad,
                                                     "image_size_hieu_luc": image_size}}}

    monkeypatch.setattr(ab, "hop_tu_gt", lambda _d: {2: (0, 0, 10, 10)})
    monkeypatch.setattr(ab, "cham", lambda _g, _s, **_kw: ham)
    monkeypatch.setattr(ab, "doc_shown", lambda _p: {})
    monkeypatch.setattr(ab, "chay_mot_lan", fake_chay)
    out = tmp_path / "a.json"
    assert ab.main(["--gt", "g", "--clip", "c", "--bbox", "0,0,10,10", "--image-size", "192", "320",
                    "--vos-every", "3", "--max-mad", "1.5", "--lan", "2", "--out", str(out)]) == 0
    # (a) chèn kẽ: A,B rồi B,A (vòng 1 đảo chiều)
    assert thu_tu == ["192/3/1.5", "320/3/1.5", "320/3/1.5", "192/3/1.5"]
    d = json.loads(out.read_text(encoding="utf-8"))
    # (b) 2 cấu hình ⇒ 1 cặp, và cặp đó đúng là cặp không chéo góc
    assert list(d["so_sanh_moi_cap"]) == ["192/3/1.5|320/3/1.5"]
    assert d["nguon_so"]["max_mad"] == [1.5] and d["schema"] == 2
