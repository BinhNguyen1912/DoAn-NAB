# AGENTS.md — Hướng dẫn cho AI Agent làm việc trong repo này

> File này là **quy ước bắt buộc** cho mọi AI agent (và contributor) khi làm việc trong repo `DoAn-NAB`.
> Đọc kỹ trước khi thực hiện bất kỳ thay đổi nào.

---

## 1. Tổng quan dự án

- **Tên đề tài:** Xây dựng hệ thống Camera AI bám bắt đối tượng theo thời gian thực.
- **Nội dung cốt lõi:** Nhận diện, phân đoạn và bám bắt đối tượng trong video real-time dựa trên:
  - **Image Segmentation** (phân đoạn ảnh)
  - **Motion Memory** (bộ nhớ chuyển động)
  - **Temporal Propagation** (lan truyền theo thời gian)
- **Yêu cầu sản phẩm cuối kỳ:**
  1. Thu nhận & xử lý video trực tiếp (Camera USB/IP).
  2. Cho phép người dùng **lựa chọn đối tượng** cần bám bắt.
  3. Phân đoạn & theo dõi đối tượng dựa trên **Segmentation Mask**.
  4. Tích hợp **Motion Memory** + **Temporal Propagation** (chịu được che khuất/biến dạng).
  5. Hiển thị vị trí, vùng phân đoạn, **quỹ đạo di chuyển** theo thời gian thực.
  6. Đánh giá hiệu năng: **FPS, độ trễ, chất lượng phân đoạn, độ ổn định bám bắt**.
- **Định hướng kỹ thuật:** Tham khảo các mô hình VOS như **SAM 2**, **SAMURAI**, **XMem**; stack chính **Python + OpenCV**.
- Tài liệu đề tài gốc: `docs/DoAnCameraAI.docx`.

---

## 2. ⚠️ QUY TẮC BẮT BUỘC: Ghi log công việc hằng ngày

**Sau MỖI phiên làm việc có thay đổi code/tài liệu, agent PHẢI tạo file log** để sinh viên dùng viết báo cáo sau này.

### 2.1. Vị trí & đặt tên

- Thư mục: `docs/task/`
- Đặt tên file: `DD-MM-YYYY-ten-cong-viec.md`
  - Ví dụ: `16-10-2026-setup-repo-va-video-capture.md`
  - Tên công việc: tiếng Việt không dấu hoặc tiếng Anh, nối bằng gạch ngang, viết thường.
- Nếu trong ngày có nhiều việc riêng biệt → có thể tạo nhiều file, hoặc 1 file tổng hợp cho cả ngày (ưu tiên 1 file/ngày nếu các việc liên quan nhau).

### 2.2. Template bắt buộc

Mỗi file log PHẢI theo cấu trúc sau:

```markdown
# Ngày DD-MM-YYYY — <Tên công việc>

## 🎯 Mục tiêu
- <Việc định làm hôm nay>

## 📥 Input
- <Đầu vào: tài liệu tham khảo, repo, model, dữ liệu, yêu cầu từ người dùng...>

## 🔨 Công việc đã thực hiện
1. <Mô tả chi tiết từng việc: file nào được tạo/sửa, lệnh chạy, cấu hình...>
2. ...

## 📤 Output / Kết quả
- <Kết quả đạt được: chức năng chạy được, số liệu đo (FPS, accuracy...), screenshot/log nếu có>
- Liệt kê file thay đổi:
  - `path/to/file1.py` — mô tả ngắn
  - `path/to/file2.md` — mô tả ngắn

## 🐞 Vấn đề gặp phải & cách xử lý
- <Lỗi/bug/khó khăn + cách giải quyết (hoặc chưa giải quyết)>

## 📌 Việc cần làm tiếp (Next steps)
- [ ] <Việc tiếp theo>

## 📚 Tài liệu tham khảo
- <Link paper, repo, docs đã dùng trong ngày>
```

### 2.3. Nguyên tắc ghi log

- Ghi **trung thực, đủ chi tiết** để sau này chép vào báo cáo (mục "Quá trình thực hiện").
- Luôn ghi rõ **Input → Xử lý → Output**.
- Có số liệu đo lường (FPS, latency, mIoU...) thì PHẢI ghi kèm.
- Không xóa/sửa log ngày cũ trừ khi được yêu cầu.

---

## 3. Cấu trúc thư mục repo

```
DOAN-NAB/
├── AGENTS.md              # File này — quy ước cho agent
├── README.md              # Giới thiệu dự án
├── docs/
│   ├── DoAnCameraAI.docx  # Đề cương đề tài gốc
│   └── task/              # 📁 Log công việc theo ngày (BẮT BUỘC)
├── src/                   # Source code chính của hệ thống
├── scripts/               # Script tiện ích (đánh giá, benchmark, convert...)
├── configs/               # File cấu hình (yaml/json)
├── models/                # Model weights / link tải model
├── data/                  # Dữ liệu test (video mẫu...) — KHÔNG commit file nặng
├── notebooks/             # Notebook thử nghiệm (nếu có)
├── requirements.txt       # Dependencies Python
└── .gitignore
```

> Khi tạo module mới, đặt đúng thư mục theo cấu trúc trên; nếu cần thư mục mới, cập nhật lại mục này trong `AGENTS.md`.

---

## 4. Quy ước code

- **Ngôn ngữ:** Python 3.10+.
- Comment/docstring: tiếng Việt hoặc tiếng Anh, nhất quán trong 1 file.
- Tên biến/hàm: `snake_case`; class: `PascalCase`.
- Mỗi module quan trọng cần docstring đầu file mô tả: chức năng, input, output.
- Không commit: model weights lớn, video dữ liệu nặng, file cache (`__pycache__`, `.venv`...). Dùng `.gitignore`.

---

## 5. Quy trình làm việc của agent trong mỗi phiên

1. Đọc yêu cầu từ người dùng + xem lại `docs/task/` gần nhất để nắm tiến độ.
2. Thực hiện code/thay đổi.
3. Chạy kiểm tra (nếu có thể) trước khi kết thúc.
4. **Tạo/cập nhật file log trong `docs/task/` theo mục 2** — đây là bước BẮT BUỘC cuối mỗi phiên.
5. Tóm tắt lại cho người dùng: đã làm gì, file nào thay đổi, bước tiếp theo.

---

## 6. Các repo/model tham khảo

> (Sẽ được cập nhật khi người dùng cung cấp repo cụ thể.)

- SAM 2: https://github.com/facebookresearch/sam2
- SAMURAI: https://github.com/yangchris11/samurai
- XMem: https://github.com/hkchengrex/XMem

---

## 7. Agent skills

### Issue tracker

Issues/spec/tickets lưu cục bộ dạng markdown trong `.scratch/<feature>/`. Xem `docs/agents/issue-tracker.md`.

### Triage labels

Dùng 5 nhãn mặc định: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Xem `docs/agents/triage-labels.md`.

### Domain docs

Single-context: một `GLOSSARY.md` + `docs/adr/` ở root. Xem `docs/agents/domain.md`.
