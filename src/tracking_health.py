"""Cờ phán quyết chất lượng bám của phiên live — hàm THUẦN, không import torch/cv2.

Vì sao có module này (ticket #14, plan 09-11): `drift_iou` và `empty_frac_window` là hai con số rời
nhau, người xem HUD không tự ghép lại được. Cờ gộp chúng thành **một phán quyết** kèm lý do:

- `ok` — p05 cửa sổ gần nhất còn cao ⇒ nội suy LK khớp ô VOS;
- `model_lost` — p05 thấp **và** mask rỗng nhiều ⇒ model đang mất vật (không phải LK tệ);
- `drift_trend` — p05 thấp **mà mask KHÔNG rỗng** ⇒ ô hiển thị và ô VOS bất nhất. Đây đúng là thứ
  `empty_frac_window` **không** nói được, và cũng là lý do ticket bị hoãn tới 19-11: trước đó tính
  p05 **cả phiên** nên nó dính 1:1 với "vật đã rời khung".
- `not_measured` — chưa đủ mẫu (hoặc `vos_every = 1`, không có cặp LK↔VOS để so).

Tên `drift_trend` (không phải "LK sai") là **có chủ ý**: `drift_iou` đo IoU(ô ĐÃ PHÁT, ô VOS sửa lại),
nên nó chỉ chứng minh *hai ô bất nhất* — chưa chứng minh bên nào sai. Muốn nói "LK sai" phải có mask
GT (xem `docs/thuoc-do-bam-dung.md`).

Ngưỡng Schmitt `0,30` vào / `0,45` ra là **KHỞI TẠO**, hiệu lực đúng trên các clip đã đo
(`docs/plan/09-11-2026-chan-doan-chat-luong-bam.md`): trên `binh1` khoẻ, ngưỡng 0,30 báo oan 0 % cửa
sổ (ngưỡng 0,70 cũ báo oan 100 % ở cửa sổ ≥ 100 mẫu — ticket #15). Đừng trích nó như ngưỡng đã
chuẩn hoá cho mọi cảnh.
"""

from __future__ import annotations

from src.drift_samples import MIN_SAMPLES, phan_vi

# Trạng thái
OK = "ok"
MODEL_LOST = "model_lost"
DRIFT_TREND = "drift_trend"
NOT_MEASURED = "not_measured"

NGUONG_VAO = 0.30        # p05 ≤ ngưỡng này ⇒ BẬT cờ
NGUONG_RA = 0.45         # đang bật: chỉ TẮT khi p05 > ngưỡng này (găng tay Schmitt, chống nhấp nháy)
EMPTY_TRAN = 0.03        # mask rỗng ≥ 3 % cửa sổ ⇒ quy cho "model mất vật", không phải LK trôi
CUA_SO = 30              # số mẫu gần nhất để tính p05 (bằng MIN_SAMPLES công bố p05 của repo)

# Lý do ở dạng máy đọc được — UI dịch sang tiếng Việt, log/artifact giữ nguyên chuỗi này.
LY_DO = {
    OK: "p05 cửa sổ gần nhất còn cao",
    MODEL_LOST: "p05 thấp và mask rỗng nhiều ⇒ model đang mất vật",
    DRIFT_TREND: "p05 thấp nhưng mask KHÔNG rỗng ⇒ ô hiển thị và ô VOS bất nhất",
    NOT_MEASURED: "chưa đủ mẫu để kết luận",
}


def _empty_frac(empty, window: int):
    """Tỉ lệ mask rỗng trong `window` mẫu cuối; `None` nếu không có mẫu nào KHAI `empty`.

    `None` ≠ 0: worker bản cũ không ghi cột `empty` ⇒ **chưa đo**, không phải "không rỗng lần nào".
    """
    if not empty:
        return None
    values = [e for e in list(empty)[-window:] if e is not None]
    if not values:
        return None
    return round(sum(1 for e in values if e) / len(values), 3)


def phan_quyet(drift, empty=None, *, vos_every: int = 3, truoc: str = OK,
               window: int = CUA_SO, nguong_vao: float = NGUONG_VAO,
               nguong_ra: float = NGUONG_RA, empty_tran: float = EMPTY_TRAN) -> dict:
    """Trả `{"co", "ly_do", "p05", "n", "empty_frac", ...}` cho cửa sổ mẫu drift gần nhất.

    `truoc` là phán quyết của lần tính trước ⇒ tạo **găng tay Schmitt**: đang `drift_trend` thì chỉ
    thoát khi `p05 > nguong_ra`, tránh cờ nhấp nháy qua lại quanh một ngưỡng.
    """
    values = [float(v) for v in (drift or [])][-window:]
    empties = list(empty)[-window:] if empty else []
    empty_frac = _empty_frac(empties, window)
    ra = {
        "n": len(values),
        "empty_frac": empty_frac,
        "p05": None,
        "nguong_vao": nguong_vao,
        "nguong_ra": nguong_ra,
        "empty_tran": empty_tran,
        "cua_so": window,
    }
    if int(vos_every) < 2:
        # `vos_every = 1` chạy model mỗi frame ⇒ KHÔNG có cặp "ô nội suy ↔ ô VOS" nào để so
        # (`_measure_drift` không được gọi). Đây là "chưa đo", không phải "ổn".
        return {**ra, "co": NOT_MEASURED, "ly_do": "vos_every=1: không có nội suy LK để đo drift"}
    p05 = phan_vi(values, min_samples=MIN_SAMPLES) if values else None
    ra["p05"] = p05
    if p05 is None:
        return {**ra, "co": NOT_MEASURED,
                "ly_do": f"mới {len(values)} mẫu drift (cần {MIN_SAMPLES})"}

    dang_bat = truoc == DRIFT_TREND
    bat = p05 <= (nguong_ra if dang_bat else nguong_vao)
    if not bat:
        return {**ra, "co": OK, "ly_do": LY_DO[OK]}
    if empty_frac is not None and empty_frac >= empty_tran:
        return {**ra, "co": MODEL_LOST, "ly_do": LY_DO[MODEL_LOST]}
    ra["ly_do"] = (LY_DO[DRIFT_TREND] if empty_frac is not None
                   else "p05 thấp, nhưng `empty` CHƯA ĐO ⇒ chỉ biết hai ô bất nhất")
    ra["empty_chua_do"] = empty_frac is None
    return {**ra, "co": DRIFT_TREND}


def cau_co(ket_qua: dict) -> str | None:
    """Một câu tiếng Việt cho HUD/`status.json` — `ok` ⇒ `None` (không chiếm chỗ trên màn hình).

    Vì sao tách khỏi `phan_quyet`: hàm kia phải là số/máy đọc được để test và để so giữa các lần chạy;
    câu chữ đổi thường xuyên hơn nhiều.
    """
    co = (ket_qua or {}).get("co")
    if co in (None, OK):
        return None
    p05 = (ket_qua or {}).get("p05")
    p05_text = "chưa đủ mẫu" if p05 is None else f"{p05:.2f}"
    if co == NOT_MEASURED:
        return f"Chất lượng bám: {ket_qua.get('ly_do')}"
    if co == MODEL_LOST:
        return (f"Chất lượng bám: model MẤT VẬT (p05 {p05_text}, mask rỗng "
                f"{100 * (ket_qua.get('empty_frac') or 0):.0f} % cửa sổ)")
    return f"Chất lượng bám: ô hiển thị lệch ô VOS (p05 {p05_text}, mask rỗng thấp)"
