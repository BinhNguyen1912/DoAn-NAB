# 21-11-2026 · Ticket #39 — nối chẩn đoán LK (`last_ly_do`/`last_ly_do_khop`/`n_diem`) ra `shown.csv` + `status.json`

## 1. Mục tiêu

Chẩn đoán LK thêm ở PR #65 (`last_ly_do`, `last_ly_do_khop`, `last_scale`, `last_angle_deg`) sống **trong
tiến trình** ⇒ suốt 3 vòng review phải **suy từ đường code** để trả lời "vì sao frame X không có ô", và
một lần suy sai thành "LK mất dấu" (thực ra `_seed` rỗng vì bbox VOS suy biến). Ticket này đưa chúng ra
artifact + thêm `n_diem` (số điểm theo dõi được) để phân biệt "cổng MAD chặn vì tản" với "quá ít điểm".

## 2. Input

- `src/light_tracker.py` (field chẩn đoán, chưa có `n_diem`).
- `src/live_tracking.py` (`_result_threaded`, `_ghi_o_hien_thi`, `_update_stats_locked`, `status_payload`).
- `scripts/ab_o_hien_thi_vs_gt.py` (`doc_shown`, `cham`, artifact `schema`).
- GT người tô `docs/gt/b1b` (7 frame giữa khe VOS), clip `data/binh1.mp4`, ô chai `300,275,150,410`.

## 3. Công việc đã thực hiện

| Nơi | Thay đổi |
|---|---|
| `src/light_tracker.py` | thêm `last_n_diem` (reset `None` đầu bước; `0` khi `seed_rong`/`lk_hong`; `keep.sum()` sau LK) |
| `src/live_tracking.py` | snapshot `_chan_doan_frame` **ngay sau** `update()`; đường `vos_every=1` xoá nó (LK không áp dụng) |
| `LiveTrackStats` | thêm `chan_doan_lk: dict` (chẩn đoán của **frame gần nhất**, có `frame_idx`) — `None` khi chưa có bước LK |
| `_ghi_o_hien_thi` | CSV từ 6 → **11 cột**: thêm `ly_do,ly_do_khop,scale,angle_deg,n_diem` ở **cuối**; ô không đo được để **trống** (không ghi `0`) |
| `scripts/ab_o_hien_thi_vs_gt.py` | `doc_chan_doan()` + `COT_CHAN_DOAN`; `cham(chan_doan=…)` thêm `ly_do_dem`/`ly_do_khop_dem`/`n_diem_median`; `schema` **5 → 6**; mỗi lần chạy khai `csv_thieu_cot` |
| tests | 3 test cho `doc_chan_doan`/`cham` + 2 test cho CSV/status; mở allowlist `status.json` cho `chan_doan_lk` |

**Tương thích ngược** (ràng buộc của ticket): CSV 6 cột (mọi artifact trước 21-11) ⇒ `doc_chan_doan` trả
`None` cho từng cột + `thieu` = cả 5 tên ⇒ artifact khai `csv_thieu_cot`; `cham()` trả `ly_do_dem = None`
(CHƯA ĐO), **không** phải `{}` hay `0`.

## 4. Output / kết quả (số đo trên CÂY SẠCH)

Artifact: `data/ab_chan_doan_lk_2026-11-21_metrics.json` — `git_rev 9ce467b`, **`git_dirty false`,
`git_dirty_code false`**, `schema 6`, `so_lan_chay_loi 0/0`, `csv_thieu_cot []`.

Lệnh: `python scripts/ab_o_hien_thi_vs_gt.py --gt docs/gt/b1b --clip data/binh1.mp4 --bbox
300,275,150,410 --max-mad 1.5 100 --lan 1` (@192, `vos_every 3`).

| cấu hình | IoU(ô hiển thị, ô GT) | `ly_do_dem` (7 frame GT) | `ly_do_khop_dem` | `n_diem` median | `csv_thieu_cot` |
|---|---|---|---|---|---|
| `1,5/shift` | 0,5914 (tệ nhất 0,3848) | **`mad_du`: 6 · `ok_shift`: 1** | `{}` (đo được, 0 mẫu) | **54** | `[]` |
| `100/shift` | 0,7844 (tệ nhất 0,5649) | `ok_shift`: 7/7 | `{}` | 58 | `[]` |

⇒ **Trả lời được câu hỏi mở của ticket #38 bằng SỐ**: ở `max_mad = 1,5`, **6/7** frame GT bị từ chối vì
**cổng MAD** (`mad_du`), **không** frame nào vì `seed_rong`; lúc từ chối vẫn còn **54/64** điểm theo dõi ⇒
"cửa quá chặt", không phải "mất dấu".

⚠ **`--lan 1` ⇒ không có ngưỡng nhiễu**: chênh IoU giữa hai mức **không** được dùng để kết luận mức nào
tốt hơn (artifact tự ghi `phan_biet_duoc: null`). Số ở bảng này chỉ để chứng minh **dụng cụ chẩn đoán
hoạt động**; A/B 3 lần/cấu hình là việc của ticket #40.

⚠ So với lần chạy **trên cây bẩn** trước đó (`1,5` → IoU 0,6396, `mad_du` 7/7), lần này là 0,5914 và
`mad_du` 6/7 — **SAM 2 không tất định** (AGENTS §6) ⇒ đừng trộn số hai lần. Lần chạy cây bẩn đã **xoá** (`git rm data/tmp_39_metrics.json` — bản đầu chỉ `rm` trong một chuỗi lệnh
mà lệnh trước đó lỗi nên `&&` chặn mất, file vẫn được commit; reviewer vòng 2 bắt đúng). **File vẫn lấy
được từ lịch sử git** tại `a994147` (`git show a994147:data/tmp_39_metrics.json`) — nếu thấy nó ở đó thì
đó là số **cây bẩn**, **KHÔNG** trích; nay `data/tmp_*` đã vào `.gitignore`;
mọi số trích trong tài liệu phải lấy từ artifact có `git_dirty_code false` ở trên.

**Không chậm thêm**: đo riêng hai lần 200 frame (@192, `vos_every 3`, cùng clip/ô): `measured_fps` **29,8**
khi bật `--dump-shown-csv` và **29,8** khi tắt (ngưỡng nhiễu ±0,3 % = ±0,09 FPS). Hai lần chạy này **không**
để lại artifact (chỉ đọc `status.json`) ⇒ là số của log, không phải số trích từ artifact; artifact
`ab_chan_doan_lk_…` ghi `measured_fps 30,0` cho **300** frame — khác số frame nên đừng trộn. `status.json` có `chan_doan_lk`
(vd `{"ly_do":"mad_du","ly_do_khop":null,"n_diem":53,"khop":false,"lk_ok":false,"frame_idx":199}`)
**kể cả khi không bật dump**.

Kiểm máy: `./run lint` xanh · `./run test` **1598 passed** (sau 3 vòng review: 2 P1 + 1 P1 + 6 mục).

## 5. Vấn đề & cách xử lý

1. **`res["shown"]` là `str`** trong `main()` ⇒ `doc_chan_doan(res["shown"])` nổ `AttributeError: 'str'
   object has no attribute 'exists'` (4 test của `ab_o_hien_thi_vs_gt` đỏ ngay). Sửa: `Path(res["shown"])`.
   Bài học: test cũ xanh vì `doc_shown` bị **monkeypatch** thành fake nhận `str` ⇒ đường thật chưa từng
   được chạy với `str`.
2. **`status.json` có allowlist khoá** (`test_status_duoc_ghi_moi_frame`): khoá mới **phải** khai, nếu
   không test đỏ — đúng thiết kế (typo `vos_fsp` từng lọt nếu chỉ kiểm superset). Đã thêm `chan_doan_lk`.
3. **Ô trống ≠ `0`**: dòng CSV không có LK (`vos_every=1`) phải để trống cả 5 ô; ghi `0` cho `n_diem`
   sẽ đọc thành "0 điểm theo dõi được" — đúng bẫy AGENTS §6. Test kiểm bằng `not rows[1]["n_diem"]`.

## 6. Next steps

- Ticket #40 (A/B `max_mad` trên `binh2`) **cần GT người tô trước** — dụng cụ đã sẵn (`ly_do_dem`).
- Khi đã có `ly_do_dem` nhiều phiên, có thể hỏi tiếp: bao nhiêu % `lk_ok=false` là `mad_du` (nới cổng được)
  vs `seed_rong`/`thieu_diem` (phải sửa nguồn ô VOS, nới cổng vô ích).
- Chưa nối `last_matrix` ra CSV (chỉ `scale`/`angle_deg`) — chỉ cần nếu muốn tái lập warp mask ngoài.

## 7. Tài liệu tham khảo

- `.scratch/camera-ai-realtime/issues/39-*.md` (ticket này), `38-*.md` (câu hỏi gốc).
- `docs/task/20-11-2026-lk-noi-suy-ti-le-va-quet-cong-max-mad.md` (§4.1c — nơi câu "vì sao f62 không có
  ô" từng phải suy từ code).
- AGENTS §6 (bẫy `0/None ≠ đã đo`, `measured_fps` bão hoà ~29,9).

## 8. Review độc lập PR #66 (vòng 1) — P0 = 0, **P1 = 2** (cả hai là lỗi THẬT, đã vá)

| Mức | Reviewer bắt | Xử lý |
|---|---|---|
| **P1** | `_ghi_o_hien_thi` dựng dòng bằng `o = ""` khi không có ô ⇒ dòng chỉ **8 field**; `DictReader` đọc `ly_do` thành giá trị của cột `angle_deg` và **mất `n_diem`** — đúng ca `seed_rong` (f62, bbox VOS suy biến) mà ticket này sinh ra để chẩn đoán | dựng bằng **list đủ 11 field**; test round-trip: `len(raw[i]) == 11` cho mọi dòng, `ly_do == "seed_rong"`, `n_diem == "0"`. **Đã kiểm ĐỎ** bằng mutant `[""]` (1 phần tử) |
| **P1** | CSV **cũ** (6 cột) ⇒ `doc_chan_doan` trả dict **không rỗng** toàn `None` ⇒ `_dem` trả `{}` = "đo được 0 mẫu" chứ **không** phải `None` | thêm `chan_doan_tu_csv()` **cổng theo CỘT THIẾU** và `main()` dùng hàm đó; test gọi đúng hàm (bản đầu test **chép lại logic** nên mutant không chết — đã sửa). **Đã kiểm ĐỎ** bằng mutant trả thẳng `chan_doan` |
| P2 | `scale`/`angle_deg` **luôn** ghi `1.0000,0.00` (giá trị reset) ở chế độ `shift`, dù similarity chưa từng được tính | thêm cờ `khop` vào snapshot; `scale`/`angle_deg` để **TRỐNG** khi `khop=False`; test khoá |
| P2 | không test nào chạm `last_n_diem` | test 3 trạng thái: chưa chạy `None` · `seed_rong` **0** · `ok_shift` **> 0** |
| P2 | xoá phần nối `_chan_doan_frame` → `chan_doan_lk` **không test nào đỏ** | thêm test đi đúng đường `_result_threaded` → `_update_stats`, assert `ly_do`/`n_diem`/`frame_idx`; **đã kiểm ĐỎ** bằng mutant `pass` |
| P2 | artifact nghiệm thu có `git_dirty_code true`, `git_rev` là **commit cha** | **đo lại trên cây sạch** (mục 4) + `git rm` artifact cũ — *nửa "xoá" ban đầu KHÔNG thành công, reviewer vòng 2 bắt thành P1* |
| P3 | test CSV không khoá hình dạng (lệch dấu phẩy vẫn xanh) | nay assert `len(fields) == 11` **mọi dòng** + `lk_ok`/`x2` đúng cột |
| P3 | comment trong `light_tracker.py` + doc `dump_shown_csv` còn nói "chưa nối ra CSV" | sửa: đã nối ra `shown.csv`/`status.json`, CSV **11 cột** |
| P3 | `int(float(v))` chỉ bắt `ValueError` ⇒ CSV sửa tay `inf` làm script chết | bắt thêm `OverflowError` + test |
| P3 | `return self._interp_base_result` (nhánh `state is None`) không reset `_chan_doan_frame` | reset phòng thủ 1 dòng (nhánh hiện **không reachable**, reviewer xác nhận) |

Reviewer cũng xác nhận các mục **không phải lỗi**: chẩn đoán gắn **đúng frame** ở mọi đường chạy được
(`_result_inline` đặt `None` mỗi frame; `_update_stats_locked` dùng cùng `self._frame_index` cho cả
`chan_doan_lk` và `_last_shown`); `last_n_diem` đúng ở cả 9 đường `return`; `schema 5 → 6` đúng;
không race/không chậm (dict 6 khoá dựng **ngoài** `_stats_lock`, ~3–6 µs/frame so với LK 2–3 ms).

**Sự cố phụ bắt được khi chạy test**: một file rác tên `1` (0 byte, do lệnh shell tai nạn) nằm ở gốc repo
làm `looks_like_file("1")` trả `True` ⇒ 2 test camera-index đỏ — đúng cảnh báo AGENTS §6 ("tên số được
hiểu theo CWD... trừ khi có file thật trùng tên"). Đã xoá; không commit.

## 9. Review vòng 2 — P0 = 0, **P1 = 1** (artifact cũ vẫn tracked) + 2 P2 + 3 P3

| Mức | Reviewer bắt | Xử lý |
|---|---|---|
| **P1** | `data/tmp_39_metrics.json` (số **cây bẩn**, `git_dirty_code true`) **vẫn còn trong git index** ở `a994147`, trong khi log khai "đã xoá". Nguyên nhân thật: lệnh là `python3 -c ... && rm -f ...` mà phần python **lỗi** (`KeyError`) ⇒ `&&` chặn mất `rm`, rồi `git add -A` commit luôn file | `git rm data/tmp_39_metrics.json` (**đã kiểm**: `ls data/tmp_39*` không còn) + sửa câu trong log |
| P2 | CSV **mới** + `vos_every=1`: `cham()` trả `{}` ("đo được 0 mẫu") cùng lúc `lk_khong_ap_dung = true` + `lk_ok_frac = None` ⇒ tự mâu thuẫn | `main`: `if int(ve) == 1: chan_doan = None` + test |
| P2 | không ca nào gọi `_ghi_o_hien_thi` với `khop=True` ⇒ **hoán vị `scale`↔`angle_deg` không test nào đỏ** | thêm dòng frame 10 (`ok_scale`, `1.06/1.5`) và assert đúng cột; **đã kiểm ĐỎ** bằng mutant hoán vị hai cột |
| P3 | `thieu_diem` đọc `n_diem` = số điểm thật nhưng **không test** ⇒ mutant dời phép gán xuống dưới cổng không đỏ | test `LkBoxTracker(min_points=10_000)` ⇒ `thieu_diem` + `last_n_diem == 64`; **đã kiểm ĐỎ** bằng mutant dời |
| P3 | comment nói `vos_every=1` để `lk_ok` TRỐNG, thực tế ghi `0` (`bool(None)`) | sửa comment: ghi `0`, đọc bằng `lk_khong_ap_dung` |
| P3 | xoá dòng reset `last_n_diem` đầu bước không bị giết (test dùng tracker mới) | thêm: sau bước `ok`, đặt `_prev_gray = None` ⇒ bước sau `chua_reset` + `last_n_diem is None` |

Reviewer cũng xác nhận **5/5 ca** hình dạng CSV đều đủ **11 field** (kể cả `lk_ok is None`), `khop` đúng
chỉ `True` ở `ok_scale`, `khop` **không** bị `_dem` đếm, mutant `last_n_diem = ... or None` là **tương
đương** (không phải lỗ hổng), và số §4 khớp artifact sạch **chính xác** (0,5914/0,3848 ·
`{"mad_du":6,"ok_shift":1}` · 54 · 0,7844 · 58).

`./run lint` xanh · `./run test` **1595 passed**.

## 10. Vòng 3 (chốt) — **MERGE ĐƯỢC: P0 = 0, P1 = 0**

Reviewer xác nhận P1 vòng 2 **đã hết** (kiểm 3 cách: đĩa, git index — có đối chứng grep `AGENTS.md` để
chứng minh tool đọc thật —, và reflog), và 5/5 ca CSV đều đủ **11 field**. Còn 1 P2 + 4 P3 + 2 Note, đã vá:

| Mức | Reviewer nêu | Xử lý |
|---|---|---|
| P2 | test "cổng `vos_every=1`" **không gọi `main()`** (tự truyền `chan_doan=None`) ⇒ xoá 2 dòng cổng vẫn xanh | thêm `test_main_KHONG_truyen_chan_doan_khi_vos_every_1` chạy `main()` thật cho cả `ve=1` và `ve=3`; **đã kiểm ĐỎ** bằng mutant bỏ cổng |
| P3 | `assert last_n_diem == 64` bám hằng số ⇒ đổi `grid` hợp lệ thì đỏ oan | `== DEFAULT_GRID ** 2` |
| P3 | snapshot `"khop"` không test nào chứng minh lấy **từ tracker** (mutant hằng `False` xanh hết) | thêm assert `khop is True` + `scale == 1.25`; **đã kiểm ĐỎ** bằng mutant `"khop": False` |
| P3 | `.gitignore` dòng `!data/*_metrics.json` **chính là cơ chế** làm artifact cây bẩn lọt (P1 vòng 2) | thêm `data/tmp_*` + `data/_tmp_*` |
| P3 | câu FPS "29,8 vs 29,8, 200 frame" không có artifact; artifact ghi 30,0 @300 frame | ghi rõ: hai lần 200 frame chỉ đọc `status.json`, **không** để lại artifact; artifact là 300 frame ⇒ đừng trộn |
| P3 | cảnh báo "đã xoá" không nói file **vẫn lấy được từ lịch sử git** | thêm: `git show a994147:data/tmp_39_metrics.json` = số **cây bẩn**, **KHÔNG** trích |

Reviewer cũng xác nhận: cổng `ve=1` đặt **trùng khít** điều kiện `lk_khong_ap_dung` nên hai chỗ không thể
lệch; `{}` còn lại là **đúng nghĩa** (cột có, 0 mẫu — ví dụ `ly_do_khop_dem` ở chế độ `shift`); `git_rev
9ce467b` của artifact là **đúng** (các commit sau chỉ đổi `scripts/`+tests+comment).

`./run lint` xanh · `./run test` **1598 passed**.
