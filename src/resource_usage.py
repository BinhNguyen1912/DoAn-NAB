"""
ResourceSampler — đo mức sử dụng CPU / RAM (và GPU nếu có) trong lúc chạy (yêu cầu 10 của GVHD).

Chức năng: lấy mẫu tài nguyên theo từng frame để mục "Đánh giá hiệu năng" có đủ 4 đại lượng
    đề cương yêu cầu: **FPS, độ trễ, mức sử dụng CPU/GPU, độ chính xác bám bắt**.
    Hai đại lượng đầu đã có trong `MetricsLogger`; module này bổ sung **mức sử dụng tài nguyên**.

Input  : không (tự đọc tiến trình hiện tại). `gpu_probe` tiêm được để test không cần GPU.
Output : `stats()` → dict `cpu_percent_mean/peak`, `rss_mb_mean/peak`, `cpu_count`,
         `cpu_percent_of_machine_mean`, `gpu` (None nếu không có GPU), `samples`.

Lưu ý  : **không thêm dependency** — đọc `/proc/self/stat` + `/proc/self/status` (Linux/WSL);
         không có `/proc` (Windows/macOS) thì lùi về `resource.getrusage` (chỉ có RSS đỉnh)
         → mọi trường không đo được trả `None`, **không bao giờ ném lỗi** (số liệu thiếu thì
         báo thiếu, đúng tinh thần ADR-0002).
         `cpu_percent` tính theo **1 lõi** (0–100 % × số lõi) như `psutil`/`top`; muốn "% máy"
         thì dùng `cpu_percent_of_machine_mean`.
         GPU: PyTorch không có API đọc % sử dụng nhân GPU; chỉ báo được bộ nhớ đã cấp phát.
         Muốn có % nhân GPU thì cần `pynvml` (chưa cài) → trường đó để `None`, ghi rõ trong báo cáo.
"""
import os
import resource
import time

# Số byte trong 1 MB — VmRSS/VmHWM của /proc tính bằng kB
_KB = 1024.0


def _clock_ticks() -> float:
    """Số nhịp đồng hồ mỗi giây (SC_CLK_TCK); Linux thường 100, không có sysconf thì đoán 100."""
    try:
        return float(os.sysconf("SC_CLK_TCK"))
    except (AttributeError, ValueError, OSError):
        return 100.0


CLOCK_TICKS = _clock_ticks()


def _is_darwin() -> bool:
    """True nếu đang chạy macOS (đơn vị `ru_maxrss` khác Linux)."""
    try:
        return os.uname().sysname == "Darwin"
    except (AttributeError, OSError):
        return False


def read_cpu_seconds() -> float:
    """Tổng thời gian CPU (user+system) của TIẾN TRÌNH hiện tại, đơn vị giây.

    Đọc `/proc/self/stat`: sau dấu ')' cuối cùng là các trường bắt đầu từ field 3 (state)
    → `utime` = field 14 = phần tử thứ 11, `stime` = field 15 = phần tử thứ 12.
    """
    with open("/proc/self/stat", "rb") as f:
        raw = f.read()
    rest = raw.rsplit(b")", 1)[1].split()
    utime, stime = int(rest[11]), int(rest[12])
    return (utime + stime) / CLOCK_TICKS


def read_rss_mb():
    """(rss_mb, rss_peak_mb) của tiến trình — từ `/proc/self/status`, lùi về `getrusage`.

    `ru_maxrss` đơn vị là **kB** trên Linux, **byte** trên macOS → quy đổi theo hệ điều hành.
    Không đọc được thì trả (None, None).
    """
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            values = {}
            for line in f:
                if line.startswith(("VmRSS:", "VmHWM:")):
                    name, rest = line.split(":", 1)
                    values[name] = float(rest.split()[0]) / _KB      # kB → MB
        rss = values.get("VmRSS")
        peak = values.get("VmHWM")
        if rss is not None:
            return rss, (peak if peak is not None else rss)
    except (OSError, ValueError, IndexError):
        pass
    try:
        max_rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # ru_maxrss: kB trên Linux, BYTE trên macOS → đơn vị quyết định hệ số chia
        peak = max_rss / (_KB * _KB) if _is_darwin() else max_rss / _KB
        return None, peak
    except (OSError, ValueError, AttributeError):
        return None, None


def torch_gpu_probe():
    """Thông tin GPU qua PyTorch (nếu có). Không có GPU/CUDA → None.

    Chỉ trả **bộ nhớ đã cấp phát đỉnh** (`max_memory_allocated`), KHÔNG trả % nhân GPU —
    PyTorch không có API đó (cần `pynvml`). Ghi `gpu_util_percent: None` để báo cáo không
    hiểu nhầm là "0 %".
    """
    try:
        import torch
    except ImportError:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        return {
            "gpu_name": torch.cuda.get_device_name(0),
            "gpu_mem_alloc_mb": round(torch.cuda.max_memory_allocated() / (1024.0 * 1024.0), 1),
            "gpu_util_percent": None,
            "gpu_util_note": "cần pynvml để đọc % nhân GPU — chưa cài (ADR-0002: số thiếu thì báo thiếu)",
        }
    except (RuntimeError, AssertionError, OSError):
        return None


def _mean(values):
    """Trung bình cộng, None nếu rỗng (không trả 0 — 0 là một con số đo được, khác 'không đo')."""
    return sum(values) / len(values) if values else None


class ResourceSampler:
    """Lấy mẫu CPU/RAM/GPU mỗi frame; `stats()` tổng hợp cho summary JSON.

    Dùng trong pipeline:
        sampler = ResourceSampler(); sampler.start()
        ... mỗi frame: sampler.sample()
        sampler.stats()      # → chèn vào summary

    `MetricsLogger(sampler=...)` đã tự gọi `sample()` trong `log()` nên run_live không phải sửa.
    """

    def __init__(self, gpu_probe=torch_gpu_probe, clock=time.monotonic):
        self.gpu_probe = gpu_probe
        self._clock = clock
        self._cpu_samples = []
        self._rss_samples = []
        self._last_t = None
        self._last_cpu = None
        self._gpu = None
        self._gpu_read = False

    # -- vòng đời ---------------------------------------------------------
    def start(self) -> None:
        """Ghi mốc thời gian/CPU đầu tiên; gọi 1 lần trước khi vào vòng lặp frame."""
        self._last_t = self._clock()
        try:
            self._last_cpu = read_cpu_seconds()
        except (OSError, ValueError, IndexError):
            self._last_cpu = None

    def sample(self) -> None:
        """Ghi 1 mẫu (gọi cuối mỗi frame). Chưa `start()` thì tự `start()` — không bao giờ ném lỗi."""
        if self._last_t is None:
            self.start()
            return
        now = self._clock()
        wall = now - self._last_t
        try:
            cpu = read_cpu_seconds()
        except (OSError, ValueError, IndexError):
            cpu = None
        if cpu is not None and self._last_cpu is not None and wall > 0:
            # % theo 1 lõi: (giây CPU tiêu thụ) / (giây thực trôi qua) × 100
            self._cpu_samples.append(100.0 * (cpu - self._last_cpu) / wall)
            self._last_cpu = cpu
        self._last_t = now
        rss, peak = read_rss_mb()
        value = peak if peak is not None else rss
        if value is not None:
            self._rss_samples.append(value)
        if not self._gpu_read:
            self._gpu_read = True
            try:
                self._gpu = self.gpu_probe() if self.gpu_probe is not None else None
            except Exception:                    # probe của bên thứ ba hỏng không được làm chết demo
                self._gpu = None

    # -- kết quả ----------------------------------------------------------
    def stats(self) -> dict:
        """Tổng hợp tài nguyên đã đo. Trường không đo được = None (không bịa số 0)."""
        cpu_mean = _mean(self._cpu_samples)
        cpu_peak = max(self._cpu_samples) if self._cpu_samples else None
        rss_mean = _mean(self._rss_samples)
        rss_peak = max(self._rss_samples) if self._rss_samples else None
        ncpu = os.cpu_count() or 1
        return {
            "cpu_percent_mean": None if cpu_mean is None else round(cpu_mean, 1),
            "cpu_percent_peak": None if cpu_peak is None else round(cpu_peak, 1),
            "cpu_percent_of_machine_mean": None if cpu_mean is None else round(cpu_mean / ncpu, 1),
            "cpu_count": ncpu,
            "rss_mb_mean": None if rss_mean is None else round(rss_mean, 1),
            "rss_mb_peak": None if rss_peak is None else round(rss_peak, 1),
            "gpu": self._gpu,
            "samples": len(self._cpu_samples),
            "cpu_note": "cpu_percent tính theo 1 lõi (như psutil/top); % toàn máy = chia cpu_count",
        }
