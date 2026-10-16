# 5: PromptSelector: kéo chuột chọn object + phím r chọn lại

**What to build:** Tương tác chọn đối tượng trên cửa sổ OpenCV: ở frame đầu (hoặc frame hiện tại), kéo chuột vẽ ô chọn → thả chuột → hệ thống track đối tượng trong ô. Phím r dừng track và quay về chế độ chọn lại trên frame hiện tại (đáp ứng story chọn nhiều đối tượng liên tiếp). ESC/q thoát.

**Blocked by:** 04

**Status:** claimed

- [x] Kéo chuột vẽ ô có khung trực quan; thả chuột → track khởi động từ ô đó
- [x] Nhấn r → track dừng, về chế độ chọn lại trên frame hiện tại; chọn đối tượng mới thành công
- [x] ESC / q thoát chương trình sạch
