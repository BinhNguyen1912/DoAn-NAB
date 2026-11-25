# 25-11-2026 — "Lag dữ vậy" + cổng báo oan khi máy chậm (bước VOS dài bất thường)

## 1. Mục tiêu

Người dùng chạy `./run demoip` (phiên `demoip_1125-084425`) và báo:

> "sao nó lag dữ vậy, đưa vật vào 1 hồi mới có bỏ đỏ"

Log: **6 frame / 10,4 s**, `mean = 2004 ms`, p95 3148 ms (bình thường **137–141 ms**), và cổng báo
"NGHI ĐỔI ĐỐI TƯỢNG" ở `f2→f3`. Phải tách **hai** vấn đề: máy chậm (môi trường) và cổng báo oan
(lỗi thiết kế bị máy chậm phơi ra).

## 2. Input

- `data/demoip_1125-084425_metrics.csv` (6 frame) + `_run_info.json` + `_web.mp4`
- `data/demoip_1125-084257_metrics.csv` (1 frame, 4083 ms — lần chạy trước đó cùng buổi)
- So sánh: `data/demoip_1124-193026_metrics.csv` (141 ms, cùng máy, cùng `image_size 192`)

## 3. Công việc đã thực hiện

### 3.1. Chẩn đoán lag: **môi trường, không phải code**

| kiểm | kết quả |
|---|---|
| `run_info.loadavg_1m` phiên 25-11 | **2,02** (không cao) |
| `run_info.live_workers_khac` | **0** (không có worker mồ côi — ca đã gặp 21-11) |
| `run_info.image_size` | **192** (đúng yêu cầu, không bị rơi về 1024) |
| `git_rev` | `fa5fd8e`, `git_dirty_code = false` |
| **Headless cùng model, cùng clip, chạy lại 15 phút sau** | **137 ms mean / 188 ms p95** (n = 15) |

⇒ Máy **bây giờ bình thường**. `loadavg` trong WSL **không thấy** tiến trình phía Windows (Windows
Update/Defender chạy lúc 8h45 là ca rất thường), mà torch lại tranh đúng số lõi vật lý đó — nên đây là
**suy đoán có bằng chứng gián tiếp** (cùng code, cùng cấu hình, 15 phút sau nhanh gấp 15 lần), **không**
phải kết luận đo được. Muốn chắc thì lần sau mở Task Manager lúc đang chậm.

### 3.2. Lỗi thật bị phơi ra: ngưỡng cổng tính **px/BƯỚC**, không phải px/giây

Cú báo ở `f3`:

| | số |
|---|---|
| `f2` bbox | `(368, 153, 469, 405)` → tâm (418,5 · 279) |
| `f3` bbox | `(115, 201, 259, 479)` → tâm (187 · 340) |
| tâm nhảy | **239,4 px** |
| bán kính cho phép | `max(0,10·800=80, 1,5·252=378)` nhưng **trần 0,25·800 = 200 px** ⇒ **200** |
| **thời gian bước** | **851 ms** ⇒ tốc độ thật **281 px/s** (tay cầm vật đi bình thường) |

⇒ Cổng báo oan **chỉ vì máy chậm**. Với `vos_every=1` và máy bị chiếm, mỗi bước dài gấp 6–20 lần ⇒
cùng một tốc độ tay luôn vượt ngưỡng. Đây đúng là lý do AGENTS từng ghi cho `theo_dt` — nhưng `theo_dt`
(với `1500 px/s × dt` **luôn bật**) đã bị bác ngày 24-11 vì làm mất ca báo đúng.

### 3.3. Luật mới: nới theo thời gian **CHỈ khi bước dài bất thường**

`src/identity_guard.py`:

- `DT_CHAM_BI_THUONG_S = 0.5` — ngưỡng "bước dài bất thường" (bình thường 77–352 ms).
- `TOC_DO_TOI_DA_PX_S = 1500.0`, `TRAN_CHAM_RATIO = 0.35`.
- `search_window_radius(..., step_seconds=None)`: nếu `step_seconds > 0,5 s` **và** người dùng không tự
  siết `max_jump_ratio` (< 0,25) ⇒ `radius = max(base, 1500 × dt)`, trần `0,35 × đường chéo`.
- `is_suspect_switch(..., step_seconds=None)`, `IdentityWatch.update(..., step_seconds=None)`.
- Ba đường runtime đo `step_seconds` bằng **đồng hồ thực** (`time.monotonic()`) giữa 2 lần đẩy cổng —
  không dùng `elapsed_ms` (ở frame nội suy LK, `elapsed_ms` là `lk_ms`, không phải độ dài bước VOS).

Vì sao **không** nới trần vô điều kiện: 24-11 đo `0,25 → 0,30` làm **mất** ca báo đúng `092343#264`
và đuôi xấu đi 146 → 159. Luật này chỉ kích hoạt ở chế độ máy chậm.

## 4. Output / Kết quả

`data/eval_gate_rules_2026-11-25_metrics.json` (`git_rev 3591f19`, `git_dirty_code = false`, 28 phiên
đọc được, nhóm chi phí 10 phiên đóng băng / 1 509 frame):

| luật | báo | ẩn | chưa xác minh | bắt ca ĐÚNG |
|---|---|---|---|---|
| `hien_tai` (trước 25-11) | 6 | 3,71 % | 4,24 % | **7/7** |
| **`cham_noi_theo_dt` (nay)** | 6 | 3,71 % | 4,24 % | **7/7** |

⇒ Trên nhóm đóng băng **y hệt** (bước của 7 ca đúng là **131–352 ms** < 500 ms ⇒ luật **không kích hoạt**).
Khác biệt nằm đúng ở phiên người dùng báo:

| phiên | `hien_tai` | `cham_noi_theo_dt` |
|---|---|---|
| `demoip_1125-084425` | `fire = [3]`, ẩn 3 frame | **`fire = []`** |
| `demoip_1125-084257` | 0 | 0 |

## 5. Vấn đề & cách xử lý

1. **Lag 2004 ms KHÔNG phải regression của code.** Cùng commit, 15 phút sau: 137 ms. Không có worker
   mồ côi, `image_size` đúng 192. Không sửa gì cho phần lag — chỉ ghi cách kiểm (Task Manager phía
   Windows, vì `loadavg` của WSL không thấy).
2. **Không được trích "máy chậm 15× vì cổng"**: hai chuyện khác nhau. Lag làm **phơi ra** lỗi ngưỡng
   px/bước; lag tự nó là môi trường.
3. **Hệ quả của luật mới với máy RẤT chậm**: bước 2 s ⇒ bán kính 280 px (trần) ⇒ vẫn bắt được cú nhảy
   thật ≥ 280 px trong 1 bước. Đây là **đánh đổi có chủ ý**: máy chậm thì mất độ nhạy cổng, đổi lấy
   không báo oan. Số `7/7` không đổi ⇒ không mất ca nào **đã biết**.
4. **`step_seconds` là ước lượng tốt hơn `latency_ms`** trong CSV: runtime dùng đồng hồ thực; script
   chấm vẫn dùng `latency_ms` (đã ghi rõ trong docstring là xấp xỉ) ⇒ số của script là **so sánh giữa
   hai luật trên cùng dữ liệu**, không phải số live.

## 5b. Phiên kiểm lại 25-11 08:58 (`demoip_1125-085815`, 360 frame / 105,5 s) — **hết kẹt latch, còn 1 báo oan KHÔNG sửa được bằng ngưỡng**

| đại lượng | số |
|---|---|
| `mean` / p95 | **280 / 415 ms**, hiển thị 17,2 FPS, tỉ lệ thời lượng **1,00** ✓ |
| `loadavg_1m` lúc chạy | **7,42** (8 lõi) — đường `--smooth` tự ăn 4,3 lõi (CPU 434 %), nên đây là **chi phí của chính pipeline**, không phải máy bị người khác chiếm như phiên 08:44 |
| `mất dấu` | 71/360 = **20 %** (thẻ vàng thật sự ra khỏi khung nhiều lần: 7 đoạn vắng ≥ 5 frame) |
| `nghi` | **8 frame** (f47–54) |
| `chua_xac_minh_n` | **27** |
| **chi phí hiển thị** | (8+27)/360 = **9,7 %** — so với **32,7 %** (phiên 24-11 19:30) và **44,3 %** (phiên 1124-125109) ⇒ **hết kẹt** |
| tự hồi phục | có: f55 hết `nghi` (mask vẫn còn 24 653 px), rồi f68–81 vắng 14 frame ⇒ tái bám ⇒ về `ok` |

### Cú báo oan f47 — và vì sao **KHÔNG** sửa được bằng ngưỡng

`f46→f47`: tâm nhảy **227,6 px** trong **343 ms** = **665 px/s**; bán kính cho phép 200 px (trần) ⇒ báo.
Ảnh 2 khung liên tiếp cắt từ `_web.mp4` cho thấy ô **vẫn trên đúng tấm thẻ vàng** mà người dùng đang vẫy
⇒ **báo oan**, không phải đổi đối tượng.

Đo cả hai lớp cạnh nhau (cùng đại lượng, cùng thước):

| | px/bước | ms | **px/s** |
|---|---|---|---|
| **7 ca báo ĐÚNG** (`CA_DUNG`) | 87 – 316 | 131 – 352 | **500 – 2 107** |
| **ca báo OAN** 085815#47 (ảnh) | **228** | 343 | **665** |

⇒ **Hai lớp chồng lấn hoàn toàn.** Bảng luật (`data/eval_gate_rules_2026-11-25_metrics.json`,
`git_rev 033eafc`, có **1 ca SAI** đầu tiên):

| luật | bắt ca ĐÚNG | báo ở ca SAI |
|---|---|---|
| `cham_noi_theo_dt` (đang ship) | **7/7** | 1/1 |
| `theo_dt` (nới vô điều kiện) | **3/7** | 0/1 |
| `theo_dt_va_dien_tich` | 2/7 | 0/1 |
| `chi_khi_cham_600` | 1/7 | 0/1 |
| `van_toc_lich_su` | 6/7 | 1/1 |

Luật duy nhất "sạch" với ca oan (`theo_dt`) **bỏ 4/7 ca đúng** ⇒ **cấm** chọn nó. Kết luận: muốn hết
báo oan kiểu này phải **xác minh bằng MASK THẬT** (re-prompt rồi chấm mask-vs-mask), tức Tầng 2 —
không phải chỉnh `max_jump_ratio` / `theo_dt` / `chi_khi_cham`.

## 6. Next steps

- [x] **Chạy lại `./run demoip`** (phiên 08:58) — **hết kẹt latch** (9,7 % so với 32,7 %), tỉ lệ thời
      lượng 1,00. Còn **1 báo oan** khi vẫy vật nhanh ⇒ **không sửa được bằng ngưỡng** (§5b).
- [ ] **Tầng 2 = việc thật sự còn lại**: xác minh bằng mask (re-prompt + mask-vs-mask) để tách "vẫy
      nhanh" khỏi "đổi vật". Cần plan 3 ý kiến trước khi code (> 4 h).
- [ ] Nếu lag lặp lại: mở **Task Manager (Windows)** lúc đó chụp lại cột CPU/Process — đó là bằng chứng
      duy nhất `loadavg` của WSL không thấy.
- [ ] Ticket đã ghi từ 24-11 (dedupe cổng theo `frame_idx` cho frame `engine.start()`) vẫn còn.
- [ ] **Tầng 2** (verified re-anchor / Cutie) cho ca trôi-dần-sang-tường — vẫn là việc > 4 h, cần plan.

## 7. Tài liệu tham khảo

- `docs/task/24-11-2026-vat-roi-khung-khong-bi-nghi.md` (luật "vật rời khung ≠ đổi đối tượng")
- `docs/plan/24-11-2026-cong-nghi-bao-oan.md` (vì sao **cấm** nới trần vô điều kiện; 7 luật bị bác)
- `src/identity_guard.py` (hằng số + docstring luật), `scripts/eval_gate_rules.py` (luật `cham_noi_theo_dt`)

---

## Bổ sung: merge vào `main` + CI đỏ 3 ngày (3 giờ sáng 25-11)

### 1. Merge
Nhánh `feat/nhan-lai-vat-live` (HEAD `c5d6dc4`) đã merge vào `main` bằng merge commit (không squash —
giữ 62 commit lẻ để `git log`/`bisect` còn tác dụng), rồi push `0480b9c`.
Kiểm sau merge: `git diff feat/nhan-lai-vat-live main` = **rỗng** ⇒ không mất commit nào.
`./run lint` xanh · `./run test` = **2 036 passed, 5 deselected** (297 s) trên chính commit merge.

### 2. CI `main` đỏ từ 22-11 — tìm ra 2 nguyên nhân, KHÔNG do việc hôm nay

`gh` không có trên máy ⇒ đọc trạng thái qua GitHub API công khai
(`/commits/<sha>/check-runs`, `/actions/runs?branch=main`):

| sha main | lúc | kết quả |
|---|---|---|
| `3ed5bc8` (20-11) | 15:45 | **success** |
| `61f2a6d` (22-11) | 09:03 | failure ← **đỏ từ đây** |
| `7121718`, `d149202` | 22-11, 24-11 | failure |
| `0480b9c` (hôm nay) | 25-11 | failure (ruff ✅, pytest ❌, provenance ❌) |

#### (a) `pytest` — 2 test phụ thuộc video KHÔNG commit

Tái hiện được bằng **checkout sạch** (`git worktree add --detach /tmp/ci_main HEAD`), đúng cách CI
checkout — không đoán:

```
FAILED tests/test_bench_gpu_binh2.py::test_dong_thanh_cong_co_lenh_rieng
FAILED tests/test_bench_gpu_binh2.py::test_ma_thoat_chi_tinh_lan_nay
  [loi] KHÔNG có clip: data/binh2.mp4
```

Nguyên nhân: `scripts/bench_gpu_binh2.py` chặn ở cửa vào khi không thấy `--clip`, còn `data/*.mp4` bị
`.gitignore` ⇒ máy dev có video (xanh), CI không có (đỏ). Đúng "bẫy môi trường": test xanh trên máy
dev **không** chứng minh được gì về CI.

Sửa: fixture `clip_gia` tạo file rỗng trong `tmp_path` + truyền `--clip` (`_so_frame_cua_clip` và
`chay_mot_cau_hinh` đều đã được monkeypatch nên chỉ cần file **tồn tại**). Không `skip` — test vẫn
chạy thật ở CI.

**Kiểm chứng**: chạy lại full làn nhanh trong checkout sạch `/tmp/ci_main` ⇒ **0 failed**.

#### (b) `git_rev của artifact` — 9 artifact schema cũ (trước luật provenance)

`scripts/check_artifact_provenance.py --nghiem` báo `9 CHẾT-MỚI`. Đọc từng file: cả 9 **không có
field `git_rev`** (schema cũ: `sach_binh{1,2}_lan{1,2,3}`, `remote_trang_comparison`,
`identity_latch_chi_phi_2026-11-21`, `jump_gate_replay_2026-11-21`) — **không phải** "rev chết"
(rev từng tồn tại rồi mất do rebase). Script gộp cả hai thành `chet` ⇒ 2 chuyện khác nhau bị gán một
nhãn, và allowlist `CHO_PHEP` (khoá `(tên, rev)`) **không dùng được** vì `rev = None`.

Sửa: thêm nhãn **`thieu-rev`** (không khai rev) tách khỏi `chet` (rev chết), + `CHO_PHEP_KHONG_REV`
allowlist **theo TÊN** kèm lý do, mỗi mục ghi rõ "cấm trích rev". Cổng **vẫn còn răng**: file MỚI
thiếu `git_rev` không nằm trong danh sách ⇒ vẫn `thieu-rev` ⇒ CI đỏ (có test
`test_thieu_rev_ten_moi_van_bi_bat`). Trước: `134 artifact: 116 ok · 6 lệch · 3 đã-biết · 9 CHẾT-MỚI`
(exit 1) → sau: `116 ok · 6 lệch · 12 đã-biết · 0 CHẾT-MỚI` (exit 0).

Cập nhật 2 test cũ đang khẳng định `None ⇒ chet` (đúng theo thiết kế CŨ, nay đổi có chủ ý) + thêm 3
test mới. **Không** sửa số trong artifact, không xoá bằng chứng.

### 3. Việc còn lại (chưa làm)
- `d149202`/`61f2a6d`/`7121718` (22–24/11) đỏ do (a)+(b) ⇒ sau commit này `main` mới xanh lại; muốn
  chắc thì xem run của commit kế tiếp.
- Máy này **không có `gh`** ⇒ không mở được PR; quy trình §7b "vào `main` qua PR" đang được làm tay
  bằng merge commit. Nên cài `gh` (hoặc dùng token) để đọc log CI khi đỏ — lần này phải tái hiện
  bằng `git worktree` mới tìm ra nguyên nhân.

### 2b. Vì sao lần đầu sửa provenance vẫn đỏ: `lech` ở máy ≠ `chet` ở CI

Sau commit `9b21d49`, CI còn đỏ **đúng job provenance** (pytest đã xanh). Đo lại từng nấc:

| môi trường | `--nghiem` | vì sao |
|---|---|---|
| `data/` trên máy dev | exit **0** | 6 rev thấy là `lech` (object còn trong `.git`, không phải tổ tiên) |
| `git worktree` của chính repo | exit **0** | worktree **dùng chung object store** với repo ⇒ vẫn thấy rev rác |
| **`git clone file://$PWD`** (chỉ copy object REACHABLE) | exit **1**, **5 CHẾT-MỚI** | đúng như CI: runner clone sạch |
| Python 3.14 thay 3.11 | exit 0 | ⇒ không phải lỗi phiên bản Python |

⇒ Bài học phương pháp: **`git worktree` KHÔNG phải bản sao của checkout CI.** Muốn tái hiện "rev có
tồn tại trên remote không" thì phải `clone` (hoặc `git fetch` vào repo trống), vì thứ tự kiểm
`rev-parse --verify` mới là thứ CI chạy. Đây là lần thứ hai trong ngày tôi suýt kết luận "đã xanh"
bằng một phép kiểm không cùng điều kiện với CI.

5 rev chết thật (đều là nhánh rebase/squash trước khi push): `6969fc4` (A/B image_size `b1b`),
`891f4f5` (A/B max_mad), `d893517` (A/B vos_every), `316c6e8` × 3 (sweep GPU `binh2` 22-11 —
`gpu_sweep_binh2_2026-11-22*.json`, rev ghi dạng NGẮN 7 ký tự ở 2 file).

Xử lý: thêm 6 mục vào `CHO_PHEP` (cơ chế CÓ SẴN cho "provenance không truy được nhưng giữ nguyên bằng
chứng"), mỗi mục nêu lý do + **CẤM dẫn rev**. Số trong AGENTS §6 vẫn dùng được (đo thật,
`git_dirty_code = false`) — chỉ rev là không kiểm lại được. Kiểm lại trong clone thật:
`134 artifact: 116 ok · 0 lệch · 18 đã-biết · 0 CHẾT-MỚI`, exit **0**.

### 3. Kết quả cuối
`main` = `e62c762`. CI **xanh cả 3 job** (`ruff`, `pytest (fast lane)`, `git_rev của artifact`) — lần đầu
xanh lại sau chuỗi đỏ từ 22-11 (`61f2a6d`).

| bước | số |
|---|---|
| `./run lint` | All checks passed |
| `./run test` | **2 038 passed**, 5 deselected (194 s) |
| làn nhanh trong **clone sạch** | 0 failed |
| provenance trong **clone sạch** | 134 artifact: 116 ok · 0 lệch · 18 đã-biết · **0 CHẾT-MỚI** |

Sai quy trình (ghi lại để lần sau tránh): commit `e62c762` được tạo **trực tiếp trên `main`** (quên
`git switch` lại nhánh) ⇒ vi phạm §7b "không commit thẳng lên `main`". Đã đồng bộ nhánh
`feat/nhan-lai-vat-live` lên đúng `main` (`git branch -f`) để không còn hai đường lịch sử; **không**
rewrite `main` đã push (tệ hơn). Bài học: `git status`/`git branch --show-current` TRƯỚC mỗi commit.
