"""Test hàm thuần của `scripts/measure_live_relay.py` — tóm tắt mẫu `/api/live/status` + phán quyết.

Vì sao có: artifact "đường camera thật chạy được" sẽ được trích trong báo cáo. Hai bẫy đã gặp trong
repo phải khoá bằng test:
  1. `None` (chưa đo) bị đổi thành `0,0` ⇒ `drift = 0` trông như "đã đo và rất xấu" (AGENTS §6);
  2. lấy mẫu mà phiên không vào `running` vẫn in bảng "đạt" ⇒ báo động giả ngược lại.
"""

import json

import pytest

import scripts.measure_live_relay as relay


def _mau(**fields):
    # CHỈ trường `LiveStatusResponse` có (drift/age nằm ở `status.json` của worker — xem docstring).
    base = {"state": "running", "frames": 10, "measured_fps": 26.3, "display_fps": 29.8,
            "mask_fps": 8.6, "empty_runs": 0, "message": ""}
    base.update(fields)
    return base


class TestSummarize:
    def test_none_khong_bi_doi_thanh_0(self):
        """Thiếu `mask_fps`/`display_fps` ⇒ `None`, KHÔNG thành `0,0` (bẫy AGENTS §6)."""
        summary = relay.summarize([_mau(mask_fps=None, display_fps=None)])
        assert summary["mask_fps_max"] is None
        assert summary["mask_fps_cuoi"] is None
        assert summary["display_fps_max"] is None

    def test_khong_tao_khoa_ma_api_khong_co(self):
        """`summarize` chỉ được tóm tắt trường API thật có: `drift_*`/`mask_age_p95` nằm ở
        `status.json` (`worker_status`), không được xuất hiện như "đã đo" ở `tom_tat`."""
        summary = relay.summarize([_mau()])
        for key in ("drift_iou_max", "drift_iou_p05_max", "drift_n_cuoi", "mask_age_p95_max"):
            assert key not in summary, f"{key} không có trong API nhưng vẫn được tóm tắt"

    def test_lay_max_cua_cac_mau(self):
        samples = [_mau(measured_fps=10.0, display_fps=25.0, mask_fps=2.0),
                   _mau(measured_fps=29.9, display_fps=30.0, mask_fps=8.7)]
        summary = relay.summarize(samples)
        assert summary["measured_fps_max"] == 29.9
        assert summary["display_fps_max"] == 30.0
        assert summary["display_fps_cuoi"] == 30.0
        assert summary["mask_fps_max"] == 8.7
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


def test_khong_vao_running_thi_khong_dat_va_khong_ghi_artefact_la_dat():
    """`state="stopped"` (phiên chết giữa lúc lấy mẫu) và danh sách mẫu rỗng đều phải KHÔNG đạt —
    fail-closed, không được coi là "đo xong" (review độc lập nhánh bằng chứng, P3)."""
    ok, reasons = relay._verdict(relay.summarize([_mau(state="stopped")]))
    assert ok is False and reasons
    ok_rong, reasons_rong = relay._verdict(relay.summarize([]))
    assert ok_rong is False and reasons_rong


class TestWorkerStatus:
    """`stability_shown` không đi qua API nên chỉ có trong artifact qua `worker_status` — phải đi
    kèm `stability_shown_n` và giữ `None` trung thực (ticket 19, cùng bẫy AGENTS §6)."""

    def test_stability_shown_di_kem_n_va_none_trung_thuc(self, tmp_path):
        (tmp_path / "status.json").write_text(json.dumps({
            "state": "running", "frames": 12, "stability": None, "stability_n": 0,
            "stability_shown": None, "stability_shown_n": 0}), encoding="utf-8")
        data = relay._worker_telemetry(tmp_path)
        assert data["stability_shown"] is None, "chưa đo mà ghi 0,0 là số liệu sai"
        assert data["stability_shown_n"] == 0
        assert data["stability"] is None

    def test_0_0_do_duoc_khong_bi_doi_thanh_none(self, tmp_path):
        """Chiều ngược của bẫy AGENTS §6: `0,0` ĐO ĐƯỢC phải đi nguyên, không bị "làm sạch"."""
        (tmp_path / "status.json").write_text(json.dumps({
            "state": "running", "stability_shown": 0.0, "stability_shown_n": 150}),
            encoding="utf-8")
        data = relay._worker_telemetry(tmp_path)
        assert data["stability_shown"] == 0.0
        assert data["stability_shown_n"] == 150

    def test_thieu_file_thi_khong_bia_so(self, tmp_path):
        assert relay._worker_telemetry(tmp_path) == {}


class TestWorkerDevice:
    """Ticket GPU-live (11-11): artifact phải ghi THIẾT BỊ THẬT, không chỉ tham số yêu cầu.

    Bẫy: quên đặt `$CAMERA_AI_DEVICE` ⇒ worker chạy CPU nhưng `--device cuda` vẫn nằm trong `lenh`
    ⇒ số FPS bị gán sai thiết bị trong báo cáo. Vì vậy đọc từ `worker.log` và ghi cả hai.
    """

    def test_doc_device_tu_worker_log(self, tmp_path):
        (tmp_path / "worker.log").write_text(
            "[worker] nạp model (image_size=192, device=cuda — Tesla T4)...\n"
            "[worker] sẵn sàng | nguồn: 0 | out: /tmp/x | device=cuda\n", encoding="utf-8")
        assert relay._worker_device(tmp_path) == "cuda"

    def test_log_cu_chua_co_device_tra_none(self, tmp_path):
        """Log của worker bản CŨ không có chữ `device=` ⇒ `None` (chưa biết), không đoán 'cpu'."""
        (tmp_path / "worker.log").write_text("[worker] sẵn sàng | nguồn: 0\n", encoding="utf-8")
        assert relay._worker_device(tmp_path) is None

    def test_khong_co_log_tra_none(self, tmp_path):
        assert relay._worker_device(tmp_path) is None


class TestPostGiuThanLoi:
    """API trả `{"detail": "..."}` là LÝ DO THẬT (vd xin `cuda` mà máy không có GPU).

    Bản trước ném `HTTPError: 400` trơn ⇒ artifact nhánh GPU-live ghi một dòng lỗi vô nghĩa, người
    đọc không biết vì sao phiên không chạy (gặp thật 11-11).
    """

    def test_400_co_than_detail_duoc_giu(self):
        import http.server
        import threading

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):                                   # noqa: N802 — API của http.server
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"detail": "khong co GPU CUDA"}')

            def log_message(self, *_args):                       # tắt log ồn
                return

        server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with pytest.raises(RuntimeError, match="khong co GPU CUDA"):
                relay._post(base, "/api/live/start", {"source": "0"}, timeout=5.0)
        finally:
            server.shutdown()
            server.server_close()


class TestVerdictThietBi:
    """`null` ≠ "đã đo" (AGENTS §6): thiết bị không đọc được hoặc lệch ⇒ artifact KHÔNG được trích.

    Bẫy thật: shell `export CAMERA_AI_DEVICE=cuda` rồi chạy script không `--device` ⇒ artifact khai
    "baseline CPU" trong khi worker chạy GPU ⇒ mọi FPS bị gán sai thiết bị trong báo cáo.
    """

    def test_khop_thi_khong_co_ly_do(self):
        assert relay._ly_do_thiet_bi("cpu", "cpu") == []
        assert relay._ly_do_thiet_bi("cuda", "cuda") == []

    def test_khong_doc_duoc_thiet_bi_la_khong_dat(self):
        reasons = relay._ly_do_thiet_bi("cpu", None)
        assert reasons and "worker.log" in reasons[0]

    def test_lech_thiet_bi_la_khong_dat(self):
        reasons = relay._ly_do_thiet_bi("cpu", "cuda")
        assert reasons and "LỆCH" in reasons[0]
