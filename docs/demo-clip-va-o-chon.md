# Clip + ô chọn cho demo và cho số đo (chốt 14-11-2026, sửa lần 2 sau review)

> Sinh ra sau khi phát hiện: **mọi số live trước 14-11 đo bằng ô nằm trên khuôn mặt** (không phải vật),
> và phần lớn "mất dấu" là **vật rời khung** / **nguồn file bị lặp**. File này là nguồn sự thật duy nhất
> cho "clip nào + ô nào + khung frame nào" khi demo và khi trích số.
>
> ⚠️ **Khung frame phải lấy từ file này, KHÔNG được chọn lại sau khi xem kết quả.** Ảnh kiểm để đối
> chiếu: `docs/media/bbox/*.jpg` (ô đúng/sai trên frame 0) và `docs/media/frames/*.jpg` (contact sheet
> mỗi 25 frame, có vẽ ô chọn) — sinh bằng `scripts/make_frame_sheet.py` (lệnh ở §5).

## 1. Bảng chốt

| Clip | Kích thước / frame | Vật | Ô chọn (`x,y,w,h`) | **Khung `--frame-window`** | Ghi chú |
|---|---|---|---|---|---|
| `data/binh1.mp4` | 720×1280 · 333 | chai xịt tím | `300,275,150,410` | **`0:110` và `165:262`** (lặp cờ) | giữa clip người ta **cất chai đi** (frame ~125–160) rồi đưa lại; ô `104,308,209,287` là **khuôn mặt**, không dùng |
| `data/binh2.mp4` | 720×1280 · 360 | chai trắng | `330,330,150,360` | **`0:160`** | chai trắng rời khung 165–240 và sau ~265; ô `200,400,300,500` phủ **2 chai + 2 tay**, không dùng |

Hai ô trên chỉ là **prompt của frame 0** — SAM 2 bám theo vật sau đó, nên không cần cập nhật ô.
**Đừng** hiểu "ô phải nằm trên vật ở mọi frame": contact sheet cho thấy vật rời khỏi ô ngay từ frame ~25
(một cách bình thường).

## 2. Lệnh đo chuẩn

```bash
# BẮT BUỘC --frame-window: empty_frac cả phiên gộp "model mất dấu" với "vật ngoài khung + vòng lặp file"
python scripts/measure_live_relay.py --source data/binh1.mp4 --bbox 300,275,150,410 \
    --image-size 192 --vos-every 3 --seconds 11 \
    --frame-window 0:110 --frame-window 165:262 --out data/<tên>_metrics.json

# Tái lập từ CSV đã commit (không cần chạy lại model):
python scripts/analyze_drift_samples.py data/drift_samples_binh1_2026-11-14_115745.csv \
    --frame-window 0:110 --frame-window 165:262 --out /tmp/dt.json
```

`--seconds` nên ≈ **một vòng** clip (binh1 11 s, binh2 12 s): chạy 55 s trên clip 11 s là **4–5 vòng**,
các vòng sau rơi hết vào `ngoai_khung` (artifact ghi `cua_so_frame.so_vong` + in cảnh báo).

**Quy tắc trích số:**

- Khi nói về chất lượng bám, `mask rỗng`/`empty` **chỉ** trích từ `trong_khung`.
- Luôn nêu **cả** `ngoai_khung` nếu nhắc tỉ lệ rỗng cả phiên: rỗng ở đó là do **người đo khai** là ngoài
  khung (vật đã cất đi **hoặc** vòng lặp file), không phải lỗi model.
- `drift_iou` **không phải** độ chính xác (AGENTS §6) — nó là độ tự nhất quán ô LK ↔ mask VOS kế tiếp.
- Artifact cũ có `lenh` **thiếu `--bbox`** (`measure_watchdog.py`, `profile_stages.py` trước 14-11) ⇒
  chạy lại phải thêm `--bbox <thiet_lap.bbox_xywh>` của chính artifact đó, nếu không nó sẽ dùng **ô chai
  mới** và không còn tái lập số cũ.

## 3. Số đo (đường live, @192, `vos_every 3`, 55 s, 3 lần xen kẽ, `git_dirty_code=false`)

| Ca | `empty` cả phiên | `empty` **trong khung** | `drift_iou` trong khung | mask/s | `mask_age_p95` |
|---|---|---|---|---|---|
| mặt người (`binh1`, ô cũ) | 0,0 % | 0,0 % | 0,881–0,884 | 7,8–8,2 | 209–228 ms |
| chai (`binh1`, ô mới, `0:110 ∪ 165:262`) | **36,0–36,7 %** | **1,7–1,8 %** (n = 57–59) | 0,475–0,484 | 8,5–8,8 | 215–221 ms |
| chai (`binh2`, ô mới, `0:160`) | 21,7–23,4 % | **0,0 %** (n = 44–45) | 0,702–0,721 | 8,1–8,5 | 209–219 ms |

- Chia nhỏ `binh1`: đoạn **`0:110` cho 0,0 % rỗng** (n = 31–32, drift 0,41–0,44); đoạn `165:262` cho
  3,7–9,1 % rỗng (vật vừa được đưa lại nên có vài nhịp chưa bám).
- Artifact: `data/lan2_{mat_binh1,chai_binh1,chai_binh2}_lan{1,2,3}_metrics.json`; CSV từng mẫu:
  `data/drift_samples_binh1_2026-11-14_{115745,120047,120349}.csv`,
  `data/drift_samples_binh2_2026-11-14_{115845,120148,120450}.csv`.
- Cách tính: `scripts/analyze_drift_samples.py ... --frame-window ...` (§2), không chép tay.
- **Đo đúng 1 vòng clip** (không lặp nguồn) để số không bị nhiễu vòng lặp, `git_dirty_code=false`:

  | Lần đo | `so_vong` | `trong_khung` | `ngoai_khung` |
  |---|---|---|---|
  | `data/sach_chai_binh1_1vong_metrics.json` (`--seconds 11`, khung `0:110` ∪ `165:262`) | 0,95 | n = 64 · **rỗng 1,6 %** · drift 0,4895 (n_drift 61) | n = 40 · rỗng 90 % |
  | `data/sach_chai_binh2_1vong_metrics.json` (`--seconds 12`, khung `0:160`) | 0,93 | n = 50 · **rỗng 0,0 %** · drift 0,726 (n_drift 50) | n = 64 · rỗng 34,4 % |

  `drift_iou` ở `ngoai_khung` **không dùng** được (mẫu rỗng chi phối) — chỉ đọc `trong_khung`.
- Kết luận (không cần train lại model): `docs/task/14-11-2026-do-lai-bbox-dung-ket-luan-khong-can-train-lai.md`.

## 4. Chuẩn bị cho buổi demo

1. **Demo live (webcam)**: người cầm vật giữ nó **trong khung suốt** — mọi thứ khác đã đúng. Vật nên có
   màu/nhãn rõ (chai xịt tím, chai trắng có nhãn) thay vì vật trơn màu.
2. **Demo bằng file** (dự phòng): dùng đúng §1. Muốn clip dài hơn thì cắt các đoạn vật còn trong khung —
   clip ghép **chỉ để diễn**, **cấm** dùng để lấy số chất lượng:

   ```bash
   python - <<'PY'
   import cv2
   def cat(src, dst, a, b):
       c = cv2.VideoCapture(src)
       w, h = c.get(cv2.CAP_PROP_FRAME_WIDTH), c.get(cv2.CAP_PROP_FRAME_HEIGHT)
       v = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"mp4v"), 30, (int(w), int(h)))
       c.set(cv2.CAP_PROP_POS_FRAMES, a)
       for _ in range(b - a):
           ok, fr = c.read()
           if not ok: break
           v.write(fr)
       c.release(); v.release()
   cat("data/binh1.mp4", "data/demo_chai_binh1.mp4", 0, 110)
   cat("data/binh2.mp4", "data/demo_chai_binh2.mp4", 0, 160)
   PY
   ```
3. **HUD phải in được cấu hình đang chạy** (`image_size`, `vos_every`, mask/s) — để "số này đo ở đâu"
   nằm trên màn hình, không nằm trong đầu người trình bày.

## 5. Sinh lại ảnh kiểm (đừng tin bảng này nếu chưa xem ảnh)

```bash
python scripts/make_frame_sheet.py --clip data/binh1.mp4 --bbox 300,275,150,410 --every 25 \
    --out docs/media/frames/binh1_bbox_300-275-150-410.jpg
python scripts/make_frame_sheet.py --clip data/binh2.mp4 --bbox 330,330,150,360 --every 25 \
    --out docs/media/frames/binh2_bbox_330-330-150-360.jpg
```

Ảnh kết quả đã commit trong `docs/media/frames/` (≈130 KB/ảnh) — nhìn frame nào **không có vật** là biết
ngay khung `--frame-window` phải cắt ở đâu.

## 6. Việc chưa chốt

- [ ] Chưa có clip **quay mới** có vật ở trong khung ≥ 20 s liên tục (mới có 3,7–5,3 s) ⇒ nếu cần demo
      dài bằng file thì phải quay thêm, hoặc ghép (mục 4.2).
- [ ] Chưa đo trên **webcam rời** thật (mọi số hiện tại là webcam laptop qua relay).
- [x] Ví dụ ô cũ đã sửa ở `README.md`, `docs/cheatsheet-lenh.md`, `run` (help), `docs/colab-gpu.md`
      và `notebooks/colab_gpu_evaluation.ipynb` (kèm test khoá `BBOX`).
- [ ] Cột "mask/s" trong bảng §3 là **`mask_fps` của mẫu cuối** (`tom_tat.mask_fps_cuoi`), không phải
      `worker_status.vos_fps` (ca `lan2_chai_binh1_lan1`: `vos_fps` 9,1 · `mask_fps_max` 9,2 · 3 mẫu
      cuối 7,9/8,4/8,8) — khi trích phải ghi rõ trường nào.
