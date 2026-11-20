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

## 4. Output / kết quả (số đo)

Lần chạy nghiệm thu: `--gt docs/gt/b1b --clip data/binh1.mp4 --bbox 300,275,150,410 --max-mad 1.5 100 --lan 1`,
@192, `vos_every 3`:

| cấu hình | IoU(ô hiển thị, ô GT) | `ly_do_dem` (7 frame GT) | `ly_do_khop_dem` | `n_diem` median | `csv_thieu_cot` |
|---|---|---|---|---|---|
| `1,5/shift` | 0,6396 (tệ nhất 0,3831) | **`mad_du`: 7/7** | `{}` (đo được, 0 mẫu) | **54** | `[]` |
| `100/shift` | 0,8002 (tệ nhất 0,5649) | `ok_shift`: 7/7 | `{}` | 58 | `[]` |

⇒ **Trả lời được câu hỏi mở của ticket #38 bằng SỐ**: ở `max_mad = 1,5`, LK từ chối cả 7/7 frame GT vì
**cổng MAD** (`mad_du`) — **không** phải `seed_rong` — và lúc đó vẫn còn **54/64** điểm theo dõi. Tức
"cửa quá chặt", không phải "mất dấu".

**Không chậm thêm**: `measured_fps` 29,8 (có `--dump-shown-csv`) vs 29,8 (không dump), 200 frame, @192,
`vos_every 3`, cùng clip/ô — ngưỡng nhiễu ±0,3 % = ±0,09 FPS. `status.json` có `chan_doan_lk`
(`{"ly_do":"mad_du","n_diem":53,"lk_ok":false,"frame_idx":199,…}`) **kể cả khi không bật dump**.

Kiểm máy: `./run lint` xanh · `./run test` **1590 passed**.

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
