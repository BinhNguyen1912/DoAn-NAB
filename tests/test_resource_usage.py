"""Test `src/resource_usage.py` — đo CPU/RAM/GPU cho yêu cầu 10 của GVHD.

Nguyên tắc: không cần GPU, không cần model, không phụ thuộc số đo tuyệt đối của máy
(chạy CI trên runner khác vẫn xanh). Chỉ khẳng định **hợp đồng** của module:
có mẫu → có số; thiếu nguồn đo → None (không bịa 0); không bao giờ ném lỗi.
"""
import builtins
import time

import pytest

from src.resource_usage import (CLOCK_TICKS, ResourceSampler, read_cpu_seconds,
                               read_rss_mb, torch_gpu_probe)

STATS_KEYS = {
    "cpu_percent_mean", "cpu_percent_peak", "cpu_percent_of_machine_mean", "cpu_count",
    "rss_mb_mean", "rss_mb_peak", "gpu", "samples", "cpu_note",
}


def _busy(seconds=0.05):
    """Tiêu CPU thật một khoảng ngắn — có số đo thì mới kiểm được là phép đo hoạt động."""
    end = time.perf_counter() + seconds
    total = 0.0
    while time.perf_counter() < end:
        total += sum(range(200))
    return total


class TestDocTienTrinh:
    def test_clock_ticks_hop_le(self):
        """CLK_TCK là số dương (Linux 100; hệ khác lấy mặc định 100)."""
        assert CLOCK_TICKS > 0

    def test_cpu_seconds_tang_khi_tieu_cpu(self):
        """Thời gian CPU của tiến trình phải TĂNG sau khi chạy vòng lặp bận."""
        before = read_cpu_seconds()
        _busy(0.05)
        after = read_cpu_seconds()
        assert after >= before, "tiêu CPU mà thời gian CPU không tăng — đọc /proc/self/stat sai"

    def test_rss_mb_doc_duoc(self):
        """RSS đọc được và là số dương hợp lý (tiến trình python luôn > 1 MB)."""
        rss, peak = read_rss_mb()
        values = [v for v in (rss, peak) if v is not None]
        assert values, "không đọc được RSS ở cả /proc và getrusage"
        assert all(v > 1.0 for v in values)
        if rss is not None and peak is not None:
            assert peak >= rss - 1.0, "RSS đỉnh không thể nhỏ hơn RSS hiện tại"

    def test_khong_co_gpu_thi_probe_tra_none_hoac_dict(self):
        """Máy không GPU → None; có GPU → dict có khoá bắt buộc (không bịa % nhân GPU)."""
        gpu = torch_gpu_probe()
        assert gpu is None or {"gpu_name", "gpu_mem_alloc_mb", "gpu_util_percent"} <= set(gpu)
        if gpu is not None:
            assert gpu["gpu_util_percent"] is None, "PyTorch không đọc được % nhân GPU — không được bịa"


class TestResourceSampler:
    def test_stats_truoc_khi_start_la_none(self):
        """Chưa đo gì → mọi số là None (khác 0: 'không đo' ≠ 'đo được 0')."""
        s = ResourceSampler(gpu_probe=lambda: None).stats()
        assert set(s) == STATS_KEYS
        assert s["cpu_percent_mean"] is None
        assert s["rss_mb_peak"] is None
        assert s["samples"] == 0

    def test_sample_dau_tien_tu_start(self):
        """`sample()` khi chưa `start()` phải tự khởi động, không ném lỗi, chưa có mẫu CPU."""
        sampler = ResourceSampler(gpu_probe=lambda: None)
        sampler.sample()
        assert sampler.stats()["samples"] == 0

    def test_do_duoc_cpu_va_ram_sau_vai_frame(self):
        """Sau vài frame có tiêu CPU → cpu_percent > 0 và RAM > 0, có mẫu thật."""
        sampler = ResourceSampler(gpu_probe=lambda: None)
        sampler.start()
        for _ in range(5):
            _busy(0.03)
            sampler.sample()
        s = sampler.stats()
        assert s["samples"] == 5
        assert 0.0 <= s["cpu_percent_mean"] <= 100.0 * s["cpu_count"] * 1.5
        assert s["cpu_percent_peak"] >= s["cpu_percent_mean"] or s["cpu_percent_mean"] == 0.0
        assert s["rss_mb_peak"] and s["rss_mb_peak"] > 1.0
        assert s["cpu_percent_of_machine_mean"] <= s["cpu_percent_mean"] + 1e-6
        assert s["cpu_count"] >= 1

    def test_cpu_percent_khong_am_khi_chi_ngoi_cho(self):
        """Không tiêu CPU → % thấp (không âm) — chứng minh công thức delta không lệch dấu."""
        sampler = ResourceSampler(gpu_probe=lambda: None)
        sampler.start()
        time.sleep(0.05)
        sampler.sample()
        s = sampler.stats()
        assert s["cpu_percent_mean"] is not None and s["cpu_percent_mean"] >= 0.0
        assert s["cpu_percent_mean"] < 100.0

    def test_gpu_probe_duoc_goi_dung_mot_lan(self):
        """Probe GPU chỉ gọi 1 lần (không import torch mỗi frame) và giá trị được giữ."""
        calls = []

        def probe():
            calls.append(1)
            return {"gpu_name": "FakeGPU", "gpu_mem_alloc_mb": 12.0, "gpu_util_percent": None}

        sampler = ResourceSampler(gpu_probe=probe)
        sampler.start()
        for _ in range(4):
            sampler.sample()
        assert len(calls) == 1
        assert sampler.stats()["gpu"]["gpu_name"] == "FakeGPU"

    def test_probe_gpu_hong_khong_lam_chet_demo(self):
        """Probe của bên thứ ba ném lỗi → gpu = None, phần còn lại vẫn chạy."""
        def broken():
            raise RuntimeError("driver hỏng")

        sampler = ResourceSampler(gpu_probe=broken)
        sampler.start()
        sampler.sample()
        s = sampler.stats()
        assert s["gpu"] is None
        assert s["rss_mb_peak"] is not None


class TestThieuNguonDo:
    def test_khong_co_proc_thi_tra_none_khong_no(self, monkeypatch):
        """Không có /proc (Windows/macOS) → RSS lùi về getrusage, CPU None, không ném lỗi."""
        real_open = builtins.open

        def fake_open(path, *a, **k):
            if str(path).startswith("/proc/"):
                raise FileNotFoundError(path)
            return real_open(path, *a, **k)

        monkeypatch.setattr(builtins, "open", fake_open)
        with pytest.raises(OSError):
            read_cpu_seconds()
        _rss, peak = read_rss_mb()          # getrusage vẫn cho RSS đỉnh
        assert peak is None or peak > 0.0

        sampler = ResourceSampler(gpu_probe=lambda: None)
        sampler.start()
        sampler.sample()
        s = sampler.stats()
        assert s["cpu_percent_mean"] is None, "thiếu nguồn đo CPU phải là None, không phải 0"
        assert s["samples"] == 0

    def test_sysconf_hong_van_chay(self):
        """Hệ không có sysconf → CLOCK_TICKS mặc định dùng được (chỉ cần > 0)."""
        assert isinstance(CLOCK_TICKS, float) and CLOCK_TICKS > 0


class TestTichHopMetricsLogger:
    def test_summary_khong_co_sampler_khong_doi(self):
        """Không truyền sampler → summary KHÔNG có khoá 'resources' (hành vi cũ giữ nguyên)."""
        from src.metrics_logger import FrameRecord, MetricsLogger

        logger = MetricsLogger()
        logger.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=1.0, center=(5, 5)))
        s = logger.summary()
        assert "resources" not in s
        assert s["total_frames"] == 1

    def test_summary_co_sampler_them_tai_nguyen(self):
        """Có sampler → summary có 'resources', và mỗi lần log() là một mẫu."""
        from src.metrics_logger import FrameRecord, MetricsLogger

        sampler = ResourceSampler(gpu_probe=lambda: None)
        sampler.start()
        logger = MetricsLogger(sampler=sampler)
        for i in range(3):
            logger.log(FrameRecord(frame_idx=i, latency_ms=100.0, score=1.0, center=(5, 5)))
        resources = logger.summary()["resources"]
        assert resources["samples"] == 3
        assert resources["rss_mb_peak"] and resources["rss_mb_peak"] > 1.0

    def test_summary_json_chua_tai_nguyen(self, tmp_path):
        """File summary JSON ghi ra phải có mục 'resources' để báo cáo đọc lại được."""
        import json

        from src.metrics_logger import FrameRecord, MetricsLogger

        sampler = ResourceSampler(gpu_probe=lambda: None)
        sampler.start()
        logger = MetricsLogger(sampler=sampler)
        logger.log(FrameRecord(frame_idx=0, latency_ms=100.0, score=1.0, center=(5, 5)))
        path = logger.write_summary_json(str(tmp_path / "s_summary.json"))
        data = json.loads(open(path, encoding="utf-8").read())
        assert data["resources"]["samples"] == 1
        assert data["total_frames"] == 1
