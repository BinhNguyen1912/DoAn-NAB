# 07a — Giữ danh tính vật thể qua che khuất trong VOS (memory & object queries)

> Báo cáo research — **bản rút gọn tự viết** sau khi scout phụ trách mảng này **timeout 30 phút**
> không ra kết quả. Ngày: **27-10-2026**.
> Nguồn học thuật trong file đều là abstract **fetch trực tiếp** từ `export.arxiv.org` hôm nay.
> Phần XMem / SAMURAI / VS-ReID đã có bảng nguồn đầy đủ ở `docs/research/06-...md` §3.

---

## 1. Câu hỏi

Khi vật bị che khuất hoặc rời khung rồi quay lại, **cơ chế nào giữ được "đây vẫn là cùng một vật"** —
và cơ chế nào trong số đó port được sang hệ thống đang có (SAM 2.1 tiny + SAMURAI, laptop CPU)?

## 2. Bốn hệ thống, bốn cách giữ danh tính

| Hệ | Cách nhớ | Cách đọc memory | Có tìm lại toàn cục? | Nguồn |
|---|---|---|---|---|
| **SAM 2 / SAMURAI** | Memory bank theo từng object (spatial feature + mask) + object pointer; cửa sổ trượt `num_maskmem` frame | Memory attention; SAMURAI **lọc frame đưa vào memory** theo `iou/obj/kf` (Kalman) | ❌ Không — chỉ lan truyền từ trạng thái đã biết | arXiv:2411.11922; code local `samurai/sam2/sam2/modeling/sam2_base.py` |
| **XMem** | 3 tầng: sensory / working / **long-term** + *memory potentiation* (hợp nhất mẫu đang dùng vào bộ nhớ dài hạn) | Đọc theo nhiều tầng, ưu tiên tầng dài hạn cho video dài | ❌ (chỉ lan truyền) | arXiv:2207.07115 |
| **Cutie** | **Object-level memory**: một **bộ nhỏ object queries** làm bản tóm tắt bậc cao của vật | **Top-down** đọc memory (query ↔ pixel feature qua object transformer) thay vì bottom-up từng pixel | ❌ | arXiv:2310.12982 |
| **DEVA** | **Tách đôi**: model phân đoạn ảnh theo tác vụ + module lan truyền thời gian **không phụ thuộc lớp**, train 1 lần dùng cho mọi tác vụ | Lan truyền hai chiều giữa các segment rời rạc | ✅ Một nửa: khi mất dấu, nó **chạy lại model ảnh** trên frame mới để tìm segment ứng viên | arXiv:2309.03903 |
| **VS-ReID** (tiền lệ) | Module lan truyền mask + **module ReID** chạy lặp với nhau | So khớp thích ứng để "lấy lại" thể hiện bị mất | ✅ ReID chính là bước tìm lại | arXiv:1708.00197 |

## 3. Áp dụng được gì cho đồ án này

1. **Cutie là bằng chứng học thuật cho lựa chọn "prototype bank" của mình.** Cutie cho thấy đọc memory ở mức
   **đối tượng** (một ít query tóm tắt vật) bền hơn đọc ở mức pixel khi có vật gây nhiễu. `ReIdSession._obj_refs`
   (tối đa 8 vector đặc trưng) chính là dạng thô của ý tưởng này → **giữ nguyên hướng**, không cần đổi sang
   memory học sẵn.
2. **XMem → việc cần làm ở v2:** thay vì giữ tối đa 8 mẫu rồi đẩy mẫu cũ ra (`deque`), hãy **hợp nhất**
   (consolidation) các mẫu gần nhau thành 1 prototype trung bình → giữ được "trí nhớ dài hạn" mà không nở bộ nhớ.
3. **DEVA → xác nhận kiến trúc "tách đôi" là hợp lệ:** phần bám (SAM 2 + SAMURAI) và phần tìm lại (re-ID) độc lập,
   đúng như `reid.py` đang làm. DEVA dùng **model ảnh** để đề xuất ứng viên khi mất dấu; mình dùng **NCC + đặc trưng
   tay** (23,8 ms — xem log 27-10) vì model ảnh quá nặng trên CPU. Đây là **đánh đổi có ý thức**, không phải thiếu sót.
4. **Không có hệ nào trong 4 hệ trên tự "nhận diện lại vật bất kỳ sau khi rời khung" bằng ngoại hình** —
   trừ DEVA/VS-ReID ở mức tác vụ/lớp. Nghĩa là **khoảng trống mình đang lấp là thật**, không phải làm lại việc thiên hạ đã làm.
5. **Cảnh báo giữ nguyên từ báo cáo 06:** hai vật **giống y hệt** thì mọi cue ngoại hình đều ≈ 1,000 →
   chỉ Kalman/motion memory (đã chạy trong repo) phân biệt được. Đừng hứa với hội đồng điều ngược lại.

## 4. Chưa kiểm chứng

- Chưa đọc **mã nguồn** Cutie/DEVA/XMem (chỉ abstract) → các mô tả cơ chế ở §2 là theo abstract, **chưa** đối chiếu
  file:dòng như đã làm với `07b`/`07c`.
- Chưa có **số đo nào** so sánh các cách đọc memory (không chạy được vì thiếu GPU/data).
- Scout timeout nên **không có** phần so sánh repo/star/license cho mảng này.

## 5. Tài liệu tham khảo (abstract fetch 27-10-2026)

- Cutie — *Putting the Object Back into Video Object Segmentation*, arXiv:2310.12982. https://arxiv.org/abs/2310.12982
- DEVA — *Tracking Anything with Decoupled Video Segmentation*, arXiv:2309.03903. https://arxiv.org/abs/2309.03903
- XMem — arXiv:2207.07115 (chi tiết ở `06-...md` §3)
- SAMURAI — arXiv:2411.11922; VS-ReID — arXiv:1708.00197 (chi tiết ở `06-...md` §3)
