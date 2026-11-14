"""Sinh `docs/so-lieu-bao-cao.md` từ ARTIFACT thật — để báo cáo không trích số không truy được nguồn.

Chức năng: đọc danh sách "tuyên bố → artifact + đường dẫn khoá" (registry bên dưới), lấy số **trực
           tiếp từ file JSON/CSV đã commit**, rồi ghi 1 bảng markdown có cột "CẤM trích thành".
Input  : `data/*_metrics.json` (+ CSV mẫu), không cần chạy model.
Output : `docs/so-lieu-bao-cao.md` (sinh lại được, chạy 2 lần ra cùng nội dung).
Lưu ý  : (1) Thiếu artifact / thiếu khoá ⇒ ghi **`THIẾU`**, KHÔNG bịa số và KHÔNG làm hỏng cả bảng.
         (2) `None` trong artifact = CHƯA ĐO ⇒ in `null`, không in 0 (AGENTS §6).
         (3) Cột "cấm trích thành" là phần quan trọng nhất: cùng một số có thể bị đọc thành hai
         nghĩa khác nhau (`drift_iou` → "độ chính xác"; `mask_fps` → "mask 30 FPS").

Cách dùng:
    python scripts/so_lieu_bao_cao.py            # ghi docs/so-lieu-bao-cao.md
    python scripts/so_lieu_bao_cao.py --check    # chỉ kiểm, thoát mã 1 nếu file đã commit khác
"""

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Mỗi dòng: (tuyên bố, artifact, đường dẫn khoá trong JSON, đơn vị, cấm trích thành)
# Đường dẫn khoá dạng "a.b.0.c" — số nguyên là chỉ số mảng.
REGISTRY = [
    ("Tốc độ model ở `image_size 192` (đường live)", "data/lan2_chai_binh1_lan1_metrics.json",
     "worker_status.vos_ms", "ms/frame",
     "KHÔNG phải \"thời gian xử lý một frame người xem thấy\" — thiếu `pre_ms` (14,3 ms) và thời "
     "gian vẽ; xem artifact chu kỳ."),
    ("Nhịp mask ở `vos_every 3` (đường live)", "data/lan2_chai_binh1_lan1_metrics.json",
     "worker_status.vos_fps", "lần/giây",
     "CẤM viết \"mask 30 FPS\": HUD 29,9 FPS là nhịp VẼ, mask chỉ ~8–10 lần/giây."),
    ("Tuổi dữ liệu ảnh, định nghĩa CŨ (age + vos)", "data/lan2_chai_binh1_lan1_metrics.json",
     "worker_status.mask_age_p95", "ms (p95)",
     "Chỉ dùng để SO với số trước 14-11. Số mới là `mask_age_total_ms` (tuổi dữ liệu thật)."),
    ("Tuổi dữ liệu ảnh, tuổi THẬT (queue+pre+vos+post+age)", "data/chu_ky_chai_binh1_1vong_lan2_metrics.json",
     "worker_status.mask_age_p95", "ms (p95)",
     "Một lần chạy 11 s (1 vòng) — 3 lần cho 268,7–301,2 ms. KHÔNG so với 271–273 ms của bộ số 13-11 "
     "(định nghĩa CŨ: chỉ age+vos)."),
    ("Chu kỳ VOS (1/vos_fps thực)", "data/chu_ky_chai_binh1_1vong_lan2_metrics.json",
     "worker_status.cycle_ms", "ms",
     "3 lần: 101,5–121,6 ms. Các pha là **mẫu của lần VOS gần nhất**, KHÔNG cùng một chu kỳ ⇒ đừng "
     "cộng 4 pha rồi đòi khớp `cycle_ms`."),
    ("Tiền xử lý mỗi frame (resize + tensor)", "data/chu_ky_chai_binh1_1vong_lan2_metrics.json",
     "worker_status.pre_ms", "ms",
     "3 lần: 11,6–13,1 ms. KHÔNG cộng vào `vos_ms` khi báo cáo (đếm hai lần) — nhưng PHẢI cộng khi "
     "nói \"một frame tốn bao lâu\"."),
    ("Frame chờ trong worker trước khi được xử lý", "data/chu_ky_chai_binh1_1vong_lan1_metrics.json",
     "worker_status.queue_ms", "ms",
     "Mẫu của lần VOS CUỐI, dao động mạnh: 3 lần cho 2,1–75,9 ms (một lần đo n=1 từng ra 0,33 ms ⇒ "
     "cấm trích một lần chạy làm \"queue ≈ 0\")."),
    ("Tỉ lệ mask rỗng khi vật CÒN trong khung (`binh1`, chai)",
     "data/sach_chai_binh1_1vong_metrics.json", "cua_so_frame.trong_khung.empty_frac", "tỉ lệ",
     "CẤM trích tỉ lệ rỗng cả phiên (0,36) thành \"model mất dấu 36 %\": phần lớn là vật ngoài khung."),
    ("Tỉ lệ mask rỗng khi vật CÒN trong khung (`binh2`, chai trắng)",
     "data/sach_chai_binh2_1vong_metrics.json", "cua_so_frame.trong_khung.empty_frac", "tỉ lệ",
     "Cùng cảnh báo trên; và ô cũ `200,400,300,500` phủ 2 chai + 2 tay nên số cũ không dùng."),
    ("Độ tự nhất quán ô bao ↔ mask VOS (`binh2`, trong khung)",
     "data/sach_chai_binh2_1vong_metrics.json", "cua_so_frame.trong_khung.drift_iou_mean", "IoU",
     "CẤM gọi là \"độ chính xác bám\" — đây là độ TỰ NHẤT QUÁN (AGENTS §6); độ chính xác cần GT mask."),
    ("Số vòng nguồn file đã phát lại", "data/sach_lap27vong_binh1_metrics.json",
     "cua_so_frame.so_vong", "vòng",
     "Chỉ là ước tính từ frame đã phát/xử lý chia số frame clip; nguồn mạng ⇒ `null`."),
    ("mIoU mask vs GT bị che 50 % (fixture TỔNG HỢP, `image_size 320`)",
     "data/occlusion_metrics_320_metrics.json", "ket_qua.che 50%.mask_miou_trong", "IoU",
     "ĐÂY LÀ CẬN TRÊN trên ảnh tổng hợp (GT = pixel một ô vuông màu, prompt = đúng bbox GT) — CẤM "
     "trích như \"mIoU trên video thật/DAVIS\"."),
    ("Watchdog phát hiện worker chết (mode worker, `kill -9`)", "data/watchdog_2026-11-09_metrics.json",
     "tom_tat.tg_bao_error_ms.mean", "ms",
     "Nhanh vì `proc.poll()` bắt được; ca \"sống mà treo\" mất ~15 s, CẤM trích 0,1 s cho ca đó."),
    # ── Việc #5 (14-11): bảng cấu hình đo bằng 3 lần chạy worker thật trên máy CPU này ──────────
    ("Nhịp mask ở `vos_every 2` (cấu hình nhanh nhất, `image_size 192`)",
     "data/bang_cau_hinh_2026-11-14_metrics.json",
     "cau_hinh.192_2.vos_fps.mean", "lần/giây",
     "CẤM viết 'mask 30 FPS' và CẤM so với FPS phát 29,7 — hai nhịp khác nhau.",
     {"std": "cau_hinh.192_2.vos_fps.std", "n": "cau_hinh.192_2.vos_fps.n"}),
    ("Tuổi dữ liệu ảnh p95 ở `image_size 192`, `vos_every 3`", "data/bang_cau_hinh_2026-11-14_metrics.json",
     "cau_hinh.192_3.mask_age_p95.mean", "ms (p95)",
     "`vos_ms` chỉ là phần model; 'một frame tốn bao lâu' phải cộng `pre_ms`. p95 dựa trên "
     "`cau_hinh.192_3.age_n` mẫu — đọc kèm, n nhỏ thì p95 ≈ max.",
     {"std": "cau_hinh.192_3.mask_age_p95.std", "n": "cau_hinh.192_3.age_n.mean"}),
    ("Tuổi dữ liệu ảnh p95 ở `image_size 320`, `vos_every 3` (chi tiết vật nhỏ)",
     "data/bang_cau_hinh_2026-11-14_metrics.json",
     "cau_hinh.320_3.mask_age_p95.mean", "ms (p95)",
     "Chỉ được nói 'cũ hơn hẳn' nếu chênh với 192 LỚN HƠN `std` lớn hơn của hai dòng (đọc `std` ngay "
     "trong cột này, đừng gõ tay).",
     {"std": "cau_hinh.320_3.mask_age_p95.std", "n": "cau_hinh.320_3.age_n.mean"}),
    # ── Việc #6 (14-11): mIoU vs GT — thước đo DUY NHẤT nói được đúng/sai ───────────────────────
    ("mIoU mask vs GT trên fixture TỔNG HỢP (ô vuông trên nền nhiễu)", "data/miou_synthetic_2026-11-14_metrics.json",
     "ket_qua.mIoU", "IoU",
     "CẬN TRÊN: GT ≡ pixel ô vuông, prompt = đúng bbox của nó. Số này chấm trên `so_frame_cham` "
     "frame trong tổng `so_frame_gt` — CẤM nói 'mIoU cả clip'. CẤM trích như mIoU trên video thật — "
     "muốn số thật thì gán tay (`scripts/score_miou.py label`).",
     {"n": "ket_qua.n_cham"}),
]

HEADER = """# Số liệu dùng cho báo cáo — sinh tự động, đừng sửa tay

> File này do `python scripts/so_lieu_bao_cao.py` sinh từ **artifact đã commit** (`data/*`).
> Sửa tay sẽ bị ghi đè; nếu cần thêm dòng thì thêm vào `REGISTRY` trong script.
> Chạy `python scripts/so_lieu_bao_cao.py --check` để CI báo khi file lệch artifact.
>
> Cột **CẤM trích thành** là phần quan trọng nhất: cùng một con số có thể bị đọc thành hai nghĩa
> khác nhau, và repo này đã 3 lần suýt trích sai (`drift_iou` → "độ chính xác"; tỉ lệ rỗng cả phiên
> → "model mất dấu"; `mask_fps` → "mask 30 FPS").
"""


def _get(data, path: str):
    """Lấy giá trị theo đường dẫn `"a.b.0.c"`; thiếu bất kỳ khúc nào ⇒ `_THIEU`."""
    node = data
    for part in path.split("."):
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return _THIEU
        elif isinstance(node, dict):
            if part not in node:
                return _THIEU
            node = node[part]
        else:
            return _THIEU
    return node


class _Thieu:
    """Đánh dấu "artifact/khoá không tồn tại" — khác hẳn `None` (chưa đo)."""

    def __repr__(self) -> str:
        return "THIẾU"

    def __str__(self) -> str:
        return "THIẾU"


_THIEU = _Thieu()


def _fmt(value) -> str:
    if value is _THIEU:
        return "THIẾU"          # dòng trong bảng đã tự bọc `**…**`
    if value is None:
        return "`null` (chưa đo)"
    if isinstance(value, float):
        return f"{value:g}".replace(".", ",")
    return str(value)


def build_table() -> str:
    """Sinh bảng markdown (hàm thuần, không ghi file) — test so được từng dòng.

    Dòng REGISTRY có thể có **phần tử thứ 6** (dict): `{"std": "khoá.std", "n": "khoá_n"}`. Khi có,
    script tự in `mean ± std (n)` **đọc từ artifact** thay vì để người viết gõ tay "± 0,4" vào cột
    cảnh báo — chính các số gõ tay đó đã sai (0,4 là của cấu hình khác; ±55 ms trong khi artifact ghi
    32,05) — review độc lập 14-11, P1.
    """
    lines = ["| Tuyên bố | Số | Đơn vị | Artifact | Lệnh / khoá | CẤM trích thành |",
             "|---|---|---|---|---|---|"]
    for row in REGISTRY:
        claim, artifact, key, unit, cam = row[:5]
        extra = row[5] if len(row) > 5 else {}
        path = _REPO_ROOT / artifact
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        value = _THIEU if data is None else _get(data, key)
        hien = _fmt(value)
        if data is not None and extra.get("std"):
            std = _get(data, extra["std"])
            n = _get(data, extra["n"]) if extra.get("n") else _THIEU
            if std is not _THIEU and std is not None:
                hien = f"{hien} ± {_fmt(std).strip('`')}"
                if n is not _THIEU and n is not None:
                    hien += f" (n = {_fmt(n)})"
        lines.append(f"| {claim} | **{hien}** | {unit} | `{artifact}` | "
                     f"`{key}` | {cam} |")
    return "\n".join(lines)


def build_document() -> str:
    thieu = [row for row in REGISTRY
             if not (_REPO_ROOT / row[1]).exists()]
    canh_bao = ""
    if thieu:
        canh_bao = ("\n> ⚠️ Thiếu artifact: " + ", ".join(f"`{a}`" for _, a, *_ in thieu)
                    + " — các dòng đó in `THIẾU`, **không** được trích.\n")
    return HEADER + canh_bao + "\n" + build_table() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/so-lieu-bao-cao.md")
    parser.add_argument("--check", action="store_true",
                        help="không ghi; thoát mã 1 nếu file đang có khác bản sinh ra")
    args = parser.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = _REPO_ROOT / out
    moi = build_document()
    if args.check:
        cu = out.read_text(encoding="utf-8") if out.exists() else ""
        if cu != moi:
            print(f"[LECH] {out} không khớp artifact — chạy `python scripts/so_lieu_bao_cao.py` "
                  f"rồi commit lại")
            return 1
        print(f"[OK] {out} khớp artifact")
        return 0
    out.write_text(moi, encoding="utf-8")
    print(f"Ghi: {out} ({len(REGISTRY)} dòng)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
