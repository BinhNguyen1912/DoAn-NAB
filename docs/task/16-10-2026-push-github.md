# Ngày 16-10-2026 — .gitignore + commit đầu tiên + push lên GitHub

## 🎯 Mục tiêu
- Đưa repo lên GitHub (`BinhNguyen1912/DoAn-NAB`) — backup, thầy xem được, chuẩn cho Colab clone về chạy.

## 📥 Input
- Repo chưa có commit nào; `samurai/` clone upstream 1.9GB (1.5GB checkpoints), `models/bench/` 196MB, `data/` 35MB.
- Git identity chỉ cấu hình trên Windows (`BinhNguyen1912` / anhbinhnguyen19122004@gmail.com).

## 🔨 Công việc đã thực hiện
1. Viết `.gitignore`: loại `samurai/` (upstream), `models/`, `*.pt/*.pth`, `data/*` (giữ lại `*.txt`), `.pi/`, cache Python/IDE. Kết quả: chỉ 23 file (code + tài liệu) được commit.
2. Đặt identity git local cho repo trong WSL (giống Windows).
3. Commit đầu tiên `9acb1b2` — 23 files, 1731 dòng.
4. Xử lý lỗi push (2 tình huống):
   - WSL không có credential GitHub → cấu hình `credential.helper` trỏ tới Git Credential Manager của Git for Windows (`D:\Program Files\Git\`).
   - Credential đang lưu thuộc tài khoản **`kaintoxic`** (không có quyền push) → erase credential, chạy lại push, người dùng đăng nhập lại đúng tài khoản `BinhNguyen1912`.
5. Push thành công: `main -> main`, branch theo dõi `origin/main`.

## 📤 Output / Kết quả
- Repo trên GitHub: https://github.com/BinhNguyen1912/DoAn-NAB (commit `9acb1b2`).
- File thay đổi:
  - `.gitignore` — quy tắc loại file nặng (mới)
  - `docs/task/16-10-2026-push-github.md` — log này (mới)

## 🐞 Vấn đề gặp phải & cách xử lý
- Push từ WSL treo (chờ credential) → dùng GCM của Git for Windows qua `/mnt/d/...`.
- 403 "denied to kaintoxic" — tài khoản GitHub đang lưu khác tài khoản owner → erase credential + đăng nhập lại.
- Dialog đăng nhập bị hủy lần đầu → chạy lại push, hoàn tất đăng nhập lần 2.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] `/to-spec` — viết spec triển khai chi tiết theo ADR-0002.
- [ ] `/to-tickets` — tách tickets vào `.scratch/`.

## 📚 Tài liệu tham khảo
- Git Credential Manager (GitHub CLI docs), quy ước AGENTS.md mục 4 (không commit file nặng).