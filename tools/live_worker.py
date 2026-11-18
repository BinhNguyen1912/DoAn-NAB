"""
Lệnh chạy worker BÁM TRỰC TIẾP (chạy trong tiến trình riêng, có torch/SAM 2).

Chức năng: nạp engine SAMURAI rồi chạy `LiveTrackingSession` — đọc nguồn frame, bám đối tượng
           (chờ ô chọn do API ghi vào `bbox.json`), ghi `frame.jpg` + `status.json` ra `--out-dir`.
Input  : --source (0 | rtsp://… | http://… | đường dẫn video), --out-dir, --image-size, --max-fps.
Output : file trong --out-dir (frame.jpg, status.json, worker.log) + log console.
Lưu ý  : tool này CHẠY BẰNG python có torch (conda env samurai). API KHÔNG import nó.
         Ghi status "loading" NGAY khi khởi động để API biết worker còn sống trong lúc nạp model
         (20–60 s trên CPU) thay vì tưởng worker treo.
         Ctrl+C / SIGTERM → dừng sạch, ghi status "stopped".
"""

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.live_tracking import (  # noqa: E402
    STATE_ERROR,
    STATE_LOADING,
    LiveTrackConfig,
    LiveTrackStats,
    LiveTrackingSession,
    cau_hinh_yeu_cau,
    session_exit_code,
    status_payload,
    write_json_atomic,
)  # noqa: E402
from src.url_safe import an_userinfo  # noqa: E402 — che credential khi in nguồn ra worker.log


def _write_loading(out_dir: Path, message: str = "Đang nạp model...", *, device: str = "",
                   cau_hinh: dict | None = None) -> None:
    """Ghi trạng thái "loading" bằng CHÍNH payload của phiên chạy (một nguồn schema).

    `device` là thiết bị ĐỊNH chạy: người xem phải biết phiên này sẽ chạy CPU hay GPU ngay từ
    lúc nạp (nạp 20–240 s), không phải đọc `worker.log` (ticket 21).
    Mặc định `""` = **chưa biết** — cố tình KHÔNG mặc định `cpu`: ai gọi mà quên truyền thì file
    phải nói "chưa biết", không được khẳng định "cpu" (AGENTS §6; P3 review 12-11).
    `cau_hinh` = cấu hình ĐỊNH chạy (`cau_hinh_yeu_cau`); `image_size_hieu_luc` chỉ có sau khi nạp
    model, nên giai đoạn này nó **có mặt nhưng luôn `None`** (`image_size_kiem_duoc = False` = chưa
    kiểm được, KHÔNG phải "khớp").
    """
    write_json_atomic(out_dir / "status.json",
                      status_payload(LiveTrackStats(state=STATE_LOADING, message=message,
                                                    device=device,
                                                    cau_hinh=dict(cau_hinh or {}))))


def _cuda_available() -> bool:
    """Máy (tiến trình này) có CUDA không — `False` cả khi thiếu torch."""
    try:
        import torch
    except Exception:                # noqa: BLE001 — thiếu torch HOẶC torch hỏng (vd OSError libcudart)
        # Bắt rộng vì worker luôn có torch; nếu torch hỏng kiểu `OSError: libcudart.so.12` thì một
        # `except ImportError` sẽ để traceback làm status.json kẹt ở `loading` (P3 review 10-11).
        return False
    return bool(torch.cuda.is_available())


def _device_note(device: str) -> str:
    """Hậu tố log tên GPU thật (rỗng nếu CPU) — để log/artifact không phải đoán thiết bị."""
    if device != "cuda":
        return ""
    try:
        import torch
        return f" — {torch.cuda.get_device_name(0)}"
    except Exception:                # noqa: BLE001 — chỉ là dòng log
        return ""


def _kiem_dump_mask_args(parser, dump_frames, vos_every) -> list[int]:
    """Validate `--dump-mask-frames` ở cửa vào; trả danh sách frame đã kiểm (hàm thuần + `parser.error`).

    Vì sao chặn hẳn khi `vos_every > 1`: model **không hề thấy** frame không chia hết cho N ⇒ mask của
    frame đó không tồn tại. Cho chạy rồi cảnh báo cuối phiên là quá muộn — người dùng đã tưởng có mask
    của frame 40 và chấm GT vào thư mục thiếu file (P0/P2 review hẹp 14-11).
    """
    n = max(1, int(vos_every))
    if n > 1:
        parser.error(
            f"--dump-mask-frames cần --vos-every 1 (đang là {n}): với vos_every={n} chỉ frame chia hết "
            f"cho {n} mới có lần VOS, nên mask của các frame khác KHÔNG tồn tại — chấm mIoU sẽ ghép GT "
            "với mask của frame khác. Dùng --vos-every 1 khi chấm điểm.")
    ra = []
    for phan in str(dump_frames).replace(";", ",").split(","):
        phan = phan.strip()
        if not phan:
            continue
        try:
            so = int(phan)
        except ValueError:
            parser.error(f"--dump-mask-frames: {phan!r} không phải số nguyên")
        if so < 0:
            parser.error(f"--dump-mask-frames: frame {so} âm")
        ra.append(so)
    return ra


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Worker bám đối tượng trực tiếp (ghi frame.jpg + status.json cho API web)"
    )
    parser.add_argument("--source", required=True,
                        help="0 = webcam | rtsp://… | http://…/snapshot.jpg | đường dẫn video")
    parser.add_argument("--out-dir", required=True, help="thư mục chia sẻ với API (nên ở /dev/shm)")
    parser.add_argument("--image-size", type=int, default=None,
                        help="độ phân giải model (192 ≈ 10 FPS, 256 ≈ 6,5 FPS trên CPU)")
    parser.add_argument("--max-fps", type=float, default=30.0,
                        help="nhịp PHÁT frame (display). VOS có thể chậm hơn — LK lấp phần giữa")
    parser.add_argument("--vos-every", type=int, default=3,
                        help="chạy VOS mỗi N frame (1 = VOS mỗi frame, tắt LK; mask mới ở nhịp 1/N)")
    parser.add_argument("--mask-smoothing", type=float, default=1.0,
                        help="trọng số mask MỚI khi trộn theo thời gian (0-1]; 1.0 = tắt (mặc định, "
                             "đo 08-11: bật không cải thiện độ êm mà thêm trễ — data/live_2026-11-08_vos3_smoothing05_metrics.json")
    parser.add_argument("--trajectory-len", type=int, default=100)
    # KHÔNG dùng `choices`: `validate_device` chuẩn hoá hoa/thường + khoảng trắng và cho CÙNG một
    # câu lỗi với API/CLI khác (`--device CUDA` từng bị argparse từ chối bằng usage thô — P3 review 10-11).
    parser.add_argument("--device", default=None,
                        help="thiết bị chạy model: cpu (mặc định) | cuda (NVIDIA/Colab)")
    parser.add_argument("--stop-after-frames", type=int, default=None,
                        help="tự thoát sau N frame đã bám (dùng cho test/thử nhanh)")
    # Xuất mask tại vài frame để chấm mIoU vs GT gán tay (việc #6). Mặc định KHÔNG ghi gì.
    parser.add_argument("--dump-mask-frames", default="",
                        help='xuất mask tại các frame này, vd "0,50,120" (để chấm mIoU với GT)')
    parser.add_argument("--bbox", default="",
                        help='ô chọn có sẵn "x,y,w,h" (dạng xywh như bbox.json) — ghi bbox.json TRƯỚC '
                             "khi phiên chạy; cần cho `--dump-mask-frames` (xem docs/thuoc-do-bam-dung.md)")
    parser.add_argument("--dump-mask-dir", default="",
                        help="thư mục ghi mask (mặc định <out-dir>/masks)")
    args = parser.parse_args()

    # Validate ở cửa vào: trước đây CLI clamp im lặng 0.0 → 0.05 còn schema API lại cho 0.0
    # (lỗi hợp đồng P2, review 08-11).
    if not 0.0 < args.mask_smoothing <= 1.0:
        parser.error("--mask-smoothing phải trong khoảng (0, 1]; 1.0 = tắt làm mượt")

    # `--bbox x,y,w,h` (dạng xywh, cùng dạng bbox.json). KIỂM ngay nhưng GHI SAU khi mọi validate
    # xong: ghi trước như bản nháp sẽ để lại bbox.json rác khi chính lệnh đó sai tham số (`--vos-every
    # 0`), rồi lần chạy sau `--dump-mask-frames` (không `--bbox`) lặng lẽ bám ô cũ (P3 review 18-11).
    def _parse_bbox(text: str) -> dict:
        so = [p.strip() for p in str(text).split(",")]
        if len(so) != 4:
            parser.error('--bbox phải dạng "x,y,w,h"')
        try:
            # SỐ NGUYÊN: `read_bbox` đọc bằng `int()` nên `0.5` sẽ thành 0 (hộp rỗng) — và tài liệu đã
            # quy ước "hộp phải là số nguyên" (`score_miou._hop_bao_hop_le`).
            vals = [int(v) for v in so]
        except ValueError:
            parser.error('--bbox phải là bốn SỐ NGUYÊN "x,y,w,h" (không nhận số thực)')
        x, y, w, h = vals
        if w <= 0 or h <= 0:
            # Lỗi kinh điển của repo: truyền `x1,y1,x2,y2` (AGENTS §6, bug đã làm hỏng cả Phase 4c).
            parser.error("--bbox: w và h phải > 0 (dạng xywh, KHÔNG phải x1,y1,x2,y2)")
        if x < 0 or y < 0:
            parser.error("--bbox: x và y phải >= 0")
        return {"x": x, "y": y, "w": w, "h": h}

    bbox_ghi = _parse_bbox(args.bbox) if args.bbox else None

    # Chặn ngay ở cửa vào (P0 review hẹp 14-11): với `vos_every > 1` model **không hề thấy** frame
    # không chia hết cho N ⇒ không có mask thật để dump. Cho chạy rồi cảnh báo cuối phiên là quá muộn:
    # người dùng đã tưởng có mask của frame 40 và chấm GT vào một thư mục thiếu file.
    if args.dump_mask_frames:
        _kiem_dump_mask_args(parser, args.dump_mask_frames, args.vos_every)
        # (P1 review 17-11, ticket #36) dump mask CHỈ đúng khi phiên bám từ frame đầu. Nếu `bbox.json`
        # chưa có, phiên đọc N frame trong lúc chờ chọn ô rồi mới bắt đầu ⇒ `mask_NNNNNN.png` là frame
        # của PHIÊN, không phải của clip; và nguồn `loop_files` quay vòng nên KHÔNG suy ra được frame
        # clip từ N (`offset + idx` phải mod độ dài clip). Chặn thay vì đoán.
        from src.live_tracking import BBOX_NAME, read_bbox

        duong = Path(args.out_dir) / BBOX_NAME
        # `exists()` là chưa đủ: bbox.json hỏng/viết dở (`{"x":1}`) vẫn cho qua cửa, rồi `read_bbox`
        # trả None ⇒ phiên chờ chọn ô VĨNH VIỄN và dump không có gì (nạp model 20–240 s vô ích).
        if bbox_ghi is None and read_bbox(duong) is None:
            parser.error(
                f"--dump-mask-frames cần {duong} ĐỌC ĐƯỢC trước khi chạy (đặt ô chọn trước: "
                "`--bbox x,y,w,h` hoặc ghi bbox.json) — nếu phiên chờ chọn ô thì tên file mask không "
                "còn là frame của clip (ticket #36)")
    if args.vos_every < 1:
        parser.error("--vos-every phải >= 1")
    if args.max_fps <= 0:
        parser.error("--max-fps phải > 0")

    if bbox_ghi is not None:
        # Ghi SAU toàn bộ validate (xem chú thích ở `_parse_bbox`).
        from src.live_tracking import BBOX_NAME

        (Path(args.out_dir)).mkdir(parents=True, exist_ok=True)
        (Path(args.out_dir) / BBOX_NAME).write_text(json.dumps(bbox_ghi), encoding="utf-8")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    from src.device import normalize_device, validate_device  # không import torch ở module

    # Ghi "loading" TRƯỚC khi `_cuda_available()` (nó import torch, vài giây) để UI không coi worker
    # là treo — nhưng phải kèm thiết bị ĐỊNH chạy. `normalize_device` là hàm thuần nên không làm
    # chậm đường này; tên rác thì để nguyên văn (dưới đây báo `error` với message nêu tên đó).
    try:
        device_hint = normalize_device(args.device)
    except ValueError:
        device_hint = str(args.device)
    # Cấu hình ĐỊNH chạy — ghi ngay từ giai đoạn nạp (20–240 s), không đợi có engine: người đọc
    # `status.json` sớm phải biết phiên sẽ chạy `image_size`/`vos_every`/`display_fps` nào.
    cau_hinh = cau_hinh_yeu_cau(source=args.source, image_size=args.image_size,
                               vos_every=args.vos_every, display_fps=args.max_fps,
                               mask_smoothing=args.mask_smoothing, device=device_hint,
                               dump_mask_frames=getattr(args, "dump_mask_frames", ()) or ())
    _write_loading(out_dir, device=device_hint, cau_hinh=cau_hinh)

    try:
        cuda_ok = _cuda_available()
        device = validate_device(args.device, cuda_available=cuda_ok)
    except ValueError as exc:
        # Lỗi ở CỬA VÀO: ghi status error để UI/watchdog thấy lý do, không nạp checkpoint 156 MB
        write_json_atomic(out_dir / "status.json", status_payload(
            LiveTrackStats(state=STATE_ERROR, device=device_hint, message=str(exc),
                           cau_hinh=cau_hinh)))
        print(f"[LOI] {exc}", flush=True)
        return 2

    from src.tracker_engine import TrackerEngine  # import muộn: cần torch, chỉ trong worker

    print(f"[worker] nạp model (image_size={args.image_size or 'mặc định 1024'}, "
          f"device={device}{_device_note(device)})...", flush=True)
    engine = TrackerEngine.build_default(image_size=args.image_size, device=device)
    # Che `user:pass@` (ticket 29): dòng này vào `worker.log`, và `worker.log` còn bị
    # `scripts/measure_live_relay.py` chép vào artifact ĐƯỢC COMMIT.
    print(f"[worker] sẵn sàng | nguồn: {an_userinfo(str(args.source))} | out: {out_dir} "
          f"| device={device}", flush=True)

    stop = threading.Event()

    def _handle(_signum, _frame):
        print("[worker] nhận tín hiệu dừng — thoát sạch", flush=True)
        stop.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    config = LiveTrackConfig(
        source=args.source,
        out_dir=out_dir,
        device=device,
        display_fps=args.max_fps,
        vos_every=args.vos_every,
        mask_smoothing=args.mask_smoothing,
        trajectory_len=args.trajectory_len,
        stop_after_frames=args.stop_after_frames,
        dump_mask_frames=args.dump_mask_frames,
        dump_mask_dir=args.dump_mask_dir,
    )
    stats = LiveTrackingSession(engine, config).run(stop)
    print(f"[worker] kết thúc: {stats.frames} frame phát, {stats.vos_runs} lần VOS | "
          f"display {stats.measured_fps} FPS | VOS {stats.vos_fps} FPS", flush=True)
    # Mã thoát là tín hiệu DUY NHẤT còn lại cho phụ huynh (systemd, subprocess runner, test): trả 0
    # cho một phiên kết thúc vì lỗi là nói dối, và `worker_source.health()` phân biệt "người dùng bấm
    # Dừng" với "chết vì lỗi" CHÍNH BẰNG mã thoát (14-11).
    if stats.state == STATE_ERROR:
        print(f"[LOI] phiên kết thúc vì lỗi: {stats.message}", flush=True)
    return session_exit_code(stats)


if __name__ == "__main__":
    sys.exit(main())
