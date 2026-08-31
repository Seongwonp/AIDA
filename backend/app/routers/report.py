"""experiment/가 만들어낸 metrics.csv(+iou_table.csv)를 읽어 대시보드용 API로 내보낸다.

데이터 흐름: experiment/run_all.py가 조건별로 학습·평가한 결과를
backend/app/data/metrics.csv에 쓰고, 이 파일이 그 CSV를 그대로 읽어 API 응답으로
변환한다. 즉 실험을 다시 돌려서 metrics.csv가 갱신되면, 여기 코드를 고치지 않아도
대시보드에 새 결과가 그대로 반영된다.
"""
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, HTTPException

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
    # 다중 클래스에서만 나온다 (experiment/config.py CLASS_SWAP_CONDITIONS)
    "class_swap": "클래스 오기입",
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


# ── 재검수 우선순위 기준 ────────────────────────────────────────────────────
# 예전 기준(15%/8% 고정)은 목업 데이터 시절 값이라, 실측 데이터에서는 최대
# 저하가 6%대여서 모든 유형이 "낮음"으로만 나왔다 — 데모에서 바로 티가 났다.
#
# 재보정은 두 가지를 쓴다:
#  1) 통계적 유의성 — 3-seed 실측에 표준편차가 있으므로 "이 저하가 학습
#     흔들림과 구분되는가"를 먼저 묻는다. 예: 세로 길이 오류의 0.99% 저하는
#     표준편차 0.89%로 1.1σ에 불과해, 크기만 보면 실재하는 듯하지만 사실은
#     노이즈와 구분되지 않는다. 이걸 "중간"으로 올리면 없는 문제에 검수
#     예산을 쓰게 만든다.
#  2) 상대적 크기 — 절대 %는 데이터셋·모델에 따라 스케일이 달라지므로,
#     관측된 최대 저하 대비 비율로 나눈다. 성능 패턴 DB가 갱신돼도 기준이
#     같이 따라간다(고정 상수였다면 또 어긋났을 것이다).
MIN_SIGNIFICANT_SIGMA = 2.0  # 이보다 작으면 노이즈와 구분 불가
HIGH_PRIORITY_FRACTION = 0.5  # 최대 저하의 절반 이상이면 높음
MEDIUM_PRIORITY_FRACTION = 0.25


def _load_aggregated_drops() -> dict[str, tuple[float, float]]:
    """조건별 (저하율 평균, 표준편차) — 3-seed 집계. 없으면 빈 dict.

    단일 시드 값(metrics.csv)보다 이쪽을 우선한다. 시드 하나짜리 관측은
    학습 흔들림을 그대로 안고 있어서, 우선순위를 매기는 근거로는 평균이
    맞다. 집계에 없는 조건은 호출부에서 metrics.csv 값으로 넘어간다.
    """
    if not AGG_METRICS_CSV_PATH.exists():
        return {}
    df = pd.read_csv(AGG_METRICS_CSV_PATH)
    if "drop_pct_std" not in df.columns or "drop_pct_mean" not in df.columns:
        return {}
    return {
        row["condition"]: (float(row["drop_pct_mean"]), float(row["drop_pct_std"]))
        for _, row in df.iterrows()
        if pd.notna(row.get("drop_pct_std")) and pd.notna(row.get("drop_pct_mean"))
    }


def _review_priority(drop_pct: float, worst_overall: float,
                     drop_std: float | None) -> tuple[str, str]:
    """(우선순위, 근거 문구). 근거를 함께 돌려주는 이유는, 등급만 보여주면
    고객이 "왜 이게 높음인가"를 확인할 방법이 없기 때문이다."""
    if drop_std is not None and drop_std > 0:
        sigma = drop_pct / drop_std
        if sigma < MIN_SIGNIFICANT_SIGMA:
            return "낮음", (
                f"저하 {drop_pct:.1f}%가 시드 간 편차({drop_std:.1f}%p)의 "
                f"{sigma:.1f}배에 불과해 학습 흔들림과 구분되지 않습니다"
            )

    if worst_overall <= 0:
        return "낮음", "성능 저하가 관측되지 않았습니다"

    share = drop_pct / worst_overall
    if share >= HIGH_PRIORITY_FRACTION:
        return "높음", (
            f"저하 {drop_pct:.1f}%로, 관측된 최대 저하({worst_overall:.1f}%)의 "
            f"{share * 100:.0f}% 수준입니다"
        )
    if share >= MEDIUM_PRIORITY_FRACTION:
        return "중간", (
            f"저하 {drop_pct:.1f}%로 중간 수준입니다 "
            f"(최대 저하 대비 {share * 100:.0f}%)"
        )
    return "낮음", (
        f"저하 {drop_pct:.1f}%로, 관측된 최대 저하({worst_overall:.1f}%) 대비 "
        f"{share * 100:.0f}%에 그칩니다"
    )


# 클래스 구성별 성능 패턴 DB. 신뢰도 프로파일과 같은 규칙으로 경로를 나눈다
# (experiment/config.py의 _csuffix).
def _metrics_path_for(profile_classes: list[str]):
    suffix = "" if profile_classes in ([], ["Car"]) else "_mc"
    return DATA_PATH.with_name(f"metrics{suffix}.csv")


def _required_types(df) -> set[str]:
    return set(df.loc[df["condition"] != "clean", "type"])


@router.get("/diagnose", response_model=DiagnosisResult)
def get_diagnosis(profile_classes: str = "") -> DiagnosisResult:
    """오류 유형별 재검수 우선순위 리포트.

    지금은 "성능 패턴 DB(metrics.csv) 자체"를 진단 예시로 그대로 보여주는
    단계다 — dataset_name이 실제 업로드된 고객 데이터셋이 아니라 고정값
    "sample_customer_dataset_v1"인 이유. 실제 서비스에서는 고객이 올린
    데이터셋을 같은 파이프라인으로 학습·평가해 나온 성능 벡터를 이 기준
    패턴과 비교해야 하는데, 그 업로드→비교 로직은 아직 구현 전이다
    (docs/09-getting-started.md "아직 안 된 것" 참고).
    """
    classes = [c for c in profile_classes.split(",") if c.strip()]
    metrics_path = _metrics_path_for(classes)
    if not metrics_path.exists():
        raise HTTPException(
            404, f"{metrics_path.name} 없음 — 이 클래스 구성의 성능 패턴 DB가 아직 없습니다."
        )
    df = pd.read_csv(metrics_path)
    baseline_rows = df.loc[df["condition"] == "clean", "map50"]
    if baseline_rows.empty:
        raise HTTPException(500, f"{metrics_path.name}에 clean 기준 행이 없습니다.")
    baseline = baseline_rows.iloc[0]
    non_baseline = df[df["condition"] != "clean"].copy()
    non_baseline["drop_pct"] = (baseline - non_baseline["map50"]) / baseline * 100

    # 3-seed 집계가 있으면 그 평균 저하율을 쓴다 (단일 시드 관측보다 미더움).
    # 집계는 Car 단일 구성에서만 돌렸으므로 다른 구성에서는 비어 있고, 그러면
    # 유의성 검사 없이 크기만으로 판정하게 된다 — rationale에 그렇게 적힌다.
    agg = _load_aggregated_drops() if not classes or classes == ["Car"] else {}
    non_baseline["drop_for_ranking"] = [
        agg[c][0] if c in agg else d
        for c, d in zip(non_baseline["condition"], non_baseline["drop_pct"])
    ]

    worst_overall = non_baseline["drop_for_ranking"].max()

    reports: list[ErrorTypeReport] = []
    for error_type, group in non_baseline.groupby("type"):
        # 유형별로 가장 저하가 큰 조건 하나만 대표값으로 뽑아 우선순위를 매김
        worst = group.loc[group["drop_for_ranking"].idxmax()]
        agg_entry = agg.get(worst["condition"])
        priority, rationale = _review_priority(
            drop_pct=worst["drop_for_ranking"],
            worst_overall=worst_overall,
            drop_std=agg_entry[1] if agg_entry else None,
        )
        reports.append(
            ErrorTypeReport(
                error_type=error_type,
                label=TYPE_LABELS.get(error_type, error_type),
                max_performance_drop_pct=round(worst["drop_for_ranking"], 1),
                review_priority=priority,
                priority_rationale=rationale,
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
