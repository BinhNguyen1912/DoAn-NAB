"""
Dựng lệnh chạy pipeline — hàm THUẦN, không chạm đĩa, không chạy gì.

Chức năng: biến (thư mục job, tham số track, bbox) thành argv cho subprocess.Popen.
Input  : job_dir (đường dẫn thư mục job có source.mp4), params (dict), bbox (x,y,w,h),
         python_exe (mặc định "python" trong conda env).
Output : ["bash", "-lc", "<lệnh đầy đủ>"].
Lưu ý  : đây là module DUY NHẤT biết `tools/run_live.py` tồn tại — đổi sang GPU worker
         (Modal/RunPod) chỉ cần thay lớp gọi, không phải sửa chỗ nào khác.
"""

import shlex
from pathlib import Path

# `python` trần KHÔNG tồn tại trong WSL (chỉ có python3 hệ thống = 3.14, không cài được torch)
# → buộc phải activate conda trước khi gọi.
CONDA_ACTIVATE = "source ~/miniconda3/etc/profile.d/conda.sh && conda activate samurai"

# Script pipeline đã được đo đạc nhiều lần (docs/task/) — dùng lại đúng nó thay vì viết lại
# vòng lặp tracking, để số liệu web đo ra trùng số liệu trong báo cáo.
RUN_LIVE_REL = "tools/run_live.py"

# Worker bám trực tiếp (Phase 4b) — chạy trong tiến trình riêng vì cần torch/SAM 2
LIVE_WORKER_REL = "tools/live_worker.py"

# Tên file cố định trong thư mục job (hợp đồng giữa pipeline ↔ storage ↔ API ↔ frontend)
SOURCE_NAME = "source.mp4"
OUT_NAME = "out.mp4"
WEB_NAME = "out_web.mp4"   # bản H.264 để trình duyệt phát được (xem web_export.py)
METRICS_NAME = "metrics.csv"
SUMMARY_NAME = "summary.json"
RUN_INFO_NAME = "run_info.json"
PROGRESS_NAME = "progress.json"
LOG_NAME = "worker.log"

# Tham số được phép truyền xuống CLI — khoá lạ bị bỏ qua (chống rò rỉ tham số tuỳ ý ra lệnh)
_ALLOWED_INT_PARAMS = {
    "image_size": "--image-size",
    "max_frames": "--max-frames",
    "max_trajectory": "--max-trajectory",
}
_ALLOWED_CUES = ("face", "object", "both")


def build_command(job_dir, *, params: dict, bbox, python_exe: str | None = None,
                  repo_root: Path | None = None) -> list[str]:
    """Trả argv chạy pipeline cho một job (xem docstring đầu module)."""
    job = Path(job_dir).resolve()
    root = Path(repo_root).resolve() if repo_root is not None else job.parents[2]
    params = params or {}
    x, y, w, h = (int(v) for v in bbox)

    args = [
        RUN_LIVE_REL,
        "--source", str(job / SOURCE_NAME),
        "--bbox", f"{x},{y},{w},{h}",
        "--record", str(job / OUT_NAME),
        "--metrics-csv", str(job / METRICS_NAME),
        "--metrics-summary", str(job / SUMMARY_NAME),
        # Backend đọc file này để vẽ thanh tiến trình (flag thêm cho web, mặc định tắt)
        "--progress-json", str(job / PROGRESS_NAME),
    ]
    for key, flag in _ALLOWED_INT_PARAMS.items():
        if params.get(key):
            args += [flag, str(int(params[key]))]

    if params.get("reid"):
        args.append("--reid")
        cue = params.get("cue") or "object"
        # Mặc định của repo là cue=face; job web mặc định bám VẬT nên phải nói rõ.
        if cue in _ALLOWED_CUES:
            args += ["--reid-cue", cue]

    inner = " ".join([shlex.quote(python_exe or "python")] + [shlex.quote(a) for a in args])
    return ["bash", "-lc", f"{CONDA_ACTIVATE} && cd {shlex.quote(str(root))} && {inner}"]


def build_live_worker_command(source: str, out_dir, *, image_size: int | None = None,
                              max_fps: float = 30.0, vos_every: int | None = None,
                              python_exe: str | None = None,
                              repo_root: Path | None = None) -> list[str]:
    """Trả argv chạy worker bám trực tiếp (tools/live_worker.py) trong conda env.

    Input  : source (0 | rtsp:// | http:// | đường dẫn video), out_dir (thư mục chia sẻ với API).
    Output : ["bash", "-lc", "<lệnh đầy đủ>"] — giống build_command, dùng chung cách activate conda.
    Lưu ý  : worker này NẠP MODEL (~20–60 s trên CPU) nên caller phải chờ frame đầu tiên với
             timeout lớn (xem src/api/adapters/worker_source.py).
    """
    root = Path(repo_root).resolve() if repo_root is not None else Path(out_dir).resolve().parents[0]
    args = [
        LIVE_WORKER_REL,
        "--source", str(source),
        "--out-dir", str(Path(out_dir).resolve()),
        "--max-fps", str(float(max_fps)),
    ]
    if image_size:
        args += ["--image-size", str(int(image_size))]
    if vos_every:
        args += ["--vos-every", str(max(1, int(vos_every)))]
    inner = " ".join([shlex.quote(python_exe or "python")] + [shlex.quote(a) for a in args])
    return ["bash", "-lc", f"{CONDA_ACTIVATE} && cd {shlex.quote(str(root))} && {inner}"]
