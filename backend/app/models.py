"""API 응답 스키마. frontend/src/types.ts와 필드가 1:1로 대응해야 한다 —
한쪽만 고치면 타입이 어긋난다.
"""
from pydantic import BaseModel


class ConditionMetric(BaseModel):
    # metrics.csv 한 행 + iou_table.csv 조인 결과. mean_iou* 는 iou_table.csv가
    # 없으면 None으로 내려간다(IoU 계산을 아직 안 돌린 환경 대비).
    condition: str
    type: str
    magnitude: float
    map50: float
    map50_95: float
    precision: float
    recall: float
    performance_drop_pct: float
    mean_iou: float | None = None
    mean_iou_drop_pct: float | None = None


class ConditionMetricAgg(BaseModel):
    condition: str
    type: str
    magnitude: float
    n_seeds: int
    map50_mean: float
    map50_std: float
    map50_95_mean: float
    map50_95_std: float
    precision_mean: float
    precision_std: float
    recall_mean: float
    recall_std: float
    drop_pct_mean: float | None = None
    drop_pct_std: float | None = None


class DatasetSummary(BaseModel):
    total_images: int
    total_objects: int
    suspected_error_count: int
    quality_score: int
    certified: bool


class ErrorTypeReport(BaseModel):
    error_type: str
    label: str
    max_performance_drop_pct: float
    review_priority: str
    # 등급만 보여주면 "왜 이게 높음인가"를 확인할 방법이 없어서 근거를 함께 내려준다
    priority_rationale: str = ""


class DiagnosisResult(BaseModel):
    dataset_name: str
    quality_score: int
    certified: bool
    generated_at: str
    error_reports: list[ErrorTypeReport]


class RoiAssumptions(BaseModel):
    dataset_labels: int
    manual_review_minutes_per_label: float
    reviewer_hourly_cost_krw: int
    suspected_review_ratio: float
    gpu_retrain_runs_without_aida: int
    gpu_retrain_runs_with_aida: int
    gpu_cost_per_run_krw: int


class UploadedDatasetInfo(BaseModel):
    dataset_id: str
    uploaded_at: str
    num_images: int
    num_labels: int


class PerformanceVector(BaseModel):
    map50: float
    map50_95: float
    precision: float
    recall: float


class ErrorTypeCandidate(BaseModel):
    error_type: str
    label: str
    closest_condition: str
    closest_magnitude: float
    distance: float


class UploadDiagnosisResult(BaseModel):
    dataset_id: str
    generated_at: str
    performance_vector: PerformanceVector
    quality_score: int
    candidates: list[ErrorTypeCandidate]
    caveat: str


class SuspicionTypeCount(BaseModel):
    suspicion: str
    label: str
    count: int
    ratio: float


class ReviewQueueItem(BaseModel):
    """재검수 대기열 한 줄 — "몇 번 이미지의 몇 번 박스를 왜 다시 봐야 하는지"."""
    rank: int
    image: str
    label_index: int | None  # 누락 의심이면 가리킬 라벨이 없어 None
    suspicion: str
    label: str
    severity: float
    detail: str


class LabelDiagnosisResult(BaseModel):
    dataset_id: str
    generated_at: str
    total_labels: int
    total_findings: int
    suspicion_ratio: float
    dominant_type: str | None
    dominant_label: str | None
    dominant_ratio: float
    systematic: bool
    by_type: list[SuspicionTypeCount]
    review_queue: list[ReviewQueueItem]
    caveat: str


class RoiEstimate(BaseModel):
    label: str
    assumptions: RoiAssumptions
    manual_review_cost_without_aida_krw: int
    manual_review_cost_with_aida_krw: int
    manual_review_savings_krw: int
    gpu_cost_without_aida_krw: int
    gpu_cost_with_aida_krw: int
    gpu_savings_krw: int
    total_savings_krw: int
    review_scope_reduction_pct: float


class ReliabilityProfileInfo(BaseModel):
    """고를 수 있는 유형 신뢰도 보정 프로파일.

    유형 신뢰도는 도메인마다 다르다 — 특히 "그 유형이 없을 때"의 값이
    크게 흔들린다(docs/21 L). name=""은 기본값(KITTI Car 실측)을 뜻한다.
    """
    name: str
    label: str
    types: list[str]
    # 이 상수를 잰 클래스 구성. 진단도 같은 구성으로 돌아간다.
    classes: list[str] = []
    # 이 구성의 기준 모델이 서버에 있는가. False면 고를 수는 있어도 진단은 실패한다.
    available: bool = True
