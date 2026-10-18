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

Mỗi file log PHẢI theo đúng cấu trúc trong **`docs/task/_template.md`** (đọc file đó rồi copy làm khuôn — 7 mục: Mục tiêu, Input, Công việc đã thực hiện, Output/Kết quả, Vấn đề & cách xử lý, Next steps, Tài liệu tham khảo).

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
├── CODING_STANDARDS.md    # Chuẩn code chi tiết (đọc khi review)
├── README.md              # Giới thiệu dự án + cài đặt từ clone mới
├── docs/
│   ├── DoAnCameraAI.docx  # Đề cương đề tài gốc
│   ├── adr/               # Quyết định kiến trúc (0001, 0002)
│   ├── agents/            # Cấu hình skill (issue-tracker, triage-labels, domain)
│   ├── samurai-setup.md   # Cơ chế hydra/checkpoint upstream (navigation)
│   └── task/              # 📁 Log công việc theo ngày (BẮT BUỘC) + _template.md
├── src/                   # Source code chính của hệ thống
├── tools/                 # CLI chạy (run_live.py), benchmark, demo
├── tests/                 # pytest (fixture synthetic, không commit dữ liệu nặng)
├── configs/               # Cấu hình (default.yaml — checkpoint/nguồn/ghi/metrics)
├── data/                  # Dữ liệu test (video mẫu...) — KHÔNG commit file nặng
├── models/                # Model weights / link tải model
├── requirements.txt       # Dependencies Python
├── ruff.toml              # Rule lint đã ghim tại repo
├── pytest.ini             # Marker slow + --timeout=120
└── .github/workflows/     # CI: ruff + pytest làn nhanh
```

> Khi tạo module mới, đặt đúng thư mục theo cấu trúc trên; nếu cần thư mục mới, cập nhật lại mục này trong `AGENTS.md`.

---

## 4. Quy ước code

- **Ngôn ngữ:** Python 3.10+.
- Chuẩn chi tiết (ngôn ngữ comment, UI phải test headless được, quy tắc test): **`CODING_STANDARDS.md`** — đọc khi review và khi thêm module mới.
- Kiểm tra cơ học bằng `ruff` (`ruff.toml`) — import/biến thừa, tên chưa định nghĩa — không tự sửa tay khi `ruff check .` báo được.
- Không commit model weights/video nặng — `.gitignore` đã chặn.

---

## 5. Quy trình làm việc của agent trong mỗi phiên

1. Đọc yêu cầu từ người dùng + xem lại `docs/task/` gần nhất để nắm tiến độ.
2. Thực hiện code/thay đổi.
3. Chạy kiểm tra trước khi kết thúc:
   - **Làn nhanh** (UI/logic/config — ~10s): `python -m pytest -m "not slow"`.
   - **Lint:** `ruff check .` (phải xanh — CI chạy đúng lệnh này).
   - **Full suite** (~100s, cần checkpoint SAM 2): chỉ khi đụng `tracker_engine`/model/CLI model hoặc trước commit cuối.
4. **Tạo/cập nhật file log trong `docs/task/` theo mục 2** (template: `docs/task/_template.md`) — bước BẮT BUỘC cuối mỗi phiên.
5. Tóm tắt lại cho người dùng: đã làm gì, file nào thay đổi, bước tiếp theo.

---

## 6. Các repo/model tham khảo

- SAM 2: https://github.com/facebookresearch/sam2
- SAMURAI: https://github.com/yangchris11/samurai
- XMem: https://github.com/hkchengrex/XMem

Cài đặt/cơ chế hydra `model_cfg` của SAMURAI trong repo này: `docs/samurai-setup.md` (cài từ clone mới: `README.md` mục 1).

---

## 7. Agent skills

### Issue tracker

Issues/spec/tickets lưu cục bộ dạng markdown trong `.scratch/<feature>/`. Xem `docs/agents/issue-tracker.md`.

### Triage labels

Dùng 5 nhãn mặc định: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Xem `docs/agents/triage-labels.md`.

### Domain docs

Single-context: một `GLOSSARY.md` + `docs/adr/` ở root. Xem `docs/agents/domain.md`.
