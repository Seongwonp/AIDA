from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter

from app.config import METRICS_CSV_PATH as DATA_PATH
from app.models import ConditionMetric, DatasetSummary, DiagnosisResult, ErrorTypeReport

router = APIRouter(prefix="/api", tags=["report"])

TYPE_LABELS = {
    "width": "가로 길이 오류",
    "height": "세로 길이 오류",
    "rotation": "회전각 오류",
}


def _load_metrics() -> pd.DataFrame:
    return pd.read_csv(DATA_PATH)


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
            )
        )
    return results


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
