"""
DriftSampleLog — ghi TỪNG mẫu `drift_iou` ra CSV để ngưỡng chẩn đoán thành tái lập được (ticket 15).

Chức năng: `status.json` chỉ có mean/p05 của cửa sổ 200 mẫu ⇒ **không đo được** "phát hiện sau bao
           nhiêu mẫu" và "bao nhiêu % cửa sổ báo oan". Module này ghi từng mẫu ra CSV
           (`frame_idx, seq, vos_ms, empty, drift_iou, bbox_*`) và cung cấp các hàm THUẦN để đọc
           lại + phân tích: `rolling_p05`, `flag_rate`, `detect_latency`, `static_control`.
Input  : `DriftSampleLog.write(...)` từ `LiveTrackingSession`; `read_samples(path)` cho CSV đã ghi.
Output : `<out_dir>/drift_samples.csv` (một dòng / một mẫu drift) + dict thống kê thuần.
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
# con số trong `status.json`/artifact cũ (cùng định nghĩa, cùng độ trễ bất đối xứng).
WINDOW = 200
# Số mẫu TỐI THIỂU để được coi là "đủ mẫu" khi kết luận cảnh tĩnh (p05 của 5 mẫu là min ⇒ vô nghĩa).
MIN_SAMPLES = 20
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
            handle = self._ensure_open()
            handle.write(line)
            # Flush mỗi dòng: phiên live bị dừng bằng SIGTERM/`kill` (không qua `finally`) vẫn giữ
            # được mẫu đã đo. Giá: ~20–50 µs cho 8 dòng/giây ⇒ không đáng kể so với `vos_ms`.
            handle.flush()
            self.n_rows += 1

    def close(self) -> None:
        with self._lock:
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


def static_control(rows, *, min_drift: float = 0.99, min_samples: int = MIN_SAMPLES) -> dict:
    """Đối chứng cảnh TĨNH: vật đứng yên ⇒ nội suy LK và VOS phải trùng nhau (drift ≈ 1,0).

    Đây là phép kiểm **bookkeeping** (`_shown_at`/`_pending_drift`), không phải phép đo chất lượng
    bám: cảnh tĩnh mà drift thấp nghĩa là ta đang so SAI CẶP frame, chứ không phải LK kém.
    """
    values = drift_values(rows)
    n = len(values)
    p05 = round(float(np.percentile(values, 5)), 4) if n >= min_samples else None
    reasons = []
    if n < min_samples:
        reasons.append(f"chỉ có {n} mẫu (< {min_samples}) — chưa đủ để kết luận")
    if p05 is not None and p05 < float(min_drift):
        reasons.append(f"p05 = {p05} < {min_drift} ⇒ nghi so lệch cặp frame, KHÔNG phải LK kém")
    return {
        "n": n,
        "drift_iou_mean": round(float(np.mean(values)), 4) if n else None,
        "drift_iou_p05": p05,
        "nguong_p05": min_drift,
        "dat": not reasons,
        "ly_do": reasons,
    }


def summarize(rows, *, window: int = WINDOW) -> dict:
    """Toàn bộ số của một file mẫu: đếm, tỉ lệ mask rỗng, phân vị, tỉ lệ báo, độ trễ phát hiện."""
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
    }
