# Quy trình Git của repo DoAn-NAB — 1 nhánh/nhiệm vụ + PR, hạn chế conflict

> Tài liệu này là quy ước làm việc với AI agent (và giữa các thành viên). `AGENTS.md` mục 9 trỏ tới đây.
> Mục tiêu: `main` **luôn xanh** (lint + test), mỗi thay đổi vào `main` qua **một PR** để người phụ trách review và merge.

## 1. Nhánh

| Loại | Tên nhánh | Ghi chú |
|---|---|---|
| Tính năng | `feat/web-live-stream` | sống < 1 ngày, xong thì xoá |
| Sửa lỗi | `fix/bbox-lech-canvas` | |
| Tài liệu | `docs/quy-trinh-git` | |
| Hạ tầng / dọn dẹp | `chore/cap-nhat-run` | |
| Nháp dài hạn (tuỳ chọn) | `demoip` | **chỉ một** nhánh nháp; xem mục 5 |

- **Không commit trực tiếp lên `main`** (trừ khi sửa 1 dòng khẩn cấp và ghi rõ lý do trong commit).
- **Không tạo tag mỗi lần làm xong.** Tag chỉ dùng cho mốc "demo chạy được", tối đa **2 tag sống**
  (một bản CLI, một bản web). Tag cũ hơn bị bản mới thay thế thì xoá.
- Xoá nhánh sau khi PR được merge (cả local và remote).

## 2. Vòng đời một thay đổi

```bash
git fetch origin
git switch -c feat/ten-ngan-gon origin/main     # luôn rẽ từ main MỚI NHẤT
# ... code ...
./run lint && ./run test                          # + ./run webtest / ./run e2e nếu đụng web/
git add -A && git commit                          # 1 commit = 1 mục đích, message nêu SỐ ĐO
git fetch origin && git rebase origin/main        # giải conflict ngay tại đây, không để lâu
git push -u origin HEAD
# → mở PR (xem mục 4)
```

Sau khi PR được merge: `git switch main && git pull --ff-only && git branch -d <nhánh>`.

## 3. Hạn chế conflict — quy tắc cụ thể

Conflict gần như luôn đến từ **file dùng chung** hoặc **file bị reformat**. Vì vậy:

**File "nóng" — chỉ một PR được đụng tại một thời điểm, và phải merge ngay khi xanh:**

- `run` (lệnh tắt — ai cũng thêm lệnh mới)
- `AGENTS.md`, `README.md` (nhiều mục, dễ chèn trùng chỗ)
- `requirements.txt`
- `tests/conftest.py` (fixture dùng chung)
- `web/package-lock.json` (npm sinh ra; sửa tay = chắc chắn conflict)

**Cách viết để giảm conflict:**

1. **Append thay vì chèn giữa**: thêm mục mới vào **cuối** danh sách/section, không chèn vào giữa
   mục đang có. Ví dụ thêm lệnh `./run xyz` thì đặt cuối nhóm lệnh, thêm test class thì thêm ở cuối file.
2. **File mới thay vì sửa file lớn**: logic mới → module mới (`src/api/adapters/foo.py`) chứ không nhồi
   vào `main.py`/`service.py`.
3. **Không reformat file không liên quan** (đổi dấu nháy, sắp lại import, đổi indent) — đó là nguồn
   conflict lớn nhất và làm review không đọc được.
4. **PR nhỏ**: mục tiêu < ~400 dòng diff. PR lớn thì tách theo tầng (backend / frontend / docs).
5. `package-lock.json`: chỉ cập nhật khi thật sự thêm/bớt dependency, và là PR riêng nếu được.
6. Nếu hai việc buộc phải sửa cùng file nóng → làm **tuần tự** (PR này merge xong mới mở PR kia).

## 4. Nội dung PR (mẫu)

```markdown
## Mục đích
<một câu: thay đổi gì và vì sao>

## Kiểm chứng
- ./run lint      → All checks passed
- ./run test      → <N> passed, <M> deselected (<giây>)
- (nếu đụng web) ./run webtest → <N> passed · ./run e2e → PASS
- (nếu có số đo) bảng FPS/độ trễ TRƯỚC và SAU

## Ảnh hưởng
- File "nóng" đã chạm: <run | AGENTS.md | requirements.txt | conftest.py | package-lock.json | không>
- Có đổi hợp đồng API không? (nếu có: endpoint/khoá nào, frontend đã cập nhật chưa)
- Có đổi số đo trong báo cáo không? (dẫn đường dẫn file log trong docs/task/)

## Việc còn lại
- [ ] <nếu có>
```

**Không bao giờ** đưa số liệu không đo vào PR (ADR-0002: báo cáo trung thực).

## 5. Nhánh nháp `demoip` (nếu cần thử nghiệm dài hạn)

- Chỉ **một** nhánh nháp tồn tại. Mỗi lần bắt đầu làm việc trên nháp: `git fetch && git rebase origin/main`.
- **Không merge `main` ngược vào nhánh nháp** (sinh merge commit và conflict lặp lại). Luôn rebase.
- Nhánh nháp **không** được merge vào `main` nguyên khối; phần nào muốn vào `main` thì tách sang PR nhỏ.

## 6. Khi CI đỏ

1. `./run lint` → sửa hết (chạy `--fix` chỉ khi chắc chắn không đổi hành vi).
2. `./run test` → đọc test nào đỏ; **không** sửa test để test xanh nếu hành vi thật đang sai.
3. Chỉ mở PR khi cả hai xanh; PR mở sớm để nhận góp ý thì ghi tiêu đề `[WIP]`.
