# Ngày 13-11-2026 — Colab T4 lần 2 (mục 8): đường live chạy được trên GPU, nhưng số CHẤT LƯỢNG không dùng được vì bbox trỏ nền

## 🎯 Mục tiêu
- Chạy lại mục 8 của `notebooks/colab_gpu_evaluation.ipynb` trên Colab T4 (lần 1 ngày 12-11 **thất bại**:
  `worker dừng khi khởi động (mã 1)`, không có số GPU nào) để lấy số cho **ticket 21 phần 2**: chọn mặc
  định `image_size` / `vos_every` theo thiết bị.
- Kiểm luôn 2 fix của ngày 12-11 có tác dụng trên Colab: lệnh worker không còn đòi conda (`a30cca7`) và
  artifact mang `worker_log`/`api_log` để tự chẩn đoán.

## 📥 Input
- 2 artifact người dùng tải từ Colab (đã đổi tên để **không lọt vào Git**, vì không dùng được cho báo
  cáo): `data/colab_t4_2026-11-13_live_512_bbox_sai.json`, `data/colab_t4_2026-11-13_live_192_bbox_sai.json`
  (`git_rev = 58770a3` = `main` hiện tại, `git_dirty_code = false`).
- Lệnh trong artifact:
  `python scripts/measure_live_relay.py --source data/input.mp4 --bbox 104,308,209,287 --device cuda
  --image-size {512,192} --vos-every 3 --seconds 30 --out data/live_{512,192}_metrics.json`
  (trên Colab sinh ra 2 file cùng tên; khi tải về đã đổi tên ở trên để khỏi lẫn với artifact cũ 12-11)
- Tái lập trên máy này (CPU) với clip tổng hợp của `src/synthetic_video.py` + đúng bbox đó để kiểm giả
  thuyết "clip sai", dùng `scripts/measure_live_relay.py`. Artifact:
  `data/repro_bbox_tro_nen_cpu_2026-11-13_metrics.json` (`git_rev = 633bdcf`, `git_dirty_code = false`,
  `device_worker_log = cpu`, nguồn `data/input_tong_hop_60f.mp4` = 60 frame 1280×720 sinh bằng đúng tham
  số cell 3b: `square_size=120, start=(200,200), velocity=(14,6)`) + dãy mẫu
  `data/drift_samples_input_tong_hop_60f_2026-11-13_140724.csv` (233 dòng, `drift_iou` trung bình 0,126).
  Clip đó = `data/input.mp4` do cell 3b sinh (60 frame 1280×720, 25 fps, ô vuông 120 px ở `200,200`,
  vận tốc `14,6`); bản dùng để đo đã đổi tên `data/input_tong_hop_60f.mp4` (bị `.gitignore` chặn,
  sha256 `5d1a54914d6c67dee6be3c27012c1ee3391fcca7052636ee99224ac8e586739c`, 60 frame) — muốn tái lập thì chạy cell 3b rồi đổi tên như vậy.

## 🔨 Công việc đã thực hiện
1. Đọc 2 artifact: `ket_qua = true`, `device_worker_log = cuda`, `git_dirty_code = false` ⇒ **lần đo này
   hợp lệ về đường ống** (khác hẳn lần 12-11 thất bại). Kiểm `worker_status` để lấy `vos_ms`/`lk_ms`/
   `mask_age_p95` (những số **không** đi qua API live).
2. Nghi vấn chất lượng: `drift_iou` 0,203 (512) / 0,346 (192) và `stability` 0,27 / 0,35 — trong khi đo
   trên CPU với **cùng model, cùng `image_size 192`** trên `data/binh1.mp4` cho `drift_iou` 0,86 và
   `stability_shown` **0,88** (13-11, 3 file `live_web_relay_2026-11-13_1256…`) / **0,95–0,96** (10-11,
   3 file `live_gpu_device_cpu_baseline_run1..3_2026-11-10_metrics.json`). Chênh quá lớn ⇒ kiểm clip.
3. **Tái lập trên CPU** (artifact lưu ở `data/repro_bbox_tro_nen_cpu_2026-11-13_metrics.json`): sinh lại
   đúng clip tổng hợp của notebook (60 frame, 1280×720, ô vuông frame 0 ở `200,200`, vận tốc `14,6`) rồi
   chạy `measure_live_relay` với bbox `104,308,209,287`/`image_size 192`: được **`drift_iou = 0,118`,
   `stability_shown = 0,389`** ⇒ **cùng kết luận** với Colab (0,203–0,346 / 0,271–0,351) — *cùng kết
   luận*, **không** trùng giá trị (0,118 nằm ngoài khoảng đó; SAM 2 không tất định + máy khác) — nghĩa là
   cả hai đều **≪ mức 0,86/0,88 trên `binh1`** ⇒ sai là do **ô chọn**, không phải do GPU.
4. Nguyên nhân gốc: cell 3b của notebook **tự sinh** `data/input.mp4` (clip ô vuông tổng hợp) nếu file
   chưa có, nên lần chạy này dùng clip tổng hợp chứ không phải `binh1.mp4`; bbox `104,308,209,287` khi đó
   rơi vào **nền** (ô vuông ở `200,200`–`320,320`).
5. Sửa để không lặp lại:
   - Notebook mục 8 tách thành 3 cell: **8a** kiểm video (in `WxH`, số frame, fps) + bbox (assert trong
     khung, vẽ `data/bbox_check.jpg` để mắt người xác nhận, **cảnh báo khi là clip tổng hợp** 1280×720
     ≤ 120 frame); **8b** chạy **2 lần/cấu hình** (SAM 2 không tất định) đặt tên `live_<size>_lan<N>_metrics.json`;
     **8c** in `vos_ms`/`vos_fps`/`lk_ms`/`mask_age_p95`/`drift` + `device_worker_log` và tải về.
   - `docs/colab-gpu.md`: cảnh báo cell 3b tự sinh clip tổng hợp + phải mở `bbox_check.jpg`.
   - `AGENTS.md` §6: thêm kết luận "bbox trỏ nền ⇒ artifact vẫn `ket_qua=true` mà drift 0,1–0,35".
6. Không commit 2 artifact này: số chất lượng trong chúng **không dùng được** cho báo cáo (bbox sai), và
   repo đã có tiền lệ phải xoá artifact GPU hỏng khỏi `main` (12-11).

## 📤 Output / Kết quả

Môi trường: **Colab T4 GPU**, `--device cuda`, `device_worker_log = cuda` (worker thật dùng GPU),
`git_rev = 58770a3`, `git_dirty_code = false`, `data/input.mp4` = **clip tổng hợp 60 frame 1280×720**.

| Cấu hình | `vos_ms` | `vos_fps` | `lk_ms` | `mask_age_p95` | `measured_fps` <br>(`worker_status`, mẫu cuối) | `mask_fps_max` | `drift_iou` | `stability` |
|---|---|---|---|---|---|---|---|---|
| `image_size 512` | **63,8 ms** | 6,5 | 16,49 | 234,8 ms | 25,6 | 10,4 | 0,203 ⚠ | 0,271 ⚠ |
| `image_size 192` | **43,5 ms** | 10,1 | 4,27 | 138,8 ms | 30,0 | 10,8 | 0,346 ⚠ | 0,351 ⚠ |

(n = **1 lần/cấu hình** ⇒ chênh lệch 1,47× chưa đối chiếu được ngưỡng nhiễu — AGENTS §6: `n < 2` thì
chưa kết luận "tốt hơn"; đó là lý do cell 8b nay chạy 2 lần/cấu hình.)

⚠ = **không dùng được** (bbox trỏ nền — xem mục 🐞). Số dùng được:

- **Đường GPU qua API live đã chạy được trên T4**: `device_worker_log = cuda`, `state_cuoi = running`,
  804–810 frame trong 30 s, `empty_runs = 0`.
- **Độ trễ model trên T4**: `vos_ms` **43,5 ms @192** và **63,8 ms @512** ⇒ 512 chậm hơn **1,47×**
  (n = 1/cấu hình, xem caveat ở bảng). So với CPU trên **cùng clip tổng hợp** (`data/repro_bbox_tro_nen_cpu_…`:
  `vos_ms` **83,2 ms** @192): T4 nhanh hơn **~1,9×**. Với `binh1.mp4` (clip KHÁC) CPU cho `vos_ms`
  **118,0 / 124,0 / 125,7 ms** (`data/live_web_relay_2026-11-13_125634|125739|125844_metrics.json`)
  ⇒ tỉ lệ khi đó là 2,7–2,9×, nhưng **so hai clip khác nhau** thì chỉ để định hướng. Lưu ý `vos_ms`
  là **mẫu cuối** của phiên (dao động 79–113 ms trong một phiên) nên đừng trích tỉ lệ tới 2 chữ số.
  Cả hai phép so đều là **hai máy khác nhau** — không phải A/B.
- **`mask_fps` KHÔNG phân biệt được 512 với 192**: cả hai chạm trần `display_fps / vos_every` ≈ 10 lần/giây
  (10,4 vs 10,8; `1/vos_ms` = 15,7 và 23 lần/giây ⇒ model còn dư) ⇒ muốn so `image_size` phải dùng
  **`vos_ms`**, không dùng `mask_fps`.
  **Suy ra (chưa đo):** trên GPU, `vos_every` mới là nút chặn nhịp mask, khác CPU nơi model chậm hơn
  `vos_every` (`mask_fps` ≈ `vos_fps` 6,1–6,6). Muốn nói chắc phải **chạy `vos_every` 1/2/6 trên T4** —
  đã ghi ở Next steps, chưa làm.
- **`lk_ms` tăng theo `image_size`**: 4,27 → 16,49 ms (×3,9) — chi phí LK + dời mask lớn hơn, và trên VM
  Colab CPU yếu hơn laptop nên `measured_fps` tụt 30,0 → 25,6 ở 512.
- **`mask_age_p95`** (tuổi dữ liệu ảnh người xem thực thấy): **138,8 ms @192** vs **234,8 ms @512**.
- Kiểm tra trên máy này: `./run lint` xanh (chỉ sửa notebook/docs, không đổi code) — `notebook` đọc lại
  bằng `json.load` hợp lệ, 15 cell; cell kiểm video/bbox đã chạy thử headless trên clip tổng hợp và bắt
  đúng cảnh báo "clip tổng hợp ⇒ bbox đúng là 200,200,120,120".
- File thay đổi:
  - `notebooks/colab_gpu_evaluation.ipynb` — mục 8 thành 3 cell (guard bbox + 2 lần/cấu hình + in số;
    8b `assert DA_KIEM_8A` để "Run all" không bỏ qua bước kiểm)
  - `tests/test_notebook_colab.py` — 5 test cấu trúc notebook (không cần model)
  - `docs/colab-gpu.md` — cảnh báo clip tổng hợp / `bbox_check.jpg`
  - `AGENTS.md` §6 — bài học "bbox trỏ nền vẫn cho `ket_qua=true`"
  - (không vào Git: 2 artifact Colab đã đổi tên thành `data/colab_t4_2026-11-13_live_*_bbox_sai.json`
    — tên không khớp whitelist `data/*_metrics.json` nên `data/*` chặn, tránh lặp lại lỗi `git add -A`
    ngày 12-11 đưa artifact hỏng vào `main`)

## 🐞 Vấn đề gặp phải & cách xử lý
- **Số chất lượng vô nghĩa dù artifact "ĐẠT"**: `ket_qua = true` chỉ nói *đường ống* chạy (running, có
  frame, có mask) — **không** nói ô đang bám có phải vật hay không. Đây đúng lỗ hổng mà `_verdict` của
  `measure_live_relay` không thể bịt (nó không biết nội dung video). Cách bịt: bước **kiểm bằng mắt** ở
  cell 8a (ảnh `bbox_check.jpg`) + cảnh báo tự động khi phát hiện clip tổng hợp.
- **Vì sao không phát hiện ngay từ đầu**: người dùng đã làm đúng yêu cầu (đổi `--bbox` thành
  `104,308,209,287`) nhưng **cell 3b đã tự sinh** `data/input.mp4` trước đó ⇒ video không phải `binh1`.
  Bài học: khi hướng dẫn người khác chạy đo, phải yêu cầu **in ra nhận dạng clip** (độ phân giải + số
  frame), không chỉ đưa số bbox.
- **Tái lập giả thuyết bằng CPU trước khi kết luận** (2 phút) đã đổi phán đoán từ "GPU bám tệ" (claim
  sai) thành "ô chọn sai" (đúng) — đúng tinh thần AGENTS §6.
- Lần chạy này **không** còn lỗi `worker dừng khi khởi động (mã 1)` của 12-11 ⇒ 2 fix hôm đó (conda +
  log trong artifact) đã xử lý đúng.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Chạy lại mục 8 với video THẬT**: upload `data/binh1.mp4` thành `data/input.mp4` (phải thấy cell 8a
      in `720x1280 | 333 frame`), giữ `BBOX = "104,308,209,287"`, `LAN = (1, 2)` ⇒ 4 artifact
      `live_{512,192}_lan{1,2}_metrics.json`. Mở `data/bbox_check.jpg` xác nhận ô xanh bao đúng người.
- [ ] Khi có 4 artifact đó: so `vos_ms` giữa 512 và 192 (ngưỡng nhiễu lấy từ 2 lần lặp), rồi mới chốt mặc
      định `image_size` cho `device=cuda` trong `src/api/main.py` (ticket 21 tiêu chí 2).
- [ ] Trong báo cáo, nếu trích số GPU phải ghi kèm `device_worker_log` + tên GPU (T4) và nêu rõ clip đo;
      **không** trích `drift_iou` từ 2 artifact ngày 13-11 này.
- [ ] Cân nhắc thêm vào `measure_live_relay.py` một cờ `--bbox-check <ảnh>` để chụp frame 0 + vẽ bbox vào
      artifact (hiện chỉ có ảnh `frame*.jpg` sau khi bám) — chưa làm vì ngoài phạm vi phiên này.
- [ ] Heuristic "clip tổng hợp" của cell 8a dựa vào `1280×720 và ≤120 frame` ⇒ một video **thật** rất ngắn
      (≤ 4 giây) sẽ bị chặn oan (đường thoát: đặt `CHO_PHEP_CLIP_TONG_HOP = True`, đã ghi trong thông
      báo lỗi). Chấp nhận trong phiên này vì mặc định an toàn; nếu thấy vướng thì nhận diện bằng nội
      dung (màu ô vuông) thay vì kích thước.
- [ ] `vos_ms` là **mẫu cuối** của phiên (không phải trung vị) — muốn con số chắc hơn cho báo cáo thì
      lấy `vos_ms` từ dãy `drift_samples_*.csv` (có từng dòng) hoặc thêm trung vị vào `status.json`.

## 📚 Tài liệu tham khảo
- `docs/task/12-11-2026-ticket-21-thiet-bi-live-xuyen-chuoi-api-hud.md` — lần đo Colab thất bại 12-11
- `docs/task/10-11-2026-duong-live-chay-duoc-tren-gpu.md` — số CPU baseline 3 lần + đường GPU của live
- `docs/colab-gpu.md` — hướng dẫn notebook; `notebooks/colab_gpu_evaluation.ipynb` mục 8
- `.scratch/camera-ai-realtime/issues/21-…` — ticket 21 (phần 2 đang chờ số GPU trên clip thật)
