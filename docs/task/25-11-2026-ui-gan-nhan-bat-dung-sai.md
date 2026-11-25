# Ngày 25-11-2026 — UI gán nhãn "bắt ĐÚNG / SAI" cho phiên đã quay

## 🎯 Mục tiêu
- Người dùng yêu cầu: *"bây giờ tôi có thể gán nhãn, làm UI cho tôi gán đi, với hướng dẫn cách gán
  nhãn"* — và nêu rõ trọng tâm đã đổi: **không cần bám phạm vi đồ án, miễn là hệ bắt đúng / focus lại /
  nhận diện lại đúng vật**.
- Mục tiêu kỹ thuật: có **nguồn nhãn thứ hai** cho các tuyên bố về cổng "nghi đổi đối tượng" và về khả
  năng nhận lại vật. AGENTS §6 hiện ghi: nhãn do **1 người** đọc video thì **không được trích** vào báo
  cáo ⇒ phải có công cụ để người thứ 2 dán **độc lập**, có provenance.

## 📥 Input
- `AGENTS.md` §6 (các kết luận đã đo: `latency_ms` phải **cộng dồn**; `nghi`/`chua_xac_minh` là hai đại
  lượng khác nhau; "vật rời khung" phải tách khỏi "mất dấu"), §9.1 (review độc lập), §7b (1 nhánh/PR).
- `scripts/gt_gan_nhanh.py` + `scripts/gt_painter.html` — công cụ **tô mask** trên **clip sạch** (đã có);
  không dùng được cho phiên đã quay vì **video đã cháy HUD**.
- Phiên thật: `data/demoip_1125-121456_metrics.csv` (295 bước VOS / 98,3 s), `_web.mp4`.
- Yêu cầu từ người dùng (25-11): làm UI + hướng dẫn gán.

## 🔨 Công việc đã thực hiện

1. **Chọn loại nhãn** sau khi loại các khả năng không khả thi:
   - Tô **mask** trên phiên đã quay: **không làm được** — `--record` cháy HUD vào video nên không còn
     frame thô. (Tô mask vẫn dùng `./run gt` trên clip sạch.)
   - Nhãn chọn: **phán quyết theo từng bước VOS** — `dung` / `sai` / `mat_dau` / `khong_co_vat` /
     `bo_qua`, kèm **ô đúng** (kéo chuột) khi hệ bắt sai. Đây đúng thứ cần để (a) kiểm cổng "nghi",
     (b) đếm tỉ lệ bắt đúng, (c) lấy ô GT cho các ca sai.

2. `tools/label_ui.py` (~380 dòng, chỉ stdlib `http.server`):
   - `GET /` phục vụ `tools/label_ui.html`; `GET /video?v=<tên>.mp4` phục vụ mp4 **có Range/206**
     (không có 206 thì Chrome không cho `currentTime` nhảy ⇒ nút "bước kế" chết);
   - `GET /api/sessions` (liệt kê phiên có **cả** CSV + video, kèm số nhãn đã có),
     `GET /api/frames?phien=` (frames + `t_uoc_luong` + `bbox` + `may_an_mask`),
     `POST /api/label` (ghi nhãn);
   - `doc_phien()`: `t_uoc_luong` = **cộng dồn `latency_ms`**. Đo trên phiên thật: bước `#141` cho
     **34,88 s** khi cộng dồn; chia đều `98,0/295×141` sẽ ra **46,8 s** ⇒ lệch **~12 s** (đúng cái bẫy
     AGENTS §6 ghi). Đã kiểm bằng API thật: `f141 t_uoc_luong: [34.88]`.
   - `ghi_nhan()`: **append-only** vào `data/nhan/<phiên>.jsonl`, mỗi dòng có `nguoi_gan`, `git_rev`,
     `do_luc`, `frame_vos`, `t_video` (đồng hồ video thật), `t_uoc_luong`, `bbox_dung`; từ chối nhãn
     ngoài tập đóng và từ chối `nguoi_gan` rỗng.
   - `--tong-hop`: đếm theo người + `dong_y_2_nguoi` (số bước cả hai cùng dán / số bước đồng ý), ghi
     `data/nhan/<phiên>_tonghop.json` có `git_rev`.

3. `tools/label_ui.html` (vanilla JS, không cần build): video + canvas overlay; phím `1/2/3/4/0` ghi
   nhãn ngay, `s` = ghi "ĐÚNG" + sang bước kế, `←/→` nhảy theo **bước VOS** (không phải frame video),
   `,`/`.` nhích ±0,2 s, `b` + kéo chuột vẽ ô đúng, `Esc` bỏ ô. Panel hiện `#frame_vos`, `bước …
   ms`, cảnh báo **"hệ đang ẩn mask"**, bộ đếm số nhãn của **người này** — nhãn của người khác **bị ẩn**
   (chỉ hiện số lượng) để hai người dán độc lập.

4. **Chốt an ninh** (tự tìm ra, không phải review): `POST /api/label` ghi file **theo tên phiên** ⇒
   `phien = "../../x"` là lỗ **ghi ra ngoài** `data/nhan/`. Thêm `ten_hop_le()` (regex + chặn `..`) áp
   ở 4 chỗ: `/video`, `/api/frames`, `/api/label`, `_gio_nhan()`. 11 case tên bẩn + 5 test HTTP.

5. `docs/cach-gan-nhan.md`: hướng dẫn người dán (chạy 30 giây, bảng phím, 3 cái bẫy, gán bao nhiêu là
   đủ, cách mở khi WSL không chia cổng, số sau khi gán dùng vào đâu, quan hệ với `./run gt`).

6. `run`: thêm target `labelui)` và `labeluie2e)` + 2 dòng help.

7. Test & E2E:
   - `tests/test_label_ui.py` — **35 test**: cộng dồn latency, `bbox` từ tâm+kích thước, ô rỗng ⇒ `None`
     (không phải `[0,0,0,0]`), append-only, từ chối nhãn lạ/thiếu người gán/bbox đảo cạnh, dòng JSONL
     hỏng không làm sập, đếm theo người + mức đồng ý, **5 test HTTP thật** (trang chủ, sessions, frames,
     label, 400 cho nhãn sai, **206 + Content-Range** cho Range, chặn `../setup.py`), 11 case tên bẩn.
   - `scripts/e2e_label_ui.js` + `./run labeluie2e`: **27 mục trên Chrome thật** (Windows Chrome lái từ
     WSL qua `cmd.exe`, đúng kiểu `e2e_web.js`/`e2e_gt_painter.js`). Kiểm: trang tải không `pageerror`;
     `<video>` có metadata (chứng minh Range chạy); nút "bước sau" **tua thật** `0,00 → 0,35 s`; phím
     `1` ghi `dung` vào đĩa; `b` + kéo chuột ⇒ `bbox_dung = [192,144,383,335]`; bộ đếm + bảng cập nhật;
     nhãn người khác không lộ. **KẾT QUẢ: PASS 19/19.** Nhãn e2e ghi vào **thư mục tạm**
     (`LABELUI_NHAN_DIR`) ⇒ `data/nhan/` sạch sau khi chạy (đã kiểm: rỗng).

## 📤 Output / Kết quả
- `./run labelui --nguoi-gan <tên>` mở UI; nhãn lưu `data/nhan/<phiên>.jsonl`; tổng hợp bằng
  `python tools/label_ui.py --tong-hop data/<phiên>_metrics.csv`.
- Kiểm chạy thật: API trên cổng 8771 liệt kê **57 phiên**; `frames` phiên 121456 = 295 bước, tổng
  94,76 s (khớp phép cộng `latency_ms`); `f141` ở **34,88 s**; `/video` trả **206** đúng `Content-Range`.
- `./run lint` xanh · `./run test` **2 102 passed** · `./run labeluie2e` **PASS 19/19**.
- File thay đổi:
  - `tools/label_ui.py` — server + đọc CSV + ghi nhãn + chặn tên bẩn
  - `tools/label_ui.html` — trang gán nhãn (phím tắt, canvas vẽ ô, bộ đếm)
  - `scripts/e2e_label_ui.js` — E2E Chrome thật (19 mục)
  - `tests/test_label_ui.py` — 35 test
  - `docs/cach-gan-nhan.md` — hướng dẫn người gán
  - `run` — thêm `labelui`, `labeluie2e`

## 🐞 Vấn đề gặp phải & cách xử lý
1. **`/video` không có Range ⇒ không tua được.** Triệu chứng: E2E "nút bước sau tua được video" đỏ
   (`0,00 → 0,00`). Sửa: tự xử lý `Range` header, trả 206 + `Content-Range` (test riêng).
2. **Playwright `waitForSelector('#phien option')` timeout** dù 57 option **có** trong DOM: `<option>`
   trong `<select>` đóng không "visible" theo Playwright ⇒ phải `state: 'attached'`.
3. **`chromium.launch()` trần ném "Executable doesn't exist"**: bản chromium tải riêng không có trên
   máy; `channel: 'chrome'` trong WSL lại tìm `/opt/google/chrome`. Cách repo đang làm (và đã chép):
   chạy **node của Windows** qua `cmd.exe`, không chạy node Linux.
4. **`ValueError: not in the subpath of`** khi in đường dẫn thư mục nhãn tạm (e2e) ⇒ bọc `relative_to`
   bằng try/except.
5. **E2E lần đầu ghi nhãn vào `data/nhan/` THẬT** (file `demoip_1125-121456.jsonl` có 2 dòng `e2e`) ⇒
   thêm `LABELUI_NHAN_DIR` để e2e dùng `mktemp -d`, không bao giờ lẫn nhãn thật. Đã xoá file rác.
6. **Favicon 404 làm E2E đỏ** ở mục "không có console.error" ⇒ thêm route `/favicon.ico` trả 204.

## 📋 Kết quả review độc lập (AGENTS §9.1)

- **Agent review:** `reviewer` (task `mwvpd7rz-66b0`, read-only). Kết luận: *mergeable after the four P1
  items; no P0 remains*. Review bắt **4 P1 + 7 P2 + 8 P3**, trong đó nhiều lỗi **thật** mà test + e2e của
  tôi không thấy:
  - **P1-1 focus trap bịa ra "2 người"**: gõ tên rồi bấm `1` ⇒ số `1` vào ô tên (`"Binh1"`), không ghi
    nhãn nào, và **mọi nhãn sau mang tên sai** ⇒ `tong_hop` báo `so_nguoi = 2` cho **một người**. Đã
    sửa: Enter ở ô tên = blur; phím nhãn vẫn ăn khi con trỏ ở ô tên/select; header hiện người đang dán.
  - **P1-2 ô vẽ sống qua bước**: vẽ ô ở bước *k*, `→`, bấm `2` ⇒ lưu ô của bước *k* cho bước *k+1*.
    Đã sửa: ô gắn `buoc`, `capNhat` xoá ô khi bước đổi; E2E kiểm (`rec3.bbox_dung === null`).
  - **P1-3 `s` luôn ghi "ĐÚNG"**: bấm `2` rồi `s` tạo **hai nhãn mâu thuẫn** cho cùng bước, và
    `tong_hop` đếm mọi dòng (`theo_nguoi`) nhưng chấm đồng ý theo dòng **đầu** ⇒ hai con số nói về hai
    tập khác nhau. Đã sửa: `s` ghi lại **nhãn vừa chọn** (chưa chọn thì từ chối), `tong_hop` lấy nhãn
    **CUỐI** của mỗi `(bước, người)` + báo `so_nhan_trung`.
  - **P1-4 trang web khác chèn được nhãn** (request `text/plain` `no-cors` ⇒ server vẫn parse) ⇒ đầu độc
    file bằng chứng **dưới tên người đang dán**. Đã sửa: bắt buộc `Content-Type: application/json`
    (buộc preflight) + chặn `Origin` lạ (403).
  - **P2 đã sửa luôn**: canvas nuốt chuột của `<video controls>` (nay `pointer-events:none`, chỉ bật khi
    vẽ) và **thiếu nhánh `Space`** dù doc hứa; nhãn người khác trước đây **vẫn được gửi về trình duyệt**
    rồi ẩn bằng CSS (nay server **chỉ trả nhãn của chính người dán** + số lượng); CSV có BOM từng làm
    **mọi `frame_vos = 0`** (nay `utf-8-sig` + từ chối CSV không tăng dần); body POST méo (mảng, `null`
    trong `bbox_dung`, `Content-Length` khổng lồ) nay trả 400/413/415 thay vì **không trả gì**; E2E assert
    rỗng (`kiem(true,…)`, kiểm `!khac ||` luôn đúng) nay kiểm **toạ độ ô chính xác** (96,72,192,168 trên
    lưới 320×240) + pre-seed nhãn người khác; `./run labeluie2e` phụ thuộc `data/demoip_1125-121456_web.mp4`
    (không được track ⇒ đỏ trên clone sạch) nay **tự sinh fixture** (`scripts/make_labelui_fixture.py`,
    H.264 bằng chính `transcode_for_web` vì **mp4v Chrome không phát được**).
  - **P2-7**: nhãn nằm trong `data/` bị gitignore ⇒ **không ai kiểm được** bằng chứng. Đã thêm ngoại lệ
    `!data/nhan/*.jsonl` + `!data/nhan/*_tonghop.json` vào `.gitignore`.
  - **Reviewer báo sai 1 chỗ**: P2-6 nói `data/demoip_1125-121456_web.mp4` "absent" — trên máy này file
    **có** (e2e cũ vẫn PASS), nhưng **lập luận về clone sạch là đúng** nên vẫn sửa theo hướng tự sinh.
### Review vòng 4 (task `mwvr3px9-ad67`) — 1 P1 + 6 P2

P1 **cùng lớp với vòng 3 nhưng ở phía SERVER**: ô "Người gán" để **trống** thì `do_POST` lấy
`self.nguoi_gan` thay thế, và `/api/frames?nguoi=` rỗng cũng fallback về tên cấu hình ⇒ người thứ 2 xoá ô
tên rồi bấm phím là nhãn ghi dưới tên người thứ 1 **và** trình duyệt của cô ấy tải về đúng nhãn của
người thứ 1 (đếm thành tiến độ của mình). Đã sửa: trống ⇒ **400**, `/api/frames` rỗng ⇒ **không trả nhãn
ai**, lọc theo `khoa_ten` (NFC+casefold) ở cả 3 chỗ.
P2 đã sửa: `flash()` nối "(đã ghi)" vào **cả** hai nhánh không ghi gì; hàng đợi POST không có `.catch`
⇒ `localStorage` ném là **mọi phím sau im lặng**; `--tong-hop` chỉ cảnh báo khi `buoc` ngoài dải mà vẫn
`exit 0` (nay `exit 1` + artifact `ket_qua=false`); `do_GET` **không** kiểm Host ⇒ DNS rebinding **đọc**
được nhãn người khác; và **không có test đường thất bại** cho `--tong-hop` (xoá cả cổng mà suite vẫn
xanh) — nay có.
P3 đã sửa: `t_video` kiểu lạ ⇒ 400 (trước 500); `Infinity`/`NaN` bị `json.dumps` ghi thành `Infinity`
(**JSON không hợp lệ** — parser strict chết) ⇒ chặn; `frame_vos` bắt buộc; artifact chỉ ghi ở **một**
chỗ kèm `ket_qua`/`ly_do`; in `so_nhan_thieu_buoc` khi hai người ở hai không-gian khoá; bỏ `assert … or
True`; test khẳng định **đúng tập 5 nhãn**; chưa tải xong phiên thì không cho ghi.

- **Sau khi sửa (4 vòng review):** `./run lint` xanh · `./run test` **2 174 passed** ·
  `tests/test_label_ui.py` **91 test** · `./run labeluie2e` **PASS 30/30** trên Chrome thật, không phụ
  thuộc `data/`.
### Review vòng 3 (task `mwvql7bu-0455`) — 1 P1 + 7 P2 + 9 P3, đã sửa hết

P1 vòng 3 nặng về **quy trình** hơn là code: bản sửa P1-A (tên đi cùng nhãn) vẫn **điền sẵn tên của
người thứ nhất** vì ưu tiên `--nguoi-gan` hơn tên đã lưu trong trình duyệt ⇒ người thứ 2 mở cùng URL,
không sửa ô tên là mọi nhãn ghi dưới tên người 1, và quy tắc "nhãn cuối thắng" **ghi đè** nhãn của
người 1 ⇒ `tong_hop` in "1 người" **và** đã xoá mất bằng chứng. Đã sửa: tên đã lưu của trình duyệt
thắng mặc định server; e2e kiểm đúng điều này.

Các P2/P3 đã sửa: `tong_hop` vẫn có thể **ném** với dòng `buoc: [1]`/`buoc: "abc"` ⇒ cả POST trả lỗi
mạng **sau khi** nhãn đã ghi (nay mọi dòng méo thành `so_nhan_loi`, và `tong_hop` trong response được
bọc); UI **nuốt lỗi POST** (`.catch(()=>{})`) rồi vẫn nhảy bước ⇒ nay hiện lỗi đỏ và **ở lại** bước;
bước được **tính lại sau khi chờ hàng đợi** nên phán quyết rơi sang bước kế (nay **ghim bước tại lúc bấm
phím**); `veO.buoc` bị **đóng dấu lại khi di chuột** (nay chỉ neo ở `mousedown`); Host allowlist chỉ
nhận 1 IPv4 ⇒ **403 đường LAN** mà tài liệu hướng dẫn (nay dùng `ip_may()` = mọi IPv4 + test); `[::1]`
bị 403 vì tách tay `rpartition(":")` (nay `urlparse("//"+host).hostname`); thiếu `buoc` thì **bỏ qua
toàn bộ kiểm** (nay bắt buộc + server tự điền `frame_vos`/`t_uoc_luong` từ CSV); `chua_xac_minh_n = 0`
hiển thị như "không có" (nay `?? null`); **tên gộp theo NFC + casefold** (`Binh`/`binh`/`BINH` là 1
người — trước đó một người gõ lại tên khác hoa/thường tạo "2 người đồng ý" giả + `--tong-hop` exit 0);
thêm `theo_cap` (đồng ý theo từng cặp) cho trường hợp ≥ 3 người; `--tong-hop` gate trên số nhãn **hợp
lệ**, kiểm `git_rev`, cảnh báo `buoc` ngoài dải CSV; fixture `i % 52` (vật không ra khỏi khung); e2e tự
dọn file nhãn khi chạy tay; bỏ `void 0;` + `state.nguoi`/`state.nhan` chết; `chonPhien` chỉ nhận phiên
mới **sau** khi tải xong; doc sửa mẫu số (`so_buoc_ca_hai_co_ket_luan`), ghi rõ tool chứng "2 **tên**"
chứ không phải "2 con người".

### Review vòng 2 (task `mwvq1i7z-26e0`) — bắt 3 P1 mà vòng 1 bỏ qua

Vòng 2 đọc **đường ghi xuống file** chứ không chỉ đường hiển thị, và bắt đúng 3 lỗi làm **số liệu sai
âm thầm**:

- **P1-A tên người dán là đồ trang trí**: `ghi_nhan(... self.nguoi_gan)` ⇒ gõ tên gì trong UI cũng ghi
  tên của cờ `--nguoi-gan` lúc khởi động. Hệ quả: 2 người dùng **cùng một server** (đúng như tài liệu
  hướng dẫn) ⇒ `so_nguoi = 1`, `dong_y_2_nguoi = null` ⇒ **không bao giờ** có được con số "2 người đồng
  ý" để nộp bài. Và assertion của e2e cũ xanh **kể cả khi UI bị bỏ qua hoàn toàn** (vì server chạy
  `--nguoi-gan e2e` và test gõ `e2e`). Đã sửa: tên đi cùng body nhãn, server dùng tên đó; `/api/frames`
  lọc theo `?nguoi=`; e2e gõ tên **khác** (`nguoi-tu-ui`) nên assertion mới có hiệu lực; test Python
  `--nguoi-gan Binh` + body `An` ⇒ file ghi `An`.
- **P1-B `veO.buoc` được GHI mà không chỗ nào ĐỌC** ⇒ ô vẽ vẫn dính sang bước sau trong 3 đường: (1) tua
  bằng `<video controls>` vì `capNhat` chỉ chạy ~4 lần/s, (2) `→` rồi bấm phím ngay (< độ trễ `seeked`),
  (3) **đổi phiên** không reset `veO`. Đã sửa: `bbox_dung` chỉ gửi khi `veO.buoc === i` (đọc tại chỗ
  ghi), reset `veO`/`buocTruoc`/`nhanChon` trong `chonPhien`.
- **P1-C `s` mang nhãn của BƯỚC TRƯỚC**: guard chỉ bảo vệ lần bấm đầu của cả phiên ⇒ bấm `2` ở bước *k*,
  `→`, bấm `s` là ghi `sai` cho bước *k+1* dù chưa phán quyết. Đã sửa: `nhanChon = {buoc, nhan}` và
  `luuVaTiep` chỉ dùng lại khi `nhanChon.buoc === bước hiện tại`.
- **P2 đã sửa**: ô 0 px (bấm `b` rồi **click**) từng làm POST 400 và **khoá cả phiên** tới khi Esc; `bo_qua`
  bị tính là "2 người đồng ý" (nay tách `so_buoc_ca_hai_co_ket_luan`); dòng JSON rác làm `tong_hop` ném
  **sau khi** nhãn đã ghi (nay đếm `so_nhan_loi`, `so_nhan_trung` chỉ trên dòng hợp lệ); trộn không-gian
  khoá `buoc`/`frame_vos` (nay có tiền tố `("buoc",n)`/`("frame",n)`); server **không đối chiếu `buoc`
  với CSV** (nay 400 nếu ngoài dải hoặc `frame_vos` lệch); doc hứa UI hiện `chua_xac_minh_n` mà code
  không hiện (nay hiện); e2e "phím số khi con trỏ ở ô tên" **không hề được test** (`type('')` + Enter
  trước) → nay bấm `1` khi con trỏ còn trong ô tên.
- **P3 đã sửa**: `Origin: "null"` là trọng lượng chết (bỏ) — thay bằng **allowlist `Host`** vì đường còn
  hở là **DNS rebinding** (Origin == Host); `trap` trong `run` đặt trước lệnh có thể fail + kiểm server
  có lên; `--tong-hop` trả mã 1 khi chưa trích được (1 người / 0 bước trùng có kết luận); fixture: vật
  chạy ra ngoài khung từ frame 56 (nay `i % 56`) và docstring sai số frame; POST **serialize** trong UI
  để "dòng cuối thắng" đúng thứ tự bấm; bỏ dead code `_trong_repo`.
- **Tự kiểm thêm 2 lỗi (không phải reviewer bắt)**: tên người dán chứa `\n`/tab vẫn ghi được (JSONL hợp
  lệ nhưng không đọc được cho người) ⇒ từ chối ký tự điều khiển; và `doc_phien` bị parse lại **ở mỗi
  nhãn** để đối chiếu `buoc` — đo **1,3 ms** (295 dòng) nhưng **169 ms** (50 000 dòng) ⇒ thêm cache theo
  `(path, mtime_ns, size)` (vẫn đúng khi CSV bị ghi lại).
- Reviewer ghi rõ **không có shell** nên lint/test/e2e là số của tôi, không tái lập được — đúng quy ước
  "ghi rõ môi trường đo".

- Vòng review vòng 1 đã chạy **trên cây đang đổi** (reviewer ghi rõ "the tree changed three times mid-review")
  ⇒ các mục P1 đã sửa cần **review vòng 2** trước khi merge.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Người dùng dán nhãn một phiên thật** (`demoip_1125-121456`), rồi **người thứ 2** dán cùng tập
      bước ⇒ mới có `dong_y_2_nguoi` để trích vào báo cáo.
- [ ] Dùng nhãn để cập nhật `CA_DUNG`/`CA_SAI` của `scripts/eval_gate_rules.py` khi có ca mới, kèm ảnh
      cắt (nhãn suông không đủ để người đọc tin).
- [ ] Cân nhắc: nhãn nằm trong `data/` (bị gitignore) ⇒ muốn làm **bằng chứng nộp bài** thì phải
      `git add -f data/nhan/<phiên>.jsonl data/nhan/<phiên>_tonghop.json` khi công bố.
- [ ] (Tầng 2, việc lớn > 4 h ⇒ cần plan 3 ý kiến) **xác minh bằng mask thật**: re-prompt SAM 2 rồi
      chấm mask-vs-mask để tách "vẫy nhanh" khỏi "đổi vật" — đó mới là thứ cứu ca *"vật vào lại thì bám
      sang tường"*.
- [ ] (P2/P3 từ review độc lập — xem mục dưới)

## 📚 Tài liệu tham khảo
- `AGENTS.md` §2 (log), §6 (cộng dồn `latency_ms`; `nghi` vs `chua_xac_minh`; "vật rời khung" ≠ "mất
  dấu"), §7b (nhánh + PR), §9.1 (review độc lập).
- `docs/cach-gan-nhan.md` (tài liệu người dùng của chính công cụ này).
- `docs/thuoc-do-bam-dung.md` (thước đo "bám đúng" = mIoU mask vs GT — công cụ **khác**, cho clip sạch).
- Playwright docs — `chromium.launch({channel})`, `waitForSelector` state `attached`.
