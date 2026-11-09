"""Test hàm thuần của `scripts/measure_live_relay.py` — tóm tắt mẫu `/api/live/status` + phán quyết.

Vì sao có: artifact "đường camera thật chạy được" sẽ được trích trong báo cáo. Hai bẫy đã gặp trong
repo phải khoá bằng test:
  1. `None` (chưa đo) bị đổi thành `0,0` ⇒ `drift = 0` trông như "đã đo và rất xấu" (AGENTS §6);
  2. lấy mẫu mà phiên không vào `running` vẫn in bảng "đạt" ⇒ báo động giả ngược lại.
"""

import scripts.measure_live_relay as relay


def _mau(**fields):
    base = {"state": "running", "frames": 10, "measured_fps": 29.8, "mask_fps": 8.6,
            "drift_iou": 0.9, "drift_iou_p05": 0.7, "drift_n": 12, "mask_age_p95": 210.0,
            "empty_runs": 0, "message": ""}
    base.update(fields)
    return base


class TestSummarize:
    def test_none_khong_bi_doi_thanh_0(self):
        summary = relay.summarize([_mau(drift_iou=None, drift_iou_p05=None, drift_n=0,
                                        mask_age_p95=None)])
        assert summary["drift_iou_max"] is None
        assert summary["drift_iou_p05_max"] is None
        assert summary["mask_age_p95_max"] is None
        assert summary["drift_n_cuoi"] == 0

    def test_lay_max_cua_cac_mau(self):
        samples = [_mau(measured_fps=10.0, mask_fps=2.0, drift_iou=0.5),
                   _mau(measured_fps=29.9, mask_fps=8.7, drift_iou=0.93)]
        summary = relay.summarize(samples)
        assert summary["measured_fps_max"] == 29.9
        assert summary["mask_fps_max"] == 8.7
        assert summary["drift_iou_max"] == 0.93
        assert summary["n_mau"] == 2

    def test_frames_tang_dan_duoc_ghi_dau_va_cuoi(self):
        summary = relay.summarize([_mau(frames=3), _mau(frames=41)])
        assert (summary["frames_dau"], summary["frames_cuoi"]) == (3, 41)

    def test_danh_sach_rong_khong_no(self):
        summary = relay.summarize([])
        assert summary["n_mau"] == 0 and summary["state_cuoi"] is None


class TestVerdict:
    def test_du_dieu_kien_thi_dat(self):
        ok, reasons = relay._verdict(relay.summarize([_mau()]))
        assert ok is True and reasons == []

    def test_frame_0_la_khong_dat(self):
        ok, reasons = relay._verdict(relay.summarize([_mau(frames=0)]))
        assert ok is False and any("frames" in r for r in reasons)

    def test_mask_fps_0_la_khong_dat(self):
        """`mask_fps = 0` nghĩa là mask không được cập nhật — không phải mode track chạy được."""
        ok, reasons = relay._verdict(relay.summarize([_mau(mask_fps=0.0)]))
        assert ok is False and any("mask_fps" in r for r in reasons)

    def test_state_error_la_khong_dat(self):
        ok, reasons = relay._verdict(relay.summarize([_mau(state="error")]))
        assert ok is False and any("state_cuoi" in r for r in reasons)
