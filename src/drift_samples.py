"""
DriftSampleLog — ghi TỪNG mẫu `drift_iou` ra CSV để ngưỡng chẩn đoán thành tái lập được (ticket 15).

Chức năng: `status.json` chỉ có mean/p05 của cửa sổ 200 mẫu ⇒ **không đo được** "phát hiện sau bao
           nhiêu mẫu" và "bao nhiêu % cửa sổ báo oan". Module này ghi từng mẫu ra CSV
           (`frame_idx, seq, vos_ms, empty, drift_iou, bbox_*`) và cung cấp các hàm THUẦN để đọc
           lại + phân tích: `rolling_p05`, `flag_rate`, `detect_latency`, `static_control`.
Input  : `DriftSampleLog.write(...)` từ `LiveTrackingSession`; `read_samples(path)` cho CSV đã ghi.
Output : `<out_dir>/drift_samples.csv` (một dòng / kết quả VOS của luồng worker) + dict thống kê
         thuần. Quan hệ đếm: `n_dong == vos_runs - 1` **khi bật LK (`vos_every > 1`)** — `vos_runs`
         cộng thêm 1 lần `engine.start()` (mẫu khởi tạo, không có nội suy để so nên không có dòng);
         `vos_every = 1` không có CSV nào (không có nội suy ⇒ không có drift để ghi).
Lưu ý  : (1) Ô TRỐNG = **chưa đo**, KHÔNG được đọc thành 0 (AGENTS §6). (2) `write()` được gọi từ
         HAI luồng (luồng VOS khi đo drift ngay, luồng chính khi mẫu `_pending_drift` tới hạn) nên
         có lock riêng; lock chỉ giữ trong lúc ghi một dòng (~vài chục µs), KHÔNG gọi hàm này khi
         đang giữ `_stats_lock` của phiên. (3) `drift_iou` KHÔNG phải độ chính xác — nó là độ tự
         nhất quán của ô bao đang hiển thị (xem AGENTS §6).
"""

import csv
import threading
from pathlib import Path

import numpy as np

DRIFT_CSV_NAME = "drift_samples.csv"
CSV_HEADER = [
    "frame_idx", "seq", "vos_ms", "empty", "drift_iou",
    "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
]

# Cửa sổ phân vị: khớp `_STAT_WINDOW` của `src/live_tracking.py` ⇒ p05 tính từ CSV tái lập đúng
# ĐỊNH NGHĨA của con số trong `status.json`/artifact cũ (độ làm tròn khác: 4 chữ số ở đây, 3 ở
# `status.json`). Có test khoá `WINDOW == live_tracking._STAT_WINDOW` để hai chỗ không trôi khỏi nhau.
WINDOW = 200
# Số mẫu TỐI THIỂU để công bố phân vị — phải bằng `_STAT_MIN_SAMPLES` của phiên (30): nếu CSV công bố
# p05 từ 20 mẫu thì nó nói một điều mà `status.json` từ chối nói (với n = 20, p05 ≈ min ⇒ "một mẫu
# xui"). `static_control` dùng ngưỡng riêng 20 vì ticket 15 yêu cầu `drift_n >= 20`.
MIN_SAMPLES = 30
# Số mẫu "đo được" tối thiểu để một cửa sổ được tính p05 trong `low_p05_low_empty`: mặc định
# `window // 2`, suy từ chính cửa sổ được hỏi (đừng ghim theo `WINDOW` — xem docstring hàm).
MIN_MEASURED_IN_WINDOW = WINDOW // 2
# Ngưỡng "mẫu xấu" (nội suy LK đã lệch hẳn) và ngưỡng CỜ chẩn đoán đề xuất trong plan 09-11.
BAD_SAMPLE = 0.5
FLAG_P05 = 0.30
# Ngưỡng đăng ký trước 08-11 cho clip khoẻ (dùng để đếm cửa sổ "báo động" trên clip KHỎE = báo oan).
HEALTHY_P05 = 0.70


class DriftSampleLog:
    """Ghi từng mẫu drift ra CSV — mở file LƯỜI (phiên không đo drift thì không sinh file rỗng).

    Vì sao lười: `vos_every=1` (tắt LK) KHÔNG có nội suy ⇒ không có mẫu drift. Nếu mở file trong
    `__init__`, mọi phiên như vậy để lại một CSV chỉ có header, dễ bị đọc thành "đã đo, 0 mẫu".
    """

    def __init__(self, path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._handle = None
        self._closed = False
        self.n_rows = 0

    @property
    def path(self) -> Path:
        return self._path

    def write(self, *, frame_idx, seq, vos_ms, empty, drift_iou, bbox) -> None:
        """Ghi MỘT mẫu. Trường nào là `None` ⇒ ô trống (chưa đo), không ghi 0."""
        row = [
            "" if frame_idx is None else int(frame_idx),
            "" if seq is None else int(seq),
            "" if vos_ms is None else f"{float(vos_ms):.1f}",
            "" if empty is None else (1 if empty else 0),
            "" if drift_iou is None else f"{float(drift_iou):.4f}",
        ]
        if bbox is None:
            row.extend(["", "", "", ""])
        else:
            row.extend([int(v) for v in bbox])
        line = ",".join(str(v) for v in row) + "\n"
        with self._lock:
            if self._closed:
                # Phiên đã đóng file (luồng VOS có thể còn sống tới 5 s sau `join`): KHÔNG mở lại —
                # `_ensure_open` dùng mode `w` nên mở lại sẽ XOÁ sạch dãy mẫu đã ghi (file bằng
                # chứng "trông hợp lệ" mà rỗng ruột — đúng bẫy AGENTS §6). Bỏ mẫu cuối, không xoá.
                return
            handle = self._ensure_open()
            handle.write(line)
            # Flush mỗi dòng: phiên live bị dừng bằng SIGTERM/`kill` (không qua `finally`) vẫn giữ
            # được mẫu đã đo. Giá: ~20–50 µs cho 8 dòng/giây ⇒ không đáng kể so với `vos_ms`.
            handle.flush()
            self.n_rows += 1

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._handle is not None:
                self._handle.close()
                self._handle = None

    def _ensure_open(self):
        """Mở file + ghi header ở lần ghi ĐẦU TIÊN (gọi khi ĐÃ giữ `self._lock`)."""
        if self._handle is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = open(self._path, "w", newline="", encoding="utf-8")
            self._handle.write(",".join(CSV_HEADER) + "\n")
        return self._handle


def _opt_int(text):
    text = (text or "").strip()
    return int(text) if text else None


def _opt_float(text):
    text = (text or "").strip()
    return float(text) if text else None


def _opt_bool(text):
    text = (text or "").strip()
    if not text:
        return None
    # Chỉ nhận ĐÚNG định dạng mình ghi (1/0). Chuỗi lạ ("True", "yes") ⇒ None = CHƯA ĐO, không
    # được quy thành False (False sẽ biến "không rõ" thành "không mất dấu" ⇒ hạ tỉ lệ báo oan sai).
    if text not in {"1", "0"}:
        return None
    return text == "1"


def read_samples(path) -> list:
    """Đọc CSV thành list dict; ô trống ⇒ `None` (KHÔNG suy ra 0/false)."""
    rows = []
    with open(path, newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            rows.append({
                "frame_idx": _opt_int(raw.get("frame_idx")),
                "seq": _opt_int(raw.get("seq")),
                "vos_ms": _opt_float(raw.get("vos_ms")),
                "empty": _opt_bool(raw.get("empty")),
                "drift_iou": _opt_float(raw.get("drift_iou")),
                "bbox": tuple(_opt_int(raw.get(f"bbox_{k}")) for k in ("x1", "y1", "x2", "y2")),
            })
    return rows


def drift_values(rows) -> list:
    """Chỉ các mẫu CÓ số đo drift (mẫu ô bao suy biến bị bỏ đo, không phải 0)."""
    return [row["drift_iou"] for row in rows if row.get("drift_iou") is not None]


def thong_ke_mau(rows) -> dict:
    """Thống kê một NHÓM mẫu — hàm THUẦN, tự bảo vệ bẫy "0 ≠ chưa đo".

    `empty_frac` = tỉ lệ mẫu CÓ cờ `empty` (mẫu không có cờ không vào mẫu số); `drift_iou_mean`
    chỉ tính trên mẫu có `drift_iou`. Không có mẫu nào ⇒ **`None`** (chưa đo), không phải `0,0`.
    """
    empty_flags = [row["empty"] for row in rows if row.get("empty") is not None]
    drifts = drift_values(rows)
    return {
        "n": len(rows),
        "n_empty_do_duoc": len(empty_flags),
        "empty_frac": round(sum(1 for v in empty_flags if v) / len(empty_flags), 3)
                      if empty_flags else None,
        "n_drift": len(drifts),
        "drift_iou_mean": round(sum(drifts) / len(drifts), 4) if drifts else None,
    }


def tach_theo_khung(rows, dau: int, cuoi: int) -> dict:
    """Tách mẫu theo KHUNG frame `[dau, cuoi]` và thống kê mỗi bên — hàm THUẦN.

    Vì sao cần: `empty_runs`/`empty_frac_window` **không phân biệt** "model mất dấu" với "vật
    không còn trong khung". Đo 14-11 trên `data/binh1.mp4` (ô đúng = chai): cả phiên 35–36 % mẫu
    rỗng, nhưng **0,0 %** khi chai còn trong khung (frame ≤ 105) — 100 % số rỗng là đoạn người ta
    đã cất chai đi (ảnh frame 160/260 không có chai). Không tách khung thì con số "mất dấu 35 %"
    bị đọc thành lỗi model.

    Cả hai bên **luôn** được trả về cùng nhau để người đọc không thể trích riêng "trong khung" mà
    giấu phần còn lại. Mẫu không có `frame_idx` (hiếm: `_seq_frame` bị cắt) xếp vào
    `khong_ro_khung`, **không** bị tính vào bên nào.

    Input : `rows` từ `read_samples()`, `dau`/`cuoi` là frame_idx **bao gồm hai đầu**.
    Output: `{khung, trong_khung, ngoai_khung, khong_ro_khung}` — mỗi nhóm là `thong_ke_mau()`.
    """
    dau, cuoi = min(int(dau), int(cuoi)), max(int(dau), int(cuoi))
    trong, ngoai, khong_ro = [], [], []
    for row in rows:
        idx = row.get("frame_idx")
        if idx is None:
            khong_ro.append(row)
        elif dau <= idx <= cuoi:
            trong.append(row)
        else:
            ngoai.append(row)
    return {
        "khung": [dau, cuoi],
        "trong_khung": thong_ke_mau(trong),
        "ngoai_khung": thong_ke_mau(ngoai),
        "khong_ro_khung": thong_ke_mau(khong_ro),
        "ghi_chu": "`trong_khung`/`ngoai_khung` PHẢI đọc cùng nhau: số rỗng ở `ngoai_khung` là "
                   "vật đã rời khung, không phải model mất dấu.",
    }


def rolling_p05(values, window: int = WINDOW) -> list:
    """p05 của từng cửa sổ `window` mẫu liên tiếp; `None` cho tới khi đủ mẫu.

    Số này phải khớp `drift_iou_p05` trong `status.json` (cùng cửa sổ, cùng định nghĩa) — nhờ vậy
    dãy trong CSV giải thích được đúng con số đã công bố, thay vì là một phép tính khác.
    """
    series = []
    for index in range(len(values)):
        if index + 1 < window:
            series.append(None)
            continue
        chunk = values[index + 1 - window:index + 1]
        series.append(round(float(np.percentile(chunk, 5)), 4))
    return series


def flag_rate(values, *, threshold: float = HEALTHY_P05, window: int = WINDOW) -> dict:
    """Tỉ lệ cửa sổ có p05 < `threshold`.

    Trên clip **khoẻ** (binh1) đây chính là **tỉ lệ báo oan** của ngưỡng đó: càng cao càng vô dụng.
    `n_cua_so == 0` ⇒ `ti_le_bao = None` (chưa đo được, không phải 0 %).
    """
    series = [value for value in rolling_p05(values, window) if value is not None]
    flagged = sum(1 for value in series if value < float(threshold))
    return {
        "nguong_p05": threshold,
        "cua_so": window,
        "n_cua_so": len(series),
        "n_bao": flagged,
        "ti_le_bao": round(flagged / len(series), 3) if series else None,
    }


def detect_latency(rows, *, bad: float = BAD_SAMPLE, flag: float = FLAG_P05,
                   window: int = WINDOW) -> dict:
    """Từ mẫu XẤU đầu tiên tới cửa sổ đầu tiên có p05 < `flag` — bao nhiêu mẫu mới phát hiện.

    Định nghĩa dùng để báo cáo (viết ra đây để người khác tái lập được):
      - "mẫu xấu" = mẫu ĐO ĐƯỢC đầu tiên có `drift_iou < bad`;
      - "phát hiện" = cửa sổ `window` mẫu đầu tiên (kết thúc ở chỉ số `j >= bad_idx`) có
        p05 < `flag`;
      - `phat_hien_sau_mau = j - bad_idx` (0 = phát hiện ngay tại mẫu xấu đó).
    Không có mẫu xấu ⇒ `phat_hien_sau_mau = None` (clip này không có gì để phát hiện — KHÔNG phải
    "phát hiện sau 0 mẫu").
    """
    values = drift_values(rows)
    bad_idx = next((i for i, value in enumerate(values) if value < float(bad)), None)
    if bad_idx is None:
        return {"mau_xau_dau": None, "phat_hien_sau_mau": None, "p05_luc_phat_hien": None}
    series = rolling_p05(values, window)
    for index in range(bad_idx, len(values)):
        value = series[index]
        if value is not None and value < float(flag):
            return {
                "mau_xau_dau": bad_idx,
                "phat_hien_sau_mau": index - bad_idx,
                "p05_luc_phat_hien": value,
            }
    return {"mau_xau_dau": bad_idx, "phat_hien_sau_mau": None, "p05_luc_phat_hien": None}


def static_control(rows, *, min_drift: float = 0.99, min_samples: int = 20) -> dict:
    """Đối chứng cảnh TĨNH: vật đứng yên ⇒ nội suy LK và VOS phải trùng nhau (drift ≈ 1,0).

    Đây là phép kiểm **bookkeeping** (`_shown_at`/`_pending_drift`), không phải phép đo chất lượng
    bám: cảnh tĩnh mà drift thấp nghĩa là ta đang so SAI CẶP frame, chứ không phải LK kém.

    Tiêu chí đạt = **`drift_iou` (trung bình) ≥ `min_drift`** — đúng đại lượng đã đăng ký trước trong
    ticket 15 (`drift_iou >= 0,99` với `drift_n >= 20` ⇒ `min_samples` mặc định 20, thấp hơn ngưỡng
    công bố phân vị 30). `p05` KHÔNG tham gia phán quyết vì đuôi thấp của cảnh tĩnh bị làm bẩn bởi
    phép **làm tròn toạ độ nguyên** của LK (đo 13-11, 357 mẫu: mean 0,9955 nhưng p05 0,9885 — lệch
    0,0015 so với ngưỡng). Ghi chú đi kèm nói rõ khi p05 dưới ngưỡng, để không ai đọc p05 thành
    lỗi bookkeeping.
    """
    values = drift_values(rows)
    n = len(values)
    mean = round(float(np.mean(values)), 4) if n else None
    p05 = round(float(np.percentile(values, 5)), 4) if n >= min_samples else None
    reasons = []
    if n < min_samples:
        reasons.append(f"chỉ có {n} mẫu (< {min_samples}) — chưa đủ để kết luận")
    elif mean is not None and mean < float(min_drift):
        reasons.append(f"mean = {mean} < {min_drift} ⇒ nghi so lệch cặp frame, KHÔNG phải LK kém")
    notes = []
    if p05 is not None and p05 < float(min_drift):
        notes.append(f"p05 = {p05} < {min_drift} trong khi mean ĐẠT: đuôi thấp do làm tròn toạ độ "
                     "nguyên của LK, không phải lỗi bookkeeping")
    return {
        "n": n,
        "drift_iou_mean": mean,
        "drift_iou_p05": p05,
        "nguong_mean": min_drift,
        "dat": not reasons,
        "ly_do": reasons,
        "ghi_chu": notes,
    }


def low_p05_low_empty(rows, *, flag: float = FLAG_P05, max_empty: float = 0.03,
                      window: int = WINDOW, min_measured=None) -> dict:
    """Đếm cửa sổ `window` lần VOS có `p05 < flag` **và** tỉ lệ mask rỗng `< max_empty`.

    Đây là **điều kiện tiên quyết của ticket 14** (cờ chẩn đoán "LK nội suy lệch"): nếu mọi cửa sổ
    p05 thấp đều có mask rỗng cao thì cờ đó chỉ là bản sao của `empty_frac_window` ⇒ claim vượt dữ
    liệu. Đếm trên trục **lần VOS** (mỗi dòng CSV = 1 lần VOS) vì mask rỗng cũng là một lần VOS.

    `min_measured` mặc định = `window // 2`: một cửa sổ phải có ít nhất nửa số mẫu ĐO ĐƯỢC thì p05
    mới có nghĩa (cửa sổ toàn mask rỗng thì p05 của 2 mẫu là vô nghĩa). Trước đây tham số này ghim
    theo `WINDOW` (100) ⇒ gọi với `window=20` cho **0 cửa sổ** và trả `False` một cách im lặng — đúng
    bẫy "0/None ≠ đã đo" (review độc lập vòng 2, P2).

    `co_dieu_kien_ticket_14` là **None** khi không có cửa sổ nào đủ mẫu: "chưa đo được", không phải
    "đã đo và không có".
    """
    min_measured = max(1, window // 2) if min_measured is None else int(min_measured)
    total = flagged = both = 0
    for start in range(max(0, len(rows) - window + 1)):
        chunk = rows[start:start + window]
        values = drift_values(chunk)
        # Ô `empty` trống = CHƯA ĐO ⇒ không được đếm thành "không rỗng" (AGENTS §6). Cửa sổ phải có
        # ít nhất nửa số dòng khai `empty` mới được dùng để nói về tỉ lệ rỗng.
        known = [row["empty"] for row in chunk if row.get("empty") is not None]
        if len(values) < min_measured or len(known) < min_measured:
            continue
        total += 1
        p05 = float(np.percentile(values, 5))
        empty_frac = sum(1 for value in known if value) / len(known)
        if p05 < float(flag):
            flagged += 1
            if empty_frac < float(max_empty):
                both += 1
    return {
        "cua_so": window,
        "min_mau_do_duoc": min_measured,
        "nguong_p05": flag,
        "nguong_empty": max_empty,
        "n_cua_so_du_mau": total,
        "n_p05_thap": flagged,
        "n_p05_thap_va_empty_thap": both,
        "co_dieu_kien_ticket_14": (both > 0) if total else None,
    }


def summarize(rows, *, window: int = WINDOW) -> dict:
    """Toàn bộ số của một file mẫu: đếm, tỉ lệ mask rỗng, phân vị, tỉ lệ báo, độ trễ phát hiện.

    `drift_iou_p05` ở đây là p05 trên **toàn dãy** của lần đo, KHÁC p05 của 200 mẫu CUỐI trong
    `status.json` — cùng định nghĩa phân vị, khác tập mẫu.
    """
    values = drift_values(rows)
    n = len(values)
    empties = [row["empty"] for row in rows if row.get("empty") is not None]
    return {
        "n_dong": len(rows),
        "n_mau_drift": n,
        "empty_frac": round(sum(1 for e in empties if e) / len(empties), 3) if empties else None,
        "drift_iou_mean": round(float(np.mean(values)), 4) if n else None,
        "drift_iou_p05": (round(float(np.percentile(values, 5)), 4)
                          if n >= MIN_SAMPLES else None),
        "bao_dong_070": flag_rate(values, threshold=HEALTHY_P05, window=window),
        "bao_dong_030": flag_rate(values, threshold=FLAG_P05, window=window),
        "phat_hien": detect_latency(rows, window=window),
        "p05_thap_va_empty": low_p05_low_empty(rows, window=window),
    }
