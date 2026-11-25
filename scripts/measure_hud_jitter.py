#!/usr/bin/env python3
"""Đo **cái người xem THẤY** trên video HUD của một phiên `demoip` — không đọc CSV.

Vì sao có script này (25-11): người dùng phàn nàn *"box đỏ hơi dựt lag"* và *"nó để nghi, nghi cũng
đúng vật, chưa cập nhật thành box đỏ"*. Cả hai là chuyện của **khung hình vẽ ra**, mà CSV chỉ ghi kết
quả **mỗi bước VOS** (`vos_every` bước mới có 1 dòng) ⇒ đọc CSV không thấy được "ô đứng yên 9 frame
rồi nhảy" (đo 25-11: CSV nói jitter med 10,2 px, video nói ô đứng yên med 9 frame rồi nhảy max 118 px).

Cách đo: dò **màu** trên từng frame hiển thị (không cần model, không cần GT):

- ô đỏ `(0,0,255)` = trạng thái bình thường ("box đỏ" người dùng nói tới);
- nét đứt vàng `(0,215,255)` = `nghi` / `chua_xac_minh` (xem `src/visualizer.py`);
- banner "MẤT DẤU" = khối đỏ đặc (phân biệt bằng mật độ pixel đỏ, không phải viền).

Chỉ số xuất ra:
- `giu_frame_med`  : số frame hiển thị ô **đứng yên** trước mỗi lần nhảy (med) ⇒ nhịp "dựt";
- `nhay_tam_med/p95/max` : bước nhảy tâm khi ô đổi vị trí (px);
- `pct_o_do` / `pct_net_dut` : % frame hiển thị có ô đỏ / có nét đứt vàng ⇒ "bao nhiêu phần phiên
  người xem thấy box đỏ";
- `fps_video`, `so_frame`.

Cách dùng:
    python scripts/measure_hud_jitter.py data/demoip_1125-100334_web.mp4
    python scripts/measure_hud_jitter.py a_web.mp4 b_web.mp4 --out data/hud_jitter_..._metrics.json

Quy ước trung thực (AGENTS §6): mọi trường `*_n` = số mẫu; `None` = **chưa đo được** (không phải 0);
script thoát mã **1** nếu không đo được video nào (0 video ≠ "đã đo").
Artifact có `git_rev` / `git_dirty_code` / `lenh` / `do_luc` để số trích được vào báo cáo.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Ngưỡng dò màu (BGR) — trùng hằng số trong `src/visualizer.py`.
_DO = dict(kênh=2, nguong=170, g_max=90, b_max=90)      # đỏ (0,0,255)
_VANG = dict(kênh=2, nguong=170, g_min=170, b_max=110)   # vàng (0,215,255)
_MIN_PIXEL_O = 80        # ít pixel hơn ⇒ coi như không có ô (nhiễu nén H.264)
_MIN_PIXEL_BANNER = 3000  # banner "MẤT DẤU" là khối đặc ⇒ nhiều pixel hơn hẳn một viền ô


def _mat_na(b, g, r):
    return ((r > 170) & (g < 90) & (b < 90))          # đỏ
def _mat_vang(b, g, r):
    return ((r > 170) & (g > 170) & (b < 110))        # vàng


def hop_tu_frame(frame):
    """Trả (x1,y1,x2,y2) của **viền ô đỏ** hoặc `None`.

    Banner "MẤT DẤU" cũng là màu đỏ nhưng là **khối đặc** ⇒ loại bằng mật độ: khối đặc có số pixel
    xấp xỉ diện tích hộp, viền ô chỉ ~chu vi × độ dày (< 15 % diện tích).
    """
    b, g, r = frame[:, :, 0].astype(int), frame[:, :, 1].astype(int), frame[:, :, 2].astype(int)
    m = _mat_na(b, g, r)
    n = int(m.sum())
    if n < _MIN_PIXEL_O:
        return None, n
    ys, xs = np.nonzero(m)
    x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
    # Banner "MẤT DẤU" = **khối đặc** đỏ có chữ trắng bên trong ⇒ tỉ lệ đỏ tính trên CẢ hộp chỉ ~14 %
    # (đo 25-11: 1 050/7 275 px) nên test "khối đặc" theo cả hộp KHÔNG bắt được — phải xét RUỘT hộp:
    # viền ô rỗng ruột (đỏ chỉ ở 2–3 px sát biên), banner thì ruột vẫn đỏ ~60–70 %.
    rx1, ry1, rx2, ry2 = x1 + 4, y1 + 4, x2 - 4, y2 - 4
    if (rx2 - rx1) >= 4 and (ry2 - ry1) >= 4:
        ruot = float(m[ry1:ry2, rx1:rx2].mean())
        # Đo 25-11 (frame 403 của phiên 100334): banner ruột đỏ **0,184**, ô thật ruột **0,000**;
        # còn "cả hộp" thì banner 0,139 < ô thật 0,308 ⇒ phải xét RUỘT, và ngưỡng 0,10 là ranh giới
        # quan sát được. Thêm điều kiện DẸT (rộng/cao > 5) để không loại oan một ô thật có vật đỏ bên
        # trong (banner 285×19 = 15:1).
        if ruot > 0.10 and (x2 - x1) / max(1, y2 - y1) > 5:
            return None, n        # khối đặc = banner, không phải ô
    return (x1, y1, x2, y2), n


def dem_vang(frame) -> int:
    b, g, r = frame[:, :, 0].astype(int), frame[:, :, 1].astype(int), frame[:, :, 2].astype(int)
    return int(_mat_vang(b, g, r).sum())


def _dai_nhay(v: float) -> str:
    """Chia dải bước nhảy — để A/B thấy ô làm mượt biến 1 cú nhảy thành nhiều bước nhỏ."""
    for nguong, ten in ((20, "<20px"), (50, "20-50px"), (100, "50-100px"), (200, "100-200px")):
        if v < nguong:
            return ten
    return ">=200px"


def do_video(path: Path, buoc_lay_mau: int = 1) -> dict:
    """Đo 1 video. `buoc_lay_mau=1` = mọi frame hiển thị (đúng thứ người xem thấy)."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"[loi] không mở được video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    o_theo_frame = []
    so_do = so_vang = so_frame = 0
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % buoc_lay_mau == 0:
            so_frame += 1
            hop, n_do = hop_tu_frame(fr)
            n_vang = dem_vang(fr)
            if hop is not None:
                so_do += 1
            if n_vang > 150:
                so_vang += 1
            o_theo_frame.append(hop if hop is not None else (None, n_do, n_vang))
        i += 1
    cap.release()
    if so_frame == 0:
        raise SystemExit(f"[loi] video không có frame: {path}")

    # chuỗi "ô đứng yên" (cùng tâm ±0.6 px) và bước nhảy khi đổi
    giu = []
    nhay = []            # bước nhảy KHI ĐANG BÁM liên tục (frame trước cũng có ô)
    dich_chuyen = []     # dịch chuyển tâm MỖI frame hiển thị (gồm cả 0) — đại lượng "trượt/giật"
    nhay_sau_gap = []    # bước nhảy ngay sau khi ô biến mất ≥1 frame (tái bám — KHÔNG phải jitter)
    run = 1
    prev = None
    truoc_co_o = False
    for o in o_theo_frame:
        co_o = isinstance(o, tuple) and len(o) == 4
        if not co_o:
            truoc_co_o = False
            if prev is not None:
                giu.append(run)
                run = 1
                prev = None
            continue
        c = ((o[0] + o[2]) / 2.0, (o[1] + o[3]) / 2.0)
        if prev is None:
            prev, truoc_co_o = c, True
            continue
        d = ((c[0] - prev[0]) ** 2 + (c[1] - prev[1]) ** 2) ** 0.5
        if truoc_co_o:
            dich_chuyen.append(d)
        if d < 0.6:
            run += 1
        else:
            giu.append(run)
            (nhay if truoc_co_o else nhay_sau_gap).append(d)
            run = 1
        prev, truoc_co_o = c, True
    if run:
        giu.append(run)

    def _p95(v):
        if not v:
            return None
        v = sorted(v)
        return v[min(len(v) - 1, int(0.95 * len(v)))]

    dai = {}
    for d in nhay:
        khoa = _dai_nhay(d)
        dai[khoa] = dai.get(khoa, 0) + 1

    return {
        "video": path.name,
        # Dịch chuyển tâm mỗi frame hiển thị: "0,00" = ô đứng yên rồi nhảy từng cục; "~1-2" = trượt đều.
        "dich_chuyen_frame_med": round(st.median(dich_chuyen), 2) if dich_chuyen else None,
        "dich_chuyen_frame_p95": round(_p95(dich_chuyen), 2) if dich_chuyen else None,
        "dich_chuyen_frame_n": len(dich_chuyen),
        "dai_buoc_nhay": dai,
        "fps_video": round(float(fps), 3),
        "so_frame": so_frame,
        "giu_frame_med": st.median(giu) if giu else None,
        # `*_n` bắt buộc: `None` = chưa đo được, không phải 0
        "giu_frame_med_n": len(giu),
        "nhay_tam_med": round(st.median(nhay), 2) if nhay else None,
        "nhay_tam_p95": round(_p95(nhay), 2) if nhay else None,
        "nhay_tam_max": round(max(nhay), 2) if nhay else None,
        "nhay_tam_n": len(nhay),
        # Tách riêng: nhảy NGAY SAU khi ô biến mất rồi hiện lại KHÁC bản chất với jitter khi đang bám.
        "nhay_sau_gap_n": len(nhay_sau_gap),
        "nhay_sau_gap_max": round(max(nhay_sau_gap), 2) if nhay_sau_gap else None,
        "pct_o_do": round(100.0 * so_do / so_frame, 2),
        "pct_net_dut": round(100.0 * so_vang / so_frame, 2),
        "o_do_n": so_do,
    }


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=_REPO_ROOT, capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _git_dirty_code() -> bool | None:
    """Bẩn **bỏ qua `data/`** — đo lại lần hai thì chính artifact bị sửa (AGENTS §6)."""
    out = _git("status", "--porcelain")
    if out is None or out == "" and _git("rev-parse", "HEAD") == "":
        return None
    for line in out.splitlines():
        duong = line[3:].strip()
        if duong and not duong.startswith("data/"):
            return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Đo jitter/chế độ vẽ ô trên video HUD của `demoip`.")
    ap.add_argument("videos", nargs="+", help="đường dẫn `*_web.mp4` (hoặc video HUD bất kỳ)")
    ap.add_argument("--out", default=None, help="ghi JSON (mặc định chỉ in bảng)")
    ap.add_argument("--buoc-lay-mau", type=int, default=1,
                    help="lấy mẫu mỗi N frame hiển thị (mặc định 1 = mọi frame)")
    args = ap.parse_args(argv)

    ket_qua = []
    for v in args.videos:
        p = Path(v)
        if not p.is_file():
            print(f"[loi] không thấy {p}")
            continue
        r = do_video(p, buoc_lay_mau=max(1, args.buoc_lay_mau))
        ket_qua.append(r)
        print(f"\n=== {r['video']} ===")
        print(f"  {r['so_frame']} frame hiển thị @ {r['fps_video']} fps")
        if r["giu_frame_med"] is None and r["nhay_tam_med"] is None:
            print("  [canh bao] KHÔNG thấy ô đỏ nào ⇒ video này không phải bản có HUD ô đỏ"
                  " (0 mẫu ≠ 'jitter = 0')")
        else:
            print(f"  ô đứng yên: med {r['giu_frame_med']} frame (n={r['giu_frame_med_n']})"
                  f" ⇒ nhảy mỗi ~{(r['giu_frame_med'] or 0) / max(r['fps_video'], 1e-6) * 1000:.0f} ms")
            print(f"  bước nhảy tâm (đang bám liên tục): med {r['nhay_tam_med']} px"
                  f" · p95 {r['nhay_tam_p95']} · max {r['nhay_tam_max']} px (n={r['nhay_tam_n']})")
            if r["dich_chuyen_frame_n"]:
                print(f"  dịch chuyển/frame hiển thị: med {r['dich_chuyen_frame_med']} px"
                      f" · p95 {r['dich_chuyen_frame_p95']} (n={r['dich_chuyen_frame_n']})"
                      "  [0,00 = ô ĐỨNG YÊN rồi nhảy; ~1-2 = trượt đều]")
            if r["dai_buoc_nhay"]:
                tong = sum(r["dai_buoc_nhay"].values())
                phan = " · ".join(f"{k}: {v} ({100 * v / tong:.0f} %)"
                                  for k, v in sorted(r["dai_buoc_nhay"].items()))
                print(f"  phân bố bước nhảy ({tong} lần): {phan}")
            if r["nhay_sau_gap_n"]:
                print(f"  nhảy sau khi ô biến mất rồi hiện lại (tái bám, KHÔNG phải jitter):"
                      f" max {r['nhay_sau_gap_max']} px (n={r['nhay_sau_gap_n']})")
        print(f"  ô ĐỎ (bình thường): {r['pct_o_do']} % frame · nét đứt vàng (nghi/chưa xác minh):"
              f" {r['pct_net_dut']} %")

    if not ket_qua:
        print("[loi] không đo được video nào ⇒ KHÔNG phải 'đã đo'")
        return 1

    if args.out:
        payload = {
            "lenh": "python scripts/measure_hud_jitter.py " + " ".join(args.videos),
            "do_luc": datetime.now().astimezone().isoformat(timespec="seconds"),
            "git_rev": _git("rev-parse", "--short", "HEAD") or None,
            "git_dirty_code": _git_dirty_code(),
            "buoc_lay_mau": args.buoc_lay_mau,
            "ket_qua": ket_qua,
            "ghi_chu": "Số đo trên KHUNG HÌNH VẼ RA (dò màu), không phải CSV mỗi bước VOS.",
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
        print(f"\n[artifact] {args.out} (git_rev={payload['git_rev']},"
              f" git_dirty_code={payload['git_dirty_code']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
