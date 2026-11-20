"""Gán GT phân đoạn NHANH cho clip thật: gợi ý bằng ngưỡng màu + tô trên trình duyệt.

Vì sao có script này: `score_miou.py label` chỉ cắt frame ra PNG, còn người gán phải mở phần mềm ảnh
và tô tay từ đầu 20–30 frame — chậm và dễ sai. Thước đo duy nhất của "bám có ĐÚNG không" là **mIoU
mask vs GT người gán** (`docs/thuoc-do-bam-dung.md`), nên đường gán GT phải rẻ.

Ba việc, một lệnh:

1. cắt frame cần gán ra `docs/gt/<ten>/frames/frame_NNNNNN.png` (dùng `score_miou.cat_frames`);
2. sinh **gợi ý** `docs/gt/<ten>/goiy/goiy_NNNNNN.png` bằng ngưỡng màu HSV (vật màu nổi trên nền xám) —
   đây là **gợi ý để sửa**, KHÔNG phải GT: `index.json` khai `nguon_gt` đúng sự thật
   (`"ngưỡng màu HSV (script) + người sửa tay"`), sai số của bộ gợi ý **chưa đo**;
3. mở **trình tô** trên trình duyệt (`http://127.0.0.1:<cổng>`) để chấm/sửa bằng chuột rồi lưu
   `gt_NNNNNN.png` **thẳng vào thư mục GT** (không phải tải về Downloads rồi chuyển tay).

Chạy:

    python scripts/gt_gan_nhanh.py --clip data/binh1.mp4 --ten binh1_tay --nguoi-gan "Nguyễn Văn A" \\
        --frames 0,25,50,57,69,90,110,150,190,230,255,280,310

Rồi mở link script in ra, tô, bấm **Lưu & tiếp**. Xong thì chấm:

    python scripts/score_miou.py score --gt docs/gt/binh1_tay --pred-dir <masks> --out data/miou_....json

GIỚI HẠN phải nói khi trích số: GT do **người** quyết định cuối cùng nhưng **khởi tạo từ ngưỡng màu**;
nếu người gán chỉ bấm "nhận gợi ý" mà không sửa thì mIoU đo *bộ gợi ý*, không đo người. `--khong-goi-y`
để tô tay từ đầu nếu cần GT "sạch" tuyệt đối.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

GT_DIR = REPO_ROOT / "docs" / "gt"
PAINTER = Path(__file__).with_name("gt_painter.html")

# Ngưỡng HSV mặc định cho vật MÀU (chai tím/đỏ) trên nền xám — chỉ là điểm khởi đầu để người sửa.
H_MIN, S_MIN, V_MIN = 40, 70, 30
# Tên bộ GT chỉ chữ/số/_/./- và không bắt đầu bằng '.' — chặn `--ten ../../docs` ghi ra ngoài `docs/gt/`
TEN_HOP_LE = __import__("re").compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def goi_y_hsv(img, *, s_min: int = S_MIN, v_min: int = V_MIN, h_min: int = H_MIN):
    """Mask gợi ý = vùng bão hoà màu cao (bỏ nền xám/trắng), giữ **thành phần liên thông lớn nhất**.

    Trả mask `uint8` 0/255 cùng kích thước ảnh. Hàm THUẦN trên mảng (test được, không cần file):
    ảnh xám ⇒ không có pixel nào đạt ngưỡng ⇒ mask rỗng (và bên gọi phải nói "không có gợi ý", không
    được coi mask rỗng là GT hợp lệ — `IoU(rỗng, rỗng) = 1,0` là bẫy đã gặp 3 lần).
    """
    import cv2
    import numpy as np

    if img is None or getattr(img, "size", 0) == 0:
        raise ValueError("goi_y_hsv: ảnh rỗng")
    if img.ndim == 2:
        # Ảnh không có thông tin MÀU ⇒ không thể gợi ý theo màu. Trả mask rỗng (và bên gọi phải nói
        # "không có gợi ý"), KHÔNG được coi mask rỗng là GT: `IoU(rỗng, rỗng) = 1,0`.
        return np.zeros(img.shape[:2], np.uint8)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    tho = ((s >= int(s_min)) & (v >= int(v_min)) & (h >= int(h_min))).astype(np.uint8)
    # Đóng lỗ nhỏ (phản sáng trên nhãn chai) rồi chỉ giữ blob lớn nhất: bàn tay/áo cũng bão hoà màu.
    tho = cv2.morphologyEx(tho, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, nhan, stats, _ = cv2.connectedComponentsWithStats(tho, connectivity=8)
    if n <= 1:
        return np.zeros(tho.shape, np.uint8)
    lon_nhat = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = np.where(nhan == lon_nhat, 255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    # Bao lồi: nhãn trắng trên chai có bão hoà thấp nên phần giữa vật bị khoét; vật dạng khối (chai,
    # hộp) thì bao lồi lấp đúng chỗ đó. Đo trên 4 frame `binh1`: IoU(gợi ý, mask model) 0,43–0,56 khi
    # không hull → 0,44–0,63 khi có hull ⇒ gợi ý sát vật hơn, người gán chỉ cần sửa viền.
    hull = cv2.convexHull(cv2.findNonZero(mask))
    if hull is not None:
        day = np.zeros_like(mask)
        cv2.fillPoly(day, [hull], 255)
        mask = day
    return mask


def ten_goi_y(frame: int) -> str:
    return f"goiy_{int(frame):06d}.png"


def ten_gt(frame: int) -> str:
    return f"gt_{int(frame):06d}.png"


def ten_frame(frame: int) -> str:
    return f"frame_{int(frame):06d}.png"


def doc_frame_tu_ten(ten: str):
    """`frame_000057.png`/`goiy_...`/`gt_...` → số frame; tên lạ ⇒ `None` (đừng đoán)."""
    goc = Path(str(ten)).stem
    for tien_to in ("frame_", "goiy_", "gt_"):
        if goc.startswith(tien_to) and goc[len(tien_to):].isdigit():
            return int(goc[len(tien_to):])
    return None


def _viet_index(gt_dir: Path, *, clip: str, ten: str, frames, nguoi_gan: str,
                co_goi_y: bool, frame_hw=None, gt_rong=(), chon_frame=None) -> Path:
    """`index.json` khai ĐÚNG nguồn GT — thiếu/sai khoá này thì `score_miou` cảnh báo hoặc từ chối.

    `frame_hw` **bắt buộc phải có**: `score_miou.kiem_index` và `gt_check_silhouette` đều **bỏ qua im
    lặng** khi khoá này thiếu ⇒ GT sai cỡ (file chép tay, `gt_*.png` cũ trong cùng thư mục) vẫn được in
    "hợp lệ, exit 0". Repo đã trả giá đúng lỗi này (`docs/task/15-11-2026-gt-hop-bao-va-mask-ngoai-gt.md`).

    Gọi lại trên thư mục ĐÃ có `index.json` ⇒ **hợp** `frames` (giữ frame đã gán trước đó) và giữ các
    khoá lạ (`dung_duoc`, `ly_do_khong_dung`, …). Ghi đè trắng sẽ làm `n_cham` nhỏ đi trong khi
    `coverage` vẫn 1,0 — số liệu nhỏ dần một cách im lặng.
    """
    path = gt_dir / "index.json"
    cu = {}
    if path.is_file():
        try:
            cu = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cu = {}
        if not isinstance(cu, dict):
            cu = {}
    dang_cu = cu.get("dang_gt")
    if dang_cu and dang_cu != "silhouette":
        # Bộ GT cũ KHÔNG phải silhouette (vd `hop_bao` có `hop_bao_xywh` từng frame): công cụ này chỉ
        # vẽ silhouette ⇒ ghi vào đó là **dán nhãn sai** cả bộ (cổng `hop_bao_xywh`↔mask tắt im lặng,
        # artifact đổi `gt_dang` ⇒ con số cũ bị in thành "IoU với GT silhouette").
        raise SystemExit(
            f"[LOI] `{ten}` đang là bộ GT dạng `{dang_cu}` — không trộn phương pháp. Dùng --ten khác.")
    cu_items = [f for f in (cu.get("frames") if isinstance(cu.get("frames"), list) else []) if isinstance(f, dict)
                and str(f.get("frame_idx", "")).lstrip("-").isdigit()]
    frames_cu = [int(f["frame_idx"]) for f in cu_items]
    # Hợp theo TỪNG FRAME (giữ `hop_bao_xywh`/ghi chú của frame cũ), không dựng lại `{"frame_idx": f}`.
    theo_frame = {int(f["frame_idx"]): dict(f) for f in cu_items}
    moi = sorted(set(int(v) for v in frames) | set(frames_cu))
    index = {
        "clip": clip,
        "ten": ten,
        "frames": [theo_frame.get(f, {"frame_idx": f}) for f in moi],
        "frame_hw": list(frame_hw) if frame_hw else cu.get("frame_hw"),
        "gt_rong": sorted(set(int(v) for v in gt_rong) | set(cu.get("gt_rong") or [])),
        "nguoi_gan": nguoi_gan or cu.get("nguoi_gan") or "",
        "gt_do_model_goi_y": False,
        "dang_gt": "silhouette",
        "nguon_gt": ("ngưỡng màu HSV (script `gt_gan_nhanh.py`) + người sửa tay"
                     if co_goi_y else "người tô tay trên frame gốc"),
        "phuong_phap_gt": ("gợi ý = vùng bão hoà màu, blob lớn nhất; người chấm/sửa rồi lưu"
                           if co_goi_y else "người tô tay từ frame trống"),
        "sai_so_bo_goi_y": ("CHƯA ĐO — mIoU này là của mask SAU khi người sửa, không phải của gợi ý"
                            if co_goi_y else None),
        # Caveat phải nằm trong `phuong_phap_gt` vì `score_miou` chỉ copy `nguon_gt`/`phuong_phap_gt`
        # vào `meta` của artifact — khoá `sai_so_bo_goi_y` KHÔNG đi theo con số ra file công bố.
        **({"phuong_phap_gt": ("GT khởi tạo bằng ngưỡng màu HSV (bao lồi) rồi NGƯỜI sửa tay; "
                               "sai số của bộ gợi ý CHƯA ĐO ⇒ không đọc mIoU này như GT người vẽ "
                               "hoàn toàn")} if co_goi_y else {}),
        # CÁCH CHỌN FRAME phải nằm trong index: `score_miou` chỉ copy `nguon_gt`/`phuong_phap_gt`
        # vào artifact, nên khoá riêng KHÔNG đi theo con số. Không có nó thì không chứng minh được
        # "7 frame này là GIỮA KHE" khi soi lại artifact (AGENTS §6: artifact tự khai điều kiện đo).
        "chon_frame": chon_frame or cu.get("chon_frame"),
        "cong_cu": "scripts/gt_gan_nhanh.py + scripts/gt_painter.html",
        "tao_luc": datetime.now().isoformat(timespec="seconds"),
        "huong_dan": ("Mở trang do script in ra, tô/eraser bằng chuột, bấm 'Lưu & tiếp'. File GT được "
                      "ghi thẳng vào thư mục này."),
    }
    # Khoá ngữ nghĩa do NGƯỜI VIẾT ĐẦU quyết định: chạy lại không được viết lại nguồn/phương pháp của
    # những frame đã gán (vd lần đầu tô tay, lần sau dùng gợi ý màu ⇒ hai phương pháp trong một bộ).
    for khoa in ("dang_gt", "nguon_gt", "phuong_phap_gt", "sai_so_bo_goi_y", "nguoi_gan",
                 "chon_frame"):
        if cu.get(khoa) is not None:
            index[khoa] = cu[khoa]
    for khoa, gia in cu.items():                     # giữ khoá lạ (dung_duoc/ly_do_khong_dung/canh_bao…)
        index.setdefault(khoa, gia)
    gt_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _kiem_png(data: bytes, *, rong: int, cao: int, cho_rong: bool = False) -> str:
    """Kiểm ảnh GT do trình duyệt gửi lên; trả thông báo lỗi (''= hợp lệ).

    Ba kiểm bắt buộc: PNG thật, **cùng kích thước frame** (khác cỡ ⇒ GT lệch frame mà `score_miou`
    không phát hiện được vì nó chỉ so `sum`), và có **ít nhất 1 pixel vật** (mask rỗng làm
    `IoU(rỗng, rỗng) = 1,0` ⇒ mIoU bị thổi phồng).
    """
    import cv2
    import numpy as np

    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if arr is None:
        return "dữ liệu không phải ảnh đọc được"
    if arr.shape[:2] != (cao, rong):
        return f"kích thước {arr.shape[1]}×{arr.shape[0]} khác frame {rong}×{cao}"
    if not np.any(arr > 127) and not cho_rong:
        # Rỗng chỉ hợp lệ khi người gán KHAI "frame này không có vật" (`?rong=1`): `score_miou` không
        # chấm frame GT rỗng, nên khai đúng thì không thổi phồng mIoU; nhận rỗng vô điều kiện thì
        # `IoU(rỗng, rỗng) = 1,0` sẽ được ghi thành điểm.
        return "mask rỗng — nếu frame này KHÔNG có vật thì bấm 'Không có vật' (khai rỗng)"
    return ""


def _make_handler(gt_dir: Path, kich_thuoc: dict[int, tuple[int, int]]):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_a):                      # giữ console sạch khi người gán đang tô
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):                                # noqa: N802 (API của http.server)
            if self.path == "/favicon.ico":
                # Trình duyệt LUÔN hỏi favicon; trả 204 để console không có lỗi 404 (e2e coi đó là lỗi
                # thật thì sẽ che mất lỗi JS thật).
                return self._send(204, b"", "image/x-icon")
            if self.path in ("/", "/index.html"):
                return self._send(200, PAINTER.read_bytes(), "text/html; charset=utf-8")
            if self.path == "/danh-sach.json":
                trong = sorted(p.name for p in gt_dir.iterdir() if p.name.startswith("gt_"))
                body = json.dumps({"frames": sorted(kich_thuoc), "da_co_gt": trong,
                                   "kich_thuoc": kich_thuoc}, ensure_ascii=False).encode()
                return self._send(200, body, "application/json")
            if (self.path.startswith("/frame/") or self.path.startswith("/goiy/")
                    or self.path.startswith("/gt/")):
                loai, _, ten = self.path.lstrip("/").partition("/")
                thu_muc = gt_dir / {"frame": "frames", "goiy": "goiy", "gt": "."}[loai]
                if doc_frame_tu_ten(ten) is None:         # chặn `../` và tên lạ
                    return self._send(404, b"ten la", "text/plain")
                path = thu_muc / Path(ten).name
                if not path.is_file():
                    return self._send(404, b"khong co", "text/plain")
                return self._send(200, path.read_bytes(), "image/png")
            return self._send(404, b"khong co", "text/plain")

        def do_POST(self):                               # noqa: N802
            # Localhost vẫn bị trang web bất kỳ POST tới (simple request) ⇒ chặn theo
            # `Sec-Fetch-Site`. Trình tô của mình là same-origin nên qua bình thường.
            site = self.headers.get("Sec-Fetch-Site")
            if site not in (None, "same-origin", "none"):
                return self._send(403, b"khac origin", "text/plain")
            if not self.path.startswith("/luu/"):
                return self._send(404, b"khong co", "text/plain")
            frame = doc_frame_tu_ten(self.path.rsplit("/", 1)[-1])
            if frame is None or frame not in kich_thuoc:
                return self._send(400, b"frame la", "text/plain")
            try:
                dai = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                # `Content-Length: abc` từng làm handler ném ValueError ⇒ client không nhận gì
                self.close_connection = True
                return self._send(400, b"Content-Length khong phai so", "text/plain")
            if dai <= 0 or dai > 8 * 1024 * 1024:
                return self._send(400, b"kich thuoc body sai", "text/plain")
            data = self.rfile.read(dai)
            rong, cao = kich_thuoc[frame]
            khai_rong = "rong=1" in self.path
            loi = _kiem_png(data, rong=rong, cao=cao, cho_rong=khai_rong)
            if loi:
                return self._send(422, loi.encode(), "text/plain")
            (gt_dir / ten_gt(frame)).write_bytes(data)
            _ghi_gt_rong(gt_dir, frame, rong=khai_rong)
            return self._send(200, f"da luu {ten_gt(frame)}".encode(), "text/plain")

    return Handler


def _ghi_gt_rong(gt_dir: Path, frame: int, *, rong: bool = True) -> None:
    """Khai frame này là "KHÔNG có vật" vào `index.json` (`gt_rong`) — `score_miou` sẽ không chấm nó.

    Cần đường này vì `binh1` có frame chai đã rời khung: ép người gán tô một vật không tồn tại là tạo
    GT sai, còn bắt họ dừng giữa buổi thì không ra được con số nào (review độc lập PR #49, P1).
    """
    path = gt_dir / "index.json"
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(index, dict):
        return
    cu = set(int(v) for v in index.get("gt_rong") or [])
    # Lưu thường trên frame TỪNG khai rỗng ⇒ phải GỠ khỏi `gt_rong`, nếu không index nói "không có vật"
    # trong khi GT có vật.
    moi = (cu | {int(frame)}) if rong else (cu - {int(frame)})
    index["gt_rong"] = sorted(moi)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _kich_thuoc_frames(gt_dir: Path, frames) -> dict[int, tuple[int, int]]:
    """`frame → (rộng, cao)` đọc từ PNG đã cắt (để kiểm GT gửi lên đúng cỡ)."""
    import cv2

    ra = {}
    for f in frames:
        path = gt_dir / "frames" / ten_frame(f)
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"[CẢNH BÁO] thiếu frame {path} — bỏ frame {f}")
            continue
        ra[int(f)] = (img.shape[1], img.shape[0])
    return ra


def frames_trai_deu(so_frame: int, n: int = 12) -> list[int]:
    """`n` frame trải đều `[0, so_frame-1]`, luôn gồm frame đầu và frame cuối, KHÔNG trùng.

    Hàm THUẦN (test được, không cần clip). Vì sao cần mặc định này: danh sách 12 frame viết tay dài
    ~50 ký tự, đủ để terminal xuống dòng khi dán và làm hỏng cả lệnh (19-11, 2 lần liền).
    """
    if so_frame <= 0:
        return []
    if so_frame <= n:
        return list(range(int(so_frame)))
    # `round` chứ không `//`: bước `so_frame/(n-1)` chia đều cả hai đầu; `set` để chống trùng khi
    # clip ngắn (vd 13 frame, 12 mốc) — trùng frame sẽ làm GT có 2 ảnh cùng tên.
    buoc = (so_frame - 1) / (n - 1)
    return sorted({int(round(i * buoc)) for i in range(n)})


def parse_khung(text: str) -> list[tuple[int, int]]:
    """Đọc `"0:110,165:262"` → `[(0,110),(165,262)]`. Hàm THUẦN, test được.

    Bao gồm cả hai đầu (`a <= f <= b`): người dùng ghi khung theo frame NHÌN THẤY vật, nên chặt bớt
    một frame ở mép chỉ làm mất mẫu chứ không làm phép đo đúng hơn.
    """
    ra = []
    for phan in str(text).replace(";", ",").split(","):
        phan = phan.strip()
        if not phan:
            continue
        if ":" not in phan:
            raise ValueError(f"khung phải có dạng a:b, nhận {phan!r}")
        a, b = phan.split(":", 1)
        a, b = int(a), int(b)
        if a > b:
            raise ValueError(f"khung ngược {a}:{b}")
        if a < 0:
            raise ValueError(f"khung âm {a}:{b}")
        ra.append((a, b))
    if not ra:
        raise ValueError("không có khung nào")
    return ra


def loc_theo_khung(frames, text, *, ten_clip: str = "") -> list[int]:
    """Sinh xong → lọc theo khung; giao RỖNG thì **báo lỗi**, không rơi về bộ mặc định.

    Vì sao phải là hàm riêng: bản đầu đặt phép lọc **trước** khi sinh danh sách ⇒ danh sách còn rỗng
    ⇒ `--khung` luôn báo "lọc hết frame" (lần chạy thử 20-11 bắt được). Tách ra để test khoá đúng thứ
    tự đó mà không cần dựng clip.
    """
    frames = [int(f) for f in frames]
    if not text:
        return frames
    try:
        khung = parse_khung(text)
    except ValueError as exc:      # người dùng gõ tay: phải ra "[LOI]", không phải traceback Python
        raise SystemExit(f"[LOI] --khung {text!r}: {exc}") from None
    ra = [f for f in frames if any(a <= f <= b for a, b in khung)]
    bo = [f for f in frames if f not in set(ra)]
    if bo:
        print(f"[khung] bỏ {len(bo)} frame ngoài {text}: {bo}")
    if not ra:
        raise SystemExit(f"[LOI] --khung {text} lọc hết frame — kiểm lại mốc/khoảng")
    return ra


def frames_giua_khe(so_frame: int, n: int = 12, vos_every: int = 3, buoc: int = 30) -> list[int]:
    """`n` frame nằm **giữa khe** VOS — `frame ≡ (vos_every-1) mod vos_every`, cách nhau `buoc`.

    Vì sao đúng chỗ này: pipeline chạy VOS ở các frame chia hết cho `vos_every`; frame ngay TRƯỚC lần VOS
    kế tiếp là frame xa mốc VOS nhất, nên ô hiển thị ở đó **hoàn toàn** do nội suy LK quyết định. Chấm GT
    ở các frame sát VOS (như bộ `b1`: ≡ 0/1 mod 3) thì LK chỉ có 1 bước ⇒ gần như không thử được `max_mad`.

    Hàm THUẦN (test được, không cần clip).
    """
    if so_frame <= 0 or vos_every < 2 or n < 1:
        return []
    moc = vos_every - 1
    # BƯỚC PHẢI LÀ BỘI CỦA vos_every, nếu không mốc sẽ trôi khỏi dàn "≡ -1 mod ve": với buoc=30 và
    # vos_every=4 thì frame thứ hai là 33 (33 % 4 = 1) — rơi đúng vào frame CÓ VOS ⇒ phép đo vô nghĩa.
    # Test tests/test_gt_gan_nhanh.py bắt được lỗi này (19–20-11).
    buoc = max(vos_every, vos_every * max(1, round(int(buoc) / vos_every)))
    ra, f = [], moc
    while f < so_frame and len(ra) < n:
        ra.append(int(f))
        f += buoc
    return ra


def so_frame_cua_clip(clip: str) -> int:
    """Số frame của clip; 0 nếu không đọc được (bên gọi tự báo lỗi rõ ràng)."""
    import cv2

    cap = cv2.VideoCapture(str(clip))
    try:
        if not cap.isOpened():
            return 0
        return int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        cap.release()


def main(argv=None) -> int:
    import cv2

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clip", required=True)
    parser.add_argument("--ten", required=True, help="tên bộ GT (thư mục con của docs/gt)")
    parser.add_argument("--nguoi-gan", required=True, help="ai chịu trách nhiệm gán (vào index.json)")
    # KHÔNG bắt buộc: bỏ trống = 12 frame trải đều toàn clip. Vì sao đổi (19-11): danh sách 12 frame
    # dài ~50 ký tự làm lệnh vượt bề rộng terminal; khi dán, terminal chèn XUỐNG DÒNG ngay sau
    # `--frames` ⇒ bash báo `argument --frames: expected one argument` rồi cố chạy dãy số như một
    # lệnh (gặp thật 2 lần liên tiếp). Lệnh ngắn thì không còn cửa cho lỗi đó.
    parser.add_argument("--frames", default="",
                        help='danh sách frame_idx, vd "0,50,120"; bỏ trống = 12 frame trải đều clip')
    # Thay cho việc gõ dãy frame dài (~30 ký tự số làm terminal wrap ngay sau `--frames`).
    #
    # Chọn frame ≡ (vos_every-1) mod vos_every vì pipeline chạy VOS ở frame chia hết cho `vos_every`
    # (`live_tracking.py`: `_frame_index % every == 0`) ⇒ frame này CHẮC CHẮN không phải frame VOS, ô
    # hiển thị là nội suy từ mốc VOS gần nhất **cách nó vos_every-1 frame**. Lưu ý: frame ≡ 0 cũng đang
    # phát ô nội suy (từ lần VOS TRƯỚC, cách vos_every frame, vì VOS về muộn hơn nhịp phát) ⇒ đây là
    # "chắc chắn không phải frame VOS", KHÔNG phải định lý "xa mốc nhất". LK luôn được gọi đúng MỘT
    # lần/frame và reset mốc về frame VOS ⇒ đại lượng thử được là KHOẢNG CÁCH, không phải "số bước".
    # Vì sao cần cờ này: dãy `--frames 2,32,62,…` dài ~30 ký tự làm terminal (~105 cột) chèn XUỐNG
    # DÒNG ngay sau `--frames` ⇒ `argument --frames: expected one argument` (gặp thật 3 lần, 19–20-11).
    parser.add_argument("--giua-khe", nargs="?", type=int, const=12, default=None,
                        metavar="N",
                        help="chọn N frame (mặc định 12) nằm GIỮA KHE VOS (≡ vos_every-1 mod vos_every), "
                             "cách nhau ~30 frame nhưng LUÔN là bội của vos_every (ve=4 ⇒ 32, ve=7 ⇒ 28)")
    # Lọc theo KHUNG FRAME — bắt buộc khi vật ra khỏi khung giữa clip: GT ở đó là mask RỖNG, chấm
    # vào chỉ tốn công tô mà không đo được gì (binh1: chai chỉ có trong 0:110 và 165:262).
    parser.add_argument("--khung", default=None, metavar="a:b[,c:d]",
                        help="chỉ lấy frame trong các khung này, vd 0:110,165:262")
    parser.add_argument("--vos-every", type=int, default=3,
                        help="chu kỳ VOS của phiên sẽ chấm (mặc định 3) — chỉ dùng với --giua-khe")
    parser.add_argument("--khong-goi-y", action="store_true",
                        help="không sinh gợi ý màu (tô tay từ đầu) ⇒ GT 'sạch' hơn")
    parser.add_argument("--s-min", type=int, default=S_MIN, help="ngưỡng bão hoà màu của gợi ý (0–255)")
    parser.add_argument("--v-min", type=int, default=V_MIN, help="ngưỡng sáng tối thiểu của gợi ý")
    parser.add_argument("--cong", type=int, default=8765, help="cổng HTTP của trình tô (0 = tự chọn)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="địa chỉ bind (127.0.0.1 = chỉ máy này; 0.0.0.0 chỉ dùng cho e2e WSL→Windows)")
    parser.add_argument("--chi-sinh", action="store_true", help="chỉ cắt frame + sinh gợi ý, không mở server")
    args = parser.parse_args(argv)

    # Validate sớm: `--vos-every 1` (đúng cấu hình phiên mIoU của repo) làm `frames_giua_khe` trả []
    # ⇒ nếu không chặn, code rơi xuống `frames_trai_deu` **im lặng** và người dùng tô GT ở frame lẫn cả
    # frame CÓ VOS ⇒ bộ mẫu vô nghĩa cho phép đo max_mad mà không ai biết (review độc lập 20-11, P1).
    if args.giua_khe is not None and int(args.giua_khe) < 1:
        raise SystemExit(f"[LOI] --giua-khe {args.giua_khe}: N phải ≥ 1")
    if args.giua_khe is not None and int(args.vos_every) < 2:
        raise SystemExit(f"[LOI] --vos-every {args.vos_every}: cần ≥ 2 mới có 'khe' (mọi frame đều do "
                         "model ⇒ dùng --frames thay vì --giua-khe)")

    frames = [int(v) for v in str(args.frames).replace(";", ",").split(",") if v.strip()]
    chon_frame = {"frames": list(frames)} if frames else None
    if frames and args.giua_khe is not None:
        print("[canh-bao] bỏ qua --giua-khe/--vos-every vì đã có --frames")
    if not frames and args.giua_khe is not None:
        frames = frames_giua_khe(so_frame_cua_clip(args.clip), n=int(args.giua_khe),
                                 vos_every=int(args.vos_every))
        chon_frame = {"giua_khe": int(args.giua_khe), "vos_every": int(args.vos_every)}
        if not frames:
            raise SystemExit(f"[LOI] --giua-khe {args.giua_khe} với --vos-every {args.vos_every} sinh "
                             f"0 frame (clip có dài hơn {int(args.vos_every) - 1} frame không?)")
    if not frames:
        frames = frames_trai_deu(so_frame_cua_clip(args.clip))
        chon_frame = {"mac_dinh": "12 frame trải đều clip"}
    # Lọc khung SAU khi đã sinh danh sách (xem `loc_theo_khung`); giao rỗng ⇒ SystemExit.
    frames = loc_theo_khung(frames, args.khung, ten_clip=args.clip)
    if args.khung:
        chon_frame = {**(chon_frame or {}), "khung": args.khung}
    if not TEN_HOP_LE.match(args.ten):
        raise SystemExit(f"--ten {args.ten!r} không hợp lệ: chỉ chữ/số/_/./- và không bắt đầu bằng '.' "
                         f"(thư mục GT là nơi ghi provenance, không được trỏ ra ngoài)")
    gt_dir = GT_DIR / args.ten
    from scripts.score_miou import cat_frames

    so = cat_frames(Path(args.clip), frames, gt_dir / "frames")
    print(f"cắt {so} frame → {gt_dir / 'frames'}")

    if not args.khong_goi_y:
        (gt_dir / "goiy").mkdir(parents=True, exist_ok=True)
        for f in frames:
            img = cv2.imread(str(gt_dir / "frames" / ten_frame(f)), cv2.IMREAD_COLOR)
            if img is None:
                continue
            mask = goi_y_hsv(img, s_min=args.s_min, v_min=args.v_min)
            cv2.imwrite(str(gt_dir / "goiy" / ten_goi_y(f)), mask)
            ti_le = float((mask > 127).mean()) * 100
            print(f"  gợi ý f{f}: {ti_le:.1f} % diện tích"
                  + ("  (RỖNG — không đạt ngưỡng màu, phải tô tay)" if ti_le == 0 else ""))

    kich_thuoc = _kich_thuoc_frames(gt_dir, frames)
    if not kich_thuoc:
        raise SystemExit("[LOI] không có frame nào để gán")
    hw = sorted({v for v in kich_thuoc.values()})
    if len(hw) != 1:
        raise SystemExit(f"[LOI] frame không cùng kích thước {hw} — một bộ GT phải cùng cỡ")
    cao, rong = hw[0][1], hw[0][0]
    # Index ghi danh sách frame THẬT SỰ cắt được (không phải danh sách yêu cầu): frame không cắt được
    # mà vẫn nằm trong index ⇒ `score` báo "thiếu file GT" khó hiểu về sau.
    index = _viet_index(gt_dir, clip=args.clip, ten=args.ten, frames=sorted(kich_thuoc),
                        nguoi_gan=args.nguoi_gan, co_goi_y=not args.khong_goi_y,
                        frame_hw=[cao, rong], chon_frame=chon_frame)
    print(f"index.json → {index}  (frame_hw = {cao}×{rong})")
    if args.chi_sinh:
        print("Chỉ sinh file. Mở trình tô bằng cách bỏ --chi-sinh.")
        return 0

    server = ThreadingHTTPServer((args.host, args.cong), _make_handler(gt_dir, kich_thuoc))
    cong = server.server_address[1]
    print(f"\nMỞ TRÌNH DUYỆT: http://127.0.0.1:{cong}")
    print("Tô bằng chuột (chuột phải = tẩy), bấm 'Lưu & tiếp'. Ctrl+C để dừng.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ndừng.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
