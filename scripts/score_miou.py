"""
CHẤM "BÁM ĐÚNG" bằng mIoU mask vs GT (việc #6 của plan) — thước đo duy nhất nói được *đúng/sai*.

Vì sao phải có: mọi con số "chất lượng" đang có trong repo đều là **độ tự nhất quán**
(`drift_iou`, `stability`): VOS bám lệch một cách ỔN ĐỊNH thì `drift_iou` vẫn cao (AGENTS §6). Muốn
nói "bám đúng" thì phải có **GT mask gán tay** và chấm `IoU(mask_pred, mask_gt)`.

Chức năng
  `label`  : cắt frame ra PNG để gán tay + sinh `index.json` (kèm cảnh báo về thiên lệch nếu dùng
             `--suggest` sinh mask gợi ý bằng chính SAM 2 — mIoU chấm trên GT do model sinh ra là
             ĐO CHÍNH NÓ, không phải đo chất lượng).
  `score`  : đọc mask model xuất ra (`live_worker --dump-mask-frames`) + GT ⇒ mIoU, bảng từng frame,
             artifact JSON có `git_rev`/`git_dirty_code`/`lenh`/`do_luc`.

Quy tắc chấm (bẫy `0/None` đã gặp 3 lần trong repo):
  - GT CÓ vật mà model trả rỗng  ⇒ IoU = **0,0** (không phải "không đo được");
  - GT RỖNG                      ⇒ **không chấm** frame đó (NaN/Ng), đếm riêng `so_frame_gt_rong`;
  - thiếu file mask của model    ⇒ đếm `so_frame_thieu_mask`, KHÔNG coi là 0 (chưa chạy ≠ bám sai);
  - `mIoU = None` khi không chấm được frame nào (không bao giờ in 0 cho "chưa đo").

Định dạng GT (commit vào `docs/gt/<clip>/`):
    docs/gt/index.json                    # {"clip": ..., "frames": [...], "nguoi_gan": ..., ...}
    docs/gt/<clip>/gt_000050.png          # mask nhị phân 0/255, cùng kích thước frame gốc
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

GT_DIR = _REPO_ROOT / "docs" / "gt"


# ── phần THUẦN (test được, không cần model) ─────────────────────────────────────────────


def iou(pred: np.ndarray, gt: np.ndarray) -> float | None:
    """IoU của hai mask nhị phân. `None` **chỉ** khi GT rỗng (không có gì để chấm).

    `pred` rỗng + `gt` có vật ⇒ **0,0**. Đây là điểm sửa quan trọng nhất so với bẫy `IoU(rỗng,rỗng)
    = 1,0` (đã gặp 3 lần trong repo): GT rỗng không phải "bám đúng tuyệt đối".
    """
    p = np.asarray(pred) > 0
    g = np.asarray(gt) > 0
    if p.shape != g.shape:
        raise ValueError(f"mask lệch kích thước: pred {p.shape} vs gt {g.shape}")
    tong_gt = int(g.sum())
    if tong_gt == 0:
        return None
    hop = int(np.logical_or(p, g).sum())
    return 0.0 if hop == 0 else float(np.logical_and(p, g).sum()) / hop


def doc_mask(path) -> np.ndarray:
    """Đọc PNG mask → bool. Ảnh xám/màu đều được (>0 là thuộc vật)."""
    import cv2

    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"không đọc được ảnh mask: {path}")
    if img.ndim == 3:
        img = img.max(axis=2)               # mask 3 kênh (một số tool xuất RGB)
    return img > 0


def cham(ds_frame, gt_dir: Path) -> dict:
    """Chấm danh sách frame. `ds_frame`: [{"frame_idx": int}] từ `index.json`."""
    rows, miou, gt_rong, thieu = [], [], 0, 0
    for item in ds_frame:
        idx = int(item["frame_idx"])
        gt_path = Path(gt_dir) / f"gt_{idx:06d}.png"
        pred_path = Path(item["pred_path"]) if item.get("pred_path") else None
        if pred_path is None or not pred_path.is_file():
            thieu += 1
            rows.append({"frame_idx": idx, "iou": None, "ly_do": "thiếu mask của model"})
            continue
        gt = doc_mask(gt_path)
        pred = doc_mask(pred_path)
        gia_tri = iou(pred, gt)
        if gia_tri is None:
            gt_rong += 1
            rows.append({"frame_idx": idx, "iou": None, "ly_do": "GT rỗng (không chấm)"})
            continue
        miou.append(gia_tri)
        rows.append({"frame_idx": idx, "iou": round(gia_tri, 4),
                     "dien_tich_gt": int(gt.sum()), "dien_tich_pred": int(pred.sum())})
    return {
        "mIoU": None if not miou else round(float(np.mean(miou)), 4),
        "mIoU_p05": None if len(miou) < 5 else round(float(np.percentile(miou, 5)), 4),
        "n_cham": len(miou),
        "so_frame_gt_rong": gt_rong,
        "so_frame_thieu_mask": thieu,
        "frames": rows,
    }


def kiem_index(index: dict, gt_dir: Path):
    """Trả danh sách LỖI của `index.json` (rỗng = hợp lệ). Dùng cho `--check`/CI."""
    loi = []
    if not index.get("clip"):
        loi.append("thiếu 'clip'")
    frames = index.get("frames") or []
    if not frames:
        loi.append("danh sách 'frames' rỗng")
    seen = set()
    for item in frames:
        idx = item.get("frame_idx")
        if not isinstance(idx, int) or idx < 0:
            loi.append(f"frame_idx không hợp lệ: {idx!r}")
            continue
        if idx in seen:
            loi.append(f"frame_idx trùng: {idx}")
        seen.add(idx)
        if not (Path(gt_dir) / f"gt_{idx:06d}.png").is_file():
            loi.append(f"thiếu file GT cho frame {idx}: gt_{idx:06d}.png")
    if not index.get("nguoi_gan"):
        loi.append("thiếu 'nguoi_gan' — GT không có người chịu trách nhiệm thì không dùng làm bằng chứng")
    if index.get("gt_do_model_goi_y"):
        loi.append("GT có mask do CHÍNH model gợi ý (gt_do_model_goi_y = true) — mIoU chấm trên đó "
                   "là đo chính model, không dùng để tuyên bố độ chính xác")
    return loi


# ── lệnh `label` ────────────────────────────────────────────────────────────────────────


def cat_frames(clip: Path, frames, out_dir: Path) -> int:
    """Cắt `frames` của `clip` thành `frame_<idx>.png` để gán tay. Trả số frame cắt được."""
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        raise SystemExit(f"[LOI] không mở được clip: {clip}")
    want = set(int(f) for f in frames)
    index, saved = 0, 0
    try:
        while want:
            ok, frame = cap.read()
            if not ok:
                break
            if index in want:
                cv2.imwrite(str(out_dir / f"frame_{index:06d}.png"), frame)
                want.discard(index)
                saved += 1
            index += 1
    finally:
        cap.release()
    if want:
        print(f"[LOI] clip chỉ có {index} frame, không cắt được frame {sorted(want)}")
    return saved


# ── `main` ──────────────────────────────────────────────────────────────────────────────


def _provenance():
    from scripts.measure_watchdog import _git_provenance

    return _git_provenance()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Chấm mIoU mask vs GT (thước đo 'bám đúng').")
    sub = parser.add_subparsers(dest="lenh", required=True)

    lbl = sub.add_parser("label", help="cắt frame ra PNG để gán tay + sinh index.json")
    lbl.add_argument("--clip", required=True)
    lbl.add_argument("--frames", required=True, help='danh sách frame_idx, vd "0,50,120"')
    lbl.add_argument("--ten", required=True, help="tên bộ GT (thư mục con của docs/gt)")
    lbl.add_argument("--nguoi-gan", default="", help="ai chịu trách nhiệm gán (bắt buộc để dùng làm bằng chứng)")
    lbl.add_argument("--gt-do-model-goi-y", action="store_true",
                     help="đánh dấu GT này có phần do model gợi ý (sẽ bị từ chối khi chấm điểm)")

    sco = sub.add_parser("score", help="chấm mIoU mask của model vs GT")
    sco.add_argument("--gt", default="", help="thư mục GT (mặc định docs/gt/<tên>); cần index.json")
    sco.add_argument("--pred-dir", required=True, help="thư mục mask model xuất (mask_<idx>.png)")
    sco.add_argument("--out", default="", help="artifact JSON (mặc định data/miou_<ngày>_metrics.json)")
    sco.add_argument("--check-index", action="store_true", help="chỉ kiểm GT hợp lệ rồi thoát")

    args = parser.parse_args(argv)

    if args.lenh == "label":
        frames = [int(v) for v in str(args.frames).replace(";", ",").split(",") if v.strip()]
        gt_dir = GT_DIR / args.ten
        saved = cat_frames(Path(args.clip), frames, gt_dir / "frames")
        index = {
            "clip": args.clip, "ten": args.ten, "frames": [
                {"frame_idx": f} for f in sorted(set(frames))],
            "nguoi_gan": args.nguoi_gan, "gt_do_model_goi_y": bool(args.gt_do_model_goi_y),
            "tao_luc": datetime.now().isoformat(timespec="seconds"),
            "huong_dan": ("Tô trắng vùng vật trên frame_<idx>.png rồi lưu thành gt_<idx>.png CÙNG "
                          "thư mục. Mask phải cùng kích thước frame gốc; nền đen, vật trắng."),
        }
        gt_dir.mkdir(parents=True, exist_ok=True)
        (gt_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
        print(f"[gt] đã cắt {saved}/{len(frames)} frame vào {gt_dir / 'frames'}")
        print(f"[gt] index: {gt_dir / 'index.json'} — nhớ điền --nguoi-gan trước khi chấm điểm")
        return 0

    gt_dir = Path(args.gt) if args.gt else None
    index_path = (gt_dir or Path()) / "index.json"
    if not index_path.is_file():
        print(f"[LOI] không thấy {index_path} — chạy `label` trước, hoặc trỏ --gt")
        return 2
    index = json.loads(index_path.read_text(encoding="utf-8"))
    loi = kiem_index(index, gt_dir)
    if args.check_index:
        for item in loi:
            print(f"[gt] LỖI: {item}")
        print("[gt] hợp lệ" if not loi else f"[gt] {len(loi)} lỗi")
        return 0 if not loi else 1

    pred_dir = Path(args.pred_dir)
    frames = []
    for item in index["frames"]:
        idx = int(item["frame_idx"])
        frames.append({"frame_idx": idx,
                       "pred_path": str(pred_dir / f"mask_{idx:06d}.png")})
    ket_qua = cham(frames, gt_dir)

    rev, dirty, dirty_code, git_loi = _provenance()
    payload = {
        # `git_*` TOP LEVEL theo quy ước artifact của repo (AGENTS §6).
        "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code, "git_loi": git_loi,
        "meta": {
            "do_luc": datetime.now().isoformat(timespec="seconds"),
            "lenh": " ".join(sys.argv),
            "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code, "git_loi": git_loi,
            "clip": index.get("clip"), "nguoi_gan": index.get("nguoi_gan"),
            "gt": str(gt_dir.relative_to(_REPO_ROOT)) if gt_dir.is_relative_to(_REPO_ROOT)
            else str(gt_dir),
            "pred_dir": str(pred_dir),
            "gt_do_model_goi_y": bool(index.get("gt_do_model_goi_y")),
            "dinh_nghia": "mIoU = trung bình IoU(mask_pred, mask_gt) trên các frame chấm được; "
                          "GT rỗng không chấm; model rỗng mà GT có vật = 0,0",
        },
        "ket_qua": ket_qua,
        "canh_bao_gt": loi,
    }
    out = Path(args.out) if args.out else (
        _REPO_ROOT / "data" / f"miou_{datetime.now():%Y-%m-%d}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    kq = ket_qua
    print(f"[miou] {out}")
    print(f"[miou] mIoU = {kq['mIoU']} trên {kq['n_cham']} frame"
          f" · GT rỗng: {kq['so_frame_gt_rong']} · thiếu mask: {kq['so_frame_thieu_mask']}")
    for ten_canh_bao in loi:
        print(f"[miou] CẢNH BÁO: {ten_canh_bao}")
    if kq["so_frame_thieu_mask"] > kq["n_cham"]:
        print(f"[miou] CẢNH BÁO: chỉ chấm được {kq['n_cham']} / "
              f"{kq['n_cham'] + kq['so_frame_thieu_mask']} frame có GT — "
              "CẤM nói 'mIoU trên cả clip' với con số này")
    if kq["mIoU"] is None:
        print("[miou] KHÔNG chấm được frame nào ⇒ mIoU = None (KHÔNG phải 0)")
        return 1
    if git_loi:
        print(f"[miou] CẢNH BÁO: không lấy được provenance ({git_loi})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
