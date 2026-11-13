"""Test bộ DÒ NGUỒN frame (`/api/live/sources`) — không cần webcam, không cần mạng.

Vì sao có: UI tự điền nguồn để người dùng không phải dán URL relay mỗi lần (`AGENTS.md` §1 yêu cầu
"cho phép người dùng lựa chọn đối tượng" — nhưng bắt dán URL là bước thừa, dễ sai). Bộ dò này mở
webcam và gọi HTTP nên hợp đồng của nó phải được khoá: thứ tự ưu tiên, cờ `available` phải là kết
quả THỬ THẬT, cache (không mở webcam mỗi request), và "không bao giờ ném" ra HTTP.
"""
from pathlib import Path

from src.api.adapters.source_probe import SourceProbe, default_gateway_ip

_ROUTE_FILE = """Iface\tDestination\tGateway\t\tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT
eth0\t00000000\t01B013AC\t0003\t0\t0\t0\t00000000\t0\t0\t0
eth0\t00B013AC\t00000000\t0001\t0\t0\t0\t00F0FFFF\t0\t0\t0
"""


def _probe(tmp_path, *, camera=None, http=None, busy=False, env=None):
    """Bộ dò với hàm thử GIẢ; `camera`/`http` là tập giá trị coi như dùng được."""
    calls = {"camera": [], "http": []}

    def camera_probe(index):
        calls["camera"].append(index)
        return index in (camera or set())

    def http_probe(url):
        calls["http"].append(url)
        return url in (http or set())

    probe = SourceProbe(
        tmp_path,
        camera_probe=camera_probe,
        http_probe=http_probe,
        live_busy=lambda: busy,
        gateway_probe=lambda: "10.0.0.5",
        env=env or {},
    )
    return probe, calls


class TestDocGateway:
    def test_doc_ip_windows_tu_bang_dinh_tuyen(self, tmp_path):
        route = tmp_path / "route"
        route.write_text(_ROUTE_FILE)
        assert default_gateway_ip(route) == "172.19.176.1"

    def test_khong_co_file_thi_none(self, tmp_path):
        """Máy Windows/Colab không có /proc/net/route ⇒ None, không ném."""
        assert default_gateway_ip(tmp_path / "khong-co") is None


class TestThuTuUuTien:
    def test_camera_mo_duoc_thi_goi_y_camera(self, tmp_path):
        probe, calls = _probe(tmp_path, camera={0})
        result = probe.suggest()
        assert result["suggested"] == "0"
        assert calls["camera"] == [0]            # có webcam rồi thì không dò 1, 2

    def test_khong_co_camera_thi_goi_y_relay(self, tmp_path):
        url = "http://10.0.0.5:8090/snapshot.jpg"
        probe, _ = _probe(tmp_path, http={url})
        assert probe.suggest()["suggested"] == url

    def test_khong_co_gi_thi_goi_y_video_demo(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "binh1.mp4").write_bytes(b"x" * (200 * 1024))
        probe, _ = _probe(tmp_path)
        result = probe.suggest()
        assert result["suggested"].endswith("binh1.mp4")
        assert result["candidates"][-1]["available"] is True   # file tồn tại = dùng được

    def test_bo_clip_tam_va_clip_qua_nho(self, tmp_path):
        """`_gui_test.mp4` (160×120, 14 KB) và clip `e2e_*` không được gợi ý cho người dùng."""
        data = tmp_path / "data"
        data.mkdir()
        (data / "_gui_test.mp4").write_bytes(b"x" * 200_000)     # tên tạm → bỏ
        (data / "e2e_web.mp4").write_bytes(b"x" * 200_000)       # clip test → bỏ
        (data / "nho.mp4").write_bytes(b"x" * 1024)              # quá nhỏ → bỏ
        (data / "binh2.mp4").write_bytes(b"x" * 200_000)         # hợp lệ
        probe, _ = _probe(tmp_path)
        sources = [c["source"] for c in probe.suggest()["candidates"] if c["kind"] == "file"]
        assert len(sources) == 1 and sources[0].endswith("binh2.mp4")

    def test_khong_nguon_nao_thi_suggested_rong(self, tmp_path):
        probe, _ = _probe(tmp_path)
        assert probe.suggest()["suggested"] == ""

    def test_cam_relay_url_duoc_thu_truoc_gateway(self, tmp_path):
        """Env URL được thử TRƯỚC, nhưng vẫn thử gateway sau (IP WSL2 đổi sau restart)."""
        url = "http://192.168.1.9:8090/snapshot.jpg"
        probe, calls = _probe(tmp_path, http={url}, env={"CAM_RELAY_URL": url})
        assert probe.suggest()["suggested"] == url
        assert calls["http"][0] == url
        assert "http://10.0.0.5:8090/snapshot.jpg" in calls["http"]


class TestKhongTranhThietBi:
    def test_dang_co_phien_live_thi_khong_mo_webcam(self, tmp_path):
        """Mở webcam để dò trong lúc phiên live đang chạy sẽ tranh thiết bị với chính nó."""
        probe, calls = _probe(tmp_path, busy=True)
        result = probe.suggest()
        assert calls["camera"] == []
        assert all(c["available"] is False for c in result["candidates"] if c["kind"] == "camera")


class TestCache:
    def test_hai_lan_goi_trong_ttl_chi_do_mot_lan(self, tmp_path):
        probe, calls = _probe(tmp_path, camera={0})
        probe.suggest()
        probe.suggest()
        assert calls["camera"] == [0]

    def test_loi_khi_do_khong_lam_no(self, tmp_path):
        def boom(*_a, **_k):
            raise RuntimeError("driver hỏng")

        probe = SourceProbe(tmp_path, camera_probe=boom, http_probe=boom,
                            gateway_probe=boom, env={})
        result = probe.suggest()                 # không ném
        assert result["suggested"] == ""


class TestEndpoint:
    def _client(self, sources):
        from fastapi.testclient import TestClient

        from src.api.main import create_app

        return TestClient(create_app(sources=sources))

    def test_tra_nguon_goi_y(self):
        payload = {
            "suggested": "http://10.0.0.5:8090/snapshot.jpg",
            "candidates": [
                {"source": "0", "label": "Webcam 0", "kind": "camera",
                 "available": False, "note": ""},
                {"source": "http://10.0.0.5:8090/snapshot.jpg",
                 "label": "Relay webcam Windows (snapshot JPEG)", "kind": "relay",
                 "available": True, "note": ""},
            ],
        }
        body = self._client(lambda: payload).get("/api/live/sources").json()
        assert body["suggested"] == payload["suggested"]
        assert [c["kind"] for c in body["candidates"]] == ["camera", "relay"]
        assert body["candidates"][1]["available"] is True

    def test_do_loi_thi_tra_rong_chu_khong_500(self):
        def boom():
            raise RuntimeError("không dò được")

        res = self._client(boom).get("/api/live/sources")
        assert res.status_code == 200
        body = res.json()
        assert body["suggested"] == "" and body["candidates"] == []
        assert res.headers["Cache-Control"] == "no-store"

    def test_do_loi_giua_chung_van_tra_200(self):
        """Dựng DTO nằm trong try: dict hỏng giữa đường không được biến thành 500."""
        def hong_sau_khi_co_du_lieu():
            class _Bad(dict):
                def get(self, *_a, **_k):
                    raise RuntimeError("dữ liệu dò hỏng")

            return _Bad()

        res = self._client(hong_sau_khi_co_du_lieu).get("/api/live/sources")
        assert res.status_code == 200

    def test_bo_do_khong_tim_thay_nguon_thi_tra_rong(self):
        """`create_app(sources=None)` = dùng bộ dò THẬT; muốn "không dò" thì tiêm bộ dò rỗng."""
        res = self._client(lambda: {}).get("/api/live/sources")
        assert res.status_code == 200
        body = res.json()
        assert body["suggested"] == "" and body["candidates"] == []

    def test_source_goi_y_that_su_mo_duoc_bang_live_start(self, tmp_path):
        """Chuỗi gợi ý phải là thứ `/api/live/start` chấp nhận — không phải nhãn hiển thị."""
        (tmp_path / "data").mkdir()
        video = tmp_path / "data" / "demo.mp4"
        video.write_bytes(b"x" * (200 * 1024))
        probe, _ = _probe(tmp_path)
        result = probe.suggest()
        source = result["suggested"]
        assert Path(source).exists(), "gợi ý phải trỏ tới đường dẫn/camera thật dùng được"
        assert result["suggested_kind"] == "file", "UI cần biết gợi ý là nguồn VIDEO, không phải camera"
        assert result["checked_at"], "phải có mốc thời gian dò — 'đã kiểm' không được vô thời hạn"

    def test_ung_vien_co_bang_chung_va_thoi_gian(self):
        """Mỗi ứng viên phải nói RÕ đã kiểm cái gì + mất bao lâu (chống chữ 'đã kiểm' vô nghĩa)."""
        payload = {
            "suggested": "http://10.0.0.5:8090/snapshot.jpg",
            "suggested_kind": "relay",
            "checked_at": "2026-11-13T22:41:03",
            "budget_ms": 1400,
            "candidates": [{"source": "0", "label": "Webcam 0", "kind": "camera",
                            "available": False, "check": "không mở được camera",
                            "latency_ms": 1, "note": ""}],
        }
        body = self._client(lambda: payload).get("/api/live/sources").json()
        assert body["suggested_kind"] == "relay" and body["checked_at"].startswith("2026-11-13")
        assert body["budget_ms"] == 1400
        assert body["candidates"][0]["check"] == "không mở được camera"
        assert body["candidates"][0]["latency_ms"] == 1


class TestNganSachThoiGian:
    """Không thử cv2 khi máy không có thiết bị; HTTP có timeout chặt (review/plan 13-11, góc nhìn C)."""

    def test_may_khong_co_dev_video_thi_khong_thu_cv2(self, monkeypatch):
        """WSL/CI không có `/dev/video*` ⇒ `camera_ok` trả False NGAY (không 90 ms + WARN OpenCV)."""
        import src.api.adapters.source_probe as sp

        monkeypatch.setattr(sp.glob, "glob", lambda _pattern: [])
        monkeypatch.setattr(sp.os, "name", "posix")

        def boom(_index):                     # cv2 không bao giờ được gọi tới
            raise AssertionError("không được mở cv2 khi máy không có /dev/video*")

        import cv2

        monkeypatch.setattr(cv2, "VideoCapture", boom)
        assert sp.camera_ok(0) is False

    def test_http_qua_han_nhanh_khong_treo(self, monkeypatch):
        import src.api.adapters.source_probe as sp

        calls = []

        def slow_urlopen(_url, timeout=None):
            calls.append(timeout)
            raise TimeoutError("black-hole")

        monkeypatch.setattr("urllib.request.urlopen", slow_urlopen)
        assert sp.http_snapshot_ok("http://10.0.0.5:8090/snapshot.jpg") is False
        assert calls == [0.8], "timeout HTTP phải là 0.8 s (ngân sách dò ≤ ~1,6 s cho 2 URL)"


class TestDangBanThietBi:
    def test_loading_cung_la_dang_ban(self):
        """`LOADING` = worker `track` đang nạp model rồi SẼ mở camera ⇒ phải coi là bận (P1 review)."""
        from src.api.domain import LiveState
        from src.api.main import live_uses_device

        class _Live:
            def __init__(self, state):
                self._state = state

            def status(self):
                class _S:
                    pass

                s = _S()
                s.state = self._state
                return s

        assert live_uses_device(_Live(LiveState.RUNNING)) is True
        assert live_uses_device(_Live(LiveState.LOADING)) is True
        assert live_uses_device(_Live(LiveState.STOPPED)) is False
        assert live_uses_device(_Live(LiveState.ERROR)) is False


class TestRelayEnvHong:
    def test_env_sai_van_thu_gateway(self, tmp_path):
        """`CAM_RELAY_URL` kẹt IP cũ (IP WSL2 đổi sau restart) không được chặn dò gateway."""
        gateway_url = "http://10.0.0.5:8090/snapshot.jpg"
        probe, calls = _probe(tmp_path, http={gateway_url},
                             env={"CAM_RELAY_URL": "http://10.9.9.9:8090/snapshot.jpg"})
        result = probe.suggest()
        assert result["suggested"] == gateway_url
        assert calls["http"] == ["http://10.9.9.9:8090/snapshot.jpg", gateway_url]


class TestUngVienHongKhongLam500:
    def test_dict_ung_vien_thieu_khoa_van_200(self):
        from fastapi.testclient import TestClient

        from src.api.main import create_app

        sources = lambda: {"suggested": "0", "candidates": [{"source": "0"}]}   # noqa: E731
        res = TestClient(create_app(sources=sources)).get("/api/live/sources")
        assert res.status_code == 200
        assert res.json()["candidates"] == []      # ứng viên hỏng bị bỏ, không nổ 500
