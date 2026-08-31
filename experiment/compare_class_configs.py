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
import sys
from pathlib import Path

import pandas as pd

import config


# Windows 콘솔 기본 코드페이지(cp949)가 em-dash 같은 문자를 못 찍어서 죽는다.
# 결과를 못 보는 것보다 글자 하나가 물음표로 나오는 편이 낫다.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


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


def by_condition(df: pd.DataFrame) -> dict[str, float]:
    """조건 이름 → 저하율.

    유형별 최대치로 비교하면 안 된다. 두 가지 이유가 있다.

    1. **양쪽의 조건 구성이 다르면 비교가 아니다.** 다중 클래스 학습이
       진행 중이라 한쪽엔 _30만 있고 다른 쪽엔 _15/_30이 다 있다. 최대끼리
       맞대면 조건이 더 많은 쪽이 유리해진다.
    2. **효과가 0인 유형에서 최대를 고르는 건 노이즈를 고르는 것이다.**
       중복은 3-seed로 저하가 없다는 게 확인됐는데(docs/21 I), 단일 시드
       3개 중 최대를 뽑으면 1.14%가 나온다.

    그래서 같은 이름의 조건끼리만 짝지어 비교한다.
    """
    return {row["condition"]: float(row["drop_pct"]) for _, row in df.iterrows()}


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

    a, b = by_condition(car), by_condition(mc)
    types = dict(zip(mc["condition"], mc["type"])) | dict(zip(car["condition"], car["type"]))
    shared = [c for c in b if c in a]

    lines = [
        "양쪽 다 seed=42 단일 시드 (다중 클래스에 3-seed 집계가 없어 맞춤)",
        f"Car 단일 {len(a)}개 조건 / 다중 클래스 {len(b)}개 조건 "
        f"— 같은 조건 {len(shared)}개만 비교"
        + ("  (다중 클래스 학습 진행 중)" if len(b) < len(a) else ""),
        "",
        f"{'조건':<16}{'유형':<15}{'Car':>9}{'다중':>9}{'차이':>10}",
        "-" * 62,
    ]
    for c in sorted(shared, key=lambda c: -(b[c] - a[c])):
        lines.append(f"{c:<16}{types.get(c, ''):<15}{a[c]:>8.2f}%{b[c]:>8.2f}%"
                     f"{b[c] - a[c]:>+9.2f}%p")

    if shared:
        diffs = [b[c] - a[c] for c in shared]
        lines += ["", f"평균 차이 {sum(diffs) / len(diffs):+.2f}%p "
                      f"(범위 {min(diffs):+.2f} ~ {max(diffs):+.2f}%p)"]

    only_mc = sorted(set(b) - set(a))
    if only_mc:
        lines += ["", "다중 클래스에만 있는 조건 (Car에는 대응이 없어 비교 불가):"]
        lines += [f"  {c:<16}{types.get(c, ''):<15}{b[c]:>8.2f}%" for c in only_mc]
    pending = sorted(set(a) - set(b))
    if pending:
        lines += ["", f"아직 학습 안 끝난 조건 {len(pending)}개: {', '.join(pending)}"]

    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
