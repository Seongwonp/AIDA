"""자들 사이의 모든 쌍 간격을 시드 산포와 견준다.

compare_rulers_seeded.py는 자기 도메인 자를 기준으로만 비교한다. 그런데
Z의 주장("먼 자가 약한 이동 자보다 낫다")과 AA의 주장("넓은 자가 약한 이동
자와 같다")은 **자기 도메인 자가 안 끼는 쌍**이라, 기준 하나로는 확인이
안 된다. 로그에서 값을 읽어 모든 쌍을 재계산한다.

사용법:
  python pairwise_rulers.py seeded_ruler4.log
"""
import itertools
import re
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADER = re.compile(r"^\[(.+?) seed=(\d+)\]")
VALUE = re.compile(r"상위10% ([\d.]+)%")


def parse(path: Path) -> dict[str, list[float]]:
    """진단 로그에서 자별 상위10% 값들을 뽑는다."""
    out: dict[str, list[float]] = {}
    label = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        h = HEADER.match(line.strip())
        if h:
            label = h.group(1)
            continue
        v = VALUE.search(line)
        if v and label:
            out.setdefault(label, []).append(float(v.group(1)))
            label = None
    return out


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "seeded_ruler4.log")
    data = parse(path)
    if not data:
        raise SystemExit(f"{path}에서 값을 못 읽었다")

    print(f"{path.name}\n")
    print(f"{'자':<14}{'n':>3}{'평균':>9}{'표준편차':>10}   값")
    print("-" * 62)
    stats = {}
    for label, vals in data.items():
        m = statistics.mean(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else float("nan")
        stats[label] = (m, sd, len(vals))
        print(f"{label:<14}{len(vals):>3}{m:>8.1f}%{sd:>10.2f}   "
              + " / ".join(f"{v:.1f}" for v in vals))

    print(f"\n{'쌍':<30}{'간격':>9}{'합동σ':>9}{'σ배수':>8}  판정")
    print("-" * 68)
    for a, b in itertools.combinations(stats, 2):
        ma, sa, _ = stats[a]
        mb, sb, _ = stats[b]
        gap = ma - mb
        pooled = ((sa ** 2 + sb ** 2) / 2) ** 0.5
        n = abs(gap) / pooled if pooled > 0 else float("inf")
        # 2σ를 넘어야 시드를 바꿔도 남는 차이라고 말한다. AB에서 쓴 기준과 같다.
        verdict = "산포를 넘는다" if n >= 2 else "산포에 묻힌다"
        print(f"{a + ' vs ' + b:<30}{gap:>+8.1f}%p{pooled:>8.2f}{n:>7.1f}σ  {verdict}")


if __name__ == "__main__":
    main()
