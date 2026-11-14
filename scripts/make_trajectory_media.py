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
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")                     # không cần màn hình (chạy được trên server/CI)
import matplotlib.pyplot as plt           # noqa: E402
import numpy as np                        # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
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
        ax0.plot([], [], "x", ms=9, mew=2, color="red",
                 label=f"mất dấu ({int(empty.sum())} lần VOS trả mask rỗng)")
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
        "n_mat_dau": int(empty.sum()),
        "drift_iou_mean": None if not np.isfinite(drift).any() else round(float(np.nanmean(drift)), 3),
        "drift_iou_p05": None if np.isfinite(drift).sum() < 20
        else round(float(np.nanpercentile(drift, 5)), 3),
        "drift_n": int(np.isfinite(drift).sum()),
    }
    fig.tight_layout()
    return fig, thong_ke


def _canh_bao_bbox(traj: dict, expect: str) -> None:
    """So ô bao dòng ĐẦU của CSV với ô mong đợi; lệch >10 % thì in cảnh báo to.

    Vì sao cần: 14-11 phát hiện ô `104,308,209,287` phủ **khuôn mặt** chứ không phải chai, và toàn bộ
    số của một phase đo bằng ô đó là vô nghĩa. CSV không tự khai nó đo vật nào ⇒ người dùng phải khai.
    """
    try:
        x1e, y1e, x2e, y2e = (float(v) for v in str(expect).split(","))
    except ValueError:
        print(f"[traj] --expect-bbox phải là x1,y1,x2,y2 (hoặc x,y,w,h); nhận {expect!r}")
        return
    if x2e <= x1e or y2e <= y1e:
        # Chấp nhận CẢ `(x, y, w, h)` — chính cái bẫy đã làm hỏng một phase đo (AGENTS §6: hộp
        # `300,275,150,410` bị truyền thẳng vào SAM 2 như `x1,y1,x2,y2` ⇒ hộp rộng ÂM).
        x1e, y1e, x2e, y2e = x1e, y1e, x1e + x2e, y1e + y2e
    data = traj["data"]
    x1 = data["cx"][0], data["cy"][0]
    if x1[0] is None:
        print("[traj] dòng đầu không có toạ độ ⇒ không so được bbox")
        return
    w = float(data["w"][0])
    h = float(data["h"][0])
    cx, cy = float(x1[0]), float(x1[1])
    cx_e, cy_e = (x1e + x2e) / 2.0, (y1e + y2e) / 2.0
    lech = max(abs(cx - cx_e) / max(1.0, (x2e - x1e)), abs(cy - cy_e) / max(1.0, (y2e - y1e)),
               abs(w - (x2e - x1e)) / max(1.0, (x2e - x1e)),
               abs(h - (y2e - y1e)) / max(1.0, (y2e - y1e)))
    if lech > 0.10:
        print(f"[traj] CẢNH BÁO: ô bao dòng đầu (tâm {cx:.0f},{cy:.0f} rộng {w:.0f} cao {h:.0f}) "
              f"lệch {lech * 100:.0f}% so với --expect-bbox ⇒ CÓ THỂ ĐANG ĐO SAI VẬT. "
              "Đừng commit ảnh này làm bằng chứng.")
    else:
        print(f"[traj] ô bao khớp --expect-bbox (lệch {lech * 100:.0f}%)")


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
                                  text=True, check=True).stdout.strip()
        except Exception:                        # noqa: BLE001 — provenance không được ném
            return None

    rev = _git(["rev-parse", "HEAD"])
    changed = _git(["status", "--porcelain"]) or ""
    dirty_code = any(not line[3:].startswith("data/") for line in changed.splitlines())
    return {
        "do_luc": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "lenh": " ".join(sys.argv),
        "git_rev": rev, "git_dirty_code": dirty_code,
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
                        help="ô bao mong đợi: x1,y1,x2,y2 (hoặc x,y,w,h); lệch >10%% thì CẢNH BÁO "
                             "(ô chọn sai từng làm toàn bộ số Phase 4c vô nghĩa — log 14-11)")
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
    if data["cx"][0] is not None:
        cx, cy = float(data["cx"][0]), float(data["cy"][0])
        w, h = float(data["w"][0]), float(data["h"][0])
        bbox_dau = (round(cx - w / 2), round(cy - h / 2), round(cx + w / 2), round(cy + h / 2))
    meta_path = Path(args.meta) if args.meta else out.with_suffix(".json")
    meta = provenance(args.csv, args.clip, out, args.title, bbox_dau)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[traj] provenance: {meta_path} (bbox dòng đầu {bbox_dau}, git_rev {meta['git_rev']})")
    print(f"[traj] {thong_ke}")
    if thong_ke["drift_n"] < 20:
        print(f"[traj] CẢNH BÁO: chỉ {thong_ke['drift_n']} mẫu drift ⇒ p05 = None (chưa đủ mẫu)")
    if args.expect_bbox:
        _canh_bao_bbox(traj, args.expect_bbox)
    if thong_ke["n_thieu_toa_do"]:
        print(f"[traj] {thong_ke['n_thieu_toa_do']} dòng không có toạ độ hợp lệ (bỏ khỏi đường đi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
