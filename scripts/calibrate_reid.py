"""
Hiệu chỉnh cổng NHẬN LẠI của re-ID vật thể — offline, từ CSV đã ghi, không chạy lại model.

Chức năng: đọc `*_metrics.csv` của `MetricsLogger`, lấy các **sự kiện nhận lại** (`reacquired=1`,
mỗi sự kiện có `(cosine, ncc)`), rồi trả lời: trên clip có nhãn này, ngưỡng nào **tách được**
ca nhận lại ĐÚNG khỏi ca nhận lại SAI?

Input  : 1 file `*_metrics.csv` + nhãn do người dùng gán bằng mắt:
           --good 10,99,150   frame của những lần nhận lại **đúng**
           --bad  20,271      frame của những lần nhận lại **sai**
           --list             chỉ in danh sách sự kiện để chọn nhãn (chạy trước)
Output : 1) **cận tách được** cho từng cue: ca sai cao nhất · ca đúng thấp nhất · điểm giữa;
         2) bảng lưới "giữ đúng / chặn sai / bỏ sót";
         3) đề xuất điểm giữa (nếu tách được) + (tuỳ chọn) JSON làm bằng chứng báo cáo.
Lưu ý  : phép quyết định dùng đúng `src.reid.accept_candidate` nên hiệu chỉnh đúng cổng hệ
         thống dùng. Thiếu ca SAI có nhãn → **không đề xuất ngưỡng** (cận trên chưa xác định);
         công cụ cũng KHÔNG biết những frame chưa từng được chấm ứng viên.

Cách dùng:
  ./run calibrate data/fast_1029-212632_metrics.csv --list
  ./run calibrate data/fast_1029-212632_metrics.csv --good 99,150 --bad 271 --json data/calib.json
"""
import argparse
import csv
import itertools
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.reid import accept_candidate   # noqa: E402

# Lưới mặc định — phủ đúng vùng số đo thật (cosine 0,59–0,98; ncc 0,39–1,00)
COS_VALUES = [round(0.50 + 0.05 * i, 2) for i in range(10)]    # 0,50 … 0,95
NCC_VALUES = [round(0.00 + 0.05 * i, 2) for i in range(19)]    # 0,00 (TẮT) … 0,90


@dataclass
class Event:
    """Một lần nhận lại: frame + điểm khớp + nhãn người dùng gán (None = chưa gán)."""

    frame_idx: int
    cosine: float
    ncc: float
    label: Optional[str] = None       # "good" | "bad" | None
    csv_idx: int = 0                  # vị trí file CSV trong danh sách đầu vào


@dataclass
class Row:
    """Kết quả một cặp ngưỡng: giữ được bao nhiêu ca đúng, lọt bao nhiêu ca sai."""

    cos_min: float
    ncc_min: float
    good_accept: int
    good_reject: int
    bad_accept: int
    bad_reject: int
    unlabeled: int


def read_reacquire_events(path) -> List[Event]:
    """Đọc CSV của MetricsLogger → các dòng `reacquired=1` (bỏ dòng thiếu cosine/ncc).

    `path` nhận 1 đường dẫn hoặc DANH SÁCH đường dẫn — gộp sự kiện của nhiều clip để hiệu
    chỉnh ngưỡng trên toàn bộ dữ liệu có nhãn (không phải từng clip rời).
    """
    paths = [path] if isinstance(path, (str, bytes)) else list(path)
    events: List[Event] = []
    for i, p in enumerate(paths):
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("reacquired") != "1":
                    continue
                try:
                    cos = float(row["reid_score"])
                    ncc = float(row["ncc"])
                except (KeyError, TypeError, ValueError):
                    print(f"[calibrate] bỏ {p} frame {row.get('frame_idx')}: thiếu cosine/ncc",
                          file=sys.stderr)
                    continue
                events.append(Event(int(row["frame_idx"]), cos, ncc, None, i))
    return events


def label_events(events: Sequence[Event], good=(), bad=()) -> List[Event]:
    """Gán nhãn: `good` = nhận lại đúng, `bad` = nhận lại sai. Còn lại để None.

    Nhãn là `frame` (1 clip) hoặc `(chỉ_số_csv, frame)` (nhiều clip — tránh nhầm frame trùng số).
    """
    def _key(item):
        return (int(item[0]), int(item[1])) if isinstance(item, (tuple, list)) else (0, int(item))

    good_set = {_key(x) for x in good}
    bad_set = {_key(x) for x in bad}
    clash = good_set & bad_set
    if clash:
        raise ValueError(f"(csv, frame) vừa là good vừa là bad: {sorted(clash)}")
    out = []
    for e in events:
        key = (e.csv_idx, e.frame_idx)
        label = "good" if key in good_set else "bad" if key in bad_set else None
        out.append(Event(e.frame_idx, e.cosine, e.ncc, label, e.csv_idx))
    return out


def _bounds(good_vals: Sequence[float], bad_vals: Sequence[float]) -> dict:
    min_good = min(good_vals) if good_vals else None
    max_bad = max(bad_vals) if bad_vals else None
    separable = (min_good is not None and max_bad is not None and max_bad < min_good)
    return {
        "min_good": min_good,
        "max_bad": max_bad,
        "separable": separable,
        "midpoint": round((max_bad + min_good) / 2, 2) if separable else None,
    }


def boundary(events: Sequence[Event]) -> dict:
    """Cận tách ngưỡng cho từng cue: ca SAI cao nhất · ca ĐÚNG thấp nhất · điểm giữa."""
    goods = [e for e in events if e.label == "good"]
    bads = [e for e in events if e.label == "bad"]
    return {
        "cosine": _bounds([e.cosine for e in goods], [e.cosine for e in bads]),
        "ncc": _bounds([e.ncc for e in goods], [e.ncc for e in bads]),
    }


def suggest(events: Sequence[Event]) -> Optional[dict]:
    """Đề xuất ngưỡng từ cận tách được. Trả None khi THIẾU một phía nhãn.

    Vì sao None: chỉ có ca sai (không có ca đúng) → không biết cận DƯỚI; chỉ có ca đúng
    (không có ca sai) → không biết cận TRÊN. Cả hai trường hợp đều chưa đủ cơ sở đề xuất.
    """
    b = boundary(events)
    if b["cosine"]["max_bad"] is None or b["cosine"]["min_good"] is None:
        return None
    return {
        "cos_min": b["cosine"]["midpoint"],     # None = không tách được bằng cosine
        "ncc_min": b["ncc"]["midpoint"],        # None = không tách được bằng ncc
        "boundary": b,
    }


def sweep(events: Sequence[Event], cos_values=COS_VALUES, ncc_values=NCC_VALUES) -> List[Row]:
    """Quét lưới ngưỡng, dùng `accept_candidate` thật để quyết định từng ca."""
    rows: List[Row] = []
    for cos_min, ncc_min in itertools.product(cos_values, ncc_values):
        good_a = good_r = bad_a = bad_r = unl = 0
        for e in events:
            if e.label is None:
                unl += 1
                continue
            accepted = accept_candidate(e.cosine, e.ncc, cos_min, ncc_min)
            if e.label == "good":
                if accepted:
                    good_a += 1
                else:
                    good_r += 1
            elif accepted:
                bad_a += 1
            else:
                bad_r += 1
        rows.append(Row(cos_min, ncc_min, good_a, good_r, bad_a, bad_r, unl))
    return rows


def frontier(rows: Sequence[Row]) -> List[Row]:
    """Với mỗi `cos_min`: cặp ngưỡng GIỮ NHIỀU CA ĐÚNG NHẤT mà không bám nhầm (ncc siết nhất).

    Gộp theo `cos_min` để bảng chỉ còn ~10 dòng biên thay vì 190 dòng trùng lặp.
    """
    by_cos: dict = {}
    for r in rows:
        if r.bad_accept != 0 or r.good_accept == 0:
            continue
        cur = by_cos.get(r.cos_min)
        if cur is None or (r.good_accept, r.ncc_min) > (cur.good_accept, cur.ncc_min):
            by_cos[r.cos_min] = r
    return sorted(by_cos.values(), key=lambda r: r.cos_min)


def _dem(events: Sequence[Event]) -> dict:
    good = sum(1 for e in events if e.label == "good")
    bad = sum(1 for e in events if e.label == "bad")
    return {"total": len(events), "good": good, "bad": bad,
            "unlabeled": len(events) - good - bad}


def _in_ds(ten: str, b: dict) -> None:
    if b["min_good"] is None:
        print(f"  {ten:<7} chưa có ca ĐÚNG có nhãn")
        return
    max_bad = "chưa có ca SAI có nhãn" if b["max_bad"] is None else f"{b['max_bad']:.3f}"
    verdict = (f"tách được → giữa = {b['midpoint']:.2f}" if b["separable"]
               else "KHÔNG tách được (chồng lấn)")
    print(f"  {ten:<7} sai cao nhất {max_bad:<22} | đúng thấp nhất {b['min_good']:.3f} "
          f"→ {verdict}")


def _in_bang(front: Sequence[Row]) -> None:
    if not front:
        print("\nKhông có cặp ngưỡng nào giữ được ca đúng mà không bám nhầm.")
        return
    print("\nBiên của lưới (bad_accept = 0, ncc siết nhất cho mỗi cosine):")
    print(f"  {'cos_min':>8} {'ncc_min':>8} {'giữ đúng':>9} {'bỏ sót':>7}")
    for r in front:
        print(f"  {r.cos_min:>8.2f} {r.ncc_min:>8.2f} {r.good_accept:>9} {r.good_reject:>7}")


def _parse_labels(text: str, n_csv: int) -> list:
    """Đọc `--good`/`--bad`: `"10,20"` (1 clip) hoặc `"0:99,1:41"` (nhiều clip).

    Nhiều CSV thì BẮT BUỘC có tiền tố chỉ số — frame trùng số giữa các clip là chuyện thường,
    nên nhãn không tiền tố sẽ gán sai clip mà không ai biết.
    """
    items = []
    for token in text.replace(" ", "").split(","):
        if not token:
            continue
        if ":" in token:
            idx_text, frame_text = token.split(":", 1)
            try:
                idx, frame = int(idx_text), int(frame_text)
            except ValueError as exc:
                raise ValueError(f"nhãn «{token}» sai định dạng (cần <chỉ-số-CSV>:<frame>)") \
                    from exc
            if not 0 <= idx < n_csv:
                raise ValueError(f"chỉ số CSV {idx} ngoài phạm vi 0..{n_csv - 1} «{token}»")
            items.append((idx, frame))
        else:
            if n_csv > 1:
                raise ValueError(
                    f"có {n_csv} file CSV → nhãn phải ghi <chỉ số CSV>:<frame>, vd 0:{token}")
            items.append(int(token))
    return items


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Quét lưới ngưỡng nhận lại re-ID từ CSV có nhãn (không cần model)")
    ap.add_argument("metrics_csv", nargs="+",
                    help="một hoặc nhiều file *_metrics.csv do MetricsLogger ghi")
    ap.add_argument("--good", default="",
                    help="nhận lại ĐÚNG: '10,99' (1 clip) hoặc '0:99,1:41' (nhiều clip)")
    ap.add_argument("--bad", default="",
                    help="nhận lại SAI: cùng định dạng với --good")
    ap.add_argument("--list", action="store_true",
                    help="chỉ in danh sách sự kiện nhận lại để chọn nhãn")
    ap.add_argument("--json", default=None, help="ghi kết quả ra JSON (bằng chứng cho báo cáo)")
    args = ap.parse_args(argv)

    def _frames(text):
        return _parse_labels(text, n_csv=len(args.metrics_csv))

    events = label_events(read_reacquire_events(args.metrics_csv),
                          good=_frames(args.good), bad=_frames(args.bad))
    dem = _dem(events)
    print(f"[calibrate] {len(args.metrics_csv)} clip: "
          f"{dem['total']} lần nhận lại | "
          f"có nhãn: đúng {dem['good']}, sai {dem['bad']} | chưa gán nhãn {dem['unlabeled']}")

    if args.list:
        print(f"\n  {'csv':>3} {'frame':>7} {'cosine':>8} {'ncc':>8}  nhãn")
        for e in events:
            print(f"  {e.csv_idx:>3} {e.frame_idx:>7} {e.cosine:>8.3f} {e.ncc:>8.3f}  {e.label or ''}")
        print("\nGán nhãn bằng mắt trên video HUD, rồi chạy lại với --good/--bad.")
        return 0

    if dem["good"] + dem["bad"] == 0:
        print("[calibrate] chưa có nhãn nào — chạy với --good/--bad (xem --list).",
              file=sys.stderr)
        return 2

    b = boundary(events)
    print("\nCận tách được từ các ca có nhãn:")
    _in_ds("cosine", b["cosine"])
    _in_ds("ncc", b["ncc"])

    if dem["good"] > 0:
        _in_bang(frontier(sweep(events)))

    s = suggest(events)
    if s is None:
        if dem["good"] == 0:
            print("\nCHƯA ĐỀ XUẤT ĐƯỢC: chưa có ca ĐÚNG nào có nhãn → cận DƯỚI chưa xác định.")
            print("  Cần gán nhãn ít nhất 1 lần nhận lại ĐÚNG (--good) rồi chạy lại.")
        else:
            print("\nCHƯA ĐỀ XUẤT ĐƯỢC: chưa có ca SAI nào có nhãn → cận TRÊN chưa xác định.")
            print("  Cần gán nhãn ít nhất 1 lần nhận lại SAI (--bad) rồi chạy lại.")
    elif s["cos_min"] is None and s["ncc_min"] is None:
        print("\nHAI CUE KHÔNG TÁCH ĐƯỢC trên clip này (ca sai cao hơn ca đúng ở cả 2).")
        print("  → Cổng điểm không đủ; dựa vào vùng tìm nở dần + xác nhận 2 frame "
              "+ kiểm chứng 2 frame.")
    else:
        print("\nĐỀ XUẤT (điểm giữa cận tách được):")
        print(f"  reid_obj_threshold: {s['cos_min']}" if s["cos_min"] is not None
              else "  reid_obj_threshold: giữ nguyên (cosine không tách được)")
        print(f"  reid_obj_ncc_min  : {s['ncc_min']}" if s["ncc_min"] is not None
              else "  reid_obj_ncc_min  : để TẮT (ncc không tách được)")

    if args.json:
        data = {
            "metrics_csv": list(args.metrics_csv),
            "dem": dem,
            "events": [asdict(e) for e in events],
            "boundary": b,
            "suggest": s,
            "frontier": [asdict(r) for r in frontier(sweep(events))] if dem["good"] else [],
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[calibrate] ghi kết quả → {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
