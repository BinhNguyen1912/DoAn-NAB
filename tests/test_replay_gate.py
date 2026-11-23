"""Test cho `scripts/replay_gate.py` — replay luật "mask sai" trên CSV, KHÔNG model.

Vì sao có: cùng một luật (điểm tin cậy sụt) được báo 3 con số khác nhau trong cùng một ngày
(0,81 % / 51,1 % / 75 lần) và **không con số nào tái lập được**. Các test dưới đây khoá đúng những
chỗ đã làm con số lệch: rò rỉ tương lai trong baseline, lẫn "số lần báo" với "số frame bị ẩn",
và bẫy "0/None ≠ đã đo".
"""
import csv
import json

import pytest

import scripts.replay_gate as rg


# ── baseline trượt: KHÔNG được nhìn thấy mẫu tương lai ──────────────────────────────────────


def test_baseline_khong_dung_mau_cua_chinh_frame_do():
    """Cú sụt mạnh ở frame i KHÔNG được kéo baseline của chính nó xuống (nếu không ⇒ 'trễ 0 frame'
    là lời tiên tri: frame nào cũng 'bắt đúng ngay')."""
    scores = [10.0] * 20 + [0.5] + [10.0] * 20
    base = rg.baseline_truot(scores, win=10, lag=1)
    assert base[20] == pytest.approx(10.0), "baseline của frame cú sụt phải là 10, không phải 0,5"
    assert base[21] == pytest.approx(10.0)


def test_baseline_none_khi_chua_du_mau():
    """Nửa đầu phiên là MÙ (không đủ mẫu) — phải trả `None`, không lấy mẫu ngắn rồi giả vờ đo được."""
    base = rg.baseline_truot([5.0] * 12, win=10, lag=1)
    assert base[:11] == [None] * 11
    assert base[11] == pytest.approx(5.0)


def test_baseline_tu_choi_lag_0():
    with pytest.raises(ValueError):
        rg.baseline_truot([1.0, 2.0], win=5, lag=0)


# ── latch: "số lần báo" ≠ "số frame bị ẩn" ─────────────────────────────────────────────────


def test_latch_an_tu_lan_bao_dau_tien_toi_het_phien():
    """`score` là tín hiệu XUNG: báo 1 lần ở frame 2/10 ⇒ ẩn 8 frame (80 %), không phải 1 frame."""
    fires = [2]
    assert rg.frame_bi_an(fires, 10) == 8
    assert rg.frame_bi_an([], 10) == 0


def test_co_latch_tra_frame_bao_dong_khong_phai_dau_chuoi():
    """P1 vòng 2: cổng chỉ HÀNH ĐỘNG ở frame thứ `run` ⇒ trả frame đó, không phải đầu chuỗi.

    Trả đầu chuỗi làm `frame_bi_an` sớm hơn thực tế `run-1` frame mỗi lần báo (cận trên).
    """
    flags = [False, True, True, False, True, True, True]
    assert rg.co_latch(flags, run=3) == [6], "chuỗi 3 frame bắt đầu ở 4 ⇒ BÁO ĐỘNG ở frame 6"
    assert rg.co_latch(flags, run=2) == [2, 5]
    assert rg.co_latch(flags, run=4) == []


def test_co_abs_bo_qua_frame_mat_dau():
    """Frame mask RỖNG đã có cơ chế riêng (`no_evidence`) ⇒ luật này không được tính nó."""
    rows = [{"score": 1.0, "mask_area": 0.0}, {"score": 1.0, "mask_area": 500.0}]
    assert rg.co_abs(rows, 2.0) == [False, True]


def test_co_rel_dung_baseline_truoc_va_bo_frame_mask_rong():
    rows = [{"score": 10.0, "mask_area": 100.0} for _ in range(12)]
    rows.append({"score": 0.5, "mask_area": 100.0})      # sụt mạnh, mask còn
    rows.append({"score": 0.5, "mask_area": 0.0})        # sụt nhưng mask rỗng ⇒ bỏ
    flags = rg.co_rel(rows, ti_le=0.7, win=10, lag=1)
    assert flags[12] is True and flags[13] is False


def test_mask_to_khi_bat_dem_dung_va_tra_None_khi_thieu_cot():
    rows = [{"score": 1.0, "mask_area": 1000.0} for _ in range(5)]
    rows[2] = {"score": 1.0, "mask_area": 100.0}          # mask nhỏ ⇒ không phải báo oan
    assert rg.mask_to_khi_bat(rows, [0, 2], ti_le=0.5) == 1
    thieu = [{"score": 1.0, "mask_area": None} for _ in range(5)]
    assert rg.mask_to_khi_bat(thieu, [0]) is None, "thiếu `mask_area` ⇒ CHƯA ĐO, không phải 0"


# ── đọc CSV + bẫy "0/None ≠ đã đo" ─────────────────────────────────────────────────────────


def _ghi_csv(path, rows, cot):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cot)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cot})


def test_doc_cot_chap_nhan_csv_cu_thieu_mask_area(tmp_path):
    p = tmp_path / "cu.csv"
    _ghi_csv(p, [{"frame_idx": 0, "score": "3.5"}, {"frame_idx": 1, "score": "2.5"}],
             ["frame_idx", "score"])
    rows = rg.doc_cot(p)
    assert [r["score"] for r in rows] == [3.5, 2.5]
    assert rows[0]["mask_area"] is None
    assert rg.co_mask_area(rows) is False, "CSV 11 cột cũ KHÔNG có mask_area ⇒ phải khai ra"


def test_main_that_bai_khi_khong_co_csv(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = rg.main(["--glob", "khong_co_*.csv"])
    assert rc == 1, "không có CSV ⇒ mã thoát 1 (bẫy '0 lần báo' thay cho 'không đo được')"
    assert "KHÔNG đo được" in capsys.readouterr().err


def test_main_tu_choi_lag_0():
    assert rg.main(["--lag", "0"]) == 2


def test_main_ghi_payload_co_provenance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _ghi_csv(tmp_path / "a_metrics.csv",
             [{"frame_idx": i, "score": 10.0, "mask_area": 100} for i in range(12)]
             + [{"frame_idx": 12, "score": 0.4, "mask_area": 100}],
             ["frame_idx", "score", "mask_area"])
    out = tmp_path / "rg.json"
    rc = rg.main(["--glob", "a_metrics.csv", "--out", str(out)])
    assert rc == 0
    d = json.loads(out.read_text())
    for k in ("git_rev", "git_dirty_code", "lenh", "do_luc", "luat", "tong", "phien"):
        assert k in d, f"artifact thiếu {k} (AGENTS §6)"
    assert d["tong"]["so_phien"] == 1 and d["tong"]["so_frame"] == 13
    assert d["phien"][0]["co_mask_area"] is True
    assert d["tong"]["pct_frame_an_rel"] is not None


# ── chi phí latch phụ thuộc đường XOÁ ───────────────────────────────────────────────────────


def test_frame_bi_an_reset_xoa_khi_nhan_lai():
    """Cùng luật, chi phí latch khác nhau tuỳ có xoá khi `reacquired=1` hay không."""
    rows = [{"reacquired": 0.0} for _ in range(20)]
    rows[8] = {"reacquired": 1.0}
    fires = [2]
    assert rg.frame_bi_an(fires, 20) == 18, "không xoá: ẩn từ frame 2 tới hết"
    assert rg.frame_bi_an_reset(rows, fires, 20) == 6, "xoá ở frame 8 ⇒ chỉ ẩn 2..7"


def test_frame_bi_an_reset_khong_co_lan_bao_thi_bang_0():
    assert rg.frame_bi_an_reset([{"reacquired": 1.0}] * 5, [], 5) == 0


def test_tong_tach_theo_co_mask_area(tmp_path, monkeypatch):
    """Cấm trộn mẫu số: CSV 11 cột (không `mask_area`) tổng riêng với CSV mới."""
    monkeypatch.chdir(tmp_path)
    cot_moi = ["frame_idx", "score", "mask_area"]
    cot_cu = ["frame_idx", "score"]
    _ghi_csv(tmp_path / "moi_metrics.csv",
             [{"frame_idx": i, "score": 10.0, "mask_area": 100} for i in range(12)], cot_moi)
    _ghi_csv(tmp_path / "cu_metrics.csv",
             [{"frame_idx": i, "score": 10.0} for i in range(4)], cot_cu)
    out = tmp_path / "rg.json"
    assert rg.main(["--glob", "*_metrics.csv", "--out", str(out)]) == 0
    t = json.loads(out.read_text())["tong_theo_mask_area"]
    assert t["co"]["so_frame"] == 12 and t["co"]["so_phien"] == 1
    assert t["khong"]["so_frame"] == 4 and t["khong"]["so_phien"] == 1
