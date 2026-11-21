# 21-11-2026 — Veto "nhận lại vào KHUÔN MẶT/ĐẦU" + siết ngưỡng re-ID (tập trung bám VẬT)

## 1. Mục tiêu

Người dùng sau 3 phiên demo webcam: *"thấy chưa ổn, tập trung vào vật đi"* — hệ phải bám **VẬT** (bình
vàng), không được nhận lại vào **mặt/trán/đầu** người. Sửa có số đo, không đổi cảm tính.

## 2. Input

- Phiên demo thật: `data/demoip_1121-080547_metrics.csv` + `data/demoip_1121-080547_web.mp4`
  (714 frame video @30 FPS · **221 frame suy luận** · `image_size 192` · `vos_every 3`).
- Hiệu chuẩn cũ: `data/reid_2clip_calib.json` (01-11): 17 ca nhận lại **ĐÚNG** (ncc 0,415–0,741,
  cosine 0,770–0,975) + 1 ca **SAI** (cosine 0,899 / ncc 0,279).
- Ca sai mới: 20-11 vào **MẶT** (cosine 0,974 / ncc 0,545); 21-11 vào **TRÁN** (0,734 / 0,423) và vào
  **ĐẦU** (0,663 / **0,356**).
- `src/face_guard.py` (`BoDoMat` = YuNet, fail-open) — đã có sẵn từ cảnh báo ô chọn phủ mặt.

## 3. Công việc đã thực hiện

### 3.1. Đính chính chẩn đoán trước (bắt buộc, vì nó làm sai hướng sửa)

Ảnh `demoip3_giua/cuoi.jpg` trước đó tôi gán nhãn f133/f175/f205 theo **frame video 30 FPS**, không phải
frame suy luận (~7/s) ⇒ kết luận "ô chọn có 2 ứng viên nên nó đổi ứng viên" là **SAI**. Quy đổi ×3,23 rồi
đọc lại đúng vùng mất dấu (`data/anh_tmp/demoip3_matdau.jpg`, video frame 662–711):

| suy luận | ảnh | kết luận |
|---|---|---|
| f205–f207 | ô + mask trên **bình vàng** | bám đúng |
| f209–f211 | ô trượt, mask mất → `MẤT DẤU — TỰ TÌM LẠI` | |
| f211 | nhận lại **TRÁN/TÓC** (0,734 / 0,423) | sai |
| f215 | nhận lại **ĐẦU** (0,663 / 0,356) | sai |
| f218–f220 | bám **cái đầu** tới hết phiên | sai vật |

### 3.2. Siết ngưỡng re-ID trên đường demo (`run demoip`)

| | cũ | mới | chặn được |
|---|---|---|---|
| `--reid-obj-ncc-min` | 0,35 | **0,40** | ca vào ĐẦU (ncc 0,356 — chỉ hơn ngưỡng cũ **0,006**) |
| `--reid-obj-threshold` | 0,60 (default config) | **0,75** | ca vào TRÁN (0,734) và vào ĐẦU (0,663) |

Kiểm lại trên tập 18 ca có nhãn (`data/reid_2clip_calib.json`, bằng script tính trực tiếp):

| ngưỡng | nhận đúng | lọt sai | chặn oan |
|---|---|---|---|
| 0,60 / 0,35 (cũ) | 17/17 | 0/1 | 0 |
| **0,75 / 0,40 (mới)** | **17/17** | **0/1** | **0** |

**Biên rất hẹp, phải nói rõ**: `min_good` cosine 0,770 vs ngưỡng 0,75 = **0,020**; ncc 0,415 vs 0,40 =
**0,015**. Đây là "cắt được ca sai đã gặp", **không** phải "ngưỡng tối ưu" — ca đúng mới với cosine 0,755
sẽ bị chặn. Ghi vào `data/reid_ca_sai_vao_mat_2026-11-20_calib.json`.

### 3.3. Veto cấu trúc: không nhận lại vào MẶT/ĐẦU (phần quan trọng nhất)

Ngưỡng điểm **không bao giờ** cứu được ca vào MẶT: ncc 0,545 nằm **giữa** dải ca đúng (0,415–0,741) ⇒
không có ngưỡng nào tách. Nhưng có một thông tin **miễn phí** chưa dùng: **ô chọn ban đầu của người dùng
không phủ mặt** (chính `face_guard` đã nói đúng, IoU 0,76) ⇒ vật cần bám không phải mặt người ⇒ ứng viên
trùm mặt là **sai theo định nghĩa**.

- `src/reid.py`:
  - `ReIdSession(..., face_veto=None)` — duck-type `BoDoMat` (`.detect(frame) -> [(x,y,w,h)]`), `None` = tắt.
  - `_phu_mat(frame, bbox)`: phần diện tích **lớn nhất** của ô ứng viên bị MỘT mặt phủ (0..1), fail-open
    (tắt veto / không có mặt / ô suy biến ⇒ 0,0).
  - `_trung_mat(frame, bbox)`: `True` nếu **TÂM ô nằm trong một mặt** (không có ngưỡng để hiệu chỉnh) **hoặc**
    `_phu_mat ≥ NGUONG_PHU_MAT = 0,30`.
  - `start()` ghi `_ref_phu_mat` = ô chọn ban đầu có phủ mặt ⇒ **người dùng chọn đúng mặt thì veto im lặng**
    (không chặn oan người muốn bám mặt).
  - Cue vật thể: ứng viên bị `_trung_mat` ⇒ **bỏ**, ở lại `MẤT DẤU — TỰ TÌM LẠI` (thà không vẽ ô còn hơn vẽ
    lên mặt người), vẫn ghi `reid_score`/`ncc` để hiệu chuẩn, đếm `veto_mat_n`, in `HINT_VETO_MAT` lần đầu
    + mỗi 20 lần.
- `tools/run_live.py`: bơm `face_guard.BoDoMat()` khi `cue ∈ {object, both}`; cờ `--no-reid-face-veto`
  để tắt. Thiếu model/opencv ⇒ `None` (như cũ), in dòng xác nhận khi bật.

## 4. Output / Kết quả

| Kiểm tra | Kết quả |
|---|---|
| `./run lint` | All checks passed |
| `./run test` | **1648 passed**, 5 deselected (105 s) |
| Test veto mới (`tests/test_reid.py::TestVetoNhanLaiVaoMat`) | **5 passed** |
| `--reid-face-veto` hiện trong `--help` | ✓ |
| `BoDoMat().detect(None)` | `[]` (fail-open) |

5 test mới khoá đúng hành vi:
1. `_phu_mat` tính đúng phần diện tích (ô = mặt ⇒ 1,0; ô vật ⇒ 0,0; ô suy biến ⇒ 0,0 fail-open).
2. Ứng viên trùm mặt **bị bỏ** khi ô chọn không phải mặt (`veto_mat_n == 1`, vẫn ở `reacquiring`).
3. Ô ứng viên TO hơn mặt (phủ < 0,30) nhưng **tâm nằm trong mặt** ⇒ vẫn bỏ (không cần ngưỡng).
4. **Tắt veto ⇒ vẫn nhận nhầm như cũ** (chứng minh veto là thứ cứu được, không phải test tự thoả mãn).
5. Ô chọn **phủ mặt** ⇒ veto **im lặng**, vẫn nhận lại (không chặn người muốn bám mặt).

### Mặc định `./run demoip` sau phiên này

```
--reid-cue object --reid-obj-ncc-min 0.40 --reid-obj-threshold 0.75 --image-size 192
```
(`--image-size 192`: đo 21-11 — 320 cho latency mean/p95 **360/430 ms**, 192 cho **140/157 ms** = 2,5×.)

## 5. Vấn đề & cách xử lý

- **Test veto ban đầu fail 3 lần**: (a) frame test sai kích thước engine giả `(120,260)`; (b) trộn hệ
  `(x,y,w,h)` với `(x1,y1,x2,y2)` — `reid` dùng **xyxy** còn `face_guard` dùng **xywh** (đúng lỗi đã gặp
  08-11); (c) `_match_object` thật không tìm ra ứng viên ở khoảng cách đó (bán kính tìm hẹp) ⇒ **stub**
  `_match_object` để test đúng tầng veto. Bài học: muốn test một tầng thì phải cắt tầng dưới, đừng để
  cascade NCC quyết định kết quả test.
- **Không tái lập được phiên bằng replay**: `_web.mp4` là video ĐÃ VẼ overlay ⇒ không dùng làm nguồn để
  A/B ngưỡng. Vì vậy ngưỡng được kiểm trên tập nhãn cũ (17+1) chứ không phải "chạy lại phiên này".
- **Chưa hiệu chuẩn `NGUONG_PHU_MAT = 0,30`**: CSV cũ **không ghi w/h** của ô ứng viên ⇒ không tính được
  phần phủ của đúng ô đã nhận nhầm. Ghi nợ: thêm `bbox_w/bbox_h` vào CSV để lần sau hiệu chuẩn được.

## 6. Next steps

- [ ] Thêm `bbox_w/bbox_h` vào `metrics_csv` (hiện chỉ có `center_x/center_y`) ⇒ mới hiệu chuẩn được
      `NGUONG_PHU_MAT` và đo "ô vẽ khi không có vật" trên `gt_rong`.
- [ ] Người dùng chạy lại `./run demoip` (mặc định mới) — nếu thấy bị **chặn oan** (không nhận lại được dù
      vật ở đó) thì `--no-reid-face-veto` và ghi lại frame.
- [ ] Ca vào MẶT (ncc 0,545) hiện chỉ được chặn nhờ veto ⇒ **không** được bỏ veto khi demo.
- [ ] Ticket #41 (binh2 bám sang vật khác) dùng chung cơ chế veto này — cần kiểm riêng.

## 7. Tài liệu tham khảo

- `docs/task/21-11-2026-demo-webcam-lan-2-o-chon-chinh-la-khuon-mat.md` (đã thêm mục ĐÍNH CHÍNH số frame).
- `data/reid_ca_sai_vao_mat_2026-11-20_calib.json` (thêm 2 ca sai + phần "kết luận hiệu chuẩn").
- AGENTS.md §6 (dòng: ô chọn `(x,y,w,h)` ≠ `(x1,y1,x2,y2)`; "đo trước, hứa sau").
