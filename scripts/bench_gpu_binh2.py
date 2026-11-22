"""
Quét `image_size` trên GPU để trả lời: "chính xác hơn + mượt hơn" đạt được ở đâu?

Vì sao cần: đo 22-11 trên CPU @192 (`data/miou_baseline_binh2_2026-11-22_metrics.json`) cho
mIoU **0,7644** với lỗi chính là **phân đoạn HỤT diện tích** (`dien_tich_pred` 27k–46k so với GT
32k–56k) — tức `image_size 192` quá thô cho vật mảnh, KHÔNG phải "bám nhầm vật". Trước khi đổi lõi
sang Cutie (thay model = rủi ro lớn), phải loại trừ giả thuyết rẻ hơn: **cùng SAM 2 nhưng chạy
`image_size` lớn trên GPU**. Trên CPU việc này bất khả thi (1024 ≈ 4 s/frame, đo cũ).

Cách dùng (Colab T4):
    python scripts/bench_gpu_binh2.py --device cuda --sizes 192,320,512,1024

Trên máy không GPU (kiểm tra đường ống, KHÔNG lấy số để công bố — artifact tự tách sang `_smoke`):
    python scripts/bench_gpu_binh2.py --device cpu --sizes 192 --max-frames 60

Nguyên tắc số đo (AGENTS §6):
- Ô chọn suy TRỰC TIẾP từ GT (không đoán), mỗi lần chạy đều truyền cùng một ô.
- Dùng CHUNG bộ frame GT với lần đo CPU ⇒ so sánh được.
- Artifact có `git_rev`, `git_dirty_code`, `lenh`, `do_luc` — Ở CẢ CẤP FILE LẪN TỪNG DÒNG, vì một
  file có thể gộp nhiều lần chạy (review độc lập 22-11, P1).
- `ms_fame`/`mIoU` đứng CẠNH nhau để không ai trích mIoU mà quên cái giá phải trả.
"""

import argparse
import json
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.score_miou import cham, doc_mask  # noqa: E402

# Hai bộ GT cùng clip, KHÔNG giẫm nhau: `binh2_tay` (12 frame, có frame GT rỗng) và `binh2_tay2`
# (7 frame tô thêm 22-11, trong đó 170–215 là GT RỖNG = vật đã rời khung).
GT_DIRS = ("docs/gt/binh2_tay", "docs/gt/binh2_tay2")

# Khoá mô tả "cùng một phép đo". Hai artifact chỉ được GỘP khi mọi khoá này trùng — gộp số của ô chọn
# khác vào cùng một file là cách nhanh nhất để tạo ra một bảng không tái lập được.
META_KHOA = ("clip", "o_chon_xywh", "frames_gt", "vos_every", "gt_dirs", "git_rev")


class LoiBench(Exception):
    """Lỗi có thông điệp cho người chạy (không phải traceback)."""


def _sh(*args) -> str:
    try:
        return subprocess.run(args, cwd=_REPO, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:                     # noqa: BLE001 — thiếu git vẫn phải ghi được artifact
        return ""


def _provenance() -> dict:
    rev = _sh("git", "rev-parse", "HEAD")
    # "bẩn" phải BỎ QUA `data/` — chính artifact sinh ra làm cây bẩn, nếu không thì `git_dirty_code`
    # luôn true một cách vô nghĩa (quy ước đã ghi trong AGENTS §6).
    dirty_all = _sh("git", "status", "--porcelain")
    dirty_code = any(not ln[3:].startswith("data/") for ln in dirty_all.splitlines() if ln)
    return {"git_rev": rev, "git_dirty_code": dirty_code}


def _frames_cua_gt(gt_dirs) -> tuple[list[int], list[int]]:
    """Trả `(frame_có_vật, frame_GT_rỗng)` của TẤT CẢ bộ GT — để dump mask ở đúng các frame đó.

    Chỉ nhận frame có FILE GT thật: một `index.json` trỏ tới PNG không tồn tại mà vẫn đem đi dump
    mask thì `cham` ghi "thiếu mask" và ta tưởng model hỏng.
    """
    co, rong = set(), set()
    for d in gt_dirs:
        p = _REPO / d / "index.json"
        if not p.is_file():
            continue
        for item in json.loads(p.read_text(encoding="utf-8"))["frames"]:
            idx = int(item["frame_idx"])
            f = p.parent / f"gt_{idx:06d}.png"
            if not f.is_file():
                print(f"[canh-bao] {d}: thiếu gt_{idx:06d}.png — bỏ frame này", flush=True)
                continue
            mask = doc_mask(f)
            (co if int(mask.sum()) else rong).add(idx)
    return sorted(co), sorted(rong)


def _o_chon_tu_gt(gt_dir: Path):
    """Ô chọn = hộp bao của mask GT ở FRAME ĐẦU TIÊN có trong `index.json`.

    Bản trước cứng `gt_000000.png` ⇒ bộ GT bắt đầu từ frame 170 (như `binh2_tay2`) làm script chết
    bằng `ValueError` (review độc lập 22-11, P2).
    """
    index = json.loads((gt_dir / "index.json").read_text(encoding="utf-8"))
    for item in sorted(index["frames"], key=lambda it: int(it["frame_idx"])):
        f = gt_dir / f"gt_{int(item['frame_idx']):06d}.png"
        if not f.is_file():
            continue
        mask = doc_mask(f)
        ys, xs = np.where(mask)
        if len(xs) == 0:
            continue                      # frame GT rỗng: không suy được hộp, thử frame sau
        return int(xs.min()), int(ys.min()), int(xs.max() - xs.min()), int(ys.max() - ys.min())
    raise LoiBench(f"[loi] {gt_dir}: không có frame GT nào có vật — không suy được ô chọn")


def _so_frame_cua_clip(path: Path) -> int:
    """Số frame của clip — để đặt `--stop-after-frames` ĐÚNG BẰNG độ dài clip.

    Bắt buộc: `live_worker` mặc định `loop_files=True` (phát lại từ đầu khi hết file), nên không
    truyền cờ này thì tiến trình không bao giờ thoát và không có bảng số (gặp thật trên Colab 22-11).
    Trả 0 hoặc âm ⇒ NÉM, không được lặng lẽ bỏ cờ (review độc lập 22-11, P0).
    """
    import cv2
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise LoiBench(f"[loi] không mở được clip: {path}")
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        cap.release()
    if n <= 0:
        raise LoiBench(f"[loi] không đọc được số frame của {path} (CAP_PROP_FRAME_COUNT = {n}). "
                       "Không có số này thì không đặt được `--stop-after-frames` ⇒ worker sẽ lặp "
                       "file vô hạn. Dùng `--max-frames N` để chỉ định thủ công.")
    return n


def _chay_co_in(proc: subprocess.Popen, timeout_s: float) -> tuple[list[str], bool]:
    """Đọc stdout của `proc` TỪNG DÒNG (in ra ngay) cho tới khi hết hoặc quá `timeout_s`.

    Phải có luồng đọc riêng: `for line in proc.stdout` một mình thì một tiến trình treo mà không in
    gì (import torch, tải checkpoint) sẽ block VĨNH VIỄN, `--timeout` không bao giờ được kiểm.
    """
    q: queue.Queue = queue.Queue()

    def _bom():
        try:
            if proc.stdout is not None:
                for ln in proc.stdout:
                    q.put(ln)
        finally:
            q.put(None)

    threading.Thread(target=_bom, daemon=True).start()
    lines: list[str] = []
    het_han = False
    deadline = time.monotonic() + timeout_s
    while True:
        con_lai = deadline - time.monotonic()
        if con_lai <= 0:
            het_han = True
            proc.kill()
            break
        try:
            item = q.get(timeout=min(con_lai, 0.5))
        except queue.Empty:
            continue
        if item is None:
            break
        lines.append(item)
        print("   " + item.rstrip(), flush=True)
    proc.wait()
    return lines, het_han


def _kiem_image_size(status: dict, size: int) -> str | None:
    """`None` nếu `status` chứng nhận model dùng ĐÚNG `size`; ngược lại trả lý do.

    AGENTS §6: `image_size_kiem_duoc = false` hoặc `image_size_hieu_luc = None` là
    **CHƯA KIỂM ĐƯỢC**, không phải "khớp". Ghi một lần chạy 1024 vào dòng 512 là công bố số sai.
    """
    ch = status.get("cau_hinh") or {}
    if ch.get("image_size_kiem_duoc") is False:
        return ("worker báo CHƯA KIỂM ĐƯỢC image_size hiệu lực "
                f"(cau_hinh_lech={ch.get('cau_hinh_lech')})")
    hieu_luc = ch.get("image_size_hieu_luc")
    if hieu_luc is None:
        return "worker không khai báo `image_size_hieu_luc` — chưa kiểm được cấu hình"
    if int(hieu_luc) != int(size):
        return (f"image_size hiệu lực {hieu_luc} ≠ yêu cầu {size} "
                f"(cau_hinh_lech={ch.get('cau_hinh_lech')})")
    return None


def chay_mot_cau_hinh(*, size: int, device: str, clip: str, bbox, frames: list[int],
                      max_frames: int | None, vos_every: int, python: str,
                      stream: bool = False, timeout_s: float = 1800.0,
                      stop_after: int | None = None, meta: dict | None = None) -> dict:
    out = _REPO / "data" / f"_gpu_{device}_{size}"
    masks = out / "masks"
    # Dọn dấu vết lần chạy trước: `status.json` cũ đọc được sau khi worker chết ngay từ đầu, và mask
    # cũ trong thư mục dùng lại sẽ được chấm như của lần này (review độc lập 22-11, P2).
    masks.mkdir(parents=True, exist_ok=True)
    for f in masks.glob("mask_*.png"):
        f.unlink()
    (out / "status.json").unlink(missing_ok=True)

    argv = [
        python, "-u", str(_REPO / "tools" / "live_worker.py"),
        "--source", clip, "--out-dir", str(out),
        "--bbox", f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "--image-size", str(size), "--vos-every", str(vos_every), "--device", device,
        "--dump-mask-frames", ",".join(str(i) for i in frames),
        "--dump-mask-dir", str(masks),
        # Nhịp phát không được là nút thắt: ta đo MODEL, không đo webcam.
        "--max-fps", "1000",
    ]
    # LUÔN có: `max_frames` (kiểm đường ống) → `stop_after` (độ dài clip). Thiếu cả hai thì worker
    # lặp vô hạn — đúng lỗi "chạy quài" trên Colab 22-11.
    dung_sau = max_frames or stop_after
    if not dung_sau or int(dung_sau) <= 0:
        raise LoiBench("[loi] không xác định được số frame cần dừng — worker sẽ lặp file vô hạn")
    argv += ["--stop-after-frames", str(int(dung_sau))]

    lenh = " ".join(argv)
    t0 = time.perf_counter()
    het_han = False
    if stream:
        # `subprocess.run(stdout=PIPE)` KHÔNG stream: nó gom hết rồi mới trả ⇒ người chạy thấy im
        # lặng 30–90 s lúc nạp model và bấm Ctrl-C (xảy ra 2 lần trên Colab 22-11).
        proc_p = subprocess.Popen(argv, cwd=_REPO, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1)
        lines, het_han = _chay_co_in(proc_p, timeout_s)
        gom = "".join(lines)
        (out / "worker.log").write_text(gom[-20000:], encoding="utf-8")
        ma_thoat, stdout_duoi, stderr_duoi = proc_p.returncode, gom[-1200:], "(đã gộp vào stdout)"
    else:
        try:
            proc = subprocess.run(argv, cwd=_REPO, capture_output=True, text=True,
                                  timeout=timeout_s)
            ma_thoat = proc.returncode
            stdout_duoi, stderr_duoi = (proc.stdout or "")[-1200:], (proc.stderr or "")[-600:]
        except subprocess.TimeoutExpired as exc:
            het_han = True
            ma_thoat = -9
            stdout_duoi = str(getattr(exc, "stdout", "") or "")[-1200:]
            stderr_duoi = f"quá --timeout {timeout_s:.0f}s"
    wall = time.perf_counter() - t0

    def _loi(ly_do: str) -> dict:
        return {
            "image_size": size, "device": device,
            "ma_thoat": ma_thoat, "lenh": lenh, "status_message": ly_do,
            "het_han": het_han, "wall_s": round(wall, 1),
            "stdout_duoi": stdout_duoi, "stderr_duoi": stderr_duoi,
            **(meta or {}),
        }

    if het_han:
        return _loi(f"quá --timeout {timeout_s:.0f} giây (tiến trình bị kill)")

    status_p = out / "status.json"
    status = json.loads(status_p.read_text(encoding="utf-8")) if status_p.is_file() else {}

    # Chẩn đoán khi lỗi: lấy CẢ HAI luồng + mã thoát + `status.json.message`. Bản đầu chỉ lấy
    # `stderr[-800:]` ⇒ trên Colab nó trả về đúng một dòng `UserWarning` của torch, che mất lỗi thật
    # (lỗi của worker đi ra stdout qua `[LOI]`/`print`). Không có chỗ này thì "LỖI: UserWarning" là
    # câu vô nghĩa với người chạy.
    if ma_thoat != 0 or status.get("state") == "error":
        return _loi(status.get("message") or "(worker không ghi `status.json.message`)")

    ch = status.get("cau_hinh") or {}
    lech = _kiem_image_size(status, size)
    if lech:
        return _loi(lech)

    frames_phat = int(status.get("frames") or 0)
    ket_qua, thong_ke = {}, {}
    for d in GT_DIRS:
        gt = _REPO / d
        if not (gt / "index.json").is_file():
            continue
        # Chỉ chấm đúng những frame thuộc bộ GT NÀY (trước đây dùng hợp của cả hai ⇒ frame không có
        # trong bộ này bị tính là "thiếu mask" — review độc lập 22-11, P2).
        idx_set = {int(it["frame_idx"])
                   for it in json.loads((gt / "index.json").read_text(encoding="utf-8"))["frames"]}
        item = [{"frame_idx": i,
                 "pred_path": str(masks / f"mask_{i:06d}.png")}
                for i in frames if i in idx_set]
        kq = cham(item, gt)
        thong_ke[Path(d).name] = {"coverage": kq.get("coverage"),
                                  "so_frame_thieu_mask": kq.get("so_frame_thieu_mask"),
                                  "so_frame_gt_rong": kq.get("so_frame_gt_rong")}
        ket_qua[Path(d).name] = {
            "mIoU": kq["mIoU"], "n_cham": kq["n_cham"],
            "mIoU_p05": kq.get("mIoU_p05"), "mIoU_p05_n": kq.get("mIoU_p05_n"),
            "mask_ngoai_gt_mean": kq["mask_ngoai_gt_mean"],
            # Giữ NGUYÊN từng dòng (`dien_tich_gt`/`dien_tich_pred`/`ly_do`) — không có chúng thì
            # "hụt diện tích" hay "tràn 5 %" chỉ là câu kể, không kiểm lại được.
            "frames": kq["frames"],
        }
    return {
        "image_size": size, "device": device, "vos_every": vos_every,
        "image_size_hieu_luc": ch.get("image_size_hieu_luc"),
        "frames_phat": frames_phat,
        "measured_fps": status.get("measured_fps"),
        "vos_fps": status.get("vos_fps"),
        "wall_s": round(wall, 1),
        "ms_moi_frame": round(wall * 1000.0 / frames_phat, 1) if frames_phat else None,
        "mIoU": {k: v["mIoU"] for k, v in ket_qua.items()},
        "n_cham": {k: v["n_cham"] for k, v in ket_qua.items()},
        "phu_gt": thong_ke,
        "chi_tiet": ket_qua,
        **(meta or {}),
    }


def _doc_artifact_cu(path: Path) -> dict | None:
    """Đọc artifact cũ; `None` nếu chưa có. Cấu trúc lạ ⇒ NÉM (không được lặng lẽ ghi đè)."""
    if not path.is_file():
        return None
    try:
        cu = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise LoiBench(f"[loi] artifact cũ không đọc được ({path}): {exc}. "
                       f"Đổi tên/di chuyển file đó rồi chạy lại.") from exc
    if not isinstance(cu, dict) or not isinstance(cu.get("ket_qua"), list):
        raise LoiBench(f"[loi] artifact cũ sai cấu trúc ({path}): cần dict có `ket_qua` là list. "
                       "Đổi tên/di chuyển file đó rồi chạy lại.")
    if not all(isinstance(r, dict) for r in cu["ket_qua"]):
        raise LoiBench(f"[loi] artifact cũ có phần tử `ket_qua` không phải object ({path}).")
    return cu


def gop_ket_qua(cu: dict | None, rows: list[dict], meta: dict) -> list[dict]:
    """Gộp `rows` (đợt này) vào `cu` (đợt trước) theo `image_size`; đợt SAU thắng nếu trùng.

    Từ chối gộp khi khác `META_KHOA`: số của hai ô chọn / hai `git_rev` / hai bộ frame mà nằm chung
    một file là bảng không tái lập được (review độc lập 22-11, P1).
    """
    if not cu:
        return sorted(rows, key=lambda r: r.get("image_size") or 0)
    lech = [k for k in META_KHOA if cu.get(k) != meta.get(k)]
    if lech:
        chi_tiet = ", ".join(f"{k}: {cu.get(k)!r} ≠ {meta.get(k)!r}" for k in lech)
        raise LoiBench(f"[loi] artifact cũ ĐO CẤU HÌNH KHÁC ({chi_tiet}) ⇒ không gộp. "
                       "Dùng `--out` để ghi file mới thay vì trộn hai phép đo.")
    moi = {r.get("image_size") for r in rows}
    cu_rows = [r for r in cu["ket_qua"] if r.get("image_size") not in moi]
    return sorted(cu_rows + rows, key=lambda r: r.get("image_size") or 0)


def tao_payload(*, rows: list[dict], meta: dict, provenance: dict, lenh: str,
                max_frames: int | None, gt_dirs) -> dict:
    """Dựng payload SAU khi gộp.

    Đây là chỗ bug P0 của bản trước: `payload["ket_qua"]` được gán trước khi gộp, rồi `rows` bị gán
    lại thành list mới ⇒ file ghi ra CHỈ có đợt cuối, còn bảng in ra thì đủ dòng (review độc lập
    22-11). Nay không tồn tại đường nào để payload trỏ vào list cũ.
    """
    return {
        **provenance,
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "lenh": lenh,
        **meta,
        "gt_dirs": [Path(d).name for d in gt_dirs],
        "max_frames": max_frames,
        "ket_qua": rows,
        "dinh_nghia": "mIoU = trung bình IoU(mask, GT silhouette) trên frame GT CÓ vật; GT rỗng "
                      "không chấm. `ms_moi_frame` = thời gian tường / số frame PHÁT (gồm cả nạp "
                      "model) ⇒ là CẬN TRÊN của độ trễ thật, không phải `vos_ms`. `vos_fps` = "
                      "nhịp VOS worker tự báo.",
        "canh_bao": [
            "mIoU ở đây là GT NGƯỜI TÔ (silhouette), không phải cận trên tổng hợp.",
            "Mỗi dòng trong `ket_qua` mang `lenh`/`git_rev`/`do_luc` riêng: file có thể gộp nhiều "
            "lần chạy, nên ĐỌC PROVENANCE CỦA TỪNG DÒNG, không chỉ cấp file.",
            "`--max-frames` ⇒ số chỉ để kiểm đường ống: KHÔNG công bố (file tự đổi tên `_smoke`).",
        ],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Quét image_size trên GPU (SAM 2) — mIoU vs ms/frame")
    ap.add_argument("--clip", default="data/binh2.mp4")
    ap.add_argument("--sizes", default="192,320,512,1024")
    ap.add_argument("--device", default="cuda",
                    help="cuda (Colab T4) hoặc cpu (chỉ để kiểm đường ống)")
    ap.add_argument("--vos-every", type=int, default=1,
                    help="1 = mask mỗi frame (chấm mIoU được ở mọi frame có GT)")
    ap.add_argument("--max-frames", type=int, default=None,
                    help="chỉ xử lý N frame đầu (kiểm đường ống; số mIoU KHÔNG công bố được)")
    ap.add_argument("--stream", action="store_true",
                    help="in log của worker NGAY khi chạy (nạp model 30–90 s mà im lặng thì dễ tưởng treo)")
    ap.add_argument("--timeout", type=float, default=1800.0, help="giây cho MỖI cấu hình")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    try:
        return _run(args)
    except LoiBench as exc:
        print(exc)
        return 2


def _run(args) -> int:
    # Clip KHÔNG nằm trong git (`data/` bị .gitignore chặn: 3–20 MB/clip) ⇒ trên Colab bản clone
    # KHÔNG có video. Không kiểm ở đây thì worker chết với "Không mở được video file" và người chạy
    # chỉ thấy một dòng lỗi của tầng dưới, không biết phải làm gì. Chặn ở cửa vào + nói rõ cách sửa.
    clip_p = Path(args.clip)
    if not clip_p.is_absolute() and not clip_p.is_file():
        clip_p = _REPO / args.clip
    if not clip_p.is_file():
        print(f"[loi] KHÔNG có clip: {args.clip}\n"
              f"      (repo KHÔNG chứa video — `data/` bị .gitignore chặn)\n"
              f"      Cách sửa trên Colab: kéo file vào `/content/DoAn-NAB/data/` rồi chạy lại;\n"
              f"      hoặc trong cell: `from google.colab import files; files.upload()` rồi\n"
              f"      `!mv binh2.mp4 data/binh2.mp4`.")
        return 2

    gt_dirs = [(_REPO / d) for d in GT_DIRS if (_REPO / d / "index.json").is_file()]
    if not gt_dirs:
        print("[loi] không thấy bộ GT nào trong", GT_DIRS)
        return 2
    co_vat, gt_rong = _frames_cua_gt(gt_dirs)
    frames = sorted(set(co_vat) | set(gt_rong))
    if args.max_frames:
        frames = [f for f in frames if f < args.max_frames]
    if not frames:
        print("[loi] không còn frame GT nào sau khi lọc `--max-frames`")
        return 2
    bbox = _o_chon_tu_gt(gt_dirs[0])
    print(f"[bench] ô chọn (từ GT frame đầu): {bbox} · {len(frames)} frame GT "
          f"· device={args.device}")

    stop_after = _so_frame_cua_clip(clip_p)
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    python = sys.executable
    rows = []
    for size in sizes:
        print(f"[bench] chạy image_size={size} …", flush=True)
        meta_row = {
            "lenh_rieng": "", "git_rev": _provenance()["git_rev"],
            "do_luc_rieng": datetime.now().isoformat(timespec="seconds"),
        }
        rows.append(chay_mot_cau_hinh(
            size=size, device=args.device, clip=args.clip, bbox=bbox, frames=frames,
            max_frames=args.max_frames, vos_every=args.vos_every, python=python,
            stream=args.stream, timeout_s=args.timeout,
            stop_after=stop_after, meta=meta_row))

    # Dòng lỗi không có `mIoU` ⇒ bảng dưới in riêng, không trộn.
    meta = {
        "clip": args.clip, "o_chon_xywh": list(bbox), "vos_every": args.vos_every,
        "frames_gt": frames, "gt_dirs": [d.name for d in gt_dirs],
        "git_rev": _provenance()["git_rev"],
    }
    for r in rows:
        r["lenh_rieng"] = r.get("lenh", "")

    if args.out:
        out = Path(args.out)
    else:
        # Lần chạy "kiểm đường ống" (`--max-frames`) KHÔNG được ghi vào artifact công bố: nó sẽ thay
        # dòng 192 thật bằng một dòng 60-frame trên CPU (review độc lập 22-11, P2).
        hauto = "_smoke" if args.max_frames else ""
        out = _REPO / "data" / f"gpu_sweep_binh2_{datetime.now():%Y-%m-%d}{hauto}_metrics.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    cu = None if args.max_frames else _doc_artifact_cu(out)
    rows = gop_ket_qua(cu, rows, meta)

    payload = tao_payload(
        rows=rows, meta=meta, provenance=_provenance(),
        lenh=" ".join([Path(sys.executable).name, "scripts/bench_gpu_binh2.py", *sys.argv[1:]]),
        max_frames=args.max_frames, gt_dirs=gt_dirs)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[bench] {out}")
    print(f"{'imgsz':>6} {'hiệu lực':>9} {'ms/frame':>9} {'vos_fps':>8}  mIoU")
    for r in rows:
        if "ma_thoat" in r:
            print(f"{r.get('image_size')!s:>6}  LỖI (mã thoát {r.get('ma_thoat')}): "
                  f"{r.get('status_message') or '(không có message)'}")
            print("        lệnh:", r.get("lenh"))
            print("        stdout:", (r.get("stdout_duoi") or "").strip()[-500:])
            continue
        miou = ", ".join(f"{k}={v}" for k, v in (r.get("mIoU") or {}).items())
        print(f"{r.get('image_size')!s:>6} {str(r.get('image_size_hieu_luc')):>9} "
              f"{str(r.get('ms_moi_frame')):>9} {str(r.get('vos_fps')):>8}  {miou}")

    hong = [r.get("image_size") for r in rows if "ma_thoat" in r]
    if hong:
        print(f"[loi] cấu hình KHÔNG đo được: {hong} — xem `status_message` ở trên")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
