# 21-11-2026 — Veto "nhận lại vào KHUÔN MẶT/ĐẦU" + siết ngưỡng re-ID (tập trung bám VẬT)

## 1. Mục tiêu

Người dùng sau 3 phiên demo webcam: *"thấy chưa ổn, tập trung vào vật đi"* — hệ phải bám **VẬT** (bình
vàng), không được nhận lại vào **mặt/trán/đầu** người. Sửa có số đo, không đổi cảm tính.

## 2. Input

- Phiên demo thật: `data/demoip_1121-080547_metrics.csv` + `data/demoip_1121-080547_web.mp4`
  (714 frame video @30 FPS · **221 frame suy luận** · `image_size 192` · đường CLI — `vos_every`
  chỉ có ở worker live, không phải tham số của `tools/run_live.py`).
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
| `--no-reid-face-veto` hiện trong `--help` | ✓ |
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

## 5b. Kết quả REVIEW ĐỘC LẬP (vòng 1, commit `564dcb0`/`cd20582`) — 0 P0, 3 P1

Reviewer (agent `reviewer`, chỉ đọc) bắt **3 P1** đều đúng, đã sửa hết trong `546932a`:

| Mức | Phát hiện | Đã sửa |
|---|---|---|
| **P1** | Veto bỏ **cả frame** chứ không bỏ **ứng viên**: `_match_object` chỉ trả ô tốt nhất, veto ô đó rồi `bbox=None` ⇒ nếu **MẶT xếp hạng trên vật thật** (đo: mặt cosine 0,9739 > ca đúng thấp nhất 0,770) thì vật nằm trong top-20 nhưng **không bao giờ được xét** ⇒ kẹt `reacquiring` vô hạn dù vật đang trong khung | Lọc ứng viên **bên trong** `_match_object` (detect 1 lần, `continue` sang ứng viên kế tiếp) + **backstop** ở `step()`; test mới dựng đúng 2 ứng viên (mặt ncc 1,0 đứng trước, vật 0,9) ⇒ phải nhận ô **vật** |
| **P1** | **HUD nói ngược**: veto vẫn để `reid_score` = điểm ứng viên đã bỏ ⇒ in `khop 0.90 / can 0.75` ⇒ người xem hiểu "đủ điểm mà không nhận = hệ hỏng" | `Step.vetoed` + `reid_vetoed` xuyên `visualizer`/`smooth_display`/`live_pipeline` ⇒ in `BO: ung vien trung KHUON MAT`; 2 test HUD (có veto ⇒ có chữ KHUON MAT, **không** có "can 0.7"; không veto ⇒ vẫn in "khop X / can Y") |
| **P1** | **Thiếu test chiều âm**: mutant "hễ `_ref_phu_mat=False` là veto tất cả" **pass cả 5 test** | Thêm test ứng viên **không** trùng mặt ⇒ `reacquired=True`, `veto_mat_n == 0` |
| P2 | Test "chỉ 1 lần YuNet" **không giết được** bản 2-detect (ô test nằm trọn trong mặt nên bản cũ cũng return sau 1 detect) | Đổi sang ô **không** phủ mặt ⇒ bản 2-detect sẽ ra 2 lần gọi |
| P2 | Veto không có provenance: `run_info` không ghi, `veto_mat_n` không rời session, CSV `latency_ms` của frame lost = 0 ⇒ artifact trước/sau **trông y hệt** | `_finish_outputs(..., reid_session)` ⇒ `run_info` có `reid_face_veto` + `reid_veto_mat_n`; in số veto cuối phiên |
| P2 | `_ref_phu_mat` là quyết định **một frame** (YuNet min_score 0,6 trượt lúc chọn ⇒ veto bật cả phiên) | **sticky**: giữ `_ref_bbox`, nếu về sau mặt phủ ≥30 % ô chọn ban đầu ⇒ `_ref_phu_mat=True`, tắt veto |
| P2 | Không test nào cho **nối cờ** `--no-reid-face-veto` | 3 test: bật ⇒ có `face_veto`; `--no-…` ⇒ `None`; `cue=face` ⇒ `None` (tự chặn mình) |
| P3 | `run:300` in "chặn vào mặt 0,545" — **sai**: 0,545 ≥ 0,40 và cosine 0,974 ≥ 0,75 ⇒ ca MẶT **chỉ** bị veto chặn | Sửa echo + nói rõ ca mặt chỉ bị veto chặn |
| P3 | `reset()` không xoá `_ref_phu_mat`/`veto_mat_n` dù docstring hứa "về trạng thái ban đầu" | Xoá cả 4 field trong `reset()` |
| P3 | In "veto đã bật" cả khi **thiếu** `.onnx` (`BoDoMat` lười, `detect()` trả `[]`) ⇒ clone mới tưởng có bảo vệ | Chỉ in dòng bật khi `os.path.isfile(model)`; thiếu thì in "TẮT THẬT" + hướng dẫn tải |
| P3 | Log ghi cờ `--reid-face-veto`, cờ thật là `--no-reid-face-veto`; ghi `vos_every 3` cho đường CLI (CLI không có tham số này) | Đã sửa trong log này |

**Reviewer cũng xác nhận "đã kiểm, không phải lỗi"** ở 3 chỗ tôi nghi:
- Hệ toạ độ **không** trộn: `reid` xyxy, `face_guard` xywh, chỗ nối đổi đúng (`fx+fw`), cả hai chiều đều có test.
- Cờ `--no-reid-face-veto` **không** bị `configs/default.yaml` đè (`merge_cli_overrides` không có key này) và `run demoip "$@"` đứng sau ⇒ cờ người dùng tới được argparse.
- Khi `r` chọn lại giữa phiên thì `start()` **có** chạy lại (`smooth_display.py:187`, `live_pipeline.py:294,320`) ⇒ không có `_ref_phu_mat` cũ.
- Số trong log khớp artifact: `reid_2clip_calib.json` 18 ca (17 good + 1 bad), `min_good` cosine 0,76957 / ncc 0,414731; CSV `demoip_1121-080547` f207–f215 khớp từng giá trị.

## 5c. REVIEW VÒNG 2 (commit `546932a`) — 0 P0, **3 P1**, đã sửa trong `1a35fc8`

| Mức | Phát hiện (đều ĐÚNG) | Đã sửa |
|---|---|---|
| **P1** | `reid_session` **không** khởi tạo trước `try` ở cả `_run_display`/`_run_headless` ⇒ `finally` ném `UnboundLocalError`, **che lỗi thật** + bỏ `cv2.destroyAllWindows()`. Ca thật: `--reid --reid-cue face` thiếu model (clone mới) ném `SystemExit(1)` có hướng dẫn ⇒ người dùng chỉ thấy traceback | Thêm `reid_session = None` trước `try` ở cả 2 hàm; test `TestKhongNuotLoiBangUnboundLocalError` — **đã kiểm ngược**: bỏ dòng khởi tạo ⇒ test FAIL, khôi phục ⇒ pass |
| **P1** | `run_interactive` (`--display --reid`, **không** `--smooth`) không gán `reid_vetoed` ⇒ HUD không bao giờ nói lý do veto, và vì `reid_score=-1` còn in **chẩn đoán sai** "chua co ung vien — kiem tra vat chon co cham mep khung" | Gán ở nhánh re-ID + nhánh else + nhánh bấm `r`; test `TestCoVetoToiHudOHaiDuong` (session giả trả `Step(vetoed=True)` ⇒ `visualizer.update` phải nhận `True`) |
| **P1** | Ứng viên bị veto **không đóng góp điểm** (`continue` trước `object_signature`) ⇒ CSV `reid_score/ncc = -1`, **trùng** giá trị "không có ứng viên" ⇒ **không hiệu chuẩn được** `NGUONG_PHU_MAT` (đúng thứ ta cần) | Chấm rồi mới bỏ (thêm ~1,4 ms **chỉ khi có veto**), trả điểm ô bị bỏ khi không còn ứng viên khác; **thêm cột `vetoed`** vào CSV (`FrameRecord` + `metrics_logger`) để đọc được bằng artifact |
| P2 | `step()` backstop gọi YuNet **lần 2** trên cùng frame (~29 ms), mà nhánh đó gần như **không thể chạm tới** | Cache khuôn mặt theo **đối tượng frame** (`_faces_frame is frame`) ⇒ 1 lần detect/frame; test `FakeMat.calls == 1` cho cả `step()` |
| P2 | `reset()` **không** xoá `_ref_phu_mat`/`_ref_bbox` (log vòng 1 nói đã sửa — **sai**) | Xoá (giữ `veto_mat_n` vì là bộ đếm cả phiên, đã ghi rõ trong docstring); test `test_P2_reset_xoa_quyet_dinh_veto` |
| P2 | Sticky `_ref_phu_mat` **một chiều, im lặng, không test** | Chấp nhận nhưng ghi nợ có tên (xem dưới) — chưa sửa trong phiên này |
| P3 | `print(HINT_VETO_MAT)` dựa `veto_mat_n == 1` ⇒ **im lặng** nếu 1 frame veto ≥ 2 ô | Đổi sang `so_veto_truoc == 0` |
| P3 | Print "xem cột `state` trong CSV" — **bất khả** (mọi frame tìm lại đều `reacquiring`) | Nay có cột `vetoed` thật ⇒ câu đó đúng |
| P3 | Test `assert "can 0.7" not in hud` **rỗng nghĩa** (không set `reid_threshold`) | (nợ — xem dưới) |

**Artifact chứng minh được GÌ** (review vòng 3 bắt đúng là heading cũ nói quá):
`data/veto_demo_21-11_metrics.csv` chứng minh **(a)** cột thứ 11 `vetoed` tồn tại và **(b)** frame tìm
lại có `latency_ms` **thật** (121,8 · 58,8 · 70,3 · 125,2 ms ở lần chạy trên cây sạch).
**KHÔNG** chứng minh "chấm điểm ô bị veto": không có dòng `vetoed = 1` nào (`reid_veto_mat_n = 0`) vì
clip `binh1` không có mặt trong vùng tìm. Muốn chứng minh phải có **phiên webcam thật** (còn nợ).

## 5d. REVIEW VÒNG 3 (commit `1a35fc8`) — **0 P0, 0 P1 ⇒ mergeable**, 3 P2 + 6 P3

Reviewer xác nhận cả 3 P1 vòng 2 đã sửa **đúng** và **không hồi quy** đường không-re-ID (kiểm cả
`_annotate`/`_record_from`/`_run_headless`). Đã sửa tiếp trong `5e960bc` + `a0ac012`:

| Mức | Phát hiện (đều ĐÚNG) | Đã sửa |
|---|---|---|
| **P3-D** (nay là lỗi **provenance thật**) | `_write_run_info` đọc `args.reid_reacquire_confirm`/`reid_verify_frames`, nhưng `main()` gán `reid_confirm`/`reid_verify` ⇒ **MỌI `data/*_run_info.json` từ trước tới nay ghi `null`** | Đọc đúng tên (fallback tên cũ) ⇒ nay `reid_reacquire_confirm: 2`, `reid_verify_frames: 2` |
| **P2-C** | `veto_demo_21-11_run_info.json` ghi `git_rev ee3058a` mà CSV đã có cột `vetoed` (commit sau) ⇒ đo trên **cây bẩn**, và `run_info` **không có** `git_dirty` | Thêm `git_dirty` **+ `git_dirty_code`** (bẩn bỏ qua `data/` — vì chính file artifact làm cây bẩn, đúng quy ước `measure_watchdog`); đo lại ⇒ `git_rev a0ac012`, `git_dirty_code: false`; 3 test |
| **P2-A** | Print cuối phiên vẫn dặn "xem cột `state`" — bất khả (mọi frame tìm lại đều `reacquiring`); log lại khẳng định câu đó đúng | Đổi sang cột `vetoed` (=1) |
| **P2-B** | Test "1 lần YuNet cho `step()`" **không giết được** mutant bỏ cache (vì `_match_object` đã truyền `faces=`, và backstop **không chạm tới được**) | 3 test khoá **đúng hợp đồng cache** (cùng frame 1 detect · frame mới detect lại · `reset()` xoá cache); ghi rõ backstop là hàng rào không reachable |
| P3-A | Đường `--smooth` (demo chính `./run demoip`) **không có test nào** chạm `reid_vetoed` | `TestCoVetoQuaInferenceWorker` — **đã kiểm ngược**: gán cứng `False` ⇒ FAIL |
| P3-B | Nhánh chọn ô không reset `reid_vetoed` (bất biến ngầm) | Reset tường minh ở cả 2 nhánh chọn ô |
| P3-C | `so_veto_truoc == 0` = "veto đầu **cả phiên**" (vì `reset()` giữ `veto_mat_n`) ⇒ sau khi bấm `r`, hint không in | Cờ riêng `_hint_veto_da_in`, xoá trong `reset()` |
| P3-E | `veto_mat_n` chỉ đếm ứng viên **đã qua cổng NCC** ⇒ là **cận dưới**; ca "vào ĐẦU" (ncc 0,356) bị cổng 0,40 loại trước nên **không** được đếm là veto | Ghi chú ngay trong code + đây |
| P3-F | Bản vá `reid_session = None` ở `_run_display` không có test | `TestKhongNuotLoiOHienThi` (thiếu model ⇒ `SystemExit(1)` **và** `destroyAllWindows` vẫn chạy) |

### Nợ còn lại (reviewer nêu đúng, xử lý ở phiên sau)
- **Chạy thật đầu tiên với cấu hình mới** — nay đo lại trên CÂY SẠCH (`git_rev a0ac012`,
  `git_dirty_code: false`); số cũ `git_rev ee3058a` là **cây bẩn**, đã bị thay (review vòng 3, P2-C) — **trên CLIP `data/binh1.mp4`,
  KHÔNG phải webcam**: `data/veto_demo_21-11_{metrics.csv,summary.json,run_info.json}`, 120 frame,
  `image_size 192`, `--reid-obj-ncc-min 0.40 --reid-obj-threshold 0.75 --bbox 300,275,150,410`:
  mean **109 ms** (n=116) / p95 **125 ms** · mất dấu **5/120 (4 %)** · `reid_face_veto: true`,
  `reid_veto_mat_n: **0**` (clip này không có mặt trong vùng tìm ⇒ veto không kích hoạt, đúng như mong
  đợi — **không** phải bằng chứng "không chặn oan trên webcam"). Frame tìm lại có latency **thật**
  thay vì 0,0. ⇒ **Vẫn còn nợ**: 1 phiên webcam thật ~60 s có `reid_veto_mat_n > 0` mới chứng minh
  được veto hoạt động và không chặn oan.
- ~~`latency_ms` của frame `lost`/`reacquiring` ghi **0.0**~~ → **đã sửa cùng phiên**: nhánh LOST đo
  `time.perf_counter()` và gán `lost.elapsed_ms` ⇒ CSV/summary nay có chi phí **tìm lại** (cascade NCC
  ~28 ms + YuNet ~29 ms khi veto) — tách khỏi `vos_ms` của model; test `test_frame_tim_lai_co_elapsed_ms_that`.
- `NGUONG_PHU_MAT = 0,30` vẫn **chưa hiệu chuẩn** (CSV thiếu `bbox_w/bbox_h`).
- ADR-0004 chưa ghi "cổng thứ 4: veto mặt/đầu" và ngưỡng demo 0,75/0,40.

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
