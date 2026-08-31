"""Car 단일 vs 다중 클래스 성능 저하표 비교.

docs/21 L에서 **진단** 상수가 클래스 구성을 탄다는 걸 확인했다. 이 스크립트는
그 앞단 질문에 답한다 — **오류가 성능을 떨어뜨리는 정도 자체**도 클래스가
늘면 달라지는가? 재검수 우선순위가 이 저하폭에 기대고 있으므로, 달라진다면
우선순위도 구성마다 따로 매겨야 한다.

두 CSV(metrics.csv, metrics_mc.csv)를 읽어 유형별로 나란히 놓는다. 아직 안
끝난 조건은 그냥 빠진 채로 표시된다 — 학습이 3시간 넘게 걸려서, 중간
결과로도 읽을 수 있어야 한다.

**양쪽 다 단일 시드(seed=42) 값을 쓴다.** Car에는 3-seed 집계가 있지만
다중 클래스에는 없어서, 집계값과 단일값을 섞으면 비교가 아니라 측정 방식의
차이를 보게 된다. 그래서 일부러 덜 미더운 쪽에 맞췄다 — 여기서 나오는
차이는 시드 하나만큼의 흔들림을 포함한다.

사용법:
  python compare_class_configs.py
"""
import argparse
from pathlib import Path

import pandas as pd

import config


def load(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    base = df.loc[df["condition"] == "clean", "map50"]
    if base.empty:
        return None
    df = df[df["condition"] != "clean"].copy()
    df["drop_pct"] = (base.iloc[0] - df["map50"]) / base.iloc[0] * 100
    return df


def worst_by_type(df: pd.DataFrame) -> dict[str, tuple[str, float]]:
    """유형별로 저하가 가장 큰 조건. 유형 간 비교의 대표값이다."""
    out: dict[str, tuple[str, float]] = {}
    for t, g in df.groupby("type"):
        row = g.loc[g["drop_pct"].idxmax()]
        out[t] = (row["condition"], float(row["drop_pct"]))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="클래스 구성별 성능 저하 비교")
    parser.add_argument("--out", help="표를 저장할 경로 (기본: 화면 출력만)")
    args = parser.parse_args()

    car_path = config.METRICS_CSV.with_name("metrics.csv")
    mc_path = config.METRICS_CSV.with_name("metrics_mc.csv")
    car, mc = load(car_path), load(mc_path)
    if car is None:
        raise SystemExit(f"{car_path} 없음")
    if mc is None:
        raise SystemExit(f"{mc_path} 없음 — 다중 클래스 clean 조건을 먼저 학습하세요")

    a, b = worst_by_type(car), worst_by_type(mc)
    lines = [
        "양쪽 다 seed=42 단일 시드 (다중 클래스에 3-seed 집계가 없어 맞춤)",
        f"Car 단일: {len(car)}개 조건 / 다중 클래스: {len(mc)}개 조건"
        + ("  (다중 클래스 학습 진행 중)" if len(mc) < len(car) else ""),
        "",
        f"{'유형':<16}{'Car 저하':>10}{'다중 저하':>11}{'차이':>10}  대표 조건",
        "-" * 68,
    ]
    for t in sorted(set(a) | set(b), key=lambda t: -(b.get(t, ("", 0))[1])):
        ca = a.get(t)
        cb = b.get(t)
        car_s = f"{ca[1]:.2f}%" if ca else "-"
        mc_s = f"{cb[1]:.2f}%" if cb else "미완료"
        diff = f"{cb[1] - ca[1]:+.2f}%p" if (ca and cb) else "-"
        cond = cb[0] if cb else (ca[0] if ca else "")
        lines.append(f"{t:<16}{car_s:>10}{mc_s:>11}{diff:>10}  {cond}")

    only_mc = sorted(set(b) - set(a))
    if only_mc:
        lines += ["", f"다중 클래스에만 있는 유형: {', '.join(only_mc)}"]
    missing = sorted(set(a) - set(b))
    if missing:
        lines += [f"아직 학습 안 끝난 유형: {', '.join(missing)}"]

    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
