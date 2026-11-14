"""
Sinh BẢNG CẤU HÌNH cho báo cáo (việc #5 của plan): `image_size` × `vos_every` ⇒ FPS phát, nhịp mask,
`vos_ms`, tuổi dữ liệu ảnh — kèm **ngưỡng nhiễu đo được** (3 lần lặp) để không ai trích một chênh
lệch nằm trong nhiễu thành "tốt hơn".

Chức năng: chạy `tools/live_worker.py` THẬT (đúng đường live: cùng worker, cùng `status.json`) trên
           một clip với từng cặp cấu hình, `--lan` lần mỗi cặp, rồi tổng hợp trung bình ± độ lệch
           chuẩn. In bảng markdown + ghi artifact JSON có `git_rev`/`git_dirty_code`/`lenh`/`do_luc`.
Input  : --clip, --bbox (x,y,w,h — BẮT BUỘC: hộp mặc định hay rơi vào nền), --sizes, --every,
         --lan, --frames, --device, --out, --md, --timeout.
Output : `data/bang_cau_hinh_<ngày>_metrics.json` + (tuỳ chọn) file markdown.
Lưu ý  : đây là số trên **máy này** (CPU, `sam2.1_hiera_tiny`) — artifact ghi rõ điều đó. Mọi so sánh
         phải so với cột `nhieu_*`; chênh lệch < nhiễu ⇒ bảng ghi **"không phân biệt được"**, không
         ghi "tốt hơn" (AGENTS §6, `scripts/repeatability.py`).
"""

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Khoá lấy từ `status.json` của worker: (khoá, nhãn trong bảng, "CẤM trích thành").
COT = [
    ("measured_fps", "FPS phát", "nhịp VẼ frame (LK lấp giữa), KHÔNG phải nhịp model"),
    ("vos_fps", "Nhịp mask", "số lần model chạy/giây — CẤM gọi là FPS của video"),
    ("vos_ms", "vos_ms", "chỉ phần model; chưa cộng `pre_ms` (~12 ms) khi nói 'một frame tốn bao lâu'"),
    ("pre_ms", "pre_ms", "tiền xử lý mỗi frame (resize + tensor), KHÔNG cộng vào `vos_ms`"),
    ("cycle_ms", "chu kỳ", "1/vos_fps thực — các pha là mẫu của lần VOS gần nhất, đừng cộng 4 pha"),
    ("mask_age_total_ms", "tuổi mask (mẫu cuối)", "một mẫu, không phải phân vị"),
    ("mask_age_p95", "tuổi mask p95", "p95 trên cửa sổ `age_n`; n=0 ⇒ chưa đo (None)"),
]


def _run_once(clip: Path, bbox, size, every, frames: int, device: str, timeout: float,
              mask_smoothing: float = 1.0) -> dict:
    """Chạy MỘT phiên worker thật rồi đọc `status.json` cuối. Trả dict số đo + lỗi (nếu có)."""
    with tempfile.TemporaryDirectory(prefix="bang_cau_hinh_") as tmp:
        out = Path(tmp)
        (out / "bbox.json").write_text(
            json.dumps({"x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3]}), encoding="utf-8")
        cmd = [sys.executable, str(_REPO_ROOT / "tools" / "live_worker.py"),
               "--source", str(clip), "--out-dir", str(out),
               "--image-size", str(size), "--vos-every", str(every),
               "--mask-smoothing", str(mask_smoothing),
               "--device", device, "--stop-after-frames", str(frames)]
        began = time.perf_counter()
        try:
            proc = subprocess.run(cmd, cwd=str(_REPO_ROOT), capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"loi": f"quá {timeout:.0f} s", "elapsed_s": None}
        elapsed = time.perf_counter() - began
        status = {}
        try:
            status = json.loads((out / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"loi": f"không đọc được status.json: {exc}", "elapsed_s": elapsed,
                    "ma_thoat": proc.returncode, "stderr": proc.stderr[-400:]}
        if status.get("state") == "error":
            return {"loi": str(status.get("message")), "elapsed_s": elapsed,
                    "ma_thoat": proc.returncode}
        if proc.returncode != 0:
            return {"loi": f"worker thoát mã {proc.returncode}", "elapsed_s": elapsed,
                    "stderr": proc.stderr[-400:]}
        rows = {key: status.get(key) for key, _nhan, _cam in COT}
        rows.update({"frames": status.get("frames"), "age_n": status.get("age_n"),
                     "elapsed_s": round(elapsed, 2)})
        return rows


def _thong_ke(gia_tri):
    """mean/std/min/max của các giá trị KHÔNG None. `n < 2` ⇒ std = None (không kết luận được)."""
    so = [float(v) for v in gia_tri if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not so:
        return {"n": 0, "mean": None, "std": None, "min": None, "max": None}
    return {
        "n": len(so),
        "mean": round(statistics.fmean(so), 2),
        "std": round(statistics.stdev(so), 2) if len(so) >= 2 else None,
        "min": round(min(so), 2),
        "max": round(max(so), 2),
    }


def tong_hop(cau_hinh, sizes, evers, runs: dict):
    """Tổng hợp `runs[(size, every)] = [kết quả từng lần]` → dict có thống kê + lỗi."""
    bang = {}
    for size in sizes:
        for every in evers:
            ket_qua = runs.get((size, every), [])
            loi = [r["loi"] for r in ket_qua if r.get("loi")]
            ok = [r for r in ket_qua if not r.get("loi")]
            dong = {"image_size": size, "vos_every": every, "so_lan": len(ket_qua),
                    "so_lan_loi": len(loi), "loi": loi[:3]}
            for key, _nhan, _cam in COT:
                dong[key] = _thong_ke([r.get(key) for r in ok])
            # `age_n`/`frames` PHẢI có trong artifact: cảnh báo "p95 trên cửa sổ `age_n`" mà field đó
            # không tồn tại thì người đọc không biết p95 dựa trên bao nhiêu mẫu (review độc lập 14-11,
            # P2). §ố mẫu nhỏ (vd lần chạy chỉ được 5/60 frame) cũng lộ ra ở đây.
            dong["age_n"] = _thong_ke([r.get("age_n") for r in ok])
            dong["frames"] = _thong_ke([r.get("frames") for r in ok])
            bang[f"{size}_{every}"] = dong
    return bang


def chenh_lech_duoi_nhieu(a: dict, b: dict, key: str) -> bool:
    """Chênh lệch `key` giữa 2 cấu hình có NẰM TRONG nhiễu không (dùng std lớn hơn làm ngưỡng)."""
    sa, sb = a.get(key) or {}, b.get(key) or {}
    if sa.get("mean") is None or sb.get("mean") is None:
        return True                                   # thiếu số ⇒ không kết luận được
    nhieu = max(sa.get("std") or 0.0, sb.get("std") or 0.0)
    return abs(sa["mean"] - sb["mean"]) <= nhieu


def bang_markdown(meta: dict, bang: dict, sizes, evers) -> str:
    """Bảng markdown: mỗi dòng một cấu hình, kèm cột `± nhiễu` để người đọc thấy ngưỡng."""
    dong = [
        "# Bảng cấu hình — sinh tự động, đừng sửa tay",
        "",
        "> Sinh bởi `python scripts/bang_cau_hinh.py`. Số trên **máy này**: "
        f"{meta['moi_truong']}. Commit `{meta['git_rev']}`"
        f"{' (cây BẨN: số không tái lập)' if meta.get('git_dirty_code') else ''}.",
        "> Mỗi cấu hình chạy **{0} lần**; `±` là độ lệch chuẩn giữa các lần ⇒ **chênh lệch nhỏ hơn `±` "
        "thì ghi 'không phân biệt được', cấm ghi 'tốt hơn'**.".format(meta["so_lan"]),
        "",
        "| image_size | vos_every | FPS phát | Nhịp mask | vos_ms | tuổi mask p95 | age_n | lần | lỗi |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for size in sizes:
        for every in evers:
            row = bang.get(f"{size}_{every}", {})
            if not row:
                continue

            def _o(key):
                s = row.get(key) or {}
                if s.get("mean") is None:
                    return "—"
                return f"{s['mean']:g} ± {s['std']:g}" if s.get("std") is not None else f"{s['mean']:g}"

            age_n = (row.get("age_n") or {}).get("mean")
            dong.append(f"| {size} | {every} | {_o('measured_fps')} | {_o('vos_fps')} | "
                        f"{_o('vos_ms')} | {_o('mask_age_p95')} | "
                        f"{'—' if age_n is None else f'{age_n:g}'} | {row.get('so_lan')} | "
                        f"{row.get('so_lan_loi')} |")
    dong += ["",
             "**CẤM trích**:",
             "",
             "- `FPS phát` là nhịp **vẽ** frame (LK lấp giữa các lần VOS) — không phải nhịp model.",
             "- `Nhịp mask` mới là số lần model chạy/giây; cấm viết \"mask 30 FPS\".",
             "- `vos_ms` chỉ là phần model; nói \"một frame tốn bao lâu\" thì phải cộng `pre_ms` "
             "(~12 ms) — xem cột trong artifact.",
             "- Tuổi mask p95 = `None` khi chưa đủ mẫu; **`None` không phải `0`**.",
             ""]
    return "\n".join(dong)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bảng cấu hình image_size × vos_every (số thật).")
    parser.add_argument("--clip", default="data/binh1.mp4")
    parser.add_argument("--bbox", required=False, help="x,y,w,h — ô chọn trên VẬT THẬT")
    parser.add_argument("--sizes", default="192,256,320")
    parser.add_argument("--every", default="2,3,6", dest="evers")
    parser.add_argument("--lan", type=int, default=3, help="số lần lặp mỗi cấu hình (>= 2 mới có ±)")
    parser.add_argument("--frames", type=int, default=60, help="số frame mỗi lần chạy")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--out", default=None)
    parser.add_argument("--md", default=None, help="ghi bảng markdown vào file này")
    parser.add_argument("--check", action="store_true",
                        help="CHỈ ĐỌC: so file .md đã commit với bản sinh lại từ artifact có sẵn "
                             "(không chạy worker, không ghi file)")
    args = parser.parse_args(argv)

    out = Path(args.out) if args.out else (
        _REPO_ROOT / "data" / f"bang_cau_hinh_{datetime.now():%Y-%m-%d}_metrics.json")
    md_path = Path(args.md) if args.md else _REPO_ROOT / "docs" / "bang-cau-hinh.md"

    if args.check:
        # `--check` (mô tả là "cho CI") ở bản trước lại CHẠY 27 phiên worker rồi GHI ĐÈ artifact trước
        # khi so ⇒ vừa tốn 5 phút vừa làm bẩn bằng chứng đã commit, và luôn lệch vì md chứa git_rev
        # (review độc lập 14-11, P2). Nay chỉ đọc artifact + sinh md từ nó.
        if not out.is_file():
            print(f"[bang] KHÔNG có artifact để kiểm: {out}")
            return 2
        payload = json.loads(out.read_text(encoding="utf-8"))
        meta = payload.get("meta", {})
        sizes = sorted({int(k.split("_")[0]) for k in payload.get("cau_hinh", {})})
        evers = sorted({int(k.split("_")[1]) for k in payload.get("cau_hinh", {})})
        md_moi = bang_markdown(meta, payload.get("cau_hinh", {}), sizes, evers)
        cu = md_path.read_text(encoding="utf-8") if md_path.is_file() else ""
        # So phần THÂN bảng (bỏ dòng provenance chứa git_rev — nó đổi sau mỗi commit, và điều cần
        # kiểm là "số trong md có khớp artifact không").
        def _than(text):
            return [ln for ln in text.splitlines()
                    if ln.startswith("|") or ln.startswith("- ") or ln.startswith("**")]

        if _than(cu) != _than(md_moi):
            print(f"[bang] {md_path} LỆCH so với {out} — chạy lại không có --check để sinh lại")
            return 1
        print(f"[bang] {md_path} khớp artifact {out.name} (chỉ đọc, không ghi)")
        return 0

    if not args.bbox:
        print("[LOI] cần --bbox x,y,w,h (ô chọn trên VẬT THẬT; hộp mặc định hay rơi vào nền)")
        return 2
    sizes = [int(v) for v in args.sizes.split(",") if v.strip()]
    evers = [int(v) for v in args.evers.split(",") if v.strip()]
    bbox = tuple(int(v) for v in args.bbox.split(","))
    if len(bbox) != 4 or bbox[2] <= 0 or bbox[3] <= 0:
        print(f"[LOI] --bbox phải là x,y,w,h với w,h > 0; nhận {args.bbox!r}")
        return 2
    if args.lan < 2:
        # Từ chối hẳn thay vì cảnh báo rồi chạy: bảng không có cột `±` sẽ bị trích như "ổn định",
        # đúng bẫy `n < 2` của AGENTS §6 ("một lần chạy thì không kết luận được gì").
        print(f"[LOI] --lan {args.lan}: cần >= 2 mới có độ lệch chuẩn (n=1 thì không kết luận được)")
        return 2

    clip = Path(args.clip)
    if not clip.is_absolute():
        clip = _REPO_ROOT / clip
    if not clip.is_file():
        print(f"[LOI] không thấy clip {clip}")
        return 2

    runs = {}
    for size in sizes:
        for every in evers:
            runs[(size, every)] = []
            for lan in range(args.lan):
                ket_qua = _run_once(clip, bbox, size, every, args.frames, args.device, args.timeout)
                runs[(size, every)].append(ket_qua)
                nhan = "LỖI: " + ket_qua["loi"] if ket_qua.get("loi") else (
                    f"fps {ket_qua.get('measured_fps')} · mask {ket_qua.get('vos_fps')} · "
                    f"vos {ket_qua.get('vos_ms')} ms · age_n {ket_qua.get('age_n')}")
                print(f"[{size}/{every}] lần {lan + 1}/{args.lan}: {nhan}", flush=True)

    bang = tong_hop(None, sizes, evers, runs)
    from scripts.measure_watchdog import _git_provenance

    rev, dirty, dirty_code, git_loi = _git_provenance()
    meta = {
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "lenh": " ".join(sys.argv),
        "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code, "git_loi": git_loi,
        "clip": str(clip.relative_to(_REPO_ROOT)) if clip.is_relative_to(_REPO_ROOT) else str(clip),
        "bbox_xywh": list(bbox), "so_lan": args.lan, "frames_moi_lan": args.frames,
        "device": args.device,
        "moi_truong": f"{args.device}, checkpoint theo configs/default.yaml, "
                      f"clip {Path(args.clip).name}",
    }
    # `git_*` ở TOP LEVEL: quy ước artifact của repo (AGENTS §6) và
    # `tests/test_so_lieu_bao_cao.py` đọc đúng các khoá đó — để trong `meta` thì artifact trông
    # "không có provenance" dù có.
    payload = {**{k: meta[k] for k in ("git_rev", "git_dirty", "git_dirty_code", "git_loi")},
               "meta": meta, "cau_hinh": bang,
               "cot": [{"khoa": k, "nhan": nhan, "cam_trich_thanh": cam} for k, nhan, cam in COT]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[bang] artifact: {out}")

    md = bang_markdown(meta, bang, sizes, evers)
    if args.md:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md, encoding="utf-8")
        print(f"[bang] bảng: {md_path}")
    print()
    print(md)
    if git_loi:
        print(f"[bang] CẢNH BÁO: không lấy được provenance ({git_loi}) — số không truy được về commit")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
