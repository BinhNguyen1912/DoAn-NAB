"""Test hàm che credential (`src/url_safe.py`) + các chỗ ECHO nguồn ra ngoài (ticket 29).

Vì sao có: chuỗi nguồn là tự do — `0`, đường dẫn file, hay `rtsp://user:pass@host/s`. Nó được echo
vào `status.json` (`cau_hinh.source`), vào `meta` của artifact mask, vào `nguon` của artifact đo, và
vào `/api/live/status` (`source` của adapter worker). Không che thì mật khẩu camera nằm trong file
được commit và trong phản hồi HTTP.
"""

import json

import pytest

from src.api.adapters.worker_source import WorkerFrameSource
from src.url_safe import an_userinfo, co_userinfo


class TestAnUserinfo:
    @pytest.mark.parametrize(("vao", "ra"), [
        # Dạng thật gặp: camera RTSP có xác thực, relay HTTP basic auth
        ("rtsp://user:pass@cam.local:554/stream1", "rtsp://cam.local:554/stream1"),
        ("http://u:p@192.168.1.9:8090/snapshot.jpg", "http://192.168.1.9:8090/snapshot.jpg"),
        ("https://admin:s3cr3t@cam.example.com/x.mjpg?fps=5",
         "https://cam.example.com/x.mjpg?fps=5"),
        # Chỉ có user, không có mật khẩu — vẫn là thông tin định danh
        ("rtsp://user@cam.local/s", "rtsp://cam.local/s"),
        # Mật khẩu chứa `@`: phần sau `@` CUỐI là host (rsplit, không split)
        ("rtsp://user:pa@ss@cam.local/s", "rtsp://cam.local/s"),
        # IPv6 + port
        ("rtsp://u:p@[::1]:554/s", "rtsp://[::1]:554/s"),
        # Không path: KHÔNG được thêm `/` thừa
        ("rtsp://u:p@cam.local", "rtsp://cam.local"),
        # Protocol-relative (giữ `//`)
        ("//u:p@cam.local/s", "//cam.local/s"),
        # Mật khẩu đã encode `%40` = `@` — vẫn là userinfo, vẫn phải che
        ("rtsp://u:p%40ss@cam.local/s", "rtsp://cam.local/s"),
    ])
    def test_che_credential(self, vao, ra):
        assert an_userinfo(vao) == ra

    @pytest.mark.parametrize("nguyen", [
        "0",                              # webcam index
        "1",
        "data/binh1.mp4",                 # đường dẫn file tương đối
        "/mnt/d/doan-nab/data/binh1.mp4",  # tuyệt đối
        "C:\\data\\binh1.mp4",            # Windows: `urlsplit` coi `C` là scheme, netloc rỗng
        "file:data/binh1.mp4",
        "file:///mnt/d/x.mp4",
        "http://cam.local:8090/snapshot.jpg",   # URL KHÔNG có credential
        "rtsp://cam.local:554/s",
        "",                               # rỗng
        # Đường dẫn file có `@` (hợp lệ với thư mục/tên file) — không được "che" bừa
        "data/clip@2x.mp4",
    ])
    def test_chuoi_khong_co_credential_tra_nguyen(self, nguyen):
        assert an_userinfo(nguyen) == nguyen

    def test_url_hong_khong_lam_sap(self):
        # `urlsplit` ném ValueError với IPv6 lệch ngoặc — không được để việc GHI LOG làm chết phiên.
        # Ghim cả TIỀN ĐỀ: nếu `urlsplit` thôi ném thì test dưới vẫn xanh mà không kiểm gì (P3 review).
        from urllib.parse import urlsplit

        with pytest.raises(ValueError):
            urlsplit("rtsp://u:p@[::1/stream")
        assert an_userinfo("rtsp://u:p@[::1/stream") == "rtsp://u:p@[::1/stream"

    def test_co_userinfo_phan_biet_duoc(self):
        assert co_userinfo("rtsp://u:p@h/s") is True
        assert co_userinfo("rtsp://u@h/s") is True
        assert co_userinfo("rtsp://h/s") is False
        assert co_userinfo("data/binh1.mp4") is False
        # Scheme HOA: `urlsplit` hạ chữ thường ⇒ round-trip khác chuỗi gốc nhưng KHÔNG có credential
        assert co_userinfo("RTSP://h/s") is False
        # Không có `@` ⇒ trả NGUYÊN chuỗi (kể cả hoa/thường) — không "chuẩn hoá" giúp người dùng
        assert an_userinfo("RTSP://h/s") == "RTSP://h/s"


class TestEchoNguonRaNgoai:
    """Ba chỗ sinh dữ liệu phải che — kiểm cả ba, không chỉ kiểm hàm thuần."""

    URL = "rtsp://user:pass@cam.local:554/stream1"
    SACH = "rtsp://cam.local:554/stream1"

    def test_cau_hinh_yeu_cau_khong_mang_mat_khau(self):
        from src.live_tracking import cau_hinh_yeu_cau

        kh = cau_hinh_yeu_cau(source=self.URL, image_size=192)
        assert kh["source"] == self.SACH
        assert "pass" not in json.dumps(kh)

    def test_nhan_nguon_cua_api_khong_mang_mat_khau(self):
        src = WorkerFrameSource.__new__(WorkerFrameSource)
        src._source = self.URL
        assert src.label == f"bám-đối-tượng:{self.SACH}"
        assert "pass" not in src.label

    def test_nguon_that_van_giu_credential(self):
        """Chỉ che khi IN RA. Che cả ở chỗ mở nguồn là phiên RTSP có xác thực không kết nối được."""
        from src.worker.command import build_live_worker_command

        src = WorkerFrameSource.__new__(WorkerFrameSource)
        src._source = self.URL
        assert src._source == self.URL
        argv = build_live_worker_command(src._source, "/tmp/out")
        assert self.URL in " ".join(argv), "lệnh mở nguồn phải nhận URL GỐC (kèm credential)"
        # …còn nhãn hiện ra ngoài thì không
        assert "pass" not in src.label

    def test_meta_manifest_mask_khong_mang_mat_khau(self, tmp_path, monkeypatch):
        """`meta` của artifact mask (manifest.json) — chỗ P2 review 15-11 bắt thiếu test."""
        from src.live_tracking import LiveTrackConfig, LiveTrackingSession

        cfg = LiveTrackConfig(source=self.URL, out_dir=tmp_path)
        session = LiveTrackingSession.__new__(LiveTrackingSession)
        session._cfg = cfg
        session._engine = None
        session._chon_bbox = (1, 2, 3, 4)
        session._write_mask_manifest(tmp_path)
        man = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert man["nguon"] == self.SACH
        assert "pass" not in json.dumps(man)

    def test_artifact_do_live_che_luon_lenh_va_moi_truong(self):
        """`lenh` = sys.argv và `moi_truong` cũng echo nguồn (P0 review 15-11).

        Artifact `data/live_web_relay_*_metrics.json` được COMMIT ⇒ che mỗi `nguon` là chưa đủ.
        """
        import importlib.util
        from pathlib import Path as _P

        path = _P("scripts/measure_live_relay.py")
        spec = importlib.util.spec_from_file_location("_mlr", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        lenh = mod._lenh_an_credential(["--source", self.URL, "--seconds", "10"])
        assert self.URL not in lenh and "pass" not in lenh
        assert "--source" in lenh and self.SACH in lenh, "cờ và tham số khác phải giữ nguyên"


class TestNhanRaHttp:
    """`/api/live/status.source` của mode **raw** (mặc định của UI) — P0 review 15-11."""

    URL = "rtsp://user:pass@cam.local:554/stream1"

    def test_nhan_mode_raw_khong_mang_mat_khau(self):
        from src.api.adapters.opencv_source import OpenCvFrameSource

        src = OpenCvFrameSource(self.URL)
        assert src.label == "nguồn rtsp://cam.local:554/stream1"
        assert "pass" not in src.label

    def test_thong_bao_loi_mo_nguon_khong_mang_mat_khau(self):
        """P1: thông báo lỗi đi vào HTTP 400 (`detail`), `status.json.message`, `worker.log`."""
        from src.video_source import HttpVideoSource, RtspVideoSource

        for nguon in (RtspVideoSource(self.URL), HttpVideoSource(self.URL)):
            with pytest.raises(ConnectionError) as info:
                nguon._raise_open_error()
            assert "pass" not in str(info.value), str(info.value)
            # Vẫn giữ host để người dùng biết sửa cái gì
            assert "cam.local:554" in str(info.value), str(info.value)

    def test_thong_bao_snapshot_hong_khong_mang_mat_khau(self):
        from src.video_source import HttpSnapshotSource

        nguon = HttpSnapshotSource(self.URL)
        nguon._fetch = lambda **kwargs: None            # không mở mạng
        with pytest.raises(ConnectionError) as info:
            nguon.open()
        assert "pass" not in str(info.value), str(info.value)


def test_doctest_trong_module_duoc_chay():
    """`pytest.ini` không bật `--doctest-modules` ⇒ ví dụ trong `src/url_safe.py` sẽ mục nếu không
    có test này (P3 review 15-11). Chạy tay để ví dụ là hợp đồng, không phải trang trí."""
    import doctest

    from src import url_safe

    assert doctest.testmod(url_safe, verbose=False).failed == 0
