"""Test cờ phán quyết chất lượng bám (ticket #14) — hàm thuần, không cần model/video."""

from __future__ import annotations

import pytest

from src.drift_samples import MIN_SAMPLES
from src.tracking_health import (
    CUA_SO, DRIFT_TREND, MODEL_LOST, NOT_MEASURED, OK, cau_co, phan_quyet,
)


def _binh1_khoe(n=40):
    """p05 cao, mask không rỗng (binh1 cả phiên, không lọc khung: p05 0,663–0,720)."""
    return [0.9 + (i % 5) * 0.01 for i in range(n)], [0] * n


def _binh1_doan_xau(n=40):
    """Đoạn 57–108 của binh1: `drift_iou = 0` ở 6–9/60 mẫu, `empty` 1,6–1,8 % (mask KHÔNG rỗng)."""
    values = [0.95] * n
    for i in range(0, n, 7):
        values[i] = 0.0
    return values, [0] * n


def _binh2(n=40):
    """VOS mất dấu thật: p05 0, `empty` 11 %."""
    return [0.0] * n, [1 if i % 9 == 0 else 0 for i in range(n)]


def test_binh1_khoe_la_ok():
    assert phan_quyet(*_binh1_khoe())["co"] == OK


def test_binh1_doan_xau_la_drift_trend():
    """Đây là TOÀN BỘ lý do ticket #14 tồn tại: p05 thấp MÀ mask không rỗng.

    Trước 19-11 người ta tính p05 cả phiên nên p05 và `empty` dính nhau 1:1 ⇒ cờ chỉ là bản sao của
    `empty_frac_window`. Lọc khung rồi mới tính thì binh1 có p05 = 0 với empty 1,6 %.
    """
    kq = phan_quyet(*_binh1_doan_xau())
    assert kq["co"] == DRIFT_TREND
    assert kq["p05"] == 0.0 and kq["empty_frac"] == 0.0


def test_binh2_la_model_lost_chu_khong_phai_LK_troi():
    """p05 thấp vì model KHÔNG thấy vật (`empty` 11 %) ⇒ quy cho model, không vu cho LK."""
    kq = phan_quyet(*_binh2())
    assert kq["co"] == MODEL_LOST
    assert kq["empty_frac"] == pytest.approx(0.111, abs=0.03)


def test_vos_every_1_la_not_measured():
    """`vos_every=1` chạy model mỗi frame ⇒ không có cặp "ô nội suy ↔ ô VOS" nào để so."""
    kq = phan_quyet([0.9] * 40, [0] * 40, vos_every=1)
    assert kq["co"] == NOT_MEASURED and kq["p05"] is None
    assert "vos_every" in kq["ly_do"]


def test_duoi_MIN_SAMPLES_la_not_measured_chu_khong_phai_ok():
    """`n < 30` ⇒ **chưa đo**. Trả `ok` ở đây là "cổng danh nghĩa": phiên mới chạy 5 frame sẽ được
    báo là "chất lượng tốt" trong khi chưa đo được gì."""
    kq = phan_quyet([0.9] * (MIN_SAMPLES - 1), [0] * (MIN_SAMPLES - 1))
    assert kq["co"] == NOT_MEASURED and kq["p05"] is None
    assert str(MIN_SAMPLES) in kq["ly_do"]


def test_gang_tay_schmitt_khong_tat_ngay_khi_p05_vua_len():
    """Đang bật: chỉ tắt khi `p05 > NGUONG_RA` (0,45). Giữa 0,30 và 0,45 thì **giữ nguyên**.

    Không có găng tay thì cờ nhấp nháy mỗi lần p05 dao động quanh 0,30 — vô dụng cho HUD.
    """
    # 30 mẫu: sắp xếp [0, 0, 0,9 …] ⇒ p05 = 0,0 + 0,45 × 0,9 = 0,405 (GIỮA 0,30 và 0,45).
    giua = [0.0, 0.0] + [0.9] * 28
    p05 = phan_quyet(giua, [0] * 30)["p05"]
    assert 0.30 < p05 <= 0.45, f"ca test phải nằm GIỮA hai ngưỡng, đang {p05}"
    assert phan_quyet(giua, [0] * 30, truoc=OK)["co"] == OK
    assert phan_quyet(giua, [0] * 30, truoc=DRIFT_TREND)["co"] == DRIFT_TREND, \
        "đang bật mà p05 ≤ ngưỡng RA thì phải GIỮ cờ"


def test_thoat_co_khi_p05_vuot_nguong_ra():
    assert phan_quyet(*_binh1_khoe(), truoc=DRIFT_TREND)["co"] == OK


def test_empty_chua_do_van_noi_duoc_dieu_gi():
    """Worker không ghi cột `empty` ⇒ vẫn báo `drift_trend` nhưng phải KHAI là chưa đo.

    Im lặng coi `empty = 0` sẽ biến "chưa đo" thành bằng chứng "mask không rỗng" — đúng bẫy 0/None.
    """
    values, _ = _binh1_doan_xau()
    kq = phan_quyet(values, None)
    assert kq["co"] == DRIFT_TREND and kq["empty_frac"] is None
    assert kq["empty_chua_do"] is True and "CHƯA ĐO" in kq["ly_do"]


def test_nan_la_so_do_hong_khong_phai_p05_thap():
    with pytest.raises(ValueError):
        phan_quyet([0.9] * 39 + [float("nan")], [0] * 40)


def test_cau_co_chi_hien_khi_co_van_de():
    assert cau_co({"co": OK}) is None and cau_co({}) is None
    assert "MẤT VẬT" in cau_co(phan_quyet(*_binh2()))
    cau = cau_co(phan_quyet(*_binh1_doan_xau()))
    assert "lệch ô VOS" in cau and "0.00" in cau
    assert "cần 30" in cau_co(phan_quyet([0.9] * 5, [0] * 5))


def test_hang_so_cua_so_bang_nguong_cong_bo_p05():
    """Cửa sổ của cờ = `MIN_SAMPLES` (30) — cùng cửa với mọi `*_p05` công bố (ticket #23).

    Hai ngưỡng khác nhau cho cùng đại lượng là đúng thứ ticket #23 đã dọn.
    """
    assert CUA_SO == MIN_SAMPLES
