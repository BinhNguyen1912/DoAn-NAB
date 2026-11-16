# 31: GT: phân biệt manifest HỎNG vs không có manifest + cảnh báo copy-paste hộp bao

**What to build:** Hai P3 còn nợ của ticket #30 (review độc lập 16-11), không đổi số mIoU:

1. `scripts/score_miou.py::_doc_manifest` nuốt lỗi JSON và trả `None` ⇒ manifest **hỏng** in ra y hệt "KHÔNG có manifest của mask" (ca sau là bình thường). Đổi thành `(manifest, lỗi)`: `(None, None)` = không có file; `(None, "…")` = có file nhưng hỏng/không phải JSON object. `main()` thêm **cảnh báo mềm** "manifest của mask HỎNG (…) ⇒ KHÔNG đối chiếu được clip/frame", ghi `meta.mask_manifest_loi` vào artifact, và `--check-index` nói đúng ca.

2. Bản hộp bao của `DUP_IOU` (`scripts/gt_check_silhouette.py`): trong `kiem_index`, khi `dang_gt == hop_bao`, gom `hop_bao_xywh` theo frame; hai frame khai **cùng một hộp** ⇒ cảnh báo MỀM "frame … khai CÙNG một hộp ⇒ kiểm xem có copy-paste GT không" (không chặn: vật đứng yên vẫn có thể trùng hộp thật). Bộ GT thật `docs/gt/binh1_hopbao` (12 hộp khác nhau) phải **không** bị cảnh báo oan.

Kèm: cập nhật `docs/thuoc-do-bam-dung.md` §1.2 (2 dòng mới + nói rõ copy-paste nay chỉ **cảnh báo mềm** với GT hộp bao; GT silhouette vẫn dùng `gt_check_silhouette`).

**Blocked by:** None (can start immediately)

**Status:** resolved

- [ ] `_doc_manifest` trả `(manifest, lỗi)`; `meta.mask_manifest_loi` có trong artifact khi manifest hỏng; `--check-index` in "manifest của mask HỎNG" thay vì "KHÔNG có manifest" (test cho JSON hỏng + manifest là list)
- [ ] Hai frame khai cùng `hop_bao_xywh` ⇒ cảnh báo MỀM "CÙNG một hộp … copy-paste?" (test ca trùng và ca khác nhau); bộ GT thật `binh1_hopbao` không bị cảnh báo oan
- [ ] `docs/thuoc-do-bam-dung.md` §1.2 có 2 dòng mới + câu giới hạn đã cập nhật
- [ ] `./run lint` + `./run test` xanh, artifact sinh lại trên cây sạch

## Answer

Xong trên nhánh `fix/gt-manifest-hong-va-copy-paste` (commit `c79e341`, `937da6b`, `6219050`), merge bằng **merge commit** để `git_rev c79e341` còn reachable trong `main` (P1 review vòng 3). `_doc_manifest` nay trả `(manifest, lỗi)`; `meta.mask_manifest_loi` có trong artifact (None khi manifest hợp lệ, chuỗi lỗi khi hỏng/không phải object); `--check-index` in "manifest của mask HỎNG" và **không** in "KHÔNG có manifest" ở ca đó (test ghim cả hai chiều). Cảnh báo mềm "frame … khai CÙNG một hộp … copy-paste?" chỉ chạy khi `dang_gt = hop_bao` và 4 số giống hệt; bộ GT thật `binh1_hopbao` (12 hộp khác nhau) không bị cảnh báo oan — có test. `./run lint` xanh · `./run test` **1278 passed** (5 deselected, +8 test) · artifact sinh trên cây sạch `c79e341`, `git_dirty_code false`, `mIoU 0,6464` **không đổi**. Review độc lập vòng 3: 0 P0, đã đóng 1 P1 + 2 P2 + 3 P3. Log: `docs/task/16-11-2026-ticket-30-cong-kiem-gt-hop-bao.md` (mục 6 + Review vòng 3).
