"""
Quét `image_size` trên GPU để trả lời: "chính xác hơn + mượt hơn" đạt được ở đâu?

Vì sao cần: đo 22-11 trên CPU @192 (`data/miou_baseline_binh2_2026-11-22_metrics.json`) cho
mIoU **0,7644** với lỗi chính là **phân đoạn HỤT diện tích** (`dien_tich_pred` 27k–46k so với GT
32k–56k) — tức `image_size 192` quá thô cho vật mảnh, KHÔNG phải "bám nhầm vật". Trước khi đổi lõi
sang Cutie (thay model = rủi ro lớn), phải loại trừ giả thuyết rẻ hơn: **cùng SAM 2 nhưng chạy
`image_size` lớn trên GPU**. Trên CPU việc này bất khả thi (1024 ≈ 4 s/frame, đo cũ).

Cách dùng (Colab T4):
    python scripts/bench_gpu_binh2.py --device cuda --sizes 192,320,512,1024

Trên máy không GPU (kiểm tra đường ống, KHÔNG lấy số để công bố):
    python scripts/bench_gpu_binh2.py --sizes 192 --max-frames 60

Nguyên tắc số đo (AGENTS §6):
- Ô chọn suy TRỰC TIẾP từ GT frame 0 (không đoán), mỗi lần chạy đều truyền cùng một ô.
- Dùng CHUNG bộ frame GT với lần đo CPU ⇒ so sánh được.
- Artifact có `git_rev`, `git_dirty_code`, `lenh`, `do_luc`; `ms/frame` và `mIoU` đứng CẠNH nhau để
  không ai trích mIoU mà quên cái giá phải trả.
"""

import argparse
import json
import subprocess
import sys
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


def _provenance() -> dict:
    def _sh(*args):
        try:
            return subprocess.run(args, cwd=_REPO, capture_output=True, text=True,
                                  check=True).stdout.strip()
        except Exception:                     # noqa: BLE001 — thiếu git vẫn phải ghi được artifact
            return ""
    rev = _sh("git", "rev-parse", "HEAD")
    # "bẩn" phải BỎ QUA `data/` — chính artifact sinh ra làm cây bẩn, nếu không thì `git_dirty_code`
    # luôn true một cách vô nghĩa (quy ước đã ghi trong AGENTS §6).
    dirty_all = _sh("git", "status", "--porcelain")
    dirty_code = any(not ln[3:].startswith("data/") for ln in dirty_all.splitlines() if ln)
    return {"git_rev": rev, "git_dirty_code": dirty_code}


def _frames_cua_gt(gt_dirs) -> tuple[list[int], list[int]]:
    """Trả `(frame_có_vật, frame_GT_rỗng)` của TẤT CẢ bộ GT — để dump mask ở đúng các frame đó."""
    co, rong = set(), set()
    for d in gt_dirs:
        p = _REPO / d / "index.json"
        if not p.is_file():
            continue
        for item in json.loads(p.read_text(encoding="utf-8"))["frames"]:
            idx = int(item["frame_idx"])
            mask = doc_mask(p.parent / f"gt_{idx:06d}.png")
            (co if int(mask.sum()) else rong).add(idx)
    return sorted(co), sorted(rong)


def _o_chon_tu_gt(gt_dir: Path):
    """Ô chọn = hộp bao của mask GT frame 0 (nguồn ĐỘC LẬP, không suy từ model)."""
    mask = doc_mask(gt_dir / "gt_000000.png")
    ys, xs = np.where(mask)
    if len(xs) == 0:
        raise SystemExit(f"[loi] GT frame 0 của {gt_dir} rỗng — không suy được ô chọn")
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min()), int(ys.max() - ys.min())


def chay_mot_cau_hinh(*, size: int, device: str, clip: str, bbox, frames: list[int],
                      max_frames: int | None, vos_every: int, python: str,
                      stream: bool = False, timeout_s: float = 1800.0) -> dict:
    out = _REPO / "data" / f"_gpu_{device}_{size}"
    masks = out / "masks"
    masks.mkdir(parents=True, exist_ok=True)
    argv = [
        python, str(_REPO / "tools" / "live_worker.py"),
        "--source", clip, "--out-dir", str(out),
        "--bbox", f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "--image-size", str(size), "--vos-every", str(vos_every), "--device", device,
        "--dump-mask-frames", ",".join(str(i) for i in frames),
        "--dump-mask-dir", str(masks),
        # Nhịp phát không được là nút thắt: ta đo MODEL, không đo webcam.
        "--max-fps", "1000",
    ]
    if max_frames:
        argv += ["--stop-after-frames", str(max_frames)]
    t0 = time.perf_counter()
    if stream:
        # `subprocess.run(stdout=PIPE)` KHÔNG stream: nó gom hết rồi mới trả ⇒ người chạy thấy im
        # lặng 30–90 s lúc nạp model và bấm Ctrl-C (xảy ra 2 lần trên Colab 22-11). Muốn thấy tiến
        # trình thật thì phải `Popen` + đọc từng dòng.
        proc = subprocess.Popen(argv, cwd=_REPO, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        lines: list[str] = []
        deadline = t0 + timeout_s
        assert proc.stdout is not None
        for line in proc.stdout:
            print("   " + line.rstrip(), flush=True)
            lines.append(line)
            if time.perf_counter() > deadline:
                proc.kill()
                break
        proc.wait()
        gom = "".join(lines)
        (out / "worker.log").write_text(gom[-20000:], encoding="utf-8")

        class _P:                      # giữ cùng hình dạng với nhánh không-stream
            returncode = proc.returncode
            stdout = gom
            stderr = ""
        proc = _P()
    else:
        proc = subprocess.run(argv, cwd=_REPO, capture_output=True, text=True,
                              timeout=timeout_s)
    wall = time.perf_counter() - t0

    status_p = out / "status.json"
    status = json.loads(status_p.read_text(encoding="utf-8")) if status_p.is_file() else {}

    # Chẩn đoán khi lỗi: lấy CẢ HAI luồng + mã thoát + `status.json.message`. Bản đầu chỉ lấy
    # `stderr[-800:]` ⇒ trên Colab nó trả về đúng một dòng `UserWarning` của torch, che mất lỗi thật
    # (lỗi của worker đi ra stdout qua `[LOI]`/`print`). Không có chỗ này thì "LỖI: UserWarning" là
    # câu vô nghĩa với người chạy.
    if proc.returncode != 0 or status.get("state") == "error":
        return {
            "image_size": size, "device": device,
            "ma_thoat": proc.returncode,
            "lenh": " ".join(argv),
            "status_message": status.get("message"),
            "stdout_duoi": (proc.stdout or "")[-1200:],
            "stderr_duoi": (proc.stderr or "")[-600:],
        }
    frames_phat = int(status.get("frames") or 0)
    ket_qua = {}
    for d in GT_DIRS:
        gt = _REPO / d
        if not (gt / "index.json").is_file():
            continue
        item = [{"frame_idx": i,
                 "pred_path": str(masks / f"mask_{i:06d}.png")} for i in frames]
        kq = cham(item, gt)
        ket_qua[Path(d).name] = {
            "mIoU": kq["mIoU"], "n_cham": kq["n_cham"],
            "mask_ngoai_gt_mean": kq["mask_ngoai_gt_mean"],
            "frames": [[r["frame_idx"], r.get("iou")] for r in kq["frames"]],
        }
    return {
        "image_size": size, "device": device, "vos_every": vos_every,
        "frames_phat": frames_phat,
        "display_fps": status.get("display_fps"),
        "mask_fps": status.get("mask_fps"),
        "image_size_hieu_luc": (status.get("cau_hinh") or {}).get("image_size_hieu_luc"),
        "wall_s": round(wall, 1),
        "ms_moi_frame": round(wall * 1000.0 / frames_phat, 1) if frames_phat else None,
        "mIoU": {k: v["mIoU"] for k, v in ket_qua.items()},
        "n_cham": {k: v["n_cham"] for k, v in ket_qua.items()},
        "chi_tiet": ket_qua,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Quét image_size trên GPU (SAM 2) — mIoU vs ms/frame")
    ap.add_argument("--clip", default="data/binh2.mp4")
    ap.add_argument("--sizes", default="192,320,512,1024")
    ap.add_argument("--device", default="cuda", help="cuda (Colab T4) hoặc cpu (chỉ để kiểm đường ống)")
    ap.add_argument("--vos-every", type=int, default=1,
                    help="1 = mask mỗi frame (chấm mIoU được ở mọi frame có GT)")
    ap.add_argument("--max-frames", type=int, default=None,
                    help="chỉ xử lý N frame đầu (kiểm đường ống; số mIoU KHÔNG công bố được)")
    ap.add_argument("--stream", action="store_true",
                    help="in log của worker NGAY khi chạy (nạp model 30–90 s mà im lặng thì dễ tưởng treo)")
    ap.add_argument("--timeout", type=float, default=1800.0, help="giây cho MỖI cấu hình")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

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
    bbox = _o_chon_tu_gt(gt_dirs[0])
    print(f"[bench] ô chọn (từ GT f0): {bbox} · {len(frames)} frame GT · device={args.device}")

    python = sys.executable
    rows = []
    for size in [int(s) for s in args.sizes.split(",") if s.strip()]:
        print(f"[bench] chạy image_size={size} …", flush=True)
        rows.append(chay_mot_cau_hinh(
            size=size, device=args.device, clip=args.clip, bbox=bbox, frames=frames,
            max_frames=args.max_frames, vos_every=args.vos_every, python=python,
            stream=args.stream, timeout_s=args.timeout))

    payload = {
        **_provenance(),
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "lenh": " ".join([Path(sys.executable).name, "scripts/bench_gpu_binh2.py", *sys.argv[1:]]),
        "clip": args.clip, "o_chon_xywh": list(bbox), "vos_every": args.vos_every,
        "frames_gt": frames, "gt_dirs": [d.name for d in gt_dirs],
        "ket_qua": rows,
        "dinh_nghia": "mIoU = trung bình IoU(mask, GT silhouette) trên frame GT CÓ vật; GT rỗng "
                      "không chấm. `ms_moi_frame` = thời gian tường / số frame PHÁT (gồm cả nạp "
                      "model) ⇒ là CẬN TRÊN của độ trễ thật, không phải `vos_ms`.",
        "canh_bao": [
            "mIoU ở đây là GT NGƯỜI TÔ (silhouette), không phải cận trên tổng hợp.",
            "Nếu `--max-frames` được dùng thì số chỉ để kiểm đường ống: KHÔNG công bố.",
        ],
    }
    out = Path(args.out) if args.out else (
        _REPO / "data" / f"gpu_sweep_binh2_{datetime.now():%Y-%m-%d}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[bench] {out}")
    print(f"{'imgsz':>6} {'hiệu lực':>9} {'ms/frame':>9} {'display_fps':>12}  mIoU")
    for r in rows:
        if r.get("status_message") is not None or "ma_thoat" in r:
            print(f"{r['image_size']:>6}  LỖI (mã thoát {r.get('ma_thoat')}): "
                  f"{r.get('status_message') or '(không có message)'}")
            print("        lệnh:", r.get("lenh"))
            print("        stdout:", (r.get("stdout_duoi") or "").strip()[-500:])
            continue
        miou = ", ".join(f"{k}={v}" for k, v in (r.get("mIoU") or {}).items())
        print(f"{r['image_size']:>6} {str(r.get('image_size_hieu_luc')):>9} "
              f"{str(r.get('ms_moi_frame')):>9} {str(r.get('display_fps')):>12}  {miou}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
