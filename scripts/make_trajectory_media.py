"""
Sinh ẢNH QUỸ ĐẠO cho báo cáo (yêu cầu 5 của đề cương: "hiển thị vị trí, vùng phân đoạn, **quỹ đạo
di chuyển**") từ CSV mẫu-drift mà worker live ghi ra (`src/drift_samples.py`).

Vì sao cần script này: repo đã có `scripts/plot_metrics.py` vẽ quỹ đạo từ `*_metrics.csv` của đường
offline, nhưng **đường live** ghi CSV khác (`drift_samples_*.csv`: mỗi dòng là một lần VOS, kèm ô
bao đã phát và `empty`). Không có ảnh thì "có quỹ đạo" chỉ là lời nói; ảnh còn để kiểm bằng mắt hai
thứ mà số không nói được: (a) quỹ đạo có đi qua vật hay đi lang thang, (b) chỗ mất dấu xảy ra ở đâu
trên khung (thường là vật ra mép).

Cách dùng:
    python scripts/make_trajectory_media.py \
        --csv data/drift_samples_binh1_2026-11-13_125634.csv --clip data/binh1.mp4 \
        --out docs/media/traj/binh1_duong_di.png

Input  : CSV có các cột `frame_idx, seq, vos_ms, empty, drift_iou, bbox_x1, bbox_y1, bbox_x2, bbox_y2`
         (đúng header của `src/drift_samples.py`), clip gốc (tuỳ chọn — để làm nền).
Output : 1 PNG 2 ô: (trái) quỹ đạo tâm ô bao trên nền frame đầu; (phải) ô bao rộng/cao theo thời gian
         + đường `drift_iou` để thấy chỗ nào VOS bám lệch.
Lưu ý  : `empty = 1` là lần VOS trả mask RỖNG ⇒ KHÔNG có toạ độ tâm; ảnh đánh dấu X đỏ **tại vị trí
         ước lượng theo mẫu trước** và ghi rõ trong chú thích — bịa toạ độ cho lần mất dấu là làm
         hỏng đúng thứ ảnh này định chứng minh. Script không vẽ `drift_iou` thành "độ chính xác"
         (AGENTS §6: đó là độ TỰ NHẤT QUÁN).
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")                     # không cần màn hình (chạy được trên server/CI)
import matplotlib.pyplot as plt           # noqa: E402
import numpy as np                        # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Ngưỡng công bố phân vị DÙNG CHUNG với `status.json`/`score_miou` (ticket #23): trước đây script này
# tự đặt 20 ⇒ cùng đại lượng `drift_iou_p05` mà ba ngưỡng khác nhau trong repo.
from src.drift_samples import MIN_SAMPLES, phan_vi  # noqa: E402

COT_BAT_BUOC = ("frame_idx", "empty", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")


def read_traj(path) -> dict:
    """Đọc CSV mẫu-drift → dict mảng numpy. Ném `ValueError` nếu thiếu cột bắt buộc.

    Cố ý KHÔNG đổi `None`/rỗng thành 0: toạ độ 0 là một vị trí thật trên khung, khác hẳn "không đo
    được" (AGENTS §6 — bẫy `0/None` đã gặp 3 lần trong repo). Dòng thiếu toạ độ bị BỎ khỏi đường đi
    và được đếm riêng vào `n_thieu_toa_do`.
    """
    path = Path(path)
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        thieu = [c for c in COT_BAT_BUOC if c not in (reader.fieldnames or [])]
        if thieu:
            raise ValueError(f"{path.name}: thiếu cột {thieu} (header: {reader.fieldnames})")
        rows = list(reader)

    def _so(row, key):
        raw = (row.get(key) or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    data = {"frame_idx": [], "cx": [], "cy": [], "w": [], "h": [], "empty": [],
            "drift_iou": [], "vos_ms": []}
    n_thieu = 0
    for row in rows:
        x1, y1, x2, y2 = (_so(row, k) for k in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"))
        empty = (_so(row, "empty") or 0.0) >= 1.0
        data["frame_idx"].append(_so(row, "frame_idx") or 0.0)
        data["empty"].append(empty)
        data["drift_iou"].append(_so(row, "drift_iou"))
        data["vos_ms"].append(_so(row, "vos_ms"))
        if x1 is None or y1 is None or x2 is None or y2 is None or x2 <= x1 or y2 <= y1:
            n_thieu += 1
            data["cx"].append(None)
            data["cy"].append(None)
            data["w"].append(None)
            data["h"].append(None)
            continue
        data["cx"].append((x1 + x2) / 2.0)
        data["cy"].append((y1 + y2) / 2.0)
        data["w"].append(x2 - x1)
        data["h"].append(y2 - y1)

    out = {k: np.array(v, dtype=object if k in ("cx", "cy", "w", "h", "drift_iou") else float)
           for k, v in data.items()}
    out["empty"] = out["empty"].astype(bool)
    return {"data": out, "n_dong": len(rows), "n_thieu_toa_do": n_thieu, "path": path}


def _background(clip):
    """Frame đầu của clip (nền cho quỹ đạo); `None` nếu không có clip/không đọc được."""
    if not clip:
        return None
    import cv2

    cap = cv2.VideoCapture(str(clip))
    try:
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


def draw(traj: dict, background=None, title: str = ""):
    """Vẽ hình 2 ô từ dữ liệu `read_traj`. Trả `(fig, thong_ke)` — tách khỏi `main()` để test được."""
    data = traj["data"]
    cx = np.array([np.nan if v is None else float(v) for v in data["cx"]], dtype=float)
    cy = np.array([np.nan if v is None else float(v) for v in data["cy"]], dtype=float)
    w = np.array([np.nan if v is None else float(v) for v in data["w"]], dtype=float)
    h = np.array([np.nan if v is None else float(v) for v in data["h"]], dtype=float)
    drift = np.array([np.nan if v is None else float(v) for v in data["drift_iou"]], dtype=float)
    frame_idx = np.asarray(data["frame_idx"], dtype=float)
    empty = np.asarray(data["empty"], dtype=bool)
    co_toa_do = ~np.isnan(cx)

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(13, 5.2))
    # ── ô trái: quỹ đạo tâm ô bao
    if background is not None:
        ax0.imshow(background[:, :, ::-1])          # cv2 là BGR, matplotlib cần RGB
        ax0.set_xlim(0, background.shape[1])
        ax0.set_ylim(background.shape[0], 0)        # ảnh: y hướng xuống
    if co_toa_do.sum() >= 2:
        # Tô màu theo THỜI GIAN để nhìn được hướng đi — một đường xanh đồng màu trên cảnh có vật
        # quay lại chỗ cũ (binh1 lặp 2,7 vòng) thì không nói được gì về chiều di chuyển.
        xs, ys = cx[co_toa_do], cy[co_toa_do]
        from matplotlib.collections import LineCollection
        from matplotlib.colors import Normalize

        diem = np.array([xs, ys]).T.reshape(-1, 1, 2)
        doan = np.concatenate([diem[:-1], diem[1:]], axis=1)
        norm = Normalize(vmin=0, vmax=max(1, len(doan)))
        lc = LineCollection(doan, cmap="viridis", norm=norm, lw=1.6)
        lc.set_array(np.arange(len(doan)))
        ax0.add_collection(lc)
        ax0.plot(xs, ys, "o", ms=2.0, color="white", alpha=0.5)
        ax0.plot([], [], lw=2, color="#440154", label="tâm ô bao, màu đậm→vàng = sớm→muộn")
        ax0.plot(cx[co_toa_do][0], cy[co_toa_do][0], "s", ms=9, color="#2ca02c", label="bắt đầu")
        ax0.plot(cx[co_toa_do][-1], cy[co_toa_do][-1], "D", ms=8, color="#ff7f0e", label="kết thúc")
    if empty.any():
        # Đánh dấu mất dấu tại mẫu CÓ toạ độ gần nhất — KHÔNG bịa toạ độ mới (xem docstring).
        gan = np.where(co_toa_do)[0]
        for i in np.where(empty)[0]:
            truoc = gan[gan < i]
            if truoc.size == 0:
                continue
            j = truoc[-1]
            ax0.plot(cx[j], cy[j], "x", ms=11, mew=2.2, color="red")
        # Một nhãn duy nhất cho cả chú thích (tránh legend 26 dòng "X")
        # KHÔNG gọi là "mất dấu": AGENTS §6 (đính chính 14-11) — phần lớn mask rỗng là **vật đã rời
        # khung** (binh1: 36 % cả phiên nhưng chỉ 1,7 % khi chai còn trong khung). Ảnh vào báo cáo mà
        # nhãn sai thì bị trích thành "mất dấu 170 lần".
        ax0.plot([], [], "x", ms=9, mew=2, color="red",
                 label=f"mask rỗng ({int(empty.sum())} lần VOS; phần lớn là vật ngoài khung)")
    ax0.set_title("Quỹ đạo tâm ô bao trên khung hình" + (f"\n{title}" if title else ""),
                  fontsize=10)
    if ax0.get_legend_handles_labels()[0]:        # rỗng (0 mẫu) ⇒ đừng gọi, matplotlib cảnh báo
        ax0.legend(loc="upper right", fontsize=7)
    ax0.grid(alpha=0.2)

    # ── ô phải: kích thước ô bao + drift theo thời gian
    ax1.plot(frame_idx, w, lw=1.1, label="rộng (px)")
    ax1.plot(frame_idx, h, lw=1.1, label="cao (px)")
    ax1.set_xlabel("frame_idx")
    ax1.set_ylabel("kích thước ô bao (px)")
    ax1.grid(alpha=0.2)
    ax1.legend(loc="upper left", fontsize=8)
    if np.isfinite(drift).any():
        ax2 = ax1.twinx()
        ax2.plot(frame_idx, drift, lw=0.9, color="gray", alpha=0.8,
                 label="drift_iou (tự nhất quán)")
        ax2.set_ylabel("drift_iou — TỰ NHẤT QUÁN, không phải độ chính xác", fontsize=8)
        ax2.set_ylim(0, 1.02)
        ax2.legend(loc="lower right", fontsize=8)
    ax1.set_title("Kích thước ô bao theo thời gian", fontsize=10)

    thong_ke = {
        "n_dong": traj["n_dong"],
        "n_co_toa_do": int(co_toa_do.sum()),
        "n_thieu_toa_do": traj["n_thieu_toa_do"],
        "n_mask_rong": int(empty.sum()),
        "drift_iou_mean": None if not np.isfinite(drift).any() else round(float(np.nanmean(drift)), 3),
        "drift_iou_p05": phan_vi(drift[np.isfinite(drift)], digits=3),
        # Ngưỡng công bố đi CÙNG con số (ticket #23): người đọc `.json` sau này thấy `None` phải biết
        # đó là "n < 30" chứ không phải "p05 = 0" hay "quên đo".
        "nguong_p05": MIN_SAMPLES,
        "drift_n": int(np.isfinite(drift).sum()),
    }
    fig.tight_layout()
    return fig, thong_ke


def _doc_hop(expect, dang=None):
    """Đọc `--expect-bbox` ⇒ `((x1, y1, x2, y2) | None, lỗi | None, dạng hiệu lực | None)`.

    Dạng hộp phải được XÁC ĐỊNH, không đoán: `50,100,300,400` là hộp `(x,y,w,h)` **hợp lệ** nhưng cũng
    đọc được thành `(x1,y1,x2,y2)` ⇒ đoán sai thì cổng in "ô bao KHỚP" trong khi thực ra không khớp
    (ticket #25 — đúng loại "cổng báo khớp OAN" mà AGENTS §6 cấm). Ba cách khai:
    `--expect-bbox-dang xywh`, tiền tố `xywh:50,100,300,400`, hoặc `xyxy:...`.
    Không khai + không suy ra được chắc chắn ⇒ trả lỗi để người gọi in "KHÔNG KẾT LUẬN".
    Phần tử thứ ba là **dạng hiệu lực** (`"xywh"`/`"xyxy"`) để provenance ghi cả ca SUY RA.

    Số không hữu hạn (`nan`/`inf`) bị TỪ CHỐI: `max()` bỏ qua NaN và `nan > 0.1` là `False` ⇒ cổng sẽ
    in "khớp" với một hộp vô nghĩa (P1 review 16-11).
    """
    raw = str(expect).strip()
    if not raw:
        return None, "--expect-bbox rỗng ⇒ không có gì để so (bỏ cờ nếu không muốn kiểm)", None
    for ten in ("xywh", "xyxy"):
        if raw.lower().startswith(f"{ten}:"):
            dang, raw = ten, raw[len(ten) + 1:]
    if dang not in (None, "xywh", "xyxy"):
        return None, f"dạng hộp lạ: {dang!r} (chỉ nhận 'xywh' | 'xyxy')", None
    try:
        a, b, c, d = (float(v) for v in raw.replace(";", ",").split(","))
    except ValueError:
        return None, (
            f"--expect-bbox phải là 4 số; nhận {expect!r}. Khai dạng: "
            "`--expect-bbox-dang xywh|xyxy` hoặc tiền tố `xywh:50,100,300,400`"), None
    if not all(math.isfinite(v) for v in (a, b, c, d)):
        return None, f"--expect-bbox có số không hữu hạn (nan/inf): {expect!r}", None
    if dang is None:
        # Hộp `(x, y, w, h)` mà `w > x` (vd `50,100,300,400`) đọc kiểu nào cũng "hợp lệ" ⇒ KHÔNG ĐOÁN.
        if c <= a or d <= b:
            dang = "xywh"          # `x2 <= x1` ⇒ chỉ có thể là (x, y, w, h)
            print(f"[traj] dạng hộp SUY RA: xywh (vì x2<=x1 hoặc y2<=y1 trong {expect})")
        else:
            return None, (
                f"--expect-bbox {expect} đọc được CẢ hai kiểu (x1,y1,x2,y2) và (x,y,w,h) ⇒ "
                "KHÔNG so được (không đoán): khai `--expect-bbox-dang xywh` hoặc `xyxy`"), None
    if dang == "xywh":
        x, y, w, h = a, b, c, d
        if w <= 0 or h <= 0:
            return None, f"--expect-bbox dạng x,y,w,h mà w/h không dương ({w}, {h})", None
        return (x, y, x + w, y + h), None, dang
    x1, y1, x2, y2 = a, b, c, d
    if x2 <= x1 or y2 <= y1:
        return None, (f"--expect-bbox dạng x1,y1,x2,y2 mà x2<=x1 hoặc y2<=y1 ({x1},{y1},{x2},{y2}) — "
                      "nếu đây là (x,y,w,h) thì khai `--expect-bbox-dang xywh`"), None
    return (x1, y1, x2, y2), None, dang


def _iou_hop(a, b) -> float:
    """IoU của hai hộp `(x1, y1, x2, y2)`."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    giao = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    hop_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    hop_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    tong = hop_a + hop_b - giao
    return 0.0 if tong <= 0 else giao / tong


IOU_CUNG_VAT = 0.7       # IoU tối thiểu để coi hai hộp là CÙNG VẬT


def _canh_bao_bbox(traj: dict, expect: str, dang: str | None = None,
                   ghi_nhan: dict | None = None) -> str:
    """So ô bao dòng ĐẦU của CSV với ô mong đợi ⇒ `"khop" | "lech" | "khong_ket_luan"`.

    Vì sao cần: 14-11 phát hiện ô `104,308,209,287` phủ **khuôn mặt** chứ không phải chai, và toàn bộ
    số của một phase đo bằng ô đó là vô nghĩa. CSV không tự khai nó đo vật nào ⇒ người dùng phải khai.

    Tiêu chí là **IoU hai hộp ≥ 0,7** (cùng vật), KHÔNG dùng "lệch % từng cạnh": với chai dựng đứng,
    sai 37 px ở cạnh cao = 9 % trong khi IoU vẫn 0,71 ⇒ ngưỡng theo cạnh vừa báo oan vừa không trả lời
    "có cùng một vật hay không". Độ lệch từng cạnh vẫn được in như **thông tin**, không quyết định.

    Không in "khớp" khi chưa so được (ticket #25). `ghi_nhan` (tuỳ chọn) được điền `expect_bbox`,
    `expect_bbox_dang`, `ket_qua_hop`, `iou_bbox` để **provenance JSON ghi lại cổng đã kết luận gì** —
    câu "đừng dùng ảnh này làm bằng chứng" chỉ ở stdout thì file `.json` còn lại trông y hệt lần đạt
    (P2 review 16-11).
    """
    def _xong(ket_qua: str, iou_hop=None) -> str:
        if ghi_nhan is not None:
            ghi_nhan.update({"expect_bbox": expect, "expect_bbox_dang": dang_hieu_luc,
                             "ket_qua_hop": ket_qua,
                             "iou_bbox": None if iou_hop is None else round(float(iou_hop), 4)})
        return ket_qua

    hop, loi, dang_hieu_luc = _doc_hop(expect, dang)
    if loi:
        print(f"[traj] KHÔNG KẾT LUẬN: {loi}")
        return _xong("khong_ket_luan")
    x1e, y1e, x2e, y2e = hop
    data = traj["data"]
    if not len(data["cx"]) or data["cx"][0] is None:
        print("[traj] không có ô bao ở dòng đầu CSV ⇒ không so được bbox")
        return _xong("khong_ket_luan")
    try:
        cx, cy = float(data["cx"][0]), float(data["cy"][0])
        w, h = float(data["w"][0]), float(data["h"][0])
    except (TypeError, ValueError):
        print("[traj] ô bao dòng đầu không phải số ⇒ không so được bbox")
        return _xong("khong_ket_luan")
    if not all(math.isfinite(v) for v in (cx, cy, w, h)):
        # CSV có `nan`/`inf` ⇒ mọi phép so đều vô nghĩa (`nan > ngưỡng` luôn False).
        print(f"[traj] KHÔNG KẾT LUẬN: ô bao dòng đầu có số không hữu hạn ({cx}, {cy}, {w}, {h})")
        return _xong("khong_ket_luan")
    hop_csv = (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)
    iou_hop = _iou_hop(hop_csv, (x1e, y1e, x2e, y2e))
    cx_e, cy_e = (x1e + x2e) / 2.0, (y1e + y2e) / 2.0
    lech = max(abs(cx - cx_e) / max(1.0, (x2e - x1e)), abs(cy - cy_e) / max(1.0, (y2e - y1e)),
               abs(w - (x2e - x1e)) / max(1.0, (x2e - x1e)),
               abs(h - (y2e - y1e)) / max(1.0, (y2e - y1e)))
    if not (iou_hop >= IOU_CUNG_VAT):          # `not >=` để `nan` rơi vào nhánh CẢNH BÁO
        print(f"[traj] CẢNH BÁO: ô bao dòng đầu (tâm {cx:.0f},{cy:.0f} rộng {w:.0f} cao {h:.0f}) "
              f"chỉ IoU {iou_hop:.2f} < {IOU_CUNG_VAT} với --expect-bbox ⇒ CÓ THỂ ĐANG ĐO SAI VẬT "
              f"(lệch cạnh tối đa {lech * 100:.0f}%). Đừng commit ảnh này làm bằng chứng.")
        return _xong("lech", iou_hop)
    print(f"[traj] ô bao khớp --expect-bbox (CÙNG VẬT): IoU {iou_hop:.2f} >= {IOU_CUNG_VAT} "
          f"(lệch cạnh tối đa {lech * 100:.0f}%)")
    return _xong("khop", iou_hop)


def _dirty_code(status_porcelain: str) -> bool:
    """Có thay đổi NGOÀI `data/` và `docs/media/` không (= code bẩn, số không tái lập)?

    BUG ĐÃ GẶP: `.strip()` trên cả khối `git status` làm mất **dấu cách đầu dòng** của dòng đầu tiên
    (`" M docs/…"` → `"M docs/…"`) ⇒ cắt `line[3:]` lệch một ký tự ⇒ `docs/media/...` không được
    miễn trừ và mọi ảnh media tự khai "cây bẩn". Vì vậy đầu vào ở đây KHÔNG được strip.
    """
    for line in status_porcelain.splitlines():
        if not line.strip():
            continue
        path = line[3:] if len(line) > 3 else ""
        if not path.startswith(("data/", "docs/media/")):
            return True
    return False


def provenance(csv_path, clip_path, out_path, title: str, bbox_dau) -> dict:
    """Metadata đi kèm ảnh: **ảnh không có provenance thì không kiểm lại được** (và một ảnh sai chú
    thích sống lâu hơn mọi lời giải thích).

    Vì sao phải có `bbox_dau` + `sha256` của CSV: 14-11 phát hiện ảnh/media sinh từ CSV đo bằng **ô
    phủ khuôn mặt** (`104,308,209,287`) trông y như ảnh đo bằng ô chọn đúng vật. Ghi ô bao dòng đầu
    vào đây thì người đọc đối chiếu được với `--expect-bbox`, không phải tin lời.
    """
    import hashlib
    import subprocess

    def _sha(path):
        if path is None:
            return None
        try:
            return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
        except OSError:
            return None

    def _git(args):
        try:
            return subprocess.run(["git", *args], cwd=str(_REPO_ROOT), capture_output=True,
                                  text=True, check=True).stdout
        except Exception:                        # noqa: BLE001 — provenance không được ném
            return None

    rev = _git(["rev-parse", "HEAD"])
    changed = _git(["status", "--porcelain"]) or ""
    dirty_code = _dirty_code(changed)
    return {
        "do_luc": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "lenh": " ".join(sys.argv),
        "git_rev": (rev or "").strip() or None, "git_dirty_code": dirty_code,
        "csv": str(csv_path), "csv_sha256_16": _sha(csv_path),
        "clip": str(clip_path) if clip_path else None,
        "clip_sha256_16": _sha(clip_path),
        "bbox_dong_dau_x1y1x2y2": list(bbox_dau) if bbox_dau else None,
        "tieu_de": title,
        "anh": str(out_path), "anh_sha256_16": _sha(out_path) if Path(out_path).is_file() else None,
        "canh_bao": "Độ tự nhất quán (drift_iou) KHÔNG phải độ chính xác — xem AGENTS §6.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Vẽ ảnh quỹ đạo (đường live) từ CSV mẫu-drift.")
    parser.add_argument("--csv", required=True, help="CSV của drift_samples (worker live ghi ra)")
    parser.add_argument("--clip", help="clip gốc để làm nền (tuỳ chọn)")
    parser.add_argument("--out", default="docs/media/traj/quy_dao.png")
    parser.add_argument("--title", default="")
    parser.add_argument("--meta", default="",
                        help="ghi provenance JSON (mặc định: cạnh ảnh, cùng tên .json)")
    parser.add_argument("--expect-bbox", default=None,
                        help="ô bao bạn ĐÃ CHỌN cho vật; phải khai kèm --expect-bbox-dang (hoặc tiền tố "
                             "xywh:/xyxy:). IoU < 0,7 với ô bao dòng đầu CSV ⇒ CẢNH BÁO + exit 1 "
                             "(ô chọn sai từng làm toàn bộ số Phase 4c vô nghĩa — log 14-11)")
    parser.add_argument("--expect-bbox-dang", choices=["xywh", "xyxy"], default=None,
                        help="dạng của --expect-bbox. Không khai và con số đọc được CẢ hai kiểu "
                             "⇒ script KHÔNG kết luận (không đoán — ticket #25)")
    args = parser.parse_args(argv)

    traj = read_traj(args.csv)
    fig, thong_ke = draw(traj, _background(args.clip), args.title or Path(args.csv).stem)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    plt.close(fig)

    print(f"[traj] {out} ({out.stat().st_size // 1024} KB)")
    data = traj["data"]
    bbox_dau = None
    if len(data["cx"]) and data["cx"][0] is not None:
        cx, cy = float(data["cx"][0]), float(data["cy"][0])
        w, h = float(data["w"][0]), float(data["h"][0])
        bbox_dau = (round(cx - w / 2), round(cy - h / 2), round(cx + w / 2), round(cy + h / 2))
    meta_path = Path(args.meta) if args.meta else out.with_suffix(".json")
    ket_qua_hop = None
    ghi_nhan: dict = {}
    if args.expect_bbox is not None:      # `is not None`: cờ rỗng vẫn phải đi qua cổng, không im lặng bỏ
        ket_qua_hop = _canh_bao_bbox(traj, args.expect_bbox, args.expect_bbox_dang, ghi_nhan)
    meta = provenance(args.csv, args.clip, out, args.title, bbox_dau)
    # Số của ảnh vào CHÍNH file provenance: trước đây `drift_iou_p05`/`drift_n` chỉ in ra stdout ⇒
    # `.json` đi kèm ảnh không nói được p05 có được công bố hay không (ticket #23: `None` phải đọc
    # được là "n < 30", không phải "p05 = 0").
    meta["thong_ke"] = thong_ke
    if ghi_nhan:
        meta.update(ghi_nhan)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[traj] provenance: {meta_path} (bbox dòng đầu {bbox_dau}, git_rev {meta['git_rev']})")
    print(f"[traj] {thong_ke}")
    if thong_ke["drift_n"] < MIN_SAMPLES:
        print(f"[traj] CẢNH BÁO: chỉ {thong_ke['drift_n']} mẫu drift ⇒ p05 = None"
              f" (chưa đủ {MIN_SAMPLES} mẫu để công bố phân vị)")
    if ket_qua_hop is not None and ket_qua_hop != "khop":
        # Ảnh vẫn được ghi (đã vẽ xong) — kể cả provenance — nhưng mã thoát 1 và JSON ghi
        # `ket_qua_hop`: "ô bao lệch"/"không so được" KHÔNG được dùng làm bằng chứng, mà exit 0 thì
        # script tự động sẽ coi là đạt.
        print(f"[traj] ô bao KHÔNG đạt (kết luận: {ket_qua_hop}) — đừng dùng ảnh này làm bằng chứng")
        return 1
    if thong_ke["n_thieu_toa_do"]:
        print(f"[traj] {thong_ke['n_thieu_toa_do']} dòng không có toạ độ hợp lệ (bỏ khỏi đường đi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
