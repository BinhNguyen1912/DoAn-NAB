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
  - `mIoU_p05 = None` khi `n_cham < 30` (ticket #23: ngưỡng công bố phân vị dùng chung với
    `status.json`). Cỡ mẫu luôn có mặt cạnh con số trong `mIoU_p05_n`: GT thật hiện chỉ 12 frame
    ⇒ p05 **không** được công bố, thay vì báo "p05" bằng frame xấu nhất.

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

# NGUỠNG CÔNG BỐ PHÂN VỊ — một hằng duy nhất cho cả repo (ticket #23). Trước đây file này tự đặt 5
# ⇒ artifact công bố `mIoU_p05` từ **5 frame**, tức "chính là giá trị xấu nhất", trong khi
# `status.json` từ chối công bố p05 dưới 30 mẫu. Dùng lại `phan_vi()` của `src/drift_samples.py`
# để không có cửa thứ hai.
from src.drift_samples import MIN_SAMPLES, phan_vi  # noqa: E402


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
        # Ảnh 4 kênh (RGBA — Chrome/canvas, một số editor xuất kèm alpha) thì PHẢI BỎ alpha: alpha
        # thường là 255 khắp nơi, lấy `max` cả 4 kênh sẽ thành "GT phủ kín khung" (đo 15-11 với PNG
        # xuất từ công cụ vẽ trong trình duyệt: 100 % khung, mIoU sụp còn ~0,1 mà không báo gì).
        img = img[:, :, :3].max(axis=2)
    return img > 0


def cham(ds_frame, gt_dir: Path) -> dict:
    """Chấm danh sách frame. `ds_frame`: [{"frame_idx": int}] từ `index.json`."""
    rows, miou, gt_rong, thieu, hong = [], [], 0, 0, 0
    for item in ds_frame:
        idx = int(item["frame_idx"])
        gt_path = Path(gt_dir) / f"gt_{idx:06d}.png"
        pred_path = Path(item["pred_path"]) if item.get("pred_path") else None
        if pred_path is None or not pred_path.is_file():
            thieu += 1
            rows.append({"frame_idx": idx, "iou": None, "ly_do": "thiếu mask của model"})
            continue
        try:
            gt = doc_mask(gt_path)
            pred = doc_mask(pred_path)
            gia_tri = iou(pred, gt)
        except (ValueError, OSError) as exc:
            # Một frame hỏng (mask lệch kích thước, PNG hỏng) KHÔNG được làm chết cả lần chấm —
            # nhưng cũng KHÔNG được im lặng: đếm riêng và nêu lý do từng frame.
            hong += 1
            rows.append({"frame_idx": idx, "iou": None, "ly_do": f"mask hỏng: {exc}"})
            continue
        if gia_tri is None:
            gt_rong += 1
            rows.append({"frame_idx": idx, "iou": None, "ly_do": "GT rỗng (không chấm)"})
            continue
        miou.append(gia_tri)
        # Phần mask NẰM NGOÀI GT ("tràn"): với GT là HỘP BAO, `mIoU` bị chặn trên ~0,75-0,85 nên
        # không nói được model có phủ quá tay không; `tran` thì đo đúng cái đó (thấp = tốt) và KHÔNG
        # bị thổi phồng bởi GT hộp. Với GT silhouette nó là chỉ báo over-segmentation chuẩn.
        tran = None
        if int(pred.sum()):
            tran = round(1.0 - float((pred & gt).sum()) / float(pred.sum()), 4)
        rows.append({"frame_idx": idx, "iou": round(gia_tri, 4),
                     "dien_tich_gt": int(gt.sum()), "dien_tich_pred": int(pred.sum()),
                     "mask_ngoai_gt": tran})
    tong = len(ds_frame)
    tran_vals = [r["mask_ngoai_gt"] for r in rows if r.get("mask_ngoai_gt") is not None]
    return {
        "mIoU": None if not miou else round(float(np.mean(miou)), 4),
        # Phân vị 5 % của IoU TỪNG FRAME = "những frame tệ nhất tệ tới đâu". Cỡ mẫu là `n_cham`
        # (`mIoU_p05_n`), và dưới `MIN_SAMPLES` (30 — dùng chung với `status.json`) thì p05 ≈ min
        # ⇒ trả `None` thay vì công bố một con số trông đáng tin hơn thực tế (ticket #23).
        "mIoU_p05": phan_vi(miou),
        "mIoU_p05_n": len(miou),
        "mIoU_p05_nguong": MIN_SAMPLES,
        # Tỉ lệ mask nằm NGOÀI GT: trung bình + frame tệ nhất (kèm `frame_idx` để truy lại ảnh).
        "mask_ngoai_gt_mean": None if not tran_vals else round(float(np.mean(tran_vals)), 4),
        # `_n`: mẫu số của trung bình "tràn" KHÁC `n_cham` khi có frame model trả mask RỖNG (không có gì
        # để tràn). Thiếu `_n` thì con số lạc quan một cách im lặng (luật `*_n` của AGENTS §6).
        "mask_ngoai_gt_n": len(tran_vals),
        "mask_ngoai_gt_max": None if not tran_vals else round(float(max(tran_vals)), 4),
        # QUY ƯỚC KHI HOÀ (ghim bằng test): nhiều frame cùng "tràn" lớn nhất ⇒ lấy frame_idx NHỎ NHẤT.
        # `max()` trơn lấy phần tử ĐẦU theo thứ tự `rows`, mà `rows` đi theo thứ tự `index.frames` ⇒
        # cùng hai frame hoà có thể ra frame khác nhau chỉ vì index xếp ngược. Tie-break tường minh để
        # `mask_ngoai_gt_max_frame` tái lập được dù index xếp thế nào.
        "mask_ngoai_gt_max_frame": None if not tran_vals else max(
            (r for r in rows if r.get("mask_ngoai_gt") is not None),
            key=lambda r: (r["mask_ngoai_gt"], -r["frame_idx"]))["frame_idx"],
        "n_cham": len(miou),
        "so_frame_gt_rong": gt_rong,
        "so_frame_thieu_mask": thieu,
        "so_frame_mask_hong": hong,
        # Coverage vào artifact, KHÔNG chỉ in ra màn hình: 5/10 frame thiếu mask từng được in mIoU mà
        # không cảnh báo, và người đọc artifact sau không biết mẫu nhỏ đến đâu.
        "so_frame_tong": tong,
        "coverage": None if not tong else round(len(miou) / tong, 4),
        "frames": rows,
    }


def _hop_bao_hop_le(hop):
    """`[x, y, w, h]` số nguyên, w/h > 0 ⇒ tuple; sai định dạng ⇒ `None`.

    `bool` bị loại (`True == 1`) để `[true, 0, 5, 5]` không lọt qua thành hộp hợp lệ.
    """
    if not isinstance(hop, (list, tuple)) or len(hop) != 4:
        return None
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in hop):
        return None
    x, y, w, h = (int(v) for v in hop)
    if min(x, y) < 0 or w <= 0 or h <= 0:
        return None
    return x, y, w, h


def doi_chieu_hop_bao(mask: np.ndarray, hop, idx: int) -> list[str]:
    """Đối chiếu mask GT với `hop_bao_xywh` khai trong index ⇒ danh sách lỗi CHẶN chấm.

    Vì sao phải kiểm: trước đây `kiem_index` chỉ biết *có* file GT và đúng kích thước khung, nên một
    file GT **lẫn frame khác** (hoặc hộp ghi sai) vẫn được "chứng nhận hợp lệ" và mIoU thành con số
    vô nghĩa — đúng lớp lỗi "ghép GT với mask của frame khác" đã xảy ra (P0 14-11). Ba phép kiểm:
    hộp nằm trong khung · số pixel = `w*h` · bao thực của mask đúng `(x, y, w, h)`.
    """
    box = _hop_bao_hop_le(hop)
    if box is None:
        return [f"'hop_bao_xywh' không hợp lệ ở frame {idx}: {hop!r} (cần [x, y, w, h] số nguyên, "
                "x/y >= 0, w/h > 0)"]
    x, y, w, h = box
    cao, rong = mask.shape[:2]
    if x + w > rong or y + h > cao:
        return [f"hộp frame {idx} vượt biên khung: {w}×{h} tại ({x},{y}) trên khung {rong}×{cao} — "
                "ghi hộp ĐÃ CẮT theo khung (hoặc sửa hộp) rồi chạy lại"]
    tong = int(mask.sum())
    if tong == 0:
        # Ca THẬT (`binh1` cất chai từ frame ~115): vật đã rời khung thì GT rỗng là ĐÚNG. Khai
        # `hop_bao_xywh` cho frame rỗng là mâu thuẫn ⇒ chặn, nhưng phải nói đúng cách sửa, đừng để
        # người chạy đọc thành "GT lẫn frame khác" rồi đi sửa sai chỗ.
        return [f"GT frame {idx} rỗng (toàn đen) nhưng vẫn khai hộp {w}×{h} — nếu vật đã RỜI KHUNG "
                "thì BỎ 'hop_bao_xywh' ở frame đó (GT rỗng không được chấm, đếm riêng)"]
    if tong != w * h:
        return [f"GT frame {idx} có {tong} pixel nhưng hộp khai {w}×{h} = {w * h} pixel — GT lẫn "
                "frame khác hoặc hộp ghi sai"]
    hang = np.flatnonzero(mask.any(axis=1))
    cot = np.flatnonzero(mask.any(axis=0))
    if (int(hang[0]), int(hang[-1]) + 1) != (y, y + h) \
            or (int(cot[0]), int(cot[-1]) + 1) != (x, x + w):
        return [f"GT frame {idx} không phải hình chữ nhật {w}×{h} tại ({x},{y}): bao thực "
                f"x {int(cot[0])}..{int(cot[-1])}, y {int(hang[0])}..{int(hang[-1])}"]
    return []


def _cung_nguon(a, b) -> bool:
    """Hai chuỗi nguồn có trỏ cùng một file không (so đường dẫn THẬT khi file tồn tại)."""
    if str(a) == str(b):
        return True
    try:
        pa, pb = Path(str(a)), Path(str(b))
        return (pa.resolve() if pa.exists() else pa) == (pb.resolve() if pb.exists() else pb)
    except (OSError, ValueError):
        return False


def _so_nguyen(value) -> int | None:
    """`37`, `37.0`, `"37"` ⇒ 37; còn lại ⇒ `None`.

    Bản trước chỉ nhận `isinstance(x, int)` ⇒ bỏ qua im lặng `37.0`/`"37"` (manifest viết tay hoặc do
    tool cũ sinh) — fail-open đúng ở khoá dùng để CHẶN (P3 review 17-11). Cùng quy ước với
    `frames_yeu_cau` (chấp nhận float nguyên, từ chối 2.7).
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else None


# Nhãn loại lỗi chặn, để `--cho-phep-offset` hạ cấp ĐÚNG nhóm (dùng nhãn, không so chuỗi con — bản
# trước so `"frame_goc_cua_phien" not in c` nên hạ cấp luôn ca "khoá có mà KHÔNG đọc được", tức mở khoá
# đúng ca không biết offset là bao nhiêu; P3 vòng review 3).
_CHAN_OFFSET = "[offset] "
_CHAN_OFFSET_KHONG_DOC = "[offset-khong-doc] "


def kiem_khop_manifest(index: dict, manifest, pred_dir=None) -> tuple[list[str], list[str]]:
    """Đối chiếu bộ GT với `manifest.json` của thư mục mask ⇒ cảnh báo MỀM (không chặn chấm).

    mIoU chỉ có nghĩa khi GT và mask là **cùng clip, cùng frame**. `manifest.json` (do
    `live_worker --dump-mask-frames` sinh) biết nguồn và danh sách frame đã xuất, nên đây là chỗ duy
    nhất kiểm được "ghép đúng" mà không tốn gì. Không có manifest ⇒ không cảnh báo (không có gì để
    đối chiếu, đừng đẻ cảnh báo rỗng).
    """
    if not isinstance(manifest, dict):
        return [], []
    chan, mem = [], []
    nguon, clip = manifest.get("nguon"), index.get("clip")
    if nguon and clip and not _cung_nguon(clip, nguon):
        mem.append(f"clip của GT ({clip}) KHÁC nguồn của mask ({nguon}) — mIoU đang ghép hai clip "
                   "khác nhau (không xác minh được nội dung khi file vắng mặt; ghi đường dẫn "
                   "tương đối từ gốc repo để so được)")
    # Mask bị GHI ĐÈ (tên file trùng giữa hai lần chọn ô / hai phiên) ⇒ file đang chấm có thể là của
    # lần chọn KHÁC. Worker đã in cảnh báo lúc ghi nhưng stdout đó không đi theo artifact; ticket #26
    # nên `manifest.json` khai `so_file_ghi_de` và chỗ CHẤM phải đọc nó (P2 review 17-11).
    # Chọn ô GIỮA phiên: tên file mask đi theo chỉ số frame của PHIÊN, không phải của clip ⇒ ghép GT
    # theo số frame là lệch đúng `frame_goc_cua_phien` (ticket #36). Thiếu khoá = manifest của bản cũ
    # (mọi lần dump cũ đều bắt đầu từ frame 0 qua `--bbox`) ⇒ không cảnh báo.
    co_goc = "frame_goc_cua_phien" in manifest
    goc = _so_nguyen(manifest.get("frame_goc_cua_phien"))
    if co_goc and goc is None:
        # Khoá CÓ MẶT mà không đọc được (`2.7`, `"abc"`, `""`, `true`, `[37]`) ⇒ CHẶN, không bỏ qua:
        # ở `frames_yeu_cau` "không đọc được" nghĩa là *cảnh báo*, nhưng ở đây nó nghĩa là *bỏ qua
        # đúng khoá dùng để chặn* = fail-open (P2 vòng review 2).
        chan.append(_CHAN_OFFSET_KHONG_DOC +
                    f"`frame_goc_cua_phien` có nhưng KHÔNG đọc được ({manifest.get('frame_goc_cua_phien')!r}) "
                    "⇒ không biết mask có lệch frame hay không; sửa manifest hoặc chạy lại phiên với ô "
                    "chọn có sẵn từ frame đầu (ticket #36)")
    if goc:
        # CHẶN, không chỉ cảnh báo: khác `so_file_ghi_de` ("có thể" trộn), ở đây mask CHẮC CHẮN lệch
        # frame khi phiên đã bỏ frame lúc chờ chọn ô — và không có cờ nào để chấm bù (số phải mod độ
        # dài clip khi nguồn quay vòng). Công bố mIoU trong ca này là số sai im lặng (ticket #36, P2
        # review 17-11).
        chan.append(_CHAN_OFFSET + f"`frame_goc_cua_phien` = {goc} ⇒ phiên đã bỏ {goc} frame lúc chờ chọn "
                   "ô, nên `mask_NNNNNN.png` KHÔNG phải frame NNNNNN của clip ⇒ mIoU sẽ ghép lệch "
                   "frame (ticket #36). Chạy lại phiên với ô chọn có sẵn từ frame đầu")
    # `frames_da_ghi` khác `frames_yeu_cau`: hai lần chạy khác bbox vào CÙNG thư mục dump thì file của
    # lần trước vẫn nằm trên đĩa, mà `frames_yeu_cau` (khoá của lần chạy CUỐI) vẫn khớp GT ⇒ phải đối
    # chiếu với danh sách ĐÃ GHI THẬT (P2 vòng review 2). Chỉ kiểm khi khoá có mặt (manifest bản cũ).
    da_ghi = manifest.get("frames_da_ghi")
    if isinstance(da_ghi, str):
        # Manifest viết tay có thể ghi `"0,6,12"` — bỏ qua im lặng là fail-open trên ĐÚNG cổng này.
        da_ghi = [x for x in da_ghi.replace(";", ",").split(",") if x.strip()]
    if isinstance(da_ghi, (list, tuple)) and "frames_da_ghi" in manifest:
        tap_ghi = {v for f in da_ghi if (v := _so_nguyen(f)) is not None}
        # CHỈ xét frame ĐỊNH CHẤM (= GT ∩ `frames_yeu_cau`), không phải mọi frame có GT: bộ GT tổng
        # hợp/DAVIS khai GT cho CẢ clip trong khi ta chỉ chấm vài frame — đòi `frames_da_ghi` phủ hết
        # GT sẽ CHẶN OAN mọi lần chấm có `coverage < 1` (bắt được khi diễn tập lại demo synthetic).
        dinh_cham = None
        yeu_cau_tap = manifest.get("frames_yeu_cau")
        if isinstance(yeu_cau_tap, (list, tuple)) and yeu_cau_tap:
            dinh_cham = {v for f in yeu_cau_tap if (v := _so_nguyen(f)) is not None}
        elif isinstance(yeu_cau_tap, str):
            dinh_cham = {v for p in yeu_cau_tap.replace(";", ",").split(",")
                         if (v := _so_nguyen(p)) is not None}
        lac = []
        for item in index.get("frames") or []:
            idx = item.get("frame_idx") if isinstance(item, dict) else None
            if not isinstance(idx, int) or isinstance(idx, bool):
                continue
            if dinh_cham is not None and idx not in dinh_cham:
                continue
            if idx in tap_ghi:
                continue
            # CHỈ là "mask của PHIÊN KHÁC" khi FILE CÓ THẬT trên đĩa (P2 vòng review 3). Phiên bị cắt
            # trước frame yêu cầu (Ctrl+C, `--stop-after-frames` nhỏ, `imwrite` fail, `mask is None`)
            # để lại frame KHÔNG có file ⇒ đó là "thiếu mask" theo hợp đồng (chấm báo
            # `so_frame_thieu_mask` + `coverage`, exit 1), không phải lỗi chặn.
            if pred_dir is not None and not (Path(pred_dir) / f"mask_{idx:06d}.png").exists():
                continue
            lac.append(idx)
        if lac:
            chan.append(f"GT cần frame {sorted(lac)} nhưng `frames_da_ghi` của phiên này chỉ có "
                        f"{sorted(tap_ghi)} ⇒ các `mask_*.png` đó CÒN LẠI trên đĩa từ PHIÊN/lần chọn "
                        "KHÁC (hai lần dump vào cùng thư mục); dùng thư mục dump riêng cho mỗi phiên")
    ghi_de = manifest.get("so_file_ghi_de")
    if isinstance(ghi_de, int) and not isinstance(ghi_de, bool) and ghi_de > 0:
        mem.append(f"mask bị GHI ĐÈ {ghi_de} lần trong lúc ghi (`so_file_ghi_de`) — có thể trộn mask "
                   "của hai lần chọn ô/phiên; dùng `--dump-mask-dir` riêng cho mỗi lần chọn")
    yeu_cau = manifest.get("frames_yeu_cau")
    if isinstance(yeu_cau, str):
        # Manifest viết tay có thể ghi `"2,12,22"`; bỏ qua im lặng là fail-open (cổng danh nghĩa).
        yeu_cau = [p for p in yeu_cau.replace(";", ",").split(",") if p.strip()]
    if isinstance(yeu_cau, (list, tuple)) and yeu_cau:
        tap = set()
        for f in yeu_cau:
            try:
                if isinstance(f, bool) or not isinstance(f, (int, str, float)):
                    raise ValueError(f)
                # Float chỉ nhận khi là số nguyên (2.7 ⇒ 2 im lặng là sai); `Infinity` ⇒ OverflowError.
                if isinstance(f, float) and not f.is_integer():
                    raise ValueError(f)
                tap.add(int(f))
            except (TypeError, ValueError, OverflowError):
                mem.append(f"`frames_yeu_cau` của mask có phần tử không đọc được ({f!r}) ⇒ chỉ đối "
                           "chiếu được phần đọc được")
        if not tap:
            return chan, mem
        thua = []
        for item in index.get("frames") or []:
            idx = item.get("frame_idx") if isinstance(item, dict) else None
            if isinstance(idx, int) and not isinstance(idx, bool) and idx not in tap:
                thua.append(idx)
        if thua:
            mem.append(f"GT có frame {sorted(thua)} KHÔNG nằm trong `frames_yeu_cau` của mask "
                       f"({sorted(tap)}) — đúng lớp lỗi 'ghép GT với mask của frame khác'")
    return chan, mem


def _doc_manifest(pred_dir: Path):
    """Đọc `manifest.json` cạnh các file mask ⇒ `(manifest | None, lỗi | None)`.

    Phải TÁCH hai ca: `(None, None)` = **không có file** (bình thường, không có gì để đối chiếu) khác
    `(None, "…")` = **có file nhưng HỎNG/không phải JSON object**. Bản trước gộp cả hai thành `None`
    ⇒ manifest sai định dạng được đọc thành "không có manifest" và cảnh báo mất nghĩa (P3 review 16-11).
    """
    path = Path(pred_dir) / "manifest.json"
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{path.name} không đọc được ({exc})"
    if not isinstance(data, dict):
        return None, f"{path.name} phải là object JSON (đang là {type(data).__name__})"
    return data, None


def kiem_index(index: dict, gt_dir: Path):
    """Trả `(chan, mem)`: lỗi CHẶN chấm điểm và cảnh báo MỀM.

    Vì sao phải tách: bản trước **chỉ in cảnh báo rồi vẫn chấm** — một GT do chính model gợi ý vẫn ra
    artifact mIoU và mã thoát 0, tức "chốt chặn danh nghĩa" đúng như tài liệu nói nó chặn (P1, review
    độc lập 14-11). Lỗi chặn ⇒ exit 2, KHÔNG ghi artifact; cảnh báo mềm ⇒ vẫn chấm nhưng exit 1.
    """
    chan, mem = [], []
    # `dang_gt` = HÌNH DẠNG của GT: `silhouette` (mask vật) | `hop_bao` (hộp chữ nhật bao vật).
    # Đọc TRƯỚC vòng lặp vì cổng "hộp bao ↔ mask" bên dưới cần biết dạng GT.
    dang = index.get("dang_gt")
    thieu_hop = 0
    # Hộp đã thấy (frame_idx → (x, y, w, h)): hai frame cùng MỘT hộp ⇒ nghi copy-paste GT (bản hộp bao
    # của `DUP_IOU` trong `scripts/gt_check_silhouette.py`). Cảnh báo MỀM: vật đứng yên vẫn có thể
    # trùng hộp thật, nên không chặn — nhưng một bộ GT 12 frame mà nhiều hộp trùng y hệt thì phải soi lại.
    hop_da_thay = {}
    if not index.get("clip"):
        mem.append("thiếu 'clip'")
    frames = index.get("frames") or []
    if not frames:
        chan.append("danh sách 'frames' rỗng — không có gì để chấm")
    seen = set()
    for item in frames:
        idx = item.get("frame_idx")
        if not isinstance(idx, int) or idx < 0:
            chan.append(f"frame_idx không hợp lệ: {idx!r}")
            continue
        if idx in seen:
            chan.append(f"frame_idx trùng: {idx}")
        seen.add(idx)
        gt_path = Path(gt_dir) / f"gt_{idx:06d}.png"
        if not gt_path.is_file():
            chan.append(f"thiếu file GT cho frame {idx}: gt_{idx:06d}.png")
            continue
        # `is_file()` KHÔNG đủ: test cũ của chính repo coi một file 1 byte là "hợp lệ", trong khi
        # `score` sẽ chết vì không giải mã được (review hẹp 14-11, P2 — "chứng nhận" một bộ GT mà
        # khâu chấm không dùng được). Giải mã + kiểm cỡ thật.
        try:
            mask = doc_mask(gt_path)
        except ValueError as exc:
            chan.append(f"GT không đọc được ở frame {idx}: {exc}")
            continue
        hw = index.get("frame_hw")
        if isinstance(hw, (list, tuple)) and len(hw) == 2 and tuple(mask.shape) != tuple(hw):
            chan.append(f"GT frame {idx} sai kích thước {mask.shape} (index ghi frame_hw = {tuple(hw)})")
        if not mask.any():
            mem.append(f"GT frame {idx} toàn đen — `score` sẽ không chấm được frame này (đếm là 'GT rỗng')")
        # GT dạng HỘP BAO: nếu index khai `hop_bao_xywh` thì mask GT phải ĐÚNG là hộp đó.
        hop = item.get("hop_bao_xywh")
        if hop is not None:
            if dang == "hop_bao":
                chan.extend(doi_chieu_hop_bao(mask, hop, idx))
                box = _hop_bao_hop_le(hop)
                if box is not None and mask.any():
                    hop_da_thay.setdefault(box, []).append(idx)
        elif dang == "hop_bao":
            # Frame GT **rỗng** là ca hợp lệ khi vật đã rời khung, và cách sửa đúng là BỎ hộp ⇒ không
            # được đếm vào cảnh báo "thiếu hop_bao_xywh" (hai câu khuyên ngược nhau, P3 review 16-11).
            if mask.any():
                thieu_hop += 1
    if not index.get("nguoi_gan"):
        mem.append("thiếu 'nguoi_gan' — GT không có người chịu trách nhiệm thì không dùng làm bằng chứng")
    if index.get("gt_do_model_goi_y"):
        chan.append("GT có mask do CHÍNH model gợi ý (gt_do_model_goi_y = true) — mIoU chấm trên đó "
                    "là đo chính model, không dùng để tuyên bố độ chính xác")
    if thieu_hop:
        mem.append(f"{thieu_hop} frame khai GT là hộp bao nhưng KHÔNG có 'hop_bao_xywh' ⇒ không đối "
                   "chiếu được mask GT với hộp (thêm hộp vào index để cổng kiểm chạy)")
    for box, ds_frame in hop_da_thay.items():
        if len(ds_frame) > 1:
            mem.append(f"frame {sorted(ds_frame)} khai CÙNG một hộp {box[2]}×{box[3]} tại "
                       f"({box[0]},{box[1]}) ⇒ kiểm xem có copy-paste GT giữa các frame không "
                       "(vật di chuyển thì hộp phải đổi)")
    # `dang_gt` = HÌNH DẠNG của GT: `silhouette` (mask vật) | `hop_bao` (hộp chữ nhật bao vật).
    # Không có khai báo thì chỉ cảnh báo MỀM (GT cũ chưa có khoá này), nhưng artifact LUÔN ghi giá trị
    # (None = không khai báo) để người đọc biết con số đang đo cái gì.
    if dang not in (None, "silhouette", "hop_bao"):
        mem.append(f"'dang_gt' lạ: {dang!r} (chỉ nhận 'silhouette' | 'hop_bao')")
    elif dang == "hop_bao":
        mem.append("GT là HỘP BAO chữ nhật (không phải silhouette) ⇒ con số là IoU(mask, hộp), "
                   "KHÔNG phải mIoU phân đoạn; chặn trên ~0,75-0,85 do hộp lớn hơn vật")
    elif dang is None:
        mem.append("GT không khai báo 'dang_gt' — không biết đây là silhouette hay hộp bao")
    return chan, mem


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
    # DẠNG GT phải do NGƯỜI KHAI, không hard-code: bản trước ghi cứng `silhouette` ngay khi sinh frame
    # ⇒ nếu người vẽ HỘP (ca thật 15-11) thì index khai sai và chốt chặn "GT hộp bao" KHÔNG BAO GIỜ in ra.
    lbl.add_argument("--dang-gt", choices=["silhouette", "hop_bao"], default=None,
                     help="silhouette = mask vật (tô tay) | hop_bao = hộp chữ nhật bao vật")
    lbl.add_argument("--phuong-phap-gt", default="",
                     help="mô tả cách làm GT (vd 'người tô tay trên frame gốc') — vào meta artifact")
    lbl.add_argument("--gt-do-model-goi-y", action="store_true",
                     help="đánh dấu GT này có phần do model gợi ý (sẽ bị từ chối khi chấm điểm)")

    sco = sub.add_parser("score", help="chấm mIoU mask của model vs GT")
    sco.add_argument("--gt", default="", help="thư mục GT (mặc định docs/gt/<tên>); cần index.json")
    sco.add_argument("--pred-dir", required=True, help="thư mục mask model xuất (mask_<idx>.png)")
    sco.add_argument("--out", default="", help="artifact JSON (mặc định data/miou_<ngày>_metrics.json)")
    sco.add_argument("--check-index", action="store_true", help="chỉ kiểm GT hợp lệ rồi thoát")
    sco.add_argument("--cho-phep-offset", action="store_true",
                     help="vẫn chấm dù manifest khai `frame_goc_cua_phien` > 0 (chỉ khi bạn ĐÃ tự cắt "
                          "GT lệch đúng offset; nếu không thì mIoU là số sai)")

    args = parser.parse_args(argv)

    if args.lenh == "label":
        frames = [int(v) for v in str(args.frames).replace(";", ",").split(",") if v.strip()]
        gt_dir = GT_DIR / args.ten
        saved = cat_frames(Path(args.clip), frames, gt_dir / "frames")
        index = {
            "clip": args.clip, "ten": args.ten, "frames": [
                {"frame_idx": f} for f in sorted(set(frames))],
            "nguoi_gan": args.nguoi_gan, "gt_do_model_goi_y": bool(args.gt_do_model_goi_y),
            # `label` sinh frame TRƯỚC khi người tô ⇒ KHÔNG được tự khai dạng GT (`--dang-gt` mới khai).
            # Không khai thì `kiem_index` cảnh báo "không biết dạng GT" ⇒ exit 1, không công bố im lặng.
            "dang_gt": args.dang_gt,
            "phuong_phap_gt": args.phuong_phap_gt or None,
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

    # `--gt` mặc định "" ⇒ `gt_dir = None` ⇒ trước đây `Path(None)` ném `TypeError` (và tìm
    # `./index.json` theo CWD) — review hẹp 14-11, P3. Nói thẳng và dừng.
    if not args.gt:
        print("[miou] thiếu --gt <thư mục GT> (phải có index.json bên trong; xem "
              "`./run miou gt`)")
        return 2
    gt_dir = Path(args.gt)
    index_path = (gt_dir or Path()) / "index.json"
    if not index_path.is_file():
        print(f"[LOI] không thấy {index_path} — chạy `label` trước, hoặc trỏ --gt")
        return 2
    index = json.loads(index_path.read_text(encoding="utf-8"))
    pred_dir = Path(args.pred_dir)
    # Manifest của thư mục mask: đối chiếu "GT có đúng clip/frame của mask không" (cảnh báo MỀM).
    mask_manifest, loi_manifest = _doc_manifest(pred_dir)
    chan, mem = kiem_index(index, gt_dir)
    chan_m, mem_m = kiem_khop_manifest(index, mask_manifest, pred_dir)
    chan += chan_m
    mem += mem_m
    # `--cho-phep-offset`: người chấm tự nhận trách nhiệm về **đúng** lớp "offset" (đã tự cắt GT lệch
    # theo `frame_goc_cua_phien`) ⇒ hạ cấp CHỈ nhóm đó. Mask còn lại từ phiên khác (`frames_da_ghi`)
    # KHÔNG hạ cấp được: không cờ nào biến nó thành đúng.
    if args.cho_phep_offset:
        # CHỈ hạ cấp nhóm `[offset]` (= offset > 0, người chấm đã tự cắt GT lệch). Nhóm
        # `[offset-khong-doc]` GIỮ NGUYÊN: không ai biết offset là bao nhiêu thì không thể cắt bù.
        mem += [f"cảnh báo (đã --cho-phep-offset): {c[len(_CHAN_OFFSET):]}"
                for c in chan_m if c.startswith(_CHAN_OFFSET)]
        chan = [c for c in chan if not c.startswith(_CHAN_OFFSET)]
    if loi_manifest:
        # "Có manifest nhưng HỎNG" KHÁC "không có manifest": ca sau là bình thường, ca trước nghĩa là
        # không ai biết mask sinh từ clip/frame nào ⇒ phải nói ra (P3 review 16-11).
        mem.append(f"manifest của mask HỎNG ({loi_manifest}) ⇒ KHÔNG đối chiếu được clip/frame")
    if args.check_index:
        # In DẠNG GT + NGUỒN GT ngay trên đầu: `--check-index` là chỗ người chạy hay xem nhất, mà
        # "hợp lệ" không có nghĩa là "con số sắp in ra là mIoU phân đoạn" (ticket #30).
        dang = index.get("dang_gt")
        print(f"[gt] dạng GT: {dang or 'KHÔNG KHAI'}"
              + (" ⇒ con số sẽ là IoU(mask, HỘP BAO), KHÔNG phải mIoU phân đoạn"
                 if dang == "hop_bao" else ""))
        print(f"[gt] nguồn GT: {index.get('nguon_gt') or index.get('phuong_phap_gt') or 'KHÔNG KHAI'}")
        if loi_manifest:
            duoi = f" · manifest của mask HỎNG ({loi_manifest}) ⇒ chưa đối chiếu được clip/frame"
        elif isinstance(mask_manifest, dict):
            nguon_mask = mask_manifest.get("nguon") or "KHÔNG KHAI"
            duoi = f" · mask từ {nguon_mask}"
        else:
            duoi = " · KHÔNG có manifest của mask ⇒ chưa đối chiếu được clip/frame"
        print(f"[gt] clip: {index.get('clip')} · {len(index.get('frames') or [])} frame{duoi}")
        for item in chan:
            print(f"[gt] LỖI (chặn chấm): {item}")
        for item in mem:
            print(f"[gt] cảnh báo: {item}")
        print("[gt] hợp lệ" if not (chan or mem) else f"[gt] {len(chan)} lỗi chặn, {len(mem)} cảnh báo")
        return 0 if not (chan or mem) else 1
    for item in chan:
        print(f"[miou] TỪ CHỐI CHẤM: {item}")
    if chan:
        print("[miou] không ghi artifact — sửa GT rồi chạy lại "
              "(xem docs/thuoc-do-bam-dung.md)")
        return 2

    frames = []
    for item in index["frames"]:
        idx = int(item["frame_idx"])
        frames.append({"frame_idx": idx,
                       "pred_path": str(pred_dir / f"mask_{idx:06d}.png")})
    ket_qua = cham(frames, gt_dir)
    # Echo DẠNG GT vào CHÍNH khối `ket_qua` (không chỉ `meta`) và đặt TRƯỚC `mIoU` trong file JSON:
    # người `grep mIoU` rồi copy sẽ thấy `gt_dang` + `mIoU_dinh_nghia` NGAY CẠNH con số, không phải mở
    # `meta` mới biết 0,6464 là IoU với hộp bao chứ không phải mIoU phân đoạn (ticket #30).
    # `dang_gt` KHÔNG KHAI cũng phải có câu định nghĩa: bỏ ra thì artifact `null` trông y hệt một bộ
    # silhouette hợp lệ, và con số lại được đọc thành "mIoU phân đoạn" (P2 review 16-11).
    dang_gt = index.get("dang_gt")
    if dang_gt == "silhouette":
        dinh_nghia_so = None
    elif dang_gt is None:
        dinh_nghia_so = ("dạng GT KHÔNG KHAI — KHÔNG được gọi là mIoU phân đoạn cho đến khi khai "
                         "`dang_gt` trong index.json")
    else:
        dinh_nghia_so = (f"IoU(mask, GT dạng '{dang_gt}') — KHÔNG phải mIoU phân đoạn silhouette")
    dau = {"gt_dang": dang_gt}
    if dinh_nghia_so:
        dau["mIoU_dinh_nghia"] = dinh_nghia_so
    ket_qua = {**dau, **ket_qua}

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
            # Hình dạng GT + cách làm ra GT: KHÔNG có hai khoá này thì người đọc artifact không biết
            # "0,65" là mIoU phân đoạn hay IoU với hộp bao (bẫy "số đúng nhưng gắn sai nghĩa").
            "dang_gt": index.get("dang_gt"),
            "nguon_gt": index.get("nguon_gt"),
            "phuong_phap_gt": index.get("phuong_phap_gt"),
            # Manifest của thư mục mask (image_size/vos_every/bbox/source) ⇒ artifact tự trả lời được
            # "mask này sinh trong điều kiện nào" (P0/P2 review hẹp 14-11).
            "mask_manifest": mask_manifest,
            "mask_manifest_loi": loi_manifest,
            "dinh_nghia": "mIoU = trung bình IoU(mask_pred, mask_gt) trên các frame chấm được; "
                          "GT rỗng không chấm; model rỗng mà GT có vật = 0,0; "
                          "`mask_ngoai_gt` = phần mask nằm NGOÀI GT (thấp = không tràn ra ngoài; "
                          "một phía, không nói mask phủ đủ); nếu `dang_gt = hop_bao` thì `mIoU` là "
                          "IoU(mask, HỘP BAO), KHÔNG phải mIoU phân đoạn",
        },
        "ket_qua": ket_qua,
        "canh_bao_gt": mem, "loi_chan": chan,
    }
    out = Path(args.out) if args.out else (
        _REPO_ROOT / "data" / f"miou_{datetime.now():%Y-%m-%d}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    kq = ket_qua
    print(f"[miou] {out}")
    print(f"[miou] mIoU = {kq['mIoU']} trên {kq['n_cham']} frame"
          f" · GT rỗng: {kq['so_frame_gt_rong']} · thiếu mask: {kq['so_frame_thieu_mask']}")
    # `mIoU_p05` KHÔNG được im lặng biến mất khi thiếu mẫu: im lặng thì người đọc artifact cũ thấy
    # con số cũ (từ 5 frame) mà không biết nay nó bị từ chối công bố (ticket #23).
    if kq["mIoU_p05"] is None:
        print(f"[miou] mIoU_p05 = CHƯA CÔNG BỐ (chỉ {kq['mIoU_p05_n']} frame < {MIN_SAMPLES} mẫu "
              "— ở cỡ mẫu này p05 ≈ frame xấu nhất; xem `frames` để đọc từng frame)")
    else:
        print(f"[miou] mIoU_p05 = {kq['mIoU_p05']} (n = {kq['mIoU_p05_n']} frame)")
    print(f"[miou] dạng GT: {kq['gt_dang'] or 'KHÔNG KHAI'}"
          + (f" — {kq['mIoU_dinh_nghia']}" if kq.get("mIoU_dinh_nghia") else ""))
    for ten_canh_bao in mem:
        print(f"[miou] CẢNH BÁO: {ten_canh_bao}")
    # LUÔN in coverage (trước đây chỉ in khi thiếu > chấm được ⇒ 5/10 frame thiếu vẫn in mIoU "sạch",
    # review hẹp 14-11). Coverage 100 % mới được nói "trên cả clip".
    print(f"[miou] coverage: {kq['n_cham']}/{kq['so_frame_tong']} frame có mask "
          f"({kq['coverage']:.0%})" if kq.get("coverage") is not None else "")
    # `mask_ngoai_gt`: phần mask nằm NGOÀI GT — chỉ số KHÔNG bị chặn trên bởi GT hộp bao, nên khi GT là
    # hộp thì đây mới là chỗ nói được "model có phủ quá tay / trôi ra ngoài vật không".
    if kq.get("mask_ngoai_gt_mean") is not None:
        print(f"[miou] mask NGOÀI GT: trung bình {kq['mask_ngoai_gt_mean']:.1%} · tệ nhất "
              f"{kq['mask_ngoai_gt_max']:.1%} (frame {kq['mask_ngoai_gt_max_frame']}) — "
              "thấp = không tràn ra ngoài; KHÔNG nói mask phủ đủ, và KHÔNG phải mIoU")
        if kq.get("mask_ngoai_gt_n") != kq.get("n_cham"):
            print(f"[miou] CẢNH BÁO: 'tràn' tính trên {kq.get('mask_ngoai_gt_n')}/"
                  f"{kq.get('n_cham')} frame — frame model trả mask RỖNG không có gì để tràn nên bị "
                  "loại khỏi trung bình (mIoU vẫn tính 0,0)")
    if kq.get("coverage") is not None and kq["coverage"] < 1.0:
        print(f"[miou] CẢNH BÁO: chỉ chấm được {kq['n_cham']} / {kq['so_frame_tong']} frame có GT — "
              "CẤM nói 'mIoU trên cả clip' với con số này")
    if kq["mIoU"] is None:
        print("[miou] KHÔNG chấm được frame nào ⇒ mIoU = None (KHÔNG phải 0)")
        return 1
    if git_loi:
        print(f"[miou] CẢNH BÁO: không lấy được provenance ({git_loi})")
        return 1
    # Cảnh báo MỀM (GT hộp bao / thiếu người gán / không khai `dang_gt`) vẫn CHẤM và vẫn ghi artifact,
    # nhưng mã thoát phải là 1: hợp đồng đã ghi từ review 14-11 là "vẫn chấm nhưng exit 1", còn code
    # cũ trả 0 ⇒ CI/cổng tự động coi một bộ GT khai báo thiếu là "đạt" (review 15-11).
    if mem:
        print(f"[miou] {len(mem)} cảnh báo ⇒ exit 1: số vẫn dùng được nhưng phải đọc kèm "
              "`meta.dang_gt`/`meta.phuong_phap_gt`/`canh_bao_gt` trong artifact")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
