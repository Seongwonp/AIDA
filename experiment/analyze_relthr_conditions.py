"""AO의 손해가 **어느 조건**에서 나는지 (docs/23 계획 1번).

AU까지는 조건 26~29개의 평균만 있었다. "COCO 자기에서만 손해"까지는 갈렸지만
왜인지는 못 봤다. `relative_threshold.py --per-condition`이 남긴 조건별 기록을
모아 미리 정한 기준으로 판정한다(`PREDICTION_ao_why_coco.md`).

    1차  음수 조건의 절반 이상이 시드 4개 이상에서 반복되면 "몰린다"
    2차  손해 조건에서 승격된 유형이 주입된 유형과 다른가

사용법:
  python analyze_relthr_conditions.py                # 손해가 난 자만
  python analyze_relthr_conditions.py --all-kinds    # 전부
"""
import argparse
import collections
import io
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from evaluate_box_accuracy import _type_matches  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = pathlib.Path(__file__).resolve().parent
REPEAT_SEEDS = 4   # 이 이상에서 반복되면 "조건의 성질"로 본다 (미리 정한 선)


def main() -> None:
    ap = argparse.ArgumentParser(description="AO 손해를 조건별로 가른다")
    ap.add_argument("--glob", default="relfb_*.json")
    ap.add_argument("--all-kinds", action="store_true")
    args = ap.parse_args()

    # kind -> condition -> [(seed, delta, injected, promoted, abs_empty), ...]
    by_kind: dict = collections.defaultdict(lambda: collections.defaultdict(list))
    labels: dict[str, str] = {}
    for f in sorted(HERE.glob(args.glob)):
        d = json.load(io.open(f, encoding="utf-8"))
        for row in d["rows"]:
            if "per_condition" not in row:
                continue
            labels[row["kind"]] = row["label"]
            for c in row["per_condition"]:
                by_kind[row["kind"]][c["condition"]].append(
                    (d["seed"], c["delta5"], c["injected"],
                     tuple(c["promoted_types"]), c["absolute_empty"]))

    if not by_kind:
        raise SystemExit("조건별 기록이 있는 파일이 없습니다 (--per-condition으로 재실행)")

    for kind, conds in by_kind.items():
        harmed = {name: obs for name, obs in conds.items()
                  if any(d < 0 for _s, d, *_ in obs)}
        if not harmed and not args.all_kinds:
            print(f"\n■ {labels[kind]} — 음수 조건 없음")
            continue

        n_seeds = max(len(o) for o in conds.values())
        print(f"\n■ {labels[kind]} — 조건 {len(conds)}개 · 시드 {n_seeds}개")
        if not harmed:
            print("  음수 조건 없음")
            continue

        print(f"  {'조건':<20}{'주입':<14}{'음수 시드':>10}{'평균 변화':>11}  승격된 유형")
        repeated = 0
        for name, obs in sorted(harmed.items(),
                                key=lambda kv: sum(1 for o in kv[1] if o[1] < 0),
                                reverse=True):
            neg = [o for o in obs if o[1] < 0]
            promoted = sorted({t for _s, _d, _i, tup, _e in neg for t in tup})
            avg = sum(o[1] for o in obs) / len(obs)
            if len(neg) >= REPEAT_SEEDS:
                repeated += 1
            print(f"  {name:<20}{obs[0][2]:<14}{f'{len(neg)}/{len(obs)}':>10}"
                  f"{avg:>+11.3f}  {', '.join(promoted) or '—'}")

        print(f"\n  1차 — 음수 조건 {len(harmed)}개 중 시드 {REPEAT_SEEDS}개 이상에서"
              f" 반복된 것 {repeated}개")
        verdict = ("몰린다 — 조건의 성질이 원인이다"
                   if repeated * 2 >= len(harmed) else
                   "흩어진다 — 자의 흔들림이고 끄는 규칙의 근거가 약하다")
        print(f"      → {verdict}")

        # 2차: 승격된 유형이 주입된 유형과 다른가
        #
        # **문자열로 비교하면 안 된다.** class_swap의 의심 유형 이름은
        # class_mismatch이고 rotation은 width/height/scale로 나온다. 처음에
        # 문자열로 셌다가 그 조건들을 전부 "못 맞힘"으로 넣었다 (docs/21 AY).
        same = diff = 0
        for name, obs in harmed.items():
            for _s, delta, injected, promoted, _e in obs:
                if delta >= 0:
                    continue
                if any(_type_matches(injected, t) for t in promoted):
                    same += 1
                else:
                    diff += 1
        print(f"  2차 — 손해가 난 (조건,시드) {same + diff}개 중 "
              f"승격 유형이 주입 유형과 **다른** 경우 {diff}개, 같은 경우 {same}개")


if __name__ == "__main__":
    main()
