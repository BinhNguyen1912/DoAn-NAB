"""
Tìm nhanh camera điện thoại/IP đang phát trong mạng LAN (phục vụ demo ticket 03).

Chức năng: quét các host trong subnet của máy (mặc định /24) trên vài cổng thường dùng của
app camera điện thoại (8080 IP Webcam, 4747 DroidCam, 8081, 8088, 5000…), thử mở bằng
OpenCV như một luồng MJPEG và in ra URL đọc được frame.

Input  : --subnet (mặc định: subnet của máy), --ports (mặc định "8080,4747,8081,8088,5000"),
         --paths (mặc định "/video,/videofeed,/mjpegfeed"), --timeout (giây/host).
Output : danh sách URL mở được + kích thước frame, kèm lệnh chạy pipeline gợi ý.
Lưu ý  : chỉ quét MẠNG CỤC BỘ của chính máy; không cần model nên chạy rất nhanh.
         Nếu app hiện sẵn URL trên màn hình thì dùng URL đó — tool này chỉ để đỡ phải mò.
"""
import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.video_source import open_video_source  # noqa: E402

DEFAULT_PORTS = "8080,4747,8081,8088,5000"
DEFAULT_PATHS = "/video,/videofeed,/mjpegfeed"


# Dải KHÔNG phải LAN thật: loopback, link-local, và 172.16.0.0/12 (WSL2 NAT dùng 172.19.x)
_NOT_LAN_RE = re.compile(r"^(127\.|169\.254\.|172\.(1[6-9]|2[0-9]|3[01])\.)")


def pick_lan_ip(ips):
    """Chọn IP LAN thật: ưu tiên 192.168.*, rồi 10.*; bỏ loopback/link-local/WSL NAT."""
    candidates = [ip for ip in ips if ip and not _NOT_LAN_RE.match(ip)]
    for prefix in ("192.168.", "10."):
        for ip in candidates:
            if ip.startswith(prefix):
                return ip
    return candidates[0] if candidates else None


def windows_lan_ips():
    """IP của Windows host qua interop — WSL2 nằm sau NAT nên không tự biết LAN thật."""
    if not shutil.which("powershell.exe"):
        return []
    cmd = ["powershell.exe", "-NoProfile", "-Command",
           "Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object { $_.IPAddress }"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def subnet_of_local_host():
    """Đoán subnet /24: ưu tiên IP LAN của Windows host (WSL2), sau đó IP của chính máy.

    Lỗi thật 18-10: trong WSL2 `connect(8.8.8.8)` trả IP NAT nội bộ (172.19.x) → quét nhầm dải.
    """
    ip = pick_lan_ip(windows_lan_ips())
    if ip:
        return ".".join(ip.split(".")[:3])
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # UDP connect: chỉ để lấy IP nguồn, không có traffic
            ip = s.getsockname()[0]
        return ".".join(ip.split(".")[:3])
    except OSError:
        return None


def port_open(host, port, timeout=0.35):
    """True nếu TCP port mở (nhanh, trước khi thử giải mã video)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_url(url):
    """Mở URL như luồng video; trả (url, (W,H)) nếu đọc được frame, ngược lại None."""
    try:
        src = open_video_source(url, open_timeout_ms=1500).open()
    except Exception:
        return None
    try:
        frame = src.read()
        if frame is None:
            return None
        return url, (frame.shape[1], frame.shape[0])
    finally:
        src.close()


def main():
    ap = argparse.ArgumentParser(description="Tìm camera điện thoại/IP trong mạng LAN")
    ap.add_argument("--subnet", default=None, help="tiền tố mạng, ví dụ 192.168.1 (mặc định: tự đoán)")
    ap.add_argument("--ports", default=DEFAULT_PORTS, help=f"cổng cần thử (mặc định {DEFAULT_PORTS})")
    ap.add_argument("--paths", default=DEFAULT_PATHS, help=f"đường dẫn stream (mặc định {DEFAULT_PATHS})")
    ap.add_argument("--timeout", type=float, default=0.35, help="timeout mỗi lần thử cổng (giây)")
    ap.add_argument("--workers", type=int, default=64, help="số luồng quét song song")
    args = ap.parse_args()

    subnet = args.subnet or subnet_of_local_host()
    if not subnet:
        print("[LOI] Không đoán được subnet — truyền --subnet (ví dụ --subnet 192.168.1)")
        raise SystemExit(1)
    ports = [int(p) for p in args.ports.split(",") if p.strip()]
    paths = [p.strip() for p in args.paths.split(",") if p.strip()]

    print(f"[quet] subnet {subnet}.1-254 | cổng {ports} | đường dẫn {paths}")

    hosts = [f"{subnet}.{i}" for i in range(1, 255)]
    targets = []

    # Bước 1: lọc host có cổng mở (nhanh), song song
    def check_host(host):
        return [port for port in ports if port_open(host, port, args.timeout)]

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for host, open_ports in zip(hosts, pool.map(check_host, hosts)):
            for port in open_ports:
                for path in paths:
                    targets.append(f"http://{host}:{port}{path}")

    if not targets:
        print("[ket qua] Không thấy host nào mở cổng camera trong subnet này.")
        print("  - Kiểm tra điện thoại và máy CÙNG một mạng Wi-Fi, app đã bấm Start server.")
        print("  - Nếu app hiện URL trên màn hình, dùng trực tiếp URL đó với --source.")
        raise SystemExit(2)

    print(f"[quet] {len(targets)} URL ứng viên — thử mở từng cái…")

    # Bước 2: thử giải mã frame thật
    found = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        for res in pool.map(probe_url, targets):
            if res:
                found.append(res)
                url, (w, h) = res
                print(f"  [OK] {url} → {w}x{h}")

    if not found:
        print("[ket qua] Có cổng mở nhưng không đọc được frame MJPEG.")
        print("  - Thử đường dẫn khác: --paths /video,/videofeed,/mjpegfeed,/stream")
        print("  - App chỉ phát RTSP → dùng rtsp://<IP>:<port>/<path>")
        raise SystemExit(3)

    print("=" * 60)
    print("Chạy pipeline với URL tìm được:")
    for url, _ in found:
        print(f'  python tools/run_live.py --source "{url}" --display')


if __name__ == "__main__":
    main()
