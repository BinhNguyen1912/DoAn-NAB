# Ngày 22-11-2026 — Quét `image_size` trên T4: mIoU vs ms/frame

## 🎯 Mục tiêu
- Trả lời bằng SỐ ĐO: với **cùng SAM 2.1 tiny**, chạy `image_size` lớn trên GPU có chấm dứt được lỗi
  "phân đoạn HỤT diện tích" (baseline CPU @192 = mIoU **0,7644**) không — trước khi quyết định
  **đổi lõi sang Cutie** (thay model = rủi ro lớn, tốn nhiều ngày).
- Mục tiêu phụ: chốt `image_size` cho các lần chạy GPU và **mốc so sánh** cho Cutie.

## 📥 Input
- Clip `data/binh2.mp4` (720×1280, 360 frame) + GT người tô: `docs/gt/binh2_tay` (12 frame, 8 frame có
  vật) và `docs/gt/binh2_tay2` (7 frame, 2 frame có vật).
- Ô chọn suy **từ GT frame đầu** (không đoán): `(334, 319, 158, 568)`.
- Baseline CPU: `data/miou_baseline_binh2_2026-11-22_metrics.json` (mIoU 0,7644 @192; artifact này
  **không có** số thời gian — thời gian CPU @192 đã đo ở chỗ khác là ~100–107 ms/frame, AGENTS §6).
- Colab T4 16 GB (`nvidia-smi` = Tesla T4, **không có Flash Attention**: Turing 7.5).

## 🔨 Công việc đã thực hiện
1. **`scripts/bench_gpu_binh2.py`** (mới): chạy `tools/live_worker.py` cho từng `image_size`, dump mask
   tại đúng các frame có GT rồi chấm `mIoU` bằng `scripts/score_miou.cham` (dùng chung thang đo với lần
   đo CPU ⇒ so sánh được). Artifact ghi `git_rev`, `git_dirty_code`, `lenh`, `do_luc` — ở cấp file VÀ
   từng dòng.
2. Sửa các lỗi gặp khi chạy trên Colab:
   - **Thiếu `--stop-after-frames` ⇒ worker LẶP FILE VÔ HẠN** (`loop_files=True`): người chạy thấy
     "chạy quài" không bao giờ có bảng số. Nay script đọc `CAP_PROP_FRAME_COUNT` và **NÉM nếu không đọc
     được hoặc ≤ 0** (bản đầu `if dung_sau:` lặng lẽ bỏ cờ ⇒ lỗi quay lại).
   - **`--stream` giả**: bản đầu dùng `subprocess.run(stdout=PIPE)` — gom hết output rồi mới trả, nên im
     lặng 1–2 phút lúc nạp model và người chạy bấm Ctrl-C. Nay `Popen` + **luồng đọc riêng** (để
     `--timeout` cắt được cả tiến trình treo mà không in gì).
   - **Ghi đè artifact**: gộp theo `image_size` — nhưng bản đầu **gộp xong không ghi** (xem mục Lỗi).
3. Chặn sớm khi **thiếu clip**: repo KHÔNG chứa video (`data/` bị `.gitignore`) nên bản clone trên Colab
   không có `binh2.mp4`; lỗi cũ chỉ hiện "Không mở được video file" từ tầng dưới.
4. Viết lại notebook: **`colab.ipynb` ở gốc repo, 6 ô** (thay notebook 17 ô; `notebooks/…` vẫn còn và
   vẫn dùng `git pull` cũ — chưa dọn). `git pull` → `checkout -B <nhánh> origin/<nhánh>` để không chết
   vì "divergent branches".

## 📤 Output / Kết quả

**Bảng số đo được (T4, `vos_every=1`, 360 frame, cùng clip + cùng ô chọn + cùng bộ frame GT)**

| imgsz | hiệu lực | ms/frame | `vos_fps` | mIoU `binh2_tay` (n=8) | mIoU `binh2_tay2` (n=2) |
|---|---|---|---|---|---|
| 192 | 192 | **99,5** | 9,5 | 0,7644 | 0,7683 |
| 320 | 320 | 111,9 | 10,9 | **0,8161** | 0,7762 |
| 512 | 512 | 129,1 | — | **0,8338** | **0,8118** |
| 1024 | 1024 | **507,4** | — | 0,8368 | 0,8198 |

> ⚠️ **Nguồn từng dòng:** 192/320 đo ở **một lần chạy**; 512/1024 đo ở **lần chạy khác** (artifact
> `data/gpu_sweep_binh2_2026-11-22_metrics.json` chỉ còn 512/1024, `lenh = … --sizes 512,1024`).
> Cả hai dùng cùng clip/ô chọn/bộ frame GT nên so sánh được, nhưng **KHÔNG phải "cùng 1 lần chạy"** —
> bản đầu của log này ghi sai như vậy, review độc lập 22-11 bắt được.

**Đọc số — so sánh CẶP theo từng frame (`scripts/paired_miou.py`, 22-11):**

So hai giá trị TRUNG BÌNH của hai lần chạy cần ngưỡng nhiễu mIoU — repo **chưa có**. Nhưng cả 4 cấu
hình đều chấm trên **cùng 8 frame** (`binh2_tay`), nên so **theo cặp** (frame i của A vs frame i của B)
là cách đúng: nó khử phương sai GIỮA các frame (thứ chi phối mọi so sánh trung bình) và không cần
mượn ngưỡng của đại lượng khác.

| So sánh | n | frame B>A | mean Δ | median Δ | CI95 (bootstrap theo frame) | sign test | ms/frame |
|---|---|---|---|---|---|---|---|
| 192 → 320 | 8 | **7/8** | **+0,0517** | +0,0371 | **[+0,0249, +0,0842]** (không chứa 0) | p = 0,070 (biên) | 99,5 → 111,9 (+12 %) |
| 320 → 512 | 8 | 6/8 | +0,0176 | +0,0251 | [+0,0036, +0,0315] (sát 0) | p = 0,289 | 111,9 → 129,1 (+15 %) |
| **512 → 1024** | 8 | **4/8** | **+0,0030** | +0,0062 | **[-0,0071, +0,0140] (CHỨA 0)** | p = 1,000 | 129,1 → **507,4 (+293 %)** |

Chênh lệch từng frame (192→320): `0:+0,142 · 33:+0,037 · 65:+0,035 · 98:+0,094 · 131:+0,031 ·
163:-0,004 · 228:+0,026 · 261:+0,053` — 7 frame tăng, **frame 163 giảm nhẹ** (và 163 là frame tệ nhất
ở MỌI kích thước: 0,746–0,750) ⇒ lỗi còn lại **không phải** do độ phân giải.

**Kết luận được phép rút ra:**
1. **512 → 1024 là KHÔNG KHÁC BIỆT** — đây là kết luận **âm tính có bằng chứng** (4/8 frame, CI chứa 0),
   mạnh hơn "chưa đo được"; cộng với **chậm 3,9×** ⇒ **cấm 1024**.
2. **192 → 320 là chênh lệch lớn nhất** (+0,052; CI không chứa 0) nhưng sign test **p = 0,070 > 0,05**
   vì chỉ có 8 frame (sign test cần 8/8 cùng dấu để p < 0,05) ⇒ viết **"có khả năng thật, chưa đạt
   ngưỡng tuyên bố"**, KHÔNG viết "tốt hơn".
3. **320 → 512: chưa kết luận** (6/8, p = 0,29, CI sát 0). Muốn chốt thì lặp 3 lần/cấu hình.
4. Các frame trong một clip **không độc lập** ⇒ p-value là chỉ báo; đừng trích "p" như bằng chứng cứng.

- `coverage` trong `phu_gt` = tỉ lệ frame **chấm được** trên số frame ĐÃ HỎI, **gồm cả frame GT rỗng**
  ⇒ với `binh2_tay` con số đúng là ~0,42 (8 chấm / 19 hỏi, 11 frame GT rỗng). Đọc kèm `n_cham`.
- `mIoU @192` trên GPU **trùng khít** baseline CPU (0,7644) ⇒ thiết bị không đổi chất lượng phân đoạn
  (thời gian CPU @192 đã đo ~100–107 ms/frame, AGENTS §6 — con số "342 ms" ở bản nháp trước **không
  có nguồn**, đã bỏ).
- `ms/frame` là thời gian tường / số frame PHÁT, **gồm cả nạp model** ⇒ **cận trên**, không phải `vos_ms`.
- Cột `binh2_tay2` chỉ có **n=2** frame có vật ⇒ mọi số từ cột đó là bằng chứng YẾU, cấm trích.

**Quyết định:** GPU mặc định **320** (chênh lệch lớn nhất so với 192, giá rẻ nhất); dùng **512** khi
cần chi tiết vật nhỏ và chấp nhận +15 % thời gian (320 vs 512 **chưa kết luận**). **Cấm 1024** (đã có
bằng chứng âm tính + chậm 3,9×). **Chưa đổi model.** Mốc cho Cutie: dùng lại `scripts/paired_miou.py`
— Cutie phải **thắng theo cặp trên cùng bộ frame** (CI95 không chứa 0), không phải hơn trung bình một
chút.
**Việc bắt buộc tiếp theo:** chạy `--sizes 192,320,512,1024` trong **MỘT lần** (ô 4 của `colab.ipynb`
nay chỉ còn 1 lần chạy) để artifact có provenance thống nhất, rồi lặp 3 lần/cấu hình nếu muốn kết luận
320 vs 512.

- File thay đổi:
  - `scripts/bench_gpu_binh2.py` — quét `image_size`, chấm mIoU, `--stream` thật, luôn
    `--stop-after-frames`, gộp artifact ĐÚNG, kiểm `image_size_hieu_luc`
  - `tests/test_bench_gpu_binh2.py` — 24 test cho gộp artifact / ô chọn / số frame / kiểm cấu hình
  - `scripts/paired_miou.py` — so sánh CẶP mIoU giữa hai cấu hình trên cùng frame (sign test + CI
    bootstrap), `--gt` để chọn bộ GT; đọc được cả 2 lược đồ `chi_tiet`
  - `tests/test_paired_miou.py` — 14 test (trọng tâm: sign test đúng — bản nháp đầu tôi quên chia 2^n)
  - `data/gpu_sweep_binh2_2026-11-22_lan{192-320,512-1024}_metrics.json — **BẢN TRÍCH** (xem `_trich_tu` trong file)` — 2 artifact THẬT của 2 lần
    chạy (cùng `git_rev 316c6e8`), đủ để tái lập bảng cặp ở trên
  - `colab.ipynb` — notebook 6 ô ở gốc repo (tên ngắn để link Colab không bị cắt)
  - `AGENTS.md` §6 — 3 bài học: `image_size` bão hoà ở 512, cạm bẫy gộp artifact, Colab phải
    `--stop-after-frames` + `Popen`

## 🐞 Vấn đề gặp phải & cách xử lý
- **"Chạy quài" 1–2 phút rồi Ctrl-C (2 lần)**: không phải model chậm — (a) thiếu `--stop-after-frames`
  ⇒ worker lặp vô hạn; (b) `--stream` dùng `subprocess.run` nên không in gì. Đã sửa cả hai.
- **P0 do review độc lập bắt: gộp artifact XONG RỒI VỨT.** `payload["ket_qua"]` được gán trước khi gộp,
  `rows` sau đó bị gán lại thành list mới ⇒ file ghi ra chỉ có đợt cuối. Bằng chứng: artifact chỉ có
  512/1024 trong khi bảng in ra đủ 4 dòng. **Đã sửa** bằng `tao_payload()` chỉ nhận list đã gộp + test
  `test_payload_mang_list_da_gop`. **Hệ quả tồn tại:** dòng 192/320 không còn trong artifact ⇒ phải
  chạy lại (đã ghi ở trên).
- **P1 do review bắt (2 vòng): mượn ngưỡng nhiễu của đại lượng khác cho mIoU.** Vòng 1 tôi lấy ±0,019
  (`drift_iou`); vòng 2 tôi lại lấy 0,022–0,034 — nhưng đó là `iou_mean` **hộp vs GT** trên
  `binh1`/`b1b`, KHÔNG phải mask mIoU trên `binh2_tay`. Kết luận đúng: **repo chưa có ngưỡng nhiễu cho
  mIoU ở cấu hình này**, n=1 mỗi cấu hình ⇒ **cả ba so sánh đều chưa kết luận được**; chỉ GIÁ là chắc
  (1024 = 3,9× mà +0,003 ⇒ cấm).
- **`git pull` báo `divergent branches`**: nhánh `colab-bench` bị force-push ⇒ notebook dùng
  `checkout -B <nhánh> origin/<nhánh>`.
- **"Không mở được video file 'data/binh2.mp4'"**: `data/` bị `.gitignore` nên bản clone không có clip.
  Nay chặn ở cửa vào với hướng dẫn, và ô 3 của notebook tự mở `files.upload()`.
- **`mask_ngoai_gt_mean` = 0,052 ở 512** ⇒ ~5 % mask nằm NGOÀI GT (tràn), khác chẩn đoán "hụt diện
  tích" ở 192. Nay `chi_tiet.frames` giữ `dien_tich_gt`/`dien_tich_pred`/`ly_do` từng frame để kiểm lại.
- **`binh2_tay2` chỉ có `n=2` frame chấm được** ⇒ số 0,81 là bằng chứng YẾU, không trích như số chắc.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Chạy `--sizes 192,320,512,1024` **một lần** trên T4 ⇒ 1 artifact 4 dòng cùng `git_rev`; lặp 3
      lần nếu cần kết luận 320 vs 512 (n=1 chưa kết luận được).
- [ ] Lặp **3 lần/cấu hình** cho 320 và 512 rồi so cặp (gộp thêm mẫu) — cách duy nhất để chốt 320 vs
      512 và để nâng 192→320 từ "có khả năng" lên "kết luận".
- [ ] Chốt A/B **Cutie trên T4** bằng `scripts/paired_miou.py` (CI95 không chứa 0 mới tính là thắng).
- [ ] Tô thêm GT cho `binh2_tay2` (hiện 2 frame có vật) để cột đó có ý nghĩa thống kê.
- [ ] Đo đường **live** trên GPU @320/512 (`scripts/measure_live_relay.py`) — số ở đây là **batch**;
      demo webcam vẫn phải chạy CPU @192 (Colab không thấy webcam laptop).
- [ ] Dọn `notebooks/colab_gpu_evaluation.ipynb` (vẫn dùng `git pull` + nhánh có `/`).

## 📚 Tài liệu tham khảo
- SAM 2: https://github.com/facebookresearch/sam2 · SAMURAI: https://github.com/yangchris11/samurai
- `docs/thuoc-do-bam-dung.md` (quy tắc chấm mIoU: GT rỗng ⇒ không chấm; model rỗng ⇒ 0,0)
- AGENTS §6 (trần CPU, ngưỡng nhiễu theo ô chọn, "Số 0,0 trong artifact là cạm bẫy")
- AGENTS §9.1 — review độc lập 22-11 (đã bắt 2 P0 + 4 P1; kết quả ghi ở trên)
