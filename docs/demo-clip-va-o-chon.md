# Clip + ô chọn cho demo và cho số đo (chốt 14-11-2026)

> Sinh ra sau khi phát hiện: **mọi số live trước 14-11 đo bằng ô nằm trên khuôn mặt** (không phải vật),
> và phần lớn "mất dấu" thật ra là **vật đã rời khung**. File này là nguồn sự thật duy nhất cho
> "clip nào + ô nào + khung frame nào" khi demo và khi trích số.
> Bằng chứng ảnh: `docs/media/bbox/*.jpg` (ô cũ / ô mới trên frame 0).

## 1. Bảng chốt

| Clip | Kích thước / số frame | Vật | Ô chọn (`x,y,w,h`) | **Khung frame vật còn trong khung** | Ghi chú |
|---|---|---|---|---|---|
| `data/binh1.mp4` | 720×1280 · 333 | chai xịt tím | `300,275,150,410` | **`0:110`** (≈3,7 s) và `165:262` | giữa clip người ta **cất chai đi** (frame 125–160 và 275+ **không có chai**) ⇒ ô `104,308,209,287` là **khuôn mặt**, không dùng |
| `data/binh2.mp4` | 720×1280 · 360 | chai trắng | `330,330,150,360` | **`0:160`** (≈5,3 s) | chai trắng rời khung ở 165–240 và sau 265 (frame 300 chỉ còn chai đen) ⇒ ô `200,400,300,500` phủ **2 chai + 2 tay**, không dùng |

Kiểm bằng ảnh: contact sheet 15 mốc frame/clip (`data/sheet_binh{1,2}.jpg`, sinh bằng
`cv2.VideoCapture` + resize) — **đừng tin bảng này nếu chưa xem ảnh frame 0 và frame cuối khung**.

## 2. Lệnh đo chuẩn (BẮT BUỘC có `--frame-window`)

```bash
python scripts/measure_live_relay.py --source data/binh1.mp4 --bbox 300,275,150,410 \
    --image-size 192 --vos-every 3 --seconds 55 --frame-window 0:110 \
    --out data/<tên>_metrics.json
```

Artifact sẽ có `cua_so_frame.trong_khung` / `.ngoai_khung`. **Quy tắc trích số:**

- `mask rỗng` / `empty_frac` **chỉ được trích từ `trong_khung`** khi nói về chất lượng bám.
- `ngoai_khung` **luôn** phải nêu kèm nếu nhắc tới tỉ lệ rỗng cả phiên — rỗng ở đó là **model trả lời
  đúng** (không có vật), không phải lỗi.
- `drift_iou` vẫn **không phải** độ chính xác (AGENTS §6) — nó là độ tự nhất quán ô LK ↔ mask VOS.

## 3. Số đo 14-11 (đường live, @192, `vos_every 3`, 55 s, 3 lần xen kẽ, `git_dirty_code=false`)

| Ca | `empty` cả phiên | `empty` **trong khung** | `drift_iou` trong khung | mask/s | `mask_age_p95` |
|---|---|---|---|---|---|
| mặt người (`binh1`, ô cũ) | 0,0 % | 0,0 % | 0,883 (0,881–0,884) | 7,8–8,2 | 209–228 ms |
| chai (`binh1`, ô mới, khung `0:110`) | 35,0–36,3 % | **0,0 %** | 0,419–0,455 | 8,5–8,8 | 215–221 ms |
| chai (`binh2`, ô mới, khung `0:140`) | 21,7–23,4 % | **0,0 %** | 0,727–0,753 | 8,1–8,5 | 209–219 ms |

Artifact: `data/lan2_*_metrics.json`. Chi tiết + kết luận (không cần train lại model):
`docs/task/14-11-2026-do-lai-bbox-dung-ket-luan-khong-can-train-lai.md`.

## 4. Chuẩn bị cho buổi demo

1. **Demo live (webcam)**: người cầm vật giữ nó **trong khung suốt** — mọi thứ khác đã đúng. Vật nên có
   màu/nhãn rõ (chai xịt tím, chai trắng có nhãn) thay vì vật trơn màu.
2. **Demo bằng file** (dự phòng): dùng đúng 2 dòng trong bảng §1; nếu muốn clip dài hơn thì **cắt ghép
   chỉ những đoạn vật còn trong khung** — clip ghép **chỉ để diễn**, **cấm** dùng để lấy số chất lượng:

   ```bash
   python - <<'PY'
   import cv2
   def cat(src, dst, a, b):
       c = cv2.VideoCapture(src); w = c.get(cv2.CAP_PROP_FRAME_WIDTH); h = c.get(cv2.CAP_PROP_FRAME_HEIGHT)
       v = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"mp4v"), 30, (int(w), int(h)))
       c.set(cv2.CAP_PROP_POS_FRAMES, a)
       for _ in range(b - a):
           ok, fr = c.read()
           if not ok: break
           v.write(fr)
       c.release(); v.release()
   cat("data/binh1.mp4", "data/demo_chai_binh1.mp4", 0, 110)     # CHỈ để diễn
   cat("data/binh2.mp4", "data/demo_chai_binh2.mp4", 0, 160)
   PY
   ```

3. **HUD phải in được cấu hình đang chạy** (`image_size`, `vos_every`, mask/s) — nếu thầy hỏi "số này
   đo ở đâu" thì câu trả lời nằm ngay trên màn hình, không phải trong đầu người trình bày.

## 5. Việc chưa chốt

- [ ] Chưa có clip **quay mới** có vật ở trong khung ≥ 20 s liên tục (mới chỉ có 3,7–5,3 s) ⇒ nếu cần
      demo dài bằng file thì phải quay thêm, hoặc ghép (mục 4.2).
- [ ] Chưa đo trên **webcam rời** thật (mọi số hiện tại là webcam laptop qua relay).
- [ ] `AGENTS.md` §6 còn 2 bullet cũ nói "binh2 mất dấu 26 lần / hybrid chỉ giữ được ô bao trên một số
      clip" — đã sửa kèm ghi chú ô chọn trong PR này; nếu thấy còn câu khác chưa đúng thì thêm vào
      mục này chứ đừng sửa lặng lẽ.
