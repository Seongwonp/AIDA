"""자 적합도가 진단 품질을 예측하는가 (docs/22 계획 1번).

제품은 화면에 "이 모델이 라벨의 31%를 짚었습니다"를 띄우고 절반 미만이면
경고한다. 그런데 **그 문턱에 눈금이 없다.** 31%가 얼마나 나쁜지, 60%면
괜찮은지 우리가 모른다.

적합도(라벨 중 예측과 짝지어진 비율)는 **정답 없이 재는 값**이라 고객 환경에서
그대로 쓸 수 있다. 상위 10% 정밀도는 정답이 있어야 재지는 값이라 고객 환경에서
못 쓴다. 그러니 "값싼 쪽이 비싼 쪽을 예측하는가"를 여기서 확인한다.

**학습은 하지 않는다.** 자는 AG·AI에서 이미 다 학습해뒀고, 조건별 정밀도도
이미 저장돼 있다(seeded_*.json). 여기서 새로 재는 것은 적합도뿐이다.

## 무엇을 어떻게 보나

같은 조건 안에서 자들을 견준다. 조건이 다르면 난이도가 달라 정밀도도 적합도도
같이 움직이는데, 그건 "적합도가 예측한다"가 아니라 "둘 다 조건을 탄다"일 뿐이다.
**조건을 고정하고 자만 바꿔야** 교란이 빠진다 — 그게 제품이 실제로 하는 선택
("이 데이터에 어느 자를 쓸까")이기도 하다.

사용법 (환경은 원래 실험과 같게 줘야 한다):

  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" AIDA_FRAME_SELECT=cyclist_rich \\
    ./venv/Scripts/python.exe fit_vs_quality.py \\
      --source seeded_ruler4_7seeds.json --out fit_vs_quality_kitti.json

  AIDA_DATASET=coco ./venv/Scripts/python.exe fit_vs_quality.py \\
      --source seeded_coco_3seeds.json --out fit_vs_quality_coco.json
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import config
import evaluate_box_accuracy as E
from compare_rulers_seeded import RULERS, ruler_path

# 자가 아는 클래스 수. runs*(_mc 없음)는 Car 1클래스다 — config.py의
# 접미사 규칙과 같은 이야기라 여기서도 폴더 이름으로 가른다.
def ruler_class_count(kind: str) -> int | None:
    base = RULERS[kind][1]
    return None if "_mc" in base or "coco" in base else 1

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def rows_from_seeded(src: dict) -> dict:
    """채점 결과에서 (자, 시드, 조건) → {적합도, 정밀도}를 뽑는다.

    적합도와 정밀도가 **같은 채점 한 번**에서 나온 값이라 짝이 정확히 맞는다.
    AL에서는 둘을 따로 재서 조인이 유효한지 따로 확인해야 했다.
    """
    rows: dict[str, dict] = {}
    for label, per_seed in src["rulers"].items():
        rows[label] = {}
        for i, seed in enumerate(src["seeds"]):
            if i >= len(per_seed) or per_seed[i] is None:
                continue
            entry = per_seed[i]
            fit = entry.get("per_condition_fit") or {}
            prec = entry["per_condition"]
            if not fit:
                raise SystemExit(
                    f"{label} seed {seed}에 per_condition_fit이 없다 — "
                    "적합도를 같이 남기기 전에 만든 결과다. --from-seeded 말고 "
                    "그냥 --source로 측정할 것.")
            rows[label][str(seed)] = {
                c: {"fit": fit[c], "precision": prec[c]}
                for c in prec if c in fit
            }
    return rows


def kind_by_label(label: str) -> str:
    """저장된 JSON은 자를 한글 이름으로 갖고 있다. 코드 쪽 키로 되돌린다."""
    for kind, (name, _base) in RULERS.items():
        if name == label:
            return kind
    raise SystemExit(f"모르는 자 이름: {label} (RULERS에 없다)")


def measure_fit(kind: str, seed: int, conditions: list[str], limit: int) -> dict[str, float]:
    """이 자·이 시드로 조건마다 적합도를 잰다. 정답을 안 쓰는 값이다."""
    w = ruler_path(kind, seed)
    if not w.exists():
        print(f"  [{kind} seed={seed}] {w} 없음 — 건너뜀")
        return {}
    E.RULER_PATH = w
    out = {}
    for name in conditions:
        r = E.score_condition(config._BY_NAME[name], limit)
        if r["matched_label_ratio"] is not None:
            out[name] = r["matched_label_ratio"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True,
                    help="조건별 정밀도가 들어 있는 seeded_*.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--analyze-only", action="store_true",
                    help="--out에 이미 있는 측정을 읽어 분석만 다시 한다 (GPU 안 씀)")
    ap.add_argument("--from-seeded", action="store_true",
                    help="--source가 조건별 적합도까지 갖고 있으면 재지 않고 바로 읽는다")
    args = ap.parse_args()

    if args.from_seeded:
        src = json.loads(Path(args.source).read_text(encoding="utf-8"))
        rows = rows_from_seeded(src)
        Path(args.out).write_text(json.dumps(
            {"source": args.source, "conditions": src["conditions"],
             "seeds": src["seeds"], "limit": src["limit"], "rows": rows},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장 → {args.out} (측정 없음)")
        analyze(rows, src["conditions"], src["seeds"])
        return

    if args.analyze_only:
        saved = json.loads(Path(args.out).read_text(encoding="utf-8"))
        analyze(saved["rows"], saved["conditions"], saved["seeds"])
        return

    src = json.loads(Path(args.source).read_text(encoding="utf-8"))
    conditions, seeds, limit = src["conditions"], src["seeds"], src["limit"]
    labels = list(src["rulers"])
    print(f"자 {len(labels)}종 · 시드 {len(seeds)}개 · 조건 {len(conditions)}개 "
          f"· 이미지 {limit}장")
    print("적합도만 잰다 — 학습 없음, 정답 없음.\n")

    # rows[(자, 시드, 조건)] = {"fit": ..., "precision": ...}
    rows: dict[str, dict] = {}
    for label in labels:
        kind = kind_by_label(label)
        per_seed = src["rulers"][label]
        rows[label] = {}
        for i, seed in enumerate(seeds):
            if i >= len(per_seed) or per_seed[i] is None:
                continue
            fit = measure_fit(kind, seed, conditions, limit)
            prec = per_seed[i]["per_condition"]
            paired = {c: {"fit": fit[c], "precision": prec[c]}
                      for c in conditions if c in fit and c in prec}
            rows[label][str(seed)] = paired
            print(f"  {label:<14} seed {seed:<6} 짝지은 조건 {len(paired)}개 "
                  f"· 적합도 중앙값 {statistics.median(f['fit'] for f in paired.values()):.3f}")

    Path(args.out).write_text(json.dumps(
        {"source": args.source, "conditions": conditions, "seeds": seeds,
         "limit": limit, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 → {args.out}")

    analyze(rows, conditions, seeds)


def label_class_share(conditions: list[str], cls: int = 0, limit: int = 80) -> float | None:
    """평가에 쓰는 라벨 중 클래스 `cls`의 비중.

    1클래스 자의 적합도 천장이 곧 이 값이다 — 나머지 클래스의 라벨은
    그 자가 무슨 수를 써도 짝지을 수 없다.
    """
    for name in conditions:
        root = config.CONDITIONS_DIR / name / "labels" / "train"
        if not root.is_dir():
            continue
        total = hit = 0
        for i, f in enumerate(sorted(root.glob("*.txt"))):
            if i >= limit:
                break
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    total += 1
                    hit += (int(line.split()[0]) == cls)
        return hit / total if total else None
    return None


def analyze(rows: dict, conditions: list[str], seeds: list[int]) -> None:
    labels = list(rows)

    print("\n" + "=" * 66)
    print("자별 평균 — 적합도와 정밀도가 같은 순서로 늘어서나")
    print("=" * 66)
    print(f"{'자':<16}{'적합도':>10}{'상위10% 정밀도':>16}")
    means = {}
    for label in labels:
        fits, precs = [], []
        for per_cond in rows[label].values():
            fits += [v["fit"] for v in per_cond.values()]
            precs += [v["precision"] for v in per_cond.values()]
        if not fits:
            continue
        means[label] = (statistics.mean(fits), statistics.mean(precs))
        print(f"{label:<16}{means[label][0]:>10.3f}{means[label][1]:>16.3f}")

    by_fit = sorted(means, key=lambda k: -means[k][0])
    by_prec = sorted(means, key=lambda k: -means[k][1])
    print(f"\n  적합도 순: {' > '.join(by_fit)}")
    print(f"  정밀도 순: {' > '.join(by_prec)}")
    print(f"  → 순서가 {'같다' if by_fit == by_prec else '다르다'}")
    print("  주의: 점이 자 개수만큼뿐이다. 순서가 같다는 것 이상은 못 읽는다.")

    if len(labels) < 2:
        return

    # --- 교란을 뺀 비교: 조건을 고정하고 자만 바꾼다 -------------------------
    print("\n" + "=" * 66)
    print("조건을 고정하고 자만 바꾸면 — 적합도가 높은 자가 정밀도도 높나")
    print("=" * 66)
    print("조건이 다르면 난이도가 달라 둘 다 같이 움직인다. 그건 '적합도가")
    print("예측한다'가 아니라 '둘 다 조건을 탄다'일 뿐이라 조건을 고정한다.\n")

    hit = tie = miss = 0
    gaps = []
    for cond in conditions:
        for seed in seeds:
            pts = []
            for label in labels:
                v = rows[label].get(str(seed), {}).get(cond)
                if v:
                    pts.append((label, v["fit"], v["precision"]))
            if len(pts) < 2:
                continue
            best_fit = max(pts, key=lambda p: p[1])
            best_prec = max(p[2] for p in pts)
            if best_fit[2] == best_prec:
                # 정밀도가 동점인 자가 여럿이면 맞혔다고 세지 않는다
                if sum(1 for p in pts if p[2] == best_prec) > 1:
                    tie += 1
                else:
                    hit += 1
            else:
                miss += 1
            gaps.append(best_prec - best_fit[2])

    total = hit + tie + miss
    chance = 1 / len(labels)
    print(f"  적합도 1등 자가 정밀도도 1등인 경우 : {hit}/{total} "
          f"({hit / total * 100:.1f}%)")
    print(f"  정밀도 1등이 동점이라 못 세는 경우  : {tie}/{total}")
    print(f"  아닌 경우                          : {miss}/{total}")
    print(f"  무작위로 골랐을 때 기대값          : {chance * 100:.1f}%")
    print(f"\n  적합도로 고른 자를 썼을 때 놓치는 정밀도(평균): {statistics.mean(gaps):.3f}")
    print(f"  최악의 경우                                   : {max(gaps):.3f}")

    # --- 가까이 붙은 자끼리도 구분하나 -------------------------------------
    print("\n" + "=" * 66)
    print("자를 둘씩 짝지어 — 가까운 자끼리도 순서를 맞히나")
    print("=" * 66)
    print("멀리 떨어진 자를 가려내는 건 쉽다. 실제 고객 상황은 그럴듯한 자")
    print("두엇 중에 고르는 것이라, 가까운 짝에서도 맞아야 쓸모가 있다.\n")
    print(f"{'자 두 대':<34}{'적합도차':>9}{'정밀도차':>9}{'순서맞힘':>10}")

    pairs = [(a, b) for i, a in enumerate(labels) for b in labels[i + 1:]]
    for a, b in pairs:
        agree = total = 0
        fit_gaps, prec_gaps = [], []
        for cond in conditions:
            for seed in seeds:
                va = rows[a].get(str(seed), {}).get(cond)
                vb = rows[b].get(str(seed), {}).get(cond)
                if not va or not vb or va["precision"] == vb["precision"]:
                    continue        # 정밀도가 같으면 맞히고 말고가 없다
                total += 1
                fit_gaps.append(abs(va["fit"] - vb["fit"]))
                prec_gaps.append(abs(va["precision"] - vb["precision"]))
                higher_fit = a if va["fit"] > vb["fit"] else b
                higher_prec = a if va["precision"] > vb["precision"] else b
                agree += (higher_fit == higher_prec)
        if not total:
            continue
        pct = agree / total * 100
        mark = "★" if pct >= 70 else ("·" if pct >= 50 else "✗")
        print(f"{a + ' vs ' + b:<34}{statistics.mean(fit_gaps):>9.3f}"
              f"{statistics.mean(prec_gaps):>9.3f}{pct:>9.1f}% {mark}")
    print("\n  50%가 동전 던지기다. 적합도 차이가 작은 짝에서 50% 근처면,")
    print("  '가까운 자는 구분 못 한다'는 뜻이다.")

    # --- 왜 거꾸로 맞히나: 적합도에는 구조적 천장이 있다 ---------------------
    print("\n" + "=" * 66)
    print("적합도의 천장 — 자가 아는 클래스가 좁으면 눈금 자체가 다르다")
    print("=" * 66)
    print("적합도는 '라벨 중 예측과 짝지어진 비율'이다. 자가 모르는 클래스의")
    print("라벨은 절대 안 짝지어지므로, 좁은 자는 아무리 잘해도 그 클래스들의")
    print("비중만큼을 못 채운다. 그 자의 적합도를 넓은 자와 나란히 놓으면")
    print("**서로 다른 눈금을 비교하는 것**이 된다.\n")

    car_share = label_class_share(conditions)
    if car_share is None:
        print("  라벨 구성을 읽지 못해 건너뛴다.")
    else:
        print(f"  평가 데이터의 Car 비중: {car_share:.3f}")
        print(f"\n{'자':<16}{'천장':>8}{'적합도':>9}{'천장 대비':>11}{'정밀도':>9}")
        for label in labels:
            if label not in means:
                continue
            kind = kind_by_label(label)
            ceiling = car_share if ruler_class_count(kind) == 1 else 1.0
            fit, prec = means[label]
            print(f"{label:<16}{ceiling:>8.3f}{fit:>9.3f}"
                  f"{fit / ceiling:>11.3f}{prec:>9.3f}")
        print("\n  천장이 1.0이 아닌 자와 1.0인 자를 생짜 적합도로 견주면 안 된다.")

    # --- 제품이 쓰려는 모양: 적합도 구간 → 정밀도 ---------------------------
    print("\n" + "=" * 66)
    print("적합도 구간별 정밀도 — 제품이 쓰려는 눈금")
    print("=" * 66)
    buckets: dict[str, list[float]] = {}
    for label in labels:
        for per_cond in rows[label].values():
            for v in per_cond.values():
                b = min(int(v["fit"] * 10), 9)
                buckets.setdefault(f"{b*10}~{b*10+9}%", []).append(v["precision"])
    for key in sorted(buckets, key=lambda k: int(k.split("~")[0])):
        vals = buckets[key]
        bar = "#" * int(statistics.mean(vals) * 40)
        print(f"  적합도 {key:>8}  n={len(vals):<5} 정밀도 {statistics.mean(vals):.3f}  {bar}")
    print("\n  이 표는 조건 교란이 안 빠져 있다. 위의 '조건 고정' 결과와 같이 읽을 것.")


if __name__ == "__main__":
    main()
