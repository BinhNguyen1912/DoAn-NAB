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
        (tmp_path / "data" / "binh1.mp4").write_bytes(b"x")
        probe, _ = _probe(tmp_path)
        result = probe.suggest()
        assert result["suggested"].endswith("binh1.mp4")
        assert result["candidates"][-1]["available"] is True   # file tồn tại = dùng được

    def test_khong_nguon_nao_thi_suggested_rong(self, tmp_path):
        probe, _ = _probe(tmp_path)
        assert probe.suggest()["suggested"] == ""

    def test_cam_relay_url_duoc_uu_tien_hon_do_gateway(self, tmp_path):
        url = "http://192.168.1.9:8090/snapshot.jpg"
        probe, calls = _probe(tmp_path, http={url}, env={"CAM_RELAY_URL": url})
        assert probe.suggest()["suggested"] == url
        assert calls["http"] == [url]            # không dò thêm IP gateway


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
        assert res.json() == {"suggested": "", "candidates": []}

    def test_bo_do_khong_tim_thay_nguon_thi_tra_rong(self):
        """`create_app(sources=None)` = dùng bộ dò THẬT; muốn "không dò" thì tiêm bộ dò rỗng."""
        res = self._client(lambda: {}).get("/api/live/sources")
        assert res.status_code == 200
        assert res.json() == {"suggested": "", "candidates": []}

    def test_source_goi_y_that_su_mo_duoc_bang_live_start(self, tmp_path):
        """Chuỗi gợi ý phải là thứ `/api/live/start` chấp nhận — không phải nhãn hiển thị."""
        (tmp_path / "data").mkdir()
        video = tmp_path / "data" / "demo.mp4"
        video.write_bytes(b"x")
        probe, _ = _probe(tmp_path)
        source = probe.suggest()["suggested"]
        assert Path(source).exists(), "gợi ý phải trỏ tới đường dẫn/camera thật dùng được"
