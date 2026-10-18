"""Test phần chọn subnet của tools/find_phone_camera.py.

Lỗi thật 18-10: chạy trong WSL → tool tự đoán subnet và ra 172.19.177.x (mạng NAT của WSL),
quét nhầm cả dải, không thấy camera. Phải ưu tiên IP LAN thật (192.168.x) lấy từ Windows host.
"""
from tools.find_phone_camera import pick_lan_ip


class TestPickLanIp:
    def test_uu_tien_192_168_hon_dai_nat_wsl(self):
        ips = ["172.19.177.162", "192.168.1.34", "10.0.0.5"]
        assert pick_lan_ip(ips) == "192.168.1.34"

    def test_bo_qua_172_16_den_172_31_va_loopback(self):
        ips = ["127.0.0.1", "169.254.10.2", "172.19.176.1", "10.5.6.7"]
        assert pick_lan_ip(ips) == "10.5.6.7"

    def test_khong_co_ip_lan_tra_none(self):
        assert pick_lan_ip(["127.0.0.1", "172.19.177.162"]) is None
