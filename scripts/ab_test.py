"""
A/B CÓ KIỂM ĐỊNH NHIỄU (việc #11 của plan): so hai cấu hình bằng cách chạy CHEN KẼ rồi so chênh lệch
với độ lệch chuẩn giữa các lần — dưới ngưỡng thì in **"không phân biệt được"**.

Vì sao phải chèn kẽ (A,B,A,B,…) chứ không chạy 3 lần A rồi 3 lần B: máy này chạy nền (torch thread,
CPU tăng nhiệt, cache checkpoint) ⇒ chạy liền một cấu hình dễ "ăn" cả một giai đoạn thuận lợi và tạo
ra chênh lệch không có thật. Chèn kẽ làm hai cấu hình chịu CÙNG một điều kiện trung bình.

Chức năng: `--a` và `--b` nhận `khoá=giá_trị` (image_size, vos_every, mask_smoothing), chạy xen kẽ
           `--lan` vòng, rồi in bảng: mean ± std mỗi bên, chênh lệch, ngưỡng nhiễu, KẾT LUẬN.
Input  : --clip, --bbox (x,y,w,h), --a, --b, --lan (>=3 khuyến nghị), --frames, --device, --out.
Output : artifact JSON (git_rev top level) + bảng ra stdout.
Lưu ý  : kết luận chỉ có 3 giá trị: "A tốt hơn", "B tốt hơn", "không phân biệt được".
         CẤM đọc bảng này thành độ chính xác — đây là tốc độ/độ trễ, không phải bám đúng
         (`scripts/score_miou.py` mới là thước đo bám đúng).
"""

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.bang_cau_hinh import _run_once  # noqa: E402 — dùng lại đúng đường chạy worker

# Khoá có thể đổi trong A/B + khoảng giá trị hợp lệ (kiểm ở cửa vào, không để worker báo sau 4 s nạp).
HOP_LE = {
    "image_size": (64, 1024),
    "vos_every": (1, 1000),
    "mask_smoothing": (0.05, 1.0),
}
METRIC = [("measured_fps", "FPS phát", 1), ("vos_fps", "Nhịp mask", 1),
          ("vos_ms", "vos_ms", -1), ("mask_age_p95", "Tuổi mask p95", -1)]
# `uu_tien`: +1 = số LỚN tốt hơn, -1 = số NHỎ tốt hơn (ms).

# SÀN NHIỄU TUYỆT ĐỐI theo chỉ số: khi cả 3 lần lặp TRÙNG KHÍT, `spread = 0` ⇒ ngưỡng 0 ⇒ mọi chênh
# lệch 0,1 thành "tốt hơn". Đã xảy ra thật: `measured_fps` 29,9 vs 29,8 bị kết luận "A tốt hơn".
SAN_NHIEU = {"measured_fps": 0.5, "vos_fps": 0.2, "vos_ms": 3.0, "mask_age_p95": 5.0}

# Chỉ số bị CHẶN TRẦN bởi thiết kế (`--max-fps 30`): chênh lệch quanh trần là nhiễu lượng tử, không
# phải hiệu năng ⇒ in số nhưng CẤM kết luận thắng/thua.
BI_CHAN_TRAN = {"measured_fps"}


def parse_cau_hinh(text: str) -> dict:
    """`"image_size=192,vos_every=3"` → dict (đã kiểm khoảng giá trị). Ném `ValueError` nếu sai."""
    out = {}
    for part in str(text).replace(";", ",").split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise ValueError(f"'{part}' phải có dạng khoá=giá_trị")
        key, raw = (v.strip() for v in part.split("=", 1))
        if key not in HOP_LE:
            raise ValueError(f"khoá {key!r} không hỗ trợ (chọn trong {sorted(HOP_LE)})")
        low, high = HOP_LE[key]
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{key}: {raw!r} không phải số") from exc
        if not low <= value <= high:
            raise ValueError(f"{key}={value} ngoài khoảng [{low}, {high}]")
        out[key] = int(value) if key != "mask_smoothing" else value
    if not out:
        raise ValueError("cấu hình rỗng")
    return out


def so_sanh(a_values, b_values, uu_tien: int = 1, key: str | None = None) -> dict:
    """So hai dãy số: mean ± std mỗi bên, độ tản, **ngưỡng nhiễu**, kết luận.

    Ngưỡng nhiễu = `max(spread_a, spread_b, SAN_NHIEU[key])` với `spread = max − min` (lấy từ
    `scripts/repeatability.py` — một định nghĩa nhiễu cho cả repo).

    Vì sao cần **sàn tuyệt đối**: khi 3 lần lặp trùng khít, `spread = 0` ⇒ ngưỡng 0 ⇒ "29,9 vs 29,8
    fps" thành "A tốt hơn" (đã xảy ra trong artifact 14-11). Và `measured_fps` bị chặn trần
    `--max-fps` nên mọi chênh lệch quanh trần là nhiễu lượng tử ⇒ **cấm kết luận**.

    `n < 2` ở một bên ⇒ "không kết luận được" (không được coi là "bằng nhau").
    """
    from scripts.repeatability import la_khac_biet, spread

    ca = [float(v) for v in a_values if isinstance(v, (int, float))]
    cb = [float(v) for v in b_values if isinstance(v, (int, float))]
    san = SAN_NHIEU.get(key or "", 0.0)
    if len(ca) < 2 or len(cb) < 2:
        return {"mean_a": ca[0] if ca else None, "mean_b": cb[0] if cb else None,
                "n_a": len(ca), "n_b": len(cb), "nhieu": None, "chenh_lech": None,
                "ket_luan": "không kết luận được (n < 2)"}
    ma, mb = statistics.fmean(ca), statistics.fmean(cb)
    sa = statistics.stdev(ca)
    sb = statistics.stdev(cb)
    ta, tb = spread(ca), spread(cb)
    nhieu = max(ta["spread"], tb["spread"], san)
    chenh = mb - ma
    if key in BI_CHAN_TRAN:
        ket_luan = "không kết luận được (chỉ số bị chặn trần --max-fps, chênh lệch là nhiễu lượng tử)"
    elif not la_khac_biet(ma, mb, nhieu, n=min(len(ca), len(cb))):
        ket_luan = "không phân biệt được (chênh lệch nằm trong nhiễu)"
    elif (chenh > 0) == (uu_tien > 0):
        ket_luan = "B tốt hơn"
    else:
        ket_luan = "A tốt hơn"
    return {"mean_a": round(ma, 2), "std_a": round(sa, 2), "spread_a": ta["spread"], "n_a": len(ca),
            "mean_b": round(mb, 2), "std_b": round(sb, 2), "spread_b": tb["spread"], "n_b": len(cb),
            "nhieu": round(nhieu, 2), "san_nhieu": san, "chenh_lech": round(chenh, 2),
            "ket_luan": ket_luan}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="A/B có kiểm định nhiễu (chạy chèn kẽ).")
    parser.add_argument("--clip", default="data/binh1.mp4")
    parser.add_argument("--bbox", required=True)
    parser.add_argument("--a", required=True, help='vd "image_size=192,vos_every=3"')
    parser.add_argument("--b", required=True, help='vd "image_size=320,vos_every=3"')
    parser.add_argument("--lan", type=int, default=3)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    try:
        cfg_a, cfg_b = parse_cau_hinh(args.a), parse_cau_hinh(args.b)
    except ValueError as exc:
        print(f"[LOI] {exc}")
        return 2
    if cfg_a == cfg_b:
        print("[LOI] A và B giống hệt nhau — không có gì để so")
        return 2
    if args.lan < 2:
        print(f"[LOI] --lan {args.lan}: cần >= 2 (n=1 thì không có nhiễu ⇒ không kết luận được)")
        return 2
    bbox = tuple(int(v) for v in args.bbox.split(","))
    if len(bbox) != 4 or bbox[2] <= 0 or bbox[3] <= 0:
        print(f"[LOI] --bbox phải là x,y,w,h với w,h > 0; nhận {args.bbox!r}")
        return 2
    clip = Path(args.clip) if Path(args.clip).is_absolute() else _REPO_ROOT / args.clip
    if not clip.is_file():
        print(f"[LOI] không thấy clip {clip}")
        return 2

    base = {"image_size": 192, "vos_every": 3, "mask_smoothing": 1.0}
    runs = {"a": [], "b": []}
    for vong in range(args.lan):
        for nhan, cfg in (("a", cfg_a), ("b", cfg_b)):
            tham_so = {**base, **cfg}
            kq = _run_once(clip, bbox, tham_so["image_size"], tham_so["vos_every"],
                           args.frames, args.device, args.timeout,
                           mask_smoothing=tham_so["mask_smoothing"])
            runs[nhan].append(kq)
            noi_dung = kq.get("loi") or f"fps {kq.get('measured_fps')} · mask {kq.get('vos_fps')}"
            print(f"[vòng {vong + 1}/{args.lan}] {nhan.upper()} {cfg}: {noi_dung}", flush=True)

    ket_qua = {}
    for key, nhan, uu_tien in METRIC:
        so_a = [r.get(key) for r in runs["a"] if not r.get("loi")]
        so_b = [r.get(key) for r in runs["b"] if not r.get("loi")]
        ket_qua[key] = {"nhan": nhan, **so_sanh(so_a, so_b, uu_tien, key=key)}

    from scripts.measure_watchdog import _git_provenance

    rev, dirty, dirty_code, git_loi = _git_provenance()
    payload = {
        "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code, "git_loi": git_loi,
        "meta": {
            "do_luc": datetime.now().isoformat(timespec="seconds"),
            "lenh": " ".join(sys.argv),
            "clip": str(clip.relative_to(_REPO_ROOT)) if clip.is_relative_to(_REPO_ROOT) else str(clip),
            "bbox_xywh": list(bbox), "device": args.device, "lan": args.lan,
            "frames_moi_lan": args.frames, "a": cfg_a, "b": cfg_b,
            "cach_chay": "chèn kẽ A,B,A,B,… (cùng điều kiện trung bình cho cả hai bên)",
            "nguong_nhieu": "max(spread_a, spread_b, san_nhieu[key]) với spread = max−min "
                            "(scripts/repeatability.py) + sàn tuyệt đối theo chỉ số; chênh lệch <= "
                            "ngưỡng ⇒ KHÔNG PHÂN BIỆT ĐƯỢC",
            "bi_chan_tran": sorted(BI_CHAN_TRAN),
        },
        "ket_qua": ket_qua,
        "lan_chay": {"a": runs["a"], "b": runs["b"]},
    }
    out = Path(args.out) if args.out else (
        _REPO_ROOT / "data" / f"ab_{datetime.now():%Y-%m-%d_%H%M}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nA = {cfg_a}\nB = {cfg_b}\n")
    print("| chỉ số | A | B | chênh lệch | nhiễu | kết luận |")
    print("|---|---|---|---|---|---|")
    for key, nhan, _uu in METRIC:
        kq = ket_qua[key]
        if kq["mean_a"] is None or kq["mean_b"] is None:
            print(f"| {nhan} | — | — | — | — | {kq['ket_luan']} |")
            continue
        a_txt = f"{kq['mean_a']:g} ± {kq['std_a']:g}"
        b_txt = f"{kq['mean_b']:g} ± {kq['std_b']:g}"
        print(f"| {nhan} | {a_txt} | {b_txt} | {kq['chenh_lech']:+g} | {kq['nhieu']:g} | "
              f"{kq['ket_luan']} |")
    print(f"\n[ab] artifact: {out}")
    loi_a = sum(1 for r in runs["a"] if r.get("loi"))
    loi_b = sum(1 for r in runs["b"] if r.get("loi"))
    if loi_a or loi_b:
        print(f"[ab] lần chạy LỖI: A {loi_a}/{args.lan} · B {loi_b}/{args.lan} "
              "— lỗi KHÔNG bị bỏ qua khỏi kết luận (n_a/n_b trong artifact)")
    if loi_a >= args.lan and loi_b >= args.lan:
        print("[ab] KHÔNG ĐO ĐƯỢC lần nào ở cả hai bên ⇒ thất bại, không phải 'không phân biệt được'")
        return 1
    if git_loi:
        print(f"[ab] CẢNH BÁO: không lấy được provenance ({git_loi})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
