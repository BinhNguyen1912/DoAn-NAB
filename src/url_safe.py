"""Che credential trong URL trước khi ghi nguồn ra file/log/HTTP.

Vì sao có module này: nguồn frame của hệ thống là chuỗi tự do — `0` (webcam), đường dẫn file, hoặc
URL có xác thực như `rtsp://user:pass@camera.local:554/stream`. Chuỗi đó được **echo** vào
`status.json` (`cau_hinh.source`), vào artifact số đo (`nguon`, `meta`), và vào `/api/live/status`
(`source`). Không che thì mật khẩu camera nằm trong những file được commit và trong phản hồi HTTP
(ticket 29) — một lần lỡ tay là phải đổi mật khẩu + viết lại lịch sử git.

Nguyên tắc: **chỉ che khi in ra**. Nguồn THẬT mà worker mở vẫn dùng chuỗi gốc — che ở đó là mất khả
năng kết nối.

Hàm thuần, không I/O ⇒ test được không cần mạng/camera.
"""

from urllib.parse import urlsplit, urlunsplit

# Vị trí `@` phân tách userinfo với host trong `netloc`.
_AT = "@"


def an_userinfo(url: str) -> str:
    """Bản sao của `url` đã bỏ `user:pass@` ở phần host; chuỗi không phải URL trả nguyên.

    Ví dụ:
        >>> an_userinfo("rtsp://u:p@cam.local:554/s1")
        'rtsp://cam.local:554/s1'
        >>> an_userinfo("http://u:p@host/x.jpg")
        'http://host/x.jpg'
        >>> an_userinfo("data/binh1.mp4")          # đường dẫn file, không phải URL
        'data/binh1.mp4'
        >>> an_userinfo("0")                       # webcam index
        '0'

    Ba ca KHÔNG được "che" bừa (mất thông tin thật):
      - không có scheme (`data/binh1.mp4`, `"0"`, `/mnt/d/x.mp4`, `C:\\x.mp4`) ⇒ trả nguyên;
      - có scheme nhưng `netloc` rỗng (`file:data/x.mp4`) ⇒ trả nguyên;
      - `netloc` không có `@` ⇒ trả nguyên (đường dẫn file có thể chứa `@` hợp lệ).
    """
    text = str(url)
    if not text:
        return text
    try:
        parts = urlsplit(text)
    except ValueError:                 # URL hỏng (dấu ngoặc vuông lệch…) — không đoán, trả nguyên
        return text
    if not parts.netloc or _AT not in parts.netloc:
        return text
    # `rsplit` chứ không `split`: mật khẩu có thể chứa `@` (người dùng hay gõ
    # `rtsp://user:pa@ss@host/s`) ⇒ phần sau `@` CUỐI là host thật.
    host = parts.netloc.rsplit(_AT, 1)[1]
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def co_userinfo(url: str) -> bool:
    """`url` có credential nhúng không (dùng để cảnh báo/log, không để in chuỗi gốc)."""
    return an_userinfo(url) != str(url)
