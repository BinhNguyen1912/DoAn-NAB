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
import unicodedata
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:      # `python tools/label_ui.py` ⇒ sys.path[0] là tools/
    sys.path.insert(0, str(REPO_ROOT))

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


_CACHE_PHIEN: dict[tuple, dict] = {}


def doc_phien_cached(csv_path: Path) -> dict:
    """`doc_phien` + cache theo `(đường dẫn, mtime, kích thước)`.

    `do_POST` phải đối chiếu `buoc` với CSV ở MỖI nhãn (review vòng 2, P2-5); parse lại không cache đo
    được 1,3 ms cho 295 dòng nhưng **169 ms cho 50 000 dòng** — người dán sẽ thấy độ trễ mỗi lần bấm
    phím. Cache vẫn đúng khi CSV bị ghi lại: mtime/size đổi ⇒ khoá đổi.
    """
    p = Path(csv_path)
    st = p.stat()
    khoa = (str(p.resolve()), st.st_mtime_ns, st.st_size)
    if khoa not in _CACHE_PHIEN:
        if len(_CACHE_PHIEN) > 8:            # đừng để cache phình theo số phiên đã mở
            _CACHE_PHIEN.clear()
        _CACHE_PHIEN[khoa] = doc_phien(p)
    return _CACHE_PHIEN[khoa]


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


def video_de_phat(ten: str) -> tuple[str | None, bool | None, str | None]:
    """Trả `(tên file cho <video>, là_H.264, ghi chú)`.

    Chrome **không giải mã `mp4v`** (bản ghi cũ, 93/130 phiên không có `_web.mp4`) ⇒ `<video>` đen thui
    nhưng tool vẫn cho dán nhãn "mù" lên bước 0 (gặp thật 25-11, người dùng gửi ảnh). Nay: thiếu bản H.264
    thì **chuyển mã ngay** bằng chính `transcode_for_web` của repo (đã dùng cho `_web.mp4`), và nói rõ nếu
    không chuyển được (thiếu ffmpeg) để UI CHẶN dán nhãn.
    """
    web = DATA_DIR / f"{ten}_web.mp4"
    if web.is_file() and web.stat().st_size > 0:
        return web.name, True, None
    goc = DATA_DIR / f"{ten}.mp4"
    if not goc.is_file():
        return None, None, f"không có file mp4 cho phiên {ten}"
    try:
        from src.worker import transcode_for_web
        ra = transcode_for_web(goc, web)
    except (ImportError, OSError) as e:                  # pragma: no cover - phụ thuộc môi trường
        ra = None
        ghi_chu = f"lỗi khi chuyển mã: {e}"
    else:
        ghi_chu = None
    if ra and web.is_file() and web.stat().st_size > 0:
        return web.name, True, f"đã chuyển mã {goc.name} → {web.name} (H.264) để trình duyệt phát được"
    return goc.name, False, (ghi_chu or "KHÔNG chuyển mã được (thiếu ffmpeg?) — file gốc là mp4v, "
                                       "Chrome KHÔNG phát được")


# ── ẢNH TỪNG BƯỚC (dán nhanh: không phải bấm dừng video) ──────────────────────────────────────────
# Vì sao: tua + dừng video rồi chấm từng bước rất chậm (mỗi lần seek 40–60 ms + phải bấm Space hai lần),
# và bản ghi cũ (mp4v) thì Chrome không phát được luôn. Ảnh tĩnh lấy sẵn ra JPEG: `←/→` là đổi ảnh ngay,
# không có khái niệm "đang phát".
ANH_DIR_NAME = ".anh"          # nằm trong thư mục nhãn; bắt đầu bằng "." để không bị liệt kê là phiên
_CAP: dict[str, tuple] = {}    # ten -> (VideoCapture, fps, n_frames)
# OpenCV/FFmpeg **KHÔNG thread-safe** cho một `VideoCapture`: prefetch 4 ảnh song song (4 request của
# `ThreadingHTTPServer`) từng làm `Assertion fctx->async_lock failed at libavcodec/pthread_frame.c:174`
# và **abort cả tiến trình**. Mọi truy cập capture đi qua khoá này.
_CAP_LOCK = threading.Lock()


def _mo_video(ten: str):
    """Mở (và giữ) `VideoCapture` cho phiên; trả `(cap, fps, n_frames)` hoặc `None`.

    Gọi dưới `_CAP_LOCK` (xem `anh_buoc`) — hàm này chỉ ĐỌC/ghi dict, không seek.
    """
    if ten in _CAP:
        return _CAP[ten]
    import cv2
    # Ưu tiên FILE GỐC: `cv2` đọc được cả `mp4v` (Chrome thì không), nên KHÔNG cần chuyển mã.
    # `video_de_phat()` có thể transcode cả clip (0,5–30 s) — gọi nó ở đây sẽ làm ảnh ĐẦU TIÊN treo
    # lâu vô ích, đúng thứ chế độ ảnh sinh ra để tránh.
    ung_vien = [DATA_DIR / f"{ten}.mp4"]
    if not ung_vien[0].is_file():
        ten_video, _, _ = video_de_phat(ten)
        if ten_video:
            ung_vien.append(DATA_DIR / ten_video)
    cap = None
    for p in ung_vien:
        if not p.is_file():
            continue
        cap = cv2.VideoCapture(str(p))
        if cap.isOpened():
            break
        cap.release()
        cap = None
    if cap is None:
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    if fps <= 0 or n <= 0:
        cap.release()
        return None
    if len(_CAP) > 2:                       # giữ tối đa 3 phiên đang mở
        _CAP.clear()
    _CAP[ten] = (cap, fps, n)
    return _CAP[ten]


def chi_so_khung(phien: str, buoc: int) -> tuple[int | None, str | None]:
    """Bước VOS `buoc` ⇒ CHỈ SỐ FRAME trong video (kèm lý do nếu không tính được).

    Dùng đúng phép bù của UI: `t_map = t_uoc_luong × (thời lượng video / tổng latency)` — chia đều
    `thời lượng/số_bước` lệch tới 12 s trên phiên 98 s (AGENTS §6).
    """
    mo = _mo_video(phien)
    if not mo:
        return None, "không mở được video"
    _, fps, n = mo
    try:
        d = doc_phien_cached(DATA_DIR / f"{phien}_metrics.csv")
    except (OSError, ValueError) as e:
        return None, f"không đọc được CSV: {e}"
    if not 0 <= buoc < len(d["frames"]):
        return None, f"buoc ngoài dải 0..{len(d['frames']) - 1}"
    thoi_luong = n / fps
    tong = d["tong_latency_s"] or 0.0
    he_so = min(2.0, max(0.5, thoi_luong / tong)) if tong > 1 and thoi_luong > 1 else 1.0
    t = d["frames"][buoc]["t_uoc_luong"] * he_so
    return int(round(t * fps)), None


def anh_buoc(phien: str, buoc: int) -> tuple[bytes | None, str | None]:
    """JPEG của khung hình tại bước `buoc` (cache trên đĩa, lần 2 trả ngay)."""
    if not ten_hop_le(phien):
        return None, "tên phiên không hợp lệ"
    try:
        buoc = int(buoc)
    except (TypeError, ValueError):
        return None, "buoc phải là số nguyên"
    thu_muc = THU_MUC_NHAN / ANH_DIR_NAME / phien
    tep = thu_muc / f"{buoc:06d}.jpg"
    if tep.is_file() and tep.stat().st_size > 0:
        return tep.read_bytes(), None
    idx, loi = chi_so_khung(phien, buoc)
    if idx is None:
        return None, loi
    import cv2
    with _CAP_LOCK:                      # seek+read TUẦN TỰ: FFmpeg không chịu được truy cập song song
        mo = _mo_video(phien)
        if not mo:
            return None, "không mở được video"
        cap, _, n = mo
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(idx, int(n) - 1)))
        ok, khung = cap.read()
    if not ok or khung is None:
        return None, f"không đọc được frame {idx} của video"
    # Thu nhỏ còn ≤ 960 px ngang: đủ nét để thấy ô/mask, nhẹ để `←/→` không phải chờ.
    h, w = khung.shape[:2]
    if w > 960:
        khung = cv2.resize(khung, (960, int(round(h * 960 / w))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", khung, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None, "không nén được JPEG"
    du_lieu = buf.tobytes()
    try:
        thu_muc.mkdir(parents=True, exist_ok=True)
        tep.write_bytes(du_lieu)
    except OSError:
        pass                                  # cache là tiện ích; không ghi được vẫn phải trả ảnh
    return du_lieu, None


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
                   "chua_xac_minh_n": cxm,
                   # `web` = đã có bản H.264? Nếu False thì lần mở tới sẽ phải chuyển mã (vài giây)
                   "web": (csv_path.with_name(ten + "_web.mp4")).is_file()})
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


def khoa_ten(ten: str) -> str:
    """Khoá GỘP người dán: NFC + casefold.

    Không có nó thì một người gõ lại tên với chữ hoa khác (`Binh` rồi `binh`) thành **2 người**, và
    `--tong-hop` in "2/2 người đồng ý" + thoát mã 0 cho **một** người (review vòng 3, P2-8).
    """
    return unicodedata.normalize("NFC", str(ten or "")).casefold()


def chuan_hoa_ten(ten) -> str:
    """Tên người dán: bắt buộc, ≤ 40 ký tự, không được là `?`.

    KHÔNG phải ranh giới an ninh (ai cũng khai được tên bất kỳ — ranh giới an ninh là `ten_hop_le` cho
    đường dẫn). Đây là để FILE BẰNG CHỨNG có provenance đọc được, và để `tong_hop` đếm đúng số người.
    """
    t = str(ten or "").strip()
    if not t:
        raise ValueError("thiếu `nguoi_gan` — số dán mà không nói ai dán thì không trích được (AGENTS §9.1)")
    if t == "?":
        raise ValueError("`nguoi_gan` không được là '?' — hãy khai tên thật")
    if len(t) > 40:
        raise ValueError("`nguoi_gan` quá dài (>40 ký tự)")
    if any(ord(c) < 32 or ord(c) == 127 for c in t):
        raise ValueError("`nguoi_gan` chứa ký tự điều khiển (xuống dòng/tab) — không đọc được cho người")
    return t


def _so_huu_han(gia, ten_truong: str) -> float:
    """Chuyển sang float và từ chối NaN/±Infinity.

    `json.loads("{\"x\": 1e400}")` cho `inf`; `float(inf)` không ném ⇒ bản ghi ghi ra `Infinity`, thứ
    mà `json.dumps` cho qua nhưng **parser strict không đọc được** — file bằng chứng bị hỏng (review
    vòng 4, P3-10).
    """
    import math
    try:
        v = float(gia or 0.0)
    except (TypeError, ValueError, OverflowError) as e:
        raise ValueError(f"`{ten_truong}` không phải số: {gia!r}") from e
    if not math.isfinite(v):
        raise ValueError(f"`{ten_truong}` phải hữu hạn (nhận {gia!r})")
    return v


def ghi_nhan(phien: str, record: dict, nguoi_gan: str, thu_muc: Path | None = None) -> dict:
    """Ghi MỘT nhãn (append-only). Trả record đã chuẩn hoá (để UI hiện lại được)."""
    nguoi_gan = chuan_hoa_ten(nguoi_gan)
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
        "t_video": round(_so_huu_han(record.get("t_video"), "t_video"), 3),
        "t_uoc_luong": (None if record.get("t_uoc_luong") is None
                        else round(_so_huu_han(record["t_uoc_luong"], "t_uoc_luong"), 2)),
        "nhan": nhan,
        "bbox_dung": b,
        "nguoi_gan": nguoi_gan,                     # tên hiển thị (giữ nguyên chữ hoa/dấu)
        "khoa_nguoi": khoa_ten(nguoi_gan),          # khoá GỘP ⇒ "Binh"/"binh" là MỘT người
        "git_rev": _git_rev(),
        "do_luc": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    p = _gio_nhan(phien, thu_muc)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def ghi_an_toan(wfile, du_lieu: bytes) -> bool:
    """Ghi ra socket, trả False (KHÔNG ném) nếu client đã đóng kết nối.

    Chrome huỷ request `Range` giữa đường mỗi lần người dùng tua video ⇒ `write()` ném
    `ConnectionResetError: [Errno 104]`, và `http.server` in **traceback 20 dòng** vào terminal đang
    dán nhãn. Đó không phải lỗi của tool (video vẫn phát bình thường) nhưng làm người dùng tưởng hỏng.
    """
    try:
        wfile.write(du_lieu)
        return True
    except (ConnectionError, BrokenPipeError, OSError):
        return False


def _khong_nan(x):
    """Thay NaN/±Infinity bằng `None` để JSON còn đọc được (số méo ⇒ "không đo được", không phải 0)."""
    import math
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _khong_nan(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_khong_nan(v) for v in x]
    return x


def tong_hop(phien: str, thu_muc: Path | None = None) -> dict:
    """Đếm theo nhãn + theo NGƯỜI GÁN (mỗi người một dòng ⇒ so được 2 người độc lập).

    Nhãn là **append-only** nên một người có thể dán 2 lần cho cùng bước (bấm `2` rồi `s`). Quy tắc:
    nhãn **CUỐI** của mỗi `(bước, người)` là nhãn có hiệu lực — nếu đếm mọi dòng thì `theo_nguoi` và
    `dong_y_2_nguoi` sẽ nói về hai tập dữ liệu khác nhau (review độc lập bắt đúng lỗi này).
    """
    rows = doc_nhan(phien, thu_muc)
    hieu_luc: dict[tuple, str] = {}
    ten_hien_thi: dict[str, dict] = {}
    so_nhan_loi = so_thieu_buoc = so_hop_le = 0
    for r in rows:
        if not isinstance(r, dict) or r.get("nhan") not in NHAN or not r.get("nguoi_gan"):
            so_nhan_loi += 1               # dòng JSON hợp lệ nhưng không phải nhãn ⇒ KHÔNG được làm sập
            continue
        so_hop_le += 1
        # `tong_hop` chạy TRONG response của POST, sau khi nhãn đã ghi ⇒ mọi kiểu dữ liệu méo
        # (`buoc: [1]`, `buoc: "abc"`, tên lạ) phải thành "dòng lỗi", KHÔNG được ném (review vòng 3).
        try:
            # Hai KHÔNG GIAN KHOÁ khác nhau phải mang tiền tố: một dòng legacy (`frame_vos=7`, không có
            # `buoc`) không được ghi đè một bước khác (`buoc=7`) — lỗi trộn schema (review vòng 2, P2-4).
            if r.get("buoc") is not None:
                khoa = ("buoc", int(r["buoc"]))
            elif r.get("frame_vos") not in (None, ""):
                khoa = ("frame", int(r["frame_vos"]))
                so_thieu_buoc += 1
            else:
                raise ValueError("thiếu buoc/frame_vos")
            # LUÔN tính lại từ tên: tin `khoa_nguoi` đã lưu thì một dòng bị sửa tay (hoặc của bản tool
            # khác) tách một người thành hai ⇒ `so_nguoi = 2` giả + cặp "tự đồng ý với mình".
            khoa_nguoi = khoa_ten(r["nguoi_gan"])
            hieu_luc[(khoa, khoa_nguoi)] = r["nhan"]
        except (TypeError, ValueError, OverflowError):
            so_nhan_loi += 1
            so_hop_le -= 1
            continue
        hien = ten_hien_thi.setdefault(khoa_nguoi, {"ten": [], "dau": None, "cuoi": None})
        if str(r["nguoi_gan"]) not in hien["ten"]:
            hien["ten"].append(str(r["nguoi_gan"]))
        luc = r.get("do_luc")
        if luc:
            hien["dau"] = hien["dau"] or luc
            hien["cuoi"] = luc
    theo_nguoi: dict[str, dict] = {}
    ban: dict[object, dict[str, str]] = {}
    for (khoa, nguoi), nhan in hieu_luc.items():
        # Nhóm theo KHOÁ (NFC+casefold) nhưng IN theo tên hiển thị đầu tiên gặp — nếu in bằng khoá thì
        # báo cáo ghi "binh" thay vì "Binh" (và không ai nhận ra đó là mình).
        hien = ten_hien_thi.get(nguoi) or {}
        ten_in = (hien.get("ten") or [nguoi])[0]
        d = theo_nguoi.setdefault(ten_in, {"tong": 0, **{k: 0 for k in NHAN}})
        d[nhan] += 1
        d["tong"] += 1
        ban.setdefault(khoa, {})[nguoi] = nhan
    dong_y = None
    if len(theo_nguoi) >= 2:
        chung = [v for v in ban.values() if len(v) >= 2]
        # `bo_qua` KHÔNG phải một kết luận: hai người cùng bấm "không kết luận được" mà tính là "đồng ý"
        # sẽ thổi phồng đúng con số đem đi trích (review vòng 2, P2-2).
        ket_luan = [v for v in chung if all(x != "bo_qua" for x in v.values())]
        dong_y = {
            "so_buoc_ca_hai": len(chung),
            "so_buoc_ca_hai_co_ket_luan": len(ket_luan),
            "so_buoc_dong_y": sum(1 for v in ket_luan if len(set(v.values())) == 1),
            "theo_cap": _theo_cap(ban, {k: ((v.get("ten") or [k])[0])
                                        for k, v in ten_hien_thi.items()}),
        }
    return {"phien": phien, "tong_nhan": len(rows), "so_nhan_hieu_luc": len(hieu_luc),
            "so_nhan_trung": so_hop_le - len(hieu_luc), "so_nhan_loi": so_nhan_loi,
            "so_nhan_thieu_buoc": so_thieu_buoc, "so_buoc_da_dan": len(ban),
            "theo_nguoi": theo_nguoi, "so_nguoi": len(theo_nguoi),
            "ten_theo_nguoi": {k: {"ten": sorted(v["ten"]), "nhan_dau": v["dau"],
                                   "nhan_cuoi": v["cuoi"]}
                               for k, v in ten_hien_thi.items()},
            "dong_y_2_nguoi": dong_y}


def _theo_cap(ban: dict, ten: dict | None = None) -> list[dict]:
    """Đồng ý theo TỪNG CẶP người (3+ người thì `so_buoc_dong_y` là "TẤT CẢ đồng ý", không phải cặp).

    `ten` (khoá → tên hiển thị) để báo cáo đọc được: in khoá `binh` còn `theo_nguoi` in `Binh` là hai
    không-gian tên khác nhau (review vòng 4, P3-17).
    """
    import itertools

    ten = ten or {}

    def hien(k):
        return ten.get(k) or k
    nguoi = sorted({n for v in ban.values() for n in v})
    # `ban` giữ khoá; in ra tên hiển thị cho dễ đọc trong báo cáo
    ra = []
    for a, b in itertools.combinations(nguoi, 2):
        chung = [v for v in ban.values() if a in v and b in v and v[a] != "bo_qua" and v[b] != "bo_qua"]
        ra.append({"cap": [hien(a), hien(b)], "so_buoc_ca_hai_co_ket_luan": len(chung),
                   "so_buoc_dong_y": sum(1 for v in chung if v[a] == v[b])})
    return ra


# ── HTTP ─────────────────────────────────────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    nguoi_gan = "?"
    phien_mac_dinh: str | None = None

    def log_message(self, *a):        # im lặng: không rác terminal khi người dùng đang dán
        return

    def _json(self, payload, code=200):
        # `allow_nan=False`: CSV có `latency_ms`/`t_uoc_luong` = NaN/Infinity (file bị sửa tay) thì
        # `json.dumps` mặc định in ra `NaN` — KHÔNG phải JSON, Chrome `JSON.parse` ném ⇒ cả UI chết.
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        except ValueError:
            body = json.dumps(_khong_nan(payload), ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        ghi_an_toan(self.wfile, body)

    def _bytes(self, data: bytes, ctype: str, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        ghi_an_toan(self.wfile, data)

    def _video(self, query):
        ten = (query.get("v") or [""])[0]
        if not ten_hop_le(ten) or not ten.endswith(".mp4"):
            return self._json({"loi": "tên video không hợp lệ"}, 400)
        p = DATA_DIR / ten
        if not p.is_file():
            return self._json({"loi": f"không có {ten}"}, 404)
        # Đọc theo ĐOẠN, không `read_bytes()` cả file: Chrome tua = nhiều Range request, mà mỗi lần
        # đọc cả mp4 27 MB từ 9p (WSL↔Windows) là chậm và tốn I/O vô ích (review vòng 1, P3).
        dai_file = p.stat().st_size
        ra = self.headers.get("Range")
        if ra and ra.startswith("bytes="):
            # `bytes=-500` (suffix) KHÔNG được hiểu thành `start=0`: Chrome dùng dạng này khi tua lùi.
            try:
                a, _, b = ra[6:].partition("-")
                if a == "" and b != "":
                    start = max(0, dai_file - int(b))
                    end = dai_file - 1
                else:
                    start = int(a or 0)
                    end = int(b) if b else dai_file - 1
            except ValueError:
                start, end = 0, dai_file - 1
            if start >= dai_file:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{dai_file}")
                self.end_headers()
                return
            start = max(0, start)
            end = min(end, dai_file - 1)
            with p.open("rb") as f:
                f.seek(start)
                chunk = f.read(end - start + 1)
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{dai_file}")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            ghi_an_toan(self.wfile, chunk)
            return
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(dai_file))
        self.end_headers()
        with p.open("rb") as f:
            while True:
                khoi = f.read(256 * 1024)              # stream, không nạp cả file vào RAM
                if not khoi:
                    break
                if not ghi_an_toan(self.wfile, khoi):
                    return                             # client đã huỷ (tua video) — im lặng


    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if (u.path == "/video" or u.path.startswith("/api/")) and not self._host_hop_le():
            return self._json({"loi": "Host lạ — không nhận (chống DNS rebinding)"}, 403)
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
        if u.path == "/anh":
            ten = (q.get("phien") or [""])[0]
            buoc = (q.get("buoc") or ["0"])[0]
            du_lieu, loi = anh_buoc(ten, buoc)
            if du_lieu is None:
                return self._json({"loi": loi or "không lấy được ảnh"}, 404)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(du_lieu)))
            self.send_header("Cache-Control", "max-age=86400")   # ảnh của một bước là bất biến
            self.end_headers()
            ghi_an_toan(self.wfile, du_lieu)
            return
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
            # Tên người dán nay do CLIENT khai (`?nguoi=`) vì 2 người có thể dùng CHUNG một server (đó là
            # cách làm đúng tài liệu) — mặc định là tên cấu hình lúc khởi động.
            toi = (q.get("nguoi") or [""])[0].strip()
            tat_ca = [r for r in doc_nhan(ten) if isinstance(r, dict)]
            # Rỗng ⇒ KHÔNG trả nhãn của ai (bản cũ fallback về `--nguoi-gan` ⇒ người thứ 2 mở trang thấy
            # ĐÚNG nhãn của người thứ 1 — mở lại đúng lỗi P1 vòng 3 ở đường đọc).
            khoa_toi = khoa_ten(toi) if toi else None
            cua_toi = ([r for r in tat_ca if khoa_ten(r.get("nguoi_gan") or "") == khoa_toi]
                       if khoa_toi else [])
            ten_video, la_h264, ghi_chu_video = video_de_phat(ten)
            d["video"] = ten_video
            d["video_phat_duoc"] = bool(la_h264)
            mo = _mo_video(ten)
            if mo:
                cap = mo[0]
                import cv2
                d["rong"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
                d["cao"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
            d["che_do_mac_dinh"] = "anh"
            d["canh_bao_video"] = ghi_chu_video
            d["nguoi_dang_dan"] = toi or None
            d["da_gan"] = cua_toi
            d["so_nhan_nguoi_khac"] = len(tat_ca) - len(cua_toi)
            d["nguoi_khac"] = sorted({r.get("nguoi_gan") for r in tat_ca
                                      if khoa_ten(r.get("nguoi_gan") or "") != khoa_toi} - {None})
            return self._json(d)
        return self._json({"loi": "không có route"}, 404)

    # Origin được phép: server chỉ phục vụ đúng trang của nó. Trang web khác KHÔNG được ghi nhãn vào
    # phiên đang dán — file nhãn là BẰNG CHỨNG, bị chèn dòng là hỏng cả kết luận (review độc lập P1).
    ORIGIN_CHO = {""}          # "" = không gửi Origin (curl/tool). KHÔNG nhận "null": mọi POST
    # `application/json` cross-origin đều phải preflight, mà server không có `do_OPTIONS` ⇒ browser
    # không gửi POST. Ngược lại, DNS rebinding thì Origin == Host nên allowlist `Host` mới chặn được.
    # "0.0.0.0" cũng nhận: tài liệu bảo `--host 0.0.0.0`, người dùng hay gõ y nguyên vào thanh địa chỉ.
    HOST_CHO = ("", "127.0.0.1", "localhost", "::1", "0.0.0.0")

    def _host_hop_le(self) -> bool:
        """Chặn DNS rebinding: kẻ tấn công khiến Origin == Host nên chỉ kiểm Origin là vô ích."""
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return True                      # curl không gửi Host (HTTP/1.0) — không phải đường browser
        # `urlsplit` hiểu đúng `[::1]:8770`; tách tay bằng `rpartition(":")` từng trả 403 cho IPv6.
        try:
            ten = (urlparse("//" + host).hostname or "").strip("[]")
        except ValueError:
            return False
        if ten in self.HOST_CHO:
            return True
        # bind 0.0.0.0 ⇒ chấp nhận MỌI IPv4 của chính máy này (người dùng mở từ máy khác)
        try:
            return ten in self.ip_may()
        except OSError:
            return False

    @staticmethod
    def ip_may() -> set[str]:
        """Tập IPv4 của CHÍNH máy này (LAN/VPN/docker có thể khác `gethostbyname`).

        `docs/cach-gan-nhan.md` §5 hướng dẫn `--host 0.0.0.0` rồi mở `http://<IP-WSL>:8770`; nếu chỉ
        so một địa chỉ thì đường dự phòng đó bị 403 ở MỌI POST trong khi trang + video vẫn chạy
        (review vòng 3, P2-7).
        """
        import socket
        ra = {"127.0.0.1"}
        try:
            ra |= set(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            pass
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ra.add(info[4][0])
        except OSError:
            pass
        # IPv6 nội bộ (ULA/link-local): thiếu nhánh này thì mở bằng IPv6 thì trang + video chạy mà MỌI
        # POST 403 — đúng lỗi vòng 3 P2-7 nhưng cho họ địa chỉ IPv6 (review vòng 4, P3-19).
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET6):
                ra.add(info[4][0].split("%")[0])
        except OSError:
            pass
        return ra

    def _origin_hop_le(self) -> bool:
        o = self.headers.get("Origin") or ""
        if o in self.ORIGIN_CHO:
            return True
        return urlparse(o).netloc == (self.headers.get("Host") or "")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/label":
            return self._json({"loi": "không có route"}, 404)
        if not self._host_hop_le():
            return self._json({"loi": "Host lạ — không nhận (chống DNS rebinding)"}, 403)
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
        # ĐỐI CHIẾU với CSV server đang giữ: `buoc` phải nằm trong dải và `frame_vos` phải khớp dòng
        # đó. Không có bước này thì client ghi được `buoc = 999999` hoặc `frame_vos` cũ (CSV sinh lại
        # cùng tên), mà đây là file BẰNG CHỨNG (review vòng 2, P2-5).
        csv_path = DATA_DIR / f"{phien}_metrics.csv"
        try:
            khung = doc_phien_cached(csv_path)["frames"]
        except (OSError, ValueError) as e:
            return self._json({"loi": f"không đọc được CSV của phiên: {e}"}, 400)
        buoc = body.get("buoc")
        if buoc in (None, "") and csv_path.is_file():
            # Trước đây thiếu `buoc` là BỎ QUA toàn bộ kiểm ⇒ tab cũ/curl ghi được `frame_vos=999999`
            # và làm `so_buoc_da_dan` vượt số bước của CSV (review vòng 3, P3-10).
            return self._json({"loi": "thiếu `buoc` — client phải gửi số thứ tự bước"}, 400)
        if buoc not in (None, ""):
            try:
                buoc = int(buoc)
            except (TypeError, ValueError):
                return self._json({"loi": "`buoc` phải là số nguyên"}, 400)
            if not 0 <= buoc < len(khung):
                return self._json({"loi": f"`buoc` ngoài dải 0..{len(khung) - 1}"}, 400)
            fv = body.get("frame_vos")
            if fv in (None, ""):
                return self._json({"loi": "thiếu `frame_vos` (phải gửi kèm `buoc`)"}, 400)
            if fv not in (None, ""):
                try:
                    if int(fv) != int(khung[buoc]["frame_vos"]):
                        return self._json({"loi": "`frame_vos` không khớp dòng CSV của `buoc`"}, 400)
                except (TypeError, ValueError):
                    return self._json({"loi": "`frame_vos` phải là số nguyên"}, 400)
            # Server TỰ điền `frame_vos`/`t_uoc_luong` từ CSV: đó là dữ liệu của server, không phải của
            # client — nhãn phải khớp CSV kể cả khi client cũ không gửi.
            body = {**body, "frame_vos": int(khung[buoc]["frame_vos"]),
                    "t_uoc_luong": khung[buoc]["t_uoc_luong"]}
        # P1-A: TÊN NGƯỜI DÁN LẤY TỪ CHÍNH NHÃN (body), không phải cờ lúc khởi động. Trước đây
        # `--nguoi-gan` quyết định toàn bộ ⇒ 2 người mở cùng URL thì mọi nhãn ghi 1 tên ⇒ "2 người
        # đồng ý" không bao giờ đạt được bằng cách làm đúng tài liệu.
        # KHÔNG fallback về `self.nguoi_gan` khi client gửi rỗng: người thứ 2 xoá ô tên rồi bấm phím sẽ
        # ghi nhãn dưới TÊN NGƯỜI THỨ 1 (đúng lớp lỗi P1 vòng 3, bị server mở lại — review vòng 4).
        nguoi = str(body.get("nguoi_gan") or "").strip()
        if not nguoi:
            return self._json({"loi": "thiếu `nguoi_gan` trong body (ô 'Người gán' đang trống)"}, 400)
        try:
            rec = ghi_nhan(phien, body, nguoi)
        except ValueError as e:
            return self._json({"loi": str(e)}, 400)
        except (TypeError, OverflowError) as e:      # vd `t_video: [1]` / `1e400` (json nhận Infinity)
            return self._json({"loi": f"giá trị không hợp lệ: {e}"}, 400)
        try:
            th = tong_hop(phien)
        except Exception as e:                    # nhãn ĐÃ ghi; không được trả lỗi mạng cho client
            th = {"loi": f"không tổng hợp được: {e}"}
        return self._json({"ok": True, "record": rec, "tong_hop": th})


def tao_server(port: int = DEFAULT_PORT, nguoi_gan: str = "?", phien_mac_dinh: str | None = None,
               host: str = "127.0.0.1"):
    """`host` mặc định 127.0.0.1 (chỉ máy này). WSL2 thường chia cổng với Windows nên vẫn mở được từ
    Chrome Windows; nếu không, chạy `--host 0.0.0.0` rồi mở `http://<IP-WSL>:<cổng>`."""
    handler = type("H", (_Handler,), {"nguoi_gan": nguoi_gan, "phien_mac_dinh": phien_mac_dinh})
    return ThreadingHTTPServer((host, port), handler)


def _ghi_artifact(ten: str, d: dict, *, ket_qua: bool, ly_do: str | None = None,
                  kiem_dai_buoc: bool | None = None) -> Path:
    """Ghi `<phiên>_tonghop.json` — LUÔN có `ket_qua` (true/false) + `ly_do`.

    Trước đây file được ghi TRƯỚC các cổng kiểm ⇒ một lần chạy "chưa trích được" vẫn để lại artifact
    trông như đã đo, mà `.gitignore` lại cho file này vào git (review vòng 4, P3-12).
    """
    out = THU_MUC_NHAN / f"{ten}_tonghop.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"phien": ten, "git_rev": _git_rev(), "ket_qua": ket_qua, "ly_do": ly_do,
                               "kiem_dai_buoc": kiem_dai_buoc,
                               "do_luc": datetime.now().astimezone().isoformat(timespec="seconds"),
                               **d}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[artifact] {duong_dan_gon(out)}  (ket_qua={ket_qua}"
          + (f", lý do: {ly_do}" if ly_do else "") + ")")
    return out


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
        if not d["so_nhan_hieu_luc"]:
            print(f"[tong-hop] KHÔNG có nhãn HỢP LỆ nào ({d['tong_nhan']} dòng, "
                  f"{d['so_nhan_loi']} dòng lỗi) — chưa đo được gì")
            _ghi_artifact(ten, d, ket_qua=False, ly_do="không có nhãn hợp lệ")
            return 1
        rev = _git_rev()
        if not rev:
            print("[tong-hop] KHÔNG đọc được git_rev — artifact không tái lập được (AGENTS §6)")
            _ghi_artifact(ten, d, ket_qua=False, ly_do="không đọc được git_rev")
            return 1
        csv_p = p if p.is_file() else DATA_DIR / f"{ten}_metrics.csv"
        ngoai: list = []
        n_buoc = None
        if csv_p.is_file():
            try:
                n_buoc = len(doc_phien_cached(csv_p)["frames"])
            except (OSError, ValueError):
                n_buoc = None
            if n_buoc is not None:
                # `tong_hop` nhận `buoc` kiểu `int("99")`/`99.0`; cổng này từng chỉ nhận `isinstance(int)`
                # ⇒ một dòng sửa tay NGOÀI dải vẫn được đếm mà không bị cờ (review vòng 5, P3).
                def _ngoai_dai(r):
                    if not isinstance(r, dict) or r.get("buoc") in (None, ""):
                        return False
                    try:
                        b = int(float(r["buoc"]))
                    except (TypeError, ValueError, OverflowError):
                        return True          # `buoc` không đọc được ⇒ coi như ngoài dải (báo lỗi)
                    return not 0 <= b < n_buoc
                ngoai = [r.get("buoc") for r in doc_nhan(ten) if _ngoai_dai(r)]
        kiem_dai = n_buoc is not None
        if not kiem_dai:
            # Chạy trên clone sạch: `data/nhan/*.jsonl` được track còn `data/*_metrics.csv` thì KHÔNG ⇒
            # không có CSV để đối chiếu. Đã từng ghi `ket_qua=true` mà không nói cổng này bị bỏ qua.
            print(f"[tong-hop] CẢNH BÁO: không tìm/đọc được CSV ({csv_p}) ⇒ KHÔNG kiểm được `buoc` có "
                  "nằm trong dải bước của phiên (artifact ghi `kiem_dai_buoc: false`)")
        if ngoai:
            print(f"[tong-hop] LỖI: {len(ngoai)} nhãn có `buoc` NGOÀI dải 0..{n_buoc - 1} "
                  f"(vd {ngoai[:3]}) ⇒ CSV đã bị sinh lại hoặc nhãn thuộc phiên khác; "
                  "KHÔNG trích được (số đồng ý sẽ bị thổi phồng)")
            _ghi_artifact(ten, d, ket_qua=False,
                         ly_do=f"{len(ngoai)} nhãn ngoài dải 0..{n_buoc - 1}")
            return 1
        canh_bao_3 = None
        if d["so_nguoi"] > 2:
            canh_bao_3 = (f"{d['so_nguoi']} người: `so_buoc_dong_y` là \"TẤT CẢ đồng ý\", "
                          "không phải tỉ lệ theo cặp — dùng `theo_cap`")
            print(f"[tong-hop] CẢNH BÁO: {canh_bao_3}")
        if d["so_nguoi"] < 2:
            print(f"[tong-hop] CHỈ {d['so_nguoi']} người dán ⇒ CHƯA trích được (cần 2 người độc lập)")
            _ghi_artifact(ten, d, ket_qua=False, ly_do=f"chỉ {d['so_nguoi']} người dán")
            return 1
        if d["dong_y_2_nguoi"] and d["dong_y_2_nguoi"]["so_buoc_ca_hai_co_ket_luan"] == 0:
            print("[tong-hop] hai người KHÔNG dán trùng bước nào có kết luận ⇒ chưa so được")
            if d["so_nhan_thieu_buoc"]:
                print(f"[tong-hop] nguyên nhân khả dĩ: có {d['so_nhan_thieu_buoc']} nhãn KHÔNG có `buoc` "
                      "(tool phiên bản cũ) ⇒ hai người đang ở hai không-gian khoá khác nhau")
            _ghi_artifact(ten, d, ket_qua=False, ly_do="không có bước nào cả hai cùng dán")
            return 1
        ly_do = []
        if not kiem_dai:
            ly_do.append("không có CSV để đối chiếu dải `buoc`")
        if canh_bao_3:
            ly_do.append(canh_bao_3)
        _ghi_artifact(ten, d, ket_qua=True, kiem_dai_buoc=kiem_dai,
                     ly_do=("; ".join(ly_do) or None))
        return 0

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
