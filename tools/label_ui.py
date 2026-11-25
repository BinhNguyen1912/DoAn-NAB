#!/usr/bin/env python3
"""UI GÁN NHÃN "hệ bắt ĐÚNG hay SAI" trên một phiên đã quay — mở trên trình duyệt.

Vì sao có công cụ này (25-11, người dùng yêu cầu): mọi tuyên bố về cổng "nghi đổi đối tượng" đang dựa
trên nhãn do **1 người** đọc video, mà AGENTS §6 nói muốn TRÍCH số thì phải có người thứ 2 dán **độc
lập**. Cách dán hiện tại là mở video bằng trình phát rồi ghi giấy — vừa chậm vừa không có provenance
(ai dán, lúc nào, trên `git_rev` nào, ở giây thứ mấy).

Khác `scripts/gt_gan_nhanh.py` (tô **mask** trên CLIP sạch): video của phiên `./run demoip` **đã cháy HUD**
nên không tô mask được nữa; thứ gán được — và đúng thứ cần — là **phán quyết theo từng bước VOS**:
`dung` / `sai` / `mat_dau` / `khong_co_vat`, kèm **ô đúng** (kéo chuột) khi hệ bắt sai.

Nguyên tắc (để số dán ra dùng được):
- Mỗi nhãn lưu **append-only** vào `data/nhan/<phiên>.jsonl` (không ghi đè lịch sử của người khác);
  mỗi dòng có `nguoi_gan`, `git_rev`, `do_luc`, `frame_vos`, `t_video` **thực tế** người gán đang xem.
- `t_video` lấy từ **đồng hồ của chính video** (truth), còn `t_uoc_luong` = **cộng dồn `latency_ms`**
  của CSV — vì chia đều `thời lượng / số_frame` lệch tới **12 s** trên phiên 98 s (AGENTS §6).
- Hai người gán **không xem nhãn của nhau**: nhãn của người khác chỉ hiện khi bấm `--hien-nhan-khac`.

Chạy:
    ./run labelui                      # rồi mở link script in ra (mặc định http://127.0.0.1:8770)
    ./run labelui --nguoi-gan Binh     # ghi rõ ai dán (bắt buộc để số trích được)
    ./run labelui --phien data/demoip_1125-121456_metrics.csv

Tổng hợp sau khi dán (in ra + ghi `data/nhan/<phiên>_tonghop.json`):
    python tools/label_ui.py --tong-hop data/demoip_1125-121456_metrics.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]

THU_MUC_NHAN = Path(os.environ.get("LABELUI_NHAN_DIR") or (REPO_ROOT / "data" / "nhan"))
HTML = Path(__file__).resolve().with_name("label_ui.html")

# Tập nhãn ĐÓNG — thêm nhãn mới phải sửa cả `label_ui.html` và `tests/test_label_ui.py`.
NHAN = {
    "dung": "Ô/mask nằm ĐÚNG trên vật đã chọn",
    "sai": "Ô/mask nằm trên vùng KHÁC (nền, tay, vật khác)",
    "mat_dau": "Vật CÒN trong khung nhưng hệ không vẽ gì (mask rỗng)",
    "khong_co_vat": "Vật KHÔNG có trong khung (người dùng đã đưa ra ngoài)",
    "bo_qua": "Không kết luận được ở frame này (mờ, che kín, không thấy rõ)",
}
DEFAULT_PORT = 8770


# ── đọc phiên ────────────────────────────────────────────────────────────────────────────────────
def _so(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def doc_phien(csv_path: Path) -> dict:
    """CSV metrics ⇒ `{phien, video, frames:[…], tong_latency_s}`.

    `t_uoc_luong` = **cộng dồn** `latency_ms` (thời điểm bước VOS đó được vẽ ra) — KHÔNG chia đều:
    phiên `demoip_1125-121456` (295 bước / 98,3 s) chia đều cho f141 ≈ 46,6 s còn cộng dồn cho **34,9 s**
    (lệch 12 s) vì các bước dài ngắn khác nhau (1291–1771 ms ở f195–197). Gán nhãn vào sai frame là
    hỏng cả bộ nhãn (AGENTS §6).
    """
    csv_path = Path(csv_path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    frames = []
    t = 0.0
    for r in rows:
        lat = _so(r.get("latency_ms")) or 0.0
        cx, cy = _so(r.get("center_x")), _so(r.get("center_y"))
        w, h = _so(r.get("bbox_w")) or 0.0, _so(r.get("bbox_h")) or 0.0
        bbox = None
        if cx is not None and cy is not None and w > 0 and h > 0:
            bbox = [round(cx - w / 2), round(cy - h / 2), round(cx + w / 2), round(cy + h / 2)]
        frames.append({
            "frame_vos": int(float(r.get("frame_idx") or 0)),
            "t_uoc_luong": round(t, 2),
            "latency_ms": round(lat, 1),
            "bbox": bbox,
            "mask_area": _so(r.get("mask_area")),
            "may_an_mask": (r.get("nghi_doi_tuong") or "").strip() == "1",
        })
        t += lat / 1000.0
    ten = csv_path.name.replace("_metrics.csv", "")
    video = csv_path.with_name(ten + "_web.mp4")
    if not video.is_file():
        video = csv_path.with_name(ten + ".mp4")
    return {
        "phien": ten,
        "csv": str(csv_path.relative_to(REPO_ROOT)) if _trong_repo(csv_path) else str(csv_path),
        "video": video.name if video.is_file() else None,
        "frames": frames,
        "tong_latency_s": round(t, 2),
    }


_TEN_HOP_LE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def ten_hop_le(ten: str) -> bool:
    """Tên phiên/video chỉ được là 1 thành phần đường dẫn an toàn.

    ĐÂY LÀ CHỐT AN NINH, không phải thẩm mỹ: `POST /api/label` ghi file theo tên phiên, nên
    `phien = "../../x"` sẽ ghi ra NGOÀI `data/nhan/` (đã từng đúng dạng này ở đường `/video` trước
    khi có kiểm). Chặn cả `/`, `\\`, `..`, đường dẫn tuyệt đối, drive letter, ký tự NUL.
    """
    return bool(ten) and bool(_TEN_HOP_LE.fullmatch(ten)) and ".." not in ten


def _trong_repo(p: Path) -> bool:
    try:
        Path(p).resolve().relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


def liet_ke_phien() -> list[dict]:
    """Các phiên có cả CSV + video, mới nhất trước, kèm số nhãn đã có."""
    ra = []
    for csv_path in sorted((REPO_ROOT / "data").glob("*_metrics.csv"), reverse=True):
        ten = csv_path.name.replace("_metrics.csv", "")
        video = csv_path.with_name(ten + "_web.mp4")
        if not video.is_file():
            video = csv_path.with_name(ten + ".mp4")
        if not video.is_file():
            continue
        da_gan = len(doc_nhan(ten))
        ra.append({"phien": ten, "csv": csv_path.name, "video": video.name, "da_gan": da_gan})
    return ra


# ── lưu / đọc nhãn ───────────────────────────────────────────────────────────────────────────────
def _gio_nhan(phien: str, thu_muc: Path | None = None) -> Path:
    if not ten_hop_le(phien):
        raise ValueError(f"tên phiên không hợp lệ: {phien!r}")
    thu_muc = Path(thu_muc) if thu_muc else THU_MUC_NHAN
    return thu_muc / f"{phien}.jsonl"


def _git_rev() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def doc_nhan(phien: str, thu_muc: Path | None = None) -> list[dict]:
    p = _gio_nhan(phien, thu_muc)
    if not p.is_file():
        return []
    ra = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ra.append(json.loads(line))
        except ValueError:
            continue          # dòng hỏng (ghi dở) không được làm sập UI
    return ra


def ghi_nhan(phien: str, record: dict, nguoi_gan: str, thu_muc: Path | None = None) -> dict:
    """Ghi MỘT nhãn (append-only). Trả record đã chuẩn hoá (để UI hiện lại được)."""
    if not nguoi_gan or not str(nguoi_gan).strip():
        raise ValueError("thiếu `nguoi_gan` — số dán mà không nói ai dán thì không trích được (AGENTS §9.1)")
    nhan = str(record.get("nhan") or "").strip()
    if nhan not in NHAN:
        raise ValueError(f"nhãn không hợp lệ: {nhan!r}; chỉ nhận {sorted(NHAN)}")
    bbox = record.get("bbox_dung")
    if bbox is not None:
        b = [int(round(float(v))) for v in bbox]
        if len(b) != 4 or b[2] <= b[0] or b[3] <= b[1]:
            raise ValueError(f"`bbox_dung` phải là [x1,y1,x2,y2] với x2>x1, y2>y1; nhận {bbox}")
        bbox = b
    else:
        b = None
    rec = {
        "phien": phien,
        "frame_vos": int(record.get("frame_vos") or 0),
        "t_video": round(float(record.get("t_video") or 0.0), 3),
        "t_uoc_luong": (None if record.get("t_uoc_luong") is None
                        else round(float(record["t_uoc_luong"]), 2)),
        "nhan": nhan,
        "bbox_dung": b,
        "nguoi_gan": str(nguoi_gan).strip(),
        "git_rev": _git_rev(),
        "do_luc": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    p = _gio_nhan(phien, thu_muc)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def tong_hop(phien: str, thu_muc: Path | None = None) -> dict:
    """Đếm theo nhãn + theo NGƯỜI GÁN (mỗi người một dòng ⇒ so được 2 người độc lập)."""
    rows = doc_nhan(phien, thu_muc)
    theo_nguoi: dict[str, dict] = {}
    for r in rows:
        n = r.get("nguoi_gan") or "?"
        d = theo_nguoi.setdefault(n, {"tong": 0, **{k: 0 for k in NHAN}})
        if r.get("nhan") in d:
            d[r["nhan"]] += 1
        d["tong"] += 1
    dong_y = None
    if len(theo_nguoi) >= 2:
        # chỉ tính trên khung MÀ CẢ HAI cùng dán
        ban = {}
        for r in rows:
            ban.setdefault(int(r["frame_vos"]), {}).setdefault(r.get("nguoi_gan") or "?", r["nhan"])
        chung = [v for v in ban.values() if len(v) >= 2]
        dong_y = {
            "so_frame_ca_hai": len(chung),
            "so_frame_dong_y": sum(1 for v in chung if len(set(v.values())) == 1),
        }
    return {"phien": phien, "tong_nhan": len(rows), "theo_nguoi": theo_nguoi,
            "so_nguoi": len(theo_nguoi), "dong_y_2_nguoi": dong_y}


# ── HTTP ─────────────────────────────────────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    nguoi_gan = "?"
    phien_mac_dinh: str | None = None

    def log_message(self, *a):        # im lặng: không rác terminal khi người dùng đang dán
        return

    def _json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, data: bytes, ctype: str, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _video(self, query):
        ten = (query.get("v") or [""])[0]
        if not ten_hop_le(ten) or not ten.endswith(".mp4"):
            return self._json({"loi": "tên video không hợp lệ"}, 400)
        p = REPO_ROOT / "data" / ten
        if not p.is_file():
            return self._json({"loi": f"không có {ten}"}, 404)
        data = p.read_bytes()
        # Range request: Chrome cần nó để tua (không có thì `currentTime` không nhảy).
        ra = self.headers.get("Range")
        if ra and ra.startswith("bytes="):
            try:
                a, _, b = ra[6:].partition("-")
                start = int(a or 0)
                end = int(b) if b else len(data) - 1
            except ValueError:
                start, end = 0, len(data) - 1
            end = min(end, len(data) - 1)
            chunk = data[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk)
            return
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            if not HTML.is_file():
                return self._bytes(b"thieu tools/label_ui.html", "text/plain; charset=utf-8", 500)
            return self._bytes(HTML.read_bytes(), "text/html; charset=utf-8")
        if u.path == "/favicon.ico":
            # Trình duyệt luôn xin file này; trả 204 để console sạch (e2e coi console.error là HỎNG).
            self.send_response(204)
            self.end_headers()
            return
        if u.path == "/video":
            return self._video(q)
        if u.path == "/api/sessions":
            return self._json({"phien": liet_ke_phien(), "phien_mac_dinh": self.phien_mac_dinh,
                               "nguoi_gan": self.nguoi_gan, "nhan": NHAN})
        if u.path == "/api/frames":
            ten = (q.get("phien") or [""])[0]
            if not ten_hop_le(ten):
                return self._json({"loi": "tên phiên không hợp lệ"}, 400)
            p = REPO_ROOT / "data" / f"{ten}_metrics.csv"
            if not p.is_file():
                return self._json({"loi": f"không có {p.name}"}, 404)
            d = doc_phien(p)
            d["da_gan"] = doc_nhan(ten)
            return self._json(d)
        return self._json({"loi": "không có route"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/label":
            return self._json({"loi": "không có route"}, 404)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, OSError):
            return self._json({"loi": "body không phải JSON"}, 400)
        phien = str(body.get("phien") or "").strip()
        if not phien:
            return self._json({"loi": "thiếu `phien`"}, 400)
        if not ten_hop_le(phien):
            return self._json({"loi": "tên phiên không hợp lệ"}, 400)
        try:
            rec = ghi_nhan(phien, body, self.nguoi_gan)
        except ValueError as e:
            return self._json({"loi": str(e)}, 400)
        return self._json({"ok": True, "record": rec, "tong_hop": tong_hop(phien)})


def tao_server(port: int = DEFAULT_PORT, nguoi_gan: str = "?", phien_mac_dinh: str | None = None):
    handler = type("H", (_Handler,), {"nguoi_gan": nguoi_gan, "phien_mac_dinh": phien_mac_dinh})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="UI gán nhãn 'bắt đúng/sai' cho phiên đã quay.")
    ap.add_argument("--nguoi-gan", default=None, help="tên người dán (bắt buộc khi dán thật)")
    ap.add_argument("--phien", default=None,
                    help="mở sẵn 1 phiên (tên `…_metrics.csv` hoặc tên phiên)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--tong-hop", default=None, metavar="CSV",
                    help="KHÔNG mở server: in + ghi bản tổng hợp nhãn của phiên này")
    args = ap.parse_args(argv)

    if args.tong_hop:
        p = Path(args.tong_hop)
        if not p.is_absolute():
            p = REPO_ROOT / p if (REPO_ROOT / p).exists() else p
        ten = p.name.replace("_metrics.csv", "").replace(".csv", "")
        d = tong_hop(ten)
        print(json.dumps(d, ensure_ascii=False, indent=2))
        out = THU_MUC_NHAN / f"{ten}_tonghop.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"phien": ten, "git_rev": _git_rev(),
                                   "do_luc": datetime.now().astimezone().isoformat(timespec="seconds"),
                                   **d}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n[artifact] {out.relative_to(REPO_ROOT)}")
        return 0 if d["tong_nhan"] else 1

    nguoi = (args.nguoi_gan or "").strip() or "?"
    if nguoi == "?":
        print("[canh bao] chưa có --nguoi-gan ⇒ nhãn sẽ ghi '?' và KHÔNG trích vào báo cáo được "
              "(cần biết ai dán để so 2 người độc lập).")
    srv = tao_server(args.port, nguoi, args.phien)
    port = srv.server_address[1]
    print(f"[labelui] mở http://127.0.0.1:{port}  (người gán: {nguoi})")
    try:
        noi = THU_MUC_NHAN.relative_to(REPO_ROOT)
    except ValueError:                 # thư mục tạm (e2e) nằm ngoài repo
        noi = THU_MUC_NHAN
    print(f"[labelui] nhãn ghi vào {noi}/<phiên>.jsonl")
    print("[labelui] Ctrl-C để dừng")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[labelui] dừng")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
