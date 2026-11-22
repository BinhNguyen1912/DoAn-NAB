# Ngày 22-11-2026 — Quét `image_size` trên T4: mIoU vs ms/frame

## 🎯 Mục tiêu
- Trả lời bằng SỐ ĐO: với **cùng SAM 2.1 tiny**, chạy `image_size` lớn trên GPU có chấm dứt được lỗi
  "phân đoạn HỤT diện tích" (baseline CPU @192 = mIoU **0,7644**) không — trước khi quyết định
  **đổi lõi sang Cutie** (thay model = rủi ro lớn, tốn nhiều ngày).
- Mục tiêu phụ: chốt `image_size` cho các lần chạy GPU và **mốc so sánh** cho Cutie.

## 📥 Input
- Clip `data/binh2.mp4` (720×1280, 360 frame) + GT người tô: `docs/gt/binh2_tay` (12 frame, 8 frame có
  vật) và `docs/gt/binh2_tay2` (7 frame, 2 frame có vật).
- Ô chọn suy **từ GT frame 0** (không đoán): `(334, 319, 158, 568)`.
- Baseline CPU: `data/miou_baseline_binh2_2026-11-22_metrics.json` (mIoU 0,7644 @192, 342 ms/frame).
- Colab T4 16 GB (`nvidia-smi` = Tesla T4, **không có Flash Attention**: Turing 7.5).

## 🔨 Công việc đã thực hiện
1. **`scripts/bench_gpu_binh2.py`** (mới): chạy `tools/live_worker.py` cho từng `image_size`, dump mask
   tại đúng các frame có GT rồi chấm `mIoU` bằng `scripts/score_miou.cham` (dùng chung thang đo với lần
   đo CPU ⇒ so sánh được). Artifact ghi `git_rev`, `git_dirty_code`, `lenh`, `do_luc`, `o_chon_xywh`.
2. Sửa **3 lỗi thật** gặp khi chạy trên Colab:
   - **Thiếu `--stop-after-frames` ⇒ worker LẶP FILE VÔ HẠN** (`loop_files=True`): người chạy thấy
     "chạy quài" không bao giờ có bảng số. Nay script tự đọc `CAP_PROP_FRAME_COUNT` của clip và luôn
     truyền cờ này.
   - **`--stream` giả**: bản đầu dùng `subprocess.run(stdout=PIPE)` — nó gom hết output rồi mới trả,
     nên im lặng 1–2 phút lúc nạp model và người chạy bấm Ctrl-C. Nay dùng `Popen` đọc **từng dòng**.
   - **Artifact bị ghi đè** khi chạy thành nhiều đợt (192/320 rồi 512/1024) ⇒ mất số đợt trước. Nay gộp
     theo `image_size`.
3. Chặn sớm khi **thiếu clip**: repo KHÔNG chứa video (`data/` bị `.gitignore`) nên bản clone trên Colab
   không có `binh2.mp4`; lỗi cũ chỉ hiện "Không mở được video file" từ tầng dưới.
4. Viết lại notebook: **`colab.ipynb` ở gốc repo, 6 ô** (thay notebook 17 ô) + đồng bộ `gpu.ipynb`;
   `git pull` → `checkout -B <nhánh> origin/<nhánh>` để không chết vì "divergent branches".

## 📤 Output / Kết quả

**Bảng số (T4, `vos_every=1`, 360 frame, cùng 1 lần chạy, `git_rev 316c6e8`, `git_dirty_code=false`)**

| imgsz | hiệu lực | ms/frame | VOS/giây | mIoU `binh2_tay` (n=8) | mIoU `binh2_tay2` (n=2) |
|---|---|---|---|---|---|
| 192 | 192 | **99,5** | 10,1 | 0,7644 | 0,7683 |
| 320 | 320 | 111,9 | 8,9 | **0,8161** | 0,7762 |
| 512 | 512 | 129,1 | 7,7 | **0,8338** | **0,8118** |
| 1024 | 1024 | **507,4** | 2,0 | 0,8368 | 0,8198 |
| *(CPU @192, phiên khác)* | 192 | 342 | 2,9 | 0,7644 | — |

**Đọc số:**
- `192 → 320`: **+0,052 mIoU** mà chỉ chậm **+12 %** ⇒ món hời nhất.
- `320 → 512`: **+0,018** (xấp xỉ ngưỡng nhiễu ±0,019 của phiên ngắn) với **+15 %** thời gian.
- `512 → 1024`: **+0,003** — **không phân biệt được** với nhiễu, mà **chậm 3,9×** (507 ms = 2 FPS).
  ⇒ **Bỏ 1024**, không đưa vào bất kỳ cấu hình nào.
- `mIoU @192` trên GPU **trùng khít** baseline CPU (0,7644) ⇒ **thiết bị không đổi chất lượng phân
  đoạn**, nên được phép so số GPU với baseline CPU đã có; chênh lệch hoàn toàn do `image_size`.
- `ms/frame` là thời gian tường / số frame PHÁT, **gồm cả nạp model** ⇒ là **cận trên** của độ trễ thật,
  không phải `vos_ms`.

**Quyết định:** GPU dùng **512** (chất lượng cao nhất còn dùng được: 7,7 lần VOS/giây); nếu cần nhịp
cao hơn thì **320** (8,9 lần VOS/giây, mất 0,018 mIoU). CPU live giữ **192** (AGENTS §6).
**Chưa đổi model.** Mốc để Cutie phải vượt: **mIoU > 0,855** trên `binh2_tay` (0,8338 + ngưỡng nhiễu
~0,02); dưới mức đó thì đổi model không đáng.

- File thay đổi:
  - `scripts/bench_gpu_binh2.py` — quét `image_size`, chấm mIoU, `--stream`, tự `--stop-after-frames`,
    gộp artifact
  - `colab.ipynb` — notebook 6 ô (mới, gốc repo, tên ngắn để link Colab không bị cắt)
  - `gpu.ipynb`, `notebooks/colab_gpu_evaluation.ipynb` — đồng bộ

## 🐞 Vấn đề gặp phải & cách xử lý
- **"Chạy quài" 1–2 phút rồi Ctrl-C (2 lần)**: không phải model chậm — (a) `--stop-after-frames` thiếu
  ⇒ worker lặp vô hạn; (b) `--stream` dùng `subprocess.run` nên không in gì. Đã sửa cả hai + ghi vào
  AGENTS §6 để không lặp lại.
- **`git pull` báo `divergent branches`**: nhánh `colab-bench` bị force-push ⇒ nay notebook dùng
  `checkout -B <nhánh> origin/<nhánh>` (Colab không có gì cần giữ).
- **"Không mở được video file 'data/binh2.mp4'"**: `data/` bị `.gitignore` nên bản clone không có clip.
  Nay chặn ở cửa vào với hướng dẫn, và ô 3 của notebook tự mở hộp thoại `files.upload()`.
- **`mask_ngoai_gt_mean` = 0,052 ở 512** ⇒ ~5 % mask nằm NGOÀI GT (tràn), khác với chẩn đoán "hụt diện
  tích" ở 192. Ghi nhận, chưa xử lý.
- **`binh2_tay2` chỉ có `n=2` frame chấm được** ⇒ số 0,81 là bằng chứng YẾU, không trích như số chắc.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Chốt A/B **Cutie trên T4** — chỉ đáng làm nếu vượt mốc mIoU 0,855 (nếu không thì giữ SAM 2 @512).
- [ ] Tô thêm GT cho `binh2_tay2` (hiện 2 frame có vật) để cột đó có ý nghĩa thống kê.
- [ ] Đo đường **live** trên GPU @512 (`scripts/measure_live_relay.py`) — số ở đây là **batch**, không
      phải số live; demo webcam vẫn phải chạy CPU @192 (Colab không thấy webcam laptop).

## 📚 Tài liệu tham khảo
- SAM 2: https://github.com/facebookresearch/sam2 · SAMURAI: https://github.com/yangchris11/samurai
- `docs/thuoc-do-bam-dung.md` (quy tắc chấm mIoU: GT rỗng ⇒ không chấm; model rỗng ⇒ 0,0)
- AGENTS §6 (trần CPU, "Số 0,0 trong artifact là cạm bẫy", ngưỡng nhiễu theo ô chọn)
- AGENTS §9.2 (plan 3 ý kiến) — quyết định "đổi lõi sang Cutie" vẫn **chưa** chốt, cần plan trước khi code.
