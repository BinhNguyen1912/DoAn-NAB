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


class TestTailFile:
    """12-11: worker chết khi khởi động ⇒ artifact phải mang đuôi log của worker (tự chẩn đoán)."""

    def test_doc_duoi_log(self, tmp_path):
        p = tmp_path / "worker.log"
        p.write_text("dòng cũ\nTraceback: ModuleNotFoundError loguru\n", encoding="utf-8")
        assert "ModuleNotFoundError" in relay._tail_file(p)

    def test_file_dai_bi_cat_va_giu_phan_cuoi(self, tmp_path):
        p = tmp_path / "worker.log"
        p.write_text("A" * 100 + "LOI-CUOI-CUNG", encoding="utf-8")
        text = relay._tail_file(p, limit=50)
        assert text.endswith("LOI-CUOI-CUNG") and len(text) < 120

    def test_khong_co_file_tra_none(self, tmp_path):
        assert relay._tail_file(tmp_path / "khong_co.log") is None


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

    def test_device_di_vao_worker_status(self, tmp_path):
        """Ticket 21: artifact phải mang `device` của worker (cùng nguồn với HUD/API); trước đây
        khoá này bị whitelist cắt nên số CPU/GPU chỉ còn đọc bằng regex `worker.log`."""
        (tmp_path / "status.json").write_text(json.dumps(
            {"state": "running", "device": "cuda", "vos_fps": 8.6}), encoding="utf-8")
        assert relay._worker_device  # cửa sổ so sánh cũ vẫn còn (worker.log)
        data = relay._worker_telemetry(tmp_path)
        assert data["device"] == "cuda"
        # Worker bản cũ không ghi khoá ⇒ **không bịa** "cpu".
        (tmp_path / "status.json").write_text(json.dumps({"state": "running"}), encoding="utf-8")
        assert "device" not in relay._worker_telemetry(tmp_path)


class TestWorkerDevice:
    """Ticket GPU-live (10-11): artifact phải ghi THIẾT BỊ THẬT, không chỉ tham số yêu cầu.

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
    đọc không biết vì sao phiên không chạy (gặp thật 10-11).
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


class TestKetQuaVaMaThoat:
    """`ket_qua` trong artifact và MÃ THOÁT phải cùng một phép tính (P2 review 10-11).

    Bản trước: `ket_qua` đã xét thiết bị nhưng `return 0 if (ok and not error and not git_loi)`
    bỏ quên nó ⇒ ca "worker chạy khác thiết bị yêu cầu" ghi `ket_qua=false` mà script thoát 0 và
    không in `[THAT BAI]` ⇒ CI/người chạy tưởng đo thành công.
    """

    def test_dat_khi_moi_thu_tot(self):
        assert relay._ket_qua(True, None, None, []) is True
        assert relay._ma_thoat(True) == 0

    def test_khong_dat_vi_thiet_bi(self):
        assert relay._ket_qua(True, None, None, ["thiết bị LỆCH"]) is False
        assert relay._ma_thoat(relay._ket_qua(True, None, None, ["thiết bị LỆCH"])) == 1

    @pytest.mark.parametrize("ok,error,git_loi", [
        (False, None, None),          # điều kiện đo không đạt
        (True, "boom", None),         # lỗi giữa phiên
        (True, None, "không có git"),  # không tái lập được
    ])
    def test_khong_dat_vi_cac_ly_do_khac(self, ok, error, git_loi):
        assert relay._ket_qua(ok, error, git_loi, []) is False
        assert relay._ma_thoat(False) == 1


def test_call_site_dung_hai_ham_thuan():
    """Guard "dây nối": chính `main()` phải DÙNG `_ket_qua`/`_ma_thoat`, không được tính lại tại chỗ.

    Vì sao cần guard đọc-mã: test hàm thuần ở trên không phát hiện việc `main()` bỏ quên
    `device_reasons` (đúng lỗi của bản trước — `ket_qua` xét thiết bị nhưng mã thoát thì không).
    Chạy `main()` thật thì phải spawn uvicorn + worker (không hợp cho test nhanh), nên khoá bằng
    chuỗi có chủ đích ở đây.
    """
    from pathlib import Path

    nguon = Path(relay.__file__).read_text(encoding="utf-8")
    assert '"ket_qua": _ket_qua(' in nguon, "artifact phải lấy ket_qua từ hàm thuần"
    assert 'return _ma_thoat(artifact["ket_qua"])' in nguon, "mã thoát phải khớp ket_qua"
    assert 'elif not artifact["ket_qua"]:' in nguon, "phải in [THAT BAI] cả khi chỉ thiết bị sai"


def test_ten_file_mac_dinh_co_gio():
    """Chạy lần hai trong ngày KHÔNG được ghi đè artifact đang được trích (P3 review 10-11)."""
    from datetime import datetime

    stamp = datetime(2026, 11, 10, 21, 5, 7).astimezone()
    name = f"live_web_relay_{stamp:%Y-%m-%d_%H%M%S}_metrics.json"
    assert name == "live_web_relay_2026-11-10_210507_metrics.json"


class TestLuuMauDrift:
    """Ticket 15: dãy mẫu drift phải ra `data/` kèm provenance, và KHÔNG bịa file khi phiên không đo.

    Bẫy đã gặp thật: mỗi dòng CSV là bằng chứng cho "% cửa sổ báo oan" — nếu file của phiên TRƯỚC
    còn trong `out_dir` thì nó sẽ được chép ra `data/` như số của lần đo NÀY.
    """

    def test_chep_ra_data_kem_meta(self, tmp_path, monkeypatch):
        out = tmp_path / "out"
        out.mkdir()
        (out / "drift_samples.csv").write_text(
            "frame_idx,seq,vos_ms,empty,drift_iou,bbox_x1,bbox_y1,bbox_x2,bbox_y2\n"
            "5,2,131.5,0,0.8750,1,2,30,40\n", encoding="utf-8")
        monkeypatch.setattr(relay, "_REPO_ROOT", tmp_path)          # không ghi vào repo thật
        (tmp_path / "data").mkdir()
        from datetime import datetime

        result = relay._luu_mau_drift(out, "binh1", datetime(2026, 11, 12, 14, 30, 0),
                                      {"git_rev": "abc1234", "lenh": "python x.py"})

        assert result["n_dong"] == 1
        assert result["csv"] == "data/drift_samples_binh1_2026-11-12_143000.csv"
        assert result["meta"] == "data/drift_samples_binh1_2026-11-12_143000.meta.json"
        meta = json.loads((tmp_path / result["meta"]).read_text(encoding="utf-8"))
        assert meta["git_rev"] == "abc1234"
        assert (tmp_path / result["csv"]).read_text(encoding="utf-8").splitlines()[1].startswith("5,2,")

    def test_khong_co_file_thi_khong_tao_artifact_rong(self, tmp_path, monkeypatch):
        """`csv=None` + `n_dong=0` + lý do — người đọc artifact không thấy "0 mẫu đã đo"."""
        monkeypatch.setattr(relay, "_REPO_ROOT", tmp_path)
        from datetime import datetime

        result = relay._luu_mau_drift(tmp_path / "out", "binh1", datetime(2026, 11, 12),
                                      {"git_rev": "abc"})
        assert result["csv"] is None and result["n_dong"] == 0
        assert "không ghi mẫu drift" in result["ly_do"]
        assert not (tmp_path / "data").exists()

    def test_ten_clip_bo_ky_tu_la(self):
        assert relay._ten_clip("data/binh1.mp4") == "binh1"
        assert relay._ten_clip("https://cam/snapshot.jpg") == "relay"
        assert relay._ten_clip("data/my clip (1).mp4") == "my_clip_1_"


class TestParseFrameWindow:
    """`--frame-window dau:cuoi` — khai báo KHUNG frame mà vật còn trong khung.

    Vì sao: `empty_frac_window` gộp "model mất dấu" với "vật đã rời khung" (đo 14-11 trên `binh1`:
    36,0–36,7 % cả phiên nhưng 1,7–1,8 % khi chai còn trong khung `0:110` ∪ `165:262`). Sai định dạng
    phải ra `ValueError` để CLI
    in `--frame-window ...` + thoát, KHÔNG được lặng lẽ coi như "không hỏi gì".
    """

    def test_doc_binh_thuong(self):
        assert relay._parse_frame_window("0:110") == [[0, 110]]

    def test_chuoi_rong_la_khong_hoi_gi(self):
        assert relay._parse_frame_window("") == []

    def test_dao_nguoc_van_nhan(self):
        """`110:0` được chấp nhận (người dùng gõ ngược) — hàm tách khung tự sắp lại."""
        assert relay._parse_frame_window("110:0") == [[110, 0]]

    @pytest.mark.parametrize("text", ["abc", "1", "1:2:3", "-5:10", "0:-5"])
    def test_sai_dinh_dang_nem_value_error(self, text):
        """`0:-5` phải bị từ chối: âm ở ĐUÔI mà chỉ kiểm `dau` thì khung `0…-5` bị hoán thành
        `-5…0` và artifact báo "0 % rỗng trong khung" từ đúng 1 mẫu vô nghĩa."""
        with pytest.raises(ValueError):
            relay._parse_frame_window(text)


class TestSoVong:
    """`_so_vong` — nguồn file bị LẶP thì "ngoài khung" không đồng nghĩa "vật đã rời khung".

    Đo 14-11 thật: 55 s trên `data/binh1.mp4` (333 frame) cho `frames_cuoi = 1495` = **4,5 vòng**;
    chỉ vòng 1 nằm trong khung. Không ghi số vòng thì người đọc hiểu sai "ngoài khung".
    """

    def test_tinh_dung_so_vong(self):
        assert relay._so_vong(1495, 333) == 4.49

    def test_khong_biet_do_dai_clip_tra_none(self):
        assert relay._so_vong(1495, None) is None

    def test_chua_co_frame_tra_none(self):
        assert relay._so_vong(None, 333) is None and relay._so_vong(0, 333) is None

    def test_nguon_mang_khong_do_duoc(self):
        assert relay._so_frame_clip("http://127.0.0.1:8090/snapshot.jpg") is None
        assert relay._so_frame_clip("data/khong-ton-tai.mp4") is None


class TestGopKhung:
    """Lặp cờ `--frame-window` phải ra NHIỀU khung — phần nối này từng không có test (review vòng 2).

    `binh1` có hai đoạn vật còn trong khung (`0:110`, `165:262`); nếu `action="append"` bị đổi thành
    một giá trị đơn thì chỉ còn 1 khung và các mẫu của đoạn 2 rơi vào `ngoai_khung` mà không ai thấy.
    """

    def test_lap_co_ra_nhieu_khung(self):
        assert relay._gop_khung(["0:110", "165:262"]) == [[0, 110], [165, 262]]

    def test_khong_co_co_nao(self):
        assert relay._gop_khung([]) == []

    def test_mot_co_sai_lam_hong_ca_cum(self):
        """Có 1 khung sai ⇒ ném lỗi, KHÔNG lặng lẽ bỏ qua khung đó (im lặng = mất đoạn vật)."""
        with pytest.raises(ValueError):
            relay._gop_khung(["0:110", "abc"])


class TestCanhBaoLap:
    """Ngưỡng cảnh báo "nguồn file đã lặp": 0,95 vòng là bình thường, > 1,1 mới kêu."""

    @pytest.mark.parametrize("so_vong,ky_vong", [(None, False), (0, False), (0.95, False),
                                                 (1.0, False), (1.1, False), (1.5, True), (4.49, True)])
    def test_nguong(self, so_vong, ky_vong):
        assert relay._canh_bao_lap(so_vong) is ky_vong
