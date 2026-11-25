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
- Hai người gán **không xem nhãn của nhau**: server chỉ trả về nhãn của **chính người đang dán**
  (`--nguoi-gan`); nhãn của người khác chỉ đi kèm **số lượng** (không có nội dung, không có toạ độ).

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

# `LABELUI_DATA_DIR`/`LABELUI_NHAN_DIR` chỉ phục vụ E2E: bộ dữ liệu mẫu KHÔNG được track (data/* bị
# gitignore) nên `./run labeluie2e` phải tự dựng data dir tạm, nếu không nó đỏ trên clone sạch/CI.
DATA_DIR = Path(os.environ.get("LABELUI_DATA_DIR") or (REPO_ROOT / "data"))
THU_MUC_NHAN = Path(os.environ.get("LABELUI_NHAN_DIR") or (DATA_DIR / "nhan"))
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
    # `utf-8-sig`: CSV đi qua Excel có BOM ⇒ mọi `r.get("frame_idx")` là None ⇒ nhãn dồn hết vào bước 0
    # mà KHÔNG có lỗi nào (đã bị review bắt). Không được đọc bằng "utf-8" trần.
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    if not rows:
        raise ValueError(f"{csv_path.name}: CSV rỗng")
    frames = []
    t = 0.0
    truoc = -1
    khong_tang = False
    for r in rows:
        if (r.get("frame_idx") or "").strip() == "":
            raise ValueError(f"{csv_path.name}: thiếu cột `frame_idx` (hoặc cột rỗng) — "
                             "nhãn sẽ dồn vào bước 0 nên tool từ chối phục vụ phiên này")
        lat = _so(r.get("latency_ms")) or 0.0
        cx, cy = _so(r.get("center_x")), _so(r.get("center_y"))
        w, h = _so(r.get("bbox_w")) or 0.0, _so(r.get("bbox_h")) or 0.0
        bbox = None
        if cx is not None and cy is not None and w > 0 and h > 0:
            bbox = [round(cx - w / 2), round(cy - h / 2), round(cx + w / 2), round(cy + h / 2)]
        fv = int(float(r["frame_idx"]))
        if fv <= truoc:
            khong_tang = True          # frame_idx lặp/giảm: HỢP LỆ (nguồn file lặp quay về 0) nhưng phải
        truoc = fv                     # cảnh báo, và `buoc` (số thứ tự dòng) mới là danh tính của bước
        frames.append({
            "buoc": len(frames),
            "frame_vos": fv,
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
        "csv": duong_dan_gon(csv_path),
        "video": video.name if video.is_file() else None,
        "frames": frames,
        "tong_latency_s": round(t, 2),
        "canh_bao": ("`frame_idx` lặp hoặc không tăng — nhãn vẫn phân biệt được vì mỗi bước có `buoc` "
                     "riêng (số thứ tự dòng), nhưng ĐỪNG cộng gộp theo `frame_vos`"
                     if khong_tang else None),
    }


_TEN_HOP_LE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def ten_hop_le(ten: str) -> bool:
    """Tên phiên/video chỉ được là 1 thành phần đường dẫn an toàn.

    ĐÂY LÀ CHỐT AN NINH, không phải thẩm mỹ: `POST /api/label` ghi file theo tên phiên, nên
    `phien = "../../x"` sẽ ghi ra NGOÀI `data/nhan/` (đã từng đúng dạng này ở đường `/video` trước
    khi có kiểm). Chặn cả `/`, `\\`, `..`, đường dẫn tuyệt đối, drive letter, ký tự NUL.
    """
    return bool(ten) and bool(_TEN_HOP_LE.fullmatch(ten)) and ".." not in ten


def duong_dan_gon(p: Path) -> str:
    """Đường dẫn gọn để IN ra. `relative_to` ném khi thư mục nhãn nằm ngoài repo (`LABELUI_NHAN_DIR`
    trỏ /tmp) ⇒ phải bọc, nếu không tool chết ngay sau khi GHI XONG file (đã gặp thật)."""
    try:
        return str(Path(p).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def _trong_repo(p: Path) -> bool:
    try:
        Path(p).resolve().relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


def liet_ke_phien() -> list[dict]:
    """Các phiên có cả CSV + video, mới nhất trước, kèm số nhãn đã có.

    Tên file lạ (bắt đầu bằng `_`/`.`, có dấu tiếng Việt) bị **BỎ QUA**, không được ném: đây là
    đường liệt kê thư mục, một file rác mà làm `/api/sessions` 500 là cả tool không mở được.
    """
    ra = []
    for csv_path in sorted(DATA_DIR.glob("*_metrics.csv"), reverse=True):
        ten = csv_path.name.replace("_metrics.csv", "")
        if not ten_hop_le(ten):
            continue
        video = csv_path.with_name(ten + "_web.mp4")
        if not video.is_file():
            video = csv_path.with_name(ten + ".mp4")
        if not video.is_file():
            continue
        da_gan = len(doc_nhan(ten))
        # `chua_xac_minh` KHÔNG có cột trong CSV metrics (chỉ có tổng trong `run_info`) ⇒ đọc từ đây để
        # người dán biết phiên này có bao nhiêu frame "vẽ nhưng chưa xác minh" (đại lượng KHÁC `nghi`).
        ri = csv_path.with_name(ten + "_run_info.json")
        cxm = None
        try:
            cxm = json.loads(ri.read_text(encoding="utf-8")).get("chua_xac_minh_n")
        except (OSError, ValueError):
            pass
        ra.append({"phien": ten, "csv": csv_path.name, "video": video.name, "da_gan": da_gan,
                   "chua_xac_minh_n": cxm})
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
    if record.get("frame_vos") in (None, "") and record.get("buoc") in (None, ""):
        raise ValueError("thiếu `frame_vos`/`buoc` — nhãn không gắn được vào bước nào")
    bbox = record.get("bbox_dung")
    if bbox is not None:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            raise ValueError(f"`bbox_dung` phải là [x1,y1,x2,y2] (4 số); nhận {bbox!r}")
        try:
            b = [int(round(float(v))) for v in bbox]
        except (TypeError, ValueError, OverflowError) as e:
            raise ValueError(f"`bbox_dung` có phần tử không phải số: {bbox!r}") from e
        if b[2] <= b[0] or b[3] <= b[1]:
            raise ValueError(f"`bbox_dung` phải có x2>x1, y2>y1; nhận {bbox}")
        bbox = b
    else:
        b = None
    rec = {
        "phien": phien,
        # `buoc` = số thứ tự dòng trong CSV = DANH TÍNH của bước (duy nhất kể cả khi frame_idx lặp).
        "buoc": None if record.get("buoc") in (None, "") else int(record["buoc"]),
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
    """Đếm theo nhãn + theo NGƯỜI GÁN (mỗi người một dòng ⇒ so được 2 người độc lập).

    Nhãn là **append-only** nên một người có thể dán 2 lần cho cùng bước (bấm `2` rồi `s`). Quy tắc:
    nhãn **CUỐI** của mỗi `(bước, người)` là nhãn có hiệu lực — nếu đếm mọi dòng thì `theo_nguoi` và
    `dong_y_2_nguoi` sẽ nói về hai tập dữ liệu khác nhau (review độc lập bắt đúng lỗi này).
    """
    rows = doc_nhan(phien, thu_muc)
    hieu_luc: dict[tuple, str] = {}
    for r in rows:
        if r.get("nhan") in NHAN:
            khoa = r.get("buoc") if r.get("buoc") is not None else int(r["frame_vos"])
            hieu_luc[(khoa, r.get("nguoi_gan") or "?")] = r["nhan"]
    theo_nguoi: dict[str, dict] = {}
    ban: dict[object, dict[str, str]] = {}
    for (buoc, nguoi), nhan in hieu_luc.items():
        d = theo_nguoi.setdefault(nguoi, {"tong": 0, **{k: 0 for k in NHAN}})
        d[nhan] += 1
        d["tong"] += 1
        ban.setdefault(buoc, {})[nguoi] = nhan
    dong_y = None
    if len(theo_nguoi) >= 2:
        chung = [v for v in ban.values() if len(v) >= 2]
        dong_y = {
            "so_buoc_ca_hai": len(chung),
            "so_buoc_dong_y": sum(1 for v in chung if len(set(v.values())) == 1),
        }
    return {"phien": phien, "tong_nhan": len(rows), "so_nhan_hieu_luc": len(hieu_luc),
            "so_nhan_trung": len(rows) - len(hieu_luc), "so_buoc_da_dan": len(ban),
            "theo_nguoi": theo_nguoi, "so_nguoi": len(theo_nguoi), "dong_y_2_nguoi": dong_y}


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
        p = DATA_DIR / ten
        if not p.is_file():
            return self._json({"loi": f"không có {ten}"}, 404)
        data = p.read_bytes()
        # Range request: Chrome cần nó để tua (không có thì `currentTime` không nhảy).
        ra = self.headers.get("Range")
        if ra and ra.startswith("bytes="):
            # `bytes=-500` (suffix) KHÔNG được hiểu thành `start=0`: Chrome dùng dạng này khi tua lùi.
            try:
                a, _, b = ra[6:].partition("-")
                if a == "" and b != "":
                    dai = int(b)
                    start = max(0, len(data) - dai)
                    end = len(data) - 1
                else:
                    start = int(a or 0)
                    end = int(b) if b else len(data) - 1
            except ValueError:
                start, end = 0, len(data) - 1
            if start >= len(data):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(data)}")
                self.end_headers()
                return
            start = max(0, start)
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
            p = DATA_DIR / f"{ten}_metrics.csv"
            if not p.is_file():
                return self._json({"loi": f"không có {p.name}"}, 404)
            try:
                d = doc_phien(p)
            except ValueError as e:                    # CSV bẩn (BOM, thiếu cột, không tăng dần)
                return self._json({"loi": str(e)}, 400)
            # ĐỘC LẬP THẬT: chỉ trả nhãn của CHÍNH người đang dán; nhãn người khác chỉ đi kèm SỐ LƯỢNG.
            # Trước đây server trả hết rồi UI ẩn bằng CSS ⇒ mở DevTools là thấy, "2 người độc lập" thành giả.
            tat_ca = doc_nhan(ten)
            cua_toi = [r for r in tat_ca if (r.get("nguoi_gan") or "") == self.nguoi_gan]
            d["da_gan"] = cua_toi
            d["so_nhan_nguoi_khac"] = len(tat_ca) - len(cua_toi)
            d["nguoi_khac"] = sorted({r.get("nguoi_gan") for r in tat_ca
                                      if (r.get("nguoi_gan") or "") != self.nguoi_gan} - {None})
            return self._json(d)
        return self._json({"loi": "không có route"}, 404)

    # Origin được phép: server chỉ phục vụ đúng trang của nó. Trang web khác KHÔNG được ghi nhãn vào
    # phiên đang dán — file nhãn là BẰNG CHỨNG, bị chèn dòng là hỏng cả kết luận (review độc lập P1).
    ORIGIN_CHO = {"", "null"}          # "" = không gửi Origin (curl/tool), "null" = file://

    def _origin_hop_le(self) -> bool:
        o = self.headers.get("Origin") or ""
        if o in self.ORIGIN_CHO:
            return True
        return urlparse(o).netloc == (self.headers.get("Host") or "")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/label":
            return self._json({"loi": "không có route"}, 404)
        if not self._origin_hop_le():
            return self._json({"loi": "Origin lạ — không nhận nhãn từ trang web khác"}, 403)
        # Bắt buộc `application/json`: một request "simple" (text/plain, no-cors) KHÔNG được phép đổi
        # Content-Type, nên luật này buộc trình duyệt phải preflight ⇒ chặn được kiểu chèn mù.
        if "application/json" not in (self.headers.get("Content-Type") or "").lower():
            return self._json({"loi": "Content-Type phải là application/json"}, 415)
        # Trần kích thước body: một nhãn chỉ vài trăm byte; không chặn thì client lỗi (hoặc ác ý) khai
        # `Content-Length: 10^9` là server cấp phát theo ⇒ treo cả tiến trình đang dán nhãn.
        TRAN_BODY = 64 * 1024
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"loi": "Content-Length không phải số"}, 400)
        if n < 0 or n > TRAN_BODY:
            return self._json({"loi": f"body quá lớn (>{TRAN_BODY} byte)"}, 413)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, OSError):
            return self._json({"loi": "body không phải JSON"}, 400)
        if not isinstance(body, dict):
            return self._json({"loi": "body phải là object JSON"}, 400)
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


def tao_server(port: int = DEFAULT_PORT, nguoi_gan: str = "?", phien_mac_dinh: str | None = None,
               host: str = "127.0.0.1"):
    """`host` mặc định 127.0.0.1 (chỉ máy này). WSL2 thường chia cổng với Windows nên vẫn mở được từ
    Chrome Windows; nếu không, chạy `--host 0.0.0.0` rồi mở `http://<IP-WSL>:<cổng>`."""
    handler = type("H", (_Handler,), {"nguoi_gan": nguoi_gan, "phien_mac_dinh": phien_mac_dinh})
    return ThreadingHTTPServer((host, port), handler)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="UI gán nhãn 'bắt đúng/sai' cho phiên đã quay.")
    ap.add_argument("--nguoi-gan", default=None, help="tên người dán (bắt buộc khi dán thật)")
    ap.add_argument("--phien", default=None,
                    help="mở sẵn 1 phiên (tên phiên, hoặc tên/đường dẫn file `…_metrics.csv`)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1",
                    help="mặc định 127.0.0.1; dùng 0.0.0.0 nếu Chrome Windows không mở được")
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
        print(f"\n[artifact] {duong_dan_gon(out)}")
        return 0 if d["tong_nhan"] else 1

    nguoi = (args.nguoi_gan or "").strip() or "?"
    if nguoi == "?":
        print("[canh bao] chưa có --nguoi-gan ⇒ nhãn sẽ ghi '?' và KHÔNG trích vào báo cáo được "
              "(cần biết ai dán để so 2 người độc lập).")
    mo_san = None
    if args.phien:
        # Chấp nhận `demoip_x`, `demoip_x_metrics.csv`, `data/demoip_x_metrics.csv` — doc hứa thế,
        # code cũ so sánh trực tiếp với tên trần nên đưa tên CSV vào là KHÔNG chọn gì (review P3).
        mo_san = Path(str(args.phien).replace("\\", "/")).name.replace("_metrics.csv", "")
        if not ten_hop_le(mo_san):
            print(f"[labelui] --phien không hợp lệ: {args.phien!r}")
            mo_san = None
    srv = tao_server(args.port, nguoi, mo_san, args.host)
    port = srv.server_address[1]
    dia_chi = "127.0.0.1" if args.host in ("127.0.0.1", "localhost", "0.0.0.0") else args.host
    print(f"[labelui] mở http://{dia_chi}:{port}  (người gán: {nguoi}, host {args.host})")
    if args.host == "0.0.0.0":
        try:
            import socket
            ip = socket.gethostbyname(socket.gethostname())
            print(f"[labelui] hoặc http://{ip}:{port} (từ máy khác trong LAN)")
        except OSError:
            pass
    print(f"[labelui] nhãn ghi vào {duong_dan_gon(THU_MUC_NHAN)}/<phiên>.jsonl")
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
