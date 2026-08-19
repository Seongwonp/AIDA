"""다중 seed 결과 집계: mean ± std 계산.

metrics_multi_seed.csv + metrics_obb_multi_seed.csv를 읽어
조건별 평균·표준편차를 metrics_agg.csv / metrics_obb_agg.csv에 저장한다.
백엔드 /api/conditions/aggregated 엔드포인트가 이 파일을 읽는다.

사용 예:
  python aggregate_seeds.py
  python aggregate_seeds.py --min-seeds 2   # 최소 seed 수 미달 조건 경고
"""
import argparse

import pandas as pd

import config

METRICS = ["map50", "map50_95", "precision", "recall"]


def aggregate(multi_csv, agg_csv, label: str, min_seeds: int) -> None:
    if not multi_csv.exists():
        print(f"[{label}] {multi_csv} 없음 — 건너뜀")
        return

    df = pd.read_csv(multi_csv)
    n_seeds = df["error_seed"].nunique()
    print(f"[{label}] {n_seeds}개 seed, {len(df)}행 로드 → {multi_csv}")

    if n_seeds < min_seeds:
        print(f"[{label}] 경고: seed가 {n_seeds}개뿐 (최소 {min_seeds}개 권장). 계속 진행.")

    group = df.groupby(["condition", "type", "magnitude"])
    agg_rows = []
    for (cond, ctype, mag), grp in group:
        row: dict = {"condition": cond, "type": ctype, "magnitude": mag, "n_seeds": len(grp)}
        for m in METRICS:
            row[f"{m}_mean"] = round(grp[m].mean(), 4)
            row[f"{m}_std"] = round(grp[m].std(ddof=1), 4) if len(grp) > 1 else 0.0
        # performance_drop_pct 기준값: clean(또는 obb_clean)의 map50_mean
        agg_rows.append(row)

    agg_df = pd.DataFrame(agg_rows)

    # clean 기준 성능 저하율 계산
    clean_name = "obb_clean" if label == "OBB" else "clean"
    clean_rows = agg_df[agg_df["condition"] == clean_name]["map50_mean"]
    if not clean_rows.empty:
        baseline = clean_rows.iloc[0]
        agg_df["drop_pct_mean"] = ((baseline - agg_df["map50_mean"]) / baseline * 100).round(2)
        # 오차 전파: drop = (baseline - map50) / baseline → std(drop) ≈ std(map50) / baseline
        agg_df["drop_pct_std"] = (agg_df["map50_std"] / baseline * 100).round(2)

    agg_csv.parent.mkdir(parents=True, exist_ok=True)
    agg_df.to_csv(agg_csv, index=False)
    print(f"[{label}] 집계 완료 → {agg_csv}")
    print(agg_df[["condition", "map50_mean", "map50_std", "drop_pct_mean"]].to_string(index=False))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="다중 seed 결과 집계")
    parser.add_argument("--min-seeds", type=int, default=2,
                        help="최소 seed 수 미달 시 경고 (기본: 2)")
    args = parser.parse_args()

    aggregate(config.MULTI_SEED_CSV, config.AGG_CSV, "AABB", args.min_seeds)
    aggregate(config.OBB_MULTI_SEED_CSV, config.OBB_AGG_CSV, "OBB", args.min_seeds)


if __name__ == "__main__":
    main()
