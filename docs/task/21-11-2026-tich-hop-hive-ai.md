# Ngày 21-11-2026 — Tích hợp Hive AI (client mỏng, log-only)

## 🎯 Mục tiêu
- Theo yêu cầu: "setup Hive AI (thehive.ai) vào repo". Dựng **client mỏng** chuẩn, không hardcode
  loại task, để gọi sau cho moderation / AI-generated content detection.

## 📥 Input
- Base URL đã kiểm tra chạy thật: `https://api.thehive.ai/api/v2/task/sync` (+ `/async`).
- Auth: header `authorization: token <HIVE_API_KEY>`; key lấy ở portal.thehive.ai.
- Repo chưa có integration Hive nào (grep sạch), chưa có `.env`/`.env.example`.

## 🔨 Công việc đã thực hiện
1. `src/hive_moderation.py` (mới): `submit_sync(payload, api_key=..., url=...)` → POST JSON, trả dict
   đã parse; `HiveError` rõ ràng khi (a) thiếu key, (b) HTTP lỗi (kèm body), (c) JSON không hợp lệ.
   Key đọc từ biến môi trường `HIVE_API_KEY`, nếu chưa có thì nạp `.env` ở root (chỉ `setdefault` ⇒
   biến môi trường thật luôn thắng). **KHÔNG hardcode task type** — caller truyền `tasks` đúng schema.
2. `.env.example` (placeholder `HIVE_API_KEY=`) + `.gitignore` thêm `.env`/`.env.*` (giữ `.env.example`).
3. `tests/test_hive_moderation.py`: 6 test, mock `urllib`, KHÔNG gọi API thật, KHÔNG cần key:
   thiếu key ⇒ báo lỗi · nạp `.env` · env thắng `.env` · header `token` + body + URL đúng ·
   HTTP 400 kèm nội dung · mạng chết.

## 📤 Output / Kết quả
- `./run lint` xanh · `python -m pytest tests/test_hive_moderation.py` **6 passed**.
- File: `src/hive_moderation.py`, `tests/test_hive_moderation.py`, `.env.example`, `.gitignore`.
- ⚠️ **Key thật KHÔNG commit** (nằm trong `.env`, đã `.gitignore`). Key đã bị dán vào chat ⇒ coi như
  lộ; nếu là key production thì xoay ở portal sau khi test.

## 🐞 Vấn đề & cách xử lý
- Chưa có schema chính thức trong tay (docs.thehive.ai bị rate-limit lúc truy cập) ⇒ **không** hardcode
  task type (moderation/visual_moderation/ai_generated_image_detection) vào client; để caller truyền.
  Chưa verify key bằng call thật vì cùng lý do (cần schema đúng + không muốn tốn quota mò).

## 📌 Next steps
- [ ] Chốt **Hive dùng để làm gì**: moderation media (ảnh/video) hay chấm AI-generated content? → chọn
  task type + nơi nối (CLI / API route / script riêng), rồi verify bằng 1 call thật.

## 📚 Tài liệu tham khảo
- https://docs.thehive.ai/reference/authentication
