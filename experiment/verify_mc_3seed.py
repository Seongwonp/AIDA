"""다중 클래스 3-seed로 L~AA의 결론이 버티는지 판정한다.

L부터 AA까지의 다중 클래스 수치는 전부 단일 관측이었다. 단일 관측을 믿었다가
두 번 데였다 — S는 데이터 오염으로 결론이 뒤집혔고, T는 1회차에서 상한을
넘는 불가능한 값이 나왔다. 여기서 시드 산포를 붙여 무엇이 살아남는지 본다.

세 가지를 묻는다:
  1. 조건별 저하가 학습 흔들림과 구분되는가 (σ = 저하 / 시드 간 표준편차)
  2. 클래스 오기입의 용량-반응(10 → 20 → 30%)이 시드를 바꿔도 단조인가
  3. Q가 말한 "Car보다 다중 클래스가 더 아프다"가 σ로 뒷받침되는가

부분 데이터로도 돌아간다 — 시드가 모자라면 그렇다고 말하고 넘어간다.

사용법:
  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" python verify_mc_3seed.py
"""
import sys

import pandas as pd

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 실험 중 만든 임시 조건들(재검수 시뮬레이션·정제 부분집합)은 시드를 안 돌렸다
TEMP_MARKERS = ("_fix_", "_asis", "_refined", "_sub")
SIGNIFICANT_SIGMA = 2.0


def real_conditions(df: pd.DataFrame) -> pd.DataFrame:
    mask = ~df["condition"].str.contains("|".join(TEMP_MARKERS), regex=True)
    return df[mask]


def main() -> None:
    path = config.MULTI_SEED_CSV
    if not path.exists():
        raise SystemExit(f"{path} 없음 — run_multi_seed.py를 먼저 돌리세요")
    df = real_conditions(pd.read_csv(path))
    seeds = sorted(df["error_seed"].unique())
    print(f"{path.name}: 시드 {seeds}, 조건 {df['condition'].nunique()}개\n")

    per_seed = df.groupby("error_seed")["condition"].nunique()
    incomplete = per_seed[per_seed < per_seed.max()]
    if len(incomplete):
        print("아직 안 끝난 시드가 있습니다:")
        for s, n in incomplete.items():
            print(f"  seed {s}: {n}/{per_seed.max()}개")
        print()

    # clean 기준 저하율을 시드별로 계산한 뒤 조건별 평균·표준편차
    rows = []
    for seed, grp in df.groupby("error_seed"):
        base = grp.loc[grp["condition"] == "clean", "map50"]
        if base.empty:
            print(f"[경고] seed {seed}에 clean이 없어 건너뜁니다")
            continue
        b = float(base.iloc[0])
        for _, r in grp[grp["condition"] != "clean"].iterrows():
            rows.append({"condition": r["condition"], "type": r["type"],
                         "magnitude": r["magnitude"], "error_seed": seed,
                         "drop_pct": (b - r["map50"]) / b * 100})
    if not rows:
        raise SystemExit("저하율을 계산할 데이터가 없습니다")
    d = pd.DataFrame(rows)

    print("=== 1. 조건별 저하가 학습 흔들림과 구분되는가 ===\n")
    agg = d.groupby(["condition", "type"]).agg(
        n=("drop_pct", "size"), mean=("drop_pct", "mean"),
        std=("drop_pct", lambda s: s.std(ddof=1) if len(s) > 1 else float("nan")),
    ).reset_index()
    agg["sigma"] = agg["mean"] / agg["std"]
    agg = agg.sort_values("mean", ascending=False)
    print(f"{'조건':<16}{'n':>3}{'저하':>9}{'±':>8}{'σ':>7}  판정")
    print("-" * 56)
    for _, r in agg.iterrows():
        if pd.isna(r["std"]):
            verdict = "시드 부족"
            sig = "-"
        else:
            sig = f"{r['sigma']:.1f}"
            verdict = "유의" if r["sigma"] >= SIGNIFICANT_SIGMA else "노이즈와 구분 안 됨"
        print(f"{r['condition']:<16}{int(r['n']):>3}{r['mean']:>8.2f}%"
              f"{r['std'] if pd.notna(r['std']) else float('nan'):>8.2f}{sig:>7}  {verdict}")

    print("\n=== 2. 클래스 오기입의 용량-반응 ===\n")
    cs = agg[agg["type"] == "class_swap"].copy()
    if cs.empty:
        print("  class_swap 조건이 없습니다")
    else:
        cs["pct"] = cs["condition"].str.extract(r"(\d+)$").astype(int)
        cs = cs.sort_values("pct")
        for _, r in cs.iterrows():
            print(f"  주입 {r['pct']:>2}%: 저하 {r['mean']:>6.2f}% "
                  f"± {r['std'] if pd.notna(r['std']) else float('nan'):.2f}")
        monotone = cs["mean"].is_monotonic_increasing
        print(f"  단조 증가: {'예' if monotone else '아니오'}")

    print("\n=== 3. Car 단일과의 비교 (같은 조건끼리) ===\n")
    car_path = config.METRICS_CSV.with_name("metrics.csv")
    if not car_path.exists():
        print("  metrics.csv 없음 — 비교 생략")
        return
    car = pd.read_csv(car_path)
    cb = car.loc[car["condition"] == "clean", "map50"]
    if cb.empty:
        print("  metrics.csv에 clean이 없어 비교 생략")
        return
    cb = float(cb.iloc[0])
    car = car[car["condition"] != "clean"].set_index("condition")
    car_drop = ((cb - car["map50"]) / cb * 100)

    shared = [c for c in agg["condition"] if c in car_drop.index]
    if not shared:
        print("  공통 조건이 없습니다")
        return
    diffs = []
    for c in shared:
        m = agg.loc[agg["condition"] == c].iloc[0]
        gap = m["mean"] - car_drop[c]
        # 다중 클래스 쪽 산포만 알고 있으므로 그것으로만 나눈다 (보수적)
        diffs.append((c, car_drop[c], m["mean"], gap,
                      gap / m["std"] if pd.notna(m["std"]) and m["std"] else float("nan")))
    diffs.sort(key=lambda x: -x[3])
    print(f"{'조건':<16}{'Car':>8}{'다중(평균)':>12}{'차이':>9}{'σ':>7}")
    print("-" * 54)
    for c, a, b, gap, sg in diffs:
        print(f"{c:<16}{a:>7.2f}%{b:>11.2f}%{gap:>+8.2f}%p"
              f"{(f'{sg:.1f}' if pd.notna(sg) else '-'):>7}")
    ok = sum(1 for *_x, gap, _s in diffs if gap > 0)
    print(f"\n  다중 클래스가 더 아픈 조건: {ok}/{len(diffs)}")
    strong = [d for d in diffs if pd.notna(d[4]) and d[4] >= SIGNIFICANT_SIGMA]
    print(f"  그중 시드 산포의 {SIGNIFICANT_SIGMA}배를 넘는 것: {len(strong)}개")


if __name__ == "__main__":
    main()
