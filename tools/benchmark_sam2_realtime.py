"""
Benchmark SAM 2.1 tiny trên máy CPU/Intel iGPU (không CUDA) — PROTOTYPE ĐO THỬ.

Mục tiêu: trả lời câu hỏi "SAM 2.1 tiny có đạt ≥ 10 FPS (real-time) trên máy này không?",
bằng cách đo từng thành phần trên các backend khả dụng:

  A. pipeline  : toàn bộ vòng propagate video trên PyTorch CPU
                 (thời gian encode N frame + thời gian propagate mỗi frame)
  B. encoder   : chỉ phần Image Encoder (chiếm ~90% thời gian mỗi frame) — PyTorch CPU,
                 thử 2 số thread (4 = số nhân lý, 8 = số luồng)
  C. onnx      : export Image Encoder → ONNX → chạy ONNX Runtime CPU (fp32; + thử INT8)
  D. openvino  : chuyển Image Encoder → OpenVINO IR → chạy trên 'CPU' và 'GPU'
                 (GPU = Intel Iris Xe iGPU, nếu WSL expose được)

Cách chạy (từ bất kỳ đâu, dùng env conda 'samurai'):
  /home/msi/miniconda3/envs/samurai/bin/python /mnt/d/DOAN-NAB/tools/benchmark_sam2_realtime.py --phase all
  (hoặc --phase pipeline|encoder|onnx|openvino)

Output: in ra bảng ms/frame + FPS suy ra; tổng streaming/frame ≈ encoder + propagate.
Đây là prototype đo số liệu — code có thể ném đi sau khi ra quyết định kiến trúc.
"""
import argparse
import os
import shutil
import statistics
import time

CKPT_TINY = "/mnt/d/DOAN-NAB/samurai/sam2/checkpoints/sam2.1_hiera_tiny.pt"
CFG_SAMURAI_T = "configs/samurai/sam2.1_hiera_t.yaml"
FRAMES_DIR = "/mnt/d/DOAN-NAB/data/demo_input_frames"
BBOX_TXT = "/mnt/d/DOAN-NAB/data/dog_bbox_frame0.txt"
TMP_FRAMES = "/mnt/d/DOAN-NAB/data/.bench_tmp_frames"
OUT_DIR = "/mnt/d/DOAN-NAB/models/bench"

TARGET_FPS = 10.0  # ngưỡng real-time chốt trong ADR-0001


def median_ms(times_s):
    return statistics.median(times_s) * 1000.0


def fps_of(ms):
    return 1000.0 / ms if ms > 0 else 0.0


def build_model():
    """Build đúng model SAMURAI tiny như demo CPU đã chạy (device=cpu)."""
    from sam2.build_sam import build_sam2_video_predictor

    predictor = build_sam2_video_predictor(CFG_SAMURAI_T, CKPT_TINY, device="cpu")
    return predictor


class ImageEncoderExport:
    """Wrapper biến image encoder (forward trả dict) thành module trả tuple
    để export ONNX/OpenVINO được (dict không export trực tiếp thoải mái)."""


def make_encoder_wrapper(sam_model, torch):
    enc = sam_model.image_encoder

    class _Enc(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.enc = enc

        def forward(self, x):
            out = self.enc(x)
            back = out["backbone_fpn"]
            pos = out["vision_pos_enc"]
            return back[0], back[1], back[2], pos[0].to(back[0].dtype), pos[1].to(back[1].dtype), pos[2].to(back[2].dtype), out["vision_features"]

    return _Enc().eval()


def run_pipeline(max_frames, no_offload=False):
    """A) Đo thời gian encode + propagate của pipeline video thật (PyTorch CPU)."""
    import numpy as np
    import torch

    offload_video = True
    offload_state = not no_offload
    print(f"\n[A][pipeline] chuẩn bị {max_frames} frames tại {TMP_FRAMES} "
          f"| offload_state_to_cpu={offload_state}")
    if os.path.isdir(TMP_FRAMES):
        shutil.rmtree(TMP_FRAMES)
    os.makedirs(TMP_FRAMES)
    names = sorted(f for f in os.listdir(FRAMES_DIR) if f.endswith(".jpg"))[:max_frames]
    if not names:
        raise RuntimeError(f"Không có frames trong {FRAMES_DIR}")
    for n in names:
        shutil.copy(os.path.join(FRAMES_DIR, n), os.path.join(TMP_FRAMES, n))

    with open(BBOX_TXT) as f:
        x, y, w, h = map(int, f.readline().strip().split(","))
    box = (x, y, x + w, y + h)

    predictor = build_model()

    with torch.inference_mode():
        t0 = time.time()
        state = predictor.init_state(TMP_FRAMES, offload_video_to_cpu=offload_video,
                                     offload_state_to_cpu=offload_state)
        t_init = time.time() - t0
        n = state["num_frames"]
        print(f"[A][pipeline] init_state: {n} frames trong {t_init:.1f}s "
              f"(→ ~{t_init/n*1000:.0f} ms/frame cho bước encode+prep)")

        predictor.add_new_points_or_box(state, box=box, frame_idx=0, obj_id=0)

        step_times = []
        for _fidx, _ids, masks in predictor.propagate_in_video(state):
            t1 = time.time()
            step_times.append(t1)
        # khoảng thời gian giữa các lần yield = thời gian xử lý 1 frame mới
        if len(step_times) > 2:
            diffs = np.diff(np.array(step_times))
            print("[A][pipeline] thời gian từng frame (ms):")
            print("  " + ", ".join(f"{d*1000:.0f}" for d in diffs))
            prop_ms = float(diffs.mean() * 1000)
        else:
            prop_ms = float("nan")
        print(f"[A][pipeline] propagate: {len(step_times)} frame, trung bình {prop_ms:.0f} ms/frame "
              f"(= memory attention + decoder)")
        print(f"[A][pipeline] ƯỚC LƯỢNG streaming/frame ≈ encode({t_init/n*1000:.0f}) "
              f"+ propagate({prop_ms:.0f}) = {(t_init/n*1000)+prop_ms:.0f} ms "
              f"→ ~{fps_of((t_init/n*1000)+prop_ms):.1f} FPS")
    return


def _time_pytorch(sam_model, runs=5, warmup=2, img_size=1024):
    import torch
    x = torch.randn(1, 3, img_size, img_size)
    with torch.inference_mode():
        for _ in range(warmup):
            sam_model.image_encoder(x)
        ts = []
        for _ in range(runs):
            t0 = time.time()
            sam_model.image_encoder(x)
            ts.append(time.time() - t0)
    return median_ms(ts)


def run_encoder(model):
    """B) Đo encoder trên PyTorch CPU, thử thread 4 và 8."""
    import torch
    results = {}
    for threads in (4, 8):
        torch.set_num_threads(threads)
        ms = _time_pytorch(model)
        results[threads] = ms
        print(f"[B][encoder|PyTorch CPU] threads={threads}: {ms:.0f} ms/frame → {fps_of(ms):.1f} FPS")
    return results


def run_onnx_encoder(model):
    """C) Export encoder sang ONNX, đo ONNX Runtime CPU (fp32 rồi INT8)."""
    import numpy as np
    import torch
    import onnx
    import onnxruntime as ort

    os.makedirs(OUT_DIR, exist_ok=True)
    fp32_path = os.path.join(OUT_DIR, "sam2.1_tiny_encoder_fp32.onnx")
    if not os.path.isfile(fp32_path):
        print(f"[C][onnx] export từ PyTorch → {fp32_path} (có thể mất ~1 phút)")
        wrapper = make_encoder_wrapper(model, torch)
        dummy = torch.randn(1, 3, 1024, 1024)
        torch.onnx.export(
            wrapper, dummy, fp32_path,
            input_names=["image"],
            output_names=["back0", "back1", "back2", "pos0", "pos1", "pos2", "features"],
            opset_version=17, dynamo=False,
        )
        onnx.checker.check_model(onnx.load(fp32_path))

    def time_ort(path, threads):
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        sess = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])
        inp = {sess.get_inputs()[0].name: np.random.randn(1, 3, 1024, 1024).astype(np.float32)}
        for _ in range(2):
            sess.run(None, inp)
        ts = []
        for _ in range(5):
            t0 = time.time()
            sess.run(None, inp)
            ts.append(time.time() - t0)
        return median_ms(ts)

    ms32 = time_ort(fp32_path, 4)
    print(f"[C][onnx|ORT CPU fp32] threads=4: {ms32:.0f} ms/frame → {fps_of(ms32):.1f} FPS")

    int8_path = os.path.join(OUT_DIR, "sam2.1_tiny_encoder_int8.onnx")
    if not os.path.isfile(int8_path):
        try:
            from onnxruntime.quantization import QuantType, quantize_dynamic
            print("[C][onnx] quantize INT8 (dynamic) ... có thể mất vài phút")
            quantize_dynamic(fp32_path, int8_path, weight_type=QuantType.QUInt8)
        except Exception as e:
            print(f"[C][onnx] INT8 quantize lỗi: {type(e).__name__}: {e}")
    if os.path.isfile(int8_path):
        try:
            ms8 = time_ort(int8_path, 4)
            print(f"[C][onnx|ORT CPU int8] threads=4: {ms8:.0f} ms/frame → {fps_of(ms8):.1f} FPS")
        except Exception as e:
            print(f"[C][onnx] chạy model INT8 lỗi: {type(e).__name__}: {e}")


def run_openvino_encoder(model):
    """D) Chuyển encoder sang OpenVINO IR, đo trên CPU và GPU (Intel Iris Xe nếu được)."""
    import numpy as np
    import torch
    import openvino as ov

    os.makedirs(OUT_DIR, exist_ok=True)
    ir_path = os.path.join(OUT_DIR, "sam2.1_tiny_encoder_ir.xml")
    if not os.path.isfile(ir_path):
        print(f"[D][openvino] convert PyTorch → OpenVINO IR → {ir_path} (có thể mất ~2-6 phút)")
        wrapper = make_encoder_wrapper(model, torch)
        dummy = torch.randn(1, 3, 1024, 1024)
        ov_model = ov.convert_model(wrapper, example_input=dummy, input=([1, 3, 1024, 1024],))
        ov.save_model(ov_model, ir_path)

    core = ov.Core()
    devices = core.get_available_devices()
    print(f"[D][openvino] devices khả dụng: {devices}")

    x_np = np.random.randn(1, 3, 1024, 1024).astype(np.float32)
    for dev in ("CPU", "GPU", "AUTO"):
        if dev not in devices and dev != "AUTO":
            print(f"[D][openvino] device '{dev}' không khả dụng — bỏ qua")
            continue
        try:
            sess = core.compile_model(ir_path, dev)
            sess({sess.input(0): x_np})  # warm-up (không cần giữ output)
            for _ in range(2):
                sess({sess.input(0): x_np})
            ts = []
            for _ in range(5):
                t0 = time.time()
                sess({sess.input(0): x_np})
                ts.append(time.time() - t0)
            ms = median_ms(ts)
            print(f"[D][openvino|{dev}] {ms:.0f} ms/frame → {fps_of(ms):.1f} FPS")
        except Exception as e:
            print(f"[D][openvino|{dev}] lỗi: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", default="all", choices=["all", "pipeline", "encoder", "onnx", "openvino"])
    ap.add_argument("--max_frames", type=int, default=15, help="số frame dùng cho phase pipeline")
    ap.add_argument("--no_offload", action="store_true", help="tắt offload_state_to_cpu (thí nghiệm)")
    args = ap.parse_args()

    import torch
    print(f"torch {torch.__version__} | threads mặc định: {torch.get_num_threads()}")
    model = None
    if args.phase in ("encoder", "onnx", "openvino", "all"):
        print("build model SAM 2.1 tiny (SAMURAI config) ...")
        # build_sam2 trả SAM2Base; encoder timing dùng model.image_encoder
        from sam2.build_sam import build_sam2
        model = build_sam2(CFG_SAMURAI_T, CKPT_TINY, device="cpu")
        model.eval()

    if args.phase in ("pipeline", "all"):
        run_pipeline(args.max_frames, no_offload=args.no_offload)
    if args.phase in ("encoder", "all"):
        run_encoder(model)
    if args.phase in ("onnx", "all"):
        run_onnx_encoder(model)
    if args.phase in ("openvino", "all"):
        run_openvino_encoder(model)

    print(f"\nNgưỡng real-time (ADR-0001): ≥ {TARGET_FPS} FPS (mục tiêu 15–24).")
    print("Lưu ý: tổng streaming/frame ≈ thời gian encoder + thời gian propagate (phase A).")


if __name__ == "__main__":
    main()