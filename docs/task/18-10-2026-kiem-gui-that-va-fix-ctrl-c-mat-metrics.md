# Ngày 18-10-2026 — Kiểm GUI thật (WSLg) + fix Ctrl+C làm mất metrics

## 🎯 Mục tiêu
- Kiểm thủ công đường GUI (kéo chuột chọn đối tượng, ghi mp4, metrics) trên máy thật — hạng mục treo từ ticket 03/05/06/07.
- Sửa mọi lỗi phát hiện được trong lúc kiểm.

## 📥 Input
- Kết quả kiểm của người dùng: Windows không có Python/conda; WSLg có (`DISPLAY=:0`) nhưng Qt thiếu `libICE.so.6`/`libSM.so.6` → `cv2.namedWindow` abort.
- Video demo cũ `data/samurai_cpu_demo_dog.mp4` **hỏng** (`moov atom not found`).
- Lệnh kiểm: `python tools/run_live.py --source data/_gui_test.mp4 --display [--record … --metrics-csv …]`.

## 🔨 Công việc đã thực hiện
1. Chẩn đoán bằng `ldd` trên `cv2/qt/plugins/platforms/libqxcb.so` → đúng 2 lib thiếu; người dùng cài `sudo apt-get install -y libice6 libsm6` → GUI chạy.
2. Tạo video test mới `data/_gui_test.mp4` (640×360, 30 frame, ô vuông cam 60px đi `(+8,+4)/frame`, 5 fps) bằng `src/synthetic_video.py` — thay video demo hỏng. (File nằm trong `data/` nên bị `.gitignore`, không commit.)
3. **Kiểm GUI thật — KẾT QUẢ ĐẠT:** kéo chuột chọn ô → bbox f0 `(79,80,142,142)` ≈ ô thật `(80,80)–(140,140)`; bám đúng quỹ đạo tới `(184,132,244,192)` ở f13 (khớp `+8x,+4y`/frame); thoát `q` in `[kết quả] 14 frame đã track`. Ghi mp4: `data/gui_hud.mp4` mở được, 9 frame, 640×360.
4. **Phát hiện bug thật:** thoát bằng **Ctrl+C** → `data/gui_metrics.csv` + `gui_summary.json` KHÔNG được ghi (mp4 vẫn có). Nguyên nhân: `_finish_metrics` nằm sau `try`, bị `SystemExit(0)` bỏ qua. Người dùng demo hay dừng bằng Ctrl+C → mất toàn bộ số liệu "đánh giá hiệu năng".
5. TDD fix: 2 test đỏ trong `tests/test_run_live_cli.py::TestCtrlCFlush` (headless + display, engine giả ném `KeyboardInterrupt` ở process thứ 2, assert CSV/JSON vẫn có + exit code 0) → sửa `_run_headless`/`_run_display`: cờ `interrupted`, flush metrics + `close_recorder()` **trong `finally`**; `_finish_metrics` bỏ tham số `total` không dùng. GREEN 9/9 test CLI.
6. Dứt tiếng ồn Qt (5 dòng `QFontDatabase: Cannot find font directory …cv2/qt/fonts`) bằng cách tạo thư mục đó + copy `DejaVuSans.ttf` → **0 cảnh báo**. Đã thử `QT_QPA_FONTDIR` trước (KHÔNG ăn với Qt5). Ghi vào README mục "Sự cố thường gặp khi chạy GUI" (kèm bảng: thiếu lib Qt, không mở được camera, HUD ô `?`, warning `_C` của SAM 2 là bình thường).
7. Verify: `ruff check .` sạch; full suite **84 passed (127s)**.

## 📤 Output / Kết quả
- Đường GUI + chọn đối tượng + ghi video: **đã kiểm chứng thật** (không chỉ test headless).
- Bug Ctrl+C mất metrics: **đã sửa + có regression test** (2 test mới).
- File thay đổi:
  - `tools/run_live.py` — flush metrics/recorder trong `finally` (cả headless + display), `_finish_metrics` gọn hơn
  - `tests/test_run_live_cli.py` — +2 test `TestCtrlCFlush`, helper `_write_cfg` dùng `textwrap.dedent`
  - `README.md` — mục "Sự cố thường gặp khi chạy GUI" + lệnh dứt cảnh báo font Qt
- Artefact kiểm (không commit): `data/_gui_test.mp4`, `data/gui_hud.mp4`.

## 🐞 Vấn đề gặp phải & cách xử lý
- Qt xcb thiếu lib → `ldd` chỉ đúng 2 gói, sửa bằng apt (không cần cài Python/conda bên Windows).
- `QT_QPA_FONTDIR` không có tác dụng với Qt5 của OpenCV → tạo đúng thư mục `cv2/qt/fonts` + TTF.
- Video demo cũ hỏng nên không dùng được cho demo lẫn test → sinh video test bằng code.
- Test YAML trong file test viết sai (mẹo `.replace` thụt lề) → chuyển helper sang `textwrap.dedent`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Kiểm **phím r** (chọn lại đối tượng thứ 2) trên GUI thật — chưa xác nhận.
- [ ] Chạy lại lệnh metrics + **Ctrl+C** để xác nhận CSV/JSON đã có (bản sửa).
- [ ] Webcam: WSL không thấy camera → dùng RTSP/HTTP từ điện thoại (kiểm adapter nguồn mạng) hoặc cài Miniconda trên Windows (`winget install -e --id Anaconda.Miniconda3`).
- [ ] Colab GPU + biểu đồ báo cáo (phase mới).

## 📚 Tài liệu tham khảo
- WSLg (`/mnt/wslg`, `DISPLAY=:0`), OpenCV Qt5 xcb plugin, `ldd`; `docs/samurai-setup.md`; ADR-0002 (số liệu trung thực — lý do Ctrl+C phải giữ metrics).
