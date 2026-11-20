# 20-11-2026 — `./run gt`: chọn frame GIỮA KHE VOS + lọc theo khung (bỏ dãy `--frames` dài)

## 1. Mục tiêu

Sinh được bộ GT người tô **ở giữa khe VOS** (`frame ≡ vos_every-1` ⇒ **chắc chắn không phải frame VOS**,
ô hiển thị là nội suy từ mốc VOS gần nhất cách nó `ve-1` frame — KHÔNG phải định lý "xa mốc nhất") — đây là phép đo duy nhất trả lời được `max_mad` của `LkBoxTracker` — mà **không**
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
   được thử ở đúng chỗ ô hiển thị **chắc chắn không phải ô của frame VOS**. (ĐÍNH CHÍNH sau review:
   đừng viết "khe 2 bước LK thay vì 1" — LK chỉ được gọi **một lần/frame** và reset mốc về frame VOS
   (`src/light_tracker.py`), đại lượng thay đổi là **khoảng cách frame** tới mốc. Và frame `≡ 0 mod ve`
   **cũng** đang phát ô nội suy, nhưng từ lần VOS **trước** — cách `ve` frame — vì VOS về muộn hơn nhịp
   phát ⇒ câu đúng là "≡ ve-1 **chắc chắn** không phải frame VOS", không phải "xa mốc nhất".)
3. Nếu vẫn "không phân biệt được": làm `LkBoxTracker` nội suy cả **tỉ lệ** (vật ra gần/xa) rồi A/B lại.

## 7. Tài liệu tham khảo

- `docs/task/19-11-2026-cong-cu-gan-gt-nhanh.md` (công cụ GT), `docs/task/19-11-2026-ab-live-lk-max-mad.md`
- `docs/task/20-11-2026-o-hien-thi-vs-gt-chot-max-mad.md` (4 lần A/B ⇒ giữ `DEFAULT_MAX_MAD 1,5`)
- AGENTS.md §6: "Mất dấu phải tách khỏi vật đã rời khung — ô chọn và khung frame phải kiểm bằng ẢNH"

## 8. Review độc lập (AGENTS §9.1) — reviewer, 20-11

**Kết quả: P0 = 0 · P1 = 1 · P2 = 6 · P3 = 5.** Lõi thuật toán (`frames_giua_khe`, `parse_khung`) đúng
— reviewer tự tính tay ve = 2,3,4,5,7,11 và xác nhận bước luôn là bội của `vos_every` ⇒ không còn ca
lệch dàn. Mốc VOS thật đã đối chiếu: `live_tracking.py` VOS ở `_frame_index % every == 0` ⇒ công thức
chọn đúng phía (không bị ngược).

### Đã sửa trong nhánh (hết P1 + 6 P2)

| Mức | Nội dung | Vá |
|---|---|---|
| **P1** | Vẫn còn cửa **âm thầm rơi về 12 frame trải đều**: `--vos-every 1` (đúng cấu hình phiên mIoU của repo), `--giua-khe 0/-5`, clip ngắn ⇒ `frames_giua_khe` trả `[]` ⇒ code lặng lẽ dùng bộ mặc định, **lẫn cả frame có VOS** ⇒ bộ mẫu vô nghĩa cho `max_mad` mà không ai biết | `SystemExit` với thông điệp nêu nguyên nhân (validate `--vos-every ≥ 2`, `--giua-khe ≥ 1`, sinh 0 frame). 2 test gọi thẳng `main()` |
| P2 | Test bất biến có thể **xanh rỗng** (hàm trả `[]` ⇒ `for` không chạy) | thêm `assert ra`, mở rộng ve = 7/11/12/20 (khoá luôn hành vi làm tròn 28/33/24/40) |
| P2 | Không test `main()` ⇒ lỗi "lọc trước khi sinh danh sách" không có test chống tái phát | tách hàm thuần `loc_theo_khung()` + 3 test (gồm ca giao rỗng **và** ca chuỗi gõ sai) |
| P2 | **Dead code**: `if not frames` thứ hai nằm sau `raise SystemExit` cùng điều kiện ⇒ câu "--frames rỗng…" **không bao giờ in** | xoá; `loc_theo_khung` lo |
| P2 | `parse_khung` ném `ValueError` thô ⇒ người gõ sai nhận **traceback Python** | bắt trong `loc_theo_khung` → `[LOI] --khung '…': …` + test 4 chuỗi sai |
| P2 | Diễn giải cơ chế LK **sai** trong docstring + log ("LK chỉ 1 bước") | viết lại (xem mục Next steps ở trên); sửa cả log |
| P2 | `index.json` thiếu provenance **cách chọn frame** ⇒ artifact không tự chứng minh được "7 frame là giữa khe" | thêm khoá `chon_frame` (`{"giua_khe":N,"vos_every":ve,"khung":…}` / `{"frames":[…]}` / `{"mac_dinh":…}`) |
| P2 | `docs/thuoc-do-bam-dung.md` vẫn dạy **đúng lệnh đã hỏng** | thay bằng `--giua-khe --khung`, thêm bảng 3 cờ + cảnh báo `--dump-mask-frames` bị chặn khi `vos_every > 1` |
| P3 | help "cách nhau 30 frame" sai khi 30 không là bội của ve | ghi rõ "~30 nhưng luôn là bội của vos_every (ve=4 ⇒ 32)" |
| P3 | `--frames` + `--giua-khe` im lặng | in `[canh-bao] bỏ qua --giua-khe/--vos-every vì đã có --frames` |
| P3 | `--khung` bỏ frame im lặng | in `[khung] bỏ N frame ngoài …: [...]` |
| P3 | cùng dãy mốc cứng ở 2 test | giữ **một** golden test, test kia suy ra từ nó |

### Kiểm bằng ẢNH (reviewer nêu là residual risk — đã làm)

Sinh gợi ý cho đúng 7 mốc rồi xem sheet ảnh: chai **có mặt ở cả 7** frame
(`goiy` 3,17 / 3,23 / 4,51 / 3,83 / 5,17 / 14,53 / 2,93 % diện tích; f212 là cận cảnh). Không mốc nào
rơi vào chỗ chai đã cất ⇒ bộ GT `b1b` dùng được. Ảnh kiểm đã xoá cùng thư mục tạm, không commit.

### Còn nợ (không chặn)

- Reviewer lưu ý "≡ ve-1 = xa mốc nhất" **không phải định lý**: nếu `vos_ms` < 1 khoảng frame thì mốc
  có thể là chính frame VOS ⇒ không làm phép đo vô nghĩa nhưng đừng viết như định lý. Đã sửa câu chữ.
- `--giua-khe` ở clip vật ra/vào khung **bắt buộc** đi kèm `--khung`; chưa có gì tự phát hiện (phải
  biết khoảng frame từ `docs/demo-clip-va-o-chon.md`).

### Sau khi vá

`./run lint` xanh · `./run test` **1548 passed** (mục 8 đo sau vá vòng 1: 1540; sau vá vòng 2: 1548) · 6 test cũ của bộ GT vẫn xanh.

## 9. Review độc lập vòng 2 (sau khi vá) — reviewer, 20-11

**P0 = 0 · P1 = 1 · P2 = 3 · P3 = 8.** Reviewer xác nhận P1 vòng 1 **đã bịt kín** (liệt kê 8 đường vào
`frames_trai_deu`, không đường nào còn âm thầm đổi bộ frame), thứ tự `--khung` đúng (một call site, sau
cả 3 nguồn), `chon_frame` không lọt `None`, khoá mới không làm `score_miou.kiem_index` /
`gt_check_silhouette` / `e2e_gt_painter.js` từ chối.

**P1 mới — do chính phép vá vòng 1 sinh ra:** `chon_frame` nằm trong tuple "khoá người-viết-đầu-thắng"
⇒ chạy lần 2 cùng `--ten` (workflow tài liệu khuyến khích: danh sách frame được **hợp**) thì index giữ
`{"mac_dinh": "12 frame trải đều"}` trong khi frames thật là 7 mốc giữa khe ⇒ **provenance nói sai**,
đúng thứ khoá này sinh ra để chống. Vá: bỏ `chon_frame` khỏi tuple ghi đè (chỉ `None` mới rơi về cũ) +
2 test.

| Mức | Nội dung | Vá |
|---|---|---|
| **P1** | trên | bỏ khỏi tuple + 2 test (`chon_frame` mới thắng / `None` giữ cũ) |
| P2 | `--frames` + `--khung`: index khai danh sách **trước** lọc | ghi lại sau lọc + test |
| P2 | docstring `frames_giua_khe` + docstring test vẫn nói "xa mốc VOS nhất"/"ô là của MODEL" (ngược comment mới) | viết lại cả 2 |
| P2 | `--frames 0,5O,100` (chữ O) ⇒ **ValueError thô + traceback** — đúng lớp lỗi vừa vá cho `--khung`, và đây là cờ gõ tay nhiều nhất | `[LOI] --frames …` + test |
| P3 | `ten_clip` là **tham số chết** | dùng trong `[LOI] --khung … (clip …)` |
| P3 | `mac_dinh` ghi cứng "12 frame" cả khi clip ngắn hơn 12 | `f"{len(frames)} frame trải đều clip"` |
| P3 | validate `--vos-every` chạy cả khi `--frames` đã có ⇒ hard-error trong khi cờ đó bị bỏ qua | chuyển vào nhánh `--giua-khe` + test |
| P3 | thông điệp "clip có dài hơn N frame không?" đổ lỗi sai khi clip **không mở được** | nêu clip + số frame đọc được |
| P3 | `set(ra)` dựng mỗi vòng (O(n²)) | tính một lần |
| P3 | không test nào đi qua `main()` tới `_viet_index`; không test `--giua-khe -5` | 3 test mới (`_chay_main` monkeypatch `score_miou.cat_frames` — vá ở module NGUỒN vì `main` import bên trong) + parametrize `0/-5` |

Ghi chú phương pháp: reviewer vòng này **không có shell** (chỉ tool đọc) nên không chạy lại được
`git show`/`pytest`; ranh giới diff được kiểm bằng đọc mã + `.git/logs`. Vì thế sau khi vá phải tự chạy
`./run lint` + `./run test` (đã chạy: xem mục 4).
