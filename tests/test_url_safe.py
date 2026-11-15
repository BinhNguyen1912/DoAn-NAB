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
        "http://cam.local:8090/snapshot.jpg",   # URL KHÔNG có credential
        "rtsp://cam.local:554/s",
        "",                               # rỗng
        # Đường dẫn file có `@` (hợp lệ với thư mục/tên file) — không được "che" bừa
        "data/clip@2x.mp4",
    ])
    def test_chuoi_khong_co_credential_tra_nguyen(self, nguyen):
        assert an_userinfo(nguyen) == nguyen

    def test_url_hong_khong_lam_sap(self):
        # `urlsplit` ném ValueError với IPv6 lệch ngoặc — không được để việc GHI LOG làm chết phiên
        assert an_userinfo("rtsp://u:p@[::1/stream") == "rtsp://u:p@[::1/stream"

    def test_co_userinfo_phan_biet_duoc(self):
        assert co_userinfo("rtsp://u:p@h/s") is True
        assert co_userinfo("rtsp://h/s") is False
        assert co_userinfo("data/binh1.mp4") is False


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
