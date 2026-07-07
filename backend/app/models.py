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
