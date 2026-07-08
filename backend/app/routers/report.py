from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter

from app.config import IOU_TABLE_CSV_PATH, METRICS_CSV_PATH as DATA_PATH
from app.models import (
    ConditionMetric,
    DatasetSummary,
    DiagnosisResult,
    ErrorTypeReport,
    RoiAssumptions,
    RoiEstimate,
)

router = APIRouter(prefix="/api", tags=["report"])

TYPE_LABELS = {
    "width": "가로 길이 오류",
    "height": "세로 길이 오류",
    "rotation": "회전각 오류",
    "translation_x": "중심점 가로 이동",
    "translation_y": "중심점 세로 이동",
    "scale": "스케일 오류",
}


def _load_metrics() -> pd.DataFrame:
    return pd.read_csv(DATA_PATH)


def _load_iou_table() -> pd.DataFrame:
    if not IOU_TABLE_CSV_PATH.exists():
        return pd.DataFrame(columns=["condition", "mean_iou", "mean_iou_drop_pct"])
    return pd.read_csv(IOU_TABLE_CSV_PATH)[["condition", "mean_iou", "mean_iou_drop_pct"]]


@router.get("/summary", response_model=DatasetSummary)
def get_summary() -> DatasetSummary:
    # MVP 데모용 값. 실제 서비스에서는 업로드된 데이터셋 스캔 결과로 대체.
    return DatasetSummary(
        total_images=412,
        total_objects=3184,
        suspected_error_count=247,
        quality_score=78,
        certified=False,
    )


@router.get("/conditions", response_model=list[ConditionMetric])
def get_conditions() -> list[ConditionMetric]:
    df = _load_metrics()
    iou_df = _load_iou_table()
    if not iou_df.empty:
        df = df.merge(iou_df, on="condition", how="left")
    baseline = df.loc[df["condition"] == "clean", "map50"].iloc[0]

    results: list[ConditionMetric] = []
    for _, row in df.iterrows():
        drop_pct = (baseline - row["map50"]) / baseline * 100
        results.append(
            ConditionMetric(
                condition=row["condition"],
                type=row["type"],
                magnitude=row["magnitude"],
                map50=row["map50"],
                map50_95=row["map50_95"],
                precision=row["precision"],
                recall=row["recall"],
                performance_drop_pct=round(drop_pct, 1),
                mean_iou=None if pd.isna(row.get("mean_iou")) else round(float(row["mean_iou"]), 4),
                mean_iou_drop_pct=None
                if pd.isna(row.get("mean_iou_drop_pct"))
                else round(float(row["mean_iou_drop_pct"]), 2),
            )
        )
    return results


@router.get("/roi-estimate", response_model=RoiEstimate)
def get_roi_estimate() -> RoiEstimate:
    assumptions = RoiAssumptions(
        dataset_labels=100_000,
        manual_review_minutes_per_label=0.5,
        reviewer_hourly_cost_krw=25_000,
        suspected_review_ratio=0.3,
        gpu_retrain_runs_without_aida=6,
        gpu_retrain_runs_with_aida=2,
        gpu_cost_per_run_krw=120_000,
    )
    hourly_cost = assumptions.reviewer_hourly_cost_krw
    manual_without = round(assumptions.dataset_labels * assumptions.manual_review_minutes_per_label / 60 * hourly_cost)
    manual_with = round(
        assumptions.dataset_labels
        * assumptions.suspected_review_ratio
        * assumptions.manual_review_minutes_per_label
        / 60
        * hourly_cost
    )
    gpu_without = assumptions.gpu_retrain_runs_without_aida * assumptions.gpu_cost_per_run_krw
    gpu_with = assumptions.gpu_retrain_runs_with_aida * assumptions.gpu_cost_per_run_krw

    return RoiEstimate(
        label="추정 예시",
        assumptions=assumptions,
        manual_review_cost_without_aida_krw=manual_without,
        manual_review_cost_with_aida_krw=manual_with,
        manual_review_savings_krw=manual_without - manual_with,
        gpu_cost_without_aida_krw=gpu_without,
        gpu_cost_with_aida_krw=gpu_with,
        gpu_savings_krw=gpu_without - gpu_with,
        total_savings_krw=(manual_without - manual_with) + (gpu_without - gpu_with),
        review_scope_reduction_pct=round((1 - assumptions.suspected_review_ratio) * 100, 1),
    )


@router.get("/diagnose", response_model=DiagnosisResult)
def get_diagnosis() -> DiagnosisResult:
    df = _load_metrics()
    baseline = df.loc[df["condition"] == "clean", "map50"].iloc[0]
    non_baseline = df[df["condition"] != "clean"].copy()
    non_baseline["drop_pct"] = (baseline - non_baseline["map50"]) / baseline * 100

    reports: list[ErrorTypeReport] = []
    for error_type, group in non_baseline.groupby("type"):
        worst = group.loc[group["drop_pct"].idxmax()]
        priority = "높음" if worst["drop_pct"] >= 15 else "중간" if worst["drop_pct"] >= 8 else "낮음"
        reports.append(
            ErrorTypeReport(
                error_type=error_type,
                label=TYPE_LABELS.get(error_type, error_type),
                max_performance_drop_pct=round(worst["drop_pct"], 1),
                review_priority=priority,
            )
        )

    reports.sort(key=lambda r: r.max_performance_drop_pct, reverse=True)

    return DiagnosisResult(
        dataset_name="sample_customer_dataset_v1",
        quality_score=78,
        certified=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
        error_reports=reports,
    )
