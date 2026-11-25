# Cách gán nhãn "hệ bắt ĐÚNG hay SAI" (và cách dùng số sau khi gán)

> Dành cho người ngồi gán nhãn. Mục đích: có **bằng chứng thứ hai** cho các tuyên bố kiểu *"hệ bám đúng
> 7/7 ca"* — AGENTS §6 nói nhãn do **1 người** thì **không được trích** vào báo cáo.

## 0. Chạy trong 30 giây

```bash
cd /mnt/d/doan-nab
./run labelui --nguoi-gan Binh          # tên MẶC ĐỊNH (điền sẵn vào ô "Người gán")
```
⚠ **Ô "Người gán" để TRỐNG thì tool TỪ CHỐI ghi** (`400`) — nó không tự lấy tên mặc định của server.
Đây là chủ ý: nếu tự lấy, người thứ 2 xoá ô tên là nhãn của họ ghi dưới tên người thứ 1 và **ghi đè**
nhãn của người thứ 1 theo quy tắc "nhãn cuối thắng".

**Tên trong ô "Người gán" là tên được ghi vào file** — sửa ô đó là đổi người dán. Vì vậy **hai người
dùng chung một server cũng đúng**: mỗi người gõ tên mình, nhãn ghi đúng tên đó (`--nguoi-gan` chỉ là
giá trị điền sẵn). Nhãn của người khác **không** được gửi về trình duyệt (server chỉ trả nhãn của tên
đang hỏi + số lượng của người khác).
Rồi mở link script in ra: **http://127.0.0.1:8770** (mở bằng Chrome/Edge trên Windows; WSL chia cổng
với Windows nên `127.0.0.1` thường vào được — nếu không, xem mục 5).

Gán xong, xem tổng hợp:

```bash
python tools/label_ui.py --tong-hop data/demoip_1125-121456_metrics.csv
```

## 1. Bạn đang chấm cái gì

Video là **bản ghi màn hình của hệ** (đã có HUD vẽ ô + mask). Bạn chấm **từng bước suy luận**:
cái ô/mask mà hệ đang vẽ **có nằm trên đúng vật đã chọn** hay không.

| Phím | Nhãn | Khi nào bấm |
|---|---|---|
| `1` | **ĐÚNG** | Ô/mask nằm trên **đúng** vật người dùng đã chọn (kể cả khi mask hơi rộng/hụt) |
| `2` | **SAI** | Ô/mask nằm trên vùng **khác**: nền, tường, điều hoà, tay người, vật khác |
| `3` | **MẤT DẤU** | **Vật vẫn còn trong khung** nhưng hệ **không vẽ gì** (không ô, không mask) |
| `4` | **KHÔNG CÓ VẬT** | Vật **không có trong khung** (người dùng đã đưa ra ngoài) — đây **không** phải lỗi |
| `0` | **BỎ QUA** | Không kết luận được: quá mờ, che kín, không thấy rõ vật |

Điều quan trọng nhất: **`3` và `4` là hai chuyện khác nhau.** Phân biệt sai ở đây sẽ biến "hệ mất dấu"
thành "người dùng cất vật" và làm hỏng mọi kết luận về độ ổn định.

## 2. Cách đi nhanh (đừng xem cả video từ đầu)

- `→` / `←`: nhảy tới **bước suy luận** kế/trước. Đây là nhịp cần chấm (mỗi bước ~0,2–0,3 s), không
  phải từng frame video. Thanh bên phải hiện `#frame_vos` và `bước … ms`.
- `Space`: phát/dừng. `,` `.`: nhích ±0,2 s khi hình đã đổi mà thời điểm ước lượng còn lệch.
  (Thanh tua/play của chính video vẫn bấm được — canvas không nuốt chuột trừ khi đang vẽ ô.)
- Bấm phím số là **ghi ngay** (append vào `data/nhan/<phiên>.jsonl`), không cần bấm Lưu.
- Nếu header hiện nhãn đỏ **`CSV: frame_idx lặp`**: CSV của phiên này có `frame_idx` lặp/không tăng
  (nguồn file lặp quay về 0, hoặc artifact cũ như `data/gpu_metrics.csv`). Vẫn dán bình thường — mỗi
  nhãn lưu kèm `buoc` (số thứ tự dòng, **duy nhất**) chứ không chỉ `frame_vos`; nhưng **đừng** cộng gộp
  thống kê theo `frame_vos` trong trường hợp này.
- `s` (hoặc nút "Lưu & bước kế") = **ghi lại nhãn bạn vừa chọn** rồi sang bước kế. Chưa chọn nhãn nào
  thì nó **từ chối** và nhắc bạn bấm `1/2/3/4` trước — nó không tự đoán "ĐÚNG".
- `b` rồi kéo chuột: vẽ **ô đúng** (lưu kèm nhãn) — dùng khi bạn muốn cả toạ độ đúng, không chỉ phán
  quyết. Ô được **xoá khi sang bước khác**: nó thuộc về đúng bước bạn vẽ, không đi theo.
- `Enter` ở ô "Người gán" = nhả focus. Phím `1/2/3/4/0` **vẫn ăn** khi con trỏ đang ở trong ô tên
  (không lọt ký tự vào tên), nên bấm Enter chỉ để tiện gõ tiếp.

## 3. Bốn cái bẫy phải biết (đã từng làm sai số của repo)

1. **Thời điểm frame ↔ giây KHÔNG chia đều.** Tool tính `t≈` bằng cách **cộng dồn `latency_ms`** của
   từng bước. Trên phiên `demoip_1125-121456` (295 bước / 98,3 s), chia đều cho bước 141 ra **46,6 s**
   nhưng cộng dồn ra **34,9 s** — lệch **12 s**. Nếu bạn chấm theo "đoán giây" thì nhãn rơi vào **sai
   frame** và cả bộ nhãn thành vô dụng. Vì vậy tool ghi **cả** `t_video` (đồng hồ thật của video, cái
   bạn đang nhìn) **và** `t_uoc_luong` (cộng dồn latency) — khi lệch nhau nhiều, hãy tin `t_video`.
2. **Nếu thanh bên hiện "lệch X s so với bước này" thì ĐỪNG bấm nhãn ngay** — nghĩa là bạn đang đứng
   giữa hai bước suy luận (các bước dài ngắn khác nhau: bước #197 tới 1,77 s), nhãn sẽ gắn vào **bước
   gần nhất** chứ không phải bước bạn đang xem. Bấm `←`/`→` cho khớp rồi hãy bấm phím số. Tool cũng
   nhân `t≈` với **hệ số bù = thời lượng video / tổng latency** (phiên 121456: 1,034) vì cộng dồn
   `latency_ms` ra 94,76 s còn video dài 98,0 s — không bù thì cuối video lệch ~3 s.
3. **Frame `NGHI` (HUD hiện `NGHI ĐỔI ĐỐI TƯỢNG`) thì hệ CỐ TÌNH không vẽ mask** ⇒ tool hiện cảnh báo
   `hệ đang ẩn mask` (cột `nghi_doi_tuong` trong CSV). Nhãn cho các bước đó nên là `bo_qua`, trừ khi
   bạn đang chấm riêng câu hỏi *"lúc nghi thì vùng nghi có đúng vật không"*.
   **Đừng lẫn với `CHUA XAC MINH`**: trạng thái đó **VẪN VẼ** (ô nét đứt, không tô, không quỹ đạo), và
   **CSV metrics KHÔNG có cột cho nó** — chỉ có tổng ở `run_info.json` (`chua_xac_minh_n`), và UI hiện số
   đó ở **dòng mô tả phiên** (cạnh tên video) sau khi bạn chọn phiên. Nghĩa là: không có cách nào biết *theo từng bước* một bước là `chua_xac_minh`,
   nên khi chấm bước nào thấy HUD ghi "CHUA XAC MINH" thì tự ghi `bo_qua` và **ghi lại số bước** vào
   sổ tay — đừng để nó lẫn vào tỉ lệ "bắt đúng".
4. **Nhãn của người khác bị ẩn** (chỉ hiện số lượng). Đây là chủ ý: hai người phải dán **độc lập**,
   nếu không thì "2 người đồng ý" chỉ là một người dán hai lần. Muốn so: gán xong cả hai rồi chạy
   `--tong-hop` (in `dong_y_2_nguoi`).

## 4. Gán bao nhiêu là đủ

| Mục đích | Số nhãn cần |
|---|---|
| Kiểm một ca cụ thể (1 lần cổng báo) | 5 bước trước + lúc báo + 5 bước sau |
| Tỉ lệ "bắt đúng" của một phiên | mọi bước có vật trong khung (bỏ `4`) |
| Đối chứng 2 người cho báo cáo | **cùng một tập** bước, 2 người dán độc lập ⇒ `--tong-hop` cho số đồng ý |

Bước có `latency_ms = 0` (frame bị đóng băng ở phiên bật re-ID) có `t≈` **trùng** bước trước ⇒ tool
không bao giờ nhảy tới đúng bước đó; phiên demo (`--no-reid`) không có ca này, nhưng nếu chấm phiên bật
re-ID thì dùng `,`/`.` để chỉnh tay.

Ghi nhãn **từng bước VOS**, không phải từng frame video — video 30 fps có ~9 frame cho mỗi bước.
Bộ đếm trên UI đếm **bước đã dán** (một bước dán lại chỉ tính 1), còn `--tong-hop` báo cả
`so_nhan_trung` để bạn thấy mình đã dán lại bao nhiêu lần.

## 5. Không mở được `127.0.0.1` từ trình duyệt Windows

WSL2 thường chia cổng với Windows, nhưng nếu không:

```bash
# trong WSL: lấy IP của WSL
hostname -I | awk '{print $1}'          # ví dụ 172.19.180.5
./run labelui --nguoi-gan Binh --host 0.0.0.0
```
Rồi mở `http://<IP-vừa-in>:8770`. Nếu vẫn không vào, kiểm `netsh interface portproxy` trên Windows
(hoặc chạy `./run labelui` và dùng trình duyệt **trong WSL** nếu có).

## 6. Sau khi gán: số dùng vào đâu

```bash
python tools/label_ui.py --tong-hop data/demoip_1125-121456_metrics.csv
```
In + ghi `data/nhan/<phiên>_tonghop.json` (có `git_rev`, `do_luc`):

- `theo_nguoi.<tên>.<nhãn>` — mỗi người một dòng, **nhãn cuối của mỗi bước** là nhãn có hiệu lực;
- `so_nhan_trung` / `so_buoc_da_dan` — đã dán lại bao nhiêu lần / có bao nhiêu bước;
- `dong_y_2_nguoi` — **mẫu số phải là `so_buoc_ca_hai_co_ket_luan`**, không phải `so_buoc_ca_hai`:
  `so_buoc_ca_hai` đếm cả bước mà **một trong hai** bấm `0` (bỏ qua), và bước đó **không** được tính là
  đồng ý. Con số trích được là **`so_buoc_dong_y / so_buoc_ca_hai_co_ket_luan`**
  (vd "2 người đồng ý **7/8** bước có kết luận").
- `theo_cap` — đồng ý theo **từng cặp** người; chỉ dùng khi có **≥ 3 người** (khi đó `so_buoc_dong_y` là
  "TẤT CẢ đồng ý", không phải tỉ lệ theo cặp).
- `ten_theo_nguoi` — các cách viết tên đã gặp + nhãn đầu/cuối. **Tên được gộp theo NFC + không phân biệt
  hoa/thường** (`Binh` = `binh`), nhưng đây là gộp **chuỗi tên**: tool chỉ chứng được "**2 chuỗi tên**",
  không chứng được "2 con người" — cần người phụ trách biết ai ngồi dán.

**Cấm trích** khi: chỉ có 1 người dán; `nguoi_gan = "?"`; hoặc bạn chấm theo giây đoán tay mà không
kiểm `t_video` (xem bẫy 1).

Nhãn nằm trong `data/` — `.gitignore` đã có ngoại lệ cho `data/nhan/*.jsonl` và `*_tonghop.json`, nên
muốn dùng làm bằng chứng nộp bài thì `git add data/nhan/…` (đừng `-f` cả thư mục `data/`).

## 7. Quan hệ với công cụ khác trong repo

| muốn gán | dùng |
|---|---|
| **Phán quyết bắt đúng/sai** trên phiên đã quay (video đã cháy HUD) | `./run labelui` (tài liệu này) |
| **Mask GT** để chấm mIoU trên **clip sạch** | `./run gt` (`scripts/gt_gan_nhanh.py`) — xem `docs/thuoc-do-bam-dung.md` |
| Chấm **sự kiện cổng** theo toạ độ (`px`, `px/s`) | `scripts/eval_gate_rules.py` (đọc `CA_DUNG`/`CA_SAI`) |

Nhãn của `labelui` là **nguồn** để cập nhật `CA_DUNG`/`CA_SAI` khi có ca mới — nhớ ghi kèm ảnh cắt.
