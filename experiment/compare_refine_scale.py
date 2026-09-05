"""자기 정제의 손익을 데이터 규모별로 분해한다 (docs/21 W·X).

W는 400장에서 정제가 진다고 결론냈다. 이유는 "이미지를 반 버리는 손해(-0.181)가
오류가 주던 손해(-0.103)보다 크다"였다. 그런데 400장은 YOLOv8n에게 너무 적어서,
그 손해가 규모 탓일 수 있었다.

같은 분해를 800장에서 반복해 교환 비율이 뒤집히는지 본다.

  전체N장 · 오류 0%   (clean)          상한
  전체N장 · 오류 30%  (scale_m30)      정제 안 함
  절반   · 오류 0%    (clean_sub)      데이터 손해만 분리한 대조군
  절반   · 오류 ~12%  (refined50)      정제한 것

사용법:
  python compare_refine_scale.py
"""
import sys

import pandas as pd

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA = config.EXPERIMENT_ROOT.parent / "backend" / "app" / "data"

# X가 쓴 두 점. 이 둘은 **프레임 구성도 달랐다**(400은 무작위 520, 800은
# 로컬 전부)라, clean이 오른 데 규모 말고 장면 분포도 섞여 있었다.
LEGACY_SETUPS = [
    ("400장", "metrics_mc.csv", "clean_sub200", 400, 200),
    ("800장", "metrics_mc_all_local_n800.csv", "clean_sub400", 800, 400),
]

# 중첩 부분집합으로 다시 잰 네 점. 한 순열에서 앞부터 잘라 쓰므로 작은
# 규모가 큰 규모의 부분집합이고, 평가셋은 목록 끝에서 고정된다. 그래서
# 네 점이 서로 비교 가능하다.
def nested_setups(mc: bool) -> list:
    """중첩 부분집합 네 점. mc면 다중 클래스 산출물을 읽는다.

    경로 접미사는 config가 정하는 규칙과 같아야 한다 — 클래스 구성이
    앞(_mc), 프레임 선택이 그다음(_nested), 규모가 마지막(_n800)이다.
    여기서 어긋나면 없는 파일을 찾거나, 더 나쁘게는 다른 실험의 수치를
    읽는다.
    """
    prefix = "metrics_mc_nested" if mc else "metrics_nested"
    return [
        (f"{n}장", f"{prefix}{'' if n == 400 else f'_n{n}'}.csv",
         f"clean_sub{n // 2}", n, n // 2)
        for n in (400, 800, 1600, 3200)
    ]


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="자기 정제 손익을 규모별로 분해")
    ap.add_argument("--legacy", action="store_true",
                    help="X가 쓴 두 점(프레임 구성이 다름)을 본다")
    ap.add_argument("--mc", action="store_true",
                    help="다중 클래스 규모 실험 결과를 본다 (X와 같은 클래스 구성)")
    args = ap.parse_args()
    setups = LEGACY_SETUPS if args.legacy else nested_setups(args.mc)
    if args.legacy:
        print("프레임 구성이 다른 두 점 (docs/21 X)")
    else:
        print(f"중첩 부분집합 · 고정 평가셋 · "
              f"{'다중 클래스' if args.mc else 'Car 단일 클래스'}")
    print()

    rows = []
    for label, csv, ctrl, full, half in setups:
        path = DATA / csv
        if not path.exists():
            print(f"[{label}] {csv} 없음 — 건너뜀")
            continue
        df = pd.read_csv(path).set_index("condition")
        need = ["clean", "scale_m30", ctrl, "scale_m30_refined50"]
        missing = [c for c in need if c not in df.index]
        if missing:
            print(f"[{label}] 아직 없는 조건: {missing}")
            continue
        g = lambda c: float(df.loc[c, "map50"])
        rows.append((label, full, half, g("clean"), g("scale_m30"),
                     g(ctrl), g("scale_m30_refined50")))

    if not rows:
        raise SystemExit("비교할 데이터가 없습니다")

    print(f"{'규모':<8}{'전체·오류0%':>12}{'전체·오류30%':>13}"
          f"{'절반·오류0%':>13}{'절반·오류12%':>13}")
    print("-" * 60)
    for label, full, half, c, s, ctrl, ref in rows:
        print(f"{label:<8}{c:>12.3f}{s:>13.3f}{ctrl:>13.3f}{ref:>13.3f}")

    print(f"\n{'규모':<8}{'절반 버리는 손해':>18}{'오류 30%의 손해':>17}"
          f"{'정제로 얻을 천장':>18}")
    print("-" * 62)
    for label, full, half, c, s, ctrl, ref in rows:
        data_loss = c - ctrl          # 라벨은 깨끗한 채 이미지만 반으로
        error_loss = c - s            # 이미지는 그대로 두고 오류만
        ceiling = ctrl - ref          # 남은 오류를 완벽히 지웠을 때의 이득
        print(f"{label:<8}{data_loss:>17.3f}{error_loss:>17.3f}{ceiling:>18.3f}")

    print("\n정제가 이기려면 '정제로 얻을 천장'이 '절반 버리는 손해'보다 커야 한다.")
    for label, full, half, c, s, ctrl, ref in rows:
        data_loss, ceiling = c - ctrl, ctrl - ref
        verdict = "정제가 이긴다" if ceiling > data_loss else "정제가 진다"
        ratio = ceiling / data_loss if data_loss else float("inf")
        print(f"  {label}: 천장 {ceiling:.3f} vs 손해 {data_loss:.3f} "
              f"= {ratio:.2f}배 → {verdict}")

    # 규모가 커질수록 비율이 1에 가까워지는가. X는 점 두 개로 "7배
    # 좋아졌다"고만 말할 수 있었고, 어디서 뒤집히는지는 말할 수 없다고 적었다.
    if len(rows) >= 3:
        print()
        print("규모에 따른 교환 비율 추세 (1.0을 넘으면 정제가 이긴다)")
        ratios = []
        for label, full, half, c, sm, ctrl, ref in rows:
            loss, ceil = c - ctrl, ctrl - ref
            ratios.append((full, ceil / loss if loss else float("inf")))
        for n, ratio in ratios:
            bar = "#" * min(int(ratio * 40), 60)
            print(f"  {n:>5}장  {ratio:>5.2f}  {bar}")
        vals = [r for _n, r in ratios]
        up = all(b > a for a, b in zip(vals, vals[1:]))
        down = all(b < a for a, b in zip(vals, vals[1:]))
        if up:
            print("  → 관측값이 계속 오른다 (단일 관측이므로 추세로 단정하지 않는다)")
        elif down:
            print("  → 관측값이 계속 내린다 (단일 관측이므로 추세로 단정하지 않는다)")
        else:
            # 양 끝만 비교하면 가운데가 제일 높아도 "올랐다"고 말하게 된다.
            # X가 점 둘로 직선을 그었고, AJ에서 점 셋으로 같은 실수를 할
            # 뻔했다(0.58/0.56/0.24 → "줄어든다" → 네 번째 0.47이 지웠다).
            # "현상이 오르내린다"가 아니라 "관측값이 단조가 아니다"까지만
            # 말한다. 각 점이 단일 관측이라 그 이상은 이 데이터로 못 한다.
            print(f"  → 관측값이 단조가 아니다 — 규모에 따른 추세를 말할 수 없다 "
                  f"(최저 {min(vals):.2f}, 최고 {max(vals):.2f}, "
                  f"양 끝 {vals[0]:.2f} → {vals[-1]:.2f})")

        # 그 오르내림이 잴 수 있는 크기인가. 천장은 두 학습 결과의 차이이므로
        # 실행 간 산포(AJ의 ±0.0185)가 √2배로 붙는다 → ±0.026.
        NOISE = 0.026
        ceilings = [ctrl - ref for _l, _f, _h, _c, _s, ctrl, ref in rows]
        spread = max(ceilings) - min(ceilings)
        print(f"\n  천장 {len(ceilings)}개의 폭 {spread:.3f} vs "
              f"학습 실행 간 흔들림 ±{NOISE:.3f} (검정 아님, 대략적 눈금)")
        # 폭이 흔들림과 "같다"는 건 실재한다는 뜻이 아니라 구분이 안 된다는
        # 뜻이다. 처음엔 1.0배에서 "실재한다"고 찍었는데, 그러면 AJ가 같은
        # 값(0.027 vs 0.026)을 두고 "흔들림"이라 한 결론과 어긋난다.
        if spread <= NOISE:
            print("  → 규모별 천장 차이는 측정된 것이 아니라 흔들림으로 봐야 한다")
        elif spread < 2 * NOISE:
            print(f"  → 폭이 흔들림의 {spread / NOISE:.1f}배뿐이라 "
                  f"흔들림과 구분되지 않는다")
        else:
            print(f"  → 폭이 흔들림의 {spread / NOISE:.1f}배 — 이 차이는 실재한다")


if __name__ == "__main__":
    main()
