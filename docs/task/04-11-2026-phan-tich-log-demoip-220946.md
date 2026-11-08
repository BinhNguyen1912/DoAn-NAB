# Ngày 04-11-2026 — Phân tích log phiên `demoip_1104-220946`: số liệu đang đếm sai + 3 lần nhận lại sai

> Phiên phân tích log (không sửa code). Mục tiêu: giải thích vì sao phiên demo qua relay báo
> **mất dấu 22/86 (26%)** và **3 lần "nghi ngờ ĐỔI ĐỐI TƯỢNG"** trước buổi báo cáo GVHD.

## 🎯 Mục tiêu
- Truy nguyên 2 hiện tượng trong log: `bbox=(0,0,0,0) ms=0` và các cú nhảy ô bao.
- Xác định con số nào trong `*_summary.json` dùng được để báo cáo, con số nào không.

## 📥 Input
- Log phiên `./run demoip` (nguồn relay `http://172.19.176.1:8090/video`, `image_size=320`,
  `--smooth --reid --reid-cue object`), 86 bản ghi, `mean=268 ms`, `mất dấu 22/86`.
- `data/demoip_1104-220946_metrics.csv`, `_summary.json`, `_run_info.json`.

## 🔨 Công việc đã thực hiện
1. Đối chiếu từng dòng log với `src/reid.py`, `src/smooth_display.py`, `src/metrics_logger.py`.
2. Kiểm tra thanh `frame loading (JPEG): 1/1` xuất hiện 3 lần ⇒ suy ra `engine.start()` chạy 3 lần
   (mỗi lần = 1 ca nhận lại), đối chiếu với 3 WARN đổi đối tượng.
3. Tính lại số liệu sau khi loại 16 bản ghi `ms=0` (không chạy model).

## 📤 Output / Kết quả

### Số liệu: log báo sai so với thực tế
| | Log báo | Đếm đúng |
|---|---|---|
| Số frame | 86 | **70** lần suy luận (16 bản ghi `ms=0`) |
| Mất dấu | 22/86 = 26% | **~5–6/70 ≈ 8%** |
| Latency TB | 268 ms | **~330 ms** (mẫu 0 ms kéo trung bình xuống) |

### 5 lỗi xác định được (chưa sửa trong phiên này)
1. **Frame giả**: `reid.py:375` tăng `_frame_idx` ở mọi lần `step()`, kể cả nhánh LOST trả
   `_lost_result()` (`elapsed_ms=0.0`, mask rỗng); `smooth_display.py` quay vòng frozen mỗi 40 ms
   ⇒ ~25 bản ghi/giây được in + `metrics.log()` như frame thật.
2. **`_lost_age` đếm vòng lặp, không đếm frame** (`reid.py:412`) ⇒ bán kính tìm nở theo nhịp 25 Hz:
   `search_grow_frames=12` còn ~0,48 s thay vì ~3,2 s ⇒ nhận lại sai.
3. **Cổng NCC tắt trong lệnh demo**: `reid_obj_ncc_min=0.0` (`config.py:68`), `./run demoip` không
   truyền `--reid-obj-ncc-min` ⇒ hiệu chỉnh `ncc_min=0.35` chưa có tác dụng.
4. **`_reacquire()` không có cổng chạm mép/mask rác** (cổng `cham_mep` chỉ nằm ở `_collect_reference`).
   Bằng chứng: 3/3 ca nhận lại sai đều dính mép khung: `(338,0,507,188)`, `(451,314,639,479)`,
   `(350,0,508,188)`.
5. **`verify_frames=2` là no-op với ứng viên rác**: chỉ kiểm khi mask khác rỗng; mask rỗng ngay ⇒
   vào LOST và `_verify_left` bị reset 0 ⇒ không bao giờ `_abandon_reacquire` (vòng f41→f48→f87).

### File thay đổi
- `docs/task/04-11-2026-phan-tich-log-demoip-220946.md` — file này (chỉ ghi chép, không sửa code).

## 🐞 Vấn đề gặp phải & cách xử lý
- Không sửa code trong phiên này (mục tiêu là xác định nguyên nhân trước buổi báo cáo).
- Khi báo cáo: dùng số **~8% mất dấu trên frame có suy luận**, nêu rõ vì sao con số 26% là do
  cách đếm, không phải do tracker.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] `metrics`: chỉ log frame có suy luận (hoặc thêm cờ `inferred`) → `total_frames`/`lost_ratio`/`p95` đúng.
- [ ] `_lost_age` theo thời gian thật (hoặc theo frame suy luận), không theo số lần gọi.
- [ ] Thêm `--reid-obj-ncc-min 0.35` vào `./run demoip` và in ngưỡng NCC ra dòng `[re-ID]`.
- [ ] Chặn ở `_reacquire`: reject candidate chạm mép / mask rỗng trước khi `engine.start()`.
- [ ] Bắt `_abandon_reacquire` khi hết `verify_frames` mà chưa đủ frame `seen`.

## 📚 Tài liệu tham khảo
- ADR-0002 (hiển thị mượt 3 luồng), ADR-0003 (tái nhận diện), ADR-0004 (cue vật thể).
- `data/demoip_1104-220946_metrics.csv` — bằng chứng 16 dòng `latency_ms=0`.
