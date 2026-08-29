"""experiment/가 만들어낸 metrics.csv(+iou_table.csv)를 읽어 대시보드용 API로 내보낸다.

데이터 흐름: experiment/run_all.py가 조건별로 학습·평가한 결과를
backend/app/data/metrics.csv에 쓰고, 이 파일이 그 CSV를 그대로 읽어 API 응답으로
변환한다. 즉 실험을 다시 돌려서 metrics.csv가 갱신되면, 여기 코드를 고치지 않아도
대시보드에 새 결과가 그대로 반영된다.
"""
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter

from app.config import (
    AGG_METRICS_CSV_PATH,
    IOU_TABLE_CSV_PATH,
    METRICS_CSV_PATH as DATA_PATH,
    OBB_AGG_METRICS_CSV_PATH,
    OBB_METRICS_CSV_PATH,
)
from app.models import (
    ConditionMetric,
    ConditionMetricAgg,
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
    "missing": "라벨 누락",
    "duplicate": "라벨 중복",
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
    # 아래 숫자는 실제 고객 계약 단가가 아니라 발표용 예시 가정값이다
    # (사업계획서의 라벨링 단가 벤치마크, docs/13-ppt-visuals-checklist.md 5번 참고).
    # 실제 절감률은 PoC를 통해 검증할 예정 — RoiEstimateCard.tsx의 캡션에도 명시돼 있음.
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


def _load_agg(csv_path) -> list[ConditionMetricAgg]:
    if not csv_path.exists():
        return []
    df = pd.read_csv(csv_path)
    results = []
    for _, row in df.iterrows():
        results.append(ConditionMetricAgg(
            condition=row["condition"],
            type=row["type"],
            magnitude=row["magnitude"],
            n_seeds=int(row["n_seeds"]),
            map50_mean=row["map50_mean"],
            map50_std=row["map50_std"],
            map50_95_mean=row["map50_95_mean"],
            map50_95_std=row["map50_95_std"],
            precision_mean=row["precision_mean"],
            precision_std=row["precision_std"],
            recall_mean=row["recall_mean"],
            recall_std=row["recall_std"],
            drop_pct_mean=None if pd.isna(row.get("drop_pct_mean")) else row["drop_pct_mean"],
            drop_pct_std=None if pd.isna(row.get("drop_pct_std")) else row["drop_pct_std"],
        ))
    return results


@router.get("/conditions/aggregated", response_model=list[ConditionMetricAgg])
def get_conditions_aggregated() -> list[ConditionMetricAgg]:
    """다중 seed 집계 결과(mean ± std). aggregate_seeds.py 실행 전엔 빈 배열."""
    return _load_agg(AGG_METRICS_CSV_PATH)


@router.get("/obb/conditions/aggregated", response_model=list[ConditionMetricAgg])
def get_obb_conditions_aggregated() -> list[ConditionMetricAgg]:
    return _load_agg(OBB_AGG_METRICS_CSV_PATH)


@router.get("/obb/conditions", response_model=list[ConditionMetric])
def get_obb_conditions() -> list[ConditionMetric]:
    """OBB 실험 결과(metrics_obb.csv)를 반환한다.

    metrics_obb.csv가 없으면 빈 배열을 반환한다 — run_obb.py 실행 전에는 데이터 없음.
    """
    if not OBB_METRICS_CSV_PATH.exists():
        return []

    df = pd.read_csv(OBB_METRICS_CSV_PATH)
    baseline_rows = df[df["condition"] == "obb_clean"]["map50"]
    if baseline_rows.empty:
        return []
    baseline = baseline_rows.iloc[0]

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
                mean_iou=None,
                mean_iou_drop_pct=None,
            )
        )
    return results


@router.get("/diagnose", response_model=DiagnosisResult)
def get_diagnosis() -> DiagnosisResult:
    """오류 유형별 재검수 우선순위 리포트.

    지금은 "성능 패턴 DB(metrics.csv) 자체"를 진단 예시로 그대로 보여주는
    단계다 — dataset_name이 실제 업로드된 고객 데이터셋이 아니라 고정값
    "sample_customer_dataset_v1"인 이유. 실제 서비스에서는 고객이 올린
    데이터셋을 같은 파이프라인으로 학습·평가해 나온 성능 벡터를 이 기준
    패턴과 비교해야 하는데, 그 업로드→비교 로직은 아직 구현 전이다
    (docs/09-getting-started.md "아직 안 된 것" 참고).
    """
    df = _load_metrics()
    baseline = df.loc[df["condition"] == "clean", "map50"].iloc[0]
    non_baseline = df[df["condition"] != "clean"].copy()
    non_baseline["drop_pct"] = (baseline - non_baseline["map50"]) / baseline * 100

    reports: list[ErrorTypeReport] = []
    for error_type, group in non_baseline.groupby("type"):
        # 유형별로 가장 저하가 큰 조건 하나만 대표값으로 뽑아 우선순위를 매김
        worst = group.loc[group["drop_pct"].idxmax()]
        # 임계값(15%/8%)은 초기 목업 데이터 기준으로 잡은 값이라, 지금 실측
        # 데이터(최대 저하가 6%대)에서는 전 조건이 "낮음"으로만 나온다 — 실제
        # 서비스에서는 도메인별 데이터로 재보정이 필요하다.
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
