# Briefing họp GVHD — 23-10-2026

> **Đọc file này trước khi vào họp (5 phút).** Mọi số liệu dưới đây lấy từ chính repo,
> không phải tự khai. Dòng nào có `file:dòng` là chỉ đúng chỗ để mở ra nếu thầy hỏi.

---

## 0. Ba file PHẢI đọc (theo thứ tự)

| # | File | Đọc mục nào | Để làm gì |
|---|---|---|---|
| 1 | `docs/task/22-10-2026-tai-nhan-dien-khuon-mat-yunet-sface.md` | Cả file (1 trang) | Việc **mới nhất** hôm qua: tái nhận diện (mất dấu → đóng băng → bám lại đúng người) |
| 2 | `docs/giai-thich-do-an.md` | **Mục 14** (chọn mặt A bám sang mặt B) + mục lục đầu file | Giải thích toàn đồ án bằng lời thường + **câu trả lời mẫu cho hội đồng** |
| 3 | `README.md` | **Mục 7 "Đánh giá hiệu năng"** (bảng số CPU/GPU) | Bảng số liệu để nói, không phải nhớ |

Nếu chỉ còn 2 phút: đọc **file 1** + **bảng ở mục 3 dưới đây**.

---

## 1. Tóm tắt 1 câu để mở đầu

> "Em làm hệ thống camera AI bám bắt đối tượng real-time trên nền SAM 2.1 + SAMURAI: chọn đối tượng
> bằng chuột, phân đoạn bằng mask, giữ được khi bị che khuất một phần, **mất dấu thì dừng chứ không
> bám sang người khác**, và **tự bám lại đúng người khi họ quay lại** — có đo FPS/độ trễ/chất lượng
> phân đoạn thật trên máy, báo cáo trung thực."

---

## 2. ĐÃ LÀM ĐƯỢC GÌ — đối chiếu 14 buổi của đề cương

| Buổi | Yêu cầu | Trạng thái | Bằng chứng |
|---|---|---|---|
| 1 | Nhận đề tài, mục tiêu, phạm vi, kế hoạch | ✅ | `spec.md`, `docs/adr/0001`, `docs/adr/0002` |
| 2 | Nghiên cứu tổng quan Camera AI, tracking | ✅ | `docs/research/01–05` (5 báo cáo) |
| 3 | Thiết kế kiến trúc hệ thống | ✅ | README "Kiến trúc (5 module)" + ADR-0001/0002 |
| 4 | Thu nhận & xử lý video (Camera USB/IP) | ✅ | `src/video_source.py`: webcam, **camera USB**, **RTSP**, **MJPEG-HTTP (điện thoại)**, video file, **thư mục frame** |
| 5 | Phân đoạn đối tượng (Segmentation Mask) | ✅ | `src/tracker_engine.py` (SAM 2.1 tiny), mask + bbox + điểm tin cậy mỗi frame |
| 6 | Lựa chọn & bám bắt, **duy trì định danh** | ✅ | `src/prompt_selector.py` (kéo chuột, phím `r`) + định danh qua SAM 2 object pointer |
| 7 | Bộ nhớ chuyển động (Motion Memory) | ✅ (dùng có sẵn, có đóng gói) | Kalman filter + memory bank của SAMURAI, bọc streaming trong `tracker_engine.py` |
| 8 | Lan truyền theo thời gian (Temporal Propagation) | ✅ (dùng có sẵn) | memory attention của SAM 2, chế độ per-frame streaming do mình viết |
| **9** | **Mất dấu + TÁI NHẬN DIỆN** | ✅ **vừa xong 22-10** | `src/reid.py` + `docs/adr/0003` — chi tiết ở mục 4 |
| 10 | Tối ưu real-time + đánh giá FPS/latency/CPU-GPU | ✅ | bảng mục 3; `--image-size`, `--smooth` 3 luồng, benchmark CPU vs Colab T4 |
| 11 | Giao diện + kiểm thử (chuyển động/che/ánh sáng) | ✅ | `src/visualizer.py` HUD 4 dòng tiếng Việt; 216 test; `scripts/experiment_occlusion.py` |
| 12–14 | Báo cáo, slide, bảo vệ | 🟡 **đang làm** | **24 file log** trong `docs/task/`, `docs/giai-thich-do-an.md`, `docs/team-contribution.md` |

**Tổng khối lượng:** ~**3 953 dòng** code chính (`src/` + `tools/` + `scripts/`), **3 267 dòng** test,
**20 file test / 216 test pass**, 9 ticket (8 xong + 1 đang làm 8/9), **3 ADR**.

---

## 3. SỐ LIỆU THẬT để nói trong họp (không bịa)

### Tốc độ — đo trên chính máy này (CPU, không GPU rời)

| Cấu hình | ms/frame | FPS | Ghi chú |
|---|---|---|---|
| 720p, image_size 1024 (mặc định) | 5 047 | **0,20** | chính xác nhất, dùng xuất ảnh cho báo cáo |
| 720p, image_size 384 + `--smooth` | 445 | **2,25** | cấu hình demo trên laptop |
| 720p, image_size 384 + **tái nhận diện** | **292** | **3,40** | đo hôm 22-10 |
| **Colab GPU T4** 720p/1024 | 380 | 2,63 | video minh hoạ tốc độ GPU |
| **Colab GPU T4** 512 + reanchor 10 | **65** | **15,28** | cận dưới (T4 không bật được FlashAttention) |

→ **Nói rõ với thầy:** "GPU T4 nhanh hơn CPU laptop **~13×** ở cùng độ phân giải, **~78×** khi cả hai
đã tối ưu." Đây là số đo thật, ghi trong `README.md` mục 7.

### Chất lượng & độ ổn định

| Thí nghiệm | Kết quả |
|---|---|
| Che khuất **50%** (khung 12–17) | IoU 0,97 → **0,53** (vẫn không mất dấu) → **0,967** ngay khung đầu sau khi hết che |
| Che khuất **100%** | IoU 0,98 → 0,00 (mất dấu 6/6) → **0,984** ngay khung sau, mất dấu **0/12** |
| Đổi `image_size` 1024 → 384 | nhanh ~6–10×, IoU khi có che giảm 0,981 → 0,861 |
| **Tái nhận diện** (chuỗi frame mặt → màn đen → mặt) | `tracking → lost (đóng băng) → tracking` với **cosine 0,560** ≥ ngưỡng 0,363 ✅ |

### Hạn chế đo được của SAM 2 (rất nên nói — chứng tỏ hiểu bài)

- Độ trễ **tăng dần** khi chạy lâu: 3,4 s (memory 1 frame) → 8,3 s (memory 8 frame) — vì chi phí
  propagate tỉ lệ với `non_cond_frame_outputs`.
- **SAM 2 luôn trả mask cho bất kỳ ô nào** (kể cả nền trống: mask 1,2% khung, score 17,8 vs 22,6)
  → nên phải có HUD "điểm tin cậy" + cảnh báo, không thể "chặn" được.
- **Mất dấu thì bộ nhớ bám sang người khác** (identity switch) — chính là lý do phải làm re-ID.

---

## 4. Việc vừa làm (nói kỹ nếu thầy hỏi "dạo này làm gì")

**Vấn đề thật gặp khi demo 2 người:** chọn mặt A → A ra khỏi khung → báo MẤT DẤU → **nó bám sang mặt B**.

**Đã sửa bằng 3 lớp:**
1. **Cảnh báo** khi ô bao nhảy > 25% đường chéo khung (`identity_guard.py`).
2. **Đóng băng khi mất dấu**: mask rỗng 2 frame liên tiếp ⇒ **ngừng lan truyền** ⇒ bộ nhớ không thể bám sang B (`src/reid.py`).
3. **Tái nhận diện khuôn mặt**: YuNet (phát hiện mặt) + SFace (embedding 128-D), so cosine với **tập mẫu**
   của A (lấy max), khớp ngưỡng ⇒ bám lại đúng A. **Không thêm thư viện nào** (dùng OpenCV có sẵn).

**Bằng chứng:**
- Chạy pipeline thật: `tracking → lost → tracking` + `reid_score=0,560` + `reacquired=1` ✅
- Đo cùng 1 người, mặt nhỏ 42×62 px: cosine 0,199–0,723 ⇒ **phải lưu nhiều mẫu + lấy max**
  (nếu chỉ lưu 1 mẫu thì trượt) → quyết định này ghi ở `docs/adr/0003`.
- Chạy 1 lệnh: `./run demo`
- Test: **216 pass** (ruff sạch).

---

## 5. ƯU ĐIỂM (nói trước)

1. **Có đóng góp kỹ thuật riêng**: adapt SAM 2 từ *offline cả video* → **streaming từng frame từ webcam**
   (SAM 2 gốc không làm được việc này) — đây là điểm mạnh nhất.
2. **Đủ 3 trụ đề tài**: Segmentation Mask + Motion Memory + Temporal Propagation, có **số đo** cho từng cái.
3. **Trung thực số liệu** (ADR-0002): dám ghi 0,2 FPS trên CPU, không claim real-time giả; có video GPU
   thật để đối chiếu.
4. **Kỹ thuật phần mềm nghiêm túc**: 216 test, CI (ruff + test), 3 ADR ghi lý do quyết định, log theo ngày,
   `docs/team-contribution.md` phân định rõ **phần nào tự viết / phần nào dùng model có sẵn**.
5. **Giải quyết đúng lỗi người dùng gặp** (bám sang người khác) bằng cơ chế có thể đo, không phải "chỉnh cho đẹp".

## 6. NHƯỢC ĐIỂM (nói thật, đừng để thầy phát hiện)

1. **Không real-time trên laptop**: 0,2–3,4 FPS ⇒ demo là "slideshow có chủ đích". Muốn 15 FPS phải GPU.
2. **Tái nhận diện chưa hiệu chỉnh ngưỡng trên người thật** (mới đo trên frame benchmark + chuỗi giả lập).
3. **Không nhận lại được nếu không thấy khuôn mặt** (quay lưng, che kín, xa/mờ) — giới hạn của phương pháp,
   không phải bug; nhưng phải nói trước.
4. **Chưa đánh giá trên dataset chuẩn** (DAVIS/LaSOT): hiện chỉ có fixture tự sinh + IoU + số đo thực.
   ⇒ chưa so sánh được với bài báo khác (J&F, J).
5. **Chưa có Backend/Frontend web** — chỉ app desktop 1 process (xem mục 8, câu hỏi số 2).
6. Phụ thuộc model có sẵn (SAM 2.1 tiny, SAMURAI, YuNet, SFace) — không huấn luyện lại.

---

## 7. KHÓ KHĂN HIỆN TẠI (xếp theo mức chặn)

| # | Khó khăn | Ảnh hưởng | Đã thử gì |
|---|---|---|---|
| 1 | **Ngưỡng re-ID chưa chốt được** — cần **clip 2 người thật** (A rời khung rồi quay lại, B trong khung) | Không có số "tỉ lệ nhận lại đúng / nhận nhầm" ⇒ không chốt được ngưỡng, không có số cho báo cáo | Đo trên 8 frame có người thật (cosine 0,20–0,72) + chuỗi giả lập; chưa có clip A–B |
| 2 | **Máy không có GPU rời** (MSI Modern 14, Iris Xe) | Demo chỉ 0,2–3,4 FPS; không chứng minh được real-time | Đã tối ưu (image_size, smooth 3 luồng, reanchor) + đo trên Colab T4 |
| 3 | **WSL không thấy webcam** | Mỗi lần demo phải gắn lại usbipd (BUSID đổi sau reboot) hoặc dùng camera điện thoại | Đã viết `tools/find_phone_camera.py`, `scripts/usbipd_helper.py`, `./run cam attach` |
| 4 | **Chưa có dataset chuẩn để đánh giá** | Thiếu số liệu so sánh với literature | Chỉ có fixture tự sinh + 1 video benchmark + đo IoU khi che khuất |
| 5 | **Mâu thuẫn phạm vi** (spec cũ ghi "tái nhận diện ngoài phạm vi" nhưng **đề cương buổi 9 yêu cầu**) | Đã tự sửa spec + viết ADR-0003, **nhưng cần thầy xác nhận** để không bị bắt làm lại | Đã đối chiếu 14 buổi, ghi rõ bằng chứng |
| 6 | Chưa có Backend/Frontend web | Nếu thầy/hội đồng đòi web UI thì phải làm thêm | Đã phân tích: chưa cần, và thêm sẽ tăng độ trễ trên máy CPU yếu |

---

## 8. CẦN THẦY GIÚP GÌ — nói thẳng, 6 yêu cầu cụ thể

> Cách nói: *"Em xin thầy 6 việc, mỗi việc em nói rõ em cần gì và để làm gì ạ."*

1. **Chốt phạm vi: tái nhận diện có bắt buộc không?**
   Đề cương buổi 6 ghi "duy trì định danh đối tượng", buổi 9 ghi "xử lý mất dấu và **tái nhận diện đối tượng**".
   Em đã làm rồi (YuNet + SFace). **Em cần thầy xác nhận** là đúng phạm vi, để em không phải làm lại.

2. **Cho em 15–20 phút quay clip 2 người** (hoặc chỉ định 1 bạn đóng vai B).
   Em cần clip: A đứng → A ra khỏi khung → B vẫn trong khung → A quay lại. **Không có clip này em không
   chốt được ngưỡng nhận dạng và không có số liệu "tỉ lệ nhận lại đúng" cho báo cáo.**

3. **Chốt cách đánh giá chất lượng phân đoạn:** fixture tự sinh + số đo thực (như hiện tại) **có đủ không**,
   hay thầy yêu cầu chạy trên **dataset chuẩn** (DAVIS/LaSOT một phần)? Nếu cần, thầy chỉ em dataset nào
   và có cần tải về không (dữ liệu nặng).

4. **Xác nhận định nghĩa "real-time":** em đã ghi ADR-0002 là **không cam kết ≥10 FPS trên laptop**,
   báo cáo trung thực 0,2–3,4 FPS và dùng **Colab GPU** làm video minh hoạ tốc độ thật. **Thầy OK với
   cách này chứ ạ?** (Nếu thầy muốn real-time thật trên laptop thì em phải đổi hướng: XMem/EfficientTAM.)

5. **Xác nhận Colab T4 là hợp lệ** để lấy số GPU trong báo cáo, hay phải dùng máy GPU của trường?
   (Em không có GPU rời.)

6. **Góp ý báo cáo:** thầy cho em biết **chương nào cần số liệu gì** (FPS? IoU? bảng so sánh? biểu đồ?)
   để em đo đúng thứ được chấm, thay vì đo tràn lan.

**Thêm 1 câu nên hỏi (về Backend/Frontend):** *"Hệ thống hiện là app desktop 1 process, giao diện là cửa sổ
OpenCV có HUD đầy đủ (mask, ô bao, quỹ đạo, FPS, cảnh báo mất dấu). Thầy có yêu cầu **web backend/frontend**
không ạ? Nếu có em làm bản mỏng (FastAPI + stream MJPEG) khoảng 1–2 ngày; nếu không em dồn thời gian cho
phần đánh giá và báo cáo."*

---

## 9. Kịch bản nói 5 phút (đọc theo thứ tự này)

1. **Bài toán**: camera AI bám bắt 1 đối tượng theo thời gian thực, chọn bằng chuột, giữ được khi bị che.
2. **Kiến trúc 5 module**: VideoSource → TrackerEngine → (PromptSelector / Visualizer / MetricsLogger).
3. **Nền tảng**: SAM 2.1 tiny + config SAMURAI (Kalman + motion-aware memory) — **đóng góp của em là
   adapt sang streaming từng frame**, vì SAM 2 gốc chỉ chạy offline cả video.
4. **Kết quả đo** (bảng mục 3): CPU 0,2–3,4 FPS, GPU T4 nhanh 13–78×; che 50% IoU 0,53 rồi phục hồi 0,967.
5. **Vấn đề gặp thật + cách sửa**: chọn A mà bám sang B ⇒ 3 lớp (cảnh báo / đóng băng / tái nhận diện
   khuôn mặt), có số đo cosine 0,560 khi nhận lại.
6. **Trung thực**: 0,2 FPS trên CPU, không giấu; video GPU trên Colab để đối chiếu.
7. **Xin ý kiến**: 6 việc ở mục 8.

---

## 10. Câu thầy có thể hỏi — trả lời ngắn

| Câu hỏi | Trả lời |
|---|---|
| "Sao chậm vậy?" | Máy không có GPU rời; nút cổ chai là suy luận model (thu nhận frame chỉ 32 ms, suy luận 3 000–6 000 ms). Đã tối ưu 6–10× bằng `image_size`, có số GPU trên Colab T4 (nhanh 13–78×). |
| "Motion Memory em tự viết à?" | Không — em **đóng gói** Kalman + memory-bank selection của SAMURAI (đúng như spec ghi), phần em viết là **lớp streaming per-frame** quanh nó. Ghi rõ trong `docs/team-contribution.md`. |
| "Sao không dùng YOLO/nhẹ hơn?" | Đề tài yêu cầu **Segmentation Mask** (mask đúng hình dáng), không chỉ bbox; SAM 2/SAMURAI đã được chốt ở ADR-0001 sau khi so EdgeTAM/EfficientTAM/XMem. |
| "Đã real-time chưa?" | **Chưa trên laptop** (0,2–3,4 FPS) — báo cáo trung thực. Trên GPU T4 tối ưu được 15,28 FPS. |
| "Mất dấu thì sao?" | Mask rỗng 2 frame ⇒ **đóng băng, không bám sang người khác**; khi đối tượng quay lại thì **tự nhận lại** bằng embedding khuôn mặt (cosine ≥ ngưỡng). |
| "Nếu 2 người giống nhau?" | Có thể nhầm — đã ghi là giới hạn; giảm bằng ngưỡng cao hơn, đòi khớp liên tiếp, và cảnh báo ô bao nhảy. |
| "Test thế nào?" | 216 test tự động (pytest), có CI ruff + test; test nhanh ~20 s, full ~2 phút. |
| "Số liệu ở đâu?" | `README.md` mục 7 + `data/*_summary.json` + `data/charts/*.png` (biểu đồ latency/quỹ đạo/mất dấu). |
| "Có Backend không?" | Chưa — app 1 process, đã **phân lớp** lõi xử lý vs hiển thị qua callback injection (cắm web được mà không sửa lõi). |
| "Đóng góp mới là gì?" | (1) adapt SAM 2 → streaming realtime; (2) cơ chế đóng băng + tái nhận diện khuôn mặt để chống bám sang người khác; (3) bộ số đo trung thực CPU vs GPU + đánh đổi `image_size`. |

---

## 11. Sau buổi họp — ghi lại ngay

Vào `docs/task/` tạo file `23-10-2026-hop-gvhd.md` theo `docs/task/_template.md`, ghi:
- Thầy chốt gì (phạm vi re-ID? dataset? BE/FE? real-time?)
- Việc thầy giao thêm
- Việc phải làm lại (nếu có)

> Đừng để trôi — đây là căn cứ để trả lời "em đã làm theo góp ý của thầy" khi bảo vệ.
