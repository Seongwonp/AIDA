from pydantic import BaseModel


class ConditionMetric(BaseModel):
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
