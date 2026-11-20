"""A/B **ô NGƯỜI XEM THẤY vs GT người tô** — phép đo trả lời được `max_mad` (ticket #38).

Vì sao phải có phép đo này (phát hiện 20-11): `mIoU` **không** dùng được để chọn `max_mad` — muốn chấm
mIoU hợp lệ phải chạy `--vos-every 1`, mà cấu hình đó **tắt hẳn LK** ⇒ `max_mad` không tham gia phép đo.
Còn `drift_iou` chỉ nói ô hiển thị có khớp **ô VOS** hay không (độ tự nhất quán), không nói ô đó có đúng
**vật** hay không.

Phép đo ở đây: hộp bao suy từ **mask người tô** (`docs/gt/<tên>`) = vị trí thật của vật; ô mà pipeline
**vẽ lên HUD** ở đúng frame đó (`--dump-shown-csv`) là thứ người xem thấy. `IoU(ô hiển thị, ô GT)` mới là
"ô bám có đúng chỗ không".

Cách chạy được CHÈN KẼ (a,b,a,b,a,b) và đảo thứ tự vòng lẻ — chạy liền 3 lần A rồi 3 lần B thì chênh
lệch nhiệt/cache bị quy oan cho cấu hình (bài học `./run ab`, AGENTS §6).

    python scripts/ab_o_hien_thi_vs_gt.py --gt docs/gt/b1 --clip data/binh1.mp4 \\
        --bbox 300,275,150,410 --lan 3 --max-mad 1.5 6.0

Quy tắc đọc số (giống mọi phép đo khác của repo): chênh lệch **< độ lệch chuẩn giữa các lần chạy** ⇒
viết "không phân biệt được", không viết "tốt hơn". Frame GT **rỗng** (không có vật) ⇒ **không chấm**.
Frame GT có vật mà pipeline không vẽ ô nào ⇒ IoU **0,0** (bám sai thật), KHÔNG phải "không đo được".
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.live_tracking import _bbox_iou                        # noqa: E402

SHOWN_HEADER = ("frame_idx", "x1", "y1", "x2", "y2", "lk_ok")


def hop_tu_gt(gt_dir: Path) -> dict[int, tuple[int, int, int, int]]:
    """`frame → hộp bao (x1,y1,x2,y2)` suy từ mask NGƯỜI tô. Bỏ frame `gt_rong` (không có vật)."""
    import cv2

    index = json.loads((gt_dir / "index.json").read_text(encoding="utf-8"))
    rong = {int(f) for f in (index.get("gt_rong") or [])}
    ra = {}
    for path in sorted(gt_dir.glob("gt_*.png")):
        frame = int(path.stem.split("_")[-1])
        if frame in rong:
            continue
        mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            continue
        ys, xs = (mask > 127).nonzero()
        if len(xs) == 0:      # mask rỗng mà KHÔNG khai `gt_rong`: mâu thuẫn ⇒ bỏ, không chấm bừa
            continue
        ra[frame] = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    return ra


KHONG_CO_O = "khong_co_o"      # sentinel: frame đó KHÔNG có ô nào hiển thị (khác "ô hỏng")
O_HONG = "o_hong"              # sentinel: có ghi toạ độ nhưng không dùng được (đảo/âm)


def doc_shown(path: Path) -> dict[int, tuple[object, bool] | tuple[tuple[int, int, int, int], bool]]:
    """`frame → (ô | KHONG_CO_O | O_HONG, lk_ok)` từ `--dump-shown-csv`.

    Ba trạng thái phải KHÁC nhau (bẫy "0/None" của AGENTS §6):
      - 4 cột rỗng ⇒ **không có ô nào hiển thị** (`KHONG_CO_O`) — chấm `0,0` vì GT có vật mà màn hình
        không có hộp = bám sai thật;
      - toạ độ đảo/âm ⇒ **ô hỏng** (`O_HONG`) — KHÔNG chấm được, phải là `None` chứ không phải `0,0`
        (quy thành 0,0 là tự làm điểm mình thấp đi một cách giả tạo);
      - còn lại ⇒ ô `(x1,y1,x2,y2)`; hộp MỎNG 1 px vẫn hợp lệ (repo coi là vật thật ở xa).
    """
    ra = {}
    if not path.exists():
        return ra
    trung = []          # frame_idx trùng ⇒ dòng sau ghi đè dòng trước (im lặng) — phải nói ra
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                frame = int(row["frame_idx"])
            except (KeyError, TypeError, ValueError):
                continue
            try:
                box = tuple(int(row[k]) for k in ("x1", "y1", "x2", "y2"))
            except (KeyError, TypeError, ValueError):
                box = None
            if box is None:
                box = KHONG_CO_O
            elif box[2] < box[0] or box[3] < box[1] or box[0] < 0 or box[1] < 0:
                box = O_HONG
            if frame in ra:
                trung.append(frame)
            ra[frame] = (box, str(row.get("lk_ok", "")).strip() == "1")
    if trung:
        print(f"[canh-bao] shown.csv có frame_idx TRÙNG {len(trung)} lần (vd {sorted(set(trung))[:5]}) "
              "— dòng sau ghi đè dòng trước, số của các frame đó không đáng tin", flush=True)
    return ra


def cham(hop_gt: dict, shown: dict) -> dict:
    """Chấm `IoU(ô hiển thị, ô GT)`. Hàm THUẦN (test được, không cần video/model).

    Ba ca phải tách:
      - GT có vật, **không có ô hiển thị** ⇒ `iou = 0.0` (bám sai thật) — KHÔNG bỏ mẫu;
      - GT có vật, ô HỎNG (đảo/âm) ⇒ `None` + đếm `khong_do_duoc` (không quy thành 0);
      - frame GT có vật **không xuất hiện** trong CSV ⇒ `thieu_frame` (chưa chạy tới frame đó).
    """
    theo_frame, thieu = [], []
    khong_do = 0
    for frame, gt in sorted(hop_gt.items()):
        if frame not in shown:
            thieu.append(frame)
            continue
        box, lk_ok = shown[frame]
        if box is KHONG_CO_O:
            theo_frame.append({"frame_idx": frame, "iou": 0.0, "lk_ok": lk_ok,
                               "vi_sao": "không có ô hiển thị ⇒ 0,0 (bám sai thật)"})
            continue
        if box is O_HONG:
            khong_do += 1
            theo_frame.append({"frame_idx": frame, "iou": None, "lk_ok": lk_ok,
                               "vi_sao": "ô hỏng (đảo/âm toạ độ) ⇒ không đo được"})
            continue
        iou = _bbox_iou(box, gt)
        if iou is None:
            theo_frame.append({"frame_idx": frame, "iou": None, "lk_ok": lk_ok,
                               "vi_sao": "ô suy biến ⇒ không đo được"})
            continue
        theo_frame.append({"frame_idx": frame, "iou": round(float(iou), 4), "lk_ok": lk_ok,
                           "hop": list(box), "hop_gt": list(gt)})
    do_duoc = [r["iou"] for r in theo_frame if r["iou"] is not None]
    return {
        "n_gt_co_vat": len(hop_gt),
        "n_cham": len(do_duoc),
        "khong_do_duoc": khong_do,
        "thieu_frame": thieu,
        "iou_mean": round(statistics.fmean(do_duoc), 4) if do_duoc else None,
        "iou_min": round(min(do_duoc), 4) if do_duoc else None,
        "lk_ok_frac": (round(sum(1 for r in theo_frame if r["lk_ok"]) / len(theo_frame), 3)
                       if theo_frame else None),
        "theo_frame": theo_frame,
    }


def _python() -> str:
    return sys.executable or "python3"


def chay_mot_lan(*, clip: str, bbox: str, image_size: int | None, vos_every: int,
                 max_mad: float, frames: int, out_dir: Path) -> dict:
    lenh = [_python(), str(REPO_ROOT / "tools" / "live_worker.py"),
            "--source", clip, "--out-dir", str(out_dir),
            "--vos-every", str(vos_every), "--stop-after-frames", str(frames),
            "--lk-max-mad", str(max_mad), "--bbox", bbox,
            "--dump-shown-csv", str(out_dir / "shown.csv")]
    if image_size is not None:
        lenh += ["--image-size", str(image_size)]
    proc = subprocess.run(lenh, cwd=str(REPO_ROOT), check=False,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    status_path = out_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    # Lần chạy HỎNG (worker chết / nạp model lỗi) không được coi là "bám sai thật": khi đó không có
    # `shown.csv` ⇒ mọi frame GT sẽ thành 0,0 và cấu hình đó bị chấm oan. Ghi lại mã thoát + state để
    # `main` LOẠI khỏi trung bình và thoát khác 0 (bẫy "0/None ≠ đã đo", AGENTS §6).
    return {"status": status, "shown": out_dir / "shown.csv", "lenh": " ".join(lenh),
            "ma_thoat": proc.returncode, "state": status.get("state", ""),
            "so_dong_shown": (sum(1 for _ in out_dir.joinpath("shown.csv").open(encoding="utf-8"))
                              if (out_dir / "shown.csv").exists() else 0)}


def so_dong_khop_frame(res: dict) -> bool:
    """`shown.csv` có đúng **1 dòng mỗi frame đã phát** không — hàm THUẦN.

    `status["frames"]` = số frame ĐÃ PHÁT; CSV phải có đúng ngần ấy dòng dữ liệu (trừ dòng tiêu đề).
    Lệch nghĩa là có frame không được ghi (mất mẫu) hoặc ghi trùng — cả hai đều làm `IoU` tính trên một
    tập frame khác tập đã phát, mà không ai thấy.
    """
    so_frame_phat = int((res.get("status") or {}).get("frames") or 0)
    return so_frame_phat > 0 and int(res.get("so_dong_shown") or 0) - 1 == so_frame_phat


def lan_chay_hop_le(res: dict) -> bool:
    """Lần chạy có dùng được không — hàm THUẦN (test được).

    Điều kiện: mã thoát 0, `state` ∈ {`stopped`, `done`}, và CSV ô-hiển-thị có ít nhất 1 dòng dữ liệu.
    """
    if int(res.get("ma_thoat") or 0) != 0:
        return False
    if str(res.get("state", "")) not in ("stopped", "done"):
        return False
    return int(res.get("so_dong_shown") or 0) > 1        # >1 vì có dòng tiêu đề


def tong_hop(lan: list[dict]) -> dict:
    """Trung bình ± độ lệch chuẩn qua các lần chạy của CÙNG cấu hình."""
    def _stats(values):
        v = [x for x in values if x is not None]
        if not v:
            return {"mean": None, "std": None, "n": 0}
        return {"mean": round(statistics.fmean(v), 4),
                "std": round(statistics.stdev(v), 4) if len(v) > 1 else None, "n": len(v)}

    return {
        "iou_mean": _stats([r["cham"]["iou_mean"] for r in lan]),
        "iou_min": _stats([r["cham"]["iou_min"] for r in lan]),
        "lk_ok_frac": _stats([r["cham"]["lk_ok_frac"] for r in lan]),
        "n_cham": _stats([r["cham"]["n_cham"] for r in lan]),
        "measured_fps": _stats([r["status"].get("measured_fps") for r in lan]),
    }


def danh_sach_cau_hinh(image_sizes, vos_everys, max_mads) -> dict:
    """Tích ĐỀ CÁC: `{("192/1/1.5"): (192, 1, 1.5), …}` — dựng MỘT chỗ rồi cả vòng chạy lẫn nhãn dùng lại.

    Vì sao phải là hàm riêng: bản đầu dựng khoá cấu hình ở 2 nơi (vòng chạy và bảng tổng hợp) ⇒ thêm
    trục `vos_every` thì một chỗ quên ⇒ `KeyError: (192, 1.5)` **chỉ lộ khi có > 1 giá trị** (chạy 1 giá
    trị vẫn xanh). Test `test_danh_sach_cau_hinh_...` khoá đúng chỗ này.
    """
    ra = {}
    for sz in image_sizes:
        for ve in vos_everys:
            for m in max_mads:
                ra[f"{sz}/{ve}/{m}"] = (sz, ve, m)
    return ra


def thu_tu_vong(cau_hinh: dict, vong: int) -> list:
    """Nhãn cấu hình của vòng `vong` (0-based); vòng LẺ đảo chiều.

    Đảo chiều để "chạy sau" không luôn là cấu hình được ưu ái (thiên lệch do thứ tự chạy).
    """
    nhan = list(cau_hinh)
    return nhan[::-1] if vong % 2 == 1 else nhan


def cau_hinh_lech(lan: list[dict]) -> tuple[list[dict], list[dict]]:
    """Lần chạy có cấu hình HIỆU LỰC khác yêu cầu. Hàm THUẦN → `(lech, chua_kiem_duoc)`.

    Ba trạng thái của `image_size` KHÔNG được lẫn (AGENTS §6):
    - số == yêu cầu ⇒ đã khớp;
    - số != yêu cầu ⇒ **LỖI** (model chạy cỡ khác ⇒ số đo không phải của cờ đã truyền);
    - `None` ⇒ **CHƯA KIỂM ĐƯỢC** (worker bản cũ không khai) — trả riêng, KHÔNG gộp vào "khớp":
      `lech == []` không được đọc thành "cấu hình đã đúng".
    """
    lech, chua = [], []
    for r in lan:
        mad = r.get("max_mad_hieu_luc")
        if mad is None or abs(float(mad) - float(r["max_mad_yeu_cau"])) > 1e-9:
            lech.append(r)
            continue
        hieu = r.get("image_size_hieu_luc")
        if hieu is None:
            chua.append(r)
        elif int(hieu) != int(r["image_size_yeu_cau"]):
            lech.append(r)
    return lech, chua


def so_sanh(a: dict, b: dict) -> dict:
    """So hai cấu hình bằng SỐ, dùng ngưỡng nhiễu = độ lệch chuẩn lớn hơn của hai bên.

    Hàm THUẦN. Chênh lệch nhỏ hơn ngưỡng ⇒ "không phân biệt được" (AGENTS §6), không viết "tốt hơn".
    """
    a_mean, b_mean = a["iou_mean"]["mean"], b["iou_mean"]["mean"]
    if a_mean is None or b_mean is None:
        return {"ket_luan": "KHÔNG kết luận: một bên không chấm được frame nào"}
    chenh = round(b_mean - a_mean, 4)
    std_a, std_b = a["iou_mean"].get("std"), b["iou_mean"].get("std")
    if std_a is None or std_b is None:
        # `std = None` nghĩa là một bên chỉ có 1 lần chạy ⇒ **không có** ngưỡng nhiễu. Coi nó là 0 sẽ
        # biến mọi chênh lệch thành "TỐT HƠN/TỆ HƠN" — đúng thứ AGENTS §6 cấm (n < 2 không kết luận).
        return {"chenh_iou": chenh, "nguong_nhieu": None, "phan_biet_duoc": None,
                "ket_luan": "KHÔNG kết luận: cần ≥ 2 lần chạy mỗi cấu hình để có ngưỡng nhiễu"}
    nhieu = max(float(std_a), float(std_b))
    phan_biet = abs(chenh) > nhieu
    return {
        "chenh_iou": chenh,
        "nguong_nhieu": round(nhieu, 4),
        "phan_biet_duoc": phan_biet,
        "ket_luan": (f"ô hiển thị {'TỐT HƠN' if chenh > 0 else 'TỆ HƠN'} {abs(chenh):.3f} IoU "
                     f"(> ngưỡng nhiễu {nhieu:.3f})" if phan_biet else
                     f"KHÔNG phân biệt được (chênh {chenh:+.3f} ≤ ngưỡng nhiễu {nhieu:.3f})"),
    }


def so_sanh_theo_cap(lan_a: list[dict], lan_b: list[dict]) -> dict:
    """So **THEO CẶP** (cùng lần chạy, cùng frame) — khử dao động giữa các lần chạy. Hàm THUẦN.

    Vì sao cần bên cạnh `so_sanh` (so trung bình): trung bình bị phương sai giữa-lần-chạy chi phối
    (đo 20-11: `std` 0,065 ở 1,5 vs 0,016 ở 6,0 ⇒ chênh 0,027 bị coi là "không phân biệt được"), trong
    khi so từng frame thì cấu hình nới chưa BAO GIỜ tệ hơn và tốt hơn rõ ở vài frame. Cặp được ghép
    theo **chỉ số lần chạy** (các lần chạy đã chèn kẽ) và theo **frame**.

    Trả `{so_cap, b_tot_hon, a_tot_hon, bang, chenh_trung_binh, chenh_lon_nhat, frame_b_tot_hon}`.
    Cặp bị bỏ khi một bên `iou` là `None` (không đo được) — không quy thành 0.
    """
    # Một bên thiếu lần chạy (vd worker chết ở lần 2) ⇒ `zip` lặng lẽ bỏ cặp ⇒ `so_cap` tụt mà không
    # ai biết. Trả cờ `can_bo_cap` để bên gọi từ chối kết luận thay vì so lệch.
    can_bo_cap = len(lan_a) != len(lan_b)
    so_cap = b_tot = a_tot = bang = 0
    chenh = []
    frame_b_tot = {}
    for ra, rb in zip(lan_a, lan_b):
        fa = {r["frame_idx"]: r["iou"] for r in ra["cham"]["theo_frame"]}
        fb = {r["frame_idx"]: r["iou"] for r in rb["cham"]["theo_frame"]}
        for frame in sorted(set(fa) & set(fb)):
            x, y = fa[frame], fb[frame]
            if x is None or y is None:
                continue
            so_cap += 1
            d = round(y - x, 4)
            chenh.append(d)
            if d > 1e-9:
                b_tot += 1
                frame_b_tot[frame] = round(frame_b_tot.get(frame, 0.0) + d, 4)
            elif d < -1e-9:
                a_tot += 1
            else:
                bang += 1
    return {
        "so_cap": so_cap, "so_lan_a": len(lan_a), "so_lan_b": len(lan_b),
        "can_bo_cap": can_bo_cap,
        "b_tot_hon": b_tot, "a_tot_hon": a_tot, "bang": bang,
        "chenh_trung_binh": round(statistics.fmean(chenh), 4) if chenh else None,
        "chenh_lon_nhat": round(max(chenh), 4) if chenh else None,
        "chenh_nho_nhat": round(min(chenh), 4) if chenh else None,
        "frame_b_tot_hon": frame_b_tot,
        "b_khong_bao_gio_te_hon": a_tot == 0 and so_cap > 0,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gt", required=True, help="thư mục GT (docs/gt/<tên>, có index.json)")
    parser.add_argument("--clip", required=True)
    parser.add_argument("--bbox", required=True, help='"x,y,w,h" (như bbox.json/UI)')
    parser.add_argument("--image-size", type=int, nargs="+", default=[192],
                        help="một hoặc nhiều giá trị ⇒ A/B CHÈN KẼ giữa các giá trị (đo 20-11: so hai "
                             "PHIÊN khác nhau là vô nghĩa — ngưỡng nhiễu đổi 0,034→0,022 và phán quyết lật)")
    parser.add_argument("--vos-every", type=int, nargs="+", default=[3],
                        help="một hoặc nhiều giá trị ⇒ A/B chèn kẽ (vos_every=1 là chạy VOS MỌI frame, "
                             "tức không có khe ⇒ trần độ chính xác; dùng làm mốc so)")
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--lan", type=int, default=3, help="số lần/cấu hình (chèn kẽ; <2 không kết luận)")
    parser.add_argument("--max-mad", type=float, nargs="+", default=[1.5, 6.0])
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    hop_gt = hop_tu_gt(Path(args.gt))
    if not hop_gt:
        raise SystemExit(f"[LOI] {args.gt} không có frame nào có vật (toàn `gt_rong`?)")
    if args.lan < 2:
        print("[CANH BAO] --lan < 2 ⇒ chưa có ngưỡng nhiễu, KHÔNG được kết luận cấu hình nào tốt hơn")

    # Khoá cấu hình = (image_size, vos_every, max_mad). `vos_every` là trục quan trọng nhất khi hỏi
    # "hybrid 30 FPS mất bao nhiêu độ chính xác so với chạy VOS mọi frame".
    cau_hinh = danh_sach_cau_hinh(args.image_size, args.vos_every, args.max_mad)
    theo_cau_hinh: dict[tuple, list] = {k: [] for k in cau_hinh.values()}
    for vong in range(args.lan):
        for nhan_ch in thu_tu_vong(cau_hinh, vong):
            sz, ve, max_mad = cau_hinh[nhan_ch]
            # KHÔNG hard-code /dev/shm: máy dev là Windows (chỉ Linux mới có) ⇒ FileNotFoundError.
            with tempfile.TemporaryDirectory(prefix=f"ab_o_{sz}_{ve}_{max_mad}_") as tmp:
                res = chay_mot_lan(clip=args.clip, bbox=args.bbox, image_size=sz,
                                   vos_every=ve, max_mad=max_mad,
                                   frames=args.frames, out_dir=Path(tmp))
                res["cham"] = cham(hop_gt, doc_shown(res["shown"]))
                cau = res["status"].get("cau_hinh") or {}
                res["max_mad_yeu_cau"] = max_mad
                res["max_mad_hieu_luc"] = cau.get("lk_max_mad")
                res["image_size_yeu_cau"] = sz
                # Ba trạng thái KHÔNG lẫn: None = CHƯA KIỂM ĐƯỢC (worker không khai), số = đo được
                res["image_size_hieu_luc"] = cau.get("image_size_hieu_luc")
                res["image_size_kiem_duoc"] = res["image_size_hieu_luc"] is not None
                res["vos_every_yeu_cau"] = ve
                res["shown"] = str(res["shown"])
                res["hop_le"] = lan_chay_hop_le(res)
                res["so_dong_khop_frame"] = so_dong_khop_frame(res)
                if res["hop_le"] and not res["so_dong_khop_frame"]:
                    print(f"[canh-bao] {sz}/{ve}/{max_mad}: shown.csv {res['so_dong_shown'] - 1} dòng "
                          f"nhưng phiên phát {res['status'].get('frames')} frame — có frame không được "
                          "ghi hoặc ghi trùng", flush=True)
            theo_cau_hinh[(sz, ve, max_mad)].append(res)
            c = res["cham"]
            print(f"vòng {vong + 1} · {sz}/{ve}/{max_mad} → IoU(ô hiển thị, ô GT) {c['iou_mean']} "
                  f"(tệ nhất {c['iou_min']}) trên {c['n_cham']}/{c['n_gt_co_vat']} frame · "
                  f"lk_ok {c['lk_ok_frac']} · hiệu lực mad {res['max_mad_hieu_luc']} · "
                  f"image_size {res['image_size_hieu_luc']}")

    # HAI chiều, tên nói rõ chiều: `tong`/`lan_chay` khoá bằng NHÃN, `theo_cau_hinh` khoá bằng TUPLE.
    # Lẫn hai chiều ⇒ `KeyError: '192/1/1.5'` (lộ đúng lúc ghi artifact, sau khi đã chạy xong 9 lần).
    nhan = {k: v for v, k in cau_hinh.items()}       # tuple → nhãn
    khoa_cua = {v: k for k, v in cau_hinh.items()}   # nhãn → tuple
    so_lan_loi = {nhan[k]: sum(1 for r in v if not r["hop_le"]) for k, v in theo_cau_hinh.items()}
    tong = {nhan[k]: tong_hop([r for r in v if r["hop_le"]]) for k, v in theo_cau_hinh.items()}
    lech, chua_kiem_duoc = cau_hinh_lech([r for v in theo_cau_hinh.values() for r in v])
    khoa = sorted(tong, key=lambda k: tuple(float(x) for x in k.split("/")))
    ss = so_sanh(tong[khoa[0]], tong[khoa[-1]]) if len(khoa) >= 2 else {}
    ss_cap = ({**so_sanh_theo_cap(theo_cau_hinh[nhan[khoa[0]]], theo_cau_hinh[nhan[khoa[-1]]]),
               "a": khoa[0], "b": khoa[-1]} if len(khoa) >= 2 else {})

    from scripts.measure_watchdog import _git_provenance

    rev, dirty, dirty_code, loi = _git_provenance()
    artifact = {
        "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code, "git_loi": loi,
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "lenh": " ".join(["python scripts/ab_o_hien_thi_vs_gt.py"] + (argv or sys.argv[1:])),
        "nguon_so": {"gt": args.gt, "clip": args.clip, "bbox": args.bbox,
                     "image_size": args.image_size, "vos_every": args.vos_every,
                     "frames": args.frames, "lan": args.lan,
                     "frame_gt_co_vat": sorted(hop_gt)},
        "dinh_nghia": ("IoU(ô bao ĐANG HIỂN THỊ ở frame đó, hộp bao suy từ mask NGƯỜI tô). GT có vật "
                       "mà không vẽ ô nào ⇒ 0,0 (bám sai thật), KHÔNG phải 'không đo được'. Đây là "
                       "phép đo 'ô bám đúng chỗ không' — khác `drift_iou` (khớp ô VOS) và khác mIoU "
                       "(mask vs GT, chỉ chạy được với vos_every=1 nên không thấy LK)."),
        "cau_hinh_hieu_luc_lech": lech,
        "image_size_chua_kiem_duoc": len(chua_kiem_duoc),
        "so_lan_chay_loi": so_lan_loi,
        "tong_hop": tong,
        "so_sanh": ss,
        "so_sanh_theo_cap": ss_cap,
        "lan_chay": {nhan[k]: [{kk: vv for kk, vv in r.items() if kk != "status"} for r in rs]
                     for k, rs in theo_cau_hinh.items()},
    }
    out = Path(args.out) if args.out else REPO_ROOT / "data" / (
        f"ab_o_hien_thi_vs_gt_{datetime.now():%Y-%m-%d}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{json.dumps(ss, ensure_ascii=False)}")
    if ss_cap:
        print(json.dumps({k: v for k, v in ss_cap.items()}, ensure_ascii=False))
    print(f"Ghi: {out}")
    if any(so_lan_loi.values()):
        print(f"[LOI] có lần chạy HỎNG (đã loại khỏi trung bình): {so_lan_loi}", file=sys.stderr)
        return 1
    if len(khoa) >= 2 and len(theo_cau_hinh[khoa_cua[khoa[0]]]) != len(theo_cau_hinh[khoa_cua[khoa[-1]]]):
        print("[LOI] hai cấu hình có SỐ LẦN CHẠY khác nhau ⇒ so theo cặp không cân", file=sys.stderr)
        return 1
    if lech:
        print(f"[LOI] {len(lech)} lần chạy có lk_max_mad hiệu lực KHÁC yêu cầu", file=sys.stderr)
        return 1
    if loi:
        print(f"[LOI] không lấy được provenance: {loi}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
