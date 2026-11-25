# 25-11-2026 — Ô đỏ "dựt", chữ đè chữ trên HUD, và vì sao hệ kẹt ở "chưa xác minh"

## 1. Mục tiêu
Người dùng chạy `./run demoip` (phiên `data/demoip_1125-100334`, `git_rev 25e72e4`, 160 frame /
43,2 s, 18,7 FPS, mean 261 ms, `mất dấu 22/160`) và phản ánh **hai** việc, sau khi phần "vật rời
khung rồi vào lại" đã chạy đúng:

1. *"nhận diện lại cũng được, nhưng mà nó để nghi, nghi cũng đúng vật, chưa cập nhật thành box đỏ"*
2. *"box đỏ hơi dựt lag chút xíu"*

## 2. Input
- `data/demoip_1125-100334_metrics.csv` (160 dòng, cột `nghi_doi_tuong`, `bbox_w/h`, `mask_area`…)
- `data/demoip_1125-100334_web.mp4` (H.264 30 fps, 1 296 frame) — **nguồn đo quan trọng nhất**, vì đó
  là đúng thứ người dùng NHÌN.
- Code: `src/identity_guard.py` (`IdentityWatch`), `src/visualizer.py`, `src/smooth_display.py`.

## 3. Công việc đã thực hiện

### 3.1 Đo cái người dùng THẤY (không đo CSV)
Dò ô đỏ theo màu trên từng frame hiển thị của video HUD (241 frame trong 18–26 s):

| đại lượng | số |
|---|---|
| chuỗi ô **đứng yên** | med **9 frame hiển thị** (~300 ms) rồi nhảy |
| bước nhảy tâm khi ô đổi | med **22,7 px**, max **118,1 px** |
| bước nhảy bề rộng | med 7 px, max 28 px |

⇒ "Dựt" = đường CLI **không có LK** (`--smooth` vẽ lại kết quả VOS gần nhất), nên ô đứng yên ~9 frame
rồi nhảy. **Không phải** model chậm hơn hôm trước: so 4 phiên, jitter tâm (residual so với median-3)
med của phiên này là **10,2 px** so với 10,5 / 11,0 / 13,5 px của các phiên 24–25/11 ⇒ **không tệ hơn**.

### 3.2 Trạng thái "chưa xác minh" — đo được, đúng như phản ánh
| số | giá trị |
|---|---|
| frame ẩn mask khi còn vật (`nghi`) | 9/160 = **5,6 %** |
| frame vẽ kiểu **chưa xác minh** (viền nét đứt, không tô, không quỹ đạo) | **29 frame** sau f123 = **18 %** phiên |
| khung hình có nét đứt vàng trong video (dò màu) | 39/216 mẫu = **18 %** |

Nguyên nhân **trong code**, không phải ngưỡng: `IdentityWatch` chỉ có `nghi → chua_xac_minh` khi đủ
`settle_steps`, còn `chua_xac_minh → ok` **chỉ** xảy ra khi gọi `reset()` (`r`, `c`, hoặc re-ID
reacquire). Đường `./run demoip` chạy `--no-reid` ⇒ **sau lần báo nghi đầu tiên, màn hình không bao
giờ trở lại "box đỏ" nữa**, dù bám đúng vật (ảnh t=37,8 s: ô nét đứt nằm đúng trên cái remote).

### 3.3 Sửa được ngay (2 việc, không cần quyết định kiến trúc)
1. **`src/box_smoother.py` (mới) + `--box-smooth-tau-ms`** — làm mượt **ô VẼ RA** bằng EMA theo thời
   gian (τ = 125 ms), `result.bbox` KHÔNG đổi (cổng nghi / metrics / mIoU vẫn dùng số model thật).
   Cú nhảy > `0,25 × đường chéo` thì **snap** (không tráng thành vệt quét ngang khung); ô rỗng ⇒ reset.
   Mô phỏng lại chính dãy ô của phiên này: dịch chuyển/frame med **0 → 1,35 px**, max **118 → 41,8 px**,
   tương quan chéo cực đại ở **lag 0** ⇒ trễ ổn định ~0. `./run demoip` bật 125; `tools/run_live.py`
   mặc định **TẮT** để artifact cũ tái lập được.
2. **Chữ đè chữ trên HUD** (ảnh t=37,8 s): nhãn ngắn `"CHUA XAC MINH"` dán ở `y1 - 6` rơi vào dải HUD
   và chồng lên banner cùng câu (banner vẽ từ `y=104` **xuống** tới ~y=122 ở 480p). Nay: đỉnh ô nằm
   trong dải HUD ⇒ **bỏ nhãn ngắn** (banner đã nói cùng câu), không dán xuống trong ô (sẽ đè mask).

### 3.4 CHƯA sửa: `chua_xac_minh → ok` tự động
Đây là thay đổi **thuật toán** (> 4 h) và chạm đúng vết xe đã biết: 21-11 hệ tự bỏ nghi rồi vẽ mask
SAI 65 frame (bám sang cửa/tường be cùng tông). Theo AGENTS §9.2 đã mở **plan 3 ý kiến × 2 vòng**
(chất lượng & số đo · sản phẩm & bằng chứng bảo vệ · độ bền & hiệu năng) — kết quả ghi vào
`docs/plan/25-11-2026-tu-het-nghi.md` khi chốt. Cấm nới ngưỡng: 24-11 đã đo mọi luật "giảm số lần
báo" đều **giảm recall** (7/7 → 1/7…6/7).

## 4. Output / Kết quả
- `src/box_smoother.py` + `tests/test_box_smoother.py` (15 test: EMA, snap, reset, chống đảo cạnh,
  τ phụ thuộc dt).
- `src/smooth_display.py`: `box_smooth_tau_ms` (mặc định TẮT), reset khi `nghi`/mất dấu/chọn lại.
- `src/visualizer.py`: `_HUD_DAY = 130` + luật bỏ nhãn ngắn khi đỉnh ô trong dải HUD; test spy.
- `tools/run_live.py --box-smooth-tau-ms`; `run` (`demoip`) bật 125 kèm số đo trong comment.
- `./run lint` xanh · **2 054 test xanh** (+16).

## 5. Vấn đề & cách xử lý
- **Bẫy đã tránh**: suýt "sửa" bằng cách nới ngưỡng cổng nghi — dữ liệu 24-11 nói nới là mất recall.
- **Bẫy đã tránh 2**: suýt kết luận "model jitter tệ hơn hôm qua" — so 4 phiên thì phiên này **không
  tệ hơn**; cái đổi là **cách vẽ** (đứng yên rồi nhảy).
- Test đầu tiên của việc sửa nhãn sai premise (đòi "trong ô không có chữ"), nhưng **banner hợp lệ đè
  lên viền ô** ⇒ đổi sang spy `_put_text` để kiểm đúng hợp đồng.

## 6. Next steps
- **Chờ plan 3 ý kiến** rồi cài cơ chế `chua_xac_minh → ok` có bằng chứng (mask-vs-mask / round-trip).
- **Cần một phiên mới** để A/B thật việc làm mượt: `./run demoip` (đã bật τ=125) rồi đo lại
  "bước nhảy max" trên video mới; số hiện có là **mô phỏng trên dãy ô cũ**, chưa phải phiên mới.
- Cân nhắc: quỹ đạo vẫn nối qua cú nhảy nhỏ (dưới ngưỡng snap) — xem lại `clear_trajectory` nếu cần.

## 7. Tài liệu tham khảo
- `docs/task/24-11-2026-cong-nghi-tu-ha-muc.md` (3 trạng thái + số replay 4 346 frame)
- `docs/plan/24-11-2026-cong-nghi-bao-oan.md` (vì sao không nới ngưỡng)
- AGENTS.md §6 các bullet "cổng nghi đổi đối tượng", "`--smooth` KHÔNG có LK"
