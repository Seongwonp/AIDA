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
    # 라벨에 실제로 등장하는 클래스 인덱스. 기준 모델이 이보다 적게 알면
    # 나머지는 오탐도 아니고 아예 검사되지 않는다 — 화면에 흔적이 없어서
    # "문제 없음"과 구별이 안 된다(docs/21 AD 반영).
    label_class_ids: list[int] = []
    # 이 데이터에 맞는 기준 모델. None이면 기본값으로 충분하다는 뜻.
    suggested_profile: str | None = None
    suggestion_reason: str = ""


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


class TypeRobustness(BaseModel):
    """이 오류 유형이 기준 모델의 상태에 얼마나 좌우되는가 (docs/21 V·Y 실측).

    진단은 기준 모델의 예측을 자로 삼아 라벨을 잰다. 그 자가 고객 데이터와
    안 맞으면 유형마다 다르게 무너진다 — 어떤 판정은 예측을 정밀한 자로
    쓰고, 어떤 판정은 위치만 아는 닻으로 쓰기 때문이다.
    """
    suspicion: str
    label: str
    # 도메인이 맞는 깨끗한 기준 모델이 있을 때의 실측 정밀도
    matched_domain: float
    # 다른 도메인의 기준 모델을 댔을 때 (지금 업로드 경로가 하는 일)
    shifted_domain: float
    # 도메인이 어긋나도 쓸 만한가
    robust: bool
    # 아예 다른 데이터셋에서 잰 값 (docs/21 AI). shifted_domain은 같은 KITTI
    # 안에서 프레임 구성만 바꿔 잰 것이라 낙관적이다 — 진짜 도메인 이동은
    # 이쪽이다. 안 잰 유형은 None.
    cross_dataset: float | None = None


class RulerInfo(BaseModel):
    """이 진단에 자로 쓴 기준 모델 (docs/21 AA·AD).

    AA와 AD가 같은 말을 한다: **대상 분포에서의 실력이 전부다.** 학습량도
    클래스 폭도 그 자체로는 진단 품질을 정하지 않는다. 그래서 어느 자를
    썼는지가 결과를 읽는 데 필요한 정보인데, 지금까지는 결과에 남지 않아
    사용자가 알 수 없었다.
    """
    # 고른 신뢰도 프로파일. ""이면 기본값(KITTI Car 단일 클래스).
    profile: str
    profile_label: str
    # 이 자가 아는 클래스. 데이터에 이보다 많은 클래스가 있으면 못 보는 게 있다.
    classes: list[str]
    # 가중치가 어디서 왔는가 (실행 폴더 이름)
    weights: str
    # 클래스 대조를 하는가. 자가 아는 클래스 수가 데이터와 다르면 끈다 —
    # 안 그러면 멀쩡한 라벨을 전부 클래스 오기입으로 부른다(docs/21 Z).
    class_aware: bool
    # 같은 종류의 자를 학습 시드만 바꿔 만들었을 때 상위 10% 정밀도의
    # 표준편차(%p, docs/21 AD). 평균만 보면 안 보이는 값이다 — 고객마다
    # 기준 모델을 새로 학습한다면 편차가 작은 쪽이 약속하기 쉽다.
    seed_spread_pp: float
    # 업로드된 라벨에 이 자가 모르는 클래스 인덱스가 있는가
    unknown_class_ids: list[int] = []


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
    # 이 데이터셋에서 실제로 나온 유형들에 대해서만 채운다
    robustness: list[TypeRobustness] = []
    # 어느 자로 쟀는가. 예전 진단 결과에는 없으므로 None을 허용한다.
    ruler: RulerInfo | None = None
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
