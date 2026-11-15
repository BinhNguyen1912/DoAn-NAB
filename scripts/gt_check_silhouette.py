"""Kiểm bộ GT **silhouette** TRƯỚC khi chấm mIoU — bắt đúng 2 lỗi đã xảy ra ngày 15-11.

Vì sao cần: `score_miou --check-index` chỉ kiểm "file có giải mã được không", nên một bộ GT vẽ bằng
**công cụ hình chữ nhật (chỉ ra viền)** hoặc **copy-paste giữa các frame** vẫn được báo "hợp lệ" và
chấm ra số vô nghĩa (0,01–0,08) mà không ai biết. Script này kiểm HÌNH DẠNG + TÍNH LẶP:

- `lấp đầy khung bao` (area / diện tích bbox):
  - `< 0,45` ⇒ GT gần như **VIỀN RỖNG** (nét vẽ quanh vật) — không phải silhouette;
  - `> 0,95` ⇒ GT là **HÌNH CHỮ NHẬT ĐẶC** (dùng công cụ hình chữ nhật) — đó là `dang_gt = hop_bao`,
    không phải silhouette;
  - vật thật thường 0,5–0,85.
- `diện tích / diện tích frame` `> 0,35` ⇒ có thể đã tô cả nền (hoặc tô nhầm ảnh gốc).
- **trùng khít frame khác** (IoU > 0,98) ⇒ copy-paste GT giữa 2 frame (vật có di chuyển).
- toàn đen ⇒ GT rỗng (hợp lệ về kỹ thuật nhưng bị **không chấm** ⇒ nói ra để không tưởng là đã đo).

Chức năng: đọc `<gt_dir>/index.json` + `gt_<idx>.png`, in bảng từng frame, thoát mã 1 nếu có cảnh báo.
Input  : thư mục GT (mặc định `docs/gt/binh1_silhouette`).
Output : bảng ra stdout; KHÔNG ghi file nào.

Cách dùng:
    python scripts/gt_check_silhouette.py --gt docs/gt/binh1_silhouette
    python scripts/gt_check_silhouette.py --gt docs/gt/binh1_silhouette --quiet   # chỉ in cảnh báo
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Ngưỡng hình dạng — đặt theo ca thật 15-11: viền rỗng 9–10 px cho `lấp đầy` 0,15–0,20; hình chữ nhật
# đặc cho 1,0; chai xịt (thuôn, có vòi hẹp) rơi vào 0,5–0,75.
FILL_MIN = 0.45          # dưới ⇒ nghi viền rỗng
FILL_MAX = 0.95          # trên ⇒ nghi hình chữ nhật đặc
AREA_FRAME_MAX = 0.35    # diện tích GT / diện tích frame
DUP_IOU = 0.98           # hai frame gần trùng khít ⇒ copy-paste


def doc_mask(path: Path) -> np.ndarray:
    """Đọc mask nhị phân (giống `score_miou.doc_mask`); ném `ValueError` nếu không giải mã được."""
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"không đọc được ảnh mask: {path}")
    if img.ndim == 3:
        # Ảnh 4 kênh (RGBA — Chrome/canvas, một số editor xuất kèm alpha) thì PHẢI BỎ alpha: alpha
        # thường là 255 khắp nơi, lấy `max` cả 4 kênh sẽ thành "GT phủ kín khung" (đo 15-11 với PNG
        # xuất từ công cụ vẽ trong trình duyệt: 100 % khung, mIoU sụp còn ~0,1 mà không báo gì).
        img = img[:, :, :3].max(axis=2)
    return img > 0


def kiem_mot_frame(mask: np.ndarray) -> dict:
    """Số liệu hình dạng của MỘT mask + danh sách cảnh báo (hàm thuần).

    Không cảnh báo khi GT rỗng (hợp lệ: "vật đã rời khung") — chỉ ghi `gt_rong = True` để người đọc
    biết frame đó sẽ KHÔNG được chấm.
    """
    dien_tich = int(mask.sum())
    ra = {"dien_tich": dien_tich, "ti_le_khung": 0.0, "lap_day": None,
          "gt_rong": dien_tich == 0, "canh_bao": []}
    if dien_tich == 0:
        return ra
    ys, xs = np.nonzero(mask)
    w = int(xs.max() - xs.min() + 1)
    h = int(ys.max() - ys.min() + 1)
    ra["ti_le_khung"] = round(dien_tich / float(mask.size), 4)
    ra["bbox_xywh"] = [int(xs.min()), int(ys.min()), w, h]
    ra["lap_day"] = round(dien_tich / float(w * h), 3)
    if ra["lap_day"] < FILL_MIN:
        ra["canh_bao"].append(
            f"lấp đầy {ra['lap_day']:.2f} < {FILL_MIN} ⇒ nghi VIỀN RỖNG (chỉ vẽ nét quanh vật) — "
            "phải TÔ ĐẶC")
    elif ra["lap_day"] > FILL_MAX:
        ra["canh_bao"].append(
            f"lấp đầy {ra['lap_day']:.2f} > {FILL_MAX} ⇒ gần như HÌNH CHỮ NHẬT ĐẶC — nếu đúng ý thì "
            "khai `dang_gt = hop_bao`, KHÔNG dùng làm silhouette")
    if ra["ti_le_khung"] > AREA_FRAME_MAX:
        ra["canh_bao"].append(
            f"diện tích = {ra['ti_le_khung']:.0%} khung > {AREA_FRAME_MAX:.0%} ⇒ có thể đã tô cả nền")
    return ra


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """IoU hai mask cùng kích thước (0 nếu hợp rỗng)."""
    if a.shape != b.shape:
        return 0.0
    union = int((a | b).sum())
    return 0.0 if union == 0 else float((a & b).sum()) / union


def kiem_bo(gt_dir: Path) -> tuple[list[dict], list[str]]:
    """Kiểm cả bộ GT: trả `(bảng từng frame, lỗi chặn)`.

    Lỗi chặn = thiếu file / sai kích thước / index hỏng. Cảnh báo hình dạng & trùng lặp nằm trong bảng
    (mã thoát 1) vì người dùng cần XEM ẢNH rồi quyết định, không nên chặn cứng.
    """
    index_path = gt_dir / "index.json"
    if not index_path.is_file():
        return [], [f"không thấy {index_path}"]
    index = json.loads(index_path.read_text(encoding="utf-8"))
    frames = index.get("frames") or []
    dong, loi = [], []
    if not frames:
        return [], ["danh sách 'frames' rỗng"]
    hw = index.get("frame_hw")
    da_doc = {}
    for item in frames:
        idx = int(item["frame_idx"])
        path = gt_dir / f"gt_{idx:06d}.png"
        dong_nay = {"frame_idx": idx, "file": path.name}
        if not path.is_file():
            dong_nay["canh_bao"] = ["THIẾU FILE GT"]
            loi.append(f"thiếu {path.name}")
            dong.append(dong_nay)
            continue
        try:
            mask = doc_mask(path)
        except ValueError as exc:
            dong_nay["canh_bao"] = [f"KHÔNG ĐỌC ĐƯỢC: {exc}"]
            loi.append(str(exc))
            dong.append(dong_nay)
            continue
        if isinstance(hw, (list, tuple)) and len(hw) == 2 and tuple(mask.shape) != tuple(hw):
            dong_nay["canh_bao"] = ["SAI KÍCH THƯỚC %s (index: %s)" % (mask.shape, tuple(hw))]
            loi.append(f"{path.name} sai kích thước")
            dong.append(dong_nay)
            continue
        dong_nay.update(kiem_mot_frame(mask))
        da_doc[idx] = mask
        dong.append(dong_nay)
    # trùng khít giữa hai frame (copy-paste) — bỏ qua frame GT rỗng
    idx_da_doc = [i for i in da_doc if da_doc[i].any()]
    for i, a in enumerate(idx_da_doc):
        for b in idx_da_doc[i + 1:]:
            if da_doc[a].shape != da_doc[b].shape:
                continue
            if iou(da_doc[a], da_doc[b]) > DUP_IOU:
                for d in dong:
                    if d["frame_idx"] in (a, b):
                        d["canh_bao"].append(f"trùng khít frame {b if d['frame_idx'] == a else a}"
                                             f" (IoU > {DUP_IOU}) ⇒ copy-paste?")
    return dong, loi


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Kiểm bộ GT silhouette trước khi chấm mIoU.")
    parser.add_argument("--gt", default="docs/gt/binh1_silhouette")
    parser.add_argument("--quiet", action="store_true", help="chỉ in frame có cảnh báo")
    args = parser.parse_args(argv)

    gt_dir = Path(args.gt)
    if not gt_dir.is_absolute():
        gt_dir = _REPO_ROOT / gt_dir
    dong, loi = kiem_bo(gt_dir)
    if loi and not dong:
        for x in loi:
            print(f"[gt] LỖI: {x}")
        return 2

    co_canh_bao = 0
    print("| frame | diện tích | % khung | lấp đầy | ghi chú |")
    print("|---|---|---|---|---|")
    for d in dong:
        cb = d.get("canh_bao") or []
        if cb:
            co_canh_bao += 1
        if args.quiet and not cb:
            continue
        lap = "—" if d.get("lap_day") is None else f"{d['lap_day']:.2f}"
        print(f"| {d['frame_idx']} | {d.get('dien_tich', '—')} | "
              f"{d.get('ti_le_khung', 0):.1%} | {lap} | {'; '.join(cb) if cb else 'OK'} |")
    rong = [d["frame_idx"] for d in dong if d.get("gt_rong")]
    if rong:
        print(f"\n[gt] GT RỖNG ở frame {rong} ⇒ frame đó KHÔNG được chấm (nếu vật có trong khung thì "
              "đang thiếu GT)")
    for x in loi:
        print(f"[gt] LỖI (chặn chấm): {x}")
    if loi:
        return 2
    if co_canh_bao:
        print(f"\n[gt] {co_canh_bao}/{len(dong)} frame có cảnh báo ⇒ MỞ ẢNH kiểm rồi sửa "
              "(viền rỗng / hình chữ nhật / tô cả nền / copy-paste)")
        return 1
    print(f"\n[gt] {len(dong)} frame: không thấy dấu hiệu viền rỗng / hình chữ nhật / copy-paste")
    return 0


if __name__ == "__main__":
    sys.exit(main())
