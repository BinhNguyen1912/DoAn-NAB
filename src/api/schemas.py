"""
Schemas Pydantic — NGUỒN SỰ THẬT DUY NHẤT của hợp đồng API.

Chức năng: khai báo kiểu dữ liệu request/response; FastAPI dùng để validate và sinh
           `/openapi.json` (frontend sinh type TypeScript từ đó).
Input  : dữ liệu HTTP (JSON body / form field) do client gửi.
Output : model đã validate, hoặc lỗi 422 tự động của FastAPI.
Lưu ý  : đổi tên khoá ở đây là ĐỔI HỢP ĐỒNG với `web/` — sửa phải sửa cả hai phía.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Trạng thái vòng đời của một job xử lý video
JobState = Literal["uploaded", "queued", "running", "done", "error"]

# Cue tái nhận diện: khuôn mặt / đặc trưng vật thể / thử mặt trước rồi tới vật thể
ReidCue = Literal["face", "object", "both"]


class BBox(BaseModel):
    """Ô chọn đối tượng theo pixel của frame đầu video."""

    x: int = Field(ge=0, description="toạ độ x góc trên-trái")
    y: int = Field(ge=0, description="toạ độ y góc trên-trái")
    w: int = Field(gt=0, description="chiều rộng ô")
    h: int = Field(gt=0, description="chiều cao ô")


class PointPrompt(BaseModel):
    """Điểm chỉ định hỗ trợ phân đoạn (positive/negative prompt)."""

    x: float = Field(ge=0, description="toạ độ x (pixel)")
    y: float = Field(ge=0, description="toạ độ y (pixel)")
    # `ge/le`: `label=2` trước đây qua được Pydantic rồi ném `ValueError` trong
    # `tracker_engine.start` (`np.isin`) ⇒ cả phiên live chết thay vì trả 422 (review 22-11, P3).
    # BẮT BUỘC (bỏ `default=1`): để mặc định thì client quên `label` biến thành điểm DƯƠNG trong
    # im lặng — đúng kiểu "gửi mà không ai biết" (review độc lập 22-11, P3).
    label: int = Field(..., ge=0, le=1,
                       description="1 = positive (thuộc vật thể), 0 = negative (thuộc nền)")


class TrackParams(BaseModel):
    """Tham số truyền xuống pipeline (tương ứng flag của tools/run_live.py)."""

    image_size: Optional[int] = Field(
        default=None, ge=64, le=1024,
        description="độ phân giải đầu vào của model; 192 ≈ 10 FPS, 256 ≈ 6,5 FPS trên CPU",
    )
    max_frames: Optional[int] = Field(default=None, ge=1, description="giới hạn số frame xử lý")
    max_trajectory: Optional[int] = Field(default=None, ge=1, description="số điểm quỹ đạo tối đa")
    reid: bool = Field(default=False, description="bật tái nhận diện khi mất dấu")
    cue: ReidCue = Field(default="object", description="cue tái nhận diện (mặc định bám VẬT)")


class JobCreateResponse(BaseModel):
    """Trả về ngay sau khi upload xong — chưa xử lý gì."""

    job_id: str
    state: JobState


class SelectRequest(BaseModel):
    """Chọn đối tượng cần bám trên frame đầu → bắt đầu xử lý."""

    bbox: BBox
    points: Optional[list[PointPrompt]] = Field(
        default=None,
        description="danh sách điểm chỉ định (positive: 1, negative: 0)",
    )


class SelectLiveRequest(BaseModel):
    """Chọn hoặc chọn lại đối tượng cho phiên live đang chạy."""

    bbox: BBox
    points: Optional[list[PointPrompt]] = Field(
        default=None,
        description="danh sách điểm chỉ định (positive: 1, negative: 0)",
    )


class JobStatusResponse(BaseModel):
    """Trạng thái đầy đủ của một job (frontend poll mỗi giây).

    Lưu ý: tên khác `JobStatus` của tầng miền (`src/api/domain.py`) là CỐ Ý — DTO của hợp đồng
    HTTP không được lẫn với thực thể miền.
    """

    job_id: str
    state: JobState
    progress: int = Field(ge=0, le=100, description="phần trăm tiến trình")
    message: str
    created_at: str
    bbox: Optional[list[int]] = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    summary: Optional[dict] = None


class JobListItem(BaseModel):
    """Một dòng trong danh sách job (không kèm summary cho nhẹ)."""

    job_id: str
    state: JobState
    progress: int = Field(ge=0, le=100)
    message: str
    created_at: str


# --------------------------------------------------------------------------- live


class LiveStartRequest(BaseModel):
    """Yêu cầu bắt đầu phát trực tiếp từ một nguồn frame."""

    source: str = Field(
        default="0",
        description="0 = webcam | rtsp://IP:554/stream | http://.../snapshot.jpg | đường dẫn video",
        min_length=1,
    )
    mode: Literal["raw", "track"] = Field(
        default="raw",
        description="raw = chỉ phát khung hình | track = bám đối tượng bằng model (cần bbox)",
    )
    bbox: Optional[BBox] = Field(
        default=None,
        description="ô chọn đối tượng cho mode=track (bắt buộc khi track)",
    )
    points: Optional[list[PointPrompt]] = Field(
        default=None,
        description="danh sách điểm chỉ định cho mode=track (positive: 1, negative: 0)",
    )
    image_size: Optional[int] = Field(
        default=None, ge=64, le=1024,
        description="độ phân giải model cho mode=track (mặc định 192 ≈ 10 FPS trên CPU)",
    )
    mask_smoothing: Optional[float] = Field(
        default=None, gt=0.0, le=1.0,
        description="mode=track: trọng số mask MỚI khi trộn theo thời gian; 1.0 = tắt (mặc định, "
                    "đo 10-11: bật không cải thiện độ êm mà thêm trễ)",
    )
    vos_every: Optional[int] = Field(
        default=None, ge=1, le=30,
        description="mode=track: chạy model mỗi N frame, các frame còn lại dùng LK (mặc định 3). "
                    "1 = chạy model mọi frame (mask tươi nhất nhưng hình chậm)",
    )


class LiveStatusResponse(BaseModel):
    """Trạng thái phiên phát trực tiếp (frontend poll mỗi giây để hiện FPS/trạng thái)."""

    state: Literal["stopped", "loading", "running", "error"]
    source: str
    device: str = Field(
        default="",
        description="thiết bị model THẬT SỰ chạy: 'cpu' | 'cuda' (worker báo); '' = chưa biết "
                    "(chế độ raw hoặc worker bản cũ) — chuỗi rỗng KHÔNG được đọc thành 'cpu'",
    )
    frames: int = Field(ge=0, description="số frame MỚI đã đọc từ khi bắt đầu (chỉ đếm khi nội "
                                           "dung đổi — cảnh tĩnh thì con số đứng yên)")
    measured_fps: float = Field(ge=0, description="FPS THỰC ĐO trong 2 giây gần nhất")
    display_fps: float = Field(default=0, ge=0,
                               description="FPS PHÁT do chính worker đo (nguồn gốc số trong báo cáo); "
                                           "0 khi nguồn không báo")
    mask_fps: float = Field(default=0, ge=0,
                            description="nhịp MASK MỚI (số lần model chạy/giây) — nhỏ hơn "
                                        "measured_fps khi chạy hybrid VOS + LK")
    mask_age_total_ms: float | None = Field(
        default=None, ge=0,
        description="Tuổi dữ liệu ảnh của mask ĐANG HIỂN THỊ (ms) = queue + pre + vos + post + age "
                    "của mẫu cuối; `null` = CHƯA ĐO (worker bản cũ), KHÁC 0 = mask tươi tuyệt đối",
    )
    mask_age_p95: float | None = Field(
        default=None, ge=0,
        description="Phân vị 95 tuổi dữ liệu trên cửa sổ `age_n` mẫu; `null` khi chưa đủ mẫu",
    )
    age_n: int = Field(default=0, ge=0, description="số mẫu của cửa sổ tuổi dữ liệu (0 ⇒ chưa đo)")
    cau_hinh_lech: list[str] | None = Field(
        default=None,
        description="Khoá mà model chạy KHÁC cấu hình yêu cầu (vd ['image_size']); `null` = CHƯA BIẾT "
                    "(worker bản cũ / khoá null); `[]` = không khoá nào lệch — NHƯNG `[]` + "
                    "`image_size_hieu_luc == null` = CHƯA KIỂM ĐƯỢC, không phải 'đã khớp'",
    )
    image_size_hieu_luc: int | None = Field(
        default=None,
        description="`image_size` model THẬT SỰ dùng (đọc từ predictor); `null` = CHƯA kiểm được — "
                    "khi đó `cau_hinh_lech == []` KHÔNG chứng minh model chạy đúng cấu hình",
    )
    bam: str | None = Field(
        default=None,
        description="CÓ BẰNG CHỨNG về vật hay không (KHÁC `state`: `state` chỉ là tiến trình). "
                    "`tracking` = mask/VOS/LK đang quan sát được vật; `no_evidence` = ô hiển thị "
                    "là suy diễn ⇒ worker KHÔNG vẽ ô; `nghi_doi_tuong` = ô bao nhảy vô lý "
                    "(nghi bám sang đối tượng khác) ⇒ từ 23-11 worker VẼ ô NÉT ĐỨT (không tô mask) "
                    "tới khi chọn lại hoặc xác nhận "
                    "(`POST /api/live/confirm`); `null` = CHƯA BIẾT (worker bản cũ / frame đầu) — "
                    "KHÔNG được đọc thành 'đang bám'",
    )
    bam_ly_do: str | None = Field(
        default=None,
        description="Vì sao mất bằng chứng. Hiện CHỈ có `'mask_rong'` (model không thấy vật; bản nháp "
                    "từng có `'lk_tu_choi'` nhưng ĐO ĐƯỢC là báo oan 74 % frame nên đã bỏ) — `null` = "
                    "không áp dụng",
    )
    nghi_doi_tuong: bool = Field(
        default=False,
        description="Cổng nhảy CÓ NHỚ: `true` = worker đang NGHI đã bám sang đối tượng khác ⇒ từ 23-11 "
                    "worker VẼ Ô NÉT ĐỨT màu vàng + nhãn 'NGHI' (không tô mask, không vẽ quỹ đạo) "
                    "chứ KHÔNG ẩn ô nữa. UI phải hiện banner + nút 'vẫn đúng' "
                    "(`POST /api/live/confirm`) — im lặng thì người xem tưởng hệ hỏng",
    )
    nghi_doi_tuong_n: int = Field(
        default=0, ge=0,
        description="Số frame ĐÃ PHÁT trong trạng thái nghi đổi đối tượng (`0` = chưa từng nghi)",
    )
    bam_no_evidence_n: int = Field(
        default=0, ge=0,
        description="Số frame ĐÃ PHÁT ở trạng thái no_evidence (đếm được, không suy ra) — "
                    "`bam_no_evidence_n == 0` + `bam == 'tracking'` là 'chưa từng mất bằng chứng'",
    )
    stability: float | None = Field(
        default=None, ge=0, le=1,
        description="IoU trung bình giữa hai mask liên tiếp (1 = không nhấp nháy). `null` = CHƯA ĐO "
                    "(xem `stability_n`), KHÁC với `0` = đo được 0 / đang mất dấu")
    stability_n: int = Field(default=0, ge=0,
                             description="số mẫu của cửa sổ IoU độ ổn định (0 ⇒ `stability` là null)")
    latency_ms: float = Field(default=0, ge=0, description="độ trễ suy luận gần nhất (ms)")
    empty_runs: int = Field(default=0, ge=0,
                            description="số lần model trả mask RỖNG (mất dấu thật) từ đầu phiên "
                                        "— bộ đếm TRỌN ĐỜI, không bao giờ giảm")
    empty_frac_window: float | None = Field(
        default=None, ge=0, le=1,
        description="tỉ lệ lần model trả mask RỖNG trong 200 lần chạy GẦN NHẤT (null = chưa đủ mẫu). "
                    "Đây mới là số nói 'hiện tại có đang mất dấu không'")
    empty_window_n: int = Field(default=0, ge=0, description="số mẫu của cửa sổ trên (0 = chưa có)")
    drift_p05: float | None = Field(
        default=None, ge=0, le=1,
        description="phân vị 5 % của IoU(ô bao đã phát, ô bao VOS sửa lại) trên tối đa 200 MẪU "
                    "DRIFT gần nhất (mẫu bị bỏ khi hộp VOS suy biến, nên `drift_n` có thể nhỏ hơn "
                    "`vos_runs`) — ĐỘ TỰ NHẤT QUÁN, KHÔNG phải độ chính xác; null khi < 30 mẫu")
    drift_n: int = Field(default=0, ge=0, description="số mẫu drift (0 ⇒ chưa đo, không phải 0,0)")
    suc_khoe: dict | None = Field(
        default=None,
        description="cờ phán quyết chất lượng bám (ticket #14): {co: ok|model_lost|drift_trend|"
                    "not_measured, ly_do, p05, n, empty_frac, cua_so, nguong_vao, nguong_ra}. "
                    "`p05` ở đây dùng CỬA SỔ RIÊNG (30 mẫu), KHÁC `drift_p05` (200 mẫu). "
                    "null = worker bản cũ CHƯA có cờ — không phải 'ok'")
    suc_khoe_cau: str | None = Field(
        default=None, description="câu tiếng Việt cho HUD; null khi cờ là `ok` (không chiếm chỗ)")
    message: str


class LiveSourceCandidate(BaseModel):
    """Một nguồn frame mà backend DÒ được, kèm cờ đã kiểm bằng thử thật."""

    source: str = Field(description="giá trị truyền cho /api/live/start (index webcam | URL | đường dẫn)")
    label: str = Field(description="tên hiện trên UI — người dùng chọn theo nhãn, không theo URL")
    kind: Literal["camera", "relay", "file"] = Field(description="loại nguồn (để UI gắn nhãn)")
    available: bool = Field(description="backend đã THỬ và dùng được tại thời điểm dò. Đây KHÔNG "
                                       "phải 'đang chạy' — chỉ phiên live mới chứng minh được điều đó")
    check: str = Field(default="", description="bằng chứng đã kiểm (vd 'nhận được ảnh JPEG') — để UI "
                                               "hiện phép đo, không hứa 'chắc chắn chạy'")
    latency_ms: int = Field(default=0, ge=0, description="thời gian dò nguồn này (ms)")
    note: str = Field(default="", description="lý do không dò được (vd 'đang có phiên live')")


class LiveSourcesResponse(BaseModel):
    """Kết quả dò nguồn — UI dùng `suggested` để tự điền ô 'Nguồn frame'."""

    suggested: str = Field(default="", description="nguồn NÊN dùng ngay ('' = không dò được nguồn nào)")
    suggested_kind: str = Field(default="", description="loại của nguồn gợi ý: camera|relay|file — "
                                                       "rỗng = không có gợi ý")
    checked_at: str = Field(default="", description="thời điểm dò (giờ máy chủ) — dò cũ ≠ dò mới")
    budget_ms: int = Field(default=0, ge=0, description="ngân sách thời gian của một lần dò (ms)")
    candidates: list[LiveSourceCandidate] = Field(default_factory=list)
