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



def gt_rong_cua(gt_dir: Path) -> list[int]:
    """Danh sách frame người tô khai **KHÔNG có vật** (`gt_rong` trong `index.json`).

    Tách khỏi `hop_tu_gt` để metric "vẽ ô khi không có vật" (`ty_le_o_ma`) dùng được mà không phải
    đổi kiểu trả về của `hop_tu_gt` (mọi chỗ gọi cũ vẫn là `dict`).
    """
    path = gt_dir / "index.json"
    if not path.exists():
        return []          # không khai `gt_rong` ⇒ KHÔNG có frame rỗng để chấm (khác "0 lần oan")
    index = json.loads(path.read_text(encoding="utf-8"))
    return sorted({int(f) for f in (index.get("gt_rong") or [])})


def hop_tu_gt(gt_dir: Path) -> dict[int, tuple[int, int, int, int]]:
    """`frame → hộp bao (x1,y1,x2,y2)` suy từ mask NGƯỜI tô. Bỏ frame `gt_rong` (không có vật).

    ĐỌC KÈM `gt_rong_cua()` — bỏ `gt_rong` ở đây là ĐÚNG (không có vật thì không có IoU để chấm),
    nhưng trước 21-11 không ai dùng tập đó ⇒ hành vi "vẽ ô trên frame KHÔNG có vật" **không bị phạt**.
    Đó là lý do có `ty_le_o_ma`.
    """
    import cv2

    rong = set(gt_rong_cua(gt_dir))
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


def doc_shown(path: Path) -> dict[int, tuple]:
    """`frame → (ô | KHONG_CO_O | O_HONG, lk_ok, bam)` từ `--dump-shown-csv`.

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
        reader = csv.DictReader(fh)
        # Cột `bam` chỉ có từ 21-11. KHÔNG trả 3 phần tử cho CSV cũ: `dem_o_khi_khong_bang_chung`
        # dùng độ dài tuple để biết "có cột hay không", trả 3 phần tử vô điều kiện ⇒ CSV 11 cột bị
        # đọc thành "đã đo và sạch" (`do_duoc = True`) — đúng bẫy `0/None ≠ đã đo` (review vòng 2, P1).
        co_cot_bam = "bam" in (reader.fieldnames or [])
        for row in reader:
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
            # `lk_ok` BA trạng thái (khớp writer + `drift_samples` + `docs/thuoc-do-bam-dung.md`):
            # `1` = LK ok, `0` = LK từ chối, ô TRỐNG = chưa đo (vd frame `engine.start()` từ 21-11).
            # Bản trước đọc 2 trạng thái ⇒ frame `start()` bị đếm vào `n_lk_khong` = "LK từ chối"
            # (review vòng 3, P3).
            lk_raw = str(row.get("lk_ok", "")).strip()
            lk_ok = None if lk_raw == "" else (lk_raw == "1")
            if co_cot_bam:
                # `bam` (cột 12, từ 21-11): rỗng ⇒ `None` = CHƯA ĐO, không phải "tracking".
                ra[frame] = (box, lk_ok, (row.get("bam") or "").strip() or None)
            else:
                ra[frame] = (box, lk_ok)
    if trung:
        print(f"[canh-bao] shown.csv có frame_idx TRÙNG {len(trung)} lần (vd {sorted(set(trung))[:5]}) "
              "— dòng sau ghi đè dòng trước, số của các frame đó không đáng tin", flush=True)
    return ra


# 5 cột chẩn đoán LK (ticket #39) — CSV sinh TRƯỚC 21-11 không có chúng.
COT_CHAN_DOAN = ("ly_do", "ly_do_khop", "scale", "angle_deg", "n_diem")


def doc_chan_doan(path: Path) -> tuple[dict[int, dict], list[str]]:
    """`frame → {ly_do, ly_do_khop, scale, angle_deg, n_diem}` + danh sách cột THIẾU.

    Tương thích ngược (ticket #39): CSV cũ (6 cột, trước 21-11) không có 5 cột này ⇒ trả dict rỗng +
    `thieu` = cả 5 tên, để artifact tự khai `csv_thieu_cot` thay vì im lặng đếm thành 0 (bẫy
    "0/None ≠ đã đo", AGENTS §6). `""` trong ô = **chưa đo** (không có bước LK ở frame đó) ⇒ `None`.
    """
    ra: dict[int, dict] = {}
    if not path.exists():
        return ra, list(COT_CHAN_DOAN)
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        co = set(reader.fieldnames or ())
        thieu = [c for c in COT_CHAN_DOAN if c not in co]
        for row in reader:
            try:
                frame = int(row["frame_idx"])
            except (KeyError, TypeError, ValueError):
                continue
            d = {}
            for c in COT_CHAN_DOAN:
                v = (row.get(c) or "").strip()
                if v == "":
                    d[c] = None
                elif c in ("ly_do", "ly_do_khop"):
                    d[c] = v
                elif c == "n_diem":
                    try:
                        d[c] = int(float(v))
                    except (ValueError, OverflowError):    # "inf" ⇒ OverflowError (CSV sửa tay)
                        d[c] = None
                else:
                    try:
                        d[c] = float(v)
                    except ValueError:
                        d[c] = None
            ra[frame] = d
    return ra, thieu


def chan_doan_tu_csv(path: Path) -> tuple[dict | None, list[str]]:
    """Đọc chẩn đoán LK từ `shown.csv` và **CỔNG theo CỘT THIẾU**.

    CSV sinh trước ticket #39 (6 cột) không có cột chẩn đoán ⇒ `doc_chan_doan` trả dict **không rỗng**
    nhưng toàn `None` cho mỗi frame. Đưa thẳng vào `cham()` thì `_dem` thấy "có dữ liệu" và trả `{}` =
    "đo được 0 mẫu" — SAI: phải là `None` = CHƯA ĐO (bẫy `0/None ≠ đã đo`, AGENTS §6; P1 review PR #66).
    """
    chan_doan, thieu_cot = doc_chan_doan(path)
    return (None if thieu_cot else chan_doan), thieu_cot


def ty_le_o_ma(gt_rong: list[int], shown: dict) -> dict:
    """Đếm frame **người tô khai KHÔNG có vật** mà hệ thống vẫn vẽ ô. Hàm THUẦN.

    Vì sao cần metric này: mọi chỉ số còn lại (`iou_mean`, `drift_iou`, `stability`) chỉ chấm trên
    frame **có vật** ⇒ một hệ "luôn trả lời" (vẽ ô ở đâu đó) không bị phạt. Đo 21-11: binh2 có 4 +
    b1 có 5 frame `gt_rong` = **9 mẫu** đã tô sẵn, không cần quay mới.

    Quy tắc chấm (cùng tinh thần `docs/thuoc-do-bam-dung.md`):
      - frame `gt_rong` **không có trong CSV** ⇒ `thieu_frame` (chưa chạy tới), KHÔNG tính là "không vẽ ô";
      - `KHONG_CO_O` ⇒ ngoan (không vẽ ô);
      - `O_HONG` / có toạ độ ⇒ **vẽ ô trên frame không có vật** ⇒ cộng vào `n_co_o_tren_rong`.
    `n` nhỏ (9) ⇒ **báo ĐẾM, không báo %**: `ty_le` chỉ để đọc kèm `n`.
    """
    thieu, co_o, khong_o, hong = [], [], [], []
    for frame in sorted(gt_rong):
        if frame not in shown:
            thieu.append(frame)
            continue
        box = shown[frame]
        box = box[0] if isinstance(box, (tuple, list)) else box     # (ô, lk_ok[, bam]) | ô | sentinel
        if box is KHONG_CO_O:
            khong_o.append(frame)
        elif box is O_HONG:
            hong.append(frame)
        else:
            co_o.append(frame)
    # Ô HỎNG (đảo/âm toạ độ) vẫn là "có vẽ một ô" ⇒ phải nằm ở TỬ SỐ. Bản nháp đầu bỏ nó khỏi cả tử
    # lẫn mẫu số ⇒ hệ vẽ ô hỏng trên frame rỗng được điểm TỐT HƠN hệ vẽ ô bình thường (P1 review 21-11).
    co_ve = len(co_o) + len(hong)
    n_cham_duoc = co_ve + len(khong_o)
    from src.drift_samples import MIN_SAMPLES as nguong   # ticket #23: MỘT ngưỡng duy nhất cho mọi `*_p05`
    return {
        "n_gt_rong": len(gt_rong),
        "n_co_o_tren_rong": len(co_o),
        "n_o_hong_tren_rong": len(hong),
        "n_khong_o_tren_rong": len(khong_o),
        "thieu_frame_rong": thieu,
        "frame_co_o_tren_rong": co_o,
        # `ty_le` = tỉ lệ frame KHÔNG có vật mà hệ vẫn vẽ ô (kể cả ô hỏng). `None` = CHƯA ĐO
        # (không phải 0,0) — AGENTS §6; và `None` cả khi n < ngưỡng, vì công bố một tỉ lệ từ 4 mẫu
        # là nói một điều mà mọi `*_p05` khác của repo từ chối nói (P2 review 21-11).
        "ty_le": (round(co_ve / n_cham_duoc, 4)
                  if n_cham_duoc and n_cham_duoc >= nguong else None),
        "ty_le_n": n_cham_duoc,
        "ty_le_nguong": nguong,
        "ty_le_du_mau": bool(n_cham_duoc >= nguong),
        "ghi_chu": ("`ty_le = None` khi chưa có frame nào chấm được HOẶC n < `ty_le_nguong` ⇒ đọc "
                    "`n_co_o_tren_rong` / `n_o_hong_tren_rong` / `n_gt_rong` (đếm, không phải tỉ lệ). "
                    "`n_o_hong_tren_rong` nằm TRONG tử số: ô hỏng vẫn là 'đã vẽ ô'"),
    }


def dem_o_khi_khong_bang_chung(rows: dict) -> dict:
    """Đếm frame **CÓ ô hiển thị** mà worker khai `bam = no_evidence` (plan 21-11 P4). Hàm THUẦN.

    Vì sao cần: trước 21-11 tiêu chí "0 frame có ô khi no_evidence" chỉ nằm trong commit message —
    không script nào đọc lại được (cột `bam` là write-only) ⇒ **không kiểm chứng được**, và tệ hơn là
    không phân biệt được "vá đã ẩn ô" với "ô vốn đã suy biến `(0,0,0,0)`" (mask rỗng luôn kéo theo bbox
    không hợp lệ ⇒ mọi frame mất dấu đều tự động không có toạ độ).

    `rows` = `frame → (ô | KHONG_CO_O | O_HONG, lk_ok, bam)` (3 phần tử) hoặc dạng 2 phần tử cũ
    (CSV cũ không có cột `bam` ⇒ `bam = None` ⇒ `n_no_evidence = 0` = **chưa đo**, không phải "sạch").
    """
    n_no_ev = 0
    co_o_khi_no_ev = []
    for frame in sorted(rows):
        row = rows[frame]
        bam = row[2] if len(row) > 2 else None
        if bam != "no_evidence":
            continue
        n_no_ev += 1
        box = row[0]
        if box is not KHONG_CO_O and (box is O_HONG or box is not None):
            co_o_khi_no_ev.append(frame)
    return {
        "n_no_evidence": n_no_ev,
        "n_co_o_khi_no_evidence": len(co_o_khi_no_ev),
        "frame_co_o_khi_no_evidence": co_o_khi_no_ev,
        # `None` = CHƯA ĐO: hoặc CSV KHÔNG có cột `bam` (11 cột), hoặc có cột mà **mọi ô đều trống**
        # (không phải "đã đo và sạch"). Chỉ `True` khi có ít nhất một giá trị thật (review vòng 3, P3:
        # bản trước chỉ kiểm "có cột" nên lùi lại đúng cái bẫy `0/None ≠ đã đo` vừa vá).
        "do_duoc": (True if any(len(r) > 2 and r[2] for r in rows.values()) else None),
    }


def cham(hop_gt: dict, shown: dict, *, lk_khong_ap_dung: bool = False,
         chan_doan: dict | None = None, gt_rong: list[int] | None = None) -> dict:
    """Chấm `IoU(ô hiển thị, ô GT)`. Hàm THUẦN (test được, không cần video/model).

    Ba ca phải tách:
      - GT có vật, **không có ô hiển thị** ⇒ `iou = 0.0` (bám sai thật) — KHÔNG bỏ mẫu;
      - GT có vật, ô HỎNG (đảo/âm) ⇒ `None` + đếm `khong_do_duoc` (không quy thành 0);
      - frame GT có vật **không xuất hiện** trong CSV ⇒ `thieu_frame` (chưa chạy tới frame đó).

    `chan_doan` (ticket #39, tuỳ chọn): `frame → {ly_do, ly_do_khop, n_diem, …}`. Có nó thì kết quả
    thêm `ly_do_dem`/`ly_do_khop_dem` **chỉ trên các frame GT** — trả lời được "LK từ chối vì cổng MAD
    hay vì `_seed` rỗng" bằng SỐ. Không có ⇒ hai khoá đó `None` (chưa đo), KHÔNG phải "0 lần".

    `lk_khong_ap_dung=True` (cấu hình `vos_every=1`): CSV vẫn ghi `lk_ok = 0` cho mọi frame vì **không có
    LK**, nên `lk_ok_frac = 0,0` ở đó KHÔNG có nghĩa "LK từ chối 100 %" ⇒ trả `None` + cờ.
    """
    theo_frame, thieu = [], []
    khong_do = 0
    for frame, gt in sorted(hop_gt.items()):
        if frame not in shown:
            thieu.append(frame)
            continue
        row = shown[frame]
        box, lk_ok = row[0], row[1]          # CSV cũ chỉ có 2 phần tử (không cột `bam`)
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
    # IoU TÁCH THEO việc LK có nhận frame đó hay không. ĐỌC ĐÚNG Ý NGHĨA (review #65, P1):
    #   - `iou_khi_lk_ok`   = chất lượng **ô LK** (LK nhận ⇒ ô hiển thị do nội suy);
    #   - `iou_khi_lk_khong`= chất lượng **ô VOS ĐÓNG BĂNG** ở frame LK từ chối.
    # Đây là so "ô LK có tốt hơn ô VOS đóng băng không" TRÊN TẬP FRAME LK TỰ CHỌN ⇒ có **hiệu ứng chọn
    # mẫu**: KHÔNG được đọc thành "cổng chọn đúng frame khó" (muốn nói câu đó phải có phản thực: cùng
    # frame đó chạy cổng mở rồi so ô LK). Đo 20-11: ô LK 0,80–0,84 vs ô đóng băng 0,49–0,61.
    iou_ok = [r["iou"] for r in theo_frame if r["iou"] is not None and r["lk_ok"] is True]
    iou_khong = [r["iou"] for r in theo_frame if r["iou"] is not None and r["lk_ok"] is False]
    # Ô TRỐNG = CHƯA ĐO (frame `engine.start()` không có bước LK nào) ⇒ phải là nhóm RIÊNG, không được
    # gộp vào "LK từ chối" (review vòng 3, P3: reader đọc 2 trạng thái trong khi writer ghi 3).
    n_lk_chua_do = sum(1 for r in theo_frame if r["iou"] is not None and r["lk_ok"] is None)
    ra = {
        "n_gt_co_vat": len(hop_gt),
        "n_cham": len(do_duoc),
        "khong_do_duoc": khong_do,
        "thieu_frame": thieu,
        "iou_mean": round(statistics.fmean(do_duoc), 4) if do_duoc else None,
        "iou_min": round(min(do_duoc), 4) if do_duoc else None,
        # `vos_every=1` ⇒ KHÔNG có LK ⇒ `lk_ok` không áp dụng. Ghi 0,0 ở đó làm người đọc hiểu thành
        # "LK từ chối 100 %" — sai (ô ở cấu hình đó là ô VOS của chính frame). Review #64.
        "lk_khong_ap_dung": bool(lk_khong_ap_dung),
        "lk_ok_frac": (None if lk_khong_ap_dung or not theo_frame else
                       round(sum(1 for r in theo_frame if r["lk_ok"]) / len(theo_frame), 3)),
        "iou_khi_lk_ok": round(statistics.fmean(iou_ok), 4) if iou_ok else None,
        "iou_khi_lk_khong": round(statistics.fmean(iou_khong), 4) if iou_khong else None,
        "iou_khi_lk_dinh_nghia": ("iou_khi_lk_ok = ô LK; iou_khi_lk_khong = ô VOS ĐÓNG BĂNG khi LK từ "
                                  "chối — CHỈ đúng khi `lk_khong_ap_dung = false` (với `vos_every=1` "
                                  "không có LK nên cả hai vô nghĩa). Chênh lệch KHÔNG chứng minh cổng "
                                  "'chọn đúng': có hiệu ứng chọn mẫu (tập frame LK nhận do LK tự quyết)."),
        "n_lk_ok": len(iou_ok),
        "n_lk_khong": len(iou_khong),
        "n_lk_chua_do": n_lk_chua_do,
        # Phân bố LÝ DO LK từ chối, chỉ trên frame GT (ticket #39). `None` = CSV không có cột chẩn
        # đoán (CSV cũ) ⇒ CHƯA ĐO, khác `{}` (đo được nhưng không mẫu nào).
        "ly_do_dem": _dem(chan_doan, hop_gt, "ly_do"),
        "ly_do_khop_dem": _dem(chan_doan, hop_gt, "ly_do_khop"),
        # "vẽ ô khi KHÔNG có vật" — metric ĐỐI CHỨNG mà mọi chỉ số còn lại bỏ qua (chỉ chấm frame có vật).
        # `gt_rong=None` (chỗ gọi cũ / GT không khai) ⇒ `None` = CHƯA ĐO, không phải "0 lần oan".
        "o_ma": ty_le_o_ma(gt_rong, shown) if gt_rong is not None else None,
        # "0 frame có ô khi `bam = no_evidence`" — tiêu chí nghiệm thu P4, nay KIỂM ĐƯỢC từ artifact
        # (trước 21-11 cột `bam` là write-only nên con số chỉ nằm trong commit message).
        "o_khi_khong_bang_chung": dem_o_khi_khong_bang_chung(shown),
        "n_diem_median": _median_n_diem(chan_doan, hop_gt),
        "theo_frame": theo_frame,
    }
    return ra


def _dem(chan_doan: dict | None, hop_gt: dict, khoa: str) -> dict | None:
    """Đếm giá trị của `khoa` trên các frame GT. `None` = chưa đo; `{}` = đo được, không mẫu nào."""
    if not chan_doan:
        return None
    ra: dict = {}
    for frame in hop_gt:
        d = chan_doan.get(frame) or {}
        v = d.get(khoa)
        if v is None:
            continue
        ra[v] = ra.get(v, 0) + 1
    return ra


def _median_n_diem(chan_doan: dict | None, hop_gt: dict) -> float | None:
    if not chan_doan:
        return None
    ns = [(chan_doan.get(f) or {}).get("n_diem") for f in hop_gt]
    ns = [n for n in ns if isinstance(n, int)]
    return float(statistics.median(ns)) if ns else None


def _python() -> str:
    return sys.executable or "python3"


def chay_mot_lan(*, clip: str, bbox: str, image_size: int | None, vos_every: int,
                 max_mad: float, lk_scale: bool = False, frames: int, out_dir: Path) -> dict:
    lenh = [_python(), str(REPO_ROOT / "tools" / "live_worker.py"),
            "--source", clip, "--out-dir", str(out_dir),
            "--vos-every", str(vos_every), "--stop-after-frames", str(frames),
            "--lk-max-mad", str(max_mad), "--bbox", bbox,
            *(["--lk-scale"] if lk_scale else []),
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
        # Trung bình THEO LẦN CHẠY của IoU tách theo lk_ok (mỗi lần chạy một giá trị ⇒ `std` = dao động
        # giữa lần chạy, đúng ngữ nghĩa các metric khác của `tong_hop`).
        "iou_khi_lk_ok": _stats([r["cham"].get("iou_khi_lk_ok") for r in lan]),
        "iou_khi_lk_khong": _stats([r["cham"].get("iou_khi_lk_khong") for r in lan]),
        "n_lk_ok": _stats([r["cham"].get("n_lk_ok") for r in lan]),
        "iou_khi_lk_dinh_nghia": ("iou_khi_lk_ok = ô LK; iou_khi_lk_khong = ô VOS đóng băng khi LK từ "
                                  "chối (chỉ đúng khi lk_khong_ap_dung = false). Chênh lệch KHÔNG "
                                  "chứng minh cổng 'chọn đúng' — có hiệu ứng chọn mẫu."),
        "n_cham": _stats([r["cham"]["n_cham"] for r in lan]),
        "measured_fps": _stats([r["status"].get("measured_fps") for r in lan]),
    }


def danh_sach_cau_hinh(image_sizes, vos_everys, max_mads, lk_scales=(False,)) -> dict:
    """Tích ĐỀ CÁC: `{"192/1/1.5/shift": (192, 1, 1.5, False), …}` — MỘT chỗ rồi cả vòng chạy lẫn nhãn dùng lại.

    Vì sao phải là hàm riêng: bản đầu dựng khoá cấu hình ở 2 nơi (vòng chạy và bảng tổng hợp) ⇒ thêm
    trục `vos_every` thì một chỗ quên ⇒ `KeyError: (192, 1.5)` **chỉ lộ khi có > 1 giá trị** (chạy 1 giá
    trị vẫn xanh). Test `test_danh_sach_cau_hinh_...` khoá đúng chỗ này.
    """
    ra = {}
    for sz in image_sizes:
        for ve in vos_everys:
            for m in max_mads:
                for sc in lk_scales:
                    ten_sc = "scale" if sc else "shift"     # tự khai CHẾ ĐỘ NỘI SUY, không chỉ tham số
                    ra[f"{sz}/{ve}/{m}/{ten_sc}"] = (sz, ve, m, bool(sc))
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
        # Mỗi lần chạy vào ĐÚNG MỘT trong ba nhóm của từng trục (`chua` / `lech` / khớp): thiếu
        # `continue` thì một lần chạy có thể vào cả `chua` và `lech` ⇒ bộ đếm > tổng số lần chạy (P3 #65).
        hieu = r.get("image_size_hieu_luc")
        if hieu is None or r.get("image_size_yeu_cau") is None:
            chua.append(r)
        elif int(hieu) != int(r["image_size_yeu_cau"]):
            lech.append(r)
        else:
            che_do = r.get("lk_scale_hieu_luc")
            if che_do is None:
                chua.append(r)
            elif bool(che_do) != bool(r.get("lk_scale_yeu_cau")):
                lech.append(r)
    return lech, chua


SAN_NHIEU = 1e-3      # sàn ngưỡng nhiễu (IoU): dưới mức này không có ý nghĩa đo


def so_sanh(a: dict, b: dict) -> dict:
    """So hai cấu hình bằng SỐ, dùng ngưỡng nhiễu = độ lệch chuẩn lớn hơn của hai bên.

    Hàm THUẦN. Chênh lệch nhỏ hơn ngưỡng ⇒ "không phân biệt được" (AGENTS §6), không viết "tốt hơn".
    """
    a_mean, b_mean = a["iou_mean"]["mean"], b["iou_mean"]["mean"]
    if a_mean is None or b_mean is None:
        return {"chenh_iou": None, "nguong_nhieu": None, "phan_biet_duoc": None,
                "ket_luan": "KHÔNG kết luận: một bên không có lần chạy HỢP LỆ nào (hoặc không chấm "
                            "được frame nào)"}
    chenh = round(b_mean - a_mean, 4)
    std_a, std_b = a["iou_mean"].get("std"), b["iou_mean"].get("std")
    if std_a is None or std_b is None:
        # `std = None` nghĩa là một bên chỉ có 1 lần chạy ⇒ **không có** ngưỡng nhiễu. Coi nó là 0 sẽ
        # biến mọi chênh lệch thành "TỐT HƠN/TỆ HƠN" — đúng thứ AGENTS §6 cấm (n < 2 không kết luận).
        return {"chenh_iou": chenh, "nguong_nhieu": None, "phan_biet_duoc": None,
                "ket_luan": "KHÔNG kết luận: cần ≥ 2 lần chạy mỗi cấu hình để có ngưỡng nhiễu"}
    nhieu = max(float(std_a), float(std_b))
    # SÀN TUYỆT ĐỐI: `std` đã làm tròn 4 chữ số nên ngưỡng khác 0 nhỏ nhất là 1e-4 ⇒ câu kết luận sẽ
    # in "(> ngưỡng nhiễu 0.000)". Hai cấu hình TẤT ĐỊNH (std = 0) vẫn phải so được khi chênh lớn
    # (vd 0,85 vs 0,58) ⇒ dùng sàn thay vì từ chối kết luận (review #64 vòng 2).
    nhieu = max(nhieu, SAN_NHIEU)
    if nhieu == 0.0:
        # Cả hai bên KHÔNG dao động (3 lần ra y hệt) ⇒ chưa có thước đo nhiễu nào. `max(0,0) = 0` sẽ
        # biến mọi chênh lệch thành "TỐT HƠN/TỆ HƠN (ngưỡng nhiễu 0.000)" — đúng thứ AGENTS §6 cấm,
        # cùng lớp lỗi đã vá cho `std = None` (review #61) nhưng bỏ sót `std = 0` (review #64).
        return {"chenh_iou": chenh, "nguong_nhieu": 0.0, "phan_biet_duoc": None,
                "ket_luan": "KHÔNG kết luận: cả hai cấu hình không dao động giữa các lần chạy ⇒ "
                            "ngưỡng nhiễu = 0, mọi chênh lệch đều nằm trong sai số đo"}
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
    parser.add_argument("--lk-scale", nargs="+", default=["shift"], choices=["shift", "scale"],
                        help="chế độ nội suy LK: shift (chỉ dịch, hành vi cũ) / scale (thêm tỉ lệ + xoay)")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    hop_gt = hop_tu_gt(Path(args.gt))
    gt_rong = gt_rong_cua(Path(args.gt))
    if gt_rong:
        print(f"[GT] {len(gt_rong)} frame người tô khai KHÔNG có vật ({gt_rong[:8]}"
              f"{'…' if len(gt_rong) > 8 else ''}) ⇒ chấm thêm `ty_le_o_ma`")
    if not hop_gt:
        raise SystemExit(f"[LOI] {args.gt} không có frame nào có vật (toàn `gt_rong`?)")
    if args.lan < 2:
        print("[CANH BAO] --lan < 2 ⇒ chưa có ngưỡng nhiễu, KHÔNG được kết luận cấu hình nào tốt hơn")

    # Khoá cấu hình = (image_size, vos_every, max_mad). `vos_every` là trục quan trọng nhất khi hỏi
    # "hybrid 30 FPS mất bao nhiêu độ chính xác so với chạy VOS mọi frame".
    cau_hinh = danh_sach_cau_hinh(args.image_size, args.vos_every, args.max_mad,
                                  [sc == "scale" for sc in args.lk_scale])
    theo_cau_hinh: dict[tuple, list] = {k: [] for k in cau_hinh.values()}
    for vong in range(args.lan):
        for nhan_ch in thu_tu_vong(cau_hinh, vong):
            sz, ve, max_mad, lk_scale = cau_hinh[nhan_ch]
            # KHÔNG hard-code /dev/shm: máy dev là Windows (chỉ Linux mới có) ⇒ FileNotFoundError.
            with tempfile.TemporaryDirectory(prefix=f"ab_o_{sz}_{ve}_{max_mad}_") as tmp:
                res = chay_mot_lan(clip=args.clip, bbox=args.bbox, image_size=sz,
                                   vos_every=ve, max_mad=max_mad, lk_scale=lk_scale,
                                   frames=args.frames, out_dir=Path(tmp))
                # `res["shown"]` có thể là `str` (test giả lập + đường ghi ở dưới) ⇒ chuẩn hoá Path.
                chan_doan, thieu_cot = chan_doan_tu_csv(Path(res["shown"]))
                # `vos_every=1` KHÔNG có LK ⇒ cột chẩn đoán toàn trống, và `cham()` đã trả
                # `lk_khong_ap_dung = true` + `lk_ok_frac = None`. Để `{}` ở đây thì cùng một dict vừa
                # nói "không áp dụng" vừa nói "đo được 0 mẫu" — mâu thuẫn (P2 review PR #66 vòng 2).
                if int(ve) == 1:
                    chan_doan = None
                res["csv_thieu_cot"] = thieu_cot
                res["cham"] = cham(hop_gt, doc_shown(res["shown"]),
                                   lk_khong_ap_dung=(int(ve) == 1), chan_doan=chan_doan,
                                   gt_rong=gt_rong)
                cau = res["status"].get("cau_hinh") or {}
                res["max_mad_yeu_cau"] = max_mad
                res["max_mad_hieu_luc"] = cau.get("lk_max_mad")
                res["image_size_yeu_cau"] = sz
                res["lk_scale_yeu_cau"] = lk_scale
                # Ba trạng thái như `image_size`: None = CHƯA KIỂM ĐƯỢC (worker không khai).
                res["lk_scale_hieu_luc"] = cau.get("lk_scale")
                # Ba trạng thái KHÔNG lẫn: None = CHƯA KIỂM ĐƯỢC (worker không khai), số = đo được
                res["image_size_hieu_luc"] = cau.get("image_size_hieu_luc")
                res["image_size_kiem_duoc"] = res["image_size_hieu_luc"] is not None
                res["vos_every_yeu_cau"] = ve
                res["shown"] = str(res["shown"])
                res["so_dong_khop_frame"] = so_dong_khop_frame(res)
                # Lệch số dòng = mất mẫu hoặc ghi trùng ⇒ IoU tính trên tập frame KHÁC tập đã phát.
                # Trước đây chỉ in cảnh báo và vẫn tính vào trung bình (review #64).
                res["hop_le"] = lan_chay_hop_le(res) and res["so_dong_khop_frame"]
                if lan_chay_hop_le(res) and not res["so_dong_khop_frame"]:
                    print(f"[LOI] {sz}/{ve}/{max_mad}: shown.csv {res['so_dong_shown'] - 1} dòng "
                          f"nhưng phiên phát {res['status'].get('frames')} frame — có frame không được "
                          "ghi hoặc ghi trùng ⇒ LOẠI lần chạy này", flush=True)
            theo_cau_hinh[(sz, ve, max_mad, lk_scale)].append(res)
            c = res["cham"]
            print(f"vòng {vong + 1} · {nhan_ch} → IoU(ô hiển thị, ô GT) {c['iou_mean']} "
                  f"(tệ nhất {c['iou_min']}) trên {c['n_cham']}/{c['n_gt_co_vat']} frame · "
                  f"lk_ok {c['lk_ok_frac']} · hiệu lực mad {res['max_mad_hieu_luc']} · "
                  f"image_size {res['image_size_hieu_luc']}")

    # HAI chiều, tên nói rõ chiều: `tong`/`lan_chay` khoá bằng NHÃN, `theo_cau_hinh` khoá bằng TUPLE.
    # Lẫn hai chiều ⇒ `KeyError: '192/1/1.5'` (lộ đúng lúc ghi artifact, sau khi đã chạy xong 9 lần).
    # `cau_hinh` là {nhãn: (sz, ve, mad)}. Đọc tên là biết chiều, KHÔNG viết comprehension hai lớp
    # (bản vá đầu viết `{v: k for k, v in …}` cho CẢ HAI ⇒ hai bảng cùng chiều, test bắt được).
    khoa_cua = dict(cau_hinh)                        # nhãn → tuple
    nhan = {tup: nhan_ch for nhan_ch, tup in cau_hinh.items()}   # tuple → nhãn
    so_lan_loi = {nhan[k]: sum(1 for r in v if not r["hop_le"]) for k, v in theo_cau_hinh.items()}
    tong = {nhan[k]: tong_hop([r for r in v if r["hop_le"]]) for k, v in theo_cau_hinh.items()}
    # Chỉ xét lần chạy HỢP LỆ: worker chết ⇒ `status` rỗng ⇒ `max_mad_hieu_luc = None` ⇒ bị nhồi vào
    # `lech` và thông điệp đổ lỗi "mad hiệu lực khác yêu cầu" (sai nguyên nhân). Review #64.
    lech, chua_kiem_duoc = cau_hinh_lech(
        [r for v in theo_cau_hinh.values() for r in v if r["hop_le"]])
    # Nhãn = "<size>/<every>/<mad>/<che_do>" ⇒ 3 phần đầu là số, phần cuối là chuỗi.
    khoa = sorted(tong, key=lambda k: (*[float(x) for x in k.split("/")[:3]], k.split("/")[3]))
    hop_le = {nhan[k]: [r for r in v if r["hop_le"]] for k, v in theo_cau_hinh.items()}
    if len(khoa) > 2:
        # "Đầu↔cuối" chỉ có nghĩa khi có ĐÚNG 2 cấu hình. Với ≥ 3, cặp đó bỏ qua cấu hình giữa và có
        # thể là cặp CHÉO GÓC (nhiều trục cùng biến thiên) ⇒ không phát `so_sanh`, dùng `so_sanh_moi_cap`.
        print(f"[canh-bao] có {len(khoa)} cấu hình ⇒ KHÔNG phát `so_sanh` (đầu↔cuối) vì dễ là cặp "
              "chéo góc; đọc `so_sanh_moi_cap`.", file=sys.stderr)
        ss = {}
    else:
        ss = so_sanh(tong[khoa[0]], tong[khoa[-1]]) if len(khoa) == 2 else {}
    # MỌI cặp, không chỉ đầu↔cuối: với > 2 cấu hình, "đầu↔cuối" bỏ qua cấu hình giữa VÀ nếu nhiều trục
    # cùng biến thiên thì cặp đó là **chéo góc** (vd mặc định `--max-mad [1.5, 6.0]` + `--vos-every 1 3`
    # ⇒ so `192/1/1.5` với `192/3/6.0` = so hai thứ khác nhau trong cùng một phép). Review #64 bắt.
    moi_cap = {}
    for i in range(len(khoa)):
        for j in range(i + 1, len(khoa)):
            a_k, b_k = khoa[i], khoa[j]
            moi_cap[f"{a_k}|{b_k}"] = {
                **so_sanh(tong[a_k], tong[b_k]),
                **{f"theo_cap_{kk}": vv for kk, vv in
                   so_sanh_theo_cap(hop_le[a_k], hop_le[b_k]).items()},
            }
    # `khoa` là NHÃN ⇒ phải quy về TUPLE bằng `khoa_cua` (dùng `nhan` ở đây là lỗi chiều — đã gặp 2 lần)
    ss_cap = ({**so_sanh_theo_cap(hop_le[khoa[0]], hop_le[khoa[-1]]),
               "a": khoa[0], "b": khoa[-1]} if len(khoa) >= 2 else {})

    from scripts.measure_watchdog import _git_provenance

    tong_lan = sum(len(v) for v in theo_cau_hinh.values())
    for nhan_truc, khoa_truc in (("image_size", "image_size_hieu_luc"),
                                 ("lk_scale", "lk_scale_hieu_luc")):
        n = sum(1 for r in chua_kiem_duoc if r.get(khoa_truc) is None)
        if n:
            print(f"[canh-bao] {n}/{tong_lan} lần chạy CHƯA kiểm được `{nhan_truc}` hiệu lực (worker "
                  f"không khai `{khoa_truc}`) ⇒ `cau_hinh_hieu_luc_lech == []` KHÔNG chứng minh trục "
                  f"`{nhan_truc}` đã khớp", file=sys.stderr)

    rev, dirty, dirty_code, loi = _git_provenance()
    artifact = {
        "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code, "git_loi": loi,
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "lenh": " ".join(["python scripts/ab_o_hien_thi_vs_gt.py"] + (argv or sys.argv[1:])),
        # 5: `tong_hop` có thêm `iou_khi_lk_dinh_nghia` (thêm khoá mà KHÔNG tăng số hiệu từng làm hai
        # artifact cùng "schema 4" nhưng khác tập khoá — đúng lỗi P3 đã bị bắt một lần, review #65 v3).
        # 6: `cham()` thêm `ly_do_dem`/`ly_do_khop_dem`/`n_diem_median` (ticket #39) + `csv_thieu_cot`.
        "schema": 7,   # 7 = thêm `cham.o_ma` (ty_le_o_ma trên frame gt_rong)
        "nguon_so": {"gt": args.gt, "clip": args.clip, "bbox": args.bbox,
                     "max_mad": args.max_mad, "lk_scale": args.lk_scale,
                     "image_size": args.image_size, "vos_every": args.vos_every,
                     "frames": args.frames, "lan": args.lan,
                     "frame_gt_co_vat": sorted(hop_gt)},
        "dinh_nghia": ("IoU(ô bao ĐANG HIỂN THỊ ở frame đó, hộp bao suy từ mask NGƯỜI tô). GT có vật "
                       "mà không vẽ ô nào ⇒ 0,0 (bám sai thật), KHÔNG phải 'không đo được'. Đây là "
                       "phép đo 'ô bám đúng chỗ không' — khác `drift_iou` (khớp ô VOS) và khác mIoU "
                       "(mask vs GT, chỉ chạy được với vos_every=1 nên không thấy LK)."),
        "cau_hinh_hieu_luc_lech": lech,
        # Đếm theo ĐÚNG trục: sau khi thêm trục `lk_scale`, `chua` gộp cả hai ⇒ `len(chua)` mang tên
        # `image_size` mà đếm cả run chỉ lệch `lk_scale` (review #65 vòng 2, P2).
        "image_size_chua_kiem_duoc": sum(1 for r in chua_kiem_duoc
                                         if r.get("image_size_hieu_luc") is None),
        # Nếu KHÔNG còn lần chạy hợp lệ nào thì `cau_hinh_hieu_luc_lech == []` và
        # `image_size_chua_kiem_duoc == 0` đều vô nghĩa — đọc thành "đã khớp" là sai (review #64 vòng 2).
        "cau_hinh_kiem_duoc": bool(hop_le and any(hop_le.values())),
        # Đếm riêng cho trục chế độ nội suy: trước đây `image_size_chua_kiem_duoc` gộp cả hai trục nên
        # tên khoá nói sai đại lượng (P3 review #65).
        "lk_scale_chua_kiem_duoc": sum(1 for r in chua_kiem_duoc if r.get("lk_scale_hieu_luc") is None),
        "so_lan_chay_loi": so_lan_loi,
        "tong_hop": tong,
        "so_sanh": ss,
        "so_sanh_moi_cap": moi_cap,
        "so_sanh_theo_cap": ss_cap,
        "lan_chay": {nhan[k]: [{kk: vv for kk, vv in r.items() if kk != "status"} for r in rs]
                     for k, rs in theo_cau_hinh.items()},
    }
    # Tên mặc định PHẢI kèm clip + bộ GT: bản đầu chỉ có NGÀY ⇒ mọi phiên cùng ngày ghi đè nhau và
    # artifact của một phiên đã MẤT (P1 review #64 vòng 1). Không ghi đè tệp đã có.
    out = Path(args.out) if args.out else REPO_ROOT / "data" / (
        f"ab_{Path(args.clip).stem}_{Path(args.gt).name}_{datetime.now():%Y-%m-%d}_metrics.json")
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
