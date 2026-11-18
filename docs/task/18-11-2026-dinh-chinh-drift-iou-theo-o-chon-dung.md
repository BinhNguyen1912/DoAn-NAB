# 18-11-2026 — Đính chính `drift_iou` trong phụ lục báo cáo: đo bằng ô KHUÔN MẶT, không phải ô chai

## Mục tiêu

Phụ lục `docs/doi-chieu-yeu-cau-gvhd.md` (tài liệu hội đồng đọc) và bản tóm tắt vẫn trích
`drift_iou` **0,887 / 0,873 / 0,528 (p05 0,000)** như số của việc "bám chai". Kiểm lại thì đó là số của
**ô khuôn mặt** (`binh1`) và ô phủ **2 chai + 2 tay** (`binh2`) — đính chính đã có từ 14-11 trong
`AGENTS.md` §6 và `docs/demo-clip-va-o-chon.md`, nhưng **chưa vào phụ lục**. Sửa để số trong báo cáo khớp
ô chọn thật.

## Input

- `docs/demo-clip-va-o-chon.md` (nguồn sự thật: ô + khung frame), `AGENTS.md` §6 (đính chính 14-11).
- Artifact **đúng ô chai + có `--frame-window`**:
  `data/chu_ky_chai_binh1_1vong_lan{1,2,3}_metrics.json` (bbox `300,275,150,410`),
  `data/sach_chai_binh1_1vong_metrics.json`, `data/sach_chai_binh2_1vong_metrics.json`
  (bbox `330,330,150,360`) — tất cả `git_dirty_code = false`.
- Artifact **ô khuôn mặt** (số cũ): `data/drift_2026-11-08_metrics.json` — `empty_runs = 0` ở mọi lần
  `binh1`, đúng dấu hiệu "ô phủ khuôn mặt" (mặt luôn trong khung).

## Công việc đã thực hiện

1. Đọc `cua_so_frame.trong_khung` của 5 artifact đúng ô chai:

   | Clip | `empty_frac` trong khung | `drift_iou_mean` trong khung |
   |---|---|---|
   | `binh1` (`0:110` ∪ `165:262`) | 1,6 % · 3,3 % · 1,6 % · 1,6 % | 0,493 · 0,504 · 0,497 · 0,490 |
   | `binh2` (`0:160`) | **0,0 %** | **0,726** |

2. Bảng phụ lục: đổi dòng "Độ tự nhất quán ô bao (`drift_iou`, p05)" thành **ô CHAI, chỉ trong khung vật
   có mặt** với `binh1` **0,48–0,50**, `binh2` **0,726** (`empty_frac` 0 %), kèm danh sách artifact.
3. Thêm **khối ⚠ ĐÍNH CHÍNH 14-11** ngay dưới bảng: số cũ 0,887 / 0,873 / 0,528 đo bằng ô khuôn mặt/ô
   sai ⇒ **không** dùng để nói "bám chai"; `p05 = 0,000` của `binh2` **cả phiên** chủ yếu là **vật rời
   khung** (36 % số lần VOS rỗng), không phải model mất dấu; `drift_iou` vẫn chỉ là **tự nhất quán**.
4. Sửa cùng số đó ở dòng 10 (bảng yêu cầu GVHD) và ở `docs/tom-tat-do-an.md:163`.

## Output / Kết quả

- `grep "0,887\|0,528" docs/*.md` → không còn chỗ nào trích số cũ **mà không** nói ô chọn.
- `./run lint` xanh (không đổi code; chỉ docs).

## Vấn đề & cách xử lý

- **Không** xoá các số cũ khỏi lịch sử (`docs/task/08-11-…`, log 14-11 giữ nguyên theo AGENTS §2.3) — chỉ
  sửa **tài liệu đang dùng để báo cáo**.
- Vì sao chọn `drift_iou_mean` trong khung thay vì `p05`: `p05` cả phiên trộn "vật ngoài khung" với
  "model lệch" (đó chính là lý do có `--frame-window`), còn `p05` **trong khung** của `binh1` = 0,000 do bị
  cắt bởi những lần VOS lúc chai vừa rời khung — trích nó cũng là trích sai. `drift_iou_mean` trong khung
  là con số duy nhất vừa đúng ô chọn vừa có nghĩa "tự nhất quán của mask khi vật có mặt".

## Next steps

- Muốn có **độ chính xác** (không phải tự nhất quán) thì phải chấm **mIoU mask vs GT người gán** trên clip
  thật — hiện chỉ có mIoU trên fixture tổng hợp (0,956/0,892, cận trên) và GT hộp bao trên `binh1`
  (0,6464, không phải phân đoạn). Đây là việc **cần người gán GT** (ticket #11/#14 cùng nhóm chờ dữ liệu).

## Tài liệu tham khảo

- `docs/demo-clip-va-o-chon.md`, `AGENTS.md` §6 (mục 14-11), `data/*chai*_1vong_metrics.json`

## Rà thêm trong cùng PR (2 phát hiện nữa)

1. **Watchdog `3,75 s` bị trích thiếu điều kiện**: artifact `data/watchdog_raw_2026-11-09_metrics.json` có
   `moi_truong = "mode raw: relay ảnh JPEG qua HTTP (localhost)"` và lệnh `--mode raw`. AGENTS §6 nói rõ
   **chưa đo trên webcam/RTSP thật**. Phụ lục đã ghi thêm đúng điều kiện đó + `kill -9` bắt bằng
   `proc.poll()` (không phải "0,1 s cho ca treo").
2. **Provenance của chính các artifact trong bảng**: quét 14 file được trích ⇒ **7 file không có `git_rev`
   truy được**:
   - 5 file **không có trường `git_rev`** (sinh trước quy ước): `res_1102_summary`, `gui_summary`,
     `lighting_iou_320_summary`, `smooth_summary`, `reid_2clip_calib`;
   - `drift_2026-11-08_metrics.json`: `git_rev` là chuỗi 40 ký tự **gõ sai** (commit thật `ee9f25672d72`);
   - `live_web_relay_2026-11-10_metrics.json`: rev chỉ còn ở object local (nhánh rebase trước khi push).
   ⇒ Đã thêm khối ⚠: số vẫn dùng được **kèm tên file**, nhưng **không** được nói "tái lập được từ
   `git_rev`", và **cấm dẫn rev** của 2 file cuối (đúng `CHO_PHEP` của `provcheck`).

Kiểm markdown vẫn đúng: khối bảng phụ lục còn **17 dòng `|`**, **0** dòng chen giữa (lỗi đã gặp ở PR #41).

3. **Hai tài liệu báo cáo khác cũng trích artifact thiếu provenance**: `docs/tom-tat-do-an.md` (8 file trích,
   3 vấn đề) và `docs/giai-thich-do-an.md` (4 file, 1 vấn đề) ⇒ đã thêm cùng khối ⚠ (ngắn) để ba tài liệu
   nói **một** giọng. Quét tự động (script trong log này): 15 file trích ở phụ lục, **8 vấn đề**.
