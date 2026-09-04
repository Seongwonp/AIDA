"""자를 시드별로 바꿔가며 진단해 Y·Z·AA의 비교에 오차막대를 붙인다.

Y는 "자기 도메인 자 92.4% vs 약한 이동 자 65.5%", Z는 "먼 이동 77.7%",
AA는 "넓은 자 65.2%"라고 했는데 전부 단일 관측이었다. AB에서 조건별 저하의
시드 산포가 ±6~10%p로 크다는 걸 봤으니, 자 쪽도 흔들릴 수 있다.

**시드는 학습 시드(AIDA_TRAIN_SEED)여야 한다.** 처음엔 기존 다중 시드
실행에서 나온 자(runs_mc_e123 등)를 그대로 썼는데, 그건 오류 시드만 바꾼
것이다. 자는 전부 clean 조건에서 나오고 clean에는 주입할 오류가 없으므로,
세 자가 같은 데이터를 같은 시드로 학습한 결과였다. 남은 차이는 CUDA
비결정성뿐이라 자기 도메인 자의 표준편차가 정확히 0으로 나왔다 — 견고해서가
아니라 같은 실험을 세 번 한 것이었다. verify_seeds_differ()가 args.yaml의
seed를 직접 읽어 이걸 막는다.

같은 데이터를 자만 바꿔 진단한다. 학습은 하지 않는다(자는 이미 있다).

조건은 유형별 대표 9개로 줄인다 — 29개를 12번 돌리면 몇 시간이 걸리고,
유형별 대표만으로도 상위권 정밀도의 비교는 성립한다. **기존 값(29개 조건)과
직접 비교하지 않도록**, 네 자 모두 같은 9개로 다시 잰다.

사용법:
  AIDA_CLASSES=... AIDA_FRAME_SELECT=cyclist_rich python compare_rulers_seeded.py
"""
import json
import statistics
import sys
from pathlib import Path

import config
import evaluate_box_accuracy as E

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CONDITIONS = ["width_m30", "height_m30", "rot_m15", "trans_x_m15", "trans_y_m15",
              "scale_m30", "missing_30", "duplicate_30", "class_swap_30"]
SEEDS = [42, 123, 2024]

# 자 4종. 값은 실행 폴더 이름 — 자는 전부 그 폴더의 clean에서 나온다.
#   matched  자기 도메인 (4클래스, cyclist_rich 400장)      docs/21 Y
#   shifted  약한 이동   (4클래스, random 400장)            docs/21 Y
#   far      먼 이동     (Car 1클래스, random 400장)        docs/21 Z
#   broad    넓은 자     (4클래스, broad 800장, 평가셋 제외) docs/21 AA
RULERS = {
    "matched": ("자기 도메인", "runs_mc_cyclist_rich"),
    "shifted": ("약한 이동", "runs_mc"),
    "far": ("먼 이동(1C)", "runs"),
    "broad": ("넓은 자(800)", "runs_mc_broad_n800"),
}


def ruler_path(kind: str, seed: int) -> Path:
    """학습 시드는 실행 폴더 이름에 붙는다(clean_ts123).

    오류 시드처럼 조건 폴더를 새로 만들 필요가 없다 — clean 데이터는 어느
    시드에서나 같고, 달라지는 건 초기화와 증강 순서뿐이기 때문이다.
    """
    base = RULERS[kind][1]
    run = "clean" if seed == 42 else f"clean_ts{seed}"
    return config.EXPERIMENT_ROOT / base / run / "weights" / "best.pt"


def verify_seeds_differ(kinds: list[str]) -> None:
    """자들이 정말 다른 시드로 학습됐는지 args.yaml에서 확인.

    이 검사가 없어서 한 번 속았다. 결과가 소수점까지 같길래 캐시를 의심하고
    _tag()와 모델 로딩을 뒤졌는데, 실제로는 같은 설정을 세 번 학습한 것이었다.
    """
    for kind in kinds:
        seen = {}
        for seed in SEEDS:
            args_yaml = ruler_path(kind, seed).parent.parent / "args.yaml"
            if not args_yaml.exists():
                continue
            for line in args_yaml.read_text(encoding="utf-8").splitlines():
                if line.startswith("seed:"):
                    seen[seed] = line.split(":", 1)[1].strip()
        if len(set(seen.values())) < len(seen):
            raise SystemExit(
                f"[{kind}] 자들이 같은 학습 시드로 학습됐다: {seen} — "
                "시드 산포를 재는 실험인데 시드가 안 바뀌었다. "
                "AIDA_TRAIN_SEED를 주고 다시 학습할 것.")
        print(f"  {RULERS[kind][0]:<12} 학습 시드 {seen}")


def measure(kind: str, seed: int, limit: int) -> dict | None:
    w = ruler_path(kind, seed)
    if not w.exists():
        print(f"  [{kind} seed={seed}] {w} 없음 — 건너뜀")
        return None
    E.RULER_PATH = w
    tp = fp = 0
    p10 = []
    per_condition: dict[str, float] = {}
    silent = []
    for name in CONDITIONS:
        r = E.score_condition(config._BY_NAME[name], limit)
        tp += r["tp"]
        fp += r["fp"]
        v = r["verdicts_by_rank"]
        if not v:
            # 지목이 0건인 건 오판이 아니라 침묵이다. Car 1클래스 자는
            # 클래스 대조를 아예 하지 않으므로 class_swap에서 아무것도 내지
            # 않는다. 이걸 정밀도 0%로 세면 "틀렸다"고 말하는 셈이 된다.
            silent.append(name)
            continue
        score = E.precision_at_k(v, max(1, int(len(v) * 0.1)))
        p10.append(score)
        per_condition[name] = score
    # class_swap을 뺀 값도 같이 낸다. Car 1클래스 자는 클래스 대조를 하지
    # 않으므로 그 조건에서 내는 지목은 정의상 전부 오탐이다 — 못 맞힌 게
    # 아니라 애초에 그 판정을 안 하는 것인데, 섞어 재면 그 자에게만 벌점이
    # 된다. 실제로 섞어 재면 먼 이동 자가 1.0σ로 묻히고, 빼면 3.7σ로 산다.
    swapless = [v for n, v in per_condition.items() if not n.startswith("class_swap")]
    return {"precision": tp / (tp + fp) if tp + fp else 0.0,
            "top10": statistics.mean(p10) if p10 else 0.0,
            "top10_noswap": statistics.mean(swapless) if swapless else 0.0,
            "n_conditions": len(p10),
            # 조건별 점수를 버리지 않는다. 이게 있어야 나중에 유형별 산포를
            # GPU 재실행 없이 뽑을 수 있다 — AD 때 없어서 다시 돌려야 했다.
            "per_condition": per_condition,
            "silent": silent}


def main() -> None:
    global CONDITIONS, SEEDS
    import argparse
    ap = argparse.ArgumentParser(description="시드별 자 비교")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--rulers", nargs="+", default=list(RULERS),
                    choices=list(RULERS), help="비교할 자 (기본: 전부)")
    # class_swap을 빼고도 봐야 한다. Car 1클래스 자는 클래스 대조를 하지
    # 않으므로 그 조건에서 내는 지목은 정의상 전부 오탐이다 — 못 맞힌 게
    # 아니라 다른 이유로 지목한 것인데, 섞어 재면 그 자에게만 벌점이 된다.
    ap.add_argument("--exclude", nargs="*", default=[],
                    help="제외할 조건 이름 (예: class_swap_30)")
    # Z·AA의 원래 수치는 조건 전체에서 나왔다. 대표 9개로 줄이면 간격 자체가
    # 달라지므로(먼 이동 vs 약한 이동이 +12.2%p → +6.6%p), 그 주장을 정면으로
    # 검증하려면 같은 조건 집합으로 재야 한다.
    ap.add_argument("--all-conditions", action="store_true",
                    help="대표 9개 대신 조건 전체를 쓴다 (Z·AA와 같은 집합)")
    ap.add_argument("--seeds", type=int, nargs="+", default=SEEDS,
                    help="학습 시드 목록 (기본: 42 123 2024). n=3에서는 표준편차 "
                         "추정 자체가 흔들리므로 늘려 확인할 때 쓴다")
    ap.add_argument("--out", type=Path, default=None,
                    help="조건별 점수까지 담은 JSON 저장 경로")
    args = ap.parse_args()

    SEEDS = args.seeds
    if args.all_conditions:
        CONDITIONS = [c.name for c in config.CONDITIONS + config.CLASS_SWAP_CONDITIONS]
    if args.exclude:
        CONDITIONS = [c for c in CONDITIONS if c not in args.exclude]
        print(f"제외한 조건: {', '.join(args.exclude)}")
    print(f"조건 {len(CONDITIONS)}개 × 자 {len(args.rulers)}종 × 학습 시드 {SEEDS}")
    verify_seeds_differ(args.rulers)
    print()

    out: dict[str, list[dict]] = {}
    silent_note: dict[str, list[str]] = {}
    for kind in args.rulers:
        label = RULERS[kind][0]
        rows = []
        for seed in SEEDS:
            print(f"[{label} seed={seed}] 진단 중...", flush=True)
            m = measure(kind, seed, args.limit)
            if m:
                rows.append(m)
                print(f"    정밀도 {m['precision']*100:.1f}%  "
                      f"상위10% {m['top10']*100:.1f}%  "
                      f"(class_swap 제외 {m['top10_noswap']*100:.1f}%)  "
                      f"(조건 {m['n_conditions']}개)")
                if m["silent"]:
                    silent_note[label] = m["silent"]
        out[label] = rows

    print(f"\n{'자':<14}{'n':>3}{'상위10% 평균':>14}{'±':>8}{'전체 정밀도':>14}")
    print("-" * 55)
    stats = {}
    for label, rows in out.items():
        if not rows:
            continue
        t = [r["top10"] * 100 for r in rows]
        p = [r["precision"] * 100 for r in rows]
        sd = statistics.stdev(t) if len(t) > 1 else float("nan")
        stats[label] = (statistics.mean(t), sd)
        print(f"{label:<14}{len(t):>3}{statistics.mean(t):>13.1f}%{sd:>8.2f}"
              f"{statistics.mean(p):>13.1f}%")

    for label, names in silent_note.items():
        print(f"\n  {label}: {', '.join(names)}에서 지목 0건 — 평균에서 뺐다. "
              f"탐지하지 못한 게 아니라 그 판정을 하지 않는다.")

    # 자기 도메인을 기준으로 나머지와의 간격을 시드 산포와 견준다.
    base = "자기 도메인"
    if base in stats and len(stats) > 1:
        ma, sa = stats[base]
        print(f"\n{base} 기준 간격:")
        for label, (mb, sb) in stats.items():
            if label == base:
                continue
            gap = ma - mb
            pooled = (((sa ** 2 + sb ** 2) / 2) ** 0.5
                      if sa == sa and sb == sb else float("nan"))
            line = f"  vs {label:<14}{gap:+6.1f}%p  합동σ ±{pooled:.2f}"
            if pooled == pooled and pooled > 0:
                n_sigma = abs(gap) / pooled
                line += (f"  = {n_sigma:.1f}σ → "
                         f"{'산포를 넘는다' if n_sigma >= 2 else '산포에 묻힌다'}")
            print(line)

    if args.out:
        args.out.write_text(json.dumps({
            "conditions": CONDITIONS,
            "seeds": SEEDS,
            "limit": args.limit,
            "rulers": {label: rows for label, rows in out.items()},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n조건별 점수 저장 → {args.out}")


if __name__ == "__main__":
    main()
