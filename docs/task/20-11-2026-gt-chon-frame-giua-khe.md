# 20-11-2026 — `./run gt`: chọn frame GIỮA KHE VOS + lọc theo khung (bỏ dãy `--frames` dài)

## 1. Mục tiêu

Sinh được bộ GT người tô **ở giữa khe VOS** (frame xa mốc VOS nhất ⇒ ô hiển thị do **hoàn toàn** LK
nội suy quyết định) — đây là phép đo duy nhất trả lời được `max_mad` của `LkBoxTracker` — mà **không**
phải gõ dãy frame dài trên terminal.

## 2. Input

- `scripts/gt_gan_nhanh.py` (đã có từ 19-11): cắt frame → mở trình tô trên browser → ghi `index.json`.
- Người dùng chạy 3 lần đều hỏng **cùng một chỗ**:
  ```
  ./run gt ... --frames 2,32,62,92,182,212,242
  gt_gan_nhanh.py: error: argument --frames: expected one argument
  2,32,62,92,182,212,242: command not found
  ```
- Nguyên nhân: terminal ~105 cột (kể cả prompt ~28) → dán dòng dài bị **chèn xuống dòng ngay sau
  `--frames`** ⇒ dãy số thành lệnh riêng. Không phải lỗi shell của người dùng, cũng không phải lỗi
  đường ống WSL.

## 3. Công việc đã thực hiện

| Việc | File |
|---|---|
| `--giua-khe [N]` — sinh N frame (mặc định 12) cách nhau ~30 frame, mọi frame ≡ `(vos_every-1) mod vos_every` | `scripts/gt_gan_nhanh.py` |
| `--vos-every` (mặc định 3) — chu kỳ VOS của phiên sẽ chấm | nt |
| `--khung a:b[,c:d]` — chỉ lấy frame trong khung (gồm cả hai đầu) | nt |
| Test: dàn mốc đúng dạng, không bao giờ rơi vào frame có VOS, biên vô hướng, `parse_khung`, và ca binh1 ra đúng 7 mốc | `tests/test_gt_gan_nhanh.py` |

### Ba lỗi tự bắt trong lúc làm (đều do test/lần chạy thử, không phải do review)

1. **Bước nhảy không phải bội của `vos_every`.** `vos_every=4`, bước 30 ⇒ mốc thứ hai là **33**
   (`33 % 4 = 1`) — rơi đúng vào frame **CÓ VOS** ⇒ phép đo mất ý nghĩa. Test
   `test_frames_giua_khe_khong_bao_gio_dung_vao_frame_co_vos` bắt được. Vá: bước = `ve × round(30/ve)`
   ⇒ ve=2/3/5/6 → 30, ve=4 → 32.
2. **Lọc khung đặt SAI THỨ TỰ** (trước khi sinh danh sách) ⇒ danh sách còn rỗng ⇒ `--khung` **luôn**
   báo "lọc hết frame". Lần chạy thử `--chi-sinh` bắt được. Vá: sinh danh sách → **rồi** lọc; lọc xong
   rỗng thì báo lỗi, **không** âm thầm rơi về bộ frame mặc định (rơi ngầm = chấm vào chỗ vật đã rời
   khung).
3. **Chọn mốc mà không lọc khung là vô ích.** Lần chạy thử in `gợi ý f122: 0,1 % diện tích` /
   `f152: 0,3 %` ⇒ chai **đã rời khung** (binh1: chai chỉ có trong `0:110` ∪ `165:262`). GT ở đó là
   mask rỗng. Vì thế `--khung` không phải "tiện ích" mà là **bắt buộc** với clip có vật ra khỏi khung.

## 4. Output / Kết quả

```
$ ./run gt --clip data/binh1.mp4 --ten b1b --nguoi-gan Binh --giua-khe --khung 0:110,165:262 --chi-sinh
  gợi ý f2: 3.2 % diện tích
  gợi ý f32: 3.2 %
  gợi ý f62: 4.5 %
  gợi ý f92: 3.8 %
  gợi ý f182: 5.2 %
  gợi ý f212: 14.5 %
  gợi ý f242: 2.9 %
index.json → docs/gt/_tmp2/index.json  (frame_hw = 1280×720)
```

- Đúng **7 mốc** `2,32,62,92,182,212,242` (như bộ đã định), mọi frame **≡ 2 mod 3** (giữa khe, không
  có VOS), và **mọi** frame đều có chai thật (2,9–14,5 % diện tích) — khác hẳn bộ sinh không lọc
  khung (f122/f152 ≈ 0,1–0,3 %).
- `./run lint` xanh · `./run test` **1535 passed** (thêm 6 test).
- Thư mục thử `docs/gt/_tmp*` đã xoá, không commit.

## 5. Vấn đề & cách xử lý

- Terminal dán dòng dài bị wrap ⇒ **thiết kế lại lệnh cho ngắn** thay vì bảo người dùng "gõ cẩn thận".
  Lệnh mới dài ~90 ký tự, dưới ngưỡng wrap.
- Không đổi ngữ nghĩa `--frames` (vẫn dùng được, ưu tiên cao hơn `--giua-khe`).

## 6. Next steps

1. Người dùng tô 7 frame → `data/gt/b1b` (bộ **giữa khe**).
2. Chấm ô hiển thị vs GT bằng `scripts/ab_o_hien_thi_vs_gt.py` với bộ `b1b` ⇒ lần đầu tiên `max_mad`
   được thử ở đúng chỗ nó có tác dụng (khe 2 bước LK thay vì 1).
3. Nếu vẫn "không phân biệt được": làm `LkBoxTracker` nội suy cả **tỉ lệ** (vật ra gần/xa) rồi A/B lại.

## 7. Tài liệu tham khảo

- `docs/task/19-11-2026-cong-cu-gan-gt-nhanh.md` (công cụ GT), `docs/task/19-11-2026-ab-live-lk-max-mad.md`
- `docs/task/20-11-2026-o-hien-thi-vs-gt-chot-max-mad.md` (4 lần A/B ⇒ giữ `DEFAULT_MAX_MAD 1,5`)
- AGENTS.md §6: "Mất dấu phải tách khỏi vật đã rời khung — ô chọn và khung frame phải kiểm bằng ẢNH"
