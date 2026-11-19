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
                co_goi_y: bool, frame_hw=None, gt_rong=()) -> Path:
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
    frames_cu = [int(f["frame_idx"]) for f in cu.get("frames", []) if isinstance(f, dict)
                 and str(f.get("frame_idx", "")).lstrip("-").isdigit()]
    moi = sorted(set(int(v) for v in frames) | set(frames_cu))
    index = {
        "clip": clip,
        "ten": ten,
        "frames": [{"frame_idx": f} for f in moi],
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
        "cong_cu": "scripts/gt_gan_nhanh.py + scripts/gt_painter.html",
        "tao_luc": datetime.now().isoformat(timespec="seconds"),
        "huong_dan": ("Mở trang do script in ra, tô/eraser bằng chuột, bấm 'Lưu & tiếp'. File GT được "
                      "ghi thẳng vào thư mục này."),
    }
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
            if khai_rong:
                _ghi_gt_rong(gt_dir, frame)
            return self._send(200, f"da luu {ten_gt(frame)}".encode(), "text/plain")

    return Handler


def _ghi_gt_rong(gt_dir: Path, frame: int) -> None:
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
    rong = sorted(set(int(v) for v in index.get("gt_rong") or []) | {int(frame)})
    index["gt_rong"] = rong
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


def main(argv=None) -> int:
    import cv2

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clip", required=True)
    parser.add_argument("--ten", required=True, help="tên bộ GT (thư mục con của docs/gt)")
    parser.add_argument("--nguoi-gan", required=True, help="ai chịu trách nhiệm gán (vào index.json)")
    parser.add_argument("--frames", required=True, help='danh sách frame_idx, vd "0,50,120"')
    parser.add_argument("--khong-goi-y", action="store_true",
                        help="không sinh gợi ý màu (tô tay từ đầu) ⇒ GT 'sạch' hơn")
    parser.add_argument("--s-min", type=int, default=S_MIN, help="ngưỡng bão hoà màu của gợi ý (0–255)")
    parser.add_argument("--v-min", type=int, default=V_MIN, help="ngưỡng sáng tối thiểu của gợi ý")
    parser.add_argument("--cong", type=int, default=8765, help="cổng HTTP của trình tô (0 = tự chọn)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="địa chỉ bind (127.0.0.1 = chỉ máy này; 0.0.0.0 chỉ dùng cho e2e WSL→Windows)")
    parser.add_argument("--chi-sinh", action="store_true", help="chỉ cắt frame + sinh gợi ý, không mở server")
    args = parser.parse_args(argv)

    frames = [int(v) for v in str(args.frames).replace(";", ",").split(",") if v.strip()]
    if not frames:
        raise SystemExit("--frames rỗng")
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
                        frame_hw=[cao, rong])
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
