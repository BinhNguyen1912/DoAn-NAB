"""`./run democheck` (`scripts/demo_preflight.py`) — 9 mục preflight trước buổi demo.

Nguyên tắc được ghim trong test này:
- **"Đọc được frame" ≠ "demo chạy được"**: nguồn đứng hình vẫn qua được mục "đọc được" ⇒ phải có
  mục riêng so sánh hai frame (bẫy "0/None ≠ đã đo" của AGENTS §6).
- **Cảnh báo không bao giờ làm đỏ**: `git` bẩn, `dist` cũ, cổng bận ⇒ in ra để người quyết, mã thoát
  vẫn 0. Nếu mọi thứ đều "bắt buộc" thì lệnh sẽ đỏ vĩnh viễn và không ai đọc nữa.
- **`--full` bắt buộc `--bbox`**: hộp mặc định rơi vào nền ⇒ phiên "chạy được" mà bám sai (AGENTS §6).
"""

import socket

import numpy as np
import pytest

from scripts import demo_preflight as dp


def _check(checks, ten):
    for c in checks:
        if c.ten == ten:
            return c
    raise AssertionError(f"không có mục {ten!r} trong {[c.ten for c in checks]}")


class TestVerdict:
    def test_moi_thu_dat_thi_ma_0(self):
        assert dp.verdict([dp.Check("a", True, "")]) == 0

    def test_canh_bao_khong_lam_do(self):
        assert dp.verdict([dp.Check("a", True, ""), dp.Check("b", False, "", bat_buoc=False)]) == 0

    def test_muc_bat_buoc_hong_thi_ma_1(self):
        assert dp.verdict([dp.Check("a", False, "")]) == 1

    def test_nhan_doc_duoc_bang_mat(self):
        assert dp.Check("a", True, "").nhan.strip() == "OK"
        assert dp.Check("a", False, "").nhan.strip() == "LỖI"
        assert dp.Check("a", False, "", bat_buoc=False).nhan.strip() == "CẢNH BÁO"


class TestCheckpoint:
    def test_thieu_thi_loi_kem_cach_sua(self, tmp_path):
        c = dp.check_checkpoint(tmp_path / "khong_co.pt")
        assert not c.ok and c.bat_buoc
        assert "--checkpoint" in c.chi_tiet

    def test_file_rong_khong_duoc_coi_la_co(self, tmp_path):
        clip = tmp_path / "w.pt"
        clip.write_bytes(b"")
        assert not dp.check_checkpoint(clip).ok

    def test_co_that_thi_ok_kem_dung_luong(self, tmp_path):
        clip = tmp_path / "w.pt"
        clip.write_bytes(b"x" * 2_000_000)
        c = dp.check_checkpoint(clip)
        assert c.ok and "MB" in c.chi_tiet


class TestClipDemo:
    def test_thieu_file(self, tmp_path):
        c = dp.check_clip(tmp_path / "a.mp4")
        assert not c.ok and c.bat_buoc

    def test_clip_that_mo_duoc(self, write_video, tmp_path):
        frames = np.full((10, 32, 48, 3), 70, np.uint8)
        path = write_video(tmp_path / "clip.mp4", frames, fps=10)
        c = dp.check_clip(path, min_frames=5)
        assert c.ok and "48×32" in c.chi_tiet

    def test_clip_qua_ngan_chi_canh_bao(self, write_video, tmp_path):
        path = write_video(tmp_path / "clip.mp4", np.full((3, 16, 16, 3), 5, np.uint8), fps=5)
        c = dp.check_clip(path, min_frames=100)
        assert not c.ok and not c.bat_buoc


class TestWebDist:
    def test_chua_build_thi_loi(self, tmp_path):
        c = dp.check_webbuild(tmp_path / "dist", tmp_path / "src")
        assert not c.ok and c.bat_buoc and "./run web" in c.chi_tiet

    def test_dist_moi_hon_src_thi_ok(self, tmp_path):
        src, dist = tmp_path / "src", tmp_path / "dist"
        (src).mkdir()
        (src / "App.tsx").write_text("x", encoding="utf-8")
        dist.mkdir()
        (dist / "index.html").write_text("<html>", encoding="utf-8")
        assert dp.check_webbuild(dist, src).ok

    def test_dist_cu_chi_canh_bao(self, tmp_path):
        """dist cũ từng làm e2e "PASS" trên mã CŨ (12-11) — phải cảnh báo, nhưng không chặn."""
        src, dist = tmp_path / "src", tmp_path / "dist"
        src.mkdir()
        dist.mkdir()
        (dist / "index.html").write_text("<html>", encoding="utf-8")
        import os
        import time

        past = time.time() - 600
        os.utime(dist / "index.html", (past, past))
        (src / "App.tsx").write_text("x", encoding="utf-8")
        c = dp.check_webbuild(dist, src)
        assert not c.ok and not c.bat_buoc and "CŨ" in c.chi_tiet


class TestApiVaCong:
    def test_api_khong_tra_loi_thi_loi(self):
        c = dp.check_api("http://x", lambda *a, **k: None, bat_buoc=True)
        assert not c.ok and c.bat_buoc

    def test_api_song_thi_ok(self):
        c = dp.check_api("http://x", lambda *a, **k: {"status": "ok"})
        assert c.ok and "ok" in c.chi_tiet

    def test_cong_ban_nhung_api_cua_ta_thi_khong_canh_bao(self, monkeypatch):
        monkeypatch.setattr(dp, "_http_json", lambda *a, **k: {"status": "ok"})
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            port = srv.getsockname()[1]
            assert dp.check_port(port, api_alive=True).ok

    def test_cong_ban_chi_canh_bao(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            port = srv.getsockname()[1]
            c = dp.check_port(port)
        assert not c.ok and not c.bat_buoc


class TestTepPhienCu:
    def test_thu_muc_chua_co_thi_ok(self, tmp_path):
        assert dp.check_stale_state(tmp_path / "chua_co").ok

    def test_bbox_cu_khong_lam_canh_bao(self, tmp_path):
        """`_prepare_dir()` xoá `bbox.json` trước mỗi lần start ⇒ cảnh báo nó là nhiễu (review P2)."""
        import json

        (tmp_path / "bbox.json").write_text(json.dumps({"x": 1, "y": 2, "w": 3, "h": 4}),
                                            encoding="utf-8")
        assert dp.check_stale_state(tmp_path).ok

    def test_worker_mo_coi_con_song_la_canh_bao(self, tmp_path):
        """pidfile còn sống ⇒ có tiến trình đang giữ nguồn, phiên mới sẽ tranh thiết bị."""
        import os

        (tmp_path / "worker.pid").write_text(str(os.getpid()), encoding="utf-8")
        c = dp.check_stale_state(tmp_path)
        assert not c.ok and not c.bat_buoc and "CÒN SỐNG" in c.chi_tiet

    def test_pidfile_cu_da_chet_thi_sach(self, tmp_path):
        (tmp_path / "worker.pid").write_text("999999", encoding="utf-8")
        c = dp.check_stale_state(tmp_path)
        assert c.ok and "đã chết" in c.chi_tiet

    def test_status_loading_cung_la_rac_phien_truoc(self, tmp_path):
        import json

        (tmp_path / "status.json").write_text(json.dumps({"state": "loading"}), encoding="utf-8")
        assert not dp.check_stale_state(tmp_path).ok

    def test_status_dang_chay_la_canh_bao(self, tmp_path):
        import json

        (tmp_path / "status.json").write_text(json.dumps({"state": "running"}), encoding="utf-8")
        c = dp.check_stale_state(tmp_path)
        assert not c.ok and "chưa dọn" in c.chi_tiet

    def test_status_da_dung_thi_khong_bao_dong(self, tmp_path):
        import json

        (tmp_path / "status.json").write_text(json.dumps({"state": "stopped"}), encoding="utf-8")
        assert dp.check_stale_state(tmp_path).ok


class TestNguonVideo:
    def test_loi_doc_nguon_duoc_neu_ro(self):
        c = dp.check_source_frames("0", [], "RuntimeError: bận", 10.0)
        assert not c.ok and "bận" in c.chi_tiet

    def test_du_frame_thi_ok(self):
        frames = [np.zeros((4, 4, 3), np.uint8)] * 8
        assert dp.check_source_frames("0", frames, None, 12.0, n=8).ok

    def test_thieu_frame_thi_loi_kem_ty_le(self):
        c = dp.check_source_frames("0", [np.zeros((4, 4, 3), np.uint8)] * 2, None, 12.0, n=8)
        assert not c.ok and "2/8" in c.chi_tiet

    def test_probe_chi_mo_nguon_mot_lan(self):
        """Một lần mở nguồn: hai lần mở là tự sinh ra "Device busy" mà preflight định phát hiện."""
        calls = {"n": 0}

        def read(source, n, timeout_s):
            calls["n"] += 1
            return [np.zeros((2, 2, 3), np.uint8)] * n, None

        frames, err, _ms = dp.probe_source("0", read, n=4, timeout_s=1.0)
        assert err is None and len(frames) == 4 and calls["n"] == 1


class TestFrameCoDoi:
    def test_frame_giong_het_la_canh_bao(self):
        frame = np.zeros((8, 8, 3), np.uint8)
        c = dp.check_source_moving([frame, frame.copy()])
        assert not c.ok and not c.bat_buoc and "đứng hình" in c.chi_tiet

    def test_frame_doi_thi_ok(self):
        a = np.zeros((8, 8, 3), np.uint8)
        b = np.full((8, 8, 3), 200, np.uint8)
        assert dp.check_source_moving([a, b]).ok

    def test_mot_frame_thi_khong_ket_luan_duoc(self):
        assert not dp.check_source_moving([np.zeros((4, 4, 3), np.uint8)]).ok

    def test_kich_thuoc_doi_la_canh_bao_khong_phai_dang(self):
        """Đổi kích thước giữa hai frame là bất thường, KHÔNG phải bằng chứng nguồn sống."""
        a = np.zeros((8, 8, 3), np.uint8)
        b = np.zeros((10, 10, 3), np.uint8)
        c = dp.check_source_moving([a, b])
        assert not c.ok and not c.bat_buoc


class TestGit:
    def test_cay_sach(self):
        assert dp.check_git(lambda: ("abc1234", False, False, None)).ok

    def test_cay_ban_chi_canh_bao_va_kem_rev(self):
        c = dp.check_git(lambda: ("abc1234def", True, True, None))
        assert not c.ok and not c.bat_buoc and "abc1234" in c.chi_tiet

    def test_ban_chi_trong_data_thi_van_ok(self):
        c = dp.check_git(lambda: ("abc1234", True, False, None))
        assert c.ok and "data/" in c.chi_tiet

    def test_thieu_git_khong_nem(self):
        c = dp.check_git(lambda: (None, None, None, "FileNotFoundError: git"))
        assert not c.ok and not c.bat_buoc and "git" in c.chi_tiet


class TestDienTapFull:
    """`--full`: có nạp model, nên test chỉ kiểm HỢP ĐỒNG (không chạy model thật)."""

    def _args(self, **kw):
        import argparse

        base = dict(base_url="http://127.0.0.1:8010", bbox="1,2,3,4", full=True,
                    full_timeout=5.0, sample_s=0.0)
        base.update(kw)
        return argparse.Namespace(**base)

    @staticmethod
    def _posts(box):
        """Ghi lại (url, timeout) của mọi lần POST; trả body giả cho `start`."""
        def fake(url, payload=None, timeout=5.0, **_kw):
            box.append((url, timeout))
            if url.endswith("/api/live/start"):
                return {"state": "loading"}, None
            return {}, None

        return fake

    def test_thieu_bbox_thi_tu_choi_ngay(self):
        c = dp._rehearsal(self._args(bbox=None), "0")
        assert not c.ok and "--bbox" in c.chi_tiet

    def test_post_start_dung_timeout_dai_vi_endpoint_chan_toi_khi_nap_xong(self, monkeypatch):
        """P0 review 14-11: POST start chặn 3,4–4,1 s (đo được) ⇒ timeout 5 s báo hỏng oan."""
        posts = []
        monkeypatch.setattr(dp, "_http_post", self._posts(posts))
        monkeypatch.setattr(dp, "_http_json", lambda *a, **k: {"state": "loading"})
        monkeypatch.setattr(dp.time, "sleep", lambda _s: None)
        monkeypatch.setattr(dp.time, "perf_counter", _Clock())
        dp._rehearsal(self._args(full_timeout=0.0), "0")

        start_calls = [t for url, t in posts if url.endswith("/api/live/start")]
        assert start_calls, posts
        assert start_calls[0] >= 30.0, f"timeout {start_calls[0]} quá ngắn cho POST start"

    def test_worker_bao_loi_thi_neu_message(self, monkeypatch):
        monkeypatch.setattr(dp, "_http_post", self._posts([]))
        monkeypatch.setattr(dp, "_http_json",
                            lambda *a, **k: {"state": "error", "message": "lỗi trong vòng lặp chính"})
        c = dp._rehearsal(self._args(), "0")
        assert not c.ok and "vòng lặp chính" in c.chi_tiet

    def test_khong_vao_running_thi_loi(self, monkeypatch):
        monkeypatch.setattr(dp, "_http_post", self._posts([]))
        monkeypatch.setattr(dp, "_http_json", lambda *a, **k: {"state": "loading"})
        monkeypatch.setattr(dp.time, "sleep", lambda _s: None)
        monkeypatch.setattr(dp.time, "perf_counter", _Clock())
        c = dp._rehearsal(self._args(full_timeout=0.0), "0")
        assert not c.ok and "running" in c.chi_tiet

    def test_running_nhung_mask_fps_0_bi_bat(self, monkeypatch):
        """`running` + frame tăng mà mask = 0: đường ống sống nhưng model không trả mask."""
        seq = [{"state": "running", "frames": 10}, {"state": "running", "frames": 40, "mask_fps": 0}]
        monkeypatch.setattr(dp, "_http_post", self._posts([]))
        monkeypatch.setattr(dp, "_http_json", lambda *a, **k: seq.pop(0) if seq else {})
        c = dp._rehearsal(self._args(), "0")
        assert not c.ok and "mask_fps = 0" in c.chi_tiet

    def test_running_va_mask_co_thi_ok(self, monkeypatch):
        seq = [{"state": "running", "frames": 10}, {"state": "running", "frames": 40, "mask_fps": 8.5}]
        monkeypatch.setattr(dp, "_http_post", self._posts([]))
        monkeypatch.setattr(dp, "_http_json", lambda *a, **k: seq.pop(0) if seq else {})
        c = dp._rehearsal(self._args(), "0")
        assert c.ok and "8.5" in c.chi_tiet

    def test_phien_chet_trong_luc_lay_mau_thi_khong_bao_ok(self, monkeypatch):
        """P1 review 14-11: `frames`/`mask_fps` sau khi phiên chết là số "dính" từ trước ⇒ phải đỏ."""
        seq = [{"state": "running", "frames": 10, "mask_fps": 9.0},
               {"state": "error", "frames": 40, "mask_fps": 9.0, "message": "worker đã dừng (mã 1)"}]
        monkeypatch.setattr(dp, "_http_post", self._posts([]))
        monkeypatch.setattr(dp, "_http_json", lambda *a, **k: seq.pop(0) if seq else {})
        c = dp._rehearsal(self._args(), "0")
        assert not c.ok and "mã 1" in c.chi_tiet

    def test_phien_duoc_dung_du_dien_tap_nem_giua_duong(self, monkeypatch):
        """`finally` phải gửi stop: preflight không được để phiên live sống tiếp (giữ webcam)."""
        posts = []
        monkeypatch.setattr(dp, "_http_post", self._posts(posts))
        monkeypatch.setattr(dp, "_http_json",
                            lambda *a, **k: {"state": "running", "frames": 5, "mask_fps": 9.0})

        def boom(_s):
            raise RuntimeError("mất mạng giữa lúc lấy mẫu")

        monkeypatch.setattr(dp.time, "sleep", boom)
        with pytest.raises(RuntimeError):
            dp._rehearsal(self._args(), "0")
        assert any(url.endswith("/api/live/stop") for url, _t in posts), posts

    def test_start_that_bai_van_gui_stop_best_effort(self, monkeypatch):
        """Timeout POST **không** chứng minh server chưa dựng phiên ⇒ vẫn phải gửi stop."""
        posts = []

        def fake(url, payload=None, timeout=5.0, **_kw):
            posts.append((url, timeout))
            return None, "HTTP 400: không mở được camera index 0"

        monkeypatch.setattr(dp, "_http_post", fake)
        c = dp._rehearsal(self._args(), "0")
        assert not c.ok and "camera index 0" in c.chi_tiet
        assert any(url.endswith("/api/live/stop") for url, _t in posts), posts


class _Clock:
    """Đồng hồ giả: mỗi lần đọc +1 s để vòng chờ `running` kết thúc ngay trong test."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 1.0
        return self.t


class TestRunChecks:
    def test_9_muc_khi_khong_full(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dp, "read_frames", lambda *a, **k: ([], "RuntimeError: không có nguồn"))
        args = self._args(tmp_path)
        checks = dp.run_checks(args)
        assert len(checks) == 9
        assert dp.verdict(checks) == 1                 # thiếu nguồn là LỖI (bắt buộc)

    def test_nguon_che_la_che_khong_phai_clip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dp, "read_frames",
                            lambda *a, **k: ([np.zeros((4, 4, 3), np.uint8)] * 8, None))
        monkeypatch.setattr(dp, "_http_json", lambda *a, **k: {"status": "ok"})
        monkeypatch.setattr(dp, "_provenance", lambda: ("abc1234", False, False, None))
        args = self._args(tmp_path, source="http://relay/snapshot.jpg")
        checks = dp.run_checks(args)
        clip = _check(checks, "clip demo")
        assert clip.ok and "không phải clip" in clip.chi_tiet

    def test_full_them_mot_muc(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dp, "read_frames",
                            lambda *a, **k: ([np.zeros((4, 4, 3), np.uint8)] * 8, None))
        monkeypatch.setattr(dp, "_rehearsal", lambda *a: dp.Check("diễn tập phiên", True, "ok"))
        checks = dp.run_checks(self._args(tmp_path, full=True))
        assert len(checks) == 10

    @staticmethod
    def _args(tmp_path, **kw):
        import argparse

        base = dict(source=str(tmp_path / "khong_co.mp4"), checkpoint=None,
                    base_url="http://127.0.0.1:1", port=dp.DEFAULT_PORT,
                    out_dir=str(tmp_path / "out"), timeout=0.5, full=False,
                    bbox=None, full_timeout=1.0, sample_s=0.0)
        base.update(kw)
        return argparse.Namespace(**base)
