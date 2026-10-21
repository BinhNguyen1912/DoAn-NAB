"""Test đọc `usbipd list` — BUSID đổi sau khởi động lại (1-8 → 2-8) nên phải tự tìm."""
from scripts.usbipd_helper import find_camera_busid, parse_rows

SAMPLE = """Connected:\r
BUSID  VID:PID    DEVICE                                                        STATE\r
1-5    0bda:0129  Realtek USB 2.0 Card Reader                                   Not shared\r
2-8    5986:211c  HD Webcam                                                     Shared (forced)\r
2-10   8087:0026  Intel(R) Wireless Bluetooth(R)                                Not shared\r
\r
Persisted:\r
GUID                                  DEVICE\r
"""


class TestParseRows:
    def test_tach_dung_cac_thiet_bi(self):
        rows = parse_rows(SAMPLE)
        assert len(rows) == 3
        assert rows[1]["busid"] == "2-8"
        assert rows[1]["device"] == "HD Webcam"
        assert "Shared" in rows[1]["state"]
        assert rows[0]["vidpid"] == "0bda:0129"


class TestFindCameraBusid:
    def test_tim_dung_busid_moi(self):
        assert find_camera_busid(SAMPLE) == "2-8"

    def test_busid_cu_khong_con(self):
        assert "1-8" not in [r["busid"] for r in parse_rows(SAMPLE)]

    def test_cac_ten_camera_khac_nhau(self):
        for name in ("HD Webcam", "USB Camera", "Integrated Camera", "UVC Camera"):
            text = f"1-4  1234:5678  {name}   Shared\n"
            assert find_camera_busid(text) == "1-4", name

    def test_khong_co_camera_tra_none(self):
        text = "1-5  0bda:0129  Realtek USB 2.0 Card Reader   Not shared\n"
        assert find_camera_busid(text) is None
