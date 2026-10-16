# Ngày 16-10-2026 — Setup Matt Pocock skills (issue tracker + domain docs)

## 🎯 Mục tiêu
- Cấu hình per-repo cho các skill matt-pocock (`/to-tickets`, `/wayfinder`, `/implement`, `/triage`, tool `tracker`) trước khi vào luồng xây dựng chính.
- Cho phép lưu spec/tickets cục bộ trong `.scratch/` (theo nhu cầu "lưu context" của người dùng).

## 📥 Input
- Skill `/setup-matt-pocock-skills` do người dùng kích hoạt.
- Trạng thái repo: remote GitHub `BinhNguyen1912/DoAn-NAB`, có `AGENTS.md`, chưa có `docs/agents/`, `.scratch/`, `GLOSSARY.md`, `docs/adr/`. Skill `triage` đã cài. Không có tín hiệu monorepo.

## 🔨 Công việc đã thực hiện
1. Khảo sát repo: `git remote -v`, kiểm tra `AGENTS.md`/`CLAUDE.md`/`GLOSSARY.md`/`docs/adr/`/`docs/agents/`/`.scratch/`, tín hiệu monorepo, cài đặt skill `triage`.
2. Thống nhất với người dùng: **Issue tracker = Local markdown** (`.scratch/<feature>/`), **Triage labels = mặc định** (5 role), **Domain docs = single-context**.
3. Tạo `docs/agents/issue-tracker.md` — quy ước local markdown tracker (spec, issues/NN-slug, wayfinder map/child, blocking, frontier, claim/resolve).
4. Tạo `docs/agents/triage-labels.md` — map 5 role `needs-triage`/`needs-info`/`ready-for-agent`/`ready-for-human`/`wontfix`.
5. Tạo `docs/agents/domain.md` — quy tắc tiêu thụ `GLOSSARY.md` + `docs/adr/`, layout single-context.
6. Thêm block `## 7. Agent skills` vào cuối `AGENTS.md` (3 sub-block: Issue tracker / Triage labels / Domain docs) trỏ tới 3 file trên.

## 📤 Output / Kết quả
- Các skill `/to-tickets`, `/wayfinder`, `/implement`, `/triage` và tool `tracker` giờ đọc/ghi theo cấu hình local markdown.
- File thay đổi:
  - `docs/agents/issue-tracker.md` — cấu hình tracker local markdown (mới)
  - `docs/agents/triage-labels.md` — map nhãn triage (mới)
  - `docs/agents/domain.md` — quy tắc domain docs single-context (mới)
  - `AGENTS.md` — thêm mục `## 7. Agent skills` (sửa)

## 🐞 Vấn đề gặp phải & cách xử lý
- Môi trường WSL không thấy `nvidia-smi`/`python` → không tự dò được GPU; phần cứng vẫn là câu hỏi dành cho người dùng (Round 1 của `/grill-with-docs`).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Tiếp tục `/grill-with-docs` Round 1 (Q1–Q6: phần cứng, FPS mục tiêu, nguồn đầu vào, UI, số object, ngôn ngữ).
- [ ] Sau khi grill xong → `/to-spec` → `/to-tickets` (lúc này tickets sẽ ghi vào `.scratch/<feature>/`).

## 📚 Tài liệu tham khảo
- Skill `/setup-matt-pocock-skills` (vendor mattpocock-skills).