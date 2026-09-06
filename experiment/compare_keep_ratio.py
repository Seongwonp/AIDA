"""자기 정제를 두 개의 자로 동시에 잰다 (docs/21 AS·AT).

AJ부터 AS까지 열두 점을 **교환 비율** 하나로 쟀다.

    교환 비율 = 천장 / 손해
              = (clean_sub{남긴 수} − refined{k}) / (clean − clean_sub{남긴 수})

이 자에는 `missing_30`(정제를 아예 안 한 원본)이 분자에도 분모에도 없다.
정제를 **"완벽한 정제"와** 견줄 뿐 **"안 하기"와** 견주지 않는다. 그런데
고객이 실제로 고르는 것은 후자다.

그래서 keep을 1에 가깝게 하면 비율이 저절로 오른다 — keep=1.0이면 손해가 0이고
천장은 clean − missing_30(0이 아니다)이라 **비율이 +∞로 발산한다.** 아무것도
안 버려도 "정제가 이긴다"가 나온다.

이 스크립트는 그래서 **직접 차이를 먼저** 찍는다:

    직접 차이 = refined{k} − 원본조건

사용법:
  python compare_keep_ratio.py                 # missing_30, 400·800장
  python compare_keep_ratio.py --condition scale_m30 --scales 400 800 1600
"""
import argparse
import pathlib
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA = pathlib.Path(__file__).resolve().parent.parent / "backend" / "app" / "data"
# 천장·차이 모두 두 학습 결과의 차이라 실행 간 산포(±0.0185)가 √2배로 붙는다.
NOISE = 0.026


def metrics(n: int) -> pd.Series | None:
    f = DATA / f"metrics_mc_nested{'' if n == 400 else f'_n{n}'}.csv"
    if not f.exists():
        return None
    return pd.read_csv(f).set_index("condition")["map50"].astype(float)


def main() -> None:
    ap = argparse.ArgumentParser(description="자기 정제를 직접 기준과 교환 비율로 동시에")
    ap.add_argument("--condition", default="missing_30")
    ap.add_argument("--scales", type=int, nargs="+", default=[400, 800])
    ap.add_argument("--keeps", type=int, nargs="+", default=[30, 50, 70, 90])
    args = ap.parse_args()

    rows = []
    for n in args.scales:
        d = metrics(n)
        if d is None:
            print(f"[{n}장] metrics 없음 — 건너뜀")
            continue
        for k in args.keeps:
            ref, ctrl = f"{args.condition}_refined{k}", f"clean_sub{int(n * k / 100)}"
            if any(c not in d.index for c in (args.condition, ref, ctrl, "clean")):
                continue
            rows.append((n, k, d[args.condition], d[ref], d[ctrl], d["clean"]))

    if not rows:
        raise SystemExit("비교할 데이터가 없습니다")

    print(f"조건 {args.condition} · 다중 클래스 · 중첩 부분집합 · 평가셋 800장 고정\n")
    print("1차 기준 — 정제한 것이 원본 그대로보다 나은가 (이것으로 판정한다)")
    print(f"{'규모':<7}{'남길 비율':>10}{'안 함':>9}{'정제':>9}{'차이':>10}   판정")
    print("-" * 62)
    for n, k, base, ref, _ctrl, _clean in rows:
        diff = ref - base
        verdict = ("정제가 이긴다" if diff > NOISE
                   else "비긴다(흔들림 안)" if diff > -NOISE else "정제가 진다")
        print(f"{n:<7}{k:>9}%{base:>9.3f}{ref:>9.3f}{diff:>+10.3f}   {verdict}")

    print(f"\n판정 눈금은 학습 실행 간 흔들림 ±{NOISE:.3f}이다 (검정 아님).")

    print("\n2차 — 교환 비율 (보고만 한다, 승패 판정에 쓰지 않는다)")
    print(f"{'규모':<7}{'남길 비율':>10}{'손해':>9}{'천장':>9}{'비율':>9}")
    print("-" * 46)
    for n, k, _base, ref, ctrl, clean in rows:
        loss, ceil = clean - ctrl, ctrl - ref
        ratio = f"{ceil / loss:>9.2f}" if loss else f"{'∞':>9}"
        print(f"{n:<7}{k:>9}%{loss:>9.3f}{ceil:>9.3f}{ratio}")

    print("\n  이 비율은 keep→1에서 +∞로 발산한다 — 손해는 0으로 가는데 천장은")
    print("  clean − 원본조건으로 남기 때문이다. 그래서 비율이 1.0을 넘는 것은")
    print("  정제를 잘했다는 뜻이 아니라 적게 버렸다는 뜻일 수 있다.")
    for n in sorted({r[0] for r in rows}):
        d = metrics(n)
        if d is not None and args.condition in d.index:
            print(f"    {n}장 keep 100%: 손해 0.000, "
                  f"천장 {d['clean'] - d[args.condition]:.3f} → 비율 ∞")


if __name__ == "__main__":
    main()
