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
            # 관측이 하나뿐이면 표준편차는 **모른다**. 0.0으로 적으면 "변동이
            # 없다"로 읽히고, report.py의 유의성 검사가 std>0 조건에서 조용히
            # 넘어가 크기만으로 등급을 매기게 된다. 빈 값으로 두면 하위 코드가
            # "집계 없음"으로 보고 같은 판단을 하되 근거를 오해하지 않는다.
            row[f"{m}_std"] = (round(grp[m].std(ddof=1), 4) if len(grp) > 1
                               else float("nan"))
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
    thin = agg_df[agg_df["n_seeds"] < min_seeds]["condition"].tolist()
    if thin:
        print(f"[{label}] seed가 {min_seeds}개 미만인 조건 {len(thin)}개는 표준편차가 "
              f"비어 있습니다: {', '.join(thin[:5])}"
              + (" ..." if len(thin) > 5 else ""))
    print(agg_df[["condition", "n_seeds", "map50_mean", "map50_std",
                  "drop_pct_mean"]].to_string(index=False))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="다중 seed 결과 집계")
    parser.add_argument("--min-seeds", type=int, default=2,
                        help="최소 seed 수 미달 시 경고 (기본: 2)")
    args = parser.parse_args()

    aggregate(config.MULTI_SEED_CSV, config.AGG_CSV, "AABB", args.min_seeds)
    if config.MULTICLASS:
        # OBB 지표는 클래스 구성별로 갈려 있지 않다(run_obb.py의
        # _refuse_multiclass 참고). 여기서 집계하면 Car 것을 다시 만지면서
        # 뭔가 한 것처럼 보인다.
        print("다중 클래스 구성이라 OBB 집계는 건너뜁니다 (단일 클래스 전용)")
    else:
        aggregate(config.OBB_MULTI_SEED_CSV, config.OBB_AGG_CSV, "OBB", args.min_seeds)


if __name__ == "__main__":
    main()
