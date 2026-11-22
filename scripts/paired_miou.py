"""
So sánh CẶP `mIoU` giữa hai cấu hình trên CÙNG những frame GT.

Vì sao cần công cụ riêng: so hai giá trị trung bình của hai lần chạy cần một **ngưỡng nhiễu** cho
mIoU — mà repo CHƯA đo được ngưỡng đó (mọi lần trích trước đây đều mượn của `drift_iou` hoặc của
`iou_mean` hộp-vs-GT, tức đại lượng khác). So sánh **theo cặp** (frame 0 của A vs frame 0 của B, ...)
loại bỏ phương sai GIỮA các frame — thứ chi phối mọi so sánh trung bình — nên trả lời được câu hỏi
"cấu hình B có tốt hơn A trên chính clip này không" mà không cần ngưỡng mượn.

Cách dùng:
    python scripts/paired_miou.py --a data/lan1.json --b data/lan2.json --size-a 192 --size-b 320

Đọc kết quả cho đúng (AGENTS §6):
- `n` là số FRAME có mặt ở CẢ HAI cấu hình. 8 frame là RẤT ít: sign test chỉ đạt p < 0,05 khi 8/8
  frame cùng dấu (p = 0,0078); 7/8 cho p = 0,070 — **biên**, chưa đủ để tuyên bố.
- Các frame trong một clip **không độc lập** (cùng vật, cùng camera) ⇒ p-value là chỉ báo, không phải
  bằng chứng thống kê cứng; muốn chắc thì phải lặp 3 lần/cấu hình.
- CI bootstrap ở đây lấy mẫu LẠI trên các frame ⇒ cũng chịu hạn chế đó. Nó dùng để trả lời "khoảng
  chênh lệch có bắc qua 0 không", không phải "xác suất B tốt hơn A".
"""

import argparse
import json
import random
import sys
from math import comb
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def doc_artifact(path: Path) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(d.get("ket_qua"), list):
        raise SystemExit(f"[loi] {path}: không có `ket_qua` dạng list")
    return d


def tim_dong(art: dict, size: int) -> dict:
    for r in art["ket_qua"]:
        if r.get("image_size") == size:
            if "ma_thoat" in r:
                raise SystemExit(f"[loi] dòng image_size={size} là dòng LỖI: {r.get('status_message')}")
            return r
    co = [r.get("image_size") for r in art["ket_qua"]]
    raise SystemExit(f"[loi] không có image_size={size} trong artifact (có: {co})")


def cap_frame(dong_a: dict, dong_b: dict, gt: str) -> list[tuple[int, float, float]]:
    """Các frame có IoU ở CẢ HAI cấu hình (bỏ frame GT rỗng / thiếu mask)."""
    def _lay(dong):
        ct = (dong.get("chi_tiet") or {}).get(gt)
        if ct is None:
            raise SystemExit(f"[loi] không có GT {gt!r} trong dòng image_size={dong['image_size']}")
        ra = {}
        for item in ct["frames"]:
            # `schema 1`: cặp [idx, iou]; `schema 2`: dict của `score_miou.cham`.
            idx, iou = (item[0], item[1]) if isinstance(item, (list, tuple)) else (item["frame_idx"], item.get("iou"))
            if iou is not None:
                ra[int(idx)] = float(iou)
        return ra

    a, b = _lay(dong_a), _lay(dong_b)
    chung = sorted(set(a) & set(b))
    return [(i, a[i], b[i]) for i in chung]


def sign_test_hai_phia(so_duong: int, n: int) -> float:
    """p-value CHÍNH XÁC của sign test hai phía (bỏ các cặp chênh lệch đúng bằng 0)."""
    if n <= 0:
        return float("nan")
    duoi = sum(comb(n, i) for i in range(0, so_duong + 1))
    tren = sum(comb(n, i) for i in range(so_duong, n + 1))
    return min(1.0, 2.0 * min(duoi, tren) / (2 ** n))


def bootstrap_ci(diffs: list[float], *, so_lan: int = 20000, seed: int = 0) -> tuple[float, float]:
    """CI95 của TRUNG BÌNH chênh lệch, lấy mẫu lại trên các frame."""
    if not diffs:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(diffs)
    tb = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(so_lan))
    return tb[int(0.025 * so_lan)], tb[int(0.975 * so_lan) - 1]


def so_sanh(dong_a: dict, dong_b: dict, gt: str) -> dict:
    cap = cap_frame(dong_a, dong_b, gt)
    diffs = [b - a for _, a, b in cap]
    n = len(diffs)
    so_duong = sum(1 for d in diffs if d > 0)
    lo, hi = bootstrap_ci(diffs)
    return {
        "gt": gt, "n": n, "so_duong": so_duong,
        "mean": round(sum(diffs) / n, 4) if n else None,
        "median": round(sorted(diffs)[n // 2], 4) if n else None,
        "ci95": [round(lo, 4), round(hi, 4)],
        "p_sign": round(sign_test_hai_phia(so_duong, n), 4),
        "chi_tiet_frame": [{"frame_idx": i, "a": round(a, 4), "b": round(b, 4),
                            "chenh": round(b - a, 4)} for i, a, b in cap],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="So sánh CẶP mIoU giữa hai cấu hình trên cùng frame GT")
    ap.add_argument("--a", required=True, help="artifact của cấu hình A (baseline)")
    ap.add_argument("--b", required=True, help="artifact của cấu hình B")
    ap.add_argument("--size-a", type=int, required=True)
    ap.add_argument("--size-b", type=int, required=True)
    ap.add_argument("--gt", default="", help="tên bộ GT (mặc định: mọi bộ có trong cả hai)")
    args = ap.parse_args(argv)

    art_a, art_b = doc_artifact(Path(args.a)), doc_artifact(Path(args.b))
    dong_a, dong_b = tim_dong(art_a, args.size_a), tim_dong(art_b, args.size_b)
    gts = [args.gt] if args.gt else [g for g in (dong_a.get("chi_tiet") or {})
                                    if g in (dong_b.get("chi_tiet") or {})]
    if not gts:
        print("[loi] không có bộ GT nào chung giữa hai artifact")
        return 2

    print(f"A = image_size {args.size_a} ({dong_a.get('ms_moi_frame')} ms/frame) · "
          f"B = image_size {args.size_b} ({dong_b.get('ms_moi_frame')} ms/frame)")
    print(f"{'GT':<12} {'n':>3} {'B>A':>5} {'mean':>8} {'median':>8} {'CI95':>20} {'p_sign':>7}")
    for gt in gts:
        r = so_sanh(dong_a, dong_b, gt)
        if not r["n"]:
            print(f"{gt:<12} {0:>3} {'—':>5} {'—':>8} {'—':>8} {'—':>20} {'—':>7}")
            continue
        ci = f"[{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}]"
        print(f"{gt:<12} {r['n']:>3} {r['so_duong']:>3}/{r['n']:<2} {r['mean']:>+8.4f} "
              f"{r['median']:>+8.4f} {ci:>20} {r['p_sign']:>7.4f}")
        if args.gt and r["n"]:
            print("   từng frame:", ", ".join(f"{f['frame_idx']}:{f['chenh']:+.3f}"
                                              for f in r["chi_tiet_frame"]))

    print("\nĐọc cho đúng: n = số FRAME chung (8 là rất ít; sign test cần 8/8 cùng dấu mới p<0,05). "
          "Các frame trong một clip KHÔNG độc lập ⇒ p-value là chỉ báo, muốn chắc phải lặp 3 lần/cấu "
          "hình. CI bắc qua 0 ⇒ KHÔNG kết luận được.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
