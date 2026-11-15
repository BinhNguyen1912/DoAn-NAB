# 27: Chạy lại `./run bangcau` để artifact đã commit có `cau_hinh` (tự kiểm cấu hình)

**What to build:** Từ commit 58bb629, `status.json` echo `cau_hinh` (yêu cầu + `image_size_hieu_luc`) và `scripts/bang_cau_hinh.py` ghi echo đó vào từng dòng artifact, đồng thời **từ chối** lần chạy có `cau_hinh_lech != []` hoặc `image_size_hieu_luc = None`.

Nhưng artifact đã commit hiện tại (`data/bang_cau_hinh_2026-11-14_metrics.json`, 9 dòng × 3 lần) và `data/ab_192_vs_320_2026-11-14_metrics.json` **sinh trước** thay đổi này ⇒ **không có** `cau_hinh` ⇒ `docs/bang-cau-hinh.md` và các dòng REGISTRY của `scripts/so_lieu_bao_cao.py` vẫn **chưa tự kiểm được** "model chạy đúng image_size đã yêu cầu".

Việc cần làm: chạy lại `./run bangcau --sizes 192,256,320 --every 2,3,6 --lan 3 --frames 60 --bbox <ô chai>` trên **cây sạch** (commit code trước, đo sau), rồi `python scripts/so_lieu_bao_cao.py` để sinh lại `docs/so-lieu-bao-cao.md` (test `test_doc_da_commit_khop_artifact` ghim file này). Tương tự cho `./run ab` nếu muốn A/B cũng có echo.

**Vì sao cần:** nếu không, câu "artifact tự kiểm cấu hình" chỉ đúng cho các lần đo **về sau**, còn bảng đang được trích trong báo cáo thì vẫn phải tin tham số CLI.

**Lưu ý:** 27 phiên worker × ~15 s ⇒ ~7 phút; phải commit code trước khi đo để `git_dirty_code == false`, nếu không số mới lại không tái lập được.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `data/bang_cau_hinh_*_metrics.json` (bản mới) có `cau_hinh` ở từng dòng, với `image_size_hieu_luc_da_thay` = một phần tử đúng bằng `image_size` của dòng đó
- [ ] Artifact mới có `git_dirty_code == false` và `git_rev` == commit chứa thay đổi echo cấu hình
- [ ] `docs/bang-cau-hinh.md` sinh lại từ artifact mới; `./run bangcau --check` xanh
- [ ] `docs/so-lieu-bao-cao.md` sinh lại; `./run test` xanh (test ghim doc ↔ artifact)
- [ ] Nếu `./run ab` cũng chạy lại: mỗi lần chạy trong `lan_chay` có `cau_hinh.image_size_hieu_luc` khớp cấu hình A/B
