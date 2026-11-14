# Ngày 14-11-2026 — `--frame-window` (tách "vật rời khung") + đổi mặc định ô chọn + sửa theo review

## 🎯 Mục tiêu
- Hai việc người dùng chốt: **(b)** để `empty_frac_window` không trộn "model mất dấu" với "vật đã rời
  khung"; **(c)** chốt clip + ô chọn cho demo và cho số đo. Kèm **(a)** đính chính `AGENTS.md` §6.
- Sửa hết phát hiện của vòng review độc lập §9.1 (2 P1 + 8 P2) trước khi merge.

## 📥 Input
- Log & plan cùng ngày: `docs/task/14-11-2026-do-lai-bbox-dung-ket-luan-khong-can-train-lai.md`,
  `docs/plan/14-11-2026-plan-3-y-kien-toi-uu-msi.md`, nhánh `docs/plan-toi-uu-va-audit-bbox`.
- Số nền (đã đo, `git_dirty_code=false`): ô mặt `binh1` → empty 0 %, drift 0,881–0,884; ô chai
  `binh1` → empty 36,0–36,7 % cả phiên nhưng **1,7–1,8 %** trong khung; ô chai `binh2` → 21,7–23,4 %
  nhưng **0,0 %** trong khung `0:160`; checkpoint `small` không hơn `tiny`; `image_size` 256/320 tệ hơn.
- Máy: MSI, WSL2, CPU; `./run lint`, `./run test` chạy được.

## 🔨 Công việc đã thực hiện
1. **`src/drift_samples.py`**: thêm `thong_ke_mau(rows)` + `tach_theo_cac_khung(rows, danh_sach_khung)`
   (và `tach_theo_khung` làm wrapper một khung). Mẫu chưa đo (`empty`/`drift_iou` = `None`) không vào
   mẫu số; khung rỗng ⇒ `None` (không phải 0); mẫu không có `frame_idx` → `khong_ro_khung`.
2. **`scripts/measure_live_relay.py`**: cờ `--frame-window dau:cuoi` (**lặp được** — `binh1` có 2 đoạn
   `0:110` và `165:262`), hàm thuần `_parse_frame_window()`, `_so_frame_clip()`/`_so_vong()`; artifact
   thêm `cua_so_frame {khung, trong_khung, ngoai_khung, khong_ro_khung, so_frame_clip, so_vong,
   ghi_chu}`; in 2 dòng + **cảnh báo khi nguồn file bị lặp** (`so_vong > 1,1`).
3. **`scripts/analyze_drift_samples.py`**: thêm `--frame-window` → tái lập các số "trong khung" **từ CSV
   đã commit**, không cần chạy lại model.
4. **`scripts/make_frame_sheet.py`** (mới) + commit ảnh kiểm `docs/media/frames/binh{1,2}_bbox_*.jpg`
   (mỗi 25 frame, có vẽ ô chọn) — bằng chứng khung frame được chọn **trước** khi xem kết quả.
5. **Đổi mặc định `--bbox`** của 3 script đo từ ô mặt `104,308,209,287` sang ô chai:
   `benchmark_light_trackers.py`, `measure_watchdog.py` = `300,275,150,410` (x,y,w,h);
   **`profile_stages.py` = `300,275,450,685`** vì script đó parse `x1,y1,x2,y2`.
   `tests/test_script_default_bbox.py` khoá cả hai định dạng + test "ô không suy biến" (rộng/cao dương).
6. **`AGENTS.md` §6**: đính chính bullet "hybrid chỉ giữ được ô bao trên một số clip" + bullet mới
   "mất dấu phải tách khỏi vật rời khung" (kèm số và đường dẫn).
7. **`docs/demo-clip-va-o-chon.md`** (mới): bảng clip + ô + khung, lệnh đo chuẩn, quy tắc trích số,
   chuẩn bị demo, lệnh sinh lại ảnh kiểm.
8. **Sửa ví dụ bbox cũ** trong `README.md`, `docs/cheatsheet-lenh.md`, `run` (help), `docs/colab-gpu.md`.

## 📤 Output / Kết quả
- `./run lint`: **All checks passed**. `./run test`: **937 passed, 5 deselected** (trước phiên: 906).
- Chạy thật 2 lần trên cây sạch (`git_dirty_code=false`, đúng **1 vòng** clip):
  - `data/sach_chai_binh1_1vong_metrics.json` — `so_vong` **0,95**; `trong_khung` n = 64 ·
    **rỗng 1,6 %** · `drift_iou` 0,4895 (n_drift 61); `ngoai_khung` n = 40 · rỗng 90 %.
  - `data/sach_chai_binh2_1vong_metrics.json` — `so_vong` **0,93**; `trong_khung` n = 50 ·
    **rỗng 0,0 %** · `drift_iou` 0,726 (n_drift 50); `ngoai_khung` n = 64 · rỗng 34,4 %.
- File thay đổi (chính): `src/drift_samples.py`, `scripts/measure_live_relay.py`,
  `scripts/analyze_drift_samples.py`, `scripts/make_frame_sheet.py`, `scripts/profile_stages.py`,
  `scripts/benchmark_light_trackers.py`, `scripts/measure_watchdog.py`, `AGENTS.md`, `README.md`,
  `docs/cheatsheet-lenh.md`, `docs/colab-gpu.md`, `run`, `docs/demo-clip-va-o-chon.md`,
  `docs/media/frames/*.jpg`, `tests/test_script_default_bbox.py`, `tests/test_drift_samples.py`,
  `tests/test_measure_live_relay.py`.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Review vòng 1 bắt 2 P1 mà tôi tự không thấy:**
  1. `profile_stages.py` parse `x1,y1,x2,y2`, nên đặt mặc định `300,275,150,410` tạo hộp **rộng âm**
     (`x2 < x1`) — đúng loại lỗi "hộp cao âm" đã từng làm hỏng một pha đo. Test khoá-chuỗi của tôi
     **che mất** lỗi này. Đã sửa + thêm test "ô không suy biến".
  2. Một khung liên tục là **sai thực tế**: `binh1` có 2 đoạn vật trong khung, và nguồn file bị **lặp**
     (55 s trên clip 11 s = 4,49 vòng) ⇒ nhãn "ngoài khung = vật đã rời" là sai. Đã cho lặp cờ, ghi
     `so_vong`, đổi câu chữ, và cảnh báo khi lặp.
- **Bài học lặp lại trong cùng một ngày:** cả 3 lỗi lớn (ô trên mặt, "mất dấu" là vật rời khung, hộp
  âm) đều chỉ lộ ra khi **nhìn ảnh** hoặc khi **có người thứ hai đọc code**. Vì vậy kỳ này commit luôn
  ảnh kiểm vào `docs/media/` thay vì để file tạm trong `data/` (bị gitignore).
- **Số sai phải sửa:** `empty` cả phiên của chai là **36,0–36,7 %** (không phải 35,0–36,3 %);
  `image_size 256` cho drift **0,34–0,36** (`data/res256_chai_binh1_lan{1,2}` = 0,3545/0,3587;
   `data/lan2_chai_binh1_256_lan1` = 0,3408) — đừng ghi 0,34 như một con số duy nhất; `binh2` dùng khung **`0:160`** (không phải `0:140`).
- **Artifact bẩn:** lần đo đầu tiên có `git_dirty_code=true` (do thư mục rác `D:/` + code chưa commit)
  ⇒ không được trích; đã đo lại trên cây sạch sau khi commit.
- `drift_iou` ở `ngoai_khung` **không dùng được** làm số (mẫu rỗng chi phối) — đã ghi rõ trong doc.

## 🔎 Review độc lập (AGENTS.md §9.1)
- **Vòng 1**: agent `reviewer` (read-only, không phải phiên đã code), phạm vi commit `a750f7f`.
  Kết quả: **0 P0 · 2 P1 · 8 P2 · 3 P3** — chi tiết ở bảng dưới. Không merge trước khi sửa.
  - P1-A: hộp rộng âm ở `profile_stages.py` (trộn `xywh`/`xyxy`).
  - P1-B: một khung liên tục + nhãn "ngoài khung = vật đã rời" sai khi nguồn lặp.
  - P2: `0:-5` không bị từ chối; `cua_so_frame = null` gộp "không hỏi" với "không có mẫu";
    số trong doc lệch artifact (36,0–36,7; 0:160; 256 = 0,35); số "trong khung" không tái lập được từ
    artifact đã commit; khung frame không có bằng chứng trong repo; 1 artifact trích bị `git_dirty_code`;
    artifact cũ mất tính tái lập vì đổi default bbox; thiếu log phiên.
  - P3: ví dụ bbox cũ còn trong README/cheatsheet/`run`/colab; test chưa phủ phần nối artifact;
    số `image_size 320` ghi 0,29 (thực 0,28–0,32).
- **Vòng 2**: agent `reviewer` thứ hai (read-only), phạm vi `git diff a750f7f..HEAD`.
  **Kết luận: ĐỒNG Ý MERGE — cả 2 P1 vòng 1 đóng đúng, 0 P0/P1 mới.** Reviewer kiểm bằng cách suy luận
  từng ca revert (revert `profile_stages.py` về `300,275,150,410` ⇒ test "ô không suy biến" đỏ; revert
  `min(nums)<0` ⇒ test `0:-5` đỏ; revert `thong_ke_mau` trả `0.0` ⇒ test khung rỗng đỏ) và mở ảnh
  `docs/media/frames/binh1_bbox_300-275-150-410.jpg` để xác nhận khung `0:110 ∪ 165:262` khớp nội dung.
  - **3 P2 còn lại — đã đóng trong cùng PR (commit `a9d114d`)**: `docs/tom-tat-do-an.md` vẫn viết
    "binh2 lỗi ở model"; 3 comment code còn "0,0 % trong khung"; artifact lần đo bẩn
    `data/khung_chai_binh1_lan1_metrics.json` vẫn nằm trong nhánh.
  - **11 P3 — đã sửa hết**: in khối khung khi không có CSV; `so_vong` dùng max(frame phát, frame worker)
    (lệch 316 vs 335); `_so_frame_clip` trả `None` khi nguồn là 1 ảnh; thêm hàm thuần
    `_gop_khung`/`_canh_bao_lap` + test (trước đó revert `action="append"` vẫn xanh); test khung chồng
    nhau; `ValueError` khi không khai khung nào; notebook Colab `BBOX`; số `256` = 0,34–0,36; nhãn cột
    `mask/s`.
  - Test sau khi đóng review: `./run lint` xanh · `./run test` **950 passed** (đầu phiên: 906).
- Mọi P2/P3 **đã sửa trong cùng PR** (không để nợ), trừ mục notebook Colab (chưa đụng vì có test
  `tests/test_notebook_colab.py`) — ghi vào Next steps.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Chạy review vòng 2 và xử lý kết quả (nếu có P1 ⇒ sửa ngay; P2 ⇒ ticket).
- [ ] Mở PR cho nhánh `docs/plan-toi-uu-va-audit-bbox` (máy này không có `gh` CLI): so sánh, mô tả, CI xanh.
- [ ] Sửa `BBOX` mặc định trong `notebooks/colab_gpu_evaluation.ipynb` (ô chai) + cập nhật
      `tests/test_notebook_colab.py`.
- [ ] Dùng `--frame-window` cho **mọi** lần đo mới; số cũ (`data/lan2_*`, `data/obj_*`) phải ghi kèm
      "ô mới nhưng không có khung" khi trích.
- [ ] Việc còn treo của plan: nhãn điểm thưa (`recall_in`/`precision_out`), HUD tuổi mask + badge mất
      dấu, `./run democheck`, media demo, `so-lieu-bao-cao.md` sinh từ artifact.

## 📚 Tài liệu tham khảo
- `docs/demo-clip-va-o-chon.md` — nguồn sự thật về clip + ô + khung frame.
- `docs/task/14-11-2026-do-lai-bbox-dung-ket-luan-khong-can-train-lai.md` — số đo gốc + kết luận
  "không train lại model".
- `docs/plan/14-11-2026-plan-3-y-kien-toi-uu-msi.md` — plan §9.2 (3 góc nhìn + phản biện).
- `AGENTS.md` §4, §6 (bảng số đã đo), §9.1 (review độc lập), §9.4 (checklist kết thúc phiên).
- Artifact: `data/sach_chai_binh{1,2}_1vong_metrics.json`, `data/lan2_*_metrics.json`,
  `data/drift_samples_*_2026-11-14_*.{csv,meta.json}`, ảnh `docs/media/{bbox,frames}/*.jpg`.

## 🔁 Bổ sung cùng phiên — việc #4 của plan: tách CHU KỲ VOS (đóng hướng cadence bằng số)

### Đã làm
- `src/tracker_engine.py`: `TrackingResult.pre_ms` (thời gian tiền xử lý), đo **riêng** — KHÔNG cộng
  vào `elapsed_ms` để mọi số `vos_ms` cũ vẫn so được.
- `src/live_tracking.py`: hàm thuần `_tach_pha()` → `queue_ms` (frame chờ trong worker),
  `cycle_ms` (1/`vos_fps` thực), `idle_ms` (luồng chờ frame); worker ghi mốc `submit`;
  `_note_mask_age()` nhận `queue/pre/post`; `_age_window` lưu **từng mẫu** `(total, cu)`.
- `status.json` thêm `pre_ms`, `queue_ms`, `post_ms`, `cycle_ms`, `idle_ms`, `mask_age_cu_ms`;
  `measure_live_relay.py::_worker_telemetry` chép các khoá này vào artifact.
- 7 test mới: `TestTachPhaChuKyVos` (3), `TestTuoiMaskTachKhoan` (2), allowlist `status.json`,
  reader của bài test lock hiểu mẫu dạng tuple.

### Số đo — **3 lần** (`data/chu_ky_chai_binh1_1vong_lan{1,2,3}_metrics.json`, 1 vòng `binh1`, @192,
`vos_every 3`, `git_dirty_code=false`)
| Pha | ms | Ghi chú |
|---|---|---|
| Pha | 3 lần (min–max) | Ghi chú |
|---|---|---|
| `vos_ms` (model) | **83,6–103,1** | chỉ phần propagate |
| `pre_ms` (tiền xử lý) | **11,6–13,1** | ~12 % chu kỳ — resize PIL + stack tensor |
| `post_ms` (drift + làm mượt) | 0,08–0,98 | |
| `queue_ms` (frame chờ worker) | **2,1–75,9** | ⚠️ **không** phải ≈0: một lần đo đầu ra 0,33 ms là **may**, n=3 mới thấy dải thật |
| `idle_ms` (luồng chờ frame) | 0,01–16,8 | |
| `cycle_ms` | **101,5–121,6** | = `1/vos_fps` (9,2–9,7 mask/s) |
| `mask_age_cu_ms` (định nghĩa cũ) | 131,6–182,0 | age + vos |
| `mask_age_total_ms` (tuổi dữ liệu thật) | 167,9–267,0 | queue + pre + vos + post + age |
| `mask_age_p95` (theo từng mẫu) | 268,7–301,2 | của cửa sổ 200 mẫu |

⚠️ Các pha là **mẫu hiện tại** (giống `vos_ms`), không phải trung bình phiên ⇒ tổng 4 pha có thể
lệch `cycle_ms` vài ms; muốn trung bình thì phải cộng thêm cửa sổ (chưa làm).

### Kết luận (đóng 2 câu hỏi đang treo)
1. **"Đổi cadence cho nhanh hơn" KHÔNG phải nút thắt** — nhưng **không** phải vì "queue ≈ 0": n=3 cho
   `queue_ms` 2,1–75,9 ms (một lần đo n=1 từng ra 0,33 ms ⇒ tôi đã kết luận sai và tự bác bằng 3 lần
   đo). Lý do đúng: `cycle ≈ vos_ms + pre_ms` (101–122 vs 84–103 + 12–13) ⇒ tăng tần suất gửi frame
   chỉ làm `queue` dài thêm, không làm mask mới hơn.
2. **Chỗ còn cắt được là tiền xử lý 11,6–13,1 ms** (~12 %), không phải phần sau model (post < 1 ms):
   `np.ascontiguousarray` → `cv2.cvtColor` và `pil.resize` → `cv2.resize` (ticket riêng — **không**
   bit-identical nên phải đo chất lượng trước khi nhận).
3. **Hai định nghĩa tuổi mask** đã tách: `mask_age_cu_ms` (so với số trước 14-11: 271–273 ms) và
   `mask_age_total_ms` (tuổi dữ liệu thật). Không được trộn hai số trong một bảng.

`./run lint` xanh · `./run test` **955 passed**.

## 📊 Bổ sung — việc #10 của plan: `docs/so-lieu-bao-cao.md` SINH từ artifact

- `scripts/so_lieu_bao_cao.py`: registry "tuyên bố → artifact + đường dẫn khoá" ⇒ sinh bảng markdown
  6 cột (Tuyên bố · Số · Đơn vị · Artifact · Khoá · **CẤM trích thành**). Không chép tay con số nào.
- `docs/so-lieu-bao-cao.md` (13 dòng) gồm: `vos_ms`/`vos_fps`/tuổi mask (2 định nghĩa)/chu kỳ + pha/
  `queue_ms`/tỉ lệ rỗng **trong khung** (binh1, binh2)/`drift_iou` trong khung/`so_vong`/mIoU fixture/
  watchdog.
- `--check` để CI báo khi file lệch artifact (test đã khoá: file sửa tay ⇒ mã thoát 1).
- Test `tests/test_so_lieu_bao_cao.py` (14 test): `None` in **`null` (chưa đo)**, thiếu artifact/khoá in
  **`THIẾU`**, cả hai **không bao giờ** in `0`; mọi dòng registry phải trỏ được tới khoá có thật; 2
  artifact chính phải có `git_dirty_code == false`.

`./run lint` xanh · `./run test` **969 passed**.

## 🔎 Review độc lập vòng 3 (4 commit cuối) + tự bác một kết luận

Agent `reviewer` thứ ba, phạm vi `git diff 53576fb..HEAD` (telemetry pha + `so_lieu_bao_cao`).
**Kết quả: 0 P0 · 1 P1 · 4 P2 · 9 P3.** Đã sửa hết trong cùng nhánh (`ab18c8b`, `14561ae`):

- **P1**: `README.md` gán số của **định nghĩa cũ** (210–250 ms) cho **tên** `mask_age_total_ms` (nay là
  tuổi dữ liệu thật) — doc-regression do chính PR này gây ra ⇒ tách 2 định nghĩa, nêu số mới
  (268,7–301,2 ms, n=3).
- **P2 — kết luận của tôi SAI vì n=1**: tôi đã ghi "queue ≈ 0 ⇒ bỏ hẳn hướng cadence". Đo lại **3 lần**
  cho `queue_ms` **2,1–75,9 ms** (lần đầu 0,33 ms là may). Kết luận đúng: `cycle ≈ vos_ms + pre_ms`
  ⇒ tăng tần suất gửi frame chỉ làm queue dài thêm; nút thắt là **model (84–103 ms) + tiền xử lý
  (12–13 ms)**. Đã sửa `AGENTS.md`, plan, log, registry và **xoá artifact n=1** khỏi nhánh.
- **P2**: test p95 trước đó **không có răng** (dùng `queue_ms=500` nên cách cũ vẫn xanh) → đổi sang
  `vos_ms=500` (revert cơ chế ⇒ đỏ) + assert `age_n`.
- **P2**: `--check` chưa nối CI ⇒ thêm test "doc đã commit == `build_document()`".
- **P3 đã sửa**: `pre_ms` mặc định `None` (engine không đo ⇒ `null`, không phải `0,0`); gom
  `pre/queue/post` vào **cùng snapshot** `_vos_state` (trước đó trộn pha 2 lần chạy: chênh 30,8 ms);
  `post_ms` đo từ đầu `_store_vos` (gồm cả `_measure_stability`); registry in kèm `n`; test provenance
  parametrize **mọi** artifact trong registry; ghi rõ tên file `sach_lap27vong` thực ra là 2,71 vòng.

`./run lint` xanh · `./run test` **978 passed**.
